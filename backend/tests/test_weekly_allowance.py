"""R178 weekly allowance (docs/WEEKLY_ALLOWANCE_2026-11-28.md, docs/CREDITS.md): Free = 4 credits per 7-day window counted from the signup day (UTC), not carried;
paid bundles released weekly (exact monthly total, remainder in week 4, catch-up for a wallet first read mid-cycle); idempotent under concurrency; switchable back."""
import threading

import pytest

import capabilities_api
import wallet_api  # noqa: F401
from common import entitlements, free_grants, plans, wallet
from tests.test_hardening import launcher  # noqa: F401
from tests.test_plans import DAY, OTHER, T0, USER, app_event, body_of, give_plan, plans_on  # noqa: F401

WEEK = 7 * DAY
SIGNUP_DAY = int(T0 // DAY) * DAY   # 2027-01-15 00:00 UTC (a Friday)
ON = {"weekly_allowance": True, "plan_weekly_release": True, "welcome_credits": 5, "free_weekly_credits": 4}


def ctx(email="ana@example.org"):
    return {"platform": "ios", "ip": "203.0.113.7", "email": email, "email_verified": True, "federated": None}


def kinds(user, now, tz=None, **c):
    return {b["kind"]: b["remaining"] for b in wallet.balance(user, now=now, tz=tz, ctx=ctx(**c))["buckets"]}


@pytest.fixture
def weekly(plans_on):
    plans.set_config(dict({"free_web": True, "require_device_proof": False, "free_daily_budget_credits": 1000}, **ON))
    return plans_on


def pc(user, now):
    return sum(b["remaining"] for b in wallet.balance(user, now=now)["buckets"] if b["kind"] == "plan")


# ------------------------------------------------------------------ Free
def test_signup_gets_five_welcome_credits_and_the_first_allowance_comes_a_week_later(weekly):
    assert kinds(USER, T0) == {"signup": 5}
    assert kinds(USER, T0 + 6 * DAY) == {"signup": 5}                       # still the signup week
    w = wallet.balance(USER, now=T0 + DAY, ctx=ctx())
    assert w["next_renewal_at"] == "2027-01-22T00:00:00Z" and w["renews_on"] == "2027-01-22" and w["next_free_credits"] == 4 and w["free_creation"] == "weekly"
    assert w["plan"]["allowance"]["renews_on"] == "2027-01-22" and w["rules"]["signup"] == 5
    assert w["plan"]["limits"]["watermark_forced"] is True and w["plan"]["limits"]["max_seconds"] == 30 and w["free"]["mode"] == "weekly"


def test_week_rollover_unused_credits_are_not_carried(weekly):
    kinds(USER, T0)
    w1 = SIGNUP_DAY + WEEK
    assert kinds(USER, w1 - 1) == {"signup": 5}                             # one second before the boundary
    assert kinds(USER, w1) == {"signup": 5, "weekly": 4}                     # exactly at it
    assert kinds(USER, w1 + 3 * DAY)["weekly"] == 4                          # reading again grants nothing
    wallet.charge(USER, 1, now=w1 + DAY, ctx=ctx())                          # soonest-expiring first: the weekly credit is used before the welcome ones
    assert kinds(USER, w1 + 2 * DAY) == {"signup": 5, "weekly": 3}
    w2 = SIGNUP_DAY + 2 * WEEK
    assert kinds(USER, w2 - 1)["weekly"] == 3
    assert kinds(USER, w2) == {"signup": 5, "weekly": 4}                     # 3 unused ended, a fresh 4 arrived: never 7
    assert wallet.balance(USER, now=w2, ctx=ctx())["next_renewal_at"] == "2027-02-05T00:00:00Z"


def test_a_missed_week_is_not_back_filled(weekly):
    kinds(USER, T0)
    assert kinds(USER, SIGNUP_DAY + 5 * WEEK + 60) == {"weekly": 4} or kinds(USER, SIGNUP_DAY + 5 * WEEK + 60).get("weekly") == 4
    held = [b for b in wallet.balance(USER, now=SIGNUP_DAY + 5 * WEEK + 60, ctx=ctx())["buckets"] if b["kind"] == "weekly"]
    assert len(held) == 1 and held[0]["remaining"] == 4


def test_boundaries_are_utc_whatever_the_timezone_and_daylight_saving(weekly):
    kinds(USER, T0, tz="America/Los_Angeles")
    w1 = SIGNUP_DAY + WEEK
    for tz in ("America/Los_Angeles", "Pacific/Auckland", "Asia/Kolkata", None):
        assert "weekly" not in kinds(USER, w1 - 1, tz=tz)
    assert kinds(USER, w1, tz="Pacific/Auckland")["weekly"] == 4
    assert kinds(USER, w1 + 3600, tz="America/Los_Angeles")["weekly"] == 4   # switching timezone neither repeats nor moves the window
    # a window that spans a US daylight-saving change (2027-03-14) is still exactly 7 x 86400 s
    other = "55555555-aaaa-bbbb-cccc-222222222222"
    t_dst = 1_805_000_000.0   # 2027-03-13 about 19:33 UTC
    k, s, e = free_grants.week_window({"signup_at": int(t_dst)}, t_dst + 7 * DAY)
    assert (k, e - s) == (1, WEEK)
    assert free_grants.week_window({"signup_at": int(T0)}, T0)[0] == 0 and other


def test_concurrent_reads_grant_a_window_once(weekly):
    kinds(USER, T0)
    now, out = SIGNUP_DAY + WEEK + 5, []
    ts = [threading.Thread(target=lambda: out.append(kinds(USER, now))) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert kinds(USER, now + 10)["weekly"] == 4 and all(o.get("weekly", 4) == 4 for o in out)
    assert len([b for b in wallet.balance(USER, now=now + 20, ctx=ctx())["buckets"] if b["kind"] == "weekly"]) == 1


def test_the_weekly_credit_is_a_free_credit_for_the_gates(weekly):
    kinds(USER, T0)
    now = SIGNUP_DAY + WEEK + 1
    kinds(USER, now)
    plans.set_config(dict({"free_web": False, "require_device_proof": False, "free_daily_budget_credits": 1000}, **ON))
    with pytest.raises(wallet.FreeNotAvailable):                              # from the web nothing free may be spent, weekly included
        wallet.charge(USER, 1, now=now + 5, ctx={**ctx(), "platform": "web"})
    assert "weekly" in free_grants.FREE_KINDS


def test_switching_the_knob_back_restores_the_daily_rules(weekly):
    kinds(USER, T0)
    plans.set_config(dict({"free_web": True, "require_device_proof": False, "free_daily_budget_credits": 1000, "welcome_credits": 5, "weekly_allowance": False, "free_daily_credits": 1}))
    assert kinds(USER, T0 + DAY) == {"daily": 1, "signup": 5}
    assert wallet.balance(USER, now=T0 + DAY, ctx=ctx())["free_creation"] == "daily"


def test_a_paid_account_gets_no_free_weekly_credit(weekly):
    give_plan(OTHER, "pro", now=T0)
    kinds(OTHER, T0, email="bea@example.org")
    assert "weekly" not in kinds(OTHER, SIGNUP_DAY + WEEK + 1, email="bea@example.org")


# ------------------------------------------------------------------ paid
def test_the_split_is_exact_with_the_remainder_in_week_four():
    assert wallet.tranches(30) == [7, 7, 7, 9] and wallet.tranches(120) == [30, 30, 30, 30] and wallet.tranches(1) == [0, 0, 0, 1]
    assert all(sum(wallet.tranches(n)) == n for n in range(0, 500))


def test_pro_is_released_weekly_and_the_month_adds_up_to_30(weekly):
    give_plan(USER, "pro", now=T0)
    seen = [pc(USER, T0 + j * WEEK + 60) for j in range(4)]
    assert seen == [7, 14, 21, 30]                                           # unused credits carry inside the month
    assert pc(USER, T0 + 3 * WEEK + 2 * DAY) == 30                            # idempotent
    nxt = entitlements.add_months(T0, 1)
    assert pc(USER, nxt - 60) == 30
    assert pc(USER, nxt + 60) == 7                                           # the unused 30 ended with the month, week 1 of the new one arrived
    w = wallet.balance(USER, now=T0 + 60)
    assert w["next_renewal_at"] == "2027-01-22T08:00:00Z" and w["next_release_credits"] == 7 and w["plan"]["allowance"]["release"] == "weekly"
    assert wallet.balance(USER, now=T0 + 3 * WEEK + 60)["next_release_credits"] == 7 and wallet.balance(USER, now=T0 + 3 * WEEK + 60)["next_renewal_at"] == "2027-02-15T08:00:00Z"


def test_max_weekly_with_rollover_and_cap(weekly):
    give_plan(USER, "max", now=T0)
    assert [pc(USER, T0 + j * WEEK + 60) for j in range(4)] == [30, 60, 90, 120]
    m1 = entitlements.add_months(T0, 1)
    assert pc(USER, m1 + 60) == 150                                           # month 0 lives one month longer (rollover) + 30 of month 1
    assert pc(USER, m1 + 3 * WEEK + 60) == 240                                # capped at 240, never 120 + 120 + ...
    assert pc(USER, entitlements.add_months(T0, 2) + 60) == 150               # month 0 ended; month 1 (120, rollover) + week 1 of month 2 (30)


def test_a_wallet_first_read_mid_cycle_gets_the_elapsed_weeks_at_once(weekly):
    give_plan(USER, "pro", now=T0, anchor=int(T0 - 15 * DAY))                # bought mid-cycle: the cycle began 15 days ago (weeks 0, 1 and 2 have begun)
    assert pc(USER, T0 + 60) == 21                                           # the pro-rated first release: 7 + 7 + 7
    assert pc(USER, T0 + 6 * DAY + 3600) == 30                               # week 4 starts on day 21 of the cycle: the 9 follow, total exact


def test_the_end_of_the_paid_period_stops_the_releases(weekly):
    give_plan(USER, "pro", until=int(T0 + 10 * DAY), now=T0)
    assert pc(USER, T0 + 9 * DAY) == 14                                      # weeks 0 and 1 began before the end
    assert pc(USER, T0 + 12 * DAY) == 0                                      # plan over: its credits go with it
    w = wallet.balance(USER, now=T0 + 9 * DAY)
    assert "next_renewal_at" not in w and w["plan"]["id"] == "pro"           # nothing is coming after the paid period, and no Free window is shown to a paid account


def test_concurrent_reads_release_a_week_once(weekly):
    give_plan(USER, "pro", now=T0)
    out = []
    ts = [threading.Thread(target=lambda: out.append(pc(USER, T0 + WEEK + 5))) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert pc(USER, T0 + WEEK + 60) == 14


def test_switching_release_back_to_monthly_never_double_grants(weekly):
    give_plan(USER, "pro", now=T0)
    assert pc(USER, T0 + WEEK + 60) == 14
    plans.set_config(dict({"free_web": True, "require_device_proof": False, "free_daily_budget_credits": 1000, "plan_weekly_release": False}))
    assert pc(USER, T0 + WEEK + 120) == 30                                   # the weeks not yet released arrive at once: month total is 30, not 44
    plans.set_config(dict({"free_web": True, "require_device_proof": False, "free_daily_budget_credits": 1000, "plan_weekly_release": True}))
    assert pc(USER, T0 + 3 * WEEK + 60) == 30                                # and switching on again grants nothing more this month


def test_the_monthly_knob_off_keeps_the_old_behaviour(weekly):
    plans.set_config({"free_web": True, "require_device_proof": False, "plan_weekly_release": False})
    give_plan(USER, "pro", now=T0)
    assert pc(USER, T0 + 60) == 30 and "next_release_credits" not in wallet.balance(USER, now=T0 + 60)


# ------------------------------------------------------------------ capabilities
def test_capabilities_and_unlimited_dictation_agree(weekly, monkeypatch):
    import dictation_api  # noqa: F401
    from common import dictation
    kinds(USER, T0)
    ev = app_event(user=USER, body={}, method="GET", resource="/users/{user_id}/capabilities")
    ev["pathParameters"] = {"user_id": USER}
    body = body_of(capabilities_api.handler(ev, None))
    assert body["free"]["mode"] == "weekly" and body["plan"]["id"] == "free"
    assert plans.unlimited_stt_seconds() == 7200
    ent = entitlements.evaluate(None, now=T0, unlimited=True)
    assert wallet._balance_plans.__name__ and ent["unlimited"]
    monkeypatch.setattr(wallet, "is_unlimited", lambda u: True)
    w = wallet.balance(USER, now=T0 + 1, ctx=ctx())
    assert w["plan"]["limits"]["stt_seconds_per_day"] == 7200 == dictation.plan_rights(USER)[1]["stt_seconds_per_day"]
    monkeypatch.setenv("UNLIMITED_DAILY_STT_SECONDS", "900")
    assert wallet.balance(USER, now=T0 + 2, ctx=ctx())["plan"]["limits"]["stt_seconds_per_day"] == 900 == dictation.plan_rights(USER)[1]["stt_seconds_per_day"]
