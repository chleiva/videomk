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


## Characters: rigged vector children (prototype, 2026-11-27)
The "next prototype" of the section above: four cartoon children who walk, wave, point, blink and talk, drawn as separate vector pieces and driven by a small bone rig. Offline demo only; the planner cannot pick it.

**Pipeline** (all offline except the render):
1. `scripts/vector_character_sheet.py`: ONE parts sheet per child from `gpt-image-2.6-flare` (1536x1024 medium, **USD 0.0358 per sheet**, ledger `docs/image_catalog/spend_log.jsonl`, run `vector-character-proto`). The prompt fixes the layout (row 1 head with a BLANK face, torso, upper arm, lower arm + hand; row 2 upper leg, lower leg + side-view shoe, eyes open, eyes closed; row 3 three mouths) on a plain background. The model followed the layout in 5 of 5 tries and returns real transparency.
2. `scripts/vector_character_build.py`: cuts the pieces by their transparency (connected shapes, eye pairs merged), names them by reading order (refuses a sheet that does not give 11 pieces), cuts the torso's own hanging sleeves away (the rig has separate arms) and closes the cut with an outline, finds each piece's joints (top centre = pivot, bottom centre = where the next piece hangs), and traces every piece with `vtracer` (2x upscaled first, `cutout`, spline): **0.4 to 0.55 MB of SVG per child**. Output: `engine/assets/vector_characters/<id>/` (11 SVGs + `manifest.json`).
3. `engine/vector_character.py` (runtime, Pillow + numpy + resvg-py): pieces are rasterised once at the size shown, then each frame turns them about their joints and pastes them. The maths is separate and tested (`tests/test_vector_character.py`, 17 tests): `two_bone_ik` (knee in front), `walk_feet` (planted-foot cycle), `walk_period`, `arm_angles` (idle / walk / wave / point), `blink`, `mouth_for` (hysteresis), `speech_envelope`.
4. `scripts/vector_character_demo.py`: the story. A native-SVG park (sky, clouds, hills, trees, ground with the path and fence, foreground tufts; tiles that wrap sideways, rasterised once with resvg), four children, one butterfly, a fact card, captions, Polly voices (one per child, cached) and music (`playful-kids`, from the untracked `backend/music-draft/`).

**Why feet do not skate.** The leg is solved by two-bone IK to a foot target. During stance the target slides back at constant speed, so if the ground moves at that speed the planted foot is still in the world: `walk_period(stride, g) = 2 * stride / g`, and the walk phase is `pi * distance / stride` where distance is what the ground layer has scrolled (the same number drives the scenery). `test_planted_foot_stays_on_the_ground_and_does_not_slide` checks the foot's world x is constant to 1e-6 over a stance. When the children stop, the feet blend to the standing pose over about 0.8 s while the ground eases to zero (a little residual slide there).

**Lip sync.** The speaking child's mouth takes one of three shapes from the per-frame RMS level of that line's audio (closed / half / wide, with hysteresis so it does not chatter). Eyes: blink every 3.1 to 4 s; once the butterfly arrives all four look toward it (eye shift plus a small head tilt).

**Story (22 s, EN and ES):** four friends walk home; "Look! A monarch butterfly!" (they slow and stop); "It's beautiful!"; Nora explains with a fact card (4,000 km a year, under 1 g) while she points; Sam adds the weight; "They fly all the way to Mexico for the winter"; everybody waves goodbye as the butterfly leaves.

**Spend:** 5 sheets (1 test + 4) = USD 0.18 of the 1.50 cap; Polly generative about USD 0.01 per language.

**Limits seen:** characters are front-facing cut-outs (a walking puppet, not a turning body); the far arm and leg are the same piece darkened; an arm raised over the torso can show the shirt's sleeve cap; a different layout from the model needs a fresh sheet (the build refuses it); the piece joints use fixed proportions (`HEAD_U`, `TORSO_U`, ...) so a very different body shape would need its own numbers. Not done: turning to face left/right, sitting, running (needs another cycle), objects held in hands, a Lottie/Rive export.
