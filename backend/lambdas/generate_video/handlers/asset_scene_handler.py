import hashlib
from typing import Any, Dict

import boto3

from ..openai_images import generate_image_bytes


def _get_assets_bucket() -> str:
    return "videomk.com"


def _scene_prompt(base_summary: str, storytelling: str, scene: Dict[str, Any]) -> str:
    description = str(scene.get("description", "")).strip()
    parts = []
    if description:
        parts.append(f"Scene: {description}")
    if storytelling:
        parts.append(f"Story context: {storytelling}")
    if base_summary:
        parts.append(f"Overall theme: {base_summary}")
    parts.append(
        "Cinematic still, ultra-detailed, realistic textures, dramatic lighting, 4K UHD, no text, no logos"
    )
    return ", ".join([p for p in parts if p])


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    s3 = boto3.client("s3")
    bucket = _get_assets_bucket()

    video_id = str(event.get("video_id", ""))
    plot = event.get("plot") or {}
    scene = event.get("scene") or {}

    summary: str = str(plot.get("summary", "")).strip()
    storytelling: str = str(plot.get("storytelling", "")).strip()

    try:
        scene_id = int(scene.get("id", 1))
    except Exception:
        scene_id = 1

    prompt = _scene_prompt(summary, storytelling, scene)

    # Deterministic seed per video/scene
    seed_input = f"{video_id}:{scene_id}:{summary}:{storytelling}".encode("utf-8")
    raw_seed = int.from_bytes(hashlib.md5(seed_input).digest()[:4], byteorder="big", signed=False)
    seed = raw_seed % 2147483646 or 1

    img_bytes = generate_image_bytes(
        prompt=prompt,
        width=1024,
        height=1024,
        cfg_scale=8.0,
        seed=seed,
    )
    key = f"generation/assets/{video_id}/scene_{scene_id}.png"
    s3.put_object(Bucket=bucket, Key=key, Body=img_bytes, ContentType="image/png")

    # Text overlay suggestion from scene description
    text_item = {
        "scene_id": scene_id,
        "type": "text",
        "content": str(scene.get("description", "")),
    }

    image_item = {
        "scene_id": scene_id,
        "type": "image",
        "s3": f"s3://{bucket}/{key}",
        "width": 1024,
        "height": 1024,
    }

    return {
        "video_id": video_id,
        "scene_id": scene_id,
        "image": image_item,
        "text": text_item,
    }


