#!/usr/bin/env python3
"""The phase 0 prototype: the water cycle on one board, drawn in time with a real narration (method D of experiments.py).

  water_cycle.py en|es [--size 1920x1080|3840x2160] [--from S --to S] [--out FILE] [--no-tip] [--still T] [--music]

The plan below is what a planner would write: items with a zone, a drawing or a label, and the narration word each is tied to. Nothing is positioned by time:
every item ENDS 0.15 s after its word starts (research note, 5.4), the pen is one pen, and the camera follows named views. A frame is a pure function of
time, so --from/--to renders any passage on its own (that is how the 4K passage is made, and how chunks would be rendered on Lambda).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import unicodedata

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import board as bd  # noqa: E402
import common  # noqa: E402
import primitives as pr  # noqa: E402
import trace as tr  # noqa: E402
import vectorize as vz  # noqa: E402

LINE = 22.0            # marker width in board units, the same for every drawing, label and connector
PEN_SPEED = 2500.0     # board units per second
FPS = 30
MUSIC = os.path.join(HERE, "..", "..", "music-draft", "calm-pad-dawn.mp3")

VIEWS = {            # camera windows on the 3840x2160 board: (x0, y0, width)
    "sun": (0, 0, 2400), "sea": (0, 810, 2400), "plant": (640, 810, 2400), "sky": (1500, 0, 2240),
    "mountain": (1300, 250, 2540), "river": (900, 830, 2360), "all": (0, 0, 3840),
}
TEXT = {
    "en": {"title": "Where does rain come from?", "evap": "evaporation", "cond": "condensation", "cycle": "The water cycle"},
    "es": {"title": "¿De dónde viene la lluvia?", "evap": "evaporación", "cond": "condensación", "cycle": "El ciclo del agua"},
}
# the narration word each item is tied to: (sentence index, word, which occurrence)
SAY = {
    "en": {"title": (0, "rain"), "sun": (1, "sun"), "heat": (2, "sun"), "sea": (2, "sea"), "vap1": (2, "water"), "vap2": (2, "gas"), "vap3": (2, "vapour"),
           "evap": (3, "evaporation"), "plant": (4, "plants"), "leaf": (4, "leaves"), "rise": (5, "rises"), "cloud": (5, "cold"), "drops": (5, "drops"),
           "cond": (6, "condensation"), "mountain": (7, "heavy"), "rain": (7, "rain"), "snow": (7, "snow"), "river": (8, "rivers"), "loop": (8, "again"), "cycle": (9, "cycle")},
    "es": {"title": (0, "lluvia"), "sun": (1, "sol"), "heat": (2, "sol"), "sea": (2, "mar"), "vap1": (2, "agua"), "vap2": (2, "gas"), "vap3": (2, "vapor"),
           "evap": (3, "evaporacion"), "plant": (4, "plantas"), "leaf": (4, "hojas"), "rise": (5, "sube"), "cloud": (5, "frio"), "drops": (5, "gotas"),
           "cond": (6, "condensacion"), "mountain": (7, "demasiado"), "rain": (7, "lluvia"), "snow": (7, "nieve"), "river": (8, "rios"), "loop": (8, "nuevo"), "cycle": (9, "agua")},
}


def _norm(w: str) -> str:
    w = unicodedata.normalize("NFD", w.lower())
    return re.sub(r"[^a-z]", "", "".join(c for c in w if unicodedata.category(c) != "Mn"))


def word_time(narr, key):
    si, word = key[0], key[1]
    hits = [w for w in narr["sentences"][si]["words"] if _norm(w[0]) == word]
    if not hits:
        raise KeyError(f"word {word!r} not in sentence {si}")
    return hits[key[2] if len(key) > 2 else 0][1]


def plan(lang):
    """The board plan: [(id, kind, spec, colour, view or None, extra)]. Positions are zones worked out once for 16:9; a planner would name zones, a layout step would place them."""
    T = TEXT[lang]
    return [
        ("title", "text", {"text": T["title"], "centre": (1480, 150), "size": 150}, bd.INK, None, {"dmax": 1.9}),
        ("sun", "art", {"sheet": ("sheet1", 0), "x": 150, "y": 215, "w": 540, "fills": "sun"}, bd.INK, None, {}),
        ("heat", "strokes", {"strokes": lambda: pr.dashes((300, 830), (255, 1400), 4, seed=1) + pr.dashes((455, 850), (455, 1420), 4, seed=2) + pr.dashes((610, 830), (655, 1400), 4, seed=3)},
         bd.ORANGE, ("sea", -0.1, 1.5), {"dmin": 0.9, "dmax": 1.2}),
        ("sea", "art", {"sheet": ("sheet1", 5), "x": 110, "y": 1500, "w": 1050}, bd.BLUE, None, {}),
        ("vap1", "strokes", {"strokes": lambda: pr.wavy_arrow((760, 1450), (815, 1030), seed=1)}, bd.BLUE, None, {}),
        ("vap2", "strokes", {"strokes": lambda: pr.wavy_arrow((945, 1450), (1000, 1000), seed=2)}, bd.BLUE, None, {}),
        ("vap3", "strokes", {"strokes": lambda: pr.wavy_arrow((1130, 1450), (1185, 1030), seed=3)}, bd.BLUE, None, {}),
        ("evap", "text", {"text": T["evap"], "centre": (1560, 1330), "size": 135, "underline": bd.RED}, bd.INK, None, {}),
        ("plant", "art", {"sheet": ("sheet1", 3), "x": 1960, "y": 1440, "w": 400, "fills": "plant"}, bd.INK, ("plant", -0.9, 1.1), {}),
        ("leaf", "strokes", {"strokes": lambda: pr.arrow([(2045, 1425), (2010, 1350), (2000, 1275)], seed=4, size=34) + pr.arrow([(2280, 1425), (2318, 1350), (2325, 1275)], seed=5, size=34)},
         bd.BLUE, None, {}),
        ("rise", "strokes", {"strokes": lambda: pr.arrow([(1010, 950), (1230, 720), (1660, 615), (2105, 640)], seed=6, size=52)}, bd.BLUE, ("sky", -0.5, 1.5), {"dmin": 0.9}),
        ("cloud", "art", {"sheet": ("sheet1", 1), "x": 2140, "y": 300, "w": 820}, bd.INK, None, {}),
        ("drops", "strokes", {"strokes": lambda: [pr.drop(x, y, 50) for x, y in ((2360, 600), (2500, 520), (2640, 630), (2780, 540), (2470, 690))], "width": 0.6}, bd.BLUE, None, {"dmin": 0.7}),
        ("cond", "text", {"text": T["cond"], "centre": (3370, 330), "size": 135}, bd.INK, None, {}),
        ("mountain", "art", {"sheet": ("sheet1", 2), "x": 2800, "y": 1000, "w": 950, "fills": "mountain"}, bd.INK, ("mountain", -1.0, 1.2), {}),
        ("rain", "strokes", {"strokes": lambda: pr.rain(2700, 3080, 850, 1090, seed=7)}, bd.BLUE, None, {}),
        ("snow", "art", {"sheet": ("sheet1", 4), "x": 3420, "y": 800, "w": 170}, bd.BLUE, None, {"dmin": 0.5, "dmax": 0.8}),
        ("river", "strokes", {"strokes": lambda: pr.arrow([(2835, 1650), (2650, 1800), (2330, 1990), (1900, 2030), (1560, 1950), (1235, 1900)], seed=8, size=60), "width": 1.15}, bd.BLUE,
         ("river", -1.0, 1.2), {"dmin": 1.3}),
        ("loop", "strokes", {"strokes": lambda: pr.loop_arrows(2000, 1040, 590, 195, seed=9)}, bd.RED, ("all", -1.6, 1.8), {"dmin": 1.2}),
        ("cycle", "text", {"text": T["cycle"], "centre": (2000, 1040), "size": 160}, bd.INK, None, {}),
    ]


def pick_fills(kind, pkg):
    b = pkg["fill_boxes"]
    if not b:
        return []
    if kind == "sun":
        return [(0, bd.FILL_YELLOW)]
    if kind == "plant":
        low = max(range(len(b)), key=lambda i: b[i][3])
        return [(i, bd.FILL_BROWN if i == low else bd.FILL_GREEN) for i in sorted(range(len(b)), key=lambda i: (i != low, b[i][1]))]
    if kind == "mountain":
        top = min(range(len(b)), key=lambda i: b[i][1])
        return [(i, bd.FILL_BLUE if i == top else bd.FILL_GREY) for i in sorted(range(len(b)), key=lambda i: b[i][1])] if len(b) > 1 else []
    return []


_SHEETS = {}


def art(sheet, idx):
    if sheet not in _SHEETS:
        _SHEETS[sheet] = tr.cut_sheet(tr.load_ink(os.path.join(common.ART, sheet + ".png")), 3, 2)
    return _SHEETS[sheet][idx]


def build(lang, scale, strategy="human"):
    """-> (board, camera, duration, report). Deterministic: the same plan and word times give the same board on any machine."""
    narr = json.load(open(os.path.join(common.AUDIO, lang + ".json")))
    b = bd.Board(3840, 2160, scale)
    cam = bd.Camera(VIEWS["sun"])
    prev_end, report = 0.25, []
    for iid, kind, spec, colour, view, extra in plan(lang):
        word_t = word_time(narr, SAY[lang][iid])
        fills, after = None, []
        if kind == "art":
            pkg = vz.build_outline(art(*spec["sheet"]), strategy)
            k = spec["w"] / pkg["w"]
            r = vz.raster(pkg, k * scale, line_px=LINE * scale * (0.8 if spec["w"] < 250 else 1.0))
            x, y = spec["x"], spec["y"]
            fills = pick_fills(spec.get("fills"), pkg)
            pen_len = r["pen_len"] * k
        elif kind == "text":
            pkg = vz.text_pkg(spec["text"], common.FONT)
            k = spec["size"] / 200.0
            r = vz.raster_text(pkg, k * scale, line_px=spec["size"] * 0.105 * scale)
            x, y = spec["centre"][0] - pkg["w"] * k / 2, spec["centre"][1] - pkg["h"] * k / 2
            pen_len = r["pen_len"] * k * 0.8          # writing is quicker than drawing
            if spec.get("underline"):
                after.append((pr.underline(x + 30 * k, spec["centre"][1] + 96 * k, pkg["w"] * k - 60 * k, seed=len(spec["text"])), spec["underline"], 0.35))
        else:
            pkg = pr.package(spec["strokes"](), LINE * spec.get("width", 1.0), seed=len(iid))
            r = vz.raster(pkg, scale)
            x, y = pkg["x"], pkg["y"]
            pen_len = r["pen_len"]
        dmin, dmax = extra.get("dmin", 0.5), extra.get("dmax", 2.5)
        dur = float(np.clip(pen_len / PEN_SPEED, dmin, dmax))
        end = word_t + 0.15
        start, how = end - dur, "on the word"
        if start < prev_end + 0.15:                      # one pen: speed up to 1.6x, else finish late
            fast = max(dur / 1.6, dmin * 0.8)
            if end - fast >= prev_end + 0.15:
                start, how = prev_end + 0.15, "faster pen"
            else:
                start, end, how = prev_end + 0.15, prev_end + 0.15 + fast, "late"
        b.place(r, x, y, colour, start, end, fills=fills, fill_t0=end + 0.08, fill_dur=0.42)
        prev_end = end
        for strokes, col, d in after:
            q = pr.package(strokes, LINE * 0.9, seed=3)
            b.place(vz.raster(q, scale), q["x"], q["y"], col, prev_end + 0.12, prev_end + 0.12 + d)
            prev_end += 0.12 + d
        if view:
            cam.move(start + view[1], start + view[1] + view[2], VIEWS[view[0]])
        report.append({"id": iid, "word_at": round(word_t, 2), "start": round(start, 2), "end": round(end, 2), "late_by": round(end - (word_t + 0.15), 2), "how": how, "pen_units": int(pen_len)})
    b.finish()
    return b, cam, narr["duration"], report


def mix_audio(lang, music):
    """Narration, optionally over a quiet music bed from the existing library. One ffmpeg, niced."""
    wav = os.path.join(common.AUDIO, lang + ".wav")
    if not music or not os.path.exists(MUSIC):
        return wav
    out = os.path.join(common.AUDIO, lang + "_mix.wav")
    dur = json.load(open(os.path.join(common.AUDIO, lang + ".json")))["duration"]
    subprocess.run(["nice", "-n", "10", "ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-stream_loop", "-1", "-i", MUSIC, "-filter_complex",
                    f"[1:a]volume=0.10,afade=t=in:d=1.5,afade=t=out:st={dur - 2.5:.2f}:d=2.5[m];[0:a][m]amix=inputs=2:duration=first:normalize=0[a]", "-map", "[a]", "-t", f"{dur:.2f}", "-ar", "48000", out], check=True)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("lang")
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--from", dest="t0", type=float, default=0.0)
    ap.add_argument("--to", dest="t1", type=float, default=None)
    ap.add_argument("--out", default="")
    ap.add_argument("--no-tip", action="store_true")
    ap.add_argument("--still", type=float, default=None)
    ap.add_argument("--music", action="store_true")
    ap.add_argument("--strategy", default="human")
    a = ap.parse_args()
    ow, oh = map(int, a.size.split("x"))
    scale = 1.0 if ow <= 1920 else 1.6            # raster pixels per board unit: at least one per output pixel at the closest view (2400 units wide)
    t0 = time.time()
    b, cam, dur, report = build(a.lang, scale, a.strategy)
    build_s = time.time() - t0
    json.dump(report, open(os.path.join(common.WORK, f"timing_{a.lang}.json"), "w"), indent=1)
    late = [r for r in report if r["late_by"] > 0.05]
    print(f"board built in {build_s:.1f} s at scale {scale}; {len(report)} items; {len(late)} finish late: " + ", ".join(f"{r['id']} +{r['late_by']} s" for r in late))
    if a.still is not None:
        out = a.out or os.path.join(common.WORK, f"still_{a.lang}_{a.still:.1f}.jpg")
        b.frame(a.still, cam.at(a.still), (ow, oh), tip=not a.no_tip).save(out, quality=90)
        print(out)
        return 0
    t1 = a.t1 if a.t1 is not None else dur
    n0, n1 = int(round(a.t0 * FPS)), int(round(t1 * FPS))
    out = a.out or os.path.join(common.OUT, f"whiteboard_water_cycle_{a.lang}.mp4")
    audio = mix_audio(a.lang, a.music)
    if a.t0 > 0 or a.t1 is not None:               # a passage: cut the same piece of the audio
        cut = os.path.join(common.AUDIO, f"{a.lang}_cut.wav")
        subprocess.run(["nice", "-n", "10", "ffmpeg", "-y", "-loglevel", "error", "-ss", f"{a.t0:.3f}", "-t", f"{t1 - a.t0:.3f}", "-i", audio, cut], check=True)
        audio = cut
    t0 = time.time()
    bd.encode((b.frame(i / FPS, cam.at(i / FPS), (ow, oh), tip=not a.no_tip) for i in range(n0, n1)), out, FPS, (ow, oh), audio=audio, crf=18 if ow <= 1920 else 20)
    el = time.time() - t0
    print(f"{out}: {n1 - n0} frames in {el:.1f} s = {el / (n1 - n0) * 1000:.1f} ms per frame including x264; {os.path.getsize(out) / 1e6:.2f} MB")
    json.dump({"frames": n1 - n0, "seconds": round(el, 1), "ms_per_frame": round(el / (n1 - n0) * 1000, 1), "size": a.size, "board_build_s": round(build_s, 1), "mb": round(os.path.getsize(out) / 1e6, 2)},
              open(os.path.join(common.WORK, f"render_{a.lang}_{a.size}.json"), "w"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
