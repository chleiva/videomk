"""The request check and several languages in one video (docs/MULTILINGUAL_CONVERSATIONS_DESIGN_2026-11-27.md section 2.7, stage 0): a request written in one language
that asks for lines in other languages is neither `unsupported` nor a block; the check's prompt says so; the form values line carries `cast_languages`' source and
`translation`. Fake model, moto DynamoDB. The requests are the owner's real one and the design's example."""
import json

import pytest

from common import intake, lang_names
import video_brief
from tests.test_hardening import launcher  # noqa: F401  (the fixture)
from tests.test_intake_safety import U, ev, tables  # noqa: F401

NINE = "en,es,fr,de,it,pt,nl,pl,fi"
OWNER = "video for children of speaking in different languages okay so can we English Italian Spanish German French and talk about topic that is really important for children so"
FOX = "a French fox, a German bear and an Italian owl explain why the sea is salty"
# what a check that does not know the feature answers: the request "is for a language other than English or Spanish"
LANGUAGE_REFUSAL = {"block": None, "questions": [], "unsupported": {"kind": "language", "message": "VideoMK can only make videos in English or Spanish.", "suggestion": "Try describing your video in English or Spanish."}}


def brief(prompt, answer=None, **body):
    seen = []

    def model(system, user):
        seen.append((system, user))
        return json.dumps(answer or {"block": None, "unsupported": None, "questions": []})
    r = video_brief.handler(ev(prompt, U, **body), None, ask=model)
    return json.loads(r["body"]), seen


def test_the_prompt_says_several_languages_are_normal(monkeypatch):
    monkeypatch.setenv("VIDEO_LANGUAGES", NINE)
    p = intake.system_prompt()
    assert "SEVERAL LANGUAGES IN ONE VIDEO IS NORMAL AND SUPPORTED" in p and 'never "unsupported" and never a "block"' in p
    assert "French, German, Italian, Portuguese, Dutch, Polish or Finnish" in p.replace("English, Spanish, ", "") or "Finnish" in p   # the stage's own languages are named
    assert "@@LOOKS@@" not in p and "Japanese" in p
    monkeypatch.delenv("VIDEO_LANGUAGES")
    assert "English or Spanish" in intake.system_prompt()                                               # a stage with two languages keeps its sentence


@pytest.mark.parametrize("prompt", [OWNER, FOX,
                                    "Un renard français, un ours allemand et un hibou italien expliquent pourquoi la mer est salée",
                                    "Un zorro francés y un oso alemán hablan del mar, cada uno en su idioma",
                                    "Ein französischer Fuchs und ein deutscher Bär sprechen miteinander, jeder in seiner Sprache, über das Meer",
                                    "make the characters speak different languages and talk about friendship"])
def test_a_request_that_asks_for_other_languages_is_never_unsupported(tables, monkeypatch, prompt):
    monkeypatch.setenv("VIDEO_LANGUAGES", NINE)
    body, _ = brief(prompt, LANGUAGE_REFUSAL)                  # even when the model says "language"
    assert body["status"] == "ok" and "message" not in body, body
    assert intake.asks_for_languages(prompt)


@pytest.mark.parametrize("prompt", ["Explain photosynthesis to children", "I want to learn French grammar", "Los verbos irregulares en francés", "Explain the history of the Polish economy"])
def test_one_language_named_is_not_polyglot(tables, prompt):
    assert not intake.asks_for_languages(prompt)


def test_a_request_really_written_in_a_language_we_lack_is_still_unsupported(tables, monkeypatch):
    monkeypatch.setenv("VIDEO_LANGUAGES", "en,es")
    body, _ = brief("これは海についてのビデオです。魚と海について説明してください。", LANGUAGE_REFUSAL)
    assert body["status"] == "not_supported"
    body, _ = brief("Explique por que o mar é salgado, em português", LANGUAGE_REFUSAL)               # one language named, not several: the model's word stands
    assert body["status"] == "not_supported"


def test_a_check_failure_never_blocks_these_requests(tables):
    body, _ = brief(FOX, {"block": None, "questions": [], "unsupported": {"kind": "language", "message": "I can't make this.", "suggestion": ""}})
    assert body["status"] == "ok"


def test_the_form_values_carry_the_languages_and_the_translation(tables, monkeypatch):
    monkeypatch.setenv("VIDEO_LANGUAGES", NINE)
    options = {"look": "cartoon", "cast": ["fox", {"id": "bear", "language": "de"}], "translation": "on", "language": "en"}
    clean = intake.clean_options(options)
    assert clean["cast"] == ["fox", "bear"] and clean["cast_languages"] == {"bear": "de"} and clean["translation"] == "on" and clean["look"] == "cartoon"
    assert intake.clean_options({"translation": "off"})["translation"] == "off" and "translation" not in intake.clean_options({"translation": "maybe"})
    body, seen = brief("Why is the sea salty?", options=options)
    assert body["status"] == "ok"
    line = seen[0][1].split("\n")[0]
    assert '"cast_languages": {"bear": "de"}' in line and '"translation": "on"' in line


def test_the_language_names_table_reads_the_nine_languages():
    assert lang_names.codes(OWNER) == ["en", "it", "es", "de", "fr"]
    assert lang_names.codes(FOX) == ["fr", "de", "it"]
    assert lang_names.codes("Un zorro francés y un oso alemán") == ["fr", "de"]
    assert lang_names.codes("Ein französischer Fuchs, ein polnischer Bär und eine finnische Eule") == ["fr", "pl", "fi"]
    assert lang_names.codes("un gatto spagnolo e un cane portoghese") == ["es", "pt"] and lang_names.codes("een Nederlandse vos") == ["nl"]
    assert lang_names.codes("PO FRANCUSKU i po polsku") == ["fr", "pl"] and lang_names.codes("ranskaksi ja suomeksi") == ["fr", "fi"]
    assert lang_names.cue("each in their own language") and lang_names.cue("cada uno en su idioma") and lang_names.cue("chacun dans sa propre langue")
    assert lang_names.cue("verschiedene Sprachen") and not lang_names.cue("learn French grammar") and not lang_names.cue("Explain why the sea is salty")
