import logging
from typing import Any, Dict

from ..auth import validate_user_id
from ..plot_creation import create_plot


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    user_id = str(event.get("user_id", ""))
    video_id = str(event.get("video_id", ""))
    # `prompt` is top-level in the new input shape; fall back to legacy body.prompt
    prompt = event.get("prompt")
    if prompt is None:
        body = event.get("body")
        prompt = body.get("prompt", "") if isinstance(body, dict) else ""
    prompt = str(prompt)

    logging.info("intent_plot_handler: video_id=%s prompt_chars=%d", video_id, len(prompt))
    validate_user_id(user_id)
    if not video_id:
        raise ValueError("video_id not provided in event payload")

    plot = create_plot(video_id=video_id, prompt=prompt)
    out = dict(event)
    out["prompt"] = prompt
    out["plot"] = plot
    return out
