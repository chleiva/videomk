"""The whiteboard element (docs/WHITEBOARD.md): the scene contract, sanitize and its fallbacks, every aspect, determinism (a frame depends only on its time), layout rules."""
import os

import numpy as np
import pytest

os.environ["WHITEBOARD_DIR"] = os.path.join(os.path.dirname(__file__), "fixtures", "whiteboard")   # three library packages: sun, plant_sprout, piggy_bank

from tests.element_utils import changed, render  # noqa: E402
from engine.scenes import ELEMENTS, registry  # noqa: E402
from engine.scenes.elements import whiteboard as wbe  # noqa: E402
from engine.whiteboard import core, hand, library, spec  # noqa: E402

EL = ELEMENTS["whiteboard"]
ASPECTS = ("16:9", "9:16", "1:1", "4:5")


def props(k=0, cues=True):
    p = EL.sanitize(EL.samples[k])
    if cues:
        p["cues"] = [1.0 + 1.4 * i for i in range(len(EL.anchors(p)))]
    return p


def ink(im):
    """How many pixels are marker ink or colour (not paper, not the marker's white barrel)."""
    a = np.asarray(im.convert("RGB"), np.int16)
    return int(((a.min(axis=2) < 150) | (a.max(axis=2) - a.min(axis=2) > 60)).sum())


def test_registered_hidden_and_complete():
    assert registry.FAILED == {}
    assert EL.hidden is True and "whiteboard" not in registry.docs_by_family()
    assert set(EL.formats) == set(ASPECTS) and EL.anchors is not None and EL.fallback is not None
    assert not any(m in open(core.__file__).read() + open(spec.__file__).read() + open(hand.__file__).read() for m in ("import scipy", "from scipy", "import cv2"))   # the engine layer has neither


def test_sanitize_is_idempotent_and_keeps_only_known_things():
    p = EL.sanitize(EL.samples[0])
    assert EL.sanitize(p) == p
    assert [it["id"] for it in p["items"]] == ["title", "sun", "plant", "ray", "sugar", "ring"]
    assert all(it.get("say") for it in p["items"] if it.get("draw") or it.get("write"))
    q = EL.sanitize({"items": [{"id": "A b!", "draw": "Sun", "zone": "nowhere", "size": "huge", "ink": "pink", "x": 5}, {"write": "  hi  there ", "near": "ab"},
                               {"connect": "zigzag", "from": "ab", "to": "ghost"}, {"mark": "circle", "on": "ghost"}, {"mark": "underline", "on": "ab"}, "junk", {"nothing": 1}]})
    kinds = [next(k for k in ("draw", "write", "connect", "mark") if k in it) for it in q["items"]]
    assert kinds == ["draw", "write", "mark"]                      # the arrow and the mark that point at nothing are dropped
    assert q["items"][0] == {"id": "ab", "draw": "sun", "zone": "centre", "size": "l", "say": q["items"][0].get("say", "")} or q["items"][0]["draw"] == "sun"
    assert "x" not in q["items"][0] and "ink" not in q["items"][0]
    for bad in ({}, {"items": []}, {"items": [{"connect": "arrow", "from": "a", "to": "b"}]}, None, {"items": "sun"}):
        with pytest.raises(ValueError):
            EL.sanitize(bad)


def test_unknown_drawing_becomes_a_written_label(monkeypatch):
    monkeypatch.setattr(library, "search", lambda phrase, k=3, embed=None: [])
    p = EL.sanitize({"items": [{"id": "g", "draw": "electric guitar", "zone": "left", "say": "guitar"}]})
    assert p["items"][0]["write"] == "electric guitar" and p["items"][0]["boxed"] is True and "draw" not in p["items"][0]
    monkeypatch.setattr(library, "search", lambda phrase, k=3, embed=None: [{"id": "piggy_bank", "score": 0.5, "title": "Piggy bank"}])
    assert EL.sanitize({"items": [{"draw": "saving money", "zone": "left"}]})["items"][0]["draw"] == "piggy_bank"       # by meaning
    assert EL.sanitize({"items": [{"draw": "Piggy Bank", "zone": "left"}]})["items"][0]["draw"] == "piggy_bank"          # by name, no model call


def test_limits():
    many = {"items": [{"id": f"w{i}", "write": f"word {i}", "zone": "centre"} for i in range(30)]}
    p = EL.sanitize(many)
    assert len(p["items"]) == wbe.MAX_SOLID
    long = EL.sanitize({"items": [{"write": "x" * 500, "zone": "top"}]})
    assert len(long["items"][0]["write"]) <= wbe.MAX_TEXT


@pytest.mark.parametrize("aspect", ASPECTS)
def test_draws_progressively_in_every_aspect(aspect):
    p = props()
    start, mid, end = (render("whiteboard", p, t, dur=10.0, aspect=aspect, captions=True) for t in (0.05, 4.0, 9.9))
    assert ink(start) < 0.25 * ink(mid)               # nearly empty at the start, drawn as the narration goes
    assert ink(mid) > 2000 and ink(end) > 2000
    assert changed(start, end) > 0.002 and changed(mid, end) > 0.002


def test_a_frame_depends_only_on_its_time():
    """Chunks render their own frames in their own containers: the same time must give the same picture whatever was drawn before."""
    p = props()
    a = render("whiteboard", p, 5.3, dur=10.0)
    wbe._STATE.clear()                                # a fresh container
    render("whiteboard", p, 9.0, dur=10.0)            # ... that drew a later frame first
    b = render("whiteboard", p, 5.3, dur=10.0)
    assert np.array_equal(np.asarray(a), np.asarray(b))
    wbe._STATE.clear()
    c = render("whiteboard", p, 5.3, dur=10.0)
    assert np.array_equal(np.asarray(a), np.asarray(c))


def test_cached_frame_equals_a_full_recomposite():
    from engine.frame import Frame
    from engine.scenes.base import SceneCtx

    board, cam, geo, _ = wbe.build(props(), 10.0, SceneCtx(frame=Frame.parse("16:9", "1080p"), captions=True), 960, 540)
    for t in (0.7, 2.2, 4.9, 6.1, 9.5):
        view = wbe.full_view(cam.at(t), geo)
        fast = np.asarray(board.frame(t, view, (960, 540), tip=False)).astype(int)
        keep_items, keep_fin = board.items, board._finish
        board.items, board._finish, board._cache, board._still = [(0, board.RH, 0, board.RW, -1e9, 1e9)], np.array([1e9]), (-1, None), (None, None)
        slow = np.asarray(board.frame(t, view, (960, 540), tip=False)).astype(int)
        board.items, board._finish, board._cache, board._still = keep_items, keep_fin, (-1, None), (None, None)
        assert np.abs(fast - slow).max() == 0


def test_layout_keeps_everything_on_the_board_and_apart():
    from engine.frame import Frame
    from engine.scenes.base import SceneCtx

    for aspect in ASPECTS:
        for k in (0, 1):
            _, _, geo, rep = wbe.build(props(k), 10.0, SceneCtx(frame=Frame.parse(aspect, "1080p"), captions=True), 480, 480)
            W, H = geo["units"]
            assert not [w for w in rep["warnings"] if "overlap" in w or "leaves the board" in w], (aspect, k, rep["warnings"])
            for iid, (x0, y0, x1, y1) in rep["boxes"].items():
                if rep["kinds"][iid] in ("draw", "write"):
                    assert -1 <= x0 < x1 <= W + 1 and -1 <= y0 < y1 <= H + 1, (aspect, iid)


def test_items_finish_inside_the_scene_and_on_their_words():
    from engine.frame import Frame
    from engine.scenes.base import SceneCtx

    p = props()
    board, cam, _, rep = wbe.build(p, 10.0, SceneCtx(frame=Frame.parse("16:9", "1080p"), captions=True), 480, 270)
    assert max(it[5] for it in board.items) <= 10.0
    assert cam.moves == [] and rep["camera_moves"] == 0          # one framing per board: the camera never moves inside a scene
    short, _, _, rep2 = wbe.build(p, 4.0, SceneCtx(frame=Frame.parse("16:9", "1080p"), captions=True), 480, 270)       # a beat shorter than its cues: compressed, never cut off
    assert max(it[5] for it in short.items) <= 4.0


def test_a_missing_package_is_written_not_fatal(monkeypatch):
    p = props()
    monkeypatch.setattr(library, "load", lambda oid: (_ for _ in ()).throw(KeyError(oid)))
    wbe._STATE.clear()
    im = render("whiteboard", p, 9.9, dur=10.0)
    assert ink(im) > 1000                              # the labels and the boxed names are still there
    wbe._STATE.clear()


def test_handwriting_tables_cover_english_and_spanish():
    for h in ("neat", "casual"):
        for ch in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789áéíóúüñÁÉÍÓÚÑ¿¡?!%$=+-()":
            g = hand.glyph(ch, h)
            assert not g.get("missing") and g["strokes"], (h, ch)
    blk = hand.layout("año ^{2} \\frac{1}{2} -> ¿sí?", "neat", 120.0, max_width=900)
    assert len(blk["words"]) == 5 and all(w["strokes"] for w in blk["words"])
    assert hand.layout("one two three four five six seven", "neat", 150.0, max_width=500, max_height=260)["size"] < 150.0     # shrinks to fit its zone


# ----------------------------------------------------------------------------- charts drawn by hand
def test_a_chart_is_drawn_in_the_look():
    p = EL.sanitize({"items": [{"id": "t", "write": "Growth", "zone": "top", "say": "growth"},
                               {"id": "c", "chart": "bars", "values": [5, 10, 16, 23], "labels": ["1", "2", "3", "4"], "zone": "centre", "say": "bigger"},
                               {"id": "l", "chart": "line", "values": [1, 2, 4], "zone": "right", "say": "rises"}, {"id": "b", "mark": "box", "on": "c"}]})
    assert [it.get("chart") for it in p["items"]] == [None, "bars", "line", None] and EL.sanitize(p) == p
    p["cues"] = [1.0, 3.0, 5.0]
    wbe._STATE.clear()
    assert ink(render("whiteboard", p, 9.9, dur=10.0)) > 3 * ink(render("whiteboard", p, 1.4, dur=10.0))
    for bad in ({"chart": "bars", "values": [1]}, {"chart": "bars", "values": ["a", "b"]}, {"chart": "bars", "values": [-1, 2]}, {"chart": "bars", "values": [0, 0]}):
        with pytest.raises(ValueError):
            EL.sanitize({"items": [bad]})                # an unusable chart is dropped; a board with nothing else is refused


# ----------------------------------------------------------------------------- one big board: the pan from the previous panel, the last pull-back
def _linked(n=3):
    from engine import whiteboard_policy as wp

    scenes = [{"id": f"s{k}", "type": "whiteboard", "duration": 10.0, "transition": "fade", "props": dict(props(k % 2))} for k in range(n)]
    assert wp.link(scenes) == n
    return scenes


def test_consecutive_boards_are_panels_of_one_board():
    scenes = _linked(3)
    assert [s["transition"] for s in scenes] == ["fade", "none", "none"]                # the camera travels instead of a crossfade
    assert [s["props"].get("panel") for s in scenes] == [[0, 3], [1, 3], [2, 3]]
    assert "prev" not in scenes[0]["props"]
    assert scenes[1]["props"]["prev"]["items"] == [{k: v for k, v in it.items() if k not in ("say", "at")} for it in scenes[0]["props"]["items"]]      # the board as it was left, marks added for the pen's rests included
    assert len(scenes[2]["props"]["wall"]) == 2 and "wall" not in scenes[1]["props"]
    assert all(s["props"]["lib"] for s in scenes)                                           # the library version is part of the segment hash
    from engine import whiteboard_policy as wp

    alone = [{"id": "a", "type": "whiteboard", "duration": 8.0, "transition": "fade", "props": dict(props())}, {"id": "t", "type": "title", "duration": 3.0, "props": {"title": "x"}}]
    assert wp.link(alone) == 0 and alone[0]["transition"] == "fade" and "panel" not in alone[0]["props"]
    again = [dict(s, props=dict(s["props"])) for s in scenes]
    wp.link(again)
    assert [s["props"] for s in again] == [s["props"] for s in scenes]                  # linking twice (an edit rebuilds the timeline) changes nothing


def test_the_pan_shows_the_previous_panel_then_only_this_one():
    scenes = _linked(2)
    p0, p1 = scenes[0]["props"], scenes[1]["props"]
    wbe._STATE.clear()
    wbe._STILLS.clear()
    start = render("whiteboard", p1, 0.0, dur=10.0)                # the previous panel, finished, fills the frame
    prev_end = render("whiteboard", {k: v for k, v in p0.items() if k != "panel"}, 9.99, dur=10.0)
    assert changed(start, prev_end) < 0.02
    mid = render("whiteboard", p1, wbe.PAN_S / 2, dur=10.0)
    assert ink(mid) > 300 and changed(mid, start) > 0.002
    after = render("whiteboard", p1, wbe.PAN_S + 0.01, dur=10.0)
    assert ink(after) < 0.2 * ink(render("whiteboard", p1, 9.5, dur=10.0))    # after the pan the previous board is gone, and nothing was drawn while the camera travelled (only the marker is arriving)


def test_the_last_panel_pulls_back_over_the_whole_board():
    scenes = _linked(3)
    last = scenes[2]["props"]
    wbe._STATE.clear()
    wbe._STILLS.clear()
    before = render("whiteboard", last, 12.0 - wbe.WALL_S - 0.05, dur=12.0)
    end = render("whiteboard", last, 11.9, dur=12.0)
    assert changed(before, end) > 0.01 and ink(end) > 1000
    a = np.asarray(end.convert("L"), np.int16)
    h, w = a.shape
    assert (a[: h // 2, : w // 3] < 150).sum() > 50 and (a[: h // 2, w // 3: 2 * w // 3] < 150).sum() > 50      # the first two panels are in the picture too
    wbe._STATE.clear()
    wbe._STILLS.clear()
    assert np.array_equal(np.asarray(end), np.asarray(render("whiteboard", last, 11.9, dur=12.0)))               # ... and a fresh container draws the same frame


def test_chunks_agree_at_any_split():
    """A scene rendered by two containers (a chunk boundary inside a run, or a 4K piece) is frame for frame what one container renders."""
    scenes = _linked(2)
    p1 = scenes[1]["props"]
    times = [0.2, 0.6, 2.0, 5.0, 9.0]
    wbe._STATE.clear(); wbe._STILLS.clear()
    one = [np.asarray(render("whiteboard", p1, t, dur=10.0)) for t in times]
    two = []
    for t in reversed(times):
        wbe._STATE.clear(); wbe._STILLS.clear()
        two.append(np.asarray(render("whiteboard", p1, t, dur=10.0)))
    assert all(np.array_equal(a, b) for a, b in zip(one, reversed(two)))


def test_memory_is_bounded():
    scenes = _linked(3)
    for s in scenes:
        render("whiteboard", s["props"], 9.5, dur=10.0)
        render("whiteboard", s["props"], 0.1, dur=10.0)
    assert set(wbe._STATE) <= {"key", "board", "cam", "geo"}       # one built board at a time
    assert len(wbe._STILLS) <= wbe.WALL_MAX + 1


# ----------------------------------------------------------------------------- one framing, sizes, shared boards, arrows, timing (docs/WHITEBOARD.md "Quality")
def _ctx(aspect="16:9"):
    from engine.frame import Frame
    from engine.scenes.base import SceneCtx

    return SceneCtx(frame=Frame.parse(aspect, "1080p"), captions=True)


def _stub(oid):
    if oid not in ("sun", "plant_sprout", "piggy_bank"):
        raise KeyError(oid)
    return {"w": 1000.0, "h": 1000.0, "strokes": [], "draw_s": 1.2, "fill_colours": []}


@pytest.mark.parametrize("aspect", ASPECTS)
def test_one_framing_shows_the_whole_board_and_nothing_is_tiny(aspect):
    items = [{"id": "t", "write": "A fairly long title for the board", "zone": "top-row", "size": "l", "say": "a"}, {"id": "s", "draw": "sun", "zone": "left", "say": "b"},
             {"id": "l", "write": "a tiny label here", "near": "s", "side": "below", "size": "xs", "tool": "pen", "say": "c"}, {"id": "n", "write": "350 000", "zone": "right", "size": "xl", "say": "d"},
             {"id": "c", "chart": "bars", "values": [1, 2, 3], "labels": ["a", "b", "c"], "zone": "bottom", "say": "e"}]
    _, cam, geo, rep = wbe.build({"items": items, "cues": [1, 3, 5, 7, 9]}, 12.0, _ctx(aspect), 480, 480, load=_stub, layout_only=True)
    vx, vy, vw = cam.at(0.0)
    assert cam.at(0.0) == cam.at(6.0) == cam.at(11.9)                             # still from the first frame to the last
    vh = vw * geo["box"][3] / geo["box"][2]
    for iid, (x0, y0, x1, y1) in rep["boxes"].items():                            # everything the board will ever hold is inside that one view
        assert vx - 2 <= x0 and x1 <= vx + vw + 2 and vy - 2 <= y0 and y1 <= vy + vh + 2, (aspect, iid)
    assert geo["units"][0] / spec.MAX_ZOOM - 1 <= vw <= geo["units"][0] + 1
    assert min(rep["text_sizes"].values()) >= spec.TEXT_MIN * 0.95                # no handwriting under the floor, whatever size was asked
    px = geo["box"][2] / vw                                                       # design px per board unit in this framing
    assert min(rep["text_sizes"].values()) * px >= 0.044 * 1080                   # ... which is at least 4.4 % of the frame's shorter side on screen
    assert rep["text_lines"]["n"] == 1                                            # a number is written smaller on one line rather than wrapped
    assert not rep["overlaps"]


def test_rows_share_the_height_by_what_they_hold():
    rows, cols = spec.weights([{"id": "t", "write": "Title", "zone": "top"}, {"id": "s", "draw": "sun", "zone": "left"}, {"id": "p", "draw": "sun", "zone": "centre"}])
    assert rows[1] > rows[0] > rows[2] and cols == [1.0, 1.0, spec.COL_EMPTY]    # drawings > a title > an empty row; the empty column gives up half its width
    L = spec.Layout(3000, 1200, rows, cols)
    assert L.rect((0, 1, 0, 1))[3] - L.rect((0, 1, 0, 1))[1] > L.rect((0, 0, 0, 0))[3] - L.rect((0, 0, 0, 0))[1]
    assert abs(L.ys[3] - 1200) < 1e-6 and abs(L.xs[3] - 3000) < 1e-6


def test_an_arrow_curves_round_what_is_in_its_way():
    items = [{"id": "a", "draw": "sun", "zone": "left", "say": "a"}, {"id": "mid", "draw": "piggy_bank", "zone": "centre", "say": "b"}, {"id": "c", "draw": "plant_sprout", "zone": "right", "say": "c"},
             {"id": "ar", "connect": "arrow", "from": "a", "to": "c"}, {"id": "dash", "connect": "dashed", "from": "a", "to": "c"}]
    _, _, _, rep = wbe.build({"items": items, "cues": [1, 3, 5]}, 10.0, _ctx(), 480, 270, load=_stub, layout_only=True)
    assert rep["crossed"] == []
    m = rep["boxes"]["mid"]
    for arrow in ("ar", "dash"):                                                  # the straight way runs through the middle drawing: both go over or under it
        b = rep["boxes"][arrow]
        assert b[1] < m[1] - 10 or b[3] > m[3] + 10, (arrow, b, m)
    L = spec.Layout(3000, 1200)
    line = np.stack([np.linspace(100, 2900, 50), np.full(50, 600.0)], 1)
    assert spec._hits(line, [(1400, 500, 1600, 700)], L) > 0.05 and spec._hits(line, [(1400, 100, 1600, 300)], L) == 0.0
    # nothing in the way: a gentle bend, and neighbours are joined directly
    _, _, _, rep2 = wbe.build({"items": items[:2] + [{"id": "ar", "connect": "arrow", "from": "a", "to": "mid"}], "cues": [1, 3]}, 10.0, _ctx(), 480, 270, load=_stub, layout_only=True)
    assert rep2["crossed"] == []


def test_nothing_is_late_when_the_pen_can_start_earlier():
    items = [{"id": "a", "draw": "sun", "zone": "left", "say": "a"}, {"id": "b", "draw": "piggy_bank", "zone": "centre", "say": "b"}, {"id": "w", "write": "three words here", "zone": "right", "say": "c"}]
    _, _, _, rep = wbe.build({"items": items, "cues": [4.0, 4.4, 4.8]}, 10.0, _ctx(), 480, 270, load=_stub, layout_only=True)     # three things within a second: the first ones are finished sooner
    assert rep["late"] == []
    assert rep["times"]["a"][1] < 4.0 and abs(rep["times"]["w"][1] - (4.8 + wbe.LEAD_IN_S + 0.15)) < 0.02
    assert rep["times"]["a"][0] >= 0.3                                             # ... but nothing before the scene is ready
    _, _, _, slow = wbe.build({"items": items[2:], "cues": [6.0]}, 10.0, _ctx(), 480, 270, load=_stub, layout_only=True)
    t0, t1 = slow["times"]["w"]
    _, _, _, quick = wbe.build({"items": items[2:], "cues": [0.5]}, 10.0, _ctx(), 480, 270, load=_stub, layout_only=True)
    assert t1 - t0 > 1.5 * (quick["times"]["w"][1] - quick["times"]["w"][0])     # writing with idle time before it starts earlier and goes slower, ending on the same word


def test_beats_that_share_a_board_draw_on_one_picture():
    from engine import whiteboard_policy as wp

    a = EL.sanitize({"items": [{"id": "t", "write": "Title", "zone": "top", "say": "title"}, {"id": "s", "draw": "sun", "zone": "left", "say": "sun"}]})
    b = EL.sanitize({"board": "same", "items": [{"id": "s", "draw": "piggy_bank", "zone": "right", "say": "pig"}, {"id": "u", "mark": "circle", "on": "s"}]})
    c = EL.sanitize({"items": [{"id": "p", "draw": "plant_sprout", "zone": "centre", "say": "plant"}]})
    assert b["board"] == "same" and EL.sanitize(b) == b
    scenes = [{"id": f"s{k}", "type": "whiteboard", "duration": 8.0, "transition": "fade", "props": dict(p, cues=[1.0, 3.0][:len(EL.anchors(p))])} for k, p in enumerate((a, b, c))]
    assert wp.link(scenes) == 3
    p0, p1, p2 = (s["props"] for s in scenes)
    own = lambda items: [it["id"] for it in items if "+r" not in it["id"]]      # noqa: E731 (marks the engine adds for the pen's rests are tested elsewhere)
    assert own(p0["items"]) == ["0:t", "0:s"] and own(p0["after"]) == ["1:s", "1:u"] and not p0.get("before")
    assert own(p1["before"]) == ["0:t", "0:s"] and next(it for it in p1["items"] if it["id"] == "1:u")["on"] == "1:s" and not p1.get("after")      # names are unique on the board, references follow
    assert p1["before"] == [{k: v for k, v in it.items() if k not in ("say", "at")} for it in p0["items"]]                # ... and a later beat sees exactly what the earlier one left
    assert p0["panel"] == p1["panel"] == [0, 2] and p2["panel"] == [1, 2]
    assert "prev" not in p0 and "prev" not in p1 and own(p2["prev"]["items"]) == ["0:t", "0:s", "1:s", "1:u"]    # the camera only travels to a NEW board
    assert p2["prev"]["items"] == p1["before"] + [{k: v for k, v in it.items() if k not in ("say", "at")} for it in p1["items"]]
    assert p2["wall"] == [p2["prev"]] and all("say" not in it for it in p2["wall"][0]["items"])
    wbe._STATE.clear(); wbe._STILLS.clear()
    end0 = render("whiteboard", p0, 7.95, dur=8.0)
    start1 = render("whiteboard", p1, 0.0, dur=8.0)
    assert changed(end0, start1) < 0.012                                         # the picture does not move, fade or redraw between two beats of one board
    assert ink(start1) > 1500
    end1 = render("whiteboard", p1, 7.95, dur=8.0)
    assert ink(end1) > ink(start1) + 500                                         # ... and the second beat adds its things to it
    wbe._STATE.clear(); wbe._STILLS.clear()
    arriving = render("whiteboard", p2, 0.0, dur=8.0)                            # the next board starts on the finished previous one
    assert changed(arriving, end1) < 0.02
    _, _, _, rep = wbe.build(p1, 8.0, _ctx(), 480, 270, layout_only=True)
    assert {i for i in rep["times"] if "+r" not in i} == {"1:s", "1:u"}                                   # only its own things are drawn in this scene


def test_the_overview_is_short_when_the_boards_would_be_too_small_to_read():
    few, many = {"wall": [{}] * 3, "items": []}, {"wall": [{}] * 5, "items": []}
    assert wbe._tail(few, 12.0) == wbe.WALL_S and wbe._tail(many, 12.0) == wbe.WALL_SHORT_S < wbe.WALL_S      # up to four boards are held as one picture; more only glanced at
    assert wbe._tail({"items": []}, 12.0) == 0.0
    assert wbe.grid(2) == (2, 1) and wbe.grid(2, portrait=True) == (1, 2) and wbe.grid(4) == (2, 2)


def test_an_engine_mark_is_drawn_at_its_fixed_time():
    items = [{"id": "s", "draw": "sun", "zone": "left", "say": "sun"}, {"id": "+r0", "mark": "circle", "on": "s", "at": 6.0}]
    _, _, _, rep = wbe.build({"items": items, "cues": [2.0]}, 10.0, _ctx(), 480, 270, load=_stub, layout_only=True)
    assert abs(rep["times"]["+r0"][1] - 6.15) < 0.02
