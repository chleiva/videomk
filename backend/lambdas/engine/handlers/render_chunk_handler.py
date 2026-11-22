"""Step 4 (fan-out per ~30 s chunk): render the chunk's scenes to a TS segment, unless an identical one is already cached."""
import io
import os
import re
import tempfile
from typing import Any, Dict, Optional

from PIL import Image

from .. import awsio, pipeline
from ..timeline import chunk_timeline

_HASH = re.compile(r"^[0-9a-f]{24}$")


def make_image_loader(video_id: str):
    allowed = awsio.prefix(video_id) + "assets/"

    def load(key: str) -> Optional[Image.Image]:
        if not key.startswith(allowed) or ".." in key:  # timeline is data we wrote, but never trust a path
            return None
        return Image.open(io.BytesIO(awsio.get_bytes(key)))

    return load


def segment_key(video_id: str, h: str, draft: bool) -> str:
    if not _HASH.match(h):
        raise ValueError("bad chunk hash")
    return f"{awsio.prefix(video_id)}segments/{'d' if draft else 'f'}_{h}.ts"


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    video_id, k = str(event["video_id"]), int(event["k"])
    draft = bool(event.get("draft"))
    key = segment_key(video_id, str(event["hash"]), draft)
    if awsio.head(key):  # same scenes, same look => reuse the segment, whatever its position in the video
        return {"k": k, "key": key, "cached": True}
    tl = awsio.get_json(event["timeline_key"])
    ct = chunk_timeline(tl, int(event["lo"]), int(event["hi"]))
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "seg.ts")
        info = pipeline.render_chunk(ct, 0, int(event["frames"]), out, make_image_loader(video_id), draft=draft)
        awsio.upload(out, key, "video/mp2t")
    return {"k": k, "key": key, "cached": False, **info}
