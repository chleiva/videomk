"""Photo upload ids and keys, shared by the launcher, the upload endpoint and the engine (no image library here: the launcher has none)."""
import re
import datetime
from typing import Any, Dict, List

MAX_PHOTOS = 100   # per video: the engine catalogues them on contact sheets (engine/curate.py), so the cost grows slowly with the count
MAX_UPLOAD_BYTES = 10_000_000
ID_RE = re.compile(r"^[0-9a-f]{16}$")


class PhotoError(ValueError):
    pass


def upload_key(user_id: str, media_id: str) -> str:
    return f"uploads/{user_id}/{media_id}.jpg"


def valid_media_ids(ids: Any) -> List[str]:
    """The list as a clean list of unique ids, or raises PhotoError."""
    if not isinstance(ids, list) or not ids:
        raise PhotoError("'media' must be a non-empty list")
    if len(ids) > MAX_PHOTOS:
        raise PhotoError(f"at most {MAX_PHOTOS} photos per video")
    if not all(isinstance(i, str) and ID_RE.match(i) for i in ids) or len(set(ids)) != len(ids):
        raise PhotoError("'media' holds invalid or duplicate photo ids")
    return list(ids)


def valid_media_meta(meta: Any, ids: List[str]) -> Dict[str, Dict[str, Any]]:
    """Optional per-photo facts read on the phone before the metadata was stripped: {media id: {"taken": "YYYY-MM-DDTHH:MM:SS", "lat": n, "lon": n}}.
    Only known ids, only these three fields, only well-formed values; coordinates are rounded to 2 decimals (about 1 km) here whatever the phone sent. Raises PhotoError for a wrong shape."""
    if meta is None:
        return {}
    if not isinstance(meta, dict) or len(meta) > MAX_PHOTOS:
        raise PhotoError("'media_meta' must be an object keyed by photo id")
    out: Dict[str, Dict[str, Any]] = {}
    for mid, m in meta.items():
        if mid not in ids:
            raise PhotoError("'media_meta' names a photo that is not in 'media'")
        if not isinstance(m, dict):
            raise PhotoError("'media_meta' values must be objects")
        row: Dict[str, Any] = {}
        t = m.get("taken")
        if isinstance(t, str):
            try:
                row["taken"] = datetime.datetime.strptime(t[:19], "%Y-%m-%dT%H:%M:%S").strftime("%Y-%m-%dT%H:%M:%S")
            except ValueError:
                raise PhotoError("'taken' must look like 2026-04-12T14:32:00") from None
        lat, lon = m.get("lat"), m.get("lon")
        if lat is not None or lon is not None:
            ok = all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in (lat, lon))
            if not ok or not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise PhotoError("'lat' and 'lon' must be numbers within range")
            row["lat"], row["lon"] = round(float(lat), 2), round(float(lon), 2)
        if row:
            out[mid] = row
    return out
