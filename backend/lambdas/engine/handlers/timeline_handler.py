"""Step 3: plan + measured durations -> timeline.json and the chunk list for the render fan-out."""
import os
from typing import Any, Dict

from .. import awsio
from ..timeline import build_timeline, chunk_ranges

MAX_DURATION_S = float(os.environ.get("MAX_VIDEO_SECONDS", str(13 * 60)))
CHUNK_SECONDS = int(os.environ.get("CHUNK_SECONDS", "30"))


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    video_id = str(event["video_id"])
    pfx = awsio.prefix(video_id)
    plan = awsio.get_json(event["plan_key"])
    results = sorted(event["beats"], key=lambda r: int(r["i"]))
    if [int(r["i"]) for r in results] != list(range(len(plan["beats"]))):
        raise ValueError("beat results do not cover the plan")

    tl = build_timeline(plan, results, video_id=video_id, fps=30)
    if tl["duration"] > MAX_DURATION_S:
        raise ValueError(f"video too long ({tl['duration']:.0f}s > {MAX_DURATION_S:.0f}s)")
    tl["ledger"] = [r["ledger"] for r in results if r.get("ledger")]
    tl["sources"] = plan.get("sources", [])
    tl["description"] = plan.get("description", "")
    key = pfx + "timeline.json"
    awsio.put_json(key, tl)
    return {
        "video_id": video_id,
        "user_id": event.get("user_id"),
        "usage_day": event.get("usage_day"),
        "timeline_key": key,
        "duration": tl["duration"],
        "chunks": [{**c, "video_id": video_id, "timeline_key": key} for c in chunk_ranges(tl, CHUNK_SECONDS)],
    }
