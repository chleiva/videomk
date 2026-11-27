"""The looks reachable on a stage: the cartoon scene element reads a catalog scene (fetched once, full bleed in every shape, never stretched, a card when it cannot
be had), the policy's scene shapes and held-back scenes, what capabilities says (`looks`), and the stack's switch, rights and environment (docs/VECTOR_SCENE_POLICY.md,
docs/CREATE_API.md "Looks")."""
import json
import os
import sys

import numpy as np
import pytest

import capabilities_api
from engine import format_options as fo, vector_policy, vector_scene as vs
from engine.renderer import Renderer
from engine.scenes import ELEMENTS
from engine.scenes.elements import vector_scene as el
from engine.scenes.formats import is_native
from engine.frame import Frame

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SVG = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}">{body}</svg>'


def _package(root, cid, aspect=(16, 9)):
    """A tiny scene: a blue sky, a red disc exactly in the middle and a green bar down the left edge (so a crop and a stretch can be told apart)."""
    w, h = (1600, 900) if aspect == (16, 9) else (900, 1600)
    d = root / cid
    d.mkdir(parents=True)
    (d / "0_sky.svg").write_text(SVG.format(w=w, h=h, body=f'<rect width="{w}" height="{h}" fill="#3070ff"/><rect width="{w // 10}" height="{h}" fill="#00c000"/>'))
    (d / "1_disc.svg").write_text(SVG.format(w=w, h=h, body=f'<circle cx="{w // 2}" cy="{h // 2}" r="{min(w, h) // 5}" fill="#ff2020"/>'))
    (d / "manifest.json").write_text(json.dumps({"name": cid, "aspect": list(aspect), "layers": [{"file": "0_sky.svg", "z": 0.0}, {"file": "1_disc.svg", "z": 0.5}], "motion": {"push": 0.0, "pan": 0.0}}))
    return d


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    pytest.importorskip("resvg_py")
    src = tmp_path / "catalog"
    _package(src, "wide_scene")
    _package(src, "tall_scene", (9, 16))
    monkeypatch.setenv("VECTOR_CATALOG_DIR", str(src))
    monkeypatch.setattr(el, "CACHE_DIR", str(tmp_path / "cache"))
    el._FOLDERS.clear()
    vs.load_folder.cache_clear()
    yield src
    el._FOLDERS.clear()
    vs.load_folder.cache_clear()


def _tl(cid, aspect="16:9", res="1080p"):
    f = fo.frame_dict(aspect, res, platform="shorts")
    return {"scenes": [{"id": "a", "type": "vector_scene", "start": 0.0, "duration": 6.0, "props": {"catalog_id": cid, "motion": "default", "alt": "A quiet valley"}, "words": [], "transition": "none"}],
            "theme": "midnight", "captions": False, "duration": 6.0, "width": f["width"], "height": f["height"], "fps": 30, "outro": False, "frame": f}


def _disc(img):
    """(centre x, centre y, width, height) of the red disc, as shares of the picture."""
    a = np.asarray(img.convert("RGB")).astype(int)
    red = (a[..., 0] > 180) & (a[..., 1] < 90) & (a[..., 2] < 90)
    ys, xs = np.nonzero(red)
    return xs.mean() / a.shape[1], ys.mean() / a.shape[0], (xs.max() - xs.min()) / a.shape[1], (ys.max() - ys.min()) / a.shape[0]


# ---------------------------------------------------------------- the element
def test_the_element_takes_a_catalog_id_and_keeps_only_what_the_policy_writes():
    s = ELEMENTS["vector_scene"].sanitize
    assert s({"catalog_id": " Pine_Forest_Valley ", "seconds": 7, "motion": "wild", "alt": "  A  pine\nvalley ", "junk": 1}) == {"catalog_id": "pine_forest_valley", "motion": "default", "seconds": 7.0, "alt": "A pine valley"}
    assert s({"catalog_id": "pine_forest_valley", "seconds": 99}) == {"catalog_id": "pine_forest_valley", "motion": "default"}
    assert s({"scene": "seaside"}) == {"scene": "seaside"}                                 # the bundled prototype scenes still work
    for bad in ({"catalog_id": "../etc/passwd"}, {"catalog_id": "a b"}, {"catalog_id": "x"}, {"scene": "nope"}, {}):
        with pytest.raises(ValueError):
            s(bad)
    assert ELEMENTS["vector_scene"].max_per_video is None and ELEMENTS["vector_scene"].hidden   # how many per video is the policy's decision; never in the ordinary scene list
    assert all(is_native("vector_scene", Frame.parse(a, "1080p")) for a in ("16:9", "9:16", "1:1", "4:5"))   # full bleed in every shape, never the framed card


def test_a_catalog_scene_is_fetched_once_and_drawn_full_bleed(catalog):
    r = Renderer(_tl("wide_scene"), draft=True)
    a, b = r.frame_at(1.0), r.frame_at(3.0)
    cx, cy, w, h = _disc(a)
    assert abs(cx - 0.5) < 0.02 and abs(cy - 0.5) < 0.02 and abs(w * 16 - h * 9) < 0.3     # the disc is round (w x 16 = h x 9 in a 16:9 picture) and in the middle
    assert np.asarray(a.convert("RGB"))[10, 10].tolist()[1] > 150                          # the green bar at the left edge: the whole scene is there
    assert os.path.isfile(os.path.join(el.CACHE_DIR, "wide_scene", "manifest.json")) and el._FOLDERS == {"wide_scene": os.path.join(el.CACHE_DIR, "wide_scene")}
    assert b.size == a.size


@pytest.mark.parametrize("cid,aspect,edge_visible", [("wide_scene", "1:1", False), ("wide_scene", "9:16", False), ("tall_scene", "9:16", True), ("tall_scene", "4:5", True), ("tall_scene", "16:9", True)])
def test_another_shape_shows_the_centre_of_the_scene_and_never_stretches_it(catalog, cid, aspect, edge_visible):
    img = Renderer(_tl(cid, aspect), draft=True).frame_at(1.0)
    cx, cy, w, h = _disc(img)
    assert abs(cx - 0.5) < 0.03 and abs(cy - 0.5) < 0.03
    assert abs(w * img.width - h * img.height) <= 0.03 * max(w * img.width, h * img.height)   # still a circle in pixels
    left = np.asarray(img.convert("RGB"))[img.height // 2, 4].tolist()
    assert (left[1] > 150 and left[0] < 100) == edge_visible                                  # a wide scene in a narrower frame loses its sides; a tall scene keeps its width


def test_the_size_a_scene_is_rendered_at_covers_the_frame_and_is_capped_for_4k():
    assert vs.cover_size((16, 9), 1920, 1080) == (1920, 1080, 1.0)
    assert vs.cover_size((16, 9), 1080, 1080) == (1920, 1080, 1.0)
    assert vs.cover_size((9, 16), 1080, 1350)[:2] == (1080, 1920)
    w, h, up = vs.cover_size((16, 9), 3840, 2160)
    assert (w, h) == (2560, 1440) and up == pytest.approx(1.5)                                 # 4K: animated at 1440p and enlarged, about a third of the pixels to move per frame
    assert vs.cover_size((16, 9), 2160, 3840)[2] > 1.0 and max(vs.cover_size((16, 9), 2160, 3840)[:2]) <= vs.MAX_RASTER_SIDE + 1


def test_a_4k_frame_is_the_right_size(catalog):
    img = Renderer(_tl("wide_scene", "16:9", "2160p")).frame_at(1.0)
    assert img.size == (3840, 2160) and abs(_disc(img)[0] - 0.5) < 0.02


def test_a_scene_that_cannot_be_had_is_a_card_with_its_line_and_is_tried_once(catalog, capsys):
    r = Renderer(_tl("missing_scene"), draft=True)
    a, b = r.frame_at(1.0), r.frame_at(2.0)
    assert a.size == b.size and np.asarray(a).std() > 1.0 and el._FOLDERS == {"missing_scene": None}
    assert capsys.readouterr().out.count("VECTOR_SCENE_FETCH_FAILED missing_scene") == 1
    plain = _tl("missing_scene")
    plain["scenes"][0]["props"].pop("alt")
    assert np.abs(np.asarray(Renderer(plain, draft=True).frame_at(1.0), int) - np.asarray(a, int)).mean() > 0.05   # the caption line is what differs


# ---------------------------------------------------------------- the policy's search
def test_square_videos_take_landscape_scenes_and_4_5_takes_tall_ones_and_turbines_are_held_back(monkeypatch):
    from common import vector_catalog as vc
    seen = []

    def search(query, aspect="16:9", k=5, **kw):
        seen.append((aspect, k))
        return [{"id": "offshore_wind_farm", "motion": ["bob", "rotate"]}, {"id": "a", "motion": ["drift"]}, {"id": "b", "motion": []}, {"id": "c"}, {"id": "d", "motion": ["wiggle"]}][:k]
    monkeypatch.setattr(vc, "search", search)
    for aspect, shape in (("16:9", "16:9"), ("9:16", "9:16"), ("1:1", "16:9"), ("4:5", "9:16"), ("weird", "16:9")):
        got = vector_policy._default_search("wind", aspect, 3)
        assert seen[-1] == (shape, 6) and [g["id"] for g in got] == ["a", "b", "c"]
    idx = json.load(open(os.path.join(ROOT, "lambdas", "common", "vector_catalog_index.json")))["items"]
    held = sorted(i["id"] for i in idx if "rotate" in i.get("motion", []))
    assert held == ["offshore_wind_farm", "solar_wind_farm", "tall_wind_turbines_vertical"] and len(idx) - len(held) == 154


# ---------------------------------------------------------------- capabilities
def _caps(monkeypatch, locale="en", **env):
    for k in ("VECTOR_SCENES", "BG_ANIMATED", "BG_LOOPS", "WATERMARK_ENABLED"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    ev = {"pathParameters": {"user_id": "u1"}, "headers": {"X-Locale": locale}, "requestContext": {"authorizer": {"claims": {"sub": "u1"}}}}
    r = capabilities_api.handler(ev, None)
    assert r["statusCode"] == 200
    return json.loads(r["body"])["looks"]


def test_capabilities_lists_the_looks_of_this_stage(monkeypatch):
    off = _caps(monkeypatch)
    assert off["style"]["param"] == "style" and off["style"]["default"] == "auto" and [o["id"] for o in off["style"]["options"]] == ["auto", "cartoon", "real"]
    assert [o["available"] for o in off["style"]["options"]] == [True, False, True] and off["backgrounds"] == {"animated": False, "loops_3d": False, "chosen_by": "director", "note": off["backgrounds"]["note"]}
    assert "cartoon" not in off["style"]["options"][0]["note"].lower()                         # with the cartoon scenes off, Auto does not promise them
    on = _caps(monkeypatch, VECTOR_SCENES="1", BG_ANIMATED="1", BG_LOOPS="1")
    assert [o["available"] for o in on["style"]["options"]] == [True, True, True] and on["backgrounds"]["animated"] is True and on["backgrounds"]["loops_3d"] is True
    assert [o["label"] for o in on["style"]["options"]] == ["Auto", "Illustrated", "Real"] and "cartoon" in on["style"]["options"][0]["note"]
    es = _caps(monkeypatch, "es", VECTOR_SCENES="1")
    assert [o["label"] for o in es["style"]["options"]] == ["Automático", "Ilustradas", "Reales"] and es["backgrounds"]["note"] != on["backgrounds"]["note"]
    assert all(o["note"] and o["note"] != e["note"] for o, e in zip(on["style"]["options"], es["style"]["options"]))


def test_the_launcher_accepts_exactly_the_styles_capabilities_lists(monkeypatch):
    import sf_launcher
    src = open(sf_launcher.__file__, encoding="utf-8").read()
    assert 'body["style"] not in ("auto", "cartoon", "real")' in src
    assert [o["id"] for o in _caps(monkeypatch)["style"]["options"]] == ["auto", "cartoon", "real"]


# ---------------------------------------------------------------- the stack
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
            app = cdk.App(context={"stage": "qa", "engine": "v2", **ctx}, outdir=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"vmk-looks-{n}"))
            os.environ.setdefault("CDK_SKIP_LAYER_CHECK", "1")
            cfg = {"account": "123456789012", "region": "eu-west-1", "domain": None, "callbackUrls": ["https://qa.videomk.com/auth/callback"], "logoutUrls": ["https://qa.videomk.com/"], **(stage_extra or {})}
            return Template.from_stack(BackendStack(app, "videomk-qa", stage="qa", stage_cfg=cfg, env=cdk.Environment(account="123456789012", region="eu-west-1"))).to_json()
        yield build
    finally:
        os.chdir(cwd)


def _env(t, name):
    return next(v["Properties"]["Environment"]["Variables"] for k, v in t["Resources"].items() if v["Type"] == "AWS::Lambda::Function" and k.startswith(name))


def test_the_stack_switches_the_cartoon_scenes_on_only_where_asked_and_only_with_the_catalog(synth):
    off = synth(0, imageCatalog="1")
    on = synth(1, {"vectorScenes": True, "bgAnimated": True, "bgLoops": True}, imageCatalog="1")
    for fn in ("V2PlanFn", "V2RenderChunkFn"):
        assert "VECTOR_SCENES" not in _env(off, fn) and _env(on, fn)["VECTOR_SCENES"] == "1"
    assert "CATALOG_BUCKET" not in _env(off, "V2RenderChunkFn") and "CATALOG_BUCKET" in _env(on, "V2RenderChunkFn") and "CATALOG_BUCKET" in _env(on, "V2SelfTestFn")
    caps = _env(on, "CapabilitiesFunction")
    assert (caps["VECTOR_SCENES"], caps["BG_ANIMATED"], caps["BG_LOOPS"]) == ("1", "1", "1") and not {"VECTOR_SCENES", "BG_ANIMATED", "BG_LOOPS"} & set(_env(off, "CapabilitiesFunction"))

    def grants(t):
        out = {}
        for k, v in t["Resources"].items():
            if v["Type"] == "AWS::IAM::Policy":
                for st in v["Properties"]["PolicyDocument"]["Statement"]:
                    if "/v/*" in json.dumps(st.get("Resource")):
                        assert st["Effect"] == "Allow" and st["Action"] == "s3:GetObject"       # read one prefix: no listing, no write
                        out[k] = st
        return out
    assert grants(off) == {} and sorted(k[:10] for k in grants(on)) == ["V2RenderCh", "V2SelfTest"]
    with pytest.raises(ValueError, match="imageCatalog"):
        synth(2, {"vectorScenes": True})                                                       # no catalog bucket, no cartoon scenes


def test_stages_json_turns_the_cartoon_scenes_on_in_qa_only():
    stages = json.load(open(os.path.join(ROOT, "stages.json")))
    assert stages["qa"].get("vectorScenes") is True and "vectorScenes" not in stages["prod"]
