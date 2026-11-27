"""GET /gallery : the showcase, videos made by videomk itself, for people who are not creating (docs/PLANS.md, "Gallery").

Public and read-only: no sign-in, no credits, no account data. The ONLY source is `showcase/index.json` in the assets bucket, which an admin writes with
`scripts/plans_admin.py showcase add|remove` (each entry is a COPY of the video under `showcase/<id>/`, outside every expiry rule and outside any customer's folder).
This function can read `showcase/*` and nothing else, and it refuses to sign a key outside that prefix, so nothing a customer made can ever appear here.

  200 {"videos": [{id, title, title_i18n: {en, es}, description, description_i18n, prompt (the real prompt, or null), aspect: "16:9"|"9:16"|"1:1"|"4:5",
                   shape: "wide"|"tall"|"square"|"portrait", width, height, seconds, lang, video_url, poster_url (or null)}], "expires_in": 3600, "count": n}
`title` and `description` follow X-Locale / Accept-Language (English fallback). The URLs are short-lived links (1 hour): fetch the list again rather than storing them.
`shape`, `width`, `height`, `seconds`, `lang`, `title_i18n`, `prompt` and `description_i18n` are the fields of the web home page's samples (frontend/src/data/samples.ts),
so the site can later read this endpoint instead of its bundled files.
"""
import json
import logging
import os
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

from common import i18n
from common.http import json_response

logger = logging.getLogger()
PREFIX = "showcase/"
INDEX_KEY = PREFIX + "index.json"
LINK_SECONDS = 3600
SHAPES = {"16:9": "wide", "9:16": "tall", "1:1": "square", "4:5": "portrait"}
MAX_VIDEOS = 60
_s3 = None


def s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def set_client(client: Any) -> None:   # tests
    global _s3
    _s3 = client


def read_index() -> List[Dict[str, Any]]:
    try:
        raw = json.loads(s3().get_object(Bucket=os.environ["ASSETS_BUCKET"], Key=INDEX_KEY)["Body"].read())
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404", "NotFound", "AccessDenied"):
            return []
        raise
    videos = raw.get("videos") if isinstance(raw, dict) else None
    return [v for v in videos if isinstance(v, dict)] if isinstance(videos, list) else []


def _link(key: Any, content_type: str) -> Optional[str]:
    if not isinstance(key, str) or not key.startswith(PREFIX) or ".." in key or key == INDEX_KEY:
        return None   # never anything outside the showcase
    return s3().generate_presigned_url("get_object", Params={"Bucket": os.environ["ASSETS_BUCKET"], "Key": key, "ResponseContentType": content_type}, ExpiresIn=LINK_SECONDS)


def _text(v: Any, loc: str) -> str:
    if isinstance(v, dict):
        return str(v.get(loc) or v.get("en") or next(iter(v.values()), "") or "")
    return str(v or "")


def public(v: Dict[str, Any], loc: str) -> Optional[Dict[str, Any]]:
    url = _link(v.get("video_key"), "video/mp4")
    if not url or not v.get("id"):
        return None
    aspect = v.get("aspect") if v.get("aspect") in SHAPES else "16:9"
    title, desc = v.get("title") or {}, v.get("description") or {}
    return {"id": str(v["id"]), "title": _text(title, loc), "title_i18n": title if isinstance(title, dict) else {"en": str(title)}, "description": _text(desc, loc),
            "description_i18n": desc if isinstance(desc, dict) else {"en": str(desc)}, "prompt": v.get("prompt") if isinstance(v.get("prompt"), str) and v.get("prompt") else None,
            "aspect": aspect, "shape": SHAPES[aspect], "width": int(v.get("width") or 0) or None, "height": int(v.get("height") or 0) or None, "seconds": int(v.get("seconds") or 0),
            "lang": v.get("lang") if v.get("lang") in i18n.LOCALES else "en", "video_url": url, "poster_url": _link(v.get("poster_key"), "image/jpeg")}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    loc = i18n.pick_locale(event)
    try:
        videos = [p for p in (public(v, loc) for v in read_index()[:MAX_VIDEOS]) if p]
    except Exception:   # noqa: BLE001
        logger.exception("GALLERY_FAILED")
        return json_response(500, {"message": i18n.t("err.generic", loc)})
    # the links live an hour; a shared cache may keep the answer for five minutes, per language
    return json_response(200, {"videos": videos, "count": len(videos), "expires_in": LINK_SECONDS}, {"Cache-Control": "public, max-age=300", "Content-Language": loc, **i18n.vary_headers()})
