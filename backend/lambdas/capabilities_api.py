"""GET /users/{user_id}/capabilities : what the apps may offer when creating a video (formats, resolutions, platforms, languages, limits).

No data access: the answer comes from the server settings (READY_ASPECTS, BETA_ASPECTS, READY_LANGUAGES, INTAKE_ENABLED), see engine/format_options.py.
The path user must be the signed-in user, like every other route.
"""
from typing import Any, Dict

import logging
import time

from common import free_grants, i18n, looks as look_flags, ops_switches, plans, wallet, watermark_store
from common.http import json_response
from common.identity import extract_cognito_sub
from engine import format_options

logger = logging.getLogger()


def add_plan(body: Dict[str, Any], user: str, event: Dict[str, Any], loc: str) -> None:
    """The plan part of the answer (docs/PLANS.md): which plan, its limits, what is locked and the plan that unlocks it, the three plans for a paywall, whether a plan can be
    bought yet, and what the Free plan offers this account right now (`free_creation`: none | welcome | daily; `free.available`, `free.reason`, `free.credits_left`,
    `free.budget_paused`). Read only: nothing is granted here. The existing lists keep every option and gain `available` / `requires_plan`, so a locked option shows its badge."""
    w = wallet._balance_plans(user, now=time.time(), tz=None, ctx=free_grants.context(event), grant=False)
    limits = w["plan"]["limits"]
    body["plan"] = {**w["plan"], "plans": plans.catalog()}
    body["free_creation"], body["free"], body["can_upgrade"] = w["free_creation"], w["free"], w["can_upgrade"]
    body["free"]["message"] = i18n.t(f"plan.free.{w['free']['reason']}", loc) if w["free"]["reason"] else None
    for r in body.get("resolutions", []):
        r["available"] = r["id"] in limits["resolutions"]
        r["requires_plan"] = None if r["available"] else plans.lowest_plan(lambda x, rid=r["id"]: rid in x["resolutions"])
    body["lengths"].update({"plan_max_seconds": limits["max_seconds"], "plan_max_minutes": limits["max_minutes"],
                            "locked": [x for x in w["plan"]["locked"] if x["feature"] == "length"]})
    body["plan_max_photos"] = min(int(body.get("max_photos") or limits["photos_per_video"]), limits["photos_per_video"])


def looks(loc: str) -> Dict[str, Any]:
    """The looks a video can have on THIS stage (docs/CREATE_API.md "Looks"): the scene style the person may choose (`style` in generate) and which moving
    backgrounds the director can use here (nothing to send: the director decides per video). From the server switches VECTOR_SCENES, BG_ANIMATED and BG_LOOPS."""
    f = look_flags.flags()   # the same switches the request check reads (common/looks.py), so the two can never disagree
    cartoon = f["cartoon"]
    return {
        "style": {"param": "style", "default": "auto", "options": [
            {"id": "auto", "label": i18n.t("cap.look.auto", loc), "note": i18n.t("cap.look.auto_note" if cartoon else "cap.look.auto_note_real", loc), "available": True},
            {"id": "cartoon", "label": i18n.t("cap.look.cartoon", loc), "note": i18n.t("cap.look.cartoon_note", loc), "available": cartoon},
            {"id": "real", "label": i18n.t("cap.look.real", loc), "note": i18n.t("cap.look.real_note", loc), "available": True},
            # the whiteboard look (docs/WHITEBOARD.md): a whole video drawn and written by a marker; server switch WHITEBOARD
            {"id": "whiteboard", "label": i18n.t("cap.look.whiteboard", loc), "note": i18n.t("cap.look.whiteboard_note", loc), "say": i18n.t("cap.look.whiteboard_say", loc), "available": f["whiteboard"]}]},
        "backgrounds": {"animated": f["bg_animated"], "loops_3d": f["bg_loops"], "chosen_by": "director", "note": i18n.t("cap.look.backgrounds_note", loc),
                        # what a person can write in the request to ask for one (engine/background.request_wish reads the words; there is no request field)
                        "ask": ([{"id": lid, "label": i18n.t(f"cap.look.bg.{key}", loc), "say": i18n.t(f"cap.look.bg.{key}_say", loc)}
                                 for lid, key in (("gas-brand-dark", "purple"), ("gas-ember-dark", "warm"), ("gas-aurora-dark", "green"), ("gas-brand-light", "light")) if f["bg_loops"]]
                                + [{"id": k, "label": i18n.t(f"cap.look.bg.{k}", loc), "say": i18n.t(f"cap.look.bg.{k}_say", loc)} for k in ("animated", "none") if f["bg_animated"] or f["bg_loops"]])},
    }


_THUMBS: Dict[str, str] = {}


def presenter(loc: str, on: bool) -> Dict[str, Any]:
    """The presenter characters (docs/PRESENTERS.md): the create option `presenter` (auto | none | a character id), the words that ask for one, and the cast with a
    small face picture each (a PNG data URI, 112 px). `available` follows the server switch PRESENTERS; where it is off the cast is still listed, for a "coming soon"."""
    import json
    import os

    from engine import presenter_policy as pp

    if not _THUMBS:
        try:
            with open(os.path.join(os.path.dirname(os.path.abspath(i18n.__file__)), "presenter_thumbs.json"), encoding="utf-8") as fh:
                _THUMBS.update(json.load(fh))
        except Exception:   # noqa: BLE001 - a missing picture never stops the creation options
            logger.exception("CAPABILITIES_PRESENTER_THUMBS_FAILED")
    lang = "es" if loc == "es" else "en"
    return {"param": "presenter", "default": "auto", "available": on,
            "options": [{"id": "auto", "label": i18n.t("cap.presenter.auto", loc), "note": i18n.t("cap.presenter.auto_note", loc)},
                        {"id": "none", "label": i18n.t("cap.presenter.none", loc), "note": i18n.t("cap.presenter.none_note", loc)}],
            "cast": [{"id": cid, "name": pp.CAST[cid]["name"], "role": pp.CAST[cid]["role"][lang], "thumbnail": _THUMBS.get(cid)} for cid in pp.ORDER],
            "say": i18n.t("cap.presenter.say", loc), "note": i18n.t("cap.presenter.note" if on else "cap.presenter.soon", loc)}


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
    try:
        body["looks"]["presenter"] = presenter(loc, look_flags.flags()["presenters"])
    except Exception:   # noqa: BLE001
        logger.exception("CAPABILITIES_PRESENTER_FAILED")
    if plans.enabled():   # a read failure must never stop the creation options: the launcher still enforces
        try:
            add_plan(body, user, event, loc)
        except Exception:   # noqa: BLE001
            logger.exception("CAPABILITIES_PLAN_FAILED")
    creation = ops_switches.creation_state(loc)   # the owner's switch "stop all new videos" (the launcher then answers 503 `maintenance`); fails open
    if creation["paused"]:   # only then: `creation: {"paused": true, "code": "maintenance", "message": ...}`, so the apps can say it before the tap (absent = running)
        body["creation"] = creation
    return json_response(200, body, {"Cache-Control": "private, max-age=60", "Content-Language": loc, **i18n.vary_headers()})
