"""`slide`: one slide of an uploaded deck, shown whole (never cropped) over a blurred, darkened, enlarged copy of itself, so it fills every aspect without bars.

Only the deck-to-video path uses it (docs/DECK_TO_VIDEO.md): the planner writes the beat, the converter made the picture (`asset`), the director never sees it
(`hidden`). Motion: the whole slide first, then, when the beat has a `focus` zone (normalised box from the slide-understanding step), a small push toward that zone that
always keeps the whole zone in view, and the rest of the slide is dimmed (a spotlight), so nothing is cropped away to make the point; with no zone a very slow push so a long beat is never a still. Bullets cannot appear one by one: the slide is a picture, its
final state (animations in the deck are ignored); the focus move and the burned-in captions carry the pacing instead.
"""
import math
import re
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageFilter

from ...canvas import with_alpha
from ...easing import ease_in_out_cubic, ease_out_cubic, progress
from ...theme import Theme
from ..base import SceneCtx
from ..registry import Element

Props = Dict[str, Any]

MAX_ZOOM = 1.08                 # a gentle push: the far edge of the slide loses at most about 4 percent, inside any slide's own margin. The focus is carried by the spotlight, not by cropping
SPOTLIGHT = 0.5                 # how much the rest of the slide is dimmed while a zone is discussed
ZONE_PAD = 0.05                 # margin kept around a focus zone (share of the slide)
MIN_ZONE, MAX_ZONE_AREA = 0.10, 0.80   # a zone narrower than 10% of the slide, or covering most of it, is not worth a move
_ASSET_RE = re.compile(r"^generation/v2/[0-9a-f-]{36}/assets/[A-Za-z0-9_./-]{1,120}$")


def _s(x: Any, n: int) -> str:
    if x is None or isinstance(x, (dict, list, tuple, set)):
        return ""
    t = "".join(c for c in str(x) if unicodedata.category(c) not in ("Cc", "Cf") or c in "\n\t")
    return re.sub(r"\s+", " ", t).strip()[:n].rstrip()


def clean_zone(z: Any) -> Optional[List[float]]:
    """[x0, y0, x1, y1] as fractions of the slide, or None for anything unusable (wrong shape, NaN, too small, nearly the whole slide)."""
    if not isinstance(z, (list, tuple)) or len(z) != 4 or any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in z):
        return None
    x0, y0, x1, y1 = (min(1.0, max(0.0, float(v))) for v in z)
    if x1 < x0:
        x0, x1 = x1, x0
    if y1 < y0:
        y0, y1 = y1, y0
    if x1 - x0 < MIN_ZONE or y1 - y0 < MIN_ZONE or (x1 - x0) * (y1 - y0) > MAX_ZONE_AREA:
        return None
    return [round(x0, 4), round(y0, 4), round(x1, 4), round(y1, 4)]


def sanitize(p: Props) -> Props:
    asset = _s(p.get("asset"), 200)
    if not asset:
        raise ValueError("slide needs an asset")
    if not (_ASSET_RE.match(asset) or asset.startswith("assets/")):   # real keys live under the video's own assets/; samples use a relative name
        raise ValueError("slide asset must be one of the video's own assets")
    out: Props = {"asset": asset, "title": _s(p.get("title"), 90), "alt": _s(p.get("alt"), 240)}
    zone = clean_zone(p.get("focus"))
    if zone:
        out["focus"] = zone
        if _s(p.get("focus_label"), 60):
            out["focus_label"] = _s(p.get("focus_label"), 60)
    n = p.get("n")
    if isinstance(n, int) and not isinstance(n, bool) and 0 < n < 1000:
        out["n"] = n
    return out


def cues(props: Props, dur: float) -> List[float]:
    return []


_BG: Dict[Tuple[int, int, int], Image.Image] = {}


def _backdrop(src: Image.Image, tw: int, tht: int, th: Theme) -> Image.Image:
    """The slide enlarged to cover the frame, blurred and darkened (cached per picture and frame size). Built from a tiny copy: it is blurred anyway."""
    key = (id(src), tw, tht)
    hit = _BG.get(key)
    if hit is not None:
        return hit
    small = src.convert("RGB").resize((64, max(1, round(64 * src.height / src.width))), Image.BILINEAR)
    k = max(tw / small.width, tht / small.height)
    cw, ch = tw / k, tht / k
    box = ((small.width - cw) / 2, (small.height - ch) / 2, (small.width + cw) / 2, (small.height + ch) / 2)
    bg = small.resize((max(2, tw // 4), max(2, tht // 4)), Image.BICUBIC, box=box).filter(ImageFilter.GaussianBlur(max(2, tw // 160))).resize((tw, tht), Image.BILINEAR)
    base = Image.new("RGB", (tw, tht), th.bg_top)
    bg = Image.blend(bg, base, 0.35).point(lambda v: int(v * 0.55))   # darkened, tinted toward the theme
    if len(_BG) >= 6:
        _BG.pop(next(iter(_BG)))
    _BG[key] = bg
    return bg


def window(ctx: SceneCtx) -> Tuple[float, float, float, float]:
    """The part of the frame the slide may use (design units): wider and a little taller than other scenes' content box, because the slide is the content; the captions
    stay where they always are."""
    fr = ctx.frame
    x0, y0, x1, y1 = ctx.box
    if fr.landscape:
        return 90.0, 30.0, fr.W - 90.0, min(fr.H - 20.0, y1 + (55.0 if ctx.captions else 20.0))
    return 36.0, float(y0), fr.W - 36.0, float(y1 + (30.0 if ctx.captions else 0.0))


def camera(props: Props, lt: float, dur: float, sw: int, sh: int, win_w: float, win_h: float) -> Tuple[float, float, float]:
    """(zoom, cx, cy): zoom relative to the slide fitted to the window, centre as fractions of the slide. With a zone the push is small and the centre moves only as far as
    keeps the whole zone in view."""
    zone = props.get("focus")
    if not zone:
        return 1.0 + 0.035 * ease_in_out_cubic(progress(lt, 0.0, max(dur, 1.0))), 0.5, 0.5
    zx0, zy0, zx1, zy1 = zone
    fit = min(win_w / sw, win_h / sh)
    zw, zh = (zx1 - zx0 + 2 * ZONE_PAD) * sw * fit, (zy1 - zy0 + 2 * ZONE_PAD) * sh * fit
    z = max(1.0, min(MAX_ZOOM, win_w / zw, win_h / zh))
    p = ease_in_out_cubic(progress(lt, zone_start(dur), min(1.4, max(0.6, 0.12 * dur))))
    zz = 1.0 + (z - 1.0) * p
    vw, vh = win_w / (fit * zz * sw), win_h / (fit * zz * sh)     # the view as fractions of the slide
    def centre(lo: float, hi: float, v: float, want: float) -> float:
        if v >= 1.0:
            return 0.5
        return min(max(want, hi - v / 2), lo + v / 2)             # keeps [lo, hi] inside [c - v/2, c + v/2]
    cx = centre(zx0, zx1, vw, 0.5 + ((zx0 + zx1) / 2 - 0.5) * 0.6)
    cy = centre(zy0, zy1, vh, 0.5 + ((zy0 + zy1) / 2 - 0.5) * 0.6)
    return zz, 0.5 + (cx - 0.5) * p, 0.5 + (cy - 0.5) * p


def zone_start(dur: float) -> float:
    return min(1.8, 0.2 * dur)


def _spotlight(img: Image.Image, zone: List[float], crop, src_size: Tuple[int, int], ss: int, amount: float) -> Image.Image:
    """The picture with everything outside the zone (padded) dimmed by `amount`, with a soft edge. The zone is mapped from slide fractions to this picture's pixels."""
    if amount <= 0.01:
        return img
    sw_src = img.width / max(1e-9, (crop[2] - crop[0]))          # picture pixels per source pixel (= s)
    pad = ZONE_PAD * 0.6
    x0 = ((zone[0] - pad) * src_size[0] - crop[0]) * sw_src
    x1 = ((zone[2] + pad) * src_size[0] - crop[0]) * sw_src
    y0 = ((zone[1] - pad) * src_size[1] - crop[1]) * sw_src
    y1 = ((zone[3] + pad) * src_size[1] - crop[1]) * sw_src
    k = 8
    m = Image.new("L", (max(2, img.width // k), max(2, img.height // k)), int(255 * amount))
    from PIL import ImageDraw
    ImageDraw.Draw(m).rectangle([x0 / k, y0 / k, x1 / k, y1 / k], fill=0)
    m = m.filter(ImageFilter.GaussianBlur(max(2, 6 * ss // 2))).resize(img.size, Image.BILINEAR)
    return Image.composite(Image.new("RGB", img.size, (0, 0, 0)), img, m)


def draw(cv, props: Props, lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    from ..viz_scenes import _placeholder

    src: Optional[Image.Image] = ctx.resolve_image(str(props.get("asset", ""))) if props.get("asset") else None
    if src is None:
        _placeholder(cv, th, ctx, str(props.get("title") or props.get("alt") or "Slide unavailable"))
        x0, y0, x1, y1 = window(ctx)
        cv.rrect(x0 + 60, y1 - 40, (x1 - x0 - 120) * progress(lt, 0.0, max(dur, 1.0)), 8, 4, fill=th.accent)   # the picture is missing: a calm card with a progress line, never a blank or broken frame
        return
    ss = cv.ss
    tw, tht = cv.W * ss, cv.H * ss
    cv.im.paste(_backdrop(src, tw, tht, th))
    x0, y0, x1, y1 = window(ctx)
    ww, wh = (x1 - x0) * ss, (y1 - y0) * ss
    sw, sh = src.size
    z, cx, cy = camera(props, lt, dur, sw, sh, ww, wh)
    s = min(ww / sw, wh / sh) * z                      # output pixels per source pixel
    vw, vh = ww / s, wh / s                            # the part of the source the window shows
    mx = sw / 2 if vw >= sw else min(max(cx * sw, vw / 2), sw - vw / 2)
    my = sh / 2 if vh >= sh else min(max(cy * sh, vh / 2), sh - vh / 2)
    sx0, sy0 = mx - vw / 2, my - vh / 2
    crop = (max(0.0, sx0), max(0.0, sy0), min(float(sw), sx0 + vw), min(float(sh), sy0 + vh))
    dw, dh = max(2, round((crop[2] - crop[0]) * s)), max(2, round((crop[3] - crop[1]) * s))
    dx, dy = round(x0 * ss + (crop[0] - sx0) * s), round(y0 * ss + (crop[1] - sy0) * s)
    a_in = ease_out_cubic(progress(lt, 0.0, 0.45))
    if z <= 1.0 + 1e-6 or dw < ww or dh < wh:   # a soft edge around the slide while its whole border is visible
        cv.shadow(dx / ss, dy / ss, dw / ss, dh / ss, 6, blur=18, dy=8, alpha=0.5 * a_in)
    img = src.resize((dw, dh), Image.BILINEAR if s > 0.5 else Image.LANCZOS, box=crop).convert("RGB")
    if props.get("focus"):
        img = _spotlight(img, props["focus"], crop, (sw, sh), ss, SPOTLIGHT * ease_in_out_cubic(progress(lt, zone_start(dur), 0.9)))
    if a_in < 0.999:
        region = cv.im.crop((dx, dy, dx + dw, dy + dh))
        img = Image.blend(region, img, a_in)
    cv.im.paste(img, (dx, dy))


ELEMENTS = [
    Element(
        name="slide", family="Media",
        doc=("- slide: {asset, title (<=90), alt (<=240), focus: optional [x0,y0,x1,y1] fractions of the slide}. One slide of the person's own deck, shown whole over a blurred copy of "
             "itself. Used only by the deck-to-video path; never choose it yourself."),
        sanitize=sanitize, draw=draw, cues=cues, hidden=True,
        formats=("16:9", "9:16", "1:1", "4:5"),
        samples=[
            {"asset": "assets/deck/slide_001.png", "title": "Revenue by year", "alt": "A column chart of revenue growing each year"},
            {"asset": "assets/deck/slide_002.png", "title": "Store economics", "alt": "A table of store formats", "focus": [0.1, 0.2, 0.9, 0.6], "focus_label": "payback column", "n": 2},
        ],
    ),
]
