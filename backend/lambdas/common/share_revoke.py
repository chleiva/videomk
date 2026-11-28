"""Take back a shared link when a video or an account is deleted (docs/SHARE_PREVIEWS_2026-11-28.md).

Feature off = no error: without SHARE_BUCKET in the environment (the share stack is not deployed or not wired to this function) nothing is done. A failure is logged
(`SHARE_REVOKE_FAILED`) and never blocks the deletion itself; the copy under an unguessable token is then removed by the owner's DELETE .../share or by the next run.
Called BEFORE the video row is deleted: the token lives on the row.
"""
import logging
import os
from typing import Any, Dict, Optional

logger = logging.getLogger()


def enabled() -> bool:
    return bool(os.environ.get("SHARE_BUCKET"))


def revoke_item(item: Dict[str, Any], s3: Any = None) -> bool:
    """Delete the shared copy named by `item['share_token']` and invalidate the CDN. True when a copy was removed. Never raises."""
    token = item.get("share_token") if isinstance(item, dict) else None
    bucket = os.environ.get("SHARE_BUCKET")
    if not token or not bucket:
        return False
    try:
        try:
            from share import share_api, share_page
        except ImportError:   # pragma: no cover - flat bundle
            import share_api, share_page  # type: ignore
        if not share_page.valid_token(token):
            return False
        if s3 is None:
            import boto3
            s3 = boto3.client("s3")
        share_api._revoke(token, bucket, s3)
        return True
    except Exception:   # noqa: BLE001
        logger.exception("SHARE_REVOKE_FAILED")
        return False
