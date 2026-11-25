"""Turns an uploaded photo into a library photo: checks it, makes the thumbnail, embeds it, stores the vector, marks it ready. SQS-triggered (S3 -> SQS -> here)."""
import hashlib
import io
import json
import logging
import os
from typing import Any, Dict, Optional

from botocore.exceptions import ClientError
from PIL import Image, ImageOps

from common import library as lib
from common import library_search as search

logger = logging.getLogger()
Image.MAX_IMAGE_PIXELS = 64_000_000
FINAL_ATTEMPT = int(os.environ.get("INGEST_FINAL_ATTEMPT", "4"))   # from this receive count on, a photo is kept even if it could not be embedded


class Retry(Exception):
    """A transient problem (throttling, storage): leave the message for another attempt."""


def process(user: str, mid: str, *, attempt: int = 1) -> str:
    """Returns "ready", "skipped" or "rejected". Raises Retry for transient trouble."""
    item = lib.get_item(user, mid, ready_only=False)
    if not item:   # a file nobody asked for (no pending row): remove it
        for k in (lib.orig_key(user, mid), lib.thumb_key(user, mid)):
            lib.s3().delete_object(Bucket=lib.bucket(), Key=k)
        return "rejected"
    if item.get("st") != "pending":
        return "skipped"   # the same event twice
    try:
        obj = lib.s3().get_object(Bucket=lib.bucket(), Key=lib.orig_key(user, mid))
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return "skipped"   # the event came before the object is visible, or it was never completed: the sweeper decides
        raise Retry() from e
    if int(obj.get("ContentLength", 0)) > int(item["size_b"]):
        lib.reject(user, mid)
        return "rejected"
    data = obj["Body"].read()
    if hashlib.sha256(data).hexdigest() != item.get("hash"):
        lib.reject(user, mid)
        return "rejected"
    try:
        im = Image.open(io.BytesIO(data))
        if im.format != "JPEG" or im.width < 1 or im.height < 1 or im.width * im.height > Image.MAX_IMAGE_PIXELS:
            raise ValueError("not an acceptable JPEG")
        w, h = im.size
        im.load()
        im = ImageOps.exif_transpose(im).convert("RGB")
    except Exception:
        lib.reject(user, mid)
        return "rejected"
    thumb = im.copy()
    thumb.thumbnail((lib.THUMB_PX, lib.THUMB_PX))
    tb = io.BytesIO()
    thumb.save(tb, "JPEG", quality=78, optimize=True)   # no metadata is carried over
    lib.s3().put_object(Bucket=lib.bucket(), Key=lib.thumb_key(user, mid), Body=tb.getvalue(), ContentType="image/jpeg",
                        CacheControl="private, max-age=31536000, immutable")
    embedded = True
    try:
        small = im.copy()
        small.thumbnail((search.EMBED_IMAGE_PX, search.EMBED_IMAGE_PX))
        sb = io.BytesIO()
        small.save(sb, "JPEG", quality=80)
        vec = search.embed_image(sb.getvalue())
        lib.vectors().put_vectors(**lib.vector_target(), vectors=[{"key": lib.vec_key(user, mid), "data": {"float32": vec}, "metadata": search.vector_metadata(user, item)}])
    except Exception as e:
        if attempt < FINAL_ATTEMPT:
            raise Retry() from e
        embedded = False
        logger.error("photo kept without a vector after %s attempts (%s)", attempt, type(e).__name__)
    try:
        lib.finalize(user, mid, actual_bytes=len(data), w=w, h=h)
    except lib.Busy as e:   # other photos of this person are finishing at the same moment: try again shortly
        raise Retry() from e
    if not embedded:
        lib.table().update_item(Key={"user_id": user, "sk": f"m#{mid}"}, UpdateExpression="SET nov = :t", ExpressionAttributeValues={":t": True})
    return "ready"


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    failures = []
    for rec in event.get("Records", []):
        try:
            attempt = int((rec.get("attributes") or {}).get("ApproximateReceiveCount", "1"))
            for r in json.loads(rec["body"]).get("Records", []):   # an S3 event notification (a test event has no Records)
                key = (((r.get("s3") or {}).get("object") or {}).get("key") or "")
                from urllib.parse import unquote_plus

                m = lib.ORIG_RE.match(unquote_plus(key))
                if not m:
                    logger.warning("ignored an object outside the library layout")
                    continue
                process(m.group(1), m.group(2), attempt=attempt)
        except Retry:
            failures.append({"itemIdentifier": rec["messageId"]})
        except Exception:
            logger.exception("ingest failed")
            failures.append({"itemIdentifier": rec["messageId"]})
    return {"batchItemFailures": failures}
