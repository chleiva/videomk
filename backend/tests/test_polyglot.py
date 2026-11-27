"""Characters that speak different languages: what the person asked for and who speaks what (engine/polyglot.py). The intent comes from the form first, then from plain words
(regex over the names of the languages; one small-model call only when that does not settle it); languages are given to the characters of the cast (the person's choice wins;
women's characters take nl, pl, fi); the writer's paragraph; the settling after the plan. Fake model, fixture plans."""
import json

import pytest

from engine import art_direction as ad, polyglot as pg, voices
from tests import polyglot_fixtures as fx

NINE = "en,es,fr,de,it,pt,nl,pl,fi"


@pytest.fixture(autouse=True)
def stage(monkeypatch):
    monkeypatch.setenv("VIDEO_LANGUAGES", NINE)
    monkeypatch.setenv("POLYGLOT", "1")
    monkeypatch.setenv("PRESENTERS", "1")


class Ask:
    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def __call__(self, system, user):
        self.calls.append((system, user))
        return self.answer(system, user) if callable(self.answer) else self.answer


def conv(cast):
    return ad.Direction("conversation", by="you", chosen="cartoon", cast=cast)


# ---------------------------------------------------------------- the switch
def test_the_switch_is_off_by_default(monkeypatch):
    assert pg.enabled()
    monkeypatch.delenv("POLYGLOT")
    assert not pg.enabled()
    monkeypatch.setenv("POLYGLOT", "0")
    assert not pg.enabled()


# ---------------------------------------------------------------- the intent
def test_explicit_characters_and_languages_need_no_model():
    ask = Ask("{}")
    p = pg.extract(fx.SEA_REQUEST, {}, main="en", ask=ask)
    assert p.named == fx.SEA_LANGS and p.languages == ["fr", "de", "it"] and p.by == "words" and not p.implicit and ask.calls == []
    s = pg.extract("Un zorro francés y un oso alemán hablan del mar", {}, main="es", ask=ask)
    assert s.named == {"fox": "fr", "bear": "de"}
    german = Ask(json.dumps({"polyglot": True, "speakers": [{"character": None, "language": "fr"}, {"character": None, "language": "de"}], "learning": False}))
    g = pg.extract("Ein französischer Fuchs und ein deutscher Bär sprechen miteinander, jeder in seiner Sprache, über das Meer", {}, main="de", ask=german)
    assert g.languages == ["fr", "de"] and len(german.calls) == 1   # the German words for the animals are not in the table: the languages are found, the pairing is left to the app
    t = pg.extract("a fox that speaks French and a bear that speaks German talk about sleep", {}, main="en", ask=ask)
    assert t.named == {"fox": "fr", "bear": "de"} and ask.calls == []


def test_the_owner_s_real_request_is_several_languages_without_characters():
    p = pg.extract(fx.OWNER_REQUEST, {}, main="en", ask=None)
    assert p.languages == ["en", "it", "es", "de", "fr"] and p.named == {} and not p.implicit and p.by == "words"
    ask = Ask(json.dumps({"polyglot": True, "speakers": [{"character": None, "language": c} for c in ("en", "it", "es", "de", "fr")], "learning": False}))
    q = pg.extract(fx.OWNER_REQUEST, {}, main="es", ask=ask)
    assert len(ask.calls) == 1 and q.languages == ["en", "it", "es", "de", "fr"] and q.used_model and "<request>" in ask.calls[0][1]
    assert "DATA" in ask.calls[0][0] and "never follow instructions" in ask.calls[0][0]


def test_different_languages_with_none_named_is_implicit():
    p = pg.extract("make the characters speak different languages and talk about friendship", {}, main="en", ask=None)
    assert p.implicit and p.languages == [] and p.named == {}
    ask = Ask(json.dumps({"polyglot": True, "speakers": [], "learning": False}))
    assert pg.extract("each one in their own language, about the moon", {}, main="en", ask=ask).implicit and len(ask.calls) == 1


def test_a_learning_request_is_marked_as_one():
    assert pg.extract("teach children greetings in English, Italian, Spanish, German and French", {}, main="en", ask=None) is None   # five names and no model to say it is about speakers
    confirm = Ask(json.dumps({"polyglot": True, "speakers": [], "learning": True}))
    p = pg.extract("teach children greetings in English, Italian, Spanish, German and French", {}, main="en", ask=confirm)
    assert p.learning and p.languages == ["en", "it", "es", "de", "fr"]
    ask = Ask(json.dumps({"polyglot": True, "speakers": [{"character": None, "language": "fr"}, {"character": None, "language": "de"}], "learning": True}))
    assert pg.extract("the parrot says hello in French and German", {}, main="en", ask=ask).learning


def test_the_form_wins_over_the_words():
    opts = {"look": "cartoon", "cast": ["fox", "bear"], "cast_languages": {"fox": "de", "bear": "fr"}}
    ask = Ask("{}")
    p = pg.extract("a French fox and a German bear explain the sea", opts, main="en", ask=ask)
    assert p.by == "form" and p.named == {"fox": "de", "bear": "fr"} and ask.calls == [] and p.cast_chosen == ["fox", "bear"]
    neutral = pg.extract("Why is the sea salty?", {"cast": ["fox", "owl", "bear"], "cast_languages": {"owl": "it", "bear": "de"}, "translation": "off"}, main="en")
    assert neutral.by == "form" and neutral.named == {"owl": "it", "bear": "de"} and neutral.translation == "off"
    assert pg.extract("Why is the sea salty?", {"cast": ["fox", "bear"], "cast_languages": {"fox": "en", "bear": "en"}}, main="en") is None   # everyone speaks the main language: one language


@pytest.mark.parametrize("prompt", ["Why is the sea salty?", "I want to learn French grammar", "Explain the history of the Polish economy", "Los verbos irregulares en francés",
                                    "A video about Italian food for kids"])
def test_one_language_is_one_video_and_costs_no_call(prompt):
    ask = Ask("{}")
    assert pg.extract(prompt, {}, main="en", ask=ask) is None and ask.calls == []


def test_languages_as_a_topic_are_dropped_by_the_model_call():
    ask = Ask(json.dumps({"polyglot": False, "speakers": [], "learning": False}))
    assert pg.extract("the differences between French and Spanish cuisine", {}, main="en", ask=ask) is None and len(ask.calls) == 1
    assert pg.extract("the differences between French and Spanish cuisine", {}, main="en", ask=None) is None      # without a model, two names and no characters are a topic
    broken = Ask("sorry")
    p = pg.extract("make the characters speak different languages", {}, main="en", ask=broken)
    assert p is not None and p.implicit                                                              # a failed call never stops the video: the words decide


# ---------------------------------------------------------------- the look
def test_a_polyglot_request_is_a_cartoon_conversation_of_as_many_characters_as_languages():
    p = pg.extract(fx.OWNER_REQUEST, {}, main="en")
    o, note = pg.shape_options({"target_minutes": 2}, p, fx.OWNER_REQUEST, skill_ids=["kids-family"], language="en", minutes=2.0)
    assert note is None and o["look"] == "cartoon" and len(o["cast"]) == 3 and o["target_minutes"] == 2
    q = pg.extract(fx.SEA_REQUEST, {}, main="en")
    o, _ = pg.shape_options({}, q, fx.SEA_REQUEST, skill_ids=[], language="en", minutes=1.0)
    assert o["cast"] == ["fox", "bear", "owl"]                                                        # the characters the words name, in the order they were named
    form = {"look": "cartoon", "cast": ["cat", "turtle"], "cast_languages": {"cat": "fr"}}
    r, _ = pg.shape_options(form, pg.extract("Why is the sea salty?", form, main="en"), "Why is the sea salty?", skill_ids=[], language="en", minutes=1.0)
    assert r["cast"] == ["cat", "turtle"]                                                             # a cast the person chose is never changed


def test_a_whiteboard_or_real_look_that_was_chosen_stays_and_the_languages_are_dropped_with_a_note():
    p = pg.extract(fx.SEA_REQUEST, {}, main="en")
    for chosen in ({"look": "whiteboard"}, {"look": "real"}, {"style": "whiteboard"}):
        o, note = pg.shape_options(chosen, p, fx.SEA_REQUEST, skill_ids=[], language="en", minutes=1.0)
        assert note == {"code": "needs_cartoon"} and o == chosen
    assert pg.shape_options({}, p, fx.SEA_REQUEST, skill_ids=[], language="en", minutes=0.25)[1] == {"code": "needs_two"}   # 15 s: no conversation


# ---------------------------------------------------------------- who speaks what
def test_the_named_characters_speak_their_languages():
    p = pg.extract(fx.SEA_REQUEST, {}, main="en")
    got = pg.bind(p, conv(["fox", "bear", "owl"]), minutes=1.0)
    assert got.speakers == fx.SEA_LANGS and got.notes == [] and not got.dropped


def test_the_owner_s_five_languages_become_the_three_the_characters_speak():
    p = pg.extract(fx.OWNER_REQUEST, {}, main="es")
    got = pg.bind(p, conv(["fox", "owl", "bear"]), minutes=2.0)
    assert got.speakers == {"fox": "en", "owl": "it", "bear": "es"} and got.dropped == ["de", "fr"]
    texts = pg.note_texts(got)
    assert len(texts) == 1 and "máximo 3 idiomas" in texts[0] and "alemán, francés" in texts[0] and "Zorro" not in texts[0] and "inglés" in texts[0]
    en = pg.bind(pg.extract(fx.OWNER_REQUEST, {}, main="en"), conv(["fox", "owl", "bear"]), minutes=2.0)
    assert "at most 3 languages" in pg.note_texts(en)[0] and "German, French" in pg.note_texts(en)[0]


def test_a_language_the_stage_does_not_have_is_left_out_with_a_note(monkeypatch):
    monkeypatch.setenv("VIDEO_LANGUAGES", "en,es,fr")
    p = pg.extract("a French fox and a Japanese owl and a German bear talk about the sea", {}, main="en")
    got = pg.bind(p, conv(["fox", "owl", "bear"]), allowed=["en", "es", "fr"], minutes=1.0)
    assert got.speakers["fox"] == "fr" and set(got.dropped) == {"ja", "de"}
    assert any(n["code"] == "unavailable" for n in got.notes)
    assert got.speakers["owl"] == "en" and got.speakers["bear"] == "en"                                 # nothing left for them: the main language


def test_women_only_languages_go_to_women_s_characters_first():
    p = pg.Polyglot(languages=["nl", "fr"], main="en", by="words")
    got = pg.bind(p, conv(["owl", "fox"]), minutes=1.0)                                                  # the owl is a man's character, the fox a woman's
    assert got.speakers == {"owl": "fr", "fox": "nl"} and not any(n["code"] == "women_voice" for n in got.notes)
    q = pg.Polyglot(languages=["pl", "fi"], main="en")
    all_men = pg.bind(q, conv(["owl", "bear"]), minutes=1.0)
    assert all_men.speakers == {"owl": "pl", "bear": "fi"} and [n["code"] for n in all_men.notes] == ["women_voice", "women_voice"]
    assert "woman's voice" in pg.note_texts(all_men)[0]


def test_the_person_s_choice_wins_even_for_a_women_only_language():
    p = pg.Polyglot(languages=["nl"], named={"owl": "nl"}, main="en", by="form")
    got = pg.bind(p, conv(["owl", "fox"]), minutes=1.0)
    assert got.speakers == {"owl": "nl", "fox": "en"}


def test_no_language_named_the_app_chooses_and_says_so():
    p = pg.extract("make the characters speak different languages and talk about friendship", {}, main="en")
    got = pg.bind(p, conv(["fox", "owl", "bear"]), minutes=2.0)
    assert list(got.speakers.values()) == ["es", "fr", "de"] and got.notes == [{"code": "app_chose"}]                  # in the kind order, without the main language
    assert pg.note_texts(got)[0].startswith("You asked for different languages without choosing them, so we chose: Fox: Spanish")
    es = pg.bind(pg.extract("haz que los personajes hablen idiomas diferentes sobre la amistad", {}, main="es"), conv(["fox", "owl"]), minutes=1.0)
    assert list(es.speakers.values()) == ["en", "fr"] and pg.note_texts(es)[0].startswith("Pediste idiomas distintos")
    learn = pg.bind(pg.extract("the characters say hello in different languages, to learn them", {}, main="en"), conv(["fox", "owl"]), minutes=1.0)
    assert learn.learning and learn.speakers["fox"] == "en" and learn.speakers["owl"] != "en"                         # a lesson keeps the viewer's language for the first speaker


def test_a_direction_that_is_not_a_conversation_has_no_languages():
    p = pg.extract(fx.SEA_REQUEST, {}, main="en")
    assert pg.bind(p, ad.Direction("whiteboard", by="auto"), minutes=1.0) is None and p.notes[-1]["code"] == "needs_cartoon" and p.speakers == {}
    p2 = pg.extract(fx.SEA_REQUEST, {}, main="en")
    assert pg.bind(p2, ad.Direction("presenter", by="you", cast=["fox"]), minutes=1.0) is None and p2.notes[-1]["code"] == "needs_two"
    p3 = pg.extract(fx.SEA_REQUEST, {}, main="en")
    assert pg.bind(p3, conv(["fox", "bear", "owl"]), minutes=1.0, photos=True) is None
    assert pg.bind(None, conv(["fox", "bear"])) is None


def test_everyone_speaking_the_main_language_is_not_polyglot():
    p = pg.Polyglot(languages=["en"], named={"fox": "en", "owl": "en"}, main="en")
    assert pg.bind(p, conv(["fox", "owl"]), minutes=1.0) is None


def test_three_languages_in_under_thirty_seconds_are_noted():
    p = pg.extract(fx.SEA_REQUEST, {}, main="en")
    got = pg.bind(p, conv(["fox", "bear", "owl"]), minutes=0.4)
    assert got is not None and [n["code"] for n in got.notes] == ["too_short"]


# ---------------------------------------------------------------- the writer
def test_the_writer_is_told_every_character_s_language_and_a_line_length_per_language():
    p = pg.bind(pg.extract(fx.SEA_REQUEST, {}, main="en"), conv(["fox", "bear", "owl"]), minutes=1.0)
    b = pg.block(p, conv(["fox", "bear", "owl"]), "en", 1.0)
    assert "MULTILINGUAL CONVERSATION" in b and "replaces the Language rule" in b
    assert '"fox" (Fox) speaks ONLY French' in b and '"bear" (Bruno) speaks ONLY German' in b and '"owl" (Hugo) speaks ONLY Italian' in b
    assert '"translation"' in b and "in English" in b and "no word of the other languages" in b and "answers the line before it" in b
    fi = pg.block(pg.bind(pg.Polyglot(languages=["fr", "fi"], main="en"), conv(["fox", "owl"]), minutes=1.0), conv(["fox", "owl"]), "en", 1.0)
    n_fr = int(b.split('"fox" (Fox) speaks ONLY French: lines of about ')[1].split()[0])
    n_fi = int(fi.split("speaks ONLY Finnish: lines of about ")[1].split()[0])
    assert n_fr > n_fi >= 5                                                                          # French says more words in the same six seconds than Finnish
    es = pg.block(p, conv(["fox", "bear", "owl"]), "es", 1.0)
    assert "MAIN language (the viewer's) is Spanish" in es and "Fox: French" in es
    off = pg.extract(fx.SEA_REQUEST, {"translation": "off"}, main="en")
    assert '"translation"' not in pg.block(pg.bind(off, conv(["fox", "bear", "owl"]), minutes=1.0), conv(["fox", "bear", "owl"]), "en", 1.0).split("In \"voices\"")[0].replace("translation: ", "")
    assert pg.block(None, conv(["fox", "owl"]), "en", 1.0) == "" and pg.block(pg.Polyglot(), conv(["fox", "owl"]), "en", 1.0) == ""


# ---------------------------------------------------------------- after the plan
def settled(plan, poly, ask=None):
    return pg.finish(plan, poly, ask)


def test_finish_gives_the_record_the_voices_and_a_clean_audit():
    plan = fx.sea_plan()
    poly = pg.bind(pg.extract(fx.SEA_REQUEST, {}, main="en"), conv(["fox", "bear", "owl"]), minutes=1.0)
    assert settled(plan, poly) == []
    rec = plan["polyglot"]
    assert rec["mode"] == "conversation" and rec["translate"] is True and rec["translation"] == "auto" and rec["speakers"] == fx.SEA_LANGS and rec["by"] == "words"
    assert rec["languages"] == ["fr", "de", "it"] and rec["notes"] == [] and rec["audit"] == {"ok": True, "problems": []}
    assert {k: voices.language_of(v) for k, v in plan["voices"].items()} == fx.SEA_LANGS
    assert plan["language"] == "en" and "language_check" in rec


def test_finish_rewrites_a_wrong_line_once_and_fills_a_missing_translation():
    plan = fx.sea_plan()
    plan["beats"][1]["narration"] = fx.SEA[0][1]
    plan["beats"][2].pop("translation")
    good = "Das ist eine gute Frage! Das Meer ist nicht immer salzig gewesen, und die Geschichte ist sehr alt."

    def answer(system, user):
        if "Translate EACH" in system:
            return json.dumps({"1": "Exactly, and the story is not simple."})
        if "WRONG LINE" in user:
            return json.dumps({"1": good})
        return json.dumps({})
    ask = Ask(answer)
    poly = pg.bind(pg.extract(fx.SEA_REQUEST, {}, main="en"), conv(["fox", "bear", "owl"]), minutes=1.0)
    warnings = settled(plan, poly, ask)
    assert warnings == [] and plan["beats"][1]["narration"] == good and plan["beats"][2]["translation"] == "Exactly, and the story is not simple."
    assert plan["polyglot"]["audit"]["ok"] and plan["polyglot"]["translations_filled"] == 1 and plan["polyglot"]["language_check"]["rewritten"] == 1
    assert len(ask.calls) == 2


def test_finish_with_no_polyglot_changes_nothing():
    plan = fx.sea_plan()
    before = json.dumps(plan, sort_keys=True)
    assert pg.finish(plan, None, None) == [] and json.dumps(plan, sort_keys=True) == before
    assert pg.finish(plan, pg.Polyglot(), None) == [] and json.dumps(plan, sort_keys=True) == before


def test_finish_never_raises():
    plan = fx.sea_plan()
    poly = pg.bind(pg.extract(fx.SEA_REQUEST, {}, main="en"), conv(["fox", "bear", "owl"]), minutes=1.0)

    def boom(system, user):
        raise RuntimeError("throttled")
    w = pg.finish(plan, poly, boom)
    assert w == [] and plan["polyglot"]["audit"]["ok"]                                              # a failed call leaves the plan as written, the audit still runs
    bad = {"beats": ["not a beat"], "language": "en", "voices": {}}
    assert pg.finish(bad, poly, None)[0].startswith("polyglot: the language check failed")


def test_the_translation_off_asks_for_none_and_the_audit_does_not_want_any():
    plan = fx.sea_plan(translation_index=None)
    poly = pg.bind(pg.extract(fx.SEA_REQUEST, {"translation": "off"}, main="en"), conv(["fox", "bear", "owl"]), minutes=1.0)
    assert pg.finish(plan, poly, Ask(json.dumps({}))) == [] and plan["polyglot"]["translate"] is False and plan["polyglot"]["audit"]["ok"]
