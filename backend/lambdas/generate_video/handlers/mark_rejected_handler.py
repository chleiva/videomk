import logging
from typing import Any, Dict

from common import wallet
from ..db import get_video_item, update_status


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """The prompt was judged not legitimate/safe: record why, refund the quota, stop."""
    video_id = str(event.get("video_id", ""))
    plot = event.get("plot") or {}
    reason = str(plot.get("reason") or "This request can't be turned into a video.")[:300]

    update_status(video_id, "REJECTED", extra_attributes={"reject_reason": reason})
    try:
        item = get_video_item(video_id)
        wallet.refund_video(item)
    except Exception:
        logging.exception("credit refund failed")
    return {"status": "REJECTED", "video_id": video_id, "reason": reason}
