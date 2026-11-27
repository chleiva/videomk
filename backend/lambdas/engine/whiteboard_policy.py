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
from typing import Any, Callable, Dict, List, Optional, Tuple

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


# Drawings made on demand (docs/LIBRARY_ON_DEMAND.md part B). The director is normally told to draw ONLY from the list, so it never asks for a drawing the
# library lacks (it picks a stand-in from the list: a house for a beehive) and nothing could ever be made on demand. When the plan step knows that THIS video may
# have drawings made (the flag, the switches, an entitled account, a tracer), it allows a few new names here; object_ondemand.fill makes them and
# object_ondemand.settle writes the name of any that could not be made. 0 (the default, and always without the flag): the prompt is byte for byte what it was.
_new_drawings = 0
_NEW_LINE = ("  * Use drawing ids from the list whenever one really shows the thing. When a KEY OBJECT of the topic is not in the list, do NOT use a different drawing as a "
             "stand-in (never a house for a beehive): give `draw` the object's own plain name instead, one or two lowercase English words (\"honeycomb\", \"beehive\"). "
             "At most {n} such new names in the whole video, each a simple physical everyday object; it is drawn when it can be made, otherwise its name is written. Never a new "
             "name for a person, a brand, a flag, a map, a symbol, a weapon, anything medical, or text; for an idea that is not an object, WRITE the word instead.\n")


def allow_new_drawings(n: int) -> None:
    """How many drawings that are not in the list the director may name in the next plan (the plan step sets it for every video; 0 = none, the list only)."""
    global _new_drawings
    _new_drawings = max(0, min(6, int(n or 0)))


class Policy:
    def __init__(self, allowed: bool, reason: str, *, asked: bool = False, flag: bool = True, judged: Optional[Dict[str, Any]] = None, aspect: str = "16:9"):
        self.allowed, self.reason, self.asked, self.flag, self.judged = allowed, reason, asked, flag, judged
        self.aspect = aspect if aspect in ("16:9", "9:16", "1:1", "4:5") else "16:9"

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
        tall = self.aspect in ("9:16", "4:5")
        shape = ("  THIS VIDEO IS TALL (" + self.aspect + "): the board is narrow. Titles and lists go in a full-width zone (top-row, middle-row, bottom-row); every written text is 1 to 3 words per line; "
                 "arrange the flow from top to bottom (top row, then middle, then bottom), not left to right.\n") if tall else \
                ("  The board is wide: arrange the flow from left to right, the title on top, results and numbers along the bottom.\n" if self.aspect == "16:9" else "")
        return (
            "\n\nWHITEBOARD VIDEO. This whole video is a whiteboard explainer: EVERY beat's scene is of type `whiteboard` (no other scene type, no photographs, no clips, no charts).\n"
            "- whiteboard: {board: \"new\"|\"same\", items: [...]}. A board that a marker draws and writes on while the narrator speaks. You give MEANING, never coordinates.\n"
            "  BOARDS. A board is ONE full picture, like a teacher's finished whiteboard: by the time it is left it holds 8 to 12 drawings and written phrases, joined by arrows, with marks on the key words, "
            "and it stays on screen for about 15 to 20 seconds. One beat cannot fill a board, so TWO consecutive beats share a board (three when they are short): the first has \"board\": \"new\", the next has "
            "\"board\": \"same\" and goes on drawing in the zones the first one left free. Plan each board as a whole BEFORE writing its beats: its title, what the first beat puts where, what the second adds. "
            "A video of N beats has about N/2 boards; never one sparse board per beat. The camera shows a board whole and still, moves only to go to the next board, and ends the video on all boards together: "
            "every board must read as a finished, composed picture.\n"
            "  Items, in the order they are drawn:\n"
            '    {"id": "<short name>", "draw": "<a drawing id from the list below>", "zone": "<zone>", "say": "<ONE word of this beat\'s narration>", "size": "m|l"}\n'
            '    {"id": "...", "write": "<1 to 4 words, a number, or a short formula>", "zone": "<zone>" (or "near": "<id>", "side": "below|above|left|right"), "say": "<one word>", "size": "s|m|l|xl", "tool": "marker|pen", "ink": "black|blue|red|orange|green"}\n'
            '    {"id": "...", "connect": "arrow|wavy|dashed", "from": "<id>", "to": "<id>", "color": "blue|red|orange|green|grey", "say": "<one word>"}\n'
            '    {"id": "...", "mark": "underline|double_underline|circle|box|tick|cross|highlight", "on": "<id>", "color": "red|blue|green|orange", "say": "<one word>"}\n'
            '    {"id": "...", "chart": "bars|line", "values": [2 to 5 numbers], "labels": ["<short>", ...], "zone": "<zone>", "say": "<one word>"}   (numbers compared or growing: drawn by hand, never a real chart scene)\n'
            "  Zones: a 3x3 grid: top-left, top, top-right, left, centre, right, bottom-left, bottom, bottom-right. ONE drawing or text per zone for the WHOLE board (all its beats together); a label goes `near` "
            "its drawing and needs no zone. Wide zones for a title, a list or a chart: top-row, middle-row, bottom-row (the full width), top-left-wide, top-right-wide, left-wide, right-wide, bottom-left-wide, "
            "bottom-right-wide (two zones). `from`, `to`, `on` and `near` name items of the SAME beat.\n"
            + shape +
            "  Rules:\n"
            "  * FILL THE BOARD. Each beat has 7 to 10 items: 4 or 5 drawings or written phrases (never fewer than 3), each drawing with a short written label `near` it (1 to 3 words, tool pen) unless the "
            "narration makes it obvious, joined by arrows, plus 1 or 2 marks. By the end of a board at least 7 of its 9 zones are used, the left and the right side and the top and the bottom row among them. "
            "Never an empty board; never more than 9 drawings and texts in one beat.\n"
            "  * EVERY KEY NOUN of the narration is on the board: DRAWN when the list has it, otherwise WRITTEN. Numbers, names of steps and technical terms are written.\n"
            "  * `say` is the exact narration word at which the item is finished, in the order the narration says them: the sun is drawn as the narrator says \"sun\". Write the narration so that it NAMES what is drawn.\n"
            "  * PACING. Keep the pen busy: one item finishes about every 3 or 4 words of narration, and never more than 5 words pass with nothing finishing. The pen needs time BEFORE the word an item "
            "is tied to: about 4 words for a drawing, a title or a chart, 1 or 2 words for an arrow, a mark or a small label. So the first item of a beat is tied to its 4th to 6th word (the pen is already "
            "moving while the first words are said), a drawing's `say` word comes at least 3 words after the previous item's, and two items are never tied to the same or to neighbouring words. "
            "Arrows and marks have their own `say` word: an arrow on the verb that links two things (\"heats\", \"becomes\", \"earns\"), an underline, circle, box or tick on the word that stresses "
            "something already on the board. One mark per item at most (never an underline AND a box on the same word); a circle or box needs free space round its item, "
            "so circle a thing that stands alone, underline a label that sits beside a drawing. An arrow joins two things with free space between them: "
            "neighbours, never across a third thing. A board whose pen rests for more than a second looks dead.\n"
            "  * Arrows join NEIGHBOURS (items in adjacent zones); an arrow never has to cross a third item.\n"
            "  * Writing is for titles, key terms, numbers and short formulas, never whole sentences. A board's title is written large (size l) in the top row by its first beat. Numbers and results are WRITTEN "
            "big (size l or xl) and then circled or underlined; a comparison is two written numbers; a list is one `write` with a line per point (\"1. ...\\n2. ...\", at most 4 lines of 1 to 3 words) in a "
            "wide zone, size m, tool marker; the pen is only for the small labels beside drawings. Markup: ^{2} for a power, _{2} for a subscript, \\frac{a}{b}, -> for an arrow.\n"
            "  * Drawings are size l (m when two share a zone's row with labels); they are the pictures of the board, not icons.\n"
            + (_NEW_LINE.format(n=_new_drawings) if _new_drawings > 0 else
               "  * Use ONLY drawing ids from the list. If nothing in the list shows the idea, WRITE the word instead (a written label is always fine); never invent an id.\n") +
            "  * People are the simple figures of the list (person_*, doctor, teacher...); never a real, named person.\n"
            "  * The first beat opens the first board with the video's question or title written large on top and the first drawings. The LAST beat stays on the last board (\"board\": \"same\") and sums up "
            "there: the key term or takeaway written large in a free zone, underlined twice.\n"
            f"  Drawing ids, by group:\n{menu}"
        )


def decide(prompt: str, *, options: Optional[Dict[str, Any]] = None, skill_ids: Optional[List[str]] = None, photos: Optional[List[Any]] = None, research_mode: str = "encyclopedia",
           ask: Optional[Callable[[str, str], str]] = None, presenter_asked: bool = False) -> Policy:
    """Is this video a whiteboard video? Cheap rules first; one small-model call only for `auto` on a kind of video that could suit it."""
    o = options or {}
    w = wish(o.get("style"), prompt)
    flag = enabled()

    def no(reason: str) -> Policy:
        return Policy(False, reason, asked=w == STYLE, flag=flag, aspect=o.get("aspect"))

    if not flag:
        return no("flag_off")
    if w == "no":
        return no("other_style")
    if photos:
        return no("user_media")
    if o.get("deck"):
        return no("deck")
    if w == STYLE:
        return Policy(True, "asked", asked=True, aspect=o.get("aspect"))
    if research_mode == "web":
        return no("current_events")
    if presenter_asked:                     # "explained by a fox": the person asked for a presenter character, which a whiteboard video never has (seen on QA: the look chosen by itself silently dropped the fox)
        return no("presenter_asked")
    ids = set(skill_ids or [])
    if ids & NEVER_SKILLS or not ids & AUTO_SKILLS:
        return no("kind_of_video")
    if ask is None:
        return no("no_classifier")
    judged = _classify(prompt, ask)
    if not judged["fit"]:
        return Policy(False, "not_suited", judged=judged, aspect=o.get("aspect"))
    return Policy(True, "auto", judged=judged, aspect=o.get("aspect"))


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
                [{"id": "list", "write": "\n".join(f"{i + 1}. {x}" for i, x in enumerate(lines)), "zone": "left-wide", "size": "m"}]
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


THEME = "paper"            # captions and the closing card of a whiteboard video are light, like the board
FILL_EVERY_WORDS = 5       # a stretch of narration this long with nothing drawn (about 2 s) gets an emphasis mark: no dead air over about 1.5 s (it was 8: the first QA videos rested up to 2.5 s)
FILL_PER_GAP = 3           # at most this many marks in one stretch
# A board (one full picture) is shared by consecutive beats (`compose`): how much it may hold, and when it is full enough to be left
BOARD_MAX_BEATS, BOARD_MAX_SOLID, BOARD_MAX_WORDS = 3, 12, 66
BOARD_FULL_SOLID, BOARD_FULL_WORDS = 8, 40


def _words(narration: str) -> List[str]:
    """The narration as the engine's alignment will match it (engine/sync.py): one normalised token per spoken word, "" for a word that cannot carry a tie."""
    from . import sync

    out = []
    for raw in str(narration or "").split():
        toks = sync.content_tokens(raw)
        out.append(toks[0] if len(toks) == 1 else "")
    return out


def _say_token(it: Dict[str, Any]) -> str:
    from . import sync

    toks = sync.content_tokens(str(it.get("say") or ""))
    return toks[-1] if toks else ""


def _targets(it: Dict[str, Any]) -> List[str]:
    return [str(it[f]) for f in ("from", "to", "on", "near") if it.get(f)]


def retie(props: Dict[str, Any], narration: str) -> Dict[str, int]:
    """Makes a board agree with the narration AS IT IS NOW (the script is shortened and corrected after the boards are written). Deterministic, no model:
      * things are drawn in the order the narrator names them (an arrow or a mark never before what it points at);
      * a tie to a word the narration no longer says, or says out of order, moves to a word at the same relative place between its neighbours' words.
    -> {"moved": items reordered, "retied": ties changed, "untied": ties dropped}."""
    items: List[Dict[str, Any]] = props.get("items") or []
    words = _words(narration)
    stats = {"moved": 0, "retied": 0, "untied": 0}
    if not items or not any(words):
        return stats
    first: Dict[str, int] = {}
    for i, w in enumerate(words):
        if w:
            first.setdefault(w, i)
    # 1. the order the narrator names things in; an untied item stays behind the one it followed
    want = [first.get(_say_token(it)) if it.get("say") else None for it in items]
    key, last = [], -1.0
    for k, w in enumerate(want):
        last = float(w) if w is not None else last + 1e-3
        key.append(last)
    order = sorted(range(len(items)), key=lambda k: (key[k], k))
    placed: List[int] = []
    waiting = list(order)
    while waiting:                                            # ... but never before what it points at
        ids = {items[k]["id"] for k in placed}
        k = next((k for k in waiting if all(t in ids for t in _targets(items[k]))), waiting[0])
        placed.append(k)
        waiting.remove(k)
    stats["moved"] = sum(1 for a_, b_ in zip(placed, range(len(items))) if a_ != b_)
    items[:] = [items[k] for k in placed]
    # 2. ties in order: each on the first saying of its word after the previous tie
    pos: List[Optional[int]] = []
    prev = -1
    for it in items:
        if not it.get("say"):
            pos.append(None)
            continue
        tok = _say_token(it)
        k = next((i for i in range(prev + 1, len(words)) if words[i] == tok), None) if tok else None
        pos.append(k)
        if k is not None:
            prev = k
    # 3. a lost tie moves to a word at the same relative place between its neighbours
    taken = {k for k in pos if k is not None}
    for i, it in enumerate(items):
        if not it.get("say") or pos[i] is not None:
            continue
        lo = max((pos[j] for j in range(i) if pos[j] is not None), default=-1)
        hi = min((pos[j] for j in range(i + 1, len(items)) if pos[j] is not None), default=len(words))
        lost = [j for j in range(len(items)) if items[j].get("say") and pos[j] is None and all(pos[m] is None for m in range(min(i, j), max(i, j) + 1) if items[m].get("say"))]
        rank = lost.index(i) + 1
        aim = lo + (hi - lo) * rank / (len(lost) + 1)
        ok = [q for q in range(lo + 1, hi) if words[q] and q not in taken and words[q] not in words[lo + 1:q]]
        ok = [q for q in ok if all(pos[j] is None or pos[j] < q for j in range(i)) ]
        if ok:
            q = min(ok, key=lambda q_: abs(q_ - aim))
            it["say"] = words[q]
            pos[i] = q
            taken.add(q)
            stats["retied"] += 1
        else:
            it.pop("say", None)
            stats["untied"] += 1
    # a tie moved between neighbours may now sit before an earlier lost one: keep ties strictly increasing in list order
    prev = -1
    for i, it in enumerate(items):
        if pos[i] is None:
            continue
        if pos[i] <= prev:
            it.pop("say", None)
            stats["untied"] += 1
        else:
            prev = pos[i]
    return stats


def keep_busy(props: Dict[str, Any], narration: str, max_items: int = 20) -> int:
    """The cheap pacing check: where the narration runs for FILL_EVERY_WORDS words or more with nothing tied to it, an emphasis mark (underline, circle, box,
    tick, in turn) is added on the last unmarked thing drawn before the gap, tied to a word in the middle of the gap. A thing has at most ONE emphasis mark
    (an underline and a box on the same word piled up on the first Portuguese video): when everything drawn so far is marked, nothing is added and the pen
    rests. Whether the mark has room is the layout's business (engine/whiteboard/spec.py fits it, turns it into an underline or leaves it out).
    Deterministic, no model. Call after `retie`. -> marks added."""
    items: List[Dict[str, Any]] = props.get("items") or []
    words = _words(narration)
    if len(words) < FILL_EVERY_WORDS or not items:
        return 0
    pos: List[Optional[int]] = []
    prev = -1
    for it in items:
        tok = _say_token(it) if it.get("say") else ""
        k = next((i for i in range(prev + 1, len(words)) if words[i] == tok), None) if tok else None
        pos.append(k)
        prev = k if k is not None else prev
    marked = {it.get("on") for it in items if it.get("mark")}
    twice: set = set()
    has = {(it.get("on"), it.get("mark")) for it in items if it.get("mark")}
    kinds = ("underline", "circle", "tick", "box", "double_underline")
    known = [(k, i) for i, k in enumerate(pos) if k is not None]
    if not known:
        return 0
    bounds = known + [(len(words), None)]
    inserts: List[Any] = []                                   # (item index to insert after, order, mark)
    for (ka, ia), (kb, _) in zip(bounds, bounds[1:]):
        gap = kb - ka - 1
        for j in range(min(FILL_PER_GAP, gap // FILL_EVERY_WORDS)):
            if len(items) + len(inserts) >= max_items:
                break
            aim = ka + (gap + 1) * (j + 1) / (min(FILL_PER_GAP, gap // FILL_EVERY_WORDS) + 1)
            ok = [q for q in range(ka + 1, kb) if words[q] and words[q] not in words[ka + 1:q] and all(q != m[3] for m in inserts)]
            ok = [q for q in ok if not any(m[0] == ia and m[3] >= q for m in inserts)]
            drawn = [i for i in range(ia + 1) if items[i].get("draw") or items[i].get("write") or items[i].get("chart")]
            before = [i for i in drawn if items[i]["id"] not in marked]
            if not ok or not before:
                break
            q = min(ok, key=lambda q_: abs(q_ - aim))
            target = items[before[-1]]
            if target["id"] in marked:
                twice.add(target["id"])
            marked.add(target["id"])
            kind = kinds[len(inserts) % len(kinds)]
            if not target.get("write") and kind in ("underline", "double_underline"):
                kind = "circle"
            if target.get("write") and "\n" in target["write"] and kind == "circle":
                kind = "box"
            if (target["id"], kind) in has or (target["id"] in twice and kind in ("circle", "box") and has & {(target["id"], "circle"), (target["id"], "box")}):
                kind = next((k_ for k_ in ("tick", "underline" if target.get("write") else "box", "box", "circle") if (target["id"], k_) not in has), "tick")
            has.add((target["id"], kind))
            inserts.append((ia, len(inserts), {"id": f"em{len(inserts)}_{target['id']}"[:24], "mark": kind, "on": target["id"], "color": "red" if len(inserts) % 2 == 0 else "blue", "say": words[q]}, q))
    for ia, _, m, _q in sorted(inserts, key=lambda x: (-x[0], -x[1])):
        items.insert(ia + 1, m)
    return len(inserts)


def _solid(it: Dict[str, Any]) -> bool:
    return bool(it.get("draw") or it.get("write") or it.get("chart"))


def _cells(zone: str) -> List[Any]:
    from .whiteboard import spec

    names = spec.SPANS.get(zone, zone)
    cs = [spec.ZONES[n] for n in ([names] if isinstance(names, str) else names)]
    c0, r0, c1, r1 = min(c[0] for c in cs), min(c[1] for c in cs), max(c[0] for c in cs), max(c[1] for c in cs)
    return [(c, r) for c in range(c0, c1 + 1) for r in range(r0, r1 + 1)]


def free_zones(props_list: List[Dict[str, Any]]) -> List[str]:
    """The single zones no drawing, text or chart of this board has been given."""
    from .scenes.elements import whiteboard as wbe

    used = {c for p in props_list for it in p.get("items") or [] if it.get("zone") and not it.get("near") for c in _cells(it["zone"])}
    return [z for z in wbe.ZONES if _cells(z)[0] not in used]


def _place(p: Dict[str, Any], used: Dict[Any, int], dry: bool = False) -> Tuple[Dict[Any, int], int, int]:
    """One beat's drawings, texts and charts on a board whose cells `used` are taken: a thing whose zone is taken moves to a free zone of the same shape, else
    to a free single zone. -> (cells this beat takes, things moved, things that found no free zone). `dry`: only count, change nothing."""
    from .scenes.elements import whiteboard as wbe

    mine: Dict[Any, int] = {}
    other: Dict[Any, int] = {}               # cells a text or chart of this beat has (a drawing never shares those)
    moved = stuck = 0
    for it in p.get("items") or []:
        if not _solid(it) or it.get("near") or not it.get("zone"):
            continue
        cells = _cells(it["zone"])
        clash = any(used.get(c) for c in cells) or any(other.get(c) for c in cells) or (not it.get("draw") and any(mine.get(c) for c in cells))
        if clash:
            shape = (max(c[0] for c in cells) - min(c[0] for c in cells), max(c[1] for c in cells) - min(c[1] for c in cells))
            cx, cy = sum(c[0] for c in cells) / len(cells), sum(c[1] for c in cells) / len(cells)
            best = None
            for z in wbe.ZONES + wbe.SPANS:
                zc = _cells(z)
                if any(used.get(c) or mine.get(c) for c in zc):
                    continue
                same = (max(c[0] for c in zc) - min(c[0] for c in zc), max(c[1] for c in zc) - min(c[1] for c in zc)) == shape
                if not same and len(zc) > 1:
                    continue
                d = abs(sum(c[0] for c in zc) / len(zc) - cx) + abs(sum(c[1] for c in zc) / len(zc) - cy)
                key = (0 if same else 1, d)
                if best is None or key < best[0]:
                    best = (key, z, zc)
            if best is not None:
                cells = best[2]
                moved += 1
                if not dry:
                    it["zone"] = best[1]
            else:
                stuck += 1
        for c in cells:
            mine[c] = mine.get(c, 0) + 1
            if not it.get("draw"):
                other[c] = 1
    return mine, moved, stuck


def _spoils(props_list: List[Dict[str, Any]], aspect: str, captions: bool) -> bool:
    """Would the LAST beat of this shared board, laid out as the renderer will, overlap something or leave the board? (A board that cannot be laid out: yes.)"""
    from .whiteboard import score

    try:
        d = score.defects(props_list, aspect, captions)
    except Exception:  # noqa: BLE001 - the beat then gets its own board, which the renderer can always show
        return True
    mine = f"{len(props_list) - 1}:"
    return any(str(a).startswith(mine) or str(c).startswith(mine) for a, c in d["overlaps"]) or any(str(j).startswith(mine) for j in d["off_board"])


def compose(beats: List[Dict[str, Any]], aspect: Optional[str] = None, captions: bool = True) -> Dict[str, int]:
    """Which beats share a BOARD, decided when the script is final. The director marks a beat that goes on drawing on the previous beat's board ("board": "same");
    the engine keeps that when the board has room (BOARD_MAX_*), and ALSO keeps a beat on the board when the director started a new one although the board
    is not full yet (fewer than BOARD_FULL_SOLID things or BOARD_FULL_WORDS words): sparse boards were the main flaw of the first videos. Then, on each
    board, a drawing, text or chart whose zone an earlier item of the board already has moves to a free zone of the same shape (or a free single zone).
    A free ZONE is not yet room: with `aspect` given the board is laid out as the renderer will (engine/whiteboard/score.defects), and a beat whose things
    would overlap what is there, or leave the board, in the zones left for it gets its own board with the zones its author gave it (`split`).
    Deterministic, no model. -> {"boards", "shared": beats that continue a board, "merged": of those, decided by the engine, "rezoned": items moved,
    "split": beats given their own board because they did not fit the shared one}."""
    stats = {"boards": 0, "shared": 0, "merged": 0, "rezoned": 0, "split": 0}
    cur: List[Dict[str, Any]] = []           # the props of the beats on the current board
    words = solid = 0
    used: Dict[Any, int] = {}
    prev_i = None
    for i, b in enumerate(beats):
        sc = b.get("scene") or {}
        if sc.get("type") != "whiteboard" or not isinstance(sc.get("props"), dict):
            cur, prev_i = [], None
            continue
        p = sc["props"]
        n_words = len(str(b.get("narration") or "").split())
        n_solid = sum(1 for it in p.get("items") or [] if _solid(it))
        room = bool(cur) and prev_i == i - 1 and len(cur) < BOARD_MAX_BEATS and solid + n_solid <= BOARD_MAX_SOLID and words + n_words <= BOARD_MAX_WORDS
        asked = p.get("board") == "same"
        thin = solid < BOARD_FULL_SOLID or words < BOARD_FULL_WORDS
        last = not any((x.get("scene") or {}).get("type") == "whiteboard" for x in beats[i + 1:])
        thin = thin or (last and n_solid < 4)                    # the closing beat sums up on the last board: it never opens a nearly empty one when there is room
        if room and (asked or thin):
            p["board"] = "same"
            stats["shared"] += 1
            stats["merged"] += 0 if asked else 1
        else:
            p.pop("board", None)
            cur, words, solid, used = [], 0, 0, {}
            stats["boards"] += 1
        # zones: one drawing or text per zone on the whole board (two drawings of the SAME beat may share one: they are laid side by side)
        placed = None
        if cur and p.get("board") == "same":
            zones0 = [(it, it.get("zone")) for it in p.get("items") or []]
            _, _, stuck = _place(p, used, dry=True)
            full = bool(stuck)                                    # no free zone left for what this beat adds: the board is full, whatever its counts say
            if not full:
                placed = _place(p, used)
                if aspect and _spoils(cur + [p], aspect, captions):       # the zones were free, the room was not (a list in a corner, a title squeezed into one zone)
                    full = True
                    stats["split"] += 1
                    for it, z in zones0:                          # on its own board it keeps the places its author gave it
                        if z is not None:
                            it["zone"] = z
            if full:
                placed = None
                p.pop("board", None)
                stats["shared"] -= 1
                stats["merged"] -= 0 if asked else 1
                cur, words, solid, used = [], 0, 0, {}
                stats["boards"] += 1
        mine, moved, stuck = placed if placed is not None else _place(p, used)
        stats["rezoned"] += moved
        for c, v in mine.items():
            used[c] = used.get(c, 0) + v
        cur.append(p)
        words += n_words
        solid += n_solid
        prev_i = i
    return stats


_SMALLER = {"xl": "l", "l": "m", "m": "s", "s": "xs"}


def untangle(props_list: List[Dict[str, Any]], aspect: str = "16:9", captions: bool = True) -> Dict[str, int]:
    """The last resort for ONE board (the props of the beats that share it) whose drawings, texts or charts still overlap or leave the board after everything
    else: it is never shown like that. Until the renderer's own layout (score.defects) finds nothing, one thing at a time, the later of two that overlap or
    the one that leaves the board: (1) it moves to a zone nothing on the board has (a text of several lines or words to a free wide zone first), at most
    twice; (2) it is made one size smaller, down to the smallest; (3) it is taken off the board with its label, arrows and marks (never a beat's last thing:
    then its partner goes, and a thing alone that still does not fit is given the whole board). Every step removes room for a clash and the steps are
    finite, so this ends. The narration is not touched. -> {"moved", "smaller", "dropped", "left": defects it could not undo (0 unless the layout fails)}."""
    from .scenes.elements import whiteboard as wbe
    from .whiteboard import score

    out = {"moved": 0, "smaller": 0, "dropped": 0, "left": 0}
    multi = len(props_list) > 1
    moves: Dict[str, int] = {}
    tried: Dict[str, set] = {}

    def find(name: str) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
        j, iid = (int(name.split(":", 1)[0]), name.split(":", 1)[1]) if multi and ":" in name else (0, name)
        return props_list[j], next((it for it in props_list[j].get("items") or [] if it.get("id") == iid), None)

    def drop(p: Dict[str, Any], iid: str) -> None:
        gone = {iid}
        while True:
            more = {it["id"] for it in p["items"] if it["id"] not in gone and (it.get("near") in gone or it.get("on") in gone or it.get("from") in gone or it.get("to") in gone)}
            if not more:
                break
            gone |= more
        p["items"] = [it for it in p["items"] if it["id"] not in gone]

    for _ in range(80):
        try:
            d = score.defects(props_list, aspect, captions)
        except Exception:  # noqa: BLE001 - a board that cannot be laid out is shown as a plain card by the renderer
            break
        out["left"] = len(d["overlaps"]) + len(d["off_board"])
        if not out["left"]:
            break
        pair = [d["off_board"][0]] if d["off_board"] else list(reversed(d["overlaps"][0]))       # the later thing first
        done = False
        for name in pair:                                                                         # gentle steps: move, then smaller
            p, it = find(name)
            if it is None:
                continue
            if it.get("zone") and not it.get("near") and moves.get(name, 0) < 2:
                taken = {c for q in props_list for o in q.get("items") or [] if o is not it and o.get("zone") and not o.get("near") for c in _cells(o["zone"])}
                wide = bool(it.get("write")) and ("\n" in it["write"] or len(it["write"]) > 12)
                order = (wbe.SPANS + wbe.ZONES) if wide else wbe.ZONES
                z = next((z for z in order if len(_cells(z)) <= (2 if wide else 1) and z != it["zone"] and z not in tried.get(name, set()) and not any(c in taken for c in _cells(z))), None)
                if z is not None:
                    tried.setdefault(name, set()).add(z)
                    moves[name] = moves.get(name, 0) + 1
                    it["zone"] = z
                    out["moved"] += 1
                    done = True
                    break
            size = it.get("size") or ("l" if it.get("draw") and not it.get("near") else "m")
            if size in _SMALLER and not it.get("chart"):
                it["size"] = _SMALLER[size]
                out["smaller"] += 1
                done = True
                break
        if done:
            continue
        for name in pair:                                                                         # then it goes
            p, it = find(name)
            if it is not None and sum(1 for o in p["items"] if _solid(o) and not o.get("near")) > 1 or (it is not None and it.get("near")):
                drop(p, it["id"])
                out["dropped"] += 1
                done = True
                break
        if done:
            continue
        p, it = find(pair[0])                                                                     # a thing alone on its beat that still does not fit
        if it is None or it.get("zone") == "full":
            break
        it.pop("near", None)
        it.pop("side", None)
        it["zone"] = "full"
        out["moved"] += 1
    else:
        return out
    try:
        d = score.defects(props_list, aspect, captions)
        out["left"] = len(d["overlaps"]) + len(d["off_board"])
    except Exception:  # noqa: BLE001
        pass
    return out


def make_safe(plan: Dict[str, Any], aspect: str = "16:9") -> Dict[str, Any]:
    """Every board of the plan whose things overlap or leave the board is made safe. A SHARED board first loses the last beat involved, which gets a board of
    its own (`split`: a fresh board is the room it lacked, and nothing is lost); a board that is one beat's, or whose first beat is the trouble, goes through
    `untangle`. -> the totals, and `boards`: the numbers (as scored before) of the boards changed."""
    from .whiteboard import score

    beats = plan.get("beats") or []
    captions = bool(plan.get("captions", True))
    tot: Dict[str, Any] = {"split": 0, "moved": 0, "smaller": 0, "dropped": 0, "left": 0, "boards": []}
    first_of = {g[0]: bi + 1 for bi, g in enumerate(score.boards_of(beats)) for _ in g}
    number = lambda g: max(n for i0, n in first_of.items() if i0 <= g[0])      # noqa: E731 - the board this group was part of when the plan was scored
    given_up: set = set()
    for _ in range(4 * max(1, len(beats))):
        changed = False
        for g in score.boards_of(beats):
            if g[0] in given_up:
                continue
            props_list = [beats[i]["scene"]["props"] for i in g]
            try:
                d = score.defects(props_list, aspect, captions)
            except Exception:  # noqa: BLE001 - shown as a plain card by the renderer
                continue
            names = [str(x) for pair in d["overlaps"] for x in pair] + [str(x) for x in d["off_board"]]
            if not names:
                continue
            if number(g) not in tot["boards"]:
                tot["boards"].append(number(g))
            j = max(int(n.split(":", 1)[0]) for n in names) if len(g) > 1 else 0
            if j >= 1:
                props_list[j].pop("board", None)
                tot["split"] += 1
            else:
                r = untangle(props_list, aspect, captions)
                for k in ("moved", "smaller", "dropped"):
                    tot[k] += r[k]
                if r["left"]:
                    tot["left"] += r["left"]
                    given_up.add(g[0])
            changed = True
            break
        if not changed:
            break
    return tot


def make_clean(plan: Dict[str, Any], aspect: str = "16:9") -> Dict[str, Any]:
    """No board ships with an emphasis mark or an arrow that touches something. The layout already guarantees it (engine/whiteboard/spec.py fits every mark
    and arrow to the real ink, and takes off what cannot be fitted), so this finds nothing; it is the plan's own last check, like `make_safe` for overlaps:
    whatever the renderer's layout still reports as a collision (score.defects) is taken out of the plan, with what pointed at it, until it reports none.
    -> {"removed": [item ids], "left": collisions it could not undo (0 unless the layout fails)}."""
    from .whiteboard import score

    beats = plan.get("beats") or []
    captions = bool(plan.get("captions", True))
    out: Dict[str, Any] = {"removed": [], "left": 0}
    for g in score.boards_of(beats):
        props_list = [beats[i]["scene"]["props"] for i in g]
        for _ in range(40):
            try:
                hits = score.defects(props_list, aspect, captions)["collisions"]
            except Exception:  # noqa: BLE001 - shown as a plain card by the renderer
                hits = []
            if not hits:
                break
            name = str(hits[0][0])
            j, iid = (int(name.split(":", 1)[0]), name.split(":", 1)[1]) if len(g) > 1 and ":" in name else (0, name)
            p = props_list[j]
            gone = {iid}
            while True:
                more = {it["id"] for it in p["items"] if it["id"] not in gone and not _solid(it) and (it.get("on") in gone or it.get("from") in gone or it.get("to") in gone)}
                if not more:
                    break
                gone |= more
            n0 = len(p["items"])
            p["items"] = [it for it in p["items"] if it["id"] not in gone or _solid(it)]
            if len(p["items"]) == n0:
                out["left"] += len(hits)
                break
            out["removed"] += sorted(gone)
    return out


_LARGER = {"xs": "s", "s": "m", "m": "l", "l": "xl"}


def fill_out(props_list: List[Dict[str, Any]], aspect: str = "16:9", captions: bool = True, target: Optional[float] = None) -> Dict[str, Any]:
    """A board that "looks empty" after the director's one rewrite (its drawings and writing cover less of the picture than the bar) is filled by what is
    already on it: one thing at a time, written texts first (a key term one size larger is the biggest gain), then drawings, each is made one size larger
    and KEPT only if the renderer's own layout then shows more of the picture covered, nothing overlapping or off the board, no text written smaller than
    before and no arrow or mark lost. Stops at the bar. Deterministic, no model, the narration and the ties untouched. -> {"larger": n, "coverage": [before, after]}."""
    from .whiteboard import score

    target = score.MIN_COVERAGE if target is None else target
    try:
        d = score.defects(props_list, aspect, captions)
    except Exception:  # noqa: BLE001
        return {"larger": 0, "coverage": [None, None]}
    out = {"larger": 0, "coverage": [d["coverage"], d["coverage"]]}
    if d["overlaps"] or d["off_board"]:
        return out
    things = [it for p in props_list for it in p.get("items") or [] if _solid(it) and not it.get("chart")]
    things.sort(key=lambda it: (0 if it.get("write") and not it.get("near") else 1 if it.get("draw") and not it.get("near") else 2))
    for _ in range(2):
        for it in things:
            if d["coverage"] >= target:
                return out
            had = it.get("size")
            cur = had or ("l" if it.get("draw") and not it.get("near") else ("xs" if it.get("draw") else "m"))
            if cur not in _LARGER:
                continue
            it["size"] = _LARGER[cur]
            try:
                t = score.defects(props_list, aspect, captions)
            except Exception:  # noqa: BLE001
                t = None
            if t and not t["overlaps"] and not t["off_board"] and not t["collisions"] and t["lost"] <= d["lost"] and t["coverage"] > d["coverage"] + 0.002 \
                    and all(v >= d["text_sizes"].get(k, 0.0) - 0.5 for k, v in t["text_sizes"].items()):
                d = t
                out["larger"] += 1
                out["coverage"][1] = t["coverage"]
            elif had is None:
                it.pop("size", None)
            else:
                it["size"] = had
    return out


def _renamed(items: List[Dict[str, Any]], j: int, ties: bool = True) -> List[Dict[str, Any]]:
    """The items of the j-th beat of a shared board under names that are unique on the board (every scene of the board uses the same names, so an item looks
    the same in all of them)."""
    out = []
    for it in items:
        o = {k: v for k, v in it.items() if ties or k != "say"}
        o["id"] = f"{j}:{it['id']}"
        for f in ("from", "to", "on", "near"):
            if o.get(f):
                o[f] = f"{j}:{o[f]}"
        out.append(o)
    return out


def _plain(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Items as the plan has them: without the board-wide names and the marks a previous `link` added (so linking twice gives the same result)."""
    out = []
    for it in items:
        if re.sub(r"^\d+:", "", str(it.get("id", ""))).startswith("+r"):
            continue
        o = dict(it)
        for f in ("id", "from", "to", "on", "near"):
            if isinstance(o.get(f), str):
                o[f] = re.sub(r"^\d+:", "", o[f])
        out.append(o)
    return out


def linked_props(props_list: List[Dict[str, Any]], sizes: List[int], ends: Optional[List[Optional[float]]] = None) -> List[Dict[str, Any]]:
    """The props of a run of consecutive whiteboard scenes, grouped into boards of `sizes` scenes each -> new props, one per scene, that know their board:
    `before` / `after` (what the other scenes of the board draw: already there, or still to come), `panel` [board, boards], `prev` (the board before, on the
    first scene of a board: the camera travels from it) and `wall` (every earlier board, on the very last scene: the final pull-back).
    `ends` (one per scene, with the scenes' `cues` in their props): the time each scene's pen may work until; given, the rests of the pen are filled with
    emphasis marks (`fill_rests`) BEFORE the boards are told about each other, so a mark is part of its board in every scene that shows it. Pure."""
    keep = lambda p: {**{k: v for k, v in p.items() if k not in ("prev", "wall", "panel", "before", "after")}, "items": _plain(p.get("items") or [])}      # noqa: E731
    style = lambda p: {f: p[f] for f in ("hand", "tool") if f in p}      # noqa: E731
    untied = lambda items: [{k: v for k, v in it.items() if k not in ("say", "at")} for it in items]      # noqa: E731
    boards: List[List[Dict[str, Any]]] = []
    k = 0
    for n in sizes:
        grp = [keep(p) for p in props_list[k:k + n]]
        for j, q in enumerate(grp):
            if len(grp) > 1:
                q["items"] = _renamed(q["items"], j)
            if ends is not None:
                seen = dict(q, before=[it for i in range(j) for it in untied(grp[i]["items"])])
                if fill_rests(seen, q.get("cues"), ends[k + j], tag=f"{j}." if len(grp) > 1 else ""):
                    q["items"] = seen["items"]
        boards.append(grp)
        k += n
    whole = [{"items": [it for q in grp for it in untied(q["items"])], **style(grp[0])} for grp in boards]      # each board finished, without ties
    out: List[Dict[str, Any]] = []
    for bi, grp in enumerate(boards):
        for j, q in enumerate(grp):
            if len(grp) > 1:
                q["before"] = [it for i in range(j) for it in untied(grp[i]["items"])]
                q["after"] = [it for i in range(j + 1, len(grp)) for it in untied(grp[i]["items"])]
            if len(boards) > 1:
                q["panel"] = [bi, len(boards)]
            if bi > 0 and j == 0:
                q["prev"] = whole[bi - 1]
            out.append(q)
    if len(boards) > 1 and out:
        out[-1]["wall"] = whole[:-1][-8:]
    return out


REST_S = 1.6               # the pen may rest this long between two things; a longer rest gets an emphasis mark (`fill_rests`)
COVER_S = {"draw": 2.2, "chart": 3.0, "write": 1.2, "connect": 0.9, "mark": 0.5}      # how long before its word the pen is already busy with a thing (a drawing is drawn slowly when there is time)
MAX_REST_MARKS = 3


def fill_rests(props: Dict[str, Any], cues: Optional[List[float]], end: Optional[float] = None, tag: str = "") -> int:
    """Pacing with the REAL word times (they exist only once the voice is made: the timeline's `link` calls this; the self-check calls it with estimated
    times). Wherever the pen would rest for more than REST_S between two tied things, at the start of a beat that continues a board, or between the last
    thing and the last word (`end`), an emphasis mark is added at a fixed time of the rest: a circle, underline, box or tick on something already on the
    board (this beat's or an earlier beat's of the same board) that has no mark yet: a thing has at most one emphasis mark, so when all are marked the pen
    rests. At most MAX_REST_MARKS a scene. Deterministic. -> marks added."""
    items: List[Dict[str, Any]] = list(props.get("items") or [])
    before = list(props.get("before") or [])
    if not cues or any("+r" in str(it.get("id", "")) for it in items):
        return 0
    kind_of = lambda it: next(k for k in ("draw", "chart", "write", "connect", "mark") if k in it)      # noqa: E731
    marked = {it.get("on") for it in before + items if it.get("mark")}
    tied = [(i, float(cues[k])) for k, (i, _) in enumerate([(i, it) for i, it in enumerate(items) if it.get("say")]) if k < len(cues)]
    if not tied:
        return 0
    spans = []                                    # (rest starts, rest ends, index in items to insert before)
    prev_t = 0.0 if before else None              # a new board's first thing is brought forward by the timeline; a continued board must not wait
    for i, t in tied:
        busy_from = t - COVER_S[kind_of(items[i])]
        if prev_t is not None and busy_from - prev_t > REST_S:
            spans.append((prev_t, busy_from, i))
        prev_t = t + 0.3
    if end is not None and end - prev_t > REST_S:
        spans.append((prev_t, end, len(items)))
    added: List[Any] = []
    kinds = ("circle", "underline", "box", "tick")
    for lo, hi, at_i in spans:
        n = min(2, int((hi - lo) / (REST_S + 0.6)) or 1)
        for k in range(n):
            if len(added) >= MAX_REST_MARKS:
                break
            drawn = [it for it in before + items[:at_i] if _solid(it)]
            pool = [it for it in drawn if it["id"] not in marked]
            if not pool:
                break
            target = pool[-1]
            if target["id"] in marked:
                kind = "tick"
                marked.add((target["id"], "tick"))
            else:
                kind = kinds[len(added) % 3] if target.get("write") else ("circle", "box")[len(added) % 2]
                if kind == "circle" and target.get("write") and "\n" in target["write"]:
                    kind = "box"
            marked.add(target["id"])
            at = lo + (hi - lo) * (k + 0.5) / n
            added.append((at_i, {"id": f"+r{tag}{len(added)}", "mark": kind, "on": target["id"], "color": ("blue", "red", "green")[len(added) % 3], "at": round(max(0.4, at), 2)}))
    for at_i, m in sorted(added, key=lambda x: -x[0]):
        items.insert(at_i, m)
    if added:
        props["items"] = items
    return len(added)


def link(scenes: List[Dict[str, Any]]) -> int:
    """Timeline step (engine/timeline.py): consecutive `whiteboard` scenes become ONE big board of panels. Scenes whose props say "board": "same" share a
    panel with the scene before (they go on drawing on it; the picture does not move or fade between them); the first scene of a later panel learns the panel
    before it (the camera travels from it), the last scene learns them all (the final pull-back). Also stamps the library version into the props, so a
    rebuilt library changes the segment hash. Pure; -> how many scenes were linked."""
    from .whiteboard import library

    built = str(library.index().get("built") or "")

    def close(run: List[Dict[str, Any]]) -> int:
        if not run:
            return 0
        from .scenes.elements import whiteboard as wbe

        sizes: List[int] = []
        for k, sc in enumerate(run):
            if k and sc["props"].get("board") == "same":
                sizes[-1] += 1
            else:
                sizes.append(1)
        ends: List[Optional[float]] = []
        for k, sc in enumerate(run):
            dur = float(sc.get("duration") or 0.0)                  # the breath after the last word belongs to the scene: the pen does not stop there either
            tail = wbe._tail({"wall": [1] * (len(sizes) - 1)}, dur) if k == len(run) - 1 and len(sizes) > 1 else 0.0
            ends.append(dur - tail - 0.5 if dur else None)
        for k, (sc, p) in enumerate(zip(run, linked_props([sc["props"] for sc in run], sizes, ends))):
            p["lib"] = built
            sc["props"] = p
            if k > 0:
                sc["transition"] = "none"
        return len(run) if len(run) > 1 else 0

    linked, run = 0, []
    for sc in scenes:
        if sc.get("type") == "whiteboard" and isinstance(sc.get("props"), dict):
            run.append(sc)
        else:
            linked += close(run)
            run = []
    return linked + close(run)


def settle(plan: Dict[str, Any], policy: Optional[Policy]) -> List[str]:
    """The LAST step of the director, when the narration is final (shortened to the length, corrected against the sources): every board is tied again to the
    words that are really said (`retie`) and gets emphasis marks where its pen would rest (`keep_busy`). Records the counts in plan["whiteboard"]."""
    if policy is None or not policy.allowed:
        return []
    tot = {"moved": 0, "retied": 0, "untied": 0, "marks_added": 0}
    boards = compose(plan.get("beats") or [], policy.aspect, bool(plan.get("captions", True)))
    for b in plan.get("beats") or []:
        sc = b.get("scene") or {}
        if sc.get("type") != "whiteboard" or not isinstance(sc.get("props"), dict):
            continue
        for k, v in retie(sc["props"], str(b.get("narration") or "")).items():
            tot[k] += v
        tot["marks_added"] += keep_busy(sc["props"], str(b.get("narration") or ""))
    plan.setdefault("whiteboard", policy.summary()).update(tot, panels=boards["boards"], beats_sharing_a_board=boards["shared"], rezoned=boards["rezoned"], split_for_room=boards["split"])
    return [f"whiteboard: {boards['boards']} board(s) for {boards['boards'] + boards['shared']} beats ({boards['merged']} kept on a board by the engine, {boards['rezoned']} item(s) moved to a free zone, "
            f"{boards['split']} beat(s) given a board of their own for lack of room); "
            f"{tot['retied']} tie(s) moved to words still said, {tot['untied']} dropped, {tot['marks_added']} emphasis mark(s) added"]


REVIEW_SYSTEM = (
    "You repair the boards of a whiteboard explainer video. The narration is FINAL: never change, add or remove a spoken word. For each beat you are given, write its board again so that the complaints "
    "about its board are fixed, keeping everything that already works (the same ids where the item stays). "
    'Answer ONLY JSON: {"beats": [{"beat": <the beat number given>, "board": "new"|"same", "items": [...]}]} with exactly the beats given, in order. '
    "Every `say` must be a word that this beat's narration really says, and the items of a beat are in the order the narration says their words.")


def review(plan: Dict[str, Any], policy: Optional[Policy], ask: Optional[Callable[[str, str], str]], language: str = "en") -> List[str]:
    """The self-check (engine/whiteboard/score.py), after `settle`: every board is laid out and timed as the renderer will and scored. Boards that fail are
    sent back to the director ONCE with their complaints (the narration stays as it is); the new boards are kept only if the video then scores at least as
    well. The scores are logged (`WHITEBOARD_SCORE`) and kept in plan["whiteboard"]["score"]. Never fails a plan."""
    import copy
    import json

    if policy is None or not policy.allowed:
        return []
    from .whiteboard import score

    notes: List[str] = []
    try:
        beats = plan.get("beats") or []
        scores = score.score_plan(plan, policy.aspect)
        first = score.summary(scores)
        failed = [s for s in scores if not s["ok"]]
        info: Dict[str, Any] = {"first": first, "replanned": False}
        print("WHITEBOARD_SCORE " + json.dumps({"pass": 1, **first, "complaints": [c for s in failed for c in s["complaints"]][:12]}, ensure_ascii=False))
        if failed and ask is not None:
            want = sorted({i - 1 for s in failed for i in s["beats"]})
            parts = []
            for s in failed:
                parts.append(f"BOARD {s['board']} (beats {', '.join(str(i) for i in s['beats'])}). Complaints:\n" + "\n".join(f"- {c}" for c in s["complaints"]))
                for i in s["beats"]:
                    pr = beats[i - 1]["scene"]["props"]
                    parts.append(f"Beat {i}. Narration (final): {json.dumps(beats[i - 1].get('narration') or '', ensure_ascii=False)}\n"
                                 f"Its board now: {json.dumps({'board': pr.get('board', 'new'), 'items': pr.get('items')}, ensure_ascii=False)}")
            try:
                raw = ask(REVIEW_SYSTEM + policy.prompt_block(language), "\n\n".join(parts))
                data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
                from .scenes import ELEMENTS

                trial = copy.deepcopy(plan)
                done = 0
                for row in data.get("beats") or []:
                    i = int(row.get("beat", 0)) - 1
                    if i not in want or not isinstance(row.get("items"), list):
                        continue
                    try:
                        with scope(policy):
                            props = ELEMENTS["whiteboard"].sanitize({"items": row["items"], "board": row.get("board")})
                    except (ValueError, TypeError):
                        continue
                    old = trial["beats"][i]["scene"]["props"]
                    trial["beats"][i]["scene"]["props"] = {**props, **{f: old[f] for f in ("hand", "tool") if f in old and f not in props}}
                    done += 1
                if done:
                    compose(trial["beats"], policy.aspect, bool(plan.get("captions", True)))
                    for i in want:
                        b = trial["beats"][i]
                        retie(b["scene"]["props"], str(b.get("narration") or ""))
                        keep_busy(b["scene"]["props"], str(b.get("narration") or ""))
                    again = score.score_plan(trial, policy.aspect)
                    second = score.summary(again)
                    took = score.better(scores, again)
                    info.update(replanned=True, beats=[i + 1 for i in want], second=second, kept="new" if took else "first")
                    print("WHITEBOARD_SCORE " + json.dumps({"pass": 2, **second, "kept": info["kept"], "complaints": [c for s in again if not s["ok"] for c in s["complaints"]][:12]}, ensure_ascii=False))
                    if took:
                        # `compose` regrouped the trial AND moved things of beats that were not written again (a beat now sharing a rewritten board got
                        # free zones on it). The whole trial board is what was scored, so the whole of it is taken: taking only the flag put a beat on a
                        # board with the zones it had on its own one, on top of what was there (the first Polish video, 19 to 32 s).
                        for i, b in enumerate(beats):
                            if (b.get("scene") or {}).get("type") == "whiteboard" and (trial["beats"][i].get("scene") or {}).get("type") == "whiteboard":
                                b["scene"] = trial["beats"][i]["scene"]
                        scores = again
                    notes.append(f"whiteboard self-check: {len(failed)} board(s) failed, written again once; kept the {'new' if took else 'first'} boards ({second['failed']} failing now)")
            except Exception as e:  # noqa: BLE001 - the repair is a bonus: the first boards stand
                logging.warning("whiteboard review: repair failed (%s: %s)", type(e).__name__, str(e)[:200])
                info["error"] = f"{type(e).__name__}: {str(e)[:120]}"
        # Whatever happened above (no repair, a repair kept or thrown away, a repair that broke): a board whose things overlap or leave the board is never
        # shipped as it is. What is recorded below is the score of the boards that ship.
        if any(s.get("overlaps") or s.get("off_board") for s in scores):
            safe = make_safe(plan, policy.aspect)
            if safe["boards"]:
                scores = score.score_plan(plan, policy.aspect)
                info["made_safe"] = safe
                print("WHITEBOARD_SCORE " + json.dumps({"pass": "safe", **score.summary(scores), **{k: safe[k] for k in ("split", "moved", "smaller", "dropped", "left")}}, ensure_ascii=False))
                notes.append(f"whiteboard self-check: board(s) {', '.join(map(str, safe['boards']))} still had things overlapping or off the board: {safe['split']} beat(s) given a board of "
                             f"their own, {safe['moved']} thing(s) moved to a free zone, {safe['smaller']} made smaller, {safe['dropped']} taken off")
        # ... nor one on which a mark or an arrow touches something (the layout takes care of that; this is the plan's own check of it)
        if any(s.get("collisions") or s.get("crossed") for s in scores):
            clean = make_clean(plan, policy.aspect)
            scores = score.score_plan(plan, policy.aspect)
            info["made_clean"] = clean
            print("WHITEBOARD_SCORE " + json.dumps({"pass": "clean", **score.summary(scores), "removed": clean["removed"], "left": clean["left"]}, ensure_ascii=False))
            notes.append(f"whiteboard self-check: {len(clean['removed'])} mark(s) or arrow(s) that touched something taken off")
        # A board that still "looks empty" is filled by what is on it (larger writing and drawings, while the layout stays clean): no second model call
        groups = score.boards_of(beats)
        grown = []
        for s, g in zip(scores, groups):
            if any("looks empty" in c for c in s["complaints"]):
                r = fill_out([beats[i]["scene"]["props"] for i in g], policy.aspect, bool(plan.get("captions", True)))
                if r["larger"]:
                    grown.append({"board": s["board"], **r})
        if grown:
            scores = score.score_plan(plan, policy.aspect)
            info["filled_out"] = grown
            print("WHITEBOARD_SCORE " + json.dumps({"pass": "fill", **score.summary(scores), "boards": grown}, ensure_ascii=False))
            notes.append("whiteboard self-check: " + "; ".join(f"board {x['board']} looked empty, {x['larger']} thing(s) made larger ({x['coverage'][0] * 100:.0f} % -> {x['coverage'][1] * 100:.0f} % covered)" for x in grown))
        final = score.summary(scores)
        plan.setdefault("whiteboard", policy.summary())["score"] = {**final, **{k: v for k, v in info.items() if k != "first"}, "first": first,
                                                                    "boards_detail": [{k: v for k, v in s.items() if k not in ("overlaps", "crossed", "off_board", "late", "collisions", "blocked")} for s in scores]}
        if final["failed"]:
            notes.append(f"whiteboard self-check: {final['failed']} of {final['boards']} board(s) still below the bar: " + "; ".join(c for s in scores for c in s["complaints"])[:300])
    except Exception as e:  # noqa: BLE001
        logging.warning("whiteboard review failed (%s: %s)", type(e).__name__, str(e)[:200])
    return notes


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
    boards = other = labels = 0
    plan["theme"] = THEME
    for i, b in enumerate(plan.get("beats") or []):
        sc = b.get("scene") or {}
        if sc.get("type") == "whiteboard":
            boards += 1
            labels += sum(1 for it in sc["props"].get("items", []) if it.get("boxed"))
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
    plan["whiteboard"].update(boards=boards, other_scenes=other, written_instead_of_drawn=labels)
    if labels:
        warnings.append(f"whiteboard: {labels} drawing(s) not in the library, written as labels")
    if other:
        warnings.append(f"whiteboard video: {other} beat(s) kept another scene type")
    return warnings
