"""Shared kit for the styled `bullets` and `diagram` scenes: accent palettes (checked for contrast on all three themes), cached sprites (gradient cards, circles, soft
shadows, glows), a faint drifting dot grid, text fitting, icon choice, spring reveals and the cleaning of the director's `style`, `accent`, `icon(s)` and `emphasis`.

Everything here is a pure function of its arguments (the renderer is cached by content hash); anything heavy is lru_cached on small integer keys.
"""
import math
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
from PIL import Image, ImageChops, ImageDraw

from ..canvas import Canvas, _shadow_sprite, with_alpha
from ..easing import ease_in_out_cubic, ease_out_back, ease_out_cubic, progress
from ..theme import Theme

RGB = Tuple[int, int, int]

ACCENTS: Tuple[str, ...] = ("indigo", "coral", "teal", "amber", "emerald", "violet", "rose", "sky")
ACCENT_CHOICES: Tuple[str, ...] = ACCENTS + ("auto",)
LIST_STYLES: Tuple[str, ...] = ("rail", "spotlight", "icons", "cards", "keywords")
FLOW_STYLES: Tuple[str, ...] = ("cards", "pills", "ladder", "stack")
DEFAULT_LIST_STYLE, DEFAULT_FLOW_STYLE = "rail", "cards"

# name -> (gradient start, gradient end)
_BASE: Dict[str, Tuple[RGB, RGB]] = {
    "indigo": ((99, 102, 241), (59, 130, 246)),
    "coral": ((255, 99, 71), (255, 159, 67)),
    "teal": ((20, 184, 166), (34, 211, 238)),
    "amber": ((245, 158, 11), (249, 115, 22)),
    "emerald": ((22, 163, 74), (132, 204, 22)),
    "violet": ((139, 92, 246), (217, 70, 239)),
    "rose": ((225, 29, 72), (244, 114, 182)),
    "sky": ((14, 165, 233), (99, 102, 241)),
}
_AUTO = {"midnight": "indigo", "paper": "rose", "sunrise": "amber"}   # 'auto' = the theme's own accent, as before (but with a matching second colour)

LEFT, RIGHT = 150, 1770      # content margins (logical px): inside the title-safe area
HEAD_Y, HEAD_SIZE = 104, 70


def lr(fr) -> Tuple[float, float]:
    """Left and right content margins (design units) of a frame (None = the landscape default)."""
    if fr is None or fr.landscape:
        return LEFT, RIGHT
    return float(fr.margin_x), float(fr.W - fr.margin_x)


# ----------------------------------------------------------------------------- colour
def _lin(v: float) -> float:
    v /= 255.0
    return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4


def lum(c: Sequence[int]) -> float:
    return 0.2126 * _lin(c[0]) + 0.7152 * _lin(c[1]) + 0.0722 * _lin(c[2])


def contrast(a: Sequence[int], b: Sequence[int]) -> float:
    la, lb = lum(a), lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def mix(a: Sequence[int], b: Sequence[int], t: float) -> RGB:
    return (int(a[0] + (b[0] - a[0]) * t), int(a[1] + (b[1] - a[1]) * t), int(a[2] + (b[2] - a[2]) * t))


WHITE: RGB = (255, 255, 255)
DARK_INK: RGB = (17, 24, 39)


@dataclass(frozen=True)
class Pal:
    name: str
    c1: RGB                  # fill gradient start (ink is readable on it)
    c2: RGB                  # fill gradient end
    ink: RGB                 # text/icon colour on c1..c2
    accent_text: RGB         # accent used for text and icons on the plain background (>= 4.5:1 against the theme's lightest/darkest background)
    dot: RGB                 # the travelling pulse
    surface: Tuple[int, int, int, int]
    surface_hi: Tuple[int, int, int, int]
    border: Tuple[int, int, int, int]
    track: Tuple[int, int, int, int]
    text: RGB
    ref_bg: RGB
    dark: bool


def _on_fill(c1: RGB, c2: RGB) -> Tuple[RGB, RGB, RGB]:
    """(c1, c2, ink): white ink when a modest darkening of the fills (at most ~30%) makes it read (>= 4.6:1) on both ends of the gradient, else dark ink with
    the fills lightened if needed."""
    w1, w2 = c1, c2
    for k in range(8):
        if contrast(WHITE, w1) >= 4.6 and contrast(WHITE, w2) >= 4.6:
            return w1, w2, WHITE
        w1, w2 = mix(w1, (0, 0, 0), 0.04), mix(w2, (0, 0, 0), 0.04)
    d1, d2 = c1, c2
    for _ in range(40):
        if contrast(DARK_INK, d1) >= 4.6 and contrast(DARK_INK, d2) >= 4.6:
            break
        d1, d2 = mix(d1, WHITE, 0.04), mix(d2, WHITE, 0.04)
    return d1, d2, DARK_INK


@lru_cache(maxsize=64)
def palette(theme_name: str, accent: str, bg_bottom: RGB, text: RGB, dark: bool) -> Pal:
    key = _AUTO.get(theme_name, "indigo") if accent not in _BASE else accent
    c1, c2, ink = _on_fill(*_BASE[key])
    ref = bg_bottom
    at = c1
    toward = WHITE if dark else DARK_INK
    for _ in range(60):
        if contrast(at, ref) >= 4.8:
            break
        at = mix(at, toward, 0.05)
    if dark:
        surf, hi, bd, tr = (255, 255, 255, 18 if theme_name == "midnight" else 24), (255, 255, 255, 36), (255, 255, 255, 46), (255, 255, 255, 34)
    else:
        surf, hi, bd, tr = (255, 255, 255, 238), (255, 255, 255, 255), (31, 41, 55, 30), (31, 41, 55, 40)
    dot = mix(c2, WHITE, 0.55) if dark else mix(c1, DARK_INK, 0.15)
    return Pal(key, c1, c2, ink, at, dot, surf, hi, bd, tr, text, ref, dark)


def pal_for(th: Theme, accent: Any) -> Pal:
    a = str(accent or "auto").lower()
    dark = th.name != "paper"
    return palette(th.name, a if a in _BASE else "auto", tuple(th.bg_bottom), tuple(th.text), dark)


# ----------------------------------------------------------------------------- props: what the director may send
def pick(value: Any, allowed: Sequence[str], default: str) -> str:
    v = str(value or "").strip().lower() if isinstance(value, str) else ""
    return v if v in allowed else default


def list_style(props: Dict[str, Any]) -> str:
    return pick(props.get("style"), LIST_STYLES, DEFAULT_LIST_STYLE)


def flow_style(props: Dict[str, Any]) -> str:
    return pick(props.get("style"), FLOW_STYLES, DEFAULT_FLOW_STYLE)


def emphasis_of(props: Dict[str, Any], n: int) -> Optional[int]:
    e = props.get("emphasis")
    if isinstance(e, bool) or not isinstance(e, int) or not 0 <= e < n:
        return None
    return e


def clean_icon(v: Any) -> str:
    """An icon name (or any English word) -> the resolved icon name of the bundled set, or '' when nothing fits."""
    if not isinstance(v, str) or not v.strip():
        return ""
    from .elements._pm_icons import find_icon

    name, how = find_icon(v.strip()[:40])
    return "" if how == "neutral" else name


def sanitize_style_props(stype: str, p: Dict[str, Any], out: Dict[str, Any], n: int, nodes_in: Optional[List[Any]] = None) -> Dict[str, Any]:
    """Adds the validated optional look props (`style`, `accent`, `emphasis`, and for bullets `icons`) to `out`; anything else is dropped."""
    styles = LIST_STYLES if stype == "bullets" else FLOW_STYLES
    st = pick(p.get("style"), styles, "")
    if st:
        out["style"] = st
    ac = pick(p.get("accent"), ACCENT_CHOICES, "")
    if ac and ac != "auto":
        out["accent"] = ac
    e = p.get("emphasis")
    if isinstance(e, int) and not isinstance(e, bool) and 0 <= e < n:
        out["emphasis"] = e
    if stype == "bullets" and isinstance(p.get("icons"), list):
        icons = [clean_icon(x) for x in p["icons"][:n]]
        if any(icons):
            out["icons"] = icons + [""] * (n - len(icons))
    return out


NUMBER_ICON = "#"   # an "icon" that is the item's number: '#1', '#2' ... (drawn as a bold numeral by `icon`)


def number_icon(i: int) -> str:
    return f"{NUMBER_ICON}{i + 1}"


@lru_cache(maxsize=512)
def match_icon(text: str) -> str:
    """The icon the item's own words name, or '' when the icon set knows none of them (most Spanish items, abstract phrases)."""
    from .elements._pm_icons import find_icon
    from ..sync import content_tokens

    toks = set(content_tokens(text))
    order = {"exact": 0, "synonym": 1, "part": 2}      # tag matches are too loose for an automatic pick (a stray glyph is worse than the fallback)
    cands = []
    for idx, w in enumerate(re.findall(r"[A-Za-z]{3,}", text)):
        if w.lower() not in toks and not any(t.startswith(w.lower()[:4]) for t in toks):
            continue
        name, how = find_icon(w)
        if how in order:
            cands.append((order[how], idx, name))
    return min(cands)[2] if cands else ""


def auto_icon(text: str, k: int) -> str:
    """The icon for an item's text: the first content word the icon set knows, else the item's NUMBER. It used to be a rotating decoration (sparkles, target, lightbulb ...)
    that had nothing to do with the item (docs/QUALITY_REVIEW.md backlog: icon picker no-match); a number is honest and reads as order."""
    return match_icon(text) or number_icon(k)


def _item_text(it: Any) -> str:
    if isinstance(it, dict):
        return str(it.get("text") or it.get("label") or it.get("title") or "")
    return str(it or "")


def _given_icon(props: Dict[str, Any], i: int) -> str:
    icons = props.get("icons")
    return clean_icon(icons[i]) if isinstance(icons, list) and i < len(icons) and icons[i] else ""


NEUTRAL_ICON = "circle-dot"   # the plain marker of an item no icon fits, in a list where most items do have one


def group_icon(found: List[str], i: int) -> str:
    """The icon of item i given what was found for every item of its list ('' = nothing fits). Most items have one: they keep it and the others get a plain marker.
    Fewer than half do: the whole list is numbered (1, 2, 3 ...), never a mix of pictures and numbers and never a decoration that means nothing."""
    if i >= len(found) or sum(1 for f in found if f) * 2 < len(found):
        return number_icon(i)
    return found[i] or NEUTRAL_ICON


def icon_for(props: Dict[str, Any], i: int, text: str) -> str:
    """The icon of item i of a list: the one the writer gave, else the one its words name, else what `group_icon` decides for a list with gaps."""
    items = props.get("items")
    if isinstance(items, list) and items:
        return group_icon([_given_icon(props, j) or match_icon(_item_text(it)) for j, it in enumerate(items)], i)
    return _given_icon(props, i) or auto_icon(text, i)


# ----------------------------------------------------------------------------- motion
def pop(lt: float, t0: float, dur: float = 0.6, over: float = 1.7) -> Tuple[float, float]:
    """(fade 0..1, spring 0..~1.05): a quick fade and an ease-out-back with a short overshoot."""
    return ease_out_cubic(progress(lt, t0, dur * 0.5)), ease_out_back(progress(lt, t0, dur), over)


def focus(times: Sequence[float], lt: float, i: int, fade: float = 0.4) -> float:
    """1 while item i is the one being narrated, easing in when it appears and out when the next one comes."""
    up = ease_out_cubic(progress(lt, times[i], fade))
    if i + 1 < len(times):
        up *= 1.0 - ease_in_out_cubic(progress(lt, times[i + 1], 0.5))
    return up


def clamp_first(times: List[float], first: float = 1.0) -> List[float]:
    """A scene never sits bare: when the narrator reaches the first part late, it still comes up by `first` s (the rest keep their cues)."""
    t = list(times)
    if t:
        t[0] = min(t[0], first)
        for k in range(1, len(t)):
            t[k] = max(t[k], t[0] + 0.05 * k)
    return t


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


# ----------------------------------------------------------------------------- sprites
def _diag(w: int, h: int, c1: RGB, c2: RGB) -> np.ndarray:
    x = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :]
    y = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    t = (0.65 * x + 0.35 * y)[..., None]
    return (np.array(c1, np.float32) * (1 - t) + np.array(c2, np.float32) * t).astype(np.uint8)


@lru_cache(maxsize=400)
def rr_sprite(w: int, h: int, r: int, fill: Tuple[int, ...], fill2: Optional[Tuple[int, ...]], border: Optional[Tuple[int, ...]], border2: Optional[Tuple[int, ...]], bw: int, ss: int) -> Image.Image:
    """Rounded rectangle as an RGBA sprite at the canvas' pixel density: solid or diagonal-gradient fill, optional (gradient) border. Built at 2x and reduced (anti-aliased)."""
    k = 2 * ss
    W, H = max(2, w * k), max(2, h * k)
    rr = max(0, min(r * k, W // 2, H // 2))
    outer = Image.new("L", (W, H), 0)
    ImageDraw.Draw(outer).rounded_rectangle([0, 0, W - 1, H - 1], rr, fill=255)
    rgb = _diag(W, H, tuple(fill[:3]), tuple((fill2 or fill)[:3]))
    img = Image.fromarray(rgb, "RGB").convert("RGBA")
    fa = fill[3] if len(fill) == 4 else 255
    img.putalpha(outer.point(lambda v: v * fa // 255))
    if border and bw > 0:
        inset = bw * k
        inner = Image.new("L", (W, H), 0)
        ImageDraw.Draw(inner).rounded_rectangle([inset, inset, W - 1 - inset, H - 1 - inset], max(0, rr - inset), fill=255)
        ring = ImageChops.subtract(outer, inner)
        b1 = tuple(border[:3])
        b2 = tuple((border2 or border)[:3])
        ba = border[3] if len(border) == 4 else 255
        layer = Image.fromarray(_diag(W, H, b1, b2), "RGB").convert("RGBA")
        layer.putalpha(ring.point(lambda v: v * ba // 255))
        img = Image.alpha_composite(img, layer)
    return img.reduce(2) if k > 1 else img


def sprite(cv: Canvas, w: float, h: float, r: float, fill, fill2=None, border=None, border2=None, bw: float = 0) -> Image.Image:
    return rr_sprite(int(round(w)), int(round(h)), int(round(r)), tuple(fill), tuple(fill2) if fill2 else None, tuple(border) if border else None,
                     tuple(border2) if border2 else None, int(round(bw)), cv.ss)


def paste_sprite(cv: Canvas, spr: Image.Image, cx: float, cy: float, scale: float = 1.0, alpha: float = 1.0) -> None:
    """Paste an RGBA sprite centred on (cx, cy) (logical px), optionally scaled and faded."""
    if alpha <= 0.01 or scale <= 0.02:
        return
    s = spr
    if abs(scale - 1.0) > 0.004:
        s = s.resize((max(1, int(s.width * scale)), max(1, int(s.height * scale))), Image.BILINEAR)
    a = s.getchannel("A")
    if alpha < 0.995:
        a = a.point(lambda v: int(v * alpha))
    cv.im.paste(s.convert("RGB"), (int(round(cv._s(cx) - s.width / 2)), int(round(cv._s(cy) - s.height / 2))), a)


def soft_shadow(cv: Canvas, x: float, y: float, w: float, h: float, r: float, alpha: float, color: RGB = (0, 0, 0), blur: float = 26, dy: float = 14) -> None:
    """Blurred shadow or glow under a rounded rectangle. The blurred mask is cached at full strength; `alpha` only scales it."""
    if alpha <= 0.01 or w < 4 or h < 4:
        return
    pad = cv._s(blur * 2.5)
    sp = _shadow_sprite(cv._s(w), cv._s(h), cv._s(r), cv._s(blur), 255, pad)
    m = sp.point(lambda v: int(v * alpha))
    cv.im.paste(Image.new("RGB", sp.size, color), (cv._s(x) - pad, cv._s(y + dy) - pad), m)


def icon(cv: Canvas, cx: float, cy: float, name: str, size: float, color, scale: float = 1.0) -> None:
    if name.startswith(NUMBER_ICON) and name[1:].isdigit():   # the item's number in place of a picture (no icon fits the item)
        a = int(color[3]) if len(color) == 4 else 255
        if a > 0 and scale > 0.02:
            cv.text(cx, cy, name[1:], "bold", size * 0.92 * scale, color, anchor="mm")
        return
    from .elements._pm_icons import draw_icon

    draw_icon(cv, cx, cy, name, size, color, scale)


# ----------------------------------------------------------------------------- backdrop: a faint dot grid that drifts, and a soft glow
_GRID = 64


@lru_cache(maxsize=4)
def _grid_mask(ss: int, W: int, H: int, a_dot: int) -> Image.Image:
    P = _GRID * ss
    w, h = W * ss + P, H * ss + P
    yy, xx = np.mgrid[0:h, 0:w]
    dx, dy = (xx % P) - P / 2, (yy % P) - P / 2
    rad = 1.7 * ss
    dots = np.clip(rad + 0.7 - np.sqrt(dx * dx + dy * dy), 0, 1)
    fx, fy = (xx - ss * W / 2) / (ss * W * 0.62), (yy - ss * H * 0.55) / (ss * H * 0.7)
    vig = np.clip(1.15 - np.sqrt(fx * fx + fy * fy), 0, 1)       # strongest in the middle, gone at the edges
    return Image.fromarray((dots * vig * a_dot).astype(np.uint8), "L")


def backdrop(cv: Canvas, th: Theme, pal: Pal, lt: float) -> None:
    """Quiet depth: a dot grid that crawls a few pixels per second (never distracting, never flickering: integer offsets)."""
    m = _grid_mask(cv.ss, cv.W, cv.H, 70 if pal.dark else 56)
    off = int(lt * 3.0) % _GRID * cv.ss
    crop = m.crop((off, off // 2, off + cv.W * cv.ss, off // 2 + cv.H * cv.ss))
    col = (255, 255, 255) if pal.dark else (31, 41, 55)
    cv.im.paste(Image.new("RGB", crop.size, col), (0, 0), crop)


def glow_blob(cv: Canvas, cx: float, cy: float, d: float, color: RGB, alpha: float) -> None:
    from ..canvas import _blob_sprite

    if alpha <= 0.01:
        return
    di = max(64, int(d * cv.ss / 32) * 32)
    blob = _blob_sprite(di, 255).point(lambda v: int(v * alpha))
    cv.im.paste(Image.new("RGB", blob.size, color), (int(cv._s(cx) - blob.width / 2), int(cv._s(cy) - blob.height / 2)), blob)


# ----------------------------------------------------------------------------- text
def fit_lines(cv: Canvas, text: str, weight: str, max_w: float, max_lines: int, start: float, min_size: float = 30, max_h: float = 0.0, lh: float = 1.18) -> Tuple[float, List[str]]:
    """Largest size <= start at which `text` wraps into at most max_lines lines that all fit max_w (and, when max_h is given, a block no taller than max_h)."""
    size = start
    while size > min_size:
        lines = cv.wrap(text, weight, size, max_w)
        if len(lines) <= max_lines and all(cv.measure(l, weight, size) <= max_w for l in lines) and (not max_h or len(lines) * size * lh <= max_h):
            return size, lines
        size -= 2
    lines = cv.wrap(text, weight, min_size, max_w)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and cv.measure(lines[-1] + "…", weight, min_size) > max_w:
            lines[-1] = lines[-1][:-1]
        lines[-1] = lines[-1].rstrip() + "…"
    return min_size, lines


def draw_lines(cv: Canvas, x: float, cy: float, lines: List[str], weight: str, size: float, color, anchor: str = "lm", lh: float = 1.18) -> None:
    """Lines stacked around the vertical centre `cy` (x is the left edge, the centre or the right edge, by anchor's first letter)."""
    h = size * lh
    y0 = cy - (len(lines) - 1) * h / 2
    for i, line in enumerate(lines):
        cv.text(x, y0 + i * h, line, weight, size, color, anchor=anchor)


# ----------------------------------------------------------------------------- heading
def title_block(cv: Canvas, th: Theme, pal: Pal, text: str, lt: float, ctx=None) -> float:
    """Big left-aligned heading with a short gradient bar that draws on. Returns the y below it (content starts there). With `ctx`, it follows the frame:
    margins, a larger size, up to two lines, below the platform's top UI zone."""
    fr = ctx.frame if ctx is not None else None
    land = fr is None or fr.landscape
    left, right = lr(fr)
    if not text:
        return 70.0 if land else float(fr.margin_top + 10)
    p = ease_out_cubic(progress(lt, 0.05, 0.55))
    if land:
        size, lines = fit_lines(cv, text, "bold", right - left, 1, HEAD_SIZE, 44)
        head_y = HEAD_Y
    else:
        size, lines = fit_lines(cv, text, "bold", right - left, 2, HEAD_SIZE * fr.type_scale, 46, lh=1.12)
        head_y = fr.margin_top + HEAD_SIZE * fr.type_scale * 0.95
    for k, line in enumerate(lines):
        cv.text(left, head_y + k * size * 1.12 + (1 - p) * 22, line, "bold", size, with_alpha(th.text, p), anchor="ls")
    bar_y = head_y + (len(lines) - 1) * size * 1.12
    bw = 132 * ease_out_cubic(progress(lt, 0.25, 0.6))
    if bw > 2:
        spr = sprite(cv, 132, 9, 4.5, pal.c1, pal.c2)
        w = int(spr.width * bw / 132)
        if w > 1:
            cv.im.paste(spr.crop((0, 0, w, spr.height)).convert("RGB"), (cv._s(left), cv._s(bar_y + 26)), spr.getchannel("A").crop((0, 0, w, spr.height)))
    return bar_y + 26 + 9 + 34


def area(ctx, y_top: float) -> Tuple[float, float]:
    """The free vertical band for content: below the heading, above the caption band."""
    return y_top, float(ctx.bottom) - 14
