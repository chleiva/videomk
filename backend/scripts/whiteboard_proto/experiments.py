#!/usr/bin/env python3
"""The four ways to get a drawing, side by side, on the same six objects and the same label. Everything is vector and rasterised at the output size.

  A  image-model art -> FILLED vector outlines (vtracer), revealed along the hidden centre line
  B  image-model art -> CENTRE-LINE strokes (smoothing cubic splines, round caps, slight pressure), the stroke IS the art
  C  a language model writes ordered strokes, looks at its drawing and fixes it twice (llm_strokes.py), smoothed
  D  hybrid: A's outlines for the line, colour in the areas the line encloses, code-drawn strokes (B's renderer) for connectors

  experiments.py [A B C D]  -> OUT/experiments/<m>_4k.jpg, <m>_crop_plant.jpg, <m>_crop_label.jpg, <m>_draw.mp4 and OUT/web/* with captions.json
"""
import json
import os
import subprocess
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import board as bd  # noqa: E402
import common  # noqa: E402
import trace as tr  # noqa: E402
import vectorize as vz  # noqa: E402

EXP = os.path.join(common.OUT, "experiments")
WEB = os.path.join(common.OUT, "web")
UI_FONT = os.path.join(HERE, "..", "..", "lambdas", "engine", "assets", "fonts", "Inter-SemiBold.ttf")
OBJECTS = [("sun", "sheet1", 0), ("raincloud", "sheet2", 2), ("plant", "sheet1", 3), ("mountain", "sheet1", 2), ("waves", "sheet1", 5), ("person", "sheet3", 0)]
LABEL = "evaporation"
TITLES = {
    "A": "A  image-model art traced to filled vector outlines, revealed along a hidden centre line",
    "B": "B  image-model art reduced to centre-line strokes (smooth curves, round caps): the stroke is the art",
    "C": "C  a language model writes the strokes, looks at its drawing and fixes it twice",
    "D": "D  hybrid: A's outlines + colour in the enclosed areas + code-drawn connectors",
}
CELLS = [(640, 500), (1920, 500), (3200, 500), (640, 1300), (1920, 1300), (3200, 1300)]
BOX = (900, 620)
DUR = 12.0
LINE = 24.0      # marker width on the board, in board units: the same for every drawing


def sheet_objects():
    cache = {}
    out = {}
    for name, sheet, idx in OBJECTS:
        if sheet not in cache:
            cache[sheet] = tr.cut_sheet(tr.load_ink(os.path.join(common.ART, sheet + ".png")), 3, 2)
        out[name] = cache[sheet][idx]
    return out


def pick_fills(name, pkg):
    b = pkg["fill_boxes"]
    if not b:
        return []
    if name == "sun":
        return [(0, bd.FILL_YELLOW)]
    if name == "raincloud":
        return [(0, bd.FILL_GREY)]
    if name == "plant":
        low = max(range(len(b)), key=lambda i: b[i][3])
        return [(i, bd.FILL_BROWN if i == low else bd.FILL_GREEN) for i in sorted(range(len(b)), key=lambda i: (i != low, b[i][1]))]
    if name == "mountain":
        top = min(range(len(b)), key=lambda i: b[i][1])
        return [(top, bd.FILL_BLUE)] if len(b) > 1 else []
    return []


def packages(method, objs):
    """-> {name: pkg}, {name: build seconds}"""
    pk, secs = {}, {}
    for name, alpha in objs.items():
        t0 = time.time()
        if method in ("A", "D"):
            pk[name] = vz.build_outline(alpha)
        elif method == "B":
            pk[name] = vz.build_strokes(alpha, draw_width=LINE / min(BOX[0] / alpha.shape[1], BOX[1] / alpha.shape[0]))
        else:
            import llm_strokes

            strokes, meta = llm_strokes.load(name)
            pk[name] = vz.from_strokes(strokes, LINE / (BOX[1] / 600), 600, 600, fills=False)
            secs[name] = meta["seconds"]
            continue
        secs[name] = time.time() - t0
    t0 = time.time()
    pk["label"] = vz.text_pkg(LABEL, common.FONT, method="B" if method in ("B", "C") else "A")
    secs["label"] = time.time() - t0
    return pk, secs


def build_board(method, pk, scale):
    b = bd.Board(3840, 2160, scale)
    t = 0.5
    for (name, _, _), (cx, cy) in zip(OBJECTS, CELLS):
        p = pk[name]
        k = min(BOX[0] / p["w"], BOX[1] / p["h"])           # board units per drawing unit
        r = vz.raster(p, k * scale, line_px=LINE * scale)
        dur = float(np.clip(r["pen_len"] * k / 2900.0, 0.6, 1.25))
        colour = bd.BLUE if (method == "D" and name == "waves") else bd.INK
        b.place(r, cx - p["w"] * k / 2, cy - p["h"] * k / 2, colour, t, t + dur, fills=pick_fills(name, p) if method == "D" else None, fill_t0=t + dur + 0.05, fill_dur=0.4)
        t += 1.5
    p = pk["label"]
    k = 1150 / p["w"]
    r = vz.raster_text(p, k * scale)
    b.place(r, 1920 - p["w"] * k / 2, 1960 - p["h"] * k / 2, bd.INK, t, t + 1.2)
    if method == "D":      # a code-drawn underline and an arrow, to show the connectors in the same hand
        import primitives as pr

        for strokes, col, t0, d in ((pr.underline(1380, 2090, 1080, seed=3), bd.RED, t + 1.3, 0.35), (pr.arrow([(2620, 1560), (2740, 1330), (2700, 1080)], seed=5), bd.BLUE, t + 1.75, 0.5)):
            q = pr.package(strokes, LINE * 0.9)
            r = vz.raster(q, scale)
            b.place(r, q["x"], q["y"], col, t0, t0 + d)
    b.finish()
    return b


def title(im, method):
    k = im.width / 1920
    d = ImageDraw.Draw(im)
    d.text((28 * k, 20 * k), TITLES[method], font=ImageFont.truetype(UI_FONT, int(26 * k)), fill=(120, 124, 132))
    return im


def web_clip(src, dst, width=960, crf=27):
    subprocess.run(["nice", "-n", "10", "ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vf", f"scale={width}:-2", "-c:v", "libx264", "-preset", "slow", "-crf", str(crf), "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "96k", "-movflags", "+faststart", dst], check=True)


def save_jpeg(im, path, max_kb=300, q=90):
    while True:
        im.save(path, "JPEG", quality=q, optimize=True)
        if os.path.getsize(path) <= max_kb * 1024 or q <= 50:
            return
        q -= 6


def main():
    os.makedirs(EXP, exist_ok=True)
    os.makedirs(WEB, exist_ok=True)
    methods = sys.argv[1:] or ["A", "B", "C", "D"]
    objs = sheet_objects()
    stats = json.load(open(os.path.join(EXP, "stats.json"))) if os.path.exists(os.path.join(EXP, "stats.json")) else {}
    for m in methods:
        pk, secs = packages(m, objs)
        # 4K still and 100 % crops
        t0 = time.time()
        b4 = build_board(m, pk, 1.0)
        build4k = time.time() - t0
        still = title(b4.frame(DUR, (0, 0, 3840), (3840, 2160), tip=False), m)
        save_jpeg(still, os.path.join(EXP, f"{m}_4k.jpg"), max_kb=900, q=92)
        save_jpeg(still.resize((1920, 1080), Image.LANCZOS), os.path.join(WEB, f"exp_{m}_still.jpg"))
        for tag, box in (("plant", (2640, 150, 3840, 950)), ("label", (1320, 1560, 2520, 2160)), ("sun", (140, 100, 1340, 900))):
            crop = still.crop(box)
            save_jpeg(crop, os.path.join(EXP, f"{m}_crop_{tag}.jpg"), max_kb=600, q=93)
            save_jpeg(crop, os.path.join(WEB, f"exp_{m}_crop4k_{tag}.jpg"))
        del b4
        # draw-on clip, 1080p
        b = build_board(m, pk, 0.5)
        t0 = time.time()
        n = int(DUR * 30)
        bd.encode((title(b.frame(i / 30, (0, 0, 3840), (1920, 1080)), m) for i in range(n)), os.path.join(EXP, f"{m}_draw.mp4"))
        per_frame = (time.time() - t0) / n
        web_clip(os.path.join(EXP, f"{m}_draw.mp4"), os.path.join(WEB, f"exp_{m}_draw.mp4"))
        stats[m] = {"build_seconds_per_object": {k: round(v, 2) for k, v in secs.items()}, "strokes": {k: len(v["strokes"]) for k, v in pk.items()},
                    "board_4k_build_s": round(build4k, 1), "ms_per_1080p_frame_incl_encode": round(per_frame * 1000, 1)}
        print(m, stats[m])
        json.dump(stats, open(os.path.join(EXP, "stats.json"), "w"), indent=1)
    captions()


def captions():
    """web/captions.json: every file in web/ with one plain line about what it is and what to look at."""
    what = {"A": "Method A (image-model drawing traced to filled vector outlines, revealed along a hidden centre line)",
            "B": "Method B (image-model drawing reduced to centre-line strokes; the stroke itself is the art)",
            "C": "Method C (a language model writes the strokes and corrects them twice after looking)",
            "D": "Method D, the hybrid I recommend (A's outlines, colour in the enclosed areas, code-drawn arrows and underlines)"}
    look = {"A": "lines keep the exact shape and weight of the generated art", "B": "lines are a little looser; small shape details at joins and line ends are lost",
            "C": "recognisable but clearly cruder doodles; proportions vary from object to object", "D": "same lines as A, plus colour that lands exactly inside the shapes"}
    path = os.path.join(WEB, "captions.json")
    old = {c["file"]: c for c in json.load(open(path))} if os.path.exists(path) else {}
    for f in sorted(os.listdir(WEB)):
        if not f.startswith("exp_"):
            continue
        m = f.split("_")[1]
        if "_draw" in f:
            cap = f"{what[m]}: 12 s draw-on clip of six objects and a label. Watch the order and direction in which each drawing appears; {look[m]}."
        elif "_still" in f:
            cap = f"{what[m]}: the finished board (a 4K frame reduced to 1920 px). Look at likeness and at how even the style is across objects; {look[m]}."
        else:
            part = f.rsplit("_", 1)[1].split(".")[0]
            cap = f"{what[m]}: 100 % crop (1200x800 px, not reduced) of the 4K frame, the {part}. Look at the line edges: they should be perfectly smooth, no steps, no blur."
        old[f] = {"file": f, "caption": cap}
    json.dump(sorted(old.values(), key=lambda c: c["file"]), open(path, "w"), indent=1)


if __name__ == "__main__":
    main()
