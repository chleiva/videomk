import json
import os
from typing import Any, Optional

import boto3

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


def put_bytes(key: str, data: bytes, content_type: str = "application/octet-stream", bkt: Optional[str] = None) -> None:
    s3().put_object(Bucket=bkt or bucket(), Key=key, Body=data, ContentType=content_type)


def get_bytes(key: str) -> bytes:
    return s3().get_object(Bucket=bucket(), Key=key)["Body"].read()


def download(key: str, path: str) -> None:
    s3().download_file(bucket(), key, path)


def upload(path: str, key: str, content_type: str, bkt: Optional[str] = None) -> None:
    s3().upload_file(path, bkt or bucket(), key, ExtraArgs={"ContentType": content_type})
