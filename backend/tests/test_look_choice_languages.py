"""Characters that speak their own language: the request contract (docs/CREATE_API.md "Characters that speak different languages"): `cast` entries may be
{"id", "language"}, normalised to the same id list plus a `cast_languages` map; what the answers say; what capabilities offers (languages per cast member from the
voice catalogue, women-only note for nl, pl, fi)."""
import json

import pytest

import capabilities_api
import sf_launcher
from common import look_choice as lc

ALL_ON = {"cartoon": True, "whiteboard": True, "bg_animated": True, "bg_loops": True, "presenters": True}
NINE = "en,es,fr,de,it,pt,nl,pl,fi"


@pytest.fixture(autouse=True)
def stage(monkeypatch):
    monkeypatch.setenv("VIDEO_LANGUAGES", NINE)
    monkeypatch.setenv("POLYGLOT", "1")


# ---------------------------------------------------------------- the request
def test_ids_only_is_exactly_what_it_was():
    assert lc.parse({"look": "cartoon", "cast": ["fox", "bear"]}) == {"look": "cartoon", "cast": ["fox", "bear"]}
    assert "cast_languages" not in sf_launcher.validate_options({"cast": ["fox", "bear"]})


def test_the_object_form_is_the_same_id_list_plus_a_map():
    r = lc.parse({"cast": ["fox", {"id": "bear", "language": "de"}, {"id": "owl", "language": "it"}], "translation": "auto"})
    assert r == {"look": "cartoon", "cast": ["fox", "bear", "owl"], "cast_languages": {"bear": "de", "owl": "it"}}   # translation auto is left out like every default
    assert lc.parse({"cast": [{"id": "fox"}, {"id": "owl", "language": "auto"}]}) == {"look": "cartoon", "cast": ["fox", "owl"]}
    assert lc.parse({"cast": [{"id": "fox", "language": "fr"}, "bear"], "translation": "off"}) == {"look": "cartoon", "cast": ["fox", "bear"], "cast_languages": {"fox": "fr"}, "translation": "off"}
    o = sf_launcher.validate_options({"look": "cartoon", "cast": [{"id": "fox", "language": "fr"}, {"id": "owl", "language": "it"}], "translation": "on"})
    assert o["cast"] == ["fox", "owl"] and o["cast_languages"] == {"fox": "fr", "owl": "it"} and o["translation"] == "on"


@pytest.mark.parametrize("body", [
    {"cast": [{"id": "fox", "language": "xx"}, "bear"]},                  # not a language
    {"cast": [{"id": "fox", "language": "ko"}, "bear"]},                  # Korean has voices but no fonts: not ready
    {"cast": [{"id": "fox", "language": 3}, "bear"]},
    {"cast": [{"id": "fox", "lang": "fr"}, "bear"]},                       # another key
    {"cast": [{"language": "fr"}, "bear"]},                                # no id
    {"cast": [{"id": "dragon", "language": "fr"}]},
    {"cast": [{"id": "fox", "language": "fr"}, {"id": "fox", "language": "de"}]},   # the same character twice
    {"cast": [{"id": "fox", "language": "fr"}, "owl", "bear", "cat"]},     # four
    {"look": "real", "cast": [{"id": "fox", "language": "fr"}]},
    {"cast": ["fox", "owl"], "translation": "sometimes"},
    {"translation": True},
])
def test_a_value_outside_the_contract_is_a_400(body):
    with pytest.raises(lc.Invalid):
        lc.parse(body)
    with pytest.raises(sf_launcher.BadRequest):
        sf_launcher.validate_options(body)


def test_a_language_the_stage_does_not_have_is_a_400(monkeypatch):
    monkeypatch.setenv("VIDEO_LANGUAGES", "en,es")
    with pytest.raises(lc.Invalid):
        lc.parse({"cast": [{"id": "fox", "language": "fr"}, "bear"]})
    assert lc.parse({"cast": [{"id": "fox", "language": "es"}, "bear"]})["cast_languages"] == {"fox": "es"}


# ---------------------------------------------------------------- what the answers say
def test_the_languages_that_will_be_used_are_answered():
    o = lc.parse({"cast": [{"id": "fox", "language": "fr"}, {"id": "bear", "language": "de"}], "translation": "on"})
    r = lc.resolve(o, "en", f=ALL_ON)
    assert r["cast"] == ["fox", "bear"] and r["languages"] == {"by_character": {"fox": "fr", "bear": "de"}, "translation": "on", "reason": None, "note": None} and r["note"] is None
    a = lc.answer(o, "en", f=ALL_ON)
    assert a["look"]["languages"]["by_character"] == {"fox": "fr", "bear": "de"} and "note" not in a
    assert "languages" not in lc.resolve({"look": "cartoon", "cast": ["fox", "bear"]}, "en", f=ALL_ON)           # nothing sent, nothing added


def test_translation_alone_is_answered():
    r = lc.resolve({"look": "cartoon", "cast": ["fox", "bear"], "translation": "off"}, "en", f=ALL_ON)
    assert r["languages"] == {"by_character": {}, "translation": "off", "reason": None, "note": None}


def test_a_language_that_cannot_be_given_is_a_note_never_a_refusal(monkeypatch):
    base = {"look": "cartoon", "cast": ["fox", "owl", "bear"], "cast_languages": {"fox": "fr", "owl": "it", "bear": "de"}, "target_minutes": 2}
    assert lc.resolve(base, "en", f=ALL_ON)["languages"]["by_character"] == {"fox": "fr", "owl": "it", "bear": "de"}
    r = lc.resolve({**base, "target_minutes": 0.4}, "en", f=ALL_ON)                       # 24 s: two languages, the third speaks the video's
    assert r["languages"]["reason"] == "too_short" and r["languages"]["by_character"] == {"fox": "fr", "owl": "it"} and "30 s" in r["note"] and r["cast"] == ["fox", "owl", "bear"]
    r = lc.resolve({**base, "target_minutes": 0.25}, "en", f=ALL_ON)                      # 15 s: one character presents (the existing rule), so no turns
    assert r["cast"] == ["fox"] and r["reason"] == "too_short" and r["languages"]["reason"] == "needs_two" and r["languages"]["by_character"] == {}
    one = {"look": "cartoon", "cast": ["fox"], "cast_languages": {"fox": "fr"}}
    assert lc.resolve(one, "es", f=ALL_ON)["languages"]["reason"] == "needs_two" and "un solo idioma" in lc.resolve(one, "es", f=ALL_ON)["note"]
    assert lc.resolve({**one, "language": "fr"}, "en", f=ALL_ON)["languages"]["reason"] is None          # one character speaking the video's own language is just a character
    wb = lc.resolve({"look": "whiteboard", "cast_languages": {"fox": "fr"}, "translation": "on"}, "en", f=ALL_ON)
    assert "languages" in wb and wb["languages"]["translation"] == "on"                  # no cast: nothing asked per character
    monkeypatch.delenv("POLYGLOT")
    r = lc.resolve(base, "en", f=ALL_ON)
    assert r["languages"]["reason"] == "not_available" and r["languages"]["by_character"] == {} and r["note"] and r["applied"] == "cartoon"
    monkeypatch.setenv("POLYGLOT", "1")
    off = {"cartoon": False, "whiteboard": False}
    assert lc.resolve(base, "en", f=off)["applied"] == "auto"


def test_the_brief_and_generate_answers_carry_the_languages(monkeypatch):
    monkeypatch.setenv("PRESENTERS", "1")
    n = sf_launcher.look_note("Why is the sea salty?", {"look": "cartoon", "cast": ["fox", "bear"], "cast_languages": {"fox": "fr"}, "translation": "on"}, "en")
    assert n["look"]["languages"] == {"by_character": {"fox": "fr"}, "translation": "on", "reason": None, "note": None}


# ---------------------------------------------------------------- capabilities
def _caps(monkeypatch, locale="en", polyglot=True):
    for k in ("VECTOR_SCENES", "BG_ANIMATED", "BG_LOOPS", "WHITEBOARD", "PRESENTERS"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("PRESENTERS", "1")
    if polyglot:
        monkeypatch.setenv("POLYGLOT", "1")
    else:
        monkeypatch.delenv("POLYGLOT", raising=False)
    ev = {"pathParameters": {"user_id": "u1"}, "headers": {"X-Locale": locale}, "requestContext": {"authorizer": {"claims": {"sub": "u1"}}}}
    r = capabilities_api.handler(ev, None)
    assert r["statusCode"] == 200
    return json.loads(r["body"])["looks"]["cast"]


def test_capabilities_list_the_languages_from_the_voice_catalogue(monkeypatch):
    cast = _caps(monkeypatch)
    langs = cast["languages"]
    assert langs["available"] is True and langs["param"] == "cast[].language" and langs["max"] == 3 and langs["min_cast"] == 2 and langs["min_seconds"] == {"2": 20, "3": 30}
    by = {o["id"]: o for o in langs["options"]}
    assert list(by) == ["en", "es", "fr", "de", "it", "pt", "nl", "pl", "fi"]
    assert by["fr"]["label"] == "Français" and by["fr"]["voices"]["female"] >= 1 and by["fr"]["voices"]["male"] >= 1 and by["fr"]["women_only"] is False
    assert [l for l, o in by.items() if o["women_only"]] == ["nl", "pl", "fi"]
    assert [t["id"] for t in langs["translation"]["options"]] == ["auto", "on", "off"] and langs["translation"]["default"] == "auto"
    members = {m["id"]: m for m in cast["members"]}
    man, woman = members["owl"], members["priya"]
    note_of = lambda m, code: next(l for l in m["languages"] if l["id"] == code)["note"]   # noqa: E731
    assert man["languages"][0]["id"] == "en" and len(man["languages"]) == 9
    assert note_of(man, "nl") and "Dutch" in note_of(man, "nl") or "Nederlands" in note_of(man, "nl")      # a man's character speaking Dutch: a woman's voice, with a note
    assert note_of(man, "fr") is None and note_of(woman, "nl") is None and note_of(woman, "fi") is None


def test_capabilities_in_spanish_and_with_the_switch_off(monkeypatch):
    es = _caps(monkeypatch, "es")
    assert "propio idioma" in es["languages"]["note"] and [t["label"] for t in es["languages"]["translation"]["options"]][0] == "Automática"
    off = _caps(monkeypatch, polyglot=False)
    assert off["languages"]["available"] is False and off["languages"]["options"] == [] and all(m["languages"] == [] for m in off["members"])
