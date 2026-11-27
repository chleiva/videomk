"""Ownership marking of VideoMK's own library images (docs/LIBRARY_ON_DEMAND.md, "Ownership marking", layer a): embedded metadata that says whose picture it is.

`mark_jpeg(jpeg, asset_id=..., title=...)` writes, WITHOUT touching a single pixel (the JPEG's own data is copied byte for byte; only metadata segments are
added or replaced):
  * EXIF: Artist, Copyright, ImageDescription, Software
  * XMP:  dc:creator, dc:rights, dc:title, dc:identifier, xmpRights:Marked / Owner / WebStatement / UsageTerms, photoshop:Credit / Source / CopyrightFlag,
          Iptc4xmpCore:CreatorContactInfo (email, web), Iptc4xmpExt:DigitalSourceType = IPTC's "trainedAlgorithmicMedia" (the standard disclosure that a
          picture was made by a generative model), plus:Licensor, and videomk:AssetId / Library
`read_marks(jpeg)` reads them back (the test of every ingest, and the backfill's check).

Honest limits: metadata is removed by anything that re-encodes or strips a file (most social platforms, a screenshot, and our own renderer, which draws the
picture into video frames). It marks the FILE in our library, not the pixels in a customer's video. The proof of ownership stays the library record, the
generation receipt and this file.
"""
import io
import struct
from typing import Any, Dict, Optional
from xml.sax.saxutils import escape

OWNER = "Agilegency Ltd"
PRODUCT = "VideoMK"
CONTACT = "hello@videomk.com"
WEB = "https://videomk.com"
AI_SOURCE = "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"
XMP_HEADER = b"http://ns.adobe.com/xap/1.0/\x00"
EXIF_HEADER = b"Exif\x00\x00"


def rights_line(year: int) -> str:
    return f"© {year} {OWNER} ({PRODUCT}). All rights reserved. AI-generated image from the {PRODUCT} library; not licensed for standalone use."


def xmp_packet(asset_id: str, title: str, year: int) -> bytes:
    t, r = escape(title or "VideoMK library image"), escape(rights_line(year))
    x = f"""<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>
<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">
<rdf:Description rdf:about="" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:xmpRights="http://ns.adobe.com/xap/1.0/rights/" xmlns:photoshop="http://ns.adobe.com/photoshop/1.0/"
 xmlns:Iptc4xmpCore="http://iptc.org/std/Iptc4xmpCore/1.0/xmlns/" xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/" xmlns:plus="http://ns.useplus.org/ldf/xmp/1.0/"
 xmlns:videomk="https://videomk.com/ns/library/1.0/"
 xmpRights:Marked="True" xmpRights:WebStatement="{WEB}/terms" photoshop:Credit="{PRODUCT}" photoshop:Source="{PRODUCT} library" photoshop:CopyrightFlag="True"
 Iptc4xmpExt:DigitalSourceType="{AI_SOURCE}" videomk:AssetId="{escape(asset_id)}" videomk:Library="{PRODUCT} library" videomk:AIGenerated="True">
<dc:creator><rdf:Seq><rdf:li>{OWNER}</rdf:li></rdf:Seq></dc:creator>
<dc:rights><rdf:Alt><rdf:li xml:lang="x-default">{r}</rdf:li></rdf:Alt></dc:rights>
<dc:title><rdf:Alt><rdf:li xml:lang="x-default">{t}</rdf:li></rdf:Alt></dc:title>
<dc:identifier>{escape(asset_id)}</dc:identifier>
<xmpRights:Owner><rdf:Bag><rdf:li>{OWNER}</rdf:li></rdf:Bag></xmpRights:Owner>
<xmpRights:UsageTerms><rdf:Alt><rdf:li xml:lang="x-default">Property of {OWNER}. Used inside {PRODUCT} videos only.</rdf:li></rdf:Alt></xmpRights:UsageTerms>
<Iptc4xmpCore:CreatorContactInfo Iptc4xmpCore:CiEmailWork="{CONTACT}" Iptc4xmpCore:CiUrlWork="{WEB}"/>
<plus:Licensor><rdf:Seq><rdf:li rdf:parseType="Resource"><plus:LicensorName>{OWNER}</plus:LicensorName><plus:LicensorEmail>{CONTACT}</plus:LicensorEmail><plus:LicensorURL>{WEB}</plus:LicensorURL></rdf:li></rdf:Seq></plus:Licensor>
</rdf:Description></rdf:RDF></x:xmpmeta>
<?xpacket end="w"?>"""
    return x.encode("utf-8")


def exif_block(asset_id: str, title: str, year: int) -> bytes:
    from PIL import Image

    ex = Image.Exif()
    ex[0x010E] = f"{title or 'VideoMK library image'} [asset {asset_id}]"   # ImageDescription
    ex[0x013B] = OWNER                                                       # Artist
    ex[0x8298] = rights_line(year).replace("©", "(c)")                       # Copyright (ASCII)
    ex[0x0131] = f"{PRODUCT} library (AI-generated)"                         # Software
    return ex.tobytes()


def _segments(jpeg: bytes):
    """(marker, payload) of every segment before the image data, and the offset where the rest (kept byte for byte) starts."""
    if jpeg[:2] != b"\xff\xd8":
        raise ValueError("not a JPEG")
    i, out = 2, []
    while i + 4 <= len(jpeg) and jpeg[i] == 0xFF and jpeg[i + 1] not in (0xDA, 0xD9):
        n = struct.unpack(">H", jpeg[i + 2:i + 4])[0]
        out.append((jpeg[i + 1], jpeg[i + 4:i + 2 + n]))
        i += 2 + n
    return out, i


def _seg(marker: int, payload: bytes) -> bytes:
    if len(payload) > 65533:
        raise ValueError("metadata segment too large")
    return b"\xff" + bytes([marker]) + struct.pack(">H", len(payload) + 2) + payload


def mark_jpeg(jpeg: bytes, *, asset_id: str, title: str = "", year: Optional[int] = None) -> bytes:
    """The same picture with the ownership metadata. Pixels are untouched; an earlier EXIF or XMP block is replaced; every other segment is kept."""
    import time

    year = year or time.gmtime().tm_year
    segs, rest = _segments(jpeg)
    keep = [(m, p) for m, p in segs if not (m == 0xE1 and (p.startswith(EXIF_HEADER) or p.startswith(XMP_HEADER)))]
    head = [s for s in keep if s[0] == 0xE0]            # JFIF stays first, as decoders expect
    tail = [s for s in keep if s[0] != 0xE0]
    ex = exif_block(asset_id, title, year)
    ex = ex if ex.startswith(EXIF_HEADER) else EXIF_HEADER + ex
    mine = [(0xE1, ex), (0xE1, XMP_HEADER + xmp_packet(asset_id, title, year))]
    return b"\xff\xd8" + b"".join(_seg(m, p) for m, p in head + mine + tail) + jpeg[rest:]


def read_marks(jpeg: bytes) -> Dict[str, Any]:
    """What a file says about its owner: {} when it carries none of our marks."""
    import re
    from PIL import Image

    out: Dict[str, Any] = {}
    try:
        segs, _ = _segments(jpeg)
    except ValueError:
        return out
    for m, p in segs:
        if m == 0xE1 and p.startswith(XMP_HEADER):
            x = p[len(XMP_HEADER):].decode("utf-8", "replace")
            for key, rx in (("asset_id", r'videomk:AssetId="([^"]+)"'), ("source_type", r'Iptc4xmpExt:DigitalSourceType="([^"]+)"'), ("credit", r'photoshop:Credit="([^"]+)"'),
                            ("creator", r"<dc:creator><rdf:Seq><rdf:li>([^<]+)"), ("rights", r'<dc:rights><rdf:Alt><rdf:li xml:lang="x-default">([^<]+)'),
                            ("email", r'Iptc4xmpCore:CiEmailWork="([^"]+)"'), ("marked", r'xmpRights:Marked="([^"]+)"'), ("owner", r"<xmpRights:Owner><rdf:Bag><rdf:li>([^<]+)")):
                hit = re.search(rx, x)
                if hit:
                    out[key] = hit.group(1)
    try:
        ex = Image.open(io.BytesIO(jpeg)).getexif()
        if ex.get(0x013B):
            out["exif_artist"] = str(ex.get(0x013B))
        if ex.get(0x8298):
            out["exif_copyright"] = str(ex.get(0x8298))
    except Exception:
        pass
    return out


def is_marked(jpeg: bytes, asset_id: Optional[str] = None) -> bool:
    m = read_marks(jpeg)
    return m.get("creator") == OWNER and m.get("exif_artist") == OWNER and m.get("source_type") == AI_SOURCE and bool(m.get("asset_id")) and (asset_id is None or m["asset_id"] == asset_id)
