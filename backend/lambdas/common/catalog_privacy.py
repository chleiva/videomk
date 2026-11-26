"""What may be written to the catalog demand table (docs/IMAGE_CATALOG.md, "Feedback loop").

Only a GENERIC search phrase is ever kept: never the user's prompt, narration, photos or id. `generic_phrase()` returns the cleaned phrase or None when the phrase
looks personal; it is deterministic (no model, no network) and errs on the side of dropping. `video_ref()` is a salted one-way hash so the table can count distinct
videos without being able to name them. Retention is 12 months (the table's TTL).
"""
import hashlib
import hmac
import re
import unicodedata
from typing import Optional

MAX_WORDS = 10
MAX_CHARS = 80

_EMAIL = re.compile(r"[^\s@]+@[^\s@]+")
_URL = re.compile(r"(https?://|www\.|\.com\b|\.net\b|\.org\b|\.es\b|\.io\b)", re.I)
_DIGITS = re.compile(r"\d")
_ADDRESS = re.compile(r"\b(street|st\.|avenue|ave\.?|road|rd\.?|lane|drive|calle|avenida|avda|carrer|via|piazza|plaza|apt|apartment|piso|zip|postcode|postal)\b", re.I)
# first person and family: "my son", "our house", "mi hijo", "nuestra casa", "my wife's"
_POSSESSIVE = re.compile(r"\b(my|mine|our|ours|mi|mis|nuestro|nuestra|nuestros|nuestras|mon|ma|mes|notre|nos|mio|mia|miei|nostro|nostra|meu|minha)\b", re.I)
_FAMILY = re.compile(r"\b(wife|husband|son|daughter|kid|kids|baby|boyfriend|girlfriend|fianc[eé]e?|partner|mom|mum|mother|dad|father|brother|sister|grandma|grandpa|granny|nan|nanny|gran|grandmother|grandfather|"
                     r"uncle|aunt|cousin|nephew|niece|friend|neighbou?r|boss|colleague|coworker|"
                     r"esposa|esposo|marido|mujer|hijo|hija|hijos|beb[eé]|novio|novia|madre|padre|mam[aá]|pap[aá]|hermano|hermana|abuelo|abuela|t[ií]o|t[ií]a|primo|prima|amigo|amiga|vecino|jefe|difunto|"
                     r"moglie|marito|figlio|figlia|fratello|sorella|nonno|nonna|femme|mari|fils|fille|fr[eè]re|s[oœ]ur)\b", re.I)
_APOSTROPHE_S = re.compile(r"\w['\u2019]s\b", re.I)   # "granny's flat", "Maria's party": somebody's own thing (a few landmarks, "queen's house", are lost on purpose)
_TITLES = re.compile(r"\b(mr|mrs|ms|miss|dr|sr|sra|se[nñ]or|se[nñ]ora|don|do[nñ]a|signor|signora|monsieur|madame|uncle|aunt|tio|tia)\.?\s+[A-Z]", re.I)
_IN_MY = re.compile(r"\b(at|in|de|en)\s+(home|casa)\b", re.I)

# first names (en/es/it/fr/pt, common): a phrase naming a person is never generic
_NAMES = set("""james john robert michael william david richard joseph thomas charles chris christopher daniel matthew anthony donald steven paul andrew joshua kenneth kevin brian george timothy ronald jason edward jeffrey ryan jacob gary nicholas eric jonathan stephen larry justin scott brandon benjamin samuel gregory alexander patrick raymond dennis jerry tyler aaron jose adam nathan henry zachary douglas peter noah ethan jeremy walter christian keith roger terry austin sean gerald carl harold dylan arthur lawrence jesse bryan bruce gabriel joe logan albert willie alan eugene russell vincent philip johnny bradley
mary patricia jennifer linda elizabeth barbara susan jessica sarah karen lisa nancy betty margaret sandra ashley kimberly emily donna michelle carol amanda dorothy melissa deborah stephanie rebecca sharon laura cynthia kathleen amy angela shirley anna brenda pamela emma nicole helen samantha katherine christine debra rachel carolyn janet catherine maria heather diane ruth julie olivia joyce virginia kelly lauren christina joan evelyn judith megan andrea cheryl hannah jacqueline martha gloria teresa ann sara madison frances kathryn janice abigail alice julia judy sophia denise doris marilyn danielle beverly isabella theresa diana natalie brittany charlotte marie kayla alexis lori
carlos juan luis miguel pedro pablo jorge javier antonio francisco manuel jesus alberto fernando sergio rafael ricardo alejandro diego marcos andres raul enrique roberto santiago mateo sebastian lucas nicolas emanuele marco giuseppe giovanni luca matteo francesco paolo stefano alessandro lorenzo davide
carmen lucia laura marta paula sofia elena isabel pilar dolores cristina beatriz patricia ana amore giulia chiara francesca elisa sara valentina martina alessia silvia federica
pierre jean jacques michel louis hugo leo lea camille chloe manon ines""".split())
_SPECIAL_NAME = re.compile(r"\b(named|called|llamad[oa]|se llama|de nombre)\b", re.I)


def _plain(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def personal_reason(phrase: str) -> Optional[str]:
    """Why the phrase may not be kept (a short code), or None when it is fine."""
    p = (phrase or "").strip()
    if not p:
        return "empty"
    if len(p) > MAX_CHARS or len(p.split()) > MAX_WORDS:
        return "too long to be a generic phrase"
    if _EMAIL.search(p):
        return "email"
    if _URL.search(p):
        return "url"
    if _DIGITS.search(p):
        return "digits (phone, address, date, year)"   # also drops "1920s" and "4k": a small, deliberate loss
    if _ADDRESS.search(p):
        return "address"
    if _APOSTROPHE_S.search(p):
        return "possessive"
    if _POSSESSIVE.search(p):
        return "first person"
    if _FAMILY.search(p):
        return "family or acquaintance"
    if _TITLES.search(p) or _SPECIAL_NAME.search(p):
        return "name"
    if _IN_MY.search(p):
        return "private place"
    for w in re.findall(r"[a-zA-ZÀ-ÿ]+", _plain(p).lower()):
        if w in _NAMES:
            return "first name"
    return None


def generic_phrase(phrase: str) -> Optional[str]:
    """The phrase lower-cased and trimmed when it is generic, else None."""
    p = re.sub(r"\s+", " ", (phrase or "").strip())
    if personal_reason(p):
        return None
    return p.lower()


def video_ref(video_id: str, salt: str) -> str:
    """A salted one-way reference to a video (HMAC-SHA256, 16 hex chars). Without the salt (kept in SSM) it cannot be reversed or linked to a user or video."""
    if not salt:
        raise ValueError("a salt is required")
    return hmac.new(salt.encode(), str(video_id).encode(), hashlib.sha256).hexdigest()[:16]
