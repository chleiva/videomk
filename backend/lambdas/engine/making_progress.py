"""What the pipeline records for the Making screen (common/making.py shapes it for the apps; docs/CREATE_API.md "Making status").

  plan step      begin(video)            forgets the progress of an earlier attempt ("Try again" reuses the video)
                 common.making.manifest  the planned scenes, stored with the status change (see plan_handler)
  beat step      record_beat(...)        the scene's voice and picture are stored: a small picture of it (when it has one) and its id in the done set
  finalize step  finishing(video)        the scenes are being stitched;  common.making.ATTRS are removed when the video is complete

The thumbnail is the picture the scene already has (the chosen photograph, the first photograph of a gallery or collage, the person's own photo, a slide, or one frame of the
chosen stock clip), reduced to 320 px wide. No model call, no extra render: one S3 read, a resize (or one ffmpeg frame grab) and one S3 write, inside the beat function that
is already running. A scene the engine draws itself (text, chart, diagram) has no picture until it is rendered, so it has no thumbnail.

Nothing here may fail or slow a video: every entry point swallows its own errors, and nothing is written unless the record says the video is being made (an edit of a finished
video runs the same beat function and records nothing).
"""
import io
import logging
import os
from typing import Any, Dict, Optional, Tuple

import boto3
from botocore.exceptions import ClientError
from PIL import Image, ImageOps

from common import making

from . import awsio

THUMB_WIDTH = 320
THUMB_QUALITY = 72
POSTER_AT_S = 0.6            # the frame taken from a stock clip (clips are at least a few seconds long)
MAX_SOURCE_BYTES = 60 * 1024 * 1024   # never pull something huge into memory for a thumbnail


def _table():
    return boto3.resource("dynamodb").Table(os.environ.get("VIDEOS_TABLE", "Videos"))


# ----------------------------------------------------------------------------- the record
def begin(video_id: str) -> None:
    """The plan step starts: an earlier attempt's progress is forgotten, so the counter of this run starts from nothing."""
    try:
        _table().update_item(Key={"video_id": video_id}, UpdateExpression="REMOVE " + ", ".join(f"#a{i}" for i in range(len(making.ATTRS))),
                             ConditionExpression="attribute_exists(video_id)", ExpressionAttributeNames={f"#a{i}": a for i, a in enumerate(making.ATTRS)})
    except Exception:   # noqa: BLE001
        logging.warning("MAKING_BEGIN_FAILED video=%s", video_id)


def plan_attributes(plan: Dict[str, Any]) -> Dict[str, Any]:
    """The attributes the plan step stores together with the status change: the manifest of the planned scenes. {} if it cannot be built (the video is made all the same)."""
    try:
        return {making.ATTR_PLAN: making.manifest(plan)}
    except Exception:   # noqa: BLE001
        logging.warning("MAKING_MANIFEST_FAILED")
        return {}


def is_making(video_id: str) -> bool:
    """Is this video being made right now (and not being edited after it was finished)? One small consistent read."""
    item = _table().get_item(Key={"video_id": video_id}, ProjectionExpression="#s", ExpressionAttributeNames={"#s": "status"}, ConsistentRead=True).get("Item") or {}
    return str(item.get("status") or "") == making.MAKING_STATUS


def mark_done(video_id: str, beat_id: str, has_thumb: bool) -> bool:
    """Adds the scene to the done set (and to the thumbnail set). Sets only grow: a repeated or late call changes nothing, and the count never goes down.
    Only while the video is being made; False when it is not (finished, failed, cancelled, or an edit)."""
    names = {"#s": "status", "#d": making.ATTR_DONE, "#p": making.ATTR_PLAN}
    expr = "ADD #d :b"
    if has_thumb:
        names["#t"] = making.ATTR_THUMBS
        expr += ", #t :b"
    try:
        _table().update_item(Key={"video_id": video_id}, UpdateExpression=expr, ConditionExpression="#s = :making AND attribute_exists(#p)",
                             ExpressionAttributeNames=names, ExpressionAttributeValues={":b": {beat_id}, ":making": making.MAKING_STATUS})
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise


def finishing(video_id: str) -> None:
    """The last step has started (stitching the scenes into the file). Only while the video is being made."""
    try:
        _table().update_item(Key={"video_id": video_id}, UpdateExpression="SET #k = :v", ConditionExpression="#s = :making AND attribute_exists(#p)",
                             ExpressionAttributeNames={"#k": making.ATTR_STEP, "#s": "status", "#p": making.ATTR_PLAN},
                             ExpressionAttributeValues={":v": making.STEP_FINISH, ":making": making.MAKING_STATUS})
    except Exception:   # noqa: BLE001 - includes "not being made": nothing to say
        pass


# ----------------------------------------------------------------------------- the thumbnail
def thumb_source(plan: Dict[str, Any], beat: Dict[str, Any], media: Dict[str, Any], video_id: str) -> Optional[Tuple[str, str]]:
    """(key, "video" | "image") of the picture this scene will show, or None for a scene without one. Only keys inside the video's own assets/ folder are ever used."""
    allowed = awsio.prefix(video_id) + "assets/"
    props = (beat.get("scene") or {}).get("props") or {}
    element = media.get("element") if isinstance(media.get("element"), dict) else {}
    items = {str(m.get("id")): str(m.get("key") or "") for m in plan.get("media_items") or [] if isinstance(m, dict)}
    own = [props.get("photo")] + (props["photos"] if isinstance(props.get("photos"), list) else [])
    element_assets = element.get("assets") if isinstance(element.get("assets"), list) else []
    # in the order a viewer meets them: the scene's photograph, the first of a gallery, an element's picture(s), a slide, the person's own photo
    images = [media.get("asset")] + [g.get("asset") for g in media.get("gallery") or [] if isinstance(g, dict)][:1] + [element.get("asset")] \
        + element_assets[:1] + [props.get("asset")] + [items.get(str(i)) for i in own if i][:1]

    def ok(key: Any) -> bool:
        return isinstance(key, str) and key.startswith(allowed) and ".." not in key

    clip = media.get("clip_asset")
    if ok(clip) and str(clip).endswith(".mp4"):
        return str(clip), "video"
    for key in images:
        if ok(key):
            return str(key), "image"
    return None


def image_thumb(data: bytes, width: int = THUMB_WIDTH) -> bytes:
    """A photograph (or a slide) as a small JPEG: `width` px wide at most, its own shape kept, upright, no metadata."""
    im = Image.open(io.BytesIO(data))
    im.draft("RGB", (width * 2, width * 2))   # a JPEG is decoded at a fraction of its size: a few milliseconds instead of a full decode
    im = ImageOps.exif_transpose(im)
    if im.mode != "RGB":
        im = im.convert("RGB")
    if im.width > width:
        im = im.resize((width, max(1, round(im.height * width / im.width))), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=THUMB_QUALITY, optimize=True)
    return out.getvalue()


def clip_thumb(mp4: bytes, width: int = THUMB_WIDTH) -> Optional[bytes]:
    """One frame of a stock clip as a small JPEG (ffmpeg, already in the function for the clip checks)."""
    from . import clips

    for t in (POSTER_AT_S, 0.0):
        frames = clips.extract_frames(mp4, [t], width=width)
        if frames:
            return image_thumb(frames[0], width)
    return None


def store_thumb(plan: Dict[str, Any], beat: Dict[str, Any], media: Dict[str, Any], video_id: str) -> bool:
    """Stores the scene's small picture next to the video's working files (tagged as working: the bucket deletes it after 7 days). False when the scene has no picture."""
    src = thumb_source(plan, beat, media, video_id)
    key = making.thumb_key(video_id, str(beat.get("id") or ""))
    if not src or not key:
        return False
    head = awsio.head(src[0])
    if not head or int(head.get("ContentLength") or 0) > MAX_SOURCE_BYTES:
        return False
    data = awsio.get_bytes(src[0])
    jpeg = clip_thumb(data) if src[1] == "video" else image_thumb(data)
    if not jpeg:
        return False
    awsio.put_bytes(key, jpeg, "image/jpeg", working=True)
    return True


def record_beat(video_id: str, plan: Dict[str, Any], beat: Dict[str, Any], media: Dict[str, Any]) -> None:
    """Called when a beat's voice and picture are stored. Never raises."""
    try:
        if not is_making(video_id):
            return
        has_thumb = False
        try:
            has_thumb = store_thumb(plan, beat, media, video_id)
        except Exception:   # noqa: BLE001 - the scene still counts as done, it just has no small picture
            logging.warning("MAKING_THUMB_FAILED video=%s beat=%s", video_id, beat.get("id"), exc_info=True)
        mark_done(video_id, str(beat["id"]), has_thumb)
    except Exception:   # noqa: BLE001
        logging.warning("MAKING_RECORD_FAILED video=%s beat=%s", video_id, beat.get("id"), exc_info=True)
