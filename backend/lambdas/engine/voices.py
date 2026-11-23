"""Polly generative voices the director may cast, per language, and how a beat's voice is resolved.

A small, balanced set on purpose (accents x genders), not Polly's whole catalogue: easier for the director to choose well and for
people to tell speakers apart. Every voice below was checked with `aws polly describe-voices --engine generative`.
They are the voices of the `polly` TTS provider; other providers ignore the cast.
"""
import re
from typing import Dict, List, Optional

# name -> (language, accent, gender): every English and Spanish generative voice Polly offers (checked with describe-voices).
# The director chooses among them using the brief and the viewer's region, so breadth helps; the defaults below keep it predictable.
CATALOG: Dict[str, tuple] = {
    "Ruth": ("en", "American", "female"), "Danielle": ("en", "American", "female"), "Joanna": ("en", "American", "female"),
    "Salli": ("en", "American", "female"), "Tiffany": ("en", "American", "female"),
    "Matthew": ("en", "American", "male"), "Stephen": ("en", "American", "male"), "Kenneth": ("en", "American", "male"), "Nate": ("en", "American", "male"),
    "Amy": ("en", "British", "female"), "Brian": ("en", "British", "male"),
    "Olivia": ("en", "Australian", "female"), "Russell": ("en", "Australian", "male"), "Curtis": ("en", "Australian", "male"),
    "Kajal": ("en", "Indian", "female"), "Kiara": ("en", "Indian", "female"), "Arjun": ("en", "Indian", "male"),
    "Niamh": ("en", "Irish", "female"), "Aria": ("en", "New Zealand", "female"), "Ayanda": ("en", "South African", "female"),
    "Jasmine": ("en", "Singaporean", "female"),
    "Lucia": ("es", "Spanish (Spain)", "female"), "Sergio": ("es", "Spanish (Spain)", "male"),
    "Mia": ("es", "Mexican", "female"), "Andres": ("es", "Mexican", "male"),
    "Lupe": ("es", "Latin American (US)", "female"), "Pedro": ("es", "Latin American (US)", "male"), "Carlos": ("es", "Latin American (US)", "male"),
}
LANGUAGES = {"en": "English", "es": "Spanish"}

# Where the viewer is decides the default accent; the brief can always ask for another ("with a British voice").
# There is no Canadian English generative voice, so Canada (and anywhere unlisted) gets American.
_EN_BY_REGION = {"GB": "Amy", "IE": "Niamh", "AU": "Olivia", "NZ": "Aria", "ZA": "Ayanda", "IN": "Kajal", "SG": "Jasmine"}
_LATAM = set("MX AR CO CL PE VE EC GT CU BO DO HN PY SV NI CR PA UY PR".split())


def default_voice(language: str, region: Optional[str] = None) -> str:
    """The voice for a viewer in `region` (ISO 3166 alpha-2, any case) when the brief doesn't ask for one."""
    r = (region or "").strip().upper()
    if language == "es":
        return "Lucia" if r in ("", "ES") else "Lupe" if r == "US" else "Mia" if r in _LATAM else "Lucia"
    return _EN_BY_REGION.get(r, "Ruth")


def clean_region(raw: object) -> Optional[str]:
    r = str(raw or "").strip().upper()
    return r if re.fullmatch(r"[A-Z]{2}", r) else None


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


def clean_cast(raw: object, language: str = "en", region: Optional[str] = None) -> Dict[str, str]:
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
        return {"narrator": default_voice(language, region)}
    out: Dict[str, str] = {}
    taken: List[str] = []
    # Characters choose first, the narrator last: if voices of one gender run out, it is the narrator who changes, not a character.
    order = [s for s in wanted if s != "narrator"] + [s for s in wanted if s == "narrator"]
    for sid in order:
        voice = wanted[sid]
        if voice is None or voice in taken:
            pool = [n for n in names(language) if n not in taken and n not in wanted.values()] or [n for n in names(language) if n not in taken]
            last_gender = CATALOG[taken[-1]][2] if taken else None
            voice = next((n for n in pool if CATALOG[n][2] != last_gender), pool[0] if pool else default_voice(language, region))
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
