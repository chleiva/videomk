#!/usr/bin/env python3
"""What videos cost, from the videos table plus the Lambda compute the per-video figure does not include.

  python scripts/cost_report.py [--profile qa] [--region eu-west-1] [--since 2026-11-24] [--user <id prefix>] [--hours 24]

Per video the table keeps `cost_usd`: language models (script, research, reviews, checks), Polly speech, web searches. Newer videos also carry the breakdown
(c_speech, c_script, c_research, c_photos, c_stock, c_stt). The Lambda compute (mostly the render chunks) is read from CloudWatch for the last --hours and divided
by the videos made in that window. Step Functions, S3 and DynamoDB are well under a tenth of a cent per video and are not counted.
"""
import argparse
import datetime
import statistics
import sys
import time

import boto3

LAMBDA_GBS_PRICE, LAMBDA_REQ_PRICE = 0.0000166667, 0.0000002   # x86, per GB-second and per request
GROUPS = ["v2_plan", "v2_beat", "v2_timeline", "v2_render_chunk", "v2_audio", "v2_finalize"]
PARTS = ("speech", "script", "research", "photos", "stock", "stt")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", default="qa")
    ap.add_argument("--region", default="eu-west-1")
    ap.add_argument("--since", default="")
    ap.add_argument("--user", default="")
    ap.add_argument("--hours", type=int, default=24)
    a = ap.parse_args()
    s = boto3.Session(profile_name=a.profile, region_name=a.region)
    ddb = s.client("dynamodb")
    table = next(t for t in ddb.list_tables()["TableNames"] if t.startswith(f"videomk-{a.profile}-VideosTable"))
    items = s.resource("dynamodb").Table(table).scan()["Items"]
    rows = [i for i in items if "cost_usd" in i and not i.get("user_id", "").startswith("qa-selft") and i.get("created_at", "") >= a.since and i.get("user_id", "").startswith(a.user)]
    if not rows:
        print("no videos with a cost in that selection")
        return 1
    cost = lambda r: float(r["cost_usd"])
    done = [r for r in rows if r.get("status") == "COMPLETE"]
    failed = [r for r in rows if r.get("status") == "FAILED"]
    print(f"{len(rows)} videos ({len(done)} completed, {len(failed)} failed), tracked total ${sum(map(cost, rows)):.2f}  [{table}]")

    def line(label, rs):
        if rs:
            v = [cost(r) for r in rs]
            print(f"  {label:42s} n={len(rs):3d}  mean ${statistics.mean(v):.3f}  median ${statistics.median(v):.3f}  min ${min(v):.3f}  max ${max(v):.3f}")
    line("completed, about 1 minute (<=6 beats)", [r for r in done if int(r.get("n_beats", 0)) <= 6])
    line("completed, about 3 minutes (>=10 beats)", [r for r in done if int(r.get("n_beats", 0)) >= 10])
    line("all completed", done)
    line("failed (the credits are refunded)", failed)
    with_parts = [r for r in rows if any(f"c_{p}" in r for p in PARTS)]
    if with_parts:
        tot = {p: sum(float(r.get(f"c_{p}", 0)) for r in with_parts) for p in PARTS}
        whole = sum(map(cost, with_parts)) or 1
        print(f"  where the money goes ({len(with_parts)} videos with a breakdown): " + ", ".join(f"{p} {v / whole * 100:.0f}%" for p, v in tot.items()))
        print("     per video on average: " + ", ".join(f"{p} ${v / len(with_parts):.3f}" for p, v in tot.items()))
    logs = s.client("logs")
    end = int(time.time())
    q = logs.start_query(logGroupNames=[f"/aws/lambda/{g}" for g in GROUPS], startTime=end - a.hours * 3600, endTime=end,
                         queryString='filter @type = "REPORT" | stats sum(@billedDuration) as ms, count(*) as n, max(@memorySize) as mem by @log')
    while True:
        r = logs.get_query_results(queryId=q["queryId"])
        if r["status"] in ("Complete", "Failed", "Cancelled"):
            break
        time.sleep(2)
    gbs = calls = 0.0
    for row in r["results"]:
        d = {x["field"]: x["value"] for x in row}
        gbs += float(d["ms"]) / 1000 * float(d["mem"]) / 1048576 / 1024
        calls += int(d["n"])
    since = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=a.hours)).strftime("%Y-%m-%dT%H")
    made = len([i for i in items if i.get("created_at", "") >= since and not i.get("user_id", "").startswith("qa-selft")]) or 1
    compute = gbs * LAMBDA_GBS_PRICE + calls * LAMBDA_REQ_PRICE
    print(f"  Lambda compute, last {a.hours} h: ${compute:.2f} over {made} videos = ${compute / made:.3f} per video (renders, edits and failed runs included)")
    print(f"  => all-in per completed 1-minute video about ${statistics.mean([cost(r) for r in done if int(r.get('n_beats', 0)) <= 6] or [0]) + compute / made:.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
