"""POST /users/{user_id}/account/delete and POST /users/{user_id}/account/apple-revoke (docs/ACCOUNT_DELETION.md). The caller is the verified Cognito `sub` and nothing else."""
import json
import logging
import os
import time
from typing import Any, Dict, Optional

from botocore.exceptions import ClientError

from common import deletion, i18n
from common.http import json_response
from common.identity import extract_cognito_sub

logger = logging.getLogger()


def _claims(event: Dict[str, Any]) -> Dict[str, Any]:
    authz = ((event or {}).get("requestContext") or {}).get("authorizer") or {}
    c = authz.get("claims") or (authz.get("jwt") or {}).get("claims") or {}
    return c if isinstance(c, dict) else {}


def _body(event: Dict[str, Any]) -> Dict[str, Any]:
    try:
        b = json.loads(event.get("body") or "{}")
    except (ValueError, TypeError):
        raise deletion.DeletionError(400, "the body must be JSON") from None
    if not isinstance(b, dict):
        raise deletion.DeletionError(400, "the body must be a JSON object")
    return b


def apple_flag() -> bool:
    return os.environ.get("APPLE_REVOKE_ENABLED", "0") == "1"


def _apple_state(user: str, username: Optional[str]) -> str:
    """'not_linked' | 'revoke_available' | 'revoke_off' | 'unknown': what the app should do about the person's Sign in with Apple grant."""
    try:
        pu = deletion.find_pool_user(user, username)
    except Exception:   # noqa: BLE001 - a lookup problem must never stop a deletion
        logger.exception("ACCOUNT_APPLE_LOOKUP_FAILED user=%s", user)
        return "unknown"
    if pu is None:
        return "unknown"
    if not deletion.apple_identity(pu["attrs"]):
        return "not_linked"
    return "revoke_available" if apple_flag() else "revoke_off"


def delete_account(event: Dict[str, Any], user: str, loc: str = "en") -> Dict[str, Any]:
    if _body(event).get("confirm") != "DELETE":
        raise deletion.DeletionError(400, "send {\"confirm\": \"DELETE\"} to delete your account", code="confirmation_required")
    claims = _claims(event)
    username = str(claims.get("cognito:username") or "") or None
    job = deletion.get_job(user)
    if job is None:
        if not deletion.recent_auth(claims.get("auth_time")):   # a stale or borrowed session must not be able to start a deletion; a repeat of one already started is harmless
            raise deletion.DeletionError(401, i18n.t("account.reauth", loc), code="reauth_required", max_age_seconds=deletion.RECENT_AUTH_SECONDS)
        deletion.create_job(user, username)
        deletion.enqueue(user)
    elif job.get("status") == "stuck":
        deletion.reopen(user)
        deletion.enqueue(user)
    elif job.get("status") == "queued" and int(time.time()) - int(job.get("created_at", 0)) > 600:
        deletion.enqueue(user)   # the first message was lost: send another (steps are idempotent)
    logger.info("ACCOUNT_DELETION_REQUESTED user=%s", user)
    return {"status": "deleting", "apple": _apple_state(user, username)}


def apple_revoke_start(event: Dict[str, Any], user: str, loc: str = "en") -> Dict[str, Any]:
    from common import apple

    if not apple_flag():
        raise deletion.DeletionError(404, "not available", code="apple_revoke_off")
    b = _body(event)
    back = b.get("return", "app")
    if back not in ("app", "web"):
        raise deletion.DeletionError(400, "'return' must be app or web")
    job = deletion.get_job(user)
    if job is None:
        raise deletion.DeletionError(409, i18n.t("account.delete_first", loc), code="not_deleting")
    if job.get("status") == "done":
        raise deletion.DeletionError(410, i18n.t("account.already_deleted", loc), code="account_deleted")
    pu = deletion.find_pool_user(user, job.get("username") or str(_claims(event).get("cognito:username") or "") or None)
    asub = deletion.apple_identity(pu["attrs"]) if pu else None
    if not asub:
        raise deletion.DeletionError(409, i18n.t("account.no_apple", loc), code="no_apple_identity")
    url = apple.authorize_url(apple.services_id(), os.environ["APPLE_RETURN_URL"], apple.sign_state(user, asub, back))
    return {"authorize_url": url, "expires_in": apple.STATE_SECONDS}


def route(event: Dict[str, Any], user: str, loc: str = "en") -> Dict[str, Any]:
    res, method = event.get("resource") or "", event.get("httpMethod") or ""
    if method == "POST" and res == "/users/{user_id}/account/delete":
        return delete_account(event, user, loc)
    if method == "POST" and res == "/users/{user_id}/account/apple-revoke":
        return apple_revoke_start(event, user, loc)
    raise deletion.DeletionError(404, "not found")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    loc = i18n.pick_locale(event)
    user = extract_cognito_sub(event)
    if not user:
        return json_response(401, {"message": i18n.t("err.unauthorized", loc)})
    path_user = ((event or {}).get("pathParameters") or {}).get("user_id")
    if not path_user or path_user != user:
        return json_response(403, {"message": i18n.t("err.forbidden", loc)})   # nobody can delete (or even ask about) another person's account
    try:
        deletion.check_user(user)
        out = route(event, user, loc)
        return json_response(202 if "status" in out else 200, out)
    except deletion.DeletionError as e:
        return json_response(e.status, {"message": e.text(loc), **e.extra})
    except ClientError:
        logger.exception("account request failed (AWS)")
        return json_response(500, {"message": i18n.t("err.generic", loc)})
    except Exception:
        logger.exception("account request failed")   # no tokens, keys or addresses in the log line
        return json_response(500, {"message": i18n.t("err.generic", loc)})
