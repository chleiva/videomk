"""\"Try again\" reuses the failed video (lambdas/video_retry.py): same id, same row, every photo it was made with, charged once, never a silent retry without the attachments."""
import datetime
import json
import uuid
from decimal import Decimal

import boto3
import pytest

from common import wallet
from generate_video.handlers import mark_failed_handler

USER = "u1"
BUCKET = "assets-test"
N = 64   # the owner's case: more than 60 photos


def _mid(i: int) -> str:
    return f"{i:016x}"


class _Sfn:
    def __init__(self):
        self.calls, self.described = [], {}

    def start_execution(self, **kw):
        self.calls.append(kw)
        return {"executionArn": "arn:x", "startDate": datetime.datetime(2026, 1, 1)}

    def describe_execution(self, executionArn):
        if executionArn not in self.described:
            raise RuntimeError("history expired")
        return {"input": json.dumps(self.described[executionArn])}


@pytest.fixture
def env(aws, monkeypatch):
    import sf_launcher
    import video_retry

    s3 = boto3.client("s3", region_name="us-west-2")
    s3.create_bucket(Bucket=BUCKET, CreateBucketConfiguration={"LocationConstraint": "us-west-2"})
    monkeypatch.setenv("ASSETS_BUCKET", BUCKET)
    monkeypatch.setenv("MEDIA_BUCKET", BUCKET)
    sfn = _Sfn()
    for mod in (sf_launcher, video_retry):
        monkeypatch.setattr(mod, "_s3", s3)
        monkeypatch.setattr(mod, "_dynamodb", aws)
        monkeypatch.setattr(mod, "_sfn", sfn)
    monkeypatch.setenv("DUPLICATE_WINDOW_S", "0")

    class E:
        pass

    e = E()
    e.s3, e.sfn, e.ddb, e.sl, e.vr = s3, sfn, aws, sf_launcher, video_retry
    return e


def _event(video_id, user=USER, path_user=None, method="POST", resource="/users/{user_id}/videos/{video_id}/retry", authed=True):
    return {"resource": resource, "httpMethod": method, "pathParameters": {"user_id": path_user or user, "video_id": video_id},
            "headers": {}, "requestContext": {"authorizer": {"claims": {"sub": user}}} if authed else {}}


def _put_uploads(env, ids, user=USER):
    for mid in ids:
        env.s3.put_object(Bucket=BUCKET, Key=f"uploads/{user}/{mid}.jpg", Body=b"jpg-" + mid.encode())


def _failed_video(env, video_id=None, *, n=N, minutes=2.0, extra_options=None, retries=0, status="FAILED", with_request=True, user=USER, charge=True):
    """A video as the launcher records it, after it failed (and was refunded)."""
    video_id = video_id or str(uuid.uuid4())
    media = [_mid(i) for i in range(1, n + 1)]
    options = {"target_minutes": minutes, "media": media, "media_meta": {m: {"taken": f"2026-10-09T09:{i % 60:02d}:00"} for i, m in enumerate(media[:40])}, "language": "es", "aspect": "16:9", "style": "real",
               "watermark": {"mode": "videomk"}, "brief": {"tone": "funny"}, "locale": "es", **(extra_options or {})}
    item = {"video_id": video_id, "user_id": user, "prompt": "Mattia cuenta todo acerca de su hermanito", "status": status, "created_at": "2026-11-27T02:16:00Z", "usage_day": "2026-11-27",
            "failure_code": "TypeError", "credits_charged": 2, "refunded": True, "charge": "[]", "title": "Mattia", "retries": retries}
    if with_request:
        item["request_json"] = json.dumps({"options": options, "library_media": []}, sort_keys=True)
    env.ddb.Table("Videos").put_item(Item=item)
    return video_id, options


def _item(env, video_id):
    return env.ddb.Table("Videos").get_item(Key={"video_id": video_id}).get("Item")


def _body(r):
    return json.loads(r["body"])


def _sent(env, i=-1):
    return json.loads(env.sfn.calls[i]["input"])


# ---------------------------------------------------------------- the same video, every photo
def test_retry_reuses_the_same_video_with_every_photo(env):
    vid, options = _failed_video(env)
    _put_uploads(env, options["media"])
    before = wallet.balance(USER)["balance"]
    r = env.sl.handler(_event(vid), None)
    assert r["statusCode"] == 202
    body = _body(r)
    assert body["video_id"] == vid and body["status"] == "STARTED_PROCESSING" and body["retries"] == 1
    assert env.ddb.Table("Videos").scan()["Count"] == 1                       # no second row, ever
    item = _item(env, vid)
    assert item["status"] == "STARTED_PROCESSING" and item["retries"] == 1 and "failure_code" not in item and "refunded" not in item
    assert item["first_created_at"] == "2026-11-27T02:16:00Z" and item["created_at"] > "2026-11-27T02:16:00Z"   # moves to the top of the list as a making item
    assert env.sfn.calls[0]["name"] == f"{vid}-r1"
    sent = _sent(env)
    assert sent["video_id"] == vid and sent["media"] == options["media"] and len(sent["media"]) == N   # INVARIANT: the retry carries every photo of the original
    for key in ("media_meta", "language", "aspect", "style", "watermark", "brief", "target_minutes"):
        assert sent[key] == options[key], key
    assert sent["prompt"] == "Mattia cuenta todo acerca de su hermanito"
    assert wallet.balance(USER)["balance"] == before - 2                        # charged like a new 2-minute video, once


def test_the_launcher_stores_the_whole_request_and_a_retry_has_the_same_photo_count(env):
    media = [_mid(i) for i in range(1, N + 1)]
    _put_uploads(env, media)
    body = {"prompt": "A short explainer about how black holes form", "target_minutes": 1, "media": media, "language": "es", "client_request_id": "retry-round-trip-1"}
    ev = {"pathParameters": {"user_id": USER}, "headers": {}, "body": json.dumps(body), "resource": "/users/{user_id}/videos/generate", "httpMethod": "POST",
          "requestContext": {"authorizer": {"claims": {"sub": USER}}}}
    r = env.sl.handler(ev, None)
    assert r["statusCode"] == 202
    vid = _body(r)["video_id"]
    original = _sent(env)
    assert len(original["media"]) == N
    stored = json.loads(_item(env, vid)["request_json"])
    assert stored["options"]["media"] == media and stored["options"]["language"] == "es"
    # the video fails: the originals still in place are kept with the video, the credits go back
    env.s3.delete_object(Bucket=BUCKET, Key=f"uploads/{USER}/{media[0]}.jpg")   # one upload already gone (the 2-day expiry)
    mark_failed_handler.handler({"video_id": vid, "error": {"Error": "X"}}, None)
    # ... and then the rest of the uploads expire
    for m in media:
        env.s3.delete_object(Bucket=BUCKET, Key=f"uploads/{USER}/{m}.jpg")
    # the first upload was gone before the failure: the retry cannot give it back and says so (never a silent 63-photo video)
    r2 = env.sl.handler(_event(vid), None)
    assert r2["statusCode"] == 409 and _body(r2)["code"] == "attachments_unavailable"
    assert len(env.sfn.calls) == 1 and _item(env, vid)["status"] == "FAILED"


def test_the_kept_originals_give_every_photo_back(env):
    media = [_mid(i) for i in range(1, N + 1)]
    _put_uploads(env, media)
    r = env.sl.handler({"pathParameters": {"user_id": USER}, "headers": {}, "body": json.dumps({"prompt": "A short explainer about how black holes form", "target_minutes": 1, "media": media}),
                        "resource": "/users/{user_id}/videos/generate", "httpMethod": "POST", "requestContext": {"authorizer": {"claims": {"sub": USER}}}}, None)
    vid = _body(r)["video_id"]
    mark_failed_handler.handler({"video_id": vid, "error": {"Error": "X"}}, None)
    kept = env.s3.list_objects_v2(Bucket=BUCKET, Prefix=f"generation/v2/{vid}/retry_uploads/")["KeyCount"]
    assert kept == N
    for m in media:   # two days later the uploads are gone
        env.s3.delete_object(Bucket=BUCKET, Key=f"uploads/{USER}/{m}.jpg")
    r2 = env.sl.handler(_event(vid), None)
    assert r2["statusCode"] == 202 and _body(r2)["photos"] == N
    assert _sent(env)["media"] == media                                          # the same photos, the same order
    assert all(env.s3.head_object(Bucket=BUCKET, Key=f"uploads/{USER}/{m}.jpg") for m in media)   # copied back for the engine
    assert env.s3.list_objects_v2(Bucket=BUCKET, Prefix=f"generation/v2/{vid}/retry_uploads/")["KeyCount"] == N   # still kept (a next retry may need them)


def test_cleaned_copies_give_the_photos_back_when_the_originals_are_gone(env):
    vid, options = _failed_video(env, n=N)
    clean = N - 1                                                                # one upload was unusable the first time too
    for i in range(1, clean + 1):
        env.s3.put_object(Bucket=BUCKET, Key=f"generation/v2/{vid}/assets/user_P{i}.jpg", Body=b"clean-%d" % i)
    env.ddb.Table("Videos").update_item(Key={"video_id": vid}, UpdateExpression="SET photo_restore = :p", ExpressionAttributeValues={":p": json.dumps(
        [{"s": options["media"][i], "t": f"2026-10-09T10:{i % 60:02d}:00" if i < 20 else None, "w": "Londres, Reino Unido" if i == 5 else None} for i in range(clean)])})
    r = env.sl.handler(_event(vid), None)
    assert r["statusCode"] == 202
    body = _body(r)
    assert body["photos"] == clean and body["photos_unusable"] == 1
    assert body["photos"] + body["photos_unusable"] == N                         # INVARIANT: nothing is dropped without being counted
    sent = _sent(env)
    assert len(sent["media"]) == clean and len(set(sent["media"])) == clean
    for k, mid in enumerate(sent["media"], start=1):                             # the cleaned photo k is the upload for the k-th new id
        assert env.s3.get_object(Bucket=BUCKET, Key=f"uploads/{USER}/{mid}.jpg")["Body"].read() == b"clean-%d" % k
    assert sent["media_meta"][sent["media"][5]]["where"] == "Londres, Reino Unido"
    assert sent["media_meta"][sent["media"][0]]["taken"] == "2026-10-09T10:00:00"
    assert all(m not in options["media"] for m in sent["media"])
    assert env.s3.list_objects_v2(Bucket=BUCKET, Prefix=f"generation/v2/{vid}/assets/user_P")["KeyCount"] == clean   # kept: the engine writes them again over these
    assert json.loads(_item(env, vid)["request_json"])["options"]["media"] == sent["media"]                       # a later retry starts from the restored photos


def test_old_video_without_a_stored_request_is_rebuilt_from_the_workflow_history(env):
    vid, options = _failed_video(env, with_request=False, n=10)
    _put_uploads(env, options["media"])
    arn = env.sl.os.environ["STATE_MACHINE_ARN"].replace(":stateMachine:", ":execution:") + ":" + vid
    env.sfn.described[arn] = {"user_id": USER, "video_id": vid, "prompt": "x", "usage_day": "2026-11-27", **options}
    r = env.sl.handler(_event(vid), None)
    assert r["statusCode"] == 202 and _sent(env)["media"] == options["media"]


def test_no_request_anywhere_is_a_409_not_a_guess(env):
    vid, _ = _failed_video(env, with_request=False)
    r = env.sl.handler(_event(vid), None)
    assert r["statusCode"] == 409 and _body(r)["code"] == "no_request" and env.sfn.calls == []


def test_a_missing_photo_is_never_dropped_silently(env):
    vid, options = _failed_video(env)
    _put_uploads(env, options["media"][:-3])                                     # three uploads are gone, no copies anywhere
    before = wallet.balance(USER)["balance"]
    r = env.sl.handler(_event(vid), None)
    assert r["statusCode"] == 409 and _body(r)["code"] == "attachments_unavailable"
    assert env.sfn.calls == [] and wallet.balance(USER)["balance"] == before and _item(env, vid)["status"] == "FAILED" and _item(env, vid)["retries"] == 0


def test_library_photos_are_copied_again(env, monkeypatch):
    vid, options = _failed_video(env, n=4)
    req = json.loads(_item(env, vid)["request_json"])
    req["library_media"] = options["media"][2:]
    env.ddb.Table("Videos").update_item(Key={"video_id": vid}, UpdateExpression="SET request_json = :r", ExpressionAttributeValues={":r": json.dumps(req)})
    _put_uploads(env, options["media"][:2])
    for m in options["media"][2:]:
        env.s3.put_object(Bucket=BUCKET, Key=f"media/{USER}/orig/{m}.jpg", Body=b"lib")
    monkeypatch.setattr(env.vr.library, "batch_get", lambda user, ids: {i: {} for i in ids})
    monkeypatch.setattr(env.vr.library, "orig_key", lambda user, mid: f"media/{user}/orig/{mid}.jpg")
    r = env.sl.handler(_event(vid), None)
    assert r["statusCode"] == 202 and _sent(env)["media"] == options["media"]
    assert env.s3.head_object(Bucket=BUCKET, Key=f"uploads/{USER}/{options['media'][3]}.jpg")


# ---------------------------------------------------------------- state machine
def test_a_second_tap_while_making_starts_and_charges_nothing(env):
    vid, options = _failed_video(env)
    _put_uploads(env, options["media"])
    assert env.sl.handler(_event(vid), None)["statusCode"] == 202
    balance = wallet.balance(USER)["balance"]
    r = env.sl.handler(_event(vid), None)
    assert r["statusCode"] == 200 and _body(r)["status"] == "STARTED_PROCESSING"
    assert len(env.sfn.calls) == 1 and wallet.balance(USER)["balance"] == balance and _item(env, vid)["retries"] == 1


def test_only_the_owner_can_retry(env):
    vid, options = _failed_video(env)
    _put_uploads(env, options["media"])
    assert env.sl.handler(_event(vid, authed=False), None)["statusCode"] == 401
    assert env.sl.handler(_event(vid, user="u2", path_user="u1"), None)["statusCode"] == 403
    r = env.sl.handler(_event(vid, user="u2"), None)
    assert r["statusCode"] == 404 and env.sfn.calls == []                         # another person's video is simply not found


@pytest.mark.parametrize("status,code", [("COMPLETE", "not_failed"), ("REJECTED", "rejected")])
def test_made_and_rejected_videos_are_not_retried(env, status, code):
    vid, _ = _failed_video(env, status=status)
    r = env.sl.handler(_event(vid), None)
    assert r["statusCode"] == 409 and _body(r)["code"] == code and env.sfn.calls == []


def test_a_cancelled_video_can_be_retried(env):
    vid, options = _failed_video(env, status="CANCELLED", n=3)
    _put_uploads(env, options["media"])
    assert env.sl.handler(_event(vid), None)["statusCode"] == 202


def test_at_most_three_retries(env):
    vid, options = _failed_video(env, retries=3)
    _put_uploads(env, options["media"])
    r = env.sl.handler(_event(vid), None)
    assert r["statusCode"] == 409 and _body(r)["code"] == "retry_limit" and env.sfn.calls == []


def test_each_retry_runs_as_its_own_execution(env):
    vid, options = _failed_video(env, retries=1, n=3)
    _put_uploads(env, options["media"])
    env.sl.handler(_event(vid), None)
    assert env.sfn.calls[0]["name"] == f"{vid}-r2" and _item(env, vid)["retries"] == 2


def test_a_presentation_video_cannot_be_retried(env):
    vid, _ = _failed_video(env, extra_options={"deck": "0123456789abcdef"}, n=1)
    r = env.sl.handler(_event(vid), None)
    assert r["statusCode"] == 409 and _body(r)["code"] == "deck_used"


def test_not_enough_credits_leaves_the_failed_video_as_it_was(env):
    vid, options = _failed_video(env, minutes=12.0, n=3)
    _put_uploads(env, options["media"])
    r = env.sl.handler(_event(vid), None)                                         # 12 credits, the account has the 5 welcome credits
    assert r["statusCode"] == 402 and _body(r)["code"] == "insufficient_credits"
    item = _item(env, vid)
    assert item["status"] == "FAILED" and item["retries"] == 0 and item["created_at"] == "2026-11-27T02:16:00Z" and env.sfn.calls == []


def test_a_workflow_that_cannot_start_refunds_and_leaves_it_failed(env):
    vid, options = _failed_video(env, n=3)
    _put_uploads(env, options["media"])
    before = wallet.balance(USER)["balance"]

    def boom(**kw):
        raise RuntimeError("sfn down")

    env.sfn.start_execution = boom
    r = env.sl.handler(_event(vid), None)
    assert r["statusCode"] == 500
    item = _item(env, vid)
    assert item["status"] == "FAILED" and item["retries"] == 0 and wallet.balance(USER)["balance"] == before


def test_a_failure_that_was_never_refunded_is_refunded_once_by_the_retry(env):
    wallet.balance(USER)
    taken = wallet.charge(USER, 2)
    vid, options = _failed_video(env, n=2)
    env.ddb.Table("Videos").update_item(Key={"video_id": vid}, UpdateExpression="SET charge = :c REMOVE refunded", ExpressionAttributeValues={":c": json.dumps(taken)})
    _put_uploads(env, options["media"])
    assert wallet.balance(USER)["balance"] == 3
    assert env.sl.handler(_event(vid), None)["statusCode"] == 202
    assert wallet.balance(USER)["balance"] == 3                                    # refund 2, charge 2: never both charged and lost


def test_the_old_attempts_leftovers_are_cleared_but_the_photos_are_kept(env):
    vid, options = _failed_video(env, n=2)
    _put_uploads(env, options["media"])
    for key in ("plan_r1.json", "assets/clip_1.mp4", "assets/user_P1.jpg", "retry_uploads/x.jpg"):
        env.s3.put_object(Bucket=BUCKET, Key=f"generation/v2/{vid}/{key}", Body=b"x")
    env.ddb.Table("Videos").update_item(Key={"video_id": vid}, UpdateExpression="SET plan_key = :p, cost_usd = :c, c_script = :c, n_beats = :n", ExpressionAttributeValues={":p": "k", ":c": Decimal("0.4"), ":n": 9})
    assert env.sl.handler(_event(vid), None)["statusCode"] == 202
    keys = {o["Key"] for o in env.s3.list_objects_v2(Bucket=BUCKET, Prefix=f"generation/v2/{vid}/").get("Contents", [])}
    assert keys == {f"generation/v2/{vid}/assets/user_P1.jpg", f"generation/v2/{vid}/retry_uploads/x.jpg"}
    item = _item(env, vid)
    assert all(k not in item for k in ("plan_key", "cost_usd", "c_script", "n_beats")) and float(item["cost_usd_before"]) == 0.4


def test_the_list_says_when_try_again_is_worth_offering(env):
    import list_videos   # noqa: F401  (imports cleanly)
    from video_retry import can_retry
    assert can_retry({"status": "FAILED", "retries": 2}) and not can_retry({"status": "FAILED", "retries": 3})
    assert not can_retry({"status": "COMPLETE"}) and not can_retry({"status": "FAILED", "stage": "deck_writing"}) and not can_retry({"status": "REJECTED"})


# ---------------------------------------------------------------- remove a failed video
def test_a_failed_video_can_be_removed_and_a_made_one_cannot(env):
    vid, _ = _failed_video(env, n=1)
    env.s3.put_object(Bucket=BUCKET, Key=f"generation/v2/{vid}/assets/user_P1.jpg", Body=b"x")
    ev = _event(vid, method="DELETE", resource="/users/{user_id}/videos/{video_id}")
    assert env.sl.handler(_event(vid, user="u2", method="DELETE", resource="/users/{user_id}/videos/{video_id}"), None)["statusCode"] == 404
    assert env.sl.handler(ev, None)["statusCode"] == 200
    assert _item(env, vid) is None and env.s3.list_objects_v2(Bucket=BUCKET, Prefix=f"generation/v2/{vid}/")["KeyCount"] == 0
    done, _ = _failed_video(env, status="COMPLETE", n=1)
    r = env.sl.handler(_event(done, method="DELETE", resource="/users/{user_id}/videos/{video_id}"), None)
    assert r["statusCode"] == 409 and _body(r)["code"] == "not_deletable" and _item(env, done)


# ---------------------------------------------------------------- the crash that failed the owner's 64-photo video
def test_photos_without_a_capture_time_do_not_crash_the_story():
    from engine import curate
    assert curate._dt(None) is None and curate._dt("") is None and curate._dt("2026-10-09T09:22:04").year == 2026
    photos = [{"id": f"P{i}", "taken": ("2026-10-09T09:%02d:00" % i) if i % 5 else None, "w": 10, "h": 10, "orientation": "landscape"} for i in range(1, 30)]
    groups = curate.group_photos(photos)       # raised TypeError: 'NoneType' object is not subscriptable
    assert sum(len(g["ids"]) for g in groups) == len(photos)   # every photo is in a group, dated or not


def test_every_retry_message_is_in_english_and_spanish():
    from common import i18n
    keys = [k for k in i18n.EN if k.startswith("retry.")]
    assert keys and all(k in i18n.ES for k in keys)
    assert "5" in i18n.t("retry.limit", "es", max=5) and "veces" in i18n.t("retry.limit", "es", max=3)
