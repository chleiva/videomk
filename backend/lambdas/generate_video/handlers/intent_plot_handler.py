import logging
from typing import Any, Dict

from ..auth import validate_user_id
from ..plot_creation import create_plot


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    table_name = "Videos"

    user_id = str(event.get("user_id", ""))
    body = event.get("body") or {}
    prompt = ""
    if isinstance(body, dict):
        prompt = str(body.get("prompt", ""))
    video_id = str(event.get("video_id", ""))

    logging.info("intent_plot_handler: user_id=%s video_id=%s", user_id, video_id)
    validate_user_id(user_id)
    if not video_id:
        raise ValueError("video_id not provided in event payload")

    plot = create_plot(video_id=video_id, prompt=prompt, table_name=table_name)
    # Return running state with additions
    out = dict(event)
    out["prompt"] = prompt
    out["plot"] = plot
    return out


