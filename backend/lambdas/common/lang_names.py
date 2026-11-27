"""The names of languages, as people write them in the languages the app handles (docs/MULTILINGUAL_CONVERSATIONS_DESIGN_2026-11-27.md section 2.2).

One table for the request check (`common/intake.py`: a request that ASKS for lines in other languages is not "unsupported") and for the engine
(`engine/polyglot.py`: which languages and which characters). Pure, no I/O. Matching is accent-blind and case-blind ("francés", "Frances", "FRANÇAIS").

Languages the app has voices for are the first nine (`engine/voices.READY`); the rest are here only so that a request for them is NOTICED (a "Japanese owl" gets a
note, never a refusal).
"""
import re
import unicodedata
from typing import Dict, List, Optional, Tuple

# code -> the words that name the language (lower case, no accents; the name of the language and its adjective, in en es fr de it pt nl pl fi). Short or ambiguous
# words are left out on purpose ("fins", "polish" as a verb is accepted: the caller only trusts a hit together with other evidence).
NAMES: Dict[str, str] = {
    "en": "english englishes ingles inglesa anglais anglaise englisch englische englischen inglese engels engelse angielski angielsku angielskim englanti englanniksi englannin englantia englanninkielinen",
    "es": "spanish espanol espanola castellano spanisch spanische spanischen espagnol espagnole spagnolo spaans spaanse hiszpanski hiszpansku hiszpanskim espanhol espanja espanjaksi espanjan espanjaa",
    "fr": "french frances francesa francais francaise francese franzosisch franzosische franzosischen frans franse francuski francusku francuskim ranska ranskaksi ranskan ranskaa",
    "de": "german aleman alemana allemand allemande deutsch deutsche deutschen tedesco tedesca duits duitse niemiecki niemiecku niemieckim saksa saksaksi saksan saksaa alemao",
    "it": "italian italiano italiana italien italienne italienisch italienische italienischen italiaans italiaanse wloski wlosku wloskim italiaksi",
    "pt": "portuguese portugues portuguesa portugais portugaise portugiesisch portugiesische portugiesischen portoghese portugees portugese portugalski portugalsku portugaliksi",
    "nl": "dutch holandes holandesa neerlandes neerlandesa neerlandais hollandais niederlandisch niederlandische olandese nederlands nederlandse holenderski holendersku hollanti hollanniksi hollannin",
    "pl": "polish polaco polaca polonais polonaise polnisch polnische polnischen polacco polacca pools poolse polski polsku polskim puola puolaksi puolan",
    "fi": "finnish finlandes finlandesa finnois finnoise finnisch finnische finnischen finlandese finlandzki finlandzku finski suomi suomeksi suomen",
    "ko": "korean coreano coreana coreen coreenne koreanisch koreanische koreaans koreanski koreaksi",
    "ja": "japanese japones japonesa japonais japonaise japanisch japanische giapponese japans japonski japaniksi",
    "zh": "chinese chino chinois chinoise chinesisch chinesische cinese chinees chinski kiina kiinaksi mandarin",
    "ru": "russian ruso rusa russe russisch russische russo russisch russisch rosyjski venaja venajaksi",
    "ar": "arabic arabe arabisch arabische arabo arabski arabiaksi",
    "hi": "hindi",
    "tr": "turkish turco turca turc turque turkisch turkische turco turks turecki turkki turkiksi",
}
ENGLISH_NAME = {"en": "English", "es": "Spanish", "fr": "French", "de": "German", "it": "Italian", "pt": "Portuguese", "nl": "Dutch", "pl": "Polish", "fi": "Finnish",
                "ko": "Korean", "ja": "Japanese", "zh": "Chinese", "ru": "Russian", "ar": "Arabic", "hi": "Hindi", "tr": "Turkish"}
READY = ("en", "es", "fr", "de", "it", "pt", "nl", "pl", "fi")

# words that are a language name only in some languages and a common word in another: they count when the text around them agrees (see `find`)
_WORD_TO_CODE: Dict[str, str] = {}
for _code, _words in NAMES.items():
    for _w in _words.split():
        _WORD_TO_CODE.setdefault(_w, _code)
        if _w.endswith("isch") or _w == "deutsch":   # German adjectives are declined: franzoesischer, deutschen, polnisches ...
            for _end in ("e", "en", "er", "es", "em"):
                _WORD_TO_CODE.setdefault(_w + _end, _code)
_WORD_RE = re.compile(r"[a-z]+")


def fold(text: str) -> str:
    """Lower case, accents removed (eszett and the Polish l-stroke included): the form the table is written in."""
    t = str(text or "").replace("ß", "ss").replace("ł", "l").replace("Ł", "l")
    return "".join(c for c in unicodedata.normalize("NFKD", t.lower()) if not unicodedata.combining(c))


def find(text: str) -> List[Tuple[str, int, int]]:
    """[(code, start, end)] for every language name in the text, in order of appearance, on the folded text (offsets are those of `fold(text)`, which has the
    same length as the text for everything but the eszett)."""
    folded = fold(text)
    out: List[Tuple[str, int, int]] = []
    for m in _WORD_RE.finditer(folded):
        code = _WORD_TO_CODE.get(m.group(0))
        if code:
            out.append((code, m.start(), m.end()))
    return out


def codes(text: str) -> List[str]:
    """The languages named in the text, each once, in order of first appearance."""
    seen: List[str] = []
    for code, _, _ in find(text):
        if code not in seen:
            seen.append(code)
    return seen


# "different languages", "each in their own language", "in several languages" ... in the nine languages: the request is about people speaking several languages
_CUE = re.compile(
    r"\b(?:different|several|many|various|multiple|distinct|own|their own|his own|her own|each (?:its|their|his|her) own|other)\s+(?:languages?|tongues?)\b"
    r"|\b(?:speak(?:s|ing)?|talk(?:s|ing)?|say|says|saying)\s+(?:in\s+)?(?:different|several|many|various|multiple)\s+languages?\b"
    r"|\beach\s+(?:one\s+)?(?:in|with|speaks?|speaking)\s+(?:its|their|his|her|a)\s+(?:own\s+)?(?:language|different language)\b"
    r"|\bin\s+(?:two|three|four|five|2|3|4|5)\s+(?:different\s+)?languages\b"
    r"|\bmultilingual\b|\bbilingual\b|\bpolyglot\b"
    r"|\b(?:diferentes|varios|distintos|muchos|otros|su propio|cada uno su|cada (?:uno|una) en su)\s+idiomas?\b|\bidiomas\s+diferentes\b|\ben\s+(?:dos|tres|cuatro|cinco)\s+idiomas\b|\bcada (?:uno|una) (?:en|habla)\b.{0,20}\bidioma\b"
    r"|\bsu\s+propio\s+idioma\b|\bmultiling[uü]e\b|\bbiling[uü]e\b|\bpol[ií]glota\b"
    r"|\bdiff[eé]rentes\s+langues\b|\bplusieurs\s+langues\b|\bchacun\s+(?:dans|en)\s+sa\s+(?:propre\s+)?langue\b|\bsa\s+propre\s+langue\b|\bmultilingue\b|\bbilingue\b"
    r"|\bverschiedene[nr]?\s+sprachen\b|\bmehrere[nr]?\s+sprachen\b|\bin\s+(?:seiner|ihrer)\s+(?:eigenen\s+)?sprache\b|\bjeder\s+in\s+(?:seiner|ihrer)\b|\bmehrsprachig\b|\bzweisprachig\b"
    r"|\blingue\s+diverse\b|\bdiverse\s+lingue\b|\bdiverse\s+lingue\b|\bpi[uù]\s+lingue\b|\bciascuno\s+nella\s+(?:sua|propria)\s+lingua\b|\bnella\s+(?:sua|propria)\s+lingua\b|\bmultilingue\b"
    r"|\bdiferentes\s+l[ií]nguas\b|\bv[aá]rias\s+l[ií]nguas\b|\bcada\s+um\s+(?:na|em)\s+sua\b|\bsua\s+pr[oó]pria\s+l[ií]ngua\b"
    r"|\bverschillende\s+talen\b|\bmeerdere\s+talen\b|\belk\s+in\s+(?:zijn|haar|eigen)\b|\beigen\s+taal\b|\bmeertalig\b"
    r"|\br[oó][zż]ne\s+j[eę]zyki\b|\bwielu\s+j[eę]zykach\b|\bkażdy\s+w\s+swoim\b|\bwłasnym\s+j[eę]zyku\b|\bwielojęzyczn\w*\b"
    r"|\berilaisilla\s+kielill[aä]\b|\beri\s+kielill[aä]\b|\bomalla\s+kielell[aä]\b|\bmonella\s+kielell[aä]\b|\bmonikielinen\b|\bkukin\s+omalla\b",
    re.I | re.U)


def cue(text: str) -> bool:
    """True when the words say that several languages are spoken ("different languages", "each in their own language"), whatever languages are named."""
    t = str(text or "")
    return bool(_CUE.search(t) or _CUE.search(fold(t)))


def name_of(code: str, native: bool = False) -> str:
    if native:
        try:
            from engine import voices   # the engine package is beside this one in every deployment that has voices; without it the English name is used
            return voices.NATIVE.get(code) or ENGLISH_NAME.get(code, code)
        except Exception:   # noqa: BLE001
            pass
    return ENGLISH_NAME.get(code, code)


def has_voice(code: Optional[str]) -> bool:
    return code in READY
