"""Deploy-time smoke test: proves the layer, ffmpeg and renderer work on *this* Lambda runtime and reports
timings, so you can size memory/concurrency from data instead of guesses.

  aws lambda invoke --function-name engine_selftest /dev/stdout
"""
import os
import platform
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {"python": sys.version.split()[0], "arch": platform.machine(), "memory_mb": getattr(context, "memory_limit_in_mb", None)}
    t = time.time()
    import numpy, PIL  # noqa: F401

    out["numpy"], out["pillow"] = numpy.__version__, PIL.__version__
    from engine import media

    ff = media.ffmpeg_bin()
    out["ffmpeg"] = ff
    ver = subprocess.run([ff, "-version"], capture_output=True, text=True).stdout.splitlines()[0]
    out["ffmpeg_version"] = ver
    filters = subprocess.run([ff, "-hide_banner", "-filters"], capture_output=True, text=True).stdout
    encoders = subprocess.run([ff, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout
    out["has"] = {n: (n in filters) for n in ("sidechaincompress", "alimiter", "amix", "afade", "loudnorm")}
    out["has"].update({"libx264": "libx264" in encoders, "aac": " aac " in encoders})
    amix_help = subprocess.run([ff, "-hide_banner", "-h", "filter=amix"], capture_output=True, text=True).stdout
    out["has"]["amix_normalize_option"] = "normalize" in amix_help
    decoders = subprocess.run([ff, "-hide_banner", "-decoders"], capture_output=True, text=True).stdout
    out["has"].update({f"decode_{n}": (f" {n} " in decoders) for n in ("h264", "vp8", "vp9", "theora")})  # stock clips arrive as mp4, webm and ogv
    out["imports_s"] = round(time.time() - t, 2)

    # render 60 frames of a mixed-scene timeline, encode, time it
    fixture = {
        "fps": 30, "width": 1920, "height": 1080, "theme": "midnight", "duration": 4.0, "captions": True,
        "scenes": [
            {"id": "a", "type": "title", "start": 0, "duration": 2.0, "props": {"title": "Self test", "subtitle": "Layer, fonts, encoder"}, "words": [["Hello", 0.4, 0.8], ["world.", 0.8, 1.2]]},
            {"id": "b", "type": "diagram", "start": 2.0, "duration": 2.0, "props": {"nodes": [{"id": "a", "label": "Plan"}, {"id": "b", "label": "Render"}], "edges": [["a", "b"]]}, "words": []},
        ],
    }
    from engine import pipeline

    with tempfile.TemporaryDirectory() as tmp:
        seg = os.path.join(tmp, "s.ts")
        t = time.time()
        info = pipeline.render_chunk(fixture, 0, 60, seg)
        el = time.time() - t
        out["render_60_frames_s"] = round(el, 2)
        out["ms_per_frame"] = round(el / info["frames"] * 1000, 1)
        out["segment_bytes"] = os.path.getsize(seg)

    # stock clips: make real footage here, run the real normalise -> decode -> render path, and time it
    from engine import clips

    with tempfile.TemporaryDirectory() as tmp:
        src = os.path.join(tmp, "src.mp4")
        subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=25", "-t", "4", "-pix_fmt", "yuv420p", src], check=True)
        t = time.time()
        with open(src, "rb") as fh:
            mp4, _ = clips.normalise(fh.read(), need_seconds=3.0, source_seconds=4.0, suffix=".mp4")
        out["clip_normalise_s"] = round(time.time() - t, 2)
        path = os.path.join(tmp, "clip.mp4")
        with open(path, "wb") as fh:
            fh.write(mp4)
        t = time.time()
        frames = clips.ClipFrames(path)
        out["clip_decode_s"], out["clip_frames"], out["clip_bytes"] = round(time.time() - t, 2), len(frames), len(mp4)
        clip_tl = {"fps": 30, "width": 1920, "height": 1080, "theme": "midnight", "duration": 3.0, "captions": True,
                   "scenes": [{"id": "c", "type": "clip", "start": 0, "duration": 3.0, "props": {"asset": "x.mp4", "alt": "test"}, "words": [["Hello", 0.4, 0.8]]}]}
        seg = os.path.join(tmp, "c.ts")
        t = time.time()
        info = pipeline.render_chunk(clip_tl, 0, 60, seg, clip_loader=lambda key: frames)
        out["clip_render_60_frames_s"] = round(time.time() - t, 2)
        out["clip_render_frames"] = info["frames"]
    out["has"]["clip_path"] = out["clip_frames"] >= 85 and out["clip_render_frames"] == 60
    # 4K (docs/FOUR_K.md): the same mixed timeline at 3840x2160, to read the real ms per frame and memory of this runtime before switching 4K on. Never fails the self test.
    try:
        import resource

        big = dict(fixture, width=3840, height=2160, frame={"aspect": "16:9", "resolution": "2160p"})
        with tempfile.TemporaryDirectory() as tmp:
            seg = os.path.join(tmp, "k.ts")
            t = time.time()
            info = pipeline.render_chunk(big, 45, 75, seg)   # 30 frames across the cut between the two scenes
            out["ms_per_frame_4k"] = round((time.time() - t) / info["frames"] * 1000, 1)
            out["segment_bytes_4k"] = os.path.getsize(seg)
        out["peak_rss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024)   # Linux reports kilobytes
    except Exception as e:  # noqa: BLE001
        out["error_4k"] = f"{type(e).__name__}: {e}"[:200]
    out["tmp_free_mb"] = round(os.statvfs("/tmp").f_bavail * os.statvfs("/tmp").f_frsize / 1e6)
    out["ok"] = all(out["has"].values())
    return out
