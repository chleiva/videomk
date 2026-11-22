"""Karaoke-style captions: the sentence being spoken, current word highlighted."""
from typing import Dict, List, Sequence, Tuple

from ..canvas import Canvas, with_alpha
from ..easing import ease_out_cubic, progress
from ..theme import Theme

Word = Tuple[str, float, float]  # text, start, end (scene-local seconds)

MAX_WORDS = 11
SIZE = 46
MAX_W = 1480
PAD_X, PAD_Y = 36, 22
BOTTOM = 1010

_pages_cache: Dict[int, List[List[Word]]] = {}


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


def draw_captions(cv: Canvas, th: Theme, words: Sequence[Word], lt: float) -> None:
    if not words:
        return
    key = id(words)
    pages = _pages_cache.get(key)
    if pages is None:
        pages = paginate(words)
        if len(_pages_cache) > 256:
            _pages_cache.clear()
        _pages_cache[key] = pages
    page = _active_page(pages, lt)
    if not page:
        return

    text = " ".join(w[0] for w in page)
    lines = cv.wrap(text, "semibold", SIZE, MAX_W)
    line_h = SIZE * 1.32
    box_w = max(cv.measure(l, "semibold", SIZE) for l in lines) + 2 * PAD_X
    box_h = len(lines) * line_h + 2 * PAD_Y - (line_h - SIZE) * 0.4
    appear = ease_out_cubic(progress(lt, page[0][1] - 0.08, 0.18))
    x0 = (cv.W - box_w) / 2
    y0 = BOTTOM - box_h + (1 - appear) * 14

    cv.rrect(x0, y0, box_w, box_h, 22, fill=with_alpha(th.caption_bg, appear))

    wi = 0
    for li, line in enumerate(lines):
        lw = cv.measure(line, "semibold", SIZE)
        x = (cv.W - lw) / 2
        y = y0 + PAD_Y + li * line_h
        for token in line.split():
            _, t0, t1 = page[wi] if wi < len(page) else (token, 1e9, 1e9)
            if lt >= t1:
                col = with_alpha(th.caption_text, appear)
            elif lt >= t0:
                col = with_alpha(th.accent2, appear)
            else:
                col = with_alpha(th.caption_text, 0.5 * appear)
            cv.text(x, y, token, "semibold", SIZE, col)
            x += cv.measure(token + " ", "semibold", SIZE)
            wi += 1
