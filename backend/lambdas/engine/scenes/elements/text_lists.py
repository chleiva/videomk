"""Text, list and process elements: kinetic_text, definition, counter, checklist, steps, funnel.

All six follow docs/ELEMENT_BUILD_GUIDE.md: sanitize is the only gate for the director's props (idempotent, raises ValueError when unusable), draw is a pure function
of (props, lt, dur), and the elements that reveal parts one by one expose `anchors` so the engine ties each reveal to the word that names it (props["cues"]).
"""
import math
import re
import unicodedata
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

from ...canvas import Canvas, load_font, partial_polyline, with_alpha
from ... import numfmt
from ...easing import COUNT_FLOOR, count_run, count_up, ease_out_back, ease_out_cubic, ease_out_expo, progress, reveal_times
from ...theme import Theme
from ..base import SceneCtx, format_number, heading, parse_number
from ..registry import Element

Props = Dict[str, Any]


# ----------------------------------------------------------------------------- shared helpers
def _s(x: Any, n: int) -> str:
    """A clean, clipped single-line string (control and bidi-override characters removed)."""
    if x is None or isinstance(x, (dict, list, tuple, set)):
        return ""
    t = "".join(c for c in str(x) if unicodedata.category(c) not in ("Cc", "Cf") or c in "\n\t")
    return re.sub(r"\s+", " ", t).strip()[:n].rstrip()


def _keep_cues(props: Props, n: int) -> Optional[List[float]]:
    """Anchored reveal times written by engine/sync.py: kept (so the editor's re-sanitize does not lose them) when there is one per part."""
    c = props.get("cues")
    if not isinstance(c, (list, tuple)) or len(c) < n:
        return None
    out = []
    for v in c[:n]:
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            return None
        out.append(round(float(v), 3))
    return out


def _with_cues(clean: Props, props: Props, n: int) -> Props:
    c = _keep_cues(props, n)
    if c:
        clean["cues"] = c
    return clean


def _ink(c: Tuple[int, ...]) -> Tuple[int, int, int]:
    """Readable text colour on a filled shape of colour c."""
    lum = 0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]
    return (255, 255, 255) if lum < 150 else (20, 24, 39)


def _mix(a, b, t: float) -> Tuple[int, int, int]:
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))  # type: ignore[return-value]


def _list_of(v: Any) -> List[Any]:
    return list(v) if isinstance(v, (list, tuple)) else []


def _fit_wide(cv: Canvas, text: str, weight: str, size: float, lines: List[str], max_w: float, floor: float = 28):
    """fit_text only limits the wrapped height: an unbreakable word can still be wider than the frame. Shrinks until no line is wider than max_w."""
    while size > floor and max((cv.measure(l, weight, size) for l in lines), default=0) > max_w:
        size -= 4
        lines = cv.wrap(text, weight, size, max_w)
    return size, lines


def _mid_y(ctx: SceneCtx) -> float:
    return (ctx.top + ctx.bottom) / 2     # middle of the frame's content box (ctx.top is CONTENT_TOP in landscape)


# ============================================================================= kinetic_text
_STOP: Optional[set] = None


def _stopwords() -> set:
    global _STOP
    if _STOP is None:
        from ... import sync
        _STOP = set(sync._STOP)
    return _STOP


def _emph_words(text: str, emphasis: str) -> List[bool]:
    """Which words of `text` belong to the emphasised phrase (case-insensitive, whole words)."""
    words = text.split()
    flags = [False] * len(words)
    if not emphasis:
        return flags
    norm = lambda w: re.sub(r"^\W+|\W+$", "", w).lower()  # noqa: E731
    ew = [norm(w) for w in emphasis.split()]
    ew = [w for w in ew if w]
    nw = [norm(w) for w in words]
    for i in range(len(nw) - len(ew) + 1):
        if ew and nw[i:i + len(ew)] == ew:
            for k in range(len(ew)):
                flags[i + k] = True
            break
    return flags


def kinetic_groups(props: Props) -> List[Tuple[List[int], bool]]:
    """The text as reveal groups: (word indexes, emphasised). A group is a content word with the little words before it (max 3 words); the emphasised
    phrase is always its own group(s), so it can be bigger and in the accent colour."""
    text = str(props.get("text", ""))
    words = text.split()
    flags = _emph_words(text, str(props.get("emphasis", "")))
    stop = _stopwords()
    groups: List[Tuple[List[int], bool]] = []
    cur: List[int] = []
    for i, w in enumerate(words):
        if cur and flags[i] != flags[cur[0]]:
            groups.append((cur, flags[cur[0]]))
            cur = []
        cur.append(i)
        core = re.sub(r"\W+", "", w).lower()
        content = core not in stop and len(core) >= 3
        if flags[i]:
            continue                                   # an emphasised phrase stays one group
        if content or len(cur) >= 3:
            groups.append((cur, False))
            cur = []
    if cur:
        if groups and not flags[cur[0]] and not groups[-1][1]:
            groups[-1] = (groups[-1][0] + cur, False)  # trailing little words join the previous group
        else:
            groups.append((cur, flags[cur[0]]))
    while len(groups) > 12:                            # long sentences: merge neighbouring plain groups so there are never too many reveals
        for k in range(len(groups) - 1):
            if not groups[k][1] and not groups[k + 1][1]:
                groups[k] = (groups[k][0] + groups[k + 1][0], False)
                del groups[k + 1]
                break
        else:
            break
    return groups


def kinetic_sanitize(props: Props) -> Props:
    text = _s(props.get("text"), 140)
    if len(text.split()) < 2:
        raise ValueError("kinetic_text needs a sentence")
    emphasis = _s(props.get("emphasis"), 60)
    if emphasis and not any(_emph_words(text, emphasis)):
        emphasis = ""
    clean: Props = {"text": text}
    if emphasis:
        clean["emphasis"] = emphasis
    return _with_cues(clean, props, len(kinetic_groups(clean)))


def kinetic_anchors(props: Props) -> List[str]:
    words = str(props.get("text", "")).split()
    return [" ".join(words[i] for i in idx) for idx, _ in kinetic_groups(props)]


@lru_cache(maxsize=32)
def _kinetic_layout(words: Tuple[str, ...], flags: Tuple[bool, ...], ss: int, max_h: int, max_w: int = 1560, start: int = 136):
    """Largest size at which the sentence fits; returns (size, lines, total_h) with lines = [(line_h, [(word index, x, width, font size)])], x centred on 0.
    Keyed by the frame's width and starting size too (the same sentence lays out differently in each shape)."""
    for size in range(start, 44, -4):
        base = load_font("bold", int(size * ss))
        space = base.getlength(" ") / ss
        lines: List[Tuple[float, List[Tuple[int, float, float, float]]]] = []
        cur: List[Tuple[int, float, float]] = []
        x = 0.0
        for i, w in enumerate(words):
            fs = size * (1.22 if flags[i] else 1.0)
            ww = load_font("bold", int(fs * ss)).getlength(w) / ss
            if cur and x + space + ww > max_w:
                lines.append((0, cur))  # type: ignore[arg-type]
                cur, x = [], 0.0
            cur.append((i, x + (space if cur else 0), ww, fs))  # type: ignore[arg-type]
            x = cur[-1][1] + ww
        if cur:
            lines.append((0, cur))  # type: ignore[arg-type]
        out = []
        total = 0.0
        for _, items in lines:
            lw = items[-1][1] + items[-1][2]
            lh = max(it[3] for it in items) * 1.2
            out.append((lh, [(i, ox - lw / 2, ww, fs) for i, ox, ww, fs in items]))
            total += lh
        if total <= max_h and all(it[2] <= max_w for _, items in lines for it in items):   # (a word wider than the frame forces a smaller size)
            return size, out, total
    return 44, out, total


def kinetic_cues(props: Props, dur: float) -> List[float]:
    groups = kinetic_groups(props)
    times = reveal_times(len(groups), dur, props.get("cues"), first=0.15, last=0.7)
    pick = [times[0]] if times else []
    pick += [times[k] for k, g in enumerate(groups) if g[1]][:1]
    return pick


KINETIC_FADE_S = 0.16      # each word fades in over ~160 ms ...
KINETIC_MOVE_S = 0.32      # ... and settles up into place over ~320 ms, so neighbouring words overlap and the text flows
KINETIC_MIN_STEP = 0.11    # words never start closer than this (no batch of 3 words popping together) ...
KINETIC_MAX_STEP = 0.38    # ... nor further apart than this inside a group (about a quick speaking pace), so the text never looks stuck
KINETIC_MAX_IDLE = 0.5     # between two groups the text may stand still for at most this long: a group whose cue is later comes in up to KINETIC_PULL early ...
KINETIC_PULL = 0.5         # ... (never more than half a second ahead of the voice; a real pause in the narration stays a pause beyond that)


def kinetic_word_times(groups: List[Tuple[List[int], bool]], n_words: int, dur: float, cues=None) -> List[float]:
    """Start time of EVERY word. A group is the little words and the content word they lead to, and the group's cue (narration, engine/sync.py) is when its CONTENT
    word is spoken. They used to pop together 70 ms apart at the cue and then nothing moved until the next cue: words came in lumps of 2-3 and the text looked stuck.
    Now the words of a group arrive at an even pace that ends on the cue (so the little words come in just before the content word, as they are spoken); the pace is
    between ~110 and ~380 ms a word; groups whose cues cluster are pushed apart so there is never a lump; and the text never holds still for more than half a second
    between words (a group whose cue is far off comes in up to half a second early rather than leave the heading frozen).
    Pure function of its arguments: the same times at every frame, in every chunk."""
    times = reveal_times(len(groups), dur, cues, first=0.15, last=0.7)
    when = [0.0] * n_words
    prev: Optional[float] = None                         # start of the previous word
    for g, (idx, _) in enumerate(groups):
        n, cue = len(idx), times[g]
        if prev is None:
            step = KINETIC_MAX_STEP * 0.65
            start = max(0.0, cue - (n - 1) * step)
        else:
            step = min(KINETIC_MAX_STEP, max(KINETIC_MIN_STEP, (cue - prev) / n))
            start = max(prev + KINETIC_MIN_STEP, cue - (n - 1) * step)
            if start - prev > KINETIC_MAX_IDLE:          # a long hold between two groups looks stuck: come in early (at most KINETIC_PULL ahead of the voice)
                start = max(prev + KINETIC_MAX_IDLE, start - KINETIC_PULL)
        for k, i in enumerate(idx):
            when[i] = start + k * step
        prev = when[idx[-1]]
    return when


def draw_kinetic(cv: Canvas, props: Props, lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    words = tuple(str(props.get("text", "")).split())
    if not words:
        return
    groups = kinetic_groups(props)
    flags = [False] * len(words)
    for idx, em in groups:
        for i in idx:
            flags[i] = em
    fr = ctx.frame
    cx = fr.cx
    land = fr.landscape
    avail = ctx.bottom - ctx.top - 110
    # the sentence may use the whole width of the content box; narrow frames start larger (fewer words per line, bigger type)
    size, lines, total = _kinetic_layout(words, tuple(flags), cv.ss, int(avail), 1560 if land else fr.W - 2 * fr.margin_x, 136 if land else int(136 * fr.type_scale))
    when = kinetic_word_times(groups, len(words), dur, props.get("cues"))
    top = _mid_y(ctx) - (total + 60) / 2
    y = top
    for lh, items in lines:
        base = y + lh * 0.84
        for i, ox, ww, fs in items:
            p = ease_out_cubic(progress(lt, when[i], KINETIC_MOVE_S))
            a = ease_out_cubic(progress(lt, when[i], KINETIC_FADE_S))
            col = th.accent if flags[i] else th.text
            cv.text(cx + ox, base + (1 - p) * 34, words[i], "bold", fs, with_alpha(col, a), anchor="ls")
        y += lh
    end = max(when) + KINETIC_MOVE_S
    bw = 220 * ease_out_expo(progress(lt, end, 0.6))
    cv.rrect(cx - bw / 2, y + 36, bw, 10, 5, fill=th.accent)


KINETIC = Element(
    name="kinetic_text", family="Text",
    doc=("- kinetic_text: {text (<=140, one sentence), emphasis (optional, a word or short phrase that occurs in text)}. The sentence appears word by word with the voice, "
         "large and centred, the emphasis bigger in the accent colour. Use for a thesis, a rule, a punchline, the one sentence to remember. "
         "Never for several ideas, never the same sentence the caption already shows alone, at most 3 per video."),
    sanitize=kinetic_sanitize, draw=draw_kinetic, cues=kinetic_cues, anchors=kinetic_anchors, max_per_video=3,
    formats=("16:9", "9:16", "1:1", "4:5"),   # converted: the reference example in docs/RESPONSIVE_LAYOUT.md
    samples=[{"text": "Compound interest rewards patience more than talent.", "emphasis": "patience"},
             {"text": "If you cannot explain it simply, you do not understand it well enough yet, and that is fine because understanding is a process, not a switch.",
              "emphasis": "understanding is a process"}],
)


# ============================================================================= definition
def definition_sanitize(props: Props) -> Props:
    term, defn = _s(props.get("term"), 40), _s(props.get("definition"), 160)
    if not term or not defn:
        raise ValueError("definition needs a term and a definition")
    clean: Props = {"term": term, "definition": defn}
    for k, n in (("origin", 80), ("example", 100)):
        v = _s(props.get(k), n)
        if v:
            clean[k] = v
    return clean


def definition_cues(props: Props, dur: float) -> List[float]:
    return list(_definition_times(props, dur))


def _definition_times(props: Props, dur: float) -> Tuple[float, ...]:
    k = min(1.0, dur / 8.0)
    out = [0.15, 0.9 * k + 0.1]
    if props.get("origin"):
        out.append(0.45 * dur if dur < 8 else 3.2)
    if props.get("example"):
        out.append(0.62 * dur if dur < 8 else 4.6)
    return tuple(round(t, 3) for t in out)


def _definition_layout(cv: Canvas, props: Props, ctx: SceneCtx, cw: float):
    """Sizes and wrapped lines of the card; in the narrow frames the card is shrunk (step by step) until it fits the content box height."""
    term, defn = str(props["term"]), str(props["definition"])
    origin, example = str(props.get("origin", "")), str(props.get("example", ""))
    fr = ctx.frame
    if fr.landscape:                                  # the original layout, numerically unchanged
        inner = cw - 180
        t_size, t_lines = cv.fit_text(term, "bold", inner, 230, 136, 60)
        d_size, d_lines = cv.fit_text(defn, "semibold", inner, 330, 66, 40, line_h=1.28)
        o_size, o_lines = (cv.fit_text(origin, "regular", inner - 200, 120, 46, 32) if origin else (0, []))
        e_size, e_lines = (cv.fit_text(example, "regular", inner - 200, 120, 46, 32) if example else (0, []))
        t_h, d_h = len(t_lines) * t_size * 1.15, len(d_lines) * d_size * 1.28
        o_h, e_h = len(o_lines) * o_size * 1.25, len(e_lines) * e_size * 1.25
        extra = (max(o_h, 48) + 28 if origin else 0) + (max(e_h, 48) + 28 if example else 0)
        card_h = 70 + t_h + 40 + d_h + (34 + extra if extra else 0) + 70
        return dict(inner=inner, pad=90, t=(t_size, t_lines, t_h), d=(d_size, d_lines, d_h), o=(o_size, o_lines, o_h), e=(e_size, e_lines, e_h), card_h=card_h)
    # narrow frames: stacked; the labels (ORIGIN / EXAMPLE) sit above their text instead of to its left
    avail = ctx.bottom - ctx.top
    ts, pad = fr.type_scale, 60
    inner = cw - 2 * pad
    k = 1.0
    side = bool(fr.square and origin and example)      # square: ORIGIN and EXAMPLE as two columns (the box is short)
    ow = (inner - 14 - 36) / 2 if side else inner
    while True:
        t_size, t_lines = cv.fit_text(term, "bold", inner, avail * 0.2 * k, 136 * ts * k, 52 if k < 0.7 else 60)
        t_size, t_lines = _fit_wide(cv, term, "bold", t_size, t_lines, inner - 14)
        d_size, d_lines = cv.fit_text(defn, "semibold", inner, avail * 0.34 * k, 66 * ts * k, 34, line_h=1.28)
        o_size, o_lines = (cv.fit_text(origin, "regular", ow, avail * (0.2 if side else 0.12) * k, 46 * k, 28 if side else 30) if origin else (0, []))
        e_size, e_lines = (cv.fit_text(example, "regular", ow, avail * (0.2 if side else 0.12) * k, 46 * k, 28 if side else 30) if example else (0, []))
        d_size, d_lines = _fit_wide(cv, defn, "semibold", d_size, d_lines, inner - 14)
        if origin:
            o_size, o_lines = _fit_wide(cv, origin, "regular", o_size, o_lines, ow)
        if example:
            e_size, e_lines = _fit_wide(cv, example, "regular", e_size, e_lines, ow)
        t_h, d_h = len(t_lines) * t_size * 1.15, len(d_lines) * d_size * 1.28
        o_h, e_h = len(o_lines) * o_size * 1.25, len(e_lines) * e_size * 1.25
        extra = (44 + max(o_h, e_h) + 24) if side else sum(44 + h + 24 for h, o in ((o_h, origin), (e_h, example)) if o)     # rule + label row + lines + gap
        card_h = pad + t_h + 32 + d_h + (30 + extra if extra else 0) + pad
        if card_h <= avail or k < 0.5:
            break
        k -= 0.06
    return dict(inner=inner, pad=pad, t=(t_size, t_lines, t_h), d=(d_size, d_lines, d_h), o=(o_size, o_lines, o_h), e=(e_size, e_lines, e_h), card_h=card_h, side=side, ow=ow)


def draw_definition(cv: Canvas, props: Props, lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    origin, example = str(props.get("origin", "")), str(props.get("example", ""))
    t = _definition_times(props, dur)
    fr = ctx.frame
    land = fr.landscape
    cx = fr.cx
    cw = 1560 if land else fr.W - 2 * fr.margin_x
    L = _definition_layout(cv, props, ctx, cw)
    pad, inner = L["pad"], L["inner"]
    t_size, t_lines, t_h = L["t"]
    d_size, d_lines, d_h = L["d"]
    o_size, o_lines, o_h = L["o"]
    e_size, e_lines, e_h = L["e"]
    card_h = L["card_h"]
    tx = cx - cw / 2 + pad
    top = _mid_y(ctx) - card_h / 2
    if not land:
        top = max(top, ctx.top)
    pc = ease_out_cubic(progress(lt, 0.0, 0.6))
    cv.card(cx - cw / 2, top + (1 - pc) * 30, cw, card_h, th, r=36, alpha=pc)
    if land:
        cv.rrect(cx - cw / 2 + 36, top + 56 + (1 - pc) * 30, 10, t_h + 40 + d_h - 8 + 28, 5, fill=with_alpha(th.accent, pc))
        y = top + 70
        gap1 = 40
    else:
        cv.rrect(cx - cw / 2 + 28, top + pad - 14 + (1 - pc) * 30, 8, t_h + 32 + d_h + 4, 4, fill=with_alpha(th.accent, pc))
        tx += 14
        inner -= 14
        y = top + pad
        gap1 = 32
    p = ease_out_cubic(progress(lt, t[0], 0.6))
    for i, line in enumerate(t_lines):
        cv.text(tx, y + i * t_size * 1.15 + (1 - p) * 26, line, "bold", t_size, with_alpha(th.accent, p))
    y += t_h + gap1
    p = ease_out_cubic(progress(lt, t[1], 0.6))
    for i, line in enumerate(d_lines):
        cv.text(tx, y + i * d_size * 1.28 + (1 - p) * 20, line, "semibold", d_size, with_alpha(th.text, p))
    y += d_h + (34 if land else 30)
    k = 2
    sy = y
    for j, (label, size, lines, hh, present) in enumerate( (("ORIGIN", o_size, o_lines, o_h, bool(origin)), ("EXAMPLE", e_size, e_lines, e_h, bool(example)))):
        if not present:
            continue
        p = ease_out_cubic(progress(lt, t[k], 0.55))
        k += 1
        if L.get("side"):
            y = sy
            bx0 = tx + j * (L["ow"] + 36)
            cv.rrect(bx0, y - 6, L["ow"], 2, 1, fill=with_alpha(th.card_outline, p))
            cv.text(bx0, y + 14, label, "bold", 28, with_alpha(th.accent2, p))
            for i, line in enumerate(lines):
                cv.text(bx0, y + 44 + i * size * 1.25 + (1 - p) * 14, line, "regular", size, with_alpha(th.muted, p))
            continue
        cv.rrect(tx, y - 6, inner, 2, 1, fill=with_alpha(th.card_outline, p))
        if land:
            y += 14
            cv.text(tx, y + 8, label, "bold", 28, with_alpha(th.accent2, p))
            for i, line in enumerate(lines):
                cv.text(tx + 200, y + i * size * 1.25 + (1 - p) * 14, line, "regular", size, with_alpha(th.muted, p))
            y += max(hh, 48) + 14
        else:
            y += 14
            cv.text(tx, y, label, "bold", 28, with_alpha(th.accent2, p))
            y += 30
            for i, line in enumerate(lines):
                cv.text(tx, y + i * size * 1.25 + (1 - p) * 14, line, "regular", size, with_alpha(th.muted, p))
            y += hh + 24


DEFINITION = Element(
    name="definition", family="Text",
    doc=("- definition: {term (<=40), definition (<=160), origin (<=80, optional), example (<=100, optional)}. A card: the term, its plain definition, then the origin "
         "and an example. Use when the narration defines a term or names where a word comes from. Never invent or improve a definition: it must come from the "
         "grounding notes (or be plain common knowledge); leave origin and example out unless the notes give them."),
    sanitize=definition_sanitize, draw=draw_definition, cues=definition_cues, formats=("16:9", "9:16", "1:1", "4:5"),
    samples=[{"term": "Inflation", "definition": "A general rise in prices over time, so the same money buys less than before."},
             {"term": "Serendipity", "definition": "Finding something valuable or pleasant by chance while looking for something else entirely.",
              "origin": "Coined by Horace Walpole in 1754, from a Persian fairy tale.", "example": "Penicillin was discovered when mould spoiled a lab dish."}],
)


# ============================================================================= counter
_PLAIN_NUM = re.compile(r"^[+\-]?[\d,]*\.?\d+$")


def _num_parts(v: Any) -> Optional[Tuple[str, float, int, str, bool]]:
    """(prefix, value, decimals, suffix, grouped) of a director's number, read the way the video's language writes numbers ('3,3' is 3.3 in Spanish)."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        if not math.isfinite(v) or abs(v) > 1e15:
            return None
        dec = 0 if float(v).is_integer() else min(6, len(repr(float(v)).split(".")[1]))
        return "", float(v), dec, "", False
    p = parse_number(_s(v, 24))
    if not p or not math.isfinite(p[1]) or abs(p[1]) > 1e15:
        return None
    if re.search(r"\d", p[0] + p[3]):
        return None                                    # "4 to 5", "10 in 2020": not one number
    return p


def _plan_value(props: Props, key: str) -> Optional[Tuple[str, float, int, str, bool]]:
    """A stored value is machine form ('1250.5', plain point, `decimals` beside it) and is read as it is in every language; a director's raw text is parsed by language."""
    raw = props.get(key)
    if raw in (None, ""):
        return None
    dkey = "decimals" if key == "value" else "from_decimals"
    if numfmt.is_canonical(raw) and isinstance(props.get(dkey), int) and not isinstance(props.get(dkey), bool):
        return "", float(raw), max(0, min(6, props[dkey])), "", bool(props.get("grouped"))
    return _num_parts(raw)


def counter_sanitize(props: Props) -> Props:
    p = _plan_value(props, "value")
    if not p:
        raise ValueError("counter needs a numeric value")
    pre, val, dec, suf, grouped = p
    dec = min(dec, 6)
    f = _plan_value(props, "from")
    prefix = _s(props.get("prefix"), 4) or (pre.strip() if len(pre.strip()) <= 4 else "")
    unit = _s(props.get("unit"), 8) or (suf.strip() if len(suf.strip()) <= 8 else "")
    grouped = grouped or (f is not None and f[4])
    # kept in machine form (plain decimal point, no grouping) with its decimals: it reads the same in every language and re-sanitizing it changes nothing
    clean: Props = {"value": numfmt.canonical(val, dec), "decimals": dec}
    if grouped:
        clean["grouped"] = True
    if prefix:
        clean["prefix"] = prefix
    if unit:
        clean["unit"] = unit
    clean["label"] = _s(props.get("label"), 70)
    if f is not None and f[1] != 0:
        fdec = min(f[2], 6)
        clean["from"] = numfmt.canonical(f[1], fdec)
        clean["from_decimals"] = fdec
    delta = _s(props.get("delta"), 24)
    if delta:
        clean["delta"] = delta
    return _with_cues(clean, props, 1)


def counter_anchors(props: Props) -> List[str]:
    p = _plan_value(props, "value")
    if not p:
        return [str(props.get("value", ""))]
    return [numfmt.format_number(p[1], p[2], bool(props.get("grouped")), "en")]    # the narration side may say it either way: the sync matches digits


def counter_cues(props: Props, dur: float) -> List[float]:
    return [0.05]                                      # the count starts the moment the scene does; the narration cue no longer delays it (no static zero)


def _tabular_width(cv: Canvas, s: str, size: float) -> float:
    cell = max(cv.measure(str(d), "bold", size) for d in "0123456789")
    return sum(cell if c.isdigit() else cv.measure(c, "bold", size) for c in s)


def _tabular_draw(cv: Canvas, x: float, y: float, s: str, size: float, fill) -> None:
    cell = max(cv.measure(str(d), "bold", size) for d in "0123456789")
    for c in s:
        if c.isdigit():
            cv.text(x + cell / 2, y, c, "bold", size, fill, anchor="ms")
            x += cell
        else:
            cv.text(x, y, c, "bold", size, fill, anchor="ls")
            x += cv.measure(c, "bold", size)


def draw_counter(cv: Canvas, props: Props, lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    pv = _plan_value(props, "value") or (_num_parts(props.get("value")))
    pre, val, dec, _, comma = pv  # type: ignore[misc]
    comma = comma or bool(props.get("grouped"))
    fp = _plan_value(props, "from")
    frm = fp[1] if fp else 0.0
    prefix, unit = str(props.get("prefix", "")), str(props.get("unit", ""))
    label, delta = str(props.get("label", "")), str(props.get("delta", ""))
    # The count starts with the scene (no static zero while the narration catches up), eases out over ~1.5 s and then holds the exact value.
    # From nothing it starts at 20% (never a frame that reads "0 <unit>"); with an explicit `from` it starts there.
    cdur = count_run(dur)
    start = 0.0
    p = count_up(lt, dur, 0.0 if fp else COUNT_FLOOR)
    shown = format_number(frm + (val - frm) * p, dec, comma)
    final = format_number(val, dec, comma)
    # one size for the whole animation, from the widest the number gets
    widest = max(final, format_number(frm, dec, comma), key=len)
    fr = ctx.frame
    land = fr.landscape
    cx = fr.cx
    max_w = 1560 if land else fr.W - 2 * fr.margin_x          # width of the content box
    size = 320.0 if land else 320.0 * fr.type_scale
    floor = 90 if land else 56
    while size > floor:
        w = _tabular_width(cv, widest, size) + (cv.measure(prefix, "bold", size * 0.55) + 14 if prefix else 0) + (cv.measure(unit, "bold", size * 0.55) + 14 if unit else 0)
        if w <= max_w:
            break
        size -= 8
    small = size * 0.55
    wp = cv.measure(prefix, "bold", small) + 14 if prefix else 0
    wu = cv.measure(unit, "bold", small) + 14 if unit else 0
    wn = _tabular_width(cv, shown, size)
    total_w = _tabular_width(cv, widest, size) + wp + wu
    if not label:
        l_size, l_lines = 0, []
    elif land:
        l_size, l_lines = cv.fit_text(label, "semibold", 1400, 150, 56, 36)
    else:
        l_size, l_lines = cv.fit_text(label, "semibold", max_w, 230 if fr.vertical else 170, 56 * fr.type_scale, 34)   # more wrapped lines, bigger type
        l_size, l_lines = _fit_wide(cv, label, "semibold", l_size, l_lines, max_w)
    chip_h = 76 if delta else 0
    block = size * 0.74 + (78 + len(l_lines) * l_size * 1.25 if label else 0) + (36 + chip_h if delta else 0)
    top = _mid_y(ctx) - block / 2 - 10
    base = top + size * 0.74
    fade = ease_out_cubic(progress(lt, 0.0, 0.3))      # number, unit and prefix fade in together while it is already counting
    rise = (1 - fade) * 24
    x = cx - total_w / 2 + (total_w - wp - wu - wn) / 2   # keep the digits centred while they grow
    col = with_alpha(th.text, fade)
    if prefix:
        cv.text(x, base - size * 0.18 + rise, prefix, "bold", small, with_alpha(th.accent, fade), anchor="ls")
    _tabular_draw(cv, x + wp, base + rise, shown, size, col)
    if unit:
        cv.text(x + wp + wn + 14, base - size * 0.18 + rise, unit, "bold", small, with_alpha(th.accent, fade), anchor="ls")
    y = base + 78
    if label:
        a = ease_out_cubic(progress(lt, 0.05, 0.4))     # the label is there with the number: a figure is never shown without what it measures
        for i, line in enumerate(l_lines):
            cv.text(cx, y + i * l_size * 1.25 + (1 - a) * 16, line, "semibold", l_size, with_alpha(th.muted, a), anchor="ma")
        y += len(l_lines) * l_size * 1.25
    if delta:
        a = ease_out_back(progress(lt, start + cdur * 0.8, 0.5), 1.2)
        aa = ease_out_cubic(progress(lt, start + cdur * 0.8, 0.35))
        fs = 40 if land else 40 * fr.type_scale
        dw = cv.measure(delta, "semibold", fs) + 56 + 44
        cx0, cy0 = cx - dw / 2, y + 36
        cv.rrect(cx0, cy0, dw, chip_h, chip_h / 2, fill=with_alpha(th.accent2, 0.18 * aa), outline=with_alpha(th.accent2, aa), width=2)
        ax, ay = cx0 + 40, cy0 + chip_h / 2
        s = delta[0]
        if s == "+":
            cv.polygon([(ax - 12, ay + 8), (ax + 12, ay + 8), (ax, ay - 10)], with_alpha(th.accent2, aa))
        elif s in "-−":
            cv.polygon([(ax - 12, ay - 8), (ax + 12, ay - 8), (ax, ay + 10)], with_alpha(th.accent2, aa))
        else:
            cv.ellipse(ax, ay, 8, 8, fill=with_alpha(th.accent2, aa))
        cv.text(cx0 + 68, ay, delta, "semibold", fs, with_alpha(th.text, aa), anchor="lm")
        _ = a


COUNTER = Element(
    name="counter", family="Text",
    doc=("- counter: {value (the number alone, plain, with a decimal POINT and no thousands separator: \"4.2\", \"73\" or \"1250\", in every language; the video writes it the way the viewer's language does, 4,2 in Spanish), unit (<=8, e.g. \"%\" or \"km\"), prefix (<=4, e.g. \"$\"), label (<=70), from (optional start number, default 0), "
         "delta (<=24, optional, e.g. \"+12% vs 2020\")}. A big number that counts up (or down from `from`) the moment the scene starts, settling on the exact value in about a second and a half. Use for one headline figure, a growth, a total. "
         "Only numbers that appear in the grounding notes; never invent or round a figure; not for several numbers (use chart)."),
    sanitize=counter_sanitize, draw=draw_counter, cues=counter_cues, anchors=counter_anchors, formats=("16:9", "9:16", "1:1", "4:5"),
    samples=[{"value": "4.2", "unit": "B", "prefix": "$", "label": "Annual revenue of the company in 2023"},
             {"value": "1,250", "unit": "km", "label": "Length of the route from coast to coast", "from": "2,000", "delta": "-38% vs the old road"},
             {"value": "73", "unit": "%", "label": "Share of adults who read at least one book a year", "delta": "+12% vs 2020"}],
)


# ============================================================================= checklist
def checklist_sanitize(props: Props) -> Props:
    items = [_s(i, 70) for i in _list_of(props.get("items")) if isinstance(i, (str, int, float)) and not isinstance(i, bool)]
    items = [i for i in items if i][:6]
    if len(items) < 2:
        raise ValueError("checklist needs 2+ items")
    raw = _list_of(props.get("checked"))
    checked = [bool(raw[i]) if i < len(raw) else True for i in range(len(items))]
    clean: Props = {"heading": _s(props.get("heading"), 50), "items": items}
    if not all(checked):
        clean["checked"] = checked
    return _with_cues(clean, props, len(items))


def checklist_anchors(props: Props) -> List[str]:
    return [str(i) for i in props.get("items", [])]


def checklist_cues(props: Props, dur: float) -> List[float]:
    return reveal_times(len(props.get("items", [])), dur, props.get("cues"))


_CK_FONT: Dict[Any, float] = {}


def _checklist_font(cv: Canvas, items: List[str], text_w: float, card_h: float, start: float) -> float:
    """One font size for all rows (narrow frames): the largest at which every item fits its card (up to 3 lines), floor 30."""
    key = (tuple(items), cv.ss, int(text_w), int(card_h), int(start))
    if key in _CK_FONT:
        return _CK_FONT[key]
    fs = float(int(start))
    out = 30.0
    while fs >= 30:
        if all(len(cv.wrap(t, "semibold", fs, text_w)) * fs * 1.22 + 22 <= card_h for t in items):
            out = fs
            break
        fs -= 2
    if len(_CK_FONT) > 256:
        _CK_FONT.clear()
    _CK_FONT[key] = out
    return out


def draw_checklist(cv: Canvas, props: Props, lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    items = [str(i) for i in props["items"]]
    n = len(items)
    checked = [bool(c) for c in props.get("checked", [])] + [True] * n
    fr = ctx.frame
    land = fr.landscape
    y = heading(cv, th, str(props.get("heading", "")), lt, y=ctx.top + 20, ctx=ctx)
    gap = 18 if land else 16
    avail = ctx.bottom - y - 10
    if land:
        card_h = max(84.0, min(126.0, (avail - gap * (n - 1)) / n))
        font_px = 46 if card_h > 110 else 40
        x0, w = 140, 1640
    else:
        card_h = max(72.0, min(230.0 if fr.vertical else 150.0, (avail - gap * (n - 1)) / n))
        x0, w = fr.margin_x, fr.W - 2 * fr.margin_x
        y += max(0.0, (avail - n * card_h - gap * (n - 1)) / 2) * 0.7     # few items: centre the stack in the free height instead of hugging the heading
    times = reveal_times(n, dur, props.get("cues"))
    r = min(34.0, card_h * 0.3) if land else min(40.0, card_h * 0.3)
    if not land:
        font_px = _checklist_font(cv, items, w - 150 - r * 2 + 40, card_h, 54.0 * fr.type_scale if fr.vertical else 50.0)
    for i, text in enumerate(items):
        p = progress(lt, times[i], 0.5)
        if p <= 0:
            continue
        a = ease_out_cubic(progress(lt, times[i], 0.3))
        dx = (1 - ease_out_cubic(p)) * -70
        cy = y + i * (card_h + gap)
        cv.card(x0 + dx, cy, w, card_h, th, r=24, alpha=a)
        mx, my = x0 + dx + (46 if land else 36) + r, cy + card_h / 2
        ok = checked[i]
        tp = progress(lt, times[i] + 0.2, 0.45)
        cv.ellipse(mx, my, r, r, outline=with_alpha(th.muted, a * 0.8), width=3)
        if tp > 0:
            col = th.accent if ok else th.muted
            e = ease_out_back(tp, 1.3)
            rr = r * min(1.0, e)
            cv.ellipse(mx, my, rr, rr, fill=with_alpha(col, min(1.0, tp * 2)))
            ink = with_alpha(_ink(col), min(1.0, tp * 2))
            if ok:
                pts = [(mx - 0.44 * r, my + 0.02 * r), (mx - 0.1 * r, my + 0.36 * r), (mx + 0.48 * r, my - 0.34 * r)]
                cv.line(partial_polyline(pts, ease_out_cubic(progress(tp, 0.2, 0.8))), ink, width=r * 0.26)
            else:
                k = 0.34 * r * ease_out_cubic(progress(tp, 0.2, 0.8))
                cv.line([(mx - k, my - k), (mx + k, my + k)], ink, width=r * 0.26)
                cv.line([(mx + k, my - k), (mx - k, my + k)], ink, width=r * 0.26)
        lines = cv.wrap(text, "semibold", font_px, w - 150 - r * 2 + (0 if land else 40))[: (2 if land else 3)]
        lh = font_px * 1.22
        ty = my - (len(lines) * lh) / 2 - lh * 0.06
        tcol = th.text if ok else th.muted
        for li, line in enumerate(lines):
            cv.text(x0 + dx + (46 if land else 36) + r * 2 + (34 if land else 28), ty + li * lh, line, "semibold", font_px, with_alpha(tcol, a))


CHECKLIST = Element(
    name="checklist", family="Lists",
    doc=("- checklist: {heading (<=50), items: 2-6 strings (<=70), checked: optional list of true/false, one per item (default all true)}. Rows ticked off one by one as they "
         "are named; false shows a cross. Use for requirements, dos and don'ts, things to check, what is included. Never for steps in order (use steps) or for long sentences."),
    sanitize=checklist_sanitize, draw=draw_checklist, cues=checklist_cues, anchors=checklist_anchors, formats=("16:9", "9:16", "1:1", "4:5"),
    samples=[{"heading": "Before you travel", "items": ["Passport valid for six months", "Travel insurance", "Offline maps downloaded"]},
             {"heading": "What counts as a healthy sleep routine", "items": ["Same bedtime every night", "Screens off an hour before bed", "A cool, dark room",
                                                                              "Coffee after 6 pm", "A quiet wind-down habit", "Bright light in the morning"],
              "checked": [True, True, True, False, True, True]}],
)


# ============================================================================= steps
def steps_sanitize(props: Props) -> Props:
    out = []
    for s in _list_of(props.get("steps")):
        if isinstance(s, dict):
            label, detail = _s(s.get("label"), 40), _s(s.get("detail"), 80)
        elif isinstance(s, (str, int, float)) and not isinstance(s, bool):
            label, detail = _s(s, 40), ""
        else:
            continue
        if label:
            out.append({"label": label, **({"detail": detail} if detail else {})})
    out = out[:6]
    if len(out) < 3:
        raise ValueError("steps needs 3+ steps")
    return _with_cues({"title": _s(props.get("title"), 50), "steps": out}, props, len(out))


def steps_anchors(props: Props) -> List[str]:
    return [str(s["label"]) for s in props.get("steps", [])]


def steps_cues(props: Props, dur: float) -> List[float]:
    return reveal_times(len(props.get("steps", [])), dur, props.get("cues"))


def _steps_grid(n: int, bottom: float, top: float) -> Tuple[int, float, float, float, float, float]:
    """(columns, card width, card height, gap x, x0, row gap)"""
    cols = n if n <= 4 else 3
    gx = 64 if cols <= 3 else 56
    cw = (1640 - gx * (cols - 1)) / cols
    rows = math.ceil(n / cols)
    rgap = 60
    ch = min(430.0, (bottom - top - rgap * (rows - 1)) / rows)
    return cols, cw, ch, gx, 140, rgap


def _steps_narrow_grid(fr, n: int, top: float, bottom: float) -> Tuple[int, float, float, float, float, float]:
    """Narrow frames: (columns, card width, card height, gap x, x0, row gap). One column of wide rows when they fit, two columns of compact cards otherwise."""
    avail = bottom - top
    rgap = 26.0
    cols = 1 if (fr.vertical and (fr.aspect == "9:16" or n <= 4)) or n <= 3 else 2
    gx = 44.0
    x0 = float(fr.margin_x)
    cw = (fr.W - 2 * fr.margin_x - gx * (cols - 1)) / cols
    rows = math.ceil(n / cols)
    ch = min(240.0 if cols == 1 else 270.0, (avail - rgap * (rows - 1)) / rows)
    return cols, cw, ch, gx, x0, rgap


def draw_steps(cv: Canvas, props: Props, lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    steps = props["steps"]
    n = len(steps)
    fr = ctx.frame
    land = fr.landscape
    y = heading(cv, th, str(props.get("title", "")), lt, y=ctx.top + 20, ctx=ctx)
    if land:
        cols, cw, ch, gx, x0, rgap = _steps_grid(n, ctx.bottom - 20, y + 20)
    else:
        cols, cw, ch, gx, x0, rgap = _steps_narrow_grid(fr, n, y, ctx.bottom)
    rows = math.ceil(n / cols)
    if land:
        top = y + 20 + ((ctx.bottom - 20 - y - 20) - (rows * ch + (rows - 1) * rgap)) / 2
    else:
        top = y + ((ctx.bottom - y) - (rows * ch + (rows - 1) * rgap)) / 2
    times = reveal_times(n, dur, props.get("cues"))
    ts = fr.type_scale
    for i, st in enumerate(steps):
        col, row = i % cols, i // cols
        cx, cy = x0 + col * (cw + gx), top + row * (ch + rgap)
        p = progress(lt, times[i], 0.55)
        if p <= 0:
            continue
        a = ease_out_cubic(progress(lt, times[i], 0.3))
        e = ease_out_back(p, 1.1)
        dy = (1 - e) * 36
        nxt = times[i + 1] if i + 1 < n else None
        lit = ease_out_cubic(progress(lt, times[i], 0.4)) * (1 - (ease_out_cubic(progress(lt, nxt, 0.4)) if nxt is not None else 0.0))
        cv.card(cx, cy + dy, cw, ch, th, r=28, alpha=a)
        if lit > 0.02:
            cv.rrect(cx, cy + dy, cw, ch, 28, outline=with_alpha(th.accent, a * lit), width=5)
        if land:
            rad = 40
            bx, by = cx + 34 + rad, cy + dy + 34 + rad
            badge_fs = 44
        else:
            rad = 36 if (cols == 1 and ch >= 150) else (28 if cols == 1 else 24)
            badge_fs = 40 if rad >= 36 else 32
        if land:
            cv.ellipse(bx, by, rad, rad, fill=with_alpha(_mix(th.muted, th.accent, lit), a))
            cv.text(bx, by + 1, str(i + 1), "bold", badge_fs, with_alpha(_ink(_mix(th.muted, th.accent, lit)), a), anchor="mm")
            inner = cw - 68
            tcol = _mix(th.muted, th.text, 0.45 + 0.55 * lit)
            l_size, l_lines = cv.fit_text(str(st["label"]), "bold", inner, 150, 46, 32)
            ty = cy + dy + 34 + rad * 2 + 26
            for k, line in enumerate(l_lines):
                cv.text(cx + 34, ty + k * l_size * 1.18, line, "bold", l_size, with_alpha(tcol, a))
            if st.get("detail"):
                d_size, d_lines = cv.fit_text(str(st["detail"]), "regular", inner, max(60.0, ch - (ty - cy - dy) - len(l_lines) * l_size * 1.18 - 50), 36, 28, line_h=1.25)
                dy0 = ty + len(l_lines) * l_size * 1.18 + 14
                for k, line in enumerate(d_lines):
                    cv.text(cx + 34, dy0 + k * d_size * 1.25, line, "regular", d_size, with_alpha(th.muted, a))
            if col < cols - 1 and i + 1 < n:                # a chevron towards the next step in the same row
                ax, ay = cx + cw + gx / 2, cy + dy + ch / 2
                cv.line([(ax - 8, ay - 16), (ax + 8, ay), (ax - 8, ay + 16)], with_alpha(th.accent, a * 0.9), width=6)
            continue
        # ---- narrow frames: the badge on the left of the label; the detail beside the label (one column) or under both (two columns)
        pad = 28.0 if ch >= 190 else (20.0 if cols == 1 else 16.0)
        compact = cols == 2
        tcol = _mix(th.muted, th.text, 0.45 + 0.55 * lit)
        bx, by = cx + pad + rad, cy + dy + pad + rad if compact else cy + dy + ch / 2
        cv.ellipse(bx, by, rad, rad, fill=with_alpha(_mix(th.muted, th.accent, lit), a))
        cv.text(bx, by + 1, str(i + 1), "bold", badge_fs, with_alpha(_ink(_mix(th.muted, th.accent, lit)), a), anchor="mm")
        tx = cx + pad + rad * 2 + 22
        lw = cx + cw - pad - tx
        has_d = bool(st.get("detail"))
        l_max = (ch - 2 * pad) * (0.42 if has_d and not compact else 1.0) if not compact else rad * 2 + 30
        l_size, l_lines = cv.fit_text(str(st["label"]), "bold", lw, max(l_max, 40), 46 * ts if cols == 1 else 40 * ts, 30)
        l_h = len(l_lines) * l_size * 1.18
        if compact:
            ly = cy + dy + pad + max(0.0, (rad * 2 - l_h) / 2)
            for k, line in enumerate(l_lines):
                cv.text(tx, ly + k * l_size * 1.18, line, "bold", l_size, with_alpha(tcol, a))
            dx0, dw0 = cx + pad, cw - 2 * pad
            dy0 = cy + dy + pad + max(rad * 2, l_h) + 12
            d_max = cy + dy + ch - pad * 0.7 - dy0
        else:
            dx0, dw0 = tx, lw
            d_max = ch - 2 * pad - l_h - 8
        d_lines, d_size = [], 0.0
        if has_d:
            d_size, d_lines = cv.fit_text(str(st["detail"]), "regular", dw0, max(d_max, 30), 36 * ts if cols == 1 else 32, 28 if cols == 1 else 24, line_h=1.25)
        d_h = len(d_lines) * d_size * 1.25
        if not compact:
            blk = l_h + (8 + d_h if has_d else 0)
            ly = cy + dy + (ch - blk) / 2
            for k, line in enumerate(l_lines):
                cv.text(tx, ly + k * l_size * 1.18, line, "bold", l_size, with_alpha(tcol, a))
            dy0 = ly + l_h + 8
        for k, line in enumerate(d_lines):
            cv.text(dx0, dy0 + k * d_size * 1.25, line, "regular", d_size, with_alpha(th.muted, a))
        if i + 1 < n:
            if col < cols - 1:                               # towards the next step in the same row
                ax, ay = cx + cw + gx / 2, cy + dy + ch / 2
                cv.line([(ax - 6, ay - 13), (ax + 6, ay), (ax - 6, ay + 13)], with_alpha(th.accent, a * 0.9), width=5)
            elif cols == 1:                                  # down, in the gap under the badge column
                ax, ay = bx, cy + dy + ch + rgap / 2
                cv.line([(ax - 12, ay - 5), (ax, ay + 6), (ax + 12, ay - 5)], with_alpha(th.accent, a * 0.9), width=5)


STEPS = Element(
    name="steps", family="Process",
    doc=("- steps: {title (<=50), steps: 3-6 [{label (<=40), detail (<=80, optional)}]}. A numbered process in cards with chevrons; each step lights up as it is named, "
         "earlier ones stay visible but muted. Use for how to do something, a procedure, a recipe, a sequence that must happen in order. "
         "Never for unordered points (use bullets/checklist) or branching flows (use diagram)."),
    sanitize=steps_sanitize, draw=draw_steps, cues=steps_cues, anchors=steps_anchors, formats=("16:9", "9:16", "1:1", "4:5"),
    samples=[{"title": "How a bill becomes law", "steps": [{"label": "Proposal", "detail": "A member writes and introduces the bill"},
                                                         {"label": "Committee", "detail": "It is studied, amended and voted on"},
                                                         {"label": "Floor vote"}, {"label": "Signature", "detail": "The head of state signs it"}]},
             {"title": "Brewing a good cup of coffee", "steps": [{"label": "Grind fresh", "detail": "Medium-coarse for a pour over"}, {"label": "Heat the water", "detail": "About 93 degrees"},
                                                                  {"label": "Rinse the filter"}, {"label": "Bloom", "detail": "Wet the grounds and wait 30 seconds"},
                                                                  {"label": "Pour slowly", "detail": "In circles, in three stages"}, {"label": "Serve", "detail": "Drink while it is hot"}]}],
)


# ============================================================================= funnel
def funnel_sanitize(props: Props) -> Props:
    out = []
    for s in _list_of(props.get("stages")):
        if isinstance(s, dict):
            label, value = _s(s.get("label"), 30), _s(s.get("value"), 12)
        elif isinstance(s, (str, int, float)) and not isinstance(s, bool):
            label, value = _s(s, 30), ""
        else:
            continue
        if label:
            out.append({"label": label, **({"value": value} if value else {})})
    out = out[:5]
    if len(out) < 3:
        raise ValueError("funnel needs 3+ stages")
    return _with_cues({"title": _s(props.get("title"), 50), "stages": out}, props, len(out))


def funnel_anchors(props: Props) -> List[str]:
    return [str(s["label"]) for s in props.get("stages", [])]


def funnel_cues(props: Props, dur: float) -> List[float]:
    return reveal_times(len(props.get("stages", [])), dur, props.get("cues"))


def draw_funnel(cv: Canvas, props: Props, lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    stages = props["stages"]
    n = len(stages)
    fr = ctx.frame
    land = fr.landscape
    stacked = fr.vertical                                  # 9:16 and 4:5: bands span the width, each label under its band; square and landscape: labels to the right
    y = heading(cv, th, str(props.get("title", "")), lt, y=ctx.top + 20, ctx=ctx)
    gap = 8
    avail = ctx.bottom - y - 20
    lab_h = 0.0
    if stacked:
        lab_size = 44.0 * fr.type_scale if fr.aspect == "9:16" else 44.0
        lab_h = lab_size * 1.25 + 12
        sh = min(190.0, (avail - n * lab_h - gap * (n - 1)) / n)      # band height
        blk = sh + lab_h
        top = y + 10 + (avail - (n * blk + gap * (n - 1))) / 2
        w_top, w_bot = fr.W - 2 * fr.margin_x, (fr.W - 2 * fr.margin_x) * 0.36
        fx = fr.cx
    elif land:
        sh = min(140.0, (avail - gap * (n - 1)) / n)
        top = y + 10 + (avail - (n * sh + gap * (n - 1))) / 2
        w_top, w_bot = 940.0, 360.0
        fx = 140 + w_top / 2                               # funnel axis (left), labels to the right
    else:                                                  # square: a narrower funnel on the left, labels to the right
        sh = min(140.0, (avail - gap * (n - 1)) / n)
        top = y + 10 + (avail - (n * sh + gap * (n - 1))) / 2
        w_top, w_bot = 400.0, 170.0
        fx = fr.margin_x + w_top / 2
    blk = sh + lab_h
    times = reveal_times(n, dur, props.get("cues"))
    wid = lambda k: w_top - (w_top - w_bot) * k / n        # noqa: E731
    for i, st in enumerate(stages):
        p = progress(lt, times[i], 0.55)
        if p <= 0:
            continue
        a = ease_out_cubic(progress(lt, times[i], 0.3))
        e = ease_out_cubic(p)
        t0 = top + i * (blk + gap) + (1 - e) * -26
        wt, wb = wid(i), wid(i + 1) - 12
        s = 0.8 + 0.2 * e
        col = _mix(th.accent, th.accent2, i / max(1, n - 1))
        poly = [(fx - wt / 2 * s, t0), (fx + wt / 2 * s, t0), (fx + wb / 2 * s, t0 + sh), (fx - wb / 2 * s, t0 + sh)]
        cv.polygon(poly, with_alpha(col, a))
        ink = _ink(col)
        v = str(st.get("value", ""))
        mid_w = (wt + wb) / 2 - (90 if land else 60)
        if v:
            vs, vl = cv.fit_text(v, "bold", mid_w, sh * 0.8, min(72.0 if land else 72.0 * fr.type_scale, sh * 0.62), 28)
            cv.text(fx, t0 + sh / 2 + 2, vl[0] if vl else v, "bold", vs, with_alpha(ink, a), anchor="mm")
        else:
            cv.text(fx, t0 + sh / 2 + 2, str(i + 1), "bold", min(60.0, sh * 0.55), with_alpha(ink, a), anchor="mm")
        la = ease_out_cubic(progress(lt, times[i] + 0.15, 0.4))
        if stacked:
            l_size, l_lines = cv.fit_text(str(st["label"]), "semibold", fr.W - 2 * fr.margin_x, lab_h - 8, lab_size, 30)
            cv.text(fx, t0 + sh + 8 + (1 - la) * 14, l_lines[0] if len(l_lines) == 1 else " ".join(l_lines), "semibold", l_size if len(l_lines) == 1 else 30, with_alpha(th.text, la), anchor="ma")
            continue
        lx = (140 if land else fr.margin_x) + w_top + (70 if land else 56)
        cv.line([(fx + wid(i + 1) / 2 * s + 20, t0 + sh / 2), (lx - 22, t0 + sh / 2)], with_alpha(th.card_outline, la), width=3, round_caps=False)
        l_size, l_lines = cv.fit_text(str(st["label"]), "semibold", (1780 if land else fr.W - fr.margin_x) - lx, sh - 8, 50 if land else 44, 32 if land else 30)
        for k, line in enumerate(l_lines):
            cv.text(lx, t0 + sh / 2 + (k - (len(l_lines) - 1) / 2) * l_size * 1.18 + (1 - la) * 14, line, "semibold", l_size, with_alpha(th.text, la), anchor="lm")


FUNNEL = Element(
    name="funnel", family="Process",
    doc=("- funnel: {title (<=50), stages: 3-5 [{label (<=30), value (<=12, optional, e.g. \"10,000\" or \"12%\")}]}. Stages that narrow top to bottom, revealed in order as they "
         "are named, the value shown big inside. Use for conversion, selection, filtering, anything that loses members at each stage. Values only from the grounding "
         "notes, never invented. Never for a plain ordered process (use steps) or for a ranking."),
    sanitize=funnel_sanitize, draw=draw_funnel, cues=funnel_cues, anchors=funnel_anchors, formats=("16:9", "9:16", "1:1", "4:5"),
    samples=[{"title": "From visitor to customer", "stages": [{"label": "Visit the site", "value": "10,000"}, {"label": "Sign up", "value": "1,200"},
                                                              {"label": "Try the product", "value": "400"}, {"label": "Pay", "value": "90"}]},
             {"title": "How a vaccine reaches approval", "stages": [{"label": "Lab research"}, {"label": "Animal studies"}, {"label": "Phase 1 trial"}, {"label": "Phase 2 trial"},
                                                                    {"label": "Phase 3 trial and approval"}]}],
)

ELEMENTS = [KINETIC, DEFINITION, COUNTER, CHECKLIST, STEPS, FUNNEL]
