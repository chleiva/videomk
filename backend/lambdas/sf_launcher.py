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
from typing import Any, Dict, Tuple

import boto3
from botocore.exceptions import ClientError

from common.http import json_response
from common.identity import extract_cognito_sub
from common import usage

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


def video_id_for(user_id: str, body: Dict[str, Any]) -> Tuple[str, bool]:
    """Deterministic id when the client sends `client_request_id` (double-click safe)."""
    crid = body.get("client_request_id")
    if isinstance(crid, str) and 8 <= len(crid) <= 64:
        return str(uuid.uuid5(_NAMESPACE, f"{user_id}:{crid}")), True
    return str(uuid.uuid4()), False


def _register_intent(user_id: str, prompt: str, video_id: str, usage_day: str, *, idempotent: bool) -> None:
    item = {
        "video_id": video_id,
        "user_id": user_id,
        "prompt": prompt,
        "status": "STARTED_PROCESSING",
        "usage_day": usage_day,
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
    except BadRequest as e:
        return json_response(400, {"message": str(e)})

    sm_arn = os.environ.get("STATE_MACHINE_ARN")
    if not sm_arn:
        logger.error("STATE_MACHINE_ARN is not configured")
        return json_response(500, {"message": "Server configuration error"})

    video_id, idempotent = video_id_for(user_id, body)
    usage_day = time.strftime("%Y-%m-%d", time.gmtime())

    # Idempotent replay: the same client_request_id returns the existing job without re-billing.
    if idempotent:
        existing = _dynamodb.Table(os.environ.get("VIDEOS_TABLE", "Videos")).get_item(Key={"video_id": video_id}).get("Item")
        if existing:
            return json_response(202, {"message": "workflow already started", "video_id": video_id})

    try:
        usage.consume(user_id)
    except usage.QuotaExceeded as e:
        return json_response(429, {"message": str(e)}, {"Retry-After": "3600"})

    try:
        _register_intent(user_id, prompt, video_id, usage_day, idempotent=idempotent)
        resp = _sfn.start_execution(
            stateMachineArn=sm_arn,
            name=video_id,  # one execution per video; duplicate starts fail fast
            input=json.dumps({"user_id": user_id, "video_id": video_id, "prompt": prompt, "usage_day": usage_day}),
        )
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code in ("ConditionalCheckFailedException", "ExecutionAlreadyExists"):
            usage.refund(user_id, day=usage_day)
            return json_response(202, {"message": "workflow already started", "video_id": video_id})
        logger.exception("Failed to start workflow")
        usage.refund(user_id, day=usage_day)
        return json_response(500, {"message": "Failed to start workflow"})
    except Exception:
        logger.exception("Failed to start workflow")
        usage.refund(user_id, day=usage_day)
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
