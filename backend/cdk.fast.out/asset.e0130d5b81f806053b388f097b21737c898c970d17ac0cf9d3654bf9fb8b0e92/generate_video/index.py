import json
import os
from typing import Any, Dict, Tuple

from .auth import validate_user_id
from .plot_creation import create_plot
from .assets_creation import create_assets
from .storyboard_creation import create_storyboard
from .render import render_video


def _extract_user_prompt_and_video_id(event: Dict[str, Any]) -> Tuple[str, str, str]:
    user_id = None
    body: Dict[str, Any] = {}
    video_id = None

    if isinstance(event, dict):
        # From Step Functions → event like {"user_id": "...", "body": {...}}
        if "user_id" in event and "body" in event:
            user_id = event.get("user_id")
            body = event.get("body") or {}
            video_id = event.get("video_id") or (body.get("video_id") if isinstance(body, dict) else None)
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
            if isinstance(body, dict):
                video_id = body.get("video_id")

    prompt = body.get("prompt") if isinstance(body, dict) else None
    return user_id or "", (prompt or ""), (video_id or "")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    table_name = os.environ.get("VIDEOS_TABLE", "")

    user_id, prompt, video_id = _extract_user_prompt_and_video_id(event)
    validate_user_id(user_id)
    if not video_id:
        raise ValueError("video_id not provided in event payload")

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

    payload = {
        "message": "generate_video started",
        "user_id": user_id,
        "video_id": video_id,
        "final": final,
    }

    # If invoked via API Gateway Lambda Proxy, return proxy response shape
    if isinstance(event, dict) and (
        "httpMethod" in event or "requestContext" in event or "resource" in event
    ):
        return {
            "statusCode": 200,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(payload),
        }

    # Fallback: raw payload (e.g., direct invocation/tests)
    return payload


