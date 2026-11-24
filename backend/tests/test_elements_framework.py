"""The element registry and everything every element must satisfy. Elements live in lambdas/engine/scenes/elements/ and are checked here automatically."""
import copy

import pytest

from tests.element_utils import changed, render, themes
from engine import plan as plan_mod, sync, timeline as tl_mod
from engine.scenes import ELEMENTS, SCENES, register_runtime
from engine.scenes import registry
from engine.scenes.registry import Element, PrepareCtx

CORE = {"title", "bullets", "diagram", "chart", "timeline", "stat", "quote", "image", "clip", "gallery"}
FAMILIES = {"Text", "Lists", "Compare", "Data", "Process", "Maps", "Code and math", "People and sources", "Media"}


def test_no_element_module_failed_to_import():
    assert registry.FAILED == {}, registry.FAILED


# ----------------------------------------------------------------------------- every registered element
@pytest.mark.parametrize("name", sorted(ELEMENTS))
def test_the_element_meets_the_contract(name):
    el = ELEMENTS[name]
    assert name not in CORE and el.name == name and el.family in FAMILIES, (el.family, FAMILIES)
    assert el.doc.lstrip().startswith(f"- {name}:") and len(el.doc) <= 800, "the doc is one to three lines starting with '- name:'"
    assert len(el.samples) >= 2
    assert SCENES[name] == (el.draw, el.cues)
    for sample in el.samples:
        clean = el.sanitize(copy.deepcopy(sample))
        assert isinstance(clean, dict) and clean
        assert el.sanitize(copy.deepcopy(clean)) == clean, "sanitize must be idempotent (the editor re-sanitizes saved props)"
    with pytest.raises(ValueError):
        el.sanitize({})                                           # an empty scene is unusable, not a blank frame


@pytest.mark.parametrize("name", sorted(ELEMENTS))
def test_the_element_draws_on_every_theme_with_something_to_see(name):
    el = ELEMENTS[name]
    for sample in el.samples:
        props = el.sanitize(copy.deepcopy(sample))
        dur = max(6.0, el.min_seconds + 2)
        for th in themes():
            early, mid, end = (render(name, props, lt, dur, th) for lt in (0.0, dur * 0.5, dur))
            assert changed(early, end) > 0.004, f"{name} shows nothing by the end on theme {th}"
            assert end.size == mid.size
        cues = el.cues(props, dur)
        assert all(isinstance(c, (int, float)) and 0 <= c <= dur for c in cues)


@pytest.mark.parametrize("name", sorted(ELEMENTS))
def test_the_element_survives_hostile_props_without_crashing(name):
    el = ELEMENTS[name]
    junk = [{"title": "x" * 5000, "items": "not a list", "values": [None, "a", {}]}, {"a": {"b": [1, 2, {"c": None}]}}, {"label": "‮" * 50}]
    for j in junk:
        try:
            props = el.sanitize(j)
        except (ValueError, TypeError):
            continue                                              # refusing is fine; crashing later in draw is not
        render(name, props, 1.0, 6.0)


# ----------------------------------------------------------------------------- the framework with a throwaway element
def _demo(**kw):
    def sanitize(p):
        t = str(p.get("title") or "").strip()[:40]
        items = [str(i)[:30] for i in (p.get("items") or []) if str(i).strip()][:4]
        if not t or len(items) < 2:
            raise ValueError("demo needs a title and 2+ items")
        return {"title": t, "items": items}

    def draw(cv, props, lt, dur, th, ctx):
        cv.text(960, 300, props["title"], "bold", 90, th.text, anchor="mm")
        for i, it in enumerate(props["items"]):
            if lt > (props.get("cues") or [0.5 + i for i in range(4)])[i]:
                cv.text(960, 450 + i * 90, it, "regular", 56, th.accent, anchor="mm")

    base = dict(name="demo_el", family="Text", doc="- demo_el: {title, items: 2-4 strings}. A throwaway element for tests.", sanitize=sanitize, draw=draw,
                cues=lambda p, d: [0.5, 1.5], samples=[{"title": "A", "items": ["one", "two"]}, {"title": "B", "items": ["x", "y", "z"]}],
                anchors=lambda p: p["items"])
    base.update(kw)
    return Element(**base)


@pytest.fixture
def demo(monkeypatch):
    el = _demo()
    monkeypatch.setitem(ELEMENTS, "demo_el", el)
    monkeypatch.setitem(SCENES, "demo_el", (el.draw, el.cues))
    monkeypatch.setattr(plan_mod, "SCENE_TYPES", tuple(SCENES))
    return el


def test_the_director_prompt_lists_elements_by_family(demo):
    docs = plan_mod.scene_docs()
    assert "[Text]" in docs and "- demo_el:" in docs and "More scene types, by family" in docs


def test_props_are_cleaned_by_the_element_and_a_bad_scene_falls_back_to_a_title_card(demo):
    raw = {"legit": True, "title": "T", "description": "d", "voices": {"narrator": "Ruth"}, "beats": [
        {"narration": "A first idea about rivers and bridges in the city.", "scene": {"type": "demo_el", "props": {"title": "Rivers", "items": ["a", "b"]}}},
        {"narration": "A second idea about markets and the food people eat.", "scene": {"type": "demo_el", "props": {"title": "no items"}}},
        {"narration": "A closing thought on the whole city and its people.", "scene": {"type": "title", "props": {"title": "End"}}}]}
    plan, warns = plan_mod.validate_plan(raw)
    assert plan["beats"][0]["scene"] == {"type": "demo_el", "props": {"title": "Rivers", "items": ["a", "b"]}}
    assert plan["beats"][1]["scene"]["type"] == "title" and any("scene replaced" in w for w in warns)


def test_a_budget_turns_the_extra_uses_into_title_cards_and_repeats_are_warned(monkeypatch, demo):
    demo.max_per_video = 1
    beats = [{"narration": "alpha beta gamma delta epsilon zeta eta theta", "scene": {"type": "demo_el", "props": {"title": "A", "items": ["a", "b"]}}} for _ in range(3)]
    warns = plan_mod.enforce_elements(beats)
    assert [b["scene"]["type"] for b in beats] == ["demo_el", "title", "title"] and any("at most 1 per video" in w for w in warns)
    demo.max_per_video = None
    beats = [{"narration": "alpha beta gamma delta epsilon zeta eta theta", "scene": {"type": "demo_el", "props": {"title": "A", "items": ["a", "b"]}}} for _ in range(2)]
    assert any("twice in a row" in w for w in plan_mod.enforce_elements(beats))


def test_an_element_with_anchors_gets_cues_from_the_words_that_name_its_items(demo):
    props = {"title": "T", "items": ["rivers", "bridges"]}
    words = [["The", 0.4, 0.6], ["rivers", 0.7, 1.2], ["and", 1.3, 1.4], ["bridges", 3.0, 3.6]]
    found = sync.apply("demo_el", props, words, 8.0)
    assert found["items"] == 2 and found["anchored"] == 2 and len(props["cues"]) == 2 and props["cues"][1] > props["cues"][0] + 1.0


def test_timeline_merges_what_prepare_fetched_and_falls_back_when_it_failed(demo):
    plan = {"beats": [{"id": "b1", "narration": "words " * 20, "scene": {"type": "demo_el", "props": {"title": "T", "items": ["a", "b"]}}},
                      {"id": "b2", "narration": "words " * 20, "scene": {"type": "demo_el", "props": {"title": "T2", "items": ["a", "b"]}}}], "mood": "calm", "theme": "paper"}
    infos = [{"duration": 6.0, "element": {"extra": 42}}, {"duration": 6.0, "element_failed": True}]
    tl = tl_mod.build_timeline(plan, infos, video_id="v")
    assert tl["scenes"][0]["type"] == "demo_el" and tl["scenes"][0]["props"]["extra"] == 42
    assert tl["scenes"][1]["type"] == "title" and tl["scenes"][1]["props"]["title"] == "T2"
    infos2 = tl_mod.beat_info_from_plan({"beats": [{"id": "x", "media": {"duration": 3, "element": {"k": 1}, "element_failed": False}}]})
    assert infos2[0]["element"] == {"k": 1} and infos2[0]["element_failed"] is False


def test_the_scene_renders_through_the_real_renderer(demo):
    props = demo.sanitize({"title": "Hello", "items": ["one", "two"]})
    assert changed(render("demo_el", props, 0.0), render("demo_el", props, 4.0)) > 0.0008


def test_register_rejects_bad_names():
    for bad in ("", "Has-Dash", "UPPER", "sp ace"):
        with pytest.raises(ValueError):
            registry.register(_demo(name=bad))


def test_the_credits_ledger_includes_photos_shown_by_elements():
    from engine.handlers.timeline_handler import credits_ledger
    plan = {"beats": [
        {"scene": {"type": "image"}, "media": {"ledger": {"id": "img"}}},
        {"scene": {"type": "gallery"}, "media": {"gallery": [{"ledger": {"id": "g1"}}, {}, {"ledger": {"id": "g2"}}]}},
        {"scene": {"type": "annotated_image"}, "media": {"element": {"ledger": {"id": "annot"}, "pins": []}}},
        {"scene": {"type": "annotated_image"}, "media": {"element": {"ledger": {"id": "gone"}}, "element_failed": True}},
        {"scene": {"type": "title"}, "media": {}}]}
    assert [e["id"] for e in credits_ledger(plan)] == ["img", "g1", "g2", "annot"]
