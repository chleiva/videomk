# Keeping what is shown in step with what is said (2026-11-24)

## What was wrong
- Reveal times for list items, diagram nodes, chart bars, timeline events and gallery photos followed a **fixed schedule** spread over the scene (10 %-72 % of its length), whatever the narrator said. Measured on a real video (a transistor explainer) the items appeared on average **1.15 s away from the word that names them**, up to 1.4 s late, 1.2 s early, or with no spoken counterpart at all.
- Word timings (captions) were a proportional guess (about 160 ms mean error).
- **Text never faded.** The canvas drew text through PIL's RGBA mode, which ignores a text colour's alpha on an RGB image: text with alpha 0 was drawn at full strength, so every fade-in showed at full strength from its first frame (shapes were fine). Fixed in `Canvas.text`.
- The percentage ring let its number be up to 1200 px wide inside a ring whose inner diameter is about 570 px.

## What it does now
1. **Words from the audio** (`engine/align.py`, free, a few ms per beat). Polly's generative voices have no speech marks, and a second request would not be the audio we play, so the waveform is the source: pauses are found in the audio and matched in order to the text's punctuation (the pause COUNT and ORDER are strong evidence, position a weak tiebreak), words are placed by syllable weight along the voiced time axis inside each phrase, and each inner boundary is snapped to the nearest energy dip (+-80 ms). Stored next to the audio as `audio/<hash>.words.json`; audio made earlier is measured on first use. Not stored when confidence is low (the estimate is kept).
   Accuracy against Polly's exact speech marks on real speech (453 words, 3 voices): **mean 80 ms, 90th percentile 198 ms, worst 368 ms**, against 160 / 404 / 616 ms for the old estimate. Four real recordings with their exact marks are fixtures in `tests/fixtures/speech`.
2. **Anchoring** (`engine/sync.py`). Each revealable item is matched to the narration word that first names it (normalised content words: accents, plurals, numbers (`73%` is `73`), no stopwords, English and Spanish; matched in order, tightest cluster wins). The reveal starts 0.15 s before that word. Items never named are interpolated between their named neighbours, or spread over the spoken part of the beat; never the old fixed schedule. Gallery photos cut when their subject is named (fully in 0.15 s after the word, never under 0.8 s on screen); a stat counts up when its number is spoken.
3. **The planner is told** to narrate list items in the order shown using each item's own key words, and a plan whose list scenes name fewer than 60 % of their items gets ONE repair attempt before it is accepted (no extra model call when the plan is fine).
4. **The check** (`sync.report`, no model, no render): the timeline step runs it on every video and logs a warning when anything appears more than 0.5 s early or 0.4 s late. `python scripts/check_sync.py <video_id>` prints the table for any finished video (`*` marks videos that predate anchoring, measured against the old schedule).

## Not done
- A model that watches the finished video and judges sync (it would cost money and time; the check above is exact for everything that has a spoken counterpart).
- Items the narrator does not name are interpolated, not anchored: the prompt rule and the repair attempt reduce them, they cannot be eliminated without rewriting the narration.
- Charts: only bar labels are anchored (not the values); diagram edges follow their nodes.
