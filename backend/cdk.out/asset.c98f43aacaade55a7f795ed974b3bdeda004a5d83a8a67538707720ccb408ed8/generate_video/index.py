import json
import os
from typing import Any, Dict


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    videos_table = os.environ.get("VIDEOS_TABLE", "")
    user_id = None
    # If triggered via Step Functions, input may be direct dict
    # The API Gateway StartExecution template wraps input with user_id and body
    if isinstance(event, dict):
        user_id = event.get("user_id") or event.get("pathParameters", {}).get("user_id")

    response = {
        "message": "generate_video started",
        "videos_table": videos_table,
        "user_id": user_id,
    }
    return response


