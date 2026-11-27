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
            '    {"id": "...", "chart": "bars|line", "values": [2 to 6 numbers], "labels": ["<short>", ...], "zone": "<zone>", "say": "<one word>"}   (numbers compared or growing: drawn by hand, never a real chart scene)\n'
            "  Zones: top-left, top, top-right, left, centre, right, bottom-left, bottom, bottom-right (one drawing per zone; a label goes `near` its drawing). A title or a list may use a wide zone: top-row, left-wide, right-wide, bottom-row.\n"
            "  Rules:\n"
            "  * 4 to 8 items per beat: usually 2 or 3 drawings or written phrases, joined by arrows, plus one or two marks. Never an empty board, never more than 9 drawings and texts.\n"
            "  * `say` is the exact narration word at which the item is finished, in the order the narration says them: the sun is drawn as the narrator says \"sun\". Write the narration so that it NAMES what is drawn.\n"
            "  * Keep the pen busy 50 to 70 % of the time: about one item for every 5 or 6 words of narration. When the narration goes on for more than a few words with nothing new to draw, add an EMPHASIS item "
            "with its own `say` word: an arrow between two things, or a mark (underline, circle, box, tick) on something already there. A board whose pen rests for seconds looks dead.\n"
            "  * Consecutive beats are panels of ONE big board: the camera travels from one to the next and ends on all of them. So each beat is a self-contained panel; do not repeat the previous panel's drawings.\n"
            "  * Writing is for titles, key terms, numbers and short formulas, never whole sentences. Numbers and results are WRITTEN big (size l or xl) and then circled or underlined; a comparison is two written numbers; "
            "a list is one `write` with a line per point (\"1. ...\\n2. ...\", at most 4 short lines) in a wide zone, size m, tool marker; the pen is only for small labels beside drawings. Markup: ^{2} for a power, _{2} for a subscript, \\frac{a}{b}, -> for an arrow.\n"
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
FILL_EVERY_WORDS = 8       # a stretch of narration this long with nothing drawn gets an emphasis mark (phase 1a: boards looked dead without them)


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


def keep_busy(props: Dict[str, Any], narration: str, max_items: int = 16) -> int:
    """The cheap pacing check: where the narration runs for FILL_EVERY_WORDS words or more with nothing tied to it, an emphasis mark (underline, circle, box,
    tick, in turn) is added on the last unmarked thing drawn before the gap, tied to a word in the middle of the gap. Deterministic, no model. Call after
    `retie`. -> marks added."""
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
    kinds = ("underline", "circle", "tick", "box", "double_underline")
    known = [(k, i) for i, k in enumerate(pos) if k is not None]
    if not known:
        return 0
    bounds = known + [(len(words), None)]
    inserts: List[Any] = []                                   # (item index to insert after, order, mark)
    for (ka, ia), (kb, _) in zip(bounds, bounds[1:]):
        gap = kb - ka - 1
        for j in range(min(2, gap // FILL_EVERY_WORDS)):
            if len(items) + len(inserts) >= max_items:
                break
            aim = ka + (gap + 1) * (j + 1) / (min(2, gap // FILL_EVERY_WORDS) + 1)
            ok = [q for q in range(ka + 1, kb) if words[q] and words[q] not in words[ka + 1:q] and all(q != m[3] for m in inserts)]
            ok = [q for q in ok if not any(m[0] == ia and m[3] >= q for m in inserts)]
            before = [i for i in range(ia + 1) if (items[i].get("draw") or items[i].get("write") or items[i].get("chart")) and items[i]["id"] not in marked]
            if not ok or not before:
                break
            q = min(ok, key=lambda q_: abs(q_ - aim))
            target = items[before[-1]]
            marked.add(target["id"])
            kind = kinds[len(inserts) % len(kinds)]
            if not target.get("write") and kind in ("underline", "double_underline"):
                kind = "circle"
            if target.get("write") and "\n" in target["write"] and kind == "circle":
                kind = "box"
            inserts.append((ia, len(inserts), {"id": f"em{len(inserts)}_{target['id']}"[:24], "mark": kind, "on": target["id"], "color": "red" if len(inserts) % 2 == 0 else "blue", "say": words[q]}, q))
    for ia, _, m, _q in sorted(inserts, key=lambda x: (-x[0], -x[1])):
        items.insert(ia + 1, m)
    return len(inserts)


def link(scenes: List[Dict[str, Any]]) -> int:
    """Timeline step (engine/timeline.py): consecutive `whiteboard` scenes become panels of ONE big board. Each later panel learns the one before it (the camera
    travels from it; the renderer's crossfade is switched off between them), the last one learns them all (the final pull-back). Also stamps the library version
    into the props, so a rebuilt library changes the segment hash. Pure; -> how many scenes were linked."""
    from .whiteboard import library

    built = str(library.index().get("built") or "")

    def lite(p: Dict[str, Any]) -> Dict[str, Any]:
        return {"items": p.get("items") or [], **{f: p[f] for f in ("hand", "tool") if f in p}}

    def close(run: List[Dict[str, Any]]) -> int:
        n = len(run)
        for k, sc in enumerate(run):
            p = sc["props"] = {k_: v for k_, v in sc["props"].items() if k_ not in ("prev", "wall", "panel")}
            p["lib"] = built
            if n > 1:
                p["panel"] = [k, n]
            if k > 0:
                p["prev"] = lite(run[k - 1]["props"])
                sc["transition"] = "none"
        if n > 1:
            run[-1]["props"]["wall"] = [lite(s["props"]) for s in run[:-1]][-8:]
        return n if n > 1 else 0

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
    for b in plan.get("beats") or []:
        sc = b.get("scene") or {}
        if sc.get("type") != "whiteboard" or not isinstance(sc.get("props"), dict):
            continue
        for k, v in retie(sc["props"], str(b.get("narration") or "")).items():
            tot[k] += v
        tot["marks_added"] += keep_busy(sc["props"], str(b.get("narration") or ""))
    plan.setdefault("whiteboard", policy.summary()).update(tot)
    return [f"whiteboard: {tot['retied']} tie(s) moved to words still said, {tot['untied']} dropped, {tot['marks_added']} emphasis mark(s) added"] if any(tot.values()) else []


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
