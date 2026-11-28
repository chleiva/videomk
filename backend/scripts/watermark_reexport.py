#!/usr/bin/env python3
"""Re-export a finished video with a different watermark (or none) WITHOUT re-rendering any scene (docs/WATERMARK_DECOUPLED_2026-11-28.md).

The watermark is the last step (engine/final_stage.py), so the same video without it is: the video's cached watermark-free render segments + its audio mix, stitched (stream copy) and
passed through the final stage with another spec. Only the video track is re-encoded (the overlay); no scene is drawn.

  AWS_PROFILE=<stage> ASSETS_BUCKET=<bucket> python backend/scripts/watermark_reexport.py --video-id V --rev 1 --out /tmp/v_nomark.mp4 [--watermark none|keep|'{"mode":"videomk",...}'] [--draft]
  ... --upload-key videos/<user>/<video>/r1_nomark.mp4 --bucket <output bucket>     # also store it (an admin decision; nothing links it to the product yet)

--watermark none (default) = the same video without the mark and without the closing card. keep = what the video was made with (a check that the export equals the delivered video).
Segments must still be cached (they live under generation/v2/<video>/segments/ for the bucket's retention); a missing one stops the script (nothing is re-rendered here).
"""
import argparse
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "lambdas"))

from engine import awsio, final_stage, media  # noqa: E402
from engine.handlers.render_chunk_handler import make_image_loader, segment_key  # noqa: E402
from engine.handlers.timeline_handler import plan_chunks  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--video-id", required=True)
    ap.add_argument("--rev", type=int, default=1)
    ap.add_argument("--mode", default="final", choices=("final", "preview"))
    ap.add_argument("--watermark", default="none", help="none (default) | keep | a JSON watermark object")
    ap.add_argument("--out", required=True)
    ap.add_argument("--upload-key")
    ap.add_argument("--bucket", default=os.environ.get("OUTPUT_BUCKET") or awsio.bucket())
    a = ap.parse_args()
    pfx = awsio.prefix(a.video_id)
    tl = awsio.get_json(f"{pfx}timeline_r{a.rev}.json")
    _, chunks = plan_chunks(tl, a.mode)
    override = final_stage._UNSET if a.watermark == "keep" else (None if a.watermark == "none" else json.loads(a.watermark))
    with tempfile.TemporaryDirectory() as tmp:
        paths = []
        for c in chunks:
            key = segment_key(a.video_id, c["hash"], bool(c.get("draft")))
            if not awsio.head(key):
                print(f"segment {key} is no longer cached: the video would have to be re-rendered", file=sys.stderr)
                return 2
            p = os.path.join(tmp, f"seg_{int(c['k']):03d}.ts")
            awsio.download(key, p)
            paths.append(p)
        audio = os.path.join(tmp, "mix.m4a")
        awsio.download(f"{pfx}audio/mix_r{a.rev}_{a.mode}.m4a", audio)
        master = os.path.join(tmp, "master.mp4")
        media.mux_final(paths, audio, master, fps=int(tl["fps"]))
        info = final_stage.export(tl, master, audio, a.out, draft=(a.mode == "preview"), image_loader=make_image_loader(a.video_id), spec_override=override, tmp=tmp)
    print(json.dumps({"out": a.out, "seconds": media.ffprobe_duration(a.out), "watermark": info["watermark"], "end_card": info["end_card"]}))
    if a.upload_key:
        awsio.upload(a.out, a.upload_key, "video/mp4", bkt=a.bucket)
        print(f"uploaded s3://{a.bucket}/{a.upload_key}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
