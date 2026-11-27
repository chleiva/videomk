"""Arms of the presenter characters: the instrument's numbers over the whole matrix, and the pictures to look at (docs/PRESENTERS.md "Arms").

  python scripts/presenter_arms.py --measure [--only fox bear] [--json out.json]      counts per character and per gesture (engine/arm_check.py)
  python scripts/presenter_arms.py --sheet OUT.jpg --who fox --kind open [--hand both] [--skeleton]    every frame of one gesture as a contact sheet
  python scripts/presenter_arms.py --rest OUT.jpg / --gestures OUT.jpg                all ten characters in each rest pose / at each gesture's stroke
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))

from engine import arm_check as ac                # noqa: E402
from engine import character_gestures as cg       # noqa: E402
from engine import vector_presenter as vp         # noqa: E402

CAST = ("ines", "david", "priya", "mateo", "fox", "owl", "bear", "cat", "parrot", "turtle")
TAILS = {"fox", "owl", "cat", "parrot", "turtle"}
KINDS = tuple(k for k in cg.KINDS)


def maker(cid):
    def make(seed, content_side, lift):
        try:
            return cg.Performance(seed=seed, content_side=content_side, tail=cid in TAILS, lift=lift, who=cid)
        except TypeError:                          # the rig before per-character rest poses
            return cg.Performance(seed=seed, content_side=content_side, tail=cid in TAILS, lift=lift)
    return make


def measure(cids, overlap, verbose=False):
    table, by_kind, worst = {}, {}, []
    for cid in cids:
        ch = vp.load(cid, ac.GEOM_PPU)
        g = ch.g
        tot = {}
        for group, name, perf, t0, t1 in ac.scenarios(KINDS, maker(cid), overlap=overlap):
            def pose_at(t, perf=perf):
                pose, _ = perf.pose(t, g)
                return vp.solve(g, pose), pose
            fr = ac.track(pose_at, t0, t1)
            res = ac.check(fr, g, active=lambda t, perf=perf: any(x.t0 - 0.1 <= t <= x.t1 + 0.6 for x in perf.gestures) or any(abs(t - b[0]) < 0.7 for b in perf.beats) or (hasattr(perf, 'folded') and 0.001 < perf.folded(t, 0) < 0.999) or (hasattr(perf, 'folded') and 0.001 < perf.folded(t, 1) < 0.999), head_w=ch.hw)
            ac.add(tot, res)
            key = group if ">" not in group else "pairs"
            ac.add(by_kind.setdefault(key, {}), res)
            bad = sum(res[k] for k in ac.CLASSES)
            if bad:
                worst.append((bad, cid, name, {k: v[:6] for k, v in res["detail"].items() if v}, res["peak"]))
            if verbose and bad:
                print(cid, name, {k: res[k] for k in ac.CLASSES if res[k]}, res["peak"])
        table[cid] = tot
    return table, by_kind, sorted(worst, key=lambda w: -w[0])


def show(table, title):
    cols = ac.CLASSES
    print(f"\n{title}")
    print(f"{'':10s}{'frames':>8s}" + "".join(f"{c:>15s}" for c in cols) + "   detail / peaks")
    for k, t in table.items():
        det = " ".join(f"{a}={b}" for a, b in t["detail"].items() if b)
        pk = t["peak"]
        print(f"{k:10s}{t['frames']:8d}" + "".join(f"{t[c]:15d}" for c in cols) + f"   {det} | speed {pk.get('speed')} accel {pk.get('accel')} drop {pk.get('drop')} bend {pk.get('bend_min')}..{pk.get('bend_max')} upper {pk.get('upper_min')}..{pk.get('upper_max')}")


def cell(ch, pose, w, h, ppu, skeleton=False, label=None, bg=(238, 240, 245), cut=78.0):
    """One character in a pose on a plain cell, from the hips up (`cut` units of the legs below the edge)."""
    from PIL import Image, ImageDraw
    im = Image.new("RGBA", (w, h), bg + (255,))
    x, ground = w / 2, h + cut * ppu
    sk = ch.draw(im, x, ground, pose)
    d = ImageDraw.Draw(im)
    if skeleton:
        def px(v):
            return (x + v[0] * ppu, ground - v[1] * ppu)
        for i in (0, 1):
            pts = [px(sk["shoulders"][i]), px(sk["elbows"][i]), px(sk["wrists"][i])]
            d.line(pts, fill=(255, 0, 200, 255), width=3)
            for q in pts:
                d.ellipse((q[0] - 4, q[1] - 4, q[0] + 4, q[1] + 4), fill=(0, 220, 255, 255), outline=(0, 0, 0, 255))
    if label:
        d.rectangle((0, 0, 8 + 7 * len(label), 16), fill=(20, 20, 30, 255))
        d.text((4, 2), label, fill=(255, 235, 90, 255))
    return im.convert("RGB")


def tile(cells, cols, out):
    from PIL import Image
    w, h = cells[0].size
    rows = (len(cells) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * w, rows * h), (255, 255, 255))
    for k, c in enumerate(cells):
        sheet.paste(c, ((k % cols) * w, (k // cols) * h))
    sheet.save(out, quality=88)
    print("wrote", out, sheet.size)


def sheet(out, cid, kinds, hand, t0, t1, every, skeleton, cols, ppu=1.25, w=300, h=330, listen=False, cs=1):
    """Every `every`-th frame of a performance: the gestures `kinds` one after the other (or a listener), with frame numbers."""
    ch = vp.load(cid, ppu)
    perf = maker(cid)(0.37, cs, 0.14)
    if listen:
        perf.limit = t1
        perf.listen(0.1, t1 - 0.4, 1.0, [1.5, 4.0])
    else:
        t = 1.3
        for k in kinds:
            perf.gesture(k, t, 1.0, None if hand == "auto" else hand, cs if k == "present" else 0)
            t = perf.gestures[-1].t1 + 0.5
        t1 = t1 or t + 0.6
    cells = []
    n0, n1 = int(t0 * 30), int(t1 * 30)
    for k in range(n0, n1, every):
        pose, _ = perf.pose(k / 30.0, ch.g)
        cells.append(cell(ch, pose, w, h, ppu, skeleton, f"{k}"))
    tile(cells, cols, out)


def rest_sheet(out, ppu=1.05, w=250, h=285):
    """All ten characters (columns) in each rest pose (rows): the four relaxed poses, two asymmetric mixes as they occur, and hands together."""
    rows = [("home", (0, 0)), ("bent", (1, 1)), ("straighter", (2, 2)), ("mixed a", (0, 1)), ("mixed b", (3, 2)), ("hands together (listening)", None)]
    cells = []
    for name, pair in rows:
        for cid in CAST:
            ch = vp.load(cid, ppu)
            if pair is None:
                perf = maker(cid)(0.2, 1, 0.14)
                ku = [perf._key_fold(ch.g, i) for i in (0, 1)]
                on = cid in cg.FOLDERS
                arms = tuple((ku[i][0], ku[i][1]) for i in (0, 1)) if on else tuple(cg.REST_POSES[0][:2] for _ in (0, 1))
                wr = (cg.FOLD_FLEX, cg.FOLD_FLEX) if on else (cg.REST_WRIST, cg.REST_WRIST)
                lab = f"{cid}: {name}" if on else f"{cid}: keeps hands at sides"
            else:
                arms = tuple(cg.REST_POSES[j][:2] for j in pair)
                wr = tuple(cg.REST_POSES[j][2] for j in pair)
                lab = f"{cid}: {name}"
            cells.append(cell(ch, {"arms": arms, "wrist": wr}, w, h, ppu, False, lab))
    tile(cells, len(CAST), out)


def gesture_sheet(out, ppu=1.05, w=250, h=300, room=None):
    """All ten characters (columns) on the stroke of each gesture (rows)."""
    cells = []
    for kind in [k for k in KINDS if k != "beat"]:
        for cid in CAST:
            ch = vp.load(cid, ppu)
            perf = maker(cid)(0.37, 1, 0.14)
            if room is not None:
                perf.room = perf.clear = (room, room)
            perf.gesture(kind, 1.3, 1.2, None, 1 if kind == "present" else 0)
            g = perf.gestures[-1]
            t = g.stroke + (0.9 if kind in ("compare", "count") else 0.35)
            pose, _ = perf.pose(t, ch.g)
            cells.append(cell(ch, pose, w, h, ppu, False, f"{cid}: {kind}", cut=70.0))
    tile(cells, len(CAST), out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--overlap", action="store_true", help="also pairs in which the second gesture cuts into the first one's hold")
    ap.add_argument("--json")
    ap.add_argument("-v", action="store_true")
    ap.add_argument("--scenes", action="store_true", help="conversations and single presenters through the element: cuts, the card, the other figures")
    ap.add_argument("--sheet")
    ap.add_argument("--who", default="fox")
    ap.add_argument("--kind", nargs="*", default=["open"])
    ap.add_argument("--hand", default="auto")
    ap.add_argument("--t0", type=float, default=0.5)
    ap.add_argument("--t1", type=float, default=0.0)
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--cols", type=int, default=10)
    ap.add_argument("--skeleton", action="store_true")
    ap.add_argument("--listen", action="store_true")
    ap.add_argument("--ppu", type=float, default=1.25)
    ap.add_argument("--rest")
    ap.add_argument("--gestures")
    ap.add_argument("--room", type=float)
    a = ap.parse_args()
    if a.scenes:
        tot = {}
        for cast in (["fox", "bear"], ["bear", "fox"], ["owl"], ["ines"], ["cat", "parrot", "turtle"], ["david", "priya"], ["mateo", "ines", "priya"]):
            for aspect in ("16:9", "9:16", "1:1", "4:5"):
                from engine.scenes.elements import presenter as el
                el.release()
                rows = ac.scene_tracks(ac.conversation(cast), aspect)
                for cid, rec in rows.items():
                    r = rec["result"]
                    ac.add(tot.setdefault(aspect, {}), r)
                    if a.v or sum(r[k] for k in ac.CLASSES):
                        print(f"  {'+'.join(cast):22s} {aspect:5s} {cid:7s}", {k: r[k] for k in ac.CLASSES if r[k]}, {k: len(v) for k, v in r["detail"].items() if v}, "cut jump", r["peak"]["cut_jump"], "rest", r["peak"]["rest_move"])
        show(tot, "whole scenes through the element (7 casts), per frame shape")
    if a.sheet:
        sheet(a.sheet, a.who, a.kind, a.hand, a.t0, a.t1, a.every, a.skeleton, a.cols, ppu=a.ppu, w=int(240 * a.ppu), h=int(264 * a.ppu), listen=a.listen)
    if a.rest:
        rest_sheet(a.rest)
    if a.gestures:
        gesture_sheet(a.gestures, room=a.room)
    if a.measure:
        table, by_kind, worst = measure(a.only or CAST, a.overlap, a.v)
        show(table, "per character")
        show(dict(sorted(by_kind.items())), "per gesture (all characters)")
        print("\nworst cases")
        for w in worst[:12]:
            print(" ", w[0], w[1], w[2], w[3])
        if a.json:
            json.dump({"characters": table, "kinds": by_kind}, open(a.json, "w"), indent=1)


if __name__ == "__main__":
    main()
