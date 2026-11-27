"""Which language a brief is written in, decided before anything else so research, script and voices all use it.

Cheap and deterministic first (common-word counts, free); a small model only when that is unsure (a few thousandths of a cent).
Only English and Spanish are supported: anything else is declined with a clear message instead of getting a video in the wrong language.
"""
import re
from typing import Callable, Optional

from .voices import LANGUAGES

_EN = set("the a an and or of to in is are was were be what why how who which that this it for with on as by from at about explain tell make "
          "story history between your you can does do not into over than their have has".split())
_ES = set("el los las un unos unas y qué cómo por para con sobre historia explica explícame cuéntame hazme entre usted puede hace al se su sus "
          "más pero muy también cuál quién".split())
_FR = set("le la les des du une est et que pas pour avec dans sur quelle quel comment pourquoi histoire".split())
_PT_IT = set("os as uma não são você como sobre para della degli che non sono perché storia".split())
# Only characters no other supported or common language uses count here: accents are shared with French, Portuguese, Italian.
_ES_CHARS = re.compile(r"[¿¡ñ]", re.I)
Detector = Callable[[str, str], str]  # (system, user) -> text


def heuristic(text: str) -> Optional[str]:
    """'en'/'es' only when the evidence is strong and nothing points to another language; else None (ask the small model).
    Words such as "de", "en", "la" belong to several languages, so they never decide alone."""
    words = re.findall(r"[a-záéíóúüñ]+", text.lower())
    en = sum(w in _EN for w in words)
    es = sum(w in _ES for w in words) + 3 * len(_ES_CHARS.findall(text))
    other = sum(w in _FR or w in _PT_IT for w in words)
    if es >= 3 and es >= 3 * (en + other):
        return "es"
    if en >= 3 and en >= 3 * (es + other):
        return "en"
    return None


def detect(text: str, ask: Optional[Detector] = None) -> str:
    """'en', 'es', or 'other'. `ask` is the model call; without it an unsure heuristic falls back to English."""
    h = heuristic(text)
    if h:
        return h
    if ask is None:
        return "en"
    try:
        out = ask("Reply with ONLY the ISO 639-1 code (two lowercase letters) of the main language the text is written in. Reply xx if you cannot tell.",
                  text[:400]).strip().lower()
    except Exception:
        return "en"
    m = re.match(r"[a-z]{2}", out)
    code = m.group(0) if m else "xx"
    return code if code in LANGUAGES else ("en" if code == "xx" else "other")


def unsupported_message() -> str:
    return "VideoMK can make videos in English and Spanish for now. Try describing your video in one of those."
