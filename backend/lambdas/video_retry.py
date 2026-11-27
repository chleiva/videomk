"""POST /users/{user_id}/videos/{video_id}/retry   and   DELETE /users/{user_id}/videos/{video_id}  (served by the launcher Lambda, see sf_launcher.handler).

"Try again" on a video that did not finish reuses THAT video: same id, same row, status back to making. It never creates a second item.

Retry (docs/CREATE_API.md "Retry a video"):
  * only the owner (404 for anything else, so ids cannot be probed), only a FAILED or CANCELLED video (REJECTED is a safety decision: never retried; COMPLETE has nothing to retry);
  * idempotent: a second tap while the video is making answers 200 with the current state, and starts nothing and charges nothing;
  * the stored request (prompt + the options the launcher sent to the workflow) is run again after the same checks as a new request (safety stop/pause, photos still there);
  * credits: the failed attempt was refunded when it failed (wallet.refund_video, once); the retry is charged again like a new video, and refunded again if it fails again;
  * at most MAX_RETRIES retries per video (each failed attempt still costs us model calls), then 409 `retry_limit`;
  * the old attempt's leftovers are cleared (S3 generation/v2/<video>/, the plan/title/failure attributes, the per-video cost counter restarts so the cost cap is per attempt);
  * a new Step Functions execution named `<video id>-r<n>` (a name can be used once, and the history of the first run stays readable).
Cancel (POST .../videos/{video_id}/cancel): a video that is being made: stop the workflow, mark it CANCELLED, credits back exactly once, working files cleared, photos kept.
Delete: a COMPLETE, FAILED, CANCELLED or REJECTED video of the caller: removes the row, its working files and its finished files (a video being made is cancelled first).
"""
import json
import logging
import os
import time
import uuid
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

from common.http import json_response
from common.identity import extract_cognito_sub
import plan_gate
from common import i18n, library, usage, wallet
from common.photo_ids import upload_key
from engine import format_options

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MAX_RETRIES = int(os.environ.get("MAX_VIDEO_RETRIES", "3"))
RETRIABLE = ("FAILED", "CANCELLED")
FINAL = ("COMPLETE", "REJECTED")
DELETABLE = ("COMPLETE", "FAILED", "CANCELLED", "REJECTED")
MAX_REQUEST_BYTES = 150_000   # what is kept on the item (the item limit is 400 KB); a larger request is read back from the workflow's own history instead
CLEAR_MAX_KEYS = 2000

# what the failed attempt left on the item (the retry builds all of it again); `title` stays so the row does not change its name
STALE_ATTRS = ("failure_code", "plan_key", "rev", "n_beats", "photos_skipped", "assets", "plot", "stage", "reject_reason", "video_uri", "preview_gif_uri", "duration_s",
               "edit_state", "edit_error", "preview_uri", "preview_rev", "cancel_reason", "cancelled_at")
COST_ATTRS = ("cost_usd", "c_speech", "c_script", "c_research", "c_photos", "c_stock", "c_deck")

_s3 = boto3.client("s3")
_sfn = boto3.client("stepfunctions")
_dynamodb = boto3.resource("dynamodb")


def _table():
    return _dynamodb.Table(os.environ.get("VIDEOS_TABLE", "Videos"))


def can_retry(item: Dict[str, Any]) -> bool:
    """For the list: is a 'Try again' worth offering? (A presentation video cannot: its deck was used up.)"""
    if str(item.get("status") or "") not in RETRIABLE:
        return False
    if int(item.get("retries") or 0) >= MAX_RETRIES:
        return False
    return not (item.get("deck") or str(item.get("stage") or "").startswith("deck"))


def _state(item: Dict[str, Any]) -> Dict[str, Any]:
    return {"video_id": item.get("video_id"), "status": item.get("status"), "retries": int(item.get("retries") or 0)}


def _auth(event: Dict[str, Any], loc: str) -> Tuple[Optional[str], Optional[str], Optional[Dict[str, Any]]]:
    """(user, video id, None) or (None, None, the 401/403/400 response)."""
    path = (event or {}).get("pathParameters") or {}
    sub = extract_cognito_sub(event)
    if not sub:
        return None, None, json_response(401, {"message": i18n.t("err.unauthorized", loc)})
    if not path.get("user_id") or path["user_id"] != sub:
        return None, None, json_response(403, {"message": i18n.t("err.forbidden", loc)})
    vid = str(path.get("video_id") or "")
    if not vid or "/" in vid or ".." in vid or len(vid) > 80:
        return None, None, json_response(400, {"message": "Invalid video id"})
    return sub, vid, None


def _own_item(user: str, video_id: str) -> Optional[Dict[str, Any]]:
    item = _table().get_item(Key={"video_id": video_id}).get("Item")
    return item if item and str(item.get("user_id") or "") == user else None   # another person's video is simply not found


def _load_request(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The request the workflow was started with: stored on the item, else (older videos, within the workflow's 90-day history) read back from the first execution."""
    raw = item.get("request_json")
    if raw:
        try:
            req = json.loads(raw)
            if isinstance(req, dict) and isinstance(req.get("options"), dict):
                return req
        except ValueError:
            pass
    arn = os.environ.get("STATE_MACHINE_ARN", "")
    if not arn:
        return None
    try:
        ex = _sfn.describe_execution(executionArn=arn.replace(":stateMachine:", ":execution:") + ":" + str(item["video_id"]))
        data = json.loads(ex.get("input") or "{}")
    except Exception:   # noqa: BLE001 - history expired, no permission or not JSON: the client falls back to a new request
        return None
    options = {k: v for k, v in data.items() if k not in ("user_id", "video_id", "prompt", "usage_day")}
    return {"options": options, "library_media": []}


def _have(key: str) -> bool:
    try:
        _s3.head_object(Bucket=os.environ["ASSETS_BUCKET"], Key=key)
        return True
    except ClientError:
        return False


def _copy_up(src_key: str, user: str, mid: str) -> None:
    _s3.copy_object(CopySource={"Bucket": os.environ["ASSETS_BUCKET"], "Key": src_key}, Bucket=os.environ["ASSETS_BUCKET"], Key=upload_key(user, mid), ContentType="image/jpeg", MetadataDirective="REPLACE")


def _order_like_prepare(media: List[str], meta: Dict[str, Any]) -> List[str]:
    """The order engine/usermedia.prepare numbers the photos in (P1, P2, ...): by capture time when most photos have one, else as given."""
    stamped = [m for m in media if (meta.get(m) or {}).get("taken")]
    if media and len(stamped) * 2 >= len(media):
        order = {m: i for i, m in enumerate(media)}
        return sorted(media, key=lambda m: ((meta.get(m) or {}).get("taken") is None, (meta.get(m) or {}).get("taken") or "", order[m]))
    return list(media)


def _clean_copies(video_id: str) -> List[str]:
    """The keys of the video's cleaned photos user_P1.jpg .. user_Pn.jpg, in order, only while they are contiguous (n >= 1)."""
    found: Dict[int, str] = {}
    try:
        token = None
        while True:
            res = _s3.list_objects_v2(Bucket=os.environ["ASSETS_BUCKET"], Prefix=f"generation/v2/{video_id}/assets/user_P", **({"ContinuationToken": token} if token else {}))
            for o in res.get("Contents", []):
                name = o["Key"].rsplit("/", 1)[-1]
                if name.startswith("user_P") and name.endswith(".jpg") and name[6:-4].isdigit():
                    found[int(name[6:-4])] = o["Key"]
            token = res.get("NextContinuationToken")
            if not token:
                break
    except ClientError:
        return []
    n = len(found)
    return [found[i] for i in range(1, n + 1)] if n and set(found) == set(range(1, n + 1)) else []


def _from_clean_copies(user: str, video_id: str, item: Dict[str, Any], opts: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Gives a video its photos back from its cleaned copies (the engine deletes the originals once it has made them). Used only when NO original is left, which means every upload
    was processed: the cleaned copies ARE the photos, and the originals that are not among them were unusable the first time too. New photo ids, the capture time and place name each photo
    had come back with it (from `photo_restore`, saved when the photos were prepared; older videos: rebuilt from the request, the one place a name or time can be a photo off)."""
    keys = _clean_copies(video_id)
    if not keys:
        return None
    media = list(opts.get("media") or [])
    meta_in = dict(opts.get("media_meta") or {})
    rows: List[Dict[str, Any]] = []
    try:
        saved = json.loads(item.get("photo_restore") or "null")
        if isinstance(saved, list) and len(saved) == len(keys):
            rows = [{"t": r.get("t"), "w": r.get("w")} for r in saved if isinstance(r, dict)]
    except ValueError:
        rows = []
    if len(rows) != len(keys):   # an older video: the order the engine numbered them in, minus the unusable ones (assumed to be the last by that order)
        ordered = _order_like_prepare(media, meta_in)[: len(keys)]
        rows = [{"t": (meta_in.get(m) or {}).get("taken"), "w": (meta_in.get(m) or {}).get("where")} for m in ordered]
        rows += [{"t": None, "w": None}] * (len(keys) - len(rows))
    new_ids, meta = [], {}
    for key, row in zip(keys, rows):
        mid = uuid.uuid4().hex[:16]
        _copy_up(key, user, mid)
        new_ids.append(mid)
        if row.get("t") or row.get("w"):
            meta[mid] = {k: v for k, v in (("taken", row.get("t")), ("where", row.get("w"))) if v}
    out = dict(opts)
    out["media"] = new_ids
    out.pop("media_meta", None)
    if meta:
        out["media_meta"] = meta
    return out


def restore_media(user: str, video_id: str, item: Dict[str, Any], req: Dict[str, Any], loc: str) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    """Every photo the video was made with, or a 409. Never a video with fewer photos without saying so. Returns (error response or None, the options to start with).
    Sources, in order: the upload still in place; the original kept when the video failed; a library photo (copied again); the cleaned copies (see _from_clean_copies)."""
    opts = dict(req["options"])
    media: List[str] = list(opts.get("media") or [])
    if not media:
        return None, opts
    lib = set(req.get("library_media") or [])
    missing = [m for m in media if not _have(upload_key(user, m))]
    if not missing:
        return None, opts
    unrecovered: List[str] = []
    for mid in missing:
        kept = f"generation/v2/{video_id}/retry_uploads/{mid}.jpg"
        if _have(kept):
            _copy_up(kept, user, mid)
        else:
            unrecovered.append(mid)
    from_library = [m for m in unrecovered if m in lib]
    unrecovered = [m for m in unrecovered if m not in lib]
    if from_library:
        found = library.batch_get(user, from_library)
        for mid in from_library:
            if mid in found:
                _copy_up_from_library(user, mid)
            else:
                unrecovered.append(mid)
    if not unrecovered:
        return None, opts
    if len(unrecovered) == len(media):   # nothing is left of the uploads: they were all made into cleaned copies
        rebuilt = _from_clean_copies(user, video_id, item, opts)
        if rebuilt:
            return None, rebuilt
    return json_response(409, {"code": "attachments_unavailable", "message": i18n.t("retry.media_expired", loc), "photos": len(media), "missing": len(unrecovered)}), opts


def _copy_up_from_library(user: str, mid: str) -> None:
    _s3.copy_object(CopySource={"Bucket": os.environ["MEDIA_BUCKET"], "Key": library.orig_key(user, mid)}, Bucket=os.environ["ASSETS_BUCKET"], Key=upload_key(user, mid),
                    ContentType="image/jpeg", MetadataDirective="REPLACE")


def _claim(video_id: str, item: Dict[str, Any], retries: int) -> bool:
    """Atomic: FAILED/CANCELLED -> making, once. Two taps at the same time: one wins, the other sees 'making'. Moves the row to the top of the list (a new attempt is made today)."""
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        _table().update_item(
            Key={"video_id": video_id},
            UpdateExpression="SET #s = :making, retries = :n, created_at = :now, first_created_at = if_not_exists(first_created_at, :was)",
            ConditionExpression="#s IN (:f, :c) AND (attribute_not_exists(retries) OR retries = :prev)",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":making": "STARTED_PROCESSING", ":n": retries + 1, ":now": now, ":was": item.get("created_at") or now, ":f": "FAILED", ":c": "CANCELLED", ":prev": retries},
        )
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise


def _revert(video_id: str, item: Dict[str, Any], retries: int, failure: Optional[str] = None) -> None:
    """Undo a claim (nothing was charged or started): the video is as it was, and the attempt does not count."""
    try:
        sets = "SET #s = :s, retries = :n, created_at = :t" + (", failure_code = :fc" if failure else "")
        vals = {":s": item.get("status") or "FAILED", ":n": retries, ":t": item.get("created_at"), ":m": "STARTED_PROCESSING", ":next": retries + 1}
        if failure:
            vals[":fc"] = failure
        _table().update_item(Key={"video_id": video_id}, UpdateExpression=sets, ConditionExpression="#s = :m AND retries = :next", ExpressionAttributeNames={"#s": "status"}, ExpressionAttributeValues=vals)
    except ClientError:
        logger.exception("VIDEO_RETRY_REVERT_FAILED video=%s", video_id)


def _clear_attempt(video_id: str, item: Dict[str, Any], charged: Any, credits: int, usage_day: str, resolution: Optional[str], request: Dict[str, Any]) -> None:
    """The new attempt's bookkeeping on the item, and the old attempt's leftovers removed. The per-video cost counter starts again (the cap is per attempt; the old total is kept)."""
    sets = ["charge = :ch", "credits_charged = :cr", "usage_day = :ud", "cost_usd_before = :cb"]
    vals: Dict[str, Any] = {":ch": json.dumps(charged or []), ":cr": credits, ":ud": usage_day, ":cb": Decimal(str(item.get("cost_usd_before", 0))) + Decimal(str(item.get("cost_usd", 0)))}
    names: Dict[str, str] = {}
    raw = json.dumps(request, sort_keys=True)   # the options as this attempt starts (photos restored under new ids are recorded, so the next retry finds them)
    if len(raw.encode("utf-8")) <= MAX_REQUEST_BYTES:
        sets.append("request_json = :rq")
        vals[":rq"] = raw
    if format_options.credits_multiplier(resolution) != 1:
        sets += ["resolution = :res", "credits_multiplier = :cm"]
        vals.update({":res": resolution, ":cm": format_options.credits_multiplier(resolution)})
    removes = ["refunded"] + [a for a in STALE_ATTRS + COST_ATTRS if a in item]
    for a in removes:
        names[f"#r_{a}"] = a
    expr = "SET " + ", ".join(sets) + (" REMOVE " + ", ".join(f"#r_{a}" for a in removes) if removes else "")
    kwargs: Dict[str, Any] = {"Key": {"video_id": video_id}, "UpdateExpression": expr, "ExpressionAttributeValues": vals}
    if names:
        kwargs["ExpressionAttributeNames"] = names
    _table().update_item(**kwargs)


def _is_photo_source(key: str) -> bool:
    """What a later retry may still need: the originals kept at failure and the cleaned photos (the next run writes the cleaned photos again, over these)."""
    return "/retry_uploads/" in key or (key.rsplit("/", 1)[-1].startswith("user_P") and "/assets/" in key)


def clear_prefix(video_id: str, keep_photos: bool = True) -> int:
    """Best effort: the working files of a video (its own prefix only). The cleanup never stops a retry or a delete."""
    bucket, prefix, n = os.environ.get("ASSETS_BUCKET", ""), f"generation/v2/{video_id}/", 0
    if not bucket or "/" in video_id or ".." in video_id:
        return 0
    try:
        token = None
        while n < CLEAR_MAX_KEYS:
            res = _s3.list_objects_v2(Bucket=bucket, Prefix=prefix, **({"ContinuationToken": token} if token else {}))
            keys = [{"Key": o["Key"]} for o in res.get("Contents", []) if not (keep_photos and _is_photo_source(o["Key"]))]
            if keys:
                _s3.delete_objects(Bucket=bucket, Delete={"Objects": keys, "Quiet": True})
                n += len(keys)
            token = res.get("NextContinuationToken")
            if not token:
                break
    except Exception:   # noqa: BLE001
        logger.warning("VIDEO_RETRY_CLEAR_FAILED video=%s", video_id)
    return n


def retry_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    import sf_launcher as sl   # the launcher's own checks and helpers (lazy: it imports this module too)
    loc = i18n.pick_locale(event)
    user, video_id, bad = _auth(event, loc)
    if bad:
        return bad
    item = _own_item(user, video_id)
    if not item:
        return json_response(404, {"code": "not_found", "message": i18n.t("retry.not_found", loc)})
    status, retries = str(item.get("status") or ""), int(item.get("retries") or 0)
    if status == "COMPLETE":
        return json_response(409, {"code": "not_failed", "message": i18n.t("retry.not_failed", loc), **_state(item)})
    if status == "REJECTED":
        return json_response(409, {"code": "rejected", "message": i18n.t("retry.rejected", loc), **_state(item)})
    if status not in RETRIABLE:   # already making (a second tap, or another phone): the same answer, nothing is started or charged
        return json_response(200, {"message": "already running", **_state(item)})
    if retries >= MAX_RETRIES:
        return json_response(409, {"code": "retry_limit", "message": i18n.t("retry.limit", loc, max=MAX_RETRIES), **_state(item)})
    sm_arn = os.environ.get("STATE_MACHINE_ARN")
    if not sm_arn:
        return json_response(500, {"message": i18n.t("err.server_config", loc)})

    req = _load_request(item)
    if not req or item.get("deck") or req["options"].get("deck") or str(item.get("stage") or "").startswith("deck"):
        return json_response(409, {"code": "no_request" if not req else "deck_used", "message": i18n.t("retry.no_request" if not req else "retry.deck_used", loc), **_state(item)})
    options: Dict[str, Any] = dict(req["options"])
    prompt = str(item.get("prompt") or "")

    gated = sl.safety_gate(user, prompt, options.get("brief") or {}, options, i18n.explicit_locale(event))   # the same stop and pause as a new request
    if gated:
        return gated
    not_ready, options = restore_media(user, video_id, item, req, loc)   # all of the video's photos, or a clear 409: never a silent retry without them
    if not_ready:
        return not_ready
    n_photos, n_asked = len(options.get("media") or []), len(req["options"].get("media") or [])

    if not _claim(video_id, item, retries):
        return json_response(200, {"message": "already running", **_state(_own_item(user, video_id) or item)})
    try:
        wallet.refund_video(item)   # a failure that never reached the refund (the flag makes this once-only)
    except Exception:   # noqa: BLE001
        logger.exception("VIDEO_RETRY_REFUND_FAILED video=%s", video_id)

    minutes = options.get("target_minutes") or float(os.environ.get("DEFAULT_TARGET_MINUTES", "3"))
    resolution = options.get("resolution")
    credits = wallet.credits_for_minutes(minutes, resolution)
    gate = plan_gate.begin(user, event)   # the same plan limits and free-credit rules as a new video (docs/PLANS.md); None where plans are off
    refused = plan_gate.check(gate, dict(options), loc, explicit_length=True, default_minutes=minutes)
    if refused:
        _revert(video_id, item, retries)
        return refused
    try:
        if gate is not None:
            charged, refused = plan_gate.charge(gate, user, credits, loc, tz=sl.request_timezone(event))
            if refused:
                _revert(video_id, item, retries)
                return refused
        else:
            charged = wallet.charge(user, credits, tz=sl.request_timezone(event))
        if credits and not charged:   # an unlimited (test/staff) account: the same ceiling as a new video
            usage.consume(f"unlimited:{user}", limit=int(os.environ.get("UNLIMITED_DAILY_VIDEOS", "50")))
    except usage.QuotaExceeded:
        _revert(video_id, item, retries)
        return json_response(429, {"message": i18n.t("create.test_limit", loc)}, {"Retry-After": "3600"})
    except wallet.InsufficientCredits as e:
        _revert(video_id, item, retries)
        return json_response(402, {"message": i18n.t("create.credits_needed", loc, needed=e.needed, balance=e.balance), "code": "insufficient_credits", "balance": e.balance, "needed": e.needed})

    usage_day = time.strftime("%Y-%m-%d", time.gmtime())
    started = None
    try:
        _clear_attempt(video_id, item, charged, credits, usage_day, resolution, {"options": options, "library_media": req.get("library_media") or []})
        clear_prefix(video_id)
        started = _sfn.start_execution(stateMachineArn=sm_arn, name=f"{video_id}-r{retries + 1}",
                                       input=json.dumps({"user_id": user, "video_id": video_id, "prompt": prompt, "usage_day": usage_day, **options}))
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ExecutionAlreadyExists":   # the same attempt started twice: the first one is running
            wallet.refund(user, charged)
            return json_response(200, {"message": "already running", **_state(_own_item(user, video_id) or item)})
        logger.exception("VIDEO_RETRY_START_FAILED video=%s", video_id)
    except Exception:   # noqa: BLE001
        logger.exception("VIDEO_RETRY_START_FAILED video=%s", video_id)
    if started is None:
        wallet.refund(user, charged)
        plan_gate.give_back(gate)
        _table().update_item(Key={"video_id": video_id}, UpdateExpression="SET #s = :f, failure_code = :fc, retries = :n, refunded = :t", ExpressionAttributeNames={"#s": "status"},
                             ExpressionAttributeValues={":f": "FAILED", ":fc": "START_FAILED", ":n": retries, ":t": True})
        return json_response(500, {"message": i18n.t("create.start_failed", loc)})
    start_date = started.get("startDate")
    return json_response(202, {"message": "workflow restarted", "video_id": video_id, "status": "STARTED_PROCESSING", "retries": retries + 1,
                               "photos": n_photos, **({"photos_unusable": n_asked - n_photos} if n_asked > n_photos else {}),
                               "startDate": start_date.isoformat() if hasattr(start_date, "isoformat") else ""})


def _execution_arn(item: Dict[str, Any]) -> Optional[str]:
    """The workflow run that is making this video now: `<video id>` for the first attempt, `<video id>-r<n>` after n retries."""
    arn = os.environ.get("STATE_MACHINE_ARN", "")
    if not arn or ":stateMachine:" not in arn:
        return None
    n = int(item.get("retries") or 0)
    return arn.replace(":stateMachine:", ":execution:") + ":" + str(item["video_id"]) + (f"-r{n}" if n else "")


def clear_published(user: str, video_id: str) -> int:
    """Best effort: the finished files of one video of one person (videos/<user>/<video>/: the MP4s of every revision, previews, the GIF). Nothing else is under that folder."""
    bucket, n = os.environ.get("ASSETS_BUCKET", ""), 0
    if not bucket or not user or any(bad in part for part in (user, video_id) for bad in ("/", "..")) or not video_id:
        return 0
    prefix = f"videos/{user}/{video_id}/"
    try:
        token = None
        while n < CLEAR_MAX_KEYS:
            res = _s3.list_objects_v2(Bucket=bucket, Prefix=prefix, **({"ContinuationToken": token} if token else {}))
            keys = [{"Key": o["Key"]} for o in res.get("Contents", [])]
            if keys:
                _s3.delete_objects(Bucket=bucket, Delete={"Objects": keys, "Quiet": True})
                n += len(keys)
            token = res.get("NextContinuationToken")
            if not token:
                break
    except Exception:   # noqa: BLE001
        logger.warning("VIDEO_DELETE_PUBLISHED_FAILED video=%s", video_id)
    return n


def cancel_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """POST /users/{user_id}/videos/{video_id}/cancel (docs/CREATE_API.md "Cancel a video"). Only the owner, only a video that is being made.
    Order: the row is moved to CANCELLED by ONE conditional write (two taps, or a tap racing the workflow's own end: exactly one wins); only the winner stops the
    workflow, refunds (wallet.refund_video is itself once-only, by the `refunded` flag on the row) and clears the working files. The photos are kept so "Try again" works."""
    loc = i18n.pick_locale(event)
    user, video_id, bad = _auth(event, loc)
    if bad:
        return bad
    item = _own_item(user, video_id)
    if not item:
        return json_response(404, {"code": "not_found", "message": i18n.t("retry.not_found", loc)})
    status = str(item.get("status") or "")
    if status == "CANCELLED":   # a second tap: the same answer, nothing is refunded again
        return json_response(200, {"message": "already cancelled", **_state(item), "refunded": 0})
    if status in ("COMPLETE", "FAILED", "REJECTED"):
        return json_response(409, {"code": "not_cancellable", "message": i18n.t("retry.cancel_not_making", loc), **_state(item)})
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    try:
        _table().update_item(
            Key={"video_id": video_id}, UpdateExpression="SET #s = :c, cancelled_at = :now, cancel_reason = :why",
            ConditionExpression="user_id = :u AND #s = :was AND (attribute_not_exists(retries) OR retries = :n)", ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":c": "CANCELLED", ":now": now, ":why": "user", ":u": user, ":was": status, ":n": int(item.get("retries") or 0)})
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
            raise
        cur = _own_item(user, video_id)   # it moved on while we looked: finished, failed, cancelled by another tap, or a later step of the making
        if not cur:
            return json_response(404, {"code": "not_found", "message": i18n.t("retry.not_found", loc)})
        if str(cur.get("status") or "") == "CANCELLED":
            return json_response(200, {"message": "already cancelled", **_state(cur), "refunded": 0})
        if str(cur.get("status") or "") in ("COMPLETE", "FAILED", "REJECTED"):
            return json_response(409, {"code": "not_cancellable", "message": i18n.t("retry.cancel_not_making", loc), **_state(cur)})
        return json_response(409, {"code": "try_again", "message": i18n.t("retry.cancel_try_again", loc), **_state(cur)})   # between two steps: the app sends it once more
    arn = _execution_arn(item)
    if arn:
        try:
            _sfn.stop_execution(executionArn=arn, error="CANCELLED", cause="cancelled by the owner")
        except Exception as e:   # noqa: BLE001 - already ended or never started: the row is cancelled either way, and status writes of late steps are refused (generate_video/db.FROZEN_STATUSES)
            logger.warning("VIDEO_CANCEL_STOP %s video=%s", type(e).__name__, video_id)
    refunded = 0
    try:
        refunded = wallet.refund_video(item)   # exactly once per attempt
    except Exception:   # noqa: BLE001
        logger.exception("VIDEO_CANCEL_REFUND_FAILED video=%s", video_id)
    clear_prefix(video_id)   # the working files; the photos stay for "Try again"
    try:   # the Making status is over
        from common import making
        attrs = [a for a in making.ATTRS if a in item]
        if attrs:
            _table().update_item(Key={"video_id": video_id}, UpdateExpression="REMOVE " + ", ".join(f"#a{i}" for i in range(len(attrs))),
                                 ConditionExpression="#s = :c", ExpressionAttributeNames={"#s": "status", **{f"#a{i}": a for i, a in enumerate(attrs)}}, ExpressionAttributeValues={":c": "CANCELLED"})
    except Exception:   # noqa: BLE001
        pass
    logger.info("VIDEO_CANCELLED video=%s refunded=%s", video_id, refunded)
    return json_response(200, {"message": "cancelled", "video_id": video_id, "status": "CANCELLED", "retries": int(item.get("retries") or 0), "refunded": refunded})


EDIT_BUSY_S = 20 * 60   # an edit that started rendering less than this ago is still writing the video's files


def delete_handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    """DELETE /users/{user_id}/videos/{video_id} (docs/CREATE_API.md "Delete a video"). Only the owner. A finished video (COMPLETE) or one that did not finish (FAILED,
    CANCELLED, REJECTED): the row, its working files and its finished files go. A video that is being made is cancelled first (POST .../cancel). Never touches the
    person's uploads or their My media library (another bucket; nothing here can write to it)."""
    loc = i18n.pick_locale(event)
    user, video_id, bad = _auth(event, loc)
    if bad:
        return bad
    item = _own_item(user, video_id)
    if not item:   # also the answer to a second DELETE: the video is gone (ids cannot be probed, so "never existed" and "already deleted" look the same)
        return json_response(404, {"code": "not_found", "message": i18n.t("retry.not_found", loc)})
    status = str(item.get("status") or "")
    if status not in DELETABLE:   # being made: cancel it first, then it can be removed
        return json_response(409, {"code": "not_deletable", "message": i18n.t("retry.not_deletable", loc), **_state(item)})
    if status == "COMPLETE" and str(item.get("edit_state") or "") == "RENDERING" and int(item.get("edit_started_at") or 0) > time.time() - EDIT_BUSY_S:
        return json_response(409, {"code": "busy", "message": i18n.t("retry.delete_busy", loc), **_state(item)})   # an edit is rendering: its files are being written right now
    if status != "COMPLETE":
        try:
            wallet.refund_video(item)   # exactly once; a failed, cancelled or rejected video costs nothing. A finished video was delivered: deleting it refunds nothing
        except Exception:   # noqa: BLE001
            logger.exception("VIDEO_DELETE_REFUND_FAILED video=%s", video_id)
    try:
        _table().delete_item(Key={"video_id": video_id}, ConditionExpression="user_id = :u AND #s = :was", ExpressionAttributeNames={"#s": "status"},
                             ExpressionAttributeValues={":u": user, ":was": status})
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":   # it was retried or edited in the meantime
            return json_response(409, {"code": "not_deletable", "message": i18n.t("retry.not_deletable", loc)})
        raise
    clear_prefix(video_id, keep_photos=False)   # a removed video keeps nothing, not even its copies of the photos
    clear_published(user, video_id)             # the MP4s, previews and GIF (also what a late step of a cancelled video may have left)
    return json_response(200, {"message": "deleted", "video_id": video_id})
