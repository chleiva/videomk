"""The director: from a brief to a validated plan. Everything between "a user typed this" and "here is the script and its cast".

Pure of storage and billing so the production handler and the evaluation script run exactly the same code:
  detect language -> research (queries written by a small model) -> director LLM -> validate, cast voices, keep only sources used.
"""
from typing import Any, Callable, Dict, List, Optional

from . import language as lang_mod, plan as plan_mod, research, voices

Ask = Callable[..., str]  # (system, user, max_tokens=...) -> text


def direct(prompt: str, *, minutes: float, ask_small: Ask, ask_big: Callable[[str, str], str],
           language: Optional[str] = None, region: Optional[str] = None, theme: Optional[str] = None) -> Dict[str, Any]:
    """Returns {"legit": False, "reason": ...} or {"legit": True, "plan": ..., "warnings": [...], "fetched": [titles]}."""
    region = voices.clean_region(region)
    if language not in voices.LANGUAGES:  # not chosen by the caller: work it out from the brief (free for clear briefs)
        language = lang_mod.detect(prompt, lambda s, u: ask_small(s, u, 20))
        if language not in voices.LANGUAGES:
            return {"legit": False, "reason": lang_mod.unsupported_message()}

    notes, sources = research.gather_notes(prompt, language=language, ask=lambda s, u: ask_small(s, u, 120))
    plan, warnings = plan_mod.generate_plan(prompt, notes, minutes, ask_big, language=language, region=region)
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
    plan["sources"] = sources
    return {"legit": True, "plan": plan, "warnings": warnings, "fetched": fetched}
