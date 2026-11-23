"""Polly generative voices the director may cast, per language, and how a beat's voice is resolved.

A small, balanced set on purpose (accents x genders), not Polly's whole catalogue: easier for the director to choose well and for
people to tell speakers apart. Every voice below was checked with `aws polly describe-voices --engine generative`.
They are the voices of the `polly` TTS provider; other providers ignore the cast.
"""
import re
from typing import Dict, List, Optional

# name -> (language, accent, gender)
CATALOG: Dict[str, tuple] = {
    # English: American, British, Australian, Indian; one woman and one man each, two more Americans (the biggest audience)
    "Ruth": ("en", "American", "female"), "Danielle": ("en", "American", "female"),
    "Matthew": ("en", "American", "male"), "Stephen": ("en", "American", "male"),
    "Amy": ("en", "British", "female"), "Brian": ("en", "British", "male"),
    "Olivia": ("en", "Australian", "female"), "Russell": ("en", "Australian", "male"),
    "Kajal": ("en", "Indian", "female"), "Arjun": ("en", "Indian", "male"),
    # Spanish: Latin American (US Spanish and Mexican) and European (Spain); one woman and one man each
    "Lupe": ("es", "Latin American (US)", "female"), "Pedro": ("es", "Latin American (US)", "male"),
    "Mia": ("es", "Mexican", "female"), "Andres": ("es", "Mexican", "male"),
    "Lucia": ("es", "Spanish (Spain)", "female"), "Sergio": ("es", "Spanish (Spain)", "male"),
}
LANGUAGES = {"en": "English", "es": "Spanish"}
DEFAULT_VOICES = {"en": "Ruth", "es": "Lupe"}   # the house voices: the director leans on them unless another clearly suits better
DEFAULT_VOICE = DEFAULT_VOICES["en"]
MAX_SPEAKERS = 4  # up to 3 speaking characters plus an optional narrator
_BY_LOWER = {n.lower(): n for n in CATALOG}
_ID_RE = re.compile(r"[^a-z0-9_]")


def language_of(voice: str) -> Optional[str]:
    return CATALOG[voice][0] if voice in CATALOG else None


def canonical(name: object, language: Optional[str] = None) -> Optional[str]:
    """The catalogue spelling of a voice name; None if unknown, or (when `language` is given) a voice of another language."""
    v = _BY_LOWER.get(str(name or "").strip().lower())
    return v if v and (language is None or CATALOG[v][0] == language) else None


def names(language: str) -> List[str]:
    return [n for n, (lang, _, _) in CATALOG.items() if lang == language]


def prompt_list(language: str = "en") -> str:
    return "; ".join(f"{n} ({CATALOG[n][1]}, {CATALOG[n][2]})" for n in names(language))


def gender_counts(language: str) -> str:
    f = sum(CATALOG[n][2] == "female" for n in names(language))
    return f"{f} women's voices and {len(names(language)) - f} men's voices"


def speaker_id(raw: object) -> str:
    return _ID_RE.sub("", str(raw or "").strip().lower())[:20]


def clean_cast(raw: object, language: str = "en") -> Dict[str, str]:
    """{speaker id: voice}, at most MAX_SPEAKERS. Every voice is real, in the video's language, and no two speakers share one.
    A speaker whose voice is unknown, in the wrong language or already taken keeps their id and gets a free voice instead
    (preferring a different gender from the speaker before), so a dialogue never loses a character."""
    wanted: Dict[str, Optional[str]] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            sid = speaker_id(k)
            if sid and sid not in wanted and len(wanted) < MAX_SPEAKERS:
                wanted[sid] = canonical(v, language)
    if not wanted:
        return {"narrator": DEFAULT_VOICES.get(language, DEFAULT_VOICE)}
    out: Dict[str, str] = {}
    taken: List[str] = []
    # Characters choose first, the narrator last: if voices of one gender run out, it is the narrator who changes, not a character.
    order = [s for s in wanted if s != "narrator"] + [s for s in wanted if s == "narrator"]
    for sid in order:
        voice = wanted[sid]
        if voice is None or voice in taken:
            pool = [n for n in names(language) if n not in taken and n not in wanted.values()] or [n for n in names(language) if n not in taken]
            last_gender = CATALOG[taken[-1]][2] if taken else None
            voice = next((n for n in pool if CATALOG[n][2] != last_gender), pool[0] if pool else DEFAULT_VOICES.get(language, DEFAULT_VOICE))
        out[sid] = voice
        taken.append(voice)
    return {sid: out[sid] for sid in wanted}  # the director's own order


def beat_voice(plan: Dict, beat: Dict) -> str:
    """The voice that speaks this beat: its speaker's voice, else the narrator (or first speaker), else the plan-wide voice."""
    cast = plan.get("voices") or {}
    if (plan.get("tts") or {}).get("provider", "polly") != "polly":  # the cast is Polly voices; other providers use the plan-wide voice
        return (plan.get("tts") or {}).get("voice", "")
    sp = beat.get("speaker")
    if sp and sp in cast:
        return cast[sp]
    if cast:
        return cast.get("narrator") or next(iter(cast.values()))
    return (plan.get("tts") or {}).get("voice", "")
