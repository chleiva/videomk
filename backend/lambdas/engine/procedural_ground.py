"""The DRAWN ground: a flat vector floor with a horizon, for cartoon conversations whose topic has no catalog backdrop that holds the cast (docs/CARTOON_GROUND_2026-11-28.md).

A backdrop type of its own (`stand_zone.PROC_ID`): its zone (ground from the horizon to the bottom edge, in every shape) and ground lines are stored like a catalog backdrop's, so the same
placement and the same hard check apply. The picture is flat like the catalog's: a sky of the video's theme, a sun or moon, a few clouds, two rows of hills, a floor reaching the
bottom edge with a lighter rim at the horizon and soft perspective stripes. No file, no fetch: pure drawing, the same pixels for the same theme and time.
"""
import math
from typing import Any, Tuple

from PIL import Image

from . import stand_zone as sz
from .canvas import Canvas, _gradient

RGB = Tuple[int, int, int]


GRASS_DARK: RGB = (52, 112, 84)
GRASS_LIGHT: RGB = (128, 184, 106)


def _mix(a: RGB, b: RGB, t: float) -> RGB:
    return tuple(int(round(a[i] * (1 - t) + b[i] * t)) for i in range(3))  # type: ignore[return-value]


def _lum(c: RGB) -> float:
    return 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]


def palette(th: Any) -> dict:
    """Colours from the video's theme: dark themes get a dusk, light themes a day."""
    dark = (_lum(th.bg_top) + _lum(th.bg_bottom)) / 2 < 140
    white, black = (255, 255, 255), (0, 0, 0)
    acc, acc2 = tuple(th.accent[:3]), tuple(th.accent2[:3])
    if dark:
        sky_top = _mix(th.bg_top, acc, 0.10)
        sky_bot = _mix(_mix(th.bg_bottom, acc2, 0.30), white, 0.10)
        far = _mix(_mix(sky_bot, GRASS_DARK, 0.25), black, 0.25)
        near = _mix(_mix(th.bg_top, GRASS_DARK, 0.45), black, 0.05)
        ground_top = _mix(_mix(th.bg_bottom, GRASS_DARK, 0.62), acc2, 0.08)   # grass in the theme's light: a floor that reads as ground, never as water
        ground_bot = _mix(_mix(th.bg_top, GRASS_DARK, 0.40), black, 0.10)
        rim = _mix(ground_top, white, 0.30)
        orb = _mix(white, acc2, 0.15)
        cloud = _mix(sky_bot, white, 0.22)
    else:
        sky_top = _mix(_mix(th.bg_top, acc2, 0.30), white, 0.25)
        sky_bot = _mix(th.bg_top, white, 0.55)
        far = _mix(_mix(sky_bot, GRASS_LIGHT, 0.40), white, 0.05)
        near = _mix(_mix(sky_bot, GRASS_LIGHT, 0.70), black, 0.04)
        ground_top = _mix(_mix(th.bg_bottom, GRASS_LIGHT, 0.72), acc2, 0.06)
        ground_bot = _mix(ground_top, black, 0.16)
        rim = _mix(ground_top, white, 0.40)
        orb = _mix(white, acc, 0.10) if _lum(acc) > 140 else _mix((255, 232, 150), white, 0.2)
        cloud = white
    return dict(dark=dark, sky_top=sky_top, sky_bot=sky_bot, far=far, near=near, ground_top=ground_top, ground_bot=ground_bot, rim=rim, orb=orb, cloud=cloud)


def _hills(cv: Canvas, hz: float, base: float, amp: float, phase: float, color: RGB, wave: Tuple[float, float, float]) -> None:
    """A row of rolling hills whose foot is at `base`, its top between base - amp and base."""
    pts = [(-4.0, base + 2)]
    n = 48
    for i in range(n + 1):
        x = cv.W * i / n
        u = x / cv.W * 2 * math.pi
        v = 0.5 + 0.5 * (0.55 * math.sin(u * wave[0] + phase) + 0.30 * math.sin(u * wave[1] + phase * 1.7) + 0.15 * math.sin(u * wave[2] + phase * 0.6))
        pts.append((x, base - amp * v))
    pts.append((cv.W + 4.0, base + 2))
    cv.polygon(pts, fill=color + (255,))


SAND_LIGHT: RGB = (236, 212, 150)
SAND_DARK: RGB = (150, 124, 84)
SEA_LIGHT: RGB = (64, 156, 196)
SEA_DARK: RGB = (28, 74, 112)


def _beach(p: dict, th: Any) -> dict:
    """The palette of the sea ground: the floor is DRY SAND (never water), the sea lies above the horizon."""
    dark = p["dark"]
    white, black = (255, 255, 255), (0, 0, 0)
    sand = SAND_DARK if dark else SAND_LIGHT
    sea = SEA_DARK if dark else SEA_LIGHT
    q = dict(p)
    q.update(ground_top=_mix(sand, tuple(th.bg_bottom[:3]), 0.12 if dark else 0.04), ground_bot=_mix(sand, black, 0.22 if dark else 0.14),
             rim=_mix(white, sea, 0.15), far=_mix(sea, p["sky_bot"], 0.35), near=sea, sea_far=_mix(sea, p["sky_bot"], 0.55), sea_near=_mix(sea, black, 0.10))
    return q


def _sea(cv: Canvas, hz: float, p: dict, lt: float) -> None:
    """The sea: a band that reaches from a far horizon down to the foam line at `hz`, a few drifting glints."""
    W, ss = cv.W, cv.ss
    top = hz * 0.80
    cv.im.paste(_gradient(W * ss, max(2, int((hz - top) * ss) + 2), p["sea_far"], p["sea_near"]), (0, int(top * ss)))
    for i in range(7):
        y = top + (hz - top) * (0.12 + 0.13 * i)
        x = (W * (0.10 + 0.37 * i) + lt * (8 + 2 * i)) % (W * 1.2) - W * 0.1
        w = W * (0.05 + 0.012 * i)
        cv.rrect(x, y, w, max(2.0, (hz - top) * 0.025), 2, fill=(255, 255, 255, 90 if not p["dark"] else 50))
    for k in range(14):   # foam: small white scallops along the shore line
        x = W * (k + 0.5) / 14
        cv.ellipse(x, hz - 1, W * 0.034, max(3.0, (hz - top) * 0.05), fill=(255, 255, 255, 170))


def draw(cv: Canvas, th: Any, ctx: Any, lt: float = 0.0, kind: str = sz.PROC_ID) -> None:
    """The ground of `ctx.frame`'s shape over the whole canvas (`kind`: stand_zone.PROC_ID, a meadow, or stand_zone.BEACH_ID, sea above and a sand floor)."""
    fr = ctx.frame
    W, H, ss = cv.W, cv.H, cv.ss
    hz = (sz.horizon(fr.aspect, kind) or 0.62) * H
    p = palette(th)
    beach = kind == sz.BEACH_ID
    if beach:
        p = _beach(p, th)
    full_w = W * ss
    # sky
    cv.im.paste(_gradient(full_w, max(2, int(hz * ss) + 2), p["sky_top"], p["sky_bot"]), (0, 0))
    u = min(W, H)
    # sun or moon with a soft halo, and clouds that drift slowly
    ox, oy, r = W * (0.80 if fr.landscape else 0.76), hz * 0.42, u * (0.075 if fr.landscape else 0.085)
    for k, a in ((3.0, 10), (2.2, 18), (1.5, 30)):
        cv.ellipse(ox, oy, r * k, r * k, fill=p["orb"] + (a,))
    cv.ellipse(ox, oy, r, r, fill=p["orb"] + (255,))
    if p["dark"]:   # the moon's craters
        for dx, dy, rr in ((-0.28, -0.2, 0.16), (0.22, 0.12, 0.2), (-0.05, 0.38, 0.1)):
            cv.ellipse(ox + dx * r, oy + dy * r, rr * r, rr * r, fill=_mix(p["orb"], p["sky_bot"], 0.22) + (255,))
    drift = (lt * 6.0) % (W * 1.3)
    for cx0, cy, s in ((0.15, 0.30, 1.0), (0.52, 0.18, 0.8), (0.88, 0.52, 0.7)):
        cx = (cx0 * W + drift) % (W * 1.3) - W * 0.15
        cw = u * 0.20 * s
        alpha = 70 if p["dark"] else 235
        for dx, dy, kx, ky in ((0, 0, 1.0, 0.34), (-0.42, 0.10, 0.62, 0.26), (0.40, 0.12, 0.66, 0.27)):
            cv.ellipse(cx + dx * cw, hz * cy + dy * cw * 0.5, cw * kx * 0.6, cw * ky * 0.6, fill=p["cloud"] + (alpha,))
    # two rows of hills
    if beach:
        _sea(cv, hz, p, lt)
    else:
        _hills(cv, hz, hz + 2, hz * 0.30, 0.6, p["far"], (1.3, 3.1, 7.0))
        _hills(cv, hz, hz + 2, hz * 0.14, 2.4, p["near"], (2.1, 4.6, 9.0))
    # the floor: from the horizon to the bottom edge
    cv.im.paste(_gradient(full_w, max(2, int((H - hz) * ss) + 2), p["ground_top"], p["ground_bot"]), (0, int(hz * ss)))
    cv.rrect(0, hz - 1, W, max(6.0, H * 0.006), 0, fill=p["rim"] + (200,))   # the light rim of the floor's far edge
    cv.rrect(0, hz + H * 0.006, W, H * 0.02, 0, fill=(0, 0, 0, 22))        # a soft darker band just below: the floor recedes
    # perspective stripes: wedges from a vanishing point on the horizon fan out to the bottom edge, alternate ones lighter
    vx, n = W * 0.5, 14
    for i in range(0, n, 2):
        a0, a1 = (i / n - 0.5) * 9.0 * W, ((i + 1) / n - 0.5) * 9.0 * W
        cv.polygon([(vx + a0 * 0.03, hz + 4), (vx + a1 * 0.03, hz + 4), (vx + a1, H + 2), (vx + a0, H + 2)], fill=(255, 255, 255, 7 if p["dark"] else 12))
    # a few tufts of grass on the floor
    for fx, fy, s in ((0.07, 0.30, 1.0), (0.31, 0.12, 0.6), (0.62, 0.20, 0.8), (0.93, 0.34, 1.1), (0.46, 0.46, 1.0), (0.16, 0.66, 1.2), (0.84, 0.74, 1.3)):
        x, y = W * fx, hz + (H - hz) * fy
        t = u * 0.012 * s
        col = _mix(p["ground_top"], (0, 0, 0), 0.20)
        if beach:   # sand has no grass: a small pebble
            cv.ellipse(x, y, t * 2.2, t * 1.1, fill=col + (255,))
            continue
        for dx, lean in ((-1.4, -0.5), (0.0, 0.0), (1.4, 0.5)):
            cv.polygon([(x + dx * t - t * 0.5, y), (x + dx * t + t * 0.5, y), (x + dx * t + lean * t * 1.4, y - t * 2.6)], fill=col + (255,))
