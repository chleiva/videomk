#!/usr/bin/env python3
"""How many cores does ONE render chunk use, and how much memory? Decides the Lambda memory of the HD render function (docs/COST_LEVERS_2026-11-28.md): a Lambda gets
about 1 vCPU per 1,769 MB, so a chunk that keeps 1.5 cores busy loses nothing at 4,096 MB (2.3 vCPU) and is slowed under 2,650 MB.

  python backend/scripts/render_cores.py [timeline.json] [--resolution 1080p|720p] [--seconds 10]
Prints per chunk: frames, wall s, CPU s (this process + ffmpeg child), cores used = CPU/wall, ms per frame, peak RSS of the process (MB) and the GB-s a Lambda of 10,240 and 4,096 MB would bill."""
import argparse
import json
import os
import resource
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))
from engine import format_options, pipeline  # noqa: E402
from engine.timeline import chunk_plan, chunk_timeline  # noqa: E402
import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402


def _loader(key):
    if key != "demo-photo":
        return None
    h, w = 1600, 2400
    y = np.linspace(0, 1, h)[:, None, None]
    x = np.linspace(0, 1, w)[None, :, None]
    return Image.fromarray(np.concatenate([40 + 160 * y * np.ones((1, w, 1)), 70 + 90 * x * np.ones((h, 1, 1)), 140 + 80 * (1 - y) * np.ones((1, w, 1))], axis=2).astype("uint8"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("timeline", nargs="?", default=os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "demo_timeline.json"))
    ap.add_argument("--resolution", default="")
    ap.add_argument("--seconds", type=int, default=10)
    ap.add_argument("--max-chunks", type=int, default=3)
    a = ap.parse_args()
    tl = json.load(open(a.timeline))
    if a.resolution:
        fr = format_options.frame_dict(tl.get("frame", {}).get("aspect") or "16:9", a.resolution, None)
        if "frame" in tl:
            tl["frame"] = fr
        tl["width"], tl["height"] = fr["width"], fr["height"]
    for k in ("width", "height"):
        pass
    chunks = chunk_plan(tl, a.seconds, draft=False)[: a.max_chunks]
    tot_wall = tot_cpu = 0.0
    with tempfile.TemporaryDirectory() as tmp:
        for c in chunks:
            r0, c0, t0 = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN), time.time()
            pipeline.render_chunk(chunk_timeline(tl, c["lo"], c["hi"]), c.get("f0", 0), c.get("f0", 0) + c["frames"], os.path.join(tmp, f"s{c['k']}.ts"), _loader, draft=False)
            wall = time.time() - t0
            r1, c1 = resource.getrusage(resource.RUSAGE_SELF), resource.getrusage(resource.RUSAGE_CHILDREN)
            cpu = (r1.ru_utime + r1.ru_stime - r0.ru_utime - r0.ru_stime) + (c1.ru_utime + c1.ru_stime - c0.ru_utime - c0.ru_stime)
            rss = r1.ru_maxrss / (1 << 20 if sys.platform == "darwin" else 1 << 10)
            tot_wall += wall
            tot_cpu += cpu
            print(f"chunk {c['k']}: {c['frames']} frames, wall {wall:.1f} s, cpu {cpu:.1f} s, cores {cpu / wall:.2f}, {wall / c['frames'] * 1000:.0f} ms/frame, peak RSS {rss:.0f} MB")
    print(f"TOTAL wall {tot_wall:.1f} s, cpu {tot_cpu:.1f} s, cores {tot_cpu / tot_wall:.2f}; billed at 10240 MB {tot_wall * 10.0:.0f} GB-s, at 4096 MB {tot_wall * 4.0:.0f} GB-s")


if __name__ == "__main__":
    main()
