"""Which whiteboard drawings the planner is shown (docs/WHITEBOARD_DRAWING_SEARCH_2026-11-28.md).

Instead of pasting all ids of the library into the planner's prompt (354 and growing; the old menu was cut at 9,000 characters, so newer drawings were silently
missing), the menu is the TOP K drawings for the video's request and research notes plus a small fixed set of generics, grouped by category as before.

HYBRID: a lexical score (BM25 over title, title_es, synonyms, tags, id words, category; accent-insensitive, plural tolerant) and an embedding score (cosine of the
query against the vectors already stored on every library item, `v`: Cohere Embed v4 through common/library_search, never Titan), fused by reciprocal rank.
Without query vectors (Bedrock down, no vectors) the lexical rank alone is used; if anything else fails `menu()` returns None and the caller shows the full list.
Never raises. The query is set once per video by the director (`set_context`), because the prompt block is built before the beats exist.
"""
import logging
import math
import os
import re
import threading
import unicodedata
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
SIDECAR = os.path.join(HERE, "..", "assets", "whiteboard", "library_embeddings.json")
DEFAULT_K = 60
# Generics a board of any subject may want: arrows and marks (symbols), simple people, numbers and money, faces. Chosen from the library's own data (category and use
# in the shipped plans), never by the query. A generic that is not in the library is skipped.
GENERICS = ["check_mark", "cross_mark", "question_mark", "exclamation", "speech_bubble", "thought_bubble", "warning", "spark", "thumbs_up", "thumbs_down",
            "person_standing", "person_thinking", "person_pointing", "person_presenting", "person_question", "person_idea", "teacher", "doctor", "scientist", "worker", "family", "two_talking",
            "face_happy", "face_sad", "face_thinking", "face_surprised",
            "sun", "water_drop", "wind", "fire", "snowflake", "clock", "calendar", "mountain", "river", "earth_globe", "two_gears",
            "calculator", "coin", "coin_stack", "banknote", "percent", "calendar_day", "stopwatch", "light_bulb", "magnifier", "gear", "globe_grid", "balance_seesaw"]
_STOP = set("""the and for with that this from how why what when does work works explain explains video about into your you are was were its their they them can will
 los las del una uno unos unas por para con que como cual cuando porque sobre entre este esta estos estas cada pero sus
 les des une dans pour avec que qui comment pourquoi sur par pas est sont
 der die das und ein eine einen mit von wie warum auf ist sind den dem des zum zur
 gli per con che come perche del della dei delle una uno nel nella sul
 os as dos das uma uns umas com por que como para pelo pela
 het een van voor met hoe waarom dat zijn
 video videos whiteboard pizarra tableau tafel lavagna quadro bord explicacion explication erklarung spiegazione explicacao uitleg""".split())
_lock = threading.Lock()
_cache: Dict[str, Any] = {}
_context: Dict[str, Any] = {"prompt": "", "notes": ""}


def fold(s: str) -> str:
    s = unicodedata.normalize("NFD", str(s or "").lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn")).strip()


def stem(t: str) -> str:
    """Language-agnostic plural/suffix tolerance for en, es, fr, de, it, pt, nl: strip one plural-ish ending, then keep 7 letters."""
    for group in (("ies", "es", "en", "s", "x", "n"), ("e", "i", "a", "o")):
        if len(t) > 4:
            for suf in group:
                if t.endswith(suf) and len(t) - len(suf) >= 4:
                    t = t[: len(t) - len(suf)] + ("y" if suf == "ies" else "")
                    break
    return t[:7]


def tokens(text: str) -> List[str]:
    return [stem(t) for t in fold(text).split() if len(t) >= 3 and t not in _STOP]


def set_context(prompt: str, notes: str = "") -> None:
    """The director calls this before the prompt block is built: the request and the research notes of THIS video."""
    _context["prompt"], _context["notes"] = str(prompt or ""), str(notes or "")


def enabled() -> bool:
    """Server setting WB_SEARCH (1/true/on enables; default OFF until docs/WHITEBOARD_DRAWING_SEARCH_2026-11-28.md's evaluation passes)."""
    return os.environ.get("WB_SEARCH", "0").strip().lower() in ("1", "true", "on", "yes")


def k_setting() -> int:
    try:
        return max(10, min(300, int(os.environ.get("WB_SEARCH_K", DEFAULT_K))))
    except ValueError:
        return DEFAULT_K


# ----------------------------------------------------------------------------- the data
def _sidecar() -> Dict[str, str]:
    import json

    try:
        with open(SIDECAR, encoding="utf-8") as f:
            return {k: v["v"] for k, v in (json.load(f).get("items") or {}).items() if isinstance(v, dict) and v.get("v")}
    except (OSError, ValueError):
        return {}


def item_text(it: Dict[str, Any]) -> str:
    """The text a drawing is embedded from (also used by scripts/whiteboard_embed.py for items that have no vector yet)."""
    return (f"{it.get('title')}. Also: {', '.join(it.get('synonyms_en') or [])}. Tags: {', '.join(it.get('tags') or [])}. "
            f"Español: {it.get('title_es')}, {', '.join(it.get('synonyms_es') or [])}.")[:1800]


def decode(b64: str) -> np.ndarray:
    import base64

    return np.frombuffer(base64.b64decode(b64), dtype="<f2").astype(np.float32)


def vector_of(it: Dict[str, Any], side: Optional[Dict[str, str]] = None) -> Optional[np.ndarray]:
    b = it.get("v") or (side if side is not None else _sidecar()).get(it["id"])
    return decode(b) if b else None


def _prepare(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    side = _sidecar()
    docs: List[Dict[str, float]] = []
    for it in items:
        d: Dict[str, float] = {}
        for text, w in ((it.get("title"), 3.0), (it.get("title_es"), 3.0), (it["id"].replace("_", " "), 2.0), (" ".join(it.get("synonyms_en") or []), 2.0),
                        (" ".join(it.get("synonyms_es") or []), 2.0), (" ".join(it.get("tags") or []), 1.5), (it.get("category"), 0.2)):
            for t in tokens(text or ""):
                d[t] = d.get(t, 0.0) + w
        docs.append(d)
    df: Dict[str, int] = {}
    for d in docs:
        for t in d:
            df[t] = df.get(t, 0) + 1
    vecs = [vector_of(it, side) for it in items]
    have = [i for i, v in enumerate(vecs) if v is not None]
    M = None
    if have:
        M = np.zeros((len(items), len(vecs[have[0]])), np.float32)
        for i in have:
            M[i] = vecs[i] / (np.linalg.norm(vecs[i]) + 1e-9)
    return {"docs": docs, "df": df, "avg": (sum(sum(d.values()) for d in docs) / max(1, len(docs))), "M": M, "n": len(items)}


def _data(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    key = (len(items), items[-1]["id"] if items else "")   # a drawing made on demand is appended to the index: rebuild
    with _lock:
        if _cache.get("key") != key:
            _cache["data"], _cache["key"] = _prepare(items), key
        return _cache["data"]


# ----------------------------------------------------------------------------- scoring
def lexical(query_weights: Dict[str, float], data: Dict[str, Any]) -> np.ndarray:
    """BM25 (k1 1.2, b 0.6) over the weighted-field documents; query terms carry their own weight (the request counts more than the notes)."""
    n, k1, b = data["n"], 1.2, 0.6
    out = np.zeros(n, np.float32)
    for t, qw in query_weights.items():
        df = data["df"].get(t)
        if not df:
            continue
        idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
        for i, d in enumerate(data["docs"]):
            tf = d.get(t)
            if tf:
                out[i] += qw * idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * sum(d.values()) / data["avg"]))
    return out


def _ranks(scores: np.ndarray, valid: Optional[np.ndarray] = None) -> np.ndarray:
    order = np.argsort(-scores, kind="stable")
    r = np.empty(len(scores), np.float32)
    r[order] = np.arange(1, len(scores) + 1)
    return r


def queries(prompt: str, notes: str) -> List[str]:
    """What is embedded: the request, the request with the first lines of the notes, and up to two more passages of the notes (the narration is not written yet)."""
    p = " ".join(str(prompt or "").split())[:300]
    sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+", str(notes or "")) if len(s.strip()) > 25]
    out = [p] if p else []
    if sents:
        out.append((p[:120] + ". " + " ".join(sents[:2]))[:300])
        for chunk in (sents[2:5], sents[5:8]):
            if chunk:
                out.append(" ".join(chunk)[:300])
    return out


def rank(prompt: str, notes: str = "", *, embed: Optional[Callable[[str], Any]] = None, items: Optional[List[Dict[str, Any]]] = None, rrf_k: int = 20) -> Tuple[List[str], Dict[str, Any]]:
    """-> (ids best first, info). Raises nothing the caller must handle except an empty library."""
    if items is None:
        from . import library

        items = library.index()["items"]
    data = _data(items)
    qw: Dict[str, float] = {}
    for t in tokens(prompt):
        qw[t] = qw.get(t, 0.0) + 2.0
    for t in tokens(str(notes or "")[:1500]):
        qw[t] = qw.get(t, 0.0) + 0.5
    lex = lexical(qw, data)
    fused = np.zeros(len(items), np.float32)
    info: Dict[str, Any] = {"lexical": bool(lex.any()), "embedded": 0}
    if lex.any():
        fused += 1.0 / (rrf_k + _ranks(lex)) * np.where(lex > 0, 1.0, 0.0)
    emb = None
    if data["M"] is not None:
        try:
            if embed is None:
                from common import library_search

                embed = library_search.embed_text
            sims = []
            for q in queries(prompt, notes):
                v = np.asarray(embed(q), np.float32)
                sims.append(data["M"] @ (v / (np.linalg.norm(v) + 1e-9)))
            if sims:
                emb = np.max(np.stack(sims), axis=0)       # a drawing close to ANY passage of the video counts
                info["embedded"] = len(sims)
        except Exception as e:  # noqa: BLE001
            logging.warning("WB_SEARCH embedding failed (%s): lexical only", type(e).__name__)
    if emb is not None:
        fused += 1.0 / (rrf_k + _ranks(emb))
    if not fused.any():
        raise ValueError("no signal")
    order = np.argsort(-fused, kind="stable")
    return [items[i]["id"] for i in order], info


def select(prompt: str, notes: str = "", k: Optional[int] = None, **kw: Any) -> Tuple[List[str], Dict[str, Any]]:
    """The ids shown to the planner: the top K, then the generics (not counted in K), in library order within each category by the caller."""
    ranked, info = rank(prompt, notes, **kw)
    k = k or k_setting()
    from . import library

    have = set(ranked)
    top = ranked[:k]
    extra = [g for g in GENERICS if g in have and g not in top]
    info.update({"k": k, "generics_added": len(extra)})
    return top + extra, info


def menu(items_all: List[Dict[str, Any]]) -> Optional[str]:
    """The 'Drawing ids, by group' body for this video, or None (retrieval off, no context, or it failed): the caller then shows the whole library."""
    if not enabled():
        return None
    try:
        prompt, notes = _context["prompt"], _context["notes"]
        if not (prompt or notes).strip():
            return None
        ids, info = select(prompt, notes)
        logging.info("WB_SEARCH shown=%s of %s %s", len(ids), len(items_all), info)
        keep = set(ids)
        cats: Dict[str, List[str]] = {}
        for it in items_all:
            if it["id"] in keep:
                cats.setdefault(it.get("category") or "other", []).append(it["id"])
        return "\n".join(f"    {c}: {', '.join(v)}" for c, v in cats.items())
    except Exception:  # noqa: BLE001 - a video is never failed by search
        logging.exception("WB_SEARCH failed: the full list is shown")
        return None
