import json
import re

import pytest

from engine import director, plan as plan_mod, skills, staged

from tests.test_staged import FakeModel


def test_every_skill_file_is_well_formed_small_and_unique():
    sk = skills.load()
    assert len(sk) >= 16
    always = [s for s in sk.values() if s.always]
    assert [s.id for s in always] == ["publish-quality"], "exactly one always-on guide"
    for s in sk.values():
        assert s.name and s.body and len(s.body) <= skills.MAX_BODY_CHARS, (s.id, len(s.body))
        assert re.match(r"^[a-z][a-z0-9-]+$", s.id)
        assert s.always or s.auto or len(s.pick) >= 20, f"{s.id} needs a 'pick' line the selector can use"
        assert s.body.lstrip().startswith("- "), f"{s.id} should be imperative bullets"
        assert "TODO" not in s.body and "{" not in s.body and "}" not in s.body
    assert skills.DEFAULT_SKILL in sk


def test_the_catalog_for_the_selector_lists_every_type_and_never_the_always_on_guide():
    cat = skills.catalog_text()
    for s in skills.load().values():
        assert (f"- {s.id}:" in cat) == (not s.always and not s.auto)


@pytest.mark.parametrize("answer,expected", [
    ('{"types": ["news-explainer"]}', ["news-explainer"]),
    ('{"types": ["history-story", "product-marketing", "funny-light"]}', ["history-story", "product-marketing"]),   # at most two
    ('Sure! {"types": ["coding-tutorial"]} hope that helps', ["coding-tutorial"]),
    ('{"types": ["publish-quality", "made-up", "kids-family", "kids-family"]}', ["kids-family"]),                   # not the always-on one, no invented ids, no duplicates
    ('{"types": []}', ["explainer-education"]),
    ("I think this is about history", ["explainer-education"]),
    ("", ["explainer-education"]),
    ('{"types": "news-explainer"}', ["explainer-education"]),
])
def test_the_producer_picks_one_or_two_valid_guides_and_defaults_safely(answer, expected):
    seen = {}
    def ask(system, user):
        seen["system"], seen["user"] = system, user
        return answer
    assert skills.select("a request", ask, 5) == expected
    assert "- news-explainer:" in seen["system"] and "a request" in seen["user"] and "5 minutes" in seen["user"]


def test_a_failing_selector_never_stops_a_video():
    def boom(system, user):
        raise RuntimeError("model down")
    assert skills.select("x", boom) == ["explainer-education"]


def test_the_rendered_craft_text_has_the_always_on_guide_first_then_the_picked_ones():
    t = skills.render(["news-explainer", "history-story"])
    assert t.index("Publish quality") < t.index("News and current affairs") < t.index("History")
    assert "use one only if it appears in the scene list above" in t
    assert skills.render([]).count("###") == 1 and "Publish quality" in skills.render([])
    assert skills.render(["nope"]).count("###") == 1                         # an unknown id is ignored


def _ask_small(types):
    def ask(system, user, n=120):
        if "producer of an AI explainer-video studio" in system:
            return json.dumps({"types": types})
        return "en"
    return ask


def test_the_director_gives_the_chosen_guides_to_the_model_and_records_them():
    prompts = []
    def one_call(system, user):
        prompts.append(system)
        return json.dumps({"legit": True, "title": "T", "description": "d", "voices": {"narrator": "Ruth"}, "beats": [
            {"narration": " ".join(["w"] * 30), "scene": {"type": "title", "props": {"title": "x"}}} for _ in range(14)]})
    out = director.direct("What happened in the news today", minutes=3.0, ask_small=_ask_small(["news-explainer"]), ask_big=one_call, language="en")
    assert out["plan"]["skills"] == ["news-explainer"] and out["research"]["skills"] == ["news-explainer"]
    assert "Inverted pyramid" in prompts[0] and "Publish quality" in prompts[0] and "History" not in prompts[0].split("Craft guides")[1]


def test_a_long_video_gives_the_guides_to_the_outline_and_every_section():
    model = FakeModel(5.0, 3)
    seen = []
    def spy(system, user):
        seen.append(system)
        return model(system, user)
    out = director.direct("The history of the Roman Empire", minutes=5.0, ask_small=_ask_small(["history-story"]), ask_big=spy, language="en")
    assert out["plan"]["skills"] == ["history-story"]
    assert len(seen) == 4 and all("Craft guides for this video" in s and "Publish quality" in s for s in seen)
    assert all("Tell it as a story with people in it" in s for s in seen)


def test_the_photo_guide_is_automatic_never_offered_to_the_selector_and_always_added_with_photos():
    sk = skills.load()
    assert sk["photo-memories"].auto and "photo-memories" not in skills.catalog_text()
    assert skills.select("a video of my trip", lambda s, u: '{"types": ["photo-memories", "travel-places"]}') == ["travel-places"]      # the model cannot pick it
    prompts = []
    def one_call(system, user):
        prompts.append(system)
        return json.dumps({"legit": True, "title": "T", "description": "d", "voices": {"narrator": "Ruth"}, "beats": [
            {"narration": " ".join(["w"] * 30), "scene": {"type": "image", "props": {"photo": "P1", "image_query": "a street", "alt": "a"}}} for _ in range(3)]})
    photos = [{"id": "P1", "key": "k", "w": 600, "h": 400, "orientation": "landscape", "caption": "a street"}]
    out = director.direct("my trip to Paris", minutes=1.0, ask_small=_ask_small(["travel-places"]), ask_big=one_call, language="en", photos=photos)
    assert out["plan"]["skills"][0] == "photo-memories" and "Let the pictures breathe" in prompts[0] and "Say less than the pictures show" in prompts[0]
    assert out["plan"]["intro_s"] == 2.5 and out["plan"]["outro_s"] == 3.5
    no_photos = director.direct("how rainbows form", minutes=1.0, ask_small=_ask_small(["explainer-education"]), ask_big=one_call, language="en")
    assert "photo-memories" not in no_photos["plan"]["skills"] and "intro_s" not in no_photos["plan"]
