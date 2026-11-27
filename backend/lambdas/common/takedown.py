"""Takedown: take ONE asset out of VideoMK's own library at once (docs/LIBRARY_ON_DEMAND.md, part C). For the owner's command line (scripts/library_safety.py);
nothing in the product calls it.

    image(cat, cid, reason)        a library image (the catalog: common/catalog_store.py)
    clip(store, cid, reason)       a library clip (common/clip_store.py)
    sketch(store, cat, oid, reason) a whiteboard sketch object (its package in the catalog bucket; its index row when it was made on demand)

What "at once" means, in order, so that a failure half-way still leaves the asset out of service:
  1. THE ROW FIRST. The row every use reads is marked (`review_status` / `status` = taken_down): from that write on, no video is given the asset.
  2. Out of search: the image's vector leaves the index; a clip or drawing row that is not active is never loaded into search.
  3. The files are COPIED to a quarantine prefix (`quarantine/...` in the catalog bucket, `q/...` under cliplib/) and only then are the originals deleted. Nothing is
     destroyed: the quarantine copy is there to be looked at. The catalog bucket is versioned too (the original key keeps its earlier versions); the assets bucket
     that holds the clips is not (checked on QA, 2026-11-27), so for a clip the quarantine copy is the only one.
  4. A takedown record (who asked is not known here: when, why, what was moved) is written under `clipgen:takedown` when a ledger store is given.
`restore_*` undoes all of it from the quarantine copy. Every function returns the list of steps it did (or would do, with dry_run=True) and never half-reports:
an exception stops it after the row is already marked.
"""
import json
import time
from typing import Any, Dict, List, Optional

from common import catalog, clip_store as cs

TAKEN = "taken_down"
Q_CATALOG = "quarantine/"
Q_CLIPS = "q/"


def _record(store: Optional[cs.Store], media: str, aid: str, reason: str, steps: List[str], *, restored: bool = False) -> None:
    if store is None:
        return
    now = int(time.time())
    if restored:
        store.add(cs.TAKEDOWN, f"{media}:{aid}", fields={"restored_at": now, "state": "restored"})
    else:
        store.put(cs.TAKEDOWN, f"{media}:{aid}", {"media": media, "id": aid, "at": now, "reason": " ".join(str(reason).split())[:300], "steps": steps, "state": TAKEN})


def taken(store: Optional[cs.Store]) -> List[Dict[str, Any]]:
    """Every takedown on record, newest first."""
    return sorted((store.query(cs.TAKEDOWN) if store is not None else []), key=lambda r: -int(r.get("at") or 0))


def denied(store: Optional[cs.Store], media: str) -> List[str]:
    """Ids of `media` that are taken down and not restored (the sketch library reads this to drop a bundled drawing without a deploy)."""
    return [str(r["sk"]).split(":", 1)[1] for r in (store.query(cs.TAKEDOWN) if store is not None else []) if str(r["sk"]).startswith(media + ":") and r.get("state") == TAKEN]


# ----------------------------------------------------------------------------- images (the catalog)
def image(cat: Any, cid: str, reason: str, *, ledger: Optional[cs.Store] = None, dry_run: bool = True) -> List[str]:
    cid = catalog.check_id(cid)
    item = cat.get_item(cid)
    if not item:
        raise KeyError(f"no catalog image {cid}")
    keys = [k for k in (catalog.key_original(cid), catalog.key_preview(cid), catalog.key_thumb(cid)) if cat.has(k)]
    steps = [f"row {cid[:12]}: review_status {item.get('review_status')} -> {TAKEN}", "vector removed from the search index (kept in quarantine)"] + \
            [f"{k} -> {Q_CATALOG}{k}" for k in keys]
    if dry_run:
        return steps
    if item.get("review_status") != TAKEN:
        cat.put_item({**item, "review_status": TAKEN, "taken_down": {"at": int(time.time()), "reason": " ".join(str(reason).split())[:300], "was": item.get("review_status")}})   # 1: the row
    got = cat.get_vector(cid)
    if got:
        cat.put(f"{Q_CATALOG}vec/{cid}.json", json.dumps({"vector": [float(x) for x in got[0]], "metadata": got[1]}).encode(), "application/json")
        cat.delete_vector(cid)                                                                                                                                                # 2: search
    for k in keys:                                                                                                                                                           # 3: the files
        cat.put(Q_CATALOG + k, cat.get(k))
        cat.delete(k)
    _record(ledger, "image", cid, reason, steps)
    return steps


def restore_image(cat: Any, cid: str, *, ledger: Optional[cs.Store] = None, dry_run: bool = True) -> List[str]:
    cid = catalog.check_id(cid)
    item = cat.get_item(cid)
    if not item or item.get("review_status") != TAKEN:
        raise KeyError(f"catalog image {cid} is not taken down")
    keys = [k for k in (catalog.key_original(cid), catalog.key_preview(cid), catalog.key_thumb(cid)) if cat.has(Q_CATALOG + k)]
    was = str((item.get("taken_down") or {}).get("was") or "approved")
    steps = [f"{Q_CATALOG}{k} -> {k}" for k in keys] + ["vector back in the search index", f"row {cid[:12]}: review_status -> {was}"]
    if dry_run:
        return steps
    for k in keys:
        cat.put(k, cat.get(Q_CATALOG + k))
    vkey = f"{Q_CATALOG}vec/{cid}.json"
    if cat.has(vkey):
        v = json.loads(cat.get(vkey))
        cat.put_vector(cid, v["vector"], v.get("metadata") or {})
    cat.put_item({**{k: v for k, v in item.items() if k != "taken_down"}, "review_status": was})   # the row last: a usable row means the files and the vector are back
    _record(ledger, "image", cid, "", steps, restored=True)
    return steps


# ----------------------------------------------------------------------------- clips
def clip(store: cs.Store, cid: str, reason: str, *, dry_run: bool = True) -> List[str]:
    from engine import clip_library as lib

    if store.get(cs.LIB, cid) is None and not store.has_object(f"m/{cid}.json"):
        raise KeyError(f"no library clip {cid}")
    keys = [k for k in (f"v/{cid}.mp4", f"p/{cid}.jpg") if store.has_object(k)]
    steps = [f"row and metadata {cid[:12]}: status -> {TAKEN} (out of search)"] + [f"{k} -> {Q_CLIPS}{k}" for k in keys]
    if dry_run:
        return steps
    if store.has_object(f"m/{cid}.json"):
        lib.set_status(store, cid, TAKEN)                                                # 1 and 2: the row and the metadata document (a reindex keeps it out)
    else:
        store.add(cs.LIB, cid, fields={"status": TAKEN})
    for k in keys:                                                                       # 3: the files; a warm function that still holds the row cannot fetch the clip any more
        store.put_object(Q_CLIPS + k, store.get_object(k), "video/mp4" if k.endswith(".mp4") else "image/jpeg")
        store.delete_object(k)
    _record(store, "clip", cid, reason, steps)
    return steps


def restore_clip(store: cs.Store, cid: str, *, dry_run: bool = True) -> List[str]:
    from engine import clip_library as lib

    keys = [k for k in (f"v/{cid}.mp4", f"p/{cid}.jpg") if store.has_object(Q_CLIPS + k)]
    if not keys:
        raise KeyError(f"library clip {cid} is not in quarantine")
    steps = [f"{Q_CLIPS}{k} -> {k}" for k in keys] + [f"row and metadata {cid[:12]}: status -> active"]
    if dry_run:
        return steps
    for k in keys:
        store.put_object(k, store.get_object(Q_CLIPS + k), "video/mp4" if k.endswith(".mp4") else "image/jpeg")
    lib.set_status(store, cid, "active")
    _record(store, "clip", cid, "", steps, restored=True)
    return steps


# ----------------------------------------------------------------------------- whiteboard sketch objects
def _wkey(oid: str) -> str:
    import re

    if not re.fullmatch(r"[a-z0-9_]{2,48}", str(oid or "")):
        raise ValueError("bad object id")
    return "w/" + oid + ".json"   # plain concatenation on purpose (see common/catalog.py): these keys hold no user id


def sketch(store: Optional[cs.Store], cat: Any, oid: str, reason: str, *, dry_run: bool = True) -> List[str]:
    """`store`: the ledger store (the index rows of drawings made on demand, and the takedown record). `cat`: the catalog store that holds the packages.
    A drawing that ships with the code (assets/whiteboard/library_index.json) has no row: its package is quarantined (a new function instance can no longer load
    it and writes the label instead) and it is put on the takedown list, which the plan step reads when library media on demand is deployed. Removing it from
    the bundled index for good is a code change; the report says so."""
    key = _wkey(oid)
    row = store.get(cs.P + "wobj", oid) if store is not None else None
    there = cat.has(key)
    if row is None and not there:
        raise KeyError(f"no sketch object {oid}")
    steps = ([f"index row {oid}: status -> {TAKEN} (out of search)"] if row is not None else [f"{oid} on the takedown list (bundled drawing: also remove it from library_index.json at the next deploy)"]) + \
            ([f"{key} -> {Q_CATALOG}{key}"] if there else [])
    if dry_run:
        return steps
    if row is not None:
        store.add(cs.P + "wobj", oid, fields={"status": TAKEN})                          # 1 and 2
    _record(store, "object", oid, reason, steps)                                         # the takedown list is what takes a bundled drawing out of the plan step
    if there:                                                                            # 3
        cat.put(Q_CATALOG + key, cat.get(key), "application/json")
        cat.delete(key)
    return steps


def restore_sketch(store: Optional[cs.Store], cat: Any, oid: str, *, dry_run: bool = True) -> List[str]:
    key = _wkey(oid)
    if not cat.has(Q_CATALOG + key):
        raise KeyError(f"sketch object {oid} is not in quarantine")
    steps = [f"{Q_CATALOG}{key} -> {key}", f"{oid}: active again"]
    if dry_run:
        return steps
    cat.put(key, cat.get(Q_CATALOG + key), "application/json")
    if store is not None and store.get(cs.P + "wobj", oid) is not None:
        store.add(cs.P + "wobj", oid, fields={"status": "active"})
    _record(store, "object", oid, "", steps, restored=True)
    return steps
