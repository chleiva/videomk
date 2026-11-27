"""POST /account/apple-callback: Apple sends the person's browser here (form_post) after the deletion-time Sign in with Apple prompt (docs/ACCOUNT_DELETION.md, "Apple").

Public route (Apple, not our app, calls it): its only credential is the signed, 10-minute `state` made by account_api for a deletion that is under way. It exchanges the code,
checks that Apple's account is the one linked to this person, revokes the refresh token and sends the browser back to the app (custom scheme) or the website. It never stores or
logs a token or the key, and the places it redirects to are fixed by the deployment, never taken from the request.
"""
import base64
import logging
import os
import urllib.parse
from typing import Any, Dict

from common import apple, deletion

logger = logging.getLogger()


def _back(kind: str, status: str) -> Dict[str, Any]:
    base = os.environ["APPLE_APP_RETURN"] if kind == "app" else os.environ["APPLE_WEB_RETURN"]
    sep = "&" if "?" in base else "?"
    url = f"{base}{sep}status={status}"
    html = f'<!doctype html><meta charset="utf-8"><meta http-equiv="refresh" content="0;url={url}"><title>VideoMK</title><p><a href="{url}">Back to VideoMK</a></p>'
    return {"statusCode": 303, "headers": {"Location": url, "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store"}, "body": html, "isBase64Encoded": False}


def _form(event: Dict[str, Any]) -> Dict[str, str]:
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8", "replace")
    return {k: v[0] for k, v in urllib.parse.parse_qs(raw[:8192]).items()}


def process(form: Dict[str, str], *, post=apple.post_form) -> str:
    """The status word for the redirect: ok | cancelled | invalid | mismatch | failed."""
    st = apple.read_state(form.get("state", ""))
    if st is None:
        return "invalid"
    user = st["u"]
    if form.get("error"):
        return "cancelled"
    code = form.get("code", "")
    if not code or len(code) > 2048:
        return "invalid"
    job = deletion.get_job(user)
    if job is None or job.get("status") == "done":
        return "invalid"   # only for a deletion that is under way
    try:
        cfg = apple.signing_config()
        secret = apple.client_secret(cfg["team_id"], cfg["key_id"], cfg["services_id"], cfg["private_key"])
        tokens = apple.exchange_code(code, client_id=cfg["services_id"], secret=secret, redirect_uri=os.environ["APPLE_RETURN_URL"], post=post)
        if apple.id_token_subject(tokens.get("id_token", "")) != st["a"]:
            logger.warning("ACCOUNT_APPLE_REVOKE_MISMATCH user=%s", user)   # a different Apple account than the linked one: nothing is revoked, the tokens are dropped
            return "mismatch"
        apple.revoke(tokens["refresh_token"], client_id=cfg["services_id"], secret=secret, post=post)
        deletion.mark_apple_revoked(user)
        logger.info("ACCOUNT_APPLE_REVOKED user=%s", user)
        return "ok"
    except apple.AppleError as e:
        logger.error("ACCOUNT_APPLE_REVOKE_FAILED user=%s where=%s status=%s error=%s", user, e.where, e.status, e.error)
        return "failed"
    except Exception as e:   # noqa: BLE001 - only the class name: a message could carry key material
        logger.error("ACCOUNT_APPLE_REVOKE_FAILED user=%s error=%s", user, type(e).__name__)
        return "failed"


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    form = _form(event)
    st = apple.read_state(form.get("state", ""))
    status = process(form)
    return _back(st["b"] if st else "web", status)
