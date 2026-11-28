#!/usr/bin/env python3
"""Make sure every whiteboard drawing can be found by meaning (docs/WHITEBOARD_DRAWING_SEARCH_2026-11-28.md).

Every item of engine/assets/whiteboard/library_index.json carries a Cohere Embed v4 vector `v` (scripts/whiteboard_proto/lib_index.py build writes it when a drawing
is made; a drawing made on demand brings its own). This script covers the rest: an item WITHOUT `v` is embedded here from its title, synonyms and tags and stored in
engine/assets/whiteboard/library_embeddings.json ({"items": {id: {"h": text hash, "v": float16 base64}}}); retrieval reads both. Idempotent: an item whose text did not
change is not embedded again; an item that left the library is dropped from the file.

  AWS_PROFILE=qa BEDROCK_REGION=eu-west-1 whiteboard_embed.py check   # lists items with no vector at all (exit 1 if any)
  AWS_PROFILE=qa BEDROCK_REGION=eu-west-1 whiteboard_embed.py fill    # embeds the missing ones (about USD 0.00002 each)
"""
import base64
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lambdas"))
os.environ.setdefault("AWS_PROFILE", "qa")
os.environ.setdefault("AWS_REGION", "eu-west-1")
os.environ.setdefault("BEDROCK_REGION", "eu-west-1")

from engine.whiteboard import library, retrieval  # noqa: E402

PATH = os.path.normpath(retrieval.SIDECAR)


def load():
    try:
        return json.load(open(PATH, encoding="utf-8"))
    except (OSError, ValueError):
        return {"model": "", "items": {}}


def missing(items=None, side=None):
    """Ids with neither an inline vector nor a stored one."""
    items = library.index()["items"] if items is None else items
    have = {k for k, v in (load() if side is None else side)["items"].items() if v.get("v")}
    return [it["id"] for it in items if not it.get("v") and it["id"] not in have]


def fill(embed=None):
    from common import library_search

    embed = embed or (lambda t: library_search._embed({"input_type": "search_document", "texts": [t]}))
    items = library.index()["items"]
    data = load()
    keep, n = {}, 0
    for it in items:
        if it.get("v"):
            continue
        text = retrieval.item_text(it)
        h = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12]
        old = data["items"].get(it["id"])
        if old and old.get("h") == h and old.get("v"):
            keep[it["id"]] = old
            continue
        v = embed(text)
        keep[it["id"]] = {"h": h, "v": base64.b64encode(__import__("numpy").asarray(v, "<f2").tobytes()).decode("ascii")}
        n += 1
    data = {"model": library_search.EMBED_MODEL, "dim": library_search.EMBED_DIM, "items": keep}
    json.dump(data, open(PATH, "w", encoding="utf-8"), separators=(",", ":"), ensure_ascii=False)
    return n, len(keep)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "check":
        m = missing()
        print(f"{len(library.index()['items'])} items, {len(m)} without a vector: {m}")
        sys.exit(1 if m else 0)
    elif cmd == "fill":
        n, total = fill()
        print(f"embedded {n} new, {total} in {PATH}")
