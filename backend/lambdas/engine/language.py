"""Which language a brief is written in, decided before anything else so research, script and voices all use it.

Cheap and deterministic first (common-word counts, free); a small model only when that is unsure (a few thousandths of a cent).
A video can be made in the languages enabled on this stage (`voices.enabled()`: server setting VIDEO_LANGUAGES, English and Spanish by default; French,
German, Italian, Portuguese, Dutch, Polish and Finnish where switched on: docs/LANGUAGES.md). Anything else is declined with a message that names what is
supported, instead of getting a video in the wrong language.
"""
import re
from typing import Callable, Dict, Optional

from . import voices
from .voices import LANGUAGES

# The commonest words of each language that are NOT also common in another one here ("de", "en", "la", "a", "o", "is", "me" belong to several and never decide).
_WORDS: Dict[str, set] = {
    "en": set("the and of to is are was were be what why how who which that this it for with on as by from at about explain tell make "
              "story history between your you can does do not into over than their have has".split()),
    "es": set("el los las unos unas y qué cómo por para con sobre historia explica explícame cuéntame hazme entre usted puede hace al se su sus "
              "más pero muy también cuál quién".split()),
    "fr": set("le les des du une est et pas pour avec dans sur quelle quel comment pourquoi histoire explique nous vous ce cette aux leur très où être".split()),
    "de": set("der die das und ist nicht ein eine einen mit für auf wie warum was wer über erkläre erklären geschichte zwischen wird sind auch dem den von zu im".split()),
    "it": set("il gli che non sono perché storia della delle degli nel nella spiega spiegami come cosa più anche questo questa tra".split()),
    "pt": set("os uma não são você como para com porque história explique entre mais também isso essa pelo pela nos nas seu sua em um".split()),
    "nl": set("het een en van niet zijn hoe waarom wat wie voor met op over leg uit geschiedenis tussen ook deze dit naar wordt".split()),
    "pl": set("jest nie się jak dlaczego co kto dla na oraz przez wyjaśnij historia między także ten ta czy są jego".split()),
    "fi": set("ja on ei miten miksi mikä kuka että tämä se kanssa selitä historia välillä myös ovat oli mitä".split()),
}
_EN, _ES = _WORDS["en"], _WORDS["es"]
# Only characters no other supported or common language uses count: plain accents are shared between French, Portuguese, Italian and Spanish.
_CHARS = {"es": re.compile(r"[¿¡ñ]", re.I), "de": re.compile(r"ß"), "pt": re.compile(r"[ãõ]", re.I), "pl": re.compile(r"[ąęłńśźż]", re.I)}
_ES_CHARS = _CHARS["es"]
_WORD = re.compile(r"[a-zà-öø-ÿāăąćęłńśźżœß]+")
Detector = Callable[[str, str], str]  # (system, user) -> text


def heuristic(text: str) -> Optional[str]:
    """A language code only when the evidence is strong and nothing points to another language; else None (ask the small model).
    English and Spanish are judged exactly as before the other languages existed; the others need more evidence, and only count where they are enabled."""
    words = _WORD.findall(text.lower())
    score = {lang: sum(w in ws for w in words) + 3 * len(_CHARS[lang].findall(text)) if lang in _CHARS else sum(w in ws for w in words) for lang, ws in _WORDS.items()}
    en, es = score["en"], score["es"]
    other = sum(w in _WORDS["fr"] or w in _WORDS["it"] or w in _WORDS["pt"] for w in words)
    if es >= 3 and es >= 3 * (en + other):
        return "es"
    if en >= 3 and en >= 3 * (es + other):
        return "en"
    best = max(score, key=lambda k: score[k])
    rest = max(v for k, v in score.items() if k != best)
    if best not in ("en", "es") and best in voices.enabled() and score[best] >= 4 and score[best] >= 3 * rest:
        return best
    return None


def detect(text: str, ask: Optional[Detector] = None) -> str:
    """A language code that has voices ('en', 'es', 'fr', ...; the caller checks it is enabled), or 'other'. `ask` is the model call; without it an unsure
    heuristic falls back to English."""
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


def _join(names) -> str:
    names = list(names)
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def unsupported_message(language: Optional[str] = None) -> str:
    """What a person reads when the request is in a language no video can be made in here: it names every language that can."""
    return f"VideoMK can make videos in {_join(voices.language_names())} for now. Try describing your video in one of those."


_MADE_WITH = {"en": "Made with VideoMK", "es": "Hecho con VideoMK", "fr": "Fait avec VideoMK", "de": "Erstellt mit VideoMK", "it": "Creato con VideoMK",
              "pt": "Feito com VideoMK", "nl": "Gemaakt met VideoMK", "pl": "Stworzono w VideoMK", "fi": "Tehty VideoMK:lla", "ko": "VideoMK로 제작"}


def made_with(language: Optional[str]) -> str:
    """The line of the closing card, in the video's language."""
    return _MADE_WITH.get(str(language or "en").lower()[:2], _MADE_WITH["en"])
