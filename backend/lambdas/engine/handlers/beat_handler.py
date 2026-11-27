"""Step 2 (fan-out per beat): narration audio + licensed photo, both content-addressed so edits only redo what changed."""
import io
import hashlib
import logging
import time
import wave
from typing import Any, Dict, Optional

import numpy as np

from common.secrets import get_secret_param

from ..scenes import ELEMENTS
from ..scenes.registry import PrepareCtx
from common import clip_config

from .. import align, assets, audio, awsio, catalog_pick, clip_ondemand, clips, costs, image_ondemand, format_options, making_progress, plan as plan_mod, register, stock, timeline as timeline_mod, tts, voices


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


def settle_register(plan: Dict[str, Any], beat: Dict[str, Any], video_id: str, samples: np.ndarray, again: Any, *, wait_s: Optional[float] = None, sleep: Any = time.sleep) -> tuple:
    """One register for a speaker across the scenes of a video (engine/register.py). The median pitch of this first take is written next to the audio; when it
    lies outside the band around the speaker's register (known from the first takes of the speaker's other beats, which their own functions write), the beat is
    said again with `again()` (a new take; at most register.retakes() times) and the take nearest the register is kept. -> (samples, record or None): the
    record {"hz", "ref", "first_hz", "takes"} goes into the beat's media. Never raises for a reason of its own: on any doubt the first take stands."""
    pfx = awsio.prefix(video_id)
    first = register.median_pitch(samples, audio.SR)
    if not first:
        return samples, None
    awsio.put_json(f"{pfx}audio/{plan_mod.tts_hash(plan, beat)}.f0.json", {"hz": first})   # the FIRST take, whatever is kept: every beat judges against first takes, so all judge alike
    others = [f"{pfx}audio/{plan_mod.tts_hash(plan, b)}.f0.json" for b in register.peers(plan, beat)]
    if not others:
        return samples, {"hz": first, "takes": 1}
    need, found = min(len(others), register.PEERS), {}
    deadline = time.time() + (register.WAIT_S if wait_s is None else wait_s)
    while True:   # the other beats are being said at this moment by their own functions: a short wait for enough of them
        for k in others:
            if k not in found:
                try:
                    found[k] = float(awsio.get_json(k)["hz"])
                except Exception:
                    pass
        if len(found) >= need or time.time() >= deadline:
            break
        sleep(0.4)
    ref = register.reference([first] + list(found.values()))
    if not ref or register.off(first, ref, beat["narration"]) <= 0:
        return samples, {"hz": first, **({"ref": round(ref, 1)} if ref else {}), "takes": 1}
    takes = [{"hz": first, "samples": samples}]
    for _ in range(register.retakes()):
        new = again()
        if new is None or new.size < audio.SR * 0.3:
            break
        takes.append({"hz": register.median_pitch(new, audio.SR), "samples": new})
        if takes[-1]["hz"] and register.off(takes[-1]["hz"], ref, beat["narration"]) <= 0:
            break
    best = takes[register.choose(takes, ref)]
    logging.info("REGISTER beat=%s voice=%s ref=%.0f first=%.0f kept=%.0f takes=%s", beat.get("id"), voices.beat_voice(plan, beat), ref, first, best["hz"] or 0, len(takes))
    return best["samples"], {"hz": best["hz"], "ref": round(ref, 1), "first_hz": first, "takes": len(takes)}


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
    reg = None
    if register.applies(plan, beat):   # a lively voice: one register from scene to scene (a beat far from it is said again; the retakes are paid like any speech)
        def again() -> Optional[np.ndarray]:
            costs.add_cost(video_id, len(text) * (getattr(provider, "cost_per_char", None) or costs.TTS_PER_CHAR.get(provider.name, 0.00002)), field=cost_field, part="speech")
            return tts.synth_beat(provider, text, voice=voice, style=cfg.get("style", ""))
        try:
            samples, reg = settle_register(plan, beat, video_id, samples, again)
        except Exception:   # the first take stands
            logging.exception("register step failed for beat %s", beat.get("id"))
    dur = round(samples.size / audio.SR, 3)
    awsio.put_bytes_meta(key, _wav_bytes(samples), "audio/wav", {"duration": str(dur)})
    out = {"tts_hash": h, "audio_key": key, "duration": dur, "voice": voice, **({"register": reg} if reg else {})}
    if _store_words(wkey, samples, text):
        out["words_key"] = wkey
    return out


def make_photo(plan: Dict[str, Any], beat: Dict[str, Any], video_id: str, cost_field: str, started: Optional[float] = None) -> Dict[str, Any]:
    pfx = awsio.prefix(video_id)
    props = beat["scene"]["props"]
    query, pick = props["image_query"], beat.get("pick")
    big = format_options.is_4k((plan.get("frame") or {}).get("resolution"))   # a 4K video fetches and keeps larger photos (docs/FOUR_K.md); 720p/1080p exactly as before
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
                jpeg, _ = assets.to_jpeg(stock.fetch_full(chosen), max_side=assets.max_side_for(big))
                stock.track_download(chosen, unsplash_key)
                result = {"jpeg": jpeg, "entry": stock.ledger_entry(chosen), "credit": stock.credit_line(chosen), "chosen": pick, "candidates": cands, "review": {}}
        except Exception:
            result = None
    if result is None and catalog_pick.catalog.enabled():   # videomk's own library first (flag `imageCatalog`, off by default); nothing passes -> stock exactly as before
        fr = plan.get("frame") or {}
        result = catalog_pick.try_catalog(query, _context(beat), props.get("alt", ""), video_id, aspect=str(fr.get("aspect") or "16:9"), big=big)
        if result:
            costs.add_cost(video_id, float(result["review"].get("cost_usd", 0.0)), field=cost_field, part="stock")
    if result is None:
        job = None
        if clip_config.flag() and not pick:   # images on demand (docs/LIBRARY_ON_DEMAND.md): our catalog has nothing for this search; a general picture may be made for it while the stock search runs
            job = image_ondemand.begin(video_id=video_id, beat_id=str(beat["id"]), query=query, alt=props.get("alt", ""), narration=_context(beat), plan=plan,
                                       ctx=clip_ondemand.context(video_id), is_edit=cost_field != "cost_usd", beat_started=started)
        openverse_key = stock.optional_secret(stock.OPENVERSE_KEY_PARAM, get_secret_param)   # a registered Openverse application when the owner has stored one; without it the search is anonymous, as always
        result = stock.scout_reviewed(query, _context(beat), props.get("alt", ""), unsplash_key=unsplash_key, **({"big": True} if big else {}), **({"openverse_key": openverse_key} if openverse_key else {}))
        if result:
            costs.add_cost(video_id, float(result.get("review", {}).get("cost_usd", 0.0)), field=cost_field, part="stock")
            if result.get("candidates"):
                awsio.put_json(cands_key, {"query": query, "candidates": result["candidates"]})
        if job is not None:   # ours when it comes in time and suits the narration: read back from the catalog, no credit line; otherwise the stock photo found meanwhile
            cid = job.wait()
            mine = image_ondemand.use(cid, query, _context(beat), props.get("alt", ""), video_id, aspect=str((plan.get("frame") or {}).get("aspect") or "16:9"), big=big, generated=job.generated) if cid else None
            if mine:
                costs.add_cost(video_id, float(mine["review"].get("cost_usd", 0.0)), field=cost_field, part="stock")
                result = mine
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


def make_clip(plan: Dict[str, Any], beat: Dict[str, Any], video_id: str, cost_field: str, speech: float, started: Optional[float] = None) -> Dict[str, Any]:
    """A short licensed stock clip (or a montage of 2-4 short clips in sequence, `clip_queries`) for the beat. If none is found or usable, a still photo of the same subject, so the video never has a hole."""
    pfx = awsio.prefix(video_id)
    props = beat["scene"]["props"]
    queries = plan_mod.clip_queries(props)
    query = queries[0]
    out: Dict[str, Any] = {"query": plan_mod.clip_signature(props), "pick": None}
    need = timeline_mod.LEAD + speech + timeline_mod.TAIL + 0.6  # the scene's length, with a little margin for the crossfade
    keys = {"pexels_key": get_secret_param("/videomk/pexels_api_key", quiet=True), "pixabay_key": get_secret_param("/videomk/pixabay_api_key", quiet=True)}
    fr = plan.get("frame") or {}   # vertical and square videos ask the stock libraries for portrait or square footage; landscape calls are exactly as before
    orient = "portrait" if fr.get("aspect") in ("9:16", "4:5") else "square" if fr.get("aspect") == "1:1" else str(fr.get("orientation") or "landscape")
    keys = {**keys, **({"orientation": orient} if orient in ("portrait", "square") else {}), **({"hd": True} if format_options.is_4k(fr.get("resolution")) else {})}   # 4K: 1080p footage instead of 720p
    # VideoMK's own clip library and clips made on demand (docs/CLIPS_ON_DEMAND.md): only with the deploy flag; without it nothing below differs from before
    ctx = clip_ondemand.context(video_id) if clip_config.flag() else None
    ours = clip_config.flag() and clip_ondemand.lib.usable(clip_ondemand.plan_of(ctx))
    job, narration, alt = None, _context(beat), props.get("alt", "")
    ask = dict(video_id=video_id, beat_id=str(beat["id"]), query=query, alt=alt, narration=narration, need_seconds=need, orientation=orient if orient in ("portrait", "square") else "landscape",
               plan=plan, ctx=ctx, is_edit=cost_field != "cost_usd", beat_started=started)
    own = {"own_library": True} if ours else {}
    if len(queries) > 1:   # a montage: every clip found, reviewed and verified on its own; failed ones dropped, fewer than half left -> the photo
        result = clips.scout_montage(queries, narration, alt, need_seconds=need, **keys, **own)
        if ctx is not None and not (result and result.get("mp4")):   # the whole montage would become a photo: one general clip may be made instead
            job = clip_ondemand.begin(**ask)
    else:
        result = clips.scout_own(query, narration, alt, need_seconds=need, **{k: v for k, v in keys.items() if k in ("orientation", "hd")}) if ours else None   # ours first
        if not result:
            job = clip_ondemand.begin(**ask) if ctx is not None else None   # not in the library: decide, and generate in the background while the stock search runs
            result = clips.scout_with_retry(query, narration, alt, need_seconds=need, **keys)   # one retry with a stock-staple wording when nothing passes; searches the clip_query, the alt wording and shortened forms in one pool
    made = None
    if job is not None:   # a library clip may come (made now, or found by its brief): it is read back FROM THE LIBRARY and checked against the narration like any other
        made = job.wait()
        mine = clips.scout_own(query, narration, alt, need_seconds=need, ids=[made], **{k: v for k, v in keys.items() if k in ("orientation", "hd")}) if made else None
        if mine:
            mine["review"]["cost_usd"] = float(mine["review"].get("cost_usd", 0.0)) + float((result or {}).get("review", {}).get("cost_usd", 0.0))   # the stock search that ran meanwhile was paid too
            result = mine
    if result:
        costs.add_cost(video_id, float(result.get("review", {}).get("cost_usd", 0.0)), field=cost_field, part="stock")
    if result and result.get("mp4"):
        key = f"{pfx}assets/clip_{beat['id']}_{hashlib.sha1(result['mp4']).hexdigest()[:8]}.mp4"
        try:
            awsio.put_bytes(key, result["mp4"], "video/mp4", working=True)
            out.update({"clip_asset": key, "credit": result["credit"], "ledger": result["entry"], "chosen": result["chosen"]})
            if result.get("entries"):   # a montage: one ledger line per clip (the first stays in `ledger` for readers that know one)
                out.update({"ledgers": result["entries"], "segments": result["segments"], "segments_requested": result["requested"]})
            if ours:
                clip_ondemand.used(video_id, result.get("chosen_all") or result["chosen"], generated_id=made if job is not None and job.generated else None)
            return out
        except Exception:  # storing the clip failed: a still photo keeps the beat visual, the video is not lost
            logging.exception("could not store clip %s", key)
    subject = str(props.get("alt") or query)
    still = {"id": beat["id"], "narration": _context(beat), "scene": {"type": "image", "props": {"image_query": query, "alt": subject, **({"word": props["word"]} if props.get("word") else {})}}}
    out.update({k: v for k, v in make_photo(plan, still, video_id, cost_field).items() if k not in ("query", "pick")})
    return out


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    video_id, beat_id = str(event["video_id"]), str(event["beat_id"])
    began = time.time()
    cost_field = str(event.get("cost_field") or "cost_usd")
    plan = awsio.get_json(event["plan_key"])
    beat = next((b for b in plan["beats"] if b["id"] == beat_id), None)
    if beat is None:
        raise ValueError(f"beat {beat_id} not in plan")
    media = make_audio(plan, beat, video_id, cost_field)
    if beat["scene"]["type"] == "image":
        media.update(make_photo(plan, beat, video_id, cost_field, began))
    elif beat["scene"]["type"] == "gallery":
        media.update(make_gallery(plan, beat, video_id, cost_field))
    elif beat["scene"]["type"] == "clip":
        media.update(make_clip(plan, beat, video_id, cost_field, float(media["duration"]), began))
    else:
        el = ELEMENTS.get(beat["scene"]["type"])
        if el is not None and el.prepare is not None:   # an element that needs outside data (a map's places, ...): a failure falls back, it never fails the video
            try:
                patch = el.prepare(dict(beat["scene"]["props"]), PrepareCtx(video_id=video_id, beat_id=beat_id, narration=beat.get("narration", ""), duration=float(media["duration"]),
                                                                            sources=plan.get("sources") or [], language=plan.get("language", "en"), region=plan.get("region"),
                                                                            media_items=plan.get("media_items") or [], frame=dict(plan.get("frame") or {})))
                media["element"] = patch if isinstance(patch, dict) else {}
            except Exception:
                logging.exception("element %s could not prepare beat %s", el.name, beat_id)
                media["element_failed"] = True
    making_progress.record_beat(video_id, plan, beat, media)   # the Making screen: this scene is ready, with a small picture when it has one (never raises; nothing during an edit)
    return {"id": beat_id, "media": media}
