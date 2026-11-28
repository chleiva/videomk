"""POST /users/{user_id}/dictation : paid dictation. Pro and Max send a recording, the better text comes back (docs/SPEECH_TO_TEXT_2026-11-28.md, docs/CREATE_API.md "Paid dictation").

Body (JSON): {audio: base64, mime: 'audio/webm' | 'audio/mp4' | ..., seconds?: the length the app measured, languages?: ['es'] | ['en','es'], prompt?: short context}
Answer 200: {id, text, language, seconds, seconds_left_today, max_clip_seconds}. The audio is never stored and never logged; only the length, model and cost are kept (the usage table).
Refusals carry `code`: dictation_plan 403 (Free), dictation_quota 429 (today's seconds used), dictation_paused 503 (switch or global ceiling), dictation_too_long 413,
bad_audio 400, dictation_failed 502 (the provider failed: nothing was charged). The apps then fall back to the phone's own engine.
"""
import base64
import binascii
import json
import logging
import uuid
from typing import Any, Dict

from common import dictation, i18n, plans, stt
from common.http import json_response
from common.identity import extract_cognito_sub

logger = logging.getLogger()


def _err(status: int, code: str, key: str, loc: str, **p: Any) -> Dict[str, Any]:
    return json_response(status, {"code": code, "message": i18n.t(key, loc, **p), "can_upgrade": plans.PURCHASES_LIVE}, {"Retry-After": "3600"} if status == 429 else {"Content-Language": loc})


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    loc = i18n.pick_locale(event)
    path_user = ((event or {}).get("pathParameters") or {}).get("user_id")
    user = extract_cognito_sub(event)
    if not user:
        return json_response(401, {"message": i18n.t("err.unauthorized", loc)})
    if not path_user or path_user != user:
        return json_response(403, {"message": i18n.t("err.forbidden", loc)})
    cfg = plans.config()
    try:
        body = json.loads(event.get("body") or "{}")
        if not isinstance(body, dict) or not isinstance(body.get("audio"), str):
            raise ValueError
        audio = base64.b64decode(body["audio"], validate=True)
    except (ValueError, TypeError, binascii.Error):
        return json_response(400, {"code": "bad_audio", "message": i18n.t("dictation.bad_audio", loc)})
    mime = stt.mime_base(body.get("mime"))
    if not audio or mime not in stt.EXT:
        return json_response(400, {"code": "bad_audio", "message": i18n.t("dictation.bad_audio", loc)})
    clip_max = int(cfg["stt_max_clip_seconds"])
    claimed = body.get("seconds")
    claimed = float(claimed) if isinstance(claimed, (int, float)) and not isinstance(claimed, bool) and claimed > 0 else None
    estimate = claimed if claimed is not None else max(1.0, len(audio) / stt.BYTES_PER_SECOND_ESTIMATE)
    if len(audio) > dictation.MAX_AUDIO_BYTES or estimate > clip_max + 1:
        return _err(413, "dictation_too_long", "dictation.too_long", loc, max=clip_max // 60)
    try:   # plan right, kill switches, today's allowance: before any cost
        plan, rights = dictation.check(user, cfg)
        reserved = max(1.0, round(estimate, 3))
        day = dictation.reserve(user, reserved, plan, rights, cfg)
    except dictation.Paused:
        logger.info("DICTATION_REFUSED code=paused user=%s", user)
        return _err(503, "dictation_paused", "dictation.paused", loc)
    except dictation.Refused as e:
        logger.info("DICTATION_REFUSED code=%s plan=%s user=%s", e.error.code, e.error.plan, user)
        return json_response(e.error.status, e.error.body(loc), {"Retry-After": "3600"} if e.error.status == 429 else {"Content-Language": loc})
    try:
        result = stt.transcribe(audio, mime, body.get("languages"), str(body.get("prompt") or "")[:400], claimed_seconds=claimed)
    except stt.SttError as e:
        dictation.release(user, day, reserved)
        logger.warning("DICTATION_PROVIDER_FAILED code=%s user=%s", e.code, user)   # counters only: never the audio or the words
        if e.code == "bad_audio":
            return json_response(400, {"code": "bad_audio", "message": i18n.t("dictation.bad_audio", loc)})
        return json_response(502, {"code": "dictation_failed", "message": i18n.t("dictation.failed", loc)})
    except Exception:   # noqa: BLE001
        dictation.release(user, day, reserved)
        logger.exception("DICTATION_FAILED user=%s", user)
        return json_response(502, {"code": "dictation_failed", "message": i18n.t("dictation.failed", loc)})
    did = uuid.uuid4().hex
    try:
        dictation.settle(user, day, reserved, result["seconds"])
        dictation.record(user, did, result)
    except Exception:   # noqa: BLE001 - the words were paid for: still return them
        logger.exception("DICTATION_RECORD_FAILED user=%s", user)
    logger.info("DICTATION_OK user=%s plan=%s seconds=%s cost_usd=%s model=%s lang=%s", user, plan, result["seconds"], result["cost_usd"], result["model"], result["language"])
    left = None
    try:
        left = max(0, int(rights["stt_seconds_per_day"]) - dictation.used_today(user, day))
    except Exception:   # noqa: BLE001
        pass
    return json_response(200, {"id": did, "text": result["text"], "language": result["language"], "seconds": result["seconds"], "seconds_left_today": left, "max_clip_seconds": clip_max},
                         {"Content-Language": loc, "Cache-Control": "no-store"})
