# Cost levers before launch (2026-11-28)

Owner decision 28 Nov: lower the cost of a video **without lowering quality**, before launch. Owner rule added during the work: no smaller model, lower effort or shorter instructions for anything the viewer sees or hears unless an A/B shows the same quality; only lossless savings ship. Everything that could not be shown neutral is listed in section 5 as an option, with numbers.

Labels: **M** = measured by me on QA Bedrock (profile qa, eu-west-1, plan stage only, no render, no voice), **V** = a vendor page read 2026-11-28, **E** = estimate, **U** = not verified. Total QA Bedrock spend of this work: about USD 1.7 of the USD 3.00 budget. Nothing deployed, nothing touched in production.

## 1. Why a whiteboard plan costs USD 0.14 to 0.33 (M, three real plans, before any change)

Sonnet 5.5 USD 2 / 10 per million tokens in / out; Haiku 5.5 USD 0.10 / 0.50.

| Plan (60 s) | Calls of the script model | Cost | Seconds |
|---|---|---|---|
| EN 16:9 "compound interest" | script 19,064 in / 2,594 out (0.064); **trim retry 19,194 in / 8,600 out, cut off at the limit (0.124)**; board review 5,373 / 5,062 (0.061) | **0.250** | 129 |
| ES 9:16 "vacuna" | script 20,150 / 2,707 (0.067); **trim retry 20,280 / 8,600, cut off (0.127)**; review 7,440 / 8,600, cut off, no JSON (0.101); review asked again 7,490 / 2,052 (0.036) | **0.331** | 162 |
| FR 16:9 "cycle de l'eau" | script 19,035 / 2,578 (0.064); review 5,360 / 6,136 (0.072) | **0.136** | 67 |

* The first script call is the same for every look: 12k fixed input tokens (instructions, scene docs, voices, rules, the whiteboard rules and the drawing menu) plus 7k per video (the encyclopedia notes and the request). Input is only USD 0.038 of its USD 0.064.
* **Repeated work.** In 2 of 3 whiteboard plans (and in the normal plan measured below) the first script was valid but long (168 words for 130 asked), so `plan.generate_plan` sent the whole prompt again to "trim". With whiteboard rules that retry thinks until the output limit (8,600 tokens, USD 0.12), returns 623 characters and the code falls back to the first script (the `over` path). The engine trims by arithmetic afterwards in any case (`length.fit_script`).
* **The board review** (`whiteboard_policy.review`) is a second Sonnet call, USD 0.04 to 0.10; 90 % of it is output, mostly thinking; once it ran out of tokens before any JSON and was paid twice.
* A normal 60 s plan makes the same script call (15.4k in, 1.2k out, USD 0.043) with no review; a cartoon conversation the same with a shorter answer. So the whiteboard extra is the retry (when it happens) plus the review.
* Nothing was cached before this work (`cache_read` 0 on every call).

## 2. What ships (all lossless)

### 2.1 Prompt caching of the fixed script prompt (`engine/llm.py`, `engine/plan.py`)
* **Bedrock supports it for Sonnet 5.5 and Haiku 5.5** (V: Bedrock "Prompt caching" page: Claude Sonnet 5.5 and Haiku 5.5 are in the explicit-caching table, minimum 512 tokens per checkpoint, 4 checkpoints, TTL 5 minutes or 1 hour, fields `system`, `messages`, `tools`; Converse takes `cachePoint`, InvokeModel takes `cache_control`). We call `invoke_model`, so the block is `{"type":"text","text":...,"cache_control":{"type":"ephemeral"}}`. M: both models, through the global profiles, wrote 12,603 tokens on the first call and read 12,603 on the second.
* **Price (V, Anthropic pricing page; the Bedrock page showed no table for these models, only the note that Sonnet 5.5 cache reads were halved on 7 Oct 2026, which matches 0.05x): Sonnet 5.5 input 2.00, 5-minute cache write 2.50 (1.25x), 1-hour write 4.00 (2x), cache read 0.10 (0.05x), output 10.00. Haiku 5.5: 0.10, 0.125, 0.20, 0.01, 0.50.** U: the Bedrock bill for cache tokens (checked for plain tokens in `docs/PLANS_PROPOSAL`, not yet for cached ones; look at Cost Explorer after the first day).
* **What is cached.** The script prompt's system text is split at a marker (`llm.CACHE_BREAK`, placed in `plan.system_prompt` right after the scene docs): the first 8,239 tokens (header, JSON format, scene docs) are the same in every language and look, so one cache entry serves all videos; the language, voices, rules, craft and look blocks come after it. The marker never reaches the model (test), the text the model reads is byte for byte what it read before, so the answer cannot change except by sampling. Long videos (`staged.py`) use the same prompt for every section, so their sections read the cache too.
* **Safety.** `PROMPT_CACHE=off` switches it off; a `ValidationException` that mentions the cache repeats the call once without it and keeps caching off for the rest of the container (`PROMPT_CACHE_REJECTED` in the log); a prefix under 3,000 characters is never marked.
* **Cost accounting.** Bedrock's `input_tokens` excludes cached tokens, so the cost now includes them (`estimate_cost(..., cache_read, cache_write)`); the video record gets `cache_read_tokens` and `cache_write_tokens` next to `c_script` (`costs.add_tokens`).
* **Measured, normal 60 s plan "how tides work" (M):**

| | Script calls | Script cost | Plan total |
|---|---|---|---|
| Caching off | 15,369 in / 1,270 out (0.0434) + retry 15,499 / 1,147 (0.0425) | 0.0859 | **0.0861** |
| On, cold (first video, the retry reads) | write 8,239 + 6,512 in (0.0467) + retry read 8,239 + 6,642 in (0.0259) | 0.0726 | **0.0727** (-16 %) |
| On, warm (another video within 5 minutes) | read 8,239 + 5,528 in (0.0245) + retry (0.0237) | 0.0482 | **0.0485** (-44 %) |

* **Per call:** a read saves 8,239 x (2.00 - 0.10) / 1M = **USD 0.0157**; a write costs 8,239 x 0.50 / 1M = **USD 0.0041** extra. So: a video whose single script call finds a warm cache saves 0.016; one with a retry (or a long video with sections) saves 0.012 even cold; **a single call on a cold cache loses 0.004**. The saving therefore depends on traffic: at least one other video, retry or section within five minutes. With launch traffic that is likely but unproven (U). The entry is refreshed by every hit.
* Whiteboard plans after the change (M, same three prompts; see 2.3 for what is noise): ES 0.331 -> 0.183, FR 0.136 -> 0.089, EN 0.250 -> 0.131. The caching part of each is the 0.016 per hit; **the rest of the difference is sampling** (the retry did not happen in FR and the model's thinking length varies run to run: reviews cost 0.022 to 0.101). Do not read 45 % as the caching effect.

### 2.2 Render function for HD on 4 GB (stack change, not deployed)
* **Today:** one render function `v2_render_chunk`, 10,240 MB, for every resolution (`engine_v2.py`). A 1080p chunk keeps about 1.4 cores busy and peaks at 1.4 GB on QA (`docs/FOUR_K.md`, `docs/WHITEBOARD.md`: 1.27 to 1.52 GB); a 10 GB function has 6 vCPU. Cost = seconds x memory.
* **Local measurement (M, `backend/scripts/render_cores.py`, demo timeline, 3 chunks, one process):** 1080p: 1.38 cores (CPU time of Python plus ffmpeg over wall time), 28 to 41 ms a frame, process peak 0.95 GB; 720p: 1.13 cores, peak 0.92 GB. A Lambda gets one vCPU per 1,769 MB (V, Lambda docs), so **4,096 MB = 2.3 vCPU, above the 1.4 to 1.5 a render uses: render time should not grow**, and the GB-seconds fall to 40 % (4 / 10) of today's. At 3,008 MB (1.7 vCPU) the margin is thin, so 4,096 is the choice.
* **Estimate (E):** HD rendering $0.070 a minute -> **about $0.028 a minute** (-$0.042), about 60 % of the render bill; $0.15 per 3-minute video. 4K stays at 10,240 MB, unchanged.
* **Change:** a second function `v2_render_chunk_hd` (same code, 4,096 MB, 10 min, 1 GB `/tmp`, same environment, layers and every grant of the 10 GB one: loops, segments, catalog `v/*` and `w/*`); the timeline step marks each chunk `big` (the final render of a 4K video) and the state machine's chunk Map picks the function with a Choice on `$.big` (previews and drafts of a 4K video are small and go to the HD function). `-c hdRenderMemoryMb=0` gives the old stack. Retries are as before (2 attempts).
* **`cdk diff` summary (synth of the QA stack, `cdk diff` itself needs the account):** 4 new resources (Lambda function `V2RenderChunkHdFn`, its service role, its default policy, its log-retention custom resource): **418 -> 422 resources** in the main stack (the limit is 500); 4 changed: the two state machines (`generate_video_workflow_v2`, `edit_video_workflow_v2`: the Map's item processor becomes Choice -> two Lambda tasks) and their two role policies (invoke permission for the new function). No change to any existing function (`v2_render_chunk` stays 10,240 MB), table, bucket or Cognito. Tests: `tests/test_hd_render_cdk.py`.
* **U, must be proven on QA before prod:** a real HD video (whiteboard, cartoon, photos, a 3-minute one) on 4,096 MB: milliseconds per frame against the 10 GB numbers in `docs/WHITEBOARD.md` (0.24 to 0.28 s a frame at 1080p), peak memory under about 2.5 GB, no timeouts (limit 600 s, slowest chunk seen 159 s), and the new `c_render` below. The CPU share of a Lambda can behave differently from a laptop; if a chunk is slower than 1.4x, raise to 6,144 (`-c hdRenderMemoryMb=6144`) before giving it up. The 10 GB audio and finalize functions are not changed (small share).

### 2.3 Render cost on the video (`c_render`, `render_gbs`)
Each render chunk now returns the GB-seconds it ran (wall time x the function's memory) and the finalize step adds them to the video: `render_gbs` and `c_render` (= GB-s x USD 0.0000166667, x86 list price, `costs.add_render`). **Not part of `cost_usd`**, because `cost_usd` has a hard cap (USD 1.50) that a 12-minute 4K render alone (about USD 1.9) would trip; the plans economics read `cost_usd + c_render`. Edits add their re-rendered chunks (cached chunks cost nothing and report nothing). It is an estimate: the bill rounds each run up to 1 ms and adds cold starts; the audio and finalize functions (10 GB, seconds) are not included (E: under 5 % of the render). "Try again" clears the new fields with the others (`video_retry.COST_ATTRS`). No stack change.

### 2.4 Tests
`tests/test_cost_levers.py` (9: marker split, never reaches the model, text identical with caching off, price of cache tokens on Sonnet and Haiku, rejection fallback once, switch off, the fixed part is the same in en/es/fr, cache and render fields on the video, chunk GB-seconds, retry clears the fields), `tests/test_hd_render_cdk.py` (4: memory of both functions, the old stack with `hdRenderMemoryMb=0`, the Choice on `$.big`, identical grants), `tests/test_four_k.py` (chunks marked `big`). Also run, all green: `test_engine`, `test_engine_e2e`, `test_length`, `test_length_fit`, `test_dictation`, `test_whiteboard_policy`, `test_polly_lively`, `test_languages`, `test_staged`, `test_video_retry`, `test_clips_on_demand_cdk`.

## 3. Whiteboard quality, before and after (M)
Score = the existing whiteboard self-check (`plan.whiteboard.score`). The prompts are identical; the only change in what the model reads is none (caching), so differences are sampling. Final boards failing the bar / complaints / items per board / coverage:

| | Before | After |
|---|---|---|
| ES 9:16 | 3 of 5 / 5 / 9.6 / 0.385 | 1 of 5 / 2 / 12.0 / 0.416 |
| FR 16:9 | 3 of 4 / 3 / 12.0 / 0.431 | 3 of 4 / 3 / 12.2 / 0.413 |
| EN 16:9 | 0 of 4 / 0 / 12.8 / 0.420 | 1 of 4 / 2 / 9.2 / 0.423 |

No fall that is more than run-to-run variation (the same plan replayed through the review at the same settings gave 1 to 3 failing boards). The review is a rewrite whose result is only kept when it scores at least as well as the first boards (`score.better`), which already guards quality.

## 4. Savings per video type (60 s, plan step only, Bedrock list prices)
| Type | Before (M) | With caching | Why |
|---|---|---|---|
| Normal | 0.086 (script, with a retry) | 0.073 cold, 0.049 warm | read 0.0157 per call; write premium 0.0041 |
| Whiteboard | 0.136 to 0.331, mean 0.24 | 0.016 less per hit, and the rest unchanged by design | the two expensive repeats (retry, review) are not touched, see 5 |
| Cartoon conversation (0.05 to 0.11) | not run again | same mechanism, 0.012 to 0.016 per hit (E) | its script call carries the same fixed first 8,239 tokens |
| Render, HD (all types) | about 0.070 a minute | about 0.028 (E, U) | 4 GB instead of 10 GB |
In credit terms (E): caching 0.01 to 0.03 and the render function about 0.04 per minute: a credit about **USD 0.08 to 0.10 lower than 0.15**, most of it from the render function.

## 5. Options that did not ship (not proven neutral) 
| Option | Measured | Why not shipped |
|---|---|---|
| Effort low on the board review | same pre-review FR plan: medium 5,594 out, USD 0.0667, final 1 failing board / 1 complaint; **low 582 out, USD 0.0165, 3 failing / 5 complaints** | quality worse |
| Haiku 5.5 for the board review | 2 calls cut off at 8,600 tokens, no JSON, USD 0.0097, boards unchanged | does not work as is |
| Effort low on the trim retry (`PLAN_RETRY_EFFORT=low`, built, off) | E: output 8,600 -> about 2,700 tokens, USD 0.12 -> about 0.05 on the plans that retry | no A/B of the trimmed script yet |
| Skip the trim retry when `fit_script` will cut it anyway | E: saves the whole 0.04 to 0.12 | changes the script (model-trimmed vs sentences cut) |
| Raise the retry's output limit so it finishes instead of being cut off | would cost more, but the trimmed script would then be used | changes the product |
| Second cache checkpoint after the look blocks | E: a further 3 to 5k tokens, USD 0.006 to 0.009 per hit on whiteboard | needs the blocks shown to be identical across videos; not measured |
| 1-hour cache (`ttl: 1h`, write 2x = USD 0.0082) | breaks even above 0.5 hits per hour | pays at low traffic only if hits are rare in 5 minutes; decide with real traffic |
| Cache the board review prompt (2.6k fixed tokens) | E: 0.005 per hit | small |
| Cache the research agent's loop (`complete_tools`) | not measured (no search key here) | left out |
| 3,008 MB for HD | 1.7 vCPU, E: another -25 % of the HD render | margin thin; try after the 4,096 proof |

## 6. What is not verified
Bedrock's bill for cached tokens; the hit rate at real traffic (a cold single call costs USD 0.004 more); the HD render on Lambda at 4,096 MB (time per frame, memory, every look); the 1.4-core figure is from a Mac, not Lambda; cartoon and long (staged) plans were not run with caching; failed runs and edits are not in these numbers; whiteboard quality has three prompts per side.
