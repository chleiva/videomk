import json
import os
from typing import Any, Dict


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    user_id = None
    if isinstance(event, dict):
        path_params = event.get("pathParameters") or {}
        user_id = path_params.get("user_id")

    # Placeholder: return empty list result for now
    body = {
        "user_id": user_id,
        "items": [],
        "note": "Implement query on GSI_UserVideos to return list view",
    }
    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body),
    }


