"""`vector_scene`: a flat-cartoon scene made of separate vector layers that drift at different speeds (parallax), with swaying leaves, drifting clouds, moving sprites
(fish, rotors, boats, birds, smoke) and a slow push-in.

Two sources: `catalog_id` = a scene of the catalog (docs/VECTOR_CATALOG.md; its package is fetched once per container from the catalog bucket, `v/<id>/`), which is
what the director writes when the policy offers the style (docs/VECTOR_SCENE_POLICY.md, flag VECTOR_SCENES); `scene` = one of the three prototype scenes bundled with
the code. HIDDEN from the ordinary scene list: the planner only learns about it through the policy's own prompt block. A scene that cannot be fetched or drawn becomes
a plain card with its `alt` line: a missing package never fails a render."""
import os
import re
from typing import Any, Dict, Optional

from PIL import Image

from ... import vector_scene as vs
from ...canvas import Canvas
from ...theme import Theme
from ..base import SceneCtx
from ..registry import Element

ID_RE = re.compile(r"^[a-z0-9_]{3,64}$")
CACHE_DIR = os.environ.get("VECTOR_SCENES_DIR", "/tmp/vector_scenes")
_FOLDERS: Dict[str, Optional[str]] = {}   # catalog id -> its folder on local disk, or None when it could not be fetched (not tried again for every frame)


def _sanitize(props: Dict[str, Any]) -> Dict[str, Any]:
    props = props or {}
    cid = str(props.get("catalog_id") or "").strip().lower()
    if cid:
        if not ID_RE.match(cid):
            raise ValueError("vector_scene needs a catalog_id")
        out: Dict[str, Any] = {"catalog_id": cid, "motion": "default"}
        try:
            sec = float(props.get("seconds"))
            if 4.0 <= sec <= 12.0:
                out["seconds"] = round(sec, 1)
        except (TypeError, ValueError):
            pass
        alt = " ".join(str(props.get("alt") or "").split())[:70]
        if alt:
            out["alt"] = alt
        return out
    sid = str(props.get("scene", "")).strip().lower()
    if sid not in vs.scene_ids():
        raise ValueError("vector_scene needs a known scene")
    return {"scene": sid}


def package_folder(cid: str) -> Optional[str]:
    """The local folder of a catalog scene: fetched once per container (to a temporary name, then renamed: a half download is never used), None when that failed."""
    if cid in _FOLDERS:
        return _FOLDERS[cid]
    folder: Optional[str] = None
    try:
        if not ID_RE.match(cid):
            raise ValueError("bad id")
        final = os.path.join(CACHE_DIR, cid)
        if os.path.isfile(os.path.join(final, "manifest.json")):
            folder = final
        else:
            from common import vector_catalog

            part = os.path.join(CACHE_DIR, f".part-{os.getpid()}")
            got = vector_catalog.fetch_package(cid, part)
            os.makedirs(CACHE_DIR, exist_ok=True)
            try:
                os.replace(got, final)
            except OSError:   # another thread or an earlier run put it there first
                pass
            folder = final if os.path.isfile(os.path.join(final, "manifest.json")) else None
    except Exception as e:  # noqa: BLE001 - no package (not in the bucket, no rights, no network): the card below
        print(f"VECTOR_SCENE_FETCH_FAILED {cid} {type(e).__name__}: {str(e)[:160]}")
        folder = None
    _FOLDERS[cid] = folder
    return folder


def _card(cv: Canvas, props: Dict[str, Any], lt: float, theme: Theme, ctx: SceneCtx) -> None:
    """What is shown when the scene itself cannot be: the theme's background and the scene's caption line, if it has one."""
    cv.background(theme, lt)
    alt = str(props.get("alt") or "")
    if alt:
        fr = ctx.frame
        cv.text(fr.W / 2, fr.H / 2, alt, "semibold", 56 if len(alt) <= 34 else 44, (*theme.text[:3], 255), anchor="mm")


def _draw(cv: Canvas, props: Dict[str, Any], lt: float, dur: float, theme: Theme, ctx: SceneCtx) -> None:
    # The finished picture is the canvas at half its pixel size (the renderer reduces 2x): the scene is drawn at that size (at most vector_scene.MAX_RASTER_SIDE on
    # its long side, enlarged above that) and pasted doubled with NEAREST (the 2x reduce gives the very same pixels back).
    w, h = max(2, cv.im.width // 2), max(2, cv.im.height // 2)
    try:
        if props.get("catalog_id"):
            folder = package_folder(props["catalog_id"])
            if folder is None:
                raise RuntimeError("no package")
        else:
            folder = os.path.join(vs.DIR, props["scene"])
        frame = vs.frame_for(folder, w, h, max(0.0, lt), dur)
    except Exception as e:  # noqa: BLE001 - never a failed render for a picture
        if props.get("catalog_id") and _FOLDERS.get(props["catalog_id"]):
            print(f"VECTOR_SCENE_DRAW_FAILED {props.get('catalog_id')} {type(e).__name__}: {str(e)[:160]}")
            _FOLDERS[props["catalog_id"]] = None
        _card(cv, props, lt, theme, ctx)
        return
    cv.im.paste(frame.resize(cv.im.size, Image.NEAREST), (0, 0))


ELEMENTS = [
    Element(
        name="vector_scene", family="Media",
        doc="- vector_scene: {catalog_id: id of a cartoon scene of the catalog}. Offered to the director only by the cartoon-scene policy.",
        sanitize=_sanitize, draw=_draw, cues=lambda props, dur: [],
        samples=[{"scene": "forest_path"}, {"scene": "seaside"}],
        formats=("16:9", "9:16", "1:1", "4:5"),   # full bleed in every shape: the scene covers the frame (engine/vector_scene.frame_for)
        hidden=True, min_seconds=4.0,   # how many per video is the policy's decision (engine/vector_policy.py), not a fixed number here
    )
]
