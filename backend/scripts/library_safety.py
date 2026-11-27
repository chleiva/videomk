#!/usr/bin/env python3
"""The safety policy of VideoMK's own library on the command line (docs/LIBRARY_ON_DEMAND.md, part C; the policy itself is lambdas/common/media_policy.py).
A store is `qa`, `prod` or `local:<folder>` (for images the folder is a catalog folder, for clips and the takedown ledger a clip-library folder).

  python backend/scripts/library_safety.py policy
        print the policy as the models read it, and its version

  python backend/scripts/library_safety.py audit --store qa [--media images,objects,clips] [--vision none|small|large] [--no-moderation] [--limit N] [--json report.json]
        READ ONLY. Runs the policy over what the library already holds: the word lists on every title, subject and name (free), the policy's vision check on
        every picture (a paid model call each: --vision small is about $0.0002 an asset, large about $0.005; none skips it) and the provider's own moderation
        model on images (free). Prints a report of everything that is not clearly fine. It never changes, moves or deletes anything.

  python backend/scripts/library_safety.py takedown image|clip|object <id> --store local:<dir> --reason "why" [--catalog local:<dir>] [--no-dry-run] [--yes-prod]
        take ONE asset out of the library at once: its row stops being served, it leaves search, its files move to a quarantine prefix (nothing is destroyed:
        they are copied there before the originals are deleted). Dry run by default: it prints what it would do. `--catalog` is the catalog store when it is not the same spec as --store.
  python backend/scripts/library_safety.py restore image|clip|object <id> --store ... [--no-dry-run]
        undo a takedown from the quarantine copy
  python backend/scripts/library_safety.py taken --store ...
        the takedowns on record
"""
import argparse
import io
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))

from common import catalog, catalog_store, clip_store as cs, media_policy as mp, takedown   # noqa: E402

WB_INDEX = os.path.join(HERE, "..", "lambdas", "engine", "assets", "whiteboard", "library_index.json")


# ----------------------------------------------------------------------------- the audit (read only)
def judge(asset: Dict[str, Any], *, vision: Optional[Callable[..., Any]], moderate: Optional[Callable[..., Optional[str]]]) -> Dict[str, Any]:
    """One asset -> its line of the report. `asset`: {media, id, title, texts: [...], notes: [...], picture: bytes or None, mime}. Verdict:
    'remove' = a check of the picture itself named a policy category, or the provider's moderation refused it; 'review' = only words matched, or a check was unsure
    or could not run; 'ok' = every check that ran is clean."""
    row: Dict[str, Any] = {"media": asset["media"], "id": asset["id"], "title": asset.get("title") or "", "status": asset.get("status") or "", "why": [], "cost_usd": 0.0}
    words = mp.text_hits(*asset.get("texts", []))
    row["words"] = [f"{c}:{w}" for c, w in words]
    soft = [f"{c}:{w}" for c, w in mp.text_hits(*asset.get("notes", [])) if (c, w) not in words]
    pic = asset.get("picture")
    hard = False
    if vision is not None:
        if not pic:
            row["vision"] = "no picture"
            row["why"].append("no picture to check")
        else:
            ok, why, verdict, cost = vision([pic], asset.get("title") or "")
            row.update({"vision": "none" if ok else why, "answered": str(verdict.get("policy") or "")[:40], "seen": str(verdict.get("seen") or "")[:80], "vision_reason": str(verdict.get("reason") or "")[:120], "cost_usd": cost})
            if not ok:
                named = why.split(":", 1)[-1] in mp.CODES
                hard = hard or named
                row["why"].append(f"picture: {why}" + (f" ({row['vision_reason']})" if row["vision_reason"] else ""))
    if moderate is not None and pic and asset["media"] != "object":
        m = moderate(image=pic, mime=asset.get("mime") or "image/jpeg")
        row["moderation"] = m or "clean"
        if m and m != "moderation:unavailable":
            hard = True
            row["why"].append(m)
        elif m:
            row["why"].append("provider moderation could not run")
    if words:
        row["why"].append("words: " + ", ".join(row["words"]))
    if soft:
        row["notes"] = soft
    row["verdict"] = "remove" if hard else "review" if row["why"] else "ok"
    return row


def image_assets(cat: catalog_store.Store, limit: int = 0) -> List[Dict[str, Any]]:
    out = []
    for it in sorted(cat.images(), key=lambda i: str(i.get("id"))):
        cid = str(it["id"])

        def pic(cid=cid):
            for key in (catalog.key_preview(cid), catalog.key_original(cid)):
                try:
                    return _fit(cat.get(key), 1024)
                except Exception:   # noqa: BLE001
                    continue
            return None
        out.append({"media": "image", "id": cid, "title": str(it.get("title") or it.get("subject") or ""), "status": str(it.get("review_status") or ""),
                    "texts": [it.get("title"), it.get("subject"), it.get("category")], "notes": [" ".join(str(t) for t in it.get("tags") or [])], "load": pic, "mime": "image/jpeg"})
    return out[:limit] if limit else out


def clip_assets(store: cs.Store, limit: int = 0) -> List[Dict[str, Any]]:
    out = []
    for r in sorted(store.query(cs.LIB), key=lambda r: str(r.get("sk"))):
        cid = str(r["sk"])

        def pic(cid=cid):
            try:
                return store.get_object(f"p/{cid}.jpg")
            except Exception:   # noqa: BLE001
                return None
        out.append({"media": "clip", "id": cid, "title": str(r.get("brief") or ""), "status": str(r.get("status") or "active"), "texts": [r.get("brief"), " ".join(str(t) for t in r.get("tags") or [])],
                    "notes": [], "load": pic, "mime": "image/jpeg"})
    return out[:limit] if limit else out


def object_assets(cat: Optional[catalog_store.Store], store: Optional[cs.Store], limit: int = 0, index_path: str = WB_INDEX) -> List[Dict[str, Any]]:
    """The drawings that ship with the code (the bundled index) and those made on demand (rows in the ledger store). The picture is drawn from the package in the
    catalog bucket with the builder's own thumbnail code; where that code or the package is missing the drawing is listed with 'no picture'."""
    items: List[Dict[str, Any]] = []
    try:
        with open(index_path, encoding="utf-8") as f:
            items += [{**it, "_origin": "bundled"} for it in json.load(f)["items"]]
    except (OSError, ValueError, KeyError):
        pass
    have = {it["id"] for it in items}
    for r in (store.query(cs.P + "wobj") if store is not None else []):
        if str(r["sk"]) not in have:
            items.append({"id": str(r["sk"]), "title": r.get("title"), "title_es": r.get("title_es"), "synonyms_en": r.get("synonyms_en"), "synonyms_es": r.get("synonyms_es"),
                          "tags": r.get("tags"), "_origin": "on-demand", "_status": r.get("status")})
    thumb = _thumbnailer()
    out = []
    for it in sorted(items, key=lambda i: i["id"]):
        oid = str(it["id"])

        def pic(oid=oid):
            if cat is None or thumb is None:
                return None
            try:
                return thumb(json.loads(cat.get(f"w/{oid}.json")))
            except Exception:   # noqa: BLE001
                return None
        out.append({"media": "object", "id": oid, "title": str(it.get("title") or oid), "status": str(it.get("_status") or it["_origin"]),
                    "texts": [oid.replace("_", " "), it.get("title"), it.get("title_es")],
                    "notes": [" ".join(str(x) for x in (it.get("synonyms_en") or []) + (it.get("synonyms_es") or []) + (it.get("tags") or []))], "load": pic, "mime": "image/jpeg"})
    return out[:limit] if limit else out


def _thumbnailer() -> Optional[Callable[[Dict[str, Any]], bytes]]:
    try:
        from common import object_maker

        mods = object_maker.load()
        if mods is None:
            return None
        lib_build = mods[1]

        def thumb(pkg: Dict[str, Any]) -> bytes:
            b = io.BytesIO()
            lib_build.thumb(pkg, 320).convert("RGB").save(b, "JPEG", quality=88)
            return b.getvalue()
        return thumb
    except Exception:   # noqa: BLE001
        return None


def _fit(jpeg: bytes, px: int) -> bytes:
    from PIL import Image

    im = Image.open(io.BytesIO(jpeg)).convert("RGB")
    s = px / max(im.size)
    if s < 1:
        im = im.resize((max(1, int(im.width * s)), max(1, int(im.height * s))), Image.LANCZOS)
    b = io.BytesIO()
    im.save(b, "JPEG", quality=85)
    return b.getvalue()


def audit(assets: List[Dict[str, Any]], *, vision: Optional[Callable[..., Any]] = None, moderate: Optional[Callable[..., Optional[str]]] = None, workers: int = 4,
          max_usd: float = 1.0, media: tuple = ()) -> Dict[str, Any]:
    """Every asset through `judge`. Stops asking the paid model once `max_usd` is spent (the rest is reported as not checked, verdict 'review')."""
    spent = {"usd": 0.0}

    def one(a: Dict[str, Any]) -> Dict[str, Any]:
        v = vision if spent["usd"] < max_usd else None
        a = {**a, "picture": a["load"]() if (v is not None or moderate is not None) and a.get("load") else None}
        row = judge(a, vision=v, moderate=moderate)
        if vision is not None and v is None:
            row["vision"] = "not checked (audit budget reached)"
            row["why"].append("picture not checked: audit budget reached")
            row["verdict"] = "review" if row["verdict"] == "ok" else row["verdict"]
        spent["usd"] += float(row.get("cost_usd") or 0.0)
        return row
    with ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        rows = list(ex.map(one, assets))
    by: Dict[str, Dict[str, int]] = {m: {"ok": 0, "review": 0, "remove": 0} for m in media}
    for r in rows:
        by.setdefault(r["media"], {"ok": 0, "review": 0, "remove": 0})[r["verdict"]] += 1
    return {"policy_version": mp.VERSION, "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "counts": by, "cost_usd": round(spent["usd"], 4), "rows": rows}


def print_report(rep: Dict[str, Any], store: str) -> None:
    print(f"Library safety audit of {store}: policy {rep['policy_version']}, {rep['at']}. READ ONLY: nothing was changed.")
    for media, c in rep["counts"].items():
        print(f"  {media + 's':<8} {sum(c.values()):>4} checked: {c['ok']} ok, {c['review']} to review, {c['remove']} recommended for removal")
    print(f"  model calls of this audit: ${rep['cost_usd']:.4f}")
    for verdict, head in (("remove", "RECOMMENDED FOR REMOVAL (a check of the picture itself named a policy category)"), ("review", "TO REVIEW (words matched, or a check was unsure or could not run)")):
        rows = [r for r in rep["rows"] if r["verdict"] == verdict]
        if rows:
            print(f"\n{head}")
        for r in rows:
            print(f"  {r['media']:<6} {r['id']}  \"{r['title'][:60]}\"" + (f"  [{r['status']}]" if r.get("status") else ""))
            print(f"         {'; '.join(r['why'])}" + (f"  | seen: {r['seen']}" if r.get("seen") else ""))
    if not any(r["verdict"] != "ok" for r in rep["rows"]):
        print("\nNothing doubtful found.")


# ----------------------------------------------------------------------------- commands
def _stores(a, need_catalog: bool, need_ledger: bool):
    cat = catalog_store.open_store(a.catalog or a.store) if need_catalog else None
    led = cs.open_store(a.store) if need_ledger else None
    return cat, led


def _openai_key(store: str) -> str:
    if os.environ.get("OPENAI_API_KEY"):
        return os.environ["OPENAI_API_KEY"]
    if store in cs.STAGES:
        try:
            import boto3
            cfg = cs.STAGES[store]
            return str(boto3.Session(profile_name=cfg["profile"], region_name=cfg["region"]).client("ssm").get_parameter(Name="/videomk/openai_api_key", WithDecryption=True)["Parameter"]["Value"]).strip()
        except Exception as e:   # noqa: BLE001 - the key is never printed
            print(f"  (no provider key for moderation: {type(e).__name__})", file=sys.stderr)
    return ""


def cmd_audit(a) -> None:
    media = [m.strip() for m in a.media.split(",") if m.strip()]
    cat = catalog_store.open_store(a.catalog or a.store) if {"images", "objects"} & set(media) else None
    led = None
    if {"clips", "objects"} & set(media):
        try:
            led = cs.open_store(a.ledger or a.store)
        except (SystemExit, Exception) as e:   # noqa: BLE001 - a stage without the feature deployed has no library clips and no on-demand drawings
            print(f"  (no clip library / ledger store: {str(e)[:100]})", file=sys.stderr)
    assets: List[Dict[str, Any]] = []
    if "images" in media:
        assets += image_assets(cat, a.limit)
    if "objects" in media:
        assets += object_assets(cat, led, a.limit)
    if "clips" in media and led is not None:
        assets += clip_assets(led, a.limit)
    if a.ids:
        assets = [x for x in assets if x["id"] in set(a.ids.split(","))]
    vision = None
    if a.vision != "none":
        from engine import llm
        model = llm.PRIMARY_MODEL if a.vision == "large" else llm.REVIEW_MODEL
        vision = lambda pics, described: mp.vision_check(pics, described, model=model)   # noqa: E731
    moderate = None
    if not a.no_moderation:
        key = _openai_key(a.store)
        if key:
            moderate = lambda **kw: mp.moderation(key=key, **kw)   # noqa: E731
    rep = audit(assets, vision=vision, moderate=moderate, workers=a.workers, max_usd=a.max_usd, media=tuple(m.rstrip("s") for m in media))
    rep["store"], rep["vision"], rep["moderation"] = a.store, a.vision, moderate is not None
    print_report(rep, a.store)
    if a.json:
        with open(a.json, "w") as f:
            json.dump(rep, f, ensure_ascii=False, indent=1)
        print(f"\nfull report: {a.json}")


def cmd_takedown(a) -> None:
    dry = not a.no_dry_run
    if not dry and "prod" in (a.store, a.catalog) and not a.yes_prod:
        if input(f"This takes {a.kind} {a.id} out of PRODUCTION. Type prod to go on: ").strip() != "prod":
            sys.exit("stopped")
    restore = a.cmd == "restore"
    if a.kind == "image":
        cat = catalog_store.open_store(a.catalog or a.store)
        led = _maybe_ledger(a)
        steps = takedown.restore_image(cat, a.id, ledger=led, dry_run=dry) if restore else takedown.image(cat, a.id, a.reason, ledger=led, dry_run=dry)
    elif a.kind == "clip":
        store = cs.open_store(a.store)
        steps = takedown.restore_clip(store, a.id, dry_run=dry) if restore else takedown.clip(store, a.id, a.reason, dry_run=dry)
    else:
        cat = catalog_store.open_store(a.catalog or a.store)
        led = _maybe_ledger(a)
        steps = takedown.restore_sketch(led, cat, a.id, dry_run=dry) if restore else takedown.sketch(led, cat, a.id, a.reason, dry_run=dry)
    print(("DRY RUN, nothing changed. It would:" if dry else "Done:"))
    for s in steps:
        print("  " + s)


def _maybe_ledger(a) -> Optional[cs.Store]:
    spec = a.ledger or (a.store if a.store in cs.STAGES else "")
    try:
        return cs.open_store(spec) if spec else None
    except (SystemExit, Exception):   # noqa: BLE001
        return None


def cmd_taken(a) -> None:
    rows = takedown.taken(cs.open_store(a.ledger or a.store))
    for r in rows:
        print(f"  {time.strftime('%Y-%m-%d %H:%M', time.gmtime(int(r.get('at') or 0)))}  {r.get('media'):<6} {r.get('id')}  {r.get('state')}  {r.get('reason')}")
    print(f"{len(rows)} takedown(s) on record")


def main(argv: Optional[List[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("policy")
    p = sub.add_parser("audit")
    p.add_argument("--store", required=True)
    p.add_argument("--catalog", default="", help="the catalog store when it differs from --store (e.g. local:<catalog folder>)")
    p.add_argument("--ledger", default="", help="the clip-library / ledger store when it differs from --store")
    p.add_argument("--media", default="images,objects,clips")
    p.add_argument("--vision", choices=("none", "small", "large"), default="small")
    p.add_argument("--no-moderation", action="store_true")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--ids", default="", help="only these asset ids (comma separated): to look again at a few")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--max-usd", type=float, default=1.0)
    p.add_argument("--json", default="")
    for name in ("takedown", "restore"):
        p = sub.add_parser(name)
        p.add_argument("kind", choices=("image", "clip", "object"))
        p.add_argument("id")
        p.add_argument("--store", required=True)
        p.add_argument("--catalog", default="")
        p.add_argument("--ledger", default="")
        p.add_argument("--reason", default="" if name == "restore" else None, required=name == "takedown")
        p.add_argument("--no-dry-run", action="store_true")
        p.add_argument("--yes-prod", action="store_true")
    p = sub.add_parser("taken")
    p.add_argument("--store", required=True)
    p.add_argument("--ledger", default="")
    a = ap.parse_args(argv)
    if a.cmd == "policy":
        print(f"VideoMK library safety policy, version {mp.VERSION}\n\n{mp.VISION_RUBRIC}\n\nWord lists: English and Spanish, {len(mp.CODES)} categories ({', '.join(mp.CODES)}).")
    elif a.cmd == "audit":
        cmd_audit(a)
    elif a.cmd in ("takedown", "restore"):
        cmd_takedown(a)
    else:
        cmd_taken(a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
