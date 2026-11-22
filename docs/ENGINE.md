# videomk engine v2

An animated-explainer renderer that runs entirely on **Lambda + Step Functions + S3**. Nothing is provisioned
that costs money while nobody is using it (no Fargate, no always-on database, no NAT, no secrets with a monthly fee).

## What it makes

A narrated, captioned explainer built from *structured scenes*, not generated stills:

| Scene | What animates | Marginal cost |
|---|---|---|
| `title` | words rise in, accent bar draws on | ~0 |
| `bullets` | cards slide in on cues | ~0 |
| `diagram` | auto-laid-out nodes pop in, arrows draw on, edge labels | ~0 |
| `chart` | bars grow with count-up values, or a line draws on | ~0 |
| `timeline` | line draws, dated events pop in | ~0 |
| `stat` | number counts up, % gets a progress ring | ~0 |
| `quote` | quote reveals word by word | ~0 |
| `image` | licensed real photo with Ken Burns + credit | ~0 (CC0 / PD / CC BY via Openverse) |

Plus karaoke captions, crossfades, procedural music (ducked under speech) and SFX. All of it is original
or licence-free by construction.

## Pipeline

```
API ─▶ launcher (auth, validate, quota, idempotency) ─▶ Step Functions
   Plan ──legit?──no──▶ MarkRejected (refund) ─▶ done
     │ yes
     ▼
   Beats  (Map, ≤5 at once)  per beat: TTS ─▶ wav in S3;  image scene ─▶ photo scout ─▶ jpeg + ledger row
     ▼
   Timeline  scene length = measured narration length; writes timeline.json; plans ~30 s chunks
     ▼
   Parallel ┬ Chunks (Map, ≤8 at once)  each Lambda renders frames [f0,f1) ─▶ MPEG-TS segment
            └ Audio                      narration + music + sfx ─▶ AAC
     ▼
   Finalize  ffmpeg -c copy concat + mux ─▶ MP4 + preview GIF in S3, credits/chapters ─▶ COMPLETE
   (any failure ─▶ MarkFailed, quota refunded)
```

Each Lambda does a bounded unit of work (a beat, a 30 s chunk), so the 15-minute limit never matters and a retry is cheap.
State between steps is S3 keys, not data (Step Functions' 256 KB limit never bites).

## Design decisions, with evidence

**Renderer: Pillow + numpy, 2x supersampled.** Measured on one core, 1080p frame, same test scene:

| Option | ms/frame | Lambda deployability |
|---|---|---|
| resvg-py (SVG → PNG) | ~270 (PNG encode dominates) | clean wheel, but ~5-10x slower |
| skia-python | not measured (needs libEGL here) | wheel links ~10 system libs (EGL, GL, X11, xcb…) that Lambda doesn't ship |
| **Pillow 2x + cached sprites** | **~41 mean over the 8 scene types** (draft 540p: ~20) | manylinux wheel, nothing native to bundle |

Anti-aliasing comes from rendering at 2x and box-reducing; expensive things (gradients, blurred shadows) are cached sprites.
The ambient background is composed at 1/8 scale and its drift is time-quantised to 0.1 s so ~2/3 of frames reuse it.

**Chunks are independent and seamless.** Frames are a pure function of time (`Renderer.frame_at(t)`; a test asserts two
independent renderers agree pixel for pixel). Segments are MPEG-TS with closed GOPs and chunk starts aligned to the GOP, so
`ffmpeg -c copy` stitches them without re-encoding. Verified: timestamps continuous across seams, an IDR frame at each
boundary, exact duration, decoded frames ≈ 42-44 dB PSNR vs. the renderer.

**TTS per beat, not per video.** Exact scene timing for free, parallel synthesis, and cheap re-synthesis of one edited beat.
Providers (`gemini`, `openai`, `mock`) sit behind one interface; keys live in SSM (`/videomk/<provider>_api_key`).
The Gemini key is sent as a header, never in the URL.

**Music and SFX are generated** (numpy), so no licence, no Content ID claims, nothing to store. A curated CC0 pack can replace
them behind the same interface.

**LLM output is untrusted.** `plan.validate_plan` whitelists and clamps every field; the model can never choose a file path
(images are resolved by the scout; a test injects `asset: s3://other/…` and checks it's dropped). The renderer and the chunk
loader independently refuse keys outside `generation/v2/<video_id>/assets/`.

**Photos are licence-aware.** Only CC0 / public-domain / CC BY (no share-alike, no non-commercial), https only, ≥1600 px wide.
Every photo gets a ledger row; the finalize step writes an *Image credits* + *Sources* block (and chapters, when valid for YouTube)
into `youtube_description`. Downloads go through an SSRF guard (public https only, every redirect re-checked), a size cap, and
a decompression-bomb limit, then are re-encoded to JPEG (metadata stripped).

## Cost model (10-minute video, ~1,500 words, ~45 beats, ~8 photos)

| Item | Estimate | Basis |
|---|---|---|
| Planning (Sonnet-class, ~3k in / ~6k out) | $0.08–0.12 | list token prices, **not verified** against your Bedrock bill |
| Narration (~9,000 chars) | $0.14–0.16 | Gemini/OpenAI TTS list prices as reported by secondary sources, **verify** |
| Photos | $0.00 | Openverse (free) |
| Render Lambdas | $0.05–0.12 | measured ~1.8 compute-seconds per video-second on 4 busy cores × 3 GB × 600 s; Lambda vCPUs differ, so **run `engine_selftest`** |
| Audio, stitch, S3, Step Functions (~75 transitions) | ~$0.02 | |
| **Total** | **≈ $0.30–0.45** | |

`costs.py` records the running cost on the video item and fails the job past `MAX_VIDEO_COST_USD` (default $1.50), refunding the quota.
Draft mode (540p, no supersampling, `draft: true` on a chunk) is ~2x cheaper/faster for previews and edits.

## Deploy and verify

```bash
cd backend
pip install -r requirements-dev.txt && pytest                  # 53 tests (needs ffmpeg/ffprobe on PATH)
./layers/build_layer.sh                                         # linux/x86_64 layers, no Docker needed
aws ssm put-parameter --name /videomk/gemini_api_key --type SecureString --value '…' --region us-west-2
#   (v1 reads /videomk/openai_api_key and falls back to the old Secrets Manager secret)

cdk deploy                                                      # v1 (default). Adds the Usage table; see "Breaking changes"
cdk deploy -c engine=v2 -c ttsProvider=gemini                   # enables v2 and points the launcher at it

aws lambda invoke --function-name engine_selftest --region us-west-2 /dev/stdout
```

`engine_selftest` is the first thing to run: it reports Python/numpy/Pillow versions, the bundled ffmpeg version, whether
`libx264`, `aac`, `sidechaincompress` and `amix normalize` exist, `/tmp` space, and **ms per frame on the real runtime**.
Use that number to set memory (`make_fn(memory=…)`), chunk size (`CHUNK_SECONDS`) and `-c renderConcurrency`.

Context flags: `engine`, `ttsProvider`, `ttsVoice`, `planModelId`, `maxVideoCostUsd`, `defaultMinutes`, `renderConcurrency`,
`dailyVideoLimit`, `httpUserAgent` (Wikimedia/Openverse ask clients to identify themselves: set a contact string).

**Quotas to check before a real run:** Lambda concurrent executions (new accounts can start very low; a 20-chunk render needs 20),
Bedrock model access for `PLAN_MODEL_ID` (falls back to Haiku 4.5 then Haiku 3 if unavailable).

**Housekeeping:** add an S3 lifecycle rule expiring `generation/v2/` after 7 days (the bucket is imported, so CDK doesn't manage it).
Finalize already deletes segments and the mixed audio; plan/timeline/beat audio/photos are kept for cheap re-renders.

## Breaking changes from the hardening pass

- `POST …/generate` now requires auth + path match, and a prompt of 10–2000 chars (also enforced at API Gateway).
- Daily quota (`dailyVideoLimit`, default **5**) on a new on-demand `Usage` table; refunded on rejection/failure.
- Status `REJECTED` (+ `reject_reason`) is new; the UI handles it.
- Step Functions input is now `{user_id, video_id, prompt, usage_day}` only (headers/JWT are no longer forwarded).
- The old `generate_video` Lambda (dead code since the Step Functions migration) is removed.
- `frontend/src/lib/*` was reconstructed (it was never committed); diff against your local originals before merging.

## What is and isn't verified

| Verified here | Not verified (no AWS / network from the build sandbox) |
|---|---|
| All 8 scenes render at every animation phase, including degenerate/hostile props (visually inspected) | Real Lambda timings, memory sizing, concurrency |
| Seamless chunk stitching, exact duration, A/V mux, ducking, GIF, credits | The bundled ffmpeg's filters on Lambda (`engine_selftest` checks) |
| Every handler end to end on moto S3/DynamoDB (53 tests), CDK synth for v1 and v2, IAM scoping | Bedrock, Gemini, OpenAI TTS, Wikipedia, Openverse: written to the documented shapes, tested against fakes only |
| Launcher auth/validation/quota/idempotency, REJECTED path, cost cap, SSRF guard | Step Functions execution semantics (data flow was traced by hand, not run) |
| Frontend build + typecheck + headless-browser check of the login redirect and state check | Sound quality of generated music/SFX and of the chosen TTS voice (listen before launch) |

## Product guardrails (YouTube)

YouTube demonetizes *mass-produced, templated, low-originality* uploads; sources describe a template slideshow with an AI voice
as the archetype. The engine helps (varied scene grammar, grounded facts with sources, real licensed photos, credits), but
**originality is a product decision**, not something a renderer can supply:

- let users edit the script/scenes and add their own angle (the plan and timeline are plain JSON, which makes this cheap);
- don't offer one-click bulk generation; keep the quota;
- remind creators to use YouTube's *altered or synthetic content* disclosure where it applies;
- keep the credits block in the description.

Prompt text is sent to the LLM, the TTS provider, Wikipedia (research) and Openverse (photo search): reflect that in the privacy policy.

## Roadmap (not built)

1. **Chapter fan-out for >12 min:** outline → per-chapter plan in a Map with a shared style bible; today's single-call planner is capped at 12 min.
2. **Critic agent:** sample frames of the rendered chunks → vision model checks overflow, image/narration mismatch, unsupported claims → re-render only flagged chunks.
3. **Editor + draft previews:** edit a beat's text/scene, re-synthesize one beat, re-render only affected chunks at 540p.
4. **TTS bake-off:** blind-test Kokoro / Qwen3-TTS / Gemini / OpenAI / ElevenLabs on 3 scripts (~$5) and pick the default; forced alignment (whisper.cpp) for word-accurate karaoke.
5. **Packaging:** thumbnail, title options, YouTube upload via the Data API.
6. **Alternative renderer:** if you need richer motion graphics (SVG/CSS/D3/KaTeX), Remotion Lambda is the drop-in swap behind `render_chunk` (check its licence for your team size).
