"""HD render function (docs/COST_LEVERS_2026-11-28.md): 720p/1080p chunks render on a 4,096 MB function, 4K stays on the 10,240 MB one; hdRenderMemoryMb=0 gives back the old stack."""
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
        os.environ.setdefault("CDK_SKIP_LAYER_CHECK", "1")
        out = {}
        for name, ctx in (("hd", {}), ("off", {"hdRenderMemoryMb": "0"}), ("whiteboard", {"imageCatalog": "1", "whiteboard": "1", "vectorScenes": "1"})):
            app = cdk.App(context={"stage": "qa", "engine": "v2", **ctx}, outdir=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"vmk-hdr-{name}"))
            stack = BackendStack(app, "videomk-qa", stage="qa", stage_cfg={"account": "123456789012", "region": "eu-west-1", "domain": None, "callbackUrls": ["https://qa.videomk.com/auth/callback"]},
                                 env=cdk.Environment(account="123456789012", region="eu-west-1"))
            out[name] = Template.from_stack(stack).to_json()
        yield out
    finally:
        os.chdir(cwd)


def _fn(t, name):
    hits = [v for v in t["Resources"].values() if v["Type"] == "AWS::Lambda::Function" and v["Properties"].get("FunctionName") == name]
    return hits[0] if hits else None


def test_hd_function_is_smaller_and_4k_keeps_10gb(templates):
    t = templates["hd"]
    assert _fn(t, "v2_render_chunk_hd")["Properties"]["MemorySize"] == 4096
    assert _fn(t, "v2_render_chunk")["Properties"]["MemorySize"] == 10240
    assert _fn(t, "v2_render_chunk_hd")["Properties"]["Handler"] == _fn(t, "v2_render_chunk")["Properties"]["Handler"]
    assert _fn(t, "v2_render_chunk_hd")["Properties"]["Timeout"] == _fn(t, "v2_render_chunk")["Properties"]["Timeout"] == 600


def test_off_is_the_old_stack(templates):
    assert _fn(templates["off"], "v2_render_chunk_hd") is None
    assert _fn(templates["off"], "v2_render_chunk")["Properties"]["MemorySize"] == 10240
    extra = len(templates["hd"]["Resources"]) - len(templates["off"]["Resources"])
    assert 0 < extra <= 6, extra     # a function, its role, its policy, its log group: the stack is near the 500-resource limit


def test_the_map_chooses_by_big(templates):
    machines = [v for v in templates["hd"]["Resources"].values() if v["Type"] == "AWS::StepFunctions::StateMachine" and v["Properties"].get("StateMachineName") == "generate_video_workflow_v2"]
    text = json.dumps(machines[0]["Properties"]["DefinitionString"])
    assert "$.big" in text and "V2RenderChunkHd" in text and "V2RenderChunk\\\"" in text.replace("V2RenderChunkHd", "")


def test_the_hd_function_has_the_same_grants_as_the_big_one(templates):
    t = templates["whiteboard"]
    roles = {}
    for name in ("v2_render_chunk", "v2_render_chunk_hd"):
        role = _fn(t, name)["Properties"]["Role"]["Fn::GetAtt"][0]
        acts = set()
        for v in t["Resources"].values():
            if v["Type"] == "AWS::IAM::Policy" and {"Ref": role} in v["Properties"]["Roles"]:
                for st in v["Properties"]["PolicyDocument"]["Statement"]:
                    a = st["Action"] if isinstance(st["Action"], list) else [st["Action"]]
                    acts |= {(x, json.dumps(st.get("Resource"), sort_keys=True)) for x in a}
        roles[name] = {a for a, _ in acts}
    assert roles["v2_render_chunk"] == roles["v2_render_chunk_hd"] and "s3:GetObject" in roles["v2_render_chunk_hd"]
