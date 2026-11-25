"""POST /users/{user_id}/videos/generate

Validates the caller, enforces the daily quota, registers the video item and
starts the Step Functions workflow. Only the minimum (user_id, video_id, prompt)
is passed to the state machine: never request headers (they carry the user's JWT
and would be stored in execution history).
"""
import hashlib
import json
import logging
import os
import time
import uuid
from typing import Any, Dict, Optional, Tuple

import boto3
from botocore.exceptions import ClientError

from common.http import json_response
from common.identity import extract_cognito_sub
from common import intake, library, safety, usage, wallet
from engine import format_options
from common.photo_ids import MAX_PHOTOS, PhotoError, upload_key, valid_media_ids, valid_media_meta

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MIN_PROMPT_CHARS = 10
MAX_PROMPT_CHARS = 2000
_NAMESPACE = uuid.UUID("6f1d2f0e-6c1b-4a53-9a57-5c1b8d7c2a11")

_sfn = boto3.client("stepfunctions")
_s3 = boto3.client("s3")
_dynamodb = boto3.resource("dynamodb")


class BadRequest(Exception):
    pass


def parse_body(event: Dict[str, Any]) -> Dict[str, Any]:
    body = event.get("body")
    if isinstance(body, str):
        try:
            body = json.loads(body or "{}")
        except json.JSONDecodeError as e:
            raise BadRequest("Body must be valid JSON") from e
    if not isinstance(body, dict):
        raise BadRequest("Body must be a JSON object")
    return body


def validate_prompt(body: Dict[str, Any]) -> str:
    prompt = body.get("prompt")
    if not isinstance(prompt, str):
        raise BadRequest("'prompt' is required")
    prompt = " ".join(prompt.split())  # collapse whitespace/control chars
    if len(prompt) < MIN_PROMPT_CHARS:
        raise BadRequest(f"'prompt' must be at least {MIN_PROMPT_CHARS} characters")
    if len(prompt) > MAX_PROMPT_CHARS:
        raise BadRequest(f"'prompt' must be at most {MAX_PROMPT_CHARS} characters")
    return prompt


def request_region(event: Dict[str, Any]) -> Optional[str]:
    """Where the viewer is, as an ISO country code, for default voice accents only. The app sends its device region (the user's own setting);
    CloudFront's viewer country is used if the API is ever served through CloudFront. Never trusted for anything but voice choice."""
    headers = {str(k).lower(): v for k, v in ((event or {}).get("headers") or {}).items()}
    for name in ("x-region", "cloudfront-viewer-country"):
        value = str(headers.get(name) or "").strip().upper()
        if len(value) == 2 and value.isalpha():
            return value
    return None


THEMES = ("midnight", "paper", "sunrise")
MIN_MINUTES, MAX_MINUTES = 0.25, 12.0   # 15 seconds to 12 minutes; credits are still the started minutes, minimum 1 (common/wallet.py)
MAX_IMAGES_PER_MINUTE = 10.0   # the ceiling a request can ask for; the planner treats it as a maximum, never a target


def validate_options(body: Dict[str, Any]) -> Dict[str, Any]:
    """Optional create options. Absent means the server default; present but invalid is a 400, never silently ignored."""
    out: Dict[str, Any] = {}
    if "target_minutes" in body and body["target_minutes"] is not None:
        m = body["target_minutes"]
        if isinstance(m, bool) or not isinstance(m, (int, float)) or not (MIN_MINUTES <= m <= MAX_MINUTES):
            raise BadRequest(f"'target_minutes' must be a number from {MIN_MINUTES:g} to {MAX_MINUTES:g}")
        out["target_minutes"] = float(m)
    if body.get("media") is not None:
        try:
            out["media"] = valid_media_ids(body["media"])
            meta = valid_media_meta(body.get("media_meta"), out["media"])
            if meta:
                out["media_meta"] = meta   # capture time and approximate place of the photos, only when the person allowed it in Settings
        except PhotoError as e:
            raise BadRequest(str(e)) from e
    if body.get("library_media") is not None:   # photos already in the person's own library: checked and copied in the handler
        try:
            out["library_media"] = valid_media_ids(body["library_media"])
        except PhotoError as e:
            raise BadRequest(str(e).replace("'media'", "'library_media'")) from e
    if len(out.get("media", [])) + len(out.get("library_media", [])) > MAX_PHOTOS:
        raise BadRequest(f"at most {MAX_PHOTOS} photos per video")
    if set(out.get("media", [])) & set(out.get("library_media", [])):
        raise BadRequest("a photo cannot be in both 'media' and 'library_media'")
    if "captions" in body and body["captions"] is not None:
        if not isinstance(body["captions"], bool):
            raise BadRequest("'captions' must be true or false")
        out["captions"] = body["captions"]
    if "max_images_per_minute" in body and body["max_images_per_minute"] is not None:
        m = body["max_images_per_minute"]
        if isinstance(m, bool) or not isinstance(m, (int, float)) or not (0 <= m <= MAX_IMAGES_PER_MINUTE):
            raise BadRequest(f"'max_images_per_minute' must be a number from 0 to {MAX_IMAGES_PER_MINUTE:g}")
        out["max_images_per_minute"] = float(m)
    if "language" in body and body["language"] is not None:   # 'auto' (the default) keeps the detection from the description; an explicit language overrides it
        lang = body["language"]
        if not isinstance(lang, str) or (lang != "auto" and lang not in format_options.LANGUAGE_LABELS):
            raise BadRequest("'language' must be 'auto' or one of: " + ", ".join(format_options.LANGUAGE_LABELS))
        if lang != "auto" and lang not in format_options.ready_languages():
            raise BadRequest("This language is not available yet")
        out["language"] = lang
    for field, allowed in (("platform", format_options.PLATFORM_IDS), ("aspect", format_options.ASPECT_IDS), ("resolution", format_options.RESOLUTION_IDS)):
        if field in body and body[field] is not None:
            if not isinstance(body[field], str) or body[field] not in allowed:
                raise BadRequest(f"'{field}' must be one of: " + ", ".join(allowed))
            out[field] = body[field]
    if out.get("aspect", format_options.DEFAULT_ASPECT) not in format_options.ready_aspects():
        raise BadRequest("This format is not available yet")
    if out.get("resolution", format_options.DEFAULT_RESOLUTION) not in format_options.ready_resolutions():   # 4K is on only where the server says so (READY_RESOLUTIONS)
        raise BadRequest("This resolution is not available yet")
    if "theme" in body and body["theme"] is not None:
        if body["theme"] not in THEMES:
            raise BadRequest("'theme' must be one of: " + ", ".join(THEMES))
        out["theme"] = body["theme"]
    return out


def bring_library_photos(user_id: str, options: Dict[str, Any]) -> bool:
    """Copies the chosen library photos into the video's own uploads (so the engine reads them like any other photo) and gives them their capture time and place name
    (the library keeps only names, never coordinates). Every id must be a ready photo of THIS user, else nothing is copied. Returns False when one is not."""
    ids = options.pop("library_media", None) or []
    if not ids:
        return True
    found = library.batch_get(user_id, ids)
    if len(found) != len(ids):
        return False
    meta = dict(options.get("media_meta") or {})
    for mid in ids:
        _s3.copy_object(CopySource={"Bucket": os.environ["MEDIA_BUCKET"], "Key": library.orig_key(user_id, mid)}, Bucket=os.environ["ASSETS_BUCKET"], Key=upload_key(user_id, mid),
                        ContentType="image/jpeg", MetadataDirective="REPLACE")
        it = found[mid]
        row = {k: v for k, v in (("taken", it.get("taken")), ("where", it.get("pl"))) if v}
        if row:
            meta[mid] = row
    options["media"] = list(options.get("media", [])) + ids
    if meta:
        options["media_meta"] = meta
    return True


def video_id_for(user_id: str, body: Dict[str, Any]) -> Tuple[str, bool]:
    """Deterministic id when the client sends `client_request_id` (double-click safe)."""
    crid = body.get("client_request_id")
    if isinstance(crid, str) and 8 <= len(crid) <= 64:
        return str(uuid.uuid5(_NAMESPACE, f"{user_id}:{crid}")), True
    return str(uuid.uuid4()), False


def request_timezone(event: Dict[str, Any]) -> Optional[str]:
    """The user's IANA timezone (X-Timezone), only to decide where their local day ends for the daily free credits."""
    headers = {str(k).lower(): v for k, v in ((event or {}).get("headers") or {}).items()}
    tz = str(headers.get("x-timezone") or "").strip()
    return tz if 1 <= len(tz) <= 40 and all(ch.isalnum() or ch in "/_+-" for ch in tz) else None


def _register_intent(user_id: str, prompt: str, video_id: str, usage_day: str, *, idempotent: bool, credits: int = 0, charge: Any = None, resolution: Optional[str] = None) -> None:
    item = {
        "video_id": video_id,
        "user_id": user_id,
        "prompt": prompt,
        "status": "STARTED_PROCESSING",
        "usage_day": usage_day,
        "credits_charged": credits,
        "charge": json.dumps(charge or []),  # exactly which buckets were charged, so a failure refunds exactly those
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if format_options.credits_multiplier(resolution) != 1:   # a 4K video: the record says why it cost double (other videos are recorded exactly as before)
        item.update({"resolution": resolution, "credits_multiplier": format_options.credits_multiplier(resolution)})
    kwargs: Dict[str, Any] = {"Item": item}
    if idempotent:
        kwargs["ConditionExpression"] = "attribute_not_exists(video_id)"
    _dynamodb.Table(os.environ.get("VIDEOS_TABLE", "Videos")).put_item(**kwargs)


def safety_gate(user_id: str, prompt: str, brief: Dict[str, Any], options: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """None to go on; else the response: 429 `paused` for a paused or held account, 400 `blocked` (recorded) for a request that must be stopped.
    One attempt with a 4 s timeout, then the deterministic screen (no retry here: the function has a 10 s budget and a clear prompt must never wait on this)."""
    if not safety.enabled():
        return None
    lang = safety.guess_language(prompt, options.get("language"))
    stopped = intake.paused(user_id, lang)
    if stopped:
        return json_response(429, stopped, {"Retry-After": str(stopped["retry_after"])})
    chk = intake.check(prompt + " " + intake.brief_text(brief) if brief else prompt, options={}, attempts=1)
    if chk.block:
        return json_response(400, intake.stop(user_id, chk, prompt, lang))
    return None


def handler(event: Dict[str, Any], context: Any):
    path_user_id = ((event or {}).get("pathParameters") or {}).get("user_id")
    auth_user_id = extract_cognito_sub(event)

    if not auth_user_id:
        return json_response(401, {"message": "Unauthorized"})
    if not path_user_id or path_user_id != auth_user_id:
        return json_response(403, {"message": "Forbidden"})
    user_id = auth_user_id

    try:
        body = parse_body(event)
        prompt = validate_prompt(body)
        options = validate_options(body)
        brief = intake.clean_brief(body.get("brief"))   # the answers to the clarifying questions: known keys, short strings, at most 2 KB
    except BadRequest as e:
        return json_response(400, {"message": str(e)})
    except intake.Invalid as e:
        return json_response(400, {"message": str(e)})

    sm_arn = os.environ.get("STATE_MACHINE_ARN")
    if not sm_arn:
        logger.error("STATE_MACHINE_ARN is not configured")
        return json_response(500, {"message": "Server configuration error"})

    region = request_region(event)
    if region:
        options["region"] = region
    video_id, idempotent = video_id_for(user_id, body)
    usage_day = time.strftime("%Y-%m-%d", time.gmtime())

    # Idempotent replay: the same client_request_id returns the existing job without re-billing.
    if idempotent:
        existing = _dynamodb.Table(os.environ.get("VIDEOS_TABLE", "Videos")).get_item(Key={"video_id": video_id}).get("Item")
        if existing:
            return json_response(202, {"message": "workflow already started", "video_id": video_id})

    # Safety gate: before any charge, copy or duplicate claim. The same check as POST .../videos/brief, so skipping `brief` skips nothing.
    gated = safety_gate(user_id, prompt, brief, options)
    if gated:
        return gated
    if brief:
        options["brief"] = brief

    for mid in options.get("media", []):  # every photo must really be uploaded, into this user's own folder
        try:
            _s3.head_object(Bucket=os.environ["ASSETS_BUCKET"], Key=upload_key(user_id, mid))
        except ClientError:
            return json_response(400, {"message": "One of your photos didn't finish uploading. Please try again."})

    try:
        if not bring_library_photos(user_id, options):
            return json_response(400, {"message": "One of the photos you chose is no longer in your library."})
    except ClientError:
        logger.exception("could not copy library photos")
        return json_response(500, {"message": "Could not prepare your photos. Please try again."})

    # The same request twice within two minutes (a double tap, text that reappeared after sending) is one video: the second returns the first, charges nothing.
    fingerprint = hashlib.sha1(json.dumps([prompt.lower(), {k: options[k] for k in sorted(options) if k not in ("region",)}], sort_keys=True).encode("utf-8")).hexdigest()
    first = usage.claim_recent(user_id, fingerprint, video_id, window_s=int(os.environ.get("DUPLICATE_WINDOW_S", "120")))
    if first and first != video_id:
        logger.warning("duplicate request from %s returned the video already started (%s)", user_id, first)
        return json_response(202, {"message": "workflow already started", "video_id": first})

    # Quote, then charge exactly the quote: the length that is billed is the length that is made.
    minutes = options.get("target_minutes") or float(os.environ.get("DEFAULT_TARGET_MINUTES", "3"))
    options["target_minutes"] = minutes
    resolution = options.get("resolution")
    credits = wallet.credits_for_minutes(minutes, resolution)   # 4K costs double; the rule lives in the wallet
    multiplier = format_options.credits_multiplier(resolution)
    try:
        charged = wallet.charge(user_id, credits, tz=request_timezone(event))
        if credits and not charged:  # nothing was taken: an unlimited (test/staff) account. Keep a ceiling and a trail in case its token is ever stolen.
            logger.warning("UNLIMITED_ACCOUNT_USE user=%s credits=%s minutes=%s", user_id, credits, minutes)
            usage.consume(f"unlimited:{user_id}", limit=int(os.environ.get("UNLIMITED_DAILY_VIDEOS", "50")))
    except usage.QuotaExceeded:
        usage.release_recent(user_id, fingerprint)
        return json_response(429, {"message": "Daily limit for this test account reached."}, {"Retry-After": "3600"})
    except wallet.InsufficientCredits as e:
        usage.release_recent(user_id, fingerprint)
        return json_response(402, {"message": f"This video needs {e.needed} credit{'s' if e.needed != 1 else ''} and you have {e.balance}.",
                                   "code": "insufficient_credits", "balance": e.balance, "needed": e.needed,
                                   **({"resolution": resolution, "credits_multiplier": multiplier} if multiplier != 1 else {})})

    try:
        _register_intent(user_id, prompt, video_id, usage_day, idempotent=idempotent, credits=credits, charge=charged, resolution=resolution)
        resp = _sfn.start_execution(
            stateMachineArn=sm_arn,
            name=video_id,  # one execution per video; duplicate starts fail fast
            input=json.dumps({"user_id": user_id, "video_id": video_id, "prompt": prompt, "usage_day": usage_day, **options}),
        )
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code in ("ConditionalCheckFailedException", "ExecutionAlreadyExists"):
            wallet.refund(user_id, charged)
            return json_response(202, {"message": "workflow already started", "video_id": video_id})
        logger.exception("Failed to start workflow")
        wallet.refund(user_id, charged)
        usage.release_recent(user_id, fingerprint)
        return json_response(500, {"message": "Failed to start workflow"})
    except Exception:
        logger.exception("Failed to start workflow")
        wallet.refund(user_id, charged)
        usage.release_recent(user_id, fingerprint)
        return json_response(500, {"message": "Failed to start workflow"})

    start_date = resp.get("startDate")
    return json_response(
        202,
        {
            "message": "workflow started",
            "video_id": video_id,
            "startDate": start_date.isoformat() if hasattr(start_date, "isoformat") else "",
        },
    )
