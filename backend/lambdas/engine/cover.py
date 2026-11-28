"""The cover of a video: the one picture that stands for it everywhere it is not playing (docs/SHARE_PREVIEWS_2026-11-28.md).

Why it exists: the first frame of a video is often blank paper (a whiteboard starts empty and the pen draws) or a bare backdrop (the characters and the title
come in after half a second), so every place that uses "a frame" as the preview (a link card, a chat thumbnail, a feed) showed white or nothing.
The cover is designed from the plan instead: the first scene's own art in its SETTLED state (the board with the title and its first drawings, the
presenter and the title panel, the first photograph), the video's title in large type, the VideoMK mark, in the right shape.

Pure Pillow, no ffmpeg and no network: `build(timeline, image_loader)` returns JPEG bytes for
  og   1200x630 (1.91:1): the link-preview card (LinkedIn, WhatsApp, Facebook, X, Slack, iMessage). For a vertical or square video the art sits on the right
       of a title panel, because a 9:16 picture cropped to 1.91:1 would show a stripe of it.
  own  the video's own aspect (long side at most 1280): the poster in the apps and the web player, the thumbnail for a feed.
and the same design is what `Renderer` holds over the first frames of the MP4 when the timeline asks for it (`cover.in_frame`, see renderer.py).

Rules the design follows (each is from the research in the doc): the title is big enough to read at 300 px wide (cap height at least about 6 % of the picture),
white on a dark scrim or ink on paper, never over busy detail without a scrim; the subject stays inside the middle of the picture, so a 1:1 or 4:5 crop of a
9:16 cover keeps the title; the mark is small and in a corner; no fade from black or white; JPEG, the card under 300 KB (WhatsApp ignores larger images).
"""
import hashlib
import io
import json
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFilter

from . import watermark as wm_mod
from .canvas import load_font
from .frame import Frame
from .renderer import Renderer
from .theme import get_theme

OG_W, OG_H = 1200, 630
OWN_LONG_SIDE = 1280
INK = (17, 20, 43)                      # the brand ink (docs/BRAND.md)
SCRIM = (8, 10, 24)
MAX_SETTLE_S = 9.0                      # a long first scene is sampled before it has changed into something else
OG_MAX_BYTES = 280 * 1024               # WhatsApp: a link-preview image above about 300 KB is not shown
OWN_MAX_BYTES = 450 * 1024
TITLE_MAX_LINES = 3

# where the title block's bottom edge sits (share of the picture height) so that a 1:1 or 4:5 crop of the cover and a platform's bottom controls never cover it
_TITLE_BOTTOM = {"16:9": 0.93, "9:16": 0.74, "1:1": 0.90, "4:5": 0.87}
_TITLE_SIZE = {"16:9": 0.092, "9:16": 0.056, "1:1": 0.082, "4:5": 0.068}     # font px as a share of the picture HEIGHT (the og card is separate)
_MARGIN_X = {"16:9": 0.06, "9:16": 0.08, "1:1": 0.08, "4:5": 0.08}


# ----------------------------------------------------------------------------- the art: the first scene, settled
def settle_time(timeline: Dict[str, Any]) -> float:
    """When the first scene looks finished: just before it ends (a scene holds its final state), but not later than MAX_SETTLE_S (a long first scene would have changed)."""
    sc = timeline["scenes"][0]
    return max(0.0, min(float(sc["start"]) + float(sc["duration"]) - 0.05, MAX_SETTLE_S))


def art_timeline(timeline: Dict[str, Any]) -> Dict[str, Any]:
    """The timeline as the art needs it: no captions (the karaoke bar is not part of a cover), no watermark (the cover has its own mark), no closing fade."""
    tl = dict(timeline)
    tl["captions"] = False
    tl["outro"] = False
    tl.pop("watermark", None)
    tl.pop("lead", None)
    tl.pop("cover", None)
    return tl


def render_art(timeline: Dict[str, Any], image_loader: Optional[Callable[[str], Optional[Image.Image]]] = None, clip_loader: Optional[Callable[[str], Any]] = None,
               t: Optional[float] = None) -> Image.Image:
    """The first scene at its settled moment, at the video's own size (RGB)."""
    r = Renderer(art_timeline(timeline), image_loader=image_loader, clip_loader=clip_loader)
    return r.frame_at(settle_time(timeline) if t is None else t)


# ----------------------------------------------------------------------------- small drawing helpers
def _cover_fit(im: Image.Image, w: int, h: int, focus_y: float = 0.5) -> Image.Image:
    """Scales to fill (w, h) and crops; focus_y: where the kept window sits vertically (0 top, 1 bottom)."""
    k = max(w / im.width, h / im.height)
    r = im.resize((max(w, int(round(im.width * k))), max(h, int(round(im.height * k)))), Image.LANCZOS)
    x = (r.width - w) // 2
    y = int(round((r.height - h) * focus_y))
    return r.crop((x, y, x + w, y + h))


def _wrap(text: str, font, max_w: float) -> List[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if font.getlength(trial) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _ellipsize(line: str, font, max_w: float) -> str:
    while line and font.getlength(line + "…") > max_w:
        line = line[:-1].rstrip()
    return line + "…"


def fit_title(title: str, max_w: float, max_h: float, size: int, min_size: int, weight: str = "bold", line_h: float = 1.14) -> Tuple[List[str], Any, int]:
    """(lines, font, size): the largest type from `size` down to `min_size` that puts the whole title in at most TITLE_MAX_LINES lines inside the box; at the
    smallest size a longer title ends with an ellipsis rather than shrinking to nothing."""
    title = " ".join((title or "").split()) or "VideoMK"
    s = size
    while True:
        font = load_font(weight, s)
        lines = _wrap(title, font, max_w)
        if len(lines) <= TITLE_MAX_LINES and len(lines) * s * line_h <= max_h:
            return lines, font, s
        if s <= min_size:
            lines = lines[:TITLE_MAX_LINES]
            while len(lines) > 1 and len(lines) * s * line_h > max_h:
                lines.pop()
            lines[-1] = _ellipsize(lines[-1], font, max_w) if (len(_wrap(title, font, max_w)) > len(lines) or font.getlength(lines[-1]) > max_w) else lines[-1]
            return lines, font, s
        s = max(min_size, int(s * 0.92))


def _mark(width: int, rgb: Tuple[int, int, int], alpha: float = 0.95) -> Image.Image:
    """The VideoMK lockup (mark and word) at the given width, tinted."""
    src = wm_mod._source("lockup")
    h = max(2, int(round(width * src.height / src.width)))
    base = wm_mod._tint(wm_mod._fit(src, width, h), rgb)
    base.putalpha(base.getchannel("A").point(lambda v: int(v * alpha)))
    return base


def _scrim(w: int, h: int, top_frac: float, strength: float = 0.88) -> Image.Image:
    """A dark gradient from transparent at `top_frac` of the height to `strength` opacity at the bottom, smooth (eased), as an RGBA layer."""
    col = Image.new("RGBA", (1, h), SCRIM + (0,))
    px = col.load()
    y0 = int(h * top_frac)
    for y in range(h):
        if y >= y0:
            k = (y - y0) / max(1, h - 1 - y0)
            k = k * k * (3 - 2 * k)
            px[0, y] = SCRIM + (int(255 * strength * k),)
    return col.resize((w, h))


def _draw_text_block(d: ImageDraw.ImageDraw, lines: List[str], font, x: int, y_bottom: int, size: int, fill, line_h: float = 1.14, shadow: bool = False):
    total = int(round(len(lines) * size * line_h))
    y = y_bottom - total
    for ln in lines:
        if shadow:
            d.text((x + max(1, size // 28), y + max(1, size // 28)), ln, font=font, fill=(0, 0, 0, 120))
        d.text((x, y), ln, font=font, fill=fill)
        y += int(round(size * line_h))
    return y_bottom - total


def _is_paper(theme_name: str) -> bool:
    return get_theme(theme_name).name == "paper"


# ----------------------------------------------------------------------------- the designs
def compose(art: Image.Image, title: str, *, aspect: str, theme: str, out_size: Tuple[int, int], title_scale: float = 1.0, layout: Optional[str] = None) -> Image.Image:
    """The art cover-fitted to `out_size` with the title and the mark, for a picture that is (about) the shape of the art: the video's own cover, and the 1.91:1 card of a
    landscape video. layout "scrim" (a photograph: nothing in it is text): white type on a bottom gradient. layout "ribbon" (a scene that carries its own text, drawings or
    panel: a whiteboard, a presenter with its title panel, a chart): the art above, the title on an ink ribbon below, so no type is ever laid over the art's own type."""
    w, h = out_size
    aspect = aspect if aspect in _TITLE_BOTTOM else "16:9"
    wide = w / h >= 1.5
    mx = int(round(w * _MARGIN_X[aspect]))
    size = int(round(h * _TITLE_SIZE[aspect] * title_scale)) if aspect != "16:9" or not wide else int(round(h * (0.105 if h <= 700 else 0.092) * title_scale))
    ribbon = (layout or ("ribbon" if _is_paper(theme) else "scrim")) == "ribbon"
    if ribbon:
        lines, font, size = fit_title(title, w - 2 * mx, h * 0.30, size, max(18, int(size * 0.6)))
        ribbon_h = int(round(len(lines) * size * 1.14 + size * 1.0 + h * 0.035))
        ribbon_h = max(ribbon_h, int(h * 0.20))
        art_h = h - ribbon_h
        base = Image.new("RGB", (w, h), INK)
        # the art above the ribbon: the whole picture scaled to the available height when it is wider than the room, else cover-fitted; kept from the top (the heading)
        base.paste(_cover_fit(art, w, art_h, focus_y=0.30 if _is_paper(theme) else 0.42), (0, 0))
        im = base.convert("RGBA")
        d = ImageDraw.Draw(im)
        d.rectangle((0, art_h, w, h), fill=INK + (255,))
        d.rectangle((0, art_h, w, art_h + max(2, h // 160)), fill=(225, 29, 72, 255))   # the paper theme's accent as a thin rule between the board and the ribbon
        top = art_h + int(h * 0.03)
        _draw_text_block(d, lines, font, mx, top + int(round(len(lines) * size * 1.14)) , size, (255, 255, 255, 255))
        mk = _mark(int(w * (0.17 if aspect == "16:9" else 0.20)), (255, 255, 255))
        im.alpha_composite(mk, (w - mx - mk.width, h - int(h * 0.035) - mk.height))
        return im.convert("RGB")
    im = _cover_fit(art, w, h, focus_y=0.40).convert("RGBA")
    block_bottom = int(h * _TITLE_BOTTOM[aspect])
    lines, font, size = fit_title(title, w - 2 * mx - (int(w * 0.16) if aspect == "9:16" else 0), h * 0.40, size, max(18, int(size * 0.62)))
    top_of_block = block_bottom - int(len(lines) * size * 1.14)
    im.alpha_composite(_scrim(w, h, max(0.18, (top_of_block - size * 1.2) / h)))
    d = ImageDraw.Draw(im)
    _draw_text_block(d, lines, font, mx, block_bottom, size, (255, 255, 255, 255), shadow=True)
    mk = _mark(int(w * (0.16 if wide else 0.22)), (255, 255, 255))
    im.alpha_composite(mk, (mx, int(h * 0.045)))
    return im.convert("RGB")


def og_card(art: Image.Image, title: str, *, aspect: str, theme: str, layout: Optional[str] = None) -> Image.Image:
    """The 1200x630 link-preview card. A landscape video: `compose` at that size. A vertical or square one: a title panel on the left and the art, whole, on the right."""
    if aspect == "16:9" or art.width / art.height >= 1.5:
        return compose(art, title, aspect="16:9", theme=theme, out_size=(OG_W, OG_H), layout=layout)
    th = get_theme(theme)
    paper = _is_paper(theme)
    bg_top, bg_bottom = (th.bg_top, th.bg_bottom) if not paper else (INK, (30, 33, 70))
    card = Image.new("RGB", (OG_W, OG_H))
    px = ImageDraw.Draw(card)
    for y in range(OG_H):   # a plain vertical gradient in the video's own theme colours (paper: the brand ink)
        k = y / (OG_H - 1)
        px.line((0, y, OG_W, y), fill=tuple(int(bg_top[i] + (bg_bottom[i] - bg_top[i]) * k) for i in range(3)))
    pad = 44
    ah = OG_H - 2 * pad
    aw = int(round(ah * art.width / art.height))
    pic = art.resize((aw, ah), Image.LANCZOS)
    mask = Image.new("L", (aw, ah), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, aw - 1, ah - 1), radius=26, fill=255)
    ax = OG_W - pad - aw
    shadow = Image.new("RGBA", (aw + 80, ah + 80), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle((40, 48, 40 + aw, 48 + ah), radius=26, fill=(0, 0, 0, 150))
    card.paste(shadow.filter(ImageFilter.GaussianBlur(18)), (ax - 40, pad - 40), shadow.filter(ImageFilter.GaussianBlur(18)))
    card.paste(pic, (ax, pad), mask)
    text_w = ax - pad * 2
    lines, font, size = fit_title(title, text_w, OG_H * 0.62, 78, 46)
    im = card.convert("RGBA")
    d = ImageDraw.Draw(im)
    top = int((OG_H - len(lines) * size * 1.14) / 2) - 14
    fill = (255, 255, 255, 255)
    _draw_text_block(d, lines, font, pad, top + int(len(lines) * size * 1.14), size, fill)
    mk = _mark(210, (255, 255, 255))
    im.alpha_composite(mk, (pad, OG_H - pad - mk.height))
    return im.convert("RGB")


def to_jpeg(im: Image.Image, max_bytes: int, quality: int = 88, floor: int = 58) -> bytes:
    """Progressive JPEG, the highest quality at or under `max_bytes` (never below `floor`)."""
    q = quality
    while True:
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=q, optimize=True, progressive=True, subsampling=0 if q >= 80 else 2)
        if buf.tell() <= max_bytes or q <= floor:
            return buf.getvalue()
        q -= 4


def own_size(width: int, height: int) -> Tuple[int, int]:
    k = min(1.0, OWN_LONG_SIDE / float(max(width, height)))
    return max(2, int(round(width * k)) // 2 * 2), max(2, int(round(height * k)) // 2 * 2)


def aspect_of(timeline: Dict[str, Any]) -> str:
    fr = timeline.get("frame") if isinstance(timeline.get("frame"), dict) else {}
    a = fr.get("aspect")
    if a in _TITLE_BOTTOM:
        return a
    w, h = int(timeline.get("width", 1920)), int(timeline.get("height", 1080))
    return "16:9" if w > h * 1.5 else "9:16" if h > w * 1.5 else "4:5" if h > w else "1:1"


PHOTO_SCENES = ("image", "gallery", "clip", "photo_collage", "photo_frame", "annotated_image")


def choose_layout(timeline: Dict[str, Any]) -> str:
    """"scrim" when the first scene is a photograph or footage (no text of its own to collide with), else "ribbon"."""
    return "scrim" if timeline["scenes"][0].get("type") in PHOTO_SCENES and not _is_paper(str(timeline.get("theme") or "")) else "ribbon"


def build_from_art(art: Image.Image, title: str, *, aspect: str, theme: str, layout: Optional[str] = None) -> Dict[str, Any]:
    """The two JPEGs from the art picture."""
    og = og_card(art, title, aspect=aspect, theme=theme, layout=layout)
    own = compose(art, title, aspect=aspect, theme=theme, out_size=own_size(art.width, art.height), layout=layout)
    return {"og": to_jpeg(og, OG_MAX_BYTES), "own": to_jpeg(own, OWN_MAX_BYTES), "og_size": og.size, "own_size": own.size, "aspect": aspect}


def build(timeline: Dict[str, Any], image_loader: Optional[Callable[[str], Optional[Image.Image]]] = None, clip_loader: Optional[Callable[[str], Any]] = None,
          title: Optional[str] = None) -> Dict[str, Any]:
    """The cover of the video the timeline describes: {"og": jpeg, "own": jpeg, "og_size", "own_size", "aspect", "settle_s"}."""
    art = render_art(timeline, image_loader, clip_loader)
    out = build_from_art(art, title if title is not None else str(timeline.get("title") or ""), aspect=aspect_of(timeline), theme=str(timeline.get("theme") or "midnight"), layout=choose_layout(timeline))
    out["settle_s"] = round(settle_time(timeline), 3)
    return out


# ----------------------------------------------------------------------------- the MP4's own first frames
IN_FRAME_BLEND_S = 0.4      # the cover is frame 0 and dissolves into the real opening over this long: no flash, no change of length, audio untouched


def in_frame(art: Image.Image, title: str, *, aspect: str, theme: str, layout: Optional[str] = None) -> Image.Image:
    """The cover at the video's own size, for frame 0 of the MP4 (same design as `compose`)."""
    return compose(art, title, aspect=aspect, theme=theme, out_size=art.size, layout=layout)


def opening_needs_cover(timeline: Dict[str, Any]) -> bool:
    """True when frame 0 is likely not a picture worth showing: a scene that is drawn or built up over time (whiteboard, presenter, text, charts...). A photograph or footage
    already opens on a real picture (measured on QA videos, docs/SHARE_PREVIEWS_2026-11-28.md), so it keeps its own first frame."""
    return timeline["scenes"][0].get("type") not in PHOTO_SCENES


def timeline_cover(timeline: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """What the timeline carries when the MP4's first frames are the cover (COVER_IN_FRAME=1): the title and the layout, so every chunk-0 render draws the same frame.
    None for a video whose opening is already a photograph."""
    if not opening_needs_cover(timeline):
        return None
    return {"title": str(timeline.get("title") or ""), "layout": choose_layout(timeline), "blend_s": IN_FRAME_BLEND_S}


# ----------------------------------------------------------------------------- where the finished pictures live
DESIGN_VERSION = 1   # bump when the design changes: every video's cover key changes, so new renders get the new design


def cover_hash(timeline: Dict[str, Any]) -> str:
    """Names a cover by what it is made of (title, look, shape, language, the first scene as written, the design version): the same render finds its cover already there."""
    sc = timeline["scenes"][0]
    blob = json.dumps({"v": DESIGN_VERSION, "title": timeline.get("title"), "theme": timeline.get("theme"), "aspect": aspect_of(timeline), "lang": timeline.get("language"),
                       "scene": {k: sc.get(k) for k in ("type", "duration", "props")}}, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def keys(prefix: str, timeline: Dict[str, Any]) -> Dict[str, str]:
    h = cover_hash(timeline)
    return {"og_key": f"{prefix}cover_{h}_og.jpg", "own_key": f"{prefix}cover_{h}_own.jpg"}
