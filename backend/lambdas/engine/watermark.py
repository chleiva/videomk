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

from PIL import Image, ImageFilter

from . import watermark_spec as ws
from .frame import Frame

log = logging.getLogger(__name__)
ASSETS = os.path.join(os.path.dirname(__file__), "assets", "watermark")
SHADOW_ALPHA = 0.62        # of the mark's own alpha
SHADOW_BLUR = 0.10         # blur radius as a share of the mark height
SHADOW_DROP = 0.035        # downward offset as a share of the mark height
INK = (17, 20, 43)         # the brand ink (#11142b): the mark on a light picture (a white mark would vanish there; docs/brand/README.md: never light-on-light)
LIGHT_FROM, LIGHT_TO = 0.55, 0.66   # mean brightness (0..1) under the mark where it starts and finishes turning from white to ink: a smooth blend, so nothing flips between frames


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
    """The artwork of one watermark at one output size: `layer` (white + shadow, or the logo), `layer_ink` (ink + glow; None for a custom logo), `pos` (where the layers' top-left goes, output px)
    and `rect_px` (the mark itself, output px: the area whose brightness decides white or ink)."""

    def __init__(self, spec: Dict[str, Any], frame: Frame, out_size: Tuple[int, int], captions: bool = True, loader: Optional[Callable[[str], Any]] = None):
        self.spec = spec
        self.layer: Optional[Image.Image] = None   # the artwork as supplied (white mark, or the person's logo)
        self.layer_ink: Optional[Image.Image] = None   # the videomk mark in ink, for light pictures (None for a custom logo: the person's colours stay)
        self.pos = (0, 0)
        self.rect_px = (0, 0, 0, 0)
        self.info: Dict[str, Any] = {}
        out_w, out_h = out_size
        scale = out_w / float(frame.W)   # design units -> output pixels (a draft is half size, 4K is twice)
        logo, ratio = None, None
        if spec["mode"] == "custom":
            logo = self._logo(spec, loader)
            if logo is None:
                log.warning("WATERMARK_LOGO_UNREADABLE asset=%s: no watermark drawn", spec.get("asset"))
                return
            ratio = logo.width / float(logo.height)
        lay = ws.layout(spec, frame, ratio, captions)
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

    @staticmethod
    def light(mean: float) -> float:
        """How light a picture of mean brightness `mean` (0..1) under the mark is, as a smooth 0..1 weight (a smoothstep between LIGHT_FROM and LIGHT_TO): 0 = white mark, 1 = ink mark."""
        u = max(0.0, min(1.0, (mean - LIGHT_FROM) / (LIGHT_TO - LIGHT_FROM)))
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
