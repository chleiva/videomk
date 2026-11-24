#!/usr/bin/env python3
"""Audit how well a finished video's visuals line up with its narration. Free: no model, no render, just the stored timeline.

  python scripts/check_sync.py <video_id> [--profile qa] [--region eu-west-1]

Prints, for every list item, diagram node, chart bar, timeline event and gallery photo: the moment it appears, the moment the narrator names it, and the gap
(negative = it appears before it is said; about -0.15 s is by design, so the picture is up as the word is heard). Exit status 1 if anything appears more than
0.5 s early or 0.4 s late.
"""
import argparse
import json
import os
import sys

import boto3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))
from engine import sync  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("video_id")
    ap.add_argument("--profile", default="qa")
    ap.add_argument("--region", default="eu-west-1")
    ap.add_argument("--bucket", default="")
    args = ap.parse_args()
    session = boto3.Session(profile_name=args.profile, region_name=args.region)
    bucket = args.bucket or f"videomk-{args.profile}-{session.client('sts').get_caller_identity()['Account']}"
    s3 = session.client("s3")
    prefix = f"generation/v2/{args.video_id}/"
    keys = [o["Key"] for o in s3.list_objects_v2(Bucket=bucket, Prefix=prefix + "timeline_r").get("Contents", [])]
    if not keys:
        print("no timeline found for that video", file=sys.stderr)
        return 2
    key = sorted(keys, key=lambda k: int(k.rsplit("_r", 1)[1].split(".")[0]))[-1]
    tl = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
    rep = sync.report(tl)
    print(f"{key}: {tl.get('duration', 0):.0f}s, {len(tl['scenes'])} scenes, aligned beats {tl.get('sync', {}).get('aligned_beats', '?')}, captions {'on' if tl.get('captions', True) else 'off'}")
    print(f"{'scene':10s} {'type':9s} {'item':42s} {'appears':>8s} {'said':>8s} {'gap':>7s}")
    for r in rep["rows"]:
        gap = "never named" if r["delta"] is None else f"{r['delta']:+.2f}"
        if r.get("legacy"):
            gap += " *"
        print(f"{str(r['scene']):10s} {r['type']:9s} {r['item']:42s} {r['cue']:8.2f} {('' if r['mention'] is None else f'{r['mention']:.2f}'):>8s} {gap:>7s}")
    print(f"\nitems {rep['items']}, anchored to a spoken word {rep['anchored']}, early (>0.5 s) {rep['early']}, late (>0.4 s) {rep['late']}, mean |gap| {rep['mean_abs_delta']}")
    print("(* = this video predates anchoring: measured against the old fixed reveal schedule)" if any(r.get("legacy") for r in rep["rows"]) else "")
    print("SYNC OK" if rep["ok"] else "SYNC PROBLEM")
    return 0 if rep["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
