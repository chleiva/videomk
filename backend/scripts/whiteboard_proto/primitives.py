"""Connectors drawn by code, in the same hand as the drawings: arrows, wavy rising arrows, underlines, dashes, loops, rain, drops.

Every function returns pen strokes in BOARD units, in drawing order; package() turns them into a vector drawing package (vectorize.from_strokes) placed at (x, y).
The hand: a slow sideways drift of a fraction of the marker width (low frequency, never a tremble) and ends that do not land exactly on the ruler.
"""
import math
from typing import List, Sequence, Tuple

import numpy as np

import vectorize as vz

Pt = Tuple[float, float]


def _curve(pts: Sequence[Pt], step: float = 6.0) -> np.ndarray:
    """Catmull-Rom through the points."""
    p = np.asarray(pts, np.float64)
    if len(p) == 2:
        n = max(2, int(np.hypot(*(p[1] - p[0])) / step))
        return p[0] + (p[1] - p[0]) * np.linspace(0, 1, n)[:, None]
    q = np.concatenate([p[:1], p, p[-1:]])
    out = []
    for i in range(1, len(q) - 2):
        p0, p1, p2, p3 = q[i - 1], q[i], q[i + 1], q[i + 2]
        n = max(4, int(np.hypot(*(p2 - p1)) / step))
        t = np.linspace(0, 1, n, endpoint=False)[:, None]
        out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t ** 2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t ** 3))
    return np.concatenate(out + [p[-1:]])


def wobble(p: np.ndarray, seed: int, amp: float = 3.5) -> np.ndarray:
    """The hand: a slow drift across the line (period of several hundred units), strongest mid-stroke."""
    if len(p) < 4:
        return p
    d = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(p, axis=0).T))])
    t = np.gradient(p, axis=0)
    t /= (np.hypot(*t.T)[:, None] + 1e-9)
    n = np.stack([-t[:, 1], t[:, 0]], 1)
    r = np.random.default_rng(seed)
    off = np.zeros(len(p))
    for period, a in ((520.0, 0.65), (230.0, 0.35)):
        off += a * np.sin(2 * math.pi * (d / period + r.random()))
    env = np.clip(np.minimum(d, d[-1] - d) / 60.0, 0, 1)
    return p + n * (off * amp * env)[:, None]


def line(a: Pt, b: Pt, seed: int = 0, amp: float = 3.5) -> np.ndarray:
    return wobble(_curve([a, b]), seed, amp)


def path(pts: Sequence[Pt], seed: int = 0, amp: float = 3.5) -> np.ndarray:
    return wobble(_curve(pts), seed, amp)


def head(p: np.ndarray, size: float = 46.0, spread: float = 27.0, seed: int = 0) -> np.ndarray:
    """An arrow head as ONE stroke: barb, tip, barb (the pen does not lift)."""
    tip = p[-1]
    back = p[max(0, len(p) - 6)]
    a = math.atan2(tip[1] - back[1], tip[0] - back[0])
    r = np.random.default_rng(seed)
    s1, s2 = math.radians(spread + r.uniform(-4, 4)), math.radians(spread + r.uniform(-4, 4))
    b1 = (tip[0] - size * math.cos(a - s1), tip[1] - size * math.sin(a - s1))
    b2 = (tip[0] - size * 0.95 * math.cos(a + s2), tip[1] - size * 0.95 * math.sin(a + s2))
    return np.array([b1, tuple(tip), b2], np.float64)


def arrow(pts: Sequence[Pt], seed: int = 0, size: float = 46.0) -> List[np.ndarray]:
    shaft = path(pts, seed)
    return [shaft, head(shaft, size, seed=seed + 1)]


def wavy_arrow(a: Pt, b: Pt, waves: float = 2.5, amp: float = 22.0, seed: int = 0, size: float = 42.0) -> List[np.ndarray]:
    """Rising vapour: a wavy shaft that straightens before the head."""
    a, b = np.asarray(a, np.float64), np.asarray(b, np.float64)
    L = float(np.hypot(*(b - a)))
    n = max(8, int(L / 5))
    u = np.linspace(0, 1, n)
    d = (b - a) / L
    nrm = np.array([-d[1], d[0]])
    env = np.clip((1 - u) / 0.22, 0, 1) * np.clip(u / 0.08, 0, 1)
    p = a + (b - a) * u[:, None] + nrm * (np.sin(2 * math.pi * waves * u) * amp * env)[:, None]
    p = wobble(p, seed, 2.0)
    return [p, head(p, size, seed=seed + 1)]


def underline(x: float, y: float, w: float, seed: int = 0) -> List[np.ndarray]:
    r = np.random.default_rng(seed)
    return [path([(x, y + r.uniform(-3, 3)), (x + w * 0.5, y + r.uniform(2, 7)), (x + w, y + r.uniform(-6, 0))], seed, 2.5)]


def dashes(a: Pt, b: Pt, n: int = 4, gap: float = 0.42, seed: int = 0) -> List[np.ndarray]:
    a, b = np.asarray(a, np.float64), np.asarray(b, np.float64)
    r = np.random.default_rng(seed)
    out = []
    for i in range(n):
        u0 = i / n + r.uniform(0, 0.02)
        u1 = u0 + (1 - gap) / n
        out.append(line(tuple(a + (b - a) * u0), tuple(a + (b - a) * u1), seed + i, 1.5))
    return out


def loop_arrows(cx: float, cy: float, rx: float, ry: float, seed: int = 0, size: float = 54.0) -> List[np.ndarray]:
    """Two curved arrows chasing each other round an ellipse, clockwise: the 'cycle' sign."""
    out = []
    for k, (a0, a1) in enumerate(((200, 345), (20, 165))):
        ang = np.radians(np.linspace(a0, a1, 70))
        r = np.random.default_rng(seed + k)
        p = np.stack([cx + rx * (1 + r.uniform(-0.015, 0.015)) * np.cos(ang), cy + ry * np.sin(ang)], 1)
        p = wobble(p, seed + 3 * k, 4.0)
        out += [p, head(p, size, seed=seed + k)]
    return out


def drop(cx: float, cy: float, h: float = 44.0) -> np.ndarray:
    """A small water drop, one closed stroke from the tip, clockwise."""
    t = np.linspace(0, 2 * math.pi, 28)
    w = h * 0.36
    x = cx + w * np.sin(t) * (0.55 + 0.45 * (1 - np.cos(t)) / 2) * 1.25
    y = cy - h / 2 + h * (1 - np.cos(t)) / 2
    return np.stack([x, y], 1)


def rain(x0: float, x1: float, y0: float, y1: float, n: int = 7, slant: float = 0.28, seed: int = 0) -> List[np.ndarray]:
    """Short slanted strokes in two staggered rows, left to right."""
    r = np.random.default_rng(seed)
    out = []
    L = (y1 - y0) * 0.36
    for row in range(2):
        m = n // 2 + (1 - row) * (n % 2)
        for i in range(m):
            x = x0 + (x1 - x0) * (i + 0.5 * row + 0.25) / (n / 2 + 0.5) + r.uniform(-8, 8)
            y = y0 + row * (y1 - y0) * 0.52 + r.uniform(-8, 8)
            out.append(line((x, y), (x - slant * L, y + L), seed + 10 * row + i, 1.0))
    return out


def package(strokes: Sequence[np.ndarray], width: float, seed: int = 0, pressure: float = 0.08):
    """Strokes in board units -> a package in its own box plus where to place it ("x", "y" in board units)."""
    allp = np.concatenate(strokes)
    m = width * 2
    x0, y0 = float(allp[:, 0].min() - m), float(allp[:, 1].min() - m)
    w, h = float(allp[:, 0].max() + m - x0), float(allp[:, 1].max() + m - y0)
    pkg = vz.from_strokes([np.asarray(s, np.float64) - np.array([x0, y0]) for s in strokes], width, w, h, seed=seed, pressure=pressure)
    pkg["x"], pkg["y"] = x0, y0
    return pkg
