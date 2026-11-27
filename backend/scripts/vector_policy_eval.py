#!/usr/bin/env python3
"""Does the cartoon-scene policy behave? (docs/VECTOR_SCENE_POLICY.md)

Runs the REAL code on QA (Bedrock, the Cohere catalog index): for ~30 briefs
  stage 1 (cheap, every brief): language detection, the producer's guide choice, the research decision (web or not) and `vector_policy.decide` -> the decision table;
  stage 2 (only briefs the policy OFFERED, plus a few refusals as a leak check): `engine.director.direct` with VECTOR_SCENES=1 (no web agent, no voice, no photos fetched,
          no rendering), then a small judge call rates every cartoon scene the director chose (is it appropriate for the beat?).
Sequential in stage 2 (the policy in force is a process-wide setting). Stops starting work when the spend cap is reached.

  AWS_PROFILE=qa AWS_REGION=eu-west-1 python backend/scripts/vector_policy_eval.py [--max-cost 4] [--only ID ...] [--stage1-only] [--out docs/vector_policy_eval]
Only the QA account is allowed.
"""
import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))

os.environ["VECTOR_SCENES"] = "1"

PHOTO = [{"id": "aaaaaaaa", "key": "x", "w": 1000, "h": 800, "orientation": "landscape", "caption": "a family on a beach"}]

# id, prompt, extra {options, photos, minutes}, what we expect: "yes" (offered), "no" (never), "either"
CASES = [
    dict(id="kids-story", prompt="A bedtime story for five-year-olds about a little cloud who is afraid of thunder", expect="yes"),
    dict(id="kids-photosynthesis", prompt="How photosynthesis works, explained for children", expect="yes"),
    dict(id="kids-seasons", prompt="Why do we have seasons? For kids aged 7", expect="yes"),
    dict(id="kids-es-volcano", prompt="Explícale a un niño de 6 años cómo funcionan los volcanes", expect="yes"),
    dict(id="light-es-water", prompt="Cómo ahorrar agua en casa, con un tono simpático y cercano", expect="either"),
    dict(id="abstract-internet", prompt="How does the internet work, in simple terms", expect="either"),
    dict(id="abstract-blockchain", prompt="Explain blockchain simply for complete beginners", expect="either"),
    dict(id="wellness-sleep", prompt="Five simple habits for better sleep, in a friendly tone", expect="either"),
    dict(id="funny-cats", prompt="Why do cats knock things off tables? A funny explainer", expect="either"),
    dict(id="motivation-habits", prompt="Why small daily habits beat big goals", expect="either"),
    dict(id="travel-beach", prompt="A relaxing beach holiday: what to pack and how to unwind", expect="either"),
    dict(id="travel-rome", prompt="A tour of Rome: the Colosseum, the Vatican and the Trevi Fountain", expect="no"),
    dict(id="cooking-pancakes", prompt="How to make fluffy pancakes", expect="either"),
    dict(id="finance-earnings", prompt="Quarterly earnings summary for a SaaS company: revenue up 12 percent, churn down to 2 percent", expect="no"),
    dict(id="news-ukraine", prompt="What happened this week in the war in Ukraine", expect="no"),
    dict(id="news-election", prompt="Latest news on the polls for the US presidential election this month", expect="no"),
    dict(id="product-launch", prompt="Launch video for our new noise-cancelling headphones, the AeroSound X2", expect="no"),
    dict(id="es-pensions", prompt="Resumen de la reforma de pensiones en España", expect="no"),
    dict(id="linkedin-leadership", prompt="Three lessons on leading remote teams", options={"platform": "linkedin", "aspect": "4:5"}, expect="no"),
    dict(id="user-photos", prompt="Make a video of my holiday photos", photos=True, expect="no"),
    dict(id="medical-heart-attack", prompt="What to do if you think you are having a heart attack", expect="no"),
    dict(id="history-rome", prompt="The fall of the Roman Empire", expect="no"),
    dict(id="tragedy-titanic", prompt="The Titanic disaster and why so many people died", expect="no"),
    dict(id="science-jwst", prompt="How the James Webb telescope sees the early universe", expect="no"),
    dict(id="coding-fastapi", prompt="How to build a REST API in Python with FastAPI", expect="no"),
    dict(id="compare-phones", prompt="iPhone vs Android: which should you buy in 2026", expect="no"),
    dict(id="cartoon-bill", prompt="Make it a cartoon: how a bill becomes law", expect="yes"),
    dict(id="cartoon-es-water", prompt="Un vídeo con dibujos animados sobre el ciclo del agua", expect="yes"),
    dict(id="cartoon-mortgage", prompt="Cartoon-style video about how mortgages work", expect="yes"),
    dict(id="real-bees", prompt="Explain how bees make honey, use real footage and real photos", expect="no"),
    dict(id="kids-tiktok-vertical", prompt="Fun fact for kids: why is the sky blue", options={"platform": "tiktok", "aspect": "9:16"}, minutes=0.75, expect="either"),
]

PLAN_EXTRA_NEVER = {"finance-earnings", "news-election", "tragedy-titanic", "real-bees", "product-launch"}   # leak check: full plans even though the policy refuses

JUDGE_SYSTEM = ("You review an explainer video's plan for the appropriate use of CARTOON scenes (flat illustrated landscapes with gentle motion, no people). Cartoon scenes are right for: children's "
                "and family topics, simple everyday or abstract explainers, light-hearted or wellness or travel-atmosphere moments, storytelling, chapter openers. They are WRONG for: news, "
                "tragedy, war, violence, illness or injury, serious finance or legal or medical advice, named real people, places, brands, products or events, numbers or facts that need a chart, "
                "and anywhere real footage or a photograph would show the thing being talked about. Given the video request and each beat that uses a cartoon scene (with its narration and chosen "
                'scene id), return ONLY JSON: {"overall": 1-5, "request_suits_cartoon": true|false, "beats": [{"beat": n, "ok": true|false, "note": "<8 words"}]}. 5 = clearly appropriate, 1 = clearly wrong.')


class Spend:
    def __init__(self, cap):
        self.cap, self.total, self.lock = cap, 0.0, threading.Lock()

    def add(self, usd):
        with self.lock:
            self.total += usd

    @property
    def over(self):
        return self.total >= self.cap


def clients(spend):
    from engine import llm

    def small(system, user, max_tokens=120):
        text, meta = llm.complete(system, user, max_tokens=max_tokens, model=llm.REVIEW_MODEL, effort="low")
        spend.add(meta["cost_usd"])
        return text

    def big(system, user, minutes=2.0):
        text, meta = llm.complete(system, user, max_tokens=int(min(32000, 6000 + 2600 * float(minutes))))
        spend.add(meta["cost_usd"])
        return text

    return small, big


def stage1(case, small, spend):
    from engine import language as lang_mod, plan as plan_mod, researcher, skills as skills_mod, vector_policy, voices
    prompt, minutes = case["prompt"], float(case.get("minutes", 2.0))
    options = dict(case.get("options") or {})
    language = lang_mod.detect(prompt, lambda s, u: small(s, u, 20))
    skill_ids = skills_mod.select(prompt, lambda s, u: small(s, u, 120), minutes)
    region = "ES" if language == "es" else "US"
    decision = researcher.decide(prompt, language=language, region=voices.clean_region(region), today=date.today().isoformat(), ask=lambda s, u, n=260: small(s, u, n))
    photos = PHOTO if case.get("photos") else None
    pol = vector_policy.decide(prompt, options=options, skill_ids=skill_ids, photos=photos, research_mode=decision.mode, minutes=minutes,
                               expected_beats=plan_mod.expected_beats(minutes, len(photos or [])), ask=lambda s, u: small(s, u, 160))
    return {"language": language, "skills": skill_ids, "research": decision.mode, "decision": "offered" if pol.allowed else "never", "reason": pol.reason, "style": pol.style,
            "share": pol.share if pol.allowed else 0, "candidates": pol.ids(), "judged": pol.judged}


def stage2(case, s1, small, big, spend):
    from engine import director
    minutes = float(case.get("minutes", 2.0))
    options = dict(case.get("options") or {})
    region = "ES" if s1["language"] == "es" else "US"
    t0 = time.time()
    r = director.direct(case["prompt"], minutes=minutes, ask_small=small, ask_big=lambda s, u: big(s, u, minutes), region=region, options=options,
                        photos=None, max_images_per_minute=10.0)
    out = {"seconds": round(time.time() - t0, 1)}
    if not r.get("legit"):
        out["declined"] = r.get("reason", "")[:120]
        return out
    plan = r["plan"]
    beats = plan["beats"]
    vec = plan.get("vector") or {}
    used = [{"beat": i, "id": (b["scene"]["props"] or {}).get("catalog_id"), "narration": b["narration"][:140]} for i, b in enumerate(beats) if b["scene"]["type"] == "vector_scene"]
    out.update({"beats": len(beats), "types": [b["scene"]["type"] for b in beats], "used": used, "vector": vec, "warnings": [w for w in r.get("warnings", []) if "cartoon" in w][:6]})
    if used:
        user = f"Request: {case['prompt']}\nBeats using a cartoon scene:\n" + "\n".join(f"- beat {u['beat']} (scene {u['id']}): {u['narration']}" for u in used)
        try:
            raw = small(JUDGE_SYSTEM, user, 500)
            j = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
            out["judge"] = j
        except Exception as e:   # a judge failure is reported, not hidden
            out["judge_error"] = f"{type(e).__name__}: {str(e)[:100]}"
    return out


def table(results):
    lines = ["| id | brief | guides | research | policy | beats | cartoon scenes | judge | $ |", "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        s1, s2 = r.get("s1") or {}, r.get("s2") or {}
        used = s2.get("used")
        judge = s2.get("judge") or {}
        shown = f"{len(used)} ({', '.join(u['id'] for u in used)})" if used else ("0" if s2 else "n/a")
        lines.append(f"| {r['id']} | {r['prompt'][:60]} | {', '.join(s1.get('skills', []))} | {s1.get('research', '')} | {s1.get('decision', '')}: {s1.get('reason', '')} | {s2.get('beats', '')} | {shown} | "
                     f"{judge.get('overall', '')} | {r.get('cost', 0):.3f} |")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-cost", type=float, default=4.0)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--stage1-only", action="store_true")
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "vector_policy_eval"))
    a = ap.parse_args()
    import boto3
    acct = boto3.client("sts").get_caller_identity()["Account"]
    if acct != "552357225438":
        sys.exit(f"refusing to run on account {acct}: QA only")
    os.makedirs(a.out, exist_ok=True)
    spend = Spend(a.max_cost)
    small, big = clients(spend)
    cases = [c for c in CASES if not a.only or c["id"] in a.only]
    results = {c["id"]: {"id": c["id"], "prompt": c["prompt"], "expect": c["expect"], "cost": 0.0} for c in cases}

    def s1job(c):
        if spend.over:
            return
        before = spend.total
        try:
            results[c["id"]]["s1"] = stage1(c, small, spend)
        except Exception as e:
            results[c["id"]]["s1_error"] = f"{type(e).__name__}: {str(e)[:200]}"
        results[c["id"]]["cost"] += spend.total - before

    with ThreadPoolExecutor(max_workers=2) as ex:
        list(ex.map(s1job, cases))
    print(f"stage 1 done, spend ${spend.total:.3f}")
    if not a.stage1_only:
        for c in cases:
            r = results[c["id"]]
            s1 = r.get("s1")
            if not s1 or spend.over:
                continue
            if s1["decision"] != "offered" and c["id"] not in PLAN_EXTRA_NEVER:
                continue
            before = spend.total
            try:
                r["s2"] = stage2(c, s1, small, big, spend)
            except Exception as e:
                r["s2_error"] = f"{type(e).__name__}: {str(e)[:200]}"
            r["cost"] += spend.total - before
            print(f"  {c['id']}: {s1['decision']} ({s1['reason']}) used={[u['id'] for u in (r.get('s2') or {}).get('used', [])]} spend ${spend.total:.3f}")
    ordered = [results[c["id"]] for c in cases]
    json.dump({"date": date.today().isoformat(), "spend_usd": round(spend.total, 4), "results": ordered}, open(os.path.join(a.out, "results.json"), "w"), indent=1, ensure_ascii=False)
    md = table(ordered)
    open(os.path.join(a.out, "results.md"), "w").write(md + f"\n\nSpend: ${spend.total:.3f} of ${a.max_cost:.2f}\n")
    print(md)
    print(f"spend ${spend.total:.3f}")
    bad = [r["id"] for r in ordered if (r.get("s1") or {}).get("decision") == "offered" and r["expect"] == "no"]
    bad += [r["id"] for r in ordered if (r.get("s1") or {}).get("decision") == "never" and r["expect"] == "yes"]
    leaks = [r["id"] for r in ordered if r["expect"] == "no" and ((r.get("s2") or {}).get("used"))]
    print("policy mismatches:", bad, "leaks:", leaks)


if __name__ == "__main__":
    main()
