"""The person's watermark settings and logo, who may use which mode, and the rule that turns a request into the watermark a video gets (docs/WATERMARK.md).

Stored privately in the assets bucket under `watermark/<user>/` (profile.json and logo.png); nothing is public and nothing is ever served back except a short-lived link to the person's own logo.
Entitlements come from the admin-written flags table (read only at runtime, like unlimited credits): the 'custom' mode is premium, i.e. any of
  flags.watermark_custom = true        (scripts/wallet_admin.py watermark <who> on)
  an active Pro library plan           (flags.storage_plan = 'pro', not lapsed)
  an unlimited test account            (flags.unlimited, only where ALLOW_UNLIMITED_ACCOUNTS=1, never in production)
The policy hook FORCE_WATERMARK=1 (stack context `forceWatermark=1`, default off) makes every video of a NON-premium account carry the videomk mark: 'none' is then not available to them.

Where plans are on (docs/PLANS.md) the PLAN decides instead, through `rights()`: Free = the videomk mark with the name and the end card, always; Pro = may remove it (and the
gentle 'moments' mode once the engine has it); Max = also its own logo. The admin flag `watermark_custom` stays an override (own logo, nothing forced) and an unlimited test
account has the rights of Max. An active Pro STORAGE flag no longer gives the logo there (owner decision 6 of the plans proposal: own logo is Max only).
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

    def __init__(self, status: int, key: str, code: str = "", extra: Optional[Dict[str, Any]] = None, **params: Any):
        super().__init__(key)
        self.status, self.key, self.code, self.params, self.extra = status, key, code, params, extra or {}   # extra: fields for the response body (which plan unlocks it)


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


# What a free (non-premium) account's video carries where the stack forces the mark (owner decision 2026-11-27, docs/WATERMARK.md section 5): the videomk lockup
# (mark + the word), small, in the quiet corner of the shape, there for the whole video, and the closing "Made with videomk" card. Nothing of it can be chosen away.
FORCED_SPEC: Dict[str, Any] = {"mode": "videomk", "style": "lockup", "presence": "always", "end_card": True, "position": "auto", "size": "small", "opacity": ws.DEFAULT_OPACITY}
PREMIUM_DEFAULT_PRESENCE = "moments"   # a premium account that keeps the videomk mark gets the gentle form unless it says otherwise
def rights(user: str, item: Optional[Dict[str, Any]] = None, now: Optional[float] = None) -> Dict[str, Any]:
    """{premium (own logo), forced (the videomk mark cannot be removed), modes (the modes the plan allows, None where plans are off), by_plan, plan}."""
    from common import plans
    if not plans.enabled():
        premium = is_premium(user, item, now)
        return {"premium": premium, "forced": force_policy() and not premium, "modes": None, "by_plan": False, "plan": None}
    from common import entitlements
    item = flags(user) if item is None else item
    unlimited = item.get("unlimited") is True and os.environ.get("ALLOW_UNLIMITED_ACCOUNTS", "0") == "1"
    ent = entitlements.effective(user, now=now, unlimited=unlimited)
    cfg = plans.config()
    r = plans.rights(ent["plan"], cfg)
    modes, forced = list(r["watermark_modes"]), bool(r["watermark_forced"]) and bool(cfg["enforce"])
    if not cfg["enforce"]:
        modes = list(plans.PLANS["pro"]["watermark_modes"]) if "none" not in modes else modes
    if item.get("watermark_custom") is True:   # the admin's override: own logo, and the mark is not forced
        modes, forced = sorted(set(modes) | {"none", "videomk", "custom"}), False
    return {"premium": "custom" in modes, "forced": forced, "modes": modes, "by_plan": True, "plan": ent["plan"]}


def _plan_for_mode(mode: str) -> Optional[str]:
    from common import plans
    return plans.lowest_plan(lambda x: mode in x["watermark_modes"])


def forced_spec(spec: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """The Free plan's watermark: the videomk mark WITH the name and the end card. The person keeps the corner and the size; the opacity never goes under the default."""
    keep = {k: v for k, v in (spec or {}).items() if k in ("position", "size")}
    opacity = max(float((spec or {}).get("opacity") or ws.DEFAULT_OPACITY), ws.DEFAULT_OPACITY)
    return ws.parse({**keep, "mode": "videomk", "style": "lockup", "presence": "always", "end_card": True, "opacity": opacity}, strict=False) or {"mode": "videomk"}   # there for the whole video: 'moments' is a paid plan's right


def capabilities(user: str, locale: Optional[str] = None) -> Dict[str, Any]:
    """The `watermark` block of GET /users/{user}/capabilities."""
    from common import i18n
    wr = rights(user)
    premium, forced = wr["premium"], wr["forced"]
    loc = i18n.normalize(locale) or i18n.DEFAULT
    modes = [{"id": "none", "available": not forced and (wr["modes"] is None or "none" in wr["modes"]), "label": i18n.t("wm.mode.none", loc)},
             {"id": "videomk", "available": True, "label": i18n.t("wm.mode.videomk", loc)},
             {"id": "custom", "available": premium, "requires": "premium", "label": i18n.t("wm.mode.custom", loc)}]
    may_moments = (not forced) if not wr["by_plan"] else ("moments" in wr["modes"] and not forced)   # 'moments' is the `presence` of the videomk mark (not a mode): by plan where plans are on
    if wr["by_plan"]:   # which plan unlocks each mode, so the apps can put its name on the option
        for m in modes:
            m["requires_plan"] = None if m["available"] else _plan_for_mode(m["id"])
    return {"modes": modes, "positions": list(ws.POSITIONS), "sizes": list(ws.SIZES), "styles": list(ws.STYLES),
            "style_options": [{"id": "mark", "available": not forced, "label": i18n.t("wm.style.mark", loc)}, {"id": "lockup", "available": True, "label": i18n.t("wm.style.lockup", loc)}],
            "presences": [{"id": "always", "available": True, "label": i18n.t("wm.presence.always", loc), "note": i18n.t("wm.presence.always_note", loc)},
                          {"id": "moments", "available": may_moments, **({"requires": "premium"} if not may_moments else {}), **({"requires_plan": None if may_moments else _plan_for_mode("moments")} if wr["by_plan"] else {}),
                           "label": i18n.t("wm.presence.moments", loc), "note": i18n.t("wm.presence.moments_note", loc)}],
            "default_presence": PREMIUM_DEFAULT_PRESENCE if may_moments and (premium or wr["by_plan"]) else "always",
            "opacity": {"min": ws.OPACITY_MIN, "max": ws.OPACITY_MAX, "default": ws.DEFAULT_OPACITY},
            "premium": premium, "forced": forced, "end_card": True,
            **({"forced_watermark": dict(FORCED_SPEC), "forced_note": i18n.t("wm.forced_note", loc)} if forced else {}),
            "logo": {"max_bytes": MAX_LOGO_BYTES, "max_px": MAX_LOGO_PX, "types": ["image/png", "image/jpeg", "image/svg+xml"]}}


def resolve(requested: Optional[Dict[str, Any]], profile: Optional[Dict[str, Any]], *, premium: bool, forced: bool, has_logo: bool, modes: Optional[list] = None) -> Dict[str, Any]:
    """The watermark a video gets. `requested`: what the request asked for (already cleaned) or None; `profile`: the person's saved default or None.
    An explicit 'custom' by someone who is not premium, or without a logo, is refused; a saved 'custom' that no longer applies (lapsed plan, deleted logo) quietly falls back.
    `forced` (a free account where the stack forces the mark): always exactly FORCED_SPEC, whatever was asked or saved. A premium account's videomk mark without a
    stated presence is 'moments'; everyone else's is 'always'."""
    explicit = requested is not None
    spec = dict(requested if explicit else (profile or {}))
    if not spec:
        spec = {"mode": "videomk"} if forced else {"mode": "none"}
    mode = spec.get("mode", "none")
    if modes is not None and explicit and mode != "custom" and mode not in modes:   # plans: an explicit request for a mode the plan lacks is refused with the plan that has it
        raise WatermarkError(403, "plan.watermark", "plan_watermark", extra={"feature": "watermark", "requires_plan": _plan_for_mode(mode)})
    if modes is not None and not explicit and mode not in modes and mode != "custom":   # a saved setting from a plan that ended: falls back quietly
        spec = {"mode": "videomk"} if forced else {"mode": "none"}
        mode = spec["mode"]
    if mode == "custom" and (not premium or not has_logo):
        if explicit:
            if not premium:
                raise WatermarkError(403, "wm.premium_max" if modes is not None else "wm.premium", "watermark_premium", extra={"feature": "watermark", "requires_plan": _plan_for_mode("custom")} if modes is not None else None)
            raise WatermarkError(400, "wm.logo_missing", "watermark_logo_missing")
        spec = {"mode": "videomk"} if forced else {"mode": "none"}
        mode = spec["mode"]
    if forced and modes is None:   # the owner's policy where plans are off: a free account's video always carries the name, for the whole video, with the closing card; nothing asked or saved changes it
        return ws.parse(FORCED_SPEC, strict=False) or dict(FORCED_SPEC)   # (with plans on, the launcher applies forced_spec to what comes out below: the same mark, and the person keeps the corner and the size)
    may_moments = premium if modes is None else "moments" in modes   # the right to a mark that comes and goes: premium where plans are off, the plan's own list where they are on
    if mode == "videomk" and spec.get("presence") == "moments" and modes is not None and not may_moments:
        if explicit:
            raise WatermarkError(403, "plan.watermark", "plan_watermark", extra={"feature": "watermark", "requires_plan": _plan_for_mode("moments")})
        spec.pop("presence", None)   # a saved setting from a plan that ended
    if mode == "videomk" and spec.get("presence") not in ws.PRESENCES and may_moments:
        spec["presence"] = PREMIUM_DEFAULT_PRESENCE   # (everyone else: absent, which is 'always', exactly as before the option existed)
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
    return {**base, **{k: v for k, v in prof.items() if k in base}, **({"presence": prof["presence"]} if prof.get("presence") in ws.PRESENCES else {}),
            "has_logo": logo, **({"logo_url": logo_link(user)} if logo else {})}


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
