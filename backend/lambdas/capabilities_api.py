"""GET /users/{user_id}/capabilities : what the apps may offer when creating a video (formats, resolutions, platforms, languages, limits).

No data access: the answer comes from the server settings (READY_ASPECTS, BETA_ASPECTS, READY_LANGUAGES, INTAKE_ENABLED), see engine/format_options.py.
The path user must be the signed-in user, like every other route.
"""
from typing import Any, Dict

from common import i18n
from common.http import json_response
from common.identity import extract_cognito_sub
from engine import format_options


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    path_user = ((event or {}).get("pathParameters") or {}).get("user_id")
    loc = i18n.pick_locale(event)
    user = extract_cognito_sub(event)
    if not user:
        return json_response(401, {"message": i18n.t("err.unauthorized", loc)})
    if not path_user or path_user != user:
        return json_response(403, {"message": i18n.t("err.forbidden", loc)})
    # the labels and notes follow the locale, so a cache must key on it (Vary) and the answer says which language it is in
    return json_response(200, format_options.capabilities(loc), {"Cache-Control": "private, max-age=60", "Content-Language": loc, **i18n.vary_headers()})
