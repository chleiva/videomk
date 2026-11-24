"""Shared pieces for scene modules."""
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

from PIL import Image

from ..canvas import Canvas, with_alpha
from ..easing import ease_out_cubic, progress
from ..theme import Theme

# Captions occupy the bottom band; scene content must stay above this line.
CONTENT_TOP = 70
CONTENT_BOTTOM = 800
CENTER_X = 960


@dataclass
class SceneCtx:
    """Per-render context handed to scenes (asset access, geometry)."""

    resolve_image: Callable[[str], Optional[Image.Image]] = lambda key: None
    resolve_clip: Callable[[str], Any] = lambda key: None   # key -> engine.clips.ClipFrames | None
    captions: bool = True

    @property
    def bottom(self) -> int:
        return CONTENT_BOTTOM if self.captions else 1000


def heading(cv: Canvas, th: Theme, text: str, lt: float, y: float = 96, size: float = 64) -> float:
    """Left-aligned section heading with a draw-on accent underline. Returns y below it."""
    if not text:
        return y
    p = ease_out_cubic(progress(lt, 0.05, 0.55))
    cv.text(140, y + (1 - p) * 24, text, "semibold", size, with_alpha(th.text, p))
    bw = min(cv.measure(text, "semibold", size), 1400) * ease_out_cubic(progress(lt, 0.25, 0.7))
    cv.rrect(140, y + size * 1.28, bw, 8, 4, fill=th.accent)
    return y + size * 1.28 + 40


_NUM = re.compile(r"^([^\d\-+]*)([\-+]?[\d,]*\.?\d+)(.*)$", re.S)


def parse_number(s: str):
    """'$1,250.5M' -> ('$', 1250.5, 1, 'M', True). Returns None when there is no number."""
    m = _NUM.match(str(s).strip())
    if not m:
        return None
    pre, num, suf = m.groups()
    raw = num.replace(",", "")
    try:
        val = float(raw)
    except ValueError:
        return None
    decimals = len(raw.split(".")[1]) if "." in raw else 0
    return pre, val, decimals, suf, "," in num


def format_number(val: float, decimals: int, comma: bool) -> str:
    return f"{val:,.{decimals}f}" if comma or abs(val) >= 10000 else f"{val:.{decimals}f}"
