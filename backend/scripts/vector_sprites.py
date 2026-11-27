"""Cut implied-motion subjects (turbine rotors, fish, boats, birds, trains, smoke, flames, lit windows, stars) out of a cartoon scene as SPRITE layers, so the runtime
can animate them (engine/vector_motion.py). Used by vector_catalog_build.py; the boxes come from vector_motion_audit.py (vision model) and the cut is deterministic.

How a sprite is cut: the picture is already split into flat-colour regions (vector_scene_build.regions); the sprite is the set of regions that lie CLOSED inside the box
the model drew (a boat, a fish, a train car is a closed region; the water, the quay and the viaduct run out of the box, so they stay), plus the outline strokes around
them. A turbine rotor is the light regions inside the circle around its hub (the shaft runs out of the circle, so it stays). Lit windows and flames are the warm bright
regions inside the box; stars are the small bright dots of a dark sky.
How the layers are built: every sprite pixel becomes 'band host - 0.5': the layers behind it fill the hole with the colours around it (plate), the layers from the host
upwards are transparent there, and the sprite is its own RGBA layer drawn right above the host layer, at the host's depth, so it keeps moving with the object it belongs to.
"""
import json
import os

import cv2
import numpy as np
from scipy import ndimage as ndi

# motion defaults per subject kind: tags for engine/vector_motion.py (pivot filled in per sprite)
DEFAULT_TAGS = {
    "turbine": lambda sp: [dict(type="rotate", pivot=sp["pivot"], period=7.0 + 1.3 * (sp["i"] % 3), dir=1, phase=0.17 * sp["i"])],
    "windmill": lambda sp: [dict(type="rotate", pivot=sp["pivot"], period=9.0, dir=1)],
    "fish": lambda sp: [dict(type="wiggle", pivot=sp["pivot"], deg=5.0, period=1.1 + 0.2 * (sp["i"] % 3), phase=0.2 * sp["i"]),
                        dict(type="drift", vx=(0.07 if sp["facing"] != "left" else -0.07), vy=0.0, mode="linear"),
                        dict(type="bob", amp=0.004, period=3.0 + sp["i"], phase=0.3 * sp["i"])],
    "bird": lambda sp: [dict(type="drift", vx=(0.22 if sp["facing"] != "left" else -0.22), vy=-0.02, mode="linear"),
                        dict(type="wiggle", pivot=sp["pivot"], deg=4.0, period=0.8, phase=0.1 * sp["i"])],
    "boat": lambda sp: [dict(type="bob", amp=0.005, period=3.4 + 0.5 * (sp["i"] % 3), phase=0.25 * sp["i"]),
                        dict(type="wiggle", pivot=sp["pivot_bottom"], deg=1.4, period=4.2, phase=0.15 * sp["i"])],
    "ship": lambda sp: [dict(type="bob", amp=0.004, period=4.5, phase=0.1 * sp["i"]),
                        dict(type="drift", vx=(0.04 if sp["facing"] != "left" else -0.04), mode="linear")],
    "train": lambda sp: [dict(type="drift", vx=(0.20 if sp["facing"] != "left" else -0.20), mode="linear")],
    "car": lambda sp: [dict(type="drift", vx=(0.16 if sp["facing"] != "left" else -0.16), mode="linear")],
    "plane": lambda sp: [dict(type="drift", vx=(0.05 if sp["facing"] != "left" else -0.05), mode="linear")] if sp["cy"] > 0.35
    else [dict(type="drift", vx=(0.14 if sp["facing"] != "left" else -0.14), vy=-0.03, mode="linear")],
    "smoke": lambda sp: [dict(type="rise", amp=0.07, period=4.5, phase=0.37 * sp["i"], grow=0.18, pivot=sp["pivot_bottom"])],
    "flame": lambda sp: [dict(type="flicker", min=0.62, period=0.55, phase=0.2 * sp["i"])],
    "lights": lambda sp: [dict(type="twinkle", min=0.62, period=3.5 + sp["i"], phase=0.31 * sp["i"])],
    "stars": lambda sp: [dict(type="twinkle", min=0.25, period=2.6 + 0.9 * sp["i"], phase=0.37 * sp["i"])],
    "flag": lambda sp: [dict(type="wiggle", pivot=sp["pivot_top"], deg=7.0, period=1.7, phase=0.1 * sp["i"])],
    "balloon": lambda sp: [dict(type="bob", amp=0.008, period=4.0, phase=0.2 * sp["i"]), dict(type="drift", vx=0.03, vy=-0.03, mode="linear")],
}
KIND_TO_CUT = {"turbine": "rotor", "windmill": "rotor", "lights": "warm", "flame": "warm", "stars": "stars"}


def _bbox_px(bb, W, H, pad):
    x0, y0, x1, y1 = bb
    pw, ph = (x1 - x0) * pad, (y1 - y0) * pad
    return (max(0, int((x0 - pw) * W)), max(0, int((y0 - ph) * H)), min(W, int((x1 + pw) * W) + 1), min(H, int((y1 + ph) * H) + 1))


def _closed_regions(comp, box, tol=2):
    """ids of flat-colour regions that lie entirely inside the box (a closed object), with their pixel counts"""
    x0, y0, x1, y1 = box
    ids = np.unique(comp[y0:y1, x0:x1])
    ids = ids[ids > 0]
    if len(ids) == 0:
        return []
    objs = ndi.find_objects(comp, max_label=int(comp.max()))
    out = []
    for i in ids:
        sl = objs[int(i) - 1]
        if sl is None:
            continue
        ys, xs = sl
        if ys.start >= y0 - tol and ys.stop <= y1 + tol and xs.start >= x0 - tol and xs.stop <= x1 + tol:
            out.append(int(i))
    return out


def _with_outline(mask, outline, box, grow=5):
    x0, y0, x1, y1 = box
    near = cv2.dilate(mask.astype(np.uint8), np.ones((grow, grow), np.uint8)).astype(bool)
    o = near & outline
    sel = np.zeros_like(mask)
    sel[y0:y1, x0:x1] = True
    return mask | (o & sel)


def cut_region(rgb, comp, outline, bb, pad=0.14, colour_ok=None, count=1):
    """boat, fish, train, car, plane, smoke, bird, flag, balloon: the regions closed inside the box. `colour_ok(mean_saturation, mean_value)` keeps only some of them
    (smoke: the light, pale regions, not the red chimney rim or the grey chimney cap that happen to lie inside the same box)."""
    H, W = comp.shape
    box = _bbox_px(bb, W, H, pad)
    ids = _closed_regions(comp, box)
    if ids and count > 1:    # several items in the box (train cars, a school of fish): each is a SMALL region; a region as wide as the box is the viaduct, the quay or the road under them
        objs = ndi.find_objects(comp, max_label=int(comp.max()))
        bw = max(1, box[2] - box[0])
        ids = [i for i in ids if objs[i - 1] is not None and (objs[i - 1][1].stop - objs[i - 1][1].start) <= 0.55 * bw / (1 + 2 * 0.0)]
    if ids and colour_ok is not None:
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        ms = ndi.mean(hsv[..., 1].astype(np.float32), comp, ids)
        mv = ndi.mean(hsv[..., 2].astype(np.float32), comp, ids)
        ids = [i for i, a_, b_ in zip(ids, np.atleast_1d(ms), np.atleast_1d(mv)) if colour_ok(float(a_), float(b_))]
    if not ids:
        return None
    m = np.isin(comp, ids)
    m = _with_outline(m, outline, box)
    return m


def cut_by_ring(rgb, outline, bb, pad=0.10):
    """fallback when no flat-colour region is closed inside the box (a boat that touches the quay, a bird on a wall): everything inside the TIGHT box that does not look like the
    surroundings (the colours of a ring just outside the box) is the subject."""
    H, W, _ = rgb.shape
    x0, y0, x1, y1 = bb
    bx0, by0, bx1, by1 = int(x0 * W), int(y0 * H), int(x1 * W) + 1, int(y1 * H) + 1
    ex0, ey0, ex1, ey1 = _bbox_px(bb, W, H, pad)
    if bx1 - bx0 < 8 or by1 - by0 < 8:
        return None
    ring = np.zeros((H, W), bool)
    ring[ey0:ey1, ex0:ex1] = True
    ring[by0:by1, bx0:bx1] = False
    if ring.sum() < 50:
        return None
    Z = rgb[ring].reshape(-1, 3).astype(np.float32)
    k = min(4, len(Z))
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 15, 1.0)
    _, _, cen = cv2.kmeans(Z, k, None, crit, 2, cv2.KMEANS_PP_CENTERS)
    box = np.zeros((H, W), bool)
    box[by0:by1, bx0:bx1] = True
    dist = np.full((H, W), 1e9, np.float32)
    for c in cen:
        dist = np.minimum(dist, np.abs(rgb.astype(np.float32) - c).sum(-1))
    fg = (dist > 42) & box
    fg = cv2.morphologyEx(fg.astype(np.uint8), cv2.MORPH_OPEN, np.ones((3, 3), np.uint8)).astype(bool)
    n, lab, st, _ = cv2.connectedComponentsWithStats(fg.astype(np.uint8), connectivity=8)
    keep = np.zeros((H, W), bool)
    for i in range(1, n):
        if st[i, cv2.CC_STAT_AREA] >= 60:
            keep |= lab == i
    area = keep.sum()
    boxa = (bx1 - bx0) * (by1 - by0)
    if area < 0.06 * boxa or area > 0.8 * boxa:
        return None
    return cv2.dilate(keep.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)


def cut_rotor(rgb, comp, outline, sub, cloud, hubs=(), sub_sky=None):
    """turbine / windmill rotor: the light regions inside the circle around the hub (the shaft runs out of the circle)"""
    H, W = comp.shape
    x0, y0, x1, y1 = sub["bbox"]
    hx, hy = sub["hub"]
    # blade length: from the hub to the far edge of the box above and to the sides (the box also holds the shaft below the hub)
    Rpx = 1.1 * max((hx - x0) * W, (x1 - hx) * W, (hy - y0) * H)   # blade length in pixels (x and y are different scales)
    yy, xx = np.mgrid[0:H, 0:W]
    inside = ((xx - hx * W) ** 2 + (yy - hy * H) ** 2) <= Rpx ** 2
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    light = (hsv[..., 2] > 110) & (hsv[..., 1] < 115)      # cream blades and their grey shaded sides; sky and hills are more saturated
    objs = ndi.find_objects(comp, max_label=int(comp.max()))
    ids = []
    cx0, cy0 = max(0, int(hx * W - Rpx) - 2), max(0, int(hy * H - Rpx) - 2)
    cx1, cy1 = min(W, int(hx * W + Rpx) + 3), min(H, int(hy * H + Rpx) + 3)
    cand = np.unique(comp[cy0:cy1, cx0:cx1])
    for i in cand[cand > 0]:
        sl = objs[int(i) - 1]
        if sl is None:
            continue
        reg = comp[sl] == i
        ys, xs = np.where(reg)
        ys = ys + sl[0].start
        xs = xs + sl[1].start
        frac_in = inside[ys, xs].mean()
        frac_light = light[ys, xs].mean()
        if len(hubs) > 1:    # a region belongs to the nearest hub (neighbouring turbines overlap in the circle)
            mx, my = xs.mean() / W, ys.mean() / H
            near = min(hubs, key=lambda h: ((h[0] - mx) * W) ** 2 + ((h[1] - my) * H) ** 2)
            if abs(near[0] - hx) > 1e-9 or abs(near[1] - hy) > 1e-9:
                continue
        if sub.get("kind") == "windmill":     # the wooden cap and body of a windmill are warm brown: only the sails (grey / dark lattice) turn
            if float(rgb[ys, xs, 0].mean()) - float(rgb[ys, xs, 2].mean()) > 12:     # warm (brown wood: red clearly above blue); the lattice of the sails is black / grey / blue-grey
                continue
        bw_, bh_ = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
        shaft_like = bh_ > 2.2 * bw_ and abs(xs.mean() - hx * W) < 0.12 * Rpx and ys.mean() > hy * H      # a narrow upright piece right under the hub is the top of the shaft
        if frac_in >= 0.96 and frac_light >= 0.6 and not cloud[ys, xs].mean() > 0.5 and not shaft_like:
            ids.append(int(i))
    if not ids:
        return None
    m = np.isin(comp, ids)
    # second pass: the thin dark-navy strokes drawn along the blades are flat-colour regions too (not 'outline' pixels); take the ones that hug the blades
    near = cv2.dilate(m.astype(np.uint8), np.ones((21, 21), np.uint8)).astype(bool)
    dark = hsv[..., 2] < 150
    for i in cand[cand > 0]:
        if int(i) in ids:
            continue
        sl = objs[int(i) - 1]
        if sl is None:
            continue
        reg = comp[sl] == i
        ys, xs = np.where(reg)
        ys = ys + sl[0].start
        xs = xs + sl[1].start
        if len(ys) < 4000 and inside[ys, xs].mean() >= 0.97 and dark[ys, xs].mean() >= 0.8 and near[ys, xs].mean() >= 0.7 and not cloud[ys, xs].mean() > 0.5:
            m |= comp == i
    # third pass, by pixel: anything within ~14 px of the blades that is not sky colour and not part of a big region (shaft, hills) is stroke or anti-aliasing of the blades
    prot = []
    for i in cand[cand > 0]:       # a region that runs out of the circle and is not dark ink (the cream shaft, hills) is not part of the rotor, whatever its size
        i = int(i)
        sl = objs[i - 1]
        if i in ids or sl is None:
            continue
        ys, xs = np.where(comp[sl] == i)
        yy_, xx_ = ys + sl[0].start, xs + sl[1].start
        if inside[yy_, xx_].mean() < 0.9 and (sub_sky is None or sub_sky[yy_, xx_].mean() < 0.5) and hsv[..., 2][yy_, xx_].mean() >= 135:
            prot.append(i)         # (dark navy strokes run out of the circle too, and form one network with the hub and shaft outlines: those are blade ink, they go)
    big = np.isin(comp, prot)
    big = cv2.dilate(big.astype(np.uint8), np.ones((15, 15), np.uint8)).astype(bool)     # and its outline stroke (6 px) plus margin
    skycol = np.median(rgb[sub_sky], axis=0) if sub_sky is not None and sub_sky.any() else np.array([110, 190, 250])
    dsky = np.abs(rgb.astype(int) - skycol).sum(-1)
    inkpx = hsv[..., 2] < 135
    creampx = (hsv[..., 1] < 95) & (hsv[..., 2] >= 110)
    halo = cv2.dilate(m.astype(np.uint8), np.ones((51, 51), np.uint8)).astype(bool) & inside & (inkpx | creampx) & (dsky > 18) & ~big
    m = m | halo
    n_, lab_, st_, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8), connectivity=8)       # drop dotted fragments (bits of the shaft's outline): they stay with the shaft
    keepm = np.zeros(m.shape, bool)
    for j in range(1, n_):
        if st_[j, cv2.CC_STAT_AREA] >= 400:
            keepm |= lab_ == j
    m = keepm
    # hub: the small outlined disc at the pivot belongs to the rotor even when it is not 'light'
    m = _with_outline(m, outline, (cx0, cy0, cx1, cy1), grow=17) & inside
    return m


def cut_warm(rgb, comp, outline, bb, pad=0.06):
    """lit windows, flames, lava: the warm bright regions inside the box"""
    H, W = comp.shape
    x0, y0, x1, y1 = _bbox_px(bb, W, H, pad)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    warm = (hsv[..., 0] <= 38) | (hsv[..., 0] >= 170)
    bright = (hsv[..., 1] > 70) & (hsv[..., 2] > 170) & warm
    box = np.zeros((H, W), bool)
    box[y0:y1, x0:x1] = True
    m = bright & box
    m = cv2.morphologyEx(m.astype(np.uint8), cv2.MORPH_OPEN, np.ones((2, 2), np.uint8)).astype(bool)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8))
    keep = np.zeros_like(m)
    for i in range(1, n):
        if 12 <= st[i, cv2.CC_STAT_AREA] <= 0.5 * (x1 - x0) * (y1 - y0):
            keep |= lab == i
    return keep if keep.any() else None


def cut_stars(rgb, sky, dark_top):
    """small bright dots in a dark sky (night scenes), split in two groups for different twinkle phases"""
    H, W, _ = rgb.shape
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    bright = (hsv[..., 2] > 200) & (hsv[..., 1] < 150)
    area = np.zeros((H, W), bool)
    area[: int(H * 0.5)] = True
    m = bright & area & dark_top
    n, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8))
    A = np.zeros((H, W), bool)
    B = np.zeros((H, W), bool)
    k = 0
    for i in range(1, n):
        if 6 <= st[i, cv2.CC_STAT_AREA] <= 900 and max(st[i, cv2.CC_STAT_WIDTH], st[i, cv2.CC_STAT_HEIGHT]) <= 45:
            (A if k % 2 == 0 else B).__ior__(lab == i)
            k += 1
    return [m_ for m_ in (A, B) if m_.sum() >= 20]


def make_sprites(rgb, comp, outline, sky, cloud, subjects):
    """list of dict(kind, mask, tags, ...) from the audit subjects (+ automatic stars)"""
    H, W = comp.shape
    sprites = []
    idx = {}
    for sub in subjects:
        k = sub["kind"]
        if k in ("other", "windmill"):      # windmill sails cannot be told from the dark roof and cap that sit at the hub: they stay still (docs/VECTOR_CATALOG.md, known limits)
            continue
        cut = KIND_TO_CUT.get(k)
        if cut == "rotor":
            if not sub.get("hub"):
                continue
            m = cut_rotor(rgb, comp, outline, sub, cloud, hubs=[tuple(x["hub"]) for x in subjects if x.get("hub") and KIND_TO_CUT.get(x["kind"]) == "rotor"], sub_sky=sky)
        elif cut == "warm":
            m = cut_warm(rgb, comp, outline, sub["bbox"])
        else:
            m = cut_region(rgb, comp, outline, sub["bbox"], colour_ok=(lambda sat, val: val >= 165 and sat < 135) if k == "smoke" else None, count=int(sub.get("count") or 1) if k in ("train", "car", "plane") else 1)
            if m is None or not m.any() or m.sum() < 0.04 * max(1.0, (sub["bbox"][2] - sub["bbox"][0]) * W * (sub["bbox"][3] - sub["bbox"][1]) * H):
                m = cut_by_ring(rgb, outline, sub["bbox"])
        if m is None or not m.any():
            continue
        area = m.sum()
        bx0, by0, bx1, by1 = sub["bbox"]
        boxa = max(1.0, (bx1 - bx0) * W * (by1 - by0) * H)
        if area < 40 or area > 1.5 * boxa * (2.0 if cut == "rotor" else 1.0) or area > 0.25 * W * H:       # a long train fills its box: only a region far bigger than the box is the scenery
            continue
        ys, xs = np.where(m)
        i = idx.get(k, 0)
        idx[k] = i + 1
        cx, cy = float(xs.mean()) / W, float(ys.mean()) / H
        if cut == "rotor":
            pivot = [sub["hub"][0], sub["hub"][1]]
        else:
            pivot = [cx, cy]
        sp = dict(kind=k, mask=m, i=i, facing=sub.get("facing", "none"), cx=cx, cy=cy, pivot=pivot,
                  pivot_bottom=[cx, float(ys.max()) / H], pivot_top=[float(xs.min()) / W if sub.get("facing") != "left" else float(xs.max()) / W, float(ys.min()) / H])
        sp["tags"] = DEFAULT_TAGS.get(k, lambda s: [])(sp)
        if sp["tags"]:
            sprites.append(sp)
    return sprites


def build(src, out, cuts, name, subjects, tall=False, nosky=False, motion_cb=None, vkw=None, auto_stars=True, merge=None):
    """vector_scene_build.build() plus object-aware depth, clean cloud detection and sprite layers. Returns (stats, sprite_report)."""
    import sys

    from PIL import Image

    HERE = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, HERE)
    import vector_objects as vo
    import vector_scene_build as vsb

    os.makedirs(out, exist_ok=True)
    im = Image.open(src).convert("RGB")
    if not tall:
        im = vsb.crop169(im)
    rgb = np.asarray(im)
    d = vsb.depth_map(im)
    keep_cfg = (vo.EDGE_T, vo.RANGE_CAP)
    if merge:                       # a solid structure whose parts the depth model ramps a lot (a space station, antenna dishes): merge more strongly
        vo.EDGE_T, vo.RANGE_CAP = merge
    try:
        rd, outline, comp = vo.object_regions(vsb.regions, rgb, d)
    finally:
        vo.EDGE_T, vo.RANGE_CAP = keep_cfg
    if nosky:
        sky = np.zeros(comp.shape, bool)
    else:
        sky = vsb.sky_mask(rgb, comp)
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        fringe = cv2.dilate(sky.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool) & ~sky & (hsv[..., 2] > 110) & ~outline
        sky = sky | fringe
    cl = vo.cloud_mask_objects(vsb.cloud_mask, rgb, sky, outline) if (not nosky and sky.any()) else np.zeros(sky.shape, bool)
    if cl.any():
        skycol = np.median(rgb[sky & ~cl], axis=0) if (sky & ~cl).any() else np.median(rgb[sky], axis=0)
        dist = np.abs(rgb.astype(int) - skycol).sum(-1)
        grown = cv2.dilate(cl.astype(np.uint8), np.ones((17, 17), np.uint8)).astype(bool)
        cl = cl | (grown & (dist > 45))
        cl = cv2.morphologyEx(cl.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((5, 5), np.uint8)).astype(bool)
        cl = ndi.binary_fill_holes(cl)
    sky = sky | cl
    # ---- sprites
    subs = list(subjects or [])
    sprites = make_sprites(rgb, comp, outline, sky, cl, subs)
    if auto_stars:
        hsv0 = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        top = hsv0[: int(rgb.shape[0] * 0.3), :, 2]
        if top.mean() < 110:
            dark = cv2.erode((hsv0[..., 2] < 130).astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool)
            dark = cv2.dilate(dark.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool) | (hsv0[..., 2] < 130)
            for j, m in enumerate(cut_stars(rgb, sky, np.ones(dark.shape, bool))):
                sp = dict(kind="stars", mask=m, i=j, facing="none", cx=0.5, cy=0.2, pivot=[0.5, 0.2], pivot_bottom=[0.5, 0.2], pivot_top=[0.5, 0.2])
                sp["tags"] = DEFAULT_TAGS["stars"](sp)
                sprites.append(sp)
    S = np.zeros(comp.shape, bool)
    for sp in sprites:
        sp["mask"] = sp["mask"] & ~S
        S |= sp["mask"]
    Sd = cv2.dilate(S.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool) if S.any() else S
    cl = cl & ~Sd
    # ---- bands
    band = np.where(sky & ~Sd, 0, 1 + vsb.bands_from(rd, cuts)).astype(np.float32)
    for sp in sprites:
        mk = sp["mask"]
        host = int(np.round(np.median(band[cv2.dilate(mk.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool) & ~Sd]))) if (cv2.dilate(mk.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool) & ~Sd).any() else 1
        if sp["kind"] in ("stars",):
            host = 0
        elif sp["kind"] in ("turbine", "windmill"):
            host = int(np.round(np.median(band[mk]))) if mk.any() else host
        sp["host"] = max(0, host)
    nb = len(cuts) + 2
    # the sprite's own pixels leave the layers: 'host - 0.5' (opaque plate below, transparent from the host layer up)
    for sp in sprites:
        spd = cv2.dilate(sp["mask"].astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
        band[spd & (band >= 0)] = np.minimum(band[spd & (band >= 0)], sp["host"] - 0.5) if sp["host"] > 0 else -0.5
    # layers back to front: layer k keeps the pixels of band k; its alpha is band >= k; a hole (nearer band) is filled with the nearest same-band colour
    outl = outline.astype(np.uint8)
    layers = {}
    ks = [k for k in range(nb) if (band == k).any()]
    for k in ks:
        keep = band == k
        src_ok = cv2.erode((keep & ~cv2.dilate(outl, np.ones((5, 5), np.uint8)).astype(bool)).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
        col = vsb.fill_behind(rgb, keep, src_ok)
        a = np.ones(band.shape, bool) if k == ks[0] else (band >= k)       # the farthest layer is opaque
        layers[k] = np.dstack([col, (a * 255).astype(np.uint8)])
    if cl.any() and ks and ks[0] in layers:
        k0 = ks[0]
        base0 = vsb.fill_behind(layers[k0][..., :3], ~cv2.dilate(cl.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool),
                                ~cv2.dilate(cl.astype(np.uint8), np.ones((9, 9), np.uint8)).astype(bool) & ~cv2.dilate(outl, np.ones((3, 3), np.uint8)).astype(bool)
                                & (cv2.cvtColor(layers[k0][..., :3], cv2.COLOR_RGB2HSV)[..., 0] >= 80))
        layers[k0] = np.dstack([base0, layers[k0][..., 3]])
    if sprites and sky.any() and ks and ks[0] == 0 and (sky & ~Sd).any():       # flat sky behind the holes (nearest-pixel fill would copy anti-aliasing smears)
        skycol0 = np.median(rgb[sky & ~Sd & ~cl], axis=0) if (sky & ~Sd & ~cl).any() else np.median(rgb[sky & ~Sd], axis=0)
        region = cv2.dilate(Sd.astype(np.uint8), np.ones((31, 31), np.uint8)).astype(bool)
        col0 = layers[0][..., :3].astype(int)
        snap = region & (np.abs(col0 - skycol0).sum(-1) < 90)
        col0[snap] = skycol0.astype(int)
        layers[0] = np.dstack([col0.astype(np.uint8), layers[0][..., 3]])
    stack = []
    present = sorted(layers)
    for k in present:
        mt = dict(z=k / (nb - 1))
        stack.append((("sky" if k == ks[0] and k == 0 else f"layer{k}"), layers[k], mt, k))
        if k == ks[0] and cl.any():
            stack.append(("clouds", np.dstack([rgb, (cl * 255).astype(np.uint8)]), dict(z=0.05, drift=0.012), 0))
        for j, sp in enumerate(sprites):
            if sp["host"] == k:
                ys, xs = np.where(sp["mask"])
                arr = np.dstack([rgb, (cv2.dilate(sp["mask"].astype(np.uint8), np.ones((3, 3), np.uint8)) * 255).astype(np.uint8)])
                mt2 = dict(z=k / (nb - 1), sprite=True, kind=sp["kind"], tags=sp["tags"])
                stack.append((f"sprite_{sp['kind']}{sp['i']}", arr, mt2, k))
    # sprites whose host layer is absent go on top of the nearest lower present layer
    placed = {n for n, *_ in stack}
    for sp in sprites:
        nm = f"sprite_{sp['kind']}{sp['i']}"
        if nm not in placed:
            lowers = [k for k in present if k <= sp["host"]] or [present[0]]
            kk = lowers[-1]
            at = max(i for i, (n, _, _, k) in enumerate(stack) if k == kk and not n.startswith("sprite_")) + 1
            arr = np.dstack([rgb, (cv2.dilate(sp["mask"].astype(np.uint8), np.ones((3, 3), np.uint8)) * 255).astype(np.uint8)])
            stack.insert(at, (nm, arr, dict(z=kk / (nb - 1), sprite=True, kind=sp["kind"], tags=sp["tags"]), kk))
    meta, stats = [], []
    for i, (nm, arr, mt, _k) in enumerate(stack):
        png = os.path.join(out, f"{i}_{nm}.png")
        Image.fromarray(arr, "RGBA").save(png)
        svg = os.path.join(out, f"{i}_{nm}.svg")
        size, paths = vsb.vec(png, svg, **(vkw or {}))
        stats.append((nm, size // 1024, paths))
        meta.append(dict(file=f"{i}_{nm}.svg", name=nm, **mt))
    man = dict(name=name, aspect=[2, 3] if tall else [16, 9], source_size=list(im.size), layers=meta, motion={})
    if motion_cb:
        motion_cb(man)
    json.dump(man, open(os.path.join(out, "manifest.json"), "w"), indent=1)
    for f in os.listdir(out):
        if f.endswith(".png"):
            os.remove(os.path.join(out, f))
    rep = [dict(kind=sp["kind"], host=sp["host"], px=int(sp["mask"].sum()), tags=[t["type"] for t in sp["tags"]]) for sp in sprites]
    return stats, rep
