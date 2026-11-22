"""Per-user daily generation quota on a pay-per-request DynamoDB table (zero idle cost).

Item: {user_id (HASH), day (RANGE, 'YYYY-MM-DD' UTC), count, ttl}
"""
import os
import time
from typing import Optional

import boto3
from botocore.exceptions import ClientError

DEFAULT_DAILY_LIMIT = 5


class QuotaExceeded(Exception):
    pass


def _table(table_name: Optional[str] = None):
    name = table_name or os.environ.get("USAGE_TABLE", "")
    if not name:
        raise RuntimeError("USAGE_TABLE environment variable is not set")
    return boto3.resource("dynamodb").Table(name)


def _today() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def daily_limit() -> int:
    try:
        return int(os.environ.get("DAILY_VIDEO_LIMIT", DEFAULT_DAILY_LIMIT))
    except ValueError:
        return DEFAULT_DAILY_LIMIT


def consume(user_id: str, *, limit: Optional[int] = None, table_name: Optional[str] = None) -> int:
    """Atomically take one unit of today's quota. Raises QuotaExceeded when spent."""
    limit = daily_limit() if limit is None else limit
    try:
        res = _table(table_name).update_item(
            Key={"user_id": user_id, "day": _today()},
            UpdateExpression="ADD #c :one SET #ttl = :ttl",
            ConditionExpression="attribute_not_exists(#c) OR #c < :limit",
            ExpressionAttributeNames={"#c": "count", "#ttl": "ttl"},
            ExpressionAttributeValues={":one": 1, ":limit": limit, ":ttl": int(time.time()) + 3 * 86400},
            ReturnValues="UPDATED_NEW",
        )
        return int(res["Attributes"]["count"])
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            raise QuotaExceeded(f"Daily limit of {limit} videos reached") from e
        raise


def refund(user_id: str, *, day: Optional[str] = None, table_name: Optional[str] = None) -> None:
    """Give back one unit (best-effort; never goes below zero)."""
    if not user_id:
        return
    try:
        _table(table_name).update_item(
            Key={"user_id": user_id, "day": day or _today()},
            UpdateExpression="ADD #c :neg",
            ConditionExpression="attribute_exists(#c) AND #c > :zero",
            ExpressionAttributeNames={"#c": "count"},
            ExpressionAttributeValues={":neg": -1, ":zero": 0},
        )
    except ClientError:
        pass
