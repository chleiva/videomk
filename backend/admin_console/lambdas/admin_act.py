"""POST /api/switches  {"switch": "stop_new_videos" | "stop_free_videos" | "stop_dictation" | "stop_video_upload", "stopped": true | false}

The ONLY thing the console can change. API Gateway has already checked the token (signature, the admin pool, this app client, expiry) before this code runs.
Here, first of all: the sign-in must be at most 5 minutes old (step-up: the page asks for the passkey again). Then the event is written to the locked audit
log, the one item is updated, and the owner gets an email. This function's policy allows: read and update that ONE item of the flags table, write audit
files, publish to the alert topic. Nothing else."""
import json
import logging
from typing import Any, Dict

import admin_common as c

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    who = c.claims(event)
    if not who.get("sub"):
        return c.response(401, {"code": "unauthorized", "message": "Sign in first."})
    age = c.auth_age(event)
    if age is None or age < -60 or age > c.STEP_UP_SECONDS:   # before anything is read or written
        return c.response(403, {"code": "step_up_required", "message": "Confirm with your passkey to change a switch.", "max_age_seconds": c.STEP_UP_SECONDS})
    try:
        body = json.loads((event or {}).get("body") or "{}")
    except (TypeError, ValueError):
        body = None
    if not isinstance(body, dict) or body.get("switch") not in c.SWITCHES or not isinstance(body.get("stopped"), bool):
        return c.response(400, {"code": "bad_request", "message": "Send {switch, stopped}."})
    name, stopped = body["switch"], body["stopped"]
    http = ((event or {}).get("requestContext") or {}).get("http") or {}
    trail = {"switch": name, "stopped": stopped, "actor": str(who["sub"]), "auth_age_s": int(age), "request_id": ((event or {}).get("requestContext") or {}).get("requestId"), "source_ip": http.get("sourceIp")}
    try:
        c.audit("switch", **trail)   # no audit entry, no change
    except Exception:   # noqa: BLE001
        logger.exception("ADMIN_AUDIT_FAILED")
        return c.response(500, {"code": "audit_failed", "message": "The change was not made: it could not be recorded. Use the runbook command if this is urgent."})
    now = c.iso()
    try:
        c.table("FLAGS_TABLE").update_item(Key={"user_id": c.SWITCH_ITEM}, UpdateExpression="SET #s = :v, updated_at = :t, updated_by = :b",
                                           ExpressionAttributeNames={"#s": name}, ExpressionAttributeValues={":v": stopped, ":t": now, ":b": "console"})
    except Exception:   # noqa: BLE001
        logger.exception("ADMIN_SWITCH_WRITE_FAILED")
        try:
            c.audit("switch_failed", **trail)
        except Exception:   # noqa: BLE001
            logger.exception("ADMIN_AUDIT_FAILED")
        return c.response(500, {"code": "write_failed", "message": "The switch could not be changed. Use the runbook command if this is urgent."})
    words = c.SWITCH_WORDS[name]
    try:
        c.notify("%s switched %s" % (words, "OFF" if stopped else "back ON"),
                 "%s were switched %s from the console at %s.\n\n%s\n\nIt takes effect within about a minute. Videos already being made finish.\n\n"
                 "If this was not you, lock the console now:\n  %s\nand set the switch back (docs/ADMIN_RUNBOOK.md)."
                 % (words, "OFF" if stopped else "back ON", c.hhmm(),
                    {"stop_new_videos": "While it is off, nobody can start or retry a video; watching, the library and sign-in keep working.",
                     "stop_free_videos": "While it is off, free credits cannot be spent; paid credits work.",
                     "stop_dictation": "While it is off, paid dictation (speech to text) is unavailable; typing and everything else keep working.",
                     "stop_video_upload": "While it is off, nobody can add a video clip; clips already ready and photos keep working."}[name], c.lock_command(username=who.get("username") or who.get("sub"))))
    except Exception:   # noqa: BLE001 - the change is made and recorded; a failed email must not undo it
        logger.exception("ADMIN_NOTIFY_FAILED")
    logger.info("ADMIN_SWITCH %s stopped=%s", name, stopped)
    return c.response(200, {"switches": {**c.switches()}, "changed": name, "stopped": stopped, "live_within_seconds": 60})
