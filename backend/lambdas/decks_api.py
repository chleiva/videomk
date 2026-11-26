"""Decks: upload a PowerPoint or PDF deck and have it prepared, before any video is paid for. docs/DECK_TO_VIDEO.md has the contract.

  POST /users/{user}/decks               {format: pptx|pdf, size: bytes}  -> presigned POST for uploads/<user>/decks/<id>/original.<ext> (size-bound, content-type fixed)
  POST /users/{user}/decks/{id}/process  after the upload                  -> 202; starts the converter (a sandboxed container with no network)
  GET  /users/{user}/decks/{id}                                            -> {status: uploading|processing|ready|failed, slides?, suggested_minutes?, suggested_credits?, code?, message?}
Nothing about the file is trusted here: it is validated, rendered and read only by the converter. The id is random and lives under the caller's own prefix, so another
user's deck can never be named. Flag: DECKS_ENABLED (set by `-c deckToVideo=1`).
"""
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from common import deck_limits as L, i18n, usage
from common.http import json_response
from common.identity import extract_cognito_sub

logger = logging.getLogger()
DAILY_DECKS = int(os.environ.get("DECKS_PER_DAY", "10"))
DAILY_PROCESS = int(os.environ.get("DECK_PROCESS_PER_DAY", "30"))


def _s3():
    return boto3.client("s3", region_name=os.environ.get("AWS_REGION") or "us-east-1", config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))


def _lambda():
    return boto3.client("lambda")


def _error(status: int, code: str, loc: str, **p: Any) -> Dict[str, Any]:
    key = f"deck.err.{code}" if code in L.ERROR_CODES else f"deck.{code}"
    return json_response(status, {"code": code, "message": i18n.t(key, loc, **p)})


def read_status(s3, bucket: str, user: str, deck_id: str) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(s3.get_object(Bucket=bucket, Key=L.status_key(user, deck_id))["Body"].read())
    except ClientError:
        return None


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    loc = i18n.pick_locale(event)
    path_user = ((event or {}).get("pathParameters") or {}).get("user_id")
    deck_id = ((event or {}).get("pathParameters") or {}).get("deck_id")
    user = extract_cognito_sub(event)
    if not user:
        return json_response(401, {"message": i18n.t("err.unauthorized", loc)})
    if not path_user or path_user != user:
        return json_response(403, {"message": i18n.t("err.forbidden", loc)})
    if os.environ.get("DECKS_ENABLED") != "1":
        return _error(404, "unavailable", loc)
    method, resource = str(event.get("httpMethod") or ""), str(event.get("resource") or "")
    bucket, s3 = os.environ["ASSETS_BUCKET"], _s3()
    if method == "POST" and resource.endswith("/decks"):
        return create(event, user, bucket, s3, loc)
    if not deck_id or not L.ID_RE.match(deck_id):
        return _error(404, "missing", loc)
    if method == "POST" and resource.endswith("/process"):
        return process(user, deck_id, bucket, s3, loc)
    if method == "GET":
        return get(user, deck_id, bucket, s3, loc)
    return json_response(405, {"message": "method not allowed"})


def create(event: Dict[str, Any], user: str, bucket: str, s3, loc: str) -> Dict[str, Any]:
    try:
        body = json.loads(event.get("body") or "{}")
        fmt, size = body.get("format"), body.get("size")
        if fmt not in L.FORMATS or isinstance(size, bool) or not isinstance(size, int) or size < 1:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        return json_response(400, {"code": "deck_unsupported", "message": i18n.t("deck.err.deck_unsupported", loc)})
    if size > L.MAX_BYTES:
        return _error(400, "deck_too_large", loc, max_mb=L.MAX_MB)
    try:
        usage.consume(f"deck:{user}", limit=DAILY_DECKS)
    except usage.QuotaExceeded:
        return json_response(429, {"code": "too_many_decks", "message": i18n.t("uploads.too_many_decks", loc)}, {"Retry-After": "3600"})
    deck_id = uuid.uuid4().hex[:16]
    ctype = L.CONTENT_TYPES[fmt]
    post = s3.generate_presigned_post(Bucket=bucket, Key=L.original_key(user, deck_id, fmt), Fields={"Content-Type": ctype},
                                      Conditions=[{"Content-Type": ctype}, ["content-length-range", 1, L.MAX_BYTES]], ExpiresIn=L.EXPIRES)
    s3.put_object(Bucket=bucket, Key=L.status_key(user, deck_id), Body=json.dumps({"status": "uploading", "format": fmt, "created": int(time.time())}).encode(), ContentType="application/json")
    return json_response(200, {"deck": {"id": deck_id, "format": fmt, "url": post["url"], "fields": post["fields"]}, "max_bytes": L.MAX_BYTES, "expires_in": L.EXPIRES, **L.limits()})


def process(user: str, deck_id: str, bucket: str, s3, loc: str) -> Dict[str, Any]:
    st = read_status(s3, bucket, user, deck_id)
    if st is None:
        return _error(404, "missing", loc)
    if st.get("status") in ("processing", "ready"):
        return json_response(202, {"status": st["status"]})   # idempotent: a second tap changes nothing
    if st.get("status") != "uploading" or st.get("format") not in L.FORMATS:
        return _error(404, "missing", loc)
    try:
        s3.head_object(Bucket=bucket, Key=L.original_key(user, deck_id, st["format"]))
    except ClientError:
        return _error(400, "missing", loc)   # the upload did not finish
    try:
        usage.consume(f"deckproc:{user}", limit=DAILY_PROCESS)
    except usage.QuotaExceeded:
        return json_response(429, {"code": "too_many_decks", "message": i18n.t("uploads.too_many_decks", loc)}, {"Retry-After": "3600"})
    s3.put_object(Bucket=bucket, Key=L.status_key(user, deck_id), Body=json.dumps({"status": "processing", "format": st["format"], "started": int(time.time())}).encode(), ContentType="application/json")
    _lambda().invoke(FunctionName=os.environ["DECK_PREP_FN"], InvocationType="Event", Payload=json.dumps({"user_id": user, "deck_id": deck_id, "ext": st["format"], "max_slides": L.MAX_SLIDES}).encode())
    return json_response(202, {"status": "processing"})


def get(user: str, deck_id: str, bucket: str, s3, loc: str) -> Dict[str, Any]:
    st = read_status(s3, bucket, user, deck_id)
    if st is None:
        return _error(404, "missing", loc)
    status = st.get("status")
    if status == "processing" and time.time() - int(st.get("started") or 0) > L.STALE_PROCESSING_S:
        status, st = "failed", {**st, "code": "deck_convert_timeout"}
    out: Dict[str, Any] = {"id": deck_id, "status": status, "format": st.get("format")}
    if status == "ready":
        n = int(st.get("slides") or 0)
        mins = L.auto_minutes(n, st.get("roles"))
        from common import wallet
        out.update({"slides": n, "suggested_minutes": mins, "suggested_credits": wallet.credits_for_minutes(mins, None)})
    elif status == "failed":
        code = st.get("code") if st.get("code") in L.ERROR_CODES else "deck_corrupt"
        out.update({"code": code, "message": i18n.t(f"deck.err.{code}", loc, max_mb=L.MAX_MB, max_slides=L.MAX_SLIDES)})
    return json_response(200, out)
