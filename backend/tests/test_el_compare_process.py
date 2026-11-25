"""versus, table, ranking, matrix, flowchart, sequence."""
import copy
import random

import pytest

from tests.element_utils import changed, render
from engine.scenes import ELEMENTS, SCENES

NAMES = ["versus", "table", "ranking", "matrix", "flowchart", "sequence"]


def el(name):
    return ELEMENTS[name]


def clean(name, i=0):
    return el(name).sanitize(copy.deepcopy(el(name).samples[i]))


def test_all_six_are_registered_in_the_right_families():
    fam = {n: el(n).family for n in NAMES}
    assert fam == {"versus": "Compare", "matrix": "Compare", "table": "Lists", "ranking": "Lists", "flowchart": "Process", "sequence": "Process"}


# ---------------------------------------------------------------- versus
def test_versus_limits_and_fairness():
    p = el("versus").sanitize({"a": {"name": "A" * 50, "tagline": "t" * 90}, "b": {"name": "B"}, "verdict": "v" * 200,
                               "rows": [{"label": "L" * 40, "a": "x" * 60, "b": "y"}] * 7})
    assert len(p["a"]["name"]) == 24 and len(p["a"]["tagline"]) == 40 and len(p["rows"]) == 5 and len(p["verdict"]) == 80
    assert len(p["rows"][0]["label"]) == 24 and len(p["rows"][0]["a"]) == 30 and "winner" not in p
    assert el("versus").sanitize({**p, "winner": "B"})["winner"] == "b"
    assert "winner" not in el("versus").sanitize({**p, "winner": "both"})
    with pytest.raises(ValueError):
        el("versus").sanitize({"a": {"name": "A"}, "b": {"name": "B"}, "rows": [{"label": "x", "a": "1", "b": "2"}]})


def test_versus_anchors_are_the_row_labels_and_winner_shows_up_at_the_end():
    p = clean("versus", 1)
    assert el("versus").anchors(p) == [r["label"] for r in p["rows"]]
    no_win = {k: v for k, v in p.items() if k != "winner"}
    assert changed(render("versus", p, 7.9, 8.0), render("versus", no_win, 7.9, 8.0)) > 0.0005


# ---------------------------------------------------------------- table
def test_table_pads_rows_and_maps_the_highlight():
    p = el("table").sanitize({"columns": ["a", "b", "c"], "rows": [["1"], [], ["x", "y", "z", "extra"], ["p", "q", "r"]], "highlight": 3})
    assert p["rows"] == [["1", "", ""], ["x", "y", "z"], ["p", "q", "r"]] and p["highlight"] == {"row": 2}
    assert "highlight" not in el("table").sanitize({"columns": ["a", "b"], "rows": [["1", "2"], ["3", "4"]], "highlight": 9})
    assert el("table").sanitize({"columns": ["a", "b"], "rows": [["1", "2"], ["3", "4"]], "highlight": {"row": 1, "col": 1}})["highlight"] == {"row": 1, "col": 1}
    with pytest.raises(ValueError):
        el("table").sanitize({"columns": ["a"], "rows": [["1"], ["2"]]})


def test_table_highlight_pulses_then_stays():
    p = clean("table", 0)
    assert changed(render("table", p, 7.9, 8.0), render("table", {k: v for k, v in p.items() if k != "highlight"}, 7.9, 8.0)) > 0.001


# ---------------------------------------------------------------- ranking
def test_ranking_counts_down_from_the_last_item():
    p = clean("ranking", 0)
    labels = [i["label"] for i in p["items"]]
    assert el("ranking").anchors(p) == labels[::-1]
    early = render("ranking", p, 1.2, 8.0)
    end = render("ranking", p, 8.0, 8.0)
    assert changed(early, end) > 0.03
    with pytest.raises(ValueError):
        el("ranking").sanitize({"items": [{"label": "a"}, {"label": "b"}]})
    assert len(el("ranking").sanitize({"items": [{"label": str(i)} for i in range(12)]})["items"]) == 7


def test_ranking_honours_narration_cues_in_countdown_order():
    p = clean("ranking", 0)
    p["cues"] = [0.5, 1.5, 2.5, 3.5]
    # at 2.0 s only the last two items are out, so #1 (revealed last) must not be showing yet
    assert changed(render("ranking", p, 2.0, 8.0), render("ranking", p, 4.5, 8.0)) > 0.02


# ---------------------------------------------------------------- matrix
def test_matrix_clamps_and_drops_bad_items():
    p = el("matrix").sanitize({"x_axis": {"low": "a", "high": "b"}, "y_axis": {"low": "c", "high": "d"},
                               "items": [{"label": "ok", "x": 3, "y": -1}, {"label": "bad", "x": "no", "y": 0.5}, {"label": "two", "x": 0.5, "y": 0.5}]})
    assert [(i["x"], i["y"]) for i in p["items"]] == [(1.0, 0.0), (0.5, 0.5)]
    with pytest.raises(ValueError):
        el("matrix").sanitize({"x_axis": {"low": "a"}, "y_axis": {"low": "c", "high": "d"}, "items": [{"label": "a", "x": 0, "y": 0}] * 3})


def test_matrix_labels_do_not_collide_even_for_close_items():
    from engine.scenes.elements.compare_process import _matrix_layout, _key
    p = clean("matrix", 1)
    dots, labels = _matrix_layout(_key(p["items"], p.get("quadrants")), 200, 714)
    rects = [(x, y, x + w, y + 42) for x, y, w in labels]
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            a, b = rects[i], rects[j]
            assert not (min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])), (p["items"][i], p["items"][j])


# ---------------------------------------------------------------- flowchart
def test_flowchart_orders_nodes_in_flow_order_and_survives_cycles():
    raw = {"nodes": [{"id": "c", "label": "Third"}, {"id": "a", "label": "First", "kind": "start"}, {"id": "b", "label": "Second"}],
           "edges": [["a", "b"], ["b", "c"], ["c", "a", "retry"]]}
    p = el("flowchart").sanitize(raw)
    assert [n["label"] for n in p["nodes"]] == ["First", "Second", "Third"] and el("flowchart").anchors(p) == ["First", "Second", "Third"]
    render("flowchart", p, 6.0, 8.0)


def test_flowchart_degrades_without_edges_and_rejects_too_few_nodes():
    p = el("flowchart").sanitize({"nodes": [{"id": "1", "label": "a"}, {"id": "2", "label": "b"}, {"id": "3", "label": "c"}], "edges": "garbage"})
    assert p["edges"] == [["1", "2"], ["2", "3"]]
    with pytest.raises(ValueError):
        el("flowchart").sanitize({"nodes": [{"id": "1", "label": "a"}, {"id": "2", "label": "b"}], "edges": [["1", "2"]]})


def test_flowchart_random_graphs_are_idempotent_and_always_draw():
    rnd = random.Random(7)
    for _ in range(40):
        n = rnd.randint(3, 8)
        nodes = [{"id": f"n{i}", "label": f"Step number {i}", "kind": rnd.choice(["start", "step", "decision", "end"])} for i in range(n)]
        edges = [[f"n{rnd.randrange(n)}", f"n{rnd.randrange(n)}", rnd.choice(["", "yes", "no"])] for _ in range(rnd.randint(2, 12))]
        try:
            p = el("flowchart").sanitize({"nodes": nodes, "edges": edges})
        except ValueError:
            continue
        assert el("flowchart").sanitize(copy.deepcopy(p)) == p
        render("flowchart", p, 7.0, 8.0)


# ---------------------------------------------------------------- sequence
def test_sequence_drops_messages_between_unknown_actors():
    p = el("sequence").sanitize({"actors": ["A", "B"], "messages": [{"from": "a", "to": "B", "label": "hi"}, {"from": "A", "to": "Z", "label": "lost"},
                                                                       {"from": "B", "to": "A", "label": "yo", "reply": True}, {"from": "A", "to": "B", "label": "bye"}]})
    assert [m["label"] for m in p["messages"]] == ["hi", "yo", "bye"] and p["messages"][1]["reply"] is True and el("sequence").anchors(p) == ["hi", "yo", "bye"]
    with pytest.raises(ValueError):
        el("sequence").sanitize({"actors": ["A"], "messages": []})


# ---------------------------------------------------------------- everything ends complete
@pytest.mark.parametrize("name", NAMES)
def test_the_end_state_is_more_complete_than_the_middle(name):
    for i in range(2):
        p = clean(name, i)
        assert changed(render(name, p, 3.0, 8.0), render(name, p, 7.9, 8.0)) > 0.0003 or name in ("table",)
        cues = el(name).cues(p, 8.0)
        assert cues == sorted(cues) and len(cues) >= 3 - (name == "versus")


# ---------------------------------------------------------------- native layouts for 9:16, 1:1, 4:5
ASPECTS = ["9:16", "1:1", "4:5"]


def test_all_six_are_tagged_for_every_aspect():
    for n in NAMES:
        assert el(n).formats == ("16:9", "9:16", "1:1", "4:5")


def _worst_case(name):
    long = "Extraordinarily long label text"
    if name == "versus":
        return {"a": {"name": "Extraordinarily Long Name", "tagline": "t" * 40}, "b": {"name": "Supercalifragilistic"},
                "rows": [{"label": long, "a": "A fairly long value text here ok", "b": "Another quite long value text"}] * 5, "verdict": "v " * 40, "winner": "b"}
    if name == "table":
        return {"title": "A long title for a table that wraps over", "columns": ["Column one", "Column two", "Column 3", "Column four"],
                "rows": [["Supercalifragilis", "Long cell text here", "$1,250,000.00", "Another longer one"]] * 6, "highlight": {"row": 3, "col": 2}}
    if name == "ranking":
        return {"title": "A long title for a ranking", "items": [{"label": long + str(i), "value": "1,234,567 km", "note": "A note that is rather long and sits below"} for i in range(7)]}
    if name == "matrix":
        return {"title": "A long title for a matrix", "x_axis": {"low": "Extremely cheap low", "high": "Extremely high cost"}, "y_axis": {"low": "Extremely basic", "high": "Extremely high value"},
                "quadrants": ["Top left label long"] * 4, "items": [{"label": long + str(i), "x": (i * 0.37) % 1, "y": (i * 0.61) % 1} for i in range(8)]}
    if name == "flowchart":
        return {"title": "A long title", "nodes": [{"id": str(i), "label": long + str(i), "kind": "decision" if i in (2, 7) else "step"} for i in range(1, 9)],
                "edges": [["1", "2"], ["2", "3", "yes"], ["2", "4", "no"], ["3", "5"], ["4", "5"], ["5", "6"], ["6", "7"], ["7", "8", "done"]]}
    return {"title": "A long title", "actors": ["Extraordinarily Long", "Another Long Actor", "Third Long Actor", "Fourth Long Actor"],
            "messages": [{"from": "Extraordinarily Long" if i % 2 == 0 else "Fourth Long Actor", "to": "Another Long Actor", "label": "A really long message label that goes on and on"} for i in range(8)]}


@pytest.mark.parametrize("aspect", ASPECTS)
@pytest.mark.parametrize("name", NAMES)
def test_worst_case_props_stay_inside_the_content_box(name, aspect):
    """Maximum counts and the longest labels: nothing is drawn below the content box (the caption band) or outside the frame."""
    import numpy as np
    from engine.frame import Frame
    p = el(name).sanitize(_worst_case(name))
    fr = Frame.parse(aspect, "720p")
    im = render(name, p, 7.9, 8.0, "midnight", captions=True, draft=False, aspect=aspect, resolution="720p")
    blank = _blank_like(aspect)
    diff = np.abs(np.asarray(im.convert("RGB"), np.int16) - np.asarray(blank, np.int16)).max(axis=2) > 40
    ys, xs = np.nonzero(diff)
    assert len(ys), "blank"
    k = im.height / fr.H
    x0, y0, x1, y1 = fr.box(True)
    assert ys.max() <= (y1 + 24) * k, (ys.max() / k, y1)
    assert xs.min() >= (x0 - 40) * k and xs.max() <= (x1 + 40) * k


def _blank_like(aspect):
    from tests.element_utils import blank as _b
    from engine import scenes
    from engine.frame import Frame
    from tests.element_utils import render as _r
    scenes.SCENES["__blank__"] = (lambda *a, **k: None, lambda p, d: [])
    try:
        return _r("__blank__", {}, 7.9, 8.0, "midnight", captions=True, draft=False, aspect=aspect, resolution="720p")
    finally:
        scenes.SCENES.pop("__blank__", None)


@pytest.mark.parametrize("aspect", ASPECTS)
def test_versus_winner_and_verdict_show_in_every_shape(aspect):
    p = clean("versus", 1)
    no_win = {k: v for k, v in p.items() if k != "winner"}
    a = render("versus", p, 7.9, 8.0, aspect=aspect, captions=True)
    b = render("versus", no_win, 7.9, 8.0, aspect=aspect, captions=True)
    assert changed(a, b) > 0.0005


@pytest.mark.parametrize("aspect", ASPECTS)
def test_table_highlight_and_reveal_in_every_shape(aspect):
    p = clean("table", 0)
    nohl = {k: v for k, v in p.items() if k != "highlight"}
    assert changed(render("table", p, 7.9, 8.0, aspect=aspect, captions=True), render("table", nohl, 7.9, 8.0, aspect=aspect, captions=True)) > 0.001
    assert changed(render("table", p, 0.5, 8.0, aspect=aspect, captions=True), render("table", p, 7.9, 8.0, aspect=aspect, captions=True)) > 0.02


@pytest.mark.parametrize("aspect", ASPECTS)
def test_ranking_countdown_cues_in_every_shape(aspect):
    p = clean("ranking", 0)
    p["cues"] = [0.5, 1.5, 2.5, 3.5]
    assert changed(render("ranking", p, 2.0, 8.0, aspect=aspect, captions=True), render("ranking", p, 4.5, 8.0, aspect=aspect, captions=True)) > 0.02


def test_flowchart_tall_layout_is_top_to_bottom_in_vertical_frames():
    from engine.scenes.elements.compare_process import _flow_tall_layout, _key
    p = clean("flowchart", 1)
    lay = _flow_tall_layout(_key(p["nodes"], p["edges"]), 200, 1400, 72, 1008, True)
    assert lay["mode"] == "td"
    xs = [v[0] for v in lay["pos"].values()]
    assert min(v[0] - v[2] / 2 for v in lay["pos"].values()) >= 72 - 1 and max(v[0] + v[2] / 2 for v in lay["pos"].values()) <= 1008 + 1


def test_matrix_axis_label_is_rotated_text_inside_the_gutter():
    from engine.scenes.elements.compare_process import _vtext
    from engine.canvas import Canvas
    cv = Canvas(200, 400, ss=1)
    _vtext(cv, 100, 200, "Hello", "semibold", 30, (255, 255, 255, 255))
    import numpy as np
    a = np.asarray(cv.im).max(axis=2) > 0
    ys, xs = np.nonzero(a)
    assert (ys.max() - ys.min()) > (xs.max() - xs.min())            # taller than wide: turned
