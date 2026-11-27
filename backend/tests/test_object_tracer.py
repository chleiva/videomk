"""The whiteboard TRACER function (docs/LIBRARY_ON_DEMAND.md part D): the maker of sketch objects in a small function of its own stack, called by the plan step.
What is tested: the call from the engine (and every way it can fail: the labels stay), the function's handler, the code bundle on its own, the real tracing
pipeline on a drawn sheet, and the stack. No network: the provider, the models and the Lambda call are stand-ins."""
import base64
import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile

import pytest

os.environ.setdefault("WB_OUT", os.path.join(tempfile.gettempdir(), "vmk-wb-tests"))   # the builder's work folder (its spend log): never the real one

from common import clip_store as cs, object_maker   # noqa: E402
from engine import clip_ondemand as od, llm, object_ondemand as oo   # noqa: E402

sys.path.insert(0, os.path.dirname(__file__))
from test_library_on_demand import ON, _board_plan, _picture, _pkg, env, spent, wb   # noqa: E402,F401 - the same stand-ins and fixtures

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
NAME = "videomk-qa-wb-tracer"


def _answer(objs, rejected=()):
    ok = [(o, n) for o, n in objs if o not in rejected]
    return {"packages": [_pkg(o, n) for o, n in ok], "thumbs": {o: base64.b64encode(_picture(4, (64, 64))).decode() for o, _ in ok},
            "stats": {"sheet_usd": 0.0375, "sheet_s": 8.1, "total_s": 10.3, "rejected": {o: "gate: not clean" for o in rejected}}}


# ================================================================= the engine's side of the call
def test_the_plan_step_sends_only_english_names_and_gets_drawings_back(wb, monkeypatch):
    seen = []

    def invoke(name, payload, timeout):
        seen.append((name, json.loads(payload), timeout))
        return json.dumps(_answer(json.loads(payload)["objects"], rejected=("teapot",))).encode()
    oo.set_maker(None)
    oo.set_invoker(invoke)
    monkeypatch.setenv("OBJECT_TRACER_FUNCTION", NAME)
    try:
        plan = _board_plan("honeycomb", "teapot")
        got = oo.fill(plan, video_id="v1", ctx=od.context("v1"))
        assert got["made"] == ["honeycomb"] and got["reason"] == "generated"
        (name, req, timeout), = seen                                                                       # ONE call for the video
        assert name == NAME and req == {"action": "make", "objects": [["honeycomb", "honeycomb"], ["teapot", "teapot"]], "timeout": 30} and timeout == 32.0
        assert "v1" not in json.dumps(req) and "u1" not in json.dumps(req)                                 # nothing of the customer or the video goes to the function
        items = plan["beats"][0]["scene"]["props"]["items"]
        assert items[0]["draw"] == "honeycomb" and items[1]["write"] == "teapot" and items[1]["boxed"] is True
        assert wb.store.get(oo.WOBJ, "honeycomb")["status"] == "active" and (wb.dir / "honeycomb.json").exists()   # stored in OUR library by the plan step, not by the function
    finally:
        oo.set_invoker(None)


@pytest.mark.parametrize("failure, reason, charged", [
    ("missing", "provider_failed", 0.0),          # the tracer stack is not deployed: nothing was paid, the reservation goes back
    ("denied", "provider_failed", 0.0),
    ("timeout", "timeout", 0.047),                # no answer in time: the sheet may have been paid for, so the reservation stays
    ("crash", "provider_failed", 0.047),          # the function failed after starting
    ("garbage", "provider_failed", 0.047),
    ("refused_unbilled", "provider_failed", 0.0),
    ("refused_moderation", "policy_refused", 0.0),
    ("refused_billed", "policy_refused", 0.047),
])
def test_a_missing_slow_or_failing_function_leaves_the_labels(wb, monkeypatch, failure, reason, charged):
    class Aws(Exception):
        def __init__(self, code):
            super().__init__(code)
            self.response = {"Error": {"Code": code}}

    def invoke(name, payload, timeout):
        if failure == "missing":
            raise Aws("ResourceNotFoundException")
        if failure == "denied":
            raise Aws("AccessDeniedException")
        if failure == "timeout":
            raise Exception("Read timed out on endpoint URL")
        if failure == "crash":
            return json.dumps({"refused": "tracer error (MemoryError)", "billed": True}).encode()
        if failure == "garbage":
            return b'{"errorMessage": "Task timed out after 60.00 seconds"}'
        if failure == "refused_unbilled":
            return json.dumps({"refused": "auth", "billed": False}).encode()
        if failure == "refused_moderation":
            return json.dumps({"refused": "moderation:violence", "billed": False}).encode()
        return json.dumps({"refused": "moderation:sexual", "billed": True}).encode()
    oo.set_maker(None)
    oo.set_invoker(invoke)
    monkeypatch.setenv("OBJECT_TRACER_FUNCTION", NAME)
    try:
        plan = _board_plan("violin")
        got = oo.fill(plan, video_id="v1", ctx=od.context("v1"))
        assert got["reason"] == reason and got["made"] == []
        assert plan["beats"][0]["scene"]["props"]["items"][0] == {"id": "i0", "write": "violin", "boxed": True, "zone": "centre"}      # exactly what the board had
        assert spent(wb.store, "object") == pytest.approx(charged) and wb.store.get(oo.WOBJ, "violin") is None
        (line,) = wb.store.query(cs.ledger_pk(cs.month()))
        assert line["outcome"] == reason and line["charged_usd"] == pytest.approx(charged)
    finally:
        oo.set_invoker(None)


def test_without_the_function_and_without_the_tracing_code_nothing_is_asked_or_spent(wb, monkeypatch):
    oo.set_maker(None)
    monkeypatch.delenv("OBJECT_TRACER_FUNCTION", raising=False)
    monkeypatch.setenv("WHITEBOARD_PROTO_DIR", "/nonexistent")            # the engine's functions: no scripts folder, no scipy
    assert oo.default_maker() is None
    assert oo.fill(_board_plan("violin"), video_id="v1", ctx=od.context("v1"))["reason"] == "no_tracer" and spent(wb.store, "object") == 0
    assert "names" not in wb.models.calls                                 # not even the policy's model call
    monkeypatch.setenv("OBJECT_TRACER_FUNCTION", NAME)
    assert oo.default_maker() is not None                                 # the function's name is enough to try it
    monkeypatch.setenv("CLIPS_ON_DEMAND", "0")                            # and with the flag off nothing is ever called
    oo.set_invoker(lambda *a: (_ for _ in ()).throw(AssertionError("must not be called")))
    try:
        assert oo.fill(_board_plan("violin"), video_id="v1", ctx=od.context("v1")) == {"asked": [], "made": [], "reason": ""}
    finally:
        oo.set_invoker(None)


def test_the_object_switch_off_means_the_function_is_never_called(wb, monkeypatch):
    from common import clip_config as cc
    oo.set_maker(None)
    monkeypatch.setenv("OBJECT_TRACER_FUNCTION", NAME)
    oo.set_invoker(lambda *a: (_ for _ in ()).throw(AssertionError("must not be called")))
    try:
        cc.set_config({**ON, "object_enabled": False})
        assert oo.fill(_board_plan("violin"), video_id="v1", ctx=od.context("v1"))["reason"] == "kill_switch"
        cc.set_config({**ON, "object_enabled": True, "master_enabled": False})
        assert oo.fill(_board_plan("violin"), video_id="v1", ctx=od.context("v1"))["reason"] == "kill_switch"
        wb.rows["v1"]["plan"] = "free"
        cc.set_config({**ON, "object_enabled": True})
        assert oo.fill(_board_plan("violin"), video_id="v1", ctx=od.context("v1"))["reason"] == "not_entitled"
    finally:
        oo.set_invoker(None)


# ================================================================= the function's handler
@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    import object_tracer
    return object_tracer.bundle(str(tmp_path_factory.mktemp("bundle") / "wb_tracer"))


@pytest.fixture
def handler(bundle):
    spec = importlib.util.spec_from_file_location("wb_tracer_handler", os.path.join(bundle, "handler.py"))
    mod = importlib.util.module_from_spec(spec)
    path = list(sys.path)
    try:
        spec.loader.exec_module(mod)
    finally:
        sys.path[:] = path
    return mod


def test_the_handler_answers_with_packages_and_thumbnails(handler, monkeypatch):
    asked = []

    def make(objs, timeout):
        asked.append((objs, timeout))
        return [_pkg(o, n) for o, n in objs], {"sheet_usd": 0.0375, "rejected": {}, "thumbs": {o: b"\xff\xd8jpeg" for o, _ in objs}, "sheet_png": b"\x89PNG" * 1000, "total_s": 9.9}
    monkeypatch.setattr(handler.object_maker, "make", make)
    out = handler.lambda_handler({"action": "make", "objects": [["kite", "kite"], ["tea_pot", "tea pot"]], "timeout": 30})
    assert [p["id"] for p in out["packages"]] == ["kite", "tea_pot"] and base64.b64decode(out["thumbs"]["kite"]) == b"\xff\xd8jpeg"
    assert "sheet_png" not in out["stats"] and "thumbs" not in out["stats"] and out["stats"]["sheet_usd"] == 0.0375 and asked == [([("kite", "kite"), ("tea_pot", "tea pot")], 30.0)]
    json.dumps(out)                                                                                           # the whole answer is plain JSON
    assert handler.lambda_handler({"action": "make", "objects": [["kite", "kite"]], "timeout": 900})["packages"] and asked[-1][1] == 45.0   # the function bounds its own wait


def test_the_handler_refuses_what_the_plan_step_would_never_send(handler, monkeypatch):
    monkeypatch.setattr(handler.object_maker, "make", lambda *a: (_ for _ in ()).throw(AssertionError("must not run")))
    no = {"refused": "bad request", "billed": False}
    for bad in ({}, {"action": "other"}, {"action": "make"}, {"action": "make", "objects": []}, {"action": "make", "objects": [["kite", "kite"]] * 7},
                {"action": "make", "objects": [["kite", "Kite!"]]}, {"action": "make", "objects": [["../x", "kite"]]}, {"action": "make", "objects": [["kite"]]},
                {"action": "make", "objects": [["kite", "kite"], ["kite", "kite"]]}, {"action": "make", "objects": [["kite", "a very long name of five words"]]}, "text", None):
        assert handler.lambda_handler(bad) == no, bad
    assert handler.lambda_handler({"action": "make", "objects": [["kite", "kite"], ["pistol", "pistol"]]}) == {"refused": "policy:war_weapons", "billed": False}   # the policy, whoever calls
    assert handler.lambda_handler({"action": "ping"})["ok"] is True


def test_the_handler_turns_every_failure_into_an_answer(handler, monkeypatch):
    monkeypatch.setattr(handler.object_maker, "make", lambda *a: (_ for _ in ()).throw(object_maker.Refused("moderation:violence", billed=False)))
    assert handler.lambda_handler({"action": "make", "objects": [["kite", "kite"]]}) == {"refused": "moderation:violence", "billed": False}
    monkeypatch.setattr(handler.object_maker, "make", lambda *a: (_ for _ in ()).throw(MemoryError()))
    assert handler.lambda_handler({"action": "make", "objects": [["kite", "kite"]]}) == {"refused": "tracer error (MemoryError)", "billed": True}
    monkeypatch.setattr(handler.object_maker, "make", lambda objs, t: ([{"id": "kite", "ink": "x" * 6_000_000}], {}))
    assert handler.lambda_handler({"action": "make", "objects": [["kite", "kite"]]}) == {"refused": "answer too large", "billed": True}


def test_the_bundle_holds_everything_the_function_imports(bundle):
    """The code folder alone, in a fresh interpreter (only the libraries of the layer beside it): the handler, the maker, the builder's tracing code, the model client."""
    pytest.importorskip("scipy")
    pytest.importorskip("vtracer")
    files = sorted(os.path.relpath(os.path.join(r, f), bundle) for r, _d, fs in os.walk(bundle) for f in fs if "__pycache__" not in r)
    assert "handler.py" in files and "lambdas/common/object_maker.py" in files and "scripts/whiteboard_proto/lib_build.py" in files and len(files) == 14
    assert sum(os.path.getsize(os.path.join(bundle, f)) for f in files) < 2_000_000 and not any("clip_store" in f or "secrets" in f for f in files)   # small, and nothing of accounts or budgets
    code = ("import json, handler; from common import object_maker; mods = object_maker.load(); import engine.llm; "
            "print(json.dumps({'ping': handler.lambda_handler({'action': 'ping'}), 'proto': mods[1].__file__, 'llm': engine.llm.__file__, 'font': __import__('os').path.isfile(mods[1].UI_FONT)}))")
    env_ = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH", "WHITEBOARD_PROTO_DIR")}
    env_["WB_OUT"] = os.path.join(bundle, "..", "wb_work")
    p = subprocess.run([sys.executable, "-c", code], cwd=bundle, env=env_, capture_output=True, text=True, timeout=120)
    assert p.returncode == 0, p.stderr[-800:]
    out = json.loads(p.stdout.strip().splitlines()[-1])
    assert out["ping"] == {"ok": True, "tracer": True} and out["font"] is True
    assert os.path.realpath(out["proto"]).startswith(os.path.realpath(bundle)) and os.path.realpath(out["llm"]).startswith(os.path.realpath(bundle))   # its own copies, not the repository's


# ================================================================= the real tracing pipeline, on a sheet drawn here
def _sheet_png():
    from PIL import Image, ImageDraw

    im = Image.new("RGB", (2048, 1152), "white")
    d = ImageDraw.Draw(im)
    cw, ch = 2048 // 3, 1152 // 2
    for k in range(6):
        cx, cy = (k % 3) * cw + cw // 2, (k // 3) * ch + ch // 2
        if k % 3 == 0:
            d.ellipse([cx - 150, cy - 150, cx + 150, cy + 150], outline="black", width=16)
        elif k % 3 == 1:
            d.rounded_rectangle([cx - 170, cy - 120, cx + 170, cy + 120], radius=30, outline="black", width=16)
        else:
            d.line([(cx - 160, cy + 130), (cx, cy - 150), (cx + 160, cy + 130), (cx - 160, cy + 130)], fill="black", width=16, joint="curve")
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def test_the_real_maker_cuts_traces_and_gates_a_sheet(monkeypatch):
    pytest.importorskip("scipy")
    pytest.importorskip("vtracer")
    pytest.importorskip("resvg_py")
    png = _sheet_png()

    class R:
        def read(self, n=-1): return json.dumps({"data": [{"b64_json": base64.b64encode(png).decode()}], "usage": {"input_tokens": 200, "output_tokens": 1212}}).encode()
        def __enter__(self): return self
        def __exit__(self, *a): return False
    sent, gate = [], {"box": False}

    def opener(req, timeout=0):
        sent.append(json.loads(req.data))
        return R()

    def complete(system, user, **kw):
        ok = not ("Requested drawing: box." in user and gate["box"] is False)
        return json.dumps({"is_subject": ok, "clean": True, "complete": True, "no_text": True, "score": 8, "problem": "" if ok else "not a box", "title_en": "Thing", "title_es": "Cosa",
                           "synonyms_en": ["a"], "synonyms_es": ["b"], "tags": ["shape"], "description": "A shape.", "fills": {"1": "yellow"}, "order": []}), {"cost_usd": 0.006}
    monkeypatch.setattr(llm, "complete", complete)
    pkgs, stats = object_maker.make([("ring", "ring"), ("box", "box"), ("tent", "tent")], 20, key="k", opener=opener, moderate=lambda **kw: None)
    assert [p["id"] for p in pkgs] == ["ring", "tent"] and stats["rejected"] == {"box": "gate: not a box"}                 # the builder's own gate decides
    assert "(1) ring; (2) box; (3) tent; (4) a small plain circle" in sent[0]["prompt"] and sent[0]["size"] == "2048x1152" and sent[0]["moderation"] == "auto"
    for p in pkgs:
        assert 11 <= p["width"] <= 24 and p["strokes"] and p["ink"].startswith("<g") and p["fill_colours"] == ["yellow"] and p["meta"]["title_es"] == "Cosa"
        assert stats["thumbs"][p["id"]][:2] == b"\xff\xd8"                                                                # a JPEG of the finished drawing for the policy's vision check
    assert stats["sheet_usd"] == pytest.approx(0.0374, abs=0.0005) and stats["total_s"] < 20 and len(json.dumps(pkgs)) < 1_000_000


# ================================================================= the stack
@pytest.fixture(scope="module")
def template(tmp_path_factory):
    import aws_cdk as cdk
    from aws_cdk.assertions import Template
    import object_tracer

    os.environ.setdefault("CDK_SKIP_LAYER_CHECK", "1")
    out = tmp_path_factory.mktemp("cdk")
    app = cdk.App(outdir=str(out / "out"))
    stack = object_tracer.ObjectTracerStack(app, NAME, stage="qa", bundle_dir=str(out / "bundle"), env=cdk.Environment(account="123456789012", region="eu-west-1"))
    return Template.from_stack(stack).to_json()


def test_the_tracer_stack_is_one_small_function_with_two_rights(template):
    res = template["Resources"]
    types = sorted(v["Type"] for v in res.values())
    assert types == ["AWS::IAM::Policy", "AWS::IAM::Role", "AWS::Lambda::Function", "AWS::Lambda::LayerVersion", "AWS::Logs::LogGroup"]          # five resources, none in the main stack
    (fn,) = [v["Properties"] for v in res.values() if v["Type"] == "AWS::Lambda::Function"]
    assert fn["FunctionName"] == NAME and fn["Handler"] == "handler.lambda_handler" and fn["Runtime"] == "python3.12" and fn["Timeout"] == 60 and fn["MemorySize"] == 3008
    assert fn["Architectures"] == ["x86_64"] and len(fn["Layers"]) == 1 and fn["Environment"]["Variables"] == {"OPENAI_SSM_PARAM": "/videomk/openai_api_key", "WB_OUT": "/tmp/wb"}
    (policy,) = [v["Properties"]["PolicyDocument"]["Statement"] for v in res.values() if v["Type"] == "AWS::IAM::Policy"]
    assert sorted(s["Action"] for s in policy) == ["bedrock:InvokeModel", "ssm:GetParameter"]                                                  # the gate's model and the provider's key: nothing else
    assert "parameter/videomk/openai_api_key" in json.dumps(policy) and "dynamodb" not in json.dumps(template) and "s3:" not in json.dumps(policy)
    (logs,) = [v["Properties"] for v in res.values() if v["Type"] == "AWS::Logs::LogGroup"]
    assert logs["LogGroupName"] == f"/aws/lambda/{NAME}" and logs["RetentionInDays"] == 30
    assert "Fn::ImportValue" not in json.dumps(template) and not template.get("Outputs")                                                       # no tie to the main stack
