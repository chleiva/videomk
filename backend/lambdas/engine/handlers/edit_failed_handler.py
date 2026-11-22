"""An edit failed: the existing video stays playable; only the edit session is marked failed."""
from typing import Any, Dict

from generate_video.db import set_attributes


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    video_id = str(event.get("video_id", ""))
    err = event.get("error") if isinstance(event.get("error"), dict) else {}
    if video_id:
        set_attributes(video_id, {"edit_state": "FAILED", "edit_error": str(err.get("Error") or "UNKNOWN")[:120]})
    return {"status": "EDIT_FAILED", "video_id": video_id}
