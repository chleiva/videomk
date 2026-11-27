"""GET /users/{user_id}/wallet : the user's credits (and grants today's free credits if due)."""
import logging
from typing import Any, Dict

from common import free_grants, i18n, plans, wallet
from common.http import json_response
from common.identity import extract_cognito_sub

logger = logging.getLogger()


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    loc = i18n.pick_locale(event)
    path_user = ((event or {}).get("pathParameters") or {}).get("user_id")
    user = extract_cognito_sub(event)
    if not user:
        return json_response(401, {"message": i18n.t("err.unauthorized", loc)})
    if not path_user or path_user != user:
        return json_response(403, {"message": i18n.t("err.forbidden", loc)})
    headers = {str(k).lower(): v for k, v in ((event or {}).get("headers") or {}).items()}
    tz = str(headers.get("x-timezone") or "").strip() or None
    try:
        if plans.enabled():   # docs/PLANS.md: the plan, its limits, what is locked, and whether this account can make a free video now (a free credit is granted only after the eligibility step)
            body = wallet.balance(user, tz=tz, ctx=free_grants.context(event))
            body["free"]["message"] = i18n.t(f"plan.free.{body['free']['reason']}", loc) if body["free"]["reason"] else None
            return json_response(200, body)
        return json_response(200, wallet.balance(user, tz=tz))
    except Exception:
        logger.exception("wallet read failed")
        return json_response(500, {"message": i18n.t("wallet.read_failed", loc)})
