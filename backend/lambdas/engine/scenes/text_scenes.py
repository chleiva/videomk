import math
from typing import Any, Dict, List

from ..canvas import Canvas, with_alpha
from ..easing import ease_out_back, ease_out_cubic, ease_out_expo, progress, reveal_times
from ..theme import Theme
from .base import SceneCtx, format_number, heading, parse_number


# ------------------------------------------------------------------ title
def title_cues(props: Dict[str, Any], dur: float) -> List[float]:
    return [0.15]


def draw_title(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    title = str(props.get("title", "")).strip()
    sub = str(props.get("subtitle", "")).strip()
    fr = ctx.frame
    cx = fr.cx
    land = fr.landscape
    cw = 1480 if land else fr.W - 2 * fr.margin_x
    ch = ctx.bottom - ctx.top
    size, lines = cv.fit_text(title, "bold", cw, 480 if land else ch * 0.6, 124 if land else 124 * fr.type_scale, 28 if land else 40)
    line_h = size * 1.14
    block_h = len(lines) * line_h
    y0 = (ctx.bottom + ctx.top) / 2 - block_h / 2 - (36 if sub else 0)
    idx = 0
    for li, line in enumerate(lines):
        x = cx - cv.measure(line, "bold", size) / 2
        for word in line.split():
            p = ease_out_cubic(progress(lt, 0.15 + idx * 0.07, 0.6))
            cv.text(x, y0 + li * line_h + (1 - p) * 46, word, "bold", size, with_alpha(th.text, p))
            x += cv.measure(word + " ", "bold", size)
            idx += 1
    t_after = 0.15 + idx * 0.07 + 0.15
    bw = (280 if land else 320) * ease_out_expo(progress(lt, t_after, 0.7))
    by = y0 + block_h + 22
    cv.rrect(cx - bw / 2, by, bw, 10, 5, fill=th.accent)
    if sub:
        p = ease_out_cubic(progress(lt, t_after + 0.25, 0.6))
        sub_size, sub_lines = cv.fit_text(sub, "regular", 1300 if land else cw, 160 if land else ch * 0.22, 48 if land else 54, 30)
        for i, line in enumerate(sub_lines):
            cv.text(cx, by + 44 + i * sub_size * 1.3 + (1 - p) * 16, line, "regular", sub_size, with_alpha(th.muted, p), anchor="ma")


# ------------------------------------------------------------------ bullets
def bullets_cues(props: Dict[str, Any], dur: float) -> List[float]:
    items = list(props.get("items") or [])[:6]
    return reveal_times(len(items), dur, props.get("cues"))


def draw_bullets(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    """The styled list (scenes/list_scenes.py): `style` and `accent` props, the default look when they are missing or unknown."""
    from .list_scenes import draw

    draw(cv, props, lt, dur, th, ctx)


# ------------------------------------------------------------------ stat
RING_R, RING_STROKE, RING_CLEAR = 300, 26, 30


def ring_radius(ctx: SceneCtx) -> float:
    """The percentage ring's radius for the frame: 300 landscape; bigger in tall frames, smaller in the squat square one."""
    fr = ctx.frame
    if fr.landscape:
        return RING_R
    ch = ctx.bottom - ctx.top
    return max(200.0, min(390.0, (ch - 230) / 2, (fr.W - 2 * fr.margin_x) / 2 - 20))


def ring_text_size(cv: Canvas, text: str, ring_r: float = RING_R) -> float:
    """The largest font size at which `text` sits wholly inside the ring: its bounding-box corners stay within the ring's inner circle, with clear space.
    Sized for the FINAL text, so the number does not change size while it counts up."""
    inner = ring_r - RING_STROKE / 2 - RING_CLEAR
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
    fr = ctx.frame
    cx = fr.cx
    land = fr.landscape
    cw = 1200 if land else (fr.W - 2 * fr.margin_x) * 0.94
    ring_r = ring_radius(ctx)
    cy = (ctx.bottom + ctx.top) / 2 - 40
    lab_size, lab_lines = cv.fit_text(label, "semibold", 1300 if land else cw, 150 if land else 190, 54 if land else 54 * fr.type_scale, 32) if label else (0, [])
    lab_h = len(lab_lines) * lab_size * 1.25
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
    if not land:      # sized from the FINAL text (it must fit the frame's width and stay put while it counts up), the number and its label centred as one group
        final_txt = f"{pre}{format_number(val, dec, comma)}{suf}" if parsed else value
        if is_pct:
            cy = (ctx.top + ctx.bottom) / 2 - (2 * ring_r + RING_STROKE + 34 + lab_h) / 2 + ring_r + RING_STROKE / 2
        else:
            size_f = 250 * fr.type_scale * 1.1
            while size_f > 80 and cv.measure(final_txt, "bold", size_f) > cw:
                size_f -= 4
            cy = (ctx.top + ctx.bottom) / 2 - (size_f * 0.8 + 46 + lab_h) / 2 + size_f * 0.4

    if is_pct:
        r = ring_r
        cv.arc(cx, cy, r, 0, 360, with_alpha(th.card_outline, 1.0) if th.name != "paper" else (31, 41, 55, 40), RING_STROKE)
        sweep = 360 * (val / 100.0) * count_p
        if sweep > 1:
            cv.arc(cx, cy, r, -90, -90 + sweep, th.accent + (255,), RING_STROKE)
        final = f"{pre}{format_number(val, dec, comma)}{suf}"
        size = ring_text_size(cv, final, ring_r)
    else:
        size = cv.fit_text(shown, "bold", cw, 300, 250, 80)[0] if land else size_f
    cv.text(cx, cy + (1 - ease_out_cubic(progress(lt, 0.1, 0.6))) * 30, shown, "bold", size, with_alpha(th.text, ease_out_cubic(progress(lt, 0.05, 0.4)) * dim), anchor="mm")
    if label:
        p = ease_out_cubic(progress(lt, 0.7, 0.6)) * (dim / 0.4 * 0.55 if waiting else 1.0)
        lines = lab_lines
        base = cy + ((330 if land else ring_r + RING_STROKE / 2 + 34) if is_pct else (190 if land else size * 0.4 + 46))
        for i, line in enumerate(lines):
            cv.text(cx, base + i * lab_size * 1.25 + (1 - p) * 18, line, "semibold", lab_size, with_alpha(th.muted, min(1.0, p)), anchor="ma")


# ------------------------------------------------------------------ quote
def quote_cues(props: Dict[str, Any], dur: float) -> List[float]:
    return [0.2]


def draw_quote(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    text = str(props.get("text", "")).strip()
    who = str(props.get("attribution", "")).strip()
    fr = ctx.frame
    land = fr.landscape
    tx = 240 if land else fr.margin_x + 4          # text left edge; landscape hangs the opening mark to its left, other shapes stack it above
    cw = 1380 if land else fr.W - 2 * fr.margin_x - 8
    ch = ctx.bottom - ctx.top
    size, lines = cv.fit_text(text, "semibold", cw, 470 if land else ch - 330, 70 if land else 70 * fr.type_scale, 34, line_h=1.28)
    line_h = size * 1.28
    block_h = len(lines) * line_h + (80 if who else 0)
    y0 = (ctx.bottom + ctx.top) / 2 - block_h / 2 + (50 if land else 100)
    qa = ease_out_cubic(progress(lt, 0.0, 0.6))
    if land:
        cv.text(150, y0 - 20 + (1 - qa) * 30, "“", "bold", 260, with_alpha(th.accent, 0.9 * qa), anchor="ls")
    else:
        cv.text(tx - 6, y0 + 20 + (1 - qa) * 30, "“", "bold", 300, with_alpha(th.accent, 0.9 * qa), anchor="ls")
    words_total = sum(len(l.split()) for l in lines)
    span = max(0.8, dur * 0.65)
    n = 0
    for li, line in enumerate(lines):
        x = tx
        for w in line.split():
            a = ease_out_cubic(progress(lt, 0.25 + span * n / max(1, words_total), 0.4))
            cv.text(x, y0 + li * line_h, w, "semibold", size, with_alpha(th.text, a))
            x += cv.measure(w + " ", "semibold", size)
            n += 1
    if who:
        a = ease_out_cubic(progress(lt, 0.25 + span + 0.1, 0.5))
        cv.rrect(tx, y0 + len(lines) * line_h + 30, 60, 6, 3, fill=with_alpha(th.accent, a))
        cv.text(tx + 80, y0 + len(lines) * line_h + 10, who if land else cv.wrap(who, "regular", 40 * fr.type_scale, cw - 80)[0], "regular", 40 if land else 40 * fr.type_scale, with_alpha(th.muted, a))
