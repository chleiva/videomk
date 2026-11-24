"""Step 3: merge measured media into the plan, build the timeline, and plan content-addressed chunks."""
import os
from typing import Any, Dict

from .. import awsio
from ..timeline import beat_info_from_plan, build_timeline, chunk_plan

MAX_DURATION_S = float(os.environ.get("MAX_VIDEO_SECONDS", str(13 * 60)))
CHUNK_SECONDS = int(os.environ.get("CHUNK_SECONDS", "30"))


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    video_id = str(event["video_id"])
    rev = int(event.get("rev", 1))
    mode = event.get("mode", "final")
    pfx = awsio.prefix(video_id)
    plan = awsio.get_json(event["plan_key"])

    new_media = {r["id"]: r["media"] for r in event.get("beats") or []}
    for b in plan["beats"]:
        if b["id"] in new_media:
            b["media"] = new_media[b["id"]]
        if not (b.get("media") or {}).get("duration"):
            raise ValueError(f"beat {b['id']} has no audio")
    awsio.put_json(event["plan_key"], plan)  # the plan now carries its measured media (editor + future edits read it)

    tl = build_timeline(plan, beat_info_from_plan(plan), video_id=video_id, fps=30)
    if tl["duration"] > MAX_DURATION_S:
        raise ValueError(f"video too long ({tl['duration']:.0f}s > {MAX_DURATION_S:.0f}s)")
    tl["ledger"] = [b["media"]["ledger"] for b in plan["beats"] if b["scene"]["type"] in ("image", "clip") and (b.get("media") or {}).get("ledger")]
    tl["ledger"] += [g["ledger"] for b in plan["beats"] if b["scene"]["type"] == "gallery" for g in (b.get("media") or {}).get("gallery") or [] if g.get("ledger")]
    tl["sources"] = plan.get("sources", [])
    tl["description"] = plan.get("description", "")
    tl["language"] = plan.get("language", "en")
    key = f"{pfx}timeline_r{rev}.json"
    awsio.put_json(key, tl)
    return {
        "video_id": video_id,
        "user_id": event.get("user_id"),
        "usage_day": event.get("usage_day"),
        "plan_key": event["plan_key"],
        "rev": rev,
        "mode": mode,
        "timeline_key": key,
        "duration": tl["duration"],
        "chunks": [{**c, "video_id": video_id, "timeline_key": key} for c in chunk_plan(tl, CHUNK_SECONDS, draft=(mode == "preview"))],
    }
