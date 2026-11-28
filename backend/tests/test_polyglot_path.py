"""The whole path of a multilingual conversation through the director with fixture plans (no real model, no network): the request's intent is extracted, the cast takes its
languages, the writer is told them, and the plan that comes out has a voice of the right language per speaker, every line in its speaker's language, voice language equal to line
language, a translation row, and a length in seconds. A plan of today (switch off, or one language) comes out the same."""
import json

import pytest

from engine import director, length, plan_langs, polyglot as pg, voices
from tests import polyglot_fixtures as fx
from tests.test_skills import _ask_small

NINE = "en,es,fr,de,it,pt,nl,pl,fi"


@pytest.fixture(autouse=True)
def stage(monkeypatch):
    monkeypatch.setenv("VIDEO_LANGUAGES", NINE)
    monkeypatch.setenv("PRESENTERS", "1")
    monkeypatch.delenv("BG_ANIMATED", raising=False)
    monkeypatch.delenv("BG_LOOPS", raising=False)
    from engine import research
    monkeypatch.setattr(research, "gather_notes", lambda *a, **k: ("Sea water is salty because rivers carry salts from rocks.", []))


def writer(rows, cast, translation_index=2, lang_of=None):
    """The script model: returns the fixture dialogue as the writer would, and keeps what it was told."""
    seen = []

    def ask_big(system, user):
        seen.append(system)
        beats = []
        ids = {}
        if lang_of:   # the writer reads who speaks which language from the paragraph it was shown and gives each fixture line to that character
            import re
            names = {"English": "en", "Italian": "it", "Spanish": "es", "French": "fr", "German": "de"}
            ids = {names[m.group(2)]: m.group(1) for m in re.finditer(r'\* "(\w+)" \([^)]*\) speaks ONLY (\w+)', system)}
        for row in rows:
            b = {"narration": row[1], "speaker": ids.get(lang_of[row[0]], row[0]) if lang_of else row[0], "scene": {"type": "title", "props": {"title": row[1].split(".")[0].split("!")[0][:40]}}}
            if len(row) > translation_index and translation_index is not None:
                b["translation"] = row[translation_index]
            beats.append(b)
        return json.dumps({"legit": True, "title": "T", "description": "d", "mood": "bright", "theme": "sunrise",
                           "voices": {c: "a friendly voice" for c in cast}, "beats": beats})
    ask_big.seen = seen
    return ask_big


def small(extra=None):
    base = _ask_small(["explainer-education"])

    def ask(system, user, n=120):
        if extra:
            r = extra(system, user)
            if r is not None:
                return r
        if system.startswith("You translate lines"):   # lines the length fit cut lose their translation: a fake translator says "<line> (translated)"
            rows = [l.split(". ", 1)[1].split("] ", 1)[1] for l in user.split("\n")]
            return json.dumps({str(k + 1): f"{r.split('.')[0]} (translated)." for k, r in enumerate(rows)})
        return base(system, user, n)
    return ask


def run(prompt, rows, cast, *, minutes=1.0, options=None, small_ask=None, translation_index=2, language="en", lang_of=None):
    big = writer(rows, cast, translation_index, lang_of)
    return director.direct(prompt, minutes=minutes, ask_small=small_ask or small(), ask_big=big, language=language, options=options), big


def lang_of_voice(plan, sid):
    return voices.language_of(plan["voices"][sid])


def check_plan(plan, speakers):
    assert plan["polyglot"]["speakers"] == speakers and plan["language"] in ("en", "es")
    for sid, lang in speakers.items():
        assert lang_of_voice(plan, sid) == lang                                   # a voice of the speaker's language
    assert len({plan["voices"][s] for s in speakers}) == len(speakers)           # nobody shares a voice
    for b in plan["beats"]:
        if b.get("silent"):
            continue
        assert voices.language_of(plan["voices"][b["speaker"]]) == plan_langs.beat_lang(plan, b) == speakers[b["speaker"]]
        assert plan_langs.heuristic_lang(b["narration"]) in (None, speakers[b["speaker"]])   # every line in its speaker's language
    assert plan["polyglot"]["audit"] == {"ok": True, "problems": []}


def test_the_sea_request_three_characters_three_languages(monkeypatch):
    monkeypatch.setenv("POLYGLOT", "1")
    out, big = run(fx.SEA_REQUEST, fx.SEA, ["fox", "bear", "owl"])
    plan = out["plan"]
    assert out["research"]["polyglot"]["speakers"] == fx.SEA_LANGS and out["research"]["polyglot"]["audit_ok"] is True
    check_plan(plan, fx.SEA_LANGS)
    assert "MULTILINGUAL CONVERSATION" in big.seen[0] and "speaks ONLY French" in big.seen[0] and "speaks ONLY German" in big.seen[0] and "speaks ONLY Italian" in big.seen[0]
    assert plan["beats"][0]["translation"].startswith("Hello friends")
    assert plan_langs.shows_translation(plan) and all(plan_langs.translation_for(plan, b) for b in plan["beats"])
    extras = plan_langs.scene_extras(plan, plan["beats"][1])
    assert extras["lang"] == "de" and extras["translation"].startswith("That is a great question")
    secs = length.estimate_total(plan)
    assert 45 <= secs <= 90, secs
    assert plan["language"] == "en" and plan["title"]


def test_the_owner_s_request_five_languages_become_three_with_a_note(monkeypatch):
    monkeypatch.setenv("POLYGLOT", "1")
    asked = []

    def extra(system, user):
        if system.startswith("You read a request for a children's cartoon video"):
            asked.append(user)
            return json.dumps({"polyglot": True, "speakers": [], "mode": "conversation", "learning": False})
        return None
    rows = [(r[0], r[1], r[3]) for r in fx.FRIENDS]   # translations into Spanish: this plan's main language is Spanish
    out, big = run(fx.OWNER_REQUEST, rows, ["fox", "owl", "bear"], minutes=1.0, small_ask=small(extra), language="es", lang_of=fx.FRIENDS_LANGS)
    plan = out["plan"]
    assert len(asked) == 1                                                     # one small call, because the words alone did not settle it
    rec = plan["polyglot"]
    assert len(rec["speakers"]) == 3 and set(rec["speakers"].values()) == {"en", "it", "es"}
    assert rec["notes"] and any("French" in n or "francés" in n or "Alemán" in n or "alemán" in n or "German" in n for n in rec["notes"])
    assert plan["language"] == "es"
    speakers = rec["speakers"]
    for sid, lang in speakers.items():
        assert lang_of_voice(plan, sid) == lang
    assert rec["audit"]["ok"] is True
    assert sorted(speakers.values()) == ["en", "es", "it"]   # the app chose the characters (the request named none) and gave each a language
    check_plan(plan, speakers)
    assert 40 <= length.estimate_total(plan) <= 90


def test_the_form_wins_over_the_words(monkeypatch):
    monkeypatch.setenv("POLYGLOT", "1")
    opts = {"cast": ["fox", "bear", "owl"], "cast_languages": {"fox": "fr", "bear": "de", "owl": "it"}, "look": "cartoon"}
    out, _ = run("why the sea is salty", fx.SEA, ["fox", "bear", "owl"], options=opts)
    assert out["research"]["polyglot"]["by"] == "form"
    check_plan(out["plan"], fx.SEA_LANGS)


def test_a_wrong_language_line_is_rewritten_once_and_voices_stay_right(monkeypatch):
    monkeypatch.setenv("POLYGLOT", "1")
    rows = [list(r) for r in fx.SEA]
    rows[1][1] = fx.SEA[0][1]   # the bear speaks French
    good = "Das ist eine gute Frage! Das Meer ist nicht immer salzig gewesen, und die Geschichte ist sehr alt."

    def extra(system, user):
        if "WRONG LINE" in user:
            return json.dumps({"1": good})
        return None
    out, _ = run(fx.SEA_REQUEST, rows, ["fox", "bear", "owl"], small_ask=small(extra))
    assert out["plan"]["beats"][1]["narration"] == good
    check_plan(out["plan"], fx.SEA_LANGS)


def test_with_the_switch_off_the_same_request_is_a_plan_of_today(monkeypatch):
    monkeypatch.delenv("POLYGLOT", raising=False)
    out, big = run(fx.SEA_REQUEST, fx.SEA, ["fox", "bear", "owl"])
    assert "polyglot" not in out["plan"] and "polyglot" not in out["research"] and "MULTILINGUAL" not in big.seen[0]
    assert plan_langs.scene_extras(out["plan"], out["plan"]["beats"][0]) == {}


def test_one_language_request_is_untouched_even_with_the_switch_on(monkeypatch):
    monkeypatch.setenv("POLYGLOT", "1")
    out, big = run("why the sea is salty", [("narrator",) + r[1:2] for r in fx.SEA[:4]], ["narrator"])
    assert "polyglot" not in out["plan"] and "MULTILINGUAL" not in big.seen[0]


def test_a_whiteboard_request_stays_a_board_and_says_why(monkeypatch):
    monkeypatch.setenv("POLYGLOT", "1")
    out, big = run(fx.SEA_REQUEST, fx.SEA, ["fox", "bear", "owl"], options={"look": "whiteboard"})
    assert "polyglot" not in out["plan"] and "MULTILINGUAL" not in big.seen[0]
    assert any(w.startswith("polyglot:") for w in out["warnings"]) and out["research"]["polyglot"]["notes"]


def test_the_timeline_carries_the_translation_and_a_plan_of_today_gets_none(monkeypatch):
    from engine.timeline import build_timeline, _scene_fingerprint
    from engine.renderer import Renderer
    monkeypatch.setenv("POLYGLOT", "1")
    out, _ = run(fx.SEA_REQUEST, fx.SEA, ["fox", "bear", "owl"])
    plan = out["plan"]
    tl = build_timeline(plan, [{"duration": 4.0} for _ in plan["beats"]], video_id="v")
    spoken = [sc for sc in tl["scenes"] if sc["id"] != "endcard"]
    assert all(sc.get("translation") and sc.get("lang") in ("fr", "de", "it") for sc in spoken)
    assert _scene_fingerprint(spoken[0])["translation"] == spoken[0]["translation"]
    plain = json.loads(json.dumps(plan))
    plain.pop("polyglot")
    tl2 = build_timeline(plain, [{"duration": 4.0} for _ in plain["beats"]], video_id="v")
    assert all("translation" not in sc and "lang" not in sc for sc in tl2["scenes"]) and "translation" not in _scene_fingerprint(tl2["scenes"][0])
    r = Renderer(tl, draft=True)   # a frame with the translation row draws (and with captions off it still does)
    img = r._draw_spec(spoken[0], 1.0)
    assert img.size[0] > 0
    tl["captions"] = False
    assert Renderer(tl, draft=True)._draw_spec(spoken[0], 1.0).size[0] > 0
