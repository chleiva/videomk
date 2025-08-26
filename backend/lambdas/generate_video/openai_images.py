import base64
import json
import logging
import os
from typing import Any, Dict, Optional

import boto3


def _fetch_openai_api_key() -> str:
    """Fetch OpenAI API key from AWS Secrets Manager in us-west-2.

    Expects secret name OPENAI_API_KEY (overridable via OPENAI_API_SECRET_NAME),
    with a JSON object containing {"API_KEY": "..."}. If the secret is a plain
    string, that string is used as the key.
    """
    secret_name = os.environ.get("OPENAI_API_SECRET_NAME", "OPENAI_API_KEY")
    try:
        client = boto3.client("secretsmanager", region_name="us-west-2")
        res = client.get_secret_value(SecretId=secret_name)
        secret_str = res.get("SecretString") or ""
        if not secret_str:
            return ""
        try:
            payload = json.loads(secret_str)
            key = payload.get("API_KEY") or payload.get("openai_api_key")
            return str(key or "")
        except json.JSONDecodeError:
            return secret_str
    except Exception as e:
        logging.exception("Failed to fetch OpenAI API key from Secrets Manager: %s", str(e))
        return ""


def _normalize_size(width: int, height: int) -> str:
    """Map requested width/height to an OpenAI images size string.

    Supports 512x512, 1024x1024, 2048x2048. Defaults to 1024x1024.
    """
    if width >= 2000 or height >= 2000:
        return "2048x2048"
    if width >= 1024 or height >= 1024:
        return "1024x1024"
    return "512x512"


def generate_image_bytes(
    *,
    prompt: str,
    model: Optional[str] = None,
    width: int = 1024,
    height: int = 1024,
    cfg_scale: float = 8.0,  # ignored by OpenAI images API but kept for signature compatibility
    seed: int = 0,  # OpenAI may ignore seed; kept for deterministic intent
) -> bytes:
    """Generate a single image using OpenAI Images API and return raw PNG bytes.

    Parameters mirror the Bedrock variant for drop-in replacement. Only a subset
    is used by OpenAI. The "size" is derived from width/height and coerced to a
    supported square size.
    """
    api_key = _fetch_openai_api_key()
    if not api_key:
        raise RuntimeError("Missing OpenAI API key")

    try:
        # Use official OpenAI SDK if available in the Lambda runtime layer; otherwise fallback to HTTP
        from openai import OpenAI  # type: ignore

        client = OpenAI(api_key=api_key)
        size = _normalize_size(width, height)
        result = client.images.generate(
            model=(model or os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")),
            prompt=prompt,
            size=size,
        )
        image_base64 = result.data[0].b64_json
        return base64.b64decode(image_base64)
    except Exception:
        # Fallback to raw HTTP call for broader compatibility
        import urllib.request

        size = _normalize_size(width, height)
        url = "https://api.openai.com/v1/images/generations"
        body: Dict[str, Any] = {
            "model": (model or os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1")),
            "prompt": prompt,
            "size": size,
        }
        data = json.dumps(body).encode("utf-8")
        req = urllib.request.Request(url, data=data)
        req.add_header("Authorization", f"Bearer {api_key}")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=60) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        images = (payload.get("data") or [])
        if not images:
            raise RuntimeError("OpenAI images API returned no data")
        image_base64 = images[0].get("b64_json")
        if not image_base64:
            raise RuntimeError("OpenAI images API missing b64_json field")
        return base64.b64decode(image_base64)


