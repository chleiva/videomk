"""The styled `bullets` and `diagram` scenes: look props (style, accent, icon, emphasis), colour contrast, backward compatibility, every style at every size,
first and last frames, and the safe area."""
import copy
import itertools
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))

import numpy as np
import pytest

from engine import plan as plan_mod
from engine import sync
from engine.scenes import style_kit as sk
from engine.scenes.list_scenes import keyword_split
from engine.theme import THEMES
from tests.element_utils import blank, changed, render

LONG26 = "Twenty six chars label ab"
LONG80 = "A deliberately long list item that runs on to the full eighty characters allowed.."


def _bullets(n, style=None, accent=None, long=False, **extra):
    items = [(LONG80 if long else f"Point number {i + 1}")[:80] for i in range(n)]
    p = {"heading": "What really matters", "items": items, **extra}
    if style:
        p["style"] = style
    if accent:
        p["accent"] = accent
    return p


def _flow(n, style=None, accent=None, long=False, branch=False, **extra):
    nodes = [{"id": f"n{i}", "label": (LONG26 if long else f"Step {i + 1}")[:26]} for i in range(n)]
    edges = [[f"n{i}", f"n{i + 1}"] for i in range(n - 1)]
    if branch and n >= 4:
        edges = [["n0", "n1"], ["n0", "n2", "or"], ["n1", "n3"], ["n2", "n3"]] + [[f"n{i}", f"n{i + 1}"] for i in range(3, n - 1)]
    p = {"title": "How the golden rule spreads", "nodes": nodes, "edges": edges, **extra}
    if style:
        p["style"] = style
    if accent:
        p["accent"] = accent
    return p


# ------------------------------------------------------------------ palettes
@pytest.mark.parametrize("theme,accent", list(itertools.product(THEMES, sk.ACCENT_CHOICES)))
def test_palette_contrast(theme, accent):
    th = THEMES[theme]
    pal = sk.pal_for(th, accent)
    assert sk.contrast(pal.accent_text, th.bg_bottom) >= 4.5, "accent text on the plain background"
    assert sk.contrast(pal.ink, pal.c1) >= 4.5 and sk.contrast(pal.ink, pal.c2) >= 4.5, "text on the accent fill"
    assert sk.contrast(pal.text, th.bg_bottom) >= 7


def test_accents_are_distinct():
    th = THEMES["midnight"]
    cols = {a: sk.pal_for(th, a).c1 for a in sk.ACCENTS}
    assert len(set(cols.values())) == len(sk.ACCENTS)


def test_unknown_accent_is_auto():
    th = THEMES["paper"]
    assert sk.pal_for(th, "chartreuse") == sk.pal_for(th, "auto") == sk.pal_for(th, None)


# ------------------------------------------------------------------ sanitising
def test_sanitize_keeps_valid_look_props():
    out = plan_mod.sanitize_props("bullets", {"heading": "H", "items": ["a b", "c d", "e f"], "style": "Cards", "accent": "TEAL", "emphasis": 1, "icons": ["rocket", "", "heart"]})
    assert out["style"] == "cards" and out["accent"] == "teal" and out["emphasis"] == 1
    assert out["icons"][0] == "rocket" and out["icons"][1] == "" and out["icons"][2] == "heart" and len(out["icons"]) == 3
    out = plan_mod.sanitize_props("diagram", {"nodes": [{"id": "a", "label": "A", "icon": "rocket"}, {"id": "b", "label": "B"}], "edges": [["a", "b"]], "style": "stack", "accent": "amber", "emphasis": 0})
    assert out["style"] == "stack" and out["accent"] == "amber" and out["emphasis"] == 0 and out["nodes"][0]["icon"] == "rocket" and "icon" not in out["nodes"][1]


def test_sanitize_drops_bad_look_props():
    bad = {"heading": "H", "items": ["a b", "c d"], "style": "<script>", "accent": "#ff0000", "emphasis": 9, "icons": "rocket", "color": "red", "x": 1}
    out = plan_mod.sanitize_props("bullets", bad)
    assert out == {"heading": "H", "items": ["a b", "c d"]}
    out = plan_mod.sanitize_props("bullets", {"items": ["a", "b"], "style": "ladder", "emphasis": True, "icons": [{"x": 1}, 5]})   # a flow style on a list, a bool, junk icons
    assert out == {"heading": "", "items": ["a", "b"]}
    out = plan_mod.sanitize_props("diagram", {"nodes": [{"id": "a", "label": "A", "icon": "x" * 500}, {"id": "b"}], "edges": [], "style": "rail", "accent": ["indigo"], "emphasis": -1})
    assert set(out) == {"title", "nodes", "edges"} and "icon" not in out["nodes"][0]


def test_sanitize_old_props_unchanged_and_idempotent():
    old = {"heading": "H", "items": ["one", "two", "three"]}
    assert plan_mod.sanitize_props("bullets", old) == old
    olddg = {"title": "T", "nodes": [{"id": "a", "label": "A"}, {"id": "b", "label": "B"}], "edges": [["a", "b", "go"]]}
    assert plan_mod.sanitize_props("diagram", olddg) == olddg
    full = plan_mod.sanitize_props("bullets", {"heading": "H", "items": ["one", "two"], "style": "icons", "accent": "sky", "emphasis": 0, "icons": ["star", "cloud"]})
    assert plan_mod.sanitize_props("bullets", full) == full


def test_director_docs_are_compact_and_name_the_looks():
    lines = {l.split(":")[0]: l for l in plan_mod.SCENE_DOCS.split("\n") if l.startswith(("- bullets", "- diagram"))}
    for stype, styles in (("- bullets", sk.LIST_STYLES), ("- diagram", sk.FLOW_STYLES)):
        assert len(lines[stype]) <= 750, len(lines[stype])
        assert all(f'"{s}"' in lines[stype] for s in styles)
        assert all(a in lines["- bullets"] for a in sk.ACCENTS)


def test_keyword_split():
    assert keyword_split("Speed: how fast it goes") == ("Speed", "how fast it goes")
    assert keyword_split("Safe by design") == ("Safe by design", "")
    k, d = keyword_split("Wealth is not everything in life")
    assert k and d and (k + " " + d).split() == "Wealth is not everything in life".split()


# ------------------------------------------------------------------ rendering
@pytest.mark.parametrize("style", list(sk.LIST_STYLES) + ["nonsense", None])
@pytest.mark.parametrize("n", [2, 3, 4, 5, 6])
def test_every_list_style_renders_at_every_size(style, n):
    for long in (False, True):
        img = render("bullets", _bullets(n, style, long=long), 30.0, 8.0, "midnight", captions=True)
        assert changed(img, blank("midnight", 30.0, 8.0)) > 0.01


@pytest.mark.parametrize("style", list(sk.FLOW_STYLES) + ["nonsense", None])
@pytest.mark.parametrize("n", [2, 3, 4, 5, 6, 7])
def test_every_flow_style_renders_at_every_size(style, n):
    for long, branch in ((False, False), (True, False), (True, True)):
        img = render("diagram", _flow(n, style, long=long, branch=branch), 30.0, 8.0, "paper", captions=True)
        assert changed(img, blank("paper", 30.0, 8.0)) > 0.01


def test_unknown_style_and_accent_fall_back_to_the_default_look():
    for stype, make, default in (("bullets", _bullets, "rail"), ("diagram", _flow, "cards")):
        a = render(stype, make(3, "no-such-style", "no-such-accent"), 7.0, 8.0, "sunrise")
        b = render(stype, make(3, default), 7.0, 8.0, "sunrise")
        c = render(stype, make(3), 7.0, 8.0, "sunrise")
        assert changed(a, b) == 0 and changed(b, c) == 0


def test_styles_really_differ():
    frames = {s: render("bullets", _bullets(4, s), 7.0, 8.0, "midnight") for s in sk.LIST_STYLES}
    for a, b in itertools.combinations(sk.LIST_STYLES, 2):
        assert changed(frames[a], frames[b], 16) > 0.02, (a, b)
    frames = {s: render("diagram", _flow(4, s), 7.0, 8.0, "midnight") for s in sk.FLOW_STYLES}
    for a, b in itertools.combinations(sk.FLOW_STYLES, 2):
        assert changed(frames[a], frames[b], 16) > 0.02, (a, b)


def test_accent_recolours():
    a = render("bullets", _bullets(3, "icons", "teal"), 7.0, 8.0, "paper")
    b = render("bullets", _bullets(3, "icons", "violet"), 7.0, 8.0, "paper")
    assert changed(a, b, 16) > 0.003


@pytest.mark.parametrize("theme", list(THEMES))
def test_all_accents_render_on_all_themes(theme):
    for acc in sk.ACCENT_CHOICES:
        render("bullets", _bullets(3, "cards", acc), 7.0, theme and 8.0, theme)
        render("diagram", _flow(3, "cards", acc), 7.0, 8.0, theme)


# ------------------------------------------------------------------ timing: cues drive the reveals
@pytest.mark.parametrize("stype,make,styles", [("bullets", _bullets, sk.LIST_STYLES), ("diagram", _flow, sk.FLOW_STYLES)])
def test_cues_drive_reveals_and_end_state_is_complete(stype, make, styles):
    for style in styles:
        props = make(4, style, cues=[1.0, 3.0, 5.0, 7.0])
        f_before = render(stype, props, 2.0, 9.0)      # only the first part is up
        f_mid = render(stype, props, 4.0, 9.0)
        f_end = render(stype, props, 8.9, 9.0)
        assert changed(f_before, f_mid, 16) > 0.004, style
        assert changed(f_mid, f_end, 16) > 0.004, style
        late = render(stype, props, 8.9, 9.0), render(stype, props, 12.0, 9.0)
        assert changed(*late, 16) < 0.01, style            # nothing moves much after the reveals (only a faint pulse)


@pytest.mark.parametrize("stype,make", [("bullets", _bullets), ("diagram", _flow)])
def test_first_second_is_never_empty_even_when_the_first_cue_is_late(stype, make):
    props = make(3, cues=[6.0, 7.0, 8.0])
    img = render(stype, props, 1.3, 10.0, "midnight")
    assert changed(img, blank("midnight", 1.3, 10.0)) > 0.003


def test_cue_semantics_unchanged():
    props = plan_mod.sanitize_props("bullets", _bullets(3))
    words = [("first", 1.0, 1.2), ("point", 1.2, 1.4), ("number", 1.4, 1.6), ("second", 3.0, 3.2), ("point", 3.2, 3.4), ("number", 3.4, 3.6)]
    info = sync.apply("bullets", props, words, 8.0)
    assert info["items"] == 3 and len(props["cues"]) == 3 and props["cues"][1] > props["cues"][0]
    dg = plan_mod.sanitize_props("diagram", _flow(3))
    assert sync.diagram_order(dg) == ["Step 1", "Step 2", "Step 3"]
    sync.apply("diagram", dg, [], 8.0)
    assert len(dg["cues"]) == 3


# ------------------------------------------------------------------ safe area
def _ink_box(img, base):
    d = np.abs(np.asarray(img.convert("RGB"), np.int16) - np.asarray(base.convert("RGB"), np.int16)).max(axis=2) > 90
    ys, xs = np.where(d)
    if not len(xs):
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())


@pytest.mark.parametrize("theme", ["midnight", "paper"])
def test_content_stays_inside_the_safe_area(theme):
    cases = []
    for style in sk.LIST_STYLES:
        for n in (2, 5, 6):
            for long in (False, True):
                cases.append(("bullets", _bullets(n, style, long=long)))
    for style in sk.FLOW_STYLES:
        for n in (2, 4, 7):
            for long in (False, True):
                cases.append(("diagram", _flow(n, style, long=long, branch=n >= 4)))
    for stype, props in cases:
        img = render(stype, props, 8.9, 9.0, theme, captions=True)
        box = _ink_box(img, blank(theme, 8.9, 9.0))
        assert box is not None
        x0, y0, x1, y1 = box
        assert x0 >= 90 and x1 <= 1830, (stype, props.get("style"), box)
        assert y0 >= 40 and y1 <= 810, (stype, props.get("style"), box)        # the caption band starts at 800
