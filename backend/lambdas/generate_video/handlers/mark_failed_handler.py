from typing import Any, Dict

from ..db import update_status


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    table_name = "Videos"
    # Expect video_id at root input
    video_id = str(event.get("video_id", "")) or str((event.get("error") or {}).get("video_id", ""))
    if video_id:
        update_status(video_id, "FAILED", table_name)
    return {"status": "FAILED", "video_id": video_id}


