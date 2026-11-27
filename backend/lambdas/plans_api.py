"""Plans API (docs/PLANS.md).

  GET  /users/{user_id}/plan               the account's plan, limits, what is locked, the three plans and their product ids, the free plan's state. Owner only (path user = token sub).
  (the two routes below are one API resource, /users/{user_id}/purchases/{store}; the three webhooks are /purchases/webhooks/{store})
  POST /users/{user_id}/purchases/apple    PHASE 2, answers 501 `purchases_unavailable` today. Body: {"signed_transaction": "<StoreKit 2 JWS>"}; the purchase must carry
                                           appAccountToken = the account's id (a UUID). 200: the same body as GET .../plan.
  POST /users/{user_id}/purchases/google   PHASE 2, 501 today. Body: {"purchase_token": "...", "subscription_id": "videomk_pro|videomk_max"}; the purchase must carry
                                           obfuscatedAccountId = the account's id. 200: the same body as GET .../plan.
  POST /purchases/webhooks/apple           PHASE 2, 501 today. App Store Server Notifications V2: {"signedPayload": "<JWS>"}. Public route: the signature is the credential.
  POST /purchases/webhooks/google          PHASE 2, 501 today. Google real-time developer notifications (a Pub/Sub push: {"message": {"data": "<base64>", "messageId": "..."}}).
  POST /purchases/webhooks/web             PHASE 2, 501 today. The web merchant's signed event.

Nothing here changes a plan: the entitlements table is read-only for this function. In phase 2 the two verify routes and the three webhooks move to their own function, the only
runtime writer of entitlements.
"""
import logging
import time
from typing import Any, Dict

from common import free_grants, i18n, plans, wallet
from common.http import json_response
from common.identity import extract_cognito_sub

logger = logging.getLogger()
_HEADERS = {"Access-Control-Allow-Methods": "GET,POST,OPTIONS", "Cache-Control": "no-store"}


def view(user: str, event: Dict[str, Any], loc: str) -> Dict[str, Any]:
    w = wallet._balance_plans(user, now=time.time(), tz=None, ctx=free_grants.context(event), grant=False)
    free = {**w["free"], "message": i18n.t(f"plan.free.{w['free']['reason']}", loc) if w["free"]["reason"] else None}
    return {"plan": w["plan"], "plans": plans.catalog(), "free_creation": w["free_creation"], "free": free, "can_upgrade": w["can_upgrade"],
            "purchases": {"apple": plans.PURCHASES_LIVE, "google": plans.PURCHASES_LIVE, "web": plans.PURCHASES_LIVE}}


def not_built(loc: str) -> Dict[str, Any]:
    return json_response(501, {"code": "purchases_unavailable", "message": i18n.t("plan.purchases_unavailable", loc), "can_upgrade": plans.PURCHASES_LIVE}, _HEADERS)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    loc = i18n.pick_locale(event)
    resource = str((event or {}).get("resource") or "")
    if resource.startswith("/purchases/webhooks/"):   # public: no account, nothing read, nothing written
        store = str(((event or {}).get("pathParameters") or {}).get("store") or resource.rsplit("/", 1)[-1])
        return not_built(loc) if store in ("apple", "google", "web") else json_response(404, {"message": i18n.t("err.not_found", loc)}, _HEADERS)
    user = extract_cognito_sub(event)
    if not user:
        return json_response(401, {"message": i18n.t("err.unauthorized", loc)}, _HEADERS)
    path_user = ((event or {}).get("pathParameters") or {}).get("user_id")
    if not path_user or path_user != user:
        return json_response(403, {"message": i18n.t("err.forbidden", loc)}, _HEADERS)
    if not plans.enabled():
        return json_response(404, {"message": i18n.t("err.not_found", loc)}, _HEADERS)
    if "/purchases/" in resource:
        store = str(((event or {}).get("pathParameters") or {}).get("store") or resource.rsplit("/", 1)[-1])
        if store not in ("apple", "google"):
            return json_response(404, {"message": i18n.t("err.not_found", loc)}, _HEADERS)
        return not_built(loc)
    try:
        return json_response(200, view(user, event, loc), _HEADERS)
    except Exception:   # noqa: BLE001
        logger.exception("PLAN_READ_FAILED")
        return json_response(500, {"message": i18n.t("err.generic", loc)}, _HEADERS)
