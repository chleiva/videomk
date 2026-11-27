"""Layered vector scenes: flat-cartoon art split into depth layers, each stored as an SVG, animated with parallax, sway and drift (docs/VECTOR_SCENES.md).

Only Pillow, numpy and resvg-py are needed (no OpenCV / SciPy): the scene is rasterised from its SVG layers at the size it is shown, so it is sharp at any
resolution, then each layer is moved by an affine map (parallax, push-in) or a sheared mesh (sway). Everything is a pure function of the time, so a chunk
rendered anywhere is identical.

A scene folder holds `manifest.json` and one SVG per layer, back to front. Layer keys: `z` (0 far .. 1 near: parallax and zoom weight), `drift` (share of the
frame width crossed over the scene, for clouds), `sway` {amp (share of width), period (s), phase}, `bob` {amp (share of height), period, phase}.
Manifest `motion`: `push` (zoom of the nearest layer over the scene) and `pan` (parallax travel of the nearest layer, share of the width).
A layer may also be a SPRITE (`sprite: true`, `kind`) with `tags` (engine/vector_motion.py): turbine blades rotate about the hub, fish swim and wiggle, boats bob, birds, trains and cars travel,
smoke rises and fades, flames flicker, lit windows and stars twinkle. A sprite is cut out of the picture offline (scripts/vector_sprites.py) and drawn at the depth of the object it belongs to.
The art is built offline with backend/scripts/vector_scene_build.py (depth model -> colour regions -> bands -> filled layers -> vtracer).
"""
import io
import json
import math
import os
from functools import lru_cache
from typing import Any, Dict, List, Tuple

from PIL import Image

from . import vector_motion as vm

DIR = os.path.join(os.path.dirname(__file__), "assets", "vector_scenes")
MARGIN = 1.12   # each layer is 12% larger than the frame: room for the parallax travel
RS = 1.08       # layers are rasterised 8% above the frame scale: room for the push-in at 1:1 sharpness


def scene_ids() -> List[str]:
    try:
        return sorted(d for d in os.listdir(DIR) if os.path.isfile(os.path.join(DIR, d, "manifest.json")))
    except OSError:
        return []


def ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


class VectorScene:
    def __init__(self, folder: str, width: int, height: int):
        import resvg_py   # lazy: the engine layer provides it; the element falls back to a plain card without it

        self.dir, self.W, self.H = folder, int(width), int(height)
        with open(os.path.join(folder, "manifest.json"), encoding="utf-8") as f:
            self.man: Dict[str, Any] = json.load(f)
        self.cw, self.ch = round(self.W * MARGIN * RS), round(self.H * MARGIN * RS)
        self.layers: List[Dict[str, Any]] = self.man["layers"]
        for lay in self.layers:   # motion tags of the catalog (vector_motion.py): validated here, so a bad manifest never reaches the renderer
            if "tags" in lay:
                lay["tags"] = vm.clean_tags(lay["tags"])
        self.rasters: List[Image.Image] = []
        for lay in self.layers:
            with open(os.path.join(folder, lay["file"]), encoding="utf-8") as f:
                png = resvg_py.svg_to_bytes(svg_string=f.read(), width=self.cw, height=self.ch)
            im = Image.open(io.BytesIO(bytes(png))).convert("RGBA")
            self.rasters.append(im if im.size == (self.cw, self.ch) else im.resize((self.cw, self.ch), Image.BILINEAR))

    def frame(self, t: float, dur: float) -> Image.Image:
        W, H = self.W, self.H
        mo = self.man.get("motion", {})
        p = ease(t / max(dur, 1e-6))
        push, pan = float(mo.get("push", 0.07)), float(mo.get("pan", 0.025))
        out = Image.new("RGB", (W, H), (0, 0, 0))
        cx, cy = self.cw / 2, self.ch / 2
        for lay, ras in zip(self.layers, self.rasters):
            z = float(lay.get("z", 0.5))
            s = 1.0 + push * (0.25 + 0.75 * z) * p                       # near layers grow faster than far ones
            tx = -(p - 0.5) * 2 * pan * W * (0.2 + 0.8 * z)
            ty = 0.0
            if "drift" in lay:
                tx += lay["drift"] * W * (min(1.0, max(0.0, t / max(dur, 1e-6))) - 0.5) * 2
            bob = lay.get("bob")
            if bob:
                ty += bob["amp"] * H * math.sin(2 * math.pi * t / bob["period"] + bob.get("phase", 0.0))
            sway = lay.get("sway")
            a = RS / s

            def src(x: float, y: float, dx: float = 0.0) -> Tuple[float, float]:
                return (cx + (x - W / 2 - tx - dx) * a, cy + (y - H / 2 - ty) * a)

            tr = vm.layer_transform(lay.get("tags"), t, dur) if lay.get("tags") else None   # motion tags (vector_motion.py): rotate, wiggle, drift, flicker...
            if tr is not None:
                coef = vm.affine(tr, W=W, H=H, cw=self.cw, ch=self.ch, rs=RS, margin=MARGIN, s=s, tx=tx, ty=ty)
                fr = ras.transform((W, H), Image.AFFINE, coef, Image.BILINEAR)
                if tr["alpha"] < 0.999:
                    fr.putalpha(fr.getchannel("A").point(lambda v, k=tr["alpha"]: int(v * k)))
            elif not sway:
                fr = ras.transform((W, H), Image.AFFINE, (a, 0, cx - (W / 2 + tx) * a, 0, a, cy - (H / 2 + ty) * a), Image.BILINEAR)
            else:
                amp, per, ph = sway["amp"] * W, sway["period"], sway.get("phase", 0.0)
                k = max(8, H // 24)

                def dxy(y: float) -> float:   # the tops of plants move most, the roots stay put
                    w = (1 - y / H) ** 1.3
                    return amp * w * (math.sin(2 * math.pi * t / per + ph + y / H * 2.2) + 0.35 * math.sin(2 * math.pi * t / (per * 0.43) + ph * 1.7 + y / H * 4.1))

                ys = [H * i / k for i in range(k + 1)]
                mesh = []
                for i in range(k):
                    y0, y1 = ys[i], ys[i + 1]
                    nw, sw_, se, ne = src(0, y0, dxy(y0)), src(0, y1, dxy(y1)), src(W, y1, dxy(y1)), src(W, y0, dxy(y0))
                    mesh.append(((0, int(round(y0)), W, int(round(y1))), (*nw, *sw_, *se, *ne)))
                fr = ras.transform((W, H), Image.MESH, mesh, Image.BILINEAR)
            out.paste(fr, (0, 0), fr)
        return out


@lru_cache(maxsize=4)
def load(scene_id: str, width: int, height: int) -> VectorScene:
    """Rasterised layers are cached per (scene, size): a render chunk draws many frames from one load (about 1 s at 1080p)."""
    if scene_id not in scene_ids():
        raise ValueError(f"unknown vector scene {scene_id!r}")
    return VectorScene(os.path.join(DIR, scene_id), width, height)
