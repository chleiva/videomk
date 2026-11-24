import math
from typing import Any, Dict, List

from ..canvas import Canvas, with_alpha
from ..easing import ease_out_back, ease_out_cubic, ease_out_expo, progress, reveal_times
from ..theme import Theme
from .base import CENTER_X, CONTENT_TOP, SceneCtx, format_number, heading, parse_number


# ------------------------------------------------------------------ title
def title_cues(props: Dict[str, Any], dur: float) -> List[float]:
    return [0.15]


def draw_title(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    title = str(props.get("title", "")).strip()
    sub = str(props.get("subtitle", "")).strip()
    size, lines = cv.fit_text(title, "bold", 1480, 480, 124)
    line_h = size * 1.14
    block_h = len(lines) * line_h
    y0 = (ctx.bottom + CONTENT_TOP) / 2 - block_h / 2 - (36 if sub else 0)
    idx = 0
    for li, line in enumerate(lines):
        x = CENTER_X - cv.measure(line, "bold", size) / 2
        for word in line.split():
            p = ease_out_cubic(progress(lt, 0.15 + idx * 0.07, 0.6))
            cv.text(x, y0 + li * line_h + (1 - p) * 46, word, "bold", size, with_alpha(th.text, p))
            x += cv.measure(word + " ", "bold", size)
            idx += 1
    t_after = 0.15 + idx * 0.07 + 0.15
    bw = 280 * ease_out_expo(progress(lt, t_after, 0.7))
    by = y0 + block_h + 22
    cv.rrect(CENTER_X - bw / 2, by, bw, 10, 5, fill=th.accent)
    if sub:
        p = ease_out_cubic(progress(lt, t_after + 0.25, 0.6))
        sub_size, sub_lines = cv.fit_text(sub, "regular", 1300, 160, 48, 30)
        for i, line in enumerate(sub_lines):
            cv.text(CENTER_X, by + 44 + i * sub_size * 1.3 + (1 - p) * 16, line, "regular", sub_size, with_alpha(th.muted, p), anchor="ma")


# ------------------------------------------------------------------ bullets
def bullets_cues(props: Dict[str, Any], dur: float) -> List[float]:
    items = list(props.get("items") or [])[:6]
    return reveal_times(len(items), dur, props.get("cues"))


def draw_bullets(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    items = [str(i) for i in (props.get("items") or [])][:6]
    y = heading(cv, th, str(props.get("heading", "")), lt, y=CONTENT_TOP + 20)
    if not items:
        return
    gap = 20
    avail = ctx.bottom - y - 10
    card_h = max(78.0, min(138.0, (avail - gap * (len(items) - 1)) / len(items)))
    font_px = 44 if card_h > 110 else 38 if card_h > 92 else 33
    x0, w = 140, 1640
    times = reveal_times(len(items), dur, props.get("cues"))
    for i, text in enumerate(items):
        p = progress(lt, times[i], 0.55)
        if p <= 0:
            continue
        e = ease_out_back(p, 1.1)
        a = ease_out_cubic(progress(lt, times[i], 0.3))
        cy = y + i * (card_h + gap)
        dx = (1 - e) * -90
        cv.card(x0 + dx, cy, w, card_h, th, r=24, alpha=a)
        cv.rrect(x0 + dx + 20, cy + 18, 8, card_h - 36, 4, fill=with_alpha(th.accent, a))
        rad = min(34, card_h * 0.3)
        bx, by = x0 + dx + 84 + rad, cy + card_h / 2
        cv.ellipse(bx, by, rad, rad, fill=with_alpha(th.accent, a))
        cv.text(bx, by, str(i + 1), "bold", rad * 1.1, with_alpha((255, 255, 255), a), anchor="mm")
        lines = cv.wrap(text, "semibold", font_px, w - 220 - rad * 2)[:2]
        lh = font_px * 1.22
        ty = by - (len(lines) * lh) / 2 - lh * 0.06
        for li, line in enumerate(lines):
            cv.text(x0 + dx + 84 + rad * 2 + 30, ty + li * lh, line, "semibold", font_px, with_alpha(th.text, a))


# ------------------------------------------------------------------ stat
RING_R, RING_STROKE, RING_CLEAR = 300, 26, 30


def ring_text_size(cv: Canvas, text: str) -> float:
    """The largest font size at which `text` sits wholly inside the ring: its bounding-box corners stay within the ring's inner circle, with clear space.
    Sized for the FINAL text, so the number does not change size while it counts up."""
    inner = RING_R - RING_STROKE / 2 - RING_CLEAR
    size = 200.0
    while size > 40:
        if math.hypot(cv.measure(text, "bold", size) / 2, size * 0.78 / 2) <= inner:
            return size
        size -= 4
    return 40.0


def stat_cues(props: Dict[str, Any], dur: float) -> List[float]:
    return [0.2, 0.2 + 1.3]


def draw_stat(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    cue = (props.get("cues") or [0.2])[0]   # the moment the narration names the number (engine/sync.py): the count-up starts then
    wait = max(0.0, float(cue) - 0.2)
    waiting = lt < wait    # before the number is spoken the card is not empty: the label and a dim zero wait for it (it once sat blank for 9 seconds)
    dim = 0.4 * ease_out_cubic(progress(lt, 0.1, 0.5)) if waiting else 1.0
    lt = 0.9 if waiting else lt - wait
    value = str(props.get("value", "")).strip()
    label = str(props.get("label", "")).strip()
    cy = (ctx.bottom + CONTENT_TOP) / 2 - 40
    parsed = parse_number(value)
    count_p = 0.0 if waiting else ease_out_expo(progress(lt, 0.2, 1.3))
    if parsed:
        pre, val, dec, suf, comma = parsed
        shown = f"{pre}{format_number(val * count_p, dec, comma)}{suf}"
        is_pct = suf.strip().startswith("%") and 0 <= val <= 100
    else:
        shown, is_pct, val = value, False, 0.0
        count_p = 0.0 if waiting else ease_out_cubic(progress(lt, 0.2, 0.7))
        if waiting:
            shown = ""   # a word-like value waits as the label alone

    if is_pct:
        r = RING_R
        cv.arc(CENTER_X, cy, r, 0, 360, with_alpha(th.card_outline, 1.0) if th.name != "paper" else (31, 41, 55, 40), RING_STROKE)
        sweep = 360 * (val / 100.0) * count_p
        if sweep > 1:
            cv.arc(CENTER_X, cy, r, -90, -90 + sweep, th.accent + (255,), RING_STROKE)
        final = f"{pre}{format_number(val, dec, comma)}{suf}"
        size = ring_text_size(cv, final)
    else:
        size, _ = cv.fit_text(shown, "bold", 1200, 300, 250, 80)
    cv.text(CENTER_X, cy + (1 - ease_out_cubic(progress(lt, 0.1, 0.6))) * 30, shown, "bold", size, with_alpha(th.text, ease_out_cubic(progress(lt, 0.05, 0.4)) * dim), anchor="mm")
    if label:
        p = ease_out_cubic(progress(lt, 0.7, 0.6)) * (dim / 0.4 * 0.55 if waiting else 1.0)
        lab_size, lines = cv.fit_text(label, "semibold", 1300, 150, 54, 32)
        base = cy + (330 if is_pct else 190)
        for i, line in enumerate(lines):
            cv.text(CENTER_X, base + i * lab_size * 1.25 + (1 - p) * 18, line, "semibold", lab_size, with_alpha(th.muted, min(1.0, p)), anchor="ma")


# ------------------------------------------------------------------ quote
def quote_cues(props: Dict[str, Any], dur: float) -> List[float]:
    return [0.2]


def draw_quote(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    text = str(props.get("text", "")).strip()
    who = str(props.get("attribution", "")).strip()
    size, lines = cv.fit_text(text, "semibold", 1380, 470, 70, 34, line_h=1.28)
    line_h = size * 1.28
    block_h = len(lines) * line_h + (80 if who else 0)
    y0 = (ctx.bottom + CONTENT_TOP) / 2 - block_h / 2 + 50
    qa = ease_out_cubic(progress(lt, 0.0, 0.6))
    cv.text(150, y0 - 20 + (1 - qa) * 30, "“", "bold", 260, with_alpha(th.accent, 0.9 * qa), anchor="ls")
    words_total = sum(len(l.split()) for l in lines)
    span = max(0.8, dur * 0.65)
    n = 0
    for li, line in enumerate(lines):
        x = 240
        for w in line.split():
            a = ease_out_cubic(progress(lt, 0.25 + span * n / max(1, words_total), 0.4))
            cv.text(x, y0 + li * line_h, w, "semibold", size, with_alpha(th.text, a))
            x += cv.measure(w + " ", "semibold", size)
            n += 1
    if who:
        a = ease_out_cubic(progress(lt, 0.25 + span + 0.1, 0.5))
        cv.rrect(240, y0 + len(lines) * line_h + 30, 60, 6, 3, fill=with_alpha(th.accent, a))
        cv.text(320, y0 + len(lines) * line_h + 10, who, "regular", 40, with_alpha(th.muted, a))
