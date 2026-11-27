import json
import logging
import os
from typing import Any, Dict

from common import wallet
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
        keep_uploads(item)
        try:
            wallet.refund_video(item)
        except Exception:
            logging.exception("credit refund failed")
    return {"status": "FAILED", "video_id": video_id}


def keep_uploads(item: Dict[str, Any]) -> int:
    """A failed video can be retried ("Try again" reuses it, lambdas/video_retry.py), but the person's uploads expire after 2 days. Keep the originals that are still there with the video
    (generation/v2/<video>/retry_uploads/), like its cleaned copies, until the video is deleted. Best effort, never stops the failure handling. Returns how many were kept."""
    bucket, user, video_id = os.environ.get("ASSETS_BUCKET", ""), str(item.get("user_id") or ""), str(item.get("video_id") or "")
    if not (bucket and user and video_id and item.get("request_json")):
        return 0
    try:
        media = json.loads(item["request_json"]).get("options", {}).get("media") or []
    except (ValueError, AttributeError):
        return 0
    import boto3
    from concurrent.futures import ThreadPoolExecutor
    s3 = boto3.client("s3")

    def one(mid: str) -> int:
        try:
            s3.copy_object(CopySource={"Bucket": bucket, "Key": f"uploads/{user}/{mid}.jpg"}, Bucket=bucket, Key=f"generation/v2/{video_id}/retry_uploads/{mid}.jpg",
                           ContentType="image/jpeg", MetadataDirective="REPLACE")
            return 1
        except Exception:   # noqa: BLE001 - already consumed by the engine (the cleaned copy is kept) or never there
            return 0

    with ThreadPoolExecutor(max_workers=16) as ex:
        return sum(ex.map(one, [str(m) for m in media[:200]]))
