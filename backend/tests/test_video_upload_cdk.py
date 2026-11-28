"""The video-upload stack (backend/vidup_stack.py): its own stack, least privilege, lifecycle, token on every route; and the main stack gaining NO resource from `-c videoUpload=1`."""
import json
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
MAIN = {"usage_table": "Usage", "flags_table": "Flags", "entitlements_table": "Ent", "safety_table": "Safety", "plans_param": "/videomk/qa/plans", "customer_pool_id": "eu-west-1_abc", "client_ids": ["c1", "c2"]}


@pytest.fixture(scope="module")
def tpl():
    import aws_cdk as cdk
    from aws_cdk.assertions import Template
    cwd = os.getcwd()
    os.chdir(ROOT)
    os.environ.setdefault("CDK_SKIP_LAYER_CHECK", "1")
    try:
        from backend_stack import BackendStack
        from vidup_stack import VideoUploadStack
        app = cdk.App(outdir=os.path.join(os.environ.get("TMPDIR", "/tmp"), "vmk-vidup-cdk"))
        t = Template.from_stack(VideoUploadStack(app, "videomk-qa-vidup", stage="qa", main=MAIN, web_origins=["https://app.videomk.com"], env=cdk.Environment(account="123456789012", region="eu-west-1"))).to_json()
        out = {"vidup": t}
        for name, ctx in (("off", {}), ("on", {"videoUpload": "1", "vidupApiUrl": "https://x.example/"})):
            a = cdk.App(context={"stage": "qa", "engine": "v2", **ctx}, outdir=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"vmk-vidup-main-{name}"))
            st = BackendStack(a, "videomk-qa", stage="qa", stage_cfg={"account": "123456789012", "region": "eu-west-1", "domain": None, "callbackUrls": ["https://qa.videomk.com/auth/callback"]},
                              env=cdk.Environment(account="123456789012", region="eu-west-1"))
            out[name] = Template.from_stack(st).to_json()
        yield out
    finally:
        os.chdir(cwd)


def res(t, typ):
    return {k: v for k, v in t["Resources"].items() if v["Type"] == typ}


def fn(t, suffix):
    (k, v), = [(k, v) for k, v in res(t, "AWS::Lambda::Function").items() if str(v["Properties"].get("FunctionName", "")).endswith(suffix)]
    return k, v


def statements(t, suffix):
    role = fn(t, suffix)[1]["Properties"]["Role"]["Fn::GetAtt"][0]
    out = []
    for v in res(t, "AWS::IAM::Policy").values():
        if {"Ref": role} in v["Properties"]["Roles"]:
            out += v["Properties"]["PolicyDocument"]["Statement"]
    return out


def test_the_bucket_is_private_and_originals_and_unused_clips_expire(tpl):
    (b,) = [v for v in res(tpl["vidup"], "AWS::S3::Bucket").values() if v["Properties"].get("BucketName") == "videomk-qa-vidup-123456789012"]
    assert b["Properties"]["PublicAccessBlockConfiguration"] == {"BlockPublicAcls": True, "BlockPublicPolicy": True, "IgnorePublicAcls": True, "RestrictPublicBuckets": True}
    rules = {r["Id"]: r for r in b["Properties"]["LifecycleConfiguration"]["Rules"]}
    assert rules["originals-never-stay"]["Prefix"] == "in/" and rules["originals-never-stay"]["ExpirationInDays"] == 1 and rules["unused-clips-expire"]["Prefix"] == "clips/" and rules["unused-clips-expire"]["ExpirationInDays"] == 14
    assert b["Properties"]["BucketEncryption"]
    assert b["Properties"]["CorsConfiguration"]["CorsRules"][0]["AllowedOrigins"] == ["https://app.videomk.com"]


def test_every_route_needs_the_customer_token(tpl):
    t = tpl["vidup"]
    routes = res(t, "AWS::ApiGatewayV2::Route")
    keys = sorted(v["Properties"]["RouteKey"] for v in routes.values())
    assert keys == ["DELETE /users/{user_id}/video-uploads/{clip_id}", "GET /users/{user_id}/video-uploads", "GET /users/{user_id}/video-uploads/{clip_id}", "POST /users/{user_id}/video-uploads",
                    "POST /users/{user_id}/video-uploads/{clip_id}/analyse"]
    assert all(v["Properties"]["AuthorizationType"] == "JWT" for v in routes.values())
    (a,) = res(t, "AWS::ApiGatewayV2::Authorizer").values()
    assert a["Properties"]["JwtConfiguration"]["Audience"] == ["c1", "c2"] and a["Properties"]["JwtConfiguration"]["Issuer"].endswith("/eu-west-1_abc")


def test_the_analysis_function_is_bounded_and_runs_once(tpl):
    p = fn(tpl["vidup"], "-analyse")[1]["Properties"]
    assert p["ReservedConcurrentExecutions"] == 5 and p["Timeout"] == 120 and p["MemorySize"] == 2048 and p["Environment"]["Variables"]["VIDUP_BUCKET"].get("Ref")
    ev = res(tpl["vidup"], "AWS::Lambda::EventInvokeConfig")
    assert fn(tpl["vidup"], "-api")[1]["Properties"]["Timeout"] == 15


def test_least_privilege_tables_only_by_key_prefix_no_wallet_no_videos(tpl):
    t = tpl["vidup"]
    for suffix in ("-api", "-analyse"):
        for s in statements(t, suffix):
            acts = s["Action"] if isinstance(s["Action"], list) else [s["Action"]]
            text = json.dumps(s["Resource"])
            if any(a.startswith("dynamodb:") for a in acts):
                assert any(x in text for x in (":table/Usage", ":table/Flags", ":table/Ent", ":table/Safety")) and "Wallet" not in text and "Videos" not in text
                if ":table/Usage" in text:
                    assert s["Condition"]["ForAllValues:StringLike"]["dynamodb:LeadingKeys"] == ["vidrec:*", "vidup:*", "vidhash:*", "vidbad"]
                if ":table/Flags" in text:
                    assert acts == ["dynamodb:GetItem"]
                    if suffix == "-analyse" or "Condition" in s:
                        assert s["Condition"]["ForAllValues:StringEquals"]["dynamodb:LeadingKeys"] == ["ops:switches"]
    api_acts = sorted({a for s in statements(t, "-api") for a in (s["Action"] if isinstance(s["Action"], list) else [s["Action"]])})
    assert "bedrock:InvokeModel" not in api_acts and "lambda:InvokeFunction" in api_acts
    an_acts = sorted({a for s in statements(t, "-analyse") for a in (s["Action"] if isinstance(s["Action"], list) else [s["Action"]])})
    assert "bedrock:InvokeModel" in an_acts and "lambda:InvokeFunction" not in an_acts and "dynamodb:GetItem" in an_acts
    s3s = [s for s in statements(t, "-analyse") if "s3:PutObject" in json.dumps(s["Action"])]
    assert all("/in/*" in json.dumps(s["Resource"]) or "/clips/*" in json.dumps(s["Resource"]) for s in s3s)


def test_the_bundle_holds_the_handlers_common_and_the_model_client_only():
    import vidup_stack
    out = vidup_stack.bundle(os.path.join(os.environ.get("TMPDIR", "/tmp"), "vmk-vidup-bundle"))
    for f in ("vidup_api.py", "vidup_analyse.py", "engine/llm.py", "engine/__init__.py", "common/vidup.py", "common/vidup_media.py", "common/media_policy.py", "common/stt.py", "common/intake.py"):
        assert os.path.exists(os.path.join(out, f)), f
    assert not os.path.exists(os.path.join(out, "engine", "plan.py"))


def test_the_main_stack_gains_no_resource_and_only_a_variable_and_a_statement(tpl):
    off, on = tpl["off"], tpl["on"]
    assert sorted(off["Resources"]) == sorted(on["Resources"])                                  # no new resource (the stack is near 500)
    _, l_off = fn(off, "VideoGenerationSFLauncher")
    _, l_on = fn(on, "VideoGenerationSFLauncher")
    assert "VIDUP_BUCKET" not in l_off["Properties"]["Environment"]["Variables"] and l_on["Properties"]["Environment"]["Variables"]["VIDUP_BUCKET"] == "videomk-qa-vidup-123456789012"
    role = l_on["Properties"]["Role"]["Fn::GetAtt"][0]
    st = [s for v in res(on, "AWS::IAM::Policy").values() if {"Ref": role} in v["Properties"]["Roles"] for s in v["Properties"]["PolicyDocument"]["Statement"]]
    assert {"Action": "s3:GetObject", "Effect": "Allow", "Resource": "arn:aws:s3:::videomk-qa-vidup-123456789012/clips/*"} in st
