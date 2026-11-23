"""Step 1: ground (Wikipedia) -> direct (LLM) -> validate -> store plan_r1.json. Rejects bad prompts here."""
import logging
import os
from typing import Any, Dict

from generate_video.db import set_attributes, update_status

from .. import awsio, costs, language as lang_mod, llm, plan as plan_mod, research, voices

DEFAULT_MINUTES = float(os.environ.get("DEFAULT_TARGET_MINUTES", "3"))
MAX_MINUTES = float(os.environ.get("MAX_TARGET_MINUTES", "12"))  # single-call planning limit; longer videos need chapter fan-out


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    video_id = str(event["video_id"])
    user_id = str(event.get("user_id", ""))
    prompt = str(event.get("prompt", ""))[:2000]
    minutes = min(MAX_MINUTES, max(1.0, float(event.get("target_minutes") or DEFAULT_MINUTES)))
    base = {"video_id": video_id, "user_id": user_id, "usage_day": event.get("usage_day")}

    update_status(video_id, "PLOT_CREATION")
    language = str(event.get("language") or "")
    if language not in voices.LANGUAGES:  # not chosen by the caller: work it out from the brief (free for clear briefs)
        language = lang_mod.detect(prompt, lambda s, u: llm.complete(s, u, max_tokens=20, model=llm.REVIEW_MODEL, effort="low")[0])
        if language not in voices.LANGUAGES:
            return {**base, "plot": {"legit": False, "reason": lang_mod.unsupported_message()}}
    def ask_small(system: str, user: str) -> str:
        text, meta = llm.complete(system, user, max_tokens=120, model=llm.REVIEW_MODEL, effort="low")
        costs.add_cost(video_id, meta["cost_usd"])
        return text

    notes, sources = research.gather_notes(prompt, language=language, ask=ask_small)

    meta_acc = {"cost": 0.0}

    def ask(system: str, user: str) -> str:
        text, meta = llm.complete(system, user)
        meta_acc["cost"] += meta["cost_usd"]
        return text

    region = voices.clean_region(event.get("region"))
    plan, warnings = plan_mod.generate_plan(prompt, notes, minutes, ask, language=language, region=region)
    costs.add_cost(video_id, meta_acc["cost"])
    if warnings:
        logging.warning("plan warnings: %s", warnings[:10])  # WARNING level: Lambda drops INFO by default

    if not plan.get("legit"):
        return {**base, "plot": {"legit": False, "reason": plan.get("reason", "")}}

    if event.get("theme") in ("midnight", "paper", "sunrise"):  # the user's choice beats the model's
        plan["theme"] = event["theme"]
    used = plan.pop("sources_used", None)
    if used is not None:  # cite only the pages the script actually drew on, not everything the research happened to fetch
        sources = [s for s in sources if s["title"] in set(used)]
    if region:
        plan["region"] = region
    plan["sources"] = sources
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
