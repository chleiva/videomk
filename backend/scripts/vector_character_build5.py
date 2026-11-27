#!/usr/bin/env python3
"""Build the five-character cast (docs/CHARACTER_LIBRARY.md) from the rig-parts sheets with the same cutter as vector_character_build.py.

  python backend/scripts/vector_character_build5.py SHEETS_DIR [--only ID ...] [--cut ID=0.2 ...]
"""
import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
from scipy import ndimage as ndi  # noqa: E402

import vector_character_build as vb  # noqa: E402


def find_pieces(rgba):
    """vb.find_pieces plus: the eye sets of these sheets carry eyebrows ABOVE the eyes (separate shapes): stacked small shapes are merged into one piece."""
    solid = rgba[..., 3] >= 200
    lab, n = ndi.label(ndi.binary_dilation(solid, iterations=5))
    boxes = []
    for i, s in enumerate(ndi.find_objects(lab), 1):
        if s is None:
            continue
        y0, y1, x0, x1 = s[0].start, s[0].stop, s[1].start, s[1].stop
        if (y1 - y0) * (x1 - x0) < 900:
            continue
        boxes.append([x0, y0, x1, y1, i])

    def merge_pass(test):
        merged = True
        while merged:
            merged = False
            for a in range(len(boxes)):
                for b in range(a + 1, len(boxes)):
                    A, B = boxes[a], boxes[b]
                    if test(A, B):
                        boxes[a] = [min(A[0], B[0]), min(A[1], B[1]), max(A[2], B[2]), max(A[3], B[3]), A[4]]
                        lab[lab == B[4]] = A[4]
                        del boxes[b]
                        merged = True
                        break
                if merged:
                    break

    def side(A, B):
        small = max(A[2] - A[0], A[3] - A[1], B[2] - B[0], B[3] - B[1]) < 220
        gap = max(A[0], B[0]) - min(A[2], B[2])
        cy = abs((A[1] + A[3]) / 2 - (B[1] + B[3]) / 2)
        return small and gap < 110 and cy < 50

    def stacked(A, B):
        for X in (A, B):
            if X[3] - X[1] > 230 or X[2] - X[0] > 420:
                return False
        ov = min(A[2], B[2]) - max(A[0], B[0])
        vgap = max(A[1], B[1]) - min(A[3], B[3])
        return ov > 0.5 * min(A[2] - A[0], B[2] - B[0]) and vgap < 110

    merge_pass(side)      # eyebrows pair, eye pair
    merge_pass(stacked)   # brows over eyes
    rows = []
    for bx in sorted(boxes, key=lambda b: (b[1] + b[3]) / 2):
        for r in rows:
            if abs((r[0][1] + r[0][3]) / 2 - (bx[1] + bx[3]) / 2) < 140:
                r.append(bx)
                break
        else:
            rows.append([bx])
    ordered = [b for r in rows for b in sorted(r, key=lambda b: b[0])]
    return [((x0, y0, x1, y1), lab[y0:y1, x0:x1] == i) for x0, y0, x1, y1, i in ordered]


vb.find_pieces = find_pieces

# fraction of the torso width cut away at each side (the torso art has its own hanging sleeves, the rig has separate arms): set by eye per character
CUT = {"ines": 0.17, "david": 0.16, "priya": 0.17, "mateo": 0.17, "fox": 0.2}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("sheets")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--cut", nargs="*", default=[])
    ap.add_argument("--out", default=os.path.join(HERE, "..", "lambdas", "engine", "assets", "vector_characters"))
    a = ap.parse_args()
    for c in a.cut:
        k, v = c.split("=")
        CUT[k] = float(v)
    vb.TORSO_CUT.update(CUT)
    for cid in CUT:
        if a.only and cid not in a.only:
            continue
        man = vb.build(os.path.join(a.sheets, f"sheet_{cid}.png"), cid, a.out)
        tot = sum(p["svg_bytes"] for p in man["parts"].values())
        print(cid, f"svg total {tot / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
