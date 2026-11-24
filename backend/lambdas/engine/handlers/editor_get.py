"""GET /users/{user_id}/videos/{video_id}/plan : everything the editor needs, with short-lived signed media URLs."""
import time
from typing import Any, Dict, List

from common.http import json_response

from .. import awsio, music as music_mod, plan as plan_mod
from ..audio import PLANNER_SFX
from ..plan import MAX_BEATS
from .editor_common import load_owned_video

STALE_EDIT_S = 45 * 60


def _s3_uri_key(uri: str) -> str:
    return uri.split("/", 3)[3] if isinstance(uri, str) and uri.startswith("s3://") and uri.count("/") >= 3 else ""


def _beat_view(plan: Dict[str, Any], beat: Dict[str, Any], pfx: str) -> Dict[str, Any]:
    m = beat.get("media") or {}
    view: Dict[str, Any] = {
        "id": beat["id"], "speaker": beat.get("speaker"), "narration": beat["narration"], "silent": bool(beat.get("silent")), "hold": beat.get("hold"), "scene": beat["scene"], "chapter": beat.get("chapter"), "pick": beat.get("pick"),
        "duration": m.get("duration"), "stale": plan_mod.needs_media(plan, beat),  # true => will be re-synthesised/re-fetched on next render
    }
    asset = m.get("asset")
    if beat["scene"]["type"] == "gallery":
        view["gallery"] = {"photos": [{"credit": g.get("credit"), "chosen": g.get("chosen"), "url": awsio.presign(g["asset"]) if isinstance(g.get("asset"), str) and g["asset"].startswith(pfx + "assets/") else None}
                                      for g in m.get("gallery") or []], "no_photo": bool(m.get("no_photo"))}
    if beat["scene"]["type"] == "clip":
        clip_key = m.get("clip_asset")
        view["clip"] = {"credit": m.get("credit"), "chosen": m.get("chosen"), "has_clip": bool(clip_key), "fallback_photo": bool(not clip_key and asset), "no_media": bool(m.get("no_photo"))}
    if beat["scene"]["type"] == "image":
        view["photo"] = {"url": awsio.presign(asset) if isinstance(asset, str) and asset.startswith(pfx + "assets/") else None, "credit": m.get("credit"), "chosen": m.get("chosen"), "no_photo": bool(m.get("no_photo"))}
        try:
            view["candidates"] = awsio.get_json(f"{pfx}assets/cands_{beat['id']}.json").get("candidates", [])[:8]
        except Exception:
            view["candidates"] = []
    return view


def handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    item, err = load_owned_video(event)
    if err:
        return err
    video_id = item["video_id"]
    pfx = awsio.prefix(video_id)
    plan = awsio.get_json(item["plan_key"])
    if plan.get("legit") is not True:
        return json_response(409, {"message": "Nothing to edit"})

    state = item.get("edit_state")
    if state == "RENDERING" and time.time() - float(item.get("edit_started_at") or 0) > STALE_EDIT_S:
        state = "FAILED"  # a render that never reported back must not lock the editor forever

    def signed(uri_attr: str):
        key = _s3_uri_key(item.get(uri_attr, ""))
        return awsio.presign(key, bkt=awsio.bucket()) if key.startswith(f"videos/{item['user_id']}/") else None

    beats: List[Dict[str, Any]] = [_beat_view(plan, b, pfx) for b in plan["beats"]]
    return json_response(200, {
        "video_id": video_id, "rev": int(item.get("rev", 1)), "status": item.get("status"), "edit_state": state or "READY",
        "edit_mode": item.get("edit_mode"), "edit_error": item.get("edit_error"),
        "title": plan.get("title"), "description": plan.get("description"), "theme": plan.get("theme"), "mood": plan.get("mood"), "captions": plan.get("captions", True),
        "voice": (plan.get("tts") or {}).get("voice", ""), "voices": plan.get("voices") or {}, "beats": beats, "chapters": [b["chapter"] for b in plan["beats"] if b.get("chapter")],
        "final": {"url": signed("video_uri"), "rev": item.get("final_rev")},
        "preview": {"url": signed("preview_uri"), "rev": item.get("preview_rev")},
        "limits": {"max_beats": MAX_BEATS, "min_words": plan_mod.MIN_BEAT_WORDS, "max_words": plan_mod.MAX_BEAT_WORDS},
        "scene_types": ["title", "bullets", "diagram", "chart", "timeline", "stat", "quote", "image", "gallery", "clip"],
        "music": plan.get("music") or {}, "music_styles": music_mod.style_catalog(), "sfx": sorted(PLANNER_SFX),
    })
