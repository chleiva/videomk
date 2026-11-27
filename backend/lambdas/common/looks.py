"""The looks a video can have on THIS stage, and what happens to a look the person asked for (docs/CREATE_API.md "Looks", docs/INTAKE_AND_SAFETY.md).

One place for three users, so they can never disagree again:
  * capabilities (`lambdas/capabilities_api.looks`) lists the looks from `flags()`;
  * the request check (`common/intake.py`) tells the small model what the product can make from `prompt_block()`, so it never claims "the app cannot make cartoons";
  * `resolve()` turns the person's wish (the create option `style`, or plain words: "animated characters", "dibujos animados", "con personajes") into the look the video
    will get and, when the wish cannot be met as asked, a short friendly note that says what was adapted and why.

A LOOK OR STYLE WISH IS NEVER A REASON TO REFUSE A VIDEO. The video is made in the closest look this stage has and the note says so.
Pure: the server switches are read from the environment (the same ones the engine functions get), nothing else is touched.
"""
import os
import re
from typing import Any, Dict, List, Optional

from common import i18n

# server switch -> our name for it (backend_stack.py sets the same variables on the engine, capabilities, request-check and launcher functions)
SWITCHES = {"cartoon": "VECTOR_SCENES", "whiteboard": "WHITEBOARD", "bg_animated": "BG_ANIMATED", "bg_loops": "BG_LOOPS", "presenters": "PRESENTERS"}
STYLES = ("auto", "cartoon", "real", "whiteboard")


def _on(name: str) -> bool:
    return os.environ.get(name, "0").strip().lower() in ("1", "true", "on", "yes")


def flags() -> Dict[str, bool]:
    """Which looks are switched on here: {cartoon, whiteboard, bg_animated, bg_loops, presenters}."""
    return {k: _on(v) for k, v in SWITCHES.items()}


# ----------------------------------------------------------------------------- what the request check is told
def prompt_block(f: Optional[Dict[str, bool]] = None) -> str:
    """The paragraph of the request-check prompt that lists the looks of this stage. Built from the switches, so it is right on QA and on production."""
    f = flags() if f is None else f
    have = ["real photographs and stock video clips", "drawn charts, maps, diagrams, lists, titles and text"]
    if f.get("cartoon"):
        have.append("illustrated CARTOON scenes (flat-colour animated settings with gentle motion; used for children's, light and simple topics, not for news or real people and places)")
    if f.get("whiteboard"):
        have.append("a hand-drawn WHITEBOARD look (the whole video drawn and written by a marker; for explaining how something works)")
    if f.get("bg_animated") or f.get("bg_loops"):
        have.append("ANIMATED" + (" and 3D" if f.get("bg_loops") else "") + " moving backgrounds behind text scenes")
    if f.get("presenters"):
        have.append("animated PRESENTER CHARACTERS (a cartoon teacher, engineer, doctor or chef, or an animal: a fox, an owl professor or a bear, who stands beside the content and speaks the narration with gestures; "
                    "for children's, fun and tutorial videos, not for serious news or the person's own photos)")
    soon = [name for key, name in (("presenters", "talking animated characters"), ("cartoon", "cartoon scenes"), ("whiteboard", "the whiteboard look")) if not f.get(key)]
    return ("LOOKS AND STYLES. The app can make: " + "; ".join(have) + "."
            + (" Not available here yet: " + ", ".join(soon) + "." if soon else "")
            + " A wish about the LOOK or STYLE of the video (cartoon, cartoons, animated, animation, animated characters or animals, a presenter, a mascot, illustrated, drawn, whiteboard, 3D, anime, comic, "
            "pixel art, a colour or mood, \"dibujos animados\", \"personajes\", \"caricaturas\", \"animado\") is NEVER a reason for \"unsupported\" and never a reason to ask a question, whether or not the app "
            "has that look and whether or not it suits the topic: the app makes the video in the closest look it has and tells the person. For such a request keep \"unsupported\" null and report the wish in "
            "\"look\". Never say the app cannot make cartoons, animations or characters.")


# ----------------------------------------------------------------------------- what the person asked for, in plain words (English and Spanish)
# The same words the engine reads (engine/vector_policy.py, engine/whiteboard_policy.py), kept here so the request-check function needs nothing from the engine package.
_CARTOON_RE = re.compile(r"\b(cartoons?|cartoony|cartoon[- ]style|illustrated (?:style|video|scenes?|look)|in an illustrated|flat illustrations?|animated (?:cartoon|illustrations?|scenes? in a flat)|"
                         r"dibujos? animados?|caricaturas?|estilo (?:de )?(?:dibujos?|cartoon|animaci[oó]n|ilustrad[oa]|ilustraci[oó]n)|ilustraciones animadas)\b", re.I)
_REAL_RE = re.compile(r"\b(real (?:footage|videos?|photos?|photographs?|pictures|images)|stock (?:footage|videos?)|photo[- ]?realistic|live[- ]action|documentary footage|"
                      r"no (?:cartoons?|animations?|illustrations?)|(?:don'?t|do not|without) (?:use |using |any )?(?:cartoons?|illustrations?|animations?)|"
                      r"im[aá]genes reales|fotos? reales|metraje real|v[ií]deos? reales?|sin (?:dibujos|caricaturas|animaciones|ilustraciones)|no (?:uses|quiero) (?:dibujos|caricaturas))\b", re.I)
_WHITEBOARD_RE = re.compile(r"\b(white\s?board(?:[- ]style| video| animation| look| explainer)?|draw(?:n)? (?:it |this )?on a (?:white\s?board|board)|hand[- ]drawn (?:video|style|explainer|animation|look)|"
                            r"marker (?:drawings?|sketch(?:es)?)|doodle (?:video|style)|sketch(?:ed)? (?:video|style|explainer)|"
                            r"(?:estilo|tipo|en|como|sobre una?) (?:de )?pizarr[aó]n?(?: blanc[ao])?|pizarra blanca|v[ií]deo de pizarra|dibujad[oa] a mano|dibujos? a mano|estilo (?:de )?boceto)\b", re.I)
_ANIMAL = r"(?:animals?|fox|owl|bear|cat|dog|parrot|turtle|rabbit|bunny|penguin|monkey|lion|animal(?:es)?|zorr[oa]|b[uú]ho|lechuza|os[oa]|gat[oa]|perr[oa]|loro|tortuga|conej[oa]|ping[uü]ino|mono|le[oó]n)"
# A wish for someone ON SCREEN who presents: characters, a presenter, a mascot, animals that explain. "A story with three characters" (a dialogue: a number) is not a look wish.
_CHARACTERS_RE = re.compile(
    r"\b((?:animated|cartoon|talking|drawn) (?:[a-z]+ )?(?:characters?|people|persons?|avatars?|mascots?|presenters?|hosts?|" + _ANIMAL + r")"
    r"|characters? (?:explain(?:ing|s)?|present(?:ing|s)?|talk(?:ing|s)?|tell(?:ing|s)?|narrat(?:ing|es?)|host(?:ing|s)?|who (?:explains?|talks?|presents?))"
    r"|(?:with|using|featuring|by) (?:an? |some |the )?(?:(?:animated|cartoon|talking|friendly|funny|cute) )?(?:presenters?|hosts?|mascots?|avatars?|characters?)"
    r"|(?:explained|presented|narrated|hosted|told) by (?:an? |the |some |two )?(?:(?:animated|cartoon|talking|friendly|funny|cute|wise|little) )*(?:characters?|presenters?|mascots?|avatars?|teacher|engineer|doctor|chef|" + _ANIMAL + r")"
    r"|" + _ANIMAL + r" (?:explain(?:ing|s)?|present(?:ing|s)?|host(?:ing|s)?) "
    r"|personajes? (?:animad[oa]s?|de dibujos|que (?:explican?|hablan?|presentan?|cuentan?)|explicando|hablando|presentando)"
    r"|(?:con|usando) (?:una? |unos |unas |el |la |los )?(?:presentador(?:a|es)?|personajes?|mascotas?|avatar(?:es)?|animales (?:animados|que hablan))"
    r"|(?:explicad[oa]s?|presentad[oa]s?|narrad[oa]s?|contad[oa]s?) por (?:una? |el |la |unos |dos )?(?:personajes?|presentador(?:a|es)?|mascotas?|profesor(?:a)?|maestr[oa]|ingenier[oa]|doctor(?:a)?|m[eé]dic[oa]|chef|cociner[oa]|" + _ANIMAL + r")"
    r"|" + _ANIMAL + r" (?:animad[oa]s?|que (?:explican?|presentan?)|explicando|presentando)"
    r"|animales animados|mu[ñn]ecos? animados?)\b", re.I)
_NO_CHARACTERS_RE = re.compile(r"\b(no (?:presenters?|characters?|hosts?|mascots?)|without (?:an? |any )?(?:presenters?|characters?|hosts?|mascots?)|sin (?:presentador(?:a|es)?|personajes?|mascotas?))\b", re.I)
# A request about what is happening now or about real events: the looks that are a special style (cartoon scenes, whiteboard, presenters) are not used for these.
_NEWS_RE = re.compile(r"\b(news|headlines?|breaking|current events?|what(?:'s| is| has) happen(?:ing|ed)|this week'?s?|latest (?:on|about|in|from)|"
                      r"noticias?|titulares|actualidad|[uú]ltima hora|qu[eé] (?:est[aá] pasando|ha pasado|pas[oó])|esta semana)\b", re.I)


def wishes(prompt: Any) -> List[str]:
    """The look wishes written in the request, in a fixed order: any of 'real', 'whiteboard', 'cartoon', 'characters'."""
    text = " ".join(str(prompt or "").split())
    out = []
    if _REAL_RE.search(text):
        out.append("real")
    if _WHITEBOARD_RE.search(text) and "real" not in out:
        out.append("whiteboard")
    if _CARTOON_RE.search(text) and "real" not in out:
        out.append("cartoon")
    if (_CHARACTERS_RE.search(text) or _animal_at_the_end(text)) and not _NO_CHARACTERS_RE.search(text):
        out.append("characters")
    return out


# Which presenter the words name ("explained by a fox", "con una doctora"): character id -> the words for it. Read only where the request asks for someone on screen.
PRESENTER_WORDS = {"fox": r"fox|zorr[oa]", "owl": r"owl|b[uú]ho|lechuza", "bear": r"bear|os[oa]|osit[oa]", "ines": r"teacher|professor|profesor(?:a)?|maestr[oa]", "david": r"engineer|programmer|developer|ingenier[oa]|programador(?:a)?",
                   "priya": r"doctor(?:a)?|scientist|m[eé]dic[oa]|cient[ií]fic[oa]", "mateo": r"chef|cook|cociner[oa]"}
_BY_RE = (r"(?:(?:explained|presented|narrated|hosted|told) by|(?:with|featuring) (?:an? |the )?(?:animated |cartoon |friendly |talking |funny |cute |wise |little )*(?=\w+ (?:as )?(?:the )?(?:presenter|host|character|mascot))"
          r"|(?:explicad[oa]s?|presentad[oa]s?|narrad[oa]s?|contad[oa]s?) por|con (?:una? |el |la )?(?=\w+ (?:como )?(?:presentador|presentadora|personaje|mascota|animad)))"
          r"\s*(?:an? |the |una? |el |la )?(?:(?:animated|cartoon|talking|friendly|funny|cute|wise|little) )*")


# An animal of the cast named at the end of the request ("Why the sky is blue, with an owl", "Los planetas, con un búho"): the animal presents. In the middle of a
# sentence ("a story with an owl who learns to fly") it is the subject of the video, not a wish.
_ANIMAL_CAST = ("fox", "owl", "bear")
_WITH_ANIMAL_RE = r"(?:with|by|con|por) (?:an? |the |una? |el |la )(?:(?:friendly|funny|cute|wise|little|talking|cartoon|animated) )*(?:{words})(?: (?:animad[oa]|simp[aá]tic[oa]|sabi[oa]))?\s*[.!]?\s*$"


def _animal_at_the_end(text: str) -> Optional[str]:
    for cid in _ANIMAL_CAST:
        if re.search(_WITH_ANIMAL_RE.format(words=PRESENTER_WORDS[cid]), text, re.I):
            return cid
    return None


def presenter_wish(prompt: Any) -> Optional[str]:
    """What the request says about a presenter: 'none' ("no presenter", "sin presentador"), a character id when the words name one ("explained by a fox",
    "explicado por un zorro", "with a doctor as the presenter"), 'any' for a presenter or characters in general, None when it says nothing."""
    text = " ".join(str(prompt or "").split())
    if _NO_CHARACTERS_RE.search(text):
        return "none"
    for cid, words in PRESENTER_WORDS.items():
        if re.search(_BY_RE + r"(?:" + words + r")\b", text, re.I):
            return cid
    return _animal_at_the_end(text) or ("any" if _CHARACTERS_RE.search(text) else None)


def about_news(prompt: Any) -> bool:
    return bool(_NEWS_RE.search(str(prompt or "")))


_ES_WORDS = set("el la los las un una unos unas de del que con por para sobre como cómo qué es son y o hoy sea mi mis su sus al se lo más muy noticias video vídeo explicado explicada explicados explicadas "
                "explica quiero hazme haz divertido personajes dibujos animados animales niños".split())
_EN_WORDS = set("the a an of that with by for about how what why is are and or today my your to it this make made explain explained explaining want fun characters cartoon cartoons animated animals kids news".split())


def guess_lang(prompt: Any, preferred: Any = None) -> str:
    """'es' or 'en' for the wording of a note. A short request ("Las noticias de hoy en dibujos animados") has too few words for the engine's strict detector, which then
    says nothing; here the question is only which of the two languages a line is written in, so plain common-word counts decide (English on a tie)."""
    if preferred in ("en", "es"):
        return preferred
    text = str(prompt or "").lower()
    words = re.findall(r"[a-záéíóúüñ]+", text)
    es = sum(w in _ES_WORDS for w in words) + 3 * len(re.findall(r"[¿¡ñ]", text))
    en = sum(w in _EN_WORDS for w in words)
    return "es" if es > en else "en"


def clean_model_look(raw: Any) -> Optional[Dict[str, Any]]:
    """The request check's own reading of the wish: {"wish": cartoon|characters|whiteboard|real|other, "serious": bool}, or None. Nothing else is kept."""
    if not isinstance(raw, dict) or raw.get("wish") not in ("cartoon", "characters", "whiteboard", "real", "other"):
        return None
    return {"wish": raw["wish"], "serious": raw.get("serious") is True}


def _base(f: Dict[str, bool], cartoon: bool = False) -> str:
    """The closest look the video really gets, as an i18n key suffix."""
    if cartoon:
        return "cartoon"
    return "animated" if f.get("bg_animated") or f.get("bg_loops") else "plain"


def resolve(prompt: Any, option: Any = None, lang: Optional[str] = None, *, model: Optional[Dict[str, Any]] = None, media_count: int = 0,
            f: Optional[Dict[str, bool]] = None, presenter: Any = None) -> Dict[str, Any]:
    """What the video will look like and what to tell the person.

    -> {"style": auto|cartoon|real|whiteboard (what `generate` will resolve to on this stage), "asked": [wishes], "presenter": bool (a presenter will be offered to the
        director), "note": a short localized sentence when a wish was adapted, else None, "adapted": [the wishes that could not be met as asked]}
    `option` is the create option `style`; `model` the request check's reading (`clean_model_look`), which adds to the words, never removes. The engine makes the final
    decision per video (engine/vector_policy.py, engine/whiteboard_policy.py): this is the same reading of the same words and switches, made before the video starts.
    """
    f = flags() if f is None else f
    asked = wishes(prompt)
    if option in ("cartoon", "real", "whiteboard"):   # the option wins over the words (as in the engine)
        asked = [option] + [w for w in asked if w == "characters"]
    if model and model["wish"] in ("cartoon", "characters", "whiteboard") and model["wish"] not in asked and "real" not in asked:
        asked.append(model["wish"])
    if presenter == "none":   # the create option `presenter` wins over the words (docs/PRESENTERS.md)
        asked = [w for w in asked if w != "characters"]
    elif isinstance(presenter, str) and presenter not in ("", "auto") and "characters" not in asked:
        asked.append("characters")
    serious = about_news(prompt) or bool(model and model.get("serious"))
    photos = media_count > 0
    style, adapted, note, presenter = "auto", [], None, False

    def say(key: str, base: str) -> str:
        return i18n.t(f"look.note.{key}", lang, base=i18n.t(f"look.base.{base}", lang))

    if "real" in asked:
        style = "real"
    elif "whiteboard" in asked:
        if f.get("whiteboard") and not serious and not photos:
            style = "whiteboard"
        else:
            adapted.append("whiteboard")
            note = say("whiteboard_soon" if not f.get("whiteboard") else "whiteboard_photos" if photos else "whiteboard_serious", _base(f))
    elif "cartoon" in asked:
        if f.get("cartoon") and not serious and not photos:
            style = "cartoon"
        else:
            adapted.append("cartoon")
            note = say("cartoon_soon" if not f.get("cartoon") else "cartoon_photos" if photos else "cartoon_serious", _base(f))
    if "characters" in asked:
        if f.get("presenters") and not serious and not photos and style != "whiteboard":
            presenter = True
        else:
            adapted.append("characters")
            key = "characters_soon" if not f.get("presenters") else "characters_photos" if photos else "characters_whiteboard" if style == "whiteboard" else "characters_serious"
            base = "whiteboard" if style == "whiteboard" else _base(f, cartoon=style == "cartoon")
            note = say(key, base)   # the characters sentence wins: it already names the look the video gets
    return {"style": style, "asked": asked, "presenter": presenter, "note": note, "adapted": adapted}


# ----------------------------------------------------------------------------- the refusal copy is the product speaking, never "I"
_FIRST_PERSON_RE = re.compile(r"(?<![\w'’])I(?:['’](?:m|ll|ve|d))?(?![\w])|(?i:\b(?:puedo|podr[ií]a|me temo|lo siento)\b|\byo\b)")
_LOOK_WORDS_RE = re.compile(r"cartoon|animat|character|illustrat|artwork|drawing|drawn|whiteboard|AI[- ]?(?:generated )?(?:image|art|visual)|generate (?:new )?(?:images|artwork|visuals)|mascot|presenter|avatar|anime|3d\b|"
                            r"dibujo|caricatura|animad|animaci|personaje|ilustra|pizarra|im[aá]genes (?:nuevas|con ia|generadas)|presentador|mascota", re.I)


def first_person(text: Any) -> bool:
    """True when a sentence speaks as "I" / "yo" (the product never does: it is "VideoMK can't ...")."""
    return bool(_FIRST_PERSON_RE.search(str(text or "")))


def about_a_look(text: Any) -> bool:
    """True when a "not supported" sentence is really about the look of the video (so it must not stop the video)."""
    return bool(_LOOK_WORDS_RE.search(str(text or "")))
