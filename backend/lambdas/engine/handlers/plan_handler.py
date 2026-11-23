"""Step 1: ground (Wikipedia) -> direct (LLM) -> validate -> store plan_r1.json. Rejects bad prompts here."""
import logging
import os
from typing import Any, Dict

from generate_video.db import set_attributes, update_status

from .. import awsio, costs, director, llm, voices

DEFAULT_MINUTES = float(os.environ.get("DEFAULT_TARGET_MINUTES", "3"))
MAX_MINUTES = float(os.environ.get("MAX_TARGET_MINUTES", "12"))  # single-call planning limit; longer videos need chapter fan-out


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    video_id = str(event["video_id"])
    user_id = str(event.get("user_id", ""))
    prompt = str(event.get("prompt", ""))[:2000]
    minutes = min(MAX_MINUTES, max(1.0, float(event.get("target_minutes") or DEFAULT_MINUTES)))
    base = {"video_id": video_id, "user_id": user_id, "usage_day": event.get("usage_day")}

    update_status(video_id, "PLOT_CREATION")
    spent = {"cost": 0.0}

    def ask_small(system: str, user: str, max_tokens: int = 120) -> str:
        text, meta = llm.complete(system, user, max_tokens=max_tokens, model=llm.REVIEW_MODEL, effort="low")
        spent["cost"] += meta["cost_usd"]
        return text

    def ask_big(system: str, user: str) -> str:
        text, meta = llm.complete(system, user)
        spent["cost"] += meta["cost_usd"]
        return text

    result = director.direct(prompt, minutes=minutes, ask_small=ask_small, ask_big=ask_big, language=event.get("language"),
                             region=event.get("region"), theme=event.get("theme"))
    costs.add_cost(video_id, spent["cost"])
    if result.get("warnings"):
        logging.warning("plan warnings: %s", result["warnings"][:10])  # WARNING level: Lambda drops INFO by default
    if not result["legit"]:
        return {**base, "plot": {"legit": False, "reason": result.get("reason", "")}}
    plan, language, region = result["plan"], result["plan"]["language"], result["plan"].get("region")

    plan["tts"] = {"provider": os.environ.get("TTS_PROVIDER", "polly"), "voice": os.environ.get("TTS_VOICE", ""), "style": os.environ.get("TTS_STYLE", "Say in a clear, warm, engaging explainer voice")}
    forced = os.environ.get("TTS_VOICE", "")
    if forced:  # an operator-forced voice overrides the director's casting: one voice, no dialogue
        plan["voices"] = {"narrator": voices.canonical(forced, language) or voices.default_voice(language, region)}
        for b in plan["beats"]:
            b.pop("speaker", None)
    if plan["tts"]["provider"] == "polly":  # recorded in the plan so edits months later still use the same voice
        plan["tts"].update({"engine": os.environ.get("POLLY_ENGINE", "generative"), "region": os.environ.get("POLLY_REGION", "us-east-1")})
    key = awsio.prefix(video_id) + "plan_r1.json"
    awsio.put_json(key, plan)
    update_status(video_id, "ASSETS_CREATION", extra_attributes={"title": plan["title"], "n_beats": len(plan["beats"])})
    set_attributes(video_id, {"plan_key": key, "rev": 1})
    return {**base, "plot": {"legit": True}, "plan_key": key, "rev": 1, "mode": "final", "cost_field": "cost_usd", "beat_ids": [b["id"] for b in plan["beats"]]}
