"""Step 2 (fan-out per beat): narration audio + licensed photo, both content-addressed so edits only redo what changed."""
import io
import hashlib
import logging
import wave
from typing import Any, Dict, Optional

import numpy as np

from common.secrets import get_secret_param

from ..scenes import ELEMENTS
from ..scenes.registry import PrepareCtx
from .. import align, assets, audio, awsio, clips, costs, plan as plan_mod, stock, timeline as timeline_mod, tts, voices


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


MIN_ALIGN_CONFIDENCE = 0.6


def _store_words(key: str, samples: np.ndarray, text: str) -> bool:
    """Word timings measured from the audio itself (free, a few ms). Not stored when the audio's pauses and the text's punctuation disagree: the timeline then
    keeps the proportional estimate rather than a wrong measurement."""
    try:
        words, conf = align.align_words(samples, audio.SR, text)
        if words and conf >= MIN_ALIGN_CONFIDENCE:
            awsio.put_json(key, {"words": [list(w) for w in words], "conf": conf})
            return True
    except Exception:
        logging.exception("word alignment failed")
    return False


def _wav_samples(data: bytes) -> np.ndarray:
    with wave.open(io.BytesIO(data), "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0


def _context(beat: Dict[str, Any]) -> str:
    """What the stock reviewers are told the picture is for: the narration, or for a silent beat the scene's own description."""
    if beat.get("narration"):
        return beat["narration"]
    p = beat["scene"]["props"]
    return str(p.get("alt") or p.get("image_query") or p.get("clip_query") or " ".join(p.get("image_queries") or []))


def make_audio(plan: Dict[str, Any], beat: Dict[str, Any], video_id: str, cost_field: str) -> Dict[str, Any]:
    if beat.get("silent"):  # a pause: no synthesis, no cost; the duration is how long the picture is held
        return {"tts_hash": plan_mod.tts_hash(plan, beat), "audio_key": None, "duration": round(float(beat.get("hold") or plan_mod.DEFAULT_HOLD_S), 3), "silent": True}
    pfx = awsio.prefix(video_id)
    h = plan_mod.tts_hash(plan, beat)
    key = f"{pfx}audio/{h}.wav"
    wkey = f"{pfx}audio/{h}.words.json"
    cached = awsio.head(key)
    if cached and (cached.get("Metadata") or {}).get("duration"):
        out = {"tts_hash": h, "audio_key": key, "duration": float(cached["Metadata"]["duration"]), "voice": voices.beat_voice(plan, beat)}
        if awsio.head(wkey) or _store_words(wkey, _wav_samples(awsio.get_bytes(key)), beat["narration"]):   # audio made before alignment existed: measure it now
            out["words_key"] = wkey
        return out
    cfg = plan.get("tts", {})
    provider = _provider(cfg)
    text = beat["narration"]
    costs.add_cost(video_id, len(text) * (getattr(provider, "cost_per_char", None) or costs.TTS_PER_CHAR.get(provider.name, 0.00002)), field=cost_field, part="speech")
    voice = voices.beat_voice(plan, beat)
    samples = tts.synth_beat(provider, text, voice=voice, style=cfg.get("style", ""))
    if samples.size < audio.SR * 0.3:
        raise RuntimeError("TTS returned (almost) no audio")
    dur = round(samples.size / audio.SR, 3)
    awsio.put_bytes_meta(key, _wav_bytes(samples), "audio/wav", {"duration": str(dur)})
    out = {"tts_hash": h, "audio_key": key, "duration": dur, "voice": voice}
    if _store_words(wkey, samples, text):
        out["words_key"] = wkey
    return out


def make_photo(plan: Dict[str, Any], beat: Dict[str, Any], video_id: str, cost_field: str) -> Dict[str, Any]:
    pfx = awsio.prefix(video_id)
    props = beat["scene"]["props"]
    query, pick = props["image_query"], beat.get("pick")
    out: Dict[str, Any] = {"query": query, "pick": pick}
    if props.get("photo"):  # the user's own photo: no search, no credit line, nothing to review
        item = next((m for m in plan.get("media_items") or [] if m.get("id") == props["photo"]), None)
        if item and str(item.get("key", "")).startswith(pfx + "assets/"):
            out.update({"asset": item["key"], "photo": props["photo"]})
            return out
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
        result = stock.scout_reviewed(query, _context(beat), props.get("alt", ""), unsplash_key=unsplash_key)
        if result:
            costs.add_cost(video_id, float(result.get("review", {}).get("cost_usd", 0.0)), field=cost_field, part="stock")
            if result.get("candidates"):
                awsio.put_json(cands_key, {"query": query, "candidates": result["candidates"]})
    if result and result.get("jpeg"):
        key = f"{pfx}assets/img_{beat['id']}_{hashlib.sha1(result['jpeg']).hexdigest()[:8]}.jpg"
        awsio.put_bytes(key, result["jpeg"], "image/jpeg")
        out.update({"asset": key, "credit": result["credit"], "ledger": result["entry"], "chosen": result["chosen"]})
    else:
        out["no_photo"] = True  # nothing suitable: the timeline degrades this scene to a title card; the editor can still offer candidates
    return out


def make_gallery(plan: Dict[str, Any], beat: Dict[str, Any], video_id: str, cost_field: str) -> Dict[str, Any]:
    """One licensed photograph per query, fetched in parallel (each is searched and reviewed like a single image scene). Queries that find nothing are dropped."""
    from concurrent.futures import ThreadPoolExecutor

    props = beat["scene"]["props"]
    queries = list(props["image_queries"])
    if props.get("photos"):   # the user's own photos: their clean copies are already stored; no search, no credit line, nothing to review, no cost
        items = {m["id"]: m for m in plan.get("media_items") or []}
        shots = [{"asset": items[i]["key"], "credit": "", "query": queries[k] if k < len(queries) else i, "photo": i} for k, i in enumerate(props["photos"]) if i in items]
        out = {"query": "|".join(queries), "photos": list(props["photos"]), "pick": None, "gallery": shots}
        if not shots:
            out["no_photo"] = True
        return out

    def one(i: int) -> Dict[str, Any]:
        still = {"id": f"{beat['id']}g{i}", "narration": _context(beat), "scene": {"type": "image", "props": {"image_query": queries[i], "alt": queries[i]}}}
        try:
            return make_photo(plan, still, video_id, cost_field)
        except Exception:
            return {}

    with ThreadPoolExecutor(max_workers=min(4, len(queries))) as ex:
        results = list(ex.map(one, range(len(queries))))
    shots = [{"asset": r["asset"], "credit": r.get("credit", ""), "ledger": r.get("ledger"), "chosen": r.get("chosen"), "query": queries[i]} for i, r in enumerate(results) if r.get("asset")]
    out: Dict[str, Any] = {"query": "|".join(queries), "pick": None, "gallery": shots}
    if not shots:
        out["no_photo"] = True
    return out


def make_clip(plan: Dict[str, Any], beat: Dict[str, Any], video_id: str, cost_field: str, speech: float) -> Dict[str, Any]:
    """A short licensed stock clip for the beat. If none is found or usable, a still photo of the same subject, so the video never has a hole."""
    pfx = awsio.prefix(video_id)
    props = beat["scene"]["props"]
    query = props["clip_query"]
    out: Dict[str, Any] = {"query": query, "pick": None}
    need = timeline_mod.LEAD + speech + timeline_mod.TAIL + 0.6  # the scene's length, with a little margin for the crossfade
    keys = {"pexels_key": get_secret_param("/videomk/pexels_api_key", quiet=True), "pixabay_key": get_secret_param("/videomk/pixabay_api_key", quiet=True)}
    fr = plan.get("frame") or {}   # vertical and square videos ask the stock libraries for portrait or square footage; landscape calls are exactly as before
    orient = "portrait" if fr.get("aspect") in ("9:16", "4:5") else "square" if fr.get("aspect") == "1:1" else str(fr.get("orientation") or "landscape")
    keys = {**keys, **({"orientation": orient} if orient in ("portrait", "square") else {})}
    result = clips.scout_clip(query, _context(beat), props.get("alt", ""), need_seconds=need, **keys)
    if result:
        costs.add_cost(video_id, float(result.get("review", {}).get("cost_usd", 0.0)), field=cost_field, part="stock")
    alt = str(props.get("alt") or "").strip()
    if (not result or not result.get("mp4")) and alt and alt.lower() != query.lower():  # the planner's second wording often finds what the first did not
        second = clips.scout_clip(alt, _context(beat), alt, need_seconds=need, **keys)
        if second:
            costs.add_cost(video_id, float(second.get("review", {}).get("cost_usd", 0.0)), field=cost_field, part="stock")
        if second and second.get("mp4"):
            result = second
    if result and result.get("mp4"):
        key = f"{pfx}assets/clip_{beat['id']}_{hashlib.sha1(result['mp4']).hexdigest()[:8]}.mp4"
        try:
            awsio.put_bytes(key, result["mp4"], "video/mp4", working=True)
            out.update({"clip_asset": key, "credit": result["credit"], "ledger": result["entry"], "chosen": result["chosen"]})
            return out
        except Exception:  # storing the clip failed: a still photo keeps the beat visual, the video is not lost
            logging.exception("could not store clip %s", key)
    still = {"id": beat["id"], "narration": _context(beat), "scene": {"type": "image", "props": {"image_query": query, "alt": props.get("alt", query), **({"word": props["word"]} if props.get("word") else {})}}}
    out.update({k: v for k, v in make_photo(plan, still, video_id, cost_field).items() if k not in ("query", "pick")})
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
    elif beat["scene"]["type"] == "gallery":
        media.update(make_gallery(plan, beat, video_id, cost_field))
    elif beat["scene"]["type"] == "clip":
        media.update(make_clip(plan, beat, video_id, cost_field, float(media["duration"])))
    else:
        el = ELEMENTS.get(beat["scene"]["type"])
        if el is not None and el.prepare is not None:   # an element that needs outside data (a map's places, ...): a failure falls back, it never fails the video
            try:
                patch = el.prepare(dict(beat["scene"]["props"]), PrepareCtx(video_id=video_id, beat_id=beat_id, narration=beat.get("narration", ""), duration=float(media["duration"]),
                                                                            sources=plan.get("sources") or [], language=plan.get("language", "en"), region=plan.get("region"),
                                                                            media_items=plan.get("media_items") or []))
                media["element"] = patch if isinstance(patch, dict) else {}
            except Exception:
                logging.exception("element %s could not prepare beat %s", el.name, beat_id)
                media["element_failed"] = True
    return {"id": beat_id, "media": media}
