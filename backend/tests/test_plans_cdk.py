"""Plans in the CDK stack (backend/plans_feature.py): additive resources, least privilege, the switch, the alarms. docs/PLANS.md."""
import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)


@pytest.fixture(scope="module")
def synth():
    import aws_cdk as cdk
    from aws_cdk.assertions import Template

    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        from backend_stack import BackendStack
        cache = {}

        def build(stage="qa", **ctx):
            ctx.setdefault("engine", "v2")
            key = (stage,) + tuple(sorted(ctx.items()))
            if key not in cache:
                app = cdk.App(context={"stage": stage, **ctx}, outdir=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"vmk-plans-{len(cache)}"))
                os.environ.setdefault("CDK_SKIP_LAYER_CHECK", "1")
                stack = BackendStack(app, f"videomk-{stage}", stage=stage, stage_cfg={"account": "123456789012", "region": "eu-west-1", "domain": None, "callbackUrls": ["https://qa.videomk.com/auth/callback"]},
                                     env=cdk.Environment(account="123456789012", region="eu-west-1"))
                cache[key] = Template.from_stack(stack).to_json()
            return cache[key]
        yield build
    finally:
        os.chdir(cwd)


def of(t, kind):
    return {k: v for k, v in t["Resources"].items() if v["Type"] == kind}


def fn(t, name):
    return next(v for v in of(t, "AWS::Lambda::Function").values() if v["Properties"].get("FunctionName") == name)


def env(t, name):
    return fn(t, name)["Properties"]["Environment"]["Variables"]


def statements(t, name):
    """Every IAM statement attached to the role of the function called `name`: [{actions, resources (as JSON text)}]."""
    role = fn(t, name)["Properties"]["Role"]["Fn::GetAtt"][0]
    out = []
    for p in of(t, "AWS::IAM::Policy").values():
        if any(r.get("Ref") == role for r in p["Properties"].get("Roles", [])):
            for s in p["Properties"]["PolicyDocument"]["Statement"]:
                acts = s["Action"] if isinstance(s["Action"], list) else [s["Action"]]
                out.append({"actions": acts, "resources": json.dumps(s["Resource"])})
    return out


def table_id(t, pattern):
    return next(k for k in of(t, "AWS::DynamoDB::Table") if pattern in k)


def can(t, name, action, resource_id):
    wild = action.split(":")[0] + ":*"
    return any((action in s["actions"] or wild in s["actions"]) and resource_id in s["resources"] for s in statements(t, name))


WRITES = ("dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:BatchWriteItem", "dynamodb:DeleteItem")
READERS = ("VideoGenerationSFLauncher", "wallet_api", "capabilities_api", "plans_api", "watermark_api", "library_api", "library_ingest")


def test_plans_are_on_by_default_and_every_function_that_needs_the_plan_can_read_it(synth):
    t = synth()
    ent = table_id(t, "EntitlementsTable")
    for name in READERS:
        e = env(t, name)
        assert e["PLANS_ENABLED"] == "1" and ent in json.dumps(e["ENTITLEMENTS_TABLE"]), name
        assert can(t, name, "dynamodb:GetItem", ent), name
    for name in ("VideoGenerationSFLauncher", "wallet_api", "capabilities_api", "plans_api"):
        assert env(t, name)["PLANS_CONFIG_PARAM"] == "/videomk/qa/plans/config"
        assert any("ssm:GetParameter" in s["actions"] and "/videomk/qa/plans/config" in s["resources"] for s in statements(t, name)), name


def test_no_function_can_write_an_entitlement_and_only_the_deletion_worker_can_remove_one(synth):
    t = synth(deviceProof="1")
    ent = table_id(t, "EntitlementsTable")
    for f in of(t, "AWS::Lambda::Function").values():
        name = f["Properties"].get("FunctionName")
        if not name:
            continue
        for action in WRITES:
            allowed = can(t, name, action, ent)
            assert allowed == (name == "account_deleter" and action == "dynamodb:DeleteItem"), f"{name} may {action} on the entitlements table"


def test_only_the_granting_functions_touch_the_free_claims(synth):
    t = synth(deviceProof="1")
    claims = table_id(t, "FreeClaimsTable")
    writers = {f["Properties"]["FunctionName"] for f in of(t, "AWS::Lambda::Function").values() if f["Properties"].get("FunctionName") and can(t, f["Properties"]["FunctionName"], "dynamodb:PutItem", claims)}
    assert writers == {"VideoGenerationSFLauncher", "wallet_api", "device_api"}
    assert not any(can(t, n, "dynamodb:DeleteItem", claims) or can(t, n, "dynamodb:Scan", claims) for n in writers)
    assert not can(t, "account_deleter", "dynamodb:DeleteItem", claims)   # the claim survives account deletion on purpose (a salted hash, no account id)
    assert t["Resources"][claims]["Properties"]["TimeToLiveSpecification"] == {"AttributeName": "ttl", "Enabled": True}


def test_the_new_tables_are_the_only_new_tables_and_existing_ones_keep_their_keys(synth):
    on, off = synth(), synth(plans="0")
    new = set(of(on, "AWS::DynamoDB::Table")) - set(of(off, "AWS::DynamoDB::Table"))
    assert len(new) == 2 and any("EntitlementsTable" in k for k in new) and any("FreeClaimsTable" in k for k in new)
    for k, v in of(off, "AWS::DynamoDB::Table").items():
        assert on["Resources"][k] == v, f"{k} changed"
    for kind in ("AWS::Cognito::UserPool", "AWS::S3::Bucket", "AWS::Cognito::UserPoolClient"):
        assert of(on, kind) == of(off, kind), kind
    assert on["Resources"][table_id(on, "EntitlementsTable")]["Properties"]["KeySchema"] == [{"AttributeName": "user_id", "KeyType": "HASH"}]


def test_switched_off_nothing_of_plans_exists(synth):
    t = synth(plans="0")
    names = {f["Properties"].get("FunctionName") for f in of(t, "AWS::Lambda::Function").values()}
    assert not names & {"plans_api", "gallery_api", "plans_daily", "device_api"}
    assert "PLANS_ENABLED" not in env(t, "VideoGenerationSFLauncher") and "PLANS_ENABLED" not in env(t, "wallet_api")
    paths = {r["Properties"].get("PathPart") for r in of(t, "AWS::ApiGateway::Resource").values()}
    assert not paths & {"gallery", "purchases", "webhooks", "device"}   # ("plan" also names the editor's video plan route)


def methods(t):
    res = of(t, "AWS::ApiGateway::Resource")

    def path(rid):
        r = res[rid]["Properties"]
        parent = r["ParentId"]
        return (path(parent["Ref"]) if "Ref" in parent else "") + "/" + r["PathPart"]
    return {(path(m["Properties"]["ResourceId"]["Ref"]), m["Properties"]["HttpMethod"]): m["Properties"].get("AuthorizationType") for m in of(t, "AWS::ApiGateway::Method").values()
            if "Ref" in m["Properties"]["ResourceId"]}


def test_routes_and_who_may_call_them(synth):
    m = methods(synth(deviceProof="1"))
    for route in (("/users/{user_id}/plan", "GET"), ("/users/{user_id}/purchases/{store}", "POST"), ("/users/{user_id}/device/challenge", "POST"), ("/users/{user_id}/device/verify", "POST")):
        assert m[route] == "COGNITO_USER_POOLS", route
    for route in (("/gallery", "GET"), ("/purchases/webhooks/{store}", "POST")):
        assert m[route] == "NONE", route   # public on purpose: the showcase, and the stores' calls (501 until phase 2 verifies their signature)
    assert ("/users/{user_id}/device/verify", "POST") not in methods(synth())   # the device routes need -c deviceProof=1


def test_the_gallery_function_reads_the_showcase_and_nothing_else(synth):
    t = synth()
    st = statements(t, "gallery_api")
    data = [s for s in st if not all(a.startswith(("logs:", "xray:")) for a in s["actions"])]
    assert all(set(s["actions"]) <= {"s3:GetObject", "s3:ListBucket"} for s in data)
    assert all("showcase/*" in s["resources"] for s in data if "s3:GetObject" in s["actions"])
    assert not any(a.startswith("dynamodb:") for s in st for a in s["actions"])
    e = env(t, "gallery_api")
    assert "PLANS_ENABLED" not in e


def test_production_requires_a_device_proof_by_default_and_qa_does_not(synth):
    assert env(synth(), "wallet_api")["PLANS_REQUIRE_DEVICE_PROOF_DEFAULT"] == "0"
    prod = synth(stage="prod", lambdaMemoryCap="3008")
    assert env(prod, "wallet_api")["PLANS_REQUIRE_DEVICE_PROOF_DEFAULT"] == "1" and env(prod, "VideoGenerationSFLauncher")["PLANS_REQUIRE_DEVICE_PROOF_DEFAULT"] == "1"
    ent = prod["Resources"][table_id(prod, "EntitlementsTable")]
    assert ent["DeletionPolicy"] == "Retain" and ent["Properties"]["PointInTimeRecoverySpecification"]["PointInTimeRecoveryEnabled"] is True


def test_the_deletion_worker_knows_the_entitlements_table(synth):
    t = synth()
    assert table_id(t, "EntitlementsTable") in json.dumps(env(t, "account_deleter")["ENTITLEMENTS_TABLE"])


def test_alarms_on_free_spend_exist_without_actions_and_the_daily_metric_runs(synth):
    t = synth(freeCostAlarmUsd="4", freeCreditsAlarm="20")
    alarms = {a["Properties"]["MetricName"]: a["Properties"] for a in of(t, "AWS::CloudWatch::Alarm").values() if a["Properties"].get("Namespace") == "videomk/Plans"}
    assert alarms["FreeCostEstimatedUsdDay"]["Threshold"] == 4 and alarms["FreeCreditsSpent"]["Threshold"] == 20
    assert all(not a.get("AlarmActions") and not a.get("OKActions") for a in alarms.values())   # no notification topic exists yet
    rules = [r["Properties"] for r in of(t, "AWS::Events::Rule").values() if "20 0 * * ? *" in r["Properties"].get("ScheduleExpression", "")]
    assert len(rules) == 1
    assert can(t, "plans_daily", "dynamodb:Scan", table_id(t, "VideosTable")) and not any(can(t, "plans_daily", a, table_id(t, "VideosTable")) for a in WRITES)


def test_the_knobs_parameter_starts_empty_so_every_default_applies(synth):
    params = [p["Properties"] for p in of(synth(), "AWS::SSM::Parameter").values() if p["Properties"].get("Name") == "/videomk/qa/plans/config"]
    assert len(params) == 1 and params[0]["Value"] == "{}"


def test_plans_stay_frugal_with_cloudformation_resources(synth):
    """The stack is close to CloudFormation's 500 resources: plans may add at most 36, the device routes 12 more, and the whole QA stack must keep room to grow."""
    flags = dict(deckToVideo="1", imageCatalog="1", socialGoogle="1", socialApple="1", intakeEnabled="1")
    off, on, dev = (len(synth(**flags, **x)["Resources"]) for x in ({"plans": "0"}, {}, {"deviceProof": "1"}))
    assert on - off <= 36 and dev - on <= 12 and dev <= 475, (off, on, dev)


def test_every_plans_function_can_be_called_by_the_api(synth):
    t = synth(deviceProof="1")
    for name in ("plans_api", "gallery_api", "device_api"):
        logical = next(k for k, v in of(t, "AWS::Lambda::Function").items() if v["Properties"].get("FunctionName") == name)
        perms = [p["Properties"] for p in of(t, "AWS::Lambda::Permission").values() if logical in json.dumps(p["Properties"]["FunctionName"])]
        assert len(perms) == 1 and perms[0]["Principal"] == "apigateway.amazonaws.com" and "execute-api" in json.dumps(perms[0]["SourceArn"]), name
