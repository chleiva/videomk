"""POST /users/{user_id}/feedback (docs/FEEDBACK.md). The caller is the verified Cognito `sub`; the text is stored and never logged."""
import json
import logging
from typing import Any, Dict

from botocore.exceptions import ClientError

from common import feedback, i18n
from common.http import json_response
from common.identity import extract_cognito_sub

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    loc = i18n.pick_locale(event)
    user = extract_cognito_sub(event)
    if not user:
        return json_response(401, {"message": i18n.t("err.unauthorized", loc)})
    path_user = ((event or {}).get("pathParameters") or {}).get("user_id")
    if not path_user or path_user != user:
        return json_response(403, {"message": i18n.t("err.forbidden", loc)})
    try:
        raw = event.get("body") or ""
        if len(raw.encode("utf-8", "ignore")) > feedback.MAX_BODY_BYTES:
            raise feedback.FeedbackError(400, "feedback.invalid")
        try:
            body = json.loads(raw or "null")
        except (ValueError, TypeError):
            raise feedback.FeedbackError(400, "feedback.invalid") from None
        fields = feedback.validate(body)
        feedback.take_slot(user)
        fid = feedback.store(user, fields)
        logger.info("FEEDBACK_STORED id=%s user=%s app=%s kind=%s chars=%d", fid, feedback.user_hash(user), fields["app"], fields["kind"], len(fields["text"]))   # never the text
        return json_response(202, {"ok": True})
    except feedback.FeedbackError as e:
        extra = {"code": e.code} if e.code else {}
        return json_response(e.status, {"message": i18n.t(e.key, loc, **e.params), **extra}, {"Retry-After": "3600"} if e.status == 429 else None)
    except ClientError:
        logger.exception("FEEDBACK_FAILED (AWS)")
        return json_response(500, {"message": i18n.t("err.generic", loc)})
    except Exception:
        logger.exception("FEEDBACK_FAILED")
        return json_response(500, {"message": i18n.t("err.generic", loc)})
