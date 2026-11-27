"""The watermark, drawn on every output frame after everything else (docs/WATERMARK.md).

It is part of the render, never an overlay the app adds, so it cannot be dropped by a client. The artwork is rasterised for the real output size (a 1024 px tall source that is only
ever scaled DOWN: the largest mark at 4K is about 150 px), tinted white with a soft shadow so it reads on any footage, and placed by engine/watermark_spec.py.
A custom logo is the person's own PNG, stored privately and copied into the video's own folder when the video starts (`spec['asset']`); an unreadable one draws nothing.
"""
import hashlib
import logging
import os
from functools import lru_cache
from typing import Any, Callable, Dict, Optional, Tuple

from PIL import Image, ImageFilter, ImageStat

from . import watermark_spec as ws
from .frame import Frame

log = logging.getLogger(__name__)
ASSETS = os.path.join(os.path.dirname(__file__), "assets", "watermark")
SHADOW_ALPHA = 0.45        # of the mark's own alpha
SHADOW_BLUR = 0.07         # blur radius as a share of the mark height
SHADOW_DROP = 0.035        # downward offset as a share of the mark height
OUTRO_FADE_S = 0.7         # the renderer's closing fade to black (renderer.OUTRO_FADE_S): the mark leaves with the picture
INK = (17, 20, 43)         # the brand ink (#11142b): the mark on a light picture (a white mark would vanish there; docs/brand/README.md: never light-on-light)
LIGHT_FROM, LIGHT_TO = 0.52, 0.74   # mean brightness (0..1) under the mark where it starts and finishes turning from white to ink: a smooth blend, so nothing flips between frames


def _fit(img: Image.Image, w: int, h: int) -> Image.Image:
    """Scale RGBA to (w, h) with premultiplied alpha (no dark fringes at the edges); halves first so a big source stays crisp."""
    img = img.convert("RGBa")
    while img.width >= w * 2 and img.height >= h * 2:
        img = img.resize((max(w, img.width // 2), max(h, img.height // 2)), Image.LANCZOS)
    return img.resize((w, h), Image.LANCZOS).convert("RGBA")


@lru_cache(maxsize=8)
def _source(kind: str) -> Image.Image:
    return Image.open(os.path.join(ASSETS, f"{kind}.png")).convert("RGBA")


def _tint(mark: Image.Image, rgb: Tuple[int, int, int]) -> Image.Image:
    out = Image.new("RGBA", mark.size, rgb + (0,))
    out.putalpha(mark.getchannel("A"))
    return out


def _with_shadow(mark: Image.Image, shadow_rgb: Tuple[int, int, int] = (0, 0, 0)) -> Tuple[Image.Image, int]:
    """(RGBA layer, pad): the mark over its own soft shadow (a glow on the ink version), padded so the blur is not cut."""
    h = mark.height
    blur = max(1.0, SHADOW_BLUR * h)
    drop = SHADOW_DROP * h
    pad = int(blur * 3 + drop) + 2
    canvas = Image.new("RGBA", (mark.width + 2 * pad, mark.height + 2 * pad), (0, 0, 0, 0))
    shadow = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    shadow.paste(Image.new("RGBA", mark.size, shadow_rgb + (255,)), (pad, pad + int(round(drop))), mark.getchannel("A"))
    a = shadow.getchannel("A").filter(ImageFilter.GaussianBlur(blur)).point(lambda v: int(v * SHADOW_ALPHA))
    shadow.putalpha(a)
    canvas.alpha_composite(shadow)
    canvas.alpha_composite(mark, (pad, pad))
    return canvas, pad


def _scaled_alpha(layer: Image.Image, k: float) -> Image.Image:
    if k >= 0.999:
        return layer
    out = layer.copy()
    out.putalpha(layer.getchannel("A").point(lambda v: int(v * k)))
    return out


class Watermark:
    """Built once per Renderer. `apply(img, t)` returns the frame with the mark on it (the frame itself, changed in place)."""

    def __init__(self, spec: Dict[str, Any], frame: Frame, out_size: Tuple[int, int], captions: bool = True, loader: Optional[Callable[[str], Any]] = None):
        self.spec = spec
        self.layer: Optional[Image.Image] = None   # the artwork as supplied (white mark, or the person's logo)
        self.layer_ink: Optional[Image.Image] = None   # the videomk mark in ink, for light pictures (None for a custom logo: the person's colours stay)
        self.pos = (0, 0)
        self.inset = 0   # design units the scenes start lower by, so a top-corner mark has a band of its own (watermark_spec.content_inset)
        self.fade = ws.FADE_IN_S
        self.windows = spec.get("windows", []) if spec.get("mode") == "videomk" and spec.get("presence") == "moments" else None   # presence 'moments': when it is on screen (this chunk's times); None = always
        out_w, out_h = out_size
        scale = out_w / float(frame.W)   # design units -> output pixels (a draft is half size, 4K is twice)
        logo, ratio = None, None
        if spec["mode"] == "custom":
            logo = self._logo(spec, loader)
            if logo is None:
                log.warning("WATERMARK_LOGO_UNREADABLE asset=%s: no watermark drawn", spec.get("asset"))
                return
            ratio = logo.width / float(logo.height)
        frame = frame.with_top_inset(0)   # placed on the shape itself, never on a frame that already carries the band
        lay = ws.layout(spec, frame, ratio, captions)
        self.inset = ws.content_inset(lay, frame)
        x0, y0, x1, y1 = lay["rect"]
        w_px, h_px = max(2, int(round((x1 - x0) * scale))), max(2, int(round((y1 - y0) * scale)))
        key = ("custom:" + str(spec.get("hash") or spec.get("asset")) if logo is not None else spec.get("style", "mark"), w_px, h_px)
        base = _fit(logo, w_px, h_px) if logo is not None else _fit(_source(spec.get("style", "mark")), w_px, h_px)
        layer, pad = _with_shadow(base)
        op = float(spec.get("opacity", ws.DEFAULT_OPACITY))
        self.layer = _scaled_alpha(layer, op)
        if logo is None:
            self.layer_ink = _scaled_alpha(_with_shadow(_tint(base, INK), (255, 255, 255))[0], op)
        self.pos = (int(round(x0 * scale)) - pad, int(round(y0 * scale)) - pad)
        self.rect_px = (int(round(x0 * scale)), int(round(y0 * scale)), int(round(x0 * scale)) + w_px, int(round(y0 * scale)) + h_px)
        self.info = dict(lay, key=key)

    @staticmethod
    def _logo(spec: Dict[str, Any], loader: Optional[Callable[[str], Any]]) -> Optional[Image.Image]:
        if not loader or not isinstance(spec.get("asset"), str):
            return None
        try:
            img = loader(spec["asset"])
            return img.convert("RGBA") if img is not None and img.width > 0 and img.height > 0 else None
        except Exception:   # noqa: BLE001 - a bad logo must never fail the render
            return None

    def apply(self, img: Image.Image, t: float = 0.0, *, first: bool = False, outro_k: float = 0.0) -> Image.Image:
        """`first`: this is the first chunk of the video, so the mark fades in over FADE_IN_S; `outro_k` (0..1): how far the closing fade to black has gone."""
        if self.layer is None:
            return img
        k = 1.0
        if self.windows is not None:   # it comes and goes: a pure function of the time (the timeline wrote the appearances, every chunk has its own copy)
            k = ws.moment_alpha(self.windows, t)
        elif first and t < self.fade:
            u = max(0.0, t) / self.fade
            k *= u * u * (3 - 2 * u)
        k *= 1.0 - max(0.0, min(1.0, outro_k))
        if k <= 0.003:
            return img
        x, y = self.pos
        box = (max(0, x), max(0, y), min(img.width, x + self.layer.width), min(img.height, y + self.layer.height))
        if box[2] <= box[0] or box[3] <= box[1]:
            return img
        region = img.crop(box).convert("RGBA")
        s = self._light(region) if self.layer_ink is not None else 0.0   # 0 = dark picture (white mark) .. 1 = light picture (ink mark)
        for layer, share in ((self.layer, 1.0 - s), (self.layer_ink, s)):
            if layer is None or share * k <= 0.003:
                continue
            lay = _scaled_alpha(layer, share * k)
            region.alpha_composite(lay.crop((box[0] - x, box[1] - y, box[2] - x, box[3] - y)))
        img.paste(region.convert("RGB"), box[:2])
        return img

    @staticmethod
    def _light(region: Image.Image) -> float:
        """How light the picture under the mark is, as a smooth 0..1 blend weight (mean brightness, then a smoothstep between LIGHT_FROM and LIGHT_TO)."""
        m = ImageStat.Stat(region.convert("L")).mean[0] / 255.0
        u = max(0.0, min(1.0, (m - LIGHT_FROM) / (LIGHT_TO - LIGHT_FROM)))
        return u * u * (3 - 2 * u)


def build(raw: Any, frame: Frame, out_size: Tuple[int, int], captions: bool = True, loader: Optional[Callable[[str], Any]] = None) -> Optional[Watermark]:
    """The Watermark for a timeline's `watermark` entry, or None (no entry, mode none, or nothing to draw)."""
    spec = ws.parse(raw, strict=False)
    if not spec or spec["mode"] == "none":
        return None
    wm = Watermark(spec, frame, out_size, captions, loader)
    return wm if wm.layer is not None else None


def logo_hash(png_bytes: bytes) -> str:
    return hashlib.sha256(png_bytes).hexdigest()[:16]
