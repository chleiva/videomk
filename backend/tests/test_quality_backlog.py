"""The QUALITY_REVIEW backlog (docs/QUALITY_REVIEW.md section 8, requirement R045): a beat per 10 s, beat 1 never a title card, a chart's first value up by 1.2 s,
no empty slots in vertical and square lists, no meaningless icon for an item nothing fits, and a year is never counted up to."""
import json

import numpy as np
import pytest

from engine import director, edits, plan as plan_mod
from engine.frame import Frame
from engine.renderer import Renderer
from engine.scenes import style_kit, viz_scenes
from engine.scenes.base import parse_number
from engine.scenes.flow_scenes import icon_for_node
from engine.scenes.text_scenes import is_calendar_year
from tests.test_skills import _ask_small


# ------------------------------------------------------------------ 1. beat length 14 s -> 10 s
def test_a_beat_is_about_ten_seconds_from_a_minute_up_and_photo_videos_keep_their_rhythm():
    assert plan_mod.BEAT_S == 10.0 and plan_mod.PHOTO_BEAT_S == 14.0
    assert [plan_mod.expected_beats(m) for m in (1, 2, 3, 5, 8, 12)] == [6, 12, 18, 30, 48, 72]
    assert plan_mod.expected_beats(12) <= plan_mod.MAX_BEATS
    assert [plan_mod.expected_beats(m, 3) for m in (1, 2, 3, 5)] == [4, 9, 13, 21]          # the person's photos: 14 s as before
    assert plan_mod.expected_beats(2, 40) == 40                                             # and never fewer beats than photos
    assert [plan_mod.expected_beats(m) for m in (0.25, 0.5, 0.75)] == [2, 3, 4]              # short forms unchanged
    for m in (1, 3, 12):   # the words still fill the length: speech plus every beat's lead-in and tail
        secs = plan_mod.expected_words(m) / plan_mod.SPOKEN_WORDS_PER_S + plan_mod.expected_beats(m) * plan_mod.BEAT_OVERHEAD_S
        assert 0.97 * m * 60 <= secs <= m * 60 + 0.5
        assert 18 <= plan_mod.expected_words(m) / plan_mod.expected_beats(m) <= 24       # about 21 words a beat, well inside the 6 to 70 a beat may have


# ------------------------------------------------------------------ 2. beat 1 is never a title card
def _beats(first, n=4):
    rest = [{"narration": " ".join(["w"] * 20), "scene": {"type": "bullets", "props": {"heading": "h", "items": ["a", "b"]}}} for _ in range(n - 1)]
    return [{"narration": "The ocean holds fifty million billion tons of salt, and rivers bring more.", "scene": first}] + rest


def _direct(first, monkeypatch=None, **kw):
    big = lambda s, u: json.dumps({"legit": True, "title": "Why the ocean is salty", "description": "d", "voices": {"narrator": "Ruth"}, "beats": _beats(first)})   # noqa: E731
    return director.direct("why is the ocean salty", minutes=0.75, ask_small=_ask_small(["explainer-education"]), ask_big=big, language="en", **kw)


def test_a_title_card_opening_becomes_a_photograph_of_the_subject_and_the_words_stay():
    out = _direct({"type": "title", "props": {"title": "Why the ocean is salty", "subtitle": "A short tour"}})
    first = out["plan"]["beats"][0]
    assert first["scene"] == {"type": "image", "props": {"image_query": "ocean salty", "alt": "Why the ocean is salty"}}
    assert first["narration"].startswith("The ocean holds")                                   # the voice and the captions are untouched
    assert any("opening title card became a photograph" in w for w in out["warnings"]) and "photograph" in out["research"]["opening"]
    assert [b["scene"]["type"] for b in out["plan"]["beats"][1:]] == ["bullets"] * 3


def test_without_photo_budget_the_opening_becomes_moving_words_and_other_openings_are_left_alone():
    out = _direct({"type": "title", "props": {"title": "Why the ocean is salty"}}, max_images_per_minute=0)
    assert out["plan"]["beats"][0]["scene"] == {"type": "kinetic_text", "props": {"text": "Why the ocean is salty"}}
    stat = {"type": "stat", "props": {"value": "3.5%", "label": "salt in sea water"}}
    out = _direct(stat)
    assert out["plan"]["beats"][0]["scene"]["type"] == "stat" and "opening" not in out["research"] and not any("opening" in w for w in out["warnings"])


def test_the_opening_rule_is_for_new_videos_only_not_for_edits_photo_videos_or_with_the_switch_off(monkeypatch):
    raw = {"legit": True, "title": "T", "voices": {"narrator": "Ruth"}, "beats": _beats({"type": "title", "props": {"title": "Why the ocean is salty"}})}
    plan, warns = plan_mod.validate_plan(raw, max_images=5)                                  # the validation alone (it also runs on every edit) never changes the opening
    assert plan["beats"][0]["scene"]["type"] == "title" and not any("opening" in w for w in warns)
    new, _ = edits.apply_ops(plan, [{"op": "set_meta", "title": "Another title"}])
    assert new["beats"][0]["scene"]["type"] == "title"
    monkeypatch.setenv("QUALITY_FIXES", "0")
    assert _direct({"type": "title", "props": {"title": "Why the ocean is salty"}})["plan"]["beats"][0]["scene"]["type"] == "title"
    monkeypatch.delenv("QUALITY_FIXES")
    # a pause that opens the video, and budgets that are full, are respected
    beats = plan["beats"]
    assert plan_mod.enforce_opening([dict(beats[0], silent=True)] + beats[1:], 5) == []
    full = [dict(beats[0])] + [{"narration": "x", "scene": {"type": "image", "props": {"image_query": "a b", "alt": "a"}}}, {"narration": "x", "scene": {"type": "kinetic_text", "props": {"text": "t"}}}]
    assert plan_mod.enforce_opening(full, 1) and full[0]["scene"]["type"] == "kinetic_text"   # the one photo is taken: moving words
    assert plan_mod.enforce_opening([], 3) == []


def test_the_opening_search_uses_the_cards_own_words():
    assert plan_mod.opening_query("Why the ocean is salty") == "ocean salty"
    assert plan_mod.opening_query("How Honeybees Turn Nectar Into Honey") == "honeybees turn nectar honey"
    assert plan_mod.opening_query("¿Por qué el cielo es azul?") == "cielo azul"
    assert plan_mod.opening_query("AI", "Sunlight is white, so why is the sky blue?") == "sunlight white sky blue"
    assert plan_mod.opening_query("", "") == "" and len(plan_mod.opening_query("one two three four five six seven eight nine ten").split()) == 6
    assert "never as the first scene" in plan_mod.scene_docs()                               # and the writer is told


# ------------------------------------------------------------------ 3. chart first cue
def test_a_charts_first_value_is_up_by_1_2_seconds_whatever_the_voice_does():
    assert viz_scenes.chart_times(4, 12.0, [6.0, 7.5, 9.0, 10.5]) == [1.2, 7.5, 9.0, 10.5]    # the voice names the first bar late: it is shown early, the others keep their moments
    assert viz_scenes.chart_times(3, 6.0, [0.4, 2.0, 3.0]) == [0.4, 2.0, 3.0]                # an early cue is kept
    assert viz_scenes.chart_times(4, 20.0, None)[0] == 1.2 and viz_scenes.chart_times(4, 6.0, None)[0] == pytest.approx(0.9)
    props = {"kind": "bar", "title": "Revenue", "labels": ["Q1", "Q2", "Q3"], "values": [120, 180, 150], "unit": "$", "cues": [6.0, 7.0, 8.0]}
    assert viz_scenes.chart_cues(props, 12.0) == [1.2, 7.0, 8.0]

    def frame(p, t):
        sc = {"id": "c", "type": "chart", "start": 0.0, "duration": 12.0, "props": p, "words": [], "transition": "none"}
        tl = {"scenes": [sc], "theme": "midnight", "captions": False, "duration": 12.0, "width": 1920, "height": 1080, "fps": 30, "outro": False}
        return np.asarray(Renderer(tl, draft=True).frame_at(t), np.int16)
    empty = frame(dict(props, values=[0.0001, 0.0001, 0.0001], cues=[11.0, 11.5, 11.9]), 3.0)   # axes only
    assert np.abs(frame(props, 3.0) - empty).max() > 60                                      # at 3 s the first bar is on screen, three seconds before the voice names it


# ------------------------------------------------------------------ 4. ghost slots
LIST = {"heading": "Three rules", "items": ["Speed: results in days", "Safety: tested widely", "Cost: free to start"], "cues": [1.0, 7.0, 9.0]}
FLOW = {"title": "How it flows", "nodes": [{"id": "a", "label": "Browser"}, {"id": "b", "label": "Server"}, {"id": "c", "label": "Database"}], "edges": [["a", "b"], ["b", "c"]], "cues": [1.0, 7.0, 9.0]}


@pytest.mark.parametrize("stype,props", [("bullets", dict(LIST, style="cards")), ("bullets", dict(LIST, style="icons")), ("diagram", FLOW)])
def test_vertical_and_square_lists_show_no_empty_slots_and_landscape_keeps_them(monkeypatch, stype, props):
    """Before the voice reaches the first item (0.6 s; the first cue is at 1.0 s) nothing of the list may be on screen outside landscape: every sprite drawn then is an
    empty slot. Landscape keeps its faint structure."""
    from engine.scenes import flow_scenes, list_scenes

    drawn = []
    real = style_kit.paste_sprite

    def spy(cv, spr, cx, cy, scale=1.0, alpha=1.0):
        if alpha > 0.01:
            drawn.append(round(alpha, 2))
        return real(cv, spr, cx, cy, scale, alpha)
    monkeypatch.setattr(list_scenes, "paste_sprite", spy)
    monkeypatch.setattr(flow_scenes, "paste_sprite", spy)
    for aspect in ("9:16", "1:1", "4:5", "16:9"):
        fr = Frame.parse(aspect, "1080p")
        sc = {"id": "s", "type": stype, "start": 0.0, "duration": 10.0, "props": props, "words": [], "transition": "none"}
        tl = {"scenes": [sc], "theme": "midnight", "captions": False, "duration": 10.0, "width": fr.width, "height": fr.height, "fps": 30, "outro": False, "frame": {"aspect": aspect, "resolution": "1080p"}}
        r = Renderer(tl, draft=True)
        drawn.clear()
        r.frame_at(0.6)
        if aspect == "16:9":
            assert len(drawn) >= 3 and max(drawn) <= 0.31, (stype, drawn)        # three faint slots, nothing else
        else:
            assert drawn == [], (stype, aspect, drawn)
        drawn.clear()
        r.frame_at(9.9)
        assert len([a for a in drawn if a > 0.9]) >= 3, (stype, aspect)           # and at the end every item is fully there in every shape


# ------------------------------------------------------------------ 5. icon picker no-match
def test_an_item_no_icon_fits_gets_a_plain_marker_and_a_list_with_mostly_none_is_numbered():
    assert style_kit.match_icon("Database of customers") == "database" and style_kit.match_icon("Atreverse a empezar") == ""
    assert style_kit.auto_icon("Atreverse a empezar", 2) == "#3"                              # never the old rotating decoration (sparkles, target, lightbulb ...)
    mostly = {"items": ["Speed: results in days", "Safety: tested widely", "Cost: free to start", "Support: help any time", "Scale: grows with you"]}
    got = [style_kit.icon_for(mostly, i, t) for i, t in enumerate(mostly["items"])]
    assert got[1] == style_kit.NEUTRAL_ICON and all(g and not g.startswith("#") for g in got) and got[0] != got[1]
    spanish = {"items": ["Atreverse a empezar", "Perseverar cada jornada", "Celebrar lo logrado"]}
    assert [style_kit.icon_for(spanish, i, t) for i, t in enumerate(spanish["items"])] == ["#1", "#2", "#3"]
    given = dict(spanish, icons=["rocket", "", "trophy"])                                    # the writer's own icons count: two of three, so the gap is a plain marker
    assert [style_kit.icon_for(given, i, t) for i, t in enumerate(given["items"])] == ["rocket", style_kit.NEUTRAL_ICON, "trophy"]
    assert style_kit.group_icon(["a", "", "", ""], 1) == "#2" and style_kit.group_icon(["a", "b", "", ""], 3) == style_kit.NEUTRAL_ICON and style_kit.group_icon([], 0) == "#1"
    nodes = [{"id": "a", "label": "Apps"}, {"id": "b", "label": "Services"}, {"id": "c", "label": "Runtime"}]
    assert [icon_for_node({"nodes": nodes}, n, i, n["label"]) for i, n in enumerate(nodes)] == ["#1", "#2", "#3"]
    nodes = [{"id": "a", "label": "Browser"}, {"id": "b", "label": "App server"}, {"id": "c", "label": "Database"}]
    assert [icon_for_node({"nodes": nodes}, n, i, n["label"]) for i, n in enumerate(nodes)] == [style_kit.NEUTRAL_ICON, "server", "database"]
    for name in ("sparkles", "target", "lightbulb", "star", "zap", "flag", "compass", "layers"):
        assert name not in [style_kit.auto_icon(f"Zzqx item {k}", k) for k in range(8)]


def test_a_number_icon_is_drawn_as_the_numeral():
    from engine.canvas import Canvas

    a, b = Canvas(200, 200, ss=1), Canvas(200, 200, ss=1)
    style_kit.icon(a, 100, 100, "#3", 80, (255, 255, 255, 255))
    assert np.asarray(a.to_rgb()).max() > 200 and np.asarray(b.to_rgb()).max() == 0
    style_kit.icon(b, 100, 100, "#3", 80, (255, 255, 255, 0))                                # fully transparent: nothing
    assert np.asarray(b.to_rgb()).max() == 0


# ------------------------------------------------------------------ and: a year is a name, not an amount (seen on QA: "1912s" on the way to "1970s")
@pytest.mark.parametrize("value,year", [("1970s", True), ("1912", True), ("2024", True), ("1969 ", True), ("1,250", False), ("1500 km", False), ("$2000", False),
                                        ("2000%", False), ("3.3 billion", False), ("73%", False), ("12000", False), ("950", False)])
def test_a_year_or_a_decade_is_not_counted_up(value, year):
    assert is_calendar_year(parse_number(value), value) is year


def test_a_decade_stat_shows_the_decade_from_its_first_frame(monkeypatch):
    from engine.scenes import text_scenes

    partial = []
    real = text_scenes.format_number
    monkeypatch.setattr(text_scenes, "format_number", lambda v, *a, **k: (partial.append(v), real(v, *a, **k))[1])

    def frame(value, t):
        sc = {"id": "s", "type": "stat", "start": 0.0, "duration": 8.0, "props": {"value": value, "label": "When it began"}, "words": [], "transition": "none"}
        tl = {"scenes": [sc], "theme": "midnight", "captions": False, "duration": 8.0, "width": 1920, "height": 1080, "fps": 30, "outro": False}
        return Renderer(tl, draft=True).frame_at(t)
    frame("1970s", 0.3)
    assert partial == []                                   # shown as written: no number on the way to it
    frame("1970 km", 0.3)
    assert partial and 0 < partial[0] < 1970               # an amount still counts up
