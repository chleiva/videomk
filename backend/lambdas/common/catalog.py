"""videomk's own catalog of generated images (docs/IMAGE_CATALOG.md): storage layout, metadata, vector search and the demand log.

Layout (one private bucket per stage, objects immutable and named by the SHA-256 of the original):
    o/<sha256>.jpg   the original at full size      p/<sha256>.jpg  preview, 1280 px wide      t/<sha256>.jpg  thumbnail, 384 px (what is embedded)
Metadata: DynamoDB table (pk `id` = the sha256). Vectors: S3 Vectors index `catalog-images` (key = id, 1024 d cosine, Cohere Embed v4: images are stored as
`search_document`, text queries are `search_query`). Nothing here is ever served publicly: the engine reads an original and bakes it into the rendered video.

Environment (set by the CDK construct only when `-c imageCatalog=1`): CATALOG_BUCKET, CATALOG_TABLE, CATALOG_VECTOR_BUCKET, CATALOG_VECTOR_INDEX, CATALOG_DEMAND_TABLE,
CATALOG_MIN_SCORE (the lowest score worth verifying), CATALOG_SALT_PARAM (SSM name of the salt for the video reference).
"""
import datetime
import hashlib
import json
import logging
import os
import re
import time
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger()

INDEX_NAME = "catalog-images"
DEFAULT_MIN_SCORE = 0.35            # see docs/IMAGE_CATALOG.md: measured on the pilot (text query vs image embedding)
SOURCE_NAME = "videomk-library"     # the ledger's `source` for a catalog image
LICENSE_NAME = "videomk library"
ID_RE = re.compile(r"^[0-9a-f]{64}$")
DEMAND_TTL_DAYS = 365               # 12 months
PREVIEW_PX, THUMB_PX = 1280, 384

_cache: Dict[str, Any] = {}


def enabled() -> bool:
    return bool(os.environ.get("CATALOG_BUCKET") and os.environ.get("CATALOG_TABLE") and os.environ.get("CATALOG_VECTOR_BUCKET"))


def min_score() -> float:
    try:
        return float(os.environ.get("CATALOG_MIN_SCORE") or DEFAULT_MIN_SCORE)
    except ValueError:
        return DEFAULT_MIN_SCORE


def _get(name: str, make: Callable[[], Any]) -> Any:
    if name not in _cache:
        _cache[name] = make()
    return _cache[name]


def set_clients(*, s3: Any = None, ddb: Any = None, vectors: Any = None, embed_text: Optional[Callable[[str], List[float]]] = None) -> None:
    """Tests (and the scripts, with their own profile) inject clients here."""
    for k, v in (("s3", s3), ("ddb", ddb), ("vec", vectors), ("embed", embed_text)):
        if v is not None:
            _cache[k] = v


def reset() -> None:
    _cache.clear()


def s3():
    import boto3
    return _get("s3", lambda: boto3.client("s3"))


def ddb():
    import boto3
    return _get("ddb", lambda: boto3.resource("dynamodb"))


def vectors():
    import boto3
    return _get("vec", lambda: boto3.client("s3vectors"))


def _embed(text: str) -> List[float]:
    def default(t: str) -> List[float]:
        from common import library_search
        return library_search.embed_text(t)
    return _get("embed", lambda: default)(text)


def table():
    return ddb().Table(os.environ["CATALOG_TABLE"])


def vector_target() -> Dict[str, str]:
    return {"vectorBucketName": os.environ["CATALOG_VECTOR_BUCKET"], "indexName": os.environ.get("CATALOG_VECTOR_INDEX", INDEX_NAME)}


# ----------------------------------------------------------------------------- keys
def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def check_id(cid: Any) -> str:
    if not isinstance(cid, str) or not ID_RE.match(cid):
        raise ValueError("invalid catalog id")
    return cid


def key_original(cid: str) -> str:
    return "o/" + check_id(cid) + ".jpg"   # plain concatenation on purpose: catalog keys hold no user id, so the account-deletion prefix scan must not list them


def key_preview(cid: str) -> str:
    return "p/" + check_id(cid) + ".jpg"   # plain concatenation on purpose: catalog keys hold no user id, so the account-deletion prefix scan must not list them


def key_thumb(cid: str) -> str:
    return "t/" + check_id(cid) + ".jpg"   # plain concatenation on purpose: catalog keys hold no user id, so the account-deletion prefix scan must not list them


# ----------------------------------------------------------------------------- search
def search(query: str, aspect: str = "16:9", k: int = 5) -> List[Dict[str, Any]]:
    """The catalog images closest to a text phrase: [{id, score, title, category, crop}] best first. `score` is the cosine similarity (1 - distance) of the phrase
    (Cohere `search_query`) to the image (Cohere `search_document`). `crop` is the centred box to cut for `aspect` (see catalog_style.crop_box). Never raises:
    any failure is an empty list, so the director falls back to stock."""
    from common import catalog_style

    q = re.sub(r"\s+", " ", (query or "").strip())[:300]
    if not q or not enabled():
        return []
    try:
        res = vectors().query_vectors(**vector_target(), queryVector={"float32": _embed(q)}, topK=max(1, min(int(k), 30)), returnDistance=True, returnMetadata=True)
    except Exception:
        logger.exception("catalog search failed")
        return []
    out: List[Dict[str, Any]] = []
    for h in res.get("vectors") or []:
        cid = str(h.get("key") or "")
        if not ID_RE.match(cid) or h.get("distance") is None:
            continue
        md = h.get("metadata") or {}
        out.append({"id": cid, "score": round(1 - float(h["distance"]), 4), "title": str(md.get("title") or ""), "category": str(md.get("category") or ""),
                    "crop_aspect": aspect, "aspect_ok": aspect in ("16:9", "9:16", "1:1", "4:5")})
    out.sort(key=lambda m: -m["score"])
    return out


def get_item(cid: str) -> Optional[Dict[str, Any]]:
    return table().get_item(Key={"id": check_id(cid)}).get("Item")


def usable(item: Optional[Dict[str, Any]]) -> bool:
    """Only images that passed review are ever used in a video."""
    return bool(item) and item.get("review_status") == "approved"


def read_object(key: str) -> bytes:
    return s3().get_object(Bucket=os.environ["CATALOG_BUCKET"], Key=key)["Body"].read()


def ledger_entry(item: Dict[str, Any]) -> Dict[str, str]:
    """No third-party credit line is needed; the record says where the picture came from. The description's credit block leaves this source out (assets.credits_block)."""
    return {"source": SOURCE_NAME, "id": str(item["id"]), "title": str(item.get("title") or "")[:120], "creator": "videomk", "license": LICENSE_NAME,
            "license_url": "", "landing_url": "", "attribution": ""}


# ----------------------------------------------------------------------------- demand log
def _salt() -> str:
    def load() -> str:
        from common.secrets import get_secret_param
        return get_secret_param(os.environ.get("CATALOG_SALT_PARAM") or "/videomk/catalog_demand_salt", quiet=True) or ""
    return _get("salt", load)


def log_demand(phrase: str, video_id: str, outcome: str, score: Optional[float] = None) -> bool:
    """One image search by the director: the generic phrase only (common/catalog_privacy), a salted hash of the video, whether the catalog answered. Best effort:
    never raises, never blocks a video. Returns whether a row was written."""
    from common import catalog_privacy as priv

    table_name = os.environ.get("CATALOG_DEMAND_TABLE")
    if not table_name:
        return False
    g = priv.generic_phrase(phrase)
    salt = _salt()
    if g is None or not salt or outcome not in ("catalog", "stock", "none", "rejected"):
        return False
    try:
        ref = priv.video_ref(video_id, salt)
        now = int(time.time())
        ddb().Table(table_name).update_item(
            Key={"phrase": g, "video": ref},
            UpdateExpression="ADD searches :one SET last_seen = :now, outcome = :o, best_score = :s, expires = :ttl, first_seen = if_not_exists(first_seen, :now)",
            ExpressionAttributeValues={":one": 1, ":now": now, ":o": outcome, ":s": __import__("decimal").Decimal(str(round(score or 0.0, 4))), ":ttl": now + DEMAND_TTL_DAYS * 86400})
        return True
    except Exception:
        logger.exception("demand log failed")
        return False


def today() -> str:
    return datetime.date.today().isoformat()
