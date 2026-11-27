# Library clips on demand: spend ledger

Every paid call made while building and proving the feature (docs/CLIPS_ON_DEMAND.md). Approved limit: at most 6 generated clips (about $4). Provider: Gemini API, `gemini-omni-1.2-flash`, key from the repository's `.env` (never printed or stored anywhere else). Models and embeddings: Bedrock, QA account. Nothing was deployed.

| # | When (UTC, 2026-11-27) | What | Size | Provider tokens (video / thought / input) | Provider cost at list price | Charged to the test budget | Result |
|---|---|---|---|---|---|---|---|
| 0 | 18:5x | first call, refused: "store=true is required when response format has video delivery set to URI" | - | none | $0 | - | HTTP 400, nothing made; the client was fixed |
| 1 | 18:5x | smoke call: "rain falling on a quiet pond" | 3 s, 360p, 16:9 | 5,793 / 1,166 / 132 | $0.080 | - (direct call, outside the flow) | 640x360, 3.03 s, 21.8 s to make; not stored |
| 2 | 19:01 | video A beat 3: bees on lavender | 8 s, 720p, 16:9 | 46,336 / 710 / 138 | $0.563 | $0.581 | gate 8/10, stored, used in video A, reused by video C |
| 3 | 19:01 | video A beat 2: hands folding dough | 8 s, 720p, 16:9 | 46,336 / 768 / 150 | $0.563 | $0.581 | gate 8/10, stored, used in video A, reused by video B (a Free account) |
| 4 | 19:02 | video C beat 1: steaming mug of coffee | 8 s, 720p, 9:16 | 46,336 / 1,049 / 136 | $0.566 | $0.581 | gate 8/10, stored, used in video C |

**Generated clips: 4 of the 6 allowed (one 3 s smoke clip, three 8 s library clips). Provider total at list price: $1.77.**
Around them: small and large model calls (9 reusability decisions, 6 briefs, 3 gates, about 12 clip checks) $0.026 measured in the first run, about $0.01 more in the second pass that only rendered the video; Cohere embeddings (about 20 short texts and 3 images) and Polly narration (about 600 characters, twice): under $0.02 together, not measured per call. **Total about $1.83.**

Notes
* The provider reports no dollar amount; "provider cost" is its own token counts times Google's list price read on 2026-11-27 ($12 per 1M video tokens, $9 per 1M text output tokens, which is how the "thought" tokens are counted here, $1.50 per 1M input). The invoice has not been seen, so the thought-token line is an assumption (about one cent a call).
* 5,792 video tokens per second at 720p and 1,931 at 360p were confirmed exactly by the answers' usage blocks.
* The full record of the run (prompts, usage blocks, decisions, counters, ledger rows) is `docs/clips_on_demand/proof_2026-11-27.json`; the video's plan is `docs/clips_on_demand/proof_plan.json`.

## Images and sketch objects (2026-11-28; approved: up to $2 more)

| # | What | Provider cost (token counts at list price) | Charged to the test budget | Result |
|---|---|---|---|---|
| 5 | object sheet, first try: violin | $0.0375 (estimated: the same sheet size) + gate $0.0065 | $0.047 | rejected by the gate (1 of 1), 14.9 s |
| 6 | object sheet: honeycomb, beehive, skateboard, violin, kite, teapot | $0.0375 + gates about $0.04 | $0.082 | 6 of 6 accepted, 10.3 s |
| 7 | object sheet: igloo, accordion, sundial, trowel | $0.0376 + gates about $0.026 | $0.068 | 4 of 4 accepted, 11.7 s |
| 8 | image: wooden beehives in a meadow (2048x1152 high) | $0.0443 | $0.05 | kept, 9.7 s |
| 9 | image: jar of honey | $0.0442 | $0.05 | rejected (captions area), 7.2 s |
| 10 | image: empty classroom | $0.0442 | $0.05 | kept, 9.6 s |
| 11 | C2PA probe: one 1024x1024 low PNG | 824 output tokens = $0.025 | - | the PNG carries a C2PA manifest; the JPEG output does not |

OpenAI total: about **$0.27** (3 sheets, 3 images, 1 probe). Bedrock around them (gates, briefs, checks, embeddings): about $0.08 measured ($0.063 + $0.0065 + $0.002) plus a few embeddings. **About $0.36 of the $2.**
The watermark measurements and the metadata work made no paid call. Two QA catalog images were rewritten with metadata and watermark (S3 and DynamoDB requests only).
The full records: `docs/clips_on_demand/proof_objects_2026-11-28.json` and `proof_images_2026-11-28.json`; the watermark numbers: `docs/clips_on_demand/watermark_eval_2026-11-28.json`.
