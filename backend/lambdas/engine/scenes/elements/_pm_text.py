"""Small helpers shared by the people_media elements: string cleaning, a serif face (Playfair Display Bold, bundled), colour maths."""
import colorsys
import os
import re
from functools import lru_cache
from typing import List, Tuple

from PIL import Image, ImageDraw, ImageFont

ASSETS = os.path.join(os.path.dirname(__file__), "..", "..", "assets")
SERIF_PATH = os.path.join(ASSETS, "fonts", "PlayfairDisplay_700Bold.ttf")

_INVISIBLE = re.compile(r"[​-‏‪-‮⁠-⁩﻿]")
_CTRL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def clean(x, n: int) -> str:
    """One line, no control or bidi characters, at most n characters; a longer text is cut on a word boundary and ends with an ellipsis.
    Idempotent: a result is already within n and comes back unchanged."""
    s = _CTRL.sub(" ", _INVISIBLE.sub("", "" if x is None else str(x)))
    s = " ".join(s.split())
    if len(s) <= n:
        return s
    cut = s[: max(1, n - 1)]
    sp = cut.rfind(" ")
    if sp >= (n - 1) * 0.55:
        cut = cut[:sp]
    return cut.rstrip(" ,;:-.") + "…"


@lru_cache(maxsize=32)
def _serif(px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(SERIF_PATH, px)


def serif_measure(cv, s: str, size: float) -> float:
    return _serif(cv._s(size)).getlength(s) / cv.ss


def serif_wrap(cv, s: str, size: float, max_w: float) -> List[str]:
    font = _serif(cv._s(size))
    limit = max_w * cv.ss
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


def serif_text(cv, x: float, y: float, s: str, size: float, fill, anchor: str = "la") -> None:
    """The canvas' own alpha-correct text routine, with the serif face."""
    a = int(fill[3]) if len(fill) == 4 else 255
    if a <= 0 or not s:
        return
    font = _serif(cv._s(size))
    X, Y = cv._s(x), cv._s(y)
    if a >= 255:
        cv.d.text((X, Y), s, font=font, fill=tuple(fill[:3]) + (255,), anchor=anchor)
        return
    l, t, r, b = cv.d.textbbox((X, Y), s, font=font, anchor=anchor)
    box = (max(0, int(l) - 3), max(0, int(t) - 3), min(cv.im.width, int(r) + 3), min(cv.im.height, int(b) + 3))
    if box[2] <= box[0] or box[3] <= box[1]:
        return
    mask = Image.new("L", (box[2] - box[0], box[3] - box[1]), 0)
    ImageDraw.Draw(mask).text((X - box[0], Y - box[1]), s, font=font, fill=255, anchor=anchor)
    cv.im.paste(tuple(fill[:3]), box, mask.point(lambda v: v * a // 255))


def luminance(c) -> float:
    def f(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2])


def on_color(bg) -> Tuple[int, int, int]:
    """Readable text colour (near-white or near-black) on a given fill."""
    return (255, 255, 255) if luminance(bg) < 0.34 else (17, 24, 39)


def hue_shift(c, turn: float) -> Tuple[int, int, int]:
    h, l, s = colorsys.rgb_to_hls(c[0] / 255, c[1] / 255, c[2] / 255)
    r, g, b = colorsys.hls_to_rgb((h + turn) % 1.0, l, s)
    return int(r * 255), int(g * 255), int(b * 255)
