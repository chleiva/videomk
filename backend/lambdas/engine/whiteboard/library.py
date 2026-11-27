"""The whiteboard object library at video time: the id list and titles ship with the code (assets/whiteboard/library_index.json, built by
scripts/whiteboard_proto/lib_index.py), the drawing packages are read from the catalog bucket under `w/<id>.json` and kept on local disk and in memory.

`WHITEBOARD_DIR` (tests, laptops) points at a folder of packages instead of the bucket. Nothing here raises to the renderer: a drawing that cannot be had
is written as a boxed label by the board compiler.
"""
import json
import os
import re
import threading
from typing import Any, Dict, List, Optional

import numpy as np

INDEX_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "whiteboard", "library_index.json")
PREFIX = "w/"
CACHE_DIR = os.environ.get("WHITEBOARD_CACHE_DIR", "/tmp/whiteboard")
ID_RE = re.compile(r"^[a-z0-9_]{2,48}$")
MAX_IN_MEMORY = 48
_index: Optional[Dict[str, Any]] = None
_pkgs: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


def index() -> Dict[str, Any]:
    """{"items": [{id, category, title, title_es, synonyms_en, synonyms_es, tags, v}], "min_score": float}; an absent index is an empty library."""
    global _index
    if _index is None:
        try:
            with open(INDEX_PATH, encoding="utf-8") as f:
                _index = json.load(f)
        except (OSError, ValueError):
            _index = {"items": [], "min_score": 1.0}
    return _index


def ids() -> List[str]:
    return [it["id"] for it in index()["items"]]


def has(oid: str) -> bool:
    return oid in set(ids())


def _norm(s: str) -> str:
    import unicodedata

    s = unicodedata.normalize("NFD", str(s).lower())
    return re.sub(r"[^a-z0-9]+", " ", "".join(c for c in s if unicodedata.category(c) != "Mn")).strip()


def by_name(phrase: str) -> Optional[str]:
    """An id for a plain name: the id itself, or an exact title or synonym (English or Spanish). No model call."""
    q = _norm(phrase)
    if not q:
        return None
    table = getattr(by_name, "_t", None)
    if table is None:
        table = {}
        for it in index()["items"]:
            for name in [it["id"].replace("_", " "), it.get("title") or "", it.get("title_es") or ""] + list(it.get("synonyms_en") or []) + list(it.get("synonyms_es") or []):
                table.setdefault(_norm(name), it["id"])
        by_name._t = table      # type: ignore[attr-defined]
    return table.get(q) or table.get(q.rstrip("s"))


def search(phrase: str, k: int = 3, embed=None) -> List[Dict[str, Any]]:
    """By meaning: Cohere Embed v4 through the shared Bedrock helper (never Titan). -> [{id, score, title}] at or above the library's floor; [] on any failure."""
    try:
        idx = index()
        if not idx["items"]:
            return []
        M = getattr(search, "_m", None)
        if M is None:
            import base64

            M = np.stack([np.frombuffer(base64.b64decode(it["v"]), dtype="<f2").astype(np.float32) for it in idx["items"]])
            M /= np.linalg.norm(M, axis=1, keepdims=True) + 1e-9
            search._m = M      # type: ignore[attr-defined]
        if embed is None:
            from common import library_search

            embed = library_search.embed_text
        q = np.asarray(embed(phrase.strip()[:200]), np.float32)
        q /= np.linalg.norm(q) + 1e-9
        sc = M @ q
        floor = float(idx.get("min_score", 0.30))
        return [{"id": idx["items"][i]["id"], "score": round(float(sc[i]), 4), "title": idx["items"][i].get("title")} for i in np.argsort(-sc)[:k] if sc[i] >= floor]
    except Exception:  # noqa: BLE001 - search is best effort: no match means a written label
        return []


def load(oid: str) -> Dict[str, Any]:
    """The drawing package of an id (raises when it cannot be had: the board writes its name instead). Read once per container."""
    if not ID_RE.match(oid or ""):
        raise KeyError(oid)
    with _lock:
        if oid in _pkgs:
            return _pkgs[oid]
    local = os.environ.get("WHITEBOARD_DIR")
    path = os.path.join(local, oid + ".json") if local else os.path.join(CACHE_DIR, oid + ".json")
    if not os.path.isfile(path):
        if local:
            raise KeyError(oid)
        import boto3

        os.makedirs(CACHE_DIR, exist_ok=True)
        part = f"{path}.part-{os.getpid()}-{threading.get_ident()}"
        boto3.client("s3").download_file(os.environ["CATALOG_BUCKET"], f"{PREFIX}{oid}.json", part)
        os.replace(part, path)
    with open(path, encoding="utf-8") as f:
        p = json.load(f)
    p["strokes"] = [np.asarray(s, np.float64) for s in p["strokes"]]
    with _lock:
        if len(_pkgs) >= MAX_IN_MEMORY:
            _pkgs.pop(next(iter(_pkgs)))
        _pkgs[oid] = p
    return p
