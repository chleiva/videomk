# Sea / bees QA defects (2026-11-28)

Source: QA run 5 (3 cartoon videos: sea 9:16, sea 16:9, bees 1:1). Branch `sea-defects`, merged on top of `cartoon-ground-2`.

NOTE: the brief said cartoon-ground-2 was already in the tip `ccr-3c41ecff-680028`. It was not (git merge-base showed it unmerged; the QA deploy was built from 5f613a7 = cartoon-ground-2). It is merged into this branch first.

## 1. Feet in the shallow water (9:16, tall_sunset_beach_vertical)
Why: the stored ground began at y 0.72 of the picture, exactly where the foam line is, and the scene's layers shift down with the push-in (about 0.03 near the bottom). Dry sand starts near 0.74 in the picture.
Fix: ground top moved to 0.79, water hazard extended to 0.78 (data in `common/vector_stand_zones.json`, marked by_eye). With the caption rule of item 3 this backdrop no longer holds a cast in 9:16 or 4:5 (the dry sand lies below the caption lines), so the planner falls back to the drawn ground. It still serves scenes without characters. Other water backdrops (tropical_beach, pirate_cove, mountain_lake, old_harbour_fort, spa_stones_pond, river_valley, camping_lake, coast_cliffs, deep_ocean_reef, abstract_misty_lake) were checked on an overlay sheet: their masks sit on sand or grass; tropical_beach and pirate_cove hug the foam line closely (left as is, no defect seen in the render).

## 2. A named animal dropped (fox and bear -> fox and owl)
Why: when the request carried the `look: cartoon` field without a cast, `art_direction.asked` returned an empty cast and ignored the words; `fill_cast` then added the topic partner (owl).
Fix: `art_direction.named_cast` reads the characters that are the subject of the explaining ("a fox and a bear explain...", "explained by...", Spanish forms). `asked` uses it when the cast is "auto". A topic animal ("how bears hibernate") is not cast. An explicit `cast` field still wins; fallback unchanged when nothing is named.

## 3. Captions over legs and feet (1:1, 4:5 groups)
Why: the square/4:5 group row was cut at "caption top + 46" but the legs were drawn down to a ground below it, so the lower legs and feet ran behind the captions.
Fix: new `stand_zone.caption_top(frame)` (read only; caption position and the watermark/cap_lift logic are untouched). Square and 4:5 groups with captions now stand whole with feet 8 units above the caption lines; `place()` refuses foot rows below `caption_top` for whole figures; ground lines re-derived model-free (`backend/scripts/vector_stand_rederive.py`). A single presenter in 1:1/4:5 stays cut at the waist (no legs shown). Side effect: fewer backdrops hold 2-3 characters in 1:1 (ground must now exist above the captions); 44 of the 158 zone records changed shape support, none changed usable/unusable.

## 4. Chart / stat cards
The sanitiser already drops empty charts (needs two non-negative bars, one positive). The "empty" card was timing: items appeared on narration cues, possibly late in the scene. Now `_early` bounds reveals (first at most 0.7 s, then 0.6 s apart). Chart labels (limit 14 -> 24 characters) wrap to two lines instead of clipping. Points: the heading box shrinks until the points can be 40 units or more (was 26 floor, giving tiny text under a two-line heading).

## Verification
Tests (targeted, all green): test_stand_zone, test_presenters, test_art_direction, test_vector_presenter, test_presenter_arms, test_vector_character_cast. New tests cover the beach ground, caption-safe feet in all shapes, whole groups in 1:1/4:5, named cast, early reveals.
Local stills: ~/Downloads/videomk-looks/web/sea-defects/ (sea_defects_sheet.jpg and the PNGs).

## What remains
- Not verified on a real deploy (no QA/prod run, no TTS, no planner model): the named-cast fix is tested on the pure function and `decide`, not through the live planner.
- 1:1/4:5 figures in groups are smaller than the old waist-up row (trade for no cut legs).
- Chart/stat text in first and last scenes was checked only through the rule changes, not re-rendered at full video length.
- The vertical beach is unavailable for characters in 9:16 (would need a different picture, or captions moved).
