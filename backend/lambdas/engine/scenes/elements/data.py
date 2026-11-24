"""Data elements: scale_compare, pictogram, bar_race, pie, area, stacked, scatter.

All of them draw only numbers the director was given (which in turn must come from the grounding notes); nothing is estimated or invented here.
The look follows `draw_chart` in viz_scenes: the same grid, tick labels, number format (`_fmt`), bar style and accent/accent2 highlight convention.
"""
import math
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

from ...canvas import Canvas, with_alpha
from ...easing import ease_in_out_cubic, ease_out_back, ease_out_cubic, progress, reveal_times, smoothstep
from ...theme import Theme
from ..base import CONTENT_TOP, SceneCtx, heading
from ..registry import Element
from ..viz_scenes import _fmt


# ----------------------------------------------------------------------------- shared helpers
def _txt(x: Any, n: int) -> str:
    """A clipped single-line string; anything that is not plain text becomes ''."""
    if not isinstance(x, (str, int, float)) or isinstance(x, bool):
        return ""
    return " ".join(str(x).split())[:n].strip()


def _num(x: Any) -> Optional[float]:
    if isinstance(x, bool) or x is None:
        return None
    try:
        v = float(str(x).replace(",", "").strip()) if isinstance(x, str) else float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and abs(v) < 1e15 else None


def _items(x: Any, cap: int) -> list:
    return list(x)[:cap] if isinstance(x, (list, tuple)) else []


def _title(props: Dict[str, Any]) -> str:
    return _txt(props.get("title"), 50)


def _mix(a: Tuple[int, ...], b: Tuple[int, ...], t: float) -> Tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def _on(c: Tuple[int, ...]) -> Tuple[int, int, int]:
    """Readable text colour on a filled shape."""
    lum = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    return (20, 24, 40) if lum > 150 else (255, 255, 255)


def _series_colors(th: Theme, n: int) -> List[Tuple[int, int, int]]:
    return [_mix(th.accent, th.accent2, i / (n - 1) if n > 1 else 0.0) for i in range(n)]


def _axis_col(th: Theme):
    return th.card_outline if th.name != "paper" else (31, 41, 55, 30)


def _top(cv: Canvas, th: Theme, props: Dict[str, Any], lt: float) -> float:
    t = _title(props)
    return heading(cv, th, t, lt, y=CONTENT_TOP + 20) if t else CONTENT_TOP + 50


def _nice(lo: float, hi: float, n: int = 4) -> Tuple[float, float, float]:
    """A tidy axis (lo, hi, step) that contains [lo, hi] with about n intervals."""
    if hi <= lo:
        hi = lo + (abs(lo) * 0.1 or 1.0)
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    step = next(m * mag for m in (1, 2, 2.5, 5, 10) if raw <= m * mag * 1.0001)
    return math.floor(lo / step + 1e-9) * step, math.ceil(hi / step - 1e-9) * step, step


def _tick(v: float) -> str:
    if float(v).is_integer() and 1800 <= v <= 2100:      # a year, not a quantity
        return str(int(v))
    return _fmt(v, "")


def _grid(cv: Canvas, th: Theme, x0: float, x1: float, y_top: float, y_base: float, lo: float, hi: float, step: float, unit: str, lt: float) -> None:
    gp = ease_out_cubic(progress(lt, 0.0, 0.6))
    k = 0
    v = lo
    while v <= hi + step * 1e-6 and k < 12:
        gy = y_base - (v - lo) / ((hi - lo) or 1.0) * (y_base - y_top)
        first = k == 0
        cv.line([(x0, gy), (x1, gy)], with_alpha(_axis_col(th), gp * (1.6 if first else 1.0)), 2, round_caps=False)
        cv.text(x0 - 16, gy, _fmt(v, unit if unit == "%" else ""), "regular", 24, with_alpha(th.muted, gp), anchor="rm")
        v += step
        k += 1


def _fit_one(cv: Canvas, s: str, weight: str, max_w: float, start: float, min_size: float) -> float:
    size = start
    while size > min_size and cv.measure(s, weight, size) > max_w:
        size -= 2
    return size


def _lines_in(cv: Canvas, s: str, weight: str, max_w: float, max_lines: int, start: float, min_size: float) -> Tuple[float, List[str]]:
    """Largest size whose wrapped text fits in max_lines lines of max_w."""
    size = start
    while size >= min_size:
        lines = cv.wrap(s, weight, size, max_w)
        if len(lines) <= max_lines and all(cv.measure(l, weight, size) <= max_w for l in lines):
            return size, lines
        size -= 2
    return min_size, cv.wrap(s, weight, min_size, max_w)[:max_lines]


def _anchor_cues(n: int, dur: float, props: Dict[str, Any], first: float = 0.15, last: float = 0.7) -> List[float]:
    return reveal_times(n, dur, props.get("cues"), first=first, last=last)


# ============================================================================= 1. scale_compare
def _sc_sanitize(props: Dict[str, Any]) -> Dict[str, Any]:
    items = []
    for it in _items(props.get("items"), 12):
        if not isinstance(it, dict):
            continue
        label, v = _txt(it.get("label"), 24), _num(it.get("value"))
        if not label or v is None or v <= 0:
            continue
        row: Dict[str, Any] = {"label": label, "value": v}
        note = _txt(it.get("note"), 40)
        if note:
            row["note"] = note
        items.append(row)
    items = items[:6]
    if len(items) < 2:
        raise ValueError("scale_compare needs 2-6 items with positive values")
    out: Dict[str, Any] = {"items": items, "unit": _txt(props.get("unit"), 10)}
    if _title(props):
        out["title"] = _title(props)
    if isinstance(props.get("cues"), list):
        out["cues"] = [c for c in (_num(c) for c in props["cues"]) if c is not None][:6]
    return out


def _sc_cap(values: List[float]) -> Optional[float]:
    """When the values differ by more than 50x the tall bars are cut at this value (a marked scale break); None when everything fits honestly."""
    if max(values) / min(values) <= 50:
        return None
    return max(v for v in values if v <= min(values) * 50)


def _sc_bar(cv: Canvas, th: Theme, x: float, w: float, base: float, h: float, col, broken: bool, p: float) -> None:
    if h < 1:
        return
    if not broken:
        cv.shadow(x, base - h, w, h, 14, blur=14, dy=8, alpha=th.shadow_alpha * 0.8 * p)
        cv.rrect(x, base - h, w, h, 14, fill=col + (255,))
        return
    yb = base - h * 0.5                                   # the break: two slanted cuts with a gap between them
    lower = [(x, base), (x + w, base), (x + w, yb - 4), (x, yb + 16)]
    upper = [(x, yb - 6), (x + w, yb - 26), (x + w, base - h), (x, base - h)]
    cv.polygon(lower, col + (255,))
    cv.polygon(upper, col + (255,))
    # the top is rounded like every other bar
    cv.rrect(x, base - h, w, 30, 14, fill=col + (255,))


def _sc_draw(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    items = props["items"]
    n = len(items)
    top = _top(cv, th, props, lt)
    unit = props.get("unit", "")
    x0, x1 = 200, 1760
    y_base = ctx.bottom - 165
    y_top = top + 60
    H = max(120.0, y_base - y_top)
    values = [float(i["value"]) for i in items]
    cap = _sc_cap(values)
    scale_max = cap / 0.72 if cap else max(values)      # a broken scale keeps the honest bars at or below 72% of the height
    times = _anchor_cues(n, dur, props)
    slot = (x1 - x0) / n
    bw = min(170.0, slot * 0.6)
    gp = ease_out_cubic(progress(lt, 0.0, 0.6))
    cv.line([(x0 - 20, y_base), (x1 + 20, y_base)], with_alpha(_axis_col(th), gp * 1.6), 3, round_caps=False)
    big = max(range(n), key=lambda i: values[i])
    cols = [th.accent2 if i == big else th.accent for i in range(n)]
    for i, it in enumerate(items):
        cx = x0 + slot * (i + 0.5)
        p = ease_out_cubic(progress(lt, times[i], 0.9))
        broken = bool(cap and values[i] > cap)
        if broken:   # only their order is shown (log position between 80% and 100%); the exact value is in the label
            full_h = H * (0.8 + 0.2 * math.log(values[i] / cap) / math.log(max(values) / cap))
        else:
            full_h = H * values[i] / scale_max
        h = full_h * p
        _sc_bar(cv, th, cx - bw / 2, bw, y_base, h, cols[i], broken, p)
        if broken and p > 0.85:
            a = ease_out_cubic(progress(p, 0.85, 0.15))
            word = "scale break" if bw >= 140 else "break"
            sz = _fit_one(cv, word, "semibold", bw - 14, 24, 16)
            tw = cv.measure(word, "semibold", sz)
            ym = y_base - full_h * 0.5 + 6
            cv.rrect(cx - tw / 2 - 10, ym - sz * 0.75, tw + 20, sz * 1.5, sz * 0.75, fill=with_alpha(th.bg_top, 0.92 * a), outline=with_alpha(cols[i], a), width=2)
            cv.text(cx, ym, word, "semibold", sz, with_alpha(th.text, a), anchor="mm")
        if p > 0.02:
            cv.text(cx, y_base - h - 14, _fmt(values[i] * p, unit), "bold", 34, with_alpha(th.text, min(1.0, p * 1.6)), anchor="mb")
        a = gp * ease_out_cubic(progress(lt, times[i], 0.5))
        size, lines = _lines_in(cv, it["label"], "semibold", slot - 14, 2, 32, 22)
        for k, line in enumerate(lines):
            cv.text(cx, y_base + 16 + k * size * 1.18, line, "semibold", size, with_alpha(th.text, a), anchor="ma")
        if it.get("note"):
            ny = y_base + 16 + len(lines) * size * 1.18 + 4
            nsize, nlines = _lines_in(cv, it["note"], "regular", slot - 14, 2, 24, 18)
            for k, line in enumerate(nlines):
                cv.text(cx, ny + k * nsize * 1.2, line, "regular", nsize, with_alpha(th.muted, a), anchor="ma")


# ============================================================================= 2. pictogram
ICONS = ("person", "dot", "square", "heart", "house")


def _pg_sanitize(props: Dict[str, Any]) -> Dict[str, Any]:
    total = _num(props.get("total", 100))
    total = 100 if total is None else int(max(10, min(100, round(total))))
    filled = _num(props.get("filled"))
    label = _txt(props.get("label"), 70)
    if filled is None or not label:
        raise ValueError("pictogram needs filled and a label")
    filled = int(max(0, min(total, round(filled))))
    icon = _txt(props.get("icon"), 10).lower()
    out: Dict[str, Any] = {"total": total, "filled": filled, "icon": icon if icon in ICONS else "person", "label": label}
    if _title(props):
        out["title"] = _title(props)
    return out


def _pg_text(filled: int, total: int) -> Tuple[str, str]:
    """(big fraction text, small second line)."""
    g = math.gcd(filled, total) or 1
    a, b = filled // g, total // g
    pct = filled / total * 100
    pct_s = f"{pct:.1f}".rstrip("0").rstrip(".") + "%"
    if filled and a == 1 and 2 <= b <= 20:
        return f"1 in {b}", pct_s
    return pct_s, ("" if total == 100 else f"{filled} of {total}")


def _pg_grid(total: int, w: float, h: float) -> Tuple[int, int, float]:
    """Columns, rows, cell size. A layout with full rows (10x10, 10x5, 6x5) is preferred unless it wastes much of the space."""
    opts = []
    for cols in range(1, total + 1):
        rows = math.ceil(total / cols)
        opts.append((min(w / cols, h / rows), -abs(cols - rows), cols, rows))
    best = max(opts)
    full = [o for o in opts if total % o[2] == 0 and o[3] >= 2]
    pick = max(full) if full and max(full)[0] >= 0.7 * best[0] else best
    return pick[2], pick[3], pick[0]


def _pg_icon(cv: Canvas, kind: str, cx: float, cy: float, s: float, col) -> None:
    if kind == "dot":
        cv.ellipse(cx, cy, 0.42 * s, 0.42 * s, fill=col)
    elif kind == "square":
        cv.rrect(cx - 0.4 * s, cy - 0.4 * s, 0.8 * s, 0.8 * s, 0.12 * s, fill=col)
    elif kind == "heart":
        r = 0.25 * s
        cv.ellipse(cx - 0.235 * s, cy - 0.15 * s, r, r, fill=col)
        cv.ellipse(cx + 0.235 * s, cy - 0.15 * s, r, r, fill=col)
        cv.polygon([(cx - 0.455 * s, cy - 0.06 * s), (cx + 0.455 * s, cy - 0.06 * s), (cx, cy + 0.46 * s)], fill=col)
    elif kind == "house":
        cv.polygon([(cx - 0.5 * s, cy - 0.02 * s), (cx, cy - 0.48 * s), (cx + 0.5 * s, cy - 0.02 * s)], fill=col)
        cv.rrect(cx - 0.36 * s, cy - 0.06 * s, 0.72 * s, 0.52 * s, 0.05 * s, fill=col)
    else:  # person
        cv.ellipse(cx, cy - 0.3 * s, 0.17 * s, 0.17 * s, fill=col)
        cv.rrect(cx - 0.27 * s, cy - 0.08 * s, 0.54 * s, 0.56 * s, 0.2 * s, fill=col)


def _pg_times(filled: int, dur: float) -> Tuple[float, float, List[float]]:
    t0 = 0.55
    wave = min(2.6, max(1.0, dur * 0.4))
    return t0, wave, [t0 + wave * smoothstep(i / max(1, filled - 1)) for i in range(filled)]


def _pg_draw(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    total, filled, kind = props["total"], props["filled"], props["icon"]
    top = _top(cv, th, props, lt)
    gx0, gx1 = 140.0, 1090.0
    gy0, gy1 = top + 10, ctx.bottom - 20
    cols, rows, cell = _pg_grid(total, gx1 - gx0, gy1 - gy0)
    cell = min(cell, 110.0)
    gw, gh = cols * cell, rows * cell
    ox, oy = gx0 + (gx1 - gx0 - gw) / 2, gy0 + (gy1 - gy0 - gh) / 2
    t0, wave, ft = _pg_times(filled, dur)
    base_col = _mix(th.muted, th.bg_top, 0.35) if th.name != "paper" else _mix(th.muted, (255, 255, 255), 0.55)
    s = cell * 0.82
    done = 0
    for i in range(total):
        r, c = divmod(i, cols)
        cx, cy = ox + (c + 0.5) * cell, oy + (r + 0.5) * cell
        fade = ease_out_cubic(progress(lt, 0.05 + 0.5 * (r + c) / (rows + cols), 0.35))
        if fade <= 0:
            continue
        if i < filled:
            q = progress(lt, ft[i], 0.4)
            if q >= 1:
                done += 1
            mix = ease_out_cubic(q)
            pop = 1.0 + 0.28 * math.sin(math.pi * min(1.0, q)) if 0 < q < 1 else 1.0
            col = _mix(base_col, th.accent, mix)
            _pg_icon(cv, kind, cx, cy, s * pop, with_alpha(col, fade))
        else:
            _pg_icon(cv, kind, cx, cy, s, with_alpha(base_col, fade * (0.9 if th.name != "paper" else 1.0)))
    # the fraction beside the grid
    big, small = _pg_text(filled, total)
    px, pw = 1180.0, 600.0
    pcx = px + pw / 2
    a = ease_out_cubic(progress(lt, 0.25, 0.6))
    label_size, label_lines = _lines_in(cv, props["label"], "regular", pw, 4, 46, 30)
    lh = label_size * 1.22
    block_h = 190 * 0.92 + 30 + len(label_lines) * lh + (60 if small else 0)
    py = (gy0 + gy1) / 2 - block_h / 2
    if big.startswith("1 in"):
        shown = big
    else:  # a percentage counts up with the wave
        pct = filled / total * 100
        part = 1.0 if lt >= t0 + wave + 0.4 or not filled else done / filled
        shown = big if part >= 1.0 else (f"{pct * part:.1f}".rstrip("0").rstrip(".") + "%" if pct % 1 else f"{round(pct * part)}%")
    size = _fit_one(cv, big, "bold", pw, 190, 90)
    cv.text(pcx, py + 190 * 0.5 * (size / 190) + (190 - size) * 0.2, shown, "bold", size, with_alpha(th.accent, a), anchor="mm")
    y = py + 190 * 0.92 + 26
    cv.rrect(pcx - 60, y + 6, 120 * ease_out_cubic(progress(lt, 0.5, 0.6)), 8, 4, fill=th.accent2)
    y += 36
    la = ease_out_cubic(progress(lt, 0.6, 0.6))
    for k, line in enumerate(label_lines):
        cv.text(pcx, y + k * lh, line, "regular", label_size, with_alpha(th.text, la), anchor="ma")
    if small:
        cv.text(pcx, y + len(label_lines) * lh + 12, small, "semibold", 38, with_alpha(th.muted, la), anchor="ma")


def _pg_cues(props: Dict[str, Any], dur: float) -> List[float]:
    f = int(props.get("filled", 0))
    _, _, ft = _pg_times(f, dur)
    if not ft:
        return [0.3]
    return [ft[min(len(ft) - 1, int(round(k * (len(ft) - 1) / 3)))] for k in range(4)]


# ============================================================================= 3. bar_race
def _br_sanitize(props: Dict[str, Any]) -> Dict[str, Any]:
    periods = [_txt(p, 8) for p in _items(props.get("periods"), 10)]
    periods = [p for p in periods if p]
    if len(periods) < 3:
        raise ValueError("bar_race needs 3-10 periods")
    series = []
    for s in _items(props.get("series"), 16):
        if not isinstance(s, dict):
            continue
        label = _txt(s.get("label"), 20)
        vals = [_num(v) for v in _items(s.get("values"), 10)]
        if not label or len(vals) < len(periods) or any(v is None or v < 0 for v in vals[: len(periods)]):
            continue
        series.append({"label": label, "values": vals[: len(periods)]})
    series = series[:8]
    if len(series) < 3:
        raise ValueError("bar_race needs 3-8 series with one non-negative value per period")
    if max(max(s["values"]) for s in series) <= 0:
        raise ValueError("bar_race needs some positive values")
    out: Dict[str, Any] = {"periods": periods, "series": series, "unit": _txt(props.get("unit"), 8)}
    if _title(props):
        out["title"] = _title(props)
    return out


def _br_ranks(series: List[Dict[str, Any]], k: int) -> List[int]:
    order = sorted(range(len(series)), key=lambda i: (-series[i]["values"][k], i))
    r = [0] * len(series)
    for pos, i in enumerate(order):
        r[i] = pos
    return r


def _br_clock(P: int, dur: float) -> Tuple[float, float]:
    t_start = 0.35
    hold = min(1.4, dur * 0.2)
    return t_start, max(0.3, (dur - hold - t_start) / (P - 1))


def _br_pos(lt: float, P: int, dur: float) -> Tuple[int, float]:
    """(period index k, eased fraction e toward k+1); the last period holds."""
    t_start, step = _br_clock(P, dur)
    u = (lt - t_start) / step
    if u <= 0:
        return 0, 0.0
    if u >= P - 1:
        return P - 2, 1.0
    k = int(u)
    return k, ease_in_out_cubic(min(1.0, (u - k) / 0.75))


def _br_draw(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    series, periods, unit = props["series"], props["periods"], props.get("unit", "")
    P, n = len(periods), len(series)
    top = _top(cv, th, props, lt)
    k, e = _br_pos(lt, P, dur)
    rk0, rk1 = _br_ranks(series, k), _br_ranks(series, k + 1)
    vmax = max(max(s["values"]) for s in series) or 1.0
    lab_r, bx0, bx1 = 440.0, 460.0, 1330.0
    y0, y1 = top + 10, ctx.bottom - 10
    row = (y1 - y0) / n
    bh = min(76.0, row * 0.76)
    g = ease_out_cubic(progress(lt, 0.0, 0.7))
    cols = _series_colors(th, n)
    cv.line([(bx0 - 2, y0), (bx0 - 2, y1)], with_alpha(_axis_col(th), g * 1.4), 3, round_caps=False)
    order = sorted(range(n), key=lambda i: rk0[i] + (rk1[i] - rk0[i]) * e)
    for i in order:
        s = series[i]
        v = s["values"][k] + (s["values"][k + 1] - s["values"][k]) * e
        pos = rk0[i] + (rk1[i] - rk0[i]) * e
        cy = y0 + (pos + 0.5) * row
        w = max(2.0, (bx1 - bx0) * v / vmax * g)
        cv.shadow(bx0, cy - bh / 2, w, bh, 12, blur=12, dy=6, alpha=th.shadow_alpha * 0.7 * g)
        cv.rrect(bx0, cy - bh / 2, w, bh, 12, fill=cols[i] + (255,))
        size, lines = _lines_in(cv, s["label"], "semibold", lab_r - 140 + 20, 2, 32, 20)
        lh = size * 1.12
        for j, line in enumerate(lines):
            cv.text(lab_r, cy - (len(lines) - 1) * lh / 2 + j * lh, line, "semibold", size, with_alpha(th.text, g), anchor="rm")
        cv.text(bx0 + w + 16, cy, _fmt(v * g, unit), "bold", 34, with_alpha(th.text, g), anchor="lm")
    near = k + (1 if e >= 0.5 else 0)
    label = periods[near]
    size = _fit_one(cv, label, "bold", 280, 120, 50)
    ga = ease_out_cubic(progress(lt, 0.15, 0.6))
    cv.text(1650, (y0 + y1) / 2, label, "bold", size, with_alpha(th.accent, ga), anchor="mm")


def _br_cues(props: Dict[str, Any], dur: float) -> List[float]:
    P = len(props.get("periods") or [])
    if P < 2:
        return [0.3]
    t_start, step = _br_clock(P, dur)
    return [min(dur, t_start + step * k) for k in range(P)]


# ============================================================================= 4. pie
def _pie_sanitize(props: Dict[str, Any]) -> Dict[str, Any]:
    labels, values = _items(props.get("labels"), 12), _items(props.get("values"), 12)
    pairs = []
    for lab, v in zip(labels, values):
        lab, v = _txt(lab, 16), _num(v)
        if lab and v is not None and v > 0:
            pairs.append((lab, v))
    pairs = pairs[:6]
    if len(pairs) < 2:
        raise ValueError("pie needs 2-6 labelled positive values")
    out: Dict[str, Any] = {"labels": [p[0] for p in pairs], "values": [p[1] for p in pairs], "unit": _txt(props.get("unit"), 6), "donut": bool(props.get("donut"))}
    if _title(props):
        out["title"] = _title(props)
    if isinstance(props.get("cues"), list):
        out["cues"] = [c for c in (_num(c) for c in props["cues"]) if c is not None][:6]
    return out


def _share(v: float, total: float) -> str:
    pct = v / total * 100
    return (f"{pct:.0f}%" if pct >= 9.5 or abs(pct - round(pct)) < 0.05 else f"{pct:.1f}%")


def _pt(cx: float, cy: float, r: float, ang: float) -> Tuple[float, float]:
    return cx + r * math.sin(ang), cy - r * math.cos(ang)


def _sector(cx: float, cy: float, r_out: float, r_in: float, a0: float, a1: float) -> List[Tuple[float, float]]:
    steps = max(2, int(abs(a1 - a0) / math.radians(2)) + 1)
    outer = [_pt(cx, cy, r_out, a0 + (a1 - a0) * j / steps) for j in range(steps + 1)]
    if r_in <= 0:
        return [(cx, cy)] + outer
    inner = [_pt(cx, cy, r_in, a1 + (a0 - a1) * j / steps) for j in range(steps + 1)]
    return outer + inner


def _pie_draw(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    labels, values, unit, donut = props["labels"], props["values"], props.get("unit", ""), props.get("donut", False)
    n = len(values)
    total = sum(values)
    top = _top(cv, th, props, lt)
    cx, cy = 560.0, (top + ctx.bottom) / 2 + 4
    R = max(120.0, min(270.0, (ctx.bottom - top) / 2 - 24))
    r_in = R * 0.58 if donut else 0.0
    times = _anchor_cues(n, dur, props, 0.12, 0.62)
    cols = _series_colors(th, n)
    bg = _mix(th.bg_top, th.bg_bottom, 0.5)
    big = max(range(n), key=lambda i: values[i])
    starts, a = [], 0.0
    for v in values:
        starts.append(a)
        a += v / total * 2 * math.pi
    spans = [v / total * 2 * math.pi for v in values]
    for i in range(n):
        p = ease_out_cubic(progress(lt, times[i], 0.8))
        if p <= 0:
            continue
        lift = 16 * ease_out_cubic(progress(lt, times[i] + 0.6, 0.5)) if i == big else 0.0
        mid = starts[i] + spans[i] / 2
        ox, oy = math.sin(mid) * lift, -math.cos(mid) * lift
        a0, a1 = starts[i], starts[i] + spans[i] * p
        cv.polygon(_sector(cx + ox, cy + oy, R, r_in, a0, a1), cols[i] + (255,))
        if p > 0.05:
            cv.line([_pt(cx + ox, cy + oy, r_in, a0), _pt(cx + ox, cy + oy, R + 2, a0)], bg + (255,), 5, round_caps=False)
        if p > 0.98 and spans[i] >= math.radians(26):
            rr = (r_in + R) / 2 if donut else R * 0.66
            lx, ly = _pt(cx + ox, cy + oy, rr, mid)
            sz = 40 if spans[i] > math.radians(50) else 32
            cv.text(lx, ly, _share(values[i], total), "bold", sz, with_alpha(_on(cols[i]), ease_out_cubic(progress(lt, times[i] + 0.8, 0.3))), anchor="mm")
    if donut:
        ca = ease_out_cubic(progress(lt, times[-1] + 0.8, 0.6))
        if abs(total - 100) < 1e-6 and unit == "%":
            head, sub = _share(values[big], total), labels[big]
        else:
            head, sub = _fmt(total, unit), "Total"
        iw = r_in * 2 * 0.82
        hs = _fit_one(cv, head, "bold", iw, 84, 36)
        ss_ = _fit_one(cv, sub, "regular", iw, 32, 20)
        cv.text(cx, cy - 8, head, "bold", hs, with_alpha(th.text, ca), anchor="mb")
        cv.text(cx, cy + 4, sub, "regular", ss_, with_alpha(th.muted, ca), anchor="ma")
    # legend with the shares
    lx0, lx1 = 1040.0, 1780.0
    row = min(92.0, (ctx.bottom - top - 20) / n)
    ly0 = (top + ctx.bottom) / 2 - row * n / 2 + 4
    for i in range(n):
        q = ease_out_cubic(progress(lt, times[i] + 0.1, 0.5))
        if q <= 0:
            continue
        y = ly0 + (i + 0.5) * row
        cv.rrect(lx0, y - 17, 34, 34, 9, fill=with_alpha(cols[i], q))
        share = _share(values[i], total)
        val = _fmt(values[i], unit)
        has_val = val != share
        sw_ = cv.measure(share, "bold", 46)
        size = _fit_one(cv, labels[i], "semibold", lx1 - lx0 - 70 - sw_ - 24, 40, 24)
        cv.text(lx0 + 56, y - (14 if has_val else 0), labels[i], "semibold", size, with_alpha(th.text, q), anchor="lm")
        if has_val:
            cv.text(lx0 + 56, y + 24, val, "regular", 28, with_alpha(th.muted, q), anchor="lm")
        cv.text(lx1, y, share, "bold", 46, with_alpha(th.accent2 if i == big else th.text, q), anchor="rm")


def _pie_cues(props: Dict[str, Any], dur: float) -> List[float]:
    return _anchor_cues(len(props.get("values") or []), dur, props, 0.12, 0.62)


# ============================================================================= 5. area
def _area_sanitize(props: Dict[str, Any]) -> Dict[str, Any]:
    labels = [_txt(l, 12) for l in _items(props.get("labels"), 8)]
    values = [_num(v) for v in _items(props.get("values"), 8)]
    n = min(len(labels), len(values))
    labels, values = labels[:n], values[:n]
    if n < 3 or any(l == "" for l in labels) or any(v is None for v in values):
        raise ValueError("area needs 3-8 labels with one number each")
    out: Dict[str, Any] = {"labels": labels, "values": values, "unit": _txt(props.get("unit"), 6)}
    hl = _num(props.get("highlight"))
    if hl is not None and 0 <= int(hl) < n:
        out["highlight"] = int(hl)
    if _title(props):
        out["title"] = _title(props)
    if isinstance(props.get("cues"), list):
        out["cues"] = [c for c in (_num(c) for c in props["cues"]) if c is not None][:8]
    return out


def _gradient_fill(cv: Canvas, poly: List[Tuple[float, float]], y_top: float, y_base: float, color, a_top: float, a_bot: float) -> None:
    if len(poly) < 3:
        return
    xs, ys = [p[0] for p in poly], [p[1] for p in poly]
    X0, Y0 = max(0, cv._s(min(xs)) - 1), max(0, cv._s(min(ys)) - 1)
    X1, Y1 = min(cv.im.width, cv._s(max(xs)) + 2), min(cv.im.height, cv._s(max(ys)) + 2)
    if X1 <= X0 or Y1 <= Y0:
        return
    mask = Image.new("L", (X1 - X0, Y1 - Y0), 0)
    ImageDraw.Draw(mask).polygon([(cv._s(x) - X0, cv._s(y) - Y0) for x, y in poly], fill=255)
    rows = np.arange(Y0, Y1, dtype=np.float32)
    t = np.clip((rows - cv._s(y_top)) / max(1.0, cv._s(y_base) - cv._s(y_top)), 0.0, 1.0)
    g = (a_top + (a_bot - a_top) * t)[:, None]
    arr = (np.asarray(mask, np.float32) * g).astype(np.uint8)
    cv.im.paste(tuple(color[:3]), (X0, Y0, X1, Y1), Image.fromarray(arr, "L"))


def _area_front(lt: float, times: List[float]) -> float:
    """How far along the points the line has been drawn (0..n-1), following the reveal times."""
    if lt <= times[0]:
        return 0.0
    for i in range(len(times) - 1):
        if lt < times[i + 1]:
            return i + ease_in_out_cubic(progress(lt, times[i], times[i + 1] - times[i]))
    return float(len(times) - 1)


def _area_draw(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    labels, values, unit = props["labels"], props["values"], props.get("unit", "")
    n = len(values)
    top = _top(cv, th, props, lt)
    x0, x1 = 200.0, 1760.0
    y_top, y_base = top + 60, ctx.bottom - 70
    lo_raw, hi_raw = min(0.0, min(values)), max(0.0, max(values))
    lo, hi, step = _nice(lo_raw, hi_raw + (hi_raw - lo_raw) * 0.08, 4)
    _grid(cv, th, x0, x1, y_top, y_base, lo, hi, step, unit, lt)

    def ypos(v: float) -> float:
        return y_base - (v - lo) / ((hi - lo) or 1.0) * (y_base - y_top)

    px0, px1 = 260.0, 1640.0
    xs = [px0 + (px1 - px0) * i / (n - 1) for i in range(n)]
    pts = [(xs[i], ypos(values[i])) for i in range(n)]
    gp = ease_out_cubic(progress(lt, 0.0, 0.6))
    times = _anchor_cues(n, dur, props, 0.15, 0.62)
    front = _area_front(lt, times)
    k = int(front)
    shown = pts[: k + 1] + ([(pts[k][0] + (pts[k + 1][0] - pts[k][0]) * (front - k), pts[k][1] + (pts[k + 1][1] - pts[k][1]) * (front - k))] if k < n - 1 and front > k else [])
    zero_y = ypos(0.0)
    if len(shown) >= 2:
        _gradient_fill(cv, shown + [(shown[-1][0], zero_y), (shown[0][0], zero_y)], y_top, y_base, th.accent, 0.42, 0.03)
        cv.line(shown, th.accent + (255,), 8)
    hl = props.get("highlight")
    for i in range(n):
        cv.text(xs[i], y_base + 18, labels[i], "regular", 28, with_alpha(th.muted, gp), anchor="ma")
        dp = ease_out_back(progress(lt, times[i] - 0.05, 0.4), 2)
        if dp <= 0:
            continue
        last = i == n - 1
        emph = last or hl == i
        r = (15 if emph else 10) * dp
        cv.ellipse(xs[i], pts[i][1], r, r, fill=(th.accent2 if emph else th.accent) + (255,), outline=(255, 255, 255, 255), width=3)
        a = min(1.0, dp)
        if last:
            continue
        nb = [values[k] for k in (i - 1, i + 1) if 0 <= k < n]
        up = not (len(nb) == 2 and all(values[i] < v for v in nb))      # a dip carries its label underneath, away from the line
        cv.text(xs[i], pts[i][1] + (-28 if up else 28), _fmt(values[i], unit), "bold" if emph else "semibold", 34 if emph else 28,
                with_alpha(th.text if emph else th.muted, a), anchor="mb" if up else "ma")
    if front >= n - 1:  # the last value is called out
        t_last = times[-1]
        a = ease_out_cubic(progress(lt, t_last + 0.1, 0.5))
        lx, ly = pts[-1]
        ring = ((lt - t_last) % 1.6) / 1.6
        cv.ellipse(lx, ly, 15 + 22 * ring, 15 + 22 * ring, outline=with_alpha(th.accent2, (1 - ring) * 0.8 * a), width=3)
        txt = _fmt(values[-1], unit)
        sz = 44
        tw = cv.measure(txt, "bold", sz)
        bw_, bh_ = tw + 44, 72
        bx, by = lx + 34, ly - bh_ / 2
        cv.card(bx, by, bw_, bh_, th, r=22, alpha=a)
        cv.rrect(bx, by, bw_, bh_, 22, outline=with_alpha(th.accent2, a), width=3)
        cv.text(bx + bw_ / 2, by + bh_ / 2, txt, "bold", sz, with_alpha(th.text, a), anchor="mm")


# ============================================================================= 6. stacked
def _st_sanitize(props: Dict[str, Any]) -> Dict[str, Any]:
    labels = [_txt(l, 12) for l in _items(props.get("labels"), 8)]
    series = []
    for s in _items(props.get("series"), 4):
        if not isinstance(s, dict):
            continue
        name = _txt(s.get("name"), 16)
        vals = [_num(v) for v in _items(s.get("values"), 8)]
        if not name or not vals or any(v is None or v < 0 for v in vals):
            continue
        series.append({"name": name, "values": vals})
    if len(series) < 2 or any(l == "" for l in labels):
        raise ValueError("stacked needs 2-4 named series of non-negative numbers and 3-8 labels")
    n = min([len(labels)] + [len(s["values"]) for s in series])
    if n < 3:
        raise ValueError("stacked needs at least 3 categories with a value in every series")
    series = [{"name": s["name"], "values": s["values"][:n]} for s in series]
    if max(sum(s["values"][i] for s in series) for i in range(n)) <= 0:
        raise ValueError("stacked needs some positive values")
    out: Dict[str, Any] = {"labels": labels[:n], "series": series, "unit": _txt(props.get("unit"), 6)}
    if _title(props):
        out["title"] = _title(props)
    if isinstance(props.get("cues"), list):
        out["cues"] = [c for c in (_num(c) for c in props["cues"]) if c is not None][:8]
    return out


def _st_draw(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    labels, series, unit = props["labels"], props["series"], props.get("unit", "")
    n, m = len(labels), len(series)
    top = _top(cv, th, props, lt)
    cols = _series_colors(th, m)
    # legend, left to right in stacking order
    lx = 200.0
    la = ease_out_cubic(progress(lt, 0.1, 0.5))
    for j, s in enumerate(series):
        cv.rrect(lx, top + 6, 26, 26, 7, fill=with_alpha(cols[j], la))
        cv.text(lx + 38, top + 19, s["name"], "regular", 30, with_alpha(th.text, la), anchor="lm")
        lx += 38 + cv.measure(s["name"], "regular", 30) + 44
    totals = [sum(s["values"][i] for s in series) for i in range(n)]
    x0, x1 = 200.0, 1760.0
    y_top, y_base = top + 90, ctx.bottom - 70
    lo, hi, step = _nice(0.0, max(totals) * 1.04, 4)
    _grid(cv, th, x0, x1, y_top, y_base, lo, hi, step, unit, lt)
    slot = (x1 - x0) / n
    bw = min(150.0, slot * 0.56)
    times = _anchor_cues(n, dur, props, 0.15, 0.7)
    gp = ease_out_cubic(progress(lt, 0.0, 0.6))
    for i in range(n):
        p = ease_out_cubic(progress(lt, times[i], 0.9))
        cx = x0 + slot * (i + 0.5)
        y = y_base
        for j, s in enumerate(series):
            v = s["values"][i]
            h = v / hi * (y_base - y_top) * p
            if h > 0.5:
                lastseg = all(series[k]["values"][i] <= 0 for k in range(j + 1, m))
                r = (12 if h > 24 else 4) if lastseg else 0
                cv.rrect(cx - bw / 2, y - h, bw, h, r, fill=cols[j] + (255,))
                if r and h > r * 2:
                    cv.polygon([(cx - bw / 2, y - h / 2), (cx + bw / 2 - 0.5, y - h / 2), (cx + bw / 2 - 0.5, y), (cx - bw / 2, y)], cols[j] + (255,))
                if h >= 44 and bw >= 70 and p > 0.8:
                    sz = _fit_one(cv, _fmt(v, ""), "semibold", bw - 12, 28, 18)
                    cv.text(cx, y - h / 2, _fmt(v, ""), "semibold", sz, with_alpha(_on(cols[j]), ease_out_cubic(progress(p, 0.8, 0.2))), anchor="mm")
            y -= h
        if p > 0.02:
            cv.text(cx, y - 14, _fmt(totals[i] * p, unit), "bold", 34, with_alpha(th.text, min(1.0, p * 1.6)), anchor="mb")
        cv.text(cx, y_base + 18, labels[i], "regular", 28, with_alpha(th.muted, gp), anchor="ma")


# ============================================================================= 7. scatter
def _sc2_sanitize(props: Dict[str, Any]) -> Dict[str, Any]:
    pts = []
    for p in _items(props.get("points"), 24):
        if not isinstance(p, dict):
            continue
        x, y = _num(p.get("x")), _num(p.get("y"))
        if x is None or y is None:
            continue
        row: Dict[str, Any] = {"x": x, "y": y}
        lab = _txt(p.get("label"), 18)
        if lab:
            row["label"] = lab
        pts.append(row)
    pts = pts[:12]
    if len(pts) < 3:
        raise ValueError("scatter needs 3-12 points with numeric x and y")
    out: Dict[str, Any] = {"points": pts, "x_label": _txt(props.get("x_label"), 20), "y_label": _txt(props.get("y_label"), 20)}
    if _title(props):
        out["title"] = _title(props)
    if isinstance(props.get("cues"), list):
        out["cues"] = [c for c in (_num(c) for c in props["cues"]) if c is not None][:12]
    return out


def _sc2_anchors(props: Dict[str, Any]) -> List[str]:
    labs = [p.get("label", "") for p in props.get("points", [])]
    return labs if labs and all(labs) else []        # unnamed points cannot be tied to words


def _axis_range(vals: List[float], n: int) -> Tuple[float, float, float]:
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.08 or abs(hi) * 0.1 or 1.0
    return _nice(0.0 if lo >= 0 and lo - pad < 0 else lo - pad, hi + pad, n)


_LAYOUTS: Dict[Any, List[Optional[Tuple[float, float, str]]]] = {}


def _place_labels(cv: Canvas, pts: List[Tuple[float, float]], labels: List[str], bounds: Tuple[float, float, float, float], radii: List[float]) -> List[Optional[Tuple[float, float, str]]]:
    """Greedy label placement: for each labelled point the first of eight candidate spots that touches no dot, no earlier label and stays in bounds
    (else the spot with the least overlap). Returns (x, y, anchor) per point."""
    key = (tuple((round(x), round(y)) for x, y in pts), tuple(labels), tuple(round(r) for r in radii), bounds)
    if key in _LAYOUTS:
        return _LAYOUTS[key]
    size, h = 30, 38.0
    dots = [(x - r - 4, y - r - 4, x + r + 4, y + r + 4) for (x, y), r in zip(pts, radii)]
    placed: List[Tuple[float, float, float, float]] = []
    result: List[Optional[Tuple[float, float, str]]] = []

    def overlap(a, b) -> float:
        w, hh = min(a[2], b[2]) - max(a[0], b[0]), min(a[3], b[3]) - max(a[1], b[1])
        return w * hh if w > 0 and hh > 0 else 0.0

    for (x, y), lab, r in zip(pts, labels, radii):
        if not lab:
            result.append(None)
            continue
        w = cv.measure(lab, "semibold", size) + 6
        gap = r + 8
        cands = [  # (rect, text anchor point, anchor)
            ((x + gap, y - h / 2, x + gap + w, y + h / 2), (x + gap, y), "lm"),
            ((x - gap - w, y - h / 2, x - gap, y + h / 2), (x - gap, y), "rm"),
            ((x - w / 2, y - gap - h, x + w / 2, y - gap), (x, y - gap), "mb"),
            ((x - w / 2, y + gap, x + w / 2, y + gap + h), (x, y + gap), "ma"),
            ((x + gap * 0.7, y - gap * 0.7 - h, x + gap * 0.7 + w, y - gap * 0.7), (x + gap * 0.7, y - gap * 0.7), "lb"),
            ((x + gap * 0.7, y + gap * 0.7, x + gap * 0.7 + w, y + gap * 0.7 + h), (x + gap * 0.7, y + gap * 0.7), "la"),
            ((x - gap * 0.7 - w, y - gap * 0.7 - h, x - gap * 0.7, y - gap * 0.7), (x - gap * 0.7, y - gap * 0.7), "rb"),
            ((x - gap * 0.7 - w, y + gap * 0.7, x - gap * 0.7, y + gap * 0.7 + h), (x - gap * 0.7, y + gap * 0.7), "ra"),
        ]
        best, best_cost = None, 1e18
        for rect, at, anc in cands:
            cost = sum(overlap(rect, d) for d in dots) + sum(overlap(rect, p) for p in placed) * 2
            out = max(0, bounds[0] - rect[0]) + max(0, rect[2] - bounds[2]) + max(0, bounds[1] - rect[1]) + max(0, rect[3] - bounds[3])
            cost += out * 400
            if cost < best_cost:
                best, best_cost = (rect, at, anc), cost
                if cost == 0:
                    break
        placed.append(best[0])  # type: ignore[index]
        result.append((best[1][0], best[1][1], best[2]))  # type: ignore[index]
    if len(_LAYOUTS) > 32:
        _LAYOUTS.clear()
    _LAYOUTS[key] = result
    return result


def _sc2_draw(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    points = props["points"]
    n = len(points)
    top = _top(cv, th, props, lt)
    x0, x1 = 260.0, 1720.0
    y_top, y_base = top + 40, ctx.bottom - 110
    xlo, xhi, xstep = _axis_range([p["x"] for p in points], 6)
    ylo, yhi, ystep = _axis_range([p["y"] for p in points], 5)
    gp = ease_out_cubic(progress(lt, 0.0, 0.6))
    gc = _axis_col(th)
    for lo, hi, step, horizontal in ((ylo, yhi, ystep, True), (xlo, xhi, xstep, False)):
        v, k = lo, 0
        while v <= hi + step * 1e-6 and k < 14:
            f = (v - lo) / ((hi - lo) or 1.0)
            if horizontal:
                gy = y_base - f * (y_base - y_top)
                cv.line([(x0, gy), (x1, gy)], with_alpha(gc, gp * (1.6 if k == 0 else 1.0)), 2, round_caps=False)
                cv.text(x0 - 16, gy, _tick(v), "regular", 24, with_alpha(th.muted, gp), anchor="rm")
            else:
                gx = x0 + f * (x1 - x0)
                cv.line([(gx, y_top), (gx, y_base)], with_alpha(gc, gp * (1.6 if k == 0 else 0.6)), 2, round_caps=False)
                cv.text(gx, y_base + 14, _tick(v), "regular", 24, with_alpha(th.muted, gp), anchor="ma")
            v += step
            k += 1
    if props.get("y_label"):
        cv.text(x0 - 60, y_top - 44, props["y_label"], "semibold", 28, with_alpha(th.muted, gp), anchor="lm")
    if props.get("x_label"):
        cv.text(x1, y_base + 60, props["x_label"], "semibold", 28, with_alpha(th.muted, gp), anchor="ra")
    pts = [(x0 + (p["x"] - xlo) / ((xhi - xlo) or 1.0) * (x1 - x0), y_base - (p["y"] - ylo) / ((yhi - ylo) or 1.0) * (y_base - y_top)) for p in points]
    radii = [20.0 if i == n - 1 else 14.0 for i in range(n)]
    spots = _place_labels(cv, pts, [p.get("label", "") for p in points], (x0 - 30, y_top - 10, x1 + 70, y_base + 6), radii)
    times = _anchor_cues(n, dur, props, 0.15, 0.7)
    for i, p in enumerate(points):
        q = progress(lt, times[i], 0.5)
        if q <= 0:
            continue
        r = radii[i] * max(0.01, ease_out_back(q, 2))
        emph = i == n - 1
        if emph:
            cv.ellipse(pts[i][0], pts[i][1], r + 9, r + 9, fill=with_alpha(th.accent2, 0.28 * min(1, q * 2)))
        cv.ellipse(pts[i][0], pts[i][1], r, r, fill=(th.accent2 if emph else th.accent) + (255,), outline=(255, 255, 255, 255), width=3)
        sp = spots[i]
        if sp:
            cv.text(sp[0], sp[1], p["label"], "bold" if emph else "semibold", 30, with_alpha(th.text, ease_out_cubic(progress(lt, times[i] + 0.15, 0.4))), anchor=sp[2])


# ============================================================================= registration
def _cues_for(count_key):
    def cues(props: Dict[str, Any], dur: float) -> List[float]:
        return reveal_times(count_key(props), dur, props.get("cues"), first=0.15, last=0.7)
    return cues


ELEMENTS = [
    Element(
        name="scale_compare", family="Data",
        doc=("- scale_compare: {title (<=50), unit (<=10), items: 2-6 [{label (<=24), value (positive number), note (<=40, optional)}]}. Things drawn to the same scale so the viewer "
             "feels the difference (heights of buildings, areas of countries, sizes of animals); each is revealed when named. Values >50x apart get a marked scale break. "
             "Never invent statistics: values only from the grounding notes. Never for a trend over time (use chart) or for unrelated units."),
        sanitize=_sc_sanitize, draw=_sc_draw, cues=_cues_for(lambda p: len(p.get("items") or [])), anchors=lambda p: [i["label"] for i in p.get("items", [])],
        samples=[
            {"title": "How tall is tall?", "unit": "m", "items": [{"label": "Statue of Liberty", "value": 93, "note": "torch to ground"}, {"label": "Big Ben", "value": 96},
                                                                  {"label": "Eiffel Tower", "value": 330}]},
            {"title": "Landmarks against the tallest", "unit": "m", "items": [{"label": "Person", "value": 1.8, "note": "average adult"}, {"label": "Oak tree", "value": 25},
                                                                     {"label": "Statue of Liberty", "value": 93}, {"label": "Eiffel Tower", "value": 330},
                                                                     {"label": "Burj Khalifa", "value": 828, "note": "tallest building"}]},
        ]),
    Element(
        name="pictogram", family="Data",
        doc=("- pictogram: {title (<=50, optional), total (integer 10-100, default 100), filled (0..total), icon: \"person\"|\"dot\"|\"square\"|\"heart\"|\"house\", label (<=70)}. "
             "'1 in 5' or '20%' as a grid of icons where `filled` light up in sequence beside the big fraction. Use for one proportion of a population. "
             "Never invent statistics: only a share stated in the grounding notes. Never for several shares (use pie) or changing values (use chart)."),
        sanitize=_pg_sanitize, draw=_pg_draw, cues=_pg_cues,
        samples=[{"title": "Who is affected", "total": 100, "filled": 20, "icon": "person", "label": "of adults report this every week"},
                 {"total": 30, "filled": 7, "icon": "house", "label": "of the homes in this survey have no heating"}]),
    Element(
        name="bar_race", family="Data",
        doc=("- bar_race: {title (<=50), unit (<=8), periods: 3-10 labels (<=8, e.g. years), series: 3-8 [{label (<=20), values: numbers, one per period}]}. Horizontal bars that grow and "
             "re-rank as the periods advance, with a big period label; the scene time is shared between the periods and the last one holds. Use for who led when. "
             "Never invent statistics: every value from the grounding notes. Never with missing periods or with only one or two series."),
        sanitize=_br_sanitize, draw=_br_draw, cues=_br_cues,
        samples=[{"title": "Largest cities by population", "unit": "M", "periods": ["1950", "1970", "1990", "2010"],
                  "series": [{"label": "Tokyo", "values": [11, 23, 32, 37]}, {"label": "New York", "values": [12, 16, 16, 19]}, {"label": "Mexico City", "values": [3, 9, 15, 20]},
                             {"label": "Sao Paulo", "values": [2, 8, 15, 20]}]},
                 {"title": "Streams per year", "unit": "B", "periods": ["2016", "2017", "2018", "2019", "2020", "2021", "2022", "2023"],
                  "series": [{"label": "Alpha Records", "values": [5, 6, 8, 9, 10, 11, 12, 13]}, {"label": "Beta Music", "values": [4, 7, 9, 12, 14, 15, 15, 16]},
                             {"label": "Gamma", "values": [6, 6, 7, 7, 8, 9, 14, 18]}, {"label": "Delta", "values": [2, 3, 4, 6, 9, 13, 14, 15]},
                             {"label": "Epsilon", "values": [8, 8, 7, 7, 7, 6, 6, 5]}, {"label": "Zeta", "values": [1, 2, 3, 3, 4, 5, 7, 9]}]}]),
    Element(
        name="pie", family="Data",
        doc=("- pie: {title (<=50), labels: 2-6 (<=16), values: positive numbers, unit (<=6), donut: bool}. Parts of one whole; slices appear in order with their share, the largest "
             "is lifted, a donut shows the total or the largest share in the middle. Use for shares that add up to a whole. "
             "Never invent statistics: values from the grounding notes. Never for more than 6 parts, for changes over time, or when the parts are not a whole."),
        sanitize=_pie_sanitize, draw=_pie_draw, cues=_pie_cues, anchors=lambda p: list(p.get("labels", [])),
        samples=[{"title": "Where the electricity comes from", "labels": ["Gas", "Wind", "Nuclear", "Solar", "Other"], "values": [38, 27, 16, 12, 7], "unit": "%", "donut": False},
                 {"title": "Household budget", "labels": ["Housing", "Food", "Transport"], "values": [1200, 600, 400], "unit": "$", "donut": True}]),
    Element(
        name="area", family="Data",
        doc=("- area: {title (<=50), labels: 3-8 (<=12), values: numbers, unit (<=6), highlight: optional index}. One value over time as a filled line that draws on left to right; the "
             "last value is called out. Use for a smooth trend with a story. "
             "Never invent statistics: values from the grounding notes. Never for unordered categories (use chart) or for several series (use stacked)."),
        sanitize=_area_sanitize, draw=_area_draw, cues=_cues_for(lambda p: len(p.get("values") or [])), anchors=lambda p: list(p.get("labels", [])),
        samples=[{"title": "Visitors per year", "labels": ["2018", "2019", "2020", "2021", "2022", "2023"], "values": [4.2, 4.8, 1.1, 1.9, 3.6, 5.1], "unit": "M", "highlight": 2},
                 {"labels": ["Q1", "Q2", "Q3", "Q4"], "values": [120, 150, 210, 340], "unit": "$"}]),
    Element(
        name="stacked", family="Data",
        doc=("- stacked: {title (<=50), labels: 3-8 categories (<=12), series: 2-4 [{name (<=16), values: numbers, one per label}], unit (<=6)}. Stacked bars grow in with a legend and the "
             "total above each. Use for how a total is made of parts across categories or years. "
             "Never invent statistics: values from the grounding notes. Never with negative values, with a single series (use chart), or with values 50x apart."),
        sanitize=_st_sanitize, draw=_st_draw, cues=_cues_for(lambda p: len(p.get("labels") or [])), anchors=lambda p: list(p.get("labels", [])),
        samples=[{"title": "Energy mix by decade", "labels": ["1990", "2000", "2010", "2020"], "unit": "TWh",
                  "series": [{"name": "Fossil", "values": [80, 85, 78, 60]}, {"name": "Nuclear", "values": [15, 18, 17, 14]}, {"name": "Renewable", "values": [5, 8, 22, 48]}]},
                 {"title": "Sales by region", "labels": ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8"], "unit": "$",
                  "series": [{"name": "North", "values": [10, 12, 14, 15, 17, 18, 20, 22]}, {"name": "South", "values": [8, 9, 9, 11, 12, 12, 13, 15]},
                             {"name": "East", "values": [5, 6, 8, 9, 9, 11, 12, 12]}, {"name": "West", "values": [3, 4, 4, 6, 7, 7, 9, 10]}]}]),
    Element(
        name="scatter", family="Data",
        doc=("- scatter: {title (<=50), x_label (<=20), y_label (<=20), points: 3-12 [{label (<=18, optional), x (number), y (number)}]}. Points pop in on labelled axes; the last one is "
             "emphasised. Use to show a relationship or where things sit on two measures. "
             "Never invent statistics: coordinates from the grounding notes. Never for fewer than 3 points, for time series (use area) or for one measure only."),
        sanitize=_sc2_sanitize, draw=_sc2_draw, cues=_cues_for(lambda p: len(p.get("points") or [])), anchors=_sc2_anchors,
        samples=[{"title": "Wealth and health", "x_label": "Income, $ per person", "y_label": "Life expectancy",
                  "points": [{"label": "Chad", "x": 1700, "y": 53}, {"label": "India", "x": 7000, "y": 70}, {"label": "Brazil", "x": 15000, "y": 76},
                             {"label": "Japan", "x": 43000, "y": 85}, {"label": "Norway", "x": 84000, "y": 83}]},
                 {"x_label": "Hours studied", "y_label": "Score",
                  "points": [{"x": 1, "y": 52}, {"x": 2, "y": 58}, {"x": 2.5, "y": 61}, {"x": 3, "y": 64}, {"x": 3.2, "y": 70}, {"x": 4, "y": 72}, {"x": 5, "y": 79},
                             {"x": 5.5, "y": 77}, {"x": 6, "y": 85}, {"x": 7, "y": 88}, {"x": 7.1, "y": 90}, {"x": 8, "y": 93}]}]),
]
