"""Step 4b (parallel to rendering): narration + generated music + sfx -> one AAC track."""
import logging
import os
import tempfile
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict

import numpy as np

from .. import audio, awsio, library, pipeline


def _load_wav(key: str, tmp: str):
    path = os.path.join(tmp, os.path.basename(key))
    awsio.download(key, path)
    samples, sr = audio.read_wav(path)
    return samples if sr == audio.SR else np.interp(np.linspace(0, samples.size - 1, int(samples.size * audio.SR / sr)), np.arange(samples.size), samples).astype(np.float32)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    video_id, rev = str(event["video_id"]), int(event.get("rev", 1))
    pfx = awsio.prefix(video_id)
    tl = awsio.get_json(event["timeline_key"])
    prefix_audio = pfx + "audio/"
    keys = [sc.get("audio_key") for sc in tl["scenes"]]
    spoken = [k for k in keys if k is not None]   # silent beats have none
    if len(spoken) != sum(1 for sc in tl["scenes"] if not sc.get("silent")) or not all(isinstance(k, str) and k.startswith(prefix_audio) and ".." not in k for k in spoken):
        raise ValueError("timeline references audio outside this video")
    with tempfile.TemporaryDirectory() as tmp:
        with ThreadPoolExecutor(max_workers=8) as ex:
            loaded = dict(zip(spoken, ex.map(lambda k: _load_wav(k, tmp), spoken)))
        beats = [loaded[k] if k is not None else None for k in keys]
        out = os.path.join(tmp, "mix.m4a")
        wanted = {s["track"] for s in (tl.get("music") or {}).get("segments", []) if s.get("track")}
        tracks: Dict[str, Any] = {}
        for tid in wanted:  # the library tracks this video uses (a missing or unreadable one falls back to the synth)
            try:
                path = os.path.join(tmp, f"track_{tid}.mp3")
                awsio.download(library.track_key(tid), path)
                tracks[tid] = library.decode(path)
            except Exception:
                logging.warning("music track %s is unavailable; the synth stands in", tid)
        pipeline.make_audio(tl, beats, out, track_loader=tracks.get)
        key = f"{pfx}audio/mix_r{rev}_{event.get('mode', 'final')}.m4a"
        awsio.upload(out, key, "audio/mp4", working=True)
    return {"key": key}
