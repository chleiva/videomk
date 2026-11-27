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


# batch 1 categories have no use_for / avoid_for in the plan: defaults (batch 2 carries its own per item). The cartoon look is for a peculiar kind of video, see docs/VECTOR_CATALOG.md "When to use".
DEFAULT_USE = {
    "nature": ("education, explainer, kids, wellness, travel", "news, current events, realistic documentary, disaster topics"),
    "city": ("explainer, business-light, education, travel", "news, current events, real places and addresses, crime and disaster topics"),
    "tech": ("tech, explainer, business-light, education", "news, security incidents, surveillance"),
    "science": ("education, explainer, kids, science", "news, conspiracy topics"),
    "education": ("education, explainer, kids, lifestyle", "news, serious topics"),
    "travel": ("travel, explainer, education, lifestyle", "news, accidents, disaster topics"),
    "seasons": ("wellness, lifestyle, kids, explainer, holidays", "news, serious topics"),
}


# solid structures that tore under the default merge (docs/VECTOR_CATALOG.md, tear check): (edge threshold, depth range cap), see vector_objects.py
STRONG_MERGE = {"space_station_earth": (0.30, 0.65), "satellite_dish_field": (0.24, 0.5)}


def audit_subjects(iid):
    """implied-motion subjects of a scene from vector_motion_audit.py (VC_AUDIT = its json), [] when none"""
    path = os.environ.get("VC_AUDIT")
    if not path or not os.path.exists(path):
        return []
    return (json.load(open(path)).get(iid) or {}).get("subjects", [])


def build_one(args):
    import vector_scene_build as vsb  # noqa: F401  (depth model path, helpers)
    import vector_sprites as vsp
    from PIL import Image

    item, src, store = args
    out = os.path.join(store, item["id"])
    if os.path.exists(os.path.join(out, "meta.json")) and not os.environ.get("VC_REBUILD"):
        return item["id"], "exists", 0
    if os.path.exists(out):
        shutil.rmtree(out)
    tall = item["orientation"] == "tall"
    nosky = item["id"] in NO_SKY

    def add_motion(man):
        # gentle sway on the two nearest ground layers of outdoor scenes (foliage); sprites and clouds keep their own tags
        base = [i for i, lay in enumerate(man["layers"]) if not lay.get("sprite") and lay["name"].startswith("layer")]
        if item["category"] in OUTDOOR and len(base) >= 2:
            man["layers"][base[-1]]["sway"] = {"amp": 0.0034, "period": 3.0, "phase": 2.0}
            man["layers"][base[-2]]["sway"] = {"amp": 0.0020, "period": 3.8, "phase": 0.8}
        man["catalog"] = item["id"]

    stats, sprites = vsp.build(src, out, CUTS, item["id"], audit_subjects(item["id"]), tall=tall, nosky=nosky, motion_cb=add_motion, merge=STRONG_MERGE.get(item["id"]))
    man = json.load(open(os.path.join(out, "manifest.json")))
    n = len(man["layers"])
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
                motion=sorted({t["type"] for l in man["layers"] if l.get("sprite") for t in l["tags"]} | ({"drift"} if any(l.get("drift") for l in man["layers"]) else set()) | ({"sway"} if any(l.get("sway") for l in man["layers"]) else set())),
                sprites=[dict(kind=l["kind"], tags=[t["type"] for t in l["tags"]]) for l in man["layers"] if l.get("sprite")],
                use_for=item.get("use_for") or DEFAULT_USE.get(item["category"], ("explainer, education", "news"))[0],
                avoid_for=item.get("avoid_for") or DEFAULT_USE.get(item["category"], ("explainer, education", "news"))[1],
                provenance=dict(model=MODEL, size=list(im.size), quality="medium", prompt_sha256_16=prompt_hash, run=os.environ.get("VC_RUN", "vector-catalog-1"), qa=qa, review_status="approved"))
    json.dump(meta, open(os.path.join(out, "meta.json"), "w"), indent=1)
    return item["id"], "built", svg_kb


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="folder with accepted/<id>.png")
    ap.add_argument("--store", required=True)
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--plan", default=PLAN)
    ap.add_argument("--run", default="vector-catalog-1", help="provenance run name of this batch")
    a = ap.parse_args()
    os.environ["VC_RUN"] = a.run
    plan = json.load(open(a.plan))
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
