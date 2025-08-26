import json
import os
import logging
from typing import Any, Dict, Optional

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError
from decimal import Decimal
from botocore.config import Config
from boto3.dynamodb.types import TypeDeserializer


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

        # For GSIs with limited projection, fetch full items to access video_uri/preview_gif_uri
        # Preserve original order
        ids_in_order = [it.get("video_id") for it in items if it.get("video_id")]
        if ids_in_order:
            ddb_client = boto3.client("dynamodb")
            deserializer = TypeDeserializer()
            keys = [{"video_id": {"S": vid}} for vid in ids_in_order]
            request = {table_name: {"Keys": keys}}
            full_items_map: Dict[str, Dict[str, Any]] = {}
            try:
                resp_bg = ddb_client.batch_get_item(RequestItems=request)
                raw_items = resp_bg.get("Responses", {}).get(table_name, [])
                for raw in raw_items:
                    item_py = {k: deserializer.deserialize(v) for k, v in raw.items()}
                    vid = item_py.get("video_id")
                    if isinstance(vid, str):
                        full_items_map[vid] = item_py
                # Note: ignoring UnprocessedKeys for simplicity; typical page sizes are small
                # Fall back to originals when not found
                merged_items = []
                for it in items:
                    vid = it.get("video_id")
                    merged_items.append(full_items_map.get(vid, it))
                items = merged_items
            except Exception:
                # If batch get fails, continue with projected items
                pass

        # Enrich items with presigned preview_gif_url when available
        def _parse_s3_uri(s3_uri: str):
            if not (isinstance(s3_uri, str) and s3_uri.startswith("s3://")):
                return None, None
            rest = s3_uri[len("s3://") :]
            bucket, _, key = rest.partition("/")
            if not bucket or not key:
                return None, None
            return bucket, key

        bucket_region_cache: Dict[str, str] = {}
        s3_meta = boto3.client("s3", region_name="us-east-1")

        def _get_bucket_region(bucket: str) -> str:
            if not bucket:
                return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
            if bucket in bucket_region_cache:
                return bucket_region_cache[bucket]
            try:
                loc = s3_meta.get_bucket_location(Bucket=bucket).get("LocationConstraint")
                region = loc or "us-east-1"
            except Exception:
                region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
            bucket_region_cache[bucket] = region
            return region

        enriched: list[dict] = []
        s3_client_cache: Dict[str, Any] = {}

        def _get_s3_client(region: str):
            if region not in s3_client_cache:
                s3_client_cache[region] = boto3.client(
                    "s3",
                    region_name=region,
                    config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}),
                )
            return s3_client_cache[region]

        for it in items:
            try:
                gif_uri = it.get("preview_gif_uri")
                if isinstance(gif_uri, str) and gif_uri.startswith("s3://"):
                    bucket, key = _parse_s3_uri(gif_uri)
                    if bucket and key:
                        region = _get_bucket_region(bucket)
                        s3 = _get_s3_client(region)
                        try:
                            url = s3.generate_presigned_url(
                                "get_object",
                                Params={
                                    "Bucket": bucket,
                                    "Key": key,
                                    "ResponseContentType": "image/gif",
                                },
                                ExpiresIn=3600,
                            )
                            it["preview_gif_url"] = url
                        except ClientError:
                            pass
                else:
                    # Try to synthesize from video_uri → replace extension with .gif
                    video_uri = it.get("video_uri")
                    if isinstance(video_uri, str) and video_uri.startswith("s3://"):
                        vb, vk = _parse_s3_uri(video_uri)
                        if vb and vk:
                            # Replace extension to .gif
                            if "." in vk:
                                base = vk.rsplit(".", 1)[0]
                            else:
                                base = vk
                            gif_key_guess = f"{base}.gif"
                            region = _get_bucket_region(vb)
                            s3 = _get_s3_client(region)
                            try:
                                # Verify object exists before presigning
                                s3.head_object(Bucket=vb, Key=gif_key_guess)
                                url = s3.generate_presigned_url(
                                    "get_object",
                                    Params={
                                        "Bucket": vb,
                                        "Key": gif_key_guess,
                                        "ResponseContentType": "image/gif",
                                    },
                                    ExpiresIn=3600,
                                )
                                it["preview_gif_url"] = url
                            except ClientError:
                                pass

                # Presign video URL for immediate viewing when available
                video_uri2 = it.get("video_uri")
                if isinstance(video_uri2, str) and video_uri2.startswith("s3://"):
                    vb2, vk2 = _parse_s3_uri(video_uri2)
                    if vb2 and vk2:
                        region2 = _get_bucket_region(vb2)
                        s3v = _get_s3_client(region2)
                        try:
                            vurl = s3v.generate_presigned_url(
                                "get_object",
                                Params={
                                    "Bucket": vb2,
                                    "Key": vk2,
                                    "ResponseContentType": "video/mp4",
                                    "ResponseContentDisposition": "inline",
                                },
                                ExpiresIn=3600,
                            )
                            it["video_url"] = vurl
                        except ClientError:
                            pass
            except Exception:
                # Non-fatal; return the item as-is
                pass
            enriched.append(it)

        # Sanitize response: expose only fields needed by clients and a presigned GIF URL
        allowed_keys = {"user_id", "video_id", "status", "title", "duration_s", "created_at", "video_url"}
        sanitized: list[dict] = []
        for it in enriched:
            out = {k: v for k, v in it.items() if k in allowed_keys}
            if "preview_gif_url" in it:
                out["preview_gif_url"] = it["preview_gif_url"]
            sanitized.append(out)

        body = {"user_id": user_id, "items": sanitized}
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


