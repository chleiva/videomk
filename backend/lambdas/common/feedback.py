"""User feedback (docs/FEEDBACK.md): validation, the time-sortable id, the per-user rate limit and the store. No AWS client is created at import time.

The text is stored verbatim (control and invisible formatting characters removed) and is NEVER logged: log lines carry counts, the feedback id and a short user hash only.
Table `FEEDBACK_TABLE`: pk feedbackId (ULID). GSI_Pending (sparse: `pending` = "1" until the item is mailed) lists what the daily email still has to send.
GSI_User (userId, KEYS_ONLY) lets the account deletion find a person's rows and replace the userId by a one-way hash.
"""
import hashlib
import os
import secrets
import time
import unicodedata
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

TEXT_MIN, TEXT_MAX = 3, 2000
KINDS = ("idea", "problem", "other")
APPS = ("ios", "android", "web")
LOCALES = ("en", "es")
VERSION_MAX, CONTEXT_MAX = 32, 64
MAX_BODY_BYTES = 16 * 1024
HOURLY_LIMIT, DAILY_LIMIT = 10, 30
_B32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"   # Crockford

_ddb = None


class FeedbackError(Exception):
    def __init__(self, status: int, key: str, code: str = "", **params: Any):
        self.status, self.key, self.code, self.params = status, key, code, params
        super().__init__(key)


def _resource():
    global _ddb
    if _ddb is None:
        _ddb = boto3.resource("dynamodb")
    return _ddb


def set_resource(r: Any) -> None:
    global _ddb
    _ddb = r


def table():
    return _resource().Table(os.environ["FEEDBACK_TABLE"])


def new_id(now_ms: Optional[int] = None) -> str:
    """ULID: 48-bit millisecond time + 80 random bits, 26 Crockford base32 characters; sorts by creation time."""
    ms = int(time.time() * 1000) if now_ms is None else now_ms
    n = (ms << 80) | secrets.randbits(80)
    return "".join(_B32[(n >> (5 * i)) & 31] for i in range(25, -1, -1))


def clean(value: str, *, keep_newlines: bool = False) -> str:
    """Remove control characters (and invisible formatting such as bidi overrides); optionally keep tabs and newlines. Line endings are normalised to \\n."""
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    out = []
    for ch in value:
        if ch in "\n\t":
            out.append(ch if keep_newlines else " ")
        elif unicodedata.category(ch) in ("Cc", "Cf", "Cs", "Co", "Cn", "Zl", "Zp"):
            continue
        else:
            out.append(ch)
    return "".join(out)


def _opt_str(b: Dict[str, Any], key: str, limit: int) -> str:
    v = b.get(key)
    if v is None:
        return ""
    if not isinstance(v, str):
        raise FeedbackError(400, "feedback.invalid")
    v = clean(v).strip()
    if len(v) > limit:
        raise FeedbackError(400, "feedback.invalid")
    return v


def validate(body: Any) -> Dict[str, str]:
    if not isinstance(body, dict):
        raise FeedbackError(400, "feedback.invalid")
    text = body.get("text")
    if not isinstance(text, str):
        raise FeedbackError(400, "feedback.text_length", min=TEXT_MIN, max=TEXT_MAX)
    text = clean(text, keep_newlines=True).strip()
    if not (TEXT_MIN <= len(text) <= TEXT_MAX):
        raise FeedbackError(400, "feedback.text_length", min=TEXT_MIN, max=TEXT_MAX)
    kind = body.get("kind")
    if kind is not None and kind not in KINDS:
        raise FeedbackError(400, "feedback.invalid")
    app = body.get("app")
    if app not in APPS:
        raise FeedbackError(400, "feedback.invalid")
    locale = body.get("locale")
    if locale is not None and locale not in LOCALES:
        raise FeedbackError(400, "feedback.invalid")
    return {"text": text, "kind": kind or "other", "app": app, "version": _opt_str(body, "version", VERSION_MAX), "locale": locale or "", "context": _opt_str(body, "context", CONTEXT_MAX)}


def user_hash(user: str) -> str:
    """Short, one-way label for the owner's email and logs (not reversible without already knowing the id)."""
    return hashlib.sha256(f"videomk-feedback\0{user}".encode()).hexdigest()[:8]


# ----------------------------------------------------------------------------- rate limit (counters in the usage table, which the account deletion already clears)
def _usage():
    return _resource().Table(os.environ["USAGE_TABLE"])


def _take(key: str, day: str, limit: int, ttl_s: int, now: int) -> bool:
    try:
        _usage().update_item(
            Key={"user_id": key, "day": day}, UpdateExpression="ADD #c :one SET #t = :t", ConditionExpression="attribute_not_exists(#c) OR #c < :l",
            ExpressionAttributeNames={"#c": "count", "#t": "ttl"}, ExpressionAttributeValues={":one": 1, ":l": limit, ":t": now + ttl_s})
        return True
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return False
        raise


def _give_back(key: str, day: str) -> None:
    try:
        _usage().update_item(Key={"user_id": key, "day": day}, UpdateExpression="ADD #c :n", ConditionExpression="#c > :z", ExpressionAttributeNames={"#c": "count"}, ExpressionAttributeValues={":n": -1, ":z": 0})
    except ClientError:
        pass


def take_slot(user: str, now: Optional[float] = None) -> None:
    """Raises FeedbackError(429) when the person already sent HOURLY_LIMIT in this clock hour or DAILY_LIMIT today (UTC)."""
    now = time.time() if now is None else now
    t = time.gmtime(now)
    hour_day, day = time.strftime("%Y-%m-%dT%H", t), time.strftime("%Y-%m-%d", t)
    if not _take(f"feedbackh:{user}", hour_day, HOURLY_LIMIT, 2 * 3600, int(now)):
        raise FeedbackError(429, "feedback.rate_limited", "rate_limited")
    if not _take(f"feedback:{user}", day, DAILY_LIMIT, 3 * 86400, int(now)):
        _give_back(f"feedbackh:{user}", hour_day)
        raise FeedbackError(429, "feedback.rate_limited", "rate_limited")


def store(user: str, fields: Dict[str, str], now: Optional[float] = None) -> str:
    now = time.time() if now is None else now
    fid = new_id(int(now * 1000))
    item = {"feedbackId": fid, "userId": user, "createdAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)), **fields, "category": "", "status": "new", "pending": "1"}
    table().put_item(Item=item, ConditionExpression="attribute_not_exists(feedbackId)")
    return fid
