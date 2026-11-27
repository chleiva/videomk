"""Cognito trigger of the ADMIN pool (post authentication): every sign-in to the console is written to the locked audit log and emailed to the owner.
A failure here is logged and never blocks the sign-in (the console must stay reachable in an emergency); the function may only write audit files and
publish to the alert topic."""
import logging
from typing import Any, Dict

import admin_common as c

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    try:
        attrs = ((event or {}).get("request") or {}).get("userAttributes") or {}
        c.audit("sign_in", actor=str(attrs.get("sub") or ""), trigger=str((event or {}).get("triggerSource") or ""))
    except Exception:   # noqa: BLE001
        logger.exception("ADMIN_AUDIT_FAILED")
    try:
        c.notify("console sign-in", "Someone signed in to the VideoMK console (%s) at %s.\n\nIf this was you, nothing to do.\n\nIf it was not, lock the console now:\n  %s\n(docs/ADMIN_RUNBOOK.md)"
                 % (c.stage(), c.hhmm(), c.lock_command((event or {}).get("userPoolId"), (event or {}).get("userName"))))
    except Exception:   # noqa: BLE001
        logger.exception("ADMIN_NOTIFY_FAILED")
    return event
