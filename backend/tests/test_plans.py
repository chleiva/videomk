"""Plans, phase 1 (docs/PLANS.md): the entitlements record and its transitions, the monthly plan credits (idempotent, rollover, cap, refund, expiry), enforcement per plan at
the launcher (length, resolution, watermark, photos), storage by plan, the API (capabilities, wallet, plan, purchase stubs) and the security rules (nobody changes their own
plan; another person's plan is unreadable). The free plan's knobs and abuse controls are in tests/test_free_grants.py."""
import json
import os
import re

import boto3
import pytest

import capabilities_api
import plans_api
import wallet_api
from common import deletion, entitlements, free_grants, library, plans, wallet, watermark_store as store
from tests.test_hardening import _event, launcher  # noqa: F401  (the fixture)

DAY = 86400
T0 = 1_800_000_000.0   # 2027-01-15 08:00:00 UTC
USER = "11111111-aaaa-bbbb-cccc-222222222222"
OTHER = "99999999-aaaa-bbbb-cccc-222222222222"
PROMPT = "A short explainer about how black holes form"
OPEN = {"free_web": True, "require_device_proof": False, "free_daily_budget_credits": 1000, "welcome_credits": 5, "free_max_seconds": 30}   # these tests are about plans: the free plan's gates are opened


@pytest.fixture
def plans_on(aws, monkeypatch):
    """Plans switched on as the stack does it, with the two new tables. Yields a helper with the mocked resources."""
    for name, key in (("Entitlements", "user_id"), ("FreeClaims", "pk")):
        aws.create_table(TableName=name, KeySchema=[{"AttributeName": key, "KeyType": "HASH"}], AttributeDefinitions=[{"AttributeName": key, "AttributeType": "S"}], BillingMode="PAY_PER_REQUEST")
    for k, v in (("PLANS_ENABLED", "1"), ("ENTITLEMENTS_TABLE", "Entitlements"), ("FREE_CLAIMS_TABLE", "FreeClaims"), ("DAILY_VIDEO_LIMIT", "100"), ("WATERMARK_ENABLED", "1"),
                 ("ASSETS_BUCKET", "assets-plans"), ("PLANS_REQUIRE_DEVICE_PROOF_DEFAULT", "0"), ("DUPLICATE_WINDOW_S", "0")):
        monkeypatch.setenv(k, v)
    monkeypatch.delenv("PLANS_CONFIG_PARAM", raising=False)
    s3 = boto3.client("s3", region_name="us-west-2")
    s3.create_bucket(Bucket="assets-plans", CreateBucketConfiguration={"LocationConstraint": "us-west-2"})
    store.set_clients(s3, aws)
    entitlements.set_resource(aws)
    free_grants.set_resource(aws)
    deletion.set_key(b"k" * 32)
    plans.set_config(dict(OPEN))
    yield type("P", (), {"ddb": aws, "s3": s3})()
    plans.set_config(None)
    store.set_clients(None, None)
    entitlements.set_resource(None)
    free_grants.set_resource(None)
    deletion.set_key(None)


def app_event(user=USER, body=None, platform="ios", email=None, ip="203.0.113.7", headers=None, resource=None, method="POST"):
    ev = _event(user=user, body=body if body is not None else {"prompt": PROMPT, "target_minutes": 0.5})
    ev["requestContext"] = {"authorizer": {"claims": {"sub": user, "email": email or f"{user[:8]}@example.org", "email_verified": "true"}}, "identity": {"sourceIp": ip}}
    ev["headers"] = {**ev["headers"], **({"X-Platform": platform} if platform else {}), **(headers or {})}
    if resource:
        ev["resource"], ev["httpMethod"] = resource, method
    return ev


def launch(launcher, user=USER, **body):
    extra = {k: body.pop(k) for k in ("platform", "email", "ip", "headers") if k in body}
    return launcher.handler(app_event(user=user, body={"prompt": PROMPT, **body}, **extra), None)


def body_of(r):
    return json.loads(r["body"])


def give_plan(user, plan, *, now=None, **kw):
    return entitlements.set_plan(user, plan, now=now, **kw)


def plan_credits(user, now):
    return sum(b["remaining"] for b in wallet.balance(user, now=now)["buckets"] if b["kind"] == "plan")


# ======================================================================== the ladder is defined once
def test_the_approved_ladder():
    p = plans.PLANS
    assert [(x, p[x]["credits_per_month"], p[x]["credits_cap"], p[x]["max_seconds"], p[x]["storage_bytes"] // plans.GB) for x in plans.ORDER] == [
        ("free", 0, 0, 60, 2), ("pro", 30, 30, 300, 100), ("max", 120, 240, 720, 300)]
    assert p["free"]["watermark_modes"] == ["videomk"] and p["free"]["watermark_forced"] and not p["free"]["commercial_use"]
    assert p["pro"]["watermark_modes"] == ["none", "videomk", "moments"] and "2160p" not in p["pro"]["resolutions"] and p["pro"]["rollover_months"] == 0
    assert p["max"]["watermark_modes"][-1] == "custom" and "2160p" in p["max"]["resolutions"] and p["max"]["rollover_months"] == 1
    assert p["max"]["priority_queue"] and p["max"]["premium_looks"] and not p["pro"]["priority_queue"] and not p["pro"]["premium_looks"]
    assert plans.PRODUCTS["max"]["apple"]["yearly"] == "com.videomk.app.max.yearly" and plans.PRODUCTS["pro"]["google"]["subscription"] == "videomk_pro"
    assert plans.PURCHASES_LIVE is False


def test_locked_names_the_cheapest_plan_that_unlocks_each_thing(plans_on):
    by = {(x["feature"], str(x["value"])): x for x in plans.locked("free")}
    assert by[("resolution", "2160p")]["requires_plan"] == "max" and by[("watermark", "none")]["requires_plan"] == "pro" and by[("watermark", "custom")]["requires_plan"] == "max"
    assert by[("length", "300")] == {"feature": "length", "value": 300, "requires_plan": "pro", "over_seconds": 30, "max_seconds": 300}
    assert by[("length", "720")]["requires_plan"] == "max" and by[("length", "720")]["over_seconds"] == 300
    assert by[("storage", str(100 * plans.GB))]["requires_plan"] == "pro" and by[("premium_looks", "True")]["requires_plan"] == "max"
    assert {x["feature"] for x in plans.locked("pro")} == {"length", "resolution", "watermark", "storage", "photos", "priority_queue", "premium_looks"}
    assert plans.locked("max") == []


# ======================================================================== entitlement transitions (pure)
@pytest.mark.parametrize("item,now,expect", [
    (None, T0, ("free", "active", False)),
    ({"plan": "pro", "state": "active", "period_end": T0 + DAY}, T0, ("pro", "active", True)),
    ({"plan": "pro", "state": "active", "period_end": T0 + DAY}, T0 + DAY, ("free", "expired", False)),                                   # the date decides: no job has to flip the state
    ({"plan": "max", "state": "active"}, T0 + 4000 * DAY, ("max", "active", True)),                                                        # no end date (an admin grant)
    ({"plan": "pro", "state": "active", "period_end": T0, "grace_until": T0 + 16 * DAY}, T0 + DAY, ("pro", "grace", True)),               # billing retry: rights stay
    ({"plan": "pro", "state": "grace", "period_end": T0, "grace_until": T0 + 16 * DAY}, T0 + 17 * DAY, ("free", "expired", False)),
    ({"plan": "max", "state": "refunded", "period_end": T0 + 30 * DAY}, T0, ("free", "refunded", False)),
    ({"plan": "max", "state": "expired", "period_end": T0 + 30 * DAY}, T0, ("free", "expired", False)),
    ({"plan": "platinum", "state": "active"}, T0, ("free", "active", False)),                                                              # an unknown plan is no plan
    ({"plan": "pro", "state": "whatever"}, T0, ("free", "expired", False)),
])
def test_what_applies_now(item, now, expect):
    e = entitlements.evaluate(item, now=now)
    assert (e["plan"], e["state"], e["grants_credits"]) == expect


def test_an_unlimited_test_account_has_the_rights_of_max_and_no_plan_credits():
    e = entitlements.evaluate(None, now=T0, unlimited=True)
    assert e["plan"] == "max" and e["unlimited"] and not e["grants_credits"]
    assert entitlements.evaluate({"plan": "pro", "state": "active"}, now=T0, unlimited=True)["plan"] == "max"


def test_monthly_dates_count_from_the_anchor_and_clamp_to_the_month_end():
    import calendar
    jan31 = calendar.timegm((2027, 1, 31, 10, 0, 0))
    assert [__import__("time").strftime("%m-%d", __import__("time").gmtime(entitlements.add_months(jan31, k))) for k in (1, 2, 3, 12, 13)] == ["02-28", "03-31", "04-30", "01-31", "02-29"]


def test_the_record_and_its_writers(plans_on):
    it = give_plan(USER, "pro", until=int(T0 + 30 * DAY), now=T0, source="apple", renews=True, product_id="com.videomk.app.pro.monthly")
    assert (it["plan"], it["state"], it["source"], it["interval"], it["anchor"], it["period_end"], it["renews"]) == ("pro", "active", "apple", "month", int(T0), int(T0 + 30 * DAY), True)
    assert entitlements.effective(USER, now=T0 + DAY)["plan"] == "pro" and entitlements.effective(OTHER, now=T0)["plan"] == "free"
    entitlements.set_state(USER, "grace", now=T0 + 30 * DAY)
    e = entitlements.effective(USER, now=T0 + 31 * DAY)
    assert (e["plan"], e["state"]) == ("pro", "grace") and e["grace_until"] == int(T0 + 46 * DAY)
    entitlements.set_state(USER, "refunded", now=T0 + 31 * DAY)
    e = entitlements.effective(USER, now=T0 + 31 * DAY)
    assert (e["plan"], e["state"], e["record_plan"], e["renews"]) == ("free", "refunded", "pro", False)
    give_plan(USER, "max", now=T0 + 40 * DAY)
    assert entitlements.effective(USER, now=T0 + 41 * DAY)["plan"] == "max"                 # one record per account: the new plan replaces the old one
    give_plan(USER, "free", now=T0 + 42 * DAY)
    assert entitlements.effective(USER, now=T0 + 42 * DAY)["plan"] == "free"
    assert [x["action"] for x in entitlements.get(USER)["log"]] == ["plan:pro", "grace", "refunded", "plan:max", "ended"]
    for bad in (dict(plan="gold"), dict(plan="pro", source="me"), dict(plan="pro", until=int(T0 - 1), now=T0), dict(plan="pro", interval="week")):
        with pytest.raises(ValueError):
            entitlements.set_plan(USER, **bad)


# ======================================================================== plan credits
def test_pro_gets_30_once_per_month_and_nothing_rolls_over(plans_on):
    give_plan(USER, "pro", now=T0)
    assert plan_credits(USER, T0) == 30
    for _ in range(3):
        assert plan_credits(USER, T0 + 3600) == 30                                           # idempotent: reading again grants nothing
    wallet.charge(USER, 5, now=T0 + DAY, ctx=None)
    assert plan_credits(USER, T0 + 2 * DAY) == 25
    nxt = entitlements.add_months(T0, 1)
    assert plan_credits(USER, nxt - 60) == 25
    assert plan_credits(USER, nxt + 60) == 30                                                # the unused 25 ended, a fresh 30 arrived: never 55
    b = [x for x in wallet.balance(USER, now=nxt + 60)["buckets"] if x["kind"] == "plan"]
    assert len(b) == 1 and b[0]["expires_at"] == entitlements.add_months(T0, 2)


def test_concurrent_reads_grant_the_month_once(plans_on):
    import threading
    give_plan(USER, "max", now=T0)
    threads = [threading.Thread(target=lambda: wallet.balance(USER, now=T0 + 5)) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert plan_credits(USER, T0 + 10) == 120


def test_max_rolls_over_one_month_and_is_capped_at_240(plans_on):
    give_plan(USER, "max", now=T0)
    m = [entitlements.add_months(T0, k) for k in range(5)]
    assert plan_credits(USER, m[0] + 60) == 120
    assert plan_credits(USER, m[1] + 60) == 240                                              # month 1 unused: carried over once
    assert plan_credits(USER, m[2] + 60) == 240                                              # month 1's credits ended, month 3's arrived: still 240, never 360
    wallet.charge(USER, 200, now=m[2] + 120, ctx=None)                                      # soonest to expire first: all of month 2's 120, then 80 of month 3's
    assert plan_credits(USER, m[2] + 180) == 40
    assert plan_credits(USER, m[3] + 60) == 160                                              # 40 carried + 120 new
    kinds = [(b["remaining"], b["expires_at"]) for b in wallet.balance(USER, now=m[3] + 60)["buckets"] if b["kind"] == "plan"]
    assert kinds == [(40, m[4]), (120, entitlements.add_months(T0, 5))]


def test_the_cap_holds_when_plans_change(plans_on):
    give_plan(USER, "max", now=T0)
    assert plan_credits(USER, T0 + 60) == 120
    assert plan_credits(USER, entitlements.add_months(T0, 1) + 60) == 240
    give_plan(USER, "max", now=entitlements.add_months(T0, 1) + 3600)                        # a new subscription (a new anchor) the same day: nothing above the cap
    assert plan_credits(USER, entitlements.add_months(T0, 1) + 7200) == 240
    give_plan(OTHER, "pro", now=T0)
    assert plan_credits(OTHER, T0 + 60) == 30
    give_plan(OTHER, "max", now=T0 + DAY)                                                    # an upgrade in the middle of the month: Pro's 30 stay until their date, Max's 120 arrive
    assert plan_credits(OTHER, T0 + DAY + 60) == 150
    give_plan(OTHER, "pro", now=T0 + 2 * DAY)                                                # down to Pro again: its cap is 30, so nothing new is added
    assert plan_credits(OTHER, T0 + 2 * DAY + 60) == 150


def test_a_wallet_that_was_not_opened_catches_up_only_on_what_is_still_valid(plans_on):
    give_plan(USER, "max", now=T0)
    give_plan(OTHER, "pro", now=T0)
    later = entitlements.add_months(T0, 3) + 60                                              # never opened in months 1 to 3
    assert plan_credits(USER, later) == 240                                                  # Max: last month's (still valid) and this month's
    assert plan_credits(OTHER, later) == 30                                                  # Pro: only this month's


def test_a_yearly_plan_gets_twelve_monthly_grants_not_one(plans_on):
    end = entitlements.add_months(T0, 12)
    give_plan(USER, "pro", until=end, interval="year", now=T0)
    seen = []
    for k in range(12):
        seen.append(plan_credits(USER, entitlements.add_months(T0, k) + 60))
    assert seen == [30] * 12
    refs = plans_on.ddb.Table("Wallet").query(KeyConditionExpression=boto3.dynamodb.conditions.Key("user_id").eq(USER) & boto3.dynamodb.conditions.Key("sk").begins_with("PLAN#"))["Items"]
    assert len(refs) == 12 and sum(int(r["credits"]) for r in refs) == 360
    assert plan_credits(USER, end + 60) == 0 and entitlements.effective(USER, now=end + 60)["plan"] == "free"   # not renewed: no 13th grant


def test_grace_keeps_the_rights_but_grants_no_new_month(plans_on):
    end = entitlements.add_months(T0, 1)
    give_plan(USER, "max", until=end, now=T0)
    assert plan_credits(USER, T0 + 60) == 120
    entitlements.set_state(USER, "grace", grace_until=end + 16 * DAY, now=end - 60)
    assert entitlements.effective(USER, now=end + DAY)["plan"] == "max"
    assert plan_credits(USER, end + DAY) == 120                                              # last month's rollover is still there; the unpaid month gave nothing
    assert plan_credits(USER, end + 17 * DAY) == 0                                           # grace over: the plan and its credits end


def test_a_refund_removes_unused_plan_credits_and_returns_to_free_never_below_zero(plans_on):
    give_plan(USER, "max", now=T0)
    wallet.give_credits(USER, 7)                                                             # bought credits are not plan credits
    wallet.balance(USER, now=T0 + 60)
    wallet.charge(USER, 100, now=T0 + 120, ctx=None)
    entitlements.set_state(USER, "refunded", now=T0 + 3600)
    assert wallet.revoke_plan_credits(USER, now=T0 + 3600) == 20
    assert wallet.revoke_plan_credits(USER, now=T0 + 3601) == 0                              # twice: nothing more to take
    b = wallet.balance(USER, now=T0 + 3700)
    assert b["plan"]["id"] == "free" and b["plan"]["state"] == "refunded" and b["plan"]["plan_credits"] == 0
    assert {x["kind"]: x["remaining"] for x in b["buckets"]}.get("paid") == 7 and all(x["remaining"] >= 0 for x in b["buckets"])
    raw = plans_on.ddb.Table("Wallet").query(KeyConditionExpression=boto3.dynamodb.conditions.Key("user_id").eq(USER))["Items"]
    assert all(int(x["remaining"]) >= 0 for x in raw if x["sk"].startswith("B#"))


def test_plan_credits_end_with_the_plan_even_without_an_explicit_revoke(plans_on):
    give_plan(USER, "max", until=int(T0 + 30 * DAY), now=T0)
    assert plan_credits(USER, T0 + 60) == 120
    assert plan_credits(USER, T0 + 31 * DAY) == 0                                            # expired by date: the next read sweeps what was left
    with pytest.raises(wallet.InsufficientCredits):
        wallet.charge(USER, 1, now=T0 + 31 * DAY, ctx=None)
    give_plan(OTHER, "pro", now=T0)
    assert plan_credits(OTHER, T0 + 60) == 30
    give_plan(OTHER, "free", now=T0 + DAY)                                                   # ended by an admin
    assert plan_credits(OTHER, T0 + DAY + 60) == 0


def test_spending_order_stays_soonest_to_expire_first(plans_on):
    wallet.balance(USER, now=T0, ctx=free_grants.context(app_event()))                       # 5 welcome credits (30 days)
    give_plan(USER, "pro", now=T0 + 10 * DAY)                                                # plan credits end on day 10 + 1 month, after the welcome credits
    wallet.give_credits(USER, 3)
    takes = wallet.charge(USER, 7, now=T0 + 11 * DAY, ctx=None)
    assert [(t["sk"].split("#")[2], t["n"]) for t in takes] == [("signup", 5), ("plan", 2)]
    assert {b["kind"]: b["remaining"] for b in wallet.balance(USER, now=T0 + 11 * DAY)["buckets"]} == {"plan": 28, "paid": 3}


# ======================================================================== enforcement at the launcher
def started(launcher):
    return json.loads(launcher.fake.calls[-1]["input"])


def test_free_length_cap_comes_from_the_knob_and_names_the_plan_that_unlocks_more(launcher, plans_on):
    r = launch(launcher, target_minutes=1)
    b = body_of(r)
    assert r["statusCode"] == 403 and b["code"] == "plan_length" and b["plan"] == "free" and b["requires_plan"] == "pro" and b["limit"]["max_seconds"] == 30 and b["can_upgrade"] is False
    assert b["message"] == "Videos on your plan can be up to 0:30 long. Pro makes longer ones."
    assert body_of(launch(launcher, target_minutes=6))["requires_plan"] == "max"            # over Pro's five minutes
    es = body_of(launch(launcher, target_minutes=1, headers={"X-Locale": "es"}))
    assert es["message"] == "Con tu plan los videos duran hasta 0:30. Pro permite videos más largos."
    assert launcher.fake.calls == []                                                         # nothing started, nothing charged
    assert wallet.balance(USER, ctx=free_grants.context(app_event()))["balance"] == 5
    assert launch(launcher, target_minutes=0.5)["statusCode"] == 202
    plans.set_config({**OPEN, "free_max_seconds": 60})                                       # the owner raises the cap: no deploy
    assert launch(launcher, target_minutes=1)["statusCode"] == 202


def test_no_length_given_means_the_default_shortened_to_the_plan(launcher, plans_on):
    assert launch(launcher)["statusCode"] == 202
    assert started(launcher)["target_minutes"] == 0.5                                        # the server default is 3 minutes; Free makes 30 seconds
    give_plan(OTHER, "pro", now=None)
    assert launch(launcher, user=OTHER)["statusCode"] == 202 and started(launcher)["target_minutes"] == 3.0


@pytest.mark.parametrize("plan,minutes,resolution,status,code,needs", [
    ("free", 0.5, "1080p", 202, None, None), ("free", 0.5, "720p", 202, None, None), ("free", 0.5, "2160p", 403, "plan_resolution", "max"),
    ("pro", 5, "1080p", 202, None, None), ("pro", 5.5, None, 403, "plan_length", "max"), ("pro", 1, "2160p", 403, "plan_resolution", "max"),
    ("max", 12, "1080p", 202, None, None), ("max", 2, "2160p", 202, None, None),
])
def test_length_and_resolution_per_plan(launcher, plans_on, monkeypatch, plan, minutes, resolution, status, code, needs):
    monkeypatch.setenv("READY_RESOLUTIONS", "720p,1080p,2160p")
    if plan != "free":
        give_plan(USER, plan)
    r = launch(launcher, target_minutes=minutes, **({"resolution": resolution} if resolution else {}))
    assert r["statusCode"] == status, r["body"]
    if code:
        assert (body_of(r)["code"], body_of(r)["requires_plan"]) == (code, needs) and launcher.fake.calls == []
    elif plan == "max" and resolution == "2160p":
        row = plans_on.ddb.Table("Videos").scan()["Items"][0]
        assert int(row["credits_charged"]) == 4 and row["plan"] == "max" and int(row["priority"]) == 1    # 4K costs double; Max videos are marked for the priority queue
        assert wallet.balance(USER)["balance"] == 121   # 5 welcome + 120 plan - 4: the welcome credits end first, so they are spent first


def test_the_free_resolution_knob(launcher, plans_on):
    plans.set_config({**OPEN, "free_max_resolution": "720p"})
    r = launch(launcher, target_minutes=0.5, resolution="1080p")
    assert body_of(r)["code"] == "plan_resolution" and body_of(r)["requires_plan"] == "pro" and body_of(r)["message"] == "1080p is part of the Pro plan."
    assert launch(launcher, target_minutes=0.5)["statusCode"] == 202 and started(launcher)["resolution"] == "720p"   # none given: the plan's best


def test_photos_per_video_follow_the_plan(launcher, plans_on):
    ids = [f"{i:016x}" for i in range(31)]
    for i in ids:
        plans_on.s3.put_object(Bucket="assets-plans", Key=f"uploads/{USER}/{i}.jpg", Body=b"x")
    r = launch(launcher, target_minutes=0.5, media=ids[:11])
    assert r["statusCode"] == 403 and body_of(r)["code"] == "plan_photos" and body_of(r)["requires_plan"] == "pro" and body_of(r)["limit"] == {"photos_per_video": 10}
    assert launch(launcher, target_minutes=0.5, media=ids[:10])["statusCode"] == 202
    give_plan(USER, "pro")
    assert body_of(launch(launcher, target_minutes=1, media=ids[:31]))["requires_plan"] == "max"
    assert launch(launcher, target_minutes=1, media=ids[:30])["statusCode"] == 202


def test_premium_looks_are_flagged_for_max_only(launcher, plans_on):
    launch(launcher, target_minutes=0.5)
    assert "premium_looks" not in started(launcher)
    give_plan(USER, "max")
    launch(launcher, target_minutes=2)
    assert started(launcher)["premium_looks"] is True


def test_enforcement_can_be_switched_off_with_the_knob(launcher, plans_on):
    plans.set_config({**OPEN, "enforce": False, "welcome_credits": 5})
    assert launch(launcher, target_minutes=3)["statusCode"] == 202 and "watermark" not in started(launcher)


def put_logo(p, user=USER):
    p.s3.put_object(Bucket="assets-plans", Key=f"watermark/{user}/logo.png", Body=b"png")


def test_free_videos_always_carry_the_videomk_mark_with_the_name_and_the_end_card(launcher, plans_on):
    assert launch(launcher, target_minutes=0.5)["statusCode"] == 202
    wm = started(launcher)["watermark"]
    assert (wm["mode"], wm["style"], wm["end_card"]) == ("videomk", "lockup", True) and wm["opacity"] >= 0.9
    r = launch(launcher, target_minutes=0.5, watermark={"mode": "none"})
    assert r["statusCode"] == 403 and body_of(r)["code"] == "plan_watermark" and body_of(r)["requires_plan"] == "pro"
    assert body_of(r)["plan"] == "free" and body_of(r)["can_upgrade"] is False                # like every plan refusal: which plan the account has, and that nothing can be bought yet
    r = launch(launcher, target_minutes=0.5, watermark={"mode": "custom"})
    assert r["statusCode"] == 403 and body_of(r)["code"] == "watermark_premium" and body_of(r)["requires_plan"] == "max"
    assert "Max" in body_of(r)["message"] and "Pro" not in body_of(r)["message"]               # found on QA 2026-11-27: the sentence said Pro while requires_plan said max
    assert body_of(r)["plan"] == "free" and body_of(r)["can_upgrade"] is False
    # the person may still choose the corner and the size, but cannot fade the mark away or drop the name
    assert launch(launcher, target_minutes=0.5, watermark={"mode": "videomk", "position": "tl", "size": "medium", "opacity": 0.2, "style": "mark", "end_card": False})["statusCode"] == 202
    wm = started(launcher)["watermark"]
    assert (wm["position"], wm["size"], wm["style"], wm["end_card"], wm["opacity"]) == ("tl", "medium", "lockup", True, 0.9)
    store.put_profile(USER, {"mode": "none"})                                                # a setting saved while on a plan: falls back quietly
    assert launch(launcher, target_minutes=0.5)["statusCode"] == 202 and started(launcher)["watermark"]["mode"] == "videomk"


def test_pro_may_remove_the_mark_but_own_logo_is_max(launcher, plans_on):
    give_plan(USER, "pro")
    put_logo(plans_on)
    assert launch(launcher, target_minutes=1)["statusCode"] == 202 and "watermark" not in started(launcher)                      # nothing forced
    assert launch(launcher, target_minutes=1, watermark={"mode": "none"})["statusCode"] == 202 and "watermark" not in started(launcher)
    assert launch(launcher, target_minutes=1, watermark={"mode": "videomk", "style": "mark"})["statusCode"] == 202 and started(launcher)["watermark"]["style"] == "mark"
    r = launch(launcher, target_minutes=1, watermark={"mode": "custom"})
    assert r["statusCode"] == 403 and body_of(r)["code"] == "watermark_premium" and body_of(r)["requires_plan"] == "max"
    give_plan(USER, "max")
    assert launch(launcher, target_minutes=1, watermark={"mode": "custom"})["statusCode"] == 202 and started(launcher)["watermark"]["mode"] == "custom"


def test_the_storage_flag_no_longer_gives_the_logo_but_the_admin_override_and_test_accounts_do(launcher, plans_on):
    flags = plans_on.ddb.Table("Flags")
    put_logo(plans_on)
    flags.put_item(Item={"user_id": USER, "storage_plan": "pro"})                            # before plans this meant "premium": own logo is Max only now (owner decision 6)
    assert store.rights(USER) == {"premium": False, "forced": True, "modes": ["videomk"], "by_plan": True, "plan": "free", "test": False}
    flags.put_item(Item={"user_id": USER, "watermark_custom": True})                         # the admin's override stays: own logo, nothing forced, on any plan
    wr = store.rights(USER)
    assert wr["premium"] and not wr["forced"] and {"none", "custom"} <= set(wr["modes"])
    assert launch(launcher, target_minutes=0.5, watermark={"mode": "custom"})["statusCode"] == 202
    flags.put_item(Item={"user_id": OTHER, "unlimited": True})                               # a staff account: the rights of Max
    wr = store.rights(OTHER)
    assert wr["plan"] == "max" and wr["premium"] and not wr["forced"]
    put_logo(plans_on, OTHER)
    assert launch(launcher, user=OTHER, target_minutes=12, watermark={"mode": "custom"}, platform=None)["statusCode"] == 202    # 12 minutes, from the web, never charged
    assert plans_on.ddb.Table("Videos").get_item(Key={"video_id": started(launcher)["video_id"]})["Item"]["plan"] == "test"


def test_watermark_settings_api_follows_the_plan(plans_on):
    import watermark_api

    def put(user, body):
        ev = app_event(user=user, body=body, resource="/users/{user_id}/watermark", method="PUT")
        return watermark_api.handler(ev, None)
    r = put(USER, {"mode": "none"})
    assert r["statusCode"] == 403 and body_of(r)["code"] == "watermark_required" and body_of(r)["requires_plan"] == "pro"
    assert body_of(put(USER, {"mode": "custom"}))["requires_plan"] == "max"
    give_plan(USER, "pro")
    assert put(USER, {"mode": "none"})["statusCode"] == 200
    caps = body_of(put(USER, {"mode": "videomk"}))["capabilities"]
    by = {m["id"]: m for m in caps["modes"]}
    assert by["none"]["available"] and not by["custom"]["available"] and by["custom"]["requires_plan"] == "max" and not caps["forced"]


def test_storage_quota_comes_from_the_plan_and_keeps_admin_add_ons(plans_on):
    assert library.limits(USER) == {"plan": "free", "limit_bytes": 2 * library.GB}
    give_plan(USER, "pro")
    assert library.limits(USER) == {"plan": "pro", "limit_bytes": 100 * library.GB}
    give_plan(USER, "max")
    assert library.limits(USER) == {"plan": "max", "limit_bytes": 300 * library.GB}
    library.set_storage(USER, "free", extra_gb=50)
    assert library.limits(USER)["limit_bytes"] == 350 * library.GB                           # an admin's extra GB still add up
    give_plan(USER, "free")
    assert library.limits(USER) == {"plan": "free", "limit_bytes": 52 * library.GB}          # the plan ended: nothing is deleted, the quota is Free's again (uploads stop until under it)
    library.set_storage(OTHER, "pro")
    assert library.limits(OTHER) == {"plan": "pro", "limit_bytes": 100 * library.GB}         # the older storage flag is still honoured
    plans_on.ddb.Table("Flags").put_item(Item={"user_id": "77777777-aaaa-bbbb-cccc-222222222222", "unlimited": True})
    assert library.limits("77777777-aaaa-bbbb-cccc-222222222222")["limit_bytes"] == 300 * library.GB


# ======================================================================== the API
def caps(user=USER, **kw):
    return body_of(capabilities_api.handler(app_event(user=user, **kw), None))


def test_capabilities_say_the_plan_what_is_locked_and_that_upgrading_cannot_be_bought_yet(plans_on, monkeypatch):
    monkeypatch.setenv("READY_RESOLUTIONS", "720p,1080p,2160p")
    c = caps()
    assert c["plan"]["id"] == "free" and c["can_upgrade"] is False and c["plan"]["can_upgrade"] is False
    assert c["plan"]["limits"]["max_seconds"] == 30 and c["plan"]["limits"]["storage_bytes"] == 2 * plans.GB and c["plan"]["limits"]["watermark_forced"]
    res = {r["id"]: r for r in c["resolutions"]}
    assert res["2160p"]["available"] is False and res["2160p"]["requires_plan"] == "max" and res["1080p"]["available"] is True and res["1080p"]["requires_plan"] is None
    assert c["lengths"]["max_minutes"] == 12 and c["lengths"]["plan_max_seconds"] == 30 and [x["requires_plan"] for x in c["lengths"]["locked"]] == ["pro", "max"]   # every length stays listed: locked ones get a badge
    assert c["max_photos"] == 100 and c["plan_max_photos"] == 10
    assert [(p["id"], p["limits"]["credits_per_month"]) for p in c["plan"]["plans"]] == [("free", 0), ("pro", 30), ("max", 120)]
    assert c["plan"]["plans"][2]["products"]["apple"]["monthly"] == "com.videomk.app.max.monthly" and c["plan"]["plans"][1]["price_usd"] == {"monthly": 14.99, "yearly": 149.99}
    wm = {m["id"]: m for m in c["watermark"]["modes"]}
    assert c["watermark"]["forced"] and not wm["none"]["available"] and wm["none"]["requires_plan"] == "pro" and wm["custom"]["requires_plan"] == "max"
    give_plan(USER, "max", until=int(__import__("time").time()) + 30 * DAY, renews=True, source="apple")
    c = caps()
    assert c["plan"]["id"] == "max" and c["plan"]["managed_by"] == "apple" and c["plan"]["renews"] and c["plan"]["period_end"].endswith("Z") and c["plan"]["locked"] == []
    assert {r["id"]: r["available"] for r in c["resolutions"]}["2160p"] is True and c["plan_max_photos"] == 60 and c["lengths"]["plan_max_seconds"] == 720
    assert not c["watermark"]["forced"] and all(m["available"] for m in c["watermark"]["modes"])


def test_capabilities_never_grant_anything(plans_on):
    caps()
    assert plans_on.ddb.Table("Wallet").scan()["Items"] == [] and plans_on.ddb.Table("FreeClaims").scan()["Items"] == []


def test_capabilities_survive_a_plan_read_failure(plans_on, monkeypatch):
    monkeypatch.setattr(wallet, "_balance_plans", lambda *a, **k: 1 / 0)
    c = caps()
    assert "aspects" in c and "plan" not in c


def test_the_wallet_shows_the_plan_and_its_credits(plans_on):
    give_plan(USER, "pro")
    w = body_of(wallet_api.handler(app_event(resource="/users/{user_id}/wallet", method="GET"), None))
    assert w["plan"]["id"] == "pro" and w["plan"]["plan_credits"] == 30 and w["plan"]["limits"]["credits_per_month"] == 30 and w["can_upgrade"] is False
    assert {b["kind"]: b["remaining"] for b in w["buckets"]} == {"plan": 30, "signup": 5} and w["balance"] == 35
    assert [x["requires_plan"] for x in w["plan"]["locked"] if x["feature"] == "resolution"] == ["max"]
    assert w["rules"]["signup"] == 5 and w["rules"]["daily"] == 0 and w["next_free_credit_at"] is None


def test_the_plan_route_and_the_purchase_stubs(plans_on):
    def call(resource, method="GET", user=USER, path_user=None, authed=True):
        ev = app_event(user=user, resource=resource, method=method)
        if path_user:
            ev["pathParameters"] = {"user_id": path_user}
        if not authed:
            ev["requestContext"] = {}
        return plans_api.handler(ev, None)
    give_plan(USER, "pro")
    r = call("/users/{user_id}/plan")
    b = body_of(r)
    assert r["statusCode"] == 200 and b["plan"]["id"] == "pro" and b["can_upgrade"] is False and b["purchases"] == {"apple": False, "google": False, "web": False} and len(b["plans"]) == 3
    assert r["headers"]["Cache-Control"] == "no-store"
    for store_name in ("apple", "google"):
        r = call(f"/users/{{user_id}}/purchases/{store_name}", "POST")
        assert r["statusCode"] == 501 and body_of(r)["code"] == "purchases_unavailable" and body_of(r)["can_upgrade"] is False
    for hook in ("apple", "google", "web"):
        assert call(f"/purchases/webhooks/{hook}", "POST", authed=False)["statusCode"] == 501
    assert entitlements.get(USER)["plan"] == "pro"                                           # nothing changed anything
    # security: another person's plan is unreadable, and nobody is told anything without a token
    assert call("/users/{user_id}/plan", path_user=OTHER)["statusCode"] == 403
    assert call("/users/{user_id}/purchases/apple", "POST", path_user=OTHER)["statusCode"] == 403
    assert call("/users/{user_id}/plan", authed=False)["statusCode"] == 401
    assert body_of(call("/users/{user_id}/plan", user=OTHER))["plan"]["id"] == "free"        # OTHER sees their own plan, not USER's


def test_a_person_cannot_change_their_own_plan_through_any_request(launcher, plans_on):
    """The body, the headers and the options of every route are ignored for the plan: only the record decides."""
    evil = {"plan": "max", "entitlement": {"plan": "max"}, "state": "active", "source": "admin"}
    for handler, ev in ((plans_api.handler, app_event(body=evil, resource="/users/{user_id}/plan", method="GET", headers={"X-Plan": "max"})),
                        (plans_api.handler, app_event(body=evil, resource="/users/{user_id}/purchases/apple", method="POST")),
                        (wallet_api.handler, app_event(body=evil, headers={"X-Plan": "max"})), (capabilities_api.handler, app_event(body=evil))):
        handler(ev, None)
    r = launcher.handler(app_event(body={"prompt": PROMPT, "target_minutes": 3, **evil}), None)
    assert r["statusCode"] == 403 and body_of(r)["code"] == "plan_length"
    assert entitlements.get(USER) is None and plans_on.ddb.Table("Entitlements").scan()["Items"] == []


def test_no_request_handler_can_write_an_entitlement():
    """The writers (set_plan, set_state, delete) are for the admin script, the deletion worker and phase 2's purchase functions. A handler that calls one fails this test."""
    root = os.path.join(os.path.dirname(__file__), "..", "lambdas")
    allowed = {os.path.join("common", "entitlements.py"), os.path.join("common", "deletion.py")}
    pattern = re.compile(r"entitlements\.(set_plan|set_state|delete|table)\(|set_unlimited\(")
    offenders = []
    for folder, _, files in os.walk(root):
        for f in files:
            rel = os.path.relpath(os.path.join(folder, f), root)
            if f.endswith(".py") and rel not in allowed and rel != os.path.join("common", "wallet.py"):
                if pattern.search(open(os.path.join(folder, f), encoding="utf-8").read()):
                    offenders.append(rel)
    assert offenders == []
    assert "ENTITLEMENTS_TABLE" in open(os.path.join(root, "common", "deletion.py"), encoding="utf-8").read()


def test_account_deletion_removes_the_plan_record(plans_on, monkeypatch):
    give_plan(USER, "pro")
    give_plan(OTHER, "max")
    deletion.set_client("ddb", plans_on.ddb)
    try:
        deletion.step_flags(USER, deletion.Budget())
    finally:
        deletion._cache.pop("ddb", None)
    assert entitlements.get(USER) is None and entitlements.get(OTHER)["plan"] == "max"
    assert {"freemonth:", "devch:"} <= set(deletion.USAGE_PREFIXES)


def test_with_plans_off_nothing_changes(launcher, aws, monkeypatch):
    monkeypatch.delenv("PLANS_ENABLED", raising=False)
    monkeypatch.setenv("DAILY_VIDEO_LIMIT", "100")
    r = launcher.handler(_event(body={"prompt": PROMPT, "target_minutes": 3}), None)
    assert r["statusCode"] == 202
    b = wallet.balance("u1")
    assert "plan" not in b and "free" not in b and b["balance"] == 2 and b["rules"]["signup"] == 5
    row = aws.Table("Videos").scan()["Items"][0]
    assert "plan" not in row and "free_credits" not in row
    assert "plan" not in body_of(capabilities_api.handler(_event(), None))
    assert plans_api.handler({**_event(), "resource": "/users/{user_id}/plan"}, None)["statusCode"] == 404
