"""The owner console's functions (backend/admin_console/lambdas; docs/ADMIN_CONSOLE_DESIGN_2026-11-28.md): the rollup maths on fixtures, frozen days that survive
an account deletion, the alerts, the two switches with their step-up check and audit entries, the sign-in hook, the read answer, and the static page's rules.
The stack (who may do what, the authorizer, the headers) is in tests/test_admin_cdk.py; the customer side of the switches in tests/test_ops_switches.py."""
import datetime
import json
import os
import re
import sys
import time

import boto3
import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "admin_console", "lambdas"))
sys.path.insert(0, ROOT)

import admin_act  # noqa: E402
import admin_auth_event  # noqa: E402
import admin_common as c  # noqa: E402
import admin_read  # noqa: E402
import admin_rollup as r  # noqa: E402
from common import ops_switches, plans  # noqa: E402

NOW = 1_800_000_000.0 + 6 * 3600           # 2027-01-15 14:00:00 UTC
TODAY, YESTERDAY = "2027-01-15", "2027-01-14"
ANA, BEN, STAFF = "11111111-aaaa-bbbb-cccc-000000000001", "11111111-aaaa-bbbb-cccc-000000000002", "11111111-aaaa-bbbb-cccc-000000000009"
SECRET_PROMPT = "A birthday video for my daughter Lucia with her medical story"
SITE = os.path.join(ROOT, "admin_console", "site")


def video(vid, day, hhmm, status, user=ANA, plan="free", cost=None, **extra):
    item = {"video_id": vid, "usage_day": day, "created_at": f"{day}T{hhmm}:00Z", "status": status, "user_id": user, "plan": plan, "prompt": SECRET_PROMPT, "title": "Lucia turns 6",
            "request_json": json.dumps({"options": {"brief": SECRET_PROMPT}}), "credits_charged": 1, **extra}
    if cost is not None:
        item["cost_usd"] = c.dec(float(cost))
    return item


FIXTURE = [
    video("v-ok-1", TODAY, "09:00", "COMPLETE", cost=0.10, c_script=c.dec(0.06), c_speech=c.dec(0.04), duration_s=28, aspect="9:16", resolution="1080p", free_credits=1),
    video("v-ok-2", TODAY, "10:00", "COMPLETE", user=BEN, plan="pro", cost=0.30, duration_s=170, credits_charged=3),
    video("v-ok-3", TODAY, "13:30", "COMPLETE", user=BEN, plan="pro", cost=0.20, duration_s=60),
    video("v-bad-1", TODAY, "13:40", "FAILED", cost=0.05, failure_code="ReadTimeoutError"),
    video("v-bad-2", TODAY, "13:45", "FAILED", user=BEN, plan="pro", failure_code="AccessDenied: arn:aws:secret/" + SECRET_PROMPT),
    video("v-stop", TODAY, "11:00", "CANCELLED", cost=0.03),
    video("v-no", TODAY, "11:30", "REJECTED", cost=0.01),
    video("v-run", TODAY, "13:58", "RENDERING", user=BEN, plan="pro"),
    video("v-staff", TODAY, "12:00", "COMPLETE", user=STAFF, plan="test", cost=1.00),
    video("v-y-1", YESTERDAY, "08:00", "COMPLETE", cost=0.12),
    video("v-y-2", YESTERDAY, "09:00", "FAILED", user=BEN, plan="pro", cost=0.02, failure_code="ValueError"),
]
RUNS = {"v-ok-1": 100.0, "v-ok-2": 200.0, "v-ok-3": 400.0, "v-staff": 50.0, "v-y-1": 130.0, "v-ok-1-r1": 999.0}


@pytest.fixture
def world(aws, monkeypatch):
    """The main stack's tables as moto has them, plus the console's own table, bucket and settings. Calls that have no moto stand-in are replaced by fixed answers."""
    c.reset_clients()
    ops_switches._table = None
    ops_switches.set_state(None)
    aws.create_table(TableName="Rollups", KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
                     AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
    s3 = boto3.client("s3", region_name="us-west-2")
    s3.create_bucket(Bucket="audit-bucket", CreateBucketConfiguration={"LocationConstraint": "us-west-2"})
    for k, v in (("ROLLUP_TABLE", "Rollups"), ("AUDIT_BUCKET", "audit-bucket"), ("ALERT_TOPIC_ARN", "arn:aws:sns:us-west-2:123456789012:alerts"), ("STAGE", "qa"), ("EXCLUDE_TEST_ACCOUNTS", "1"),
                 ("STATE_MACHINE_ARN", "arn:aws:states:us-west-2:123456789012:stateMachine:generate_video_workflow_v2"), ("CUSTOMER_POOL_ID", "us-west-2_CUSTOMER"), ("ADMIN_POOL_ID", "us-west-2_ADMIN")):
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("PLANS_CONFIG_PARAM", raising=False)
    for item in FIXTURE:
        aws.Table("Videos").put_item(Item=item)
    sent = []
    monkeypatch.setattr(c, "notify", lambda subject, text: sent.append((subject, text)))
    monkeypatch.setattr(r, "succeeded_runs", lambda since: dict(RUNS))
    monkeypatch.setattr(r, "running_runs", lambda now: [{"name": "v-run", "minutes": 2}])
    monkeypatch.setattr(r, "compute_cost", lambda day, now: 0.80 if day == TODAY else 0.10)
    monkeypatch.setattr(r, "signups", lambda days: {d: (2 if d == TODAY else 1) for d in days})
    monkeypatch.setattr(r, "failed_step", lambda vid, retries: "render")
    yield type("World", (), {"ddb": aws, "s3": s3, "sent": sent})
    c.reset_clients()
    ops_switches._table = None
    ops_switches.set_state(None)


def rollup(world, pk, sk="all"):
    return c.plain(world.ddb.Table("Rollups").get_item(Key={"pk": pk, "sk": sk}).get("Item"))


def event(auth_age=10, sub="admin-sub", body=None, now=None):
    claims = {"sub": sub, "username": "admin-user", "auth_time": str(int((now or time.time()) - auth_age))} if sub else {}
    return {"requestContext": {"authorizer": {"jwt": {"claims": claims}} if sub else {}, "requestId": "req-1", "http": {"sourceIp": "198.51.100.7"}}, "body": json.dumps(body) if body is not None else None}


# ======================================================================== the maths
def test_percentile_is_nearest_rank():
    assert r.percentile([], 50) is None and r.percentile([7], 95) == 7
    assert r.percentile([100, 200, 400], 50) == 200 and r.percentile([100, 200, 400], 95) == 400
    assert r.percentile(list(range(1, 101)), 95) == 95 and r.percentile(list(range(1, 101)), 50) == 50


def test_a_day_is_counted_from_its_records_and_test_accounts_are_left_out():
    today = [x for x in FIXTURE if x["usage_day"] == TODAY]
    s = r.summarize(today, exclude_test=True)
    assert (s["started"], s["complete"], s["failed"], s["cancelled"], s["rejected"], s["in_progress"], s["excluded_test"]) == (8, 3, 2, 1, 1, 1, 1)
    assert s["failure_rate"] == 0.4                                           # failed / (complete + failed) = 2 / 5; cancelled and rejected are beside it
    assert s["cost_tracked"] == pytest.approx(0.69) and s["cost_failed"] == pytest.approx(0.05) and s["cost_cancelled"] == pytest.approx(0.03) and s["cost_rejected"] == pytest.approx(0.01)
    assert s["cost_parts"]["script"] == pytest.approx(0.06) and s["cost_parts"]["speech"] == pytest.approx(0.04)
    assert s["active_accounts"] == 2 and s["credits_charged"] == 5 and s["free_credits"] == 1   # credits of completed videos only: the others are refunded
    assert s["plans"]["pro"] == {"started": 4, "complete": 2, "failed": 1, "cancelled": 0, "cost_tracked": pytest.approx(0.50)} and "test" not in s["plans"]
    with_staff = r.summarize(today, exclude_test=False)
    assert with_staff["started"] == 9 and with_staff["cost_tracked"] == pytest.approx(1.69) and with_staff["plans"]["test"]["complete"] == 1
    empty = r.summarize([], exclude_test=True)
    assert empty["started"] == 0 and empty["failure_rate"] is None and empty["cost_tracked"] == 0


def test_all_in_cost_adds_compute_and_lost_money_takes_its_share():
    s = r.summarize([x for x in FIXTURE if x["usage_day"] == TODAY], exclude_test=True)
    m = r.money(s, 0.80)
    assert m["cost_all_in"] == pytest.approx(1.49) and m["cost_per_video"] == pytest.approx(1.49 / 3, abs=1e-6)
    assert m["lost_usd"] == pytest.approx(0.05 + 0.03 + 0.80 * 3 / 8)          # tracked cost of failed and cancelled + their share of the day's compute
    none = r.money(s, None)                                                     # compute could not be read: the tracked part is still shown, compute says "not known"
    assert none["compute_usd"] is None and none["cost_all_in"] == pytest.approx(0.69) and none["lost_usd"] == pytest.approx(0.08)
    assert r.money(r.summarize([], exclude_test=True), 0.5)["cost_per_video"] is None


def test_time_to_make_uses_first_runs_of_complete_videos_only():
    today = [x for x in FIXTURE if x["usage_day"] == TODAY]
    assert r.make_times(today, RUNS, exclude_test=True) == {"make_p50_s": 200.0, "make_p95_s": 400.0, "make_n": 3}   # the retry run and the staff video are not in it
    assert r.make_times(today, {}, exclude_test=True) == {"make_p50_s": None, "make_p95_s": None, "make_n": 0}


def test_failures_carry_cause_cost_plan_and_length_but_no_prompt_or_account():
    items = r.failure_items(FIXTURE, exclude_test=True)
    assert [i["video_id"] for i in items] == ["v-bad-1", "v-bad-2", "v-stop", "v-y-2"]
    by = {i["video_id"]: i for i in items}
    assert by["v-bad-1"]["cause"].startswith("timeout") and by["v-bad-1"]["code"] == "ReadTimeoutError" and by["v-bad-1"]["cost_usd"] == 0.05 and by["v-bad-1"]["plan"] == "free"
    assert by["v-bad-2"]["cause"].startswith("permission") and len(by["v-bad-2"]["code"]) <= 60 and " " not in by["v-bad-2"]["code"]   # the error NAME, cut and cleaned
    assert by["v-stop"]["cause"] == "cancelled by the person" and by["v-y-2"]["cause"].startswith("bad plan or data")
    text = json.dumps(items)
    assert "Lucia" not in text and "birthday" not in text and ANA not in text and BEN not in text and "user_id" not in text and "prompt" not in text
    assert r.cause_of("UNKNOWN") == "unknown" and r.cause_of("SomethingNew") == "SomethingNew" and r.cause_of("ThrottlingException").startswith("throttled")
    assert r.step_of("V2RenderChunks") == "render" and r.step_of("V2Plan") == "plan" and r.step_of("V2Beats") == "scenes" and r.step_of(None) == ""


def test_the_alerts_fire_when_something_starts_not_every_hour():
    snap = {"today": TODAY, "hour": {"failed": 3, "complete": 2}, "stuck": [], "budget": {"spent": 3, "limit": 15, "unlimited": False, "usd_per_credit": 0.15}}
    emails, state = r.evaluate_alerts(snap, {})
    assert [s for s, _ in emails] == ["videos are failing"] and "3 of the 5" in emails[0][1] and state["failing"] is True
    assert r.evaluate_alerts(snap, state)[0] == []                                                        # still failing an hour later: no second email
    assert r.evaluate_alerts({**snap, "hour": {"failed": 2, "complete": 0}}, {})[0] == []                 # under 3 failures: never
    assert r.evaluate_alerts({**snap, "hour": {"failed": 3, "complete": 12}}, {})[0] == []                # 3 of 15 = 20 %: not MORE than 20 %
    calm, state2 = r.evaluate_alerts({**snap, "hour": {"failed": 0, "complete": 4}}, state)
    assert calm == [] and state2["failing"] is False
    assert [s for s, _ in r.evaluate_alerts(snap, state2)[0]] == ["videos are failing"]                   # it stopped and started again: a new email

    stuck = {**snap, "hour": {"failed": 0, "complete": 0}, "stuck": [{"name": "v-slow", "minutes": 41}]}
    emails, st = r.evaluate_alerts(stuck, {})
    assert [s for s, _ in emails] == ["a video is stuck"] and "v-slow" in emails[0][1] and "41" in emails[0][1]
    assert r.evaluate_alerts(stuck, st)[0] == []

    def budget(spent, prev, **kw):
        return r.evaluate_alerts({"today": TODAY, "hour": {"failed": 0, "complete": 0}, "stuck": [], "budget": {"spent": spent, "limit": 15, "unlimited": False, "usd_per_credit": 0.15, **kw}}, prev)
    assert budget(11, {})[0] == []                                                                        # 73 %
    e80, s80 = budget(12, {})
    assert [s for s, _ in e80] == ["free budget at 80 %"] and "12 of today's 15" in e80[0][1] and s80["budget_levels"] == [80]
    assert budget(13, s80)[0] == []
    e100, s100 = budget(15, s80)
    assert [s for s, _ in e100] == ["free budget at 100 %"] and budget(15, s100)[0] == []
    assert [s for s, _ in budget(15, {})[0]] == ["free budget at 100 %"]                                  # straight to 100 %: one email, not two
    assert [s for s, _ in budget(12, {**s100, "budget_day": YESTERDAY})[0]] == ["free budget at 80 %"]    # a new day starts again
    assert budget(500, {}, unlimited=True)[0] == [] and budget(0, {}, limit=0)[0] == []


def test_the_last_hour_counts_videos_started_in_it():
    assert r.last_hour(FIXTURE, NOW, exclude_test=True) == {"failed": 2, "complete": 1}                   # 13:30 complete, 13:40 and 13:45 failed; 13:58 still running


# ======================================================================== the job
def test_the_job_writes_today_and_yesterday_and_the_failures_list(world):
    snap = r.collect(NOW)
    r.write(snap)
    r.alert(snap)
    t = rollup(world, f"day#{TODAY}")
    assert (t["started"], t["complete"], t["failed"], t["cancelled"], t["failure_rate"], t["signups"], t["active_accounts"]) == (8, 3, 2, 1, 0.4, 2, 2)
    assert t["make_p50_s"] == 200 and t["make_p95_s"] == 400 and t["compute_usd"] == 0.8 and t["cost_all_in"] == pytest.approx(1.49) and t["source"] == "scan" and t["partial"] == []
    assert rollup(world, f"day#{YESTERDAY}")["complete"] == 1 and rollup(world, f"day#{TODAY}", "plan#pro")["started"] == 4
    fails = world.ddb.Table("Rollups").query(KeyConditionExpression=boto3.dynamodb.conditions.Key("pk").eq(f"fail#{TODAY}"))["Items"]
    assert [f["video_id"] for f in fails] == ["v-stop", "v-bad-1", "v-bad-2"] and fails[1]["step"] == "render" and "step" not in fails[0] and all(f["ttl"] > NOW for f in fails)
    meta = rollup(world, "meta", "rollup")
    assert meta["hour"] == {"failed": 2, "complete": 1} and meta["running"] == 1 and meta["updated_at"] == "2027-01-15T14:00:00Z"
    everything = json.dumps(c.plain(world.ddb.Table("Rollups").scan()["Items"]))
    assert "Lucia" not in everything and "birthday" not in everything and ANA not in everything and BEN not in everything   # counts only: no prompt, no account id
    assert world.sent == []                                                                # 2 failures in the hour: under the threshold


def test_frozen_days_survive_an_account_deletion_and_a_rerun_changes_nothing(world):
    def run(at):
        snap = r.collect(at)
        r.write(snap)
    run(NOW)
    before_today, before_yesterday = rollup(world, f"day#{TODAY}"), rollup(world, f"day#{YESTERDAY}")
    run(NOW)                                                                                               # the job ran twice: the same rollups (recomputed, not added)
    assert rollup(world, f"day#{TODAY}") == before_today
    for item in FIXTURE:                                                                                   # Ben deletes his account: every record of his is gone
        if item["user_id"] == BEN:
            world.ddb.Table("Videos").delete_item(Key={"video_id": item["video_id"]})
    run(NOW + 3 * 86400)                                                                                   # three days later
    assert rollup(world, f"day#{TODAY}") == before_today and rollup(world, f"day#{YESTERDAY}") == before_yesterday   # frozen: still counts his videos, holds nothing of him
    assert rollup(world, "day#2027-01-18")["started"] == 0 and rollup(world, "day#2027-01-17")["started"] == 0
    run(NOW + 3600)                                                                                        # (inside the two-day window a rerun does follow the records: by design)
    assert rollup(world, f"day#{TODAY}")["started"] == 4


def test_a_retried_or_deleted_failure_leaves_the_failures_list_of_an_open_day(world):
    r.write(r.collect(NOW))
    world.ddb.Table("Videos").update_item(Key={"video_id": "v-bad-1"}, UpdateExpression="SET #s = :s", ExpressionAttributeNames={"#s": "status"}, ExpressionAttributeValues={":s": "COMPLETE"})
    r.write(r.collect(NOW + 60))
    fails = world.ddb.Table("Rollups").query(KeyConditionExpression=boto3.dynamodb.conditions.Key("pk").eq(f"fail#{TODAY}"))["Items"]
    assert sorted(f["video_id"] for f in fails) == ["v-bad-2", "v-stop"]


def test_a_part_that_cannot_be_read_is_reported_not_guessed(world, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("cloudwatch is down")
    monkeypatch.setattr(r, "compute_cost", boom)
    monkeypatch.setattr(r, "signups", boom)
    snap = r.collect(NOW)
    r.write(snap)
    t = rollup(world, f"day#{TODAY}")
    assert set(snap["partial"]) == {"compute", "signups"} and "compute_usd" not in t and "signups" not in t and t["cost_all_in"] == pytest.approx(0.69) and t["complete"] == 3


def test_the_day_is_read_through_the_index_when_it_exists_and_never_with_the_prompt(world, monkeypatch):
    world.ddb.create_table(
        TableName="VideosIdx", KeySchema=[{"AttributeName": "video_id", "KeyType": "HASH"}], BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": n, "AttributeType": "S"} for n in ("video_id", "usage_day", "created_at")],
        GlobalSecondaryIndexes=[{"IndexName": "GSI_UsageDay", "KeySchema": [{"AttributeName": "usage_day", "KeyType": "HASH"}, {"AttributeName": "created_at", "KeyType": "RANGE"}],
                                 "Projection": {"ProjectionType": "INCLUDE", "NonKeyAttributes": [f for f in r.FIELDS if f not in ("video_id", "usage_day", "created_at")]}}])
    for item in FIXTURE:
        world.ddb.Table("VideosIdx").put_item(Item=item)
    scanned, how = r.read_day(TODAY)
    assert how == "scan" and len(scanned) == 9
    monkeypatch.setenv("VIDEOS_TABLE", "VideosIdx")
    c.reset_clients()
    indexed, how = r.read_day(TODAY)
    assert how == "index" and sorted(x["video_id"] for x in indexed) == sorted(x["video_id"] for x in scanned)
    for row in scanned + indexed:
        assert set(row) <= set(r.FIELDS) and "prompt" not in row and "request_json" not in row and "title" not in row
    assert r.summarize(indexed, exclude_test=True) == r.summarize(scanned, exclude_test=True)


def test_the_job_emails_each_alert_once_and_a_test_alert_on_request(world, monkeypatch):
    world.ddb.Table("Videos").put_item(Item=video("v-bad-3", TODAY, "13:50", "FAILED", failure_code="ReadTimeoutError"))
    world.ddb.Table("Usage").put_item(Item={"user_id": "fbudget", "day": TODAY, "count": 12})
    monkeypatch.setattr(r, "running_runs", lambda now: [{"name": "v-run", "minutes": 44}])
    snap = r.collect(NOW)
    r.write(snap)
    assert sorted(r.alert(snap)) == ["a video is stuck", "free budget at 80 %", "videos are failing"]
    assert len(world.sent) == 3 and all("Lucia" not in text for _, text in world.sent)
    snap = r.collect(NOW + 600)
    r.write(snap)
    assert r.alert(snap) == [] and len(world.sent) == 3
    assert r.handler({"test_alert": True}, None) == {"sent": "test alert"} and world.sent[-1][0] == "test alert"


def test_the_free_budget_knobs_are_read_like_the_launcher_reads_them(world, monkeypatch):
    assert c.BUDGET_DEFAULTS == {k: plans.KNOBS[k][0] for k in c.BUDGET_DEFAULTS}
    assert c.budget_knobs() == c.BUDGET_DEFAULTS                                                           # no parameter name: the defaults
    ssm = boto3.client("ssm", region_name="us-west-2")
    monkeypatch.setenv("PLANS_CONFIG_PARAM", "/videomk/qa/plans/config")
    assert c.budget_knobs() == c.BUDGET_DEFAULTS                                                           # the parameter was never set: the defaults
    ssm.put_parameter(Name="/videomk/qa/plans/config", Type="String", Value=json.dumps({"free_daily_budget_credits": 40, "cost_per_credit_usd": 0.2, "free_budget_unlimited": "yes", "free_web": True}))
    assert c.budget_knobs() == {"free_daily_budget_credits": 40, "free_budget_unlimited": False, "cost_per_credit_usd": 0.2}


# ======================================================================== the switches (the only thing the console can change)
def flags(world):
    return world.ddb.Table("Flags").get_item(Key={"user_id": c.SWITCH_ITEM}).get("Item")


def audit_entries(world):
    keys = [o["Key"] for o in world.s3.list_objects_v2(Bucket="audit-bucket").get("Contents", [])]
    return [json.loads(world.s3.get_object(Bucket="audit-bucket", Key=k)["Body"].read()) for k in sorted(keys)], keys


def test_the_console_and_the_launcher_mean_the_same_item_and_fields():
    assert c.SWITCH_ITEM == ops_switches.ITEM_KEY and c.SWITCHES == ops_switches.SWITCHES and set(c.SWITCH_WORDS) == set(c.SWITCHES)


@pytest.mark.parametrize("ev", [event(sub=None, body={"switch": "stop_new_videos", "stopped": True}), {}, {"requestContext": {}}, None])
def test_no_token_claims_means_no_change(world, ev):
    assert admin_act.handler(ev, None)["statusCode"] == 401 and flags(world) is None and audit_entries(world)[1] == []


@pytest.mark.parametrize("age", [301, 600, 86400, -3600])
def test_a_switch_needs_a_sign_in_from_the_last_five_minutes_and_is_refused_before_anything_is_touched(world, monkeypatch, age):
    def forbidden(*a, **k):
        raise AssertionError("nothing may be read or written before the step-up check passes")
    monkeypatch.setattr(c, "audit", forbidden)
    monkeypatch.setattr(c, "table", forbidden)
    monkeypatch.setattr(c, "client", forbidden)
    res = admin_act.handler(event(auth_age=age, body={"switch": "stop_new_videos", "stopped": True}), None)
    assert res["statusCode"] == 403 and json.loads(res["body"])["code"] == "step_up_required" and world.sent == []


def test_a_token_without_a_sign_in_time_is_refused(world):
    ev = event(body={"switch": "stop_new_videos", "stopped": True})
    del ev["requestContext"]["authorizer"]["jwt"]["claims"]["auth_time"]
    assert admin_act.handler(ev, None)["statusCode"] == 403 and flags(world) is None


@pytest.mark.parametrize("body", [None, {}, {"switch": "free_daily_budget_credits", "stopped": True}, {"switch": "unlimited", "stopped": True}, {"switch": "stop_new_videos", "stopped": "true"},
                                  {"switch": "stop_new_videos"}, {"switch": ["stop_new_videos"], "stopped": True}, [1]])
def test_only_the_two_named_switches_with_true_or_false_are_accepted(world, body):
    assert admin_act.handler(event(body=body), None)["statusCode"] == 400 and flags(world) is None and audit_entries(world)[1] == []


def test_a_switch_is_recorded_changed_and_emailed_and_the_launcher_sees_it(world):
    res = admin_act.handler(event(auth_age=40, body={"switch": "stop_new_videos", "stopped": True}), None)
    body = json.loads(res["body"])
    assert res["statusCode"] == 200 and body["switches"]["stop_new_videos"] is True and body["switches"]["stop_free_videos"] is False
    item = flags(world)
    assert item["stop_new_videos"] is True and item["updated_by"] == "console" and set(item) == {"user_id", "stop_new_videos", "updated_at", "updated_by"}
    entries, keys = audit_entries(world)
    assert len(entries) == 1 and re.match(r"^audit/\d{4}/\d{2}/\d{2}/\d{6}-switch-[0-9a-f]{8}\.json$", keys[0])
    assert entries[0]["action"] == "switch" and entries[0]["switch"] == "stop_new_videos" and entries[0]["stopped"] is True and entries[0]["actor"] == "admin-sub" and entries[0]["auth_age_s"] == 40
    assert "@" not in json.dumps(entries)                                                                  # never an email address
    assert len(world.sent) == 1 and world.sent[0][0] == "New videos switched OFF" and "admin-disable-user" in world.sent[0][1] and "admin-user" in world.sent[0][1]
    assert ops_switches.stopped(ops_switches.NEW_VIDEOS) and not ops_switches.stopped(ops_switches.FREE_VIDEOS)   # the customer side reads exactly this

    admin_act.handler(event(body={"switch": "stop_free_videos", "stopped": True}), None)
    admin_act.handler(event(body={"switch": "stop_new_videos", "stopped": False}), None)
    item = flags(world)
    assert item["stop_new_videos"] is False and item["stop_free_videos"] is True                           # one switch never touches the other
    entries, _ = audit_entries(world)
    assert sorted((e["switch"], e["stopped"]) for e in entries) == [("stop_free_videos", True), ("stop_new_videos", False), ("stop_new_videos", True)]   # one entry per change
    assert [s for s, _ in world.sent] == ["New videos switched OFF", "Free videos switched OFF", "New videos switched back ON"]


def test_no_audit_entry_no_change(world, monkeypatch):
    def down(*a, **k):
        raise RuntimeError("s3 is down")
    monkeypatch.setattr(c, "audit", down)
    res = admin_act.handler(event(body={"switch": "stop_new_videos", "stopped": True}), None)
    assert res["statusCode"] == 500 and json.loads(res["body"])["code"] == "audit_failed" and flags(world) is None and world.sent == []


def test_a_failed_email_does_not_undo_a_recorded_change(world, monkeypatch):
    def down(*a, **k):
        raise RuntimeError("sns is down")
    monkeypatch.setattr(c, "notify", down)
    assert admin_act.handler(event(body={"switch": "stop_free_videos", "stopped": True}), None)["statusCode"] == 200
    assert flags(world)["stop_free_videos"] is True and len(audit_entries(world)[0]) == 1


def test_every_sign_in_is_recorded_and_emailed_and_a_failure_never_blocks_it(world, monkeypatch):
    ev = {"triggerSource": "PostAuthentication_Authentication", "userPoolId": "eu-west-1_ADMIN", "userName": "abc-123", "request": {"userAttributes": {"sub": "admin-sub", "email": "owner@example.org"}}, "response": {}}
    assert admin_auth_event.handler(ev, None) is ev
    entries, _ = audit_entries(world)
    assert entries[0]["action"] == "sign_in" and entries[0]["actor"] == "admin-sub" and "@" not in json.dumps(entries)
    assert world.sent[0][0] == "console sign-in" and "eu-west-1_ADMIN" in world.sent[0][1] and "abc-123" in world.sent[0][1] and "owner@example.org" not in world.sent[0][1]

    def down(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(c, "audit", down)
    monkeypatch.setattr(c, "notify", down)
    assert admin_auth_event.handler(ev, None) is ev


# ======================================================================== the read answer
def test_the_home_answer_has_the_numbers_and_nothing_personal(world, monkeypatch):
    snap = r.collect(NOW)
    r.write(snap)
    world.ddb.Table("Usage").put_item(Item={"user_id": "fbudget", "day": TODAY, "count": 9})
    world.ddb.Table("Flags").put_item(Item={"user_id": c.SWITCH_ITEM, "stop_free_videos": True, "updated_at": "2027-01-15T13:05:00Z"})
    monkeypatch.setattr(admin_read.time, "time", lambda: NOW + 540)
    monkeypatch.setattr(admin_read, "running", lambda now: {"count": 3, "more": False, "oldest_minutes": 4})
    monkeypatch.setattr(admin_read, "alarms", lambda: {"total": 7, "firing": []})
    res = admin_read.handler(event(auth_age=30, now=NOW + 540), None)
    h = json.loads(res["body"])
    assert res["statusCode"] == 200 and res["headers"]["Cache-Control"] == "no-store" and "Access-Control-Allow-Origin" not in res["headers"]
    assert [d["day"] for d in h["days"]] == ["2027-01-09", "2027-01-10", "2027-01-11", "2027-01-12", "2027-01-13", YESTERDAY, TODAY]
    assert h["days"][0] == {"day": "2027-01-09", "missing": True} and h["days"][-1]["complete"] == 3 and h["days"][-1]["cost_all_in"] == pytest.approx(1.49) and h["days"][-2]["failed"] == 1
    assert h["budget"] == {"spent": 9, "limit": 15, "unlimited": False, "usd_per_credit": 0.15, "spent_usd": 1.35, "limit_usd": 2.25}
    assert h["switches"]["stop_free_videos"] is True and h["switches"]["stop_new_videos"] is False and h["running"]["count"] == 3
    assert [f["video_id"] for f in h["failures"]] == ["v-bad-2", "v-bad-1", "v-stop", "v-y-2"] and h["failures"][0]["step"] == "render"   # newest first
    assert h["session"] == {"signed_in_seconds_ago": 30, "step_up_seconds": 300, "can_switch": True} and h["meta"]["updated_at"] == "2027-01-15T14:00:00Z"
    text = res["body"]
    assert "Lucia" not in text and "birthday" not in text and ANA not in text and BEN not in text and "user_id" not in text and "prompt" not in text and "@" not in text


def test_a_part_of_the_page_that_fails_says_so_and_the_rest_still_answers(world, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("step functions is down")
    monkeypatch.setattr(admin_read, "running", boom)
    monkeypatch.setattr(admin_read, "alarms", lambda: {"total": 0, "firing": []})
    h = json.loads(admin_read.handler(event(), None)["body"])
    assert h["running"] == {"error": True} and h["meta"] == {"missing": True} and h["failures"] == [] and all(d.get("missing") for d in h["days"]) and h["budget"]["spent"] == 0
    assert admin_read.handler(event(sub=None), None)["statusCode"] == 401


def test_last_fifty_failures_at_most(world):
    t = world.ddb.Table("Rollups")
    for i in range(70):
        t.put_item(Item={"pk": f"fail#{TODAY if i < 40 else YESTERDAY}", "sk": f"{i:03d}", "video_id": f"v{i}", "at": f"{TODAY}T00:00:{i % 60:02d}Z", "status": "FAILED"})
    assert len(admin_read.failures(NOW)) == 50


# ======================================================================== the page
def test_the_page_loads_nothing_from_outside_and_has_no_inline_code():
    html = open(os.path.join(SITE, "index.html"), encoding="utf-8").read()
    js = open(os.path.join(SITE, "app.js"), encoding="utf-8").read()
    css = open(os.path.join(SITE, "app.css"), encoding="utf-8").read()
    assert sorted(os.listdir(SITE)) == ["app.css", "app.js", "favicon.svg", "index.html", "logo-dark.svg", "logo-light.svg"]
    assert not re.search(r"https?://", html) and not re.search(r"https?://", css.replace("http://www.w3.org", ""))
    assert re.findall(r"https?://[^'\"\s)]+", js) == ["http://www.w3.org/2000/svg", "https://cognito-idp."]   # the SVG namespace and the admin pool's own endpoint: nothing else
    assert re.findall(r"<script[^>]*>", html) == ['<script src="app.js" defer>'] and "<style" not in html and " style=" not in html and not re.search(r"\son[a-z]+=", html)
    assert "innerHTML" not in js and "eval(" not in js and "document.write" not in js and "sessionStorage" not in js and "document.cookie" not in js
    assert js.count("localStorage") == 2 and "USER_KEY" in js                                             # the sign-in name only; tokens stay in memory
    assert "noindex" in html and "VideoMK" in html and "prefers-color-scheme: dark" in css
    for text in (html, js):
        assert not re.search(r"\b(Videomk|VideoMk|VIDEOMK|videoMK)\b", text)
    assert "prompt" not in js.lower().replace("no prompt text", "")


def test_the_logo_files_are_the_brand_masters():
    brand = os.path.join(ROOT, "..", "docs", "brand", "final")
    for copy, master in (("logo-light.svg", "lockup-horizontal-light.svg"), ("logo-dark.svg", "lockup-horizontal-dark.svg"), ("favicon.svg", "favicon.svg")):
        assert open(os.path.join(SITE, copy), "rb").read() == open(os.path.join(brand, master), "rb").read()


def test_the_dictation_switch_is_a_console_switch_the_customer_side_reads_and_the_page_words_it(world):
    assert "stop_dictation" in c.SWITCHES and c.SWITCH_WORDS["stop_dictation"] == "Dictation"
    from common import dictation
    assert dictation.STOP_SWITCH == ops_switches.DICTATION == "stop_dictation"
    res = admin_act.handler(event(auth_age=40, body={"switch": "stop_dictation", "stopped": True}), None)
    assert res["statusCode"] == 200 and json.loads(res["body"])["switches"]["stop_dictation"] is True
    assert ops_switches.stopped(dictation.STOP_SWITCH) and not ops_switches.stopped(ops_switches.NEW_VIDEOS)
    assert [s for s, _ in world.sent] == ["Dictation switched OFF"]
    js = open(os.path.join(os.path.dirname(__file__), "..", "admin_console", "site", "app.js")).read()
    assert "stop_dictation: { name: 'Dictation'" in js
