"""The email-forwarding stack: DNS in the imported zone, private raw bucket, one receipt rule for hello@ only, least-privilege IAM, off unless -c mail=1."""
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
ZONE = "Z07620702J1XHOWB4O7NZ"


@pytest.fixture(scope="module")
def t(tmp_path_factory):
    import aws_cdk as cdk
    from aws_cdk.assertions import Template
    from mail_forward import MailForwardStack
    app = cdk.App(outdir=str(tmp_path_factory.mktemp("mail")))
    st = MailForwardStack(app, "videomk-mail", forward_to="chris@agilegency.com", forward_from="hello@videomk.com", env=cdk.Environment(account="464863885161", region="us-east-1"))
    return Template.from_stack(st).to_json()


def of(t, typ):
    return {k: v for k, v in t["Resources"].items() if v["Type"] == typ}


def records(t, typ):
    return [v["Properties"] for v in of(t, "AWS::Route53::RecordSet").values() if v["Properties"]["Type"] == typ]


def test_no_new_zone_and_records_go_to_the_imported_zone(t):
    assert not of(t, "AWS::Route53::HostedZone")
    assert all(r["HostedZoneId"] == ZONE for r in records(t, "MX") + records(t, "TXT") + records(t, "CNAME"))


def test_domain_identity_with_easydkim_and_destination_identity(t):
    ids = {v["Properties"]["EmailIdentity"]: v["Properties"] for v in of(t, "AWS::SES::EmailIdentity").values()}
    assert set(ids) == {"videomk.com", "chris@agilegency.com"}
    assert len(records(t, "CNAME")) == 3   # the three EasyDKIM records


def test_mx_spf_dmarc(t):
    mx = records(t, "MX")
    assert len(mx) == 1 and mx[0]["Name"] == "videomk.com." and mx[0]["ResourceRecords"] == ["10 inbound-smtp.us-east-1.amazonaws.com"]
    txt = {r["Name"]: r["ResourceRecords"] for r in records(t, "TXT")}
    assert txt["videomk.com."] == ['"v=spf1 include:amazonses.com ~all"']
    assert txt["_dmarc.videomk.com."] == ['"v=DMARC1; p=none; adkim=r; aspf=r"']
    assert "rua" not in json.dumps(txt)


def test_one_rule_for_hello_only(t):
    (rule,) = of(t, "AWS::SES::ReceiptRule").values()
    r = rule["Properties"]["Rule"]
    assert r["Recipients"] == ["hello@videomk.com"] and r["ScanEnabled"] and r["TlsPolicy"] == "Require" and r["Enabled"]
    acts = r["Actions"]
    assert "S3Action" in acts[0] and acts[1]["LambdaAction"]["InvocationType"] == "Event"
    assert len(of(t, "AWS::SES::ReceiptRuleSet")) == 1


def test_bucket_private_lifecycle_and_ses_only_policy(t):
    (b,) = of(t, "AWS::S3::Bucket").values()
    p = b["Properties"]
    assert all(p["PublicAccessBlockConfiguration"].values()) and len(p["PublicAccessBlockConfiguration"]) == 4
    assert p["BucketEncryption"]
    assert p["LifecycleConfiguration"]["Rules"][0]["ExpirationInDays"] == 7
    (pol,) = of(t, "AWS::S3::BucketPolicy").values()
    stmts = pol["Properties"]["PolicyDocument"]["Statement"]
    allows = [s for s in stmts if s["Effect"] == "Allow"]
    assert all(s["Principal"] == {"Service": "ses.amazonaws.com"} for s in allows)
    assert any(s["Condition"]["StringEquals"].get("AWS:SourceArn", "").endswith("receipt-rule/forward-hello") for s in allows if "Condition" in s)
    assert any(s["Effect"] == "Deny" and "aws:SecureTransport" in json.dumps(s) for s in stmts)


def test_forwarder_function_settings_and_dlq(t):
    (f,) = [v for v in of(t, "AWS::Lambda::Function").values() if v["Properties"].get("FunctionName") == "videomk-mail-forwarder"]
    p = f["Properties"]
    assert p["Runtime"] == "python3.12" and p["Timeout"] == 60 and p["MemorySize"] <= 256 and "DeadLetterConfig" in p
    assert p["Environment"]["Variables"]["FORWARD_TO"] == "chris@agilegency.com"
    assert of(t, "AWS::SQS::Queue") and of(t, "AWS::CloudWatch::Alarm")


def test_ses_send_is_scoped(t):
    sends = [s for pol in of(t, "AWS::IAM::Policy").values() for s in pol["Properties"]["PolicyDocument"]["Statement"] if "ses:SendRawEmail" in json.dumps(s["Action"])]
    assert len(sends) == 1
    s = sends[0]
    assert s["Resource"] != "*" and "*" not in json.dumps(s["Resource"]).replace("arn:", "")
    assert s["Condition"]["StringEquals"]["ses:FromAddress"] == "hello@videomk.com"
    gets = [s for pol in of(t, "AWS::IAM::Policy").values() for s in pol["Properties"]["PolicyDocument"]["Statement"] if "s3:GetObject" in json.dumps(s["Action"])]
    assert gets and all(g["Resource"] != "*" for g in gets)


def test_activation_custom_resource_present(t):
    cs = [v for v in t["Resources"].values() if v["Type"] == "AWS::CloudFormation::CustomResource" or v["Type"].startswith("Custom::")]
    assert any(c["Properties"].get("RuleSetName") == "videomk-inbound" for c in cs)


def _synth(ctx, tmp_path):
    env = dict(os.environ, CDK_CONTEXT_JSON=json.dumps(ctx), CDK_OUTDIR=str(tmp_path))
    env.pop("CDK_DEFAULT_ACCOUNT", None)
    return subprocess.run([sys.executable, "app.py"], cwd=ROOT, env=env, capture_output=True, text=True)


def test_stack_only_with_flag(tmp_path):
    on = _synth({"mail": "1"}, tmp_path / "on")
    assert on.returncode == 0, on.stderr
    assert (tmp_path / "on" / "videomk-mail.template.json").exists()
    off = _synth({}, tmp_path / "off")
    assert off.returncode != 0 and not (tmp_path / "off" / "videomk-mail.template.json").exists()


def test_bad_destination_refused(tmp_path):
    r = _synth({"mail": "1", "forwardTo": "not-an-address"}, tmp_path)
    assert r.returncode != 0 and "not an email address" in (r.stderr + r.stdout)
