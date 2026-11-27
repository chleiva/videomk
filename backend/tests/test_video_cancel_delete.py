"""Cancel a video that is being made, delete a finished one, and the wallet says when the next free credit arrives (lambdas/video_retry.py, common/wallet.py;
docs/CREATE_API.md). Owner only, the refund exactly once, never another person's video, never the person's uploads or My media."""
import datetime
import json
import time
import uuid

import pytest

from common import i18n, wallet
from generate_video import db
from generate_video.handlers import mark_failed_handler
from tests.test_video_retry import BUCKET, USER, _body, _event, _item, env  # noqa: F401  (the fixture)

ARN = "arn:aws:states:us-west-2:123456789012:execution:generate_video_workflow:"
CANCEL = "/users/{user_id}/videos/{video_id}/cancel"
ITEM = "/users/{user_id}/videos/{video_id}"


@pytest.fixture
def stops(env, monkeypatch):  # noqa: F811
    calls = []

    def stop_execution(**kw):
        calls.append(kw)
        return {"stopDate": datetime.datetime(2026, 1, 1)}
    monkeypatch.setattr(env.sfn, "stop_execution", stop_execution, raising=False)
    return calls


def _video(env, status="ASSETS_CREATION", user=USER, credits=2, retries=0, **extra):  # noqa: F811
    """A video as the launcher records it, charged from the person's real wallet."""
    vid = str(uuid.uuid4())
    wallet.balance(user)
    taken = wallet.charge(user, credits) if credits else []
    item = {"video_id": vid, "user_id": user, "prompt": "how tides work", "status": status, "created_at": "2026-11-27T02:16:00Z", "usage_day": "2026-11-27", "credits_charged": credits,
            "charge": json.dumps(taken), "title": "Tides", "request_json": json.dumps({"options": {"target_minutes": 2.0}, "library_media": []}), **({"retries": retries} if retries else {}), **extra}
    env.ddb.Table("Videos").put_item(Item=item)
    for key in (f"generation/v2/{vid}/plan_r1.json", f"generation/v2/{vid}/segments/f_x.ts", f"generation/v2/{vid}/assets/user_P1.jpg", f"generation/v2/{vid}/retry_uploads/a.jpg"):
        env.s3.put_object(Bucket=BUCKET, Key=key, Body=b"x")
    return vid


def _keys(env, prefix):  # noqa: F811
    return sorted(o["Key"] for o in env.s3.list_objects_v2(Bucket=BUCKET, Prefix=prefix).get("Contents", []))


def _cancel(env, vid, **kw):  # noqa: F811
    return env.sl.handler(_event(vid, resource=CANCEL, **kw), None)


def _delete(env, vid, **kw):  # noqa: F811
    return env.sl.handler(_event(vid, method="DELETE", resource=ITEM, **kw), None)


# ---------------------------------------------------------------- cancel
@pytest.mark.parametrize("status", ["STARTED_PROCESSING", "PLOT_CREATION", "ASSETS_CREATION"])
def test_cancel_stops_the_workflow_marks_it_cancelled_and_gives_the_credits_back(env, stops, status):  # noqa: F811
    vid = _video(env, status, making_plan="{}", making_done="[]")
    assert wallet.balance(USER)["balance"] == 3
    r = _cancel(env, vid)
    assert r["statusCode"] == 200 and _body(r) == {"message": "cancelled", "video_id": vid, "status": "CANCELLED", "retries": 0, "refunded": 2}
    it = _item(env, vid)
    assert it["status"] == "CANCELLED" and it["cancel_reason"] == "user" and it["cancelled_at"].endswith("Z") and it["refunded"] is True and "making_plan" not in it
    assert stops == [{"executionArn": ARN + vid, "error": "CANCELLED", "cause": "cancelled by the owner"}]
    assert wallet.balance(USER)["balance"] == 5
    assert _keys(env, f"generation/v2/{vid}/") == [f"generation/v2/{vid}/assets/user_P1.jpg", f"generation/v2/{vid}/retry_uploads/a.jpg"]   # working files gone, the photos kept for "Try again"


def test_a_second_cancel_changes_nothing_and_never_refunds_twice(env, stops):  # noqa: F811
    vid = _video(env)
    assert _body(_cancel(env, vid))["refunded"] == 2
    for _ in range(3):
        r = _cancel(env, vid)
        assert r["statusCode"] == 200 and _body(r) == {"message": "already cancelled", "video_id": vid, "status": "CANCELLED", "retries": 0, "refunded": 0}
    assert wallet.balance(USER)["balance"] == 5 and len(stops) == 1


def test_only_the_owner_can_cancel(env, stops):  # noqa: F811
    vid = _video(env)
    wallet.balance("u2")
    assert _cancel(env, vid, user="u2")["statusCode"] == 404 and _body(_cancel(env, vid, user="u2"))["code"] == "not_found"   # another person's video is simply not found
    assert _cancel(env, vid, user="u2", path_user=USER)["statusCode"] == 403                                                    # nor by naming the owner in the path
    assert _cancel(env, vid, authed=False)["statusCode"] == 401
    assert _cancel(env, "../" + vid)["statusCode"] == 400 and _cancel(env, "no-such-video")["statusCode"] == 404
    assert _item(env, vid)["status"] == "ASSETS_CREATION" and stops == [] and wallet.balance(USER)["balance"] == 3 and wallet.balance("u2")["balance"] == 5


@pytest.mark.parametrize("status", ["COMPLETE", "FAILED", "REJECTED"])
def test_a_video_that_is_not_being_made_cannot_be_cancelled(env, stops, status):  # noqa: F811
    vid = _video(env, status)
    r = _cancel(env, vid)
    assert r["statusCode"] == 409 and _body(r)["code"] == "not_cancellable" and _body(r)["status"] == status
    assert _item(env, vid)["status"] == status and stops == [] and wallet.balance(USER)["balance"] == 3


def test_a_retried_video_stops_its_own_run(env, stops):  # noqa: F811
    vid = _video(env, retries=2)
    assert _body(_cancel(env, vid))["retries"] == 2 and stops[0]["executionArn"] == ARN + vid + "-r2"


def test_a_workflow_that_already_ended_still_leaves_the_video_cancelled_and_refunded(env, monkeypatch):  # noqa: F811
    monkeypatch.setattr(env.sfn, "stop_execution", lambda **kw: (_ for _ in ()).throw(RuntimeError("ExecutionDoesNotExist")), raising=False)
    vid = _video(env)
    assert _cancel(env, vid)["statusCode"] == 200 and _item(env, vid)["status"] == "CANCELLED" and wallet.balance(USER)["balance"] == 5


def test_a_late_step_of_the_stopped_workflow_cannot_wake_or_fail_a_cancelled_video(env, stops):  # noqa: F811
    vid = _video(env)
    _cancel(env, vid)
    assert db.update_status(vid, "ASSETS_CREATION") == {} and db.update_status(vid, "COMPLETE", extra_attributes={"video_uri": "s3://x"}) == {}
    assert mark_failed_handler.handler({"video_id": vid, "error": {"Error": "States.TaskFailed"}}, None)["status"] == "FAILED"   # the failure path runs, and changes nothing
    it = _item(env, vid)
    assert it["status"] == "CANCELLED" and "video_uri" not in it and "failure_code" not in it and wallet.balance(USER)["balance"] == 5


def test_a_video_that_finishes_while_the_cancel_is_on_its_way_is_not_cancelled_or_refunded(env, stops, monkeypatch):  # noqa: F811
    vid = _video(env)
    stale = dict(_item(env, vid))
    env.ddb.Table("Videos").update_item(Key={"video_id": vid}, UpdateExpression="SET #s = :c", ExpressionAttributeNames={"#s": "status"}, ExpressionAttributeValues={":c": "COMPLETE"})
    real = env.vr._own_item
    seen = []
    monkeypatch.setattr(env.vr, "_own_item", lambda u, v: (seen.append(1), stale)[1] if not seen else real(u, v))   # the handler read the row a moment before it finished
    r = _cancel(env, vid)
    assert r["statusCode"] == 409 and _body(r)["code"] == "not_cancellable" and _item(env, vid)["status"] == "COMPLETE" and stops == [] and wallet.balance(USER)["balance"] == 3
    vid2 = _video(env, "PLOT_CREATION")
    stale2 = dict(_item(env, vid2))
    env.ddb.Table("Videos").update_item(Key={"video_id": vid2}, UpdateExpression="SET #s = :c", ExpressionAttributeNames={"#s": "status"}, ExpressionAttributeValues={":c": "ASSETS_CREATION"})
    seen.clear()
    monkeypatch.setattr(env.vr, "_own_item", lambda u, v: (seen.append(1), stale2)[1] if not seen else real(u, v))   # ... or a moment before its next step
    r = _cancel(env, vid2)
    assert r["statusCode"] == 409 and _body(r)["code"] == "try_again" and _item(env, vid2)["status"] == "ASSETS_CREATION" and stops == []
    monkeypatch.setattr(env.vr, "_own_item", real)
    assert _cancel(env, vid2)["statusCode"] == 200 and len(stops) == 1                                             # sent once more: cancelled


def test_a_cancelled_video_can_be_tried_again_or_removed_and_the_list_offers_both(env, stops):  # noqa: F811
    vid = _video(env)
    _cancel(env, vid)
    assert env.vr.can_retry(_item(env, vid)) is True
    r = env.sl.handler(_event(vid), None)                                           # Try again: charged like a new video
    assert r["statusCode"] == 202 and _item(env, vid)["status"] == "STARTED_PROCESSING" and "cancelled_at" not in _item(env, vid) and wallet.balance(USER)["balance"] == 3
    assert _cancel(env, vid)["statusCode"] == 200 and stops[-1]["executionArn"] == ARN + vid + "-r1" and wallet.balance(USER)["balance"] == 5   # and cancelled again: refunded again, once
    assert _delete(env, vid)["statusCode"] == 200 and _item(env, vid) is None and wallet.balance(USER)["balance"] == 5


# ---------------------------------------------------------------- delete
def test_the_owner_can_delete_a_finished_video_and_everything_of_it_goes(env):  # noqa: F811
    vid, other = _video(env, "COMPLETE", edit_state="READY"), _video(env, "COMPLETE", credits=0)
    mine = [f"videos/{USER}/{vid}/r1.mp4", f"videos/{USER}/{vid}/r1.gif", f"videos/{USER}/{vid}/r2_preview.mp4"]
    keep = [f"videos/{USER}/{other}/r1.mp4", f"videos/u2/{vid}/r1.mp4", f"uploads/{USER}/0000000000000001.jpg", f"library/{USER}/orig/abc.jpg", f"watermark/{USER}/logo.png"]
    for k in mine + keep:
        env.s3.put_object(Bucket=BUCKET, Key=k, Body=b"x")
    r = _delete(env, vid)
    assert r["statusCode"] == 200 and _body(r) == {"message": "deleted", "video_id": vid}
    assert _item(env, vid) is None and _keys(env, f"generation/v2/{vid}/") == [] and _keys(env, f"videos/{USER}/{vid}/") == []
    assert all(_keys(env, k) == [k] for k in keep) and _item(env, other)["status"] == "COMPLETE" and len(_keys(env, f"generation/v2/{other}/")) == 4   # nothing else: not another video, not the uploads, not My media
    assert wallet.balance(USER)["balance"] == 3                                      # a delivered video is not refunded by deleting it
    again = _delete(env, vid)
    assert again["statusCode"] == 404 and _body(again)["code"] == "not_found"        # a second DELETE: already gone


def test_nobody_else_can_delete_it(env):  # noqa: F811
    vid = _video(env, "COMPLETE")
    env.s3.put_object(Bucket=BUCKET, Key=f"videos/{USER}/{vid}/r1.mp4", Body=b"x")
    assert _delete(env, vid, user="u2")["statusCode"] == 404 and _delete(env, vid, user="u2", path_user=USER)["statusCode"] == 403 and _delete(env, vid, authed=False)["statusCode"] == 401
    assert _item(env, vid)["status"] == "COMPLETE" and _keys(env, f"videos/{USER}/{vid}/") == [f"videos/{USER}/{vid}/r1.mp4"] and len(_keys(env, f"generation/v2/{vid}/")) == 4


@pytest.mark.parametrize("status", ["STARTED_PROCESSING", "PLOT_CREATION", "ASSETS_CREATION"])
def test_a_video_that_is_being_made_is_cancelled_first(env, stops, status):  # noqa: F811
    vid = _video(env, status)
    r = _delete(env, vid)
    assert r["statusCode"] == 409 and _body(r)["code"] == "not_deletable" and _item(env, vid)["status"] == status and len(_keys(env, f"generation/v2/{vid}/")) == 4
    assert _cancel(env, vid)["statusCode"] == 200 and _delete(env, vid)["statusCode"] == 200 and _item(env, vid) is None and _keys(env, f"generation/v2/{vid}/") == []


def test_a_video_whose_edit_is_rendering_waits_and_a_stuck_edit_does_not_block_forever(env):  # noqa: F811
    vid = _video(env, "COMPLETE", edit_state="RENDERING", edit_started_at=int(time.time()) - 60)
    r = _delete(env, vid)
    assert r["statusCode"] == 409 and _body(r)["code"] == "busy" and _item(env, vid)
    env.ddb.Table("Videos").update_item(Key={"video_id": vid}, UpdateExpression="SET edit_started_at = :t", ExpressionAttributeValues={":t": int(time.time()) - 3600})
    assert _delete(env, vid)["statusCode"] == 200 and _item(env, vid) is None


def test_deleting_a_failed_video_still_refunds_once_and_a_finished_one_never(env):  # noqa: F811
    failed = _video(env, "FAILED")                                                    # a failure that never reached its refund
    assert _delete(env, failed)["statusCode"] == 200 and wallet.balance(USER)["balance"] == 5
    done = _video(env, "COMPLETE")
    assert _delete(env, done)["statusCode"] == 200 and wallet.balance(USER)["balance"] == 3


# ---------------------------------------------------------------- the next free credit
def test_the_wallet_says_when_the_next_free_credit_arrives(aws):
    day0 = datetime.datetime(2026, 3, 10, 15, 0, tzinfo=datetime.timezone.utc).timestamp()
    b = wallet.balance("w1", now=day0, tz="America/Los_Angeles")                      # 08:00 in Los Angeles; signed up today
    assert b["next_free_credit_at"] == "2026-03-11T07:00:00Z" and b["next_free_credits"] == 1 and b["rules"]["daily"] == 1      # the next local midnight (PDT = UTC-7)
    assert b["next_daily_at"] == int(datetime.datetime(2026, 3, 11, 7, 0, tzinfo=datetime.timezone.utc).timestamp())             # the older field, the same moment
    just_before, at = b["next_daily_at"] - 1, b["next_daily_at"]
    assert not any(k["kind"] == "daily" for k in wallet.balance("w1", now=just_before, tz="America/Los_Angeles")["buckets"])
    after = wallet.balance("w1", now=at, tz="America/Los_Angeles")
    assert any(k["kind"] == "daily" for k in after["buckets"]) and after["next_free_credit_at"] == "2026-03-12T07:00:00Z"        # it arrived exactly then; the next one a local day later
    utc = wallet.balance("w2", now=day0)                                              # no timezone sent: the day is the UTC day
    assert utc["next_free_credit_at"] == "2026-03-11T00:00:00Z"
    tokyo = wallet.balance("w3", now=day0, tz="Asia/Tokyo")                           # 00:00 on the 11th in Tokyo is 15:00 UTC on the 10th: the same UTC day as the sign-up,
    assert tokyo["next_free_credit_at"] == "2026-03-11T15:00:00Z"                     # so the claim waits for the local midnight after the UTC day has moved on too
    assert wallet.next_free_credit("w3", now=day0, tz="Asia/Tokyo")["next_free_credit_at"] == tokyo["next_free_credit_at"]


def test_with_daily_credits_switched_off_there_is_no_next_one(aws, monkeypatch):
    monkeypatch.setenv("WALLET_DAILY_CREDITS", "0")
    b = wallet.balance("w1")
    assert b["next_free_credit_at"] is None and b["next_daily_at"] is None and b["next_free_credits"] == 0


def test_every_new_message_is_in_english_and_spanish():
    for key in ("retry.cancel_not_making", "retry.cancel_try_again", "retry.delete_busy", "retry.not_deletable"):
        assert i18n.t(key, "en") != i18n.t(key, "es") and i18n.t(key, "es") != key
