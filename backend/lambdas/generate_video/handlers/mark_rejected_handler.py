import logging
from typing import Any, Dict

from common import usage
from ..db import get_video_item, update_status


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """The prompt was judged not legitimate/safe: record why, refund the quota, stop."""
    video_id = str(event.get("video_id", ""))
    plot = event.get("plot") or {}
    reason = str(plot.get("reason") or "This request can't be turned into a video.")[:300]

    update_status(video_id, "REJECTED", extra_attributes={"reject_reason": reason})
    try:
        item = get_video_item(video_id)
        usage.refund(str(item.get("user_id") or event.get("user_id") or ""), day=item.get("usage_day"))
    except Exception:
        logging.exception("quota refund failed")
    return {"status": "REJECTED", "video_id": video_id, "reason": reason}
