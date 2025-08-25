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

    try:
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


