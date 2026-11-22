#!/usr/bin/env python3
"""Render a timeline end to end on this machine with the SAME functions the Lambdas run.

Chunks are rendered in a process pool to mimic the Step Functions fan-out; per-chunk wall time is printed
so you can estimate Lambda duration/cost (Lambda vCPU is slower than a laptop core: treat this as a floor).

  python scripts/local_render.py tests/fixtures/demo_timeline.json out.mp4 [--draft] [--workers 4] [--chunk-seconds 30]
"""
import argparse
import json
import os
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from engine import media, pipeline  # noqa: E402
from engine.tts import MockTTS, synth_beat  # noqa: E402
from engine.timeline import chunk_ranges  # noqa: E402


def _demo_photo():
    h, w = 1600, 2400
    y = np.linspace(0, 1, h)[:, None, None]
    x = np.linspace(0, 1, w)[None, :, None]
    img = np.concatenate([40 + 160 * y * np.ones((1, w, 1)), 70 + 90 * x * np.ones((h, 1, 1)), 140 + 80 * (1 - y) * np.ones((1, w, 1))], axis=2)
    return Image.fromarray(img.astype("uint8"))


def _loader(key):
    return _demo_photo() if key == "demo-photo" else None


def _work(args):
    tl, k, f0, f1, path, draft = args
    t = time.time()
    pipeline.render_chunk(tl, f0, f1, path, _loader, draft=draft)
    return k, path, time.time() - t, f1 - f0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("timeline")
    ap.add_argument("out")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    ap.add_argument("--chunk-seconds", type=int, default=30)
    a = ap.parse_args()

    tl = json.load(open(a.timeline))
    chunks = chunk_ranges(tl, a.chunk_seconds)
    t0 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        jobs = [(tl, c["k"], c["f0"], c["f1"], os.path.join(tmp, f"seg_{c['k']:03d}.ts"), a.draft) for c in chunks]
        with ProcessPoolExecutor(max_workers=a.workers) as ex:
            results = sorted(ex.map(_work, jobs))
        t_render = time.time() - t0
        for k, _, secs, frames in results:
            print(f"  chunk {k}: {frames:5d} frames in {secs:6.1f}s  ({secs / frames * 1000:5.1f} ms/frame)")

        t1 = time.time()
        beats = [synth_beat(MockTTS(), " ".join(w[0] for w in sc["words"])) if sc.get("words") else np.zeros(2400, np.float32) for sc in tl["scenes"]]
        audio = os.path.join(tmp, "audio.m4a")
        pipeline.make_audio(tl, beats, audio)
        t_audio = time.time() - t1

        t2 = time.time()
        media.mux_final([r[1] for r in results], audio, a.out, fps=tl["fps"])
        t_mux = time.time() - t2

    dur = media.ffprobe_duration(a.out)
    total_chunk_s = sum(r[2] for r in results)
    print(f"render (parallel, {a.workers} workers): {t_render:.1f}s | audio: {t_audio:.1f}s | stitch+mux: {t_mux:.2f}s")
    print(f"video: {dur:.2f}s (timeline {tl['duration']:.2f}s), {os.path.getsize(a.out) / 1e6:.1f} MB")
    gbs = total_chunk_s * 3.0  # assume 3 GB Lambdas
    print(f"summed chunk compute: {total_chunk_s:.0f}s -> ~{gbs:,.0f} GB-s -> ~${gbs * 0.0000166667:.3f} Lambda compute at 3 GB (x86)")


if __name__ == "__main__":
    main()
