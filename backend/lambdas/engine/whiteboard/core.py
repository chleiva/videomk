"""Strokes, vector rasterising and the reveal map. NumPy, Pillow and resvg only."""
import io
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw

Pkg = Dict[str, Any]
NEVER = 2.0          # reveal-map value of a pixel the pen never passes


def length_of(p: np.ndarray) -> float:
    d = np.diff(np.asarray(p, np.float64), axis=0)
    return float(np.hypot(d[:, 0], d[:, 1]).sum()) if len(d) else 0.0


def resample(p: np.ndarray, step: float) -> np.ndarray:
    p = np.asarray(p, np.float64)
    if len(p) < 2:
        return p
    d = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(p, axis=0).T))])
    if d[-1] < step:
        return p
    u = np.linspace(0, d[-1], max(2, int(d[-1] / step) + 1))
    return np.stack([np.interp(u, d, p[:, 0]), np.interp(u, d, p[:, 1])], 1)


def noise(n: int, seed: int, period: float) -> np.ndarray:
    """Smooth, slow, deterministic variation in -1..1 along a stroke."""
    r = np.random.default_rng(seed)
    x = np.arange(n) / max(period, 1.0)
    out = np.zeros(n)
    for f, a in ((1.0, 0.6), (2.3, 0.3), (4.1, 0.1)):
        out += a * np.sin(2 * math.pi * (f * x + r.random()))
    return out


def stroke_svg(p: np.ndarray, width: float, seed: int = 0, pressure: float = 0.07, taper: float = 0.2) -> str:
    """A pen stroke as SVG: a chain of short round-capped pieces whose width breathes slowly and is lighter where the pen lands and lifts."""
    p = resample(np.asarray(p, np.float64), max(1.0, width * 0.22))
    n = len(p)
    if n < 2:
        return f'<circle cx="{p[0][0]:.2f}" cy="{p[0][1]:.2f}" r="{width / 2:.2f}" fill="#000"/>'
    d = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(p, axis=0).T))])
    closed = n > 8 and float(np.hypot(*(p[0] - p[-1]))) < 0.5
    w = width * (1.0 + pressure * noise(n, seed, period=max(8.0, 9.0 * width / (d[-1] / n + 1e-9))))
    if not closed and taper > 0:
        e = np.minimum(d, d[-1] - d) / (1.6 * width)
        w *= (1 - taper) + taper * np.clip(e, 0, 1) ** 0.7
    wq = np.round(w / (width * 0.02)) * (width * 0.02)
    out, i = [], 0
    while i < n - 1:
        j = i + 1
        while j < n - 1 and wq[j] == wq[i]:
            j += 1
        pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in p[i:j + 1])
        out.append(f'<polyline points="{pts}" stroke-width="{wq[i]:.2f}"/>')
        i = j
    return '<g fill="none" stroke="#000" stroke-linecap="round" stroke-linejoin="round">' + "".join(out) + "</g>"


def svg_alpha(fragment: str, w: float, h: float, scale: float) -> np.ndarray:
    import resvg_py

    W, H = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {w} {h}">{fragment}</svg>'
    png = resvg_py.svg_to_bytes(svg_string=svg, width=W, height=H)
    return np.asarray(Image.open(io.BytesIO(bytes(png))).convert("RGBA"), np.float32)[..., 3] / 255.0


def stroke_times(strokes: Sequence[np.ndarray], travel_speed: float = 3.0, pace: float = 0.0, ref: float = 20.0) -> Tuple[List[np.ndarray], float]:
    """Pen time at each point of each stroke (pen-length units), and the total. Pen-up travel is `travel_speed` times faster; `pace` slows the pen through bends."""
    t, out, prev = 0.0, [], None
    for p in strokes:
        p = np.asarray(p, np.float64)
        if prev is not None:
            t += float(np.hypot(*(p[0] - prev))) / travel_speed
        seg = np.diff(p, axis=0)
        ds = np.hypot(seg[:, 0], seg[:, 1]) if len(seg) else np.zeros(0)
        if pace > 0 and len(p) > 3:
            ang = np.unwrap(np.arctan2(seg[:, 1], seg[:, 0]))
            turn = np.abs(np.diff(ang, prepend=ang[0]))
            k = np.minimum(turn / np.maximum(ds, 1e-6) * ref, 2.0)
            k = np.convolve(np.pad(k, 2, mode="edge"), np.ones(5) / 5, "valid")
            ds = ds * (1.0 + pace * k)
        d = np.concatenate([[0.0], np.cumsum(ds)])
        out.append(t + d)
        t += float(d[-1])
        prev = p[-1]
    return out, max(t, 1e-6)


def reveal_map(alpha: np.ndarray, strokes: Sequence[np.ndarray], width: float, pace: float = 0.0) -> Tuple[np.ndarray, List[np.ndarray], float]:
    """WHEN the pen uncovers each pixel of a drawing: -> (T in 0..1, NEVER where there is no ink; per-stroke point times 0..1; pen length).
    The pen path is painted with a round tip `width` pixels wide, the LAST stroke first, each short piece carrying its time as its colour: where strokes overlap
    the earliest pass stays on top. Plain Pillow drawing, so it costs milliseconds at any size (no distance transform)."""
    H, W = alpha.shape
    strokes = [np.asarray(s, np.float64) for s in strokes if len(s) >= 1]
    times, total = stroke_times(strokes, pace=pace, ref=max(width, 2.0) * 2.5)
    Q = 60000
    im = Image.new("I", (W, H), 2 * Q)
    dr = ImageDraw.Draw(im)
    wd = max(2, int(round(width)))
    r = wd / 2.0
    step = max(1.5, width * 0.3)
    for p, tt in zip(reversed(strokes), reversed(times)):
        if len(p) == 1:
            p, tt = np.concatenate([p, p + 0.5]), np.array([tt[0], tt[0]])
        d = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(p, axis=0).T))])
        n = max(2, int(d[-1] / step) + 1)
        u = np.linspace(0, d[-1], n)
        xs, ys, tv = np.interp(u, d, p[:, 0]), np.interp(u, d, p[:, 1]), np.interp(u, d, tt) / total
        for i in range(n - 1, 0, -1):
            v = int(tv[i - 1] * Q)
            dr.line([(xs[i - 1], ys[i - 1]), (xs[i], ys[i])], fill=v, width=wd)
            dr.ellipse([xs[i - 1] - r, ys[i - 1] - r, xs[i - 1] + r, ys[i - 1] + r], fill=v)
    T = np.asarray(im, np.float32) / Q
    ink = alpha >= 0.02
    T[(T > 1.5) & ink] = 1.0            # ink the path missed appears as the drawing is finished, never stays hidden
    T[~ink] = NEVER
    return T, [tt / total for tt in times], total


def raster_package(pkg: Pkg, scale: float, line_px: Optional[float] = None) -> Dict[str, Any]:
    """A library drawing at `scale` pixels per unit. `line_px`: the marker width wanted on screen; the outline is grown or thinned to it with a vector offset
    (an SVG stroke added to, or cut from, the filled shape), so every drawing on a board has the same line weight."""
    ink = pkg["ink"]
    alpha = svg_alpha(ink, pkg["w"], pkg["h"], scale)
    lw = pkg["width"] * scale
    if line_px is not None and "<path " in ink:
        delta = float(np.clip((line_px / scale) - pkg["width"], -0.45 * pkg["width"], 0.8 * pkg["width"]))
        if abs(delta) > 0.03 * pkg["width"]:
            up = 4.0          # the traced paths sit in a group scaled by 1/4
            if delta > 0:
                alpha = svg_alpha(ink.replace("<path ", f'<path stroke="#000" stroke-width="{delta * up:.3f}" stroke-linejoin="round" '), pkg["w"], pkg["h"], scale)
            else:
                only = ink.replace("<path ", f'<path stroke="#000" stroke-width="{-delta * up:.3f}" stroke-linejoin="round" ').replace('fill="#000000"', 'fill="none"')
                alpha = np.clip(alpha - svg_alpha(only, pkg["w"], pkg["h"], scale), 0, 1)
            lw = line_px
    strokes = [np.asarray(s, np.float64) * scale for s in pkg["strokes"]]
    T, times, total = reveal_map(alpha, strokes, lw * 1.6, pace=float(pkg.get("pace", 0.0)))
    fills = [svg_alpha(f, pkg["w"], pkg["h"], scale) for f in pkg.get("fills", [])]
    return {"alpha": alpha, "T": T, "fills": fills, "strokes": strokes, "times": times, "pen_len": total / scale}


def stroke_package(strokes: Sequence[np.ndarray], width: float, seed: int = 0, pressure: float = 0.08) -> Pkg:
    """Pen strokes in board units -> a package in its own box, plus where it goes ("x", "y")."""
    allp = np.concatenate([np.asarray(s, np.float64) for s in strokes])
    m = width * 2
    x0, y0 = float(allp[:, 0].min() - m), float(allp[:, 1].min() - m)
    w, h = float(allp[:, 0].max() + m - x0), float(allp[:, 1].max() + m - y0)
    local = [np.asarray(s, np.float64) - np.array([x0, y0]) for s in strokes]
    return {"w": w, "h": h, "ink": "".join(stroke_svg(s, width, seed + 7 * i, pressure) for i, s in enumerate(local)), "fills": [], "strokes": local, "width": width, "x": x0, "y": y0}


def raster_strokes(pkg: Pkg, scale: float) -> Dict[str, Any]:
    alpha = svg_alpha(pkg["ink"], pkg["w"], pkg["h"], scale)
    strokes = [s * scale for s in pkg["strokes"]]
    T, times, total = reveal_map(alpha, strokes, pkg["width"] * scale * 1.35, pace=float(pkg.get("pace", 0.0)))
    return {"alpha": alpha, "T": T, "fills": [], "strokes": strokes, "times": times, "pen_len": total / scale}
