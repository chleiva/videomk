"""The director's choice of the animated background (engine/background.py, docs/BACKGROUNDS_ANIMATED.md): chosen by the topic's mood behind BG_ANIMATED,
checked against the theme, never a muddy combination, carried by the timeline and the chunks, continuous across scene changes, and nothing at all with the flag off."""
import copy
import json

import numpy as np
import pytest

from engine import background as bgsel, bg_animated as B, director, edits
from engine.renderer import Renderer
from engine.timeline import build_timeline, chunk_plan, chunk_timeline
from tests.test_create_options import _plan, _run_timeline
from tests.test_skills import _ask_small


def _big(system, user):
    return json.dumps({"legit": True, "title": "How tides work", "description": "d", "mood": "calm", "theme": "midnight", "voices": {"narrator": "Ruth"}, "beats": [
        {"narration": " ".join(["w"] * 30), "scene": {"type": "title", "props": {"title": "x"}}} for _ in range(4)]})


def _small(answer):
    base = _ask_small(["explainer-education"])

    def ask(system, user, n=120):
        if "moving background" in system:
            if isinstance(answer, Exception):
                raise answer
            return answer
        return base(system, user, n)
    return ask


# ------------------------------------------------------------------ the choice
def test_flag_off_the_plan_has_no_background_and_no_call_is_made(monkeypatch):
    monkeypatch.delenv("BG_ANIMATED", raising=False)
    seen = []

    def ask(system, user, n=120):
        seen.append(system)
        return _ask_small(["explainer-education"])(system, user, n)
    out = director.direct("how tides work", minutes=1.0, ask_small=ask, ask_big=_big, language="en")
    assert "background" not in out["plan"] and "background" not in out["research"] and not any("moving background" in s for s in seen)


def test_flag_on_the_director_picks_by_mood_and_the_choice_is_recorded(monkeypatch):
    monkeypatch.setenv("BG_ANIMATED", "1")
    out = director.direct("how tides work", minutes=1.0, ask_small=_small('{"style": "aurora", "palette": "ocean"}'), ask_big=_big, language="en")
    bg = out["plan"]["background"]
    assert (bg["style"], bg["palette"], bg["mode"], bg["by"]) == ("aurora", "ocean", "dark", "director") and bg["speed"] == 0.7 and bg["loop_seconds"] == bgsel.LOOP_SECONDS
    assert out["research"]["background"] == {"style": "aurora", "palette": "ocean", "by": "director"}
    assert B.sanitize(bg, "midnight") == B.BgSpec(style="aurora", palette="ocean", mode="dark", speed=0.7, intensity=0.8, seed=bg["seed"], loop_seconds=12.0)   # what the renderer makes of it


@pytest.mark.parametrize("answer", ["", "no idea", '{"style": "plasma"}', "[1, 2]", RuntimeError("throttled")])
def test_a_failed_or_odd_answer_falls_back_to_the_mood_and_never_fails_the_video(monkeypatch, answer):
    monkeypatch.setenv("BG_ANIMATED", "1")
    out = director.direct("how tides work", minutes=1.0, ask_small=_small(answer), ask_big=_big, language="en")
    bg = out["plan"]["background"]
    assert bg["by"] == "mood" and bg["style"] == "aurora" and bg["palette"] == "midnight"   # calm -> aurora, the theme's own palette


def test_a_video_of_the_persons_photos_keeps_todays_backdrop(monkeypatch):
    monkeypatch.setenv("BG_ANIMATED", "1")

    def big(system, user):
        return json.dumps({"legit": True, "title": "T", "description": "d", "voices": {"narrator": "Ruth"}, "beats": [
            {"narration": " ".join(["w"] * 30), "scene": {"type": "image", "props": {"photo": "P1", "image_query": "a street", "alt": "a"}}} for _ in range(3)]})
    photos = [{"id": "P1", "key": "k", "w": 600, "h": 400, "orientation": "landscape", "caption": "a street"}]
    out = director.direct("my trip to Paris", minutes=1.0, ask_small=_small('{"style": "gas"}'), ask_big=big, language="en", photos=photos)
    assert "background" not in out["plan"]


def test_muddy_combinations_are_never_used():
    for theme, pals in bgsel.THEME_PALETTES.items():
        mode = bgsel.mode_of(theme)
        for mood in ("calm", "bright", "tense", "odd"):
            for style in bgsel.STYLES + ("", "nope"):
                for pal in tuple(B.PALETTES) + ("", "nope"):
                    st, p = bgsel.settle(style, pal, mood, theme)
                    assert bgsel.allowed(st, p, mode) and p in pals, (theme, mood, style, pal, st, p)
                    assert not (st in ("mesh", "lava") and p in bgsel.WARM) and not (st == "mesh" and mode == "light")
    assert bgsel.settle("mesh", "sunrise", "bright", "sunrise") == ("mesh", "violet")     # the wished style survives on a palette that carries it
    assert bgsel.settle("lava", "ember", "bright", "sunrise") == ("lava", "violet")
    assert bgsel.settle("mesh", "violet", "bright", "paper")[0] == "bokeh"                # light mode has no mesh: the mood's style instead
    assert bgsel.settle("gas", "forest", "calm", "sunrise") == ("gas", "sunrise")         # a palette that does not suit the theme: the theme's own
    assert bgsel.settle("smoke", "mono", "tense", "midnight") == ("smoke", "mono")


def test_the_choice_is_stable_per_video_and_the_prompt_lists_only_the_themes_palettes():
    plan = {"title": "How tides work", "mood": "tense", "theme": "sunrise"}
    seen = []
    a = bgsel.choose("tides", plan, lambda s, u: seen.append((s, u)) or '{"style":"smoke","palette":"ember"}')
    assert a == bgsel.choose("tides", plan, lambda s, u: '{"style":"smoke","palette":"ember"}') and a["palette"] == "ember" and a["speed"] == 1.15
    assert "sunrise, ember, violet" in seen[0][0] and "forest" not in seen[0][0].split("Palettes:")[1].split(".")[0] and "Mood: tense" in seen[0][1]
    assert bgsel.choose("tides", plan)["by"] == "mood"   # no model at all


# ------------------------------------------------------------------ timeline and chunks
def test_the_timeline_and_every_chunk_carry_the_background_and_the_hashes_follow_it(monkeypatch):
    plain, _ = _run_timeline(monkeypatch, _plan())
    plan = _plan()
    plan["background"] = bgsel.choose("x", plan)
    tl, _ = _run_timeline(monkeypatch, plan)
    assert "background" not in plain and all("bg_t0" not in s for s in plain["scenes"])
    assert tl["background"] == plan["background"]
    assert [s["bg_t0"] for s in tl["scenes"]] == [round(s["start"] % 12.0, 3) for s in tl["scenes"]]
    a, b = chunk_plan(plain, 4), chunk_plan(tl, 4)
    assert len(a) == len(b) and all(x["hash"] != y["hash"] for x, y in zip(a, b))
    other = copy.deepcopy(tl)
    other["background"] = dict(tl["background"], style="smoke")
    assert all(x["hash"] != y["hash"] for x, y in zip(chunk_plan(other, 4), b))
    sub = chunk_timeline(tl, b[-1]["lo"], b[-1]["hi"])
    assert sub["background"] == tl["background"] and sub["scenes"][0]["bg_t0"] == tl["scenes"][b[-1]["lo"]]["bg_t0"] and sub["scenes"][0]["start"] == 0
    assert "background" not in chunk_timeline(plain, 0, 1)


def _tl2(bg=None):
    scenes = [{"id": "a", "type": "title", "start": 0.0, "duration": 5.0, "props": {"title": ""}, "words": [], "transition": "none"},
              {"id": "b", "type": "title", "start": 5.0, "duration": 5.0, "props": {"title": ""}, "words": [], "transition": "none"}]
    tl = {"scenes": scenes, "theme": "midnight", "captions": False, "duration": 10.0, "width": 1920, "height": 1080, "fps": 30, "outro": False}
    if bg:
        tl["background"] = bg
        for s in scenes:
            s["bg_t0"] = bgsel.phase(s["start"], bg)
    return tl


def test_the_background_flows_across_a_scene_change_and_a_chunk_boundary(monkeypatch):
    monkeypatch.setenv("BG_ANIMATED", "1")
    bg = bgsel.choose("x", {"title": "t", "mood": "bright", "theme": "midnight"})
    tl = _tl2(bg)
    r = Renderer(tl, draft=True)
    before, after = np.asarray(r.frame_at(5.0 - 1 / 30), np.int16), np.asarray(r.frame_at(5.0), np.int16)
    step = np.abs(np.asarray(r.frame_at(2.0), np.int16) - np.asarray(r.frame_at(2.0 + 1 / 30), np.int16)).mean()
    assert np.abs(before - after).mean() <= step * 3 + 1.5   # one frame's drift (plus dither grain), not a jump to another place in the loop
    r2 = Renderer(chunk_timeline(tl, 1, 2), draft=True)   # the second scene rendered on its own, as a render function does
    assert np.abs(np.asarray(r2.frame_at(0.0), np.int16) - after).mean() < 1.5
    old = copy.deepcopy(tl)   # without the scene's place in the loop (the old per-scene phase) the same cut jumps
    for s in old["scenes"]:
        s.pop("bg_t0")
    ro = Renderer(old, draft=True)
    assert np.abs(np.asarray(ro.frame_at(5.0 - 1 / 30), np.int16) - np.asarray(ro.frame_at(5.0), np.int16)).mean() > np.abs(before - after).mean()


def test_with_the_flag_off_a_timeline_that_carries_a_background_renders_as_before(monkeypatch):
    monkeypatch.delenv("BG_ANIMATED", raising=False)
    bg = bgsel.choose("x", {"title": "t", "mood": "calm", "theme": "midnight"})
    assert np.array_equal(np.asarray(Renderer(_tl2(bg), draft=True).frame_at(1.0)), np.asarray(Renderer(_tl2(), draft=True).frame_at(1.0)))


def test_a_theme_edit_keeps_the_background_allowed():
    plan = _plan()
    plan["theme"], plan["mood"] = "midnight", "bright"
    plan["background"] = bgsel.choose("x", plan, lambda s, u: '{"style":"mesh","palette":"forest"}')
    assert (plan["background"]["style"], plan["background"]["palette"]) == ("mesh", "forest")
    new, _ = edits.apply_ops(plan, [{"op": "set_meta", "theme": "paper"}])[:2]
    bg = new["background"]
    assert bg["mode"] == "light" and bgsel.allowed(bg["style"], bg["palette"], "light") and bg["palette"] in bgsel.THEME_PALETTES["paper"] and bg["seed"] == plan["background"]["seed"]
