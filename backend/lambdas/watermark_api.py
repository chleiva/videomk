"""The watermark settings and logo (docs/WATERMARK.md). The caller is the verified Cognito `sub` and nothing else.

  GET    /users/{user_id}/watermark        the saved settings + whether a logo is stored (+ a 5 minute link to it) + what this account may use
  PUT    /users/{user_id}/watermark        save the default settings: {mode, position, opacity, size, style, end_card}  (the same object a create request may carry as `watermark`)
  DELETE /users/{user_id}/watermark        forget the settings AND the logo
  PUT    /users/{user_id}/watermark/logo   {"data": "<base64 of a PNG, JPEG or SVG up to 2 MB>"}  premium only
  DELETE /users/{user_id}/watermark/logo   remove the logo (a saved 'custom' mode then falls back until a new logo is added)
"""
import base64
import binascii
import json
import logging
from typing import Any, Dict, Optional

from botocore.exceptions import ClientError

from common import i18n, usage, watermark_store as store
from common.http import json_response
from common.identity import extract_cognito_sub
from engine import watermark_spec as ws

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MAX_BODY = 3 * 1024 * 1024        # 2 MB of image is 2.8 MB as base64
LOGO_UPLOADS_PER_DAY = 20
_HEADERS = {"Access-Control-Allow-Methods": "GET,PUT,DELETE,OPTIONS"}


def _body(event: Dict[str, Any]) -> Dict[str, Any]:
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        try:
            raw = base64.b64decode(raw).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError):
            raise store.WatermarkError(400, "wm.invalid", "invalid") from None
    if len(raw.encode("utf-8", "ignore")) > MAX_BODY:
        raise store.WatermarkError(400, "wm.logo_size", "logo_too_big", mb=2)
    try:
        body = json.loads(raw or "{}")
    except (ValueError, TypeError):
        raise store.WatermarkError(400, "wm.invalid", "invalid") from None
    if not isinstance(body, dict):
        raise store.WatermarkError(400, "wm.invalid", "invalid")
    return body


def _clean(body: Dict[str, Any], *, premium: bool, forced: Optional[bool] = None, modes: Optional[list] = None) -> Dict[str, Any]:
    if "mode" not in body:   # saving settings always says which mode
        raise store.WatermarkError(400, "wm.invalid", "invalid")
    try:
        spec = ws.parse(body, strict=True)
    except ws.WatermarkError:
        raise store.WatermarkError(400, "wm.invalid", "invalid") from None
    if spec is None:
        raise store.WatermarkError(400, "wm.invalid", "invalid")
    by_plan = modes is not None   # plans on (docs/PLANS.md): the refusal also names the plan that unlocks the mode
    if spec["mode"] == "custom" and not premium:
        raise store.WatermarkError(403, "wm.premium_max" if by_plan else "wm.premium", "watermark_premium", extra={"requires_plan": store._plan_for_mode("custom")} if by_plan else None)
    is_forced = (store.force_policy() and not premium) if forced is None else forced
    if spec["mode"] == "none" and is_forced:
        raise store.WatermarkError(403, "wm.required", "watermark_required", extra={"requires_plan": store._plan_for_mode("none")} if by_plan else None)   # the owner's policy: a free account's videos carry the videomk name for the whole video (capabilities.watermark.forced_watermark)
    if spec.get("presence") == "moments" and (("moments" not in modes) if by_plan else is_forced):   # the mark that comes and goes: a paid plan's right (plans on), not for a forced account (plans off)
        if by_plan:
            raise store.WatermarkError(403, "plan.watermark", "plan_watermark", extra={"requires_plan": store._plan_for_mode("moments")})
        raise store.WatermarkError(403, "wm.required", "watermark_required")
    if by_plan and spec["mode"] not in modes and spec["mode"] != "custom":
        raise store.WatermarkError(403, "plan.watermark", "plan_watermark", extra={"requires_plan": store._plan_for_mode(spec["mode"])})
    return spec


def view(user: str, loc: str) -> Dict[str, Any]:
    return {"watermark": store.public_profile(user), "capabilities": store.capabilities(user, loc)}


def route(event: Dict[str, Any], user: str, loc: str) -> Dict[str, Any]:
    res, method = event.get("resource") or "", event.get("httpMethod") or ""
    base = "/users/{user_id}/watermark"
    if res == base and method == "GET":
        return view(user, loc)
    if res == base and method == "PUT":
        wr = store.rights(user)
        spec = _clean(_body(event), premium=wr["premium"], forced=wr["forced"], modes=wr["modes"])
        if spec["mode"] == "custom" and not store.has_logo(user):
            raise store.WatermarkError(400, "wm.logo_missing", "watermark_logo_missing")
        store.put_profile(user, spec)
        return view(user, loc)
    if res == base and method == "DELETE":
        store.delete_profile(user)
        store.delete_logo(user)
        return view(user, loc)
    if res == f"{base}/logo" and method == "PUT":
        wr = store.rights(user)
        if not wr["premium"]:
            raise store.WatermarkError(403, "wm.premium_max" if wr.get("by_plan") else "wm.premium", "watermark_premium", extra={"requires_plan": "max"})
        try:
            usage.consume(f"wmlogo:{user}", limit=LOGO_UPLOADS_PER_DAY)
        except usage.QuotaExceeded:
            raise store.WatermarkError(429, "wm.rate_limited", "rate_limited") from None
        b64 = _body(event).get("data")
        if not isinstance(b64, str):
            raise store.WatermarkError(400, "wm.invalid", "invalid")
        try:
            data = base64.b64decode(b64, validate=True)
        except (binascii.Error, ValueError):
            raise store.WatermarkError(400, "wm.logo_type", "logo_type") from None
        store.put_logo(user, data)
        return view(user, loc)
    if res == f"{base}/logo" and method == "DELETE":
        store.delete_logo(user)
        prof = store.get_profile(user)
        if prof.get("mode") == "custom":   # a saved 'custom' without a logo would be a dead setting
            store.put_profile(user, {"mode": "videomk", **{k: v for k, v in prof.items() if k in ("position", "opacity", "size")}})
        return view(user, loc)
    raise store.WatermarkError(404, "err.not_found")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    loc = i18n.pick_locale(event)
    user = extract_cognito_sub(event)
    if not user:
        return json_response(401, {"message": i18n.t("err.unauthorized", loc)}, _HEADERS)
    path_user = ((event or {}).get("pathParameters") or {}).get("user_id")
    if not path_user or path_user != user:
        return json_response(403, {"message": i18n.t("err.forbidden", loc)}, _HEADERS)
    if not store.enabled():
        return json_response(404, {"message": i18n.t("err.not_found", loc)}, _HEADERS)
    try:
        store.check_user(user)
        return json_response(200, route(event, user, loc), {**_HEADERS, "Cache-Control": "no-store"})
    except store.WatermarkError as e:
        extra = {**({"code": e.code} if e.code else {}), **e.extra}
        return json_response(e.status, {"message": i18n.t(e.key, loc, **e.params), **extra}, {**_HEADERS, **({"Retry-After": "3600"} if e.status == 429 else {})})
    except ClientError:
        logger.exception("WATERMARK_FAILED (AWS)")
        return json_response(500, {"message": i18n.t("err.generic", loc)}, _HEADERS)
    except Exception:
        logger.exception("WATERMARK_FAILED")   # never the image or the settings in the log line
        return json_response(500, {"message": i18n.t("err.generic", loc)}, _HEADERS)
