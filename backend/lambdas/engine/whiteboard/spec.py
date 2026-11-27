"""A whiteboard BOARD: the items a planner writes, and the step that turns them plus word timings into a board ready to render (docs/WHITEBOARD.md).
The planner gives meaning (what, in which zone, tied to which word); layout, timing and camera are computed here. Engine copy of
scripts/whiteboard_proto/boardspec.py: same layout, camera and timing, driven by the engine's own cue times instead of a word list.

Layout    The board has the content box's shape and a 3x3 grid of zones. A drawing lives inside its zone's safe area; things placed beside others avoid them.
Camera    The close view is exactly 2x2 zones and is only used if it cuts no drawing or text at its edge; the scene ends on a pull-back framed on the content.
Timing    Every anchored item ENDS 0.15 s after its word starts; one pen; up to 1.6x faster when squeezed, slower to use idle time; everything fits the scene.
"""
import math
import re
import unicodedata
from typing import Any, Callable, Dict, List, Optional, Tuple

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
DRAW_SIZE = {"xs": 0.34, "s": 0.48, "m": 0.64, "l": 0.82, "xl": 0.94}       # share of the zone's smaller side
TEXT_SIZE = {"xs": 64.0, "s": 84.0, "m": 112.0, "l": 150.0, "xl": 196.0}   # letter size in board units
INKS = {"black": bd.INK, "blue": bd.BLUE, "red": bd.RED, "orange": bd.ORANGE, "green": bd.GREEN, "purple": (124, 77, 190), "grey": (110, 116, 126)}
FILLS = {"yellow": (255, 216, 77), "orange": (250, 178, 92), "red": (240, 128, 110), "pink": (247, 178, 200), "purple": (190, 170, 232), "blue": (120, 178, 238),
         "light_blue": (176, 218, 247), "green": (150, 212, 130), "brown": (214, 178, 140), "grey": (214, 219, 226)}
CHALK_PAPER = (38, 52, 50)
MARGIN = 0.07                 # safe margin inside a zone, share of its size


def _norm(w: str) -> str:
    w = unicodedata.normalize("NFD", str(w).lower())
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in w if unicodedata.category(c) != "Mn"))


class Layout:
    def __init__(self, W: float, H: float):
        self.W, self.H = float(W), float(H)
        self.cw, self.ch = self.W / 3.0, self.H / 3.0

    def cells(self, zone) -> Tuple[int, int, int, int]:
        """-> (col0, row0, col1, row1) inclusive."""
        names = SPANS.get(zone, zone) if isinstance(zone, str) else zone
        names = [names] if isinstance(names, str) else list(names)
        cs = [ZONES[n] for n in names]
        return (min(c[0] for c in cs), min(c[1] for c in cs), max(c[0] for c in cs), max(c[1] for c in cs))

    def rect(self, cells) -> Tuple[float, float, float, float]:
        c0, r0, c1, r1 = cells
        x0, y0, x1, y1 = c0 * self.cw, r0 * self.ch, (c1 + 1) * self.cw, (r1 + 1) * self.ch
        mx, my = MARGIN * self.cw, MARGIN * self.ch
        return (x0 + mx, y0 + my, x1 - mx, y1 - my)

    def cells_of_box(self, box) -> Tuple[int, int, int, int]:
        x0, y0, x1, y1 = box
        f = lambda v, s: int(min(2, max(0, math.floor(v / s))))      # noqa: E731
        return (f(x0 + 1, self.cw), f(y0 + 1, self.ch), f(x1 - 1, self.cw), f(y1 - 1, self.ch))

    def window(self, c0: int, r0: int) -> Tuple[float, float, float]:
        return (c0 * self.cw, r0 * self.ch, 2 * self.cw)


def _union(a, b):
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def _edge_point(box, towards, gap: float):
    """Where the line from the box's centre towards a point leaves the box (plus a gap)."""
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    dx, dy = towards[0] - cx, towards[1] - cy
    n = math.hypot(dx, dy) or 1.0
    hx, hy = (box[2] - box[0]) / 2 + gap, (box[3] - box[1]) / 2 + gap
    t = min(hx / abs(dx) if dx else 1e9, hy / abs(dy) if dy else 1e9, 0.42)       # never past the middle of the way
    del n
    return (cx + dx * t, cy + dy * t)


def compile_board(items_in: List[Dict[str, Any]], anchors: Dict[str, float], dur: float, size_units: Tuple[float, float], scale: float, load: Callable[[str], Dict[str, Any]], *,
                  hand: str = "neat", tool: str = "marker", chalk: bool = False, camera: str = "auto", pad: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0),
                  frame_aspect: Optional[float] = None, tail: float = 0.0) -> Tuple[bd.Board, bd.Camera, Dict[str, Any]]:
    """-> (board, camera, report). Deterministic: the same items, anchor times, size and scale give the same board on any machine.
    `anchors`: item id -> scene-local time its narration word starts (items without one are drawn right after the previous item). `size_units`: the board's
    width and height in board units (the content box). `scale`: raster pixels per unit. `pad`: paper around the content (left, top, right, bottom, units). `tail`: seconds at the end of the
    scene by which everything, the pull-back included, is over (the last scene of a big board then pulls back over all its panels)."""
    dur = max(2.0, dur - tail)
    L = Layout(size_units[0], size_units[1])
    b = bd.Board(int(round(L.W + pad[0] + pad[2])), int(round(L.H + pad[1] + pad[3])), scale, paper=CHALK_PAPER if chalk else bd.PAPER, origin=(pad[0], pad[1]))
    hand_default, tool_default = hand, tool
    warnings: List[str] = []
    out_size = (frame_aspect or (L.W / L.H), 1.0)

    def ink(name, default="black"):
        c = INKS.get(name or default, INKS["black"])
        if chalk:
            return (238, 238, 230) if (name or default) == "black" else tuple(int(v + (255 - v) * 0.45) for v in c)
        return c

    # ------------------------------------------------------------ 1. geometry
    items = [dict(it) for it in items_in]
    by_id: Dict[str, Dict[str, Any]] = {}
    zone_draws: Dict[Tuple[int, int, int, int], List[str]] = {}
    for it in items:
        if "draw" in it and "zone" in it:
            zone_draws.setdefault(L.cells(it["zone"]), []).append(it["id"])
    # an item may point at one that comes later in the list (an arrow drawn before its target): geometry is resolved in dependency order, timing keeps the list order
    pending = list(items)
    for _ in range(6):
        later = []
        for it in pending:
            try:
                if _ == 0 and "near" in it:
                    raise KeyError(it["near"])           # things placed beside others wait until every zone item is placed, so they can avoid them all
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
                            frac = DRAW_SIZE[it.get("size", "xs")]
                            hmax = frac * min(L.cw, L.ch)
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
                            hmax = DRAW_SIZE[it.get("size", "m")] * min(L.cw, L.ch) * (1 - 2 * MARGIN)
                            k = min(hmax / pkg["h"], slot_w * 0.96 / pkg["w"])
                            w, h = pkg["w"] * k, pkg["h"] * k
                            dx, dy = it.get("shift", [0, 0])
                            x, y = x0 + (slot_w - w) / 2 + dx * slot_w, y0 + (y1 - y0 - h) / 2 + dy * (y1 - y0)
                        g.update(kind="draw", pkg=pkg, k=k, box=(x, y, x + w, y + h), cells=cells)
                if "chart" in it:
                    cells = L.cells(it["zone"])
                    g.update(kind="chart", cells=cells, **_chart(it, L.rect(cells), hand_default, _seed(it["id"])))
                elif "write" in it:
                    hand, tool = it.get("hand", hand_default), it.get("tool", tool_default)
                    size = TEXT_SIZE[it["size"]] if isinstance(it.get("size"), str) else float(it.get("size", TEXT_SIZE["m"]))
                    if "near" in it:
                        tb = by_id[it["near"]]["box"]
                        cells = by_id[it["near"]]["cells"]
                        blk = wr.layout(it["write"], hand, size, max_width=L.cw * 0.95, align="center", seed=_seed(it["id"]))
                        x, y = _free_side(tb, blk["w"], blk["h"], it.get("side", "below"), 0.12 * blk["size"], by_id, L)
                    else:
                        cells = L.cells(it["zone"])
                        x0, y0, x1, y1 = L.rect(cells)
                        align = it.get("align") or ("left" if "\n" in it["write"] else "center")
                        blk = wr.layout(it["write"], hand, size, max_width=x1 - x0, max_height=y1 - y0, align=align, seed=_seed(it["id"]))
                        x = x0 if align == "left" else x0 + (x1 - x0 - blk["w"]) / 2
                        va = it.get("valign", "middle")
                        y = y0 if va == "top" else (y1 - blk["h"] if va == "bottom" else y0 + (y1 - y0 - blk["h"]) / 2)
                        dx, dy = it.get("shift", [0, 0])
                        x, y = x + dx * (x1 - x0), y + dy * (y1 - y0)
                    g.update(kind="write", blk=blk, origin=(x, y), box=(x, y + 0.1 * blk["size"], x + blk["w"], y + blk["h"]), cells=cells, hand=hand, tool=tool)
                elif "connect" in it:
                    a, c = by_id[it["from"]], by_id[it["to"]]
                    ca, cc = _centre(a["box"]), _centre(c["box"])
                    p0, p1 = _edge_point(a["box"], cc, it.get("gap", 34.0)), _edge_point(c["box"], ca, it.get("gap", 34.0))
                    g.update(kind="connect", strokes=_connector(it, p0, p1), cells=_cells_union(a["cells"], c["cells"]))
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
                        s = (box[3] - box[1]) * 0.8
                        side = it.get("side", "left")
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
    for i, a in enumerate(solid):
        for c in solid[i + 1:]:
            ox = min(a["box"][2], c["box"][2]) - max(a["box"][0], c["box"][0])
            oy = min(a["box"][3], c["box"][3]) - max(a["box"][1], c["box"][1])
            if ox > 12 and oy > 12 and ox * oy > 0.06 * min(_area(a["box"]), _area(c["box"])):
                warnings.append(f"{a['id']} and {c['id']} overlap")
        if a["box"][0] < 0 or a["box"][1] < 0 or a["box"][2] > L.W or a["box"][3] > L.H:
            warnings.append(f"{a['id']} leaves the board")

    # ------------------------------------------------------------ 2. timing
    ops: List[Dict[str, Any]] = []
    for g in geo:
        it = g["it"]
        anchor = anchors.get(g["id"])
        if g["kind"] == "draw":
            pen = sum(core.length_of(s) for s in g["pkg"]["strokes"]) * g["k"]
            ops.append({"g": g, "nat": float(np.clip(pen / PEN_SPEED, 0.45, 2.6)), "anchor": anchor, "stretch": True})
        elif g["kind"] == "write":
            blk, tool, hand = g["blk"], g["tool"], g["hand"]
            # a written block ENDS on its word; its words are written back to back just before it (the engine gives one cue per item, not per written word)
            block_ops = [{"g": g, "word": wi, "nat": max(0.12, wr.write_time(w["strokes"], tool, blk["size"], hand)), "anchor": None, "stretch": False} for wi, w in enumerate(blk["words"])]
            if anchor is not None and block_ops:
                t = anchor
                for o in reversed(block_ops):
                    o["anchor"] = t
                    t -= o["nat"] * 1.05 + 0.05
            ops += block_ops
        elif g["kind"] == "chart":
            pen = sum(core.length_of(s) for s in g["strokes"])
            ops.append({"g": g, "nat": float(np.clip(pen / PEN_SPEED, 0.7, 3.0)), "anchor": anchor, "stretch": True})
            ops += [{"g": g, "text": ti, "word": wi, "nat": max(0.12, wr.write_time(w["strokes"], "pen", blk["size"], hand_default)), "anchor": None, "stretch": False}
                    for ti, (blk, _) in enumerate(g["texts"]) for wi, w in enumerate(blk["words"])]
        else:
            pen = sum(core.length_of(s) for s in g["strokes"])
            ops.append({"g": g, "nat": float(np.clip(pen / PEN_SPEED, 0.3, 1.8)), "anchor": anchor, "stretch": g["kind"] == "connect"})
    prev_end = 0.3
    for o in ops:
        nat = o["nat"]
        if o["anchor"] is None:
            start, end = prev_end + GAP, prev_end + GAP + nat
            o["how"] = "after the previous"
        else:
            end = o["anchor"] + 0.15
            start, o["how"] = end - nat, "on the word"
            lo = prev_end + (0.05 if "word" in o and o["word"] > 0 else GAP)
            if start < lo:
                fast = nat / 1.6
                if end - fast >= lo:
                    start, o["how"] = lo, "faster pen"
                else:
                    start, end, o["how"] = lo, lo + fast, "late"
            elif o["stretch"]:                                   # idle time before this item: draw it more slowly instead of waiting
                start = max(lo, end - min(nat * 2.4, 3.0))
        o["start"], o["end"] = start, end
        prev_end = end
    # Everything must be on the board before the scene ends (the pull-back and a moment to read it included): whatever runs past is brought forward and sped up.
    limit = max(1.0, dur - (1.9 if camera != "static" else 0.5))
    over = max((o["end"] for o in ops), default=0.0)
    if over > limit:
        t_first = min(o["start"] for o in ops)
        k_ = (limit - t_first) / max(over - t_first, 1e-6)
        for o in ops:
            o["start"], o["end"] = t_first + (o["start"] - t_first) * k_, t_first + (o["end"] - t_first) * k_
        warnings.append(f"items compressed {k_:.2f}x to fit the scene")
    last_ink = max((o["end"] for o in ops), default=0.0)

    # ------------------------------------------------------------ 3. rasterise and place
    fills_after: List[Tuple[float, Dict[str, Any]]] = []
    for o in ops:
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
                        d = float(np.clip(area_u / 260000.0, 0.22, 0.6))
                        b.place_under(fa, g["box"][0], g["box"][1], col, tf, tf + d, opacity=0.6 if chalk else 0.92, tip_colour=tuple(int(v * 0.82) for v in col), tip_size=1.0)
                        tf += d + 0.05
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
                b.place_under(fa, x0_, y0_, col, tf, tf + 0.3, opacity=0.6 if chalk else 0.92, tip_colour=tuple(int(v * 0.82) for v in col), tip_size=1.0)
                tf += 0.34
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
                b.place(core.raster_strokes(bx, scale), bx["x"], bx["y"], ink("grey"), t1 + 0.1, t1 + 0.6)
        elif g["kind"] == "mark" and g["mark"] == "highlight":
            box_h = g["box"][3] - g["box"][1]
            q = core.stroke_package(g["strokes"], it.get("width", 70.0), pressure=0.03)
            a = core.svg_alpha(q["ink"], q["w"], q["h"], scale)
            col = FILLS.get(it.get("color", "yellow"), FILLS["yellow"])
            b.place_under(a, q["x"], q["y"], col, t0, t1, opacity=0.75, strokes=[s * scale for s in q["strokes"]], tip_colour=col, tip_size=1.1, width=it.get("width", 70.0) * scale)
            del box_h
        else:
            width = LINE * (it.get("width", 0.9))
            q = core.stroke_package(g["strokes"], width, seed=_seed(g["id"]))
            b.place(core.raster_strokes(q, scale), q["x"], q["y"], ink(it.get("color"), "blue" if g["kind"] == "connect" else "red"), t0, t1)
    b.finish()

    # ------------------------------------------------------------ 4. camera: 2x2-zone windows, no cut objects, final pull-back on the content
    content = None
    for g in geo:
        content = g["box"] if content is None else _union(content, g["box"])
    cam_mode = camera
    final_view = _fit_view(content, L, out_size)
    wins = [(c, r) for r in (0, 1) for c in (0, 1)]

    def inside(cells, win):
        return win[0] <= cells[0] and cells[2] <= win[0] + 1 and win[1] <= cells[1] and cells[3] <= win[1] + 1

    def clean(win) -> bool:
        """A close view is only used if it cuts NO drawing or text of the board at its edge (each is wholly in the window or wholly out)."""
        wx, wy, ww = L.window(*win)
        wh = 2 * L.ch
        for g_ in solid:
            bx = g_["box"]
            ix, iy = min(bx[2], wx + ww) - max(bx[0], wx), min(bx[3], wy + wh) - max(bx[1], wy)
            frac = (max(ix, 0.0) * max(iy, 0.0)) / _area(bx)
            if 0.03 < frac < 0.97:
                return False
        return True

    seq = [(o["start"], o["g"]["cells"]) for o in ops]
    moves: List[Tuple[float, Any]] = []          # (time the view is needed by, window or "all")
    cur: Any = None
    if cam_mode == "static":
        cur = "all"
    for i, (ts, cells) in enumerate(seq):
        if cam_mode == "static":
            break
        if cur is not None and cur != "all" and inside(cells, cur):
            continue
        cands = [w for w in wins if inside(cells, w) and clean(w)]
        if not cands:
            nxt: Any = "all"
        else:
            look = [c for _, c in seq[i:i + 7]]
            nxt = max(cands, key=lambda w: (sum(inside(c, w) for c in look), -abs(w[0] - (cur[0] if isinstance(cur, tuple) else w[0])) - abs(w[1] - (cur[1] if isinstance(cur, tuple) else w[1]))))
            if cur == "all" and (len(look) < 2 or sum(inside(c, nxt) for c in look[:3]) < min(3, len(look))):   # (nor zoom in for one last mark, only to pull back again)
                continue                           # stay wide while the next items jump around
        if nxt != cur:
            moves.append((ts, nxt))
            cur = nxt

    def view(v):
        return final_view if v == "all" else L.window(*v)

    first = view(moves[0][1]) if moves else final_view
    cam = bd.Camera(first)
    prev_t = 0.0
    for k, (ts, v) in enumerate(moves[1:], 1):
        d = 1.15
        t0 = max(prev_t + 0.2, ts - 0.85)
        cam.move(t0, t0 + d, view(v))
        prev_t = t0 + d
    end_ink = max([last_ink] + [o.get("fill_end", 0) for o in ops])
    if cam_mode != "static" and cur != "all":
        t0 = min(max(prev_t + 0.2, end_ink + 0.3), max(prev_t + 0.2, dur - 1.6))      # the pull-back always completes inside the scene
        cam.move(t0, t0 + 1.4, final_view)
    merged: List[List[float]] = []
    for s_, e_ in sorted([(o["start"], o.get("fill_end", o["end"])) for o in ops]):
        if merged and s_ <= merged[-1][1] + 0.05:
            merged[-1][1] = max(merged[-1][1], e_)
        else:
            merged.append([s_, e_])
    busy = sum(e_ - s_ for s_, e_ in merged)
    gaps = [b_[0] - a_[1] for a_, b_ in zip(merged, merged[1:])]
    report = {"items": len(geo), "pen_ops": len(ops), "pen_busy_share": round(busy / max(dur, 1e-6), 3), "longest_idle_s": round(max(gaps, default=0.0), 2),
              "late": [[o["g"]["id"], round(o["end"] - (o["anchor"] + 0.15), 2)] for o in ops if o["how"] == "late"], "camera_moves": len(cam.moves), "warnings": warnings,
              "boxes": {g["id"]: [round(v, 1) for v in g["box"]] for g in geo}, "kinds": {g["id"]: g["kind"] for g in geo}}
    return b, cam, report


def _chart(it: Dict[str, Any], rect, hand: str, seed: int) -> Dict[str, Any]:
    """Numbers drawn by hand: `bars` (a baseline and one outlined, coloured bar per value, its value above, its label below) or `line` (two axes and a rising
    or falling line with an arrow head). -> the pen strokes, the bar areas to colour, the texts and the box."""
    x0, y0, x1, y1 = rect
    vals, labels = [float(v) for v in it["values"]], list(it.get("labels") or [])
    n = len(vals)
    lab = min(60.0, (y1 - y0) * 0.11)
    has_labels = any(labels)
    yb = y1 - (lab * 1.5 if has_labels else 8.0)
    top = y0 + lab * 1.5
    slot = (x1 - x0) / n
    vmax = max(vals) or 1.0
    strokes: List[np.ndarray] = []
    bars, texts = [], []

    def text(s_: str, cx: float, y: float, size: float, k: int):
        blk = wr.layout(s_, hand, size, max_width=slot * 0.96, align="center", seed=seed + k)
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
            text(f"{v:,.10g}", (bx0 + bx1) / 2, by - lab * 1.35, lab, 100 + k)
    for k, s_ in enumerate(labels[:n]):
        if s_:
            text(s_, x0 + slot * (k + 0.5), yb + lab * 0.1, lab * 0.9, k)
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
        if hit < 1.0:
            return x, y
        if best is None or hit < best[0]:
            best = (hit, x, y)
    return best[1], best[2]


def _connector(it, p0, p1) -> List[np.ndarray]:
    style, n = it.get("connect", "arrow"), int(it.get("count", 1))
    seed = _seed(it["id"])
    d = np.array(p1) - np.array(p0)
    Ln = float(np.hypot(*d)) or 1.0
    nrm = np.array([-d[1], d[0]]) / Ln
    out: List[np.ndarray] = []
    for k in range(n):
        off = nrm * (k - (n - 1) / 2) * it.get("spread", 120.0)
        a, c = tuple(np.array(p0) + off), tuple(np.array(p1) + off)
        if style == "wavy":
            out += pr.wavy_arrow(a, c, waves=max(1.5, Ln / 190.0), seed=seed + k)
        elif style == "dashed":
            ds = pr.dashes(a, c, n=max(3, int(Ln / 120)), seed=seed + k)
            out += ds + ([pr.head(np.concatenate(ds[-2:]), 44.0, seed=seed)] if it.get("head", True) else [])
        elif style == "line":
            out += [pr.line(a, c, seed + k)]
        else:
            bend = it.get("bend", 0.14) * Ln
            mid = (np.array(a) + np.array(c)) / 2 + nrm * bend
            out += pr.arrow([a, tuple(mid), c], seed=seed + k, size=it.get("head_size", 48.0)) if it.get("head", True) else [pr.path([a, tuple(mid), c], seed + k)]
    return out


def _fit_view(content, L, out_size) -> Tuple[float, float, float]:
    """The pull-back: everything drawn, with a margin, in the frame's aspect, inside the board."""
    if content is None:
        return (0.0, 0.0, float(L.W))
    asp = out_size[0] / out_size[1]
    m = 0.05 * L.W
    x0, y0, x1, y1 = content[0] - m, content[1] - m, content[2] + m, content[3] + m
    w = max(x1 - x0, (y1 - y0) * asp)
    w = min(w, L.W, L.H * asp)
    h = w / asp
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    vx = min(max(cx - w / 2, 0.0), L.W - w)
    vy = min(max(cy - h / 2, 0.0), L.H - h - 1e-6)
    return (vx, max(vy, 0.0), w)
