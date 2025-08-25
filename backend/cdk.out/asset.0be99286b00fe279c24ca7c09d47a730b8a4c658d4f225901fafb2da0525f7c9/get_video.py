import json
import os
from typing import Any, Dict, Optional, Tuple

import boto3
from botocore.exceptions import ClientError
from botocore.config import Config

try:
    # Reuse validation semantics from generation flow
    from generate_video.auth import validate_user_id
except Exception:
    def validate_user_id(user_id: Optional[str]) -> None:
        if not user_id:
            raise ValueError("user_id is required")


def _parse_s3_uri(s3_uri: str) -> Tuple[str, str]:
    # s3://bucket/key
    if not (isinstance(s3_uri, str) and s3_uri.startswith("s3://")):
        raise ValueError("video_uri is not a valid s3 uri")
    rest = s3_uri[len("s3://") :]
    bucket, _, key = rest.partition("/")
    if not bucket or not key:
        raise ValueError("video_uri missing bucket or key")
    return bucket, key


def _json_response(status: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "statusCode": status,
        "headers": {
            "Content-Type": "application/json",
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Headers": "Content-Type",
            "Access-Control-Allow-Methods": "GET,OPTIONS",
        },
        "body": json.dumps(body),
    }


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    # Extract path params
    path_params = (event or {}).get("pathParameters") or {}
    user_id = path_params.get("user_id")
    video_id = path_params.get("video_id")

    try:
        validate_user_id(user_id)
    except Exception as e:
        return _json_response(400, {"message": str(e)})

    if not video_id:
        return _json_response(400, {"message": "Missing required path parameter 'video_id'"})

    table_name = os.environ.get("VIDEOS_TABLE")
    if not table_name:
        return _json_response(500, {"message": "Server configuration error: VIDEOS_TABLE not set"})

    # Fetch the item
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)
    try:
        resp = table.get_item(Key={"video_id": video_id})
        item = resp.get("Item") or {}
    except ClientError as e:
        return _json_response(500, {"message": "Failed to get video", "error": str(e)})

    if not item:
        return _json_response(404, {"message": "Video not found"})

    # Ownership check
    owner = item.get("user_id")
    if owner and owner != user_id:
        return _json_response(403, {"message": "Forbidden"})

    status = (item.get("status") or "").upper()
    video_uri = item.get("video_uri")
    if not video_uri:
        # If not complete yet, signal progress
        return _json_response(409, {"message": "Video not ready", "status": status})

    try:
        bucket, key = _parse_s3_uri(video_uri)
    except ValueError as e:
        return _json_response(500, {"message": str(e)})

    # Query params for response options
    qs = (event or {}).get("queryStringParameters") or {}
    download_flag = (qs.get("download") or "").lower() in ("1", "true", "yes")
    redirect_flag = (qs.get("redirect") or "").lower() in ("1", "true", "yes")

    # Determine bucket region to avoid S3 PermanentRedirects
    try:
        meta_s3 = boto3.client("s3", region_name="us-east-1")
        loc = meta_s3.get_bucket_location(Bucket=bucket).get("LocationConstraint")
        bucket_region = loc or "us-east-1"
    except Exception:
        bucket_region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"

    # Generate a presigned URL using the bucket's region
    s3 = boto3.client("s3", region_name=bucket_region, config=Config(signature_version="s3v4"))
    disposition = (
        f"attachment; filename=\"{video_id}.mp4\"" if download_flag else "inline"
    )
    # Default to mp4; the generator uses mp4
    params = {
        "Bucket": bucket,
        "Key": key,
        "ResponseContentType": "video/mp4",
        "ResponseContentDisposition": disposition,
    }
    try:
        url = s3.generate_presigned_url(
            "get_object", Params=params, ExpiresIn=3600
        )
    except ClientError as e:
        return _json_response(500, {"message": "Failed to sign url", "error": str(e)})

    if redirect_flag:
        return {
            "statusCode": 302,
            "headers": {
                "Location": url,
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Headers": "Content-Type",
                "Access-Control-Allow-Methods": "GET,OPTIONS",
            },
            "body": "",
        }

    return _json_response(
        200,
        {
            "user_id": user_id,
            "video_id": video_id,
            "status": status,
            "url": url,
            "download": download_flag,
        },
    )


