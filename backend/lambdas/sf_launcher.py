"""POST /users/{user_id}/videos/generate   (also POST .../videos/{video_id}/retry and DELETE .../videos/{video_id}: lambdas/video_retry.py)

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
import plan_gate
import video_retry
from common import deck_limits, i18n, intake, library, safety, usage, wallet, watermark_store
from engine import format_options, watermark_spec
from common.photo_ids import MAX_PHOTOS, PhotoError, upload_key, valid_media_ids, valid_media_meta

logger = logging.getLogger()
logger.setLevel(logging.INFO)

DEFAULT_DECK_PROMPT = "Explain this presentation clearly for a general audience."
MIN_PROMPT_CHARS = 10
MAX_PROMPT_CHARS = 2000
_NAMESPACE = uuid.UUID("6f1d2f0e-6c1b-4a53-9a57-5c1b8d7c2a11")

_sfn = boto3.client("stepfunctions")
_s3 = boto3.client("s3")
_dynamodb = boto3.resource("dynamodb")


class BadRequest(Exception):
    """A 400. A protocol problem keeps its English text; a `Localized` message (something a person can cause) is shown in their language."""

    def __init__(self, message: Any = ""):
        self.localized = message if isinstance(message, i18n.Localized) else None
        super().__init__(str(message))


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
        raise BadRequest(i18n.Localized("create.prompt_min", min=MIN_PROMPT_CHARS))
    if len(prompt) > MAX_PROMPT_CHARS:
        raise BadRequest(i18n.Localized("create.prompt_max", max=MAX_PROMPT_CHARS))
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
    if body.get("deck") is not None:   # a prepared deck (POST .../decks, then .../process): its id; checked in the handler. A deck and photos are different stories: not both.
        if not isinstance(body["deck"], str) or not deck_limits.ID_RE.match(body["deck"]):
            raise BadRequest("'deck' must be a deck id")
        if out.get("media") or out.get("library_media"):
            raise BadRequest(i18n.Localized("deck.with_photos"))
        out["deck"] = body["deck"]
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
            raise BadRequest(i18n.Localized("create.language_unavailable"))
        out["language"] = lang
    for field, allowed in (("platform", format_options.PLATFORM_IDS), ("aspect", format_options.ASPECT_IDS), ("resolution", format_options.RESOLUTION_IDS)):
        if field in body and body[field] is not None:
            if not isinstance(body[field], str) or body[field] not in allowed:
                raise BadRequest(f"'{field}' must be one of: " + ", ".join(allowed))
            out[field] = body[field]
    if "style" in body and body["style"] is not None:   # the look of the scenes: 'auto' (the director decides, cartoon scenes only where the policy allows), 'cartoon' (illustrated), 'real' (photographs and footage only); docs/VECTOR_SCENE_POLICY.md
        if not isinstance(body["style"], str) or body["style"] not in ("auto", "cartoon", "real"):
            raise BadRequest("'style' must be one of: auto, cartoon, real")
        if body["style"] != "auto":
            out["style"] = body["style"]
    if out.get("aspect", format_options.DEFAULT_ASPECT) not in format_options.ready_aspects():
        raise BadRequest(i18n.Localized("create.format_unavailable"))
    if out.get("resolution", format_options.DEFAULT_RESOLUTION) not in format_options.ready_resolutions():   # 4K is on only where the server says so (READY_RESOLUTIONS)
        raise BadRequest(i18n.Localized("create.resolution_unavailable"))
    if "theme" in body and body["theme"] is not None:
        if body["theme"] not in THEMES:
            raise BadRequest("'theme' must be one of: " + ", ".join(THEMES))
        out["theme"] = body["theme"]
    if body.get("watermark") is not None:   # {mode, position, opacity, size, style, end_card}: docs/WATERMARK.md; who may use which mode is decided in the handler (it needs the account)
        try:
            out["watermark"] = watermark_spec.parse(body["watermark"], strict=True)
        except watermark_spec.WatermarkError as e:
            raise BadRequest(f"'watermark': {e}") from e
    return out


def apply_watermark(user_id: str, options: Dict[str, Any], loc: str) -> Optional[Dict[str, Any]]:
    """Settles the video's watermark (the request's own, else the person's saved default, else the stack policy) and puts the result in `options['watermark']`;
    nothing is added when the result is 'no watermark' (so a stack with the feature off sends exactly what it always sent). None, or the 4xx response to return."""
    if not watermark_store.enabled():
        options.pop("watermark", None)
        return None
    wr: Dict[str, Any] = {}
    try:
        wr = watermark_store.rights(user_id)   # by plan where plans are on (docs/PLANS.md), else the flags and the stack policy as before
        premium, forced = wr["premium"], wr["forced"]
        requested = options.get("watermark")
        profile = watermark_store.get_profile(user_id) if requested is None else None
        needs_logo = (requested or profile or {}).get("mode") == "custom"
        spec = watermark_store.resolve(requested, profile, premium=premium, forced=forced,
                                       has_logo=watermark_store.has_logo(user_id) if needs_logo else False, modes=wr.get("modes"))
        if forced and wr.get("by_plan"):
            spec = watermark_store.forced_spec(spec)
    except watermark_store.WatermarkError as e:
        by_plan = {"plan": wr.get("plan"), "can_upgrade": plan_gate.plans.PURCHASES_LIVE} if wr.get("by_plan") and "requires_plan" in e.extra else {}   # a plan refusal says the same as the others (docs/PLANS.md section 4)
        return json_response(e.status, {"message": i18n.t(e.key, loc, **e.params), **({"code": e.code} if e.code else {}), **e.extra, **by_plan})
    except Exception:   # noqa: BLE001 - a watermark lookup problem must never stop a video: the policy default decides
        logger.exception("WATERMARK_RESOLVE_FAILED user=%s", user_id)
        from common import plans as _plans
        spec = watermark_store.forced_spec({}) if _plans.enabled() else (dict(watermark_store.FORCED_SPEC) if watermark_store.force_policy() else {"mode": "none"})
    if spec.get("mode") == "none":
        options.pop("watermark", None)
    else:
        options["watermark"] = spec
    return None


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


def check_deck(user_id: str, options: Dict[str, Any], loc: str) -> Optional[Dict[str, Any]]:
    """None when the deck is ready and the length is set (the deck's suggested length unless the person chose one); else the 400 response. Only a deck under the
    caller's own prefix can be found, so another user's id is simply 'missing'."""
    if os.environ.get("DECKS_ENABLED") != "1":
        return json_response(404, {"code": "unavailable", "message": i18n.t("deck.unavailable", loc)})
    try:
        st = json.loads(_s3.get_object(Bucket=os.environ["ASSETS_BUCKET"], Key=deck_limits.status_key(user_id, options["deck"]))["Body"].read())
    except ClientError:
        return json_response(400, {"code": "deck_missing", "message": i18n.t("deck.missing", loc)})
    if st.get("status") == "failed":
        code = st.get("code") if st.get("code") in deck_limits.ERROR_CODES else "deck_corrupt"
        return json_response(400, {"code": code, "message": i18n.t(f"deck.err.{code}", loc, max_mb=deck_limits.MAX_MB, max_slides=deck_limits.MAX_SLIDES)})
    if st.get("status") != "ready":
        return json_response(409, {"code": "deck_not_ready", "message": i18n.t("deck.not_ready", loc)})
    if not options.get("target_minutes"):
        options["target_minutes"] = deck_limits.auto_minutes(int(st.get("slides") or 1), st.get("roles"))
    options["locale"] = loc
    return None


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


def _register_intent(user_id: str, prompt: str, video_id: str, usage_day: str, *, idempotent: bool, credits: int = 0, charge: Any = None, resolution: Optional[str] = None,
                     request: Optional[Dict[str, Any]] = None, extra: Optional[Dict[str, Any]] = None) -> None:
    item = {
        "video_id": video_id,
        "user_id": user_id,
        "prompt": prompt,
        "status": "STARTED_PROCESSING",
        "usage_day": usage_day,
        "credits_charged": credits,
        "charge": json.dumps(charge or []),  # exactly which buckets were charged, so a failure refunds exactly those
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        **(extra or {}),   # plans: which plan made it and how many of its credits were free ones (the free-usage reports read these)
    }
    if format_options.credits_multiplier(resolution) != 1:   # a 4K video: the record says why it cost double (other videos are recorded exactly as before)
        item.update({"resolution": resolution, "credits_multiplier": format_options.credits_multiplier(resolution)})
    if request is not None:   # what the workflow is started with, so "Try again" can run THIS video again (docs/CREATE_API.md, lambdas/video_retry.py)
        raw = json.dumps(request, sort_keys=True)
        if len(raw.encode("utf-8")) <= video_retry.MAX_REQUEST_BYTES:
            item["request_json"] = raw
        if request["options"].get("deck"):
            item["deck"] = True   # a presentation is used up when the video starts: its video cannot be retried
    kwargs: Dict[str, Any] = {"Item": item}
    if idempotent:
        kwargs["ConditionExpression"] = "attribute_not_exists(video_id)"
    _dynamodb.Table(os.environ.get("VIDEOS_TABLE", "Videos")).put_item(**kwargs)


def safety_gate(user_id: str, prompt: str, brief: Dict[str, Any], options: Dict[str, Any], locale: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """None to go on; else the response: 429 `paused` for a paused or held account, 400 `blocked` (recorded) for a request that must be stopped.
    One attempt with a 4 s timeout, then the deterministic screen (no retry here: the function has a 10 s budget and a clear prompt must never wait on this)."""
    if not safety.enabled():
        return None
    lang = locale or safety.guess_language(prompt, options.get("language"))   # the app's language (X-Locale) when it sends one, else the language of the request
    stopped = intake.paused(user_id, lang)
    if stopped:
        return json_response(429, stopped, {"Retry-After": str(stopped["retry_after"])})
    chk = intake.check(prompt + " " + intake.brief_text(brief) if brief else prompt, options={}, attempts=1)
    if chk.block:
        return json_response(400, intake.stop(user_id, chk, prompt, lang))
    return None


def handler(event: Dict[str, Any], context: Any):
    resource, method = str((event or {}).get("resource") or ""), str((event or {}).get("httpMethod") or "").upper()
    if resource.endswith("/{video_id}/retry"):   # POST /users/{user_id}/videos/{video_id}/retry: the same video again (lambdas/video_retry.py)
        return video_retry.retry_handler(event, context)
    if resource.endswith("/{video_id}/cancel"):   # POST /users/{user_id}/videos/{video_id}/cancel: stop a video that is being made, credits back
        return video_retry.cancel_handler(event, context)
    if resource.endswith("/{video_id}") and method == "DELETE":   # DELETE /users/{user_id}/videos/{video_id}: remove a video (finished, failed, cancelled or rejected) and its files
        return video_retry.delete_handler(event, context)
    path_user_id = ((event or {}).get("pathParameters") or {}).get("user_id")
    auth_user_id = extract_cognito_sub(event)
    loc = i18n.pick_locale(event)

    if not auth_user_id:
        return json_response(401, {"message": i18n.t("err.unauthorized", loc)})
    if not path_user_id or path_user_id != auth_user_id:
        return json_response(403, {"message": i18n.t("err.forbidden", loc)})
    user_id = auth_user_id

    try:
        body = parse_body(event)
        if body.get("deck") is not None and not body.get("prompt"):   # a deck needs no description: the request only steers audience and tone
            body = {**body, "prompt": DEFAULT_DECK_PROMPT}
        prompt = validate_prompt(body)
        options = validate_options(body)
        brief = intake.clean_brief(body.get("brief"))   # the answers to the clarifying questions: known keys, short strings, at most 2 KB
    except (BadRequest, intake.Invalid) as e:
        return json_response(400, {"message": i18n.error_text(e, loc)})

    sm_arn = os.environ.get("STATE_MACHINE_ARN")
    if not sm_arn:
        logger.error("STATE_MACHINE_ARN is not configured")
        return json_response(500, {"message": i18n.t("err.server_config", loc)})

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
    gated = safety_gate(user_id, prompt, brief, options, i18n.explicit_locale(event))
    if gated:
        return gated
    if brief:
        options["brief"] = brief

    explicit_length = options.get("target_minutes") is not None
    if options.get("deck"):
        bad = check_deck(user_id, options, loc)
        if bad:
            return bad
    # The plan's limits (docs/PLANS.md): length, resolution, photos per video. Before any charge, copy or duplicate claim; nothing happens where plans are off.
    gate = plan_gate.begin(user_id, event)
    refused = plan_gate.check(gate, options, loc, explicit_length=explicit_length, default_minutes=float(os.environ.get("DEFAULT_TARGET_MINUTES", "3")))
    if refused:
        return refused
    for mid in options.get("media", []):  # every photo must really be uploaded, into this user's own folder
        try:
            _s3.head_object(Bucket=os.environ["ASSETS_BUCKET"], Key=upload_key(user_id, mid))
        except ClientError:
            return json_response(400, {"message": i18n.t("create.photo_unfinished", loc)})

    bad_wm = apply_watermark(user_id, options, loc)
    if bad_wm:
        return bad_wm

    library_ids = list(options.get("library_media") or [])   # kept for a retry: their 2-day working copies can be made again from the library
    try:
        if not bring_library_photos(user_id, options):
            return json_response(400, {"message": i18n.t("create.photo_missing", loc)})
    except ClientError:
        logger.exception("could not copy library photos")
        return json_response(500, {"message": i18n.t("create.photo_prepare", loc)})

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
        if gate is not None:
            charged, refused = plan_gate.charge(gate, user_id, credits, loc, tz=request_timezone(event))
            if refused:
                usage.release_recent(user_id, fingerprint)
                return refused
        else:
            charged = wallet.charge(user_id, credits, tz=request_timezone(event))
        if credits and not charged:  # nothing was taken: an unlimited (test/staff) account. Keep a ceiling and a trail in case its token is ever stolen.
            logger.warning("UNLIMITED_ACCOUNT_USE user=%s credits=%s minutes=%s", user_id, credits, minutes)
            usage.consume(f"unlimited:{user_id}", limit=int(os.environ.get("UNLIMITED_DAILY_VIDEOS", "50")))
    except usage.QuotaExceeded:
        usage.release_recent(user_id, fingerprint)
        return json_response(429, {"message": i18n.t("create.test_limit", loc)}, {"Retry-After": "3600"})
    except wallet.InsufficientCredits as e:
        usage.release_recent(user_id, fingerprint)
        return json_response(402, {"message": i18n.t("create.credits_needed", loc, needed=e.needed, balance=e.balance),
                                   "code": "insufficient_credits", "balance": e.balance, "needed": e.needed,
                                   **({"plan": gate.plan, "can_upgrade": plan_gate.plans.PURCHASES_LIVE} if gate is not None else {}),
                                   **({"resolution": resolution, "credits_multiplier": multiplier} if multiplier != 1 else {})})

    try:
        _register_intent(user_id, prompt, video_id, usage_day, idempotent=idempotent, credits=credits, charge=charged, resolution=resolution,
                         request={"options": options, "library_media": library_ids}, extra=plan_gate.record(gate, credits))
        resp = _sfn.start_execution(
            stateMachineArn=sm_arn,
            name=video_id,  # one execution per video; duplicate starts fail fast
            input=json.dumps({"user_id": user_id, "video_id": video_id, "prompt": prompt, "usage_day": usage_day, **options}),
        )
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code in ("ConditionalCheckFailedException", "ExecutionAlreadyExists"):
            wallet.refund(user_id, charged)
            plan_gate.give_back(gate)
            return json_response(202, {"message": "workflow already started", "video_id": video_id})
        logger.exception("Failed to start workflow")
        wallet.refund(user_id, charged)
        plan_gate.give_back(gate)
        usage.release_recent(user_id, fingerprint)
        return json_response(500, {"message": i18n.t("create.start_failed", loc)})
    except Exception:
        logger.exception("Failed to start workflow")
        wallet.refund(user_id, charged)
        plan_gate.give_back(gate)
        usage.release_recent(user_id, fingerprint)
        return json_response(500, {"message": i18n.t("create.start_failed", loc)})

    start_date = resp.get("startDate")
    return json_response(
        202,
        {
            "message": "workflow started",
            "video_id": video_id,
            "startDate": start_date.isoformat() if hasattr(start_date, "isoformat") else "",
        },
    )
