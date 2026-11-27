# Whiteboard look, phase 1a: library, writing, board spec, renderer (2026-11-27)

Follows `docs/WHITEBOARD_PROTOTYPE_2026-11-27.md` (phase 0). The owner chose method D (image-model art as filled vector outlines, revealed along a hidden pen path, colour in the enclosed areas) and asked to keep the clean marker style exactly. Phase 1a is everything that does not touch the engine, planner or stack. Code: `backend/scripts/whiteboard_proto/`. Outputs: `~/Downloads/videomk-whiteboard/` (phone copies and captions in `web/`).

**Measured** = run today on this Mac. **Looked** = judged from extracted frames; I cannot hear audio or watch motion.

## 1. Object library

| | Measured |
|---|---|
| Planned (`lib_plan.py`) | 372 objects in 14 groups: nature, animals, science, health, people (30 poses and roles), faces (12), business, money, technology, places, transport, home and food, symbols, time and ideas |
| In the library | **354** (344 passed on the first try, 8 on the second, 2 on the third) |
| Dropped after three tries | 18: arrow_up, arrow_down, arrow_right, cycle_arrows, plus, minus, equals, infinity, eye_crossed, no_sign, power, link_chain, org_chart, podium, snowball, bridge_gap, soap_hands, face_sleepy |
| Why rejected (66 rejections in 420 attempts) | line too thick, mostly the plain symbols (about 40); the gate's answer unreadable (7); the gate said "not clearly that thing" or "blob" (the rest) |
| Line width of accepted objects | 11.2 to 23.2 px on the sheet, median 16.1; equalised to one weight at render time |
| Gate score | 8 or 9 of 10 for 346 objects, 7 for 8 |
| Cost | **USD 4.90** for the build = **USD 0.014 per accepted object** (image sheets 2.71, vision gate 2.33) |
| Time | about 25 minutes, 3 sheets in parallel |
| Storage | `s3://videomk-qa-catalog-552357225438/w/`: `<id>.json` (package), `<id>.png` (thumbnail), `index.json`. 708 files, 39 MB. Nothing large in git |

**A package** (`<id>.json`, 50 to 160 KB): `w`, `h`, `width` (marker width in its own units), `ink` (SVG outlines from vtracer), `fills` (SVG of each enclosed area), `fill_colours` (one colour name or `none` per area), `strokes` (the ordered pen path), `pen_length`, `meta` (`title_en`, `title_es`, `synonyms_en`, `synonyms_es`, `tags`, `description`, `score`), `provenance`.

**The quality gate** (`lib_build.py`) is one vision call per object (Sonnet 5.5, three pictures: the drawing, its numbered areas, its numbered pen strokes). It answers: is it clearly the named thing, one clean line, complete, no text, a score; and in the same call it writes the names, synonyms, tags and description, picks a colour for each area (restrained: at most two colours, gaps stay white) and gives the order a person would draw the strokes in (head before body, frame before wheels). Automatic measures run first: line width in range, not touching the sheet edge, a sane stroke count. A rejected object is generated again, up to three times, then dropped and listed.

The model changed the stroke order of 238 of 354 objects. On the six I looked at closely the result was better than the rule alone (the person's head now comes before the body); I did not review all 354 reveal strips.

**Search** (`lib_index.py`): Cohere Embed v4 through Bedrock, one 1024-d text vector per object (English and Spanish names, synonyms, tags, description), float16 base64, 1.1 MB index. Test set of 42 queries (30 English, 12 Spanish): **39 right at rank 1, 41 in the top 3**. Misses: "computer" returned keyboard, mouse, chip (laptop and desktop lower); "bank" returned banknote first; "the internet" scored low everywhere. Scores of correct top hits start at 0.31; ten things that are not in the library scored 0.16 to 0.37 (a skateboard found the scooter at 0.37). The two ranges overlap, so `MIN_SCORE` is 0.30 and the planner must be shown the top titles and choose, as with the vector catalog.

Known flaws (looked at the contact sheets): colours are sensible but not uniform across similar objects (I forced all faces to yellow afterwards); a few symbols are missing (see dropped list; arrows, plus and minus are drawn by code or written anyway).

## 2. Writing

`writing.py`. Any text: titles, sentences, bullet and numbered lists, numbers, `^{ }` superscript, `_{ }` subscript, `\frac{a}{b}`, `->`, Spanish accents, ñ, ¿, ¡. Lines break and the size shrinks to fit a zone.

* **Letters are the font's own outlines**, uncovered along each letter's centre line in writing order (top first, round letters anticlockwise, dots, accents and bars last), the pen slowing through bends and lifting between strokes. I first drew the centre lines themselves as the letters: at 4K it was smooth, but "a" read as "o" because the stem and the bowl share a line. Keeping the outline and using the centre line only as the pen path fixed it.
* **Each written word is tied to its spoken word** (the engine's word alignment); words the voice does not say literally (numbers, symbols, formulas) are spread between their neighbours.
* **Hands**: `neat` (Patrick Hand) and `casual` (Caveat). Both SIL OFL 1.1, licence files read and bundled in `fonts/`. Both cover Latin with Spanish; Caveat also has Cyrillic. Other scripts need their own handwriting fonts (Arabic and Devanagari also need shaping, which Pillow only does with libraqm).
* **Tools**: `pen` (9 units, quick), `marker` (20 units), `highlighter` (goes under the ink). The outline is grown or thinned to the tool's width.
* **Marks by hand**: underline, double underline, circle a word, box, tick, cross, cross-out, arrow, highlight.
* **Variation**: each letter gets its own size (±3 % neat, ±6 % casual), slant, small lift, spacing; each line a slow baseline wander. Deterministic per seed; no two letters share a seed.
* **Chalk on a dark board** came nearly free (same vectors, other colours); no chalk texture.

What still looks typed or mechanical (looked):
* One shape per letter. The variation is size, slant, position and spacing, not different letter forms, so close up it is a very regular hand.
* Stroke order inside a letter is by rule; some letters are not written the way a person writes them.
* Whole sentences written word for word run 0.1 to 0.7 s behind the voice (the list in the demo). Key phrases keep up.
* The casual hand with the thick marker is too heavy: small letters fill in. Use the pen with it.
* A fraction's digits are small at normal sizes.

## 3. Board spec and renderer

A **board** is JSON that a planner can write: no coordinates. Example: `boards/photosynthesis.json`.

```
{"id", "version": 1, "lang", "voice", "hand": "neat|casual", "tool": "pen|marker", "theme": "paper|chalk", "camera": "auto|static",
 "narration": ["sentence", ...]            ("|" at the end of a sentence = a longer breath)
 "items": [ ... in drawing order ... ],
 "i18n": {"es": {"voice", "narration", "text": {id: text}, "say": {id: say}, "say_lines": {id: [...]}, "word": {id: word}}}}
```

| Item | Fields |
|---|---|
| Drawing | `draw` (library id), `zone` or `near`+`side`, `size` xs/s/m/l/xl, `ink` colour, `fill` (true, false or a colour), `say` |
| Writing | `write` (text with markup), `zone` or `near`+`side`, `size` xs..xl, `hand`, `tool`, `ink`, `align`, `say` or `say_lines` (one per text line), `follow` (default true: word by word) |
| Connector | `connect`: arrow, wavy, dashed, line; `from`, `to` (item ids); `color`, `count`, `bend`, `head`, `say` |
| Mark | `mark`: underline, double_underline, circle, box, tick, cross, cross_out, arrow, highlight; `on` (item id); `word` (a word, a list of words or an index); `color`, `side`, `say` |

`say` is `[sentence index, word, occurrence]`. An item with no `say` is drawn right after the previous one. Zones: `top-left, top, top-right, left, centre, right, bottom-left, bottom, bottom-right`, and spans such as `top-row`, `left-wide`, `full`. A drawing that is not in the library becomes its name written in a box.

`boardspec.compile_board(spec, words, aspect, size)` does the rest, deterministically:
* **Layout**: the board has the output's aspect and a 3x3 grid of zones with safe margins. Things placed `near` another avoid every other item (they try the other sides). Overlaps are reported as warnings.
* **Camera**: the close view is exactly 2x2 zones, and a window is only used if it cuts no drawing or text of the board at its edge; otherwise the camera stays wide. It moves only when the next item is outside the current window and ends on a pull-back framed on everything drawn.
* **Timing**: each item ends 0.15 s after its word starts; one pen; up to 1.6x faster when squeezed, up to 2.4x slower to use idle time. The report gives pen-busy share, the longest idle gap, late items and warnings.
* **Colour fill**: two to five broad diagonal passes, each only as long as the shape is wide there, with a round front; the marker shows the fill colour.
* **Aspects**: 16:9, 9:16, 1:1, 4:5 from the same spec. Sizes are board units, so 720p, 1080p and 4K are the same vectors at another scale.
* **Chunks**: `render_board.py --from S --to S` renders any passage alone. Finished items are cached; the cached frame equals a full recomposite (checked on 63 random frames in phase 0, difference 0).

Deviation from the research note: tall formats use the same 3x3 zone names instead of a 2x4 grid, so one spec serves every aspect.

## 4. The demo boards (acceptance test for layout and pacing)

| Board | Length | Pen busy | Longest idle | Warnings | 1080p render |
|---|---|---|---|---|---|
| photosynthesis | 25 s | 66 % | 1.2 s | none | 35 ms per frame |
| vaccines | 22 s | 82 % | 0.6 s | none | 30 ms per frame |
| compound interest | 26 s | 60 % | 1.8 s (two pauses over 1.5 s) | none | 32 ms per frame |
| writing demo (EN) | 21 s | 53 % | 1.0 s | none | 44 ms per frame |

Also rendered from the same specs: photosynthesis 9:16, vaccines 1:1, compound interest 4:5, writing demo in Spanish 16:9 and 9:16. No overlap warnings after the "avoid neighbours" rule.

What is still wrong (looked):
* Connectors go straight from one item to another and can cross a third (in 9:16 the arrow from the water drop passes over the roots; in 1:1 the arrow from the virus passes under the face).
* When an arrow joins two windows the camera pulls back and zooms in again; in a short board that is a lot of camera.
* Pacing is good only because I wrote extra beats into the boards (underline this, circle that). The planner must be told to do the same.
* In the vaccines board one pen label finishes 1.5 s late.

## 5. Render speed (measured, this Mac, including x264)

| | 1080p | 4K |
|---|---|---|
| Per frame | 25 to 55 ms | **234 ms** (8 s passage) |
| Preparing the board (once per render or per chunk) | 10 to 18 s | **194 s** |

The 4K preparation time is the problem: it grows much faster than the pixel count because the reveal map is computed per item on a large raster. As it stands a 4K chunk would spend minutes preparing before its first frame. The fix is to compute each item's reveal map once at a fixed modest size and enlarge it (the map is smooth), and to prepare only the items a chunk shows. Until that is done and measured, 4K whiteboard on Lambda is not proven.

## 6. Spend

USD 5.35 of the 40 cap: phase 0 0.26, library sheets 2.71, gate 2.33, narration for the demos 0.04, embeddings 0.01.
