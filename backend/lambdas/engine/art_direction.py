"""Art direction: ONE look for the whole video, decided before a word is written, then checked and repaired (docs/CREATE_API.md "Video look (chosen and enforced)").

The owner's complaint this answers: videos felt random, "mixing too many things", and a look asked for only half happened. So:

  * `decide`   the video's direction. A look the person CHOSE (`look`, `cast`, `extras`; or the old `style` / `presenter` fields and plain words such as
               "as a whiteboard video", "explained by a fox and a bear") is taken as it is. Otherwise (`auto`) the director commits to one of the named recipes
               with a one-sentence reason: the topic policies say which recipes this video may have, one small model call picks among them.
  * `policies` the three older per-look policies (cartoon scenes, whiteboard, presenter) built FROM the direction, so they can no longer each add a little.
  * `prompt_block` what the writer is told for the cartoon recipes (a presenter in every scene, a conversation, a hand-drawn board beside them).
  * `enforce`  after the plan is written: every scene must fit the direction. A scene that does not is converted to the look's own scene type with the same
               narration (a list becomes a board, or a character beside the list). Never an error, never silently ignored: `plan["look"]` records every repair.

Recipes: footage | whiteboard | presenter | conversation | presenter_board | conversation_board.
Tested numbers (tests/test_art_direction.py): whiteboard >= 80 % of the time on a board (a real picture at most once per 30 s, never first or last);
cartoon 100 % in the cartoon world and >= 80 % with a character on screen; real / footage 0 % cartoon, board or character.
"""
import json
import logging
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from . import presenter_policy, vector_policy, whiteboard_policy

RECIPES = ("footage", "whiteboard", "presenter", "conversation", "presenter_board", "conversation_board")
LOOK_OF = {"footage": "real", "whiteboard": "whiteboard", "presenter": "cartoon", "conversation": "cartoon", "presenter_board": "cartoon", "conversation_board": "cartoon"}
MIN_SHARE = {"whiteboard": 0.80, "cartoon": 0.80, "real": 1.0}     # the share of the video's time that must be in the look (cartoon: with a character on screen)
PICTURE_EVERY_S = 30.0          # whiteboard: one real picture per this many seconds at most
BACKDROP_ONLY_SHARE = 0.20      # cartoon: full-screen cartoon scenes without the character, at most this share of the time
CONVERSATION_MIN_S = 20.0
CONVERSATION_BEAT_S = 6.0       # a line of a conversation is about this long (an ordinary beat is 10 s)
BOARD_MAX_ITEMS = 8             # the board beside a character is half a frame: fewer things than a full whiteboard
SPOKEN_WORDS_PER_S, BEAT_OVERHEAD_S = 2.4, 0.95      # engine/plan.py (kept here so this module needs nothing from it)
# Who talks well with whom when the cast is chosen for the person: same kind (animals with animals, people with people), different temperaments and voices.
PARTNER = {"fox": "owl", "owl": "fox", "bear": "fox", "cat": "owl", "parrot": "turtle", "turtle": "parrot", "ines": "david", "david": "ines", "priya": "ines", "mateo": "priya"}
THIRD = {"fox": "bear", "owl": "bear", "bear": "owl", "cat": "fox", "parrot": "fox", "turtle": "owl", "ines": "priya", "david": "priya", "priya": "david", "mateo": "ines"}
ROLES = ("asks the questions a curious viewer would ask", "explains, patiently and concretely", "adds an everyday example or a gentle joke")
MEDIA = ("image", "gallery", "clip")
FAMILY = {"image": "media", "gallery": "media", "clip": "media", "vector_scene": "cartoon", "presenter": "characters", "whiteboard": "whiteboard"}   # anything else: "graphics" (our drawn titles, lists, charts, maps)

_CONVERSATION_RE = re.compile(r"\b(conversation|dialogue|talking to each other|talk(?:ing)? (?:to|with) each other|chat(?:ting)? (?:about|with)|discuss(?:ing)?|multiple characters|several characters|"
                              r"(?:two|three|2|3) (?:\w+ )?(?:characters|friends|animals|presenters|hosts)|characters? talking|"
                              r"conversaci[oó]n|di[aá]logo|hablando entre|conversando|charlando|varios personajes|(?:dos|tres) (?:\w+ )?(?:personajes|amigos|animales|presentadores))\b", re.I)
_THREE_RE = re.compile(r"\b(three|3|tres)\b", re.I)
_BOARD_RE = re.compile(r"\b(on a (?:white)?board|with a (?:white)?board|draw(?:s|ing)? (?:it )?(?:on|as)|sketch(?:es|ing)?|hand[- ]drawn|en (?:una|la) pizarra|con (?:una )?pizarra|dibuj(?:a|an|ando)|boceto)\b", re.I)


class Direction:
    """The decision for one video."""

    def __init__(self, recipe: str, *, by: str = "auto", chosen: str = "auto", cast: Optional[List[str]] = None, why: str = "", reason: Optional[str] = None,
                 candidates: Optional[List[str]] = None):
        self.recipe = recipe if recipe in RECIPES else "footage"
        self.look = LOOK_OF[self.recipe]
        self.by, self.chosen, self.cast, self.why, self.reason = by, chosen, list(cast or []), why, reason
        self.candidates = list(candidates or [])
        self.board = self.recipe.endswith("_board")
        self.conversation = self.recipe.startswith("conversation")

    def summary(self) -> Dict[str, Any]:
        return {"chosen": self.chosen, "applied": self.look, "recipe": self.recipe, "by": self.by, "why": self.why, "reason": self.reason,
                "cast": list(self.cast) if self.look == "cartoon" else [], "extras": ["board"] if self.board else [],
                **({"candidates": self.candidates} if self.candidates else {})}


def beat_seconds(b: Dict[str, Any]) -> float:
    if b.get("silent"):
        return float(b.get("hold") or 2.0)
    return len(str(b.get("narration") or "").split()) / SPOKEN_WORDS_PER_S + BEAT_OVERHEAD_S


def family(scene: Dict[str, Any]) -> str:
    return FAMILY.get((scene or {}).get("type"), "graphics")


# ----------------------------------------------------------------------------- what the person asked for
def cast_in_words(prompt: str) -> List[str]:
    """The characters of the cast the request names, in the order it names them ("explained by a fox and a bear" -> fox, bear), at most three."""
    from common import looks

    text = " ".join(str(prompt or "").split())
    found = []
    for cid, words in looks.PRESENTER_WORDS.items():
        m = re.search(r"\b(?:" + words + r")\b", text, re.I)
        if m:
            found.append((m.start(), cid))
    return [cid for _, cid in sorted(found)][:3]


def asked(prompt: str, options: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The look the person chose, in the terms of the contract: {"look", "cast": [...], "board": bool, "by": "you" (a field) | "words"}; None when nothing was chosen.
    The `look` field wins; then the older fields (`style`, `presenter`); then plain words."""
    from common import look_choice, looks

    c = look_choice.from_legacy(options)
    if c:
        return {"look": c["look"], "cast": list(c.get("cast") or []), "board": "board" in (c.get("extras") or []), "by": "you", "n": len(c.get("cast") or []) or None}
    pres = options.get("presenter") if isinstance(options.get("presenter"), str) else None
    if pres in presenter_policy.CAST:
        return {"look": "cartoon", "cast": [pres], "board": False, "by": "you", "n": 1}
    wishes = looks.wishes(prompt)
    if "real" in wishes:
        return {"look": "real", "cast": [], "board": False, "by": "words", "n": None}
    text = " ".join(str(prompt or "").split())
    characters = "characters" in wishes and pres != "none"
    if characters or (options.get("style") == "cartoon" and pres != "none") or ("cartoon" in wishes and pres != "none" and "whiteboard" not in wishes):
        named = cast_in_words(text) if characters else []
        one = looks.presenter_wish(text)
        if not named and one in presenter_policy.CAST:
            named = [one]
        talk = bool(_CONVERSATION_RE.search(text)) or len(named) >= 2
        n = (3 if _THREE_RE.search(text) and _CONVERSATION_RE.search(text) else 2) if talk else 1
        return {"look": "cartoon", "cast": named[:3], "board": characters and ("whiteboard" in wishes or bool(_BOARD_RE.search(text))), "by": "you" if options.get("style") == "cartoon" else "words",
                "n": max(n, len(named)) if talk else (len(named) or None)}
    if "whiteboard" in wishes or options.get("style") == "whiteboard":
        return {"look": "whiteboard", "cast": [], "board": False, "by": "words", "n": None}
    return None


def fill_cast(cast: List[str], n: int, prompt: str, skill_ids: List[str], language: str) -> List[str]:
    """`n` characters that suit the topic and each other: the ones named, then the topic's own character, then its usual partner. Never people with animals unless named so."""
    out = [c for c in cast if c in presenter_policy.CAST][:3]
    if not out:
        out = [presenter_policy.cast(prompt, skill_ids, None, language)]
    while len(out) < n:
        for cand in (PARTNER.get(out[0]), THIRD.get(out[0])) + tuple(c for c in presenter_policy.ORDER if (c in presenter_policy.ANIMALS) == (out[0] in presenter_policy.ANIMALS)):
            if cand and cand not in out:
                out.append(cand)
                break
        else:
            break
    return out[:max(1, n)]


# ----------------------------------------------------------------------------- auto: one direction, with a reason
AUTO_SYSTEM = (
    "You are the art director of a narrated explainer video. Before anything is written you commit to ONE visual direction for the whole video, so that it looks like one piece and not a mix. "
    "Choose from the directions listed in the request (only those), by the topic, the audience, the platform and the length:\n"
    "- footage: real photographs and stock video with clean animated titles, charts and maps. The default. Right for real things (places, nature, people at work, products, food, history, "
    "science you can see), for adult and professional audiences, for anything where real pictures carry the story.\n"
    "- whiteboard: everything is drawn and written by a marker on a whiteboard. Right for HOW something works or WHY: a process, a mechanism, a concept, an idea with steps, causes or "
    "numbers, where real pictures would add little.\n"
    "- presenter: one friendly cartoon character presents every scene in a cartoon world. Right for young children, playful topics and friendly tutorials.\n"
    "- conversation: two cartoon characters talk the topic through, one asking and one explaining. Right for children's \"why\" questions and playful explainers of 30 seconds or more.\n"
    "- presenter_board: a cartoon character explains at a hand-drawn board. Right for a lesson for children or beginners that has steps, parts or numbers worth drawing.\n"
    "When two fit, prefer the one that shows the subject most truthfully; never pick a cartoon direction for a serious, sad or professional topic. "
    'Answer with JSON only: {"direction": "<one of the listed ids>", "why": "<one plain sentence, at most 18 words, in the language asked for, saying why this look suits THIS video>"}'
)
WHY = {
    "en": {"you": "You chose this look.", "words": "You asked for this look in your request.", "own_photos": "Made from your own photos.", "deck": "Made from your slides.",
           "footage": "Real pictures tell this topic best.", "whiteboard": "A process like this is clearest drawn step by step.", "presenter": "A friendly character suits this audience.",
           "conversation": "Two characters make the questions and answers lively.", "presenter_board": "A character at a board makes the steps easy to follow.",
           "current": "A topic about real events is shown with real pictures."},
    "es": {"you": "Elegiste este estilo.", "words": "Pediste este estilo en tu solicitud.", "own_photos": "Hecho con tus propias fotos.", "deck": "Hecho con tus diapositivas.",
           "footage": "Las imágenes reales cuentan mejor este tema.", "whiteboard": "Un proceso así se entiende mejor dibujado paso a paso.", "presenter": "Un personaje cercano encaja con este público.",
           "conversation": "Dos personajes hacen más vivas las preguntas y respuestas.", "presenter_board": "Un personaje junto a una pizarra hace fáciles los pasos.",
           "current": "Un tema sobre hechos reales se muestra con imágenes reales."},
}


def _why(key: str, language: str) -> str:
    return WHY["es" if str(language)[:2] == "es" else "en"][key]


def candidates(*, skill_ids: List[str], photos: Any, deck: bool, research_mode: str, minutes: float, options: Dict[str, Any]) -> List[str]:
    """The directions `auto` may choose from for this video: the older topic policies, now deciding the whole video instead of single scenes."""
    out = ["footage"]
    if photos or deck or research_mode == "web":
        return out
    ids = set(skill_ids or [])
    if whiteboard_policy.enabled() and ids & whiteboard_policy.AUTO_SKILLS and not ids & whiteboard_policy.NEVER_SKILLS:
        out.append("whiteboard")
    if (presenter_policy.enabled() and ids & presenter_policy.AUTO_SKILLS and not ids & presenter_policy.NEVER_SKILLS and options.get("presenter") != "none"
            and options.get("platform") != "linkedin"):
        out.append("presenter")
        if minutes * 60.0 >= 30.0 and ids & {"kids-family", "funny-light"}:
            out.append("conversation")
        if whiteboard_policy.enabled():
            out.append("presenter_board")
    return out


def choose_auto(prompt: str, cands: List[str], *, skill_ids: List[str], minutes: float, language: str, options: Dict[str, Any], ask: Optional[Callable[[str, str], str]]) -> Tuple[str, str]:
    """(direction, why). One candidate: no call. Otherwise one small model call; any failure is `footage` (a plain, coherent video is always a good answer)."""
    if len(cands) == 1 or ask is None:
        return cands[0], _why(cands[0], language)
    brief = options.get("brief") if isinstance(options.get("brief"), dict) else {}
    user = (f"Video request: {(prompt or '')[:600]}\nKind of video: {', '.join(skill_ids[:3]) or 'general'}\nAudience: {brief.get('audience') or 'not stated'}\nTone: {brief.get('tone') or 'not stated'}\n"
            f"Platform: {options.get('platform') or 'not stated'}\nLength: {int(round(minutes * 60))} seconds\nDirections you may choose from: {', '.join(cands)}\n"
            f"Language of the reason: {'Spanish' if str(language)[:2] == 'es' else 'English'}")
    for _ in range(2):
        try:
            raw = ask(AUTO_SYSTEM, user)
            data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
            if data.get("direction") in cands:
                why = " ".join(str(data.get("why") or "").split())[:160]
                return data["direction"], why or _why(data["direction"], language)
        except Exception:  # noqa: BLE001
            continue
    logging.warning("ART_DIRECTION auto choice failed twice; footage")
    return "footage", _why("footage", language)


def decide(prompt: str, *, options: Optional[Dict[str, Any]] = None, skill_ids: Optional[List[str]] = None, photos: Optional[List[Any]] = None, research_mode: str = "encyclopedia",
           minutes: float = 1.0, language: str = "en", ask: Optional[Callable[[str, str], str]] = None) -> Direction:
    """The one direction of this video. What still overrides a chosen look: the person's own photos or deck (they ARE the look) and a look this stage does not have."""
    o = options or {}
    ids = list(skill_ids or [])
    deck = bool(o.get("deck")) or "deck-explainer" in ids
    a = asked(prompt, o)
    chosen = a["look"] if a else "auto"
    if photos or deck:
        return Direction("footage", by="auto" if not a or a["look"] == "real" else a["by"], chosen=chosen, why=_why("deck" if deck else "own_photos", language),
                         reason=("deck" if deck else "own_photos") if a and a["look"] != "real" else None)
    reason = None
    if a:
        if a["look"] == "real":
            return Direction("footage", by=a["by"], chosen=chosen, why=_why(a["by"], language))
        if a["look"] == "whiteboard" and whiteboard_policy.enabled():
            return Direction("whiteboard", by=a["by"], chosen=chosen, why=_why(a["by"], language))
        serious = a["by"] == "words" and (research_mode == "web" or set(ids) & presenter_policy.NEVER_SKILLS)     # words alone do not put a cartoon fox into the news; the look FIELD does
        if a["look"] == "cartoon" and presenter_policy.enabled() and not serious:
            n = a["n"] or (2 if (minutes * 60.0 >= 30.0 and set(ids) & {"kids-family", "funny-light"} and not a["cast"]) else 1)
            if n >= 2 and minutes * 60.0 < CONVERSATION_MIN_S:
                n, reason = 1, "too_short"
            cast = fill_cast(a["cast"], n, prompt, ids, language)
            board = a["board"] and whiteboard_policy.enabled()
            if a["board"] and not board:
                reason = "not_available"
            return Direction(("conversation" if len(cast) >= 2 else "presenter") + ("_board" if board else ""), by=a["by"], chosen=chosen, cast=cast, why=_why(a["by"], language), reason=reason)
        if serious:
            return Direction("footage", by="auto", chosen=chosen, why=_why("current", language), reason="serious")
        reason = "not_available"   # the stage does not have the look: the director chooses, and the record says why
    cands = candidates(skill_ids=ids, photos=photos, deck=deck, research_mode=research_mode, minutes=minutes, options=o)
    recipe, why = choose_auto(prompt, cands, skill_ids=ids, minutes=minutes, language=language, options=o, ask=ask)
    cast = fill_cast([], 2 if recipe.startswith("conversation") else 1, prompt, ids, language) if LOOK_OF[recipe] == "cartoon" else []
    return Direction(recipe, by="auto", chosen=chosen, cast=cast, why=why, reason=reason, candidates=cands)


# ----------------------------------------------------------------------------- the older policies, built from the direction
def policies(d: Direction, prompt: str, *, options: Optional[Dict[str, Any]] = None, skill_ids: Optional[List[str]] = None, minutes: float = 1.0, expected_beats: int = 0, language: str = "en",
             vector_search: Any = None, ask: Optional[Callable[[str, str], str]] = None) -> Tuple[vector_policy.Policy, whiteboard_policy.Policy, presenter_policy.Policy]:
    """(cartoon scenes, whiteboard, presenter) for this direction. Exactly one look is on; the other two are off with the reason `direction:<recipe>`."""
    o = dict(options or {})
    aspect = o.get("aspect") if o.get("aspect") in ("16:9", "9:16", "1:1", "4:5") else "16:9"
    why = "direction:" + d.recipe
    v = vector_policy.Policy(False, "real" if d.look == "real" else "auto", why, aspect=aspect, flag=vector_policy.enabled())
    w = whiteboard_policy.Policy(False, why, flag=whiteboard_policy.enabled(), aspect=aspect)
    p = presenter_policy.Policy(False, why, flag=presenter_policy.enabled(), language=language)
    if d.look == "whiteboard":
        w = whiteboard_policy.Policy(True, "asked" if d.by != "auto" else "auto", asked=d.by != "auto", aspect=aspect)
    elif d.look == "cartoon":
        p = presenter_policy.Policy(True, "asked" if d.by != "auto" else "auto", character=d.cast[0], asked=d.by != "auto", language=language)
        p.every, p.cast_ids, p.board = True, list(d.cast), d.board
        if vector_policy.enabled():   # the backdrops: cartoon scenes of the catalog that fit the topic (the person's look, so a loose match is fine)
            v = vector_policy.decide(prompt, options={**o, "style": "cartoon"}, skill_ids=skill_ids, minutes=minutes, expected_beats=expected_beats, search=vector_search, ask=ask)
            v.share, v.first_ok = BACKDROP_ONLY_SHARE, False
    return v, w, p


def conversation_beats(minutes: float) -> int:
    return max(4, int(round(minutes * 60.0 / CONVERSATION_BEAT_S)))


def prompt_block(d: Direction, language: str = "en", minutes: float = 1.0, aspect: str = "16:9") -> str:
    """What the writer is told about the direction. The whiteboard has its own block (whiteboard_policy); footage needs none (nothing else is offered)."""
    if d.look != "cartoon":
        return ""
    C = presenter_policy.CAST
    names = [f"{C[c]['name']} (speaker id \"{c}\": a cartoon {C[c]['role']['en'].lower()})" for c in d.cast]
    out = ("\n\nCARTOON VIDEO. This whole video happens in one cartoon world with cartoon character(s) on screen: EVERY beat's scene is of type `presenter`"
           " (no photographs as scenes, no clips, no other scene type; a `vector_scene` from the list above, when one is offered, may be used for at most one beat in five as an establishing shot, "
           "never the first or the last beat and never two in a row).\n")
    content = ("{heading (<=48 chars), points: 0 to 4 short strings (<=60 chars each)}  OR  {heading, chart: {labels: 2-5 strings (<=14), values: plain numbers, unit (<=6)}}  OR  "
               "{heading (<=48), image_query (2-6 words describing a real photograph to show on the card)}")
    if d.board:
        content = ("{board: {items: [...]}}: a HAND-DRAWN BOARD beside the character, drawn and written by a marker while the character speaks. Items, in the order they are drawn (4 to 7 per beat, "
                   "at least 2 drawings or written phrases):\n"
                   '      {"id": "<short name>", "draw": "<a simple everyday object in one or two words: sun, cloud, tree, heart, house, battery...>", "zone": "<zone>", "say": "<ONE word of this beat\'s narration>"}\n'
                   '      {"id": "...", "write": "<1 to 3 words, or a number>", "zone": "<zone>" (or "near": "<id>", "side": "below|above|left|right"), "say": "<one word>", "size": "m|l"}\n'
                   '      {"id": "...", "connect": "arrow", "from": "<id>", "to": "<id>", "say": "<one word>"}\n'
                   '      {"id": "...", "mark": "underline|circle|tick", "on": "<id>", "say": "<one word>"}\n'
                   '      {"id": "...", "chart": "bars", "values": [2 to 5 numbers], "labels": ["<short>", ...], "zone": "<zone>", "say": "<one word>"}\n'
                   "    Zones: top-left, top, top-right, left, centre, right, bottom-left, bottom, bottom-right; one drawing or text per zone. `say` is the exact narration word at which the item is "
                   "finished, in the order the narration says them: write the narration so that it NAMES what is drawn. The board is small: few, large things; the title of the beat written on top. "
                   "Never whole sentences on the board")
    out += f"- presenter: {content}. The character stands beside it and says the beat's narration with gestures. Do not write `character`, `cast` or any layout.\n"
    if d.conversation:
        n = conversation_beats(minutes)
        roles = "; ".join(f"{C[c]['name']} {ROLES[i]}" for i, c in enumerate(d.cast))
        out += (f"  THIS VIDEO IS A CONVERSATION between {' and '.join(names)}, all on screen together. In \"voices\" use EXACTLY these speaker ids ({', '.join(d.cast)}) and no narrator; "
                "tag every beat's \"speaker\" with one of them.\n"
                f"  * One beat is ONE line of one character: 8 to 18 words, spoken to the other character(s) and to the viewer, in the first person. Write about {n} beats (this replaces the number of "
                "beats asked for elsewhere; the total number of words stays as asked). The speakers take turns: never the same speaker three beats in a row.\n"
                f"  * Roles: {roles}. They explain the topic TO EACH OTHER: a question, an answer, a follow-up, an example. They use each other's names now and then. Clean handovers: a line ends "
                "on a finished thought, the next one reacts to it (\"Good question!\", \"So that means...\", \"Exactly.\").\n"
                "  * The first beat: one character greets the viewer and asks the video's question. The last beat: one sums up in one line and they say goodbye.\n"
                "  * Content is shown only when a point needs showing: about every second beat. A line that shows nothing new has props {\"talk\": true} (what is already shown stays on screen).\n"
                "  * No stage directions, no \"says\", no narrator. Each character sounds like its role; for children the lines are short and playful.\n")
    else:
        c = C[d.cast[0]]
        out += (f"  The presenter is {c['name']}, a friendly cartoon {c['role']['en'].lower()}, who speaks the whole narration in the first person, warm and direct: one voice, never \"our presenter says\".\n"
                "  * The first beat: the presenter greets the viewer and asks the video's question; `heading` is that question or the title.\n"
                "  * The beats between: what the presenter explains is on the card beside it, 2 to 4 `points` that the narration SAYS in order (each appears as it is said), a small chart for numbers "
                "from the grounding notes, or one picture. Ordinal words (first, second, third), contrasts (but, on the other hand) and pointing words (look, this, here) become gestures: use them.\n"
                "  * The last beat: the presenter sums up and says goodbye; `heading` is the takeaway.\n")
    out += "  Never name a real person as a character. Numbers only from the grounding notes."
    return out


# ----------------------------------------------------------------------------- repair: any scene as the look's own scene type
def _text_of(scene: Dict[str, Any]) -> Tuple[str, List[str]]:
    """(a heading, up to four points) said by any scene: what a text card, a list, a diagram or a picture caption carries."""
    p = scene.get("props") or {}
    heading = ""
    for k in ("heading", "title", "question", "term", "text", "label", "claim", "quote", "alt", "image_query", "clip_query"):
        if isinstance(p.get(k), str) and p[k].strip():
            heading = " ".join(p[k].split())
            break
    raw = next((p[k] for k in ("items", "points", "steps", "events", "nodes", "rows", "labels") if isinstance(p.get(k), list) and p[k]), [])
    points = []
    for x in raw:
        t = str(x.get("label") or x.get("text") or x.get("title") or x.get("name") or "") if isinstance(x, dict) else str(x) if isinstance(x, (str, int, float)) else ""
        if t.strip():
            points.append(" ".join(t.split()))
    return heading, points[:4]


def _card_text(narration: str, n: int = 6) -> str:
    try:
        from . import plan as plan_mod
        return plan_mod.card_text(narration, n)
    except Exception:  # noqa: BLE001
        return " ".join(str(narration or "").split()[:n])


def _chart_of(scene: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    p = scene.get("props") or {}
    labels, values = p.get("labels"), p.get("values")
    if scene.get("type") in ("chart", "bar_race", "comparison_bars") and isinstance(labels, list) and isinstance(values, list) and 2 <= len(labels) == len(values) <= 5 \
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) and v >= 0 for v in values) and max(values) > 0:
        return {"labels": [str(x)[:14] for x in labels], "values": [float(v) for v in values], "unit": str(p.get("unit") or "")[:6]}
    return None


def as_board(scene: Dict[str, Any], narration: str, max_items: int = 20) -> Dict[str, Any]:
    """Any scene as board items (unsanitized): the older text conversions first, a chart as a hand-drawn chart, anything else as its heading written large and its points as a list."""
    made = whiteboard_policy.board_for(scene, narration)
    if made is not None:
        return made["props"]
    heading, points = _text_of(scene)
    chart = _chart_of(scene)
    words = [w.strip(".,;:!?¿¡\"'()").lower() for w in str(narration or "").split()]

    def said(text: str) -> str:   # the narration word a thing is tied to: its own last word when the narration says it
        for w in reversed(str(text).split()):
            if w.strip(".,;:!?").lower() in words:
                return w.strip(".,;:!?")
        return ""

    title = (heading if scene.get("type") not in MEDIA + ("vector_scene",) else "") or _card_text(narration, 5)
    items: List[Dict[str, Any]] = [{"id": "title", "write": title[:40], "zone": "top-row" if (points or chart) else "centre", "size": "l", **({"say": said(title)} if said(title) else {})},
                                   {"id": "line", "mark": "underline", "on": "title", "color": "red"}]
    if chart:
        items.append({"id": "chart", "chart": "bars", "values": chart["values"], "labels": chart["labels"], "zone": "middle-row"})
    elif points:
        items.append({"id": "list", "write": "\n".join(f"{i + 1}. {x[:28]}" for i, x in enumerate(points)), "zone": "middle-row", "size": "m", **({"say": said(points[-1])} if said(points[-1]) else {})})
    elif scene.get("type") in MEDIA + ("vector_scene",):   # a picture that may not stay: the thing it showed, drawn when the library has it by name
        try:
            from .whiteboard import library
            q = str((scene.get("props") or {}).get("image_query") or (scene.get("props") or {}).get("clip_query") or (scene.get("props") or {}).get("alt") or "")
            for w in q.lower().split():
                oid = w if library.has(w) else library.by_name(w)
                if oid:
                    items[0]["zone"] = "top-row"
                    items.append({"id": "pic", "draw": oid, "zone": "centre", "size": "l", **({"say": said(w)} if said(w) else {})})
                    break
        except Exception:  # noqa: BLE001 - the library is an improvement, never a requirement
            pass
    return {"items": items[:max_items]}


def as_presenter(scene: Dict[str, Any], narration: str, board: bool = False) -> Dict[str, Any]:
    """Any scene as the content beside a character (unsanitized presenter props): a list as points, a chart as the small chart, a picture as the picture on the card, a cartoon
    scene as the backdrop behind a heading. With `board` the content is the hand-drawn board."""
    t, p = scene.get("type"), scene.get("props") or {}
    if t == "presenter":
        if not board or p.get("board") or p.get("talk"):
            return dict(p)
        inner = {"type": "chart", "props": {**p["chart"]}} if p.get("chart") else {"type": "bullets", "props": {"heading": p.get("heading", ""), "items": list(p.get("points") or [])}} if p.get("points") \
            else {"type": "title", "props": {"title": p.get("heading") or p.get("image_query") or _card_text(narration)}}
        return {**{k: v for k, v in p.items() if k in ("character", "side", "backdrop", "cast")}, "board": as_board(inner, narration, BOARD_MAX_ITEMS)}
    if board:
        return {"board": as_board(scene, narration, BOARD_MAX_ITEMS), **({"backdrop": p["catalog_id"]} if t == "vector_scene" and p.get("catalog_id") else {})}
    chart = _chart_of(scene)
    heading, points = _text_of(scene)
    if chart:
        return {"heading": (heading or _card_text(narration))[:48], "chart": chart}
    if t in MEDIA:
        q = p.get("image_query") or p.get("clip_query") or (p.get("image_queries") or [""])[0]
        if q:
            return {"heading": str(p.get("alt") or _card_text(narration))[:48], "image_query": str(q)[:80]}
    if t == "vector_scene":
        return {"heading": _card_text(narration)[:48], **({"backdrop": p["catalog_id"]} if p.get("catalog_id") else {})}
    return {"heading": (heading or _card_text(narration))[:48], **({"points": [x[:60] for x in points]} if len(points) >= 2 else {})}


def as_real(scene: Dict[str, Any], beat: Dict[str, Any]) -> Dict[str, Any]:
    """A cartoon scene, a character or a board as an ordinary scene that shows the same thing."""
    t = scene.get("type")
    if t == "vector_scene":
        return vector_policy._replacement(beat)
    if t == "presenter":
        p = scene.get("props") or {}
        if p.get("board") and not (p.get("heading") or p.get("points") or p.get("chart") or p.get("image_query")):
            t, scene = "whiteboard", {"type": "whiteboard", "props": p["board"]}
        else:
            return presenter_policy._fallback_scene(scene)
    if t == "whiteboard":
        lines = [str(it.get("write") or "").split("\n")[0] for it in (scene.get("props") or {}).get("items", []) if it.get("write")]
        if len(lines) >= 3:
            return {"type": "bullets", "props": {"heading": lines[0][:60], "items": [x[:60] for x in lines[1:5]]}}
        return {"type": "title", "props": {"title": (lines[0] if lines else _card_text(str(beat.get("narration") or "")))[:60], "subtitle": ""}}
    return scene


# ----------------------------------------------------------------------------- measuring
def measure(plan: Dict[str, Any], look: Optional[str] = None) -> Dict[str, Any]:
    """How the plan's time is shared between the visual systems, and (with `look`) the share that is in the look."""
    beats = plan.get("beats") or []
    secs: Dict[str, float] = {}
    for b in beats:
        f = family(b.get("scene") or {})
        secs[f] = secs.get(f, 0.0) + beat_seconds(b)
    total = sum(secs.values()) or 1.0
    shares = {k: round(v / total, 3) for k, v in sorted(secs.items())}
    out: Dict[str, Any] = {"seconds": round(total, 1), "families": shares, "systems": len(shares)}
    if look == "whiteboard":
        out["share"] = shares.get("whiteboard", 0.0)
    elif look == "cartoon":
        out["share"] = shares.get("characters", 0.0)
        out["in_world"] = round(shares.get("characters", 0.0) + shares.get("cartoon", 0.0), 3)
    elif look == "real":
        out["share"] = round(shares.get("media", 0.0) + shares.get("graphics", 0.0), 3)
    return out


# ----------------------------------------------------------------------------- enforcement
def _sanitizers() -> Tuple[Callable[[Dict[str, Any]], Dict[str, Any]], Callable[[Dict[str, Any]], Dict[str, Any]]]:
    from .scenes import ELEMENTS

    return ELEMENTS["whiteboard"].sanitize, ELEMENTS["presenter"].sanitize


def _enforce_real(plan: Dict[str, Any], repairs: List[Dict[str, Any]]) -> None:
    for i, b in enumerate(plan.get("beats") or []):
        sc = b.get("scene") or {}
        if family(sc) in ("cartoon", "characters", "whiteboard"):
            b["scene"] = as_real(sc, b)
            repairs.append({"beat": i, "from": sc.get("type"), "to": b["scene"]["type"], "why": "not in a real-footage video"})


def _enforce_whiteboard(plan: Dict[str, Any], repairs: List[Dict[str, Any]], sanitize_board: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
    beats = plan.get("beats") or []
    total = sum(beat_seconds(b) for b in beats) or 1.0
    allowed_n = int(total // PICTURE_EVERY_S)
    budget_s = (1.0 - MIN_SHARE["whiteboard"]) * total - sum(beat_seconds(b) for b in beats if b.get("silent") and (b.get("scene") or {}).get("type") != "whiteboard")   # a pause keeps its picture: that time comes out of the allowance
    kept_n, kept_s, prev_kept = 0, 0.0, False
    for i, b in enumerate(beats):
        sc = b.get("scene") or {}
        t = sc.get("type")
        if t == "whiteboard":
            prev_kept = False
            continue
        why = None
        if t in MEDIA and not b.get("silent"):
            s = beat_seconds(b)
            if i == 0 or i == len(beats) - 1:
                why = "the opening and the closing are boards"
            elif prev_kept:
                why = "never two real pictures in a row"
            elif kept_n >= allowed_n:
                why = f"at most one real picture per {int(PICTURE_EVERY_S)} s"
            elif kept_s + s > budget_s + 1e-6:
                why = f"at least {int(MIN_SHARE['whiteboard'] * 100)} % of the video is drawn"
            else:
                kept_n, kept_s, prev_kept = kept_n + 1, kept_s + s, True
                continue
        else:
            why = "every scene of a whiteboard video is a board"
        prev_kept = False
        if b.get("silent"):
            continue   # a pause shows what it showed: there is no narration to draw to
        try:
            b["scene"] = {"type": "whiteboard", "props": sanitize_board(as_board(sc, str(b.get("narration") or "")))}
        except (ValueError, TypeError):
            b["scene"] = {"type": "whiteboard", "props": sanitize_board({"items": [{"id": "title", "write": _card_text(str(b.get("narration") or ""), 5) or "…", "zone": "centre", "size": "l"}]})}
        repairs.append({"beat": i, "from": t, "to": "whiteboard", "why": why})


def _enforce_cartoon(plan: Dict[str, Any], d: Direction, repairs: List[Dict[str, Any]], sanitize_presenter: Callable[[Dict[str, Any]], Dict[str, Any]], backdrops: List[str]) -> Dict[str, Any]:
    """Every beat a character scene (or, rarely, a full-screen cartoon scene); who speaks which beat, with which voice, where everyone stands, what stays on the card."""
    beats = plan.get("beats") or []
    language = str(plan.get("language") or "en")[:2]
    cast = [c for c in d.cast if c in presenter_policy.CAST] or [presenter_policy.DEFAULT]
    # --- speakers -> characters
    who: Dict[str, str] = {}
    if len(cast) >= 2:
        voices_in = plan.get("voices") if isinstance(plan.get("voices"), dict) else {}
        order = [b.get("speaker") for b in beats if b.get("speaker")]
        speakers = list(dict.fromkeys([s for s in order if s in voices_in and s != "narrator"]))
        free = [c for c in cast if c not in speakers]
        for s in speakers:
            who[s] = s if s in cast else (free.pop(0) if free else cast[len(who) % len(cast)])
        written = len(set(who.values())) >= 2
        last = None
        for i, b in enumerate(beats):   # every line belongs to a character of the cast; a script that was not written as a dialogue takes turns line by line
            c = who.get(b.get("speaker")) if written else None
            if c is None:
                c = cast[i % len(cast)] if not written else next((x for x in cast if x != last), cast[0])
                if not written or b.get("speaker") != c:
                    repairs.append({"beat": i, "from": "narrator" if not b.get("speaker") else str(b.get("speaker")), "to": c, "why": "every line of a conversation is spoken by one of its characters"})
            b["speaker"] = c
            last = c
        taken: List[str] = []
        plan["voices"] = {}
        for c in cast:
            plan["voices"][c] = presenter_policy.voice_for(c, language, taken, plan.get("region"))   # one accent for the whole cast: the viewer's
            taken.append(plan["voices"][c])
    else:
        for b in beats:
            b.pop("speaker", None)
        plan["voices"] = {"narrator": presenter_policy.voice_for(cast[0], language, None, plan.get("region"))}
    # --- every beat in the cartoon world
    total = sum(beat_seconds(b) for b in beats) or 1.0
    only_s, prev_only = 0.0, False
    for i, b in enumerate(beats):
        sc = b.get("scene") or {}
        t = sc.get("type")
        if t == "vector_scene" and not b.get("silent") and 0 < i < len(beats) - 1 and not prev_only and only_s + beat_seconds(b) <= BACKDROP_ONLY_SHARE * total + 1e-6 \
                and (sc.get("props") or {}).get("catalog_id") in backdrops:
            only_s, prev_only = only_s + beat_seconds(b), True
            continue
        prev_only = False
        if b.get("silent"):
            if t != "presenter":
                continue
        props = as_presenter(sc, str(b.get("narration") or ""), d.board)
        speaker = b.get("speaker") if len(cast) >= 2 else cast[0]
        props.update(character=speaker, **({"cast": cast} if len(cast) >= 2 else {}))
        props.pop("side", None)
        try:
            clean = sanitize_presenter(props)
        except (ValueError, TypeError):
            clean = sanitize_presenter({"heading": _card_text(str(b.get("narration") or "")) or "…", "character": speaker, **({"cast": cast} if len(cast) >= 2 else {})})
        b["scene"] = {"type": "presenter", "props": clean}
        if t != "presenter":
            repairs.append({"beat": i, "from": t, "to": "presenter", "why": "every scene of a cartoon video shows its character(s)" if t != "vector_scene" else "a cartoon scene without the character: too many, or first or last"})
        elif d.board and not (sc.get("props") or {}).get("board") and not clean.get("talk"):
            repairs.append({"beat": i, "from": "presenter card", "to": "presenter board", "why": "the content beside the character is the hand-drawn board"})
    # --- one set: a backdrop behind every character scene (the same one for a stretch of beats), and what a line without content keeps showing
    pres = [b for b in beats if (b.get("scene") or {}).get("type") == "presenter"]
    # a conversation stays in ONE place (the characters do not move); a presenter changes the set once, half way, in a video long enough to have two parts
    stretch = (len(pres) + 1) // 2 if len(backdrops) >= 2 and len(cast) == 1 and len(pres) >= 6 else len(pres) or 1
    held: Optional[Dict[str, Any]] = None
    for k, b in enumerate(pres):
        p = b["scene"]["props"]
        if backdrops and not p.get("backdrop"):
            p["backdrop"] = backdrops[min(len(backdrops) - 1, k // stretch)]
        if len(cast) == 1:
            p["side"] = "left"
        content = {key: p[key] for key in ("heading", "points", "chart", "image_query", "alt", "board") if key in p}
        if p.get("talk") and not content:
            if held:
                p.update({**held, "held": True})
            else:
                p["heading"] = str(plan.get("title") or _card_text(str(b.get("narration") or "")))[:48]
        elif content:
            held = content
    if isinstance(plan.get("vector"), dict):   # the cartoon scenes' own record follows what is left after the conversions
        plan["vector"]["used"] = [{"beat": i, "id": b["scene"]["props"].get("catalog_id")} for i, b in enumerate(beats) if (b.get("scene") or {}).get("type") == "vector_scene"]
        plan["vector"]["backdrops"] = sorted({b["scene"]["props"]["backdrop"] for b in pres if b["scene"]["props"].get("backdrop")})
    return {"cast": cast, "voices": dict(plan["voices"]), "backdrop_only_s": round(only_s, 1)}


def enforce(plan: Dict[str, Any], d: Optional[Direction], *, backdrops: Optional[List[str]] = None, sanitize_board: Any = None, sanitize_presenter: Any = None) -> List[str]:
    """After the plan is cleaned and the older policies have run: every scene fits the direction, or is converted. Records `plan["look"]` (the direction, the share of
    the time in the look before and after, every repair). Returns warnings. Never raises: a look is never a reason for a failed video."""
    if d is None:
        return []
    warnings: List[str] = []
    repairs: List[Dict[str, Any]] = []
    before = measure(plan, d.look)
    extra: Dict[str, Any] = {}
    try:
        if sanitize_board is None or sanitize_presenter is None:
            sb, sp = _sanitizers()
            sanitize_board, sanitize_presenter = sanitize_board or sb, sanitize_presenter or sp
        if d.look == "real":
            _enforce_real(plan, repairs)
        elif d.look == "whiteboard":
            _enforce_whiteboard(plan, repairs, sanitize_board)
        else:
            extra = _enforce_cartoon(plan, d, repairs, sanitize_presenter, list(backdrops or []))
            plan["presenter"] = {"decision": "presenter", "reason": "look", "asked": d.by != "auto", "character": extra["cast"][0], "scenes": sum(1 for b in plan.get("beats") or [] if (b.get("scene") or {}).get("type") == "presenter"),
                                 "of": len(plan.get("beats") or []), "cast": {c: c for c in extra["cast"]} if len(extra["cast"]) >= 2 else {"narrator": extra["cast"][0]}, "voices": extra["voices"]}
    except Exception:  # noqa: BLE001 - recorded, never fatal
        logging.exception("ART_DIRECTION_ENFORCE_FAILED")
        warnings.append("look: the repair failed; the plan was left as written")
    after = measure(plan, d.look)
    prior = plan.get("look") if isinstance(plan.get("look"), dict) and plan["look"].get("recipe") == d.recipe else None   # a second pass over the final plan adds to the first record
    if prior:
        repairs = list(prior.get("repairs") or []) + repairs
        before = {"share": prior.get("share_written", before.get("share", 0.0))}
    plan["look"] = {**d.summary(), **({"cast": extra["cast"]} if extra.get("cast") else {}), "share": after.get("share", 0.0), "share_written": before.get("share", 0.0),
                    "min_share": MIN_SHARE[d.look], "ok": after.get("share", 0.0) + 1e-9 >= MIN_SHARE[d.look], "systems": after["systems"], "families": after["families"],
                    "repaired": len(repairs), "repairs": repairs[:60]}
    if repairs and not prior:
        warnings.append(f"look {d.recipe}: {len(repairs)} scene(s) converted to keep the look ({before.get('share', 0.0):.0%} -> {after.get('share', 0.0):.0%} of the time)")
    logging.warning("ART_DIRECTION recipe=%s by=%s chosen=%s share=%s written=%s repaired=%s systems=%s", d.recipe, d.by, d.chosen, plan["look"]["share"], plan["look"]["share_written"], len(repairs), after["systems"])
    return warnings


def record(plan: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The compact `look` of the video record (list and item answers): no repairs list, no measurements beyond the share."""
    lk = plan.get("look")
    if not isinstance(lk, dict):
        return None
    return {k: lk.get(k) for k in ("chosen", "applied", "recipe", "cast", "extras", "why", "by", "share", "repaired", "reason")}


def settle_boards(plan: Dict[str, Any]) -> int:
    """When the narration is final: the hand-drawn board beside a character is tied to the words really said (in the order they are said) and gets an emphasis mark
    where its pen would rest. The whiteboard look's own two steps (whiteboard_policy.retie, keep_busy), one board per beat. -> how many boards."""
    n = 0
    for b in plan.get("beats") or []:
        sc = b.get("scene") or {}
        p = sc.get("props") or {}
        if sc.get("type") != "presenter" or not isinstance(p.get("board"), dict) or p.get("held"):
            continue
        try:
            board = {"items": [dict(it) for it in p["board"]["items"]]}
            whiteboard_policy.retie(board, str(b.get("narration") or ""))
            whiteboard_policy.keep_busy(board, str(b.get("narration") or ""), BOARD_MAX_ITEMS + 3)
            p["board"] = board
            n += 1
        except Exception:  # noqa: BLE001 - the board as written is still a board
            logging.exception("ART_DIRECTION_BOARD_SETTLE_FAILED")
    held: Optional[Dict[str, Any]] = None
    for b in plan.get("beats") or []:   # a line that keeps showing the board before it shows the board as it now is
        sc = b.get("scene") or {}
        p = sc.get("props") or {}
        if sc.get("type") != "presenter":
            continue
        if p.get("held") and p.get("board") and held is not None:
            p["board"] = {"items": [dict(it) for it in held["items"]]}
        elif p.get("board"):
            held = p["board"]
    return n
