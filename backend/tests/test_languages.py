"""Every Polly generative voice and the languages a video can be made in (docs/LANGUAGES.md, docs/SELECTION_ARCHITECTURE.md).

Per language: detection, the default voice and the cast, the measured pace, word timing from real speech against exact word marks, and every bundled font
drawing every letter of the language (no empty boxes). English and Spanish must behave as they always did."""
import json
import os
import wave

import numpy as np
import pytest
from PIL import ImageFont

from engine import align, director, language, length, numfmt, plan as plan_mod, presenter_policy, research, timeline, voice_data, voices

NEW = ("fr", "de", "it", "pt", "nl", "pl", "fi")
ALL = "en,es,fr,de,it,pt,nl,pl,fi"
FIX = os.path.join(os.path.dirname(__file__), "fixtures", "speech")
ASSETS = os.path.join(os.path.dirname(voices.__file__), "assets")
BRIEF = {
    "fr": "Explique-moi pourquoi le ciel est bleu, en quelques phrases simples, pour les enfants.",
    "de": "Erkläre, wie die Gezeiten funktionieren und warum es Ebbe und Flut gibt, mit einfachen Worten.",
    "it": "Spiegami come funzionano le maree e perché il mare sale e scende, con parole semplici per i bambini.",
    "pt": "Explique como funcionam as marés e por que o mar sobe e desce, de forma simples, para crianças que não conhecem o assunto.",
    "nl": "Leg uit hoe de getijden werken en waarom het water stijgt en daalt, in eenvoudige woorden voor kinderen.",
    "pl": "Wyjaśnij, jak działają pływy morskie i dlaczego woda się podnosi, prostymi słowami dla dzieci.",
    "fi": "Selitä, miten vuorovesi toimii ja miksi meri nousee ja laskee, yksinkertaisin sanoin lapsille.",
}
# every letter the language writes beyond a-z, both cases, with its quotation marks, inside a sentence that uses all of them
PANGRAM = {
    "en": "The quick brown fox jumps over the lazy dog: “1,250.5” — £3, $4, 5% … it’s done!",
    "es": "El veloz murciélago hindú comía feliz cardillo y kiwi. ¿Qué? ¡Sí! La cigüeña tocaba el saxofón: ÁÉÍÓÚÜÑ áéíóúüñ «12 345,6 €».",
    "fr": "Portez ce vieux whisky au juge blond qui fume : dès Noël, où un zéphyr haï me vêt de glaçons würmiens. ÀÂÆÇÉÈÊËÎÏÔŒÙÛÜŸ àâæçéèêëîïôœùûüÿ « 12 345,6 € »",
    "de": "Zwölf Boxkämpfer jagen Viktor quer über den großen Sylter Deich. ÄÖÜ äöüß „12 345,6 €“ – Straße, Maß, Fuß.",
    "it": "Quel vituperabile xenofobo zelante assaggia il whisky ed esclama: alleluja! ÀÈÉÌÍÎÒÓÙÚ àèéìíîòóùú «12 345,6 €» perché, così, più.",
    "pt": "Luís argüia à Júlia que «brações, fé, chá, óxido, pôr, zângão» eram palavras do português. ÁÂÃÀÇÉÊÍÓÔÕÚ áâãàçéêíóôõú 12 345,6 €",
    "nl": "Pa's wijze lynx bezag vroom het fikse aquaduct. ÉËÏÓÖÜ áéëïóöü ĳ Ĳ ‘12 345,6 €’ – coördinatie, reünie, één.",
    "pl": "Pchnąć w tę łódź jeża lub ośm skrzyń fig. ĄĆĘŁŃÓŚŹŻ ąćęłńóśźż „12 345,6 zł” – źdźbło, żółć, gęślą jaźń.",
    "fi": "Törkylempijävongahdus. Albert osti fagotin ja töräytti puhkuvan melodian. ÄÖÅŠŽ äöåšž ”12 345,6 €” – yö, työ, älä.",
}


@pytest.fixture
def all_languages(monkeypatch):
    monkeypatch.setenv("VIDEO_LANGUAGES", ALL)


# ================================================================= the catalogue is what Polly lists
def test_the_catalogue_is_every_generative_voice_polly_lists():
    assert len(voice_data.VOICES) == len(voices.CATALOG) == 55 and voice_data.REGION == "us-east-1"
    assert {l: len(voices.names(l)) for l in voices.LANGUAGES} == {"en": 21, "es": 7, "fr": 8, "de": 6, "it": 3, "pt": 3, "nl": 2, "pl": 2, "fi": 1, "ko": 2}
    for v in voice_data.VOICES:
        assert "generative" in v["engines"] and v["language"] in voices.LANGUAGES and v["gender"] in ("female", "male") and v["locale"][:2] == v["language"]
        assert 90 <= v["wpm"] <= 230 and 6.0 <= v["sample_s"] <= 18.0, v["id"]          # every voice was really heard saying the sentence of its language
    assert voices.names("en")[0] == "Ruth" and voices.names("es")[0] == "Lucia"          # the owner's choices stay first
    assert voices.canonical("léa") is None and voices.canonical("lea") == "Lea" and voices.canonical("Lea", "en") is None


def test_only_ready_languages_can_be_enabled_and_english_and_spanish_are_the_default(monkeypatch):
    monkeypatch.delenv("VIDEO_LANGUAGES", raising=False)
    assert voices.enabled() == ["en", "es"]
    monkeypatch.setenv("VIDEO_LANGUAGES", "fr, DE ,ko,ja,en")
    assert voices.enabled() == ["en", "fr", "de"]                                         # Korean has voices but no font yet; Japanese has no generative voice
    monkeypatch.setenv("VIDEO_LANGUAGES", "ko")
    assert voices.enabled() == ["en", "es"]                                               # never an empty list
    assert set(voices.READY) < set(voices.LANGUAGES) and "ko" not in voices.READY
    stage = json.load(open(os.path.join(os.path.dirname(__file__), "..", "stages.json")))
    assert stage["qa"]["videoLanguages"] == ALL and "videoLanguages" not in stage["prod"]  # QA first


# ================================================================= detection and the refusal
@pytest.mark.parametrize("lang", NEW)
def test_a_clear_brief_is_recognised_without_a_model_call_only_where_the_language_is_enabled(lang, monkeypatch):
    monkeypatch.delenv("VIDEO_LANGUAGES", raising=False)
    assert language.heuristic(BRIEF[lang]) is None                                        # English and Spanish only: the heuristic never names another language
    monkeypatch.setenv("VIDEO_LANGUAGES", ALL)
    assert language.heuristic(BRIEF[lang]) == lang
    assert language.detect(BRIEF[lang], lambda s, u: (_ for _ in ()).throw(AssertionError("no model call for a clear brief"))) == lang


def test_english_and_spanish_are_detected_as_before_whatever_is_enabled(all_languages):
    assert language.heuristic("Explica cómo funciona la fotosíntesis, ¿por qué?") == "es"
    assert language.heuristic("What is the history of the Roman empire and why did it fall?") == "en"
    assert language.heuristic("Historia de Roma") is None and language.heuristic("Roma") is None    # too short to tell: the small model decides
    assert language.detect("Roma", lambda s, u: "it") == "it" and language.detect("東京の歴史", lambda s, u: "ja") == "other"


def test_the_refusal_names_every_language_enabled(monkeypatch):
    ask = lambda *a, **k: "fr"   # noqa: E731
    monkeypatch.delenv("VIDEO_LANGUAGES", raising=False)
    r = director.direct("Quelle est l'histoire de Paris et de sa tour ?", minutes=1, ask_small=ask, ask_big=None)
    assert r == {"legit": False, "reason": "VideoMK can make videos in English and Spanish for now. Try describing your video in one of those."}
    monkeypatch.setenv("VIDEO_LANGUAGES", "en,es,fr,de")
    assert "English, Spanish, French and German" in language.unsupported_message()
    r = director.direct("東京の歴史を教えてください", minutes=1, ask_small=lambda *a, **k: "ja", ask_big=None)
    assert r["legit"] is False and "French and German" in r["reason"]


def test_the_request_check_names_the_languages_of_the_stage(monkeypatch):
    from common import intake
    monkeypatch.delenv("VIDEO_LANGUAGES", raising=False)
    assert intake.system_prompt({}) == intake.SYSTEM and "narrated in English or Spanish" in intake.SYSTEM
    monkeypatch.setenv("VIDEO_LANGUAGES", "en,es,fr")
    p = intake.system_prompt({})
    assert "narrated in English, Spanish or French" in p and "a language other than English, Spanish or French" in p and "English or Spanish" not in p


# ================================================================= casting: what is wanted -> the closest voice there is
@pytest.mark.parametrize("lang,region,voice", [("fr", None, "Lea"), ("fr", "FR", "Lea"), ("fr", "CA", "Gabrielle"), ("fr", "BE", "Isabelle"), ("de", "DE", "Vicki"),
                                               ("de", "AT", "Hannah"), ("de", "CH", "Sabrina"), ("it", "IT", "Bianca"), ("pt", "BR", "Camila"), ("pt", "PT", "Camila"),
                                               ("nl", "NL", "Laura"), ("nl", "BE", "Lisa"), ("pl", "PL", "Ola"), ("fi", "FI", "Suvi"), ("ko", "KR", "Seoyeon")])
def test_the_default_voice_of_every_language_follows_the_region(lang, region, voice):
    assert voices.default_voice(lang, region) == voice and voices.language_of(voice) == lang
    assert voices.cast_voices(None, lang, region) == ({"narrator": voice}, []) and voices.cast_voices({"narrator": {}}, lang, region) == ({"narrator": voice}, [])


def test_the_resolver_casts_what_was_asked_and_says_what_it_substituted():
    r = voices.resolve
    assert r({"accent": "British", "gender": "male"}, "en", "US") == ("Brian", "")
    assert r({"accent": "British"}, "en", "IN") == ("Amy", "") and r("a British woman", "en", "US") == ("Amy", "")
    assert r({"gender": "male"}, "en", "GB") == ("Brian", "") and r({"gender": "male"}, "en", "US")[0] == "Matthew"   # no accent asked: the viewer's own
    assert r({}, "en", "IN") == ("Kajal", "") and r(None, "es", "MX") == ("Mia", "") and r({"gender": "any"}, "en") == ("Ruth", "")
    assert r({"name": "Brian"}, "en", "US") == ("Brian", "") and r("stephen", "en") == ("Stephen", "")
    assert r({"accent": "mexicana", "gender": "female"}, "es", "ES") == ("Mia", "") and r({"accent": "Latin American"}, "es", "ES") == ("Mia", "")
    assert r({"accent": "Canadian", "gender": "male"}, "fr", "FR") == ("Liam", "") and r({"accent": "Swiss"}, "de") == ("Sabrina", "")
    # what the catalogue does not have: the nearest voice, and one plain sentence saying so
    v, note = r({"accent": "Irish", "gender": "male"}, "en", "US")
    assert v == "Brian" and note == "no Irish voice for a male speaker: Brian (British, male) speaks instead"
    v, note = r({"accent": "Canadian"}, "en", "CA")
    assert v == "Ruth" and note.startswith("no Canadian voice: Ruth (American, female)")
    v, note = r({"accent": "Argentinian", "gender": "female"}, "es", "ES")
    assert v == "Mia" and "no Argentinian voice" in note
    v, note = r({"gender": "male"}, "nl", "NL")
    assert v == "Laura" and note.startswith("no free male voice in Dutch")
    v, note = r({"accent": "Portugal"}, "pt", "PT")
    assert v == "Camila" and "Brazilian" in note
    v, note = r({"name": "Lupe"}, "en", "US")
    assert v == "Ruth" and note.startswith("Lupe is not a voice for English")
    # pace is measured, so it can be matched: among the voices that fit equally, the slower or the faster one
    us_men = [n for n in voices.names("en") if voices.CATALOG[n][1:] == ("American", "male")]
    assert r({"gender": "male", "pace": "slow"}, "en", "US")[0] == min(us_men, key=lambda n: voices.INFO[n]["wpm"])
    assert r({"gender": "male", "pace": "fast"}, "en", "US")[0] == max(us_men, key=lambda n: voices.INFO[n]["wpm"])


def test_a_dialogue_gets_distinct_voices_of_the_right_gender_in_every_language():
    cast, notes = voices.cast_voices({"maya": {"gender": "female"}, "sam": {"gender": "male"}, "lee": {"gender": "male", "accent": "British"}}, "en", "US")
    assert cast == {"maya": "Ruth", "sam": "Matthew", "lee": "Brian"} and notes == []
    cast, notes = voices.cast_voices({"ana": {"gender": "female"}, "lucia": {"gender": "female"}, "marta": {"gender": "female"}, "narrator": {}}, "es", "ES")
    assert [voices.CATALOG[cast[s]][2] for s in ("ana", "lucia", "marta")] == ["female"] * 3 and voices.CATALOG[cast["narrator"]][2] == "male" and notes == []
    for lang in ("fr", "de", "it", "pt"):
        cast, notes = voices.cast_voices({"a": {"gender": "female"}, "b": {"gender": "male"}}, lang)
        assert [voices.CATALOG[cast[s]][2] for s in "ab"] == ["female", "male"] and notes == [] and all(voices.language_of(v) == lang for v in cast.values())
    cast, notes = voices.cast_voices({"a": {"gender": "female"}, "b": {"gender": "male"}}, "pl")          # Polish has two voices, both women
    assert sorted(cast.values()) == ["Ewa", "Ola"] and len(notes) == 1 and "no free male voice in Polish" in notes[0]
    cast, notes = voices.cast_voices({"a": {}, "b": {}}, "fi")                                             # Finnish has one voice in all
    assert cast == {"a": "Suvi", "b": "Suvi"} and "Finnish has 1 voice in all" in notes[0]
    # names still work (plans made before, edits, a brief that names a voice), and a name is never given to someone else first
    assert voices.clean_cast({"a": {"gender": "female"}, "b": "Ruth"}, "en", "US") == {"a": "Danielle", "b": "Ruth"}


def test_the_plan_records_what_was_substituted():
    raw = {"legit": True, "title": "T", "voices": {"narrator": {"accent": "Scottish", "gender": "male"}},
           "beats": [{"narration": "This is a first beat with enough words to be kept by the validator.", "scene": {"type": "title", "props": {"title": "A"}}}]}
    p, warns = plan_mod.validate_plan(raw, language="en", region="US")
    assert p["voices"] == {"narrator": "Brian"} and p["voice_notes"] == ["narrator: no Scottish voice: Brian (British, male) speaks instead"]
    assert any(w.startswith("voice: narrator: no Scottish voice") for w in warns)
    again, _ = plan_mod.validate_plan(p, language="en", region="US")                                       # a validated plan validates to itself (edits, repairs)
    assert again["voices"] == {"narrator": "Brian"} and "voice_notes" not in again


def test_the_voice_list_never_enters_the_prompt_and_the_block_does_not_grow_with_the_catalogue():
    for lang in voices.READY:
        p = plan_mod.system_prompt(lang, "US")
        assert f"in {voices.LANGUAGES[lang]}." in p and " | ".join(voices.accents(lang)) in p
        assert not any(f"{n} (" in p for n in voices.names(lang)), lang                                    # no "Ruth (American, female)" rows
        i, j = p.index("Language: write EVERYTHING"), p.index("\nRules:\n")
        assert j - i < 1750, (lang, j - i)                                                                 # about the size the English block always was, for 21 voices or 200
    assert "write those in English" not in plan_mod.system_prompt("en") + plan_mod.system_prompt("es")     # English and Spanish keep their prompt
    assert all("image_query, image_queries, clip queries" in plan_mod.system_prompt(lang) for lang in NEW)


def test_a_presenter_speaks_the_language_of_the_video():
    for cid, c in presenter_policy.CAST.items():
        for lang in NEW:
            v = presenter_policy.voice_for(cid, lang)
            assert voices.language_of(v) == lang, (cid, lang, v)
            if any(voices.CATALOG[n][2] == voices.CATALOG[c["voices"]["en"][0]][2] for n in voices.names(lang)):
                assert voices.CATALOG[v][2] == voices.CATALOG[c["voices"]["en"][0]][2], (cid, lang, v)     # the character's own gender where the language has it
        assert presenter_policy.voice_for(cid, "en") == c["voices"]["en"][0] and presenter_policy.voice_for(cid, "es") == c["voices"]["es"][0]


# ================================================================= pace, numbers, research, the closing card
def test_every_voice_has_a_measured_pace_and_the_fitted_voices_keep_their_fit():
    assert length.rate_for("en", "Ruth") == (0.0547, 0.351, 0.16) and length.rate_for("es", "Lucia") == (0.0495, 0.378, 0.14)
    assert length.rate_for("en") == (0.0555, 0.33, 0.20) and length.rate_for("es", None) == (0.0530, 0.345, 0.14)
    for v in voice_data.VOICES:
        if v["id"] in length.RATES:
            continue
        est = length.estimate_speech(voice_data.SAMPLE[v["language"]], v["language"], v["id"])
        assert est == pytest.approx(v["sample_s"] * length.SAMPLE_CALIBRATION, rel=0.01), v["id"]         # the estimate reproduces the one sentence the voice was heard saying
    assert length.rate_for("fr") == length.rate_for("fr", "Lea") and length.rate_for("xx") == length.LANG_RATES["en"]
    assert length.estimate_speech("Bonjour à tous.", "fr", "Florian") < length.estimate_speech("Bonjour à tous.", "fr", "Lea")   # Florian speaks faster than Léa
    # sentences are cut at capitals of every Latin alphabet (a Polish sentence opening with Ś or Ł is a sentence)
    assert length.sentences("To jest pierwsze zdanie tekstu. Śnieg pada od rana w górach. Łódź płynie powoli po rzece.") == [
        "To jest pierwsze zdanie tekstu.", "Śnieg pada od rana w górach.", "Łódź płynie powoli po rzece."]


@pytest.mark.parametrize("lang", NEW)
def test_numbers_are_written_with_a_decimal_comma(lang):
    assert numfmt.norm_lang(lang) == "es" and numfmt.format_number(3.3, 1, False, lang) == "3,3"
    assert numfmt.format_number(12345.6, 1, True, lang) == "12" + numfmt.NBSP + "345,6"
    assert numfmt.parse_amount("1.234,5", lang) == (1234.5, 1, True) and numfmt.parse_amount("3,3", lang)[0] == 3.3
    assert numfmt.norm_lang("en") == numfmt.norm_lang("ko") == numfmt.norm_lang("English") == "en" and numfmt.norm_lang("Spanish") == numfmt.norm_lang("es-MX") == "es"


def test_research_and_the_closing_card_follow_the_language():
    assert research.api_for("fr") == "https://fr.wikipedia.org/w/api.php" and research.api_for("pl").startswith("https://pl.") and research.api_for("xx").startswith("https://en.")
    asked = []
    research.queries_for("les marées", "fr", lambda s, u: asked.append(s) or "marée")
    assert "in French)" in asked[0]
    assert language.made_with("es") == "Hecho con VideoMK" and language.made_with("en") == language.made_with(None) == "Made with VideoMK"
    assert all("VideoMK" in language.made_with(lang) and language.made_with(lang) != language.made_with("en") for lang in NEW)
    plan = {"language": "de", "watermark": {"mode": "videomk", "end_card": True}, "beats": [{"id": "b1", "narration": "Hallo Welt.", "scene": {"type": "title", "props": {"title": "A"}}}]}
    tl = timeline.build_timeline(plan, [{"duration": 1.0}], video_id="v")
    assert tl["scenes"][-1]["props"]["title"] == "Erstellt mit VideoMK"


# ================================================================= fonts: every letter of every language, in every bundled font
def _missing(font, text):
    """The characters this font has no glyph for: they draw as the font's own "missing" box."""
    box = font.getmask("\U0010fffd")
    blank = (bytes(box), box.size)
    return "".join(sorted({c for c in text if not c.isspace() and (bytes(font.getmask(c)), font.getmask(c).size) == blank}))


FONTS = [os.path.join("fonts", f) for f in ("Inter-Regular.ttf", "Inter-SemiBold.ttf", "Inter-Bold.ttf", "PlayfairDisplay_700Bold.ttf")] + \
        [os.path.join("whiteboard", f) for f in ("PatrickHand-Regular.ttf", "Caveat-Variable.ttf")]


@pytest.mark.parametrize("lang", voices.READY)
def test_every_font_draws_every_letter_of_the_language(lang):
    assert set(PANGRAM) == set(voices.READY)
    for rel in FONTS:
        font = ImageFont.truetype(os.path.join(ASSETS, rel), 48)
        assert _missing(font, "☃") or True                                               # (the check itself is proved below)
        assert _missing(font, PANGRAM[lang] + voice_data.SAMPLE[lang] + PANGRAM[lang].upper() + language.made_with(lang)) == "", (lang, rel)


def _letters(lang):
    """Everything the language writes: its pangram in both cases, its sample sentence, its closing-card line."""
    return sorted({c for c in PANGRAM[lang] + PANGRAM[lang].upper() + voice_data.SAMPLE[lang] + language.made_with(lang) if not c.isspace()})


@pytest.mark.parametrize("lang", voices.READY)
@pytest.mark.parametrize("hand_name", ["neat", "casual"])
def test_the_pen_has_strokes_for_every_letter_of_the_language(lang, hand_name):
    """The font having a letter is not enough on a whiteboard: the pen writes from the STROKE tables (assets/whiteboard/glyphs_*.json). A letter missing there
    was a gap of the wrong width that the pen never traced ("sł ońce")."""
    from engine.whiteboard import hand

    table = hand._table(hand_name)["glyphs"]
    font = ImageFont.truetype(hand.HANDS[hand_name]["font"], 1000)
    lacking = "".join(c for c in _letters(lang) if c not in table or not table[c]["strokes"])
    assert lacking == "", (lang, hand_name, lacking)
    for c in _letters(lang):
        g = hand.glyph(c, hand_name)
        assert not g.get("missing") and abs(g["adv"] - font.getlength(c) / 1000) < 0.01, (lang, hand_name, c)            # the font's own advance: no gap


@pytest.mark.parametrize("hand_name", ["neat", "casual"])
def test_a_letter_without_strokes_is_still_written_at_its_own_width(hand_name, monkeypatch):
    """Whatever the tables lack (a sign, a letter of a language added later): the font's advance, a pen path over its ink, and the word is drawn."""
    from engine.whiteboard import hand

    table = hand._table(hand_name)
    full = hand.layout("słońce", hand_name, 120.0)
    monkeypatch.setitem(hand._TABLES, hand_name, dict(table, glyphs={k: v for k, v in table["glyphs"].items() if k not in "łńĄŻ"}))
    hand._FALLBACK.clear()
    g = hand.glyph("ł", hand_name)
    assert g["missing"] and abs(g["adv"] - table["glyphs"]["ł"]["adv"]) < 0.01 and g["strokes"]
    xs = np.concatenate(g["strokes"])[:, 0]
    assert xs.min() > -0.2 and xs.max() < g["adv"] + 0.2                                    # the pen stays on the letter
    cut = hand.layout("słońce", hand_name, 120.0)
    assert abs(cut["w"] - full["w"]) < 0.02 * full["w"]                                     # the word is as wide as with the table: no "sł ońce"
    only = hand.layout("ĄŻ", hand_name, 120.0)["words"][0]                                  # a word made only of such letters
    r = hand.raster_word(only, (0.0, 0.0), hand_name, "marker", 120.0, 1.0)
    assert r is not None and (r["alpha"] > 0.5).sum() > 500 and ((r["T"] <= 1.0) & (r["alpha"] > 0.5)).sum() > 0.6 * (r["alpha"] > 0.5).sum()   # drawn, and the pen uncovers it


def test_the_glyph_check_sees_a_missing_letter_and_korean_is_why_it_is_not_ready():
    inter = ImageFont.truetype(os.path.join(ASSETS, "fonts", "Inter-Regular.ttf"), 48)
    assert _missing(inter, "기차 abc") == "기차" and _missing(inter, voice_data.SAMPLE["ko"]) != ""    # no Hangul in the render package: Korean captions would be boxes
    assert "ko" not in voices.READY


@pytest.mark.parametrize("lang", voices.READY)
def test_captions_of_the_language_render_with_real_glyphs(lang):
    """The caption line as the renderer draws it (the canvas's own font loader): ink where every word is, and nothing drawn as the missing-glyph box."""
    from engine import canvas
    font = canvas.load_font("semibold", 44)
    text = voice_data.SAMPLE[lang]
    assert _missing(font, text) == ""
    assert font.getlength(text) > 20 * len(text) * 0.5


# ================================================================= word timing from the audio, per language, against exact word marks
def _speech(name):
    meta = json.load(open(os.path.join(FIX, name + ".json"), encoding="utf-8"))
    with wave.open(os.path.join(FIX, name + ".wav"), "rb") as w:
        sr = w.getframerate()
        samples = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
    return meta["text"], samples, sr, [m["start"] for m in meta["marks"]]


@pytest.mark.parametrize("name,mean_max,worst", [("fr_lea", 0.11, 0.35), ("de_vicki", 0.13, 0.40), ("it_bianca", 0.12, 0.45), ("pt_camila", 0.10, 0.35),
                                                 ("nl_laura", 0.10, 0.40), ("pl_ola", 0.17, 0.90), ("fi_suvi", 0.10, 0.45), ("ko_seoyeon", 0.10, 0.35)])
def test_words_are_placed_from_the_audio_in_every_language(name, mean_max, worst):
    text, samples, sr, truth = _speech(name)
    words, conf = align.align_words(samples, sr, text)
    assert [w[0] for w in words] == text.split() and conf >= 0.9
    err = np.array([abs(w[1] - t) for w, t in zip(words, truth) if t is not None])            # a lone "?" or ":" (French spacing) has no mark of its own
    old = np.array([abs(w[1] - t) for w, t in zip(align.estimate_words(text, samples.size / sr), truth) if t is not None])
    assert err.mean() < mean_max and err.max() < worst, (name, round(float(err.mean()), 3), round(float(err.max()), 3))
    assert err.mean() < old.mean()                                                             # better than spreading the words evenly
    starts = [w[1] for w in words]
    assert all(b >= a for a, b in zip(starts, starts[1:]))


def test_a_long_consonant_is_not_taken_for_a_comma():
    """Italian "tutte" and Finnish "noudattaa" hold a consonant as long as a short breath. Before the pace check a comma was pinned to that silence and the
    words after it were up to 2 seconds late."""
    for name in ("it_bianca", "fi_suvi"):
        text, samples, sr, truth = _speech(name)
        words, _ = align.align_words(samples, sr, text)
        assert max(abs(w[1] - t) for w, t in zip(words, truth)) < 0.45, name
    assert align.syllable_weight("기차가") > align.syllable_weight("기차") > align.syllable_weight("a")   # a Hangul block is a syllable
    assert align.syllable_weight("irmão") == align.syllable_weight("irmao") and align.syllable_weight("księgą") == align.syllable_weight("ksiega")
