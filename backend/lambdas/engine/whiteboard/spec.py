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


def weights(items: List[Dict[str, Any]]) -> Tuple[List[float], List[float]]:
    """Row and column weights of a board from what its zones hold (every item of the board, whenever it is drawn). Pure."""
    rows, cols = [ROW_NEED["empty"]] * 3, [COL_EMPTY] * 3
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
                  layout_only: bool = False) -> Tuple[Optional[bd.Board], bd.Camera, Dict[str, Any]]:
    """-> (board, camera, report). Deterministic: the same items, anchor times, size and scale give the same board on any machine.
    `anchors`: item id -> scene-local time its narration word starts (items without one are drawn right after the previous item). `size_units`: the board's
    width and height in board units (the content box). `scale`: raster pixels per unit. `pad`: paper around the content (left, top, right, bottom, units). `tail`: seconds at the end of the
    scene by which everything is over (the last scene of a big board then pulls back over all its panels). `done`: ids already on the board when the scene starts
    (earlier scenes of the same board drew them); `hidden`: ids that keep their place but are not drawn in this scene (later scenes draw them). `t_min`: nothing
    is drawn before this time (the camera is still arriving). `layout_only`: no raster (board is None): layout, timing and the report only. `camera` is kept
    for callers of the first version: the framing is always one still view."""
    dur = max(2.0, dur - tail)
    L = Layout(size_units[0], size_units[1], *weights(items_in))
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
    pending = list(items)
    for _ in range(6):
        later = []
        for it in pending:
            try:
                if _ == 0 and ("near" in it or "connect" in it):
                    raise KeyError(it.get("near") or it["from"])     # things placed beside others, and arrows, wait until every zone item is placed, so they can avoid them all
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
                        x, y = _free_side(tb, blk["w"], blk["h"], it.get("side", "below"), 0.1 * blk["size"], by_id, L)
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
                        x = x0 if align == "left" else min(max(hx - blk["w"] / 2, x0), max(x0, x1 - blk["w"]))
                        va = it.get("valign", "middle")
                        hy = (home[1] + home[3]) / 2
                        y = y0 if va == "top" else (y1 - blk["h"] if va == "bottom" else min(max(hy - blk["h"] / 2, y0), max(y0, y1 - blk["h"])))
                        dx, dy = it.get("shift", [0, 0])
                        x, y = x + dx * (x1 - x0), y + dy * (y1 - y0)
                    g.update(kind="write", blk=blk, origin=(x, y), box=(x, y + 0.1 * blk["size"], x + blk["w"], y + blk["h"]), cells=cells, hand=hand, tool=tool)
                elif "connect" in it:
                    a, c = by_id[it["from"]], by_id[it["to"]]
                    others = [g_["box"] for g_ in by_id.values() if g_.get("kind") in ("draw", "write", "chart") and g_["id"] not in (a["id"], c["id"])]
                    strokes, crossed = _connector(it, a["box"], c["box"], others, L)
                    g.update(kind="connect", strokes=strokes, cells=_cells_union(a["cells"], c["cells"]), crossed=crossed)
                    allp = np.concatenate(g["strokes"])
                    g["box"] = (float(allp[:, 0].min()), float(allp[:, 1].min()), float(allp[:, 0].max()), float(allp[:, 1].max()))
                elif "mark" in it:
                    t = by_id[it["on"]]
                    box = t["box"]
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
                        by_id[it["id"]] = g
                        continue
                    if it["mark"] in ("tick", "cross"):          # a tick or a cross goes beside its target, not over it
                        s = min((box[3] - box[1]) * 0.8, 0.5 * L.ch)
                        side = it.get("side", "left")
                        if side == "left" and box[0] - s * 1.35 < 8.0:
                            side = "right"
                        bx = box[0] - s * 1.35 if side == "left" else box[2] + s * 0.35
                        box = (bx, box[1] + 0.1 * s, bx + s, box[1] + 1.1 * s)
                    g.update(kind="mark", strokes=wr.mark(it["mark"], box, seed=_seed(it["id"])), cells=t["cells"], mark=it["mark"])
                    allp = np.concatenate(g["strokes"])
                    g["box"] = (float(allp[:, 0].min()), float(allp[:, 1].min()), float(allp[:, 0].max()), float(allp[:, 1].max()))
                g["it"] = it
                by_id[it["id"]] = g
            except KeyError as e:
                if str(e).strip("'") not in {x["id"] for x in items}:
                    raise
                later.append(it)
        pending = later
        if not pending:
            break
    if pending:
        raise ValueError(f"items that depend on each other: {[x['id'] for x in pending]}")

    geo = [by_id[it["id"]] for it in items]
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
    crossed = [g["id"] for g in geo if g.get("crossed")]

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
              "coverage": round(float(mask.mean()), 3), "overlaps": overlaps, "crossed": crossed,
              "times": {i_: [round(min(o["start"] for o in live if o["g"]["id"] == i_), 2), round(max(o["end"] for o in live if o["g"]["id"] == i_), 2)] for i_ in {o["g"]["id"] for o in live}}}
    return b, cam, report


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
