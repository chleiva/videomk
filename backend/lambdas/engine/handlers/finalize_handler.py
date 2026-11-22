"""Step 5: stitch segments (stream copy) + audio -> MP4, preview GIF, credits, mark COMPLETE."""
import os
import tempfile
from typing import Any, Dict, List

from generate_video.db import update_status

from .. import assets, awsio, media, pipeline

OUTPUT_BUCKET = os.environ.get("ASSETS_BUCKET", "videomk.com")


def _chapters_text(chapters: List[Dict[str, Any]], duration: float) -> str:
    """YouTube needs the first chapter at 0:00, 3+ chapters, each >= 10 s."""
    ch = [c for c in chapters]
    if ch and ch[0]["start"] > 0.5:
        ch.insert(0, {"start": 0.0, "title": "Intro"})
    ch = [c for i, c in enumerate(ch) if i == 0 or c["start"] - ch[i - 1]["start"] >= 10]
    if len(ch) < 3:
        return ""
    fmt = lambda s: f"{int(s) // 60}:{int(s) % 60:02d}"
    return "\n".join(f"{fmt(c['start'])} {c['title']}" for c in ch)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    video_id, user_id = str(event["video_id"]), str(event["user_id"])
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
        mp4 = os.path.join(tmp, "final.mp4")
        media.mux_final(paths, audio_path, mp4, fps=tl["fps"])
        got = media.ffprobe_duration(mp4)
        if abs(got - float(tl["duration"])) > 1.0:
            raise RuntimeError(f"stitched duration {got:.2f}s != timeline {tl['duration']:.2f}s")
        gif = os.path.join(tmp, "preview.gif")
        have_gif = pipeline.preview_gif(mp4, gif, got)

        vkey = f"videos/{user_id}/{video_id}.mp4"
        awsio.upload(mp4, vkey, "video/mp4", bkt=OUTPUT_BUCKET)
        gkey = f"videos/{user_id}/{video_id}.gif"
        if have_gif:
            awsio.upload(gif, gkey, "image/gif", bkt=OUTPUT_BUCKET)

    description = "\n\n".join(x for x in (tl.get("description", ""), _chapters_text(tl.get("chapters", []), got), assets.credits_block(tl.get("ledger", []), tl.get("sources", []))) if x)
    update_status(
        video_id, "COMPLETE",
        extra_attributes={
            "video_uri": f"s3://{OUTPUT_BUCKET}/{vkey}",
            "duration_s": int(got),
            **({"preview_gif_uri": f"s3://{OUTPUT_BUCKET}/{gkey}"} if have_gif else {}),
            "youtube_description": description[:4800],
        },
    )
    # intermediates are large and re-creatable; keep plan/timeline/audio/images for cheap edits
    try:
        for s in segs:
            awsio.s3().delete_object(Bucket=awsio.bucket(), Key=s["key"])
        awsio.s3().delete_object(Bucket=awsio.bucket(), Key=event["render"]["audio"]["key"])
    except Exception:
        pass
    return {"video_id": video_id, "status": "COMPLETE", "duration_s": got}
