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
