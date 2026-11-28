"""The video look a person CHOOSES, and that the engine then ENFORCES (docs/CREATE_API.md "Video look (chosen and enforced)").

One choice instead of the scattered `style` / `presenter` wishes (which keep working):
  * `look`   : auto | real | whiteboard | cartoon            (`presenters` is accepted as another name for `cartoon`)
  * `cast`   : "auto" or 1 to 3 character ids                (look `cartoon` only; 2 or 3 = a conversation between them)
  * `extras` : a list of switches the look allows; today only `board` on `cartoon` (the characters explain on a hand-drawn board)
  * `cast` entries may also be `{"id": "fox", "language": "fr"}`: that character speaks its OWN language (docs/CREATE_API.md "Characters that speak different languages").
    Normalised to the same id list plus a `cast_languages` map, so a client (and the engine) that only knows ids keeps working.
  * `translation` : auto | on | off, the translation line under lines spoken in another language than the video's

This module is the contract's single home for the three users that must agree: the launcher (`parse`: a bad value is a 400), the request check and the launcher's
202 answer (`resolve`: what the video will get and, when it cannot be given as chosen, why), and capabilities (`capabilities`: the picker, the cast, the previews).
The engine's side (which scene types belong to a look, validation and repair of a plan) is `engine/art_direction.py`.
Pure: reads the server switches through `common.looks.flags()`, nothing else.
"""
import json
import os
from typing import Any, Dict, List, Optional

from common import i18n, looks

LOOKS = ("auto", "real", "whiteboard", "cartoon")
ALIASES = {"presenters": "cartoon", "characters": "cartoon"}
EXTRAS = {"cartoon": ("board",)}                     # look -> the extras it allows
MAX_CAST = 3
# The cast (ids and kind) without importing the engine: the request-check function ships `common` only. tests/test_look_choice.py pins it to engine/presenter_policy.
PEOPLE = ("ines", "david", "priya", "mateo")
ANIMALS = ("fox", "owl", "bear", "cat", "parrot", "turtle")
CAST_IDS = PEOPLE + ANIMALS
# What each look needs (docs/CREATE_API.md): the server switches, the shortest video it works in, the shapes it looks best in.
NEEDS = {"auto": (), "real": (), "whiteboard": ("whiteboard",), "cartoon": ("presenters",)}
MIN_SECONDS = {"auto": 15, "real": 15, "whiteboard": 15, "cartoon": 15}
CONVERSATION_MIN_SECONDS = 20                        # two or three characters need at least a question, an answer and a goodbye
BEST_ASPECTS = {"auto": ["16:9", "9:16", "1:1", "4:5"], "real": ["16:9", "9:16", "1:1", "4:5"], "whiteboard": ["16:9", "1:1"], "cartoon": ["16:9", "1:1", "4:5"]}
# Topics each character suits (shown under the face in the cast picker; the automatic casting uses the same idea: engine/presenter_policy.CAST words)
TOPICS = {"ines": "school", "david": "technology", "priya": "health", "mateo": "food", "fox": "kids", "owl": "science", "bear": "feelings", "cat": "gadgets", "parrot": "travel", "turtle": "nature"}
TRANSLATIONS = ("auto", "on", "off")
LANGUAGE_MIN_SECONDS = {2: 20, 3: 30}                # six seconds a line: three languages need 30 s, two need 20 s (design doc 2.9)
WOMEN_ONLY = ("nl", "pl", "fi")                      # the voice catalogue has no man's voice in these (docs/LANGUAGES.md)
RECIPES = ("footage", "whiteboard", "presenter", "conversation", "presenter_board", "conversation_board")


class Invalid(ValueError):
    """A value of `look`, `cast` or `extras` that is not in the contract: HTTP 400 with this message."""


def clean_look(v: Any) -> Optional[str]:
    v = ALIASES.get(v, v) if isinstance(v, str) else v
    return v if isinstance(v, str) and v in LOOKS else None


def polyglot_enabled() -> bool:
    """Server switch POLYGLOT (characters that speak different languages; docs/MULTILINGUAL_CONVERSATIONS_DESIGN_2026-11-27.md): off where nothing is set."""
    return os.environ.get("POLYGLOT", "").lower() in ("1", "true")


def stage_languages() -> List[str]:
    """The languages a character can speak on this stage: the engine's `voices.enabled()` (server setting VIDEO_LANGUAGES), read here without importing the engine when it is not beside this module."""
    try:
        from engine import voices
        return list(voices.enabled())
    except Exception:   # noqa: BLE001 - the request-check function ships `common` only: read the same setting
        ready = ("en", "es", "fr", "de", "it", "pt", "nl", "pl", "fi")
        asked = [x.strip().lower() for x in os.environ.get("VIDEO_LANGUAGES", "en,es").split(",")]
        return [x for x in ready if x in asked] or ["en", "es"]


def parse(body: Dict[str, Any]) -> Dict[str, Any]:
    """The look part of a create request, normalised: {} when nothing was chosen, else {"look": id, "cast"?: [ids], "cast_languages"?: {id: language}, "extras"?: [ids]},
    and `translation` ("on" | "off") when chosen. Absent or `auto` values are left out (so a request that chooses nothing is stored and fingerprinted exactly as before).
    A `cast` entry is an id or {"id", "language"}. Raises `Invalid`."""
    out: Dict[str, Any] = {}
    look = None
    if body.get("look") is not None:
        look = clean_look(body["look"])
        if look is None:
            raise Invalid("'look' must be one of: " + ", ".join(LOOKS))
    cast: List[str] = []
    cast_languages: Dict[str, str] = {}
    if body.get("cast") is not None and body["cast"] != "auto":
        raw = body["cast"]
        bad = f"'cast' must be 'auto' or a list of 1 to {MAX_CAST} different character ids (or {{\"id\", \"language\"}} objects): " + ", ".join(CAST_IDS)
        if not isinstance(raw, list) or not (1 <= len(raw) <= MAX_CAST):
            raise Invalid(bad)
        ids: List[str] = []
        for entry in raw:
            if isinstance(entry, dict):
                if set(entry) - {"id", "language"} or not isinstance(entry.get("id"), str):
                    raise Invalid(bad)
                cid, lang = entry["id"], entry.get("language")
            else:
                cid, lang = entry, None
            if not isinstance(cid, str) or cid not in CAST_IDS:
                raise Invalid(bad)
            ids.append(cid)
            if lang is not None and lang != "auto":
                if not isinstance(lang, str) or lang not in stage_languages():
                    raise Invalid(f"the language of '{cid}' must be one of: " + ", ".join(stage_languages()))
                cast_languages[cid] = lang
        if len(set(ids)) != len(ids):
            raise Invalid(bad)
        cast = ids
    if body.get("translation") is not None:
        if body["translation"] not in TRANSLATIONS:
            raise Invalid("'translation' must be one of: " + ", ".join(TRANSLATIONS))
        if body["translation"] != "auto":
            out["translation"] = body["translation"]
    extras: List[str] = []
    if body.get("extras") is not None:
        raw = body["extras"]
        known = sorted({e for v in EXTRAS.values() for e in v})
        if not isinstance(raw, list) or any(not isinstance(e, str) or e not in known for e in raw):
            raise Invalid("'extras' must be a list of: " + ", ".join(known))
        extras = sorted(set(raw))
    if (cast or extras) and look in (None, "auto"):   # choosing characters, or their board, IS choosing the look
        look = "cartoon"
    if cast and look != "cartoon":
        raise Invalid("'cast' is only for the look 'cartoon'")
    if any(e not in EXTRAS.get(look or "", ()) for e in extras):
        raise Invalid(f"'extras' {extras} are not available with the look '{look}'")
    if look and look != "auto":
        out["look"] = look
        if cast:
            out["cast"] = cast
            if cast_languages:
                out["cast_languages"] = cast_languages
        if extras:
            out["extras"] = extras
    return out


def from_legacy(options: Dict[str, Any]) -> Dict[str, Any]:
    """The chosen look of a request: its own `look`, else the old `style` field where it always meant the whole video (`real`, `whiteboard`).
    `style: "cartoon"` and `presenter: "<id>"` keep their old, softer meaning (docs/CREATE_API.md "Looks")."""
    if clean_look(options.get("look")) not in (None, "auto"):
        return {k: options[k] for k in ("look", "cast", "extras", "cast_languages") if options.get(k)} | {"look": clean_look(options["look"])}
    if options.get("style") in ("real", "whiteboard"):
        return {"look": options["style"]}
    return {}


def recipe(look: str, cast: Optional[List[str]] = None, extras: Optional[List[str]] = None) -> Optional[str]:
    """The named recipe of a chosen look (the same names the automatic art direction uses)."""
    if look == "real":
        return "footage"
    if look == "whiteboard":
        return "whiteboard"
    if look == "cartoon":
        return ("conversation" if len(cast or []) >= 2 else "presenter") + ("_board" if "board" in (extras or []) else "")
    return None


def available(look: str, f: Optional[Dict[str, bool]] = None) -> bool:
    f = looks.flags() if f is None else f
    return all(f.get(k) for k in NEEDS.get(look, ()))


def resolve(options: Dict[str, Any], lang: Optional[str] = None, *, media_count: int = 0, deck: bool = False, f: Optional[Dict[str, bool]] = None) -> Optional[Dict[str, Any]]:
    """What a CHOSEN look becomes, before the video starts. None when nothing was chosen (the old answers stay exactly as they were).

    -> {"chosen", "applied", "enforced": bool, "recipe", "cast": [ids] | "auto" (cartoon only), "extras": [ids], "reason": None | code, "note": None | sentence}
    A chosen look is never a reason to refuse: where it cannot be given the video is made as `applied` and `reason` says why:
      not_available (this stage does not have the look yet), own_photos, deck (the person's own pictures or slides ARE the look), too_short (a conversation in
      under 20 s: one character presents). Safety and plan limits are decided elsewhere and stop or shorten the video as for any request."""
    c = from_legacy(options)
    if not c:
        return None
    f = looks.flags() if f is None else f
    look, cast, extras = c["look"], list(c.get("cast") or []), list(c.get("extras") or [])
    applied, reason = look, None
    if look != "real" and (media_count > 0 or deck):
        applied, reason = "real", ("deck" if deck else "own_photos")
    elif not available(look, f):
        applied, reason = "auto", "not_available"
    seconds = float(options.get("target_minutes") or 0) * 60.0
    if applied == "cartoon" and len(cast) >= 2 and 0 < seconds < CONVERSATION_MIN_SECONDS:
        cast, reason = cast[:1], "too_short"
    if applied == "cartoon" and "board" in extras and not f.get("whiteboard"):
        extras, reason = [e for e in extras if e != "board"], "not_available"
    out = {"chosen": look, "applied": applied, "enforced": applied == look, "recipe": recipe(applied, cast, extras) if applied == look else None,
           "extras": extras if applied == "cartoon" else [], "reason": reason,
           "note": i18n.t(f"look.choice.{reason}", lang, look=i18n.t(f"cap.pick.{look}", lang)) if reason else None}
    if applied == "cartoon":
        out["cast"] = cast or "auto"
    asked_languages = {k: v for k, v in (c.get("cast_languages") or {}).items() if k in (c.get("cast") or [])}
    if asked_languages or options.get("translation"):
        out["languages"] = _languages_answer(asked_languages, cast, applied, seconds, options, lang)
        if out["languages"]["note"] and not out["note"]:
            out["note"] = out["languages"]["note"]
    return out


def _languages_answer(asked: Dict[str, str], cast: List[str], applied: str, seconds: float, options: Dict[str, Any], lang: Optional[str]) -> Dict[str, Any]:
    """What becomes of `cast_languages` (design doc 2.2): {"by_character": {id: language} that will be used, "translation", "reason": None | code, "note": None | sentence}.
    Never a refusal: where the languages cannot be given the video is made without them and `reason` says why.
    Reasons: not_available (this stage has no POLYGLOT), needs_cartoon (the look is not cartoon), needs_two (one character cannot take turns with itself),
    too_short (three languages need 30 s: the third is dropped)."""
    used, reason = dict(asked), None
    video_language = str(options.get("language") or "")
    if used and not polyglot_enabled():
        used, reason = {}, "not_available"
    elif used and applied != "cartoon":
        used, reason = {}, "needs_cartoon"
    elif used and len(cast) < 2:
        if not (len(used) == 1 and next(iter(used.values())) == video_language):   # one character speaking the video's own language is just a character
            reason = "needs_two"
        used = {}
    elif used and len(cast) == 3 and 0 < seconds < LANGUAGE_MIN_SECONDS[3]:
        used, reason = {k: v for k, v in used.items() if k in cast[:2]}, "too_short"
    note = i18n.t(f"look.choice.lang_{reason}", lang, n=len(cast) if reason == "too_short" else 0) if reason else None
    return {"by_character": used, "translation": options.get("translation") or "auto", "reason": reason, "note": note}


def answer(options: Dict[str, Any], lang: Optional[str] = None, **kw: Any) -> Dict[str, Any]:
    """The optional `look` (+ `note`) fields of the `brief` and `generate` answers for a chosen look; {} when nothing was chosen. The older keys of `look`
    (`style`, `asked`, `adapted`, `presenter`: docs/CREATE_API.md "Looks") are filled in the same terms, so a client that reads only those still gets the truth."""
    r = resolve(options, lang, **kw)
    if r is None:
        return {}
    note = r.pop("note")
    asked = ["cartoon", "characters"] if r["chosen"] == "cartoon" else [r["chosen"]]
    old = {"style": r["applied"], "asked": asked, "adapted": [] if r["enforced"] else asked, "presenter": r["applied"] == "cartoon"}
    return {"look": {**old, **r}, **({"note": note} if note else {})}


def merge(base: Dict[str, Any], chosen: Dict[str, Any]) -> Dict[str, Any]:
    """The answer for words in the request (`base`) with the answer for a chosen look on top: the choice wins, and takes the words' note with it."""
    if not chosen:
        return base
    out = {k: v for k, v in base.items() if k != "note"}
    out["look"] = {**(base.get("look") or {}), **chosen["look"]}
    if chosen.get("note"):
        out["note"] = chosen["note"]
    return out


_PREVIEWS: Dict[str, str] = {}


def _previews() -> Dict[str, str]:
    if not _PREVIEWS:
        with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "look_previews.json"), encoding="utf-8") as fh:
            _PREVIEWS.update(json.load(fh))
    return _PREVIEWS


def capabilities(loc: str, cast: List[Dict[str, Any]], *, f: Optional[Dict[str, bool]] = None, aspects: Optional[List[str]] = None,
                 plan_max_seconds: Optional[float] = None) -> Dict[str, Any]:
    """`capabilities.looks.look` and `capabilities.looks.cast`: the picker (at most four tiles, Auto first), per look where and when it can be used, and the cast.
    `cast` is the list capabilities already builds for `looks.presenter.cast` (id, name, role, thumbnail); kind and a topic are added here."""
    f = looks.flags() if f is None else f
    try:
        previews = _previews()
    except Exception:   # noqa: BLE001 - a missing picture never stops the creation options
        previews = {}
    shapes = aspects or ["16:9", "9:16", "1:1", "4:5"]
    options = []
    for lid in LOOKS:
        on = available(lid, f)
        allowed = plan_max_seconds is None or plan_max_seconds >= MIN_SECONDS[lid]
        options.append({
            "id": lid, "label": i18n.t(f"cap.pick.{lid}", loc), "note": i18n.t(f"cap.pick.{lid}_note", loc), "preview": previews.get(lid),
            "available": on,                                   # this stage has the look (a server switch); false: show "coming soon" or hide the tile
            "allowed": allowed, "requires_plan": None,         # this account's plan may use it (no look is behind a plan today; the plan's longest video must reach `min_seconds`)
            "with_photos": lid in ("auto", "real"), "with_deck": lid in ("auto", "real"),   # false: do not offer the tile when the request has own photos / a deck
            "min_seconds": MIN_SECONDS[lid], "aspects": shapes, "best_aspects": [a for a in BEST_ASPECTS[lid] if a in shapes],
            "cast": lid == "cartoon",                          # true: show the cast picker under the tile
            "extras": [{"id": e, "label": i18n.t(f"cap.pick.extra.{e}", loc), "note": i18n.t(f"cap.pick.extra.{e}_note", loc), "available": on and bool(f.get("whiteboard"))}
                       for e in EXTRAS.get(lid, ())]})
    return {
        "look": {"param": "look", "default": "auto", "enforced": True, "options": options},
        "cast": {"param": "cast", "default": "auto", "min": 1, "max": MAX_CAST, "available": available("cartoon", f),
                 "auto": {"id": "auto", "label": i18n.t("cap.cast.auto", loc), "note": i18n.t("cap.cast.auto_note", loc)},
                 "conversation": {"from": 2, "min_seconds": CONVERSATION_MIN_SECONDS, "note": i18n.t("cap.cast.conversation_note", loc)},
                 "members": [{**m, "kind": "animal" if m["id"] in ANIMALS else "person", "topic": i18n.t(f"cap.cast.topic.{TOPICS[m['id']]}", loc),
                              "languages": member_languages(m["id"], loc)} for m in cast if m["id"] in CAST_IDS],
                 "languages": language_options(loc, f)},
    }


def _voice_table() -> List[Dict[str, Any]]:
    try:
        from engine import voice_data
        return list(voice_data.VOICES)
    except Exception:   # noqa: BLE001 - without the engine there is no voice catalogue: no language options
        return []


def character_gender(cid: str) -> Optional[str]:
    """'female' | 'male': the gender of the voice the character has by default (the first English voice of the cast table, as the engine casts the other languages)."""
    try:
        from engine import presenter_policy, voices
        return voices.CATALOG[presenter_policy.CAST[cid]["voices"]["en"][0]][2]
    except Exception:   # noqa: BLE001
        return None


def voices_of(language: str) -> Dict[str, int]:
    """{"female": n, "male": n} generative voices the catalogue has for the language (engine/voice_data.py)."""
    out = {"female": 0, "male": 0}
    for v in _voice_table():
        if v.get("language") == language and "generative" in (v.get("engines") or ["generative"]):
            out[v["gender"]] = out.get(v["gender"], 0) + 1
    return out


def language_options(loc: str, f: Optional[Dict[str, bool]] = None) -> Dict[str, Any]:
    """`capabilities.looks.cast.languages`: whether characters may speak their own language here, the languages that have a voice, and the translation switch."""
    from common import lang_names
    on = polyglot_enabled() and available("cartoon", f)
    langs = []
    for code in stage_languages():
        n = voices_of(code)
        if n["female"] + n["male"]:
            langs.append({"id": code, "label": lang_names.name_of(code, native=True), "voices": n, "women_only": n["male"] == 0})
    return {"param": "cast[].language", "available": on, "max": MAX_CAST, "min_cast": 2, "note": i18n.t("cap.cast.languages_note", loc),
            "min_seconds": {str(k): v for k, v in LANGUAGE_MIN_SECONDS.items()}, "options": langs if on else [],
            "translation": {"param": "translation", "default": "auto", "options": [{"id": t, "label": i18n.t(f"cap.cast.translation.{t}", loc)} for t in TRANSLATIONS]}}


def member_languages(cid: str, loc: str) -> List[Dict[str, Any]]:
    """The languages a character can speak: [{"id", "voices": n, "note": None | "women_only" sentence}]. A language with only women's voices (nl, pl, fi) is offered to a
    man's character with a note: it speaks with a woman's voice."""
    from common import lang_names
    if not polyglot_enabled():
        return []
    gender, out = character_gender(cid), []
    for code in stage_languages():
        n = voices_of(code)
        total = n["female"] + n["male"]
        if not total:
            continue
        women_only = gender == "male" and n["male"] == 0
        out.append({"id": code, "voices": n.get(gender or "female", total) or total, "note": i18n.t("cap.cast.lang_women_only", loc, language=lang_names.name_of(code, native=True)) if women_only else None})
    return out
