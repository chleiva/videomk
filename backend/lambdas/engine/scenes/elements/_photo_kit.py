"""Shared helpers of the Photos elements (`photo_collage`, `photo_frame`, `chapter_card`): sprites of the user's photos (cached), the blurred backdrop,
the lower-third label and the date chip. Everything here is pure: caches are keyed on the asset key, the identity of the decoded image and the sizes, so a
frame costs a few pastes and nothing is decoded, resized or blurred twice.

Units: functions named `*_px` or taking `w`/`h` for sprites work in supersampled pixels (logical * cv.ss); drawing helpers take logical coordinates."""
import re
import zlib
from collections import OrderedDict
from functools import lru_cache
from typing import Any, Callable, Dict, List, NamedTuple, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter

from ...canvas import Canvas, with_alpha
from ...easing import ease_out_cubic, progress
from ...theme import Theme
from ._pm_text import clean

ID_RE = re.compile(r"^P\d{1,3}$")
ORIENTATIONS = ("landscape", "portrait", "square")
DEFAULT_RATIOS = (1.5, 0.75, 1.333, 1.0, 1.5, 0.8, 1.777, 1.25, 0.75)    # the shapes of the placeholder tiles (a photo is not there yet)


# ----------------------------------------------------------------------------------------------------------------------------- props
def photo_id(x: Any) -> str:
    s = str(x if x is not None else "").strip().upper()
    return s if ID_RE.match(s) else ""


def id_list(raw: Any, limit: int) -> List[str]:
    if isinstance(raw, str):
        raw = re.split(r"[,\s]+", raw)
    out: List[str] = []
    for x in (raw if isinstance(raw, (list, tuple)) else []):
        i = photo_id(x)
        if i and i not in out:
            out.append(i)
    return out[:limit]


def num(x: Any, lo: float, hi: float, default: float) -> float:
    try:
        f = float(x)
    except (TypeError, ValueError):
        return default
    if f != f:
        return default
    return max(lo, min(hi, f))


def ratio_of(item: Dict[str, Any]) -> float:
    w, h = num(item.get("w"), 0, 1e6, 0), num(item.get("h"), 0, 1e6, 0)
    return round(max(0.2, min(5.0, w / h)), 4) if w > 0 and h > 0 else 1.0


def orientation_of(r: float) -> str:
    return "landscape" if r > 1.12 else "portrait" if r < 0.89 else "square"


def jitter(seed: str, k: int = 0) -> float:
    """A deterministic number in [-1, 1] from a string (the photo ids), so a layout looks the same on every render."""
    return (zlib.crc32(f"{seed}:{k}".encode()) % 20011) / 10005.5 - 1.0


# ----------------------------------------------------------------------------------------------------------------------------- caches
_CACHE: "OrderedDict[Any, Any]" = OrderedDict()
_LIMIT = 96


def cached(key: Any, build: Callable[[], Any], pin: Any = None) -> Any:
    """A small LRU. `pin` (the decoded source image) is kept next to the value so its id() in the key cannot be reused while the entry lives."""
    hit = _CACHE.get(key)
    if hit is not None:
        _CACHE.move_to_end(key)
        return hit[1]
    val = build()
    _CACHE[key] = (pin, val)
    while len(_CACHE) > _LIMIT:
        _CACHE.popitem(last=False)
    return val


def sid(src: Optional[Image.Image]) -> Tuple[int, Tuple[int, int]]:
    return (id(src), src.size) if src is not None else (0, (0, 0))


class Sprite(NamedTuple):
    rgb: Image.Image
    a: Image.Image

    @property
    def w(self) -> int:
        return self.rgb.width

    @property
    def h(self) -> int:
        return self.rgb.height


def sprite_of(rgba: Image.Image) -> Sprite:
    return Sprite(rgba.convert("RGB"), rgba.getchannel("A"))


def blit(cv: Canvas, sp: Sprite, cx: float, cy: float, scale: float = 1.0, alpha: float = 1.0) -> None:
    """Paste a sprite centred on logical (cx, cy), optionally scaled and faded."""
    if alpha <= 0.004 or scale <= 0.01:
        return
    rgb, a = sp.rgb, sp.a
    if abs(scale - 1.0) > 0.003:
        size = (max(1, int(round(sp.w * scale))), max(1, int(round(sp.h * scale))))
        rgb, a = rgb.resize(size, Image.BILINEAR), a.resize(size, Image.BILINEAR)
    if alpha < 0.996:
        k = int(alpha * 256)
        a = a.point(lambda v: v * k >> 8)
    cv.im.paste(rgb, (int(round(cx * cv.ss - rgb.width / 2)), int(round(cy * cv.ss - rgb.height / 2))), a)


# ----------------------------------------------------------------------------------------------------------------------------- image fitting
def _resize(img: Image.Image, w: int, h: int, box=None) -> Image.Image:
    return img.resize((max(1, w), max(1, h)), Image.LANCZOS if (w < img.width and box is None) else Image.BICUBIC, box=box, reducing_gap=2.5)


def cover(src: Image.Image, w: int, h: int, focus: float = 0.38) -> Image.Image:
    """Fill w x h, cropping the excess; the crop leans towards the top (faces) when height is cut."""
    sw, sh = src.size
    s = max(w / sw, h / sh)
    cw, ch = w / s, h / s
    x0 = (sw - cw) / 2
    y0 = (sh - ch) * focus
    return _resize(src, w, h, box=(max(0.0, x0), max(0.0, y0), min(float(sw), x0 + cw), min(float(sh), y0 + ch)))


def contain(src: Image.Image, w: int, h: int) -> Image.Image:
    """The whole photo, as large as fits inside w x h (never cropped)."""
    s = min(w / src.width, h / src.height)
    return _resize(src, int(round(src.width * s)), int(round(src.height * s)))


def blur_fill(src: Image.Image, w: int, h: int, dark: float = 0.6) -> Image.Image:
    """w x h filled with a blurred, darkened enlargement of the photo (cheap: blurred at a small size)."""
    k = 14
    sw, sh = max(8, w // k), max(8, h // k)
    small = cover(src, sw, sh, 0.5).filter(ImageFilter.GaussianBlur(2.2))
    small = small.point(lambda v: int(v * dark))
    return small.resize((w, h), Image.BICUBIC)


def tile_image(src: Image.Image, w: int, h: int) -> Image.Image:
    """A photo in a w x h cell: cropped to fill when the cell is about its shape, else shown whole over a blurred copy of itself (no face is ever cut off)."""
    mismatch = max((w / h) / (src.width / src.height), (src.width / src.height) / (w / h))
    if mismatch <= 1.3:
        return cover(src, w, h)
    bg = blur_fill(src, w, h)
    fg = contain(src, w, h)
    bg.paste(fg, ((w - fg.width) // 2, (h - fg.height) // 2))
    return bg


@lru_cache(maxsize=64)
def _round_mask(w: int, h: int, r: int) -> Image.Image:
    m = Image.new("L", (w * 2, h * 2), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, w * 2 - 1, h * 2 - 1], r * 2, fill=255)
    return m.reduce(2)


def rounded(img: Image.Image, r: int) -> Image.Image:
    out = img.convert("RGBA")
    out.putalpha(_round_mask(img.width, img.height, max(0, min(r, img.width // 2, img.height // 2))))
    return out


def shadowed(rgba: Image.Image, blur: int, dy: int, alpha: float, spread: int = 0) -> Image.Image:
    """The sprite on a bigger transparent canvas with a soft drop shadow under it; the photo stays at the centre."""
    pad = int(blur * 2.4) + abs(dy) + spread
    w, h = rgba.width + 2 * pad, rgba.height + 2 * pad
    q = 4
    mask = Image.new("L", (w // q + 2, h // q + 2), 0)
    mask.paste(rgba.getchannel("A").reduce(q), (pad // q, (pad + dy) // q))
    mask = mask.filter(ImageFilter.GaussianBlur(max(1.0, blur / q))).resize((w // q * q + 2 * q, h // q * q + 2 * q), Image.BILINEAR).crop((0, 0, w, h))
    mask = mask.point(lambda v: int(v * alpha))
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.putalpha(mask)
    out.alpha_composite(rgba, (pad, pad))
    return out


def rotated(rgba: Image.Image, angle: float) -> Image.Image:
    return rgba.rotate(angle, resample=Image.BICUBIC, expand=True) if abs(angle) > 0.05 else rgba


def placeholder(w: int, h: int, th: Theme, idx: int) -> Image.Image:
    """A neutral stand-in for a photo that is not there (yet): a soft two-tone panel with a small landscape glyph. Same shape as the photo would have."""
    def build() -> Image.Image:
        a, b = (th.accent, th.accent2) if idx % 2 == 0 else (th.accent2, th.accent)
        t = Image.new("RGB", (2, 2))
        top = tuple(int(th.bg_top[i] * 0.55 + a[i] * 0.45) for i in range(3))
        bot = tuple(int(th.bg_bottom[i] * 0.55 + b[i] * 0.45) for i in range(3))
        t.putdata([top, top, bot, bot])
        im = t.resize((w, h), Image.BILINEAR)
        d = ImageDraw.Draw(im, "RGBA")
        u = min(w, h) / 10
        cx, cy = w / 2, h / 2
        glyph = (255, 255, 255, 120)
        d.polygon([(cx - 3.2 * u, cy + 2 * u), (cx - 1.1 * u, cy - 1.0 * u), (cx + 0.2 * u, cy + 0.8 * u), (cx + 1.2 * u, cy - 0.4 * u), (cx + 3.2 * u, cy + 2 * u)], fill=glyph)
        d.ellipse([cx + 1.6 * u, cy - 2.4 * u, cx + 2.6 * u, cy - 1.4 * u], fill=glyph)
        return im
    return cached(("ph", w, h, th.name, idx % 2), build)


def photo_tile(src: Optional[Image.Image], w: int, h: int, th: Theme, idx: int) -> Image.Image:
    """The photo (or the placeholder) as a w x h RGB image, cached."""
    if src is None:
        return placeholder(w, h, th, idx)
    return cached(("tile", sid(src), w, h), lambda: tile_image(src, w, h), pin=src)


def fit_photo(src: Optional[Image.Image], w: int, h: int, th: Theme, idx: int) -> Image.Image:
    """The photo shown whole at exactly w x h (the caller has already chosen a w x h with the photo's shape), or the placeholder."""
    if src is None:
        return placeholder(w, h, th, idx)
    return cached(("fit", sid(src), w, h), lambda: _resize(src, w, h), pin=src)


# ----------------------------------------------------------------------------------------------------------------------------- backdrop
@lru_cache(maxsize=8)
def _grad(w: int, h: int, top: Tuple[int, ...], bottom: Tuple[int, ...]) -> Image.Image:
    col = Image.new("RGB", (1, 2))
    col.putdata([top, bottom])
    return col.resize((w, h), Image.BILINEAR)


def backdrop(cv: Canvas, src: Optional[Image.Image], th: Theme, dark: float = 0.42, mix: float = 0.84, blur: float = 3.0, wash: bool = True) -> bool:
    """Paste a heavily blurred, darkened enlargement of `src` over the theme background (it replaces the ambient glow). Cached per photo and size.
    Dark themes: the photo darkened and mixed with the theme gradient. Paper: the photo washed out towards the paper colour. Returns False when there is no photo."""
    if src is None:
        return False
    W, H = cv.W * cv.ss, cv.H * cv.ss

    def build() -> Image.Image:
        k = 12
        sw, sh = W // k, H // k
        small = cover(src, sw, sh, 0.45).filter(ImageFilter.GaussianBlur(blur))
        base = _grad(sw, sh, th.bg_top, th.bg_bottom)
        if th.name == "paper" and wash:                                  # a light theme: a pastel wash of the photo, still readable under dark text and under the dark label
            small = Image.blend(base, small, 0.42)
            small = small.point(lambda v: int(v * 0.97))
        else:
            small = Image.blend(base, small.point(lambda v: int(v * dark)), mix)
        # a soft vignette keeps the edges calm so the layout, not the background, is the focus
        vig = Image.new("L", (sw, sh), 0)
        ImageDraw.Draw(vig).ellipse([-sw * 0.25, -sh * 0.35, sw * 1.25, sh * 1.35], fill=255)
        vig = vig.filter(ImageFilter.GaussianBlur(sw / 8))
        edge = Image.new("RGB", (sw, sh), tuple(th.bg_top))
        small = Image.composite(small, Image.blend(small, edge, 0.5), vig)
        return small.resize((W, H), Image.BICUBIC)
    cv.im.paste(cached(("bd", sid(src), W, H, th.name, dark, mix, wash), build, pin=src))
    return True


# ----------------------------------------------------------------------------------------------------------------------------- label and chip
def label_metrics(cv: Canvas, title: str, subtitle: str, max_w: float) -> Optional[Dict[str, Any]]:
    """Size of the lower-third label (None when there is no text)."""
    if not title and not subtitle:
        return None
    inner = max_w - 56
    tsize, tlines = (0, [])
    if title:
        tsize = 46
        while tsize > 34 and cv.measure(title, "bold", tsize) > inner:
            tsize -= 4
        tlines = cv.wrap(title, "bold", tsize, inner)[:2]
    ssize, slines = (0, [])
    if subtitle:
        ssize = 28
        slines = cv.wrap(subtitle, "regular", ssize, inner)[:2]
    tw = max([cv.measure(l, "bold", tsize) for l in tlines] + [cv.measure(l, "regular", ssize) for l in slines] + [200.0])
    h = 18 + len(tlines) * tsize * 1.2 + (6 if tlines and slines else 0) + len(slines) * ssize * 1.3 + 18
    return {"w": min(max_w, tw + 56 + 8), "h": h, "tsize": tsize, "tlines": tlines, "ssize": ssize, "slines": slines}


def draw_label(cv: Canvas, th: Theme, m: Dict[str, Any], lt: float, x: float, bottom: float, t0: float = 0.45) -> None:
    """The lower-third: a dark card with an accent bar that grows, the title, the subtitle. Slides in from the left, then holds."""
    p = ease_out_cubic(progress(lt, t0, 0.55))
    if p <= 0.01:
        return
    w, h = m["w"], m["h"]
    x = x - (1 - p) * 60
    y = bottom - h
    cv.shadow(x, y, w, h, 18, blur=18, dy=8, alpha=0.4 * p)
    cv.rrect(x, y, w, h, 18, fill=with_alpha(th.caption_bg, 0.95 * p))
    bar = ease_out_cubic(progress(lt, t0 + 0.12, 0.5))
    cv.rrect(x + 16, y + 16 + (h - 32) * (1 - bar) / 2, 8, (h - 32) * bar, 4, fill=with_alpha(th.accent, p))
    ty = y + 18
    for l in m["tlines"]:
        cv.text(x + 44, ty, l, "bold", m["tsize"], with_alpha(th.caption_text, p))
        ty += m["tsize"] * 1.2
    if m["tlines"] and m["slines"]:
        ty += 6
    for l in m["slines"]:
        cv.text(x + 44, ty, l, "regular", m["ssize"], with_alpha(th.caption_text, 0.78 * p))
        ty += m["ssize"] * 1.3


def chip_metrics(cv: Canvas, text: str) -> Tuple[float, float]:
    return cv.measure(text, "semibold", 30) + 44, 58.0


def draw_chip(cv: Canvas, th: Theme, text: str, lt: float, x: float, y: float, t0: float = 0.6, anchor: str = "l") -> None:
    """A small rounded chip (the date). `x` is its left edge, or its right edge with anchor 'r'; `y` is its bottom."""
    p = ease_out_cubic(progress(lt, t0, 0.45))
    if p <= 0.01 or not text:
        return
    w, h = chip_metrics(cv, text)
    x0 = x - w if anchor == "r" else x
    y0 = y - h + (1 - p) * 14
    cv.rrect(x0, y0, w, h, h / 2, fill=with_alpha(th.accent, 0.95 * p))
    cv.text(x0 + w / 2, y0 + h / 2 + 1, text, "semibold", 30, with_alpha((255, 255, 255), p), anchor="mm")


def spaced_text(cv: Canvas, x: float, y: float, s: str, weight: str, size: float, fill, track: float = 0.16, anchor: str = "l") -> float:
    """Letter-spaced text (small uppercase lines). Returns its width. anchor 'l' draws from x, 'm' centres on x."""
    gap = size * track
    widths = [cv.measure(ch, weight, size) for ch in s]
    total = sum(widths) + gap * max(0, len(s) - 1)
    cx = x - total / 2 if anchor == "m" else x
    for ch, w in zip(s, widths):
        cv.text(cx, y, ch, weight, size, fill, anchor="ls")
        cx += w + gap
    return total


def reveal_schedule(n: int, dur: float, cues: Any, first: float = 0.04, last: float = 0.7, tail: float = 0.7) -> List[float]:
    """Start time of each of n reveals: the narration cues when given (else spread), the first never later than 0.35 s into the scene, all finished before the end."""
    from ...easing import reveal_times
    ts = reveal_times(n, dur, cues, first=first, last=last)
    ts = [min(t, max(0.0, dur - tail)) for t in ts]
    if ts:
        ts[0] = min(ts[0], 0.35)
    for i in range(1, len(ts)):                                 # never out of order
        ts[i] = max(ts[i], ts[i - 1])
    return ts
