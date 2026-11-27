"""When may the director use the cartoon vector scenes? (docs/VECTOR_SCENE_POLICY.md)

The cartoon scenes (common/vector_catalog.py, scene type `vector_scene`) are a special style, never the default. This module decides, for one video, whether the
director may be offered them, writes the short prompt block that offers them, and cleans the plan afterwards (only catalog ids, a small share, never two in a row).

Pure of storage and billing, no network except the catalog search, which is injected (`search`) so tests and the eval script run the same code.
Switched off by the server setting VECTOR_SCENES (default OFF): with it off nothing here changes a plan.

Scene props agreed with the element owner: {"catalog_id": "<catalog id>", "seconds": 4-12 (optional, advisory), "motion": "default", "alt": "<fallback caption, optional>"}.
"""
import logging
import os
import re
import threading
from typing import Any, Callable, Dict, List, Optional

STYLES = ("auto", "cartoon", "real")
DEFAULT_STYLE = "auto"

SHARE_AUTO = 0.20        # at most one beat in five when the director chooses by itself
SHARE_KIDS = 0.40        # children's topics: the style fits, so more
SHARE_CARTOON = 0.60     # the person asked for cartoon / illustrated scenes
MIN_BEATS_AUTO = 5       # a video of fewer beats never gets one by itself (kids: 3)
MIN_BEATS_KIDS = 3
MENU_AUTO, MENU_CARTOON = 3, 6   # how many catalog scenes the director is shown
MAX_USES_PER_SCENE = 2
MIN_SECONDS, MAX_SECONDS = 4.0, 12.0

# The kind of video, as the producer (engine/skills.py) already classified it: no extra model call for the clear cases.
KIDS_SKILLS = {"kids-family"}
LIGHT_SKILLS = {"explainer-education", "funny-light", "inspiration-motivation", "health-wellbeing", "travel-places"}
# These guides mean the topic needs real pictures or a serious register: never by itself (news, products, history, biography, true crime, comparisons, code, decks, the person's photos, recaps of a source).
SERIOUS_SKILLS = {"news-explainer", "product-marketing", "history-story", "mystery-true-crime", "biography-profile", "comparison-versus", "coding-tutorial", "deck-explainer", "photo-memories",
                  "recap-summary"}
# These can be either (a physics concept or a telescope's photographs; a habits list or a ranking of real products; blockchain in simple words or quarterly earnings; a cartoon-able
# routine or a recipe that must be filmed): a small model call decides (`classify`). Without one they never qualify, except on a children's topic.
AMBIGUOUS_SKILLS = {"science-wonder", "tutorial-howto", "listicle-ranking", "finance-business"}
MIN_SCORE_SOFT = 0.24   # children's and cartoon-style videos use the scenes as atmosphere: a looser match is fine (the catalog's own floor for real topics is vector_catalog.MIN_SCORE)

CLASSIFY_SYSTEM = (
    "You decide whether a video request suits flat CARTOON illustration scenes (generic illustrated landscapes with gentle motion, no people). Answer ONLY JSON: "
    '{"fit": true|false, "kind": "kids|concept|light|wellness|travel|story|other", "why": "<10 words", "scene": "<3-8 English words: the kind of landscape or place an illustration of this topic would show>"}. '
    "fit is true only when BOTH hold. (1) The video is for children or families, OR explains an everyday or abstract idea in simple general terms (how something works in general, habits, feelings, "
    "money or technology ideas for beginners), OR is a light-hearted, wellness, relaxing-travel or storytelling piece. (2) Nothing in it needs real pictures: it is not about a named real person, "
    "place, brand, product, company, event or set of figures; not news or recent events; not tragedy, war, violence, crime, disease, injury, emergencies or medical, legal or investment advice; "
    "not cooking, repairs, sport technique or any physical how-to that must be seen for real; not a real science subject best shown by photographs or footage (telescope images, wild animals, "
    "anatomy, geology, specific historical or current events), unless it is a simple natural-world topic for children. When unsure, fit is false.")

# What the person may write in the request itself (English and Spanish). "Real" wins over "cartoon" when both appear.
_CARTOON_RE = re.compile(r"\b(cartoons?|cartoony|cartoon[- ]style|illustrated (?:style|video|scenes?|look)|in an illustrated|flat illustrations?|animated (?:cartoon|illustrations?|scenes? in a flat)|"
                         r"dibujos? animados?|caricaturas?|estilo (?:de )?(?:dibujos?|cartoon|animaci[oó]n|ilustrad[oa]|ilustraci[oó]n)|ilustraciones animadas)\b", re.I)
_REAL_RE = re.compile(r"\b(real (?:footage|videos?|photos?|photographs?|pictures|images)|stock (?:footage|videos?)|photo[- ]?realistic|live[- ]action|documentary footage|"
                      r"no (?:cartoons?|animations?|illustrations?)|(?:don'?t|do not|without) (?:use |using |any )?(?:cartoons?|illustrations?|animations?)|"
                      r"im[aá]genes reales|fotos? reales|metraje real|v[ií]deos? reales?|sin (?:dibujos|caricaturas|animaciones|ilustraciones)|no (?:uses|uses|quiero) (?:dibujos|caricaturas))\b", re.I)

Search = Callable[..., List[Dict[str, Any]]]


def enabled() -> bool:
    """Server setting VECTOR_SCENES (default OFF; 1/true/on enables). Never switch it on in a stage before the `vector_scene` element reads `catalog_id` (docs/VECTOR_SCENE_POLICY.md)."""
    return os.environ.get("VECTOR_SCENES", "0").strip().lower() in ("1", "true", "on", "yes")


def clean_style(v: Any) -> str:
    return v if isinstance(v, str) and v in STYLES else DEFAULT_STYLE


def resolve_style(option: Any, prompt: str) -> str:
    """The create option wins; with 'auto' (or none) the person's own words can still ask for one: 'real' beats 'cartoon'."""
    s = clean_style(option)
    if s != "auto":
        return s
    text = prompt or ""
    if _REAL_RE.search(text):
        return "real"
    if _CARTOON_RE.search(text):
        return "cartoon"
    return "auto"


def classify(prompt: str, ask: Callable[[str, str], str]) -> Dict[str, Any]:
    """One small-model call (one retry): does this request suit cartoon scenes, and what setting would illustrate it? Conservative: any doubt or failure is 'no'."""
    import json

    def once() -> Optional[Dict[str, Any]]:
        try:
            raw = ask(CLASSIFY_SYSTEM, f"Video request: {(prompt or '')[:600]}")
            data = json.loads(raw[raw.index("{"): raw.rindex("}") + 1])
        except Exception:
            return None
        return {"fit": data.get("fit") is True, "kind": str(data.get("kind") or "other")[:20], "why": str(data.get("why") or "")[:80],
                "scene": " ".join(str(data.get("scene") or "").split())[:80]}

    out = once() or once()
    if out is None:
        logging.warning("vector policy classification failed twice; treated as not suited")
        return {"fit": False, "kind": "other", "why": "classifier failed", "scene": ""}
    return out


class Policy:
    """The decision for one video."""

    def __init__(self, allowed: bool, style: str, reason: str, *, share: float = 0.0, first_ok: bool = False, candidates: Optional[List[Dict[str, Any]]] = None,
                 aspect: str = "16:9", expected_beats: int = 0, search: Optional[Search] = None, flag: bool = True):
        self.allowed, self.style, self.reason = allowed, style, reason
        self.share, self.first_ok, self.aspect = share, first_ok, aspect
        self.candidates = candidates or []
        self.expected_beats = expected_beats
        self.search = search
        self.flag = flag
        self.judged: Optional[Dict[str, Any]] = None

    def ids(self) -> List[str]:
        return [c["id"] for c in self.candidates]

    def cap(self, n_beats: int) -> int:
        """How many beats of a video of `n_beats` may be cartoon scenes."""
        if not self.allowed or n_beats <= 0:
            return 0
        n = int(self.share * n_beats)
        enough = 1 if self.style == "cartoon" else (MIN_BEATS_KIDS if self.share >= SHARE_KIDS else MIN_BEATS_AUTO)
        return max(1, n) if n_beats >= enough else n

    def summary(self) -> Dict[str, Any]:
        return {"decision": "offered" if self.allowed else "never", "style": self.style, "reason": self.reason, "share": self.share if self.allowed else 0.0,
                "candidates": self.ids(), "aspect": self.aspect, **({"judged": self.judged} if self.judged else {})}

    def prompt_block(self, language: str = "en") -> str:
        """The paragraph added to the director's prompt (empty when the style is not offered)."""
        if not self.allowed or not self.candidates:
            return ""
        menu = "\n".join(f"    - {c['id']}: {c.get('title', c['id'])} ({c.get('category', '')}, {c.get('mood', '')})" for c in self.candidates)
        n = max(1, int(self.share * (self.expected_beats or 8))) if self.expected_beats else 2
        if self.style == "cartoon":
            how = (f"The person asked for an illustrated / cartoon look: use cartoon scenes generously, up to about {int(self.share * 100)} percent of the beats (about {n} in a video this long), "
                   "for every beat whose narration is general, atmospheric or conceptual and where one of the listed scenes fits; photographs, clips, charts and diagrams stay for beats that need them.")
        elif self.share >= SHARE_KIDS:
            how = (f"This is a children's or family topic, so the cartoon look fits: use cartoon scenes for up to about {int(self.share * 100)} percent of the beats (about {n} in a video this long) where one fits.")
        else:
            how = (f"Use them RARELY: at most about {int(self.share * 100)} percent of the beats (about {n} in a video this long, often one or two), only where a listed scene clearly fits the beat. "
                   "When in doubt, use a photograph, a clip, a diagram or text instead; a video with no cartoon scene is perfectly good.")
        return (
            "\n\nCartoon scenes (a special illustrated style, offered for this video only):\n"
            "- vector_scene: {catalog_id: one of the ids listed below, seconds: optional number 4-12}. A flat-colour cartoon landscape with gentle parallax motion (clouds drift, leaves sway), no people and no text, "
            "held for the whole beat.\n"
            f"  {how}\n"
            "  Use one only for a beat whose narration is general, atmospheric or conceptual: setting a place or a mood, opening a chapter, an everyday idea, a transition. Never for a named real person, place, "
            "brand, product or event, never for a number, fact or list that needs a chart or diagram, never for news, tragedy, war, violence, illness, injury or any serious moment. Never two in a row, "
            + ("" if self.first_ok else "never the first beat, ")
            + f"and the same scene at most {MAX_USES_PER_SCENE} times. If no listed scene fits a beat, do not use vector_scene there. Scenes available for this video (use only these ids):\n{menu}"
        )


def _default_search(query: str, aspect: str, k: int) -> List[Dict[str, Any]]:
    from common import vector_catalog as vc
    return vc.search(query, aspect=aspect, k=k)


def _search_query(prompt: str) -> str:
    return " ".join((prompt or "").split())[:300]


def decide(prompt: str, *, options: Optional[Dict[str, Any]] = None, skill_ids: Optional[List[str]] = None, photos: Optional[List[Any]] = None,
           research_mode: str = "encyclopedia", minutes: float = 3.0, expected_beats: Optional[int] = None, search: Optional[Search] = None,
           ask: Optional[Callable[[str, str], str]] = None) -> Policy:
    """May this video be offered cartoon scenes, and how many? Cheap rules first, then the catalog search (a scene must fit the topic)."""
    o = options or {}
    aspect = o.get("aspect") if o.get("aspect") in ("16:9", "9:16", "1:1", "4:5") else "16:9"
    style = resolve_style(o.get("style"), prompt)

    def no(reason: str) -> Policy:
        return Policy(False, style, reason, aspect=aspect, flag=enabled())

    if not enabled():
        return no("flag_off")
    if style == "real":
        return no("style_real")
    if photos:
        return no("user_media")
    if o.get("deck"):
        return no("deck")
    ids = list(skill_ids or [])
    kids = any(s in KIDS_SKILLS for s in ids)
    judged: Optional[Dict[str, Any]] = None
    if style == "auto":
        if research_mode == "web":
            return no("current_events")
        if o.get("platform") == "linkedin":
            return no("platform_linkedin")
        serious = [s for s in ids if s in SERIOUS_SKILLS]
        if serious:
            return no("serious_topic:" + serious[0])
        ambiguous = [s for s in ids if s in AMBIGUOUS_SKILLS]
        if ask is not None:
            judged = classify(prompt, ask)
            if not judged["fit"]:
                return no("not_suited:" + (judged["why"] or "needs real pictures"))
        elif ambiguous and not kids:
            return no("serious_topic:" + ambiguous[0])
        elif not any(s in KIDS_SKILLS or s in LIGHT_SKILLS for s in ids):
            return no("topic_not_suited")
    n_beats = expected_beats if expected_beats is not None else max(1, round(minutes * 60 / 12))
    if style == "auto" and n_beats < (MIN_BEATS_KIDS if kids else MIN_BEATS_AUTO):
        return no("too_short")
    if style == "cartoon" and ask is not None and judged is None:
        judged = classify(prompt, ask)   # only for the setting to search for; a cartoon request is not second-guessed
    run = search or _default_search
    k = MENU_CARTOON if style == "cartoon" else MENU_AUTO
    queries = [_search_query(prompt)] + ([judged["scene"]] if judged and judged.get("scene") else [])
    best: Dict[str, Dict[str, Any]] = {}
    for q in queries:
        found: List[Dict[str, Any]] = []
        for attempt in range(2):   # one retry: an empty answer is usually a throttled embedding call
            try:
                found = run(q, aspect, k) or []
            except Exception:   # the catalog is an improvement, never a requirement
                logging.exception("vector catalog search failed")
                found = []
            if found:
                break
        for c in found:
            if isinstance(c, dict) and c.get("id") and (c["id"] not in best or float(c.get("score", 0)) > float(best[c["id"]].get("score", 0))):
                best[c["id"]] = c
    found = sorted(best.values(), key=lambda c: -float(c.get("score", 0)))
    from common import vector_catalog as vc   # MIN_SCORE lives with the measurement
    floor = MIN_SCORE_SOFT if (kids or style == "cartoon") else vc.MIN_SCORE
    cands = [c for c in found if isinstance(c, dict) and c.get("id") and float(c.get("score", 0)) >= floor][:k]
    if not cands:
        return no("no_catalog_match")
    share = SHARE_CARTOON if style == "cartoon" else (SHARE_KIDS if kids else SHARE_AUTO)
    if style == "cartoon":
        reason = "style_cartoon"
    elif kids:
        reason = "kids"
    else:
        reason = "judged:" + judged["kind"] if judged else "light_topic:" + next(s for s in ids if s in LIGHT_SKILLS)
    pol = Policy(True, style, reason, share=share, first_ok=kids or style == "cartoon", candidates=cands, aspect=aspect, expected_beats=n_beats, search=run)
    pol.judged = judged
    return pol


# ---------------------------------------------------------------- the policy in force while a plan is written and validated
_lock = threading.Lock()
_active: Optional[Policy] = None   # a plain global (not a ContextVar): the long-video writer validates sections on worker threads


class scope:
    """`with vector_policy.scope(policy):` makes the policy the one `sanitize` checks ids against (one video per process at a time, as in a Lambda)."""

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


def active() -> Optional[Policy]:
    return _active


_ID_RE = re.compile(r"^[a-z0-9_]{3,64}$")


def sanitize(props: Dict[str, Any]) -> Dict[str, Any]:
    """The props of a `vector_scene` the director wrote -> clean props, or ValueError (the beat then falls back to an ordinary scene)."""
    pol = active()
    if pol is None or not pol.allowed:
        raise ValueError("vector_scene is not available for this video")
    cid = str((props or {}).get("catalog_id") or "").strip().lower()
    if not _ID_RE.match(cid):
        raise ValueError("vector_scene needs a catalog_id from the list")
    if cid not in pol.ids():
        raise ValueError(f"vector_scene catalog_id {cid!r} is not one of the scenes offered for this video")
    out: Dict[str, Any] = {"catalog_id": cid, "motion": "default"}
    try:
        sec = float((props or {}).get("seconds"))
        if sec == sec:
            out["seconds"] = min(MAX_SECONDS, max(MIN_SECONDS, sec))
    except (TypeError, ValueError):
        pass
    alt = " ".join(str((props or {}).get("alt") or "").split())[:70]
    if alt:
        out["alt"] = alt
    return out


def _replacement(beat: Dict[str, Any]) -> Dict[str, Any]:
    """An ordinary scene for a beat that may not be a cartoon scene: a photograph of what it says when it has a caption, else the card the planner uses everywhere."""
    from . import plan as plan_mod
    alt = str((beat["scene"].get("props") or {}).get("alt") or "").strip()
    if alt and len(alt.split()) >= 2:
        q = " ".join(alt.split()[:6])
        return {"type": "image", "props": {"image_query": q, "alt": alt[:70], "ken_burns": "in"}}
    return plan_mod._fallback_scene(beat.get("narration", ""))


def enforce(plan: Dict[str, Any], policy: Optional[Policy]) -> List[str]:
    """Final pass over the finished plan: with no policy or a refusal no cartoon scene survives; with one: the share cap, never the first beat (unless allowed), never two in a row,
    a scene at most twice. Extra ones become ordinary scenes. Returns warnings and records what happened in plan['vector'] (which videos show cartoon scenes: docs/VECTOR_SCENE_POLICY.md)."""
    beats = plan.get("beats") or []
    warns: List[str] = []
    allowed = policy is not None and policy.allowed
    cap = policy.cap(len(beats)) if allowed else 0
    used: List[Dict[str, Any]] = []
    uses: Dict[str, int] = {}
    prev_vec = False
    for i, b in enumerate(beats):
        sc = b.get("scene") or {}
        if sc.get("type") != "vector_scene":
            prev_vec = False
            continue
        cid = (sc.get("props") or {}).get("catalog_id")
        why = None
        if not allowed:
            why = "not offered for this video"
        elif cid not in policy.ids():
            why = "unknown scene"
        elif i == 0 and not policy.first_ok:
            why = "never the first beat"
        elif prev_vec:
            why = "two in a row"
        elif len(used) >= cap:
            why = f"over the share cap ({cap})"
        elif uses.get(cid, 0) >= MAX_USES_PER_SCENE:
            why = "the same scene a third time"
        elif b.get("silent"):
            why = "silent beat"
        if why:
            b["scene"] = _replacement(b)
            warns.append(f"beat {i}: cartoon scene replaced ({why})")
            prev_vec = False
            continue
        used.append({"beat": i, "id": cid})
        uses[cid] = uses.get(cid, 0) + 1
        prev_vec = True
    if policy is not None and (policy.flag or used):
        info = policy.summary()
        info["used"] = used
        info["beats"] = len(beats)
        info["cap"] = cap
        plan["vector"] = info
        logging.warning("VECTOR_SCENES decision=%s style=%s reason=%s candidates=%s used=%s beats=%s", info["decision"], info["style"], info["reason"], info["candidates"], [u["id"] for u in used], len(beats))
    return warns
