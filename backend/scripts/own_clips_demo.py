#!/usr/bin/env python3
"""One whole video on this machine with the REAL engine steps (plan, beats, timeline, audio, render) and videomk's OWN clip library as the first clip source.

  AWS_PROFILE=qa python scripts/own_clips_demo.py LIB_DIR OUT_DIR --prompt "..." [--minutes 1.5] [--plan plan.json] [--resolution 720p] [--draft]

LIB_DIR holds library.json + the clips (engine/clips.py `own_search`). The S3 of the engine is replaced by OUT_DIR/store (music tracks and the catalogue are read, never
written, from the QA bucket). Models, Polly, Tavily and stock photos are the real thing (QA account only; the script refuses any other account).
Prints the spend by part. Nothing is uploaded, committed or deployed.
"""
import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))

STORE = ""
SPEND: dict = {}


def _check_account():
    import boto3
    acct = boto3.client("sts").get_caller_identity()["Account"]
    if acct != "552357225438":
        sys.exit(f"refusing to run in account {acct}: QA only")


def _install_local_awsio(store: str, qa_bucket: str):
    """Swap the S3 helpers of engine.awsio for a folder; reads of keys not in the folder fall back to the QA bucket (music, catalogue), read-only."""
    from engine import awsio, costs
    import boto3

    real = boto3.client("s3", region_name="eu-west-1")

    def path(key):
        if ".." in key:
            raise ValueError("bad key")
        return os.path.join(store, key)

    def put_bytes(key, data, content_type="", bkt=None, *, working=False):
        p = path(key)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, "wb").write(data)

    def get_bytes(key):
        p = path(key)
        if os.path.exists(p):
            return open(p, "rb").read()
        return real.get_object(Bucket=qa_bucket, Key=key)["Body"].read()

    awsio.put_json = lambda key, obj: put_bytes(key, json.dumps(obj).encode())
    awsio.get_json = lambda key: json.loads(get_bytes(key))
    awsio.put_bytes = put_bytes
    awsio.get_bytes = get_bytes
    awsio.put_bytes_meta = lambda key, data, ct, md: put_bytes(key, data)
    awsio.download = lambda key, dest: open(dest, "wb").write(get_bytes(key))
    awsio.upload = lambda src, key, ct, bkt=None, *, working=False: put_bytes(key, open(src, "rb").read())
    awsio.head = lambda key: {"ContentLength": os.path.getsize(path(key))} if os.path.exists(path(key)) else None
    awsio.delete = lambda key: os.path.exists(path(key)) and os.remove(path(key))

    def add_cost(video_id, usd, *, field="cost_usd", part="other"):
        SPEND[part] = SPEND.get(part, 0.0) + float(usd)

    costs.add_cost = add_cost


def _web_tools(spent):
    from common.secrets import get_secret_param
    from engine import llm, websearch

    key = get_secret_param("/videomk/tavily_api_key", quiet=True)
    if not key:
        return None, None

    def ask_tools(system, messages, tools, **kw):
        blocks, stop, meta = llm.complete_tools(system, messages, tools, model=llm.RESEARCH_MODEL, effort=llm.RESEARCH_EFFORT, max_tokens=4000, **kw)
        spent["research"] = spent.get("research", 0.0) + meta["cost_usd"]
        return blocks, stop, meta

    return websearch.TavilyProvider(key), ask_tools


def make_plan(prompt: str, minutes: float, aspect: str, resolution: str, video_id: str):
    from engine import awsio, director, format_options, library, llm, plan as plan_mod, voices

    spent: dict = {}

    def ask_small(system, user, max_tokens=120):
        text, meta = llm.complete(system, user, max_tokens=max_tokens, model=llm.REVIEW_MODEL, effort="low")
        spent["script"] = spent.get("script", 0.0) + meta["cost_usd"]
        return text

    def ask_big(system, user):
        text, meta = llm.complete(system, user, max_tokens=int(min(32000, 6000 + 2600 * minutes)))
        spent["script"] = spent.get("script", 0.0) + meta["cost_usd"]
        return text

    provider, ask_tools = _web_tools(spent)
    catalog = library.load_catalog(awsio.get_json)
    res = director.direct(prompt, minutes=minutes, ask_small=ask_small, ask_big=ask_big, language=None, options={"aspect": aspect}, region=None, theme=None,
                          web_provider=provider, ask_tools=ask_tools, photos=[], story=None, max_images_per_minute=10, music_tracks=catalog)
    r = res.get("research") or {}
    spent["research"] = spent.get("research", 0.0) + float(r.get("searches", 0)) * 0.008
    for k, v in spent.items():
        SPEND[k] = SPEND.get(k, 0.0) + v
    if not res["legit"]:
        sys.exit(f"planner refused: {res.get('reason')}")
    plan = res["plan"]
    known = {t["id"] for t in catalog}
    chosen = plan_mod.sanitize_music(plan.get("music"), len(plan["beats"]), known)
    plan.pop("music", None)
    if chosen:
        plan["music"] = chosen
    plan["target_seconds"] = round(minutes * 60)
    plan["frame"] = format_options.frame_dict(aspect, resolution, None)
    plan["captions"] = True
    plan["tts"] = {"provider": "polly", "voice": "", "style": "Say in a clear, warm, engaging explainer voice", "engine": "generative", "region": "us-east-1"}
    return plan, res.get("warnings")


def _loader(key):
    from PIL import Image
    p = os.path.join(STORE, key)
    return Image.open(p) if os.path.exists(p) else None


def _clip_loader_for(store):
    def load(key):
        from engine import clips
        p = os.path.join(store, key)
        return clips.ClipFrames(p) if os.path.exists(p) and key.endswith(".mp4") else None
    return load


def _work(args):
    tl, c, path, draft, store = args
    global STORE
    STORE = store
    from engine import pipeline
    from engine.timeline import chunk_timeline
    t = time.time()
    pipeline.render_chunk(chunk_timeline(tl, c["lo"], c["hi"]), 0, c["frames"], path, lambda k: _loader(k), draft=draft, clip_loader=_clip_loader_for(store))
    return c["k"], path, time.time() - t, c["frames"]


def main():
    global STORE
    ap = argparse.ArgumentParser()
    ap.add_argument("lib_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--prompt", required=True)
    ap.add_argument("--minutes", type=float, default=1.5)
    ap.add_argument("--aspect", default="16:9")
    ap.add_argument("--resolution", default="720p")
    ap.add_argument("--plan", default=None, help="reuse a stored plan (no planner cost)")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--own-only", action="store_true", help="no stock clip providers: only our own library (photos still come from Unsplash)")
    ap.add_argument("--workers", type=int, default=min(4, os.cpu_count() or 2))
    a = ap.parse_args()

    os.environ.setdefault("AWS_REGION", "eu-west-1")
    os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-1")
    os.environ["CLIPS_OWN_DIR"] = os.path.abspath(a.lib_dir)
    os.environ["CLIPS_NASA"] = "0"       # the test shows the own clips: no live stock providers besides the photo fallback
    os.environ["CLIPS_COMMONS"] = "0"
    os.makedirs(a.out_dir, exist_ok=True)
    STORE = os.path.join(os.path.abspath(a.out_dir), "store")
    os.makedirs(STORE, exist_ok=True)
    _check_account()
    _install_local_awsio(STORE, "videomk-qa-552357225438")

    from engine import awsio, format_options, media
    from engine.handlers import audio_handler, beat_handler, timeline_handler
    if a.own_only:
        real_secret = beat_handler.get_secret_param
        beat_handler.get_secret_param = lambda name, **kw: "" if name in ("/videomk/pexels_api_key", "/videomk/pixabay_api_key") else real_secret(name, **kw)
    from concurrent.futures import ThreadPoolExecutor

    video_id = "00000000-0000-4000-8000-0000000f0e57"
    t0 = time.time()
    plan_key = awsio.prefix(video_id) + "plan_r1.json"
    if a.plan:
        plan = json.load(open(a.plan))
    else:
        plan, warnings = make_plan(a.prompt, a.minutes, a.aspect, a.resolution, video_id)
        print("plan warnings:", (warnings or [])[:6])
    plan["frame"] = format_options.frame_dict(a.aspect, a.resolution, None)
    json.dump(plan, open(os.path.join(a.out_dir, "plan.json"), "w"), ensure_ascii=False, indent=1)
    awsio.put_json(plan_key, plan)
    kinds = [b["scene"]["type"] for b in plan["beats"]]
    print(f"plan: {len(plan['beats'])} beats {dict((k, kinds.count(k)) for k in set(kinds))} in {time.time() - t0:.0f}s; models ${sum(SPEND.values()):.3f}")

    # step 2: every beat (Polly narration, photos, and clips from our own library first), like the beat Lambda
    def one(b):
        return beat_handler.handler({"video_id": video_id, "beat_id": b["id"], "plan_key": plan_key, "cost_field": "cost_usd"}, None)

    t1 = time.time()
    with ThreadPoolExecutor(max_workers=3) as ex:
        beats = list(ex.map(one, plan["beats"]))
    print(f"beats done in {time.time() - t1:.0f}s")
    own = []
    for b, r in zip(plan["beats"], beats):
        if b["scene"]["type"] == "clip":
            m = r["media"]
            own.append({"beat": b["id"], "narration": b["narration"][:90], "clip": m.get("chosen"), "segments": m.get("segments"), "fallback_photo": bool(m.get("asset") and not m.get("clip_asset")),
                        "credit": m.get("credit")})
    json.dump(own, open(os.path.join(a.out_dir, "clip_beats.json"), "w"), indent=1)
    for o in own:
        print("  clip beat", o)
    chars = sum(len(b.get("narration") or "") for b in plan["beats"] if not b.get("silent"))
    SPEND["speech_polly_est"] = chars * 0.00003

    tl_out = timeline_handler.handler({"video_id": video_id, "plan_key": plan_key, "rev": 1, "mode": "final", "beats": beats}, None)
    tl = awsio.get_json(tl_out["timeline_key"])
    print(f"timeline {tl['duration']:.1f}s, {len(tl_out['chunks'])} chunks")
    aud = audio_handler.handler({"video_id": video_id, "rev": 1, "mode": "final", "timeline_key": tl_out["timeline_key"]}, None)

    from engine import pipeline  # noqa: F401
    t2 = time.time()
    with tempfile.TemporaryDirectory() as tmp:
        jobs = [(tl, {"k": c["k"], "lo": c["lo"], "hi": c["hi"], "frames": c["frames"]}, os.path.join(tmp, f"seg_{c['k']:03d}.ts"), a.draft, STORE) for c in tl_out["chunks"]]
        with ProcessPoolExecutor(max_workers=a.workers) as ex:
            results = sorted(ex.map(_work, jobs))
        audio_path = os.path.join(tmp, "mix.m4a")
        open(audio_path, "wb").write(awsio.get_bytes(aud["key"]))
        out = os.path.join(os.path.abspath(a.out_dir), "video.mp4")
        media.mux_final([r[1] for r in results], audio_path, out, fps=tl["fps"])
    dur = media.ffprobe_duration(out)
    chunk_s = sum(r[2] for r in results)
    print(f"video {out}: {dur:.1f}s, {os.path.getsize(out) / 1e6:.1f} MB; render {time.time() - t2:.0f}s wall, {chunk_s:.0f} chunk-seconds")
    print("spend by part:", {k: round(v, 4) for k, v in SPEND.items()}, "total", round(sum(SPEND.values()), 4))


if __name__ == "__main__":
    main()
