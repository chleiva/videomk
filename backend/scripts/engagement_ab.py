#!/usr/bin/env python3
"""Deterministic engagement metrics over two audit run folders (see docs/QUALITY_REVIEW.md): python scripts/engagement_ab.py <before_dir> <after_dir>
Per plan: first scene is a title card, hook beat words, banned openers/clichés, max same-scene run, words per beat, generic ending, definition-card openers; plus the judge means."""
import glob
import json
import os
import re
import statistics as st
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))
from engine import engagement  # noqa: E402

CLICHE = re.compile("|".join(re.escape(x) for x in engagement.BANNED_EN + engagement.BANNED_ES), re.I)
GENERIC_END = re.compile(r"(thanks? for watching|gracias por|subscribe|suscr|see you|nos vemos|in conclusion|en conclusi)", re.I)


def metrics(run):
    beats = run["plan"]["beats"]
    narr = [b.get("narration") or "" for b in beats]
    types = [b["scene"]["type"] for b in beats]
    runmax = cur = 1
    for a, b in zip(types, types[1:]):
        cur = cur + 1 if a == b else 1
        runmax = max(runmax, cur)
    spoken = [n for n in narr if n.strip()]
    return {"title_first": types[0] in ("title", "title_short"), "hook_words": len(narr[0].split()), "cliches": len(CLICHE.findall(" ".join(narr))),
            "max_run": runmax, "beat_words": st.mean(len(n.split()) for n in spoken), "generic_end": bool(GENERIC_END.search(narr[-1])), "beats": len(beats),
            "types": len(set(types)), "def_open": sum(1 for t in types if t in ("definition", "term"))}


def load(d):
    out = {}
    for f in glob.glob(os.path.join(d, "*.json")):
        r = json.load(open(f))
        if r.get("plan"):
            out[os.path.basename(f)[:-5]] = r
    return out


def main(a, b):
    A, B = load(a), load(b)
    ids = sorted(set(A) & set(B))
    print(f"{len(ids)} prompts in both")
    keys = ["title_first", "hook_words", "cliches", "max_run", "beat_words", "generic_end", "beats", "types", "def_open"]
    print("metric | before | after")
    for k in keys:
        va = st.mean(float(metrics(A[i])[k]) for i in ids); vb = st.mean(float(metrics(B[i])[k]) for i in ids)
        print(f"{k} | {va:.2f} | {vb:.2f}")
    def jm(R, key):
        vals = [R[i]["judge"]["scores"][key]["score"] for i in ids if R[i].get("judge") and R[i]["judge"].get("scores")]
        return st.mean(vals) if vals else float("nan")
    for k in ["accuracy", "coverage", "structure", "hook_ending", "tone", "visuals", "originality", "instructions", "language"]:
        try:
            print(f"judge.{k} | {jm(A, k):.2f} | {jm(B, k):.2f}")
        except KeyError:
            pass
    def cost(R):
        return st.mean(R[i]["cost"]["total"] for i in ids if R[i].get("cost"))
    def secs(R):
        return st.mean(R[i].get("timings", {}).get("total_s", 0) for i in ids)
    print(f"cost per plan | {cost(A):.3f} | {cost(B):.3f}")
    print(f"plan seconds | {secs(A):.1f} | {secs(B):.1f}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
