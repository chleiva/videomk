"""Edit workflow step 1: find the beats whose audio/photo must be re-made (everything else is reused from cache)."""
from typing import Any, Dict

from .. import awsio, plan as plan_mod


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    plan = awsio.get_json(event["plan_key"])
    ids = [b["id"] for b in plan["beats"] if plan_mod.needs_media(plan, b)]
    return {
        "video_id": event["video_id"], "user_id": event.get("user_id"), "usage_day": event.get("usage_day"),
        "plan_key": event["plan_key"], "rev": int(event["rev"]), "mode": event.get("mode", "final"),
        "cost_field": event.get("cost_field") or f"cost_r{int(event['rev'])}", "beat_ids": ids,
    }
