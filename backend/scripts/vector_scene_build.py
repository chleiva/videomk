#!/usr/bin/env python3
"""Build a layered vector scene (engine/vector_scene.py, docs/VECTOR_SCENES.md) from ONE flat-cartoon picture. OFFLINE tool: needs
  pip install vtracer opencv-python-headless scipy onnxruntime
and the Depth-Anything-V2-small ONNX model (Apache-2.0, public, ~100 MB):
  curl -L -o ~/.cache/videomk/depth-anything-v2-small.onnx https://huggingface.co/onnx-community/depth-anything-v2-small/resolve/main/onnx/model.onnx

  python scripts/vector_scene_build.py picture.png OUT_DIR --cuts 0.4,0.58 [--sun] [--no-clouds] [--motion '{"2": {"sway": {"amp": 0.003, "period": 3.2}}}']

How: (1) relative depth from the model, (2) the picture is cut into flat-colour regions and each region gets ONE depth (so a depth band never slices an object),
(3) band 0 is the sky (blue areas touching the top, haze bands, the sun), clouds become their own drifting layer, the other bands come from --cuts on the region
depth, (4) every layer keeps its own pixels and gets the colour of the nearest same-band pixel behind nearer layers (outline strokes are not used, so a gap
revealed by the parallax is flat colour), (5) each layer goes through vtracer to an SVG. Output: OUT_DIR/manifest.json plus one SVG per layer (back to front).
Known limits: an object whose parts have different depths can still split across layers (pin it by merging bands), and thin outline strokes can double at
the cut. The model's depth reads overhead canopy as far away, so a forest top moves like background.
"""
import json
import os
import sys

import cv2
import numpy as np
import vtracer
from PIL import Image
from scipy import ndimage as ndi

DEPTH_MODEL = os.environ.get("VECTOR_SCENE_DEPTH_MODEL") or os.path.expanduser("~/.cache/videomk/depth-anything-v2-small.onnx")



def crop169(im):
    W, H = im.size
    h = round(W * 9 / 16)
    if h <= H:
        t = (H - h) // 2
        return im.crop((0, t, W, t + h))
    w = round(H * 16 / 9)
    l = (W - w) // 2
    return im.crop((l, 0, l + w, H))

def regions(rgb, depth, k=24, outline_v=75, min_px=120):
    """flat-colour connected regions (outlines set aside) -> piecewise-constant depth map"""
    blur = cv2.bilateralFilter(rgb, 7, 40, 7)
    Z = blur.reshape(-1, 3).astype(np.float32)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, lab, cen = cv2.kmeans(Z, k, None, crit, 2, cv2.KMEANS_PP_CENTERS)
    lab = lab.reshape(rgb.shape[:2])
    hsv = cv2.cvtColor(blur, cv2.COLOR_RGB2HSV)
    outline = hsv[..., 2] < outline_v
    outline = cv2.morphologyEx(outline.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)).astype(bool)
    comp = np.zeros(lab.shape, np.int32); n = 0
    for c in range(k):
        m = (lab == c) & ~outline
        l, cnt = ndi.label(m)
        comp[m] = l[m] + n; n += cnt
    d = depth.astype(np.float32) / 255.0
    rd = np.zeros(lab.shape, np.float32)
    idx = np.arange(1, n + 1)
    med = ndi.median(d, comp, idx) if n else []
    sizes = ndi.sum(np.ones_like(d), comp, idx)
    lut = np.zeros(n + 1, np.float32); lut[1:] = med
    big = np.zeros(n + 1, bool); big[1:] = sizes >= min_px
    rd = lut[comp]
    valid = big[comp] & (comp > 0)
    # outline pixels and tiny regions: take the NEAREST (max depth) valid region around them, so the front object keeps its outline
    rdv = np.where(valid, rd, 0).astype(np.float32)
    grow = cv2.dilate(rdv, np.ones((9, 9), np.uint8))
    out = np.where(valid, rd, grow)
    # anything still empty: raw depth
    out = np.where(out > 0, out, d)
    return out, outline, comp

def bands_from(rd, cuts):
    b = np.zeros(rd.shape, np.int32)
    for c in cuts:
        b += (rd > c)
    return b

def fill_behind(rgb, keep, src_ok=None):
    """pixels in keep stay; the others get the colour of the nearest src_ok pixel (default keep): hidden under nearer layers, revealed only by parallax.
    src_ok excludes outline strokes, so a revealed gap is flat colour, not a dark fringe."""
    if keep.all():
        return rgb.copy()
    src_ok = keep if src_ok is None or not src_ok.any() else src_ok
    _, (iy, ix) = ndi.distance_transform_edt(~src_ok, return_indices=True)
    return np.where(keep[..., None], rgb, rgb[iy, ix])

def build_layers(rgb, band, nb, outline=None):
    """layer k = pixels of band k, holes (nearer bands) filled; alpha = band >= k (layer 0 fully opaque). returns list of RGBA arrays"""
    out = []
    for k in range(nb):
        keep = band == k
        if not keep.any():
            continue
        col = fill_behind(rgb, keep, cv2.erode((keep & ~cv2.dilate(outline.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool) if outline is not None else None)
        a = (band >= k)
        # soft 1px edge so the cut is not jagged against the layer below
        af = cv2.GaussianBlur(a.astype(np.float32), (0, 0), 0.8)
        af = np.where(a, 1.0, af * 0.0)  # keep hard binary edge for the vectoriser
        rgba = np.dstack([col, (af * 255).astype(np.uint8)])
        out.append(rgba)
    return out



def depth_map(im: Image.Image) -> np.ndarray:
    """Relative inverse depth 0..255 (255 = nearest) of an RGB picture, same size."""
    import onnxruntime as ort

    W, H = im.size
    x = np.asarray(im.convert("RGB").resize((518, 518), Image.BICUBIC), dtype=np.float32) / 255.0
    x = ((x - [0.485, 0.456, 0.406]) / [0.229, 0.224, 0.225]).transpose(2, 0, 1)[None].astype(np.float32)
    sess = ort.InferenceSession(DEPTH_MODEL, providers=["CPUExecutionProvider"])
    d = sess.run(None, {sess.get_inputs()[0].name: x})[0][0]
    d = (d - d.min()) / (d.max() - d.min() + 1e-9)
    return np.asarray(Image.fromarray((d * 255).astype("uint8")).resize((W, H), Image.BICUBIC))



def sky_mask(rgb, comp):
    """sky = flat-colour areas that are blue-ish and touch the top of the picture, plus pale-cyan haze areas (clouds in the distance).
    The areas come from the colour regions, so the sea below the horizon (another blue) is not sky."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    n = int(comp.max())
    idx = np.arange(1, n + 1)
    H, S, V = (ndi.median(hsv[..., c].astype(np.float32), comp, idx) for c in range(3))
    area = ndi.sum(np.ones(comp.shape, np.float32), comp, idx)
    topids = set(np.unique(comp[:comp.shape[0] // 8])) - {0}
    ok = np.zeros(n + 1, bool)
    for i in range(n):
        blue = 78 <= H[i] <= 112 and S[i] > 25 and V[i] > 120
        pale = 78 <= H[i] <= 100 and 25 < S[i] < 130 and V[i] > 185
        if area[i] > 0.004 * comp.size and ((blue and (i + 1) in topids) or pale):
            ok[i + 1] = True
    # grow into blue areas next to the sky that are not more saturated than it (haze bands); the sea and lakes are more saturated, so they stay out
    seeds = [i for i in range(n) if ok[i + 1]]
    if seeds:
        smax = max(S[i] for i in seeds); vmin = min(V[i] for i in seeds)
        for _ in range(4):
            near = cv2.dilate(ok[comp].astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
            touching = set(np.unique(comp[near])) - {0}
            grew = False
            for i in range(n):
                if not ok[i + 1] and (i + 1) in touching and area[i] > 0.002 * comp.size and 78 <= H[i] <= 112 and 25 < S[i] <= smax + 8 and V[i] >= vmin - 20:
                    ok[i + 1] = True; grew = True
            if not grew:
                break
    m = ok[comp]
    # outline fringes and 1-2 px gaps between the area and the picture's own outlines
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)).astype(bool)
    return m

def cloud_mask(rgb, sky, outline=None):
    """light cloud shapes inside/around the sky: bright, low saturation (cream/white) or very pale cyan, near sky"""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    s, v = hsv[..., 1].astype(int), hsv[..., 2].astype(int)
    light = ((v > 200) & (s < 90)) | ((hsv[..., 0] >= 80) & (hsv[..., 0] <= 100) & (s < 110) & (v > 200))
    near = cv2.dilate(sky.astype(np.uint8), np.ones((41, 41), np.uint8)).astype(bool)
    m = light & near
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m)
    keep = np.zeros_like(m, bool)
    for i in range(1, n):
        if st[i, cv2.CC_STAT_AREA] > 800:
            comp = lab == i
            k = lambda z: cv2.dilate(comp.astype(np.uint8), np.ones((z, z), np.uint8)).astype(bool)
            ring = k(31) & ~k(11)
            if (ring & sky).sum() > 0.55 * ring.sum():      # a cloud floats in the sky; snow caps and lighthouse walls touch other things
                keep |= k(9) & (comp | outline)             # the cloud with its own outline stroke
    return keep

def vec(png, svg, **kw):
    p = dict(colormode="color", hierarchical="stacked", mode="spline", filter_speckle=6, color_precision=6, layer_difference=24,
             corner_threshold=60, length_threshold=5.0, max_iterations=10, splice_threshold=45, path_precision=2)
    p.update(kw)
    vtracer.convert_image_to_svg_py(png, svg, **p)
    s = open(svg).read()
    return os.path.getsize(svg), s.count("<path")

def build(src, out, cuts, name, sway=None, clouds=True, vkw=None, sun=False, layer_motion=None):
    os.makedirs(out, exist_ok=True)
    im = crop169(Image.open(src).convert("RGB"))
    tmp = os.path.join(out, "_crop.png"); im.save(tmp)
    rgb = np.asarray(im); d = depth_map(im)
    rd, outline, comp = regions(rgb, d)
    sky = sky_mask(rgb, comp)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    fringe = cv2.dilate(sky.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool) & ~sky & (hsv[..., 2] > 110) & ~outline
    sky = sky | fringe
    if sun:   # yellow disc and rays in the top part: part of the sky, not a layer of its own
        hh, ss, vv = hsv[..., 0], hsv[..., 1], hsv[..., 2]
        y = (hh >= 15) & (hh <= 35) & (ss > 120) & (vv > 190)
        y[int(rgb.shape[0] * 0.4):] = False
        sky = sky | cv2.dilate(y.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool) & ~outline | y
    cl = cloud_mask(rgb, sky, outline) if clouds else np.zeros(sky.shape, bool)
    if cl.any():   # the cloud takes ALL of its pixels that are not sky colour (soft outline strokes included), so no ghost outline stays in the sky layer
        skycol = np.median(rgb[sky & ~cl], axis=0)
        dist = np.abs(rgb.astype(int) - skycol).sum(-1)
        grown = cv2.dilate(cl.astype(np.uint8), np.ones((17, 17), np.uint8)).astype(bool)
        cl = cl | (grown & (dist > 45))
        cl = cv2.morphologyEx(cl.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)).astype(bool)
        cl = ndi.binary_fill_holes(cl)      # shaded patches inside the cloud belong to it
    sky = sky | cl
    band = np.where(sky, 0, 1 + bands_from(rd, cuts))      # band 0 is the sky and nothing else; the cuts split the rest by depth
    nb = len(cuts) + 2
    out_layers, meta = [], []
    # layer 0 (sky + far) with clouds cut out (filled with sky colour), clouds as their own transparent layer on top
    L = build_layers(rgb, band, nb, outline)
    if cl.any():
        base0 = fill_behind(L[0][..., :3], ~cv2.dilate(cl.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool), ~cv2.dilate(cl.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool) & ~cv2.dilate(outline.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool) & (cv2.cvtColor(L[0][..., :3], cv2.COLOR_RGB2HSV)[..., 0] >= 80))
        L[0] = np.dstack([base0, L[0][..., 3]])
    stack = [("sky", L[0], dict(z=0.0))]
    if cl.any():
        c = np.dstack([rgb, (cl * 255).astype(np.uint8)])
        stack.append(("clouds", c, dict(z=0.05, drift=0.012)))
    for k in range(1, len(L)):
        mt = dict(z=k / (nb - 1))
        if layer_motion and k in layer_motion:
            mt.update(layer_motion[k])
        stack.append((f"layer{k}", L[k], mt))
    stats = []
    for i, (nm, arr, mt) in enumerate(stack):
        png = os.path.join(out, f"{i}_{nm}.png"); Image.fromarray(arr, "RGBA").save(png)
        svg = os.path.join(out, f"{i}_{nm}.svg")
        size, paths = vec(png, svg, **(vkw or {}))
        stats.append((nm, size // 1024, paths))
        meta.append(dict(file=f"{i}_{nm}.svg", name=nm, **mt))
    man = dict(name=name, aspect=[16, 9], source_size=list(im.size), layers=meta, motion=sway or {})
    json.dump(man, open(os.path.join(out, "manifest.json"), "w"), indent=1)
    for f in os.listdir(out):   # the intermediate pictures are not part of the scene
        if f.endswith(".png"):
            os.remove(os.path.join(out, f))
    return stats



def main() -> int:
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("picture")
    ap.add_argument("out")
    ap.add_argument("--cuts", default="0.4,0.58", help="depth cuts on the 0..1 region depth; the sky is always band 0")
    ap.add_argument("--sun", action="store_true")
    ap.add_argument("--no-clouds", action="store_true")
    ap.add_argument("--motion", default="{}", help='per-layer motion by band number, JSON, e.g. {"2": {"sway": {"amp": 0.003, "period": 3.2}}, "3": {"bob": {"amp": 0.004, "period": 3}}}')
    a = ap.parse_args()
    motion = {int(k): v for k, v in json.loads(a.motion).items()}
    st = build(a.picture, a.out, [float(x) for x in a.cuts.split(",")], os.path.basename(a.out.rstrip("/")), sun=a.sun, clouds=not a.no_clouds, layer_motion=motion)
    for name, kb, paths in st:
        print(f"{name:10s} {kb:5d} KB  {paths:5d} paths")
    print("total", sum(s[1] for s in st), "KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
