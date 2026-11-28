"""Step 3: merge measured media into the plan, build the timeline, and plan content-addressed chunks."""
import logging
import os
from typing import Any, Dict

from .. import awsio, format_options
from .. import sync as sync_mod
from ..timeline import beat_info_from_plan, build_timeline, chunk_plan, shortest

MAX_DURATION_S = float(os.environ.get("MAX_VIDEO_SECONDS", str(13 * 60)))
CHUNK_SECONDS = int(os.environ.get("CHUNK_SECONDS", "10"))
# 4K (docs/FOUR_K.md): a frame takes about 2.5 times as long to draw and encode as at 1080p, so chunks are shorter and a long scene is cut into pieces:
# every render function then finishes in a few minutes of its 10. Previews of a 4K video are small drafts and are chunked like any other video.
CHUNK_SECONDS_4K = int(os.environ.get("CHUNK_SECONDS_4K", "6"))
CHUNK_MAX_FRAMES_4K = int(os.environ.get("CHUNK_MAX_FRAMES_4K", "180"))
# A cartoon scene (vector_scene) costs about a second a frame on Lambda (measured on QA: 1.3 s before it was drawn on twos): a video that has one is cut into pieces of
# at most 5 seconds, like 4K, so no render function works for more than a few minutes of its 10 whatever the scene's length.
CHUNK_MAX_FRAMES_VECTOR = int(os.environ.get("CHUNK_MAX_FRAMES_VECTOR", "150"))


def credits_ledger(plan: Dict[str, Any]) -> list:
    """Every licensed photograph or clip the video shows, for the credits in its description: image and clip scenes, each photo of a gallery, and the photo
    of any element that fetches one (its `prepare` patch carries a `ledger`, e.g. annotated_image)."""
    out = [b["media"]["ledger"] for b in plan["beats"] if b["scene"]["type"] in ("image", "clip") and (b.get("media") or {}).get("ledger") and not (b.get("media") or {}).get("ledgers")]
    out += [e for b in plan["beats"] if b["scene"]["type"] == "clip" for e in (b.get("media") or {}).get("ledgers") or [] if e]   # a montage: one line per clip
    out += [g["ledger"] for b in plan["beats"] if b["scene"]["type"] == "gallery" for g in (b.get("media") or {}).get("gallery") or [] if g.get("ledger")]
    out += [b["media"]["element"]["ledger"] for b in plan["beats"]
            if isinstance((b.get("media") or {}).get("element"), dict) and b["media"]["element"].get("ledger") and not (b.get("media") or {}).get("element_failed")]
    return out


def fit_speech(plan: Dict[str, Any], video_id: str, asked: float) -> list:
    """The guard on the length, for any voice (engine/speechcut.py): when the speech that was really made leaves the video past its window (the length asked
    plus 5 percent) even with the shortest silences, whole sentences are cut out of the stored audio at their pauses, the ones the lengthening step added
    first. The shorter audio is stored under the hash of the shorter text (what an edit of that text would look for), its words are measured again, and the
    plan says what went (`length_cut`). Nothing is read from storage when the video fits. -> the cuts."""
    import copy
    import io
    import wave

    import numpy as np

    from .. import align, audio, length, plan as plan_mod, speechcut

    beats = plan["beats"]
    durs = [float((b.get("media") or {}).get("duration") or 0.0) for b in beats]
    total, target = shortest(plan, durs, asked)
    if length.overrun(total, target) <= 0:
        return []
    pfx = awsio.prefix(video_id)
    audio_of: Dict[int, Any] = {}
    words_of: Dict[int, Any] = {}
    for i, b in enumerate(beats):
        m = b.get("media") or {}
        key = m.get("audio_key")
        if b.get("silent") or not isinstance(key, str) or not key.startswith(pfx + "audio/") or ".." in key or len(length.sentences(b.get("narration", ""))) < 2:
            continue
        with wave.open(io.BytesIO(awsio.get_bytes(key)), "rb") as w:
            if w.getframerate() != audio.SR or w.getnchannels() != 1:
                continue
            audio_of[i] = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0
        wkey = m.get("words_key")
        if isinstance(wkey, str) and wkey.startswith(pfx + "audio/") and ".." not in wkey:
            try:
                words_of[i] = awsio.get_json(wkey)["words"]
            except Exception:
                pass

    def total_with(changed: Dict[int, float]) -> float:
        return shortest(plan, [changed.get(i, d) for i, d in enumerate(durs)], asked)[0]

    work = copy.deepcopy(plan)   # the plan itself changes beat by beat, each only once its shorter audio is stored
    cuts = speechcut.fit(work, audio_of, audio.SR, total_with, target, words_of, min_beat_words=plan_mod.MIN_BEAT_WORDS)
    for i in sorted({c["beat"] for c in cuts}):
        b, samples = beats[i], audio_of[i]
        narration = work["beats"][i]["narration"]
        h = plan_mod.tts_hash(plan, {**b, "narration": narration})
        key, wkey, dur = f"{pfx}audio/{h}.wav", f"{pfx}audio/{h}.words.json", round(samples.size / audio.SR, 3)
        buf = io.BytesIO()
        with wave.open(buf, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(audio.SR)
            w.writeframes((np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
        awsio.put_bytes_meta(key, buf.getvalue(), "audio/wav", {"duration": str(dur)})
        media = {**(b.get("media") or {}), "tts_hash": h, "audio_key": key, "duration": dur}
        media.pop("words_key", None)
        try:
            words, conf = align.align_words(samples, audio.SR, narration)
            if words and conf >= 0.6:
                awsio.put_json(wkey, {"words": [list(x) for x in words], "conf": conf})
                media["words_key"] = wkey
        except Exception:
            logging.exception("word alignment failed after a cut")
        b["narration"], b["media"] = narration, media
    if cuts:
        ids = [beats[c["beat"]].get("id") for c in cuts]
        plan["length_cut"] = [{"beat": ids[k], "sentence": c["text"], "seconds": c["seconds"], "added": c["added"]} for k, c in enumerate(cuts)]
        after = total_with({i: audio_of[i].size / audio.SR for i in {c["beat"] for c in cuts}})
        logging.warning("LENGTH_CUT asked=%s shortest_before=%.1f shortest_after=%.1f sentences=%s added=%s seconds=%.1f", asked, total, after, len(cuts),
                        sum(1 for c in cuts if c["added"]), sum(c["seconds"] for c in cuts))
    if length.overrun(total_with({i: audio_of[i].size / audio.SR for i in audio_of}), target) > 0:
        logging.warning("LENGTH_OVER asked=%s: the speech is longer than the window and no sentence could be cut", asked)
    return cuts


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    video_id = str(event["video_id"])
    rev = int(event.get("rev", 1))
    mode = event.get("mode", "final")
    pfx = awsio.prefix(video_id)
    plan = awsio.get_json(event["plan_key"])

    new_media = {r["id"]: r["media"] for r in event.get("beats") or []}
    for b in plan["beats"]:
        if b["id"] in new_media:
            b["media"] = new_media[b["id"]]
        if not (b.get("media") or {}).get("duration"):
            raise ValueError(f"beat {b['id']} has no audio")
    if rev == 1 and float(plan.get("target_seconds") or 0) and os.environ.get("FIT_TO_TARGET", "1") != "0":
        try:   # a first render is never longer than asked plus the window: if the voice took longer than every estimate, sentences come out of the audio
            fit_speech(plan, video_id, float(plan["target_seconds"]))
        except Exception:   # never a reason to lose the video: it is then longer than asked, as before this guard
            logging.exception("LENGTH_CUT failed")
    awsio.put_json(event["plan_key"], plan)  # the plan now carries its measured media (editor + future edits read it)

    infos = beat_info_from_plan(plan)
    for info in infos:  # word timings measured from each beat's audio (stored next to it); missing or unreadable ones fall back to the estimate
        key = info.pop("words_key", None)
        if isinstance(key, str) and key.startswith(pfx + "audio/") and ".." not in key:
            try:
                info["words"] = awsio.get_json(key)["words"]
            except Exception:
                pass
    frame = format_options.frame_of(plan)   # a plan made before formats existed has no frame: 16:9 1080p
    first = rev == 1   # only a first render is fitted to the length asked: an edit that removes scenes must be allowed to be shorter, and keeps the pace of its video
    asked = float(plan.get("target_seconds") or 0)
    tl = build_timeline(plan, infos, video_id=video_id, fps=30, width=frame["width"], height=frame["height"],
                        min_seconds=asked if rev == 1 and os.environ.get("STRETCH_TO_TARGET", "1") != "0" else 0.0,
                        fit_seconds=asked if rev == 1 and os.environ.get("FIT_TO_TARGET", "1") != "0" else 0.0)
    if first and tl.get("pace") != plan.get("pace"):   # the silences were shortened (or no longer are): the plan remembers, so every later render of this video has the same pace
        if tl.get("pace"):
            plan["pace"] = tl["pace"]
        else:
            plan.pop("pace", None)
        awsio.put_json(event["plan_key"], plan)
    if first and asked:
        logging.info("LENGTH asked=%s made=%.1f over=%.1f%% pace=%s", asked, tl["duration"], 100.0 * (tl["duration"] / asked - 1.0), tl.get("pace"))
    rep = sync_mod.report(tl)  # the free alignment check: is every reveal near the word that names it? (no model, a few ms)
    tl["sync"].update({k: rep[k] for k in ("anchored", "early", "late", "mean_abs_delta", "ok")})
    if not rep["ok"]:
        logging.warning("sync check: %s", {k: rep[k] for k in ("items", "anchored", "early", "late", "mean_abs_delta")} | {"worst": sorted((r for r in rep["rows"] if r["delta"] is not None), key=lambda r: -abs(r["delta"]))[:3]})
    if tl["duration"] > MAX_DURATION_S:
        raise ValueError(f"video too long ({tl['duration']:.0f}s > {MAX_DURATION_S:.0f}s)")
    tl["frame"] = frame
    if os.environ.get("COVER_IN_FRAME", "0") == "1" and mode != "preview":   # the designed cover over the first frames of the MP4 (off by default: docs/SHARE_PREVIEWS_2026-11-27.md)
        from .. import cover
        if cover.timeline_cover(tl):
            tl["cover"] = cover.timeline_cover(tl)
    tl["ledger"] = credits_ledger(plan)
    tl["sources"] = plan.get("sources", [])
    tl["description"] = plan.get("description", "")
    tl["language"] = plan.get("language", "en")
    key = f"{pfx}timeline_r{rev}.json"
    awsio.put_json(key, tl)
    return {
        "video_id": video_id,
        "user_id": event.get("user_id"),
        "usage_day": event.get("usage_day"),
        "plan_key": event["plan_key"],
        "rev": rev,
        "mode": mode,
        "timeline_key": key,
        "duration": tl["duration"],
        "chunks": [{**c, "video_id": video_id, "timeline_key": key} for c in (
            chunk_plan(tl, CHUNK_SECONDS_4K, draft=False, max_frames=CHUNK_MAX_FRAMES_4K) if format_options.is_4k(frame["resolution"]) and mode != "preview"
            else chunk_plan(tl, CHUNK_SECONDS, draft=(mode == "preview"), max_frames=CHUNK_MAX_FRAMES_VECTOR if any(sc.get("type") == "vector_scene" or (sc.get("type") == "presenter" and (sc.get("props") or {}).get("backdrop")) for sc in tl["scenes"]) else 0))],   # a character in front of a cartoon scene draws that scene too
    }
