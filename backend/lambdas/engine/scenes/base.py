"""Shared pieces for scene modules."""
import re
from dataclasses import dataclass
from typing import Any, Callable, Optional

from PIL import Image

from ..canvas import Canvas, with_alpha
from ..easing import ease_out_cubic, progress
from ..frame import DEFAULT_FRAME, Frame
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
    frame: Frame = DEFAULT_FRAME   # the shape being rendered (engine/frame.py): lay out in design units from it, never from 1920/1080 literals

    @property
    def bottom(self) -> int:
        """Lowest y (design units) content may reach: just above the caption band of this frame."""
        return self.frame.content_bottom(self.captions)

    @property
    def top(self) -> int:
        return self.frame.margin_top

    @property
    def box(self):
        """(x0, y0, x1, y1) scenes may use, above the caption band."""
        return self.frame.box(self.captions)


def heading(cv: Canvas, th: Theme, text: str, lt: float, y: float = 96, size: float = 64, ctx: Optional[SceneCtx] = None) -> float:
    """Left-aligned section heading with a draw-on accent underline. Returns y below it. With `ctx` it follows the frame (margin, width, a larger size when
    narrow, wrapped to two lines if needed); without it, it is the landscape heading it always was."""
    if not text:
        return y
    fr = ctx.frame if ctx is not None else DEFAULT_FRAME
    x, wmax = (fr.margin_x, fr.W - 2 * fr.margin_x) if not fr.landscape else (140, 1400)
    p = ease_out_cubic(progress(lt, 0.05, 0.55))
    if fr.landscape:
        lines = [text]
    else:
        size = size * fr.type_scale
        for _ in range(20):
            lines = cv.wrap(text, "semibold", size, wmax)
            if len(lines) <= 2 or size <= 40:
                break
            size -= 4
        lines = lines[:2]
        while max(cv.measure(l, "semibold", size) for l in lines) > wmax and size > 28:   # one very long word (hyphenated terms) must still fit the frame
            size -= 4
            lines = cv.wrap(text, "semibold", size, wmax)[:2]
    for k, line in enumerate(lines):
        cv.text(x, y + k * size * 1.2 + (1 - p) * 24, line, "semibold", size, with_alpha(th.text, p))
    yl = y + (len(lines) - 1) * size * 1.2
    bw = min(max(cv.measure(l, "semibold", size) for l in lines), wmax) * ease_out_cubic(progress(lt, 0.25, 0.7))
    cv.rrect(x, yl + size * 1.28, bw, 8, 4, fill=th.accent)
    return yl + size * 1.28 + 40


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
