"""The pre-rendered 3D background loops wired into the engine (docs/HERO_LOOPS_3D.md, flag BG_LOOPS): the director's choice (only loops that fit the theme, the
static look for data-heavy and photo videos), the plan and timeline fields, the renderer and canvas (continuous across scene changes, chunk boundaries and the loop
point; a missing file never fails a render), theme edits, the stack's flag and IAM, and nothing at all with the flag off."""
import copy
import json
import os
import shutil
import subprocess
import sys

import numpy as np
import pytest

from engine import awsio, background as bgsel, bg_animated as B, bg_loops as L, canvas as canvas_mod, director, edits, media, renderer as renderer_mod
from engine.renderer import Renderer
from engine.timeline import chunk_plan, chunk_timeline
from tests.test_background import _big, _small, _tl2
from tests.test_create_options import _plan, _run_timeline

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
INDEX = json.load(open(os.path.join(ROOT, "scripts", "hero_loops_index.json")))   # the real index: the four loops in the bucket
LOOPS = L.clean_index(INDEX)
FRAMES, FPS, SW, SH = 300, 30, 320, 180


@pytest.fixture(scope="module")
def loop_file(tmp_path_factory):
    """A 10 s seamless synthetic loop: a soft bright band that travels once across the picture and a brightness that swells and returns."""
    d = tmp_path_factory.mktemp("loop10")
    raw, out = d / "in.raw", d / "loop.mp4"
    xs = np.arange(SW, dtype=np.float32)[None, :]
    with open(raw, "wb") as f:
        for i in range(FRAMES):
            th = 2 * np.pi * i / FRAMES
            band = 60 * np.exp(-(((xs - SW * (0.5 + 0.35 * np.sin(th))) / 40.0) ** 2))
            a = np.clip(40 + 20 * np.cos(th) + band, 0, 255).astype(np.uint8)
            f.write(np.repeat(np.repeat(a, SH, axis=0)[..., None], 3, axis=2).tobytes())
    subprocess.run([media.ffmpeg_bin(), "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{SW}x{SH}", "-r", str(FPS), "-i", str(raw),
                    "-c:v", "libx264", "-crf", "12", "-g", "30", "-pix_fmt", "yuv420p", "-an", str(out)], check=True)
    return str(out)


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    for k in ("BG_LOOPS", "BG_ANIMATED"):
        monkeypatch.delenv(k, raising=False)
    L.release()
    L.reset_index_cache()
    canvas_mod._LOOP_FAILED.clear()
    yield
    L.release()
    L.reset_index_cache()
    canvas_mod._LOOP_FAILED.clear()


@pytest.fixture
def bucket(monkeypatch, loop_file, tmp_path):
    """The assets bucket as the engine sees it: the index and every loop's 1080.mp4 (the synthetic file). Counts what was read."""
    seen = {"json": [], "files": []}

    def get_json(key):
        seen["json"].append(key)
        if key != L.INDEX_KEY:
            raise KeyError(key)
        return copy.deepcopy(INDEX)

    def download(key, path):
        seen["files"].append(key)
        shutil.copyfile(loop_file, path)
    monkeypatch.setattr(awsio, "get_json", get_json)
    monkeypatch.setattr(awsio, "download", download)
    monkeypatch.setattr(L, "CACHE_DIR", str(tmp_path / "cache"))
    return seen


def _direct(answer, theme="midnight", mood="calm", scene=None):
    def big(system, user):
        d = json.loads(_big(system, user))
        d.update(theme=theme, mood=mood)
        if scene:
            for b, sc in zip(d["beats"], scene):
                b["scene"] = sc
        return json.dumps(d)
    return director.direct("how tides work", minutes=1.0, ask_small=_small(answer), ask_big=big, language="en")


# ------------------------------------------------------------------ the choice
def test_flag_off_no_loop_is_offered_or_read_even_when_the_model_names_one(monkeypatch, bucket):
    monkeypatch.setenv("BG_ANIMATED", "1")
    out = _direct('{"style": "gas", "palette": "ocean", "loop": "gas-brand-dark"}')
    bg = out["plan"]["background"]
    assert "loop" not in bg and "loop_palette" not in bg and bg["loop_seconds"] == bgsel.LOOP_SECONDS and bucket["json"] == []
    assert out["research"]["background"] == {"style": "gas", "palette": "ocean", "by": "director"}


def test_flag_on_the_director_picks_a_loop_and_the_plan_keeps_the_procedural_style_behind_it(monkeypatch, bucket):
    monkeypatch.setenv("BG_LOOPS", "1")
    out = _direct('{"style": "gas", "palette": "ocean", "loop": "gas-aurora-dark"}')
    bg = out["plan"]["background"]
    assert (bg["loop"], bg["loop_palette"], bg["loop_seconds"], bg["mode"], bg["by"]) == ("gas-aurora-dark", "aurora", 10.0, "dark", "director")
    assert (bg["style"], bg["palette"]) == ("gas", "ocean") and B.sanitize(bg, "midnight").loop_seconds == 10.0   # what plays if the loop cannot be used
    assert out["research"]["background"] == {"style": "gas", "palette": "ocean", "by": "director", "loop": "gas-aurora-dark"}
    assert bucket["json"] == [L.INDEX_KEY] and bucket["files"] == []   # the planner reads the index only, never a loop file


def test_the_menu_lists_only_the_loops_that_fit_the_theme():
    seen = []
    for theme, ids in (("midnight", ["gas-brand-dark", "gas-aurora-dark"]), ("sunrise", ["gas-ember-dark"]), ("paper", ["gas-brand-light"])):
        assert [lp.id for lp in bgsel.loops_for(theme, LOOPS)] == ids
        bgsel.choose("tides", {"title": "T", "mood": "calm", "theme": theme}, lambda s, u: seen.append(s) or "{}", loops=LOOPS)
        menu = seen[-1].split("Premium 3D loops")[1]
        assert all(i in menu for i in ids) and not any(lp.id in menu for lp in LOOPS if lp.id not in ids)
        assert seen[-1].count("Answer with ONLY this JSON") == 1 and '"loop"' in seen[-1].rsplit("\n", 1)[1]
    bgsel.choose("tides", {"title": "T", "theme": "midnight"}, lambda s, u: seen.append(s) or "{}")   # no loops: the plain menu, no loop in the answer format
    assert "Premium" not in seen[-1] and '"loop"' not in seen[-1]


@pytest.mark.parametrize("theme,wish", [("midnight", "gas-ember-dark"), ("midnight", "gas-brand-light"), ("paper", "gas-brand-dark"), ("sunrise", "gas-aurora-dark"),
                                        ("midnight", "none"), ("midnight", "../etc"), ("midnight", "gas-unknown-dark")])
def test_a_loop_that_does_not_fit_the_theme_or_does_not_exist_is_never_used(theme, wish):
    bg = bgsel.choose("x", {"title": "T", "mood": "calm", "theme": theme}, lambda s, u: json.dumps({"style": "gas", "loop": wish}), loops=LOOPS)
    assert "loop" not in bg and bg["by"] == "director" and bg["loop_seconds"] == bgsel.LOOP_SECONDS
    assert bg["mode"] == bgsel.mode_of(theme)


@pytest.mark.parametrize("theme,mood,loop", [("midnight", "calm", "gas-brand-dark"), ("sunrise", "tense", "gas-ember-dark"), ("paper", "bright", "gas-brand-light"),
                                             ("midnight", "bright", None), ("sunrise", "calm", None), ("paper", "tense", None)])
def test_without_a_usable_answer_the_mood_picks_a_loop_only_when_a_loop_carries_that_mood(theme, mood, loop):
    for ask in (None, lambda s, u: "no idea", lambda s, u: (_ for _ in ()).throw(RuntimeError("throttled"))):
        bg = bgsel.choose("x", {"title": "T", "mood": mood, "theme": theme}, ask, loops=LOOPS)
        assert bg.get("loop") == loop and bg["by"] == "mood" and bg["style"] in bgsel.STYLES


def test_a_loop_answer_alone_counts_as_the_directors_choice():
    bg = bgsel.choose("x", {"title": "T", "mood": "tense", "theme": "midnight"}, lambda s, u: '{"loop": "GAS-BRAND-DARK"}', loops=LOOPS)
    assert bg["loop"] == "gas-brand-dark" and bg["by"] == "director" and bg["style"] == "smoke"   # the procedural style behind it comes from the mood


def test_a_data_heavy_video_keeps_the_static_look(monkeypatch, bucket):
    monkeypatch.setenv("BG_LOOPS", "1")
    monkeypatch.setenv("BG_ANIMATED", "1")
    chart = {"type": "chart", "props": {"kind": "bar", "labels": ["Red", "Green", "Violet"], "values": [42, 41, 40], "unit": "°"}}
    title = {"type": "title", "props": {"title": "x"}}
    out = _direct('{"style": "gas", "loop": "gas-brand-dark"}', scene=[title, chart, chart, title])
    assert [b["scene"]["type"] for b in out["plan"]["beats"]].count("chart") == 2   # the scenes survived validation as charts
    assert "background" not in out["plan"] and "background" not in out["research"] and bucket["json"] == []
    out = _direct('{"style": "gas", "loop": "gas-brand-dark"}', scene=[title, chart, title, title])   # one chart in four: the background stays
    assert out["plan"]["background"]["loop"] == "gas-brand-dark"
    assert bgsel.data_heavy({"beats": []}) is False and bgsel.data_heavy({"beats": [{"scene": {"type": "table"}}, {"scene": {"type": "title"}}]}) is True


def test_a_video_of_the_persons_photos_gets_no_loop(monkeypatch, bucket):
    monkeypatch.setenv("BG_LOOPS", "1")

    def big(system, user):
        return json.dumps({"legit": True, "title": "T", "description": "d", "voices": {"narrator": "Ruth"}, "beats": [
            {"narration": " ".join(["w"] * 30), "scene": {"type": "image", "props": {"photo": "P1", "image_query": "a street", "alt": "a"}}} for _ in range(3)]})
    photos = [{"id": "P1", "key": "k", "w": 600, "h": 400, "orientation": "landscape", "caption": "a street"}]
    out = director.direct("my trip to Paris", minutes=1.0, ask_small=_small('{"loop": "gas-brand-dark"}'), ask_big=big, language="en", photos=photos)
    assert "background" not in out["plan"] and bucket["json"] == []


def test_an_unreadable_index_means_no_loops_never_a_failed_video(monkeypatch):
    monkeypatch.setenv("BG_LOOPS", "1")
    monkeypatch.setattr(awsio, "get_json", lambda k: (_ for _ in ()).throw(RuntimeError("AccessDenied")))
    bg = _direct('{"style": "aurora", "palette": "ocean", "loop": "gas-brand-dark"}')["plan"]["background"]
    assert "loop" not in bg and bg["style"] == "aurora"


# ------------------------------------------------------------------ timeline, hashes, edits
def _loop_bg(loop="gas-brand-dark", theme="midnight", mood="calm"):
    return bgsel.choose("x", {"title": "t", "mood": mood, "theme": theme}, lambda s, u: json.dumps({"style": "gas", "loop": loop}), loops=LOOPS)


def test_the_timeline_places_every_scene_in_the_10_s_loop_and_the_hashes_follow_the_loop_id(monkeypatch):
    plan = _plan()
    plan["background"] = _loop_bg()
    tl, _ = _run_timeline(monkeypatch, plan)
    assert tl["background"]["loop"] == "gas-brand-dark" and [s["bg_t0"] for s in tl["scenes"]] == [round(s["start"] % 10.0, 3) for s in tl["scenes"]]
    a = chunk_plan(tl, 4)
    other = copy.deepcopy(tl)
    other["background"] = dict(tl["background"], loop="gas-aurora-dark", loop_palette="aurora")
    none = copy.deepcopy(tl)
    none["background"] = {k: v for k, v in tl["background"].items() if k not in ("loop", "loop_palette")}
    for b in (chunk_plan(other, 4), chunk_plan(none, 4)):
        assert len(a) == len(b) and all(x["hash"] != y["hash"] for x, y in zip(a, b))
    assert chunk_timeline(tl, a[-1]["lo"], a[-1]["hi"])["background"] == tl["background"]


def test_a_theme_edit_keeps_a_loop_only_while_it_fits():
    plan = _plan()
    plan["theme"], plan["mood"] = "midnight", "calm"
    plan["background"] = _loop_bg("gas-brand-dark")
    paper = edits.apply_ops(plan, [{"op": "set_meta", "theme": "paper"}])[0]["background"]
    assert "loop" not in paper and "loop_palette" not in paper and paper["mode"] == "light" and paper["loop_seconds"] == bgsel.LOOP_SECONDS and paper["seed"] == plan["background"]["seed"]
    sunrise = edits.apply_ops(plan, [{"op": "set_meta", "theme": "sunrise"}])[0]["background"]   # still dark, but the blue gas does not suit the warm theme
    assert "loop" not in sunrise and sunrise["mode"] == "dark"
    same = edits.apply_ops(plan, [{"op": "set_meta", "theme": "midnight"}])[0]["background"]
    assert same["loop"] == "gas-brand-dark" and same["loop_seconds"] == 10.0


# ------------------------------------------------------------------ renderer and canvas
def _tl(loop="gas-brand-dark", theme="midnight", durations=(5.0, 7.0)):
    bg = _loop_bg(loop, theme)
    tl = _tl2()
    tl["theme"] = theme
    t = 0.0
    for s, d in zip(tl["scenes"], durations):
        s.update(start=t, duration=d, bg_t0=bgsel.phase(t, bg))
        t += d
    tl.update(background=bg, duration=t)
    return tl


def test_the_renderer_uses_the_loop_only_with_the_flag_and_only_when_it_fits_the_theme(monkeypatch, bucket):
    tl = _tl()
    assert Renderer(tl, draft=True).bg_anim is None and bucket["json"] == []          # both flags off: nothing, and nothing is read
    monkeypatch.setenv("BG_ANIMATED", "1")
    assert isinstance(Renderer(tl, draft=True).bg_anim, B.BgSpec) and bucket["json"] == []   # loops off: the procedural style of the same plan
    monkeypatch.setenv("BG_LOOPS", "1")
    spec = Renderer(tl, draft=True).bg_anim
    assert isinstance(spec, L.LoopSpec) and spec.id == "gas-brand-dark" and spec.frames == 300
    assert isinstance(Renderer(dict(tl, theme="paper"), draft=True).bg_anim, B.BgSpec)     # a dark loop never plays under the light theme
    assert isinstance(Renderer(dict(tl, background=dict(tl["background"], loop="gas-nope-dark")), draft=True).bg_anim, B.BgSpec)
    monkeypatch.delenv("BG_ANIMATED")
    assert Renderer(dict(tl, theme="paper"), draft=True).bg_anim is None                # no fit and no procedural flag: the static look
    assert isinstance(Renderer(tl, draft=True).bg_anim, L.LoopSpec)                     # BG_LOOPS alone is enough for a loop


def _diff(a, b):
    return float(np.abs(np.asarray(a, np.int16) - np.asarray(b, np.int16)).mean())


def test_the_loop_flows_across_a_scene_change_a_chunk_boundary_and_the_loop_point(monkeypatch, bucket):
    monkeypatch.setenv("BG_LOOPS", "1")
    tl = _tl()   # scenes [0, 5) and [5, 12): the second one runs through the loop point at 10 s
    r = Renderer(tl, draft=True)
    f = 1 / 30
    step = max(_diff(r.frame_at(2.0), r.frame_at(2.0 + f)), _diff(r.frame_at(7.0), r.frame_at(7.0 + f)))
    assert step > 0.05                                                                   # the picture really moves
    assert _diff(r.frame_at(5.0 - f), r.frame_at(5.0)) <= step * 2 + 0.5                 # the scene change: one frame's drift
    assert _diff(r.frame_at(10.0 - f), r.frame_at(10.0)) <= step * 2 + 0.5               # the loop point
    assert _diff(r.frame_at(1.0), r.frame_at(11.0)) < 0.5 < _diff(r.frame_at(1.0), r.frame_at(6.0))   # 10 s later the same picture, half a loop later another
    r2 = Renderer(chunk_timeline(tl, 1, 2), draft=True)                                  # the second scene on its own, as a render function draws it
    assert _diff(r2.frame_at(0.0), r.frame_at(5.0)) < 0.5 and _diff(r2.frame_at(5.5), r.frame_at(10.5)) < 0.5
    assert bucket["files"] == ["backgrounds/loops/gas-brand-dark/1080.mp4"]              # downloaded once for both renderers


@pytest.mark.parametrize("w,h", [(1080, 1920), (1080, 1080), (1080, 1350)])
def test_other_aspects_take_the_centre_of_the_loop(monkeypatch, bucket, w, h):
    monkeypatch.setenv("BG_LOOPS", "1")
    tl = _tl()
    tl.update(width=w, height=h)
    r = Renderer(tl, draft=True)
    img = r.frame_at(2.5)   # a quarter of the loop: the bright band is right of the centre of the source, outside or at the edge of a centre crop
    assert img.size == (r.out_w, r.out_h) and isinstance(r.bg_anim, L.LoopSpec)
    assert _diff(img, Renderer({k: v for k, v in tl.items() if k != "background"}, draft=True).frame_at(2.5)) > 1.0   # not the static glow


def test_a_missing_loop_file_draws_the_static_look_and_is_tried_once(monkeypatch, bucket):
    monkeypatch.setenv("BG_LOOPS", "1")
    calls = []
    monkeypatch.setattr(awsio, "download", lambda key, path: calls.append(key) or (_ for _ in ()).throw(RuntimeError("NoSuchKey")))
    tl = _tl()
    r = Renderer(tl, draft=True)
    a, b = r.frame_at(1.0), r.frame_at(1.5)
    static = Renderer({k: v for k, v in tl.items() if k != "background"}, draft=True)
    assert len(calls) == 1 and "gas-brand-dark" in canvas_mod._LOOP_FAILED
    assert a.size == static.frame_at(1.0).size and _diff(a, b) < 3.0 and np.asarray(a).std() > 1.0   # a whole picture (the theme's glow, on the video's clock), not a blank or an error


def test_release_caches_frees_the_loops_frames(monkeypatch, bucket):
    monkeypatch.setenv("BG_LOOPS", "1")
    Renderer(_tl(), draft=True).frame_at(1.0)
    assert sum(p.cached_bytes() for p in L._players.values()) > 0
    renderer_mod.release_caches()
    assert not L._players


def test_with_both_flags_off_a_timeline_that_carries_a_loop_renders_as_before(bucket):
    tl = _tl()
    plain = {k: v for k, v in tl.items() if k != "background"}
    # the scenes keep bg_t0: without a background spec it is ignored
    a = np.asarray(Renderer(tl, draft=True).frame_at(1.0))
    assert np.array_equal(a, np.asarray(Renderer(plain, draft=True).frame_at(1.0))) and bucket["json"] == [] and bucket["files"] == []


# ------------------------------------------------------------------ the stack: flag and IAM
@pytest.fixture(scope="module")
def synth():
    import aws_cdk as cdk
    from aws_cdk.assertions import Template

    sys.path.insert(0, ROOT)
    cwd = os.getcwd()
    os.chdir(ROOT)
    try:
        from backend_stack import BackendStack

        def build(n, stage_extra=None, **ctx):
            app = cdk.App(context={"stage": "qa", "engine": "v2", **ctx}, outdir=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"vmk-bgloops-{n}"))
            os.environ.setdefault("CDK_SKIP_LAYER_CHECK", "1")
            cfg = {"account": "123456789012", "region": "eu-west-1", "domain": None, "callbackUrls": ["https://qa.videomk.com/auth/callback"], "logoutUrls": ["https://qa.videomk.com/"], **(stage_extra or {})}
            return Template.from_stack(BackendStack(app, "videomk-qa", stage="qa", stage_cfg=cfg, env=cdk.Environment(account="123456789012", region="eu-west-1"))).to_json()
        yield build
    finally:
        os.chdir(cwd)


def _fn_env(t, name):
    return next(v["Properties"]["Environment"]["Variables"] for k, v in t["Resources"].items() if v["Type"] == "AWS::Lambda::Function" and k.startswith(name))


def _loop_grants(t):
    """{role logical id prefix: [resource strings]} of every statement that names backgrounds/loops."""
    out = {}
    for k, v in t["Resources"].items():
        if v["Type"] != "AWS::IAM::Policy":
            continue
        for st in v["Properties"]["PolicyDocument"]["Statement"]:
            res = json.dumps(st.get("Resource"))
            if "backgrounds/loops" in res:
                assert st["Effect"] == "Allow" and st["Action"] == "s3:GetObject"   # read only: no list, no write
                out[k] = res
    return out


def test_the_stack_sets_the_flag_only_where_asked_and_grants_read_only_access_to_the_loops(synth):
    off, on, ctx = synth(0), synth(1, {"bgLoops": True}), synth(2, bgLoops="1")
    for fn in ("V2PlanFn", "V2RenderChunkFn"):
        assert "BG_LOOPS" not in _fn_env(off, fn) and _fn_env(on, fn)["BG_LOOPS"] == "1" and _fn_env(ctx, fn)["BG_LOOPS"] == "1"
        assert "BG_ANIMATED" not in _fn_env(on, fn)   # the two switches are independent
    grants = _loop_grants(on)
    assert _loop_grants(off).keys() == grants.keys() and len(grants) == 3   # the grant itself is harmless and always there: flipping the flag never needs new rights
    by = {next(n for n in ("V2PlanFn", "V2RenderChunkFn", "V2SelfTestFn") if n in k): v for k, v in grants.items()}
    assert by["V2PlanFn"].count("backgrounds/loops/index.json") == 1 and "loops/*" not in by["V2PlanFn"]
    assert "backgrounds/loops/*" in by["V2RenderChunkFn"] and "backgrounds/loops/*" in by["V2SelfTestFn"]


def test_stages_json_turns_the_loops_on_in_qa_and_prod():
    stages = json.load(open(os.path.join(ROOT, "stages.json")))   # prod since 2026-11-27: the owner watched the four loops and approved them
    assert stages["qa"].get("bgLoops") is True and stages["prod"].get("bgLoops") is True and stages["prod"].get("bgAnimated") is True
