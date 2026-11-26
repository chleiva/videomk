"""SQS worker of the account deletion (docs/ACCOUNT_DELETION.md): one message = one user id; the work is in common/deletion.run."""
import json
import logging
from typing import Any, Dict

from common import deletion

logger = logging.getLogger()
SAFETY_MARGIN_S = 45


def handle_one(user: str, seconds_left: float) -> deletion.Outcome:
    out = deletion.run(user, budget=deletion.Budget(max(5.0, seconds_left - SAFETY_MARGIN_S)))
    if out.status in ("wait", "retry", "continue"):
        deletion.enqueue(user, out.delay)   # the same user again, later (SQS delays at most 15 minutes; a longer wait is several hops)
    return out


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    failures = []
    for rec in event.get("Records", []):
        try:
            user = json.loads(rec["body"]).get("user_id")
            left = context.get_remaining_time_in_millis() / 1000.0 if context else 600.0
            out = handle_one(deletion.check_user(user), left)
            logger.info("ACCOUNT_DELETION_STEP user=%s status=%s step=%s", user, out.status, out.step)
        except deletion.DeletionError:
            logger.error("ACCOUNT_DELETION_BAD_MESSAGE")   # not a user id: retrying cannot help; the message goes to the dead-letter queue after its attempts
            failures.append({"itemIdentifier": rec.get("messageId")})
        except Exception:
            logger.exception("ACCOUNT_DELETION_WORKER_ERROR")
            failures.append({"itemIdentifier": rec.get("messageId")})
    return {"batchItemFailures": failures}
