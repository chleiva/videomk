# The whiteboard look (phase 1b, 2026-11-27)

**Since 2026-11-28** the look of a video is one decision (`docs/ART_DIRECTION.md`): on `auto` the whiteboard is one of the directions an art-direction step chooses from (it no longer has its own yes/no call), a chosen whiteboard look is enforced (at least 80 % boards, a real picture at most once per 30 s), and the board renderer is also the content panel beside cartoon characters (the `board` extra).


A whole video drawn and written by a marker on a whiteboard, in time with the narration. Library, handwriting and the standalone prototype are in `docs/WHITEBOARD_PHASE_1A_2026-11-27.md`; this page is how the look lives in the product engine. **Measured** = run on 2026-11-27, on QA Lambda where it says so, else on the owner's Mac. QA: on (commit 4beeb09). Production: off.

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
1. **Policy** (`engine/whiteboard_policy.py`): `decide` (table above); `prompt_block` teaches the director the `whiteboard` scene and lists the 354 drawing ids by group; while the plan is cleaned a `whiteboard` scene is refused unless this video's policy allows it. The policy knows the video's aspect: a tall video (9:16, 4:5) gets its own layout advice (full-width titles, 1 to 3 words per line, top to bottom).
2. **The board the director writes** (`engine/scenes/elements/whiteboard.py`, hidden from the ordinary scene list): items in drawing order, never coordinates.
   * `draw` (library id), `write` (text; `^{2}`, `_{2}`, `\frac{a}{b}`, `->`), `chart` (`bars` or `line`, 2 to 6 values, labels: drawn by hand), `connect` (arrow, wavy, dashed, line), `mark` (underline, double_underline, circle, box, tick, cross, cross_out, highlight).
   * Each has a `zone` of a 3x3 grid (or `near` another item) and `say`: the narration word on which it is finished.
   * `"board": "same"` on a beat: it goes on drawing on the board of the beat before it (see 4).
3. **Validity, no model** (`sanitize`): at most 20 items and 9 drawings/texts/charts a beat; a drawing name is matched by id, then by exact title or synonym (EN/ES), then by meaning (Cohere Embed v4 against the bundled index, floor 0.30); **no match: the name is written in a box** (no image is ever generated in the request path); arrows and marks that point at nothing are dropped; an empty board is refused and the beat falls back. Text beats the director wrote as title, bullets, stat or quote are rewritten as boards (`enforce`).
4. **Boards are full pictures shared by beats** (`compose`, when the script is final). One beat (about 10 s, 20 to 25 words) cannot fill a board, so consecutive beats share one: the director marks the continuing beat, and the engine also keeps a beat on the board when the board is not full yet (fewer than 8 things or 40 words), up to 3 beats, 12 drawings and texts, 66 words. A thing whose zone is taken moves to a free zone of the same shape; a beat that finds no free zone opens a new board. The closing beat stays on the last board. Result on the three test prompts: 2 to 4 boards of 15 to 21 s with 12 to 18 items each (before: 5 to 8 boards of 5 items).
5. **When the narration is final** (`settle`, last step of the director): `compose`; `retie` reorders items into the order the narrator names them and moves a tie whose word was cut; `keep_busy` adds an emphasis mark, tied to a word, wherever 5 or more words pass with nothing drawn (a thing gets at most two different marks). Then the **self-check** (below).
6. **Timeline** (`whiteboard_policy.link`, called by `engine/timeline.py`): the scenes of one board know each other (`before`: what earlier beats drew, there from the first frame; `after`: what later beats will draw, their place is kept); the first scene of a later board carries the previous board (`prev`: the camera travels from it), the last scene carries all (`wall`). Items get board-wide names (`0:sun`), so a thing looks the same in every scene of its board. Here the REAL word times are known, so `fill_rests` adds emphasis marks at fixed times wherever the pen would rest more than 1.6 s: between two tied things, at the start of a beat that continues a board, and in the breath after the last word (at most 3 a scene, on things of this board that have no mark yet). The library build date is stamped into the props (segment hash).
7. **Render** (`engine/whiteboard/spec.py`, `board.py`): layout, timing and ONE framing per board.
   * **Layout**: rows and columns share the board by what they hold (a title row is lower than a row of drawings; an empty row or column gives up most of its room). A drawing fills its zone less the room of its labels. Handwriting is never under 76 board units (4.7 % of the frame's shorter side on screen): text that does not fit spreads into free neighbouring zones, a number or short phrase is written smaller on one line rather than wrapped, the rest wraps. A chart takes a free zone above or below and its numbers have a minimum size.
   * **Arrows** leave and arrive at the edges of their items and curve; the gentlest of eight bends that crosses no other drawing or text and stays on the board is taken (a straight dashed or wavy connector whose way is blocked becomes such a curved arrow). The report lists any arrow that still crosses something.
   * **Timing**: each item ends 0.15 s after its word starts and never later when that is possible: items before a squeezed one are finished sooner (backward pass), then the pen goes up to 1.6x faster. A drawing with idle time before it is drawn up to 2.6x slower, a written block is started earlier and written up to 1.8x slower. Nothing is drawn while the camera arrives.
   * **Camera**: the whole board (everything it will ever hold, with a margin), enlarged up to 1.45x when the board is not full; still for every scene of the board. It moves only between boards (0.8 s) and for the final overview: the boards' content boxes side by side inside the content box of the frame, above the captions (3.8 s: 1.5 s travel, then held before the 1.4 s closing fade). With more than 4 boards the overview would be too small to read: the video stays on the last board and only glances at the whole (1.8 s).
   The board is the content box of `engine/frame.py` (above the caption band, below a top watermark band) for all four aspects. The theme is `paper`; no moving background.
8. **Memory and cache**: one built board per container plus small finished pictures of other boards (at most 10). Drawing packages: `s3://<catalog>/w/<id>.json`, kept under `/tmp/whiteboard` and at most 48 in memory. `WHITEBOARD_DIR` points tests and laptops at a folder instead.
9. **Never a failed render**: a missing package is a boxed label; a board that cannot be built is a plain card with its first written line.

## Self-check (`engine/whiteboard/score.py`, `whiteboard_policy.review`)
After `settle` every board is laid out and timed exactly as the renderer will, without drawing a pixel and without the drawing packages (shape and drawing time of each object come from the bundled index; word times from the measured speaking rate). Per board: things per 10 s (at least 4, never under 4 on a board of 10 s or more), coverage of the framed picture by the boxes of drawings and writing (at least 30 %), smallest letter size (at least 4.4 % of the shorter side), overlaps, things off the board, arrows that cross something, pen-busy share (at least 45 %), longest rest (at most 2.2 s with estimated times), items finished more than 0.8 s after their word. A board that fails is sent back to the director ONCE with its complaints in plain words ("only 4 drawings and written phrases for about 19 s: it needs at least 6 ... in the free zones (left, bottom)"); the narration is never changed; the new boards are kept only if the video then scores at least as well. **Overlaps are never shipped (2026-11-27, languages-qa-fixes).** Three rules, after the first Polish video showed two beats written on top of each other: (1) `compose` knows the aspect and lays a shared board out as the renderer will (`score.defects`): a beat shares a board only if its things really fit there, else it gets its own board with the zones its author gave it (`split_for_room`); a free zone alone is not room. (2) When the rewritten boards are kept, the WHOLE trial is taken, not the rewritten beats plus the others' `board` flags (that was the bug: a beat got the flag `same` but kept the zones of a board of its own, and the score had been taken on the trial, so it said `overlaps: 0`). (3) Last resort, whatever the repair did (`make_safe`, `untangle`): a board whose drawings, texts or charts still overlap or leave the board loses its last beat to a fresh board, then things move to a free zone, get one size smaller, and at the very end are taken off, until the renderer's own layout finds nothing (logged as pass `safe`, kept in `score.made_safe`). The summary counts `overlaps` and `off_board` on every board, failing and shared ones included; `not_laid_out` counts boards without numbers. Boards that only miss the fullness or pacing bar are still shipped as they are. Logged as `WHITEBOARD_SCORE {...}` (pass 1 and pass 2) by the plan function and kept in `plan.whiteboard.score` (`first`, `second`, `kept`, `boards_detail`). Cost: one more call of the script model when a board fails (about USD 0.05 to 0.08 and 25 to 40 s of planning).

## Measured on QA Lambda (2026-11-27, ten real videos; `v2_render_chunk` 10 GB, 600 s)
| | First build (8c77b12) | Final build (4beeb09) |
|---|---|---|
| Render per frame, 1080p | 0.19 to 0.20 s | 0.24 to 0.28 s (fuller boards) |
| Slowest chunk | 152 s (795 frames) | 159 s (665 frames): about a quarter of the time limit |
| Peak memory of a render | 1,265 MB | 1,519 MB |
| Plan function | 22 to 34 s | 30 to 72 s (the longer ones had boards written again) |
| Whole video, 45 to 60 s | 107 to 178 s | 134 to 210 s |
| Errors, timeouts, `WHITEBOARD_*_FAILED` | none | none |

Same three prompts before and after (compound interest 16:9, vacuna 9:16 in Spanish, water cycle on `auto`):
| | Before | After |
|---|---|---|
| Boards (panels) | 5 / 5 / 8 | 3 / 4 / 4 |
| Items per board | 5.2 / 5.0 / 5.2 | 8.7 / 8.2 / 12.2 |
| Board covered by drawings and writing (boxes) | 11.5 / 15.0 / 8.9 % | 37 / 31 / 26 % |
| Smallest writing while its board is shown, share of frame height | 6.9 / 3.3 / 9.1 % (in close views) | 6.9 / 3.7 / 6.9 % (the whole board) |
| Smallest writing in the final overview | 2.3 / 1.1 / 3.0 % | 3.5 / 1.8 / 3.5 % |
| Pen busy, measured on the picture (camera time left out) | 60 / 56 / 60 % | 77 / 79 / 77 % (63 / 66 / 63 % counting only tenths of a second in which ink appears) |
| Longest rest of the pen, measured | 1.9 / 2.0 / 2.4 s | 1.5 / 2.0 / 1.7 s |
| Camera moves a minute, measured | 19 / 16 / 14 | 4 / 5.5 / 4 |
| Items finished over 0.3 s late | 2 / 0 / 1 | 0 / 0 / 2 |
Defects of the first build that are gone: writing drawn under the caption (a close view let the next row into the caption band), a jump cut where a pull-back had not finished at a scene end, the final overview fading before it was seen.

Local figures (this Mac, x264 included): 55 to 85 ms a frame at 1080p, 0.7 GB peak; a plan costs USD 0.12 to 0.20 (two calls of the script model when a board is written again). 4K was not run again after this work.

## Costs
Per video: the director's usual calls plus about 14,000 characters of prompt (rules and the id menu); at most one small call for `auto`; one more call of the script model when the self-check fails a board; one Cohere embedding only for a drawing name not found by name. The library cost USD 4.90 once.

## Limits and known weak points (looked at the QA videos of the final build)
* **How full a board is still depends on the director.** When it plans boards in pairs (most 16:9 runs) a board has 12 to 18 items like the demos; when it writes each beat as its own full-zone board, the nine zones leave no room to merge and boards have 8 items. The self-check only catches boards under its bar.
* **Tall videos (9:16, 4:5)** are the weakest: the grid is 3x3 in every aspect, so a tall board has wide gaps between its rows and the final overview is small. A 2-column, 4-row grid for tall frames is the next step.
* Emphasis marks added for the pen's rests land on the latest unmarked thing, not on the most important word; in narrow formats a circle can touch its neighbour.
* A re-zoned title can end up in the middle of a board. Charts are small in a single zone (they take a second zone only when it is free).
* The library has 354 objects: a topic outside it gets stand-ins (cheese for wax cells) or written words.
* Pen busy measured 77 to 79 % with pen travel counted, above the 50 to 70 % aimed at; counting only tenths with new ink it is 63 to 66 %.
* The whiteboard look is never chosen by itself when the person asked for a presenter character (and a presenter never appears on a whiteboard video).
* Only Latin handwriting: every letter of en, es, fr, de, it, pt, nl, pl, fi has pen strokes (tables rebuilt with `scripts/whiteboard_proto/glyph_table.py`, which needs SciPy; the engine does not). A sign outside the tables is written from the font with a plain left-to-right pen path, not a traced centre line. Ties are one word. The editor apps have no board editor (editing the narration re-ties the board). 4K not re-measured. 1:1 and 4:5 were looked at as local renders only.

## Files
`engine/whiteboard/` (core, board, hand, spec, primitives, library), `engine/scenes/elements/whiteboard.py`, `engine/whiteboard_policy.py`, `engine/assets/whiteboard/` (two OFL fonts with licences, glyph tables, library index), `engine/whiteboard/score.py` (the self-check), `scripts/whiteboard_local.py` (a whole video on a laptop), tests `test_el_whiteboard.py`, `test_whiteboard_policy.py`, `test_whiteboard_score.py`, `test_looks.py`.

## Try it locally
```
AWS_PROFILE=qa AWS_REGION=eu-west-1 python backend/scripts/whiteboard_local.py "Explain how compound interest makes savings grow, as a whiteboard video" out_dir --seconds 40
```
