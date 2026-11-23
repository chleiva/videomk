import json

import pytest

from common import usage, wallet
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
    assert set(sent) == {"user_id", "video_id", "prompt", "usage_day", "target_minutes"}  # no headers; the billed length rides along
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
    assert wallet.balance("u1")["balance"] == 5  # nothing was charged for the rejected request


def test_launcher_charges_one_credit_per_started_minute_and_refuses_when_short(launcher):
    assert wallet.balance("u1")["balance"] == 5                         # welcome credits
    ok = launcher.handler(_event(body={"prompt": "A short explainer about how black holes form", "target_minutes": 2.5}), None)
    assert ok["statusCode"] == 202 and wallet.balance("u1")["balance"] == 2   # 2.5 minutes = 3 started minutes = 3 credits
    sent = json.loads(launcher.fake.calls[0]["input"])
    assert sent["target_minutes"] == 2.5                                 # what is billed is what is made
    item = launcher._dynamodb.Table("Videos").get_item(Key={"video_id": json.loads(ok["body"])["video_id"]})["Item"]
    assert item["credits_charged"] == 3 and sum(x["n"] for x in json.loads(item["charge"])) == 3
    r = launcher.handler(_event(body={"prompt": "Another explainer about how black holes form", "target_minutes": 3}), None)
    body = json.loads(r["body"])
    assert r["statusCode"] == 402 and body["code"] == "insufficient_credits" and (body["balance"], body["needed"]) == (2, 3)
    assert len(launcher.fake.calls) == 1 and wallet.balance("u1")["balance"] == 2   # refused: nothing started, nothing taken
    assert launcher.handler(_event(body={"prompt": "A one minute explainer about black holes", "target_minutes": 1}), None)["statusCode"] == 202


def test_launcher_defaults_to_the_servers_default_length_and_bills_it(launcher):
    assert launcher.handler(_event(), None)["statusCode"] == 202
    assert json.loads(launcher.fake.calls[0]["input"])["target_minutes"] == 3.0 and wallet.balance("u1")["balance"] == 2


def test_launcher_idempotent_with_client_request_id(launcher):
    body = {"prompt": "A short explainer about how black holes form", "client_request_id": "click-12345678"}
    a = json.loads(launcher.handler(_event(body=body), None)["body"])
    b = json.loads(launcher.handler(_event(body=body), None)["body"])
    assert a["video_id"] == b["video_id"]
    assert len(launcher.fake.calls) == 1  # double-click did not start (or bill) a second job
    assert wallet.balance("u1")["balance"] == 2  # one default (3 minute) video was charged once, not twice


def test_launcher_refunds_when_start_fails(launcher):
    def boom(**kw):
        raise RuntimeError("sfn down")
    launcher.fake.start_execution = boom
    assert launcher.handler(_event(), None)["statusCode"] == 500
    assert wallet.balance("u1")["balance"] == 5  # refunded in full


# ---------- reject/failed handlers ----------
def _charged_video(aws, status, credits=3):
    wallet.balance("u1")
    taken = wallet.charge("u1", credits)
    aws.Table("Videos").put_item(Item={"video_id": "v", "user_id": "u1", "status": status, "charge": json.dumps(taken), "credits_charged": credits})
    return taken


def test_mark_rejected_sets_reason_and_refunds(aws):
    from generate_video.handlers import mark_rejected_handler
    _charged_video(aws, "PLOT_CREATION")
    assert wallet.balance("u1")["balance"] == 2
    out = mark_rejected_handler.handler({"video_id": "v", "plot": {"legit": False, "reason": "unsafe"}}, None)
    assert out["status"] == "REJECTED"
    item = aws.Table("Videos").get_item(Key={"video_id": "v"})["Item"]
    assert item["status"] == "REJECTED" and item["reject_reason"] == "unsafe"
    assert wallet.balance("u1")["balance"] == 5  # "no credits used" is true


def test_mark_failed_refunds_a_failed_video_once(aws):
    from generate_video.handlers import mark_failed_handler
    _charged_video(aws, "RENDERING")
    mark_failed_handler.handler({"video_id": "v", "error": {"Error": "X"}}, None)
    mark_failed_handler.handler({"video_id": "v", "error": {"Error": "X"}}, None)  # a retry must not refund twice
    assert wallet.balance("u1")["balance"] == 5


def test_mark_failed_does_not_refund_completed(aws):
    from generate_video.handlers import mark_failed_handler
    _charged_video(aws, "COMPLETE")
    mark_failed_handler.handler({"video_id": "v", "error": {"Error": "X"}}, None)
    assert wallet.balance("u1")["balance"] == 2  # a finished video stays paid for


def test_wallet_endpoint_requires_the_owner(aws):
    import wallet_api
    ev = {"pathParameters": {"user_id": "u1"}, "headers": {"X-Timezone": "Europe/Madrid"}, "requestContext": {"authorizer": {"claims": {"sub": "u1"}}}}
    out = wallet_api.handler(ev, None)
    body = json.loads(out["body"])
    assert out["statusCode"] == 200 and body["balance"] == 5 and body["rules"]["daily"] == 2 and body["buckets"][0]["kind"] == "signup"
    assert wallet_api.handler({**ev, "requestContext": {}}, None)["statusCode"] == 401
    assert wallet_api.handler({**ev, "pathParameters": {"user_id": "u2"}}, None)["statusCode"] == 403


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


def test_launcher_passes_the_viewers_region_but_only_as_a_two_letter_code(launcher, monkeypatch):
    monkeypatch.setenv("DAILY_VIDEO_LIMIT", "10")
    ev = _event(body={"prompt": "A short explainer about how black holes form", "target_minutes": 1})
    ev["headers"] = {"X-Region": "gb", "Authorization": "Bearer SECRET"}
    assert launcher.handler(ev, None)["statusCode"] == 202
    sent = json.loads(launcher.fake.calls[0]["input"])
    assert sent["region"] == "GB" and "SECRET" not in launcher.fake.calls[0]["input"]
    ev2 = _event(body={"prompt": "A short explainer about how black holes form", "client_request_id": "region-test-02", "target_minutes": 1})
    ev2["headers"] = {"X-Region": "../etc"}
    assert launcher.handler(ev2, None)["statusCode"] == 202 and "region" not in json.loads(launcher.fake.calls[1]["input"])
    ev3 = _event(body={"prompt": "A short explainer about how black holes form", "client_request_id": "region-test-03", "target_minutes": 1})
    ev3["headers"] = {"CloudFront-Viewer-Country": "IN"}
    launcher.handler(ev3, None)
    assert json.loads(launcher.fake.calls[2]["input"])["region"] == "IN"
