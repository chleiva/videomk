# Watermark decoupled from how a video is made (owner requirement, 28 Nov 2026)

Requirement: creating a video (whiteboard, cartoon, photos) is one thing; the watermark is an independent layer applied at the very END, so that (a) it can never change layout, content area, caption position, scene composition, timing or the plan / board scores, and (b) a customer who later upgrades can get the SAME video without the watermark: same plan, same cached scene segments, only the last compositing step differs.

## 1. Audit: where the watermark influenced anything before the final composite (base 5f613a7)
| # | Place | Coupling found | Now |
|---|---|---|---|
| 1 | `engine/frame.py` | `Frame.top_inset` (content box starts lower for a top-corner mark: 9:16/1:1/4:5 about 144/52/40 px), `Frame.cap_lift` + `caption["bottom"] - cap_lift` (16:9 captions raised 40 px), `with_top_inset`, `with_cap_lift`, `base_margin_top` | all removed; `margin_top` = the shape's own margin, `caption` = the fixed table, for every account |
| 2 | `engine/renderer.py` | built `watermark.build(...)` in `__init__`, replaced `self.frame` with the band / lift, drew the mark last in `frame_at` (with first-chunk fade-in and outro_k) | no watermark code at all; `Renderer` has no `wm`. `output_size()` factored out for the final stage |
| 3 | `engine/watermark_spec.py` | `CAPTION_LIFT`, `content_inset()`, `CONTENT_GAP`, `layout()` evaluated the caption box *with the lift* and returned `cap_lift`; caption box included its bottom padding | pure placement per shape; no lift, no inset; the caption zone is the text extent only (16:9: the mark sits in the strip under the text, 2 % margin) |
| 4 | `engine/watermark.py` | `Watermark.apply()` (per-frame PIL compositing inside the scene renderer), `inset`, `cap_lift`, `windows`, `fade` | artwork builder only (white + shadow layer, ink + glow layer, custom logo); compositing moved to `final_stage.py` |
| 5 | `engine/timeline.py` | (a) end card appended as a `title` scene in `scenes` (changes scene list, total duration, music length, `moments` clearance); (b) `build_timeline` subtracted `END_CARD_S` from `min_seconds` / `fit_seconds` (length fit, pace); (c) `shortest()` the same; (d) `chunk_plan` hash carried `wm`, `first`, `wmv: 4`; (e) `chunk_timeline` carried `watermark`; (f) `_chunk_watermark` | (a) card is `end_card_timeline()`, a separate one-scene timeline the final stage renders; (b)(c) removed: the fit is identical with and without a watermark (the video is 2.4 s longer than asked when the card is on: the card is the only added duration); (d)(e)(f) removed. `timeline["watermark"]` only carries the spec (and the `moments` windows, computed from the content's own scene times) through to the final stage |
| 6 | `engine/director.py`, `handlers/plan_handler.py` | the script was written and fitted to `minutes*60 - 2.4` when the plan had an end card (`options.end_card`) | the director never hears about the end card: same script, same plan |
| 7 | `engine/scenes/elements/whiteboard.py` | `ctx.frame.top_inset` in the geometry cache keys (the board's content box moved with the band) | key without it; board geometry and score identical with and without a watermark |
| 8 | `engine/scenes/viz_scenes.py`, `elements/presenter.py` | `_credit_y` used `base_margin_top`; presenter stub frame carried `top_inset` | plain `margin_top`; stub cleaned |
| 9 | segment / scene fingerprints | `chunk_plan` hash: `wm`, `first`, `wmv` | none of them: the segment hash of a watermarked video is exactly the hash of the same video without a watermark |
| 10 | `handlers/render_chunk_handler.py` | passes `chunk_timeline` to `Renderer`; the chunk timeline carried the watermark (so the mark was inside the cached segment) | the chunk timeline has no watermark; the cached segment is watermark-free (no code change in the handler itself) |
| 11 | `handlers/finalize_handler.py` | stitched segments + audio and uploaded (no watermark work; the mark was already in the frames) | stitches the master, then calls `final_stage.export()` when the timeline has a watermark |
| 12 | `engine/cover.py` | pops `watermark` from the cover's timeline, draws its own brand lockup | unchanged: the designed cover is its own artwork and was already independent of the account's mark |
| 13 | whiteboard policy / score (`whiteboard_policy.py`, `whiteboard/score.py`) | no reference to the watermark (checked) | unchanged; a test proves scores are identical across watermark modes |
| 14 | audio (`pipeline.make_audio`) | `timeline.duration` included the card, so music ran / faded over it | audio is the content's; the card gets 2.4 s of silence in the final stage |

## 2. Design
```
plan -> timeline (content only) -> render chunks (watermark-free, cached by content hash)
     -> finalize: stitch segments + audio = MASTER (no watermark, stream copy)
     -> final_stage.export(master): the watermark layer and the closing card  -> r{rev}.mp4
```
`engine/final_stage.py`:
* **Lockup overlay.** `watermark.Watermark` pre-renders two transparent PNGs at the real output size (white + soft shadow, ink + soft glow; a custom logo: its own colours + shadow). ffmpeg overlays them at the mark's fixed place (`watermark_spec.layout`, per shape). The layers' alpha is computed per frame from an expression of the time `T`: *always* = eased fade in over 0.6 s and gone with the closing fade to black; *moments* = the timeline's windows (video seconds, eased ramps). Opacity is baked into the layer.
* **White or ink.** The brightness under the mark is measured on the finished (watermark-free) frames, 4 samples a second, judged per scene piece (scenes cut into pieces of at most 4 s) with hysteresis around the middle of the 0.55 to 0.66 band; white and ink crossfade over 0.4 s at the change. The closing fade to black is ignored. So legibility does not depend on what the scene designer put in the corner.
* **End card.** `timeline.end_card_timeline()` (silent title scene, the video's theme, shape and language) is rendered to a 2.4 s TS segment (rises from black, ends on the closing fade) and concatenated after the content (stream copy). The audio gets `apad` 2.4 s of silence (no music tail, no sting). The content's length, audio, captions and music fade are untouched.
* **Cost.** Only the video track is re-encoded (same x264 settings as a segment), plus the 2.4 s card; the audio is copied except for the card padding (re-encoded AAC 192k). A local 720p 6 s test: about 6 s. The finalize function has 10 GB / 10 min / 8 GB tmp. **Not measured on Lambda** (see section 6).
* **Same video without the watermark.** `final_stage.export(tl, master, audio, out, spec_override=None)` returns the master unchanged (no re-encode, no scene drawn). `backend/scripts/watermark_reexport.py --video-id V --rev N --watermark none --out file.mp4` rebuilds the master from the video's cached segments (`timeline_handler.plan_chunks` gives their hashes) and audio mix and passes it through the stage with another spec (`none`, `keep`, or any watermark JSON). A missing segment stops it (nothing is re-rendered). Wiring to a customer button is out of scope.
* **Position (fixed per shape, content does not move).** 16:9 bottom right (2 % margin, under the caption text); 9:16 top left under the platform header (x 38, y 200); 1:1 and 4:5 top left (x 38, y 38). The mark can sit over a scene margin or the paper edge; the shadow / glow and the white-or-ink choice keep it readable. A corner chosen by a premium account is still moved when it would hit the caption text box or the credit line (a pure function of the shape).

## 3. What changed (files)
engine: `frame.py`, `renderer.py`, `watermark_spec.py`, `watermark.py`, `timeline.py`, `director.py`, `final_stage.py` (new), `handlers/finalize_handler.py`, `handlers/plan_handler.py`, `handlers/timeline_handler.py` (`plan_chunks`), `scenes/viz_scenes.py`, `scenes/elements/{whiteboard,presenter}.py`; `scripts/watermark_reexport.py`, `scripts/watermark_looks_sheet.py` (new). Tests: `tests/test_watermark_decoupled.py` (new, 38), `tests/test_watermark.py`, `tests/test_watermark_presence.py`, `tests/test_languages.py` adapted.

## 4. Caches and hashes that change
* **Segment hashes of watermarked videos change once**: the `wm`, `first`, `wmv` keys leave the hash, so a watermarked video now hashes exactly like the same video without a watermark. That invalidates every cached segment of a video made with a watermark (before: every video of a free account, every promo video of the owner's, each carried `wmv 3` or `4`): these are re-rendered on their next edit or re-render; nothing else is touched. **Segments of videos without a watermark keep their hash (the hash payload of a video without a watermark is byte-for-byte what it was; `RENDER_VERSION` is unchanged) and stay valid.** The number of invalidated segments cannot be counted from here (no bucket access in this task); it is the number of `generation/v2/*/segments/*` objects of watermarked videos, all in the 7-day working-set expiry anyway.
* After this change a free video and the same video for an account without a watermark SHARE segments (the first render of either fills the cache for both).
* The whiteboard in-process picture cache keys lose `top_inset` (memory only).
* The timeline JSON of a watermarked video no longer has the end-card scene and its `duration` is the content's; `timeline["watermark"]` is the only trace.
* `Frame` no longer has `top_inset` / `cap_lift`; nothing else read them.

## 5. Behaviour changes to know about
* A video with the end card is now content + 2.4 s: before, the script, the pace and the stretch aimed at the length asked INCLUDING the card (30 s asked: 30 s made). Now 30 s asked: about 30 s of content + 2.4 s card. This is the owner's "the end card is the only added duration".
* The card has no music tail (before, the music faded over it); it is silent.
* The mark no longer follows the content: in 9:16 / 1:1 / 4:5 the content starts where it always did (no 144 / 52 / 40 px band), so the mark can overlap a heading's margin or the top of a drawing.
* One more video re-encode pass for watermarked videos (the mark is drawn on the stitched video): see the Lambda note below.
* Generation loss: the content video of a watermarked video is encoded twice (segment, then the overlay pass), both CRF 20 (draft CRF 28); a local test sees re-encoding noise below 4 levels of mean difference outside the mark.

## 6. Not verified / to check on QA after deploy
* The final stage in Lambda (ffmpeg of the layer: `geq`, `overlay`, `apad`, `-filter_complex_script` must exist in the layer's static ffmpeg; locally they run on the imageio-ffmpeg / system ffmpeg of the venv, so check `ffmpeg -filters` in the layer).
* Time and memory of the extra pass in V2FinalizeFn for a 5 and a 10 minute 1080p video and for a 4K one (10 min timeout): measure `final_stage.export` duration in the logs (`WATERMARK_INK`). If it is too slow the pass should move to a fan-out step (per segment) or a dedicated function.
* Both preview (draft) and final paths; a custom logo (the loader reads `generation/v2/<video>/assets/watermark.png`); `moments` with a real long timeline; a video with `end_card` and music (audio padding, A/V length within 0.1 s); the `watermark_reexport.py` script against real S3 objects.
* The two CDK-stack watermark tests that fail in this environment on the base fail the same way.
