import math
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from .. import numfmt
from ..canvas import Canvas, partial_polyline, with_alpha
from ..easing import ease_in_out_cubic, ease_out_back, ease_out_cubic, lerp, progress, reveal_times
from ..theme import Theme
from .base import SceneCtx, format_number, heading

MAX_NODES = 10


# ------------------------------------------------------------------ diagram
def layout_diagram(nodes: List[Dict[str, Any]], edges: List[List[Any]]) -> Dict[str, int]:
    """Longest-path layering (cycle-safe). Returns node id -> layer index."""
    ids = [str(n["id"]) for n in nodes]
    layer = {i: 0 for i in ids}
    clean = [(str(e[0]), str(e[1])) for e in edges if len(e) >= 2 and str(e[0]) in layer and str(e[1]) in layer and str(e[0]) != str(e[1])]
    for _ in range(len(ids)):
        changed = False
        for a, b in clean:
            if layer[b] < layer[a] + 1 and layer[a] + 1 < len(ids):
                layer[b] = layer[a] + 1
                changed = True
        if not changed:
            break
    return layer


def _diagram_geometry(cv: Canvas, props: Dict[str, Any], top: float, bottom: float):
    nodes = [n for n in (props.get("nodes") or []) if isinstance(n, dict) and "id" in n][:MAX_NODES]
    edges = [e for e in (props.get("edges") or []) if isinstance(e, (list, tuple)) and len(e) >= 2]
    layer = layout_diagram(nodes, edges)
    n_layers = (max(layer.values()) + 1) if layer else 1
    area_x0, area_x1 = 140, 1780
    gap = 130 if n_layers <= 4 else 90
    # Edge labels wrap to <=2 lines of <=190px, so a modest gap is enough and nodes stay big.
    label_w = max((max((cv.measure(l, "regular", 24) for l in cv.wrap(str(e[2]), "regular", 24, 190)), default=0.0)
                   for e in edges if len(e) >= 3 and e[2]), default=0.0)
    if label_w:
        gap = max(gap, min(label_w + 70, 250))
    big = 1.25 if n_layers <= 3 else 1.0
    node_w = min(340.0 * big, (area_x1 - area_x0 - gap * (n_layers - 1)) / n_layers)
    node_h = (104.0 if node_w > 230 else 92.0) * (big if node_w > 280 else 1.0)
    cols: Dict[int, List[Dict[str, Any]]] = {}
    for n in nodes:
        cols.setdefault(layer[str(n["id"])], []).append(n)
    max_col = max((len(v) for v in cols.values()), default=1)
    vgap = 36
    total_h_max = max_col * node_h + (max_col - 1) * vgap
    if total_h_max > bottom - top:  # compress
        node_h = max(70.0, ((bottom - top) - (max_col - 1) * vgap) / max_col)
    used_w = n_layers * node_w + (n_layers - 1) * gap
    x_start = (area_x0 + area_x1) / 2 - used_w / 2
    cy_mid = (top + bottom) / 2
    pos: Dict[str, Tuple[float, float]] = {}
    order: List[str] = []
    for li in range(n_layers):
        col = cols.get(li, [])
        col_h = len(col) * node_h + (len(col) - 1) * vgap
        for k, n in enumerate(col):
            x = x_start + li * (node_w + gap)
            y = cy_mid - col_h / 2 + k * (node_h + vgap)
            pos[str(n["id"])] = (x, y)
            order.append(str(n["id"]))
    return nodes, edges, pos, order, node_w, node_h, layer


def diagram_cues(props: Dict[str, Any], dur: float) -> List[float]:
    n = min(len(props.get("nodes") or []), MAX_NODES)
    return reveal_times(n, dur, props.get("cues"), first=0.12, last=0.78)


def _arrowhead(cv: Canvas, pts, color) -> None:
    ex, ey = pts[-1]
    px, py = pts[-2]
    ang = math.atan2(ey - py, ex - px)
    s = 18
    tip = (ex + math.cos(ang) * 12, ey + math.sin(ang) * 12)
    cv.polygon(
        [tip, (tip[0] - s * math.cos(ang - 0.45), tip[1] - s * math.sin(ang - 0.45)),
         (tip[0] - s * math.cos(ang + 0.45), tip[1] - s * math.sin(ang + 0.45))],
        fill=color,
    )


def _edge_label(cv: Canvas, th: Theme, text: str, run_a: float, run_b: float, y_line: float, alpha: float) -> None:
    lines = cv.wrap(text, "regular", 24, 190)[:2]
    tw = max(cv.measure(l, "regular", 24) for l in lines)
    lh = 28
    h = len(lines) * lh + 10
    lx = (run_a + run_b) / 2
    bottom = y_line - 14  # sits just above the arrow's final run
    cv.rrect(lx - tw / 2 - 10, bottom - h, tw + 20, h, 12, fill=with_alpha(th.bg_top, 0.8 * alpha))
    for i, l in enumerate(lines):
        cv.text(lx, bottom - h + 5 + i * lh + lh / 2, l, "regular", 24, with_alpha(th.text, alpha), anchor="mm")


def draw_diagram(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    """The styled flow (scenes/flow_scenes.py): `style` and `accent` props, the default look when they are missing or unknown."""
    from .flow_scenes import draw

    draw(cv, props, lt, dur, th, ctx)


# ------------------------------------------------------------------ chart
def _fmt(v: float, unit: str) -> str:
    dec = 0 if abs(v) >= 100 or float(v).is_integer() else 1 if abs(v) >= 10 else 2
    s = format_number(v, dec, abs(v) >= 1000)
    mark = "," if numfmt.current_language() == "es" else "."   # the video's decimal mark (the number is already written the way its language does)
    if mark in s:
        s = s.rstrip("0").rstrip(mark)
    if unit in ("$", "€", "£"):
        return unit + s
    return s + (unit if unit in ("%", "x") else (" " + unit if unit else ""))


def chart_cues(props: Dict[str, Any], dur: float) -> List[float]:
    return reveal_times(len(props.get("values") or []), dur, props.get("cues"), first=0.15, last=0.7)


def draw_chart(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    labels = [str(x) for x in (props.get("labels") or [])][:12]
    try:
        values = [float(v) for v in (props.get("values") or [])][: len(labels)]
    except (TypeError, ValueError):
        values = []
    n = min(len(labels), len(values))
    fr = ctx.frame
    land = fr.landscape
    ts = 1.15      # type scale of the small chart text (axis, categories, values): 24 px at 1080p was the smallest text of the landscape charts in the QA review
    top = heading(cv, th, str(props.get("title", "")), lt, y=ctx.top + 20, ctx=ctx) if props.get("title") else ctx.top + 50
    if n == 0:
        return
    unit = str(props.get("unit", ""))
    kind = str(props.get("kind", "bar"))
    if not land and kind != "line" and n > 5:     # many categories: one row each; up to five stay classic columns
        return _hbars(cv, props, ctx, lt, dur, th, labels, values, n, unit, top)
    x0, x1 = (200, 1760) if land else (fr.margin_x + 100, fr.W - fr.margin_x)
    y_top, y_base = top + 60, ctx.bottom - 70
    vmax = max(max(values[:n]), 0.0) or 1.0
    vmin = min(min(values[:n]), 0.0) if kind == "bar" else min(values[:n])
    if kind == "line":
        pad = (vmax - vmin) * 0.12 or 1
        vmin, vmax = vmin - pad, vmax + pad
    rng = (vmax - vmin) or 1.0

    def ypos(v: float) -> float:
        return y_base - (v - vmin) / rng * (y_base - y_top)

    # grid
    gp = ease_out_cubic(progress(lt, 0.0, 0.6))
    for k in range(5):
        gy = y_base - (y_base - y_top) * k / 4
        cv.line([(x0, gy), (x1, gy)], with_alpha(th.card_outline if th.name != "paper" else (31, 41, 55, 30), gp * (1.0 if k else 1.6)), 2, round_caps=False)
        if k:
            cv.text(x0 - 16, gy, _fmt(vmin + rng * k / 4, unit if unit != "%" else "%"), "regular", 24 * ts, with_alpha(th.muted, gp), anchor="rm")
    times = reveal_times(n, dur, props.get("cues"), first=0.15, last=0.7)
    slot = (x1 - x0) / n
    highlight = props.get("highlight")
    if kind == "line":
        pts = [(x0 + slot * (i + 0.5), ypos(values[i])) for i in range(n)]
        total_p = ease_in_out_cubic(progress(lt, times[0], max(0.8, times[-1] - times[0] + 0.5)))
        part = partial_polyline(pts, total_p)
        lab_w = max(cv.measure(l, "regular", 28 * ts) for l in labels[:n])
        stride = max(1, math.ceil((lab_w + 14) / slot))                      # thin the x labels (and values) when the slots are narrower than the words
        val_w = max(cv.measure(_fmt(v, unit), "semibold", 30 * ts) for v in values[:n])
        vstride = max(1, math.ceil((val_w + 12) / slot))
        if len(part) >= 2:
            cv.polygon(part + [(part[-1][0], y_base), (part[0][0], y_base)], with_alpha(th.accent, 0.16))
            cv.line(part, th.accent + (255,), 8)
        for i, (px, py) in enumerate(pts):
            dp = ease_out_back(progress(lt, times[i] + 0.1, 0.4), 2)
            if dp > 0:
                cv.ellipse(px, py, 13 * dp, 13 * dp, fill=th.accent2 + (255,), outline=(255, 255, 255, 255), width=3)
                if i % vstride == 0 or i == n - 1:
                    cv.text(px, py - 34, _fmt(values[i], unit), "semibold", 30 * ts, with_alpha(th.text, min(1, dp)), anchor="mb")
            if i % stride == 0:
                cv.text(px, y_base + 18, labels[i], "regular", 28 * ts, with_alpha(th.muted, gp), anchor="ma")
        return
    bw = min(150.0 if land else 190.0, slot * 0.56)
    for i in range(n):
        p = ease_out_cubic(progress(lt, times[i], 0.9))
        cx = x0 + slot * (i + 0.5)
        zero_y = ypos(0.0 if vmin < 0 else vmin)
        top_y = zero_y + (ypos(values[i]) - zero_y) * p
        col = th.accent2 if (highlight is not None and int(highlight) == i) else th.accent
        a, b = sorted((zero_y, top_y))
        if b - a > 1:
            cv.shadow(cx - bw / 2, a, bw, b - a, 14, blur=14, dy=8, alpha=th.shadow_alpha * 0.8 * p)
            cv.rrect(cx - bw / 2, a, bw, b - a, 14, fill=col + (255,))
        shown = _fmt(values[i] * p, unit)
        cv.text(cx, a - 14, shown, "bold", 34 * ts, with_alpha(th.text, min(1.0, p * 1.6)), anchor="mb")
        cv.text(cx, y_base + 18, labels[i], "regular", 28 * ts, with_alpha(th.muted, gp), anchor="ma")


def _hbars(cv: Canvas, props: Dict[str, Any], ctx: SceneCtx, lt: float, dur: float, th: Theme, labels, values, n: int, unit: str, top: float) -> None:
    """Bar chart for tall and square frames: one row per category (name above its bar, value at the bar's end), so any number of categories reads."""
    fr = ctx.frame
    x0, x1 = fr.margin_x, fr.W - fr.margin_x
    y_top, y_bot = top + 8, ctx.bottom - 6
    pitch = (y_bot - y_top) / n
    lab_size = max(24.0, min(40.0, pitch * 0.34))
    val_size = max(28.0, min(44.0, pitch * 0.42))
    bar_h = max(18.0, min(70.0, pitch * 0.42))
    val_w = max(cv.measure(_fmt(v, unit), "bold", val_size) for v in values[:n]) + 22
    bar_w = (x1 - x0) - val_w
    vmax = max(max(values[:n]), 0.0) or 1.0
    vmin = min(min(values[:n]), 0.0)
    rng = (vmax - vmin) or 1.0
    zero_x = x0 + (-vmin) / rng * bar_w
    times = reveal_times(n, dur, props.get("cues"), first=0.15, last=0.7)
    highlight = props.get("highlight")
    gp = ease_out_cubic(progress(lt, 0.0, 0.6))
    cv.line([(zero_x, y_top), (zero_x, y_bot)], with_alpha(th.card_outline if th.name != "paper" else (31, 41, 55, 40), gp), 2, round_caps=False)
    block = lab_size * 1.15 + 8 + bar_h
    for i in range(n):
        p = ease_out_cubic(progress(lt, times[i], 0.9))
        cy0 = y_top + pitch * i + (pitch - block) / 2
        cv.text(x0, cy0, labels[i], "semibold", lab_size, with_alpha(th.muted if p < 0.3 else th.text, max(gp * 0.85, p)))
        by = cy0 + lab_size * 1.15 + 8
        end = zero_x + values[i] / rng * bar_w * p
        a, b = sorted((zero_x, end))
        col = th.accent2 if (highlight is not None and int(highlight) == i) else th.accent
        if b - a > 1:
            cv.shadow(a, by, b - a, bar_h, bar_h * 0.3, blur=12, dy=6, alpha=th.shadow_alpha * 0.7 * p)
            cv.rrect(a, by, b - a, bar_h, min(bar_h * 0.3, 16), fill=col + (255,))
        shown = _fmt(values[i] * p, unit)
        vx = b + 14 if values[i] >= 0 else a - 14
        cv.text(vx, by + bar_h / 2, shown, "bold", val_size, with_alpha(th.text, min(1.0, p * 1.6)), anchor="lm" if values[i] >= 0 else "rm")


# ------------------------------------------------------------------ timeline
def timeline_cues(props: Dict[str, Any], dur: float) -> List[float]:
    return reveal_times(len(props.get("events") or []), dur, props.get("cues"), first=0.15, last=0.75)


def draw_timeline(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    events = [e for e in (props.get("events") or []) if isinstance(e, dict)][:7]
    top = heading(cv, th, str(props.get("title", "")), lt, y=ctx.top + 20, ctx=ctx) if props.get("title") else ctx.top + 40
    if not events:
        return
    if not ctx.frame.landscape:
        return _timeline_vertical(cv, props, events, ctx, lt, dur, th, top)
    n = len(events)
    ly = (top + ctx.bottom) / 2 + 20
    x0, x1 = 180, 1740
    times = reveal_times(n, dur, props.get("cues"), first=0.15, last=0.75)
    drawn = ease_in_out_cubic(progress(lt, 0.05, max(0.8, times[-1] + 0.3)))
    cv.line([(x0, ly), (x1, ly)], with_alpha(th.card_outline if th.name != "paper" else (31, 41, 55, 50), 1.0), 8)
    cv.line(partial_polyline([(x0, ly), (x1, ly)], drawn), th.accent + (255,), 8)
    slot = (x1 - x0) / max(1, n - 1) if n > 1 else 0
    box_w = min(340.0, (x1 - x0) / n * 1.25)
    for i, ev in enumerate(events):
        cx = x0 + slot * i if n > 1 else (x0 + x1) / 2
        p = progress(lt, times[i], 0.5)
        if p <= 0:
            continue
        a = ease_out_cubic(p * 1.5)
        s = ease_out_back(p, 2)
        above = i % 2 == 0
        cv.ellipse(cx, ly, 20 * s, 20 * s, fill=th.accent2 + (255,), outline=(255, 255, 255, 255), width=4)
        stem = 70 + (1 - ease_out_cubic(p)) * 20
        y_edge = ly - 28 - stem if above else ly + 28 + stem
        cv.line([(cx, ly - 24) if above else (cx, ly + 24), (cx, y_edge)], with_alpha(th.muted, a * 0.7), 3)
        date = str(ev.get("date", ""))
        label = str(ev.get("label", ""))
        lines = cv.wrap(label, "regular", 31, box_w - 28)[:3]
        h = (78 + len(lines) * 40) if date else (34 + len(lines) * 40)
        by = y_edge - h if above else y_edge
        bx = min(max(cx - box_w / 2, 60), 1920 - 60 - box_w)
        cv.card(bx, by, box_w, h, th, r=20, alpha=a)
        ty = by + 16
        if date:
            cv.text(bx + 20, ty, date, "bold", 34, with_alpha(th.accent, a))
            ty += 48
        for k, line in enumerate(lines):
            cv.text(bx + 20, ty + k * 40, line, "regular", 31, with_alpha(th.text, a))


def _timeline_vertical(cv: Canvas, props: Dict[str, Any], events, ctx: SceneCtx, lt: float, dur: float, th: Theme, top: float) -> None:
    """Tall and square frames: the spine runs down the left, events hang off it in order. Roomy rows get a card each; tight rows (many events in the
    square frame) become two columns, the date left of the spine and the words right of it."""
    fr = ctx.frame
    n = len(events)
    y0, y1 = top + 10, ctx.bottom - 8
    pitch = (y1 - y0) / n
    times = reveal_times(n, dur, props.get("cues"), first=0.15, last=0.75)
    drawn = ease_in_out_cubic(progress(lt, 0.05, max(0.8, times[-1] + 0.3)))
    cards = pitch >= 128
    mx = fr.margin_x
    track = with_alpha(th.card_outline if th.name != "paper" else (31, 41, 55, 50), 1.0)
    dates = [str(e.get("date", "")) for e in events]
    if cards:
        sx = mx + 30
        cx0, cx1 = sx + 62, fr.W - mx
    else:
        dsz = 34.0 if pitch >= 90 else 30.0
        date_w = min(300.0, max((cv.measure(d, "bold", dsz) for d in dates), default=0.0))
        sx = mx + date_w + 36
        cx0, cx1 = sx + 40, fr.W - mx
    cys = [y0 + pitch * (i + 0.5) for i in range(n)]
    if n > 1:
        pts = [(sx, cys[0]), (sx, cys[-1])]
        cv.line(pts, track, 8)
        cv.line(partial_polyline(pts, drawn), th.accent + (255,), 8)
    for i, ev in enumerate(events):
        p = progress(lt, times[i], 0.5)
        if p <= 0:
            continue
        a = ease_out_cubic(p * 1.5)
        s = ease_out_back(p, 2)
        cy = cys[i]
        cv.ellipse(sx, cy, 20 * s, 20 * s, fill=th.accent2 + (255,), outline=(255, 255, 255, 255), width=4)
        date, label = dates[i], str(ev.get("label", ""))
        dx = (1 - ease_out_cubic(p)) * 26
        if cards:
            lsz = 42.0 if pitch >= 200 else 36.0
            dsz = lsz + 4
            date_h = 50 if date else 0
            max_lines = max(1, min(3, int((pitch - 18 - 34 - date_h) // (lsz * 1.18))))
            lines = cv.wrap(label, "regular", lsz, cx1 - cx0 - 44)[:max_lines]
            h = 34 + date_h + len(lines) * lsz * 1.18
            by = cy - h / 2
            cv.line([(sx + 22, cy), (cx0, cy)], with_alpha(th.muted, a * 0.7), 3)
            cv.card(cx0 + dx, by, cx1 - cx0, h, th, r=22, alpha=a)
            ty = by + 18
            if date:
                cv.text(cx0 + dx + 24, ty, date, "bold", dsz, with_alpha(th.accent, a))
                ty += date_h
            for k, line in enumerate(lines):
                cv.text(cx0 + dx + 24, ty + k * lsz * 1.18, line, "regular", lsz, with_alpha(th.text, a))
        else:
            lsz = 32.0 if pitch >= 90 else 28.0
            cv.text(sx - 36 - dx, cy, date, "bold", dsz, with_alpha(th.accent, a), anchor="rm")
            lines = cv.wrap(label, "regular", lsz, cx1 - cx0)[:2]
            lh = lsz * 1.16
            for k, line in enumerate(lines):
                cv.text(cx0 + dx, cy - (len(lines) - 1) * lh / 2 + k * lh, line, "regular", lsz, with_alpha(th.text, a), anchor="lm")


# ------------------------------------------------------------------ image (Ken Burns)
def image_cues(props: Dict[str, Any], dur: float) -> List[float]:
    return [0.0]


def _placeholder(cv: Canvas, th: Theme, ctx: SceneCtx, text: str) -> None:
    """The card shown when a picture or clip is missing or unreadable."""
    fr = ctx.frame
    if fr.landscape:
        cv.card(260, 180, 1400, 560, th, r=36)
        cv.text(fr.cx, 460, text, "semibold", 54, with_alpha(th.muted, 1), anchor="mm")
        return
    x0, y0, x1, y1 = ctx.box
    h = min(560.0, (y1 - y0) * 0.5)
    y = (y0 + y1) / 2 - h / 2
    cv.card(x0, y, x1 - x0, h, th, r=36)
    size, lines = cv.fit_text(text, "semibold", x1 - x0 - 80, h - 60, 54 * fr.type_scale, 30)
    for i, line in enumerate(lines):
        cv.text(fr.cx, y + h / 2 + (i - (len(lines) - 1) / 2) * size * 1.25, line, "semibold", size, with_alpha(th.muted, 1), anchor="mm")


_FOCUS: Dict[Tuple[int, Tuple[int, int]], Tuple[float, float]] = {}


def focus_point(src: Image.Image) -> Tuple[float, float]:
    """Where a tall or square crop of a landscape picture should be centred: (x, y) as fractions of the picture. A cheap saliency guess (edge and colour
    contrast on a small copy, weighted toward the centre and the upper third where faces and horizons are), cached per picture. Only used for non-landscape frames."""
    key = (id(src), src.size)
    hit = _FOCUS.get(key)
    if hit is not None:
        return hit
    import numpy as np
    from PIL import ImageFilter

    small = src.copy()
    small.thumbnail((96, 96))
    a = np.asarray(small.convert("RGB"), np.float32)
    g = a.mean(axis=2)
    gx = np.abs(np.diff(g, axis=1, prepend=g[:, :1]))
    gy = np.abs(np.diff(g, axis=0, prepend=g[:1, :]))
    colour = np.abs(a - a.reshape(-1, 3).mean(axis=0)).sum(axis=2) * 0.25
    sal = Image.fromarray(np.clip(gx + gy + colour, 0, 255).astype(np.uint8), "L").filter(ImageFilter.GaussianBlur(3))
    m = np.asarray(sal, np.float32)
    h, w = m.shape
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    prior = np.exp(-((xx / w - 0.5) / 0.38) ** 2 / 2) * np.exp(-((yy / h - 0.42) / 0.45) ** 2 / 2)
    m = m * prior
    thr = np.percentile(m, 80)
    wgt = np.where(m >= thr, m, 0.0)
    tot = float(wgt.sum())
    fx, fy = (float((wgt * xx).sum() / tot / w), float((wgt * yy).sum() / tot / h)) if tot > 0 else (0.5, 0.45)
    out = (min(0.8, max(0.2, fx)), min(0.65, max(0.3, fy)))
    if len(_FOCUS) > 64:
        _FOCUS.clear()
    _FOCUS[key] = out
    return out


def _user_photo_fits(src: Image.Image, frame, tw: int, tht: int) -> bool:
    """A user's own photo is cropped to fill the frame only when the crop loses little (<= ~28% along the cropped side); otherwise it is shown whole over a blur."""
    sa, fa = src.width / src.height, tw / tht
    return min(sa / fa, fa / sa) >= 0.72


HALF_FILL_SS = 4   # 4K canvases (supersampled 4x, see docs/FOUR_K.md)


def _fill(src: Image.Image, tw: int, tht: int, box, ss: int = 2) -> Image.Image:
    """The part `box` of a photograph or clip frame as a tw x tht image (the whole canvas). On a 4K canvas (`ss` 4: supersampled 4x, reduced 2x at the end) the picture is
    resampled once to the output size and doubled: the final reduce gives back exactly that resample, at about a third of the cost of resampling to the whole canvas.
    Every other canvas (ss 1 or 2: drafts, 720p, 1080p): one resample, exactly as always."""
    if ss >= HALF_FILL_SS and tw % 2 == 0 and tht % 2 == 0:
        return src.resize((tw // 2, tht // 2), Image.BILINEAR, box=box).resize((tw, tht), Image.NEAREST)
    return src.resize((tw, tht), Image.BILINEAR, box=box)


def draw_image(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    src: Optional[Image.Image] = ctx.resolve_image(str(props.get("asset", ""))) if props.get("asset") else None
    tw, tht = cv.W * cv.ss, cv.H * cv.ss
    fr = ctx.frame
    if src is None:  # asset missing: elegant placeholder instead of a crash
        _placeholder(cv, th, ctx, str(props.get("alt") or props.get("title") or "Image unavailable"))
        return
    motion = str(props.get("ken_burns", "in"))
    p = ease_in_out_cubic(progress(lt, 0.0, max(dur, 0.5)))
    z = lerp(1.0, 1.14, p) if motion != "out" else lerp(1.14, 1.0, p)
    sw, sh = src.size
    contain = (sw / sh < 1.3) if fr.landscape else not _user_photo_fits(src, fr, tw, tht)
    if contain and props.get("photo"):  # a photo of the user's that would lose too much to a crop: show all of it, never crop a face off
        _draw_contained(cv, src, tw, tht, z)
        cv.im.paste(Image.new("RGB", _scrim(tw, tht, fr).size, (0, 0, 0)), (0, tht - _scrim(tw, tht, fr).height), _scrim(tw, tht, fr))
        _draw_word(cv, props, lt, dur, ctx)
        return
    base = max(tw / sw, tht / sh)
    vw, vh = tw / (base * z), tht / (base * z)
    cx, cy = (sw / 2, sh / 2) if fr.landscape else (focus_point(src)[0] * sw, focus_point(src)[1] * sh)
    pan = (sw - vw) / 2 * 0.8
    if motion == "left":
        cx += lerp(pan, -pan, p)
    elif motion == "right":
        cx += lerp(-pan, pan, p)
    cx = min(max(cx, vw / 2), sw - vw / 2)
    cy = min(max(cy, vh / 2), sh - vh / 2)
    img = _fill(src, tw, tht, _box(cx, cy, vw, vh, sw, sh), cv.ss)
    cv.im.paste(img)
    # bottom scrim so captions stay legible over any photo
    scrim = _scrim(tw, tht, fr)
    cv.im.paste(Image.new("RGB", scrim.size, (0, 0, 0)), (0, tht - scrim.height), scrim)
    credit = str(props.get("credit", "")).strip()
    if credit:
        a = ease_out_cubic(progress(lt, 0.4, 0.6))
        cv.text(cv.W - 40, _credit_y(fr), credit[:90], "regular", 22 if fr.landscape else 26, with_alpha((255, 255, 255), 0.7 * a), anchor="ra")
    _draw_word(cv, props, lt, dur, ctx)


def _credit_y(fr) -> float:
    return 40 if fr.landscape else max(40, fr.margin_top - 30)


def _draw_word(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, ctx: Optional[SceneCtx] = None, over: Optional[Tuple[float, float, float]] = None) -> None:
    """One big word over a picture (a silent beat's punchline): fades in, holds, fades out, with a soft shadow so it reads on any photograph."""
    word = str(props.get("word") or "").strip()
    if not word:
        return
    a_in = ease_out_cubic(progress(lt, 0.45, 0.55))
    a = min(a_in, 1.0 - ease_out_cubic(progress(lt, max(0.8, dur - 0.55), 0.45)))
    if a <= 0.01:
        return
    fr = ctx.frame if ctx is not None else None
    if over is not None:   # a picture smaller than the frame (the 4K clip window): the word sits inside it, (centre x, centre y, widest)
        cx, base_y, mw, start = over[0], over[1], over[2], 190
    elif fr is None or fr.landscape:
        cx, base_y, mw, start = 960, 500, 1500, 210
    else:
        cx, base_y, mw, start = fr.cx, ctx.top + (ctx.bottom - ctx.top) * 0.55, fr.W - 2 * fr.margin_x, 210 * fr.type_scale
    size, _ = cv.fit_text(word, "bold", mw, 260, start, 70)
    y = base_y + (1 - a_in) * 26
    cv.text(cx + 4, y + 7, word, "bold", size, (0, 0, 0, int(140 * a)), anchor="mm")
    cv.text(cx, y, word, "bold", size, (255, 255, 255, int(255 * a)), anchor="mm")


# ------------------------------------------------------------------ gallery (several photographs during one beat)
GALLERY_FADE_S = 0.6


def gallery_cues(props: Dict[str, Any], dur: float) -> List[float]:
    return []


def _box(cx: float, cy: float, vw: float, vh: float, sw: int, sh: int) -> Tuple[float, float, float, float]:
    """The crop box centred on (cx, cy), kept inside the source: when the photo has exactly the frame's shape the box equals the image and float rounding
    used to put its edge at -1e-13, which PIL rejects ("box offset can't be negative") and which failed the whole render."""
    return (max(0.0, cx - vw / 2), max(0.0, cy - vh / 2), min(float(sw), cx + vw / 2), min(float(sh), cy + vh / 2))


def _cover(src: Image.Image, tw: int, tht: int, z: float, motion: str, p: float, focus: Optional[Tuple[float, float]] = None, ss: int = 2) -> Image.Image:
    sw, sh = src.size
    base = max(tw / sw, tht / sh)
    vw, vh = tw / (base * z), tht / (base * z)
    cx, cy = (sw / 2, sh / 2) if focus is None else (focus[0] * sw, focus[1] * sh)
    pan = (sw - vw) / 2 * 0.8
    if motion == "left":
        cx += lerp(pan, -pan, p)
    elif motion == "right":
        cx += lerp(-pan, pan, p)
    cx = min(max(cx, vw / 2), sw - vw / 2)
    cy = min(max(cy, vh / 2), sh - vh / 2)
    return _fill(src, tw, tht, _box(cx, cy, vw, vh, sw, sh), ss)


def draw_gallery(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    assets = [str(a) for a in props.get("assets") or []]
    srcs = [ctx.resolve_image(a) for a in assets]
    tw, tht = cv.W * cv.ss, cv.H * cv.ss
    fr = ctx.frame
    if not assets or all(s is None for s in srcs):
        _placeholder(cv, th, ctx, str(props.get("alt") or "Images unavailable"))
        return
    n = len(assets)
    total = max(dur, 0.5)
    # each photograph starts at its cut: when the narration names it (props.cuts, see engine/sync.py), else the beat is shared evenly
    cuts = [float(c) for c in props.get("cuts") or []]
    if len(cuts) != n or cuts[0] != 0.0 or any(b <= a for a, b in zip(cuts, cuts[1:])) or cuts[-1] >= total:
        cuts = [total * k / n for k in range(n)]
    bounds = cuts + [total]
    t = max(0.0, min(lt, dur - 1e-3))
    i = max(k for k in range(n) if cuts[k] <= t)
    motions = ("in", "left", "in", "right")

    def frame(k: int) -> Optional[Image.Image]:
        if srcs[k] is None:
            return None
        local = (t - bounds[k]) / max(0.2, bounds[k + 1] - bounds[k])
        p = ease_in_out_cubic(min(1.0, max(0.0, local)))
        whole = (srcs[k].width / srcs[k].height < 1.3) if fr.landscape else not _user_photo_fits(srcs[k], fr, tw, tht)
        if props.get("user") and whole:   # a photo of the user's that a crop would hurt: all of it, never a face cropped off
            return _contained_image(srcs[k], tw, tht, lerp(1.0, 1.06, p))
        return _cover(srcs[k], tw, tht, lerp(1.0, 1.12, p), motions[k % 4], p, None if fr.landscape else focus_point(srcs[k]), cv.ss)

    cur = frame(i) or next((f for f in (frame(k) for k in range(n)) if f is not None), None)
    if cur is None:
        return
    # the next photograph fades in so that it is fully there at its cut
    into_next = t - bounds[i + 1] + GALLERY_FADE_S
    if i < n - 1 and into_next > 0:
        nxt = frame(i + 1)
        if nxt is not None:
            cur = Image.blend(cur, nxt, min(1.0, into_next / GALLERY_FADE_S))
    cv.im.paste(cur)
    scrim = _scrim(tw, tht, fr)
    cv.im.paste(Image.new("RGB", scrim.size, (0, 0, 0)), (0, tht - scrim.height), scrim)
    credits = [str(c) for c in props.get("credits") or []]
    cur_k = i + 1 if (i < n - 1 and into_next > GALLERY_FADE_S * 0.5) else i                 # the credit switches with the picture
    shown = credits[cur_k] if credits and cur_k < len(credits) else ""
    if shown.strip():
        a = ease_out_cubic(progress(t - bounds[cur_k], 0.15, 0.5))
        cv.text(cv.W - 40, _credit_y(fr), shown[:90], "regular", 22 if fr.landscape else 26, with_alpha((255, 255, 255), 0.7 * a), anchor="ra")
    _draw_word(cv, props, lt, dur, ctx)


# ------------------------------------------------------------------ clip (stock video behind the narration)
def clip_cues(props: Dict[str, Any], dur: float) -> List[float]:
    return [0.0]


# 4K and footage below ~1080p wide (our own 720p library, small stock files): drawn in a window at FRAMED_SCALE output pixels per source pixel instead of a 3x full-frame enlargement.
FRAMED_SCALE = 1.5          # output pixels per source pixel in the window (1.0 = pixel for pixel; 1.5 verified clean on the forest clips)
FRAMED_MIN_FULL_W = 1900    # footage at least this wide (1080p) keeps the full-bleed look: it is enlarged 2x at most, the same as 720p footage in a 1080p video


def clip_is_framed(fr, size: Tuple[int, int]) -> bool:
    """True for a landscape 4K frame and footage narrower than FRAMED_MIN_FULL_W. Every other frame (720p, 1080p, vertical, square) keeps the full-frame look unchanged."""
    return bool(fr is not None and getattr(fr, "resolution", "") == "2160p" and fr.landscape and size[0] < FRAMED_MIN_FULL_W)


_ROUND_MASK: Dict[Tuple[int, int, int], Image.Image] = {}


def _round_mask(w: int, h: int, r: int) -> Image.Image:
    key = (w, h, r)
    if key not in _ROUND_MASK:
        from PIL import ImageDraw

        if len(_ROUND_MASK) > 6:
            _ROUND_MASK.clear()
        m = Image.new("L", (w, h), 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], radius=r, fill=255)
        _ROUND_MASK[key] = m
    return _ROUND_MASK[key]


def _draw_clip_framed(cv: Canvas, props: Dict[str, Any], src: Image.Image, lt: float, dur: float, p: float, th: Theme, ctx: SceneCtx) -> None:
    """The clip in a rounded window at its own resolution over a soft glow of itself, with a small caption line and the credit under it. Everything but the footage is
    drawn at the canvas density, so text and edges are native 4K; the footage is enlarged at most FRAMED_SCALE x."""
    tw, tht = cv.W * cv.ss, cv.H * cv.ss
    ss = cv.ss
    px = max(1.0, ss / 2.0)                       # output pixels per design unit (2 on a 4K canvas)
    sw, sh = src.size
    glow = Image.eval(src.resize((48, 27), Image.BOX).resize((max(2, tw // 2), max(2, tht // 2)), Image.BICUBIC), lambda v: int(v * 0.42))
    cv.im.paste(glow.resize((tw, tht), Image.NEAREST) if ss >= HALF_FILL_SS else glow.resize((tw, tht), Image.BILINEAR))
    wd = min(sw * FRAMED_SCALE / px, cv.W * 0.74)    # window size in design units
    hd = wd * sh / sw
    caption = str(props.get("alt") or "").strip()
    credit = str(props.get("credit") or "").strip()
    block = hd + (74 if (caption or credit) else 0)
    top_limit, bottom_limit = 70.0, (800.0 if ctx.captions else 1000.0)
    x = (cv.W - wd) / 2
    y = top_limit + max(0.0, (bottom_limit - top_limit - block) / 2)
    a = ease_out_cubic(progress(lt, 0.0, 0.45))
    y += (1 - a) * 14
    wc, hc = max(2, round(wd * ss)), max(2, round(hd * ss))
    z = lerp(1.0, 1.04, p)
    vw, vh = sw / z, sh / z
    box = ((sw - vw) / 2, (sh - vh) / 2, (sw + vw) / 2, (sh + vh) / 2)
    win = _fill(src, wc, hc, box, ss)
    radius = 26
    cv.shadow(x, y, wd, hd, radius, blur=34, dy=18, alpha=0.5 * a)
    cv.im.paste(win, (round(x * ss), round(y * ss)), _round_mask(wc, hc, round(radius * ss)))
    cv.rrect(x, y, wd, hd, radius, outline=with_alpha((255, 255, 255), 0.16), width=1.5)
    ty = y + hd + 38
    if caption:
        cv.text(x + 6, ty, caption[:90], "regular", 30, with_alpha((255, 255, 255), 0.9 * a), anchor="lm")
    if credit:
        cv.text(x + wd - 6, ty, credit[:90], "regular", 22, with_alpha((255, 255, 255), 0.6 * a), anchor="rm")
    _draw_word(cv, props, lt, dur, ctx, over=(x + wd / 2, y + hd * 0.52, wd * 0.84))


def draw_clip(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    frames = ctx.resolve_clip(str(props.get("asset", ""))) if props.get("asset") else None
    tw, tht = cv.W * cv.ss, cv.H * cv.ss
    fr = ctx.frame
    if frames is None:  # the file is missing or undecodable: the same elegant placeholder as a missing photo
        _placeholder(cv, th, ctx, str(props.get("alt") or props.get("title") or "Video unavailable"))
        return
    t = max(0.0, min(lt, dur))  # an outgoing scene holds its final frame during the crossfade; footage shorter than the scene holds its last frame (never loops)
    src = frames.frame(int(t * frames.fps))
    p = ease_in_out_cubic(progress(t, 0.0, max(dur, 0.5)))
    if clip_is_framed(fr, src.size):   # 4K video, footage too small to fill the frame without a visible enlargement: a native-size window (docs/FOUR_K.md)
        _draw_clip_framed(cv, props, src, lt, dur, p, th, ctx)
        return
    z = lerp(1.0, 1.06, p)  # a slow push-in hides the modest source resolution and keeps the frame alive
    sw, sh = src.size
    base = max(tw / sw, tht / sh)
    vw, vh = tw / (base * z), tht / (base * z)
    if fr.landscape:
        box = ((sw - vw) / 2, (sh - vh) / 2, (sw + vw) / 2, (sh + vh) / 2)
    else:   # stock footage is mostly landscape: crop its middle (a little above centre), or all of it when it is already tall
        cx, cy = min(max(sw / 2, vw / 2), sw - vw / 2), min(max(sh * 0.46, vh / 2), sh - vh / 2)
        box = _box(cx, cy, vw, vh, sw, sh)
    cv.im.paste(_fill(src, tw, tht, box, cv.ss))
    scrim = _scrim(tw, tht, fr)
    cv.im.paste(Image.new("RGB", scrim.size, (0, 0, 0)), (0, tht - scrim.height), scrim)
    credit = str(props.get("credit", "")).strip()
    if credit:
        a = ease_out_cubic(progress(lt, 0.4, 0.6))
        cv.text(cv.W - 40, _credit_y(fr), credit[:90], "regular", 22 if fr.landscape else 26, with_alpha((255, 255, 255), 0.7 * a), anchor="ra")
    _draw_word(cv, props, lt, dur, ctx)


_BACKDROP: Dict[Tuple[int, int, int], Image.Image] = {}


def _contained_image(src: Image.Image, tw: int, tht: int, z: float) -> Image.Image:
    """The photo whole, centred and gently zooming, over a blurred, darkened copy of itself that fills the frame (an image of the full frame size)."""
    from PIL import ImageFilter

    key = (id(src), tw, tht)
    if key not in _BACKDROP:
        if len(_BACKDROP) > 8:
            _BACKDROP.clear()
        small = src.copy()
        small.thumbnail((480, 480))
        bg = small.resize((tw, tht), Image.BILINEAR, box=_cover_box(small.size, tw, tht)).filter(ImageFilter.GaussianBlur(28 * tw / 1920))
        _BACKDROP[key] = Image.eval(bg, lambda v: int(v * 0.45))
    frame = _BACKDROP[key].copy()
    s = min(tw * 0.9 / src.width, tht * 0.94 / src.height) * z
    fg = src.resize((max(1, round(src.width * s)), max(1, round(src.height * s))), Image.BILINEAR)
    frame.paste(fg, ((tw - fg.width) // 2, (tht - fg.height) // 2))
    return frame


def _draw_contained(cv: Canvas, src: Image.Image, tw: int, tht: int, z: float) -> None:
    cv.im.paste(_contained_image(src, tw, tht, z))



def _cover_box(size: Tuple[int, int], tw: int, tht: int) -> Tuple[float, float, float, float]:
    sw, sh = size
    scale = max(tw / sw, tht / sh)
    vw, vh = tw / scale, tht / scale
    return ((sw - vw) / 2, (sh - vh) / 2, (sw + vw) / 2, (sh + vh) / 2)


_SCRIM: Dict[Tuple[int, int], Image.Image] = {}


def _scrim(w: int, h: int, frame=None) -> Image.Image:
    key = (w, h)
    if key not in _SCRIM:
        import numpy as np

        sh = int(h * (0.42 if frame is None or frame.landscape else 0.34))
        ramp = (np.linspace(0, 1, sh, dtype=np.float32) ** 1.6 * 215).astype("uint8")
        _SCRIM[key] = Image.fromarray(np.repeat(ramp[:, None], w, axis=1), "L")
    return _SCRIM[key]
