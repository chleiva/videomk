"""The board and its renderer: a frame is a PURE FUNCTION OF TIME (so a video can be rendered in chunks, in any order, on any machine).

The board is bigger than the screen and is held as a few arrays at `scale` raster pixels per board unit:
  ink  : colour, coverage and, per pixel, the TIME the pen uncovers it (seconds; inf = never)
  fill : the same for the colour that arrives after the outline
A frame at time t shows ink where time <= t, through a camera window (x0, y0, width in board units), reduced to the output size. Nothing is accumulated between frames.
Board units are 1/3840 of the board's width, whatever the output resolution: 1080p and 4K are the same vectors rasterised at a different `scale`.
"""
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

INK = (26, 26, 30)
BLUE = (33, 118, 199)
RED = (222, 74, 52)
ORANGE = (240, 150, 30)
GREEN = (52, 150, 80)
FILL_YELLOW = (255, 216, 77)
FILL_BLUE = (158, 208, 245)
FILL_GREEN = (150, 212, 130)
FILL_BROWN = (214, 178, 140)
FILL_GREY = (226, 230, 236)
PAPER = (251, 249, 244)
SOFT = 0.035      # seconds over which the growing end of a line fades in (anti-aliases the reveal in time)


def ease(u: float) -> float:
    u = min(1.0, max(0.0, u))
    return u * u * u * (u * (6 * u - 15) + 10)


class Board:
    def __init__(self, W: int = 3840, H: int = 2160, scale: float = 1.0, seed: int = 7):
        self.W, self.H, self.s = W, H, scale
        self.RW, self.RH = int(round(W * scale)), int(round(H * scale))
        self.ink_rgb = np.zeros((self.RH, self.RW, 3), np.uint8)
        self.ink_a = np.zeros((self.RH, self.RW), np.uint8)
        self.ink_t = np.full((self.RH, self.RW), np.inf, np.float32)
        self.fill_rgb = np.zeros((self.RH, self.RW, 3), np.uint8)
        self.fill_a = np.zeros((self.RH, self.RW), np.uint8)
        self.fill_t = np.full((self.RH, self.RW), np.inf, np.float32)
        self.pen: List[Dict[str, Any]] = []      # pen movements, for the marker tip
        self.items: List[Tuple[int, int, int, int, float, float]] = []   # raster box and (start, finish) of everything placed
        self._cache: Tuple[int, Optional[np.ndarray]] = (-1, None)
        # paper: warm white with a very faint, static, low-frequency mottling (static = costs no bitrate)
        r = np.random.default_rng(seed)
        low = r.normal(0, 1, (self.RH // 48 + 2, self.RW // 48 + 2)).astype(np.float32)
        tex = np.asarray(Image.fromarray(low).resize((self.RW, self.RH), Image.BICUBIC), np.float32)
        self.paper = np.clip(np.array(PAPER, np.float32)[None, None, :] + tex[..., None] * 0.8 + 0.5, 0, 255).astype(np.uint8)

    # ------------------------------------------------------------------ placing
    def place(self, r: Dict[str, Any], x: float, y: float, colour: Tuple[int, int, int], t0: float, t1: float,
              fills: Optional[Sequence[Tuple[int, Tuple[int, int, int]]]] = None, fill_t0: float = 0.0, fill_dur: float = 0.45, tip: bool = True) -> None:
        """Put a rasterised drawing (vectorize.raster at this board's scale) with its top-left corner at board units (x, y); the pen draws it from t0 to t1.
        `fills`: [(index of the enclosed area, colour)], coloured in from fill_t0 over fill_dur each."""
        a, T = r["alpha"], r["T"]
        px, py = int(round(x * self.s)), int(round(y * self.s))
        h, w = a.shape
        sx0, sy0 = max(0, -px), max(0, -py)
        sx1, sy1 = min(w, self.RW - px), min(h, self.RH - py)
        if sx1 <= sx0 or sy1 <= sy0:
            return
        src = (slice(sy0, sy1), slice(sx0, sx1))
        dst = (slice(py + sy0, py + sy1), slice(px + sx0, px + sx1))
        a8 = np.clip(a * 255 + 0.5, 0, 255).astype(np.uint8)
        take = a8[src] > self.ink_a[dst]
        self.ink_rgb[dst][take] = colour
        self.ink_t[dst][take] = np.where(T[src] <= 1.0, t0 + T[src] * (t1 - t0), np.inf)[take]
        self.ink_a[dst][take] = a8[src][take]
        f_end = (fill_t0 + len(fills or []) * (fill_dur + 0.08)) if fills else t1
        self.items.append((py + sy0, py + sy1, px + sx0, px + sx1, t0, max(t1, f_end)))
        if tip:
            for s, tt in zip(r["strokes"], r["times"]):
                self.pen.append({"t": t0 + np.asarray(tt) * (t1 - t0), "p": (np.asarray(s) + np.array([px, py])) / self.s, "colour": colour})
        k = 0
        for idx, col in (fills or []):
            if idx >= len(r["fills"]):
                continue
            fa = r["fills"][idx][src] * 0.92
            ys, xs = np.nonzero(fa > 0.02)
            if not len(ys):
                continue
            f0 = fill_t0 + k * (fill_dur + 0.08)
            k += 1
            # coloured in with a diagonal zigzag, like a marker held flat: bands across, alternating direction
            yy, xx = np.mgrid[0:fa.shape[0], 0:fa.shape[1]].astype(np.float32)
            u, v = (xx + yy) * 0.7071, (xx - yy) * 0.7071
            m = fa > 0.02
            umin, umax, vmin, vmax = u[m].min(), u[m].max(), v[m].min(), v[m].max()
            nb = int(max(3, min(7, (umax - umin) / (60 * self.s))))
            bw = (umax - umin + 1e-3) / nb
            band = np.clip(np.floor((u - umin) / bw), 0, nb - 1)
            frac = np.clip((v - vmin) / (vmax - vmin + 1e-3), 0, 1)
            frac = np.where(band % 2 == 1, 1 - frac, frac)
            FT = f0 + (band + frac) / nb * fill_dur
            fa8 = np.clip(fa * 255 + 0.5, 0, 255).astype(np.uint8)
            takef = fa8 > self.fill_a[dst]
            self.fill_rgb[dst][takef] = col
            self.fill_t[dst][takef] = FT[takef]
            self.fill_a[dst][takef] = fa8[takef]

    SETTLE = 0.12     # seconds after an item's last pen pass at which its soft edges are fully in

    def _compose(self, sl, t: float) -> np.ndarray:
        """The board inside raster slice `sl` at time t, float RGB: paper, then colour, then ink."""
        out = self.paper[sl].astype(np.float32)
        fa = self.fill_a[sl] * (np.clip((t - self.fill_t[sl]) / 0.06, 0.0, 1.0) / 255.0)
        if fa.any():
            out += (self.fill_rgb[sl].astype(np.float32) - out) * fa[..., None]
        ia = self.ink_a[sl] * (np.clip((t - self.ink_t[sl]) / SOFT, 0.0, 1.0) / 255.0)
        if ia.any():
            out += (self.ink_rgb[sl].astype(np.float32) - out) * ia[..., None]
        return out

    # ------------------------------------------------------------------ a frame
    def frame(self, t: float, cam: Tuple[float, float, float], size: Tuple[int, int] = (1920, 1080), tip: bool = True) -> Image.Image:
        ow, oh = size
        x0, y0, w = cam
        h = w * oh / ow
        s = self.s
        fx0, fy0, fx1, fy1 = x0 * s, y0 * s, (x0 + w) * s, (y0 + h) * s
        ix0, iy0 = max(0, int(math.floor(fx0)) - 2), max(0, int(math.floor(fy0)) - 2)
        ix1, iy1 = min(self.RW, int(math.ceil(fx1)) + 2), min(self.RH, int(math.ceil(fy1)) + 2)
        # Everything finished is flat and cached (the cache is itself a function of time: it depends only on WHICH items have finished);
        # only the boxes of items being drawn right now are composited again. The result is identical to compositing the whole window.
        fin = int(np.searchsorted(self._finish, t - self.SETTLE, side="right"))
        if self._cache[0] != fin:
            tc = float(self._finish[fin - 1]) + self.SETTLE if fin else -1e9
            whole = (slice(0, self.RH), slice(0, self.RW))
            self._cache = (fin, np.clip(self._compose(whole, tc) + 0.5, 0, 255).astype(np.uint8))
        crop = self._cache[1][iy0:iy1, ix0:ix1].copy()
        for (y0b, y1b, x0b, x1b, ts, tf) in self.items:
            if ts <= t < tf + self.SETTLE:
                ya, yb, xa, xb = max(y0b, iy0), min(y1b, iy1), max(x0b, ix0), min(x1b, ix1)
                if yb > ya and xb > xa:
                    crop[ya - iy0:yb - iy0, xa - ix0:xb - ix0] = np.clip(self._compose((slice(ya, yb), slice(xa, xb)), t) + 0.5, 0, 255).astype(np.uint8)
        im = Image.fromarray(crop)
        im = im.resize((ow, oh), Image.BICUBIC if (fx1 - fx0) < ow * 1.3 else Image.LANCZOS, box=(fx0 - ix0, fy0 - iy0, fx1 - ix0, fy1 - iy0))
        if tip:
            pos = self.pen_at(t)
            if pos is not None:
                (bx, by), colour, alpha = pos
                k = ow / w
                draw_marker(im, ((bx - x0) * k, (by - y0) * k), colour, alpha, ow / 1920.0)
        return im

    # ------------------------------------------------------------------ the marker tip
    def finish(self) -> None:
        self.pen.sort(key=lambda m: float(m["t"][0]))
        self._starts = np.array([float(m["t"][0]) for m in self.pen])
        self.items.sort(key=lambda it: it[5])
        self._finish = np.array([it[5] for it in self.items])

    def pen_at(self, t: float):
        """-> ((x, y) in board units, ink colour, opacity) or None. While drawing the tip is on the growing end; between strokes it glides along a shallow arc;
        left idle it lifts away (fades) and comes back just before the next stroke."""
        if not self.pen:
            return None
        i = int(np.searchsorted(self._starts, t, side="right")) - 1
        if i < 0:
            nxt = self.pen[0]
            u = (float(nxt["t"][0]) - t) / 0.35
            return (tuple(nxt["p"][0] + np.array([60.0, 60.0]) * min(1, u)), nxt["colour"], max(0.0, 1 - u)) if u < 1 else None
        cur = self.pen[i]
        tt, pp = cur["t"], cur["p"]
        if t <= tt[-1]:
            return ((float(np.interp(t, tt, pp[:, 0])), float(np.interp(t, tt, pp[:, 1]))), cur["colour"], 1.0)
        end, t_end = pp[-1], float(tt[-1])
        if i + 1 >= len(self.pen):
            u = (t - t_end) / 0.5
            return (tuple(end + np.array([70.0, 70.0]) * ease(u)), cur["colour"], 1 - ease(u)) if u < 1 else None
        nxt = self.pen[i + 1]
        gap = float(nxt["t"][0]) - t_end
        if gap > 1.1:        # idle: lift away, return before the next stroke
            if t - t_end < 0.4:
                u = (t - t_end) / 0.4
                return (tuple(end + np.array([70.0, 70.0]) * ease(u)), cur["colour"], 1 - ease(u))
            if float(nxt["t"][0]) - t < 0.4:
                u = (float(nxt["t"][0]) - t) / 0.4
                return (tuple(nxt["p"][0] + np.array([70.0, 70.0]) * ease(u)), nxt["colour"], 1 - ease(u))
            return None
        u = ease((t - t_end) / max(gap, 1e-3))
        a, b = end, nxt["p"][0]
        mid = a + (b - a) * u
        lift = math.sin(math.pi * u) * min(40.0, 0.12 * float(np.hypot(*(b - a))))
        return ((float(mid[0]), float(mid[1] - lift)), nxt["colour"] if u > 0.5 else cur["colour"], 1.0)


_MARKERS: Dict[Tuple[Tuple[int, int, int], int], Tuple[Image.Image, Tuple[int, int]]] = {}


def _marker_sprite(colour: Tuple[int, int, int], k: float) -> Tuple[Image.Image, Tuple[int, int]]:
    """A whiteboard marker seen from above, nib at the sprite's anchor, held as a right hand holds it (barrel going down-right). Drawn large and reduced."""
    key = (colour, int(k * 100))
    if key in _MARKERS:
        return _MARKERS[key]
    S = 4
    L, Wd = int(430 * k * S), int(46 * k * S)
    pad = int(40 * k * S)
    im = Image.new("RGBA", (L + 2 * pad, Wd + 2 * pad), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    cy = pad + Wd // 2
    nib, neck = int(26 * k * S), int(52 * k * S)
    d.polygon([(pad, cy), (pad + nib, cy - Wd * 0.16), (pad + nib, cy + Wd * 0.16)], fill=colour + (255,))                          # nib
    d.polygon([(pad + nib, cy - Wd * 0.2), (pad + nib + neck, cy - Wd * 0.42), (pad + nib + neck, cy + Wd * 0.42), (pad + nib, cy + Wd * 0.2)], fill=(58, 61, 68, 255))   # collar
    x = pad + nib + neck
    d.rounded_rectangle([x, cy - Wd // 2, pad + L, cy + Wd // 2], radius=int(Wd * 0.22), fill=(246, 246, 248, 255), outline=(150, 154, 162, 255), width=max(1, int(1.6 * S * k)))   # barrel
    d.rectangle([x + int(34 * k * S), cy - Wd // 2 + 1, x + int(120 * k * S), cy + Wd // 2 - 1], fill=colour + (255,))               # colour band
    d.rounded_rectangle([pad + L - int(56 * k * S), cy - Wd // 2, pad + L, cy + Wd // 2], radius=int(Wd * 0.22), fill=colour + (255,))  # end cap
    d.line([x + 6, cy - Wd * 0.26, pad + L - 8, cy - Wd * 0.26], fill=(255, 255, 255, 150), width=max(1, int(3 * S * k)))            # highlight
    rot = im.rotate(-52, resample=Image.BICUBIC, expand=True)
    # where did the nib go: rotate the anchor the same way
    cx0, cy0 = im.width / 2, im.height / 2
    ang = math.radians(52)
    dx, dy = pad - cx0, cy - cy0
    ax = rot.width / 2 + dx * math.cos(ang) - dy * math.sin(ang)
    ay = rot.height / 2 + dx * math.sin(ang) + dy * math.cos(ang)
    small = rot.resize((max(1, rot.width // S), max(1, rot.height // S)), Image.LANCZOS)
    sh = Image.new("RGBA", small.size, (0, 0, 0, 0))
    sh.putalpha(small.split()[3].point(lambda v: int(v * 0.22)).filter(ImageFilter.GaussianBlur(6 * k)))
    canvas = Image.new("RGBA", (small.width + int(30 * k), small.height + int(30 * k)), (0, 0, 0, 0))
    canvas.alpha_composite(sh, (int(10 * k), int(12 * k)))
    canvas.alpha_composite(small, (0, 0))
    _MARKERS[key] = (canvas, (int(round(ax / S)), int(round(ay / S))))
    return _MARKERS[key]


def draw_marker(im: Image.Image, xy: Tuple[float, float], colour: Tuple[int, int, int], alpha: float, k: float) -> None:
    if alpha <= 0.01:
        return
    spr, (ax, ay) = _marker_sprite(colour, k)
    if alpha < 0.999:
        spr = spr.copy()
        spr.putalpha(spr.split()[3].point(lambda v: int(v * alpha)))
    im.paste(spr, (int(round(xy[0] - ax)), int(round(xy[1] - ay))), spr)


class Camera:
    """Holds a view, eases to the next: [(t_start, t_end, (x0, y0, w))]. Pure function of time."""

    def __init__(self, first: Tuple[float, float, float]):
        self.first, self.moves = first, []

    def move(self, t0: float, t1: float, view: Tuple[float, float, float]) -> None:
        self.moves.append((t0, t1, view))

    def at(self, t: float) -> Tuple[float, float, float]:
        cur = self.first
        for t0, t1, v in self.moves:
            if t >= t1:
                cur = v
            elif t > t0:
                u = ease((t - t0) / (t1 - t0))
                # zoom is eased in log space and the window centre linearly: no swimming
                w = math.exp(math.log(cur[2]) + (math.log(v[2]) - math.log(cur[2])) * u)
                return (cur[0] + (v[0] - cur[0]) * u, cur[1] + (v[1] - cur[1]) * u, w)
            else:
                break
        return cur


def encode(frames, path: str, fps: int = 30, size: Tuple[int, int] = (1920, 1080), audio: Optional[str] = None, crf: int = 18) -> None:
    """Pipe RGB frames to ONE niced ffmpeg (x264). No frame files are written."""
    import subprocess

    cmd = ["nice", "-n", "10", "ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{size[0]}x{size[1]}", "-r", str(fps), "-i", "-"]
    if audio:
        cmd += ["-i", audio]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p", "-threads", "3"]
    if audio:
        cmd += ["-c:a", "aac", "-b:a", "128k", "-shortest"]
    cmd += ["-movflags", "+faststart", path]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for im in frames:
        p.stdin.write(im.tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("ffmpeg failed")
