#!/usr/bin/env python3
"""Cut a rig-parts sheet (vector_character_sheet.py) into pieces, vectorise each piece with vtracer and write a character folder for engine/vector_character.py.

  python backend/scripts/vector_character_build.py SHEET.png --id mia --out backend/lambdas/engine/assets/vector_characters

Offline tool (never runs in Lambda). The sheet has a fixed order (row 1: head, torso, upper arm, lower arm; row 2: upper leg, lower leg, eyes open, eyes closed; row 3: closed,
half open and wide open mouth). Pieces are found as connected shapes of the sheet's own transparency, then named by reading order, so a sheet with another count is refused.
For every piece the folder gets `<name>.svg` and the manifest records its size in source pixels and its joints (pivot = where it hangs, end = where the next piece hangs).
"""
import argparse
import json
import os
import sys
from typing import Any, Dict, List, Tuple

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

TORSO_CUT = {"mia": 0.17, "leo": 0.16, "nora": 0.17, "sam": 0.23}   # fraction of the torso width cut away on each side, by eye per character
NAMES = ["head", "torso", "upper_arm", "lower_arm", "upper_leg", "lower_leg", "eyes_open", "eyes_closed", "mouth_closed", "mouth_half", "mouth_wide"]
OUTLINE = (20, 18, 24, 0)


def find_pieces(rgba: np.ndarray) -> List[Tuple[Tuple[int, int, int, int], np.ndarray]]:
    """-> [((x0, y0, x1, y1), boolean mask over the bbox)] in reading order (rows by y, then x). Eye pairs are merged into one piece."""
    solid = rgba[..., 3] >= 200
    lab, n = ndi.label(ndi.binary_dilation(solid, iterations=5))
    boxes = []
    for i, s in enumerate(ndi.find_objects(lab), 1):
        if s is None:
            continue
        y0, y1, x0, x1 = s[0].start, s[0].stop, s[1].start, s[1].stop
        if (y1 - y0) * (x1 - x0) < 900:
            continue   # specks
        boxes.append([x0, y0, x1, y1, i])
    # merge the two eyes of a pair: small shapes side by side on one row
    merged = True
    while merged:
        merged = False
        for a in range(len(boxes)):
            for b in range(a + 1, len(boxes)):
                A, B = boxes[a], boxes[b]
                small = max(A[2] - A[0], A[3] - A[1], B[2] - B[0], B[3] - B[1]) < 220
                gap = max(A[0], B[0]) - min(A[2], B[2])
                cy = abs((A[1] + A[3]) / 2 - (B[1] + B[3]) / 2)
                if small and gap < 110 and cy < 50:
                    boxes[a] = [min(A[0], B[0]), min(A[1], B[1]), max(A[2], B[2]), max(A[3], B[3]), A[4]]
                    lab[lab == B[4]] = A[4]
                    del boxes[b]
                    merged = True
                    break
            if merged:
                break
    rows: List[List[list]] = []
    for bx in sorted(boxes, key=lambda b: (b[1] + b[3]) / 2):
        for r in rows:
            if abs((r[0][1] + r[0][3]) / 2 - (bx[1] + bx[3]) / 2) < 140:
                r.append(bx)
                break
        else:
            rows.append([bx])
    ordered = [b for r in rows for b in sorted(r, key=lambda b: b[0])]
    out = []
    for x0, y0, x1, y1, i in ordered:
        out.append(((x0, y0, x1, y1), lab[y0:y1, x0:x1] == i))
    return out


def cut(rgba: np.ndarray, box: Tuple[int, int, int, int], mask: np.ndarray) -> Image.Image:
    x0, y0, x1, y1 = box
    part = rgba[y0:y1, x0:x1].copy()
    keep = mask & (part[..., 3] >= 200)
    part[~keep] = OUTLINE
    part[keep, 3] = 255
    im = Image.fromarray(part)
    bb = im.getbbox()
    pad = 3
    bb = (max(0, bb[0] - pad), max(0, bb[1] - pad), min(im.width, bb[2] + pad), min(im.height, bb[3] + pad))
    return im.crop(bb)


def trim_sleeves(im: Image.Image, frac: float) -> Image.Image:
    """The torso drawing has its own hanging sleeves; the rig has separate arms, so the sides of the torso below the shoulders are cut away (a vest) and closed with an outline."""
    a = np.array(im)
    h, w = a.shape[:2]
    y0 = int(h * 0.24)
    cx0, cx1 = int(w * frac), int(w * (1 - frac))
    t = max(5, w // 55)
    inner = a[..., 3].copy()                       # what stays solid, read before anything is erased
    a[y0:, :cx0] = OUTLINE
    a[y0:, cx1:] = OUTLINE
    ink = (20, 18, 24, 255)
    for y in range(y0, h):
        if inner[y, cx0 + t + 2] > 0:
            a[y, cx0:cx0 + t] = ink
        if inner[y, cx1 - t - 3] > 0:
            a[y, cx1 - t:cx1] = ink
    out = Image.fromarray(a)
    return out.crop(out.getbbox())


def edge_x(im: Image.Image, top: bool, rows: float = 0.03) -> float:
    """Mean x of the solid pixels in the top (or bottom) few percent of rows: where a limb piece meets the joint."""
    a = np.array(im)[..., 3] > 0
    k = max(2, int(a.shape[0] * rows))
    band = a[:k] if top else a[-k:]
    xs = np.nonzero(band.any(axis=0))[0]
    return float((xs.min() + xs.max()) / 2) if xs.size else a.shape[1] / 2


def trace(im: Image.Image, svg_path: str, tmp_png: str) -> int:
    import vtracer

    big = im.resize((im.width * 2, im.height * 2), Image.LANCZOS)
    arr = np.array(big)
    arr[..., 3] = np.where(arr[..., 3] >= 128, 255, 0)
    Image.fromarray(arr).save(tmp_png)
    vtracer.convert_image_to_svg_py(tmp_png, svg_path, colormode="color", hierarchical="cutout", mode="spline", filter_speckle=6, color_precision=6, layer_difference=12,
                                    corner_threshold=80, length_threshold=4.0, max_iterations=10, splice_threshold=45, path_precision=3)
    return os.path.getsize(svg_path)


def build(sheet: str, cid: str, out_root: str) -> Dict[str, Any]:
    rgba = np.array(Image.open(sheet).convert("RGBA"))
    pieces = find_pieces(rgba)
    if len(pieces) != len(NAMES):
        raise SystemExit(f"{sheet}: found {len(pieces)} pieces, expected {len(NAMES)}: regenerate the sheet")
    folder = os.path.join(out_root, cid)
    os.makedirs(folder, exist_ok=True)
    man: Dict[str, Any] = {"id": cid, "parts": {}}
    for name, (box, mask) in zip(NAMES, pieces):
        im = cut(rgba, box, mask)
        if name == "torso":
            im = trim_sleeves(im, TORSO_CUT.get(cid, 0.17))
        size = trace(im, os.path.join(folder, name + ".svg"), os.path.join(folder, "_tmp.png"))
        w, h = im.size
        part: Dict[str, Any] = {"file": name + ".svg", "w": w, "h": h, "svg_bytes": size}
        if name in ("head", "torso"):
            part["pivot"] = [w / 2, h]                                    # neck / waist: bottom centre
        elif name in ("upper_arm", "lower_arm", "upper_leg", "lower_leg"):
            part["pivot"] = [edge_x(im, True), 0.0]                       # hangs from its top centre
            part["end"] = [edge_x(im, False), float(h)]                   # the next piece hangs here
        else:
            part["pivot"] = [w / 2, h / 2]
        man["parts"][name] = part
    os.remove(os.path.join(folder, "_tmp.png"))
    with open(os.path.join(folder, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f, indent=1)
    return man


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sheet")
    ap.add_argument("--id", required=True)
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "..", "lambdas", "engine", "assets", "vector_characters"))
    a = ap.parse_args()
    man = build(a.sheet, a.id, a.out)
    tot = sum(p["svg_bytes"] for p in man["parts"].values())
    print(a.id, {k: (v["w"], v["h"]) for k, v in man["parts"].items()}, f"svg total {tot / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
