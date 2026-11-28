"""Sharing one video by link (docs/SHARE_PREVIEWS_2026-11-28.md): the owner opts in per video, and can take the link back at any time.

  POST   /users/{user_id}/videos/{video_id}/share   share it: copy the video and its covers next to a new page under an unguessable token, answer {shared, token, url}
  GET    ...                                        is it shared? {shared, token?, url?}
  DELETE ...                                        stop sharing: the files are deleted and the address is dead (the CDN cache is invalidated)

Runs in the small share stack (backend/share_stack.py), behind its own HTTP API with the same Cognito sign-in as the main API. Only the owner may call it.
The shared copy is a COPY of the finished MP4 and of the cover JPEGs, so the share never needs a signed link to the private bucket and never exposes the owner's folder.
Nothing personal goes on the page: no user id, no email, no video id (share_page.render). A video that is deleted or a person who deletes their account must revoke
its share (`revoke_for_video`, called by the deletion paths; until they are wired the owner's DELETE is the way, see the doc).
"""
import json
import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

import boto3

try:
    from share import share_page
except ImportError:   # bundled flat in the share stack's function
    import share_page  # type: ignore

logger = logging.getLogger()

IMG = "image/jpeg"


def _resp(status: int, body: Dict[str, Any]) -> Dict[str, Any]:
    return {"statusCode": status, "headers": {"Content-Type": "application/json", "Cache-Control": "no-store", "Access-Control-Allow-Origin": "*"},
            "isBase64Encoded": False, "body": json.dumps(body)}


def _sub(event: Dict[str, Any]) -> Optional[str]:
    try:
        claims = (((event.get("requestContext") or {}).get("authorizer") or {}).get("jwt") or {}).get("claims") or {}
        return str(claims.get("sub")) if claims.get("sub") else None
    except Exception:   # noqa: BLE001
        return None


def _env() -> Tuple[str, str, str, str]:
    return os.environ["VIDEOS_TABLE"], os.environ["ASSETS_BUCKET"], os.environ["SHARE_BUCKET"], os.environ["SHARE_HOST"]


def _split(uri: str) -> Tuple[str, str]:
    assert uri.startswith("s3://")
    b, _, k = uri[5:].partition("/")
    return b, k


def _own_uri(uri: Any, user: str, video: str, assets: str) -> Optional[Tuple[str, str]]:
    """Only objects inside THIS video's own folder may be copied: a tampered record cannot make the share a window onto anything else."""
    if not isinstance(uri, str) or not uri.startswith("s3://"):
        return None
    b, k = _split(uri)
    return (b, k) if b == assets and k.startswith(f"videos/{user}/{video}/") and ".." not in k else None


def url_for(host: str, token: str) -> str:
    return f"https://{host}/{token}"


def _invalidate(token: str) -> None:
    dist = os.environ.get("DISTRIBUTION_ID")
    if not dist:
        return
    try:
        boto3.client("cloudfront").create_invalidation(DistributionId=dist, InvalidationBatch={"Paths": {"Quantity": 2, "Items": [f"/{token}", f"/{token}/*"]}, "CallerReference": f"{token}-{time.time_ns()}"})
    except Exception:   # noqa: BLE001 - the objects are already gone; the cache expires on its own (short TTL)
        logger.exception("SHARE_INVALIDATE_FAILED")


def create(user: str, video: str, s3: Any = None, ddb: Any = None) -> Tuple[int, Dict[str, Any]]:
    table_name, assets, share_bucket, host = _env()
    s3 = s3 or boto3.client("s3")
    table = (ddb or boto3.resource("dynamodb")).Table(table_name)
    item = table.get_item(Key={"video_id": video}).get("Item") or {}
    if not item or item.get("user_id") != user:
        return 404, {"code": "not_found"}
    if str(item.get("status") or "").upper() != "COMPLETE":
        return 409, {"code": "not_ready"}
    if item.get("share_token") and share_page.valid_token(item["share_token"]):
        return 200, {"shared": True, "token": item["share_token"], "url": url_for(host, item["share_token"])}   # already shared: same address (idempotent)
    mp4 = _own_uri(item.get("video_uri"), user, video, assets)
    if not mp4:
        return 409, {"code": "not_ready"}
    og = _own_uri(item.get("cover_og_uri"), user, video, assets)
    own = _own_uri(item.get("cover_uri"), user, video, assets)
    token = share_page.new_token()
    # the video first (the biggest), the page last: a visitor never gets a page whose video is missing
    s3.copy_object(Bucket=share_bucket, Key=f"{token}/video.mp4", CopySource={"Bucket": mp4[0], "Key": mp4[1]}, ContentType="video/mp4", MetadataDirective="REPLACE", CacheControl="public, max-age=3600")
    for src, name in ((og, "og.jpg"), (own, "poster.jpg")):
        if src:
            s3.copy_object(Bucket=share_bucket, Key=f"{token}/{name}", CopySource={"Bucket": src[0], "Key": src[1]}, ContentType=IMG, MetadataDirective="REPLACE", CacheControl="public, max-age=3600")
    page = share_page.render(host=host, token=token, title=str(item.get("title") or ""), description=share_page.blurb(item.get("youtube_description")),
                             language=str(item.get("language") or "en")[:2].lower(), aspect=str(item.get("aspect") or "16:9"), has_cover=bool(og), has_poster=bool(own),
                             duration_s=int(item["duration_s"]) if item.get("duration_s") is not None else None)
    s3.put_object(Bucket=share_bucket, Key=f"{token}/index.html", Body=page.encode("utf-8"), ContentType="text/html; charset=utf-8", CacheControl="public, max-age=300")
    table.update_item(Key={"video_id": video}, UpdateExpression="SET share_token = :t, shared_at = :n", ConditionExpression="user_id = :u AND attribute_not_exists(share_token)",
                      ExpressionAttributeValues={":t": token, ":n": int(time.time()), ":u": user})
    return 200, {"shared": True, "token": token, "url": url_for(host, token)}


def _revoke(token: str, share_bucket: str, s3: Any) -> None:
    s3.delete_objects(Bucket=share_bucket, Delete={"Objects": [{"Key": f"{token}/{n}"} for n in share_page.FILES], "Quiet": True})
    _invalidate(token)


def revoke_for_video(user: str, video: str, s3: Any = None, ddb: Any = None) -> bool:
    """Take the link back. True when there was a share."""
    table_name, _a, share_bucket, _h = _env()
    table = (ddb or boto3.resource("dynamodb")).Table(table_name)
    item = table.get_item(Key={"video_id": video}).get("Item") or {}
    token = item.get("share_token")
    if not item or item.get("user_id") != user or not share_page.valid_token(token):
        return False
    _revoke(token, share_bucket, s3 or boto3.client("s3"))
    table.update_item(Key={"video_id": video}, UpdateExpression="REMOVE share_token, shared_at", ConditionExpression="user_id = :u", ExpressionAttributeValues={":u": user})
    return True


def state(user: str, video: str, ddb: Any = None) -> Tuple[int, Dict[str, Any]]:
    table_name, _a, _s, host = _env()
    item = (ddb or boto3.resource("dynamodb")).Table(table_name).get_item(Key={"video_id": video}).get("Item") or {}
    if not item or item.get("user_id") != user:
        return 404, {"code": "not_found"}
    t = item.get("share_token")
    return 200, ({"shared": True, "token": t, "url": url_for(host, t)} if share_page.valid_token(t) else {"shared": False})


def handler(event: Dict[str, Any], context: Any = None) -> Dict[str, Any]:
    pp = event.get("pathParameters") or {}
    user = _sub(event)
    if not user:
        return _resp(401, {"code": "unauthorized"})
    if pp.get("user_id") != user:
        return _resp(403, {"code": "forbidden"})
    video = pp.get("video_id") or ""
    if not video or len(video) > 80 or "/" in video:
        return _resp(400, {"code": "bad_video"})
    method = ((event.get("requestContext") or {}).get("http") or {}).get("method") or event.get("httpMethod") or ""
    try:
        if method == "POST":
            return _resp(*create(user, video))
        if method == "DELETE":
            return _resp(200, {"shared": False, "was_shared": revoke_for_video(user, video)})
        if method == "GET":
            return _resp(*state(user, video))
    except Exception:   # noqa: BLE001
        logger.exception("SHARE_FAILED")
        return _resp(500, {"code": "share_failed"})
    return _resp(405, {"code": "method"})
