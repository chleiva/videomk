"""The director: from a brief to a validated plan. Everything between "a user typed this" and "here is the script and its cast".

Pure of storage and billing so the production handler and the evaluation script run exactly the same code:
  detect language -> research (queries written by a small model) -> director LLM -> validate, cast voices, keep only sources used.
"""
import os
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple

from datetime import date

import logging

from . import background, engagement, language as lang_mod, length as length_mod, plan as plan_mod, quality, research, researcher, skills as skills_mod, staged as staged_mod, vector_policy, voices, whiteboard_policy
from .netsafe import quality_fixes

def fit_to_target() -> bool:
    """The deterministic length steps (engine/length.py) are on unless FIT_TO_TARGET=0."""
    return os.environ.get("FIT_TO_TARGET", "1") != "0"


SHORT_PHOTO_INTRO_S, SHORT_PHOTO_OUTRO_S = 1.0, 1.5   # the same under a minute (15, 30, 45 s): the music-only frame is 2.5 s, not 6 (plan.SHORT_PHOTO_FRAME_S)
PHOTO_INTRO_S = 2.5   # seconds of music and pictures before the first word of a video made from the user's photos
PHOTO_OUTRO_S = 3.5   # seconds of music alone after the last word

Ask = Callable[..., str]  # (system, user, max_tokens=...) -> text


SHORT_RESEARCH_BUDGET = researcher.Budget(max_iterations=3, max_searches=2, max_reads=1, max_seconds=30.0)   # a video under a minute: one or two searches, one page
SHORT_NOTES_CHARS = 2500   # grounding notes for a video under a minute (15 seconds is about 30 words)


def direct(prompt: str, *, minutes: float, ask_small: Ask, ask_big: Callable[[str, str], str],
           language: Optional[str] = None, region: Optional[str] = None, theme: Optional[str] = None,
           web_provider: Any = None, ask_tools: Optional[researcher.AskTools] = None, today: Optional[str] = None,
           budget: Optional[researcher.Budget] = None, photos: Optional[List[Dict[str, Any]]] = None,
           max_images_per_minute: Optional[float] = None, music_tracks: Optional[List[Dict[str, Any]]] = None, story: Optional[Dict[str, Any]] = None,
           options: Optional[Dict[str, Any]] = None, vector_search: Optional[Callable[..., List[Dict[str, Any]]]] = None) -> Dict[str, Any]:
    """Returns {"legit": False, "reason": ...} or {"legit": True, "plan": ..., "warnings": [...], "fetched": [titles], "research": {...}}.
    With a `web_provider` the brief is first classified: time-sensitive briefs get a web research agent, the rest the cheap encyclopedia path."""
    region = voices.clean_region(region)
    if language not in voices.LANGUAGES:  # not chosen by the caller: work it out from the brief (free for clear briefs)
        language = lang_mod.detect(prompt, lambda s, u: ask_small(s, u, 20))
        if language not in voices.LANGUAGES:
            return {"legit": False, "reason": lang_mod.unsupported_message()}

    today = today or date.today().isoformat()
    info: Dict[str, Any] = {"mode": "encyclopedia"}
    skill_ids = skills_mod.select(prompt, lambda s, u: ask_small(s, u, 120), minutes)   # the producer: which kind of video is this, and so which craft guides apply
    if photos and "photo-memories" not in skill_ids:   # a video of the person's own photos always follows the photo guide (pacing, pauses, music), whatever else it is about
        skill_ids = ["photo-memories"] + skill_ids
    platform = (options or {}).get("platform") if skills_mod.platform_skills_enabled() else None   # the platform guide is loaded from the create option, never picked by the producer
    craft = skills_mod.render(skill_ids, platform) + plan_mod.frame_prompt(options, minutes) + engagement.block(prompt, minutes, language, bool(photos))   # options: {platform, aspect, brief} from the create request
    info["skills"] = skill_ids
    notes, sources = "", []
    if web_provider is not None and ask_tools is not None:
        decision = researcher.decide(prompt, language=language, region=region, today=today, ask=lambda s, u, n=260: ask_small(s, u, n))
        info.update({"decided": decision.mode, "reason": decision.reason, "queries": decision.queries})
        if decision.mode == "web":
            r = researcher.research_web(prompt, decision=decision, language=language, region=region, today=today, provider=web_provider, ask_tools=ask_tools,
                                        budget=budget or (SHORT_RESEARCH_BUDGET if plan_mod.is_short(minutes) else None))
            info.update({"searches": r.searches, "reads": r.reads, "iterations": r.iterations, "seconds": round(r.seconds, 1), "cost_usd": r.cost_usd, "error": r.error})
            if r.sources:
                notes, sources, info["mode"] = r.notes, r.sources, "web"
            else:
                info["fallback"] = True  # nothing usable came back: fall through to the encyclopedia path
    fetch_errors: List[Dict[str, Any]] = []   # Wikipedia/Wikimedia failures (status only): the audit could not tell a 429 from an empty search, now it can
    staged = staged_mod.is_staged(minutes, len(photos or []))
    if info["mode"] != "web":
        notes, sources = research.gather_notes(prompt, language=language, ask=lambda s, u: ask_small(s, u, 120), errors=fetch_errors)
        if plan_mod.is_short(minutes):   # a video under a minute needs a paragraph of facts: notes are capped, and thin notes never trigger a web agent (only a time-sensitive request is researched on the web)
            notes = notes[:SHORT_NOTES_CHARS]
        elif (quality_fixes() and web_provider is not None and ask_tools is not None and not staged and not photos and not info.get("fallback")
                and (len(notes) < research.MIN_USEFUL_NOTES_CHARS or not sources)):
            # thin notes (the audit: 16 of 40 videos had under 1,500 characters, 14 none): escalate to the web research agent, within its own budget, before writing
            dec = researcher.Decision(mode="web", queries=list(info.get("queries") or []), topic="general", reason="thin encyclopedia notes")
            r = researcher.research_web(prompt, decision=dec, language=language, region=region, today=today, provider=web_provider, ask_tools=ask_tools, budget=budget)
            info["searches"] = info.get("searches", 0) + r.searches
            info["escalated"] = {"from_chars": len(notes), "searches": r.searches, "reads": r.reads, "sources": len(r.sources), "seconds": round(r.seconds, 1), "cost_usd": r.cost_usd, "error": r.error}
            logging.warning("RESEARCH_ESCALATED from_chars=%s searches=%s sources=%s", len(notes), r.searches, len(r.sources))
            if r.sources:
                notes = (r.notes + ("\n\n" + notes if notes else ""))[:researcher.MAX_NOTES_CHARS + research.MAX_NOTES_CHARS]
                have = {s["title"] for s in r.sources}
                sources = r.sources + [s for s in sources if s["title"] not in have]
    if plan_mod.is_short(minutes):
        notes = notes[:SHORT_NOTES_CHARS]
    vpolicy = vector_policy.decide(prompt, options=options, skill_ids=skill_ids, photos=photos, research_mode=info["mode"], minutes=minutes,
                                   expected_beats=plan_mod.expected_beats(minutes, len(photos or [])), search=vector_search,
                                   ask=(lambda sys_, usr: ask_small(sys_, usr, 160)) if vector_policy.enabled() else None)   # the cartoon scenes: a special style, offered only where the policy allows (docs/VECTOR_SCENE_POLICY.md)
    # the whiteboard look (docs/WHITEBOARD.md, flag WHITEBOARD): a whole-video style; when it is on for this video the cartoon scenes are not offered
    wpolicy = whiteboard_policy.decide(prompt, options=options, skill_ids=skill_ids, photos=photos, research_mode=info["mode"],
                                       ask=(lambda sys_, usr: ask_small(sys_, usr, 120)) if whiteboard_policy.enabled() else None)
    if wpolicy.allowed:
        vpolicy = vector_policy.Policy(False, vpolicy.style, "whiteboard_video", aspect=vpolicy.aspect, flag=vpolicy.flag)
    craft += vpolicy.prompt_block(language) + wpolicy.prompt_block(language)
    written_from = [notes]   # everything the writer was shown (the grounding check compares the narration with it)
    rate = {"max_images_per_minute": max_images_per_minute} if max_images_per_minute is not None else {}
    with vector_policy.scope(vpolicy), whiteboard_policy.scope(wpolicy):
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
                sec_errors: List[Dict[str, Any]] = []
                out = research.gather_notes(f"{sec['title']} {prompt}", language=language, ask=lambda s, u: ask_small(s, u, 120), errors=sec_errors)
                if sec_errors:
                    with lock:
                        fetch_errors.extend(sec_errors)
                return out

            plan, warnings, sinfo = staged_mod.generate(prompt, notes, minutes, ask_big, research=research_section, language=language, region=region,
                                                        today=today if web_provider is not None else None, allow_clips=info["mode"] != "web", music_tracks=music_tracks, craft=craft, **rate)
            seen = {s["title"] for s in sources}
            sources = sources + [s for s in sinfo["sources"] if s["title"] not in seen and not seen.add(s["title"])]
            info["staged"] = {"sections": sinfo["sections"], "titles": sinfo["titles"]}
            written_from = [notes] + list(sinfo.get("notes") or [])
        else:
            plan, warnings = plan_mod.generate_plan(prompt, notes, minutes, ask_big, language=language, region=region, today=today if info["mode"] == "web" else None, photos=photos,
                                                      allow_clips=info["mode"] != "web", music_tracks=music_tracks, craft=craft, story=story, **rate)
    if not plan.get("legit"):
        return {"legit": False, "reason": plan.get("reason", "")}
    warnings += vector_policy.enforce(plan, vpolicy)   # only catalog ids, the share cap, never two in a row; records plan["vector"]
    warnings += whiteboard_policy.enforce(plan, wpolicy)   # look on: text beats the director left become boards; records plan["whiteboard"]
    rejected = plan.pop("_rejected_scenes", None) or []
    if fetch_errors:
        info["fetch_errors"] = fetch_errors[:20]
        info["fetch_errors_n"] = len(fetch_errors)
    if quality_fixes() and not photos:
        if rejected:   # scenes replaced as invalid get one chance to be corrected, instead of a title card
            sr = quality.repair_scenes(plan, rejected, lambda s, u, n=1800: ask_small(s, u, n), plan_mod.scene_docs())
            info["scene_repair"] = sr
            if sr["repaired"]:
                warnings.append(f"scenes corrected: {sr['repaired']} of {sr['rejected']}")
        brief = options.get("brief") if isinstance((options or {}).get("brief"), dict) else {}
        g = quality.ground_check(plan, written_from, lambda s, u, n=4500: ask_small(s, u, n), request=prompt, brief=" ".join(str(v) for v in brief.values() if v), review_claims="product-marketing" in skill_ids)
        info["grounding"] = g
        if g["flagged"]:
            warnings.append(f"grounding: {g['flagged']} beats had unsupported specifics, {g['repaired']} rewritten")

    if quality_fixes() and not photos:   # beat 1 is never a title card: a photograph of the subject (photo budget permitting) or the card's line as moving words (plan.enforce_opening)
        per_min = plan_mod.DEFAULT_MAX_IMAGES_PER_MINUTE if max_images_per_minute is None else min(plan_mod.MAX_IMAGES_PER_MINUTE, max(0.0, float(max_images_per_minute)))
        opened = plan_mod.enforce_opening(plan["beats"], plan_mod.image_budget(minutes, per_min))
        if opened:
            warnings += opened
            info["opening"] = opened[0].split(": ", 1)[-1]
    if theme in ("midnight", "paper", "sunrise"):  # the user's choice beats the model's
        plan["theme"] = theme
    if wpolicy.allowed:   # a whiteboard video is on paper whatever theme was chosen (captions and the closing card match the board), and has no moving background behind it
        plan["theme"] = whiteboard_policy.THEME
    fetched: List[str] = [s["title"] for s in sources]
    used = plan.pop("sources_used", None)
    if used is not None:  # cite only the pages the script actually drew on, not everything the research happened to fetch
        sources = [s for s in sources if s["title"] in set(used)]
    plan["skills"] = skill_ids   # which craft guides shaped this video (for review)
    bg_wish = None if photos or wpolicy.allowed else background.request_wish(prompt)   # "with a purple 3D background", "fondo fijo": a stated wish wins over the mood (never on a video of the person's own photos)
    if bg_wish and background.enabled() and theme not in ("midnight", "paper", "sunrise") and background.wish_theme(bg_wish):
        plan["theme"] = background.wish_theme(bg_wish)   # the look asked for needs its theme (a light background is the paper theme); a theme chosen in the options stays
    if background.enabled() and not photos and not wpolicy.allowed and (bg_wish or {}).get("kind") != "none" and (bg_wish or not background.data_heavy(plan)):   # the moving background, chosen by the topic's mood (BG_ANIMATED / BG_LOOPS; docs/BACKGROUNDS_ANIMATED.md, docs/HERO_LOOPS_3D.md): one small call, never a failure. Photo videos and data-heavy videos keep the static look
        bg_menu = None
        if background.loops_enabled():   # the pre-rendered 3D loops in the assets bucket: the premium look, offered when the flag is on and the index can be read
            from . import bg_loops
            bg_menu = bg_loops.load_index()
        plan["background"] = background.choose(prompt, plan, lambda s, u: ask_small(s, u, 300), loops=bg_menu, wish=bg_wish)   # the answer is about 20 tokens, but the model's own thinking counts against the limit (60 came back empty on QA)
        info["background"] = {k: plan["background"][k] for k in ("style", "palette", "by", "loop") if k in plan["background"]}
    elif bg_wish and background.enabled():
        info["background"] = {"by": "request", "style": "none"}
    if photos:   # the music has the first seconds and the last seconds to itself: the pictures arrive before the voice does, and the ending is held
        plan["intro_s"], plan["outro_s"] = (SHORT_PHOTO_INTRO_S, SHORT_PHOTO_OUTRO_S) if plan_mod.is_short(minutes) else (PHOTO_INTRO_S, PHOTO_OUTRO_S)
    if fit_to_target():   # the length is kept by arithmetic (engine/length.py; the 2.4 s closing card of a watermarked video, when there is one, is part of the length): a script estimated past the length asked loses whole sentences, then a surplus beat; never the opening or the last line
        fit = length_mod.fit_script(plan, minutes * 60.0 - (2.4 if (options or {}).get("end_card") else 0.0), min_beat_words=plan_mod.MIN_BEAT_WORDS, min_beats=plan_mod.expected_beats(minutes, len(photos or [])), drop_beats=not photos)
        if fit["cut_words"] or not fit["fits"]:   # recorded only when the step acted (or could not): a script that fits leaves no trace
            info["length"] = fit
        if fit["cut_words"]:
            warnings.append(f"length: estimated {fit['before']:.0f} s for {fit['target']:.0f} s asked, cut {fit['cut_sentences']} sentences and {fit['cut_beats']} beats ({fit['cut_words']} words) to {fit['after']:.0f} s")
    if region:
        plan["region"] = region
    if photos:  # the beats that show these photos find them here (the clean copies live in the video's own assets)
        plan["media_items"] = [{**{k: p.get(k) for k in ("id", "key", "w", "h", "orientation", "caption")}, **{k: p[k] for k in ("taken", "where") if p.get(k)}} for p in photos]   # time and place only when the photo has them
        if story and story.get("chapters"):   # what the photos were understood to be about (kept for review and the editor, never shown in the video)
            plan["photo_story"] = {"story": story.get("story", ""), "voice": story.get("voice"), "tone": story.get("tone", ""), "chapters": [{"title": c.get("title", ""), "summary": c.get("summary", "")} for c in story["chapters"]],
                                   "unused": story.get("unused", [])}
    plan["sources"] = sources
    if wpolicy.allowed:   # the narration is final now: every board is tied to the words really said and gets emphasis marks where its pen would rest
        warnings = [w for w in warnings if "whiteboard twice in a row" not in w] + whiteboard_policy.settle(plan, wpolicy)
    return {"legit": True, "plan": plan, "warnings": warnings, "fetched": fetched, "research": info}
