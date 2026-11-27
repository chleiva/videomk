#!/usr/bin/env python3
"""Look at the reveal order: for each drawing of a sheet, a strip of the art at 8 moments of its reveal, strategy A (scan) above strategy B (human).

  preview_order.py sheet1 [sheet2]   -> WORK/order_<sheet>.jpg ; prints stroke counts, pen lengths and line widths
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import wbcommon as common  # noqa: E402
import gen_art  # noqa: E402
import trace  # noqa: E402

STEPS = [0.1, 0.2, 0.35, 0.5, 0.65, 0.8, 0.9, 1.0]


def strip(alpha, strategy, cell=220):
    tr = trace.trace(alpha, strategy)
    T, times, total = trace.time_map(alpha, tr["strokes"], tr["width"] * 0.6)
    H, W = alpha.shape
    s = cell / max(H, W)
    row = Image.new("RGB", (cell * len(STEPS), cell), "white")
    for k, p in enumerate(STEPS):
        a = alpha * np.clip((p - T) / 0.004 + 1, 0, 1)
        im = Image.fromarray((255 - a * 255).astype(np.uint8)).resize((max(1, int(W * s)), max(1, int(H * s))), Image.LANCZOS)
        row.paste(im, (k * cell + (cell - im.width) // 2, (cell - im.height) // 2))
    travel = sum(float(np.hypot(*(b[0] - a[-1]))) for a, b in zip(tr["strokes"], tr["strokes"][1:]))
    return row, tr, travel


def main():
    for name in sys.argv[1:]:
        cols, rows, subjects = gen_art.SHEETS[name.split("-")[0]]
        objs = trace.cut_sheet(trace.load_ink(os.path.join(common.ART, name + ".png")), cols, rows)
        rowsimg = []
        for alpha, subj in zip(objs, subjects):
            ra, ta, va = strip(alpha, "scan")
            rb, tb, vb = strip(alpha, "human")
            print(f"{name} {subj[:34]:34s} width {tb['width']:.1f}px pieces {tb['pieces']:3d} | scan: {len(ta['strokes']):3d} strokes, pen-up travel {va:6.0f}px | human: {len(tb['strokes']):3d} strokes, travel {vb:6.0f}px")
            for tag, r in (("A scan", ra), ("B human", rb)):
                ImageDraw.Draw(r).text((4, 2), f"{tag}: {subj[:40]}", fill=(200, 0, 0))
                rowsimg.append(r)
        sheet = Image.new("RGB", (rowsimg[0].width, sum(r.height for r in rowsimg)), "white")
        y = 0
        for r in rowsimg:
            sheet.paste(r, (0, y))
            y += r.height
        out = os.path.join(common.WORK, f"order_{name}.jpg")
        sheet.save(out, quality=85)
        print(out)


if __name__ == "__main__":
    main()
