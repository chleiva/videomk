# 3D volumetric hero background loops (2026-11-27)

Owner request: a few pre-rendered "advanced 3D" gas/nebula backgrounds, modern and lean, usable behind text, as the premium tier above the procedural backgrounds (docs/BACKGROUNDS_ANIMATED.md).

**State (2026-11-27, evening):** four loops rendered, checked and stored in the QA bucket AND copied to the prod bucket; wired into the engine behind the flag `BG_LOOPS` (on in QA and, since the owner watched and approved all four loops on 2026-11-27, in prod: `stages.json` `"bgLoops": true` in both); two real QA videos made and looked at. See "Wired into the engine" below.

## What exists
| id | look | text colour | 1080p | 4K master | worst / mean title contrast in the middle |
|---|---|---|---|---|---|
| `gas-brand-dark` | blue-violet gas on navy black (the one the owner watched and liked) | white | 6.7 MB | 43.3 MB | 10.7 : 1 / 18.0 : 1 |
| `gas-ember-dark` | orange embers and smoke on a warm black | white | 7.4 MB | 49.6 MB | 10.2 : 1 / 18.5 : 1 |
| `gas-aurora-dark` | teal-green veils on a deep sea black | white | 7.0 MB | 45.1 MB | 7.8 : 1 / 16.6 : 1 |
| `gas-brand-light` | lavender gas on a paper white | `#0b1020` | 7.0 MB | 56.9 MB | 14.7 : 1 / 17.2 : 1 |

All are 10 s seamless, 30 fps, 16:9, H.264 High, 8 bit. Where they are (QA assets bucket, private):
```
s3://videomk-qa-552357225438/backgrounds/loops/index.json
s3://videomk-qa-552357225438/backgrounds/loops/<id>/1080.mp4     the file the engine plays (keyframe every second)
s3://videomk-qa-552357225438/backgrounds/loops/<id>/4k.mp4       3840 x 2160 master, for download and marketing
s3://videomk-qa-552357225438/backgrounds/loops/<id>/poster.jpg   first frame, 1920 x 1080
```
`index.json` (source: `backend/scripts/hero_loops_index.json`): `{"version": 1, "loops": [{id, title, palette, mode, mood[], text, seconds, fps, frames, width, height, contrast, description}]}`.
The pattern follows the music library (`music/catalog.json` + one file per track): a small index the engine reads, files fetched on demand.

Files in the repo:
* `backend/scripts/blender_hero_loops.py`: the whole scene as one Blender (4.2 LTS, Cycles) script. `--palette brand|ember|aurora`, `--mode dark|light`, `--seed`, `--res`, `--seconds`, `--fps`, `--samples`, `--device`, `--density`, `--emission`, `--clear-floor`. Reproducible: same arguments, same frames.
* `backend/scripts/hero_loops_gpu.py`: renders on one short-lived GPU instance through the GPU lab (`gpu_lab.py`) and all of its guardrails; test frames first, then a job queue, encode and upload on the instance; `publish` copies the finished files to `backgrounds/loops/`.
* `backend/lambdas/engine/bg_loops.py` + `backend/tests/test_bg_loops.py` (23 tests): index, fetch, frames. Not imported by anything yet.

The exact commands of the four loops (all with `--res 3840x2160 --seconds 10 --fps 15 --samples 32 --device OPTIX --denoiser OPTIX`):
```
gas-brand-dark    --palette brand  --mode dark  (seed 7, density 1)
gas-ember-dark    --palette ember  --mode dark  --seed 31 --density 1.0
gas-aurora-dark   --palette aurora --mode dark  --seed 11 --density 1.0
gas-brand-light   --palette brand  --mode light --seed 7  --density 20
```

## How it is made
* A flat volume slab (34 x 3.2 x 20 scene units) in front of a dark world, Principled Volume shader, camera 13 units away looking through it. Density = a 4D noise (detail 8, roughness 0.66) whose lookup is bent by a second, slower noise (domain warp) so the gas curls into filaments; shaped with a smooth threshold so there are voids and wisps.
* Colour = a palette ramp driven by the density field; emission is **multiplied by the density** in the node graph (Principled Volume's emission ignores density, so without this the whole slab glows evenly: found the hard way).
* The world behind the gas takes a tint of the palette (a navy black behind orange gas reads as mud).
* Light mode is a different material: the gas is a coloured **filter** over a pale world (Volume Absorption, no emission, no scattering). Two things that did not work: a Principled Volume with a white colour absorbs nothing (grey haze), and with the ramp as its colour it also scatters, which washes the hue to a dirty mauve. Light mode needs far more density than dark (20, not 1): at 1 to 4 the picture is a blank white page.
* Text safety: a soft elliptical clearing is cut into the density around the camera axis (centre density x 0.04, 1.0 near the edges). Titles and captions sit on a calm centre; the 9:16 and 1:1 centre crops keep that calm centre.
* Seamless loop by construction: every animated value is a function of theta = 2 pi (frame-1)/N. The noise is sampled on a circle in (z, w) of 4D space (the gas morphs and returns exactly, it does not merely slide) and the camera drifts on a small ellipse of the same period.
* Rendered at 15 fps (150 frames for 10 s), 3840 x 2160, 32 samples, adaptive sampling, OptiX denoiser; encoded to 30 fps by blending the neighbouring frames (the gas is smooth, so blending is indistinguishable from rendering every frame, at half the GPU cost). The loop closes on frame 1 (a copy is appended before blending). The 4K master: x264 slow, crf 15, error-diffusion dithering plus one level of grain so dark gradients do not band.
* The 1080p the engine plays is made from the master: lanczos, one more level of grain AFTER the reduction, crf 18, `aq-mode=3` (more bits for dark areas), a keyframe every 30 frames (so the engine can decode any one-second window on its own). The first attempt (crf 22, no grain after the reduction) banded: 109 one-level stairs in 104 sampled rows of the brand loop's dark gradients; with these settings 4.
* Licensing: our own procedural scene rendered with Blender (GPL software; its renders are not covered by the GPL). Nothing third party is in the pixels.

## Checks on the finished 1080p files
Measured on 11 frames of each file (`first`, `last`, and nine in between), nothing judged by eye alone:
| id | wrap (frame 300 -> 1) vs a normal step | title contrast, worst 32 px cell / mean, middle 60% x 40% | one-level stairs in 104 rows |
|---|---|---|---|
| `gas-brand-dark` | 2.41 vs 2.19 (1.10x) | 10.7 : 1 / 18.0 : 1 | 4 |
| `gas-ember-dark` | 2.52 vs 2.25 (1.12x) | 10.2 : 1 / 18.5 : 1 | 2 |
| `gas-aurora-dark` | 1.83 vs 1.68 (1.09x) | 7.8 : 1 / 16.6 : 1 | 3 |
| `gas-brand-light` | 1.60 vs 1.37 (1.16x) | 14.7 : 1 / 17.2 : 1 | 2 |

* Seamless: the difference between the last and the first frame is the same as between any two neighbouring frames (mean absolute difference, 0 to 255 scale; most of it is the grain), against about 15 to 22 between frames half a loop apart.
* Calm centre: the title colour of the index against every 32 px cell of the middle, WCAG contrast. All are above 7 : 1 (AAA) at their worst cell in every sampled frame. The edges and corners are livelier on purpose; the engine's margins keep text out of them.
* Banding: runs of equal luma along rows; a "stair" is two flat runs of 40 px or more that differ by one level. A handful in 104 rows of 1920 px is the flat world colour itself, not a gradient.
* Looks that were tested and dropped (one 720p frame each, before any loop was paid for): light mode at density 1, 2 and 4 in all three palettes (an almost blank page), ember light (reads as a pink-red stain in one corner), aurora light (fine but weaker than the brand one; a candidate for later), brand light at density 30 (the left edge goes to a hard violet) and ember with seed 23 (a dim smear behind where a title sits).

## Cost and speed (measured)
* **This run (2026-11-27, ember + aurora + light, and the brand loop's 1080p):** one `g5.xlarge` (NVIDIA A10G 24 GB), on demand, eu-north-1b, USD 1.067 per hour. Launched 11:36:04 UTC, terminated 13:22:02 UTC: 106 minutes = USD 1.88, plus the 150 GB disk for that time USD 0.03 = **USD 1.92**. Inside those 106 minutes: boot and install 11 (9 of them lost to the stale package lists, see below), nine test frames 1, ember 31, aurora 32, light 26, the last encode and upload 4; the encodes of the earlier loops (6 to 8 minutes each) ran beside the next render.
* Per loop on the A10G: 150 frames at 4K, mean 12.5 s per frame for ember and aurora (11.1 alone; slower while the previous loop's encode shares the 4 vCPUs) = 31 to 32 minutes, 26 minutes for the light one; encode of the master and the 1080p 4 minutes alone, 6 to 8 beside a render. About **USD 0.60 per loop** all in. A 720p test frame takes 0.8 s.
  About half of each frame is CPU work (scene sync, 16 bit PNG), so a GPU twice as fast does not halve it.
* **The first loop (night of 26 to 27 Nov, brand dark):** one `g6e.xlarge` (L40S), on demand, USD 1.974 per hour, from 01:21 to about 02:30 UTC (CloudTrail start, last CloudWatch datapoint), at most 69 minutes = **USD 2.28** with its disk. It rendered the brand loop in about 21 minutes, and an aurora loop that was never encoded or uploaded (lost with the machine).
* **Total for the 3D loops: USD 4.20 (2.28 + 1.92) of the USD 6 cap.** The bill is the truth: Cost Explorer shows the day's usage about a day later (filter region eu-north-1, usage types `EUN1-BoxUsage:g5.xlarge`, `EUN1-BoxUsage:g6e.xlarge`, `EUN1-EBS:VolumeUsage.gp3`).
* Why this instance: the L40S (`g6e.xlarge`, then `g6e.2xlarge`) was tried first, expecting the most frames per dollar, but had **no capacity in any Stockholm zone**; the A10G was next and was available in one zone (eu-north-1b). Measured, the A10G is the cheaper one for this scene anyway: 31 minutes x USD 1.067 = USD 0.55 per loop against about 21 minutes x USD 1.974 = USD 0.69 on the L40S, because half of each frame is CPU work. Use `g5.xlarge`. Spot is not possible on this account: the spot quota for G instances in eu-north-1 is 0 ("All G and VT Spot Instance Requests" = 0), so everything is on demand.
* Lessons, now in the script: a fresh image has stale package lists, so `apt-get update` must come before installing the X libraries Blender links against (cost nine idle minutes here); each loop is uploaded the moment it is encoded (the first night's second loop died with the instance); a `pkill -f` pattern must not match the shell that sends it.

## How the engine uses a loop (`engine/bg_loops.py`)
* `load_index()` reads `backgrounds/loops/index.json` (cached 5 minutes; a missing or broken index means "no loops", never an error). `clean_index` keeps only well-formed entries. `pick(loops, mood=, palette=, mode=)` chooses one deterministically (the mode is a hard filter because it decides the text colour); `sanitize(value, loops)` turns a plan value (`"gas-ember-dark"` or `{"loop": id}`) into a `LoopSpec` or None; `prompt_list(loops)` is the menu text for a planner prompt.
* `ensure_local(id)` downloads `1080.mp4` once per container to `/tmp/bg_loops/` (temporary name, then rename: a half download is never used). About 7 MB per loop.
* `render(spec, w, h, t)` returns the `(h, w, 3)` uint8 picture for time `t`, the same call shape as `bg_animated.render`. Frame = `round(t * fps) mod frames`, so any `t` works and chunks need no bookkeeping.
* Only the frames a chunk needs are decoded: one short ffmpeg run per window of 30 frames (one second, one GOP), a bounded number of windows kept (192 MB by default, `BG_LOOPS_CACHE_MB`; a whole loop decoded would be 1.9 GB). At 1080p that is one window in memory at a time.
* Aspects: the stored loop is 16:9; 9:16, 1:1 and 4:5 take the centre crop (ffmpeg crops before it scales, so nothing bigger than needed is ever in memory).
* 4K: decoded at half size and enlarged smoothly (bicubic) with one level of grain; gas has no detail to lose. The 4K master is not used by the engine.
* `release()` frees the decoded frames.

## Wired into the engine (2026-11-27, flag `BG_LOOPS`, QA only; tests `backend/tests/test_bg_loops_wiring.py`, 32)
* **Who chooses:** the director, in the same small-model call that picks the procedural background (`engine/background.py choose`). With the flag on, the menu gains a "Premium 3D loops" part listing only the loops that fit the video's theme, and the answer may carry `"loop": "<id>"`. Fit = same light/dark mode as the theme (it decides the text colour) and a palette that suits the theme's cards: midnight: `gas-brand-dark`, `gas-aurora-dark`; sunrise: `gas-ember-dark`; paper: `gas-brand-light` (`LOOP_PALETTES`). A loop that does not fit, or is not in the index, is never used. No usable answer: the loop whose tags name the video's mood (calm, bright, tense), else the procedural style.
* **Three looks:** loop (premium) when the director picks one; procedural (`BG_ANIMATED`) otherwise; **static** for videos of the person's own photos and for data-heavy videos (half or more of the beats are charts, tables, maps, code or equations: `background.data_heavy`), where nothing moving should compete with the values.
* **Plan and timeline:** `plan["background"]` keeps the procedural choice and adds `loop`, `loop_palette` and `loop_seconds = 10` (the loop's length), so every scene's `bg_t0 = start mod 10` and the picture runs on the video's clock; the loop id is in every chunk's hash. If the loop cannot be used (flag off, index unreadable, theme changed) the procedural style of the same plan plays; if the file cannot be fetched inside a render the static glow is drawn and the download is not retried for every frame (`canvas._moving_background`, log line `BG_LOOP_FAILED`).
* **Edits:** a theme change keeps the loop only while it still fits (`background.retheme`); otherwise it is dropped and the procedural style follows the new theme.
* **IAM:** `s3:GetObject` on `backgrounds/loops/*` for the chunk renderer and the self-test, on `backgrounds/loops/index.json` for the planner; granted in every stage (read only, no listing), so switching the flag needs no new rights.
* **Production:** code deployed, files copied (13 objects, 223,249,438 bytes, same sizes as QA), flag ON since 2026-11-27 (`"bgLoops": true` and `"bgAnimated": true` under `prod` in `backend/stages.json`; remove them and deploy to switch off). Prod render functions have 3008 MB; the loop needs about 190 MB of decoded frames at 1080p.

### Measured on QA (two real videos, 30 s, made 2026-11-27 13:45 UTC)
| video | format | loop | where the loop shows |
|---|---|---|---|
| `555ee526` "neural network learns a digit" | 16:9 1080p, 32.9 s, 4 scenes | `gas-brand-dark` (director) | all of it (kinetic text, diagram, steps) |
| `4ff1e3c5` "Pompeii" | 9:16 1080p, 30.4 s, 3 scenes | `gas-ember-dark` (director) | 8.5 to 19.1 s only (a title card that replaced a clip nobody found); the rest is full-screen footage and a photo |
* **Seams (frame-to-frame difference on a text-free strip, 0 to 255):** scene changes 3.28 and 2.63 against a normal 3.60 and 2.67; the chunk boundary at 15.9 s 3.39 against 2.92; the loop point at 10 s 3.98 against 3.14 (it is also a keyframe), at 20 s 3.51 against 3.35, at 30 s 3.58 against 3.38; vertical at 10 s 2.19 against 1.98. No jump anywhere; the frames either side of each seam were also looked at side by side.
* **Readability:** titles, cards and the caption box read cleanly on both; nothing had to be changed.
* **Banding:** 16:9: none visible even with the dark range stretched 4 times; 9 one-level stairs in 104 rows of the finished video. 9:16: the loop is a 608 px wide centre crop enlarged 1.78 times, so it is softer, and the finished video has 55 stairs in 104 rows; at normal contrast the frame is smooth, stretched 5 times it shows the encoder's blotches in the dark areas (no contour lines). Not judged on a phone at full brightness.
* **Cost on Lambda (the same 476-frame chunk of `555ee526` rendered three ways on warm functions):** static glow 166 ms per frame, **loop 296 ms**, procedural 408 ms. The loop costs about 130 ms a frame more than the static look and about 110 ms less than the procedural background that was already live on QA. The first real render of that video took 122, 75 and 144 s in its three render functions.
* **Memory:** the three cold render functions of the loop video peaked at 1376, 759 and 1064 MB (of 10240 MB); a 720p vertical video with a procedural background earlier the same day peaked at 524 to 842 MB. A clean like-for-like peak was not possible (Lambda reports the highest use since the function started, and the comparison ran on warm functions).

## Asking for a background in the request text (2026-11-27; `engine/background.request_wish`, tests `backend/tests/test_looks.py`)
The person can ask in plain words, in English or Spanish, the way "make it a cartoon" asks for cartoon scenes. Only phrases that name the background count ("a video about smoke" changes nothing). A stated wish wins over the mood and over the data-heavy rule; it never applies to a video made of the person's own photos; with the switches off it does nothing.
| Words in the request | Result |
|---|---|
| "with a purple 3D background" (purple, violet, blue, indigo; "con un fondo 3D morado", violeta, azul) | `gas-brand-dark`; the video takes the midnight theme |
| "with a warm 3D background" (warm, orange, fire, ember, red; "con un fondo 3D cálido", naranja, fuego, rojo) | `gas-ember-dark`; sunrise theme |
| "with a green 3D background" (green, teal, aurora, emerald; "con un fondo 3D verde", turquesa) | `gas-aurora-dark`; midnight theme |
| "with a light 3D background" (light, white, bright, pale; "con un fondo 3D claro", blanco) | `gas-brand-light`; paper theme |
| "with a 3D background", "3D smoke background", "fondo 3D", "fondo en 3D" (no colour) | a 3D loop that fits the theme the writer chose (the one whose tags name the video's mood, else the first) |
| "with an animated background", "moving background", "smoke background", "fondo animado", "fondo en movimiento" | a moving background for sure (also on a data-heavy video); which one is still the director's choice |
| "no moving background", "still / static background", "without an animated background", "fondo fijo", "fondo estático", "sin fondo animado" | no moving background: the static look. Wins when both kinds of words appear |
* A colour word must sit right at the word background ("purple background", "fondo morado", "fondo 3D de color verde"); a colour elsewhere in the request is ignored. A colour alone ("a blue background") already asks for that loop.
* The theme follows the look only when the person did not choose a theme in the options (`theme` in the request). If they did and it cannot carry the look (a light background on the midnight theme), the theme stays and the nearest procedural background plays.
* Where the 3D loops are switched off the same words give the procedural gas in the nearest palette.
* The plan records it: `plan.background.by = "request"` (and `research.background`), or `research.background = {"by": "request", "style": "none"}` for "no moving background".
* No model call is made when a look or "3D" is named (the choice is arithmetic). Capabilities publishes the phrases per stage: `looks.backgrounds.ask = [{id, label, say}]` (a test checks that every published phrase does what it says, in both languages).
* Honest limit: the words stay in the request the writer reads, so the script may occasionally mention the background. Not seen in the checks, not excluded.

## Hook-up steps (the plan that was followed)
1. **Canvas** (`engine/canvas.py`, `Canvas.background`): where `anim` is handled today, accept a `bg_loops.LoopSpec` as well: `arr = bg_loops.render(anim, self.W, self.H, t) if isinstance(anim, bg_loops.LoopSpec) else bg_animated.render(anim, self.W, self.H, t)`; the rest (enlarge to the supersampled canvas) stays. Wrap the loop call in `try/except` and fall through to the static glow: a missing file must never fail a render.
2. **Renderer** (`engine/renderer.py`, where `bg_anim` is settled from `timeline["background"]`): if the cleaned background carries `"loop": "<id>"`, use `bg_loops.sanitize(bg, bg_loops.load_index())`; None falls back to the procedural spec. Call `bg_loops.release()` where the picture caches are emptied. Text colour: the loop's `mode` must equal the theme's mode (dark themes take dark loops, `paper` takes the light one), which keeps every text colour as it is; `spec.text` is there for a caption drawn outside a theme.
3. **Timeline** (`engine/timeline.py`): nothing new. `bg_t0 = start mod loop` is already written per scene from `background["loop_seconds"]`; set `loop_seconds` to the loop's `seconds` (10) when a loop is chosen, so the picture flows across scene and chunk boundaries.
4. **Director / planner** (`engine/background.py`): add the loops to the menu as one more style (for example `style: "gas3d"` with `loop: id`), chosen by mood with `bg_loops.pick`; suggested mapping from the index tags: tech / AI / night -> `gas-brand-dark`; energy / history / sport / tense -> `gas-ember-dark`; nature / science / calm -> `gas-aurora-dark`; lifestyle / wellness / bright on the paper theme -> `gas-brand-light`. Keep the rule "one background per video".
5. **IAM** (`backend_stack.py`): the functions that render frames (the chunk renderer, and any function that renders a preview or thumbnail) need `s3:GetObject` on `arn:aws:s3:::<ASSETS_BUCKET>/backgrounds/loops/*`. The function that builds the plan needs the same on `backgrounds/loops/index.json` if the planner reads the menu. No `ListBucket`, no write.
6. **Environment:** none required. `ASSETS_BUCKET` is already set; optional `BG_LOOPS_DIR` (default `/tmp/bg_loops`) and `BG_LOOPS_CACHE_MB` (default 192). `/tmp`: 7 MB per loop used, well inside the default 512 MB. A flag in the style of `BG_ANIMATED` (for example `bgLoops` in `stages.json` -> `BG_LOOPS=1`) keeps it QA-only at first.
7. **Hashes:** a chunk's segment hash must include the loop id (it does if the id sits in `timeline["background"]`, as the procedural spec does), so a changed background re-renders.
8. **Production:** the files are in the QA bucket only. Before the flag goes on in prod: `aws s3 sync s3://videomk-qa-552357225438/backgrounds/loops/ s3://<prod assets bucket>/backgrounds/loops/`.

## Not verified
* `gas-aurora-dark` (video `9df5de7a`, 16:9, 61 s) and `gas-brand-light` (video `65eaa9b9`, 9:16, Spanish, 30 s; the loop shows in its first 9 s only) were each chosen by the director in a later QA video and looked at on a contact sheet (text readable, the look fits); their seams and banding were not measured again.
* Nobody has watched the QA videos in motion with sound; the checks are numbers and still frames.
* 4K with a loop was not rendered on Lambda (the canvas makes the background at 1080p and enlarges it, as for the procedural one).
* The 130 ms a frame is mostly the enlargement to the 2x canvas and one ffmpeg start per second of video; decoding straight to the canvas size would likely recover part of it (not done).
* The exact GPU bill is not in Cost Explorer yet (it lags about a day); the spend above is computed from launch and termination times and the list price.

## Make another loop
```
cd backend/scripts
python hero_loops_gpu.py job 10_name "name palette mode seed density"     # queue first, so no paid minute waits
python hero_loops_gpu.py up --type g5.xlarge --minutes 60                 # prints the worst case; test frames land in lab/avatars/hero3d/out/tests/
python hero_loops_gpu.py status                                           # frames done, log tails
python gpu_lab.py down                                                    # terminate; then check gpu_lab.py status says "no lab instance exists"
python hero_loops_gpu.py publish hero_loops_index.json name=gas-name-dark # after adding the entry to the index
```
Edit `TESTS` in `hero_loops_gpu.py` to choose the test frames. One loop is about 40 minutes and USD 0.70 on a `g5.xlarge` including boot.
