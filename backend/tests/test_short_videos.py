"""Videos of 15, 30 and 45 seconds (docs/SHORT_VIDEOS.md): lengths, credits, budgets, prompt blocks, platform recommendations."""
import json
import re

import pytest

from common import wallet
from engine import curate, director, format_options as fo, plan as plan_mod
from engine import timeline as tl_mod
from tests.test_hardening import _event, launcher  # noqa: F401  (the fixture)

PROMPT = "A short explainer about how black holes form"
SHORT = [0.25, 0.5, 0.75]


def post(launcher, minutes, **extra):
    return launcher.handler(_event(body={"prompt": PROMPT + extra.pop("tag", ""), "target_minutes": minutes, **extra}), None)


# ---------- validation and credits ----------
@pytest.mark.parametrize("m,code", [(0.24, 400), (0.25, 202), (0.5, 202), (0.75, 202), (12, 402), (12.01, 400), (0, 400), (-1, 400)])   # 12 passes validation (402: the test wallet has 5 credits)
def test_length_edges(launcher, m, code):
    assert post(launcher, m)["statusCode"] == code


def test_short_lengths_are_billed_and_sent_as_asked(launcher):
    before = wallet.balance("u1")["balance"]
    assert post(launcher, 0.25)["statusCode"] == 202
    assert json.loads(launcher.fake.calls[-1]["input"])["target_minutes"] == 0.25 and wallet.balance("u1")["balance"] == before - 1


@pytest.mark.parametrize("seconds,credits", [(15, 1), (30, 1), (45, 1), (60, 1), (61, 2), (120, 2), (121, 3), (720, 12)])
def test_credits_are_started_minutes_minimum_one(seconds, credits):
    assert wallet.credits_for_minutes(seconds / 60) == credits


def test_duplicate_short_request_is_one_video(launcher):
    first = post(launcher, 0.5, client_request_id="short-dup-01")
    again = post(launcher, 0.5, client_request_id="short-dup-01")
    assert first["statusCode"] == 202 and again["statusCode"] == 202 and len(launcher.fake.calls) == 1
    other = post(launcher, 0.25, tag=" again")
    assert other["statusCode"] == 202 and len(launcher.fake.calls) == 2


def test_api_gateway_schema_allows_short_videos():
    src = open("backend_stack.py").read()
    assert re.search(r'"target_minutes": apigw\.JsonSchema\(type=apigw\.JsonSchemaType\.NUMBER, minimum=0\.25, maximum=12\)', src)


# ---------- budgets ----------
def test_beats_and_words_for_short_videos():
    assert [plan_mod.expected_beats(m) for m in SHORT] == [2, 3, 4]
    assert plan_mod.expected_beats(0.25) * plan_mod.BEAT_OVERHEAD_S + plan_mod.SHORT_END_S < 15   # no 4-beat floor that overshoots 15 s
    w = [plan_mod.expected_words(m) for m in SHORT]
    assert 20 <= w[0] < w[1] < w[2] < plan_mod.expected_words(1.0) or w[2] < plan_mod.expected_words(1.0) + 20
    for m, words in zip(SHORT, w):   # the words fill the target (to within the calibration)
        secs = words / plan_mod.SPOKEN_WORDS_PER_S + plan_mod.expected_beats(m) * plan_mod.BEAT_OVERHEAD_S + plan_mod.SHORT_END_S
        assert 0.85 * m * 60 <= secs <= m * 60
    assert plan_mod.expected_beats(1) == 4 and plan_mod.expected_words(1) == int((60 - 4 * plan_mod.BEAT_OVERHEAD_S) * plan_mod.SPOKEN_WORDS_PER_S)   # a minute is unchanged


def test_photo_frame_is_scaled_down_under_a_minute():
    assert plan_mod.photo_frame_s(0.5) == 2.5 == director.SHORT_PHOTO_INTRO_S + director.SHORT_PHOTO_OUTRO_S
    assert plan_mod.photo_frame_s(1) == 6.0 == director.PHOTO_INTRO_S + director.PHOTO_OUTRO_S
    assert plan_mod.expected_words(0.5, 6) == int((30 - 2.5 - 6 * plan_mod.BEAT_OVERHEAD_S) * plan_mod.SPOKEN_WORDS_PER_S * plan_mod.SHORT_WORDS_CALIBRATION)


def test_photo_capacity_at_short_lengths():
    assert curate.max_used(0.25) == 12 and curate.max_used(0.5) == 25 and curate.max_used(0.75) == 38


def test_staged_writer_is_not_used_under_four_minutes():
    from engine import staged
    assert not any(staged.is_staged(m) for m in SHORT + [1, 3, 3.9]) and staged.is_staged(4)


def test_stretch_margin_is_small_for_short_videos():
    out = tl_mod.stretch_to([5.0, 5.0], [False, False], 15)
    assert 15 <= sum(out) <= 15.5
    long_ = tl_mod.stretch_to([20.0, 20.0], [False, False], 120)
    assert 121 <= sum(long_) <= 121.5


def beats(n, words):
    return {"beats": [{"narration": " ".join(["word"] * words), "scene": {"type": "title", "props": {}}} for _ in range(n)]}


def test_repair_loops_at_short_lengths():
    target = plan_mod.expected_words(0.25)
    assert plan_mod.length_problem(beats(2, target // 2), 0.25) is None and plan_mod.long_problem(beats(2, target // 2), 0.25) is None
    assert "15-second" in plan_mod.length_problem(beats(2, 6), 0.25)
    assert "15-second" in plan_mod.long_problem(beats(2, 22), 0.25)
    t30 = plan_mod.expected_words(0.5)
    assert plan_mod.length_problem(beats(3, (t30 // 3) - 4), 0.5) and plan_mod.long_problem(beats(3, (t30 // 3) + 6), 0.5)
    assert plan_mod.length_problem(beats(3, t30 // 3), 0.5) is None and plan_mod.long_problem(beats(3, t30 // 3 + 1), 0.5) is None   # inside the tolerance


# ---------- prompts ----------
def test_short_form_block_and_user_prompt():
    f = plan_mod.frame_prompt(None, 0.25)
    assert "SHORT-FORM" in f and "15 seconds" in f and "first 2 seconds" in f and "call to action ONLY if the request has one" in f and "no timelines" in f
    assert plan_mod.frame_prompt(None, 1) == "" and plan_mod.frame_prompt(None, 3) == "" and plan_mod.frame_prompt({}, None) == ""
    u = plan_mod.build_user_prompt("Why we sleep", "", 0.5)
    assert "30 seconds" in u and str(plan_mod.expected_words(0.5)) in u and "minute(s)" not in u
    assert "2 minute(s)" in plan_mod.build_user_prompt("x", "", 2)


def test_platform_hint_carries_recommendation_and_style_but_the_length_wins():
    p = plan_mod.frame_prompt({"platform": "linkedin", "aspect": "4:5"}, 0.5)
    assert "LinkedIn" in p and "about 1 minute" in p and "the length asked for wins" in p and "professional" in p and "SHORT-FORM" in p
    t = plan_mod.frame_prompt({"platform": "tiktok", "aspect": "9:16"}, 3)
    assert "about 30 seconds" in t and "hook in 2 seconds" in t and "SHORT-FORM" not in t   # a 3-minute TikTok is respected: no short-form rules
    assert "Platform default" not in plan_mod.frame_prompt({"platform": "other", "aspect": "9:16"}, 1)


def test_photo_video_prompt_adds_no_extra_scenes_when_short():
    photos = [{"id": f"P{i}", "caption": "a beach", "orientation": "landscape"} for i in range(1, 4)]
    assert "no extra scenes at all" in plan_mod.photos_prompt(photos, None, 0.5)
    assert "up to 2 non-photo scenes" in plan_mod.photos_prompt(photos, None, 2)


# ---------- capabilities and the platform table ----------
def test_capabilities_lengths_and_platform_fields():
    c = fo.capabilities()
    assert c["lengths"] == {"min_minutes": 0.25, "max_minutes": 12, "presets": [0.25, 0.5, 0.75, 1, 2, 3, 5, 8, 12]}
    for p in c["platforms"]:
        assert {"id", "label", "aspect", "resolution", "note", "recommended_minutes", "max_minutes", "other_aspects"} <= set(p)


def test_platform_table_is_consistent():
    ids = [p["id"] for p in fo.PLATFORMS]
    assert ids == ["youtube", "shorts", "tiktok", "reels", "instagram_feed", "linkedin", "x", "other"] and set(fo.PLATFORM_STYLE) >= set(ids) - {"other"}
    for p in fo.PLATFORMS:
        assert p["recommended_minutes"] in fo.LENGTH_PRESETS
        assert p["aspect"] in fo.ASPECT_IDS and p["resolution"] in fo.RESOLUTION_IDS
        assert all(a in fo.ASPECT_IDS and a != p["aspect"] for a in p["other_aspects"])
        assert p["max_minutes"] is None or p["max_minutes"] >= p["recommended_minutes"]
        secs = round(p["recommended_minutes"] * 60)
        dur = f"{secs} s" if secs < 60 else f"{secs // 60} min"
        assert p["note"].endswith(f"about {dur}") and p["aspect"] in p["note"] and "1080p" in p["note"], p["note"]
    by = {p["id"]: p for p in fo.PLATFORMS}
    assert (by["linkedin"]["aspect"], by["linkedin"]["recommended_minutes"]) == ("4:5", 1)
    assert by["linkedin"]["note"] == "Portrait 4:5 · 1080p · about 1 min"
    assert (by["shorts"]["aspect"], by["shorts"]["recommended_minutes"], by["shorts"]["max_minutes"]) == ("9:16", 0.75, 3)
    assert (by["tiktok"]["recommended_minutes"], by["reels"]["recommended_minutes"], by["x"]["recommended_minutes"]) == (0.5, 0.5, 0.75)
    assert (by["youtube"]["recommended_minutes"], by["youtube"]["max_minutes"], by["other"]["recommended_minutes"]) == (3, None, 3)
