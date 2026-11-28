"""A whiteboard BOARD: the items a planner writes, and the step that turns them plus word timings into a board ready to render (docs/WHITEBOARD.md).
The planner gives meaning (what, in which zone, tied to which word); layout, timing and camera are computed here. Engine copy of
scripts/whiteboard_proto/boardspec.py: same layout, camera and timing, driven by the engine's own cue times instead of a word list.

Layout    The board has the content box's shape and a 3x3 grid of zones. A drawing fills its zone's safe area (less the room its label needs); writing never goes
          under a minimum letter size (it spreads into free neighbouring zones instead); things placed beside others avoid them; arrows curve round what is
          in their way.
Camera    ONE framing for the whole board: everything that will ever be on it, with a margin, enlarged up to MAX_ZOOM when the board is not full. The camera
          never moves inside a scene (the element moves it between boards and for the final overview).
Timing    Every anchored item ENDS 0.15 s after its word starts and never later: what is squeezed is started earlier (the items before it are finished sooner),
          then drawn up to 1.6x faster; one pen; a drawing with idle time before it is drawn more slowly instead of waiting.
A board may be shared by several scenes (consecutive beats on one panel): `done` are the items earlier scenes drew (on the board from the first frame), `hidden`
the items later scenes will draw (they keep their place, nothing is drawn).
"""
import math
import re
import unicodedata
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from . import board as bd
from . import core
from . import hand as wr
from . import primitives as pr

LINE = 22.0
PEN_SPEED = 2500.0
GAP = 0.12                    # pen travel between items, seconds
ZONES = {"top-left": (0, 0), "top": (1, 0), "top-right": (2, 0), "left": (0, 1), "centre": (1, 1), "center": (1, 1), "right": (2, 1),
         "bottom-left": (0, 2), "bottom": (1, 2), "bottom-right": (2, 2)}
SPANS = {"top-row": ["top-left", "top-right"], "middle-row": ["left", "right"], "bottom-row": ["bottom-left", "bottom-right"], "left-col": ["top-left", "bottom-left"],
         "centre-col": ["top", "bottom"], "right-col": ["top-right", "bottom-right"], "full": ["top-left", "bottom-right"],
         "top-left-wide": ["top-left", "top"], "top-right-wide": ["top", "top-right"], "left-wide": ["left", "centre"], "right-wide": ["centre", "right"],
         "bottom-left-wide": ["bottom-left", "bottom"], "bottom-right-wide": ["bottom", "bottom-right"],
         "left-tall": ["top-left", "left"], "right-tall": ["top-right", "right"], "left-low": ["left", "bottom-left"], "right-low": ["right", "bottom-right"],
         "upper": ["top-left", "right"], "lower": ["left", "bottom-right"], "left-two-cols": ["top-left", "bottom"], "right-two-cols": ["top", "bottom-right"]}
DRAW_SIZE = {"xs": 0.50, "s": 0.64, "m": 0.80, "l": 0.92, "xl": 1.0}        # share of the zone's smaller side (a drawing beside another item, `near`, uses NEAR_SIZE)
NEAR_SIZE = {"xs": 0.34, "s": 0.44, "m": 0.56, "l": 0.68, "xl": 0.8}
TEXT_SIZE = {"xs": 80.0, "s": 94.0, "m": 120.0, "l": 158.0, "xl": 206.0}   # letter size in board units
TEXT_MIN = 76.0              # no handwriting is ever smaller than this (board units; 4.7 % of the frame's shorter side at the element's board size): text that does not fit spreads or wraps, it is not shrunk further
CHART_TEXT = 76.0            # the numbers and labels of a hand-drawn chart
WRITE_SLOW = 1.8             # writing with idle time before it is started earlier and written up to this many times slower (the natural speed is a quick hand)
MAX_ZOOM = 1.45              # how far the one framing of a board may enlarge a board that is not full
INKS = {"black": bd.INK, "blue": bd.BLUE, "red": bd.RED, "orange": bd.ORANGE, "green": bd.GREEN, "purple": (124, 77, 190), "grey": (110, 116, 126)}
FILLS = {"yellow": (255, 216, 77), "orange": (250, 178, 92), "red": (240, 128, 110), "pink": (247, 178, 200), "purple": (190, 170, 232), "blue": (120, 178, 238),
         "light_blue": (176, 218, 247), "green": (150, 212, 130), "brown": (214, 178, 140), "grey": (214, 219, 226)}
CHALK_PAPER = (38, 52, 50)
MARGIN = 0.05                 # safe margin inside a zone, share of its size
BENDS = (0.14, -0.14, 0.3, -0.3, 0.48, -0.48, 0.7, -0.7)      # how an arrow may curve (share of its length, either side), tried in this order until it crosses nothing
# Marks and arrows are fitted to the REAL ink (docs/WHITEBOARD.md, "Marks and arrows"). Distances in board units, from the CENTRE LINE of the mark or arrow
# (the marker is LINE wide: 10 of each distance is the stroke itself, the rest is paper you can see).
MARK_PADS = (30.0, 22.0)      # a circle or box is drawn this far outside the ink it surrounds: a comfortable loop first, then a close one
UNDER_PADS = (32.0, 25.0)     # an underline, below the lowest ink of its text (descenders included)
MARK_OWN = 15.0               # ... and after the hand's wobble no point of it may be nearer than this to the ink it marks
MARK_SAME = 15.0              # ... or to the other words of the same text
MARK_CLEAR = 20.0             # ... or to the ink of anything else
LOOP_CLEAR = 34.0             # a circle or box keeps this far from the ink of the NEXT item (round 2: loops 15 to 22 px from the next item looked cramped)
UNDERLINES_MAX = 5            # underline marks on one board (the ones a circle or box degraded into at most UNDERLINES_DEGRADED): a row of them is a ruled page, not emphasis
UNDERLINES_DEGRADED = 3
UNDER_END_GAP = 90.0          # two underlines at about the same height never end less than this far from each other (end to end they read as one line)
UNDER_AIM = 70.0              # an arrow that comes this near the underline of one of its own ends aims at the writing, and the underline yields
ATTACH = 14.0                 # an underline is nearer to its own ink than to anything else by at least this much: it must read as THAT thing's underline
MARK_APART = 30.0             # ... or to another mark or an arrow (centre line to centre line)
PATH_CLEAR = 24.0             # an arrow, to the ink of everything it passes and to the marks round it
PATH_TIGHT = 16.0             # ... or this, when the only way round is a narrow one
EDGE = 12.0                   # no arrow nearer than this to the edge of the board
MARK_OUT = (70.0, 50.0, 34.0)  # a loop round a thing at the edge of the board may run this far into the paper around the board: at the sides, the top, the bottom (the frame keeps more paper than that on every side in every aspect; the captions are below)
TOUCH = 11.0                  # what the report calls a collision: the stroke of a mark or arrow reaches the ink of something (half its width, and a hair) ...
STROKE_TOUCH = 19.0           # ... or two strokes run into each other
AUTO_MARK = re.compile(r"^(?:\d+:)?(?:em\d+_|\+r)")      # the ids of the marks the engine adds for pacing (whiteboard_policy.keep_busy: em<n>_<thing>; fill_rests: +r...)
TEXT_GAP = 64.0              # the clear space between the real ink of two different texts: under this ("sel" over "soleil", 8 px apart on screen) they read as one word. 64 units are 4 % of the frame's shorter side, about twice the space between two words of the handwriting
STUB = (170.0, 90.0)          # an arrow with no clean way through is shortened to a stub of this length at most, at least


def _norm(w: str) -> str:
    w = unicodedata.normalize("NFD", str(w).lower())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in w if unicodedata.category(c) != "Mn"))


class Layout:
    """The 3x3 grid of a board. Rows and columns share the board by WEIGHT: a row that only holds a title is lower than a row of drawings, an empty row or
    column gives most of its room to the others (`weights`)."""

    def __init__(self, W: float, H: float, rows: Sequence[float] = (1.0, 1.0, 1.0), cols: Sequence[float] = (1.0, 1.0, 1.0)):
        self.W, self.H = float(W), float(H)
        self.cw, self.ch = self.W / 3.0, self.H / 3.0             # the average zone: what sizes that do not depend on one zone are measured against
        self.xs = [self.W * sum(cols[:k]) / sum(cols) for k in range(4)]
        self.ys = [self.H * sum(rows[:k]) / sum(rows) for k in range(4)]

    def cells(self, zone) -> Tuple[int, int, int, int]:
        """-> (col0, row0, col1, row1) inclusive."""
        names = SPANS.get(zone, zone) if isinstance(zone, str) else zone
        names = [names] if isinstance(names, str) else list(names)
        cs = [ZONES[n] for n in names]
        return (min(c[0] for c in cs), min(c[1] for c in cs), max(c[0] for c in cs), max(c[1] for c in cs))

    def rect(self, cells) -> Tuple[float, float, float, float]:
        c0, r0, c1, r1 = cells
        x0, y0, x1, y1 = self.xs[c0], self.ys[r0], self.xs[c1 + 1], self.ys[r1 + 1]
        mx, my = MARGIN * self.cw, MARGIN * self.ch
        return (x0 + mx, y0 + my, x1 - mx, y1 - my)

    def cells_of_box(self, box) -> Tuple[int, int, int, int]:
        x0, y0, x1, y1 = box
        f = lambda v, e: int(min(2, max(0, sum(1 for k in (1, 2) if v >= e[k]))))      # noqa: E731
        return (f(x0 + 1, self.xs), f(y0 + 1, self.ys), f(x1 - 1, self.xs), f(y1 - 1, self.ys))

    def window(self, c0: int, r0: int) -> Tuple[float, float, float]:
        return (c0 * self.cw, r0 * self.ch, 2 * self.cw)


ROW_NEED = {"draw": 1.0, "chart": 1.2, "list": 1.0, "text": 0.62, "empty": 0.38}      # how much height a row wants, by the biggest thing in it
COL_EMPTY = 0.5                                                                    # an empty column keeps half its width
TALL = 1.2                                                                         # a board this much taller than wide (9:16, 4:5) is a tall one
ROW_EMPTY_TALL, COL_EMPTY_TALL = 0.14, 0.14                                        # ... on it an empty row or column keeps almost nothing: 2026-11-27 the Spanish 9:16 vaccine video shipped boards half empty


def weights(items: List[Dict[str, Any]], tall: bool = False) -> Tuple[List[float], List[float]]:
    """Row and column weights of a board from what its zones hold (every item of the board, whenever it is drawn). Pure. A TALL board (9:16, 4:5) gives an
    empty row or column almost nothing: its zones are narrow, so a drawing is bounded by the width of its zone, and the two or three rows the director used
    left the bottom (or the whole side) of the frame blank."""
    rows, cols = [ROW_EMPTY_TALL if tall else ROW_NEED["empty"]] * 3, [COL_EMPTY_TALL if tall else COL_EMPTY] * 3
    for it in items:
        if "zone" not in it or "near" in it or not ("draw" in it or "write" in it or "chart" in it):
            continue
        names = SPANS.get(it["zone"], it["zone"])
        cs = [ZONES[n] for n in ([names] if isinstance(names, str) else names)]
        c0, r0, c1, r1 = min(c[0] for c in cs), min(c[1] for c in cs), max(c[0] for c in cs), max(c[1] for c in cs)
        kind = "draw" if "draw" in it else "chart" if "chart" in it else ("list" if it["write"].count("\n") >= 1 or it.get("size") == "xl" else "text")
        need = ROW_NEED[kind] / (r1 - r0 + 1) if kind in ("list", "chart") and r1 > r0 else ROW_NEED[kind]
        for r in range(r0, r1 + 1):
            rows[r] = max(rows[r], need)
        for c in range(c0, c1 + 1):
            cols[c] = 1.0
    return rows, cols


def _cells_of(zone: str) -> Tuple[int, int, int, int]:
    names = SPANS.get(zone, zone)
    cs = [ZONES[n] for n in ([names] if isinstance(names, str) else names)]
    return (min(c[0] for c in cs), min(c[1] for c in cs), max(c[0] for c in cs), max(c[1] for c in cs))


_NAME_OF = {}
for _n, _c in ZONES.items():
    if _n != "center":
        _NAME_OF.setdefault((_c[0], _c[1], _c[0], _c[1]), _n)
for _n in SPANS:
    _NAME_OF.setdefault(_cells_of(_n), _n)


def centred(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A board whose things all sit in ONE outer column (only the left, or only the right, zones used) is moved to the middle column: the Spanish 9:16 vaccine
    video (2026-11-27) had a board of a title, an arrow and a cell in the left third, the rest of the frame blank for 11 s. Only zones move (to the zone of the
    same shape one column over); things placed `near` another follow it; nothing is changed when any zone has no such twin. Pure; returns the same list when
    there is nothing to do."""
    cols, zoned = set(), []
    for it in items:
        if "zone" in it and "near" not in it and ("draw" in it or "write" in it or "chart" in it):
            try:
                c = _cells_of(it["zone"])
            except KeyError:
                return items
            cols |= set(range(c[0], c[2] + 1))
            zoned.append(it)
    if len(cols) != 1 or cols == {1} or not zoned:
        return items
    d = 1 if cols == {0} else -1
    out = []
    for it in items:
        if "zone" in it:
            try:
                c = _cells_of(it["zone"])
            except KeyError:
                return items
            name = _NAME_OF.get((c[0] + d, c[1], c[2] + d, c[3]))
            if name is None or not 0 <= c[0] + d <= 2:
                return items
            it = dict(it, zone=name)
        out.append(it)
    return out


def _union(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _edge_point(box, towards, gap: float, cap: float = 0.42):
    """Where the line from the box's centre towards a point leaves the box (plus a gap)."""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    dx, dy = towards[0] - cx, towards[1] - cy
    n = math.hypot(dx, dy) or 1.0
    hx, hy = (box[2] - box[0]) / 2 + gap, (box[3] - box[1]) / 2 + gap
    t = min(hx / abs(dx) if dx else 1e9, hy / abs(dy) if dy else 1e9, cap)       # never past the middle of the way
    del n
    return (cx + dx * t, cy + dy * t)


def compile_board(items_in: List[Dict[str, Any]], anchors: Dict[str, float], dur: float, size_units: Tuple[float, float], scale: float, load: Callable[[str], Dict[str, Any]], *,
                  hand: str = "neat", tool: str = "marker", chalk: bool = False, camera: str = "auto", pad: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
                  frame_aspect: Optional[float] = None, tail: float = 0.0, done: Sequence[str] = (), hidden: Sequence[str] = (), t_min: float = 0.3,
                  layout_only: bool = False, tidy: bool = True) -> Tuple[Optional[bd.Board], bd.Camera, Dict[str, Any]]:
    """-> (board, camera, report). Deterministic: the same items, anchor times, size and scale give the same board on any machine.
    `anchors`: item id -> scene-local time its narration word starts (items without one are drawn right after the previous item). `size_units`: the board's
    width and height in board units (the content box). `scale`: raster pixels per unit. `pad`: paper around the content (left, top, right, bottom, units). `tail`: seconds at the end of the
    scene by which everything is over (the last scene of a big board then pulls back over all its panels). `done`: ids already on the board when the scene starts
    (earlier scenes of the same board drew them); `hidden`: ids that keep their place but are not drawn in this scene (later scenes draw them). `t_min`: nothing
    is drawn before this time (the camera is still arriving). `layout_only`: no raster (board is None): layout, timing and the report only. `camera` is kept
    for callers of the first version: the framing is always one still view. `tidy` (always on in the product): emphasis marks and arrows are fitted to the
    REAL ink of what is on the board and never touch anything ("Marks and arrows" in docs/WHITEBOARD.md); off, they are drawn where the plan asks whatever is
    there, which is only for measuring a plan as it was written (the report's `collisions` says what touches what, either way)."""
    dur = max(2.0, dur - tail)
    items_in = centred(items_in)
    L = Layout(size_units[0], size_units[1], *weights(items_in, tall=size_units[1] >= TALL * size_units[0]))
    b = None if layout_only else bd.Board(int(round(L.W + pad[0] + pad[2])), int(round(L.H + pad[1] + pad[3])), scale, paper=CHALK_PAPER if chalk else bd.PAPER, origin=(pad[0], pad[1]))
    hand_default, tool_default = hand, tool
    warnings: List[str] = []
    out_size = (frame_aspect or (L.W / L.H), 1.0)
    done_ids, hidden_ids = set(done), set(hidden)

    def ink(name, default="black"):
        c = INKS.get(name or default, INKS["black"])
        if chalk:
            return (238, 238, 230) if (name or default) == "black" else tuple(int(v + (255 - v) * 0.45) for v in c)
        return c

    def text_size(it, default="m"):
        return TEXT_SIZE[it["size"]] if isinstance(it.get("size"), str) else float(it.get("size", TEXT_SIZE[default]))

    # ------------------------------------------------------------ 1. geometry
    items = [dict(it) for it in items_in]
    by_id: Dict[str, Dict[str, Any]] = {}
    zone_draws: Dict[Tuple[int, int, int, int], List[str]] = {}
    taken: Dict[Tuple[int, int], int] = {}                       # grid cell -> how many zone items claim it
    label_room: Dict[str, Dict[str, float]] = {}                 # a drawing leaves room for the labels written above and below it
    for it in items:
        if "zone" in it and "near" not in it:
            c0, r0, c1, r1 = L.cells(it["zone"])
            for c in range(c0, c1 + 1):
                for r in range(r0, r1 + 1):
                    taken[(c, r)] = taken.get((c, r), 0) + 1
            if "draw" in it:
                zone_draws.setdefault((c0, r0, c1, r1), []).append(it["id"])
        if "write" in it and it.get("near") and it.get("side", "below") in ("below", "above"):
            size = max(text_size(it), TEXT_MIN)
            lines = it["write"].count("\n") + 1 + (1 if len(it["write"]) * 0.4 * size > L.cw * 0.95 else 0)
            room = label_room.setdefault(it["near"], {})
            room[it.get("side", "below")] = room.get(it.get("side", "below"), 0.0) + size * 1.2 * lines + 0.3 * size

    def grown(cells, fits, tall_first: bool = False) -> Tuple[int, int, int, int]:
        """A written block that does not fit its zone takes the free zones beside it (then below, then above) until it does (a chart: below and above first)."""
        c0, r0, c1, r1 = cells
        own = {(c, r) for c in range(c0, c1 + 1) for r in range(r0, r1 + 1)}

        def free(cs):
            return all(0 <= c <= 2 and 0 <= r <= 2 and (taken.get((c, r), 0) == 0 or ((c, r) in own and taken[(c, r)] == 1)) for c, r in cs)

        for _ in range(4):
            if fits((c0, r0, c1, r1)):
                break
            cands = [(c0, r0, c1 + 1, r1), (c0 - 1, r0, c1, r1), (c0, r0, c1, r1 + 1), (c0, r0 - 1, c1, r1)]
            for cand in (cands[2:] + cands[:2] if tall_first else cands):
                new = {(c, r) for c in range(cand[0], cand[2] + 1) for r in range(cand[1], cand[3] + 1)} - own
                if new and free(new):
                    c0, r0, c1, r1 = cand
                    own |= new
                    break
            else:
                break
        for cell in own:
            taken[cell] = max(1, taken.get(cell, 0))
        return (c0, r0, c1, r1)

    # an item may point at one that comes later in the list (an arrow drawn before its target): geometry is resolved in dependency order, timing keeps the list order
    marks: Dict[str, List[Any]] = {"kept": [], "degraded": [], "dropped": [], "moved": []}      # what became of the emphasis marks and of the arrows (the report)
    arrows: Dict[str, List[Any]] = {"direct": [], "rerouted": [], "stub": [], "dropped": []}
    marked: Dict[str, str] = {}                                  # thing -> the ONE emphasis mark it has

    def gone(it, like, why, book, like2=None) -> Dict[str, Any]:
        """A mark or arrow that is not drawn: it keeps a place in the books (something may point at it) and never reaches the board."""
        book["dropped"].append([it["id"], why])
        return {"id": it["id"], "kind": "gone", "box": like["box"] if like2 is None else _union(like["box"], like2["box"]), "cells": like["cells"], "it": it}

    def solids() -> List[Dict[str, Any]]:
        return [g_ for g_ in by_id.values() if g_["kind"] in ("draw", "write", "chart")]

    def fit_mark(it, t) -> Optional[Tuple[str, List[np.ndarray]]]:
        """The mark `it` on the thing `t`, fitted to the real ink: -> (the kind that fits, its strokes), or None when nothing fits or `t` has a mark already."""
        if t["id"] in marked:
            return None
        own = list(_inks(t))
        loop_own = _own_inks(t)                                  # what a loop round it must stay clear of
        if t["kind"] == "write" and it.get("word") is not None:
            sel = _word_sel(t["blk"]["words"], it["word"])
            if sel:
                own = loop_own = [t["inks"][k] for k in sel]
        rest = [(bx, MARK_SAME) for bx in _inks(t) if bx not in own]
        labels = [g_ for g_ in solids() if g_["it"].get("near") == t["id"]] if len(own) == len(_inks(t)) else []
        other = [(bx, MARK_CLEAR) for g_ in solids() if g_ is not t for bx in _inks(g_)]
        far = [(bx, MARK_CLEAR) for g_ in solids() if g_ is not t and g_ not in labels for bx in _inks(g_)]
        drawn = [_dense(g_["strokes"]) for g_ in by_id.values() if g_["kind"] in ("mark", "connect")]
        seed = _seed(it["id"])
        kind = it["mark"]
        T = _union_all(own)
        tries: List[Tuple[str, List[np.ndarray], List[Any], List[Any]]] = []        # (kind, strokes, the ink it must stay clear of with OWN, ... with their own clearance)
        if kind in ("circle", "box"):
            rnd = t["kind"] == "draw" and kind == "circle"
            sizes = [(MARK_PADS[0], 1.2), (MARK_PADS[1], 1.2), (MARK_PADS[1], 1.1)] if rnd else [(pad, 0.0) for pad in MARK_PADS]
            loose = [(bx, LOOP_CLEAR) for bx, _ in other]
            loose_far = [(bx, LOOP_CLEAR) for bx, _ in far]
            for pad, f in sizes:
                tries.append((kind, wr.mark_fit(kind, T, seed, pad, f), loop_own if rnd else own, rest + loose))
            if labels:                                           # a drawing with its label right beside it: the loop goes round both
                grp = [bx for g_ in labels for bx in _inks(g_)]
                for pad, f in sizes:
                    tries.append((kind, wr.mark_fit(kind, _union_all(own + grp), seed, pad, f), (loop_own if rnd else own) + grp, loose_far))
        if kind in ("double_underline",):
            tries += [(kind, wr.mark_fit(kind, T, seed, pad), own, rest + other) for pad in UNDER_PADS]
        if kind in ("tick", "cross") and it.get("side") != "over":
            s_ = min((T[3] - T[1]) * 0.8, 0.5 * L.ch)
            for side in ([it.get("side", "left")] + ["right", "left"]):
                bx = T[0] - s_ * 1.35 if side == "left" else T[2] + s_ * 0.35
                tries.append((kind, wr.mark(kind, (bx, T[1] + 0.1 * s_, bx + s_, T[1] + 1.1 * s_), seed=seed), own, rest + other))
        if kind in ("cross", "cross_out", "highlight") and not (kind == "cross" and it.get("side") != "over"):      # these go OVER what they mark, and over nothing else
            if kind == "cross":
                d_ = 0.12 * min(T[2] - T[0], T[3] - T[1])
                st = [pr.line((T[0] + d_, T[1] + d_), (T[2] - d_, T[3] - d_), seed, 3.0), pr.line((T[2] - d_, T[1] + d_), (T[0] + d_, T[3] - d_), seed + 1, 3.0)]
            else:
                st = wr.mark(kind, T, seed=seed)
            tries.append((kind, st, [], rest + other))
        else:                                                    # no room for the mark asked for: an underline, when there is room for that
            # (a little shorter than the word when something stands right beside it: a label next to its drawing)
            tries += [("underline", wr.mark_fit("underline", (T[0] + cut, T[1], T[2] - cut, T[3]), seed, pad), own, rest + other)
                      for cut in ((0.0, 24.0) if T[2] - T[0] > 130.0 else (0.0,)) for pad in UNDER_PADS]
        under_made = [g_ for g_ in by_id.values() if g_["kind"] == "mark" and g_.get("mark") in ("underline", "double_underline")]
        n_degraded = sum(1 for x in marks["degraded"] if x[2] in ("underline", "double_underline"))
        for kind_, st, mine, theirs in tries:
            pts = _dense(st)
            if kind_ in ("underline", "double_underline"):
                if len(under_made) >= UNDERLINES_MAX or (kind_ != kind and n_degraded >= UNDERLINES_DEGRADED):
                    continue                                         # enough underlines on this board (a circle that has no room is left out, not ruled)
                x0_, x1_, y_ = pts[:, 0].min(), pts[:, 0].max(), float(pts[:, 1].mean())
                if any(abs(float(u["box"][3] + u["box"][1]) / 2 - y_) < 45.0 and max(u["box"][0] - x1_, x0_ - u["box"][2]) < UNDER_END_GAP for u in under_made):
                    continue                                         # end to end with another underline
                near_own = min((_box_dist(pts, bx) for bx in own), default=1e9)
                near_other = min((_box_dist(pts, bx) for g_ in solids() if g_ is not t and g_["kind"] == "write" for bx in _inks(g_)), default=1e9)
                if near_other < near_own + ATTACH:
                    continue                                         # it would sit nearer to somebody else's WRITING than to its own (a drawing beside its label is not that: the label's underline may be as near to the picture): it must stay attached to its target
            if _free(pts, [(bx, MARK_OWN) for bx in mine] + theirs, L, [-v for v in MARK_OUT]) and all(_apart(pts, d_) >= MARK_APART for d_ in drawn):
                return kind_, st
        return None

    def route(it, a, c) -> Tuple[Optional[List[np.ndarray]], str]:
        """An arrow between two things, through free space: its ends start outside the things and whatever marks them; everything else is in its way.
        An arrow says more than an emphasis mark: when the marks ON its two ends leave it no direct way, it is routed as if they were not there and the
        ones it would then touch are taken off."""
        skip = {a["id"], c["id"]}
        on_ends = [g_ for g_ in by_id.values() if g_["kind"] == "mark" and g_.get("on") in skip]
        # An arrow aims at the INK of its thing (round 2: an arrowhead that stopped at the tip of an underline pointed at the underline, not at the words).
        # A loop (circle, box) round a thing is part of its picture and the arrow may end at it; an underline or double underline under it is not, it is
        # an obstacle like any other mark and, when the arrow cannot find a way past it, it yields (taken off, below).
        loops = lambda e, ms: [g_["box"] for g_ in ms if g_["on"] == e["id"] and g_.get("mark") not in ("underline", "double_underline")]      # noqa: E731
        others = [bx for g_ in solids() if g_["id"] not in skip for bx in _inks(g_)] + [g_["box"] for g_ in by_id.values() if g_["kind"] == "mark" and (g_.get("on") not in skip or g_ in on_ends and g_.get("mark") in ("underline", "double_underline"))]
        end = lambda e, ms: _union_all(list(_inks(e)) + loops(e, ms))      # noqa: E731 - the INK (the room a text was given is not what the arrow points at)
        strokes, how = _route(it, end(a, on_ends), end(c, on_ends), others, L)
        under = [g_ for g_ in on_ends if g_.get("mark") in ("underline", "double_underline")]
        near_under = lambda st_: [g_ for g_ in under if _apart(_dense(st_), _dense(g_["strokes"])) < UNDER_AIM]      # noqa: E731
        if on_ends and (how != "direct" or near_under(strokes)):
            # the arrow reaches its thing's ink only if the thing's own underline gets out of the way: tried without the underlines as obstacles, they yield
            # when that works; else (as before) tried without ANY mark on its ends, the ones it would then touch are taken off
            bare_others = [bx for bx in others if not any(bx == g_["box"] for g_ in under)]
            tries_ = [(end(a, on_ends), end(c, on_ends), bare_others)]
            if how != "direct":
                tries_.append((end(a, []), end(c, []), bare_others))
            for ea, ec, obs in tries_:
                bare, how2 = _route(it, ea, ec, obs, L)
                if how2 == "direct":
                    pts = _dense(bare)
                    for g_ in on_ends:
                        if _apart(pts, _dense(g_["strokes"])) < (UNDER_AIM if g_ in under else MARK_APART):
                            marks["kept"] = [x for x in marks["kept"] if x != g_["id"]]
                            marks["degraded"] = [x for x in marks["degraded"] if x[0] != g_["id"]]
                            if marked.get(g_["on"]) == g_["id"]:
                                del marked[g_["on"]]
                            by_id[g_["id"]] = gone(g_["it"], g_, "an arrow needed the room", marks)
                    return bare, how2
        return strokes, how

    def place(it) -> Dict[str, Any]:
        g: Dict[str, Any] = {"id": it["id"]}
        if "draw" in it:
            try:
                pkg = load(it["draw"])
            except Exception:  # noqa: BLE001 - a missing drawing never leaves a hole: the name is written in a box instead
                warnings.append(f"{it['id']}: no drawing '{it['draw']}', written as a boxed label")
                it = it | {"write": str(it.get("label") or it["draw"]).replace("_", " "), "boxed": True}
                it.pop("draw")
                pkg = None
            if pkg is not None:
                if "near" in it:
                    tb = by_id[it["near"]]["box"]
                    hmax = NEAR_SIZE[it.get("size", "xs")] * min(L.cw, L.ch)
                    k = min(hmax / pkg["h"], hmax * 1.3 / pkg["w"])
                    w, h = pkg["w"] * k, pkg["h"] * k
                    x, y = _free_side(tb, w, h, it.get("side", "right"), 26.0, by_id, L)
                    cells = L.cells_of_box(tb)
                else:
                    cells = L.cells(it["zone"])
                    x0, y0, x1, y1 = L.rect(cells)
                    peers = zone_draws[cells]
                    slot_w = (x1 - x0) / len(peers)
                    x0 = x0 + peers.index(it["id"]) * slot_w
                    room = label_room.get(it["id"], {})
                    below, above = min(room.get("below", 0.0), 0.42 * (y1 - y0)), min(room.get("above", 0.0), 0.3 * (y1 - y0))
                    avail = (y1 - y0) - below - above
                    hmax = min(DRAW_SIZE[it.get("size", "l")] * min(slot_w, y1 - y0, 1.5 * min(L.cw, L.ch)), avail)
                    k = min(hmax / pkg["h"], slot_w * 0.96 / pkg["w"])
                    w, h = pkg["w"] * k, pkg["h"] * k
                    dx, dy = it.get("shift", [0, 0])
                    x, y = x0 + (slot_w - w) / 2 + dx * slot_w, y0 + above + (avail - h) / 2 + dy * (y1 - y0)
                g.update(kind="draw", pkg=pkg, k=k, box=(x, y, x + w, y + h), cells=cells)
        if "chart" in it:
            # a chart needs height for its bars under the numbers: it takes a free zone below or above its own
            cells = grown(L.cells(it["zone"]), lambda c_: c_[3] > c_[1], tall_first=True)
            x0, y0, x1, y1 = L.rect(cells)
            room = label_room.get(it["id"], {})
            y0, y1 = y0 + min(room.get("above", 0.0), 0.3 * (y1 - y0)), y1 - min(room.get("below", 0.0), 0.3 * (y1 - y0))
            wmax = (0.34 if it.get("chart") != "line" else 0.6) * (y1 - y0) * max(2, len(it["values"])) + 60.0      # bars are taller than wide: a chart is never stretched across the board
            if x1 - x0 > wmax:
                x0, x1 = (x0 + x1 - wmax) / 2, (x0 + x1 + wmax) / 2
            g.update(kind="chart", cells=cells, **_chart(it, (x0, y0, x1, y1), hand_default, _seed(it["id"])))
        elif "write" in it:
            hand, tool = it.get("hand", hand_default), it.get("tool", tool_default)
            size = max(text_size(it), TEXT_MIN)
            if "near" in it:
                tb = by_id[it["near"]]["box"]
                cells = by_id[it["near"]]["cells"]
                blk = wr.layout(it["write"], hand, size, max_width=L.cw * 0.95, align="center", seed=_seed(it["id"]), min_size=TEXT_MIN)
                to_text = by_id[it["near"]].get("kind") == "write"
                x, y = _free_side(tb, blk["w"], blk["h"], it.get("side", "below"), (TEXT_GAP + 0.25 * blk["size"]) if to_text else 0.1 * blk["size"], by_id, L)
                x, y = _apart_texts(blk, x, y, it.get("side", "below"), tool, hand, [i_ for g_ in by_id.values() if g_.get("kind") == "write" for i_ in g_.get("inks", [])], L,
                                    [g_["box"] for g_ in by_id.values() if g_.get("kind") in ("draw", "write", "chart") and g_["box"] != tb])
            else:
                align = it.get("align") or ("left" if "\n" in it["write"] else "center")
                home = L.rect(L.cells(it["zone"]))

                def lay(cells_, min_size):
                    x0_, y0_, x1_, y1_ = L.rect(cells_)
                    return wr.layout(it["write"], hand, size, max_width=x1_ - x0_, max_height=y1_ - y0_, align=align, seed=_seed(it["id"]), min_size=min_size)

                def fits(cells_):
                    x0_, y0_, x1_, y1_ = L.rect(cells_)
                    blk_ = lay(cells_, size)
                    return blk_["w"] <= (x1_ - x0_) * 1.02 and blk_["h"] <= (y1_ - y0_) * 1.04

                cells = grown(L.cells(it["zone"]), fits)
                blk = lay(cells, TEXT_MIN)
                natural = it["write"].count("\n") + 1
                if blk["lines"] > natural:               # it wrapped: a number, or a short phrase, is rather written a little smaller on its own line
                    x0_, y0_, x1_, y1_ = L.rect(cells)
                    floor = max(TEXT_MIN, size * (0.5 if not re.search(r"[^\W\d_]", it["write"]) else 0.74))
                    sz = size * 0.93
                    while sz >= floor:
                        one = wr.layout(it["write"], hand, sz, max_width=x1_ - x0_, max_height=y1_ - y0_, align=align, seed=_seed(it["id"]), min_size=sz)
                        if one["lines"] == natural and one["w"] <= (x1_ - x0_) * 1.02:
                            blk = one
                            break
                        sz *= 0.93
                x0, y0, x1, y1 = L.rect(cells)
                hx = (home[0] + home[2]) / 2                                # stays centred on its own zone when the wider place allows it
                # a block of several lines is flush left INSIDE itself, but the block as a whole stands centred on its zone (round 2: "ARN / mensajero" in a full-width
                # row was pushed to the left edge of the frame, and the board looked half empty), unless the director asked for `align: left` by name
                x = x0 if it.get("align") == "left" else min(max(hx - blk["w"] / 2, x0), max(x0, x1 - blk["w"]))
                va = it.get("valign", "middle")
                hy = (home[1] + home[3]) / 2
                y = y0 if va == "top" else (y1 - blk["h"] if va == "bottom" else min(max(hy - blk["h"] / 2, y0), max(y0, y1 - blk["h"])))
                dx, dy = it.get("shift", [0, 0])
                x, y = x + dx * (x1 - x0), y + dy * (y1 - y0)
            g.update(kind="write", blk=blk, origin=(x, y), box=(x, y + 0.1 * blk["size"], x + blk["w"], y + blk["h"]), cells=cells, hand=hand, tool=tool)
            g["inks"] = word_inks(blk, (x, y), tool, hand)
            if it.get("boxed"):                                  # the frame of a boxed label is ink too
                m_ = 0.12 * (g["box"][3] - g["box"][1]) + 8 + LINE * 0.5
                g["inks"].append((g["box"][0] - m_, g["box"][1] - m_, g["box"][2] + m_, g["box"][3] + m_))
        elif "connect" in it:
            a, c = by_id[it["from"]], by_id[it["to"]]
            if tidy:
                if "gone" in (a["kind"], c["kind"]):
                    return gone(it, a, "one of its ends is not on the board", arrows)
                strokes, how = route(it, a, c)
                if strokes is None:
                    return gone(it, a, "no clean path", arrows, c)
                arrows[how].append(it["id"])
                g.update(kind="connect", strokes=strokes, cells=_cells_union(a["cells"], c["cells"]), crossed=False, how=how)
            else:
                others = [g_["box"] for g_ in by_id.values() if g_.get("kind") in ("draw", "write", "chart") and g_["id"] not in (a["id"], c["id"])]
                strokes, crossed = _connector(it, a["box"], c["box"], others, L)
                arrows["direct"].append(it["id"])
                g.update(kind="connect", strokes=strokes, cells=_cells_union(a["cells"], c["cells"]), crossed=crossed, how="direct")
            allp = np.concatenate(g["strokes"])
            g["box"] = (float(allp[:, 0].min()), float(allp[:, 1].min()), float(allp[:, 0].max()), float(allp[:, 1].max()))
        elif "mark" in it and tidy and by_id[it["on"]]["kind"] in ("draw", "write", "chart", "gone"):
            t = by_id[it["on"]]
            if t["kind"] == "gone":
                return gone(it, t, "what it marks is not on the board", marks)
            fit = fit_mark(it, t)
            if fit is None and AUTO_MARK.match(it["id"]):
                # a mark the ENGINE added to keep the pen busy (whiteboard_policy.keep_busy, fill_rests) stresses "the latest thing": when that has no
                # room, or has its mark, it goes to the latest thing drawn before it that is free (no mark of its own, room round it)
                order = {x["id"]: k for k, x in enumerate(items)}
                claimed = {x["on"] for x in items if "mark" in x and x["id"] != it["id"]} | set(marked)
                for cand in sorted((g_ for g_ in solids() if order[g_["id"]] < order[it["id"]] and g_["id"] not in claimed and g_ is not t), key=lambda g_: -order[g_["id"]]):
                    kind_ = "circle" if cand["kind"] != "write" and it["mark"] in ("underline", "double_underline") else it["mark"]
                    fit = fit_mark({k: v for k, v in it.items() if k != "word"} | {"mark": kind_}, cand)
                    if fit is not None:
                        marks["moved"].append([it["id"], t["id"], cand["id"]])
                        t = cand
                        it = it | {"on": cand["id"], "mark": kind_}
                        break
            if fit is None:
                return gone(it, t, "one mark per thing" if t["id"] in marked else "no room", marks)
            kind_, strokes = fit
            if kind_ != it["mark"]:
                marks["degraded"].append([it["id"], it["mark"], kind_])
                it = it | {"mark": kind_}
            else:
                marks["kept"].append(it["id"])
            marked[t["id"]] = it["id"]
            g.update(kind="mark", strokes=strokes, cells=t["cells"], mark=kind_, on=t["id"])
            allp = np.concatenate(g["strokes"])
            g["box"] = (float(allp[:, 0].min()), float(allp[:, 1].min()), float(allp[:, 0].max()), float(allp[:, 1].max()))
        elif "mark" in it:
            t = by_id[it["on"]]
            box = t["box"]
            marks["kept"].append(it["id"])
            if t["kind"] == "write" and it.get("word") is not None:
                ws_ = t["blk"]["words"]
                def key(x):
                    return _norm(re.sub(r"\\frac", "", x)) or x
                if isinstance(it["word"], int):
                    sel = [ws_[it["word"]]]
                else:
                    want = [key(x) for x in ([it["word"]] if isinstance(it["word"], str) else it["word"])]
                    sel = [w for w in ws_ if key(w["text"]) in want]
                if sel:
                    ox, oy = t["origin"]
                    box = (min(w["box"][0] for w in sel) + ox, min(w["box"][1] for w in sel) + oy, max(w["box"][2] for w in sel) + ox, max(w["box"][3] for w in sel) + oy)
            if it["mark"] == "cross" and it.get("side") == "over":      # a big X across the target
                d_ = 0.12 * min(box[2] - box[0], box[3] - box[1])
                g.update(kind="mark", strokes=[pr.line((box[0] + d_, box[1] + d_), (box[2] - d_, box[3] - d_), _seed(it["id"]), 3.0),
                                               pr.line((box[2] - d_, box[1] + d_), (box[0] + d_, box[3] - d_), _seed(it["id"]) + 1, 3.0)], cells=t["cells"], mark="cross")
                allp = np.concatenate(g["strokes"])
                g["box"] = (float(allp[:, 0].min()), float(allp[:, 1].min()), float(allp[:, 0].max()), float(allp[:, 1].max()))
                g["it"] = it
                g["on"] = t["id"]
                return g
            if it["mark"] in ("tick", "cross"):          # a tick or a cross goes beside its target, not over it
                s = min((box[3] - box[1]) * 0.8, 0.5 * L.ch)
                side = it.get("side", "left")
                if side == "left" and box[0] - s * 1.35 < 8.0:
                    side = "right"
                if side == "right" and box[2] + s * 1.35 > L.W - 8.0 and box[0] - s * 1.35 >= 8.0:
                    side = "left"
                bx = box[0] - s * 1.35 if side == "left" else box[2] + s * 0.35
                if bx < 8.0 or bx + s > L.W - 8.0:      # no room beside it on either side (a title across the board): underlined instead
                    it = it | {"mark": "underline"}
                else:
                    box = (bx, box[1] + 0.1 * s, bx + s, box[1] + 1.1 * s)
            g.update(kind="mark", strokes=wr.mark(it["mark"], box, seed=_seed(it["id"])), cells=t["cells"], mark=it["mark"], on=t["id"])
            allp = np.concatenate(g["strokes"])
            g["box"] = (float(allp[:, 0].min()), float(allp[:, 1].min()), float(allp[:, 0].max()), float(allp[:, 1].max()))
        g["it"] = it
        return g

    def settle_item(it) -> bool:
        try:
            by_id[it["id"]] = place(it)
            return True
        except KeyError as e:
            if str(e).strip("'") not in {x["id"] for x in items}:
                raise
            return False

    is_solid = lambda it: "draw" in it or "write" in it or "chart" in it      # noqa: E731
    pending = list(items)
    if tidy:
        # what the board HOLDS first (zone things, then things beside them), then the emphasis marks, which must fit round that, then the arrows, which
        # must find a way through all of it; whatever depends on a mark or an arrow comes last
        for allowed in (lambda it: is_solid(it) and "near" not in it, is_solid, lambda it: is_solid(it) or "mark" in it, lambda it: True):
            for _ in range(6):
                n0 = len(pending)
                pending = [it for it in pending if not (allowed(it) and settle_item(it))]
                if len(pending) == n0:
                    break
    else:
        for _ in range(6):
            # things placed beside others, and arrows, wait until every zone item is placed, so they can avoid them all
            pending = [it for it in pending if (_ == 0 and ("near" in it or "connect" in it)) or not settle_item(it)]
            if not pending:
                break
    if pending:
        raise ValueError(f"items that depend on each other: {[x['id'] for x in pending]}")
    for g in by_id.values():
        if "inks" not in g:
            g["inks"] = [g["box"]]
    if tidy:
        # the last word: whatever was placed after a mark or an arrow was fitted (a label beside an arrow) may have landed on it. Until nothing touches:
        # an arrow is routed again through what is there now, a mark is taken off; then what pointed at a thing that went is taken off too
        for _ in range(2 * len(by_id) + 2):
            hit = _collisions([g for g in by_id.values() if g["kind"] != "gone"])
            if not hit:
                break
            g = by_id[hit[0][0]]
            it = g["it"]
            if g["kind"] == "connect" and not g.get("again"):
                for book in arrows.values():
                    book[:] = [x for x in book if x != it["id"]]
                del by_id[it["id"]]
                new = place(it)
                new["again"] = True
                by_id[it["id"]] = new
            else:
                book = arrows if g["kind"] == "connect" else marks
                for k_ in book:
                    book[k_] = [x for x in book[k_] if (x[0] if isinstance(x, list) else x) != it["id"]]
                if marked.get(g.get("on")) == it["id"]:
                    del marked[g["on"]]
                by_id[it["id"]] = gone(it, g, "it touched something", book)
            for g_ in list(by_id.values()):
                if g_["kind"] == "mark" and by_id[g_["on"]]["kind"] == "gone":
                    marks["kept"] = [x for x in marks["kept"] if x != g_["id"]]
                    marks["degraded"] = [x for x in marks["degraded"] if x[0] != g_["id"]]
                    by_id[g_["id"]] = gone(g_["it"], g_, "what it marks is not on the board", marks)

    geo = [by_id[it["id"]] for it in items if by_id[it["id"]]["kind"] != "gone"]
    solid = [g for g in geo if g["kind"] in ("draw", "write", "chart")]
    overlaps: List[List[str]] = []
    for i, a in enumerate(solid):
        for c in solid[i + 1:]:
            ox = min(a["box"][2], c["box"][2]) - max(a["box"][0], c["box"][0])
            oy = min(a["box"][3], c["box"][3]) - max(a["box"][1], c["box"][1])
            if ox > 12 and oy > 12 and ox * oy > 0.06 * min(_area(a["box"]), _area(c["box"])):
                warnings.append(f"{a['id']} and {c['id']} overlap")
                overlaps.append([a["id"], c["id"]])
        if a["box"][0] < 0 or a["box"][1] < 0 or a["box"][2] > L.W or a["box"][3] > L.H:
            warnings.append(f"{a['id']} leaves the board")
    writes = [g for g in geo if g["kind"] == "write"]
    close_texts = [[a["id"], c["id"], round(gp, 1)] for i, a in enumerate(writes) for c in writes[i + 1:] if (gp := text_gap(a["inks"], c["inks"])) < TEXT_GAP]
    collisions = _collisions(geo)
    crossed = sorted({a_ for a_, c_ in collisions if by_id[a_]["kind"] == "connect" and by_id[c_]["kind"] in ("draw", "write", "chart")} | {g["id"] for g in geo if g.get("crossed")})

    # ------------------------------------------------------------ 2. timing
    ops: List[Dict[str, Any]] = []
    for g in geo:
        if g["id"] in hidden_ids:
            continue
        it = g["it"]
        anchor = anchors.get(g["id"])
        was = g["id"] in done_ids
        if g["kind"] == "draw":
            pen = sum(core.length_of(s) for s in g["pkg"]["strokes"]) * g["k"]
            nat = float(g["pkg"].get("draw_s") or 0.0) or float(np.clip(pen / PEN_SPEED, 0.45, 2.6))
            ops.append({"g": g, "nat": float(np.clip(nat, 0.45, 2.6)), "anchor": anchor, "stretch": True, "done": was})
        elif g["kind"] == "write":
            blk, tool, hand = g["blk"], g["tool"], g["hand"]
            # a written block ENDS on its word; its words are written back to back just before it (the engine gives one cue per item, not per written word)
            block_ops = [{"g": g, "word": wi, "nat": max(0.12, wr.write_time(w["strokes"], tool, blk["size"], hand)), "anchor": None, "stretch": False, "done": was} for wi, w in enumerate(blk["words"])]
            if anchor is not None and block_ops:
                t = anchor
                for o in reversed(block_ops):
                    o["anchor"] = t
                    t -= o["nat"] * 1.05 + 0.05
            ops += block_ops
        elif g["kind"] == "chart":
            pen = sum(core.length_of(s) for s in g["strokes"])
            ops.append({"g": g, "nat": float(np.clip(pen / PEN_SPEED, 0.7, 3.0)), "anchor": anchor, "stretch": True, "done": was})
            ops += [{"g": g, "text": ti, "word": wi, "nat": max(0.12, wr.write_time(w["strokes"], "pen", blk["size"], hand_default)), "anchor": None, "stretch": False, "done": was}
                    for ti, (blk, _) in enumerate(g["texts"]) for wi, w in enumerate(blk["words"])]
        else:
            pen = sum(core.length_of(s) for s in g["strokes"])
            ops.append({"g": g, "nat": float(np.clip(pen / PEN_SPEED, 0.3, 1.8)), "anchor": anchor, "stretch": g["kind"] == "connect", "done": was})
    live = [o for o in ops if not o["done"]]
    for o in ops:
        if o["done"]:
            o["start"], o["end"], o["how"] = -2.0, -1.0, "already there"

    def gap_before(o) -> float:
        return 0.05 if "word" in o and o["word"] > 0 else GAP

    # Backwards: the latest each thing may END so that everything after it can still end on its word at up to FAST x the natural speed (never late when that is possible).
    FAST = 1.6
    latest = [math.inf] * len(live)
    nxt_start = math.inf
    for i in range(len(live) - 1, -1, -1):
        o = live[i]
        own = o["anchor"] + 0.15 if o["anchor"] is not None else math.inf
        latest[i] = min(own, nxt_start - (gap_before(live[i + 1]) if i + 1 < len(live) else 0.0))
        nxt_start = latest[i] - o["nat"] / FAST
    prev_end = max(0.0, t_min - GAP)
    for i, o in enumerate(live):
        nat = o["nat"]
        lo = prev_end + gap_before(o)
        if o["anchor"] is None:
            start, end, o["how"] = lo, lo + nat, "after the previous"
            if end > latest[i]:                                  # the next thing needs the pen: this one is drawn faster
                end, o["how"] = max(lo + nat / FAST, latest[i]), "faster pen"
        else:
            own = o["anchor"] + 0.15
            end = min(own, latest[i])
            start, o["how"] = end - nat, "on the word" if end >= own - 1e-6 else "early, for the next"
            if start < lo:
                fast = nat / FAST
                if end - fast >= lo:
                    start, o["how"] = lo, "faster pen"
                else:
                    start, end, o["how"] = lo, lo + fast, ("late" if lo + fast > own + 1e-6 else "faster pen")
            elif o["stretch"]:                                   # idle time before this item: draw it more slowly instead of waiting
                start = max(lo, end - min(nat * 2.6, 3.2))
        o["start"], o["end"] = start, end
        prev_end = end
    # A written block with idle time before it is started earlier and written more slowly (never later): the hand keeps moving instead of waiting to dash it off.
    k = 0
    while k < len(live):
        o = live[k]
        if "word" in o and "text" not in o and o["word"] == 0 and o["anchor"] is not None:
            blk_ops = [x for x in live[k:] if x["g"] is o["g"] and "text" not in x]
            lo = (live[k - 1]["end"] if k else max(0.0, t_min - GAP)) + GAP
            t_end, span, idle = blk_ops[-1]["end"], blk_ops[-1]["end"] - o["start"], o["start"] - lo
            if idle > 0.15 and span > 0.05:
                f = min(WRITE_SLOW, (span + idle) / span)
                for x in blk_ops:
                    x["start"], x["end"] = t_end - (t_end - x["start"]) * f, t_end - (t_end - x["end"]) * f
            k += len(blk_ops)
        else:
            k += 1
    limit = max(1.0, dur - 0.5)
    last_tied = max((i for i, o in enumerate(live) if o["anchor"] is not None), default=-1)
    trail = live[last_tied + 1:]
    if trail and live:                                           # things with no word of their own after the last tied one: spread over what is left of the scene, not rushed and then nothing
        spare = (limit - 0.6) - trail[-1]["end"]
        if spare > 0.8:
            groups: List[List[Dict[str, Any]]] = []
            for o in trail:
                if groups and o["g"] is groups[-1][-1]["g"]:
                    groups[-1].append(o)
                else:
                    groups.append([o])
            for k, grp in enumerate(groups):
                d = spare * (k + 1) / (len(groups) + 0.5)
                for o in grp:
                    o["start"], o["end"] = o["start"] + d, o["end"] + d
    # Everything must be on the board before the scene ends (a moment to read it included): whatever runs past is brought forward and sped up.
    over = max((o["end"] for o in live), default=0.0)
    if over > limit and live:
        t_first = min(o["start"] for o in live)
        k_ = (limit - t_first) / max(over - t_first, 1e-6)
        for o in live:
            o["start"], o["end"] = t_first + (o["start"] - t_first) * k_, t_first + (o["end"] - t_first) * k_
        warnings.append(f"items compressed {k_:.2f}x to fit the scene")

    # ------------------------------------------------------------ 3. rasterise and place
    for o in ([] if layout_only else ops):
        g, it = o["g"], o["g"]["it"]
        t0, t1 = o["start"], o["end"]
        if g["kind"] == "draw":
            pkg = g["pkg"]
            r = core.raster_package(pkg, g["k"] * scale, line_px=LINE * scale * (0.82 if (g["box"][3] - g["box"][1]) < 230 else 1.0))
            b.place(r, g["box"][0], g["box"][1], ink(it.get("ink")), t0, t1)
            if it.get("fill", True):
                cols = pkg.get("fill_colours") or []
                tf = t1 + 0.06
                for fa, name in zip(r["fills"], cols):
                    name = (it.get("fill") if isinstance(it.get("fill"), str) else name)
                    if name in FILLS and (fa > 0.3).sum() > 40:
                        col = FILLS[name]
                        if chalk:
                            col = tuple(int(v * 0.8) for v in col)
                        area_u = float((fa > 0.3).sum()) / (scale * scale)
                        d = 0.01 if o["done"] else float(np.clip(area_u / 260000.0, 0.22, 0.6))
                        b.place_under(fa, g["box"][0], g["box"][1], col, tf, tf + d, opacity=0.6 if chalk else 0.92, tip_colour=tuple(int(v * 0.82) for v in col), tip_size=1.0)
                        tf += d + (0.0 if o["done"] else 0.05)
                o["fill_end"] = tf
        elif g["kind"] == "chart" and "text" in o:
            blk, org = g["texts"][o["text"]]
            r = wr.raster_word(blk["words"][o["word"]], org, hand_default, "pen", blk["size"], scale, seed=_seed(g["id"]) + 31 * o["text"] + o["word"])
            if r is not None:
                b.place(r, r["x"], r["y"], ink("black"), t0, t1, tip_size=0.78)
        elif g["kind"] == "chart":
            q = core.stroke_package(g["strokes"], LINE * 0.9, seed=_seed(g["id"]))
            b.place(core.raster_strokes(q, scale), q["x"], q["y"], ink(it.get("color"), "blue"), t0, t1)
            tf = t1 + 0.06
            for (x0_, y0_, x1_, y1_) in g["bars"]:
                fa = core.svg_alpha(f'<rect x="0" y="0" width="{x1_ - x0_:.1f}" height="{y1_ - y0_:.1f}" fill="#000"/>', x1_ - x0_, y1_ - y0_, scale)
                col = FILLS["light_blue"]
                d = 0.01 if o["done"] else 0.3
                b.place_under(fa, x0_, y0_, col, tf, tf + d, opacity=0.6 if chalk else 0.92, tip_colour=tuple(int(v * 0.82) for v in col), tip_size=1.0)
                tf += d + (0.0 if o["done"] else 0.04)
            o["fill_end"] = tf
        elif g["kind"] == "write":
            blk, tool = g["blk"], g["tool"]
            w = blk["words"][o["word"]]
            ox, oy = g["origin"]
            r = wr.raster_word(w, (ox, oy), g["hand"], tool, blk["size"], scale, seed=_seed(g["id"]) + o["word"])
            if r is None:
                continue
            b.place(r, r["x"], r["y"], ink(it.get("ink")), t0, t1, tip_size=0.78 if tool == "pen" else 1.0)
            if it.get("boxed") and o["word"] == len(blk["words"]) - 1:
                bx = core.stroke_package(wr.mark("box", g["box"], seed=_seed(g["id"])), LINE * 0.8)
                b.place(core.raster_strokes(bx, scale), bx["x"], bx["y"], ink("grey"), t1 + (0.0 if o["done"] else 0.1), t1 + (0.01 if o["done"] else 0.6))
        elif g["kind"] == "mark" and g["mark"] == "highlight":
            q = core.stroke_package(g["strokes"], it.get("width", 70.0), pressure=0.03)
            a = core.svg_alpha(q["ink"], q["w"], q["h"], scale)
            col = FILLS.get(it.get("color", "yellow"), FILLS["yellow"])
            b.place_under(a, q["x"], q["y"], col, t0, t1, opacity=0.75, strokes=[s * scale for s in q["strokes"]], tip_colour=col, tip_size=1.1, width=it.get("width", 70.0) * scale)
        else:
            width = LINE * (it.get("width", 0.9))
            q = core.stroke_package(g["strokes"], width, seed=_seed(g["id"]))
            b.place(core.raster_strokes(q, scale), q["x"], q["y"], ink(it.get("color"), "blue" if g["kind"] == "connect" else "red"), t0, t1)
    if b is not None:
        b.finish()

    # ------------------------------------------------------------ 4. camera: one framing, on everything this board will ever hold
    content = None
    for g in geo:
        content = g["box"] if content is None else _union(content, g["box"])
    final_view = _fit_view(content, L, out_size)
    cam = bd.Camera(final_view)

    merged: List[List[float]] = []
    for s_, e_ in sorted([(o["start"], max(o["end"], o.get("fill_end", o["end"]) if not layout_only else o["end"])) for o in live]):
        if merged and s_ <= merged[-1][1] + 0.05:
            merged[-1][1] = max(merged[-1][1], e_)
        else:
            merged.append([s_, e_])
    busy = sum(e_ - s_ for s_, e_ in merged)
    gaps = [b_[0] - a_[1] for a_, b_ in zip(merged, merged[1:])]
    lead = merged[0][0] if merged else dur
    rest = max(0.0, dur - merged[-1][1]) if merged else dur
    view_h = final_view[2] / out_size[0]
    mask = np.zeros((48, 48), bool)                              # how much of the framed view the drawings and writing cover (their boxes)
    for g in solid:
        x0, y0, x1, y1 = g["box"]
        i0, i1 = int(np.clip((y0 - final_view[1]) / view_h * 48, 0, 48)), int(np.clip(math.ceil((y1 - final_view[1]) / view_h * 48), 0, 48))
        j0, j1 = int(np.clip((x0 - final_view[0]) / final_view[2] * 48, 0, 48)), int(np.clip(math.ceil((x1 - final_view[0]) / final_view[2] * 48), 0, 48))
        mask[i0:i1, j0:j1] = True
    report = {"items": len(geo), "pen_ops": len(live), "pen_busy_share": round(busy / max(dur, 1e-6), 3), "longest_idle_s": round(max(gaps, default=0.0), 2),
              "idle_before_s": round(lead, 2), "idle_after_s": round(rest, 2),
              "late": [[o["g"]["id"], round(o["end"] - (o["anchor"] + 0.15), 2)] for o in live if o["how"] == "late"], "camera_moves": 0, "warnings": warnings,
              "boxes": {g["id"]: [round(v, 1) for v in g["box"]] for g in geo}, "kinds": {g["id"]: g["kind"] for g in geo},
              "text_sizes": {g["id"]: round(g["blk"]["size"], 1) for g in geo if g["kind"] == "write"}, "text_lines": {g["id"]: g["blk"]["lines"] for g in geo if g["kind"] == "write"}, "view": [round(v, 1) for v in final_view], "view_h": round(view_h, 1),
              "coverage": round(float(mask.mean()), 3), "overlaps": overlaps, "close_texts": close_texts, "arrow_ends": {g["id"]: [[round(float(g["strokes"][0][0][0]), 1), round(float(g["strokes"][0][0][1]), 1)], [round(float(g["strokes"][-1][-1][0]), 1), round(float(g["strokes"][-1][-1][1]), 1)]] for g in geo if g["kind"] == "connect"}, "crossed": crossed, "collisions": collisions, "marks": marks, "arrows": arrows,
              "times": {i_: [round(min(o["start"] for o in live if o["g"]["id"] == i_), 2), round(max(o["end"] for o in live if o["g"]["id"] == i_), 2)] for i_ in {o["g"]["id"] for o in live}}}
    return b, cam, report


def word_inks(blk: Dict[str, Any], origin: Tuple[float, float], tool: str, hand: str) -> List[Tuple[float, float, float, float]]:
    """The REAL ink of every written word of a block, in board units: the pen's path over its letters (accents, tails and tall letters included) grown by
    half the stroke. This is what a mark is sized from and what nothing else may touch; the block's `box` is the room the lines were given, not the ink."""
    ox, oy = origin
    half = max(wr.tool_width(tool, blk["size"]), wr.natural_width(hand) * blk["size"]) / 2.0 + 8.0      # measured against the raster of accented, tall and tailed letters: the ink never reaches further (tests)
    out = []
    for w in blk["words"]:
        if w["strokes"]:
            p = np.concatenate(w["strokes"])
            out.append((float(p[:, 0].min()) - half + ox, float(p[:, 1].min()) - half + oy, float(p[:, 0].max()) + half + ox, float(p[:, 1].max()) + half + oy))
        else:
            out.append((w["box"][0] + ox, w["box"][1] + oy, w["box"][2] + ox, w["box"][3] + oy))
    return out


def _inks(g: Dict[str, Any]) -> List[Tuple[float, float, float, float]]:
    return g.get("inks") or [g["box"]]


def _own_inks(g: Dict[str, Any]) -> List[Tuple[float, float, float, float]]:
    """The ink of a thing as ITS OWN mark must respect it. A text: its real ink. A drawing: its box less the four corners (a cross of two boxes): drawings
    are known here by their box only, and a loop round one may pass over the empty corners of that box, never over the rest."""
    if g["kind"] != "draw":
        return list(_inks(g))
    x0, y0, x1, y1 = g["box"]
    dx, dy = 0.2 * (x1 - x0), 0.2 * (y1 - y0)
    return [(x0, y0 + dy, x1, y1 - dy), (x0 + dx, y0, x1 - dx, y1)]


def _union_all(boxes):
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def _word_sel(words: List[Dict[str, Any]], word) -> List[int]:
    """Which written words a mark's `word` means: an index, or the word(s) by their letters."""
    key = lambda x: _norm(re.sub(r"\\frac", "", x)) or x      # noqa: E731
    if isinstance(word, int):
        return [word] if -len(words) <= word < len(words) else []
    want = {key(x) for w_ in ([word] if isinstance(word, str) else word) for x in [w_] + str(w_).split()}
    return [k for k, w in enumerate(words) if key(w["text"]) in want]


def _dense(strokes: Sequence[np.ndarray], step: float = 8.0) -> np.ndarray:
    """The points of pen strokes, close enough together that nothing slips between two of them."""
    out = []
    for s_ in strokes:
        s_ = np.asarray(s_, np.float64)
        if len(s_) < 2:
            out.append(s_)
            continue
        n = np.maximum(1, np.ceil(np.hypot(*np.diff(s_, axis=0).T) / step)).astype(int)
        out.append(np.concatenate([s_[i] + (s_[i + 1] - s_[i]) * np.linspace(0, 1, k, endpoint=False)[:, None] for i, k in enumerate(n)] + [s_[-1:]]))
    return np.concatenate(out) if out else np.zeros((0, 2))


def _inside(pts: np.ndarray, box, pad: float) -> bool:
    return bool(((pts[:, 0] > box[0] - pad) & (pts[:, 0] < box[2] + pad) & (pts[:, 1] > box[1] - pad) & (pts[:, 1] < box[3] + pad)).any())


def _free(pts: np.ndarray, boxes: Sequence[Tuple[Any, float]], L, edge: Sequence[float] = (EDGE, EDGE, EDGE)) -> bool:
    """Is a stroke on the board (`edge` inside it: sides, top, bottom) and clear of every (box, clearance)?"""
    if not len(pts):
        return False
    if pts[:, 0].min() < edge[0] or pts[:, 1].min() < edge[1] or pts[:, 0].max() > L.W - edge[0] or pts[:, 1].max() > L.H - edge[2]:
        return False
    return not any(_inside(pts, bx, pad) for bx, pad in boxes)


def _box_dist(pts: np.ndarray, box) -> float:
    """The smallest distance from a stroke's points to a rectangle."""
    dx = np.maximum(0.0, np.maximum(box[0] - pts[:, 0], pts[:, 0] - box[2]))
    dy = np.maximum(0.0, np.maximum(box[1] - pts[:, 1], pts[:, 1] - box[3]))
    return float(np.hypot(dx, dy).min()) if len(pts) else math.inf


def _apart(p: np.ndarray, q: np.ndarray) -> float:
    """The smallest distance between two strokes (their points)."""
    if not len(p) or not len(q):
        return math.inf
    gap = max(q[:, 0].min() - p[:, 0].max(), p[:, 0].min() - q[:, 0].max(), q[:, 1].min() - p[:, 1].max(), p[:, 1].min() - q[:, 1].max())
    if gap > 80.0:
        return gap
    d = p[:, None, :] - q[None, :, :]
    return float(np.sqrt((d * d).sum(-1).min()))


def _collisions(gs: List[Dict[str, Any]]) -> List[List[str]]:
    """Every emphasis mark or arrow that touches something, on the geometry as it will be drawn: [[the mark or arrow, what it touches]]. A stroke touches a
    drawing, text or chart when it reaches its ink (a text's real ink, word by word; a drawing's box), its own target included: a circle that cuts the phrase
    it surrounds is a collision. Only a mark that is drawn OVER its target on purpose (highlight, cross-out, a big X) may touch that target. A mark touches
    another mark or an arrow when their strokes meet. Two arrows may cross each other."""
    solid = [g for g in gs if g["kind"] in ("draw", "write", "chart")]
    pens = [g for g in gs if g["kind"] in ("mark", "connect")]
    pts = {g["id"]: _dense(g["strokes"]) for g in pens}
    out: List[List[str]] = []
    for i, g in enumerate(pens):
        p = pts[g["id"]]
        over = g["kind"] == "mark" and (g["mark"] in ("cross_out", "highlight") or (g["mark"] == "cross" and g["it"].get("side") == "over"))
        for s_ in solid:
            mine = g["kind"] == "mark" and g.get("on") == s_["id"]
            if over and mine:
                continue
            if any(_inside(p, bx, TOUCH) for bx in (_own_inks(s_) if mine and g["mark"] in ("circle", "box") else _inks(s_))):
                out.append([g["id"], s_["id"]])
        for h in pens[:i]:
            if g["kind"] == "connect" and h["kind"] == "connect":
                continue
            if _apart(p, pts[h["id"]]) < STROKE_TOUCH:
                out.append([g["id"], h["id"]])
    return out


def _route(it, box_a, box_c, others, L) -> Tuple[Optional[List[np.ndarray]], str]:
    """An arrow (or wavy, dashed, plain line) from one thing to another through FREE space. `box_a`, `box_c`: the ends with whatever marks them; `others`:
    the ink of everything else and the marks round it. In this order, the first path of which no point comes within PATH_CLEAR of anything, enters an end
    or leaves the board: the straight way or the gentlest bend ("direct"); a way round the corners of what is in between, the shortest first ("rerouted");
    a short arrow that leaves its start towards the target, or arrives at the target, and touches neither ("stub"). None of them: (None, "dropped")."""
    style, n = it.get("connect", "arrow"), int(it.get("count", 1))
    seed = _seed(it["id"])
    gap = it.get("gap", 30.0)
    ca, cc = np.array(_centre(box_a)), np.array(_centre(box_c))
    d = cc - ca
    Ln = float(np.hypot(*d)) or 1.0
    nrm = np.array([-d[1], d[0]]) / Ln
    def clean(strokes, clear: float = PATH_CLEAR) -> bool:
        return _free(_dense(strokes), [(bx, clear) for bx in others] + [(box_a, 10.0), (box_c, 10.0)], L)

    def ends(first, last):
        return _edge_point(box_a, tuple(first), gap, 0.85), _edge_point(box_c, tuple(last), gap, 0.85)

    def span() -> float:                                           # the free way between the two ends, along the line that joins them
        p0, p1 = ends(cc, ca)
        return float(np.dot(np.array(p1) - np.array(p0), d / Ln))

    if span() < 70.0:                                              # neighbours: the arrow starts and ends closer to them
        gap = min(gap, 14.0)
    room = span()
    if room < 44.0:                                                # no room for an arrow between two things that nearly touch: a hook round them says nothing
        return None, "dropped"

    def draw(pts, kind):
        return pr.arrow(pts, seed=seed, size=it.get("head_size", 48.0)) if kind == "arrow" else [pr.path(pts, seed)]

    if style in ("wavy", "dashed", "line"):
        p0, p1 = ends((ca + cc) / 2, (ca + cc) / 2)
        out: List[np.ndarray] = []
        for k in range(n):
            off = nrm * (k - (n - 1) / 2) * it.get("spread", 120.0)
            a, c = tuple(np.array(p0) + off), tuple(np.array(p1) + off)
            dl = float(np.hypot(c[0] - a[0], c[1] - a[1])) or 1.0
            if style == "wavy":
                out += pr.wavy_arrow(a, c, waves=max(1.5, dl / 190.0), seed=seed + k)
            elif style == "dashed":
                ds = pr.dashes(a, c, n=max(3, int(dl / 120)), seed=seed + k)
                out += ds + ([pr.head(np.concatenate(ds[-2:]), 44.0, seed=seed)] if it.get("head", True) else [])
            else:
                out += [pr.line(a, c, seed + k)]
        if clean(out):
            return out, "direct"
        style = "arrow" if it.get("head", True) else "curve"       # the straight way is blocked: a curved arrow round the obstacle instead
    for bend in ([it["bend"]] if it.get("bend") is not None else []) + [b_ for b_ in BENDS if abs(b_) < 0.2 or room >= 220.0]:      # a short arrow is not bent hard
        mid = (ca + cc) / 2 + nrm * bend * Ln
        p0, p1 = ends(mid, mid)
        m = (np.array(p0) + np.array(p1)) / 2 + nrm * bend * float(np.hypot(p1[0] - p0[0], p1[1] - p0[1]))
        st = draw([p0, tuple(m), p1], style)
        if clean(st):
            return st, "direct"
    # round the corners of what is in the way: one corner, or two neighbouring corners, of every obstacle; and the two elbows
    D = PATH_CLEAR + 44.0
    ways: List[List[Tuple[float, float]]] = [[(float(ca[0]), float(cc[1]))], [(float(cc[0]), float(ca[1]))]]
    for x0, y0, x1, y1 in others:
        cs = [(x0 - D, y0 - D), (x1 + D, y0 - D), (x1 + D, y1 + D), (x0 - D, y1 + D)]
        ways += [[c_] for c_ in cs]
        for k in range(4):
            ways += [[cs[k], cs[(k + 1) % 4]], [cs[(k + 1) % 4], cs[k]]]
    cands = []
    for way in (ways if room >= 220.0 else []):
        if any(not (EDGE < x < L.W - EDGE and EDGE < y < L.H - EDGE) for x, y in way):
            continue
        p0, p1 = ends(way[0], way[-1])
        pts = [p0] + way + [p1]
        cands.append((sum(math.hypot(b_[0] - a_[0], b_[1] - a_[1]) for a_, b_ in zip(pts, pts[1:])), pts))
    cands.sort(key=lambda x: x[0])
    for clear in (PATH_CLEAR, PATH_TIGHT):                         # a way round with comfortable room first; a close one is still better than an arrow that stops half way
        for length, pts in cands:
            if length > 2.6 * Ln + 300.0:                          # a way that long is not an arrow any more
                break
            st = draw(pts, style)
            if clean(st, clear):
                return st, "rerouted"
    p0, p1 = ends(cc, ca)
    u = d / Ln
    free = float(np.hypot(p1[0] - p0[0], p1[1] - p0[1]))
    for length in (min(STUB[0], max(STUB[1], 0.32 * free)), STUB[1]):
        for a_, c_ in ((np.array(p0), np.array(p0) + u * length), (np.array(p1) - u * length, np.array(p1))):
            st = draw([tuple(a_), tuple(c_)], style)
            if clean(st):
                return st, "stub"
    return None, "dropped"


def _chart(it: Dict[str, Any], rect, hand: str, seed: int) -> Dict[str, Any]:
    """Numbers drawn by hand: `bars` (a baseline and one outlined, coloured bar per value, its value above, its label below) or `line` (two axes and a rising
    or falling line with an arrow head). -> the pen strokes, the bar areas to colour, the texts and the box."""
    x0, y0, x1, y1 = rect
    vals, labels = [float(v) for v in it["values"]], list(it.get("labels") or [])
    n = len(vals)
    lab = float(np.clip((y1 - y0) * 0.13, CHART_TEXT, 96.0))      # the numbers are read in the one framing of the board: never tiny
    has_labels = any(labels)
    yb = y1 - (lab * 1.12 if has_labels else 8.0)
    top = y0 + lab * 1.3
    slot = (x1 - x0) / n
    vmax = max(vals) or 1.0
    strokes: List[np.ndarray] = []
    bars, texts = [], []

    def text(s_: str, cx: float, y: float, size: float, k: int):
        blk = wr.layout(s_, hand, size, max_width=slot * 0.98, align="center", seed=seed + k, min_size=min(size, CHART_TEXT * 0.8))
        texts.append((blk, (cx - blk["w"] / 2, y)))

    if it.get("chart") == "line":
        strokes += [pr.line((x0, top - lab), (x0, yb), seed, 3.0), pr.line((x0, yb), (x1, yb), seed + 1, 3.0)]
        pts = [(x0 + slot * (k + 0.5), yb - (yb - top) * (0.06 + 0.94 * v / vmax)) for k, v in enumerate(vals)]
        strokes += pr.arrow(pts, seed=seed + 2, size=44.0)
    else:
        strokes.append(pr.line((x0, yb), (x1, yb), seed, 3.0))
        for k, v in enumerate(vals):
            bx0, bx1, by = x0 + slot * (k + 0.2), x0 + slot * (k + 0.8), yb - max(14.0, (yb - top) * v / vmax)
            strokes += [pr.line((bx0, yb), (bx0, by), seed + 3 * k + 2, 2.5), pr.line((bx0, by), (bx1, by), seed + 3 * k + 3, 2.5), pr.line((bx1, by), (bx1, yb), seed + 3 * k + 4, 2.5)]
            bars.append((bx0 + 8, by + 8, bx1 - 8, yb - 6))
            text(f"{v:,.10g}", (bx0 + bx1) / 2, by - lab * 1.25, lab, 100 + k)
    for k, s_ in enumerate(labels[:n]):
        if s_:
            text(s_, x0 + slot * (k + 0.5), yb + lab * 0.02, lab * 0.9, k)
    return {"strokes": strokes, "bars": [b_ for b_ in bars if b_[2] - b_[0] > 12 and b_[3] - b_[1] > 12], "texts": texts, "box": (x0, y0, x1, y1)}


def _seed(s: str) -> int:
    import zlib

    return zlib.crc32(s.encode()) % 100000


def _centre(box):
    return ((box[0] + box[2]) / 2, (box[1] + box[3]) / 2)


def _area(box):
    return max(1.0, (box[2] - box[0]) * (box[3] - box[1]))


def _cells_union(a, c):
    return (min(a[0], c[0]), min(a[1], c[1]), max(a[2], c[2]), max(a[3], c[3]))


def _beside(tb, w, h, side, gap):
    cx, cy = _centre(tb)
    if side == "below":
        return cx - w / 2, tb[3] + gap
    if side == "above":
        return cx - w / 2, tb[1] - gap - h
    if side == "left":
        return tb[0] - gap - w, cy - h / 2
    return tb[2] + gap, cy - h / 2


def _rect_gap(a, b) -> float:
    """The clear distance between two rectangles (0 when they touch or overlap)."""
    dx = max(0.0, max(a[0], b[0]) - min(a[2], b[2]))
    dy = max(0.0, max(a[1], b[1]) - min(a[3], b[3]))
    return math.hypot(dx, dy)


def text_gap(inks_a, inks_b) -> float:
    """The clear distance between the REAL ink of two texts (the pen path of their words, `word_inks`)."""
    return min((_rect_gap(p, q) for p in inks_a for q in inks_b), default=1e9)


def _apart_texts(blk, x, y, side, tool, hand, others, L, solids=(), gap: float = TEXT_GAP):
    """A text put `side` of another is pushed away from it (along that side's axis) until the real ink of the two is at least `gap` apart and clear of every
    other text; stays on the board. -> (x, y)."""
    step = {"below": (0.0, 1.0), "above": (0.0, -1.0), "right": (1.0, 0.0), "left": (-1.0, 0.0)}.get(side, (0.0, 1.0))
    for _ in range(12):
        mine = word_inks(blk, (x, y), tool, hand)
        worst = text_gap(mine, others)
        if worst >= gap:
            break
        d = gap - worst + 1.0
        nx, ny = x + step[0] * d, y + step[1] * d
        if nx < 20.0 or ny < 10.0 or nx + blk["w"] > L.W - 20.0 or ny + blk["h"] > L.H - 10.0:
            break
        if any(_rect_gap((nx, ny, nx + blk["w"], ny + blk["h"]), o) < 6.0 for o in solids):      # never into another drawing or text to get away from this one
            break
        x, y = nx, ny
    return x, y


def _free_side(tb, w, h, side, gap, by_id, L):
    """Beside the target on the asked side; if that would cover another drawing or text, or leave the board, the first other side that is free."""
    others = [g["box"] for g in by_id.values() if g.get("kind") in ("draw", "write", "chart") and g["box"] != tb]
    best = None
    for sd in [side] + [x for x in ("below", "right", "above", "left") if x != side]:
        x, y = _beside(tb, w, h, sd, gap)
        x, y = min(max(x, 20.0), L.W - w - 20.0), min(max(y, 10.0), L.H - h - 10.0)
        box = (x, y, x + w, y + h)
        hit = sum(max(0.0, min(box[2], o[2]) - max(box[0], o[0])) * max(0.0, min(box[3], o[3]) - max(box[1], o[1])) for o in others + [tb])
        if hit < 0.03 * w * h:
            return x, y
        if best is None or hit < best[0]:
            best = (hit, x, y)
    return best[1], best[2]


def _hits(pts: np.ndarray, boxes, L, pad: float = 16.0) -> float:
    """How much of a path runs over other things (share of its points inside any box grown by `pad`) or off the board."""
    if not len(pts):
        return 0.0
    bad = (pts[:, 0] < 6) | (pts[:, 1] < 6) | (pts[:, 0] > L.W - 6) | (pts[:, 1] > L.H - 6)
    for x0, y0, x1, y1 in boxes:
        bad |= (pts[:, 0] > x0 - pad) & (pts[:, 0] < x1 + pad) & (pts[:, 1] > y0 - pad) & (pts[:, 1] < y1 + pad)
    return float(bad.mean())


def _connector(it, box_a, box_c, others, L) -> Tuple[List[np.ndarray], bool]:
    """An arrow (or wavy, dashed, plain line) from one item to another. It leaves and arrives at the edges of their boxes and CURVES round whatever lies between:
    the gentlest bend, to either side, that crosses no other drawing or text and stays on the board. -> (strokes, True when even the best path crosses something)."""
    style, n = it.get("connect", "arrow"), int(it.get("count", 1))
    seed = _seed(it["id"])
    gap = it.get("gap", 30.0)
    ca, cc = np.array(_centre(box_a)), np.array(_centre(box_c))
    d = cc - ca
    Ln = float(np.hypot(*d)) or 1.0
    nrm = np.array([-d[1], d[0]]) / Ln

    def ends(mid):
        return _edge_point(box_a, tuple(mid), gap, 0.85), _edge_point(box_c, tuple(mid), gap, 0.85)

    if style in ("wavy", "dashed", "line"):
        p0, p1 = ends((ca + cc) / 2)
        if _hits(pr._curve([p0, p1], 12.0), others, L) < 0.02 or it.get("bend") is not None:
            out: List[np.ndarray] = []
            for k in range(n):
                off = nrm * (k - (n - 1) / 2) * it.get("spread", 120.0)
                a, c = tuple(np.array(p0) + off), tuple(np.array(p1) + off)
                dl = float(np.hypot(c[0] - a[0], c[1] - a[1])) or 1.0
                if style == "wavy":
                    out += pr.wavy_arrow(a, c, waves=max(1.5, dl / 190.0), seed=seed + k)
                elif style == "dashed":
                    ds = pr.dashes(a, c, n=max(3, int(dl / 120)), seed=seed + k)
                    out += ds + ([pr.head(np.concatenate(ds[-2:]), 44.0, seed=seed)] if it.get("head", True) else [])
                else:
                    out += [pr.line(a, c, seed + k)]
            return out, False
        style = "arrow" if it.get("head", True) else "curve"       # the straight way is blocked: a curved arrow round the obstacle instead
    best = None
    for bend in ([it["bend"]] if it.get("bend") is not None else BENDS):
        mid = (ca + cc) / 2 + nrm * bend * Ln
        p0, p1 = ends(mid)
        m = (np.array(p0) + np.array(p1)) / 2 + nrm * bend * float(np.hypot(p1[0] - p0[0], p1[1] - p0[1]))
        pts = [p0, tuple(m), p1]
        cost = _hits(pr._curve(pts, 12.0), others, L)
        if best is None or cost < best[0] - 1e-9:
            best = (cost, pts)
        if cost < 0.005:
            break
    cost, pts = best
    strokes = pr.arrow(pts, seed=seed, size=it.get("head_size", 48.0)) if style == "arrow" else [pr.path(pts, seed)]
    return strokes, cost >= 0.02


def _fit_view(content, L, out_size) -> Tuple[float, float, float]:
    """The board's one framing: everything drawn, with a margin, in the frame's aspect, inside the board."""
    if content is None:
        return (0.0, 0.0, float(L.W))
    asp = out_size[0] / out_size[1]
    m = 0.04 * min(L.W, L.H)
    x0, y0, x1, y1 = content[0] - m, content[1] - m, content[2] + m, content[3] + m
    w = max(x1 - x0, (y1 - y0) * asp, min(L.W, L.H * asp) / MAX_ZOOM)      # a board that is not full is enlarged, up to MAX_ZOOM
    w = min(w, L.W, L.H * asp)
    h = w / asp
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    vx = min(max(cx - w / 2, 0.0), L.W - w)
    vy = min(max(cy - h / 2, 0.0), L.H - h - 1e-6)
    return (vx, max(vy, 0.0), w)
