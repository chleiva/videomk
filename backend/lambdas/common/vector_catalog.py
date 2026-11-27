"""videomk's catalog of cartoon vector scenes (docs/VECTOR_SCENES.md, docs/VECTOR_CATALOG.md): lookup by meaning.

A scene package is a folder `<id>/` with `manifest.json`, one SVG per depth layer, `thumb.jpg` and `meta.json` (built offline by scripts/vector_catalog_build.py).
Search needs no infrastructure: the whole index (a few dozen scenes, two 1024-d Cohere Embed v4 vectors each, stored as base64 float16) is the JSON file `vector_catalog_index.json`
next to this module, so it ships inside the Lambda code zip. A text query is embedded with Cohere (`search_query`, through the same Bedrock helper as the image catalog) and
compared by cosine with each scene's image vector and description vector (best of the two). The packages themselves (0.3 to 2 MB each) do NOT ship in the code zip: they are read from
the catalog bucket under `v/<id>/<file>` (see `fetch_package`) or from a local folder given by VECTOR_CATALOG_DIR (tests, laptops).

Aspect: a scene is drawn for ONE shape (its SVG layers are rasterised at the frame size, so another shape would stretch it): landscape scenes serve 16:9, tall scenes serve 9:16.
`search` never raises: any failure returns [] so the director falls back to a normal scene.
"""
import base64
import json
import logging
import math
import os
from functools import lru_cache
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger()

INDEX_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vector_catalog_index.json")
MIN_SCORE = 0.30            # lowest cosine worth showing to the planner (see docs/VECTOR_CATALOG.md for the measurement)
PREFIX = "v/"


@lru_cache(maxsize=4)
def _load(path: str) -> Dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, ValueError):
        return {"dim": 0, "items": []}
    import struct

    def dec(b64: str) -> List[float]:
        buf = base64.b64decode(b64)
        n = len(buf) // 2
        return list(struct.unpack(f"<{n}e", buf))

    items = []
    for it in raw.get("items", []):
        it = dict(it)
        it["vi"], it["vt"] = dec(it.pop("vi")), dec(it.pop("vt"))
        items.append(it)
    return {"dim": raw.get("dim", 0), "items": items}


def load_index(path: Optional[str] = None) -> Dict[str, Any]:
    """-> {"dim": int, "items": [{id, title, ..., "vi": [float], "vt": [float]}]} (vectors decoded once). An absent index is an empty catalog."""
    return _load(path or INDEX_PATH)


load_index.cache_clear = _load.cache_clear     # type: ignore[attr-defined]


def _cos(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def search(query: str, aspect: str = "16:9", k: int = 5, *, embed: Optional[Callable[[str], List[float]]] = None, min_score: float = MIN_SCORE) -> List[Dict[str, Any]]:
    """The best scenes for a phrase, best first: [{id, score, title, category, mood, aspects, palette, layers, svg_kb}]. Only scenes drawn for `aspect` are returned."""
    try:
        idx = load_index()
        if not idx["items"] or not isinstance(query, str) or not query.strip():
            return []
        if embed is None:
            from common import library_search
            embed = library_search.embed_text
        q = embed(query.strip())
        out = []
        for it in idx["items"]:
            if aspect not in it.get("aspects", []):
                continue
            score = max(_cos(q, it["vi"]), _cos(q, it["vt"]))
            if score >= min_score:
                out.append({"id": it["id"], "score": round(score, 4), "title": it["title"], "category": it["category"], "mood": it["mood"],
                            "aspects": it["aspects"], "palette": it.get("palette", []), "layers": it.get("layers"), "svg_kb": it.get("svg_kb")})
        out.sort(key=lambda r: -r["score"])
        return out[:max(1, int(k))]
    except Exception:      # noqa: BLE001 - search is best effort: no match means a normal scene
        logger.exception("vector catalog search failed")
        return []


def scene_ids() -> List[str]:
    return [it["id"] for it in load_index()["items"]]


def check_id(scene_id: Any) -> str:
    import re
    if not isinstance(scene_id, str) or not re.fullmatch(r"[a-z0-9_]{3,64}", scene_id):
        raise ValueError("bad scene id")
    return scene_id


def fetch_package(scene_id: str, dest: str, *, s3: Any = None, bucket: Optional[str] = None) -> str:
    """Make the package of a scene available in the folder `dest` and return its path (the folder VectorScene reads).
    Source: the folder VECTOR_CATALOG_DIR/<id> when that variable is set, else the catalog bucket (`v/<id>/...`, CATALOG_BUCKET) through `s3` (a boto3 client)."""
    scene_id = check_id(scene_id)
    out = os.path.join(dest, scene_id)
    os.makedirs(out, exist_ok=True)
    local = os.environ.get("VECTOR_CATALOG_DIR")
    names = ("manifest.json",)
    if local:
        import shutil
        src = os.path.join(local, scene_id)
        for f in sorted(os.listdir(src)):
            if f.endswith((".svg", ".json")):
                shutil.copy(os.path.join(src, f), os.path.join(out, f))
        return out
    import boto3
    s3 = s3 or boto3.client("s3")
    bucket = bucket or os.environ["CATALOG_BUCKET"]
    man = json.loads(s3.get_object(Bucket=bucket, Key=f"{PREFIX}{scene_id}/manifest.json")["Body"].read())
    with open(os.path.join(out, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(man, f)
    for lay in man["layers"]:
        name = os.path.basename(lay["file"])
        with open(os.path.join(out, name), "wb") as f:
            f.write(s3.get_object(Bucket=bucket, Key=f"{PREFIX}{scene_id}/{name}")["Body"].read())
    del names
    return out
