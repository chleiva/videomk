#!/usr/bin/env python3.11
"""Text -> SVG outline paths (fontTools; kerning from GPOS pair positioning). Writes wordmarks.json next to this file.
Units: 1000 per em, y down, baseline at y=0."""
import json, os, sys
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

HERE = os.path.dirname(os.path.abspath(__file__))
F = os.path.join(HERE, "fonts")
_cache = {}


def font(name, **axes):
    key = (name, tuple(sorted(axes.items())))
    if key not in _cache:
        f = TTFont(os.path.join(F, name + ".ttf"))
        if "fvar" in f:
            lim = {a.axisTag: axes.get(a.axisTag, a.defaultValue) for a in f["fvar"].axes}
            f = instancer.instantiateVariableFont(f, lim)
        _cache[key] = f
    return _cache[key]


def kern(f, a, b):
    if "GPOS" not in f:
        return 0
    t = f["GPOS"].table
    idx = set()
    for fr in t.FeatureList.FeatureRecord:
        if fr.FeatureTag == "kern":
            idx.update(fr.Feature.LookupListIndex)
    for i in sorted(idx):
        lk = t.LookupList.Lookup[i]
        for st in lk.SubTable:
            if lk.LookupType == 9:
                st = st.ExtSubTable
            if getattr(st, "LookupType", lk.LookupType) != 2 and lk.LookupType != 9:
                continue
            if not hasattr(st, "Coverage") or a not in st.Coverage.glyphs:
                continue
            if st.Format == 1:
                ps = st.PairSet[st.Coverage.glyphs.index(a)]
                for r in ps.PairValueRecord:
                    if r.SecondGlyph == b:
                        return (r.Value1.XAdvance or 0) if r.Value1 else 0
            elif st.Format == 2:
                c1 = st.ClassDef1.classDefs.get(a, 0)
                c2 = st.ClassDef2.classDefs.get(b, 0)
                v = st.Class1Record[c1].Class2Record[c2].Value1
                x = (v.XAdvance or 0) if v else 0
                if x:
                    return x
    return 0


def run(f, text, tracking=0.0, x0=0.0):
    """-> (d, advance) in 1000/em units. tracking in em/1000 added after every glyph."""
    upm = f["head"].unitsPerEm
    k = 1000.0 / upm
    gs = f.getGlyphSet()
    cmap = f.getBestCmap()
    names = [cmap[ord(c)] for c in text]
    x = x0
    out = []
    for i, g in enumerate(names):
        pen = SVGPathPen(gs, ntos=lambda v: ("%.2f" % v).rstrip("0").rstrip("."))
        gs[g].draw(TransformPen(pen, (k, 0, 0, -k, x, 0)))
        out.append(pen.getCommands())
        x += gs[g].width * k + tracking
        if i + 1 < len(names):
            x += kern(f, g, names[i + 1]) * k
    return "".join(out), x - tracking - x0


def build(segs, join_kern=0.0):
    """segs: list of (fontname, axes, text, tracking). -> {segs:[{d,x,w}], width, cap, xh}"""
    x = 0.0
    res = []
    cap = xh = 0
    for i, (name, axes, text, tr) in enumerate(segs):
        f = font(name, **axes)
        d, w = run(f, text, tr, x)
        res.append({"d": d, "x": round(x, 2), "w": round(w, 2), "text": text})
        x += w + (tr if text.endswith(" ") is False else 0) + (join_kern if i + 1 < len(segs) else 0)
        os2 = f["OS/2"]
        k = 1000.0 / f["head"].unitsPerEm
        cap = max(cap, getattr(os2, "sCapHeight", 700) * k)
        xh = max(xh, getattr(os2, "sxHeight", 500) * k)
    return {"segs": res, "width": round(x, 2), "cap": round(cap, 2), "xh": round(xh, 2)}


I = lambda w: ("Inter", {"wght": w, "opsz": 32})
W = {
    # the recommended wordmark: Inter Display, Video 600 + MK 800, tracking -18
    "inter_shift": build([(*I(600), "Video", -18), (*I(800), "MK", -10)]),
    "inter_700": build([(*I(700), "VideoMK", -18)]),
    "inter_600": build([(*I(600), "VideoMK", -16)]),
    "manrope_shift": build([("Manrope", {"wght": 600}, "Video", -14), ("Manrope", {"wght": 800}, "MK", -8)]),
    "sora_600": build([("Sora", {"wght": 600}, "VideoMK", -22)]),
    "jakarta_shift": build([("PlusJakartaSans", {"wght": 600}, "Video", -14), ("PlusJakartaSans", {"wght": 800}, "MK", -8)]),
    "made_with": build([(*I(500), "Made with ", -6), (*I(600), "Video", -18), (*I(800), "MK", -10)]),
    "hecho_con": build([(*I(500), "Hecho con ", -6), (*I(600), "Video", -18), (*I(800), "MK", -10)]),
    "url": build([(*I(500), "videomk.com", 2)]),
}
json.dump(W, open(os.path.join(HERE, "wordmarks.json"), "w"))
for k, v in W.items():
    print(k, v["width"], v["cap"], [(s["text"], s["x"], s["w"]) for s in v["segs"]])
