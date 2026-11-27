"""The owner's emergency switches as the customer side reads them (lambdas/common/ops_switches.py; docs/ADMIN_CONSOLE_DESIGN_2026-11-28.md section 4):
"stop all new videos" at the launcher (generate and retry; cancel and delete keep working), "stop free videos" as a free budget of 0, restrict-only values,
one read a minute, and FAIL OPEN on any read problem. The console side (who may write the item) is tested in tests/test_admin_console.py."""
import json

import pytest

import capabilities_api
import video_retry
from common import free_grants, ops_switches, plans
from tests.test_hardening import _event, launcher  # noqa: F401  (the fixture)
from tests.test_plans import T0, body_of, launch, plans_on  # noqa: F401

PROMPT = "A short explainer about how black holes form"


@pytest.fixture(autouse=True)
def clean():
    ops_switches._table = None
    ops_switches.set_state(None)
    yield
    ops_switches._table = None
    ops_switches.set_state(None)


def store(aws, **values):
    aws.Table("Flags").put_item(Item={"user_id": ops_switches.ITEM_KEY, **values})
    ops_switches.set_state(None)   # the next read goes to the table


def ev(resource="/users/{user_id}/videos/generate", method="POST", locale=None, **kw):
    e = _event(**kw)
    e.update({"resource": resource, "httpMethod": method})
    if locale:
        e["headers"]["X-Locale"] = locale
    return e


def test_nothing_stored_means_everything_runs(launcher):
    assert ops_switches.state() == {} and not ops_switches.stopped(ops_switches.NEW_VIDEOS) and not ops_switches.stopped(ops_switches.FREE_VIDEOS)
    assert ops_switches.maintenance(ev()) is None
    assert launcher.handler(ev(), None)["statusCode"] == 202 and len(launcher.fake.calls) == 1


def test_stop_new_videos_refuses_generate_with_a_clear_localized_answer_and_starts_nothing(launcher, aws):
    store(aws, stop_new_videos=True)
    r = launcher.handler(ev(), None)
    b = json.loads(r["body"])
    assert r["statusCode"] == 503 and b["code"] == "maintenance" and b["retry_after"] == 300 and r["headers"]["Retry-After"] == "300"
    assert b["message"] == ops_switches.MESSAGES["en"] and "VideoMK" in b["message"]
    assert json.loads(launcher.handler(ev(locale="es"), None)["body"])["message"] == ops_switches.MESSAGES["es"]
    assert launcher.fake.calls == []                                                 # no workflow
    assert aws.Table("Videos").scan()["Items"] == [] and aws.Table("Wallet").scan()["Items"] == []   # no record, nothing charged
    assert launcher.handler(ev(authed=False), None)["statusCode"] == 503            # the same answer before anything else is looked at


def test_stop_new_videos_covers_retry_but_never_cancel_or_delete(launcher, aws, monkeypatch):
    store(aws, stop_new_videos=True)
    seen = []
    for name in ("retry_handler", "cancel_handler", "delete_handler"):
        monkeypatch.setattr(video_retry, name, lambda e, c, n=name: seen.append(n) or {"statusCode": 200, "body": "{}"})
    assert launcher.handler(ev("/users/{user_id}/videos/{video_id}/retry"), None)["statusCode"] == 503
    assert launcher.handler(ev("/users/{user_id}/videos/{video_id}/cancel"), None)["statusCode"] == 200
    assert launcher.handler(ev("/users/{user_id}/videos/{video_id}", "DELETE"), None)["statusCode"] == 200
    assert seen == ["cancel_handler", "delete_handler"]


def test_switching_back_lets_videos_start_again(launcher, aws):
    store(aws, stop_new_videos=True)
    assert launcher.handler(ev(), None)["statusCode"] == 503
    store(aws, stop_new_videos=False)
    assert launcher.handler(ev(), None)["statusCode"] == 202


@pytest.mark.parametrize("value", ["true", "True", 1, "yes", "on", {"a": 1}, None, False, 0])
def test_a_switch_is_on_only_for_exactly_true(aws, value):
    store(aws, stop_new_videos=value, stop_free_videos=value)
    assert not ops_switches.stopped(ops_switches.NEW_VIDEOS) and not ops_switches.stopped(ops_switches.FREE_VIDEOS)
    assert ops_switches.maintenance(ev()) is None


def test_unknown_fields_cannot_hand_out_anything(aws, launcher):
    """The stored item is only ever read for the two switches and the two message texts: a hostile value can stop things, never grant."""
    store(aws, free_daily_budget_credits=10**6, free_budget_unlimited=True, unlimited=True, welcome_credits=50)
    assert plans.clean_config({})["free_daily_budget_credits"] == 15 and not ops_switches.stopped(ops_switches.NEW_VIDEOS)
    assert launcher.handler(ev(), None)["statusCode"] == 202


def test_fails_open_when_the_read_fails_and_keeps_the_last_good_values(aws, monkeypatch):
    def boom():
        raise RuntimeError("dynamodb is down")
    monkeypatch.setattr(ops_switches, "_read", boom)
    assert ops_switches.state(now=1000.0) == {} and not ops_switches.stopped(ops_switches.NEW_VIDEOS, now=1000.0)
    assert ops_switches.maintenance(ev()) is None                                    # nothing known + a storage error = videos run
    monkeypatch.undo()
    store(aws, stop_new_videos=True)
    assert ops_switches.stopped(ops_switches.NEW_VIDEOS, now=2000.0)
    monkeypatch.setattr(ops_switches, "_read", boom)
    assert ops_switches.stopped(ops_switches.NEW_VIDEOS, now=2000.0 + 3600)          # the read fails later: the last good value (stopped) stays


def test_fails_open_without_a_table_name_and_on_a_missing_table(aws, monkeypatch):
    monkeypatch.setenv("FLAGS_TABLE", "NoSuchTable")
    assert not ops_switches.stopped(ops_switches.NEW_VIDEOS)
    ops_switches._table = None
    ops_switches.set_state(None)
    monkeypatch.delenv("FLAGS_TABLE")
    assert ops_switches.state() == {}


def test_the_table_is_read_at_most_once_a_minute(aws, monkeypatch):
    reads = []
    monkeypatch.setattr(ops_switches, "_read", lambda: reads.append(1) or {"stop_new_videos": True})
    for now in (10.0, 20.0, 69.0):
        assert ops_switches.stopped(ops_switches.NEW_VIDEOS, now=now)
    assert len(reads) == 1
    ops_switches.stopped(ops_switches.NEW_VIDEOS, now=71.0)
    assert len(reads) == 2


def test_an_admin_can_store_another_sentence_by_hand(aws):
    store(aws, stop_new_videos=True, message_en="Back at 15:00 UTC.", message_es="   ")
    assert json.loads(ops_switches.maintenance(ev())["body"])["message"] == "Back at 15:00 UTC."
    assert json.loads(ops_switches.maintenance(ev(locale="es"))["body"])["message"] == ops_switches.MESSAGES["es"]


def test_capabilities_says_creation_is_paused():
    assert ops_switches.creation_state("en") == {"paused": False, "code": None, "message": None}
    ops_switches.set_state({"stop_new_videos": True})
    assert ops_switches.creation_state("es") == {"paused": True, "code": "maintenance", "message": ops_switches.MESSAGES["es"]}
    r = json.loads(capabilities_api.handler(ev("/users/{user_id}/capabilities", "GET"), None)["body"])
    assert r["creation"]["paused"] is True and r["creation"]["message"] == ops_switches.MESSAGES["en"]
    ops_switches.set_state({})
    assert "creation" not in json.loads(capabilities_api.handler(ev("/users/{user_id}/capabilities", "GET"), None)["body"])   # absent while videos run: the answer is exactly as before


def test_stop_free_videos_reads_as_a_free_budget_of_zero_and_leaves_paid_credits_alone(plans_on):
    cfg = plans.clean_config({"free_daily_budget_credits": 15})
    assert free_grants.budget_take(2, cfg, T0) and not free_grants.budget_state(cfg, T0)["paused"]
    ops_switches.set_state({"stop_free_videos": True})
    st = free_grants.budget_state(cfg, T0)
    assert st["paused"] and st["limit_credits"] == 0 and not free_grants.budget_take(1, cfg, T0)
    assert not free_grants.budget_take(1, plans.clean_config({"free_budget_unlimited": True}), T0)     # even an unlimited budget is stopped
    assert free_grants.budget_take(0, cfg, T0)                                                           # a video paid with plan credits takes nothing from the budget
    assert cfg["free_daily_budget_credits"] == 15                                                        # the owner's knob itself is untouched
    ops_switches.set_state({"stop_free_videos": False})
    assert free_grants.budget_take(1, cfg, T0) and free_grants.budget_state(cfg, T0)["spent_credits"] == 3


def test_stop_free_videos_refuses_a_free_video_at_the_launcher_with_the_existing_answer(launcher, plans_on):
    assert launch(launcher, target_minutes=0.5)["statusCode"] == 202                                     # a free account with welcome credits
    ops_switches.set_state({"stop_free_videos": True})
    r = launch(launcher, target_minutes=0.5, client_request_id="second-one")
    assert r["statusCode"] == 429 and body_of(r)["code"] == "free_budget_spent"
    assert len(launcher.fake.calls) == 1
