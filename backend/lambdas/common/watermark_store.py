"""The person's watermark settings and logo, who may use which mode, and the rule that turns a request into the watermark a video gets (docs/WATERMARK.md).

Stored privately in the assets bucket under `watermark/<user>/` (profile.json and logo.png); nothing is public and nothing is ever served back except a short-lived link to the person's own logo.
Entitlements come from the admin-written flags table (read only at runtime, like unlimited credits): the 'custom' mode is premium, i.e. any of
  flags.watermark_custom = true        (scripts/wallet_admin.py watermark <who> on)
  an active Pro library plan           (flags.storage_plan = 'pro', not lapsed)
  an unlimited test account            (flags.unlimited, only where ALLOW_UNLIMITED_ACCOUNTS=1, never in production)
The policy hook FORCE_WATERMARK=1 (stack context `forceWatermark=1`, default off) makes every video of a NON-premium account carry the videomk mark: 'none' is then not available to them.
"""
import io
import json
import os
import re
import time
from typing import Any, Dict, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

from engine import watermark_spec as ws

USER_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")
MAX_LOGO_BYTES = 2 * 1024 * 1024
MAX_LOGO_PX = 2000        # either side of what may be uploaded
STORE_PX = 1024           # a stored logo is scaled down to at most this (the mark is never drawn bigger than ~160 px)
MIN_LOGO_PX = 16
LOGO_LINK_SECONDS = 300
_PNG, _JPEG = b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff"

_s3 = None
_ddb = None


class WatermarkError(Exception):
    """An error the API turns into a response: status, a message key (common/i18n) and a stable `code` for the apps."""

    def __init__(self, status: int, key: str, code: str = "", **params: Any):
        super().__init__(key)
        self.status, self.key, self.code, self.params = status, key, code, params


def s3():
    global _s3
    if _s3 is None:
        _s3 = boto3.client("s3")
    return _s3


def set_clients(s3_client: Any = None, ddb_resource: Any = None) -> None:   # tests
    global _s3, _ddb
    _s3, _ddb = s3_client, ddb_resource


def ddb():
    global _ddb
    if _ddb is None:
        _ddb = boto3.resource("dynamodb")
    return _ddb


def bucket() -> str:
    return os.environ["ASSETS_BUCKET"]


def check_user(user: Any) -> str:
    if not isinstance(user, str) or not USER_RE.match(user):
        raise WatermarkError(403, "err.forbidden")
    return user


def profile_key(user: str) -> str:
    return f"watermark/{check_user(user)}/profile.json"


def logo_key(user: str) -> str:
    return f"watermark/{check_user(user)}/logo.png"


# ----------------------------------------------------------------------------- policy
def enabled() -> bool:
    """On where the stack sets WATERMARK_ENABLED=1 (backend/watermark_feature.py, default on; `-c watermark=0` removes it). Unset: off, so nothing else changes."""
    return os.environ.get("WATERMARK_ENABLED", "0") == "1"


def force_policy() -> bool:
    """FORCE_WATERMARK=1: free-tier videos carry the videomk mark (owner switch, default off)."""
    return os.environ.get("FORCE_WATERMARK", "0") == "1"


def flags(user: str) -> Dict[str, Any]:
    if not os.environ.get("FLAGS_TABLE"):
        return {}
    return ddb().Table(os.environ["FLAGS_TABLE"]).get_item(Key={"user_id": check_user(user)}).get("Item") or {}


def is_premium(user: str, item: Optional[Dict[str, Any]] = None, now: Optional[float] = None) -> bool:
    item = flags(user) if item is None else item
    now = time.time() if now is None else now
    if item.get("watermark_custom") is True:
        return True
    until = item.get("storage_until")
    if item.get("storage_plan") == "pro" and (until is None or float(until) > now):
        return True
    return item.get("unlimited") is True and os.environ.get("ALLOW_UNLIMITED_ACCOUNTS", "0") == "1"


def capabilities(user: str, locale: Optional[str] = None) -> Dict[str, Any]:
    """The `watermark` block of GET /users/{user}/capabilities."""
    from common import i18n
    premium = is_premium(user)
    forced = force_policy() and not premium
    loc = i18n.normalize(locale) or i18n.DEFAULT
    modes = [{"id": "none", "available": not forced, "label": i18n.t("wm.mode.none", loc)},
             {"id": "videomk", "available": True, "label": i18n.t("wm.mode.videomk", loc)},
             {"id": "custom", "available": premium, "requires": "premium", "label": i18n.t("wm.mode.custom", loc)}]
    return {"modes": modes, "positions": list(ws.POSITIONS), "sizes": list(ws.SIZES), "styles": list(ws.STYLES),
            "opacity": {"min": ws.OPACITY_MIN, "max": ws.OPACITY_MAX, "default": ws.DEFAULT_OPACITY},
            "premium": premium, "forced": forced, "end_card": True,
            "logo": {"max_bytes": MAX_LOGO_BYTES, "max_px": MAX_LOGO_PX, "types": ["image/png", "image/jpeg", "image/svg+xml"]}}


def resolve(requested: Optional[Dict[str, Any]], profile: Optional[Dict[str, Any]], *, premium: bool, forced: bool, has_logo: bool) -> Dict[str, Any]:
    """The watermark a video gets. `requested`: what the request asked for (already cleaned) or None; `profile`: the person's saved default or None.
    An explicit 'custom' by someone who is not premium, or without a logo, is refused; a saved 'custom' that no longer applies (lapsed plan, deleted logo) quietly falls back."""
    explicit = requested is not None
    spec = dict(requested if explicit else (profile or {}))
    if not spec:
        spec = {"mode": "videomk"} if forced else {"mode": "none"}
    mode = spec.get("mode", "none")
    if mode == "custom" and (not premium or not has_logo):
        if explicit:
            if not premium:
                raise WatermarkError(403, "wm.premium", "watermark_premium")
            raise WatermarkError(400, "wm.logo_missing", "watermark_logo_missing")
        spec = {"mode": "videomk"} if forced else {"mode": "none"}
        mode = spec["mode"]
    if mode == "none" and forced:   # the owner's policy: a free account's video always carries the mark
        spec = {"mode": "videomk"}
    out = ws.parse(spec, strict=False) or {"mode": "none"}
    return out


# ----------------------------------------------------------------------------- profile and logo (S3)
def get_profile(user: str) -> Dict[str, Any]:
    try:
        raw = json.loads(s3().get_object(Bucket=bucket(), Key=profile_key(user))["Body"].read())
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("NoSuchKey", "404", "NotFound"):
            return {}
        raise
    except ValueError:
        return {}
    return ws.parse(raw, strict=False) or {}


def has_logo(user: str) -> bool:
    try:
        s3().head_object(Bucket=bucket(), Key=logo_key(user))
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") in ("404", "NoSuchKey", "NotFound"):
            return False
        raise


def put_profile(user: str, spec: Dict[str, Any]) -> None:
    s3().put_object(Bucket=bucket(), Key=profile_key(user), Body=json.dumps(spec).encode("utf-8"), ContentType="application/json")


def delete_profile(user: str) -> None:
    s3().delete_object(Bucket=bucket(), Key=profile_key(user))


def delete_logo(user: str) -> None:
    s3().delete_object(Bucket=bucket(), Key=logo_key(user))


def logo_link(user: str) -> Optional[str]:
    if not has_logo(user):
        return None
    return s3().generate_presigned_url("get_object", Params={"Bucket": bucket(), "Key": logo_key(user), "ResponseContentType": "image/png"}, ExpiresIn=LOGO_LINK_SECONDS)


def public_profile(user: str) -> Dict[str, Any]:
    """What GET /watermark returns: the saved settings (defaults filled in) and whether a logo is stored."""
    prof = get_profile(user)
    logo = has_logo(user)
    base = {"mode": "none", "position": "auto", "opacity": ws.DEFAULT_OPACITY, "size": "small", "style": "mark", "end_card": False}
    return {**base, **{k: v for k, v in prof.items() if k in base}, "has_logo": logo, **({"logo_url": logo_link(user)} if logo else {})}


# ----------------------------------------------------------------------------- the logo upload
def _sniff(data: bytes) -> str:
    head = data[:16]
    if head.startswith(_PNG):
        return "png"
    if head.startswith(_JPEG):
        return "jpeg"
    text = data[:2048].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if text.startswith(b"<svg") or (text.startswith(b"<?xml") and b"<svg" in data[:4096].lower()):
        return "svg"
    return ""


_SVG_BAD = re.compile(rb"<!doctype|<!entity|<script|<foreignobject|<iframe|<use[^>]+href=[\"'](?!#)|(?:xlink:)?href\s*=\s*[\"'](?!#|data:image/(?:png|jpeg);base64,)|@import|javascript:|url\(\s*[\"']?(?!#)", re.I)


def normalise_logo(data: bytes) -> Tuple[bytes, int, int]:
    """The uploaded bytes -> (PNG bytes, width, height), or a WatermarkError. The type is decided from the CONTENT (magic bytes), never from the name or the declared type;
    the image is decoded and re-encoded (so metadata and anything hidden in the file is gone), scaled down to at most STORE_PX and trimmed of empty margins.
    An SVG is refused if it can fetch anything, run anything or reference a file; the rest is drawn by resvg here, once, and only the PNG is stored."""
    from PIL import Image
    if not data or len(data) > MAX_LOGO_BYTES:
        raise WatermarkError(400, "wm.logo_size", "logo_too_big", mb=MAX_LOGO_BYTES // (1024 * 1024))
    kind = _sniff(data)
    if not kind:
        raise WatermarkError(400, "wm.logo_type", "logo_type")
    try:
        if kind == "svg":
            if _SVG_BAD.search(data):
                raise WatermarkError(400, "wm.logo_svg", "logo_svg")
            import resvg_py
            img = Image.open(io.BytesIO(bytes(resvg_py.svg_to_bytes(svg_string=data.decode("utf-8", "strict"), width=STORE_PX)))).convert("RGBA")
        else:
            limit = Image.MAX_IMAGE_PIXELS
            Image.MAX_IMAGE_PIXELS = MAX_LOGO_PX * MAX_LOGO_PX * 4   # the decoder refuses a decompression bomb before it allocates
            try:
                probe = Image.open(io.BytesIO(data))
                if max(probe.size) > MAX_LOGO_PX:
                    raise WatermarkError(400, "wm.logo_px", "logo_px", px=MAX_LOGO_PX)
                probe.verify()
                img = Image.open(io.BytesIO(data))
                img.load()
                img = img.convert("RGBA")
            finally:   # the limit is Pillow's process-wide setting: left lowered it made every later large canvas in the same process (a 4K frame is 33 M pixels) a "bomb"
                Image.MAX_IMAGE_PIXELS = limit
    except WatermarkError:
        raise
    except Exception:   # noqa: BLE001 - anything the decoder dislikes is just 'not an image'
        raise WatermarkError(400, "wm.logo_type", "logo_type") from None
    bbox = img.getchannel("A").getbbox()
    if not bbox:
        raise WatermarkError(400, "wm.logo_empty", "logo_empty")
    img = img.crop(bbox)
    if min(img.size) < 4 or max(img.size) < MIN_LOGO_PX:
        raise WatermarkError(400, "wm.logo_empty", "logo_empty")
    if max(img.size) > STORE_PX:
        k = STORE_PX / max(img.size)
        img = img.convert("RGBa").resize((max(1, int(img.width * k)), max(1, int(img.height * k))), Image.LANCZOS).convert("RGBA")
    out = io.BytesIO()
    img.save(out, "PNG", optimize=True)   # a fresh image: no EXIF, no text chunks, no profile
    return out.getvalue(), img.width, img.height


def put_logo(user: str, data: bytes) -> Dict[str, int]:
    png, w, h = normalise_logo(data)
    s3().put_object(Bucket=bucket(), Key=logo_key(user), Body=png, ContentType="image/png")
    return {"width": w, "height": h}
