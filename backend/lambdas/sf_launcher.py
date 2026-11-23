"""POST /users/{user_id}/videos/generate

Validates the caller, enforces the daily quota, registers the video item and
starts the Step Functions workflow. Only the minimum (user_id, video_id, prompt)
is passed to the state machine: never request headers (they carry the user's JWT
and would be stored in execution history).
"""
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
from common import usage, wallet

logger = logging.getLogger()
logger.setLevel(logging.INFO)

MIN_PROMPT_CHARS = 10
MAX_PROMPT_CHARS = 2000
_NAMESPACE = uuid.UUID("6f1d2f0e-6c1b-4a53-9a57-5c1b8d7c2a11")

_sfn = boto3.client("stepfunctions")
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
MIN_MINUTES, MAX_MINUTES = 1.0, 12.0


def validate_options(body: Dict[str, Any]) -> Dict[str, Any]:
    """Optional create options. Absent means the server default; present but invalid is a 400, never silently ignored."""
    out: Dict[str, Any] = {}
    if "target_minutes" in body and body["target_minutes"] is not None:
        m = body["target_minutes"]
        if isinstance(m, bool) or not isinstance(m, (int, float)) or not (MIN_MINUTES <= m <= MAX_MINUTES):
            raise BadRequest(f"'target_minutes' must be a number from {MIN_MINUTES:g} to {MAX_MINUTES:g}")
        out["target_minutes"] = float(m)
    if "language" in body and body["language"] is not None:
        if body["language"] not in ("en", "es"):
            raise BadRequest("'language' must be 'en' or 'es'")
        out["language"] = body["language"]
    if "theme" in body and body["theme"] is not None:
        if body["theme"] not in THEMES:
            raise BadRequest("'theme' must be one of: " + ", ".join(THEMES))
        out["theme"] = body["theme"]
    return out


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


def _register_intent(user_id: str, prompt: str, video_id: str, usage_day: str, *, idempotent: bool, credits: int = 0, charge: Any = None) -> None:
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
    kwargs: Dict[str, Any] = {"Item": item}
    if idempotent:
        kwargs["ConditionExpression"] = "attribute_not_exists(video_id)"
    _dynamodb.Table(os.environ.get("VIDEOS_TABLE", "Videos")).put_item(**kwargs)


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
    except BadRequest as e:
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

    # Quote, then charge exactly the quote: the length that is billed is the length that is made.
    minutes = options.get("target_minutes") or float(os.environ.get("DEFAULT_TARGET_MINUTES", "3"))
    options["target_minutes"] = minutes
    credits = wallet.credits_for_minutes(minutes)
    try:
        charged = wallet.charge(user_id, credits, tz=request_timezone(event))
        if credits and not charged:  # nothing was taken: an unlimited (test/staff) account. Keep a ceiling and a trail in case its token is ever stolen.
            logger.warning("UNLIMITED_ACCOUNT_USE user=%s credits=%s minutes=%s", user_id, credits, minutes)
            usage.consume(f"unlimited:{user_id}", limit=int(os.environ.get("UNLIMITED_DAILY_VIDEOS", "50")))
    except usage.QuotaExceeded:
        return json_response(429, {"message": "Daily limit for this test account reached."}, {"Retry-After": "3600"})
    except wallet.InsufficientCredits as e:
        return json_response(402, {"message": f"This video needs {e.needed} credit{'s' if e.needed != 1 else ''} and you have {e.balance}.",
                                   "code": "insufficient_credits", "balance": e.balance, "needed": e.needed})

    try:
        _register_intent(user_id, prompt, video_id, usage_day, idempotent=idempotent, credits=credits, charge=charged)
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
        return json_response(500, {"message": "Failed to start workflow"})
    except Exception:
        logger.exception("Failed to start workflow")
        wallet.refund(user_id, charged)
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
