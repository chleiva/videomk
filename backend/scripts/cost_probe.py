#!/usr/bin/env python3
"""Plan stage only, with every model call counted (docs/COST_LEVERS_2026-11-28.md). Real Bedrock, no voice, no render.

  AWS_PROFILE=qa AWS_REGION=eu-west-1 BEDROCK_REGION=eu-west-1 python backend/scripts/cost_probe.py "prompt" [--seconds 60] [--aspect 9:16] [--style whiteboard|auto] [--region ES] [--json out.json]

Prints one line per model call (stage guessed from the system prompt, model, input/cached/output tokens, USD) and the total, plus the whiteboard score when there is one."""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))
os.environ.setdefault("CATALOG_BUCKET", "videomk-qa-catalog-552357225438")

from engine import director, format_options, llm  # noqa: E402


def stage_of(system: str, user: str) -> str:
    s = (system or "")[:400]
    for key, name in (("director of a short animated", "script"), ("repair the boards", "wb_review"), ("producer", "skills"), ("language", "language")):
        if key in s:
            return name
    return s[:40].replace("\n", " ")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("prompt")
    ap.add_argument("--seconds", type=int, default=60)
    ap.add_argument("--aspect", default="16:9")
    ap.add_argument("--style", default="auto")
    ap.add_argument("--region", default="US")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    calls = []
    real = llm.complete

    def counted(system, user, **kw):
        t0 = time.time()
        text, meta = real(system, user, **kw)
        calls.append({"stage": stage_of(system, user), "model": meta["model"].split(".")[-1], "in": meta["tokens_in"], "cache_read": meta.get("cache_read_tokens", 0),
                      "cache_write": meta.get("cache_write_tokens", 0), "out": meta["tokens_out"], "usd": round(meta["cost_usd"], 5), "s": round(time.time() - t0, 1), "system_chars": len(system), "stop": meta.get("stop_reason")})
        if os.environ.get("PROBE_DUMP"):
            open(os.path.join(os.environ["PROBE_DUMP"], f"call{len(calls):02d}_{calls[-1]['stage']}.txt"), "w").write("SYSTEM(tail)\n" + system[-1500:] + "\n\nUSER\n" + user[:3000] + "\n\nANSWER\n" + text)
        return text, meta

    llm.complete = counted
    if os.environ.get("PROBE_PREREVIEW"):   # the plan as it is when the whiteboard self-check starts, to replay the check with other settings (backend/scripts/wb_review_replay.py)
        import copy
        import pickle

        from engine import whiteboard_policy as wp
        real_review = wp.review

        def keep_then_review(plan, policy, ask, language="en"):
            pickle.dump({"plan": copy.deepcopy(plan), "aspect": policy.aspect, "language": language, "reason": policy.reason}, open(os.environ["PROBE_PREREVIEW"], "wb"))
            return real_review(plan, policy, ask, language)
        wp.review = keep_then_review

    def small(system, user, max_tokens=120):
        return llm.complete(system, user, max_tokens=max_tokens, model=llm.REVIEW_MODEL, effort="low")[0]

    def big(system, user):
        return llm.complete(system, user, max_tokens=min(32000, int(6000 + 2600 * a.seconds / 60.0)))[0]

    t0 = time.time()
    r = director.direct(a.prompt, minutes=a.seconds / 60.0, ask_small=small, ask_big=big, region=a.region,
                        options={"aspect": a.aspect, "resolution": "1080p", **({"style": a.style} if a.style != "auto" else {})})
    out = {"legit": r.get("legit"), "calls": calls, "total_usd": round(sum(c["usd"] for c in calls), 4), "seconds": round(time.time() - t0, 1)}
    if r.get("legit"):
        plan = r["plan"]
        out["beats"] = len(plan["beats"])
        wb = plan.get("whiteboard") or {}
        if wb.get("score"):
            sc = wb["score"]
            out["score"] = {k: sc.get(k) for k in ("boards", "failed", "items_per_board", "coverage", "pen_busy", "longest_idle_s", "overlaps", "collisions", "min_text", "replanned", "kept", "director_calls")}
            out["first"] = sc.get("first")
            out["complaints"] = [c for d in sc.get("boards_detail", []) for c in d.get("complaints", [])]
        out["warnings"] = [w for w in r.get("warnings", []) if "whiteboard" in w][:6]
    for c in calls:
        print(c)
    print(json.dumps({k: v for k, v in out.items() if k != "calls"}, ensure_ascii=False))
    if a.json:
        json.dump(out, open(a.json, "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
