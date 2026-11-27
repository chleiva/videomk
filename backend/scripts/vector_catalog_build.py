#!/usr/bin/env python3
"""Turn the accepted pictures of the cartoon vector scene catalog into scene packages (layers as SVG + manifest + metadata) in a LOCAL store.

  python backend/scripts/vector_catalog_build.py --src DIR_WITH_accepted --store DIR [--only id ...] [--workers 3]

Per scene: `vector_scene_build.build` (depth split, flat-colour regions, vtracer) with catalog defaults (4 depth cuts, gentle sway on the nearest layers of outdoor scenes, drifting clouds),
a 384 px thumbnail, and `meta.json` (id, title, category, mood, tags, topics, aspects, palette, layers, svg KB, provenance: model, prompt hash, QA scores, spend ledger).
Offline tool: needs vtracer, opencv-python-headless, scipy, onnxruntime and the depth ONNX model (see vector_scene_build.py). Store layout: STORE/<id>/{manifest.json,*.svg,thumb.jpg,meta.json}.
"""
import argparse
import hashlib
import json
import os
import shutil
import sys
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, HERE)

PLAN = os.path.join(ROOT, "docs", "vector_catalog", "plan.json")
MODEL = "gpt-image-2.6-flare"
CUTS = [0.35, 0.5, 0.65, 0.8]
OUTDOOR = {"nature", "seasons", "travel", "science"}
# scenes whose "sky" is not an ordinary blue sky at the top (space, a window in an interior): the sky/cloud detector would eat the Earth's blue or the window view, so it is switched off
NO_SKY = {"moon_base_surface", "library_interior_view"}


def motion_for(item, nlayers):
    """sway on the two nearest layers of outdoor scenes (foliage), a slow bob on water scenes; nothing for buildings and interiors"""
    mot = {}
    if item["category"] in OUTDOOR:
        mot[nlayers - 1] = {"sway": {"amp": 0.0034, "period": 3.0, "phase": 2.0}}
        mot[nlayers - 2] = {"sway": {"amp": 0.0020, "period": 3.8, "phase": 0.8}}
    return mot


def palette(path, k=5):
    import cv2
    import numpy as np
    from PIL import Image

    im = Image.open(path).convert("RGB")
    im.thumbnail((256, 256))
    Z = np.asarray(im).reshape(-1, 3).astype(np.float32)
    crit = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, lab, cen = cv2.kmeans(Z, k, None, crit, 2, cv2.KMEANS_PP_CENTERS)
    cnt = np.bincount(lab.ravel(), minlength=k)
    order = np.argsort(-cnt)
    return ["#%02x%02x%02x" % tuple(int(x) for x in cen[i]) for i in order]


def build_one(args):
    import vector_scene_build as vsb
    from PIL import Image

    item, src, store = args
    out = os.path.join(store, item["id"])
    if os.path.exists(os.path.join(out, "meta.json")):
        return item["id"], "exists", 0
    if os.path.exists(out):
        shutil.rmtree(out)
    tall = item["orientation"] == "tall"
    if tall:
        vsb.crop169 = lambda im: im     # keep the 2:3 picture whole: the scene is a 9:16-family scene
    nosky = item["id"] in NO_SKY
    if nosky:
        import numpy as np
        vsb.sky_mask = lambda rgb, comp: np.zeros(comp.shape, bool)
    stats = vsb.build(src, out, CUTS, item["id"], sun=False, clouds=not nosky, layer_motion=None)
    man = json.load(open(os.path.join(out, "manifest.json")))
    n = len(man["layers"])
    # motion by layer position (nearest layers sway): apply after the build, the layer list is known
    mot = motion_for(item, n)
    for i, lay in enumerate(man["layers"]):
        if i in mot:
            lay.update(mot[i])
    man["aspect"] = [2, 3] if tall else [16, 9]
    man["catalog"] = item["id"]
    json.dump(man, open(os.path.join(out, "manifest.json"), "w"), indent=1)
    im = Image.open(src).convert("RGB")
    t = im.copy()
    t.thumbnail((384, 384))
    t.save(os.path.join(out, "thumb.jpg"), "JPEG", quality=85)
    qa = {}
    qp = src[:-4] + ".qa.json"
    if os.path.exists(qp):
        qa = json.load(open(qp))
    svg_kb = sum(os.path.getsize(os.path.join(out, f)) for f in os.listdir(out) if f.endswith(".svg")) // 1024
    prompt_hash = hashlib.sha256((item["desc"]).encode()).hexdigest()[:16]
    meta = dict(id=item["id"], title=item["title"], category=item["category"], mood=item["mood"], tags=item["tags"].split(","), topics=item["topics"], description=item["desc"],
                aspects=["9:16"] if tall else ["16:9"], orientation=item["orientation"], palette=palette(src), layers=n, svg_kb=svg_kb, paths=sum(s[2] for s in stats),
                provenance=dict(model=MODEL, size=list(im.size), quality="medium", prompt_sha256_16=prompt_hash, run="vector-catalog-1", qa=qa, review_status="approved"))
    json.dump(meta, open(os.path.join(out, "meta.json"), "w"), indent=1)
    return item["id"], "built", svg_kb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="folder with accepted/<id>.png")
    ap.add_argument("--store", required=True)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--workers", type=int, default=3)
    a = ap.parse_args()
    plan = json.load(open(PLAN))
    jobs = []
    for it in plan["items"]:
        p = os.path.join(a.src, "accepted", it["id"] + ".png")
        if os.path.exists(p) and (not a.only or it["id"] in a.only):
            jobs.append((it, p, a.store))
    os.makedirs(a.store, exist_ok=True)
    with ProcessPoolExecutor(max_workers=a.workers) as ex:
        for iid, st, kb in ex.map(build_one, jobs):
            print(f"{iid}: {st} {kb} KB", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
