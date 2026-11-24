"""headline, dialogue, icons, annotated_image (engine/scenes/elements/people_media.py)."""
import copy
import json

import pytest
from PIL import Image

from tests.element_utils import changed, render
from engine.scenes import ELEMENTS
from engine.scenes.elements import _pm_icons, _pm_vision, people_media as pm
from engine.scenes.registry import PrepareCtx


def ctx(sources=None):
    return PrepareCtx(video_id="v1", beat_id="b1", narration="the narration", duration=6.0, sources=sources or [])


SOURCES = [
    {"title": "Central bank holds interest rates steady as inflation cools - Reuters", "url": "https://www.reuters.com/markets/rates-2026-11-12/", "publisher": "Reuters"},
    {"title": "Ministers agree new flood defence funding for coastal towns", "url": "https://www.bbc.co.uk/news/uk-123", "publisher": ""},
    {"title": "Coastal towns welcome flood funding but warn it may arrive too late", "url": "https://www.theguardian.com/x", "publisher": "The Guardian", "date": "2026-11-04"},
    {"title": "Rail strike ends after 12 days of talks", "url": "https://www.nytimes.com/a", "publisher": "The New York Times"},
]


# ------------------------------------------------------------------------------------------------ headline
def test_headline_sanitize_keeps_real_length_and_never_shortens_a_headline():
    assert pm.sanitize_headline({"headlines": [{"text": "x " * 100, "outlet": "BBC"}, {"text": "Fine headline here today", "outlet": "BBC", "date": "1 Jan 2026"}]})["headlines"][0]["text"] == "Fine headline here today"
    with pytest.raises(ValueError):
        pm.sanitize_headline({"headlines": [{"text": "word " * 60, "outlet": "BBC"}]})        # too long to be copied as it is: not used, not trimmed
    with pytest.raises(ValueError):
        pm.sanitize_headline({"headlines": [{"text": "No outlet at all", "outlet": ""}]})
    many = {"headlines": [{"text": f"headline number {i} about things", "outlet": "BBC"} for i in range(6)]}
    assert len(pm.sanitize_headline(many)["headlines"]) == 3


def test_outlet_matching_is_tolerant_of_the_and_domain_forms():
    s = SOURCES
    assert pm.outlet_matches("Reuters", s[0]) and pm.outlet_matches("reuters", s[0])
    assert pm.outlet_matches("BBC News", s[1]) and pm.outlet_matches("bbc.co.uk", s[1])          # no publisher: the domain says it
    assert pm.outlet_matches("Guardian", s[2]) and pm.outlet_matches("The Guardian", s[2])
    assert pm.outlet_matches("NYT", s[3]) and pm.outlet_matches("New York Times", s[3])
    assert not pm.outlet_matches("Reuters", s[1]) and not pm.outlet_matches("Daily Mail", s[2]) and not pm.outlet_matches("X", s[0])


def test_headline_text_must_overlap_the_source_title_without_adding_or_cherry_picking():
    t = SOURCES[0]["title"]
    assert pm.text_matches_title("Central bank holds interest rates steady as inflation cools", t, "Reuters")        # the title without the outlet tag
    assert pm.text_matches_title("Central bank holds interest rates steady as inflation cools - Reuters", t)
    assert not pm.text_matches_title("Central bank cuts interest rates sharply as inflation soars", t)               # a different story
    assert not pm.text_matches_title("Inflation cools", t)                                                          # a few cherry-picked words
    assert not pm.text_matches_title("Central bank holds interest rates steady as inflation cools and unemployment falls to 3 percent", t)   # adds a claim and a number
    assert not pm.text_matches_title("Rail strike ends after 14 days of talks", SOURCES[3]["title"])               # a changed number


def test_prepare_headline_keeps_only_verified_headlines_and_raises_when_none():
    props = {"headlines": [
        {"text": "Central bank holds interest rates steady as inflation cools", "outlet": "Reuters", "date": "12 Nov 2026"},
        {"text": "Prime minister resigns after shock vote", "outlet": "BBC News", "date": "3 Nov 2026"},                       # invented
        {"text": "Rail strike ends after 12 days of talks", "outlet": "Daily Mail", "date": "1 Nov 2026"},                    # right words, wrong outlet
        {"text": "Coastal towns welcome flood funding but warn it may arrive too late", "outlet": "The Guardian", "date": "4 Nov 2025"},   # wrong year
    ]}
    out = pm.prepare_headline(props, ctx(SOURCES))
    assert [h["outlet"] for h in out["headlines"]] == ["Reuters"] and out["headlines"][0]["source"] == "reuters.com"
    with pytest.raises(ValueError):
        pm.prepare_headline({"headlines": [{"text": "Prime minister resigns after shock vote", "outlet": "BBC News"}]}, ctx(SOURCES))
    with pytest.raises(ValueError):
        pm.prepare_headline(props, ctx([]))                                                                               # no cited sources at all
    assert pm.sanitize_headline({**props, "headlines": out["headlines"]})["headlines"] == out["headlines"]               # the patch survives re-sanitizing


def test_headline_doc_states_the_honesty_rule():
    assert "Only headlines that appear in the grounding notes with their outlet and date; never invented or rephrased" in ELEMENTS["headline"].doc


# ------------------------------------------------------------------------------------------------ dialogue
def test_dialogue_keeps_speaker_order_trims_on_a_word_boundary_and_limits_voices():
    long = "The quick brown fox jumps over the lazy dog and keeps running through the forest until it reaches the river bank where it finally rests for the night"
    p = pm.sanitize_dialogue({"turns": [{"speaker": "Ann", "text": long}, {"speaker": "bob", "text": "Hi"}, {"speaker": "BOB", "text": "again"}, {"speaker": "Cy", "text": "c"},
                                        {"speaker": "Dee", "text": "fourth voice"}, {"speaker": "Ann", "text": "end"}]})
    assert [t["speaker"] for t in p["turns"]] == ["Ann", "bob", "bob", "Cy", "Ann"]
    t0 = p["turns"][0]["text"]
    assert len(t0) <= 120 and t0.endswith("…") and long.startswith(t0[:-1]) and long[len(t0) - 1] == " "
    assert pm.sanitize_dialogue(p) == p
    with pytest.raises(ValueError):
        pm.sanitize_dialogue({"turns": [{"speaker": "Ann", "text": "a"}, {"speaker": "ann", "text": "b"}]})         # one voice is not a dialogue
    with pytest.raises(ValueError):
        pm.sanitize_dialogue({"turns": [{"speaker": "Ann", "text": "only one"}]})
    assert len(pm.sanitize_dialogue({"turns": [{"speaker": "AB"[i % 2], "text": f"turn {i}"} for i in range(9)]})["turns"]) == 6


def test_dialogue_anchors_are_the_texts_in_order():
    p = pm.sanitize_dialogue(ELEMENTS["dialogue"].samples[0])
    assert ELEMENTS["dialogue"].anchors(p) == [t["text"] for t in p["turns"]]


def test_dialogue_with_six_long_turns_still_fits_and_shows_every_bubble_at_the_end():
    turns = [{"speaker": ["A", "B", "C"][i % 3], "text": "word " * 24} for i in range(6)]
    p = pm.sanitize_dialogue({"turns": turns})
    a, b = render("dialogue", p, 3.0, 12.0), render("dialogue", p, 12.0, 12.0)
    assert changed(a, b) > 0.002


# ------------------------------------------------------------------------------------------------ icons
@pytest.mark.parametrize("word,expected", [("lock", "lock"), ("cloud", "cloud"), ("heart", "heart"), ("rocket", "rocket"), ("money", "banknote"), ("Piggy Bank", "piggy-bank"), ("hearts", "heart")])
def test_icon_lookup_finds_the_named_icon(word, expected):
    assert _pm_icons.find_icon(word)[0] == expected


def test_icon_lookup_never_fails_and_falls_back_to_a_neutral_glyph():
    for w in ("", "   ", "zzzzqx", "a" * 200, "naïve café", "../../etc/passwd", "🙂"):
        name, how = _pm_icons.find_icon(w)
        assert name in _pm_icons._index()
    assert _pm_icons.find_icon("zzzzqx") == (_pm_icons.NEUTRAL, "neutral")
    assert _pm_icons.find_icon("puppy")[0] == "dog" and _pm_icons.find_icon("magnifier")[0] == "search"
    assert _pm_icons.glyph_mask("lock", 120) is not None


def test_icons_sanitize_limits_and_idempotence():
    p = pm.sanitize_icons({"title": "T" * 80, "items": [{"icon": "lock", "label": "L" * 40, "sub": "s" * 90}, {"label": "No icon word"}, {"icon": "x"}, "junk"] + [{"label": f"i{i}"} for i in range(8)]})
    assert len(p["items"]) == 6 and len(p["title"]) <= 50 and len(p["items"][0]["label"]) <= 24 and len(p["items"][0]["sub"]) <= 40
    assert p["items"][1]["icon"] == "No icon word" and pm.sanitize_icons(p) == p
    with pytest.raises(ValueError):
        pm.sanitize_icons({"items": [{"icon": "lock", "label": "only one"}]})


# ------------------------------------------------------------------------------------------------ the end state shows everything
@pytest.mark.parametrize("name", ["headline", "dialogue", "icons", "annotated_image"])
def test_every_part_is_there_at_the_end(name):
    el = ELEMENTS[name]
    props = el.sanitize(copy.deepcopy(el.samples[-1]))
    dur = 10.0
    cues = el.cues(props, dur)
    before_last = render(name, props, cues[-1] - 0.05, dur)
    end = render(name, props, dur, dur)
    assert changed(before_last, end) > 0.0005, "the last part should appear by the end"


# ------------------------------------------------------------------------------------------------ annotated_image
def test_annotated_sanitize_keeps_pins_and_derives_labels_from_them():
    p = pm.sanitize_annotated({"image_query": "bridge", "alt": "a" * 100, "labels": ["a", "A", "b", "c", "d", "e"]})
    assert p["labels"] == ["a", "b", "c", "d"] and len(p["alt"]) <= 70 and "pins" not in p
    q = pm.sanitize_annotated({**p, "asset": "k.jpg", "credit": "Photo: x", "pins": [{"label": "Arch", "x": 0.4, "y": 0.5}, {"label": "Bad", "x": 2, "y": 0.1}, {"label": "Nan", "x": "a", "y": 1}]})
    assert q["pins"] == [{"label": "Arch", "x": 0.4, "y": 0.5}] and q["labels"] == ["Arch"] and pm.sanitize_annotated(q) == q
    with pytest.raises(ValueError):
        pm.sanitize_annotated({"image_query": "bridge", "labels": ["only one"]})
    with pytest.raises(ValueError):
        pm.sanitize_annotated({"labels": ["a", "b"]})


def _answer(parts):
    return json.dumps({"parts": parts}), {"cost_usd": 0.001}


def _part(label, x, y, r=0.08):
    return {"label": label, "visible": True, "pin": [x, y], "box": [x - r, y - r, x + r, y + r]}


def test_vision_trusts_only_what_two_looks_agree_on():
    jpeg = _pm_jpeg()
    calls = []

    def complete(system, user, images=(), **kw):
        calls.append(user)
        first = len(calls) == 1
        return _answer([
            _part("Wheel", 0.30, 0.60),                                                      # both looks agree
            _part("Handlebars", 0.60, 0.30) if first else _part("Handlebars", 0.62, 0.34),   # agree within tolerance
            _part("Saddle", 0.50, 0.20) if first else _part("Saddle", 0.80, 0.70),          # the looks disagree: dropped
            {"label": "Bell", "visible": False},                                             # not visible: dropped
        ])

    found, cost = _pm_vision.locate(jpeg, ["Wheel", "Handlebars", "Saddle", "Bell"], "a bicycle", complete)
    assert set(found) == {"Wheel", "Handlebars"} and found["Wheel"] == (0.3, 0.6) and cost > 0 and len(calls) == 2 and "grid" in calls[1] and "grid" not in calls[0]


def test_vision_drops_self_contradicting_huge_or_overlapping_answers():
    jpeg = _pm_jpeg()
    parts = [
        {"label": "A", "visible": True, "pin": [0.9, 0.9], "box": [0.1, 0.1, 0.3, 0.3]},     # pin outside its own box
        {"label": "B", "visible": True, "pin": [0.5, 0.5], "box": [0.0, 0.0, 1.0, 1.0]},     # the whole picture is not a part
        _part("C", 0.30, 0.30), _part("D", 0.33, 0.31),                                      # D sits on top of C
        {"label": "E", "visible": True, "pin": [1.4, 0.2], "box": [0.2, 0.2, 0.5, 0.5]},     # out of range
    ]
    found, _ = _pm_vision.locate(jpeg, ["A", "B", "C", "D", "E"], "x", lambda *a, **k: _answer(parts))
    assert list(found) == ["C"]


def test_vision_survives_garbage_replies():
    jpeg = _pm_jpeg()
    for text in ("", "I cannot see", "{not json", '{"parts": "x"}', '{"parts": [1, 2]}'):
        found, _ = _pm_vision.locate(jpeg, ["A", "B"], "x", lambda *a, **k: (text, {}))
        assert found == {}


def _pm_jpeg():
    import io
    b = io.BytesIO()
    Image.new("RGB", (900, 600), (80, 120, 160)).save(b, "JPEG")
    return b.getvalue()


@pytest.fixture
def fake_world(monkeypatch):
    from engine import awsio, llm
    from engine.handlers import beat_handler
    state = {"photo": {"asset": "p/assets/img_b1_abc.jpg", "credit": "Photo: Jane / Unsplash", "ledger": {"source": "unsplash", "id": "1"}}, "reply": None}
    monkeypatch.setattr(beat_handler, "make_photo", lambda plan, beat, vid, field: dict(state["photo"]))
    monkeypatch.setattr(awsio, "get_bytes", lambda key: _pm_jpeg())

    def complete(system, user, images=(), **kw):
        if isinstance(state["reply"], Exception):
            raise state["reply"]
        return state["reply"], {"cost_usd": 0.0}
    monkeypatch.setattr(llm, "complete", complete)
    from engine import costs
    monkeypatch.setattr(costs, "add_cost", lambda *a, **k: None)
    return state


def test_prepare_annotated_returns_the_photo_credit_and_only_located_pins(fake_world):
    fake_world["reply"] = json.dumps({"parts": [_part("Arch", 0.4, 0.5), {"label": "Parapet", "visible": False}]})
    patch = pm.prepare_annotated({"image_query": "old stone bridge", "alt": "a bridge", "labels": ["Arch", "Parapet"]}, ctx())
    assert patch["asset"].endswith(".jpg") and patch["credit"] == "Photo: Jane / Unsplash" and patch["ledger"]["source"] == "unsplash"
    assert patch["pins"] == [{"label": "Arch", "x": 0.4, "y": 0.5}] and patch["labels"] == ["Arch"]
    merged = {**pm.sanitize_annotated({"image_query": "old stone bridge", "alt": "a bridge", "labels": ["Arch", "Parapet"]}), **patch}
    assert pm.sanitize_annotated({k: v for k, v in merged.items() if k != "ledger"})["pins"] == patch["pins"]


def test_prepare_annotated_shows_the_photo_alone_when_nothing_can_be_located(fake_world):
    for reply in ('{"parts": []}', RuntimeError("bedrock down")):
        fake_world["reply"] = reply
        patch = pm.prepare_annotated({"image_query": "old stone bridge", "labels": ["Arch", "Parapet"]}, ctx())
        assert patch["pins"] == [] and patch["asset"]


def test_prepare_annotated_raises_without_a_photograph(fake_world):
    fake_world["photo"] = {"no_photo": True}
    with pytest.raises(RuntimeError):
        pm.prepare_annotated({"image_query": "old stone bridge", "labels": ["Arch", "Parapet"]}, ctx())
    assert pm.annotated_fallback({"image_query": "old stone bridge", "alt": "a bridge"})[0] == "image"


def test_annotated_draws_the_photo_pins_and_credit_and_the_plain_photo_when_no_pins():
    photo = Image.new("RGB", (1600, 1067), (90, 140, 200))
    props = pm.sanitize_annotated({"image_query": "red bike", "labels": ["a", "b"], "asset": "k", "credit": "Photo: J", "pins": [{"label": "Wheel", "x": 0.3, "y": 0.6}, {"label": "Bar", "x": 0.7, "y": 0.3}]})
    load = lambda k: photo
    start, end = render("annotated_image", props, 0.2, 8.0, image_loader=load), render("annotated_image", props, 8.0, 8.0, image_loader=load)
    assert changed(start, end) > 0.004
    bare = {**props, "pins": []}
    plain = render("annotated_image", bare, 4.0, 8.0, image_loader=load)
    assert changed(plain, render("annotated_image", props, 8.0, 8.0, image_loader=load)) > 0.004
    assert ELEMENTS["annotated_image"].max_per_video == 3
