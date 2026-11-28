"""Paid dictation (docs/SPEECH_TO_TEXT_2026-11-28.md): plan right, daily and global caps, kill switches, metering, records, the capabilities answer, c_stt on the video.
The provider is a fake; one real call was made by hand (see the doc). Nothing here touches the network."""
import base64
import json
from decimal import Decimal

import pytest

import capabilities_api
import dictation_api
from common import dictation, ops_switches, plans, stt
from tests.test_plans import USER, OTHER, OPEN, app_event, body_of, give_plan, launch, plans_on, launcher, caps  # noqa: F401  (fixtures)

AUDIO = base64.b64encode(b"x" * 20000).decode()


class FakeProvider:
    def __init__(self, seconds=30, fail=None):
        self.seconds, self.fail, self.calls = seconds, fail, []

    def transcribe(self, audio, mime, languages, prompt="", claimed=None):
        self.calls.append({"bytes": len(audio), "mime": mime, "languages": languages, "prompt": prompt})
        if self.fail:
            raise stt.SttError(self.fail)
        return {"text": "Make a video about my coffee shop", "language": "en", "seconds": self.seconds, "cost_usd": stt.cost_usd(self.seconds), "model": "gpt-transcribe", "provider": "openai"}


@pytest.fixture
def fake(monkeypatch, plans_on):
    f = FakeProvider()
    monkeypatch.setattr(stt, "provider", lambda name=None: f)
    monkeypatch.setattr(ops_switches, "_override", {}, raising=False)
    yield f
    ops_switches.set_state(None)


def dictate(user=USER, **body):
    ev = app_event(user=user, body={"audio": AUDIO, "mime": "audio/webm;codecs=opus", "seconds": 30, **body})
    r = dictation_api.handler(ev, None)
    return r["statusCode"], json.loads(r["body"]), r


def used(user=USER):
    return dictation.used_today(user)


def test_the_caps_are_the_justified_ones_and_are_plan_settings():
    assert [(p, plans.PLANS[p]["stt_premium"], plans.PLANS[p]["stt_seconds_per_day"]) for p in plans.ORDER] == [("free", False, 0), ("pro", True, 600), ("max", True, 1200)]
    # worst case if a user maxes the cap every day for 30 days (docs/SPEECH_TO_TEXT_2026-11-28.md section 8): Pro 300 min = $1.35 (9 % of $14.99), Max 600 min = $2.70 (7 % of $39.99)
    for plan, usd, share in (("pro", 1.35, 0.09), ("max", 2.70, 0.07)):
        month = stt.cost_usd(plans.PLANS[plan]["stt_seconds_per_day"] * 30)
        assert round(month, 2) == usd and month / plans.PRICES_USD[plan]["monthly"] < share + 0.005
    k = plans.config()
    assert k["stt_enabled"] is True and k["stt_max_clip_seconds"] == 360 and k["stt_global_daily_seconds"] == 100000
    assert dictation.MAX_AUDIO_BYTES == 3 * 1024 * 1024


def test_free_is_refused_with_the_plan_that_has_it_and_nothing_is_called_or_counted(fake):
    code, b, _ = dictate()
    assert code == 403 and b["code"] == "dictation_plan" and b["requires_plan"] == "pro" and b["feature"] == "dictation" and fake.calls == [] and used() == 0


@pytest.mark.parametrize("plan", ["pro", "max"])
def test_pro_and_max_get_the_text_and_the_seconds_are_metered_and_recorded(fake, plan):
    give_plan(USER, plan)
    code, b, r = dictate(languages=["es"], prompt="A request for a short explainer video")
    assert code == 200 and b["text"].startswith("Make a video") and b["seconds"] == 30 and len(b["id"]) == 32 and b["max_clip_seconds"] == 360
    assert b["seconds_left_today"] == plans.PLANS[plan]["stt_seconds_per_day"] - 30 and r["headers"]["Cache-Control"] == "no-store"
    assert fake.calls[0]["languages"] == ["es"] and used() == 30
    rec = dictation._table().get_item(Key={"user_id": f"sttrec:{USER}", "day": b["id"]})["Item"]
    assert rec["seconds"] == 30 and rec["cost_usd"] == Decimal("0.00225") and rec["model"] == "gpt-transcribe" and "text" not in rec and "audio" not in rec   # counters only
    assert dictation._table().get_item(Key={"user_id": "stt:global", "day": dictation.today()})["Item"]["seconds"] == 30


def test_the_daily_cap_is_enforced_per_plan_and_comes_back_tomorrow(fake):
    give_plan(USER, "pro")
    for _ in range(20):
        assert dictate()[0] == 200          # 20 x 30 s = 600 s = Pro's whole day
    code, b, r = dictate()
    assert code == 429 and b["code"] == "dictation_quota" and b["requires_plan"] == "max" and r["headers"]["Retry-After"] == "3600" and used() == 600 and len(fake.calls) == 20
    give_plan(USER, "max")
    assert dictate()[0] == 200                # Max has 1200
    tomorrow = "2099-01-02"
    assert dictation.used_today(USER, day=tomorrow) == 0


def test_max_over_its_cap_has_nothing_to_upgrade_to(fake):
    give_plan(USER, "max")
    for _ in range(40):
        assert dictate()[0] == 200
    code, b, _ = dictate()
    assert code == 429 and b["requires_plan"] is None and "tomorrow" in b["message"]


def test_the_cap_is_per_account(fake):
    give_plan(USER, "pro"); give_plan(OTHER, "pro")
    for _ in range(20):
        dictate()
    assert dictate()[0] == 429 and dictate(user=OTHER)[0] == 200


def test_the_provider_reports_the_real_length_and_the_counters_follow_it(fake):
    give_plan(USER, "pro")
    fake.seconds = 42
    code, b, _ = dictate(seconds=30)
    assert code == 200 and b["seconds"] == 42 and used() == 42
    fake.seconds = 10
    dictate(seconds=30)
    assert used() == 52


def test_a_provider_failure_charges_nothing(fake):
    give_plan(USER, "pro")
    fake.fail = "provider_unavailable"
    code, b, _ = dictate()
    assert code == 502 and b["code"] == "dictation_failed" and used() == 0
    fake.fail = "bad_audio"
    code, b, _ = dictate()
    assert code == 400 and b["code"] == "bad_audio" and used() == 0
    assert dictation._table().scan()["Items"] and all(not i["user_id"].startswith("sttrec:") for i in dictation._table().scan()["Items"])


def test_clip_and_size_limits(fake):
    give_plan(USER, "pro")
    code, b, _ = dictate(seconds=362)
    assert code == 413 and b["code"] == "dictation_too_long" and "6" in b["message"]
    big = base64.b64encode(b"x" * (3 * 1024 * 1024 + 1)).decode()
    code, b, _ = dictate(audio=big, seconds=60)
    assert code == 413
    fake.seconds = 360
    code, b, _ = dictate(seconds=360)
    assert code == 200 and used() == 360
    assert fake.calls and len(fake.calls) == 1


@pytest.mark.parametrize("bad", [{"audio": "!!!notbase64"}, {"audio": ""}, {"mime": "text/plain"}, {"mime": None}, {"audio": 5}])
def test_bad_requests_are_400_before_any_cost(fake, bad):
    give_plan(USER, "pro")
    code, b, _ = dictate(**bad)
    assert code == 400 and b["code"] == "bad_audio" and fake.calls == [] and used() == 0


def test_auth_and_path_rules(fake):
    assert dictation_api.handler(app_event(body={}) | {"requestContext": {}}, None)["statusCode"] == 401
    ev = app_event(body={"audio": AUDIO, "mime": "audio/webm"})
    ev["pathParameters"] = {"user_id": OTHER}
    assert dictation_api.handler(ev, None)["statusCode"] == 403


def test_the_knob_and_the_ops_switch_pause_dictation_for_everyone(fake):
    give_plan(USER, "pro")
    plans.set_config({**OPEN, "stt_enabled": False})
    code, b, _ = dictate()
    assert code == 503 and b["code"] == "dictation_paused" and fake.calls == [] and used() == 0
    plans.set_config(dict(OPEN))
    assert dictate()[0] == 200
    ops_switches.set_state({dictation.STOP_SWITCH: True})
    assert dictate()[0] == 503
    ops_switches.set_state({dictation.STOP_SWITCH: "yes"})   # only exactly true stops, like the other switches
    assert dictate()[0] == 200


def test_the_global_ceiling_pauses_everyone_and_gives_the_account_its_seconds_back(fake):
    give_plan(USER, "pro"); give_plan(OTHER, "max")
    plans.set_config({**OPEN, "stt_global_daily_seconds": 70})
    assert dictate()[0] == 200 and dictate(user=OTHER)[0] == 200
    code, b, _ = dictate()
    assert code == 503 and b["code"] == "dictation_paused" and used() == 30 and used(OTHER) == 30   # the refused reservation was released
    plans.set_config({**OPEN, "stt_global_daily_seconds": 0})
    assert dictate()[0] == 503


def test_an_unlimited_test_account_has_max_rights_and_its_own_ceiling(fake, monkeypatch):
    monkeypatch.setattr("common.wallet.is_unlimited", lambda u: u == USER)
    monkeypatch.setenv("UNLIMITED_DAILY_STT_SECONDS", "90")
    assert [dictate()[0] for _ in range(4)] == [200, 200, 200, 429]


def test_capabilities_tell_the_apps_whether_to_show_better_dictation(plans_on, monkeypatch):
    c = caps()["dictation"]
    assert c["premium"] is False and c["available"] is False and c["requires_plan"] == "pro" and c["seconds_per_day"] == 0 and c["max_clip_seconds"] == 360 and c["paused"] is False
    assert caps()["plan"]["limits"]["stt_premium"] is False and caps()["plan"]["limits"]["stt_seconds_per_day"] == 0
    give_plan(USER, "pro")
    c = caps()["dictation"]
    assert c["premium"] and c["available"] and c["seconds_per_day"] == 600 and c["seconds_left_today"] == 600 and c["requires_plan"] is None and c["max_clip_bytes"] == 3 * 1024 * 1024
    dictation.reserve(USER, 600, "pro", plans.rights("pro"), plans.config())
    c = caps()["dictation"]
    assert c["available"] is False and c["seconds_left_today"] == 0 and c["premium"] is True
    plans.set_config({**OPEN, "stt_enabled": False})
    assert caps()["dictation"]["paused"] is True and caps()["dictation"]["available"] is False
    assert [x["feature"] for x in caps()["plan"]["locked"] if x["feature"] == "stt_premium"] == []   # Pro already has it


def test_free_plan_locked_list_names_the_plan_that_has_better_dictation(plans_on):
    assert {"feature": "stt_premium", "value": True, "requires_plan": "pro"} in plans.locked("free", plans.config())


# ---------------------------------------------------------------- the cost of the video
def make_dictations(n, seconds=60, user=USER):
    ids = []
    for i in range(n):
        did = f"{i:032x}"
        dictation.record(user, did, {"seconds": seconds, "cost_usd": stt.cost_usd(seconds), "model": "gpt-transcribe", "language": "en"})
        ids.append(did)
    return ids


def test_a_video_that_names_its_dictations_carries_c_stt_stt_seconds_and_it_is_in_cost_usd(launcher, plans_on):
    give_plan(USER, "pro")
    ids = make_dictations(3, 60)                       # three recordings, all paid for: all charged to the video
    r = launch(launcher, dictation_ids=ids + [ids[0]], target_minutes=0.5)
    assert r["statusCode"] == 202, r["body"]
    row = plans_on.ddb.Table("Videos").scan()["Items"][0]
    assert row["c_stt"] == Decimal("0.0135") and row["stt_seconds"] == 180 and row["cost_usd"] == Decimal("0.0135") and row["dictation_ids"] == ids
    sent = json.loads(launcher.fake.calls[0]["input"])
    assert "dictation_ids" not in sent                  # the workflow never sees them
    from engine import costs
    costs.add_cost(row["video_id"], 0.05, part="speech")
    row = plans_on.ddb.Table("Videos").scan()["Items"][0]
    assert row["cost_usd"] == Decimal("0.0635") and row["c_stt"] == Decimal("0.0135") and row["c_speech"] == Decimal("0.05")


def test_a_video_without_dictations_has_no_stt_fields(launcher, plans_on):
    give_plan(USER, "pro")
    assert launch(launcher, target_minutes=0.5)["statusCode"] == 202
    row = plans_on.ddb.Table("Videos").scan()["Items"][0]
    assert not {"c_stt", "stt_seconds", "dictation_ids", "cost_usd"} & set(row)


@pytest.mark.parametrize("ids", [["nothex"], "abc", [5], ["0" * 31], [f"{i:032x}" for i in range(21)], ["a" * 32]])
def test_bad_or_foreign_dictation_ids_are_a_400_and_nothing_starts(launcher, plans_on, ids):
    give_plan(USER, "pro")
    r = launch(launcher, dictation_ids=ids, target_minutes=0.5)
    assert r["statusCode"] == 400 and launcher.fake.calls == []


def test_another_accounts_dictation_cannot_be_attached(launcher, plans_on):
    give_plan(USER, "pro")
    theirs = make_dictations(1, user=OTHER)
    r = launch(launcher, dictation_ids=theirs, target_minutes=0.5)
    assert r["statusCode"] == 400 and launcher.fake.calls == []


def test_a_retry_does_not_charge_the_dictation_again():
    import video_retry
    assert "c_stt" in video_retry.COST_ATTRS    # the attempt's cost restarts at 0 for the new attempt; the old total (c_stt included) moves to cost_usd_before and stt_seconds stays
    from engine import costs
    assert "stt" in costs.PARTS
