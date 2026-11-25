"""Step 5: stitch segments (stream copy) + audio -> MP4, preview GIF, credits. Final or preview, initial or edit."""
import os
import tempfile
import time
from typing import Any, Dict, List

from generate_video.db import set_attributes, update_status

from .. import assets, awsio, media, pipeline

OUTPUT_BUCKET = os.environ.get("ASSETS_BUCKET", "videomk.com")


def _chapters_text(chapters: List[Dict[str, Any]], language: str = "en") -> str:
    """YouTube needs the first chapter at 0:00, 3+ chapters, each >= 10 s."""
    ch = list(chapters)
    if ch and ch[0]["start"] > 0.5:
        ch.insert(0, {"start": 0.0, "title": assets.LABELS.get(language, assets.LABELS["en"])["intro"]})
    ch = [c for i, c in enumerate(ch) if i == 0 or c["start"] - ch[i - 1]["start"] >= 10]
    if len(ch) < 3:
        return ""
    fmt = lambda s: f"{int(s) // 60}:{int(s) % 60:02d}"
    return "\n".join(f"{fmt(c['start'])} {c['title']}" for c in ch)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    video_id, user_id = str(event["video_id"]), str(event["user_id"])
    rev, mode = int(event.get("rev", 1)), event.get("mode", "final")
    tl = awsio.get_json(event["timeline_key"])
    segs = sorted(event["render"]["segments"], key=lambda s: int(s["k"]))
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

    description = "\n\n".join(x for x in (tl.get("description", ""), _chapters_text(tl.get("chapters", []), tl.get("language", "en")), assets.credits_block(tl.get("ledger", []), tl.get("sources", []), tl.get("language", "en"))) if x)
    attrs = {
        "video_uri": f"s3://{OUTPUT_BUCKET}/{vkey}", "duration_s": int(got), "final_rev": rev, "edit_state": "READY",
        "aspect": (tl.get("frame") or {}).get("aspect", "16:9"), "resolution": (tl.get("frame") or {}).get("resolution", "1080p"),
        "youtube_description": description[:4800], "title": tl.get("title") or "Untitled", "last_rendered_at": int(time.time()),
        **({"preview_gif_uri": f"s3://{OUTPUT_BUCKET}/{gkey}"} if have_gif else {}),
    }
    update_status(video_id, "COMPLETE", extra_attributes=attrs)  # first render: flips status (no-op once COMPLETE)
    set_attributes(video_id, attrs, remove=["edit_error"])         # edits: refresh the playable video on an already-COMPLETE item
    return {"video_id": video_id, "status": "COMPLETE", "rev": rev, "duration_s": got}
