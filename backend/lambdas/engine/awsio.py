import json
import os
from functools import lru_cache
from typing import Any, Dict, Optional

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

_s3 = None


def s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def bucket() -> str:
    return os.environ.get("ASSETS_BUCKET", "videomk.com")


def prefix(video_id: str) -> str:
    """Every v2 artifact of a video lives under this prefix (and nothing else is readable by the engine)."""
    if not video_id or "/" in video_id or ".." in video_id:
        raise ValueError("bad video_id")
    return f"generation/v2/{video_id}/"


def put_json(key: str, obj: Any) -> None:
    s3().put_object(Bucket=bucket(), Key=key, Body=json.dumps(obj).encode("utf-8"), ContentType="application/json")


def get_json(key: str) -> Any:
    return json.loads(s3().get_object(Bucket=bucket(), Key=key)["Body"].read())


def put_bytes(key: str, data: bytes, content_type: str = "application/octet-stream", bkt: Optional[str] = None, *, working: bool = False) -> None:
    """`working=True`: a re-creatable intermediate (the bucket expires it after 7 days), e.g. a stock clip we only keep to render and edit."""
    s3().put_object(Bucket=bkt or bucket(), Key=key, Body=data, ContentType=content_type, **({"Tagging": WORKING_TAG} if working else {}))


def get_bytes(key: str) -> bytes:
    return s3().get_object(Bucket=bucket(), Key=key)["Body"].read()


def download(key: str, path: str) -> None:
    s3().download_file(bucket(), key, path)


WORKING_TAG = "retention=working"  # the bucket's lifecycle rule deletes objects with this tag after 7 days (see backend_stack.py)


def upload(path: str, key: str, content_type: str, bkt: Optional[str] = None, *, working: bool = False) -> None:
    """`working=True` marks a re-creatable intermediate (video segments, audio mixes): the bucket expires it after 7 days.
    Never tag anything an edit cannot rebuild by itself (narration audio, photos, plans, finished videos)."""
    extra = {"ContentType": content_type, **({"Tagging": WORKING_TAG} if working else {})}
    s3().upload_file(path, bkt or bucket(), key, ExtraArgs=extra)


def delete(key: str) -> None:
    s3().delete_object(Bucket=bucket(), Key=key)


def head(key: str) -> Optional[Dict[str, Any]]:
    """Object metadata, or None when it doesn't exist (used for content-addressed cache hits)."""
    try:
        return s3().head_object(Bucket=bucket(), Key=key)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return None
        raise


def put_bytes_meta(key: str, data: bytes, content_type: str, metadata: Dict[str, str]) -> None:
    s3().put_object(Bucket=bucket(), Key=key, Body=data, ContentType=content_type, Metadata=metadata)


@lru_cache(maxsize=4)
def _region_of(bkt: str) -> str:
    try:
        loc = boto3.client("s3", region_name="us-east-1").get_bucket_location(Bucket=bkt).get("LocationConstraint")
        return loc or "us-east-1"
    except Exception:
        return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"


def presign(key: str, bkt: Optional[str] = None, expires: int = 3600) -> str:
    """Time-limited GET URL signed for the bucket's own region (avoids S3 PermanentRedirects)."""
    b = bkt or bucket()
    client = boto3.client("s3", region_name=_region_of(b), config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))
    return client.generate_presigned_url("get_object", Params={"Bucket": b, "Key": key}, ExpiresIn=expires)
