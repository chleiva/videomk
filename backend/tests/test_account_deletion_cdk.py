"""Account deletion in the CDK template: the routes, the queue, the worker's rights, and the check that nothing a person owns can be missed (docs/ACCOUNT_DELETION.md).
The coverage check is built from the stack's own resources: a new table, bucket or vector index that is not listed in account_deletion.py fails here."""
import glob
import json
import os
import re
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "lambdas"))

import account_deletion as ad  # noqa: E402
from common import deletion  # noqa: E402


@pytest.fixture(scope="module")
def synth():
    import aws_cdk as cdk
    from aws_cdk.assertions import Template

    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        from backend_stack import BackendStack
        cache = {}

        def build(**ctx):
            ctx.setdefault("engine", "v2")
            key = tuple(sorted(ctx.items()))
            if key not in cache:
                app = cdk.App(context={"stage": "qa", **ctx}, outdir=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"vmk-del-{len(cache)}"))
                os.environ.setdefault("CDK_SKIP_LAYER_CHECK", "1")
                stack = BackendStack(app, "videomk-qa", stage="qa", stage_cfg={"account": "123456789012", "region": "eu-west-1", "domain": None, "callbackUrls": ["https://qa.videomk.com/auth/callback"]},
                                     env=cdk.Environment(account="123456789012", region="eu-west-1"))
                cache[key] = Template.from_stack(stack).to_json()
            return cache[key]
        yield build
    finally:
        os.chdir(cwd)


def of(t, typ):
    return {k: v for k, v in t["Resources"].items() if v["Type"] == typ}


def fn_id(t, name):
    hits = [k for k, v in of(t, "AWS::Lambda::Function").items() if v["Properties"].get("FunctionName") == name]
    assert len(hits) == 1, (name, hits)
    return hits[0]


def statements(t, name):
    role = t["Resources"][fn_id(t, name)]["Properties"]["Role"]["Fn::GetAtt"][0]
    out = []
    for p in of(t, "AWS::IAM::Policy").values():
        if {"Ref": role} in p["Properties"]["Roles"]:
            for s in p["Properties"]["PolicyDocument"]["Statement"]:
                acts = s["Action"] if isinstance(s["Action"], list) else [s["Action"]]
                res = s["Resource"] if isinstance(s["Resource"], list) else [s["Resource"]]
                out.append({"actions": acts, "resources": res, "conditions": s.get("Condition"), "effect": s["Effect"]})
    return out


def grants(t, name, action):
    return [s for s in statements(t, name) if action in s["actions"] or any(a.endswith(":*") and action.startswith(a[:-1]) for a in s["actions"])]


def env(t, name):
    return t["Resources"][fn_id(t, name)]["Properties"]["Environment"]["Variables"]


def mentions(resources, logical_id):
    return any(logical_id in json.dumps(r) for r in resources)


def ids_matching(t, typ, regex):
    return [k for k in of(t, typ) if re.search(regex, k)]


# ----------------------------------------------------------------------------- nothing a person owns can be forgotten
def test_every_table_bucket_and_index_of_the_stack_is_either_cleaned_or_explicitly_exempt(synth):
    t = synth()
    tables = list(of(t, "AWS::DynamoDB::Table"))
    for k in tables:
        covered = [n for n in ad.COVERED_TABLES if re.search(n, k)]
        exempt = [n for n in ad.EXEMPT_TABLES if re.search(n, k)]
        assert len(covered) + len(exempt) == 1, f"table {k} is not covered by the account deletion (account_deletion.py COVERED_TABLES / EXEMPT_TABLES): decide whether it holds personal data"
    assert not [n for n in list(ad.COVERED_TABLES) + list(ad.EXEMPT_TABLES) if not any(re.search(n, k) for k in tables)], "a listed table no longer exists in the stack"
    buckets = list(of(t, "AWS::S3::Bucket"))
    for k in buckets:
        assert sum(1 for n in ad.COVERED_BUCKETS if re.search(n, k)) == 1, f"bucket {k} is not covered by the account deletion"
    assert len(buckets) == len(ad.COVERED_BUCKETS)
    indexes = list(of(t, "AWS::S3Vectors::Index"))
    for k in indexes:
        assert any(re.search(n, k) for n in ad.COVERED_VECTOR_INDEXES), f"vector index {k} is not covered by the account deletion"
    assert len(indexes) == len(ad.COVERED_VECTOR_INDEXES)
    queues = of(t, "AWS::SQS::Queue")
    assert queues, "sanity"


def test_the_worker_can_delete_from_every_covered_table_and_knows_its_name(synth):
    t = synth()
    e = env(t, "account_deleter")
    names = {"VideosTable": "VIDEOS_TABLE", "UsageTable": "USAGE_TABLE", "WalletTable": "WALLET_TABLE", "AccountFlagsTable": "FLAGS_TABLE", "MediaTable": "MEDIA_TABLE", "SafetyTable": "SAFETY_TABLE"}
    assert set(names) == set(ad.COVERED_TABLES)
    for pattern, var in names.items():
        lid = ids_matching(t, "AWS::DynamoDB::Table", pattern)[0]
        assert json.dumps(e[var]) .find(lid) >= 0, f"{var} does not point at {lid}"
        assert any(mentions(s["resources"], lid) and ("dynamodb:DeleteItem" in s["actions"]) for s in statements(t, "account_deleter")), f"the worker cannot delete from {lid}"
    for bucket in ("AssetsBucket", "MediaBucket"):
        lid = ids_matching(t, "AWS::S3::Bucket", bucket)[0]
        name = json.dumps(t["Resources"][lid]["Properties"]["BucketName"])   # some policies name the bucket by its fixed name, others by reference
        assert any((mentions(s["resources"], lid) or name.strip('"') in json.dumps(s["resources"])) and "s3:DeleteObject" in s["actions"] for s in statements(t, "account_deleter")), f"the worker cannot delete objects of {lid}"
    idx = ids_matching(t, "AWS::S3Vectors::Index", "PhotoIndex")[0]
    assert any(mentions(s["resources"], idx) and "s3vectors:DeleteVectors" in s["actions"] for s in statements(t, "account_deleter"))


def test_the_prefixes_the_code_writes_are_all_covered(synth):
    """Scans the Lambda sources for S3 key prefixes built from a user or video id and for the usage-counter key prefixes; each must be in the deletion's lists."""
    src = []
    for f in glob.glob(os.path.join(ROOT, "lambdas", "**", "*.py"), recursive=True):
        if "/tests/" not in f:
            src.append((f, open(f).read()))
    found = set()
    for _, text in src:
        for m in re.finditer(r'f["\']((?:[a-z0-9_]+/)+)\{', text):
            found.add(m.group(1))
    covered = {p.split("{")[0] for p in deletion.ASSET_USER_PREFIXES + deletion.ASSET_VIDEO_PREFIXES + deletion.MEDIA_PREFIXES} | set(deletion.SHARED_PREFIXES)
    assert found, "the scan found nothing: the pattern is stale"
    assert found <= covered, f"S3 prefixes written by the code but not removed by the account deletion: {sorted(found - covered)}"
    usage = set()
    for _, text in src:
        usage |= set(re.findall(r'usage\.[a-z_]+\(f"([a-z]+:)\{', text))
        usage |= set(re.findall(r'"user_id": f"([a-z]+:)\{', text))
    flags = {p for p in usage if p == "safety:"}
    usage -= flags
    assert usage, "the scan found nothing: the pattern is stale"
    assert usage <= set(deletion.USAGE_PREFIXES), f"usage-table partitions written by the code but not removed: {sorted(usage - set(deletion.USAGE_PREFIXES))}"
    assert "safety:{u}" in deletion.FLAG_KEYS


def test_the_worker_deletes_per_user_prefixes_only(synth):
    t = synth()
    s3 = [s for s in statements(t, "account_deleter") if any(a.startswith("s3:") for a in s["actions"])]
    assert s3
    for s in s3:
        assert s["effect"] == "Allow" and set(s["actions"]) <= {"s3:DeleteObject", "s3:ListBucket"}      # no read, no write, no whole-bucket delete
        assert "*" not in s["resources"]
        if "s3:DeleteObject" in s["actions"]:
            tails = [(r["Fn::Join"][1][-1] if isinstance(r, dict) and "Fn::Join" in r else r) for r in s["resources"]]
            assert all(re.search(r"/(videos|uploads|generation/v2|generation/assets|o|t)/\*$", x) for x in tails), tails      # exactly the per-user areas, never a bucket-wide delete
        else:
            prefixes = s["conditions"]["StringLike"]["s3:prefix"]
            assert set(prefixes) <= {"videos/*", "uploads/*", "generation/v2/*", "generation/assets/*", "o/*", "t/*"}


def test_the_worker_has_no_wildcard_resources_and_the_only_write_it_has_is_deleting(synth):
    t = synth()
    for s in statements(t, "account_deleter"):
        if s["actions"] == ["logs:CreateLogStream", "logs:PutLogEvents"]:
            continue
        assert "*" not in s["resources"], s
        for a in s["actions"]:
            assert not a.endswith(":*"), s
    ddb_write = {a for s in statements(t, "account_deleter") for a in s["actions"] if a.startswith("dynamodb:") and not a.startswith(("dynamodb:Get", "dynamodb:Query", "dynamodb:Batch", "dynamodb:Scan", "dynamodb:Describe", "dynamodb:Condition"))}
    assert ddb_write <= {"dynamodb:DeleteItem", "dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:ConditionCheckItem"}


def test_the_admin_only_flags_table_is_delete_only_for_the_worker_and_stays_unwritable_for_everyone_else(synth):
    t = synth()
    flags = ids_matching(t, "AWS::DynamoDB::Table", "AccountFlagsTable")[0]
    for s in statements(t, "account_deleter"):
        if mentions(s["resources"], flags):
            assert s["actions"] == ["dynamodb:DeleteItem"], s
    for name in ("account_api", "wallet_api", "VideoGenerationSFLauncher", "library_api", "video_brief", "apple_revoke"):
        try:
            sts = statements(t, name)
        except AssertionError:
            continue
        for s in sts:
            if mentions(s["resources"], flags):
                assert not (set(s["actions"]) & {"dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:BatchWriteItem"}), (name, s)


def test_cognito_deletion_rights_belong_to_the_worker_alone_and_are_scoped_to_the_pool(synth):
    t = synth(appleRevoke="1")
    names = [v["Properties"]["FunctionName"] for v in of(t, "AWS::Lambda::Function").values() if "FunctionName" in v["Properties"]]
    for n in names:
        try:
            sts = statements(t, n)
        except (AssertionError, KeyError):
            continue
        dangerous = [s for s in sts if set(s["actions"]) & {"cognito-idp:AdminDeleteUser", "cognito-idp:AdminDisableUser", "cognito-idp:AdminUserGlobalSignOut"}]
        assert (n == "account_deleter") == bool(dangerous), n
    for s in grants(t, "account_deleter", "cognito-idp:AdminDeleteUser"):
        assert s["resources"] == [{"Fn::GetAtt": [ids_matching(t, "AWS::Cognito::UserPool", "UserPool")[0], "Arn"]}]


def test_only_the_worker_may_stop_workflows_and_only_the_video_machines(synth):
    t = synth()
    sts = grants(t, "account_deleter", "states:StopExecution")
    assert sts and all("*" not in s["resources"] for s in sts)
    blob = json.dumps(sts)
    assert ":execution:" in blob and "stateMachine" not in blob.replace("StateMachine", "")
    for n in ("account_api", "wallet_api"):
        assert not grants(t, n, "states:StopExecution")


# ----------------------------------------------------------------------------- the routes and the queue
def api_methods(t):
    res = of(t, "AWS::ApiGateway::Resource")
    parts = {}

    def path(k):
        r = res[k]["Properties"]
        parent = r["ParentId"]
        base = path(parent["Ref"]) if isinstance(parent, dict) and "Ref" in parent else ""
        return f"{base}/{r['PathPart']}"
    out = {}
    for m in of(t, "AWS::ApiGateway::Method").values():
        p = m["Properties"]
        rid = p["ResourceId"]
        if isinstance(rid, dict) and "Ref" in rid and rid["Ref"] in res:
            out[(p["HttpMethod"], path(rid["Ref"]))] = p
    return out


def test_the_delete_route_exists_and_needs_a_cognito_sign_in(synth):
    t = synth()
    m = api_methods(t)[("POST", "/users/{user_id}/account/delete")]
    assert m["AuthorizationType"] == "COGNITO_USER_POOLS" and "AuthorizerId" in m
    assert ("POST", "/users/{user_id}/account/apple-revoke") not in api_methods(t)
    assert ("POST", "/account/apple-callback") not in api_methods(t)


def test_the_queue_has_a_dead_letter_queue_a_long_enough_timeout_and_partial_failure_reporting(synth):
    t = synth()
    q = [v for k, v in of(t, "AWS::SQS::Queue").items() if "AccountDeletionDeletionQueue" in k][0]["Properties"]
    assert q["RedrivePolicy"]["maxReceiveCount"] == 5 and q["VisibilityTimeout"] >= 600
    worker = t["Resources"][fn_id(t, "account_deleter")]["Properties"]
    assert worker["Timeout"] <= q["VisibilityTimeout"]
    m = [v for v in of(t, "AWS::Lambda::EventSourceMapping").values() if json.dumps(v["Properties"]["FunctionName"]).find(fn_id(t, "account_deleter")) >= 0][0]["Properties"]
    assert m["FunctionResponseTypes"] == ["ReportBatchItemFailures"] and m["BatchSize"] == 1


def test_failures_have_a_metric_filter_and_alarms(synth):
    t = synth()
    mf = [v for v in of(t, "AWS::Logs::MetricFilter").values() if "ACCOUNT_DELETION_FAILED" in v["Properties"]["FilterPattern"]]
    assert mf and "ACCOUNT_DELETION_STUCK" in mf[0]["Properties"]["FilterPattern"]
    assert len([k for k in of(t, "AWS::CloudWatch::Alarm") if "AccountDeletion" in k]) == 2


def test_the_deletion_table_has_a_ttl_and_no_backup_and_the_key_secret_exists(synth):
    t = synth()
    tb = [v for k, v in of(t, "AWS::DynamoDB::Table").items() if "AccountDeletionTable" in k][0]["Properties"]
    assert tb["TimeToLiveSpecification"] == {"AttributeName": "ttl", "Enabled": True}
    assert not tb.get("PointInTimeRecoverySpecification", {}).get("PointInTimeRecoveryEnabled")      # a backup would keep what a person asked us to delete
    assert any("DeletionKey" in k for k in of(t, "AWS::SecretsManager::Secret"))


def test_the_wallet_functions_can_read_the_deletion_table_and_never_write_it(synth):
    t = synth()
    tbl = ids_matching(t, "AWS::DynamoDB::Table", "AccountDeletionTable")[0]
    for n in ("wallet_api", "VideoGenerationSFLauncher"):
        assert env(t, n)["DELETION_TABLE"] and env(t, n)["TOMBSTONE_ENABLED"] == "0"
        for s in statements(t, n):
            if mentions(s["resources"], tbl):
                assert not (set(s["actions"]) & {"dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:BatchWriteItem"}), (n, s)
        assert not grants(t, n, "cognito-idp:ListUsers")                                           # no Cognito rights unless the tombstone is switched on


# ----------------------------------------------------------------------------- the flags
def test_the_tombstone_is_off_by_default_and_the_switch_adds_exactly_its_rights(synth):
    off, on = synth(), synth(accountTombstone="1")
    assert env(off, "account_deleter")["TOMBSTONE_ENABLED"] == "0" and env(on, "account_deleter")["TOMBSTONE_ENABLED"] == "1"
    assert env(on, "wallet_api")["TOMBSTONE_ENABLED"] == "1" and env(on, "wallet_api")["TOMBSTONE_DAYS"] == "90"
    for n in ("wallet_api", "VideoGenerationSFLauncher"):
        assert grants(on, n, "cognito-idp:ListUsers") and not grants(on, n, "cognito-idp:AdminGetUser")
        assert any("DeletionKey" in json.dumps(s["resources"]) for s in grants(on, n, "secretsmanager:GetSecretValue"))
    assert synth(accountTombstone="1", tombstoneDays="30") is not None and env(synth(accountTombstone="1", tombstoneDays="30"), "wallet_api")["TOMBSTONE_DAYS"] == "30"


def test_apple_revocation_is_off_by_default_and_has_no_trace_in_the_template(synth):
    t = synth()
    assert not [v for v in of(t, "AWS::Lambda::Function").values() if v["Properties"].get("FunctionName") == "apple_revoke"]
    assert not of(t, "AWS::Lambda::LayerVersion") or all("cryptography" not in json.dumps(v) for v in of(t, "AWS::Lambda::LayerVersion").values())
    assert "apple_private_key" not in json.dumps(t)
    assert not [k for k in of(t, "AWS::Lambda::LayerVersion") if "Apple" in k]
    assert env(t, "account_api")["APPLE_REVOKE_ENABLED"] == "0" and "APPLE_RETURN_URL" not in env(t, "account_api")
    assert not [k for k in t["Outputs"] if "AppleRevokeReturnUrl" in k]


def test_apple_revocation_on_adds_two_routes_one_public_callback_and_a_scoped_function(synth):
    t = synth(appleRevoke="1")
    m = api_methods(t)
    assert m[("POST", "/users/{user_id}/account/apple-revoke")]["AuthorizationType"] == "COGNITO_USER_POOLS"
    assert m[("POST", "/account/apple-callback")]["AuthorizationType"] == "NONE"            # Apple's own form post: the signed state is the credential
    fn = t["Resources"][fn_id(t, "apple_revoke")]["Properties"]
    assert fn["Layers"] and any("AppleDepsLayer" in json.dumps(l) for l in fn["Layers"])
    sts = statements(t, "apple_revoke")
    secret = [s for s in sts if "secretsmanager:GetSecretValue" in s["actions"]]
    assert len(secret) == 2 and any("apple_private_key-*" in json.dumps(s["resources"]) for s in secret) and any("DeletionKey" in json.dumps(s["resources"]) for s in secret)
    ssm = [r for s in sts if "ssm:GetParameter" in s["actions"] for r in s["resources"]]
    assert len(ssm) == 3 and all("parameter/videomk/apple_" in json.dumps(r) for r in ssm)
    assert not [s for s in sts if any(a.startswith(("s3:", "cognito-idp:", "states:", "s3vectors:")) for a in s["actions"])]
    dyn = [s for s in sts if any(a.startswith("dynamodb:") for a in s["actions"])]
    assert dyn and all(mentions(s["resources"], ids_matching(t, "AWS::DynamoDB::Table", "AccountDeletionTable")[0]) for s in dyn)
    assert [k for k in t["Outputs"] if "AppleRevokeReturnUrl" in k]
    for n in ("account_api", "wallet_api", "account_deleter"):
        assert not [s for s in statements(t, n) if "apple_private_key" in json.dumps(s["resources"])], n   # nobody else can read the Apple key


def test_the_api_function_cannot_touch_user_data(synth):
    t = synth()
    e = env(t, "account_api")
    assert e["USER_POOL_ID"] and e["DELETION_QUEUE_URL"] and "SAFETY_TABLE" not in e
    for s in statements(t, "account_api"):
        assert not any(a.startswith(("s3:", "s3vectors:", "states:")) for a in s["actions"]), s
        assert not (set(s["actions"]) & {"cognito-idp:AdminDeleteUser", "cognito-idp:AdminDisableUser"}), s
