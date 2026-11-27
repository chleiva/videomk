"""The video look a person chooses (docs/CREATE_API.md "Video look (chosen and enforced)"): what the launcher accepts, what the answers say when a chosen look
has to be adapted, and what capabilities offers the picker (four tiles, the cast, the previews)."""
import base64
import json

import pytest

import capabilities_api
import sf_launcher
from common import look_choice as lc
from engine import presenter_policy as pp

ALL_ON = {"cartoon": True, "whiteboard": True, "bg_animated": True, "bg_loops": True, "presenters": True}
ALL_OFF = {k: False for k in ALL_ON}


# ---------------------------------------------------------------- the request
def test_nothing_chosen_adds_nothing_to_the_request():
    assert lc.parse({}) == {} and lc.parse({"look": "auto", "cast": "auto", "extras": []}) == {}
    assert "look" not in sf_launcher.validate_options({"style": "cartoon", "presenter": "fox"})          # the old fields alone stay exactly what they were


def test_a_look_is_one_choice_and_the_cast_belongs_to_cartoon():
    assert lc.parse({"look": "whiteboard"}) == {"look": "whiteboard"} and lc.parse({"look": "real"}) == {"look": "real"}
    assert lc.parse({"look": "cartoon", "cast": ["fox", "bear"], "extras": ["board"]}) == {"look": "cartoon", "cast": ["fox", "bear"], "extras": ["board"]}
    assert lc.parse({"look": "presenters", "cast": "auto"}) == {"look": "cartoon"}                         # another name for the same tile
    assert lc.parse({"cast": ["owl"]}) == {"look": "cartoon", "cast": ["owl"]}                               # choosing characters is choosing the look
    assert lc.parse({"look": "auto", "extras": ["board"]}) == {"look": "cartoon", "extras": ["board"]}
    assert sf_launcher.validate_options({"look": "cartoon", "cast": ["fox", "bear"]})["cast"] == ["fox", "bear"]


@pytest.mark.parametrize("body", [{"look": "chalk"}, {"look": 3}, {"cast": []}, {"cast": ["fox", "fox"]}, {"cast": ["fox", "owl", "bear", "cat"]}, {"cast": ["dragon"]}, {"cast": "fox"},
                                  {"look": "real", "cast": ["fox"]}, {"look": "whiteboard", "extras": ["board"]}, {"extras": ["confetti"]}, {"extras": "board"}])
def test_a_value_outside_the_contract_is_a_400(body):
    with pytest.raises(lc.Invalid):
        lc.parse(body)
    with pytest.raises(sf_launcher.BadRequest):
        sf_launcher.validate_options(body)


def test_the_cast_ids_are_the_engine_s_cast():
    assert lc.CAST_IDS == pp.ORDER and lc.ANIMALS == pp.ANIMALS and set(lc.TOPICS) == set(pp.ORDER)


def test_the_old_style_field_is_a_chosen_look_only_where_it_always_meant_the_whole_video():
    assert lc.from_legacy({"style": "real"}) == {"look": "real"} and lc.from_legacy({"style": "whiteboard"}) == {"look": "whiteboard"}
    assert lc.from_legacy({"style": "cartoon"}) == {} and lc.from_legacy({"presenter": "fox"}) == {} and lc.from_legacy({}) == {}
    assert lc.from_legacy({"style": "real", "look": "cartoon", "cast": ["owl"]}) == {"look": "cartoon", "cast": ["owl"]}   # `look` wins over `style`


# ---------------------------------------------------------------- what the answers say
def test_a_chosen_look_is_applied_and_enforced_where_the_stage_has_it():
    r = lc.resolve({"look": "cartoon", "cast": ["fox", "bear"], "extras": ["board"], "target_minutes": 0.75}, "en", f=ALL_ON)
    assert r == {"chosen": "cartoon", "applied": "cartoon", "enforced": True, "recipe": "conversation_board", "extras": ["board"], "reason": None, "note": None, "cast": ["fox", "bear"]}
    assert lc.resolve({"look": "cartoon"}, "en", f=ALL_ON)["cast"] == "auto" and lc.resolve({"look": "cartoon"}, "en", f=ALL_ON)["recipe"] == "presenter"
    assert lc.resolve({"look": "whiteboard"}, "en", f=ALL_ON)["recipe"] == "whiteboard" and lc.resolve({"look": "real"}, "en", f=ALL_OFF)["recipe"] == "footage"
    assert lc.resolve({}, "en", f=ALL_ON) is None and lc.answer({"style": "cartoon"}, "en", f=ALL_ON) == {}


def test_a_look_that_cannot_be_given_is_adapted_with_a_reason_never_refused():
    soon = lc.resolve({"look": "whiteboard"}, "en", f=ALL_OFF)
    assert (soon["applied"], soon["reason"], soon["enforced"]) == ("auto", "not_available", False) and "Whiteboard" in soon["note"]
    photos = lc.resolve({"look": "cartoon", "cast": ["fox"]}, "es", media_count=3, f=ALL_ON)
    assert (photos["applied"], photos["reason"]) == ("real", "own_photos") and "tus fotos" in photos["note"] and "cast" not in photos
    assert lc.resolve({"look": "whiteboard"}, "en", deck=True, f=ALL_ON)["reason"] == "deck"
    assert lc.resolve({"look": "real"}, "en", media_count=5, f=ALL_ON)["enforced"] is True                  # a photo video IS a real video
    short = lc.resolve({"look": "cartoon", "cast": ["fox", "bear"], "target_minutes": 0.25}, "en", f=ALL_ON)
    assert short["cast"] == ["fox"] and short["reason"] == "too_short" and short["recipe"] == "presenter" and short["enforced"] is True
    noboard = lc.resolve({"look": "cartoon", "extras": ["board"]}, "en", f={**ALL_ON, "whiteboard": False})
    assert noboard["extras"] == [] and noboard["recipe"] == "presenter" and noboard["reason"] == "not_available"


def test_the_answer_keeps_the_older_keys_true_and_the_choice_wins_over_words():
    a = lc.answer({"look": "cartoon", "cast": ["owl"]}, "en", f=ALL_ON)
    assert a["look"]["style"] == "cartoon" and a["look"]["presenter"] is True and a["look"]["adapted"] == [] and "note" not in a
    words = {"look": {"style": "auto", "asked": ["characters"], "adapted": ["characters"], "presenter": False}, "note": "old"}
    m = lc.merge(words, lc.answer({"look": "real"}, "en", f=ALL_ON))
    assert m["look"]["applied"] == "real" and m["look"]["asked"] == ["real"] and "note" not in m and lc.merge(words, {}) is words


# ---------------------------------------------------------------- capabilities
def _caps(monkeypatch, locale="en", **env):
    for k in ("VECTOR_SCENES", "BG_ANIMATED", "BG_LOOPS", "WATERMARK_ENABLED", "WHITEBOARD", "PRESENTERS"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    ev = {"pathParameters": {"user_id": "u1"}, "headers": {"X-Locale": locale}, "requestContext": {"authorizer": {"claims": {"sub": "u1"}}}}
    r = capabilities_api.handler(ev, None)
    assert r["statusCode"] == 200
    return json.loads(r["body"])["looks"]


def test_the_picker_has_four_tiles_with_a_preview_each_in_both_languages(monkeypatch):
    en, es = _caps(monkeypatch, WHITEBOARD="1", PRESENTERS="1", VECTOR_SCENES="1"), _caps(monkeypatch, "es", WHITEBOARD="1", PRESENTERS="1", VECTOR_SCENES="1")
    tiles = en["look"]["options"]
    assert en["look"]["param"] == "look" and en["look"]["default"] == "auto" and en["look"]["enforced"] is True
    assert [t["id"] for t in tiles] == list(lc.LOOKS) == ["auto", "real", "whiteboard", "cartoon"] and len(tiles) <= 5
    assert [t["label"] for t in tiles] == ["Auto", "Real", "Whiteboard", "Cartoon"] and [t["label"] for t in es["look"]["options"]] == ["Automático", "Real", "Pizarra", "Dibujos animados"]
    for t, s in zip(tiles, es["look"]["options"]):
        raw = base64.b64decode(t["preview"].split(",", 1)[1])
        assert t["preview"].startswith("data:image/jpeg;base64,") and raw[:2] == b"\xff\xd8" and len(raw) < 60_000
        assert t["note"] and s["note"] and len(t["note"]) <= 48 and len(s["note"]) <= 48 and t["available"] is True and t["allowed"] is True and t["requires_plan"] is None
        assert set(t["best_aspects"]) <= set(t["aspects"]) and t["min_seconds"] >= 15
    by = {t["id"]: t for t in tiles}
    assert by["auto"]["with_photos"] and by["real"]["with_deck"] and not by["whiteboard"]["with_photos"] and not by["cartoon"]["with_deck"]
    assert by["cartoon"]["cast"] is True and not by["real"]["cast"] and [e["id"] for e in by["cartoon"]["extras"]] == ["board"] and by["cartoon"]["extras"][0]["available"] is True
    assert all(not by[k]["extras"] for k in ("auto", "real", "whiteboard"))


def test_the_cast_lists_people_and_animals_with_a_face_and_a_topic(monkeypatch):
    c = _caps(monkeypatch, PRESENTERS="1")["cast"]
    assert (c["param"], c["default"], c["min"], c["max"], c["available"]) == ("cast", "auto", 1, 3, True) and c["conversation"]["from"] == 2 and c["conversation"]["min_seconds"] == 20
    assert [m["id"] for m in c["members"]] == list(pp.ORDER)
    assert [m["kind"] for m in c["members"]] == ["person"] * 4 + ["animal"] * 6
    assert all(m["name"] and m["role"] and m["topic"] and m["thumbnail"].startswith("data:image/png;base64,") for m in c["members"])
    es = _caps(monkeypatch, "es", PRESENTERS="1")["cast"]
    assert es["members"][5]["role"] == "Búho profesor" and es["members"][5]["topic"] == "Ciencia e historia" and es["auto"]["label"] == "Automático"


def test_a_stage_without_the_looks_says_so_per_tile(monkeypatch):
    off = _caps(monkeypatch)
    assert [t["available"] for t in off["look"]["options"]] == [True, True, False, False] and off["cast"]["available"] is False
    half = _caps(monkeypatch, PRESENTERS="1")                                                               # characters without the whiteboard: the tile is there, its board extra is not
    assert [t["available"] for t in half["look"]["options"]] == [True, True, False, True] and half["look"]["options"][3]["extras"][0]["available"] is False


def test_a_plan_whose_longest_video_is_under_a_look_s_minimum_does_not_allow_it():
    caps = lc.capabilities("en", [], f=ALL_ON, plan_max_seconds=10)
    assert [t["allowed"] for t in caps["look"]["options"]] == [False] * 4
    assert all(t["allowed"] for t in lc.capabilities("en", [], f=ALL_ON, plan_max_seconds=30)["look"]["options"])


def test_generate_and_brief_answers_carry_the_chosen_look(monkeypatch):
    for k in ("WHITEBOARD", "PRESENTERS"):
        monkeypatch.setenv(k, "1")
    n = sf_launcher.look_note("How do volcanoes work?", {"look": "cartoon", "cast": ["fox", "bear"]}, "en")
    assert n["look"]["chosen"] == "cartoon" and n["look"]["recipe"] == "conversation" and n["look"]["cast"] == ["fox", "bear"] and "note" not in n
    monkeypatch.setenv("WHITEBOARD", "0")
    n = sf_launcher.look_note("How do volcanoes work?", {"look": "whiteboard"}, "es")
    assert n["look"]["applied"] == "auto" and n["look"]["reason"] == "not_available" and "Pizarra" in n["note"]
    import video_brief
    b = video_brief._look("How do volcanoes work?", {"look": "cartoon"}, 2, "en")
    assert b["look"]["reason"] == "own_photos" and b["note"].startswith("Made from your photos")
    assert video_brief._look("How do volcanoes work?", {}, 0, "en") == {}
