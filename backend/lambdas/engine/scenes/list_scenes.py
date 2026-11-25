"""The `bullets` scene, styled. Five looks (`style`): rail (default), spotlight, icons, cards, keywords; the colour comes from `accent`.

Every look follows the voice: the item being narrated (its reveal time, `props["cues"]`) is lit (scale, colour, glow) while earlier items settle back, and the last
state shows every item. The block is centred in the free band under the heading and sized to fill it (type up to 64-76 px, never below ~36 px).
"""
import math
import re
from typing import Any, Dict, List, Tuple

from ..canvas import Canvas, with_alpha
from ..easing import ease_in_out_cubic, ease_out_cubic, progress, reveal_times
from ..theme import Theme
from .base import SceneCtx
from .style_kit import (
    LEFT, RIGHT, Pal, area, lr, backdrop, clamp_first, emphasis_of, fit_lines, draw_lines, focus, glow_blob, icon, icon_for, lerp, list_style, pal_for, paste_sprite, pop, soft_shadow,
    sprite, title_block,
)

MAX_ITEMS = 6
_SPLIT = re.compile(r"\s*(?::|\s[–—-]\s)\s*")
_WEAK = {"the", "a", "an", "to", "of", "in", "on", "for", "and", "or", "my", "your", "our", "is", "are", "be", "it", "we", "you", "i", "no", "not"}


def keyword_split(text: str) -> Tuple[str, str]:
    """'Speed: how fast it goes' -> ('Speed', 'how fast it goes'); 'Wealth is not everything' -> ('Wealth', 'is not everything'); one short phrase stays whole."""
    t = " ".join(text.split())
    parts = _SPLIT.split(t, maxsplit=1)
    if len(parts) == 2 and parts[0] and parts[1] and len(parts[0]) <= 28:
        return parts[0], parts[1]
    words = t.split()
    if len(words) < 4:      # a short phrase stays whole: splitting 'Safe by design' would only produce a dull keyword
        return t, ""
    k = 1
    while k < len(words) - 1 and (words[k - 1].lower().strip(",.") in _WEAK or len(words[k - 1]) <= 2) and k < 3:
        k += 1
    return " ".join(words[:k]), " ".join(words[k:])


def _rows(n: int, top: float, bot: float, max_pitch: float) -> Tuple[float, float]:
    pitch = min(max_pitch, (bot - top) / n)
    return pitch, top + ((bot - top) - pitch * n) / 2


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ----------------------------------------------------------------------------- rail
def _rail(cv, items, props, lt, times, th, pal, top, bot, emph, ctx):
    fr = ctx.frame
    land = fr.landscape
    LEFT, RIGHT = lr(fr)
    n = len(items)
    pitch, y0 = _rows(n, top, bot, 230 if land else 300)
    r = _clamp(pitch * 0.32, 32, 58 if land else 66)
    cx = LEFT + r + 6
    tx = cx + r + 46
    max_w = RIGHT - tx - 20
    start = _clamp(pitch * 0.55, 44, 74 if land else 74 * fr.type_scale)
    fits = [fit_lines(cv, t, "semibold", max_w, 2 if land else 3, start, 34, pitch * 0.9) for t in items]
    size = min(f[0] for f in fits)
    cys = [y0 + pitch * (i + 0.5) for i in range(n)]
    for i in range(n - 1):                                        # the rail: a faint track, and the lit line that draws down to each new item
        a, b = cys[i] + r + 10, cys[i + 1] - r - 10
        if progress(lt, times[0], 0.3) > 0:
            cv.line([(cx, a), (cx, b)], pal.track, 4)
        p = ease_in_out_cubic(progress(lt, times[i + 1] - 0.4, 0.4))
        if p > 0:
            cv.line([(cx, a), (cx, a + (b - a) * p)], with_alpha(pal.accent_text, 0.9), 4)
    big_cy = (top + bot) / 2
    for i, text in enumerate(items):
        a, e = pop(lt, times[i])
        if a <= 0:
            continue
        f = focus(times, lt, i)
        fe = max(f, 1.0 if emph == i else 0.0)
        dy = (1 - e) * 38
        cy = cys[i] + dy
        if f > 0.02:                                              # ghost numeral on the right: fills the frame, follows the voice
            cv.text(RIGHT - 10, big_cy + 20, str(i + 1), "bold", 400 if land else 340, with_alpha(pal.accent_text, 0.11 * f * a), anchor="rm")
        d = int(r * 2)
        soft_shadow(cv, cx - r, cy - r, d, d, r, 0.55 * fe * a, pal.c1, blur=20, dy=6)
        paste_sprite(cv, sprite(cv, d, d, r, (*pal.c1, 56), (*pal.c2, 56), (*pal.c1, 190), (*pal.c2, 190), 2), cx, cy, 1.0, a)
        paste_sprite(cv, sprite(cv, d, d, r, pal.c1, pal.c2), cx, cy, 1.0 + 0.1 * fe, a * fe)
        num = str(i + 1)
        cv.text(cx, cy + 1, num, "bold", r * 1.05, with_alpha(pal.accent_text, a * (1 - fe)), anchor="mm")
        cv.text(cx, cy + 1, num, "bold", r * 1.05 * (1 + 0.06 * fe), with_alpha(pal.ink, a * fe), anchor="mm")
        col = with_alpha(th.text, a * (0.66 + 0.34 * fe))
        draw_lines(cv, tx + (1 - e) * -26 + 6 * fe, cy, fits[i][1] if fits[i][0] == size else cv.wrap(text, "semibold", size, max_w)[:2 if land else 3], "semibold", size * (1 + 0.025 * fe), col)


# ----------------------------------------------------------------------------- spotlight
def _spotlight(cv, items, props, lt, times, th, pal, top, bot, emph, ctx):
    fr = ctx.frame
    land = fr.landscape
    LEFT, RIGHT = lr(fr)
    n = len(items)
    pitch, y0 = _rows(n, top, bot, 250 if land else 320)
    fs = _clamp(pitch * 0.62, 48, 92 if land else 100)
    idx_w = cv.measure("00", "bold", fs * 0.95)
    tx = LEFT + idx_w + 56
    max_w = RIGHT - tx
    fits = [fit_lines(cv, t, "bold", max_w, 2 if land else 3, fs, 34, pitch * 0.9, 1.14) for t in items]
    size = min(f[0] for f in fits)
    cys = [y0 + pitch * (i + 0.5) for i in range(n)]
    for i in range(n - 1):                                         # hairlines between rows, drawn on left to right
        p = ease_out_cubic(progress(lt, times[i + 1] - 0.3, 0.6))
        if p > 0:
            yy = y0 + pitch * (i + 1)
            cv.line([(LEFT, yy), (LEFT + (RIGHT - LEFT) * p, yy)], pal.track, 2, round_caps=False)
    for i, text in enumerate(items):                               # the moving light first, so the text sits on it
        f = focus(times, lt, i)
        if f > 0.02:
            glow_blob(cv, LEFT + 640 if land else fr.cx, cys[i], 1500 if land else 1200, pal.c1, 0.26 * f if pal.dark else 0.16 * f)
    for i, text in enumerate(items):
        a, e = pop(lt, times[i], 0.65, 1.5)
        if a <= 0:
            continue
        f = focus(times, lt, i)
        fe = max(f, 1.0 if emph == i else 0.0)
        cy = cys[i] + (1 - e) * 44
        bar_h = pitch * 0.58 * min(1.0, fe * 1.0)
        if bar_h > 4:
            paste_sprite(cv, sprite(cv, 9, pitch * 0.58, 4.5, pal.c1, pal.c2), LEFT - 34, cy, 1.0, a)
        cv.text(LEFT, cy + 2, f"{i + 1:02d}", "bold", fs * 0.95, with_alpha(pal.accent_text, a * (0.34 + 0.66 * fe)), anchor="lm")
        col = with_alpha(th.text, a * (0.52 + 0.48 * fe))
        lines = fits[i][1] if fits[i][0] == size else cv.wrap(text, "bold", size, max_w)[:2 if land else 3]
        draw_lines(cv, tx + (1 - e) * -40 + 10 * fe, cy, lines, "bold", size, col, lh=1.14)


# ----------------------------------------------------------------------------- icons
def _icons(cv, items, props, lt, times, th, pal, top, bot, emph, ctx):
    fr = ctx.frame
    land = fr.landscape
    LEFT, RIGHT = lr(fr)
    n = len(items)
    pitch, y0 = _rows(n, top, bot, 200 if land else 270)
    gap = _clamp(pitch * 0.14, 12, 24)
    ch = _clamp(pitch - gap, 90, 190 if land else 250)
    tile = ch - 30
    cw = RIGHT - LEFT
    tx = LEFT + 15 + tile + 34
    max_w = RIGHT - tx - 30
    start = _clamp(ch * 0.5, 40, 68 if land else 68 * fr.type_scale)
    fits = [fit_lines(cv, t, "semibold", max_w, 2 if land else 3, start, 30, ch - 24) for t in items]
    size = min(f[0] for f in fits)
    base = sprite(cv, cw, ch, 26, pal.surface, border=pal.border, bw=2)
    lit = sprite(cv, cw, ch, 26, (*pal.c1, 40), (*pal.c2, 40), pal.c1, pal.c2, 3)
    full = sprite(cv, cw, ch, 26, pal.c1, pal.c2)
    t_soft = sprite(cv, tile, tile, 22, (*pal.c1, 64), (*pal.c2, 64))
    t_full = sprite(cv, tile, tile, 22, pal.c1, pal.c2)
    for i, text in enumerate(items):
        a, e = pop(lt, times[i])
        if a < 1:
            paste_sprite(cv, base, LEFT + cw / 2, y0 + pitch * (i + 0.5), 1.0, 0.3 * (1 - a))   # an empty slot: the structure is there before the voice reaches it
        if a <= 0:
            continue
        f = focus(times, lt, i)
        strong = emph == i
        fe = max(f, 1.0 if strong else 0.0)
        cy = y0 + pitch * (i + 0.5) + (1 - e) * 30
        dx = (1 - e) * -70 + 12 * fe
        cx = LEFT + cw / 2 + dx
        soft_shadow(cv, cx - cw / 2, cy - ch / 2, cw, ch, 26, th.shadow_alpha * a * 0.8)
        soft_shadow(cv, cx - cw / 2, cy - ch / 2, cw, ch, 26, 0.38 * fe * a, pal.c1, blur=30, dy=4)
        paste_sprite(cv, base, cx, cy, 1.0, a)
        paste_sprite(cv, lit, cx, cy, 1.0, a * f)
        if strong:
            paste_sprite(cv, full, cx, cy, 1.0, a)
        tcx = LEFT + dx + 15 + tile / 2
        paste_sprite(cv, t_soft, tcx, cy, 1.0, a)
        paste_sprite(cv, t_full, tcx, cy, 1.0 + 0.05 * fe, a * fe)
        name = icon_for(props, i, text)
        isz = tile * 0.5
        icon(cv, tcx, cy, name, isz, with_alpha(pal.accent_text, a * (1 - fe)))
        icon(cv, tcx, cy, name, isz, with_alpha(pal.ink, a * fe), 1.0 + 0.05 * fe)
        on_full = strong
        col = with_alpha(pal.ink if on_full else th.text, a * (0.74 + 0.26 * fe))
        lines = fits[i][1] if fits[i][0] == size else cv.wrap(text, "semibold", size, max_w)[:2 if land else 3]
        draw_lines(cv, tx + dx, cy, lines, "semibold", size, col)


# ----------------------------------------------------------------------------- cards
def _cards(cv, items, props, lt, times, th, pal, top, bot, emph, ctx):
    fr = ctx.frame
    land = fr.landscape
    LEFT, RIGHT = lr(fr)
    n = len(items)
    cols = (n if n <= 3 else 2 if n == 4 else 3) if land else (1 if fr.aspect == "9:16" or n <= (2 if fr.square else 3) else 2)
    nrows = math.ceil(n / cols)
    gap = 34
    stagger = 26 if cols >= 2 else 0
    avail = bot - top - stagger
    cw = (RIGHT - LEFT - gap * (cols - 1)) / cols
    ch = min((avail - gap * (nrows - 1)) / nrows, 460 if nrows == 1 else (320 if land else 340))
    ch = max(ch, 150)
    horiz = (not land) and (ch < 250 or (cols == 1 and cw / ch > 3.2))        # tight rows (square frame, many items): icon tile on the left, words to its right
    total = ch * nrows + gap * (nrows - 1) + stagger
    y_start = top + (bot - top - total) / 2
    tile = _clamp(ch * 0.27, 64, 96) if not horiz else _clamp(ch * 0.46, 64, 110)
    pad = 34
    text_top = pad + tile + 22
    max_w = cw - 2 * pad
    max_h = ch - text_top - pad
    start = _clamp(cw * 0.13, 40, 64 if land else 74)
    if horiz:
        pad = 26
        tile = min(tile, max(56.0, cw * 0.2))
        max_w, max_h, start = cw - 2 * pad - tile - 24 - (60 if cw > 700 else 0), ch - 36, _clamp(ch * 0.3, 36, 64)
    size = min(cv.fit_text(t, "semibold", max_w, max_h, start, 30)[0] for t in items)
    base = sprite(cv, cw, ch, 32, pal.surface, border=pal.border, bw=2)
    lit = sprite(cv, cw, ch, 32, (*pal.c1, 40), (*pal.c2, 40), pal.c1, pal.c2, 3)
    full = sprite(cv, cw, ch, 32, pal.c1, pal.c2)
    t_soft = sprite(cv, tile, tile, 24, (*pal.c1, 64), (*pal.c2, 64))
    t_full = sprite(cv, tile, tile, 24, pal.c1, pal.c2)
    for i, text in enumerate(items):
        r_, c_ = divmod(i, cols)
        in_row = min(cols, n - r_ * cols)
        x = LEFT + (cols - in_row) * (cw + gap) / 2 + c_ * (cw + gap)
        y = y_start + r_ * (ch + gap) + (stagger if c_ % 2 == 1 else 0)
        a, e = pop(lt, times[i], 0.7, 1.6)
        if a < 1:
            paste_sprite(cv, base, x + cw / 2, y + ch / 2, 1.0, 0.3 * (1 - a))
        if a <= 0:
            continue
        f = focus(times, lt, i)
        strong = emph == i
        fe = max(f, 1.0 if strong else 0.0)
        cx, cy = x + cw / 2, y + ch / 2 + (1 - e) * 60 - 10 * fe
        sc = 0.94 + 0.06 * min(1.0, e) + 0.012 * fe
        soft_shadow(cv, cx - cw / 2, cy - ch / 2, cw, ch, 32, th.shadow_alpha * a * 0.9, blur=30, dy=18)
        soft_shadow(cv, cx - cw / 2, cy - ch / 2, cw, ch, 32, 0.40 * fe * a, pal.c1, blur=34, dy=6)
        paste_sprite(cv, base, cx, cy, sc, a)
        paste_sprite(cv, lit, cx, cy, sc, a * f)
        if strong:
            paste_sprite(cv, full, cx, cy, sc, a)
        left, tcy = cx - cw / 2 * sc + pad, cy - ch / 2 * sc + pad + tile / 2
        if horiz:
            tcy = cy
        paste_sprite(cv, t_soft, left + tile / 2, tcy, sc, a)
        paste_sprite(cv, t_full, left + tile / 2, tcy, sc, a * fe)
        name = icon_for(props, i, text)
        icon(cv, left + tile / 2, tcy, name, tile * 0.5, with_alpha(pal.accent_text, a * (1 - fe)), sc)
        icon(cv, left + tile / 2, tcy, name, tile * 0.5, with_alpha(pal.ink, a * fe), sc)
        ncol = pal.ink if strong else th.text
        if not horiz or cw > 700:
            cv.text(cx + cw / 2 * sc - pad, tcy, f"{i + 1:02d}", "bold", 34, with_alpha(ncol, a * 0.42), anchor="rm")
        lines = cv.wrap(text, "semibold", size, max_w)
        col = with_alpha(pal.ink if strong else th.text, a * (0.8 + 0.2 * fe))
        if horiz:
            draw_lines(cv, left + tile + 24, cy, lines[:3], "semibold", size, col, anchor="lm", lh=1.2)
            continue
        ty = cy - ch / 2 * sc + text_top
        for k, line in enumerate(lines[:4]):
            cv.text(left, ty + k * size * 1.2, line, "semibold", size, col, anchor="la")


# ----------------------------------------------------------------------------- keywords
def _keywords(cv, items, props, lt, times, th, pal, top, bot, emph, ctx):
    fr = ctx.frame
    land = fr.landscape
    LEFT, RIGHT = lr(fr)
    n = len(items)
    split = [keyword_split(t) for t in items]
    has_desc = any(d for _, d in split)
    pitch, y0 = _rows(n, top, bot, 200 if land else 280)
    cys = [y0 + pitch * (i + 0.5) for i in range(n)]
    ks = _clamp(pitch * 0.58, 46, 92)
    stacked = has_desc and not land      # tall and square frames: the keyword over its explanation, not beside it
    if stacked:
        col_w = RIGHT - LEFT
        ks = _clamp(pitch * 0.36, 40, 84)
        kfits = [fit_lines(cv, k if d else t, "bold", col_w, 1, ks, 34) for (k, d), t in zip(split, items)]
        ksize = min(f[0] for f in kfits)
        div_x, dx0 = 0, LEFT
        dsize_start = _clamp(pitch * 0.24, 30, 48)
        dfit = {i: fit_lines(cv, d, "regular", RIGHT - LEFT, 2, dsize_start, 28, pitch * 0.46) for i, (_, d) in enumerate(split) if d}
        dsize = min((f[0] for f in dfit.values()), default=dsize_start)
    elif has_desc:
        col_w = 560
        kfits = [fit_lines(cv, k if d else t, "bold", col_w, 1, ks, 34) for (k, d), t in zip(split, items)]
        ksize = min(f[0] for f in kfits)
        div_x = LEFT + col_w + 34
        dx0 = div_x + 40
        dsize_start = _clamp(pitch * 0.4, 36, 54)
        dfit = {i: fit_lines(cv, d, "regular", RIGHT - dx0, 2, dsize_start, 28, pitch * 0.9) for i, (_, d) in enumerate(split) if d}
        dsize = min((f[0] for f in dfit.values()), default=dsize_start)
    else:
        col_w = RIGHT - LEFT
        kfits = [fit_lines(cv, k, "bold", col_w, 2, ks * 1.12, 34, pitch * 0.9, 1.1) for k, _ in split]
        ksize = min(f[0] for f in kfits)
        div_x, dx0, dsize, dfit = 0, 0, 0, {}
    for i in range(n):
        p = ease_out_cubic(progress(lt, times[i] - 0.2, 0.6))
        if p > 0:
            yy = y0 + pitch * i
            cv.line([(LEFT, yy), (LEFT + (RIGHT - LEFT) * p, yy)], pal.track, 2, round_caps=False)
    if progress(lt, times[-1], 0.6) > 0.5:
        yy = y0 + pitch * n
        cv.line([(LEFT, yy), (RIGHT, yy)], pal.track, 2, round_caps=False)
    for i, ((kw, desc), text) in enumerate(zip(split, items)):
        a, e = pop(lt, times[i], 0.65, 1.6)
        if a <= 0:
            continue
        f = focus(times, lt, i)
        strong = emph == i
        fe = max(f, 1.0 if strong else 0.0)
        cy = cys[i] + (1 - e) * 30
        kwtext = kw if (desc or not has_desc) else text
        lines = kfits[i][1] if kfits[i][0] == ksize else cv.wrap(kwtext, "bold", ksize, col_w)[:2]
        kcy = cy
        if stacked:
            dl = (dfit[i][1] if dfit[i][0] == dsize else cv.wrap(desc, "regular", dsize, RIGHT - LEFT)[:2]) if desc else []
            kh, dh = len(lines) * ksize * 1.1, len(dl) * dsize * 1.2
            tot = kh + (12 + dh if dl else 0)
            kcy = cy - tot / 2 + kh / 2
            if dl:
                pd = ease_out_cubic(progress(lt, times[i] + 0.12, 0.45))
                draw_lines(cv, LEFT + (1 - pd) * 24, kcy + kh / 2 + 12 + dh / 2, dl, "regular", dsize, with_alpha(th.text, pd * (0.78 + 0.22 * fe)), lh=1.2)
        if f > 0.02:
            glow_blob(cv, LEFT + 380 if land else fr.cx, cy, 760 if land else 1000, pal.c1, 0.2 * f if pal.dark else 0.12 * f)
        if strong:
            w = max(cv.measure(l, "bold", ksize) for l in lines) + 44
            h = len(lines) * ksize * 1.18 + 26
            paste_sprite(cv, sprite(cv, w, h, 20, pal.c1, pal.c2), LEFT - 6 + w / 2, kcy, 1.0, a)
        kx = LEFT + (1 - e) * -50 + (16 if strong else 0)
        kcol = pal.ink if strong else pal.accent_text
        draw_lines(cv, kx, kcy, lines, "bold", ksize * (1 + 0.03 * fe), with_alpha(kcol, a * (0.7 + 0.3 * fe)), lh=1.1)
        if has_desc and desc and not stacked:
            lines_d = dfit[i][1] if dfit[i][0] == dsize else cv.wrap(desc, "regular", dsize, RIGHT - dx0)[:2]
            pd = ease_out_cubic(progress(lt, times[i] + 0.12, 0.45))
            cv.line([(div_x, cy - pitch * 0.3), (div_x, cy + pitch * 0.3)], with_alpha(pal.accent_text, a * (0.4 + 0.5 * fe)), 4)
            draw_lines(cv, dx0 + (1 - pd) * 24, cy, lines_d, "regular", dsize, with_alpha(th.text, pd * (0.78 + 0.22 * fe)))


_LOOKS = {"rail": _rail, "spotlight": _spotlight, "icons": _icons, "cards": _cards, "keywords": _keywords}


def draw(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    items = [str(i).strip() for i in (props.get("items") or []) if str(i).strip()][:MAX_ITEMS]
    pal = pal_for(th, props.get("accent"))
    backdrop(cv, th, pal, lt)
    y = title_block(cv, th, pal, str(props.get("heading", "")).strip(), lt, ctx)
    if not items:
        return
    top, bot = area(ctx, y)
    times = clamp_first(reveal_times(len(items), dur, props.get("cues")))
    _LOOKS[list_style(props)](cv, items, props, lt, times, th, pal, top, bot, emphasis_of(props, len(items)), ctx)
