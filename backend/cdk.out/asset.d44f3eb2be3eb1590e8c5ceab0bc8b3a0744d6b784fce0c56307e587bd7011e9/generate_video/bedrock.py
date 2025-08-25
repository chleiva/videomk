import json
from typing import Any, Dict, List, Optional, Tuple

import boto3


_bedrock = boto3.client("bedrock-runtime")



def invoke_anthropic(
    messages: List[Dict[str, Any]],
    *,
    model_id: str = "anthropic.claude-3-haiku-20240307-v1:0",
    max_tokens: int = 12000,
    temperature: float = 0.7,
    system: Optional[str] = None,
) -> Dict[str, Any]:
    """Invoke Anthropic Claude 3 on Bedrock with Bedrock's message schema.

    - Adds required anthropic_version
    - Moves any 'system' role content to top-level 'system'
    - Ensures message.content is an array of {type: "text", text: "..."}
    """
    system_prompts: List[str] = []
    if isinstance(system, str) and system.strip():
        system_prompts.append(system)

    formatted_messages: List[Dict[str, Any]] = []
    for msg in messages or []:
        role = str(msg.get("role", "")).strip()
        content = msg.get("content")
        if role.lower() == "system":
            if isinstance(content, str) and content.strip():
                system_prompts.append(content)
            elif isinstance(content, list):
                # Attempt to concatenate text parts if provided as rich content
                texts = []
                for part in content:
                    if isinstance(part, dict) and part.get("type") == "text" and isinstance(part.get("text"), str):
                        texts.append(part["text"])
                if texts:
                    system_prompts.append("\n\n".join(texts))
            continue  # do not include 'system' in messages array

        if role not in ("user", "assistant"):
            # Skip unknown roles to satisfy Bedrock schema
            continue

        # Normalize content to array of text blocks
        if isinstance(content, str):
            content_blocks = [{"type": "text", "text": content}]
        elif isinstance(content, list):
            content_blocks = content  # assume already in Bedrock format
        else:
            content_blocks = [{"type": "text", "text": str(content)}]

        formatted_messages.append({"role": role, "content": content_blocks})

    body: Dict[str, Any] = {
        "anthropic_version": "bedrock-2023-05-31",
        "messages": formatted_messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if system_prompts:
        # Bedrock Claude accepts string or array; use a single concatenated string
        body["system"] = "\n\n".join(system_prompts)

    res = _bedrock.invoke_model(modelId=model_id, body=json.dumps(body))
    return json.loads(res["body"].read())


def response_text(response: Dict[str, Any]) -> str:
    """Extract primary text from a Bedrock Anthropic response."""
    content = response.get("content")
    if isinstance(content, list) and content:
        first = content[0]
        if isinstance(first, dict) and "text" in first:
            return str(first["text"])
    # Some variants may include different fields; fallback to stringifying
    return json.dumps(response)



def generate_image_bytes(
    *,
    prompt: str,
    model_id: str = "amazon.nova-canvas-v1:0",
    width: int = 3840,
    height: int = 2160,
    cfg_scale: float = 8.0,
    seed: int = 0,
) -> bytes:
    """Generate a single image using Amazon Nova Canvas and return raw bytes.

    Parameters
    ----------
    prompt: Text prompt for the image.
    model_id: Bedrock model identifier. Default: amazon.nova-canvas-v1:0
    width: Output image width in pixels. Default: 3840
    height: Output image height in pixels. Default: 2160
    cfg_scale: Guidance scale. Default: 8.0
    seed: Random seed for reproducibility. Default: 0
    """
    body: Dict[str, Any] = {
        "taskType": "TEXT_IMAGE",
        "textToImageParams": {
            "text": prompt,
        },
        "imageGenerationConfig": {
            "numberOfImages": 1,
            "height": int(height),
            "width": int(width),
            "cfgScale": float(cfg_scale),
            "seed": int(seed),
        },
    }

    response = _bedrock.invoke_model(
        body=json.dumps(body),
        modelId=model_id,
        accept="application/json",
        contentType="application/json",
    )

    payload = json.loads(response.get("body").read())
    # Expecting { images: [base64, ...], error?: ... }
    error = payload.get("error")
    if error is not None:
        # Normalize error to string
        raise RuntimeError(f"Image generation error from {model_id}: {error}")

    images = payload.get("images") or []
    if not images or not isinstance(images, list) or not images[0]:
        raise RuntimeError("Image generation returned no images")

    # Bedrock returns base64 (no data URL prefix) for each image
    import base64

    base64_image: str = images[0]
    return base64.b64decode(base64_image.encode("ascii"))


