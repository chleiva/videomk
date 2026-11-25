"""Compare, list and process elements: versus, table, ranking, matrix, flowchart, sequence.

All six reveal their parts one by one (their `anchors` tie each reveal to the word that names it), keep everything on screen at the end, and are drawn from
sanitized props only. Layout work (column widths, label placement, graph layering) is cached on the props.
"""
import json
import math
import unicodedata
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw

from ...canvas import Canvas, load_font, partial_polyline, with_alpha
from ...easing import ease_in_out_cubic, ease_out_back, ease_out_cubic, progress, reveal_times
from ..base import CONTENT_TOP, heading
from ..registry import Element


# ------------------------------------------------------------------ shared helpers
def _t(v: Any, n: int) -> str:
    """Clean, clipped text: no layout characters, collapsed whitespace, never longer than n."""
    if v is None or isinstance(v, (dict, list, tuple, set, bool)):
        return ""
    s = "".join(c if not unicodedata.category(c).startswith("C") else " " for c in str(v))
    return " ".join(s.split())[:n].rstrip()


def _num(v: Any) -> Optional[float]:
    if isinstance(v, bool) or v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _list(v: Any) -> list:
    return list(v) if isinstance(v, (list, tuple)) else []


def _key(*parts: Any) -> str:
    return json.dumps(parts, sort_keys=True, ensure_ascii=False)


_MCV = Canvas(8, 8)        # measuring only, so layout can be cached without a frame canvas


def _meas(s: str, weight: str, size: float) -> float:
    return load_font(weight, int(round(size * 2))).getlength(s) / 2


def _top(cv: Canvas, th, props: Dict[str, Any], lt: float, size: float = 56) -> float:
    """Draws the optional title; returns the y where content may start."""
    if props.get("title"):
        return heading(cv, th, props["title"], lt, y=CONTENT_TOP + 10, size=size)
    return CONTENT_TOP + 30


def _white_on_accent(th) -> Tuple[int, int, int]:
    return (255, 255, 255)


def _tint(th, a: float) -> Tuple[int, int, int, int]:
    return with_alpha(th.accent, a)


def _arrowhead(cv: Canvas, tip: Tuple[float, float], frm: Tuple[float, float], color, size: float = 20) -> None:
    ang = math.atan2(tip[1] - frm[1], tip[0] - frm[0])
    cv.polygon([tip, (tip[0] - size * math.cos(ang - 0.42), tip[1] - size * math.sin(ang - 0.42)),
                (tip[0] - size * math.cos(ang + 0.42), tip[1] - size * math.sin(ang + 0.42))], fill=color)


def _pull_back(pts: List[Tuple[float, float]], d: float) -> List[Tuple[float, float]]:
    """Shorten the end of a polyline by d so a line does not poke through its arrowhead."""
    pts = list(pts)
    (x1, y1), (x2, y2) = pts[-2], pts[-1]
    L = math.hypot(x2 - x1, y2 - y1)
    if L > d + 1:
        pts[-1] = (x2 - (x2 - x1) / L * d, y2 - (y2 - y1) / L * d)
    return pts


def _arrow(cv: Canvas, pts: List[Tuple[float, float]], p: float, color, width: float = 5, dashed: bool = False) -> None:
    """A poly-line arrow drawn on from its start; the head appears with the last bit."""
    if p <= 0 or len(pts) < 2:
        return
    shown = partial_polyline(_pull_back(pts, 16), p)
    if dashed:
        _dashed(cv, shown, color, width)
    else:
        cv.line(shown, color, width)
    if p >= 0.97:
        _arrowhead(cv, pts[-1], pts[-2], color, 22)


def _dashed(cv: Canvas, pts: List[Tuple[float, float]], color, width: float, dash: float = 18, gap: float = 12) -> None:
    for i in range(len(pts) - 1):
        (x1, y1), (x2, y2) = pts[i], pts[i + 1]
        L = math.hypot(x2 - x1, y2 - y1)
        if L < 1:
            continue
        ux, uy = (x2 - x1) / L, (y2 - y1) / L
        d = 0.0
        while d < L:
            e = min(d + dash, L)
            cv.line([(x1 + ux * d, y1 + uy * d), (x1 + ux * e, y1 + uy * e)], color, width, round_caps=False)
            d += dash + gap


def _chip(cv: Canvas, th, text: str, cx: float, cy: float, size: float, alpha: float, weight: str = "semibold") -> None:
    """A small label on a backing so a line behind it never hurts legibility."""
    if alpha <= 0.02:
        return
    w = cv.measure(text, weight, size) + 24
    h = size * 1.5
    cv.rrect(cx - w / 2, cy - h / 2, w, h, h / 2, fill=with_alpha(th.bg_top, 0.9 * alpha))
    cv.text(cx, cy, text, weight, size, with_alpha(th.text, alpha), anchor="mm")


def _fit_lines(cv: Canvas, text: str, weight: str, max_w: float, max_h: float, start: float, min_size: float = 22):
    size, lines = cv.fit_text(text, weight, max_w, max_h, start, min_size)
    return size, lines


def _draw_block(cv: Canvas, lines: List[str], weight: str, size: float, cx: float, cy: float, color, anchor_x: str = "m", line_h: float = 1.18) -> None:
    lh = size * line_h
    y0 = cy - (len(lines) - 1) * lh / 2
    for i, ln in enumerate(lines):
        cv.text(cx, y0 + i * lh, ln, weight, size, color, anchor=anchor_x + "m")


def _fit_draw(cv: Canvas, text: str, weight: str, cx: float, cy: float, w: float, h: float, start: float, color, min_size: float = 22, align: str = "m") -> None:
    size, lines = cv.fit_text(text, weight, w, h, start, min_size)
    if align == "m":
        _draw_block(cv, lines, weight, size, cx, cy, color)
    else:                               # left aligned: cx is the left edge
        lh = size * 1.18
        y0 = cy - (len(lines) - 1) * lh / 2
        for i, ln in enumerate(lines):
            cv.text(cx, y0 + i * lh, ln, weight, size, color, anchor="lm")


def _clip_w(cv: Canvas, text: str, weight: str, size: float, max_w: float) -> str:
    while cv.measure(text, weight, size) > max_w and len(text) > 1:
        text = text[:-2].rstrip() + "…" if not text.endswith("…") else text[:-2].rstrip() + "…"
    return text


def _end_cue(times: List[float], dur: float, extra: float) -> float:
    """When a closing element (verdict, highlight) appears: just after the last reveal, never past the end."""
    last = times[-1] if times else 0.0
    return min(last + extra, max(last + 0.15, dur - 0.9))


# ------------------------------------------------------------------ versus
def _san_versus(p: Dict[str, Any]) -> Dict[str, Any]:
    def side(v: Any) -> Dict[str, str]:
        if isinstance(v, str):
            v = {"name": v}
        if not isinstance(v, dict):
            raise ValueError("versus needs two sides")
        name = _t(v.get("name"), 24)
        if not name:
            raise ValueError("versus side without a name")
        out = {"name": name}
        tag = _t(v.get("tagline"), 40)
        if tag:
            out["tagline"] = tag
        return out

    a, b = side(p.get("a")), side(p.get("b"))
    rows = []
    for r in _list(p.get("rows")):
        if not isinstance(r, dict):
            continue
        label, ra, rb = _t(r.get("label"), 24), _t(r.get("a"), 30), _t(r.get("b"), 30)
        if label and (ra or rb):
            rows.append({"label": label, "a": ra or "-", "b": rb or "-"})
    rows = rows[:5]
    if len(rows) < 2:
        raise ValueError("versus needs 2+ rows")
    out: Dict[str, Any] = {"a": a, "b": b, "rows": rows}
    verdict = _t(p.get("verdict"), 80)
    if verdict:
        out["verdict"] = verdict
    w = p.get("winner")
    w = w.strip().lower() if isinstance(w, str) else ""
    if w not in ("a", "b"):
        w = "a" if w and w == a["name"].lower() else "b" if w and w == b["name"].lower() else ""
    if w:
        out["winner"] = w
    return out


def _versus_times(props: Dict[str, Any], dur: float) -> List[float]:
    return reveal_times(len(props["rows"]), dur, props.get("cues"), first=0.2, last=0.7)


def versus_cues(props: Dict[str, Any], dur: float) -> List[float]:
    times = _versus_times(props, dur)
    if props.get("verdict"):
        times = times + [_end_cue(times, dur, 0.8)]
    return [min(t, dur) for t in times]


def _draw_versus_land(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th, ctx) -> None:
    rows = props["rows"]
    n = len(rows)
    times = _versus_times(props, dur)
    verdict = props.get("verdict", "")
    win = props.get("winner", "")
    top = CONTENT_TOP + 30
    bottom = ctx.bottom - 10
    head_h = 150
    vh = 92 if verdict else 0
    rows_top = top + head_h
    rows_bottom = bottom - (vh + 22 if verdict else 0)
    row_h = min(124.0, (rows_bottom - rows_top - 12) / n)
    panel_h = head_h + n * row_h + 12
    pw = 690
    xs = {"a": 105, "b": 1920 - 105 - pw}
    cols = {"a": th.accent, "b": th.accent2}
    after = _end_cue(times, dur, 0.8)
    t_verdict = after
    t_win = after + (0.55 if verdict else 0.0)
    p0 = ease_out_cubic(progress(lt, 0.05, 0.55))

    for side in ("a", "b"):
        x = xs[side]
        slide = (1 - p0) * (-70 if side == "a" else 70)
        cv.card(x + slide, top, pw, panel_h, th, alpha=p0)
        cv.rrect(x + slide + 36, top + 20, pw - 72, 8, 4, fill=with_alpha(cols[side], p0))
        s = props[side]
        tag = s.get("tagline", "")
        ny = top + (70 if tag else 88)
        _fit_draw(cv, s["name"], "bold", x + pw / 2 + slide, ny, pw - 80, 76, 64, with_alpha(th.text, p0), 34)
        if tag:
            _fit_draw(cv, tag, "regular", x + pw / 2 + slide, top + 120, pw - 80, 40, 34, with_alpha(th.muted, p0), 22)
    vp = ease_out_back(progress(lt, 0.3, 0.5), 1.8)
    r = 46 * max(0.01, vp)
    cv.ellipse(960, top + 76, r, r, fill=with_alpha(th.bg_top, 1.0), outline=with_alpha(th.muted, min(1, vp)), width=3)
    if vp > 0.5:
        cv.text(960, top + 76, "VS", "bold", 38 * min(1.0, vp), with_alpha(th.text, min(1.0, vp)), anchor="mm")

    for i, row in enumerate(rows):
        p = ease_out_cubic(progress(lt, times[i], 0.5))
        if p <= 0:
            continue
        y = rows_top + i * row_h
        cy = y + row_h / 2
        if i:
            for side in ("a", "b"):
                cv.line([(xs[side] + 40, y), (xs[side] + pw - 40, y)], with_alpha(th.card_outline, p), 2, round_caps=False)
        # the row label sits between the two panels, on the divide
        lw = 336
        size, lines = cv.fit_text(row["label"], "semibold", lw - 40, row_h - 26, 34, 22)
        cv.rrect(960 - lw / 2, cy - row_h / 2 + 8, lw, row_h - 16, (row_h - 16) / 2, fill=with_alpha(th.bg_top, 0.92 * p), outline=with_alpha(th.card_outline, p), width=2)
        _draw_block(cv, lines, "semibold", size, 960, cy, with_alpha(th.muted, p))
        for side, off in (("a", -1), ("b", 1)):
            weight = "bold" if win == side and lt >= t_win else "semibold"
            cx = xs[side] + pw / 2 + off * (1 - p) * 40
            cell_w = pw - 90 if side == "a" else pw - 90
            _fit_draw(cv, row[side], weight, cx, cy, cell_w, row_h - 14, 50, with_alpha(th.text, p), 24)

    if win:
        wp = ease_out_cubic(progress(lt, t_win, 0.6))
        if wp > 0:
            x = xs[win]
            cv.rrect(x - 2, top - 2, pw + 4, panel_h + 4, 30, outline=with_alpha(th.accent, wp), width=7)
            bx, by = x + pw - 48, top + 8
            br = 34 * ease_out_back(wp, 1.6)
            if br > 1:
                cv.ellipse(bx, by, br, br, fill=th.accent, outline=with_alpha(th.bg_top, 1), width=4)
                s = br / 34
                cv.line([(bx - 14 * s, by + 1 * s), (bx - 4 * s, by + 11 * s), (bx + 15 * s, by - 10 * s)], (255, 255, 255), 7 * s)

    if verdict:
        vp2 = ease_out_cubic(progress(lt, t_verdict, 0.55))
        if vp2 > 0:
            y = rows_bottom + 22 + (1 - vp2) * 30
            cv.rrect(105, y, 1710, vh, 24, fill=with_alpha(th.accent, 0.20 * vp2), outline=with_alpha(th.accent, vp2), width=3)
            _fit_draw(cv, verdict, "bold", 960, y + vh / 2, 1620, vh - 16, 46, with_alpha(th.text, vp2), 26)


def draw_versus(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th, ctx) -> None:
    """16:9 keeps its original layout untouched; the other shapes are laid out natively (see the tall section below)."""
    if ctx.frame.landscape:
        _draw_versus_land(cv, props, lt, dur, th, ctx)
    else:
        _draw_versus_tall(cv, props, lt, dur, th, ctx)

VERSUS = Element(
    name="versus", family="Compare",
    doc=("- versus: {a: {name (<=24), tagline (<=40, optional)}, b: {same}, rows: 2-5 [{label (<=24), a (<=30), b (<=30)}], verdict (<=80, optional), winner: optional \"a\"|\"b\"}. "
         "Two things side by side, matching rows revealed one by one in the order named. Use when the narration compares two options on the same points. "
         "Fair by default: set winner only if the narration clearly declares one. Never invent facts, specs or numbers; never more than two sides."),
    sanitize=_san_versus, draw=draw_versus, formats=("16:9", "9:16", "1:1", "4:5"), cues=versus_cues, anchors=lambda p: [r["label"] for r in p["rows"]],
    samples=[
        {"a": {"name": "Electric car", "tagline": "Quiet and cheap to run"}, "b": {"name": "Petrol car", "tagline": "Fills up in minutes"},
         "rows": [{"label": "Running cost", "a": "Low", "b": "High"}, {"label": "Refuelling", "a": "Hours at home", "b": "5 minutes"},
                  {"label": "Servicing", "a": "Few moving parts", "b": "Regular oil changes"}],
         "verdict": "It depends how far you drive each day"},
        {"a": {"name": "Cats"}, "b": {"name": "Dogs"},
         "rows": [{"label": "Attention", "a": "Independent", "b": "Needs company"}, {"label": "Exercise", "a": "Self-managed", "b": "Daily walks"},
                  {"label": "Training", "a": "Limited", "b": "Very trainable"}, {"label": "Space needed", "a": "Small flat is fine", "b": "Room to roam"},
                  {"label": "Lifespan", "a": "12 to 18 years", "b": "10 to 13 years"}],
         "verdict": "Both are good companions", "winner": "a"},
    ],
)


# ------------------------------------------------------------------ table
def _san_table(p: Dict[str, Any]) -> Dict[str, Any]:
    cols = [_t(c, 18) for c in _list(p.get("columns"))[:4]]
    if len(cols) < 2:
        raise ValueError("table needs 2+ columns")
    rows, index_map = [], {}
    for i, r in enumerate(_list(p.get("rows"))):
        if not isinstance(r, (list, tuple)):
            continue
        cells = [_t(c, 22) for c in list(r)[: len(cols)]]
        cells += [""] * (len(cols) - len(cells))
        if not any(cells):
            continue
        if len(rows) < 6:
            index_map[i] = len(rows)
            rows.append(cells)
    if len(rows) < 2:
        raise ValueError("table needs 2+ rows")
    out: Dict[str, Any] = {"columns": cols, "rows": rows}
    title = _t(p.get("title"), 50)
    if title:
        out["title"] = title
    h = p.get("highlight")
    if isinstance(h, dict):
        r, c = _num(h.get("row")), _num(h.get("col"))
    else:
        r, c = _num(h), None
    if r is not None and int(r) in index_map:
        hl: Dict[str, int] = {"row": index_map[int(r)]}
        if c is not None and 0 <= int(c) < len(cols):
            hl["col"] = int(c)
        out["highlight"] = hl
    return out


@lru_cache(maxsize=32)
def _table_geometry(key: str) -> Tuple[int, List[float], float]:
    cols, rows = json.loads(key)
    n = len(cols)
    for fs in range(52, 29, -2):
        nat = [max([_meas(cols[j], "semibold", fs * 0.8)] + [_meas(r[j], "semibold" if j == 0 else "regular", fs) for r in rows]) + 64 for j in range(n)]
        if sum(nat) <= 1640:
            break
    total = min(1640.0, max(sum(nat), 1400.0 if n > 2 else 1000.0))
    widths = [w * total / sum(nat) for w in nat]
    return fs, widths, total


def table_cues(props: Dict[str, Any], dur: float) -> List[float]:
    times = reveal_times(len(props["rows"]), dur, props.get("cues"), first=0.2, last=0.7)
    if props.get("highlight"):
        times = times + [_end_cue(times, dur, 0.8)]
    return [min(t, dur) for t in times]


def _draw_table_land(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th, ctx) -> None:
    cols, rows = props["columns"], props["rows"]
    n = len(rows)
    top = _top(cv, th, props, lt) + 6
    fs, widths, total = _table_geometry(_key(cols, rows))
    head_h = 84.0
    row_h = min(124.0, (ctx.bottom - 12 - top - head_h - 20) / n)
    x0 = (1920 - total) / 2
    height = head_h + n * row_h + 12
    times = reveal_times(n, dur, props.get("cues"), first=0.2, last=0.7)
    t_hl = _end_cue(times, dur, 0.8)
    p0 = ease_out_cubic(progress(lt, 0.1, 0.5))
    cv.card(x0, top, total, height, th, r=26, alpha=p0)
    cv.rrect(x0 + 8, top + 8, total - 16, head_h - 8, 20, fill=with_alpha(th.accent2, 0.16 * p0))
    xs = [x0]
    for w in widths:
        xs.append(xs[-1] + w)
    hs = max(24.0, min(36.0, fs * 0.8))
    for j, c in enumerate(cols):
        _fit_draw(cv, c, "semibold", xs[j] + 28, top + head_h / 2 + 2, widths[j] - 44, head_h - 14, hs, with_alpha(th.accent2, p0), 20, align="l")
    hl = props.get("highlight")
    hp = ease_out_cubic(progress(lt, t_hl, 0.4)) if hl else 0.0
    pulse = math.sin(math.pi * progress(lt, t_hl, 1.1)) if hl else 0.0
    for i, row in enumerate(rows):
        p = ease_out_cubic(progress(lt, times[i], 0.5))
        if p <= 0:
            continue
        y = top + head_h + 4 + i * row_h
        if i % 2 == 0:
            cv.rrect(x0 + 8, y, total - 16, row_h, 14, fill=with_alpha(th.text, 0.045 * p))
        if hl and hl["row"] == i and hp > 0:
            hx0, hx1 = (xs[hl["col"]] + 6, xs[hl["col"] + 1] - 6) if "col" in hl else (x0 + 8, x0 + total - 8)
            grow = 5 * pulse
            cv.rrect(hx0 - grow, y - grow, hx1 - hx0 + 2 * grow, row_h + 2 * grow, 16, fill=with_alpha(th.accent, (0.20 + 0.14 * pulse) * hp),
                     outline=with_alpha(th.accent, hp), width=4)
        for j, cell in enumerate(row):
            if not cell:
                continue
            on = hl and hl["row"] == i and hp > 0.5 and ("col" not in hl or hl["col"] == j)
            _fit_draw(cv, cell, "bold" if (j == 0 or on) else "regular", xs[j] + 28 + (1 - p) * 28, y + row_h / 2, widths[j] - 44, row_h - 12, fs,
                      with_alpha(th.text, p), 24, align="l")


def draw_table(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th, ctx) -> None:
    """16:9 keeps its original layout untouched; the other shapes are laid out natively (see the tall section below)."""
    if ctx.frame.landscape:
        _draw_table_land(cv, props, lt, dur, th, ctx)
    else:
        _draw_table_tall(cv, props, lt, dur, th, ctx)

TABLE = Element(
    name="table", family="Lists",
    doc=("- table: {title (<=50), columns: 2-4 strings (<=18), rows: 2-6 lists of cells (<=22 each, one per column), highlight: optional row index (from 0) or {row, col}}. "
         "A clean grid, rows revealed in order, the highlighted row or cell pulses at the end. Use for specs, prices, schedules and features by category. "
         "Keep cells to a few words. Never invent figures; never more than 6 rows or 4 columns."),
    sanitize=_san_table, draw=draw_table, formats=("16:9", "9:16", "1:1", "4:5"), cues=table_cues, anchors=lambda p: [r[0] or " ".join(r) for r in p["rows"]],
    samples=[
        {"title": "Streaming plans", "columns": ["Plan", "Screens", "Quality", "Price"],
         "rows": [["Basic", "1", "HD", "$7"], ["Standard", "2", "Full HD", "$11"], ["Premium", "4", "4K", "$17"]], "highlight": 1},
        {"title": "The inner planets", "columns": ["Planet", "Day length", "Moons"],
         "rows": [["Mercury", "59 days", "0"], ["Venus", "243 days", "0"], ["Earth", "24 hours", "1"], ["Mars", "24.6 hours", "2"], ["Jupiter", "10 hours", "95"],
                  ["Saturn", "10.7 hours", "146"]], "highlight": {"row": 2, "col": 1}},
    ],
)


# ------------------------------------------------------------------ ranking
def _san_ranking(p: Dict[str, Any]) -> Dict[str, Any]:
    items = []
    for it in _list(p.get("items")):
        if isinstance(it, str):
            it = {"label": it}
        if not isinstance(it, dict):
            continue
        label = _t(it.get("label"), 40)
        if not label:
            continue
        d = {"label": label}
        v = it.get("value")
        value = _t(v if not isinstance(v, bool) else None, 14)
        if value:
            d["value"] = value
        note = _t(it.get("note"), 60)
        if note:
            d["note"] = note
        items.append(d)
    items = items[:7]
    if len(items) < 3:
        raise ValueError("ranking needs 3+ items")
    out: Dict[str, Any] = {"items": items}
    title = _t(p.get("title"), 50)
    if title:
        out["title"] = title
    return out


def _ranking_times(props: Dict[str, Any], dur: float) -> List[float]:
    # times[k] is when the k-th revealed item appears: the LAST item of the list first, #1 last
    return reveal_times(len(props["items"]), dur, props.get("cues"), first=0.14, last=0.74)


def ranking_cues(props: Dict[str, Any], dur: float) -> List[float]:
    return [min(t, dur) for t in _ranking_times(props, dur)]


def _draw_ranking_land(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th, ctx) -> None:
    items = props["items"]
    n = len(items)
    top = _top(cv, th, props, lt, 52) - 6
    bottom = ctx.bottom - 8
    gap = 10.0
    u = min(140.0, (bottom - top - (n - 1) * gap) / (n - 1 + 1.35))
    h1 = u * 1.35
    times = _ranking_times(props, dur)
    x0, w = 200, 1520
    ys, y = [], top
    for i in range(n):
        ys.append(y)
        y += (h1 if i == 0 else u) + gap
    for k in range(n):                           # reveal order: k = 0 is the last item
        i = n - 1 - k
        p = progress(lt, times[k], 0.6)
        if p <= 0:
            continue
        pe = ease_out_cubic(p)
        it = items[i]
        first = i == 0
        h = h1 if first else u
        y = ys[i] + (1 - pe) * 46
        a = pe
        has_note = bool(it.get("note"))
        cv.shadow(x0, y, w, h, 24, alpha=th.shadow_alpha * a * (1.2 if first else 0.8))
        fill = with_alpha(th.accent, 0.22 * a) if first else with_alpha(th.card, a)
        if th.name == "paper" and not first:
            fill = (255, 255, 255, int(255 * a))
        cv.rrect(x0, y, w, h, 24, fill=fill, outline=with_alpha(th.accent if first else th.card_outline, a), width=4 if first else 1.5)
        # the big number
        pop = ease_out_back(progress(lt, times[k], 0.55), 2.0)
        d = h * 0.76 * max(0.05, min(1.25, pop))
        bx, by = x0 + 20 + h * 0.4, y + h / 2
        cv.ellipse(bx, by, d / 2, d / 2, fill=th.accent if first else with_alpha(th.accent, 0.9 * a), outline=None)
        ns = d * (0.56 if i < 9 else 0.45)
        cv.text(bx, by + ns * 0.04, str(i + 1), "bold", ns, with_alpha((255, 255, 255), a), anchor="mm")
        tx = x0 + 40 + h * 0.8 + 6
        val = it.get("value", "")
        vw = 0.0
        if val:
            vs = min(60.0, h * 0.5) * (1.1 if first else 1.0)
            vs = min(vs, 62)
            while _meas(val, "bold", vs) > 330 and vs > 24:
                vs -= 2
            vw = _meas(val, "bold", vs)
            cv.text(x0 + w - 36, y + h / 2, val, "bold", vs, with_alpha(th.accent2, a), anchor="rm")
        lw = x0 + w - 36 - tx - (vw + 36 if val else 0)
        if has_note and h < 92:                   # a short row: the note follows the label on the same line
            lsz = min(40.0, h * 0.5)
            lab = it["label"]
            while _meas(lab, "semibold", lsz) > lw * 0.62 and lsz > 24:
                lsz -= 2
            lw1 = min(_meas(lab, "semibold", lsz), lw * 0.62)
            _fit_draw(cv, lab, "semibold", tx, y + h / 2, lw * 0.62, h - 10, lsz, with_alpha(th.text, a), 20, align="l")
            _fit_draw(cv, it["note"], "regular", tx + lw1 + 26, y + h / 2, lw - lw1 - 26, h - 10, 28, with_alpha(th.muted, a), 18, align="l")
        elif has_note:
            lsz = min(52.0 if first else 44.0, h * 0.44)
            nsz = min(30.0, h * 0.28)
            cv.text(tx, y + h / 2 - nsz * 0.62, _clip_w(cv, it["label"], "bold" if first else "semibold", lsz, lw), "bold" if first else "semibold", lsz, with_alpha(th.text, a), anchor="lm")
            cv.text(tx, y + h / 2 + lsz * 0.62, _clip_w(cv, it["note"], "regular", nsz, lw), "regular", nsz, with_alpha(th.muted, a), anchor="lm")
        else:
            _fit_draw(cv, it["label"], "bold" if first else "semibold", tx, y + h / 2, lw, h - 14, min(54.0, h * 0.5) * (1.2 if first else 1.0), with_alpha(th.text, a), 22, align="l")
        if first and p > 0:                       # #1 lands with a ring that expands once
            rp = progress(lt, times[k] + 0.1, 0.9)
            if 0 < rp < 1:
                cv.rrect(x0 - 14 * rp, y - 14 * rp, w + 28 * rp, h + 28 * rp, 24 + 14 * rp, outline=with_alpha(th.accent, 0.8 * (1 - rp)), width=5)


def draw_ranking(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th, ctx) -> None:
    """16:9 keeps its original layout untouched; the other shapes are laid out natively (see the tall section below)."""
    if ctx.frame.landscape:
        _draw_ranking_land(cv, props, lt, dur, th, ctx)
    else:
        _draw_ranking_tall(cv, props, lt, dur, th, ctx)

RANKING = Element(
    name="ranking", family="Lists",
    doc=("- ranking: {title (<=50), items: 3-7 [{label (<=40), value (<=14, optional), note (<=60, optional)}]} listed BEST FIRST (#1 first). "
         "The scene counts down: the last item appears first, #1 last and emphasised, all stay stacked. Use for top-N lists and countdowns when the narration "
         "names them from last to first. Never invent values or an order the sources do not give."),
    sanitize=_san_ranking, draw=draw_ranking, formats=("16:9", "9:16", "1:1", "4:5"), cues=ranking_cues, anchors=lambda p: [it["label"] for it in reversed(p["items"])],
    samples=[
        {"title": "Most visited countries", "items": [{"label": "France", "value": "100M", "note": "Tourists a year"}, {"label": "Spain", "value": "85M"},
                                                       {"label": "United States", "value": "79M"}, {"label": "Italy", "value": "65M"}]},
        {"title": "Longest rivers", "items": [{"label": "Nile", "value": "6,650 km"}, {"label": "Amazon", "value": "6,400 km", "note": "Largest by volume"},
                                              {"label": "Yangtze", "value": "6,300 km"}, {"label": "Mississippi", "value": "6,275 km"},
                                              {"label": "Yenisei", "value": "5,539 km"}, {"label": "Yellow River", "value": "5,464 km"},
                                              {"label": "Ob-Irtysh", "value": "5,410 km", "note": "Flows through Siberia"}]},
    ],
)


# ------------------------------------------------------------------ matrix
def _san_matrix(p: Dict[str, Any]) -> Dict[str, Any]:
    def axis(v: Any) -> Dict[str, str]:
        if not isinstance(v, dict):
            raise ValueError("matrix needs both axes")
        low, high = _t(v.get("low"), 18), _t(v.get("high"), 18)
        if not low or not high:
            raise ValueError("matrix axis needs low and high")
        return {"low": low, "high": high}

    xa, ya = axis(p.get("x_axis")), axis(p.get("y_axis"))
    items = []
    for it in _list(p.get("items")):
        if not isinstance(it, dict):
            continue
        label, x, y = _t(it.get("label"), 24), _num(it.get("x")), _num(it.get("y"))
        if label and x is not None and y is not None:
            items.append({"label": label, "x": round(min(1.0, max(0.0, x)), 3), "y": round(min(1.0, max(0.0, y)), 3)})
    items = items[:8]
    if len(items) < 2:
        raise ValueError("matrix needs 2+ items")
    out: Dict[str, Any] = {"x_axis": xa, "y_axis": ya, "items": items}
    title = _t(p.get("title"), 50)
    if title:
        out["title"] = title
    q = [_t(c, 24) for c in _list(p.get("quadrants"))[:4]]
    if len(q) == 4 and any(q):
        out["quadrants"] = q
    return out


_MX0, _MX1 = 400, 1780


@lru_cache(maxsize=32)
def _matrix_layout(key: str, y0: float, y1: float, mx0: float = _MX0, mx1: float = _MX1, lsz: float = 32, padx: float = 70) -> Tuple[list, list]:
    """Dot positions (pushed apart if they would sit on each other) and, for each, where its label goes with the least overlap."""
    items, quads = json.loads(key)
    W, H = mx1 - mx0, y1 - y0
    pady = 56
    dots = []
    for i, it in enumerate(items):
        x = mx0 + padx + it["x"] * (W - 2 * padx)
        y = y1 - pady - it["y"] * (H - 2 * pady)
        for _ in range(4):
            for (ox, oy) in dots:
                d = math.hypot(x - ox, y - oy)
                if d < 34:
                    ang = (i * 2.4) if d < 0.5 else math.atan2(y - oy, x - ox)
                    x, y = ox + math.cos(ang) * 34, oy + math.sin(ang) * 34
        dots.append((x, y))
    lh = lsz + 10
    obstacles: List[Tuple[float, float, float, float]] = [(x - 24, y - 24, x + 24, y + 24) for x, y in dots]
    if quads:
        for k, qt in enumerate(quads):
            if not qt:
                continue
            w = min(420, _meas(qt, "semibold", 28)) + 10
            qx = mx0 + 18 if k % 2 == 0 else mx1 - 18 - w
            qy = y0 + 14 if k < 2 else y1 - 14 - 36
            obstacles.append((qx, qy, qx + w, qy + 36))
    placed: List[Tuple[float, float, float, float]] = []
    out = []
    for i, it in enumerate(items):
        x, y = dots[i]
        w = _meas(it["label"], "semibold", lsz)
        cands = [(x + 26, y - lh / 2), (x - 26 - w, y - lh / 2), (x - w / 2, y - 28 - lh), (x - w / 2, y + 28),
                 (x + 22, y - lh - 14), (x + 22, y + 14), (x - 22 - w, y - lh - 14), (x - 22 - w, y + 14),
                 (x + 26, y - lh / 2 - 44), (x + 26, y - lh / 2 + 44), (x - 26 - w, y - lh / 2 - 44), (x - 26 - w, y - lh / 2 + 44)]
        best, best_s = cands[0], 1e18
        for ci, (lx, ly) in enumerate(cands):
            r = (lx, ly, lx + w, ly + lh)
            s = ci * 4.0
            for o in obstacles[:len(dots)] + obstacles[len(dots):] + placed:
                if o == (x - 24, y - 24, x + 24, y + 24):
                    continue                                    # its own dot
                ox = min(r[2], o[2]) - max(r[0], o[0])
                oy = min(r[3], o[3]) - max(r[1], o[1])
                if ox > 0 and oy > 0:
                    s += ox * oy + 2000
            ox_out = max(0, mx0 + 6 - r[0]) + max(0, r[2] - (mx1 - 6))
            oy_out = max(0, y0 + 6 - r[1]) + max(0, r[3] - (y1 - 6))
            s += (ox_out + oy_out) * 400
            if s < best_s:
                best, best_s = (lx, ly), s
        placed.append((best[0], best[1], best[0] + w, best[1] + lh))
        out.append((best[0], best[1], w))
    return dots, out


def matrix_cues(props: Dict[str, Any], dur: float) -> List[float]:
    return [min(t, dur) for t in reveal_times(len(props["items"]), dur, props.get("cues"), first=0.3, last=0.75)]


def _draw_matrix_land(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th, ctx) -> None:
    items = props["items"]
    top = _top(cv, th, props, lt) - 8
    y0, y1 = top, ctx.bottom - 86
    dots, labels = _matrix_layout(_key(items, props.get("quadrants")), y0, y1)
    times = reveal_times(len(items), dur, props.get("cues"), first=0.3, last=0.75)
    p0 = ease_out_cubic(progress(lt, 0.1, 0.5))
    cv.card(_MX0, y0, _MX1 - _MX0, y1 - y0, th, r=24, alpha=p0)
    mx, my = (_MX0 + _MX1) / 2, (y0 + y1) / 2
    cv.rrect(mx, y0 + 3, _MX1 - mx - 3, my - y0 - 3, 20, fill=with_alpha(th.accent, 0.07 * p0))
    _dashed(cv, [(mx, y0 + 16), (mx, y1 - 16)], with_alpha(th.muted, 0.45 * p0), 3, 14, 12)
    _dashed(cv, [(_MX0 + 16, my), (_MX1 - 16, my)], with_alpha(th.muted, 0.45 * p0), 3, 14, 12)
    ax = with_alpha(th.muted, p0)
    cv.line([(_MX0 - 14, y1), (_MX1 + 4, y1)], ax, 5)
    _arrowhead(cv, (_MX1 + 22, y1), (_MX1, y1), ax, 22)
    cv.line([(_MX0 - 14, y1), (_MX0 - 14, y0 - 4)], ax, 5)
    _arrowhead(cv, (_MX0 - 14, y0 - 22), (_MX0 - 14, y0), ax, 22)
    xa, ya = props["x_axis"], props["y_axis"]
    tc = with_alpha(th.text, p0)
    cv.text(_MX0, y1 + 24, xa["low"], "semibold", 32, tc, anchor="la")
    cv.text(_MX1, y1 + 24, xa["high"], "semibold", 32, tc, anchor="ra")
    for text, yy, anchor in ((ya["high"], y0 + 6, "t"), (ya["low"], y1 - 6, "b")):
        size, lines = cv.fit_text(text, "semibold", 236, 110, 32, 22)
        lh = size * 1.2
        start = yy if anchor == "t" else yy - lh * len(lines)
        for i, ln in enumerate(lines):
            cv.text(_MX0 - 36, start + i * lh, ln, "semibold", size, tc, anchor="ra")
    q = props.get("quadrants")
    if q:
        for k, qt in enumerate(q):
            if not qt:
                continue
            w = min(420, cv.measure(qt, "semibold", 28)) + 10
            qx = _MX0 + 18 if k % 2 == 0 else _MX1 - 18 - w
            qy = y0 + 14 if k < 2 else y1 - 14 - 36
            cv.text(qx, qy + 18, qt, "semibold", 28, with_alpha(th.muted, 0.8 * p0), anchor="lm")
    for i, it in enumerate(items):
        p = progress(lt, times[i], 0.5)
        if p <= 0:
            continue
        x, y = dots[i]
        s = max(0.01, ease_out_back(p, 2.0))
        r = 17 * s
        cv.ellipse(x, y, r + 6 * s, r + 6 * s, fill=with_alpha(th.bg_top, 0.9))
        cv.ellipse(x, y, r, r, fill=th.accent if i % 2 == 0 else th.accent2)
        lx, ly, w = labels[i]
        a = ease_out_cubic(progress(lt, times[i] + 0.12, 0.4))
        if a > 0:
            cv.rrect(lx - 10, ly - 2, w + 20, 46, 14, fill=with_alpha(th.bg_top, 0.78 * a))
            cv.text(lx, ly + 22, it["label"], "semibold", 32, with_alpha(th.text, a), anchor="lm")


def draw_matrix(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th, ctx) -> None:
    """16:9 keeps its original layout untouched; the other shapes are laid out natively (see the tall section below)."""
    if ctx.frame.landscape:
        _draw_matrix_land(cv, props, lt, dur, th, ctx)
    else:
        _draw_matrix_tall(cv, props, lt, dur, th, ctx)

MATRIX = Element(
    name="matrix", family="Compare",
    doc=("- matrix: {title (<=50), x_axis: {low (<=18), high (<=18)}, y_axis: {low, high}, quadrants: optional 4 labels (<=24; order top-left, top-right, bottom-left, bottom-right), "
         "items: 2-8 [{label (<=24), x (0-1), y (0-1)}]}. A 2x2 map: each item placed by x (left=low) and y (bottom=low), appearing in order. Use to position options on two "
         "qualities (cost vs value, effort vs impact). Place items by what the narration says, never by invented scores; top-right is the 'high, high' corner."),
    sanitize=_san_matrix, draw=draw_matrix, formats=("16:9", "9:16", "1:1", "4:5"), cues=matrix_cues, anchors=lambda p: [i["label"] for i in p["items"]],
    samples=[
        {"title": "What to do first", "x_axis": {"low": "Low effort", "high": "High effort"}, "y_axis": {"low": "Low impact", "high": "High impact"},
         "quadrants": ["Plan it", "Big bets", "Skip it", "Quick wins"],
         "items": [{"label": "Fix onboarding", "x": 0.2, "y": 0.85}, {"label": "Redesign app", "x": 0.85, "y": 0.8}, {"label": "New logo", "x": 0.3, "y": 0.2},
                   {"label": "Add dark mode", "x": 0.55, "y": 0.35}]},
        {"title": "Phones compared", "x_axis": {"low": "Cheap", "high": "Expensive"}, "y_axis": {"low": "Basic", "high": "Powerful"},
         "items": [{"label": "Budget A", "x": 0.12, "y": 0.2}, {"label": "Budget B", "x": 0.15, "y": 0.25}, {"label": "Midrange", "x": 0.5, "y": 0.55},
                   {"label": "Flagship", "x": 0.9, "y": 0.92}, {"label": "Flagship Pro", "x": 0.92, "y": 0.9}, {"label": "Rugged", "x": 0.5, "y": 0.3},
                   {"label": "Foldable", "x": 0.97, "y": 0.6}, {"label": "Gaming", "x": 0.7, "y": 0.8}]},
    ],
)


# ------------------------------------------------------------------ flowchart
_KINDS = ("start", "step", "decision", "end")
_YES = ("yes", "y", "true", "ok", "si", "sí")
_NO = ("no", "n", "false", "fail")


def _layers(ids: List[str], kinds: Dict[str, str], edges: List[list]) -> Tuple[Dict[str, int], set]:
    """Layer of each node (longest path from the start) after setting aside the edges that would close a cycle ('back edges')."""
    out: Dict[str, List[str]] = {i: [] for i in ids}
    indeg = {i: 0 for i in ids}
    for e in edges:
        out[e[0]].append(e[1])
        indeg[e[1]] += 1
    roots = [i for i in ids if kinds[i] == "start"] + [i for i in ids if indeg[i] == 0 and kinds[i] != "start"] + list(ids)
    state: Dict[str, int] = {}
    back = set()

    def dfs(u: str) -> None:
        state[u] = 1
        for v in out[u]:
            if state.get(v) == 1:
                back.add((u, v))
            elif v not in state:
                dfs(v)
        state[u] = 2

    for r in roots:
        if r not in state:
            dfs(r)
    layer = {i: 0 for i in ids}
    fwd = [(e[0], e[1]) for e in edges if (e[0], e[1]) not in back]
    for _ in range(len(ids) + 1):
        moved = False
        for u, v in fwd:
            if layer[v] < layer[u] + 1:
                layer[v] = layer[u] + 1
                moved = True
        if not moved:
            break
    return layer, back


def _san_flowchart_once(p: Dict[str, Any]) -> Dict[str, Any]:
    nodes, seen, by_label = [], set(), {}
    for i, n in enumerate(_list(p.get("nodes"))[:12]):
        if isinstance(n, str):
            n = {"label": n}
        if not isinstance(n, dict):
            continue
        label = _t(n.get("label"), 28) or _t(n.get("id"), 28)
        if not label:
            continue
        nid = _t(n.get("id"), 20) or f"n{i + 1}"
        if nid in seen:
            nid = f"{nid[:17]}_{i + 1}"
        kind = _t(n.get("kind"), 12).lower()
        nodes.append({"id": nid, "label": label, "kind": kind if kind in _KINDS else "step"})
        seen.add(nid)
        by_label.setdefault(label.lower(), nid)
    nodes = nodes[:8]
    ids = [n["id"] for n in nodes]
    by_label = {k: v for k, v in by_label.items() if v in ids}
    if len(nodes) < 3:
        raise ValueError("flowchart needs 3+ nodes")

    def ref(x: Any) -> Optional[str]:
        s = _t(x, 28)
        return s if s in ids else by_label.get(s.lower())

    edges: List[list] = []
    for e in _list(p.get("edges")):
        if isinstance(e, dict):
            e = [e.get("from"), e.get("to"), e.get("label")]
        if not isinstance(e, (list, tuple)) or len(e) < 2:
            continue
        a, b = ref(e[0]), ref(e[1])
        if a is None or b is None or a == b or any(x[0] == a and x[1] == b for x in edges):
            continue
        lab = _t(e[2], 12) if len(e) > 2 else ""
        edges.append([a, b, lab] if lab else [a, b])
    edges = edges[:16]
    if not edges:                                   # no wiring given: the nodes are a straight sequence
        edges = [[ids[i], ids[i + 1]] for i in range(len(ids) - 1)]
    used = {x for e in edges for x in e[:2]}
    nodes = [n for n in nodes if n["id"] in used]
    if len(nodes) < 3:
        raise ValueError("flowchart needs 3+ connected nodes")
    ids = [n["id"] for n in nodes]
    kinds = {n["id"]: n["kind"] for n in nodes}
    layer, _back = _layers(ids, kinds, edges)
    order = sorted(range(len(nodes)), key=lambda k: (layer[ids[k]], k))
    nodes = [nodes[k] for k in order]
    out: Dict[str, Any] = {"nodes": nodes, "edges": edges}
    title = _t(p.get("title"), 50)
    if title:
        out["title"] = title
    return out


def _san_flowchart(p: Dict[str, Any]) -> Dict[str, Any]:
    out = _san_flowchart_once(p)
    for _ in range(4):                              # reordering can change which edge closes a cycle: settle on a fixed point
        nxt = _san_flowchart_once(out)
        if nxt == out:
            break
        out = nxt
    return out


def _lane_rank(label: str) -> int:
    l = label.lower()
    return 0 if l in _YES else 2 if l in _NO else 1


def _spread(items: List[Tuple[str, float, float]], lo: float, hi: float, gap: float) -> Dict[str, float]:
    """Place boxes along one axis as close to their desired centre as possible without overlapping, kept inside [lo, hi]. items: (id, desired, size)."""
    if not items:
        return {}
    pos = [d for _, d, _ in items]
    for k in range(1, len(items)):
        pos[k] = max(pos[k], pos[k - 1] + items[k - 1][2] / 2 + items[k][2] / 2 + gap)
    shift = sum(d - p for (_, d, _), p in zip(items, pos)) / len(items)
    pos = [p + shift for p in pos]
    over = (pos[0] - items[0][2] / 2) - lo
    if over < 0:
        pos = [p - over for p in pos]
    over = hi - (pos[-1] + items[-1][2] / 2)
    if over < 0:
        pos = [p + over for p in pos]
        under = (pos[0] - items[0][2] / 2) - lo
        if under < 0:                                # too wide for the space: squeeze evenly
            span = hi - lo
            tot = sum(s for _, _, s in items)
            g = max(0.0, (span - tot) / max(1, len(items) - 1))
            x, pos = lo, []
            for _, _, s in items:
                pos.append(x + s / 2)
                x += s + g
    return {it[0]: p for it, p in zip(items, pos)}


def _dims(kind: str, s: float, kw: float = 1.0, kh: float = 1.0) -> Tuple[float, float]:
    if kind == "decision":
        return 440 * s * kw, 156 * s * kh
    if kind in ("start", "end"):
        return 270 * s * kw, 90 * s * kh
    return 320 * s * kw, 92 * s * kh


@lru_cache(maxsize=32)
def _flow_layout(key: str, top: float, bottom: float, X0: float = 140.0, X1: float = 1780.0, force: Optional[Tuple[str, int]] = None,
                 smax: float = 1.0, nsteps: int = 12, kw: float = 1.0, kh: float = 1.0, gap_td: float = 40.0) -> Dict[str, Any]:
    nodes, edges = json.loads(key)
    ids = [n["id"] for n in nodes]
    kinds = {n["id"]: n["kind"] for n in nodes}
    layer, back = _layers(ids, kinds, edges)
    L = max(layer.values()) + 1
    layers = [[i for i in ids if layer[i] == k] for k in range(L)]
    W = max(len(l) for l in layers)
    fwd = [e for e in edges if (e[0], e[1]) not in back]
    preds: Dict[str, List[list]] = {i: [] for i in ids}
    for e in fwd:
        preds[e[1]].append(e)
    mode = "ltr" if (W == 1 or L > 5) else "td"
    nb = 1 if (mode == "td" or L <= 5) else 2
    if force:                                       # narrow frames try each arrangement and keep the one that gives the largest nodes
        mode, nb = force[0], (1 if force[0] == "td" else force[1])
    per = L if nb == 1 else (L + 1) // 2
    has_back = bool(back)
    avail_h = bottom - top - (44 if has_back and mode == "ltr" else 0)
    band_h = avail_h if nb == 1 else (avail_h - 44) / 2
    cross_w = (X1 - X0) - (70 if has_back and mode == "td" else 0)
    gap_m = gap_td if mode == "td" else 96.0
    gap_c = 40.0 if mode == "td" else 24.0
    chosen = smax - (nsteps - 1) * 0.05
    for si in range(0, nsteps):
        s = smax - si * 0.05
        dims = {i: _dims(kinds[i], s, kw, kh) for i in ids}
        if mode == "td":
            ok = sum(max(dims[i][1] for i in l) for l in layers) + (L - 1) * gap_m <= avail_h
            ok = ok and all(sum(dims[i][0] for i in l) + (len(l) - 1) * gap_c <= cross_w for l in layers)
        else:
            lw = [max(dims[i][0] for i in l) for l in layers]
            ok = all(sum(lw[b * per:(b + 1) * per]) + (len(lw[b * per:(b + 1) * per]) - 1) * gap_m <= X1 - X0 - (90 if nb == 2 else 0) for b in range(nb))
            ok = ok and all(sum(dims[i][1] for i in l) + (len(l) - 1) * gap_c <= band_h for l in layers)
        if ok:
            chosen = s
            break
    s = chosen
    dims = {i: _dims(kinds[i], s, kw, kh) for i in ids}
    pos: Dict[str, Tuple[float, float, float, float]] = {}
    bandof = {i: (layer[i] // per if nb == 2 else 0) for i in ids}
    # cross-axis centres per node, layer by layer
    cross: Dict[str, float] = {}
    if mode == "td":
        lo, hi = X0, X0 + cross_w
        centre_c = (lo + hi) / 2
    for k, l in enumerate(layers):
        b = k // per if nb == 2 else 0
        if mode == "td":
            lo, hi = X0, X0 + cross_w
            size_i = 0
        else:
            lo, hi = top + b * (band_h + 44), top + b * (band_h + 44) + band_h
        centre = (lo + hi) / 2

        def desired(i: str) -> Tuple[float, int, int]:
            ps = [e for e in preds[i] if bandof[e[0]] == b]
            if not ps:
                return centre, 1, ids.index(i)
            m = sum(cross[e[0]] for e in ps) / len(ps)
            return m, _lane_rank(ps[0][2] if len(ps[0]) > 2 else ""), ids.index(i)

        order = sorted(l, key=lambda i: (round(desired(i)[0] / 4), desired(i)[1], desired(i)[2]))
        if len(l) == 1:
            d = desired(l[0])[0]
            cross[l[0]] = min(max(d, lo + dims[l[0]][0 if mode == "td" else 1] / 2), hi - dims[l[0]][0 if mode == "td" else 1] / 2)
        else:
            ax = 0 if mode == "td" else 1
            got = _spread([(i, desired(i)[0], dims[i][ax]) for i in order], lo, hi, 120.0 if mode == "td" else gap_c)
            cross.update(got)
    # main-axis positions
    main: Dict[str, float] = {}
    lane_mid = None
    if mode == "td":
        hs = [max(dims[i][1] for i in l) for l in layers]
        gm = min(96.0, (avail_h - sum(hs)) / max(1, L - 1))
        y = top + (avail_h - sum(hs) - gm * (L - 1)) / 2
        for k, l in enumerate(layers):
            for i in l:
                main[i] = y + hs[k] / 2
            y += hs[k] + gm
    else:
        ws = [max(dims[i][0] for i in l) for l in layers]
        first_band = ws[:per]
        gm = min(150.0, (X1 - X0 - (90 if nb == 2 else 0) - sum(first_band)) / max(1, len(first_band) - 1)) if len(first_band) > 1 else 0
        total = sum(first_band) + gm * (len(first_band) - 1)
        x0 = X0 + (90 if nb == 2 else 0) + (X1 - X0 - (90 if nb == 2 else 0) - total) / 2
        for b in range(nb):
            x = x0
            for k in range(b * per, min(L, (b + 1) * per)):
                for i in layers[k]:
                    main[i] = x + ws[k] / 2
                x += ws[k] + gm
        if nb == 2:
            lane_mid = top + band_h + 22
    for i in ids:
        w, h = dims[i]
        cx, cy = (cross[i], main[i]) if mode == "td" else (main[i], cross[i])
        pos[i] = (cx, cy, w, h)
    return {"pos": pos, "mode": mode, "nb": nb, "band": bandof, "lane": lane_mid, "back": sorted(back), "scale": s, "layer": layer}


def _edge_route(lay: Dict[str, Any], a: str, b: str, kinds: Dict[str, str], out_deg: Dict[str, int], is_back: bool) -> List[Tuple[float, float]]:
    pos = lay["pos"]
    ax, ay, aw, ah = pos[a]
    bx, by, bw, bh = pos[b]
    td = lay["mode"] == "td"
    if lay["nb"] == 2 and lay["band"][a] != lay["band"][b]:
        lane = lay["lane"]
        bus = min(pos[k][0] - pos[k][2] / 2 for k in pos if lay["layer"][k] == lay["layer"][b]) - 66
        return [(ax, ay + ah / 2), (ax, lane), (bus, lane), (bus, by), (bx - bw / 2, by)]
    if is_back:
        if td:
            right_of_a = any(abs(p[1] - ay) < 4 and p[0] > ax for k, p in pos.items() if k != a)
            if right_of_a:
                xl = min(p[0] - p[2] / 2 for p in pos.values()) - 40
                return [(ax - aw / 2, ay), (xl, ay), (xl, by), (bx - bw / 2, by)]
            xr = max(p[0] + p[2] / 2 for p in pos.values()) + 40
            return [(ax + aw / 2, ay), (xr, ay), (xr, by), (bx + bw / 2, by)]
        yl = max(p[1] + p[3] / 2 for k, p in pos.items() if lay["band"][k] == lay["band"][a]) + 32
        return [(ax, ay + ah / 2), (ax, yl), (bx, yl), (bx, by + bh / 2)]
    branch = kinds[a] == "decision" and out_deg[a] >= 2
    if td:
        if abs(ax - bx) < 6:
            return [(ax, ay + ah / 2), (bx, by - bh / 2)]
        if branch:
            sx = ax + (aw / 2 if bx > ax else -aw / 2)
            return [(sx, ay), (bx, ay), (bx, by - bh / 2)]
        mid = ay + ah / 2 + (by - bh / 2 - ay - ah / 2) / 2
        return [(ax, ay + ah / 2), (ax, mid), (bx, mid), (bx, by - bh / 2)]
    if abs(ay - by) < 6:
        return [(ax + aw / 2, ay), (bx - bw / 2, by)]
    if branch:
        sy = ay + (ah / 2 if by > ay else -ah / 2)
        return [(ax, sy), (ax, by), (bx - bw / 2, by)]
    mid = ax + aw / 2 + (bx - bw / 2 - ax - aw / 2) / 2
    return [(ax + aw / 2, ay), (mid, ay), (mid, by), (bx - bw / 2, by)]


def _diamond(cx, cy, w, h) -> List[Tuple[float, float]]:
    return [(cx, cy - h / 2), (cx + w / 2, cy), (cx, cy + h / 2), (cx - w / 2, cy)]


def flowchart_cues(props: Dict[str, Any], dur: float) -> List[float]:
    return [min(t, dur) for t in reveal_times(len(props["nodes"]), dur, props.get("cues"), first=0.14, last=0.76)]


def draw_flowchart(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th, ctx) -> None:
    nodes, edges = props["nodes"], props["edges"]
    fr = ctx.frame
    if fr.landscape:
        top = _top(cv, th, props, lt) - 2
        lay = _flow_layout(_key(nodes, edges), top, ctx.bottom - 8)
        tsz, chip_sz = 1.0, 26
    else:
        top = _topt(cv, th, props, lt, ctx) - 2
        lay = _flow_tall_layout(_key(nodes, edges), top, ctx.bottom - 8, ctx.box[0], ctx.box[2], fr.vertical)
        tsz, chip_sz = fr.type_scale, int(26 * fr.type_scale * max(lay['scale'], 0.8))
    pos, back = lay["pos"], {tuple(b) for b in lay["back"]}
    kinds = {n["id"]: n["kind"] for n in nodes}
    out_deg: Dict[str, int] = {}
    for e in edges:
        out_deg[e[0]] = out_deg.get(e[0], 0) + 1
    times = reveal_times(len(nodes), dur, props.get("cues"), first=0.14, last=0.76)
    node_t = {n["id"]: times[i] for i, n in enumerate(nodes)}
    col = with_alpha(th.accent2, 0.95)
    for e in edges:
        a, b = e[0], e[1]
        start = max(node_t[a], node_t[b] - 0.15) + 0.2
        p = ease_in_out_cubic(progress(lt, start, 0.55))
        if p <= 0:
            continue
        route = _edge_route(lay, a, b, kinds, out_deg, (a, b) in back)
        _arrow(cv, route, p, col if (a, b) not in back else with_alpha(th.muted, 0.95), 5, dashed=(a, b) in back)
        if len(e) > 2 and p > 0.85:
            segs = list(zip(route[:-1], route[1:]))
            cross = len(route) == 5
            seg = segs[2] if cross else next((sg for sg in segs if math.hypot(sg[1][0] - sg[0][0], sg[1][1] - sg[0][1]) >= 70),
                                             max(segs, key=lambda sg: math.hypot(sg[1][0] - sg[0][0], sg[1][1] - sg[0][1])))
            (x1, y1), (x2, y2) = seg
            horiz = abs(y2 - y1) < abs(x2 - x1)
            mx, my = (x1 + x2) / 2, (y1 + y2) / 2
            if cross:
                _chip(cv, th, e[2], mx, my, chip_sz, ease_out_cubic(progress(lt, start + 0.4, 0.3)), "semibold")
            elif horiz:
                _chip(cv, th, e[2], mx, my - 22, chip_sz, ease_out_cubic(progress(lt, start + 0.4, 0.3)), "semibold")
            else:
                _chip(cv, th, e[2], mx + cv.measure(e[2], "semibold", chip_sz) / 2 + 22, my, chip_sz, ease_out_cubic(progress(lt, start + 0.4, 0.3)), "semibold")
    sc = lay["scale"]
    for n in nodes:
        nid = n["id"]
        cx, cy, w, h = pos[nid]
        p = progress(lt, node_t[nid], 0.5)
        if p <= 0:
            continue
        s = max(0.01, ease_out_back(p, 1.5))
        a = ease_out_cubic(progress(lt, node_t[nid], 0.25))
        kind = n["kind"]
        W, H = w * s, h * s
        cv.shadow(cx - W / 2, cy - H / 2, W, H, 24, alpha=th.shadow_alpha * a * (0.5 if kind == "decision" else 1))
        paper = th.name == "paper"
        if kind == "decision":
            pts = _diamond(cx, cy, W, H)
            cv.polygon(pts, with_alpha(th.bg_top, a))
            cv.polygon(pts, (255, 255, 255, int(255 * a)) if paper else with_alpha(th.accent2, 0.20 * a))
            cv.line(pts + [pts[0]], with_alpha(th.accent2, a), 4)
            iw, ih = w * 0.60 * s, h * 0.58 * s
            size, lines = cv.fit_text(n["label"], "semibold", iw, ih, 30 * tsz * max(sc, 0.8), 18)
            _draw_block(cv, lines, "semibold", size, cx, cy, with_alpha(th.text, a))
            continue
        if kind in ("start", "end"):
            fill = with_alpha(th.accent, a) if kind == "start" else ((255, 255, 255, int(255 * a)) if paper else with_alpha(th.card, a))
            cv.rrect(cx - W / 2, cy - H / 2, W, H, H / 2, fill=fill, outline=with_alpha(th.accent2 if kind == "start" else th.accent, a), width=4 if kind == "end" else 3)
            txt = with_alpha((255, 255, 255), a) if kind == "start" else with_alpha(th.text, a)
        else:
            fill = (255, 255, 255, int(255 * a)) if paper else with_alpha(th.card, a)
            cv.rrect(cx - W / 2, cy - H / 2, W, H, 22, fill=fill, outline=with_alpha(th.accent, a), width=3)
            txt = with_alpha(th.text, a)
        size, lines = cv.fit_text(n["label"], "semibold", (w - 44) * s, (h - 18) * s, 36 * tsz * max(sc, 0.8), 18)
        _draw_block(cv, lines, "semibold", size, cx, cy, txt)


FLOWCHART = Element(
    name="flowchart", family="Process",
    doc=("- flowchart: {title (<=50), nodes: 3-8 [{id, label (<=28), kind: \"start\"|\"step\"|\"decision\"|\"end\"}], edges: [[from_id, to_id, optional label (<=12, e.g. \"yes\")]]}. "
         "Laid out automatically, nodes and arrows drawn on in flow order; decisions are diamonds with labelled branches. Use for procedures, troubleshooting and "
         "decisions the narration walks through. Never more than 8 nodes; give every decision a labelled edge per outcome; never invent steps."),
    sanitize=_san_flowchart, draw=draw_flowchart, formats=("16:9", "9:16", "1:1", "4:5"), cues=flowchart_cues, anchors=lambda p: [n["label"] for n in p["nodes"]],
    samples=[
        {"title": "Is it a good time to plant?", "nodes": [{"id": "s", "label": "Check the weather", "kind": "start"}, {"id": "d", "label": "Is there frost?", "kind": "decision"},
                                                           {"id": "w", "label": "Wait a week"}, {"id": "p", "label": "Plant the seeds"}, {"id": "e", "label": "Water daily", "kind": "end"}],
         "edges": [["s", "d"], ["d", "w", "yes"], ["d", "p", "no"], ["w", "s"], ["p", "e"]]},
        {"title": "How a bill becomes law", "nodes": [{"id": "1", "label": "Idea drafted", "kind": "start"}, {"id": "2", "label": "Committee review"}, {"id": "3", "label": "Floor vote", "kind": "decision"},
                                                      {"id": "4", "label": "Other chamber"}, {"id": "5", "label": "Sent to the president"}, {"id": "6", "label": "Signed into law", "kind": "end"},
                                                      {"id": "7", "label": "Bill dies", "kind": "end"}],
         "edges": [["1", "2"], ["2", "3"], ["3", "4", "passes"], ["3", "7", "fails"], ["4", "5"], ["5", "6"]]},
    ],
)


# ------------------------------------------------------------------ sequence
def _san_sequence(p: Dict[str, Any]) -> Dict[str, Any]:
    actors: List[str] = []
    for a in _list(p.get("actors")):
        s = _t(a, 18)
        if s and s.lower() not in [x.lower() for x in actors]:
            actors.append(s)
    actors = actors[:4]
    if len(actors) < 2:
        raise ValueError("sequence needs 2+ actors")
    low = {a.lower(): a for a in actors}
    msgs = []
    for m in _list(p.get("messages")):
        if not isinstance(m, dict):
            continue
        f, t = low.get(_t(m.get("from"), 18).lower()), low.get(_t(m.get("to"), 18).lower())
        label = _t(m.get("label"), 36)
        if f and t and f != t and label:
            d: Dict[str, Any] = {"from": f, "to": t, "label": label}
            if m.get("reply") is True:
                d["reply"] = True
            msgs.append(d)
    msgs = msgs[:8]
    if len(msgs) < 3:
        raise ValueError("sequence needs 3+ messages")
    out: Dict[str, Any] = {"actors": actors, "messages": msgs}
    title = _t(p.get("title"), 50)
    if title:
        out["title"] = title
    return out


def sequence_cues(props: Dict[str, Any], dur: float) -> List[float]:
    return [min(t, dur) for t in reveal_times(len(props["messages"]), dur, props.get("cues"), first=0.2, last=0.78)]


def _draw_sequence_land(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th, ctx) -> None:
    actors, msgs = props["actors"], props["messages"]
    m, n = len(actors), len(msgs)
    top = _top(cv, th, props, lt, 52) - 4
    bottom = ctx.bottom - 6
    cw = 1640 / m
    cx = [140 + cw * (i + 0.5) for i in range(m)]
    bw = min(320.0, cw - 36)
    bh = 78.0
    p0 = ease_out_cubic(progress(lt, 0.05, 0.5))
    times = reveal_times(n, dur, props.get("cues"), first=0.2, last=0.78)
    y_life0 = top + bh
    y_life1 = bottom
    for i, a in enumerate(actors):
        lp = ease_out_cubic(progress(lt, 0.2, 0.7))
        _dashed(cv, partial_polyline([(cx[i], y_life0 + 4), (cx[i], y_life1)], lp), with_alpha(th.muted, 0.55), 3, 14, 12)
        cv.card(cx[i] - bw / 2, top + (1 - p0) * -30, bw, bh, th, r=22, alpha=p0)
        cv.rrect(cx[i] - bw / 2, top + (1 - p0) * -30, bw, bh, 22, outline=with_alpha(th.accent if i % 2 == 0 else th.accent2, p0), width=3)
        _fit_draw(cv, a, "bold", cx[i], top + bh / 2 + (1 - p0) * -30, bw - 28, bh - 14, 36, with_alpha(th.text, p0), 20)
    area_top = y_life0 + 30
    sp = (y_life1 - area_top) / n
    idx = {a: i for i, a in enumerate(actors)}
    for k, msg in enumerate(msgs):
        y = area_top + sp * (k + 0.62)
        x1, x2 = cx[idx[msg["from"]]], cx[idx[msg["to"]]]
        d = 1 if x2 > x1 else -1
        p = ease_in_out_cubic(progress(lt, times[k], 0.5))
        if p <= 0:
            continue
        reply = bool(msg.get("reply"))
        color = with_alpha(th.muted if reply else th.accent2, 0.95)
        pts = [(x1 + d * 8, y), (x2 - d * 4, y)]
        _arrow(cv, pts, p, color, 5, dashed=reply)
        a = ease_out_cubic(progress(lt, times[k] + 0.15, 0.4))
        if a > 0:
            span = abs(x2 - x1) - 50
            size, lines = cv.fit_text(msg["label"], "semibold", span, min(sp * 0.62, 78), 32, 20)
            lh = size * 1.15
            ymid = y - 12 - (len(lines) * lh) / 2
            tw = max(cv.measure(l, "semibold", size) for l in lines)
            mx = (x1 + x2) / 2
            cv.rrect(mx - tw / 2 - 12, ymid - len(lines) * lh / 2 - 3, tw + 24, len(lines) * lh + 6, 12, fill=with_alpha(th.bg_top, 0.7 * a))
            _draw_block(cv, lines, "semibold", size, mx, ymid, with_alpha(th.text, a), line_h=1.15)
        # step number on the sender's lifeline
        if p > 0.2:
            r = 15 * min(1.0, p * 2)
            cv.ellipse(x1, y, r, r, fill=th.accent if not reply else th.muted)
            if r > 12:
                cv.text(x1, y + 1, str(k + 1), "bold", 18, (255, 255, 255), anchor="mm")


def draw_sequence(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th, ctx) -> None:
    """16:9 keeps its original layout untouched; the other shapes are laid out natively (see the tall section below)."""
    if ctx.frame.landscape:
        _draw_sequence_land(cv, props, lt, dur, th, ctx)
    else:
        _draw_sequence_tall(cv, props, lt, dur, th, ctx)

SEQUENCE = Element(
    name="sequence", family="Process",
    doc=("- sequence: {title (<=50), actors: 2-4 names (<=18), messages: 3-8 [{from (an actor name), to (an actor name), label (<=36), reply: optional true for a dashed return arrow}]}. "
         "A sequence diagram: lifelines and numbered arrows appearing in order. Use to explain how a request, an order or a conversation passes between people or systems. "
         "Use the exact actor names in from/to; never invent steps."),
    sanitize=_san_sequence, draw=draw_sequence, formats=("16:9", "9:16", "1:1", "4:5"), cues=sequence_cues, anchors=lambda p: [m["label"] for m in p["messages"]],
    samples=[
        {"title": "What happens when you open a website", "actors": ["Browser", "DNS", "Server"],
         "messages": [{"from": "Browser", "to": "DNS", "label": "Where is example.com?"}, {"from": "DNS", "to": "Browser", "label": "It is at 93.184.216.34", "reply": True},
                      {"from": "Browser", "to": "Server", "label": "Please send the page"}, {"from": "Server", "to": "Browser", "label": "Here is the HTML", "reply": True}]},
        {"title": "Ordering a coffee", "actors": ["Customer", "Cashier", "Barista", "Kitchen"],
         "messages": [{"from": "Customer", "to": "Cashier", "label": "One flat white, please"}, {"from": "Cashier", "to": "Barista", "label": "Ticket for a flat white"},
                      {"from": "Barista", "to": "Kitchen", "label": "Need a pastry too?"}, {"from": "Kitchen", "to": "Barista", "label": "Croissant ready", "reply": True},
                      {"from": "Barista", "to": "Customer", "label": "Your flat white is ready"}, {"from": "Cashier", "to": "Customer", "label": "That is 4.50, thanks"}]},
    ],
)


# ------------------------------------------------------------------ native layouts for 9:16, 1:1 and 4:5
# 16:9 keeps the original drawers above (pixel-identical). Everything below lays out from `ctx.box` / `ctx.frame` in design units.
def _topt(cv: Canvas, th, props: Dict[str, Any], lt: float, ctx, size: float = 46) -> float:
    """Title for narrow frames (wrapped to two lines, sized by the frame); returns the y where content may start."""
    if props.get("title"):
        return heading(cv, th, props["title"], lt, y=ctx.top + 10, size=size, ctx=ctx) - 8
    return ctx.top + 24


def _fit2(cv: Canvas, text: str, weight: str, w: float, h: float, start: float, min_size: float = 22, line_h: float = 1.18):
    """Largest size whose wrapped block fits w x h, checking the WIDTH of every line too (an unbreakable word can be wider than the box); clips as a last resort."""
    size = float(start)
    while True:
        lines = cv.wrap(text, weight, size, w)
        ok = len(lines) * size * line_h <= h and all(cv.measure(l, weight, size) <= w for l in lines)
        if ok or size <= min_size:
            break
        size -= 2
    if not ok:
        n = max(1, int(h // (size * line_h)))
        lines = [_clip_w(cv, l, weight, size, w) for l in lines[:n]]
    return size, lines


def _draw_fit2(cv: Canvas, text: str, weight: str, x: float, cy: float, w: float, h: float, start: float, color, min_size: float = 22, align: str = "m") -> float:
    size, lines = _fit2(cv, text, weight, w, h, start, min_size)
    lh = size * 1.18
    y0 = cy - (len(lines) - 1) * lh / 2
    for i, ln in enumerate(lines):
        if align == "m":
            cv.text(x, y0 + i * lh, ln, weight, size, color, anchor="mm")
        else:
            cv.text(x, y0 + i * lh, ln, weight, size, color, anchor="lm")
    return size


def _vtext(cv: Canvas, x: float, y: float, s: str, weight: str, size: float, color, anchor: str = "m") -> None:
    """Text rotated to read bottom to top, centred on x. anchor: 'm' centres on y, 'b' starts at y (text runs up from y), 't' ends at y (text runs down from y)."""
    a = int(color[3]) if len(color) == 4 else 255
    if a <= 0 or not s:
        return
    cv.min_font = min(cv.min_font, size)
    font = cv.font(weight, size)
    l, t, r, b = font.getbbox(s)
    pad = 4
    mask = Image.new("L", (int(r - l) + 2 * pad, int(b - t) + 2 * pad), 0)
    ImageDraw.Draw(mask).text((pad - l, pad - t), s, font=font, fill=255)
    mask = mask.rotate(90, expand=True)
    mask = mask.point(lambda v: v * a // 255)
    X = cv._s(x) - mask.width // 2
    ln = mask.height
    Y = cv._s(y) - ln // 2 if anchor == "m" else cv._s(y) - ln if anchor == "b" else cv._s(y)
    cv.im.paste(tuple(color[:3]), (X, Y), mask)


# ---- versus: one card, two halves, matching rows read across. Stacked (9:16, 4:5): the label sits on the seam above its two values.
# Square: the label gets its own middle column so every row stays one band tall.
def _draw_versus_tall(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th, ctx) -> None:
    fr = ctx.frame
    ts = fr.type_scale
    bx0, by0, bx1, by1 = ctx.box
    W = bx1 - bx0
    rows = props["rows"]
    n = len(rows)
    times = _versus_times(props, dur)
    verdict = props.get("verdict", "")
    win = props.get("winner", "")
    top = _topt(cv, th, props, lt, ctx) if props.get("title") else by0 + 12
    gap = 14.0
    stack = fr.vertical
    big = fr.H > 1500
    head_h = 176.0 if stack else 136.0
    vh = (112.0 if stack else 76.0) if verdict else 0.0
    rows_bottom = by1 - (vh + gap if verdict else 0)
    rows_top = top + head_h
    row_h = min(236.0 if big else 190.0 if stack else 120.0, (rows_bottom - rows_top - 12) / n)
    panel_h = head_h + n * row_h + 12
    top += max(0.0, (by1 - top - panel_h - (vh + gap if verdict else 0)) / 2)       # a short block sits in the middle of the free space
    rows_top = top + head_h
    rows_bottom = top + panel_h
    lc = 0.0 if stack else 236.0                                                        # width of the label column (square)
    cwid = (W - lc) / 2                                                                 # width of one side
    xs = {"a": bx0, "b": bx1 - cwid}
    mid = bx0 + W / 2
    cols = {"a": th.accent, "b": th.accent2}
    after = _end_cue(times, dur, 0.8)
    t_verdict = after
    t_win = after + (0.55 if verdict else 0.0)
    p0 = ease_out_cubic(progress(lt, 0.05, 0.55))
    cv.card(bx0, top, W, panel_h, th, alpha=p0)
    for sx in ([mid] if stack else [xs["a"] + cwid, xs["b"]]):
        cv.line([(sx, top + head_h * (0.62 if stack else 0.9)), (sx, top + panel_h - 18)], with_alpha(th.card_outline, p0), 2, round_caps=False)
    for side in ("a", "b"):
        x = xs[side]
        slide = (1 - p0) * (-50 if side == "a" else 50)
        cv.rrect(x + slide + 30, top + 18, cwid - 60, 8, 4, fill=with_alpha(cols[side], p0))
        s = props[side]
        tag = s.get("tagline", "")
        ncy = top + (68 if tag else 88) * (1.0 if stack else 0.8)
        _draw_fit2(cv, s["name"], "bold", x + cwid / 2 + slide, ncy, cwid - 104, (70 if tag else 84) if stack else (56 if tag else 70), 56 * ts, with_alpha(th.text, p0), 30)
        if tag:
            _draw_fit2(cv, tag, "regular", x + cwid / 2 + slide, top + head_h - (44 if stack else 38), cwid - 60, 62 if stack else 52, 30 * ts, with_alpha(th.muted, p0), 24)
    vp = ease_out_back(progress(lt, 0.3, 0.5), 1.8)
    r = 40 * max(0.01, vp)
    vcy = top + head_h * (0.48 if stack else 0.5)
    cv.ellipse(mid, vcy, r, r, fill=with_alpha(th.bg_top, 1.0), outline=with_alpha(th.muted, min(1, vp)), width=3)
    if vp > 0.5:
        cv.text(mid, vcy, "VS", "bold", 32 * min(1.0, vp), with_alpha(th.text, min(1.0, vp)), anchor="mm")
    lb = max(34.0, min(46.0, row_h * 0.3)) if stack else 0.0
    for i, row in enumerate(rows):
        p = ease_out_cubic(progress(lt, times[i], 0.5))
        if p <= 0:
            continue
        y = rows_top + i * row_h
        if i:
            cv.line([(bx0 + 30, y), (bx1 - 30, y)], with_alpha(th.card_outline, p), 2, round_caps=False)
        if stack:
            lsz, llines = _fit2(cv, row["label"], "semibold", W - 120, lb - 4, 28 * ts, 22)
            lw = max(cv.measure(l, "semibold", lsz) for l in llines) + 36
            cv.rrect(mid - lw / 2, y + 4, lw, lb, lb / 2, fill=with_alpha(th.bg_top, 0.92 * p), outline=with_alpha(th.card_outline, p), width=2)
            cv.text(mid, y + 4 + lb / 2, llines[0], "semibold", lsz, with_alpha(th.muted, p), anchor="mm")
            cy = y + 4 + lb + (row_h - lb - 8) / 2 + 4
            ch = row_h - lb - 22
        else:
            _draw_fit2(cv, row["label"], "semibold", mid, y + row_h / 2, lc - 24, row_h - 12, 28 * ts, with_alpha(th.muted, p), 22)
            cy = y + row_h / 2
            ch = row_h - 10
        for side, off in (("a", -1), ("b", 1)):
            weight = "bold" if win == side and lt >= t_win else "semibold"
            cx = xs[side] + cwid / 2 + off * (1 - p) * 30
            _draw_fit2(cv, row[side], weight, cx, cy, cwid - 40, ch, 46 * ts, with_alpha(th.text, p), 24)
    if win:
        wp = ease_out_cubic(progress(lt, t_win, 0.6))
        if wp > 0:
            x = xs[win]
            cv.rrect(x + 2, top - 2, cwid - 4, panel_h + 4, 30, outline=with_alpha(th.accent, wp), width=7)
            bx, by = (x + cwid - 40) if win == "a" else (x + 40), top + 4
            br = 30 * ease_out_back(wp, 1.6)
            if br > 1:
                cv.ellipse(bx, by, br, br, fill=th.accent, outline=with_alpha(th.bg_top, 1), width=4)
                k = br / 34
                cv.line([(bx - 14 * k, by + 1 * k), (bx - 4 * k, by + 11 * k), (bx + 15 * k, by - 10 * k)], (255, 255, 255), 7 * k)
    if verdict:
        vp2 = ease_out_cubic(progress(lt, t_verdict, 0.55))
        if vp2 > 0:
            y = rows_bottom + gap + (1 - vp2) * 30
            cv.rrect(bx0, y, W, vh, 24, fill=with_alpha(th.accent, 0.20 * vp2), outline=with_alpha(th.accent, vp2), width=3)
            _draw_fit2(cv, verdict, "bold", mid, y + vh / 2, W - 60, vh - 14, 42 * ts, with_alpha(th.text, vp2), 26)


# ---- table: a grid when it reads at 30+ px, otherwise one card per row (the first cell is its title, the rest are labelled values)
@lru_cache(maxsize=32)
def _table_geometry_tall(key: str, w: float, fs_max: int, fs_min: int, pad: float):
    cols, rows = json.loads(key)
    n = len(cols)
    fs = fs_max
    while fs >= fs_min:
        nat = [max([_meas(cols[j], "semibold", fs * 0.8)] + [_meas(r[j], "semibold" if j == 0 else "regular", fs) for r in rows]) + pad for j in range(n)]
        if sum(nat) <= w:
            return fs, [x * w / sum(nat) for x in nat]
        fs -= 2
    return None


def _draw_table_tall(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th, ctx) -> None:
    fr = ctx.frame
    ts = fr.type_scale
    bx0, by0, bx1, by1 = ctx.box
    W = bx1 - bx0
    cols, rows = props["columns"], props["rows"]
    n = len(rows)
    nc = len(cols)
    key = _key(cols, rows)
    top = (_topt(cv, th, props, lt, ctx) if props.get("title") else by0 + 16) + 4
    times = reveal_times(n, dur, props.get("cues"), first=0.2, last=0.7)
    t_hl = _end_cue(times, dur, 0.8)
    hl = props.get("highlight")
    hp = ease_out_cubic(progress(lt, t_hl, 0.4)) if hl else 0.0
    pulse = math.sin(math.pi * progress(lt, t_hl, 1.1)) if hl else 0.0
    p0 = ease_out_cubic(progress(lt, 0.1, 0.5))
    geo = _table_geometry_tall(key, W, int(46 * ts), 30, 44.0)
    avail = by1 - top
    gap = 12.0
    card_h = (avail - (n - 1) * gap) / n
    if geo is not None and fr.vertical and geo[0] < 40 and card_h >= 150:       # a small grid: cards read better
        geo = None
    if geo is None and (fr.square or card_h < 140):                    # no room for cards: a denser grid
        geo = _table_geometry_tall(key, W, 30, 24, 36.0) or (24, [W / nc] * nc)
    if geo is not None:
        fs, widths = geo
        head_h = 76.0
        row_h = min(190.0 if fr.H > 1500 else 140.0, (avail - head_h - 28) / n)
        height = head_h + n * row_h + 12
        top += max(0.0, (avail - height) / 2)
        xs = [bx0]
        for w in widths:
            xs.append(xs[-1] + w)
        cv.card(bx0, top, W, height, th, r=26, alpha=p0)
        cv.rrect(bx0 + 8, top + 8, W - 16, head_h - 8, 20, fill=with_alpha(th.accent2, 0.16 * p0))
        hs = max(24.0, min(34.0, fs * 0.8))
        for j, c in enumerate(cols):
            _draw_fit2(cv, c, "semibold", xs[j] + 18, top + head_h / 2 + 2, widths[j] - 26, head_h - 12, hs, with_alpha(th.accent2, p0), 22, align="l")
        for i, row in enumerate(rows):
            p = ease_out_cubic(progress(lt, times[i], 0.5))
            if p <= 0:
                continue
            y = top + head_h + 4 + i * row_h
            if i % 2 == 0:
                cv.rrect(bx0 + 8, y, W - 16, row_h, 14, fill=with_alpha(th.text, 0.045 * p))
            if hl and hl["row"] == i and hp > 0:
                hx0, hx1 = (xs[hl["col"]] + 4, xs[hl["col"] + 1] - 4) if "col" in hl else (bx0 + 8, bx1 - 8)
                grow = 5 * pulse
                cv.rrect(hx0 - grow, y - grow, hx1 - hx0 + 2 * grow, row_h + 2 * grow, 16, fill=with_alpha(th.accent, (0.20 + 0.14 * pulse) * hp),
                         outline=with_alpha(th.accent, hp), width=4)
            for j, cell in enumerate(row):
                if not cell:
                    continue
                on = hl and hl["row"] == i and hp > 0.5 and ("col" not in hl or hl["col"] == j)
                _draw_fit2(cv, cell, "bold" if (j == 0 or on) else "regular", xs[j] + 18 + (1 - p) * 24, y + row_h / 2, widths[j] - 26, row_h - 10, fs,
                           with_alpha(th.text, p), 24, align="l")
        return
    # cards
    ch = min(230.0, card_h)
    k = max(0.9, min(1.25, ch / 170))
    top += max(0.0, (avail - n * ch - (n - 1) * gap) / 2)
    for i, row in enumerate(rows):
        p = ease_out_cubic(progress(lt, times[i], 0.5))
        if p <= 0:
            continue
        y = top + i * (ch + gap) + (1 - p) * 40
        is_hl = bool(hl and hl["row"] == i and hp > 0)
        cv.shadow(bx0, y, W, ch, 24, alpha=th.shadow_alpha * p * 0.8)
        fill = with_alpha(th.card, p)
        if th.name == "paper":
            fill = (255, 255, 255, int(255 * p))
        cv.rrect(bx0, y, W, ch, 24, fill=fill, outline=with_alpha(th.card_outline, p), width=1.5)
        cv.rrect(bx0 + 14, y + 18, 7, ch - 36, 3.5, fill=with_alpha(th.accent2 if i % 2 else th.accent, p))
        if is_hl:
            grow = 5 * pulse
            whole = "col" not in hl
            cv.rrect(bx0 - grow, y - grow, W + 2 * grow, ch + 2 * grow, 26, fill=with_alpha(th.accent, (0.16 + 0.12 * pulse) * hp) if whole else None,
                     outline=with_alpha(th.accent, hp), width=4)
        hd = ch * 0.34
        tx = bx0 + 44 + (1 - p) * 20
        on0 = is_hl and hp > 0.5 and hl.get("col", 0) == 0
        if row[0]:
            _draw_fit2(cv, row[0], "bold", tx, y + 18 + hd / 2, W - 90, hd, 46 * ts * k, with_alpha(th.text, p), 28, align="l")
        others = [(j, row[j]) for j in range(1, nc) if row[j]]
        if others:
            pw = (W - 70) / max(1, nc - 1)
            py = y + 18 + hd + 8
            for j, cell in others:
                px = bx0 + 44 + (j - 1) * pw
                if is_hl and hp > 0.5 and hl.get("col") == j:
                    cv.rrect(px - 14, py - 4, pw - 6, ch - hd - 28, 14, fill=with_alpha(th.accent, 0.22 * hp), outline=with_alpha(th.accent, hp), width=3)
                lab = _clip_w(cv, cols[j], "semibold", 26 * k, pw - 24)
                cv.text(px, py + 16 * k, lab, "semibold", 26 * k, with_alpha(th.accent2, p), anchor="lm")
                _draw_fit2(cv, cell, "bold" if (is_hl and hp > 0.5 and hl.get("col") == j) else "regular", px, py + 16 * k + 22 + (ch - hd - 28 - 32 * k) / 2,
                           pw - 20, ch - hd - 28 - 32 * k - 6, 38 * ts * k, with_alpha(th.text, p), 26, align="l")


# ---- ranking: the same countdown, rows as wide as the box, label and note stacked beside the number, value on the right
def _draw_ranking_tall(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th, ctx) -> None:
    fr = ctx.frame
    ts = fr.type_scale
    bx0, by0, bx1, by1 = ctx.box
    items = props["items"]
    n = len(items)
    top = (_topt(cv, th, props, lt, ctx) if props.get("title") else by0 + 12) - 4
    gap = 12.0 if fr.vertical else 8.0
    first_k = 1.3 if fr.vertical else 1.22
    u = min((200.0 if fr.H > 1500 else 150.0) if fr.vertical else 124.0, (by1 - top - (n - 1) * gap) / (n - 1 + first_k))
    h1 = u * first_k
    top += max(0.0, (by1 - top - ((n - 1) * (u + gap) + h1)) / 2)
    times = _ranking_times(props, dur)
    x0, w = bx0, bx1 - bx0
    ys, y = [], top
    for i in range(n):
        ys.append(y)
        y += (h1 if i == 0 else u) + gap
    for k in range(n):
        i = n - 1 - k
        p = progress(lt, times[k], 0.6)
        if p <= 0:
            continue
        pe = ease_out_cubic(p)
        it = items[i]
        first = i == 0
        h = h1 if first else u
        y = ys[i] + (1 - pe) * 46
        a = pe
        cv.shadow(x0, y, w, h, 24, alpha=th.shadow_alpha * a * (1.2 if first else 0.8))
        fill = with_alpha(th.accent, 0.22 * a) if first else with_alpha(th.card, a)
        if th.name == "paper" and not first:
            fill = (255, 255, 255, int(255 * a))
        cv.rrect(x0, y, w, h, 24, fill=fill, outline=with_alpha(th.accent if first else th.card_outline, a), width=4 if first else 1.5)
        pop = ease_out_back(progress(lt, times[k], 0.55), 2.0)
        d = h * 0.7 * max(0.05, min(1.25, pop))
        bx, by = x0 + 18 + h * 0.37, y + h / 2
        cv.ellipse(bx, by, d / 2, d / 2, fill=th.accent if first else with_alpha(th.accent, 0.9 * a), outline=None)
        ns = d * 0.56
        cv.text(bx, by + ns * 0.04, str(i + 1), "bold", ns, with_alpha((255, 255, 255), a), anchor="mm")
        tx = x0 + 36 + h * 0.74
        val = it.get("value", "")
        vw = 0.0
        if val:
            vs = min(h * 0.44, 52.0 * ts) * (1.1 if first else 1.0)
            while _meas(val, "bold", vs) > w * 0.34 and vs > 24:
                vs -= 2
            vw = _meas(val, "bold", vs)
            cv.text(x0 + w - 28, y + h / 2, val, "bold", vs, with_alpha(th.accent2, a), anchor="rm")
        lw = x0 + w - 28 - tx - (vw + 24 if val else 0)
        wl = "bold" if first else "semibold"
        note = it.get("note", "")
        if note:
            ls, ll = _fit2(cv, it["label"], wl, lw, h * 0.52, min(46.0 * ts, h * 0.4) * (1.1 if first else 1.0), 24)
            ns_, nl = _fit2(cv, note, "regular", lw, h * 0.36, min(30.0 * ts, h * 0.25), 22)
            tot = len(ll) * ls * 1.18 + 4 + len(nl) * ns_ * 1.18
            yy = y + h / 2 - tot / 2
            for ln in ll:
                cv.text(tx, yy + ls * 0.59, ln, wl, ls, with_alpha(th.text, a), anchor="lm")
                yy += ls * 1.18
            yy += 4
            for ln in nl:
                cv.text(tx, yy + ns_ * 0.59, ln, "regular", ns_, with_alpha(th.muted, a), anchor="lm")
                yy += ns_ * 1.18
        else:
            _draw_fit2(cv, it["label"], wl, tx, y + h / 2, lw, h - 14, min(54.0 * ts, h * 0.5) * (1.15 if first else 1.0), with_alpha(th.text, a), 24, align="l")
        if first and p > 0:
            rp = progress(lt, times[k] + 0.1, 0.9)
            if 0 < rp < 1:
                g = 10 * rp                        # the ring stays inside the box edge margin
                cv.rrect(x0 - g, y - g, w + 2 * g, h + 2 * g, 24 + g, outline=with_alpha(th.accent, 0.8 * (1 - rp)), width=5)


# ---- matrix: the plot fills the box (a tall plot in 9:16), y axis label turned to read upward in a gutter
def _draw_matrix_tall(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th, ctx) -> None:
    fr = ctx.frame
    ts = fr.type_scale
    bx0, by0, bx1, by1 = ctx.box
    items = props["items"]
    top = (_topt(cv, th, props, lt, ctx) if props.get("title") else by0 + 12) - 4
    gut = 58.0
    px0, px1 = bx0 + gut, bx1 - 14
    y0, y1 = top + 8, by1 - 66
    lsz = 32 * min(1.0, ts)
    lsz = 34 if fr.vertical else 30
    dots, labels = _matrix_layout(_key(items, props.get("quadrants")), y0, y1, px0, px1, lsz, 56)
    times = reveal_times(len(items), dur, props.get("cues"), first=0.3, last=0.75)
    p0 = ease_out_cubic(progress(lt, 0.1, 0.5))
    cv.card(px0, y0, px1 - px0, y1 - y0, th, r=24, alpha=p0)
    mx, my = (px0 + px1) / 2, (y0 + y1) / 2
    cv.rrect(mx, y0 + 3, px1 - mx - 3, my - y0 - 3, 20, fill=with_alpha(th.accent, 0.07 * p0))
    _dashed(cv, [(mx, y0 + 16), (mx, y1 - 16)], with_alpha(th.muted, 0.45 * p0), 3, 14, 12)
    _dashed(cv, [(px0 + 16, my), (px1 - 16, my)], with_alpha(th.muted, 0.45 * p0), 3, 14, 12)
    ax = with_alpha(th.muted, p0)
    cv.line([(px0, y1 + 14), (px1, y1 + 14)], ax, 5)
    _arrowhead(cv, (px1 + 10, y1 + 14), (px1 - 14, y1 + 14), ax, 20)
    cv.line([(px0 - 14, y1), (px0 - 14, y0)], ax, 5)
    _arrowhead(cv, (px0 - 14, y0 - 10), (px0 - 14, y0 + 14), ax, 20)
    xa, ya = props["x_axis"], props["y_axis"]
    tc = with_alpha(th.text, p0)
    asz = 32 if fr.vertical else 30
    half_w = (px1 - px0) / 2 - 12
    for text, x, anchor in ((xa["low"], px0, "l"), (xa["high"], px1, "r")):
        _, lines = _fit2(cv, text, "semibold", half_w, asz * 1.3, asz, 22)
        sz = _fit2(cv, text, "semibold", half_w, asz * 1.3, asz, 22)[0]
        cv.text(x, y1 + 22 + 20, _clip_w(cv, text, "semibold", sz, half_w), "semibold", sz, tc, anchor=anchor + "m")
    plot_h = y1 - y0
    for text, anchor in ((ya["high"], "t"), (ya["low"], "b")):
        sz = asz
        while _meas(text, "semibold", sz) > plot_h / 2 - 20 and sz > 22:
            sz -= 2
        _vtext(cv, bx0 + gut / 2 - 14, y0 + 2 if anchor == "t" else y1 - 2, text, "semibold", sz, tc, anchor=anchor)
    q = props.get("quadrants")
    if q:
        for k, qt in enumerate(q):
            if not qt:
                continue
            w = min(420, cv.measure(qt, "semibold", 28)) + 10
            qx = px0 + 18 if k % 2 == 0 else px1 - 18 - w
            qy = y0 + 14 if k < 2 else y1 - 14 - 36
            cv.text(qx, qy + 18, qt, "semibold", 28, with_alpha(th.muted, 0.8 * p0), anchor="lm")
    lh = lsz + 14
    for i, it in enumerate(items):
        p = progress(lt, times[i], 0.5)
        if p <= 0:
            continue
        x, y = dots[i]
        s = max(0.01, ease_out_back(p, 2.0))
        r = 17 * s
        cv.ellipse(x, y, r + 6 * s, r + 6 * s, fill=with_alpha(th.bg_top, 0.9))
        cv.ellipse(x, y, r, r, fill=th.accent if i % 2 == 0 else th.accent2)
        lx, ly, w = labels[i]
        a = ease_out_cubic(progress(lt, times[i] + 0.12, 0.4))
        if a > 0:
            cv.rrect(lx - 10, ly - 2, w + 20, lh - 6, 14, fill=with_alpha(th.bg_top, 0.78 * a))
            cv.text(lx, ly + (lh - 10) / 2 - 1, it["label"], "semibold", lsz, with_alpha(th.text, a), anchor="lm")


# ---- flowchart (the drawer is shared with 16:9; only the layout differs): try top-to-bottom and one or two left-to-right bands, keep the largest nodes
def _flow_tall_layout(key: str, top: float, bottom: float, x0: float, x1: float, vertical: bool) -> Dict[str, Any]:
    """Top-to-bottom wherever the nodes stay readable (squat nodes and tight gaps in the square); otherwise the left-to-right bands whose nodes come out clearly larger."""
    kh, gap = (1.2, 40.0) if vertical else (0.85, 26.0)
    td = _flow_layout(key, top, bottom, x0, x1, ("td", 1), 1.2, 22, 1.12, kh, gap)
    if td["scale"] >= 0.62:
        return td
    alt = [_flow_layout(key, top, bottom, x0, x1, f, 1.2, 22, 1.12, kh) for f in (("ltr", 1), ("ltr", 2))]
    best = max(alt, key=lambda l: l["scale"])
    return best if best["scale"] > td["scale"] * 1.3 else td


# ---- sequence: actors across the top, lifelines down; messages may overhang neighbouring lifelines so a label never has to squeeze between two close ones
def _draw_sequence_tall(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th, ctx) -> None:
    fr = ctx.frame
    ts = fr.type_scale
    bx0, by0, bx1, by1 = ctx.box
    actors, msgs = props["actors"], props["messages"]
    m, n = len(actors), len(msgs)
    top = (_topt(cv, th, props, lt, ctx) if props.get("title") else by0 + 12)
    bottom = by1 - 6
    W = bx1 - bx0
    cw = W / m
    cx = [bx0 + cw * (i + 0.5) for i in range(m)]
    bw = cw - 14
    bh = 104.0 if fr.vertical else 76.0
    p0 = ease_out_cubic(progress(lt, 0.05, 0.5))
    times = reveal_times(n, dur, props.get("cues"), first=0.2, last=0.78)
    y_life0 = top + bh
    for i, a in enumerate(actors):
        lp = ease_out_cubic(progress(lt, 0.2, 0.7))
        _dashed(cv, partial_polyline([(cx[i], y_life0 + 4), (cx[i], bottom)], lp), with_alpha(th.muted, 0.55), 3, 14, 12)
        cv.card(cx[i] - bw / 2, top + (1 - p0) * -30, bw, bh, th, r=22, alpha=p0)
        cv.rrect(cx[i] - bw / 2, top + (1 - p0) * -30, bw, bh, 22, outline=with_alpha(th.accent if i % 2 == 0 else th.accent2, p0), width=3)
        _draw_fit2(cv, a, "bold", cx[i], top + bh / 2 + (1 - p0) * -30, bw - 16, bh - 12, 34 * ts, with_alpha(th.text, p0), 22)
    area_top = y_life0 + 22
    sp = (bottom - area_top) / n
    idx = {a: i for i, a in enumerate(actors)}
    for k, msg in enumerate(msgs):
        x1, x2 = cx[idx[msg["from"]]], cx[idx[msg["to"]]]
        d = 1 if x2 > x1 else -1
        p = ease_in_out_cubic(progress(lt, times[k], 0.5))
        if p <= 0:
            continue
        y = area_top + sp * (k + 0.68)
        reply = bool(msg.get("reply"))
        color = with_alpha(th.muted if reply else th.accent2, 0.95)
        _arrow(cv, [(x1 + d * 8, y), (x2 - d * 4, y)], p, color, 5, dashed=reply)
        a = ease_out_cubic(progress(lt, times[k] + 0.15, 0.4))
        if a > 0:
            mx = (x1 + x2) / 2
            span = abs(x2 - x1) - 30
            room = 2 * min(mx - bx0, bx1 - mx) - 8
            lw = max(span, min(room, W * 0.72))
            size, lines = _fit2(cv, msg["label"], "semibold", lw - 24, min(sp * 0.66, 2 * 40 * ts), 32 * ts, 22, 1.15)
            lh = size * 1.15
            ymid = y - 20 - (len(lines) * lh) / 2
            tw = max(cv.measure(l, "semibold", size) for l in lines)
            cv.rrect(mx - tw / 2 - 12, ymid - len(lines) * lh / 2 - 3, tw + 24, len(lines) * lh + 6, 12, fill=with_alpha(th.bg_top, 0.82 * a))
            _draw_block(cv, lines, "semibold", size, mx, ymid, with_alpha(th.text, a), line_h=1.15)
        if p > 0.2:
            r = 17 * min(1.0, p * 2)
            cv.ellipse(x1, y, r, r, fill=th.accent if not reply else th.muted)
            if r > 13:
                cv.text(x1, y + 1, str(k + 1), "bold", 22, (255, 255, 255), anchor="mm")


ELEMENTS = [VERSUS, TABLE, RANKING, MATRIX, FLOWCHART, SEQUENCE]
