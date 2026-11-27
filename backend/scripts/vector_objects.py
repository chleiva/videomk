"""Object-aware depth for the cartoon scene builder: whole objects move as one piece, so a parallax shift never tears a tower, a lighthouse or a tree in two.

vector_scene_build.regions() gives every flat-colour region ONE depth, but an object is several regions (a tower is a white body, a grey shade side, a base block,
a nacelle...) and the depth model ramps along it, so a depth cut used to slice through the object ("the wind turbines break at the base").
`object_regions` wraps regions(): regions that touch each other (also across a thin outline stroke) and whose depths are close are merged into one object by
agglomerative merging (smallest depth difference first, the merged depth range is capped), and the object gets ONE depth (area-weighted median) before the bands are cut.
Big ground planes still keep a range of depths, because the cap stops the chain.
"""
import cv2
import numpy as np
from scipy import ndimage as ndi

EDGE_T = 0.12    # two touching regions merge when their depths differ by less than this
RANGE_CAP = 0.26  # ... and the merged object's depth range stays under this (stops a ground plane chaining into one band)
MIN_BOUNDARY = 6  # px of shared boundary needed to count as touching (avoids merging by a corner)


def merge_objects(comp, depth_by_comp, sizes, outline):
    """Union-find over the region adjacency graph. Returns lut: comp id -> object depth (0 where the region has no valid depth)."""
    n = len(depth_by_comp) - 1
    valid = sizes > 0
    # nearest labelled region for every pixel, so two regions separated only by an outline stroke count as touching
    lab = comp.copy()
    hole = lab == 0
    if hole.any() and (~hole).any():
        _, (iy, ix) = ndi.distance_transform_edt(hole, return_indices=True)
        lab = lab[iy, ix]
    pairs = {}
    for a, b in ((lab[:, :-1], lab[:, 1:]), (lab[:-1, :], lab[1:, :])):
        m = a != b
        key = np.minimum(a[m], b[m]).astype(np.int64) * (n + 1) + np.maximum(a[m], b[m])
        u, c = np.unique(key, return_counts=True)
        for k, cnt in zip(u, c):
            pairs[int(k)] = pairs.get(int(k), 0) + int(cnt)
    parent = list(range(n + 1))
    lo = list(depth_by_comp)
    hi = list(depth_by_comp)

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    edges = []
    for k, cnt in pairs.items():
        a, b = divmod(k, n + 1)
        if a == 0 or b == 0 or not (valid[a] and valid[b]) or cnt < MIN_BOUNDARY:
            continue
        edges.append((abs(depth_by_comp[a] - depth_by_comp[b]), a, b))
    edges.sort()
    for diff, a, b in edges:
        if diff > EDGE_T:
            break
        ra, rb = find(a), find(b)
        if ra == rb:
            continue
        nlo, nhi = min(lo[ra], lo[rb]), max(hi[ra], hi[rb])
        if nhi - nlo > RANGE_CAP:
            continue
        parent[rb] = ra
        lo[ra], hi[ra] = nlo, nhi
    roots = np.array([find(i) for i in range(n + 1)])
    lut = np.zeros(n + 1, np.float32)
    for r in np.unique(roots[1:]):
        members = np.where((roots == r) & valid)[0]
        members = members[members > 0]
        if len(members) == 0:
            continue
        w = sizes[members]
        order = np.argsort(depth_by_comp[members])
        cw = np.cumsum(w[order])
        med = depth_by_comp[members][order][np.searchsorted(cw, cw[-1] / 2)]
        lut[members] = med
    return lut


def object_regions(regions_fn, rgb, depth, **kw):
    """Drop-in for vector_scene_build.regions(rgb, depth): same return (depth map, outline, comp) with merged object depths."""
    out, outline, comp = regions_fn(rgb, depth, **kw)
    n = int(comp.max())
    if n < 2:
        return out, outline, comp
    idx = np.arange(1, n + 1)
    sizes = np.zeros(n + 1, np.float32)
    sizes[1:] = ndi.sum(np.ones(comp.shape, np.float32), comp, idx)
    dep = np.zeros(n + 1, np.float32)
    dep[1:] = ndi.median(out, comp, idx)
    min_px = kw.get("min_px", 120)
    s2 = np.where(sizes >= min_px, sizes, 0)
    lut = merge_objects(comp, dep, s2, outline)
    valid = (lut[comp] > 0) & (comp > 0)
    rdv = np.where(valid, lut[comp], 0).astype(np.float32)
    grow = cv2.dilate(rdv, np.ones((9, 9), np.uint8))
    new = np.where(valid, lut[comp], grow)
    new = np.where(new > 0, new, out)
    return new, outline, comp


def cloud_mask_objects(orig_cloud_mask, rgb, sky, outline=None):
    """vector_scene_build.cloud_mask() keeps every light shape that floats in the sky, which also caught white wind-turbine blades, shafts and nacelles
    (they drifted as clouds and tore away from their bases). A cloud is a compact blob (solidity = area / convex hull area >= 0.4; blades, towers and
    branching shapes score 0.2) that is not surrounded by ground: reject a candidate that is thin or whose surroundings are mostly non-sky colour."""
    m = orig_cloud_mask(rgb, sky, outline)
    if not m.any():
        return m
    n, lab, st, _ = cv2.connectedComponentsWithStats(m.astype(np.uint8))
    skycol = np.median(rgb[sky & ~m], axis=0) if (sky & ~m).any() else np.array([100, 190, 250])
    dist = np.abs(rgb.astype(int) - skycol).sum(-1)
    keep = np.zeros(m.shape, bool)
    for i in range(1, n):
        comp = lab == i
        area = int(st[i, cv2.CC_STAT_AREA])
        cnts, _ = cv2.findContours(comp.astype(np.uint8), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        hull_area = sum(cv2.contourArea(cv2.convexHull(c)) for c in cnts) or 1.0
        solidity = area / hull_area
        k = lambda z: cv2.dilate(comp.astype(np.uint8), np.ones((z, z), np.uint8)).astype(bool)
        ring = k(31) & ~k(15)
        frac_other = (ring & ~comp & (dist > 70)).sum() / max(1, ring.sum())
        if solidity >= 0.4 and frac_other < 0.5:
            keep |= comp
    return keep
