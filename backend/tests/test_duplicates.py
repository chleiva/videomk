import json
import time

import pytest

from common import usage, wallet
from tests.test_hardening import launcher  # noqa: F401  (the fixture)

PROMPT = "Have you explaining the news today"


def ev(prompt=PROMPT, crid="req-0000001", **body):
    return {"pathParameters": {"user_id": "u1"}, "headers": {}, "requestContext": {"authorizer": {"claims": {"sub": "u1"}}},
            "body": json.dumps({"prompt": prompt, "client_request_id": crid, "target_minutes": 1, **body})}


def test_the_same_request_twice_in_a_row_is_one_video_and_one_charge(launcher):
    first = launcher.handler(ev(crid="aaaa-1111-aaaa"), None)
    second = launcher.handler(ev(crid="bbbb-2222-bbbb"), None)          # what the app did: a new request id for the same text, 3 seconds later
    assert first["statusCode"] == 202 and second["statusCode"] == 202
    assert json.loads(second["body"])["video_id"] == json.loads(first["body"])["video_id"] and "already started" in json.loads(second["body"])["message"]
    assert len(launcher.fake.calls) == 1 and wallet.balance("u1")["balance"] == 4         # one execution, one credit (5 welcome credits)


def test_case_and_spacing_do_not_make_it_a_different_request(launcher):
    launcher.handler(ev(PROMPT, "aaaa-1111-aaaa"), None)
    again = launcher.handler(ev("  have you explaining THE news   today ", "cccc-3333-cccc"), None)
    assert len(launcher.fake.calls) == 1 and json.loads(again["body"])["video_id"]


def test_a_different_prompt_or_different_options_is_a_different_video(launcher):
    launcher.handler(ev(PROMPT, "aaaa-1111-aaaa"), None)
    launcher.handler(ev("Best Christmas markets in Europe", "dddd-4444-dddd"), None)
    launcher.handler(ev(PROMPT, "eeee-5555-eeee", target_minutes=2), None)               # the same words but another length is a deliberate second request
    launcher.handler(ev(PROMPT, "ffff-6666-ffff", captions=False), None)
    assert len(launcher.fake.calls) == 4


def test_the_same_request_is_allowed_again_after_the_window(launcher, monkeypatch):
    launcher.handler(ev(PROMPT, "aaaa-1111-aaaa"), None)
    real = time.time
    monkeypatch.setattr(usage.time, "time", lambda: real() + 121)
    later = launcher.handler(ev(PROMPT, "gggg-7777-gggg"), None)
    assert len(launcher.fake.calls) == 2 and json.loads(later["body"])["message"] == "workflow started"


def test_another_user_is_never_blocked_by_someone_elses_request(launcher):
    launcher.handler(ev(PROMPT, "aaaa-1111-aaaa"), None)
    other = ev(PROMPT, "hhhh-8888-hhhh")
    other["pathParameters"]["user_id"] = "u2"
    other["requestContext"]["authorizer"]["claims"]["sub"] = "u2"
    assert launcher.handler(other, None)["statusCode"] == 202 and len(launcher.fake.calls) == 2


def test_a_request_that_could_not_start_does_not_block_the_retry(launcher):
    wallet.balance("u1")
    taken = wallet.charge("u1", 5)                                                           # no credits left
    out = launcher.handler(ev(PROMPT, "aaaa-1111-aaaa"), None)
    assert out["statusCode"] == 402 and not launcher.fake.calls
    wallet.refund("u1", taken)
    retry = launcher.handler(ev(PROMPT, "bbbb-2222-bbbb"), None)
    assert retry["statusCode"] == 202 and len(launcher.fake.calls) == 1                     # the refused attempt left no claim behind


def test_a_replay_with_the_same_request_id_still_returns_the_existing_video(launcher):
    a = launcher.handler(ev(PROMPT, "aaaa-1111-aaaa"), None)
    b = launcher.handler(ev(PROMPT, "aaaa-1111-aaaa"), None)
    assert json.loads(a["body"])["video_id"] == json.loads(b["body"])["video_id"] and len(launcher.fake.calls) == 1 and wallet.balance("u1")["balance"] == 4


def test_lost_response_replay_long_after_the_window_with_changed_photo_ids_is_still_one_video_and_one_charge(launcher, monkeypatch):
    """The answer was lost on cellular and the app re-uploaded its photos (new media ids, so a different fingerprint) minutes later: the request id alone must return the first video."""
    first = launcher.handler(ev(PROMPT, "aaaa-1111-aaaa", language="en"), None)
    real = time.time
    monkeypatch.setattr(usage.time, "time", lambda: real() + 3600)          # far outside the 2-minute duplicate window
    again = launcher.handler(ev(PROMPT, "aaaa-1111-aaaa", language="es"), None)   # different options, same key
    assert json.loads(again["body"])["video_id"] == json.loads(first["body"])["video_id"] and "already started" in json.loads(again["body"])["message"]
    assert len(launcher.fake.calls) == 1 and wallet.balance("u1")["balance"] == 4


def test_a_new_request_id_after_the_window_is_a_new_video_so_the_client_must_reuse_its_key(launcher, monkeypatch):
    """Documents why the apps keep one request id per Create attempt: a fresh id with changed photos is a second, charged video."""
    launcher.handler(ev(PROMPT, "aaaa-1111-aaaa", language="en"), None)
    real = time.time
    monkeypatch.setattr(usage.time, "time", lambda: real() + 3600)
    launcher.handler(ev(PROMPT, "bbbb-2222-bbbb", language="es"), None)
    assert len(launcher.fake.calls) == 2 and wallet.balance("u1")["balance"] == 3
