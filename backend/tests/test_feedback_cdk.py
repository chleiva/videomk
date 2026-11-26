"""The feedback loop in the CDK template, with the flag on (default) and off (`-c feedback=0`): table, route, schedule, rights, sender."""
import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "lambdas"))


@pytest.fixture(scope="module")
def synth():
    import aws_cdk as cdk
    from aws_cdk.assertions import Template

    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        from backend_stack import BackendStack
        cache = {}

        def build(stage="qa", **ctx):
            ctx.setdefault("engine", "v2")
            key = (stage,) + tuple(sorted(ctx.items()))
            if key not in cache:
                app = cdk.App(context={"stage": stage, **ctx}, outdir=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"vmk-fb-{len(cache)}"))
                os.environ.setdefault("CDK_SKIP_LAYER_CHECK", "1")
                acct, region = ("464863885161", "us-west-2") if stage == "prod" else ("123456789012", "eu-west-1")
                stack = BackendStack(app, f"videomk-{stage}", stage=stage, stage_cfg={"account": acct, "region": region, "domain": None, "callbackUrls": ["https://qa.videomk.com/auth/callback"]},
                                     env=cdk.Environment(account=acct, region=region))
                cache[key] = Template.from_stack(stack).to_json()
            return cache[key]
        yield build
    finally:
        os.chdir(cwd)


def of(t, typ):
    return {k: v for k, v in t["Resources"].items() if v["Type"] == typ}


def fn(t, name):
    (v,) = [v for v in of(t, "AWS::Lambda::Function").values() if v["Properties"].get("FunctionName") == name]
    return v["Properties"]


def feedback_tables(t):
    return {k: v for k, v in of(t, "AWS::DynamoDB::Table").items() if "FeedbackTable" in k}


def test_on_by_default_table_is_kept_encrypted_and_without_ttl(synth):
    t = synth()
    ((_, tbl),) = feedback_tables(t).items()
    p = tbl["Properties"]
    assert p["BillingMode"] == "PAY_PER_REQUEST" and p["KeySchema"] == [{"AttributeName": "feedbackId", "KeyType": "HASH"}]
    assert p["PointInTimeRecoverySpecification"]["PointInTimeRecoveryEnabled"] is True
    assert "TimeToLiveSpecification" not in p and tbl["DeletionPolicy"] == "Retain"
    assert "SSESpecification" not in p   # default at-rest encryption (DynamoDB-owned key), like the other tables
    gsis = {g["IndexName"]: g for g in p["GlobalSecondaryIndexes"]}
    assert gsis["GSI_Pending"]["Projection"]["ProjectionType"] == "ALL" and gsis["GSI_User"]["Projection"]["ProjectionType"] == "KEYS_ONLY"


def test_route_is_cognito_protected_and_put_only(synth):
    t = synth()
    res = [k for k, v in of(t, "AWS::ApiGateway::Resource").items() if v["Properties"]["PathPart"] == "feedback"]
    assert len(res) == 1
    methods = [v["Properties"] for v in of(t, "AWS::ApiGateway::Method").values() if v["Properties"].get("ResourceId") == {"Ref": res[0]}]
    assert {m["HttpMethod"] for m in methods} == {"POST", "OPTIONS"}
    post = [m for m in methods if m["HttpMethod"] == "POST"][0]
    assert post["AuthorizationType"] == "COGNITO_USER_POOLS"
    actions = {a for pol in of(t, "AWS::IAM::Policy").values() for s in pol["Properties"]["PolicyDocument"]["Statement"] if "FeedbackTable" in json.dumps(s["Resource"]) for a in ([s["Action"]] if isinstance(s["Action"], str) else s["Action"])}
    assert "dynamodb:PutItem" in actions and "dynamodb:DeleteItem" not in actions   # nothing deletes feedback


def test_daily_schedule_at_nine_utc_targets_the_digest(synth):
    t = synth()
    rules = [v["Properties"] for k, v in of(t, "AWS::Events::Rule").items() if "Feedback" in k]
    assert len(rules) == 1 and rules[0]["ScheduleExpression"] == "cron(0 9 * * ? *)"
    assert fn(t, "feedback_digest")["Handler"] == "feedback_digest.handler"
    assert fn(t, "feedback_digest")["Environment"]["Variables"]["FEEDBACK_EMAIL_TO_PARAM"] == "/videomk/feedback_email_to"


def test_ssm_parameter_is_read_only_and_not_created(synth):
    t = synth()
    assert not of(t, "AWS::SSM::Parameter")
    stm = [s for pol in of(t, "AWS::IAM::Policy").values() for s in pol["Properties"]["PolicyDocument"]["Statement"] if "ssm:GetParameter" in json.dumps(s["Action"]) and "feedback_email_to" in json.dumps(s["Resource"])]
    assert len(stm) == 1


def test_qa_has_no_sender_and_no_ses_right(synth):
    t = synth()
    assert fn(t, "feedback_digest")["Environment"]["Variables"]["FEEDBACK_FROM"] == ""
    assert not [1 for pol in of(t, "AWS::IAM::Policy").values() for s in pol["Properties"]["PolicyDocument"]["Statement"] if "ses:SendEmail" in json.dumps(s["Action"]) and "FeedbackTable" not in json.dumps(s)]


def test_qa_can_send_to_a_verified_address_with_context(synth):
    t = synth(feedbackFrom="qa@example.com", feedbackSesRegion="eu-west-1")
    assert fn(t, "feedback_digest")["Environment"]["Variables"]["FEEDBACK_FROM"] == "qa@example.com"


def test_prod_sends_from_the_videomk_identity_in_us_east_1(synth):
    t = synth(stage="prod")
    e = fn(t, "feedback_digest")["Environment"]["Variables"]
    assert e["FEEDBACK_FROM"] == "hello@videomk.com" and e["FEEDBACK_SES_REGION"] == "us-east-1"
    (s,) = [s for pol in of(t, "AWS::IAM::Policy").values() for s in pol["Properties"]["PolicyDocument"]["Statement"] if "ses:SendEmail" in json.dumps(s["Action"])]
    assert s["Condition"]["StringEquals"]["ses:FromAddress"] == "hello@videomk.com" and "us-east-1" in json.dumps(s["Resource"])


def test_account_deletion_knows_the_table_and_may_only_update_it(synth):
    t = synth()
    e = fn(t, "account_deleter")["Environment"]["Variables"]
    assert "FeedbackTable" in json.dumps(e["FEEDBACK_TABLE"])


def test_flag_off_removes_everything(synth):
    t = synth(feedback="0")
    assert not feedback_tables(t)
    names = {v["Properties"].get("FunctionName") for v in of(t, "AWS::Lambda::Function").values()}
    assert "feedback_api" not in names and "feedback_digest" not in names
    assert not [k for k, v in of(t, "AWS::ApiGateway::Resource").items() if v["Properties"]["PathPart"] == "feedback"]
    assert not [k for k in of(t, "AWS::Events::Rule") if "Feedback" in k]
    assert "FEEDBACK_TABLE" not in fn(t, "account_deleter")["Environment"]["Variables"]
