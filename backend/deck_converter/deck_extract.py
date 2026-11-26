"""What a deck says, per slide: title, text blocks in reading order, speaker notes, tables, chart data, alt text, layout role.

Runs on a package that `deck_safe` accepted and sanitized (no external relationships, no embedded workbooks). python-pptx reads it with lxml configured not to resolve
entities. Everything returned is untrusted DATA: strings are length-bounded and stripped of control characters here, and the writer is told to treat them as content,
never as instructions. Hyperlink targets are not extracted at all.
"""
import io
import re
from typing import Any, Dict, List, Optional

MAX_BLOCKS = 40
MAX_TEXT = 600            # characters per text block
MAX_NOTES = 4000
MAX_TABLE_ROWS, MAX_TABLE_COLS, MAX_CELL = 30, 12, 120
MAX_SERIES, MAX_POINTS = 8, 40
_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f  ‪-‮⁦-⁩]")


def clean(s: Any, n: int) -> str:
    return re.sub(r"[ \t]+", " ", _CTRL.sub("", str(s or "").replace("\x0b", " ").replace("\r", "\n"))).strip()[:n]


def _shapes(shapes, depth: int = 0):
    for sh in shapes:
        yield sh
        if depth < 4 and sh.shape_type is not None and int(sh.shape_type) == 6:   # a group
            yield from _shapes(sh.shapes, depth + 1)


def _chart(ch) -> Dict[str, Any]:
    out: Dict[str, Any] = {"type": str(ch.chart_type).split(".")[-1].split(" ")[0].lower()[:30], "title": "", "categories": [], "series": []}
    try:
        if ch.has_title:
            out["title"] = clean(ch.chart_title.text_frame.text, 120)
    except Exception:
        pass
    try:
        plot = ch.plots[0]
        out["categories"] = [clean(c, 40) for c in list(plot.categories)[:MAX_POINTS]]
        for s in list(plot.series)[:MAX_SERIES]:
            out["series"].append({"name": clean(s.name, 60), "values": [None if v is None else round(float(v), 4) for v in list(s.values)[:MAX_POINTS]]})
    except Exception:
        pass
    return out


def _role(i: int, n: int, title: str, blocks: List[Dict[str, Any]], tables: list, charts: list, pics: int, layout: str, text_chars: int) -> str:
    low = (layout or "").lower()
    if charts:
        return "chart"
    if tables:
        return "table"
    if i == 0 and (text_chars < 200 or "title" in low):
        return "title"
    if "section" in low or (text_chars < 40 and not pics and i not in (0, n - 1)):
        return "section"
    if re.search(r"\b(thank|thanks|gracias|merci|danke|obrigad|grazie|questions?|preguntas?)\b", f"{title} {' '.join(b['t'] for b in blocks)}".lower()) and text_chars < 80 and i == n - 1:
        return "closing"
    if "comparison" in low or "two content" in low:
        return "comparison"
    if pics and text_chars < 160:
        return "image"
    if re.search(r"\b(agenda|outline|contents?|índice|indice|agenda)\b", title.lower()) and i < 3:
        return "agenda"
    return "content"


def extract_pptx(raw: bytes, max_slides: int = 60) -> Dict[str, Any]:
    from pptx import Presentation

    prs = Presentation(io.BytesIO(raw))
    W, H = int(prs.slide_width or 12192000), int(prs.slide_height or 6858000)
    slides: List[Dict[str, Any]] = []
    hidden = 0
    for idx, s in enumerate(prs.slides):
        if s._element.get("show") == "0":   # hidden slides are not part of the show (and the converter does not draw them)
            hidden += 1
            continue
        if len(slides) >= max_slides:
            break
        title = clean(s.shapes.title.text_frame.text, 200) if s.shapes.title is not None and s.shapes.title.has_text_frame else ""
        blocks: List[Dict[str, Any]] = []
        tables: List[List[List[str]]] = []
        charts: List[Dict[str, Any]] = []
        alts: List[str] = []
        pics = 0
        items = []
        for sh in _shapes(s.shapes):
            try:
                if sh.has_text_frame and sh != s.shapes.title:
                    items.append((int(sh.top or 0) // 300000, int(sh.left or 0), sh))
                elif getattr(sh, "has_table", False) and sh.has_table:
                    rows = [[clean(c.text, MAX_CELL) for c in list(r.cells)[:MAX_TABLE_COLS]] for r in list(sh.table.rows)[:MAX_TABLE_ROWS]]
                    tables.append(rows)
                elif getattr(sh, "has_chart", False) and sh.has_chart:
                    charts.append(_chart(sh.chart))
                elif int(sh.shape_type or 0) == 13:   # a picture
                    pics += 1
                    alt = clean(sh._element.xpath(".//p:cNvPr/@descr")[0] if sh._element.xpath(".//p:cNvPr/@descr") else "", 200)
                    if alt:
                        alts.append(alt)
            except Exception:
                continue
        for _, _, sh in sorted(items, key=lambda t: (t[0], t[1])):
            for p in sh.text_frame.paragraphs:
                t = clean("".join(r.text for r in p.runs) or p.text, MAX_TEXT)
                if t and len(blocks) < MAX_BLOCKS:
                    blocks.append({"t": t, "lvl": min(int(p.level or 0), 4)})
        ntf = s.notes_slide.notes_text_frame if s.has_notes_slide else None
        notes = clean(ntf.text, MAX_NOTES) if ntf is not None else ""
        layout = clean(s.slide_layout.name, 60)
        chars = len(title) + sum(len(b["t"]) for b in blocks)
        slides.append({"n": len(slides) + 1, "title": title, "blocks": blocks, "notes": notes, "tables": tables[:3], "charts": charts[:3], "alts": alts[:5], "pictures": pics,
                       "layout": layout, "role": ""})
    n = len(slides)
    for i, sl in enumerate(slides):
        sl["role"] = _role(i, n, sl["title"], sl["blocks"], sl["tables"], sl["charts"], sl["pictures"], sl["layout"], len(sl["title"]) + sum(len(b["t"]) for b in sl["blocks"]))
    return {"format": "pptx", "aspect": round(W / H, 4), "slides": slides, "hidden": hidden}


def extract_pdf(pages_text: List[str]) -> Dict[str, Any]:
    """A PDF deck: the text of each page (from pdftotext); the first non-empty line is taken as the title. No notes, tables or charts as structure: the page image carries them."""
    slides = []
    for i, t in enumerate(pages_text):
        lines = [clean(l, MAX_TEXT) for l in t.splitlines()]
        lines = [l for l in lines if l]
        slides.append({"n": i + 1, "title": lines[0][:200] if lines else "", "blocks": [{"t": l, "lvl": 0} for l in lines[1:MAX_BLOCKS]], "notes": "", "tables": [], "charts": [],
                       "alts": [], "pictures": 0, "layout": "", "role": ""})
    n = len(slides)
    for i, sl in enumerate(slides):
        sl["role"] = _role(i, n, sl["title"], sl["blocks"], [], [], 0, "", len(sl["title"]) + sum(len(b["t"]) for b in sl["blocks"]))
    return {"format": "pdf", "aspect": 0.0, "slides": slides, "hidden": 0}
