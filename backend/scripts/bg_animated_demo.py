#!/usr/bin/env python3
"""Samples, measurements and a showreel for the procedural animated backgrounds (engine/bg_animated.py). Local only, no AWS, no cost.

  python backend/scripts/bg_animated_demo.py OUT_DIR [--fast]

Writes: <style>_16x9.mp4 and <style>_9x16.mp4 (8 s, 1080p, a seamless loop), gas_4k.mp4 (8 s, 3840x2160), showreel.mp4 (every style with sample text over it),
contact_sheet.png, and report.json (ms per frame at 720p/1080p/4K and each aspect, loop seam error, worst text contrast per style/palette/mode).
"""
import json
import os
import subprocess
import sys
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))
from engine import bg_animated as B   # noqa: E402

FONT = os.path.join(HERE, "..", "lambdas", "engine", "assets", "fonts", "Inter-Bold.ttf")
FPS = 30


def encode(path, w, h, frames, fps=FPS, crf=16):
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-", "-an",
           "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-pix_fmt", "yuv420p", "-movflags", "+faststart", path]
    pr = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = 0
    for fr in frames:
        pr.stdin.write(fr.tobytes())
        n += 1
    pr.stdin.close()
    pr.wait()
    return n


def clip(spec, w, h, seconds, path):
    t0 = time.time()
    n = encode(path, w, h, (B.render(spec, w, h, i / FPS) for i in range(int(seconds * FPS))))
    return round((time.time() - t0) / max(n, 1) * 1000, 1)


def with_text(arr, title, sub, light=False):
    im = Image.fromarray(arr, "RGB")
    d = ImageDraw.Draw(im)
    w, h = im.size
    ink = (31, 41, 55) if light else (255, 255, 255)
    f1, f2 = ImageFont.truetype(FONT, int(h * 0.09)), ImageFont.truetype(FONT, int(h * 0.04))
    d.text((w / 2, h * 0.44), title, font=f1, fill=ink, anchor="mm")
    d.text((w / 2, h * 0.88), sub, font=f2, fill=ink, anchor="mm")
    return np.asarray(im)


def main():
    out = sys.argv[1]
    fast = "--fast" in sys.argv
    os.makedirs(out, exist_ok=True)
    report = {"ms_per_frame": {}, "seam": {}, "contrast": {}}
    secs = 2 if fast else 8
    # per-frame cost
    for style in B.STYLES:
        sp = B.BgSpec(style=style)
        for name, (w, h) in {"720p": (1280, 720), "1080p": (1920, 1080), "1080x1920": (1080, 1920), "1080x1080": (1080, 1080), "1080x1350": (1080, 1350), "4k": (3840, 2160)}.items():
            B.render(sp, w, h, 0.0)
            t0 = time.time()
            for i in range(4):
                B.render(sp, w, h, i * 0.37)
            report["ms_per_frame"][f"{style}@{name}"] = round((time.time() - t0) / 4 * 1000, 1)
        report["seam"][style] = B.seam_error(sp)
    # contrast: every style x palette x mode
    for style in B.STYLES:
        for pal in B.PALETTES:
            for mode in B.MODES:
                r = B.contrast_report(B.BgSpec(style=style, palette=pal, mode=mode), 640, 360, (0, 2, 4, 6, 8))
                report["contrast"][f"{style}/{pal}/{mode}"] = r
    # clips
    for style in B.STYLES:
        sp = B.BgSpec(style=style, palette={"gas": "midnight", "smoke": "mono", "lava": "ember", "aurora": "forest", "mesh": "sunrise", "bokeh": "violet"}[style], seed=3)
        clip(sp, 1920, 1080, secs, os.path.join(out, f"{style}_16x9.mp4"))
        clip(sp, 1080, 1920, secs, os.path.join(out, f"{style}_9x16.mp4"))
    t4 = clip(B.BgSpec(style="gas", palette="midnight", seed=3), 3840, 2160, secs, os.path.join(out, "gas_4k.mp4"))
    report["ms_per_frame"]["gas@4k_encode_included"] = t4
    # showreel with sample text, 1080p, 4 s per style, then the light variants
    def reel():
        for style, pal, mode in [(s, p, "dark") for s, p in zip(B.STYLES, ("midnight", "mono", "ember", "forest", "sunrise", "violet"))] + [("gas", "violet", "light"), ("mesh", "ocean", "light")]:
            sp = B.BgSpec(style=style, palette=pal, mode=mode, seed=3)
            for i in range(4 * FPS):
                yield with_text(B.render(sp, 1920, 1080, i / FPS), f"{style} ({pal}, {mode})", "Captions and titles stay readable on top of it.", mode == "light")
    encode(os.path.join(out, "showreel.mp4"), 1920, 1080, reel())
    # contact sheet: each style, 3 times, 16:9 and one 9:16
    W, H = 480, 270
    sheet = Image.new("RGB", (W * 3 + 152, H * len(B.STYLES)), (20, 20, 20))
    for r, style in enumerate(B.STYLES):
        sp = B.BgSpec(style=style, palette={"gas": "midnight", "smoke": "mono", "lava": "ember", "aurora": "forest", "mesh": "sunrise", "bokeh": "violet"}[style], seed=3)
        for c, t in enumerate((1.0, 4.0, 7.0)):
            sheet.paste(Image.fromarray(B.render(sp, W, H, t)), (c * W, r * H))
        sheet.paste(Image.fromarray(B.render(sp, 152, 270, 3.0)).resize((152, 270)), (W * 3, r * H))
    sheet.save(os.path.join(out, "contact_sheet.png"))
    json.dump(report, open(os.path.join(out, "report.json"), "w"), indent=1)
    worst = min(v["zone_min"] for v in report["contrast"].values())
    print("worst zone contrast:", worst, "| max seam error:", max(v["seam"] for v in report["seam"].values()), "| 1080p ms:", {k: v for k, v in report["ms_per_frame"].items() if k.endswith("@1080p")})


if __name__ == "__main__":
    main()
