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
    out["has"] = {n: (n in filters) for n in ("sidechaincompress", "alimiter", "amix", "afade")}
    out["has"].update({"libx264": "libx264" in encoders, "aac": " aac " in encoders})
    amix_help = subprocess.run([ff, "-hide_banner", "-h", "filter=amix"], capture_output=True, text=True).stdout
    out["has"]["amix_normalize_option"] = "normalize" in amix_help
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
    out["tmp_free_mb"] = round(os.statvfs("/tmp").f_bavail * os.statvfs("/tmp").f_frsize / 1e6)
    out["ok"] = all(out["has"].values())
    return out
