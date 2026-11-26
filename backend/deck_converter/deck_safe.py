"""Hostile-input checks for an uploaded deck. Pure Python, no network, no model, no conversion: everything here runs before anything opens the file for real.

What it guarantees when `inspect_pptx` returns: the bytes are a zip with a sane size, entry count and compression ratio; no entry name escapes; no macro, ActiveX or
OLE part; every XML part parses with DTDs and entities forbidden (defusedxml); at most MAX_SLIDES slides. `sanitize_pptx` then rewrites the package WITHOUT the embedded
workbooks and WITHOUT any external relationship (hyperlinks, linked images, remote templates), so nothing the converter opens can name a URL or a file.
External references are counted and never resolved. `DeckError.code` is the machine code the API returns; the English `detail` is for logs only (it never holds slide text).
"""
import io
import posixpath
import re
import zipfile
from typing import Any, Dict, List, Optional, Tuple

import defusedxml.ElementTree as SafeET
from defusedxml.common import DefusedXmlException

MAX_BYTES = 50 * 1024 * 1024
MAX_SLIDES = 60
MAX_ENTRIES = 4000
MAX_TOTAL_UNCOMPRESSED = 500 * 1024 * 1024
MAX_ENTRY_UNCOMPRESSED = 120 * 1024 * 1024
MAX_XML_PART = 24 * 1024 * 1024
MAX_RATIO = 250            # per entry, applied once an entry exceeds 1 MB uncompressed (XML compresses 10 to 30 times, a bomb 1000 and more)
MAX_PDF_PAGES = 60

OLE_MAGIC = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"   # legacy .ppt, and what a password-protected Office file is saved as
ZIP_MAGIC = b"PK\x03\x04"
_SLIDE_RE = re.compile(r"^ppt/slides/slide\d+\.xml$")
_FORBIDDEN = re.compile(r"(^|/)(vbaproject[^/]*|vbadata\.xml)$|^ppt/activex/|^ppt/ctrlprops/|^ppt/embeddings/[^/]*\.(bin|ole|exe|dll)$|oleobject\d*\.bin$|\.(exe|dll|js|vbs|bat|cmd|ps1|sh|jar)$", re.I)


class DeckError(Exception):
    """A deck that cannot be used. `code` is stable (apps switch on it); `detail` is English and for logs; it never contains slide text."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code, self.detail = code, detail


def kind_of(head: bytes) -> str:
    """'pptx', 'pdf', 'ole' (legacy or encrypted Office file) or '' from the first bytes. The file name and content type are never trusted."""
    if head.startswith(ZIP_MAGIC):
        return "pptx"
    if head.startswith(b"%PDF-"):
        return "pdf"
    if head.startswith(OLE_MAGIC):
        return "ole"
    return ""


def _safe_name(name: str) -> bool:
    if not name or name.startswith("/") or "\\" in name or "\x00" in name or len(name) > 260:
        return False
    return ".." not in name.split("/")


def inspect_pptx(raw: bytes, max_slides: int = MAX_SLIDES) -> Dict[str, Any]:
    """Validates a pptx package and returns {"slides": n, "entries": n, "external_refs": n, "uncompressed": bytes}. Raises DeckError."""
    if len(raw) > MAX_BYTES:
        raise DeckError("deck_too_large", f"{len(raw)} bytes")
    if raw.startswith(OLE_MAGIC):
        raise DeckError("deck_encrypted", "OLE container (legacy .ppt or password protected)")
    if not raw.startswith(ZIP_MAGIC):
        raise DeckError("deck_unsupported", "not a zip package")
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        infos = zf.infolist()
    except (zipfile.BadZipFile, ValueError, OSError, EOFError, NotImplementedError) as e:
        raise DeckError("deck_corrupt", type(e).__name__)
    if len(infos) > MAX_ENTRIES:
        raise DeckError("deck_unsafe", f"{len(infos)} entries")
    names, total = set(), 0
    for i in infos:
        if not _safe_name(i.filename):
            raise DeckError("deck_unsafe", "entry name")
        if i.filename.lower() in names:
            raise DeckError("deck_unsafe", "duplicate entry")
        names.add(i.filename.lower())
        if i.flag_bits & 0x1:
            raise DeckError("deck_encrypted", "encrypted zip entry")
        if i.is_dir():
            continue
        if i.file_size > MAX_ENTRY_UNCOMPRESSED:
            raise DeckError("deck_unsafe", "entry too large")
        if i.file_size > 1024 * 1024 and i.file_size > MAX_RATIO * max(1, i.compress_size):
            raise DeckError("deck_unsafe", "compression ratio")
        if _FORBIDDEN.search(i.filename):
            raise DeckError("deck_macro", "macro, ActiveX or OLE part")
        total += i.file_size
    if total > MAX_TOTAL_UNCOMPRESSED:
        raise DeckError("deck_unsafe", "total size")
    if "[content_types].xml" not in names or "ppt/presentation.xml" not in names:
        raise DeckError("deck_unsupported", "not a PowerPoint package")
    slides = [i for i in infos if _SLIDE_RE.match(i.filename)]
    if not slides:
        raise DeckError("deck_empty", "no slides")
    if len(slides) > max_slides:
        raise DeckError("deck_too_many_slides", f"{len(slides)} slides")
    external = 0
    for i in infos:
        if i.is_dir() or not i.filename.lower().endswith((".xml", ".rels")):
            continue
        data = _read_bounded(zf, i)
        if i.filename == "[Content_Types].xml" and (b"macroEnabled" in data or b"vbaProject" in data):
            raise DeckError("deck_macro", "macro-enabled content type")
        try:
            root = SafeET.fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
        except DefusedXmlException:
            raise DeckError("deck_unsafe", "DTD or entity in XML")
        except Exception:
            raise DeckError("deck_corrupt", "XML does not parse")
        if i.filename.endswith(".rels"):
            external += sum(1 for el in root if el.get("TargetMode") == "External")
    return {"slides": len(slides), "entries": len(infos), "external_refs": external, "uncompressed": total}


def _read_bounded(zf: zipfile.ZipFile, info: zipfile.ZipInfo, limit: int = MAX_XML_PART) -> bytes:
    """Reads an entry counting the bytes actually produced, not the size the header claims."""
    out = bytearray()
    with zf.open(info) as f:
        while True:
            chunk = f.read(1 << 20)
            if not chunk:
                break
            out += chunk
            if len(out) > min(limit, MAX_ENTRY_UNCOMPRESSED):
                raise DeckError("deck_unsafe", "entry grew past its limit")
    return bytes(out)


def sanitize_pptx(raw: bytes) -> bytes:
    """The package without embedded workbooks and without external relationships. Call after `inspect_pptx` accepted it."""
    from lxml import etree

    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False, dtd_validation=False, huge_tree=False)
    zin = zipfile.ZipFile(io.BytesIO(raw))
    dropped = {i.filename for i in zin.infolist() if i.filename.startswith("ppt/embeddings/")}
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for i in zin.infolist():
            if i.is_dir() or i.filename in dropped:
                continue
            data = _read_bounded(zin, i, limit=MAX_ENTRY_UNCOMPRESSED)
            if i.filename.endswith(".rels"):
                base = posixpath.dirname(posixpath.dirname(i.filename))
                root = etree.fromstring(data, parser)
                for el in list(root):
                    target = el.get("Target") or ""
                    resolved = posixpath.normpath(posixpath.join(base, target)) if not target.startswith("/") else target.lstrip("/")
                    if el.get("TargetMode") == "External" or resolved in dropped:
                        root.remove(el)
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            elif i.filename == "[Content_Types].xml":
                root = etree.fromstring(data, parser)
                for el in list(root):
                    if (el.get("PartName") or "").lstrip("/") in dropped:
                        root.remove(el)
                data = etree.tostring(root, xml_declaration=True, encoding="UTF-8", standalone=True)
            z.writestr(i.filename, data)
    return out.getvalue()


def inspect_pdf(raw: bytes, max_pages: int = MAX_PDF_PAGES) -> Dict[str, Any]:
    """A PDF deck: magic bytes, size, no encryption, no active content keywords. The page count is checked after rendering with pdfinfo."""
    if len(raw) > MAX_BYTES:
        raise DeckError("deck_too_large", f"{len(raw)} bytes")
    if not raw.startswith(b"%PDF-"):
        raise DeckError("deck_unsupported", "not a pdf")
    head = raw[: 2 * 1024 * 1024] + raw[-1024 * 1024:]
    if b"/Encrypt" in head:
        raise DeckError("deck_encrypted", "encrypted pdf")
    if re.search(rb"/(JavaScript|JS|Launch|EmbeddedFile)\b", raw):
        raise DeckError("deck_macro", "pdf with scripts, launch actions or embedded files")
    return {"pdf": True}
