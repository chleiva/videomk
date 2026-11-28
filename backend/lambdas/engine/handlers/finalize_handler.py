"""Step 5: stitch segments (stream copy) + audio -> MP4, preview GIF, credits. Final or preview, initial or edit."""
import os
import tempfile
import time
from typing import Any, Dict, List

from generate_video.db import set_attributes, update_status

from common import making

from .. import assets, awsio, costs, making_progress, media, pipeline

OUTPUT_BUCKET = os.environ.get("ASSETS_BUCKET", "videomk.com")


def _chapters_text(chapters: List[Dict[str, Any]], language: str = "en") -> str:
    """YouTube needs the first chapter at 0:00, 3+ chapters, each >= 10 s."""
    ch = list(chapters)
    if ch and ch[0]["start"] > 0.5:
        ch.insert(0, {"start": 0.0, "title": assets.labels(language)["intro"]})
    ch = [c for i, c in enumerate(ch) if i == 0 or c["start"] - ch[i - 1]["start"] >= 10]
    if len(ch) < 3:
        return ""
    fmt = lambda s: f"{int(s) // 60}:{int(s) % 60:02d}"
    return "\n".join(f"{fmt(c['start'])} {c['title']}" for c in ch)


def copy_cover(event: Dict[str, Any], base: str, rev: int) -> Dict[str, str]:
    """The cover pictures the first chunk made (engine/cover.py) -> the video's own folder, next to the MP4: {cover_uri (the video's own shape), cover_og_uri (1200x630)}.
    Empty when there are none: a video without a cover is still complete, and the apps fall back to the GIF."""
    try:
        want = ((sorted(event["render"]["segments"], key=lambda s: int(s["k"]))[0]).get("cover")) or {}
        pre = awsio.prefix(str(event["video_id"]))
        out: Dict[str, str] = {}
        for src_key, name, attr in ((want.get("own_key"), f"r{rev}_cover.jpg", "cover_uri"), (want.get("og_key"), f"r{rev}_og.jpg", "cover_og_uri")):
            if not isinstance(src_key, str) or not src_key.startswith(pre + "cover_") or ".." in src_key:
                return {}
            awsio.put_bytes(base + name, awsio.get_bytes(src_key), "image/jpeg", bkt=OUTPUT_BUCKET)
            out[attr] = f"s3://{OUTPUT_BUCKET}/{base}{name}"
        return out
    except Exception:   # noqa: BLE001 - never worth a failed video
        import logging
        logging.exception("COVER_COPY_FAILED video=%s", event.get("video_id"))
        return {}


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    video_id, user_id = str(event["video_id"]), str(event["user_id"])
    rev, mode = int(event.get("rev", 1)), event.get("mode", "final")
    tl = awsio.get_json(event["timeline_key"])
    if rev == 1 and mode != "preview":
        making_progress.finishing(video_id)   # the Making screen: "Adding the finishing touches" (only while the video is being made; never raises)
    segs = sorted(event["render"]["segments"], key=lambda s: int(s["k"]))
    costs.add_render(video_id, sum(float(s.get("gbs") or 0) for s in segs))   # what the render chunks of this run cost (estimate; information, never fails a video)
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for s in segs:
            p = os.path.join(tmp, f"seg_{int(s['k']):03d}.ts")
            awsio.download(s["key"], p)
            paths.append(p)
        audio_path = os.path.join(tmp, "mix.m4a")
        awsio.download(event["render"]["audio"]["key"], audio_path)
        mp4 = os.path.join(tmp, "out.mp4")
        media.mux_final(paths, audio_path, mp4, fps=tl["fps"])
        got = media.ffprobe_duration(mp4)
        if abs(got - float(tl["duration"])) > 1.0:
            raise RuntimeError(f"stitched duration {got:.2f}s != timeline {tl['duration']:.2f}s")

        base = f"videos/{user_id}/{video_id}/"
        if mode == "preview":
            vkey = f"{base}preview_r{rev}.mp4"
            awsio.upload(mp4, vkey, "video/mp4", bkt=OUTPUT_BUCKET)
            set_attributes(video_id, {"preview_uri": f"s3://{OUTPUT_BUCKET}/{vkey}", "preview_rev": rev, "edit_state": "READY"}, remove=["edit_error"])
            return {"video_id": video_id, "status": "PREVIEW_READY", "rev": rev, "duration_s": got}

        gif = os.path.join(tmp, "preview.gif")
        have_gif = pipeline.preview_gif(mp4, gif, got)
        vkey, gkey = f"{base}r{rev}.mp4", f"{base}r{rev}.gif"
        awsio.upload(mp4, vkey, "video/mp4", bkt=OUTPUT_BUCKET)
        if have_gif:
            awsio.upload(gif, gkey, "image/gif", bkt=OUTPUT_BUCKET)

    covers = copy_cover(event, base, rev)
    description = "\n\n".join(x for x in (tl.get("description", ""), _chapters_text(tl.get("chapters", []), tl.get("language", "en")), assets.credits_block(tl.get("ledger", []), tl.get("sources", []), tl.get("language", "en"))) if x)
    attrs = {
        "video_uri": f"s3://{OUTPUT_BUCKET}/{vkey}", "duration_s": int(got), "final_rev": rev, "edit_state": "READY",
        "aspect": (tl.get("frame") or {}).get("aspect", "16:9"), "resolution": (tl.get("frame") or {}).get("resolution", "1080p"),
        "youtube_description": description[:4800], "title": tl.get("title") or "Untitled", "last_rendered_at": int(time.time()),
        **({"preview_gif_uri": f"s3://{OUTPUT_BUCKET}/{gkey}"} if have_gif else {}),
        **covers,   # the designed cover (docs/SHARE_PREVIEWS_2026-11-28.md): poster in the apps and the web, og:image of a share page
    }
    update_status(video_id, "COMPLETE", extra_attributes=attrs)  # first render: flips status (no-op once COMPLETE)
    set_attributes(video_id, attrs, remove=["edit_error", *making.ATTRS])   # edits: refresh the playable video on an already-COMPLETE item; the Making status is over
    return {"video_id": video_id, "status": "COMPLETE", "rev": rev, "duration_s": got}
