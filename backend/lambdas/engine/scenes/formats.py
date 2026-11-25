"""Which scene types are laid out natively for which frame shape, the framed fallback for the rest, and what the director is told about it.

A scene type is NATIVE for an aspect when its draw function lays out in design units from `ctx.frame` (docs/RESPONSIVE_LAYOUT.md) and its tag (`formats`) lists
that aspect. Every other scene still renders, never failing and never blank: `draw_framed` draws it at its landscape design size on an offscreen canvas and places
it, scaled to the width, as a rounded card on the themed background of the real frame.
"""
import functools
from typing import Any, Dict, Iterable, List, Sequence, Tuple, Union

from PIL import Image, ImageDraw

from ..canvas import Canvas
from ..frame import DEFAULT_FRAME, MIN_READABLE_PX, Frame
from .base import SceneCtx

ALL_ASPECTS: Tuple[str, ...] = ("16:9", "9:16", "1:1", "4:5")
# The ten built-in scene types (scenes/text_scenes.py, viz_scenes.py, list_scenes.py, flow_scenes.py) are laid out natively for every aspect.
BUILTIN_FORMATS: Dict[str, Tuple[str, ...]] = {t: ALL_ASPECTS for t in ("title", "bullets", "diagram", "chart", "timeline", "stat", "quote", "image", "clip", "gallery")}


def formats_of(stype: str) -> Tuple[str, ...]:
    """The aspects a scene type lays out natively (registry elements: `Element.formats`, default ("16:9",))."""
    from .registry import ELEMENTS

    el = ELEMENTS.get(stype)
    if el is not None:
        return tuple(el.formats)
    return BUILTIN_FORMATS.get(stype, ("16:9",))


def is_native(stype: str, frame: Frame) -> bool:
    return frame.aspect in formats_of(stype)


def scenes_for(frame: Frame) -> Dict[str, List[str]]:
    """{'native': [...], 'framed': [...]}: every known scene type, sorted, split by whether it is laid out natively for this frame."""
    from . import SCENES

    native, framed = [], []
    for t in sorted(SCENES):
        (native if is_native(t, frame) else framed).append(t)
    return {"native": native, "framed": framed}


def format_scene_hint(frame: Frame) -> str:
    """One line for the director's prompt (empty for a frame where everything is native)."""
    sf = scenes_for(frame)
    if not sf["framed"]:
        return ""
    return (f"Format {frame.aspect} ({frame.orientation}): prefer these scene types, laid out for this shape: {', '.join(sf['native'])}. "
            f"These are shown small inside a frame here, use them only when nothing else fits: {', '.join(sf['framed'])}.")


def check_scene_formats(frame: Frame, scenes: Iterable[Union[str, Dict[str, Any]]]) -> List[str]:
    """Warnings (never changes or drops anything) for scenes that will be shown framed in this format. `scenes`: scene type strings, or plan beats
    ({'scene': {'type': ...}}) or timeline scenes ({'type': ...})."""
    out: List[str] = []
    if frame.landscape:
        return out
    for i, s in enumerate(scenes):
        t = s if isinstance(s, str) else str(((s.get("scene") or s) if isinstance(s, dict) else {}).get("type") or "")
        if t and not is_native(t, frame):
            out.append(f"scene {i + 1} ({t}) has no native {frame.aspect} layout: it is shown framed and small")
    return out


# ----------------------------------------------------------------------------- the framed fallback
@functools.lru_cache(maxsize=16)
def _round_mask(w: int, h: int, r: int) -> Image.Image:
    m = Image.new("L", (w * 2, h * 2), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w * 2 - 1, h * 2 - 1], r * 2, fill=255)
    return m.reduce(2)


def framed_geometry(frame: Frame, captions: bool = True) -> Tuple[float, float, float, float, float]:
    """(x, y, w, h, scale) of the landscape card inside a non-landscape frame (design units)."""
    x0, y0, x1, y1 = frame.box(captions)
    pad = max(36, frame.margin_x * 0.5)
    w = frame.W - 2 * pad
    s = w / DEFAULT_FRAME.W
    h = DEFAULT_FRAME.H * s
    cy = (y0 + y1) / 2
    return pad, cy - h / 2, w, h, s


def draw_framed(cv: Canvas, fn, props: Dict[str, Any], lt: float, dur: float, th, ctx: SceneCtx, bg_t: float = 0.0, ambience: bool = True) -> Dict[str, Any]:
    """Draws `fn` (a landscape-only scene) as a card inside `cv`'s frame. Returns {'scale', 'min_text_px', 'readable'} for the preview report."""
    land = SceneCtx(resolve_image=ctx.resolve_image, resolve_clip=ctx.resolve_clip, captions=False, frame=DEFAULT_FRAME)   # captions live outside the card
    off = Canvas(DEFAULT_FRAME.W, DEFAULT_FRAME.H, ss=cv.ss)
    off.background(th, bg_t, ambience=ambience)
    fn(off, props, lt, dur, th, land)
    x, y, w, h, s = framed_geometry(ctx.frame, ctx.captions)
    ss = cv.ss
    pw, ph = int(round(w * ss)), int(round(h * ss))
    card = off.im.resize((pw, ph), Image.BOX)
    r = 26
    cv.shadow(x, y, w, h, r, blur=26, dy=14, alpha=th.shadow_alpha)
    cv.im.paste(card, (int(round(x * ss)), int(round(y * ss))), _round_mask(pw, ph, int(round(r * ss))))
    cv.rrect(x, y, w, h, r, outline=(*th.card_outline[:3], 120), width=1.5)
    eff = (off.min_font if off.min_font < 1e8 else 99.0) * s
    return {"scale": round(s, 3), "min_text_px": round(eff, 1), "readable": eff >= MIN_READABLE_PX}
