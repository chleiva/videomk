import os
import json
import time
from typing import Any, Dict, Optional

import boto3
from botocore.exceptions import ClientError


_dynamodb = boto3.resource("dynamodb")


def _get_table(table_name: Optional[str] = None):
    name = table_name or os.environ.get("VIDEOS_TABLE", "")
    if not name:
        raise RuntimeError("VIDEOS_TABLE environment variable is not set")
    return _dynamodb.Table(name)


def put_video_item(
    table_name: Optional[str],
    item: Dict[str, Any],
) -> None:
    table = _get_table(table_name)
    # Ensure created_at exists
    item.setdefault("created_at", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    table.put_item(Item=item)


def update_status(
    video_id: str,
    status: str,
    table_name: Optional[str] = None,
    extra_attributes: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    table = _get_table(table_name)
    update_expressions = ["#s = :s"]
    expression_attribute_values: Dict[str, Any] = {":s": status}
    expression_attribute_names = {"#s": "status"}

    if extra_attributes:
        for key, value in extra_attributes.items():
            placeholder = f":{key}"
            name_placeholder = f"#{key}"
            update_expressions.append(f"{name_placeholder} = {placeholder}")
            expression_attribute_values[placeholder] = value
            expression_attribute_names[name_placeholder] = key

    update_expression = "SET " + ", ".join(update_expressions)

    try:
        response = table.update_item(
            Key={"video_id": video_id},
            UpdateExpression=update_expression,
            ExpressionAttributeNames=expression_attribute_names,
            ExpressionAttributeValues=expression_attribute_values,
            ReturnValues="ALL_NEW",
        )
        return response.get("Attributes", {})
    except ClientError as e:
        # Minimal error surface; raise to be handled by caller
        raise e


