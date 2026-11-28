"""Video upload, the media work (docs/VIDEO_UPLOAD_2026-11-28.md section 4): look inside an untrusted file, make the one normalised copy we keep, sample frames.

Rules this module keeps:
  * ffmpeg is run with FIXED arguments only. Nothing the user sent (a name, a header, a filter, a codec option) ever reaches a command line; the file is always
    `src` in a work folder we made, and `-protocol_whitelist file` stops a playlist or a container from fetching anything else;
  * the container and the video codec must be on the lists in common/vidup.py; sizes, length and frame rate are bounded BEFORE any decode;
  * the kept copy carries no metadata at all (no GPS, no device, no title, no chapters, no extra streams), is at most 5 s, at most 1080p-class, 30 fps, H.264, silent.
"""
import io
import json
import os
import random
import re
import shutil
import subprocess
from typing import Any, Dict, List, Optional, Sequence, Tuple

from common import vidup as V

RUN_TIMEOUT_S = 90


class Rejected(Exception):
    """The file cannot be used. `code` is stable (the apps map it to wording): not_video, container, codec, too_long, too_big, too_small, fps, no_video, unreadable."""

    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code, self.detail = code, detail


def ffmpeg_bin() -> str:
    env = os.environ.get("FFMPEG_BIN")
    if env and os.path.exists(env):
        return env
    try:   # the static binary of the layer (imageio-ffmpeg wheel)
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:   # noqa: BLE001
        pass
    found = shutil.which("ffmpeg")
    if not found:
        raise RuntimeError("ffmpeg not found (set FFMPEG_BIN or add imageio-ffmpeg to the layer)")
    return found


def ffprobe_bin() -> Optional[str]:
    env = os.environ.get("FFPROBE_BIN")
    if env and os.path.exists(env):
        return env
    return shutil.which("ffprobe")


def _run(cmd: List[str], timeout: int = RUN_TIMEOUT_S) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, timeout=timeout, stdin=subprocess.DEVNULL)


# ----------------------------------------------------------------------------- probe
def _rotation(stream: Dict[str, Any]) -> int:
    tags = (stream.get("tags") or {}).get("rotate")
    if tags is not None:
        try:
            return int(float(tags)) % 360
        except ValueError:
            pass
    for sd in stream.get("side_data_list") or []:
        if "rotation" in sd:
            try:
                return int(round(float(sd["rotation"]))) % 360
            except (TypeError, ValueError):
                pass
    return 0


def _fraction(s: Any) -> float:
    try:
        a, b = str(s).split("/")
        return float(a) / float(b) if float(b) else 0.0
    except (ValueError, ZeroDivisionError):
        try:
            return float(s)
        except (TypeError, ValueError):
            return 0.0


def parse_ffprobe(doc: Dict[str, Any]) -> Dict[str, Any]:
    """ffprobe's JSON (-show_format -show_streams) -> {format, duration, streams, video: {codec,w,h,fps,rotation}, audio: {codec} | None}. w/h are the DISPLAYED size (rotation applied)."""
    fmt = doc.get("format") or {}
    streams = doc.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)
    out: Dict[str, Any] = {"format": str(fmt.get("format_name") or ""), "duration": float(fmt.get("duration") or (video or {}).get("duration") or 0.0), "streams": len(streams), "video": None, "audio": None}
    if video:
        rot = _rotation(video)
        w, h = int(video.get("width") or 0), int(video.get("height") or 0)
        if rot in (90, 270):
            w, h = h, w
        out["video"] = {"codec": str(video.get("codec_name") or ""), "w": w, "h": h, "fps": _fraction(video.get("avg_frame_rate") or video.get("r_frame_rate")), "rotation": rot}
    if audio:
        out["audio"] = {"codec": str(audio.get("codec_name") or "")}
    return out


_DUR = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")
_VID = re.compile(r"Stream #\S+.*?Video:\s*([A-Za-z0-9_]+).*?,\s*(\d{2,5})x(\d{2,5})")
_FPS = re.compile(r"([\d.]+)\s*fps")
_ROT = re.compile(r"rotation of (-?[\d.]+) degrees|rotate\s*:\s*(-?\d+)")
_INPUT = re.compile(r"Input #0,\s*([^,]+(?:,[a-z0-9_]+)*?),\s*from")


def parse_ffmpeg_text(stderr: str) -> Dict[str, Any]:
    """The same facts from `ffmpeg -i` text (the layer has no ffprobe)."""
    inp = _INPUT.search(stderr)
    d = _DUR.search(stderr)
    dur = int(d.group(1)) * 3600 + int(d.group(2)) * 60 + float(d.group(3)) if d else 0.0
    vm = _VID.search(stderr)
    streams = len(re.findall(r"^\s*Stream #", stderr, flags=re.M))
    out: Dict[str, Any] = {"format": inp.group(1).strip() if inp else "", "duration": dur, "streams": streams, "video": None, "audio": None}
    if vm and not re.search(r"attached pic", stderr):
        line = next((ln for ln in stderr.splitlines() if "Video:" in ln and "Stream #" in ln), "")
        fps = _FPS.search(line)
        rm = _ROT.search(stderr)
        rot = int(round(float(rm.group(1) or rm.group(2)))) % 360 if rm else 0
        w, h = int(vm.group(2)), int(vm.group(3))
        if rot in (90, 270):
            w, h = h, w
        out["video"] = {"codec": vm.group(1).lower(), "w": w, "h": h, "fps": float(fps.group(1)) if fps else 0.0, "rotation": rot}
    am = re.search(r"Stream #\S+.*?Audio:\s*([A-Za-z0-9_]+)", stderr)
    if am:
        out["audio"] = {"codec": am.group(1).lower()}
    return out


def probe(path: str) -> Dict[str, Any]:
    """Facts about the file as the tools see it. Raises Rejected('not_video') when the tools cannot read it at all."""
    fp = ffprobe_bin()
    try:
        if fp:
            proc = _run([fp, "-v", "error", "-protocol_whitelist", "file", "-print_format", "json", "-show_format", "-show_streams", path], timeout=30)
            if proc.returncode != 0:
                raise Rejected("not_video")
            return parse_ffprobe(json.loads(proc.stdout.decode("utf-8", "replace") or "{}"))
        proc = _run([ffmpeg_bin(), "-hide_banner", "-nostdin", "-protocol_whitelist", "file", "-i", path], timeout=30)   # exits 1 (no output file): the facts are in the text
        text = proc.stderr.decode("utf-8", "replace")
        if "Invalid data found" in text or "Stream #" not in text:
            raise Rejected("not_video")
        return parse_ffmpeg_text(text)
    except subprocess.TimeoutExpired:
        raise Rejected("unreadable", "probe timeout") from None
    except ValueError:
        raise Rejected("not_video") from None


def validate(info: Dict[str, Any]) -> Dict[str, Any]:
    """Raises Rejected for anything outside the limits; returns the facts the record keeps: {w, h, source_duration, duration, fps, has_audio, aspect, orientation, container, codec}."""
    fmt = info.get("format") or ""
    if fmt not in V.CONTAINERS_OK:
        raise Rejected("container", fmt[:40])
    v = info.get("video")
    if not v:
        raise Rejected("no_video")
    if v["codec"] not in V.CODECS_OK:
        raise Rejected("codec", str(v["codec"])[:20])
    if int(info.get("streams") or 0) > 8:
        raise Rejected("unreadable", "too many streams")
    w, h = int(v["w"]), int(v["h"])
    if min(w, h) < V.MIN_SIDE:
        raise Rejected("too_small")
    if max(w, h) > V.MAX_SIDE or w * h > V.MAX_PIXELS:
        raise Rejected("too_big", "dimensions")
    dur = float(info.get("duration") or 0.0)
    if dur <= 0.0:
        raise Rejected("unreadable", "no duration")
    if dur > V.MAX_SOURCE_SECONDS:
        raise Rejected("too_long")
    fps = float(v.get("fps") or 0.0)
    if fps > V.MAX_FPS:
        raise Rejected("fps")
    used = min(V.USED_SECONDS, dur)
    return {"w": w, "h": h, "source_duration": round(dur, 2), "duration": round(used, 2), "fps": round(fps, 2) if fps else None, "has_audio": bool(info.get("audio")),
            "aspect": V.aspect_label(w, h), "orientation": V.orientation(w, h), "container": fmt.split(",")[0], "codec": v["codec"]}


# ----------------------------------------------------------------------------- the one kept copy
def mezzanine_scale(w: int, h: int, long_side: int = V.MEZZ_LONG_SIDE) -> Tuple[int, int]:
    """Output size: the same shape, even numbers, the long side at most `long_side`; a smaller clip keeps its own size (never enlarged)."""
    k = min(1.0, long_side / float(max(w, h)))
    return max(2, int(w * k) // 2 * 2), max(2, int(h * k) // 2 * 2)


def transcode(src: str, out: str, info: Dict[str, Any]) -> None:
    """src -> out: H.264 mp4, the FIRST 5 SECONDS only, displayed orientation baked in, <=1080p-class, 30 fps at most, yuv420p, NO audio, NO metadata, faststart.
    Every argument is a constant or a number we computed. Raises Rejected('unreadable') if ffmpeg fails or produces nothing."""
    ow, oh = mezzanine_scale(info["w"], info["h"])
    cmd = [ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-nostdin", "-protocol_whitelist", "file", "-t", f"{V.USED_SECONDS:g}", "-i", src,
           "-map", "0:v:0", "-an", "-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1",
           "-vf", f"scale={ow}:{oh}:flags=lanczos,setsar=1,fps={V.MEZZ_FPS}", "-t", f"{V.USED_SECONDS:g}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p", "-profile:v", "high", "-threads", "2",
           "-fflags", "+bitexact", "-flags:v", "+bitexact", "-movflags", "+faststart", "-fs", str(20_000_000), "-f", "mp4", out]
    try:
        proc = _run(cmd)
    except subprocess.TimeoutExpired:
        raise Rejected("unreadable", "transcode timeout") from None
    if proc.returncode != 0 or not os.path.exists(out) or os.path.getsize(out) < 1000:
        raise Rejected("unreadable", "transcode failed")


def extract_audio(src: str, out: str) -> bool:
    """The first 5 s of the clip's sound as a small AAC file (mono, 24 kHz, no metadata). False when there is no usable sound (no stream, silent decode failure)."""
    cmd = [ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-nostdin", "-protocol_whitelist", "file", "-t", f"{V.USED_SECONDS:g}", "-i", src,
           "-map", "0:a:0", "-vn", "-sn", "-dn", "-map_metadata", "-1", "-map_chapters", "-1", "-ac", "1", "-ar", "24000", "-c:a", "aac", "-b:a", "48k",
           "-t", f"{V.USED_SECONDS:g}", "-fflags", "+bitexact", "-movflags", "+faststart", "-f", "mp4", out]
    try:
        proc = _run(cmd)
    except subprocess.TimeoutExpired:
        return False
    return proc.returncode == 0 and os.path.exists(out) and os.path.getsize(out) > 500


# ----------------------------------------------------------------------------- frames
ANALYSIS_FPS = 10        # the change detector looks at 10 small grey pictures a second
GRID_W, GRID_H = 32, 18
MAX_FRAMES = 9           # the most frames ever sent to a model for one clip (cost cap)
MAX_PEAKS = 3            # the most change moments picked; each gives the frame before and the frame after the change
PEAK_SPACING_S = 0.4     # two picked changes are at least this far apart
MIN_CHANGE = 8.0         # mean grey-level difference (0-255) between consecutive pictures below which nothing counts as a change (a static or slowly moving clip has none)


def change_scores(path: str, duration: float) -> List[float]:
    """scores[i] = mean absolute grey difference between analysis picture i and i-1 (scores[0] = 0), pictures taken at 10 per second from the start. Deterministic: the same file
    always gives the same list (fixed decode, fixed 32x18 area-averaged grey frames)."""
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-nostdin", "-protocol_whitelist", "file", "-t", f"{max(0.2, duration):.2f}", "-i", path, "-an",
           "-vf", f"fps={ANALYSIS_FPS},scale={GRID_W}:{GRID_H}:flags=area,format=gray", "-f", "rawvideo", "-"]
    proc = _run(cmd, timeout=40)
    size = GRID_W * GRID_H
    raw = proc.stdout
    pics = [raw[i:i + size] for i in range(0, len(raw) - size + 1, size)]
    out = [0.0]
    for prev, cur in zip(pics, pics[1:]):
        out.append(sum(abs(x - y) for x, y in zip(prev, cur)) / float(size))
    return out


def choose_times(duration: float, scores: Sequence[float], total: int = MAX_FRAMES) -> List[float]:
    """Which moments go to the checks AND the description (the same frames for both), chosen by the picture itself, never at random:
      1  the first frame and the last frame, always
      2  the top change moments (hard cuts, a sudden flash or new content): the frame just BEFORE and just AFTER each, at most MAX_PEAKS, at least PEAK_SPACING_S apart,
         only scores >= MIN_CHANGE; ties broken by the earlier time
      3  the rest evenly spaced over the clip (this is all there is for a static clip: first, last and 7 evenly spaced)
    At most `total` times, sorted, distinct (>= 0.2 s apart). Pure function of (duration, scores): reproducible and cacheable by the file's hash."""
    d = max(0.2, float(duration))
    last = round(max(0.0, d - 0.05), 2)
    times = {0.0, last}
    ranked = sorted(((-s, i) for i, s in enumerate(scores) if i > 0 and s >= MIN_CHANGE))
    picked: List[float] = []
    for _neg, i in ranked:
        t = i / float(ANALYSIS_FPS)
        if t > last or any(abs(t - p) < PEAK_SPACING_S for p in picked):
            continue
        picked.append(t)
        if len(picked) >= MAX_PEAKS:
            break
    for t in sorted(picked):
        for x in (round(max(0.0, t - 1.0 / ANALYSIS_FPS), 2), round(min(last, t), 2)):
            if len(times) < total - 1:
                times.add(x)
    for n in (8, 16, 32):   # fill: evenly spaced, coarse grid first, skipping what is too close to a chosen frame
        for j in range(n + 1):
            t = round(last * j / n, 2)
            if len(times) < total and all(abs(t - x) >= 0.2 for x in times):
                times.add(t)
    return sorted(times)[:total]


def select_times(path: str, duration: float, total: int = MAX_FRAMES) -> List[float]:
    try:
        scores = change_scores(path, duration)
    except Exception:   # noqa: BLE001 - no scores: the fixed fallback frames (still deterministic)
        scores = []
    return choose_times(duration, scores, total)


def frame_jpeg(path: str, t: float, side: int = 512) -> bytes:
    """One frame at time t as a JPEG whose long side is at most `side`."""
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-nostdin", "-protocol_whitelist", "file", "-ss", f"{max(0.0, t):.2f}", "-i", path, "-frames:v", "1",
           "-vf", f"scale='if(gt(iw,ih),min({side},iw),-2)':'if(gt(iw,ih),-2,min({side},ih))'", "-q:v", "4", "-f", "image2pipe", "-vcodec", "mjpeg", "-"]
    proc = _run(cmd, timeout=30)
    if proc.returncode != 0 or len(proc.stdout) < 200:
        raise Rejected("unreadable", "frame")
    return proc.stdout


def frames(path: str, times: Sequence[float], side: int = 512) -> List[Tuple[float, bytes]]:
    out = []
    for t in times:
        try:
            out.append((t, frame_jpeg(path, t, side)))
        except Rejected:
            continue   # a moment past the last decodable frame: the others still count
    if len(out) < 3:
        raise Rejected("unreadable", "too few frames")
    return out


def contact_sheet(samples: Sequence[Tuple[float, bytes]], cell: int = 400, cols: int = 3) -> bytes:
    """One JPEG with the sampled frames in a grid (cells fit in cell x cell, each labelled with its time). This is the only picture the checking model is given."""
    from PIL import Image, ImageDraw
    ims = []
    for t, raw in samples:
        im = Image.open(io.BytesIO(raw)).convert("RGB")
        im.thumbnail((cell, cell))
        ims.append((t, im))
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * cell, rows * cell), (20, 20, 20))
    for i, (t, im) in enumerate(ims):
        x, y = (i % cols) * cell + (cell - im.width) // 2, (i // cols) * cell + (cell - im.height) // 2
        sheet.paste(im, (x, y))
        d = ImageDraw.Draw(sheet)
        label = f"{t:.1f}s"
        d.rectangle((x, y, x + 8 * len(label) + 8, y + 16), fill=(0, 0, 0))
        d.text((x + 4, y + 2), label, fill=(255, 255, 255))
    buf = io.BytesIO()
    sheet.save(buf, "JPEG", quality=80, optimize=True)
    return buf.getvalue()


def poster(raw: bytes, side: int = 360) -> bytes:
    from PIL import Image
    im = Image.open(io.BytesIO(raw)).convert("RGB")
    im.thumbnail((side, side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=76, optimize=True)   # re-encoded: no metadata carried over
    return buf.getvalue()
