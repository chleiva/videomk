#!/usr/bin/env python3
"""Merge the vision audit(s) into the stored stand zones, and make the contact sheet (docs/CARTOON_GROUND_2026-11-28.md).

  python backend/scripts/vector_stand_build.py --audit a.json [b.json ...] --thumbs DIR --out-zones common/vector_stand_zones.json [--sheet OUTDIR] [--overrides overrides.json]

`overrides.json`: {id: {"usable": false, "reason": "..."}} decisions taken by eye (a verdict by a person beats the model's). Per scene the record keeps the model's polygons, its verdict,
the per-shape numbers (`shapes`: max_cast, the standing row) computed by engine/stand_zone.py, and the final `usable`: the model said so AND the engine can place at least one character
in at least one of the shapes the scene is used in (its own shape and the crops).
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from engine import stand_zone as sz  # noqa: E402


def merge(audits, overrides, prev):
    zones = {}
    for sid in sorted({k for a in audits for k in a}):
        a = next(x[sid] for x in audits if sid in x)   # the first audit given is the one whose polygons are used
        z = {"usable": bool(a["usable"]) and bool(a["ground"]), "native": "9:16" if sid.startswith("tall_") else "16:9", "ground": a["ground"], "hazards": a["hazards"],
             "reason": a["reason"], "model": a.get("model", ""), "model_capacity": a["capacity"]}
        if len(audits) > 1:
            z["cross_check"] = [{"model": x[sid].get("model", ""), "usable": x[sid]["usable"], "capacity": x[sid]["capacity"], "reason": x[sid]["reason"]} for x in audits if sid in x]
        if prev.get(sid, {}).get("disabled"):
            z["disabled"], z["usable"] = True, False
            z["reason"] = prev[sid].get("reason", z["reason"])
        o = overrides.get(sid)
        if o:
            z.update({k: v for k, v in o.items() if k in ("usable", "ground", "hazards", "reason", "disabled")})
            z["by_eye"] = True
        zones[sid] = z
    return zones


def lines_and_shapes(zones, path):
    """Ground line per shape (engine/stand_zone.derive_lines) for every backdrop the audit accepted; a backdrop whose ground yields no line in any shape is not usable.
    Then the per shape numbers the contact sheet shows."""
    for sid, z in zones.items():
        z.pop("ground_line", None)
    json.dump({"version": 1, "zones": zones}, open(path, "w"), separators=(",", ":"))
    sz.reload()
    for sid, z in zones.items():
        if not z.get("usable"):
            continue
        z["ground_line"] = sz.derive_lines(sid)
        if not z["ground_line"]:
            z["usable"], z["reason"] = False, (z["reason"] + " | no shape has a ground line the engine can place on").strip(" |")
    json.dump({"version": 1, "zones": zones}, open(path, "w"), separators=(",", ":"))
    sz.reload()
    for sid, z in zones.items():
        z["shapes"] = {a: {"max_cast": (sz.max_cast(sid, a) if z.get("usable") else 0), "casts": [n for n in (1, 2, 3) if z.get("usable") and sz.holds(sid, a, n)]} for a in ("16:9", "9:16", "1:1", "4:5")}
    json.dump({"version": 1, "zones": zones}, open(path, "w"), separators=(",", ":"))
    sz.reload()


def sheet(zones, thumbs, outdir):
    os.makedirs(outdir, exist_ok=True)
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 15)
    except OSError:
        font = ImageFont.load_default()
    ids = sorted(zones)
    cols, cw, ch = 4, 360, 330
    per = 24
    pages = []
    for p0 in range(0, len(ids), per):
        chunk = ids[p0:p0 + per]
        rows = (len(chunk) + cols - 1) // cols
        im = Image.new("RGB", (cols * cw, rows * ch), (24, 24, 28))
        for i, sid in enumerate(chunk):
            z = zones[sid]
            t = Image.open(os.path.join(thumbs, sid, "thumb.jpg")).convert("RGB")
            box_w, box_h = cw - 8, 250
            k = min(box_w / t.width, box_h / t.height)
            t = t.resize((int(t.width * k), int(t.height * k)))
            ov = Image.new("RGBA", t.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(ov)
            for poly in z.get("ground") or []:
                d.polygon([(x * t.width, y * t.height) for x, y in poly], fill=(40, 220, 80, 90), outline=(20, 255, 60, 255))
            for poly in z.get("hazards") or []:
                d.polygon([(x * t.width, y * t.height) for x, y in poly], fill=(255, 40, 40, 70), outline=(255, 60, 60, 255))
            # the engine's own feet for 3 (else the largest cast) in the scene's own shape
            asp = "9:16" if z["native"] == "9:16" else "16:9"
            n = z.get("shapes", {}).get(asp, {}).get("max_cast", 0)
            if z.get("usable") and n:
                try:
                    pts = sz.foot_points(sz._cast_props(sid, n), asp)
                    for x, y in pts:
                        yy = min(y, 1.0)
                        d.ellipse((x * t.width - 6, yy * t.height - 6, x * t.width + 6, yy * t.height + 6), fill=(255, 220, 0, 255), outline=(0, 0, 0, 255))
                except Exception:  # noqa: BLE001
                    pass
            # the shapes a backdrop is served in: its own, and the centre crop of the square (16:9) or 4:5 (tall) one; the ideal ground line (yellow) and its band (white) in each
            for asp2, col2 in ((asp, (255, 230, 0, 255)), ("1:1" if asp == "16:9" else "4:5", (0, 230, 255, 255))):
                gl = (z.get("ground_line") or {}).get(asp2) if z.get("usable") else None
                if not gl:
                    continue
                cx0, cy0, cx1, cy1 = sz._crop(z["native"], asp2)
                if asp2 != asp:
                    d.rectangle((cx0 * t.width, cy0 * t.height, cx1 * t.width - 1, cy1 * t.height - 1), outline=col2, width=1)
                def yy_(v):
                    return (cy0 + min(v, 0.995) * (cy1 - cy0)) * t.height
                d.line([(cx0 * t.width, yy_(gl["y"])), (cx1 * t.width, yy_(gl["y"]))], fill=col2, width=2)
                for yb in gl["band"]:
                    d.line([(cx0 * t.width, yy_(yb)), (cx1 * t.width, yy_(yb))], fill=(255, 255, 255, 170), width=1)
            t = Image.alpha_composite(t.convert("RGBA"), ov).convert("RGB")
            x0, y0 = (i % cols) * cw + 4, (i // cols) * ch + 4
            im.paste(t, (x0, y0))
            dd = ImageDraw.Draw(im)
            verdict = "RETIRED" if z.get("disabled") else ("OK" if z.get("usable") else "NO")
            col = {"OK": (80, 230, 110), "NO": (255, 90, 90), "RETIRED": (255, 150, 40)}[verdict]
            caps = " ".join(f"{a}:{z['shapes'][a]['max_cast']}" for a in ("16:9", "9:16", "1:1", "4:5")) if "shapes" in z else ""
            dd.text((x0, y0 + 254), f"{verdict}  {sid}", fill=col, font=font)
            dd.text((x0, y0 + 272), caps, fill=(200, 200, 210), font=font)
            dd.text((x0, y0 + 290), (z.get("reason") or "")[:52], fill=(150, 150, 160), font=font)
        name = f"sheet_{p0 // per + 1}.jpg"
        im.save(os.path.join(outdir, name), quality=88)
        pages.append(name)
    return pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit", nargs="+", required=True)
    ap.add_argument("--thumbs", required=True)
    ap.add_argument("--out-zones", required=True)
    ap.add_argument("--sheet")
    ap.add_argument("--overrides")
    a = ap.parse_args()
    audits = []
    for f in a.audit:
        merged = {}
        for g in f.split(","):
            merged.update(json.load(open(g)))
        audits.append(merged)
    overrides = json.load(open(a.overrides)) if a.overrides else {}
    prev = json.load(open(a.out_zones)).get("zones", {}) if os.path.exists(a.out_zones) else {}
    zones = merge(audits, overrides, prev)
    lines_and_shapes(zones, a.out_zones)
    if a.sheet:
        print(sheet(zones, a.thumbs, a.sheet))
    n_ok = sum(1 for z in zones.values() if z.get("usable"))
    print(f"{len(zones)} backdrops, {n_ok} usable for characters")


if __name__ == "__main__":
    main()
