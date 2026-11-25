"""The safety policy as code, the per-account record of stops, and the enforcement computed from it (docs/INTAKE_AND_SAFETY.md).

A safety stop stops the video: nothing is charged, the person gets a short neutral message, and the stop is recorded against the account.
Records live in SAFETY_TABLE {user_id (HASH), ts (RANGE, epoch ms), category, severity, source, prompt_hash, excerpt, ttl 90 days}. Nothing else is stored:
never the model's reasoning, never the whole prompt. Enforcement is computed from the records, so there is no counter that can drift:
  * a zero-tolerance category            -> hold at once
  * 3 standard stops within 24 h         -> paused for 24 h after the third
  * 8 standard stops within 30 days      -> hold for review
Staff tooling writes to the admin-only FLAGS_TABLE under the key 'safety:<sub>' (runtime Lambdas may only READ it): `safety_cleared_at` (earlier stops no
longer count) and `safety_hold`. See scripts/safety_admin.py.
"""
import hashlib
import logging
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger()

ZERO, STANDARD = "zero_tolerance", "standard"

# category id -> (severity, what it covers: this text is also the policy list inside the classifier prompt)
CATEGORIES: Dict[str, Any] = {
    "minors_sexual": (ZERO, "sexual content involving minors, in any form"),
    "violence_instructions": (ZERO, "credible instructions or practical help to hurt or kill people, or to plan or carry out an attack or terrorism"),
    "private_targeting": (ZERO, "targeting a private individual for harassment, stalking, intimidation or doxxing (finding or publishing where they live, work or how to reach them)"),
    "sexual_explicit": (STANDARD, "explicit sexual content or pornography"),
    "graphic_gore": (STANDARD, "graphic gore, torture or cruelty as the point of the video"),
    "self_harm_methods": (STANDARD, "methods, encouragement or step-by-step guidance for suicide or self-harm"),
    "weapons_drugs": (STANDARD, "how to make weapons, explosives or illegal drugs, or how to get around laws on them"),
    "hate_harassment": (STANDARD, "hate, dehumanising or harassing content about a protected group (race, religion, sex, orientation, disability, nationality)"),
    "fraud_deception": (STANDARD, "fraud, scams, phishing, forged documents, impersonation, or deepfake-style deception that puts words in the mouth of a real person"),
    "malware": (STANDARD, "malware, ransomware, spyware or help breaking into other people's systems or accounts"),
    "extremist_propaganda": (STANDARD, "propaganda, recruitment or praise for terrorist or violent extremist groups"),
    "nonconsensual_intimate": (STANDARD, "intimate or sexual content about a real person without their consent, including revenge porn"),
    "disinformation": (STANDARD, "election or health disinformation presented as fact"),
    "other_harm": (STANDARD, "anything else clearly intended to seriously harm people"),
}


def severity(category: str) -> str:
    return CATEGORIES.get(category, (STANDARD, ""))[0]


def normalise_category(value: Any) -> Optional[str]:
    """The model's `block` field as a category id, or None when it does not mean a block. A block with an id we do not know is still a block (other_harm)."""
    if value is None or value is False or value is True:
        return "other_harm" if value is True else None
    s = str(value).strip().lower()
    if s in ("", "none", "null", "ok", "false", "no", "safe", "n/a"):
        return None
    return s if s in CATEGORIES else "other_harm"


# ----------------------------------------------------------------------------- what the person reads (short, neutral, kind; never names the rule)
_BLOCKED = {"en": "We can't make this video. If you had something else in mind, try describing a different idea.",
            "es": "No podemos crear este video. Si tenías otra idea en mente, prueba a describir una distinta."}
_PAUSED = {"en": "Video creation is paused on your account for now. Please try again later.",
           "es": "La creación de videos está en pausa en tu cuenta por ahora. Inténtalo de nuevo más tarde."}
_HOLD = {"en": "Video creation is on hold while we take a look at your account. If you think this is a mistake, please contact support.",
         "es": "La creación de videos está detenida mientras revisamos tu cuenta. Si crees que es un error, escribe a soporte."}


def _lang(lang: Optional[str]) -> str:
    return "es" if lang == "es" else "en"


def blocked_message(lang: Optional[str] = None) -> str:
    return _BLOCKED[_lang(lang)]


def guess_language(text: str, preferred: Optional[str] = None) -> str:
    """'es' or 'en', only to pick the wording of a message."""
    if preferred in ("en", "es"):
        return preferred
    try:
        from engine import language
        return language.heuristic(text) or "en"
    except Exception:
        return "en"


# ----------------------------------------------------------------------------- deterministic screen (only when the model call failed)
def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return " ".join(t.split())


_W = r"[a-z']+"
# Narrow on purpose: it only decides when the model could not, so each pattern needs a clearly harmful verb or noun ("how to make a bomb", "child porn"),
# never a bare topic word. Educational and news requests that merely mention a topic must pass. Accents are removed before matching.
_SCREEN: List[tuple] = [
    ("minors_sexual", r"\b(child|children|kid|kids|minor|minors|underage|nina|ninas|nino|ninos|menor|menores|infantil)\b.{0,30}\b(porn\w*|erotic\w*|nude|naked|desnud\w*)\b|"
                      r"\b(porn\w*|pornografia|sexo|sex|nude|desnud\w*)\b.{0,25}\b(of|with|involving|de|con)\s+(a\s+|un\s+|una\s+)?(child|children|kid|kids|minors?|underage|nin[oa]s?|menores?)\b|"
                      r"\b(child|kiddie)\s*porn|\bcsam\b|pornografia infantil|\bsexual\w*\s+(story|scene|content|video|images?|escena|historia|contenido)\b.{0,20}\b(child|kid|minor|underage|nin[oa]|menor)"),
    ("violence_instructions", r"\bhow\s+to\s+(plan|carry out|commit|organi[sz]e)\s+(a\s+|an\s+)?(terror\w*|mass shooting|school shooting|attack on|massacre)|"
                              r"\bhow\s+to\s+(kill|murder|poison|assassinate)\s+(my|a|an|someone|somebody|him|her|them|the)\b|\bhow\s+to\s+get away with murder|"
                              r"\bcomo\s+(planear|planificar|cometer|organizar)\s+(un\s+|una\s+)?(atentado|ataque terrorista|tiroteo|masacre)|\bcomo\s+(matar|asesinar|envenenar)\s+a\b"),
    ("private_targeting", r"\bdox+(ing|ed|x?ing)?\b|\b(find|get|publish|post|leak)\b.{0,25}\b(home address|phone number|address)\b.{0,25}\b(of|for)\s+(my|a|an|this|that)\s+(ex|neighbou?r|coworker|boss|classmate|girlfriend|boyfriend|teacher|stranger|girl|guy|person)\b|"
                          r"\b(harass|stalk|intimidate|threaten|bully)\s+(my|a|an|this|that)\s+(ex|neighbou?r|coworker|boss|classmate|girlfriend|boyfriend|teacher|girl|guy|person)\b|"
                          r"\b(acosar|hostigar|amenazar|acechar)\s+a\s+(mi|un|una|este|esta)\b|\bpublicar\b.{0,25}\b(direccion|telefono)\b.{0,20}\bde\s+(mi|un|una)\s+(ex|vecin[oa]|jefe|jefa|companer[oa])"),
    ("nonconsensual_intimate", r"\brevenge\s+porn\b|\b(leaked|leak)\s+(nudes?|intimate (photos|pictures|video))\b|\bporno de venganza\b|\bfotos intimas de mi ex\b"),
    ("sexual_explicit", r"\b(explicit|hardcore)\s+(sex|porn\w*|sexual)\b|\b(porn|pornographic|xxx)\s+(video|movie|scene|story)\b|\b(video|escena|historia)\s+porno\b|\bescena sexual explicita\b"),
    ("graphic_gore", r"\b(snuff|torture porn)\b|\bgraphic (gore|torture)\b.{0,20}\b(video|scene|for fun|for entertainment)\b"),
    ("self_harm_methods", r"\bhow\s+to\s+(kill myself|commit suicide|hurt myself|cut myself|end my life)\b|\b(best|easiest|painless)\s+(way|method)s?\s+to\s+(die|kill myself|commit suicide)\b|\bcomo\s+(suicidarme|quitarme la vida|hacerme dano)\b|\bformas?\s+de\s+suicidarse\b"),
    ("weapons_drugs", r"\bhow\s+to\s+(make|build|assemble|construct|create)\s+(a\s+|an\s+)?(\w+\s+)?(bomb|explosive|pipe bomb|molotov|ied|nerve agent|bioweapon|ghost gun|silencer)\b|"
                      r"\bbuild\s+(a\s+|an\s+)?(explosive|bomb)\b|\binstructions\s+(to|for)\s+(build|make)\w*\s+(an?\s+)?(explosive|bomb)|"
                      r"\bhow\s+to\s+(make|cook|synthesi[sz]e|produce)\s+(\w+\s+)?(meth|methamphetamine|cocaine|fentanyl|heroin|crack|lsd)\b|"
                      r"\bcomo\s+(hacer|fabricar|construir|armar|cocinar|sintetizar)\s+(una\s+|un\s+)?(\w+\s+)?(bomba|explosivo|metanfetamina|cocaina|fentanilo|heroina)\b"),
    ("hate_harassment", r"\bwhy\s+(jews|muslims|blacks|black people|immigrants|gays|women|asians|mexicans)\s+(are|should)\s+(inferior|vermin|subhuman|animals|scum|dirty|be (killed|exterminated|deported))\b|"
                        r"\bgas the (jews|muslims|blacks)\b|\bpor\s+que\s+los\s+(judios|musulmanes|negros|inmigrantes|gays|mexicanos)\s+(son|deberian)\s+(inferiores|basura|animales|escoria|sucios|exterminados)\b"),
    ("fraud_deception", r"\b(write|create|make|build|generate|draft)\b.{0,15}\b(phishing|scam)\s+(email|page|site|website|message|script|text)\b|\bfake\s+(bank|passport|id|invoice|receipt|diploma)\b.{0,15}\b(that looks real|to fool|to trick)\b|"
                        r"\b(deepfake|fake video)\s+(of|de)\b|\b(crear|hacer|escribir)\b.{0,15}\b(correo|sitio|pagina|mensaje)\s+(de\s+)?(phishing|estafa)\b"),
    ("malware", r"\b(write|create|make|build|code|develop)\b.{0,12}\b(ransomware|keylogger|computer virus|malware|botnet|spyware|trojan)\b|\b(crear|hacer|programar|escribir)\b.{0,12}\b(ransomware|keylogger|virus informatico|malware|botnet|troyano)\b|\bhack into (my|a|someone|somebody|her|his)\b.{0,15}\b(account|phone|wifi|email)\b"),
    ("extremist_propaganda", r"\b(recruitment|propaganda)\s+(video|for|to recruit)\b.{0,25}\b(isis|al.?qaeda|daesh|neo.?nazi|the taliban|boko haram)\b|\breclut\w+\b.{0,20}\b(isis|al.?qaeda|daesh|neonazi)\b"),
]
_SCREEN_RE = [(cat, re.compile(pat)) for cat, pat in _SCREEN]


def screen(text: str) -> Optional[str]:
    """The category id of an obviously harmful request, or None. Deterministic, English and Spanish; used only when the model check could not run."""
    t = _norm(text or "")
    for cat, rx in _SCREEN_RE:
        if rx.search(t):
            return cat
    return None


# ----------------------------------------------------------------------------- the record
HOLD_AFTER_STANDARD_24H, PAUSE_S = 3, 24 * 3600
HOLD_AFTER_STANDARD_30D, WINDOW_30D_S = 8, 30 * 86400
RECORD_TTL_S = 90 * 86400
EXCERPT_CHARS = 160


def enabled() -> bool:
    return bool(os.environ.get("SAFETY_TABLE"))


def _table():
    return boto3.resource("dynamodb").Table(os.environ["SAFETY_TABLE"])


def _flags_key(user_id: str) -> Dict[str, str]:
    return {"user_id": f"safety:{user_id}"}


def _flags(user_id: str) -> Dict[str, Any]:
    if not os.environ.get("FLAGS_TABLE"):
        return {}
    return boto3.resource("dynamodb").Table(os.environ["FLAGS_TABLE"]).get_item(Key=_flags_key(user_id)).get("Item") or {}


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(" ".join((prompt or "").split()).lower().encode("utf-8")).hexdigest()[:32]


@dataclass
class State:
    status: str = "ok"            # ok | paused | hold
    retry_after: int = 0
    reason: str = ""              # for logs and staff only: admin_hold | zero_tolerance | repeated_30d | pause_24h

    @property
    def stopped(self) -> bool:
        return self.status != "ok"

    def body(self, lang: Optional[str] = None) -> Dict[str, Any]:
        msg = (_HOLD if self.status == "hold" else _PAUSED)[_lang(lang)]
        return {"status": "paused", "message": msg, "retry_after": self.retry_after}


def records(user_id: str, *, since_ms: int = 0) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    kw: Dict[str, Any] = {"KeyConditionExpression": Key("user_id").eq(user_id) & Key("ts").gt(int(since_ms)), "ConsistentRead": True}
    while True:
        res = _table().query(**kw)
        out.extend(res.get("Items", []))
        if "LastEvaluatedKey" not in res:
            return out
        kw["ExclusiveStartKey"] = res["LastEvaluatedKey"]


def evaluate(recs: List[Dict[str, Any]], now_s: float) -> State:
    """The enforcement rule on already-filtered records (pure, easy to test)."""
    now_ms = now_s * 1000
    if any(r.get("severity") == ZERO for r in recs):   # a zero-tolerance stop holds the account until staff clear it (or its record expires after 90 days)
        return State("hold", 86400, "zero_tolerance")
    std = sorted(float(r["ts"]) for r in recs if r.get("severity") != ZERO and now_ms - float(r["ts"]) <= WINDOW_30D_S * 1000)
    if len(std) >= HOLD_AFTER_STANDARD_30D:
        return State("hold", 86400, "repeated_30d")
    pause_until = 0.0
    for i in range(len(std) - HOLD_AFTER_STANDARD_24H + 1):
        if std[i + HOLD_AFTER_STANDARD_24H - 1] - std[i] <= PAUSE_S * 1000:
            pause_until = max(pause_until, std[i + HOLD_AFTER_STANDARD_24H - 1] / 1000 + PAUSE_S)
    if pause_until > now_s:
        return State("paused", int(pause_until - now_s) + 1, "pause_24h")
    return State()


def account_state(user_id: str, *, now: Optional[float] = None) -> State:
    """Whether this account may create videos right now. Never raises: when the tables cannot be read the account is treated as fine (and it is logged),
    because a storage hiccup must not stop paying people; the check on the request itself still runs."""
    if not enabled() or not user_id:
        return State()
    now = time.time() if now is None else now
    try:
        flags = _flags(user_id)
        if flags.get("safety_hold"):
            return State("hold", 86400, "admin_hold")
        since = max(int(flags.get("safety_cleared_at") or 0) * 1000, int((now - RECORD_TTL_S) * 1000))
        return evaluate(records(user_id, since_ms=since), now)
    except Exception:
        logger.exception("SAFETY_STATE_UNAVAILABLE user=%s", user_id)
        return State()


def record_block(user_id: str, category: str, source: str, prompt: str, *, now: Optional[float] = None) -> State:
    """Writes the stop and returns the account's state afterwards. Logs account id and category only."""
    now = time.time() if now is None else now
    sev = severity(category)
    item = {"user_id": user_id, "ts": int(now * 1000), "category": category, "severity": sev, "source": source if source in ("model", "fallback") else "model",
            "prompt_hash": prompt_hash(prompt), "excerpt": " ".join((prompt or "").split())[:EXCERPT_CHARS], "ttl": int(now) + RECORD_TTL_S}
    try:
        _table().put_item(Item=item)
    except Exception:
        logger.exception("SAFETY_RECORD_FAILED user=%s category=%s", user_id, category)
        return State()
    logger.warning("SAFETY_STRIKE user=%s category=%s", user_id, category)
    state = account_state(user_id, now=now)
    if state.stopped:
        logger.warning("SAFETY_HOLD user=%s reason=%s", user_id, state.reason)
    return state


# ----------------------------------------------------------------------------- staff (admin credentials only: the runtime roles cannot write the flags table)
def set_hold(user_id: str, on: bool) -> None:
    t = boto3.resource("dynamodb").Table(os.environ["FLAGS_TABLE"])
    if on:
        t.update_item(Key=_flags_key(user_id), UpdateExpression="SET safety_hold = :t, safety_hold_at = :n", ExpressionAttributeValues={":t": True, ":n": int(time.time())})
    else:
        t.update_item(Key=_flags_key(user_id), UpdateExpression="REMOVE safety_hold, safety_hold_at")


def clear(user_id: str) -> None:
    """Earlier stops no longer count; a staff hold is lifted. The records stay (until their 90 days) for review."""
    t = boto3.resource("dynamodb").Table(os.environ["FLAGS_TABLE"])
    t.update_item(Key=_flags_key(user_id), UpdateExpression="SET safety_cleared_at = :n REMOVE safety_hold, safety_hold_at", ExpressionAttributeValues={":n": int(time.time()) + 1})   # +1 s: a stop made in this very second is cleared too
