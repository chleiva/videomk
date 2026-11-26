#!/usr/bin/env python3
"""Deck to video on this machine with the SAME engine functions the Lambdas run (docs/DECK_TO_VIDEO.md): a converted deck (the output folder of the converter: deck.json and
slide_NNN.png) -> storyboard (real models) -> narration (Polly) -> timeline -> frames -> MP4.

  AWS_PROFILE=qa BEDROCK_REGION=eu-west-1 python scripts/deck_demo.py DECK_DIR OUT_DIR [--prompt "..."] [--minutes 3] [--aspect 16:9] [--resolution 1080p] [--language es]
        [--plan plan.json]   reuse a storyboard (no model cost)      [--no-video]  stop after the plan      [--draft]
Prints the models' cost; the plan, the timeline, the MP4 and a few frames land in OUT_DIR. Never run against the prod account.
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

DECK_DIR = ""


def _loader(key):
    f = os.path.join(DECK_DIR, os.path.basename(key))
    return Image.open(f).convert("RGB") if os.path.exists(f) else None


def _work(args):
    global DECK_DIR
    tl, c, path, draft, deck_dir = args
    DECK_DIR = deck_dir
    from engine import pipeline
    from engine.timeline import chunk_timeline
    t = time.time()
    pipeline.render_chunk(chunk_timeline(tl, c["lo"], c["hi"]), 0, c["frames"], path, _loader, draft=draft)
    return c["k"], path, time.time() - t, c["frames"]


def main():
    global DECK_DIR
    ap = argparse.ArgumentParser()
    ap.add_argument("deck_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--prompt", default="Explain this presentation clearly for a general audience.")
    ap.add_argument("--minutes", type=float, default=None)
    ap.add_argument("--aspect", default="16:9")
    ap.add_argument("--resolution", default="1080p")
    ap.add_argument("--language", default=None)
    ap.add_argument("--plan", default=None)
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--draft", action="store_true")
    ap.add_argument("--workers", type=int, default=os.cpu_count() or 2)
    a = ap.parse_args()
    DECK_DIR = os.path.abspath(a.deck_dir)
    os.makedirs(a.out_dir, exist_ok=True)

    from engine import align, audio, deck_plan, format_options, llm, media, pipeline, plan as plan_mod, timeline as tl_mod, tts, voices
    from engine.timeline import beat_info_from_plan, build_timeline, chunk_plan

    deck = json.load(open(os.path.join(DECK_DIR, "deck.json")))
    spent = {"deck": 0.0, "script": 0.0}
    calls = []

    def ask_small(system, user, max_tokens=120):
        text, meta = llm.complete(system, user, max_tokens=max_tokens, model=llm.REVIEW_MODEL, effort="low")
        spent["script"] += meta["cost_usd"]
        calls.append(("small", meta["tokens_in"], meta["tokens_out"]))
        return text

    def ask_big(system, user):
        text, meta = llm.complete(system, user, max_tokens=plan_mod.plan_max_tokens(a.minutes or 5) if hasattr(plan_mod, "plan_max_tokens") else 16000)
        spent["script"] += meta["cost_usd"]
        calls.append(("big", meta["tokens_in"], meta["tokens_out"]))
        return text

    def ask_vision(system, user, images):
        text, meta = llm.complete(system, user, images=images, max_tokens=2500, model=llm.REVIEW_MODEL, effort="low")
        spent["deck"] += meta["cost_usd"]
        calls.append(("vision", meta["tokens_in"], meta["tokens_out"]))
        return text

    plan_path = os.path.join(a.out_dir, "plan.json")
    t0 = time.time()
    if a.plan:
        plan = json.load(open(a.plan))
        minutes = plan["target_seconds"] / 60
    else:
        from engine import deckio  # noqa: F401
        images = []
        import io
        for n in deck["images"]:
            im = Image.open(os.path.join(DECK_DIR, n)).convert("RGB")
            im.thumbnail((1024, 1024))
            b = io.BytesIO()
            im.save(b, "JPEG", quality=80)
            images.append(b.getvalue())
        res = deck_plan.direct_deck(deck, images, prompt=a.prompt, minutes=a.minutes, ask_small=ask_small, ask_big=ask_big, ask_vision=ask_vision,
                                    asset_for=lambda n: f"generation/v2/00000000-0000-0000-0000-000000000000/assets/deck/{deck['images'][n - 1]}", language=a.language,
                                    options={"aspect": a.aspect})
        if not res["legit"]:
            print("REFUSED:", res)
            return
        plan, minutes = res["plan"], res["minutes"]
        print("warnings:", res["warnings"])
        plan["target_seconds"] = round(minutes * 60)
        plan["tts"] = {"provider": "polly", "voice": "", "style": "Say in a clear, warm, engaging explainer voice", "engine": "generative", "region": "us-east-1"}
        plan["captions"] = True
        plan["frame"] = format_options.frame_dict(a.aspect, a.resolution, None)
        json.dump(plan, open(plan_path, "w"), ensure_ascii=False, indent=1)
    plan["frame"] = format_options.frame_dict(a.aspect, a.resolution, None)   # a stored storyboard can be rendered in any shape
    t_plan = time.time() - t0
    print(f"plan: {len(plan['beats'])} beats, {plan_mod.spoken_words(plan['beats'])} words for {minutes:g} min asked, {t_plan:.1f}s, models ${spent['deck'] + spent['script']:.4f} "
          f"(vision ${spent['deck']:.4f}, script ${spent['script']:.4f}), calls {[(k, i, o) for k, i, o in calls]}")
    for i, b in enumerate(plan["beats"]):
        p = b["scene"]["props"]
        print(f"  {i + 1:2d}. slide {p.get('n')}{' zone:' + p.get('focus_label', '') if p.get('focus') else ''}: {b['narration']}")
    if a.no_video:
        return

    # narration with Polly, word timings measured from the audio
    cfg = plan["tts"]
    provider = tts.get_provider("polly", "", cfg)
    t1 = time.time()
    samples, chars = [], 0
    for b in plan["beats"]:
        s = tts.synth_beat(provider, b["narration"], voice=voices.beat_voice(plan, b), style=cfg.get("style", ""))
        words, conf = align.align_words(s, audio.SR, b["narration"])
        b["media"] = {"duration": round(s.size / audio.SR, 3), "words_key": None}
        b["_words"] = [list(w) for w in words] if words and conf >= 0.6 else None
        samples.append(s)
        chars += len(b["narration"])
    t_tts = time.time() - t1
    infos = beat_info_from_plan(plan)
    for info, b in zip(infos, plan["beats"]):
        info.pop("words_key", None)
        if b.get("_words"):
            info["words"] = b["_words"]
    fr = format_options.frame_of(plan)
    tl = build_timeline(plan, infos, video_id="demo", fps=30, width=fr["width"], height=fr["height"], min_seconds=float(plan["target_seconds"]))
    tl["frame"] = fr
    tl["captions"] = True
    json.dump(tl, open(os.path.join(a.out_dir, "timeline.json"), "w"))
    chunks = chunk_plan(tl, 10, draft=a.draft)
    t2 = time.time()
    out = os.path.join(a.out_dir, f"deck_{a.aspect.replace(':', 'x')}_{a.resolution}.mp4")
    with tempfile.TemporaryDirectory() as tmp:
        jobs = [(tl, c, os.path.join(tmp, f"seg_{c['k']:03d}.ts"), a.draft, DECK_DIR) for c in chunks]
        with ProcessPoolExecutor(max_workers=a.workers) as ex:
            results = sorted(ex.map(_work, jobs))
        t_render = time.time() - t2
        aud = os.path.join(tmp, "audio.m4a")
        pipeline.make_audio(tl, [None if sc.get("silent") else s for sc, s in zip(tl["scenes"], samples)], aud)
        media.mux_final([r[1] for r in results], aud, out, fps=tl["fps"])
    dur = media.ffprobe_duration(out)
    chunk_s = sum(r[2] for r in results)
    polly = chars * 0.00003  # generative voices: about USD 30 per million characters
    print(f"video {out}: {dur:.1f}s ({tl['duration']:.1f}s timeline), {os.path.getsize(out) / 1e6:.1f} MB; tts {t_tts:.1f}s ({chars} chars, about ${polly:.4f}); render {t_render:.1f}s wall, "
          f"{chunk_s:.1f} chunk-seconds (about ${chunk_s * 10.0 * 0.0000166667:.4f} at 10 GB Lambda)")
    for frac in (0.1, 0.4, 0.75):
        t = tl["duration"] * frac
        from engine.renderer import Renderer
        Renderer(tl, image_loader=_loader).frame_at(t).save(os.path.join(a.out_dir, f"frame_{a.aspect.replace(':', 'x')}_{int(frac * 100):02d}.png"))


if __name__ == "__main__":
    main()
