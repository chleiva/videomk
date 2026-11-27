"""POST /users/{user_id}/videos/brief: the request check, called by the app when the person taps Create, before `generate` (docs/CREATE_API.md).

Safety, 'can we make this' and 'is it clear enough' in one small-model call. Nothing is charged here, nothing is stored except a stop (common/safety.py).
Stateless: the answers carry all state, so calling again with the same input gives the same kind of result. The app treats any failure of this endpoint as 'ok'.
"""
import json
import logging
import os
from typing import Any, Dict, Optional

from common import i18n, intake, looks, safety, usage
from common.http import json_response
from common.identity import extract_cognito_sub

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DAILY_CALLS = int(os.environ.get("BRIEF_DAILY_LIMIT", "400"))   # generous: a person editing a prompt ten times a day is far below this


def _body(event: Dict[str, Any]) -> Dict[str, Any]:
    body = event.get("body")
    if isinstance(body, str):
        try:
            body = json.loads(body or "{}")
        except json.JSONDecodeError as e:
            raise intake.Invalid("Body must be valid JSON") from e
    if not isinstance(body, dict):
        raise intake.Invalid("Body must be a JSON object")
    return body


def _look(prompt: str, options: Dict[str, Any], media_count: int, lang: str, chk: Optional[intake.Check] = None) -> Dict[str, Any]:
    """The look part of an answer that lets the video go on (docs/CREATE_API.md "Looks"): `look` = what the person asked for and what the video gets, and `note` = one
    short friendly sentence when a wish was adapted ("Made as a narrated explainer with animated backgrounds; talking characters are coming soon."). Never a blocker."""
    r = looks.resolve(prompt, options.get("style"), lang, model=chk.look if chk else None, media_count=media_count)
    if not r["asked"] and not r["note"]:
        return {}
    out: Dict[str, Any] = {"look": {"style": r["style"], "asked": r["asked"], "adapted": r["adapted"], "presenter": r["presenter"]}}
    if r["note"]:
        out["note"] = r["note"]
    return out


def _ok(brief: Dict[str, Any], look: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    return json_response(200, {"status": "ok", "brief": brief, **(look or {})})


def handler(event: Dict[str, Any], context: Any, *, ask: Optional[intake.Ask] = None):
    path_user = ((event or {}).get("pathParameters") or {}).get("user_id")
    user_id = extract_cognito_sub(event)
    loc = i18n.pick_locale(event)
    if not user_id:
        return json_response(401, {"message": i18n.t("err.unauthorized", loc)})
    if not path_user or path_user != user_id:
        return json_response(403, {"message": i18n.t("err.forbidden", loc)})
    try:
        body = _body(event)
        prompt = intake.clean_prompt(body.get("prompt"))
        options = intake.clean_options(body.get("options"))
        answers = intake.clean_answers(body.get("answers"))
        media_count = intake.clean_media_count(body.get("media_count"))
    except intake.Invalid as e:
        return json_response(400, {"message": i18n.error_text(e, loc)})

    lang = i18n.explicit_locale(event) or safety.guess_language(prompt, options.get("language") if options.get("language") in ("en", "es") else None)
    note_lang = i18n.explicit_locale(event) or looks.guess_lang(prompt, options.get("language"))   # the app's language, else the language the request is written in
    stopped = intake.paused(user_id, lang)
    if stopped:
        return json_response(429, stopped, {"Retry-After": str(stopped["retry_after"])})

    brief = intake.apply_answers(answers)
    try:
        usage.consume(f"brief:{user_id}", limit=DAILY_CALLS)
    except usage.QuotaExceeded:
        # over the generous cap: no model call, only the free deterministic screen; generate checks the request again anyway
        cat = safety.screen(prompt + " " + intake.free_text(answers))
        if cat:
            return json_response(200, intake.stop(user_id, intake.Check(block=cat, source="fallback"), prompt, lang))
        return _ok(brief, _look(prompt, options, media_count, note_lang))
    except Exception:
        logger.exception("brief rate limiter unavailable")

    # Round two with only option taps (no free text) changes nothing about the request that was already checked in round one: skip the model, build the brief.
    # (generate checks the request itself again, so skipping the first call cannot bypass anything.)
    if answers and not intake.free_text(answers):
        return _ok(brief, _look(prompt, options, media_count, note_lang))

    chk = intake.check(prompt, options=options, media_count=media_count, answers=answers, ask=ask)
    logger.info("BRIEF_CHECK ms=%s source=%s block=%s unsupported=%s questions=%s", chk.ms, chk.source, bool(chk.block), bool(chk.unsupported), len(chk.questions))
    if chk.block:
        return json_response(200, intake.stop(user_id, chk, prompt, lang))
    if chk.unsupported:
        return json_response(200, {"status": "not_supported", "message": chk.unsupported["message"], "suggestion": chk.unsupported["suggestion"]})
    look = _look(prompt, options, media_count, note_lang, chk)
    if look.get("note"):
        logger.info("BRIEF_LOOK asked=%s adapted=%s style=%s", look["look"]["asked"], look["look"]["adapted"], look["look"]["style"])
    if chk.questions:
        return json_response(200, {"status": "questions", "questions": chk.questions, **look})
    return _ok(brief, look)
