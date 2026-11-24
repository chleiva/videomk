"""The director: from a brief to a validated plan. Everything between "a user typed this" and "here is the script and its cast".

Pure of storage and billing so the production handler and the evaluation script run exactly the same code:
  detect language -> research (queries written by a small model) -> director LLM -> validate, cast voices, keep only sources used.
"""
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from datetime import date

from . import language as lang_mod, plan as plan_mod, research, researcher, staged as staged_mod, voices

Ask = Callable[..., str]  # (system, user, max_tokens=...) -> text


def direct(prompt: str, *, minutes: float, ask_small: Ask, ask_big: Callable[[str, str], str],
           language: Optional[str] = None, region: Optional[str] = None, theme: Optional[str] = None,
           web_provider: Any = None, ask_tools: Optional[researcher.AskTools] = None, today: Optional[str] = None,
           budget: Optional[researcher.Budget] = None, photos: Optional[List[Dict[str, Any]]] = None,
           max_images_per_minute: Optional[float] = None, music_tracks: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """Returns {"legit": False, "reason": ...} or {"legit": True, "plan": ..., "warnings": [...], "fetched": [titles], "research": {...}}.
    With a `web_provider` the brief is first classified: time-sensitive briefs get a web research agent, the rest the cheap encyclopedia path."""
    region = voices.clean_region(region)
    if language not in voices.LANGUAGES:  # not chosen by the caller: work it out from the brief (free for clear briefs)
        language = lang_mod.detect(prompt, lambda s, u: ask_small(s, u, 20))
        if language not in voices.LANGUAGES:
            return {"legit": False, "reason": lang_mod.unsupported_message()}

    today = today or date.today().isoformat()
    info: Dict[str, Any] = {"mode": "encyclopedia"}
    notes, sources = "", []
    if web_provider is not None and ask_tools is not None:
        decision = researcher.decide(prompt, language=language, region=region, today=today, ask=lambda s, u, n=260: ask_small(s, u, n))
        info.update({"decided": decision.mode, "reason": decision.reason, "queries": decision.queries})
        if decision.mode == "web":
            r = researcher.research_web(prompt, decision=decision, language=language, region=region, today=today, provider=web_provider, ask_tools=ask_tools, budget=budget)
            info.update({"searches": r.searches, "reads": r.reads, "iterations": r.iterations, "seconds": round(r.seconds, 1), "cost_usd": r.cost_usd, "error": r.error})
            if r.sources:
                notes, sources, info["mode"] = r.notes, r.sources, "web"
            else:
                info["fallback"] = True  # nothing usable came back: fall through to the encyclopedia path
    if info["mode"] != "web":
        notes, sources = research.gather_notes(prompt, language=language, ask=lambda s, u: ask_small(s, u, 120))
    rate = {"max_images_per_minute": max_images_per_minute} if max_images_per_minute is not None else {}
    if staged_mod.is_staged(minutes, len(photos or [])):
        # a long video is written in stages (outline, then each section on its own, each with its own research): see engine/staged.py
        lock = threading.Lock()

        def research_section(sec: Dict[str, Any]) -> Tuple[str, List[Dict[str, str]]]:
            brief = f"{prompt}: {sec['title']}. {sec['goal']}"
            if web_provider is not None and ask_tools is not None:
                dec = researcher.Decision(mode="web", queries=sec["queries"], topic="general", reason="research for one section of a long video")
                r = researcher.research_web(brief, decision=dec, language=language, region=region, today=today, provider=web_provider, ask_tools=ask_tools, budget=budget)
                with lock:
                    info["searches"] = info.get("searches", 0) + r.searches
                    info["section_searches"] = info.get("section_searches", 0) + r.searches
                if r.sources:
                    return r.notes, r.sources
            return research.gather_notes(f"{sec['title']} {prompt}", language=language, ask=lambda s, u: ask_small(s, u, 120))

        plan, warnings, sinfo = staged_mod.generate(prompt, notes, minutes, ask_big, research=research_section, language=language, region=region,
                                                    today=today if web_provider is not None else None, allow_clips=info["mode"] != "web", music_tracks=music_tracks, **rate)
        seen = {s["title"] for s in sources}
        sources = sources + [s for s in sinfo["sources"] if s["title"] not in seen and not seen.add(s["title"])]
        info["staged"] = {"sections": sinfo["sections"], "titles": sinfo["titles"]}
    else:
        plan, warnings = plan_mod.generate_plan(prompt, notes, minutes, ask_big, language=language, region=region, today=today if info["mode"] == "web" else None, photos=photos,
                                                  allow_clips=info["mode"] != "web", music_tracks=music_tracks, **rate)
    if not plan.get("legit"):
        return {"legit": False, "reason": plan.get("reason", "")}

    if theme in ("midnight", "paper", "sunrise"):  # the user's choice beats the model's
        plan["theme"] = theme
    fetched: List[str] = [s["title"] for s in sources]
    used = plan.pop("sources_used", None)
    if used is not None:  # cite only the pages the script actually drew on, not everything the research happened to fetch
        sources = [s for s in sources if s["title"] in set(used)]
    if region:
        plan["region"] = region
    if photos:  # the beats that show these photos find them here (the clean copies live in the video's own assets)
        plan["media_items"] = [{k: p.get(k) for k in ("id", "key", "w", "h", "orientation", "caption")} for p in photos]
    plan["sources"] = sources
    return {"legit": True, "plan": plan, "warnings": warnings, "fetched": fetched, "research": info}
