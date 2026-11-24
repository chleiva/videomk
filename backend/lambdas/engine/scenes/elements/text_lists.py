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
from ...easing import ease_out_back, ease_out_cubic, ease_out_expo, progress, reveal_times
from ...theme import Theme
from ..base import CENTER_X, CONTENT_TOP, SceneCtx, format_number, heading, parse_number
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


def _mid_y(ctx: SceneCtx) -> float:
    return (CONTENT_TOP + ctx.bottom) / 2


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
def _kinetic_layout(words: Tuple[str, ...], flags: Tuple[bool, ...], ss: int, max_h: int):
    """Largest size at which the sentence fits; returns (size, lines, total_h) with lines = [(line_h, [(word index, x, width, font size)])], x centred on 0."""
    max_w = 1560
    for size in range(136, 44, -4):
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
        if total <= max_h:
            return size, out, total
    return 44, out, total


def kinetic_cues(props: Props, dur: float) -> List[float]:
    groups = kinetic_groups(props)
    times = reveal_times(len(groups), dur, props.get("cues"), first=0.15, last=0.7)
    pick = [times[0]] if times else []
    pick += [times[k] for k, g in enumerate(groups) if g[1]][:1]
    return pick


def draw_kinetic(cv: Canvas, props: Props, lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    words = tuple(str(props.get("text", "")).split())
    if not words:
        return
    groups = kinetic_groups(props)
    flags = [False] * len(words)
    for idx, em in groups:
        for i in idx:
            flags[i] = em
    avail = ctx.bottom - CONTENT_TOP - 110
    size, lines, total = _kinetic_layout(words, tuple(flags), cv.ss, int(avail))
    when = [0.0] * len(words)
    times = reveal_times(len(groups), dur, props.get("cues"), first=0.15, last=0.7)
    for g, (idx, _) in enumerate(groups):
        for k, i in enumerate(idx):
            when[i] = times[g] + 0.07 * k
    top = _mid_y(ctx) - (total + 60) / 2
    y = top
    for lh, items in lines:
        base = y + lh * 0.84
        for i, ox, ww, fs in items:
            p = ease_out_back(progress(lt, when[i], 0.45), 1.2)
            a = ease_out_cubic(progress(lt, when[i], 0.3))
            col = th.accent if flags[i] else th.text
            cv.text(CENTER_X + ox, base + (1 - p) * 34, words[i], "bold", fs, with_alpha(col, a), anchor="ls")
        y += lh
    end = max(when) + 0.45
    bw = 220 * ease_out_expo(progress(lt, end, 0.6))
    cv.rrect(CENTER_X - bw / 2, y + 36, bw, 10, 5, fill=th.accent)


KINETIC = Element(
    name="kinetic_text", family="Text",
    doc=("- kinetic_text: {text (<=140, one sentence), emphasis (optional, a word or short phrase that occurs in text)}. The sentence appears word by word with the voice, "
         "large and centred, the emphasis bigger in the accent colour. Use for a thesis, a rule, a punchline, the one sentence to remember. "
         "Never for several ideas, never the same sentence the caption already shows alone, at most 3 per video."),
    sanitize=kinetic_sanitize, draw=draw_kinetic, cues=kinetic_cues, anchors=kinetic_anchors, max_per_video=3,
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


def draw_definition(cv: Canvas, props: Props, lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    term, defn = str(props["term"]), str(props["definition"])
    origin, example = str(props.get("origin", "")), str(props.get("example", ""))
    t = _definition_times(props, dur)
    cw = 1560
    tx = CENTER_X - cw / 2 + 90
    inner = cw - 180
    t_size, t_lines = cv.fit_text(term, "bold", inner, 230, 136, 60)
    d_size, d_lines = cv.fit_text(defn, "semibold", inner, 330, 66, 40, line_h=1.28)
    o_size, o_lines = (cv.fit_text(origin, "regular", inner - 200, 120, 46, 32) if origin else (0, []))
    e_size, e_lines = (cv.fit_text(example, "regular", inner - 200, 120, 46, 32) if example else (0, []))
    t_h, d_h = len(t_lines) * t_size * 1.15, len(d_lines) * d_size * 1.28
    o_h, e_h = len(o_lines) * o_size * 1.25, len(e_lines) * e_size * 1.25
    extra = (max(o_h, 48) + 28 if origin else 0) + (max(e_h, 48) + 28 if example else 0)
    card_h = 70 + t_h + 40 + d_h + (34 + extra if extra else 0) + 70
    top = _mid_y(ctx) - card_h / 2
    pc = ease_out_cubic(progress(lt, 0.0, 0.6))
    cv.card(CENTER_X - cw / 2, top + (1 - pc) * 30, cw, card_h, th, r=36, alpha=pc)
    cv.rrect(CENTER_X - cw / 2 + 36, top + 56 + (1 - pc) * 30, 10, t_h + 40 + d_h - 8 + 28, 5, fill=with_alpha(th.accent, pc))
    y = top + 70
    p = ease_out_cubic(progress(lt, t[0], 0.6))
    for i, line in enumerate(t_lines):
        cv.text(tx, y + i * t_size * 1.15 + (1 - p) * 26, line, "bold", t_size, with_alpha(th.accent, p))
    y += t_h + 40
    p = ease_out_cubic(progress(lt, t[1], 0.6))
    for i, line in enumerate(d_lines):
        cv.text(tx, y + i * d_size * 1.28 + (1 - p) * 20, line, "semibold", d_size, with_alpha(th.text, p))
    y += d_h + 34
    k = 2
    for label, size, lines, hh, present in (("ORIGIN", o_size, o_lines, o_h, bool(origin)), ("EXAMPLE", e_size, e_lines, e_h, bool(example))):
        if not present:
            continue
        p = ease_out_cubic(progress(lt, t[k], 0.55))
        k += 1
        cv.rrect(tx, y - 6, inner, 2, 1, fill=with_alpha(th.card_outline, p))
        y += 14
        cv.text(tx, y + 8, label, "bold", 28, with_alpha(th.accent2, p))
        for i, line in enumerate(lines):
            cv.text(tx + 200, y + i * size * 1.25 + (1 - p) * 14, line, "regular", size, with_alpha(th.muted, p))
        y += max(hh, 48) + 14


DEFINITION = Element(
    name="definition", family="Text",
    doc=("- definition: {term (<=40), definition (<=160), origin (<=80, optional), example (<=100, optional)}. A card: the term, its plain definition, then the origin "
         "and an example. Use when the narration defines a term or names where a word comes from. Never invent or improve a definition: it must come from the "
         "grounding notes (or be plain common knowledge); leave origin and example out unless the notes give them."),
    sanitize=definition_sanitize, draw=draw_definition, cues=definition_cues,
    samples=[{"term": "Inflation", "definition": "A general rise in prices over time, so the same money buys less than before."},
             {"term": "Serendipity", "definition": "Finding something valuable or pleasant by chance while looking for something else entirely.",
              "origin": "Coined by Horace Walpole in 1754, from a Persian fairy tale.", "example": "Penicillin was discovered when mould spoiled a lab dish."}],
)


# ============================================================================= counter
_PLAIN_NUM = re.compile(r"^[+\-]?[\d,]*\.?\d+$")


def _num_parts(v: Any) -> Optional[Tuple[str, float, int, str, bool]]:
    if isinstance(v, bool) or v is None:
        return None
    p = parse_number(_s(v, 24))
    if not p or not math.isfinite(p[1]) or abs(p[1]) > 1e15:
        return None
    if re.search(r"\d", p[0] + p[3]):
        return None                                    # "4 to 5", "10 in 2020": not one number
    return p


def counter_sanitize(props: Props) -> Props:
    p = _num_parts(props.get("value"))
    if not p:
        raise ValueError("counter needs a numeric value")
    pre, val, dec, suf, comma = p
    dec = min(dec, 6)
    f = _num_parts(props.get("from")) if props.get("from") not in (None, "") else None
    prefix = _s(props.get("prefix"), 4) or (pre.strip() if len(pre.strip()) <= 4 else "")
    unit = _s(props.get("unit"), 8) or (suf.strip() if len(suf.strip()) <= 8 else "")
    comma = comma or (f is not None and f[4])
    clean: Props = {"value": format_number(val, dec, comma)}
    if prefix:
        clean["prefix"] = prefix
    if unit:
        clean["unit"] = unit
    clean["label"] = _s(props.get("label"), 70)
    if f is not None and f[1] != 0:
        clean["from"] = format_number(f[1], dec, comma)
    delta = _s(props.get("delta"), 24)
    if delta:
        clean["delta"] = delta
    return _with_cues(clean, props, 1)


def counter_anchors(props: Props) -> List[str]:
    return [str(props.get("value", ""))]


def counter_cues(props: Props, dur: float) -> List[float]:
    return [_count_start(props, dur)]


def _count_start(props: Props, dur: float) -> float:
    cue = (props.get("cues") or [0.4])[0]
    return max(0.2, min(float(cue), max(0.2, dur - 3.0)))


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
    pre, val, dec, _, comma = parse_number(props["value"])  # type: ignore[misc]
    frm_p = parse_number(props.get("from") or "0")
    frm = frm_p[1] if frm_p else 0.0
    prefix, unit = str(props.get("prefix", "")), str(props.get("unit", ""))
    label, delta = str(props.get("label", "")), str(props.get("delta", ""))
    start = _count_start(props, dur)
    cdur = max(0.8, min(2.2, dur - start - 0.5))
    p = ease_out_expo(progress(lt, start, cdur))
    shown = format_number(frm + (val - frm) * p, dec, comma)
    final = format_number(val, dec, comma)
    # one size for the whole animation, from the widest the number gets
    widest = max(final, format_number(frm, dec, comma), key=len)
    size = 320.0
    while size > 90:
        w = _tabular_width(cv, widest, size) + (cv.measure(prefix, "bold", size * 0.55) + 14 if prefix else 0) + (cv.measure(unit, "bold", size * 0.55) + 14 if unit else 0)
        if w <= 1560:
            break
        size -= 8
    small = size * 0.55
    wp = cv.measure(prefix, "bold", small) + 14 if prefix else 0
    wu = cv.measure(unit, "bold", small) + 14 if unit else 0
    wn = _tabular_width(cv, shown, size)
    total_w = _tabular_width(cv, widest, size) + wp + wu
    l_size, l_lines = cv.fit_text(label, "semibold", 1400, 150, 56, 36) if label else (0, [])
    chip_h = 76 if delta else 0
    block = size * 0.74 + (78 + len(l_lines) * l_size * 1.25 if label else 0) + (36 + chip_h if delta else 0)
    top = _mid_y(ctx) - block / 2 - 10
    base = top + size * 0.74
    fade = ease_out_cubic(progress(lt, 0.05, 0.5))
    rise = (1 - fade) * 30
    x = CENTER_X - total_w / 2 + (total_w - wp - wu - wn) / 2   # keep the digits centred while they grow
    col = with_alpha(th.text, fade)
    if prefix:
        cv.text(x, base - size * 0.18 + rise, prefix, "bold", small, with_alpha(th.accent, fade), anchor="ls")
    _tabular_draw(cv, x + wp, base + rise, shown, size, col)
    if unit:
        cv.text(x + wp + wn + 14, base - size * 0.18 + rise, unit, "bold", small, with_alpha(th.accent, fade), anchor="ls")
    y = base + 78
    if label:
        a = ease_out_cubic(progress(lt, 0.6, 0.6))
        for i, line in enumerate(l_lines):
            cv.text(CENTER_X, y + i * l_size * 1.25 + (1 - a) * 16, line, "semibold", l_size, with_alpha(th.muted, a), anchor="ma")
        y += len(l_lines) * l_size * 1.25
    if delta:
        a = ease_out_back(progress(lt, start + cdur * 0.8, 0.5), 1.2)
        aa = ease_out_cubic(progress(lt, start + cdur * 0.8, 0.35))
        fs = 40
        dw = cv.measure(delta, "semibold", fs) + 56 + 44
        cx0, cy0 = CENTER_X - dw / 2, y + 36
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
    doc=("- counter: {value (a number like \"4.2\", \"73\" or \"1,250\"), unit (<=8, e.g. \"%\" or \"km\"), prefix (<=4, e.g. \"$\"), label (<=70), from (optional start number, default 0), "
         "delta (<=24, optional, e.g. \"+12% vs 2020\")}. A big number that counts up (or down from `from`) as it is named. Use for one headline figure, a growth, a total. "
         "Only numbers that appear in the grounding notes; never invent or round a figure; not for several numbers (use chart)."),
    sanitize=counter_sanitize, draw=draw_counter, cues=counter_cues, anchors=counter_anchors,
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


def draw_checklist(cv: Canvas, props: Props, lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    items = [str(i) for i in props["items"]]
    n = len(items)
    checked = [bool(c) for c in props.get("checked", [])] + [True] * n
    y = heading(cv, th, str(props.get("heading", "")), lt, y=CONTENT_TOP + 20)
    gap = 18
    avail = ctx.bottom - y - 10
    card_h = max(84.0, min(126.0, (avail - gap * (n - 1)) / n))
    font_px = 46 if card_h > 110 else 40
    x0, w = 140, 1640
    times = reveal_times(n, dur, props.get("cues"))
    r = min(34.0, card_h * 0.3)
    for i, text in enumerate(items):
        p = progress(lt, times[i], 0.5)
        if p <= 0:
            continue
        a = ease_out_cubic(progress(lt, times[i], 0.3))
        dx = (1 - ease_out_cubic(p)) * -70
        cy = y + i * (card_h + gap)
        cv.card(x0 + dx, cy, w, card_h, th, r=24, alpha=a)
        mx, my = x0 + dx + 46 + r, cy + card_h / 2
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
        lines = cv.wrap(text, "semibold", font_px, w - 150 - r * 2)[:2]
        lh = font_px * 1.22
        ty = my - (len(lines) * lh) / 2 - lh * 0.06
        tcol = th.text if ok else th.muted
        for li, line in enumerate(lines):
            cv.text(x0 + dx + 46 + r * 2 + 34, ty + li * lh, line, "semibold", font_px, with_alpha(tcol, a))


CHECKLIST = Element(
    name="checklist", family="Lists",
    doc=("- checklist: {heading (<=50), items: 2-6 strings (<=70), checked: optional list of true/false, one per item (default all true)}. Rows ticked off one by one as they "
         "are named; false shows a cross. Use for requirements, dos and don'ts, things to check, what is included. Never for steps in order (use steps) or for long sentences."),
    sanitize=checklist_sanitize, draw=draw_checklist, cues=checklist_cues, anchors=checklist_anchors,
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


def draw_steps(cv: Canvas, props: Props, lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    steps = props["steps"]
    n = len(steps)
    y = heading(cv, th, str(props.get("title", "")), lt, y=CONTENT_TOP + 20)
    cols, cw, ch, gx, x0, rgap = _steps_grid(n, ctx.bottom - 20, y + 20)
    rows = math.ceil(n / cols)
    top = y + 20 + ((ctx.bottom - 20 - y - 20) - (rows * ch + (rows - 1) * rgap)) / 2
    times = reveal_times(n, dur, props.get("cues"))
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
        rad = 40
        bx, by = cx + 34 + rad, cy + dy + 34 + rad
        cv.ellipse(bx, by, rad, rad, fill=with_alpha(_mix(th.muted, th.accent, lit), a))
        cv.text(bx, by + 1, str(i + 1), "bold", 44, with_alpha(_ink(_mix(th.muted, th.accent, lit)), a), anchor="mm")
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


STEPS = Element(
    name="steps", family="Process",
    doc=("- steps: {title (<=50), steps: 3-6 [{label (<=40), detail (<=80, optional)}]}. A numbered process in cards with chevrons; each step lights up as it is named, "
         "earlier ones stay visible but muted. Use for how to do something, a procedure, a recipe, a sequence that must happen in order. "
         "Never for unordered points (use bullets/checklist) or branching flows (use diagram)."),
    sanitize=steps_sanitize, draw=draw_steps, cues=steps_cues, anchors=steps_anchors,
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
    y = heading(cv, th, str(props.get("title", "")), lt, y=CONTENT_TOP + 20)
    gap = 8
    avail = ctx.bottom - y - 20
    sh = min(140.0, (avail - gap * (n - 1)) / n)
    top = y + 10 + (avail - (n * sh + gap * (n - 1))) / 2
    w_top, w_bot = 940.0, 360.0
    fx = 140 + w_top / 2                                   # funnel axis (left), labels to the right
    times = reveal_times(n, dur, props.get("cues"))
    wid = lambda k: w_top - (w_top - w_bot) * k / n        # noqa: E731
    for i, st in enumerate(stages):
        p = progress(lt, times[i], 0.55)
        if p <= 0:
            continue
        a = ease_out_cubic(progress(lt, times[i], 0.3))
        e = ease_out_cubic(p)
        t0 = top + i * (sh + gap) + (1 - e) * -26
        wt, wb = wid(i), wid(i + 1) - 12
        s = 0.8 + 0.2 * e
        col = _mix(th.accent, th.accent2, i / max(1, n - 1))
        poly = [(fx - wt / 2 * s, t0), (fx + wt / 2 * s, t0), (fx + wb / 2 * s, t0 + sh), (fx - wb / 2 * s, t0 + sh)]
        cv.polygon(poly, with_alpha(col, a))
        ink = _ink(col)
        v = str(st.get("value", ""))
        mid_w = (wt + wb) / 2 - 90
        if v:
            vs, vl = cv.fit_text(v, "bold", mid_w, sh * 0.8, min(72.0, sh * 0.62), 28)
            cv.text(fx, t0 + sh / 2 + 2, vl[0] if vl else v, "bold", vs, with_alpha(ink, a), anchor="mm")
        else:
            cv.text(fx, t0 + sh / 2 + 2, str(i + 1), "bold", min(60.0, sh * 0.55), with_alpha(ink, a), anchor="mm")
        la = ease_out_cubic(progress(lt, times[i] + 0.15, 0.4))
        lx = 140 + w_top + 70
        cv.line([(fx + wid(i + 1) / 2 * s + 20, t0 + sh / 2), (lx - 22, t0 + sh / 2)], with_alpha(th.card_outline, la), width=3, round_caps=False)
        l_size, l_lines = cv.fit_text(str(st["label"]), "semibold", 1780 - lx, sh - 8, 50, 32)
        for k, line in enumerate(l_lines):
            cv.text(lx, t0 + sh / 2 + (k - (len(l_lines) - 1) / 2) * l_size * 1.18 + (1 - la) * 14, line, "semibold", l_size, with_alpha(th.text, la), anchor="lm")


FUNNEL = Element(
    name="funnel", family="Process",
    doc=("- funnel: {title (<=50), stages: 3-5 [{label (<=30), value (<=12, optional, e.g. \"10,000\" or \"12%\")}]}. Stages that narrow top to bottom, revealed in order as they "
         "are named, the value shown big inside. Use for conversion, selection, filtering, anything that loses members at each stage. Values only from the grounding "
         "notes, never invented. Never for a plain ordered process (use steps) or for a ranking."),
    sanitize=funnel_sanitize, draw=draw_funnel, cues=funnel_cues, anchors=funnel_anchors,
    samples=[{"title": "From visitor to customer", "stages": [{"label": "Visit the site", "value": "10,000"}, {"label": "Sign up", "value": "1,200"},
                                                              {"label": "Try the product", "value": "400"}, {"label": "Pay", "value": "90"}]},
             {"title": "How a vaccine reaches approval", "stages": [{"label": "Lab research"}, {"label": "Animal studies"}, {"label": "Phase 1 trial"}, {"label": "Phase 2 trial"},
                                                                    {"label": "Phase 3 trial and approval"}]}],
)

ELEMENTS = [KINETIC, DEFINITION, COUNTER, CHECKLIST, STEPS, FUNNEL]
