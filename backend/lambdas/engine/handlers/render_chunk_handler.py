"""Step 4 (fan-out per ~30 s chunk): render the chunk's scenes to a TS segment, unless an identical one is already cached."""
import io
import os
import re
import tempfile
from typing import Any, Dict, Optional

from PIL import Image

from .. import awsio, format_options, pipeline, renderer
from ..timeline import chunk_timeline

_HASH = re.compile(r"^[0-9a-f]{24}$")


def make_image_loader(video_id: str):
    allowed = awsio.prefix(video_id) + "assets/"

    def load(key: str) -> Optional[Image.Image]:
        if not key.startswith(allowed) or ".." in key:  # timeline is data we wrote, but never trust a path
            return None
        return Image.open(io.BytesIO(awsio.get_bytes(key)))

    return load


def make_clip_loader(video_id: str, tmp: str):
    """Stock clips: download the normalised MP4 once per chunk, decode it to frames once."""
    allowed = awsio.prefix(video_id) + "assets/"

    def load(key: str):
        from .. import clips

        if not key.startswith(allowed) or ".." in key or not key.endswith(".mp4"):
            return None
        path = os.path.join(tmp, "clip_" + re.sub(r"[^A-Za-z0-9]", "_", key[len(allowed):]))
        with open(path, "wb") as fh:
            fh.write(awsio.get_bytes(key))
        return clips.ClipFrames(path)

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
    if not draft and format_options.is_4k((tl.get("frame") or {}).get("resolution")):
        renderer.release_caches()   # 4K pictures are 4x the size: a warm function must not carry the last chunk's sprites and photos into this one
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "seg.ts")
        f0 = int(event.get("f0") or 0)   # a piece of a long chunk (4K, timeline.chunk_plan max_frames) starts part-way in; every other chunk at its first frame
        info = pipeline.render_chunk(ct, f0, f0 + int(event["frames"]), out, make_image_loader(video_id), draft=draft, clip_loader=make_clip_loader(video_id, tmp))
        awsio.upload(out, key, "video/mp2t", working=True)
    return {"k": k, "key": key, "cached": False, **info}
