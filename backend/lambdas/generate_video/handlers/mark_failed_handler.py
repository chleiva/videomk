import logging
from typing import Any, Dict

from common import usage
from ..db import get_video_item, update_status


def _error_summary(event: Dict[str, Any]) -> str:
    err = event.get("error")
    if isinstance(err, dict):
        return str(err.get("Error") or "")[:200]
    return ""


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    video_id = str(event.get("video_id", ""))
    if not video_id:
        return {"status": "FAILED", "video_id": ""}

    updated = update_status(video_id, "FAILED", extra_attributes={"failure_code": _error_summary(event) or "UNKNOWN"})
    if updated:  # only refund when we actually moved the video to FAILED
        item = get_video_item(video_id)
        try:
            usage.refund(str(item.get("user_id") or event.get("user_id") or ""), day=item.get("usage_day"))
        except Exception:
            logging.exception("quota refund failed")
    return {"status": "FAILED", "video_id": video_id}
