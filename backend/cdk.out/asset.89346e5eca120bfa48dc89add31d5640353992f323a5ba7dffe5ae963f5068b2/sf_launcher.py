import json
import os
import time
import uuid
import boto3
from typing import Any, Dict, Optional


_sfn = boto3.client("stepfunctions")
_dynamodb = boto3.resource("dynamodb")


def _get_table(table_name: Optional[str] = None):
    name = table_name or os.environ.get("VIDEOS_TABLE", "")
    if not name:
        raise RuntimeError("VIDEOS_TABLE environment variable is not set")
    return _dynamodb.Table(name)


def _register_intent(
    *,
    user_id: str,
    prompt: str,
    video_id: str,
    table_name: Optional[str] = None,
) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "video_id": video_id,
        "user_id": user_id,
        "prompt": prompt,
        "status": "STARTED_PROCESSING",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    table = _get_table(table_name)
    table.put_item(Item=item)
    return item


def _pack_input(event: Dict[str, Any]) -> Dict[str, Any]:
    path_params = event.get("pathParameters") or {}
    query = event.get("queryStringParameters") or {}
    headers = event.get("headers") or {}

    body = event.get("body")
    if isinstance(body, str):
        try:
            body = json.loads(body)
        except json.JSONDecodeError:
            body = {"raw": body}
    elif not isinstance(body, dict):
        body = {}

    packed = {
        "path": path_params,
        "query": query,
        "headers": headers,
        "body": body,
    }
    # convenience fan-out of common path param
    if "user_id" in path_params and "user_id" not in packed:
        packed["user_id"] = path_params["user_id"]
    return packed


def handler(event: Dict[str, Any], context: Any):
    sm_arn = os.environ["STATE_MACHINE_ARN"]
    table_name = os.environ.get("VIDEOS_TABLE", "")
    input_obj = _pack_input(event)

    # Extract needed fields
    user_id = input_obj.get("user_id") or ""
    prompt = ""
    body = input_obj.get("body") or {}
    if isinstance(body, dict):
        prompt = body.get("prompt", "")

    # Generate video_id and persist an initial record
    video_id = str(uuid.uuid4())
    input_obj["video_id"] = video_id

    try:
        _register_intent(
            user_id=user_id,
            prompt=prompt,
            video_id=video_id,
            table_name=table_name or None,
        )

        resp = _sfn.start_execution(
            stateMachineArn=sm_arn,
            input=json.dumps(input_obj),
        )

        start_date = resp.get("startDate")
        if hasattr(start_date, "isoformat"):
            start_date_str = start_date.isoformat()
        elif start_date is None:
            start_date_str = ""
        else:
            start_date_str = str(start_date)

        body_payload = {
            "message": "workflow started",
            "video_id": video_id,
            "executionArn": resp.get("executionArn"),
            "startDate": start_date_str,
        }

        return {
            "statusCode": 202,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "isBase64Encoded": False,
            "body": json.dumps(body_payload),
        }
    except Exception as e:
        error_payload = {
            "message": "Failed to start workflow",
            "error": str(e),
        }
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
            },
            "isBase64Encoded": False,
            "body": json.dumps(error_payload),
        }


