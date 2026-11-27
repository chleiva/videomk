"""Library clips on demand in the CDK stack (docs/CLIPS_ON_DEMAND.md): off by default, and when on it adds NO resource to the main stack (it is near 500)."""
import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)


@pytest.fixture(scope="module")
def templates():
    import aws_cdk as cdk
    from aws_cdk.assertions import Template

    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        from backend_stack import BackendStack
        from clips_obs import ClipsObsStack
        os.environ.setdefault("CDK_SKIP_LAYER_CHECK", "1")
        out = {}
        for name, ctx in (("off", {}), ("on", {"clipsOnDemand": "1"})):
            app = cdk.App(context={"stage": "qa", "engine": "v2", **ctx}, outdir=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"vmk-clipsod-{name}"))
            stack = BackendStack(app, "videomk-qa", stage="qa", stage_cfg={"account": "123456789012", "region": "eu-west-1", "domain": None, "callbackUrls": ["https://qa.videomk.com/auth/callback"]},
                                 env=cdk.Environment(account="123456789012", region="eu-west-1"))
            out[name] = Template.from_stack(stack).to_json()
        app = cdk.App(outdir=os.path.join(os.environ.get("TMPDIR", "/tmp"), "vmk-clipsod-obs"))
        out["obs"] = Template.from_stack(ClipsObsStack(app, "videomk-qa-clips-obs", day_budget_usd=10)).to_json()
        yield out
    finally:
        os.chdir(cwd)


def _beat(t):
    (fn,) = [v for v in t["Resources"].values() if v["Type"] == "AWS::Lambda::Function" and v["Properties"].get("FunctionName") == "v2_beat"]
    return fn


def _beat_statements(t):
    role = _beat(t)["Properties"]["Role"]["Fn::GetAtt"][0]
    out = []
    for v in t["Resources"].values():
        if v["Type"] == "AWS::IAM::Policy" and {"Ref": role} in v["Properties"]["Roles"]:
            out += v["Properties"]["PolicyDocument"]["Statement"]
    return out


def test_off_by_default_the_beat_function_knows_nothing_of_it(templates):
    env = _beat(templates["off"])["Properties"]["Environment"]["Variables"]
    assert "CLIPS_ON_DEMAND" not in env and "CLIPS_CONFIG_PARAM" not in env
    assert "cliplib" not in json.dumps(templates["off"]) and "clipgen" not in json.dumps(templates["off"])


def test_switched_on_it_adds_no_resource_to_the_main_stack(templates):
    off, on = templates["off"]["Resources"], templates["on"]["Resources"]
    assert set(on) == set(off) and len(on) == len(off)
    changed = sorted(k for k in on if on[k] != off[k])
    assert len(changed) == 2 and {on[k]["Type"] for k in changed} == {"AWS::Lambda::Function", "AWS::IAM::Policy"}     # the beat function's variables and its own policy


def test_switched_on_the_beat_function_gets_exactly_the_rights_it_needs(templates):
    env = _beat(templates["on"])["Properties"]["Environment"]["Variables"]
    assert env["CLIPS_ON_DEMAND"] == "1" and env["CLIPS_CONFIG_PARAM"] == "/videomk/qa/clips/config" and env["USAGE_TABLE"] and env["ASSETS_BUCKET"]
    new = [s for s in _beat_statements(templates["on"]) if s not in _beat_statements(templates["off"])]
    assert len(new) == 3
    table = next(s for s in new if "dynamodb:Query" in s["Action"])
    assert sorted(table["Action"]) == ["dynamodb:DeleteItem", "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:Query", "dynamodb:UpdateItem"]
    assert table["Condition"] == {"ForAllValues:StringLike": {"dynamodb:LeadingKeys": ["clipgen:*"]}}                    # only this feature's rows of the usage table
    bucket = next(s for s in new if "s3:PutObject" in s["Action"])
    assert sorted(bucket["Action"]) == ["s3:GetObject", "s3:PutObject"] and json.dumps(bucket["Resource"]).endswith('/cliplib/*"')
    param = next(s for s in new if s["Action"] == "ssm:GetParameter")
    assert "parameter/videomk/qa/clips/config" in json.dumps(param["Resource"])
    assert "parameter/videomk/*_api_key" in json.dumps(_beat_statements(templates["on"]))                                 # the provider key: a right the function already had


def test_the_alarms_live_in_their_own_small_stack(templates):
    res = templates["obs"]["Resources"]
    assert len(res) == 2 and {v["Type"] for v in res.values()} == {"AWS::CloudWatch::Alarm"}
    by = {v["Properties"]["MetricName"]: v["Properties"] for v in res.values()}
    assert by["BudgetStop"]["Threshold"] == 1 and by["SpendUsd"]["Threshold"] == 8 and all("AlarmActions" not in p for p in by.values())
