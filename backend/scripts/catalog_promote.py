#!/usr/bin/env python3
"""Copy the approved catalog images of one store to another WITHOUT paying twice (docs/IMAGE_CATALOG.md, "Promotion").

  catalog_promote.py --from qa --to prod                 # dry run (the default): says what would be copied
  catalog_promote.py --from qa --to prod --no-dry-run --yes-prod
  catalog_promote.py --from local:/path --to qa --no-dry-run

Copies objects (original, preview, thumbnail), the VECTOR (read from the source index: nothing is re-embedded) and the metadata row, which is written LAST and records
`promoted_from`. No model is called, so nothing is generated or embedded twice. Idempotent by content hash: an image already complete in the target is skipped. Every copy is verified by
checksum (the original must hash to its own id, in the source before and in the target after). Only items with review_status "approved" travel. Stores: qa, prod, local:<folder>.
Writing to prod needs --no-dry-run AND --yes-prod.
"""
import argparse
import datetime
import hashlib
import os
import sys
from typing import Any, Dict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))

from common import catalog  # noqa: E402


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def promote(src, dst, *, dry_run: bool = True, now: str = "") -> Dict[str, Any]:
    now = now or datetime.datetime.utcnow().isoformat() + "Z"
    rep: Dict[str, Any] = {"copied": [], "skipped": [], "refused": [], "dry_run": dry_run}
    for item in sorted(src.images(), key=lambda i: i.get("created", "")):
        cid = item["id"]
        if item.get("review_status") != "approved":
            rep["refused"].append({"id": cid, "why": f"review_status is {item.get('review_status')!r}"})
            continue
        keys = [catalog.key_original(cid), catalog.key_preview(cid), catalog.key_thumb(cid)]
        vec = src.get_vector(cid)
        if vec is None or any(not src.has(k) for k in keys):
            rep["refused"].append({"id": cid, "why": "the source is missing an object or the vector"})
            continue
        if _sha(src.get(keys[0])) != (item.get("stored_sha256") or cid):   # an image marked as ours (scripts/ownership_admin.py) keeps its id; its file's own hash is recorded on the row
            rep["refused"].append({"id": cid, "why": "the original does not match its content hash in the source"})
            continue
        have = dst.get_item(cid)
        if have and have.get("review_status") == "approved" and all(dst.has(k) for k in keys) and dst.get_vector(cid) is not None:
            rep["skipped"].append(cid)
            continue
        if dry_run:
            rep["copied"].append(cid)
            continue
        for k in keys:
            data = src.get(k)
            if not dst.has(k):
                dst.put(k, data)
            if _sha(dst.get(k)) != _sha(data):
                raise RuntimeError(f"checksum mismatch after copying {k}")
        if dst.get_vector(cid) is None:
            dst.put_vector(cid, vec[0], vec[1])
        row = dict(item)
        row["promoted_from"] = src.label
        row["promoted_at"] = now
        dst.put_item(row)   # last: an image with a row is a complete one
        rep["copied"].append(cid)
    return rep


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="src", required=True)
    ap.add_argument("--to", dest="dst", required=True)
    ap.add_argument("--dry-run", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--yes-prod", action="store_true", help="required to write to prod")
    a = ap.parse_args()
    if a.src == a.dst:
        sys.exit("--from and --to are the same store")
    if a.dst == "prod" and not a.dry_run and not a.yes_prod:
        sys.exit("Refusing to write to prod without --yes-prod.")
    if a.src == "prod":
        sys.exit("Refusing: images flow qa -> prod (or local -> qa), never out of prod.")
    from common.catalog_store import open_store

    rep = promote(open_store(a.src), open_store(a.dst), dry_run=a.dry_run)
    verb = "would copy" if a.dry_run else "copied"
    print(f"{verb} {len(rep['copied'])}, already there {len(rep['skipped'])}, refused {len(rep['refused'])}")
    for r in rep["refused"]:
        print("  refused", r["id"][:12], r["why"])
    if a.dry_run:
        print("Dry run: nothing was written. Add --no-dry-run (and --yes-prod for prod).")


if __name__ == "__main__":
    main()
