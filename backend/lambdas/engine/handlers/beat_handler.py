"""Step 2 (fan-out per beat): synthesize narration + fetch a licensed photo if the scene needs one."""
import io
from typing import Any, Dict

import numpy as np

from common.secrets import get_secret_param

from .. import assets, audio, awsio, costs, tts


def _provider(cfg: Dict[str, Any]):
    name = (cfg.get("provider") or "gemini").lower()
    key = "" if name == "mock" else get_secret_param(f"/videomk/{name}_api_key")
    if name != "mock" and not key:
        raise RuntimeError(f"missing API key for TTS provider {name}")
    return tts.get_provider(name, key)


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    video_id, i = str(event["video_id"]), int(event["i"])
    pfx = awsio.prefix(video_id)
    plan = awsio.get_json(pfx + "plan.json")
    beat = plan["beats"][i]
    cfg = plan.get("tts", {})

    provider = _provider(cfg)
    text = beat["narration"]
    costs.add_cost(video_id, len(text) * costs.TTS_PER_CHAR.get(provider.name, 0.00002))
    samples = tts.synth_beat(provider, text, voice=cfg.get("voice", ""), style=cfg.get("style", ""))
    if samples.size < audio.SR * 0.3:
        raise RuntimeError("TTS returned (almost) no audio")
    wav_key = f"{pfx}audio/beat_{i:03d}.wav"
    buf = io.BytesIO()
    import wave
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(audio.SR)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
    awsio.put_bytes(wav_key, buf.getvalue(), "audio/wav")

    out: Dict[str, Any] = {"i": i, "duration": round(samples.size / audio.SR, 3)}
    scene = beat["scene"]
    if scene["type"] == "image":
        found = assets.scout(scene["props"]["image_query"])
        if found:
            jpeg, entry = found
            key = f"{pfx}assets/img_{i:03d}.jpg"
            awsio.put_bytes(key, jpeg, "image/jpeg")
            out.update({"asset": key, "credit": assets.credit_line(entry), "ledger": entry})
    return out
