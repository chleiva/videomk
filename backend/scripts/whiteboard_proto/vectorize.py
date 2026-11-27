"""Vector drawing packages. Everything the board shows is vector geometry, rasterised by resvg AT THE SIZE IT IS SHOWN (1080p, 4K, any zoom).

A package is a dict:
  w, h      the drawing's own units (the pixels of the generated sheet)
  ink       SVG fragment of the visible line art, in those units, fill="#000"
  fills     list of SVG fragments: the areas enclosed by the line (colour goes there, so a fill can never miss its shape)
  strokes   the ordered centre-line pen path (list of (n,2) arrays): hidden reveal path for method A, the art itself for method B
  width     marker width in units

  build_outline(alpha)   method A: the image model's art traced to FILLED outlines with vtracer (the repo's image-to-vector tool, MIT)
  build_strokes(alpha)   method B: the centre line fitted with smoothing cubic splines (corners kept), drawn as round-capped strokes with a slight pressure profile
  from_strokes(...)      a package from pen strokes written by code or by a language model (method C, arrows, underlines)
  raster(pkg, scale)     -> ink alpha, fill alphas, reveal time map and pen path at `scale` pixels per unit
"""
import io
import math
import os
import re
import tempfile
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from PIL import Image
from scipy import interpolate, ndimage

import trace as tr

Pkg = Dict[str, Any]


# ----------------------------------------------------------------------------- vtracer: raster mask -> filled vector outlines
def mask_to_svg(mask_or_alpha: np.ndarray, up: int = 4, speckle: int = 8) -> str:
    """A soft 0..1 ink image -> SVG path elements in the image's own units. The image is enlarged first so the tracer sees the anti-aliased edge
    with sub-pixel precision; the curves it fits are then scaled back, so nothing of the pixel grid survives."""
    import vtracer

    a = np.clip(mask_or_alpha.astype(np.float32), 0, 1)
    im = Image.fromarray((a * 255).astype(np.uint8)).resize((a.shape[1] * up, a.shape[0] * up), Image.LANCZOS)
    im = im.point(lambda v: 0 if v >= 128 else 255)       # black shape on white for the binary tracer
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, "a.png"), os.path.join(d, "a.svg")
        im.convert("RGB").save(src)
        vtracer.convert_image_to_svg_py(src, dst, colormode="binary", mode="spline", filter_speckle=speckle, corner_threshold=70, length_threshold=5.0,
                                        max_iterations=10, splice_threshold=45, path_precision=2)
        svg = open(dst).read()
    paths = re.findall(r"<path[^>]*/>", svg)
    return f'<g transform="scale({1.0 / up:.6f})">' + "".join(paths) + "</g>"


def _fills(alpha: np.ndarray) -> List[str]:
    return [mask_to_svg(m.astype(np.float32), up=2, speckle=16) for m in tr.enclosed_regions(alpha)]


def _fill_boxes(alpha: np.ndarray) -> List[List[float]]:
    out = []
    for m in tr.enclosed_regions(alpha):
        ys, xs = np.nonzero(m)
        out.append([float(xs.min()), float(ys.min()), float(xs.max()), float(ys.max()), float(m.sum())])
    return out


def build_outline(alpha: np.ndarray, strategy: str = "human") -> Pkg:
    t = tr.trace(alpha, strategy)
    return {"w": alpha.shape[1], "h": alpha.shape[0], "ink": mask_to_svg(alpha), "fills": _fills(alpha), "fill_boxes": _fill_boxes(alpha),
            "strokes": [smooth_stroke(s, t["width"]) for s in t["strokes"]], "width": t["width"], "method": "A"}


# ----------------------------------------------------------------------------- smooth strokes
def _resample(p: np.ndarray, step: float) -> np.ndarray:
    d = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(p, axis=0).T))])
    if d[-1] < step:
        return p
    u = np.linspace(0, d[-1], max(2, int(d[-1] / step) + 1))
    return np.stack([np.interp(u, d, p[:, 0]), np.interp(u, d, p[:, 1])], 1)


def _corners(p: np.ndarray, k: int, min_deg: float = 48.0) -> List[int]:
    n = len(p)
    if n < 2 * k + 3:
        return []
    a = p[k:-k] - p[:-2 * k]
    b = p[2 * k:] - p[k:-k]
    cos = (a * b).sum(1) / (np.hypot(*a.T) * np.hypot(*b.T) + 1e-9)
    ang = np.degrees(np.arccos(np.clip(cos, -1, 1)))
    out = []
    i = 0
    while i < len(ang):
        if ang[i] >= min_deg:
            j = i
            while j + 1 < len(ang) and ang[j + 1] >= min_deg:
                j += 1
            out.append(int(i + np.argmax(ang[i:j + 1])) + k)
            i = j + 1
        else:
            i += 1
    return out


def _spline(p: np.ndarray, tol: float, step: float, closed: bool = False) -> np.ndarray:
    if len(p) < 5:
        return p
    try:
        q = p[:-1] if closed else p
        tck, _ = interpolate.splprep([q[:, 0], q[:, 1]], k=3, s=len(q) * tol * tol, per=1 if closed else 0)
        L = tr.length_of(p)
        x, y = interpolate.splev(np.linspace(0, 1, max(4, int(L / step) + 1)), tck)
        out = np.stack([x, y], 1)
        if not closed:
            out[0], out[-1] = p[0], p[-1]
        return out
    except Exception:
        return p


def smooth_stroke(p: np.ndarray, width: float, tol: Optional[float] = None) -> np.ndarray:
    """A traced pixel path -> a smooth curve: cubic smoothing splines between corners (a mountain peak stays a peak). Sampled densely; the result is a
    piecewise cubic, i.e. Bezier, curve."""
    tol = 0.06 * width if tol is None else tol
    step = max(1.0, width * 0.12)
    closed = len(p) > 8 and float(np.hypot(*(p[0] - p[-1]))) < 3.0
    q = _resample(p.astype(np.float64), 2.0)
    k = max(3, int(width * 0.45))
    cs = _corners(q, k)
    if closed and not cs:
        return _spline(q, tol, step, closed=True).astype(np.float32)
    cuts = [0] + [c for c in cs if k < c < len(q) - 1 - k] + [len(q) - 1]
    parts = []
    for a, b in zip(cuts, cuts[1:]):
        s = _spline(q[a:b + 1], tol, step)
        parts.append(s if not parts else s[1:])
    return np.concatenate(parts).astype(np.float32)


def _noise(n: int, seed: int, period: float) -> np.ndarray:
    """Smooth, slow, deterministic variation in -1..1 along a stroke (pressure, wobble)."""
    r = np.random.default_rng(seed)
    x = np.arange(n) / max(period, 1.0)
    out = np.zeros(n)
    for f, a in ((1.0, 0.6), (2.3, 0.3), (4.1, 0.1)):
        out += a * np.sin(2 * math.pi * (f * x + r.random()))
    return out


def stroke_polygon(p: np.ndarray, width: float, seed: int = 0, pressure: float = 0.07, taper: float = 0.2) -> str:
    """A pen stroke as SVG: a chain of short round-capped segments whose width breathes slowly by `pressure` and is slightly lighter where the pen lands and
    lifts. (A union of round segments has no folds at tight corners, which a single offset outline has.)"""
    p = _resample(p.astype(np.float64), max(1.0, width * 0.22))
    n = len(p)
    if n < 2:
        return f'<circle cx="{p[0][0]:.2f}" cy="{p[0][1]:.2f}" r="{width / 2:.2f}" fill="#000"/>'
    d = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(p, axis=0).T))])
    closed = n > 8 and float(np.hypot(*(p[0] - p[-1]))) < 0.5
    w = width * (1.0 + pressure * _noise(n, seed, period=max(8.0, 9.0 * width / (d[-1] / n + 1e-9))))
    if not closed and taper > 0:
        e = np.minimum(d, d[-1] - d) / (1.6 * width)
        w *= (1 - taper) + taper * np.clip(e, 0, 1) ** 0.7
    wq = np.round(w / (width * 0.02)) * (width * 0.02)        # a few width steps, so runs of equal width share one path
    out, i = [], 0
    while i < n - 1:
        j = i + 1
        while j < n - 1 and wq[j] == wq[i]:
            j += 1
        pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in p[i:j + 1])
        out.append(f'<polyline points="{pts}" stroke-width="{wq[i]:.2f}"/>')
        i = j
    return '<g fill="none" stroke="#000" stroke-linecap="round" stroke-linejoin="round">' + "".join(out) + "</g>"


def from_strokes(strokes: Sequence[np.ndarray], width: float, w: float, h: float, seed: int = 0, fills: bool = False, pressure: float = 0.07) -> Pkg:
    ink = "".join(stroke_polygon(s, width, seed + 7 * i, pressure) for i, s in enumerate(strokes))
    pkg = {"w": w, "h": h, "ink": ink, "fills": [], "fill_boxes": [], "strokes": [np.asarray(s, np.float32) for s in strokes], "width": width, "method": "B"}
    if fills:
        a = svg_alpha(pkg["ink"], w, h, 1.0)
        pkg["fills"], pkg["fill_boxes"] = _fills(a), _fill_boxes(a)
    return pkg


def build_strokes(alpha: np.ndarray, strategy: str = "human", draw_width: Optional[float] = None) -> Pkg:
    """`draw_width`: the marker width to draw with, in drawing units (default: the width measured on the art)."""
    t = tr.trace(alpha, strategy)
    strokes = [smooth_stroke(s, t["width"]) for s in t["strokes"]]
    return from_strokes(strokes, draw_width or t["width"], alpha.shape[1], alpha.shape[0], fills=True)


# ----------------------------------------------------------------------------- rasterising at the size shown
def svg_alpha(fragment: str, w: float, h: float, scale: float) -> np.ndarray:
    import resvg_py

    W, H = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {w} {h}">{fragment}</svg>'
    png = resvg_py.svg_to_bytes(svg_string=svg, width=W, height=H)
    return np.asarray(Image.open(io.BytesIO(bytes(png))).convert("RGBA"), np.float32)[..., 3] / 255.0


def raster(pkg: Pkg, scale: float, line_px: Optional[float] = None) -> Dict[str, Any]:
    """Rasterise a package at `scale` pixels per unit. `line_px`: the marker width wanted on screen, in raster pixels. Drawings are shown at different sizes, so
    their lines would differ in weight; the outline is grown or shrunk (a vector offset: an SVG stroke added to, or cut from, the filled shape) so that every
    drawing on a board has the same line weight."""
    ink = pkg["ink"]
    alpha = svg_alpha(ink, pkg["w"], pkg["h"], scale)
    if line_px is not None and pkg.get("method") == "A":
        delta = (line_px / scale) - pkg["width"]                  # in drawing units, total change of width
        delta = float(np.clip(delta, -0.45 * pkg["width"], 0.8 * pkg["width"]))
        if abs(delta) > 0.03 * pkg["width"]:
            # the vtracer group is scaled by 1/4: stroke widths inside it are in enlarged units
            up = 4.0
            both = ink.replace("<path ", f'<path stroke="#000" stroke-width="{abs(delta) * up:.3f}" stroke-linejoin="round" ')
            grown = svg_alpha(both, pkg["w"], pkg["h"], scale)
            if delta > 0:
                alpha = grown
            else:
                only = ink.replace("<path ", f'<path fill-opacity="0" stroke="#000" stroke-width="{abs(delta) * up:.3f}" stroke-linejoin="round" ').replace('fill="#000000"', 'fill="none"')
                alpha = np.clip(alpha - svg_alpha(only, pkg["w"], pkg["h"], scale), 0, 1)
    strokes = [s * scale for s in pkg["strokes"]]
    lw = line_px if (line_px is not None and pkg.get("method") == "A") else pkg["width"] * scale
    T, times, total = tr.time_map(alpha, strokes, lw * 0.55, pace=float(pkg.get("pace", 0.0)))
    fills = [svg_alpha(f, pkg["w"], pkg["h"], scale) for f in pkg["fills"]]
    return {"alpha": alpha, "T": T, "fills": fills, "strokes": strokes, "times": times, "pen_len": total / scale}


# ----------------------------------------------------------------------------- handwriting
def text_pkg(text: str, font_path: str, size: float = 200.0, method: str = "A") -> Pkg:
    """A short label. Method A: the font's own outlines (rasterised from the font at the size shown), revealed along each letter's centre line, letters left to right.
    Method B: the letters' centre lines drawn as marker strokes (a single-line hand)."""
    from PIL import ImageDraw, ImageFont

    font = ImageFont.truetype(font_path, int(size))
    asc, desc = font.getmetrics()
    pad = int(size * 0.2)
    W, H = int(font.getlength(text)) + 2 * pad, asc + desc + 2 * pad
    strokes: List[np.ndarray] = []
    widths = []
    for i, ch in enumerate(text):
        if ch.isspace():
            continue
        x = pad + font.getlength(text[:i])
        im = Image.new("L", (W, H), 0)
        ImageDraw.Draw(im).text((x, pad), ch, font=font, fill=255)
        a = np.asarray(im, np.float32) / 255.0
        bx = np.nonzero(a.max(0) > 0.1)[0]
        if not len(bx):
            continue
        x0, x1 = max(0, bx[0] - 4), min(W, bx[-1] + 5)
        t = tr.trace(a[:, x0:x1], "human")
        widths.append(t["width"])
        ss = t["strokes"]
        for s in ss:
            strokes.append(smooth_stroke(s, t["width"]) + np.array([x0, 0], np.float32))
    width = float(np.median(widths)) if widths else size * 0.08
    if method == "B":
        return from_strokes(strokes, width, W, H, seed=len(text))
    return {"w": W, "h": H, "ink": None, "text": (text, font_path, size, pad), "fills": [], "fill_boxes": [], "strokes": strokes, "width": width, "method": "A"}


def raster_text(pkg: Pkg, scale: float, line_px: Optional[float] = None) -> Dict[str, Any]:
    """`line_px`: wanted pen width in raster pixels; the font's outline is thickened to it (never thinned), so labels match the drawings' marker."""
    from PIL import ImageDraw, ImageFont

    if pkg.get("ink"):
        return raster(pkg, scale)
    grow = int(round(max(0.0, (line_px or 0) - pkg["width"] * scale) / 2))
    text, font_path, size, pad = pkg["text"]
    W, H = int(round(pkg["w"] * scale)), int(round(pkg["h"] * scale))
    font = ImageFont.truetype(font_path, size * scale)
    im = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(im)
    base = ImageFont.truetype(font_path, int(size))
    for i, ch in enumerate(text):          # letters at the same advances the centre lines were traced at
        if not ch.isspace():
            d.text(((pad + base.getlength(text[:i])) * scale - grow, pad * scale - grow), ch, font=font, fill=255, stroke_width=grow, stroke_fill=255)
    alpha = np.asarray(im, np.float32) / 255.0
    strokes = [s * scale for s in pkg["strokes"]]
    T, times, total = tr.time_map(alpha, strokes, max(pkg["width"] * scale, line_px or 0) * 0.6)
    return {"alpha": alpha, "T": T, "fills": [], "strokes": strokes, "times": times, "pen_len": total / scale}
