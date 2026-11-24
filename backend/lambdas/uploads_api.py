"""POST /users/{user_id}/uploads  {count: 1..10}  ->  one presigned POST per photo.

The app uploads each photo straight to S3 under uploads/<user>/<id>.jpg. The presigned POST fixes the key, the content type and a size range, so a
user can only write small JPEGs into their own folder; nothing else about the upload is trusted (the engine re-reads and re-encodes every photo).
"""
import logging
import os
import uuid
from typing import Any, Dict

import boto3
from botocore.config import Config

from common import usage
from common.http import json_response
from common.identity import extract_cognito_sub
from common.photo_ids import MAX_PHOTOS, MAX_UPLOAD_BYTES, upload_key

logger = logging.getLogger()
DAILY_PHOTOS = int(os.environ.get("UPLOAD_PHOTOS_PER_DAY", "600"))
EXPIRES = 900


def _s3():
    return boto3.client("s3", region_name=os.environ.get("AWS_REGION") or "us-east-1", config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    path_user = ((event or {}).get("pathParameters") or {}).get("user_id")
    user = extract_cognito_sub(event)
    if not user:
        return json_response(401, {"message": "Unauthorized"})
    if not path_user or path_user != user:
        return json_response(403, {"message": "Forbidden"})
    import json

    try:
        body = json.loads(event.get("body") or "{}")
        count = body.get("count")
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= MAX_PHOTOS:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        return json_response(400, {"message": f"'count' must be a whole number from 1 to {MAX_PHOTOS}"})
    try:
        for _ in range(count):
            usage.consume(f"upload:{user}", limit=DAILY_PHOTOS)
    except usage.QuotaExceeded:
        return json_response(429, {"message": "Too many photos uploaded today. Try again tomorrow."}, {"Retry-After": "3600"})
    bucket, s3, slots = os.environ["ASSETS_BUCKET"], _s3(), []
    for _ in range(count):
        mid = uuid.uuid4().hex[:16]
        post = s3.generate_presigned_post(Bucket=bucket, Key=upload_key(user, mid), Fields={"Content-Type": "image/jpeg"},
                                          Conditions=[{"Content-Type": "image/jpeg"}, ["content-length-range", 1, MAX_UPLOAD_BYTES]], ExpiresIn=EXPIRES)
        slots.append({"id": mid, "url": post["url"], "fields": post["fields"]})
    return json_response(200, {"uploads": slots, "max_bytes": MAX_UPLOAD_BYTES, "expires_in": EXPIRES})
