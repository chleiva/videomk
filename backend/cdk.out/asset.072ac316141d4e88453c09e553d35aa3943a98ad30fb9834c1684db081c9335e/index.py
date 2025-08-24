import json
import os
from typing import Any, Dict, Tuple

from .auth import validate_user_id
from .register_intent import register_intent
from .plot_creation import create_plot
from .assets_creation import create_assets
from .storyboard_creation import create_storyboard
from .render import render_video


def _extract_user_and_prompt(event: Dict[str, Any]) -> Tuple[str, str]:
    user_id = None
    body: Dict[str, Any] = {}

    if isinstance(event, dict):
        # From Step Functions → event like {"user_id": "...", "body": {...}}
        if "user_id" in event and "body" in event:
            user_id = event.get("user_id")
            body = event.get("body") or {}
        else:
            # Direct Lambda/APIGW invocation style
            user_id = event.get("pathParameters", {}).get("user_id")
            raw_body = event.get("body")
            if isinstance(raw_body, str):
                try:
                    body = json.loads(raw_body or "{}")
                except json.JSONDecodeError:
                    body = {}
            elif isinstance(raw_body, dict):
                body = raw_body

    prompt = body.get("prompt") if isinstance(body, dict) else None
    return user_id or "", (prompt or "")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    table_name = os.environ.get("VIDEOS_TABLE", "")

    user_id, prompt = _extract_user_and_prompt(event)
    validate_user_id(user_id)

    # 1) Register Intent (STARTED_PROCESSING)
    record = register_intent(user_id=user_id, prompt=prompt, table_name=table_name)
    video_id = record["video_id"]

    # 2) Plot Creation (updates → PLOT_CREATION then → ASSETS_CREATION)
    plot = create_plot(video_id=video_id, prompt=prompt, table_name=table_name)

    # 3) Assets Creation (updates → STORYBOARD_CREATION)
    assets = create_assets(video_id=video_id, plot=plot, table_name=table_name)

    # 4) Storyboard Creation (updates → RENDERING)
    storyboard = create_storyboard(
        video_id=video_id, plot=plot, assets=assets, table_name=table_name
    )

    # 5) Render (updates → COMPLETE)
    final = render_video(
        video_id=video_id,
        user_id=user_id,
        assets=assets,
        storyboard=storyboard,
        table_name=table_name,
    )

    return {
        "message": "generate_video started",
        "user_id": user_id,
        "video_id": video_id,
        "final": final,
    }


