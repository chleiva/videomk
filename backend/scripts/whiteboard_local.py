#!/usr/bin/env python3
"""A whiteboard video end to end on this machine with the SAME code the Lambdas run (docs/WHITEBOARD.md): the director writes the boards from a plain prompt
(real model calls), Polly speaks, the engine's own alignment gives the word times, the timeline links the boards into one big board, the chunks are rendered
one at a time and muxed. Nothing is deployed and nothing is stored in S3; the drawing packages are read from the QA catalog bucket and cached under /tmp.

  AWS_PROFILE=qa AWS_REGION=eu-west-1 python backend/scripts/whiteboard_local.py "How does compound interest work?" out_dir [--seconds 40] [--aspect 16:9]
      [--resolution 1080p] [--style whiteboard|auto] [--chunk-seconds 10] [--stage plan|audio|render]

Each stage is kept in out_dir (plan.json, audio/*.npy, timeline.json, seg_*.ts): a rerun continues from what is there; delete a file to redo its stage.
Chunks are rendered in THIS process, one after another (a 16 GB laptop), and the time and peak memory of each is printed.
"""
import argparse
import json
import os
import resource
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))
os.environ.setdefault("WHITEBOARD", "1")
os.environ.setdefault("CATALOG_BUCKET", "videomk-qa-catalog-552357225438")

import numpy as np  # noqa: E402

from engine import align, audio, director, format_options, llm, media, pipeline, tts, voices  # noqa: E402
from engine.timeline import build_timeline, chunk_plan, chunk_timeline  # noqa: E402


def plan_stage(a, out):
    path = os.path.join(out, "plan.json")
    if os.path.isfile(path):
        return json.load(open(path))
    spent = [0.0]

    def small(system, user, max_tokens=120):
        text, meta = llm.complete(system, user, max_tokens=max_tokens, model=llm.REVIEW_MODEL, effort="low")
        spent[0] += meta["cost_usd"]
        return text

    def big(system, user):
        text, meta = llm.complete(system, user)
        spent[0] += meta["cost_usd"]
        return text

    t0 = time.time()
    r = director.direct(a.prompt, minutes=a.seconds / 60.0, ask_small=small, ask_big=big, region="US",
                        options={"aspect": a.aspect, "resolution": a.resolution, **({"style": a.style} if a.style != "auto" else {})})
    if not r.get("legit"):
        raise SystemExit(f"refused: {r.get('reason')}")
    plan = r["plan"]
    plan["target_seconds"] = a.seconds
    plan["frame"] = format_options.frame_dict(a.aspect, a.resolution, None)
    plan["captions"] = True
    plan["_local"] = {"plan_seconds": round(time.time() - t0, 1), "plan_cost_usd": round(spent[0], 4), "warnings": r.get("warnings")}
    json.dump(plan, open(path, "w"), indent=1, ensure_ascii=False)
    print(f"plan: {len(plan['beats'])} beats in {time.time() - t0:.0f} s, ${spent[0]:.3f}; whiteboard: {plan.get('whiteboard')}; warnings: {r.get('warnings')}")
    return plan


def audio_stage(plan, out):
    os.makedirs(os.path.join(out, "audio"), exist_ok=True)
    cfg = plan.get("tts", {})
    provider = tts.get_provider((cfg.get("provider") or "polly"), "", cfg)
    infos, samples = [], []
    for i, beat in enumerate(plan["beats"]):
        if beat.get("silent"):
            infos.append({"duration": float(beat.get("hold") or 2.0), "silent": True})
            samples.append(None)
            continue
        p = os.path.join(out, "audio", f"{i:02d}.npy")
        if os.path.isfile(p):
            s = np.load(p)
        else:
            s = tts.synth_beat(provider, beat["narration"], voice=voices.beat_voice(plan, beat), style=cfg.get("style", ""))
            np.save(p, s)
        info = {"duration": round(s.size / audio.SR, 3), "audio_key": f"local/{i:02d}"}
        words, conf = align.align_words(s, audio.SR, beat["narration"])
        if words and conf >= 0.5:
            info["words"] = [list(w) for w in words]
        infos.append(info)
        samples.append(s)
    return infos, samples


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("out")
    ap.add_argument("--seconds", type=int, default=40)
    ap.add_argument("--aspect", default="16:9")
    ap.add_argument("--resolution", default="1080p")
    ap.add_argument("--style", default="whiteboard")
    ap.add_argument("--chunk-seconds", type=int, default=10)
    ap.add_argument("--stage", default="render", choices=("plan", "audio", "render"))
    ap.add_argument("--draft", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)

    plan = plan_stage(a, a.out)
    if a.stage == "plan":
        return
    infos, samples = audio_stage(plan, a.out)
    fr = plan["frame"]
    tl = build_timeline(plan, infos, video_id="local", fps=30, width=fr["width"], height=fr["height"], min_seconds=float(a.seconds), fit_seconds=float(a.seconds))
    tl["frame"] = fr
    json.dump(tl, open(os.path.join(a.out, "timeline.json"), "w"), indent=1, ensure_ascii=False)
    print(f"timeline: {tl['duration']:.1f} s, {len(tl['scenes'])} scenes, sync {tl['sync']}")
    if a.stage == "audio":
        return

    from engine.scenes.elements import whiteboard as wbe

    chunks = chunk_plan(tl, a.chunk_seconds, draft=a.draft)
    segs = []
    for c in chunks:
        path = os.path.join(a.out, f"seg_{c['k']:03d}_{c['hash'][:10]}.ts")
        segs.append(path)
        if os.path.isfile(path):
            continue
        wbe._STATE.clear()
        wbe._STILLS.clear()      # every chunk as a fresh container would see it
        t0 = time.time()
        pipeline.render_chunk(chunk_timeline(tl, c["lo"], c["hi"]), c.get("f0", 0), c.get("f0", 0) + c["frames"], path + ".part", None, draft=a.draft)
        os.replace(path + ".part", path)
        secs = time.time() - t0
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1 << 20 if sys.platform == "darwin" else 1 << 10)
        print(f"  chunk {c['k']}: scenes {c['lo']}..{c['hi'] - 1}, {c['frames']} frames in {secs:.1f} s ({secs / c['frames'] * 1000:.0f} ms/frame), peak memory of the process so far {rss:.0f} MB", flush=True)
    apath = os.path.join(a.out, "audio.m4a")
    pipeline.make_audio(tl, samples, apath)
    final = os.path.join(a.out, "video.mp4")
    media.mux_final(segs, apath, final, fps=tl["fps"])
    print(f"video: {final} {media.ffprobe_duration(final):.2f} s, {os.path.getsize(final) / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
