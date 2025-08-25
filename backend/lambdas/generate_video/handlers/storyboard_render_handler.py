from typing import Any, Dict

from ..storyboard_creation import create_storyboard
from ..render import render_video


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    table_name = "Videos"

    video_id = str(event.get("video_id", ""))
    user_id = str(event.get("user_id", ""))
    plot = event.get("plot") or {}
    assets = event.get("assets") or {}

    storyboard = create_storyboard(video_id=video_id, plot=plot, assets=assets, table_name=table_name)
    final = render_video(video_id=video_id, user_id=user_id, assets=assets, storyboard=storyboard, table_name=table_name)

    out = dict(event)
    out["storyboard"] = storyboard
    out["final"] = final
    return out


