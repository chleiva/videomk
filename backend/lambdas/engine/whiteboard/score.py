"""The self-check of a whiteboard plan (docs/WHITEBOARD.md, "Self-check"): every board is laid out and timed exactly as the renderer will, without drawing a
pixel, and scored: how full it is, the smallest handwriting, overlaps, arrows that cross things, how busy the pen is. A board that fails gets a complaint in
plain words that the director is shown once (engine/whiteboard_policy.review).

No model, no storage, no drawing packages: a drawing's shape and drawing time come from the bundled library index, the word times from the measured speaking
rate (the real ones are only known after the voice is made; the renderer then uses those).
"""
from typing import Any, Dict, List, Optional, Tuple

WORDS_PER_S = 2.4            # engine/plan.SPOKEN_WORDS_PER_S
LEAD_S = 0.45                # a beat's lead-in before its first word
# What a board must reach (looked at on the hand-arranged demos: one board of 19 items, 12 of them drawings or writing, pen busy 60 to 82 %, longest rest 0.6 to 1.8 s)
MIN_SOLID_PER_10S = 4.0      # drawings and written phrases per 10 seconds of board
MIN_SOLID = 4                # ... and never fewer than this on a board of 10 s or more
MIN_COVERAGE = 0.30          # share of the framed picture covered by the boxes of drawings and writing
MIN_TEXT = 0.044             # smallest letter size, as a share of the frame's shorter side
MIN_BUSY = 0.45              # pen-busy share of the board's time
MAX_IDLE_S = 2.2             # longest stretch with the pen off the board (estimated times: the real limit aimed at is about 1.5 s)
MAX_LATE_S = 0.8             # with estimated word times only a clear delay is worth a complaint (the renderer starts things earlier to stay within about 0.3 s)


def _stub_loader():
    from . import library

    by = {it["id"]: it for it in library.index()["items"]}

    def load(oid: str) -> Dict[str, Any]:
        it = by[oid]                                           # KeyError: not in the library (written as a boxed label, as at render time)
        return {"w": 1000.0 * float(it.get("aspect") or 1.0), "h": 1000.0, "strokes": [], "draw_s": float(it.get("draw_s") or 1.2), "fill_colours": []}

    return load


def word_times(narration: str) -> Tuple[List[str], List[float], float]:
    """The narration as the alignment will tokenise it -> (tokens, estimated start time of each word, estimated scene length)."""
    from .. import whiteboard_policy

    toks = whiteboard_policy._words(narration)
    times = [LEAD_S + k / WORDS_PER_S for k in range(len(toks))]
    return toks, times, LEAD_S + len(toks) / WORDS_PER_S + 1.2      # a beat ends on a breath of about a second


def estimated_cues(props: Dict[str, Any], narration: str) -> Tuple[List[float], float]:
    """One cue per tied item (the scene's `cues` contract), at the estimated time of its word; a tie to a word that is not said takes the previous time."""
    from .. import whiteboard_policy

    toks, times, dur = word_times(narration)
    cues: List[float] = []
    prev = -1
    for it in props.get("items") or []:
        if not it.get("say"):
            continue
        tok = whiteboard_policy._say_token(it)
        k = next((i for i in range(prev + 1, len(toks)) if toks[i] == tok), None) if tok else None
        if k is not None:
            prev = k
        cues.append(round(times[k] if k is not None else (times[prev] if prev >= 0 else LEAD_S), 3))
    return cues, dur


def boards_of(beats: List[Dict[str, Any]]) -> List[List[int]]:
    """Beat indexes grouped by board: a whiteboard beat with props.board == "same" continues the board of the beat before it."""
    out: List[List[int]] = []
    for i, b in enumerate(beats):
        sc = b.get("scene") or {}
        if sc.get("type") != "whiteboard":
            continue
        if out and (sc.get("props") or {}).get("board") == "same" and out[-1][-1] == i - 1:
            out[-1].append(i)
        else:
            out.append([i])
    return out


def _off_board(rep: Dict[str, Any]) -> List[str]:
    return [w.split(" leaves")[0] for w in rep["warnings"] if w.endswith("leaves the board")]


def defects(props_list: List[Dict[str, Any]], aspect: str = "16:9", captions: bool = True) -> Dict[str, List[Any]]:
    """The geometry of ONE board, the props of the beats that share it, laid out as the renderer will: -> {"overlaps": [[id, id]], "off_board": [id]} of its
    drawings, texts and charts. Ids are the board-wide names (`j:id`, j the beat's place on the board) when beats share it, the plain ids when it is one beat's.
    Raises what the layout raises: the caller decides what a board that cannot be laid out means."""
    from .. import whiteboard_policy
    from ..frame import Frame
    from ..scenes.base import SceneCtx
    from ..scenes.elements import whiteboard as wbe

    ctx = SceneCtx(frame=Frame.parse(aspect, "1080p"), captions=captions)
    props = dict(whiteboard_policy.linked_props([{k: v for k, v in p.items() if k != "cues"} for p in props_list], [len(props_list)])[-1])
    _, _, _, rep = wbe.build(props, 10.0, ctx, 480, 270, load=_stub_loader(), layout_only=True)
    return {"overlaps": [list(x) for x in rep["overlaps"]], "off_board": _off_board(rep)}


def score_plan(plan: Dict[str, Any], aspect: str = "16:9") -> List[Dict[str, Any]]:
    """-> one score per board: {"board", "beats", "seconds", "items", "solid", "coverage", "min_text", "min_drawing", "overlaps", "crossed", "off_board",
    "pen_busy", "longest_idle_s", "late", "ok", "complaints": [plain sentences]}. Never raises: a board that cannot be laid out fails with that as its complaint."""
    from .. import whiteboard_policy
    from ..frame import Frame
    from ..scenes.base import SceneCtx
    from ..scenes.elements import whiteboard as wbe

    beats = plan.get("beats") or []
    frame = Frame.parse(aspect, "1080p")
    ctx = SceneCtx(frame=frame, captions=bool(plan.get("captions", True)))
    load = _stub_loader()
    groups = boards_of(beats)
    flat = [i for g in groups for i in g]
    timed, durs = [], []
    for i in flat:                                             # estimated word times stand in for the real ones (the timeline has those once the voice is made)
        p = dict(beats[i]["scene"]["props"])
        p["cues"], dur = estimated_cues(p, str(beats[i].get("narration") or ""))
        timed.append(p)
        durs.append(dur)
    linked = whiteboard_policy.linked_props(timed, [len(g) for g in groups], [d - 0.5 for d in durs])
    out: List[Dict[str, Any]] = []
    k = 0
    for bi, g in enumerate(groups):
        sc: Dict[str, Any] = {"board": bi + 1, "beats": [i + 1 for i in g], "complaints": []}
        try:
            total = busy = 0.0
            idle, late, rep = 0.0, [], None
            rests: List[Tuple[float, int, float]] = []
            for n, i in enumerate(g):
                props = dict(linked[k])
                k += 1
                props.pop("prev", None)
                props.pop("wall", None)
                dur = durs[k - 1]
                _, _, geo, rep = wbe.build(props, dur, ctx, 480, 270, load=load, layout_only=True)
                total += dur
                busy += rep["pen_busy_share"] * dur
                for gap, at in ((rep["longest_idle_s"], None), (rep["idle_before_s"] - (0.0 if n else 0.6), 0.0), (rep["idle_after_s"] - 0.6, dur)):
                    if gap > idle:
                        idle = gap
                    if gap > MAX_IDLE_S:
                        rests.append((gap, i, -1.0 if at is None else at))
                first = next((it["id"] for it in props["items"]), None)      # the first thing of a beat cannot start before the beat: only a long delay counts there
                late += [x for x in rep["late"] if x[1] > (1.5 if x[0] == first else MAX_LATE_S)]
            kinds, boxes = rep["kinds"], rep["boxes"]
            solid = [j for j, kd in kinds.items() if kd in ("draw", "write", "chart")]
            px = geo["box"][2] / rep["view"][2] / min(frame.W, frame.H)          # share of the frame's shorter side per board unit, in this board's framing
            texts = [v * px for v in rep["text_sizes"].values()]
            draws = [max(boxes[j][2] - boxes[j][0], boxes[j][3] - boxes[j][1]) * px for j in solid if kinds[j] == "draw"]
            off = _off_board(rep)
            sc.update(seconds=round(total, 1), items=len(kinds), solid=len(solid), coverage=rep["coverage"], min_text=round(min(texts), 3) if texts else None,
                      min_drawing=round(min(draws), 3) if draws else None, overlaps=rep["overlaps"], crossed=rep["crossed"], off_board=off,
                      pen_busy=round(busy / max(total, 1e-6), 2), longest_idle_s=round(idle, 2), late=late)
            need = max(MIN_SOLID if total >= 10 else 2, int(total / 10.0 * MIN_SOLID_PER_10S))
            name = lambda j: j.split(":", 1)[-1]      # noqa: E731
            free = whiteboard_policy.free_zones([beats[i]["scene"]["props"] for i in g])
            if len(solid) < need:
                sc["complaints"].append(f"only {len(solid)} drawings and written phrases for about {total:.0f} s: it needs at least {need}. Add drawings (with a written label near each) or key words"
                                        + (f" in the free zones ({', '.join(free)})" if free else ""))
            elif rep["coverage"] < MIN_COVERAGE:
                sc["complaints"].append(f"the board looks empty (its drawings and writing cover {rep['coverage'] * 100:.0f} % of the picture): use size l for the main drawings, write key terms larger"
                                        + (f" and fill the free zones ({', '.join(free)})" if free else ""))
            for a, c in rep["overlaps"][:3]:
                sc["complaints"].append(f"'{name(a)}' and '{name(c)}' overlap: give each its own zone" + (f" (free: {', '.join(free)})" if free else "") + " or shorten the text")
            for j in off[:2]:
                sc["complaints"].append(f"'{name(j)}' does not fit the board: shorten it or give it a wide zone")
            for j in rep["crossed"][:2]:
                sc["complaints"].append(f"the arrow '{name(j)}' runs across another drawing or text: connect neighbours, or move one end to a zone next to the other")
            if texts and min(texts) < MIN_TEXT:
                sc["complaints"].append("some writing is too small to read: fewer words per text, size m or larger")
            for gap, i, at in rests[:2]:
                sc["complaints"].append(f"in beat {i + 1} the pen rests for about {gap:.1f} s" + (" at the start" if at == 0.0 else " at the end" if at > 0 else "")
                                        + ": tie an item (a drawing, a key word, an arrow or an underline/circle/tick) to a word said in that stretch")
            if not rests and busy / max(total, 1e-6) < MIN_BUSY:
                sc["complaints"].append(f"the pen is busy only {busy / max(total, 1e-6) * 100:.0f} % of the time: add items tied to the words between the existing ones")
            for j, d in late[:2]:
                sc["complaints"].append(f"'{name(j)}' is finished {d:.1f} s after its word: write fewer words there or tie the item before it to an earlier word")
        except Exception as e:  # noqa: BLE001 - a score never breaks a plan
            sc["complaints"].append(f"the board could not be laid out ({type(e).__name__}: {str(e)[:120]})")
            k = sum(len(x) for x in groups[:bi + 1])
        sc["ok"] = not sc["complaints"]
        out.append(sc)
    return out


def summary(scores: List[Dict[str, Any]]) -> Dict[str, Any]:
    """The video in a few numbers (logged, and kept in plan["whiteboard"]["score"]). Overlaps and things off the board are counted on EVERY board, passing or
    failing, shared or not; a board that could not be laid out at all has no numbers and is counted in `not_laid_out`."""
    good = [s for s in scores if "seconds" in s]
    tot = sum(s["seconds"] for s in good) or 1.0
    texts = [s["min_text"] for s in good if s.get("min_text")]
    return {"boards": len(scores), "failed": sum(1 for s in scores if not s["ok"]), "items_per_board": round(sum(s["items"] for s in good) / max(1, len(good)), 1),
            "solid_per_board": round(sum(s["solid"] for s in good) / max(1, len(good)), 1), "coverage": round(sum(s["coverage"] * s["seconds"] for s in good) / tot, 3),
            "min_text": min(texts) if texts else None, "pen_busy": round(sum(s["pen_busy"] * s["seconds"] for s in good) / tot, 2),
            "longest_idle_s": max((s["longest_idle_s"] for s in good), default=0.0), "overlaps": sum(len(s.get("overlaps") or []) for s in scores),
            "off_board": sum(len(s.get("off_board") or []) for s in scores), "not_laid_out": len(scores) - len(good),
            "crossed": sum(len(s.get("crossed") or []) for s in scores), "seconds_per_board": round(tot / max(1, len(good)), 1)}


def better(a: Optional[List[Dict[str, Any]]], b: List[Dict[str, Any]]) -> bool:
    """Is the second set of scores at least as good as the first (fewer failed boards, then fewer complaints, then fuller)?"""
    if a is None:
        return True
    ka = (sum(1 for s in a if not s["ok"]), sum(len(s["complaints"]) for s in a), -sum(s.get("solid", 0) for s in a))
    kb = (sum(1 for s in b if not s["ok"]), sum(len(s["complaints"]) for s in b), -sum(s.get("solid", 0) for s in b))
    return kb <= ka
