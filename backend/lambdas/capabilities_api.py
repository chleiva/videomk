"""GET /users/{user_id}/capabilities : what the apps may offer when creating a video (formats, resolutions, platforms, languages, limits).

No data access: the answer comes from the server settings (READY_ASPECTS, BETA_ASPECTS, READY_LANGUAGES, INTAKE_ENABLED), see engine/format_options.py.
The path user must be the signed-in user, like every other route.
"""
import os
from typing import Any, Dict

from common import i18n, watermark_store
from common.http import json_response
from common.identity import extract_cognito_sub
from engine import format_options


def _on(name: str) -> bool:
    return os.environ.get(name, "0").strip().lower() in ("1", "true", "on", "yes")


def looks(loc: str) -> Dict[str, Any]:
    """The looks a video can have on THIS stage (docs/CREATE_API.md "Looks"): the scene style the person may choose (`style` in generate) and which moving
    backgrounds the director can use here (nothing to send: the director decides per video). From the server switches VECTOR_SCENES, BG_ANIMATED and BG_LOOPS."""
    cartoon = _on("VECTOR_SCENES")
    return {
        "style": {"param": "style", "default": "auto", "options": [
            {"id": "auto", "label": i18n.t("cap.look.auto", loc), "note": i18n.t("cap.look.auto_note" if cartoon else "cap.look.auto_note_real", loc), "available": True},
            {"id": "cartoon", "label": i18n.t("cap.look.cartoon", loc), "note": i18n.t("cap.look.cartoon_note", loc), "available": cartoon},
            {"id": "real", "label": i18n.t("cap.look.real", loc), "note": i18n.t("cap.look.real_note", loc), "available": True}]},
        "backgrounds": {"animated": _on("BG_ANIMATED"), "loops_3d": _on("BG_LOOPS"), "chosen_by": "director", "note": i18n.t("cap.look.backgrounds_note", loc)},
    }


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    path_user = ((event or {}).get("pathParameters") or {}).get("user_id")
    loc = i18n.pick_locale(event)
    user = extract_cognito_sub(event)
    if not user:
        return json_response(401, {"message": i18n.t("err.unauthorized", loc)})
    if not path_user or path_user != user:
        return json_response(403, {"message": i18n.t("err.forbidden", loc)})
    # the labels and notes follow the locale, so a cache must key on it (Vary) and the answer says which language it is in
    body = format_options.capabilities(loc)
    if watermark_store.enabled():   # what this account may use as a watermark (docs/WATERMARK.md); a read failure must never stop the creation options
        try:
            body["watermark"] = watermark_store.capabilities(user, loc)
        except Exception:   # noqa: BLE001
            pass
    body["looks"] = looks(loc)
    return json_response(200, body, {"Cache-Control": "private, max-age=60", "Content-Language": loc, **i18n.vary_headers()})
