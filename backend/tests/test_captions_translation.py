"""The translation row (engine/scenes/captions.py, design doc 2.5): a smaller row under the caption row, in the same band, for the line being spoken; with it the caption is
lifted, a little smaller and in shorter pages. Both rows stay in the band the scenes leave free (frame.content_bottom), in every shape; nothing changes for a video without
a translation. Real drawing on a Canvas (no video, no ffmpeg)."""
import numpy as np
import pytest

from engine.canvas import Canvas
from engine.frame import Frame
from engine.scenes import captions as C
from engine.theme import get_theme

TH = get_theme("sunrise")
WORDS = [(w, 0.3 + i * 0.3, 0.55 + i * 0.3) for i, w in enumerate("Das ist eine tolle Frage! Das Meer ist nicht immer salzig gewesen, und die Geschichte ist sehr alt.".split())]
SHORT = "That is a great question!"
LONG = "That is a great question! The sea has not always been salty, and the story is very old, so we will see why it is so."
ASPECTS = ("16:9", "9:16", "1:1", "4:5")


def blank(fr):
    cv = Canvas(fr.W, fr.H, ss=1)
    cv.background(TH, 0.0)
    return cv


def ink_rows(fr, draw):
    """(top, bottom) design rows where the drawing changed the picture, and the columns."""
    base = np.asarray(blank(fr).to_rgb()).astype(int)
    cv = blank(fr)
    draw(cv)
    diff = np.abs(np.asarray(cv.to_rgb()).astype(int) - base).sum(axis=2) > 12
    rows, cols = np.where(diff.any(axis=1))[0], np.where(diff.any(axis=0))[0]
    return (int(rows.min()), int(rows.max()), int(cols.min()), int(cols.max())) if len(rows) else None


@pytest.mark.parametrize("aspect", ASPECTS)
@pytest.mark.parametrize("text", [SHORT, LONG])
def test_both_rows_fit_the_band_the_scenes_leave_free(aspect, text):
    fr = Frame(aspect)
    cap = fr.caption

    def both(cv):
        C.draw_captions(cv, TH, WORDS, 2.5, fr, lift=C.translation_height(cv, fr, text))
        C.draw_translation(cv, TH, text, 2.5, fr)
    top, bottom, left, right = ink_rows(fr, both)
    assert bottom <= cap["bottom"] + 1                                       # nothing below the band's bottom edge (the platform zone in 9:16 stays free)
    assert top >= fr.content_bottom(True) - 12                               # nothing into the content box (a few units: the pill's soft edge)
    assert left >= cap["x0"] - 2 and right <= cap["x1"] + 2                  # inside the span the box is centred in (the reserved strip in vertical)


@pytest.mark.parametrize("aspect", ASPECTS)
def test_the_translation_row_is_smaller_than_the_caption_and_below_it(aspect):
    fr = Frame(aspect)
    cv = blank(fr)
    lines, size, box_w, box_h = C.translation_layout(cv, fr, LONG)
    assert size < fr.caption["size"] and size >= C.TRANSLATION_MIN_SIZE and len(lines) <= 2 and box_w <= fr.caption["max_w"]
    tr_only = ink_rows(fr, lambda c: C.draw_translation(c, TH, LONG, 2.5, fr))
    assert tr_only[1] <= fr.caption["bottom"] + 1 and tr_only[0] >= fr.caption["bottom"] - box_h - 2   # the row ends where the caption band ends
    cap_only = ink_rows(fr, lambda c: C.draw_captions(c, TH, WORDS, 2.5, fr, lift=C.translation_height(c, fr, LONG)))
    assert cap_only[1] < tr_only[0]                                          # the caption sits above the translation, without touching it


def test_a_video_without_a_translation_draws_exactly_what_it_drew():
    fr = Frame("16:9")
    a, b = blank(fr), blank(fr)
    C.draw_captions(a, TH, WORDS, 2.5, fr)
    C.draw_captions(b, TH, WORDS, 2.5, fr, lift=0.0)
    assert np.array_equal(np.asarray(a.to_rgb()), np.asarray(b.to_rgb()))
    assert ink_rows(fr, lambda c: C.draw_captions(c, TH, WORDS, 2.5, fr))[1] <= fr.caption["bottom"] + 1


def test_the_translation_alone_with_captions_off_sits_at_the_bottom_of_the_band():
    fr = Frame("9:16")
    top, bottom, _, _ = ink_rows(fr, lambda c: C.draw_translation(c, TH, SHORT, 2.5, fr))
    assert bottom <= fr.caption["bottom"] + 1 and top >= fr.content_bottom(True)


def test_the_row_appears_with_the_line_and_an_empty_text_draws_nothing():
    fr = Frame("16:9")
    assert ink_rows(fr, lambda c: C.draw_translation(c, TH, SHORT, 0.0, fr)) is None        # the line has not begun
    assert ink_rows(fr, lambda c: C.draw_translation(c, TH, SHORT, 1.0, fr)) is not None
    assert ink_rows(fr, lambda c: C.draw_translation(c, TH, "   ", 1.0, fr)) is None


def test_a_very_long_translation_is_cut_never_a_third_line():
    fr = Frame("9:16")
    text = " ".join(["translation"] * 60)
    cv = blank(fr)
    lines, size, _, box_h = C.translation_layout(cv, fr, text)
    assert len(lines) == 2 and lines[1].endswith("...") and size >= C.TRANSLATION_MIN_SIZE and box_h < 140
