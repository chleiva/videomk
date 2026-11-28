#!/usr/bin/env python3
"""Give existing finished videos a cover and a link-preview card (docs/SHARE_PREVIEWS_2026-11-28.md), the way engine/cover.py does for new ones.

  AWS_PROFILE-free: the profile and region come from backend/stages.json.
  python backend/scripts/cover_backfill.py --stage qa               # dry run: counts and lists what WOULD be written (default)
  python backend/scripts/cover_backfill.py --stage qa --apply       # writes (prod asks you to type prod)
  options: --limit N  --rate 2 (videos per second, default 2)  --video <id>

No re-render: the art is a frame of the video's stored preview GIF (the middle of it, where a whiteboard is drawn and a presenter has come in), cut to the video's own
shape; engine/cover.build_from_art puts the title and the mark on it. The theme is not stored on the row, so the "paper" design is used (title on an ink ribbon below the
art: never type over the art's own type). Videos with no GIF are skipped and counted. A video that already has cover_uri AND cover_og_uri is left alone, and a row is only
updated when it still has none (conditional write), so a run can be repeated and never overwrites a cover a render made.
Files go next to the MP4: videos/<user>/<video>/r<rev>_cover.jpg and r<rev>_og.jpg, the same names finalize_handler uses.
"""
import argparse
import io
import json
import os
import sys
import time
from typing import Any, Callable, Dict, Iterator, Optional

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambdas"))

from PIL import Image  # noqa: E402

from engine import cover  # noqa: E402

THEME = "paper"


def split_uri(uri: str):
    b, _, k = uri[5:].partition("/")
    return b, k


def own_key_ok(item: Dict[str, Any], key: str) -> bool:
    return key.startswith(f"videos/{item['user_id']}/{item['video_id']}/") and ".." not in key


def needs_cover(item: Dict[str, Any]) -> bool:
    return str(item.get("status") or "").upper() == "COMPLETE" and not (item.get("cover_uri") and item.get("cover_og_uri"))


def art_from_gif(data: bytes) -> Optional[Image.Image]:
    """The middle frame of the preview GIF as RGB; None when it cannot be read."""
    try:
        im = Image.open(io.BytesIO(data))
        n = max(1, getattr(im, "n_frames", 1))
        im.seek(n // 2)
        return im.convert("RGB")
    except Exception:   # noqa: BLE001
        return None


def process(item: Dict[str, Any], s3: Any, table: Any, apply: bool) -> str:
    """One video -> "done" | "would" | "no_gif" | "bad_gif" | "unsafe"."""
    gif = item.get("preview_gif_uri")
    if not isinstance(gif, str) or not gif.startswith("s3://"):
        return "no_gif"
    bucket, gkey = split_uri(gif)
    if not own_key_ok(item, gkey):
        return "unsafe"
    if not apply:
        return "would"
    art = art_from_gif(s3.get_object(Bucket=bucket, Key=gkey)["Body"].read())
    if art is None:
        return "bad_gif"
    aspect = str(item.get("aspect") or cover.aspect_of({"width": art.width, "height": art.height}))
    out = cover.build_from_art(art, str(item.get("title") or ""), aspect=aspect, theme=THEME, layout="ribbon")
    rev = int(item.get("final_rev") or 1)
    base = f"videos/{item['user_id']}/{item['video_id']}/"
    own_k, og_k = f"{base}r{rev}_cover.jpg", f"{base}r{rev}_og.jpg"
    s3.put_object(Bucket=bucket, Key=own_k, Body=out["own"], ContentType="image/jpeg")
    s3.put_object(Bucket=bucket, Key=og_k, Body=out["og"], ContentType="image/jpeg")
    table.update_item(Key={"video_id": item["video_id"]}, UpdateExpression="SET cover_uri = :a, cover_og_uri = :b",
                      ConditionExpression="user_id = :u AND attribute_not_exists(cover_uri) AND attribute_not_exists(cover_og_uri)",
                      ExpressionAttributeValues={":a": f"s3://{bucket}/{own_k}", ":b": f"s3://{bucket}/{og_k}", ":u": item["user_id"]})
    return "done"


def scan_items(table: Any) -> Iterator[Dict[str, Any]]:
    kw: Dict[str, Any] = {}
    while True:
        res = table.scan(**kw)
        yield from res.get("Items", [])
        if not res.get("LastEvaluatedKey"):
            return
        kw["ExclusiveStartKey"] = res["LastEvaluatedKey"]


def run(items: Iterator[Dict[str, Any]], s3: Any, table: Any, *, apply: bool, limit: Optional[int] = None, rate: float = 2.0,
        sleep: Callable[[float], None] = time.sleep, log: Callable[[str], None] = print) -> Dict[str, int]:
    counts: Dict[str, int] = {"seen": 0, "has_cover": 0, "not_ready": 0, "failed": 0}
    handled = 0
    for it in items:
        counts["seen"] += 1
        if str(it.get("status") or "").upper() != "COMPLETE":
            counts["not_ready"] += 1
            continue
        if not needs_cover(it):
            counts["has_cover"] += 1
            continue
        if limit is not None and handled >= limit:
            break
        handled += 1
        try:
            r = process(it, s3, table, apply)
        except Exception as e:   # noqa: BLE001 - one bad video never stops the run
            r = "failed"
            log(f"FAILED {it.get('video_id')}: {type(e).__name__}: {e}")
        counts[r] = counts.get(r, 0) + 1
        if r in ("would", "done"):
            log(f"{r} {it.get('video_id')} {str(it.get('title') or '')[:50]!r}")
            if apply and rate > 0:
                sleep(1.0 / rate)
    return counts


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--stage", choices=["qa", "prod"], required=True)
    ap.add_argument("--apply", action="store_true", help="write the covers (default: dry run)")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--rate", type=float, default=2.0, help="videos per second when writing")
    ap.add_argument("--video", help="only this video id")
    a = ap.parse_args(argv)
    if a.apply and a.stage == "prod" and input("type prod to write covers on PROD: ").strip() != "prod":
        return 1
    import boto3
    cfg = json.load(open(os.path.join(os.path.dirname(__file__), "..", "stages.json")))[a.stage]
    session = boto3.Session(profile_name=cfg["profile"], region_name=cfg["region"])
    ddb = session.resource("dynamodb")
    name = next(t for t in session.client("dynamodb").list_tables()["TableNames"] if t.startswith(f"videomk-{a.stage}-VideosTable"))
    table = ddb.Table(name)
    items = iter([table.get_item(Key={"video_id": a.video}).get("Item") or {}]) if a.video else scan_items(table)
    c = run(items, session.client("s3"), table, apply=a.apply, limit=a.limit, rate=a.rate)
    print(("APPLIED " if a.apply else "DRY RUN ") + json.dumps(c))
    return 0


if __name__ == "__main__":
    sys.exit(main())
