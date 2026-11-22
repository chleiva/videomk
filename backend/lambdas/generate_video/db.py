import os
import time
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError

_dynamodb = boto3.resource("dynamodb")

# Once a video reaches one of these, later (late/duplicate) updates are ignored.
TERMINAL_STATUSES = ("COMPLETE", "REJECTED")


def _get_table(table_name: Optional[str] = None):
    name = table_name or os.environ.get("VIDEOS_TABLE") or "Videos"
    return _dynamodb.Table(name)


def put_video_item(table_name: Optional[str], item: Dict[str, Any]) -> None:
    item.setdefault("created_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    _get_table(table_name).put_item(Item=item)


def get_video_item(video_id: str, table_name: Optional[str] = None) -> Dict[str, Any]:
    try:
        return _get_table(table_name).get_item(Key={"video_id": video_id}).get("Item") or {}
    except ClientError:
        return {}


def update_status(
    video_id: str,
    status: str,
    table_name: Optional[str] = None,
    extra_attributes: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Set status (+ attributes). No-op (returns {}) if the item is already terminal."""
    names = {"#s": "status"}
    values: Dict[str, Any] = {":s": status}
    sets = ["#s = :s"]
    for key, value in (extra_attributes or {}).items():
        names[f"#{key}"] = key
        values[f":{key}"] = value
        sets.append(f"#{key} = :{key}")

    terminal_values = {f":t{i}": t for i, t in enumerate(TERMINAL_STATUSES)}
    values.update(terminal_values)
    condition = "attribute_not_exists(#s) OR NOT (#s IN ({}))".format(", ".join(terminal_values))

    try:
        res = _get_table(table_name).update_item(
            Key={"video_id": video_id},
            UpdateExpression="SET " + ", ".join(sets),
            ConditionExpression=condition,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ReturnValues="ALL_NEW",
        )
        return res.get("Attributes", {})
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return {}
        raise
