from typing import Any, Dict, List, Optional

from .db import update_status


def create_storyboard(
    video_id: str, plot: Dict[str, Any], assets: Dict[str, Any], table_name: Optional[str] = None
) -> Dict[str, Any]:
    # Update status to STORYBOARD_CREATION (idempotent)
    update_status(video_id, "STORYBOARD_CREATION", table_name)

    # Placeholder storyboard compatible with MoviePy-like instructions
    storyboard: Dict[str, Any] = {
        "timeline": [
            {
                "start_s": 0,
                "duration_s": 3,
                "image": assets.get("images", [{}])[0].get("s3"),
                "text": assets.get("texts", [{}])[0].get("content"),
                "effects": ["fadein"],
            }
        ]
    }

    update_status(
        video_id, "RENDERING", table_name, extra_attributes={"storyboard": storyboard}
    )
    return storyboard


