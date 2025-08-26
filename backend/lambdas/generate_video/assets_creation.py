from typing import Any, Dict, List, Optional

import os
import hashlib
import logging
import boto3

from .db import update_status
from .openai_images import generate_image_bytes


def _get_assets_bucket() -> str:
    # Fallback to the same bucket name used by render placeholder
    return os.environ.get("ASSETS_BUCKET", "videomk.com")


def _scene_prompt(base_summary: str, storytelling: str, scene: Dict[str, Any]) -> str:
    description = str(scene.get("description", "")).strip()
    # Build a richer, cinematic image prompt leveraging the storytelling context
    parts: List[str] = []
    if description:
        parts.append(f"Scene: {description}")
    if storytelling:
        parts.append(f"Story context: {storytelling}")
    if base_summary:
        parts.append(f"Overall theme: {base_summary}")

    # Cinematic styling and guidance to avoid text artifacts
    parts.append(
        "Cinematic still, ultra-detailed, realistic textures, dramatic lighting, volumetric light, "
        "soft natural light, depth of field, soft bokeh, rich textures, high dynamic range, filmic color grading, "
        "subtle film grain, 4K UHD, compositionally strong, rule of thirds, no text, no logos, no watermark"
    )

    prompt = ", ".join([p for p in parts if p])
    return prompt or "Cinematic still, evocative, ultra-detailed, dramatic lighting, 4K UHD, no text"


def create_assets(video_id: str, plot: Dict[str, Any], table_name: Optional[str] = None) -> Dict[str, Any]:
    # Update status to ASSETS_CREATION (idempotent)
    update_status(video_id, "ASSETS_CREATION", table_name or "Videos")

    # If plot is not legit, skip image generation and return minimal assets
    if not isinstance(plot, dict) or not plot.get("legit"):
        assets: Dict[str, Any] = {"images": [], "texts": []}
        update_status(
            video_id,
            "STORYBOARD_CREATION",
            table_name or "Videos",
            extra_attributes={"assets": assets},
        )
        return assets

    s3 = boto3.client("s3")
    bucket = _get_assets_bucket()

    scenes: List[Dict[str, Any]] = plot.get("scenes") or []
    summary: str = str(plot.get("summary", "")).strip()
    storytelling: str = str(plot.get("storytelling", "")).strip()

    images: List[Dict[str, Any]] = []
    texts: List[Dict[str, Any]] = []

    for scene in scenes:
        try:
            scene_id = int(scene.get("id", len(images) + 1))
        except Exception:
            scene_id = len(images) + 1

        prompt = _scene_prompt(summary, storytelling, scene)

        # Generate an image for each scene
        try:
            # Derive a deterministic seed from video, scene, and narrative context for uniqueness
            seed_input = f"{video_id}:{scene_id}:{summary}:{storytelling}".encode("utf-8")
            raw_seed = int.from_bytes(hashlib.md5(seed_input).digest()[:4], byteorder="big", signed=False)
            # Keep seed within 32-bit signed range for portability (even if OpenAI ignores it)
            seed = raw_seed % 2147483646
            if seed == 0:
                seed = 1
            img_bytes = generate_image_bytes(
                prompt=prompt,
                width=1024,
                height=1024,
                cfg_scale=8.0,
                seed=seed,
            )
            key = f"generation/assets/{video_id}/scene_{scene_id}.png"
            s3.put_object(Bucket=bucket, Key=key, Body=img_bytes, ContentType="image/png")
            images.append({
                "scene_id": scene_id,
                "type": "image",
                "s3": f"s3://{bucket}/{key}",
                "width": 1024,
                "height": 1024,
            })
        except Exception as e:
            logging.exception(
                "Failed to generate/upload scene image for video_id=%s scene_id=%s: %s",
                video_id,
                scene_id,
                str(e),
            )

        # Provide a text overlay candidate per scene
        texts.append({
            "scene_id": scene_id,
            "type": "text",
            "content": scene.get("description", ""),
        })

    assets: Dict[str, Any] = {"images": images, "texts": texts}

    update_status(
        video_id,
        "STORYBOARD_CREATION",
        table_name or "Videos",
        extra_attributes={"assets": assets},
    )
    return assets


