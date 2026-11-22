"""Step 4 (fan-out per ~30 s chunk): render a frame range to a TS segment."""
import io
import os
import tempfile
from typing import Any, Dict, Optional

from PIL import Image

from .. import awsio, pipeline


def make_image_loader(video_id: str):
    allowed = awsio.prefix(video_id) + "assets/"

    def load(key: str) -> Optional[Image.Image]:
        if not key.startswith(allowed) or ".." in key:  # timeline is data we wrote, but never trust a path
            return None
        return Image.open(io.BytesIO(awsio.get_bytes(key)))

    return load


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    video_id, k = str(event["video_id"]), int(event["k"])
    tl = awsio.get_json(event["timeline_key"])
    key = f"{awsio.prefix(video_id)}segments/seg_{k:03d}.ts"
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "seg.ts")
        info = pipeline.render_chunk(tl, int(event["f0"]), int(event["f1"]), out, make_image_loader(video_id), draft=bool(event.get("draft")))
        awsio.upload(out, key, "video/mp2t")
    return {"k": k, "key": key, **info}
