"""Presenter characters in real videos (docs/PRESENTERS.md): the `presenter` scene, who is cast and when, the words that ask for one (English and Spanish), the
create option, what capabilities lists, the stack's switch, and that a frame is the same whenever and wherever it is rendered."""
import json
import os

import pytest

from common import looks
from engine import align, format_options, presenter_policy as pp, vector_presenter as vp
from engine.renderer import Renderer
from engine.scenes import ELEMENTS
from engine.scenes.elements import presenter as el
from engine.timeline import build_timeline

pytest.importorskip("resvg_py")
E = ELEMENTS["presenter"]
TEXT = "Hello! Why is the sky blue? First, sunlight is every colour. Second, the air scatters blue the most, but red goes straight on. Look at this!"


@pytest.fixture(autouse=True)
def fresh(monkeypatch):
    monkeypatch.setenv("PRESENTERS", "1")
    el.release()
    yield
    el.release()


def timeline(props, aspect="16:9", resolution="720p", dur=8.0, speech=True):
    fr = format_options.frame_dict(aspect, resolution, None)
    words = [list(w) for w in align.estimate_words(TEXT, dur - 1.2, lead=0.4)]
    p = E.sanitize(dict(props))
    scenes = [{"id": "s1", "type": "presenter", "start": 0.0, "duration": dur, "props": p, "words": words if speech else []}]
    pp.link(scenes)
    return {"fps": 30, "width": fr["width"], "height": fr["height"], "frame": fr, "theme": "midnight", "captions": True, "outro": False, "scenes": scenes}


# ----------------------------------------------------------------------------- the scene
def test_props_are_cleaned_idempotent_and_refused_when_empty():
    for s in E.samples:
        once = E.sanitize(dict(s))
        assert E.sanitize(dict(once)) == once and once["character"] in el.CAST and once["side"] in ("left", "right")
    with pytest.raises(ValueError):
        E.sanitize({})
    with pytest.raises(ValueError):
        E.sanitize({"character": "fox"})
    p = E.sanitize({"character": "dragon", "side": "top", "framing": "x", "heading": "h" * 90, "points": ["a", "", 3, {"x": 1}, "b" * 99, "c", "d", "e"], "speech": [["x", 0, 1]], "evil": 1})
    assert p["character"] == "ines" and p["side"] == "left" and p["framing"] == "auto" and len(p["heading"]) == 48 and p["points"] == ["a", "3", "b" * 60, "c"] and "speech" not in p and "evil" not in p
    c = E.sanitize({"heading": "Load", "chart": {"labels": ["A", "B", "C"], "values": [1, "2.5", "x"], "unit": "seconds"}, "image_query": "ignored with a chart"})
    assert c["chart"] == {"labels": ["A", "B"], "values": [1.0, 2.5], "unit": "second"} and "image_query" not in c
    assert E.anchors(E.sanitize({"heading": "h", "points": ["one", "two"]})) == ["one", "two"] and E.cues(E.sanitize({"heading": "h"}), 6.0) == []
    assert E.hidden and E.formats == ("16:9", "9:16", "1:1", "4:5")
    assert E.fallback({"character": "fox", "side": "left", "image_query": "red fox in snow"}) == ("presenter", {"character": "fox", "side": "left", "heading": "red fox in snow"})


@pytest.mark.parametrize("aspect", ["16:9", "9:16", "1:1", "4:5"])
def test_it_draws_the_character_beside_the_card_in_every_shape(aspect):
    tl = timeline(E.samples[0], aspect)
    r = Renderer(tl)
    with_char = r.frame_at(4.0)
    el._BROKEN["ines"] = "test"   # the same frame without the character: what differs is the character
    without = Renderer(tl).frame_at(4.0)
    el._BROKEN.clear()
    import numpy as np
    diff = np.abs(np.asarray(with_char, dtype=np.int16) - np.asarray(without, dtype=np.int16)).sum(axis=2) > 40
    assert 0.02 < diff.mean() < 0.45                       # a figure, not a speck and not the whole frame (9:16: the whole figure, small, under the card)
    ys, xs = np.nonzero(diff)
    lay = el.layout(tl["scenes"][0]["props"], r.ctx)
    k = with_char.width / r.frame.W
    x0, _y0, x1, _y1 = [v * k for v in lay["content"]]
    inside = ((xs > x0 + 40 * k) & (xs < x1 - 40 * k) & (ys > lay["content"][1] * k + 40 * k) & (ys < lay["content"][3] * k - 40 * k)).mean()
    assert inside < 0.12, inside                           # the character does not stand on the card (a presenting hand may reach its edge)


def test_a_frame_is_the_same_whenever_and_wherever_it_is_rendered():
    tl = timeline(E.samples[0])
    r = Renderer(tl)
    times = [0.3, 2.0, 3.7, 5.1, 7.9]
    first = [r.frame_at(t).tobytes() for t in times]
    assert len(set(first)) == len(times)                   # it moves
    el.release()                                           # another chunk, another container: nothing kept from before
    again = [Renderer(tl).frame_at(t).tobytes() for t in reversed(times)]   # and in another order (a warm cache holds other pieces)
    assert again[::-1] == first
    held = Renderer(tl).frame_at(8.0 + 0.2).tobytes()       # the outgoing scene held under a crossfade: past its end
    el.release()
    assert Renderer(tl).frame_at(8.2).tobytes() == held


def test_memory_is_bounded_and_the_cache_is_used():
    c = vp.TurnCache(max_bytes=1 << 20)
    from PIL import Image
    for i in range(40):
        c.put(("k", i), Image.new("RGBA", (128, 128)), (0.0, 0.0))
    assert c.bytes <= (1 << 20) and len(c.d) <= 16 and c.get(("k", 39)) is not None and c.get(("k", 0)) is None
    tl = timeline(E.samples[0])
    r = Renderer(tl)
    for f in range(0, 240, 4):
        r.frame_at(f / 30)
    ch = vp.load_cached("ines", round(el.layout(tl["scenes"][0]["props"], r.ctx)["ppu"], 4), 1.0)   # 720p from a 1920-wide design: one design unit is one layer pixel
    assert ch.cache.hits > ch.cache.misses and ch.cache.bytes <= 48 << 20
    assert vp.load_cached.cache_info().maxsize == 4 and len(el._PERF) <= 16
    assert vp.load("ines", 2.0).cache is None              # the exact rig of the review clips is untouched


def test_the_mouth_follows_the_words_and_gestures_come_from_them():
    words = [("Hello", 0.5, 0.9), ("everybody", 1.0, 1.6)]
    m = el.mouth_track(words, 3.0)
    assert m[0] == "closed" and m[int(0.95 * 30)] == "closed" and m[-1] == "closed" and "wide" in m[int(0.5 * 30):int(0.9 * 30)] and set(m) <= {"closed", "half", "wide"}
    tl = timeline(E.samples[0])
    p = tl["scenes"][0]["props"]
    assert p["speech"] and p["enter"] is True and 0 <= p["seed"] < 1
    perf = el.performance(p, 8.0, 0.14, "left")
    assert perf is el.performance(p, 8.0, 0.14, "left") and perf.gestures and perf.content_side == 1
    kinds = {g.kind for g in perf.gestures}
    assert kinds & {"wave", "count", "present", "compare"}, kinds


def test_no_words_is_a_quiet_presenter_and_a_missing_character_never_fails(monkeypatch):
    tl = timeline(E.samples[1], speech=False)
    assert Renderer(tl).frame_at(2.0).size == (1280, 720)
    monkeypatch.setattr(vp, "DIR", "/nonexistent")
    el.release()
    assert Renderer(tl).frame_at(2.0).size == (1280, 720) and "fox" in el._BROKEN


# ----------------------------------------------------------------------------- who, and when
@pytest.mark.parametrize("prompt,skills,want", [
    ("Explain why the sky is blue, with a presenter", ["explainer-education", "science-wonder"], "ines"),
    ("How vaccines train your body, with a presenter", ["health-wellbeing"], "priya"),
    ("How to cache a web app, with a presenter", ["coding-tutorial"], "david"),
    ("A quick pasta recipe, with a presenter", ["tutorial-howto"], "mateo"),
    ("The water cycle for kids, with a character", ["kids-family"], "fox"),
    ("Something silly and fun about socks, con personajes", ["funny-light"], "fox"),
    ("Why the sky is blue, explained by a fox", ["science-wonder"], "fox"),
    ("Por qué el cielo es azul, explicado por un zorro", ["science-wonder"], "fox"),
    ("Cómo dormir mejor, con un presentador", ["health-wellbeing"], "priya"),
    ("How compound interest works, with animated characters", ["finance-business"], "ines"),
    # the animal cast: by name anywhere, by topic in children's and fun videos only
    ("Why the sky is blue, explained by an owl", ["science-wonder"], "owl"),
    ("Los planetas, con un búho", ["science-wonder"], "owl"),
    ("Por qué dormimos, explicado por un oso", ["health-wellbeing"], "bear"),
    ("The planets for kids, with a character", ["kids-family"], "owl"),
    ("History of the pyramids for children, with a presenter", ["kids-family", "history-story"], "owl"),
    ("What to do when you feel worried, for kids, with a character", ["kids-family"], "bear"),
    ("Por qué hay que lavarse los dientes, para niños, con personajes", ["kids-family"], "bear"),
    ("How robots work, for kids, with a character", ["kids-family"], "cat"),
    ("Cómo funciona internet, para niños, con un personaje", ["kids-family"], "cat"),
    ("Robots, by a cat", ["science-wonder"], "cat"),
    ("Fun facts about countries for kids, with a character", ["kids-family"], "parrot"),
    ("Aprende los colores en inglés, para niños, con un personaje", ["kids-family"], "parrot"),
    ("Los volcanes, explicado por un loro", ["science-wonder"], "parrot"),
    ("Life in the sea for kids, with a character", ["kids-family"], "turtle"),
    ("How to plant a seed step by step, for kids, with a presenter", ["kids-family"], "turtle"),
    ("Las mareas, con una tortuga", ["science-wonder"], "turtle"),
    ("How sleep works, with a presenter", ["health-wellbeing"], "priya"),              # an adult topic keeps its person
    ("The history of Rome, with a presenter", ["history-story"], "ines"),
    ("How the internet works, with a presenter", ["explainer-education"], "david"),
])
def test_casting_by_topic_and_by_name(prompt, skills, want):
    p = pp.decide(prompt, skill_ids=skills)
    assert p.allowed and p.reason == "asked" and p.character == want


def test_auto_only_where_it_fits_and_never_on_photos_decks_news_or_whiteboard(monkeypatch):
    assert pp.decide("The water cycle for six-year-olds", skill_ids=["kids-family"]).character == "fox"
    assert pp.decide("How to tie a bowline knot", skill_ids=["tutorial-howto"]).allowed
    assert pp.decide("A funny look at why cats knock things over", skill_ids=["funny-light"]).character == "fox"
    for skills in (["explainer-education"], ["science-wonder"], ["finance-business"], ["history-story"], ["travel-places"], ["product-marketing"]):
        assert not pp.decide("How tides work", skill_ids=skills).allowed            # nothing said: no presenter by itself
    ask = "with a presenter"
    assert pp.decide("My trip " + ask, skill_ids=["kids-family"], photos=[{"id": "p1"}]).reason == "user_media"
    assert pp.decide("My deck " + ask, skill_ids=["kids-family"], options={"deck": "d1"}).reason == "deck"
    assert pp.decide("The election results " + ask, skill_ids=["kids-family"], research_mode="web").reason == "current_events"
    assert pp.decide("The crisis " + ask, skill_ids=["news-explainer"]).reason == "kind_of_video"
    assert pp.decide("A murder case " + ask, skill_ids=["mystery-true-crime"]).reason == "kind_of_video"
    assert pp.decide("Tides " + ask, skill_ids=["kids-family"], whiteboard=True).reason == "whiteboard_video"
    assert pp.decide("The water cycle for kids, no presenter", skill_ids=["kids-family"]).reason == "asked_none"
    assert pp.decide("The water cycle for kids", skill_ids=["kids-family"], options={"presenter": "none"}).reason == "asked_none"
    assert pp.decide("How tides work", skill_ids=["science-wonder"], options={"presenter": "mateo"}).character == "mateo"   # the option names one: that one
    assert pp.decide("Tides, explained by a fox", skill_ids=["science-wonder"], options={"presenter": "priya"}).character == "priya"   # the option wins over the words
    # a Spanish children's video with no topic of another animal gets the parrot; fun videos and English ones keep the fox
    assert pp.decide("El ciclo del agua para niños", skill_ids=["kids-family"], language="es").character == "parrot"
    assert pp.decide("Algo divertido sobre calcetines", skill_ids=["funny-light"], language="es").character == "fox"
    assert pp.voice_for("parrot", "es") == "Carlos" and pp.voice_for("owl", "en") == "Brian" and pp.voice_for("bear", "en") == "Stephen"   # Spanish: the lively man (it was Pedro)
    monkeypatch.setenv("PRESENTERS", "0")
    off = pp.decide("The water cycle for kids, explained by a fox", skill_ids=["kids-family"])
    assert not off.allowed and off.reason == "flag_off" and off.prompt_block() == ""


@pytest.mark.parametrize("text,want", [
    ("Explain tides, with a presenter", "any"), ("Explain tides with a character", "any"), ("Tides explained by a fox", "fox"), ("animated characters explain the tides", "any"),
    ("Las mareas, con un presentador", "any"), ("Las mareas con personajes", "any"), ("Las mareas, explicado por un zorro", "fox"), ("Las mareas explicadas por una doctora", "priya"),
    ("A recipe told by a friendly chef", "mateo"), ("Vaccines, with a doctor as the presenter", "priya"), ("Tides, no presenter please", "none"), ("Las mareas, sin presentador", "none"),
    ("A story about a fox who learns to share", None), ("The teachers' strike", None), ("A debate between two characters about pizza", None), ("How tides work", None),
    ("Tides explained by an owl", "owl"), ("Las mareas, con un búho", "owl"), ("Las mareas explicadas por un búho", "owl"), ("Why we sleep, with a bear", "bear"),
    ("Por qué dormimos, explicado por un oso", "bear"), ("Feelings, told by a friendly bear", "bear"), ("A story about an owl who learns to fly", None),
    ("A story with a bear who loses his hat", None), ("Why owls hunt at night", None), ("Los osos polares", None),
    ("Robots, by a cat", "cat"), ("Cómo funciona un motor, con un gato", "cat"), ("Countries of the world, explained by a parrot", "parrot"), ("Los colores, con un loro", "parrot"),
    ("The sea, hosted by a wise turtle", "turtle"), ("El mar, explicado por una tortuga", "turtle"), ("Why cats purr", None), ("Sea turtles and their long journey", None),
])
def test_the_words_that_ask_for_a_presenter_in_english_and_spanish(text, want):
    assert looks.presenter_wish(text) == want
    assert pp.wish(None, text) == (want or "auto")


def beats(*types):
    return [{"id": f"b{i}", "narration": f"Line {i} of the script goes here.", "scene": {"type": t, "props": dict(p)}} for i, (t, p) in enumerate(types)]


def test_enforce_sets_character_voice_cap_and_opens_and_closes_with_the_presenter():
    pol = pp.decide("The water cycle for kids, explained by a fox", skill_ids=["kids-family"], language="en")
    pres = ("presenter", {"heading": "A point", "points": ["one thing", "another thing"]})
    plan = {"language": "en", "voices": {"narrator": "Matthew"}, "beats": beats(("title", {"title": "The water cycle", "subtitle": "x"}), pres, pres, ("image", {"image_query": "rain cloud"}), pres, pres,
                                                                               ("clip", {"clip_query": "river"}), pres, ("bullets", {"heading": "Remember", "items": ["Rain falls", "Rivers run", "Sun lifts"]}))}
    with pp.scope(pol):
        for b in plan["beats"]:
            if b["scene"]["type"] == "presenter":
                b["scene"]["props"] = E.sanitize(b["scene"]["props"])
        w = pp.enforce(plan, pol)
    types = [b["scene"]["type"] for b in plan["beats"]]
    assert types[0] == "presenter" and types[-1] == "presenter" and plan["beats"][0]["scene"]["props"]["heading"] == "The water cycle"
    assert plan["beats"][-1]["scene"]["props"]["points"] == ["Rain falls", "Rivers run", "Sun lifts"]
    assert types.count("presenter") == pol.cap(9) == 3 and not any(a == b == "presenter" for a, b in zip(types, types[1:]))
    assert all(b["scene"]["props"]["character"] == "fox" and b["scene"]["props"]["side"] == "left" for b in plan["beats"] if b["scene"]["type"] == "presenter")
    assert "bullets" in types                                # a presenter scene beyond the cap is the plain scene that shows the same thing
    assert plan["voices"] == {"narrator": "Joanna"} and plan["presenter"] == {"decision": "presenter", "reason": "asked", "asked": True, "character": "fox", "scenes": 3, "of": 9,
                                                                               "cast": {"narrator": "fox"}, "voices": {"narrator": "Joanna"}}
    assert any("became a presenter scene" in x for x in w)
    es = {"language": "es", "voices": {"narrator": "Sergio"}, "beats": beats(pres, ("image", {"image_query": "x y"}), pres)}
    for b in es["beats"]:
        if b["scene"]["type"] == "presenter":
            b["scene"]["props"] = E.sanitize(b["scene"]["props"])
    pp.enforce(es, pp.decide("El ciclo del agua, con una doctora como presentadora", skill_ids=["kids-family"], language="es"))
    assert es["voices"] == {"narrator": "Lupe"} and es["presenter"]["character"] == "priya"
    assert pp.backdrops(plan, ["autumn_forest_path", "lake"]) == 2 and plan["beats"][0]["scene"]["props"]["backdrop"] == "autumn_forest_path"
    off = {"beats": beats(pres)}
    assert pp.enforce(off, pp.Policy(False, "kind_of_video")) == [] and off["presenter"]["decision"] == "no" and "voices" not in off


def test_a_dialogue_gets_one_presenter_per_speaker_each_with_their_own_voice_and_side():
    pol = pp.decide("Two friends argue about pineapple on pizza, with characters", skill_ids=["funny-light"])
    pres = {"heading": "Pineapple?", "points": ["Sweet and salty", "Never on pizza"]}
    plan = {"language": "en", "voices": {"maya": "Ruth", "leo": "Matthew"}, "beats": [
        {"id": "b0", "speaker": "maya", "narration": "I love pineapple on pizza, it is the best.", "scene": {"type": "presenter", "props": E.sanitize(pres)}},
        {"id": "b1", "speaker": "leo", "narration": "No way, fruit does not belong there.", "scene": {"type": "image", "props": {"image_query": "pizza"}}},
        {"id": "b2", "speaker": "leo", "narration": "But I admit it looks rather good.", "scene": {"type": "presenter", "props": E.sanitize(pres)}}]}
    pp.enforce(plan, pol)
    a, b = plan["beats"][0]["scene"]["props"], plan["beats"][2]["scene"]["props"]
    assert a["character"] == "fox" and a["side"] == "left" and b["character"] in set(pp.ANIMALS) - {"fox"} and b["side"] == "right"      # an animal talks with another animal
    assert set(plan["voices"]) == {"maya", "leo"} and plan["voices"]["maya"] != plan["voices"]["leo"] and plan["presenter"]["cast"] == {"maya": "fox", "leo": b["character"]}


def test_the_plan_refuses_a_presenter_scene_unless_the_video_has_one():
    from engine import plan as plan_mod
    raw = {"legit": True, "title": "T", "description": "d", "voices": {"narrator": "Ruth"}, "beats": [
        {"narration": "Hello there, today we look at why the sky is blue, together.", "scene": {"type": "presenter", "props": {"heading": "Why is the sky blue?"}}},
        {"narration": "Sunlight holds every colour and the air scatters the blue part most.", "scene": {"type": "bullets", "props": {"heading": "Why", "items": ["All colours", "Blue scatters"]}}}]}
    clean, warnings = plan_mod.validate_plan(json.loads(json.dumps(raw)), language="en") if hasattr(plan_mod, "validate_plan") else plan_mod._validate_plan(json.loads(json.dumps(raw)), language="en")
    assert clean["beats"][0]["scene"]["type"] != "presenter" and any("presenter is not available" in w for w in warnings)
    with pp.scope(pp.Policy(True, "asked", character="ines")):
        clean, _ = plan_mod._validate_plan(json.loads(json.dumps(raw)), language="en")
    assert clean["beats"][0]["scene"] == {"type": "presenter", "props": {"character": "ines", "side": "left", "framing": "auto", "heading": "Why is the sky blue?"}}
    edit = {**json.loads(json.dumps(raw)), "presenter": {"decision": "presenter", "character": "ines"}}   # an edit of a finished video: no policy scope, the plan says it has one
    clean, _ = plan_mod._validate_plan(edit, language="en")
    assert clean["beats"][0]["scene"]["type"] == "presenter"


def test_the_timeline_gives_each_presenter_scene_its_words():
    plan = {"theme": "midnight", "voices": {"narrator": "Ruth"}, "language": "en", "beats": [
        {"id": "b0", "narration": "Hello! Why is the sky blue?", "scene": {"type": "presenter", "props": E.sanitize({"character": "ines", "heading": "Why is the sky blue?"})}},
        {"id": "b1", "narration": "First, sunlight is every colour. Second, air scatters blue.", "scene": {"type": "presenter", "props": E.sanitize({"character": "ines", "heading": "Two facts", "points": ["Every colour", "Air scatters blue"]})}},
        {"id": "b2", "narration": "That is all.", "scene": {"type": "title", "props": {"title": "The end", "subtitle": ""}}}]}
    tl = build_timeline(plan, [{"duration": 2.4}, {"duration": 4.4}, {"duration": 1.2}], video_id="v")
    a, b, c = tl["scenes"]
    assert [w[0] for w in a["props"]["speech"]] == [w[0] for w in a["words"]] and a["props"]["speech"][0][1] >= 0.39
    assert a["props"]["enter"] is True and b["props"]["enter"] is False and a["props"]["seed"] != b["props"]["seed"] and "speech" not in c["props"]
    assert len(b["props"]["cues"]) == 2 and b["cues"]            # the points appear at the words that name them


# ----------------------------------------------------------------------------- the request, capabilities, the stack
def test_generate_accepts_the_presenter_option(monkeypatch):
    import sf_launcher
    assert sf_launcher.validate_options({"presenter": "fox"})["presenter"] == "fox" and "presenter" not in sf_launcher.validate_options({"presenter": "auto"})
    assert sf_launcher.validate_options({"presenter": "none"})["presenter"] == "none"
    for bad in ("dragon", 3, ["fox"]):
        with pytest.raises(sf_launcher.BadRequest):
            sf_launcher.validate_options({"presenter": bad})


def test_the_look_reading_follows_the_switch_and_the_option(monkeypatch):
    on = looks.resolve("Why the sky is blue, explained by a fox", None, "en")
    assert on["presenter"] is True and on["note"] is None
    assert looks.resolve("How tides work", None, "en", presenter="fox")["presenter"] is True
    assert looks.resolve("Tides, explained by a fox", None, "en", presenter="none")["asked"] == []
    assert "not used for news" in looks.resolve("The news today explained by a fox", None, "en")["note"]
    assert looks.resolve("Mi viaje con un presentador", None, "es", media_count=5)["note"].startswith("Lo hacemos con tus fotos")
    monkeypatch.setenv("PRESENTERS", "0")
    assert "coming soon" in looks.resolve("Why the sky is blue, explained by a fox", None, "en")["note"]


def test_capabilities_lists_the_cast_with_labels_in_both_languages(monkeypatch):
    import capabilities_api
    en, es = capabilities_api.presenter("en", True), capabilities_api.presenter("es", True)
    assert en["param"] == "presenter" and en["default"] == "auto" and en["available"] is True and [o["id"] for o in en["options"]] == ["auto", "none"]
    assert [c["id"] for c in en["cast"]] == list(pp.ORDER) and [c["id"] for c in en["cast"]][:5] == ["ines", "david", "priya", "mateo", "fox"]
    assert [c["name"] for c in en["cast"]] == ["Inés", "David", "Priya", "Mateo", "Fox", "Otto", "Bruno", "Mika", "Paco", "Tula"]
    assert [c["role"] for c in en["cast"]] == ["Teacher", "Engineer", "Doctor", "Chef", "Guide for children", "Owl professor", "Caring bear", "Curious cat", "Travelling parrot", "Wise turtle"]
    assert [c["role"] for c in es["cast"]] == ["Profesora", "Ingeniero", "Doctora", "Chef", "Guía para niños", "Búho profesor", "Oso cariñoso", "Gata curiosa", "Loro viajero", "Tortuga sabia"]
    assert all(c["thumbnail"].startswith("data:image/png;base64,") and len(c["thumbnail"]) < 8000 for c in en["cast"])
    assert en["say"] == "with a presenter" and es["say"] == "con un presentador" and es["options"][1]["label"] == "Sin presentador"
    off = capabilities_api.presenter("en", False)
    assert off["available"] is False and off["note"] == "Presenter characters are coming soon." and len(off["cast"]) == len(pp.ORDER)
    assert set(pp.CAST) == set(el.CAST) == set(pp.ORDER) and set(pp.ANIMALS) < set(pp.ORDER) and set(pp.KIDS_TOPICS) < set(pp.ANIMALS)
    assert {c for c, v in el.CAST.items() if v.get("tail")} == {c for c in pp.ORDER if "tail" in json.load(open(os.path.join(vp.DIR, c, "presenter.json")))}   # the tail sways only where there is one
    import sf_launcher
    assert sf_launcher.PRESENTER_OPTIONS == ("auto", "none") + pp.ORDER
    from engine import voices
    for c in pp.CAST.values():
        for lang, names in c["voices"].items():
            assert all(voices.language_of(n) == lang for n in names), (lang, names)
        assert len(set(c["voices"]["en"])) == len(c["voices"]["en"]) >= 2


def test_the_stack_switch_is_a_variable_on_existing_functions_and_qa_only():
    stages = json.load(open(os.path.join(os.path.dirname(__file__), "..", "stages.json")))
    assert stages["qa"].get("presenters") is True and "presenters" not in stages["prod"]
    import aws_cdk as cdk
    from aws_cdk.assertions import Template
    import sys
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    sys.path.insert(0, root)
    cwd = os.getcwd()
    os.chdir(root)
    try:
        from backend_stack import BackendStack
        os.environ.setdefault("CDK_SKIP_LAYER_CHECK", "1")

        def build(n, extra):
            app = cdk.App(context={"stage": "qa", "engine": "v2"}, outdir=os.path.join(os.environ.get("TMPDIR", "/tmp"), f"vmk-pres-{n}"))
            cfg = {"account": "123456789012", "region": "eu-west-1", "domain": None, "callbackUrls": ["https://qa.videomk.com/auth/callback"], "logoutUrls": ["https://qa.videomk.com/"], **extra}
            return Template.from_stack(BackendStack(app, "videomk-qa", stage="qa", stage_cfg=cfg, env=cdk.Environment(account="123456789012", region="eu-west-1"))).to_json()
        off, on = build(0, {}), build(1, {"presenters": True})
    finally:
        os.chdir(cwd)

    def envs(t):
        return {v["Properties"].get("Handler"): v["Properties"].get("Environment", {}).get("Variables", {}) for v in t["Resources"].values() if v["Type"] == "AWS::Lambda::Function"}
    need = [h for h in envs(on) if h in ("video_brief.handler", "sf_launcher.handler", "capabilities_api.handler") or h in ("engine.handlers.plan_handler.handler", "engine.handlers.render_chunk_handler.handler", "engine.handlers.timeline_handler.handler", "engine.handlers.editor_apply.handler")]
    assert len(need) == 7
    for h in need:
        assert envs(on)[h].get("PRESENTERS") == "1" and "PRESENTERS" not in envs(off)[h], h
    assert len(on["Resources"]) == len(off["Resources"])       # no new resource: the stack is near the 500 limit
    assert json.dumps(on).count("AWS::IAM::Policy") == json.dumps(off).count("AWS::IAM::Policy")


def test_cards_are_never_empty_for_long_and_chart_labels_wrap():   # QA 2026-11-28: an empty chart card at the end of a scene, "Water evaporated" clipped
    from engine.easing import reveal_times
    from engine.scenes.elements import presenter as pe
    late = pe._early(reveal_times(3, 20.0, [9.0, 12.0, 15.0]))
    assert late[0] <= 0.7 and late[1] <= 1.3 and late[2] <= 1.9
    assert pe._early([0.1, 0.2]) == [0.1, 0.2]
    ch = pe.sanitize({"character": "fox", "heading": "Water", "chart": {"labels": ["Water evaporated", "Salt stays"], "values": [70, 30], "unit": "%"}}) if hasattr(pe, "sanitize") else None
    if ch is not None:
        assert ch["chart"]["labels"][0] == "Water evaporated"


def test_a_group_in_a_square_or_4x5_frame_stands_whole_above_the_captions():
    from types import SimpleNamespace
    from engine.frame import Frame
    from engine import stand_zone as sz
    from engine.scenes.elements import presenter as pe
    for asp in ("1:1", "4:5"):
        fr = Frame.parse(asp, "1080p")
        ctx = SimpleNamespace(frame=fr, captions=True, top=fr.margin_top, bottom=fr.content_bottom(True), box=fr.box(True))
        lay = pe.group_layout({"character": "fox", "side": "left", "cast": ["fox", "owl"]}, ctx)
        assert lay["floor"] is not None and lay["floor"] <= sz.caption_top(fr) * fr.H
        assert lay["content"][3] < lay["floor"] - 290.0 * lay["ppu"]          # the card stays above the heads
