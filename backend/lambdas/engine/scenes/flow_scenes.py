"""The `diagram` scene, styled. Four looks (`style`): cards (default), pills, ladder, stack; the colour comes from `accent`.

One layout engine (the same layering as before: `viz_scenes.layout_diagram`, so `sync.diagram_order` still names the reveal order) and four node looks.
Connectors are smooth curves that DRAW ON toward each new node, land with an arrowhead that bounces in, and then carry a slow travelling pulse; the node being
narrated (reveal time = `props["cues"]`) is lit while earlier ones settle back. Before the voice reaches a node its slot is already there as a faint ghost,
so the frame is never empty and the structure reads at a glance. More than 4 layers wraps into a two-row snake (the second row runs right to left).
"""
import math
from typing import Any, Dict, List, Optional, Tuple

from ..canvas import Canvas, with_alpha
from ..easing import ease_in_out_cubic, ease_out_back, ease_out_cubic, progress, reveal_times
from ..theme import Theme
from .base import SceneCtx
from .style_kit import (
    LEFT, RIGHT, Pal, area, backdrop, clamp_first, draw_lines, emphasis_of, fit_lines, flow_style, focus, glow_blob, icon, icon_for, mix, pal_for, paste_sprite, pop,
    soft_shadow, sprite, title_block,
)
from .viz_scenes import MAX_NODES, layout_diagram

Rect = Tuple[float, float, float, float]
W_AREA = RIGHT - LEFT


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ----------------------------------------------------------------------------- layout
def _model(props: Dict[str, Any]):
    nodes = [n for n in (props.get("nodes") or []) if isinstance(n, dict) and "id" in n][:MAX_NODES]
    ids = [str(n["id"]) for n in nodes]
    edges = [e for e in (props.get("edges") or []) if isinstance(e, (list, tuple)) and len(e) >= 2]
    layer = layout_diagram(nodes, edges)
    n_layers = (max(layer.values()) + 1) if layer else 1
    order = [str(n["id"]) for li in range(n_layers) for n in nodes if layer[str(n["id"])] == li]
    by_id = {str(n["id"]): n for n in nodes}
    good = [(str(e[0]), str(e[1]), str(e[2]) if len(e) >= 3 and e[2] else "") for e in edges if str(e[0]) in by_id and str(e[1]) in by_id and str(e[0]) != str(e[1])]
    return nodes, by_id, layer, n_layers, order, good


def effective_style(style: str, n_layers: int) -> str:
    return "cards" if style in ("ladder", "stack") and n_layers > 5 else style


def layout(cv: Canvas, style: str, nodes, layer, n_layers: int, edges, top: float, bot: float) -> Tuple[Dict[str, Rect], str, str]:
    """-> (rect per node id, variant 'col'|'row'|'pill', effective style)."""
    style = effective_style(style, n_layers)
    cols: Dict[int, List[str]] = {}
    for n in nodes:
        cols.setdefault(layer[str(n["id"])], []).append(str(n["id"]))
    max_col = max(len(v) for v in cols.values())
    lw = max((cv.measure(l, "semibold", 26) for _, _, lab in edges if lab for l in cv.wrap(lab, "semibold", 26, 190)[:2]), default=0.0)
    avail = bot - top
    pos: Dict[str, Rect] = {}
    if style == "stack":
        gap = 64.0 if n_layers <= 3 else 50.0 if n_layers == 4 else 38.0
        h = _clamp((avail - gap * (n_layers - 1)) / n_layers, 78, 124)
        total = h * n_layers + gap * (n_layers - 1)
        y0 = top + (avail - total) / 2
        wgap = 40
        for li in range(n_layers):
            ids = cols.get(li, [])
            w = min(1000.0, (W_AREA - wgap * (len(ids) - 1)) / max(1, len(ids))) if len(ids) == 1 else min(760.0, (W_AREA - wgap * (len(ids) - 1)) / len(ids))
            row_w = w * len(ids) + wgap * (len(ids) - 1)
            for k, nid in enumerate(ids):
                pos[nid] = (LEFT + (W_AREA - row_w) / 2 + k * (w + wgap), y0 + li * (h + gap), w, h)
        return pos, "row", style
    snake = n_layers > 4
    per_row = math.ceil(n_layers / 2) if snake else n_layers
    nrows = 2 if snake else 1
    g = _clamp(max(120.0, lw + 80), 120, 250) if not snake else _clamp(max(100.0, lw + 70), 100, 200)
    if style == "pills":
        w = _clamp((W_AREA - g * (per_row - 1)) / per_row, 240, 520)
        h = 132.0
        vgap = 36.0
    elif style == "ladder":
        g = _clamp(lw + 70 if lw else 110, 110, 190)
        w = _clamp((W_AREA - g * (n_layers - 1)) / n_layers, 220, 440)
        h = 150.0
        vgap = 30.0
    else:
        w = _clamp((W_AREA - g * (per_row - 1)) / per_row, 220, 470)
        vgap = 40.0
        if snake:
            h = _clamp((avail - 70 - 2 * vgap * (max_col - 1)) / (2 * max_col), 80, 210)
        else:
            h = _clamp((avail - vgap * (max_col - 1)) / max_col, 80, max(190.0, min(360.0, w * 1.08)))
    if style == "pills" and max_col * h + vgap * (max_col - 1) > avail:
        h = _clamp((avail - vgap * (max_col - 1)) / max_col, 84, 132)
    if style == "ladder":
        h = _clamp(min(h, (avail - vgap * (max_col - 1)) / max_col), 80, 160)
    row_gap = 70.0
    total_h = nrows * (max_col * h + vgap * (max_col - 1)) + (nrows - 1) * row_gap
    step = 0.0
    if style == "ladder" and n_layers > 1:
        step = _clamp((avail - (max_col * h + vgap * (max_col - 1))) / (n_layers - 1), 0, 140)
        total_h = max_col * h + vgap * (max_col - 1) + step * (n_layers - 1)
    y_start = top + max(0.0, (avail - total_h)) / 2
    for li in range(n_layers):
        row = li // per_row if snake else 0
        idx = li % per_row if snake else li
        if snake and row == 1:
            idx = per_row - 1 - idx
        row_w = w * (per_row if snake else n_layers) + g * ((per_row if snake else n_layers) - 1)
        x_row0 = LEFT + (W_AREA - row_w) / 2
        ids = cols.get(li, [])
        col_h = len(ids) * h + vgap * (len(ids) - 1)
        full_h = max_col * h + vgap * (max_col - 1)
        for k, nid in enumerate(ids):
            x = x_row0 + idx * (w + g)
            if style == "ladder":
                base_y = y_start + (n_layers - 1 - li) * step
                y = base_y + (full_h - col_h) / 2 + k * (h + vgap)
            else:
                y = y_start + row * (full_h + row_gap) + (full_h - col_h) / 2 + k * (h + vgap)
            pos[nid] = (x, y, w, h)
    variant = "pill" if style == "pills" else ("col" if (style == "cards" and h >= 190) else "row")
    return pos, variant, style


# ----------------------------------------------------------------------------- connectors
def _bez(p0, p1, p2, p3, n: int = 44) -> List[Tuple[float, float]]:
    out = []
    for i in range(n + 1):
        t = i / n
        u = 1 - t
        out.append((u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0], u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]))
    return out


def route(ra: Rect, rb: Rect, back: bool, vertical_mode: bool) -> List[Tuple[float, float]]:
    ax, ay, aw, ah = ra
    bx, by, bw, bh = rb
    acx, acy, bcx, bcy = ax + aw / 2, ay + ah / 2, bx + bw / 2, by + bh / 2
    dx, dy = bcx - acx, bcy - acy
    if back:
        if vertical_mode:
            xr = max(ax + aw, bx + bw) + 70
            return _bez((ax + aw, acy), (xr, acy), (xr, bcy), (bx + bw + 4, bcy))
        yb = max(ay + ah, by + bh) + 64
        return _bez((acx, ay + ah), (acx, yb), (bcx, yb), (bcx, by + bh + 4))
    if abs(dy) > max(ah, bh) * 1.1 and abs(dx) < (aw + bw) * 0.45:
        s = (acx, ay + ah if dy > 0 else ay)
        e = (bcx, by - 4 if dy > 0 else by + bh + 4)
        k = abs(e[1] - s[1]) * 0.5
        sg = 1 if dy > 0 else -1
        return _bez(s, (s[0], s[1] + sg * k), (e[0], e[1] - sg * k), e)
    if dx >= 0:
        s, e = (ax + aw, acy), (bx - 4, bcy)
        k = max(40.0, (e[0] - s[0]) * 0.5)
        return _bez(s, (s[0] + k, s[1]), (e[0] - k, e[1]), e)
    s, e = (ax, acy), (bx + bw + 4, bcy)
    k = max(40.0, (s[0] - e[0]) * 0.5)
    return _bez(s, (s[0] - k, s[1]), (e[0] + k, e[1]), e)


def _lengths(pts) -> List[float]:
    acc = [0.0]
    for i in range(1, len(pts)):
        acc.append(acc[-1] + math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]))
    return acc


def point_at(pts, u: float) -> Tuple[float, float, float]:
    acc = _lengths(pts)
    tgt = acc[-1] * u
    for i in range(1, len(pts)):
        if acc[i] >= tgt:
            seg = acc[i] - acc[i - 1] or 1.0
            f = (tgt - acc[i - 1]) / seg
            x = pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * f
            y = pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * f
            return x, y, math.atan2(pts[i][1] - pts[i - 1][1], pts[i][0] - pts[i - 1][0])
    x, y = pts[-1]
    return x, y, math.atan2(pts[-1][1] - pts[-2][1], pts[-1][0] - pts[-2][0])


def _draw_edge(cv: Canvas, th: Theme, pal: Pal, pts, lt: float, t_src: float, t_dst: float, label: str, lab_size: float) -> None:
    acc = _lengths(pts)
    total = acc[-1]
    if total < 4:
        return
    lead = max(0.2, min(0.65, t_dst - t_src - 0.1))
    start = max(t_src + 0.1, t_dst - lead)
    dur = max(0.2, t_dst + 0.05 - start)
    p = ease_in_out_cubic(progress(lt, start, dur))
    trim = 16.0 / total                                   # the line stops short of the node: the arrowhead sits in the gap
    body = []
    if p > 0:
        u_end = max(0.0, p - trim * p)
        n = max(2, int(len(pts) * u_end))
        sub = [point_at(pts, u_end * i / n)[:2] for i in range(n + 1)] if u_end > 0.004 else []
        for i in range(len(sub) - 1):
            col = mix(pal.c1, pal.c2, i / max(1, len(sub) - 1))
            cv.line([sub[i], sub[i + 1]], col + (255,), 6)
    if label and p > 0.55:
        mx, my, _ = point_at(pts, 0.5)
        la = ease_out_cubic(progress(lt, start + dur * 0.55, 0.35))
        lines = cv.wrap(label, "semibold", lab_size, 190)[:2]
        tw = max(cv.measure(l, "semibold", lab_size) for l in lines)
        hh = len(lines) * lab_size * 1.15 + 18
        ww = tw + 34
        paste_sprite(cv, sprite(cv, ww, hh, hh / 2, pal.surface_hi if not pal.dark else (24, 22, 56, 255), border=pal.c1, border2=pal.c2, bw=2), mx, my, 0.9 + 0.1 * la, la)
        draw_lines(cv, mx, my, lines, "semibold", lab_size, with_alpha(th.text, la), anchor="mm", lh=1.15)
    land = start + dur
    if p >= 0.999:
        ap = progress(lt, land - 0.05, 0.32)
        s = 0.2 + 0.8 * ease_out_back(ap, 2.6)
        ex, ey, ang = point_at(pts, 1.0)
        size = 24 * s
        tip = (ex - math.cos(ang) * 2, ey - math.sin(ang) * 2)
        base = (tip[0] - math.cos(ang) * size, tip[1] - math.sin(ang) * size)
        nx, ny = -math.sin(ang), math.cos(ang)
        cv.polygon([tip, (base[0] + nx * size * 0.62, base[1] + ny * size * 0.62), (base[0] - nx * size * 0.62, base[1] - ny * size * 0.62)], pal.c2 + (int(255 * min(1.0, ap * 3)),))
        if ap >= 1.0:                                      # the pulse: one soft dot travelling the connector, slowly
            u = ((lt - land) / 2.6) % 1.0
            dx_, dy_, _ = point_at(pts, u)
            al = math.sin(math.pi * u) ** 0.7
            cv.ellipse(dx_, dy_, 17, 17, fill=with_alpha(pal.dot, 0.18 * al))
            cv.ellipse(dx_, dy_, 8.5, 8.5, fill=with_alpha(pal.dot, 0.95 * al))


# ----------------------------------------------------------------------------- nodes
def _node(cv: Canvas, th: Theme, pal: Pal, rect: Rect, variant: str, label: str, name: str, lines: List[str], size: float, a: float, e: float, f: float, strong: bool, ghost: float) -> None:
    x, y, w, h = rect
    cx, cy = x + w / 2, y + h / 2
    r = h / 2 if variant == "pill" else _clamp(h * 0.16, 22, 34)
    base = sprite(cv, w, h, r, pal.surface, border=pal.border, bw=2)
    if ghost > 0.01:
        paste_sprite(cv, base, cx, cy, 1.0, ghost * 0.3)
    if a <= 0.01:
        return
    fe = max(f, 1.0 if strong else 0.0)
    sc = 0.84 + 0.16 * e + 0.03 * fe
    cy2 = cy + (1 - min(1.0, e)) * 24
    soft_shadow(cv, cx - w / 2, cy2 - h / 2, w, h, r, th.shadow_alpha * a * 0.85, blur=28, dy=16)
    soft_shadow(cv, cx - w / 2, cy2 - h / 2, w, h, r, 0.42 * fe * a, pal.c1, blur=34, dy=4)
    paste_sprite(cv, base, cx, cy2, sc, a)
    paste_sprite(cv, sprite(cv, w, h, r, (*pal.c1, 34), (*pal.c2, 34), pal.c1, pal.c2, 3), cx, cy2, sc, a * f)
    if strong:
        paste_sprite(cv, sprite(cv, w, h, r, pal.c1, pal.c2), cx, cy2, sc, a)
    ink = pal.ink if strong else th.text
    tcol = with_alpha(ink, a * (0.86 + 0.14 * fe))
    if variant == "col":
        tile = _clamp(h * 0.27, 62, 84)
        ty = cy2 - h / 2 * sc + 34 + tile / 2
        _tile(cv, pal, cx, ty, tile, name, a, fe, strong, sc)
        top_text = ty + tile / 2 + 18
        mid = (top_text + (cy2 + h / 2 * sc - 22)) / 2
        draw_lines(cv, cx, mid, lines, "semibold", size, tcol, anchor="mm", lh=1.16)
    else:
        tile = _row_tile(variant, w, h)
        tx = x + (w - w * sc) / 2 + (h - tile) / 2 if variant == "pill" else x + (w - w * sc) / 2 + 18
        _tile(cv, pal, tx + tile / 2, cy2, tile, name, a, fe, strong, sc, circle=variant == "pill")
        text_x0 = tx + tile + 16
        text_w = x + w - 18 - text_x0
        draw_lines(cv, text_x0 + text_w / 2 - 0, cy2, lines, "semibold", size, tcol, anchor="mm", lh=1.14)


def _row_tile(variant: str, w: float, h: float) -> float:
    return _clamp(h - 36, 54, 96) if variant == "pill" else _clamp(min(h * 0.5, w * 0.2), 48, 84)


def _tile(cv: Canvas, pal: Pal, cx: float, cy: float, tile: float, name: str, a: float, fe: float, strong: bool, sc: float, circle: bool = False) -> None:
    r = tile / 2 if circle else tile * 0.3
    soft = sprite(cv, tile, tile, r, (*pal.c1, 70), (*pal.c2, 70))
    full = sprite(cv, tile, tile, r, pal.c1, pal.c2)
    paste_sprite(cv, soft, cx, cy, sc, a * (0.0 if strong else 1.0))
    paste_sprite(cv, full, cx, cy, sc, a * (1.0 if strong else 0.55 + 0.45 * fe))
    ink = pal.ink
    icon(cv, cx, cy, name, tile * 0.5, with_alpha(ink, a), sc)


# ----------------------------------------------------------------------------- scene
def draw(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    nodes, by_id, layer, n_layers, order, edges = _model(props)
    pal = pal_for(th, props.get("accent"))
    backdrop(cv, th, pal, lt)
    y = title_block(cv, th, pal, str(props.get("title", "")).strip(), lt) if props.get("title") else 90.0
    if not nodes:
        return
    top, bot = area(ctx, y + 6)
    pos, variant, style = layout(cv, flow_style(props), nodes, layer, n_layers, edges, top, bot)
    times = clamp_first(reveal_times(len(order), dur, props.get("cues"), first=0.12, last=0.78))
    t_of = {nid: times[i] for i, nid in enumerate(order)}
    rank = {nid: i for i, nid in enumerate(order)}
    emph_i = emphasis_of(props, len(nodes))
    strong_id = str(nodes[emph_i]["id"]) if emph_i is not None else None
    # one type size for every node, so the row reads as a set
    lab = {nid: str(by_id[nid].get("label") or nid) for nid in order}
    sizes, fits = [], {}
    for nid in order:
        x, yy, w, h = pos[nid]
        if variant == "col":
            tile = _clamp(h * 0.27, 62, 84)
            mw, ml, start, mh = w - 40, 3, _clamp(w * 0.14, 30, 60), h - 34 - tile - 18 - 22
        elif variant == "pill":
            mw, ml, start, mh = w - (h - _row_tile("pill", w, h)) / 2 - _row_tile("pill", w, h) - 16 - 18, 2, 46.0, h - 22
        else:
            mw, ml, start, mh = w - 18 - _row_tile("row", w, h) - 16 - 18, 2, _clamp(h * 0.4, 30, 54), h - 20
        fits[nid] = (mw, ml)
        sizes.append(fit_lines(cv, lab[nid], "semibold", mw, ml, start, 22, mh, 1.16)[0])
    size = min(sizes)
    # connectors under the nodes
    pos_row = {nid: pos[nid] for nid in pos}
    vertical = style == "stack"
    for a_id, b_id, label in edges:
        back = layer[b_id] <= layer[a_id]
        pts = route(pos_row[a_id], pos_row[b_id], back, vertical)
        faint = ease_out_cubic(progress(lt, 0.2, 0.7)) * 0.55
        if faint > 0.01:
            cv.line(pts, with_alpha(pal.track, faint), 4)
        _draw_edge(cv, th, pal, pts, lt, t_of[a_id], t_of[b_id], label, 26)
    for nid in order:
        a, e = pop(lt, t_of[nid], 0.62, 1.8)
        f = focus(times, lt, rank[nid])
        ghost = 1.0 - a
        mw, ml = fits[nid]
        lines = cv.wrap(lab[nid], "semibold", size, mw)[:ml]
        _node(cv, th, pal, pos[nid], variant, lab[nid], icon_for_node(props, by_id[nid], rank[nid], lab[nid]), lines, size, a, e, f, nid == strong_id, ghost)


def icon_for_node(props: Dict[str, Any], node: Dict[str, Any], i: int, label: str) -> str:
    from .style_kit import auto_icon, clean_icon

    v = clean_icon(node.get("icon")) if node.get("icon") else ""
    return v or auto_icon(label, i)
