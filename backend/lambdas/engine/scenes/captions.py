"""Karaoke-style captions: the sentence being spoken, current word highlighted."""
from typing import Dict, List, Sequence, Tuple

from ..canvas import Canvas, with_alpha
from ..easing import ease_out_cubic, progress
from ..frame import DEFAULT_FRAME, Frame
from ..theme import Theme

Word = Tuple[str, float, float]  # text, start, end (scene-local seconds)

MAX_WORDS = 11
SIZE = 46
MAX_W = 1480
PAD_X, PAD_Y = 36, 22
BOTTOM = 1010
# The translation row (engine/plan_langs.translation_for): a smaller row under the caption row, in the same band, for lines spoken in another language than the video's
# (design doc 2.5). With it the caption is a little smaller and its pages shorter, so both rows fit the band the scenes already leave free (engine/frame.py).
TRANSLATION_SCALE = 0.62                                   # its type size, as a share of the caption's
TRANSLATION_MIN_SIZE = 24                                  # design px (frame.MIN_READABLE_PX is 22)
TRANSLATION_GAP = 8
WITH_TRANSLATION_SCALE = 0.9
WITH_TRANSLATION_WORDS = {"16:9": 8, "9:16": 5, "1:1": 6, "4:5": 6}

_pages_cache: Dict[Tuple[int, int], List[List[Word]]] = {}


def paginate(words: Sequence[Word], max_words: int = MAX_WORDS) -> List[List[Word]]:
    """Split into pages <= max_words, preferring to break after sentence/clause punctuation."""
    pages: List[List[Word]] = []
    cur: List[Word] = []
    for w in words:
        cur.append(w)
        end_sentence = w[0].rstrip().endswith((".", "!", "?"))
        end_clause = w[0].rstrip().endswith((",", ";", ":", "—"))
        if end_sentence and len(cur) >= 3 or len(cur) >= max_words or (end_clause and len(cur) >= max_words - 3):
            pages.append(cur)
            cur = []
    if cur:
        if pages and len(cur) <= 2:
            pages[-1].extend(cur)
        else:
            pages.append(cur)
    return pages


def _active_page(pages: List[List[Word]], lt: float):
    chosen = None
    for pg in pages:
        if lt >= pg[0][1] - 0.08:
            chosen = pg
        else:
            break
    return chosen


def draw_captions(cv: Canvas, th: Theme, words: Sequence[Word], lt: float, frame: Frame = DEFAULT_FRAME, lift: float = 0.0) -> None:
    """Karaoke captions in the frame's caption band (engine/frame.py): landscape bottom band as ever; 9:16 above the platform UI zone; at most 2 lines.
    `lift` (design units, 0 for every video without a translation row): the caption box sits that much higher, a little smaller and in shorter pages, to make room for the
    translation row under it (`draw_translation`)."""
    if not words:
        return
    cap = frame.caption
    size, max_w, bottom, max_words = cap["size"], cap["max_w"], cap["bottom"] - lift, int(cap["words"])
    if lift:
        size, max_words = size * WITH_TRANSLATION_SCALE, min(max_words, WITH_TRANSLATION_WORDS[frame.aspect])
    pad_x, pad_y = (PAD_X, PAD_Y) if frame.landscape else (32, 20)
    key = (id(words), max_words)
    pages = _pages_cache.get(key)
    if pages is None:
        pages = paginate(words, max_words)
        if len(_pages_cache) > 256:
            _pages_cache.clear()
        _pages_cache[key] = pages
    page = _active_page(pages, lt)
    if not page:
        return

    text = " ".join(w[0] for w in page)
    size = cap["size"] * WITH_TRANSLATION_SCALE if lift else cap["size"]
    lines = cv.wrap(text, "semibold", size, max_w - 2 * pad_x if not frame.landscape else max_w)
    while not frame.landscape and len(lines) > cap["max_lines"] and size > 34:   # two lines at most: shrink a little before ever running to a third
        size -= 2
        lines = cv.wrap(text, "semibold", size, max_w - 2 * pad_x if not frame.landscape else max_w)
    line_h = size * 1.32
    box_w = max(cv.measure(l, "semibold", size) for l in lines) + 2 * pad_x
    box_h = len(lines) * line_h + 2 * pad_y - (line_h - size) * 0.4
    appear = ease_out_cubic(progress(lt, page[0][1] - 0.08, 0.18))
    x0 = (cap["x0"] + cap["x1"] - box_w) / 2
    y0 = bottom - box_h + (1 - appear) * 14

    cv.rrect(x0, y0, box_w, box_h, 22, fill=with_alpha(th.caption_bg, appear))

    wi = 0
    for li, line in enumerate(lines):
        lw = cv.measure(line, "semibold", size)
        x = x0 + (box_w - lw) / 2
        y = y0 + pad_y + li * line_h
        for token in line.split():
            _, t0, t1 = page[wi] if wi < len(page) else (token, 1e9, 1e9)
            if lt >= t1:
                col = with_alpha(th.caption_text, appear)
            elif lt >= t0:
                col = with_alpha(th.accent2, appear)
            else:
                col = with_alpha(th.caption_text, 0.5 * appear)
            cv.text(x, y, token, "semibold", size, col)
            x += cv.measure(token + " ", "semibold", size)
            wi += 1


def translation_layout(cv: Canvas, frame: Frame, text: str) -> Tuple[List[str], float, float, float]:
    """(lines, size, box width, box height) of the translation row: at most two lines, shrunk from 62 percent of the caption size down to 24 px before a second line is used."""
    cap = frame.caption
    pad_x, pad_y = 22, 12
    max_w = float(cap["max_w"]) - 2 * pad_x
    size = float(cap["size"]) * TRANSLATION_SCALE
    lines = cv.wrap(text, "regular", size, max_w)
    while len(lines) > 2 and size > TRANSLATION_MIN_SIZE:
        size = max(float(TRANSLATION_MIN_SIZE), size - 2)
        lines = cv.wrap(text, "regular", size, max_w)
    if len(lines) > 2:   # still longer than two lines at the smallest size: the end is cut, never a third line
        lines = lines[:2]
        lines[1] = lines[1].rstrip(" ,.;:") + "..."
    line_h = size * 1.3
    box_w = max(cv.measure(l, "regular", size) for l in lines) + 2 * pad_x
    return lines, size, min(box_w, float(cap["max_w"])), len(lines) * line_h + 2 * pad_y - (line_h - size) * 0.4


def translation_height(cv: Canvas, frame: Frame, text: str) -> float:
    """How much of the band the translation row takes (with its gap): the caption row is lifted by this much."""
    return translation_layout(cv, frame, text)[3] + TRANSLATION_GAP


def draw_translation(cv: Canvas, th: Theme, text: str, lt: float, frame: Frame = DEFAULT_FRAME) -> None:
    """The translation row: the line being spoken, in the video's main language, smaller than the captions, at the bottom of the caption band; it fades in with the line."""
    text = " ".join(str(text or "").split())
    if not text:
        return
    cap = frame.caption
    lines, size, box_w, box_h = translation_layout(cv, frame, text)
    pad_y = 12
    appear = ease_out_cubic(progress(lt, 0.1, 0.25))
    if appear <= 0:
        return
    x0 = (cap["x0"] + cap["x1"] - box_w) / 2
    y0 = cap["bottom"] - box_h + (1 - appear) * 10
    cv.rrect(x0, y0, box_w, box_h, 18, fill=with_alpha(th.caption_bg, appear))
    line_h = size * 1.3
    for i, line in enumerate(lines):
        lw = cv.measure(line, "regular", size)
        cv.text(x0 + (box_w - lw) / 2, y0 + pad_y + i * line_h, line, "regular", size, with_alpha(th.caption_text, 0.92 * appear))
