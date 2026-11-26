"""Forward mail received at hello@videomk.com to one personal inbox (docs/EMAIL_FORWARDING.md).

SES inbound stores the raw message in S3 and invokes this function (asynchronously) with the SES event. We read the message, drop what must not be forwarded,
rewrite the headers so the copy passes SPF/DKIM/DMARC at the destination (it is sent by videomk.com itself, not by the original sender) and send it with SES.

Dropped (counted in a log line, never delivered): spam or virus verdict FAIL, mail from our own forwarding address or already marked `X-Forwarded-By: videomk`
(loop guard), auto-replies / bulk / bounces (`Auto-Submitted`, `Precedence: bulk|junk|list`, null return-path).
Too big to send: a short notice goes instead; the original stays in S3 until the lifecycle rule expires it.
Logs hold counters and a short hash of the message id only: never an address, a subject or any content. A send failure raises, so the asynchronous retry
applies and, after the retries, the event lands in the dead-letter queue.
Alarm-friendly lines: `MAIL_FORWARD forwarded=1`, `MAIL_FORWARD dropped=1 reason=...`, `MAIL_FORWARD_FAILED stage=... id=...`.
"""
import email
import hashlib
import logging
import os
import re
from email import policy
from email.headerregistry import Address
from email.message import EmailMessage
from email.utils import getaddresses, parseaddr
from typing import Any, Dict, Optional

import boto3

log = logging.getLogger()
log.setLevel(logging.INFO)

MARKER_HEADER = "X-Forwarded-By"
MARKER_VALUE = "videomk"
# SES SendRawEmail accepts up to 10 MB per message, counted after encoding: stay below with room for the headers we add.
MAX_SEND_BYTES = 9_500_000
# Headers of the original that must not travel with the copy: signatures would fail (body/headers change), SES sets the others.
DROP_HEADERS = ("DKIM-Signature", "DomainKey-Signature", "ARC-Seal", "ARC-Message-Signature", "ARC-Authentication-Results", "Return-Path", "Sender",
                "Message-ID", "Received-SPF", "Authentication-Results", "From", "Reply-To", "To", "Cc", "Bcc", "Delivered-To", "X-Original-To",
                "X-Original-From", MARKER_HEADER, "X-SES-Spam-Verdict", "X-SES-Virus-Verdict", "Resent-From", "Resent-To", "Resent-Sender")

_s3 = None
_ses = None


def _clients():
    global _s3, _ses
    if _s3 is None:
        _s3 = boto3.client("s3")
        _ses = boto3.client("ses")
    return _s3, _ses


def _h(value: str) -> str:
    return hashlib.sha256((value or "").encode()).hexdigest()[:12]


def _cfg() -> Dict[str, str]:
    return {"bucket": os.environ["MAIL_BUCKET"], "prefix": os.environ.get("MAIL_KEY_PREFIX", ""),
            "forward_to": os.environ["FORWARD_TO"], "forward_from": os.environ["FORWARD_FROM"]}


def _clean_name(name: str) -> str:
    """A display name safe to put in a header: no control characters, no quotes or angle brackets, bounded length."""
    name = re.sub(r"[\x00-\x1f\x7f]+", " ", name or "")
    name = re.sub(r'["<>\\]', "", name).strip()
    return name[:120]


def _addr(value: Optional[str]) -> str:
    name, a = parseaddr(str(value or ""))
    a = a.strip()
    return a if re.fullmatch(r"[^\s<>@,;]+@[^\s<>@,;]+", a) else ""


def _verdict(receipt: Dict[str, Any], key: str) -> str:
    return str((receipt.get(key) or {}).get("status", "")).upper()


def _drop_reason(msg: EmailMessage, receipt: Dict[str, Any], source: str, sender: str, forward_from: str) -> Optional[str]:
    if "FAIL" in (_verdict(receipt, "spamVerdict"), str(msg.get("X-SES-Spam-Verdict", "")).strip().upper()):
        return "spam"
    if "FAIL" in (_verdict(receipt, "virusVerdict"), str(msg.get("X-SES-Virus-Verdict", "")).strip().upper()):
        return "virus"
    ff = forward_from.lower()
    if msg.get(MARKER_HEADER) is not None or sender.lower() == ff or source.lower() == ff:
        return "loop"
    auto = str(msg.get("Auto-Submitted", "")).strip().lower()
    if auto and auto != "no":
        return "auto_submitted"
    if str(msg.get("Precedence", "")).strip().lower() in ("bulk", "junk", "list"):
        return "bulk"
    rp = str(msg.get("Return-Path", "")).strip()
    if not source or source in ("<>",) or rp == "<>":
        return "null_return_path"
    return None


def rewrite(raw: bytes, *, forward_from: str, forward_to: str, original_to: str, sender_hint: str = "") -> EmailMessage:
    """The copy to send: same MIME tree, new envelope-ish headers."""
    msg = email.message_from_bytes(raw, policy=policy.default)
    orig_from = msg.get("From")
    name, a = parseaddr(str(orig_from or ""))
    sender = _addr(orig_from) or _addr(sender_hint)
    reply = _addr(msg.get("Reply-To")) or sender
    shown = _clean_name(name) or sender or "unknown sender"
    subject = msg.get("Subject")
    date = msg.get("Date")
    for h in DROP_HEADERS:
        del msg[h]
    local, _, domain = forward_from.partition("@")
    msg["From"] = Address(display_name=f"{shown} via videomk", username=local, domain=domain)
    if reply:
        msg["Reply-To"] = reply
    msg["To"] = forward_to
    msg["X-Original-From"] = sender or "unknown"
    msg["X-Original-To"] = original_to
    msg[MARKER_HEADER] = MARKER_VALUE
    if subject is None:
        msg["Subject"] = "(no subject)"
    return msg


def _notice(raw_msg: EmailMessage, *, forward_from: str, forward_to: str, size: int, bucket: str, key: str) -> EmailMessage:
    note = EmailMessage(policy=policy.default)
    note["From"] = Address(display_name="videomk mail", username=forward_from.split("@")[0], domain=forward_from.split("@")[1])
    note["To"] = forward_to
    note[MARKER_HEADER] = MARKER_VALUE
    note["Subject"] = "A message to hello@ was too large to forward"
    sender = raw_msg.get("X-Original-From", "unknown")
    subj = str(raw_msg.get("Subject", "(no subject)")).replace("\r", " ").replace("\n", " ")
    note.set_content(
        f"A message was received at the forwarding address but it is too large to forward by email ({size // 1024} KB; the limit is about {MAX_SEND_BYTES // 1024} KB).\n\n"
        f"From: {sender}\nSubject: {subj}\nDate: {raw_msg.get('Date', '')}\n\n"
        f"The original is kept in the S3 bucket {bucket} under {key} for 7 days, then deleted. Download it from the AWS console, or ask the sender to resend it smaller.\n")
    return note


def handler(event, _ctx=None):
    cfg = _cfg()
    s3, ses = _clients()
    rec = (event.get("Records") or [{}])[0].get("ses") or {}
    mail, receipt = rec.get("mail") or {}, rec.get("receipt") or {}
    mid = str(mail.get("messageId") or "")
    tag = _h(mid)
    # the S3 action stores the message under <prefix><messageId>; the id is generated by SES, but never trust it to build a path
    if not re.fullmatch(r"[A-Za-z0-9._=+-]{1,128}", mid) or ".." in mid:
        log.error("MAIL_FORWARD_FAILED stage=event id=%s", tag)
        raise ValueError("bad message id in event")
    key = cfg["prefix"] + mid
    try:
        raw = s3.get_object(Bucket=cfg["bucket"], Key=key)["Body"].read()
    except Exception:
        log.error("MAIL_FORWARD_FAILED stage=read id=%s", tag)
        raise
    msg = email.message_from_bytes(raw, policy=policy.default)
    source = str(mail.get("source") or "")
    sender = _addr(msg.get("From")) or _addr(source)
    reason = _drop_reason(msg, receipt, source, sender, cfg["forward_from"])
    if reason:
        log.info("MAIL_FORWARD dropped=1 reason=%s id=%s", reason, tag)
        return {"dropped": reason}
    dests = [d for d in (rec.get("receipt") or {}).get("recipients") or mail.get("destination") or [] if d]
    original_to = _addr(dests[0]) if dests else cfg["forward_from"]
    out = rewrite(raw, forward_from=cfg["forward_from"], forward_to=cfg["forward_to"], original_to=original_to or cfg["forward_from"], sender_hint=source)
    data = out.as_bytes()
    kind = "forwarded"
    if len(data) > MAX_SEND_BYTES:
        data = _notice(out, forward_from=cfg["forward_from"], forward_to=cfg["forward_to"], size=len(raw), bucket=cfg["bucket"], key=key).as_bytes()
        kind = "too_large"
    try:
        ses.send_raw_email(Source=cfg["forward_from"], Destinations=[cfg["forward_to"]], RawMessage={"Data": data})
    except Exception:
        log.error("MAIL_FORWARD_FAILED stage=send id=%s", tag)
        raise
    log.info("MAIL_FORWARD forwarded=1 kind=%s bytes=%d id=%s", kind, len(raw), tag)
    return {"forwarded": kind}
