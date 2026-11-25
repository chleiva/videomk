import math
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image

from ..canvas import Canvas, partial_polyline, with_alpha
from ..easing import ease_in_out_cubic, ease_out_back, ease_out_cubic, lerp, progress, reveal_times
from ..theme import Theme
from .base import CENTER_X, CONTENT_TOP, SceneCtx, format_number, heading

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
    if "." in s:
        s = s.rstrip("0").rstrip(".")
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
    top = heading(cv, th, str(props.get("title", "")), lt, y=CONTENT_TOP + 20) if props.get("title") else CONTENT_TOP + 50
    if n == 0:
        return
    unit = str(props.get("unit", ""))
    kind = str(props.get("kind", "bar"))
    x0, x1 = 200, 1760
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
            cv.text(x0 - 16, gy, _fmt(vmin + rng * k / 4, unit if unit != "%" else "%"), "regular", 24, with_alpha(th.muted, gp), anchor="rm")
    times = reveal_times(n, dur, props.get("cues"), first=0.15, last=0.7)
    slot = (x1 - x0) / n
    highlight = props.get("highlight")
    if kind == "line":
        pts = [(x0 + slot * (i + 0.5), ypos(values[i])) for i in range(n)]
        total_p = ease_in_out_cubic(progress(lt, times[0], max(0.8, times[-1] - times[0] + 0.5)))
        part = partial_polyline(pts, total_p)
        if len(part) >= 2:
            cv.polygon(part + [(part[-1][0], y_base), (part[0][0], y_base)], with_alpha(th.accent, 0.16))
            cv.line(part, th.accent + (255,), 8)
        for i, (px, py) in enumerate(pts):
            dp = ease_out_back(progress(lt, times[i] + 0.1, 0.4), 2)
            if dp > 0:
                cv.ellipse(px, py, 13 * dp, 13 * dp, fill=th.accent2 + (255,), outline=(255, 255, 255, 255), width=3)
                cv.text(px, py - 34, _fmt(values[i], unit), "semibold", 30, with_alpha(th.text, min(1, dp)), anchor="mb")
            cv.text(px, y_base + 18, labels[i], "regular", 28, with_alpha(th.muted, gp), anchor="ma")
        return
    bw = min(150.0, slot * 0.56)
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
        cv.text(cx, a - 14, shown, "bold", 34, with_alpha(th.text, min(1.0, p * 1.6)), anchor="mb")
        cv.text(cx, y_base + 18, labels[i], "regular", 28, with_alpha(th.muted, gp), anchor="ma")


# ------------------------------------------------------------------ timeline
def timeline_cues(props: Dict[str, Any], dur: float) -> List[float]:
    return reveal_times(len(props.get("events") or []), dur, props.get("cues"), first=0.15, last=0.75)


def draw_timeline(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    events = [e for e in (props.get("events") or []) if isinstance(e, dict)][:7]
    top = heading(cv, th, str(props.get("title", "")), lt, y=CONTENT_TOP + 20) if props.get("title") else CONTENT_TOP + 40
    if not events:
        return
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


# ------------------------------------------------------------------ image (Ken Burns)
def image_cues(props: Dict[str, Any], dur: float) -> List[float]:
    return [0.0]


def draw_image(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    src: Optional[Image.Image] = ctx.resolve_image(str(props.get("asset", ""))) if props.get("asset") else None
    tw, tht = cv.W * cv.ss, cv.H * cv.ss
    if src is None:  # asset missing: elegant placeholder instead of a crash
        cv.card(260, 180, 1400, 560, th, r=36)
        cv.text(CENTER_X, 460, str(props.get("alt") or props.get("title") or "Image unavailable"), "semibold", 54, with_alpha(th.muted, 1), anchor="mm")
        return
    motion = str(props.get("ken_burns", "in"))
    p = ease_in_out_cubic(progress(lt, 0.0, max(dur, 0.5)))
    z = lerp(1.0, 1.14, p) if motion != "out" else lerp(1.14, 1.0, p)
    sw, sh = src.size
    if sw / sh < 1.3 and props.get("photo"):  # a portrait or square phone photo of the user's: show all of it, never crop a face off
        _draw_contained(cv, src, tw, tht, z)
        cv.im.paste(Image.new("RGB", _scrim(tw, tht).size, (0, 0, 0)), (0, tht - _scrim(tw, tht).height), _scrim(tw, tht))
        _draw_word(cv, props, lt, dur)
        return
    base = max(tw / sw, tht / sh)
    vw, vh = tw / (base * z), tht / (base * z)
    cx, cy = sw / 2, sh / 2
    pan = (sw - vw) / 2 * 0.8
    if motion == "left":
        cx += lerp(pan, -pan, p)
    elif motion == "right":
        cx += lerp(-pan, pan, p)
    cx = min(max(cx, vw / 2), sw - vw / 2)
    cy = min(max(cy, vh / 2), sh - vh / 2)
    img = src.resize((tw, tht), Image.BILINEAR, box=_box(cx, cy, vw, vh, sw, sh))
    cv.im.paste(img)
    # bottom scrim so captions stay legible over any photo
    scrim = _scrim(tw, tht)
    cv.im.paste(Image.new("RGB", scrim.size, (0, 0, 0)), (0, tht - scrim.height), scrim)
    credit = str(props.get("credit", "")).strip()
    if credit:
        a = ease_out_cubic(progress(lt, 0.4, 0.6))
        cv.text(1880, 40, credit[:90], "regular", 22, with_alpha((255, 255, 255), 0.7 * a), anchor="ra")
    _draw_word(cv, props, lt, dur)


def _draw_word(cv: Canvas, props: Dict[str, Any], lt: float, dur: float) -> None:
    """One big word over a picture (a silent beat's punchline): fades in, holds, fades out, with a soft shadow so it reads on any photograph."""
    word = str(props.get("word") or "").strip()
    if not word:
        return
    a_in = ease_out_cubic(progress(lt, 0.45, 0.55))
    a = min(a_in, 1.0 - ease_out_cubic(progress(lt, max(0.8, dur - 0.55), 0.45)))
    if a <= 0.01:
        return
    size, _ = cv.fit_text(word, "bold", 1500, 260, 210, 70)
    y = 500 + (1 - a_in) * 26
    cv.text(CENTER_X + 4, y + 7, word, "bold", size, (0, 0, 0, int(140 * a)), anchor="mm")
    cv.text(CENTER_X, y, word, "bold", size, (255, 255, 255, int(255 * a)), anchor="mm")


# ------------------------------------------------------------------ gallery (several photographs during one beat)
GALLERY_FADE_S = 0.6


def gallery_cues(props: Dict[str, Any], dur: float) -> List[float]:
    return []


def _box(cx: float, cy: float, vw: float, vh: float, sw: int, sh: int) -> Tuple[float, float, float, float]:
    """The crop box centred on (cx, cy), kept inside the source: when the photo has exactly the frame's shape the box equals the image and float rounding
    used to put its edge at -1e-13, which PIL rejects ("box offset can't be negative") and which failed the whole render."""
    return (max(0.0, cx - vw / 2), max(0.0, cy - vh / 2), min(float(sw), cx + vw / 2), min(float(sh), cy + vh / 2))


def _cover(src: Image.Image, tw: int, tht: int, z: float, motion: str, p: float) -> Image.Image:
    sw, sh = src.size
    base = max(tw / sw, tht / sh)
    vw, vh = tw / (base * z), tht / (base * z)
    cx, cy = sw / 2, sh / 2
    pan = (sw - vw) / 2 * 0.8
    if motion == "left":
        cx += lerp(pan, -pan, p)
    elif motion == "right":
        cx += lerp(-pan, pan, p)
    cx = min(max(cx, vw / 2), sw - vw / 2)
    cy = min(max(cy, vh / 2), sh - vh / 2)
    return src.resize((tw, tht), Image.BILINEAR, box=_box(cx, cy, vw, vh, sw, sh))


def draw_gallery(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    assets = [str(a) for a in props.get("assets") or []]
    srcs = [ctx.resolve_image(a) for a in assets]
    tw, tht = cv.W * cv.ss, cv.H * cv.ss
    if not assets or all(s is None for s in srcs):
        cv.card(260, 180, 1400, 560, th, r=36)
        cv.text(CENTER_X, 460, str(props.get("alt") or "Images unavailable"), "semibold", 54, with_alpha(th.muted, 1), anchor="mm")
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
        if props.get("user") and srcs[k].width / srcs[k].height < 1.3:   # a portrait or square photo of the user's: all of it, never a face cropped off
            return _contained_image(srcs[k], tw, tht, lerp(1.0, 1.06, p))
        return _cover(srcs[k], tw, tht, lerp(1.0, 1.12, p), motions[k % 4], p)

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
    scrim = _scrim(tw, tht)
    cv.im.paste(Image.new("RGB", scrim.size, (0, 0, 0)), (0, tht - scrim.height), scrim)
    credits = [str(c) for c in props.get("credits") or []]
    cur_k = i + 1 if (i < n - 1 and into_next > GALLERY_FADE_S * 0.5) else i                 # the credit switches with the picture
    shown = credits[cur_k] if credits and cur_k < len(credits) else ""
    if shown.strip():
        a = ease_out_cubic(progress(t - bounds[cur_k], 0.15, 0.5))
        cv.text(1880, 40, shown[:90], "regular", 22, with_alpha((255, 255, 255), 0.7 * a), anchor="ra")
    _draw_word(cv, props, lt, dur)


# ------------------------------------------------------------------ clip (stock video behind the narration)
def clip_cues(props: Dict[str, Any], dur: float) -> List[float]:
    return [0.0]


def draw_clip(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    frames = ctx.resolve_clip(str(props.get("asset", ""))) if props.get("asset") else None
    tw, tht = cv.W * cv.ss, cv.H * cv.ss
    if frames is None:  # the file is missing or undecodable: the same elegant placeholder as a missing photo
        cv.card(260, 180, 1400, 560, th, r=36)
        cv.text(CENTER_X, 460, str(props.get("alt") or props.get("title") or "Video unavailable"), "semibold", 54, with_alpha(th.muted, 1), anchor="mm")
        return
    t = max(0.0, min(lt, dur))  # an outgoing scene holds its final frame during the crossfade; footage shorter than the scene loops inside it
    src = frames.frame(int(t * frames.fps))
    p = ease_in_out_cubic(progress(t, 0.0, max(dur, 0.5)))
    z = lerp(1.0, 1.06, p)  # a slow push-in hides the modest source resolution and keeps the frame alive
    sw, sh = src.size
    base = max(tw / sw, tht / sh)
    vw, vh = tw / (base * z), tht / (base * z)
    box = ((sw - vw) / 2, (sh - vh) / 2, (sw + vw) / 2, (sh + vh) / 2)
    cv.im.paste(src.resize((tw, tht), Image.BILINEAR, box=box))
    scrim = _scrim(tw, tht)
    cv.im.paste(Image.new("RGB", scrim.size, (0, 0, 0)), (0, tht - scrim.height), scrim)
    credit = str(props.get("credit", "")).strip()
    if credit:
        a = ease_out_cubic(progress(lt, 0.4, 0.6))
        cv.text(1880, 40, credit[:90], "regular", 22, with_alpha((255, 255, 255), 0.7 * a), anchor="ra")
    _draw_word(cv, props, lt, dur)


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


def _scrim(w: int, h: int) -> Image.Image:
    key = (w, h)
    if key not in _SCRIM:
        import numpy as np

        sh = int(h * 0.42)
        ramp = (np.linspace(0, 1, sh, dtype=np.float32) ** 1.6 * 215).astype("uint8")
        _SCRIM[key] = Image.fromarray(np.repeat(ramp[:, None], w, axis=1), "L")
    return _SCRIM[key]
