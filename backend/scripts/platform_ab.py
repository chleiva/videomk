#!/usr/bin/env python3
"""A/B of the platform guides (docs/PLATFORM_SKILLS_RESEARCH.md, docs/SKILLS.md): the real director on QA, the same prompt and platform with PLATFORM_SKILLS off and on.

Both arms share the research notes and the producer's picked guides (cached per prompt), so the only difference is the platform guide. No web agent, no TTS, no images.
  AWS_PROFILE=qa python backend/scripts/platform_ab.py gen [--max-cost 9]      # writes docs/audit/2026-11-26-platform-skills/{off,on}/<prompt>__<platform>.json
  AWS_PROFILE=qa python backend/scripts/platform_ab.py score [--max-cost 4]    # deterministic platform rubric (free) + blind pairwise model judge
  python backend/scripts/platform_ab.py report                                # the table
Only the QA account is allowed. Spend is logged to <out>/spend.log.
"""
import argparse
import json
import os
import random
import re
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))
OUT = os.path.join(ROOT, "docs", "audit", "2026-11-26-platform-skills")
PROMPT_IDS = ["sci-01", "how-01", "his-03", "fin-02", "cmp-01", "bio-03", "tra-01", "pro-02", "mkt-02", "tec-01"]
PLATFORMS = {"youtube": 2.0, "tiktok": 0.5, "reels": 0.5, "linkedin": 1.0, "x": 0.75}   # minutes: the platform's recommended length (YouTube capped at 2 for cost)
GREETING = re.compile(r"^\W*(hello|hi|hey|welcome|good (morning|evening|afternoon)|hola|bienvenid|buenas|saludos)\b", re.I)
GENERIC_CTA = re.compile(r"(thanks? for watching|like and subscribe|don'?t forget to|follow (me|us|for)|link in (my )?bio|gracias por (ver|vernos)|suscr[ií]be|s[ií]gueme|sígueme)", re.I)
COMPLEX = {"diagram", "timeline", "map", "code", "equation", "chart", "versus", "table"}
SKIP_KEYS = ("query", "alt", "icon", "style", "accent", "emphasis", "hold", "why", "voice", "ken_burns", "color", "theme")
# per platform: (max words in the first sentence, beat words (low, high), max on-screen words per beat, complex scenes allowed)
NORMS = {"youtube": (25, (18, 45), 14, True), "tiktok": (14, (6, 26), 6, False), "reels": (14, (6, 26), 6, False), "linkedin": (20, (10, 34), 10, True), "x": (16, (8, 28), 8, True)}
LOG_LOCK = threading.Lock()


def log_spend(kind, usd):
    with LOG_LOCK:
        with open(os.path.join(OUT, "spend.log"), "a") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {kind} {usd:.5f}\n")


def spent():
    p = os.path.join(OUT, "spend.log")
    return sum(float(l.split()[-1]) for l in open(p)) if os.path.exists(p) else 0.0


def setup_env():
    if os.environ.setdefault("AWS_PROFILE", "qa") != "qa":
        sys.exit("QA account only")
    os.environ.setdefault("AWS_REGION", "eu-west-1")
    os.environ.setdefault("AWS_DEFAULT_REGION", "eu-west-1")
    os.environ.setdefault("BEDROCK_REGION", "eu-west-1")
    os.makedirs(os.path.join(OUT, "on"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "off"), exist_ok=True)


def load_prompts():
    items = json.load(open(os.path.join(ROOT, "docs", "audit", "prompts.json"), encoding="utf-8"))
    return [i for i in items if i["id"] in PROMPT_IDS]


# ------------------------------------------------------------------ generation
def gen(args):
    setup_env()
    from engine import director, llm, plan as plan_mod, research, skills as skills_mod, format_options
    notes_cache, skills_cache, lock = {}, {}, threading.Lock()
    real_notes, real_select = research.gather_notes, skills_mod.select

    def cached_notes(topic, *a, **k):
        with lock:
            if topic not in notes_cache:
                notes_cache[topic] = real_notes(topic, *a, **k)
            return notes_cache[topic]

    def cached_select(request, ask, minutes=3.0):
        with lock:
            if request not in skills_cache:
                skills_cache[request] = real_select(request, ask, 3.0)
            return skills_cache[request]
    research.gather_notes, skills_mod.select = cached_notes, cached_select
    prompts = load_prompts()
    # warm the caches once (sequential): the same notes and picked guides for every run
    for it in prompts:
        research.gather_notes(it["prompt"], language=it["language"], ask=None)
    plat = {p["id"]: p for p in format_options.PLATFORMS}

    def one(arm, it, pid):
        path = os.path.join(OUT, arm, f"{it['id']}__{pid}.json")
        if os.path.exists(path):
            return
        if spent() > args.max_cost:
            return
        minutes = PLATFORMS[pid]
        cost = [0.0]

        def small(s, u, n=120):
            t, m = llm.complete(s, u, max_tokens=n, model=llm.REVIEW_MODEL, effort="low")
            cost[0] += m["cost_usd"]
            return t

        def big(s, u):
            t, m = llm.complete(s, u, max_tokens=int(min(32000, 6000 + 2600 * minutes)))
            cost[0] += m["cost_usd"]
            return t
        t0 = time.time()
        opts = {"platform": pid, "aspect": plat[pid]["aspect"]}
        captured = {}
        orig_render = skills_mod.render
        try:
            r = director.direct(it["prompt"], minutes=minutes, ask_small=small, ask_big=big, language=it["language"], region="ES" if it["language"] == "es" else "US",
                                max_images_per_minute=10.0, options=opts)
            err = None
        except Exception as e:
            r, err = {}, f"{type(e).__name__}: {e}"
        pl = r.get("plan") or {}
        res = {"id": it["id"], "platform": pid, "arm": arm, "minutes": minutes, "language": it["language"], "prompt": it["prompt"], "error": err, "legit": r.get("legit"),
               "plan": {k: pl.get(k) for k in ("title", "description", "beats", "skills")} if pl else None, "warnings": r.get("warnings") or [],
               "cost_usd": round(cost[0], 5), "seconds": round(time.time() - t0, 1)}
        json.dump(res, open(path, "w"), ensure_ascii=False, indent=1)
        log_spend(f"gen {arm} {it['id']} {pid}", cost[0])
        print(arm, it["id"], pid, f"${cost[0]:.3f}", f"{res['seconds']}s", err or "", flush=True)

    if args.legacy:   # the common guides as they were before 2026-11-26: only the old Publish quality, no platform guide (3 platforms, to check the new always-on guides)
        os.makedirs(os.path.join(OUT, "legacy"), exist_ok=True)
        old = open(args.legacy, encoding="utf-8").read()
        loaded = dict(skills_mod.load())
        loaded.pop("outstanding-video")
        loaded["publish-quality"] = skills_mod._parse(args.legacy)
        skills_mod.load = lambda: loaded
        os.environ["PLATFORM_SKILLS"] = "0"
        with ThreadPoolExecutor(args.workers) as ex:
            list(ex.map(lambda a: one("legacy", *a), [(it, pid) for it in prompts for pid in ("youtube", "tiktok", "linkedin")]))
        print(f"spent ${spent():.3f}")
        return
    plats = [p for p in PLATFORMS if not args.only or p in args.only.split(",")]
    for arm, flag in (("off", "0"), ("on", "1")):
        os.environ["PLATFORM_SKILLS"] = flag
        with ThreadPoolExecutor(args.workers) as ex:
            list(ex.map(lambda a: one(arm, *a), [(it, pid) for it in prompts for pid in plats]))
    print(f"spent ${spent():.3f}")


# ------------------------------------------------------------------ deterministic platform rubric
def words(t):
    return re.findall(r"[\w'’]+", t or "", flags=re.U)


def onscreen_words(scene):
    n = 0

    def walk(k, v):
        nonlocal n
        if any(s in k for s in SKIP_KEYS):
            return
        if isinstance(v, str):
            n += len(words(v))
        elif isinstance(v, list):
            for x in v:
                walk(k, x)
        elif isinstance(v, dict):
            for kk, vv in v.items():
                walk(kk, vv)
    for k, v in ((scene or {}).get("props") or {}).items():
        walk(k, v)
    return n


def rubric(run):
    from engine import plan as plan_mod
    pid = run["platform"]
    beats = (run.get("plan") or {}).get("beats") or []
    if not beats:
        return None
    first_w, (lo, hi), max_text, cx_ok = NORMS[pid]
    spoken = [b for b in beats if (b.get("narration") or "").strip()]
    nar = [len(words(b["narration"])) for b in spoken]
    first = spoken[0]["narration"] if spoken else ""
    sent = re.split(r"(?<=[.!?])\s+", first.strip())[0]
    last = spoken[-1]["narration"] if spoken else ""
    total_w = sum(nar)
    exp = plan_mod.expected_words(run["minutes"])
    types = [str((b.get("scene") or {}).get("type")) for b in beats]
    text = [onscreen_words(b.get("scene")) for b in beats if (b.get("scene") or {}).get("type") not in ("image", "clip", "gallery")]
    r = {"hook_ok": len(words(sent)) <= first_w and not GREETING.search(first) and types[0] != "title",
         "hook_words": len(words(sent)),
         "beat_median_words": statistics.median(nar) if nar else 0,
         "beats_in_norm": round(sum(lo <= n <= hi for n in nar) / len(nar), 2) if nar else 0,
         "text_words_mean": round(statistics.mean(text), 1) if text else 0,
         "text_ok": (statistics.mean(text) <= max_text) if text else True,
         "complex_scenes": sum(t in COMPLEX for t in types),
         "complex_ok": cx_ok or not any(t in COMPLEX for t in types),
         "pause_beats": sum(1 for b in beats if not (b.get("narration") or "").strip()),
         "ending_ok": len(words(last)) >= 6 and not GENERIC_CTA.search(last),
         "words": total_w, "words_vs_expected": round(total_w / exp, 2), "length_fit": 0.85 <= total_w / exp <= 1.15,
         "n_beats": len(beats), "distinct_scene_types": len(set(types))}
    r["checks_passed"] = sum(bool(r[k]) for k in ("hook_ok", "text_ok", "complex_ok", "ending_ok", "length_fit")) + (r["beats_in_norm"] >= 0.6)
    return r


PAIR_SYSTEM = """You are a senior social video producer who knows what top-performing videos on each platform look like. You compare two SCRIPTS (beat by beat: narration plus the scene on screen) of a narrated explainer made for ONE platform. \
You cannot see the video. Judge which script would perform better and feel more native on that platform: the hook in the first 2 seconds (what is spoken and what is on screen), pacing (beat length, visual change), \
on-screen text (short, large, sound-off friendly), tone and vocabulary for the platform, an ending that suits the platform, and still accurate and valuable. Do not reward length or hype. Platform notes: tiktok = native, direct, fast, casual; reels = visual first, polished, loop-friendly; \
linkedin = professional insight with a point of view, understandable muted; x = blunt, the point first, quotable; youtube = clear explanation, strong hook, steady pace and a payoff.
Return ONLY JSON: {"winner": "A"|"B"|"tie", "hook": "A"|"B"|"tie", "pacing": "A"|"B"|"tie", "tone": "A"|"B"|"tie", "ending": "A"|"B"|"tie", "reason": "one sentence"}"""


def script_text(run):
    lines = []
    for i, b in enumerate((run.get("plan") or {}).get("beats") or [], 1):
        sc = b.get("scene") or {}
        props = {k: v for k, v in (sc.get("props") or {}).items() if not any(s in k for s in ("ken_burns", "accent", "style", "icons", "emphasis", "hold"))}
        lines.append(f"Beat {i}: scene {sc.get('type')} {json.dumps(props, ensure_ascii=False)[:300]}\n  narration: {b.get('narration', '')}")
    return f"Title: {(run.get('plan') or {}).get('title')}\n" + "\n".join(lines)


def score(args):
    setup_env()
    from engine import llm
    pairs = []
    for it in load_prompts():
        for pid in PLATFORMS:
            f = f"{it['id']}__{pid}.json"
            a, b = os.path.join(OUT, args.a, f), os.path.join(OUT, args.b, f)
            if os.path.exists(a) and os.path.exists(b):
                pairs.append((f, json.load(open(a)), json.load(open(b))))
    rng = random.Random(7)

    def one(p):
        f, off, on = p
        path = os.path.join(OUT, "pair" if (args.a, args.b) == ("off", "on") else f"pair_{args.a}_{args.b}", f)
        if os.path.exists(path) or not off.get("plan") or not on.get("plan"):
            return
        if spent() > args.max_cost + 0:
            return
        flip = rng.random() < 0.5
        A, B = (on, off) if flip else (off, on)   # off = arm a, on = arm b
        user = f"Platform: {off['platform']}. Request: {off['prompt']}. Target length {off['minutes']} min.\n\n=== SCRIPT A ===\n{script_text(A)}\n\n=== SCRIPT B ===\n{script_text(B)}"
        text, meta = llm.complete(PAIR_SYSTEM, user, max_tokens=700, model=llm.PRIMARY_MODEL, effort="low")
        log_spend("pair " + f, meta["cost_usd"])
        m = re.search(r"\{.*\}", text, re.S)
        try:
            j = json.loads(m.group(0))
        except Exception:
            return
        unflip = {"A": "on" if flip else "off", "B": "off" if flip else "on", "tie": "tie"}
        res = {k: unflip.get(j.get(k), "tie") for k in ("winner", "hook", "pacing", "tone", "ending")}
        res["reason"] = j.get("reason")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        json.dump(res, open(path, "w"), ensure_ascii=False)
    with ThreadPoolExecutor(args.workers) as ex:
        list(ex.map(one, pairs))
    print(f"spent ${spent():.3f}")


def report(args):
    rows = {}
    for arm in (args.a, args.b):
        for fn in sorted(os.listdir(os.path.join(OUT, arm))):
            if fn.endswith(".json"):
                run = json.load(open(os.path.join(OUT, arm, fn)))
                rows[(arm, run["id"], run["platform"])] = run
    keys = ("hook_ok", "beats_in_norm", "text_ok", "complex_ok", "ending_ok", "length_fit", "checks_passed", "text_words_mean", "beat_median_words", "words_vs_expected", "pause_beats")
    out = {}
    for pid in PLATFORMS:
        out[pid] = {}
        for arm in (args.a, args.b):
            rs = [(rubric(r), r) for (a, i, p), r in rows.items() if a == arm and p == pid]
            rs = [(x, r) for x, r in rs if x]
            out[pid][arm] = {"n": len(rs), **{k: round(statistics.mean(float(x[k]) for x, _ in rs), 2) for k in keys if rs},
                             "cost": round(statistics.mean(r["cost_usd"] for _, r in rs), 4) if rs else 0, "secs": round(statistics.mean(r["seconds"] for _, r in rs), 1) if rs else 0}
    print(json.dumps(out, indent=1))
    wins = {}
    pdir = os.path.join(OUT, "pair" if (args.a, args.b) == ("off", "on") else f"pair_{args.a}_{args.b}")
    if os.path.isdir(pdir):
        for fn in os.listdir(pdir):
            pid = fn[:-5].split("__")[1]
            j = json.load(open(os.path.join(pdir, fn)))
            for k in ("winner", "hook", "pacing", "tone", "ending"):
                wins.setdefault(pid, {}).setdefault(k, {"on": 0, "off": 0, "tie": 0})[j[k]] += 1
    print(json.dumps(wins, indent=1))
    json.dump({"rubric": out, "pairwise": wins}, open(os.path.join(OUT, "summary.json" if (args.a, args.b) == ("off", "on") else f"summary_{args.a}_{args.b}.json"), "w"), indent=1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["gen", "score", "report"])
    ap.add_argument("--max-cost", type=float, default=9.0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--only", help="gen: comma list of platforms (rerun)")
    ap.add_argument("--legacy", help="gen: path to the old publish-quality.md; runs the 'legacy' arm instead of off/on")
    ap.add_argument("--a", default="off", help="score/report: the baseline arm")
    ap.add_argument("--b", default="on", help="score/report: the arm compared with it")
    a = ap.parse_args()
    {"gen": gen, "score": score, "report": report}[a.cmd](a)
