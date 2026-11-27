# Animated backgrounds: prototype and recommendation (2026-11-27)

Owner idea: a library of modern, lean animated backgrounds (gas, smoke, fluid motion, "advanced 3D" look) that the director can pick, ready at 4K and every aspect.
Prototype: `engine/bg_animated.py` (six styles), `scripts/bg_animated_demo.py` (samples and measurements), `tests/test_bg_animated.py` (34 tests).
Nothing is enabled for users: the plumbing is off unless the Lambda env has `BG_ANIMATED=1` AND the timeline carries a `background` dict.

## Recommendation: procedural first, pre-rendered 3D only for a few hero loops (hybrid)
Procedural wins for a background: it is generated at the exact size and aspect (16:9, 9:16, 1:1, 4:5, 4K) from a handful of numbers, so there is nothing to store, nothing to
re-render per format, the palette follows the video's theme, and a seed gives endless variety. Every style loops perfectly by construction (the seam error between frame 0 and
frame T is exactly 0.0, tested). A pre-rendered 3D library would be hundreds of MB to GBs per format and aspect, fixed colours, and a GPU bill; it only pays off for looks that
procedural fields cannot reach (true volumetric lighting, fluid simulation with caustics). I did NOT run the GPU lab: the procedural quality was enough for a background, and nothing
shown here needs a 3D renderer. If the owner wants one or two hero loops later, budget one GPU session (g6e.xlarge, about USD 2 per hour in eu-north-1 per docs/VIDEO_CATALOG.md,
at most USD 3 for 90 minutes; `gpu_lab.py up` prints the worst case first) and store the loop once at 4K 16:9 and 9:16.

## The six styles (parameters: style, palette, mode, speed, intensity, seed, loop_seconds, quiet)
| style | what it is | looks like | cost 1080p |
|---|---|---|---|
| gas | domain-warped fractal noise through the theme's colour ramp | slow satin / nebula | 35 ms |
| smoke | stretched noise, sparse wisps | dark with drifting wisps (best on `mono`, calm/serious topics) | 36 ms |
| lava | soft metaballs on closed orbits | glowing blobs that merge and split (`ember`, `sunrise`) | 35 ms |
| aurora | curtains with vertical rays | northern lights across the upper half (`forest`, `ocean`) | 49 ms |
| mesh | moving Gaussian colour points (gradient mesh) | Apple-like colour fields (`sunrise`, `violet`; light mode is the prettiest) | 46 ms |
| bokeh | rising soft discs over a faint gas | quiet depth, good under lists (`violet`, `midnight`) | 35 ms |
Palettes: midnight, sunrise, ocean, ember, violet, forest, mono (the first two are the engine's themes; `paper` maps to violet in light mode). Modes: dark (white text) and light (dark ink; pastel).

## How it is made cheap and clean
- The picture is computed on a small grid (360 px on the long side), enlarged with bicubic filtering in floating point (gas and light have no fine detail to lose), then given
  triangular-noise dither before the 8-bit rounding. At 12x contrast stretch the undithered frame shows clear contour bands and the dithered one shows only fine grain
  (checked on a dark smoke frame): this matters, because x264 would otherwise turn dark gradients into visible steps.
- Loops are exact: each wave has an integer time frequency, so the phase advances by whole turns per loop (6 to 20 s, default 10). Speed = how many wavelengths things travel per loop.
- 4K: computed at 1080p and enlarged (bilinear), dither included. Measured per frame, gas: 720p 19 ms, 1080p 35 ms, 9:16 36 ms, 1:1 30 ms, 4:5 33 ms, 4K 73 ms (aurora, the heaviest: 49 ms and 129 ms).
  Inside the renderer (whole frame of the demo timeline, one scene) animated gas adds about 38 ms at 1080p and 17 ms at 4K to the 50 and 100 ms of the static glow (which is cached), i.e.
  well inside the ~190 ms per frame class of the heavier scenes. A cheaper option if needed: render each background once per scene-loop (8 s = 240 frames) per chunk and cache it.

## Text safety (measured)
A smooth quiet zone (the broad middle, where titles, lists and captions live) limits brightness (dark mode) or darkness (light mode) so the video's own text keeps at least 4.5:1 (WCAG AA).
Measured on 84 combinations (6 styles x 7 palettes x 2 modes, 5 frames each): worst case inside the zone 5.37:1, none below 4.5. The corners and edges are intentionally livelier and
can drop to 1.6:1 at their brightest (never put text there; the engine's margins keep text out). The limit is a smooth compression, not a clip, so shapes keep their form (a clip turned yellow into mud
and made a visible edge; found and fixed while building). Weak spots: `mesh` and `lava` on warm palettes still look a little muddy in the middle (a vignette), and `aurora` is soft rather than crisp.

## Integration proposal (not enabled)
1. Timeline field `background: {style, palette, mode, speed, intensity, seed, loop_seconds}` (already cleaned by `bg_animated.sanitize`: unknown values dropped, numbers clamped, nothing else survives). Already plumbed through `Renderer` and `Canvas.background(anim=...)` behind `BG_ANIMATED=1`.
2. The planner chooses ONE background for the whole video (consistency; changing per scene would pop), from a menu keyed to mood, with the palette taken from the theme unless the topic asks otherwise:
   calm science/nature -> gas or aurora (ocean, forest); news/serious/finance -> smoke (mono) or gas (midnight); tech/AI -> gas or mesh (violet, midnight); energy/history/sport -> lava (ember, sunrise);
   wellness/lifestyle/kids -> mesh or bokeh (light mode, sunrise); lists and explainers -> bokeh. About 120 characters of prompt, plus a validation that falls back to today's static glow.
3. Scenes that are full-bleed images (type `image`) already skip the ambience; framed clips keep their own backdrop.
4. Cost and files: no storage, no new dependency (numpy and Pillow already in the layer), about +20 to 40 ms per frame, +0 for 1080p/4K decisions elsewhere.
5. Later, if wanted: a 4K 16:9/9:16 hero loop from Blender on the GPU lab, listed as one more `style` that plays a stored file instead of computing.

## Owner decisions
1. Go for the planner menu and enabling `BG_ANIMATED` on QA first (about a day of work), or keep it as a library of looks the user picks in Create (a UX agent is redoing Create now)?
2. Should a user be able to pick the background, or only the director? (Recommended: director decides; one "Background" chip in the advanced sheet.)
3. Appetite for one or two pre-rendered 3D hero loops (about USD 3 per attempt)?

## Wired into the director (2026-11-27, flag `BG_ANIMATED`, on in QA only)
Owner decision: the director picks. `engine/background.py`, tests `tests/test_background.py`.
- **Choice:** after the script is written, one small-model call (about 20 tokens out, limit 300 because the model's thinking counts; about USD 0.00006) reads the request, the title, the mood the writer gave (`calm|bright|tense`) and the theme, and answers `{"style", "palette"}` from the menu above. A failed or odd answer falls back to the mood (calm: aurora, bright: bokeh, tense: smoke). Stored as `plan["background"] = {style, palette, mode, speed, intensity, seed, loop_seconds, by}` (`by`: `director` or `mood`; speed 0.7 / 1.0 / 1.15 by mood; seed from the title). Videos of the person's own photos and deck videos get none.
- **Never muddy:** the palette must be one that suits the theme (midnight: midnight, ocean, violet, forest, mono; sunrise: sunrise, ember, violet; paper, light mode: violet, ocean, forest, midnight, mono), and `mesh`/`lava` are never used on the warm palettes (sunrise, ember), nor `mesh` in light mode (a dark corner on the sample sheet). A wish outside this keeps its style on an allowed palette, else the mood's style. A theme change in the editor re-settles it.
- **Continuity:** the background runs on the video's clock, not the scene's: the timeline writes each scene's place in the loop (`bg_t0 = start mod loop`), so it flows across scene changes and chunk boundaries (tested: the cut is one frame's drift). An edit that shifts later scenes re-renders their chunks (only for videos with a background).
- **Switch:** `stages.json` `"bgAnimated": true` (QA) or `-c bgAnimated=1` sets `BG_ANIMATED=1` on the engine functions. Off: no call, no plan field, frames and segment hashes exactly as before. A plan that already has a background renders with the static glow if the flag is later turned off.
