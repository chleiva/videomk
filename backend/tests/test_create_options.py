"""The deterministic creation options (docs/CREATE_API.md, docs/CREATE_OPTIONS_FLOW.md): validation, workflow input, picture size, cache keys, ffmpeg size,
capabilities, edits keeping their format, and the price not depending on format."""
import copy
import json

import pytest

from common import photo_ids, wallet
from engine import awsio, format_options as fo, media, plan as plan_mod
from engine.frame import Frame
from engine.handlers import edit_prep_handler, editor_get, timeline_handler
from engine.renderer import Renderer
from engine.timeline import build_timeline, chunk_plan
from tests.test_hardening import _event, launcher  # noqa: F401  (the fixture)
from tests.tests_helpers import PLAN_WITH_IMAGE

PROMPT = "A short explainer about how black holes form"
PIXELS = {("16:9", "720p"): (1280, 720), ("16:9", "1080p"): (1920, 1080), ("9:16", "720p"): (720, 1280), ("9:16", "1080p"): (1080, 1920),
          ("1:1", "720p"): (720, 720), ("1:1", "1080p"): (1080, 1080), ("4:5", "720p"): (720, 900), ("4:5", "1080p"): (1080, 1350)}


def post(launcher, **extra):
    return launcher.handler(_event(body={"prompt": PROMPT, "target_minutes": 1, **extra}), None)


def sent(launcher):
    return json.loads(launcher.fake.calls[-1]["input"])


@pytest.fixture
def all_ready(monkeypatch):
    monkeypatch.setenv("READY_ASPECTS", "16:9,9:16,1:1,4:5")


# ---------- validation ----------
def test_defaults_without_any_new_field_behave_as_today(launcher):
    assert post(launcher)["statusCode"] == 202
    s = sent(launcher)
    assert not ({"platform", "aspect", "resolution", "language", "brief", "captions"} & set(s))   # nothing new reaches the workflow
    assert format_options_default() == {"aspect": "16:9", "resolution": "1080p", "width": 1920, "height": 1080}


def format_options_default():
    f = fo.frame_dict()
    return {k: f[k] for k in ("aspect", "resolution", "width", "height")}


def test_every_valid_value_is_forwarded(launcher, all_ready):
    brief = {"audience": "kids", "tone": "calm", "summary": "For kids · Calm"}
    r = post(launcher, platform="shorts", aspect="9:16", resolution="720p", captions=False, language="es", brief=brief)
    assert r["statusCode"] == 202
    s = sent(launcher)
    assert (s["platform"], s["aspect"], s["resolution"], s["captions"], s["language"], s["brief"]) == ("shorts", "9:16", "720p", False, "es", brief)


@pytest.mark.parametrize("platform", fo.PLATFORM_IDS)
def test_every_platform_is_accepted(launcher, platform):
    assert post(launcher, platform=platform)["statusCode"] == 202 and sent(launcher)["platform"] == platform


@pytest.mark.parametrize("extra", [
    {"platform": "myspace"}, {"platform": 3}, {"aspect": "2:1"}, {"aspect": 1}, {"resolution": "4k"}, {"resolution": 1080}, {"captions": "yes"}, {"captions": 1},
    {"language": "fr"}, {"language": "EN"}, {"language": 5}, {"brief": "kids"}, {"brief": ["a"]}, {"brief": {"notes": "x" * 3000}},
])
def test_invalid_values_are_a_400_and_charge_nothing(launcher, all_ready, extra):
    r = post(launcher, **extra)
    assert r["statusCode"] == 400 and json.loads(r["body"])["message"]
    assert launcher.fake.calls == [] and wallet.balance("u1")["balance"] == 5


def test_the_400_messages_name_the_field_and_the_choices(launcher):
    assert "'aspect' must be one of: 16:9, 9:16, 1:1, 4:5" in json.loads(post(launcher, aspect="3:2")["body"])["message"]
    assert "'resolution' must be one of: 720p, 1080p" in json.loads(post(launcher, resolution="2k")["body"])["message"]
    assert "'language' must be 'auto' or one of: en, es" in json.loads(post(launcher, language="de")["body"])["message"]


def test_language_auto_is_valid(launcher):
    assert post(launcher, language="auto")["statusCode"] == 202 and sent(launcher)["language"] == "auto"


def test_a_format_that_is_not_ready_is_refused(launcher):
    r = post(launcher, aspect="9:16")
    assert r["statusCode"] == 400 and json.loads(r["body"])["message"] == "This format is not available yet"
    assert launcher.fake.calls == [] and wallet.balance("u1")["balance"] == 5
    assert post(launcher, aspect="16:9")["statusCode"] == 202   # the default stays available


def test_a_ready_format_is_accepted_and_only_the_ready_ones(launcher, monkeypatch):
    monkeypatch.setenv("READY_ASPECTS", "16:9,9:16")
    assert post(launcher, aspect="9:16", resolution="720p")["statusCode"] == 202
    assert post(launcher, aspect="4:5")["statusCode"] == 400


def test_a_language_that_is_not_ready_is_refused(launcher, monkeypatch):
    monkeypatch.setenv("READY_LANGUAGES", "en")
    assert post(launcher, language="es")["statusCode"] == 400
    assert post(launcher, language="en")["statusCode"] == 202


def test_options_are_part_of_the_duplicate_fingerprint(launcher, all_ready):
    assert post(launcher, aspect="16:9")["statusCode"] == 202
    again = post(launcher, aspect="9:16")                        # same text, different format: a different video
    assert json.loads(again["body"])["message"] == "workflow started" and len(launcher.fake.calls) == 2
    same = post(launcher, aspect="9:16")                         # the very same request: the first video
    assert "already started" in json.loads(same["body"])["message"] and len(launcher.fake.calls) == 2
    other = post(launcher, aspect="9:16", resolution="720p")
    assert json.loads(other["body"])["message"] == "workflow started"
    assert json.loads(post(launcher, aspect="9:16", resolution="720p", captions=False)["body"])["message"] == "workflow started"


def test_format_does_not_change_the_price(launcher, all_ready):
    assert wallet.credits_for_minutes(3) == 3 and wallet.credits_for_minutes(0.25 + 1) == 2
    for aspect, res in (("16:9", "1080p"), ("9:16", "720p"), ("1:1", "1080p"), ("4:5", "720p")):
        before = wallet.balance("u1")["balance"]
        r = launcher.handler(_event(body={"prompt": f"{PROMPT} in {aspect} {res}", "target_minutes": 1, "aspect": aspect, "resolution": res}), None)
        assert r["statusCode"] == 202 and wallet.balance("u1")["balance"] == before - 1   # 1 credit for 1 minute, whatever the format


def test_max_photos_constant_matches():
    assert fo.MAX_PHOTOS == photo_ids.MAX_PHOTOS


# ---------- the picture size ----------
@pytest.mark.parametrize("key,size", PIXELS.items())
def test_the_exact_pixel_table(key, size):
    assert fo.frame_size(*key) == size
    f = Frame.parse(*key)
    assert (f.width, f.height) == size and all(x % 2 == 0 for x in size)   # even: yuv420p needs it


def test_unknown_or_absent_means_16_9_1080p():
    assert fo.frame_size() == (1920, 1080) and fo.frame_size("weird", "weird") == (1920, 1080)
    assert fo.frame_dict()["orientation"] == "landscape" and fo.frame_dict("9:16")["orientation"] == "portrait" and fo.frame_dict("1:1")["orientation"] == "square"
    assert fo.frame_of({}) == fo.frame_dict() and fo.frame_of({"frame": "junk"}) == fo.frame_dict()


_BASE, _ = plan_mod.validate_plan(copy.deepcopy(PLAN_WITH_IMAGE))   # beat ids are random: one plan, so equal inputs hash equal


def _plan(frame=None):
    plan = copy.deepcopy(_BASE)
    if frame is not None:
        plan["frame"] = frame
    return plan


def _run_timeline(monkeypatch, plan, **event):
    store = {"generation/v2/v1/plan_r1.json": plan}
    monkeypatch.setattr(awsio, "get_json", lambda k: copy.deepcopy(store[k]))
    monkeypatch.setattr(awsio, "put_json", lambda k, o: store.__setitem__(k, copy.deepcopy(o)))
    beats = [{"id": b["id"], "media": {"duration": 3.0, "audio_key": f"generation/v2/v1/audio/{b['id']}.mp3"}} for b in plan["beats"]]
    out = timeline_handler.handler({"video_id": "v1", "user_id": "u1", "plan_key": "generation/v2/v1/plan_r1.json", "rev": 1, "mode": "final", "beats": beats, **event}, None)
    return store[out["timeline_key"]], out


@pytest.mark.parametrize("key,size", PIXELS.items())
def test_width_and_height_reach_the_timeline(monkeypatch, key, size):
    tl, out = _run_timeline(monkeypatch, _plan(fo.frame_dict(*key, platform="shorts")))
    assert (tl["width"], tl["height"]) == size and tl["frame"]["aspect"] == key[0] and tl["frame"]["resolution"] == key[1]
    assert chunk_plan(tl, 10) and out["chunks"]


def test_an_old_plan_without_a_frame_is_16_9_1080p(monkeypatch):
    tl, _ = _run_timeline(monkeypatch, _plan())
    assert (tl["width"], tl["height"]) == (1920, 1080) and tl["frame"]["aspect"] == "16:9"


def test_build_timeline_default_size_is_unchanged():
    tl = build_timeline(_plan(), [{"duration": 3.0}] * 4, video_id="v")
    assert (tl["width"], tl["height"]) == (1920, 1080)


def test_chunk_cache_key_changes_with_the_frame_size(monkeypatch):
    hashes = {}
    for key in PIXELS:
        tl, _ = _run_timeline(monkeypatch, _plan(fo.frame_dict(*key)))
        hashes[key] = [c["hash"] for c in chunk_plan(tl, 10)]
    assert len({tuple(h) for h in hashes.values()}) == len(PIXELS)           # two sizes never share cached segments
    assert all(not set(hashes[a]) & set(hashes[b]) for a in PIXELS for b in PIXELS if a != b)
    tl, _ = _run_timeline(monkeypatch, _plan(fo.frame_dict("9:16")))
    assert [c["hash"] for c in chunk_plan(tl, 10)] == hashes[("9:16", "1080p")]   # and the same size always shares


def test_captions_off_changes_the_timeline_and_the_cache_key(monkeypatch):
    on, _ = _run_timeline(monkeypatch, _plan())
    plan = _plan()
    plan["captions"] = False
    off, _ = _run_timeline(monkeypatch, plan)
    assert on["captions"] is True and off["captions"] is False
    assert [c["hash"] for c in chunk_plan(on, 10)] != [c["hash"] for c in chunk_plan(off, 10)]


def test_draft_output_size_is_half_and_even_for_every_format():
    for key, (w, h) in PIXELS.items():
        r = Renderer({"width": w, "height": h, "fps": 30, "scenes": [{"start": 0, "duration": 1, "type": "title", "props": {"title": "x"}}], "duration": 1.0}, draft=True)
        assert (r.out_w, r.out_h) == (w // 4 * 2, h // 4 * 2) and r.out_w % 2 == 0 and r.out_h % 2 == 0
        assert (Renderer({"width": w, "height": h, "fps": 30, "scenes": r.scenes, "duration": 1.0}).out_w, ) == (w,)


# ---------- ffmpeg ----------
class _Popen:
    cmds = []

    def __init__(self, cmd, **kw):
        _Popen.cmds.append(cmd)
        import io
        self.stdin, self.stderr = io.BytesIO(), io.BytesIO()

    def wait(self):
        return 0


@pytest.mark.parametrize("key,size", PIXELS.items())
def test_the_encode_command_uses_the_frame_size(monkeypatch, key, size):
    monkeypatch.setattr(media.subprocess, "Popen", _Popen)
    monkeypatch.setattr(media, "ffmpeg_bin", lambda: "ffmpeg")
    _Popen.cmds.clear()
    media.encode_segment([b"x"], "/tmp/o.ts", width=size[0], height=size[1], fps=30, start_time=0.0, gop=30)
    cmd = _Popen.cmds[0]
    assert cmd[cmd.index("-s") + 1] == f"{size[0]}x{size[1]}"


def test_the_renderer_hands_the_frame_size_to_the_encoder(monkeypatch):
    from engine import pipeline
    seen = {}
    monkeypatch.setattr(media, "encode_segment", lambda frames, out, **kw: seen.update(kw) or 0)
    tl = {"width": 1080, "height": 1350, "fps": 30, "theme": "midnight", "scenes": [{"id": "a", "start": 0, "duration": 1, "type": "title", "props": {"title": "x"}, "words": []}], "duration": 1.0}
    pipeline.render_chunk(tl, 0, 30, "/tmp/x.ts")
    assert (seen["width"], seen["height"]) == (1080, 1350)
    pipeline.render_chunk(tl, 0, 30, "/tmp/x.ts", draft=True)
    assert (seen["width"], seen["height"]) == (540, 674)


def test_the_preview_gif_keeps_the_videos_shape(tmp_path, monkeypatch):
    from PIL import Image
    from engine import pipeline
    monkeypatch.setattr(media, "extract_frame", lambda v, t, png: Image.new("RGB", (1080, 1920), (9, 9, 9)).save(png))
    out = str(tmp_path / "p.gif")
    assert pipeline.preview_gif("v.mp4", out, 10.0)
    assert Image.open(out).size == (320, 568)


# ---------- edits keep the format ----------
def test_an_edit_keeps_the_original_format(monkeypatch):
    from engine import edits
    plan = _plan(fo.frame_dict("4:5", "720p", "instagram_feed"))
    new, _ = edits.apply_ops(plan, [{"op": "set_meta", "theme": "paper", "captions": False}, {"op": "set_narration", "id": plan["beats"][0]["id"], "text": "A rewritten first beat about the wonder of light in water droplets."}])
    assert new["frame"] == plan["frame"] and new["captions"] is False
    tl, _ = _run_timeline(monkeypatch, new, rev=2)      # the edit workflow rebuilds the timeline from this plan
    assert (tl["width"], tl["height"]) == (720, 900) and tl["frame"]["aspect"] == "4:5"
    assert [c["hash"] for c in chunk_plan(tl, 10)] != [c["hash"] for c in chunk_plan(_run_timeline(monkeypatch, _plan(), rev=2)[0], 10)]   # not the 16:9 cache
    store = {"generation/v2/v1/plan_r2.json": new}
    monkeypatch.setattr(awsio, "get_json", lambda k: store[k])
    out = edit_prep_handler.handler({"video_id": "v1", "user_id": "u1", "plan_key": "generation/v2/v1/plan_r2.json", "rev": 2}, None)
    assert out["plan_key"] == "generation/v2/v1/plan_r2.json"     # the edit prep passes the plan along; the frame lives in the plan


def test_editor_view_reports_the_frame():
    assert fo.frame_of(_plan(fo.frame_dict("1:1")))["width"] == 1080 and editor_get.format_options is fo


# ---------- the director's FORMAT line ----------
def test_frame_prompt_is_empty_for_the_default_and_short_otherwise():
    assert plan_mod.frame_prompt(None) == "" and plan_mod.frame_prompt({}) == "" and plan_mod.frame_prompt({"aspect": "16:9", "platform": "other"}) == ""
    v = plan_mod.frame_prompt({"aspect": "9:16", "platform": "shorts"})
    assert "Frame: vertical 9:16 for Shorts" in v and "hook in the first 3 seconds" in v and len(v) < 300
    assert "square 1:1" in plan_mod.frame_prompt({"aspect": "1:1"}) and "for YouTube" in plan_mod.frame_prompt({"platform": "youtube"})
    b = plan_mod.frame_prompt({"brief": {"audience": "kids", "tone": "calm", "summary": "x"}})
    assert "audience kids" in b and "tone calm" in b and "summary" not in b


def test_the_director_gets_the_frame_line(monkeypatch):
    from engine import director
    seen = {}

    def fake_generate_plan(topic, notes, minutes, ask_big, **kw):
        seen["craft"] = kw["craft"]
        return {"legit": False, "reason": "stop"}, []

    monkeypatch.setattr(director.plan_mod, "generate_plan", fake_generate_plan)
    monkeypatch.setattr(director.research, "gather_notes", lambda *a, **k: ("", []))
    monkeypatch.setattr(director.skills_mod, "select", lambda *a, **k: [])
    director.direct("Explain how bees make honey to kids", minutes=1, ask_small=lambda s, u, n=120: "en", ask_big=lambda s, u: "", language="en", options={"aspect": "9:16", "platform": "tiktok"})
    assert "Frame: vertical 9:16 for TikTok" in seen["craft"]
    director.direct("Explain how bees make honey to kids", minutes=1, ask_small=lambda s, u, n=120: "en", ask_big=lambda s, u: "", language="en")
    assert "Frame:" not in seen["craft"]


# ---------- capabilities ----------
def cap_event(user="u1", path_user=None, authed=True):
    return {"pathParameters": {"user_id": path_user or user}, "headers": {}, "requestContext": {"authorizer": {"claims": {"sub": user}}} if authed else {}}


def test_capabilities_shape_and_defaults(monkeypatch):
    import capabilities_api
    for k in ("READY_ASPECTS", "BETA_ASPECTS", "READY_LANGUAGES", "INTAKE_ENABLED"):
        monkeypatch.delenv(k, raising=False)
    r = capabilities_api.handler(cap_event(), None)
    body = json.loads(r["body"])
    assert r["statusCode"] == 200
    assert set(body) == {"aspects", "resolutions", "platforms", "languages", "lengths", "max_photos", "intake"}
    assert body["aspects"] == [{"id": "16:9", "label": "Landscape", "ready": True, "beta": False}, {"id": "9:16", "label": "Vertical", "ready": False, "beta": False},
                               {"id": "1:1", "label": "Square", "ready": False, "beta": False}, {"id": "4:5", "label": "Portrait", "ready": False, "beta": False}]
    assert body["resolutions"] == [{"id": "720p", "label": "720p"}, {"id": "1080p", "label": "1080p"}]
    assert body["languages"] == [{"id": "en", "label": "English"}, {"id": "es", "label": "Español"}]
    assert body["lengths"] == {"min_minutes": 0.25, "max_minutes": 12, "presets": [0.25, 0.5, 0.75, 1, 2, 3, 5, 8, 12]} and body["max_photos"] == 100 and body["intake"] is False
    plat = {p["id"]: p for p in body["platforms"]}
    assert set(plat) == set(fo.PLATFORM_IDS) and all(set(p) == {"id", "label", "aspect", "resolution", "note", "recommended_minutes", "max_minutes", "other_aspects"} for p in plat.values())
    assert [(plat[k]["aspect"], plat[k]["resolution"]) for k in ("youtube", "shorts", "tiktok", "reels", "instagram_feed", "linkedin", "x", "other")] == [
        ("16:9", "1080p"), ("9:16", "1080p"), ("9:16", "1080p"), ("9:16", "1080p"), ("4:5", "1080p"), ("4:5", "1080p"), ("16:9", "1080p"), ("16:9", "1080p")]
    assert "1:1" in plat["linkedin"]["other_aspects"] and plat["youtube"]["note"] == "Landscape 16:9 · 1080p · about 3 min"


def test_capabilities_follow_the_server_settings(monkeypatch):
    import capabilities_api
    monkeypatch.setenv("READY_ASPECTS", "16:9,9:16,bogus")
    monkeypatch.setenv("BETA_ASPECTS", "9:16,1:1")      # 1:1 is beta but not ready: not reported as beta
    monkeypatch.setenv("READY_LANGUAGES", "en")
    monkeypatch.setenv("INTAKE_ENABLED", "1")
    body = json.loads(capabilities_api.handler(cap_event(), None)["body"])
    got = {a["id"]: (a["ready"], a["beta"]) for a in body["aspects"]}
    assert got == {"16:9": (True, False), "9:16": (True, True), "1:1": (False, False), "4:5": (False, False)}
    assert body["languages"] == [{"id": "en", "label": "English"}] and body["intake"] is True


def test_capabilities_auth_and_path_checks():
    import capabilities_api
    assert capabilities_api.handler(cap_event(authed=False), None)["statusCode"] == 401
    assert capabilities_api.handler(cap_event(user="u1", path_user="u2"), None)["statusCode"] == 403
    assert capabilities_api.handler({"requestContext": {"authorizer": {"claims": {"sub": "u1"}}}}, None)["statusCode"] == 403


def test_what_capabilities_lists_ready_the_launcher_accepts(launcher, monkeypatch):
    import capabilities_api
    monkeypatch.setenv("READY_ASPECTS", "16:9,1:1")
    ready = [a["id"] for a in json.loads(capabilities_api.handler(cap_event(), None)["body"])["aspects"] if a["ready"]]
    for a in fo.ASPECT_IDS:
        assert (post(launcher, aspect=a, platform=f"{'x' if a == '1:1' else 'other'}")["statusCode"] == 202) == (a in ready) or a == "16:9"


def test_vertical_videos_ask_for_portrait_stock_clips_and_landscape_calls_are_unchanged(monkeypatch):
    from engine.handlers import beat_handler

    seen = []
    monkeypatch.setattr(beat_handler.clips, "scout_clip", lambda q, ctx, alt, **kw: seen.append(kw) or None)
    monkeypatch.setattr(beat_handler, "get_secret_param", lambda *a, **k: "k")
    monkeypatch.setattr(beat_handler.awsio, "prefix", lambda v: f"p/{v}/")
    monkeypatch.setattr(beat_handler, "make_photo", lambda *a, **k: {})
    beat = {"id": "b1", "scene": {"type": "clip", "props": {"clip_query": "city street", "alt": "street"}}}
    for frame, want in (({}, None), ({"aspect": "16:9"}, None), ({"aspect": "9:16"}, "portrait"), ({"aspect": "4:5"}, "portrait"), ({"aspect": "1:1"}, "square")):
        seen.clear()
        try:
            beat_handler.make_clip({"frame": frame, "beats": []}, beat, "v1", "cost", 5.0)
        except Exception:
            pass
        assert seen and seen[0].get("orientation") == want, (frame, seen)
