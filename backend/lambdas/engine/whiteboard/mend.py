"""Model-free repairs of the complaints the director used to be asked about (docs/WHITEBOARD_REVIEW_COST_2026-11-28.md).

Every move is a small edit of what the director wrote (a word tie one word earlier, a text one size larger, a label on another side of its drawing, one end of a
blocked arrow in another zone), tried on the real plan and scored with the renderer's own layout (`score.score_plan`). A move is KEPT only when the video then
scores strictly better (fewer complaints, no board that passed now failing, no board with a new kind of complaint). No thing is added, taken off or reworded,
the narration and the order of the words are untouched. Nothing is guessed: a move that does not help is undone. No model, no storage; about 0.05 to 0.3 s per
try, capped (MAX_TRIES, MAX_SECONDS).
"""
import time
from typing import Any, Dict, List, Optional, Tuple

MAX_TRIES = 40
MAX_SECONDS = 6.0
MENDS = ("late", "small", "gap", "arrow", "crossed")      # the kinds of complaint a move exists for
_SIDES = ("below", "above", "right", "left")
_LARGER = {"xs": "s", "s": "m", "m": "l", "l": "xl"}
_SIZES = ("xs", "s", "m", "l", "xl")


def _key(scores: List[Dict[str, Any]]) -> Tuple[int, int]:
    return (sum(1 for s in scores if not s["ok"]), sum(len(s["complaints"]) for s in scores))


def _improves(old: List[Dict[str, Any]], new: List[Dict[str, Any]]) -> bool:
    """Strictly fewer complaints, no more failing boards, no passing board now failing, and no board gets a kind of complaint it did not have."""
    if len(old) != len(new):
        return False
    ko, kn = _key(old), _key(new)
    if kn[0] > ko[0] or kn[1] >= ko[1]:
        return False
    for a, b in zip(old, new):
        if set(b["kinds"]) - set(a["kinds"]) or (a["ok"] and not b["ok"]):
            return False
    return True


def _find(plan: Dict[str, Any], score: Dict[str, Any], name: str) -> Tuple[Optional[Dict[str, Any]], Optional[int], Optional[Dict[str, Any]]]:
    """The item a board-wide name (`j:id`, or the plain id on a board of one beat) stands for -> (item, beat index, its props)."""
    beats = [i - 1 for i in score["beats"]]
    j, iid = (name.split(":", 1) if ":" in name else ("0", name))
    try:
        bi = beats[int(j)]
    except (ValueError, IndexError):
        return None, None, None
    props = plan["beats"][bi]["scene"]["props"]
    return next((it for it in props.get("items") or [] if it.get("id") == iid), None), bi, props


def _ties(props: Dict[str, Any], narration: str) -> List[Optional[int]]:
    from .. import whiteboard_policy as wp

    words = wp._words(narration)
    out: List[Optional[int]] = []
    prev = -1
    for it in props.get("items") or []:
        tok = wp._say_token(it) if it.get("say") else ""
        k = next((i for i in range(prev + 1, len(words)) if words[i] == tok), None) if tok else None
        out.append(k)
        if k is not None:
            prev = k
    return out


def _late_moves(plan: Dict[str, Any], score: Dict[str, Any]) -> List[Any]:
    """Each late item tied one word earlier, two, three... never before the word its predecessor is tied to (the order of the words stays the narration's)."""
    from .. import whiteboard_policy as wp

    moves = []
    for name, _d in score.get("late") or []:
        it, bi, props = _find(plan, score, name)
        if not it or not it.get("say"):
            continue
        narration = str(plan["beats"][bi].get("narration") or "")
        words = wp._words(narration)
        ties = _ties(props, narration)
        idx = props["items"].index(it)
        k = ties[idx]
        if k is None:
            continue
        floor = max([t for t in ties[:idx] if t is not None], default=-1) + 1
        for q in range(k - 1, max(floor, k - 6) - 1, -1):
            if words[q] and words[q] not in words[floor:q]:
                moves.append((it, "say", it["say"], words[q]))
    return moves


def _small_moves(plan: Dict[str, Any], score: Dict[str, Any]) -> List[Any]:
    """Every written text of the board one size larger, the smallest first."""
    texts = [it for i in score["beats"] for it in plan["beats"][i - 1]["scene"]["props"].get("items") or [] if it.get("write")]
    texts.sort(key=lambda it: _SIZES.index(it.get("size") or "m") if (it.get("size") or "m") in _SIZES else 2)
    return [(it, "size", it.get("size"), _LARGER[it.get("size") or "m"]) for it in texts if (it.get("size") or "m") in _LARGER]


def _gap_moves(plan: Dict[str, Any], score: Dict[str, Any]) -> List[Any]:
    """The label of a close pair on each other side of its own drawing or text."""
    moves = []
    for a, c, _g in score.get("close_texts") or []:
        for name in (a, c):
            it, _bi, _p = _find(plan, score, name)
            if it and it.get("near"):
                moves += [(it, "side", it.get("side"), side) for side in _SIDES if side != (it.get("side") or "below")]
    return moves


def _arrow_moves(plan: Dict[str, Any], score: Dict[str, Any]) -> List[Any]:
    """One end of a blocked or crossing arrow in each free zone, then swapped with each other single-zone drawing or text of the board."""
    from .. import whiteboard_policy as wp
    from ..scenes.elements import whiteboard as wbe

    moves = []
    names = list(score.get("crossed") or []) + [x for pair in score.get("arrow_cross") or [] for x in pair] + [x for x in score.get("blocked") or [] if x not in (score.get("arrows_readable") or [])]
    props_list = [plan["beats"][i - 1]["scene"]["props"] for i in score["beats"]]
    free = wp.free_zones(props_list)
    solid = [x for p in props_list for x in p.get("items") or [] if x.get("zone") in wbe.ZONES and not x.get("near") and wp._solid(x)]
    for name in names[:3]:
        arrow, _bi, props = _find(plan, score, name)
        if not arrow:
            continue
        for end in ("to", "from"):
            it = next((x for x in props.get("items") or [] if x.get("id") == arrow.get(end)), None)
            if not it or it.get("near") or it.get("zone") not in wbe.ZONES:
                continue
            moves += [(it, "zone", it["zone"], z) for z in free if z != it["zone"] and z in wbe.ZONES]
            moves += [(it, "swap", it["zone"], o) for o in solid if o is not it and o["zone"] != it["zone"]]
    return moves


def _apply(m: Tuple[Any, ...]) -> None:
    it, field, _old, new = m
    if field == "swap":
        it["zone"], new["zone"] = new["zone"], it["zone"]
    elif new is None:
        it.pop(field, None)
    else:
        it[field] = new


def _undo(m: Tuple[Any, ...]) -> None:
    it, field, old, new = m
    if field == "swap":
        it["zone"], new["zone"] = new["zone"], it["zone"]
    elif old is None:
        it.pop(field, None)
    else:
        it[field] = old


_GENS = (("late", _late_moves), ("small", _small_moves), ("gap", _gap_moves), ("arrow", _arrow_moves), ("crossed", _arrow_moves))


def mend(plan: Dict[str, Any], aspect: str, scores: List[Dict[str, Any]], kinds: Tuple[str, ...] = MENDS) -> Dict[str, Any]:
    """Try the moves above on every board that fails for a kind in `kinds`, one kept at a time, until nothing more helps.
    -> {"kept": [what was kept], "tries": n, "scores": the scores now}. The plan is changed in place (only by kept moves)."""
    from . import score as sc

    t0 = time.time()
    tries = 0
    kept: List[Dict[str, Any]] = []
    cur = scores
    progress = True
    while progress and tries < MAX_TRIES and time.time() - t0 < MAX_SECONDS:
        progress = False
        for s in cur:
            if s["ok"] or not set(s["kinds"]) & set(kinds):
                continue
            for kind, gen in _GENS:
                if kind not in s["kinds"] or kind not in kinds:
                    continue
                for m in gen(plan, s):
                    if tries >= MAX_TRIES or time.time() - t0 >= MAX_SECONDS:
                        break
                    tries += 1
                    _apply(m)
                    try:
                        new = sc.score_plan(plan, aspect)
                    except Exception:  # noqa: BLE001
                        new = None
                    if new is not None and _improves(cur, new):
                        kept.append({"board": s["board"], "kind": kind, "item": m[0].get("id"), "field": m[1], "from": m[2],
                                     "to": m[3].get("id") if m[1] == "swap" else m[3]})
                        cur = new
                        progress = True
                        break
                    _undo(m)
                if progress:
                    break
            if progress:
                break
    return {"kept": kept, "tries": tries, "scores": cur}


def fill_count(plan: Dict[str, Any], aspect: str, scores: List[Dict[str, Any]], max_add: int = 2) -> Dict[str, Any]:
    """OPTION (setting WB_MEND_COUNT, default OFF): a board short of its count of drawings and written phrases gets the longest words its own narration says, written
    in a free zone and tied to that word (the order of the items follows the narration), one at a time, each kept only if the video then scores strictly better.
    The scorer counts them; whether a rule-picked word reads as well as one the director chose is NOT something it can tell (see the document). -> {"kept": [...], "scores"}."""
    import re

    from .. import whiteboard_policy as wp
    from . import score as sc

    kept: List[Dict[str, Any]] = []
    cur = scores
    for s in list(cur):
        if s["ok"] or "count" not in s["kinds"]:
            continue
        for _ in range(max_add):
            s = next((x for x in cur if x["board"] == s["board"]), None)
            if not s or "count" not in s["kinds"]:
                break
            props_list = [plan["beats"][i - 1]["scene"]["props"] for i in s["beats"]]
            free = [z for z in wp.free_zones(props_list)]
            done = False
            for bi in [i - 1 for i in s["beats"]][::-1]:
                props = plan["beats"][bi]["scene"]["props"]
                narration = str(plan["beats"][bi].get("narration") or "")
                raw = [re.sub(r"[^\w'-]", "", w) for w in narration.split()]
                toks = wp._words(narration)
                used = {wp._say_token(it) for it in props["items"] if it.get("say")} | {it.get("write", "").lower() for it in props["items"] if it.get("write")}
                cands = sorted({k for k, w in enumerate(raw) if len(w) >= 6 and toks[k] and toks[k] not in used and toks[k] not in toks[:k]}, key=lambda k: -len(raw[k]))
                ties = _ties(props, narration)
                for k in cands[:4]:
                    for z in free[:4]:
                        before = sum(1 for t in ties if t is not None and t < k)
                        pos = next((i for i, t in enumerate(ties) if t is not None and t > k), len(props["items"]))
                        item = {"id": f"kw{k}", "write": raw[k], "zone": z, "size": "m", "say": toks[k]}
                        props["items"].insert(pos, item)
                        try:
                            new = sc.score_plan(plan, aspect)
                        except Exception:  # noqa: BLE001
                            new = None
                        if new is not None and _improves(cur, new):
                            kept.append({"board": s["board"], "word": raw[k], "zone": z})
                            cur = new
                            done = True
                            break
                        props["items"].remove(item)
                    if done:
                        break
                if done:
                    break
            if not done:
                break
    return {"kept": kept, "scores": cur}


# --------------------------------------------------------------------------------------------------------------------------------------------------------------
# What the director left thin (docs/WHITEBOARD_VACCINE_REGRESSION_2026-11-28.md): the LAST model-free steps, after the director has had its one chance.
WORD_KINDS = ("count", "rest", "busy")
MIN_WORD = 5                  # a narration word shorter than this is never matched to a drawing ('te' is not a cup)
_DRAWINGS: Dict[str, Any] = {}


def _named_drawings() -> Dict[str, List[Tuple[int, str]]]:
    """Folded name (English or Spanish title or synonym of a library drawing) -> [(rank, drawing id)]; rank 0 when it is the drawing's title or first synonym."""
    if not _DRAWINGS:
        from . import library
        from .retrieval import fold

        for it in library.index()["items"]:
            for lang in ("en", "es"):
                names = [it.get("title" if lang == "en" else "title_es")] + list(it.get("synonyms_" + lang) or [])
                for r, n in enumerate(names):
                    f = fold(n)
                    if f and len(f) >= MIN_WORD:
                        _DRAWINGS.setdefault(f, []).append((0 if r <= 1 else 1, it["id"]))
    return _DRAWINGS


def _drawing_for(word: str) -> Optional[str]:
    """The ONE library drawing that is what this word names (title or synonym, English or Spanish, unique at its best rank), else None: never a guess."""
    from .retrieval import fold

    hits = _named_drawings().get(fold(word)) or []
    if not hits:
        return None
    best = min(r for r, _ in hits)
    ids = {i for r, i in hits if r == best}
    return next(iter(ids)) if len(ids) == 1 else None


MAX_WORDS = 2                 # at most this many written key words are added to one board (the drawings that words name come first)
KEY_WORD_MIN = 7              # a written key word has at least this many letters
_NOT_KEY = ("mente", "ment", "lich", "mente", "zione", "ement")      # adverbs read as filler on a board (rapidamente, simplement, schnellstens ...)


def _candidates(narration: str, drawn: set, at: Optional[float], words: bool = False) -> List[Tuple[int, str, str, str]]:
    """Words of this narration that NAME a drawing of the library: (index, as spoken, the token tied to, the drawing id), a drawing the board does not already
    have; for a rest the words inside the stretch that rests first (`at`: 0.0 the start of the beat, a time for its end, None anywhere). With `words`, then the
    longest plain words (a written key word: at least KEY_WORD_MIN letters, not an adverb, not the first word of a sentence), id ''."""
    import re

    from .. import whiteboard_policy as wp

    raw = [re.sub(r"[^\w'-]", "", w) for w in narration.split()]
    toks = wp._words(narration)
    if len(raw) != len(toks):
        return []
    out = []
    for k, w in enumerate(raw):
        if len(w) < MIN_WORD or not toks[k] or toks[k] in toks[:k]:
            continue
        d = _drawing_for(w)
        if d and d not in drawn:
            out.append((k, w, toks[k], d))
    plain = []
    if words:
        for k, w in enumerate(raw):
            starts = k == 0 or str(narration.split()[k - 1]).rstrip().endswith((".", "!", "?", ":", "¿", "¡"))
            if len(w) >= KEY_WORD_MIN and toks[k] and toks[k] not in toks[:k] and not starts and not w.lower().endswith(_NOT_KEY) and not any(k == o[0] for o in out):
                plain.append((k, w, toks[k], ""))
    plain.sort(key=lambda x: -len(x[1]))
    if at is None:
        return out + plain
    return sorted(out, key=lambda x: x[0] if at == 0.0 else -x[0]) + sorted(plain, key=lambda x: x[0] if at == 0.0 else -x[0])


def rest_long(s: Dict[str, Any]) -> bool:
    return any(g >= 3.5 for g, _i, _a in (s.get("rests") or []))


def fill_words(plan: Dict[str, Any], aspect: str, scores: List[Dict[str, Any]], max_add: int = 3) -> Dict[str, Any]:
    """A board still thin after the director (too few drawings and phrases for its length, a pen that rests) gets the drawing that a word of its own narration NAMES
    (the library drawing whose title or synonym is exactly that word, unique: `_drawing_for`), tied to that word, in a free zone, one at a time. Nothing is
    written that is not said, no drawing is a guess. For `count` the additions stay only if some wanted complaint is then gone, and each is kept only if no board gets
    a kind of complaint it did not have (but those of WORD_KINDS) and none that passed now fails. A board that cannot be helped is left exactly as it was.
    -> {"kept": [...], "scores": the scores now}."""
    from .. import whiteboard_policy as wp
    from . import score as sc

    kept: List[Dict[str, Any]] = []
    cur = scores
    t0 = time.time()
    for s0 in list(scores):
        want = [k for k in WORD_KINDS if k in s0["kinds"]]
        if s0["ok"] or not want or time.time() - t0 > MAX_SECONDS * 2:
            continue
        board = s0["board"]
        added: List[Tuple[Dict[str, Any], Dict[str, Any]]] = []
        base = cur
        for _ in range(max_add):
            s = next((x for x in cur if x["board"] == board), None)
            if not s or not set(s["kinds"]) & set(WORD_KINDS):
                break
            props_list = [plan["beats"][i - 1]["scene"]["props"] for i in s["beats"]]
            free = wp.free_zones(props_list)
            drawn = {it.get("draw") for p in props_list for it in p.get("items") or []}
            sparse = s["solid"] <= 3 or bool(rest_long(s))     # key words only on a board that has almost nothing, or whose pen rests a long time: the drawings that words name come first anywhere
            rest = next(iter(s.get("rests") or []), None) if "rest" in s["kinds"] else None
            at = None if not rest else (0.0 if rest[2] == 0.0 else rest[2] if rest[2] > 0 else None)
            beats = [rest[1] - 1] if rest else [i - 1 for i in s["beats"]][::-1]
            done = False
            for bi in beats:
                props = plan["beats"][bi]["scene"]["props"]
                narration = str(plan["beats"][bi].get("narration") or "")
                ties = _ties(props, narration)
                for k, word, tok, did in _candidates(narration, drawn, at, words=sparse and sum(1 for _, it_ in added if it_.get("write")) < MAX_WORDS)[:5]:
                    for z in free[:4]:
                        for size in ("l", "m"):
                            pos = next((i for i, t in enumerate(ties) if t is not None and t > k), len(props["items"]))
                            item = ({"id": f"kd{k}", "draw": did} if did else {"id": f"kw{k}", "write": word}) | {"zone": z, "size": size, "say": tok}
                            props["items"].insert(pos, item)
                            try:
                                new = sc.score_plan(plan, aspect)
                            except Exception:  # noqa: BLE001
                                new = None
                            nb = next((x for x in new or [] if x["board"] == board), None)
                            ok_ = new is not None and len(new) == len(cur) and nb is not None and nb["solid"] > s["solid"] and _key(new) <= _key(cur) and not any(
                                (set(b["kinds"]) - set(a["kinds"]) - set(WORD_KINDS)) or (a["ok"] and not b["ok"]) for a, b in zip(cur, new))
                            if ok_:
                                added.append((props, item))
                                cur = new
                                done = True
                                break
                            props["items"].remove(item)
                        if done:
                            break
                    if done:
                        break
                if done:
                    break
            if not done:
                break
        final = next((x for x in cur if x["board"] == board), None)
        if added and final and set(want) <= set(final["kinds"]):      # nothing wanted was cleared: the board is left as it was
            for props, item in added:
                props["items"].remove(item)
            cur = base
        elif added:
            kept += [{"board": board, "word": it["say"], "drawing": it.get("draw") or it.get("write"), "zone": it["zone"], "size": it["size"]} for _, it in added]
    return {"kept": kept, "scores": cur}
