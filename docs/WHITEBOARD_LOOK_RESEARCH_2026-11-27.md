# Whiteboard-sketch explainer look: can we build it, and how (research, 2026-11-27)

Tracker item R134. Owner's ask: the YouTube "whiteboard" style, where text and simple figures appear as if drawn by hand while the narrator explains, fully automatic, e.g. the water cycle (a sun, a plant, evaporation, rain). **Nothing is built; no product code was changed.** This note says whether it is possible now, how to build it on our engine, what it costs and what could go wrong.

How to read it: **measured** = I ran it today or it is a number already measured in this repo; **sourced** = a page I read today (link at the end); **assumed** = my estimate, not tested.

## 1. The answer in ten lines

1. **Yes, it is possible now**, with what the engine already has. The animation itself is the easy part; **where good drawings come from is the whole problem.**
2. Drawing a set of ordered strokes in time with the narration is trivial for our renderer: **measured about 10 ms per 1080p frame** (today's scenes are 57 to 70 ms, vector scenes 160 to 230 ms). A whiteboard video would render faster and produce smaller files than any look we have.
3. A language model writing stroke coordinates "blind" gives recognisable but amateur doodles (**measured today**, section 3.3): fine for arrows, waves, boxes, underlines; not "really good quality" for a plant or a person.
4. The approach I recommend is what VideoScribe and Doodly do by hand, automated: **the art is a clean marker drawing made by the image model in one fixed house style; a traced centre line is used only as the invisible path along which the art is revealed.** The viewer sees the real drawing appear along its own lines.
5. Drawings come from **our own library first** (about 300 common explainer objects, searched by meaning like our catalogs), generation only for misses, and every generated miss joins the library.
6. Handwriting: an open-licence handwriting font revealed letter by letter along the letter's centre line. Arrows, underlines, boxes, braces: pure code.
7. The planner writes a **board** per scene: what to draw, in which zone, in which order, tied to which narration words. The existing word timing (`engine/align.py`, `engine/sync.py`) already gives what is needed: a drawing ends as its word is said.
8. Cost: library about **USD 15 to 25 once**; per video about **the same as today, plus USD 0.01 to 0.05** when something has to be generated. Render cost goes down.
9. Effort: prototype of one water-cycle scene **1 to 2 days, under USD 3**; a shippable first version about **3 weeks**; all aspects, 4K, camera and characters about **2 more weeks**.
10. The one thing not proven: that automatic centre-line tracing of image-model marker art gives a reveal that looks hand-drawn (order and direction of strokes). The prototype exists to settle exactly that, and the design tolerates imperfect tracing because the traced line is never shown.

## 2. What the engine already has that this reuses

| Need | Already there | Gap |
|---|---|---|
| Word-level narration timing | `engine/align.py` (mean error 80 ms, p90 198 ms, measured in docs/SYNC.md), `engine/sync.py` anchors a reveal to the word that names it | A drawing has a duration, so it must be anchored to END at the word, not start |
| Frames drawn in Python, pure function of time, 30 s chunks | renderer, `engine/frame.py` design units for 16:9, 9:16, 1:1, 4:5, 4K as a scale | A board that persists across scenes (the chunk hash already includes "the scene before") |
| SVG rasterising on Lambda | `resvg-py` in the engine layer (docs/VECTOR_SCENES.md) | none |
| Image generation in a fixed style, with a cheap vision check and a spend cap | `scripts/vector_catalog_generate.py` pattern, about USD 0.036 per picture, Haiku-class check | a "marker line drawing" house prompt |
| Raster to vector | `vtracer` (MIT) used offline | vtracer traces OUTLINES of shapes; a centre line needs another step (section 3.2) |
| Catalog searched by meaning | `common/vector_catalog.py`: Cohere Embed v4, index file shipped in the Lambda zip, `MIN_SCORE` cut | a third catalog with the same pattern |
| Parts-sheet trick (many pieces in one generated image, cut apart) | `scripts/vector_character_sheet.py` followed the layout 5 of 5 times | reuse for "six objects on one sheet" |
| Director that picks a look by topic | `engine/background.py`, `engine/vector_policy.py` | a rule for when a video is a whiteboard video |

## 3. How the look is produced: the options, compared honestly

### 3.1 The basic trick
A drawing "draws itself" when each line is shown progressively from its start to its end, lines in a sensible order, a pen tip at the growing end. In browsers this is the well-known SVG `stroke-dasharray` / `stroke-dashoffset` animation (Jake Archibald, 2013; Vivus.js). In our renderer no dash trick is needed: we hold the board as an image and each frame add the next few millimetres of line. Both need the same input: **the drawing as an ordered list of pen strokes (centre lines), not as filled shapes.** That is the constraint that decides everything below.

There are two ways to use the strokes:
* **Stroke is the art:** we draw the stroke itself with a round pen. Tiny data (a few KB per drawing), perfect at 4K, but the line has constant width and the drawing is only as good as the strokes.
* **Stroke is an invisible reveal path:** the real art (a nicer drawing with marker texture, varying line weight, colour) sits underneath, hidden; a wide invisible stroke travels along the centre line and uncovers it. This is exactly what VideoScribe documents for brush art ("copy the stroke, set it to 0 % opacity, VideoScribe draws along the transparent stroke and reveals the brush stroke beneath") and what Doodly calls "draw paths" (sourced). It forgives an imperfect centre line, because the path is never seen.

### 3.2 Options table

| | Option | Quality today | Stroke order | Cost per drawing | Runs on Lambda | Licence | Verdict |
|---|---|---|---|---|---|---|---|
| a | **Stroke reveal of true stroke SVG** | as good as the strokes; constant-width "plotter" line unless textured | given by the file | render only | yes (measured, 3.3) | none needed | The renderer for arrows, underlines, boxes, handwriting skeletons. Not a source of drawings |
| b | **Centre-line tracing of line art** (thinning/skeleton, then follow the lines) | clean on thin, clean marker lines; weak at junctions, blobs, filled areas, and it loses line weight. `potrace` does not do centre lines (its own FAQ, sourced); `autotrace -centerline` does but is **GPL**; `vtracer` (MIT) is outline only; `skeleton-tracing` (MIT, Lingdong Huang) and plain Zhang-Suen thinning are free and small; deep-learning tracers exist (Deep Sketch Vectorization, SIGGRAPH 2024, MIT code; "virtual sketching", Apache-2.0) but are GPU research code | must be invented: none of these gives a human drawing order | free, CPU, about 1 to 5 s (assumed) | thinning yes; deep models no | MIT options exist; avoid autotrace (GPL) | **Use, but only to get the hidden reveal path** (so its flaws are not seen). Not verified on our art today |
| c | **Language model writes the strokes** | simple icons: recognisable doodles; figures, hands, animals: poor. Benchmarks agree that models degrade as drawings get complex (SVGenius 2025; StarVector's authors say intricate shapes are hard). Style is whatever the model does that day | natural: the model draws part by part, and can name the parts | about USD 0.02 blind, about USD 0.05 with a "look at it and fix" loop (SketchAgent paper: USD 0.05 per sketch with Claude 3.5 Sonnet, sourced) | yes (a Bedrock call) | none | Good for **connectors and simple diagrams**; fallback for misses; not the main art source |
| d | **Image model draws a clean marker drawing, then trace** | the best-looking art available automatically: image models are very good at "black marker doodle on white, thick even line, no shading". One fixed prompt gives one consistent style (we already do this for two catalogs) | must be computed (heuristics plus an optional cheap vision pass) | about USD 0.036 per image (measured price); about USD 0.006 per object when six objects share a sheet (assumed) | generation is an API call; tracing offline or in a small step | our own generated assets | **The art source** |
| e | **Sketch research models** | Quick, Draw! data and Sketch-RNN: 20-second doodles by the public, charming but crude, 345 categories. CLIPasso and DiffSketcher: abstract "artist sketch" look, strokes are optimised curves with no natural order, minutes on a GPU per sketch (assumed from the methods; not run). SketchAgent: ordered strokes on a 50x50 grid, doodle quality | Sketch-RNN, SketchAgent: yes; CLIPasso, DiffSketcher: no | GPU time, or USD 0.05 (SketchAgent) | only SketchAgent (it is just a model call) | Quick, Draw! **CC BY 4.0** (attribution needed); Sketch-RNN Apache-2.0; **CLIPasso CC BY-NC-SA: not usable commercially**; DiffSketcher MIT; SketchAgent MIT (all licence files read today) | None as the main path. SketchAgent's method is option (c) done properly |
| f | **Own library of drawings with stroke order, searched by meaning** | as good as we make it, because every item is looked at once before it ships; consistent style; instant and free at video time | stored with the item, reviewed once | about USD 0.05 to 0.08 per accepted item to build (assumed, from the vector catalog's measured USD 2.375 for 46 scenes) | yes (S3 read plus the index in the zip) | ours | **The main source at video time** |
| g | **Reveal a raster with a moving mask** (wipe, diagonal scribble) | reads as "an image being uncovered", not as drawing. Doodly does this for imported images with no paths ("scribbled diagonally ... without any drawing action", sourced) and users are told to add paths by hand | none | free | yes | none | Poor alone. **Becomes good when the mask follows the traced centre line** (that is b + d, the recommendation) |

### 3.3 Small experiment run today (measured)
A six-second 1080p clip of a water-cycle board: sun, sea, three rising arrows, cloud, mountain, rain, a plant, two colour fills. **I (the language model) wrote every stroke as coordinates, blind, with no look at the result**, which is option (c) in its cheapest form. Script: Pillow only, strokes smoothed (Catmull-Rom), a little hand wobble, drawn incrementally on a 2x canvas and reduced, piped to x264.

| | Result |
|---|---|
| Strokes / line segments | 33 / 1,818 |
| Drawing work per frame | **0.8 ms** |
| Reduce 3840x2160 to 1920x1080 per frame | **9.0 ms** |
| Whole clip, 180 frames, including x264 | **3.4 s** wall time (this Mac, load about 3) |
| Peak memory | 422 MB |
| mp4 size | **78 KB for 6 s** (about 100 kbit/s: a white board compresses extremely well) |

What the picture showed (I looked at the frames):
* Recognisable at once: sun with rays, waves, wavy arrows, mountain with a snow line, rain.
* Amateur: the cloud outline has a small loop where two bumps meet; the plant is weak; **both colour fills landed off their shapes** (a yellow block over the sun, a green bar beside the leaf).
* The hand wobble I added was too fine and regular; it reads as "shaky", not "hand-drawn".

Reading: the rendering side is solved and cheap. Blind model-written coordinates are good enough for primitives and not for the drawings the owner has in mind. With a look-and-fix loop they would improve (this is what SketchAgent does), but they would still be doodles. This is why the recommendation takes the art from the image model.
Files (temporary, not in the repo): `/private/tmp/claude-501/-Users-chleiva-code-videomk/d19b0e3e-ca88-5b4b-b8d2-dfc97f1d79f0/scratchpad/wb/out.mp4`, `/private/tmp/claude-501/-Users-chleiva-code-videomk/d19b0e3e-ca88-5b4b-b8d2-dfc97f1d79f0/scratchpad/wb/out_179.png`, `/private/tmp/claude-501/-Users-chleiva-code-videomk/d19b0e3e-ca88-5b4b-b8d2-dfc97f1d79f0/scratchpad/wb/wb.py`.

### 3.4 The side questions

**A drawing hand, or not.**
* Sourced: a 2023 study (Smart Learning Environments, 84 students) compared a hand drawing the content, a hand pushing finished content in, and no hand. The drawing hand gave higher motivation than the pushing hand and did not add mental load. I could not read the full results (paywall redirect), so whether the hand improves recall over no hand is **not verified**. A separate 2023 study (Heliyon) found that drawing the picture progressively beats showing it finished: the drawing-on effect is the part that matters.
* Practical: a photographic hand covers a lot of a 9:16 frame, needs licensed or self-shot assets at 4K, and looks cheap when it jumps between drawings. VideoScribe lets users remove it; Golpo sells "Pen in hand" as one style among ten.
* Recommendation: **version 1 shows a small marker tip only** (a vector nib at the growing end of the line, moving between drawings along a short arc instead of jumping). A real hand is an option later (one self-shot hand and marker on a transparent background, a few poses; no licence question).

**Handwriting.**
| Way | Look | Stroke order | Licence | Verdict |
|---|---|---|---|---|
| Single-line fonts (Hershey; the "EMS" SVG fonts used by pen plotters; Relief SingleLine) | plotter-like, thin; some are pleasant | paths are roughly in writing order, not guaranteed | Hershey: free with acknowledgment; EMS fonts are derived from **SIL OFL** fonts; Relief SingleLine **OFL** (file read today) | Usable for small labels; accents and non-Latin coverage must be checked per font (not checked) |
| Ordinary handwriting font, revealed along each letter's centre line (the reveal-path trick) | a real marker handwriting look, full language coverage of the font | letters appear left to right; inside a letter the pen follows the skeleton. At writing speed (a letter in under 0.1 s) nobody can see that the order inside a letter is not exact | Google Fonts handwriting families such as Caveat, Patrick Hand, Kalam are listed as OFL (**re-check the licence file of the chosen font before bundling**; not opened today) | **Recommended.** Same machinery as the drawings |
| Handwriting synthesis (neural, Graves-style) | the most natural | yes | the popular open implementation has **no licence file**, and such models are trained on research-only handwriting data | Do not use |

Rules for legibility: handwriting only for titles and short labels (1 to 4 words), never for sentences; minimum height as for captions; the caption system stays as it is.

**Marker texture.** With the reveal-path approach the texture is in the art itself (slightly uneven black line from the image model, kept as a vector outline traced by vtracer so it stays sharp at 4K). For code-drawn strokes: round ends, a slow width change of about 10 %, a low-frequency wobble (lower and less regular than my experiment), and a faint paper tint on the board. No grain animation: it costs bitrate and looks noisy.

**Colour.** The good examples are mostly black line with one or two accent colours that arrive AFTER the outline (observation from the style, see section 4). Technically: a colour layer under the ink, revealed by a quick zigzag "colouring-in" path inside the shape. To avoid what my experiment showed (fills missing their shapes), the fill region comes from the art itself (flood region of the closed outline, or the colour layer of the generated picture), never from model-written coordinates. Palette: black plus the video theme's accent, plus at most two natural colours (sun yellow, water blue, leaf green).

**Erasing and moving between boards.** Three moves cover it, all cheap because the board is one big picture and the frame is a window on it: (1) **pan** to a fresh area of a board larger than the screen; (2) **pull back** to show the whole board at the end (the classic payoff shot); (3) **wipe**: an eraser stroke path that paints paper colour, or a quick slide of the old board off screen. A new board at each major section, at most about one board per 20 to 40 s.

## 4. What the commercial tools do, and what makes the good ones engaging

| Tool | What it is | How the drawing happens | Automatic? | Price (sourced today unless said) |
|---|---|---|---|---|
| **VideoScribe** (Sparkol) | the classic editor, big library of SVG art | draws SVG **strokes in the order of the file**; brush art needs an invisible stroke on top that reveals it; the hand can be removed | AI drafts the script, voice and images, but a reviewer notes "I still had to shape the video piece by piece" | about USD 36 to 67 per month (third-party listing) |
| **Doodly** (Voomly) | desktop editor, library with built-in draw paths | library art has reveal paths; imported images are "scribbled diagonally" unless the user places path points by hand; SVGs can bring their paths | no | subscription (not checked today) |
| **Vyond, Powtoon** | general animation makers with a whiteboard style | hand-draws their own stock assets | templates, some AI scripting | **not verified today** (my searches returned nothing usable on their whiteboard modes) |
| **Golpo** | prompt or document in, narrated whiteboard video out; styles include "Pen in hand", sharpie sketch, chalkboard | not disclosed | **yes, end to end** | USD 39.99 per month for 20 credits; **colour only from the USD 199.99 plan**; API USD 2 per generation; 9:16 and landscape |
| HeyGen, Agent Opus, NoteGPT, Medeo, Ankon and others | "whiteboard" as one style of an AI video maker | not disclosed; several look like generated sketch images with a reveal effect (my reading of their pages, **not verified**) | yes | various |

So the market has moved to automatic in the last year, and a fully automatic whiteboard video sells for roughly USD 2 a video. Our cost per video is USD 0.07 to 0.15 (measured, docs/COSTS.md). Nobody discloses a method; none of the pages I read claims true stroke-ordered drawing with narration-synchronised strokes, so doing that well is a way to be visibly better, but I cannot prove what they do inside.

**What makes the good ones work** (sources for the first four; the last three are my observation of the style, not sourced: I found no page documenting them for RSA Animate, whose early videos were filmed live drawing, sped up):
* **Progressive drawing is the point.** Drawing the picture as it is explained beats showing it finished (Heliyon 2023; a 521-adult study found whiteboard animation beat slides, text and audio, still a week later; treat the "15 % better recall" figure with caution, it comes from the studio that makes them).
* **One idea per scene, one main drawing per key sentence**; do not crowd the board (Voomly, practitioner guides).
* **Narration about 150 to 160 words a minute**, with a one-second breath after a dense point (same sources). If a scene drags, cut words; do not speed the pen.
* **The drawing leads the word slightly**: the viewer watches the line and guesses what it will be, and the word confirms it. This anticipation is the hook. (Our rule below: finish as the word is said.)
* The pen is almost never idle and never frantic: roughly 50 to 70 % of the time something is being drawn.
* **Black first, colour as a reward**: an accent colour lands after the outline, on the thing the sentence is about.
* **The drawings connect**: arrows and lines join them into one picture, and the camera pulls back at the end to show the whole board. That final wide shot is what makes it feel like one explanation instead of a slide show.

## 5. The automatic pipeline for our engine

```
planner (board per scene)  ->  resolve drawings (library | generate)  ->  layout per aspect
      ->  timing against narration words  ->  render in chunks (deterministic)  ->  vision check
```

### 5.1 Data: a drawing package
One folder per drawing, like a vector scene package:
* `art.svg`: the visible art (vtracer outline of the marker drawing, black; optional colour regions as separate paths). Sharp at any size.
* `strokes.json`: the hidden reveal paths in draw order: `[{part: "outline", pts: [...], width}, ...]`, plus fill paths, plus anchors (`top`, `bottom`, `left`, `right`, `centre`) for arrows to attach to. A few KB.
* `meta.json`: title, tags, topics, the two Cohere vectors, total pen length, a default draw time, review status, provenance.
Code-drawn things (arrows, underline, box, circle-around, brace, dotted path, rising squiggles, rain, simple waves) are **primitives**: no package, generated from parameters.

### 5.2 The planner writes a board, not coordinates
Same principle as today ("the director gives meaning, not layout"). Per scene:
```json
{"type": "whiteboard", "board": "continue",
 "items": [
   {"id": "sun",   "draw": "sun",            "zone": "top-left",    "say": "sun",   "color": "yellow"},
   {"id": "sea",   "draw": "sea waves",      "zone": "bottom-left", "say": "sea",   "color": "blue"},
   {"id": "vap",   "arrow": "rising", "from": "sea", "to": "sky",   "say": "vapour"},
   {"id": "lab1",  "write": "evaporation",   "near": "vap",         "say": "evaporation"}
 ],
 "camera": "hold"}
```
* `draw` is a phrase, resolved by catalog search; the planner sees only the top matches for its phrases (as with vector scenes), never the whole catalog.
* `zone` is one of nine named zones (or `near: <id>`); `say` is the narration word the item is tied to. The existing rule "name the item with its own key word, in the order shown" and the one repair attempt already exist for lists (docs/SYNC.md) and apply unchanged.
* Limits in the contract: at most 3 drawings and 2 labels per sentence, at most about 9 items on a board, labels of 1 to 4 words, every item must have a `say` word.
* Fallback: an item with no acceptable drawing becomes a handwritten label in a hand-drawn box, so a miss never leaves a hole.

### 5.3 Where drawings come from
1. **Library** (`w/` prefix in the catalog bucket, index file in the Lambda zip, `MIN_SCORE` cut, same code path as `vector_catalog`).
2. **Miss:** all missing objects of a video go on **one generated sheet** (up to about six objects, the house marker prompt), cut apart, traced, ordered, vision-checked ("is this a <plant>? one object, no text, clean line?"). One image call per video at most, about USD 0.036 and 20 to 40 s (latency assumed), done in parallel with speech. Accepted drawings are **added to the library** after the same check, so misses fall with use.
3. **Still nothing:** language-model strokes for simple shapes, else the label fallback.

Reveal-path building (offline for the library, a small step for misses): thin the black line to a one-pixel skeleton, follow it into polylines, join pieces that continue straight through a junction, drop specks, then order: biggest closed outline first, then inner details, then small marks, each started at its top-left end, next stroke = nearest start; fills last. Optional: a cheap vision call names the parts ("pot, stem, left leaf, right leaf") so parts are drawn whole and in a human order.

### 5.4 Timing
For item i with anchor word starting at `w_i`:
* `end_i = w_i + 0.15 s` (the drawing completes just as the word lands; the 0.15 s covers the measured 80 ms mean timing error);
* `dur_i = clamp(pen_length_i / pen_speed, 0.5 s, 2.5 s)`; colour fill adds 0.3 to 0.5 s right after;
* `start_i = end_i - dur_i`, but never before the previous item's end plus 0.15 s of pen travel (one pen). If items collide, speed the pen up to 1.6x; if they still collide, the later item is drawn right after its word instead of before (logged by the sync check).
* Labels: about 0.07 s per letter.
All of this is a pure function of the plan and the word times, so chunks render the same anywhere and the existing sync report can check it without a model.

### 5.5 Layout for every aspect and resolution
* The board is laid out in **design units** (`engine/frame.py`): zones are a 3x3 grid inside the safe margins for 16:9 and 1:1, a 2-column by 4-row grid for 9:16 and 4:5 (the same zone names map to different cells: "top-left / bottom-left / right" become "top / middle / bottom"). Drawings are scaled to fit their zone; arrows are computed between anchors AFTER layout, so they are right in every aspect. Captions keep their band; the board uses the area above it.
* A wide board can be larger than the frame; the camera is a window (pan, pull back). On 9:16 this is the natural way to show a landscape diagram: follow the pen, then pull back.
* 1080p and 4K are the same vectors at scale 1 and 2. The board is rasterised incrementally (only the new piece of line each frame), so 4K costs a bigger reduce step, not a bigger drawing step (assumed about 4x the 9 ms measured; still far under today's 4K frame).
* Chunks: a chunk that starts mid-board first draws every earlier item complete (fast: rasterise the finished art once), then continues. The chunk hash includes the board's earlier items.

### 5.6 The water cycle, concretely (45 s, about 110 words)

Narration:
> Where does rain come from? It starts with the **sun**. The sun warms the **sea**, the lakes and the rivers, and some of that water turns into an invisible gas called water **vapour**. This is **evaporation**. **Plants** help too: they release water through their **leaves**. The vapour rises, and high in the sky the air is cold, so it turns back into tiny **drops**. That is **condensation**, and it is how clouds form. When the drops get heavy, they fall as **rain** or **snow**. The water runs down the **mountains** into **rivers**, back to the sea, and the journey **starts again**. That is the **water cycle**.

One board, 16:9. Sun top-left, sea bottom-left, plant bottom-centre, cloud top-centre, mountain right, everything joined clockwise by arrows. Times are estimates for a 145 words-per-minute voice; the real ones come from the audio.

| # | Item | Source | Zone | Tied to word (about) | Pen draws | Colour |
|---|---|---|---|---|---|---|
| 1 | "Where does rain come from?" | handwriting | top-centre | "rain" (1.2 s) | 0.2 to 2.2 s | black |
| 2 | Sun with rays | library | top-left | "sun" (3.9) | 2.7 to 4.0 | yellow fill 4.0 to 4.4 |
| 3 | Sea (three wave lines) | primitive | bottom-left | "sea" (6.0) | 5.0 to 6.1 | blue line |
| 4 | Heat rays, sun to sea (short dashes) | primitive | between 2 and 3 | "rivers" (8.0) | 7.2 to 8.0 | yellow |
| 5 | Three wavy rising arrows | primitive | above the sea | "vapour" (12.3) | 10.9 to 12.4 | blue |
| 6 | "evaporation" | handwriting | beside the arrows | "evaporation" (14.0) | 13.3 to 14.2 | black, underline 14.2 to 14.5 |
| 7 | Ground line and a plant | library | bottom-centre | "Plants" (15.3) | 14.6 to 15.9 | green fill 15.9 to 16.3 |
| 8 | Two small arrows off the leaves | primitive | above the plant | "leaves" (18.8) | 18.2 to 18.9 | blue |
| 9 | Arrows continue up to the sky | primitive | centre | "rises" (20.6) | 20.0 to 20.8 | blue |
| 10 | Cloud | library | top-centre | "drops" (26.0) | 23.8 to 25.6, dots inside 25.6 to 26.1 | black, blue dots |
| 11 | "condensation" | handwriting | under the cloud | "condensation" (27.3) | 26.5 to 27.5 | black |
| 12 | Mountain with snow cap | library | right | (scenery, drawn in the pause before "When") | 29.2 to 30.8; camera eases right | black |
| 13 | Rain strokes from the cloud's right side | primitive | above the mountain | "rain" (32.6) | 31.9 to 32.7 | blue |
| 14 | Snowflake on the peak | library | peak | "snow" (33.5) | 33.0 to 33.6 | blue |
| 15 | River down the mountain to the sea | primitive (wavy path between anchors) | right to bottom-left | "rivers" (37.2) | 35.6 to 37.4, arrowhead at the sea 38.6 to 39.2 | blue |
| 16 | Camera pulls back to the whole board; a big loop arrow closes the circle | camera + primitive | whole board | "starts again" (41.3) | 40.2 to 41.8 | accent |
| 17 | "The water cycle", underlined | handwriting | centre of the loop | "water cycle" (43.8) | 42.6 to 44.2, underline to 44.6 | black, accent underline |

Pen busy about 21 of 45 s plus camera and fills: inside the 50 to 70 % range with the fills. Four library drawings (sun, plant, cloud, mountain, snowflake = five), everything else is code. In 9:16 the same items stack: sun and cloud on top, mountain and rain in the middle right, sea and plant at the bottom, and the camera follows the pen downward and back up before the pull-back.

## 6. Quality risks and the cheap controls

| Risk | Control | Cost |
|---|---|---|
| Ugly or inconsistent drawings | One house prompt; the library is built once and every item is viewed on a contact sheet before it ships (as for the vector catalog); generated misses pass the same automatic check | library review: an hour of looking; check about USD 0.0005 per drawing (Haiku-class, as today) |
| Wrong drawing (a "plant" that is not a plant) | Vision check on the FINISHED drawing with the planner's phrase: "what is this?" must match; search score under `MIN_SCORE` means miss, not "closest thing" (the vector catalog note shows why: the water cycle once matched a waterfall) | same call |
| Unnatural stroke order | Hidden reveal path makes exact order matter less; rules (outline, details, small marks, fill; top-left first); optional part naming by the vision model; library items reviewed as a 2 s animation strip, not a still | free, or about USD 0.001 |
| Reveal uncovers a neighbouring line early | reveal width tied to the line width; parts revealed as wholes | free |
| Text legibility | handwriting only for 1 to 4 word labels; minimum size per aspect; a font chosen for clarity; captions unchanged; a measured check that every label fits its zone | free |
| People and children | **Not in version 1.** Then a small fixed cast of very simple marker figures (round head, simple body), each as a set of about 8 library poses (standing, pointing, thinking, happy, sad, walking, carrying, two people talking), generated on one sheet per figure so they match. No rig: on a whiteboard a figure is redrawn in a new pose, it does not move. Faces minimal (dots and a line) to avoid uncanny results | about USD 0.04 to 0.11 per figure (the rig pilot's measured sheet price) |
| Style drift between elements | everything comes from one prompt and one line weight; drawings are normalised at build (line thickness measured from the skeleton, scaled so all items have the same stroke width on the board); generated misses that measure outside the range are rejected | free |
| Abstract topics with nothing to draw (inflation, trust) | the planner is told to use the library's metaphor set (scales, arrows up and down, light bulb, target, clock, coins, handshake, ladder, puzzle) and labelled boxes; if under about half of a video's sentences have something drawable, the director does not choose the whiteboard look | free |
| Too busy or too empty | contract limits (5.2) and a pen-busy check (50 to 70 %) in the existing sync report | free |
| The finished video | the existing idea of a critic on sampled frames: one frame per board at its end, "is anything overlapping, cut off, unreadable?" | about USD 0.002 per video |

## 7. Cost and speed

Prices: image USD 0.036 (measured in this repo, 1536x1024 medium); Sonnet 5.5 USD 2 / 10 and Haiku 5.5 USD 0.10 / 0.50 per million tokens (the list prices in `engine/llm.py`); today's video USD 0.07 for 1 minute and 0.15 for 3 minutes all-in (measured, docs/COSTS.md).

**Per drawing**
| Option | Money | Time | Note |
|---|---|---|---|
| Library hit (f) | 0 | an S3 read | |
| Image model, one object per image (d) | USD 0.036 + check | 20 to 40 s (assumed) | |
| Image model, six on a sheet (d) | about USD 0.006 each | same, once per video | sheet layout obeyed 5 of 5 in the character pilot |
| Language model strokes, blind (c) | about USD 0.02 Sonnet, about USD 0.002 Haiku (assumed token counts: 1.5k in, 1.5k out) | 5 to 15 s | doodle quality |
| Language model with look-and-fix (SketchAgent way) | about USD 0.05 (sourced) | 20 to 60 s | |
| Research models on a GPU (e) | GPU minutes | minutes | not suitable |
| Tracing and ordering (b) | 0 | 1 to 5 s CPU (assumed) | |

**Per video (1 minute, about 10 to 12 drawings)**
| | Today | Whiteboard |
|---|---|---|
| Script | about USD 0.035 | plus about USD 0.01 to 0.02 (the board plan is more output) |
| Speech | about USD 0.03 | same |
| Drawings | n/a | USD 0 when all hit; about USD 0.04 when a sheet is generated |
| Checks | about USD 0.002 | about USD 0.004 |
| Render (Lambda) | about USD 0.025 | lower: about 10 to 30 ms per frame against 57 to 70 (assumed half or less; to be measured on Lambda) |
| **Total** | **about USD 0.07** | **about USD 0.07 to 0.12** |
So it fits inside the USD 0.15 cost per credit of the plans proposal with no change to pricing. Time to make a video: unchanged, or 20 to 40 s longer when a sheet is generated (it runs beside speech).

**Storage.** A drawing package is about 20 to 150 KB (outline SVG) plus a few KB of strokes: 300 items is about 10 to 40 MB in S3, cents per year. The index is about 1.7 MB for 300 items at the vector catalog's measured 5.7 KB per item: still fine inside the Lambda zip. Finished videos are much smaller than today's (measured 100 kbit/s on the test clip), so storage and delivery go down.

**A first library of 300 objects.** One object per image for best quality: 300 x USD 0.036 = USD 10.8; the vector catalog needed about 1.35 pictures per accepted scene, so about USD 15; checks and embeddings under USD 1; style exploration before the batch about USD 3. **Cap: USD 25.** With sheets of six it would be about USD 4, at some loss of detail per object; I would use single images for the 100 most used objects and sheets for the rest. Content: nature and weather, science and lab, body and health, home and food, school, money and business, technology, transport, buildings, time, people-free symbols and metaphors, about 25 per group.

## 8. Recommendation

**Is it possible now? Yes.** Not "partly": every piece exists or is small. What is uncertain is how good the automatic stroke order looks, and how well the image model holds one marker style across 300 objects; both are settled by a two-day prototype for under USD 3.

**What I would build:** our own library of marker drawings made by the image model in one house style, each stored as crisp vector art plus a hidden, ordered centre-line reveal path; a `whiteboard` scene type whose plan is a board (items, zones, words); strokes timed to end on the narration word; handwriting from an open-licence font revealed the same way; arrows and other connectors drawn by code; a marker tip, no hand, in version 1; black line with accent colour arriving after the outline; pan and pull-back camera on a board larger than the screen.

**Phases**
| Phase | What | Effort (one builder) | Spend cap | Exit test |
|---|---|---|---|---|
| 0. Prototype | The water-cycle scene above, 16:9, 1080p, offline script (like `vector_scene_demo.py`): generate 5 drawings in the house style, trace, order, reveal against a real Polly narration with real word times; handwriting; colour; pull-back. Also the same scene with code-drawn strokes only, side by side | 1 to 2 days | USD 3 | The owner watches 45 s and says whether it looks hand-drawn and good. If the reveal order looks wrong, try part naming; if still wrong, see the alternative |
| 1. First version | Package format and builder scripts; library of 300 with contact-sheet review; catalog search (`w/`); `whiteboard` element (hidden first); board plan in the planner with limits, fallbacks and the sync rule; primitives; timing; vision check; miss sheet; director rule for when to pick the look; tests | about 3 weeks | USD 40 (library 25, test videos 15) | 20 test topics end to end on QA; pen-sync report inside limits; owner review of 5 |
| 2. Complete | 9:16, 1:1, 4:5 layouts; 4K; multi-board videos with pan, wipe and erase; simple marker figures (pose sets); optional real hand; chalkboard variant (same data, inverted palette); library growth from misses; app option to choose the look | about 2 weeks | USD 20 | all four aspects reviewed; 4K chunk time measured on Lambda |

Total: about 5 to 6 weeks of one builder, about USD 65, no new infrastructure beyond one catalog prefix and IAM line (the same change the vector catalog needs).

**What could make it fail**
1. The traced reveal looks mechanical (wrong direction, hopping between parts). Mitigation is built in (hidden path, part naming), but it is the open question.
2. The image model does not hold a clean, even marker line across hundreds of objects (shading, double lines, stray text). The vector catalog shows a fixed prompt holds a style, but line art has less room to hide flaws.
3. The planner over-draws or picks objects that say nothing ("draw a document"), giving a busy board that is less clear than our current scenes. Needs prompt work and the limits above.
4. Topics that are abstract or about real people, places and news do not suit the look; the director must refuse it there, or it will produce weak videos.
5. Taste: a whiteboard video with average drawings looks like the cheap end of the genre. The bar is the owner's "really good quality"; the prototype is the gate.

**One alternative if the first choice disappoints:** drop the tracing and make the strokes the art. A language model draws each library object as ordered strokes with a look-and-fix loop (the SketchAgent method, MIT, about USD 0.05 per sketch), we keep only the best of three tries per object after review, and the renderer draws the strokes directly with a textured pen. The style becomes a deliberate thin-marker doodle (closer to "napkin sketch" than to VideoScribe), stroke order is natural by construction, files are tiny, and the library costs about USD 45 for 300 objects. The renderer and planner from phase 1 are unchanged, so nothing is thrown away.

## 9. What I could not verify
* Centre-line tracing quality and automatic stroke order **on our own image-model art**: not run (no spend, no heavy tools on the owner's machine today). This is the prototype's job.
* Lambda timings: every render number here is from this Mac.
* Image latency (20 to 40 s) and the six-objects-per-sheet quality for line art: assumed from the character pilot.
* How Golpo and the other automatic tools make their drawings: not disclosed.
* Vyond and Powtoon whiteboard details and current prices; Doodly's current price.
* The full results of the hand study (paywall); the engagement points marked as my observation.
* Licence files of the handwriting fonts to bundle (Caveat, Patrick Hand, Kalam) and of the individual EMS fonts: listed as OFL, to be opened before bundling. Their coverage of every language we support.
* Running time and hardware needs of CLIPasso and DiffSketcher (not run; CLIPasso is excluded by licence anyway).
* SketchAgent's quality with today's models (its paper used Claude 3.5 Sonnet).

## 10. Sources (all accessed 2026-11-27)

Technique and tools
* VideoScribe help, "Creating your own SVG images" (strokes, layer order, invisible reveal stroke): https://help.videoscribe.co/knowledge/create-your-own-images
* VideoScribe help, "Draw" (hand can be removed): https://help.videoscribe.co/knowledge/draw
* Voomly (Doodly), "How to customize drawing movements" and "How to work with SVG files in Doodly" (draw paths, diagonal scribble for imported images): https://voomly.com/blog/how-to-customize-drawing-movements , https://voomly.com/blog/how-to-work-with-svg-files-in-doodly
* SitePoint, "invisible pen" SVG effect with Vivus.js (dash offset technique): https://www.sitepoint.com/how-to-create-the-invisible-pen-effect-in-svg-using-vivus-js
* Wikipedia, comparison of raster-to-vector software (potrace has no centre-line mode, autotrace has): https://en.wikipedia.org/wiki/Comparison_of_raster-to-vector_conversion_software
* Golpo (product, styles, plans, API price): https://video.golpoai.com/
* VideoScribe AI generation: https://www.videoscribe.co/ai-generation ; review noting manual shaping: https://dreamina.capcut.com/ai-video/videoscribe-review
* Lists of AI whiteboard makers: https://www.digitalocean.com/resources/articles/ai-animation-video-generator , https://www.heygen.com/video/whiteboard-video-generator , https://www.opus.pro/agent/workflows/hand-drawn-video-maker

Research models and benchmarks
* SketchAgent (CVPR 2025; USD 0.05 per sketch in the supplement): https://arxiv.org/abs/2411.17673 , https://github.com/yael-vinker/SketchAgent
* SVGenius benchmark (models degrade with complexity): https://arxiv.org/abs/2506.03139
* StarVector: https://arxiv.org/abs/2312.11556 ; OmniSVG: https://arxiv.org/abs/2504.06263
* Deep Sketch Vectorization via Implicit Surface Extraction (SIGGRAPH 2024): https://cragl.cs.gmu.edu/sketchvector/
* Single-Line Drawing Vectorization (Eurographics 2025): https://diglib.eg.org/handle/10.1111/cgf70228

Licences (licence file in each repository read today)
* SketchAgent, MIT: https://github.com/yael-vinker/SketchAgent/blob/main/LICENSE
* CLIPasso, CC BY-NC-SA 4.0 (non-commercial): https://github.com/yael-vinker/CLIPasso/blob/main/LICENSE
* DiffSketcher, MIT: https://github.com/ximinng/DiffSketcher
* diffvg, Apache-2.0: https://github.com/BachiLi/diffvg
* Quick, Draw! dataset, CC BY 4.0: https://github.com/googlecreativelab/quickdraw-dataset
* Magenta (Sketch-RNN), Apache-2.0: https://github.com/magenta/magenta
* autotrace, GPL-2: https://github.com/autotrace/autotrace
* vtracer, MIT: https://github.com/visioncortex/vtracer
* skeleton-tracing, MIT: https://github.com/LingDong-/skeleton-tracing
* Deep-Sketch-Vectorization, MIT: https://github.com/Nauhcnay/Deep-Sketch-Vectorization
* virtual_sketching, Apache-2.0: https://github.com/MarkMoHR/virtual_sketching
* Relief SingleLine, SIL OFL 1.1: https://github.com/isdat-type/Relief-SingleLine
* EMS / Hershey SVG fonts (derived from OFL fonts; licence inside each font file): https://gitlab.com/oskay/svg-fonts
* Hershey fonts package (data under the Hershey licence, tools GPL-2): https://github.com/kamalmostafa/hershey-fonts
* handwriting-synthesis (no licence file found): https://github.com/sjvasquez/handwriting-synthesis

Learning and engagement
* Krieglstein et al. 2023, hand drawing vs hand pushing vs no hand (Smart Learning Environments): https://link.springer.com/article/10.1186/s40561-023-00258-6
* Schneider et al. 2023, progressive drawing and narrative (Heliyon), via https://doaj.org/article/b614400e1604410898273830657364b1
* VideoScribe blog on the 521-adult study: https://blog.videoscribe.co/whiteboard-animation-beats-slides-for-retention-new-research
* Cognitive (RSA Animate studio), research page and history: https://cognitive-media.squarespace.com/whiteboard-animation-research , https://cognitive-media.squarespace.com/blog/history-whiteboard-animation-animates
* Wikipedia, Whiteboard animation (includes the sceptical 2016 view): https://en.wikipedia.org/wiki/Whiteboard_animation
* Voomly, writing a whiteboard script (one idea per scene, pacing): https://www.voomly.com/blog/write-whiteboard-script-that-doesnt-bore
* Practitioner notes on crowding and pauses: https://functioningmedia.substack.com/p/common-mistakes-to-avoid-when-creating

In this repository
* docs/SYNC.md, docs/COSTS.md, docs/VECTOR_SCENES.md, docs/VECTOR_CATALOG.md, docs/CHARACTER_ANIMATION_PROOF.md, docs/FOUR_K.md, docs/PLANS_PROPOSAL_2026-11-27.md, `backend/lambdas/engine/frame.py`, `engine/llm.py`, `engine/vector_scene.py`.
