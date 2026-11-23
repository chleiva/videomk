"""Polly generative voices the director may cast, and how a beat's voice is resolved.

The list is every English generative voice Polly offers (checked with `aws polly describe-voices --engine generative`).
They are the voices of the `polly` TTS provider; other providers ignore the cast.
"""
import re
from typing import Dict, List, Optional

# name -> (accent, gender)
CATALOG: Dict[str, tuple] = {
    "Ruth": ("US", "female"), "Danielle": ("US", "female"), "Joanna": ("US", "female"), "Salli": ("US", "female"), "Tiffany": ("US", "female"),
    "Matthew": ("US", "male"), "Stephen": ("US", "male"), "Kenneth": ("US", "male"), "Nate": ("US", "male"),
    "Amy": ("British", "female"), "Brian": ("British", "male"),
    "Olivia": ("Australian", "female"), "Russell": ("Australian", "male"), "Curtis": ("Australian", "male"),
    "Niamh": ("Irish", "female"), "Aria": ("New Zealand", "female"), "Ayanda": ("South African", "female"),
    "Kajal": ("Indian", "female"), "Kiara": ("Indian", "female"), "Arjun": ("Indian", "male"), "Jasmine": ("Singaporean", "female"),
}
DEFAULT_VOICE = "Ruth"
MAX_SPEAKERS = 4  # up to 3 speaking characters plus an optional narrator
_BY_LOWER = {n.lower(): n for n in CATALOG}
_ID_RE = re.compile(r"[^a-z0-9_]")


def canonical(name: object) -> Optional[str]:
    """The catalogue spelling of a voice name, or None if Polly's generative engine doesn't offer it."""
    return _BY_LOWER.get(str(name or "").strip().lower())


def prompt_list() -> str:
    return "; ".join(f"{n} ({a}, {g})" for n, (a, g) in CATALOG.items())


def speaker_id(raw: object) -> str:
    return _ID_RE.sub("", str(raw or "").strip().lower())[:20]


def clean_cast(raw: object) -> Dict[str, str]:
    """{speaker id: catalogue voice}, at most MAX_SPEAKERS, every voice real and no two speakers sharing one."""
    out: Dict[str, str] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            sid, voice = speaker_id(k), canonical(v)
            if sid and voice and sid not in out and len(out) < MAX_SPEAKERS:
                out[sid] = voice
    if not out:
        return {"narrator": DEFAULT_VOICE}
    used: List[str] = []
    for sid in list(out):  # two speakers on one voice would be unintelligible: move the later one to an unused voice
        if out[sid] in used:
            gender = CATALOG[out[sid]][1]
            pool = [n for n, (_, g) in CATALOG.items() if n not in used and n not in out.values()]
            out[sid] = next((n for n in pool if CATALOG[n][1] != gender), pool[0] if pool else out[sid])
        used.append(out[sid])
    return out


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
