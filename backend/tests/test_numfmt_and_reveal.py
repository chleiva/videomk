"""Owner reports of 2026-11-27: (1) a counter/stat that sat on a static '0 billion', (2) '3,3 millones' drawn as 33 in a Spanish video, (3) headings that appeared in
stuck lumps of 2-3 words. Numbers are tested as strings drawn on the canvas (recorded), the reveal as the number of words visible at every frame."""
import copy
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))

from engine import easing, numfmt, plan as plan_mod  # noqa: E402
from engine.canvas import Canvas  # noqa: E402
from engine.frame import Frame  # noqa: E402
from engine.renderer import Renderer  # noqa: E402
from engine.scenes import ELEMENTS  # noqa: E402
from engine.scenes.elements.text_lists import kinetic_groups, kinetic_word_times  # noqa: E402


# ----------------------------------------------------------------------------- parsing and formatting
@pytest.mark.parametrize("text,lang,value,decimals,grouped", [
    ("3,3", "es", 3.3, 1, False), ("3.3", "es", 3.3, 1, False), ("3,3", "en", 3.3, 1, False), ("3.3", "en", 3.3, 1, False),
    ("1.234", "es", 1234.0, 0, True), ("1,234", "en", 1234.0, 0, True),
    ("1.234", "en", 1.234, 3, False), ("1,234", "es", 1.234, 3, False),                    # exactly 3 digits after one mark: the language decides
    ("1.234,5", "es", 1234.5, 1, True), ("1.234,5", "en", 1234.5, 1, True), ("1,234.5", "en", 1234.5, 1, True), ("1,234.5", "es", 1234.5, 1, True),
    ("12,5", "es", 12.5, 1, False), ("12.5", "en", 12.5, 1, False), ("0,5", "es", 0.5, 1, False), ("0,5", "en", 0.5, 1, False),
    ("0,500", "es", 0.5, 3, False), ("1234.56", "es", 1234.56, 2, False), ("1.234.567", "es", 1234567.0, 0, True), ("1,234,567", "en", 1234567.0, 0, True),
    ("12 345,6", "es", 12345.6, 1, True), ("3300", "es", 3300.0, 0, False),
])
def test_amounts_are_read_the_way_the_language_writes_them(text, lang, value, decimals, grouped):
    assert numfmt.parse_amount(text, lang) == (value, decimals, grouped)


@pytest.mark.parametrize("bad", ["1,23,4", "1.2.3", "12 34", "1..2", "", "3,,3"])
def test_a_separator_is_never_dropped_silently(bad):
    assert numfmt.parse_amount(bad, "es") is None and numfmt.parse_amount(bad, "en") is None


def test_owner_case_3_3_million_in_spanish():
    assert numfmt.parse_number("3,3 millones", "es") == ("", 3.3, 1, " millones", False)
    assert numfmt.parse_number("12,5 %", "es")[1:4] == (12.5, 1, " %")
    assert numfmt.parse_number("$1,250.5M", "en") == ("$", 1250.5, 1, "M", True)
    with numfmt.language_scope("es"):
        assert numfmt.parse_float("3,3") == 3.3 and numfmt.parse_float("1.234,5") == 1234.5
    with pytest.raises(ValueError):
        numfmt.parse_float("many")
    with pytest.raises(ValueError):
        numfmt.parse_float(True)


def test_formatting_per_language():
    assert numfmt.format_number(3.3, 1, False, "es") == "3,3"
    assert numfmt.format_number(1234.5, 1, True, "es") == "1234,5"                      # RAE: no separator for four digits
    assert numfmt.format_number(1234567.5, 1, True, "es") == "1 234 567,5"    # five or more digits: a non-breaking space
    assert numfmt.format_number(-0.04, 1, False, "es") == "0,0"
    assert numfmt.format_number(3.3, 1, False, "en") == "3.3" and numfmt.format_number(1234.5, 1, True, "en") == "1,234.5"
    assert numfmt.format_number(12345, 0, False, "en") == "12,345"
    assert numfmt.localize("3.5%", "es") == "3,5%" and numfmt.localize("3.5%", "en") == "3.5%"


def test_chart_values_from_the_director_keep_their_decimals_in_spanish():
    clean, _ = plan_mod.validate_plan(
        {"title": "t", "legit": True, "beats": [{"narration": "Las emisiones por sector y su evolucion durante la ultima decada en el mundo entero.",
                                                  "scene": {"type": "chart", "props": {"labels": ["a", "b"], "values": ["3,3", "1.234,5"], "unit": "M"}}}]},
        language="es")
    chart = [b for b in clean["beats"] if b["scene"]["type"] == "chart"]
    assert chart and chart[0]["scene"]["props"]["values"] == [3.3, 1234.5]            # it was [33.0, 12345.0]


# ----------------------------------------------------------------------------- counter and stat
def _record(stype, props, lt, dur=8.0, language="en", aspect="16:9"):
    """Everything drawn as text at scene time `lt`: [(string, alpha 0..255)], through the real Renderer."""
    fr = Frame.parse(aspect, "1080p")
    sc = {"id": "t", "type": stype, "start": 0.0, "duration": dur, "props": props, "words": [], "transition": "none"}
    tl = {"scenes": [sc], "theme": "midnight", "captions": False, "duration": dur, "width": fr.width, "height": fr.height, "fps": 30, "outro": False,
          "language": language, "frame": {"aspect": fr.aspect, "resolution": fr.resolution}}
    r = Renderer(tl, draft=True)
    seen = []
    orig = Canvas.text

    def spy(self, x, y, s, weight="regular", size=40, fill=(255, 255, 255, 255), anchor="la"):
        seen.append((s, int(fill[3]) if len(fill) == 4 else 255))
        return orig(self, x, y, s, weight, size, fill, anchor)

    Canvas.text = spy
    try:
        r._draw_spec(sc, lt)
    finally:
        Canvas.text = orig
    return seen


def _joined(seen):
    """The counter draws its number one character at a time (tabular figures): the number as one string."""
    return "".join(s for s, a in seen if len(s) == 1 and (s.isdigit() or s in ",.\u00a0") and a > 0)


def _numbers(seen):
    return [(s, a) for s, a in seen if any(c.isdigit() for c in s)]


@pytest.mark.parametrize("language,expected", [("en", "3.3 billion"), ("es", "3,3 billion")])
def test_stat_draws_the_final_value_in_the_video_language(language, expected):
    end = _numbers(_record("stat", {"value": "3,3 billion" if language == "es" else "3.3 billion", "label": "x"}, 7.0, language=language))
    assert [s for s, a in end if a > 200] == [expected], end


def test_spanish_stat_is_not_33():
    drawn = [s for s, _ in _numbers(_record("stat", {"value": "3,3 millones", "label": "de toneladas"}, 7.0, language="es"))]
    assert drawn == ["3,3 millones"] and "33 millones" not in drawn


def test_stat_never_shows_a_zero_and_counts_from_the_first_frames():
    for lt in (0.0, 0.1, 0.2, 0.5, 1.0):
        for s, a in _numbers(_record("stat", {"value": "3.3 billion", "label": "tonnes of CO2 absorbed by forests each year"}, lt)):
            assert not s.startswith("0 ") and s != "0 billion", (lt, s)
    f0 = _numbers(_record("stat", {"value": "3.3 billion", "label": "x"}, 0.1))
    assert f0 and float(f0[0][0].split()[0]) >= 0.2 * 3.3 - 0.05            # frame 0.1 s already shows at least 20% of the figure (and the unit)
    assert "billion" in f0[0][0]
    mid = [float(s.split()[0]) for s, a in _numbers(_record("stat", {"value": "3.3 billion", "label": "x"}, 0.4))]
    end = [float(s.split()[0]) for s, a in _numbers(_record("stat", {"value": "3.3 billion", "label": "x"}, 7.0))]
    assert mid[0] < end[0] == 3.3


def test_the_label_is_there_with_the_number():
    seen = _record("stat", {"value": "3.3 billion", "label": "tonnes of carbon dioxide absorbed by forests each year"}, 0.5)
    assert any("tonnes" in s and a > 60 for s, a in seen)


def test_counter_starts_immediately_eases_out_and_holds_the_exact_value():
    p = ELEMENTS["counter"].sanitize({"value": "73", "unit": "%", "label": "Share of adults"})
    vals = []
    for lt in (0.05, 0.1, 0.2, 0.4, 0.8, 1.2, 1.6, 2.0, 7.9):
        j = _joined(_record("counter", p, lt))
        vals.append(int(j) if j else None)
    shown = [v for v in vals if v is not None]
    assert shown[0] >= 0.2 * 73 - 1 and shown[0] > 0, vals                  # frame 0: already mid-count, never 0
    assert shown == sorted(shown) and shown[-1] == 73 and vals[-1] == 73
    assert vals[7] == 73                                                     # settled by 2 s
    assert (vals[2] - vals[0]) > (vals[5] - vals[4])                         # fast, then settling (ease-out)
    unit_alpha = [a for s, a in _record("counter", p, 0.6) if s == "%"]
    assert unit_alpha and unit_alpha[0] > 100                                # the unit is visible with the number


def test_counter_with_an_explicit_start_counts_from_it_and_spanish_decimals_work():
    p = ELEMENTS["counter"].sanitize({"value": "1,250", "unit": "km", "from": "2,000", "label": "x"})
    first = _joined(_record("counter", p, 0.1))
    assert 1800 <= int(first.replace(",", "")) <= 2000, first                            # it counts DOWN from the director's start value, not from a floor
    p = ELEMENTS["counter"].sanitize({"value": "3,3", "unit": "M", "label": "x"})        # the director wrote a Spanish decimal comma (parsed at plan time with no language: 1 digit after)
    assert p["value"] == "3.3" and p["decimals"] == 1
    assert _joined(_record("counter", p, 7.5, language="es")) == "3,3"                  # drawn the Spanish way
    assert _joined(_record("counter", p, 7.5, language="en")) == "3.3"
    assert ELEMENTS["counter"].sanitize(copy.deepcopy(p)) == p                          # idempotent: the editor re-sanitizes


def test_counter_sanitize_reads_ambiguous_numbers_by_the_plan_language():
    el = ELEMENTS["counter"]
    with numfmt.language_scope("es"):
        assert el.sanitize({"value": "1.234", "label": "x"})["value"] == "1234"
        assert el.sanitize({"value": "3.300", "label": "x"})["value"] == "3300"
    with numfmt.language_scope("en"):
        assert el.sanitize({"value": "1.234", "label": "x"})["value"] == "1.234"
        assert el.sanitize({"value": "1,234", "label": "x"})["value"] == "1234"


def test_count_helpers_stay_inside_the_standard():
    assert easing.count_run(10.0) == 1.5 and easing.count_run(2.0) == 0.8 and easing.count_run(0.5) == 0.5
    assert easing.count_up(0.0, 10.0) == easing.COUNT_FLOOR and easing.count_up(5.0, 10.0) == 1.0 and easing.count_up(0.0, 10.0, 0.0) == 0.0
    ps = [easing.count_up(t / 30.0, 10.0) for t in range(0, 60)]
    assert ps == sorted(ps) and all(0.0 <= v <= 1.0 for v in ps)


# ----------------------------------------------------------------------------- kinetic reveal
def _kinetic_words(props, lt, dur=8.0):
    """Words visible (alpha > 6%) at scene time lt."""
    return sum(1 for s, a in _record("kinetic_text", props, lt, dur=dur) if a > 15 and s.strip() and s.split()[0] in props["text"].split())


def _max_gap_between_changes(props, dur, step=1 / 30):
    counts = [_kinetic_words(props, i * step, dur) for i in range(int(dur / step))]
    changes = [i for i in range(1, len(counts)) if counts[i] != counts[i - 1]]
    gaps = [b - a for a, b in zip(changes, changes[1:])]
    return counts, max(gaps) * step if gaps else 0.0


SENTENCE = "If you cannot explain it simply, you do not understand it well enough yet, and that is fine because understanding is a process."


def test_kinetic_word_times_are_even_even_when_the_cues_cluster():
    p = ELEMENTS["kinetic_text"].sanitize({"text": SENTENCE, "emphasis": "understanding is a process"})
    groups = kinetic_groups(p)
    n = len(p["text"].split())
    clustered = [0.5 + 0.02 * g for g in range(len(groups))]                  # every group cued almost at the same moment
    when = kinetic_word_times(groups, n, 8.0, clustered)
    steps = [b - a for a, b in zip(sorted(when), sorted(when)[1:])]
    assert min(steps) >= 0.1 and max(steps) <= 0.4 + 1e-9                    # no lumps, no stalls
    assert when == sorted(when)                                              # words appear in reading order
    cues = [0.5, 3.0, 5.5]                                                   # a real pause between cues: each content word still lands on its cue, the little words just before it
    groups3 = groups[:3]
    when3 = kinetic_word_times(groups3, sum(len(g[0]) for g in groups3), 8.0, cues)
    assert when3 == sorted(when3)
    ends = [when3[sum(len(g[0]) for g in groups3[:k + 1]) - 1] for k in range(3)]
    assert all(e <= c + 1e-9 for e, c in zip(ends, cues)) and all(e >= c - 1.3 for e, c in zip(ends, cues))


def test_kinetic_text_reveals_smoothly_at_every_frame():
    p = ELEMENTS["kinetic_text"].sanitize({"text": "Compound interest rewards patience more than talent over time.", "emphasis": "patience"})
    words = [["Compound", 0.5, 0.9], ["interest", 1.0, 1.4], ["rewards", 1.5, 1.9], ["patience", 2.5, 3.0], ["more", 3.1, 3.3], ["than", 3.3, 3.5], ["talent", 3.6, 4.0],
             ["over", 4.1, 4.2], ["time", 4.3, 4.6]]
    from engine import sync
    sync.apply("kinetic_text", p, words, 8.0)
    counts, gap = _max_gap_between_changes(p, 8.0)
    assert counts == sorted(counts) and counts[-1] == len(p["text"].split())    # monotonic, ends with every word
    assert gap <= 0.55, f"the text stood still for {gap:.2f}s between two words"
    assert counts[0] <= 1 and next(i for i, c in enumerate(counts) if c) <= 25   # nothing stuck at the start


def test_kinetic_text_with_clustered_narration_timings_never_lumps():
    p = ELEMENTS["kinetic_text"].sanitize({"text": SENTENCE, "emphasis": "understanding is a process"})
    groups = kinetic_groups(p)
    p["cues"] = [1.0 + 0.01 * g for g in range(len(groups))]
    counts, gap = _max_gap_between_changes(p, 8.0)
    jumps = [b - a for a, b in zip(counts, counts[1:])]
    assert max(jumps) <= 1, f"{max(jumps)} words appeared in one frame"      # at most one new word per frame (30 fps): no batch of 3
    assert gap <= 0.5


def test_chapter_card_and_quote_reveal_at_a_constant_pace():
    from engine.scenes.elements import photo_layouts  # noqa: F401
    q = {"text": "Never doubt that a small group of thoughtful committed citizens can change the world", "attribution": "M. Mead"}
    counts = []
    for i in range(0, 200):
        seen = _record("quote", q, i / 30.0, dur=8.0)
        counts.append(sum(1 for s, a in seen if a > 15 and s in q["text"].split()))
    assert counts == sorted(counts) and counts[-1] == len(q["text"].split())
    jumps = [b - a for a, b in zip(counts, counts[1:])]
    assert max(jumps) <= 1
