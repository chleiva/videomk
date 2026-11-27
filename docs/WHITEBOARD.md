# The whiteboard look (phase 1b, 2026-11-27)

A whole video drawn and written by a marker on a whiteboard, in time with the narration. Library, handwriting and the standalone prototype are in `docs/WHITEBOARD_PHASE_1A_2026-11-27.md`; this page is how the look lives in the product engine. **Measured** = run on the owner's Mac on 2026-11-27. Nothing here has run on Lambda yet (not deployed).

## How to ask for it
| Way | What happens |
|---|---|
| `"style": "whiteboard"` in `POST /users/{user}/videos/generate` | A whiteboard video, whatever the topic (the person asked). |
| Words in the prompt | EN: "as a whiteboard video", "whiteboard style", "draw it on a whiteboard", "hand-drawn video/style/explainer", "marker drawings", "doodle video", "sketch video". ES: "estilo pizarra", "en pizarra blanca", "vídeo de pizarra", "dibujado a mano", "dibujos a mano", "estilo boceto". Same result as the option. |
| `auto` (nothing sent) | The director may choose it only when the producer's kind of video is one of explainer-education, science-wonder, tutorial-howto, finance-business, health-wellbeing, kids-family AND one small model call agrees that the video explains a process or concept and needs no real pictures. Any doubt is no. |
| Never | Flag off; `style` cartoon or real; the words "real footage", "no whiteboard", "sin pizarra", "imágenes reales"; a video from the person's photos; a deck; on `auto`: current events (web research), news, biography, history, travel, product, true crime. |

Capabilities lists it under `looks.style.options`: `{"id": "whiteboard", "label": "Whiteboard" / "Pizarra", "note", "say": "as a whiteboard video" / "estilo pizarra", "available": <flag>}`. With the flag off the option is still accepted by the launcher and simply gives an ordinary video (as with `cartoon`).

## Flag and rights
* `WHITEBOARD=1` on the engine functions and on capabilities. `backend/stages.json`: `"whiteboard": true` for QA, absent for prod; or `-c whiteboard=1`. Needs `-c imageCatalog=1` (the deploy fails otherwise).
* The render and self-test functions get `s3:GetObject` on `w/*` of the catalog bucket and `CATALOG_BUCKET`. The planner needs nothing new: the library index ships with the code and the Cohere search uses the Bedrock right the plan function already has.
* No new function, route or other resource (a test compares the resource types of the stack with the flag on and off).

## How it works
1. **Policy** (`engine/whiteboard_policy.py`): `decide` (table above); `prompt_block` teaches the director the `whiteboard` scene and lists the 354 drawing ids by group; while the plan is cleaned a `whiteboard` scene is refused unless this video's policy allows it.
2. **The board the director writes** (`engine/scenes/elements/whiteboard.py`, hidden from the ordinary scene list): items in drawing order, never coordinates.
   * `draw` (library id), `write` (text; `^{2}`, `_{2}`, `\frac{a}{b}`, `->`), `chart` (`bars` or `line`, 2 to 6 values, labels: drawn by hand), `connect` (arrow, wavy, dashed, line), `mark` (underline, double_underline, circle, box, tick, cross, cross_out, highlight).
   * Each has a `zone` of a 3x3 grid (or `near` another item) and `say`: the narration word on which it is finished.
3. **Validity, no model** (`sanitize`): at most 16 items and 9 drawings/texts/charts; a drawing name is matched by id, then by exact title or synonym (EN/ES), then by meaning (Cohere Embed v4 against the bundled index, floor 0.30); **no match: the name is written in a box** (no image is ever generated in the request path); arrows and marks that point at nothing are dropped; a second drawing in a taken zone moves to a free one; an empty board is refused and the beat falls back. Text beats the director wrote as title, bullets, stat or quote are rewritten as boards (`enforce`).
4. **When the narration is final** (`settle`, last step of the director, after the script is cut to length and corrected): `retie` reorders items into the order the narrator names them (never an arrow or mark before its target) and moves a tie whose word was cut to a word still said at the same relative place; `keep_busy` adds an emphasis mark, tied to a word, wherever 8 or more words pass with nothing drawn. The same `retie` runs when a beat's narration is edited.
5. **Timeline** (`whiteboard_policy.link`, called by `engine/timeline.py`): consecutive boards are **panels of one big board**. Each later scene carries the previous panel's items (`prev`) and its place (`panel`), the crossfade between them is off; the last one carries all (`wall`, at most 8 before it). The library build date is stamped into the props, so it is part of the segment hash.
6. **Render**: `engine/whiteboard/spec.py` lays out, times (each item ends 0.15 s after its word starts; one pen; up to 1.6x faster when squeezed, slower to fill idle time) and frames the camera; `board.py` draws a frame as a pure function of the scene time. The board is the content box of `engine/frame.py` (above the caption band, below a top watermark band) for all four aspects; the rest of the frame is paper. A scene starts with the camera travelling from the previous panel (0.8 s) and the last scene ends on a pull-back over every panel (3 s). The video's theme is `paper` (light captions and closing card) and it has no moving background.
7. **Memory and cache**: one built board per container plus small finished pictures of neighbouring panels (at most 10). Drawing packages: `s3://<catalog>/w/<id>.json`, kept under `/tmp/whiteboard` and at most 48 in memory. `WHITEBOARD_DIR` points tests and laptops at a folder instead.
8. **Never a failed render**: a missing package is a boxed label; a board that cannot be built is a plain card with its first written line.

## Measured (16:9, this Mac, x264 included)
| | 1080p | 4K |
|---|---|---|
| Board preparation, once per scene per container | 0.2 s | **0.7 s** (was 194 s in phase 1a: the reveal map is now painted along the pen path with Pillow instead of a distance transform per item) |
| Per frame in the pipeline | 52 to 64 ms (10 s chunks: 15 to 27 s each) | 176 to 193 ms (two 90-frame pieces of the last scene) |
| Peak memory of the render process | 0.77 GB (three chunks in one process) | 3.1 GB |
| Planner | 23 s and USD 0.10 for a 40 s video (director, all calls) | same |

4K therefore fits the render function (10 GB, 10 minutes, pieces of 180 frames) by these numbers and is **not capped**; it has not been run on Lambda, where a core is two to three times slower.

## Costs
Per video: the director's usual calls plus about 9,000 characters of prompt (the id menu); at most one small call for `auto`; one Cohere embedding only for a drawing name not found by name. Rendering is cheaper than a photo video (no downloads, about 50 ms a frame). The library cost USD 4.90 once.

## Limits and known weak points (looked at the first local video)
* Wide views are sparse: drawings are small when the camera shows the whole board. The board was already made a quarter smaller than the demos (`BOARD_K` 1.5) to help.
* The camera still zooms in and out often; connectors run straight and can cross a third item (phase 1a notes).
* A list of several lines is small; the director is told to keep lists to four short lines with the marker.
* The pacing rule adds marks only for gaps of 8 words; pen-busy share was 66 % on the one board measured, not measured over many videos.
* Only Latin handwriting (EN, ES). Chalk theme exists in the compiler but is not offered.
* Ties are one word; a tie to a word the narrator says twice lands on the first saying after the previous tie.
* The editor apps have no board editor: a board's props are read-only there; editing the narration re-ties the board.
* Not done: a large continuous canvas with free camera paths (panels in a grid stand in for it); whole-board overlap check before render (overlaps are avoided per item and reported by `compile_board`, not repaired); QA run on Lambda; 9:16, 1:1, 4:5 were tested by unit tests only, not watched as full videos.

## Files
`engine/whiteboard/` (core, board, hand, spec, primitives, library), `engine/scenes/elements/whiteboard.py`, `engine/whiteboard_policy.py`, `engine/assets/whiteboard/` (two OFL fonts with licences, glyph tables, library index), `scripts/whiteboard_local.py` (a whole video on a laptop), tests `test_el_whiteboard.py`, `test_whiteboard_policy.py`, `test_looks.py`.

## Try it locally
```
AWS_PROFILE=qa AWS_REGION=eu-west-1 python backend/scripts/whiteboard_local.py "Explain how compound interest makes savings grow, as a whiteboard video" out_dir --seconds 40
```
