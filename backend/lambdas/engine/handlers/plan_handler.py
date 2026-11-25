"""Step 1: ground (Wikipedia) -> direct (LLM) -> validate -> store plan_r1.json. Rejects bad prompts here."""
import logging
import os
from typing import Any, Dict

from generate_video.db import set_attributes, update_status

from common.secrets import get_secret_param

from .. import curate, library, awsio, costs, director, format_options, llm, plan as plan_mod, usermedia, voices, websearch

DEFAULT_MINUTES = float(os.environ.get("DEFAULT_TARGET_MINUTES", "3"))
MAX_MINUTES = float(os.environ.get("MAX_TARGET_MINUTES", "12"))  # single-call planning limit; longer videos need chapter fan-out


WEB_SEARCH_COST_USD = float(os.environ.get("WEB_SEARCH_COST_USD", "0.008"))  # Tavily basic search, one credit; verify against your plan


def plan_max_tokens(minutes: float) -> int:
    return int(min(32000, 6000 + 2600 * float(minutes)))


def _web_tools(spent: Dict[str, float]):
    """The web research tools, or (None, None) when no search key is configured (the encyclopedia path is used)."""
    key = get_secret_param("/videomk/tavily_api_key", quiet=True)
    if not key or os.environ.get("WEB_RESEARCH", "on") == "off":
        return None, None

    def ask_tools(system, messages, tools, **kw):
        # the research agent runs on the script model at medium effort (not the small model): what it finds is what the video says. Thinking counts against max_tokens, hence the room.
        blocks, stop, meta = llm.complete_tools(system, messages, tools, model=llm.RESEARCH_MODEL, effort=llm.RESEARCH_EFFORT, max_tokens=4000, **kw)
        spent["research"] = spent.get("research", 0.0) + meta["cost_usd"]
        return blocks, stop, meta

    return websearch.TavilyProvider(key), ask_tools


def _user_photos(video_id: str, user_id: str, media_ids: Any, spent: Dict[str, float], prompt: str, minutes: float, media_meta: Any = None):
    """The user's uploads made safe and understood. Returns (usable photos, skipped [{id, reason}], story).
    Cheap by design (engine/curate.py): the photos are shown to a small model on contact sheets of 10, then one text-only call works out the story."""
    ids = usermedia.valid_media_ids(media_ids)
    photos, thumbs, skipped = usermedia.prepare(video_id, user_id, ids, get=lambda k: awsio.get_bytes(k), put=lambda k, b: awsio.put_bytes(k, b, "image/jpeg"),
                                                delete=awsio.delete, asset_prefix=awsio.prefix(video_id) + "assets/", meta=media_meta if isinstance(media_meta, dict) else None)
    named = usermedia.attach_places(photos)   # place names from the rounded coordinates; the coordinates are forgotten right here

    def ask_vision(system: str, user: str, images: Any) -> str:
        text, meta = llm.complete(system, user, images=images, max_tokens=1800, model=llm.REVIEW_MODEL, effort="low")
        spent["photos"] = spent.get("photos", 0.0) + meta["cost_usd"]   # (a dict update from several threads: add-and-store of floats, a lost update is a rounding error)
        return text

    def ask_text(system: str, user: str) -> str:
        text, meta = llm.complete(system, user, max_tokens=4500)
        spent["photos"] = spent.get("photos", 0.0) + meta["cost_usd"]
        return text

    flagged, story = curate.curate(photos, thumbs, prompt, minutes, ask_vision=ask_vision, ask_text=ask_text)
    if flagged:
        logging.warning("photo review flagged %s of %s photos: %s", len(flagged), len(ids), [f["reason"] for f in flagged])
    logging.warning("photos: %s uploaded, %s usable (%s with a time, %s with a place), story of %s moments (%s photos used), cost so far $%.4f", len(ids), len(photos), sum(1 for p in photos if p.get("taken")), named, len(curate.moments(story)), len(curate.used_ids(story)), spent.get("photos", 0.0))
    return photos, skipped + flagged, story


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    video_id = str(event["video_id"])
    user_id = str(event.get("user_id", ""))
    prompt = str(event.get("prompt", ""))[:2000]
    minutes = min(MAX_MINUTES, max(0.25, float(event.get("target_minutes") or DEFAULT_MINUTES)))
    base = {"video_id": video_id, "user_id": user_id, "usage_day": event.get("usage_day")}

    update_status(video_id, "PLOT_CREATION")
    spent: Dict[str, float] = {}   # what was spent, by what it paid for (costs.PARTS)

    def ask_small(system: str, user: str, max_tokens: int = 120) -> str:
        text, meta = llm.complete(system, user, max_tokens=max_tokens, model=llm.REVIEW_MODEL, effort="low")
        spent["script"] = spent.get("script", 0.0) + meta["cost_usd"]
        return text

    def ask_big(system: str, user: str) -> str:
        # room for the whole script: a long video is about 100 tokens per spoken beat plus its scene, and the model's own thinking counts against the limit too
        text, meta = llm.complete(system, user, max_tokens=plan_max_tokens(minutes))
        if meta.get("stop_reason") == "max_tokens":
            logging.warning("the plan was cut off at the output limit (%s tokens) for a %s-minute video", meta.get("tokens_out"), minutes)
        spent["script"] = spent.get("script", 0.0) + meta["cost_usd"]
        return text

    photos, skipped, story = [], [], None
    if event.get("media"):
        photos, skipped, story = _user_photos(video_id, user_id, event["media"], spent, prompt, minutes, event.get("media_meta"))
        if not photos:
            return {**base, "plot": {"legit": False, "reason": "None of your photos could be used" + (f" ({skipped[0]['reason']})" if skipped else "") + ". Try different photos."}}
    provider, ask_tools = _web_tools(spent)
    catalog = library.load_catalog(awsio.get_json)
    result = director.direct(prompt, minutes=minutes, ask_small=ask_small, ask_big=ask_big, language=None if event.get("language") in (None, "auto") else event.get("language"),   # auto: detected from the description
                             options={k: event.get(k) for k in ("platform", "aspect", "brief")},
                             region=event.get("region"), theme=event.get("theme"), web_provider=provider, ask_tools=ask_tools, photos=photos, story=story,
                             max_images_per_minute=event.get("max_images_per_minute", float(os.environ.get("MAX_IMAGES_PER_MINUTE", "10"))),
                             music_tracks=catalog)
    r = result.get("research") or {}
    spent["research"] = spent.get("research", 0.0) + float(r.get("searches", 0)) * WEB_SEARCH_COST_USD  # the search provider's own price per search
    for part, usd in spent.items():
        costs.add_cost(video_id, usd, part=part)
    if r.get("mode") == "web" or r.get("fallback") or r.get("escalated") or r.get("fetch_errors_n"):
        logging.warning("research: %s", {k: r.get(k) for k in ("mode", "decided", "searches", "reads", "iterations", "seconds", "error", "fallback", "escalated", "fetch_errors_n", "grounding")})
    if result.get("warnings"):
        logging.warning("plan warnings: %s", result["warnings"][:10])  # WARNING level: Lambda drops INFO by default
    if not result["legit"]:
        return {**base, "plot": {"legit": False, "reason": result.get("reason", "")}}
    plan, language, region = result["plan"], result["plan"]["language"], result["plan"].get("region")

    known = {t["id"] for t in catalog}
    chosen = plan_mod.sanitize_music(plan.get("music"), len(plan["beats"]), known)   # only recordings that really exist; no catalogue, no music
    plan.pop("music", None)
    if chosen:
        plan["music"] = chosen
    plan["target_seconds"] = round(minutes * 60)   # the length asked and billed: the timeline never comes out shorter
    plan["frame"] = format_options.frame_dict(event.get("aspect"), event.get("resolution"), event.get("platform"))   # the picture size: the timeline, the renderer and every edit read it back
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
