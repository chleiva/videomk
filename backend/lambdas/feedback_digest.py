"""The daily feedback email (docs/FEEDBACK.md): one plain-text email to the owner with the feedback that arrived since the last one; nothing at all when there is none.

Reads the sparse GSI_Pending (items still carrying pending="1"), groups by kind, sends with SES, and ONLY AFTER a successful send removes `pending` and sets `emailedAt`.
A send error raises (nothing of that part is marked; the next run sends it). Large batches are split into several emails (MAX_ITEMS_PER_EMAIL / MAX_CHARS_PER_EMAIL).
Does nothing, with a warning, when the SSM parameter FEEDBACK_EMAIL_TO_PARAM (default /videomk/feedback_email_to) is missing or not an address; skips with a log line when no sender is configured (QA).
The text of a message is never logged.
"""
import logging
import os
import re
import time
from typing import Any, Dict, List

import boto3
from botocore.exceptions import ClientError

from common import feedback

log = logging.getLogger()
log.setLevel(logging.INFO)

MAX_ITEMS_PER_EMAIL = 100
MAX_CHARS_PER_EMAIL = 120_000
MAX_ITEMS_PER_RUN = 2000
KIND_ORDER = ("problem", "idea", "other")
_EMAIL = re.compile(r"^[^\s@<>,;]+@[^\s@<>,;]+\.[^\s@<>,;]+$")
_ssm = _ses = _ddb = None


def _clients():
    global _ssm, _ses, _ddb
    if _ddb is None:
        _ddb = boto3.resource("dynamodb")
        feedback.set_resource(_ddb)
    if _ssm is None:
        _ssm = boto3.client("ssm")
    if _ses is None:
        _ses = boto3.client("ses", region_name=os.environ.get("FEEDBACK_SES_REGION") or None)
    return _ssm, _ses, _ddb


def recipient(ssm) -> str:
    name = os.environ.get("FEEDBACK_EMAIL_TO_PARAM", "/videomk/feedback_email_to")
    try:
        v = str(ssm.get_parameter(Name=name, WithDecryption=True)["Parameter"]["Value"]).strip()
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "ParameterNotFound":
            log.warning("FEEDBACK_DIGEST_NO_RECIPIENT parameter %s does not exist: nothing sent", name)
            return ""
        raise
    if not _EMAIL.match(v):
        log.warning("FEEDBACK_DIGEST_NO_RECIPIENT parameter %s does not hold an email address: nothing sent", name)
        return ""
    return v


def pending(tbl) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    kw: Dict[str, Any] = {"IndexName": "GSI_Pending", "KeyConditionExpression": "pending = :p", "ExpressionAttributeValues": {":p": "1"}, "ScanIndexForward": True}
    while len(out) < MAX_ITEMS_PER_RUN:
        r = tbl.query(**kw)
        out.extend(r.get("Items", []))
        if not r.get("LastEvaluatedKey"):
            break
        kw["ExclusiveStartKey"] = r["LastEvaluatedKey"]
    return sorted(out, key=lambda i: i["feedbackId"])[:MAX_ITEMS_PER_RUN]


def split(items: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
    parts: List[List[Dict[str, Any]]] = []
    cur: List[Dict[str, Any]] = []
    size = 0
    for it in items:
        n = len(str(it.get("text", ""))) + 200
        if cur and (len(cur) >= MAX_ITEMS_PER_EMAIL or size + n > MAX_CHARS_PER_EMAIL):
            parts.append(cur)
            cur, size = [], 0
        cur.append(it)
        size += n
    if cur:
        parts.append(cur)
    return parts


def _when(created: str) -> str:
    return created.replace("T", " ").replace("Z", " UTC")[:20] if created else "?"


def build(items: List[Dict[str, Any]], part: int = 1, parts: int = 1, total: int = 0) -> Dict[str, str]:
    n = total or len(items)
    subject = f"VideoMK feedback: {n} new" + (f" (part {part}/{parts})" if parts > 1 else "")
    by_kind: Dict[str, List[Dict[str, Any]]] = {}
    for it in items:
        k = it.get("kind") if it.get("kind") in feedback.KINDS else "other"
        by_kind.setdefault(k, []).append(it)
    lines = [f"{len(items)} new feedback message{'s' if len(items) != 1 else ''}" + (f" in this email (part {part} of {parts}, {n} in total)" if parts > 1 else ""), ""]
    lines.append("  ".join(f"{k}: {len(by_kind[k])}" for k in KIND_ORDER if k in by_kind))
    for k in KIND_ORDER:
        if k not in by_kind:
            continue
        lines += ["", f"=== {k} ({len(by_kind[k])}) ===", ""]
        for it in by_kind[k]:
            who = " ".join(x for x in (str(it.get("app", "?")) + (f" {it['version']}" if it.get("version") else ""), f"locale {it['locale']}" if it.get("locale") else "", f"context {it['context']}" if it.get("context") else "",
                                       f"user {feedback.user_hash(str(it.get('userId', '')))}") if x)
            lines.append(f"[{_when(str(it.get('createdAt', '')))}] {who}")
            lines.append("    " + str(it.get("text", "")).replace("\n", "\n    "))
            lines.append("")
    lines.append("-- VideoMK feedback digest. Items are in the feedback table; this email lists only what was not mailed before.")
    return {"subject": subject, "body": "\n".join(lines)}


def mark_sent(tbl, items: List[Dict[str, Any]], now: float) -> None:
    stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now))
    for it in items:
        tbl.update_item(Key={"feedbackId": it["feedbackId"]}, UpdateExpression="SET emailedAt = :t REMOVE pending", ExpressionAttributeValues={":t": stamp})


def handler(event: Any = None, context: Any = None) -> Dict[str, Any]:
    ssm, ses, ddb = _clients()
    sender = os.environ.get("FEEDBACK_FROM", "").strip()
    if not sender:
        log.info("FEEDBACK_DIGEST_SKIPPED no sender configured for this stage (docs/FEEDBACK.md): nothing sent")
        return {"sent": 0, "skipped": "no_sender"}
    to = recipient(ssm)
    if not to:
        return {"sent": 0, "skipped": "no_recipient"}
    tbl = ddb.Table(os.environ["FEEDBACK_TABLE"])
    items = pending(tbl)
    if not items:
        log.info("FEEDBACK_DIGEST none new")
        return {"sent": 0}
    parts = split(items)
    sent = 0
    for i, part in enumerate(parts, 1):
        mail = build(part, i, len(parts), len(items))
        try:
            ses.send_email(Source=sender, Destination={"ToAddresses": [to]}, Message={"Subject": {"Data": mail["subject"], "Charset": "UTF-8"}, "Body": {"Text": {"Data": mail["body"], "Charset": "UTF-8"}}})
        except Exception as e:   # noqa: BLE001 - nothing of this part is marked; earlier parts already are
            code = e.response.get("Error", {}).get("Code", "") if isinstance(e, ClientError) else ""
            log.error("FEEDBACK_DIGEST_SEND_FAILED part=%d/%d error=%s%s sent_before=%d", i, len(parts), type(e).__name__, f"/{code}" if code else "", sent)
            raise
        mark_sent(tbl, part, time.time())
        sent += len(part)
    log.info("FEEDBACK_DIGEST sent=%d emails=%d", sent, len(parts))
    return {"sent": sent, "emails": len(parts)}
