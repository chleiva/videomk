"""Step 4 (fan-out per ~30 s chunk): render the chunk's scenes to a TS segment, unless an identical one is already cached."""
import io
import os
import re
import tempfile
import time
from typing import Any, Dict, Optional

from PIL import Image

import logging

from .. import awsio, cover, format_options, pipeline, renderer
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


def ensure_cover(video_id: str, tl: Dict[str, Any]) -> Optional[Dict[str, str]]:
    """The video's cover pictures (engine/cover.py), made here because this function already has the loaders and the catalog access the first scene needs. Named by content, so an
    edit that does not change the opening finds them. Never raises: a video without a cover is still a video (finalize copies them when they are there)."""
    try:
        ks = cover.keys(awsio.prefix(video_id), tl)
        if awsio.head(ks["og_key"]) and awsio.head(ks["own_key"]):
            return ks
        with tempfile.TemporaryDirectory() as tmp:
            out = cover.build(tl, make_image_loader(video_id), make_clip_loader(video_id, tmp))
        awsio.put_bytes(ks["own_key"], out["own"], "image/jpeg")
        awsio.put_bytes(ks["og_key"], out["og"], "image/jpeg")   # last: its presence says both are there
        return ks
    except Exception:   # noqa: BLE001
        logging.exception("COVER_FAILED video=%s", video_id)
        return None


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    t_start = time.time()
    video_id, k = str(event["video_id"]), int(event["k"])
    draft = bool(event.get("draft"))
    key = segment_key(video_id, str(event["hash"]), draft)
    first = int(event.get("lo") or 0) == 0 and int(event.get("f0") or 0) == 0 and not draft   # the chunk that opens the video makes its cover
    if awsio.head(key):  # same scenes, same look => reuse the segment, whatever its position in the video
        res = {"k": k, "key": key, "cached": True}
        if first:
            ck = ensure_cover(video_id, awsio.get_json(event["timeline_key"]))
            if ck:
                res["cover"] = ck
        return res
    tl = awsio.get_json(event["timeline_key"])
    ct = chunk_timeline(tl, int(event["lo"]), int(event["hi"]))
    if not draft and format_options.is_4k((tl.get("frame") or {}).get("resolution")):
        renderer.release_caches()   # 4K pictures are 4x the size: a warm function must not carry the last chunk's sprites and photos into this one
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "seg.ts")
        f0 = int(event.get("f0") or 0)   # a piece of a long chunk (4K, timeline.chunk_plan max_frames) starts part-way in; every other chunk at its first frame
        info = pipeline.render_chunk(ct, f0, f0 + int(event["frames"]), out, make_image_loader(video_id), draft=draft, clip_loader=make_clip_loader(video_id, tmp))
        awsio.upload(out, key, "video/mp2t", working=True)
    # GB-seconds this chunk will be billed for (wall time x the function's memory): the finalize step adds them up into the video's `c_render` (costs.render_cost)
    gbs = round((time.time() - t_start) * float(getattr(context, "memory_limit_in_mb", 0) or 0) / 1024.0, 2)
    res = {"k": k, "key": key, "cached": False, **info, **({"gbs": gbs} if gbs > 0 else {})}
    if first:
        ck = ensure_cover(video_id, tl)
        if ck:
            res["cover"] = ck
    return res
