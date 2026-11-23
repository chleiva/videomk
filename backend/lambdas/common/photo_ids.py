"""Photo upload ids and keys, shared by the launcher, the upload endpoint and the engine (no image library here: the launcher has none)."""
import re
from typing import Any, List

MAX_PHOTOS = 10
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
