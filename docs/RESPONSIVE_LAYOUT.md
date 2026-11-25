# Responsive layout: making a scene or element work in 9:16, 1:1 and 4:5

Decided 2026-11-25: vertical, square and 4:5 videos work now. Today every scene is native only for 16:9; the 10 built-in scene types (title, bullets, diagram, stat, quote, chart, timeline, image, gallery, clip) are native for all four aspects; the 28 elements still to convert render through a **framed fallback** (a small landscape card on the themed frame). This guide is everything an engineer needs to convert elements. Background: `docs/PIPELINE_V3.md` section 7, formats table `docs/CREATE_API.md`.

## The contract
* `engine/frame.py`: `Frame(aspect, resolution)`. Scenes lay out in **design units**: a virtual canvas whose short side is 1080 (16:9 1920x1080, 9:16 1080x1920, 1:1 1080x1080, 4:5 1080x1350). `cv.W`/`cv.H` are the design size; the renderer scales to the real pixels (720p is a scale of 2/3). A scene never knows the resolution. 16:9 numbers do not change: converted code must stay pixel-identical in 16:9.
* `ctx.frame` is the `Frame`. Use: `fr.W, fr.H, fr.cx, fr.cy`, `fr.landscape / fr.vertical (9:16 and 4:5) / fr.square`, `fr.margin_x`, `fr.margin_top`, `fr.type_scale` (1.0 landscape, 1.22 for 9:16, 1.12 square, 1.15 for 4:5: multiply type that must stay legible on a narrower frame), `fr.right_reserve` (130 on 9:16: the platform buttons column; matters only low on the frame).
* `ctx.top` / `ctx.bottom` / `ctx.box` = the **content box** (x0, y0, x1, y1) above the caption band (captions on) or the frame's bottom limit (captions off). Everything must stay inside it: 16:9 (140, 70, 1780, 800); 9:16 (72, 150, 1008, 1450); 1:1 (80, 70, 1000, 780); 4:5 (80, 80, 1000, 1040) (captions on). The top 150 of 9:16 and the bottom 250 / right 130 are the platform UI zone.
* Captions: `scenes/captions.py` places them per frame (9:16 bottom edge at y=1670, max 2 lines, above the UI zone). Scenes never draw into the caption band.
* **Tag** the element: `Element(..., formats=("16:9", "9:16", "1:1", "4:5"))` lists the aspects `draw` lays out natively. Default `("16:9",)`. Tag only the aspects you verified (all four is the goal; if a layout cannot work in the square, leave "1:1" out and it is framed there).
* Framed fallback (`scenes/formats.py: draw_framed`): an element whose `formats` lacks the requested aspect is drawn at 1920x1080 on an offscreen canvas (captions off) and pasted, scaled to the frame width minus margins, as a rounded card in the middle of the content box. It never fails or blanks. The renderer records `renderer.fallbacks[scene id] = {scale, min_text_px, readable}`; text under 22 design px after the shrink is flagged `readable: False` (previews print it). The director is told which scenes are native by `formats.scenes_for(frame)` and `formats.format_scene_hint(frame)`; `formats.check_scene_formats(frame, scenes)` returns warnings (never edits).
* Rules for native layouts: no 1920/1080/960/540/140/800/1000 literals for geometry (use `ctx.frame`, `ctx.box`, `cv.W/H`); keep every part inside `ctx.box`; vertical frames need larger relative type and fewer words per line (start font sizes higher, allow more wrapped lines, shorter rows); sync, `anchors`, `cues`, `cues` semantics, reveal order are identical in every aspect (do not change `sanitize`, `cues`, `anchors`).
* Caches keyed by size: any cache of images, sprites or layouts must include what changes with the frame (pixel size, `max_w`, `ss`). Example below.

## Worked example: `kinetic_text` (already converted, `scenes/elements/text_lists.py`)
Before: `max_w = 1560`, sizes `range(136, 44, -4)`, `CENTER_X`, `ctx.bottom - CONTENT_TOP - 110`, cache keyed `(words, flags, ss, max_h)`.
After (the whole change):
```python
fr = ctx.frame; cx = fr.cx; land = fr.landscape
avail = ctx.bottom - ctx.top - 110
size, lines, total = _kinetic_layout(words, tuple(flags), cv.ss, int(avail),
                                     1560 if land else fr.W - 2 * fr.margin_x,       # width of the content box
                                     136 if land else int(136 * fr.type_scale))      # bigger type, fewer words per line
...
cv.text(cx + ox, ...)            # was CENTER_X + ox
cv.rrect(cx - bw / 2, ...)       # was CENTER_X - bw / 2
# _kinetic_layout(words, flags, ss, max_h, max_w, start) is lru_cached: max_w and start are now part of the key
# a word wider than the frame forces a smaller size (the old code only checked the height)
Element(..., formats=("16:9", "9:16", "1:1", "4:5"))
```
`_mid_y(ctx)` in `text_lists.py` now uses `ctx.top` (it equals `CONTENT_TOP` in landscape). Landscape output is byte-identical: `tests/test_formats.py::test_landscape_pixel_identical_to_before` guards the built-ins; for your element, compare a render before and after yourself (see Testing).
Other reference implementations: `scenes/text_scenes.py` (title, stat, quote), `viz_scenes.py` (`_hbars` chart for many categories, `_timeline_vertical`, `focus_point` image crop), `flow_scenes.py: layout_tall` (flow top to bottom, U-snake in the square), `list_scenes.py` (cards: single column and a horizontal card variant).

## Checklist per element
1. Grep your file for `1920`, `1080`, `960`, `540`, `CENTER_X`, `CONTENT_TOP`, `CONTENT_BOTTOM`, `cv.W * `, fixed x ranges (`140`, `1780`, `200`, `1760`), caption-related constants. Every hit is geometry to derive from `ctx.frame`/`ctx.box`/`cv.W`.
2. Decide the shape per aspect. Landscape: unchanged. Vertical/square: re-flow, do not stretch: columns become rows, side-by-side becomes stacked, long horizontal axes become vertical, grids reduce their column count, labels move above values. Prefer a second layout function over parameter soup (`_xxx_tall`), selected by `ctx.frame.landscape`.
3. Type: start sizes `x fr.type_scale` (or larger), minimum around 30 design px in vertical frames, allow more wrapped lines but cap the block height by `ctx.box`.
4. Pictures: use cover crops with a focus point, not the centre. `viz_scenes.focus_point(img)` gives a saliency guess biased to the centre and the upper third; `_cover(src, tw, tht, z, motion, p, focus)`. A user's own photo that a crop would hurt (lose more than ~28%) is shown whole over a blurred copy (`_contained_image`, `_user_photo_fits`). Map tiles / images that were fetched at 16:9 need a re-crop (compute the view from `ctx.box` size, not 1920x1080).
5. Keep the reveal times and anchors untouched; check the last state (everything shown) fits, not just the first frames.
6. Caches: add the frame-dependent values to any lru_cache key (pixel size `cv.W * cv.ss`, max_w, start size).
7. Tag `formats=(...)` on the `Element` only when all listed aspects pass the tests and look polished in the previews.
8. Run the tests and look at the sheets (below). Fix what is cramped, overlapping the caption band, or smaller than ~30 px.

## Pitfalls
* Literals hidden in helpers (`_mid_y`, sprites sized in px, `cv.W * cv.ss` for photos is fine because `cv.W` is the design width; `1920` is not).
* Anything anchored to the right edge (`1880`, `1780`): use `cv.W - 40`, `ctx.box[2]`.
* `fit_text` only limits the wrapped HEIGHT; an unbreakable word (a number like `$1,250`, a URL) can still be wider than the frame. Check `cv.measure(...) <= max_w` and shrink (see `draw_stat`).
* The caption band: with `ctx.captions` False `ctx.bottom` is larger; test with captions on (tests do).
* Image cover crops: crop from the focus point, clamp the view box inside the source (`_box`), never `(sw/2, sh/2)` for tall frames.
* Do not draw into the top 150 (9:16) or the bottom of the frame; credits go at `_credit_y(fr)` and `cv.W - 40`.
* Do not rely on `ctx.frame.resolution`: layouts are resolution independent.
* Stock footage is portrait in vertical videos (`clips.scout_clip(orientation=...)`): clip scenes must cope with any footage shape (cover crop).

## Testing and previews
* Contact sheet for any element and aspect, with the framed fallback marked: `python scripts/element_preview.py <name> --aspect 9:16 [--theme paper] --out /tmp/x.png`; the built-ins and (with `--elements`) every element: `python scripts/format_preview.py --aspect 9:16 --elements [--only name,name] --out sheet.png` (prints framed scale and smallest text). LOOK at the sheet (Read the PNG): text readable at phone size, nothing under captions, end state complete.
* `cd backend && ../.venv/bin/python -m pytest -q -p no:cacheprovider tests/test_formats.py` renders every built-in sample and every element sample in every aspect (720p): no exception, not blank, content inside the frame, inside `content_box` for non-landscape built-ins, framed cards inside the box, captions inside their band (9:16 clear of the UI zone), 16:9 unchanged (golden hashes in `tests/fixtures/golden_16x9.json`).
* To pin an element's 16:9 pixels while converting: render before and after with `tests.element_utils.render(name, props, lt, dur, theme, captions=True, draft=False)` and compare `tobytes()`.
* `tests/format_samples.py` holds the deterministic sample props (and synthetic photos/clips); add yours if an element needs pictures.

## Elements still to convert (all tagged `("16:9",)` today; rough effort for one engineer-day = 1 d)
Text: `counter` 0.25 d, `definition` 0.5 d (card layout, stacked origin/example). Lists: `checklist` 0.5 d, `table` 1 d (columns to stacked records or fewer columns; hardest of the lists), `ranking` 0.5 d. Process: `steps` 0.5 d, `funnel` 0.5 d, `flowchart` 1 d (reuse `flow_scenes.layout_tall` ideas), `sequence` 0.75 d. Compare: `versus` 0.5 d (stack the two sides), `matrix` 1 d. Data: `bar_race` 0.5 d (horizontal already), `pie` 0.5 d, `area` 0.5 d, `stacked` 0.75 d, `scatter` 0.5 d, `scale_compare` 0.75 d, `pictogram` 0.5 d. Code and math: `code` 0.75 d (fewer columns, bigger font, wrap), `equation` 0.5 d. People and sources: `headline` 0.5 d, `dialogue` 0.5 d. Media/Photos: `icons` 0.5 d, `annotated_image` 1 d (annotation positions relative to a re-cropped image), `photo_collage` 1 d, `photo_frame` 0.5 d, `chapter_card` 0.5 d. Maps: `map` 1.5 d (projection and tiles must be fitted to the box). Total about 18 engineer-days; groups of 3-5 elements per engineer in parallel. Done: `kinetic_text`.
