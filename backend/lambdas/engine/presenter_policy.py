"""Does this video get a presenter, who is it, and how often is it on screen? (docs/PRESENTERS.md)

A presenter is one of the standing cartoon characters (engine/vector_presenter.py): four people and the animal cast. In a video that has one, a few beats are `presenter` scenes
(engine/scenes/elements/presenter.py): the character stands beside a card, a chart or a picture and says the narration. The other beats stay normal scenes.

  * the server setting PRESENTERS must be on (default OFF; QA on, production off);
  * the person asked: the create option `presenter: "<id>"`, or plain words ("with a presenter", "explained by a fox", "con personajes", "explicado por un zorro");
  * or, on `auto`, the director's kind of video is one where a presenter fits: children's and fun explainers and tutorials. Nothing else gets one by itself;
  * never: a video of the person's own photos, a deck, a whiteboard video, current events (web research) or a serious kind of video (news, true crime, biography,
    history, recap), not even when asked: the request check's note says so (common/looks.py);
  * `presenter: "none"` or "no presenter" in the words: never.

Casting (`cast`): the character the person named. Else a children's or fun video gets an ANIMAL, by its topic (the owl for learning, science and history, the bear
for health, feelings and bedtime, the cat for technology and how things work, the parrot for languages, travel and fun facts, the turtle for nature, the sea and
step-by-step), and when no topic decides the parrot in a Spanish children's video and the fox everywhere else. Every other video gets a PERSON by topic, as before the animals: the doctor for health, the
engineer for technology, the chef for food, the teacher for everything else. The narrator's voice becomes the character's voice. A dialogue (two or three
speaking characters) gets one presenter per speaker, up to two, each on their own side: animals with animals, people with people.

How often (`Policy.cap`): the opening, the closing and the key points between: about one beat in three, at least two, never two in a row.

This module decides (`decide`), writes the director's prompt block (`Policy.prompt_block`), is the gate `presenter` scenes are checked against while the plan is
cleaned (`scope`, `allowed`), settles the plan afterwards (`enforce`: character, side, voice, the cap, an opening and a closing) and gives the timeline's scenes
their words (`link`). Pure of storage and billing, no model call.
"""
import os
import re
import threading
import zlib
from typing import Any, Dict, List, Optional

# id -> who they are. `voices`: the Polly voices that fit the character, first choice first (all in engine/voices.CATALOG). English: hand-picked, the same for
# every viewer. Every other language: the character's own order among the voices of its gender; which of them speaks also follows the viewer's accent and the
# voice family (`voice_for`). Since 2026-11-27 every first choice is a LIVELY voice where the language has one of that gender (engine/voices.STEADY; measured:
# docs/POLLY_LIVELY_DEFAULTS_2026-11-27.md): Spanish women Lupe and men Carlos (they were Mia, Lucia, Pedro, Andrés, Sergio), French Ambre and Florian, Italian
# Beatrice and Lorenzo, German and Portuguese below. A language with no entry has one lively voice per gender at most and needs no order.
# `skills`: the producer's kinds of video (engine/skills.py) the character is cast for; `words`: topic words that cast it when the kind of video does not decide.
_ES_F, _ES_M = ["Lupe", "Mia", "Lucia"], ["Carlos", "Pedro", "Andres", "Sergio"]
CAST: Dict[str, Dict[str, Any]] = {
    # the teacher: the default narrator's voice of each language (clear, even)
    "ines": {"name": "Inés", "role": {"en": "Teacher", "es": "Profesora"}, "voices": {"en": ["Ruth", "Danielle"], "es": _ES_F, "de": ["Vicki", "Tina"], "pt": ["Camila", "Carolina"]},
             "skills": {"explainer-education", "science-wonder", "history-story", "finance-business", "inspiration-motivation", "listicle-ranking"}, "words": r""},
    "david": {"name": "David", "role": {"en": "Engineer", "es": "Ingeniero"}, "voices": {"en": ["Matthew", "Stephen"], "es": _ES_M},
              "skills": {"coding-tutorial"},
              "words": r"software|code|coding|program|app\b|apps\b|computer|internet|website|algorithm|robot|engineer|technology|tech\b|data\b|\bai\b|machine learning|"
                       r"c[oó]digo|programa|computador|ordenador|tecnolog|ingenier|algoritmo|inteligencia artificial"},
    # the doctor: Kiara, the lively Indian English voice (it was Kajal, steady); elsewhere the calmer, slower woman (German Tina 155 words a minute against Vicki 172)
    "priya": {"name": "Priya", "role": {"en": "Doctor", "es": "Doctora"}, "voices": {"en": ["Kiara", "Danielle"], "es": _ES_F, "de": ["Tina", "Vicki"], "pt": ["Camila", "Carolina"]},
              "skills": {"health-wellbeing"},
              "words": r"health|healthy|doctor|medicine|medical|vaccine|body|heart|brain|sleep|exercise|vitamin|immune|disease|virus|bacteria|"
                       r"salud|saludable|m[eé]dic|medicina|vacuna|cuerpo|coraz[oó]n|cerebro|sue[ñn]o|ejercicio|vitamina|enfermedad"},
    "mateo": {"name": "Mateo", "role": {"en": "Chef", "es": "Chef"}, "voices": {"en": ["Stephen", "Matthew"], "es": _ES_M},
              "skills": set(),
              "words": r"recipe|cook|cooking|kitchen|food|bake|baking|bread|pasta|pizza|soup|ingredient|meal|chef|dish|"
                       r"receta|cocina|cocinar|comida|hornear|pan\b|sopa|ingrediente|plato"},
    # the fox is young: the brighter, quicker woman (German Vicki, the liveliest on a children's text; Portuguese Carolina, 218 Hz and 207 words a minute against Camila 202 and 198)
    "fox": {"name": "Fox", "role": {"en": "Guide for children", "es": "Guía para niños"}, "voices": {"en": ["Joanna", "Salli"], "es": _ES_F, "de": ["Vicki", "Tina"], "pt": ["Carolina", "Camila"]},
            "skills": {"kids-family", "funny-light"}, "words": r"kids?\b|children|child\b|toddlers?|preschool|\d-year-olds?|ni[ñn]os|ni[ñn]as|infantil|peques"},
    # The animal cast. They are cast by themselves only in children's and fun videos (the fox's kinds of video), by the topic `words`; anywhere when asked for by name.
    # the owl is older and calm: a man's voice, the lowest and slowest lively one there is (English Brian; one lively man per language elsewhere: Carlos, Florian, Lennart, Lorenzo, Leo)
    "owl": {"name": "Otto", "role": {"en": "Owl professor", "es": "Búho profesor"}, "voices": {"en": ["Brian", "Matthew"], "es": _ES_M}, "skills": set(),
            "words": r"learn\w*|school|homework|lessons?|science|scientists?|experiments?|history|ancient|maths?|numbers|planets?|space|stars?|dinosaurs?|"
                     r"aprend\w*|escuela|colegio|deberes|lecci[oó]n|ciencias?|experimentos?|historia|antigu[oa]s?|matem[aá]ticas|n[uú]meros|planetas?|espacio|estrellas?|dinosaurios?"},
    "bear": {"name": "Bruno", "role": {"en": "Caring bear", "es": "Oso cariñoso"}, "voices": {"en": ["Stephen", "Matthew"], "es": _ES_M}, "skills": set(),
             "words": r"health|healthy|feelings?|emotions?|worr(?:y|ied|ies)|sad|angry|afraid|scared|calm|bedtime|sleep\w*|teeth|wash\w* (?:your |our )?hands|doctor|dentist|kindness|friendship|"
                      r"salud|saludable|sentimientos?|emoci[oó]n(?:es)?|miedo|triste|enfad\w*|enoj\w*|calma|dormir|sue[ñn]o|dientes|lavarse|m[eé]dic[oa]|dentista|amistad"},
    # the cat is curious and quick: as the fox; in a conversation with the fox she takes the other woman
    "cat": {"name": "Mika", "role": {"en": "Curious cat", "es": "Gata curiosa"}, "voices": {"en": ["Olivia", "Salli"], "es": _ES_F, "de": ["Vicki", "Tina"], "pt": ["Carolina", "Camila"]}, "skills": set(),
            "words": r"technology|tech|computers?|robots?|internet|coding|code|apps?|machines?|engines?|electricity|batter(?:y|ies)|gadgets?|inventions?|phones?|how (?:\w+ ){0,3}works?|"
                     r"tecnolog\w*|computador\w*|ordenador(?:es)?|robots?|internet|programar|c[oó]digo|m[aá]quinas?|motor(?:es)?|electricidad|bater[ií]as?|inventos?|tel[eé]fonos?|c[oó]mo funcionan?"},
    "parrot": {"name": "Paco", "role": {"en": "Travelling parrot", "es": "Loro viajero"}, "voices": {"en": ["Nate", "Matthew"], "es": _ES_M}, "skills": set(),
               "words": r"languages?|spanish|english|french|vocabulary|alphabet|travel\w*|trips?|countr(?:y|ies)|cities|flags?|fun facts?|did you know|"
                        r"idiomas?|espa[ñn]ol|ingl[eé]s|franc[eé]s|vocabulario|abecedario|viaj\w*|pa[ií]s(?:es)?|ciudades|banderas?|datos curiosos|curiosidades|sab[ií]as que"},
    # the turtle is wise and unhurried: the slower woman (German Tina, Portuguese Camila)
    "turtle": {"name": "Tula", "role": {"en": "Wise turtle", "es": "Tortuga sabia"}, "voices": {"en": ["Amy", "Ruth"], "es": _ES_F, "de": ["Tina", "Vicki"], "pt": ["Camila", "Carolina"]}, "skills": set(),
               "words": r"nature|sea|oceans?|beach|rivers?|forests?|jungle|plants?|trees?|recycl\w*|environment|step[- ]by[- ]step|how to|"
                        r"naturaleza|mar|oc[eé]anos?|playa|r[ií]os?|bosques?|selva|plantas?|[aá]rbol(?:es)?|recicl\w*|medio ambiente|paso a paso|c[oó]mo hacer"},
}
ORDER = ("ines", "david", "priya", "mateo", "fox", "owl", "bear", "cat", "parrot", "turtle")
ANIMALS = ("fox", "owl", "bear", "cat", "parrot", "turtle")       # the rest of ORDER are people
KIDS_TOPICS = ("bear", "cat", "parrot", "turtle", "owl")          # in a children's or fun video: the first animal whose topic words are in the request
KIDS_DEFAULT = {"es": "parrot"}                                   # no topic decides: the parrot in a Spanish children's video, the fox everywhere else
DEFAULT = "ines"
OPTIONS = ("auto", "none") + ORDER

# The producer's kinds of video (engine/skills.py). On `auto` only these get a presenter by themselves.
AUTO_SKILLS = {"kids-family", "funny-light", "tutorial-howto", "coding-tutorial"}
# Never, not even when asked: a cartoon presenter does not belong in these.
NEVER_SKILLS = {"news-explainer", "mystery-true-crime", "biography-profile", "photo-memories", "deck-explainer", "recap-summary"}
SHARE = 0.34          # about one beat in three is a presenter scene
MIN_SCENES = 2        # the opening and the closing
# Scenes the director may have written that say the same thing as a presenter card (so `enforce` can turn one into the opening or the closing).
_CARD_TYPES = ("title", "bullets", "kinetic_text", "question_card", "definition", "takeaways", "checklist", "steps", "quote", "stat", "counter", "myth_fact")

_active: Optional["Policy"] = None
_lock = threading.Lock()


def enabled() -> bool:
    """Server setting PRESENTERS (default OFF; 1/true/on enables)."""
    return os.environ.get("PRESENTERS", "0").strip().lower() in ("1", "true", "on", "yes")


def clean_option(v: Any) -> str:
    return v if isinstance(v, str) and v in OPTIONS else "auto"


def wish(option: Any, prompt: str) -> str:
    """'none', a character id, 'any' (a presenter, whoever fits) or 'auto' (nothing said). The option wins; with `auto` the person's own words decide."""
    o = clean_option(option)
    if o != "auto":
        return o
    from common import looks   # the same reading as the request check (so its note and the video agree)

    return looks.presenter_wish(prompt) or "auto"


def cast(prompt: str, skill_ids: Optional[List[str]] = None, asked: Optional[str] = None, language: str = "en") -> str:
    """Which character presents. Asked by name: that one. Else children's and fun videos get an animal: the one whose topic it is (KIDS_TOPICS), else the parrot in a Spanish children's video and the fox elsewhere. Every
    other video gets a person: by the topic's words (doctor, engineer, chef), then by the kind of video, else the teacher."""
    if asked in CAST:
        return asked
    ids = set(skill_ids or [])
    text = str(prompt or "")
    if ids & CAST["fox"]["skills"] or re.search(CAST["fox"]["words"], text, re.I):
        for cid in KIDS_TOPICS:
            if re.search(r"\b(?:" + CAST[cid]["words"] + r")\b", text, re.I):
                return cid
        kids = "kids-family" in ids or re.search(CAST["fox"]["words"], text, re.I)
        return KIDS_DEFAULT.get(str(language or "en")[:2], "fox") if kids else "fox"
    for cid in ("mateo", "priya", "david"):
        if re.search(r"\b(?:" + CAST[cid]["words"] + r")", text, re.I):
            return cid
    for cid in ("david", "priya", "ines"):
        if ids & CAST[cid]["skills"]:
            return cid
    return DEFAULT


def voice_for(cid: str, language: str, taken: Optional[List[str]] = None, region: Optional[str] = None) -> str:
    """The voice of a character in a video of `language` for a viewer in `region`. English: the character's hand-picked voice, the same everywhere. Every other
    language: a voice of the character's gender that is, in this order, free (not `taken` by another character of the video), of the VIEWER'S accent (the accent
    of `voices.default_voice`; then the accent nearest to it), lively rather than steady, and first in the character's own order. So the characters of one video
    share the viewer's accent as far as Polly has voices for it: a conversation for a Latin American viewer is Lupe and Carlos, in Spain Lucia and Sergio; a
    second woman is Mia in Latin America (Mexican: Polly has one lively Latin American woman) and Lupe in Spain (it has one Castilian woman). A language with
    no voice of the character's gender (Dutch, Polish and Finnish have no man) gives one of the other gender, as before."""
    from . import voices

    taken = list(taken or [])
    names = CAST[cid]["voices"].get(language) or []
    if language == "en" and names:
        return next((n for n in names if n not in taken), names[0])
    gender = voices.CATALOG[CAST[cid]["voices"]["en"][0]][2]
    pool = [n for n in voices.names(language) if voices.CATALOG[n][2] == gender] or voices.names(language)
    if not pool:
        return voices.default_voice(language, region)
    home = voices.INFO[voices.default_voice(language, region)]["locale"]
    near = voices._NEAR.get(home, []) + voices._HOME_NEAR.get(home, [])

    def rank(n: str) -> tuple:
        loc = voices.INFO[n]["locale"]
        return (n in taken, 0 if loc == home else 1 if loc in near else 2, n in voices.STEADY, names.index(n) if n in names else len(names), voices._ORDER.index(n))

    return min(pool, key=rank)


class Policy:
    """The decision for one video."""

    def __init__(self, allowed: bool, reason: str, *, character: Optional[str] = None, asked: bool = False, flag: bool = True, language: str = "en"):
        self.allowed, self.reason, self.character, self.asked, self.flag, self.language = allowed, reason, character, asked, flag, language
        # A video whose LOOK is cartoon (engine/art_direction.py): the character(s) are in every scene, not one beat in three; `cast_ids` are the characters of a
        # conversation, `board` puts a hand-drawn board beside them. The direction then writes the prompt block and settles the plan itself.
        self.every, self.cast_ids, self.board = False, [character] if character else [], False

    def cap(self, n_beats: int) -> int:
        """How many beats of a video of `n_beats` may be presenter scenes."""
        if not self.allowed or n_beats <= 0:
            return 0
        if self.every:
            return n_beats
        return min(n_beats, max(MIN_SCENES, int(round(SHARE * n_beats))))

    def summary(self) -> Dict[str, Any]:
        return {"decision": "presenter" if self.allowed else "no", "reason": self.reason, "asked": self.asked, **({"character": self.character} if self.allowed else {})}

    def prompt_block(self, language: str = "en", expected_beats: int = 0) -> str:
        """The paragraph added to the director's prompt (empty when this video has no presenter, and when the look is cartoon: art_direction.prompt_block)."""
        if not self.allowed or self.every:
            return ""
        c = CAST[self.character]
        n = self.cap(expected_beats) if expected_beats else 3
        return (
            f"\n\nPRESENTER. This video is presented by {c['name']}, a friendly cartoon {c['role']['en'].lower()} who appears on screen and speaks. "
            f"Use the scene type `presenter` for the FIRST beat, the LAST beat and the key points between: {MIN_SCENES} to {max(MIN_SCENES, n)} beats in all, never two in a row. "
            "Every other beat is a normal scene (pictures, clips, diagrams, numbers) while the same voice goes on.\n"
            "- presenter: {heading (<=48 chars), points: 0 to 4 short strings (<=60 chars each)}  OR  {heading, chart: {labels: 2-5 strings (<=14), values: plain numbers, unit (<=6)}}  "
            "OR  {heading (<=48), image_query (2-6 words describing a real photograph)}. The presenter stands beside this card, chart or picture and says the beat's narration, "
            "with gestures. Do not write `character` or any layout.\n"
            "  * The first beat: the presenter greets the viewer and asks the video's question; `heading` is that question or the title, no points.\n"
            "  * A key-point beat: 2 to 4 `points`, each a few words that the narration SAYS, in the order it says them (each appears as it is said). "
            "Ordinal words (first, second, third), contrasts (but, on the other hand) and pointing words (look, this, here) in the narration become gestures: use them where natural.\n"
            "  * The last beat: the presenter sums up and says goodbye; `heading` is the takeaway, at most 3 `points`.\n"
            f"  * Narration of presenter beats is {c['name']} talking to the viewer in the first person, warm and direct. The narrator of the whole video is {c['name']}: "
            "one voice, never \"our presenter says\". Never name a real person as the presenter.\n"
            "  * Numbers in a `chart` only from the grounding notes; never invent them."
        )


def decide(prompt: str, *, options: Optional[Dict[str, Any]] = None, skill_ids: Optional[List[str]] = None, photos: Optional[List[Any]] = None,
           research_mode: str = "encyclopedia", language: str = "en", whiteboard: bool = False) -> Policy:
    """Does this video get a presenter, and which? Rules only: no model call."""
    o = options or {}
    w = wish(o.get("presenter"), prompt)
    asked = w not in ("auto", "none")
    flag = enabled()

    def no(reason: str) -> Policy:
        return Policy(False, reason, asked=asked, flag=flag, language=language)

    if not flag:
        return no("flag_off")
    if w == "none":
        return no("asked_none")
    if photos:
        return no("user_media")
    if o.get("deck"):
        return no("deck")
    if whiteboard:
        return no("whiteboard_video")
    if research_mode == "web":
        return no("current_events")
    ids = set(skill_ids or [])
    if ids & NEVER_SKILLS:
        return no("kind_of_video")
    if o.get("style") == "real":
        return no("real_style") if not asked else Policy(True, "asked", character=cast(prompt, skill_ids, w, language), asked=True, language=language)
    if asked:
        return Policy(True, "asked", character=cast(prompt, skill_ids, w, language), asked=True, language=language)
    if not ids & AUTO_SKILLS:
        return no("kind_of_video")
    return Policy(True, "auto", character=cast(prompt, skill_ids, None, language), language=language)


class scope:
    """`with presenter_policy.scope(policy):` makes it the policy `allowed()` answers for (one video per process at a time, as in a Lambda)."""

    def __init__(self, policy: Optional[Policy]):
        self.policy = policy

    def __enter__(self) -> Optional[Policy]:
        global _active
        with _lock:
            self._prev, _active = _active, self.policy
        return self.policy

    def __exit__(self, *exc: Any) -> None:
        global _active
        with _lock:
            _active = self._prev


def allowed(plan: Optional[Dict[str, Any]] = None) -> bool:
    """May a `presenter` scene stay in the plan being cleaned right now? Yes in a video the policy gave a presenter, and in a plan that already records one
    (`plan["presenter"]`: an edit of a finished video cleans its plan again, outside any policy scope, and must keep its presenter scenes)."""
    if _active is not None and _active.allowed:
        return True
    rec = (plan or {}).get("presenter")
    return isinstance(rec, dict) and rec.get("decision") == "presenter"


def backdrops(plan: Dict[str, Any], catalog_ids: List[str]) -> int:
    """A cartoon scene of the catalog behind the presenter's opening and closing (only in a video where the cartoon-scene policy offered scenes: its candidates fit
    the topic). Card scenes only: a chart or a picture keeps the plain background. -> how many scenes got one."""
    if not catalog_ids:
        return 0
    pres = [b for b in plan.get("beats") or [] if (b.get("scene") or {}).get("type") == "presenter"]
    ends = pres[:1] + (pres[-1:] if len(pres) > 1 else [])
    n = 0
    for i, b in enumerate(ends):
        p = b["scene"]["props"]
        if not p.get("chart") and not p.get("image_query"):
            p["backdrop"] = catalog_ids[i % len(catalog_ids)]
            n += 1
    return n


# ----------------------------------------------------------------------------- after the plan is cleaned
def _as_card(scene: Dict[str, Any], narration: str) -> Optional[Dict[str, Any]]:
    """The presenter props that say what a text scene said, or None when the scene is not a text card."""
    if scene.get("type") not in _CARD_TYPES:
        return None
    p = scene.get("props") or {}
    heading = str(p.get("heading") or p.get("title") or p.get("question") or p.get("term") or p.get("text") or p.get("label") or p.get("claim") or "").strip()
    raw = p.get("items") or p.get("points") or p.get("steps") or []
    points = [str(x.get("label") or x.get("text") or x.get("title") or "") if isinstance(x, dict) else str(x) for x in raw if x][:4]
    if not heading and not points:
        heading = " ".join(str(narration or "").split()[:7])
    return {"heading": heading[:48], **({"points": [t[:60] for t in points if t.strip()]} if points else {})}


def _fallback_scene(scene: Dict[str, Any]) -> Dict[str, Any]:
    """A presenter scene beyond the cap, as the plain scene that shows the same thing."""
    p = scene.get("props") or {}
    if p.get("image_query"):
        return {"type": "image", "props": {"image_query": p["image_query"], "alt": p.get("alt") or p.get("heading") or p["image_query"]}}
    if len(p.get("points") or []) >= 2:
        return {"type": "bullets", "props": {"heading": p.get("heading", ""), "items": list(p["points"])}}
    if p.get("chart"):
        return {"type": "chart", "props": {"kind": "bar", "title": p.get("heading", ""), "labels": p["chart"]["labels"], "values": p["chart"]["values"], "unit": p["chart"].get("unit", "")}}
    return {"type": "title", "props": {"title": p.get("heading") or (p.get("points") or [""])[0], "subtitle": ""}}


def enforce(plan: Dict[str, Any], policy: Optional[Policy], sanitize: Optional[Any] = None) -> List[str]:
    """After the plan is cleaned. Records plan["presenter"]. With a presenter: every presenter scene gets its character and side, the voice becomes the character's,
    scenes beyond the cap (and the second of two in a row) become plain scenes, and the video opens and closes with the presenter when the director wrote a text
    card there. Without: nothing to do (a stray `presenter` scene was already refused while cleaning). Returns warnings."""
    warnings: List[str] = []
    if policy is None:
        return warnings
    plan["presenter"] = policy.summary()
    if not policy.allowed or policy.every:   # a cartoon-look video is settled by its direction (art_direction.enforce): every scene, the cast, the voices
        return warnings
    if sanitize is None:
        from .scenes import ELEMENTS

        sanitize = ELEMENTS["presenter"].sanitize
    beats = plan.get("beats") or []
    language = str(plan.get("language") or policy.language or "en")[:2]
    voices = plan.get("voices") if isinstance(plan.get("voices"), dict) else {}
    speakers = [s for s in voices if s != "narrator"]
    # who presents: one character for the narrator; in a dialogue one per speaking character (two at most), each on their own side
    who: Dict[str, Dict[str, str]] = {}
    if speakers:
        kind = [c for c in ORDER if (c in ANIMALS) == (policy.character in ANIMALS)]      # an animal talks with another animal, a person with a person
        others = [c for c in kind if c != policy.character]
        for i, sp in enumerate(speakers[:2]):
            who[sp] = {"character": policy.character if i == 0 else others[zlib.crc32(sp.encode()) % len(others)], "side": "left" if i == 0 else "right"}
    else:
        who["narrator"] = {"character": policy.character, "side": "left"}
    taken: List[str] = []
    new_voices = dict(voices)
    for sp, w in who.items():
        v = voice_for(w["character"], language, taken, plan.get("region"))   # the viewer's accent for every character of the video
        taken.append(v)
        new_voices[sp] = v
    if not speakers:
        new_voices = {"narrator": new_voices["narrator"]}
    plan["voices"] = new_voices

    def is_pres(b: Dict[str, Any]) -> bool:
        return (b.get("scene") or {}).get("type") == "presenter"

    def speaker_of(b: Dict[str, Any]) -> Optional[str]:
        sp = b.get("speaker") or ("narrator" if "narrator" in who else None)
        return sp if sp in who else None

    def make(b: Dict[str, Any], props: Dict[str, Any]) -> bool:
        sp = speaker_of(b)
        if sp is None or b.get("silent"):
            return False
        try:
            b["scene"] = {"type": "presenter", "props": sanitize({**props, **who[sp]})}
        except ValueError:
            return False
        return True

    # the director's own presenter scenes: character and side; a beat the presenter cannot speak (silent, another speaker) becomes a plain scene
    for b in beats:
        if is_pres(b) and not make(b, b["scene"]["props"]):
            b["scene"] = _fallback_scene(b["scene"])
    # open and close with the presenter when a text card stands there
    for idx in ((0, len(beats) - 1) if len(beats) >= 2 else (0,) if beats else ()):
        b = beats[idx]
        if not is_pres(b):
            card = _as_card(b.get("scene") or {}, str(b.get("narration") or ""))
            if card is not None and make(b, card):
                warnings.append(f"presenter: beat {idx + 1} became a presenter scene")
    # never two in a row, then the cap (the opening and the closing are kept, the later extras go first)
    cap = policy.cap(len(beats))
    for i in range(1, len(beats) - 1):
        if is_pres(beats[i]) and is_pres(beats[i - 1]):
            beats[i]["scene"] = _fallback_scene(beats[i]["scene"])
    idxs = [i for i, b in enumerate(beats) if is_pres(b)]
    keep = set(idxs[:1] + idxs[-1:])
    for i in reversed(idxs):
        if len([j for j, b in enumerate(beats) if is_pres(b)]) <= cap:
            break
        if i not in keep:
            beats[i]["scene"] = _fallback_scene(beats[i]["scene"])
    if len(beats) >= 2 and is_pres(beats[-1]) and is_pres(beats[-2]) and len(beats) > 2:
        beats[-2]["scene"] = _fallback_scene(beats[-2]["scene"])
    n = sum(1 for b in beats if is_pres(b))
    plan["presenter"].update({"scenes": n, "of": len(beats), "cast": {sp: w["character"] for sp, w in who.items()}, "voices": {sp: new_voices[sp] for sp in who}})
    if n == 0:
        warnings.append("presenter: the video has a presenter but no beat could show it")
    return warnings


# ----------------------------------------------------------------------------- the timeline
def link(scenes: List[Dict[str, Any]]) -> int:
    """Timeline step (engine/timeline.py): every `presenter` scene learns the words it speaks and when (`speech`, scene time: its gestures and mouth come from them),
    whether the character walks in (`enter`: not when the scene before already showed it on the same side), a seed of its own, where in the video it starts (`at`:
    the characters' breathing, weight and rest pose run on the video's clock, so they do not jump at a cut) and, in a conversation, who spoke in the scene before
    and who speaks in the next one (`prev_speaker`, `next_speaker`: a listener keeps its hands together across the cut). Pure; -> how many scenes."""
    n = 0
    prev: Optional[Dict[str, Any]] = None
    for i, sc in enumerate(scenes):
        if sc.get("type") == "presenter":
            p = sc["props"]
            p["speech"] = [[str(w[0]), float(w[1]), float(w[2])] for w in sc.get("words") or []][:600]
            pp = (prev or {}).get("props") or {}
            same_group = bool(p.get("cast")) and pp.get("cast") == p.get("cast")     # a conversation: everyone is already standing there
            p["enter"] = not (prev is not None and prev.get("type") == "presenter" and (same_group or (not p.get("cast") and pp.get("character") == p.get("character") and pp.get("side") == p.get("side"))))
            p["seed"] = (zlib.crc32(str(sc.get("id", n)).encode("utf-8")) % 997) / 997.0
            p["at"] = round(float(sc.get("start") or 0.0), 4)
            p.pop("prev_speaker", None)
            p.pop("next_speaker", None)
            if p.get("cast"):
                nxt = scenes[i + 1] if i + 1 < len(scenes) else None
                if prev is not None and prev.get("type") == "presenter" and same_group:
                    p["prev_speaker"] = pp.get("character")
                if nxt is not None and nxt.get("type") == "presenter" and (nxt.get("props") or {}).get("cast") == p.get("cast"):
                    p["next_speaker"] = nxt["props"].get("character")
            n += 1
        prev = sc
    return n
