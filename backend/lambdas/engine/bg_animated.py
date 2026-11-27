"""Procedural animated backgrounds: gas, smoke, lava, aurora, mesh and bokeh. PROTOTYPE, not used by any scene yet (docs/BACKGROUNDS_ANIMATED.md).

Why procedural: zero storage, native at any size and aspect (16:9, 9:16, 1:1, 4:5 and 4K), palette follows the video's theme, endless variety from a seed,
and every style is a SEAMLESS LOOP by construction: all time dependence is `sin(... + k * 2*pi*t/T)` with an integer k, so frame t and frame t+T are identical.

How it stays cheap: the picture is computed on a small grid (about 360 px on the long side; gas, smoke and light have no fine detail), smoothly enlarged
(bicubic, floating point) to the requested size, and dithered with triangular noise before the 8-bit rounding, which removes the banding that a dark smooth
gradient would otherwise show. `render(spec, w, h, t)` returns an (h, w, 3) uint8 array.

Text safety: a quiet zone (the middle of the frame and the caption band) limits how bright (dark mode) or how dark (light mode) the picture can get, so the
video's own text keeps at least `min_contrast` (WCAG, 4.5 by default) there; the edges stay lively. `contrast_report` measures it on real frames.

Everything is a pure function of (spec, w, h, t): a chunk rendered anywhere in a video is identical.
"""
import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np
from PIL import Image

STYLES: Tuple[str, ...] = ("gas", "smoke", "lava", "aurora", "mesh", "bokeh")
MODES: Tuple[str, ...] = ("dark", "light")

RGB = Tuple[float, float, float]
# name -> (bg top, bg bottom, accent a, accent b), the same family as the themes (engine/theme.py)
PALETTES: Dict[str, Tuple[RGB, RGB, RGB, RGB]] = {
    "midnight": ((10, 14, 32), (30, 27, 75), (99, 102, 241), (34, 211, 238)),
    "sunrise": ((28, 16, 66), (122, 31, 92), (251, 146, 60), (253, 224, 71)),
    "ocean": ((4, 18, 34), (7, 44, 74), (14, 116, 144), (45, 212, 191)),
    "ember": ((24, 8, 10), (70, 16, 22), (220, 60, 40), (251, 191, 36)),
    "violet": ((14, 8, 32), (46, 16, 84), (139, 92, 246), (236, 72, 153)),
    "forest": ((6, 22, 18), (10, 54, 46), (16, 185, 129), (163, 230, 53)),
    "mono": ((12, 12, 16), (34, 36, 44), (120, 130, 150), (220, 225, 235)),
}
THEME_PALETTE = {"midnight": "midnight", "sunrise": "sunrise", "paper": "violet"}   # the engine's three themes -> a palette (paper is a light theme: mode light)

DARK_TEXT: RGB = (255, 255, 255)        # text on dark backgrounds
LIGHT_TEXT: RGB = (31, 41, 55)          # text on light backgrounds (the paper theme's ink)
MIN_CONTRAST = 4.5
INTERNAL_LONG = 360                      # pixels of the small grid on the long side
LUT_N = 1024
TWO_PI = 2.0 * math.pi


@dataclass(frozen=True)
class BgSpec:
    style: str = "gas"
    palette: str = "midnight"
    mode: str = "dark"
    speed: float = 1.0          # 0.5 .. 2 (how many wavelengths things drift per loop)
    intensity: float = 1.0      # 0.4 .. 1.4 (contrast of the shapes)
    seed: int = 1
    loop_seconds: float = 10.0  # 6 .. 20
    quiet: float = 0.8          # 0 .. 1, how strongly the middle and the caption band are calmed


def sanitize(raw: Optional[Dict[str, Any]], theme: str = "midnight") -> BgSpec:
    """Cleans a dict from the planner: only known values survive, numbers are clamped, anything else is dropped."""
    raw = raw if isinstance(raw, dict) else {}

    def num(key, lo, hi, default):
        v = raw.get(key)
        return float(min(hi, max(lo, v))) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) else default

    style = str(raw.get("style", "")).lower()
    pal = str(raw.get("palette", "")).lower()
    mode = str(raw.get("mode", "")).lower()
    seed = raw.get("seed")
    return BgSpec(
        style=style if style in STYLES else "gas",
        palette=pal if pal in PALETTES else THEME_PALETTE.get(theme, "midnight"),
        mode=mode if mode in MODES else ("light" if theme == "paper" else "dark"),
        speed=num("speed", 0.5, 2.0, 1.0), intensity=num("intensity", 0.4, 1.4, 1.0),
        seed=int(seed) % 10000 if isinstance(seed, int) and not isinstance(seed, bool) else 1,
        loop_seconds=num("loop_seconds", 6.0, 20.0, 10.0), quiet=num("quiet", 0.0, 1.0, 0.8),
    )


# ------------------------------------------------------------------ colour helpers
def _mix(a: RGB, b: RGB, k: float) -> RGB:
    return tuple(a[i] * (1 - k) + b[i] * k for i in range(3))


def _lum(rgb: Iterable[float]) -> float:
    """WCAG relative luminance of an sRGB colour (0..255 channels)."""
    out = []
    for c in rgb:
        c = c / 255.0
        out.append(c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * out[0] + 0.7152 * out[1] + 0.0722 * out[2]


def contrast(a: Iterable[float], b: Iterable[float]) -> float:
    la, lb = _lum(a), _lum(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def _stops(pal: str, mode: str) -> List[RGB]:
    top, bot, a, b = PALETTES[pal]
    w = (255.0, 255.0, 255.0)
    if mode == "light":
        return [(251.0, 250.0, 247.0), _mix(w, b, 0.16), _mix(w, a, 0.26), _mix(w, a, 0.42), _mix(w, b, 0.5), _mix(w, a, 0.62)]
    return [top, bot, _mix(bot, a, 0.38), _mix(bot, a, 0.8), _mix(a, b, 0.45), _mix(b, w, 0.2)]


@lru_cache(maxsize=64)
def _lut(pal: str, mode: str) -> np.ndarray:
    """A smooth colour ramp, LUT_N x 3 float32 (smoothstep between evenly spaced stops)."""
    st = np.array(_stops(pal, mode), np.float32)
    x = np.linspace(0, len(st) - 1, LUT_N, dtype=np.float32)
    i = np.minimum(x.astype(np.int32), len(st) - 2)
    f = x - i
    f = f * f * (3 - 2 * f)
    return (st[i] * (1 - f)[:, None] + st[i + 1] * f[:, None]).astype(np.float32)


def _ramp(lut: np.ndarray, f: np.ndarray) -> np.ndarray:
    idx = np.clip(f * (LUT_N - 1) + 0.5, 0, LUT_N - 1).astype(np.int32)
    return lut[idx]


# ------------------------------------------------------------------ sinusoid fields (periodic in time by construction)
class Waves:
    """A sum of travelling sine waves. Each wave has an integer time frequency, so phase(t + T) = phase(t) + 2*pi*k: seamless loops."""

    def __init__(self, rng: np.random.RandomState, n: int, fmin: float, fmax: float, speed: float, kmax: int = 2,
                 aniso: Tuple[float, float] = (1.0, 1.0), angle0: float = 0.0, spread: float = math.pi):
        f = np.exp(rng.uniform(math.log(fmin), math.log(fmax), n))        # cycles per unit
        th = angle0 + rng.uniform(-spread, spread, n)
        self.kx = (TWO_PI * f * np.cos(th) * aniso[0]).astype(np.float32)
        self.ky = (TWO_PI * f * np.sin(th) * aniso[1]).astype(np.float32)
        self.ph = rng.uniform(0, TWO_PI, n).astype(np.float32)
        base = rng.randint(1, kmax + 1, n)
        self.kt = np.maximum(1, np.round(base * speed)).astype(np.int32) * rng.choice([-1, 1], n)
        amp = (1.0 / np.maximum(f, 0.3)) ** 0.5
        self.amp = (amp / math.sqrt(float(np.sum(amp ** 2)) / 2.0)).astype(np.float32)   # unit standard deviation overall

    def eval(self, u: np.ndarray, v: np.ndarray, tp: float) -> np.ndarray:
        acc = np.zeros(u.shape, np.float32)
        for i in range(len(self.amp)):
            acc += self.amp[i] * np.sin(self.kx[i] * u + self.ky[i] * v + np.float32(self.ph[i] + self.kt[i] * tp))
        return acc


def _sig(z: np.ndarray, gain: float) -> np.ndarray:
    return 0.5 + 0.5 * np.tanh(z * gain)


# ------------------------------------------------------------------ the per-(spec, size) plan: everything that does not depend on time
@dataclass
class _Plan:
    iw: int
    ih: int
    u: np.ndarray
    v: np.ndarray
    x: np.ndarray
    y: np.ndarray
    quiet: np.ndarray          # 0..1 mask of the text zone
    cap: np.ndarray            # per pixel brightness limit on the "lum2" scale (dark: maximum, light: minimum)
    lut: np.ndarray
    st: Dict[str, Any]
    qe: Optional[np.ndarray] = None   # 0..1: how much the quiet-zone limit applies per pixel
    ex: float = 1.0      # extent of the frame in u units (width / sqrt(w*h))
    ey: float = 1.0


def _quiet_mask(x: np.ndarray, y: np.ndarray, portrait: bool) -> np.ndarray:
    """1 where the video's own text lives (a broad middle: titles, lists, captions), falling to 0 in the corners. One smooth lobe, no seams."""
    e = ((x - 0.5) / 0.5) ** 2 + ((y - 0.5) / 0.5) ** 2
    t = np.clip((e - 0.35) / 1.2, 0, 1)
    return (1.0 - t * t * (3 - 2 * t)).astype(np.float32)


def _cap_scale(mode: str) -> float:
    """The limit inside the quiet zone, on the scale of `lum2` (sqrt of the gamma-2 luminance, 0..1) for dark mode: the brightest allowed pixel (white text needs
    1.05 / (Y + 0.05) >= MIN_CONTRAST); for light mode on the DARKNESS (1 - lum2): the darkest allowed pixel (dark ink needs (Y + 0.05) / (Yink + 0.05) >= MIN_CONTRAST)."""
    if mode == "dark":
        y = 1.05 / MIN_CONTRAST - 0.05
        return float((y * 0.9) ** (1 / 2.2))
    y = MIN_CONTRAST * (_lum(LIGHT_TEXT) + 0.05) - 0.05
    return float(1.0 - (y * 1.1) ** (1 / 2.2))       # margin for the approximation and for dithering


def _zone(q: np.ndarray, quiet: float) -> np.ndarray:
    z = np.clip(q * quiet * 1.6, 0.0, 1.0)             # 1 where the limit is fully applied (what contrast_report measures); smoothstep: no visible edge
    return z * z * (3 - 2 * z)


@lru_cache(maxsize=32)
def _plan(spec: BgSpec, w: int, h: int) -> _Plan:
    long_ = INTERNAL_LONG
    if w >= h:
        iw, ih = long_, max(8, int(round(long_ * h / w)))
    else:
        ih, iw = long_, max(8, int(round(long_ * w / h)))
    xs = (np.arange(iw, dtype=np.float32) + 0.5) / iw
    ys = (np.arange(ih, dtype=np.float32) + 0.5) / ih
    x, y = np.meshgrid(xs, ys)
    ref = math.sqrt(w * h)                                             # same feature size on every aspect
    u = ((x - 0.5) * (w / ref)).astype(np.float32)
    v = ((y - 0.5) * (h / ref)).astype(np.float32)
    q = _quiet_mask(x, y, h > w)
    capv = _cap_scale(spec.mode)
    qe = _zone(q, spec.quiet)
    cap = ((1.5 ** (1 - qe)) * (capv ** qe)).astype(np.float32)        # geometric blend: a gradual, invisible transition
    rng = np.random.RandomState(spec.seed * 7919 + STYLES.index(spec.style) * 104729 % 99991)
    st = _setup(spec, rng, u, v, x, y)
    return _Plan(iw, ih, u, v, x, y, q, cap, _lut(spec.palette, spec.mode), st, qe=qe, ex=w / ref, ey=h / ref)


# ------------------------------------------------------------------ styles: setup (random constants) and draw (per frame, returns float RGB 0..255 on the small grid)
def _setup(spec: BgSpec, rng: np.random.RandomState, u, v, x, y) -> Dict[str, Any]:
    s = spec.speed
    if spec.style == "gas":
        return dict(wx=Waves(rng, 5, 0.45, 1.1, s, 1), wy=Waves(rng, 5, 0.45, 1.1, s, 1), w2x=Waves(rng, 4, 0.9, 1.8, s, 2), w2y=Waves(rng, 4, 0.9, 1.8, s, 2),
                    fb=Waves(rng, 9, 0.45, 1.7, s, 2))
    if spec.style == "smoke":
        ang = rng.uniform(-0.5, 0.5)
        return dict(fb=Waves(rng, 16, 0.9, 3.4, s, 2, aniso=(0.22, 1.0), angle0=ang, spread=0.45), wx=Waves(rng, 5, 0.6, 1.4, s, 1), wy=Waves(rng, 5, 0.6, 1.4, s, 1), ang=ang)
    if spec.style == "lava":
        n = 8
        return dict(c=rng.uniform(0.15, 0.85, (n, 2)).astype(np.float32), a=rng.uniform(0.08, 0.28, (n, 2)).astype(np.float32),
                    k=(rng.randint(1, 3, (n, 2)) * rng.choice([-1, 1], (n, 2))).astype(np.int32), ph=rng.uniform(0, TWO_PI, (n, 2)).astype(np.float32),
                    r=rng.uniform(0.085, 0.17, n).astype(np.float32), col=rng.uniform(0, 1, n).astype(np.float32))
    if spec.style == "aurora":
        n = 4
        return dict(y0=np.linspace(0.30, 0.62, n).astype(np.float32) + rng.uniform(-0.04, 0.04, n).astype(np.float32),
                    a1=rng.uniform(0.05, 0.11, n).astype(np.float32), a2=rng.uniform(0.02, 0.05, n).astype(np.float32),
                    f1=rng.uniform(1.1, 2.1, n).astype(np.float32), f2=rng.uniform(2.4, 4.0, n).astype(np.float32),
                    p1=rng.uniform(0, TWO_PI, n).astype(np.float32), p2=rng.uniform(0, TWO_PI, n).astype(np.float32),
                    k1=(np.maximum(1, np.round(rng.randint(1, 3, n) * s)) * rng.choice([-1, 1], n)).astype(np.int32),
                    k2=(np.maximum(1, np.round(rng.randint(1, 3, n) * s)) * rng.choice([-1, 1], n)).astype(np.int32),
                    fr=rng.uniform(14, 26, n).astype(np.float32), pr=rng.uniform(0, TWO_PI, n).astype(np.float32),
                    kr=(np.maximum(1, np.round(rng.randint(1, 3, n) * s)) * rng.choice([-1, 1], n)).astype(np.int32),
                    hue=np.linspace(0.18, 0.78, n).astype(np.float32), wd=rng.uniform(0.08, 0.14, n).astype(np.float32))
    if spec.style == "mesh":
        n = 6
        return dict(c=rng.uniform(0.1, 0.9, (n, 2)).astype(np.float32), a=rng.uniform(0.2, 0.55, (n, 2)).astype(np.float32),
                    k=(rng.randint(1, 3, (n, 2)) * rng.choice([-1, 1], (n, 2))).astype(np.int32), ph=rng.uniform(0, TWO_PI, (n, 2)).astype(np.float32),
                    sg=rng.uniform(0.16, 0.28, n).astype(np.float32), col=np.array([0.0, 0.12, 0.28, 0.42, 0.56, 0.72], np.float32)[rng.permutation(6)])
    if spec.style == "bokeh":
        n = 34
        return dict(x0=rng.uniform(0, 1, n).astype(np.float32), y0=rng.uniform(0, 1, n).astype(np.float32), r=rng.uniform(0.012, 0.075, n).astype(np.float32),
                    lap=rng.randint(1, 3, n).astype(np.int32), sw=rng.uniform(0.01, 0.05, n).astype(np.float32), swk=rng.randint(1, 3, n).astype(np.int32),
                    swp=rng.uniform(0, TWO_PI, n).astype(np.float32), al=rng.uniform(0.18, 0.7, n).astype(np.float32), col=rng.uniform(0.45, 1, n).astype(np.float32),
                    under=Waves(rng, 6, 0.6, 1.4, s, 1))
    raise ValueError(spec.style)


def _smooth(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def _draw(spec: BgSpec, p: _Plan, t: float) -> np.ndarray:
    tp = np.float32(TWO_PI * (t % spec.loop_seconds) / spec.loop_seconds)
    st, u, v, g = p.st, p.u, p.v, spec.intensity
    lut = p.lut
    if spec.style == "gas":
        u1 = u + 0.27 * st["wx"].eval(u, v, tp)
        v1 = v + 0.27 * st["wy"].eval(u, v, tp)
        u2 = u1 + 0.16 * st["w2x"].eval(u1, v1, tp)
        v2 = v1 + 0.16 * st["w2y"].eval(u1, v1, tp)
        f = 0.04 + 0.80 * _sig(st["fb"].eval(u2, v2, tp) - 0.15, 0.36 * g) ** 1.35
        return _ramp(lut, f)
    if spec.style == "smoke":
        ca, sa = math.cos(st["ang"]), math.sin(st["ang"])
        ur, vr = u * ca - v * sa, u * sa + v * ca
        ur = ur + 0.5 * st["wx"].eval(u, v, tp)
        vr = vr + 0.5 * st["wy"].eval(u, v, tp)
        z = st["fb"].eval(ur, vr, tp)
        f = _smooth(-0.6, 2.4 / max(g, 0.4), z) ** 2.0                  # sparse wisps
        return _ramp(lut, 0.05 + 0.75 * f)
    if spec.style == "lava":
        n = len(st["r"])
        field = np.zeros(u.shape, np.float32)
        for i in range(n):
            cu = (st["c"][i, 0] - 0.5 + 0.5 * st["a"][i, 0] * np.cos(st["k"][i, 0] * tp + st["ph"][i, 0])) * p.ex
            cv = (st["c"][i, 1] - 0.5 + 0.5 * st["a"][i, 1] * np.sin(st["k"][i, 1] * tp + st["ph"][i, 1])) * p.ey
            r = st["r"][i]
            field += (r * r) / ((u - cu) ** 2 + (v - cv) ** 2 + 0.0035)
        f = _sig(np.log1p(field) - 0.85, 2.2 * g) * (1.0 - 0.45 * p.qe)   # the middle stays in the darker part of the ramp (a clamp alone turns yellow into mud)
        return _ramp(lut, f)
    if spec.style == "aurora":
        n = len(st["y0"])
        inten = np.zeros(u.shape, np.float32)
        hue = np.zeros(u.shape, np.float32)
        wsum = np.zeros(u.shape, np.float32) + 1e-4
        x, y = p.x, p.y
        for i in range(n):
            yc = st["y0"][i] + st["a1"][i] * np.sin(st["f1"][i] * TWO_PI * u + st["p1"][i] + st["k1"][i] * tp) + st["a2"][i] * np.sin(st["f2"][i] * TWO_PI * u + st["p2"][i] + st["k2"][i] * tp)
            d = (y - yc) / st["wd"][i]
            vert = np.where(d < 0, np.exp(-(d * 0.55) ** 2), np.exp(-(d * 1.9) ** 2))   # soft fade above (d < 0), crisp lower edge
            rays = 0.62 + 0.38 * np.sin(st["fr"][i] * u + 2.2 * np.sin(2.3 * TWO_PI * u * 0.5 + st["pr"][i] + st["kr"][i] * tp) + st["pr"][i])
            li = (0.85 * vert * rays).astype(np.float32)
            inten = 1 - (1 - inten) * (1 - np.clip(li, 0, 1))
            hue += li * (st["hue"][i] + 0.18 * np.clip(-d, -1, 1) * 0.5)
            wsum += li
        hue = np.clip(hue / wsum, 0, 1)
        base = _ramp(lut, np.zeros_like(hue))                          # background colour (ramp start)
        col = _ramp(lut, 0.35 + 0.65 * hue)
        k = np.clip(inten * g, 0, 1)[..., None]
        return base * (1 - k) + col * k
    if spec.style == "mesh":
        nb = np.zeros(u.shape + (3,), np.float32)      # bright colours (the lively edges)
        nd = np.zeros(u.shape + (3,), np.float32)      # the same blobs in the dark half of the ramp (under the text)
        den = np.zeros(u.shape, np.float32) + 1e-4
        for i in range(len(st["sg"])):
            cu = (st["c"][i, 0] - 0.5 + 0.5 * st["a"][i, 0] * np.cos(st["k"][i, 0] * tp + st["ph"][i, 0])) * p.ex
            cv = (st["c"][i, 1] - 0.5 + 0.5 * st["a"][i, 1] * np.sin(st["k"][i, 1] * tp + st["ph"][i, 1])) * p.ey
            wgt = np.exp(-((u - cu) ** 2 + (v - cv) ** 2) / (2 * (st["sg"][i] ** 2 * 0.5)))
            pos = float(np.clip(st["col"][i], 0, 1))
            nb += wgt[..., None] * lut[int(pos * (LUT_N - 1))]
            nd += wgt[..., None] * lut[int(pos * 0.62 * (LUT_N - 1))]
            den += wgt
        qe = p.qe[..., None] if spec.mode == "dark" else 0.0 * p.qe[..., None]
        return (nd * qe + nb * (1.0 - qe)) / den[..., None]
    if spec.style == "bokeh":
        under = _sig(st["under"].eval(u, v, tp), 0.9 * g)
        out = _ramp(lut, 0.04 + 0.38 * under)
        ph = float(tp) / TWO_PI
        for i in range(len(st["r"])):
            cy = (st["y0"][i] - st["lap"][i] * ph) % 1.0                  # rises by `lap` frame heights per loop (wraps)
            cx = (st["x0"][i] + st["sw"][i] * math.sin(st["swk"][i] * float(tp) + float(st["swp"][i]))) % 1.0
            r = float(st["r"][i])                                         # in units of the frame height
            col = lut[int(np.clip(st["col"][i], 0, 1) * (LUT_N - 1))]
            for oy in (0.0, 1.0, -1.0):                                   # wrap copies, drawn only when they touch the frame
                yy = cy + oy
                if yy + r < 0 or yy - r > 1:
                    continue
                rx = r * (p.ih / p.iw) * (p.ey / p.ex) * (p.ex / p.ey) * (1.0)
                x0 = int(max(0, (cx - r * p.ey / p.ex) * p.iw - 1)); x1 = int(min(p.iw, (cx + r * p.ey / p.ex) * p.iw + 2))
                y0 = int(max(0, (yy - r) * p.ih - 1)); y1 = int(min(p.ih, (yy + r) * p.ih + 2))
                if x1 <= x0 or y1 <= y0:
                    continue
                dx = (p.x[y0:y1, x0:x1] - cx) * p.ex / p.ey              # to frame-height units
                dy = p.y[y0:y1, x0:x1] - yy
                d = np.sqrt(dx * dx + dy * dy) / r
                disc = _smooth(1.0, 0.72, d) * (0.55 + 0.45 * d)         # soft disc with a slightly brighter rim (bokeh)
                a = (st["al"][i] * 0.45 * g) * disc
                out[y0:y1, x0:x1] += a[..., None] * (col - out[y0:y1, x0:x1]) * 0.9
        return out
    raise ValueError(spec.style)


# ------------------------------------------------------------------ brightness limit in the quiet zone, dither, output
def _smin(x: np.ndarray, cap: np.ndarray, n: float = 3.0) -> np.ndarray:
    """A smooth minimum that never exceeds min(x, cap): squeezes bright values toward the cap instead of clipping them (clipping flattens shapes into plateaus)."""
    return (np.maximum(x, 1e-4) ** -n + np.maximum(cap, 1e-4) ** -n) ** (-1.0 / n)


def _limit(rgb: np.ndarray, p: _Plan, mode: str) -> np.ndarray:
    lum2 = np.sqrt(0.2126 * rgb[..., 0] ** 2 + 0.7152 * rgb[..., 1] ** 2 + 0.0722 * rgb[..., 2] ** 2) / 255.0
    if mode == "dark":
        k = _smin(lum2, p.cap) / np.maximum(lum2, 1e-4)
        return rgb * k[..., None]
    d = _smin(1.0 - lum2, p.cap)                                         # light mode: squeeze the darkness instead
    s = np.clip(((1.0 - d) - lum2) / np.maximum(1.0 - lum2, 1e-4), 0, 1)
    return rgb + (255.0 - rgb) * s[..., None]


_NOISE: Dict[int, np.ndarray] = {}


def _noise(w: int, h: int, frame_key: int) -> np.ndarray:
    """Triangular-PDF dither in (-1, 1), from one cached 2048x2048 tile read at a per-frame offset (the grain moves, never freezes)."""
    if 0 not in _NOISE:
        r = np.random.RandomState(12345)
        _NOISE[0] = (r.random_sample((2048, 2048)).astype(np.float32) + r.random_sample((2048, 2048)).astype(np.float32) - 1.0)
    tile = _NOISE[0]
    ox, oy = (frame_key * 97) % (2048 - 0 if w > 2048 else 2048 - w + 1), (frame_key * 61) % (2048 - 0 if h > 2048 else 2048 - h + 1)
    if w > 2048 or h > 2048:
        return np.tile(tile, (h // 2048 + 1, w // 2048 + 1))[:h, :w]
    return tile[oy:oy + h, ox:ox + w]


HALF_ABOVE_PIXELS = 2_500_000   # above this many pixels (1440p and up, i.e. 4K) the frame is computed at half size and enlarged: the picture has no fine detail to lose


def render(spec: BgSpec, w: int, h: int, t: float, dither: bool = True) -> np.ndarray:
    """One frame, (h, w, 3) uint8. Time is wrapped by the loop length, so the animation repeats seamlessly. 4K is computed at 1080p and enlarged (bilinear), dither included."""
    if w * h > HALF_ABOVE_PIXELS:
        small = render(spec, (w + 1) // 2, (h + 1) // 2, t, dither)
        return np.asarray(Image.fromarray(small, "RGB").resize((w, h), Image.BILINEAR))
    p = _plan(spec, w, h)
    small = _limit(_draw(spec, p, t), p, spec.mode)
    out = np.empty((h, w, 3), np.float32)
    for c in range(3):
        ch = Image.fromarray(np.ascontiguousarray(small[..., c], dtype=np.float32), "F").resize((w, h), Image.BICUBIC)
        out[..., c] = np.asarray(ch)
    if dither:
        out += _noise(w, h, int(round(t * 30)))[..., None] + 0.5
    else:
        out += 0.5
    np.clip(out, 0, 255, out=out)
    return out.astype(np.uint8)


def render_image(spec: BgSpec, w: int, h: int, t: float) -> Image.Image:
    return Image.fromarray(render(spec, w, h, t), "RGB")


# ------------------------------------------------------------------ measurement
def contrast_report(spec: BgSpec, w: int = 960, h: int = 540, times: Iterable[float] = (0, 2.5, 5, 7.5)) -> Dict[str, float]:
    """Worst text contrast over sample frames: inside the quiet zone and over the whole frame (text colour by mode)."""
    text = DARK_TEXT if spec.mode == "dark" else LIGHT_TEXT
    p = _plan(spec, w, h)
    zone_min, all_min = 99.0, 99.0
    ys, xs = np.mgrid[0:h, 0:w]
    qz = _zone(_quiet_mask((xs + 0.5) / w, (ys + 0.5) / h, h > w), spec.quiet) >= 0.999
    for t in times:
        fr = render(spec, w, h, t, dither=False).astype(np.float32)
        lin = np.where(fr / 255 <= 0.03928, fr / 255 / 12.92, ((fr / 255 + 0.055) / 1.055) ** 2.4)
        Y = 0.2126 * lin[..., 0] + 0.7152 * lin[..., 1] + 0.0722 * lin[..., 2]
        Lt = _lum(text)
        c = (np.maximum(Y, Lt) + 0.05) / (np.minimum(Y, Lt) + 0.05)
        all_min = min(all_min, float(c.min()))
        if qz.any():
            zone_min = min(zone_min, float(c[qz].min()))
    return dict(zone_min=round(zone_min, 2), frame_min=round(all_min, 2))


def seam_error(spec: BgSpec, w: int = 640, h: int = 360) -> Dict[str, float]:
    """Mean absolute difference (0..255) between frame 0 and frame T (the loop seam) versus between neighbouring frames (30 fps)."""
    a = render(spec, w, h, 0.0, dither=False).astype(np.float32)
    b = render(spec, w, h, spec.loop_seconds, dither=False).astype(np.float32)
    c = render(spec, w, h, 1 / 30, dither=False).astype(np.float32)
    return dict(seam=round(float(np.abs(a - b).mean()), 4), neighbour=round(float(np.abs(a - c).mean()), 4))
