#!/usr/bin/env python3
"""Mark VideoMK's own catalog images as the company's property (docs/LIBRARY_ON_DEMAND.md, "Ownership marking"). A store is `qa`, `prod` or `local:<folder>`.

  python backend/scripts/ownership_admin.py status --store qa                     how many images carry the metadata and the invisible watermark
  python backend/scripts/ownership_admin.py mark   --store qa [--watermark] [--no-dry-run] [--limit N] [--yes-prod]
        layer (a): embedded EXIF/XMP ownership metadata on every approved image (pixels untouched), verified after writing.
        --watermark: layer (c), Adobe TrustMark (MIT) carrying the first 60 bits of the asset id, embedded BEFORE the metadata. Needs `pip install trustmark`
        (PyTorch; it cannot run inside the engine's functions, so on-demand images are stored with `watermark: pending` and this command finishes them).
  python backend/scripts/ownership_admin.py read FILE.jpg|FRAME.png               what a file says: metadata, and the watermark id if one can be read (also from a video frame)

An image keeps its id (the hash of the picture as the provider made it). The rewritten file's own hash goes on the row (`stored_sha256`), which promotion checks.
Dry run by default. The catalog bucket is versioned, so the earlier file of every image stays recoverable.
"""
import argparse
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))

from common import catalog, catalog_store, ownership   # noqa: E402

WM_NAME = "trustmark-Q-bch5"
WM_BITS = 60


def wm_bits(asset_id: str) -> str:
    return bin(int(asset_id[:15], 16))[2:].zfill(WM_BITS) + "0"   # 61 payload bits: 60 of the id and a spare


def _trustmark():
    from trustmark import TrustMark
    return TrustMark(verbose=False, model_type="Q", encoding_type=TrustMark.Encoding.BCH_5)


def watermark_jpeg(tm, jpeg: bytes, asset_id: str) -> bytes:
    from PIL import Image
    out = io.BytesIO()
    tm.encode(Image.open(io.BytesIO(jpeg)).convert("RGB"), wm_bits(asset_id), MODE="binary").convert("RGB").save(out, "JPEG", quality=95, subsampling=0)
    return out.getvalue()


def read_watermark(tm, image_bytes: bytes):
    """-> the 15 hex characters of an asset id, or None."""
    from PIL import Image
    bits, present, _ = tm.decode(Image.open(io.BytesIO(image_bytes)).convert("RGB"), MODE="binary")
    return f"{int(bits[:WM_BITS], 2):015x}" if present and bits else None


def mark_store(store, *, watermark: bool = False, dry_run: bool = True, limit: int = 0, tm=None) -> dict:
    rep = {"marked": [], "already": [], "refused": [], "watermarked": 0}
    if watermark and tm is None:
        tm = _trustmark()
    for item in store.images():
        cid = item["id"]
        if item.get("review_status") != "approved":
            continue
        need_wm = watermark and item.get("watermark") != WM_NAME
        data = store.get(catalog.key_original(cid))
        if ownership.is_marked(data, cid) and not need_wm:
            rep["already"].append(cid)
            continue
        if catalog.content_hash(data) not in (cid, item.get("stored_sha256")):
            rep["refused"].append({"id": cid, "why": "the stored file matches neither its id nor its recorded hash"})
            continue
        if limit and len(rep["marked"]) >= limit:
            break
        if not dry_run:
            if need_wm:
                data = watermark_jpeg(tm, data, cid)
                if read_watermark(tm, data) != cid[:15]:
                    rep["refused"].append({"id": cid, "why": "the watermark did not read back"})
                    continue
                rep["watermarked"] += 1
            out = ownership.mark_jpeg(data, asset_id=cid, title=str(item.get("title") or ""))
            if not ownership.is_marked(out, cid):
                rep["refused"].append({"id": cid, "why": "the metadata did not verify"})
                continue
            store.put(catalog.key_original(cid), out)
            store.put_item({**item, "marked": True, "stored_sha256": catalog.content_hash(out), "owner_name": ownership.OWNER, "scope": item.get("scope") or "library",
                            "watermark": WM_NAME if (need_wm or item.get("watermark") == WM_NAME) else (item.get("watermark") or "none")})
        rep["marked"].append(cid)
    return rep


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("status", "mark"):
        s = sub.add_parser(name)
        s.add_argument("--store", required=True)
        if name == "mark":
            s.add_argument("--watermark", action="store_true")
            s.add_argument("--no-dry-run", dest="dry_run", action="store_false")
            s.add_argument("--limit", type=int, default=0)
            s.add_argument("--yes-prod", action="store_true")
    r = sub.add_parser("read")
    r.add_argument("file")
    a = ap.parse_args()
    if a.cmd == "read":
        data = open(a.file, "rb").read()
        print("metadata:", ownership.read_marks(data) or "none")
        try:
            print("watermark id:", read_watermark(_trustmark(), data) or "none readable")
        except ImportError:
            print("watermark: trustmark is not installed here")
        return
    store = catalog_store.open_store(a.store)
    if a.cmd == "status":
        items = [i for i in store.images() if i.get("review_status") == "approved"]
        print(f"{store.label}: {len(items)} approved images; metadata on {sum(1 for i in items if i.get('marked'))}; watermark on {sum(1 for i in items if i.get('watermark') == WM_NAME)}; "
              f"watermark pending on {sum(1 for i in items if i.get('watermark') == 'pending')}")
        return
    if a.store == "prod" and not a.dry_run and not a.yes_prod:
        sys.exit("marking prod needs --yes-prod")
    rep = mark_store(store, watermark=a.watermark, dry_run=a.dry_run, limit=a.limit)
    print(f"{'would mark' if a.dry_run else 'marked'} {len(rep['marked'])}; already marked {len(rep['already'])}; watermarked {rep['watermarked']}; refused {len(rep['refused'])}")
    for r_ in rep["refused"]:
        print("  refused", r_["id"][:12], r_["why"])


if __name__ == "__main__":
    main()
