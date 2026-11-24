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

The **edit** workflow reuses the same tail: `EditPrep` (which beats changed?) → Beats → Timeline → Parallel{Chunks, Audio} → Finalize.
See "Editor" below.
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
Providers (`polly` (default, IAM, no key), `gemini`, `openai`, `mock`) sit behind one interface; keys for the keyed ones live in SSM (`/videomk/<provider>_api_key`).
The Gemini key is sent as a header, never in the URL.

**Music and SFX are generated** (numpy), so no licence, no Content ID claims, nothing to store. A curated CC0 pack can replace
them behind the same interface.

**LLM output is untrusted.** `plan.validate_plan` whitelists and clamps every field; the model can never choose a file path
(images are resolved by the scout; a test injects `asset: s3://other/…` and checks it's dropped). The renderer and the chunk
loader independently refuse keys outside `generation/v2/<video_id>/assets/`.

**Photos: Unsplash + Openverse, reviewed by a vision model.** For each `image` scene the scout gathers up to 6 candidates
(Unsplash first, Openverse CC0/public-domain/CC BY to fill; wide, ≥1600 px, https only), sends ~512 px thumbnails to a vision
model (`REVIEW_MODEL_ID`, Haiku-class by default) together with the narration, and the model **picks the best fit or rejects them
all** (text/logos/watermarks, identifiable private people, mismatched subject). A rejected set yields a clean title card instead of a
bad photo; a reviewer failure falls back to the provider's relevance order; the model's answer is only ever parsed as a number, so text
inside an image can't steer anything. The chosen photo is downloaded through an SSRF guard (public https only, every redirect
re-checked), size-capped, checked against a decompression-bomb limit, and re-encoded to JPEG (metadata stripped).
Every photo gets a ledger row; finalize writes *Image credits* + *Sources* (and valid YouTube chapters) into `youtube_description`.

### Unsplash: what the integration does, and what is still open

The primary Unsplash terms pages could **not be read** from the build sandbox (host not reachable). The integration follows the
requirements as described in Unsplash's help-centre guideline pages: use the image URLs the API returns (we fetch `urls.raw` plus
imgix size params, which keeps the `ixid` token); call `links.download_location` when a photo is actually used (we do, once, only for the
photo that was chosen: never for rejected candidates); credit photographer **and** Unsplash with links carrying
`utm_source=<app name>&utm_medium=referral` (on-screen "Photo: Name / Unsplash", links in the description). `UNSPLASH_APP_NAME`
must be the name you register with Unsplash.

Open questions to settle before relying on it (re-read https://unsplash.com/api-terms and ask Unsplash if unclear):

1. **Video use.** Photos are baked into a rendered MP4. The hotlinking/"use the API URLs" rule was written for displaying photos in an
   app; whether a rendered video counts as compliant use is not something I could confirm.
2. **Working copy.** We keep a short-lived copy in S3 so edits don't re-download. Add a lifecycle rule expiring `generation/v2/`,
   or re-fetch at render time if Unsplash asks.
3. **Rate limits.** Demo apps are limited (secondary sources say 50 requests/hour; verify) and production access requires an approval
   that checks attribution. Each photo scene costs 1 search + 1 download-tracking call; with `UNSPLASH_ACCESS_KEY` absent the scout
   uses Openverse only, so nothing breaks while approval is pending.

Setup: `aws ssm put-parameter --name /videomk/unsplash_access_key --type SecureString --value '<Access Key>' --region us-west-2`.

## Editor

Anyone can review and change any part of a video. The design leans on properties the pipeline already had:

- **The plan and timeline are plain JSON** (beats: narration + scene + props), so a human edit is just a validated change to JSON.
- **Edits are operations, validated like LLM output**: `set_narration`, `set_scene` (all 8 types), `pick_image`, `insert`, `delete`, `move`,
  `set_chapter`, `set_meta` (title/theme/mood), `set_voice`. Ids are strict 8-hex (they end up in S3 keys); a person can never supply a file
  path; the whole batch is all-or-nothing (`edits.py`). Inserted beats get a client `ref` that later ops in the same batch can target.
- **Revisions + optimistic locking**: every edit writes `plan_rN.json` and bumps `rev` with a conditional write (a stale tab gets a 409);
  one render at a time per video; a render that never reports back stops blocking after 45 minutes.
- **Only what changed is re-made**:
  - narration audio is content-addressed by `hash(text, voice, style, provider)`: unchanged text is never re-synthesised;
  - photos are re-searched only when the query changes; picking a candidate re-uses the stored candidate list;
  - render chunks group whole scenes and are content-addressed by `hash(renderer version, look, the chunk's scenes, the scene before it)`,
    deliberately *excluding* absolute time (background motion is scene-relative), so after an edit every untouched chunk keeps its hash even
    though it moved in the timeline. Tested: edit scene 1 and chunks 2 and 3 keep their hash; edit the last scene of a chunk and the next chunk
    (whose opening crossfade shows it) re-renders too.
- **Preview vs publish**: *Preview* renders half-resolution drafts (own cache) in seconds and never touches the published video;
  *Publish* renders full quality (re-using every unchanged full-quality chunk from earlier renders) and creates a new version
  `videos/<user>/<video>/rN.mp4`; earlier versions stay.
- **Failures are contained**: a failed edit sets `edit_state=FAILED` only; the published video stays playable.
- **Cost**: each revision has its own budget (`cost_rN`, default $1.50 like the original); a daily edit limit (default 60) applies.

API (engine v2): `GET /users/{u}/videos/{v}/plan` (beats, signed media URLs, photo candidates, preview/final URLs) and
`POST /users/{u}/videos/{v}/edits` `{base_rev, ops[], mode: preview|final}` (empty `ops` re-renders the current revision, e.g. to publish an
approved preview). Both are Cognito-authorised with ownership checks; the POST body is also validated at API Gateway.

UI (`/edit/index.html?id=…`, linked from Generations for editable videos): scene list (reorder, add, delete), a preview player
(Preview / Published tabs), and an inspector with narration (word count, spoken-time estimate), scene type, a form per scene type
(diagrams, charts and timelines are edited as simple text lines), chapter titles, and a photo picker showing the candidates. The UI edits a
**local working copy** and submits `diff(server, local)`; problems are shown next to the field before anything is sent, and editing is locked
while a render runs. 9 unit tests cover the diff (replayed with the server's own semantics), the text formats and validation, and a headless-browser
run against a mocked API checked validation, the submitted operations, the rendering lock and revision polling.

## Cost model (10-minute video, ~1,500 words, ~45 beats, ~8 photos)

| Item | Estimate | Basis |
|---|---|---|
| Planning (Sonnet-class, ~3k in / ~6k out) | $0.08–0.12 | list token prices, **not verified** against your Bedrock bill |
| Narration (~9,000 chars) | $0.14–0.16 | Gemini/OpenAI TTS list prices as reported by secondary sources, **verify** |
| Photos (search free; LLM review of ~6 thumbnails per photo scene, ~8 scenes) | $0.02–0.04 | Haiku-class vision pricing, **not verified** |
| Render Lambdas | $0.05–0.12 | measured ~1.8 compute-seconds per video-second on 4 busy cores × 3 GB × 600 s; Lambda vCPUs differ, so **run `engine_selftest`** |
| Audio, stitch, S3, Step Functions (~75 transitions) | ~$0.02 | |
| **Total** | **≈ $0.30–0.50** | an edit costs only the changed beats' TTS/photo review plus re-rendered chunks (typically a few cents) |

`costs.py` records the running cost on the video item and fails the job past `MAX_VIDEO_COST_USD` (default $1.50), refunding the quota.
Draft mode (540p, no supersampling, `draft: true` on a chunk) is ~2x cheaper/faster for previews and edits.

## Deploy and verify

```bash
cd backend
pip install -r requirements-dev.txt && pytest                  # 53 tests (needs ffmpeg/ffprobe on PATH)
./layers/build_layer.sh                                         # linux/x86_64 layers, no Docker needed
aws ssm put-parameter --name /videomk/gemini_api_key --type SecureString --value '…' --region us-west-2
aws ssm put-parameter --name /videomk/unsplash_access_key --type SecureString --value '…' --region us-west-2   # optional
#   (v1 reads /videomk/openai_api_key and falls back to the old Secrets Manager secret)

cdk deploy                                                      # v1 (default). Adds the Usage table; see "Breaking changes"
cdk deploy -c engine=v2 -c ttsProvider=gemini                   # enables v2 and points the launcher at it

aws lambda invoke --function-name engine_selftest --region us-west-2 /dev/stdout
```

`engine_selftest` is the first thing to run: it reports Python/numpy/Pillow versions, the bundled ffmpeg version, whether
`libx264`, `aac`, `sidechaincompress` and `amix normalize` exist, `/tmp` space, and **ms per frame on the real runtime**.
Use that number to set memory (`make_fn(memory=…)`), chunk size (`CHUNK_SECONDS`) and `-c renderConcurrency`.

Context flags: `engine`, `reviewModelId`, `unsplashAppName`, `editDailyLimit`, `ttsProvider`, `ttsVoice`, `planModelId`, `maxVideoCostUsd`, `defaultMinutes`, `renderConcurrency`,
`dailyVideoLimit`, `httpUserAgent` (Wikimedia/Openverse ask clients to identify themselves: set a contact string).

**Quotas to check before a real run:** Lambda concurrent executions (new accounts can start very low; a 20-chunk render needs 20),
Bedrock model access for `PLAN_MODEL_ID` (Claude Sonnet 5.5 by default) and `REVIEW_MODEL_ID` (Claude Haiku 5.5 by default). There is deliberately no automatic fallback model: a silent downgrade once hid a broken primary (set `PLAN_FALLBACK_MODEL_IDS` to opt in).

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
| Every handler end to end on moto S3/DynamoDB (53 tests), CDK synth for v1 and v2, IAM scoping | Bedrock (incl. image input for the photo review), Gemini, OpenAI TTS, Wikipedia, Openverse and **Unsplash**: written to the documented shapes, tested against fakes only |
| Unsplash's own terms (unreachable from the sandbox): compliance for baked-into-video use is an open question above |
| The editor against the real API (signed URLs, S3 permissions such as `ListBucket` for cache lookups), and on phones |
| Launcher auth/validation/quota/idempotency, REJECTED path, cost cap, SSRF guard | Step Functions execution semantics (data flow was traced by hand, not run) |
| Editor: edit ops, revisions/locking, cache reuse after edits, preview→publish, failure containment (62 backend tests); editor UI in a headless browser against a mocked API; 9 frontend unit tests |
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
3. **Editor v2:** drag-and-drop reordering, per-beat audio preview, a visual (not text) diagram editor, undo/redo and a local draft that survives a reload, comments/sharing for reviewers, restoring an older revision.
4. **TTS bake-off:** blind-test Kokoro / Qwen3-TTS / Gemini / OpenAI / ElevenLabs on 3 scripts (~$5) and pick the default; forced alignment (whisper.cpp) for word-accurate karaoke.
5. **Packaging:** thumbnail, title options, YouTube upload via the Data API.
6. **Alternative renderer:** if you need richer motion graphics (SVG/CSS/D3/KaTeX), Remotion Lambda is the drop-in swap behind `render_chunk` (check its licence for your team size).
