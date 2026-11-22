"""POST /users/{user_id}/videos/{video_id}/edits  {base_rev, ops[], mode: "preview"|"final"}

Validates the operations, writes a new plan revision, and starts the edit workflow (which re-makes only what changed).
With an empty `ops` list it re-renders the current revision (e.g. to turn an approved preview into the final video).
"""
import json
import os
import time
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError

from common import usage
from common.http import json_response

from .. import awsio, edits
from .editor_common import load_owned_video

STALE_EDIT_S = 45 * 60
EDIT_DAILY_LIMIT = int(os.environ.get("EDIT_DAILY_LIMIT", "60"))
_sfn = boto3.client("stepfunctions")


def _body(event: Dict[str, Any]) -> Dict[str, Any]:
    raw = event.get("body")
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except json.JSONDecodeError:
        data = None
    if not isinstance(data, dict):
        raise edits.EditError("body must be a JSON object")
    return data


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    item, err = load_owned_video(event)
    if err:
        return err
    video_id, user_id = item["video_id"], item["user_id"]
    try:
        body = _body(event)
        mode = body.get("mode", "preview")
        if mode not in ("preview", "final"):
            raise edits.EditError("mode must be 'preview' or 'final'")
        base_rev = body.get("base_rev")
        if isinstance(base_rev, bool) or not isinstance(base_rev, int):
            raise edits.EditError("base_rev is required")
    except edits.EditError as e:
        return json_response(400, {"message": str(e)})

    cur_rev = int(item.get("rev", 1))
    if base_rev != cur_rev:
        return json_response(409, {"message": "This video changed since you loaded it. Reload to continue.", "rev": cur_rev})

    ops = body.get("ops") or []
    new_rev, plan_key = cur_rev, item["plan_key"]
    if ops:
        try:
            new_plan, _ = edits.apply_ops(awsio.get_json(plan_key), ops)
        except edits.EditError as e:
            return json_response(400, {"message": str(e)})
        new_rev = cur_rev + 1
        plan_key = f"{awsio.prefix(video_id)}plan_r{new_rev}.json"
        awsio.put_json(plan_key, new_plan)
    elif mode == "final" and item.get("final_rev") == cur_rev:
        return json_response(409, {"message": "This revision is already rendered.", "rev": cur_rev})

    try:
        usage.consume(f"edit:{user_id}", limit=EDIT_DAILY_LIMIT)
    except usage.QuotaExceeded:
        return json_response(429, {"message": "Daily edit limit reached.", "rev": cur_rev}, {"Retry-After": "3600"})

    now = int(time.time())
    try:  # optimistic lock: same rev, and no live render in progress
        boto3.resource("dynamodb").Table(os.environ.get("VIDEOS_TABLE", "Videos")).update_item(
            Key={"video_id": video_id},
            UpdateExpression="SET #rev = :new, plan_key = :pk, edit_state = :rendering, edit_mode = :mode, edit_started_at = :now REMOVE edit_error",
            ConditionExpression="#rev = :base AND (attribute_not_exists(edit_state) OR edit_state <> :rendering OR edit_started_at < :stale)",
            ExpressionAttributeNames={"#rev": "rev"},
            ExpressionAttributeValues={":new": new_rev, ":pk": plan_key, ":rendering": "RENDERING", ":mode": mode, ":now": now, ":base": cur_rev, ":stale": now - STALE_EDIT_S},
        )
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
            return json_response(409, {"message": "An edit is already rendering. Wait for it to finish.", "rev": cur_rev})
        raise
    try:
        _sfn.start_execution(
            stateMachineArn=os.environ["EDIT_STATE_MACHINE_ARN"],
            name=f"{video_id}-r{new_rev}-{mode}-{now}"[:80],
            input=json.dumps({"user_id": user_id, "video_id": video_id, "plan_key": plan_key, "rev": new_rev, "mode": mode}),
        )
    except Exception:
        from generate_video.db import set_attributes

        set_attributes(video_id, {"edit_state": "FAILED", "edit_error": "START_FAILED"})
        return json_response(500, {"message": "Couldn't start the render. Please try again."})
    return json_response(202, {"rev": new_rev, "mode": mode, "message": "render started"})
