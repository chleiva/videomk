"""Step 3: merge measured media into the plan, build the timeline, and plan content-addressed chunks."""
import logging
import os
from typing import Any, Dict

from .. import awsio, format_options
from .. import sync as sync_mod
from ..timeline import beat_info_from_plan, build_timeline, chunk_plan

MAX_DURATION_S = float(os.environ.get("MAX_VIDEO_SECONDS", str(13 * 60)))
CHUNK_SECONDS = int(os.environ.get("CHUNK_SECONDS", "10"))
# 4K (docs/FOUR_K.md): a frame takes about 2.5 times as long to draw and encode as at 1080p, so chunks are shorter and a long scene is cut into pieces:
# every render function then finishes in a few minutes of its 10. Previews of a 4K video are small drafts and are chunked like any other video.
CHUNK_SECONDS_4K = int(os.environ.get("CHUNK_SECONDS_4K", "6"))
CHUNK_MAX_FRAMES_4K = int(os.environ.get("CHUNK_MAX_FRAMES_4K", "180"))


def credits_ledger(plan: Dict[str, Any]) -> list:
    """Every licensed photograph or clip the video shows, for the credits in its description: image and clip scenes, each photo of a gallery, and the photo
    of any element that fetches one (its `prepare` patch carries a `ledger`, e.g. annotated_image)."""
    out = [b["media"]["ledger"] for b in plan["beats"] if b["scene"]["type"] in ("image", "clip") and (b.get("media") or {}).get("ledger") and not (b.get("media") or {}).get("ledgers")]
    out += [e for b in plan["beats"] if b["scene"]["type"] == "clip" for e in (b.get("media") or {}).get("ledgers") or [] if e]   # a montage: one line per clip
    out += [g["ledger"] for b in plan["beats"] if b["scene"]["type"] == "gallery" for g in (b.get("media") or {}).get("gallery") or [] if g.get("ledger")]
    out += [b["media"]["element"]["ledger"] for b in plan["beats"]
            if isinstance((b.get("media") or {}).get("element"), dict) and b["media"]["element"].get("ledger") and not (b.get("media") or {}).get("element_failed")]
    return out


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    video_id = str(event["video_id"])
    rev = int(event.get("rev", 1))
    mode = event.get("mode", "final")
    pfx = awsio.prefix(video_id)
    plan = awsio.get_json(event["plan_key"])

    new_media = {r["id"]: r["media"] for r in event.get("beats") or []}
    for b in plan["beats"]:
        if b["id"] in new_media:
            b["media"] = new_media[b["id"]]
        if not (b.get("media") or {}).get("duration"):
            raise ValueError(f"beat {b['id']} has no audio")
    awsio.put_json(event["plan_key"], plan)  # the plan now carries its measured media (editor + future edits read it)

    infos = beat_info_from_plan(plan)
    for info in infos:  # word timings measured from each beat's audio (stored next to it); missing or unreadable ones fall back to the estimate
        key = info.pop("words_key", None)
        if isinstance(key, str) and key.startswith(pfx + "audio/") and ".." not in key:
            try:
                info["words"] = awsio.get_json(key)["words"]
            except Exception:
                pass
    frame = format_options.frame_of(plan)   # a plan made before formats existed has no frame: 16:9 1080p
    tl = build_timeline(plan, infos, video_id=video_id, fps=30, width=frame["width"], height=frame["height"], min_seconds=float(plan.get("target_seconds") or 0) if rev == 1 and os.environ.get("STRETCH_TO_TARGET", "1") != "0" else 0.0)   # only a first render: an edit that removes scenes must be allowed to be shorter
    rep = sync_mod.report(tl)  # the free alignment check: is every reveal near the word that names it? (no model, a few ms)
    tl["sync"].update({k: rep[k] for k in ("anchored", "early", "late", "mean_abs_delta", "ok")})
    if not rep["ok"]:
        logging.warning("sync check: %s", {k: rep[k] for k in ("items", "anchored", "early", "late", "mean_abs_delta")} | {"worst": sorted((r for r in rep["rows"] if r["delta"] is not None), key=lambda r: -abs(r["delta"]))[:3]})
    if tl["duration"] > MAX_DURATION_S:
        raise ValueError(f"video too long ({tl['duration']:.0f}s > {MAX_DURATION_S:.0f}s)")
    tl["frame"] = frame
    tl["ledger"] = credits_ledger(plan)
    tl["sources"] = plan.get("sources", [])
    tl["description"] = plan.get("description", "")
    tl["language"] = plan.get("language", "en")
    key = f"{pfx}timeline_r{rev}.json"
    awsio.put_json(key, tl)
    return {
        "video_id": video_id,
        "user_id": event.get("user_id"),
        "usage_day": event.get("usage_day"),
        "plan_key": event["plan_key"],
        "rev": rev,
        "mode": mode,
        "timeline_key": key,
        "duration": tl["duration"],
        "chunks": [{**c, "video_id": video_id, "timeline_key": key} for c in (
            chunk_plan(tl, CHUNK_SECONDS_4K, draft=False, max_frames=CHUNK_MAX_FRAMES_4K) if format_options.is_4k(frame["resolution"]) and mode != "preview"
            else chunk_plan(tl, CHUNK_SECONDS, draft=(mode == "preview")))],
    }
