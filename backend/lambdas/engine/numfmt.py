"""Locale-aware numbers for the scenes: ONE parser and ONE formatter, so '3,3 millones' is 3.3 million in a Spanish video and never 33.

English writes 1,234.5 (comma groups thousands, point is the decimal mark); Spanish writes 1234,5 or 1.234,5 (RAE: decimal comma; from five digits a
non-breaking space groups thousands). The director may send either form, so the parser reads the shape of the text first and the video's language only when
the shape is ambiguous:

  both marks present            the LAST one is the decimal mark ("1.234,5" and "1,234.5" are both 1234.5)
  one mark, repeated            thousands ("1.234.567", "1,234,567")
  one mark, once, not 3 digits after it, or a leading 0       decimal ("3,3", "12,5", "0,500", "1234.56")
  one mark, once, exactly 3 digits after a 1-3 digit head     ambiguous ("1.234", "3,300"): the language decides (en: "," groups; es: "." groups)
  spaces / NBSP / thin space / apostrophe between 3-digit groups    thousands

A separator is never dropped silently: text that does not fit a pattern is not a number (parse returns None / raises ValueError).

The language of the video is carried by a context variable (`language_scope`) that the renderer sets around every scene draw and `plan.validate_plan` around
every sanitize, so the shared helpers need no extra argument; every function also takes an explicit `lang`.
"""
import contextlib
import contextvars
import re
from typing import Iterator, Optional, Tuple

NBSP = " "
_SEPS = "    '’"
_LANG: "contextvars.ContextVar[str]" = contextvars.ContextVar("vmk_number_language", default="en")

# one number token: digits with optional , . and group spaces inside; or a leading-mark decimal (".5", ",5")
_TOKEN = r"(?:\d[\d.,    '’]*\d|\d|[.,]\d+)"
_PARSE = re.compile(r"^(?P<pre>[^\d\-+−.,]*)(?P<sign>[+\-−]?)(?P<num>" + _TOKEN + r")(?P<suf>.*)$", re.S)
_FULL = re.compile(r"^\s*(?P<sign>[+\-−]?)\s*(?P<num>" + _TOKEN + r")\s*$")
_GROUPED = re.compile(r"^\d{1,3}(?:[" + re.escape(_SEPS) + r"]\d{3})+(?:[.,]\d+)?$")


# Languages that write the decimal mark as a comma. They all share one style here, the one built for Spanish ("es"): a decimal comma, and a non-breaking space
# between thousands from five integer digits (the international form, right in French, Polish and Finnish; German, Italian, Dutch and Brazilian Portuguese more
# often group with a point, "12.345,6", but read the spaced form without doubt). Parsing accepts both groupings.
COMMA_LANGUAGES = ("es", "fr", "de", "it", "pt", "nl", "pl", "fi")


def norm_lang(lang: Optional[str]) -> str:
    """The number STYLE of a language: 'es' (decimal comma) for 'es', 'es-MX', 'Spanish', 'fr', 'de', ...; 'en' (decimal point) for everything else."""
    s = str(lang or "").strip().lower()
    return "es" if s[:2] in COMMA_LANGUAGES and not s.startswith("eng") or s.startswith("span") else "en"


def current_language() -> str:
    return _LANG.get()


@contextlib.contextmanager
def language_scope(lang: Optional[str]) -> Iterator[None]:
    tok = _LANG.set(norm_lang(lang))
    try:
        yield
    finally:
        _LANG.reset(tok)


def parse_amount(token: str, lang: Optional[str] = None) -> Optional[Tuple[float, int, bool]]:
    """'1.234,5' -> (1234.5, 1, True). (value, decimals, grouped); None when the text is not a well-formed number."""
    lg = norm_lang(lang) if lang is not None else _LANG.get()
    s = str(token).strip()
    if not s:
        return None
    grouped = False
    if re.search(r"[" + re.escape(_SEPS) + r"]", s):
        if not _GROUPED.match(s):
            return None                                  # "1 2" or "12 34": not a thousands grouping
        s = re.sub(r"(?<=\d)[" + re.escape(_SEPS) + r"](?=\d{3}(?:\D|$))", "", s)
        grouped = True
    dots, commas = s.count("."), s.count(",")
    if dots and commas:
        dec = "." if s.rfind(".") > s.rfind(",") else ","
        thou = "," if dec == "." else "."
        head, _, tail = s.rpartition(dec)
        if dec in head or not re.fullmatch(r"\d{1,3}(?:%s\d{3})+" % re.escape(thou), head):
            return None
        s, grouped = head.replace(thou, "") + "." + tail, True
    elif dots or commas:
        mark = "." if dots else ","
        n = dots or commas
        if n > 1:
            if not re.fullmatch(r"\d{1,3}(?:%s\d{3})+" % re.escape(mark), s):
                return None
            s, grouped = s.replace(mark, ""), True
        else:
            head, _, tail = s.partition(mark)
            ambiguous = len(tail) == 3 and 1 <= len(head) <= 3 and not head.startswith("0") and head != ""
            if ambiguous:
                thousands = (lg == "en" and mark == ",") or (lg == "es" and mark == ".")
            else:
                thousands = False
            if thousands:
                s, grouped = head + tail, True
            else:
                s = (head or "0") + "." + tail
    try:
        val = float(s)
    except ValueError:
        return None
    decimals = len(s.split(".")[1]) if "." in s else 0
    return val, decimals, grouped


def parse_float(x, lang: Optional[str] = None) -> float:
    """A plain number from a director value (int, float or a string such as '3,3' / '1.234,5'). Raises ValueError for anything else (never a silent 33)."""
    if isinstance(x, bool):
        raise ValueError("not a number")
    if isinstance(x, (int, float)):
        return float(x)
    m = _FULL.match(str(x))
    if not m:
        raise ValueError(f"not a number: {x!r}")
    p = parse_amount(m.group("num"), lang)
    if not p:
        raise ValueError(f"not a number: {x!r}")
    return -p[0] if m.group("sign") in ("-", "−") else p[0]


def parse_number(s: str, lang: Optional[str] = None):
    """'$1,250.5M' -> ('$', 1250.5, 1, 'M', True); '3,3 millones' in Spanish -> ('', 3.3, 1, ' millones', False). None when there is no number."""
    m = _PARSE.match(str(s).strip())
    if not m:
        return None
    p = parse_amount(m.group("num"), lang)
    if not p:
        return None
    val, dec, grouped = p
    if m.group("sign") in ("-", "−"):
        val = -val
    return m.group("pre"), val, dec, m.group("suf"), grouped


def format_number(val: float, decimals: int, grouped: bool, lang: Optional[str] = None) -> str:
    """English: '1,250.5' (grouped when asked or from 10 000); Spanish: '1250,5', and from five integer digits '12 345,6' with a non-breaking space (RAE)."""
    lg = norm_lang(lang) if lang is not None else _LANG.get()
    if lg == "es":
        s = f"{abs(val):.{decimals}f}"
        ip, _, fp = s.partition(".")
        if len(ip) >= 5:
            ip = f"{int(ip):,}".replace(",", NBSP)
        out = ip + ("," + fp if fp else "")
        return ("-" if val < 0 and float(s) != 0 else "") + out
    return f"{val:,.{decimals}f}" if grouped or abs(val) >= 10000 else f"{val:.{decimals}f}"


def canonical(val: float, decimals: int) -> str:
    """Machine form kept in a plan: a plain decimal point, no grouping ('1250.5'), the same in every language."""
    return f"{val:.{max(0, decimals)}f}"


_CANON = re.compile(r"^-?\d+(\.\d+)?$")


def is_canonical(s) -> bool:
    return isinstance(s, str) and bool(_CANON.match(s))


def localize(s: str, lang: Optional[str] = None) -> str:
    """Re-mark an English-formatted plain number string for the video's language ('3.5%' -> '3,5%' in Spanish). Strings with a thousands comma are left alone."""
    lg = norm_lang(lang) if lang is not None else _LANG.get()
    if lg != "es" or "," in s:
        return s
    return re.sub(r"(?<=\d)\.(?=\d)", ",", s)
