"""Step 2 (fan-out per beat): narration audio + licensed photo, both content-addressed so edits only redo what changed."""
import io
import hashlib
import wave
from typing import Any, Dict, Optional

import numpy as np

from common.secrets import get_secret_param

from .. import assets, audio, awsio, costs, plan as plan_mod, stock, tts


def _provider(cfg: Dict[str, Any]):
    name = (cfg.get("provider") or "polly").lower()
    keyless = name in ("mock", "polly")  # polly authenticates with the Lambda's IAM role
    key = "" if keyless else get_secret_param(f"/videomk/{name}_api_key")
    if not keyless and not key:
        raise RuntimeError(f"missing API key for TTS provider {name}")
    return tts.get_provider(name, key, cfg)


def _wav_bytes(samples: np.ndarray) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(audio.SR)
        w.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
    return buf.getvalue()


def make_audio(plan: Dict[str, Any], beat: Dict[str, Any], video_id: str, cost_field: str) -> Dict[str, Any]:
    pfx = awsio.prefix(video_id)
    h = plan_mod.tts_hash(plan, beat)
    key = f"{pfx}audio/{h}.wav"
    cached = awsio.head(key)
    if cached and (cached.get("Metadata") or {}).get("duration"):
        return {"tts_hash": h, "audio_key": key, "duration": float(cached["Metadata"]["duration"])}
    cfg = plan.get("tts", {})
    provider = _provider(cfg)
    text = beat["narration"]
    costs.add_cost(video_id, len(text) * (getattr(provider, "cost_per_char", None) or costs.TTS_PER_CHAR.get(provider.name, 0.00002)), field=cost_field)
    samples = tts.synth_beat(provider, text, voice=cfg.get("voice", ""), style=cfg.get("style", ""))
    if samples.size < audio.SR * 0.3:
        raise RuntimeError("TTS returned (almost) no audio")
    dur = round(samples.size / audio.SR, 3)
    awsio.put_bytes_meta(key, _wav_bytes(samples), "audio/wav", {"duration": str(dur)})
    return {"tts_hash": h, "audio_key": key, "duration": dur}


def make_photo(plan: Dict[str, Any], beat: Dict[str, Any], video_id: str, cost_field: str) -> Dict[str, Any]:
    pfx = awsio.prefix(video_id)
    props = beat["scene"]["props"]
    query, pick = props["image_query"], beat.get("pick")
    out: Dict[str, Any] = {"query": query, "pick": pick}
    unsplash_key = get_secret_param("/videomk/unsplash_access_key", quiet=True)
    cands_key = f"{pfx}assets/cands_{beat['id']}.json"

    result: Optional[Dict[str, Any]] = None
    if pick:  # a human chose this exact candidate in the editor
        try:
            cands = awsio.get_json(cands_key).get("candidates", [])
            chosen = next((c for c in cands if stock.candidate_key(c) == pick), None)
            if chosen:
                jpeg, _ = assets.to_jpeg(stock.fetch_full(chosen))
                stock.track_download(chosen, unsplash_key)
                result = {"jpeg": jpeg, "entry": stock.ledger_entry(chosen), "credit": stock.credit_line(chosen), "chosen": pick, "candidates": cands, "review": {}}
        except Exception:
            result = None
    if result is None:
        result = stock.scout_reviewed(query, beat["narration"], props.get("alt", ""), unsplash_key=unsplash_key)
        if result:
            costs.add_cost(video_id, float(result.get("review", {}).get("cost_usd", 0.0)), field=cost_field)
            if result.get("candidates"):
                awsio.put_json(cands_key, {"query": query, "candidates": result["candidates"]})
    if result and result.get("jpeg"):
        key = f"{pfx}assets/img_{beat['id']}_{hashlib.sha1(result['jpeg']).hexdigest()[:8]}.jpg"
        awsio.put_bytes(key, result["jpeg"], "image/jpeg")
        out.update({"asset": key, "credit": result["credit"], "ledger": result["entry"], "chosen": result["chosen"]})
    else:
        out["no_photo"] = True  # nothing suitable: the timeline degrades this scene to a title card; the editor can still offer candidates
    return out


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    video_id, beat_id = str(event["video_id"]), str(event["beat_id"])
    cost_field = str(event.get("cost_field") or "cost_usd")
    plan = awsio.get_json(event["plan_key"])
    beat = next((b for b in plan["beats"] if b["id"] == beat_id), None)
    if beat is None:
        raise ValueError(f"beat {beat_id} not in plan")
    media = make_audio(plan, beat, video_id, cost_field)
    if beat["scene"]["type"] == "image":
        media.update(make_photo(plan, beat, video_id, cost_field))
    return {"id": beat_id, "media": media}
