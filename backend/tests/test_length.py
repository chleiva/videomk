import json

import pytest

from engine import plan as plan_mod
from engine.handlers import plan_handler


def beats_json(n, words_each):
    text = " ".join(["word"] * words_each)
    return json.dumps({"legit": True, "title": "All about Paris", "description": "d", "voices": {"narrator": "Ruth"},
                       "beats": [{"narration": f"Beat {i} " + text, "scene": {"type": "title", "props": {"title": f"T{i}"}}} for i in range(n)]})


def test_the_targets_come_from_the_measured_speaking_rate():
    assert plan_mod.expected_beats(5) == 21 and plan_mod.expected_beats(1) == 4 and plan_mod.expected_beats(1, 9) == 9
    w5 = plan_mod.expected_words(5)
    assert 650 <= w5 <= 700                                                                  # (300 s - 21 beats x 0.95 s) x 2.4 words per second
    assert plan_mod.expected_words(1) < 140 < plan_mod.expected_words(2) < plan_mod.expected_words(3)
    # the real case: 326 words in 15 beats made 150 s (136 s of speech) = 2.4 words per second
    assert 326 / 2.4 + 15 * 0.95 == pytest.approx(150, abs=1)


def test_the_prompt_makes_the_length_a_hard_requirement_with_numbers():
    p = plan_mod.build_user_prompt("All about Paris", "", 5)
    assert "hard requirement" in p and "5 minute" in p and "at least 21 beats" in p and "pays per minute" in p
    lo, hi = int(plan_mod.expected_words(5) * 0.9), int(plan_mod.expected_words(5) * 1.1)
    assert f"between {lo} and {hi} words" in p


def test_a_script_far_too_short_for_the_length_asked_is_found():
    short = {"beats": [{"narration": " ".join(["w"] * 22)} for _ in range(15)]}                 # the real Paris plan: 330 words for 5 minutes
    msg = plan_mod.length_problem(short, 5)
    assert msg and "330 words" in msg and "5-minute" in msg and "at least 21 beats" in msg
    ok = {"beats": [{"narration": " ".join(["w"] * 33)} for _ in range(21)]}
    assert plan_mod.length_problem(ok, 5) is None
    assert plan_mod.length_problem({"beats": [{"narration": "a b c"}]}, 1) is None                # a one-minute plan is not policed
    silent = {"beats": ok["beats"] + [{"narration": "", "silent": True, "hold": 4}]}
    assert plan_mod.spoken_words(silent["beats"]) == 21 * 33                                      # pauses add no words and are not counted


def test_the_planner_gets_up_to_two_repairs_for_a_short_long_video_and_stops_when_it_is_long_enough():
    seen = []
    answers = iter([beats_json(15, 22), beats_json(18, 28), beats_json(21, 33)])
    plan, warns = plan_mod.generate_plan("All about Paris", "", 5, lambda s, u: (seen.append(u), next(answers))[1])
    assert len(seen) == 3 and "words but a 5-minute video needs about" in seen[1]
    assert plan_mod.spoken_words(plan["beats"]) >= 0.85 * plan_mod.expected_words(5) and not any(w.startswith("length:") for w in warns)
    seen.clear()
    plan, warns = plan_mod.generate_plan("All about Paris", "", 5, lambda s, u: (seen.append(u), beats_json(21, 33))[1])
    assert len(seen) == 1                                                                         # long enough the first time: no extra call


def test_a_script_that_stays_short_is_accepted_with_a_logged_warning_not_looped_forever():
    seen = []
    plan, warns = plan_mod.generate_plan("All about Paris", "", 5, lambda s, u: (seen.append(u), beats_json(15, 22))[1])
    assert len(seen) == 3 and plan["beats"] and any(w.startswith("length:") for w in warns)


def test_the_planner_has_room_for_a_long_script():
    assert plan_handler.plan_max_tokens(1) == 8600 and plan_handler.plan_max_tokens(5) == 19000 and plan_handler.plan_max_tokens(12) == 32000
    assert plan_handler.plan_max_tokens(5) > 8000                                                  # the old cap that a 5-minute plan plus its thinking could hit


# ---------------------------------------------------------------- a video is never shorter than the length asked
from engine import timeline as tl_mod


def _plan(n=10, silent_at=()):
    beats = [{"id": f"b{i}", "narration": "" if i in silent_at else "word " * 20, "silent": i in silent_at, "hold": 4 if i in silent_at else None,
              "scene": {"type": "image" if i in silent_at else "title", "props": {"image_query": "x", "title": "t"}}} for i in range(n)]
    return {"beats": beats, "mood": "calm", "theme": "paper"}


def _infos(plan, speech=8.0):
    return [{"duration": (4.0 if b.get("silent") else speech)} for b in plan["beats"]]


def test_a_short_video_is_stretched_to_the_length_asked_and_never_past_a_few_seconds_over():
    plan = _plan(10)
    base = tl_mod.build_timeline(plan, _infos(plan), video_id="v")["duration"]                    # 10 x (0.4 + 8 + 0.55) + 1.4 = 90.9
    want = base + 14
    t = tl_mod.build_timeline(plan, _infos(plan), video_id="v", min_seconds=want)
    assert want <= t["duration"] <= want + tl_mod.MIN_VIDEO_MARGIN + 0.01
    assert sum(s["duration"] for s in t["scenes"]) == pytest.approx(t["duration"], abs=0.01)
    assert all(a["start"] < b["start"] for a, b in zip(t["scenes"], t["scenes"][1:]))              # scenes stay contiguous and in order
    # nothing already tied to a word moves: only the tail of each scene grows
    plain = tl_mod.build_timeline(plan, _infos(plan), video_id="v")
    assert t["scenes"][0]["words"] == plain["scenes"][0]["words"]


def test_a_video_already_long_enough_is_left_alone():
    plan = _plan(10)
    base = tl_mod.build_timeline(plan, _infos(plan), video_id="v")["duration"]
    assert tl_mod.build_timeline(plan, _infos(plan), video_id="v", min_seconds=base - 5)["duration"] == base


def test_stretching_spreads_first_over_speech_then_pauses_then_the_last_scene():
    d = [10.0, 10.0, 4.0, 10.0]
    s = [False, False, True, False]
    small = tl_mod.stretch_to(d, s, sum(d) + 3 - tl_mod.MIN_VIDEO_MARGIN)
    assert small == [11.0, 11.0, 4.0, 11.0]                                                         # 1 s on each spoken scene
    big = tl_mod.stretch_to(d, s, sum(d) + 10)
    assert big[0] == big[1] == 11.6 and big[2] > 4.0 and sum(big) >= sum(d) + 10                   # speech capped at +1.6, then the pause is held longer
    huge = tl_mod.stretch_to(d, s, sum(d) + 60)
    assert sum(huge) >= sum(d) + 60 and huge[2] == 8.0                                              # pauses stop at the hold limit; the rest goes to the end


def test_the_plan_handler_records_the_length_asked_and_only_a_first_render_is_stretched():
    import inspect
    from engine.handlers import plan_handler, timeline_handler
    assert 'plan["target_seconds"] = round(minutes * 60)' in inspect.getsource(plan_handler)
    src = inspect.getsource(timeline_handler)
    assert "min_seconds=" in src and "if rev == 1 and" in src                                  # an edit may legitimately make the video shorter


# ---------------------------------------------------------------- the big word is about the subject, never the pause
def test_a_big_word_that_names_the_pause_is_dropped_in_any_language():
    for w in ("Silence", "SILENCE", "silence.", "Breathe", "Quiet", "Silencio", "Pausa", "Stille", "Silêncio", "Silenzio", "Take a breath"):
        assert plan_mod._word_prop({"word": w}) == {}, w
    assert plan_mod._word_prop({"word": "Paris"}) == {"word": "Paris"}
    assert plan_mod._word_prop({"word": "1889"}) == {"word": "1889"}
    assert plan_mod._word_prop({"word": "Seine"}) == {"word": "Seine"}


def test_the_prompt_does_not_invite_a_title_about_silence():
    s = plan_mod.system_prompt("en", None)
    assert "SILENT" not in s and "Never a word about the pause or sound" in s and '"silence"' in s


def test_a_silent_beat_with_a_meta_word_keeps_its_picture_but_loses_the_word():
    raw = {"legit": True, "title": "T", "description": "d", "voices": {"narrator": "Ruth"}, "beats": [
        {"narration": "A first idea about rivers and bridges.", "scene": {"type": "title", "props": {"title": "Rivers"}}},
        {"narration": "", "hold": 4, "scene": {"type": "image", "props": {"image_query": "river at dawn", "word": "Silence"}}},
        {"narration": "And a closing thought on the whole.", "scene": {"type": "title", "props": {"title": "End"}}}]}
    plan, warns = plan_mod.validate_plan(raw)
    silent = [b for b in plan["beats"] if b.get("silent")]
    assert len(silent) == 1 and "word" not in silent[0]["scene"]["props"] and silent[0]["scene"]["type"] == "image"


def test_a_reply_with_text_or_a_second_object_after_the_json_is_still_read():
    good = '{"legit": true, "beats": [{"narration": "hello there"}]}'
    for raw in (good + "\n\nNote: I kept it short.", good + '\n{"extra": 1}', "Here is the plan:\n" + good + "\nHope that helps {really}", "```json\n" + good + "\n```\nThanks"):
        assert plan_mod.parse_plan_json(raw)["legit"] is True, raw
    with pytest.raises(ValueError):
        plan_mod.parse_plan_json("I cannot help with that {not json")


# ---------------------------------------------------------------- the director decides pauses and has a reason for each
def test_the_director_prompt_has_the_craft_rules_and_makes_pauses_and_big_words_optional():
    s = plan_mod.system_prompt("en", None)
    for needle in ("hook in the first beat", "Never greet", "One idea per beat", "not decoration", "name its reason", "usually zero in videos under 2 minutes", "optional and rare", "never the narrated sentence"):
        assert needle in s, needle
    assert "include a few" not in s and "SILENT" not in s                                             # nothing tells the model to add pauses to be seasoned


def test_a_pause_keeps_the_directors_reason_and_a_missing_reason_is_fine():
    raw = {"legit": True, "title": "T", "description": "d", "voices": {"narrator": "Ruth"}, "beats": [
        {"narration": "A first idea about rivers and bridges in the city.", "scene": {"type": "title", "props": {"title": "Rivers"}}},
        {"narration": "", "hold": 4, "why": "lets the aerial shot of the old town land", "scene": {"type": "image", "props": {"image_query": "old town from above"}}},
        {"narration": "And a second idea about the markets and the food.", "scene": {"type": "title", "props": {"title": "Markets"}}},
        {"narration": "", "hold": 3, "scene": {"type": "image", "props": {"image_query": "market at dawn"}}},
        {"narration": "A closing thought on the whole city and its people.", "scene": {"type": "title", "props": {"title": "End"}}}]}
    plan, _ = plan_mod.validate_plan(raw)
    pauses = [b for b in plan["beats"] if b.get("silent")]
    assert pauses and pauses[0].get("why") == "lets the aerial shot of the old town land"
    assert all("word" not in b["scene"]["props"] for b in pauses)                                      # no word unless the director chose one


def test_the_staged_prompts_carry_the_arc_hook_and_pause_rules():
    from engine import staged
    assert "never a greeting or an agenda" in staged.outline_system("en", None) and "arc" in staged.outline_system("en", None)
    assert "at most one pause in it" in staged.SECTION_ADDENDUM


# ---------------------------------------------------------------- pauses depend on the kind of video; photo videos open and end on music
def test_the_pause_rule_is_different_for_explanations_and_for_picture_videos():
    s = plan_mod.system_prompt("en", None)
    assert "usually zero in videos under 2 minutes" in s and "Videos built on pictures and mood" in s and "never talk over every picture" in s and "one beat in three" in s


def test_photo_videos_may_spend_one_beat_in_three_on_pauses_others_one_in_four():
    def beats(n):
        out = []
        for i in range(n):
            silent = i % 2 == 1 and 0 < i < n - 1
            out.append({"narration": "" if silent else "words " * 12, "silent": silent, "hold": 4.0 if silent else None, "scene": {"type": "image", "props": {"image_query": "x"}}})
        return out
    a, b = beats(13), beats(13)
    plan_mod.enforce_silence(a, 0.25)
    plan_mod.enforce_silence(b, 0.34)
    assert sum(x.get("silent", False) for x in a) == 3 and sum(x.get("silent", False) for x in b) == 4


def test_a_photo_video_starts_with_music_and_a_picture_before_the_first_word_and_ends_on_music():
    from engine import timeline as tl_mod
    plan = {"beats": [{"id": "aaaaaaa1", "narration": "words " * 20, "scene": {"type": "title", "props": {"title": "t"}}}, {"id": "aaaaaaa2", "narration": "words " * 20, "scene": {"type": "title", "props": {"title": "u"}}}],
            "mood": "calm", "theme": "paper"}
    infos = [{"duration": 6.0, "words": [["hello", 0.0, 0.4], ["there", 0.5, 0.9]]}, {"duration": 6.0}]
    plain = tl_mod.build_timeline(plan, infos, video_id="v")
    with_music = tl_mod.build_timeline({**plan, "intro_s": 2.5, "outro_s": 3.5}, infos, video_id="v")
    assert plain["intro_s"] == 0.0 and plain["outro_s"] == tl_mod.END_HOLD
    assert with_music["intro_s"] == 2.5 and with_music["outro_s"] == 3.5
    s0, p0 = with_music["scenes"][0], plain["scenes"][0]
    assert s0["narration_offset"] == pytest.approx(p0["narration_offset"] + 2.5) and s0["duration"] == pytest.approx(p0["duration"] + 2.5)
    assert s0["words"][0][1] == pytest.approx(p0["words"][0][1] + 2.5)                                      # the first word waits for the intro
    assert with_music["scenes"][1]["duration"] == pytest.approx(plain["scenes"][1]["duration"] + 3.5 - tl_mod.END_HOLD)
    assert with_music["duration"] == pytest.approx(plain["duration"] + 2.5 + 3.5 - tl_mod.END_HOLD)


def test_the_music_comes_up_over_the_opening_and_the_ending_of_a_photo_video(tmp_path, monkeypatch):
    import numpy as np
    from engine import pipeline, media
    seen = {}
    monkeypatch.setattr(media, "mix_audio", lambda *a, **k: seen.update(k))
    tl = {"duration": 30.0, "intro_s": 2.5, "outro_s": 3.5, "scenes": [{"start": 0.0, "duration": 15.0, "narration_offset": 2.9, "type": "title"}, {"start": 15.0, "duration": 15.0, "narration_offset": 0.4, "type": "title"}]}
    pipeline.make_audio(tl, [np.zeros(24000, np.float32)] * 2, str(tmp_path / "o.m4a"))
    assert (0.2, 2.8) in seen["swells"] and (26.8, 29.8) in [(round(a, 1), round(b, 1)) for a, b in seen["swells"]]
    seen.clear()
    pipeline.make_audio({**tl, "intro_s": 0.0, "outro_s": 1.4}, [np.zeros(24000, np.float32)] * 2, str(tmp_path / "p.m4a"))
    assert seen["swells"] == []                                                                          # other videos are unchanged


def test_a_video_of_the_persons_photos_leaves_room_for_the_music_only_opening_and_ending():
    plain, photos = plan_mod.expected_words(2.0, 0), plan_mod.expected_words(2.0, 12)
    beats_p, beats_f = plan_mod.expected_beats(2.0, 0), plan_mod.expected_beats(2.0, 12)
    assert photos == int((120 - plan_mod.PHOTO_FRAME_S - beats_f * plan_mod.BEAT_OVERHEAD_S) * plan_mod.SPOKEN_WORDS_PER_S)
    assert plan_mod.PHOTO_FRAME_S == 6.0 and plain == int((120 - beats_p * plan_mod.BEAT_OVERHEAD_S) * plan_mod.SPOKEN_WORDS_PER_S)
