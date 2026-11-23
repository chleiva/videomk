"""Credits wallet. 1 credit = 1 started minute of video (a 10-second video costs 1, 61 seconds costs 2).

Credits live in *buckets* so each kind can expire on its own and the soonest-expiring is spent first:
  daily   1 free credit a day, expire at the end of the user's local day (no hoarding)
  signup  5 welcome credits, expire after 30 days
  paid    bought through the stores, never expire (one bucket per user, increased per purchase)
  refund  a make-good when a refund finds its original bucket already expired (valid 24 h)
The amounts are server config (env), so they change without an app update.

Table (WALLET_TABLE): HASH user_id, RANGE sk.  META item `sk="META"`; bucket items `sk="B#<expiry>#<kind>#<id>"` so a query returns
them in spending order; `REF#<id>` items make purchase grants idempotent.
"""
import json
import math
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

NEVER = 9_999_999_999
MAX_MINUTES = 12
UNLIMITED_DISPLAY = 999  # what an unlimited account's balance reads as, so older app builds still let it send


class InsufficientCredits(Exception):
    def __init__(self, balance: int, needed: int):
        super().__init__(f"{needed} credits needed, {balance} available")
        self.balance, self.needed = balance, needed


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def rules() -> Dict[str, int]:
    return {"credit_unit_seconds": 60, "max_minutes": MAX_MINUTES, "signup": _int("WALLET_SIGNUP_CREDITS", 5), "daily": _int("WALLET_DAILY_CREDITS", 1),
            "signup_valid_days": _int("WALLET_SIGNUP_VALID_DAYS", 30)}


def credits_for_minutes(minutes: float) -> int:
    """Started minutes, at least 1: 0.2 -> 1, 1 -> 1, 1.01 -> 2, 12 -> 12."""
    return max(1, min(MAX_MINUTES, math.ceil(round(float(minutes), 6))))


def _table():
    return boto3.resource("dynamodb").Table(os.environ["WALLET_TABLE"])


def _tx(items: List[Dict[str, Any]]) -> None:
    _table().meta.client.transact_write_items(TransactItems=items)


def _cancelled(e: ClientError) -> bool:
    return e.response.get("Error", {}).get("Code") in ("TransactionCanceledException", "ConditionalCheckFailedException")


def local_day(now: float, tz: Optional[str]) -> Tuple[str, float]:
    """(YYYY-MM-DD in the user's timezone, epoch of the next local midnight). Unknown timezone names fall back to UTC."""
    zone: Any = timezone.utc
    if tz:
        try:
            zone = ZoneInfo(tz)
        except Exception:
            zone = timezone.utc
    dt = datetime.fromtimestamp(now, zone)
    return dt.strftime("%Y-%m-%d"), (dt.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)).timestamp()


def _bucket(user_id: str, kind: str, amount: int, expires: int, now: float, name: Optional[str] = None) -> Dict[str, Any]:
    return {"user_id": user_id, "sk": f"B#{expires:010d}#{kind}#{name or uuid.uuid4().hex[:12]}", "kind": kind, "remaining": amount, "granted": amount,
            "expires_at": expires, "created_at": int(now), **({"ttl": expires + 7 * 86400} if expires < NEVER else {})}


def ensure_grants(user_id: str, *, now: Optional[float] = None, tz: Optional[str] = None) -> None:
    """Welcome credits the first time we see a user; then the day's free credits once per local day. Race-safe (conditional writes)."""
    now = time.time() if now is None else now
    r, t = rules(), _table()
    day, midnight = local_day(now, tz)
    meta = t.get_item(Key={"user_id": user_id, "sk": "META"}, ConsistentRead=True).get("Item")
    tn = t.name
    if meta is None:  # first sight: welcome credits now; the daily credits start with the next local day
        items: List[Dict[str, Any]] = [{"Put": {"TableName": tn, "Item": {"user_id": user_id, "sk": "META", "signup_at": int(now), "last_daily_key": day, "last_daily_utc_day": int(now // 86400)},
                                                "ConditionExpression": "attribute_not_exists(user_id)"}}]
        if r["signup"] > 0:
            items.append({"Put": {"TableName": tn, "Item": _bucket(user_id, "signup", r["signup"], int(now + r["signup_valid_days"] * 86400), now)}})
        try:
            _tx(items)
        except ClientError as e:
            if not _cancelled(e):
                raise
        return
    utc_day = int(now // 86400)
    # Claimable when the user's LOCAL day and the UTC day have both moved on: at most one claim per UTC day, so sending different
    # timezones cannot earn extra days, while an honest user still gets a fresh 2 each local day.
    if r["daily"] > 0 and meta.get("last_daily_key") != day and utc_day > int(meta.get("last_daily_utc_day", -1)):
        try:
            _tx([
                {"Update": {"TableName": tn, "Key": {"user_id": user_id, "sk": "META"}, "UpdateExpression": "SET last_daily_key = :d, last_daily_utc_day = :u",
                            "ConditionExpression": "attribute_not_exists(last_daily_key) OR (last_daily_key <> :d AND last_daily_utc_day < :u)",
                            "ExpressionAttributeValues": {":d": day, ":u": utc_day}}},
                {"Put": {"TableName": tn, "Item": _bucket(user_id, "daily", r["daily"], int(midnight), now, name=day)}},
            ])
        except ClientError as e:
            if not _cancelled(e):
                raise


def _flags():
    return boto3.resource("dynamodb").Table(os.environ["FLAGS_TABLE"])


def unlimited_allowed() -> bool:
    """Off by default and set to 1 by the stack only for non-production stages: in production the flag is ignored even if someone writes it."""
    return os.environ.get("ALLOW_UNLIMITED_ACCOUNTS") == "1"


def is_unlimited(user_id: str) -> bool:
    """Test and staff accounts. The flag lives in its own table (FLAGS_TABLE) that the runtime Lambdas can only READ: it is written only
    with AWS admin credentials (`scripts/wallet_admin.py`), never through the API and never by a function that handles user input.
    Keyed by the immutable Cognito `sub`, never by email (users can change their email)."""
    if not unlimited_allowed() or not user_id or not os.environ.get("FLAGS_TABLE"):
        return False
    item = _flags().get_item(Key={"user_id": user_id}).get("Item") or {}
    return item.get("unlimited") is True


def set_unlimited(user_id: str, on: bool = True) -> None:
    """Admin only (needs write access to FLAGS_TABLE, which no Lambda role has)."""
    if on:
        _flags().put_item(Item={"user_id": user_id, "unlimited": True, "set_at": int(time.time())})
    else:
        _flags().delete_item(Key={"user_id": user_id})


def give_credits(user_id: str, credits: int, note: str = "admin") -> bool:
    """Add paid (never-expiring) credits by hand, once per call (a fresh reference each time)."""
    return grant_paid(user_id, credits, f"{note}-{uuid.uuid4().hex[:10]}")


def _live_buckets(user_id: str, now: float) -> List[Dict[str, Any]]:
    res = _table().query(KeyConditionExpression=Key("user_id").eq(user_id) & Key("sk").begins_with("B#"), ConsistentRead=True)
    return [b for b in sorted(res["Items"], key=lambda b: b["sk"]) if int(b["remaining"]) > 0 and int(b["expires_at"]) > now]


def balance(user_id: str, *, now: Optional[float] = None, tz: Optional[str] = None) -> Dict[str, Any]:
    now = time.time() if now is None else now
    ensure_grants(user_id, now=now, tz=tz)
    live = _live_buckets(user_id, now)
    meta = _table().get_item(Key={"user_id": user_id, "sk": "META"}).get("Item") or {}
    unlimited = is_unlimited(user_id)
    r = rules()
    _, midnight = local_day(now, tz)
    next_daily = max(midnight, (int(meta.get("last_daily_utc_day", 0)) + 1) * 86400.0) if r["daily"] else None
    return {"balance": UNLIMITED_DISPLAY if unlimited else sum(int(b["remaining"]) for b in live), "unlimited": unlimited,
            "buckets": [{"kind": b["kind"], "remaining": int(b["remaining"]), "expires_at": int(b["expires_at"]) if int(b["expires_at"]) < NEVER else None} for b in live],
            "next_daily_at": int(next_daily) if next_daily else None, "rules": r}


def charge(user_id: str, credits: int, *, now: Optional[float] = None, tz: Optional[str] = None) -> List[Dict[str, Any]]:
    """Take `credits`, soonest-expiring first. Returns the breakdown (needed to refund exactly what was taken).
    Raises InsufficientCredits. Concurrent requests can never overspend: every bucket update is conditional on what it still holds."""
    now = time.time() if now is None else now
    ensure_grants(user_id, now=now, tz=tz)
    if is_unlimited(user_id):
        return []  # nothing taken, so a failed video has nothing to refund
    for _ in range(5):
        live = _live_buckets(user_id, now)
        have = sum(int(b["remaining"]) for b in live)
        if have < credits:
            raise InsufficientCredits(have, credits)
        need, takes = credits, []
        for b in live:
            take = min(need, int(b["remaining"]))
            takes.append({"sk": b["sk"], "n": take})
            need -= take
            if need == 0:
                break
        try:
            _tx([{"Update": {"TableName": _table().name, "Key": {"user_id": user_id, "sk": x["sk"]}, "UpdateExpression": "SET remaining = remaining - :n",
                             "ConditionExpression": "remaining >= :n AND expires_at > :now", "ExpressionAttributeValues": {":n": x["n"], ":now": int(now)}}} for x in takes])
            return takes
        except ClientError as e:
            if not _cancelled(e):
                raise  # a concurrent spend changed a bucket: read again and retry
    raise InsufficientCredits(0, credits)


def refund(user_id: str, breakdown: List[Dict[str, Any]], *, now: Optional[float] = None) -> int:
    """Put taken credits back where they came from; if that bucket has expired meanwhile, give a 24-hour make-good instead."""
    now = time.time() if now is None else now
    t, total = _table(), 0
    for x in breakdown:
        n = int(x["n"])
        try:
            t.update_item(Key={"user_id": user_id, "sk": x["sk"]}, UpdateExpression="SET remaining = remaining + :n",
                          ConditionExpression="attribute_exists(sk) AND expires_at > :now", ExpressionAttributeValues={":n": n, ":now": int(now)})
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") != "ConditionalCheckFailedException":
                raise
            t.put_item(Item=_bucket(user_id, "refund", n, int(now + 86400), now))
        total += n
    return total


def refund_video(item: Dict[str, Any]) -> int:
    """Refund what a video was charged, exactly once (failed or rejected videos cost nothing). Safe to call twice."""
    charge_json, video_id, user_id = item.get("charge"), item.get("video_id"), str(item.get("user_id") or "")
    if not charge_json or not video_id or not user_id:
        return 0
    try:
        boto3.resource("dynamodb").Table(os.environ["VIDEOS_TABLE"]).update_item(
            Key={"video_id": video_id}, UpdateExpression="SET refunded = :t", ConditionExpression="attribute_not_exists(refunded)", ExpressionAttributeValues={":t": True})
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return 0
        raise
    return refund(user_id, json.loads(charge_json))


def grant_paid(user_id: str, credits: int, ref: str, *, now: Optional[float] = None, tz: Optional[str] = None) -> bool:
    """Add purchased credits once per store transaction `ref` (False when this ref was already granted). Paid credits never expire."""
    now = time.time() if now is None else now
    ensure_grants(user_id, now=now, tz=tz)
    tn = _table().name
    try:
        _tx([{"Put": {"TableName": tn, "Item": {"user_id": user_id, "sk": f"REF#{ref}", "credits": credits, "at": int(now)}, "ConditionExpression": "attribute_not_exists(user_id)"}},
             {"Update": {"TableName": tn, "Key": {"user_id": user_id, "sk": f"B#{NEVER:010d}#paid#main"},
                         "UpdateExpression": "ADD remaining :n, granted :n SET kind = :k, expires_at = :e, created_at = if_not_exists(created_at, :now)",
                         "ExpressionAttributeValues": {":n": credits, ":k": "paid", ":e": NEVER, ":now": int(now)}}}])
        return True
    except ClientError as e:
        if _cancelled(e):
            return False
        raise
