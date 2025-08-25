from typing import Any, Dict, List, Optional
import os
import json
import logging
import boto3
from botocore.exceptions import ClientError
from decimal import Decimal
import re

from .db import update_status


DEFAULT_MUSIC_S3 = os.environ.get(
    "DEFAULT_MUSIC_S3", "s3://videomk.com/generation/assets/static/basic.wav"
)


def _get_table(table_name: Optional[str] = None):
    name = table_name or os.environ.get("VIDEOS_TABLE", "")
    if not name:
        raise RuntimeError("VIDEOS_TABLE environment variable is not set")
    return boto3.resource("dynamodb").Table(name)


def _get_video_item(video_id: str, table_name: Optional[str] = None) -> Dict[str, Any]:
    table = _get_table(table_name)
    try:
        resp = table.get_item(Key={"video_id": video_id})
        return (resp.get("Item") or {})
    except ClientError as e:
        logging.exception("Failed to get video item for video_id=%s: %s", video_id, str(e))
        return {}


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
            # SecretString was a plain API key
            return secret_str
    except Exception as e:
        logging.exception("Failed to fetch OpenAI API key from Secrets Manager: %s", str(e))
        return ""


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        try:
            as_int = int(value)
            if value == as_int:
                return as_int
        except Exception:
            pass
        try:
            return float(value)
        except Exception:
            return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in list(value)]
    return value


def _to_dynamodb_compatible(value: Any) -> Any:
    """Recursively convert floats to Decimal for DynamoDB."""
    if isinstance(value, float):
        # Preserve precision by converting via string
        return Decimal(str(value))
    if isinstance(value, dict):
        return {str(k): _to_dynamodb_compatible(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_dynamodb_compatible(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_to_dynamodb_compatible(v) for v in value)
    return value


def _call_openai_storyboard(api_key: str, context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not api_key:
        return None

    import urllib.request

    req = urllib.request.Request("https://api.openai.com/v1/chat/completions")
    req.add_header("Authorization", f"Bearer {api_key}")
    req.add_header("Content-Type", "application/json")

    system = (
        "You are a video storyboard generator. Return compact JSON only with fields: "
        "output, audio, narration, scenes, transitions. Use user's assets (S3 URIs) when provided. "
        "Use the provided storytelling text to guide the flow and insert succinct captions across scenes. "
        "Break the storytelling into short 6-15 word snippets mapped to scenes in order. "
        "Place captions as overlay.text near the bottom (y≈0.85) with a semi-transparent box for readability. "
        "No markdown, no explanations."
    )

    plot = context.get("plot") or {}
    assets = context.get("assets") or {}

    summary = str(plot.get("summary", ""))
    storytelling = str(plot.get("storytelling", ""))
    scenes = plot.get("scenes") or []
    images = assets.get("images") or []
    texts = assets.get("texts") or []

    def _brief_images(imgs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        brief: List[Dict[str, Any]] = []
        for img in imgs[:10]:
            brief.append({k: img.get(k) for k in ("scene_id", "s3", "width", "height")})
        return brief

    contract = {
        "output": ["filename", "width", "height", "fps", "crf", "audio_bitrate"],
        "audio": ["music", "music_volume"],
        "narration": ["tts_engine"],
        "scene.background": ["type", "path?", "value?", "fit?", "effects?"],
        "overlay.text": ["type", "text", "fontsize", "color", "align", "y", "effects?", "box?"],
    }

    context_payload = {
        'video_id': context.get('video_id', ''),
        'summary': summary,
        'storytelling': storytelling,
        'scenes': scenes,
        'assets': {'images': _brief_images(images), 'texts': texts[:10]},
        'requirements': {
            'defaults': {'width': 1920, 'height': 1080, 'fps': 30, 'crf': 18, 'audio_bitrate': '192k'},
            'narration': {'tts_engine': 'none'},
            'transitions_default': 'none',
            'audio': {'music': DEFAULT_MUSIC_S3, 'music_volume': 0.12},
        },
        'format_contract': contract,
    }
    user = (
        "Using this context, produce a 10–40 second storyboard. "
        "Use available scene durations; if missing, keep 2–4 seconds per scene. "
        "Reference provided S3 image URIs in scene backgrounds via path field. "
        "Distribute the storytelling text into concise captions across scenes in order; if longer than scenes, truncate; "
        "if shorter, leave some scenes without caption. Place captions as overlay.text near bottom with a readable box. "
        "Return ONLY JSON. "
        f"Context: {json.dumps(_json_safe(context_payload), separators=(',', ':'))}"
    )

    body = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-5"),
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.2,
        "max_tokens": 1200,
    }

    try:
        data = json.dumps(body).encode("utf-8")

        # Debug: log request details (mask API key)
        try:
            auth = req.get_header("Authorization") or ""
            masked = auth[:20] + "…" if auth else ""
            logging.info(
                "OpenAI request: url=%s model=%s temp=%s max_tokens=%s headers={Authorization:%s, Content-Type:%s} payload=%s",
                req.full_url,
                body.get("model"),
                body.get("temperature"),
                body.get("max_tokens"),
                masked,
                req.get_header("Content-Type"),
                json.dumps(body, ensure_ascii=False, separators=(",", ":")),
            )
        except Exception:
            pass

        with urllib.request.urlopen(req, data=data, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        choices = payload.get("choices") or []
        text = ""
        if choices:
            message = choices[0].get("message") or {}
            text = message.get("content") or ""
        if not text:
            return None
        return json.loads(text)
    except Exception as e:
        # Try to include response body for HTTP errors to aid debugging
        try:
            import urllib.error
            if isinstance(e, urllib.error.HTTPError):
                err_body = e.read().decode("utf-8", "ignore")
                err_headers = {k: v for k, v in (e.headers.items() if e.headers else [])}
                logging.exception(
                    "OpenAI call failed: code=%s reason=%s url=%s body=%s headers=%s",
                    getattr(e, "code", None),
                    getattr(e, "reason", None),
                    getattr(e, "url", None),
                    err_body,
                    json.dumps(err_headers),
                )
            else:
                logging.exception("OpenAI call failed: %s", str(e))
        except Exception:
            logging.exception("OpenAI call failed: %s", str(e))
        return None


def _fallback_storyboard(video_id: str, plot: Dict[str, Any], assets: Dict[str, Any]) -> Dict[str, Any]:
    width = 1920
    height = 1080

    plot_scenes = plot.get("scenes") or []
    storytelling_text = str(plot.get("storytelling", "")).strip()
    # Split storytelling into short phrases (~6-15 words) to map to scenes
    def _split_story(text: str, parts: int) -> List[str]:
        if not text:
            return []
        # Basic split by sentence boundaries, then further chunk by words
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks: List[str] = []
        for s in sentences:
            words = s.strip().split()
            chunk: List[str] = []
            for w in words:
                chunk.append(w)
                if len(chunk) >= 12:
                    chunks.append(" ".join(chunk))
                    chunk = []
            if chunk:
                chunks.append(" ".join(chunk))
        # If still too many chunks, trim to number of scenes
        return chunks[:max(0, parts)]
    image_by_scene = {img.get("scene_id"): img for img in (assets.get("images") or [])}
    text_by_scene: Dict[Any, Dict[str, Any]] = {}
    for t in (assets.get("texts") or []):
        text_by_scene.setdefault(t.get("scene_id"), t)

    scenes_out: List[Dict[str, Any]] = []
    captions = _split_story(storytelling_text, len(plot_scenes))
    for idx, scene in enumerate(plot_scenes):
        try:
            duration = int(scene.get("duration_s", 3) or 3)
        except Exception:
            duration = 3
        img = image_by_scene.get(scene.get("id"))
        txt = text_by_scene.get(scene.get("id"))
        background: Dict[str, Any] = {"type": "color", "value": [20, 20, 30]}
        if img and img.get("s3"):
            background = {"type": "image", "path": img.get("s3"), "fit": "cover"}
        overlays: List[Dict[str, Any]] = []
        if txt and txt.get("content"):
            overlays.append(
                {
                    "type": "text",
                    "text": txt.get("content"),
                    "fontsize": 40,
                    "color": "white",
                    "align": "center",
                    "y": 0.85,
                    "effects": ["fadein:0.3"],
                    "box": {"width": 0.8, "padding": 18, "radius": 10, "fill": [0, 0, 0, 220]},
                }
            )
        # Add storytelling caption if available for this scene index
        if idx < len(captions) and captions[idx]:
            overlays.append(
                {
                    "type": "caption",
                    "text": captions[idx],
                    "fontsize": 38,
                    "color": "white",
                    "align": "center",
                    "y": 0.88,
                    "effects": ["fadein:0.4"],
                    "box": {"width": 0.9, "padding": 20, "radius": 12, "fill": [0, 0, 0, 210]},
                }
            )
        scenes_out.append(
            {
                "duration": max(1, min(duration, 30)),
                "background": background,
                "overlays": overlays,
            }
        )

    if not scenes_out:
        scenes_out.append(
            {
                "duration": 3,
                "background": {"type": "color", "value": [20, 20, 30]},
                "overlays": [
                    {
                        "type": "text",
                        "text": "Demo",
                        "fontsize": 64,
                        "color": "white",
                        "align": "center",
                        "y": 0.5,
                    }
                ],
            }
        )

    return {
        "output": {
            "filename": f"{video_id}.mp4",
            "width": width,
            "height": height,
            "fps": 30,
            "crf": 18,
            "audio_bitrate": "192k",
        },
        "audio": {"music": DEFAULT_MUSIC_S3, "music_volume": 0.12},
        "narration": {"tts_engine": "none"},
        "scenes": scenes_out,
        "transitions": {"default": "none"},
    }


def _validate_storyboard(storyboard: Dict[str, Any]) -> bool:
    try:
        if not isinstance(storyboard, dict):
            return False
        if not storyboard.get("scenes"):
            return False
        out = storyboard.get("output") or {}
        if not isinstance(out, dict) or not out.get("filename"):
            return False
        return True
    except Exception:
        return False


def _apply_default_music(storyboard: Dict[str, Any]) -> Dict[str, Any]:
    try:
        audio = storyboard.get("audio") or {}
        if not isinstance(audio, dict):
            audio = {}
        if not audio.get("music"):
            audio["music"] = DEFAULT_MUSIC_S3
        if "music_volume" not in audio:
            audio["music_volume"] = 0.12
        storyboard["audio"] = audio
    except Exception:
        storyboard["audio"] = {"music": DEFAULT_MUSIC_S3, "music_volume": 0.12}
    return storyboard


def create_storyboard(
    video_id: str, plot: Dict[str, Any], assets: Dict[str, Any], table_name: Optional[str] = None
) -> Dict[str, Any]:
    # Update status to STORYBOARD_CREATION (idempotent)
    update_status(video_id, "STORYBOARD_CREATION", table_name)

    # Fetch freshest video record (plot, assets) from DynamoDB
    item = _get_video_item(video_id, table_name)
    plot_fresh = item.get("plot") or plot or {}
    assets_fresh = item.get("assets") or assets or {}

    # Build context for model
    context: Dict[str, Any] = {
        "video_id": video_id,
        "plot": plot_fresh,
        "assets": assets_fresh,
    }

    # Try OpenAI first
    api_key = _fetch_openai_api_key()
    storyboard = _call_openai_storyboard(api_key, context) or {}

    if not _validate_storyboard(storyboard):
        storyboard = _fallback_storyboard(video_id, plot_fresh, assets_fresh)

    # Ensure a default background music track is always present
    storyboard = _apply_default_music(storyboard)

    # Convert floats to Decimal before storing in DynamoDB
    storyboard_ddb = _to_dynamodb_compatible(storyboard)

    update_status(
        video_id, "RENDERING", table_name, extra_attributes={"storyboard": storyboard_ddb}
    )
    return storyboard


