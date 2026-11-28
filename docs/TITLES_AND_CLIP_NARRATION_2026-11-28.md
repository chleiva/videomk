# Titles clear of the corner mark, and the clip description never narrated (28 Nov 2026)

## 1. Titles and cards under the corner mark (9:16, 1:1, 4:5)

QA finding: in 9:16 the bullet card title ("Known standard") and other templates sat at the top left, where the corner logo lands. The earlier fix (`presenter.CARD_TOP`) covered the cartoon cards only.

### Audit
Every scene reads its top from `Frame.margin_top` (through `SceneCtx.top`, `Frame.box()` and `title_block` / `heading`), so the cause was one number per shape, not one bug per template:

| shape | old `margin_top` | lowest the mark reaches (largest custom logo, medium) | new `margin_top` |
|---|---|---|---|
| 9:16 | 150 | y 308 (x 38, y 200 under the platform header) | 310 |
| 1:1 | 70 | y 146 | 150 |
| 4:5 | 80 | y 146 | 150 |
| 16:9 | 70 | mark is bottom right, under the caption text | unchanged |

Changes (all constants of the shape, the same for every account; no watermark input, the mark stays a final layer, scenes are byte-identical with and without it):
* `engine/frame.py`: `_MARGIN` tops 310 / 150 / 150. To keep the working area, the content bottom with captions of 1:1 is 840 (was 780) and of 4:5 is 1080 (was 1040): the box shrinks by 20 (1:1: 690 tall instead of 710) and 30 (4:5) instead of 80 and 70. 9:16 box: 1075 tall instead of 1235. New `Frame.credit_y` keeps the clip / photo credit line (top right) where it was (it used `margin_top - 30`); `viz_scenes._credit_y` and `watermark_spec.credit_rect` use it.
* `presenter.CARD_TOP` is now `margin_top + 10` (320 / 160 / 160): redundant but kept as the cartoon card's explicit floor; its test still pins one constant.
* The map scene paints on a panel at the box origin, so its panel and title chip start below the mark too (asserted in the test).
* Full-bleed pictures and clips are not text; their own text (credit, the one word) is in the check.

### Test
`tests/test_titles_clear_of_mark.py`: every built-in scene sample and every element sample (236 cases) x 4 aspects, drawn at three moments, with every text run and every card-sized rounded rectangle recorded in design units; none may intersect the mark rectangles of the largest lockup, the largest mark, the widest custom logo and the small lockup (placed by `watermark_spec.layout`, auto position). A 16:9 custom logo wider than the bottom-right corner allows is moved to the top left by the placement rules (a premium edge case, skipped in the test: the 16:9 content there starts at the unchanged top margin 70 and a wide custom logo can land on a heading; not changed here).

Existing tests adapted: `test_watermark_decoupled.py` (pinned tops), `test_sea_backdrop2.py` follows `CARD_TOP`.

### Stills
`backend/scripts/titles_clear_stills.py` renders each template in 9:16, 1:1, 4:5 with the real mark artwork (largest lockup) composited at its real place and its rectangle outlined: `~/Downloads/videomk-looks/web/titles-clear/` (one PNG per template and shape plus `sheet_*.jpg`).

### Consequences
* Non-landscape videos lay out about 160 (9:16) / 40 (1:1) / 30 (4:5) design px less tall; some elements fit their content a little smaller. 16:9 output is unchanged (the golden test passes).
* Cached segments: the layout of non-landscape scenes changed but `RENDER_VERSION` was NOT bumped (it would invalidate every segment, including 16:9). Segments cached before this change for 9:16 / 1:1 / 4:5 videos keep the old layout until their content changes: bump `timeline.RENDER_VERSION` on deploy if that matters.

## 2. The clip description narrated (video upload)

QA finding: the narration read the description of an uploaded clip aloud ("The clip opens on a plain red screen..."), and the captions showed it.

### Where it leaked
1. `engine/plan.ensure_video_clips`: a clip the planner did not place got a beat of its own whose narration was the clip's `summary` ("The clip opens on a plain red screen, ..."). This is the literal leak in the QA video.
2. `common/vidup.planner_block`: the prompt said "give its beat narration of about that many seconds" with no rule against describing; the description and the speech transcript sat in the prompt as ordinary data, so a model could read them out (or the transcript as if the narrator said it).

### Fix
* Prompt (`planner_block`): the description is for the planner only, never to be read, quoted, paraphrased or translated in narration or captions; the narration tells the story around the picture; the speech transcript is what the people in the clip say, never to be said by the narrator (let it play as a pause beat, or talk about it in other words); a sentence that copies the description is removed.
* Model-free post-check (`common/vidup.scrub_narration`, called by `ensure_video_clips` on every beat of the plan, `user_text` = the person's request): sentences of at least 4 words are dropped when a run of consecutive shared words covers 60 % of the sentence (and is at least 4 words), or when 75 % of its words are found in one description line that it covers at least half of (reordered copy). Sources: the overall line, each second's line and each sentence of the transcript. A sentence the person wrote in their own request is theirs to quote and stays (the explicit "quote it" choice). Dropped sentences are returned as a warning on the plan (`narration copied the clip description, removed: ...`). Captions come from the narration, so they are clean too.
* The unused-clip fallback beat now says a fixed neutral line ("Here is a moment from the clip."), never the summary. The clip's `alt` (from the summary) is not spoken or captioned for a clip that loads (it only shows in the unavailable placeholder).

### Tests (`tests/test_video_upload_engine.py`)
Prompt carries the rule; four copy shapes (summary verbatim, a line verbatim, near verbatim, the transcript said by the narrator) are removed and the surrounding story sentences kept; story narration is untouched; the person's own quoted words stay; `ensure_video_clips` strips, warns, and never reads the summary for an unused clip.

### Limits (not verified)
* The check is lexical. A true paraphrase with different words, or a translation (a Spanish video of an English description), passes; the prompt is the only guard there. Not tried against a live model.
* A beat emptied by the check keeps an empty narration (a silent beat); the planner contract allows pause beats on clip scenes. Length fit afterwards is the engine's usual one.
* The staged (section-by-section) planning path does not pass `video_assets` to the model at all; it only gets `ensure_video_clips`, which now also scrubs.
