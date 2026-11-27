"""The Making status: what the apps show while a video is being built (docs/CREATE_API.md "Making status", docs/DESIGN_BAR_2026.md section 3 item 3).

Where each part comes from (nothing here calls a model, nothing is estimated):
  * the plan step writes a compact MANIFEST of the planned scenes on the video record (`making_plan`): per scene its kind, a short subject and the first sentence of its narration;
  * every beat of the pictures-and-voice step adds its id to `making_done` when its voice and its picture are stored, and to `making_thumbs` when a small picture of the scene
    was stored at generation/v2/<video>/thumbs/<beat>.jpg (engine/making_progress.py). Both are DynamoDB sets that only grow, so the counter can never go down during a run;
  * the last step sets `making_step = "finish"` when it starts stitching, and removes all of this when the video is complete.

`shape()` turns the record into the `making` object of the API. It is pure: the route passes a `sign` function that turns a thumbnail key into a short-lived URL.
"""
import json
import os
import re
from typing import Any, Callable, Dict, List, Optional

from . import i18n

ATTR_PLAN, ATTR_DONE, ATTR_THUMBS, ATTR_STEP = "making_plan", "making_done", "making_thumbs", "making_step"
ATTRS = (ATTR_PLAN, ATTR_DONE, ATTR_THUMBS, ATTR_STEP)
STEP_FINISH = "finish"
MAKING_STATUS = "ASSETS_CREATION"   # the record's status from the moment the plan exists until the video is complete (the only state in which progress is written)
# a video in one of these states has no Making status: nothing is planned yet, or nothing is being made any more
NOT_MAKING = ("", "STARTED_PROCESSING", "PLOT_CREATION", "COMPLETE", "COMPLETED", "FAILED", "REJECTED", "CANCELLED")

THUMB_URL_SECONDS = int(os.environ.get("MAKING_THUMB_URL_SECONDS", "600"))   # the apps poll every few seconds and get fresh URLs each time
MAX_LINE_WORDS = 8          # the live line: one short plain sentence
MAX_SUBJECT_WORDS, MAX_SUBJECT_CHARS = 5, 40
MAX_NARRATION_CHARS = 180
MAX_SCENES = 200            # far above any real plan (12 minutes is about 50 scenes, 100 photos 100): a bound, not a feature

_BEAT_ID = re.compile(r"^[0-9A-Za-z]{1,32}$")
_VIDEO_ID = re.compile(r"^[0-9A-Za-z-]{1,64}$")
_SENTENCE_END = re.compile(r"([.!?…]+[\"'”’»)\]]*)\s+(?=[\"'“‘«(\[¿¡]*[A-ZÁÉÍÓÚÑÜ0-9])")
_ES_MARKS = re.compile(r"[áéíóúñü¿¡]|\b(?:de|del|la|las|el|los|en|con|un|una|y|para|por|su|sus|al)\b|\w{3,}(?:ando|iendo)\b", re.IGNORECASE)

OWN_PHOTO_SCENES = ("photo_collage", "photo_frame", "photo_chapter")


# ----------------------------------------------------------------------------- text helpers
def _clean(text: Any) -> str:
    return " ".join(str(text or "").split())


def first_sentence(text: Any, max_chars: int = MAX_NARRATION_CHARS) -> str:
    """The first sentence of a narration, whole. A fragment that is not a sentence on its own ("Dr.", "No.") is joined with what follows; a very long one is cut at a word with an ellipsis."""
    s = _clean(text)
    if not s:
        return ""
    out = s
    for m in _SENTENCE_END.finditer(s):
        cand = s[: m.end(1)]
        if len(cand.split()) >= 2 and len(cand) >= 8:
            out = cand
            break
    if len(out) <= max_chars:
        return out
    cut = out[: max_chars - 1].rsplit(" ", 1)[0].rstrip(",;:—-")
    return cut + "…"


def _subject(text: Any) -> str:
    """A subject short enough for the live line, or '' (the generic line is used instead; a phrase is never cut in the middle)."""
    s = _clean(text).strip(" .,:;")
    if not s or len(s) > MAX_SUBJECT_CHARS or len(s.split()) > MAX_SUBJECT_WORDS or any(c in s for c in "{}<>\n"):
        return ""
    return s


def looks_spanish(text: str) -> bool:
    return bool(_ES_MARKS.search(text or ""))


# ----------------------------------------------------------------------------- the manifest (written once, by the plan step)
def _kind(scene: Dict[str, Any]) -> str:
    typ, props = str(scene.get("type") or ""), scene.get("props") or {}
    if typ == "slide":
        return "slide"
    if props.get("photo") or props.get("photos") or typ in OWN_PHOTO_SCENES:
        return "own"
    if typ == "clip":
        return "clip"
    if typ in ("image", "gallery"):
        return "image"
    return "words"


def manifest(plan: Dict[str, Any]) -> str:
    """The planned scenes as compact JSON for the video record: {"v":1,"lang":"en","scenes":[{"id","k","q"?,"t"?,"n"?}]}.
    k: clip | image | own (the person's photos) | slide | words (a scene drawn by the engine); q: what the stock search looks for; t: the scene's own title;
    n: the first sentence of the narration. About 250 bytes per scene."""
    scenes: List[Dict[str, str]] = []
    for b in (plan.get("beats") or [])[:MAX_SCENES]:
        scene = b.get("scene") or {}
        props = scene.get("props") or {}
        k = _kind(scene)
        row: Dict[str, str] = {"id": str(b.get("id") or ""), "k": k}
        if k == "clip":
            qs = [q for q in (props.get("clip_queries") or []) if isinstance(q, str)]
            q = _subject(props.get("clip_query")) or _subject(qs[0] if qs else "") or _subject(props.get("alt"))
        elif k == "image":
            qs = [q for q in (props.get("image_queries") or []) if isinstance(q, str)]
            q = _subject(props.get("image_query")) or _subject(qs[0] if qs else "") or _subject(props.get("alt"))
        else:
            q = ""
        t = (_subject(props.get("title")) or _subject(props.get("heading"))) if k == "words" else ""
        n = first_sentence(b.get("narration"))
        if q:
            row["q"] = q
        if t:
            row["t"] = t
        if n:
            row["n"] = n
        scenes.append(row)
    return json.dumps({"v": 1, "lang": str(plan.get("language") or "en")[:5], "scenes": scenes}, ensure_ascii=False, separators=(",", ":"))


def _load(raw: Any) -> Optional[Dict[str, Any]]:
    try:
        m = json.loads(raw) if isinstance(raw, str) else None
    except ValueError:
        return None
    if not isinstance(m, dict) or not isinstance(m.get("scenes"), list) or not m["scenes"]:
        return None
    m["scenes"] = [s for s in m["scenes"][:MAX_SCENES] if isinstance(s, dict)]
    return m if m["scenes"] else None


# ----------------------------------------------------------------------------- the thumbnail of a scene
def thumb_key(video_id: str, beat_id: str) -> Optional[str]:
    """Where a scene's small picture lives: inside the video's own working folder, under thumbs/. None for an id that is not an id (a key is never built from odd input)."""
    if not (_VIDEO_ID.match(str(video_id or "")) and _BEAT_ID.match(str(beat_id or ""))):
        return None
    return f"generation/v2/{video_id}/thumbs/{beat_id}.jpg"


_signer_client = None


def presign_thumb(key: str) -> Optional[str]:
    """A short-lived GET URL for one thumbnail, signed with the calling function's own role (which may read generation/v2/*/thumbs/* and nothing else of the working files)."""
    global _signer_client
    bucket = os.environ.get("ASSETS_BUCKET", "")
    if not bucket or "/thumbs/" not in key or ".." in key or not key.startswith("generation/v2/"):
        return None
    try:
        if _signer_client is None:
            import boto3
            from botocore.config import Config

            _signer_client = boto3.client("s3", region_name=os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1",
                                          config=Config(signature_version="s3v4", s3={"addressing_style": "virtual"}))
        return _signer_client.generate_presigned_url("get_object", Params={"Bucket": bucket, "Key": key, "ResponseContentType": "image/jpeg"}, ExpiresIn=THUMB_URL_SECONDS)
    except Exception:   # noqa: BLE001 - a thumbnail is never worth a failed status call
        return None


# ----------------------------------------------------------------------------- the live line
def _line(key: str, locale: str, **params: Any) -> str:
    return i18n.t(f"making.line.{key}", locale, **params)


def live_line(scene: Optional[Dict[str, Any]], video_lang: str, locale: str, *, all_done: bool = False, step: str = "") -> str:
    """One short plain sentence in the app's language for what is really happening now. The scene's subject is named only when it is written in that language
    (stock searches are worded in English, titles in the video's language); otherwise the plain sentence without it. Never more than MAX_LINE_WORDS words."""
    loc = i18n.normalize(locale) or i18n.DEFAULT
    if step == STEP_FINISH:
        return _line("finish", loc)
    if all_done or not scene:
        return _line("assemble", loc)
    k = str(scene.get("k") or "words")
    if k == "own":
        return _line("own", loc)
    if k == "slide":
        return _line("slide", loc)
    if k in ("clip", "image"):
        q = _subject(scene.get("q"))
        q_lang = "es" if looks_spanish(q) else "en"
        if q and q_lang == loc:
            text = _line(f"{k}_of", loc, subject=q)
            if len(text.split()) <= MAX_LINE_WORDS:
                return text
        return _line(k, loc)
    t = _subject(scene.get("t"))
    if t and (i18n.normalize(video_lang) or "") == loc:
        text = _line("words_of", loc, subject=t)
        if len(text.split()) <= MAX_LINE_WORDS:
            return text
    return _line("words", loc)


# ----------------------------------------------------------------------------- the API object
def _ids(value: Any) -> set:
    return {str(x) for x in value} if isinstance(value, (set, frozenset, list, tuple)) else set()


def shape(item: Dict[str, Any], locale: str, sign: Optional[Callable[[str], Optional[str]]] = None) -> Optional[Dict[str, Any]]:
    """The `making` object for a video record, or None when there is nothing honest to say (no plan yet, or the video is not being made).

    scene_total   the planned scenes
    scene_done    scenes whose voice and picture are stored (counted from a set that only grows: it never goes down during a run)
    live_line     what is happening now, in `locale`
    narration_line  the first sentence of the scene being worked on (the first scene not yet done); once every scene is done, of the opening scene
    scenes        [{index, done, thumb_url?}] in story order; thumb_url only for a scene whose small picture exists
    """
    try:
        if str(item.get("status") or "").upper() in NOT_MAKING:
            return None
        m = _load(item.get(ATTR_PLAN))
        if not m:
            return None
        video_id = str(item.get("video_id") or "")
        scenes = m["scenes"]
        known = [str(s.get("id") or "") for s in scenes]
        done_ids = _ids(item.get(ATTR_DONE)) & set(known)
        thumb_ids = _ids(item.get(ATTR_THUMBS)) & done_ids   # a picture is only shown for a scene that is done
        out_scenes: List[Dict[str, Any]] = []
        current: Optional[Dict[str, Any]] = None
        for i, s in enumerate(scenes):
            sid = known[i]
            done = sid in done_ids
            row: Dict[str, Any] = {"index": i + 1, "done": done}
            if done and sid in thumb_ids and sign is not None:
                key = thumb_key(video_id, sid)
                url = sign(key) if key else None
                if url:
                    row["thumb_url"] = url
            if not done and current is None:
                current = s
            out_scenes.append(row)
        total, n_done = len(scenes), sum(1 for r in out_scenes if r["done"])
        all_done = n_done >= total
        out: Dict[str, Any] = {"scene_total": total, "scene_done": n_done,
                               "live_line": live_line(current, str(m.get("lang") or "en"), locale, all_done=all_done, step=str(item.get(ATTR_STEP) or ""))}
        narration = str((current or scenes[0]).get("n") or "")
        if narration:
            out["narration_line"] = narration
        out["scenes"] = out_scenes
        return out
    except Exception:   # noqa: BLE001 - the Making status is an extra: it must never break the list or the status call
        return None


def for_owner(item: Dict[str, Any], user_id: Optional[str], locale: str) -> Optional[Dict[str, Any]]:
    """What the routes call: the Making status with signed thumbnail URLs, only when `user_id` (the authenticated caller) owns the record. Thumbnails are the person's own
    content (their photos, their slides): nobody else ever gets a URL, and the URLs are short-lived."""
    if not user_id or str(item.get("user_id") or "") != str(user_id):
        return None
    return shape(item, locale, presign_thumb)
