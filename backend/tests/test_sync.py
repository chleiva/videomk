import json
import math
import os
import wave

import numpy as np
import pytest

from engine import align, edits, sync
from engine.renderer import Renderer
from engine.scenes.text_scenes import RING_CLEAR, RING_R, RING_STROKE, ring_text_size
from engine.timeline import LEAD, build_timeline
from tests.test_engine import small_timeline
from tests.test_hardening import launcher  # noqa: F401  (the fixture)

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "speech")


def fixture(name):
    meta = json.load(open(os.path.join(FIX, name + ".json")))
    with wave.open(os.path.join(FIX, name + ".wav"), "rb") as w:
        samples = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    return meta["text"], samples, [m["start"] for m in meta["marks"]]


# ================================================================= alignment against real speech with exact word marks
@pytest.mark.parametrize("name", ["list_joanna", "numbers_matthew", "places_amy", "steps_joanna"])
def test_words_are_placed_from_the_audio_within_a_fraction_of_a_second(name):
    text, samples, truth = fixture(name)
    words, conf = align.align_words(samples, 16000, text)
    assert [w[0] for w in words] == text.split() and conf >= 0.9
    err = np.abs(np.array([w[1] for w in words]) - np.array(truth))
    err = np.abs(err - np.median(err * 0) )                        # onset times are measured from the first sample on both sides: no offset is removed
    old = np.abs(np.array([w[1] for w in align.estimate_words(text, samples.size / 16000)]) - np.array(truth))
    assert err.mean() < 0.13 and np.percentile(err, 90) < 0.3 and err.max() < 0.5, (name, err.mean(), err.max())
    assert err.mean() < old.mean() or err.mean() < 0.09                    # and it is better than the proportional estimate (or already excellent)
    starts = [w[1] for w in words]
    assert all(b >= a for a, b in zip(starts, starts[1:])) and all(w[2] >= w[1] + 0.04 for w in words)


def test_in_a_spoken_list_every_item_lands_on_its_own_word():
    text, samples, truth = fixture("list_joanna")
    words, _ = align.align_words(samples, 16000, text)
    by = {w[0]: w[1] for w in words}
    for token, true_t in zip(text.split(), truth):
        if token in ("First,", "speed.", "Second,", "cost,", "third,", "quality."):
            assert abs(by[token] - true_t) < 0.16, token                  # list items sit between pauses, so they are anchored exactly


def test_confidence_drops_when_the_audio_does_not_match_the_text():
    text, samples, _ = fixture("list_joanna")
    assert align.align_words(samples, 16000, text)[1] >= 0.9
    # the same sentence but with no punctuation to explain the pauses, and a speaking rate far too high for the audio
    words, conf = align.align_words(samples, 16000, " ".join(["word"] * 120))
    assert conf < 0.7
    assert align.align_words(np.zeros(16000, np.float32), 16000, "hello there") == ([], 0.0) and align.align_words(samples, 16000, "") == ([], 0.0)


def test_syllable_weights_follow_how_long_things_take_to_say():
    w = align.syllable_weight
    assert w("a") < w("table") < w("remember.") < w("extraordinarily")
    assert w("there") == pytest.approx(w("then"), abs=0.6) and w("make") < w("making")           # silent final e is not a syllable
    assert w("73") > w("7") and w("73%") > w("73") and w("$4.2B") > w("$4")                      # digits and symbols are spoken words
    assert w("--") < w("a")                                                                       # bare punctuation takes almost no time


def test_pauses_and_punctuation_are_matched_even_when_counts_differ():
    sr = 16000
    def burst(sec): return (np.random.default_rng(1).standard_normal(int(sr * sec)) * 0.3).astype(np.float32)
    gap = lambda s: np.zeros(int(sr * s), np.float32)
    # three phrases spoken with two clear pauses
    audio = np.concatenate([gap(0.2), burst(1.0), gap(0.4), burst(0.8), gap(0.35), burst(1.2), gap(0.2)])
    words, conf = align.align_words(audio, sr, "One two three. Four five, six seven eight nine.")
    t = {w[0]: (w[1], w[2]) for w in words}
    assert t["Four"][0] == pytest.approx(0.2 + 1.0 + 0.4, abs=0.06) and t["three."][1] == pytest.approx(1.2, abs=0.06)       # the phrase edges sit on the pauses
    # a comma the speaker did not pause at: the boundary is simply left unmatched, nothing breaks
    words2, conf2 = align.align_words(audio, sr, "One two, three. Four five six seven eight nine.")
    assert len(words2) == 9 and conf2 > 0.6


# ================================================================= matching what is shown to what is said
def W(text, step=0.4, start=0.5):
    return [(tok, round(start + i * step, 3), round(start + i * step + 0.3, 3)) for i, tok in enumerate(text.split())]


def test_items_are_found_in_the_narration_in_order_and_unnamed_ones_are_none():
    words = W("Transistors have three jobs. They switch signals, they amplify weak signals, and they remember a state.")
    found = sync.find_mentions(["Switch signals on and off", "Amplify weak signals", "Remember state", "Cool down the chip"], words)
    assert found == [5, 8, 13, None]                                             # "amplify weak signals" starts at "amplify", not at the earlier "signals"
    # stopwords and short words never match: "the", "of" ...
    assert sync.find_mentions(["The of and"], words) == [None]


def test_matching_ignores_accents_plurals_and_works_in_spanish():
    words = W("Primero, la velocidad. Segundo, el costo, y tercero, la calidad.")
    assert sync.find_mentions(["Velocidades", "Costos", "Calidad"], words) == [2, 5, 9]
    assert sync.norm("Fábricas") == sync.norm("fabrica") and sync.norm("Walking") == sync.norm("walks") == "walk"
    assert sync.norm("73%") == sync.norm("73") == "73" and sync.norm("$4.2B") == "4.2" and sync.norm("1,200") == "1200"


def test_numbers_match_digits():
    words = W("Prices rose 73 percent while wages grew 2 percent in 1969.")
    assert sync.find_mentions(["73%", "1969 moon landing"], words)[0] == 2
    assert sync.find_mentions(["1969"], words) == [10]


def test_a_repeated_word_is_matched_after_the_previous_item_not_before_it():
    words = W("Speed matters. Cost matters too. And speed again, but quality matters most.")
    assert sync.find_mentions(["Speed", "Cost", "Quality"], words) == [0, 2, 9]
    assert sync.find_mentions(["Cost", "Speed"], words)[1] == 6                    # the second item is the next mention after the first, not the earlier "Speed"


def test_reveal_times_follow_the_mentions_with_a_small_lead_and_never_collide():
    words = W("First speed. Second cost. Third quality.", step=1.0, start=0.5)
    cues, idx = sync.anchor_times(["Speed", "Cost", "Quality"], words, 8.0)
    assert idx == [1, 3, 5] and cues == pytest.approx([1.5 - 0.15, 3.5 - 0.15, 5.5 - 0.15], abs=0.01)
    close = W("Speed cost quality.", step=0.1, start=0.5)
    cues, _ = sync.anchor_times(["Speed", "Cost", "Quality"], close, 8.0)
    assert all(b - a >= sync.MIN_GAP_S - 1e-6 for a, b in zip(cues, cues[1:]))


def test_an_item_the_narration_never_names_is_interpolated_between_its_neighbours():
    words = W("Speed comes first. Quality comes last.", step=1.0, start=0.5)
    cues, idx = sync.anchor_times(["Speed", "Something unmentioned", "Quality"], words, 9.0)
    assert idx[1] is None and cues[0] < cues[1] < cues[2]
    nothing, idx = sync.anchor_times(["alpha", "beta", "gamma"], words, 9.0)
    assert idx == [None] * 3 and nothing[0] >= 0.15 and nothing[-1] <= words[-1][1]          # spread over the spoken part, never the old fixed schedule
    assert sync.anchor_times(["a b", "c d"], [], 10.0)[0] == pytest.approx([1.0, 7.2])        # no words at all: the old behaviour


def test_each_scene_type_says_what_it_reveals_and_in_which_order():
    assert sync.item_texts("bullets", {"items": ["a", "b"]}) == ["a", "b"]
    d = {"nodes": [{"id": "x", "label": "Sensor"}, {"id": "y", "label": "Brain"}, {"id": "z", "label": "Arm"}], "edges": [["z", "x"], ["x", "y"]]}
    assert sync.diagram_order(d) == ["Arm", "Sensor", "Brain"]                                # revealed by layer, as draw_diagram does
    assert sync.item_texts("timeline", {"events": [{"date": "1969", "label": "Moon landing"}]}) == ["1969 Moon landing"]
    assert sync.item_texts("chart", {"labels": ["2020", "2021"], "values": [1, 2]}) == ["2020", "2021"]
    assert sync.item_texts("gallery", {"image_queries": ["Rome forum", "Pantheon"]}) == ["Rome forum", "Pantheon"]
    assert sync.item_texts("title", {}) == []


def test_apply_writes_cues_cuts_and_stat_cue_into_the_props():
    words = W("Imagine the Colosseum at dawn. Then walk to the Pantheon, and finally the Trevi fountain, where coins fly.", step=0.5)
    gallery = {"image_queries": ["Colosseum dawn", "Pantheon dome", "Trevi fountain"], "alt": "Rome"}
    out = sync.apply("gallery", gallery, words, 12.0)
    assert out == {"items": 3, "anchored": 3} and gallery["cuts"][0] == 0.0 and gallery["cuts"] == sorted(gallery["cuts"]) and gallery["cuts"][1] == pytest.approx(0.5 + 9 * 0.5 + sync.GALLERY_AFTER_S, abs=0.01)
    bullets = {"heading": "Stops", "items": ["Colosseum", "Pantheon", "Trevi fountain"]}
    assert sync.apply("bullets", bullets, words, 12.0) == {"items": 3, "anchored": 3} and bullets["cues"][0] < bullets["cues"][1] < bullets["cues"][2]
    stat = {"value": "73%", "label": "of visitors"}
    assert sync.apply("stat", stat, W("Most visitors, about 73 percent, come in summer."), 8.0)["anchored"] == 1 and stat["cues"][0] > 0.5
    unspoken = {"items": ["x y z"]}
    assert sync.apply("bullets", unspoken, words, 10.0)["anchored"] == 0 and sync.apply("title", {}, words, 10.0) == {}
    crowded = {"image_queries": ["Colosseum dawn", "Pantheon dome"], "alt": ""}
    sync.apply("gallery", crowded, W("Colosseum then the Pantheon.", step=0.3), 2.4)       # the anchored cut leaves the last photo 0.8 s: kept
    assert crowded["cuts"] == [0.0, 1.6]
    tight = {"image_queries": ["Colosseum dawn", "Pantheon dome"], "alt": ""}
    sync.apply("gallery", tight, W("Colosseum then the Pantheon.", step=0.3), 1.2)         # no room for two photos worth seeing: the beat is shared evenly instead
    assert tight["cuts"] == [0.0, 0.6]


# ================================================================= in the timeline
def plan_with(beat_scene, narration, captions=None):
    p = {"beats": [{"id": "b1", "narration": narration, "scene": beat_scene}], "theme": "midnight"}
    if captions is not None:
        p["captions"] = captions
    return p


def test_the_timeline_anchors_reveals_to_the_measured_words_and_reports_it():
    text, samples, _ = fixture("list_joanna")
    words, _ = align.align_words(samples, 16000, text)
    speech = samples.size / 16000
    plan = plan_with({"type": "bullets", "props": {"heading": "Three ideas", "items": ["Speed", "Cost", "Quality"]}}, text)
    tl = build_timeline(plan, [{"duration": speech, "words": [list(w) for w in words]}], video_id="v")
    sc = tl["scenes"][0]
    by = {w[0]: w[1] for w in sc["words"]}
    cues = sc["props"]["cues"]
    assert cues == pytest.approx([by["speed."] - 0.15, by["cost,"] - 0.15, by["quality."] - 0.15], abs=0.01)    # each item arrives just before it is said
    assert sc["words"][0][1] >= LEAD - 0.01 and tl["sync"] == {"items": 3, "anchored": 3, "aligned_beats": 1}
    rep = sync.report(tl)
    assert rep["ok"] and rep["anchored"] == 3 and rep["early"] == 0 and rep["late"] == 0 and all(-0.2 <= r["delta"] <= -0.1 for r in rep["rows"])


def test_without_measured_words_it_still_anchors_to_the_estimate():
    text = "First comes speed. Then cost. Finally quality matters most."
    tl = build_timeline(plan_with({"type": "bullets", "props": {"heading": "x", "items": ["Speed", "Cost", "Quality"]}}, text), [{"duration": 4.5}], video_id="v")
    assert tl["sync"]["anchored"] == 3 and tl["sync"]["aligned_beats"] == 0 and sync.report(tl)["ok"]


def test_the_alignment_check_catches_the_old_fault_of_things_appearing_before_they_are_said():
    text, samples, _ = fixture("list_joanna")
    words, _ = align.align_words(samples, 16000, text)
    plan = plan_with({"type": "bullets", "props": {"heading": "Three ideas", "items": ["Speed", "Cost", "Quality"]}}, text)
    tl = build_timeline(plan, [{"duration": samples.size / 16000, "words": [list(w) for w in words]}], video_id="v")
    sc = tl["scenes"][0]
    dur = sc["duration"]
    sc["props"]["cues"] = [dur * 0.1, dur * 0.1 + (dur * 0.62) / 2, dur * 0.72]                    # the old fixed schedule, ignoring the narration
    rep = sync.report(tl)
    assert not rep["ok"] and rep["early"] >= 1 and rep["rows"][0]["delta"] < -0.5


def test_galleries_cut_when_the_narration_names_the_next_photo():
    text = "Start at the Colosseum, then walk to the Pantheon, and end at the Trevi fountain."
    words = W(text, step=0.55, start=0.3)
    plan = plan_with({"type": "gallery", "props": {"image_queries": ["Colosseum arches", "Pantheon dome", "Trevi fountain"], "alt": "Rome"}}, text)
    tl = build_timeline(plan, [{"duration": 8.0, "words": [[w, s - LEAD, e - LEAD] for w, s, e in words], "gallery": [{"asset": "a.jpg"}, {"asset": "b.jpg"}, {"asset": "c.jpg"}]}], video_id="v")
    cuts = tl["scenes"][0]["props"]["cuts"]
    assert cuts[0] == 0.0 and cuts[1] == pytest.approx(0.3 + 8 * 0.55 + sync.GALLERY_AFTER_S, abs=0.01) and cuts[2] > cuts[1] + sync.MIN_SHOT_S - 0.01
    colors = {"a.jpg": (200, 30, 30), "b.jpg": (30, 200, 30), "c.jpg": (30, 30, 200)}
    from PIL import Image
    r = Renderer({**tl, "captions": False}, lambda key: Image.new("RGB", (2400, 1400), colors[key]))
    pix = lambda t: r.frame_at(t).getpixel((960, 400))
    assert pix(cuts[1] - 0.9)[0] > 150 and pix(cuts[1] + 0.3)[1] > 150 and pix(cuts[2] + 0.3)[2] > 150   # the photo is up when its word is said


def test_the_stat_counts_up_when_its_number_is_spoken_not_before():
    text = "Many people ask how common this is. The answer is 73 percent of everyone surveyed."
    words = W(text, step=0.4, start=0.4)
    plan = plan_with({"type": "stat", "props": {"value": "73%", "label": "of everyone surveyed"}}, text)
    tl = build_timeline(plan, [{"duration": 6.5, "words": [[w, s - LEAD, e - LEAD] for w, s, e in words]}], video_id="v")
    cue = tl["scenes"][0]["props"]["cues"][0]
    assert cue == pytest.approx(0.4 + 10 * 0.4 - 0.35, abs=0.01)
    from engine.theme import get_theme
    r = Renderer({**tl, "captions": False}, None)
    before, after = r.frame_at(cue - 0.5), r.frame_at(cue + 1.8)
    text_rgb = np.array(get_theme("midnight").text[:3])
    count = lambda im: int((np.abs(np.asarray(im, dtype=int)[250:800] - text_rgb).sum(axis=2) < 40).sum())      # pixels in the number's own colour
    assert count(before) < 50 and count(after) > 3000                                                          # nothing of the stat is on screen before its number is spoken


# ================================================================= the percentage ring never overflows
@pytest.mark.parametrize("value", ["100%", "99.9%", "73%", "5%", "100.00%", "88.88%", "0.5%"])
def test_the_number_is_always_inside_the_ring(value):
    from engine.canvas import Canvas
    from engine.scenes.base import CENTER_X, CONTENT_TOP
    from engine.theme import get_theme
    tl = small_timeline(6.0, ["stat"])
    tl["scenes"][0]["props"] = {"value": value, "label": "of people"}
    tl["scenes"][0]["words"] = []
    tl["captions"] = False
    r = Renderer(tl)
    frame = np.asarray(r._draw_spec(tl["scenes"][0], 5.0), dtype=int)                          # fully counted up
    cy = (r.ctx.bottom + CONTENT_TOP) / 2 - 40
    text_rgb = np.array(get_theme("midnight").text[:3])
    ys, xs = np.nonzero(np.abs(frame - text_rgb).sum(axis=2) < 40)                             # the number is drawn in the theme's text colour
    near = (ys > cy - RING_R - 30) & (ys < cy + RING_R + 30)                                   # the label sits below the ring in another colour
    xs, ys = xs[near], ys[near]
    assert xs.size > 500, "the number was not drawn"
    inner = RING_R - RING_STROKE / 2
    dist = np.hypot(xs - CENTER_X, ys - cy)
    assert dist.max() <= inner - RING_CLEAR * 0.5, (value, float(dist.max()), inner)          # no pixel of the number reaches the ring, with clearance
    cv = Canvas(1920, 1080, ss=1)                                                              # and by geometry: the text box's corners are inside the circle
    size = ring_text_size(cv, value)
    assert math.hypot(cv.measure(value, "bold", size) / 2, size * 0.78 / 2) <= RING_R - RING_STROKE / 2 - RING_CLEAR + 1e-6 and size >= 40


def test_a_long_percentage_gets_a_smaller_font_than_a_short_one():
    from engine.canvas import Canvas
    cv = Canvas(1920, 1080, ss=1)
    assert ring_text_size(cv, "5%") > ring_text_size(cv, "100.00%") and ring_text_size(cv, "73%") <= 200


# ================================================================= subtitles are optional
def test_captions_follow_the_creators_choice_and_show_only_when_on():
    text = "Waves roll in slowly over the sand."
    words = W(text, step=0.4, start=0.5)
    scene = {"type": "title", "props": {"title": "Waves", "subtitle": ""}}
    info = [{"duration": 3.5, "words": [[w, s - LEAD, e - LEAD] for w, s, e in words]}]
    on = build_timeline(plan_with(scene, text), info, video_id="v")
    off = build_timeline(plan_with(scene, text, captions=False), info, video_id="v")
    assert on["captions"] is True and off["captions"] is False
    t = 1.6
    on_nowords = build_timeline(plan_with(scene, text), [{"duration": 3.5}], video_id="v")
    on_nowords["scenes"][0]["words"] = []                                                                      # same layout, no caption to draw
    off_nowords = {**off, "scenes": [{**off["scenes"][0], "words": []}]}
    bottom = (slice(900, 1060), slice(300, 1620))
    diff = lambda x, y: np.abs(np.asarray(x, dtype=int) - np.asarray(y, dtype=int))
    d_on = diff(Renderer(on).frame_at(t), Renderer(on_nowords).frame_at(t))
    assert d_on[bottom].sum() > 100_000 and d_on[:700].sum() == 0                                              # subtitles on: the caption pill is drawn, only there
    assert diff(Renderer(off).frame_at(t), Renderer(off_nowords).frame_at(t)).sum() == 0                       # subtitles off: the words change nothing at all


def test_captions_can_be_switched_by_the_editor():
    plan = {"title": "T", "beats": [{"id": "aaaaaaa1", "narration": "x " * 10, "scene": {"type": "title", "props": {"title": "t"}}}]}
    new, _ = edits.apply_ops(plan, [{"op": "set_meta", "captions": False}])
    assert new["captions"] is False
    assert edits.apply_ops(new, [{"op": "set_meta", "captions": True}])[0]["captions"] is True
    with pytest.raises(edits.EditError):
        edits.apply_ops(plan, [{"op": "set_meta", "captions": "no"}])


def test_the_launcher_takes_a_captions_choice(launcher):
    from tests.test_music_images import event
    for ok in (True, False):
        assert launcher.handler(event({"captions": ok}), None)["statusCode"] == 202
        assert json.loads(launcher.fake.calls[-1]["input"])["captions"] is ok
    n = len(launcher.fake.calls)
    for bad in ("false", 0, [True]):
        assert launcher.handler(event({"captions": bad}), None)["statusCode"] == 400
    assert len(launcher.fake.calls) == n


# ================================================================= text fades really fade (the canvas used to ignore text alpha)
def test_text_honours_its_alpha_so_fades_and_hidden_text_work():
    from engine.canvas import Canvas
    peaks = {}
    for a in (0, 40, 128, 255):
        cv = Canvas(400, 200, ss=2)
        cv.im.paste((0, 0, 0), (0, 0, 800, 400))
        cv.text(200, 100, "HELLO", "bold", 80, (255, 255, 255, a), anchor="mm")
        peaks[a] = int(np.asarray(cv.to_rgb()).max())
    assert peaks == {0: 0, 40: 40, 128: 128, 255: 255}                       # alpha 0 draws nothing, alpha 128 is half strength
    cv = Canvas(400, 200, ss=1)
    base = np.asarray(cv.to_rgb()).copy()
    cv.text(200, 100, "", "bold", 80, (255, 255, 255, 200))                  # empty text is harmless
    assert np.array_equal(base, np.asarray(cv.to_rgb()))


def test_a_stat_label_is_not_visible_before_its_turn():
    tl = small_timeline(8.0, ["stat"])
    tl["scenes"][0]["props"] = {"value": "73%", "label": "of everyone surveyed", "cues": [3.0]}
    tl["scenes"][0]["words"] = []
    tl["captions"] = False
    from engine.theme import get_theme
    r = Renderer(tl)
    muted = np.array(get_theme("midnight").muted[:3])
    visible = lambda t: int((np.abs(np.asarray(r.frame_at(t), dtype=int)[800:1000] - muted).sum(axis=2) < 40).sum())
    assert visible(1.0) == 0 and visible(5.5) > 1500                          # the label of the stat appears with the number, not at the start of the scene


# ================================================================= late mentions, and plans whose list items are never spoken
def test_a_photo_named_at_the_very_end_of_a_beat_keeps_its_anchor_without_reordering_the_others():
    words = W("Start at the Colosseum, then the Pantheon is next, and finally right at the very end the Trevi fountain.", step=0.5, start=0.3)
    props = {"image_queries": ["Colosseum", "Pantheon", "Trevi fountain"], "alt": ""}
    dur = words[-1][2] + 0.4
    sync.apply("gallery", props, words, dur)
    cuts = props["cuts"]
    assert cuts[0] == 0.0 and cuts == sorted(cuts) and cuts[1] == pytest.approx(0.3 + 6 * 0.5 + sync.GALLERY_AFTER_S, abs=0.01)    # the second photo keeps its anchor
    assert cuts[2] <= dur - 0.6 and cuts[2] - cuts[1] >= 0.8                                                                          # the last is pulled back just enough to be seen
    assert all(b - a >= 0.8 for a, b in zip(cuts, cuts[1:]))


def beat(narration, stype, props):
    return {"id": "b", "narration": narration, "scene": {"type": stype, "props": props}}


def test_scenes_whose_items_the_narrator_never_says_are_found_before_the_plan_is_accepted():
    ok = beat("First, ask questions. Second, teach others. Third, sleep enough, and fourth, practise daily.", "bullets", {"heading": "h", "items": ["Ask questions", "Teach others", "Sleep enough", "Practise daily"]})
    paraphrase = beat("Fast learners share a few simple habits that anyone can build over time.", "bullets", {"heading": "h", "items": ["Ask questions", "Teach others", "Sleep enough", "Practise daily"]})
    short = beat("Two things matter here.", "bullets", {"heading": "h", "items": ["Alpha thing", "Beta thing"]})          # under three items: not worth a retry
    assert sync.coverage_problems([ok, short]) == []
    gaps = sync.coverage_problems([ok, paraphrase])
    assert len(gaps) == 1 and gaps[0].startswith("beat 2 (bullets)") and "Ask questions" in gaps[0]
    partly = beat("First, ask questions. Then there are other things.", "bullets", {"heading": "h", "items": ["Ask questions", "Teach others", "Sleep enough", "Practise daily"]})
    assert sync.coverage_problems([partly])                                                                                   # 1 of 4 is under the 60 % bar


def test_the_planner_gets_one_repair_when_list_items_are_not_spoken_and_none_when_they_are():
    from engine import plan as plan_mod
    def llm_json(narration):
        return json.dumps({"legit": True, "title": "T", "description": "d", "voices": {"narrator": "Ruth"}, "beats": [
            {"narration": narration, "scene": {"type": "bullets", "props": {"heading": "Habits", "items": ["Ask questions", "Teach others", "Sleep enough"]}}}]})
    bad = llm_json("Fast learners share a few simple habits that anyone can build over time, step by step.")
    good = llm_json("First, ask questions. Second, teach others. Third, sleep enough, because memory needs rest.")
    seen = []
    answers = iter([bad, good])
    plan, _ = plan_mod.generate_plan("habits", "", 1, lambda s, u: (seen.append(u), next(answers))[1])
    assert len(seen) == 2 and "never mentions" in seen[1] and "ask questions" in plan["beats"][0]["narration"].lower()
    seen.clear()
    plan, _ = plan_mod.generate_plan("habits", "", 1, lambda s, u: (seen.append(u), good)[1])
    assert len(seen) == 1                                                                                                    # nothing to repair: no extra model call
    seen.clear()
    plan, _ = plan_mod.generate_plan("habits", "", 1, lambda s, u: (seen.append(u), bad)[1])
    assert len(seen) == 2 and plan["beats"]                                                                                  # still not fixed after the one retry: accepted, the reveals are interpolated
    assert "IN THE ORDER SHOWN" in plan_mod.system_prompt("en")


def test_the_legacy_schedule_is_what_old_videos_are_measured_against():
    assert sync.legacy_cues("bullets", 3, 10.0) == pytest.approx([1.0, 4.1, 7.2]) and sync.legacy_cues("gallery", 3, 9.0) == [0.0, 3.0, 6.0]
    old = {"scenes": [{"id": "s", "type": "bullets", "duration": 10.0, "props": {"items": ["Speed", "Cost", "Quality"]},
                       "words": [["Speed", 0.5, 0.9], ["comes", 1.0, 1.3], ["first,", 1.4, 1.8], ["cost", 2.0, 2.4], ["next,", 2.5, 2.9], ["quality", 3.0, 3.5]]}]}
    rep = sync.report(old)
    assert not rep["ok"] and all(r["legacy"] for r in rep["rows"]) and rep["late"] >= 1                                      # the fixed schedule shows the last item far too late


def test_a_gallery_photo_is_cut_in_when_its_subject_is_named_even_if_the_query_describes_more():
    words = W("Your day starts at the Colosseum. Next, the Roman Forum. Then a pasta lunch, and a walk by the river.", step=0.9, start=0.3)
    props = {"image_queries": ["Rome skyline", "Colosseum interior arena", "Roman Forum ruins", "plate of Italian pasta"], "alt": ""}
    sync.apply("gallery", props, words, 14.0)
    by = {w[0]: w[1] for w in words}
    assert props["cuts"][1] == pytest.approx(by["Colosseum."] + sync.GALLERY_AFTER_S, abs=0.01)         # 1 of 3 query words is enough for a photo
    assert props["cuts"][2] == pytest.approx(by["Roman"] + sync.GALLERY_AFTER_S, abs=0.01)
    assert props["cuts"][3] == pytest.approx(by["pasta"] + sync.GALLERY_AFTER_S, abs=0.01)
    # lists keep the stricter rule: half of an item's words must be said
    assert sync.find_mentions(["Colosseum interior arena"], words) == [None] and sync.find_mentions(["Colosseum interior arena"], words, 0.0) == [5]


# ================================================================= a photo of exactly the frame's shape must not crash the render (found live)
@pytest.mark.parametrize("size", [(1920, 1080), (3840, 2160), (1408, 792), (1401, 788), (1409, 792), (2000, 1125)])   # 1408x792 and its neighbours put the crop box at -1e-13
def test_photos_of_exactly_16_by_9_render_in_images_and_galleries(size):
    from PIL import Image
    photo = Image.new("RGB", size, (90, 140, 200))
    tl = small_timeline(9.0, ["image", "gallery"])
    tl["scenes"][0]["props"] = {"asset": "k", "ken_burns": "in"}
    tl["scenes"][1]["props"] = {"assets": ["a", "b", "c"], "credits": [], "alt": "x", "cuts": [0.0, 1.5, 3.0]}
    tl["captions"] = False
    r = Renderer(tl, lambda key: photo)
    for t in np.linspace(0.0, 8.95, 60):                         # every phase of both scenes, including the crossfades and the end
        assert r.frame_at(float(t)).size == (1920, 1080)
    for k in ("in", "left", "right", "out"):
        tl["scenes"][0]["props"]["ken_burns"] = k
        for t in (0.0, 2.0, 4.4):
            Renderer(tl, lambda key: photo).frame_at(t)
