"""Licence-aware photo scout (Openverse) + the credits ledger.

Only CC0 / public-domain / CC BY images are used (no share-alike, no non-commercial). Every image that
ends up in a video gets a ledger row (source, licence, creator, landing page) which is stored with the
video and rendered into the YouTube description, so attribution is automatic and auditable.
"""
import io
import urllib.parse
from typing import Any, Callable, Dict, List, Optional, Tuple

from PIL import Image

from .netsafe import FetchError, fetch_bytes, fetch_json

OPENVERSE = "https://api.openverse.org/v1/images/"
ALLOWED_LICENSES = ("cc0", "pdm", "by")
MIN_WIDTH = 1600
MAX_SIDE = 2800      # the stored size of a stock photo for 720p and 1080p videos (as always)
MAX_SIDE_4K = 4400   # ... and for a 4K video: 3840 across plus the 1.14x push-in of an image scene, so the photo is never enlarged when the source is that big (docs/FOUR_K.md)


def max_side_for(big: bool = False) -> int:
    return MAX_SIDE_4K if big else MAX_SIDE
MAX_PIXELS = 50_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS  # decompression-bomb guard


def search(query: str, fetch: Callable[[str], Any] = fetch_json, limit: int = 12) -> List[Dict[str, Any]]:
    q = urllib.parse.urlencode({
        "q": query[:120], "license": ",".join(ALLOWED_LICENSES), "license_type": "commercial",
        "mature": "false", "aspect_ratio": "wide", "size": "large", "page_size": limit,
    })
    return list(fetch(f"{OPENVERSE}?{q}").get("results") or [])


def pick(results: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Best candidate: allowed licence, https, wide enough; larger first. (A vision rerank can slot in here.)"""
    ok = []
    for r in results:
        lic = str(r.get("license", "")).lower()
        w, h = int(r.get("width") or 0), int(r.get("height") or 0)
        url = str(r.get("url") or "")
        if lic in ALLOWED_LICENSES and url.startswith("https://") and w >= MIN_WIDTH and h > 0 and w / h >= 1.3:
            ok.append(r)
    return max(ok, key=lambda r: int(r.get("width") or 0) * int(r.get("height") or 0), default=None)


def ledger_entry(r: Dict[str, Any]) -> Dict[str, str]:
    lic = str(r.get("license", "")).lower()
    ver = str(r.get("license_version") or "")
    return {
        "source": "openverse",
        "id": str(r.get("id", "")),
        "title": str(r.get("title") or "")[:120],
        "creator": str(r.get("creator") or "")[:80],
        "license": f"{lic.upper()} {ver}".strip(),
        "license_url": str(r.get("license_url") or ""),
        "landing_url": str(r.get("foreign_landing_url") or ""),
        "attribution": str(r.get("attribution") or "")[:300],
    }


def to_jpeg(raw: bytes, max_side: int = MAX_SIDE, quality: int = 88) -> Tuple[bytes, Tuple[int, int]]:
    """Validate + re-encode (strips metadata, normalises format, bounds size)."""
    im = Image.open(io.BytesIO(raw))
    im.load()
    im = im.convert("RGB")
    if max(im.size) > max_side:
        s = max_side / max(im.size)
        im = im.resize((int(im.width * s), int(im.height * s)), Image.LANCZOS)
    out = io.BytesIO()
    im.save(out, "JPEG", quality=quality, optimize=True)
    return out.getvalue(), im.size


def scout(query: str, *, fetch_json_fn: Callable[[str], Any] = fetch_json, fetch_bytes_fn: Callable[..., bytes] = fetch_bytes) -> Optional[Tuple[bytes, Dict[str, str]]]:
    """Find, download and normalise one photo. Returns (jpeg_bytes, ledger_entry) or None. Never raises."""
    try:
        r = pick(search(query, fetch=fetch_json_fn))
        if not r:
            return None
        raw = fetch_bytes_fn(str(r["url"]))
        jpeg, _ = to_jpeg(raw)
        return jpeg, ledger_entry(r)
    except (FetchError, OSError, ValueError, KeyError, TypeError, Image.DecompressionBombError):
        return None


def credit_line(entry: Dict[str, str]) -> str:
    """Short on-screen credit (full attribution goes in the description)."""
    who = entry.get("creator") or "Unknown"
    return f"Photo: {who} ({entry.get('license', '')})".strip()


LABELS = {"en": {"credits": "Image credits:", "sources": "Sources:", "intro": "Intro"},
          "es": {"credits": "Créditos de las imágenes:", "sources": "Fuentes:", "intro": "Introducción"}}


def credits_block(ledger: List[Dict[str, str]], sources: List[Dict[str, str]], language: str = "en") -> str:
    """The Unsplash attribution lines themselves keep Unsplash's recommended wording ("Photo by ... on Unsplash") in every language."""
    labels = LABELS.get(language, LABELS["en"])
    lines: List[str] = []
    if ledger:
        lines.append(labels["credits"])
        lines += [f"- {e.get('attribution') or (e.get('title') + ' - ' + e.get('creator') + ' (' + e.get('license') + ')')}  {e.get('landing_url', '')}".rstrip() for e in ledger]
    if sources:
        lines.append(labels["sources"])
        lines += [f"- {s['title']} ({s.get('publisher', '')}) {s.get('url', '')}".rstrip() for s in sources]
    return "\n".join(lines)
