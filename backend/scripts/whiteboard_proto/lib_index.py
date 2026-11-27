#!/usr/bin/env python3
"""Search the whiteboard object library by meaning, the way the other catalogs do: Cohere Embed v4 through Bedrock (never Titan), 1024 d, float16 base64.

  AWS_PROFILE=qa lib_index.py build            # embed every package's description (EN + ES words) -> library_index.json next to this file
  AWS_PROFILE=qa lib_index.py test             # the test set below: hit@1, hit@3, and the scores of things that are NOT in the library (for MIN_SCORE)
  AWS_PROFILE=qa lib_index.py upload           # packages, thumbnails and the index -> s3://videomk-qa-catalog-<account>/w/   (QA only)
  AWS_PROFILE=qa lib_index.py find "a phrase"  # top 5

At video time a query costs one text embedding; the index (about 3 KB per object) ships with the code, the packages are read from the bucket.
"""
import base64
import json
import os
import struct
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.append(os.path.join(HERE, "..", "..", "lambdas"))
os.environ.setdefault("AWS_PROFILE", "qa")
os.environ.setdefault("AWS_REGION", "eu-west-1")
os.environ.setdefault("BEDROCK_REGION", "eu-west-1")

import wbcommon  # noqa: E402

LIB = os.path.expanduser(os.environ.get("WB_LIBRARY", os.path.join(wbcommon.OUT, "library")))
INDEX = os.path.join(HERE, "library_index.json")
PREFIX = "w/"
MIN_SCORE = 0.30        # below this a query is a MISS. Measured (lib_index.py test): correct top hits score 0.31 and up, absent things 0.16 to 0.37, so the two ranges overlap: the planner must be shown the top titles and choose, as with the vector catalog
EMBED_USD = 0.00002     # indicative per text embedding (Cohere Embed v4 on Bedrock), logged as an estimate

# query -> acceptable ids (any of them at rank 1 is a hit)
TESTS = {
    "the sun": ["sun", "sunrise"], "rain": ["rain_cloud", "storm_cloud", "water_drop"], "a plant growing": ["plant_sprout", "seedling_hands", "growth_plant", "seed"],
    "bacteria": ["bacteria"], "virus": ["virus"], "vaccine injection": ["syringe"], "immune system antibodies": ["antibody"], "doctor": ["doctor"],
    "saving money": ["piggy_bank", "coin_stack", "money_bag", "safe", "growth_plant"], "bank": ["bank"], "money growing over time": ["growth_plant", "line_chart", "coin_stack"],
    "an idea": ["light_bulb", "person_idea"], "goal": ["target", "mountain_flag", "flag", "trophy"], "teamwork": ["handshake_people", "handshake", "group_three", "puzzle_two"],
    "a happy person": ["face_happy", "person_cheering", "face_laughing"], "someone thinking": ["person_thinking", "face_thinking", "thought_bubble"],
    "computer": ["laptop", "desktop"], "the internet": ["globe_grid", "wifi", "network", "cloud_upload"], "artificial intelligence robot": ["robot", "chip", "brain"],
    "electricity": ["lightning", "plug", "battery", "circuit", "light_bulb"], "renewable energy": ["wind_turbine", "solar_panel"], "time is running out": ["hourglass", "sand_timer", "stopwatch", "alarm_clock"],
    "school": ["school", "teacher", "backpack"], "a family": ["family"], "transport by road": ["car", "truck", "bus", "road", "delivery_truck"], "planet Earth": ["earth_globe", "globe_grid", "planet"],
    "danger": ["warning", "stop_sign", "explosion"], "photosynthesis leaf": ["leaf", "plant_sprout"], "heart health": ["heart_organ", "heart", "heartbeat"], "DNA genetics": ["dna"],
    "el sol": ["sun", "sunrise"], "una vacuna": ["syringe"], "ahorrar dinero": ["piggy_bank", "coin_stack", "money_bag", "safe"], "una idea": ["light_bulb", "person_idea"],
    "el cerebro": ["brain"], "una casa": ["house", "house_price"], "un médico": ["doctor"], "energía eólica": ["wind_turbine", "windmill"], "el corazón": ["heart", "heart_organ"],
    "trabajo en equipo": ["handshake_people", "handshake", "group_three", "puzzle_two"], "un árbol": ["tree", "pine_tree", "forest"], "persona corriendo": ["person_running"],
}
NOT_IN_LIBRARY = ["a guitar", "the French Revolution", "a kangaroo", "inflation", "a sewing machine", "black hole", "a wedding", "una guitarra", "democracy", "a skateboard"]


def enc(v):
    return base64.b64encode(struct.pack(f"<{len(v)}e", *v)).decode("ascii")


def dec(b64):
    buf = base64.b64decode(b64)
    return list(struct.unpack(f"<{len(buf) // 2}e", buf))


def describe(p) -> str:
    m = p["meta"]
    return (f"{m.get('title_en')}. {m.get('description')} Also: {', '.join(m.get('synonyms_en') or [])}. Tags: {', '.join(m.get('tags') or [])}. "
            f"Español: {m.get('title_es')}, {', '.join(m.get('synonyms_es') or [])}.")[:1800]


def packages():
    for f in sorted(os.listdir(LIB)):
        if f.endswith(".json") and not f.startswith("_"):
            yield json.load(open(os.path.join(LIB, f)))


def build():
    from common import library_search

    items = []
    for p in packages():
        m = p["meta"]
        v = library_search._embed({"input_type": "search_document", "texts": [describe(p)]})
        items.append({"id": p["id"], "category": p["category"], "title": m.get("title_en"), "title_es": m.get("title_es"), "synonyms_en": m.get("synonyms_en"), "synonyms_es": m.get("synonyms_es"),
                      "tags": m.get("tags"), "aspect": round(p["w"] / p["h"], 3), "areas": sum(1 for c in p.get("fill_colours", []) if c != "none"), "strokes": len(p["strokes"]),
                      "draw_s": round(p["pen_length"] / 1150.0, 2), "v": enc(v)})
    json.dump({"model": library_search.EMBED_MODEL, "dim": library_search.EMBED_DIM, "built": time.strftime("%Y-%m-%d"), "prefix": PREFIX, "min_score": MIN_SCORE, "items": items},
              open(INDEX, "w"), separators=(",", ":"), ensure_ascii=False)
    wbcommon.charge(f"Cohere Embed v4 x{len(items)} (estimate)", EMBED_USD * len(items), item="library index")
    print(f"index: {len(items)} objects, {os.path.getsize(INDEX) // 1024} KB")


_IDX = None


def search(query: str, k: int = 5, min_score: float = MIN_SCORE, embed=None):
    """-> [{id, score, title}] best first; [] is a miss. Never raises."""
    global _IDX
    try:
        if _IDX is None:
            raw = json.load(open(INDEX, encoding="utf-8"))
            import numpy as np

            M = np.array([dec(it["v"]) for it in raw["items"]], np.float32)
            M /= np.linalg.norm(M, axis=1, keepdims=True) + 1e-9
            _IDX = (raw["items"], M)
        items, M = _IDX
        if embed is None:
            from common import library_search

            embed = library_search.embed_text
        import numpy as np

        q = np.asarray(embed(query.strip()), np.float32)
        q /= np.linalg.norm(q) + 1e-9
        sc = M @ q
        order = np.argsort(-sc)[:k]
        return [{"id": items[i]["id"], "score": round(float(sc[i]), 4), "title": items[i]["title"]} for i in order if sc[i] >= min_score]
    except Exception:  # noqa: BLE001
        return []


def test():
    h1 = h3 = 0
    low = 1.0
    for q, want in TESTS.items():
        r = search(q, 5, min_score=0.0)
        ids = [x["id"] for x in r]
        a, b = ids[0] in want, any(i in want for i in ids[:3])
        h1 += a
        h3 += b
        if a:
            low = min(low, r[0]["score"])
        print(f"{'ok ' if a else ('top3' if b else 'MISS')} {q!r}: " + ", ".join(f"{x['id']} {x['score']:.2f}" for x in r[:3]))
    neg = []
    for q in NOT_IN_LIBRARY:
        r = search(q, 1, min_score=0.0)
        neg.append(r[0]["score"])
        print(f"not in library {q!r}: nearest {r[0]['id']} {r[0]['score']:.2f}")
    wbcommon.charge(f"Cohere Embed v4 x{len(TESTS) + len(NOT_IN_LIBRARY)} queries (estimate)", EMBED_USD * (len(TESTS) + len(NOT_IN_LIBRARY)), item="library search test")
    print(f"hit@1 {h1}/{len(TESTS)}, hit@3 {h3}/{len(TESTS)}; lowest score of a correct top hit {low:.2f}; scores of absent things {min(neg):.2f} to {max(neg):.2f}")


def upload():
    import boto3

    sess = boto3.Session(profile_name="qa", region_name="eu-west-1")
    acct = sess.client("sts").get_caller_identity()["Account"]
    assert acct == "552357225438", "QA account only"
    bucket, s3, n, size = f"videomk-qa-catalog-{acct}", sess.client("s3"), 0, 0
    for f in sorted(os.listdir(LIB)):
        if f.startswith("_") or not f.endswith((".json", ".png")):
            continue
        s3.upload_file(os.path.join(LIB, f), bucket, PREFIX + f, ExtraArgs={"ContentType": "application/json" if f.endswith(".json") else "image/png"})
        n += 1
        size += os.path.getsize(os.path.join(LIB, f))
    s3.upload_file(INDEX, bucket, PREFIX + "index.json", ExtraArgs={"ContentType": "application/json"})
    print(f"uploaded {n} files ({size / 1e6:.1f} MB) and the index to s3://{bucket}/{PREFIX}")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "test"
    if cmd == "build":
        build()
    elif cmd == "test":
        test()
    elif cmd == "upload":
        upload()
    elif cmd == "find":
        print(search(sys.argv[2], 5, min_score=0.0))
