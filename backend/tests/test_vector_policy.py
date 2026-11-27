"""The cartoon-scene policy (engine/vector_policy.py, docs/VECTOR_SCENE_POLICY.md): who may be offered them, the prompt block, plan sanitising and the final pass."""
import pytest

from engine import director, plan as plan_mod, vector_policy as vp

CANDS = [
    {"id": "pine_forest_valley", "title": "Pine forest valley", "category": "nature", "mood": "calm", "score": 0.52},
    {"id": "mountain_lake", "title": "Mountain lake", "category": "nature", "mood": "calm", "score": 0.44},
    {"id": "flower_meadow", "title": "Flower meadow", "category": "nature", "mood": "cheerful", "score": 0.40},
]


def fake_search(query, aspect="16:9", k=5):
    return [dict(c) for c in CANDS[:k]]


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setenv("VECTOR_SCENES", "1")


def decide(prompt="Explain how plants grow, for kids", skills=("kids-family",), **kw):
    kw.setdefault("search", fake_search)
    return vp.decide(prompt, skill_ids=list(skills), minutes=3, expected_beats=10, **kw)


# ---------------------------------------------------------------- the switch and the hard rules
def test_flag_off_never_offers_anything(monkeypatch):
    monkeypatch.delenv("VECTOR_SCENES", raising=False)
    p = decide()
    assert not p.allowed and p.reason == "flag_off" and p.prompt_block() == ""


def test_kids_topic_is_offered_with_a_bigger_share(on):
    p = decide()
    assert p.allowed and p.share == vp.SHARE_KIDS and p.first_ok and p.reason == "kids"
    assert "- vector_scene:" in p.prompt_block() and "pine_forest_valley" in p.prompt_block()


def test_light_topic_gets_the_small_share_and_never_the_first_beat(on):
    p = decide("How does the internet work, simply?", skills=("explainer-education",))
    assert p.allowed and p.share == vp.SHARE_AUTO and not p.first_ok
    assert "RARELY" in p.prompt_block() and "never the first beat" in p.prompt_block()


@pytest.mark.parametrize("skill", ["news-explainer", "product-marketing", "history-story", "biography-profile", "coding-tutorial", "photo-memories", "comparison-versus", "mystery-true-crime"])
def test_serious_or_real_topics_never_in_auto(on, skill):
    p = decide("whatever", skills=(skill,), ask=lambda s, u: '{"fit": true, "kind": "concept", "why": "x"}')   # even a yes from the judge cannot rescue them
    assert not p.allowed and p.reason.startswith("serious_topic")


@pytest.mark.parametrize("skill", ["science-wonder", "tutorial-howto", "listicle-ranking", "finance-business"])
def test_ambiguous_guides_need_the_judge(on, skill):
    assert decide("x", skills=(skill, "explainer-education")).reason == "serious_topic:" + skill   # no judge available: never
    yes = decide("x", skills=(skill, "explainer-education"), ask=lambda s, u: '{"fit": true, "kind": "concept", "why": "everyday idea"}')
    assert yes.allowed and yes.reason == "judged:concept" and yes.judged["fit"]
    no = decide("x", skills=(skill, "explainer-education"), ask=lambda s, u: '{"fit": false, "kind": "other", "why": "needs real photographs"}')
    assert not no.allowed and no.reason == "not_suited:needs real photographs"


def test_kids_guide_beats_an_ambiguous_one_even_without_a_judge(on):
    assert decide("x", skills=("kids-family", "science-wonder")).allowed


def test_judge_failure_or_garbage_means_no(on):
    def boom(s, u):
        raise RuntimeError("down")
    assert not decide(ask=boom).allowed
    assert not decide(ask=lambda s, u: "I think so!").allowed
    assert not decide(ask=lambda s, u: '{"fit": "true"}').allowed   # only a real true counts
    assert decide(ask=lambda s, u: '{"fit": true, "kind": "kids", "why": "children"}').allowed


def test_cartoon_request_is_never_second_guessed_but_the_judge_still_names_the_setting(on):
    seen = []

    def spy(q, aspect, k):
        seen.append(q)
        return fake_search(q, aspect, k)
    p = decide("make it a cartoon about money", ask=lambda s, u: '{"fit": false, "kind": "other", "why": "x", "scene": "a quiet city street"}', search=spy)
    assert p.allowed and "a quiet city street" in seen   # fit=false is ignored for a cartoon request; the setting widens the search


def test_search_uses_the_setting_from_the_judge_and_keeps_the_best_score_per_scene(on):
    def search(q, aspect, k):
        return [{"id": "mountain_lake", "title": "Lake", "category": "n", "mood": "calm", "score": 0.5 if "lake" in q else 0.33}, {"id": "flower_meadow", "title": "Meadow", "category": "n", "mood": "c", "score": 0.4}]
    p = decide("explain tides", skills=("explainer-ed" "ucation",), ask=lambda s, u: '{"fit": true, "kind": "concept", "why": "x", "scene": "a calm lake shore"}', search=search)
    assert p.ids() == ["mountain_lake", "flower_meadow"] and p.candidates[0]["score"] == 0.5


def test_an_empty_search_is_retried_once(on):
    calls = []

    def flaky(q, aspect, k):
        calls.append(1)
        return [] if len(calls) == 1 else fake_search(q, aspect, k)
    assert decide(search=flaky).allowed and len(calls) == 2


def test_soft_match_floor_for_kids_and_cartoon_only(on):
    low = lambda q, a, k: [{"id": "mountain_lake", "title": "Lake", "category": "nature", "mood": "calm", "score": 0.26}]
    assert decide(search=low).allowed                                   # kids
    assert decide("make it a cartoon", search=low).allowed              # cartoon
    assert decide("explain tides", skills=("explainer-education",), search=low).reason == "no_catalog_match"


def test_one_serious_guide_among_light_ones_blocks(on):
    assert not decide(skills=("kids-family", "news-explainer")).allowed


def test_current_events_linkedin_user_media_and_decks_never(on):
    assert decide(research_mode="web").reason == "current_events"
    assert decide(options={"platform": "linkedin"}).reason == "platform_linkedin"
    assert decide(photos=[{"id": "x"}]).reason == "user_media"
    assert decide(options={"deck": "abc"}).reason == "deck"


def test_too_short_in_auto(on):
    p = vp.decide("explain tides", skill_ids=["explainer-education"], minutes=0.5, expected_beats=3, search=fake_search)
    assert not p.allowed and p.reason == "too_short"
    assert vp.decide("explain tides", skill_ids=["kids-family"], minutes=0.5, expected_beats=3, search=fake_search).allowed


def test_no_catalog_match_or_a_search_failure_means_no_menu(on):
    assert decide(search=lambda *a, **k: []).reason == "no_catalog_match"
    assert decide(search=lambda *a, **k: [{"id": "x_scene", "score": 0.1}]).reason == "no_catalog_match"

    def boom(*a, **k):
        raise RuntimeError("bedrock down")
    assert decide(search=boom).reason == "no_catalog_match"


# ---------------------------------------------------------------- the person's own words
@pytest.mark.parametrize("text,style", [
    ("Make it a cartoon about recycling", "cartoon"), ("a video in an illustrated style about bees", "cartoon"), ("Un vídeo con dibujos animados sobre el sol", "cartoon"),
    ("estilo ilustrado, por favor", "cartoon"), ("use real footage of bees", "real"), ("no cartoons, only real photos", "real"), ("sin dibujos ni animaciones", "real"),
    ("imágenes reales de la ciudad", "real"), ("real footage and a cartoon intro", "real"), ("explain how bees make honey", "auto"), ("illustrate how a bill becomes law", "auto"),
])
def test_prompt_can_ask_for_a_style(text, style):
    assert vp.resolve_style(None, text) == style
    assert vp.resolve_style("auto", text) == style


def test_the_option_beats_the_words():
    assert vp.resolve_style("real", "make it a cartoon") == "real"
    assert vp.resolve_style("cartoon", "real footage please") == "cartoon"
    assert vp.resolve_style("bogus", "x") == "auto"


def test_explicit_cartoon_is_offered_even_for_a_serious_guide_but_never_with_media_or_real(on):
    p = decide("Make it a cartoon about money", skills=("finance-business",))
    assert p.allowed and p.style == "cartoon" and p.share == vp.SHARE_CARTOON and p.first_ok
    assert len(p.candidates) == 3   # the fake catalog has three
    assert not decide("Make it a cartoon", skills=("kids-family",), photos=[{"id": "p"}]).allowed
    assert not decide("Make it a cartoon", options={"style": "real"}).allowed
    assert decide("Make it a cartoon about news", research_mode="web", skills=("news-explainer",)).allowed   # the person asked; the prompt block still forbids serious beats


def test_cartoon_menu_is_bigger(on):
    seen = {}

    def spy(q, aspect, k):
        seen["k"] = k
        return fake_search(q, aspect, k)
    decide("make it a cartoon", search=spy)
    assert seen["k"] == vp.MENU_CARTOON
    decide("how plants grow", search=spy)
    assert seen["k"] == vp.MENU_AUTO


def test_spanish_and_english_requests_are_decided_the_same_way(on):
    assert decide("Explícame cómo crecen las plantas, para niños").allowed
    assert decide("Explain how plants grow, for kids").allowed


# ---------------------------------------------------------------- plan sanitising (only while a policy is in force)
def vs_beat(cid, text="A quiet valley wakes up under the morning light, and everything slowly begins."):
    return {"narration": text, "scene": {"type": "vector_scene", "props": {"catalog_id": cid, "alt": "quiet valley at sunrise"}}}


def text_beat(i):
    return {"narration": f"Beat number {i} says something clear about the topic at hand today.", "scene": {"type": "title", "props": {"title": f"Part {i}"}}}


def make_plan(beats):
    return {"legit": True, "title": "t", "description": "d", "mood": "calm", "theme": "midnight", "voices": {"narrator": "Ruth"}, "beats": beats}


def test_vector_scene_is_rejected_without_a_policy():
    plan, warns = plan_mod.validate_plan(make_plan([text_beat(1), vs_beat("pine_forest_valley"), text_beat(3)]))
    assert plan["beats"][1]["scene"]["type"] != "vector_scene"
    assert any("scene replaced" in w for w in warns)


def test_vector_scene_props_are_cleaned_inside_a_scope(on):
    pol = decide()
    with vp.scope(pol):
        plan, warns = plan_mod.validate_plan(make_plan([text_beat(1), {"narration": vs_beat("x")["narration"], "scene": {"type": "vector_scene", "props": {"catalog_id": " Pine_Forest_Valley ", "seconds": 99, "motion": "evil", "extra": 1}}}, text_beat(3)]))
    props = plan["beats"][1]["scene"]["props"]
    assert plan["beats"][1]["scene"]["type"] == "vector_scene"
    assert props == {"catalog_id": "pine_forest_valley", "motion": "default", "seconds": vp.MAX_SECONDS}


@pytest.mark.parametrize("bad", ["../etc/passwd", "forest_path", "", None, "PINE FOREST", "a" * 80])
def test_unknown_or_hostile_ids_fall_back(on, bad):
    with vp.scope(decide()):
        plan, warns = plan_mod.validate_plan(make_plan([text_beat(1), {"narration": vs_beat("x")["narration"], "scene": {"type": "vector_scene", "props": {"catalog_id": bad, "alt": "quiet valley at sunrise"}}}, text_beat(3)]))
    assert plan["beats"][1]["scene"]["type"] != "vector_scene"


def test_scope_restores_the_previous_policy(on):
    assert vp.active() is None
    with vp.scope(decide()):
        assert vp.active() is not None
    assert vp.active() is None


# ---------------------------------------------------------------- the final pass: share, adjacency, first beat
def validated(beats, pol):
    with vp.scope(pol):
        plan, _ = plan_mod.validate_plan(make_plan(beats))
    return plan


def test_enforce_share_cap_adjacency_and_first_beat(on):
    pol = decide("How does the internet work, simply?", skills=("explainer-education",))   # share 0.2
    beats = [vs_beat("pine_forest_valley")] + [text_beat(i) for i in range(1, 4)] + [vs_beat("mountain_lake"), text_beat(5), vs_beat("flower_meadow")] + [text_beat(i) for i in range(7, 10)]
    plan = validated(beats, pol)
    warns = vp.enforce(plan, pol)
    types = [b["scene"]["type"] for b in plan["beats"]]
    assert types[0] != "vector_scene"                    # never the first beat
    assert types.count("vector_scene") == pol.cap(len(beats)) == 2
    assert not any(a == b == "vector_scene" for a, b in zip(types, types[1:]))
    assert plan["vector"]["used"] and plan["vector"]["decision"] == "offered" and plan["vector"]["cap"] == 2
    assert any("first beat" in w for w in warns) or any("two in a row" in w for w in warns)


def test_enforce_never_two_in_a_row(on):
    pol = decide("make it a cartoon", skills=("explainer-education",))
    plan = validated([text_beat(0), vs_beat("mountain_lake"), vs_beat("flower_meadow"), text_beat(3), text_beat(4)], pol)
    warns = vp.enforce(plan, pol)
    types = [b["scene"]["type"] for b in plan["beats"]]
    assert types[1] == "vector_scene" and types[2] != "vector_scene" and any("two in a row" in w for w in warns)


def test_enforce_kids_may_open_with_one_and_over_cap_is_trimmed(on):
    pol = decide()
    beats = [vs_beat("pine_forest_valley")] + [vs_beat("mountain_lake") if i % 2 == 0 else text_beat(i) for i in range(1, 9)] + [vs_beat("flower_meadow")]
    plan = validated(beats, pol)
    vp.enforce(plan, pol)
    n = [b["scene"]["type"] for b in plan["beats"]].count("vector_scene")
    assert n <= pol.cap(len(plan["beats"])) == 4 and plan["beats"][0]["scene"]["type"] == "vector_scene"


def test_enforce_without_a_policy_removes_every_cartoon_scene(on):
    pol = decide()
    plan = validated([text_beat(1), vs_beat("pine_forest_valley"), text_beat(3)], pol)
    warns = vp.enforce(plan, None)
    assert all(b["scene"]["type"] != "vector_scene" for b in plan["beats"]) and warns
    assert "vector" not in plan


def test_enforce_same_scene_at_most_twice(on):
    pol = decide("make it a cartoon", skills=("explainer-education",))
    beats = [text_beat(0), vs_beat("pine_forest_valley"), text_beat(2), vs_beat("pine_forest_valley"), text_beat(4), vs_beat("pine_forest_valley"), text_beat(6), text_beat(7)]
    plan = validated(beats, pol)
    vp.enforce(plan, pol)
    assert [b["scene"].get("props", {}).get("catalog_id") for b in plan["beats"]].count("pine_forest_valley") == 2


def test_flag_off_leaves_no_trace(monkeypatch):
    monkeypatch.delenv("VECTOR_SCENES", raising=False)
    pol = vp.decide("x", skill_ids=["kids-family"], search=fake_search)
    plan = make_plan([text_beat(1), text_beat(2)])
    assert vp.enforce(plan, pol) == [] and "vector" not in plan


def test_replacement_is_a_photo_when_the_beat_has_a_caption(on):
    pol = decide()
    plan = validated([text_beat(1), vs_beat("pine_forest_valley")], pol)
    vp.enforce(plan, None)
    sc = plan["beats"][1]["scene"]
    assert sc["type"] == "image" and sc["props"]["image_query"].startswith("quiet valley")


# ---------------------------------------------------------------- the director wires it in
def test_director_offers_the_menu_only_when_allowed_and_records_the_result(on, monkeypatch):
    seen = {}

    def ask_small(system, user, max_tokens=120):
        if "CARTOON" in system:   # the policy's fit judge
            return '{"fit": true, "kind": "kids", "why": "children"}'
        return "en"

    def ask_big(system, user):
        seen["system"] = system
        import json
        beats = [text_beat(i) for i in range(1, 6)]
        beats[2] = vs_beat("mountain_lake")
        return json.dumps(make_plan(beats))

    monkeypatch.setattr(director.research, "gather_notes", lambda *a, **k: ("notes", []))
    monkeypatch.setattr(director.skills_mod, "select", lambda *a, **k: ["kids-family"])
    r = director.direct("Explain how plants grow, for kids", minutes=1.0, ask_small=ask_small, ask_big=ask_big, language="en", vector_search=fake_search)
    assert r["legit"]
    assert "- vector_scene:" in seen["system"] and "mountain_lake" in seen["system"]
    assert r["plan"]["vector"]["used"] == [{"beat": 2, "id": "mountain_lake"}]
    assert r["plan"]["beats"][2]["scene"]["props"]["catalog_id"] == "mountain_lake"


def test_director_flag_off_prompt_is_unchanged(monkeypatch):
    monkeypatch.delenv("VECTOR_SCENES", raising=False)
    seen = {}

    def ask_big(system, user):
        seen["system"] = system
        import json
        return json.dumps(make_plan([text_beat(i) for i in range(1, 6)]))

    monkeypatch.setattr(director.research, "gather_notes", lambda *a, **k: ("notes", []))
    monkeypatch.setattr(director.skills_mod, "select", lambda *a, **k: ["kids-family"])
    r = director.direct("Explain how plants grow, for kids", minutes=1.0, ask_small=lambda s, u, n=120: "en", ask_big=ask_big, language="en", vector_search=fake_search)
    assert "vector_scene" not in seen["system"] and "vector" not in r["plan"]


# ---------------------------------------------------------------- the options
def test_style_option_is_validated():
    import sf_launcher as sf
    assert sf.validate_options({"style": "cartoon"})["style"] == "cartoon"
    assert "style" not in sf.validate_options({"style": "auto"})
    assert "style" not in sf.validate_options({})
    with pytest.raises(sf.BadRequest):
        sf.validate_options({"style": "pixar"})
    with pytest.raises(sf.BadRequest):
        sf.validate_options({"style": 3})


def test_element_accepts_the_catalog_id_prop():
    from engine.scenes import ELEMENTS
    out = ELEMENTS["vector_scene"].sanitize({"catalog_id": "pine_forest_valley"})
    assert out.get("catalog_id") == "pine_forest_valley"
