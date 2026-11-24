"""The user's own photos: prepare them (rotate, bound the size, strip all metadata, delete the original) and understand them (captions, safety).

Flow: the app uploads originals to `uploads/<user>/<id>.jpg` (presigned POST, size-capped). When the video is planned, `prepare` writes a clean copy
next to the video's other assets, keeps nothing but pixels (no EXIF, so no GPS), and deletes the original; `analyze` makes one batched call to a small
vision model for a caption of each photo and a safety verdict. The director then writes the script around the photos.
Photos only ever go to Bedrock inside our AWS account. The clean copies live with the video (the editor and later edits need them) and are deleted
with it.
"""
import io
import json
import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image, ImageOps

from common.photo_ids import ID_RE, MAX_PHOTOS, MAX_UPLOAD_BYTES, PhotoError, upload_key, valid_media_ids  # noqa: F401  (shared with the launcher)

MAX_PIXELS = 80_000_000      # a decompression-bomb guard well above any phone camera
MAX_SIDE = 2048
THUMB_SIDE = 768
PHOTO_ID_RE = re.compile(r"^P\d{1,3}$")


def _taken(im: Image.Image) -> Optional[str]:
    try:
        ex = im.getexif()
        raw = ex.get_ifd(0x8769).get(36867) or ex.get(306)
        m = re.match(r"(\d{4}):(\d{2}):(\d{2})", str(raw or ""))
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}" if m else None
    except Exception:
        return None


def normalize(raw: bytes) -> Tuple[bytes, bytes, Dict[str, Any]]:
    """(clean full-size JPEG, 768 px JPEG for the vision model, facts). Raises PhotoError for anything that is not a usable photo."""
    if len(raw) > MAX_UPLOAD_BYTES:
        raise PhotoError("photo is too large")
    try:
        im = Image.open(io.BytesIO(raw))
        if im.format not in ("JPEG", "PNG", "WEBP", "MPO"):
            raise PhotoError("unsupported photo format")
        if im.size[0] * im.size[1] > MAX_PIXELS or min(im.size) < 64:
            raise PhotoError("photo is too large or too small")
        taken = _taken(im)
        im = ImageOps.exif_transpose(im)
        im.load()
    except PhotoError:
        raise
    except Exception as e:
        raise PhotoError("not a readable photo") from e
    im = im.convert("RGB")
    if max(im.size) > MAX_SIDE:
        s = MAX_SIDE / max(im.size)
        im = im.resize((round(im.width * s), round(im.height * s)), Image.LANCZOS)
    full = io.BytesIO()
    im.save(full, "JPEG", quality=88, optimize=True)  # a fresh JPEG with no EXIF, ICC or GPS: only pixels are kept
    t = im.copy()
    t.thumbnail((THUMB_SIDE, THUMB_SIDE), Image.LANCZOS)
    thumb = io.BytesIO()
    t.save(thumb, "JPEG", quality=80)
    shape = "portrait" if im.height > im.width * 1.1 else "landscape" if im.width > im.height * 1.1 else "square"
    return full.getvalue(), thumb.getvalue(), {"w": im.width, "h": im.height, "orientation": shape, "taken": taken}


def prepare(video_id: str, user_id: str, media_ids: List[str], *, get: Callable[[str], bytes], put: Callable[[str, bytes], None],
            delete: Callable[[str], None], asset_prefix: str, workers: int = 8) -> Tuple[List[Dict[str, Any]], List[bytes], List[Dict[str, str]]]:
    """Returns (photos P1..Pn in upload order, their thumbnails, skipped [{id, reason}]). Originals are deleted whether or not they were usable.
    The photos are read, cleaned and stored in parallel (up to 100 of them), but numbered in the order the person gave them."""
    from concurrent.futures import ThreadPoolExecutor

    def one(mid: str):
        key = upload_key(user_id, mid)
        try:
            full, thumb, facts = normalize(get(key))
        except PhotoError as e:
            delete(key)
            return mid, None, str(e)
        except Exception:  # missing object or storage trouble
            return mid, None, "photo not found"
        return mid, (key, full, thumb, facts), ""

    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(media_ids) or 1))) as ex:
        results = list(ex.map(one, media_ids))
    photos, thumbs, skipped, pending = [], [], [], []
    for mid, ok, reason in results:
        if ok is None:
            skipped.append({"id": mid, "reason": reason})
            continue
        key, full, thumb, facts = ok
        pid = f"P{len(photos) + 1}"
        akey = f"{asset_prefix}user_{pid}.jpg"
        photos.append({"id": pid, "key": akey, **facts})
        thumbs.append(thumb)
        pending.append((key, akey, full))

    def store(item) -> None:
        key, akey, full = item
        put(akey, full)
        delete(key)

    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(pending) or 1))) as ex:
        list(ex.map(store, pending))
    return photos, thumbs, skipped


_REVIEW = (
    "You help make a video from a person's OWN photos. For each numbered image return a caption and a safety verdict. Return ONLY JSON: "
    '{"photos":[{"n":1,"caption":"<=18 words, what is visible, plain and factual","people":true|false,"exclude":false,"reason":""}]}.\n'
    "Set exclude=true (with a short reason) ONLY for: nudity or sexual content, graphic violence or gore, identity documents, bank cards or screens showing "
    "personal data, or hate symbols. Ordinary photos of people, children, family, pets, food, places and events are fine: exclude=false.\n"
    "Describe only what you can see; never guess names, ages or relationships."
)


def analyze(photos: List[Dict[str, Any]], thumbs: List[bytes], ask_vision: Callable[..., str], *, mode: Optional[str] = None) -> List[Dict[str, str]]:
    """Adds `caption` and `people` to each photo in place and returns the photos that must not be used [{id, reason}].
    mode (env PHOTO_REVIEW): on = drop flagged photos; log_only = report but keep; off = never drop. A failed review never blocks the video."""
    mode = (mode or os.environ.get("PHOTO_REVIEW", "on")).lower()
    if not photos:
        return []
    try:
        text = ask_vision(_REVIEW, f"There are {len(photos)} images, numbered in order. Return JSON for all of them.", thumbs)
        m = re.search(r"\{.*\}", text or "", flags=re.S)
        rows = (json.loads(m.group(0)).get("photos") if m else None) or []
    except Exception:
        rows = []
    by_n = {int(r.get("n")): r for r in rows if isinstance(r, dict) and str(r.get("n", "")).isdigit()}
    flagged: List[Dict[str, str]] = []
    for i, p in enumerate(photos, start=1):
        r = by_n.get(i) or {}
        p["caption"] = re.sub(r"\s+", " ", str(r.get("caption") or "")).strip()[:160] or "a photo"
        p["people"] = bool(r.get("people"))
        if r.get("exclude") is True and mode != "off":
            flagged.append({"id": p["id"], "reason": re.sub(r"\s+", " ", str(r.get("reason") or "not suitable")).strip()[:120]})
    if mode == "on":
        drop = {f["id"] for f in flagged}
        photos[:] = [p for p in photos if p["id"] not in drop]
    return flagged
