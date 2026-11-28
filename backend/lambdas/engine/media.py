"""ffmpeg plumbing: encode a frame range to a segment, stitch segments with -c copy, mix audio, mux.

Segments are MPEG-TS with a fixed GOP and closed GOPs, so any number of independently rendered
chunks concatenate byte-for-byte with `-c copy` (no re-encode, seconds not minutes).
"""
import os
import shutil
import subprocess
import tempfile
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


def ffmpeg_bin() -> str:
    env = os.environ.get("FFMPEG_BIN")
    if env and os.path.exists(env):
        return env
    try:  # bundled static binary shipped by the layer (imageio-ffmpeg wheel)
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    found = shutil.which("ffmpeg")
    if not found:
        raise RuntimeError("ffmpeg not found (set FFMPEG_BIN or add imageio-ffmpeg to the layer)")
    return found


def ffprobe_duration(path: str) -> float:
    """Duration via ffmpeg itself (a static ffprobe is not bundled in the layer)."""
    proc = subprocess.run([ffmpeg_bin(), "-hide_banner", "-i", path], capture_output=True, text=True)
    for line in proc.stderr.splitlines():
        if "Duration:" in line:
            h, m, s = line.split("Duration:")[1].split(",")[0].strip().split(":")
            return int(h) * 3600 + int(m) * 60 + float(s)
    raise RuntimeError(f"could not read duration of {path}")


UHD_PIXELS = 2560 * 1440   # a frame with more pixels than this is encoded with the 4K settings (docs/FOUR_K.md)
UHD_CRF = int(os.environ.get("UHD_CRF", "21"))
UHD_PRESET = os.environ.get("UHD_PRESET", "veryfast")
UHD_MAXRATE_K = int(os.environ.get("UHD_MAXRATE_K", "24000"))   # a ceiling for busy footage: bounds the file (12 min <= about 2.2 GB) without touching ordinary scenes


def encode_settings(width: int, height: int, draft: bool = False) -> Dict[str, Any]:
    """The x264 settings for a frame size. Up to 1080p: exactly what it always was (CRF 20 veryfast, draft CRF 28 ultrafast; profile and level left to x264).
    4K: High profile at level 5.1 (3840x2160 at 30 fps; every player and platform that takes 4K H.264 takes it), CRF 21 with a bitrate ceiling."""
    if draft:
        return {"crf": 28, "preset": "ultrafast", "extra": []}
    if width * height > UHD_PIXELS:
        return {"crf": UHD_CRF, "preset": UHD_PRESET,
                "extra": ["-profile:v", "high", "-level:v", "5.1", "-maxrate", f"{UHD_MAXRATE_K}k", "-bufsize", f"{UHD_MAXRATE_K * 2}k"]}
    return {"crf": 20, "preset": "veryfast", "extra": []}


def encode_segment(
    frames: Iterable[bytes],
    out_path: str,
    *,
    width: int,
    height: int,
    fps: int,
    start_time: float,
    gop: int,
    crf: int = 20,
    preset: str = "veryfast",
    threads: int = 0,
    extra: Sequence[str] = (),
) -> int:
    """Encode raw rgb24 frames into an MPEG-TS segment whose timestamps start at `start_time`. `extra`: more encoder options (4K: profile, level, bitrate ceiling)."""
    cmd = [
        ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}", "-r", str(fps), "-i", "-",
        "-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p", *extra,
        "-g", str(gop), "-keyint_min", str(gop), "-sc_threshold", "0", "-bf", "2",
        "-x264-params", "open-gop=0", "-threads", str(threads),
        "-output_ts_offset", f"{start_time:.6f}", "-muxdelay", "0", "-muxpreload", "0",
        "-f", "mpegts", out_path,
    ]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    n = 0
    try:
        assert proc.stdin is not None
        for fr in frames:
            proc.stdin.write(fr)
            n += 1
        proc.stdin.close()
    except BrokenPipeError:
        pass
    err = proc.stderr.read().decode("utf-8", "replace") if proc.stderr else ""
    if proc.wait() != 0:
        raise RuntimeError(f"ffmpeg encode failed: {err[-800:]}")
    return n


def mux_final(segments: Sequence[str], audio_path: Optional[str], out_path: str, *, fps: int) -> None:
    """Concatenate TS segments (stream copy) and mux the mixed audio into a faststart MP4."""
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False) as lst:
        for s in segments:
            lst.write(f"file '{s}'\n")
        list_path = lst.name
    try:
        cmd = [ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", list_path]
        if audio_path:
            cmd += ["-i", audio_path, "-map", "0:v:0", "-map", "1:a:0", "-c:a", "copy", "-shortest"]
        else:
            cmd += ["-map", "0:v:0"]
        cmd += ["-c:v", "copy", "-movflags", "+faststart", out_path]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg mux failed: {proc.stderr[-800:]}")
    finally:
        os.unlink(list_path)


def mix_audio(
    narration_wav: str,
    music_wav: Optional[str],
    sfx_wav: Optional[str],
    out_path: str,
    *,
    duration: float,
    music_volume: float = 0.22,
    duck: bool = True,
    swells: Sequence[Tuple[float, float]] = (),
    swell_gain: float = 2.2,
    loudness_lufs: Optional[float] = None,
    clip_wav: Optional[str] = None,
    clip_volume: float = 0.85,
) -> None:
    """(`clip_wav`: the person's own clips' sound, already placed on the timeline, ducked under the narration like the music; docs/VIDEO_UPLOAD_2026-11-28.md.)
    Narration + (ducked) music + sfx -> AAC. Music is faded in/out and ducked under speech. With `loudness_lufs` the whole mix is levelled to that integrated
    loudness (EBU R128, true peak -1.5 dB): -14 is what YouTube plays at, so a video neither jumps nor gets turned down when it is published."""
    inputs = ["-i", narration_wav]
    graph: List[str] = []
    labels = ["[nar]"]
    taps = (["[nar_sc]"] if (music_wav and duck) else []) + (["[nar_sc2]"] if clip_wav else [])   # copies of the narration that the music and the clip sound listen to
    graph.append(f"[0:a]aresample=44100,aformat=channel_layouts=stereo,asplit={1 + len(taps)}[nar]{''.join(taps)}" if taps else "[0:a]aresample=44100,aformat=channel_layouts=stereo[nar]")
    idx = 1
    if music_wav:
        inputs += ["-stream_loop", "-1", "-i", music_wav]
        fade_out_at = max(0.0, duration - 2.5)
        # while nobody is speaking (a silent beat) the music comes up, with 0.8 s ramps so it breathes in and out
        lift = "".join(f",volume='1+({swell_gain}-1)*clip(min((t-{a:.3f})/0.8,({b:.3f}-t)/0.8),0,1)':eval=frame" for a, b in swells if b - a > 1.0)
        graph.append(
            f"[{idx}:a]aresample=44100,aformat=channel_layouts=stereo,volume={music_volume}{lift},atrim=0:{duration:.3f},"
            f"afade=t=in:d=1.5,afade=t=out:st={fade_out_at:.3f}:d=2.5[mus]"
        )
        if duck:
            graph.append("[mus][nar_sc]sidechaincompress=threshold=0.02:ratio=10:attack=15:release=450:makeup=1[musd]")
            labels.append("[musd]")
        else:
            labels.append("[mus]")
        idx += 1
    if sfx_wav:
        inputs += ["-i", sfx_wav]
        graph.append(f"[{idx}:a]aresample=44100,aformat=channel_layouts=stereo[sfx]")
        labels.append("[sfx]")
        idx += 1
    if clip_wav:
        inputs += ["-i", clip_wav]
        graph.append(f"[{idx}:a]aresample=44100,aformat=channel_layouts=stereo,volume={clip_volume}[clp]")
        graph.append("[clp][nar_sc2]sidechaincompress=threshold=0.02:ratio=6:attack=15:release=300:makeup=1[clpd]")
        labels.append("[clpd]")
        idx += 1
    level = f",loudnorm=I={loudness_lufs:g}:TP=-1.5:LRA=11,aresample=44100" if loudness_lufs is not None else ""
    graph.append(f"{''.join(labels)}amix=inputs={len(labels)}:duration=first:normalize=0{level},alimiter=limit=0.95,atrim=0:{duration:.3f}[out]")
    cmd = [ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", *inputs, "-filter_complex", ";".join(graph), "-map", "[out]",
           "-c:a", "aac", "-b:a", "192k", out_path]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg audio mix failed: {proc.stderr[-800:]}")


def extract_frame(video_path: str, t: float, out_png: str) -> None:
    proc = subprocess.run([ffmpeg_bin(), "-y", "-hide_banner", "-loglevel", "error", "-ss", f"{t:.3f}", "-i", video_path, "-frames:v", "1", out_png],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr[-400:])
