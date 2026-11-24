"""Family `Code and math`: `code` (an editor / terminal / diff panel with typed-on, syntax-coloured code and step highlights) and
`equation` (a small Pillow typesetter: fractions, scripts, roots, big operators with limits, Greek, parentheses; steps revealed one after another).

Only Pillow is used. Fonts bundled in engine/assets/fonts: DejaVu Sans Mono (code), STIX General (math). See docs/ELEMENT_CODE_MATH.md.
"""
import math
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFont

from ...canvas import FONT_DIR, Canvas, with_alpha
from ...easing import ease_in_out_cubic, ease_out_cubic, progress, reveal_times
from ...theme import Theme
from ..base import CONTENT_TOP, SceneCtx, heading
from ..registry import Element

FAMILY = "Code and math"


# ============================================================================== shared helpers
def _clean_text(v: Any, n: int) -> str:
    s = "" if v is None or isinstance(v, (dict, list)) else str(v)
    s = "".join(ch if (ch.isprintable() and ch not in "\u202e\u202d\u200f\u200e") else " " for ch in s)
    return re.sub(r"\s+", " ", s).strip()[:n].strip()


@lru_cache(maxsize=32)
def _ttf(name: str, px: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(os.path.join(FONT_DIR, name), px)


def _draw_text(cv: Canvas, x: float, y: float, s: str, font_file: str, size: float, fill, anchor: str = "ls") -> None:
    """Like Canvas.text but with one of this module's fonts; honours the fill's alpha."""
    if not s:
        return
    a = int(fill[3]) if len(fill) == 4 else 255
    if a <= 0:
        return
    font = _ttf(font_file, max(1, cv._s(size)))
    X, Y = cv._s(x), cv._s(y)
    if a >= 255:
        cv.d.text((X, Y), s, font=font, fill=tuple(fill[:3]) + (255,), anchor=anchor)
        return
    l, t, r, b = cv.d.textbbox((X, Y), s, font=font, anchor=anchor)
    box = (max(0, int(l) - 3), max(0, int(t) - 3), min(cv.im.width, int(r) + 3), min(cv.im.height, int(b) + 3))
    if box[2] <= box[0] or box[3] <= box[1]:
        return
    mask = Image.new("L", (box[2] - box[0], box[3] - box[1]), 0)
    ImageDraw.Draw(mask).text((X - box[0], Y - box[1]), s, font=font, fill=255, anchor=anchor)
    cv.im.paste(tuple(fill[:3]), box, mask.point(lambda v: v * a // 255))


def _mix(c: Sequence[int], bg: Sequence[int], k: float) -> Tuple[int, int, int]:
    """k=1 -> c, k=0 -> bg."""
    k = max(0.0, min(1.0, k))
    return (int(bg[0] + (c[0] - bg[0]) * k), int(bg[1] + (c[1] - bg[1]) * k), int(bg[2] + (c[2] - bg[2]) * k))


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def _clean_cues(v: Any, n: int) -> List[float]:
    return [float(c) for c in (v if isinstance(v, list) else []) if isinstance(c, (int, float)) and not isinstance(c, bool) and math.isfinite(c)][:n]


# ============================================================================== code: tokenizer
MONO, MONO_BOLD = "DejaVuSansMono.ttf", "DejaVuSansMono-Bold.ttf"
MONO_ADV = 0.602   # DejaVu Sans Mono advance width / em

MAX_LINES, MAX_COLS, MAX_CHARS = 18, 70, 900

ALIASES = {"js": "javascript", "node": "javascript", "ts": "typescript", "py": "python", "python3": "python", "sh": "bash", "shell": "bash", "zsh": "bash",
           "c++": "cpp", "cs": "csharp", "c#": "csharp", "golang": "go", "rs": "rust", "yml": "yaml", "htm": "html", "postgres": "sql", "mysql": "sql"}

_KW_SRC = {
    "python": "and as assert async await break class continue def del elif else except finally for from global if import in is lambda not or pass raise return try while with yield None True False",
    "javascript": "const let var function return if else for while do switch case break continue new class extends import from export default async await try catch finally throw typeof instanceof this null undefined true false of in static void delete",
    "typescript": "const let var function return if else for while do switch case break continue new class extends implements import from export default async await try catch finally throw typeof instanceof this null undefined true false of in static void interface type enum readonly public private protected",
    "java": "public private protected static final class interface extends implements new return if else for while do switch case break continue try catch finally throw throws import package void int long double float boolean char byte short null true false this super abstract",
    "csharp": "public private protected static readonly class interface new return if else for foreach while do switch case break continue try catch finally throw using namespace void int long double float bool char string var null true false this base async await in",
    "go": "package import func return if else for range switch case break continue defer go chan select struct interface map type var const nil true false",
    "rust": "fn let mut pub use mod struct enum impl trait match if else for while loop return break continue self Self as in ref move async await true false where const static",
    "c": "if else for while do switch case break continue return typedef struct enum union static const void int long double float char unsigned signed sizeof NULL",
    "cpp": "if else for while do switch case break continue return typedef struct class enum union static const void int long double float char bool unsigned signed sizeof nullptr new delete namespace using template typename public private auto true false",
    "sql": "select from where group by order having join left right inner outer on as and or not null insert into values update set delete create table drop alter index primary key foreign references limit offset distinct union all case when then else end like in is between exists desc asc",
    "bash": "if then else elif fi for while do done case esac function in return export local",
    "json": "true false null",
    "yaml": "true false null",
}
_KW = {k: frozenset(v.split()) for k, v in _KW_SRC.items()}
_FAMILY = {"python": "hash", "bash": "hash", "yaml": "hash", "sql": "sql", "html": "html", "json": "json"}   # everything else: clike

_STR = r"""(?P<string>"(?:\\.|[^"\\])*"?|'(?:\\.|[^'\\])*'?|`[^`]*`?)"""
_NUM = r"(?P<number>\b0x[0-9a-fA-F]+\b|\b\d[\d_]*(?:\.\d+)?(?:[eE][+-]?\d+)?\b)"
_IDENT = r"(?P<ident>[A-Za-z_$][A-Za-z_0-9$]*)"
_COMMENT = {"hash": r"(?P<comment>#.*)", "clike": r"(?P<comment>//.*|/\*.*?(?:\*/|$))", "sql": r"(?P<comment>--.*)", "html": r"(?P<comment><!--.*?(?:-->|$))", "json": ""}
_RX: Dict[str, "re.Pattern[str]"] = {}


def _rx(family: str) -> "re.Pattern[str]":
    if family not in _RX:
        parts = [_COMMENT[family]]
        if family == "html":
            parts.append(r"(?P<tag></?[A-Za-z][\w-]*)")
        if family == "hash":
            parts.append(r"(?P<flag>(?<![\w])--?[A-Za-z][\w-]*)")
            parts.append(r"(?P<var>\$[A-Za-z_]\w*|\$\{[^}]*\})")
        parts += [_STR, _NUM, _IDENT, r"(?P<space>\s+)", r"(?P<other>.)"]
        _RX[family] = re.compile("|".join(p for p in parts if p))
    return _RX[family]


@lru_cache(maxsize=512)
def tokenize(line: str, lang: str) -> Tuple[Tuple[int, str, str], ...]:
    """One line -> ((column, text, kind), ...); kinds: keyword string comment number func type punct text flag var tag attr prompt."""
    fam = _FAMILY.get(lang, "clike")
    kws = _KW.get(lang, frozenset())
    ci = lang == "sql"
    out: List[Tuple[int, str, str]] = []
    first_word = lang == "bash"
    for m in _rx(fam).finditer(line):
        kind, text = m.lastgroup or "other", m.group()
        if kind == "ident":
            rest = line[m.end():].lstrip()
            if (text.lower() if ci else text) in kws:
                kind = "keyword"
            elif first_word:
                kind = "func"
            elif rest.startswith("(") and fam != "json":
                kind = "func"
            elif text[:1].isupper() and len(text) > 1 and not text.isupper():
                kind = "type"
            elif fam == "html" and rest.startswith("="):
                kind = "attr"
            else:
                kind = "text"
        elif kind == "string" and fam == "json" and line[m.end():].lstrip().startswith(":"):
            kind = "func"
        elif kind == "other":
            kind = "punct" if text in "{}[]()<>;,.:=+-*/%&|!?^~@" else "text"
        elif kind == "space":
            kind = "text"
        if kind != "text":
            first_word = False
        elif text.strip():
            first_word = False
        out.append((m.start(), text, kind))
    return tuple(out)


PALETTE = {   # fixed: the panel is dark on every theme
    "text": (226, 232, 240), "keyword": (192, 132, 252), "string": (134, 239, 172), "comment": (113, 128, 150), "number": (251, 191, 36),
    "func": (96, 165, 250), "type": (45, 212, 191), "punct": (148, 163, 184), "prompt": (74, 222, 128), "flag": (251, 191, 36), "var": (244, 114, 182),
    "tag": (192, 132, 252), "attr": (125, 211, 252), "out": (203, 213, 225), "err": (248, 113, 113), "warn": (251, 191, 36),
}
PANEL = (17, 20, 30)
CHROME = (28, 32, 45)
GUTTER = (86, 98, 120)
ADD, DEL = (34, 197, 94), (239, 68, 68)


# ============================================================================== code: props
def _norm_lang(v: Any) -> str:
    s = re.sub(r"[^a-z0-9+#_-]", "", _clean_text(v, 12).lower())
    return ALIASES.get(s, s)[:12]


def sanitize_code(props: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(props, dict):
        raise ValueError("code props must be an object")
    raw = props.get("code")
    if not isinstance(raw, str):
        raise ValueError("code is required")
    raw = raw.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    lines = ["".join(ch for ch in ln if ch.isprintable()).rstrip()[:MAX_COLS].rstrip() for ln in raw.split("\n")]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    lines = lines[:MAX_LINES]
    while lines and len("\n".join(lines)) > MAX_CHARS:
        lines.pop()
    if not lines or not any(ln.strip() for ln in lines):
        raise ValueError("code is empty")
    mode = str(props.get("mode") or "code").strip().lower()
    if mode not in ("code", "terminal", "diff"):
        mode = "code"
    if mode == "diff" and not any(ln[:1] in ("+", "-") for ln in lines):
        mode = "code"
    steps: List[Dict[str, Any]] = []
    raw_steps = props.get("steps")
    for st in (raw_steps if isinstance(raw_steps, list) else [])[:5]:
        if not isinstance(st, dict):
            continue
        nums = set()
        src = st.get("lines")
        for x in (src if isinstance(src, list) else []):
            if isinstance(x, bool):
                continue
            try:
                v = int(float(x))
            except (TypeError, ValueError, OverflowError):
                continue
            if 1 <= v <= len(lines):
                nums.add(v)
        if not nums:
            continue
        d: Dict[str, Any] = {"lines": sorted(nums)}
        note = _clean_text(st.get("note"), 70)
        if note:
            d["note"] = note
        steps.append(d)
    out: Dict[str, Any] = {"code": "\n".join(lines), "language": _norm_lang(props.get("language")), "mode": mode}
    title = _clean_text(props.get("title"), 50)
    if title:
        out["title"] = title
    if steps:
        out["steps"] = steps
    cues = _clean_cues(props.get("cues"), 6)
    if cues:
        out["cues"] = cues
    return out


# ============================================================================== code: layout + timing
@dataclass(frozen=True)
class _Line:
    text: str            # what is displayed (the diff sign is stripped)
    sign: str            # "+", "-" or "" (diff only)
    tokens: Tuple[Tuple[int, str, str], ...]
    typed: bool          # False: a terminal output line, which appears whole


@lru_cache(maxsize=64)
def _parse_lines(code: str, lang: str, mode: str) -> Tuple[_Line, ...]:
    out = []
    for ln in code.split("\n"):
        if mode == "terminal":
            if ln.startswith("$ ") or ln == "$":
                toks = ((0, "$ ", "prompt"),) + tuple((c + 2, t, k) for c, t, k in tokenize(ln[2:], "bash"))
                out.append(_Line(ln, "", toks, True))
            else:
                low = ln.lower().lstrip()
                kind = "err" if re.match(r"(error|fatal|traceback|\w*exception)", low) else "warn" if low.startswith("warn") else "out"
                out.append(_Line(ln, "", ((0, ln, kind),) if ln else (), False))
        elif mode == "diff" and ln[:1] in ("+", "-"):
            out.append(_Line(ln[1:], ln[0], tokenize(ln[1:], lang), True))
        elif mode == "diff" and ln.startswith(" "):
            out.append(_Line(ln[1:], "", tokenize(ln[1:], lang), True))
        else:
            out.append(_Line(ln, "", tokenize(ln, lang), True))
    return tuple(out)


CPS = 75.0
TYPE_START = 0.3


@lru_cache(maxsize=64)
def _type_schedule(lines: Tuple[_Line, ...], dur: float) -> Tuple[Tuple[Tuple[float, float], ...], float]:
    """(start, end) of the typing of each line, and when typing ends: about 75 characters a second, finished within the first third of the scene."""
    raw: List[Tuple[float, float]] = []
    t = 0.0
    for ln in lines:
        d = (len(ln.text.strip()) + 1) / CPS if ln.typed else 0.10
        raw.append((t, t + d))
        t += d
    cap = max(0.6, dur / 3.0 - TYPE_START)
    k = min(1.0, cap / t) if t > 0 else 1.0
    return tuple((TYPE_START + a * k, TYPE_START + b * k) for a, b in raw), TYPE_START + t * k


def _step_times(props: Dict[str, Any], dur: float, n_steps: int, type_end: float) -> List[float]:
    first = min(0.6, max(0.12, (type_end + 0.5) / max(dur, 1.0)))
    return reveal_times(n_steps, dur, props.get("cues"), first=first, last=max(first, 0.85))


def _identifiers(lines: Sequence[str]) -> List[str]:
    seen: List[str] = []
    for ln in lines:
        for w in re.findall(r"[A-Za-z_][A-Za-z_0-9]{2,}", ln):
            if w not in seen:
                seen.append(w)
    return seen


def code_anchors(props: Dict[str, Any]) -> List[str]:
    code_lines = str(props.get("code", "")).split("\n")
    out = []
    for st in props.get("steps") or []:
        if st.get("note"):
            out.append(st["note"])
        else:
            ids = _identifiers([code_lines[i - 1] for i in st["lines"] if 0 < i <= len(code_lines)])
            out.append(" ".join(ids[:4]) or "code")
    return out


def code_cues(props: Dict[str, Any], dur: float) -> List[float]:
    lines = _parse_lines(props["code"], props.get("language", ""), props.get("mode", "code"))
    _, tend = _type_schedule(lines, float(dur))
    cues = [TYPE_START]
    n = len(props.get("steps") or [])
    if n:
        cues += _step_times(props, dur, n, tend)
    return [min(max(0.0, c), dur) for c in cues]


@lru_cache(maxsize=64)
def _code_geometry(n_lines: int, cols: int, has_note: bool, mode: str, top: float, bottom: float) -> Dict[str, float]:
    note_h = 105.0 if has_note else 0.0
    area_h = max(200.0, bottom - top - note_h)
    chrome, pad_y, pad_x = 56.0, 22.0, 36.0
    show_nums = mode != "terminal"
    gut_cols = (len(str(n_lines)) + 1) if show_nums else 0
    extra = 34 if mode == "diff" else 0
    fs, ratio = 20.0, 1.3
    done = False
    for ratio, floor in ((1.5, 22), (1.4, 22), (1.3, 20)):
        fs = 40.0
        while fs >= floor:
            cw = fs * MONO_ADV
            gutter = gut_cols * cw + (26 if show_nums else 0) + extra
            if pad_x * 2 + gutter + max(cols, 12) * cw + cw <= 1640 and chrome + pad_y * 2 + n_lines * fs * ratio <= area_h:
                done = True
                break
            fs -= 1
        if done:
            break
    fs = max(fs, 20.0)
    lh, cw = fs * ratio, fs * MONO_ADV
    gutter = gut_cols * cw + (26 if show_nums else 0) + (34 if mode == "diff" else 0)
    pw = min(1640.0, max(1100.0, pad_x * 2 + gutter + max(cols, 12) * cw + cw * 2))
    ph = chrome + pad_y * 2 + n_lines * lh
    py = top + max(0.0, (bottom - top - (ph + note_h)) / 2.0)
    return {"fs": fs, "lh": lh, "cw": cw, "gutter": gutter, "pw": pw, "ph": ph, "px": 960 - pw / 2, "py": py, "chrome": chrome, "pad_x": pad_x, "pad_y": pad_y,
            "note_y": py + ph + 30}


def draw_code(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    mode = props.get("mode", "code")
    lang = props.get("language", "")
    lines = _parse_lines(props["code"], lang, mode)
    steps = props.get("steps") or []
    title = props.get("title", "")
    compact = bool(title) and len(lines) > 11   # a long snippet needs the room: the title moves into the window bar
    top = heading(cv, th, title, lt, y=CONTENT_TOP + 20) if (title and not compact) else CONTENT_TOP + (30 if compact else 50)
    cols = max(len(ln.text) + (1 if ln.sign else 0) + (2 if mode == "terminal" else 0) for ln in lines)
    g = _code_geometry(len(lines), cols, bool(steps), mode, float(top), float(ctx.bottom - 6))
    fs, lh, cw, px, py, pw, ph = g["fs"], g["lh"], g["cw"], g["px"], g["py"], g["pw"], g["ph"]
    p_in = ease_out_cubic(progress(lt, 0.0, 0.45))
    if p_in <= 0:
        return
    py += (1 - p_in) * 28
    cv.shadow(px, py, pw, ph, 22, alpha=0.5 * p_in)
    cv.rrect(px, py, pw, ph, 22, fill=with_alpha(PANEL, p_in), outline=with_alpha((255, 255, 255), 0.14 * p_in), width=1.5)
    ch = g["chrome"]
    cv.rrect(px, py, pw, ch, 22, fill=with_alpha(CHROME, p_in))
    cv.rrect(px, py + 30, pw, ch - 30, 0, fill=with_alpha(CHROME, p_in))
    for i, col in enumerate(((255, 95, 86), (255, 189, 46), (39, 201, 63))):
        cv.ellipse(px + 40 + i * 34, py + ch / 2, 10, 10, fill=with_alpha(col, p_in))
    label = {"terminal": "terminal", "diff": f"diff  {lang}".strip()}.get(mode, lang or "code")
    if compact:
        label = title
    cv.text(px + pw / 2, py + ch / 2, label, "semibold", 26, with_alpha((148, 163, 184), p_in), anchor="mm")
    cv.rrect(px + pw - 40 - 80, py + ch / 2 - 3, 80, 6, 3, fill=with_alpha(th.accent, 0.9 * p_in))

    sched, type_end = _type_schedule(lines, float(dur))
    times = _step_times(props, dur, len(steps), type_end) if steps else []
    cur = -1
    for i, t in enumerate(times):
        if lt >= t:
            cur = i
    k = ease_in_out_cubic(progress(lt, times[cur], 0.4)) if cur >= 0 else 1.0

    def emph(step: int, i: int) -> Tuple[float, float]:
        """(brightness, band) of line i (0-based) while `step` is active."""
        if step < 0:
            return 1.0, 0.0
        return (1.0, 1.0) if (i + 1) in steps[step]["lines"] else (0.30, 0.0)

    x_num = px + g["pad_x"]
    x_code = x_num + g["gutter"]
    y0 = py + ch + g["pad_y"]
    for i, ln in enumerate(lines):
        y = y0 + i * lh
        b0, s0 = emph(cur - 1, i)
        b1, s1 = emph(cur, i)
        bright, band = _lerp(b0, b1, k), _lerp(s0, s1, k)
        bright = max(0.0, min(1.0, bright)) * p_in
        if ln.sign:
            tint = ADD if ln.sign == "+" else DEL
            cv.rrect(px + 6, y + 2, pw - 12, lh - 4, 6, fill=_mix(_mix(tint, PANEL, 0.20), PANEL, 0.4 + 0.6 * bright))
        if band > 0.01:
            cv.rrect(px + 8, y + 2, pw - 16, lh - 4, 8, fill=_mix(_mix(th.accent, PANEL, 0.26), PANEL, band))
            cv.rrect(px + 8, y + 7, 6, lh - 14, 3, fill=_mix(th.accent, PANEL, band))
        base = y + lh * 0.5 + fs * 0.33
        if mode != "terminal":
            _draw_text(cv, x_num + g["gutter"] - 26 - (34 if mode == "diff" else 0), base, str(i + 1), MONO, fs * 0.82, _mix((200, 208, 224) if band > 0.5 else GUTTER, PANEL, bright), anchor="rs")
        if ln.sign:
            _draw_text(cv, x_code - 22, base, ln.sign, MONO_BOLD, fs, _mix(ADD if ln.sign == "+" else DEL, PANEL, bright), anchor="ms")
        a, b = sched[i]
        vis = int(round(progress(lt, a, max(1e-3, b - a)) * len(ln.text))) if ln.typed else (len(ln.text) if lt >= a else 0)
        for col, text, kind in ln.tokens:
            if col >= vis:
                break
            _draw_text(cv, x_code + col * cw, base, text[: vis - col], MONO, fs, _mix(PALETTE.get(kind, PALETTE["text"]), PANEL, bright))
    # typing cursor
    if TYPE_START <= lt < type_end + 0.9 and int(lt * 2.6) % 2 == 0:
        idx = max((i for i, (a, _) in enumerate(sched) if lt >= a), default=0)
        ln = lines[idx]
        a, b = sched[idx]
        vis = int(round(progress(lt, a, max(1e-3, b - a)) * len(ln.text))) if ln.typed else len(ln.text)
        cv.rrect(x_code + vis * cw + 2, y0 + idx * lh + lh * 0.18, cw * 0.55, lh * 0.64, 2, fill=with_alpha(th.accent2 if th.name != "paper" else (125, 211, 252), 0.85))
    if steps and cur >= 0:
        for j, alpha in ((cur - 1, 1 - k), (cur, k)):
            if j >= 0 and alpha > 0.02:
                _draw_note(cv, th, steps[j], j, alpha, g["note_y"])


def _draw_note(cv: Canvas, th: Theme, st: Dict[str, Any], j: int, alpha: float, y: float) -> None:
    nums = st["lines"]
    note = st.get("note") or ("Line %d" % nums[0] if len(nums) == 1 else "Lines %d-%d" % (nums[0], nums[-1]))
    size, wrapped = cv.fit_text(note, "semibold", 1380, 60, 44, 32)
    line = wrapped[0] if wrapped else note
    rad = 30
    total = rad * 2 + 26 + cv.measure(line, "semibold", size)
    x = 960 - total / 2
    ry = y + 8 + (1 - alpha) * 12
    cv.ellipse(x + rad, ry + 36, rad, rad, fill=with_alpha(th.accent, alpha))
    cv.text(x + rad, ry + 36, str(j + 1), "bold", 34, with_alpha((255, 255, 255), alpha), anchor="mm")
    cv.text(x + rad * 2 + 26, ry + 36, line, "semibold", size, with_alpha(th.text, alpha), anchor="lm")


CODE_DOC = ("- code: {title (<=50), language (<=12: python, javascript, sql, bash, json, java, go, rust, html), code (<=900 chars, max 18 lines of <=70 columns), "
            "steps: optional 1-5 [{lines: [1-based line numbers], note (<=70)}], mode: \"code\"|\"terminal\"|\"diff\"}. "
            "An editor window: the code types on, then each step lights its lines (others dim) with its note, in the order the narration reaches them. "
            "terminal: lines starting \"$ \" are typed commands, the rest is output. diff: lines start with + (green), - (red) or a space. "
            "Use when the narration walks through a real snippet or command. Never pseudo-random or unverified code, never invented output: real, correct, short code, under 18 lines.")

CODE_SAMPLES = [
    {"title": "Reading a file safely", "language": "python", "code": "def read_lines(path):\n    with open(path) as f:\n        return [line.strip() for line in f]\n\nnames = read_lines(\"names.txt\")\nprint(len(names))",
     "steps": [{"lines": [1], "note": "A function takes a file path"}, {"lines": [2, 3], "note": "The with block closes the file for us"}, {"lines": [5, 6], "note": "Call it and count the lines"}]},
    {"language": "bash", "mode": "terminal", "code": "$ git status\nOn branch main\nnothing to commit, working tree clean\n$ git log --oneline -n 2\n3f2a1bc Fix typo in README\n9d8e7c6 Add install guide",
     "steps": [{"lines": [1, 2, 3], "note": "Check the state of the repo"}, {"lines": [4, 5, 6], "note": "Show the two latest commits"}]},
    {"language": "javascript", "mode": "diff", "code": " function total(items) {\n-  let sum = 0;\n-  for (let i = 0; i < items.length; i++) sum += items[i].price;\n-  return sum;\n+  return items.reduce((s, it) => s + it.price, 0);\n }",
     "steps": [{"lines": [2, 3, 4], "note": "Remove the manual loop"}, {"lines": [5], "note": "One reduce call replaces it"}]},
    {"language": "sql", "code": "SELECT name, COUNT(*) AS orders\nFROM customers c\nJOIN orders o ON o.customer_id = c.id\nWHERE o.total > 100  -- big orders only\nGROUP BY name\nORDER BY orders DESC\nLIMIT 10;",
     "steps": [{"lines": [1]}, {"lines": [3]}, {"lines": [4, 5]}]},
]


# ============================================================================== equation: typesetter
STIX, STIX_IT, STIX_BOLD = "STIXGeneral.ttf", "STIXGeneralItalic.ttf", "STIXGeneralBol.ttf"
_STYLE_FONT = {"up": STIX, "it": STIX_IT, "bold": STIX_BOLD}
REF = 200   # px at which glyphs are measured
AXIS = 0.26

GREEK = {"alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ", "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ",
         "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ", "chi": "χ", "psi": "ψ", "omega": "ω"}
GREEK_UP = {"Gamma": "Γ", "Delta": "Δ", "Theta": "Θ", "Lambda": "Λ", "Xi": "Ξ", "Pi": "Π", "Sigma": "Σ", "Phi": "Φ", "Psi": "Ψ", "Omega": "Ω"}
OPW = {"pm": ("±", "bin"), "times": ("×", "bin"), "cdot": ("·", "bin"), "approx": ("≈", "rel"), "neq": ("≠", "rel"), "leq": ("≤", "rel"), "geq": ("≥", "rel"), "to": ("→", "rel")}
SYMW = {"inf": "∞", "infty": "∞", "infinity": "∞", "partial": "∂", "nabla": "∇", "deg": "°", "degrees": "°"}
FUNCS = {"sin", "cos", "tan", "cot", "sec", "csc", "arcsin", "arccos", "arctan", "sinh", "cosh", "tanh", "log", "ln", "exp", "lim", "max", "min", "det", "gcd", "mod"}
KWS = {"sqrt", "sum", "prod", "int"}
_WHOLE = set(FUNCS) | set(OPW) | set(SYMW) | KWS
_GREEK_ALL = {**GREEK, **GREEK_UP}
UNI_GREEK = {v: (v, "it") for v in GREEK.values()}
UNI_GREEK.update({v: (v, "up") for v in GREEK_UP.values()})
UNI_OTHER = {"√": ("kw", "sqrt"), "∑": ("kw", "sum"), "∏": ("kw", "prod"), "∫": ("kw", "int"), "∞": ("sym", "∞"), "∂": ("sym", "∂"), "∇": ("sym", "∇"), "°": ("sym", "°"),
             "±": ("op", ("±", "bin")), "×": ("op", ("×", "bin")), "·": ("op", ("·", "bin")), "÷": ("op", ("÷", "bin")), "≤": ("op", ("≤", "rel")), "≥": ("op", ("≥", "rel")),
             "≠": ("op", ("≠", "rel")), "≈": ("op", ("≈", "rel")), "→": ("op", ("→", "rel")), "−": ("op", ("−", "bin"))}
MAX_TOKENS, MAX_DEPTH = 160, 8


def _split_word(run: str) -> List[Tuple[str, Any]]:
    """An alphabetic run -> tokens: whole words (sin, pi, sqrt...), Greek names greedily, otherwise single-letter variables."""
    out: List[Tuple[str, Any]] = []
    i = 0
    while i < len(run):
        rest = run[i:]
        if rest in _WHOLE or rest in _GREEK_ALL:
            name = rest
        else:
            cands = [g for g in _GREEK_ALL if rest.startswith(g)]
            name = max(cands, key=len) if cands else rest[0]
        i += len(name)
        if name in GREEK:
            out.append(("greek", (GREEK[name], "it")))
        elif name in GREEK_UP:
            out.append(("greek", (GREEK_UP[name], "up")))
        elif name in OPW:
            out.append(("op", OPW[name]))
        elif name in SYMW:
            out.append(("sym", SYMW[name]))
        elif name in KWS:
            out.append(("kw", name))
        elif name in FUNCS:
            out.append(("func", name))
        else:
            out.append(("var", name))
    return out


_NUMRX = re.compile(r"\d+(?:\.\d+)?|\.\d+")
_ALPHA = re.compile(r"[A-Za-z]+")
_TWO = {"<=": ("≤", "rel"), ">=": ("≥", "rel"), "!=": ("≠", "rel"), "~=": ("≈", "rel"), "->": ("→", "rel"), "+-": ("±", "bin"), "==": ("=", "rel")}
_ONE = {"+": ("+", "bin"), "-": ("−", "bin"), "*": ("·", "bin"), "=": ("=", "rel"), "<": ("<", "rel"), ">": (">", "rel"), ",": (",", "punct"), ";": (";", "punct"),
        "~": ("≈", "rel")}
_TEXT1 = {"!": "!", "|": "|", ".": ".", ":": ":", "%": "%", "'": "′"}


def _tokenize(s: str) -> List[Tuple[str, Any, bool]]:
    out: List[Tuple[str, Any, bool]] = []
    i, sp = 0, False
    while i < len(s):
        c = s[i]
        if c.isspace():
            sp = True
            i += 1
            continue
        if len(out) >= MAX_TOKENS:
            raise ValueError("formula too long")
        m = _NUMRX.match(s, i) if (c.isdigit() or c == ".") else None
        if m:
            out.append(("num", m.group(), sp))
            i = m.end()
        elif c.isascii() and c.isalpha():
            m = _ALPHA.match(s, i)
            for j, tok in enumerate(_split_word(m.group())):
                out.append((tok[0], tok[1], sp and j == 0))
            i = m.end()
        elif s[i:i + 2] in _TWO:
            out.append(("op", _TWO[s[i:i + 2]], sp))
            i += 2
        elif c in _ONE:
            out.append(("op", _ONE[c], sp))
            i += 1
        elif c in "([{":
            out.append(("open", c, sp))
            i += 1
        elif c in ")]}":
            out.append(("close", c, sp))
            i += 1
        elif c == "^":
            out.append(("hat", c, sp))
            i += 1
        elif c == "_":
            out.append(("sub", c, sp))
            i += 1
        elif c == "/":
            out.append(("slash", c, sp))
            i += 1
        elif c in _TEXT1:
            out.append(("text", _TEXT1[c], sp))
            i += 1
        elif c in UNI_GREEK:
            out.append(("greek", UNI_GREEK[c], sp))
            i += 1
        elif c in UNI_OTHER:
            t = UNI_OTHER[c]
            out.append((t[0], t[1], sp))
            i += 1
        else:
            raise ValueError(f"unsupported character {c!r}")
        sp = False
    return out


_CLOSER = {"(": ")", "[": "]", "{": "}"}


class _Parser:
    def __init__(self, toks):
        self.t = toks
        self.i = 0
        self.depth = 0

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else None

    def next(self):
        tok = self.peek()
        if tok is None:
            raise ValueError("unexpected end of formula")
        self.i += 1
        return tok

    def enter(self):
        self.depth += 1
        if self.depth > MAX_DEPTH:
            raise ValueError("formula nested too deeply")

    def parse(self):
        node = self.seq(None)
        if self.peek() is not None:
            raise ValueError("unbalanced brackets")
        if not node[1]:
            raise ValueError("empty formula")
        return node

    def seq(self, closer):
        self.enter()
        items: List[Any] = []
        prev_operand = False
        while True:
            tok = self.peek()
            if tok is None:
                if closer:
                    raise ValueError("missing closing bracket")
                break
            if tok[0] == "close":
                if tok[1] != closer:
                    raise ValueError("mismatched bracket")
                break
            if tok[0] == "op":
                self.i += 1
                items.append(("op", tok[1][0], tok[1][1]))
                prev_operand = False
                continue
            if tok[0] == "slash":
                raise ValueError("fraction without numerator")
            if prev_operand:
                items.append(("gap", 0.14))
            items.append(self.term())
            prev_operand = True
        self.depth -= 1
        return ("seq", items)

    def term(self):
        left = self.run()
        while self.peek() is not None and self.peek()[0] == "slash":
            self.i += 1
            right = self.run()
            left = ("frac", _unwrap(left), _unwrap(right))
        return left

    def run(self):
        atoms = [self.atom()]
        while True:
            nt = self.peek()
            if nt is None or nt[2] or nt[0] in ("op", "close", "slash"):
                break
            if atoms[-1][0] == "text" and atoms[-1][2] == "up" and atoms[-1][1] in FUNCS:
                atoms.append(("gap", 0.10))
            atoms.append(self.atom())
        return atoms[0] if len(atoms) == 1 else ("row", atoms)

    def group(self):
        o = self.next()
        body = self.seq(_CLOSER[o[1]])
        self.next()
        return o[1], body

    def script_arg(self):
        tok = self.peek()
        if tok is None:
            raise ValueError("missing script")
        if tok[0] == "open":
            _, body = self.group()
            return body
        if tok[0] == "num":
            self.i += 1
            return ("text", tok[1], "up")
        if tok[0] == "op" and tok[1][0] in ("+", "−"):
            self.i += 1
            return ("row", [("text", tok[1][0], "up"), self.atom(scripts=False)])
        if tok[0] in ("var", "greek", "sym", "func"):
            return self.atom(scripts=False)
        raise ValueError("bad script")

    def atom(self, scripts: bool = True):
        self.enter()
        tok = self.next()
        kind = tok[0]
        node: Any
        if kind == "num":
            node = ("text", tok[1], "up")
        elif kind == "var":
            node = ("text", tok[1], "it")
        elif kind == "greek":
            node = ("text", tok[1][0], tok[1][1])
        elif kind in ("sym", "func", "text"):
            node = ("text", tok[1], "up")
        elif kind == "open":
            self.i -= 1
            o, body = self.group()
            node = ("group", body) if o == "{" else ("paren", o, body)
        elif kind == "kw":
            name = tok[1]
            if name == "sqrt":
                nt = self.peek()
                if nt is None:
                    raise ValueError("sqrt needs an argument")
                if nt[0] == "open":
                    _, body = self.group()
                else:
                    body = self.atom(scripts=False)
                node = ("sqrt", body)
            else:
                sub = sup = None
                for _ in range(2):
                    nt = self.peek()
                    if nt is not None and nt[0] == "sub" and sub is None:
                        self.i += 1
                        sub = self.script_arg()
                    elif nt is not None and nt[0] == "hat" and sup is None:
                        self.i += 1
                        sup = self.script_arg()
                self.depth -= 1
                return ("bigop", name, sub, sup)
        else:
            raise ValueError(f"unexpected {kind}")
        if scripts:
            sub = sup = None
            while self.peek() is not None and self.peek()[0] in ("hat", "sub"):
                t = self.next()
                arg = self.script_arg()
                if t[0] == "hat":
                    if sup is not None:
                        raise ValueError("double superscript")
                    sup = arg
                else:
                    if sub is not None:
                        raise ValueError("double subscript")
                    sub = arg
            if sub is not None or sup is not None:
                node = ("script", node, sub, sup)
        self.depth -= 1
        return node


def _unwrap(node):
    if node[0] == "paren" and node[1] == "(":
        return node[2]
    if node[0] == "group":
        return node[1]
    return node


# ---- boxes
@dataclass
class Box:
    w: float
    asc: float
    desc: float
    ops: List[Tuple]


def _sh(ops: Sequence[Tuple], dx: float, dy: float) -> List[Tuple]:
    out = []
    for o in ops:
        if o[0] == "t":
            out.append(("t", o[1] + dx, o[2] + dy) + tuple(o[3:]))
        elif o[0] == "l":
            out.append(("l", o[1] + dx, o[2] + dy, o[3] + dx, o[4] + dy, o[5]))
        else:
            out.append(("p", tuple((x + dx, y + dy) for x, y in o[1]), o[2]))
    return out


def _tbox(text: str, style: str, size: float) -> Box:
    f = _ttf(_STYLE_FONT[style], REF)
    k = size / REF
    l, t, r, b = f.getbbox(text, anchor="ls")
    return Box(f.getlength(text) * k, max(max(-t, 0) * k, 0.45 * size), max(b, 0) * k, [("t", 0.0, 0.0, text, style, size)])


def _hcat(boxes: Sequence[Tuple[Box, float]]) -> Box:
    """(box, extra left gap) pairs laid left to right on one baseline."""
    x = asc = desc = 0.0
    ops: List[Tuple] = []
    for b, gap in boxes:
        x += gap
        ops += _sh(b.ops, x, 0)
        x += b.w
        asc, desc = max(asc, b.asc), max(desc, b.desc)
    return Box(x, asc, desc, ops)


def _lay(node, size: float, level: int) -> Box:
    kind = node[0]
    if kind == "text":
        return _tbox(node[1], node[2], size)
    if kind == "gap":
        return Box(node[1] * size, 0.0, 0.0, [])
    if kind == "group":
        return _lay(node[1], size, level)
    if kind == "row":
        return _hcat([(_lay(c, size, level), 0.0) for c in node[1]])
    if kind == "seq":
        return _lay_seq(node[1], size, level)
    if kind == "paren":
        return _lay_paren(node, size, level)
    if kind == "frac":
        return _lay_frac(node, size, level)
    if kind == "script":
        return _lay_script(node, size, level)
    if kind == "sqrt":
        return _lay_sqrt(node, size, level)
    if kind == "bigop":
        return _lay_bigop(node, size, level)
    raise ValueError(f"cannot lay out {kind}")


def _lay_seq(items, size: float, level: int) -> Box:
    parts: List[Tuple[Box, float]] = []
    prev_operand = False
    shrink = 0.6 if level else 1.0
    pending = 0.0
    for it in items:
        if it[0] == "op":
            glyph, cls = it[1], it[2]
            unary = (not prev_operand) and cls == "bin" and glyph in ("+", "−", "±")
            if cls == "punct":
                left, right = 0.0, 0.2 * size * shrink
            elif cls == "rel":
                left = right = 0.30 * size * shrink
            elif unary:
                left, right = 0.0, 0.03 * size
            else:
                left = right = 0.22 * size * shrink
            parts.append((_tbox(glyph, "up", size), pending + left))
            pending = right
            prev_operand = False
        else:
            parts.append((_lay(it, size, level), pending))
            pending = 0.0
            prev_operand = prev_operand or it[0] != "gap"
    return _hcat(parts)


def _lay_paren(node, size: float, level: int) -> Box:
    o, body = node[1], node[2]
    inner = _lay(body, size, level)
    half = max(inner.asc - size * AXIS, inner.desc + size * AXIS, 0.5 * size) + 0.04 * size
    a, d = size * AXIS + half, half - size * AXIS
    h = a + d
    pw = min(0.5 * size, max(0.3 * size, 0.08 * size + 0.10 * h))
    stroke = max(0.04 * size, 0.035 * size + 0.01 * h)
    depth = min(0.3 * size, 0.07 * size + 0.05 * h)

    def curve(left: bool) -> Tuple:
        pts = []
        for i in range(21):
            t = -1 + i / 10.0
            y = -a + (t + 1) / 2 * h
            off = depth * (1 - t * t)
            pts.append(((pw * 0.78 - off) if left else (pw * 0.22 + off), y))
        return ("p", tuple(pts), stroke)

    if o == "[":
        lo = ("p", ((pw * 0.75, -a), (pw * 0.25, -a), (pw * 0.25, d), (pw * 0.75, d)), stroke)
        ro = ("p", ((pw * 0.25, -a), (pw * 0.75, -a), (pw * 0.75, d), (pw * 0.25, d)), stroke)
    else:
        lo, ro = curve(True), curve(False)
    gap = 0.05 * size
    ops = [lo] + _sh(inner.ops, pw + gap, 0) + _sh([ro], pw + gap * 2 + inner.w, 0)
    return Box(pw * 2 + inner.w + gap * 3, a, d, ops)


def _lay_frac(node, size: float, level: int) -> Box:
    ss = size * (0.88 if level == 0 else 0.78)
    num, den = _lay(node[1], ss, level + 1), _lay(node[2], ss, level + 1)
    w = max(num.w, den.w) + 0.24 * size
    axis, gap = AXIS * size, 0.13 * size
    ny = -axis - gap - num.desc
    dy = -axis + gap + den.asc
    ops = [("l", 0.04 * size, -axis, w - 0.04 * size, -axis, max(0.04 * size, 3.0))]
    ops += _sh(num.ops, (w - num.w) / 2, ny) + _sh(den.ops, (w - den.w) / 2, dy)
    return Box(w, -ny + num.asc, dy + den.desc, ops)


def _lay_script(node, size: float, level: int) -> Box:
    base = _lay(node[1], size, level)
    ss = size * 0.66
    sub = _lay(node[2], ss, level + 1) if node[2] is not None else None
    sup = _lay(node[3], ss, level + 1) if node[3] is not None else None
    off = 0.04 * size if node[1][0] == "text" and node[1][2] == "it" else 0.0
    sup_s = max(0.42 * size, base.asc - 0.4 * ss) if sup else 0.0
    sub_s = max(0.20 * size, base.desc) if sub else 0.0
    if sup and sub:
        need = 0.12 * size - ((sup_s - sup.desc) - (-sub_s + sub.asc))
        if need > 0:
            sup_s += need / 2
            sub_s += need / 2
    x = base.w + off
    ops = list(base.ops)
    w, asc, desc = x, base.asc, base.desc
    if sup:
        ops += _sh(sup.ops, x, -sup_s)
        w, asc = max(w, x + sup.w), max(asc, sup_s + sup.asc)
    if sub:
        ops += _sh(sub.ops, x, sub_s)
        w, desc = max(w, x + sub.w), max(desc, sub_s + sub.desc)
    return Box(w + 0.04 * size, asc, desc, ops)


def _lay_sqrt(node, size: float, level: int) -> Box:
    body = _lay(node[1], size, level)
    top = -(body.asc + 0.16 * size)
    bot = body.desc + 0.06 * size
    H = bot - top
    rw = 0.56 * size
    pts = ((0.03 * size, bot - 0.40 * H), (0.12 * size, bot - 0.45 * H), (0.30 * size, bot), (rw - 0.02 * size, top), (rw + body.w + 0.14 * size, top))
    ops = [("p", pts, max(0.04 * size, 3.0))] + _sh(body.ops, rw + 0.06 * size, 0)
    return Box(rw + body.w + 0.16 * size, -top + 0.04 * size, bot, ops)


def _lay_bigop(node, size: float, level: int) -> Box:
    name, sub_n, sup_n = node[1], node[2], node[3]
    glyph = {"sum": "∑", "prod": "∏", "int": "∫"}[name]
    gs = size * (1.7 if name != "int" else 2.0)
    f = _ttf(STIX, REF)
    k = gs / REF
    gw = f.getlength(glyph) * k
    l, t, r, b = f.getbbox(glyph, anchor="ls")
    t, b, r = t * k, b * k, r * k
    yb = -AXIS * size - (t + b) / 2
    it, ib = yb + t, yb + b
    ss = size * 0.62
    sub = _lay(sub_n, ss, level + 1) if sub_n is not None else None
    sup = _lay(sup_n, ss, level + 1) if sup_n is not None else None
    asc, desc = -it, ib
    if name != "int":
        w = max(gw, sup.w if sup else 0, sub.w if sub else 0) + 0.06 * size
        ops = [("t", (w - gw) / 2, yb, glyph, "up", gs)]
        if sup:
            y = it - 0.08 * size - sup.desc
            ops += _sh(sup.ops, (w - sup.w) / 2, y)
            asc = max(asc, -y + sup.asc)
        if sub:
            y = ib + 0.08 * size + sub.asc
            ops += _sh(sub.ops, (w - sub.w) / 2, y)
            desc = max(desc, y + sub.desc)
        return Box(w + 0.1 * size, asc, desc, ops)
    ops = [("t", 0.0, yb, glyph, "up", gs)]
    w = gw
    if sup:
        y, x = it + sup.asc * 0.85, r + 0.02 * size
        ops += _sh(sup.ops, x, y)
        w, asc = max(w, x + sup.w), max(asc, -y + sup.asc)
    if sub:
        y, x = ib - 0.05 * size, r * 0.45
        ops += _sh(sub.ops, x, y)
        w, desc = max(w, x + sub.w), max(desc, y + sub.desc)
    return Box(w + 0.14 * size, asc, desc, ops)


MIN_FONT_REF_W = 3300.0   # a formula wider than this (at font size 100) would be set below ~45 px on screen


@lru_cache(maxsize=128)
def layout_formula(formula: str) -> Tuple[float, float, float, Tuple[Tuple, ...]]:
    """Parse and typeset at font size 100. Returns (width, ascent, descent, ops); raises ValueError when the formula does not parse."""
    try:
        box = _lay(_Parser(_tokenize(formula)).parse(), 100.0, 0)
    except ValueError:
        raise
    except (RecursionError, IndexError, KeyError, TypeError) as e:
        raise ValueError(f"formula could not be typeset: {e}") from e
    if box.w > MIN_FONT_REF_W or box.w < 1 or box.asc + box.desc < 5:
        raise ValueError("formula too wide or empty")
    return box.w, box.asc, box.desc, tuple(box.ops)


# ============================================================================== equation: props + drawing
def sanitize_equation(props: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(props, dict):
        raise ValueError("equation props must be an object")
    raw = props.get("steps")
    if not isinstance(raw, list) or not raw:
        raw = [{"formula": props.get("formula"), "note": props.get("note")}] if props.get("formula") else []
    steps: List[Dict[str, Any]] = []
    for st in raw[:4]:
        if isinstance(st, str):
            st = {"formula": st}
        if not isinstance(st, dict):
            continue
        f = _clean_text(st.get("formula"), 80)
        if not f:
            continue
        layout_formula(f)   # ValueError: reject the whole scene rather than draw garbage
        d: Dict[str, Any] = {"formula": f}
        note = _clean_text(st.get("note"), 60)
        if note:
            d["note"] = note
        steps.append(d)
    if not steps:
        raise ValueError("equation needs at least one formula")
    out: Dict[str, Any] = {"steps": steps}
    title = _clean_text(props.get("title"), 50)
    if title:
        out["title"] = title
    cues = _clean_cues(props.get("cues"), 4)
    if cues:
        out["cues"] = cues
    return out


def equation_anchors(props: Dict[str, Any]) -> List[str]:
    return [st.get("note") or st["formula"] for st in props.get("steps") or []]


def equation_cues(props: Dict[str, Any], dur: float) -> List[float]:
    return reveal_times(len(props.get("steps") or []), dur, props.get("cues"), first=0.12, last=0.70)


@lru_cache(maxsize=64)
def _eq_plan(formulas: Tuple[str, ...], notes: Tuple[str, ...], top: float, bottom: float) -> List[Tuple[float, float, float, float, float]]:
    """Per step: (scale from font-size-100 units to px, row top, row height, note size, padding)."""
    n = len(formulas)
    boxes = [layout_formula(f) for f in formulas]
    target = {1: 240.0, 2: 190.0, 3: 150.0, 4: 120.0}[n]
    pad, gap, note_gap = (30.0, 24.0, 34.0) if n == 1 else (20.0, 16.0, 14.0)
    avail = bottom - top
    f = 1.0
    while True:
        rows = []
        for (w, a, d, _), note in zip(boxes, notes):
            k = min(target * f / 100.0, 1500.0 / w)
            nsz = (40.0 if n == 1 else 36.0) if f > 0.7 else 32.0
            rows.append((k, pad * 2 + (a + d) * k + ((note_gap + nsz * 1.25) if note else 0.0), nsz))
        total = sum(r[1] for r in rows) + gap * (n - 1)
        if total <= avail or f < 0.4:
            break
        f *= 0.95
    y = top + max(0.0, (avail - total) / 2)
    out = []
    for k, h, nsz in rows:
        out.append((k, y, h, nsz, pad))
        y += h + gap
    return out


def draw_equation(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, th: Theme, ctx: SceneCtx) -> None:
    steps = props["steps"]
    n = len(steps)
    title = props.get("title", "")
    top = heading(cv, th, title, lt, y=CONTENT_TOP + 20) if title else CONTENT_TOP + 40
    plan = _eq_plan(tuple(s["formula"] for s in steps), tuple(s.get("note", "") for s in steps), float(top), float(ctx.bottom - 10))
    times = reveal_times(n, dur, props.get("cues"), first=0.12, last=0.70)
    for i, st in enumerate(steps):
        a = ease_out_cubic(progress(lt, times[i], 0.6))
        if a <= 0.01:
            continue
        k, ry, rh, nsz, pad = plan[i]
        dim = 1.0 - 0.5 * ease_out_cubic(progress(lt, times[i + 1], 0.5)) if i + 1 < n else 1.0
        ry += (1 - a) * 26
        cv.card(140, ry, 1640, rh, th, r=30, alpha=a * (0.6 + 0.4 * dim))
        if dim > 0.99:
            cv.rrect(160, ry + 22, 8, rh - 44, 4, fill=with_alpha(th.accent, a))
        w, asc, desc, ops = layout_formula(st["formula"])
        x0 = 960 - w * k / 2
        base_y = ry + pad + asc * k
        col = with_alpha(th.text, a * dim)
        for o in ops:
            if o[0] == "t":
                _draw_text(cv, x0 + o[1] * k, base_y + o[2] * k, o[3], _STYLE_FONT[o[4]], o[5] * k, col, anchor="ls")
            elif o[0] == "l":
                cv.line([(x0 + o[1] * k, base_y + o[2] * k), (x0 + o[3] * k, base_y + o[4] * k)], col, max(2.0, o[5] * k), round_caps=False)
            else:
                cv.line([(x0 + x * k, base_y + y * k) for x, y in o[1]], col, max(2.0, o[2] * k))
        note = st.get("note")
        if note:
            ny = ry + pad + (asc + desc) * k + (34 if n == 1 else 14) + nsz * 0.62 + (1 - a) * 10
            size, wrapped = cv.fit_text(note, "semibold", 1440, nsz * 1.3, nsz, 28)
            cv.text(960, ny, wrapped[0] if wrapped else note, "semibold", size, with_alpha(th.muted, a * dim), anchor="mm")


EQUATION_DOC = ("- equation: {title (<=50), steps: 1-4 [{formula (<=80 chars, plain linear notation: `E = m c^2`, `x = (-b + sqrt(b^2 - 4ac)) / (2a)`, "
                "`sum_{i=1}^{n} i = n(n+1)/2`, `int_0^1 x^2 dx`, Greek by name: pi, theta, Delta), note (<=60)}]}. "
                "Typeset formulas (fractions, powers, subscripts, roots, sums and integrals) revealed one after another, the newest in focus. "
                "Use when the narration states a standard formula or derives one step by step. Never invent a formula or constant, only formulas you are sure are correct; "
                "no LaTeX or backslashes; a formula that does not parse is rejected.")

EQUATION_SAMPLES = [
    {"title": "Mass-energy equivalence", "steps": [{"formula": "E = m c^2", "note": "Energy equals mass times the speed of light squared"}]},
    {"title": "Solving a quadratic", "steps": [{"formula": "a x^2 + b x + c = 0", "note": "Start from the general quadratic"},
                                              {"formula": "x = (-b + sqrt(b^2 - 4ac)) / (2a)", "note": "The quadratic formula gives the roots"},
                                              {"formula": "sum_{i=1}^{n} i = n(n+1)/2", "note": "A sum with limits"}]},
    {"steps": [{"formula": "A = pi r^2"}, {"formula": "int_0^1 x^2 dx = 1/3", "note": "Area under a parabola"}, {"formula": "sin(theta)^2 + cos(theta)^2 = 1"},
               {"formula": "x_{n+1} = x_n - f(x_n)/f'(x_n)", "note": "Newton's method"}]},
]

ELEMENTS = [
    Element("code", FAMILY, CODE_DOC, sanitize_code, draw_code, code_cues, CODE_SAMPLES, anchors=code_anchors, max_per_video=4, min_seconds=5.0),
    Element("equation", FAMILY, EQUATION_DOC, sanitize_equation, draw_equation, equation_cues, EQUATION_SAMPLES, anchors=equation_anchors, max_per_video=3, min_seconds=3.0),
]
