#!/usr/bin/env python3
"""End-to-end proof of library clips on demand on THIS machine with the REAL engine steps and the REAL provider (docs/CLIPS_ON_DEMAND.md, "Proof").

  AWS_PROFILE=qa python backend/scripts/clips_on_demand_proof.py OUT_DIR [--max-generations 4] [--no-video] [--env-file .env]

What is real: the beat step (`beat_handler.handler` / `make_clip`), the small and large models and the Cohere embeddings (Bedrock, QA account only), Polly, the stock search,
the video provider (key read from the environment or --env-file, never printed), ffmpeg, the renderer. What is local: S3 is OUT_DIR/store, the clip library and every
counter are OUT_DIR/library (a `LocalStore`), and who owns each video is told to the engine by this script (there is no videos table here).
It spends real money on the provider: a hard stop after --max-generations calls, whatever the budgets say. Writes OUT_DIR/proof.json. Nothing is uploaded or deployed.
"""
import argparse
import importlib.util
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))
_spec = importlib.util.spec_from_file_location("own_clips_demo", os.path.join(HERE, "own_clips_demo.py"))
demo = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(demo)

VIDEO_A = "00000000-0000-4000-8000-00000c11b0a1"   # a 16:9 video of test account t1: four clip beats, the per-video cap allows two generations
VIDEO_B = "00000000-0000-4000-8000-00000c11b0b2"   # a FREE account's video: may only reuse the library
VIDEO_C = "00000000-0000-4000-8000-00000c11b0c3"   # a vertical video of test account t2
WHO = {VIDEO_A: {"user_id": "proof-t1", "plan": "test"}, VIDEO_B: {"user_id": "proof-free", "plan": "free"}, VIDEO_C: {"user_id": "proof-t2", "plan": "test"}}

BASE = {"legit": True, "title": "From field to breakfast table", "description": "", "mood": "warm", "theme": "midnight", "language": "en", "voices": {"narrator": "Ruth"},
        "skills": ["explainer-education"], "background": {"style": "smoke", "palette": "midnight", "mode": "dark", "speed": 1.0, "intensity": 1.0, "seed": 11, "loop_seconds": 12.0, "by": "director"},
        "region": "US", "sources": [], "music": {"track": "cinematic-rise"}, "target_seconds": 30, "captions": True,
        "tts": {"provider": "polly", "voice": "", "style": "Say in a clear, warm, engaging explainer voice", "engine": "generative", "region": "us-east-1"}}
BEATS_A = [
    ("a1c11p01", "Breakfast starts far from the kitchen, in wide fields where wheat ripens under the summer sun.", "golden wheat field swaying in the wind", "ripe wheat ears moving in a breeze"),
    ("a1c11p02", "Flour, water and patient hands turn that grain into dough, pressed and folded until it is smooth.", "baker hands kneading bread dough", "hands folding dough on a floured table"),
    ("a1c11p03", "Honey begins with bees, drifting from flower to flower through the warm morning air.", "bees on lavender flowers", "honey bees collecting nectar"),
    ("a1c11p04", "And at the end of that long journey, steam rises from a quiet cup of coffee.", "steam rising from a cup of coffee", "hot coffee cup on a wooden table"),
]
REFUSALS = [("woman in a red coat buying mangoes in Oaxaca market on a rainy Tuesday", "fruit stall at a street market in the rain"),
            ("president giving a speech at a podium", "politician speaking to a crowd"), ("coca-cola bottle on a table", "soft drink bottle"),
            ("Eiffel Tower at sunset", "paris skyline evening"), ("stock market chart on a trading screen", "financial data dashboard"),
            ("close-up of a surgeon making an incision", "operating theatre surgery"), ("footballer scoring the winning goal", "stadium crowd celebrating"),
            ("rain falling on a quiet pond", "raindrops rippling on still water"), ("old wooden fishing boat tied at a jetty", "small boat moored in a calm harbour")]


def load_env(path):
    if not path or not os.path.isfile(path):
        return
    for ln in open(path):
        if ln.startswith("GEMINI_API_KEY=") and not os.environ.get("GEMINI_API_KEY"):
            os.environ["GEMINI_API_KEY"] = ln.split("=", 1)[1].strip().strip('"').strip("'")   # never printed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--max-generations", type=int, default=4)
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--env-file", default=os.path.join(HERE, "..", "..", ".env"))
    ap.add_argument("--workers", type=int, default=2)
    a = ap.parse_args()
    out_dir = os.path.abspath(a.out_dir)
    os.makedirs(out_dir, exist_ok=True)
    os.environ.setdefault("AWS_REGION", "eu-west-1")
    os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-1")
    os.environ.update({"CLIPS_ON_DEMAND": "1", "CLIPS_LIB_DIR": os.path.join(out_dir, "library"), "CLIPS_NASA": "0", "CLIPS_COMMONS": "0"})
    load_env(a.env_file)
    if not os.environ.get("GEMINI_API_KEY"):
        sys.exit("no provider key (GEMINI_API_KEY)")
    demo._check_account()
    demo.STORE = os.path.join(out_dir, "store")
    os.makedirs(demo.STORE, exist_ok=True)
    demo._install_local_awsio(demo.STORE, "videomk-qa-552357225438")

    from common import clip_config as cc, clip_store as cs
    from engine import awsio, clip_brief, clip_gen, clip_ondemand as od, format_options, llm, media
    from engine.handlers import audio_handler, beat_handler, timeline_handler

    cc.set_config({"enabled": True})   # every other knob at its recommended default: $2 a day for test accounts, $3 an account, 2 a video
    od.set_readers(video=lambda vid: WHO.get(vid), credits=lambda user, now: 0)
    proof = {"started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "config": {k: v for k, v in cc.config().items() if k in (
        "test_day_usd", "test_month_usd", "test_account_cap_usd", "video_cap_clips", "price_per_second_usd", "overhead_usd", "clip_seconds", "gen_timeout_s", "model")}, "generations": [], "models_usd": 0.0}

    class Counted(clip_gen.GeminiOmni):   # the proof's own hard stop, and what each call really took
        def generate(self, prompt, **kw):
            if len(proof["generations"]) >= a.max_generations:
                raise clip_gen.GenError("quota", "the proof's own limit", billed=False)
            rec = {"prompt": prompt, "seconds": kw.get("seconds"), "aspect": kw.get("aspect"), "at": time.strftime("%H:%M:%S", time.gmtime())}
            proof["generations"].append(rec)
            t = time.time()
            try:
                out = super().generate(prompt, **kw)
                rec.update({"ok": True, "latency_s": round(time.time() - t, 1), "bytes": len(out["mp4"]), "usage": out.get("usage")})
                return out
            except clip_gen.GenError as e:
                rec.update({"ok": False, "latency_s": round(time.time() - t, 1), "error": e.kind, "billed": e.billed, "detail": str(e)[:200]})
                raise
    clip_gen.set_provider(Counted(str(cc.config()["model"])))
    real_complete = llm.complete

    def complete(*args, **kw):   # count what the models around the clips cost
        text, meta = real_complete(*args, **kw)
        proof["models_usd"] = round(proof["models_usd"] + float(meta.get("cost_usd", 0.0)), 6)
        return text, meta
    llm.complete = complete

    # 1. the reusability decision on specific searches (the small model only; nothing is generated)
    proof["decisions"] = []
    for q, alt in REFUSALS:
        d, _ = clip_brief.generalise(q, alt, "")
        proof["decisions"].append({"search": q, "reusable": d["reusable"], "reason": d["reason"], "brief": d.get("brief")})
        print("decide:", q, "->", d["reason"] if not d["reusable"] else d["brief"])

    # 2. video A, the whole real pipeline: four clip beats made in parallel, then a closing line
    plan = {**BASE, "frame": format_options.frame_dict("16:9", "720p", None),
            "beats": [{"id": i, "narration": n, "scene": {"type": "clip", "props": {"clip_query": q, "alt": alt}}} for i, n, q, alt in BEATS_A]
            + [{"id": "a1c11p05", "narration": "Every breakfast is a small journey.", "scene": {"type": "kinetic_text", "props": {"text": "Every breakfast is a small journey.", "emphasis": "journey"}}}]}
    plan_key = awsio.prefix(VIDEO_A) + "plan_r1.json"
    awsio.put_json(plan_key, plan)
    json.dump(plan, open(os.path.join(out_dir, "plan_a.json"), "w"), indent=1)
    t1 = time.time()
    with ThreadPoolExecutor(max_workers=4) as ex:
        beats = list(ex.map(lambda b: beat_handler.handler({"video_id": VIDEO_A, "beat_id": b["id"], "plan_key": plan_key, "cost_field": "cost_usd"}, None), plan["beats"]))
    proof["video_a"] = {"beats_wall_s": round(time.time() - t1, 1), "clip_beats": [
        {"beat": b["id"], "query": b["scene"]["props"]["clip_query"], "chosen": r["media"].get("chosen"), "credit": r["media"].get("credit"), "photo_fallback": bool(r["media"].get("asset") and not r["media"].get("clip_asset"))}
        for b, r in zip(plan["beats"], beats) if b["scene"]["type"] == "clip"]}
    for c in proof["video_a"]["clip_beats"]:
        print("video A:", c)

    # 3. video B, a FREE account: the same scenes worded differently. It may only reuse the library.
    proof["video_b"] = []
    for i, (n, q, alt) in enumerate([("Fields of grain stretch to the horizon before harvest.", "wheat field at sunset", "ears of wheat in a field"),
                                     ("Bread begins as dough worked by hand.", "kneading dough by hand", "baker working bread dough")]):
        before = len(proof["generations"])
        out = beat_handler.make_clip({**BASE, "beats": [], "frame": format_options.frame_dict("16:9", "720p", None)},
                                     {"id": f"b{i}", "narration": n, "scene": {"type": "clip", "props": {"clip_query": q, "alt": alt}}}, VIDEO_B, "cost_usd", 4.0, time.time())
        proof["video_b"].append({"query": q, "chosen": out.get("chosen"), "credit": out.get("credit"), "generations_started": len(proof["generations"]) - before})
        print("video B:", proof["video_b"][-1])

    # 4. video C, vertical, another test account: scenes video A asked for and did not get (its cap). The day's budget decides.
    proof["video_c"] = []
    for i, (n, q, alt) in enumerate([("Steam curls up from a fresh cup of coffee.", "steam rising from coffee cup", "hot coffee steaming in a mug"),
                                     ("Bees move between the flowers all morning.", "bees on lavender flowers", "honey bees on purple flowers")]):
        before = len(proof["generations"])
        out = beat_handler.make_clip({**BASE, "beats": [], "frame": format_options.frame_dict("9:16", "1080p", None)},
                                     {"id": f"c{i}", "narration": n, "scene": {"type": "clip", "props": {"clip_query": q, "alt": alt}}}, VIDEO_C, "cost_usd", 5.0, time.time())
        if out.get("clip_asset"):
            open(os.path.join(out_dir, f"video_c_beat{i}.mp4"), "wb").write(awsio.get_bytes(out["clip_asset"]))
        proof["video_c"].append({"query": q, "chosen": out.get("chosen"), "credit": out.get("credit"), "generations_started": len(proof["generations"]) - before})
        print("video C:", proof["video_c"][-1])

    store = cs.current()
    proof["stats"] = {k: v for k, v in (store.get(cs.STATS, cs.day()) or {}).items() if k not in ("pk", "sk", "ttl")}
    proof["spend"] = {"test_day_usd": cs.usd((store.get(cs.spend_pk("test", "day"), cs.day()) or {}).get("spent")), "paid_day_usd": cs.usd((store.get(cs.spend_pk("paid", "day"), cs.day()) or {}).get("spent"))}
    proof["ledger"] = [{k: v for k, v in r.items() if k not in ("pk", "ttl")} for r in store.query(cs.ledger_pk(cs.month()))]
    proof["library"] = [{k: r.get(k) for k in ("sk", "brief", "aspect", "seconds", "width", "height", "center_safe", "gate_score", "uses", "videos", "cost_usd")} for r in store.query(cs.LIB)]
    json.dump(proof, open(os.path.join(out_dir, "proof.json"), "w"), indent=1, ensure_ascii=False, default=str)

    # 5. render video A
    if not a.no_video:
        tl_out = timeline_handler.handler({"video_id": VIDEO_A, "plan_key": plan_key, "rev": 1, "mode": "final", "beats": beats}, None)
        tl = awsio.get_json(tl_out["timeline_key"])
        aud = audio_handler.handler({"video_id": VIDEO_A, "rev": 1, "mode": "final", "timeline_key": tl_out["timeline_key"]}, None)
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            jobs = [(tl, {"k": c["k"], "lo": c["lo"], "hi": c["hi"], "frames": c["frames"]}, os.path.join(tmp, f"seg_{c['k']:03d}.ts"), False, demo.STORE) for c in tl_out["chunks"]]
            with ProcessPoolExecutor(max_workers=a.workers) as ex:
                results = sorted(ex.map(demo._work, jobs))
            audio_path = os.path.join(tmp, "mix.m4a")
            open(audio_path, "wb").write(awsio.get_bytes(aud["key"]))
            video = os.path.join(out_dir, "video_a.mp4")
            media.mux_final([r[1] for r in results], audio_path, video, fps=tl["fps"])
        proof["video_a"]["file"], proof["video_a"]["seconds"] = video, round(media.ffprobe_duration(video), 1)
        json.dump(proof, open(os.path.join(out_dir, "proof.json"), "w"), indent=1, ensure_ascii=False, default=str)
        print("video:", video, proof["video_a"]["seconds"], "s")
    print(json.dumps({"generations": len(proof["generations"]), "spend": proof["spend"], "models_usd": proof["models_usd"], "stats": proof["stats"]}, indent=1))


if __name__ == "__main__":
    main()
