import json
from typing import Any, Dict, Optional, List

from .db import update_status
from .bedrock import invoke_anthropic, response_text

MODEL_ID = "anthropic.claude-3-haiku-20240307-v1:0"


def truncate_prompt(prompt: str, max_len: int = 2048) -> str:
    return prompt[:max_len] if prompt else ""


def _build_system_prompt() -> str:
    return (
        "You are a strict validator and planner for short videos. "
        "First, decide if the user's request is legitimate and safe to fulfill. "
        "If it is not legitimate, respond with a compact JSON with legit=false "
        "and a short reason. If it is legitimate, produce a concise plot outline "
        "for a 10-30 second video with 2-6 scenes. Each scene should include a "
        "one-line description and an estimated duration in seconds (integer). "
        "Do not include camera jargon or production details."
    )


def _build_user_prompt(user_prompt: str) -> str:
    example = {
        "legit": True,
        "summary": "Quick teaser showcasing a beach sunrise with a motivating caption.",
        "scenes": [
            {"id": 1, "description": "Title card fades in: 'New day, new energy'", "duration_s": 3},
            {"id": 2, "description": "Sunlight over waves with upbeat vibe", "duration_s": 6},
            {"id": 3, "description": "Closing tag: 'Keep moving'", "duration_s": 4},
        ],
    }
    instructions = (
        "Return ONLY compact JSON. Keys: legit (bool), summary (string), scenes (array of {id, description, duration_s}). "
        "durations must be small integers. If not legit, return {\"legit\": false, \"reason\": \"...\"}. "
        "No markdown, no code fences."
    )
    return (
        f"User prompt: {user_prompt}\n\n"
        f"Guidelines: {instructions}\n\n"
        f"Example legit JSON: {json.dumps(example)}"
    )


def _parse_plot_json(text: str) -> Dict[str, Any]:
    try:
        data = json.loads(text)
        # Basic shape validation
        if not isinstance(data, dict):
            raise ValueError("Response is not a JSON object")
        if "legit" not in data:
            raise ValueError("Missing 'legit' field")
        if data.get("legit") is True:
            scenes = data.get("scenes") or []
            if not isinstance(scenes, list) or len(scenes) == 0:
                raise ValueError("Expected non-empty 'scenes' array when legit=true")
            # Normalize scenes
            normalized: List[Dict[str, Any]] = []
            for idx, scene in enumerate(scenes, start=1):
                if not isinstance(scene, dict):
                    continue
                description = str(scene.get("description", "")).strip()
                duration = int(scene.get("duration_s", 3) or 3)
                normalized.append({"id": idx, "description": description, "duration_s": max(1, min(duration, 30))})
            data["scenes"] = normalized
        return data
    except Exception as e:
        # Wrap parsing failures with a non-legit response
        return {"legit": False, "reason": f"Failed to parse model response: {str(e)}"}


def create_plot(video_id: str, prompt: str, table_name: Optional[str] = None) -> Dict[str, Any]:
    # Update to PLOT_CREATION
    update_status(video_id, "PLOT_CREATION", table_name)

    truncated = truncate_prompt(prompt)
    if not truncated or len(truncated.strip()) < 3:
        plot = {"legit": False, "reason": "Empty or too short prompt"}
        update_status(video_id, "ASSETS_CREATION", table_name, extra_attributes={"plot": plot})
        return plot

    # Call Bedrock Anthropic to validate and draft a plot
    system_msg = _build_system_prompt()
    user_msg = _build_user_prompt(truncated)
    response = invoke_anthropic(
        messages=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ],
        model_id=MODEL_ID,
        max_tokens=600,
        temperature=0.2,
        system=system_msg,
    )
    raw_text = response_text(response)
    plot = _parse_plot_json(raw_text)

    # Record artifact fields. Next stage expects status to advance to ASSETS_CREATION.
    update_status(video_id, "ASSETS_CREATION", table_name, extra_attributes={"plot": plot})
    return plot


