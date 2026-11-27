#!/usr/bin/env python3
"""Builds the watermark artwork the engine ships (backend/lambdas/engine/assets/watermark/) from the brand files in docs/brand/final/.

  .venv/bin/python backend/scripts/watermark_assets.py

mark.svg / lockup.svg: ONE colour (white), tight viewBox, so the engine can tint and shadow them. mark.png / lockup.png: 1024 px tall renders of the same, which the engine
only ever scales DOWN (a 4K frame at the largest size needs about 150 px), so the mark is crisp at every resolution without a rasteriser at render time.
The mark is the VideoMK logo (one play, two stars; docs/BRAND.md section 2); the lockup is the mark plus the 'VideoMK' wordmark (Inter outlines). Sources:
docs/brand/final/mark-white.svg and lockup-horizontal-white.svg, made by docs/brand/final/build_final.py. After a change of shape, update MARK_RATIO and LOCKUP_RATIO in
engine/watermark_spec.py to the sizes this prints.
"""
import io
import os
import re
import sys

import resvg_py
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
BRAND = os.path.join(HERE, "..", "..", "docs", "brand", "final")
OUT = os.path.join(HERE, "..", "lambdas", "engine", "assets", "watermark")
TALL = 1024


def _render(svg: str, w: int, h: int) -> Image.Image:
    return Image.open(io.BytesIO(bytes(resvg_py.svg_to_bytes(svg_string=svg, width=w, height=h)))).convert("RGBA")


def _white(path_tag: str) -> str:
    return re.sub(r'fill="[^"]+"', 'fill="#ffffff"', path_tag)


def _tight(svg_body: str, vb: tuple) -> tuple:
    """(viewBox string, width, height) of the ink's bounding box, measured from a 4x render of the given viewBox."""
    x0, y0, w, h = vb
    k = 4096 / max(w, h)
    pw, ph = int(round(w * k)), int(round(h * k))
    img = _render(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{x0} {y0} {w} {h}" width="{pw}" height="{ph}">{svg_body}</svg>', pw, ph)
    bx = img.getchannel("A").getbbox()
    nx, ny = x0 + bx[0] / k, y0 + bx[1] / k
    nw, nh = (bx[2] - bx[0]) / k, (bx[3] - bx[1]) / k
    return (round(nx, 2), round(ny, 2), round(nw, 2), round(nh, 2))


def build(name: str, svg_body: str, vb: tuple) -> None:
    tvb = _tight(svg_body, vb)
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{tvb[0]} {tvb[1]} {tvb[2]} {tvb[3]}">{svg_body}</svg>'
    open(os.path.join(OUT, f"{name}.svg"), "w").write(svg)
    h = TALL
    w = int(round(TALL * tvb[2] / tvb[3]))
    img = _render(svg.replace("<svg ", f'<svg width="{w}" height="{h}" ', 1), w, h)
    img.save(os.path.join(OUT, f"{name}.png"), optimize=True)
    print(name, "viewBox", tvb, "png", img.size)


def _source(name: str) -> tuple:
    """(the file's paths in white, its viewBox)"""
    text = open(os.path.join(BRAND, name)).read()
    vb = tuple(float(v) for v in re.search(r'viewBox="([^"]+)"', text).group(1).split())
    return "".join(_white(p) for p in re.findall(r"<path[^>]*>", text)), vb


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    build("mark", *_source("mark-white.svg"))                  # the play and the two stars
    build("lockup", *_source("lockup-horizontal-white.svg"))   # the same, then the wordmark


if __name__ == "__main__":
    sys.exit(main())
