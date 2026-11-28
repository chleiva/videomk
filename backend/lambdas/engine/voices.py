"""Polly generative voices, per language, and how a voice is chosen for a speaker.

The catalogue is EVERY generative voice Polly offers (engine/voice_data.py, rebuilt from `describe-voices --engine generative` by scripts/polly_voice_catalog.py:
55 voices, 10 languages on 2026-11-27). The director never sees the list: it states what it WANTS for each speaker in a few fields
({"accent": "British", "gender": "male", "pace": "slow"}, or {"name": "Brian"} when the brief names a voice) and `resolve` (plain code, no model call) casts the
closest voice there is, says what it substituted when the wish cannot be met exactly, and falls back to the default of the viewer's region. So the catalogue can
grow without the prompt growing (docs/SELECTION_ARCHITECTURE.md). They are the voices of the `polly` TTS provider; other providers ignore the cast.
"""
import os
import re
from typing import Any, Dict, List, Optional, Tuple

from . import voice_data

# What the catalogue knows about a voice, and nothing more: language, accent, gender, measured pace. Polly publishes no description of a voice's character
# ("warm", "calm"), nobody has listened to all of them, so there are no such labels here and the resolver does not pretend to match on them.
INFO: Dict[str, Dict[str, Any]] = {v["id"]: v for v in voice_data.VOICES}
# The order voices are offered in when nothing else decides (after gender, accent and family: see `resolve`): the order the English and Spanish catalogue always
# had (Ruth first for US English), then Polly's own order for the languages added on 2026-11-27.
_FIRST = ("Ruth Danielle Joanna Salli Tiffany Matthew Stephen Kenneth Nate Amy Brian Olivia Russell Curtis Kajal Kiara Arjun Niamh Aria Ayanda Jasmine "
          "Lucia Sergio Mia Andres Lupe Pedro Carlos Lea Remi Celine Ambre Florian Gabrielle Liam Isabelle Vicki Daniel Tina Lennart Hannah Sabrina "
          "Bianca Lorenzo Beatrice Camila Leo Carolina Laura Lisa Ola Ewa Suvi Seoyeon Hyunduk").split()
_ORDER = [n for n in _FIRST if n in INFO] + [n for n in INFO if n not in _FIRST]
# name -> (language, accent, gender)
CATALOG: Dict[str, tuple] = {n: (INFO[n]["language"], INFO[n]["accent"], INFO[n]["gender"]) for n in _ORDER}
# every language Polly has a generative voice for; which of them a video may be made in is `enabled()`
LANGUAGES = {"en": "English", "es": "Spanish", "fr": "French", "de": "German", "it": "Italian", "pt": "Portuguese", "nl": "Dutch", "pl": "Polish", "fi": "Finnish", "ko": "Korean"}
NATIVE = {"en": "English", "es": "Español", "fr": "Français", "de": "Deutsch", "it": "Italiano", "pt": "Português (Brasil)", "nl": "Nederlands", "pl": "Polski", "fi": "Suomi", "ko": "한국어"}
# The languages the whole engine is ready for (voice, fonts, word timing, numbers: docs/LANGUAGES.md). Korean has voices but no font with Hangul in the render package yet.
READY = ("en", "es", "fr", "de", "it", "pt", "nl", "pl", "fi")
DEFAULT_ENABLED = "en,es"


def enabled() -> List[str]:
    """The languages a video may be made in on this stage: server setting VIDEO_LANGUAGES (comma list, default en,es), limited to READY."""
    asked = [x.strip().lower() for x in os.environ.get("VIDEO_LANGUAGES", DEFAULT_ENABLED).split(",")]
    out = [x for x in READY if x in asked]
    return out or ["en", "es"]


def language_names(codes: Optional[List[str]] = None, native: bool = False) -> List[str]:
    return [(NATIVE if native else LANGUAGES)[c] for c in (codes or enabled())]


# Where the viewer is decides the default accent; the brief can always ask for another ("with a British voice").
# There is no Canadian English generative voice, so Canada (and anywhere unlisted) gets American.
# South Africa has one voice, Ayanda, of the steady family (see STEADY): kept, there is no other South African voice. India was Kajal (steady) until 2026-11-27.
_EN_BY_REGION = {"GB": "Amy", "IE": "Niamh", "AU": "Olivia", "NZ": "Aria", "ZA": "Ayanda", "IN": "Kiara", "SG": "Jasmine"}
_LATAM = set("MX AR CO CL PE VE EC GT CU BO DO HN PY SV NI CR PA UY PR".split())
# The other languages: a LIVELY voice of the viewer's accent wherever Polly has one (every voice measured on 2026-11-27: docs/POLLY_LIVELY_DEFAULTS_2026-11-27.md).
# French (France) was Léa (steady) and is Ambre. An accent whose voices are all steady keeps its own voice, never another accent's lively one: Canadian French
# (Gabrielle; Liam measures the same) and Polish (Ola; Ewa measures the same). Two owner decisions of 2026-11-28 set that rule aside: ALL Dutch videos use the
# lively Flemish Lisa (nl-BE; Laura, nl-NL, steady, is the second voice: Polly has no Dutch man) and Belgian French uses Ambre (fr-FR, lively) instead of
# Isabelle (steady, still in the catalogue for a brief that names her).
_BY_REGION = {"fr": {"CA": "Gabrielle"}, "de": {"AT": "Hannah", "CH": "Sabrina"}}
_DEFAULT = {"fr": "Ambre", "de": "Vicki", "it": "Beatrice", "pt": "Camila", "nl": "Lisa", "pl": "Ola", "fi": "Suvi", "ko": "Seoyeon"}
# Polly's "generative" engine is two families of voices, and they do not speak alike (measured 2026-11-27, docs/VOICE_QUALITY_IT_ES_2026-11-27.md).
# These 18 give the same audio every time for the same text, read each sentence alone, ignore what the text is about, and move their pitch about as little as
# the neural engine does (Bianca: 2.8 semitones of spread on a children's passage, Lucia 3.3, Mia 3.2). The other 37 (Vicki, Ruth, Amy, Beatrice, Lorenzo,
# Lupe, Carlos ...) give a new take each time, lift their voice for a question or a lively text, and move twice as much (Beatrice 6.6, Lupe 5.2, Vicki 5.6).
# They are also exactly the voices missing from eu-west-2 and ca-central-1 (voice_data.PARTIAL_REGIONS). A default is never one of these when its accent
# has another voice (Italian Beatrice, French Ambre, Indian English Kiara, Spanish Lupe), and `resolve` prefers the other family inside an accent. They stay in
# the catalogue: a brief that names one gets it. Spain has only Lucia and Sergio, both of this family: Sergio, who moves a little more, is its default.
STEADY = frozenset("Andres Ayanda Bianca Celine Daniel Ewa Gabrielle Isabelle Kajal Laura Lea Liam Lucia Mia Ola Pedro Remi Sergio".split())


def default_voice(language: str, region: Optional[str] = None) -> str:
    """The voice for a viewer in `region` (ISO 3166 alpha-2, any case) when the brief doesn't ask for one."""
    r = (region or "").strip().upper()
    if language == "es":   # owner, 2026-11-27: a viewer in Spain keeps a Castilian voice (Sergio; the woman is Lucia); everyone else, the Americas, any other country and
        return "Sergio" if r == "ES" else "Lupe"   # an unknown one, hears Lupe (the man is Carlos). Until then Lucia outside the Americas and Mia (Mexican) in Latin America
    if language in _DEFAULT:
        return _BY_REGION.get(language, {}).get(r, _DEFAULT[language])
    return _EN_BY_REGION.get(r, "Ruth")


def lively(voice: str) -> bool:
    """A voice of the family that gives a new take each time and moves its pitch about twice as much (see STEADY)."""
    return voice in CATALOG and voice not in STEADY


def second_voice(language: str, region: Optional[str] = None) -> str:
    """The default voice of the other gender for this viewer (the second speaker of a conversation when nothing else is asked): the resolver's own answer.
    A language with voices of one gender only gives another voice of that gender, and a language with one voice gives that voice."""
    first = default_voice(language, region)
    other = "male" if CATALOG[first][2] == "female" else "female"
    return resolve({"gender": other}, language, region, [first])[0]


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


# ----------------------------------------------------------------------------- the resolver: what was wanted -> the closest voice there is
# An accent as people and models write it -> Polly locales, best first. A locale we have no voice for maps to the nearest one we do have, and the note says so.
_ACCENTS: List[Tuple[str, List[str]]] = [
    (r"latin|latam|latino|hispano", ["es-US", "es-MX"]),   # before "american"; es-US first since 2026-11-27 (Lupe and Carlos are the lively voices: see STEADY)
    (r"american|\bu\.?s\.?a?\b|united states|estadounidense|am[eé]ricain|amerikanisch", ["en-US", "es-US"]),
    (r"british|\bu\.?k\b|england|english \(uk\)|brit[aá]nic|britannique|britisch|\bgb\b|london", ["en-GB"]),
    (r"scottish|scotland|welsh|wales", ["~en-GB"]),
    (r"australian|aussie|australia", ["en-AU"]),
    (r"new zealand|kiwi|\bnz\b", ["en-NZ"]),
    (r"irish|ireland", ["en-IE"]),
    (r"south african|south africa", ["en-ZA"]),
    (r"singapor", ["en-SG"]),
    (r"indian|india|hindi", ["en-IN"]),
    (r"canadian|canada|qu[eé]b[eé]c|canadien|kanad", ["fr-CA", "~en-US"]),
    (r"mexican|mexico|m[eé]xic|mejic", ["es-MX"]),
    (r"castilian|castellan|peninsular|spain|espa[ñn]a|\bde espa|european spanish|iberian", ["es-ES"]),
    (r"argentin|colombia|chile|peru|venez|ecuador|urugua|cuba|caribe|caribbean|centroam|central america", ["~es-US", "~es-MX"]),   # no such voice: the Latin American ones, the lively pair first
    (r"belgian|belgium|belgi|flemish|vlaams|wallon", ["fr-BE", "nl-BE"]),
    (r"swiss|switzerland|suisse|schweiz", ["de-CH", "~fr-FR"]),
    (r"austrian|austria|[oö]sterreich|autrich", ["de-AT"]),
    (r"brazil|brasil|br[eé]sil", ["pt-BR"]),
    (r"portugal|european portuguese|lusitan", ["~pt-BR"]),
    (r"parisian|paris|\bfrance\b|metropolitan french", ["fr-FR"]),
    (r"germany|deutschland|hochdeutsch|standard german", ["de-DE"]),
    (r"netherlands|holland|nederland", ["nl-NL"]),
]
# when the wanted accent has no free voice (or none of the wanted gender): the accents nearest to it, nearest first
_NEAR = {"en-IE": ["en-GB"], "en-NZ": ["en-AU", "en-GB"], "en-AU": ["en-NZ", "en-GB"], "en-ZA": ["en-GB"], "en-SG": ["en-GB"], "en-GB": ["en-IE", "en-AU"], "en-IN": [], "en-US": [],
         "es-MX": ["es-US"], "es-US": ["es-MX"], "es-ES": [], "fr-BE": ["fr-FR"], "fr-CA": ["fr-FR"], "fr-FR": ["fr-BE"],
         "de-AT": ["de-DE"], "de-CH": ["de-DE"], "de-DE": ["de-AT"], "nl-BE": ["nl-NL"], "nl-NL": ["nl-BE"]}
_FEMALE = re.compile(r"\b(female|woman|women|girl|she|her|feminine|mujer|femenin[ao]|chica|femme|f[eé]minin|frau|weiblich|donna|femminile|mulher|feminin[ao]|vrouw|kobiet|nainen)\b", re.I)
_MALE = re.compile(r"\b(male|man|men|boy|he|his|masculine|hombre|masculin[ao]|chico|homme|masculin|mann|m[aä]nnlich|uomo|maschile|homem|mannelijk|m[eę][zż]czyzn|mies)\b", re.I)
_SLOW = re.compile(r"\b(slow|slower|slowly|calm|unhurried|relaxed|gentle|measured|lento|lenta|despacio|pausad[oa]|tranquil[oa]|lent|lente|langsam|ruhig)\b", re.I)
_FAST = re.compile(r"\b(fast|faster|quick|brisk|lively|energetic|upbeat|snappy|r[aá]pid[oa]|[aá]gil|en[eé]rgic[oa]|rapide|vif|schnell|lebhaft)\b", re.I)
W_GENDER, W_ACCENT, W_NEAR, W_REGION, W_DEFAULT, W_PACE = 6.0, 5.0, 3.0, 2.0, 1.0, 0.5   # a wrong gender is heard at once, a neighbouring accent is not
# A lively voice before a steady one (see STEADY) of the same gender and accent: more than pace, and less than the viewer's own accent (W_REGION) or the step
# from the accent asked to its neighbour (W_ACCENT - W_NEAR) even with pace against it, so a Castilian or Mexican wish is never answered with another accent.
W_LIVELY = 0.9
# With no accent asked, after the viewer's own accent: a Latin American viewer's next voice is Mexican before Castilian (a tie-breaker, smaller than everything else).
_HOME_NEAR = {"es-US": ["es-MX"]}
W_HOME_NEAR = 0.6


def accents(language: str) -> List[str]:
    """The accent words of a language, default first: all the director is told about the catalogue."""
    out: List[str] = []
    for n in names(language):
        if CATALOG[n][1] not in out:
            out.append(CATALOG[n][1])
    return out


def _wanted_locales(text: str, language: str) -> Tuple[List[str], bool]:
    """(locales of this language that fit the accent words, best first; True when only a neighbour of what was asked exists)."""
    low = text.lower()
    have = {INFO[n]["locale"] for n in names(language)}
    for n in names(language):   # the catalogue's own accent word or locale code, exactly
        if CATALOG[n][1].lower() == low.strip() or INFO[n]["locale"].lower() == low.strip():
            return [INFO[n]["locale"]], False
    for pattern, locales in _ACCENTS:
        if re.search(pattern, low):
            exact = [x for x in locales if not x.startswith("~") and x in have]
            if exact:
                return exact, False
            near = [x.lstrip("~") for x in locales if x.lstrip("~") in have]
            if near:
                return near, True
    return [], False


def intent(raw: object, language: str = "en") -> Dict[str, Any]:
    """What was asked for a speaker, in the resolver's own terms: {name, locales, near, gender, pace, said}. `raw` is the director's object
    ({"accent", "gender", "pace", "name"}), a voice name, or a few free words ("a British woman")."""
    d = raw if isinstance(raw, dict) else {"name": raw} if canonical(raw) else {"accent": str(raw or "")}
    out: Dict[str, Any] = {"name": canonical(d.get("name") or d.get("voice")), "locales": [], "near": False, "gender": None, "pace": None, "accent": ""}
    words = " ".join(str(d.get(k) or "") for k in ("accent", "gender", "pace", "manner", "age_feel", "style") if isinstance(d.get(k), (str, int, float)))[:200]
    acc = str(d.get("accent") or "") if isinstance(d.get("accent"), str) else ""
    if acc.strip() and acc.strip().lower() not in ("any", "default", "none", "neutral"):
        out["locales"], out["near"] = _wanted_locales(acc, language)
        out["accent"] = acc.strip()[:40]
    g = str(d.get("gender") or "") + " " + (acc if not isinstance(raw, dict) else "")
    out["gender"] = "female" if _FEMALE.search(g) else "male" if _MALE.search(g) else None
    out["pace"] = "slow" if _SLOW.search(words) else "fast" if _FAST.search(words) else None
    return out


def resolve(raw: object, language: str = "en", region: Optional[str] = None, taken: Optional[List[str]] = None, avoid_gender: Optional[str] = None) -> Tuple[str, str]:
    """(voice, note). The closest free voice of `language` to what was asked; `note` is "" when the wish was met (or nothing was asked) and one plain
    sentence when something had to be substituted. `avoid_gender`: in a dialogue, the gender of the speaker before, used only when no gender was asked."""
    taken = list(taken or [])
    default = default_voice(language, region)
    want = intent(raw, language)
    pool = [n for n in names(language) if n not in taken] or names(language) or [default]
    named = want["name"]
    if named and CATALOG[named][0] == language and named not in taken:
        return named, ""
    home = INFO[default]["locale"] if default in INFO else ""
    rates = sorted(INFO[n].get("wpm") or 0 for n in pool)
    median = rates[len(rates) // 2] if rates else 0

    def score(n: str) -> float:
        v, sc = INFO[n], 0.0
        if want["gender"]:
            sc += W_GENDER if v["gender"] == want["gender"] else 0.0
        elif avoid_gender:
            sc += 1.5 if v["gender"] != avoid_gender else 0.0
        if want["locales"]:
            if v["locale"] in want["locales"]:
                sc += W_ACCENT - 0.1 * want["locales"].index(v["locale"])
            elif any(v["locale"] in _NEAR.get(loc, []) for loc in want["locales"]):
                sc += W_NEAR
        elif v["locale"] == home:
            sc += W_REGION
        elif v["locale"] in _HOME_NEAR.get(home, ()):
            sc += W_HOME_NEAR
        if n == default and (not want["locales"] or v["locale"] in want["locales"]):   # the viewer's default counts only inside the accent asked
            sc += W_DEFAULT
        if n not in STEADY:
            sc += W_LIVELY
        if want["pace"] and v.get("wpm") and median:
            sc += W_PACE * max(-1.0, min(1.0, (v["wpm"] - median) / 15.0)) * (1 if want["pace"] == "fast" else -1)
        return sc

    best = max(pool, key=lambda n: (score(n), -_ORDER.index(n)))
    v = INFO[best]
    missed: List[str] = []
    if named and best != named:
        missed.append(f"{named} is " + ("already speaking" if named in taken else f"not a voice for {LANGUAGES.get(language, language)}"))
    if want["gender"] and v["gender"] != want["gender"]:
        missed.append(f"no free {want['gender']} voice in {LANGUAGES.get(language, language)}")
    if want["accent"] and (want["near"] or not want["locales"] or v["locale"] not in want["locales"]):
        missed.append(f"no {want['accent']} voice" + (f" for a {want['gender']} speaker" if want["gender"] and want["locales"] and not want["near"] else ""))
    note = (f"{'; '.join(missed)}: {best} ({v['accent']}, {v['gender']}) speaks instead" if missed else "")
    return best, note


def cast_voices(raw: object, language: str = "en", region: Optional[str] = None) -> Tuple[Dict[str, str], List[str]]:
    """({speaker id: voice}, notes), at most MAX_SPEAKERS. Each value of `raw` says what is wanted for that speaker (see `intent`). Every voice is real, in the
    video's language, and no two speakers share one; a speaker whose wish cannot be met keeps their id and gets the closest free voice (a note says what changed),
    so a dialogue never loses a character."""
    wanted: Dict[str, Any] = {}
    if isinstance(raw, dict):
        for k, v in raw.items():
            sid = speaker_id(k)
            if sid and sid not in wanted and len(wanted) < MAX_SPEAKERS:
                wanted[sid] = v
    if not wanted:
        return {"narrator": default_voice(language, region)}, []
    out: Dict[str, str] = {}
    taken: List[str] = []
    notes: List[str] = []
    # voices asked for by name are kept out of everyone else's reach; then characters choose, the narrator last: if voices of one gender run out, it is the
    # narrator who changes, not a character.
    reserved = [canonical(v.get("name") or v.get("voice") if isinstance(v, dict) else v, language) for v in wanted.values()]
    order = [s for s in wanted if s != "narrator"] + [s for s in wanted if s == "narrator"]
    for sid in order:
        w = wanted[sid]
        mine = canonical(w.get("name") or w.get("voice") if isinstance(w, dict) else w, language)
        blocked = taken + [r for r in reserved if r and r != mine and r not in taken]
        empty = (isinstance(w, dict) and not any(w.get(k) for k in ("name", "voice", "accent", "gender", "pace"))) or w in (None, "", "default")
        if empty and not taken and len(wanted) == 1:
            voice, note = default_voice(language, region), ""
        else:
            last_gender = CATALOG[taken[-1]][2] if taken else None
            voice, note = resolve(w, language, region, blocked if len(blocked) < len(names(language)) else taken, avoid_gender=last_gender)
            if voice in taken:   # the language has fewer voices than the cast: two speakers must share one
                note = f"{LANGUAGES.get(language, language)} has {len(names(language))} voice{'s' if len(names(language)) != 1 else ''} in all: {voice} speaks for more than one character"
        if note:
            notes.append(f"{sid}: {note}")
        out[sid] = voice
        taken.append(voice)
    return {sid: out[sid] for sid in wanted}, notes   # the director's own order


def clean_cast(raw: object, language: str = "en", region: Optional[str] = None) -> Dict[str, str]:
    return cast_voices(raw, language, region)[0]


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
