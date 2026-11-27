# Whiteboard-sketch look: phase 0 prototype (2026-11-27)

Tracker item R134. This executes phase 0 of `docs/WHITEBOARD_LOOK_RESEARCH_2026-11-27.md`, reshaped the same day by the owner's direction: **vector first, compare the methods on the same objects before anything else, no library building.** Nothing in the engine, planner or stack was touched; all code is in `backend/scripts/whiteboard_proto/`.

How to read it: **measured** = run today on this Mac; **looked** = I extracted frames and looked at them. I cannot hear the audio or watch motion, so sync and "feel" are judged from frames and from the timing report, not from playback. The owner's viewing is the real test.

## 1. What exists

Everything is in `~/Downloads/videomk-whiteboard/` (not in git). Phone-sized copies with one-line captions are in `web/` (`web/captions.json`).

| File | What |
|---|---|
| `whiteboard_water_cycle_en.mp4` | The video: 43.5 s, 1080p, English, Polly generative voice (Ruth), quiet music bed, 4.4 MB |
| `whiteboard_water_cycle_es.mp4` | Same board in Spanish: 41.3 s, voice Lucia, Spanish labels. Same code, only the script, labels and anchor words differ |
| `whiteboard_water_cycle_en_4k_passage.mp4` | 9 s of the English video (13.5 to 22.5 s) rendered at real 3840x2160 |
| `contact_sheet_en.jpg`, `contact_sheet_es.jpg` | One frame every 2.3 s |
| `object_sheet_1.jpg` to `_3.jpg` | The generated art exactly as returned (3 calls, 18 objects) |
| `order_strategies_sheet1.jpg` to `_3.jpg` | The two drawing-order strategies, 8 moments per object, for all 18 objects |
| `experiments/` | Methods A, B, C, D: 4K still, three 100 % crops, 12 s draw-on clip each, `stats.json` |
| `web/` | 42 web-friendly files and `captions.json` |

Small reference frames are in `docs/whiteboard/` (1.3 MB).

## 2. The four methods, same six objects and one label

Sun, rain cloud, plant, mountain, waves, simple person, label "evaporation". All four are vector and rasterised by resvg at the output size.

| | Method | Line quality at 4K (looked) | Likeness (looked) | Cost per object (measured) | Time per object (measured) |
|---|---|---|---|---|---|
| A | Image-model art traced to **filled outlines** with vtracer, revealed along a hidden centre line | Smooth | Best: exactly the generated drawing | USD 0.0063 (USD 0.038 per sheet of six) | 7 to 8 s per sheet, plus 0.1 to 0.4 s tracing |
| B | Image-model art reduced to **centre-line strokes** (smoothing cubic splines, round caps, slight pressure); the stroke is the art | Smooth | Close, but looser: sun rays shorter and uneven, the cloud's cusps soften, joins on the plant's stem are rougher | same | same |
| C | A language model (Sonnet 5.5) **writes the strokes**, then looks at its drawing and fixes it, twice | Smooth | Recognisable but cruder: stick person, odd mountain, proportions differ between objects | USD 0.013 to 0.021 | 6 to 11 s |
| D | **Hybrid**: A's outlines with line weight equalised, colour in the areas the line encloses, connectors (arrows, underlines) drawn by code with B's stroke renderer | Smooth | Same as A, plus colour | same as A | same as A |

**Winner: D.** The pixelation the owner saw in the first speed test is gone in every method, because nothing is an upscaled picture any more. The methods differ in how good the drawing is, and A/D keep the image model's drawing intact while B and C lose some of it. The video uses D.

Why B loses detail: a centre line is shorter than the stroke it came from (line ends) and bends where three lines meet. A hides both, because its centre line is only the hidden reveal path.

## 3. How the video is made

1. **Art** (`gen_art.py`): one fixed style paragraph, six objects per 2048x1152 image, same model and key path as the image catalog (`gpt-image-2.6-flare`, medium quality). The model returned black ink on a transparent background.
2. **Vector** (`vectorize.py`): each object is enlarged 4x and traced by vtracer to spline outlines. Line weight is equalised across objects at render time by a vector offset (an SVG stroke added to or cut from the shape): every drawing on the board has a 22-unit line, whatever size it is shown at.
3. **Hidden pen path** (`trace.py`, own code, NumPy and SciPy only): Zhang-Suen thinning, centre line as a graph, short spurs dropped, then ordered (section 4). No autotrace, no CLIPasso.
4. **Reveal**: for each ink pixel, the time the pen passes the nearest centre-line point, with a round front. A frame shows the real art where that time has passed. Lines that are close together never uncover each other early.
5. **Colour**: areas fully enclosed by the line are found from the art itself, vectorised, and coloured in with a diagonal zigzag right after the outline. A fill cannot miss its shape.
6. **Labels**: Patrick Hand (SIL OFL 1.1; licence file read and bundled as `fonts/OFL-PatrickHand.txt`). The letters are the font's own outlines, rendered from the font at output size, revealed letter by letter along each letter's centre line. Covers the Spanish accents and ¿.
7. **Connectors** (`primitives.py`): arrows, wavy rising arrows, dashes, rain, drops, underline, loop arrows; strokes with a slow sideways drift, not a tremble.
8. **Narration** (`narrate.py`): one Polly generative call per sentence through `engine/tts.py`, words placed by `engine/align.py` (confidence 1.0 on all 20 sentences). Every item ends 0.15 s after its word starts; one pen; up to 1.6x faster when items collide.
9. **Board and camera** (`board.py`, `water_cycle.py`): a 3840x2160-unit board, seven named views, eased pans, final pull-back. A marker follows the growing end of the line and changes colour with the ink. No hand.
10. **Render**: Pillow and NumPy, a frame is a pure function of time. Finished items are cached and only items being drawn are recomposited; I checked 63 random frames against a full recomposite and the difference was 0. `--from/--to` renders any passage alone, which is how the 4K passage was made. One niced ffmpeg, no frame files.

Deviations from the research note, with the reason:
* Sea is generated art in blue ink, not a code primitive: it looked better and tests tinting.
* Three rising arrows are tied to three words ("water", "gas", "vapour") instead of one, to fill a 5 s gap with nothing to draw.
* No "code strokes only" side-by-side video: experiment C covers that question.

## 4. The two open questions

**(1) Does the automatic drawing order look natural?** Mostly yes for simple objects; not reliably for complex ones.

I tried two strategies and looked at all 18 objects (`order_strategies_*.jpg`):
* **A, naive scan**: every traced piece separately, top to bottom. Visibly mechanical: the sun gets three rays before its circle, the snowflake and the bicycle appear in scattered bits, pen-up travel is 1.2 to 5 times longer.
* **B, chosen**: pieces joined through junctions where one continues the other (always at a plain corner), the stroke that spans the drawing first, then the rest by shortest pen travel with a mild left-to-right, top-to-bottom preference; closed outlines start at the top and run clockwise; equal rows (waves) start with the top one.

B gives: sun circle then rays clockwise; cloud, walking person and mountain as one continuous line; waves top to bottom, left to right; house roof, walls, door, window. Where it is weaker (looked):
* The standing person's body is drawn before the head; the plant grows from the soil up, with one leaf before the stem reaches it.
* The bicycle starts with a wheel and the frame arrives in pieces; the light bulb's filament and base are plausible but not how a person would do it.
* Where a later line meets an earlier one, a small stub of the later line can show a moment early. Small, but visible if you look for it (the mountain's snow line).

So the hidden-path design does what the research hoped: the order is forgiving because the art is always correct at the end. For a library, each item still needs a look at its 2 s reveal strip, and complex items would benefit from the part-naming pass (a cheap vision call that names parts so they are drawn whole). I did not need the fallback (C) for any object.

**(2) Can the image model hold one clean, even marker style?** Yes, on this evidence: three separate calls, 18 objects, one style. No shading, no grey, no text, no stray marks, layout obeyed 3 of 3. Measured line width 15.1 to 18.8 px across all 18 (16.2 to 18.8 without the river, which has the most detail). The remaining spread is removed at render time. 18 objects is not 300; the first real batch should measure width and reject outliers as planned.

## 5. What looks good, what does not (looked)

Good:
* Lines are clean at 1080p and at 4K, in stills and in the 4K passage.
* One consistent style across drawings, labels and connectors; colour sits exactly inside the shapes.
* The final pull-back reads as one diagram.
* Spanish worked with no code change.

Not good enough yet:
* **The style is "clean icon", not "loose hand sketch".** It is closer to a tidy infographic than to RSA Animate. If the owner wants more hand, the style prompt is where to change it, and that needs its own small test.
* **The pen is idle too much**: busy 35 % of the time (EN 15.3 of 43.5 s), against the 50 to 70 % target. The board needs a few more items, or slower, longer strokes.
* **Camera framing is hand-set and sometimes cuts a neighbour**: in the mountain view the plant is cut by the bottom edge, and the title is cut on the left in the sky view. A layout step must choose views that do not slice objects.
* The board is a little crowded in the middle; "condensation" sits far from its cloud.
* Two items finish late: sea +0.17 s (EN and ES), heat rays +0.18 s (ES).
* The marker is a simple drawn shape. Acceptable, not charming.
* Colour fill is a flat zigzag wipe; real marker colouring has overlap and texture.

## 6. Measured cost and speed

| | Measured |
|---|---|
| Image, six objects, 2048x1152 medium | USD 0.0377 to 0.0378, 7 to 8 s |
| Per object (sheet of six) | USD 0.0063 |
| Language-model strokes, 1 draw + 2 fixes | USD 0.013 to 0.021 per object |
| Narration, Polly generative | USD 0.017 (EN, 553 characters), USD 0.018 (ES) |
| **This video, all-in** | **USD 0.054**: one sheet 0.038 + narration 0.017 (no script or planning call: the plan was written by hand) |
| **Total spend today** | **USD 0.26** of the USD 3 cap (3 sheets 0.113, method C 0.111, narration 0.035) |
| Tracing and vectorising | 0.1 to 0.4 s per object |
| Board build | 2.7 to 4.4 s at 1080p, 4.4 s at 4K |
| Render, 1080p | **52 to 59 ms per frame including x264** (1306 frames in 77 s) |
| Render, 4K | **100 ms per frame including x264** (270 frames in 27 s) |
| File size | 4.4 MB for 43.5 s at 1080p (about 0.8 Mbit/s with audio, crf 18) |

The research note's 10 ms per frame was for bare strokes with no camera. With the camera, colour, marker and a board held at up to 1.6x the output size it is about 55 ms at 1080p: the same range as today's scenes, not faster. All numbers are from this Mac while it was busy with another build; nothing was run on Lambda.

## 7. What phase 1 should change

1. Decide the style with the owner first (clean icon as now, or looser). Everything else depends on it.
2. Keep method D and the package as vector: outline SVG, fill SVGs, ordered centre-line path, measured width. Review each library item as a reveal strip, not a still.
3. Add the part-naming pass for objects with more than about 8 strokes, and fix the early stub where lines meet.
4. A layout step that places items in zones and derives camera views that never cut an object; today both are hand-set numbers in `water_cycle.py`.
5. Plan for pen-busy 50 to 70 %: more items per sentence, or pacing rules.
6. Move the thinning and tracing off SciPy if it must run in the engine layer for generated misses (the engine has only Pillow, NumPy and resvg); for the library it runs offline, so this only matters for misses.
7. Measure render time on Lambda, and 9:16.
8. Nicer marker and a textured colour fill.

## 8. Not verified

* Playback: I did not hear the audio or watch the video in motion.
* Lambda timings; 9:16, 1:1 and 4:5 layouts; languages other than English and Spanish.
* Style consistency beyond 18 objects.
* Whether the planner can write such a board by itself: this plan was written by hand.
