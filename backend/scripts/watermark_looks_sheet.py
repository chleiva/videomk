#!/usr/bin/env python3
"""Contact sheets of the watermark as the FINAL STAGE draws it (docs/WATERMARK_DECOUPLED_2026-11-28.md): 6 looks x 4 aspects, local frames, no Lambda.

For each look and aspect the scene is rendered watermark-free (the same frames every account gets), stitched into a master, and passed through the real final stage (ffmpeg overlay, white or
ink by the measured brightness) with the test-account default (lockup, always, end card). Frames at 1.2 s go on a sheet (rows = looks, columns = aspects) plus crops of the mark at 100 %.

  .venv/bin/python backend/scripts/watermark_looks_sheet.py --out ~/Downloads/videomk-looks/web/watermark3 [--resolutions 720p 1080p 2160p] [--stock path.jpg]
"""
import argparse
import os
import sys
import tempfile

sys.path[:0] = [os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."), os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lambdas")]
os.environ.setdefault("WHITEBOARD_DIR", os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tests", "fixtures", "whiteboard"))

from PIL import Image, ImageDraw, ImageFont  # noqa: E402

from engine import final_stage, media, pipeline, watermark_spec as ws  # noqa: E402
from engine.frame import ASPECTS, Frame  # noqa: E402
from engine.renderer import Renderer  # noqa: E402
from engine.scenes import ELEMENTS  # noqa: E402

SPEC = {"mode": "videomk", "style": "lockup", "presence": "always", "end_card": True, "position": "auto", "size": "small", "opacity": ws.DEFAULT_OPACITY}
WORDS = [["This", 0.2, 0.5], ["is", 0.5, 0.7], ["a", 0.7, 0.9], ["caption", 0.9, 1.4], ["line", 1.4, 1.8], ["of", 1.8, 2.0], ["the", 2.0, 2.2], ["story", 2.2, 2.6]]
LIST = {"heading": "Lighthouse facts", "items": ["Warn of rocks and reefs", "Guide ships into harbors", "Fewer shine today"]}


def _bright(w=1600, h=1200):
    im = Image.new("RGB", (w, h))
    d = ImageDraw.Draw(im)
    for y in range(h):
        t = y / h
        d.line([(0, y), (w, y)], fill=(int(150 + 90 * t), int(205 + 40 * t), int(250 - 20 * t)))   # a bright sky into sand
    d.ellipse([w * 0.7, h * 0.12, w * 0.8, h * 0.12 + w * 0.1], fill=(255, 250, 220))
    d.rectangle([0, h * 0.72, w, h], fill=(238, 222, 180))
    return im


def _night(w=1600, h=1200):
    import random
    rnd = random.Random(7)
    im = Image.new("RGB", (w, h), (8, 10, 24))
    d = ImageDraw.Draw(im)
    for y in range(h):
        d.line([(0, y), (w, y)], fill=(10 + y // 40, 12 + y // 50, 30 + y // 25))
    for _ in range(70):
        x, bw = rnd.randint(0, w), rnd.randint(40, 120)
        top = rnd.randint(int(h * 0.3), int(h * 0.8))
        d.rectangle([x, top, x + bw, h], fill=(14, 16, 30))
        for wy in range(top + 10, h, 26):
            for wx in range(x + 8, x + bw - 8, 22):
                if rnd.random() < 0.35:
                    d.rectangle([wx, wy, wx + 8, wy + 12], fill=(255, 214, 120))
    return im


def looks(stock):
    wb = ELEMENTS["whiteboard"].sanitize(ELEMENTS["whiteboard"].samples[0])
    wb["cues"] = [0.1 + 0.1 * i for i in range(len(ELEMENTS["whiteboard"].anchors(wb)))]
    pres = ELEMENTS["presenter"].sanitize(ELEMENTS["presenter"].samples[0])
    stock_im = Image.open(stock).convert("RGB") if stock and os.path.exists(stock) else _bright().filter(__import__("PIL.ImageFilter", fromlist=["x"]).GaussianBlur(3))
    imgs = {"bright": _bright(), "night": _night(), "stock": stock_im}
    return [
        ("whiteboard on white", "whiteboard", wb, "paper", imgs),
        ("cartoon scene", "vector_scene", {"scene": "forest_path"}, "midnight", imgs),
        ("bright photo", "image", {"asset": "bright", "alt": "A bright beach"}, "midnight", imgs),
        ("stock photo", "image", {"asset": "stock", "alt": "A stock photo"}, "midnight", imgs),
        ("night city photo", "image", {"asset": "night", "alt": "A city at night"}, "midnight", imgs),
        ("presenter", "presenter", pres, "paper", imgs),
    ]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--resolutions", nargs="+", default=["720p", "1080p"])
    ap.add_argument("--stock")
    ap.add_argument("--aspects", nargs="+", default=list(ASPECTS))
    a = ap.parse_args()
    out = os.path.expanduser(a.out)
    os.makedirs(out, exist_ok=True)
    rows = looks(a.stock)
    for res in a.resolutions:
        cells, crops = {}, {}
        for name, scene, props, theme, imgs in rows:
            for aspect in a.aspects:
                fr = Frame.parse(aspect, res)
                dur = 2.4
                sc = {"id": "t", "type": scene, "start": 0.0, "duration": dur, "props": props, "words": WORDS, "transition": "none"}
                tl = {"scenes": [sc], "theme": theme, "captions": True, "duration": dur, "width": fr.width, "height": fr.height, "fps": 30, "outro": False,
                      "frame": {"aspect": aspect, "resolution": res}, "watermark": SPEC}
                loader = lambda k, imgs=imgs: imgs.get(k)  # noqa: E731
                with tempfile.TemporaryDirectory() as tmp:
                    seg, mst, fin = (os.path.join(tmp, n) for n in ("s.ts", "m.mp4", "f.mp4"))
                    pipeline.render_chunk(tl, 0, int(dur * 30), seg, loader, draft=False)
                    media.mux_final([seg], None, mst, fps=30)
                    final_stage.export(tl, mst, None, fin, image_loader=loader, tmp=tmp)
                    media.extract_frame(fin, 1.2, os.path.join(tmp, "f.png"))
                    img = Image.open(os.path.join(tmp, "f.png")).convert("RGB")
                cells[(name, aspect)] = img
                r = Renderer(tl, draft=False)
                sc_ = r.out_w / Frame.parse(aspect).W
                x0, y0, x1, y1 = [v * sc_ for v in ws.layout(SPEC, Frame.parse(aspect), None, True)["rect"]]
                m = 0.5 * (y1 - y0)
                crops[(name, aspect)] = img.crop((max(0, int(x0 - m)), max(0, int(y0 - m)), min(img.width, int(x1 + m)), min(img.height, int(y1 + m))))
                print(res, name, aspect, flush=True)
        _sheet(cells, [r_[0] for r_ in rows], a.aspects, os.path.join(out, f"sheet_{res}.jpg"), cell_h=420 if res != "2160p" else 420)
        _sheet(crops, [r_[0] for r_ in rows], a.aspects, os.path.join(out, f"crops_{res}.jpg"), cell_h=None)
    return 0


def _sheet(cells, names, aspects, path, cell_h):
    font = ImageFont.load_default()
    pad, lab = 8, 16
    if cell_h:
        sized = {k: v.resize((max(1, int(v.width * cell_h / v.height)), cell_h), Image.LANCZOS) for k, v in cells.items()}
    else:
        sized = cells
    colw = {asp: max(sized[(n, asp)].width for n in names) for asp in aspects}
    rowh = {n: max(sized[(n, asp)].height for asp in aspects) for n in names}
    W = sum(colw.values()) + pad * (len(aspects) + 1)
    H = sum(rowh.values()) + (pad + lab) * len(names) + pad
    sh = Image.new("RGB", (W, H), (60, 60, 64))
    d = ImageDraw.Draw(sh)
    y = pad
    for n in names:
        d.text((pad, y), n, fill=(255, 255, 255), font=font)
        y += lab
        x = pad
        for asp in aspects:
            sh.paste(sized[(n, asp)], (x, y))
            x += colw[asp] + pad
        y += rowh[n] + pad
    sh.save(path, quality=90)


if __name__ == "__main__":
    sys.exit(main())
