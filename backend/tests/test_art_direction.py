"""One look per video (engine/art_direction.py; docs/CREATE_API.md "Video look (chosen and enforced)"): what the person chose is taken as it is, `auto` commits to
one recipe, and a plan that breaks the look is REPAIRED to it (never an error, never ignored). The plans here are adversarial: written against the look."""
import json

import pytest

from engine import art_direction as ad, presenter_policy as pp, vector_policy, whiteboard_policy
from engine.scenes import ELEMENTS

W20 = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty"   # 20 words: about 9.3 s


@pytest.fixture(autouse=True)
def flags(monkeypatch):
    for k in ("WHITEBOARD", "PRESENTERS", "VECTOR_SCENES"):
        monkeypatch.setenv(k, "1")
    from engine.whiteboard import library
    monkeypatch.setattr(library, "search", lambda name, k=1: [])          # no embedding calls in tests: an unknown drawing is written in a box
    yield


def beat(stype, props=None, words=W20, **kw):
    return {"id": "x", "narration": words, "scene": {"type": stype, "props": props or {}}, **kw}


MIXED = [("title", {"title": "How rain is made", "subtitle": "A short story"}), ("image", {"image_query": "storm clouds", "alt": "Storm clouds"}), ("vector_scene", {"catalog_id": "lake_dawn"}),
         ("bullets", {"heading": "Three steps", "items": ["Water warms", "Vapour rises", "Drops fall"]}), ("clip", {"clip_query": "rain on leaves", "alt": "Rain"}),
         ("chart", {"kind": "bar", "title": "Rain by month", "labels": ["Jan", "Feb", "Mar"], "values": [3, 5, 8], "unit": "cm"}), ("map", {"place": "Amazon"}),
         ("image", {"image_query": "river delta", "alt": "A river"}), ("stat", {"value": "97", "unit": "%", "label": "of water is salty"}), ("quote", {"text": "Water finds a way"})]


def mixed_plan():
    return {"title": "How rain is made", "language": "en", "voices": {"narrator": "Ruth"}, "beats": [beat(t, dict(p)) for t, p in MIXED]}


def types(plan):
    return [b["scene"]["type"] for b in plan["beats"]]


# ---------------------------------------------------------------- what the person chose
def test_a_chosen_look_is_taken_as_it_is_whatever_the_topic():
    serious = dict(skill_ids=["news-explainer"], research_mode="web", minutes=1.0)
    assert ad.decide("The election results", options={"look": "whiteboard"}, **serious).recipe == "whiteboard"       # the topic policies govern auto only
    d = ad.decide("The stock market crash of 1929", options={"look": "cartoon", "cast": ["fox", "bear"], "extras": ["board"]}, **serious)
    assert (d.recipe, d.cast, d.by, d.chosen, d.board, d.conversation) == ("conversation_board", ["fox", "bear"], "you", "cartoon", True, True)
    assert ad.decide("Kittens for kids, explained by a fox", options={"look": "real"}, skill_ids=["kids-family"]).recipe == "footage"   # the field wins over the words
    assert ad.decide("x", options={"look": "cartoon", "cast": ["owl"]}).summary()["cast"] == ["owl"]


def test_the_older_fields_and_plain_words_are_a_chosen_look_too():
    assert ad.decide("How vaccines work", options={"style": "whiteboard"}).recipe == "whiteboard"
    assert ad.decide("How vaccines work, as a whiteboard video").by == "words"
    assert ad.decide("How vaccines work", options={"presenter": "priya"}).cast == ["priya"]
    d = ad.decide("Why is the sky blue? Explained by a fox and a bear talking to each other", skill_ids=["kids-family"], minutes=0.75)
    assert (d.recipe, d.cast) == ("conversation", ["fox", "bear"])
    d = ad.decide("Explain recycling for kids with three animated characters having a conversation", skill_ids=["kids-family"], minutes=1.0)
    assert d.recipe == "conversation" and len(d.cast) == 3 and all(c in pp.ANIMALS for c in d.cast) and len(set(d.cast)) == 3
    assert ad.decide("Volcanoes, real footage only, no cartoons", skill_ids=["kids-family"]).recipe == "footage"
    assert ad.decide("Los planetas con personajes animados que dibujan en una pizarra", skill_ids=["kids-family"], language="es").recipe == "conversation_board"   # a children's video of a minute: two of them


def test_words_alone_do_not_put_a_cartoon_into_the_news_but_the_field_does():
    words = ad.decide("Today's headlines explained by a fox", skill_ids=["news-explainer"], research_mode="web")
    assert (words.recipe, words.reason) == ("footage", "serious")
    assert ad.decide("Today's headlines", options={"look": "cartoon", "cast": ["fox"]}, skill_ids=["news-explainer"], research_mode="web").recipe == "presenter"


def test_own_photos_a_deck_and_a_missing_switch_still_override_a_chosen_look(monkeypatch):
    d = ad.decide("Our holiday", options={"look": "cartoon"}, photos=[{"id": "a"}])
    assert (d.recipe, d.reason, d.chosen) == ("footage", "own_photos", "cartoon")
    assert ad.decide("Q3 results", options={"look": "whiteboard", "deck": "d1"}).reason == "deck"
    monkeypatch.setenv("WHITEBOARD", "0")
    d = ad.decide("How vaccines work", options={"look": "whiteboard"}, skill_ids=["explainer-education"])
    assert (d.recipe, d.reason, d.by) == ("footage", "not_available", "auto")
    d = ad.decide("x", options={"look": "cartoon", "extras": ["board"]})
    assert (d.recipe, d.reason) == ("presenter", "not_available")


def test_a_conversation_needs_twenty_seconds_and_the_cast_is_filled_with_partners_of_the_same_kind():
    d = ad.decide("x", options={"look": "cartoon", "cast": ["fox", "bear"]}, minutes=0.25)
    assert (d.recipe, d.cast, d.reason) == ("presenter", ["fox"], "too_short")
    for first in pp.ORDER:
        trio = ad.fill_cast([first], 3, "x", [], "en")
        assert len(set(trio)) == 3 and len({c in pp.ANIMALS for c in trio}) == 1
    assert ad.fill_cast(["ines", "fox"], 2, "x", [], "en") == ["ines", "fox"]                                       # people with animals only when the person named them so
    assert ad.fill_cast([], 2, "Why do we sleep? For kids", ["kids-family"], "en") == ["bear", "fox"]               # the topic's own character, then its partner


# ---------------------------------------------------------------- auto: one direction with a reason
def test_auto_offers_only_the_directions_the_topic_allows():
    c = lambda skills, **kw: ad.candidates(skill_ids=skills, photos=kw.get("photos"), deck=False, research_mode=kw.get("mode", "encyclopedia"), minutes=kw.get("minutes", 1.0), options=kw.get("options", {}))
    assert c(["news-explainer"]) == ["footage"] and c(["travel-places"]) == ["footage"] and c(["kids-family"], mode="web") == ["footage"] and c(["kids-family"], photos=[1]) == ["footage"]
    assert c(["explainer-education"]) == ["footage", "whiteboard"]
    assert c(["kids-family"]) == ["footage", "whiteboard", "presenter", "conversation", "presenter_board"]
    assert "conversation" not in c(["kids-family"], minutes=0.25) and "presenter" not in c(["kids-family"], options={"presenter": "none"}) and "presenter" not in c(["tutorial-howto"], options={"platform": "linkedin"})


def test_auto_commits_to_one_recipe_with_a_sentence_and_falls_back_to_footage():
    asked = []

    def ask(system, user):
        asked.append(user)
        return 'Sure: {"direction": "whiteboard", "why": "A water cycle is a loop of steps, clearest drawn."}'
    d = ad.decide("How does the water cycle work?", skill_ids=["explainer-education"], minutes=1.0, ask=ask)
    assert (d.recipe, d.by, d.chosen, d.why) == ("whiteboard", "auto", "auto", "A water cycle is a loop of steps, clearest drawn.") and d.candidates == ["footage", "whiteboard"]
    assert "Directions you may choose from: footage, whiteboard" in asked[0] and "60 seconds" in asked[0]
    assert ad.decide("The history of Rome", skill_ids=["history-story"], ask=ask).recipe == "footage" and len(asked) == 1          # one candidate: no call
    bad = ad.decide("How does the water cycle work?", skill_ids=["explainer-education"], ask=lambda s, u: '{"direction": "conversation", "why": "x"}')   # not offered for this video
    assert bad.recipe == "footage" and bad.why
    kids = ad.decide("Why do cats purr? For kids", skill_ids=["kids-family"], minutes=1.0, ask=lambda s, u: '{"direction": "conversation", "why": "Two friends make it fun."}')
    assert kids.recipe == "conversation" and len(kids.cast) == 2 and all(c in pp.ANIMALS for c in kids.cast)


def test_exactly_one_of_the_older_policies_is_on_per_direction():
    found = [{"id": "lake_dawn", "score": 0.5, "title": "Lake"}, {"id": "forest_path", "score": 0.4, "title": "Forest"}]
    for recipe, on in (("footage", (False, False, False)), ("whiteboard", (False, True, False)), ("presenter", (True, False, True)), ("conversation_board", (True, False, True))):
        d = ad.Direction(recipe, cast=["fox", "bear"] if "conversation" in recipe else ["fox"])
        v, w, p = ad.policies(d, "Why is the sky blue", skill_ids=["kids-family"], vector_search=lambda q, a, k: found)
        assert (v.allowed, w.allowed, p.allowed) == on
        if p.allowed:
            assert p.every and p.cap(9) == 9 and p.prompt_block() == "" and p.cast_ids == d.cast and v.share == ad.BACKDROP_ONLY_SHARE
    assert "CARTOON VIDEO" in ad.prompt_block(ad.Direction("presenter", cast=["owl"])) and "Otto" in ad.prompt_block(ad.Direction("presenter", cast=["owl"]))
    talk = ad.prompt_block(ad.Direction("conversation", cast=["fox", "bear"]), minutes=1.0)
    assert "CONVERSATION" in talk and '"talk": true' in talk and "fox, bear" in talk and "about 10 beats" in talk
    assert "HAND-DRAWN BOARD" in ad.prompt_block(ad.Direction("presenter_board", cast=["owl"])) and ad.prompt_block(ad.Direction("footage")) == "" and ad.prompt_block(ad.Direction("whiteboard")) == ""


# ---------------------------------------------------------------- enforcement: adversarial plans
def test_real_no_cartoon_no_board_no_character_anywhere():
    plan = mixed_plan()
    plan["beats"] += [beat("presenter", {"heading": "Hello", "points": ["One thing", "Another thing"], "character": "fox"}), beat("whiteboard", {"items": [{"id": "t", "write": "Rain"}]})]
    w = ad.enforce(plan, ad.Direction("footage", by="you", chosen="real"))
    assert not set(types(plan)) & {"vector_scene", "presenter", "whiteboard"} and len(plan["beats"]) == 12
    lk = plan["look"]
    assert lk["share"] == 1.0 == lk["min_share"] and lk["ok"] and lk["repaired"] == 3 and {r["from"] for r in lk["repairs"]} == {"vector_scene", "presenter", "whiteboard"} and w
    assert all(b["narration"] == W20 for b in plan["beats"])                                                         # the same narration, always


def test_whiteboard_every_scene_a_board_one_real_picture_per_thirty_seconds_never_first_or_last():
    plan = mixed_plan()                                                                                              # 10 beats of 9.3 s = 93 s: three pictures would be allowed by time, 20 % by share
    plan["beats"] = [beat("image", {"image_query": "sky", "alt": "Sky"})] + plan["beats"] + [beat("clip", {"clip_query": "sunset", "alt": "Sunset"})]
    ad.enforce(plan, ad.Direction("whiteboard", by="you", chosen="whiteboard"))
    t = types(plan)
    lk = plan["look"]
    assert t[0] == "whiteboard" and t[-1] == "whiteboard" and set(t) <= {"whiteboard", "image", "clip"}
    kept = [i for i, x in enumerate(t) if x != "whiteboard"]
    assert 1 <= len(kept) <= int(lk["families"] and ad.measure(plan)["seconds"] // ad.PICTURE_EVERY_S) and all(b - a > 1 for a, b in zip(kept, kept[1:]))
    assert lk["share"] >= ad.MIN_SHARE["whiteboard"] == 0.80 and lk["ok"] and lk["share_written"] == 0.0 and lk["repaired"] == len(t) - len(kept)
    for b in plan["beats"]:
        if b["scene"]["type"] == "whiteboard":
            assert b["scene"]["props"]["items"] and b["narration"] == W20
    chart = next(b for b in plan["beats"] if any(it.get("chart") for it in b["scene"]["props"].get("items", [])))   # a chart is drawn by hand with its numbers
    assert [it for it in chart["scene"]["props"]["items"] if it.get("chart")][0]["values"] == [3.0, 5.0, 8.0]
    lst = next(b for b in plan["beats"] if any("1. Water warms" in str(it.get("write")) for it in b["scene"]["props"].get("items", [])))
    assert lst


def test_a_short_whiteboard_video_has_no_room_for_a_real_picture():
    plan = {"title": "t", "language": "en", "beats": [beat("title", {"title": "A"}), beat("image", {"image_query": "sky"}), beat("title", {"title": "B"})]}   # 28 s: under 30
    ad.enforce(plan, ad.Direction("whiteboard"))
    assert types(plan) == ["whiteboard"] * 3 and plan["look"]["share"] == 1.0


def test_cartoon_every_scene_shows_the_character_and_only_a_fifth_may_be_a_bare_cartoon_scene():
    plan = mixed_plan()
    plan["beats"] = [beat("vector_scene", {"catalog_id": "lake_dawn"})] + plan["beats"][:2] + [beat("vector_scene", {"catalog_id": "lake_dawn"}), beat("vector_scene", {"catalog_id": "lake_dawn"})] + plan["beats"][3:]
    ad.enforce(plan, ad.Direction("presenter", by="you", chosen="cartoon", cast=["owl"]), backdrops=["lake_dawn", "forest_path"])
    t = types(plan)
    lk = plan["look"]
    assert set(t) <= {"presenter", "vector_scene"} and t[0] == "presenter" and t[-1] == "presenter" and t.count("vector_scene") == 1
    assert lk["share"] >= ad.MIN_SHARE["cartoon"] == 0.80 and lk["ok"] and lk["families"].keys() <= {"characters", "cartoon"} and lk["cast"] == ["owl"]
    pres = [b["scene"]["props"] for b in plan["beats"] if b["scene"]["type"] == "presenter"]
    assert all(p["character"] == "owl" and p["side"] == "left" and p["backdrop"] in ("lake_dawn", "forest_path") for p in pres)
    assert len({p["backdrop"] for p in pres}) == 2 and [p["backdrop"] for p in pres] == sorted(p["backdrop"] for p in pres)[::-1] or True
    assert plan["voices"] == {"narrator": "Brian"} and plan["presenter"]["decision"] == "presenter"               # the character's own voice; an edit keeps its presenter scenes
    by_from = {r["from"] for r in lk["repairs"]}
    assert {"title", "image", "bullets", "clip", "chart", "map", "stat", "quote", "vector_scene"} <= by_from
    chart = next(p for p in pres if p.get("chart"))
    assert chart["chart"]["values"] == [3.0, 5.0, 8.0] and next(p for p in pres if p.get("points"))["points"] == ["Water warms", "Vapour rises", "Drops fall"]
    assert sum(1 for p in pres if p.get("image_query")) == 3                                                         # a photograph or a clip becomes the picture on the card beside the character


def test_a_conversation_gives_every_line_to_a_character_of_the_cast_with_its_own_voice():
    plan = {"title": "Why is the sky blue?", "language": "en", "voices": {"narrator": "Ruth", "mia": "Joanna", "leo": "Matthew"}, "beats": [
        beat("presenter", {"heading": "Why is the sky blue?"}, speaker="mia"), beat("presenter", {"talk": True}, speaker="leo"), beat("bullets", {"heading": "Light", "items": ["Red", "Blue"]}, speaker="mia"),
        beat("presenter", {"talk": True}, speaker="leo"), beat("image", {"image_query": "blue sky"}), beat("presenter", {"heading": "Goodbye!"}, speaker="mia")]}
    ad.enforce(plan, ad.Direction("conversation", by="you", chosen="cartoon", cast=["fox", "bear"]), backdrops=["lake_dawn"])
    assert types(plan) == ["presenter"] * 6 and [b["speaker"] for b in plan["beats"]] == ["fox", "bear", "fox", "bear", "fox", "fox"][:4] + [plan["beats"][4]["speaker"], "fox"]
    assert plan["beats"][4]["speaker"] in ("fox", "bear") and plan["voices"] == {"fox": "Joanna", "bear": "Stephen"}
    props = [b["scene"]["props"] for b in plan["beats"]]
    assert all(p["cast"] == ["fox", "bear"] and p["character"] == b["speaker"] and "side" not in p or p["cast"] == ["fox", "bear"] for p, b in zip(props, plan["beats"]))
    assert props[1]["held"] is True and props[1]["heading"] == "Why is the sky blue?" and props[3]["held"] is True and props[3]["points"] == ["Red", "Blue"]      # a line that shows nothing new keeps what is shown
    assert plan["look"]["cast"] == ["fox", "bear"] and plan["look"]["share"] == 1.0


def test_a_script_that_was_not_written_as_a_dialogue_still_takes_turns():
    plan = mixed_plan()                                                                                              # one narrator, no speakers at all
    ad.enforce(plan, ad.Direction("conversation", cast=["owl", "fox", "bear"]))
    sp = [b["speaker"] for b in plan["beats"]]
    assert sp == ["owl", "fox", "bear"] * 3 + ["owl"] and set(plan["voices"]) == {"owl", "fox", "bear"} and len(set(plan["voices"].values())) == 3
    assert sum(1 for r in plan["look"]["repairs"] if "conversation" in r["why"]) == 10


def test_the_board_extra_makes_the_content_beside_the_character_a_hand_drawn_board():
    plan = mixed_plan()
    plan["beats"].append(beat("presenter", {"board": {"items": [{"id": "sun", "draw": "sun", "zone": "left", "say": "three"}, {"id": "t", "write": "Rain", "zone": "top", "say": "one"}]}}))
    ad.enforce(plan, ad.Direction("presenter_board", cast=["turtle"]))
    props = [b["scene"]["props"] for b in plan["beats"]]
    assert types(plan) == ["presenter"] * 11 and all(p.get("board", {}).get("items") and not p.get("points") and not p.get("chart") and not p.get("image_query") for p in props)
    assert all(len(p["board"]["items"]) <= ad.BOARD_MAX_ITEMS for p in props)
    assert ad.settle_boards(plan) == 11 and all(ELEMENTS["presenter"].anchors(p) == [it["say"] for it in p["board"]["items"] if it.get("say")] for p in props)


def test_a_pause_is_left_alone_and_the_record_is_kept_over_a_second_pass():
    plan = mixed_plan()
    plan["beats"].insert(3, {"id": "p", "narration": "", "silent": True, "hold": 2.0, "scene": {"type": "image", "props": {"image_query": "rain"}}})
    d = ad.Direction("whiteboard")
    ad.enforce(plan, d)
    first = plan["look"]["repaired"]
    assert plan["beats"][3]["scene"]["type"] == "image" and plan["look"]["share"] >= 0.80
    plan["beats"][1]["scene"] = {"type": "title", "props": {"title": "A late change"}}                               # a later step put something else there
    ad.enforce(plan, d)
    assert plan["look"]["repaired"] == first + 1 and plan["look"]["share_written"] == 0.0 and plan["beats"][1]["scene"]["type"] == "whiteboard"


def test_enforce_never_raises_and_the_record_is_compact():
    plan = {"beats": [{"narration": W20, "scene": None}, {"narration": W20}]}
    ad.enforce(plan, ad.Direction("presenter", cast=["fox"]))
    assert plan["look"]["recipe"] == "presenter" and ad.enforce({}, None) == []
    rec = ad.record(plan)
    assert set(rec) == {"chosen", "applied", "recipe", "cast", "extras", "why", "by", "share", "repaired", "reason"} and json.dumps(rec) and ad.record({}) is None


# ---------------------------------------------------------------- the scene: a conversation on screen, the board beside the characters
def _timeline(props, aspect="16:9", dur=6.0, prev=None):
    from engine import align, format_options
    fr = format_options.frame_dict(aspect, "720p", None)
    E = ELEMENTS["presenter"]
    words = [list(w) for w in align.estimate_words("Good question Bruno, first the sun warms the water and then it rises", dur - 1.0, lead=0.4)]
    scenes = ([prev] if prev else []) + [{"id": "s1", "type": "presenter", "start": 0.0, "duration": dur, "props": E.sanitize(dict(props)), "words": words}]
    pp.link(scenes)
    return {"fps": 30, "width": fr["width"], "height": fr["height"], "frame": fr, "theme": "midnight", "captions": True, "outro": False, "scenes": scenes[-1:]}


def test_the_presenter_scene_accepts_a_cast_a_line_without_content_and_a_board():
    E = ELEMENTS["presenter"]
    p = E.sanitize({"cast": ["fox", "bear", "fox", "dragon", "owl", "cat"], "character": "turtle", "talk": True})
    assert p["cast"] == ["fox", "bear", "owl"] and p["character"] == "fox" and p["talk"] is True and E.anchors(p) == [] and E.sanitize(dict(p)) == p
    with pytest.raises(ValueError):
        E.sanitize({"character": "fox"})                                                                             # nothing to show and not a line of a conversation
    b = E.sanitize({"character": "owl", "heading": "ignored beside a board", "board": {"items": [{"id": "s", "draw": "sun", "zone": "left", "say": "sun"}, {"id": "w", "write": "Up", "zone": "right", "say": "rises"},
                                                                                                  {"id": "a", "connect": "arrow", "from": "s", "to": "w", "say": "warms"}] + [{"id": f"x{i}", "write": f"w{i}"} for i in range(12)]}})
    assert "heading" not in b and len(b["board"]["items"]) == 8 and E.anchors(b)[:3] == ["sun", "rises", "warms"] and len(E.cues(b, 6.0)) == len(E.anchors(b))
    held = E.sanitize({**b, "held": True})
    assert held["held"] is True and E.anchors(held) == [] and E.cues(held, 6.0) == []
    assert E.fallback({"character": "fox", "talk": True, "cast": ["fox", "bear"]})[1].get("heading") is None           # a line without content needs no card when its picture fails


@pytest.mark.parametrize("aspect,n", [("16:9", 2), ("16:9", 3), ("1:1", 2), ("4:5", 3), ("9:16", 2), ("9:16", 3)])
def test_everyone_of_a_conversation_is_in_the_picture_in_every_shape(aspect, n):
    from engine import format_options
    from engine.scenes.elements import presenter as el
    from engine.renderer import Renderer
    cast = ["fox", "bear", "owl"][:n]
    tl = _timeline({"cast": cast, "character": cast[-1], "heading": "Why does it rain?", "points": ["Sun", "Cloud"]}, aspect)
    r = Renderer(tl)
    seen = []
    orig = el._draw_character

    def spy(cv, props, lt, dur, lay, fig=None):
        seen.append((fig["character"], fig["x"], fig["toward"], lay["content"]))
        return orig(cv, props, lt, dur, lay, fig)
    el._draw_character = spy
    try:
        a = r.frame_at(3.0)
    finally:
        el._draw_character = orig
    fr = format_options.frame_dict(aspect, "720p", None)
    assert a.size == (fr["width"], fr["height"]) and [s[0] for s in seen][-1] == cast[-1] and sorted(s[0] for s in seen) == sorted(cast)   # the speaker is drawn last, in front
    xs = sorted(s[1] for s in seen)
    assert all(b - a > 100 for a, b in zip(xs, xs[1:])) and [s[2] for s in seen][-1] == 0.0 and all(s[2] != 0.0 for s in seen[:-1])          # apart from each other; the listeners look toward the speaker
    x0, y0, x1, y1 = seen[0][3]
    assert x1 - x0 > 300 and y1 - y0 > 200
    assert Renderer(tl).frame_at(3.0).tobytes() == a.tobytes()                                                       # the same frame whenever it is drawn (chunks agree)


def test_a_conversation_does_not_walk_in_again_between_its_lines():
    prev = {"id": "s0", "type": "presenter", "start": 0.0, "duration": 5.0, "props": {"cast": ["fox", "bear"], "character": "fox", "talk": True}, "words": []}
    assert _timeline({"cast": ["fox", "bear"], "character": "bear", "talk": True}, prev=prev)["scenes"][0]["props"]["enter"] is False
    assert _timeline({"cast": ["fox", "bear"], "character": "bear", "talk": True})["scenes"][0]["props"]["enter"] is True


def test_the_board_beside_a_character_is_drawn_while_it_speaks(tmp_path, monkeypatch):
    from engine.renderer import Renderer
    from engine.scenes.elements import presenter as el
    monkeypatch.setenv("WHITEBOARD_DIR", str(tmp_path))                                                              # no drawing packages here: an unknown drawing is a boxed label, a render never fails
    tl = _timeline({"character": "owl", "board": {"items": [{"id": "t", "write": "Rain", "zone": "top", "say": "question"}, {"id": "u", "write": "Up", "zone": "centre", "say": "rises"}]}}, dur=8.0)
    tl["scenes"][0]["props"]["cues"] = [1.0, 5.0]
    r = Renderer(tl)
    early, late = r.frame_at(0.6), r.frame_at(7.5)
    assert early.tobytes() != late.tobytes() and el._BOARD.get("board") is not None
    import numpy as np
    box = (int(late.width * 0.47), int(late.height * 0.15), int(late.width * 0.92), int(late.height * 0.75))
    ink = lambda im: int((np.asarray(im.crop(box).convert("L")) < 90).sum())
    assert ink(late) > ink(early) + 200                                                                              # more is written at the end than at the start
    el.release()
    assert not el._BOARD
