"""The one change the owner console needs in the main stack (docs/ADMIN_CONSOLE_DESIGN_2026-11-28.md section 2.3): an index by day on the videos table that
carries small fields only (never the prompt), and nothing else: the emergency switches are read from the account-flags table the launcher can already read."""
import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)


@pytest.fixture(scope="module")
def template():
    import aws_cdk as cdk
    from aws_cdk.assertions import Template

    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        from backend_stack import BackendStack
        os.environ.setdefault("CDK_SKIP_LAYER_CHECK", "1")
        app = cdk.App(context={"stage": "qa", "engine": "v2"}, outdir=os.path.join(os.environ.get("TMPDIR", "/tmp"), "vmk-usage-day"))
        stack = BackendStack(app, "videomk-qa", stage="qa", stage_cfg={"account": "123456789012", "region": "eu-west-1", "domain": None}, env=cdk.Environment(account="123456789012", region="eu-west-1"))
        yield Template.from_stack(stack).to_json()
    finally:
        os.chdir(cwd)


def videos_table(t):
    return next(v for k, v in t["Resources"].items() if v["Type"] == "AWS::DynamoDB::Table" and k.startswith("VideosTable"))["Properties"]


def test_the_videos_table_has_an_index_by_day_with_small_fields_only(template):
    import backend_stack
    idx = {i["IndexName"]: i for i in videos_table(template)["GlobalSecondaryIndexes"]}
    assert set(idx) == {"GSI_UserVideos", "GSI_UsageDay"}
    day = idx["GSI_UsageDay"]
    assert [(k["AttributeName"], k["KeyType"]) for k in day["KeySchema"]] == [("usage_day", "HASH"), ("created_at", "RANGE")]
    assert day["Projection"]["ProjectionType"] == "INCLUDE" and set(day["Projection"]["NonKeyAttributes"]) == set(backend_stack.USAGE_DAY_FIELDS)
    for private in ("prompt", "request_json", "title", "youtube_description", "video_uri", "charge"):
        assert private not in day["Projection"]["NonKeyAttributes"]
    assert {"status", "plan", "user_id", "cost_usd", "failure_code", "duration_s"} <= set(day["Projection"]["NonKeyAttributes"])


def test_the_switches_need_no_new_permission_variable_or_resource(template):
    """The launcher already reads the account-flags table (and cannot write it); nothing in the main stack mentions an ops parameter."""
    text = json.dumps(template)
    assert "ops/config" not in text and "OPS_" not in text
    fns = {v["Properties"].get("FunctionName"): v for v in template["Resources"].values() if v["Type"] == "AWS::Lambda::Function"}
    launcher = fns["VideoGenerationSFLauncher"]
    assert "FLAGS_TABLE" in launcher["Properties"]["Environment"]["Variables"]
    role = launcher["Properties"]["Role"]["Fn::GetAtt"][0]
    flags = next(k for k, v in template["Resources"].items() if v["Type"] == "AWS::DynamoDB::Table" and k.startswith("AccountFlagsTable"))
    writes = {"dynamodb:PutItem", "dynamodb:UpdateItem", "dynamodb:DeleteItem", "dynamodb:BatchWriteItem", "dynamodb:*"}
    for p in template["Resources"].values():
        if p["Type"] == "AWS::IAM::Policy" and any(r.get("Ref") == role for r in p["Properties"].get("Roles", [])):
            for s in p["Properties"]["PolicyDocument"]["Statement"]:
                acts = set(s["Action"] if isinstance(s["Action"], list) else [s["Action"]])
                if flags in json.dumps(s["Resource"]):
                    assert not (acts & writes), "the launcher must never write the flags table (it holds the unlimited flag and the switches)"
