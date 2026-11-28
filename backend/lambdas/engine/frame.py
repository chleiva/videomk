"""Frame: the shape of a video (aspect + resolution) and the layout numbers every scene needs.

Scenes lay out in DESIGN units, a virtual canvas whose short side is 1080 (16:9 -> 1920x1080, 9:16 -> 1080x1920, 1:1 -> 1080x1080, 4:5 -> 1080x1350).
The renderer scales design units to the real pixel size (720p is just a scale of 2/3, 2160p (4K) a scale of 2), so a scene never knows which resolution it renders at.
Dependency-free on purpose: the options plumbing, the director prompt and the renderer all import it.
The contract for scenes and elements is in docs/RESPONSIVE_LAYOUT.md.
"""
from dataclasses import dataclass
from typing import Dict, Tuple

ASPECTS = ("16:9", "9:16", "1:1", "4:5")
RESOLUTIONS = ("720p", "1080p", "2160p")
SHORT_SIDE: Dict[str, int] = {"720p": 720, "1080p": 1080, "2160p": 2160}   # real pixels of the short side; 2160p is 4K (16:9 -> 3840x2160), docs/FOUR_K.md
DEFAULT_ASPECT = "16:9"
DEFAULT_RESOLUTION = "1080p"

_DESIGN: Dict[str, Tuple[int, int]] = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350)}
_ORIENT = {"16:9": "landscape", "9:16": "portrait", "1:1": "square", "4:5": "portrait"}
# Burned-in captions: bottom edge of the caption box (design y), type size, widest box, reserved right strip (platform buttons), words per page
_CAPTION = {
    "16:9": dict(bottom=1010, size=46, max_w=1480, x0=0, x1=1920, words=11),
    "9:16": dict(bottom=1600, size=58, max_w=900, x0=48, x1=950, words=7),     # above the platform UI zone (bottom 320 = the TikTok figure of published safe-zone guides, right 130)
    "1:1": dict(bottom=1020, size=50, max_w=920, x0=0, x1=1080, words=8),
    "4:5": dict(bottom=1290, size=52, max_w=920, x0=0, x1=1080, words=8),
}
# Safe margins (left/right, top) in design units. The top of the shapes whose corner mark sits at the top-left (9:16 under the platform header, 1:1, 4:5) is just below the lowest the mark
# can reach there (the largest custom logo, 9:16 y 200 to 308, square and 4:5 y 38 to 146), so no title or card of ANY scene template starts under it.
# A constant of the shape, the same for every account (the mark is a final layer: docs/WATERMARK_DECOUPLED_2026-11-28.md, docs/TITLES_AND_CLIP_NARRATION_2026-11-28.md).
_MARGIN = {"16:9": (140, 70), "9:16": (72, 310), "1:1": (80, 150), "4:5": (80, 150)}
_CREDIT_Y = {"16:9": 40, "9:16": 120, "1:1": 40, "4:5": 50}   # the clip / photo credit line (top right): where it always was, it is not under the mark (top left)
# Bottom of the content box when captions are ON: just above the caption box (2 lines) with a gap; None -> computed
_CONTENT_BOTTOM_CAP = {"16:9": 800, "9:16": 1385, "1:1": 840, "4:5": 1080}   # 1:1 and 4:5 raised when their top margin moved down (150): the box shrinks by 20 and 30 and not by 80 and 70
_CONTENT_BOTTOM_NOCAP = {"16:9": 1000, "9:16": 1670, "1:1": 1010, "4:5": 1280}
_RIGHT_RESERVE = {"16:9": 0, "9:16": 130, "1:1": 0, "4:5": 0}   # platform buttons column (vertical formats): keep key text out of it near the bottom

MIN_READABLE_PX = 22   # design px at 1080 short side: smaller drawn text (after any fallback shrink) is flagged unreadable


@dataclass(frozen=True)
class Frame:
    aspect: str = DEFAULT_ASPECT
    resolution: str = DEFAULT_RESOLUTION

    # ----- pixel size
    @property
    def design_w(self) -> int:
        return _DESIGN[self.aspect][0]

    @property
    def design_h(self) -> int:
        return _DESIGN[self.aspect][1]

    @property
    def W(self) -> int:
        """Design width (what scenes lay out in)."""
        return self.design_w

    @property
    def H(self) -> int:
        return self.design_h

    @property
    def scale_factor(self) -> float:
        return SHORT_SIDE.get(self.resolution, 1080) / 1080

    @property
    def width(self) -> int:
        """Real output width in pixels."""
        return int(round(self.design_w * self.scale_factor))

    @property
    def height(self) -> int:
        return int(round(self.design_h * self.scale_factor))

    def scale(self, x: float) -> float:
        """Design units -> real pixels."""
        return x * self.scale_factor

    @property
    def orientation(self) -> str:
        return _ORIENT[self.aspect]

    @property
    def landscape(self) -> bool:
        return self.aspect == "16:9"

    @property
    def vertical(self) -> bool:
        """Taller than wide (9:16 and 4:5)."""
        return self.orientation == "portrait"

    @property
    def square(self) -> bool:
        return self.aspect == "1:1"

    @property
    def cx(self) -> float:
        return self.design_w / 2

    @property
    def cy(self) -> float:
        return self.design_h / 2

    # ----- type scale
    @property
    def type_scale(self) -> float:
        """How much larger text should be, relative to a landscape layout, for the same legibility on a narrower frame (1.0 landscape)."""
        return {"16:9": 1.0, "9:16": 1.22, "1:1": 1.12, "4:5": 1.15}[self.aspect]

    # ----- margins, captions, content box
    @property
    def margin_x(self) -> int:
        return _MARGIN[self.aspect][0]

    @property
    def margin_top(self) -> int:
        return _MARGIN[self.aspect][1]   # the same for every video: a watermark never moves content (docs/WATERMARK.md, the final stage)

    @property
    def credit_y(self) -> int:
        return _CREDIT_Y[self.aspect]

    @property
    def right_reserve(self) -> int:
        return _RIGHT_RESERVE[self.aspect]

    @property
    def caption(self) -> Dict[str, float]:
        """Caption placement in design units: bottom (y of the box's bottom edge), size (font), max_w (text width), x0/x1 (the span the box is centred in), words (per page)."""
        return dict(_CAPTION[self.aspect], max_lines=2)

    def content_bottom(self, captions: bool = True) -> int:
        return (_CONTENT_BOTTOM_CAP if captions else _CONTENT_BOTTOM_NOCAP)[self.aspect]

    def box(self, captions: bool = True) -> Tuple[int, int, int, int]:
        """The rectangle (x0, y0, x1, y1) scenes may use, above the caption band (design units)."""
        return (self.margin_x, self.margin_top, self.design_w - self.margin_x, self.content_bottom(captions))

    @property
    def content_box(self) -> Tuple[int, int, int, int]:
        """`box(captions=True)`."""
        return self.box(True)

    def content_size(self, captions: bool = True) -> Tuple[int, int]:
        b = self.box(captions)
        return b[2] - b[0], b[3] - b[1]

    # ----- parsing and ids
    @property
    def id(self) -> str:
        return f"{self.aspect}@{self.resolution}"

    @classmethod
    def parse(cls, aspect=None, resolution=None) -> "Frame":
        """Lenient: anything unknown falls back to the default (16:9, 1080p). Accepts '9:16', '9x16', 'vertical', '720', 720, '2160p', '4k'."""
        a = str(aspect or "").strip().lower().replace("x", ":").replace("/", ":")
        a = {"vertical": "9:16", "portrait": "9:16", "landscape": "16:9", "square": "1:1", "wide": "16:9"}.get(a, a)
        if a not in ASPECTS:
            a = DEFAULT_ASPECT
        r = str(resolution or "").strip().lower()
        if r in ("720", "720p", "hd"):
            r = "720p"
        elif r in ("1080", "1080p", "fhd", "full hd"):
            r = "1080p"
        elif r in ("2160", "2160p", "4k", "uhd"):
            r = "2160p"
        else:
            r = DEFAULT_RESOLUTION
        return FRAMES.get((a, r)) or cls(a, r)

    @classmethod
    def from_size(cls, width: int, height: int) -> "Frame":
        """The frame matching an exact pixel size; an unknown size gets the closest aspect at the nearest resolution."""
        for (a, r), f in FRAMES.items():
            if (f.width, f.height) == (int(width), int(height)):
                return f
        w, h = max(1, int(width)), max(1, int(height))
        ratio = w / h
        a = min(ASPECTS, key=lambda k: abs(_DESIGN[k][0] / _DESIGN[k][1] - ratio))
        short = min(w, h)
        return cls.parse(a, "720p" if short < 900 else "1080p" if short < 1620 else "2160p")


FRAMES: Dict[Tuple[str, str], Frame] = {(a, r): Frame(a, r) for a in ASPECTS for r in RESOLUTIONS}
DEFAULT_FRAME = FRAMES[(DEFAULT_ASPECT, DEFAULT_RESOLUTION)]
