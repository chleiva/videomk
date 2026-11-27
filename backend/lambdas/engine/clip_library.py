"""VideoMK's own clip library (docs/CLIPS_ON_DEMAND.md): add a clip, find one by meaning, hand it to the beat step as an ordinary clip candidate, count its uses.

Search is by embedding (Cohere Embed v4 through Bedrock, the same model and space as the image catalog and My media; never Titan): every clip carries two vectors,
its general brief as text (`tvec`) and its middle frame as an image (`ivec`). A wording is compared with both; the comparison is exact (numpy over every clip, cached
while the function is warm), which is right up to a few thousand clips.

A library clip is never trusted because it is ours: it goes through the same trim, crop and strict 3-frame check against the narration as stock footage (clips.scout_own).
"""
import hashlib
import json
import logging
import time
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np

from common import clip_config, clip_store as cs

PROVIDER = "videomk-library"       # the ledger's `source`; the description's credit block leaves this source out (assets.credits_block)
LICENSE = "VideoMK library"
SCHEME = "cliplib://"
SCOPE_LIBRARY = "library"          # who a clip is for. Today the only value. A future "exclusive" clip (made for and owned by one customer) carries scope "exclusive" and `owner`, and is never searched here
IMG_BONUS = 0.15                   # a wording scores about 0.15 lower against a picture than against a matching text (docs/IMAGE_CATALOG.md: 0.40-0.56 for correct matches)
CROP_PENALTY = 0.03                # a clip that must be cropped to the video's shape ranks a little below one that already has it
CACHE_S = 120.0

_embedders: Dict[str, Callable[[Any], Sequence[float]]] = {}
_cache: Dict[str, Any] = {"at": 0.0, "rows": None, "store": None}


# ----------------------------------------------------------------------------- embeddings
def set_embedder(*, query: Optional[Callable[[str], Sequence[float]]] = None, doc: Optional[Callable[[str], Sequence[float]]] = None,
                 image: Optional[Callable[[bytes], Sequence[float]]] = None) -> None:
    """Tests (and scripts with their own profile) inject embedders; None values leave the default (Cohere Embed v4 on Bedrock)."""
    for k, v in (("query", query), ("doc", doc), ("image", image)):
        if v is not None:
            _embedders[k] = v


def reset() -> None:
    _embedders.clear()
    _cache.update({"at": 0.0, "rows": None, "store": None})


def embed(kind: str, value: Any) -> np.ndarray:
    """kind: 'query' (a search wording), 'doc' (a clip's brief), 'image' (a JPEG frame). A unit float32 vector."""
    fn = _embedders.get(kind)
    if fn is None:
        from common import library_search as ls
        fn = {"query": ls.embed_text, "doc": lambda t: ls._embed({"input_type": "search_document", "texts": [str(t)[:600]]}), "image": ls.embed_image}[kind]
    v = np.asarray(fn(value), dtype=np.float32)
    return v / (float(np.linalg.norm(v)) or 1.0)


def pack(vec: np.ndarray) -> str:
    return cs.b64(np.asarray(vec, dtype=np.float16).tobytes())


def unpack(text: str) -> np.ndarray:
    v = np.frombuffer(cs.unb64(text), dtype=np.float16).astype(np.float32)
    return v / (float(np.linalg.norm(v)) or 1.0)


# ----------------------------------------------------------------------------- who may use it
def usable(plan: Optional[str] = None, cfg: Optional[Dict[str, Any]] = None) -> bool:
    """Is there a library, is reuse on, and (when a plan is given) may that plan's videos use it?"""
    if cs.current() is None:
        return False
    cfg = clip_config.config() if cfg is None else cfg
    return bool(cfg["reuse_enabled"]) and (plan is None or plan in cfg["reuse_plans"])


def video_ref(video_id: str) -> str:
    """A one-way reference to a video (video ids are random UUIDs, so the hash cannot be walked back): the library counts distinct videos without naming them."""
    return hashlib.sha256(f"clipgen:v:{video_id}".encode()).hexdigest()[:16]


def account_ref(user_id: str) -> str:
    return hashlib.sha256(f"clipgen:a:{user_id}".encode()).hexdigest()[:16]


# ----------------------------------------------------------------------------- the index
def rows(store: Optional[cs.Store] = None, *, fresh: bool = False) -> List[Dict[str, Any]]:
    store = store or cs.current()
    if store is None:
        return []
    now = time.time()
    if fresh or _cache["rows"] is None or _cache["store"] is not store or now - _cache["at"] > CACHE_S:
        out = []
        for r in store.query(cs.LIB):
            if r.get("status", "active") != "active" or not r.get("tvec") or r.get("scope", SCOPE_LIBRARY) != SCOPE_LIBRARY:
                continue   # only the shared library is ever searched: a clip with any other scope (a future exclusive clip made for one customer) never reaches another account
            r["_t"] = unpack(r["tvec"])
            r["_i"] = unpack(r["ivec"]) if r.get("ivec") else None
            out.append(r)
        _cache.update({"at": now, "rows": out, "store": store})
    return _cache["rows"]


def shape_fit(row: Dict[str, Any], orientation: str) -> Optional[int]:
    """0: the clip already has the video's shape. 1: it will be centre-cropped and the gate said the subject stays in the middle. None: not offered.
    A landscape video takes only 16:9 clips; a 9:16 clip is never cropped to landscape (it would keep a third of the picture)."""
    aspect, safe = str(row.get("aspect") or "16:9"), bool(row.get("center_safe"))
    if orientation == "portrait":
        return 0 if aspect == "9:16" else (1 if safe else None)
    if orientation == "square":
        return 1 if safe else None
    return 0 if aspect == "16:9" else None


def search(text: str, orientation: str = "landscape", *, k: int = 3, min_score: Optional[float] = None, qvec: Optional[np.ndarray] = None,
           store: Optional[cs.Store] = None, min_seconds: float = 0.0) -> List[Tuple[float, Dict[str, Any]]]:
    """The clips closest to a wording, best first: [(score, row)]. score = the better of text-to-brief and text-to-frame (+IMG_BONUS), minus a little when a crop is needed."""
    lib = rows(store)
    if not lib or not str(text or "").strip():
        return []
    floor = float(clip_config.config()["search_min_score"]) if min_score is None else min_score
    q = embed("query", " ".join(str(text).split())[:300]) if qvec is None else qvec
    out: List[Tuple[float, Dict[str, Any]]] = []
    for r in lib:
        fit = shape_fit(r, orientation)
        if fit is None or float(r.get("seconds") or 0) < min_seconds:
            continue
        s = max(float(q @ r["_t"]), (float(q @ r["_i"]) + IMG_BONUS) if r["_i"] is not None else -1.0) - CROP_PENALTY * fit
        if s >= floor:
            out.append((round(s, 4), r))
    out.sort(key=lambda t: -t[0])
    return out[:k]


def nearest_brief(bvec: np.ndarray, orientation: str = "landscape", store: Optional[cs.Store] = None) -> Optional[Tuple[float, Dict[str, Any]]]:
    """The library clip whose BRIEF is closest to this brief (text to text only): the 'do we already have this scene?' question."""
    best: Optional[Tuple[float, Dict[str, Any]]] = None
    for r in rows(store):
        if shape_fit(r, orientation) is None:
            continue
        s = float(bvec @ r["_t"])
        if best is None or s > best[0]:
            best = (round(s, 4), r)
    return best


def candidate(row: Dict[str, Any], score: float = 0.0) -> Dict[str, Any]:
    cid = str(row["sk"])
    return {"provider": PROVIDER, "id": cid, "thumb_url": f"{SCHEME}p/{cid}.jpg", "video_url": f"{SCHEME}v/{cid}.mp4", "width": int(row.get("width") or 1280),
            "height": int(row.get("height") or 720), "duration": float(row.get("seconds") or 0), "creator": "VideoMK", "creator_url": "", "landing_url": "",
            "license": LICENSE, "alt": str(row.get("brief") or "")[:200], "attribution": "", "score": score}


def fetch(inner: Callable[..., bytes], store: Optional[cs.Store] = None) -> Callable[..., bytes]:
    """A fetch function that reads `cliplib://` from the library and sends everything else to `inner`."""
    def f(url: str, **kw: Any) -> bytes:
        if str(url).startswith(SCHEME):
            s = store or cs.current()
            if s is None:
                raise OSError("no clip library")
            return s.get_object(str(url)[len(SCHEME):])
        return inner(url, **kw)
    return f


# ----------------------------------------------------------------------------- writing
INDEX_FIELDS = ("scope", "owner", "brief", "tags", "aspect", "width", "height", "seconds", "center_safe", "created", "cost_usd", "provider", "model", "origin", "demand_video", "gate_score", "status")


def clip_id(mp4: bytes) -> str:
    return hashlib.sha256(mp4).hexdigest()


def add_clip(store: cs.Store, *, mp4: bytes, poster: bytes, meta: Dict[str, Any], tvec: np.ndarray, ivec: Optional[np.ndarray]) -> str:
    """Store one accepted clip: the file, its poster, the metadata document (the source of truth, vectors included), then the index row. The id is the SHA-256 of the
    file, so storing the same clip twice changes nothing (and never resets its use count)."""
    cid = clip_id(mp4)
    if meta.get("scope", SCOPE_LIBRARY) != SCOPE_LIBRARY:
        raise ValueError("only shared library clips are stored here")   # exclusive media needs its own store and rights: not built
    doc = {**meta, "id": cid, "scope": SCOPE_LIBRARY, "license": LICENSE, "status": meta.get("status", "active"), "created": int(meta.get("created") or time.time()),
           "tvec": pack(tvec), **({"ivec": pack(ivec)} if ivec is not None else {})}
    store.put_object(f"v/{cid}.mp4", mp4, "video/mp4")
    store.put_object(f"p/{cid}.jpg", poster, "image/jpeg")
    store.put_object(f"m/{cid}.json", json.dumps(doc, ensure_ascii=False, sort_keys=True).encode(), "application/json")
    index_row(store, doc)
    return cid


def index_row(store: cs.Store, doc: Dict[str, Any]) -> bool:
    """The search row of a metadata document; an existing row is left alone (its uses are history)."""
    row = {k: doc[k] for k in INDEX_FIELDS if doc.get(k) is not None}
    row.update({"tvec": doc["tvec"], "uses": 0, **({"ivec": doc["ivec"]} if doc.get("ivec") else {})})
    made = store.put(cs.LIB, str(doc["id"]), row, only_if_absent=True)
    _cache["rows"] = None
    return made


def record_use(clip: str, video_id: str, store: Optional[cs.Store] = None) -> None:
    """One video used this clip (best effort: a counter must never cost a video)."""
    try:
        (store or cs.current()).add(cs.LIB, clip, {"uses": 1}, sets={"videos": [video_ref(video_id)]}, fields={"last_used": int(time.time())})
    except Exception:
        logging.exception("clip use not recorded")


def set_status(store: cs.Store, clip: str, status: str) -> None:
    """'retired' takes a clip out of search (the file stays); 'active' brings it back."""
    doc = json.loads(store.get_object(f"m/{clip}.json"))
    doc["status"] = status
    store.put_object(f"m/{clip}.json", json.dumps(doc, ensure_ascii=False, sort_keys=True).encode(), "application/json")
    store.add(cs.LIB, clip, fields={"status": status})
    _cache["rows"] = None


def reindex(store: cs.Store) -> int:
    """Rebuild missing index rows from the metadata documents (the usage table has no backup; the bucket is the truth). Returns the rows created."""
    made = 0
    for key in store.list_objects("m/"):
        doc = json.loads(store.get_object(key))
        if doc.get("tvec") and index_row(store, doc):
            made += 1
    return made


def promote(src: cs.Store, dst: cs.Store, ids: Optional[Sequence[str]] = None, *, dry_run: bool = True) -> List[Dict[str, Any]]:
    """Copy clips from one store to another (local -> qa -> prod) WITHOUT generating, checking or embedding anything again: the file, the poster, the metadata and
    the vectors travel as they are. Idempotent by id; a clip already there is skipped. Retired clips are not promoted."""
    out = []
    for key in src.list_objects("m/"):
        cid = key[2:-5]
        if ids and cid not in ids:
            continue
        doc = json.loads(src.get_object(key))
        if doc.get("status", "active") != "active" or doc.get("scope", SCOPE_LIBRARY) != SCOPE_LIBRARY:
            out.append({"id": cid, "action": "skipped: " + str(doc.get("status"))})
            continue
        if dst.has_object(f"m/{cid}.json") and dst.get(cs.LIB, cid):
            out.append({"id": cid, "action": "already there"})
            continue
        if not dry_run:
            dst.put_object(f"v/{cid}.mp4", src.get_object(f"v/{cid}.mp4"), "video/mp4")
            dst.put_object(f"p/{cid}.jpg", src.get_object(f"p/{cid}.jpg"), "image/jpeg")
            doc = {**doc, "promoted_from": doc.get("origin") or src.label, "promoted_at": int(time.time())}
            dst.put_object(f"m/{cid}.json", json.dumps(doc, ensure_ascii=False, sort_keys=True).encode(), "application/json")
            index_row(dst, doc)
        out.append({"id": cid, "action": "would copy" if dry_run else "copied", "brief": doc.get("brief"), "cost_usd": doc.get("cost_usd")})
    return out
