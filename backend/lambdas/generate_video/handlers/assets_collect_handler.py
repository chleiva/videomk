from typing import Any, Dict, List

from ..db import update_status


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    video_id = str(event.get("video_id", ""))
    results: List[Dict[str, Any]] = event.get("assetResults") or []

    images: List[Dict[str, Any]] = []
    texts: List[Dict[str, Any]] = []
    for r in results:
        img = r.get("image")
        txt = r.get("text")
        if isinstance(img, dict) and img.get("s3"):
            images.append(img)
        if isinstance(txt, dict):
            texts.append(txt)

    assets: Dict[str, Any] = {"images": images, "texts": texts}
    update_status(video_id, "STORYBOARD_CREATION", extra_attributes={"assets": assets})

    out = dict(event)
    out["assets"] = assets
    return out


