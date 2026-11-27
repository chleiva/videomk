"""The watermark policy of 2026-11-27 (docs/WATERMARK.md): a free account's video always carries the videomk NAME (lockup, whole video, closing card) and nothing can
change that; `presence: moments` lets a premium account's mark come and go (eased fades, about 4 s near the start and about every 30 s at a scene change, never on an
emphasis scene, never over the closing card), the same in every render chunk; entitlements, capabilities, the API and the stack's switch."""
import copy
import json
import os

import numpy as np
import pytest

from common import i18n, watermark_store as store
from engine import watermark_spec as ws
from engine.renderer import Renderer
from engine.timeline import build_timeline, chunk_plan, chunk_timeline

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SPAN = ws.MOMENT_HOLD_S + 2 * ws.MOMENT_FADE_S


def _scenes(durs, types=None):
    out, t = [], 0.0
    for i, d in enumerate(durs):
        out.append({"id": f"s{i}", "type": (types or {}).get(i, "title"), "start": t, "duration": d})
        t += d
    return out, t


# ---------------------------------------------------------------- the option
def test_presence_is_a_videomk_option_validated_strictly():
    assert ws.parse({"mode": "videomk", "presence": "moments"})["presence"] == "moments" and ws.parse({"mode": "videomk", "presence": "always"})["presence"] == "always"
    assert "presence" not in ws.parse({"mode": "videomk"})                                  # absent stays absent: the policy decides, and a video without it is 'always' as before
    for bad in ({"mode": "videomk", "presence": "sometimes"}, {"mode": "videomk", "presence": True}, {"mode": "custom", "presence": "moments"}, {"mode": "videomk", "windows": [[0, 5]]}):
        with pytest.raises(ws.WatermarkError):
            ws.parse(bad)
    assert "presence" not in ws.parse({"mode": "videomk", "presence": "nonsense"}, strict=False)
    stored = ws.parse({"mode": "videomk", "presence": "moments", "windows": [[1.2, 6.4], ["x", 2], [9, 3], [30.3, 35.5]]}, strict=False)
    assert stored["windows"] == [[1.2, 6.4], [30.3, 35.5]]                                    # the timeline's own field survives a lenient read, cleaned
    assert "windows" not in ws.parse({"mode": "videomk", "presence": "always", "windows": [[1, 2]]}, strict=False)


# ---------------------------------------------------------------- when a 'moments' mark is on screen
def test_the_first_appearance_starts_after_the_first_second_and_lasts_about_four_seconds():
    scenes, total = _scenes([10, 10, 10])
    w = ws.moments(scenes, total)
    assert w[0] == [1.2, 1.2 + SPAN] and SPAN == pytest.approx(5.2)
    assert ws.moment_alpha(w, 0.5) == 0.0 and ws.moment_alpha(w, 1.0) == 0.0 and ws.moment_alpha(w, 1.2) == 0.0
    assert 0.0 < ws.moment_alpha(w, 1.4) < ws.moment_alpha(w, 1.6) < 1.0 and ws.moment_alpha(w, 1.5) == pytest.approx(0.5)   # eased: half way at half the fade
    assert ws.moment_alpha(w, 1.8) == 1.0 and ws.moment_alpha(w, 5.8) == 1.0 and 0.0 < ws.moment_alpha(w, 6.2) < 1.0 and ws.moment_alpha(w, 6.4) == 0.0 and ws.moment_alpha(w, 8.0) == 0.0
    steps = [ws.moment_alpha(w, 1.2 + i / 30) for i in range(19)]
    assert all(b >= a for a, b in zip(steps, steps[1:])) and max(b - a for a, b in zip(steps, steps[1:])) < 0.09               # no pop: at most 9 percent a frame


def test_it_returns_about_every_30_seconds_at_a_scene_change():
    scenes, total = _scenes([9, 11, 8, 12, 10, 9, 11, 10, 10, 10, 10, 10])                  # 120 s; scene changes at 9, 20, 28, 40, 50, 59, 70, 80, ...
    w = ws.moments(scenes, total)
    assert [round(a, 1) for a, _ in w] == [1.2, 28.3, 59.3, 90.3]                             # 30 -> the change at 28, 60 -> 59, 90 -> 90; 0.3 s into the new scene
    assert all(b - a == pytest.approx(SPAN) for a, b in w) and all(n[0] - p[1] >= ws.MOMENT_MIN_GAP_S for p, n in zip(w, w[1:]))
    assert w[-1][1] <= total - 0.7 - ws.MOMENT_END_CLEAR_S


def test_it_never_arrives_on_a_counter_or_a_chart():
    scenes, total = _scenes([9, 11, 8, 12, 10, 9, 11, 10], {2: "counter", 3: "chart"})       # the scene changes at 28 and 40 open emphasis scenes
    w = ws.moments(scenes, total)
    assert [round(a, 1) for a, _ in w][:2] == [1.2, 40.3] and not any(19.9 <= a <= 39.9 for a, _ in w)   # the counter is on from 20 and the chart from 28: no calm change within 8 s of 30, and 30 is inside the chart, so it waits for the next calm scene (40)
    far, total2 = _scenes([20, 30, 30], {1: "counter"})                                       # no calm change near 30: the plain time falls inside the counter, so it waits for the next scene
    w2 = ws.moments(far, total2)
    assert round(w2[1][0], 1) == 50.3


def test_never_over_the_closing_card_or_the_final_fade_and_none_in_a_video_too_short():
    scenes, total = _scenes([10, 10, 10, ws.END_CARD_S])
    w = ws.moments(scenes, total, ws.END_CARD_S)
    assert w and all(b <= total - ws.END_CARD_S - ws.MOMENT_END_CLEAR_S for _, b in w)
    assert ws.moments(*_scenes([4.0, 3.0])) == [] and ws.moments(*_scenes([9.0])) == [[1.2, 6.4]]
    assert ws.moments(*_scenes([5.0, ws.END_CARD_S]), ws.END_CARD_S) == []                    # too short: the closing card carries the name
    long = ws.moments(*_scenes([10] * 30))                                                    # 5 minutes: about ten appearances
    assert 9 <= len(long) <= 11


def test_the_appearances_are_a_pure_function_of_the_timeline():
    scenes, total = _scenes([9, 11, 8, 12, 10, 9, 11])
    assert ws.moments(scenes, total) == ws.moments(copy.deepcopy(scenes), total) == ws.moments(list(reversed(scenes)), total)


# ---------------------------------------------------------------- timeline, chunks, frames
def _plan(n=8, wm=None):
    beats = [{"id": f"b{i}", "narration": "one two three four five six seven eight", "scene": {"type": "title", "props": {"title": "Tides", "subtitle": ""}}} for i in range(n)]
    return {"title": "T", "language": "en", "theme": "midnight", "beats": beats, **({"watermark": wm} if wm else {})}


MOMENTS = {"mode": "videomk", "style": "lockup", "presence": "moments", "end_card": True, "position": "auto", "size": "small", "opacity": 0.65}
ALWAYS = {**MOMENTS, "presence": "always"}


def test_the_timeline_fixes_the_appearances_once_and_every_chunk_gets_its_own_times():
    tl = build_timeline(_plan(8, MOMENTS), [{"duration": 9.0}] * 8, video_id="v")
    wins = tl["watermark"]["windows"]
    assert wins[0] == [1.2, 6.4] and len(wins) >= 2 and tl["scenes"][-1]["id"] == "endcard" and wins[-1][1] <= tl["duration"] - ws.END_CARD_S - 1.0
    assert "windows" not in build_timeline(_plan(8, ALWAYS), [{"duration": 9.0}] * 8, video_id="v")["watermark"]
    chunks = chunk_plan(tl, 10)
    for c in chunks:
        sub = chunk_timeline(tl, c["lo"], c["hi"])
        base = tl["scenes"][c["lo"]]["start"]
        for a, b in sub["watermark"]["windows"]:
            assert [round(a + base, 3), round(b + base, 3)] in wins                              # the same appearances, in the chunk's own time
        for t in np.arange(0.0, sub["duration"], 0.25):                                           # and the same visibility at every moment as the whole video
            assert ws.moment_alpha(sub["watermark"]["windows"], t) == pytest.approx(ws.moment_alpha(wins, t + base), abs=1e-6)


def test_chunk_hashes_follow_the_presence_and_where_the_chunk_sits():
    a = build_timeline(_plan(8, ALWAYS), [{"duration": 9.0}] * 8, video_id="v")
    m = build_timeline(_plan(8, MOMENTS), [{"duration": 9.0}] * 8, video_id="v")
    ha, hm = [c["hash"] for c in chunk_plan(a, 10)], [c["hash"] for c in chunk_plan(m, 10)]
    assert len(ha) == len(hm) and all(x != y for x, y in zip(ha, hm))                          # another presence, another picture
    locals_ = [json.dumps(chunk_timeline(m, c["lo"], c["hi"])["watermark"]["windows"]) for c in chunk_plan(m, 10)]
    assert len(set(locals_)) > 1                                                                 # what is hashed is the chunk's own appearances: a chunk with the mark and one without never share a segment
    assert hm == [c["hash"] for c in chunk_plan(build_timeline(_plan(8, MOMENTS), [{"duration": 9.0}] * 8, video_id="v"), 10)]


def _mark_strength(img, plain):
    return float(np.abs(np.asarray(img, np.int16) - np.asarray(plain, np.int16)).mean())


def test_frames_show_the_mark_only_in_its_moments_and_chunks_agree_with_the_whole_video():
    tl = build_timeline(_plan(5, MOMENTS), [{"duration": 9.0}] * 5, video_id="v")
    tl["captions"] = False
    plain = {k: v for k, v in tl.items() if k != "watermark"}
    r, rp = Renderer(tl, draft=True), Renderer(plain, draft=True)
    seen = {t: _mark_strength(r.frame_at(t), rp.frame_at(t)) for t in (0.5, 1.5, 3.0, 6.2, 8.0, 15.0)}
    assert seen[0.5] == 0.0 and seen[8.0] == 0.0 and seen[15.0] == 0.0 and seen[3.0] > 0.02      # absent in the first second and between appearances, there in the middle of one
    assert 0.0 < seen[1.5] < seen[3.0] and 0.0 < seen[6.2] < seen[3.0]                          # the fades
    wins = tl["watermark"]["windows"]
    assert len(wins) >= 2
    second = wins[1]
    c = next(c for c in chunk_plan(tl, 10) if tl["scenes"][c["lo"]]["start"] <= second[0] + 2.0 < tl["scenes"][c["hi"] - 1]["start"] + tl["scenes"][c["hi"] - 1]["duration"])
    sub = chunk_timeline(tl, c["lo"], c["hi"])
    sub["captions"] = False
    base = tl["scenes"][c["lo"]]["start"]
    rc = Renderer(sub, draft=True)
    for t in (second[0] + 0.3, second[0] + 2.0, second[1] - 0.2, second[1] + 1.0):
        if base <= t < base + sub["duration"]:
            assert _mark_strength(rc.frame_at(t - base), r.frame_at(t)) < 0.01                  # the chunk on its own draws the frame the whole video draws: no pop at a boundary


def test_an_always_on_mark_is_there_for_the_whole_video_as_before():
    tl = build_timeline(_plan(4, ALWAYS), [{"duration": 9.0}] * 4, video_id="v")
    tl["captions"] = False
    r, rp = Renderer(tl, draft=True), Renderer({k: v for k, v in tl.items() if k != "watermark"}, draft=True)
    assert all(_mark_strength(r.frame_at(t), rp.frame_at(t)) > 0.02 for t in (1.0, 8.0, 15.0, 30.0))


# ---------------------------------------------------------------- who gets what
def test_a_free_account_under_the_policy_always_gets_the_lockup_for_the_whole_video_with_the_closing_card():
    f = dict(premium=False, forced=True, has_logo=False)
    want = {"mode": "videomk", "style": "lockup", "presence": "always", "end_card": True, "position": "auto", "size": "small", "opacity": 0.65}
    for requested in (None, {"mode": "none"}, {"mode": "videomk", "style": "mark"}, {"mode": "videomk", "presence": "moments"}, {"mode": "videomk", "opacity": 0.2, "size": "medium", "position": "tr", "end_card": False}):
        for profile in (None, {"mode": "none"}, {"mode": "videomk", "presence": "moments", "opacity": 0.2}, {"mode": "custom"}):
            assert store.resolve(requested, profile, **f) == want
    with pytest.raises(store.WatermarkError):                                                    # asking outright for your own logo is still answered with the reason
        store.resolve({"mode": "custom"}, None, **f)


def test_a_premium_account_chooses_and_its_videomk_mark_comes_and_goes_by_default():
    p = dict(premium=True, forced=False, has_logo=True)
    assert store.resolve({"mode": "videomk"}, None, **p)["presence"] == "moments"
    assert store.resolve(None, {"mode": "videomk", "style": "lockup", "end_card": True}, **p)["presence"] == "moments"
    assert store.resolve({"mode": "videomk", "presence": "always"}, None, **p)["presence"] == "always"
    assert store.resolve({"mode": "none"}, {"mode": "videomk"}, **p) == {"mode": "none"}
    assert store.resolve({"mode": "custom"}, None, **p)["mode"] == "custom" and "presence" not in store.resolve({"mode": "custom"}, None, **p)
    assert store.resolve(None, None, **p) == {"mode": "none"}                                    # nothing saved, nothing asked: no mark (the owner's account has a saved default)
    free = dict(premium=False, forced=False, has_logo=False)                                     # a stage without the policy: as it always was
    assert "presence" not in store.resolve({"mode": "videomk"}, None, **free) and store.resolve({"mode": "videomk", "presence": "moments"}, None, **free)["presence"] == "moments"


def test_capabilities_say_what_is_forced_and_what_can_be_chosen(monkeypatch):
    monkeypatch.setenv("FORCE_WATERMARK", "1")
    monkeypatch.setattr(store, "is_premium", lambda user, *a, **k: False)
    c = store.capabilities("user-0001")
    assert c["forced"] is True and c["forced_watermark"] == store.FORCED_SPEC and c["default_presence"] == "always" and c["forced_note"]
    assert {m["id"]: m["available"] for m in c["modes"]} == {"none": False, "videomk": True, "custom": False}
    assert {m["id"]: m["available"] for m in c["presences"]} == {"always": True, "moments": False} and {m["id"]: m["available"] for m in c["style_options"]} == {"mark": False, "lockup": True}
    monkeypatch.setattr(store, "is_premium", lambda user, *a, **k: True)
    c = store.capabilities("user-0001", "es")
    assert c["forced"] is False and "forced_watermark" not in c and c["default_presence"] == "moments"
    assert all(m["available"] for m in c["modes"] + c["presences"] + c["style_options"]) and [m["label"] for m in c["presences"]] == ["Siempre visible", "De vez en cuando"]
    monkeypatch.setenv("FORCE_WATERMARK", "0")
    monkeypatch.setattr(store, "is_premium", lambda user, *a, **k: False)
    c = store.capabilities("user-0001")
    assert c["forced"] is False and all(m["available"] for m in c["presences"]) and c["default_presence"] == "always"


def test_the_settings_api_refuses_what_the_policy_forbids(monkeypatch):
    import watermark_api
    monkeypatch.setenv("FORCE_WATERMARK", "1")
    for body in ({"mode": "none"}, {"mode": "videomk", "presence": "moments"}):
        with pytest.raises(store.WatermarkError) as e:
            watermark_api._clean(body, premium=False)
        assert e.value.status == 403 and e.value.code == "watermark_required" and i18n.t(e.value.key, "es") != i18n.t(e.value.key, "en")
    assert watermark_api._clean({"mode": "videomk"}, premium=False)["mode"] == "videomk"
    assert watermark_api._clean({"mode": "videomk", "presence": "moments"}, premium=True)["presence"] == "moments" and watermark_api._clean({"mode": "none"}, premium=True) == {"mode": "none"}
    with pytest.raises(store.WatermarkError):
        watermark_api._clean({"mode": "videomk", "presence": "often"}, premium=True)


def test_every_new_string_is_in_english_and_spanish():
    for key in ("wm.required", "wm.style.mark", "wm.style.lockup", "wm.presence.always", "wm.presence.always_note", "wm.presence.moments", "wm.presence.moments_note", "wm.forced_note"):
        assert i18n.t(key, "en") != key and i18n.t(key, "es") != i18n.t(key, "en")


def test_the_policy_is_on_in_both_stages_and_the_stack_reads_it():
    stages = json.load(open(os.path.join(ROOT, "stages.json")))
    assert stages["qa"].get("forceWatermark") is True and stages["prod"].get("forceWatermark") is True
    src = open(os.path.join(ROOT, "backend_stack.py"), encoding="utf-8").read()
    assert 'stage_cfg.get("forceWatermark")' in src and 'try_get_context("forceWatermark") is not None' in src   # stages.json decides unless -c forceWatermark=0|1 says otherwise
