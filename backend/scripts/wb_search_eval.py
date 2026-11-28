#!/usr/bin/env python3
"""Whiteboard drawing search, the evaluation gate (docs/WHITEBOARD_DRAWING_SEARCH_2026-11-28.md): the SAME request planned with the full drawing list and with the
retrieved list, same research notes, real planner calls on QA. Prints per request: drawings used (in the library / asked), items written, prompt tokens, cost, and whether
every drawing the full-list run chose is inside the retrieved menu (recall). Results are saved as JSON so the table can be rebuilt without new calls.

  AWS_PROFILE=qa AWS_REGION=eu-west-1 BEDROCK_REGION=eu-west-1 python backend/scripts/wb_search_eval.py run  --out FILE [--minutes 0.5] [--max-cost 1.2] [--case N ...]
  AWS_PROFILE=qa ... wb_search_eval.py recall --out FILE [--k 60]     # recall of the saved full runs inside the retrieved menu for K, no planner calls (embeds queries only)
"""
import argparse
import json
import os
import re
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))
os.environ.setdefault("AWS_REGION", "eu-west-1")
os.environ.setdefault("BEDROCK_REGION", "eu-west-1")
os.environ["WHITEBOARD"] = "1"
os.environ["VIDEO_LANGUAGES"] = "en,es,fr,de,it,pt,nl"

from engine import director, llm, research, whiteboard_policy as wp  # noqa: E402
from engine.whiteboard import library, retrieval  # noqa: E402

CASES = [
    ("sundial-en", "en", "How does a sundial tell the time?"),
    ("windmill-es", "es", "Explica cómo funciona un molino de viento"),
    ("vaccine-en", "en", "How do vaccines train the immune system?"),
    ("sea-salt-fr", "fr", "Comment fait-on du sel de mer dans les marais salants ?"),
    ("compound-interest-en", "en", "Explain compound interest"),
    ("water-cycle-de", "de", "Erkläre den Wasserkreislauf"),
    ("compass-it", "it", "Come funziona una bussola?"),
    ("bread-es", "es", "Cómo se hace el pan en casa"),
    ("fridge-de", "de", "Wie funktioniert ein Kühlschrank?"),
    ("beehive-en", "en", "How do bees make honey in a beehive?"),
]
DRAW = re.compile(r'"draw"\s*:\s*"([^"]+)"')
WRITE = re.compile(r'"write"\s*:')


def run_arm(prompt, minutes, notes_cache, on):
    os.environ["WB_SEARCH"] = "1" if on else "0"
    spent, tin, raw = [0.0], [], []

    def small(system, user, max_tokens=120):
        t, m = llm.complete(system, user, max_tokens=max_tokens, model=llm.REVIEW_MODEL, effort="low")
        spent[0] += m["cost_usd"]
        return t

    def big(system, user):
        t, m = llm.complete(system, user)
        spent[0] += m["cost_usd"]
        tin.append(int(m.get("tokens_in") or 0) + int(m.get("cache_read_tokens") or 0) + int(m.get("cache_write_tokens") or 0))   # all prompt tokens, cached or not
        raw.append(t)
        return t

    orig = research.gather_notes

    def cached(p, **kw):
        if p not in notes_cache:
            notes_cache[p] = orig(p, **kw)
        return notes_cache[p]

    research.gather_notes = cached
    try:
        wp.allow_new_drawings(3)
        r = director.direct(prompt, minutes=minutes, ask_small=small, ask_big=big, ask_review=lambda s, u: "", options={"style": "whiteboard"})
    finally:
        research.gather_notes = orig
    text = "\n".join(raw[:1])      # the first planner call: what the planner chose, before any repair
    draws = DRAW.findall(text)
    ids = set(library.ids())
    return {"draws": draws, "in_library": sum(d in ids for d in draws), "asked": [d for d in draws if d not in ids], "written": len(WRITE.findall(text)),
            "tokens_in": tin[0] if tin else 0, "cost": round(spent[0], 4), "legit": r.get("legit")}


def run(a):
    out, total = {}, 0.0
    if os.path.exists(a.out):
        out = json.load(open(a.out))
    cache = {}
    for name, lang, prompt in CASES:
        if a.case and name not in a.case:
            continue
        if name in out and not a.force:
            continue
        full = run_arm(prompt, a.minutes, cache, False)
        ret = run_arm(prompt, a.minutes, cache, True)
        notes = cache.get(prompt)
        out[name] = {"prompt": prompt, "lang": lang, "full": full, "retrieved": ret, "notes": (notes[0] if notes else "")[:1500]}
        total += full["cost"] + ret["cost"]
        print(f"{name}: full {full['in_library']} lib/{len(full['asked'])} asked/{full['written']} written, {full['tokens_in']} tok ${full['cost']}; retrieved {ret['in_library']}/{len(ret['asked'])}/{ret['written']}, {ret['tokens_in']} tok ${ret['cost']}  (spent ${total:.2f})", flush=True)
        json.dump(out, open(a.out, "w"), ensure_ascii=False, indent=1)
        if total > a.max_cost:
            print("budget reached")
            break


def recall(a):
    out = json.load(open(a.out))
    os.environ["WB_SEARCH"] = "1"
    tot = hit = 0
    for name, d in out.items():
        notes = d.get("notes") or ""
        ids, info = retrieval.select(d["prompt"], notes, k=a.k)
        want = {x for x in d["full"]["draws"] if library.has(x)}
        miss = sorted(want - set(ids))
        tot += len(want)
        hit += len(want) - len(miss)
        print(f"{name}: {len(want) - len(miss)}/{len(want)} in {len(ids)} shown; missed {miss}")
    print(f"recall {hit}/{tot} = {hit / max(1, tot):.3f} at K={a.k}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "recall"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--minutes", type=float, default=0.5)
    ap.add_argument("--max-cost", type=float, default=1.2)
    ap.add_argument("--case", action="append")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--k", type=int, default=60)
    a = ap.parse_args()
    run(a) if a.cmd == "run" else recall(a)
