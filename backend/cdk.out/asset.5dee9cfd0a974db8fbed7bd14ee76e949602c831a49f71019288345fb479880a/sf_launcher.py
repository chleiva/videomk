import json
import os
import boto3
from typing import Any, Dict


_sfn = boto3.client("stepfunctions")


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
    input_obj = _pack_input(event)

    resp = _sfn.start_execution(
        stateMachineArn=sm_arn,
        input=json.dumps(input_obj),
    )

    return {
        "statusCode": 202,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({
            "message": "workflow started",
            "executionArn": resp.get("executionArn"),
            "startDate": resp.get("startDate", ""),
        }),
    }


