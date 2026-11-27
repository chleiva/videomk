"""The free plan's containment (docs/PLANS.md): the owner's knobs and their defaults, gallery-only mode, the global daily free budget, the monthly cap, the eligibility
step that keeps one free allowance per person (normalised email, sign-in identity, device, disposable domains, velocity), what is stored about a claim (a salted hash and
nothing else), device proofs (App Attest, Play Integrity verdicts), the showcase gallery and the admin report."""
import base64
import datetime
import hashlib
import json
import struct

import boto3
import pytest

import capabilities_api
import device_api
import gallery_api
import plan_gate
import wallet_api
from common import deletion, device_proof as dp, entitlements, free_grants, plan_report, plans, wallet
from tests.test_hardening import launcher  # noqa: F401  (the fixture)
from tests.test_plans import DAY, OTHER, PROMPT, T0, USER, app_event, body_of, give_plan, launch, plans_on, started  # noqa: F401

THIRD = "33333333-aaaa-bbbb-cccc-222222222222"


@pytest.fixture
def defaults(plans_on):
    """The real defaults (no knob set), on a stage that does not require a device proof (QA)."""
    plans.set_config({})
    return plans_on


def ctx(email="ana@example.org", ip="203.0.113.7", platform="ios", federated=None, verified=True):
    return {"platform": platform, "ip": ip, "email": email, "email_verified": verified, "federated": federated}


def kinds(user, now=T0, **c):
    return {b["kind"]: b["remaining"] for b in wallet.balance(user, now=now, ctx=ctx(**c))["buckets"]}


def free_of(user, now=T0, **c):
    return wallet.balance(user, now=now, ctx=ctx(**c))["free"]


def meta(p, user):
    return p.ddb.Table("Wallet").get_item(Key={"user_id": user, "sk": "META"}).get("Item") or {}


# ======================================================================== the knobs
def test_the_defaults_the_owner_approved():
    c = plans.clean_config({})
    assert (c["welcome_credits"], c["welcome_valid_days"], c["free_daily_credits"], c["free_max_seconds"], c["free_max_resolution"]) == (2, 30, 0, 30, "1080p")
    assert (c["free_daily_budget_credits"], c["cost_per_credit_usd"], c["free_budget_unlimited"], c["free_monthly_videos_cap"]) == (15, 0.15, False, 0)
    assert plans.usd(15, c) == 2.25 and round(plans.usd(15, c) * 31, 2) == 69.75           # about $2 a day, about $70 a month at the very worst
    assert (c["free_web"], c["block_disposable_email"], c["device_proof_ios"], c["device_check_ios"], c["device_proof_android"]) == (False, True, True, False, False)
    assert (c["claims_per_ip_day"], c["claims_per_ip_block_day"], c["signups_per_ip_hour"], c["claim_retention_days"], c["enforce"]) == (3, 10, 5, 730, True)
    assert set(c) == set(plans.KNOBS)


def test_device_proof_is_required_by_default_in_production_only(monkeypatch):
    monkeypatch.setenv("PLANS_REQUIRE_DEVICE_PROOF_DEFAULT", "1")
    assert plans.clean_config({})["require_device_proof"] is True
    monkeypatch.setenv("PLANS_REQUIRE_DEVICE_PROOF_DEFAULT", "0")
    assert plans.clean_config({})["require_device_proof"] is False
    assert plans.clean_config({"require_device_proof": True})["require_device_proof"] is True   # the knob wins over the stage default
    monkeypatch.delenv("PLANS_REQUIRE_DEVICE_PROOF_DEFAULT")
    assert plans.clean_config({})["require_device_proof"] is True                               # nothing set: the strict answer


def test_a_bad_knob_falls_back_to_its_default_and_the_others_still_apply():
    c = plans.clean_config({"free_max_seconds": "long", "welcome_credits": 999, "free_max_resolution": "8K", "free_credit_cadence": "hourly", "free_daily_credits": 1,
                            "email_domain_deny": "Bad.Example  spam.test", "unknown_knob": 1, "enforce": "off", "free_daily_budget_credits": 2.5})
    assert (c["free_max_seconds"], c["welcome_credits"], c["free_max_resolution"], c["free_credit_cadence"], c["free_daily_budget_credits"]) == (30, 2, "1080p", "daily", 15)
    assert c["free_daily_credits"] == 1 and c["email_domain_deny"] == ["bad.example", "spam.test"] and c["enforce"] is False and "unknown_knob" not in c
    assert plans.clean_config("not a dict")["welcome_credits"] == 2
    for name, bad in (("free_max_seconds", 5), ("welcome_credits", -1), ("free_web", "maybe"), ("email_domain_allow", ["a@b.com"])):
        with pytest.raises(ValueError):
            plans._coerce(name, bad)


def test_the_knobs_are_read_from_one_parameter_with_a_short_cache_and_survive_a_read_failure(aws, monkeypatch):
    ssm = boto3.client("ssm", region_name="us-west-2")
    ssm.put_parameter(Name="/videomk/qa/plans/config", Value=json.dumps({"welcome_credits": 4}), Type="String")
    monkeypatch.setenv("PLANS_CONFIG_PARAM", "/videomk/qa/plans/config")
    monkeypatch.setattr(plans, "_ssm", ssm)
    plans.set_config(None)
    assert plans.config(now=1000.0)["welcome_credits"] == 4
    ssm.put_parameter(Name="/videomk/qa/plans/config", Value=json.dumps({"welcome_credits": 0, "free_daily_credits": 1}), Type="String", Overwrite=True)
    assert plans.config(now=1030.0)["welcome_credits"] == 4                                   # within the minute: the cached value
    c = plans.config(now=1061.0)
    assert (c["welcome_credits"], c["free_daily_credits"]) == (0, 1)                           # no deploy: the next read after the cache picks it up
    ssm.put_parameter(Name="/videomk/qa/plans/config", Value="{broken", Type="String", Overwrite=True)
    assert plans.config(now=1200.0)["welcome_credits"] == 0                                   # unreadable: the last good values stay
    ssm.delete_parameter(Name="/videomk/qa/plans/config")
    c = plans.config(now=1400.0)
    assert (c["welcome_credits"], c["free_daily_credits"]) == (2, 0)                           # no parameter (never set, or removed): every default, and no error


# ======================================================================== the default free plan: 2 welcome credits from the app, no daily credit
def test_a_new_account_on_the_app_gets_two_welcome_credits_once_and_no_daily_credit(defaults):
    assert kinds(USER) == {"signup": 2}
    assert kinds(USER, T0 + 3600) == {"signup": 2}
    assert kinds(USER, T0 + 3 * DAY) == {"signup": 2}                                          # the daily free credit is off by default
    w = wallet.balance(USER, now=T0 + DAY, ctx=ctx())
    assert w["free_creation"] == "welcome" and w["next_free_credit_at"] is None and w["next_free_credits"] == 0 and w["rules"]["daily"] == 0 and w["rules"]["signup"] == 2
    assert w["free"] == {"mode": "welcome", "credits_left": 2, "max_seconds": 30, "budget_paused": False, "resumes_at": None, "available": True, "reason": None, "pending": False}
    assert kinds(USER, T0 + 31 * DAY) == {}                                                    # valid 30 days
    assert free_of(USER, T0 + 31 * DAY)["reason"] == "used"
    assert meta(defaults, USER)["welcome_state"] == "granted"


def test_the_welcome_knobs(defaults):
    plans.set_config({"welcome_credits": 3, "welcome_valid_days": 7})
    b = wallet.balance(USER, now=T0, ctx=ctx())["buckets"]
    assert [(x["kind"], x["remaining"], x["expires_at"]) for x in b] == [("signup", 3, int(T0 + 7 * DAY))]


def test_the_web_neither_grants_nor_spends_free_credits(launcher, defaults):
    w = wallet.balance(USER, now=T0, ctx=ctx(platform="web"))
    assert w["buckets"] == [] and w["balance"] == 0 and w["free"]["available"] is False and w["free"]["reason"] == "app_only" and w["free_creation"] == "welcome"
    assert meta(defaults, USER)["welcome_state"] == "pending"                                  # not lost: the first visit from the app grants it
    assert kinds(USER, T0 + 60) == {"signup": 2}
    web = wallet.balance(USER, now=T0 + 120, ctx=ctx(platform="web"))
    assert web["balance"] == 0 and web["free"]["credits_left"] == 2 and web["free"]["reason"] == "app_only"   # the web shows them as not spendable here
    wallet.balance(USER, ctx=ctx())                                                            # (real clock for the launcher below)
    r = launch(launcher, target_minutes=0.5, platform=None)
    b = body_of(r)
    assert r["statusCode"] == 403 and b["code"] == "free_not_available" and b["reason"] == "app_only" and "app" in b["message"] and launcher.fake.calls == []
    assert launch(launcher, target_minutes=0.5, platform="android")["statusCode"] == 202
    plans.set_config({"free_web": True})                                                       # the knob opens it
    assert launch(launcher, target_minutes=0.5, platform=None)["statusCode"] == 202


def test_a_paid_plan_is_not_touched_by_the_free_gates(launcher, defaults):
    give_plan(USER, "pro")
    plans.set_config({"free_daily_budget_credits": 0, "require_device_proof": True})           # every free gate closed
    r = launch(launcher, target_minutes=3, platform=None)                                      # from the web, no device proof, no budget
    assert r["statusCode"] == 202
    row = defaults.ddb.Table("Videos").scan()["Items"][0]
    assert row["plan"] == "pro" and int(row["free_credits"]) == 0 and int(row["credits_charged"]) == 3
    w = body_of(wallet_api.handler(app_event(platform=None, resource="/users/{user_id}/wallet", method="GET"), None))
    assert w["plan"]["plan_credits"] == 27 and w["free"]["available"] is True


# ======================================================================== gallery-only mode
def test_capabilities_before_the_first_wallet_read_do_not_claim_or_mislead(defaults):
    c = body_of(capabilities_api.handler(app_event(), None))["free"]
    assert c["available"] is True and c["pending"] is True and c["credits_left"] == 0 and c["reason"] is None     # nothing tried yet: the wallet read settles it
    assert defaults.ddb.Table("Wallet").scan()["Items"] == []
    assert body_of(capabilities_api.handler(app_event(platform=None), None))["free"]["reason"] == "app_only"
    w = body_of(wallet_api.handler(app_event(resource="/users/{user_id}/wallet", method="GET"), None))["free"]
    assert w["credits_left"] == 2 and w["pending"] is False and w["available"] is True
    c = body_of(capabilities_api.handler(app_event(), None))["free"]
    assert c["credits_left"] == 2 and c["pending"] is False


def test_gallery_only_mode_is_a_complete_state(launcher, defaults):
    plans.set_config({"welcome_credits": 0})                                                   # no welcome credits, daily off: Free can watch, not create
    w = body_of(wallet_api.handler(app_event(resource="/users/{user_id}/wallet", method="GET"), None))
    assert w["free_creation"] == "none" and w["balance"] == 0 and w["buckets"] == []
    assert w["free"]["available"] is False and w["free"]["reason"] == "off" and w["free"]["credits_left"] == 0 and w["free"]["budget_paused"] is False
    assert w["free"]["message"] == "Creating videos needs a plan. Watch what videomk makes in the gallery."
    assert w["plan"]["id"] == "free" and w["can_upgrade"] is False and w["next_free_credit_at"] is None
    c = body_of(capabilities_api.handler(app_event(headers={"X-Locale": "es"}), None))
    assert c["free_creation"] == "none" and c["free"]["reason"] == "off" and c["free"]["message"].startswith("Para crear videos necesitas un plan")
    assert c["plan"]["plans"][1]["id"] == "pro" and "aspects" in c                              # the paywall data and the options are all there: nothing is broken or empty
    r = launch(launcher, target_minutes=0.5)
    assert r["statusCode"] == 402 and body_of(r)["code"] == "insufficient_credits" and body_of(r)["plan"] == "free" and body_of(r)["can_upgrade"] is False
    assert defaults.ddb.Table("FreeClaims").scan()["Items"] == []                               # nothing was claimed, so switching the allowance on later still works
    plans.set_config({"welcome_credits": 2})
    assert kinds(USER, __import__("time").time()) == {"signup": 2}
    give_plan(OTHER, "pro")                                                                    # and a paying account creates as usual in gallery-only mode
    plans.set_config({"welcome_credits": 0})
    assert launch(launcher, user=OTHER, target_minutes=2, platform=None)["statusCode"] == 202


# ======================================================================== the global daily free budget
def test_the_budget_is_one_atomic_counter_for_all_accounts_and_resets_with_the_utc_day(defaults):
    cfg = plans.config()
    assert all(free_grants.budget_take(5, cfg, T0) for _ in range(3))                          # 15 of 15
    assert not free_grants.budget_take(1, cfg, T0)
    st = free_grants.budget_state(cfg, T0)
    assert st == {"limit_credits": 15, "limit_usd": 2.25, "resumes_at": "2027-01-16T00:00:00Z", "spent_credits": 15, "paused": True}
    assert free_grants.budget_take(1, cfg, T0 + 16 * 3600 + 1) and not free_grants.budget_state(cfg, T0 + 16 * 3600 + 1)["paused"]   # 00:00 UTC: a new day
    free_grants.budget_return(5, T0)
    assert free_grants.budget_take(5, cfg, T0) and not free_grants.budget_take(1, cfg, T0)     # a video that never started gave its share back
    assert not free_grants.budget_take(16, cfg, T0 + 5 * DAY)                                  # more than the whole budget never fits
    assert not free_grants.budget_take(1, {**cfg, "free_daily_budget_credits": 0}, T0 + 6 * DAY)   # 0 = no free creation at all
    assert free_grants.budget_take(500, {**cfg, "free_budget_unlimited": True}, T0 + 6 * DAY)


def test_concurrent_free_videos_cannot_overspend_the_budget(defaults):
    import threading
    cfg, got = plans.config(), []
    threads = [threading.Thread(target=lambda: got.append(free_grants.budget_take(1, cfg, T0))) for _ in range(40)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert got.count(True) == 15 and free_grants.budget_state(cfg, T0)["spent_credits"] == 15


def test_when_the_budget_is_spent_free_creation_pauses_with_a_clear_message_and_nothing_is_lost(launcher, defaults):
    plans.set_config({"free_daily_budget_credits": 3})
    users = [USER, OTHER, THIRD]
    for i, u in enumerate(users):                                                               # three accounts, each with 2 welcome credits
        assert launch(launcher, user=u, target_minutes=0.5, email=f"p{i}@example.org", ip=f"198.51.{i}.9")["statusCode"] == 202
    assert free_grants.budget_state(plans.config())["paused"] is True
    r = launch(launcher, user=USER, target_minutes=0.5, email="p0@example.org", ip="198.51.0.9")
    b = body_of(r)
    assert r["statusCode"] == 429 and b["code"] == "free_budget_spent" and b["reason"] == "paused" and b["requires_plan"] == "pro" and b["resumes_at"].endswith("T00:00:00Z")
    assert b["message"] == "Free videos are done for today. They are back tomorrow, or choose a plan to make yours now."
    es = body_of(launch(launcher, user=USER, target_minutes=0.5, email="p0@example.org", ip="198.51.0.9", headers={"X-Locale": "es"}))
    assert es["message"].startswith("Los videos gratis de hoy se terminaron")
    assert len(launcher.fake.calls) == 3
    w = body_of(wallet_api.handler(app_event(email="p0@example.org", ip="198.51.0.9", resource="/users/{user_id}/wallet", method="GET"), None))
    assert w["balance"] == 1 and w["free"]["credits_left"] == 1                                 # the welcome credit is still there: not lost, just not spendable until the reset
    assert w["free"]["available"] is False and w["free"]["reason"] == "paused" and w["free"]["budget_paused"] is True and w["free"]["resumes_at"].endswith("T00:00:00Z")
    c = body_of(capabilities_api.handler(app_event(email="p0@example.org", ip="198.51.0.9"), None))
    assert c["free"]["budget_paused"] is True and c["free"]["reason"] == "paused"
    give_plan(THIRD, "pro")                                                                    # paid plans are unaffected
    assert launch(launcher, user=THIRD, target_minutes=2, email="p2@example.org", ip="198.51.2.9")["statusCode"] == 202
    plans.set_config({"free_daily_budget_credits": 10})                                        # the owner raises the budget: free creation is back at once
    assert launch(launcher, user=USER, target_minutes=0.5, email="p0@example.org", ip="198.51.0.9")["statusCode"] == 202
    rows = {r["user_id"]: r for r in defaults.ddb.Table("Videos").scan()["Items"] if r["user_id"] == OTHER}
    assert rows[OTHER]["plan"] == "free" and int(rows[OTHER]["free_credits"]) == 1


def test_a_video_that_fails_to_start_gives_the_budget_back(launcher, defaults, monkeypatch):
    def boom(**kw):
        raise RuntimeError("no workflow")
    monkeypatch.setattr(launcher._sfn, "start_execution", boom)
    assert launch(launcher, target_minutes=0.5)["statusCode"] == 500
    assert free_grants.budget_state(plans.config())["spent_credits"] == 0
    assert wallet.balance(USER, ctx=ctx(email=f"{USER[:8]}@example.org"))["balance"] == 2


def test_the_monthly_cap_per_account(launcher, defaults):
    plans.set_config({"welcome_credits": 5, "free_monthly_videos_cap": 2})
    assert [launch(launcher, target_minutes=0.5)["statusCode"] for _ in range(2)] == [202, 202]
    r = launch(launcher, target_minutes=0.5)
    assert r["statusCode"] == 429 and body_of(r)["code"] == "free_monthly_cap" and body_of(r)["reason"] == "monthly_cap"
    w = wallet.balance(USER, ctx=free_grants.context(app_event()))
    assert w["balance"] == 3 and w["free"]["reason"] == "monthly_cap" and free_grants.budget_state(plans.config())["spent_credits"] == 2
    cfg = plans.config()
    assert not free_grants.monthly_take(USER, cfg) and free_grants.monthly_take(OTHER, cfg)    # per account
    feb = __import__("time").time() + 32 * DAY
    assert free_grants.monthly_take(USER, cfg, feb)                                            # and per calendar month


# ======================================================================== the recurring free credit (off by default)
def test_the_daily_credit_knob_and_its_weekly_cadence(defaults):
    plans.set_config({"free_daily_credits": 1})
    assert kinds(USER) == {"signup": 2}                                                        # the first day has none (the welcome credits cover it)
    assert kinds(USER, T0 + DAY) == {"daily": 1, "signup": 2}
    assert kinds(USER, T0 + DAY + 60) == {"daily": 1, "signup": 2}
    w = wallet.balance(USER, now=T0 + DAY + 60, ctx=ctx())
    assert w["free_creation"] == "daily" and w["next_free_credit_at"] == "2027-01-17T00:00:00Z" and w["next_free_credits"] == 1
    assert kinds(USER, T0 + 2 * DAY) == {"daily": 1, "signup": 2}                              # yesterday's ended, today's arrived
    assert "daily" not in kinds(USER, T0 + 3 * DAY, platform="web")                            # not from the web
    plans.set_config({"free_daily_credits": 1, "free_credit_cadence": "weekly", "free_credits_per_week": 2})
    got = ["daily" in kinds(OTHER, T0 + k * DAY, email="bea@example.org", ip="198.51.100.4") for k in range(0, 7)]   # T0 is a Friday
    #        Fri    Sat   Sun   | Mon   Tue   Wed    Thu
    assert got == [False, True, True, True, True, False, False]
    w = wallet.balance(OTHER, now=T0 + 6 * DAY, ctx=ctx(email="bea@example.org", ip="198.51.100.4"))
    assert w["next_free_credit_at"] == "2027-01-25T00:00:00Z"                                   # this week's two are used: the next one is on Monday
    got = ["daily" in kinds(OTHER, T0 + k * DAY, email="bea@example.org", ip="198.51.100.4") for k in range(7, 11)]
    #        Fri    Sat    Sun  | Mon
    assert got == [False, False, False, True]
    give_plan(THIRD, "pro", now=T0)
    assert "daily" not in kinds(THIRD, T0 + DAY, email="cy@example.org", ip="198.51.100.5")    # the recurring free credit is the Free plan's


# ======================================================================== one allowance per person
@pytest.mark.parametrize("a,b", [
    ("Ana.Perez@gmail.com", "anaperez@gmail.com"), ("ana.perez@gmail.com", "a.n.a.p.e.r.e.z+promo@googlemail.com"), ("ana@outlook.com", "ana+two@outlook.com"),
    ("ANA@Example.ORG ", "ana+x@example.org"),
])
def test_spellings_of_one_mailbox_are_one_person(defaults, a, b):
    assert free_grants.normalise_email(a) == free_grants.normalise_email(b)
    assert kinds(USER, email=a) == {"signup": 2}
    assert kinds(OTHER, email=b, ip="198.51.100.20") == {}                                     # the second account gets no allowance
    f = free_of(OTHER, email=b, ip="198.51.100.20")
    assert f["available"] is False and f["reason"] == "not_available"                          # ... and is not told why
    m = meta(defaults, OTHER)
    assert m["welcome_state"] == "denied" and m["free_refusal"] == "duplicate_email"
    assert kinds(OTHER, T0 + 40 * DAY, email="someone.else@example.org", ip="198.51.100.20") == {}   # final for that account


def test_different_people_on_one_domain_are_different_people(defaults):
    assert kinds(USER, email="ana@example.org") == {"signup": 2}
    assert kinds(OTHER, email="an.a@example.org", ip="198.51.100.20") == {"signup": 2}         # dots only mean nothing at Gmail


def test_the_sign_in_identity_is_claimed_too_so_a_new_address_does_not_reset_it(defaults):
    assert kinds(USER, email="ana@icloud.com", federated="signinwithapple_000123.abc") == {"signup": 2}
    assert kinds(OTHER, email="relay-xyz@privaterelay.appleid.com", federated="signinwithapple_000123.abc", ip="198.51.100.20") == {}
    assert meta(defaults, OTHER)["free_refusal"] == "duplicate_identity"
    assert kinds(THIRD, email="relay-abc@privaterelay.appleid.com", federated="signinwithapple_000999.zzz", ip="198.51.100.21") == {"signup": 2}


def test_the_token_is_the_only_source_of_identity(defaults):
    ev = app_event(email="ana@gmail.com", ip="203.0.113.50", body={"email": "other@gmail.com", "platform": "ios"}, headers={"X-Forwarded-For": "1.1.1.1", "X-Email": "x@y.zz"})
    ev["requestContext"]["authorizer"]["claims"].update({"cognito:username": "Google_1234567890", "identities": json.dumps([{"userId": "1234567890", "providerName": "Google"}])})
    c = free_grants.context(ev)
    assert c == {"platform": "ios", "ip": "203.0.113.50", "email": "ana@gmail.com", "email_verified": True, "federated": "google_1234567890"}
    ev["headers"].pop("X-Platform")
    assert free_grants.context(ev)["platform"] == "web"
    ev["headers"]["X-Platform"] = "windows"
    assert free_grants.context(ev)["platform"] == "web"
    ev["requestContext"]["authorizer"]["claims"].pop("cognito:username")
    assert free_grants.context(ev)["federated"] == "google_1234567890"                         # from the identities claim when the username is not there
    assert free_grants.context({})["email"] == "" and free_grants.context(None)["platform"] == "web"


def test_an_unverified_address_gets_no_allowance(defaults):
    assert kinds(USER, verified=False) == {} and meta(defaults, USER)["free_refusal"] == "identity"
    assert kinds(USER, T0 + 60, verified=True) == {"signup": 2}                                # once verified it does (the refusal was not final)


def test_what_is_stored_about_a_claim_is_a_salted_hash_and_nothing_else(defaults):
    kinds(USER, email="Ana.Perez+x@gmail.com", federated="google_1234567890", ip="203.0.113.99")
    rows = defaults.ddb.Table("FreeClaims").scan()["Items"]
    assert sorted(r["pk"][:2] for r in rows) == ["e#", "f#"]
    for r in rows:
        assert set(r) == {"pk", "kind", "day", "n", "ttl"} and r["day"] == "2027-01-15" and int(r["n"]) == 1
        assert int(r["ttl"]) == int(T0 + 730 * DAY) and len(r["pk"]) == 66 and all(ch in "0123456789abcdef" for ch in r["pk"][2:])
    dump = json.dumps(rows, default=str) + json.dumps(defaults.ddb.Table("Usage").scan()["Items"], default=str)
    for secret in (USER, "ana", "perez", "gmail", "1234567890", "203.0.113.99"):
        assert secret not in dump.lower()                                                       # no account id, no address, no identity, no full IP anywhere outside the wallet row
    assert "203.0.113.0/24" in dump                                                             # (the /24 block is kept for a few days so the report can name it)
    email_key = next(r["pk"] for r in rows if r["pk"].startswith("e#"))
    assert email_key == "e#" + deletion.mac("free:email", "anaperez@gmail.com")                 # keyed HMAC of the NORMALISED address ...
    assert email_key[2:] != hashlib.sha256(b"anaperez@gmail.com").hexdigest()                   # ... not a plain hash anyone could recompute
    deletion.set_key(b"another-stage-key-0123456789abcdef")
    assert "e#" + deletion.mac("free:email", "anaperez@gmail.com") != email_key                 # and useless without this stage's key
    deletion.set_key(b"k" * 32)


def test_deleting_and_recreating_the_account_does_not_reset_the_allowance(defaults):
    assert kinds(USER, email="ana@gmail.com") == {"signup": 2}
    deletion.set_client("ddb", defaults.ddb)
    try:
        deletion.step_wallet(USER, deletion.Budget())                                           # the account is deleted: its wallet rows go ...
    finally:
        deletion._cache.pop("ddb", None)
    assert defaults.ddb.Table("Wallet").scan()["Items"] == []
    assert len(defaults.ddb.Table("FreeClaims").scan()["Items"]) == 1                           # ... the claim (a hash, no account id) stays
    assert kinds(OTHER, T0 + 10 * DAY, email="a.n.a+again@gmail.com", ip="198.51.100.77") == {}  # the same person, a new account: no second allowance
    assert int(defaults.ddb.Table("FreeClaims").scan()["Items"][0]["n"]) == 2                   # the report's "accounts per identity"
    assert kinds(THIRD, T0 + 800 * DAY, email="ana@gmail.com", ip="198.51.100.78") == {"signup": 2}   # after the retention time the claim is gone for good


def test_no_key_no_allowance_fail_closed(defaults):
    deletion.set_key(None)                                                                      # (no DELETION_KEY_SECRET in this environment either)
    assert kinds(USER) == {} and meta(defaults, USER)["free_refusal"] == "internal"
    assert wallet.balance(USER, now=T0, ctx=ctx())["plan"]["id"] == "free"                      # the account itself keeps working
    deletion.set_key(b"k" * 32)


@pytest.mark.parametrize("email,knobs,granted", [
    ("x@mailinator.com", {}, False), ("x@sub.mailinator.com", {}, False), ("x@guerrillamail.com", {}, False), ("x@gmail.com", {}, True), ("x@privaterelay.appleid.com", {}, True),
    ("x@mailinator.com", {"email_domain_allow": ["mailinator.com"]}, True), ("x@mailinator.com", {"block_disposable_email": False}, True),
    ("x@corp.example", {"email_domain_deny": ["corp.example"]}, False), ("x@corp.example", {"email_domain_deny": ["corp.example"], "block_disposable_email": False}, False),
])
def test_disposable_domains_and_the_admin_lists(defaults, email, knobs, granted):
    plans.set_config(knobs)
    assert (kinds(USER, email=email) == {"signup": 2}) is granted
    if not granted:
        assert meta(defaults, USER)["free_refusal"] == "disposable" and meta(defaults, USER)["welcome_state"] == "pending"


def test_the_shipped_list_is_the_public_cc0_one():
    import os
    path = os.path.join(os.path.dirname(free_grants.__file__), "data", "disposable_email_domains.txt")
    head = open(path, encoding="utf-8").read(600)
    assert "CC0 1.0" in head and "disposable-email-domains" in head and "commit" in head
    d = free_grants.disposable_domains()
    assert len(d) > 5000 and "mailinator.com" in d and not {"gmail.com", "outlook.com", "icloud.com", "yahoo.com", "privaterelay.appleid.com", "hotmail.com", "proton.me"} & d


def test_velocity_per_address_and_per_block(defaults):
    def claim(i, ip):
        return kinds(f"{i:08d}-aaaa-bbbb-cccc-222222222222", email=f"person{i}@example.org", ip=ip) == {"signup": 2}
    assert [claim(i, "203.0.113.7") for i in range(4)] == [True, True, True, False]            # 3 allowances per address and day
    assert meta(defaults, f"{3:08d}-aaaa-bbbb-cccc-222222222222")["free_refusal"] == "ip"
    assert [claim(10 + i, f"203.0.113.{20 + i}") for i in range(8)] == [True] * 7 + [False]    # 10 per /24 and day (3 + 7)
    assert meta(defaults, f"{17:08d}-aaaa-bbbb-cccc-222222222222")["free_refusal"] == "ip_block"
    assert claim(30, "203.0.114.7")                                                             # the next block is not affected
    assert kinds(f"{3:08d}-aaaa-bbbb-cccc-222222222222", T0 + DAY, email="person3@example.org", ip="203.0.113.7") == {"signup": 2}   # a velocity refusal is not final: the next day works
    v6 = [claim(40 + i, f"2001:db8:aa:{i:x}::1") for i in range(11)]                           # IPv6: the /48
    assert v6 == [True] * 10 + [False] and free_grants.ip_block("2001:db8:aa:1::1") == "2001:db8:aa::/48" and free_grants.ip_block("203.0.113.9") == "203.0.113.0/24"
    plans.set_config({"claims_per_ip_day": 0, "claims_per_ip_block_day": 0})                    # 0 = no limit
    assert claim(60, "203.0.113.7")


def test_sign_ups_per_address_and_hour(defaults):
    def first_seen(i, now, ip="192.0.2.50"):
        return kinds(f"{i:08d}-aaaa-bbbb-cccc-222222222222", now, email=f"q{i}@example.org", ip=ip) == {"signup": 2}
    plans.set_config({"claims_per_ip_day": 0, "signups_per_ip_hour": 2})
    assert [first_seen(i, T0 + i) for i in range(4)] == [True, True, False, False]              # the third account first seen from this address within the hour
    assert meta(defaults, f"{2:08d}-aaaa-bbbb-cccc-222222222222")["free_refusal"] == "signup_velocity"
    assert first_seen(9, T0 + 10, ip="192.0.2.51")                                              # another address
    assert first_seen(2, T0 + 3 * 3600)                                                         # later it passes (not final)


def test_unlimited_test_accounts_bypass_every_rule(launcher, defaults):
    plans.set_config({"require_device_proof": True, "free_daily_budget_credits": 0, "claims_per_ip_day": 1, "welcome_credits": 2})
    defaults.ddb.Table("Flags").put_item(Item={"user_id": USER, "unlimited": True})
    w = wallet.balance(USER, now=T0, ctx=ctx(email="x@mailinator.com", platform="web", verified=False))
    assert w["unlimited"] and w["balance"] == wallet.UNLIMITED_DISPLAY and w["free"]["available"] is True and w["plan"]["id"] == "max" and w["plan"]["test_account"] is True
    assert defaults.ddb.Table("FreeClaims").scan()["Items"] == []                               # no claim is recorded for it
    assert launch(launcher, target_minutes=12, platform=None)["statusCode"] == 202
    assert free_grants.budget_state(plans.config())["spent_credits"] == 0


def test_an_account_from_before_plans_keeps_what_it_had_and_gets_no_second_welcome(defaults, monkeypatch):
    monkeypatch.delenv("PLANS_ENABLED")
    assert {b["kind"]: b["remaining"] for b in wallet.balance(USER, now=T0)["buckets"]} == {"signup": 5}   # the old rules: 5 welcome credits
    monkeypatch.setenv("PLANS_ENABLED", "1")
    assert kinds(USER, T0 + DAY) == {"signup": 5}                                               # plans go live: still its 5, no extra 2
    assert defaults.ddb.Table("FreeClaims").scan()["Items"] == [] and "welcome_state" not in meta(defaults, USER)
    assert free_of(USER, T0 + DAY)["available"] is True


def test_a_refusal_is_logged_and_counted_once_with_its_reason_and_never_shown(defaults, caplog, capsys):
    import logging
    caplog.set_level(logging.INFO)
    for k in range(3):
        f = free_of(USER, T0 + k, email="x@mailinator.com")
        assert f["reason"] == "not_available" and "disposable" not in json.dumps(f)
    lines = [r.getMessage() for r in caplog.records if "FREE_CLAIM" in r.getMessage()]
    assert lines == [f"FREE_CLAIM result=refused reason=disposable final=False user={USER}"]
    metrics = [json.loads(x) for x in capsys.readouterr().out.splitlines() if x.startswith('{"_aws"')]
    assert [(m["Reason"], m["FreeClaimRefused"]) for m in metrics if "FreeClaimRefused" in m] == [("disposable", 1)]
    assert metrics[0]["_aws"]["CloudWatchMetrics"][0]["Namespace"] == "videomk/Plans"
    kinds(OTHER, T0 + 10, email="ok@example.org")
    st = defaults.ddb.Table("Usage").get_item(Key={"user_id": "fstat", "day": "2027-01-15"})["Item"]
    assert int(st["refused_disposable"]) == 1 and int(st["granted"]) == 1


# ======================================================================== device proof required (production's default)
def test_with_device_proof_required_nothing_free_happens_without_one(launcher, defaults):
    plans.set_config({"require_device_proof": True})
    assert kinds(USER) == {} and meta(defaults, USER)["free_refusal"] == "no_device"
    f = free_of(USER, T0 + 60)
    assert f["available"] is False and f["reason"] == "not_available"
    t = defaults.ddb.Table("Wallet")
    t.update_item(Key={"user_id": USER, "sk": "META"}, UpdateExpression="SET device_pass_until = :u, device_ref = :r", ExpressionAttributeValues={":u": int(T0 + 900), ":r": "abc123"})
    assert kinds(USER, T0 + 120) == {"signup": 2}                                               # a verified proof (lambdas/device_api.py writes these two fields): granted
    assert {r["pk"][:2] for r in defaults.ddb.Table("FreeClaims").scan()["Items"]} == {"e#", "d#"}
    f = free_of(USER, T0 + 1000)
    assert f["credits_left"] == 2 and f["available"] is False and f["reason"] == "not_available"   # the pass ran out: the credits wait for the next proof
    with pytest.raises(wallet.FreeNotAvailable) as e:
        wallet.charge(USER, 1, now=T0 + 1000, ctx=ctx())
    assert e.value.reason == "no_device" and e.value.balance == 0
    # a second account on the same attested device key: no second allowance
    wallet.balance(OTHER, now=T0 + 200, ctx=ctx(email="other@example.org", ip="198.51.100.9"))
    t.update_item(Key={"user_id": OTHER, "sk": "META"}, UpdateExpression="SET device_pass_until = :u, device_ref = :r", ExpressionAttributeValues={":u": int(T0 + 900), ":r": "abc123"})
    assert kinds(OTHER, T0 + 300, email="other@example.org", ip="198.51.100.9") == {} and meta(defaults, OTHER)["free_refusal"] == "duplicate_device"
    # Apple's DeviceCheck bit / Google's device recall says the device was used before (survives reinstall)
    wallet.balance(THIRD, now=T0 + 200, ctx=ctx(email="third@example.org", ip="198.51.100.10"))
    t.update_item(Key={"user_id": THIRD, "sk": "META"}, UpdateExpression="SET device_pass_until = :u, device_claimed = :t", ExpressionAttributeValues={":u": int(T0 + 900), ":t": True})
    assert kinds(THIRD, T0 + 300, email="third@example.org", ip="198.51.100.10") == {} and meta(defaults, THIRD)["free_refusal"] == "duplicate_device"


# ---- App Attest: a complete fake Apple chain
def _attest_kit():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    now = datetime.datetime.now(datetime.timezone.utc)

    def cert(subject, issuer_name, pub, signer, ca, ext=None):
        b = (x509.CertificateBuilder().subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, subject)])).issuer_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_name)]))
             .public_key(pub).serial_number(x509.random_serial_number()).not_valid_before(now - datetime.timedelta(days=1)).not_valid_after(now + datetime.timedelta(days=30))
             .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True))
        if ext is not None:
            b = b.add_extension(x509.UnrecognizedExtension(x509.ObjectIdentifier(dp.NONCE_OID), ext), critical=False)
        return b.sign(signer, hashes.SHA384())
    root_key, mid_key = ec.generate_private_key(ec.SECP384R1()), ec.generate_private_key(ec.SECP384R1())
    root = cert("Test Root", "Test Root", root_key.public_key(), root_key, True)
    mid = cert("Test Intermediate", "Test Root", mid_key.public_key(), root_key, True)

    def make(app_id="39ANXJNUTL.com.videomk.app", challenge=b"challenge", aaguid=dp.AAGUID_PROD, counter=0, key=None, nonce_challenge=None):
        key = key or ec.generate_private_key(ec.SECP256R1())
        point = key.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        key_id = hashlib.sha256(point).digest()
        auth = hashlib.sha256(app_id.encode()).digest() + b"\x41" + struct.pack(">I", counter) + aaguid + struct.pack(">H", 32) + key_id + b"\xa0"
        nonce = hashlib.sha256(auth + hashlib.sha256(nonce_challenge or challenge).digest()).digest()
        leaf = cert("Leaf", "Test Intermediate", key.public_key(), mid_key, False, ext=b"\x30\x24\xa1\x22\x04\x20" + nonce)
        att = dp.cbor_encode({"fmt": "apple-appattest", "attStmt": {"x5c": [leaf.public_bytes(serialization.Encoding.DER), mid.public_bytes(serialization.Encoding.DER)], "receipt": b"r"}, "authData": auth})
        return key, key_id, att

    def assertion(key, client_data, counter, app_id="39ANXJNUTL.com.videomk.app"):
        auth = hashlib.sha256(app_id.encode()).digest() + b"\x01" + struct.pack(">I", counter)
        sig = key.sign(hashlib.sha256(auth + hashlib.sha256(client_data).digest()).digest(), ec.ECDSA(hashes.SHA256()))
        return dp.cbor_encode({"signature": sig, "authenticatorData": auth})
    return type("Kit", (), {"root_pem": root.public_bytes(serialization.Encoding.PEM), "make": staticmethod(make), "assertion": staticmethod(assertion)})()


@pytest.fixture
def kit():
    k = _attest_kit()
    dp.set_root(k.root_pem)
    yield k
    dp.set_root(None)


APP = ["39ANXJNUTL.com.videomk.app"]


def test_app_attest_attestation_and_assertions(kit):
    key, key_id, att = kit.make()
    got = dp.verify_attestation(att, key_id, b"challenge", APP, allow_development=False)
    assert got["counter"] == 0 and got["environment"] == "production" and "BEGIN PUBLIC KEY" in got["public_key_pem"]
    assert dp.verify_assertion(kit.assertion(key, b"c1", 1), b"c1", got["public_key_pem"], 0, APP) == 1
    assert dp.verify_assertion(kit.assertion(key, b"c2", 7), b"c2", got["public_key_pem"], 1, APP) == 7

    def refused(fn):
        with pytest.raises(dp.ProofError) as e:
            fn()
        return e.value.reason
    assert refused(lambda: dp.verify_assertion(kit.assertion(key, b"c1", 1), b"c1", got["public_key_pem"], 1, APP)) == "counter"      # a replay
    assert refused(lambda: dp.verify_assertion(kit.assertion(key, b"c1", 2), b"other", got["public_key_pem"], 1, APP)) == "signature"  # not over our challenge
    other, _, _ = kit.make()
    assert refused(lambda: dp.verify_assertion(kit.assertion(other, b"c3", 9), b"c3", got["public_key_pem"], 1, APP)) == "signature"   # another device's key
    assert refused(lambda: dp.verify_assertion(kit.assertion(key, b"c3", 9, app_id="EVIL.com.other"), b"c3", got["public_key_pem"], 1, APP)) == "app_id"
    assert refused(lambda: dp.verify_attestation(att, key_id, b"another challenge", APP, allow_development=False)) == "nonce"
    assert refused(lambda: dp.verify_attestation(att, b"x" * 32, b"challenge", APP, allow_development=False)) == "key_id"
    assert refused(lambda: dp.verify_attestation(att, key_id, b"challenge", ["TEAM.com.someone.else"], allow_development=False)) == "app_id"
    _, kid, dev = kit.make(aaguid=dp.AAGUID_DEV)
    assert refused(lambda: dp.verify_attestation(dev, kid, b"challenge", APP, allow_development=False)) == "environment"                # a development build is not production
    assert dp.verify_attestation(dev, kid, b"challenge", APP, allow_development=True)["environment"] == "development"
    _, kid, used = kit.make(counter=3)
    assert refused(lambda: dp.verify_attestation(used, kid, b"challenge", APP, allow_development=False)) == "counter"
    assert refused(lambda: dp.verify_attestation(b"\xa0", key_id, b"challenge", APP, allow_development=False)) == "format"
    assert refused(lambda: dp.verify_attestation(b"\xff\xff", key_id, b"challenge", APP, allow_development=False)) == "cbor"
    dp.set_root(None)                                                                             # against Apple's REAL root our home-made chain is worthless
    assert refused(lambda: dp.verify_attestation(att, key_id, b"challenge", APP, allow_development=False)) == "chain"


def test_apples_real_root_certificate_is_the_pinned_one():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    c = x509.load_pem_x509_certificate(dp.APPLE_APP_ATTEST_ROOT_PEM)
    assert "Apple App Attestation Root CA" in c.subject.rfc4514_string() and c.fingerprint(hashes.SHA256()).hex() == "1cb9823ba28ba6ad2d33a006941de2ae4f513ef1d4e831b9f7e0fa7b6242c932"


def test_cbor_round_trip_and_garbage():
    v = {"fmt": "apple-appattest", "attStmt": {"x5c": [b"a" * 300, b"b"], "n": 70000}, "authData": b"\x00" * 37}
    assert dp.cbor_decode(dp.cbor_encode(v)) == v
    for junk in (b"", b"\xbf", b"\x5a\xff\xff\xff\xff", b"\x9f\x01", b"\xf9\x00\x00"):
        with pytest.raises(dp.ProofError):
            dp.cbor_decode(junk)


def test_play_integrity_verdicts():
    now = 1_800_000_000

    def verdict(**over):
        v = {"requestDetails": {"requestPackageName": "com.videomk.app", "requestHash": "chal", "timestampMillis": str(now * 1000)},
             "appIntegrity": {"appRecognitionVerdict": "PLAY_RECOGNIZED"}, "deviceIntegrity": {"deviceRecognitionVerdict": ["MEETS_DEVICE_INTEGRITY"]}}
        for k, val in over.items():
            v[k] = {**v[k], **val}
        return v
    assert dp.check_play_verdict(verdict(), "com.videomk.app", "chal", now=now + 5) == {"device_claimed": False}
    assert dp.check_play_verdict(verdict(deviceIntegrity={"deviceRecall": {"values": {"bitFirst": True}}}), "com.videomk.app", "chal", now=now)["device_claimed"] is True
    for bad, reason in ((verdict(requestDetails={"requestPackageName": "com.evil"}), "package"), (verdict(requestDetails={"requestHash": "other"}), "nonce"),
                        (verdict(requestDetails={"timestampMillis": str((now - 3600) * 1000)}), "timestamp"), (verdict(appIntegrity={"appRecognitionVerdict": "UNRECOGNIZED_VERSION"}), "app"),
                        (verdict(deviceIntegrity={"deviceRecognitionVerdict": ["MEETS_BASIC_INTEGRITY"]}), "device"), (verdict(deviceIntegrity={"deviceRecognitionVerdict": []}), "device")):
        with pytest.raises(dp.ProofError) as e:
            dp.check_play_verdict(bad, "com.videomk.app", "chal", now=now)
        assert e.value.reason == reason


def test_play_integrity_and_devicecheck_calls_are_shaped_for_google_and_apple(monkeypatch):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec, rsa
    calls = []

    def fake(url, body, headers, form=False):
        calls.append((url, body, headers, form))
        if "oauth2" in url:
            return {"access_token": "tok"}
        if "decodeIntegrityToken" in url:
            return {"tokenPayloadExternal": {"requestDetails": {"requestPackageName": "com.videomk.app"}}}
        if "query_two_bits" in url:
            return {"bit0": True, "bit1": False}
        return {}
    monkeypatch.setattr(dp, "http_json", fake)
    pem = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    sa = {"client_email": "svc@project.iam.gserviceaccount.com", "private_key": pem}
    assert dp.play_decode("T" * 60, "com.videomk.app", sa)["requestDetails"]["requestPackageName"] == "com.videomk.app"
    assert calls[0][0] == "https://oauth2.googleapis.com/token" and calls[0][3] is True and calls[0][1]["assertion"].count(".") == 2
    assert calls[1][0] == "https://playintegrity.googleapis.com/v1/com.videomk.app:decodeIntegrityToken" and calls[1][2] == {"Authorization": "Bearer tok"}
    dp.play_recall_write("T" * 60, "com.videomk.app", sa)
    assert calls[-1][0].endswith("/com.videomk.app/deviceRecall:write") and calls[-1][1]["newValues"] == {"bitFirst": True}
    p8 = ec.generate_private_key(ec.SECP256R1()).private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    creds = {"team_id": "39ANXJNUTL", "key_id": "KEY1234567", "private_key": p8}
    assert dp.devicecheck_bits("devtoken", creds) == {"bit0": True, "bit1": False}
    assert calls[-1][0] == "https://api.devicecheck.apple.com/v1/query_two_bits" and calls[-1][2]["Authorization"].startswith("Bearer ey")
    head = json.loads(base64.urlsafe_b64decode(calls[-1][2]["Authorization"].split(" ")[1].split(".")[0] + "=="))
    assert head == {"alg": "ES256", "kid": "KEY1234567"}
    dp.devicecheck_set("devtoken", creds)
    assert calls[-1][0].endswith("/v1/update_two_bits") and calls[-1][1]["bit0"] is True


def dev_call(resource, body=None, user=USER, **kw):
    return device_api.handler(app_event(user=user, body=body or {}, resource=f"/users/{{user_id}}/device/{resource}", **kw), None)


def b64(b):
    return base64.b64encode(b).decode()


def test_the_device_route_grants_the_allowance_with_the_proof_in_hand(launcher, defaults, kit):
    plans.set_config({"require_device_proof": True})
    assert body_of(wallet_api.handler(app_event(resource="/users/{user_id}/wallet", method="GET"), None))["free"]["reason"] == "not_available"
    assert launch(launcher, target_minutes=0.5)["statusCode"] == 402                             # nothing to spend yet
    ch = body_of(dev_call("challenge"))
    assert len(base64.urlsafe_b64decode(ch["challenge"] + "=")) == 32 and ch["expires_in"] == 300
    key, key_id, att = kit.make(challenge=ch["challenge"].encode())
    r = dev_call("verify", {"platform": "ios", "challenge": ch["challenge"], "key_id": b64(key_id), "attestation": b64(att)})
    b = body_of(r)
    assert r["statusCode"] == 200 and b["verified"] is True and b["free"]["available"] is True and b["free"]["credits_left"] == 2 and b["valid_until"].endswith("Z")
    assert launch(launcher, target_minutes=0.5)["statusCode"] == 202                             # with the pass, the free video starts
    # the challenge is single use, and bound to the account
    assert dev_call("verify", {"platform": "ios", "challenge": ch["challenge"], "key_id": b64(key_id), "attestation": b64(att)})["statusCode"] == 403
    ch2 = body_of(dev_call("challenge"))["challenge"]
    stolen = dev_call("verify", {"platform": "ios", "challenge": ch2, "key_id": b64(key_id), "assertion": b64(kit.assertion(key, ch2.encode(), 1))}, user=OTHER, email="o@example.org")
    assert stolen["statusCode"] == 403 and body_of(stolen) == {"code": "device_not_verified", "message": "We could not verify this device."}   # never says which check failed
    # later: an assertion with the stored key renews the pass; the same assertion again is a replay
    ch3 = body_of(dev_call("challenge"))["challenge"]
    a = {"platform": "ios", "challenge": ch3, "key_id": b64(key_id), "assertion": b64(kit.assertion(key, ch3.encode(), 1))}
    assert dev_call("verify", a)["statusCode"] == 200
    ch4 = body_of(dev_call("challenge"))["challenge"]
    assert dev_call("verify", {**a, "challenge": ch4})["statusCode"] == 403
    rows = [r for r in defaults.ddb.Table("Wallet").scan()["Items"] if r["sk"].startswith("DEV#")]
    assert len(rows) == 1 and rows[0]["user_id"] == USER and int(rows[0]["counter"]) == 1         # the app key lives in the account's own rows (removed with the account)
    claims = defaults.ddb.Table("FreeClaims").scan()["Items"]
    assert sorted(c["pk"][:2] for c in claims) == ["d#", "e#"] and b64(key_id) not in json.dumps(claims, default=str)
    # the same key cannot claim for a second account (it is registered to the first), and garbage is refused quietly
    for bad in ({"platform": "ios"}, {"platform": "windows", "challenge": "x" * 43}, {"platform": "android", "challenge": body_of(dev_call("challenge"))["challenge"], "integrity_token": "t" * 80}):
        assert dev_call("verify", bad)["statusCode"] == 403                                       # (Play Integrity is behind its knob: off)
    assert dev_call("verify", {}, user=USER, headers={})["statusCode"] == 403
    ev = app_event(resource="/users/{user_id}/device/challenge")
    ev["pathParameters"] = {"user_id": OTHER}
    assert device_api.handler(ev, None)["statusCode"] == 403


def test_devicecheck_and_play_integrity_when_their_knobs_are_on(defaults, kit, monkeypatch):
    plans.set_config({"require_device_proof": True, "device_check_ios": True, "device_proof_android": True})
    marks = []
    monkeypatch.setattr(device_api, "_secret", lambda env: {"team_id": "T", "key_id": "K", "private_key": "x", "client_email": "e", "private_key_id": "x"})
    bits = {"bit0": False}
    monkeypatch.setattr(dp, "devicecheck_bits", lambda token, creds, now=None: {"bit0": bits["bit0"], "bit1": False})
    monkeypatch.setattr(dp, "devicecheck_set", lambda token, creds: marks.append(("apple", token)))

    def ios(user, email, dc="dc-token"):
        ch = body_of(dev_call("challenge", user=user, email=email))["challenge"]
        _, key_id, att = kit.make(challenge=ch.encode())
        body = {"platform": "ios", "challenge": ch, "key_id": b64(key_id), "attestation": b64(att), **({"device_check_token": dc} if dc else {})}
        return dev_call("verify", body, user=user, email=email, ip=f"198.51.100.{len(email)}")
    assert ios(USER, "one@example.org", dc=None)["statusCode"] == 403                            # the knob is on: the DeviceCheck token is required
    r = ios(USER, "one@example.org")
    assert body_of(r)["free"]["credits_left"] == 2 and marks == [("apple", "dc-token")]          # granted: the device is marked on Apple's side
    bits["bit0"] = True                                                                          # a new account, a NEW app key (reinstall), the same device
    r = ios(OTHER, "second@example.org")
    assert r["statusCode"] == 200 and body_of(r)["free"]["credits_left"] == 0 and body_of(r)["free"]["reason"] == "not_available"
    assert meta(defaults, OTHER)["free_refusal"] == "duplicate_device" and len(marks) == 1
    # Android: Google decodes the token; the recall bit plays DeviceCheck's part
    recall = {"on": False}
    monkeypatch.setattr(dp, "play_decode", lambda token, package, sa, now=None: {
        "requestDetails": {"requestPackageName": package, "requestHash": token.split("|")[1], "timestampMillis": str(int(__import__("time").time() * 1000))},
        "appIntegrity": {"appRecognitionVerdict": token.split("|")[0]}, "deviceIntegrity": {"deviceRecognitionVerdict": ["MEETS_DEVICE_INTEGRITY"], "deviceRecall": {"values": {"bitFirst": recall["on"]}}}})
    monkeypatch.setattr(dp, "play_recall_write", lambda token, package, sa: marks.append(("google", package)))

    def android(user, email, verdict="PLAY_RECOGNIZED"):
        ch = body_of(dev_call("challenge", user=user, email=email, platform="android"))["challenge"]
        return dev_call("verify", {"platform": "android", "challenge": ch, "integrity_token": f"{verdict}|{ch}|" + "p" * 60}, user=user, email=email, platform="android", ip="198.51.101.1")
    assert android(THIRD, "third@example.org", "UNRECOGNIZED_VERSION")["statusCode"] == 403       # a modified app
    r = android(THIRD, "third@example.org")
    assert body_of(r)["free"]["credits_left"] == 2 and marks[-1] == ("google", "com.videomk.app")
    recall["on"] = True
    fourth = "44444444-aaaa-bbbb-cccc-222222222222"
    assert body_of(android(fourth, "fourth@example.org"))["free"]["credits_left"] == 0 and meta(defaults, fourth)["free_refusal"] == "duplicate_device"


# ======================================================================== the gallery
@pytest.fixture
def showcase(aws, monkeypatch):
    monkeypatch.setenv("ASSETS_BUCKET", "assets-gallery")
    s3 = boto3.client("s3", region_name="us-west-2")
    s3.create_bucket(Bucket="assets-gallery", CreateBucketConfiguration={"LocationConstraint": "us-west-2"})
    gallery_api.set_client(s3)

    def put(videos):
        s3.put_object(Bucket="assets-gallery", Key="showcase/index.json", Body=json.dumps({"version": 1, "videos": videos}).encode())
    yield put
    gallery_api.set_client(None)


def gallery(headers=None):
    return gallery_api.handler({"headers": headers or {}, "resource": "/gallery", "httpMethod": "GET"}, None)


def test_the_gallery_is_public_lists_only_what_an_admin_marked_and_signs_only_showcase_files(showcase):
    assert body_of(gallery()) == {"videos": [], "count": 0, "expires_in": 3600}                  # no showcase yet: an empty list, not an error
    showcase([
        {"id": "forest", "title": {"en": "How a forest breathes", "es": "Cómo respira un bosque"}, "description": {"en": "Footage and a statistic.", "es": "Imágenes y una estadística."},
         "prompt": "A calm explainer about how a forest breathes", "aspect": "16:9", "width": 1280, "height": 720, "seconds": 28, "lang": "en",
         "video_key": "showcase/forest/video.mp4", "poster_key": "showcase/forest/poster.jpg"},
        {"id": "focus", "title": {"en": "3 quick tips to focus"}, "aspect": "9:16", "seconds": 30, "video_key": "showcase/focus/video.mp4"},
        {"id": "leak1", "title": {"en": "a customer's video"}, "video_key": "videos/some-user/abc/final.mp4"},            # a wrong entry can never expose a customer's file
        {"id": "leak2", "title": {"en": "x"}, "video_key": "showcase/../videos/u/final.mp4"},
        {"id": "leak3", "title": {"en": "x"}, "video_key": "showcase/index.json"},
        {"title": {"en": "no id"}, "video_key": "showcase/x/video.mp4"}, "junk",
    ])
    r = gallery()
    b = body_of(r)
    assert r["statusCode"] == 200 and [v["id"] for v in b["videos"]] == ["forest", "focus"] and b["count"] == 2
    f = b["videos"][0]
    assert f["title"] == "How a forest breathes" and f["title_i18n"]["es"] == "Cómo respira un bosque" and f["prompt"].startswith("A calm explainer") and f["description"] == "Footage and a statistic."
    assert (f["aspect"], f["shape"], f["width"], f["height"], f["seconds"], f["lang"]) == ("16:9", "wide", 1280, 720, 28, "en")
    assert "showcase/forest/video.mp4" in f["video_url"] and "ignature=" in f["video_url"] and "showcase/forest/poster.jpg" in f["poster_url"]
    v = b["videos"][1]
    assert (v["shape"], v["poster_url"], v["prompt"], v["title"]) == ("tall", None, None, "3 quick tips to focus")
    assert "videos/" not in json.dumps(b).replace("showcase/", "") and r["headers"]["Cache-Control"] == "public, max-age=300"
    es = body_of(gallery({"X-Locale": "es"}))
    assert es["videos"][0]["title"] == "Cómo respira un bosque" and es["videos"][0]["description"] == "Imágenes y una estadística." and es["videos"][1]["title"] == "3 quick tips to focus"
    assert set(f) == {"id", "title", "title_i18n", "description", "description_i18n", "prompt", "aspect", "shape", "width", "height", "seconds", "lang", "video_url", "poster_url"}


def test_the_gallery_needs_no_account_and_reads_no_account_data(showcase, monkeypatch):
    for k in ("VIDEOS_TABLE", "WALLET_TABLE", "FLAGS_TABLE", "USAGE_TABLE"):
        monkeypatch.delenv(k, raising=False)
    showcase([{"id": "a", "title": {"en": "A"}, "video_key": "showcase/a/video.mp4"}])
    assert body_of(gallery())["count"] == 1
    src = open(gallery_api.__file__, encoding="utf-8").read()
    assert "dynamodb" not in src and "extract_cognito_sub" not in src and "videos/" not in src.replace("{videos", "").replace('"videos"', "")


# ======================================================================== measurement
def test_the_report_separates_free_from_paid_and_prices_free_usage():
    rows = [
        {"video_id": "1", "user_id": "ana", "plan": "free", "free_credits": 1, "credits_charged": 1, "cost_usd": "0.11", "status": "COMPLETE"},
        {"video_id": "2", "user_id": "ana", "plan": "free", "free_credits": 1, "credits_charged": 1, "cost_usd": "0.09", "status": "COMPLETE"},
        {"video_id": "3", "user_id": "bea", "plan": "free", "free_credits": 1, "credits_charged": 1, "cost_usd": "0.02", "status": "FAILED", "refunded": True},
        {"video_id": "4", "user_id": "cy", "plan": "pro", "free_credits": 0, "credits_charged": 3, "cost_usd": "0.40"},
        {"video_id": "5", "user_id": "di", "plan": "max", "free_credits": 0, "credits_charged": 24, "cost_usd": "2.10"},
        {"video_id": "6", "user_id": "staff", "plan": "test", "credits_charged": 0, "cost_usd": "0.30"},
        {"video_id": "7", "user_id": "old", "credits_charged": 3, "cost_usd": "0.2"},
    ]
    rep = plan_report.summarize("2027-01-15", rows, stats={"granted": 4, "refused_disposable": 2, "refused_duplicate_email": 1, "budget_refused": 3, "device_refused_chain": 1, "ttl": 9},
                                budget_spent=2, cfg=plans.clean_config({}))
    assert rep["videos"] == {"free": 3, "pro": 1, "max": 1, "test": 1, "unknown": 1} and rep["paid_videos"] == 2 and rep["credits"] == {"free": 2, "paid": 30}
    assert rep["free"] == {"videos": 3, "users": 2, "tracked_usd": 0.22, "estimated_usd": 0.3, "cost_per_credit_usd": 0.15, "tracked_usd_per_user": 0.11, "estimated_usd_per_user": 0.15}
    assert [(u["user"], u["videos"], u["free_credits"], u["tracked_usd"], u["estimated_usd"]) for u in rep["top_free_users"]] == [("ana", 2, 2, 0.2, 0.3), ("bea", 1, 0, 0.02, 0.0)]
    assert rep["budget"] == {"limit_credits": 15, "spent_credits": 2, "limit_usd": 2.25} and rep["paid_tracked_usd"] == 2.5
    assert rep["claims"] == {"granted": 4, "refused": {"disposable": 2, "duplicate_email": 1}, "budget_refused": 3, "cap_refused": 0, "device_refused": {"chain": 1}}


def test_the_daily_metric_and_the_abuse_tables(launcher, defaults, capsys):
    import plans_daily
    import time as _t
    assert launch(launcher, target_minutes=0.5)["statusCode"] == 202
    give_plan(OTHER, "pro")
    assert launch(launcher, user=OTHER, target_minutes=2, email="o@example.org", ip="198.51.100.3")["statusCode"] == 202
    wallet.balance(THIRD, ctx=ctx(email=f"{USER[:8]}@example.org", ip="203.0.113.8"))          # a second account for the first person's address: refused
    vid = next(r for r in defaults.ddb.Table("Videos").scan()["Items"] if r["user_id"] == USER)
    defaults.ddb.Table("Videos").update_item(Key={"video_id": vid["video_id"]}, UpdateExpression="SET cost_usd = :c", ExpressionAttributeValues={":c": "0.12"})
    capsys.readouterr()
    day = _t.strftime("%Y-%m-%d", _t.gmtime())
    rep = plans_daily.handler({"day": day}, None)
    assert rep["videos"]["free"] == 1 and rep["paid_videos"] == 1 and rep["free"]["tracked_usd"] == 0.12 and rep["free"]["estimated_usd"] == 0.15 and rep["free"]["users"] == 1
    assert rep["claims"]["granted"] == 2 and rep["claims"]["refused"] == {"duplicate_email": 1} and rep["budget"]["spent_credits"] == 1
    assert rep["top_free_users"][0]["user"] == USER[:8]                                         # the log line keeps a short prefix only
    m = {k: v for line in capsys.readouterr().out.splitlines() if line.startswith('{"_aws"') for k, v in json.loads(line).items() if k.endswith("Day")}
    assert m == {"FreeVideosDay": 1, "PaidVideosDay": 1, "FreeUsersDay": 1, "FreeCreditsDay": 1, "FreeCostTrackedUsdDay": 0.12, "FreeCostEstimatedUsdDay": 0.15,
                 "FreeCostPerUserUsdDay": 0.15, "ClaimsGrantedDay": 2, "ClaimsRefusedDay": 1}
    blocks = plan_report.ip_blocks(day, defaults.ddb.Table("Usage"))
    assert {"block": "203.0.113.0/24", "claims": 1} in blocks and {"block": "198.51.100.0/24", "claims": 1} in blocks
    ids = plan_report.shared_identities(defaults.ddb.Table("FreeClaims"))
    assert ids["claims"] == 2 and ids["by_kind"]["email"] == 2 and ids["shared"] == 1 and ids["top"][0]["accounts"] == 2 and ids["top"][0]["identity"].endswith("...") and len(ids["top"][0]["identity"]) == 17


def test_the_gate_without_plans_is_a_no_op(aws, monkeypatch):
    monkeypatch.delenv("PLANS_ENABLED", raising=False)
    assert plan_gate.begin(USER, app_event()) is None and plan_gate.check(None, {"target_minutes": 12}, "en", explicit_length=True, default_minutes=3) is None
    assert plan_gate.record(None, 3) == {}
    plan_gate.give_back(None)
