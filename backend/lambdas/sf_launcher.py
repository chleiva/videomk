import json
import os
import time
import uuid
import logging
import boto3
from typing import Any, Dict, Optional


_sfn = boto3.client("stepfunctions")
_dynamodb = boto3.resource("dynamodb")


def _get_table(table_name: Optional[str] = None):
    name = table_name or "Videos"
    if not name:
        raise RuntimeError("VIDEOS_TABLE environment variable is not set")
    return _dynamodb.Table(name)


def _extract_cognito_sub(event: Dict[str, Any]) -> Optional[str]:
    """
    Try to extract the Cognito user id (sub) from API Gateway authorizer context.
    Supports REST API (authorizer.claims.sub) and HTTP API (authorizer.jwt.claims.sub).
    """
    try:
        rc = (event or {}).get("requestContext") or {}
        authz = rc.get("authorizer") or {}
        # REST API with Cognito User Pool authorizer
        claims = authz.get("claims") or {}
        if isinstance(claims, dict):
            sub = claims.get("sub") or claims.get("cognito:username")
            if sub:
                return str(sub)
        # HTTP API with JWT authorizer
        jwt = authz.get("jwt") or {}
        jwt_claims = jwt.get("claims") or {}
        if isinstance(jwt_claims, dict):
            sub = jwt_claims.get("sub") or jwt_claims.get("cognito:username")
            if sub:
                return str(sub)
    except Exception:
        pass
    return None


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
    # Derive user_id from Cognito when available, else fall back to path param
    auth_user_id = _extract_cognito_sub(event)
    path_user_id = path_params.get("user_id")
    effective_user_id = auth_user_id or path_user_id or ""
    packed["user_id"] = effective_user_id

    # Log user identity details and possible mismatch
    logging.info(
        "Launcher received user identity: auth_user_id=%s path_user_id=%s effective_user_id=%s",
        auth_user_id,
        path_user_id,
        effective_user_id,
    )
    if auth_user_id and path_user_id and auth_user_id != path_user_id:
        logging.warning(
            "user_id mismatch: using Cognito auth_user_id=%s over path_user_id=%s",
            auth_user_id,
            path_user_id,
        )
    return packed


def handler(event: Dict[str, Any], context: Any):
    table_name = "Videos"
    # Discover state machine by name to avoid env vars
    sm_name = "generate_video_workflow"
    sm_arn = None
    paginator = _sfn.get_paginator("list_state_machines")
    for page in paginator.paginate():
        for sm in page.get("stateMachines", []) or []:
            if sm.get("name") == sm_name:
                sm_arn = sm.get("stateMachineArn")
                break
        if sm_arn:
            break
    if not sm_arn:
        raise RuntimeError("State machine 'generate_video_workflow' not found")
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


