"""Shared pieces for scene modules."""
from dataclasses import dataclass
from typing import Any, Callable, Optional

from PIL import Image

from .. import numfmt
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
    language: str = "en"   # the video's language ('en'/'es'): numbers are written and read the way that language does (engine/numfmt.py)
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


def parse_number(s: str, lang=None):
    """'$1,250.5M' -> ('$', 1250.5, 1, 'M', True); in a Spanish video '3,3 millones' -> ('', 3.3, 1, ' millones', False). None when there is no number.
    Locale-aware (engine/numfmt.py): the video's language comes from the renderer's scope, so '3,3' is never read as 33."""
    return numfmt.parse_number(s, lang)


def format_number(val: float, decimals: int, comma: bool, lang=None) -> str:
    """The number as the video's language writes it (English 1,250.5; Spanish 1250,5 and 12 345,6)."""
    return numfmt.format_number(val, decimals, comma, lang)
