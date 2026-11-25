"""`photo_collage`: layouts (pure geometry, cached) and drawing of 2-9 of the user's photos on screen at once, revealed one after another.

Styles: mosaic (one big tile, the others around it, shapes chosen from the photos' orientations), polaroids (white frames thrown on a table), grid (equal tiles),
filmstrip (film strips with sprocket holes that drift while the frames light up), stack (dropped on one another, the last one largest)."""
import math
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw

from ...canvas import Canvas, with_alpha
from ...easing import ease_in_out_cubic, ease_out_back, ease_out_cubic, progress
from ...theme import Theme
from ..base import SceneCtx
from . import _photo_kit as K

STYLES = ("mosaic", "polaroids", "grid", "filmstrip", "stack")
GAP = 14.0
AX0, AX1, AY0 = 90.0, 1830.0, 50.0
REVEAL_S = 0.45
Rect = Tuple[float, float, float, float]          # x, y, w, h (logical)


def default_style(n: int, orientations: List[str]) -> str:
    """When the director names no style: few photos look best as polaroids, many as a grid when they share a shape, else a mosaic."""
    same = len(set(orientations)) <= 1 if orientations else True
    if n <= 4:
        return "polaroids"
    if n >= 7 and same:
        return "grid"
    return "mosaic"


# ----------------------------------------------------------------------------------------------------------------------------- mosaic geometry
def _split(k: int, c: int) -> List[int]:
    base, extra = divmod(k, c)
    return [base + (1 if i < extra else 0) for i in range(c)]


def _mosaic_templates(n: int, ax0: float, ay0: float, aw: float, ah: float) -> List[List[Rect]]:
    """Candidate layouts: one hero column (a single big tile) and the other photos in 1-4 columns; the hero on the left, right or in the middle."""
    k = n - 1
    out: List[List[Rect]] = []
    for hpos in ("left", "right", "mid"):
        for hf in (0.30, 0.36, 0.42, 0.50):
            for c in range(1, min(4, k) + 1):
                if hpos == "mid" and c < 2:
                    continue
                counts = _split(k, c)
                cols: List[Tuple[float, int, bool]] = [((1 - hf) / c, cnt, False) for cnt in counts]
                hero = (hf, 1, True)
                if hpos == "left":
                    cols = [hero] + cols
                elif hpos == "right":
                    cols = cols + [hero]
                else:
                    cut = c // 2
                    cols = cols[:cut] + [hero] + cols[cut:]
                x = ax0 - GAP / 2
                hero_rect: Optional[Rect] = None
                rects: List[Rect] = []
                full_w, full_h = aw + GAP, ah + GAP
                for frac, cnt, is_hero in cols:
                    cw = full_w * frac
                    for r in range(cnt):
                        rh = full_h / cnt
                        rect = (x + GAP / 2, ay0 - GAP / 2 + r * rh + GAP / 2, cw - GAP, rh - GAP)
                        if is_hero:
                            hero_rect = rect
                        else:
                            rects.append(rect)
                    x += cw
                if hero_rect is None or min(min(r[2], r[3]) for r in rects + [hero_rect]) < 150:
                    continue
                out.append([hero_rect] + rects)
    return out


def _assign(cells: List[Rect], ratios: Tuple[float, ...]) -> Tuple[float, List[int]]:
    """photo index for each cell, minimising how much each photo would be cropped (hero cell: also a mild preference for the first photo)."""
    n = len(cells)

    def cost(ci: int, pi: int) -> float:
        d = math.log((cells[ci][2] / cells[ci][3]) / ratios[pi])
        return d * d + (0.05 * pi if ci == 0 else 0.0)

    order = sorted(range(n), key=lambda i: -cells[i][2] * cells[i][3])
    free = set(range(n))
    pick = [0] * n
    for ci in order:
        best = min(free, key=lambda pi: cost(ci, pi))
        pick[ci] = best
        free.discard(best)
    improved = True
    while improved:
        improved = False
        for a in range(n):
            for b in range(a + 1, n):
                if cost(a, pick[b]) + cost(b, pick[a]) < cost(a, pick[a]) + cost(b, pick[b]) - 1e-9:
                    pick[a], pick[b] = pick[b], pick[a]
                    improved = True
    return sum(cost(i, pick[i]) for i in range(n)), pick


@lru_cache(maxsize=128)
def mosaic_layout(ratios: Tuple[float, ...], ax0: float, ay0: float, aw: float, ah: float) -> Tuple[Rect, ...]:
    n = len(ratios)
    best: Optional[Tuple[float, List[Rect], List[int]]] = None
    for cells in _mosaic_templates(n, ax0, ay0, aw, ah):
        c, pick = _assign(cells, ratios)
        if best is None or c < best[0] - 1e-9:
            best = (c, cells, pick)
    if best is None:                                      # no template fits (tiny area): equal tiles
        return grid_layout(ratios, ax0, ay0, aw, ah)[0]
    _, cells, pick = best
    out: List[Optional[Rect]] = [None] * n
    for ci, pi in enumerate(pick):
        out[pi] = cells[ci]
    return tuple(r for r in out if r is not None)


# ----------------------------------------------------------------------------------------------------------------------------- grid geometry
@lru_cache(maxsize=128)
def grid_layout(ratios: Tuple[float, ...], ax0: float, ay0: float, aw: float, ah: float) -> Tuple[Tuple[Rect, ...], float]:
    n = len(ratios)
    g = GAP + 4
    best = None
    for rows in range(1, min(3, n) + 1):
        cols = math.ceil(n / rows)
        t = min((1.5, 1.0, 0.75), key=lambda t: sum(math.log(t / r) ** 2 for r in ratios))
        w = min((aw - (cols - 1) * g) / cols, ((ah - (rows - 1) * g) / rows) * t)
        h = w / t
        if best is None or w * h > best[0] * 1.04:
            best = (w * h, rows, cols, w, h)
    _, rows, cols, w, h = best
    counts = _split(n, rows)
    total_h = rows * h + (rows - 1) * g
    y = ay0 + (ah - total_h) / 2
    rects: List[Rect] = []
    for cnt in counts:
        row_w = cnt * w + (cnt - 1) * g
        x = ax0 + (aw - row_w) / 2
        for _ in range(cnt):
            rects.append((x, y, w, h))
            x += w + g
        y += h + g
    return tuple(rects), 18.0


# ----------------------------------------------------------------------------------------------------------------------------- polaroids and stack geometry
def _frame_size(ratio: float, bw: float, bh: float, border: float = 0.045, bottom: float = 0.17) -> Tuple[float, float, float]:
    """(photo w, photo h, long side s) of the largest framed photo that fits bw x bh; border and bottom are fractions of the photo's long side."""
    a, b = min(1.0, ratio), min(1.0, 1.0 / ratio)
    s = min(bw / (a + 2 * border), bh / (b + border + bottom))
    return s * a, s * b, s


@lru_cache(maxsize=128)
def polaroid_layout(ids: Tuple[str, ...], ratios: Tuple[float, ...], ax0: float, ay0: float, aw: float, ah: float):
    """For each photo: (cx, cy, photo_w, photo_h, border, bottom_border, angle). Rows of frames, jittered, overlapping about 10%."""
    n = len(ratios)
    best = None
    for rows in (1, 2):
        if rows > n:
            continue
        counts = _split(n, rows)
        cw, chh = aw / max(counts), ah / rows
        total = sum(_frame_size(r, cw * 1.12, chh * 1.08)[2] ** 2 for r in ratios)
        if best is None or total > best[0] * 1.03:
            best = (total, rows, counts, cw, chh)
    _, rows, counts, cw, chh = best
    seed = ",".join(ids)
    out = []
    i = 0
    for ri, cnt in enumerate(counts):
        row_w = cw * cnt
        x0 = ax0 + (aw - row_w) / 2
        for ci in range(cnt):
            r = ratios[i]
            pw, ph, s = _frame_size(r, cw * 1.12, chh * 1.08)
            bd, bt = 0.045 * s, 0.17 * s
            ang = K.jitter(seed, i * 3) * 9.0
            if abs(ang) < 2.5:
                ang = 2.5 if ang >= 0 else -2.5
            if i > 0 and ang * out[-1][6] > 0 and abs(ang) > 4:       # neighbours lean opposite ways more often than not
                ang = -ang
            fw, fh = pw + 2 * bd, ph + bd + bt
            ex = (abs(math.cos(math.radians(ang))) * fw + abs(math.sin(math.radians(ang))) * fh) / 2
            ey = (abs(math.sin(math.radians(ang))) * fw + abs(math.cos(math.radians(ang))) * fh) / 2
            cx = x0 + cw * (ci + 0.5) + K.jitter(seed, i * 3 + 1) * cw * 0.05
            cy = ay0 + chh * (ri + 0.5) + K.jitter(seed, i * 3 + 2) * chh * 0.05
            cx = min(max(cx, ax0 + ex), ax0 + aw - ex) if ex * 2 < aw else ax0 + aw / 2
            cy = min(max(cy, ay0 + ey), ay0 + ah - ey) if ey * 2 < ah else ay0 + ah / 2
            out.append((cx, cy, pw, ph, bd, bt, ang))
            i += 1
    return tuple(out)


@lru_cache(maxsize=128)
def stack_layout(ids: Tuple[str, ...], ratios: Tuple[float, ...], ax0: float, ay0: float, aw: float, ah: float):
    """For each photo: (cx, cy, photo_w, photo_h, border, angle): earlier photos smaller and further from the middle, the last one largest and nearly straight."""
    n = len(ratios)
    seed = ",".join(ids)
    out = []
    mx, my = ax0 + aw / 2, ay0 + ah / 2
    for i, r in enumerate(ratios):
        t = i / (n - 1) if n > 1 else 1.0
        f = 0.58 + 0.42 * t ** 0.85
        pw, ph, s = _frame_size(r, min(aw * 0.62, 1100) * f, ah * 0.97 * f, border=0.03, bottom=0.03)
        bd = 0.03 * s
        ang = K.jitter(seed, i * 3) * 7.0 * (1.0 - 0.55 * t)
        if abs(ang) < 1.5 and i < n - 1:
            ang = 1.5 if i % 2 else -1.5
        side = -1.0 if i % 2 else 1.0
        spread = (1 - t) ** 0.9
        cx = mx + side * spread * aw * (0.27 + 0.05 * abs(K.jitter(seed, i * 3 + 1)))
        cy = my + K.jitter(seed, i * 3 + 2) * spread * ah * 0.12
        fw, fh = pw + 2 * bd, ph + 2 * bd
        ex = (abs(math.cos(math.radians(ang))) * fw + abs(math.sin(math.radians(ang))) * fh) / 2
        ey = (abs(math.sin(math.radians(ang))) * fw + abs(math.cos(math.radians(ang))) * fh) / 2
        cx = min(max(cx, ax0 + ex), ax0 + aw - ex) if ex * 2 < aw else mx
        cy = min(max(cy, ay0 + ey), ay0 + ah - ey) if ey * 2 < ah else my
        out.append((cx, cy, pw, ph, bd, ang))
    return tuple(out)


# ----------------------------------------------------------------------------------------------------------------------------- film strip geometry
BAND = 40.0          # the sprocket band above and below the frames
STRIP_MARGIN = 520.0
FRAME_PAD = 18.0
FRAME_GAP = 16.0


@lru_cache(maxsize=64)
def film_layout(ratios: Tuple[float, ...], ay0: float, ah: float):
    """Rows of the film strips: [{y, h, ih, frames: [(photo index, x, w)], dir}]; x is measured from the left edge of the screen."""
    n = len(ratios)
    nrows = 1 if n <= 5 else 2
    counts = _split(n, nrows)
    max_w = 1840.0
    hs = min(430.0, (ah - (nrows - 1) * 26) / nrows)
    ih = hs - 2 * BAND
    for _ in range(2):
        idx = 0
        worst = 1.0
        for cnt in counts:
            ws = [ih * max(0.72, min(1.5, ratios[idx + j])) for j in range(cnt)]
            total = sum(ws) + FRAME_GAP * (cnt - 1) + 2 * FRAME_PAD
            worst = min(worst, max_w / total)
            idx += cnt
        if worst < 1.0:
            ih *= worst
    hs = ih + 2 * BAND
    block = nrows * hs + (nrows - 1) * 26
    y = ay0 + (ah - block) / 2
    rows = []
    idx = 0
    for ri, cnt in enumerate(counts):
        ws = [ih * max(0.72, min(1.5, ratios[idx + j])) for j in range(cnt)]
        total = sum(ws) + FRAME_GAP * (cnt - 1)
        x = (1920 - total) / 2
        frames = []
        for j in range(cnt):
            frames.append((idx + j, x, ws[j]))
            x += ws[j] + FRAME_GAP
        rows.append({"y": y, "h": hs, "ih": ih, "frames": frames, "dir": -1.0 if ri % 2 == 0 else 1.0})
        y += hs + 26
        idx += cnt
    return rows


def _film_strip_sprite(cv: Canvas, row: Dict[str, Any], srcs: List[Optional[Image.Image]], th: Theme) -> K.Sprite:
    """The film body with sprocket holes and every frame dimmed (cached per photo set and size); frames light up on top of it, per frame."""
    ss = cv.ss
    key = ("film", tuple(K.sid(s) for s in srcs[row["frames"][0][0]: row["frames"][-1][0] + 1]), round(row["h"]), round(row["ih"]), ss, th.name,
           tuple(round(f[1]) for f in row["frames"]))

    def build() -> K.Sprite:
        W, H = int((1920 + 2 * STRIP_MARGIN) * ss), int(row["h"] * ss)
        im = Image.new("RGB", (W, H), (17, 17, 21))
        d = ImageDraw.Draw(im, "RGBA")
        band = int(BAND * ss)
        d.rectangle([0, band - 2 * ss, W, band - ss], fill=(255, 255, 255, 22))
        d.rectangle([0, H - band + ss, W, H - band + 2 * ss], fill=(255, 255, 255, 22))
        pitch, hw, hh = 46 * ss, 24 * ss, 16 * ss
        x = 6 * ss
        while x < W:
            for cy in (band / 2, H - band / 2):
                d.rounded_rectangle([x, cy - hh / 2, x + hw, cy + hh / 2], 4 * ss, fill=(233, 231, 224, 235))
            x += pitch
        for idx, fx, fw in row["frames"]:
            w, h = int(fw * ss), int(row["ih"] * ss)
            tile = K.photo_tile(srcs[idx], w, h, th, idx).point(lambda v: int(v * 0.36))
            im.paste(K.rounded(tile, 3 * ss), (int((fx + STRIP_MARGIN) * ss), band), K.rounded(tile, 3 * ss).getchannel("A"))
        return K.Sprite(im, Image.new("L", (W, H), 255))
    return K.cached(key, build, pin=tuple(srcs))


def _draw_film(cv: Canvas, th: Theme, srcs, ratios, times, lt: float, dur: float, area: Rect) -> None:
    ss = cv.ss
    rows = film_layout(tuple(ratios), area[1], area[3])
    n = len(srcs)
    latest = max([i for i in range(n) if lt >= times[i]] or [-1])
    for row in rows:
        sp = _film_strip_sprite(cv, row, srcs, th)
        enter = 1 - ease_out_cubic(progress(lt, 0.0, 1.0))
        drift = row["dir"] * (-70 + 140 * min(1.0, lt / max(dur, 1.0)))
        off = drift + row["dir"] * -1 * enter * 380
        a = min(1.0, progress(lt, 0.0, 0.5) * 1.5)
        K.blit(cv, sp, 960 + off, row["y"] + row["h"] / 2, alpha=a)
        for idx, fx, fw in row["frames"]:
            p = ease_out_cubic(progress(lt, times[idx], REVEAL_S))
            if p <= 0.01:
                continue
            w, h = int(fw * ss), int(row["ih"] * ss)
            tile = K.cached(("filmlit", K.sid(srcs[idx]), w, h, th.name, idx % 2), lambda: K.sprite_of(K.rounded(K.photo_tile(srcs[idx], w, h, th, idx), 3 * ss)), pin=srcs[idx])
            cx = fx + fw / 2 + off
            cy = row["y"] + row["h"] / 2
            K.blit(cv, tile, cx, cy, scale=1.0 + 0.05 * (1 - p), alpha=p * a)
            if idx == latest:
                cv.rrect(cx - fw / 2 - 3, cy - row["ih"] / 2 - 3, fw + 6, row["ih"] + 6, 6, outline=with_alpha(th.accent, p * a), width=5)


# ----------------------------------------------------------------------------------------------------------------------------- sprites
def _tile_sprite(cv: Canvas, src, w: float, h: float, r: float, th: Theme, idx: int) -> K.Sprite:
    ss = cv.ss
    pw, ph = int(round(w * ss)), int(round(h * ss))
    key = ("tilesp", K.sid(src), pw, ph, int(r * ss), th.name if src is None else "", idx % 2 if src is None else 0)
    return K.cached(key, lambda: K.sprite_of(K.shadowed(K.rounded(K.photo_tile(src, pw, ph, th, idx), int(r * ss)), int(11 * ss), int(5 * ss), 0.42)), pin=src)


def _framed_sprite(cv: Canvas, src, pw: float, ph: float, bd: float, bt: float, angle: float, th: Theme, idx: int, paper=(250, 248, 243)) -> K.Sprite:
    """A white-bordered photo (polaroid when bt is large), rotated, with its drop shadow."""
    ss = cv.ss
    w, h = int(round(pw * ss)), int(round(ph * ss))
    b, t = int(round(bd * ss)), int(round(bt * ss))
    key = ("framesp", K.sid(src), w, h, b, t, round(angle, 1), th.name if src is None else "", idx % 2 if src is None else 0)

    def build() -> K.Sprite:
        card = Image.new("RGB", (w + 2 * b, h + b + t), paper)
        card.paste(K.fit_photo(src, w, h, th, idx), (b, b))
        d = ImageDraw.Draw(card, "RGBA")
        d.rectangle([b, b, b + w - 1, b + h - 1], outline=(0, 0, 0, 38), width=max(1, ss // 2))
        sp = K.rotated(K.rounded(card, int(3 * ss)), angle)
        return K.sprite_of(K.shadowed(sp, int(16 * ss), int(9 * ss), 0.5))
    return K.cached(key, build, pin=src)


# ----------------------------------------------------------------------------------------------------------------------------- animation
def _dir(seed: str, k: int) -> Tuple[float, float]:
    a = (K.jitter(seed, k) + 1) * math.pi
    return math.cos(a), math.sin(a)


def _anim(kind: str, p: float, seed: str, base_off: Tuple[float, float] = (0, 0)) -> Tuple[float, float, float, float]:
    """(dx, dy, scale, alpha) of a photo `p` (0..1) of the way through its entrance; (0, 0, 1, 1) at rest."""
    if p >= 1.0:
        return 0.0, 0.0, 1.0, 1.0
    e = ease_out_cubic(p)
    if kind == "pop":
        return 0.0, 0.0, 0.8 + 0.2 * ease_out_back(p, 1.6), min(1.0, p * 3.0)
    if kind == "slide":
        return base_off[0] * (1 - e), base_off[1] * (1 - e), 0.96 + 0.04 * e, min(1.0, p * 2.5)
    if kind == "drop":
        return 0.0, -(1 - ease_out_back(p, 1.1)) * 240, 1.0 + 0.14 * (1 - e), min(1.0, p * 4.0)
    ux, uy = _dir(seed, 7)                                  # fly: from outside, towards the table
    return ux * 520 * (1 - e), (uy * 260 - 120) * (1 - e), 0.78 + 0.22 * ease_out_back(p, 1.3), min(1.0, p * 3.0)


# ----------------------------------------------------------------------------------------------------------------------------- the scene
def draw_collage(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    ids = tuple(props.get("photos") or ())
    assets = [str(a) for a in (props.get("assets") or [])]
    n = len(ids) or len(assets) or 3
    n = max(2, min(9, n))
    ids = ids if len(ids) == n else tuple(f"P{i + 1}" for i in range(n))
    srcs: List[Optional[Image.Image]] = []
    for i in range(n):
        try:
            srcs.append(ctx.resolve_image(assets[i]) if i < len(assets) and assets[i] else None)
        except Exception:                                    # an unreadable photo is a placeholder, never a crash
            srcs.append(None)
    given = [float(x) for x in (props.get("ratios") or []) if isinstance(x, (int, float)) and x > 0.1]
    ratios = tuple(round(given[i], 3) if i < len(given) else round(srcs[i].width / srcs[i].height, 3) if srcs[i] is not None else K.DEFAULT_RATIOS[i % len(K.DEFAULT_RATIOS)]
                   for i in range(n))
    orients = [K.orientation_of(r) for r in ratios]
    style = props.get("style") if props.get("style") in STYLES else default_style(n, orients)
    times = K.reveal_schedule(n, dur, props.get("cues"))

    first = next((s for s in srcs if s is not None), None)
    K.backdrop(cv, first, th)

    title, subtitle = str(props.get("title") or ""), str(props.get("subtitle") or "")
    lab = K.label_metrics(cv, title, subtitle, 1000)
    bottom = ctx.bottom - 4
    ay1 = bottom - ((lab["h"] + 14) if lab else 0)
    area = (AX0, AY0, AX1 - AX0, ay1 - AY0)

    if style == "filmstrip":
        _draw_film(cv, th, srcs, ratios, times, lt, dur, area)
    elif style in ("mosaic", "grid"):
        rects, rad = (grid_layout(ratios, *area)) if style == "grid" else (mosaic_layout(ratios, *area), 22.0)
        cx_mid = area[0] + area[2] / 2
        for i in range(n):
            p = progress(lt, times[i], REVEAL_S)
            if p <= 0:
                continue
            x, y, w, h = rects[i]
            sp = _tile_sprite(cv, srcs[i], w, h, rad, th, i)
            off = ((-1 if x + w / 2 < cx_mid else 1) * 90, 0)
            dx, dy, sc, a = _anim("pop" if style == "grid" else "slide", p, ids[i], off)
            K.blit(cv, sp, x + w / 2 + dx, y + h / 2 + dy, scale=sc, alpha=a)
    elif style == "polaroids":
        lay = polaroid_layout(ids, ratios, *area)
        for i in range(n):
            p = progress(lt, times[i], REVEAL_S + 0.1)
            if p <= 0:
                continue
            cx, cy, pw, ph, bd, bt, ang = lay[i]
            sp = _framed_sprite(cv, srcs[i], pw, ph, bd, bt, ang, th, i)
            dx, dy, sc, a = _anim("fly", p, ids[i])
            K.blit(cv, sp, cx + dx, cy + dy, scale=sc, alpha=a)
    else:                                                    # stack
        lay = stack_layout(ids, ratios, *area)
        for i in range(n):
            p = progress(lt, times[i], REVEAL_S + 0.1)
            if p <= 0:
                continue
            cx, cy, pw, ph, bd, ang = lay[i]
            sp = _framed_sprite(cv, srcs[i], pw, ph, bd, bd, ang, th, i)
            dx, dy, sc, a = _anim("drop", p, ids[i])
            K.blit(cv, sp, cx + dx, cy + dy, scale=sc, alpha=a)

    if lab:
        K.draw_label(cv, th, lab, lt, 90, bottom, t0=min(0.9, times[min(1, n - 1)] + 0.2))
