"""The mail forwarder Lambda: header rewriting, drops, loop guard, big messages, logs without personal data. No network: fake S3 and SES."""
import io
import logging
import os
import sys
from email import message_from_bytes, policy
from email.message import EmailMessage

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "lambdas"))
import mail_activate  # noqa: E402
import mail_forwarder as mf  # noqa: E402

FROM, TO = "hello@videomk.com", "chris@agilegency.com"
SECRET = "supersecret-person@example.org"


class FakeS3:
    def __init__(self, objects):
        self.objects, self.asked = objects, []

    def get_object(self, Bucket, Key):
        self.asked.append((Bucket, Key))
        if Key not in self.objects:
            raise RuntimeError("NoSuchKey")
        return {"Body": io.BytesIO(self.objects[Key])}


class FakeSes:
    def __init__(self, fail=False):
        self.sent, self.fail = [], fail

    def send_raw_email(self, **kw):
        if self.fail:
            raise RuntimeError("Throttling")
        self.sent.append(kw)


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("MAIL_BUCKET", "raw-bucket")
    monkeypatch.setenv("MAIL_KEY_PREFIX", "incoming/")
    monkeypatch.setenv("FORWARD_TO", TO)
    monkeypatch.setenv("FORWARD_FROM", FROM)


def raw_mail(frm=f"Ana García <{SECRET}>", subject="Hola, ¿qué tal? Ünï", extra=None, attach=False, body="Hola — cuerpo ñ"):
    m = EmailMessage(policy=policy.SMTP)
    m["From"], m["To"], m["Subject"] = frm, FROM, subject
    m["Date"] = "Tue, 24 Nov 2026 10:00:00 +0000"
    m["Message-ID"] = "<orig@example.org>"
    m["Return-Path"] = f"<{SECRET}>"
    m["DKIM-Signature"] = "v=1; a=rsa-sha256; d=example.org; s=x; b=abc"
    for k, v in (extra or {}).items():
        m[k] = v
    m.set_content(body)
    if attach:
        m.add_attachment(b"%PDF-1.4 data", maintype="application", subtype="pdf", filename="informe-año.pdf")
    return m.as_bytes()


def run(raw, *, spam="PASS", virus="PASS", source=SECRET, ses=None, mid="abc123", recipients=(FROM,)):
    s3, ses = FakeS3({f"incoming/{mid}": raw}), ses or FakeSes()
    mf._s3, mf._ses = s3, ses
    event = {"Records": [{"ses": {"mail": {"messageId": mid, "source": source, "destination": list(recipients)},
                                  "receipt": {"spamVerdict": {"status": spam}, "virusVerdict": {"status": virus}, "recipients": list(recipients)}}}]}
    return mf.handler(event), s3, ses


def sent_msg(ses):
    return message_from_bytes(ses.sent[0]["RawMessage"]["Data"], policy=policy.default)


def test_headers_are_rewritten():
    out, s3, ses = run(raw_mail(extra={"Reply-To": "Other <other@example.org>", "Cc": "x@example.org"}))
    assert out == {"forwarded": "forwarded"}
    kw = ses.sent[0]
    assert kw["Source"] == FROM and kw["Destinations"] == [TO]
    m = sent_msg(ses)
    assert m["From"].addresses[0].addr_spec == FROM
    assert m["From"].addresses[0].display_name == "Ana García via videomk"
    assert m["Reply-To"].addresses[0].addr_spec == "other@example.org"
    assert m["To"].addresses[0].addr_spec == TO
    assert m["Cc"] is None
    assert m["X-Forwarded-By"] == "videomk"
    assert m["X-Original-From"] == SECRET and m["X-Original-To"] == FROM
    assert m["Subject"] == "Hola, ¿qué tal? Ünï"
    assert m["Date"] == "Tue, 24 Nov 2026 10:00:00 +0000"
    for gone in ("DKIM-Signature", "Return-Path", "Sender", "Message-ID"):
        assert m[gone] is None
    assert "Hola — cuerpo ñ" in m.get_body().get_content()


def test_reply_to_defaults_to_original_sender():
    run_out = run(raw_mail())
    assert sent_msg(run_out[2])["Reply-To"].addresses[0].addr_spec == SECRET


def test_s3_key_is_prefix_plus_message_id():
    _, s3, _ = run(raw_mail(), mid="r4nd0m-id_1")
    assert s3.asked == [("raw-bucket", "incoming/r4nd0m-id_1")]


@pytest.mark.parametrize("mid", ["../etc/passwd", "a/b", "", "x" * 200])
def test_bad_message_ids_are_refused(mid):
    mf._s3, mf._ses = FakeS3({}), FakeSes()
    with pytest.raises(ValueError):
        mf.handler({"Records": [{"ses": {"mail": {"messageId": mid}, "receipt": {}}}]})
    assert mf._s3.asked == []


def test_attachment_and_non_ascii_filename_survive():
    _, _, ses = run(raw_mail(attach=True))
    m = sent_msg(ses)
    parts = [p for p in m.iter_attachments()]
    assert len(parts) == 1 and parts[0].get_filename() == "informe-año.pdf" and parts[0].get_content() == b"%PDF-1.4 data"
    assert "Hola — cuerpo ñ" in m.get_body().get_content()


def test_display_name_cannot_inject_headers():
    _, _, ses = run(raw_mail(frm='"Evil\r\nBcc: x@y.z" <a@example.org>'.replace("\r\n", " ")))
    m = sent_msg(ses)
    assert m["Bcc"] is None and m["From"].addresses[0].addr_spec == FROM


@pytest.mark.parametrize("kw,reason", [({"spam": "FAIL"}, "spam"), ({"virus": "FAIL"}, "virus")])
def test_spam_and_virus_are_dropped(kw, reason):
    out, _, ses = run(raw_mail(), **kw)
    assert out == {"dropped": reason} and ses.sent == []


def test_header_verdict_also_drops():
    out, _, ses = run(raw_mail(extra={"X-SES-Spam-Verdict": "FAIL"}))
    assert out == {"dropped": "spam"} and ses.sent == []


def test_loop_guard():
    for raw, src in ((raw_mail(frm=f"Me <{FROM}>"), SECRET), (raw_mail(extra={"X-Forwarded-By": "videomk"}), SECRET), (raw_mail(), FROM)):
        out, _, ses = run(raw, source=src)
        assert out == {"dropped": "loop"} and ses.sent == []


@pytest.mark.parametrize("hdr,reason", [({"Auto-Submitted": "auto-replied"}, "auto_submitted"), ({"Precedence": "bulk"}, "bulk"), ({"Precedence": "junk"}, "bulk")])
def test_auto_mail_dropped(hdr, reason):
    out, _, ses = run(raw_mail(extra=hdr))
    assert out == {"dropped": reason} and ses.sent == []


def test_auto_submitted_no_is_kept():
    out, _, ses = run(raw_mail(extra={"Auto-Submitted": "no"}))
    assert out == {"forwarded": "forwarded"} and len(ses.sent) == 1


def test_null_return_path_dropped():
    out, _, ses = run(raw_mail(), source="")
    assert out == {"dropped": "null_return_path"} and ses.sent == []


def test_big_message_sends_a_notice(monkeypatch):
    monkeypatch.setattr(mf, "MAX_SEND_BYTES", 500)
    out, _, ses = run(raw_mail(body="x" * 2000, subject="Big one"))
    assert out == {"forwarded": "too_large"} and len(ses.sent) == 1
    m = sent_msg(ses)
    body = m.get_content()
    assert "incoming/abc123" in body and "7 days" in body and "x" * 100 not in body
    assert m["X-Forwarded-By"] == "videomk" and m["To"].addresses[0].addr_spec == TO


def test_logs_have_no_addresses_or_content(caplog):
    caplog.set_level(logging.INFO)
    run(raw_mail(subject="private subject"))
    run(raw_mail(), spam="FAIL")
    text = caplog.text
    assert "MAIL_FORWARD forwarded=1" in text and "dropped=1 reason=spam" in text
    for secret in (SECRET, "example.org", "private subject", "cuerpo", "chris@", "hello@", "abc123"):
        assert secret not in text


def test_send_failure_raises_and_logs_without_pii(caplog):
    caplog.set_level(logging.INFO)
    with pytest.raises(RuntimeError):
        run(raw_mail(), ses=FakeSes(fail=True))
    assert "MAIL_FORWARD_FAILED stage=send" in caplog.text and SECRET not in caplog.text


def test_missing_object_raises(caplog):
    mf._s3, mf._ses = FakeS3({}), FakeSes()
    with pytest.raises(RuntimeError):
        mf.handler({"Records": [{"ses": {"mail": {"messageId": "nope"}, "receipt": {}}}]})
    assert "MAIL_FORWARD_FAILED stage=read" in caplog.text


# ---- the rule-set activation custom resource ----
class FakeRuleSes:
    def __init__(self, active=""):
        self.active, self.calls = active, []

    def describe_active_receipt_rule_set(self):
        return {"Metadata": {"Name": self.active}} if self.active else {}

    def set_active_receipt_rule_set(self, RuleSetName=""):
        self.calls.append(RuleSetName)
        self.active = RuleSetName


def ev(kind):
    return {"RequestType": kind, "ResourceProperties": {"RuleSetName": "videomk-inbound"}}


def test_activation_refuses_foreign_active_set():
    s = FakeRuleSes(active="someone-else")
    with pytest.raises(RuntimeError, match="someone-else"):
        mail_activate.on_event(ev("Create"), ses=s)
    assert s.calls == []


def test_activation_when_none_or_ours():
    for start in ("", "videomk-inbound"):
        s = FakeRuleSes(active=start)
        mail_activate.on_event(ev("Update"), ses=s)
        assert s.active == "videomk-inbound"


def test_delete_deactivates_only_ours():
    s = FakeRuleSes(active="videomk-inbound")
    mail_activate.on_event(ev("Delete"), ses=s)
    assert s.active == ""
    other = FakeRuleSes(active="someone-else")
    mail_activate.on_event(ev("Delete"), ses=other)
    assert other.active == "someone-else" and other.calls == []
