"""Video upload API (docs/VIDEO_UPLOAD_2026-11-28.md section 3). One function behind an HTTP API of its own stack (backend/vidup_stack.py), every route behind the customer pool's token.

  POST   /users/{user_id}/video-uploads                    {size_bytes, content_type, use_audio, sha256?}  -> 201 {id, upload: {url, fields}, ...} | 200 {duplicate: true, clip}
  POST   /users/{user_id}/video-uploads/{clip_id}/analyse  (after the file is uploaded)                    -> 202 {clip} (analysis started) | 200 (already decided)
  GET    /users/{user_id}/video-uploads/{clip_id}          -> {clip}: status, metadata, what we understood, a signed poster link when ready
  GET    /users/{user_id}/video-uploads                    -> {clips: [...]} the clips kept for this account (ready and in progress)
  DELETE /users/{user_id}/video-uploads/{clip_id}          -> 204: the kept files and the record are removed
Refusals carry `code`: video_upload_plan 403, video_upload_quota 429, video_upload_paused 503, too_big 413, bad_request 400, rejected 400 (known refused file), not_found 404, unfinished 400.
"""
import json
import logging
import os
import time
from typing import Any, Dict, Optional

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError

from common import i18n, intake, plans, vidup as V
from common.identity import extract_cognito_sub

logger = logging.getLogger()

HEADERS = {"Content-Type": "application/json", "Access-Control-Allow-Origin": "*", "Access-Control-Allow-Headers": "Content-Type,Authorization,X-Locale",
           "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS", "Cache-Control": "no-store"}
_s3c = None
_lam = None


def s3():
    global _s3c
    if _s3c is None:
        _s3c = boto3.client("s3", region_name=os.environ.get("AWS_REGION") or "us-east-1", config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))
    return _s3c


def lam():
    global _lam
    if _lam is None:
        _lam = boto3.client("lambda")
    return _lam


def bucket() -> str:
    return os.environ["VIDUP_BUCKET"]


def _resp(status: int, body: Optional[Dict[str, Any]] = None, extra: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    from common.http import _default
    return {"statusCode": status, "headers": {**HEADERS, **(extra or {})}, "isBase64Encoded": False, "body": "" if body is None else json.dumps(body, default=_default)}


def _err(status: int, code: str, key: str, loc: str, **p: Any) -> Dict[str, Any]:
    return _resp(status, {"code": code, "message": i18n.t(key, loc, **p), "can_upgrade": plans.PURCHASES_LIVE}, {"Content-Language": loc, **({"Retry-After": "3600"} if status == 429 else {})})


def view(rec: Dict[str, Any], loc: str, *, signed: bool = True) -> Dict[str, Any]:
    """The clip as the apps see it. Never the hash, the keys, or any cost."""
    st = rec.get("status")
    out: Dict[str, Any] = {"id": rec.get("day"), "status": st, "ready": st == V.READY, "use_audio": bool(rec.get("use_audio"))}
    if st in (V.REJECTED, V.FAILED):
        out["code"] = "rejected" if st == V.REJECTED else "check_failed"
        out["message"] = i18n.t("vidup.rejected" if st == V.REJECTED else "vidup.failed", loc)
    if st == V.READY:
        dur, src = float(rec["duration"]), float(rec.get("source_duration") or rec["duration"])
        out.update({"width": int(rec["w"]), "height": int(rec["h"]), "aspect": rec.get("aspect"), "orientation": rec.get("orientation"), "duration": dur, "source_duration": src,
                    "trimmed": src > dur + 0.05, "has_audio": bool(rec.get("has_audio")), "audio_used": bool(rec.get("audio_used")), "audio_state": rec.get("audio_state"),
                    "summary": rec.get("summary"), "lines": list(rec.get("lines") or []), "described": bool(rec.get("described"))})
        if signed and rec.get("thumb_key"):
            try:
                out["thumb_url"] = s3().generate_presigned_url("get_object", Params={"Bucket": bucket(), "Key": rec["thumb_key"]}, ExpiresIn=V.SIGNED_GET_SECONDS)
            except Exception:   # noqa: BLE001 - a missing poster never fails the answer
                logger.exception("VIDUP_SIGN_FAILED")
    return out


def _body(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        b = json.loads(event.get("body") or "{}")
        return b if isinstance(b, dict) else {}
    except (ValueError, TypeError):
        return {}


def create(user: str, event: Dict[str, Any], loc: str) -> Dict[str, Any]:
    body = _body(event)
    cfg = plans.config()
    size, ctype, use_audio = body.get("size_bytes"), str(body.get("content_type") or "").split(";")[0].strip().lower(), body.get("use_audio")
    digest = str(body.get("sha256") or "").lower()
    if isinstance(size, bool) or not isinstance(size, int) or size < 1000 or ctype not in V.MIME_OK or not isinstance(use_audio, bool) or (digest and not V.HASH_RE.match(digest)):
        return _err(400, "bad_request", "vidup.bad_file", loc)
    if size > V.MAX_BYTES:
        return _err(413, "too_big", "vidup.too_big", loc, max=V.MAX_BYTES // (1024 * 1024))
    try:   # switches and the plan's right: before any cost
        plan, rights = V.check(user, cfg)
    except V.Paused:
        return _err(503, "video_upload_paused", "vidup.paused", loc)
    except V.Refused as e:
        return _resp(e.error.status, e.error.body(loc), {"Content-Language": loc})
    stopped = intake.paused(user, loc) if os.environ.get("SAFETY_TABLE") else None   # an account on a safety pause or hold adds nothing
    if stopped:
        return _resp(429, stopped, {"Retry-After": str(stopped.get("retry_after", 3600))})
    if digest:
        if V.is_bad_hash(digest):
            return _err(400, "rejected", "vidup.rejected", loc)
        prior = V.find_by_hash(user, f"{digest}:{'a' if use_audio else 'n'}")
        old = V.get_record(user, prior) if prior else None
        if V.usable(old):   # the same file again: no slot, no count, no analysis
            return _resp(200, {"duplicate": True, "clip": view(old, loc)}, {"Content-Language": loc})
    try:
        day = V.reserve_clip(user, plan, rights, cfg)
    except V.Refused as e:
        return _resp(e.error.status, e.error.body(loc), {"Content-Language": loc, **({"Retry-After": "3600"} if e.error.status == 429 else {})})
    import uuid
    cid = uuid.uuid4().hex
    V.put_record(user, cid, {"status": V.PENDING, "use_audio": use_audio, "size_bytes": size, "count_day": day, "created": int(time.time()), "plan": plan})
    post = s3().generate_presigned_post(Bucket=bucket(), Key=V.in_key(user, cid), Fields={"Content-Type": ctype},
                                        Conditions=[{"Content-Type": ctype}, ["content-length-range", 1, V.MAX_BYTES]], ExpiresIn=V.UPLOAD_SECONDS)
    left = max(0, int(rights["video_clips_per_day"]) - V.used_today(user, day))
    return _resp(201, {"id": cid, "upload": {"url": post["url"], "fields": post["fields"]}, "expires_in": V.UPLOAD_SECONDS, "max_bytes": V.MAX_BYTES, "used_seconds": V.USED_SECONDS,
                       "use_audio": use_audio, "clips_left_today": left}, {"Content-Language": loc})


def analyse(user: str, cid: str, loc: str) -> Dict[str, Any]:
    rec = V.get_record(user, cid)
    if not rec:
        return _err(404, "not_found", "vidup.not_found", loc)
    if rec.get("status") != V.PENDING:   # already started or decided: idempotent, no second analysis, no second cost
        return _resp(200 if rec.get("status") != V.ANALYSING else 202, {"clip": view(rec, loc)}, {"Content-Language": loc})
    cfg = plans.config()
    try:
        plan, rights = V.check(user, cfg)
        day = V.reserve_budget(plan, rights, cfg)   # the budget guard: the worst case of one analysis against today's ceiling
    except V.Paused:
        return _err(503, "video_upload_paused", "vidup.paused", loc)
    except V.Refused as e:
        return _resp(e.error.status, e.error.body(loc), {"Content-Language": loc})
    try:
        head = s3().head_object(Bucket=bucket(), Key=V.in_key(user, cid))
    except ClientError:
        V.release_budget(day, V.WORST_CASE_USD)
        return _err(400, "unfinished", "vidup.unfinished", loc)
    if int(head.get("ContentLength", 0)) > V.MAX_BYTES:
        V.release_budget(day, V.WORST_CASE_USD)
        return _err(413, "too_big", "vidup.too_big", loc, max=V.MAX_BYTES // (1024 * 1024))
    if not V.update_record(user, cid, {"status": V.ANALYSING, "budget_day": day, "budget_reserved": V.WORST_CASE_USD, "started": int(time.time())}, expect=V.PENDING):
        V.release_budget(day, V.WORST_CASE_USD)   # another request got there first
        return _resp(202, {"clip": view(V.get_record(user, cid) or rec, loc)}, {"Content-Language": loc})
    try:
        lam().invoke(FunctionName=os.environ["ANALYSE_FUNCTION"], InvocationType="Event", Payload=json.dumps({"user": user, "clip": cid}).encode())
    except Exception:   # noqa: BLE001
        logger.exception("VIDUP_INVOKE_FAILED")
        V.update_record(user, cid, {"status": V.PENDING}, expect=V.ANALYSING)
        V.release_budget(day, V.WORST_CASE_USD)
        return _err(502, "check_failed", "vidup.failed", loc)
    return _resp(202, {"clip": view({**rec, "status": V.ANALYSING}, loc)}, {"Content-Language": loc})


def delete(user: str, cid: str, loc: str) -> Dict[str, Any]:
    rec = V.get_record(user, cid)
    if not rec:
        return _resp(204)
    if rec.get("status") == V.ANALYSING:   # let the one analysis finish; the apps may delete when it has
        return _resp(409, {"code": "busy", "message": i18n.t("vidup.not_ready", loc)})
    keys = [V.in_key(user, cid), V.mezz_key(user, cid), V.audio_key(user, cid), V.thumb_key(user, cid)]
    try:
        s3().delete_objects(Bucket=bucket(), Delete={"Objects": [{"Key": k} for k in keys], "Quiet": True})
    except ClientError:
        logger.exception("VIDUP_DELETE_FAILED")
    for tag in ("a", "n"):
        if rec.get("hash") and V.find_by_hash(user, f"{rec['hash']}:{tag}") == cid:
            V.forget_hash(user, f"{rec['hash']}:{tag}")
    V.delete_record(user, cid)
    return _resp(204)


def listing(user: str, loc: str) -> Dict[str, Any]:
    from boto3.dynamodb.conditions import Key
    items = V._table().query(KeyConditionExpression=Key("user_id").eq(f"vidrec:{user}"), Limit=60).get("Items", [])
    items = sorted(items, key=lambda r: -int(r.get("created") or r.get("analysed_at") or 0))[:30]
    return _resp(200, {"clips": [view(r, loc) for r in items if r.get("status") in (V.READY, V.ANALYSING, V.PENDING)]}, {"Content-Language": loc})


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    loc = i18n.pick_locale(event)
    path_user = ((event or {}).get("pathParameters") or {}).get("user_id")
    user = extract_cognito_sub(event)
    if not user:
        return _resp(401, {"message": i18n.t("err.unauthorized", loc)})
    if not path_user or path_user != user:
        return _resp(403, {"message": i18n.t("err.forbidden", loc)})
    method = str(((event.get("requestContext") or {}).get("http") or {}).get("method") or event.get("httpMethod") or "").upper()
    cid = ((event.get("pathParameters") or {}).get("clip_id")) or ""
    path = str(event.get("rawPath") or event.get("path") or "")
    if method == "OPTIONS":
        return _resp(204)
    if cid and not V.ID_RE.match(cid):
        return _err(404, "not_found", "vidup.not_found", loc)
    if method == "POST" and not cid:
        return create(user, event, loc)
    if method == "POST" and path.rstrip("/").endswith("/analyse"):
        return analyse(user, cid, loc)
    if method == "GET" and cid:
        rec = V.get_record(user, cid)
        return _resp(200, {"clip": view(rec, loc)}, {"Content-Language": loc}) if rec else _err(404, "not_found", "vidup.not_found", loc)
    if method == "GET":
        return listing(user, loc)
    if method == "DELETE" and cid:
        return delete(user, cid, loc)
    return _resp(405, {"message": "method not allowed"})
