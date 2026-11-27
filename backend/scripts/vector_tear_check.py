#!/usr/bin/env python3
"""Tear check for layered vector scenes: does a parallax shift slice an object in two? (owner: 'the wind turbines break at the base').

  python backend/scripts/vector_tear_check.py STORE [--only id ...] [--max-tears 6] [--frames OUT_DIR] [--json report.json]

A scene package is a stack of layers; layer k is opaque where the picture's depth band is >= k. A depth cut that runs ALONG an object's silhouette is fine (the near layer
carries the whole object); a cut that runs ACROSS an object tears it when the layers move. At a tear the object's own outline stroke crosses the cut, so the
stroke is dark on BOTH sides of the cut, while at a clean silhouette the stroke belongs entirely to the near side. The check rasterises the layers at 1024 px,
finds the cut pixels (neighbouring pixels in different bands) where both sides are dark outline pixels in the identity picture, and counts the connected
crossings that are long enough to see (>= MIN_LEN px of cut). Overlay layers (clouds and animated sprites) are ignored: they move on purpose.
Exit code 1 when any scene has more than --max-tears crossings. --frames writes a crop of the worst crossing at identity and at full parallax for the eye.
"""
import argparse
import io
import json
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))
W, H = 1024, 576
MIN_LEN = int(os.environ.get("TEAR_MIN_LEN", "16"))   # px of cut, at 1024 wide, that makes a visible tear (a short crossing is leaf or texture detail, a long one is an object body cut)
INK_V = 95           # a pixel darker than this (max of RGB) is outline ink
OVERLAY = ("cloud", "sprite", "anim")


def load_layers(folder):
    import resvg_py

    man = json.load(open(os.path.join(folder, "manifest.json")))
    base = []
    for lay in man["layers"]:
        svg = open(os.path.join(folder, lay["file"]), encoding="utf-8").read()
        png = resvg_py.svg_to_bytes(svg_string=svg, width=W, height=H)
        im = Image.open(io.BytesIO(bytes(png))).convert("RGBA")
        if im.size != (W, H):
            im = im.resize((W, H), Image.BILINEAR)
        overlay = any(k in lay.get("name", "") for k in OVERLAY) or lay.get("sprite")
        base.append((np.asarray(im), bool(overlay)))
    return man, base


def analyse(folder, want_frames=None):
    man, layers = load_layers(folder)
    stack = [a for a, ov in layers if not ov]
    comp = np.zeros((H, W, 3), np.float32)
    band = np.zeros((H, W), np.int32)
    for k, a in enumerate(stack):
        al = a[..., 3:4].astype(np.float32) / 255.0
        comp = comp * (1 - al) + a[..., :3].astype(np.float32) * al
        band += (a[..., 3] > 128).astype(np.int32) if k > 0 else 0
    ink = comp.max(-1) < INK_V
    cut = np.zeros((H, W), bool)
    for dy, dx in ((0, 1), (1, 0)):
        a = band[: H - dy, : W - dx]
        b = band[dy:, dx:]
        diff = a != b
        both_ink = ink[: H - dy, : W - dx] & ink[dy:, dx:]
        cut[: H - dy, : W - dx] |= diff & both_ink
    cut = ndi.binary_dilation(cut, iterations=1)
    lab, n = ndi.label(cut, structure=np.ones((3, 3)))
    tears = []
    for i in range(1, n + 1):
        ys, xs = np.where(lab == i)
        ext = max(ys.max() - ys.min(), xs.max() - xs.min()) + 1
        if len(ys) >= MIN_LEN and ext >= 8:
            tears.append(dict(x=int(xs.mean()), y=int(ys.mean()), px=int(len(ys)), extent=int(ext)))
    tears.sort(key=lambda t: -t["px"])
    return dict(tears=len(tears), worst=tears[:5], layers=len(stack)), (comp.astype(np.uint8), tears)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("store")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--max-tears", type=int, default=6)
    ap.add_argument("--frames")
    ap.add_argument("--json")
    a = ap.parse_args()
    ids = sorted(d for d in os.listdir(a.store) if os.path.isfile(os.path.join(a.store, d, "manifest.json")))
    ids = [i for i in ids if not a.only or i in a.only]
    report, bad = {}, 0
    for sid in ids:
        r, (comp, tears) = analyse(os.path.join(a.store, sid))
        report[sid] = r
        flag = r["tears"] > a.max_tears
        bad += flag
        print(f"{sid:28s} crossings {r['tears']:3d} {'TEAR RISK' if flag else 'ok'}", flush=True)
        if a.frames and tears:
            os.makedirs(a.frames, exist_ok=True)
            t = tears[0]
            x0, y0 = max(0, t["x"] - 80), max(0, t["y"] - 60)
            Image.fromarray(comp[y0:y0 + 120, x0:x0 + 160]).resize((480, 360), Image.NEAREST).save(os.path.join(a.frames, f"{sid}_worst.png"))
    if a.json:
        json.dump(report, open(a.json, "w"), indent=1)
    print(f"{bad} of {len(ids)} scenes over {a.max_tears} crossings")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
