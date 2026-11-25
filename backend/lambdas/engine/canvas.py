"""A small 2D canvas on Pillow with 2x supersampling (anti-aliased shapes), logical 1920x1080 coords.

Pillow's ImageDraw has no anti-aliasing, so everything is drawn at `ss`x and box-reduced at the end.
Heavy things (gradients, blurred shadows) are cached sprites, never recomputed per frame.
"""
import os
from functools import lru_cache
from typing import List, Sequence, Tuple

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .theme import Theme

FONT_DIR = os.path.join(os.path.dirname(__file__), "assets", "fonts")
_WEIGHTS = {"regular": "Inter-Regular.ttf", "semibold": "Inter-SemiBold.ttf", "bold": "Inter-Bold.ttf"}

Color = Tuple[int, ...]


@lru_cache(maxsize=64)
def load_font(weight: str, px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(os.path.join(FONT_DIR, _WEIGHTS.get(weight, _WEIGHTS["regular"])), px)


def with_alpha(c: Color, a: float) -> Tuple[int, int, int, int]:
    base = c[3] / 255.0 if len(c) == 4 else 1.0
    return (int(c[0]), int(c[1]), int(c[2]), int(max(0.0, min(1.0, a * base)) * 255))


@lru_cache(maxsize=8)
def _gradient(w: int, h: int, top: Color, bottom: Color) -> Image.Image:
    t = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None, None]
    arr = np.array(top, np.float32) * (1 - t) + np.array(bottom, np.float32) * t
    arr = np.broadcast_to(arr, (h, w, 3)).astype(np.uint8)
    return Image.fromarray(arr, "RGB")


@lru_cache(maxsize=64)
def _shadow_sprite(w: int, h: int, r: int, blur: int, alpha: int, pad: int) -> Image.Image:
    mask = Image.new("L", (w + 2 * pad, h + 2 * pad), 0)
    ImageDraw.Draw(mask).rounded_rectangle([pad, pad, pad + w - 1, pad + h - 1], r, fill=alpha)
    return mask.filter(ImageFilter.GaussianBlur(blur))


@lru_cache(maxsize=16)
def _blob_sprite(d: int, alpha: int) -> Image.Image:
    """Soft glow mask. Built at low resolution (the glow is blurry by nature) and reused."""
    mask = Image.new("L", (d, d), 0)
    ImageDraw.Draw(mask).ellipse([d * 0.2, d * 0.2, d * 0.8, d * 0.8], fill=alpha)
    return mask.filter(ImageFilter.GaussianBlur(d * 0.12))


_BG_CACHE: dict = {}
AMBIENT_DOWNSCALE = 8  # ambient layer is composed at 1/8 of the supersampled canvas, then upscaled


class Canvas:
    def __init__(self, width: int = 1920, height: int = 1080, ss: int = 2):
        self.W, self.H, self.ss = width, height, ss   # W, H: DESIGN units (see frame.py); the pixel size is W*ss x H*ss
        self.min_font = 1e9   # smallest type size drawn (design units): the framed fallback reads it to flag text that became too small
        self.im = Image.new("RGB", (width * ss, height * ss))
        self.d = ImageDraw.Draw(self.im, "RGBA")

    # ---------- output ----------
    def to_rgb(self, size=None, resample=None) -> Image.Image:
        """The finished image at design size, or at `size` (w, h) when that differs (720p: a box reduce by 3 from the 2x canvas)."""
        if size and tuple(size) != (self.W, self.H):
            tw, th = int(size[0]), int(size[1])
            if self.im.width % tw == 0 and self.im.height % th == 0 and self.im.width // tw == self.im.height // th:
                k = self.im.width // tw
                return self.im.reduce(k) if k > 1 else self.im
            return self.im.resize((tw, th), resample if resample is not None else (Image.BOX if self.ss > 1 else Image.BILINEAR))
        return self.im.reduce(self.ss) if self.ss > 1 else self.im

    # ---------- background ----------
    def background(self, theme: Theme, t: float = 0.0, ambience: bool = True) -> None:
        import math

        full = (self.W * self.ss, self.H * self.ss)
        if not ambience:
            self.im.paste(_gradient(full[0], full[1], theme.bg_top, theme.bg_bottom))
            return
        # The glow drifts ~1px per 0.1s: quantise time so consecutive frames reuse one composed image.
        qt = round(t * 10) / 10.0
        key = (theme.name, full, qt)
        cached = _BG_CACHE.get(key)
        if cached is not None:
            self.im.paste(cached)
            return
        sw, sh = full[0] // AMBIENT_DOWNSCALE, full[1] // AMBIENT_DOWNSCALE
        small = _gradient(sw, sh, theme.bg_top, theme.bg_bottom).copy()
        d = int(sw * 0.9)
        alpha = 70 if theme.name != "paper" else 38
        for color, phase, ax, ay in ((theme.accent, 0.0, 0.26, 0.2), (theme.accent2, 2.1, 0.74, 0.8)):
            blob = _blob_sprite(d, alpha)
            cx = (ax + 0.04 * math.sin(qt * 0.35 + phase)) * sw
            cy = (ay + 0.05 * math.cos(qt * 0.28 + phase)) * sh
            small.paste(Image.new("RGB", blob.size, color), (int(cx - d / 2), int(cy - d / 2)), blob)
        if self.ss >= 4:   # 4K (docs/FOUR_K.md): the glow has no detail, so it is enlarged smoothly to half the canvas and doubled; after the final 2x reduce this is exactly the smooth image
            composed = small.resize((full[0] // 2, full[1] // 2), Image.BICUBIC).resize(full, Image.NEAREST)
        else:
            composed = small.resize(full, Image.BICUBIC)
        if len(_BG_CACHE) >= 4:
            _BG_CACHE.pop(next(iter(_BG_CACHE)))
        _BG_CACHE[key] = composed
        self.im.paste(composed)

    # ---------- primitives (logical coordinates) ----------
    def _s(self, v: float) -> int:
        return int(round(v * self.ss))

    def rrect(self, x, y, w, h, r, fill=None, outline=None, width: float = 0):
        x0, y0, x1, y1 = self._s(x), self._s(y), self._s(x + w) - 1, self._s(y + h) - 1
        if x1 <= x0 or y1 <= y0:  # degenerate (e.g. an animation's first frame): nothing to draw
            return
        rad = max(0, min(self._s(r), (x1 - x0) // 2, (y1 - y0) // 2))
        self.d.rounded_rectangle([x0, y0, x1, y1], rad, fill=fill, outline=outline, width=max(1, self._s(width)) if outline else 0)

    def ellipse(self, cx, cy, rx, ry, fill=None, outline=None, width: float = 0):
        if rx <= 0 or ry <= 0:
            return
        self.d.ellipse(
            [self._s(cx - rx), self._s(cy - ry), self._s(cx + rx), self._s(cy + ry)],
            fill=fill, outline=outline, width=max(1, self._s(width)) if outline else 0,
        )

    def line(self, pts: Sequence[Tuple[float, float]], fill, width: float = 4, round_caps: bool = True):
        if len(pts) < 2:
            return
        sp = [(self._s(x), self._s(y)) for x, y in pts]
        w = max(1, self._s(width))
        self.d.line(sp, fill=fill, width=w, joint="curve")
        if round_caps:
            r = w / 2
            for x, y in (sp[0], sp[-1]):
                self.d.ellipse([x - r, y - r, x + r, y + r], fill=fill)

    def polygon(self, pts, fill):
        self.d.polygon([(self._s(x), self._s(y)) for x, y in pts], fill=fill)

    def arc(self, cx, cy, radius, start_deg, end_deg, fill, width: float):
        r = self._s(radius)
        self.d.arc([self._s(cx) - r, self._s(cy) - r, self._s(cx) + r, self._s(cy) + r], start_deg, end_deg, fill=fill, width=max(1, self._s(width)))

    def shadow(self, x, y, w, h, r, blur: float = 22, dy: float = 12, alpha: float = 0.4):
        if w < 2 or h < 2:
            return
        pad = self._s(blur * 2.5)
        sp = _shadow_sprite(self._s(w), self._s(h), self._s(r), self._s(blur), int(255 * max(0.0, min(1.0, alpha))), pad)
        black = Image.new("RGB", sp.size, (0, 0, 0))
        self.im.paste(black, (self._s(x) - pad, self._s(y + dy) - pad), sp)

    def card(self, x, y, w, h, theme: Theme, r: float = 28, alpha: float = 1.0, shadow: bool = True):
        if alpha <= 0.01:
            return
        if shadow:
            self.shadow(x, y, w, h, r, alpha=theme.shadow_alpha * alpha)
        self.rrect(x, y, w, h, r, fill=with_alpha(theme.card, alpha), outline=with_alpha(theme.card_outline, alpha), width=1.5)

    # ---------- text ----------
    def font(self, weight: str, size: float) -> ImageFont.FreeTypeFont:
        return load_font(weight, self._s(size))

    def measure(self, s: str, weight: str, size: float) -> float:
        return self.font(weight, size).getlength(s) / self.ss

    def text(self, x, y, s: str, weight="regular", size=40, fill=(255, 255, 255, 255), anchor="la"):
        """Draws text honouring the fill's alpha. (PIL's RGBA draw ignores the alpha of text on an RGB canvas: every fade-in used to appear at full
        strength from its first frame, and text with alpha 0 was fully visible. Shapes blend correctly; text is blended here through a mask.)"""
        a = int(fill[3]) if len(fill) == 4 else 255
        if a <= 0 or not s:
            return
        if size < self.min_font:
            self.min_font = size
        font = self.font(weight, size)
        X, Y = self._s(x), self._s(y)
        if a >= 255:
            self.d.text((X, Y), s, font=font, fill=tuple(fill[:3]) + (255,), anchor=anchor)
            return
        l, t, r, b = self.d.textbbox((X, Y), s, font=font, anchor=anchor)
        box = (max(0, int(l) - 3), max(0, int(t) - 3), min(self.im.width, int(r) + 3), min(self.im.height, int(b) + 3))
        if box[2] <= box[0] or box[3] <= box[1]:
            return
        mask = Image.new("L", (box[2] - box[0], box[3] - box[1]), 0)
        ImageDraw.Draw(mask).text((X - box[0], Y - box[1]), s, font=font, fill=255, anchor=anchor)
        self.im.paste(tuple(fill[:3]), box, mask.point(lambda v: v * a // 255))

    def wrap(self, s: str, weight: str, size: float, max_w: float) -> List[str]:
        font = self.font(weight, size)
        limit = max_w * self.ss
        lines: List[str] = []
        cur = ""
        for word in s.split():
            trial = f"{cur} {word}".strip()
            if font.getlength(trial) <= limit or not cur:
                cur = trial
            else:
                lines.append(cur)
                cur = word
        if cur:
            lines.append(cur)
        return lines

    def fit_text(self, s: str, weight: str, max_w: float, max_h: float, start: float, min_size: float = 28, line_h: float = 1.18):
        """Largest font size (<= start) whose wrapped block fits max_w x max_h. Returns (size, lines)."""
        size = start
        while size >= min_size:
            lines = self.wrap(s, weight, size, max_w)
            if len(lines) * size * line_h <= max_h:
                return size, lines
            size -= 4
        return min_size, self.wrap(s, weight, min_size, max_w)

    # ---------- images ----------
    def paste_image(self, img: Image.Image, x: float = 0, y: float = 0, alpha: float = 1.0):
        if alpha >= 0.999:
            self.im.paste(img, (self._s(x), self._s(y)))
        elif alpha > 0:
            region = self.im.crop((self._s(x), self._s(y), self._s(x) + img.width, self._s(y) + img.height))
            self.im.paste(Image.blend(region, img, alpha), (self._s(x), self._s(y)))


def partial_polyline(pts: Sequence[Tuple[float, float]], p: float) -> List[Tuple[float, float]]:
    """The first fraction p (0..1) of a polyline's length: used for 'draw-on' animations."""
    if p >= 1:
        return list(pts)
    if p <= 0 or len(pts) < 2:
        return [pts[0]] if pts else []
    seg = [((pts[i + 1][0] - pts[i][0]) ** 2 + (pts[i + 1][1] - pts[i][1]) ** 2) ** 0.5 for i in range(len(pts) - 1)]
    target = sum(seg) * p
    out = [pts[0]]
    run = 0.0
    for i, s in enumerate(seg):
        if run + s >= target:
            f = (target - run) / s if s else 0
            out.append((pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f, pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f))
            return out
        out.append(pts[i + 1])
        run += s
    return out
