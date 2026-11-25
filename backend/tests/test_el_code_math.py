"""Tests for the `code` and `equation` elements."""
import copy

import pytest

from tests.element_utils import changed, render
from engine.scenes import ELEMENTS
from engine.scenes.elements import code_math as cm

CODE, EQ = ELEMENTS["code"], ELEMENTS["equation"]


# ----------------------------------------------------------------------------- code: sanitize
def test_code_sanitize_limits_and_cleaning():
    long = "\n".join(f"line{i} = {i}\t# tab" for i in range(40))
    out = CODE.sanitize({"code": long, "language": "JS", "title": "t" * 99, "steps": [{"lines": [1, 99, "x", 0, 2.0], "note": "n" * 200}, {"lines": [77]}, "junk"]})
    lines = out["code"].split("\n")
    assert len(lines) <= 18 and len(out["code"]) <= 900 and "\t" not in out["code"]
    assert out["language"] == "javascript" and len(out["title"]) == 50
    assert out["steps"] == [{"lines": [1, 2], "note": "n" * 70}]   # invalid line numbers dropped, a step with no valid line dropped


def test_code_columns_clipped_and_empty_rejected():
    out = CODE.sanitize({"code": "x" * 300})
    assert max(len(l) for l in out["code"].split("\n")) == 70
    for bad in ({}, {"code": ""}, {"code": "  \n\n "}, {"code": 5}, {"code": None}):
        with pytest.raises(ValueError):
            CODE.sanitize(bad)


def test_code_mode_defaults_and_diff_without_changes_becomes_code():
    assert CODE.sanitize({"code": "a = 1", "mode": "weird"})["mode"] == "code"
    assert CODE.sanitize({"code": "a = 1\nb = 2", "mode": "diff"})["mode"] == "code"
    assert CODE.sanitize({"code": "-a = 1\n+b = 2", "mode": "diff"})["mode"] == "diff"


def test_code_anchors_use_notes_or_identifiers():
    p = CODE.sanitize({"code": "def total(prices):\n    return sum(prices)", "language": "python", "steps": [{"lines": [1], "note": "A function"}, {"lines": [2]}]})
    a = CODE.anchors(p)
    assert a[0] == "A function" and "return" in a[1] and "prices" in a[1]


def test_tokenizer_colours_the_basics():
    kinds = {t: k for _, t, k in cm.tokenize('def f(x): return "a" # c', "python")}
    assert kinds["def"] == "keyword" and kinds["f"] == "func" and kinds['"a"'] == "string" and kinds["# c"] == "comment"
    assert {t: k for _, t, k in cm.tokenize("SELECT 42 FROM t", "sql")}["SELECT"] == "keyword"
    assert {t: k for _, t, k in cm.tokenize('{"a": 1}', "json")}['"a"'] == "func"
    assert cm.tokenize("npm install -g x", "bash")[0][2] == "func"


def test_code_typing_finishes_in_the_first_third():
    p = CODE.sanitize(CODE.samples[0])
    lines = cm._parse_lines(p["code"], p["language"], p["mode"])
    _, end = cm._type_schedule(lines, 9.0)
    assert end <= 9.0 / 3 + 1e-6
    big = CODE.sanitize({"code": "\n".join("x = %d  # %s" % (i, "y" * 40) for i in range(18))})
    _, end = cm._type_schedule(cm._parse_lines(big["code"], "", "code"), 9.0)
    assert end <= 3.0 + 1e-6


def test_code_steps_dim_and_end_state_shows_the_note():
    p = CODE.sanitize(CODE.samples[0])
    early, late = render("code", p, 1.0, 9.0), render("code", p, 8.9, 9.0)
    assert changed(early, late) > 0.01
    assert changed(render("code", p, 5.0, 9.0), late) > 0.005   # a later step changes the picture


def test_code_cues_follow_narration():
    p = CODE.sanitize(CODE.samples[0])
    p["cues"] = [4.0, 5.0, 6.0]
    assert CODE.cues(p, 9.0) == [0.3, 4.0, 5.0, 6.0]


@pytest.mark.parametrize("i", range(4))
def test_code_samples_render_all_modes_on_all_themes(i):
    p = CODE.sanitize(copy.deepcopy(CODE.samples[i]))
    for th in ("midnight", "paper", "sunrise"):
        render("code", p, 8.0, 9.0, th, captions=True)


def test_code_full_size_max_content_fits():
    p = CODE.sanitize({"title": "Title here", "language": "python", "code": "\n".join("value_%02d = compute(%d)  # note" % (i, i) for i in range(18)),
                       "steps": [{"lines": [18], "note": "n" * 70}]})
    g = cm._code_geometry(18, 70, True, "code", 100.0, 794.0)
    assert g["py"] + g["ph"] + 105 <= 800 + 1 and g["fs"] >= 20
    render("code", p, 8.0, 9.0, "midnight", captions=True)


# ----------------------------------------------------------------------------- equation: parser
GOOD = ["E = m c^2", "x = (-b + sqrt(b^2 - 4ac)) / (2a)", "sum_{i=1}^{n} i = n(n+1)/2", "a/b", "int_0^1 x^2 dx", "pi r^2", "sin(theta)^2 + cos(theta)^2 = 1",
        "prod_{k=1}^{n} k = n!", "e^(-x^2/2)", "1/2 m v^2", "F = G m_1 m_2 / r^2", "alpha + beta <= gamma", "sqrt(2)", "x_{n+1} = x_n - f(x_n)/f'(x_n)", "Delta x -> 0",
        "-b", "lim x -> inf", "[a + b]^2"]


@pytest.mark.parametrize("f", GOOD)
def test_good_formulas_typeset(f):
    w, a, d, ops = cm.layout_formula(f)
    assert w > 10 and a + d > 10 and ops
    out = EQ.sanitize({"steps": [{"formula": f}]})
    assert out["steps"][0]["formula"] == f


@pytest.mark.parametrize("f", ["(a + b", "a + b)", "x^", "x_", "/2", "a /", "sqrt", "x^2^3", "x_1_2", "\\frac{a}{b}", "a ? b", "(" * 12 + "x" + ")" * 12, "a" * 200, "sum_", "{a"])
def test_bad_formulas_are_rejected(f):
    with pytest.raises(ValueError):
        EQ.sanitize({"steps": [{"formula": f}]})


def test_equation_layout_structure():
    # a fraction is taller than its parts, a superscript raises the ink, sqrt draws a radical polyline
    _, a1, d1, _ = cm.layout_formula("a")
    _, a2, d2, ops2 = cm.layout_formula("a/b")
    assert a2 + d2 > a1 + d1 and any(o[0] == "l" for o in ops2)
    _, a3, _, _ = cm.layout_formula("a^2")
    assert a3 > a1
    assert any(o[0] == "p" for o in cm.layout_formula("sqrt(x)")[3])
    glyphs = [o[3] for o in cm.layout_formula("sum_{i=1}^{n} i")[3] if o[0] == "t"]
    assert "∑" in glyphs and "n" in glyphs and "1" in glyphs
    assert "π" in [o[3] for o in cm.layout_formula("pi")[3] if o[0] == "t"]
    glyphs = [o[3] for o in cm.layout_formula("1/2 m v^2")[3] if o[0] == "t"]
    assert "m" in glyphs and "1" in glyphs   # "1/2 m" is a half times m, not 1 over 2m


def test_equation_sanitize_steps_and_notes():
    out = EQ.sanitize({"title": "T" * 80, "steps": [{"formula": f"x = {i}", "note": "n" * 100} for i in range(9)]})
    assert len(out["steps"]) == 4 and len(out["steps"][0]["note"]) == 60 and len(out["title"]) == 50
    assert EQ.sanitize({"formula": "a = b"})["steps"] == [{"formula": "a = b"}]
    assert EQ.sanitize({"steps": ["a = 1", {"formula": ""}]})["steps"] == [{"formula": "a = 1"}]
    with pytest.raises(ValueError):
        EQ.sanitize({"steps": [{"formula": "a = 1"}, {"formula": "(("}]})   # one bad step rejects the scene
    with pytest.raises(ValueError):
        EQ.sanitize({"steps": []})


def test_equation_anchors_and_reveal_order():
    p = EQ.sanitize(EQ.samples[1])
    assert EQ.anchors(p)[0] == "Start from the general quadratic"
    assert EQ.anchors(EQ.sanitize({"steps": [{"formula": "a = 1"}]})) == ["a = 1"]
    p["cues"] = [1.0, 3.0, 5.0]
    assert EQ.cues(p, 8.0) == [1.0, 3.0, 5.0]
    mid = render("equation", p, 2.0, 8.0)       # only step 1 visible
    end = render("equation", p, 8.0, 8.0)
    assert changed(mid, end) > 0.01


@pytest.mark.parametrize("i", range(3))
def test_equation_end_state_complete_on_all_themes(i):
    p = EQ.sanitize(copy.deepcopy(EQ.samples[i]))
    for th in ("midnight", "paper", "sunrise"):
        end = render("equation", p, 8.0, 8.0, th, captions=True)
        assert changed(render("equation", p, 0.0, 8.0, th), end) > 0.01


# ----------------------------------------------------------------------------- responsive layouts (9:16, 1:1, 4:5)
ASPECTS = ("9:16", "1:1", "4:5")


def _inside_box(img, aspect, ref_img):
    import numpy as np
    from engine.frame import Frame
    fr = Frame.parse(aspect, "720p")
    a, b = np.asarray(img.convert("RGB"), np.int16), np.asarray(ref_img.convert("RGB"), np.int16)
    ys, xs = np.where(np.abs(a - b).max(axis=2) > 60)
    cx0, cy0, cx1, cy1 = fr.content_box
    s = 1.0   # draft frames are drawn at design size
    return xs.min() >= (cx0 - 40) * s and xs.max() <= (cx1 + 40) * s and ys.max() <= (cy1 + 40) * s and ys.min() >= (fr.margin_top - 45) * s


def _end_state(name, props, aspect, dur=8.0):
    from tests.element_utils import make_renderer
    r, sc = make_renderer(name, props, dur, "midnight", [], True, None, True, aspect, "720p")
    from engine.frame import Frame
    fr = Frame.parse(aspect, "720p")
    return r._draw_spec(sc, dur * 0.95), fr


def test_code_and_equation_are_tagged_for_every_aspect():
    assert CODE.formats == EQ.formats == ("16:9", "9:16", "1:1", "4:5")


def test_wrap_line_hangs_and_never_loses_text():
    t = "        raise FileNotFoundError(f\"missing configuration file at {cfg.path} please create it\")"
    rows = cm._wrap_line(t, 40)
    assert len(rows) >= 3 and rows[0][2] == 0 and all(r[2] > 0 for r in rows[1:])
    text = "".join(t[a:b] for a, b, _ in rows).replace(" ", "")
    assert text == t.replace(" ", "")
    assert all(b - a + i <= 40 for a, b, i in rows)
    assert cm._wrap_line("short", 40) == [(0, 5, 0)]
    assert cm._wrap_line("x" * 100, 30)[-1][1] == 100     # a word longer than a row is cut, not dropped


@pytest.mark.parametrize("aspect", ASPECTS)
def test_code_longest_snippet_fits_the_box_and_the_font_is_not_tiny(aspect):
    code = "\n".join(("    " * (i % 3)) + f"value_{i} = compute_something(argument_one, argument_two, argument_three_{i})" for i in range(18))
    props = CODE.sanitize({"title": "Long snippet", "language": "python", "code": code, "steps": [{"lines": [3], "note": "A fairly long explanation of what this line does in plain words"}]})
    img, fr = _end_state("code", props, aspect)
    from tests.element_utils import blank
    from tests.test_formats import _bg
    assert _inside_box(img, aspect, _bg(aspect, "midnight", 7.6, draft=True))
    lines = cm._parse_lines(props["code"], "python", "code")
    c = ctx_for(aspect)
    g = cm._code_geometry_tall(lines, True, "code", float(c.box[0]), float(c.box[2]), float(c.top + 30), float(c.bottom - 6), 44.0, 34.0)
    assert g["fs"] >= 18 and g["py"] + g["ph"] + 150 <= c.bottom + 1


def ctx_for(aspect):
    from engine.frame import Frame
    from engine.scenes.base import SceneCtx
    return SceneCtx(frame=Frame.parse(aspect, "720p"), captions=True)


@pytest.mark.parametrize("aspect", ASPECTS)
def test_code_vertical_font_is_larger_than_the_landscape_card_would_be(aspect):
    props = CODE.sanitize(CODE.samples[1])
    lines = cm._parse_lines(props["code"], "bash", "terminal")
    c = ctx_for(aspect)
    g = cm._code_geometry_tall(lines, True, "terminal", float(c.box[0]), float(c.box[2]), float(c.top + 50), float(c.bottom - 6), 44.0, 34.0)
    assert g["fs"] >= 30 and g["pw"] == c.box[2] - c.box[0]


def test_formula_lines_split_at_relations_and_every_line_parses():
    f = "sum_{i=1}^{n} i^2 = n(n+1)(2n+1)/6 = (2n^3 + 3n^2 + n)/6"
    lines = cm._formula_lines(f, 600.0)
    assert len(lines) >= 2 and lines[1].startswith("=")
    for ln in lines:
        cm.layout_formula(ln)
    assert cm._formula_lines("E = m c^2", 600.0) == ("E = m c^2",)     # fits: left alone
    # nothing inside brackets is cut
    assert cm._formula_lines("x = (-b + sqrt(b^2 - 4ac)) / (2a)", 150.0)[0] in ("x", "x = (-b + sqrt(b^2 - 4ac)) / (2a)")


@pytest.mark.parametrize("aspect", ASPECTS)
def test_equation_four_long_steps_fit_the_box(aspect):
    props = EQ.sanitize({"title": "Four steps of a long derivation", "steps": [
        {"formula": "x_{n+1} = x_n - f(x_n)/f'(x_n)", "note": "Newton's method with a long explanation"},
        {"formula": "sum_{i=1}^{n} i^2 = n(n+1)(2n+1)/6 = (2n^3 + 3n^2 + n)/6", "note": "Sum of squares"},
        {"formula": "int_0^1 x^2 dx + int_1^2 x^3 dx + int_2^3 x^4 dx = 1/3 + 15/4 + 211/5"}, {"formula": "sin(theta)^2 + cos(theta)^2 = 1"}]})
    img, fr = _end_state("equation", props, aspect)
    from tests.test_formats import _bg
    assert _inside_box(img, aspect, _bg(aspect, "midnight", 7.6, draft=True))
    plan = cm._eq_plan_tall(tuple(s["formula"] for s in props["steps"]), tuple(s.get("note", "") for s in props["steps"]), 200.0, float(ctx_for(aspect).bottom - 10), 840.0, fr.type_scale, fr.vertical)
    assert plan[-1][1] + plan[-1][2] <= ctx_for(aspect).bottom + 1


def test_landscape_code_and_equation_geometry_unchanged():
    # the landscape path must not be affected by the narrow-frame code
    g = cm._code_geometry(6, 36, True, "code", 150.0, 794.0)
    assert g["px"] + g["pw"] / 2 == 960
