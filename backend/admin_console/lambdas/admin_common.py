"""Shared by the owner console's functions (docs/ADMIN_CONSOLE_DESIGN_2026-11-28.md). Nothing here is deployed with the customer-facing functions.

The console can read numbers and flip two switches. It never handles prompts, emails, credits, plans or budgets (its IAM policies allow none of that:
tests/test_admin_cdk.py reads them from the synthesized template)."""
import datetime
import hashlib
import json
import os
import secrets
import time
from decimal import Decimal
from typing import Any, Dict, Optional

import boto3

SWITCH_ITEM = "ops:switches"                       # the same item the launcher reads (lambdas/common/ops_switches.py); a test holds the two together
SWITCHES = ("stop_new_videos", "stop_free_videos", "stop_dictation")
SWITCH_WORDS = {"stop_new_videos": "New videos", "stop_free_videos": "Free videos", "stop_dictation": "Dictation"}
STEP_UP_SECONDS = 300                              # a switch needs a sign-in (passkey, or password + authenticator code) made in the last 5 minutes
# the free plan's knobs the console SHOWS (never writes); the same defaults as lambdas/common/plans.KNOBS (a test compares them)
BUDGET_DEFAULTS = {"free_daily_budget_credits": 15, "free_budget_unlimited": False, "cost_per_credit_usd": 0.15}

_clients: Dict[str, Any] = {}


def client(name: str, **kw: Any) -> Any:
    key = name + json.dumps(kw, sort_keys=True)
    if key not in _clients:
        _clients[key] = boto3.client(name, **kw)
    return _clients[key]


def table(env_name: str) -> Any:
    key = "table:" + env_name
    if key not in _clients:
        _clients[key] = boto3.resource("dynamodb").Table(os.environ[env_name])
    return _clients[key]


def reset_clients() -> None:
    _clients.clear()


def stage() -> str:
    return os.environ.get("STAGE", "qa")


def iso(ts: Optional[float] = None) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() if ts is None else ts))


def day_of(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.gmtime(ts))


def hhmm(ts: Optional[float] = None) -> str:
    return time.strftime("%H:%M", time.gmtime(time.time() if ts is None else ts)) + " UTC"


def plain(obj: Any) -> Any:
    """DynamoDB numbers as JSON numbers."""
    if isinstance(obj, Decimal):
        return int(obj) if obj % 1 == 0 else float(obj)
    if isinstance(obj, dict):
        return {k: plain(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [plain(v) for v in obj]
    return obj


def dec(obj: Any) -> Any:
    """Floats as Decimal for DynamoDB (6 decimals: costs are tracked to a millionth of a dollar)."""
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, float):
        return Decimal(str(round(obj, 6)))
    if isinstance(obj, dict):
        return {k: dec(v) for k, v in obj.items() if v is not None}
    if isinstance(obj, (list, tuple)):
        return [dec(v) for v in obj]
    return obj


def response(status: int, body: Dict[str, Any]) -> Dict[str, Any]:
    # no CORS headers on purpose: the page and the API share one address, and no other site may read the answers
    return {"statusCode": status, "headers": {"Content-Type": "application/json", "Cache-Control": "no-store"}, "body": json.dumps(plain(body))}


def claims(event: Any) -> Dict[str, Any]:
    """The token's claims as API Gateway verified them (signature, issuer = the admin pool, this app client, not expired) before this code ran."""
    try:
        c = (((event or {}).get("requestContext") or {}).get("authorizer") or {}).get("jwt", {}).get("claims")
        return c if isinstance(c, dict) else {}
    except Exception:   # noqa: BLE001
        return {}


def auth_age(event: Any, now: Optional[float] = None) -> Optional[float]:
    """Seconds since the person last proved who they are (the token's `auth_time`; a renewed token keeps the original time). None: unknown."""
    try:
        at = float(claims(event).get("auth_time"))
    except (TypeError, ValueError):
        return None
    return (time.time() if now is None else now) - at


def budget_knobs() -> Dict[str, Any]:
    """The three free-budget knobs, read from the plans parameter (read only). Missing or unreadable values are the defaults."""
    out = dict(BUDGET_DEFAULTS)
    name = os.environ.get("PLANS_CONFIG_PARAM")
    if not name:
        return out
    ssm = client("ssm")
    try:
        raw = json.loads(ssm.get_parameter(Name=name)["Parameter"]["Value"] or "{}")
    except ssm.exceptions.ParameterNotFound:
        return out
    if isinstance(raw, dict):
        v = raw.get("free_daily_budget_credits")
        if isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= 1_000_000:
            out["free_daily_budget_credits"] = v
        if isinstance(raw.get("free_budget_unlimited"), bool):
            out["free_budget_unlimited"] = raw["free_budget_unlimited"]
        c = raw.get("cost_per_credit_usd")
        if isinstance(c, (int, float)) and not isinstance(c, bool) and 0 <= c <= 10:
            out["cost_per_credit_usd"] = float(c)
    return out


def budget_spent(day: str) -> int:
    """Free credits spent today by all accounts: the launcher's own counter (usage table, item `fbudget` / UTC day)."""
    item = table("USAGE_TABLE").get_item(Key={"user_id": "fbudget", "day": day}).get("Item") or {}
    return int(item.get("count") or 0)


def switches() -> Dict[str, Any]:
    item = table("FLAGS_TABLE").get_item(Key={"user_id": SWITCH_ITEM}).get("Item") or {}
    return {**{s: item.get(s) is True for s in SWITCHES}, "updated_at": item.get("updated_at"), "updated_by": item.get("updated_by")}


def audit(action: str, **fields: Any) -> str:
    """One small file per event in the locked bucket (Object Lock, compliance mode: nobody can change or delete it before its date).
    Never a prompt, never an email address. Raises when it cannot be written: the caller decides what that means."""
    now = time.time()
    entry = {"time": iso(now), "stage": stage(), "action": action, **{k: v for k, v in fields.items() if v is not None}}
    body = json.dumps(plain(entry), sort_keys=True).encode("utf-8")
    key = "audit/%s/%s-%s-%s.json" % (time.strftime("%Y/%m/%d", time.gmtime(now)), time.strftime("%H%M%S", time.gmtime(now)), action, secrets.token_hex(4))
    import base64
    client("s3").put_object(Bucket=os.environ["AUDIT_BUCKET"], Key=key, Body=body, ContentType="application/json",
                            ContentMD5=base64.b64encode(hashlib.md5(body).digest()).decode("ascii"))   # a bucket with a default lock asks for the checksum
    return key


def notify(subject: str, text: str) -> None:
    """One plain email to the owner through the alert topic."""
    client("sns").publish(TopicArn=os.environ["ALERT_TOPIC_ARN"], Subject=("VideoMK %s: %s" % (stage(), subject))[:100], Message=text)


def lock_command(pool_id: Any = None, username: Any = None) -> str:
    """The one command that locks the console from any computer (docs/ADMIN_RUNBOOK.md)."""
    return ("aws cognito-idp admin-disable-user --user-pool-id %s --username %s --profile %s --region %s"
            % (pool_id or os.environ.get("ADMIN_POOL_ID") or "<AdminPoolId>", username or "<the admin user name>", os.environ.get("AWS_CLI_PROFILE", stage()), os.environ.get("AWS_REGION", "")))
