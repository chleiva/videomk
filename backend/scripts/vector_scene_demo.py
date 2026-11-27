#!/usr/bin/env python3
"""Render a bundled layered-vector scene (engine/assets/vector_scenes/<id>) to an mp4 with the engine's own runtime (engine/vector_scene.py).

  python scripts/vector_scene_demo.py forest_path out.mp4 [--size 1920x1080] [--seconds 8] [--fps 30]
  python scripts/vector_scene_demo.py --list

Prints the render time per frame and the size of the SVG layers next to the mp4. Needs ffmpeg on PATH and resvg-py (pip install resvg-py).
"""
import argparse
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))

from engine import vector_scene as vs  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("scene", nargs="?")
    ap.add_argument("out", nargs="?")
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--seconds", type=float, default=8.0)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.list or not a.scene:
        print("\n".join(vs.scene_ids()))
        return 0
    w, h = (int(x) for x in a.size.lower().split("x"))
    t0 = time.time()
    sc = vs.load(a.scene, w, h)
    load = time.time() - t0
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(a.fps), "-i", "-",
           "-c:v", "libx264", "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p", "-movflags", "+faststart", a.out]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n = int(a.seconds * a.fps)
    t1 = time.time()
    for i in range(n):
        p.stdin.write(sc.frame(i / a.fps, a.seconds).tobytes())
    p.stdin.close()
    p.wait()
    el = time.time() - t1
    svg = sum(os.path.getsize(os.path.join(sc.dir, l["file"])) for l in sc.layers)
    print(f"{a.scene} {w}x{h}: rasterise layers {load:.1f}s, {n} frames in {el:.1f}s = {el / n * 1000:.0f} ms/frame; svg layers {svg // 1024} KB, mp4 {os.path.getsize(a.out) // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
