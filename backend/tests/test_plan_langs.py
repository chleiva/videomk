"""The language of every spoken line and the checks that keep it true (engine/plan_langs.py): who speaks what, the per-line language check (heuristic first, one batched
model call for the rest), the single rewrite of a wrong line, a voice of the right language per speaker, the audit voice language == line language, the translation row,
the length. Fake model, fixture plans (tests/polyglot_fixtures.py)."""
import json

import pytest

from engine import length, plan_langs as pl, voices
from tests import polyglot_fixtures as fx

NINE = "en,es,fr,de,it,pt,nl,pl,fi"


@pytest.fixture(autouse=True)
def stage(monkeypatch):
    monkeypatch.setenv("VIDEO_LANGUAGES", NINE)


def with_polyglot(p, speakers, translation="auto", translate=True):
    p = fx.deep(p)
    p["polyglot"] = {"mode": "conversation", "translate": translate, "translation": translation, "speakers": dict(speakers)}
    return p


class Ask:
    """A fake small model: answers from a function of (system, user); records every call."""

    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def __call__(self, system, user):
        self.calls.append((system, user))
        return self.answer(system, user)


# ---------------------------------------------------------------- who speaks what
def test_a_plan_without_polyglot_is_one_language_and_untouched():
    p = fx.sea_plan()
    assert not pl.is_polyglot(p) and pl.beat_lang(p, p["beats"][1]) == "en" and pl.languages_of(p) == ["en"]
    assert pl.audit(p) == {"ok": True, "problems": []}
    assert pl.translation_for(p, p["beats"][0]) is None and pl.scene_extras(p, p["beats"][0]) == {} and not pl.shows_translation(p)


def test_every_beat_has_its_speakers_language():
    p = with_polyglot(fx.sea_plan(), fx.SEA_LANGS)
    assert [pl.beat_lang(p, b) for b in p["beats"][:4]] == ["fr", "de", "it", "fr"]
    assert pl.speaker_lang(p, "bear") == "de" and pl.speaker_lang(p, "nobody") == "en"
    assert pl.languages_of(p) == ["fr", "de", "it"] and pl.is_polyglot(p)
    p["beats"][1]["lang"] = "it"                                      # a beat's own `lang` wins
    assert pl.beat_lang(p, p["beats"][1]) == "it"


def test_the_main_language_comes_first_when_it_is_spoken():
    p = with_polyglot(fx.friends_plan("en"), fx.FRIENDS_LANGS)
    assert pl.languages_of(p) == ["en", "it", "es"]
    assert pl.is_polyglot(with_polyglot(fx.sea_plan(), {"fox": "fr", "bear": "fr", "owl": "fr"}))   # only French spoken, for an English viewer: still needs its translation row


# ---------------------------------------------------------------- the language of each line
def test_the_fixture_lines_are_judged_by_the_heuristic_alone_or_one_call():
    p = with_polyglot(fx.sea_plan(), fx.SEA_LANGS)
    r = pl.check_lines(p, None)
    assert r["wrong"] == [] and r["unsure"] == [] and r["asked"] == 0 and r["ok"] == len(p["beats"])
    q = with_polyglot(fx.friends_plan("en"), fx.FRIENDS_LANGS)           # short lines are beyond the word counts: unsure, never wrong
    r = pl.check_lines(q, None)
    assert r["wrong"] == [] and 0 < len(r["unsure"]) < len(q["beats"])
    ask = Ask(lambda s, u: json.dumps({str(k + 1): fx.FRIENDS_LANGS[q["beats"][i]["speaker"]] for k, i in enumerate(r["unsure"])}))
    r2 = pl.check_lines(q, ask)
    assert len(ask.calls) == 1 and r2["wrong"] == [] and r2["unsure"] == [] and r2["asked"] == len(r["unsure"])


def test_a_line_in_the_wrong_language_is_found_without_a_model():
    p = with_polyglot(fx.sea_plan(), fx.SEA_LANGS)
    p["beats"][1]["narration"] = fx.SEA[0][1]                          # the bear speaks the fox's French
    r = pl.check_lines(p, None)
    assert r["wrong"] == [{"beat": 1, "expected": "de", "found": "fr"}]


def test_the_lines_the_heuristic_cannot_judge_go_to_one_batched_call():
    p = with_polyglot(fx.sea_plan(), fx.SEA_LANGS)
    p["beats"][0]["narration"] = "Bonjour !"
    p["beats"][1]["narration"] = "Wunderbar!"
    p["beats"][2]["narration"] = "Grazie!"
    ask = Ask(lambda s, u: json.dumps({"1": "fr", "2": "de", "3": "it"}))
    r = pl.check_lines(p, ask)
    assert len(ask.calls) == 1 and r["asked"] == 3 and r["wrong"] == [] and r["unsure"] == []
    assert "1. Bonjour !" in ask.calls[0][1] and "3. Grazie!" in ask.calls[0][1]
    wrong = Ask(lambda s, u: json.dumps({"1": "fr", "2": "fr", "3": "it"}))   # the model hears "Wunderbar!" as French
    assert pl.check_lines(p, wrong)["wrong"] == [{"beat": 1, "expected": "de", "found": "fr"}]
    assert pl.check_lines(p, None)["unsure"] == [0, 1, 2]              # no model: the benefit of the doubt, nothing is called wrong
    boom = Ask(lambda s, u: "I cannot say")
    assert pl.check_lines(p, boom)["wrong"] == []                     # an unusable answer never fails the plan


def test_a_wrong_line_is_rewritten_once_and_the_plan_says_so():
    p = with_polyglot(fx.sea_plan(), fx.SEA_LANGS)
    good = "Das ist eine gute Frage! Das Meer ist nicht immer salzig gewesen, und die Geschichte ist sehr alt."
    p["beats"][1]["narration"] = fx.SEA[0][1]
    ask = Ask(lambda s, u: json.dumps({"1": good}))
    out = pl.settle(p, ask)
    assert len(ask.calls) == 1 and "German" in ask.calls[0][1] and "WRONG LINE" in ask.calls[0][1] and fx.SEA[2][1][:20] in ask.calls[0][1]   # context: the line after
    assert p["beats"][1]["narration"] == good and out["rewritten"] == 1 and out["warnings"] == [] and out["still_wrong"] == []
    assert p["polyglot"]["language_check"] == {"wrong": 1, "rewritten": 1, "still_wrong": [], "asked": 0, "unsure": 0}
    assert pl.check_lines(p, None)["wrong"] == []


def test_a_line_still_wrong_after_one_rewrite_is_kept_and_named_never_dropped():
    p = with_polyglot(fx.sea_plan(), fx.SEA_LANGS)
    p["beats"][1]["narration"] = fx.SEA[0][1]
    ask = Ask(lambda s, u: json.dumps({"1": fx.SEA[3][1]}))             # the rewrite is French again
    out = pl.settle(p, ask)
    assert len(ask.calls) == 1 and out["still_wrong"] == [1] and "still in fr" in out["warnings"][0] and len(p["beats"]) == 10 and p["beats"][1]["narration"] == fx.SEA[3][1]
    p2 = with_polyglot(fx.sea_plan(), fx.SEA_LANGS)
    p2["beats"][1]["narration"] = fx.SEA[0][1]
    out2 = pl.settle(p2, Ask(lambda s, u: "no"))
    assert out2["still_wrong"] == [1] and "rewrite failed" in out2["warnings"][0] and p2["beats"][1]["narration"] == fx.SEA[0][1]
    p3 = with_polyglot(fx.sea_plan(), fx.SEA_LANGS)
    p3["beats"][1]["narration"] = fx.SEA[0][1]
    assert pl.settle(p3, None)["still_wrong"] == [1]                    # no model at all: named, not changed


# ---------------------------------------------------------------- voices
def test_every_speaker_gets_a_voice_of_its_own_language():
    p = with_polyglot(fx.sea_plan(), fx.SEA_LANGS)
    got = pl.recast(p)
    assert {k: voices.language_of(v) for k, v in got.items()} == fx.SEA_LANGS and p["voices"] == got and len(set(got.values())) == 3
    q = with_polyglot(fx.friends_plan("es"), fx.FRIENDS_LANGS)
    got = pl.recast(q)
    assert {k: voices.language_of(v) for k, v in got.items()} == fx.FRIENDS_LANGS


def test_two_speakers_of_one_language_get_two_voices():
    p = with_polyglot(fx.sea_plan(), {"fox": "fr", "bear": "fr", "owl": "it"})
    got = pl.recast(p)
    assert voices.language_of(got["fox"]) == voices.language_of(got["bear"]) == "fr" and got["fox"] != got["bear"]


def test_a_man_s_character_speaking_dutch_gets_the_dutch_voice_there_is():
    p = with_polyglot(fx.sea_plan(), {"fox": "nl", "bear": "nl", "owl": "pl"})
    got = pl.recast(p)
    assert {voices.language_of(v) for v in got.values()} == {"nl", "pl"} and got["fox"] != got["bear"]   # nl has two voices, both women


def test_the_audit_fails_for_a_voice_of_another_language_and_passes_after_recast():
    p = with_polyglot(fx.sea_plan(), fx.SEA_LANGS)                      # the voices are English ones: Joanna reads the French
    a = pl.audit(p)
    assert not a["ok"] and any("Joanna (en) but written in fr" in x for x in a["problems"])
    pl.recast(p)
    assert pl.audit(p) == {"ok": True, "problems": []}
    p["beats"][4].pop("speaker")                                        # a line with no speaker has no language of its own
    assert any("no language in polyglot.speakers" in x for x in pl.audit(p)["problems"])


def test_the_audit_wants_a_translation_for_lines_that_are_not_in_the_main_language():
    p = with_polyglot(fx.sea_plan(), fx.SEA_LANGS)
    pl.recast(p)
    p["beats"][2].pop("translation")
    a = pl.audit(p)
    assert a["problems"] == ["beat 2: no translation into en"]
    p["polyglot"]["translate"] = False
    assert pl.audit(p)["ok"]


# ---------------------------------------------------------------- the translation row
def test_the_translation_switch():
    p = with_polyglot(fx.friends_plan("en"), fx.FRIENDS_LANGS, "auto")
    en_line, it_line = p["beats"][0], p["beats"][1]
    assert pl.translation_for(p, en_line) is None                       # already in the main language
    assert pl.translation_for(p, it_line).startswith("Hello friends!") and pl.shows_translation(p)
    p["polyglot"]["translation"] = "on"
    assert pl.translation_for(p, en_line) is None                       # a line is never translated into itself
    assert pl.translation_for(p, it_line)
    p["polyglot"]["translation"] = "off"
    assert pl.translation_for(p, it_line) is None and not pl.shows_translation(p)
    q = with_polyglot(fx.friends_plan("es"), fx.FRIENDS_LANGS, "auto")  # main Spanish: the Spanish speaker is not translated, the English one is
    assert pl.translation_for(q, q["beats"][0]).startswith("¡Hola a todos!") and pl.translation_for(q, q["beats"][2]) is None
    q["beats"][5]["silent"] = True
    assert pl.translation_for(q, q["beats"][5]) is None


def test_the_timeline_extras_are_empty_for_a_plan_of_today():
    p = with_polyglot(fx.sea_plan(), fx.SEA_LANGS)
    e = pl.scene_extras(p, p["beats"][1])
    assert e["lang"] == "de" and e["translation"].startswith("That is a great question")
    assert pl.scene_extras(fx.sea_plan(), fx.sea_plan()["beats"][1]) == {}
    q = with_polyglot(fx.friends_plan("en"), fx.FRIENDS_LANGS)
    assert pl.scene_extras(q, q["beats"][0]) == {}


# ---------------------------------------------------------------- length
def test_a_finnish_line_takes_longer_than_a_french_line_of_the_same_words():
    fr, fi = voices.default_voice("fr"), voices.default_voice("fi")
    fr_text = "un deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze"
    fi_text = "yksi kaksi kolme neljä viisi kuusi seitsemän kahdeksan yhdeksän kymmenen yksitoista kaksitoista kolmetoista neljätoista"
    assert len(fr_text.split()) == len(fi_text.split()) == 14
    assert length.estimate_speech(fi_text, "fi", fi) > length.estimate_speech(fr_text, "fr", fr)   # the same number of words, a longer sentence
    assert pl.words_per_line("fr", 6.0) > pl.words_per_line("fi", 6.0) > 0                       # so the writer is told fewer words for the Finnish speaker


def test_the_plan_length_in_seconds_follows_each_speakers_voice():
    p = with_polyglot(fx.sea_plan(), fx.SEA_LANGS)
    before = pl.plan_seconds(p)                                         # English voices reading the lines
    pl.recast(p)
    after = pl.plan_seconds(p)
    assert 40 < before < 120 and 40 < after < 120 and after != before
