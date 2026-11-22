"""Shared auth/ownership checks for the editor API."""
import os
from typing import Any, Dict, Optional, Tuple

import boto3

from common.http import json_response
from common.identity import extract_cognito_sub


def load_owned_video(event: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """-> (item, error_response). Auth, path match, ownership, and 'editable by the v2 engine' in one place."""
    path = (event or {}).get("pathParameters") or {}
    user_id, video_id = path.get("user_id"), path.get("video_id")
    sub = extract_cognito_sub(event)
    if not sub:
        return None, json_response(401, {"message": "Unauthorized"})
    if not user_id or user_id != sub:
        return None, json_response(403, {"message": "Forbidden"})
    if not video_id:
        return None, json_response(400, {"message": "Missing video_id"})
    item = boto3.resource("dynamodb").Table(os.environ.get("VIDEOS_TABLE", "Videos")).get_item(Key={"video_id": video_id}).get("Item")
    if not item:
        return None, json_response(404, {"message": "Video not found"})
    if item.get("user_id") != sub:  # same answer as 'not found' would leak existence; 403 matches get_video
        return None, json_response(403, {"message": "Forbidden"})
    if not item.get("plan_key"):
        return None, json_response(409, {"message": "This video was made with the previous engine and can't be edited."})
    return item, None
