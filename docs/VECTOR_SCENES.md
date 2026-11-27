# Layered vector scenes (prototype, 2026-11-27)

Owner idea: flat-cartoon art stored as **vectors**, so it is sharp at any resolution (real 4K without paying for 4K video), tiny, and cheap to animate. The old experiment
(`~/code/animations`: PNG -> `vtracer` -> SVG -> Manim) made one fused shape, so only the whole picture could move. The fix tried here: **separate depth layers**, each vectorised on its own,
moved at different speeds.

## What exists
* **Element `vector_scene`** (`engine/scenes/elements/vector_scene.py`, tests `tests/test_el_vector_scene.py`). `hidden=True`: **the planner does not list it**, nothing in a user's video can pick it. Props: `{scene: forest_path | seaside | mountain_cabin}`.
* **Runtime** `engine/vector_scene.py`: Pillow + numpy + `resvg-py` only (added to `layers/engine_deps/requirements.txt`, 1.4 MB manylinux wheel; and to `requirements-dev.txt`). The SVG layers are rasterised once per (scene, size) at the size shown, then each frame moves them: affine map (parallax + push-in), a sheared mesh (sway of foliage), horizontal drift (clouds), vertical bob (water). Pure function of the time.
* **Bundled art** `engine/assets/vector_scenes/<id>/` (manifest + one SVG per layer, 0.35 to 0.83 MB per scene).
* **Offline tools** (never run in Lambda): `scripts/vector_scene_art.py` (OpenAI flat-cartoon picture, about USD 0.037, ledger in `docs/image_catalog/spend_log.jsonl`), `scripts/vector_scene_build.py` (picture -> layers -> SVG), `scripts/vector_scene_demo.py` (render a scene to mp4 and time it).

## How a picture becomes layers (`vector_scene_build.py`)
1. Relative depth from Depth-Anything-V2-small (ONNX, Apache-2.0, public weights, runs on CPU in about 1 s, free).
2. The picture is cut into flat-colour regions (k-means colours, outline strokes set aside); **each region gets one depth** (median), so a depth band never slices through an object.
3. Band 0 = sky (blue areas touching the top, pale haze bands, the sun); clouds become their own drifting layer; the rest is split by depth cuts you choose per picture.
4. Each layer keeps its own pixels; what a nearer layer hides is filled with the colour of the nearest same-layer pixel (outline strokes excluded), so a gap that parallax reveals is flat colour, not a dark fringe. Every layer is opaque where it or anything nearer is, so there are no seams.
5. `vtracer` (spline mode) turns each layer into an SVG.

## Measured (this Mac, load average about 19 from other jobs: upper bounds)
| | 1080p | 4K (3840x2160) |
|---|---|---|
| Rasterise the SVG layers (once per scene and size) | 0.8 to 1.3 s | 2.7 to 4.0 s |
| One frame (parallax, sway, bob, drift, composite) | 160 to 230 ms | 0.95 to 1.1 s |
| 8 s clip (240 frames) incl. x264 | 45 to 75 s | 227 s |
| mp4 size | 1.5 to 3.8 MB | 9.6 MB |

SVG weight per scene: forest 621 KB (5 layers, 840 paths), seaside 347 KB (6 layers), mountain cabin 826 KB (7 layers). Memory: the 4K scene holds six 4645x2613 RGBA rasters, about 290 MB.
Reading: 1080p is fine for the engine (the contract wants a frame well under 0.3 s: met). **4K is about 5x slower**: a 30 s render chunk would be about 900 frames, about 15 min, over the 10 min Lambda chunk limit, so 4K scenes would need 10 s chunks or a faster path (rasterise only the visible window, skip the mesh when sway is off, cache the static part of the composite).
True 4K edges are a little crisper than a 1080p frame upscaled (visible on outlines at 100%); flat colour areas hide most of the difference.

## What looks good / what does not
* Looks good: the picture keeps the original's bold outlines and flat colours at any size; parallax plus slow push-in reads as depth; clouds drift, water bobs, plants sway; no black gaps; no popping between frames.
* Imperfect: outline strokes sometimes double at a layer cut (a thin second stroke); an object whose parts have different depths can still split (the boat did, until the sky/sea rule was fixed); the depth model reads overhead canopy as far, so a forest roof moves like background; vtracer slightly wobbles curves and loses fine texture.
* **Photographs do not work.** The catalog's house-v2 images are photographs: vtracer collapses soft gradients into a few flat blobs (tried on the sunrise mountains: 3 layers, 18 KB, unrecognisable). This only suits flat-cartoon source art, so a cartoon style would be a second, separate catalog.

## Cost and speed
* Art: one cartoon picture is about USD 0.037 (2048x1152 medium). Depth, regions, vtracer: free (about 5 s on CPU). Nothing per second of video, unlike a generated clip (USD 0.07 per second at 720p).
* Render: see the report; the work per frame is a few RGBA transforms of 1.2x oversize layers (the 4K scene holds six 4645x2613 RGBA rasters, about 290 MB, so a 4K render of this scene needs a render Lambda with several GB).

## Not done / next
* The planner cannot choose it. To make it a real scene type: a catalog of such scenes (embedding search like the image catalog), an element doc line, a rule for when a cartoon beat fits the video style, and the framed layout for 9:16 (it now falls back to a framed card).
* A **character** that walks or waves needs more than layers: draw it as separate parts (head, torso, arms, legs on transparent layers), vectorise each, and animate with a small bone rig (rotations about joints, a walk cycle as sine curves) or Lottie/Rive. That is the next prototype.
* Pin objects to one layer (`--merge`), or generate the scene already as separate transparent layers.
