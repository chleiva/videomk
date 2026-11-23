import json

import pytest

from common import usage
from generate_video import db


def _event(user="u1", path_user=None, body=None, authed=True):
    ev = {
        "pathParameters": {"user_id": path_user or user},
        "headers": {"Authorization": "Bearer SECRET.JWT.TOKEN"},
        "body": json.dumps(body if body is not None else {"prompt": "A short explainer about how black holes form"}),
        "requestContext": {"authorizer": {"claims": {"sub": user}}} if authed else {},
    }
    return ev


# ---------- quota ----------
def test_quota_consumes_then_blocks_then_refunds(aws):
    for i in range(3):
        assert usage.consume("u1", limit=3) == i + 1
    with pytest.raises(usage.QuotaExceeded):
        usage.consume("u1", limit=3)
    usage.refund("u1")
    assert usage.consume("u1", limit=3) == 3


def test_quota_is_per_user(aws):
    usage.consume("a", limit=1)
    assert usage.consume("b", limit=1) == 1


def test_refund_never_goes_negative(aws):
    usage.refund("nobody")
    usage.consume("u1", limit=5)
    usage.refund("u1")
    usage.refund("u1")
    assert usage.consume("u1", limit=5) == 1


# ---------- terminal-state guard ----------
def test_terminal_status_is_not_overwritten(aws):
    aws.Table("Videos").put_item(Item={"video_id": "v1", "status": "STARTED_PROCESSING"})
    assert db.update_status("v1", "RENDERING")["status"] == "RENDERING"
    assert db.update_status("v1", "COMPLETE", extra_attributes={"duration_s": 10})["status"] == "COMPLETE"
    assert db.update_status("v1", "FAILED") == {}  # late MarkFailed must not clobber COMPLETE
    assert aws.Table("Videos").get_item(Key={"video_id": "v1"})["Item"]["status"] == "COMPLETE"


def test_update_status_creates_missing_item_attrs(aws):
    out = db.update_status("v2", "PLOT_CREATION", extra_attributes={"title": "T"})
    assert out["status"] == "PLOT_CREATION" and out["title"] == "T"


# ---------- launcher ----------
class _FakeSfn:
    def __init__(self):
        self.calls = []

    def start_execution(self, **kw):
        self.calls.append(kw)
        import datetime
        return {"executionArn": "arn:x", "startDate": datetime.datetime(2026, 1, 1)}


@pytest.fixture
def launcher(aws, monkeypatch):
    import sf_launcher
    fake = _FakeSfn()
    monkeypatch.setattr(sf_launcher, "_sfn", fake)
    monkeypatch.setattr(sf_launcher, "_dynamodb", aws)
    monkeypatch.setenv("DAILY_VIDEO_LIMIT", "2")
    sf_launcher.fake = fake
    return sf_launcher


def test_launcher_requires_auth(launcher):
    assert launcher.handler(_event(authed=False), None)["statusCode"] == 401


def test_launcher_forbids_other_users_path(launcher):
    assert launcher.handler(_event(user="u1", path_user="u2"), None)["statusCode"] == 403


@pytest.mark.parametrize("prompt", ["", "short", "x" * 2001, 123, None])
def test_launcher_rejects_bad_prompts(launcher, prompt):
    r = launcher.handler(_event(body={"prompt": prompt}), None)
    assert r["statusCode"] == 400
    assert launcher.fake.calls == []


def test_launcher_rejects_invalid_json(launcher):
    ev = _event()
    ev["body"] = "{not json"
    assert launcher.handler(ev, None)["statusCode"] == 400


def test_launcher_never_forwards_headers_or_jwt(launcher):
    r = launcher.handler(_event(), None)
    assert r["statusCode"] == 202
    sent = json.loads(launcher.fake.calls[0]["input"])
    assert set(sent) == {"user_id", "video_id", "prompt", "usage_day"}
    assert "SECRET" not in launcher.fake.calls[0]["input"]
    assert launcher.fake.calls[0]["stateMachineArn"].endswith("generate_video_workflow")


def test_launcher_forwards_valid_create_options(launcher):
    body = {"prompt": "A short explainer about how black holes form", "target_minutes": 2, "theme": "paper"}
    assert launcher.handler(_event(body=body), None)["statusCode"] == 202
    sent = json.loads(launcher.fake.calls[0]["input"])
    assert sent["target_minutes"] == 2.0 and sent["theme"] == "paper"


@pytest.mark.parametrize("extra", [{"target_minutes": 0}, {"target_minutes": 13}, {"target_minutes": "3"}, {"target_minutes": True}, {"theme": "neon"}])
def test_launcher_rejects_invalid_options_without_charging(launcher, extra):
    body = {"prompt": "A short explainer about how black holes form", **extra}
    assert launcher.handler(_event(body=body), None)["statusCode"] == 400
    assert launcher.fake.calls == []
    assert usage.consume("u1", limit=2) == 1  # nothing was consumed by the rejected request


def test_launcher_quota_429_and_no_extra_execution(launcher):
    for _ in range(2):
        assert launcher.handler(_event(), None)["statusCode"] == 202
    r = launcher.handler(_event(), None)
    assert r["statusCode"] == 429 and r["headers"]["Retry-After"]
    assert len(launcher.fake.calls) == 2


def test_launcher_idempotent_with_client_request_id(launcher):
    body = {"prompt": "A short explainer about how black holes form", "client_request_id": "click-12345678"}
    a = json.loads(launcher.handler(_event(body=body), None)["body"])
    b = json.loads(launcher.handler(_event(body=body), None)["body"])
    assert a["video_id"] == b["video_id"]
    assert len(launcher.fake.calls) == 1  # double-click did not start (or bill) a second job
    assert usage.consume("u1", limit=2) == 2  # only one unit was consumed before this call


def test_launcher_refunds_when_start_fails(launcher):
    def boom(**kw):
        raise RuntimeError("sfn down")
    launcher.fake.start_execution = boom
    assert launcher.handler(_event(), None)["statusCode"] == 500
    assert usage.consume("u1", limit=1) == 1  # refunded


# ---------- reject/failed handlers ----------
def test_mark_rejected_sets_reason_and_refunds(aws):
    from generate_video.handlers import mark_rejected_handler
    usage.consume("u1", limit=1)
    day = usage._today()
    aws.Table("Videos").put_item(Item={"video_id": "v", "user_id": "u1", "usage_day": day, "status": "PLOT_CREATION"})
    out = mark_rejected_handler.handler({"video_id": "v", "plot": {"legit": False, "reason": "unsafe"}}, None)
    assert out["status"] == "REJECTED"
    item = aws.Table("Videos").get_item(Key={"video_id": "v"})["Item"]
    assert item["status"] == "REJECTED" and item["reject_reason"] == "unsafe"
    assert usage.consume("u1", limit=1) == 1


def test_mark_failed_does_not_refund_completed(aws):
    from generate_video.handlers import mark_failed_handler
    usage.consume("u1", limit=1)
    aws.Table("Videos").put_item(Item={"video_id": "v", "user_id": "u1", "usage_day": usage._today(), "status": "COMPLETE"})
    mark_failed_handler.handler({"video_id": "v", "error": {"Error": "X"}}, None)
    with pytest.raises(usage.QuotaExceeded):
        usage.consume("u1", limit=1)


# ---------- renderer asset allow-list ----------
def test_render_blocks_foreign_assets():
    from generate_video import render
    ok = "s3://videomk.com/generation/assets/vid-1/scene_1.png"
    assert render._is_allowed_asset(ok, "vid-1")
    assert render._is_allowed_asset("s3://videomk.com/generation/assets/static/basic.wav", "vid-1")
    assert not render._is_allowed_asset("s3://videomk.com/generation/assets/other-vid/scene_1.png", "vid-1")
    assert not render._is_allowed_asset("s3://videomk.com/videos/user/secret.mp4", "vid-1")
    assert not render._is_allowed_asset("s3://other-bucket/generation/assets/vid-1/x.png", "vid-1")
    assert not render._is_allowed_asset("s3://videomk.com/generation/assets/vid-1/../x.png", "vid-1")
