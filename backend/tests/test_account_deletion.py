"""Account deletion (docs/ACCOUNT_DELETION.md): every step with fake and moto AWS (no network), idempotency, resume, ownership, the recent sign-in rule, the safety-record rule,
the welcome-credit tombstone and the API handler. The CDK checks are in tests/test_account_deletion_cdk.py."""
import json
import logging
import time

import boto3
import pytest
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from moto import mock_aws

import account_api
import account_deleter
from common import deletion, wallet
from common.deletion import Budget, TimeUp

REGION = "us-west-2"
A, B = "aaaaaaaa-1111-2222-3333-444444444444", "bbbbbbbb-1111-2222-3333-444444444444"
VA1, VA2, VA3 = "11111111-aaaa-4aaa-8aaa-aaaaaaaaaaa1", "11111111-aaaa-4aaa-8aaa-aaaaaaaaaaa2", "11111111-aaaa-4aaa-8aaa-aaaaaaaaaaa3"
VB1 = "22222222-bbbb-4bbb-8bbb-bbbbbbbbbbb1"
ASSETS, MEDIA = "assets-test-bucket", "media-test-bucket"
POOL = "us-west-2_Pool"
NOW = 1_800_000_000


def cerr(code, op="X"):
    return ClientError({"Error": {"Code": code, "Message": "boom"}}, op)


class FakeIdp:
    """Just the Cognito calls the deletion uses; records the order of the calls."""

    def __init__(self):
        self.users, self.calls, self.fail, self.on_delete = {}, [], {}, None

    def add(self, username, sub, email=None, verified="true", identities=None):
        attrs = [{"Name": "sub", "Value": sub}]
        if email:
            attrs += [{"Name": "email", "Value": email}, {"Name": "email_verified", "Value": verified}]
        if identities:
            attrs.append({"Name": "identities", "Value": json.dumps(identities)})
        self.users[username] = {"Username": username, "UserAttributes": attrs, "Attributes": attrs, "Enabled": True}

    def _call(self, name, **kw):
        self.calls.append((name, kw.get("Username")))
        if self.fail.get(name):
            raise self.fail[name]

    def admin_get_user(self, UserPoolId, Username):
        self._call("get", Username=Username)
        if Username not in self.users:
            raise cerr("UserNotFoundException")
        return self.users[Username]

    def list_users(self, UserPoolId, Filter, Limit=60):
        self._call("list")
        sub = Filter.split('"')[1]
        return {"Users": [u for u in self.users.values() if any(a["Name"] == "sub" and a["Value"] == sub for a in u["Attributes"])]}

    def admin_disable_user(self, UserPoolId, Username):
        self._call("disable", Username=Username)
        self.users[Username]["Enabled"] = False

    def admin_user_global_sign_out(self, UserPoolId, Username):
        self._call("signout", Username=Username)

    def admin_delete_user(self, UserPoolId, Username):
        self._call("delete", Username=Username)
        if self.on_delete:
            self.on_delete()
        self.users.pop(Username, None)

    def names(self):
        return [c[0] for c in self.calls]


class FakeVectors:
    def __init__(self):
        self.deleted, self.fail = [], None

    def delete_vectors(self, vectorBucketName, indexName, keys):
        if self.fail:
            raise self.fail
        self.deleted += list(keys)


def table(ddb, name, hash_, range_=None, range_type="S", gsi=None):
    ks = [{"AttributeName": hash_, "KeyType": "HASH"}] + ([{"AttributeName": range_, "KeyType": "RANGE"}] if range_ else [])
    ad = [{"AttributeName": hash_, "AttributeType": "S"}] + ([{"AttributeName": range_, "AttributeType": range_type}] if range_ else [])
    kw = {}
    if gsi:
        ad.append({"AttributeName": "created_at", "AttributeType": "S"})
        kw["GlobalSecondaryIndexes"] = [{"IndexName": "GSI_UserVideos", "KeySchema": [{"AttributeName": "user_id", "KeyType": "HASH"}, {"AttributeName": "created_at", "KeyType": "RANGE"}], "Projection": {"ProjectionType": "ALL"}}]
        if not any(a["AttributeName"] == "user_id" for a in ad):
            ad.append({"AttributeName": "user_id", "AttributeType": "S"})
    ddb.create_table(TableName=name, KeySchema=ks, AttributeDefinitions=ad, BillingMode="PAY_PER_REQUEST", **kw)


@pytest.fixture
def world(monkeypatch):
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name=REGION)
        table(ddb, "Videos", "video_id", gsi=True)
        table(ddb, "Usage", "user_id", "day")
        table(ddb, "Wallet", "user_id", "sk")
        table(ddb, "Flags", "user_id")
        table(ddb, "Media", "user_id", "sk")
        table(ddb, "Safety", "user_id", "ts", "N")
        table(ddb, "Deletion", "pk")
        s3 = boto3.client("s3", region_name=REGION)
        for b in (ASSETS, MEDIA):
            s3.create_bucket(Bucket=b, CreateBucketConfiguration={"LocationConstraint": REGION})
        sqs = boto3.client("sqs", region_name=REGION)
        qurl = sqs.create_queue(QueueName="deletion")["QueueUrl"]
        sf = boto3.client("stepfunctions", region_name=REGION)
        role = "arn:aws:iam::123456789012:role/r"
        d = json.dumps({"StartAt": "W", "States": {"W": {"Type": "Wait", "Seconds": 300, "End": True}}})
        gen = sf.create_state_machine(name="generate_video_workflow_v2", definition=d, roleArn=role)["stateMachineArn"]
        edit = sf.create_state_machine(name="edit_video_workflow_v2", definition=d, roleArn=role)["stateMachineArn"]
        for k, v in dict(VIDEOS_TABLE="Videos", USAGE_TABLE="Usage", WALLET_TABLE="Wallet", FLAGS_TABLE="Flags", MEDIA_TABLE="Media", SAFETY_TABLE="Safety", DELETION_TABLE="Deletion",
                         ASSETS_BUCKET=ASSETS, MEDIA_BUCKET=MEDIA, VECTOR_BUCKET="vec", VECTOR_INDEX="photos", DELETION_QUEUE_URL=qurl, USER_POOL_ID=POOL, GENERATE_STATE_MACHINE_ARNS=gen,
                         EDIT_STATE_MACHINE_ARN=edit, TOMBSTONE_ENABLED="0", TOMBSTONE_DAYS="90", DELETION_SETTLE_SECONDS="3900", APPLE_REVOKE_ENABLED="0").items():
            monkeypatch.setenv(k, v)
        deletion.reset_clients()
        deletion.set_key(b"k" * 32)
        idp, vec = FakeIdp(), FakeVectors()
        deletion.set_client("idp", idp)
        deletion.set_client("vec", vec)
        w = type("World", (), {})()
        w.ddb, w.s3, w.sqs, w.sf, w.idp, w.vec, w.gen, w.edit, w.qurl = ddb, s3, sqs, sf, idp, vec, gen, edit, qurl
        idp.add(A, A, "a@example.com")
        idp.add(B, B, "b@example.com")
        yield w
        deletion.reset_clients()
        deletion.set_key(None)


def seed(w, user, vid, vid2=None, orphan=None):
    """Everything the app can store for one person. Returns the count of rows/objects written (so 'untouched' can be compared)."""
    ddb, s3 = w.ddb, w.s3
    vids = [vid] + ([vid2] if vid2 else [])
    created = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for v in vids:
        ddb.Table("Videos").put_item(Item={"video_id": v, "user_id": user, "created_at": created, "status": "STARTED_PROCESSING", "prompt": "secret prompt"})
        for k in (f"generation/v2/{v}/plan_r1.json", f"generation/assets/{v}/scene_1.png", f"videos/{user}/{v}/final.mp4"):
            s3.put_object(Bucket=ASSETS, Key=k, Body=b"x")
    if orphan:   # a video whose row is gone: only the final file names it
        s3.put_object(Bucket=ASSETS, Key=f"videos/{user}/{orphan}.mp4", Body=b"x")
        s3.put_object(Bucket=ASSETS, Key=f"generation/v2/{orphan}/plan_r1.json", Body=b"x")
    s3.put_object(Bucket=ASSETS, Key=f"uploads/{user}/aaaaaaaaaaaaaaaa.jpg", Body=b"x")
    for k in ("profile.json", "logo.png"):   # the saved watermark settings and logo (docs/WATERMARK.md) go with the account
        s3.put_object(Bucket=ASSETS, Key=f"watermark/{user}/{k}", Body=b"x")
    for m in ("0123456789abcdef", "fedcba9876543210"):
        ddb.Table("Media").put_item(Item={"user_id": user, "sk": f"m#{m}", "st": "ready"})
        ddb.Table("Media").put_item(Item={"user_id": user, "sk": f"h#{m * 4}", "mid": m})
        s3.put_object(Bucket=MEDIA, Key=f"o/{user}/{m}.jpg", Body=b"x")
        s3.put_object(Bucket=MEDIA, Key=f"t/{user}/{m}.jpg", Body=b"x")
    for sk in ("c#0000000000000001", "cm#0000000000000001#x", "prefs", "facets", "stats"):
        ddb.Table("Media").put_item(Item={"user_id": user, "sk": sk})
    ddb.Table("Wallet").put_item(Item={"user_id": user, "sk": "META", "signup_at": 1})
    ddb.Table("Wallet").put_item(Item={"user_id": user, "sk": "B#0000000099#signup#x", "remaining": 5})
    ddb.Table("Wallet").put_item(Item={"user_id": user, "sk": "REF#store-1", "credits": 10})
    for p in deletion.USAGE_PREFIXES:
        ddb.Table("Usage").put_item(Item={"user_id": f"{p}{user}", "day": "2027-01-01", "count": 1})
    ddb.Table("Usage").put_item(Item={"user_id": f"{user}", "day": "2027-01-02", "count": 1})
    ddb.Table("Flags").put_item(Item={"user_id": user, "unlimited": True})
    ddb.Table("Flags").put_item(Item={"user_id": f"safety:{user}", "safety_hold": True})
    ddb.Table("Safety").put_item(Item={"user_id": user, "ts": NOW * 1000, "category": "weapons_drugs", "severity": "standard", "source": "model", "prompt_hash": "ph1", "excerpt": "e" * 160, "ttl": NOW + 50 * 86400})
    ddb.Table("Safety").put_item(Item={"user_id": user, "ts": NOW * 1000 + 5, "category": "malware", "severity": "standard", "source": "fallback", "prompt_hash": "ph2", "excerpt": "short", "ttl": NOW + 10 * 86400})


def snapshot(w, user):
    """What is stored for a person, as plain counts (the same call the admin script prints)."""
    deletion.reset_clients()
    deletion.set_client("idp", w.idp)
    deletion.set_client("vec", w.vec)
    return deletion.inventory(user)


def running(w):
    out = []
    for m in (w.gen, w.edit):
        out += [e["executionArn"].rsplit(":", 1)[1] for e in w.sf.list_executions(stateMachineArn=m, statusFilter="RUNNING")["executions"]]
    return sorted(out)


def start_executions(w, vid_user_pairs):
    for v in vid_user_pairs:
        w.sf.start_execution(stateMachineArn=w.gen, name=v, input="{}")
    w.sf.start_execution(stateMachineArn=w.edit, name=f"{vid_user_pairs[0]}-r2-final-17", input="{}")


def finish(user, now=NOW):
    """Run to the end the way the worker would across messages (no real waiting)."""
    for _ in range(40):
        out = deletion.run(user, now=now, budget=Budget())
        if out.status in ("done", "stuck", "absent"):
            return out
        if out.status == "wait":
            now = now + out.delay
    raise AssertionError("never finished")


# ----------------------------------------------------------------------------- the whole deletion
def test_deletes_everything_of_one_person_and_nothing_of_another(world):
    w = world
    seed(w, A, VA1, VA2, orphan=VA3)
    seed(w, B, VB1)
    start_executions(w, [VA1, VB1])
    before_b = snapshot(w, B)
    assert all(v > 0 for v in snapshot(w, A).values()), snapshot(w, A)

    assert deletion.create_job(A, A, now=NOW)
    out = finish(A)
    assert out.status == "done"
    assert all(v == 0 for v in snapshot(w, A).values()), snapshot(w, A)
    assert snapshot(w, B) == before_b and all(v > 0 for v in before_b.values())
    assert w.s3.list_objects_v2(Bucket=ASSETS, Prefix=f"generation/v2/{VA3}/").get("KeyCount") == 0   # the orphan video's working files went too
    assert running(w) == [VB1]                                                                     # B's workflow still runs; A's generation and edit are stopped
    assert A not in w.idp.users and B in w.idp.users
    assert w.idp.names()[-1] == "delete" and w.idp.names().count("delete") == 1


def test_the_cognito_user_is_deleted_last_after_every_store_is_empty(world):
    w = world
    seed(w, A, VA1)
    seen = {}
    w.idp.on_delete = lambda: seen.update(snapshot(w, A))
    deletion.create_job(A, A, now=NOW)
    assert finish(A).status == "done"
    assert seen and all(v == 0 for v in seen.values())
    assert "signout" in w.idp.names() and w.idp.names().index("signout") < w.idp.names().index("delete")


def test_sign_in_is_disabled_first_and_old_tokens_are_waited_out_before_the_identity_goes(world):
    w = world
    seed(w, A, VA1)
    deletion.create_job(A, A, now=NOW)
    out = deletion.run(A, now=NOW)
    assert out.status == "wait" and out.step == "settle" and 0 < out.delay <= 900
    assert w.idp.users[A]["Enabled"] is False and A in w.idp.users          # cannot sign in any more, still there
    assert all(v == 0 for v in snapshot(w, A).values())                     # the data is already gone
    assert deletion.get_job(A)["status"] == "waiting"
    assert deletion.run(A, now=NOW + 3000).status == "wait"
    assert deletion.run(A, now=NOW + 3901).status == "done" and A not in w.idp.users


def test_a_row_created_while_waiting_is_removed_by_the_final_sweep(world):
    w = world
    seed(w, A, VA1)
    deletion.create_job(A, A, now=NOW)
    assert deletion.run(A, now=NOW).status == "wait"
    w.ddb.Table("Wallet").put_item(Item={"user_id": A, "sk": "META"})                  # a token that was still valid made a call
    w.ddb.Table("Usage").put_item(Item={"user_id": f"libsearch:{A}", "day": "2027-02-01", "count": 1})
    w.ddb.Table("Safety").put_item(Item={"user_id": A, "ts": NOW * 1000 + 99, "category": "malware", "severity": "standard", "excerpt": "late", "ttl": NOW + 86400 * 5})
    assert deletion.run(A, now=NOW + 3901).status == "done"
    assert all(v == 0 for v in snapshot(w, A).values())
    assert len(w.ddb.Table("Safety").query(KeyConditionExpression=Key("user_id").eq(f"deleted:{deletion.account_ref(A)}"))["Items"]) == 3


def test_a_second_run_and_a_second_request_after_completion_do_nothing(world):
    w = world
    seed(w, A, VA1)
    deletion.create_job(A, A, now=NOW)
    assert finish(A).status == "done"
    calls = len(w.idp.calls)
    assert deletion.run(A, now=NOW + 10000).status == "done"
    assert deletion.create_job(A, A) is False
    assert len(w.idp.calls) == calls
    job = deletion.get_job(A)
    assert job["status"] == "done" and int(job["ttl"]) > NOW   # the finished job expires by itself


def test_running_an_unknown_job_is_absent(world):
    assert deletion.run(A).status == "absent"


# ----------------------------------------------------------------------------- failure and resume
def test_a_failing_step_is_logged_retried_and_never_skipped(world, caplog, monkeypatch):
    w = world
    seed(w, A, VA1)
    deletion.create_job(A, A, now=NOW)
    real = deletion.s3()
    calls = {"n": 0}

    class Flaky:
        def __getattr__(self, n):
            return getattr(real, n)

        def delete_objects(self, **kw):
            if kw["Bucket"] == ASSETS:
                calls["n"] += 1
                if calls["n"] == 1:
                    raise cerr("InternalError", "DeleteObjects")
            return real.delete_objects(**kw)

    deletion.set_client("s3", Flaky())
    with caplog.at_level(logging.INFO):
        out = deletion.run(A, now=NOW)
    assert out.status == "retry" and out.step == "videos" and out.delay == 30
    assert "ACCOUNT_DELETION_FAILED" in caplog.text and "step=videos" in caplog.text and "InternalError" in caplog.text
    assert "@" not in caplog.text and "example.com" not in caplog.text
    job = deletion.get_job(A)
    assert job["status"] == "retrying" and "media" in job["steps"] and "videos" not in job["steps"] and job["fails"] == 1
    assert A in w.idp.users and "delete" not in w.idp.names()                      # the identity is untouched until everything else is done
    assert deletion.inventory(A)["videos_rows"] == 1                               # the rows stay until their files are gone, so the next run still finds every video
    assert finish(A).status == "done" and all(v == 0 for v in snapshot(w, A).values())
    assert deletion.get_job(A)["fails"] == 0


def test_a_vector_that_cannot_be_deleted_stops_the_media_step(world):
    w = world
    seed(w, A, VA1)
    w.vec.fail = cerr("ServiceUnavailableException", "DeleteVectors")
    deletion.create_job(A, A, now=NOW)
    out = deletion.run(A, now=NOW)
    assert out.status == "retry" and out.step == "media"
    assert snapshot(w, A)["media_rows"] > 0 and snapshot(w, A)["media_files"] > 0   # nothing was removed ahead of the vectors: no orphan vector can be left without its id
    w.vec.fail = None
    assert finish(A).status == "done"
    assert sorted(w.vec.deleted) == sorted(f"{A}:{m}" for m in ("0123456789abcdef", "fedcba9876543210"))


def test_a_vector_without_a_row_is_still_found_through_its_file(world):
    w = world
    w.s3.put_object(Bucket=MEDIA, Key=f"o/{A}/00000000000000aa.jpg", Body=b"x")
    deletion.create_job(A, A, now=NOW)
    assert finish(A).status == "done"
    assert f"{A}:00000000000000aa" in w.vec.deleted


def test_s3_reporting_an_undeleted_key_is_an_error(world):
    w = world
    seed(w, A, VA1)
    real = deletion.s3()

    class Partial:
        def __getattr__(self, n):
            return getattr(real, n)

        def delete_objects(self, **kw):
            return {"Errors": [{"Key": "k", "Code": "AccessDenied"}]}

    deletion.set_client("s3", Partial())
    deletion.create_job(A, A, now=NOW)
    out = deletion.run(A, now=NOW)
    assert out.status == "retry" and out.step == "media"


def test_cognito_failure_at_the_end_keeps_the_job_resumable_with_the_same_identity(world):
    w = world
    seed(w, A, VA1)
    deletion.create_job(A, A, now=NOW)
    assert deletion.run(A, now=NOW).status == "wait"
    w.idp.fail["delete"] = cerr("TooManyRequestsException", "AdminDeleteUser")
    out = deletion.run(A, now=NOW + 4000)
    assert out.status == "retry" and out.step == "cognito" and A in w.idp.users
    w.idp.fail.clear()
    assert deletion.run(A, now=NOW + 4100).status == "done" and A not in w.idp.users


def test_after_the_limit_the_job_is_stuck_alarmed_and_a_retry_reopens_it(world, caplog):
    w = world
    deletion.create_job(A, A, now=NOW)
    w.idp.fail["disable"] = cerr("InternalErrorException", "AdminDisableUser")
    with caplog.at_level(logging.ERROR):
        for i in range(deletion.MAX_FAILS):
            out = deletion.run(A, now=NOW)
    assert out.status == "stuck" and deletion.get_job(A)["status"] == "stuck"
    assert caplog.text.count("ACCOUNT_DELETION_FAILED") == deletion.MAX_FAILS and "ACCOUNT_DELETION_STUCK" in caplog.text
    assert deletion.run(A, now=NOW).status == "stuck"                              # a stuck job does not spin
    w.idp.fail.clear()
    deletion.reopen(A)
    assert deletion.get_job(A)["fails"] == 0 and finish(A).status == "done"


def test_backoff_grows_and_is_capped():
    assert [deletion.backoff(n) for n in (1, 2, 3, 4, 5, 6, 10)] == [30, 60, 120, 240, 480, 900, 900]


def test_out_of_time_stops_cleanly_and_the_next_message_continues(world):
    w = world
    seed(w, A, VA1)
    deletion.create_job(A, A, now=NOW)
    clock = iter([0.0] + [100.0] * 1000)
    out = deletion.run(A, now=NOW, budget=Budget(10, clock=lambda: next(clock)))
    assert out.status == "continue" and deletion.get_job(A)["status"] == "queued"
    assert finish(A).status == "done" and all(v == 0 for v in snapshot(w, A).values())


def test_budget_raises_when_spent():
    t = [0.0]
    b = Budget(5, clock=lambda: t[0])
    b.check()
    t[0] = 6
    with pytest.raises(TimeUp):
        b.check()


# ----------------------------------------------------------------------------- executions
def test_running_workflows_of_the_person_are_stopped_first_and_others_are_not(world):
    w = world
    seed(w, A, VA1)
    seed(w, B, VB1)
    start_executions(w, [VA1, VB1])
    assert running(w) == sorted([VA1, VB1, f"{VA1}-r2-final-17"])
    deletion.create_job(A, A, now=NOW)
    deletion.run(A, now=NOW)
    assert running(w) == [VB1]


# ----------------------------------------------------------------------------- safety records
def test_safety_records_keep_only_what_the_policy_discloses_under_a_hashed_reference(world):
    w = world
    seed(w, A, VA1)
    w.ddb.Table("Safety").put_item(Item={"user_id": A, "ts": 5, "category": "malware", "severity": "standard", "excerpt": "old", "prompt_hash": "x", "ttl": NOW - 5})   # already expired
    deletion.create_job(A, A, now=NOW)
    deletion.run(A, now=NOW)
    t = w.ddb.Table("Safety")
    assert t.query(KeyConditionExpression=Key("user_id").eq(A))["Items"] == []
    ref = f"deleted:{deletion.account_ref(A)}"
    assert A not in ref and len(ref) == len("deleted:") + 32
    kept = sorted(t.query(KeyConditionExpression=Key("user_id").eq(ref))["Items"], key=lambda r: r["ts"])
    assert len(kept) == 2
    for r in kept:
        assert set(r) == {"user_id", "ts", "category", "severity", "excerpt", "prompt_hash", "ttl"}    # category, time, excerpt, fingerprint, expiry: no source, no sub
        assert len(r["excerpt"]) <= 160
    assert [int(r["ttl"]) for r in kept] == [NOW + 50 * 86400, NOW + 10 * 86400]                       # the original 90-day clock, not restarted
    assert [r["category"] for r in kept] == ["weapons_drugs", "malware"]


def test_the_hashed_reference_is_stable_per_account_and_differs_between_accounts_and_keys(world):
    assert deletion.account_ref(A) == deletion.account_ref(A) != deletion.account_ref(B)
    deletion.set_key(b"z" * 32)
    assert deletion.account_ref(A) != f"{'0' * 32}"
    other = deletion.account_ref(A)
    deletion.set_key(b"k" * 32)
    assert deletion.account_ref(A) != other
    assert deletion.mac("email", "x") != deletion.mac("username", "x")                                   # one value hashes differently for each purpose


# ----------------------------------------------------------------------------- the API
def event(user=A, path_user=None, body='{"confirm": "DELETE"}', auth_time="now", res="/users/{user_id}/account/delete", username=A):
    claims = {"sub": user, "cognito:username": username}
    if auth_time == "now":
        claims["auth_time"] = str(int(time.time()) - 30)
    elif auth_time is not None:
        claims["auth_time"] = str(auth_time)
    return {"httpMethod": "POST", "resource": res, "pathParameters": {"user_id": path_user or user}, "body": body, "requestContext": {"authorizer": {"claims": claims}}}


def call(ev):
    r = account_api.handler(ev, None)
    return r["statusCode"], json.loads(r["body"])


def test_delete_with_a_fresh_sign_in_starts_the_job_and_queues_one_message(world):
    w = world
    code, body = call(event())
    assert code == 202 and body["status"] == "deleting" and body["apple"] == "not_linked"
    job = deletion.get_job(A)
    assert job["status"] == "queued" and job["username"] == A
    msgs = w.sqs.receive_message(QueueUrl=w.qurl, MaxNumberOfMessages=10).get("Messages", [])
    assert [json.loads(m["Body"]) for m in msgs] == [{"user_id": A}]


def test_an_old_sign_in_is_refused_with_reauth_required_and_nothing_is_created(world):
    for at in (int(time.time()) - 601, int(time.time()) - 86400, None, "garbage", int(time.time()) + 3600):
        code, body = call(event(auth_time=at))
        assert code == 401 and body["code"] == "reauth_required" and body["max_age_seconds"] == 600, at
    assert deletion.get_job(A) is None
    assert world.sqs.receive_message(QueueUrl=world.qurl).get("Messages") is None


def test_the_recent_sign_in_window_edges():
    n = 1_000_000
    assert deletion.recent_auth(n - 600, now=n) and not deletion.recent_auth(n - 601, now=n)
    assert deletion.recent_auth(n + 30, now=n) and not deletion.recent_auth(n + 61, now=n)
    assert not any(deletion.recent_auth(x, now=n) for x in (None, "", "x", [], {}))


def test_a_repeat_call_is_harmless_even_with_an_old_token_and_after_completion(world):
    w = world
    assert call(event())[0] == 202
    assert call(event(auth_time=None))[0] == 202                                    # already deleting: not a new request, no re-sign-in needed
    msgs = w.sqs.receive_message(QueueUrl=w.qurl, MaxNumberOfMessages=10).get("Messages", [])
    assert len(msgs) == 1                                                           # no message storm
    assert finish(A).status == "done"
    code, body = call(event(auth_time=None))
    assert code == 202 and body["status"] == "deleting"


def test_a_stuck_job_is_reopened_by_calling_again(world):
    deletion.create_job(A, A)
    deletion._update(A, "SET #s = :s, fails = :f", {"#s": "status"}, {":s": "stuck", ":f": 30})
    assert call(event(auth_time=None))[0] == 202
    assert deletion.get_job(A)["status"] == "queued" and deletion.get_job(A)["fails"] == 0


def test_a_lost_first_message_is_sent_again_after_ten_minutes(world):
    w = world
    deletion.create_job(A, A, now=int(time.time()) - 700)
    assert call(event(auth_time=None))[0] == 202
    assert len(w.sqs.receive_message(QueueUrl=w.qurl, MaxNumberOfMessages=10).get("Messages", [])) == 1


def test_a_user_can_never_delete_or_even_touch_another_users_account(world):
    w = world
    seed(w, A, VA1)
    code, _ = call(event(user=B, path_user=A))                                      # B's token, A's path
    assert code == 403
    assert deletion.get_job(A) is None and deletion.get_job(B) is None
    assert all(v > 0 for v in snapshot(w, A).values())
    assert call(event(user=A, path_user=B))[0] == 403
    r = account_api.handler({"httpMethod": "POST", "resource": "/users/{user_id}/account/delete", "pathParameters": {"user_id": A}, "body": '{"confirm":"DELETE"}', "requestContext": {}}, None)
    assert r["statusCode"] == 401                                                   # no verified identity at all
    r = account_api.handler(event(path_user=A) | {"pathParameters": {}}, None)
    assert r["statusCode"] == 403
    assert w.sqs.receive_message(QueueUrl=w.qurl).get("Messages") is None


def test_the_worker_acts_only_on_the_id_in_its_message_and_that_id_is_the_token_sub(world):
    w = world
    seed(w, A, VA1)
    seed(w, B, VB1)
    assert call(event(user=A))[0] == 202
    msg = w.sqs.receive_message(QueueUrl=w.qurl)["Messages"][0]
    ev = {"Records": [{"messageId": "1", "body": msg["Body"]}]}
    class Ctx:
        def get_remaining_time_in_millis(self): return 600000
    account_deleter.handler(ev, Ctx())
    assert all(v == 0 for v in snapshot(w, A).values()) and all(v > 0 for v in snapshot(w, B).values())


@pytest.mark.parametrize("body", ['{"confirm": "delete"}', '{"confirm": true}', "{}", "[]", "not json", '{"confirm": "DELETE "}'])
def test_the_confirmation_word_is_required(world, body):
    code, _ = call(event(body=body))
    assert code == 400 and deletion.get_job(A) is None


def test_bad_worker_messages_go_back_for_the_dead_letter_queue(world):
    class Ctx:
        def get_remaining_time_in_millis(self): return 600000
    out = account_deleter.handler({"Records": [{"messageId": "m1", "body": json.dumps({"user_id": "../../x"})}, {"messageId": "m2", "body": "oops"}]}, Ctx())
    assert [f["itemIdentifier"] for f in out["batchItemFailures"]] == ["m1", "m2"]


def test_the_worker_requeues_itself_with_the_delay_and_stops_when_done(world):
    w = world
    seed(w, A, VA1)
    deletion.create_job(A, A, now=int(time.time()))
    out = account_deleter.handle_one(A, 600)
    assert out.status == "wait"
    msgs = w.sqs.receive_message(QueueUrl=w.qurl, MaxNumberOfMessages=10, WaitTimeSeconds=0).get("Messages", [])
    assert msgs == []                                                              # delayed: not visible yet (SQS DelaySeconds)
    attrs = w.sqs.get_queue_attributes(QueueUrl=w.qurl, AttributeNames=["ApproximateNumberOfMessagesDelayed"])["Attributes"]
    assert attrs["ApproximateNumberOfMessagesDelayed"] == "1"


def test_account_api_reports_the_apple_grant_state(world):
    w = world
    apple = [{"providerName": "SignInWithApple", "userId": "001234.abcd.0001", "providerType": "SignInWithApple", "primary": "false"}]
    w.idp.add("SignInWithApple_001234.abcd.0001", B, "b@example.com", identities=apple)
    w.idp.users.pop(B, None)
    code, body = call(event(user=B, username="SignInWithApple_001234.abcd.0001"))
    assert code == 202 and body["apple"] == "revoke_off"                            # linked, feature switched off
    w.idp.fail["get"] = cerr("InternalErrorException")
    w.idp.fail["list"] = cerr("InternalErrorException")
    code, body = call(event(user=B, username="SignInWithApple_001234.abcd.0001"))
    assert code == 202 and body["apple"] == "unknown"                               # a lookup problem never blocks the deletion


# ----------------------------------------------------------------------------- the welcome credit
def new_user(w, sub, email, username=None, verified="true"):
    w.idp.add(username or sub, sub, email, verified)


def test_an_account_being_deleted_gets_no_welcome_credit_and_no_rows(world):
    w = world
    deletion.create_job(A, A)
    wallet.ensure_grants(A, now=NOW)
    assert w.ddb.Table("Wallet").query(KeyConditionExpression=Key("user_id").eq(A))["Items"] == []
    wallet.ensure_grants(B, now=NOW)
    assert wallet.balance(B, now=NOW)["balance"] == 5                               # everybody else is unchanged


def test_no_tombstone_by_default_so_a_returning_email_gets_the_welcome_credit(world):
    w = world
    wallet.ensure_grants(A, now=NOW)
    deletion.create_job(A, A, now=NOW)
    finish(A)
    assert w.ddb.Table("Deletion").scan()["Items"][0]["pk"].startswith("job#")      # only the job: no email hash anywhere
    assert not [i for i in w.ddb.Table("Deletion").scan()["Items"] if i["pk"].startswith("tomb#")]
    new_user(w, "cccccccc-1111-2222-3333-444444444444", "a@example.com")
    assert wallet.balance("cccccccc-1111-2222-3333-444444444444", now=NOW)["balance"] == 5


@pytest.fixture
def tomb(world, monkeypatch):
    monkeypatch.setenv("TOMBSTONE_ENABLED", "1")
    return world


def delete_account(w, sub, now=NOW):
    deletion.create_job(sub, sub, now=now)
    assert finish(sub, now).status == "done"


C = "cccccccc-1111-2222-3333-444444444444"


def test_with_the_tombstone_on_a_returning_verified_email_gets_no_second_welcome_credit(tomb):
    w = tomb
    w.idp.add(A, A, "Some.One+promo@Example.com")
    delete_account(w, A)
    tombs = [i for i in w.ddb.Table("Deletion").scan()["Items"] if i["pk"].startswith("tomb#")]
    assert len(tombs) == 1 and "example" not in json.dumps(tombs, default=int) and "@" not in json.dumps(tombs, default=int)
    assert int(tombs[0]["expires_at"]) == NOW + 3901 + 90 * 86400 - 1 or NOW + 90 * 86400 <= int(tombs[0]["expires_at"]) <= NOW + 91 * 86400
    new_user(w, C, "some.one@example.com")                                          # another spelling of the same mailbox
    wallet.ensure_grants(C, now=NOW + 5000)
    meta = w.ddb.Table("Wallet").get_item(Key={"user_id": C, "sk": "META"})["Item"]
    assert meta["signup_denied"] == "returning"
    assert wallet.balance(C, now=NOW + 5000)["balance"] == 0
    assert wallet.balance(C, now=NOW + 5000 + 86400)["balance"] == 1                # the free daily credit still works: the person is not blocked, only the one-time grant is withheld


def test_gmail_dots_and_tags_are_one_mailbox_and_other_people_are_not_affected(tomb):
    w = tomb
    w.idp.add(A, A, "john.smith@gmail.com")
    delete_account(w, A)
    new_user(w, C, "johnsmith+x@googlemail.com")
    assert wallet.balance(C, now=NOW + 5000)["balance"] == 0
    D = "dddddddd-1111-2222-3333-444444444444"
    new_user(w, D, "john.smith2@gmail.com")
    assert wallet.balance(D, now=NOW + 5000)["balance"] == 5


def test_an_unverified_email_is_never_stored_or_matched(tomb):
    w = tomb
    w.idp.add(A, A, "x@example.com", verified="false")
    delete_account(w, A)
    assert not [i for i in w.ddb.Table("Deletion").scan()["Items"] if i["pk"].startswith("tomb#")]
    new_user(w, C, "x@example.com")
    assert wallet.balance(C, now=NOW + 5000)["balance"] == 5


def test_a_federated_username_is_matched_even_with_another_email(tomb):
    w = tomb
    w.idp.users.pop(A)
    w.idp.add("Google_1234567890", A, "g@example.com", verified="false")
    delete_account(w, A)
    tombs = [i["pk"] for i in w.ddb.Table("Deletion").scan()["Items"] if i["pk"].startswith("tomb#")]
    assert len(tombs) == 1 and tombs[0].startswith("tomb#u#")
    w.idp.add("Google_1234567890", C, "other@example.com", verified="false")
    assert wallet.balance(C, now=NOW + 5000)["balance"] == 0


def test_the_tombstone_expires_after_its_bounded_period(tomb, monkeypatch):
    w = tomb
    monkeypatch.setenv("TOMBSTONE_DAYS", "30")
    w.idp.add(A, A, "e@example.com")
    delete_account(w, A)
    t = [i for i in w.ddb.Table("Deletion").scan()["Items"] if i["pk"].startswith("tomb#")][0]
    assert NOW + 30 * 86400 <= int(t["expires_at"]) <= NOW + 31 * 86400 and int(t["ttl"]) == int(t["expires_at"])
    new_user(w, C, "e@example.com")
    assert wallet.balance(C, now=NOW + 31 * 86400 + 10000)["balance"] >= 5           # after the period the welcome credit works again (the check uses expires_at, not the lagging DynamoDB TTL)


def test_a_failed_lookup_fails_closed_and_the_wallet_call_can_be_retried(tomb):
    w = tomb
    new_user(w, C, "q@example.com")
    w.idp.fail["list"] = cerr("InternalErrorException")
    with pytest.raises(ClientError):
        wallet.balance(C, now=NOW)
    assert w.ddb.Table("Wallet").query(KeyConditionExpression=Key("user_id").eq(C))["Items"] == []   # nothing half-written
    w.idp.fail.clear()
    assert wallet.balance(C, now=NOW)["balance"] == 5


def test_the_tombstone_switch_off_makes_no_cognito_lookup_in_the_wallet(world):
    w = world
    new_user(w, C, "q@example.com")
    wallet.balance(C, now=NOW)
    assert w.idp.calls == []


def test_the_tombstone_holds_hashes_only_never_the_sub_or_email(tomb):
    w = tomb
    w.idp.add(A, A, "h@example.com")
    delete_account(w, A)
    blob = json.dumps(w.ddb.Table("Deletion").scan()["Items"], default=int)
    assert "h@example.com" not in blob
    tomb_rows = [i for i in w.ddb.Table("Deletion").scan()["Items"] if i["pk"].startswith("tomb#")]
    assert A not in json.dumps(tomb_rows, default=int)


def test_logs_never_carry_an_address(tomb, caplog):
    w = tomb
    w.idp.add(A, A, "private.person@example.com")
    with caplog.at_level(logging.DEBUG):
        call(event())
        delete_account(w, A)
    assert "private" not in caplog.text and "example.com" not in caplog.text


def test_the_wait_for_old_tokens_starts_when_sign_in_is_switched_off_not_when_it_was_requested(world):
    w = world
    deletion.create_job(A, A, now=NOW)
    w.idp.fail["disable"] = cerr("InternalErrorException", "AdminDisableUser")
    assert deletion.run(A, now=NOW).status == "retry"
    w.idp.fail.clear()
    assert deletion.run(A, now=NOW + 7200).status == "wait"                         # the disable only worked two hours later: tokens issued until then live another hour
    assert deletion.get_job(A)["settle_at"] == NOW + 7200 + 3900
