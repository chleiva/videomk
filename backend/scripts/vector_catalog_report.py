#!/usr/bin/env python3
"""Contact sheet and showreel of the cartoon vector scene catalog (a local store built by vector_catalog_build.py).

  python backend/scripts/vector_catalog_report.py sheet --store DIR --out sheet.png [--check]
  python backend/scripts/vector_catalog_report.py reel  --store DIR --out reel.mp4 --ids a b c ... [--seconds 4.5] [--size 1920x1080]

`sheet` labels every scene (id, layers, SVG KB); with --check it also renders each scene at 480x270 (or 270x480 for tall ones) at 40% of its duration with the real runtime and uses that
frame, so a broken layer split or a gap shows up in the sheet. `reel` renders the scenes one after another with the engine's own runtime (engine/vector_scene.py) and 0.5 s cross-fades.
"""
import argparse
import json
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))

from engine import vector_scene as vs  # noqa: E402


def metas(store):
    out = []
    for sid in sorted(os.listdir(store)):
        mp = os.path.join(store, sid, "meta.json")
        if os.path.exists(mp):
            out.append(json.load(open(mp)))
    return out


def sheet(store, out, check):
    ms = metas(store)
    cols, cw, ch = 6, 320, 180
    tall = [m for m in ms if m["orientation"] == "tall"]
    wide = [m for m in ms if m["orientation"] != "tall"]
    rows = (len(wide) + cols - 1) // cols
    th = 320
    tcols = cols * cw // 230                                  # tall tiles wrap into rows of the sheet width
    trows = (len(tall) + tcols - 1) // tcols
    S = Image.new("RGB", (cols * cw, rows * (ch + 30) + trows * (th + 30)), "white")
    d = ImageDraw.Draw(S)

    def tile(m, x, y, w, h):
        if check:
            sc = vs.VectorScene(os.path.join(store, m["id"]), w, h)
            im = sc.frame(0.4 * 4.0, 4.0).convert("RGB")
        else:
            im = Image.open(os.path.join(store, m["id"], "thumb.jpg")).convert("RGB").resize((w, h))
        S.paste(im, (x, y + 30))
        d.text((x + 4, y + 3), f"{m['id']}", fill="black")
        d.text((x + 4, y + 15), f"{m['layers']} layers, {m['svg_kb']} KB, {m['mood']}", fill="#555555")

    for n, m in enumerate(wide):
        tile(m, (n % cols) * cw, (n // cols) * (ch + 30), cw, ch)
    for n, m in enumerate(tall):
        tile(m, (n % tcols) * 230, rows * (ch + 30) + (n // tcols) * (th + 30), 213, th)
    S.save(out)
    print("sheet", out, len(ms), "scenes")


def reel(store, out, ids, seconds, size):
    w, h = (int(x) for x in size.lower().split("x"))
    fps, fade = 30, 15
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = int(seconds * fps)
    prev_tail = None
    for sid in ids:
        sc = vs.VectorScene(os.path.join(store, sid), w, h)
        frames = [np.asarray(sc.frame(i / fps, seconds).convert("RGB")) for i in range(n)]
        if prev_tail is not None:
            for k in range(fade):
                a = (k + 1) / (fade + 1)
                frames[k] = (prev_tail[k] * (1 - a) + frames[k] * a).astype(np.uint8)
        for f in frames[:n - fade]:
            p.stdin.write(f.tobytes())
        prev_tail = frames[n - fade:]
        print("rendered", sid, flush=True)
    for f in prev_tail:
        p.stdin.write(f.tobytes())
    p.stdin.close()
    p.wait()
    print("reel", out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["sheet", "reel"])
    ap.add_argument("--store", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--seconds", type=float, default=4.5)
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.cmd == "sheet":
        sheet(a.store, a.out, a.check)
    else:
        reel(a.store, a.out, a.ids, a.seconds, a.size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
