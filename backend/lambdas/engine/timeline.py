"""Plan + measured audio durations -> timeline. Scene length comes from the narration, never from a guess."""
import hashlib
import json
from typing import Any, Dict, List, Sequence

from . import length as length_mod
from . import plan_langs
from . import sync as sync_mod
from . import watermark_spec
from .align import estimate_words
from .scenes import ELEMENTS, SCENES

LEAD = 0.40     # silence before the first word of a beat
TAIL = 0.55     # breathing room after the last word
MIN_SCENE = 2.8
END_HOLD = 1.4  # extra on the final scene for the outro fade
GOP_SECONDS = 2
RENDER_VERSION = "3"  # bump when scene/renderer code changes: invalidates every cached segment
MIN_TAIL_CHUNK_S = 8.0


MAX_SPOKEN_STRETCH = 1.6   # most seconds a spoken scene may be held longer to reach the length asked
MAX_END_FREEZE = 2.5       # the last scene is never held longer than this on top of its share to reach the length: more is spread over every spoken scene
MIN_VIDEO_MARGIN = 1.0     # aim this far past the asked length so rounding can never leave it short
SHORT_VIDEO_MARGIN = 0.4   # under a minute (15, 30, 45 s) a whole second would be 7 percent of the video


def stretch_to(durs: List[float], silent: List[bool], min_seconds: float, max_hold: float = 8.0) -> List[float]:
    """A video must never be shorter than the length asked for (it may run over by a few seconds). Shortfall is spread as a longer hold at the END of scenes
    (so nothing already anchored to a word moves): first a little on every spoken scene, then longer pauses, then what is left on the last scene when it
    is a moment (MAX_END_FREEZE), else evenly over the spoken scenes again. It was always all put on the last scene: a script 11 s short froze the last
    picture and caption for 8 to 11 s with music only (the first French and Portuguese videos). The director lengthens such a script before it gets here
    (length.extend_script); this is what remains when it could not."""
    out = list(durs)
    short = min_seconds + (SHORT_VIDEO_MARGIN if min_seconds < 60 else MIN_VIDEO_MARGIN) - sum(out)
    if short <= 0:
        return out
    spoken = [i for i, s in enumerate(silent) if not s]
    if spoken:
        each = min(MAX_SPOKEN_STRETCH, short / len(spoken))
        for i in spoken:
            out[i] += each
        short -= each * len(spoken)
    for i, s in enumerate(silent):
        if short <= 0:
            break
        if s:
            add = min(short, max(0.0, max_hold - out[i]))
            out[i] += add
            short -= add
    if short > 0:
        if short <= MAX_END_FREEZE or not spoken:
            out[-1] += short
        else:
            for i in spoken:
                out[i] += short / len(spoken)
    return out


def shortest(plan: Dict[str, Any], speech: Sequence[float], fit_seconds: float) -> tuple:
    """(the length of the video with the silences around every spoken beat at their floors, the length the fit works towards). `speech`: the measured speech
    of each beat in seconds (a pause beat: how long it is held). The same arithmetic as `build_timeline`: the intro, the outro and the closing card count.
    A video whose first number is past the window above the second cannot be saved by shorter silences (length.overrun): sentences must come out."""
    intro = max(0.0, min(6.0, float(plan.get("intro_s") or 0.0)))
    outro = max(END_HOLD, min(8.0, float(plan.get("outro_s") or END_HOLD)))
    beats = plan.get("beats") or []
    total = 0.0
    for i, beat in enumerate(beats):
        sp = float(speech[i])
        total += max(MIN_SCENE, sp) if beat.get("silent") else max(MIN_SCENE, length_mod.LEAD_FLOOR + sp + length_mod.TAIL_FLOOR)
    if beats and not beats[0].get("silent"):
        total += intro
    wm0 = watermark_spec.parse(plan.get("watermark"), strict=False)
    card = watermark_spec.END_CARD_S if wm0 and wm0.get("mode") == "videomk" and wm0.get("end_card") else 0.0
    return total + outro, (max(1.0, float(fit_seconds) - card) if fit_seconds else 0.0)


def build_timeline(
    plan: Dict[str, Any],
    beat_info: Sequence[Dict[str, Any]],
    *,
    video_id: str,
    fps: int = 30,
    width: int = 1920,
    height: int = 1080,
    min_seconds: float = 0.0,
    fit_seconds: float = 0.0,
) -> Dict[str, Any]:
    """beat_info[i] = {'duration': speech seconds, 'asset': optional key for image scenes}.
    `min_seconds`: the video is never shorter than this (scenes are held longer). `fit_seconds`: the length asked for; when the measured narration would run
    more than a few percent past it, the silences around every spoken beat are shortened (engine/length.py). Without `fit_seconds` the silences are the ones
    stored in the plan (`pace`, written by the first render) or the normal ones."""
    intro = max(0.0, min(6.0, float(plan.get("intro_s") or 0.0)))                    # music and pictures before the first word
    outro = max(END_HOLD, min(8.0, float(plan.get("outro_s") or END_HOLD)))          # music alone after the last word

    def lengths(ld: float, tl: float) -> List[float]:
        out = []
        for i, beat in enumerate(plan["beats"]):
            speech, silent = float(beat_info[i]["duration"]), bool(beat.get("silent"))
            out.append(max(MIN_SCENE, speech) if silent else max(MIN_SCENE, ld + speech + tl))
        out[0] += intro if not plan["beats"][0].get("silent") else 0.0
        out[-1] += outro
        return out

    wm0 = watermark_spec.parse(plan.get("watermark"), strict=False)
    card = watermark_spec.END_CARD_S if wm0 and wm0.get("mode") == "videomk" and wm0.get("end_card") else 0.0
    if card:   # the closing "Made with VideoMK" card is part of the video's length: the scenes aim that much shorter, so the whole video still lands on the length asked (seen on QA: 32.8 s for 30)
        min_seconds = max(0.0, min_seconds - card) if min_seconds else min_seconds
        fit_seconds = max(1.0, fit_seconds - card) if fit_seconds else fit_seconds
    if fit_seconds:   # a first render: the pace is worked out from the measured audio
        LEAD_S, TAIL_S = length_mod.tighten(sum(1 for b in plan["beats"] if not b.get("silent")), sum(lengths(LEAD, TAIL)), fit_seconds, LEAD, TAIL)
    else:             # an edit keeps the pace its video was made with
        LEAD_S, TAIL_S = length_mod.clean_pace(plan.get("pace"), LEAD, TAIL)
    base = lengths(LEAD_S, TAIL_S)
    durs = stretch_to(base, [bool(b.get("silent")) for b in plan["beats"]], min_seconds) if min_seconds else base
    scenes: List[Dict[str, Any]] = []
    sync_items = sync_anchored = 0
    t = 0.0
    chapters: List[Dict[str, Any]] = []
    for i, beat in enumerate(plan["beats"]):
        info = beat_info[i]
        speech = float(info["duration"])
        silent = bool(beat.get("silent"))
        lead = LEAD_S + (intro if i == 0 and not silent else 0.0)   # the first beat starts speaking after the intro
        dur = durs[i]   # the narration's length (+ lead and tail), a silent beat exactly as long as it is held, stretched at the end if the video would be shorter than asked
        stype = beat["scene"]["type"]
        props = dict(beat["scene"]["props"])
        el = ELEMENTS.get(stype)
        if el is not None:   # an element: merge what its prepare step fetched, or show its fallback when that failed
            if info.get("element_failed"):
                stype, props = el.fallback(props) if el.fallback else ("title", {"title": str(props.get("title") or props.get("heading") or props.get("label") or beat.get("narration", ""))[:60], "subtitle": ""})
            elif isinstance(info.get("element"), dict):
                props = {**props, **info["element"]}
        if stype == "gallery":
            shots = [g for g in (info.get("gallery") or []) if g.get("asset")]
            if len(shots) >= 2:
                queries = [g.get("query") for g in shots]
                if not all(queries):
                    queries = list(props.get("image_queries") or [])[: len(shots)]
                props = {"assets": [g["asset"] for g in shots], "credits": [g.get("credit") or "" for g in shots], "alt": props.get("alt", ""), "image_queries": queries, **({"word": props["word"]} if props.get("word") else {}), **({"user": True} if props.get("photos") else {})}
            elif len(shots) == 1:  # only one photograph could be found: a plain image scene (the image branch below attaches the asset and credit)
                info = {**info, "asset": shots[0]["asset"], "credit": shots[0].get("credit") or None}
                stype, props = "image", {"alt": props.get("alt", ""), "ken_burns": "in", **({"photo": shots[0]["photo"]} if shots[0].get("photo") else {})}
            else:
                stype, props = "title", {"title": props.get("alt") or (props.get("image_queries") or [""])[0], "subtitle": ""}
        if stype == "clip":
            if info.get("clip_asset"):
                props = {"asset": info["clip_asset"], "alt": props.get("alt", ""), **({"word": props["word"]} if props.get("word") else {}), **({"credit": info["credit"]} if info.get("credit") else {})}
            elif info.get("asset"):  # no footage found: a still photo of the same subject keeps the beat visual
                stype, props = "image", {"asset": info["asset"], "alt": props.get("alt", ""), "ken_burns": "in", **({"credit": info["credit"]} if info.get("credit") else {})}
            else:
                stype, props = "title", {"title": props.get("alt") or props.get("clip_query", ""), "subtitle": ""}
        if stype == "image":
            if info.get("asset"):
                props["asset"] = info["asset"]
                if info.get("credit"):
                    props["credit"] = info["credit"]
            else:  # scout found nothing usable: degrade to a clean title card instead of a hole
                stype, props = "title", {"title": props.get("alt") or props.get("image_query", ""), "subtitle": ""}
        # words: measured from the audio when we have them (engine/align.py), else the proportional estimate; both in scene time (after the lead-in)
        if silent:
            words = []
        elif info.get("words"):
            words = [[w, round(lead + float(s), 3), round(lead + float(e), 3)] for w, s, e in info["words"]]
        else:
            words = [list(w) for w in estimate_words(beat["narration"], speech, lead=lead)]
        found = sync_mod.apply(stype, props, words, dur)   # anchor reveals to the words that name them (props.cues / props.cuts)
        if found:
            sync_items += found["items"]
            sync_anchored += found["anchored"]
        # reveal cues, as seconds from scene start, for sfx; scenes without cues get none
        cues = SCENES[stype][1](props, dur)
        scenes.append(
            {
                "id": beat.get("id") or f"s{i + 1}",
                "type": stype,
                "start": round(t, 4),
                "duration": round(dur, 4),
                "props": props,
                "words": words,
                "audio_key": info.get("audio_key"),
                **({"silent": True} if silent else {}),
                "narration_offset": lead,
                "cues": [round(c, 3) for c in cues[:8]],
                "transition": "fade",
                **({"sfx": beat["sfx"]} if beat.get("sfx") else {}),
                **plan_langs.scene_extras(plan, beat),   # {} unless the plan has characters speaking different languages
            }
        )
        if beat.get("chapter"):
            chapters.append({"start": round(t, 3), "title": beat["chapter"]})
        t += dur
    wm = watermark_spec.parse(plan.get("watermark"), strict=False)   # the plan's watermark option (docs/WATERMARK.md): none/absent = nothing added anywhere
    if wm and wm["mode"] == "none":
        wm = None
    if wm and wm.get("end_card") and scenes:   # optional closing card (VideoMK mark only): a silent 'Made with VideoMK' scene after the last one
        from . import language as lang_mod
        props = {"title": lang_mod.made_with(plan.get("language")), "subtitle": "videomk.com"}
        scenes.append({"id": "endcard", "type": "title", "start": round(t, 4), "duration": watermark_spec.END_CARD_S, "props": props, "words": [], "audio_key": None, "silent": True,
                       "narration_offset": 0.0, "cues": [round(c, 3) for c in SCENES["title"][1](props, watermark_spec.END_CARD_S)[:8]], "transition": "fade"})
        t += watermark_spec.END_CARD_S
    if wm and wm.get("mode") == "videomk" and wm.get("presence") == "moments":   # the mark comes and goes: its appearances are fixed here, once, for the whole video
        wm = {**wm, "windows": watermark_spec.moments(scenes, t, watermark_spec.END_CARD_S if wm.get("end_card") else 0.0)}
    if any(sc["type"] == "whiteboard" for sc in scenes):   # the whiteboard look (docs/WHITEBOARD.md): consecutive boards are panels of one big board
        from . import whiteboard_policy

        whiteboard_policy.link(scenes)
    if any(sc["type"] == "presenter" for sc in scenes):   # presenter scenes (docs/PRESENTERS.md): each learns the words it speaks and when, for its gestures and mouth
        from . import presenter_policy

        presenter_policy.link(scenes)
    # the director's animated background (engine/background.py; only in a plan made with BG_ANIMATED on): each scene knows where in the loop it starts, so the
    # background flows on across scene changes and chunks instead of jumping
    bg = plan.get("background") if isinstance(plan.get("background"), dict) else None
    if bg:
        from . import background as background_mod

        for sc in scenes:
            sc["bg_t0"] = background_mod.phase(sc["start"], bg)
    # segment boundaries must be a multiple of the GOP so chunks start on an IDR frame
    from . import music as music_mod

    return {
        "music": music_mod.resolve(plan.get("music"), [s["start"] for s in scenes], t),
        "version": 2,
        "video_id": video_id,
        "fps": fps,
        "width": width,
        "height": height,
        "theme": plan.get("theme", "midnight"),
        "mood": plan.get("mood", "calm"),
        "captions": bool(plan.get("captions", True)),
        "language": str(plan.get("language") or "en"),   # numbers are written the way this language does (engine/numfmt.py)
        "sync": {"items": sync_items, "anchored": sync_anchored, "aligned_beats": sum(1 for b in beat_info if b.get("words"))},
        "duration": round(t, 4),
        "intro_s": round(intro, 3), "outro_s": round(outro, 3),
        "scenes": scenes,
        "chapters": chapters,
        "title": plan.get("title", ""),
        **({"watermark": wm} if wm else {}),
        **({"background": bg} if bg else {}),
        **({"pace": {"lead": LEAD_S, "tail": TAIL_S}} if (LEAD_S, TAIL_S) != (LEAD, TAIL) else {}),   # only when the silences were shortened to keep the length (engine/length.py)
    }


def beat_info_from_plan(plan: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Per-beat measured media (written into the plan by the timeline step) in the shape build_timeline expects."""
    out = []
    for b in plan["beats"]:
        m = b.get("media") or {}
        out.append({"duration": m["duration"], "asset": m.get("asset"), "clip_asset": m.get("clip_asset"), "gallery": m.get("gallery"), "words_key": m.get("words_key"), "credit": m.get("credit"), "audio_key": m.get("audio_key"), "silent": bool(m.get("silent")), "element": m.get("element"), "element_failed": bool(m.get("element_failed"))})
    return out


def _scene_fingerprint(sc: Dict[str, Any]) -> Dict[str, Any]:
    return {**{k: sc.get(k) for k in ("id", "type", "duration", "props", "words", "transition")}, **({"bg_t0": sc["bg_t0"]} if "bg_t0" in sc else {}), **({"translation": sc["translation"]} if sc.get("translation") else {})}   # bg_t0: only with an animated background


def chunk_plan(timeline: Dict[str, Any], target_seconds: float = 30, draft: bool = False, max_frames: int = 0) -> List[Dict[str, Any]]:
    """Group whole scenes into ~target_seconds chunks. Each chunk is content-addressed:

    hash = f(renderer version, format, theme, draft, its scenes, the scene before it (crossfade), whether it ends the video).
    It deliberately excludes absolute time, so after an edit every chunk the edit didn't touch hashes the same and its cached
    segment is reused; a segment is rendered from t=0 and stitched purely by duration.

    `max_frames` (4K only, docs/FOUR_K.md; 0 = off, the plan is then exactly what it always was): a group with more frames is rendered as several pieces of
    at most that many frames, so one long scene can never take a render function past its time limit. A piece is {"f0": first frame within the group,
    "frames": how many}; its hash is the group's hash plus its frame range, so pieces are cached and reused like whole chunks.
    """
    scenes = timeline["scenes"]
    fps = int(timeline["fps"])
    groups: List[List[int]] = []
    cur: List[int] = []
    acc = 0.0
    for i, sc in enumerate(scenes):
        cur.append(i)
        acc += float(sc["duration"])
        if acc >= target_seconds:
            groups.append(cur)
            cur, acc = [], 0.0
    if cur:
        if groups and acc < MIN_TAIL_CHUNK_S:
            groups[-1].extend(cur)  # don't leave a sliver chunk
        else:
            groups.append(cur)
    out: List[Dict[str, Any]] = []
    prev_f1 = 0  # cumulative rounding: frame counts always sum to round(total*fps), so video and audio can't drift apart
    for k, g in enumerate(groups):
        lo, hi = g[0], g[-1] + 1
        f0 = prev_f1
        f1 = int(round((float(scenes[hi - 1]["start"]) + float(scenes[hi - 1]["duration"])) * fps))
        prev_f1 = max(f1, f0 + 1)
        h = hashlib.sha256(json.dumps({
            "v": RENDER_VERSION, "fps": fps, "w": timeline["width"], "h": timeline["height"], "theme": timeline.get("theme"),
            "captions": timeline.get("captions", True), "language": timeline.get("language", "en"), "draft": draft,
            "scenes": [_scene_fingerprint(x) for x in scenes[lo:hi]],
            "lead": _scene_fingerprint(scenes[lo - 1]) if lo > 0 else None, "outro": hi == len(scenes),
            **({"wm": _chunk_watermark(timeline, lo, hi), "first": lo == 0, "wmv": 4} if timeline.get("watermark") else {}),   # the mark is part of every frame (and fades in on the first chunk only; a 'moments' mark: this chunk's own appearances)
            **({"bg": timeline["background"]} if timeline.get("background") else {}),   # the animated background, when the plan has one
            **({"cover": timeline["cover"]} if timeline.get("cover") and lo == 0 else {}),   # the designed opening frames (engine/cover.py): the first chunk only
        }, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:24]
        n = max(1, f1 - f0)
        if not max_frames or n <= max_frames:
            out.append({"k": len(out), "lo": lo, "hi": hi, "frames": n, "hash": h, "draft": draft})
            continue
        parts = -(-n // int(max_frames))   # even pieces: 400 frames with a limit of 180 are 133 + 133 + 134, never 180 + 180 + 40
        for j in range(parts):
            a, b = n * j // parts, n * (j + 1) // parts
            hj = hashlib.sha256(f"{h}:{a}:{b}".encode("utf-8")).hexdigest()[:24]
            out.append({"k": len(out), "lo": lo, "hi": hi, "f0": a, "frames": b - a, "hash": hj, "draft": draft})
    return out


def chunk_timeline(timeline: Dict[str, Any], lo: int, hi: int) -> Dict[str, Any]:
    """Self-contained timeline for scenes [lo, hi): offsets relative to the chunk start, plus the lead scene for the crossfade."""
    scenes = timeline["scenes"]
    base = float(scenes[lo]["start"])
    sub = [{**sc, "start": round(float(sc["start"]) - base, 6)} for sc in scenes[lo:hi]]
    return {
        "fps": timeline["fps"], "width": timeline["width"], "height": timeline["height"], "theme": timeline.get("theme", "midnight"),
        "captions": timeline.get("captions", True), "language": timeline.get("language", "en"), "scenes": sub, "lead": scenes[lo - 1] if lo > 0 else None,
        "outro": hi == len(scenes), "duration": round(sum(float(x["duration"]) for x in sub), 6),
        **({"frame": timeline["frame"]} if timeline.get("frame") else {}),
        **({"watermark": _chunk_watermark(timeline, lo, hi)} if timeline.get("watermark") else {}),
        **({"background": timeline["background"]} if timeline.get("background") else {}),
        **({"cover": timeline["cover"]} if timeline.get("cover") and lo == 0 else {}),   # the designed opening frames: the first chunk only
    }


def _chunk_watermark(timeline: Dict[str, Any], lo: int, hi: int) -> Dict[str, Any]:
    """The watermark as the chunk of scenes [lo, hi) needs it: unchanged, except that the appearances of a 'moments' mark are given in the chunk's own time
    (a chunk is rendered from t = 0), and only those that touch it."""
    wm = timeline["watermark"]
    if not isinstance(wm, dict) or "windows" not in wm:
        return wm
    scenes = timeline["scenes"]
    base = float(scenes[lo]["start"])
    dur = sum(float(x["duration"]) for x in scenes[lo:hi])
    return {**wm, "windows": watermark_spec.shift_windows(wm["windows"], base, dur)}
