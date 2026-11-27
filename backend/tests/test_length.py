"""The length of a video kept by arithmetic (engine/length.py): the estimate of the speaking time, the cut of a script that would run long (whole sentences,
then a surplus beat; never the opening or the last line), the shortened silences once the audio is measured, the pace remembered for edits, and the window
[asked, asked + 5 percent] from 15 seconds to 5 minutes in English and Spanish."""
import copy
import json

import pytest

from engine import awsio, director, length as L, plan as plan_mod, timeline as T
from engine.handlers import timeline_handler
from engine.timeline import build_timeline
from tests.test_skills import _ask_small

EN = ["The tide follows the moon across the sky.", "Water piles up on the side that faces it.", "A second bulge forms on the far side of the planet.",
      "Twice a day the coast meets one of them.", "The sun adds its own, smaller pull.", "When both line up the tides run highest.",
      "Bays and channels can double the height.", "Sailors have timed their trips by it for 3,000 years."]
ES = ["La marea sigue a la luna por el cielo.", "El agua se acumula en la cara que la mira.", "Un segundo abultamiento aparece al otro lado del planeta.",
      "Dos veces al día la costa se encuentra con uno.", "El sol añade su propia fuerza, más pequeña.", "Cuando ambos se alinean las mareas son más altas.",
      "Las bahías y los canales pueden duplicar la altura.", "Los marineros llevan 3.000 años navegando con ella."]


def _beat(i, text, **extra):
    return {"id": f"b{i}", "narration": text, "scene": {"type": "title", "props": {"title": "Tides", "subtitle": ""}}, **extra}


def _plan(texts, language="en", voice=None, **extra):
    return {"title": "Tides", "language": language, "voices": {"narrator": voice or ("Ruth" if language == "en" else "Lupe")}, "theme": "midnight",
            "beats": [_beat(i, t) for i, t in enumerate(texts)], **extra}


def _script(seconds, language="en", share=1.0, beats=None):
    """A plan whose ESTIMATED length is about `share` of `seconds`: beats of whole sentences, about 10 s each."""
    pool = EN if language == "en" else ES
    n = beats or plan_mod.expected_beats(seconds / 60.0)
    plan = _plan([""] * n, language)
    i = 0
    while L.estimate_total(plan) < seconds * share:
        b = plan["beats"][i % n]
        b["narration"] = (b["narration"] + " " + pool[i % len(pool)]).strip()
        i += 1
    assert all(b["narration"] for b in plan["beats"])
    return plan


def _speech(plan, factor=1.0):
    """What the voice 'really' took: the estimate times a factor (the voice is never exactly the estimate)."""
    return [{"duration": round(L.estimate_speech(b["narration"], plan["language"], plan["voices"]["narrator"]) * factor, 3)} for b in plan["beats"]]


# ------------------------------------------------------------------ the estimate
def test_the_estimate_follows_the_text_and_the_voice():
    s = "Sunlight enters a raindrop, bends, reflects off the back, and bends again as it leaves."
    assert L.estimate_speech("") == 0.0 and L.estimate_speech("   ") == 0.0
    assert 5.5 < L.estimate_speech(s, "en", "Ruth") < 7.0                                  # about 15 words at 2.6 words a second, plus four pauses
    assert L.estimate_speech(s + " " + s, "en", "Amy") == pytest.approx(2 * L.estimate_speech(s, "en", "Amy") + L.RATES["Amy"][0], abs=1e-6)
    assert L.estimate_speech("In 1969 it landed.", "en") > L.estimate_speech("In that it landed.", "en")   # a number is spoken long
    assert L.rate_for("es", "Lucia") == L.RATES["Lucia"] and L.rate_for("es-MX", "Nobody") == L.LANG_RATES["es"] and L.rate_for(None, None) == L.LANG_RATES["en"]
    assert L.estimate_speech("uno, dos, tres.", "es", "Lucia") != L.estimate_speech("uno, dos, tres.", "es", "Lupe")


def test_sentences_are_whole_and_short_pieces_stay_with_a_neighbour():
    assert L.sentences("One two three four. Five six seven eight! Nine ten eleven?") == ["One two three four.", "Five six seven eight!", "Nine ten eleven?"]
    assert L.sentences("It costs 3.5 million. That is a lot of money.") == ["It costs 3.5 million.", "That is a lot of money."]
    assert L.sentences("Dr. Smith found it first. Nobody believed her.") == ["Dr. Smith found it first.", "Nobody believed her."]
    assert L.sentences("They waited for hours. No.") == ["They waited for hours. No."]
    assert L.sentences("¿Por qué sube el mar? ¡Por la luna, claro que sí! Así de simple es.") == ["¿Por qué sube el mar?", "¡Por la luna, claro que sí!", "Así de simple es."]
    assert L.sentences('He said "it moves." Then he left the room.') == ['He said "it moves."', "Then he left the room."]
    assert L.sentences("") == [] and L.sentences("one") == ["one"]


def test_the_estimated_total_is_what_the_timeline_builds():
    plan = _script(60)
    tl = build_timeline(plan, _speech(plan), video_id="v")
    assert L.estimate_total(plan) == pytest.approx(tl["duration"], abs=0.05)
    photo = dict(plan, intro_s=2.5, outro_s=3.5)
    assert L.estimate_total(photo) == pytest.approx(build_timeline(photo, _speech(photo), video_id="v")["duration"], abs=0.05)
    pause = copy.deepcopy(plan)
    pause["beats"].insert(2, _beat(99, "", silent=True, hold=4.0))
    assert L.estimate_total(pause) == pytest.approx(L.estimate_total(plan) + 4.0, abs=0.01)
    assert L.estimate_total({"beats": []}) == 0.0


# ------------------------------------------------------------------ the cut before the voice is made
def test_a_script_that_fits_is_never_touched():
    for share in (0.5, 0.9, 1.0):
        plan = _script(60, share=share)
        before = copy.deepcopy(plan)
        rep = L.fit_script(plan, 60)
        assert plan == before and rep["cut_words"] == 0 and rep["fits"] and rep["before"] == rep["after"]
    assert L.fit_script({"beats": []}, 60)["fits"] and L.fit_script(_script(60, share=1.5), 0)["cut_words"] == 0   # no length asked: nothing to keep


@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize("seconds", [15, 30, 45, 60, 120, 180, 300])
@pytest.mark.parametrize("share", [1.08, 1.2, 1.45])
def test_a_long_script_is_cut_to_the_length_by_whole_sentences(language, seconds, share):
    plan = _script(seconds, language, share)
    before = copy.deepcopy(plan)
    rep = L.fit_script(plan, seconds, min_beats=plan_mod.expected_beats(seconds / 60.0))
    assert rep["cut_sentences"] >= 1 and rep["cut_beats"] == 0 and rep["fits"]
    assert rep["after"] == pytest.approx(L.estimate_total(plan), abs=0.06) and rep["after"] < rep["before"]
    assert abs(rep["after"] - seconds) <= max(0.03 * seconds, 2.6)                       # as near the length as one sentence allows (a sentence is about 4 s)
    assert rep["after"] <= seconds * 1.05 + 0.48 * len(plan["beats"])                    # and always within what the pauses can still give back
    first, last = L.sentences(before["beats"][0]["narration"])[0], L.sentences(before["beats"][-1]["narration"])[-1]
    assert plan["beats"][0]["narration"].startswith(first) and plan["beats"][-1]["narration"].endswith(last)   # the hook and the last line stay
    for b, o in zip(plan["beats"], before["beats"]):
        kept, had = L.sentences(b["narration"]), iter(L.sentences(o["narration"]))
        assert len(b["narration"].split()) >= 6 and all(any(s == h for h in had) for s in kept)   # only whole sentences went, the rest in their order, nothing added
    assert rep["cut_words"] == sum(len(o["narration"].split()) - len(b["narration"].split()) for b, o in zip(plan["beats"], before["beats"]))
    again = copy.deepcopy(before)
    assert L.fit_script(again, seconds, min_beats=plan_mod.expected_beats(seconds / 60.0)) == rep and again == plan   # the same script is always cut the same way


def test_the_cut_prefers_the_middle_and_stops_at_the_nearest_point():
    a, b, c = "The tide follows the moon across the sky.", "The tide follows the moon across the sea.", "The tide follows the moon across the bay."   # equal length: only the place differs
    plan = _plan([f"{a} {b} {c}"] * 3)
    total = L.estimate_total(plan)
    rep = L.fit_script(plan, total / 1.1)                                    # ten percent long: one sentence of nine is the nearest cut
    assert rep["cut_sentences"] == 1 and rep["cut_words"] == 8 and rep["after"] == pytest.approx(L.estimate_total(plan), abs=0.06)
    assert [b_["narration"] for b_ in plan["beats"]] == [f"{a} {b} {c}", f"{a} {c}", f"{a} {b} {c}"]   # the middle sentence of the middle beat
    plan = _plan([f"{a} {b} {c}"] * 3)
    rep = L.fit_script(plan, total / 1.6)                                    # far too long: sentences go until one more would overshoot
    assert rep["cut_sentences"] in (3, 4) and abs(rep["after"] - total / 1.6) < 2.0
    assert plan["beats"][0]["narration"].startswith(a) and plan["beats"][2]["narration"].endswith(c)


def test_a_surplus_beat_goes_when_no_sentence_can():
    one = "The tide follows the moon across the whole sky and piles the water up on the side of the planet that faces it."   # one sentence a beat: nothing to trim
    plan = _plan([one] * 4)
    plan["beats"][2]["chapter"] = "Why"
    rep = L.fit_script(plan, 24, min_beats=3)                                                # about 31 s of script in 4 beats, and room for 3
    assert rep["cut_sentences"] == 0 and rep["cut_beats"] == 1 and [b["id"] for b in plan["beats"]] in (["b0", "b2", "b3"], ["b0", "b1", "b3"]) and rep["cut_words"] == len(one.split())
    assert any(b.get("chapter") == "Why" for b in plan["beats"])                             # a chapter that started on the beat that went starts on the next one
    kept = _plan([one] * 4)
    assert L.fit_script(kept, 24, min_beats=4)["cut_beats"] == 0 and len(kept["beats"]) == 4  # never below the beats the length should have
    photos = _plan([one] * 4)
    rep = L.fit_script(photos, 24, min_beats=3, drop_beats=False)                            # a beat that carries the person's photo is never dropped
    assert rep["cut_beats"] == 0 and len(photos["beats"]) == 4 and rep["fits"] is False       # and the report says the script does not fit
    talk = _plan([one] * 4)
    for b in talk["beats"][1:3]:
        b["speaker"] = "maya"
    assert L.fit_script(talk, 24, min_beats=3)["cut_beats"] == 0                             # a dialogue line is somebody's turn
    pause = _plan([one, one, one])
    pause["beats"].insert(1, _beat(9, "", silent=True, hold=5.0))
    assert L.fit_script(pause, 22, min_beats=2)["cut_beats"] == 1
    assert any(b.get("silent") for b in pause["beats"])                                      # a pause is never the beat that goes


def test_a_beat_is_never_left_with_too_few_words():
    plan = _plan(["A long opening line that sets the whole scene for the viewer. No way.", "Tides rise. " + " ".join(EN[:4]), EN[7] + " " + EN[6]])
    L.fit_script(plan, 15, min_beat_words=6)
    assert all(len(b["narration"].split()) >= 6 for b in plan["beats"])


# ------------------------------------------------------------------ the pauses, with the measured audio
def test_tighten_leaves_a_video_inside_the_window_alone_and_never_goes_under_the_floors():
    assert L.tighten(6, 61.0, 60, 0.40, 0.55) == (0.40, 0.55) and L.tighten(6, 61.8, 60, 0.40, 0.55) == (0.40, 0.55)
    lead, tail = L.tighten(6, 63.0, 60, 0.40, 0.55)                       # 1.2 s to give back over 6 beats
    assert L.LEAD_FLOOR < lead < 0.40 and L.TAIL_FLOOR < tail < 0.55 and 6 * ((0.40 - lead) + (0.55 - tail)) == pytest.approx(1.2, abs=0.02)
    assert L.tighten(6, 80.0, 60, 0.40, 0.55) == (L.LEAD_FLOOR, L.TAIL_FLOOR)
    assert L.tighten(0, 80.0, 60, 0.40, 0.55) == (0.40, 0.55) and L.tighten(6, 80.0, 0, 0.40, 0.55) == (0.40, 0.55)
    assert L.clean_pace({"lead": 0.3, "tail": 0.4}, 0.40, 0.55) == (0.3, 0.4) and L.clean_pace({"lead": 0.01, "tail": 9}, 0.40, 0.55) == (L.LEAD_FLOOR, 0.55)
    assert L.clean_pace(None, 0.40, 0.55) == (0.40, 0.55) and L.clean_pace({"lead": "x"}, 0.40, 0.55) == (0.40, 0.55)


def test_the_timeline_shortens_the_silences_and_the_words_move_with_them():
    plan = _script(60, share=1.0)
    slow = _speech(plan, 1.07)                                             # the voice took 7 percent longer than estimated
    plain = build_timeline(plan, slow, video_id="v")
    tl = build_timeline(plan, slow, video_id="v", fit_seconds=60, min_seconds=60)
    assert plain["duration"] > 63.0 and "pace" not in plain
    assert 60.0 <= tl["duration"] <= 63.0 and tl["pace"]["lead"] < T.LEAD and tl["pace"]["tail"] < T.TAIL
    for sc, p, info in zip(tl["scenes"], plain["scenes"], slow):
        assert sc["narration_offset"] == pytest.approx(tl["pace"]["lead"]) and sc["words"][0][1] == pytest.approx(tl["pace"]["lead"], abs=0.01)   # the voice and its captions start together, earlier
        assert sc["duration"] < p["duration"] and sc["duration"] >= tl["pace"]["lead"] + info["duration"] + tl["pace"]["tail"] - 0.001              # never into the words
    fast = build_timeline(plan, _speech(plan, 0.9), video_id="v", fit_seconds=60, min_seconds=60)
    assert 60.0 <= fast["duration"] <= 63.0 and "pace" not in fast          # a short video is held longer instead (the step that was already there)


def test_an_edit_keeps_the_pace_of_its_video():
    plan = _script(60, share=1.0)
    slow = _speech(plan, 1.07)
    first = build_timeline(plan, slow, video_id="v", fit_seconds=60, min_seconds=60)
    edited = build_timeline(dict(plan, pace=first["pace"]), slow, video_id="v")           # a later render: no fitting, the stored pace
    assert edited["pace"] == first["pace"] and [s["narration_offset"] for s in edited["scenes"]] == [s["narration_offset"] for s in first["scenes"]]
    assert build_timeline(dict(plan, pace={"lead": -5, "tail": "x"}), slow, video_id="v").get("pace") is None   # nonsense in the plan: the normal silences


def _run(monkeypatch, plan, speech, rev=1):
    store = {"generation/v2/v1/plan.json": copy.deepcopy(plan)}
    monkeypatch.setattr(awsio, "get_json", lambda k: copy.deepcopy(store[k]))
    monkeypatch.setattr(awsio, "put_json", lambda k, o: store.__setitem__(k, copy.deepcopy(o)))
    beats = [{"id": b["id"], "media": {"duration": s["duration"], "audio_key": f"generation/v2/v1/audio/{b['id']}.mp3"}} for b, s in zip(plan["beats"], speech)]
    out = timeline_handler.handler({"video_id": "v1", "user_id": "u1", "plan_key": "generation/v2/v1/plan.json", "rev": rev, "mode": "final", "beats": beats}, None)
    return store[out["timeline_key"]], store["generation/v2/v1/plan.json"]


def test_the_first_render_stores_the_pace_in_the_plan_and_later_renders_use_it(monkeypatch):
    plan = dict(_script(60, share=1.0), target_seconds=60)
    slow = _speech(plan, 1.07)
    tl, saved = _run(monkeypatch, plan, slow)
    assert 60.0 <= tl["duration"] <= 63.0 and saved["pace"] == tl["pace"] and saved["pace"]["lead"] < T.LEAD
    tl2, saved2 = _run(monkeypatch, saved, slow, rev=2)
    assert tl2["pace"] == tl["pace"] and saved2["pace"] == saved["pace"] and tl2["duration"] == pytest.approx(tl["duration"], abs=0.01)
    ok, kept = _run(monkeypatch, plan, _speech(plan, 1.0))                  # nothing to tighten: nothing stored
    assert "pace" not in ok and "pace" not in kept
    monkeypatch.setenv("FIT_TO_TARGET", "0")
    off, _ = _run(monkeypatch, plan, slow)
    assert "pace" not in off and off["duration"] > 63.0                    # the switch: the timeline as it was


# ------------------------------------------------------------------ the window, end to end
@pytest.mark.parametrize("language", ["en", "es"])
@pytest.mark.parametrize("seconds", [15, 30, 45, 60, 90, 120, 180, 300])
@pytest.mark.parametrize("share", [0.75, 0.95, 1.1, 1.3])
@pytest.mark.parametrize("voice", [0.92, 1.0, 1.06])
def test_from_15_seconds_to_5_minutes_the_video_lands_in_the_window(language, seconds, share, voice):
    """Whatever the writer delivered (25 percent short to 30 percent long) and with a voice 8 percent faster to 6 percent slower than the estimate, the video is
    never shorter than asked and at most 5 percent longer."""
    plan = _script(seconds, language, share)
    L.fit_script(plan, seconds, min_beats=plan_mod.expected_beats(seconds / 60.0))
    tl = build_timeline(plan, _speech(plan, voice), video_id="v", fit_seconds=seconds, min_seconds=seconds)
    assert seconds <= tl["duration"] <= seconds * 1.05 + 0.01, (tl["duration"], tl.get("pace"))


# ------------------------------------------------------------------ the director
def _big(texts):
    def big(system, user):
        return json.dumps({"legit": True, "title": "How tides work", "description": "d", "mood": "calm", "theme": "midnight", "voices": {"narrator": "Ruth"},
                           "beats": [{"narration": t, "scene": {"type": "title", "props": {"title": "x"}}} for t in texts]})
    return big


def test_the_director_cuts_a_long_script_and_says_so(monkeypatch):
    long = [" ".join(EN[:4]), " ".join(EN[2:6]), " ".join(EN[4:8])]          # about 38 s of script for a 30 s video, whatever the repair asks
    out = director.direct("how tides work", minutes=0.5, ask_small=_ask_small(["explainer-education"]), ask_big=_big(long), language="en")
    rep = out["research"]["length"]
    assert rep["target"] == 30.0 and rep["before"] > 36 and rep["after"] <= 31.5 and rep["cut_sentences"] >= 2 and rep["fits"]
    assert any(w.startswith("length: estimated") for w in out["warnings"])
    assert L.estimate_total(out["plan"]) == pytest.approx(rep["after"], abs=0.06)
    assert out["plan"]["beats"][-1]["narration"].endswith(EN[7])
    monkeypatch.setenv("FIT_TO_TARGET", "0")
    off = director.direct("how tides work", minutes=0.5, ask_small=_ask_small(["explainer-education"]), ask_big=_big(long), language="en")
    assert "length" not in off["research"] and sum(len(b["narration"].split()) for b in off["plan"]["beats"]) > sum(len(b["narration"].split()) for b in out["plan"]["beats"])


def test_the_director_leaves_a_script_of_the_right_length_alone():
    texts = [" ".join(EN[:2]), " ".join(EN[2:4]), " ".join(EN[6:8])]
    out = director.direct("how tides work", minutes=0.5, ask_small=_ask_small(["explainer-education"]), ask_big=_big(texts), language="en")
    assert "length" not in out["research"] and [b["narration"] for b in out["plan"]["beats"]] == texts
    assert not any(w.startswith("length:") for w in out["warnings"])
