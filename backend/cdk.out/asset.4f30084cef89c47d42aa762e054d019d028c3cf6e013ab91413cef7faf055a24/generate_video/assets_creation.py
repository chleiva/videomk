from typing import Any, Dict, List, Optional

import os
import boto3

from .db import update_status
from .bedrock import generate_image_bytes


def _get_assets_bucket() -> str:
    # Fallback to the same bucket name used by render placeholder
    return os.environ.get("ASSETS_BUCKET", "videomk.com")


def _scene_prompt(base_summary: str, scene: Dict[str, Any]) -> str:
    description = str(scene.get("description", "")).strip()
    if base_summary:
        return f"{base_summary}. Scene: {description}"
    return description or "High-quality cinematic still that fits the scene."


def create_assets(video_id: str, plot: Dict[str, Any], table_name: Optional[str] = None) -> Dict[str, Any]:
    # Update status to ASSETS_CREATION (idempotent)
    update_status(video_id, "ASSETS_CREATION", table_name)

    # If plot is not legit, skip image generation and return minimal assets
    if not isinstance(plot, dict) or not plot.get("legit"):
        assets: Dict[str, Any] = {"images": [], "texts": []}
        update_status(
            video_id,
            "STORYBOARD_CREATION",
            table_name,
            extra_attributes={"assets": assets},
        )
        return assets

    s3 = boto3.client("s3")
    bucket = _get_assets_bucket()

    scenes: List[Dict[str, Any]] = plot.get("scenes") or []
    summary: str = str(plot.get("summary", "")).strip()

    images: List[Dict[str, Any]] = []
    texts: List[Dict[str, Any]] = []

    for scene in scenes:
        try:
            scene_id = int(scene.get("id", len(images) + 1))
        except Exception:
            scene_id = len(images) + 1

        prompt = _scene_prompt(summary, scene)

        # Generate a 4K UHD image for each scene
        try:
            img_bytes = generate_image_bytes(
                prompt=prompt,
                width=3840,
                height=2160,
                cfg_scale=8.0,
                seed=0,
            )
            key = f"generation/assets/{video_id}/scene_{scene_id}.png"
            s3.put_object(Bucket=bucket, Key=key, Body=img_bytes, ContentType="image/png")
            images.append({
                "scene_id": scene_id,
                "type": "image",
                "s3": f"s3://{bucket}/{key}",
                "width": 3840,
                "height": 2160,
            })
        except Exception:
            # On any failure, add a placeholder reference so downstream can still proceed
            images.append({
                "scene_id": scene_id,
                "type": "image",
                "s3": f"s3://{bucket}/generation/assets/{video_id}/placeholder_scene_{scene_id}.png",
                "width": 3840,
                "height": 2160,
            })

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
        table_name,
        extra_attributes={"assets": assets},
    )
    return assets


