"""Step 1: ground (Wikipedia) -> direct (LLM) -> validate -> store plan_r1.json. Rejects bad prompts here."""
import logging
import os
from typing import Any, Dict

from generate_video.db import set_attributes, update_status

from common.secrets import get_secret_param

from .. import awsio, costs, director, llm, usermedia, voices, websearch

DEFAULT_MINUTES = float(os.environ.get("DEFAULT_TARGET_MINUTES", "3"))
MAX_MINUTES = float(os.environ.get("MAX_TARGET_MINUTES", "12"))  # single-call planning limit; longer videos need chapter fan-out


WEB_SEARCH_COST_USD = float(os.environ.get("WEB_SEARCH_COST_USD", "0.008"))  # Tavily basic search, one credit; verify against your plan


def _web_tools(spent: Dict[str, float]):
    """The web research tools, or (None, None) when no search key is configured (the encyclopedia path is used)."""
    key = get_secret_param("/videomk/tavily_api_key", quiet=True)
    if not key or os.environ.get("WEB_RESEARCH", "on") == "off":
        return None, None

    def ask_tools(system, messages, tools, **kw):
        blocks, stop, meta = llm.complete_tools(system, messages, tools, model=llm.REVIEW_MODEL, **kw)
        spent["cost"] += meta["cost_usd"]
        return blocks, stop, meta

    return websearch.TavilyProvider(key), ask_tools


def _user_photos(video_id: str, user_id: str, media_ids: Any, spent: Dict[str, float]):
    """Clean copies of the user's uploads plus a caption and safety verdict for each. Returns (usable photos, skipped [{id, reason}])."""
    ids = usermedia.valid_media_ids(media_ids)
    photos, thumbs, skipped = usermedia.prepare(video_id, user_id, ids, get=lambda k: awsio.get_bytes(k), put=lambda k, b: awsio.put_bytes(k, b, "image/jpeg"),
                                                delete=awsio.delete, asset_prefix=awsio.prefix(video_id) + "assets/")

    def ask_vision(system: str, user: str, images: Any) -> str:
        text, meta = llm.complete(system, user, images=images, max_tokens=1800, model=llm.REVIEW_MODEL, effort="low")
        spent["cost"] += meta["cost_usd"]
        return text

    flagged = usermedia.analyze(photos, thumbs, ask_vision)
    if flagged:
        logging.warning("photo review flagged %s of %s photos: %s", len(flagged), len(ids), [f["reason"] for f in flagged])
    return photos, skipped + flagged


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

    photos, skipped = [], []
    if event.get("media"):
        photos, skipped = _user_photos(video_id, user_id, event["media"], spent)
        if not photos:
            return {**base, "plot": {"legit": False, "reason": "None of your photos could be used" + (f" ({skipped[0]['reason']})" if skipped else "") + ". Try different photos."}}
    provider, ask_tools = _web_tools(spent)
    result = director.direct(prompt, minutes=minutes, ask_small=ask_small, ask_big=ask_big, language=event.get("language"),
                             region=event.get("region"), theme=event.get("theme"), web_provider=provider, ask_tools=ask_tools, photos=photos,
                             max_images_per_minute=event.get("max_images_per_minute", float(os.environ.get("MAX_IMAGES_PER_MINUTE", "10"))))
    r = result.get("research") or {}
    spent["cost"] += float(r.get("searches", 0)) * WEB_SEARCH_COST_USD  # the search provider's own price per search
    costs.add_cost(video_id, spent["cost"])
    if r.get("mode") == "web" or r.get("fallback"):
        logging.warning("research: %s", {k: r.get(k) for k in ("mode", "decided", "searches", "reads", "iterations", "seconds", "error", "fallback")})
    if result.get("warnings"):
        logging.warning("plan warnings: %s", result["warnings"][:10])  # WARNING level: Lambda drops INFO by default
    if not result["legit"]:
        return {**base, "plot": {"legit": False, "reason": result.get("reason", "")}}
    plan, language, region = result["plan"], result["plan"]["language"], result["plan"].get("region")

    plan["captions"] = bool(event.get("captions", True))   # the creator's choice: subtitles on (default) or off
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
    set_attributes(video_id, {"plan_key": key, "rev": 1, **({"photos_skipped": len(skipped)} if skipped else {})})
    return {**base, "plot": {"legit": True}, "plan_key": key, "rev": 1, "mode": "final", "cost_field": "cost_usd", "beat_ids": [b["id"] for b in plan["beats"]]}
