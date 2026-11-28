#!/usr/bin/env python3
"""Replay the whiteboard self-check on a plan saved before it ran (cost_probe.py with PROBE_PREREVIEW=file.pkl), with other settings, to compare cost and score.

  AWS_PROFILE=qa AWS_REGION=eu-west-1 BEDROCK_REGION=eu-west-1 python backend/scripts/wb_review_replay.py file.pkl --model haiku|sonnet --effort low|medium [--json out.json]
"""
import argparse
import copy
import json
import os
import pickle
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))
os.environ.setdefault("CATALOG_BUCKET", "videomk-qa-catalog-552357225438")
os.environ.setdefault("WHITEBOARD", "1")

from engine import llm, whiteboard_policy as wp  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pkl")
    ap.add_argument("--model", default="sonnet", choices=("haiku", "sonnet"))
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--json", default="")
    a = ap.parse_args()
    d = pickle.load(open(a.pkl, "rb"))
    plan = copy.deepcopy(d["plan"])
    pol = wp.Policy(True, d["reason"], aspect=d["aspect"])
    model = llm.REVIEW_MODEL if a.model == "haiku" else llm.PRIMARY_MODEL
    calls = []

    def ask(system, user):
        text, meta = llm.complete(system, user, max_tokens=8600, model=model, effort=a.effort)
        calls.append({"in": meta["tokens_in"], "out": meta["tokens_out"], "usd": round(meta["cost_usd"], 5), "stop": meta.get("stop_reason")})
        return text

    notes = wp.review(plan, pol, ask, d["language"])
    sc = plan["whiteboard"]["score"]
    complaints = [c for b in sc.get("boards_detail", []) for c in b.get("complaints", [])]
    out = {"model": a.model, "effort": a.effort, "calls": calls, "usd": round(sum(c["usd"] for c in calls), 4), "boards": sc.get("boards"), "failed": sc.get("failed"), "complaints": len(complaints),
           "kept": sc.get("kept"), "replanned": sc.get("replanned"), "items_per_board": sc.get("items_per_board"), "coverage": sc.get("coverage"), "pen_busy": sc.get("pen_busy"),
           "first_failed": (sc.get("first") or {}).get("failed")}
    print(json.dumps(out))
    if a.json:
        json.dump(out, open(a.json, "w"))


if __name__ == "__main__":
    main()
