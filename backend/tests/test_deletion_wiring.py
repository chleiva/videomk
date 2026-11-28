"""Account and video deletion also remove the share previews (objects in the share bucket + CDN invalidation) and the video-upload data (`vidrec:`/`vidhash:`/`vidup:` rows and the
user's prefixes in the vidup bucket). moto/fake AWS, no network. Behaviour: idempotent, one person only, a failure is retried and never skipped. CDK: names-only wiring behind context
flags, least privilege, no new resource in the main stack (docs/SHARE_PREVIEWS_2026-11-28.md, docs/VIDEO_UPLOAD_2026-11-28.md)."""
import json
import os
import sys

import boto3
import pytest

import video_retry
from common import deletion, share_revoke
from share import share_api, share_page
from tests.test_account_deletion import A, B, ASSETS, REGION, VA1, VB1, finish, seed, snapshot, world  # noqa: F401  (world is the fixture)
from tests.test_hardening import _event  # noqa: F401

SHARE, VIDUP = "share-test-bucket", "vidup-test-bucket"


class Cloudfront:
    def __init__(self):
        self.calls, self.fail = [], False

    def create_invalidation(self, **kw):
        if self.fail:
            raise RuntimeError("cloudfront down")
        self.calls.append(kw)


@pytest.fixture
def both(world, monkeypatch):  # noqa: F811
    w = world
    for b in (SHARE, VIDUP):
        w.s3.create_bucket(Bucket=b, CreateBucketConfiguration={"LocationConstraint": REGION})
    monkeypatch.setenv("SHARE_BUCKET", SHARE)
    monkeypatch.setenv("DISTRIBUTION_ID", "EDIST")
    monkeypatch.setenv("VIDUP_BUCKET", VIDUP)
    cf = Cloudfront()
    real = boto3.client

    def client(name, *a, **k):
        return cf if name == "cloudfront" else real(name, *a, **k)
    monkeypatch.setattr(share_api.boto3, "client", client)
    w.cf = cf
    return w


def share_video(w, user, vid, token=None):
    token = token or share_page.new_token()
    for n in share_page.FILES:
        w.s3.put_object(Bucket=SHARE, Key=f"{token}/{n}", Body=b"x")
    w.ddb.Table("Videos").update_item(Key={"video_id": vid}, UpdateExpression="SET share_token = :t", ExpressionAttributeValues={":t": token})
    return token


def keys(w, bucket):
    return sorted(o["Key"] for o in w.s3.list_objects_v2(Bucket=bucket).get("Contents", []))


def seed_vidup(w, user, cid="c1"):
    for k in (f"in/{user}/{cid}", f"clips/{user}/{cid}/mezz.mp4", f"clips/{user}/{cid}/audio.m4a", f"clips/{user}/{cid}/thumb.jpg"):
        w.s3.put_object(Bucket=VIDUP, Key=k, Body=b"x")
    for p in ("vidrec:", "vidhash:", "vidup:"):
        w.ddb.Table("Usage").put_item(Item={"user_id": f"{p}{user}", "day": cid, "ttl": 1})


# ------------------------------------------------------------------ account deletion: share previews
def test_account_deletion_takes_back_every_shared_link_and_invalidates_the_cdn(both):
    w = both
    seed(w, A, VA1, "11111111-aaaa-4aaa-8aaa-aaaaaaaaaaa2")
    seed(w, B, VB1)
    ta, tb = share_video(w, A, VA1), share_video(w, B, VB1)
    deletion.create_job(A, A, now=1_800_000_000)
    assert finish(A).status == "done"
    assert keys(w, SHARE) == sorted(f"{tb}/{n}" for n in share_page.FILES)                  # A's four files are gone, B's untouched
    assert [c["InvalidationBatch"]["Paths"]["Items"] for c in w.cf.calls] == [[f"/{ta}", f"/{ta}/*"]]
    assert all(v == 0 for v in snapshot(w, A).values())


def test_a_failed_share_delete_keeps_the_rows_is_retried_and_finishes(both, caplog):
    w = both
    seed(w, A, VA1)
    t = share_video(w, A, VA1)
    real = deletion.s3()
    fail = {"on": True}

    class Flaky:
        def __getattr__(self, n):
            return getattr(real, n)

        def delete_objects(self, **kw):
            if kw["Bucket"] == SHARE and fail["on"]:
                return {"Errors": [{"Key": f"{t}/index.html", "Code": "AccessDenied"}]}
            return real.delete_objects(**kw)
    deletion.set_client("s3", Flaky())
    deletion.create_job(A, A, now=1_800_000_000)
    out = deletion.run(A, now=1_800_000_000)
    assert out.status == "retry" and out.step == "videos"                                    # the existing retry pattern (backoff, stuck + alarm, SQS dead-letter)
    assert "SHARE_REVOKE_FAILED" in caplog.text and deletion.inventory(A)["videos_rows"] == 1   # the row, which holds the token, is still there
    fail["on"] = False
    assert finish(A).status == "done" and keys(w, SHARE) == []


def test_a_failed_invalidation_is_also_retried(both):
    w = both
    seed(w, A, VA1)
    share_video(w, A, VA1)
    w.cf.fail = True
    deletion.create_job(A, A, now=1_800_000_000)
    assert deletion.run(A, now=1_800_000_000).status == "retry"
    w.cf.fail = False
    assert finish(A).status == "done" and len(w.cf.calls) == 1


def test_without_the_share_stack_nothing_is_called(world, monkeypatch):
    monkeypatch.delenv("SHARE_BUCKET", raising=False)
    seed(world, A, VA1)
    world.ddb.Table("Videos").update_item(Key={"video_id": VA1}, UpdateExpression="SET share_token = :t", ExpressionAttributeValues={":t": share_page.new_token()})
    deletion.create_job(A, A, now=1_800_000_000)
    assert finish(A).status == "done"


# ------------------------------------------------------------------ account deletion: video upload
def test_account_deletion_removes_vidup_rows_and_only_this_users_prefixes(both):
    w = both
    seed(w, A, VA1)
    seed(w, B, VB1)
    seed_vidup(w, A)
    seed_vidup(w, B)
    w.ddb.Table("Usage").put_item(Item={"user_id": "vidup:global", "day": "2027-01-01", "micros": 5})
    w.ddb.Table("Usage").put_item(Item={"user_id": "vidbad", "day": "a" * 64, "code": "x"})
    deletion.create_job(A, A, now=1_800_000_000)
    assert finish(A).status == "done"
    assert keys(w, VIDUP) == sorted([f"in/{B}/c1", f"clips/{B}/c1/mezz.mp4", f"clips/{B}/c1/audio.m4a", f"clips/{B}/c1/thumb.jpg"])
    usage = w.ddb.Table("Usage")
    assert all("Item" not in usage.get_item(Key={"user_id": f"{p}{A}", "day": "c1"}) for p in ("vidrec:", "vidhash:", "vidup:"))
    assert all("Item" in usage.get_item(Key={"user_id": f"{p}{B}", "day": "c1"}) for p in ("vidrec:", "vidhash:", "vidup:"))
    assert "Item" in usage.get_item(Key={"user_id": "vidup:global", "day": "2027-01-01"}) and "Item" in usage.get_item(Key={"user_id": "vidbad", "day": "a" * 64})


def test_step_vidup_is_idempotent_resumable_and_skipped_when_the_feature_is_off(both, monkeypatch):
    w = both
    seed_vidup(w, A)
    assert deletion.inventory(A)["vidup_files"] == 4
    assert deletion.step_vidup(A, deletion.Budget()) == {"files": 4}
    assert deletion.step_vidup(A, deletion.Budget()) == {"files": 0}                           # again: nothing left, no error
    monkeypatch.delenv("VIDUP_BUCKET")
    assert deletion.step_vidup(A, deletion.Budget()) == {"skipped": 1} and "vidup_files" not in deletion.inventory(A)


def test_a_clip_written_after_the_first_pass_is_removed_by_the_recheck(both):
    w = both
    seed(w, A, VA1)
    deletion.create_job(A, A, now=1_800_000_000)
    first = deletion.run(A, now=1_800_000_000, budget=deletion.Budget())
    assert first.status in ("wait", "continue", "retry", "done")
    seed_vidup(w, A, "late")   # an analysis that finished after the data steps
    assert finish(A).status == "done" and keys(w, VIDUP) == []


# ------------------------------------------------------------------ video deletion
def _delete_event(user, vid):
    ev = _event(user=user)
    ev["pathParameters"] = {"user_id": user, "video_id": vid}
    ev["httpMethod"] = "DELETE"
    return ev


def test_deleting_a_video_takes_its_share_back_and_a_failure_keeps_the_video(both, monkeypatch):
    w = both
    for k, v in (("VIDEOS_TABLE", "Videos"), ("ASSETS_BUCKET", ASSETS)):
        monkeypatch.setenv(k, v)
    seed(w, A, VA1)
    w.ddb.Table("Videos").update_item(Key={"video_id": VA1}, UpdateExpression="SET #s = :c", ExpressionAttributeNames={"#s": "status"}, ExpressionAttributeValues={":c": "FAILED"})
    t = share_video(w, A, VA1)
    w.cf.fail = True
    r = video_retry.delete_handler(_delete_event(A, VA1), None)
    assert r["statusCode"] == 503 and json.loads(r["body"])["code"] == "share_revoke_failed"
    assert "Item" in w.ddb.Table("Videos").get_item(Key={"video_id": VA1})                      # still there: the same DELETE can be repeated
    w.cf.fail = False
    r = video_retry.delete_handler(_delete_event(A, VA1), None)
    assert r["statusCode"] == 200 and keys(w, SHARE) == [] and "Item" not in w.ddb.Table("Videos").get_item(Key={"video_id": VA1})
    assert w.cf.calls[-1]["InvalidationBatch"]["Paths"]["Items"] == [f"/{t}", f"/{t}/*"]
    assert video_retry.delete_handler(_delete_event(A, VA1), None)["statusCode"] == 404          # idempotent


def test_revoke_item_strict_raises_and_default_swallows(monkeypatch):
    monkeypatch.setenv("SHARE_BUCKET", SHARE)

    class Boom:
        def delete_objects(self, **kw):
            raise RuntimeError("down")
    tok = share_page.new_token()
    assert share_revoke.revoke_item({"share_token": tok}, s3=Boom()) is False
    with pytest.raises(RuntimeError):
        share_revoke.revoke_item({"share_token": tok}, s3=Boom(), strict=True)


# ------------------------------------------------------------------ CDK: names only, behind flags, least privilege, no new resource
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(scope="module")
def tpl():
    import aws_cdk as cdk
    from aws_cdk.assertions import Template
    sys.path.insert(0, ROOT)
    sys.path.insert(0, os.path.join(ROOT, "lambdas"))
    cwd = os.getcwd()
    os.chdir(ROOT)
    os.environ.setdefault("CDK_SKIP_LAYER_CHECK", "1")
    try:
        from backend_stack import BackendStack
        out = {}
        for name, ctx in (("off", {}), ("on", {"shareBucket": "videomk-share-b", "shareDistributionId": "E123ABC", "videoUpload": "1"})):
            app = cdk.App(context={"stage": "qa", "engine": "v2", **ctx}, outdir=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"vmk-wire-{name}"))
            st = BackendStack(app, "videomk-qa", stage="qa", stage_cfg={"account": "123456789012", "region": "eu-west-1", "domain": None, "callbackUrls": ["https://qa.videomk.com/auth/callback"]},
                              env=cdk.Environment(account="123456789012", region="eu-west-1"))
            out[name] = Template.from_stack(st).to_json()
        yield out
    finally:
        os.chdir(cwd)


def _fn(t, name):
    (k, v), = [(k, v) for k, v in t["Resources"].items() if v["Type"] == "AWS::Lambda::Function" and v["Properties"].get("FunctionName") == name]
    return k, v


def _stmts(t, fname):
    role = _fn(t, fname)[1]["Properties"]["Role"]["Fn::GetAtt"][0]
    return [s for p in t["Resources"].values() if p["Type"] == "AWS::IAM::Policy" and {"Ref": role} in p["Properties"]["Roles"] for s in p["Properties"]["PolicyDocument"]["Statement"]]


def _flat(x):
    return x if isinstance(x, list) else [x]


def test_the_main_stack_gains_no_resource(tpl):
    assert sorted(tpl["off"]["Resources"]) == sorted(tpl["on"]["Resources"])
    assert len(tpl["on"]["Resources"]) <= 500


def test_off_means_no_variable_and_no_statement(tpl):
    for fname in ("VideoGenerationSFLauncher", "account_deleter"):
        try:
            _, f = _fn(tpl["off"], fname)
        except ValueError:
            continue
        v = f["Properties"]["Environment"]["Variables"]
        assert "SHARE_BUCKET" not in v and "DISTRIBUTION_ID" not in v
    assert "videomk-share-b" not in json.dumps(tpl["off"]) and "E123ABC" not in json.dumps(tpl["off"])


def test_on_the_launcher_and_the_worker_may_only_delete_in_the_share_bucket_and_invalidate_one_distribution(tpl):
    t = tpl["on"]
    workers = [k for k, v in t["Resources"].items() if v["Type"] == "AWS::Lambda::Function" and v["Properties"].get("Handler") == "account_deleter.handler"]
    launchers = [_fn(t, "VideoGenerationSFLauncher")[0]]
    assert len(workers) == 1
    for lid in workers + launchers:
        f = t["Resources"][lid]
        v = f["Properties"]["Environment"]["Variables"]
        assert v["SHARE_BUCKET"] == "videomk-share-b" and v["DISTRIBUTION_ID"] == "E123ABC"
        role = f["Properties"]["Role"]["Fn::GetAtt"][0]
        st = [s for p in t["Resources"].values() if p["Type"] == "AWS::IAM::Policy" and {"Ref": role} in p["Properties"]["Roles"] for s in p["Properties"]["PolicyDocument"]["Statement"]]
        share = [s for s in st if "videomk-share-b" in json.dumps(s["Resource"])]
        assert share == [{"Action": "s3:DeleteObject", "Effect": "Allow", "Resource": "arn:aws:s3:::videomk-share-b/*"}]
        cf = [s for s in st if "cloudfront:CreateInvalidation" in _flat(s["Action"])]
        assert len(cf) == 1 and json.dumps(cf[0]["Resource"]).count("E123ABC") == 1 and "*" not in json.dumps(cf[0]["Resource"]).replace("/*", "").replace("distribution/E123ABC", "")


def test_on_the_worker_reaches_only_the_in_and_clips_prefixes_of_the_vidup_bucket(tpl):
    t = tpl["on"]
    (wid,) = [k for k, v in t["Resources"].items() if v["Type"] == "AWS::Lambda::Function" and v["Properties"].get("Handler") == "account_deleter.handler"]
    f = t["Resources"][wid]
    assert f["Properties"]["Environment"]["Variables"]["VIDUP_BUCKET"] == "videomk-qa-vidup-123456789012"
    role = f["Properties"]["Role"]["Fn::GetAtt"][0]
    st = [s for p in t["Resources"].values() if p["Type"] == "AWS::IAM::Policy" and {"Ref": role} in p["Properties"]["Roles"] for s in p["Properties"]["PolicyDocument"]["Statement"]]
    mine = [s for s in st if "videomk-qa-vidup-123456789012" in json.dumps(s["Resource"])]
    acts = sorted(a for s in mine for a in _flat(s["Action"]))
    assert acts == ["s3:DeleteObject", "s3:ListBucket"]
    dele = [s for s in mine if s["Action"] == "s3:DeleteObject"][0]
    assert sorted(_flat(dele["Resource"])) == ["arn:aws:s3:::videomk-qa-vidup-123456789012/clips/*", "arn:aws:s3:::videomk-qa-vidup-123456789012/in/*"]
    lst = [s for s in mine if s["Action"] == "s3:ListBucket"][0]
    assert lst["Condition"] == {"StringLike": {"s3:prefix": ["in/*", "clips/*"]}}


def test_only_one_of_the_two_share_flags_is_refused():
    import aws_cdk as cdk
    cwd = os.getcwd()
    os.chdir(ROOT)
    os.environ.setdefault("CDK_SKIP_LAYER_CHECK", "1")
    try:
        from backend_stack import BackendStack
        app = cdk.App(context={"stage": "qa", "engine": "v2", "shareBucket": "x"}, outdir=os.path.join(os.environ.get("TMPDIR", "/tmp"), "vmk-wire-bad"))
        with pytest.raises(ValueError, match="both"):
            BackendStack(app, "videomk-qa", stage="qa", stage_cfg={"account": "123456789012", "region": "eu-west-1", "domain": None, "callbackUrls": ["https://qa.videomk.com/auth/callback"]},
                         env=cdk.Environment(account="123456789012", region="eu-west-1"))
    finally:
        os.chdir(cwd)
