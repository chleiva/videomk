"""Getting the best out of Polly's generative voices (docs/POLLY_LIVELY_DEFAULTS_2026-11-27.md): a lively default and second voice wherever an accent has one,
the resolver's preference, the cartoon cast (one accent per video: the viewer's), length fits from real beats, the guard that keeps a video inside its window
whatever the voice took, the lengthening step that adds content and not echoes, one register from scene to scene, one speech level, and the script's rhythm."""
import copy
import io
import json
import os
import sys
import wave

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))

from engine import align, audio, awsio, length, plan as plan_mod, presenter_policy as pp, register, speechcut, staged, timeline, voice_data, voices  # noqa: E402
from engine.handlers import beat_handler, timeline_handler  # noqa: E402

SR = audio.SR
PLANS = os.path.join(os.path.dirname(__file__), "fixtures", "plans")
# every language and region the product serves -> (default, the default of the other gender). None: the language has no voice of the other gender.
DEFAULTS = {
    ("en", None): ("Ruth", "Matthew"), ("en", "US"): ("Ruth", "Matthew"), ("en", "CA"): ("Ruth", "Matthew"), ("en", "GB"): ("Amy", "Brian"), ("en", "AU"): ("Olivia", "Russell"),
    ("en", "IN"): ("Kiara", "Arjun"), ("en", "IE"): ("Niamh", "Matthew"), ("en", "NZ"): ("Aria", "Matthew"), ("en", "SG"): ("Jasmine", "Matthew"), ("en", "ZA"): ("Ayanda", "Matthew"),
    ("es", "ES"): ("Sergio", "Lucia"), ("es", None): ("Lupe", "Carlos"), ("es", "MX"): ("Lupe", "Carlos"), ("es", "AR"): ("Lupe", "Carlos"), ("es", "US"): ("Lupe", "Carlos"),
    ("es", "GB"): ("Lupe", "Carlos"), ("es", "FR"): ("Lupe", "Carlos"), ("es", "PH"): ("Lupe", "Carlos"),
    ("fr", None): ("Ambre", "Florian"), ("fr", "FR"): ("Ambre", "Florian"), ("fr", "CH"): ("Ambre", "Florian"), ("fr", "CA"): ("Gabrielle", "Liam"), ("fr", "BE"): ("Ambre", "Florian"),
    ("de", "DE"): ("Vicki", "Lennart"), ("de", "AT"): ("Hannah", "Lennart"), ("de", "CH"): ("Sabrina", "Lennart"), ("it", "IT"): ("Beatrice", "Lorenzo"),
    ("pt", "BR"): ("Camila", "Leo"), ("pt", "PT"): ("Camila", "Leo"), ("nl", "NL"): ("Lisa", None), ("nl", "BE"): ("Lisa", None), ("pl", "PL"): ("Ola", None), ("fi", "FI"): ("Suvi", None),
    ("ko", "KR"): ("Seoyeon", "Hyunduk"),
}
# the accents Polly has no lively voice for: their default stays a steady voice of that accent
NO_LIVELY = {"es-ES", "es-MX", "fr-CA", "fr-BE", "nl-NL", "pl-PL", "en-ZA"}


def _locale(v):
    return voices.INFO[v]["locale"]


def _of(locale, gender=None):
    return [x["id"] for x in voice_data.VOICES if x["locale"] == locale and (gender is None or x["gender"] == gender)]


# ================================================================= 1. defaults
@pytest.mark.parametrize("lang,region", sorted(DEFAULTS, key=str))
def test_the_default_and_the_second_voice_are_lively_wherever_the_accent_has_a_lively_voice(lang, region):
    first, second = DEFAULTS[(lang, region)]
    assert voices.default_voice(lang, region) == first and voices.cast_voices(None, lang, region) == ({"narrator": first}, [])
    loc = _locale(first)
    if any(voices.lively(v) for v in _of(loc)):
        assert voices.lively(first), (first, "is steady although its accent has a lively voice")
    else:
        assert loc in NO_LIVELY and first in voices.STEADY
    other = "male" if voices.CATALOG[first][2] == "female" else "female"
    got = voices.second_voice(lang, region)
    if second is None:   # Dutch, Polish and Finnish have women's voices only
        assert not any(voices.CATALOG[n][2] == other for n in voices.names(lang)) and voices.language_of(got) == lang
        return
    assert got == second and voices.CATALOG[second][2] == other
    if any(voices.lively(v) for v in _of(loc, other)):          # the viewer's own accent has a lively voice of the other gender: that one
        assert _locale(second) == loc and voices.lively(second)
    elif _of(loc, other):                                        # only steady ones: still the viewer's accent, never another accent's lively voice
        assert _locale(second) == loc
    cast, notes = voices.cast_voices({"a": {}, "b": {}}, lang, region)   # a conversation with nothing asked: the two of them
    assert cast == {"a": first, "b": second} and notes == []


def test_the_accents_without_a_lively_voice_are_exactly_the_ones_recorded():
    locales = {v["locale"] for v in voice_data.VOICES}
    assert {loc for loc in locales if not any(voices.lively(v) for v in _of(loc))} == NO_LIVELY
    assert len(voices.STEADY) == 18 and sum(voices.lively(v["id"]) for v in voice_data.VOICES) == 37


def test_spain_keeps_a_castilian_voice_and_everyone_else_hears_lupe():
    d = voices.default_voice
    assert d("es", "ES") == d("es", "es") == "Sergio" and _locale("Sergio") == _locale("Lucia") == "es-ES"
    for region in (None, "", "MX", "AR", "CO", "CL", "PE", "US", "GB", "FR", "DE", "PH", "GQ", "ZZ"):       # the Americas, any other country, and no country at all
        assert d("es", region) == "Lupe", region
        assert voices.resolve({"gender": "male"}, "es", region) == ("Carlos", "")
    assert voices.resolve({"gender": "female"}, "es", "ES") == ("Lucia", "") and voices.resolve({"gender": "male"}, "es", "ES") == ("Sergio", "")
    for region in ("ES", "MX", None):                                                                         # a Mexican accent asked by name is Mexican, anywhere
        assert voices.resolve({"accent": "mexicana", "gender": "female"}, "es", region) == ("Mia", "")
        assert voices.resolve({"accent": "Mexican", "gender": "male"}, "es", region) == ("Andres", "")
    assert voices.resolve({"accent": "Castilian"}, "es", "MX")[0] in ("Sergio", "Lucia") and voices.resolve({"accent": "de España", "gender": "female"}, "es", "AR") == ("Lucia", "")


# ================================================================= 2. the resolver
def test_the_resolver_prefers_a_lively_voice_inside_the_accent_asked():
    r = voices.resolve
    assert r({"gender": "male"}, "fr", "FR") == ("Florian", "") and r({"accent": "French (France)", "gender": "female"}, "fr", "CA") == ("Ambre", "")   # not Rémi, not Léa
    assert r({"gender": "male"}, "de", "DE") == ("Lennart", "") and r({"accent": "Germany", "gender": "male"}, "de", "AT") == ("Lennart", "")           # not Daniel
    assert r({"accent": "Indian", "gender": "female"}, "en", "US") == ("Kiara", "") and r({"accent": "Indian", "gender": "male"}, "en", "GB") == ("Arjun", "")
    assert r({"accent": "Latin American", "gender": "male"}, "es", "ES") == ("Carlos", "") and r({"accent": "latina"}, "es", "ES") == ("Lupe", "")      # not Pedro
    assert r({"gender": "female"}, "it") == ("Beatrice", "") and r({"gender": "male", "pace": "slow"}, "fr", "FR")[0] == "Florian"                       # livelier matters more than pace
    v, note = r({"accent": "Colombian", "gender": "male"}, "es", "CO")
    assert v == "Carlos" and "no Colombian voice" in note
    # never another accent because it is livelier: the viewer's own accent, or the one asked, comes first
    assert r({"gender": "female"}, "fr", "CA") == ("Gabrielle", "") and r({"gender": "male"}, "fr", "CA") == ("Liam", "")
    assert r({"accent": "Canadian", "gender": "male"}, "fr", "FR") == ("Liam", "") and r({"accent": "Belgian"}, "fr", "FR") == ("Isabelle", "")
    assert r({"gender": "female"}, "nl", "NL") == ("Lisa", "") and r({}, "pl", "PL") == ("Ola", "") and r({"accent": "South African"}, "en", "US") == ("Ayanda", "")


def test_a_steady_voice_asked_for_by_name_is_given():
    for name, lang in (("Kajal", "en"), ("Lea", "fr"), ("Léa", None), ("Remi", "fr"), ("Bianca", "it"), ("Lucia", "es"), ("Mia", "es"), ("Pedro", "es"), ("Daniel", "de"), ("Celine", "fr")):
        want = voices.canonical(name) or {"Léa": "Lea"}[name]
        assert want in voices.STEADY
        assert voices.resolve({"name": want}, voices.language_of(want), None) == (want, "")
        assert voices.clean_cast({"narrator": want}, voices.language_of(want), "US") == {"narrator": want}
    assert voices.clean_cast({"narrator": "Brian"}, "en", "IN") == {"narrator": "Brian"}


def test_a_conversation_gets_different_voices_and_lively_ones_where_there_are():
    three = {"a": {"gender": "female"}, "b": {"gender": "male"}, "c": {"gender": "female"}}
    for lang in voices.READY:
        for region in [r for (lg, r) in DEFAULTS if lg == lang]:
            for n in (2, 3):
                cast, notes = voices.cast_voices({k: three[k] for k in list(three)[:n]}, lang, region)
                have = len(voices.names(lang))
                assert len(set(cast.values())) == min(n, have), (lang, region, cast)                         # nobody shares a voice while the language has another
                assert all(voices.language_of(v) == lang for v in cast.values())
                home = _locale(voices.default_voice(lang, region))
                for sid, v in cast.items():   # each speaker: a lively voice whenever the viewer's accent still has a free one of that gender
                    if any(voices.lively(x) for x in _of(home, three[sid]["gender"])) and sid in ("a", "b"):
                        assert voices.lively(v) and _locale(v) == home, (lang, region, sid, v)
    assert voices.cast_voices(three, "en", "US")[0] == {"a": "Ruth", "b": "Matthew", "c": "Danielle"}        # English: as it always was
    assert voices.cast_voices({"maya": {"gender": "female"}, "sam": {"gender": "male"}, "lee": {"gender": "male", "accent": "British"}}, "en", "US")[0] == {"maya": "Ruth", "sam": "Matthew", "lee": "Brian"}
    assert voices.cast_voices(three, "es", "MX")[0] == {"a": "Lupe", "b": "Carlos", "c": "Mia"}             # the second woman of a Latin American viewer is Mexican, not Castilian
    assert voices.cast_voices(three, "es", "ES")[0] == {"a": "Lucia", "b": "Sergio", "c": "Lupe"}
    assert voices.cast_voices(three, "fr", "FR")[0] == {"a": "Ambre", "b": "Florian", "c": "Lea"} and voices.cast_voices(three, "de", "DE")[0] == {"a": "Vicki", "b": "Lennart", "c": "Tina"}
    # two voices of a conversation are told apart by more than their names: a man and a woman of every default pair are far apart in pitch (measured medians, Hz)
    assert voices.cast_voices({"a": {"gender": "male"}, "b": {"gender": "male"}}, "de", "DE")[0] == {"a": "Lennart", "b": "Daniel"}


# ================================================================= 3. the cartoon cast
CAST_VOICES = {
    "en": {"ines": "Ruth", "david": "Matthew", "priya": "Kiara", "mateo": "Stephen", "fox": "Joanna", "owl": "Brian", "bear": "Stephen", "cat": "Olivia", "parrot": "Nate", "turtle": "Amy"},
    "es": {"ines": "Lupe", "david": "Carlos", "priya": "Lupe", "mateo": "Carlos", "fox": "Lupe", "owl": "Carlos", "bear": "Carlos", "cat": "Lupe", "parrot": "Carlos", "turtle": "Lupe"},
    "fr": {"ines": "Ambre", "david": "Florian", "priya": "Ambre", "mateo": "Florian", "fox": "Ambre", "owl": "Florian", "bear": "Florian", "cat": "Ambre", "parrot": "Florian", "turtle": "Ambre"},
    "de": {"ines": "Vicki", "david": "Lennart", "priya": "Tina", "mateo": "Lennart", "fox": "Vicki", "owl": "Lennart", "bear": "Lennart", "cat": "Vicki", "parrot": "Lennart", "turtle": "Tina"},
    "it": {"ines": "Beatrice", "david": "Lorenzo", "priya": "Beatrice", "mateo": "Lorenzo", "fox": "Beatrice", "owl": "Lorenzo", "bear": "Lorenzo", "cat": "Beatrice", "parrot": "Lorenzo", "turtle": "Beatrice"},
    "pt": {"ines": "Camila", "david": "Leo", "priya": "Camila", "mateo": "Leo", "fox": "Carolina", "owl": "Leo", "bear": "Leo", "cat": "Carolina", "parrot": "Leo", "turtle": "Camila"},
}


def test_every_character_has_a_lively_voice_of_its_own_gender_in_every_language():
    assert set(pp.CAST) == set(pp.ORDER) and len(pp.ORDER) == 10
    for lang, table in CAST_VOICES.items():
        assert {c: pp.voice_for(c, lang) for c in pp.ORDER} == table, lang
    for lang in voices.READY:
        for cid, c in pp.CAST.items():
            gender = voices.CATALOG[c["voices"]["en"][0]][2]
            v = pp.voice_for(cid, lang)
            assert voices.language_of(v) == lang
            if any(voices.CATALOG[n][2] == gender for n in voices.names(lang)):
                assert voices.CATALOG[v][2] == gender, (cid, lang, v)                                          # the owl is a man, the fox a woman, in every language that has both
            if any(voices.CATALOG[n][2] == gender and voices.lively(n) and _locale(n) == _locale(voices.default_voice(lang)) for n in voices.names(lang)):
                assert voices.lively(v), (cid, lang, v)                                                        # and never a steady voice where a lively one of that gender exists
    # English is the cast it always was, but for the doctor: Kajal (steady) is Kiara
    assert [pp.CAST[c]["voices"]["en"] for c in pp.ORDER] == [["Ruth", "Danielle"], ["Matthew", "Stephen"], ["Kiara", "Danielle"], ["Stephen", "Matthew"], ["Joanna", "Salli"],
                                                             ["Brian", "Matthew"], ["Stephen", "Matthew"], ["Olivia", "Salli"], ["Nate", "Matthew"], ["Amy", "Ruth"]]
    assert all(pp.voice_for(c, "en", None, r) == CAST_VOICES["en"][c] for c in pp.ORDER for r in ("US", "GB", "IN"))   # and the same for every viewer
    assert all(voices.lively(n) for c in pp.ORDER for n in pp.CAST[c]["voices"]["en"])


def test_the_characters_of_one_video_share_the_viewers_accent():
    def talk(lang, region, *cids):
        taken, out = [], {}
        for c in cids:
            out[c] = pp.voice_for(c, lang, taken, region)
            taken.append(out[c])
        return out

    # what QA saw on 2026-11-27: a Latin American conversation of the fox (Lucia, Castilian) and the bear (Andrés, Mexican), both steady
    for region in ("US", "MX", "AR", None, "GB"):
        assert talk("es", region, "fox", "bear") == {"fox": "Lupe", "bear": "Carlos"}
        assert {_locale(v) for v in talk("es", region, "fox", "bear").values()} == {"es-US"}
    assert talk("es", "ES", "fox", "bear") == {"fox": "Lucia", "bear": "Sergio"} and talk("es", "ES", "owl", "parrot") == {"owl": "Sergio", "parrot": "Carlos"}
    assert talk("es", "MX", "fox", "cat") == {"fox": "Lupe", "cat": "Mia"}             # Polly has one lively Latin American woman: the second woman is the Mexican one, not the Castilian
    assert talk("es", "MX", "owl", "bear", "parrot") == {"owl": "Carlos", "bear": "Pedro", "parrot": "Andres"}
    assert talk("fr", "CA", "fox", "bear") == {"fox": "Gabrielle", "bear": "Liam"} and talk("fr", "FR", "fox", "bear") == {"fox": "Ambre", "bear": "Florian"}
    assert talk("de", "DE", "fox", "cat", "owl", "bear") == {"fox": "Vicki", "cat": "Tina", "owl": "Lennart", "bear": "Daniel"}
    assert talk("de", "AT", "fox", "owl") == {"fox": "Hannah", "owl": "Lennart"} and talk("nl", "BE", "fox", "owl") == {"fox": "Lisa", "owl": "Laura"}
    for lang in voices.READY:   # two characters never share a voice while the language has two
        if len(voices.names(lang)) >= 2:
            assert len(set(talk(lang, None, "fox", "bear").values())) == 2 and len(set(talk(lang, None, "fox", "cat").values())) == 2, lang


def test_the_presenter_of_a_plan_speaks_with_the_viewers_accent(monkeypatch):
    monkeypatch.setenv("PRESENTERS", "1")
    pres = ("presenter", {"heading": "Hola", "points": []})

    def plan(region=None):
        beats = [{"id": f"b{i}", "narration": "Hola a todos, hoy vemos por qué dormimos cada noche.", "scene": {"type": t, "props": dict(p)}} for i, (t, p) in enumerate([pres, ("title", {"title": "x", "subtitle": ""}), pres])]
        return {"language": "es", "voices": {"narrator": "Lucia"}, "beats": beats, **({"region": region} if region else {})}

    pol = pp.Policy(True, "asked", character="bear", asked=True, language="es")
    for region, voice in (("US", "Carlos"), ("MX", "Carlos"), (None, "Carlos"), ("ES", "Sergio")):
        p = plan(region)
        pp.enforce(p, pol, sanitize=lambda props: props)
        assert p["voices"] == {"narrator": voice} and p["presenter"]["voices"] == {"narrator": voice}, region


# ================================================================= 4. length: fits from real beats
def _it():
    with open(os.path.join(PLANS, "it_blue_sky_beatrice_plan.json"), encoding="utf-8") as f:
        return json.load(f)


def test_every_default_and_second_voice_has_a_fit_of_its_own_where_it_changed():
    for v in ("Sergio", "Lupe", "Carlos", "Ambre", "Florian", "Kiara", "Arjun", "Beatrice", "Lorenzo", "Lennart"):
        assert v in length.RATES and length.rate_for(voices.language_of(v), v) == length.RATES[v], v
    for (lang, region), (first, _) in DEFAULTS.items():
        if lang in voices.READY and lang not in ("en", "es"):
            assert first in length.RATES or length._base_voice(voices.INFO[first])["id"] in length.RATES, first
    assert length.RATES["Lisa"] == (0.0515, 0.307, 0.19) and voices.cast_voices({"a": {}, "b": {}}, "nl", "NL")[0] == {"a": "Lisa", "b": "Laura"}   # Dutch default since 2026-11-28
    assert length.RATES["Ruth"] == (0.0547, 0.351, 0.16) and length.RATES["Amy"] == (0.0558, 0.309, 0.23) and length.RATES["Lucia"] == (0.0495, 0.378, 0.14)   # untouched
    # a steady French voice is still estimated from Léa (a steady voice), not from the lively default
    assert length._base_voice(voices.INFO["Gabrielle"])["id"] == "Lea" and length._base_voice(voices.INFO["Tina"])["id"] == "Vicki"
    assert length.estimate_speech("Bonjour à tous.", "fr", "Florian") < length.estimate_speech("Bonjour à tous.", "fr", "Ambre") < length.estimate_speech("Bonjour à tous.", "fr", "Lea")


def test_beatrices_fit_matches_her_real_beats_and_the_first_fit_did_not():
    fx = _it()
    texts = [b["narration"] for b in fx["beats"]]
    est = sum(length.estimate_speech(t, "it", "Beatrice") for t in texts)
    for take in fx["speech_s"]:                                             # three takes of the same four beats: 48.1, 47.2 and 47.6 s
        assert est == pytest.approx(sum(take), rel=0.04)
    first_fit = (0.0514, 0.305, 0.18)                                       # two lab passages: 17 percent short for the real video
    old = sum(len(t) * first_fit[0] + len(length._PUNCT.findall(t)) * first_fit[1] for t in texts)
    assert sum(fx["speech_s"][0]) / old > 1.15
    # the spread no fit removes: the same text, one beat, differs by up to 6 percent between takes
    worst = max(max(b) / min(b) for b in zip(*fx["speech_s"]))
    assert 1.02 < worst < 1.10
    assert length.WORDS_PER_S["it"] == 2.54 and length.WORDS_PER_S["fr"] == 3.41 and length.WORDS_PER_S["en"] == 2.63
    assert plan_mod.expected_words(0.75, 0, "en") == plan_mod.expected_words(0.75, 0, "es") == 89                                    # English and Spanish budgets as they were


# ================================================================= 5. the guard: never longer than asked plus the window
def _say(text, f0=180.0, word_s=0.26, gap=0.05, comma=0.22, stop=0.5):
    """Speech-shaped audio for a text: a voiced burst per word, a breath after a comma, a real pause after a sentence. -> samples at SR."""
    out = []
    for w in text.split():
        n = int((word_s + 0.012 * len(w)) * SR)
        t = np.arange(n, dtype=np.float32) / SR
        env = np.sin(np.pi * np.clip(t / (n / SR), 0, 1)) ** 0.5
        out.append(((np.sin(2 * np.pi * f0 * t) + 0.5 * np.sin(2 * np.pi * 2 * f0 * t) + 0.3 * np.sin(2 * np.pi * 3 * f0 * t)) * env * 0.2).astype(np.float32))
        out.append(np.zeros(int((stop if w[-1] in ".!?" else comma if w[-1] in ",;:" else gap) * SR), np.float32))
    return audio.trim_silence(np.concatenate(out), SR)


def _long_plan():
    fx = _it()
    plan = {"language": "it", "voices": {"narrator": "Beatrice"}, "tts": fx["tts"], "target_seconds": 45, "beats": [dict(b, scene={"type": "title", "props": {"title": "x"}}) for b in fx["beats"]]}
    plan["length_added"] = [{"beat": b["id"], "index": i, "sentences": [s for s in fx["added"] if s in b["narration"]]} for i, b in enumerate(plan["beats"]) if any(s in b["narration"] for s in fx["added"])]
    return plan, fx


def test_a_sentence_is_cut_out_of_the_audio_at_its_own_pauses():
    text = "Resta il rosso, che passa meglio. Così il cielo si tinge di rosso. Cambia la strada, non la luce."
    a = _say(text)
    cuts = speechcut.sentence_cuts(a, SR, text)
    assert len(cuts) == 3 and all(c is not None for c in cuts)
    for j, keep in ((0, "Così il cielo si tinge di rosso. Cambia la strada, non la luce."), (1, "Resta il rosso, che passa meglio. Cambia la strada, non la luce."), (2, "Resta il rosso, che passa meglio. Così il cielo si tinge di rosso.")):
        b = speechcut.remove(a, SR, cuts[j])
        assert b.size / SR == pytest.approx(_say(keep).size / SR, abs=0.25)                    # what remains is as long as the remaining sentences said alone
        words, conf = align.align_words(b, SR, keep)
        assert conf >= 0.9 and len(words) == len(keep.split())                                   # and its words are still found, one by one
        k0, k1 = int(cuts[j][0] * SR), int(cuts[j][1] * SR)
        edge = np.concatenate([a[max(0, k0 - 240): k0 + 240] if 0 < k0 < a.size else np.zeros(1, np.float32), a[k1 - 240: k1 + 240] if 0 < k1 < a.size else np.zeros(1, np.float32)])
        assert float(np.max(np.abs(edge))) < 0.02                                                # every cut lies in silence
    assert speechcut.sentence_cuts(_say("Una sola frase qui."), SR, "Una sola frase qui.") == [None]
    glued = _say(text, stop=0.05)                                                                # no pause between the sentences: nothing can be cut cleanly, so nothing is
    assert speechcut.sentence_cuts(glued, SR, text) == [None, None, None]


def test_a_video_whose_voice_took_too_long_loses_the_added_sentences_first_and_fits():
    """The first Italian video with Beatrice: 48.1 s of speech for 45 s asked, 51.4 s on screen. The guard works on any voice: it only looks at the audio."""
    plan, fx = _long_plan()
    factor = sum(fx["speech_s"][0]) / sum(_say(b["narration"]).size / SR for b in plan["beats"])   # the mock voice, as slow as Beatrice was
    audio_of = {i: _say(b["narration"], word_s=0.26 * factor, gap=0.05 * factor, comma=0.22 * factor, stop=0.5 * factor) for i, b in enumerate(plan["beats"])}
    durs = [audio_of[i].size / SR for i in range(4)]
    total, target = timeline.shortest(plan, durs, 45)
    assert target == 45 and total == pytest.approx(51.4, abs=0.6) and length.overrun(total, target) > 3.5        # what QA measured: no silence is short enough
    tl = timeline.build_timeline(copy.deepcopy(plan), [{"duration": d} for d in durs], video_id="v", fit_seconds=45, min_seconds=45)
    assert tl["duration"] == pytest.approx(total, abs=0.01) and tl["pace"] == {"lead": length.LEAD_FLOOR, "tail": length.TAIL_FLOOR}   # `shortest` is the timeline's own arithmetic
    before = [b["narration"] for b in plan["beats"]]
    cuts = speechcut.fit(plan, audio_of, SR, lambda ch: timeline.shortest(plan, [ch.get(i, d) for i, d in enumerate(durs)], 45)[0], target)
    assert cuts and all(c["added"] for c in cuts) and {c["text"] for c in cuts} <= set(fx["added"])              # only sentences the lengthening step had added
    new = [audio_of[i].size / SR for i in range(4)]
    tl = timeline.build_timeline(plan, [{"duration": d} for d in new], video_id="v", fit_seconds=45, min_seconds=45)
    assert 45 <= tl["duration"] <= 45 * (1 + length.OVER) + 0.01                                                  # inside the window the product promises
    assert plan["beats"][0]["narration"] == before[0] and plan["beats"][-1]["narration"].endswith("Cambia la strada, non la luce.")   # the opening and the last line are never cut
    for c in cuts:
        assert c["text"] not in plan["beats"][c["beat"]]["narration"]
    assert all(align.align_words(audio_of[i], SR, b["narration"])[1] >= 0.9 for i, b in enumerate(plan["beats"]))
    # nothing was added and it is still too long: sentences go by the rules of the script cut (never the first line, never the last, a beat keeps its words)
    plan2, _ = _long_plan()
    plan2.pop("length_added")
    audio2 = {i: _say(b["narration"], word_s=0.26 * factor * 1.1, gap=0.05 * factor, comma=0.22 * factor, stop=0.5 * factor) for i, b in enumerate(plan2["beats"])}
    d2 = [audio2[i].size / SR for i in range(4)]
    cuts2 = speechcut.fit(plan2, audio2, SR, lambda ch: timeline.shortest(plan2, [ch.get(i, d) for i, d in enumerate(d2)], 45)[0], 45)
    assert cuts2 and not any(c["added"] for c in cuts2)
    assert length.overrun(timeline.shortest(plan2, [audio2[i].size / SR for i in range(4)], 45)[0], 45) == 0
    assert plan2["beats"][0]["narration"].startswith("Perché il cielo") and plan2["beats"][-1]["narration"].endswith("non la luce.")
    assert all(len(b["narration"].split()) >= 6 for b in plan2["beats"])
    # a video that fits is not touched, whatever its voice
    plan3, _ = _long_plan()
    audio3 = {i: _say(b["narration"], word_s=0.26 * factor * 0.85, gap=0.05 * factor, comma=0.22 * factor, stop=0.5 * factor) for i, b in enumerate(plan3["beats"])}
    d3 = [audio3[i].size / SR for i in range(4)]
    assert length.overrun(timeline.shortest(plan3, d3, 45)[0], 45) == 0 and speechcut.fit(plan3, audio3, SR, lambda ch: timeline.shortest(plan3, d3, 45)[0], 45) == []
    assert length.pick_cut([{"beat": 1, "sentence": 2, "seconds": 2.0, "added": False}, {"beat": 2, "sentence": 1, "seconds": 2.2, "added": True}], 50.0, 45)["added"] is True
    assert length.pick_cut([], 50.0, 45) is None and length.pick_cut([{"beat": 1, "sentence": 2, "seconds": 2.0, "added": True}], 46.0, 45) is None
    assert length.overrun(47.25, 45) == 0 and length.overrun(47.3, 45) == pytest.approx(0.05) and length.overrun(60, 0) == 0


def _wav(samples):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def test_the_timeline_step_stores_the_shorter_audio_under_the_hash_of_the_shorter_text(monkeypatch):
    plan, fx = _long_plan()
    store, meta = {}, {}
    monkeypatch.setattr(awsio, "get_bytes", lambda k: store[k])
    monkeypatch.setattr(awsio, "get_json", lambda k: json.loads(store[k]))
    monkeypatch.setattr(awsio, "put_json", lambda k, o: store.__setitem__(k, json.dumps(o).encode()))
    monkeypatch.setattr(awsio, "put_bytes_meta", lambda k, data, ct, md: (store.__setitem__(k, data), meta.__setitem__(k, md)))
    pfx = awsio.prefix("vid1")
    factor = sum(fx["speech_s"][0]) / sum(_say(b["narration"]).size / SR for b in plan["beats"])
    for b in plan["beats"]:
        a = _say(b["narration"], word_s=0.26 * factor, gap=0.05 * factor, comma=0.22 * factor, stop=0.5 * factor)
        h = plan_mod.tts_hash(plan, b)
        store[f"{pfx}audio/{h}.wav"] = _wav(a)
        b["media"] = {"tts_hash": h, "audio_key": f"{pfx}audio/{h}.wav", "duration": round(a.size / SR, 3), "voice": "Beatrice"}
    old_keys = [b["media"]["audio_key"] for b in plan["beats"]]
    cuts = timeline_handler.fit_speech(plan, "vid1", 45.0)
    assert cuts and plan["length_cut"] and all(c["added"] for c in plan["length_cut"]) and {c["sentence"] for c in plan["length_cut"]} <= set(fx["added"])
    changed = [i for i, b in enumerate(plan["beats"]) if b["media"]["audio_key"] != old_keys[i]]
    assert changed == sorted({c["beat"] for c in cuts})
    for i in changed:
        b = plan["beats"][i]
        h = plan_mod.tts_hash(plan, b)
        assert b["media"]["tts_hash"] == h and b["media"]["audio_key"] == f"{pfx}audio/{h}.wav"                 # where an edit of this text would look: never said again
        with wave.open(io.BytesIO(store[b["media"]["audio_key"]]), "rb") as w:
            assert w.getnframes() / SR == pytest.approx(b["media"]["duration"], abs=0.001) and float(meta[b["media"]["audio_key"]]["duration"]) == b["media"]["duration"]
        words = json.loads(store[b["media"]["words_key"]])["words"]
        assert [w[0] for w in words] == b["narration"].split()
        assert old_keys[i] in store                                                                               # the first audio is kept (content-addressed, nothing is overwritten)
    infos = timeline.beat_info_from_plan(plan)
    tl = timeline.build_timeline(plan, infos, video_id="vid1", fit_seconds=45, min_seconds=45)
    assert 45 <= tl["duration"] <= 45 * 1.05 + 0.01
    again = copy.deepcopy(plan)
    n = len(store)
    assert timeline_handler.fit_speech(again, "vid1", 45.0) == [] and len(store) == n                             # it fits now: nothing is read or written


# ================================================================= 6. the lengthening step adds content, not echoes
def test_the_lengthening_prompt_asks_for_new_content_and_is_shown_the_notes():
    s = length.EXTEND_SYSTEM
    assert "something the script has NOT said yet" in s and "NEVER say again" in s and "returned unchanged" in s and "a slightly shorter video is better than a repeated sentence" in s
    assert "grounding notes" in s and "existing sentences word for word" in s
    fx = _it()
    plan = {"language": "it", "voices": {"narrator": "Beatrice"}, "beats": [{"id": b["id"], "narration": " ".join(x for x in length.sentences(b["narration"]) if x not in fx["added"])} for b in fx["beats"]]}
    seen = []

    def writer(answer):
        def ask(system, user):
            seen.append((system, user))
            return json.dumps({"beats": answer})
        return ask

    # the answer of 2026-11-27 (QA): three sentences that say the one before again
    echo = [{"beat": i + 1, "narration": b["narration"]} for i, b in enumerate(fx["beats"])]
    p1 = copy.deepcopy(plan)
    rep = length.extend_script(p1, 60, writer(echo), notes="## Diffusione di Rayleigh\nLa luce blu ha una lunghezza d'onda di circa 450 nanometri.")
    assert "Italian" in seen[-1][0] and "Grounding notes (facts you may add from" in seen[-1][1] and "450 nanometri" in seen[-1][1]
    assert rep["refused_restatements"] == 1 and "Cambia la strada, non la luce." not in p1["beats"][3]["narration"]   # an echo in the same words is refused outright
    assert length.restates("Cambia la strada, non la luce.", length.sentences(plan["beats"][3]["narration"])) is True
    # an echo in other words cannot be told by its words; it is remembered as added, so it is the first to go if the video comes out long (the guard above)
    added = [s for row in p1["length_added"] for s in row["sentences"]]
    assert added == ["Il blu ci arriva da ogni parte.", "Si perde prima di raggiungerci."]
    assert length.added_sentences(p1, 1, p1["beats"][1]) == ["Il blu ci arriva da ogni parte."] and length.added_sentences(p1, 0, p1["beats"][0]) == []
    # what the same step wrote with the new prompt (real model, 2026-11-27): an example, a contrast, a comparison, a consequence. None is an echo, all are taken.
    new = [{"beat": i + 1, "narration": plan["beats"][i]["narration"] + " " + row["sentences"][0]} for i, row in enumerate(fx["written_with_new_prompt"])]
    p2 = copy.deepcopy(plan)
    rep2 = length.extend_script(p2, 60, writer(new))
    assert rep2["extended"] == 4 and "refused_restatements" not in rep2 and "There are no grounding notes" in seen[-1][1]
    for row, b in zip(fx["written_with_new_prompt"], p2["beats"]):
        assert b["narration"].endswith(row["sentences"][0]) and not length.restates(row["sentences"][0], length.sentences(b["narration"])[:-1])
    assert not length.restates("Sì.", ["Sì, certo."]) and not length.restates("Lo stesso accade all'alba.", [])


def test_spanish_scripts_for_the_fast_men_are_lengthened_and_the_others_are_as_before():
    texts = ["Cada mañana salen unos trenes de la estación central de la ciudad.", "Algunos cruzan todo el país, mientras que otros solo llegan al pueblo vecino.",
             "Cada uno sigue un horario planificado hace meses por la compañía.", "Así viajan millones de personas cada día sin pensarlo."]
    asked = []

    def ask(system, user):
        asked.append(user)
        return json.dumps({"beats": []})

    for voice, n in (("Sergio", 1), ("Carlos", 2), ("Lupe", 2), ("Lucia", 2)):
        plan = {"language": "es", "voices": {"narrator": voice}, "beats": [{"id": f"b{i}", "narration": t} for i, t in enumerate(texts)]}
        length.extend_script(plan, 45, ask)
        assert len(asked) == n, voice                                                         # Sergio and Carlos say 3.0 to 3.1 words a second: their scripts are lengthened; Lupe's and Lucia's never were
    english = {"language": "en", "voices": {"narrator": "Kiara"}, "beats": [{"id": "b0", "narration": "A short line for a long video."}, {"id": "b1", "narration": "And another short line to end it."}]}
    assert length.extend_script(english, 45, ask)["asked"] == 0 and len(asked) == 2


# ================================================================= 7. one register from scene to scene
def _voice(f0, seconds=3.0):
    return _say(" ".join(["parola"] * int(seconds / 0.38)) + ".", f0=f0)


def test_the_median_pitch_of_speech_is_measured():
    for f0 in (95.0, 180.0, 224.0, 271.0):
        assert register.median_pitch(_voice(f0), SR) == pytest.approx(f0, rel=0.02)
    assert register.median_pitch(np.zeros(SR, np.float32), SR) is None and register.median_pitch(np.zeros(100, np.float32), SR) is None
    assert register.semitones(271, 180) == pytest.approx(7.1, abs=0.1)


def test_the_register_is_the_lower_half_and_a_beat_far_from_it_is_off():
    fx = _it()
    qa, calm, both = fx["f0_hz"]
    assert register.reference(qa) == pytest.approx(176.6, abs=0.5) and register.reference(both) == pytest.approx(175, abs=1)   # two of four beats went up: still the normal voice
    assert register.reference([200.0]) is None and register.reference([]) is None
    text = fx["beats"][3]["narration"]
    assert register.off(qa[3], register.reference(qa), text) > 5 and register.off(qa[1], register.reference(qa), text) == 0     # 271 Hz against 177: 7.4 semitones, 5.4 past the band
    assert all(register.off(x, register.reference(calm), text) == 0 for x in calm)                                              # the take that was fine: nothing is said again
    assert register.band("Perché il cielo è blu? Davvero!") == register.QUESTION_BAND_ST and register.band(text) == register.BAND_ST
    assert register.off(None, 180.0) == 0 and register.off(200.0, None) == 0
    assert register.choose([{"hz": 271.0}, {"hz": None}, {"hz": 193.5}, {"hz": 215.0}], 176.5) == 2


def test_only_a_lively_polly_voice_is_said_again(monkeypatch):
    fx = _it()
    plan = {"language": "it", "voices": {"narrator": "Beatrice"}, "tts": fx["tts"], "beats": [dict(b) for b in fx["beats"]]}
    b = plan["beats"][0]
    assert register.applies(plan, b) and len(register.peers(plan, b)) == 3
    assert not register.applies({**plan, "voices": {"narrator": "Bianca"}}, b)                              # a steady voice says the same thing the same way every time
    assert not register.applies({**plan, "tts": {**fx["tts"], "engine": "neural"}}, b) and not register.applies({**plan, "tts": {"provider": "mock"}}, b)
    assert not register.applies(plan, {**b, "silent": True, "narration": ""})
    monkeypatch.setenv("REGISTER_RETAKES", "0")
    assert not register.applies(plan, b) and register.retakes() == 0
    monkeypatch.setenv("REGISTER_RETAKES", "9")
    assert register.retakes() == 4
    two = {**plan, "voices": {"fox": "Beatrice", "bear": "Lorenzo"}, "beats": [dict(x, speaker=s) for x, s in zip(fx["beats"], ("fox", "bear", "fox", "bear"))]}
    assert [x["id"] for x in register.peers(two, two["beats"][0])] == [two["beats"][2]["id"]]             # a speaker is compared with their own beats only


def test_a_beat_in_another_register_is_said_again_and_the_nearest_take_is_kept(monkeypatch):
    fx = _it()
    plan = {"language": "it", "voices": {"narrator": "Beatrice"}, "tts": fx["tts"], "beats": [dict(b) for b in fx["beats"]]}
    store = {}
    monkeypatch.setattr(awsio, "put_json", lambda k, o: store.__setitem__(k, o))

    def get(k):
        if k not in store:
            raise KeyError(k)
        return store[k]

    monkeypatch.setattr(awsio, "get_json", get)
    pfx = awsio.prefix("v")
    qa = fx["f0_hz"][0]                                                                       # 200, 175, 179, 271 Hz: the QA video
    for b, hz in zip(plan["beats"], qa):                                                      # the other beats' functions have written their first takes
        store[f"{pfx}audio/{plan_mod.tts_hash(plan, b)}.f0.json"] = {"hz": hz}
    asked = []

    def takes(*hz):
        it = iter(hz)

        def again():
            f = next(it)
            asked.append(f)
            return _voice(f)
        return again

    last = plan["beats"][3]
    kept, rec = beat_handler.settle_register(plan, last, "v", _voice(271.0), takes(253.0, 190.0), wait_s=0.0)
    assert asked == [253.0, 190.0] and rec["takes"] == 3 and rec["first_hz"] == pytest.approx(271, rel=0.02) and rec["hz"] == pytest.approx(190, rel=0.02) and rec["ref"] == pytest.approx(177, abs=2)
    assert register.median_pitch(kept, SR) == pytest.approx(190, rel=0.02)
    assert store[f"{pfx}audio/{plan_mod.tts_hash(plan, last)}.f0.json"]["hz"] == pytest.approx(271, rel=0.02)   # the record is the FIRST take: every beat judges against first takes
    asked.clear()
    kept, rec = beat_handler.settle_register(plan, last, "v", _voice(271.0), takes(180.0, 100.0), wait_s=0.0)
    assert asked == [180.0] and rec["takes"] == 2                                                            # inside the band: no third take
    asked.clear()
    kept, rec = beat_handler.settle_register(plan, last, "v", _voice(271.0), takes(262.0, 240.0), wait_s=0.0)
    assert asked == [262.0, 240.0] and rec["hz"] == pytest.approx(240, rel=0.02)                             # never in the band: the nearest of the three, and no fourth take
    asked.clear()
    kept, rec = beat_handler.settle_register(plan, plan["beats"][1], "v", _voice(175.0), takes(), wait_s=0.0)
    assert asked == [] and rec == {"hz": pytest.approx(175, rel=0.02), "ref": pytest.approx(177, abs=2), "takes": 1}   # a beat in the register is left alone: nothing is paid
    # nobody to compare with (the others have not reported, or there are none): the first take stands
    store.clear()
    kept, rec = beat_handler.settle_register(plan, last, "v", _voice(271.0), takes(), wait_s=0.0, sleep=lambda s: None)
    assert asked == [] and rec["takes"] == 1 and "ref" not in rec
    solo = {**plan, "beats": [dict(fx["beats"][0])]}
    assert beat_handler.settle_register(solo, solo["beats"][0], "v", _voice(271.0), takes(), wait_s=0.0)[1] == {"hz": pytest.approx(271, rel=0.02), "takes": 1}


def test_measured_on_the_qa_plans_the_step_brings_the_beats_together():
    """The three takes of the Italian video's four beats (fixture): whichever take comes first, saying an outlier again brings the spread under the aim when a
    calmer take exists; it never makes it worse."""
    fx = _it()
    takes = list(zip(*fx["f0_hz"]))                                # per beat: the pitch of its three takes
    spread = lambda xs: 12 * np.log2(max(xs) / min(xs))            # noqa: E731
    for first_take in range(3):
        first = [t[first_take] for t in takes]
        ref = register.reference(first)
        final = []
        for t in takes:
            order = [t[first_take]] + [x for k, x in enumerate(t) if k != first_take]
            got = [{"hz": order[0]}]
            for hz in order[1:1 + register.retakes()]:
                if register.off(got[register.choose(got, ref)]["hz"], ref) <= 0:
                    break
                got.append({"hz": hz})
            final.append(got[register.choose(got, ref)]["hz"])
        assert spread(final) <= spread(first) + 1e-9 and spread(final) < 2.5, (first, final)
    assert spread([t[0] for t in takes]) > 7 and spread([t[2] for t in takes]) > 7 and spread([t[1] for t in takes]) < 1.1   # before: 7.6, 1.0 and 7.5 semitones


# ================================================================= 8. one speech level under the music
def test_every_beat_reaches_the_mix_at_one_speech_level():
    a = _voice(180.0)
    base = audio.speech_level_db(a, SR)
    for db in (-3.0, -1.2, 0.0, 2.5):                                                          # Sergio, Beatrice, Ruth, Kiara against Ruth's level
        x = (a * 10 ** ((audio.SPEECH_LEVEL_DB - base + db) / 20)).astype(np.float32)
        assert audio.speech_level_db(x, SR) == pytest.approx(audio.SPEECH_LEVEL_DB + db, abs=0.05)
        assert audio.speech_level_db(audio.level_speech(x, SR), SR) == pytest.approx(audio.SPEECH_LEVEL_DB, abs=0.1)
    ruth = (a * 10 ** ((audio.SPEECH_LEVEL_DB - base) / 20)).astype(np.float32)
    assert np.allclose(audio.level_speech(ruth, SR), ruth, atol=1e-3)                          # a voice already at the level is not changed
    slow = np.concatenate([ruth, np.zeros(SR * 3, np.float32), ruth])
    assert audio.speech_level_db(slow, SR) == pytest.approx(audio.SPEECH_LEVEL_DB, abs=0.1)    # pauses do not count
    far = (ruth * 10 ** (-20 / 20)).astype(np.float32)
    assert audio.speech_level_db(audio.level_speech(far, SR), SR) == pytest.approx(audio.SPEECH_LEVEL_DB - 20 + audio.MAX_LEVEL_GAIN_DB, abs=0.1)   # at most 6 dB either way
    spiky = ruth.copy()
    spiky[1000] = 0.9
    assert float(np.max(np.abs(audio.level_speech((spiky * 0.6).astype(np.float32), SR)))) <= 0.971                                              # and never into clipping
    silence = np.zeros(SR, np.float32)
    assert audio.speech_level_db(silence, SR) is None and audio.level_speech(silence, SR) is silence


# ================================================================= 9. the script is written for a voice
def test_the_script_writer_is_asked_for_spoken_rhythm_in_every_language(monkeypatch):
    monkeypatch.delenv("SPOKEN_RHYTHM", raising=False)
    rule = plan_mod.SPOKEN_RHYTHM_RULE
    for must in ("Vary the length of the sentences", "Ask a real question", "answer it at once", "never one in every beat", "their natural equivalents in the video's language",
                 "contractions where it has them", "Write numbers the way they are said", "at most one exclamation mark in the whole video", "no talking down", "explainer for adults unless the brief says otherwise"):
        assert must in rule, must
    assert len(rule) < 1300                                                                    # modest: a paragraph, not a style guide
    for lang in voices.READY:
        p = plan_mod.system_prompt(lang, "US")
        assert rule in p and p.index("written for the ear") < p.index("- Spoken rhythm.") < p.index("- Vary the visuals"), lang
    assert rule in staged.plan_mod.system_prompt("fr") + staged.SECTION_ADDENDUM              # long videos: every section is written with it
    monkeypatch.setenv("SPOKEN_RHYTHM", "0")
    assert "Spoken rhythm" not in plan_mod.system_prompt("en") and plan_mod.spoken_rhythm_rule() == ""
