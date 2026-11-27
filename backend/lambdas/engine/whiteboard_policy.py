"""When is a video a WHITEBOARD video, and what the director is told then (docs/WHITEBOARD.md).

The whiteboard look is a whole-video style: when it is on for a video, every beat is a `whiteboard` scene (engine/scenes/elements/whiteboard.py). It is on when
  * the server setting WHITEBOARD is on (default OFF), and
  * the person asked for it: the create option `style: "whiteboard"`, or plain words in the request ("as a whiteboard video", "estilo pizarra", ...), or
  * the director may choose by itself (`style` auto) and the request is an explainer of a process or concept with nothing that needs real pictures:
    the producer's kind of video (engine/skills.py) must be one that suits it AND one small model call must agree. Any doubt is "no".
It is never on for a video made from the person's photos or a deck, for current events (web research), or when the person asked for real footage or cartoons.

This module decides (`decide`), writes the prompt block that teaches the director the scene (`Policy.prompt_block`), is the gate `whiteboard` scenes are checked
against while the plan is cleaned (`scope`, `allowed`), and afterwards turns the few beats the director left as text into boards (`enforce`).
Pure of storage and billing; the only model call (`ask`) is injected.
"""
import logging
import os
import re
import threading
from typing import Any, Callable, Dict, List, Optional

STYLE = "whiteboard"
# What the person may write in the request (English and Spanish).
_WISH_RE = re.compile(r"\b(white\s?board(?:[- ]style| video| animation| look| explainer)?|draw(?:n)? (?:it |this )?on a (?:white\s?board|board)|hand[- ]drawn (?:video|style|explainer|animation|look)|"
                      r"marker (?:drawings?|sketch(?:es)?)|doodle (?:video|style)|sketch(?:ed)? (?:video|style|explainer)|"
                      r"(?:estilo|tipo|en|como|sobre una?) (?:de )?pizarr[aó]n?(?: blanc[ao])?|pizarra blanca|v[ií]deo de pizarra|dibujad[oa] a mano|dibujos? a mano|estilo (?:de )?boceto)\b", re.I)
_NOT_RE = re.compile(r"\b(no (?:white\s?board|hand[- ]drawn|drawings?)|(?:don'?t|do not|without) (?:use |using |a |any )?(?:white\s?board|drawings?)|sin (?:pizarra|dibujos)|"
                     r"real (?:footage|videos?|photos?|photographs?|pictures|images)|stock (?:footage|videos?)|im[aá]genes reales|fotos? reales|metraje real)\b", re.I)
# The producer's kinds of video (engine/skills.py). On `auto` only these may become a whiteboard video, and only if the small model agrees.
AUTO_SKILLS = {"explainer-education", "science-wonder", "tutorial-howto", "finance-business", "health-wellbeing", "kids-family"}
NEVER_SKILLS = {"news-explainer", "product-marketing", "history-story", "mystery-true-crime", "biography-profile", "deck-explainer", "photo-memories", "recap-summary", "travel-places"}
CLASSIFY_SYSTEM = (
    "You decide whether a video request suits a WHITEBOARD explainer: simple marker drawings of common objects, short hand-written labels, numbers and arrows, drawn while the narrator explains. "
    'Answer ONLY JSON: {"fit": true|false, "why": "<10 words"}. '
    "fit is true only when BOTH hold. (1) The video explains HOW something works or WHY: a process, a cycle, steps, a concept, a comparison of ideas, basic maths, money or science, a habit or method. "
    "(2) Nothing in it needs real pictures: it is not about a named real person, place, brand, product, company or event; not news or recent events; not history told through real people and places; "
    "not travel, food, sport or anything that must be seen for real; not tragedy, war, violence or crime. When unsure, fit is false.")
MAX_MENU_CHARS = 9000


def enabled() -> bool:
    """Server setting WHITEBOARD (default OFF; 1/true/on enables)."""
    return os.environ.get("WHITEBOARD", "0").strip().lower() in ("1", "true", "on", "yes")


def wish(option: Any, prompt: str) -> str:
    """'whiteboard' when the person asked for it (the option wins, then their words), 'no' when their words rule it out, else 'auto'."""
    if option == STYLE:
        return STYLE
    if option in ("cartoon", "real"):
        return "no"
    text = prompt or ""
    if _NOT_RE.search(text):
        return "no"
    return STYLE if _WISH_RE.search(text) else "auto"


class Policy:
    def __init__(self, allowed: bool, reason: str, *, asked: bool = False, flag: bool = True, judged: Optional[Dict[str, Any]] = None):
        self.allowed, self.reason, self.asked, self.flag, self.judged = allowed, reason, asked, flag, judged

    def summary(self) -> Dict[str, Any]:
        return {"decision": "whiteboard" if self.allowed else "no", "reason": self.reason, "asked": self.asked, **({"judged": self.judged} if self.judged else {})}

    def prompt_block(self, language: str = "en") -> str:
        """The paragraph added to the director's prompt (empty when the look is off for this video)."""
        if not self.allowed:
            return ""
        from .whiteboard import library

        cats: Dict[str, List[str]] = {}
        for it in library.index()["items"]:
            cats.setdefault(it.get("category") or "other", []).append(it["id"])
        menu = "\n".join(f"    {c}: {', '.join(v)}" for c, v in cats.items())[:MAX_MENU_CHARS]
        return (
            "\n\nWHITEBOARD VIDEO. This whole video is a whiteboard explainer: EVERY beat's scene is of type `whiteboard` (no other scene type, no photographs, no clips, no charts).\n"
            "- whiteboard: {items: [...]}. A board that a marker draws and writes on while the narrator speaks. You give MEANING, never coordinates. Items, in the order they are drawn:\n"
            '    {"id": "<short name>", "draw": "<a drawing id from the list below>", "zone": "<zone>", "say": "<ONE word of this beat\'s narration>", "size": "s|m|l"}\n'
            '    {"id": "...", "write": "<1 to 6 words, a number, or a short formula>", "zone": "<zone>" (or "near": "<id>", "side": "below|above|left|right"), "say": "<one word>", "size": "s|m|l|xl", "tool": "marker|pen", "ink": "black|blue|red|orange|green"}\n'
            '    {"id": "...", "connect": "arrow|wavy|dashed", "from": "<id>", "to": "<id>", "color": "blue|red|orange|green|grey"}\n'
            '    {"id": "...", "mark": "underline|double_underline|circle|box|tick|cross|highlight", "on": "<id>", "color": "red|blue|green|orange"}\n'
            "  Zones: top-left, top, top-right, left, centre, right, bottom-left, bottom, bottom-right (one drawing per zone; a label goes `near` its drawing). A title or a list may use a wide zone: top-row, left-wide, right-wide, bottom-row.\n"
            "  Rules:\n"
            "  * 4 to 8 items per beat: usually 2 or 3 drawings or written phrases, joined by arrows, plus one or two marks. Never an empty board, never more than 9 drawings and texts.\n"
            "  * `say` is the exact narration word at which the item is finished, in the order the narration says them: the sun is drawn as the narrator says \"sun\". Write the narration so that it NAMES what is drawn.\n"
            "  * Keep the pen busy: when the narration goes on for more than a few words with nothing new to draw, add an arrow between two things, or a mark (underline, circle, tick) on something already there.\n"
            "  * Writing is for titles, key terms, numbers and short formulas, never whole sentences. Numbers and results are WRITTEN big (size l or xl) and then circled or underlined; a comparison is two written numbers; "
            "a list is one `write` with a line per point (\"1. ...\\n2. ...\"), tool pen. Markup: ^{2} for a power, _{2} for a subscript, \\frac{a}{b}, -> for an arrow.\n"
            "  * Use ONLY drawing ids from the list. If nothing in the list shows the idea, WRITE the word instead (a written label is always fine); never invent an id.\n"
            "  * People are the simple figures of the list (person_*, doctor, teacher...); never a real, named person.\n"
            "  * The first beat is a board with the video's question or title written (zone top or centre) and one drawing. The last beat sums up: the key term written large, underlined twice.\n"
            f"  Drawing ids, by group:\n{menu}"
        )


def decide(prompt: str, *, options: Optional[Dict[str, Any]] = None, skill_ids: Optional[List[str]] = None, photos: Optional[List[Any]] = None, research_mode: str = "encyclopedia",
           ask: Optional[Callable[[str, str], str]] = None) -> Policy:
    """Is this video a whiteboard video? Cheap rules first; one small-model call only for `auto` on a kind of video that could suit it."""
    o = options or {}
    w = wish(o.get("style"), prompt)
    flag = enabled()

    def no(reason: str) -> Policy:
        return Policy(False, reason, asked=w == STYLE, flag=flag)

    if not flag:
        return no("flag_off")
    if w == "no":
        return no("other_style")
    if photos:
        return no("user_media")
    if o.get("deck"):
        return no("deck")
    if w == STYLE:
        return Policy(True, "asked", asked=True)
    if research_mode == "web":
        return no("current_events")
    ids = set(skill_ids or [])
    if ids & NEVER_SKILLS or not ids & AUTO_SKILLS:
        return no("kind_of_video")
    if ask is None:
        return no("no_classifier")
    judged = _classify(prompt, ask)
    if not judged["fit"]:
        return Policy(False, "not_suited", judged=judged)
    return Policy(True, "auto", judged=judged)


def _classify(prompt: str, ask: Callable[[str, str], str]) -> Dict[str, Any]:
    import json

    for _ in range(2):
        try:
            raw = ask(CLASSIFY_SYSTEM, f"Video request: {(prompt or '')[:600]}")
            data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
            return {"fit": data.get("fit") is True, "why": str(data.get("why") or "")[:80]}
        except Exception:  # noqa: BLE001
            continue
    logging.warning("whiteboard policy classification failed twice; treated as not suited")
    return {"fit": False, "why": "classifier failed"}


_lock = threading.Lock()
_active: Optional[Policy] = None   # a plain global, as in vector_policy: the long-video writer validates sections on worker threads


class scope:
    """`with whiteboard_policy.scope(policy):` makes it the policy `allowed()` answers for (one video per process at a time, as in a Lambda)."""

    def __init__(self, policy: Optional[Policy]):
        self.policy = policy

    def __enter__(self) -> Optional[Policy]:
        global _active
        with _lock:
            self._prev, _active = _active, self.policy
        return self.policy

    def __exit__(self, *exc: Any) -> None:
        global _active
        with _lock:
            _active = self._prev


def allowed() -> bool:
    """May a `whiteboard` scene stay in the plan being cleaned right now?"""
    return _active is not None and _active.allowed


def board_for(scene: Dict[str, Any], narration: str) -> Optional[Dict[str, Any]]:
    """An ordinary text scene as a board, for the beats the director did not write as one: a title becomes a written title, bullets a written list, a stat a big
    circled number. Anything else (a photograph, a chart, a map) has no honest board and is left as it is."""
    t, p = scene.get("type"), scene.get("props") or {}
    if t == "title":
        items: List[Dict[str, Any]] = [{"id": "title", "write": str(p.get("title") or "")[:60], "zone": "centre", "size": "l"}]
        if p.get("subtitle"):
            items.append({"id": "sub", "write": str(p["subtitle"])[:60], "near": "title", "side": "below", "size": "s", "tool": "pen"})
        items.append({"id": "line", "mark": "underline", "on": "title", "color": "red"})
    elif t == "bullets":
        lines = [str(x)[:60] for x in (p.get("items") or [])[:5] if str(x).strip()]
        if not lines:
            return None
        items = ([{"id": "head", "write": str(p["heading"])[:50], "zone": "top", "size": "m"}] if p.get("heading") else []) + \
                [{"id": "list", "write": "\n".join(f"{i + 1}. {x}" for i, x in enumerate(lines)), "zone": "left-wide", "tool": "pen", "size": "m"}]
    elif t in ("stat", "counter"):
        value = " ".join(str(p.get(k) or "") for k in ("prefix", "value", "unit")).strip() or str(p.get("value") or "")
        if not value:
            return None
        items = [{"id": "num", "write": value[:24], "zone": "centre", "size": "xl", "ink": "blue"}, {"id": "ring", "mark": "circle", "on": "num", "color": "red"}]
        if p.get("label"):
            items.append({"id": "label", "write": str(p["label"])[:50], "near": "num", "side": "below", "size": "s", "tool": "pen"})
    elif t in ("quote", "kinetic_text", "definition", "question_card"):
        text = str(p.get("text") or p.get("quote") or p.get("term") or p.get("question") or "")[:60]
        if not text:
            return None
        items = [{"id": "text", "write": text, "zone": "centre", "size": "l"}, {"id": "line", "mark": "underline", "on": "text", "color": "red"}]
    else:
        return None
    return {"type": "whiteboard", "props": {"items": [it for it in items if it.get("write") or it.get("mark")]}}


def enforce(plan: Dict[str, Any], policy: Optional[Policy], sanitize: Optional[Callable[[Dict[str, Any]], Dict[str, Any]]] = None) -> List[str]:
    """After the plan is cleaned. Look ON: text beats the director did not write as boards become boards; records plan["whiteboard"]. Look OFF: any stray
    `whiteboard` scene was already refused while cleaning (`allowed`). Returns warnings."""
    warnings: List[str] = []
    if policy is None:
        return warnings
    plan["whiteboard"] = policy.summary()
    if not policy.allowed:
        return warnings
    if sanitize is None:
        from .scenes import ELEMENTS

        sanitize = ELEMENTS["whiteboard"].sanitize
    boards = other = 0
    for i, b in enumerate(plan.get("beats") or []):
        sc = b.get("scene") or {}
        if sc.get("type") == "whiteboard":
            boards += 1
            continue
        made = board_for(sc, str(b.get("narration") or ""))
        if made is not None:
            try:
                b["scene"] = {"type": "whiteboard", "props": sanitize(made["props"])}
                boards += 1
                warnings.append(f"beat {i}: {sc.get('type')} written on the board")
                continue
            except (ValueError, TypeError):
                pass
        other += 1
    plan["whiteboard"].update(boards=boards, other_scenes=other)
    if other:
        warnings.append(f"whiteboard video: {other} beat(s) kept another scene type")
    return warnings
