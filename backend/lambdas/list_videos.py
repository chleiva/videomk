import json
import os
import logging
from typing import Any, Dict, Optional

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from decimal import Decimal


def _extract_cognito_sub(event: Dict[str, Any]) -> Optional[str]:
    try:
        rc = (event or {}).get("requestContext") or {}
        authz = rc.get("authorizer") or {}
        claims = authz.get("claims") or {}
        if isinstance(claims, dict):
            sub = claims.get("sub") or claims.get("cognito:username")
            if sub:
                return str(sub)
        jwt = authz.get("jwt") or {}
        jwt_claims = jwt.get("claims") or {}
        if isinstance(jwt_claims, dict):
            sub = jwt_claims.get("sub") or jwt_claims.get("cognito:username")
            if sub:
                return str(sub)
    except Exception:
        pass
    return None


def _json_default(obj: Any):
    if isinstance(obj, Decimal):
        # Convert to int when integral, else float
        return int(obj) if obj % 1 == 0 else float(obj)
    raise TypeError(f"Object of type {obj.__class__.__name__} is not JSON serializable")


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    user_id = None
    path_params = {}
    if isinstance(event, dict):
        path_params = event.get("pathParameters") or {}
        path_user_id = path_params.get("user_id")
        auth_user_id = _extract_cognito_sub(event)

        logging.info(
            "list_videos identity: auth_user_id=%s path_user_id=%s",
            auth_user_id,
            path_user_id,
        )

        # Enforce that a user_id is provided in the path
        if not path_user_id:
            return {
                "statusCode": 400,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type",
                    "Access-Control-Allow-Methods": "GET,OPTIONS",
                },
                "body": json.dumps({"message": "Missing required path parameter 'user_id'"}),
            }

        # Enforce that request is authenticated and matches the path user
        if not auth_user_id:
            return {
                "statusCode": 401,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type",
                    "Access-Control-Allow-Methods": "GET,OPTIONS",
                },
                "body": json.dumps({"message": "Unauthorized"}),
            }
        if auth_user_id != path_user_id:
            return {
                "statusCode": 403,
                "headers": {
                    "Content-Type": "application/json",
                    "Access-Control-Allow-Origin": "*",
                    "Access-Control-Allow-Headers": "Content-Type",
                    "Access-Control-Allow-Methods": "GET,OPTIONS",
                },
                "body": json.dumps({"message": "Forbidden"}),
            }

        user_id = path_user_id

    table_name = os.environ.get("VIDEOS_TABLE")
    index_name = os.environ.get("GSI_USER_VIDEOS", "GSI_UserVideos")

    if not table_name:
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "GET,OPTIONS",
            },
            "body": json.dumps({"message": "Server configuration error: VIDEOS_TABLE not set"}),
        }

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    try:
        response = table.query(
            IndexName=index_name,
            KeyConditionExpression=Key("user_id").eq(user_id),
            ScanIndexForward=False,  # newest first by created_at
        )
        items = response.get("Items", [])
        body = {"user_id": user_id, "items": items}
        return {
            "statusCode": 200,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "GET,OPTIONS",
            },
            "body": json.dumps(body, default=_json_default),
        }
    except ClientError as e:
        return {
            "statusCode": 500,
            "headers": {
                "Content-Type": "application/json",
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "GET,OPTIONS",
            },
            "body": json.dumps({"message": "Failed to query videos", "error": str(e)}),
        }


