"""GET /users/{user_id}/wallet : the user's credits (and grants today's free credits if due)."""
import logging
from typing import Any, Dict

from common import wallet
from common.http import json_response
from common.identity import extract_cognito_sub

logger = logging.getLogger()


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    path_user = ((event or {}).get("pathParameters") or {}).get("user_id")
    user = extract_cognito_sub(event)
    if not user:
        return json_response(401, {"message": "Unauthorized"})
    if not path_user or path_user != user:
        return json_response(403, {"message": "Forbidden"})
    headers = {str(k).lower(): v for k, v in ((event or {}).get("headers") or {}).items()}
    tz = str(headers.get("x-timezone") or "").strip() or None
    try:
        return json_response(200, wallet.balance(user, tz=tz))
    except Exception:
        logger.exception("wallet read failed")
        return json_response(500, {"message": "Couldn't read your credits. Please try again."})
