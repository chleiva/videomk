"""Sample decks for the deck-to-video tests and the spike, generated with python-pptx (no binary fixtures in the repo).

business_en(): 10 slides, English, chart + table + image + speaker notes.   spanish_6(): 6 slides, Spanish.   long_deck(n): dark theme, custom fonts.
nasty(): hidden slide, transitions/animation XML, external hyperlink and linked-image relationships, grouped and rotated shapes, 120 shapes, CJK and emoji, empty slide.
"""
import io
import zipfile
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw

from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE
from pptx.util import Emu, Inches, Pt


def _png(w: int = 900, h: int = 600, label: str = "Photo", c1=(31, 78, 121), c2=(237, 125, 49)) -> bytes:
    im = Image.new("RGB", (w, h), c1)
    d = ImageDraw.Draw(im)
    for i in range(0, w, 60):
        d.line([(i, 0), (w - i, h)], fill=c2, width=6)
    d.ellipse([w // 3, h // 3, 2 * w // 3, 2 * h // 3], fill=(255, 255, 255))
    d.text((w // 2 - 20, h // 2 - 5), label, fill=(0, 0, 0))
    b = io.BytesIO()
    im.save(b, "PNG")
    return b.getvalue()


def _widen(p) -> None:
    """The default template is 4:3: when the deck is widescreen, stretch the placeholders to it and set readable type, so the sample looks like a real 16:9 deck."""
    k = p.slide_width / Inches(10)
    for s in p.slides:
        for sh in s.placeholders:
            l, t, w, h = sh.left, sh.top, sh.width, sh.height
            sh.left, sh.top, sh.width, sh.height = int(l * k), t, int(w * k), h
            if sh.has_text_frame:
                is_title = sh == s.shapes.title
                for para in sh.text_frame.paragraphs:
                    for r in para.runs:
                        r.font.size = Pt(40 if is_title else 28)
                        if is_title:
                            r.font.bold = True
                            r.font.color.rgb = RGBColor(0x1F, 0x4E, 0x79)


def _save(p) -> bytes:
    _widen(p)
    b = io.BytesIO()
    p.save(b)
    return b.getvalue()


def _new(widescreen: bool = True) -> Presentation:
    p = Presentation()
    if widescreen:
        p.slide_width, p.slide_height = Inches(13.333), Inches(7.5)
    return p


def _title(p, title: str, subtitle: str = "", notes: str = ""):
    s = p.slides.add_slide(p.slide_layouts[0])
    s.shapes.title.text = title
    s.placeholders[1].text = subtitle
    if notes:
        s.notes_slide.notes_text_frame.text = notes
    return s


def _bullets(p, title: str, items: List[str], notes: str = ""):
    s = p.slides.add_slide(p.slide_layouts[1])
    s.shapes.title.text = title
    tf = s.placeholders[1].text_frame
    tf.text = items[0]
    for it in items[1:]:
        tf.add_paragraph().text = it
    if notes:
        s.notes_slide.notes_text_frame.text = notes
    return s


def _blank_title(p, title: str):
    s = p.slides.add_slide(p.slide_layouts[5])   # title only
    s.shapes.title.text = title
    return s


def _chart(p, title: str, cats: List[str], series: List[Tuple[str, List[float]]], kind=None, notes: str = ""):
    s = _blank_title(p, title)
    cd = CategoryChartData()
    cd.categories = cats
    for name, vals in series:
        cd.add_series(name, vals)
    s.shapes.add_chart(kind or XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(1.6), Inches(11), Inches(5.2), cd)
    if notes:
        s.notes_slide.notes_text_frame.text = notes
    return s


def _table(p, title: str, rows: List[List[str]], notes: str = ""):
    s = _blank_title(p, title)
    t = s.shapes.add_table(len(rows), len(rows[0]), Inches(1), Inches(1.8), Inches(11), Inches(0.5 * len(rows))).table
    for r, row in enumerate(rows):
        for c, v in enumerate(row):
            t.cell(r, c).text = v
    if notes:
        s.notes_slide.notes_text_frame.text = notes
    return s


def _image(p, title: str, caption: str, alt: str, notes: str = ""):
    s = _blank_title(p, title)
    pic = s.shapes.add_picture(io.BytesIO(_png(label=alt)), Inches(2.5), Inches(1.6), width=Inches(8))
    pic._element.nvPicPr.cNvPr.set("descr", alt)
    tb = s.shapes.add_textbox(Inches(2.5), Inches(6.6), Inches(8), Inches(0.5))
    tb.text_frame.text = caption
    if notes:
        s.notes_slide.notes_text_frame.text = notes
    return s


def business_en() -> bytes:
    p = _new()
    _title(p, "Northwind Coffee: 2026 Growth Plan", "Board update, Q3", "Open with the headline: we grew revenue 34 percent while opening only 6 stores. The rest of the deck explains how.")
    _bullets(p, "Agenda", ["Where we are", "What worked", "The numbers", "Next 12 months"])
    _bullets(p, "Where we are", ["Revenue reached $48.2M in 2025", "112 stores in 9 states", "Customer retention rose to 71 percent", "Online orders are now 23 percent of sales"],
             "Stress that online orders were 9 percent two years ago. Retention is the number the CEO cares about most.")
    _chart(p, "Revenue by year ($M)", ["2022", "2023", "2024", "2025"], [("Revenue", [21.0, 28.4, 36.0, 48.2])], notes="Growth accelerated each year; 2025 is the first year above 30 percent.")
    _image(p, "The new Portland flagship", "Opened March 2025", "Portland flagship store interior", "The flagship tests our new drive-through concept. It sold 1,900 drinks per day in its first month.")
    _table(p, "Store economics", [["Format", "Stores", "Payback (months)"], ["Flagship", "4", "26"], ["Standard", "98", "19"], ["Kiosk", "10", "11"]],
           "Kiosks pay back fastest, which is why they lead the plan.")
    _chart(p, "Online share of sales (%)", ["Q1", "Q2", "Q3", "Q4"], [("Online", [14, 17, 20, 23]), ("In store", [86, 83, 80, 77])], kind=XL_CHART_TYPE.LINE_MARKERS)
    s = p.slides.add_slide(p.slide_layouts[3])   # two content
    s.shapes.title.text = "Risks and mitigations"
    for ph, items in ((s.placeholders[1], ["Coffee bean prices up 18 percent", "Labour costs rising"]), (s.placeholders[2], ["Hedge 60 percent of 2026 volume", "Automate ordering at kiosks"])):
        ph.text_frame.text = items[0]
        ph.text_frame.add_paragraph().text = items[1]
    s.notes_slide.notes_text_frame.text = "Left side is the risk, right side is what we do about it."
    _bullets(p, "Next 12 months", ["Open 20 kiosks", "Launch loyalty app v2", "Break even in Texas by Q2"], "Ask the board to approve the kiosk budget of $3.1M.")
    _title(p, "Thank you", "Questions?")
    return _save(p)


def spanish_6() -> bytes:
    p = _new()
    _title(p, "Plan de energía solar para escuelas", "Propuesta al ayuntamiento", "El objetivo es reducir la factura eléctrica de las escuelas municipales a la mitad en tres años.")
    _bullets(p, "El problema", ["Las 24 escuelas gastan 1,8 millones de euros al año en electricidad", "El consumo crece un 6 % anual", "El 70 % de los tejados está sin usar"], "Subraya que el dinero ahorrado volvería a las aulas.")
    _chart(p, "Ahorro previsto (miles de euros)", ["Año 1", "Año 2", "Año 3"], [("Ahorro", [180, 520, 910])], notes="El ahorro crece porque cada año se instalan más escuelas.")
    _table(p, "Coste por fase", [["Fase", "Escuelas", "Inversión (M€)"], ["Piloto", "4", "0,6"], ["Ampliación", "12", "1,7"], ["Final", "8", "1,1"]])
    _bullets(p, "Qué pedimos", ["Aprobar la fase piloto", "Crear una comisión con las direcciones de los centros", "Revisar resultados a los 12 meses"])
    _title(p, "Gracias", "Preguntas")
    return _save(p)


def long_deck(n: int = 20, dark: bool = True) -> bytes:
    p = _new()
    _title(p, "Platform Reliability Review", "Engineering all-hands", "")
    for i in range(1, n):
        kind = i % 4
        if kind == 1:
            s = _bullets(p, f"Finding {i}: latency budget", [f"p99 latency {100 + i * 7} ms", f"Error rate {0.1 * i:.1f} percent", "Owner: platform team"], f"Notes for finding {i}.")
        elif kind == 2:
            s = _chart(p, f"Incidents per month, team {i}", ["Jan", "Feb", "Mar", "Apr"], [("Incidents", [3 + i, 5, 2, 4])])
        elif kind == 3:
            s = _table(p, f"Capacity plan {i}", [["Region", "Nodes"], ["us-east", str(10 + i)], ["eu-west", str(8 + i)]])
        else:
            s = _image(p, f"Architecture {i}", "Simplified diagram", f"diagram {i}")
    _widen(p)
    if dark:
        for s in p.slides:
            bg = s.background.fill
            bg.solid()
            bg.fore_color.rgb = RGBColor(0x12, 0x16, 0x24)
            for sh in s.shapes:
                if sh.has_text_frame:
                    for para in sh.text_frame.paragraphs:
                        for r in para.runs:
                            r.font.color.rgb = RGBColor(0xF2, 0xF2, 0xF2)
                            r.font.name = "Montserrat"   # a font the converter will not have: substituted
    b = io.BytesIO()
    p.save(b)
    return b.getvalue()


def nasty() -> bytes:
    """A deck that is hard to render and hostile in small ways, but still a valid, macro-free pptx."""
    p = _new()
    _title(p, "Nasty deck 日本語 🚀", "emoji, CJK, long text", "Notes with <b>markup</b> & entities &amp; a url http://169.254.169.254/latest/meta-data/ that must stay text.")
    s = p.slides.add_slide(p.slide_layouts[6])   # blank with 120 shapes, some rotated, one group
    for i in range(120):
        sh = s.shapes.add_shape(1, Inches(0.3 + (i % 12) * 1.05), Inches(0.3 + (i // 12) * 0.7), Inches(0.9), Inches(0.5))
        sh.rotation = (i * 7) % 360
        sh.text_frame.text = str(i)
    grp = s.shapes.add_group_shape()
    grp.shapes.add_textbox(Inches(1), Inches(1), Inches(3), Inches(1)).text_frame.text = "Grouped text"
    s = _bullets(p, "Overflowing text", ["This bullet is very long. " * 30] * 6, "")
    s = p.slides.add_slide(p.slide_layouts[6])   # empty slide
    s = _bullets(p, "Click me", ["Hyperlink to an external site"], "")
    r = s.placeholders[1].text_frame.paragraphs[0].runs[0]
    r.hyperlink.address = "http://127.0.0.1:9/ssrf-probe"
    s = _bullets(p, "Hidden slide", ["Hidden from the show"], "")
    s._element.set("show", "0")
    s = _bullets(p, "Animated slide", ["One", "Two", "Three"], "")
    s._element.append(s._element.makeelement("{http://schemas.openxmlformats.org/presentationml/2006/main}transition", {"spd": "slow"}))
    b = io.BytesIO()
    p.save(b)
    data = b.getvalue()
    # an external linked image relationship (a remote URL): must never be fetched
    zin = zipfile.ZipFile(io.BytesIO(data))
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for n in zin.namelist():
            raw = zin.read(n)
            if n == "ppt/slides/_rels/slide1.xml.rels":
                raw = raw.replace(b"</Relationships>", b'<Relationship Id="rIdX1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="http://127.0.0.1:9/linked.png" TargetMode="External"/></Relationships>')
            z.writestr(n, raw)
    return out.getvalue()


def pdf_deck(pages: int = 3) -> bytes:
    """A small multi-page PDF (a Google Slides or Keynote export looks like this)."""
    ims = [Image.open(io.BytesIO(_png(1600, 900, f"Page {i + 1}", c1=(20 + i * 40, 60, 120)))).convert("RGB") for i in range(pages)]
    b = io.BytesIO()
    ims[0].save(b, "PDF", save_all=True, append_images=ims[1:], resolution=100)
    return b.getvalue()
