"""Deterministic rule functions of scripts/quality_audit.py (no model, no network)."""
import importlib.util
import os
import re

import pytest

_spec = importlib.util.spec_from_file_location("quality_audit", os.path.join(os.path.dirname(__file__), "..", "scripts", "quality_audit.py"))
qa = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(qa)


def beats(*items):
    return [{"id": f"b{i}", "narration": n, "scene": {"type": t, "props": {}}} for i, (n, t) in enumerate(items)]


def test_length_fit_flags():
    b = beats(("one two three four five", "title"), ("six seven eight nine ten", "bullets"))
    assert qa.length_fit(b, 10, 2)["ratio"] == 1.0
    assert qa.length_fit(b, 100, 2)["flag_short"]
    assert qa.length_fit(b, 5, 2)["flag_long"]
    assert qa.length_fit(b, 10, 9)["flag_few_beats"]


def test_hook_and_close():
    h = qa.hook_and_close(beats(("Hello and welcome to this video about bees.", "title"), ("Bees are great.", "image"), ("Thanks for watching, see you next time!", "title")))
    assert h["hook_greeting"] and h["close_generic"] and h["close_short"]
    h = qa.hook_and_close(beats(("", "title"), ("Why do we dream? Nobody knows for sure.", "image"), ("Tonight, notice what your mind does when the lights go out and it is free again.", "quote")))
    assert h["hook_question"] and not h["hook_greeting"] and not h["close_generic"] and h["hook_words"] == 8   # the silent title card is skipped
    assert qa.hook_and_close(beats(("Hola a todos, bienvenidos.", "title")))["hook_greeting"]
    assert qa.hook_and_close(beats(("¿Qué es la entropía?", "title")))["hook_question"]


def test_scene_variety():
    v = qa.scene_variety(beats(*[("x", "bullets")] * 6))
    assert v["distinct"] == 1 and v["max_run"] == 6 and v["flag_low_variety"] and v["flag_run"]
    v = qa.scene_variety(beats(("a", "title"), ("b", "image"), ("c", "bullets"), ("d", "image"), ("e", "diagram"), ("f", "stat")))
    assert v["distinct"] == 5 and v["max_run"] == 1 and not v["flag_low_variety"] and not v["flag_run"]


def test_extract_numbers_skips_small_and_normalises():
    assert qa.extract_numbers("In 1453 there were 3 ships and 12,500 men, 40% fell; also 5%") == ["1453", "12500", "40", "5"]
    assert qa.extract_numbers("pi is 3.14") == ["3.14"]


def test_extract_entities_ignores_sentence_start():
    ents = qa.extract_entities("Today Mehmed II attacked. Then Constantine XI died in Constantinople on Monday.")
    assert "Mehmed II" in ents and "Constantinople" in ents and "Constantine XI" in ents
    assert "Today" not in ents and "Then" not in ents and "Monday" not in ents


def test_grounding_numbers_and_entities():
    notes = "Mehmed II besieged Constantinople in 1453 with about 80.000 troops."
    narr = "In 1453 Mehmed II took Constantinople. He had 80,000 soldiers and 62 cannons, said Orban of Hungary."
    g = qa.grounding(narr, notes, "")
    assert g["ungrounded_numbers"] == ["62"]            # 1453 and 80,000 (80.000 in the notes) are grounded
    assert "Orban" in g["ungrounded_entities"] and "Constantinople" not in g["ungrounded_entities"]
    assert 0 < g["ungrounded_share"] < 1
    g = qa.grounding("The Moon is 384400 km away.", "", "")
    assert g["no_notes"] and g["ungrounded_numbers"] == ["384400"]
    assert qa.grounding("Tienes 2024 razones", "", "Dame 2024 razones")["ungrounded_numbers"] == []   # the user's own number counts as given


def test_grounding_accent_insensitive():
    assert qa.grounding("Fue en México.", "mexico was", "")["ungrounded_entities"] == []


def test_repeated_phrases():
    r = qa.repeated_phrases("Russell had a lock up on the lap. Later Russell had a lock up again and lost places.")
    assert r and r[0]["count"] == 2 and "lock" in r[0]["phrase"]
    assert qa.repeated_phrases("one two three four five six seven eight nine ten") == []
    assert qa.repeated_phrases("it is the one and it is the one") == []   # only stop words


def test_silent_and_warning_kinds():
    assert qa.silent_beats(beats(("", "title"), ("hi", "image")))["silent"] == 1
    k = qa.warning_kinds(["length: the narration totals 100", "beat 2: scene replaced (bad props)", "some scenes list items their narration never mentions", "section 2: x"])
    assert k == {"length": 1, "scene_replaced": 1, "coverage": 1, "section": 1}


def test_language_detection():
    assert qa.detect_lang("El cielo es azul porque la luz se dispersa en las moléculas del aire.") == "es"
    assert qa.detect_lang("The sky is blue because the light is scattered by the molecules of the air.") == "en"
    assert qa.detect_lang("¿Por qué?") == "es"


def test_time_sensitivity():
    cue = re.compile(r"\b(latest|news)\b", re.I)
    assert qa.time_sensitivity("latest F1 race", False, "encyclopedia", cue)["flag_no_web"]
    assert not qa.time_sensitivity("latest F1 race", False, "web", cue)["flag_no_web"]
    assert qa.time_sensitivity("mortgage rates", True, "encyclopedia", cue)["flag_no_web"]
    assert not qa.time_sensitivity("how tides work", False, "encyclopedia", cue)["flag_no_web"]


def test_apply_rules_end_to_end():
    run = {"prompt": "explain tides", "language": "en", "time_sensitive": False, "notes": "Tides are caused by the Moon gravity.", "warnings": [],
           "research": {"mode": "encyclopedia", "n_fetched": 2}, "plan": {"sources": [], "beats": beats(("Hi there, welcome!", "title"), ("Tides come from the Moon.", "title"), ("Bye, thanks for watching.", "title"))}}
    r = qa.apply_rules(run, 300, 9)
    for f in ("too_short", "few_beats", "hook_greeting", "close_generic", "scene_run_3plus", "thin_notes", "no_sources_cited"):
        assert f in r["flags"], f
    run["language"] = "es"
    assert "wrong_language" in qa.apply_rules(run, 300, 9)["flags"]


def test_extract_notes_from_prompts():
    u1 = "Topic: x\n\nGrounding notes (may be empty):\n## A\nalpha text\n\n## B\nbeta text\n\nReturn the JSON plan now."
    u2 = "Research notes for this section (may be empty; use them for facts and numbers):\n## B\nbeta text\n\n## C\ngamma\n\nReturn the JSON for this section now."
    n = qa.extract_notes([u1, u2])
    assert n.count("beta text") == 1 and "gamma" in n and "alpha" in n
    assert qa.extract_notes(["Grounding notes (may be empty):\n(none)\n\nReturn the JSON plan now."]) == ""


def test_parse_json_and_judge_scoring():
    assert qa.parse_json('xx {"a": 1} yy') == {"a": 1}
    with pytest.raises(ValueError):
        qa.parse_json("nothing")
    scores = {k: {"score": 3, "reason": "r"} for k, _ in qa.DIMS}
    run = {"language": "en", "prompt": "p", "minutes": 1, "great": "g", "options": {}, "rules": {"length": {"expected_words": 100}}, "plan": {"beats": [], "sources": []}, "research": {}}
    seen = []

    def complete(system, user):
        seen.append(system)
        import json
        return json.dumps({"scores": scores, "defects": []}), {"cost_usd": 0.01, "tokens_in": 1, "tokens_out": 1}
    j = qa.judge_run(run, complete)
    assert j["mean"] == 3.0 and "SPANISH" not in seen[0]
    run["language"] = "es"
    qa.judge_run(run, complete)
    assert "SPANISH" in seen[1]


def test_spend_cap():
    s = qa.Spend(1.0)
    assert s.try_start(0.4) and s.try_start(0.4)
    assert not s.try_start(0.4)   # 3 in flight at 0.4 would exceed 1.0
    s.done()
    s.add(0.5)
    assert not s.try_start(0.4)
