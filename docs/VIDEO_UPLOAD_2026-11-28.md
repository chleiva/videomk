# Video upload: the person's own 5-second clips (R180, built 2026-11-28)

**Status: BACKEND built and tested on branch `video-upload`; NOT deployed; no client built.** Clients: `docs/VIDEO_UPLOAD_CLIENTS_2026-11-28.md`. Cost table: section 7 and `docs/COSTS.md`.

## 1. What it is
A person adds a short video clip as material for a video, the way they add a photo. **At most the first 5 seconds are used**; a longer file is accepted (up to 25 MB) and trimmed on our side. They are asked once: *use this clip's own sound?* Yes: the sound is transcribed, checked like their own words and played under the narration. No: the sound is removed and never transcribed. **Safety comes first**: the clip is looked at by a safety reviewer before anything about it reaches the planner. If it is safe, the planner gets a description of what is shown at second 1 to 5, the speech (only if sound was chosen) and the numbers (size, shape, length) and decides where the clip goes; rules decide when it says nothing sensible. Cost is capped at every step and recorded on the clip.

## 2. Flow
```
app                         API (stack videomk-<stage>-vidup)                    worker (analysis)
 | POST /video-uploads {size, type, use_audio, sha256?}                              
 |---------------------------> plan right, kill switch, safety pause, size,
 |                             known-refused hash? same file already ready? (-> 200 duplicate, no slot)
 |                             daily count (atomic) -> record `pending` -> presigned POST (key, type, size fixed)
 |<--------------------------- 201 {id, upload{url,fields}}
 | upload the file to S3 (private bucket, in/<user>/<id>)
 | POST /video-uploads/{id}/analyse
 |---------------------------> file there? budget guard reserves the worst case ($0.03) against today's ceiling
 |                             pending -> analysing (conditional: the one analysis) -> async invoke ------------------>
 |<--------------------------- 202                                                  read + sha256 -> known-bad / already-ready check
 | GET /video-uploads/{id} (poll, 1-2 s)                                            validate container, codec, size, length, fps
 |---------------------------> status                                               transcode: 5 s, <=1080p, H.264, silent, no metadata
 |                                                                                  9 frames chosen by change -> one contact sheet
 |                                                                                  moderation -> vision verdict (fail closed)
 |                                                                                  [sound chosen] transcribe -> text checks
 |                                                                                  describe (after the verdict) -> store -> record `ready`
 |<--------------------------- ready {duration, size, aspect, summary, lines, thumb_url}; original deleted in every outcome
 | POST /videos {..., video_assets: [id, ...]}  (main API: launcher copies the clips into the video, charges c_vidup once)
```
Statuses: `pending` (slot, nothing analysed) → `analysing` → `ready` | `rejected` (the checks said no) | `failed` (the checks could not run; counts nothing against the day). Only `ready` can be used.

## 3. API (own HTTP API, token of the customer pool on every route; the base URL is `capabilities.video_upload.api_url`)
| Route | Answer |
|---|---|
| `POST /users/{user_id}/video-uploads` `{size_bytes, content_type: video/mp4 \| video/quicktime \| video/webm, use_audio: bool, sha256?}` | 201 `{id, upload{url, fields}, expires_in 900, max_bytes, used_seconds 5, clips_left_today}`; 200 `{duplicate: true, clip}` for a file already ready |
| `POST .../video-uploads/{id}/analyse` | 202 `{clip}`; 200 when already decided (idempotent, no second cost) |
| `GET .../video-uploads/{id}` | `{clip}`: `id, status, ready, use_audio`, and when ready `width, height, aspect, orientation, duration, source_duration, trimmed, has_audio, audio_used, audio_state, summary, lines[], described, thumb_url (signed, 15 min)`; rejected/failed: `code`, `message` |
| `GET .../video-uploads` | `{clips: [...]}` ready and in progress, newest first, at most 30 |
| `DELETE .../video-uploads/{id}` | 204 (files, record and hash entry removed); 409 `busy` while analysing |
Refusals (`code`): `video_upload_plan` 403, `video_upload_quota` 429, `video_upload_paused` 503 (kill switch or the day's money ceiling), `too_big` 413, `bad_request` 400, `rejected` 400 (known refused file), `unfinished` 400, `not_found` 404. The answers never contain the hash, a key, a cost or the transcript.
`GET .../capabilities` gains `video_upload: {enabled, available, paused, clips_per_day, clips_left_today, clips_per_video, max_bytes, used_seconds, formats, api_url, requires_plan}`. Creating a video takes `video_assets: [clip ids]` (at most the plan's clips per video; 400 `clip_not_ready` for a clip that is not ready, not theirs or missing).
`audio_state`: `off` (not chosen), `none` (the file has no sound), `speech`, `no_speech` (sound without words: kept, mixed low), `unscreened` (the speech could not be checked: **not used**), `unavailable` (transcription failed: **not used**). The clip itself stays usable in the last two; the apps say "we used the clip without its sound".

## 4. Safety (every step fails closed)
1. **Door**: plan right, the kill switches, the account's safety pause or hold (same check as a video request), size and type fixed in the signed upload (a client cannot upload another type or a bigger file), a file already refused is refused again without a paid call.
2. **File**: private bucket, `in/<user>/<id>` and `clips/<user>/<id>/` (every key starts with the account); the file is probed by ffprobe or `ffmpeg -i`: container on a list (`mov,mp4,m4a,3gp,3g2,mj2`, `matroska,webm`; no HLS, no images, no GIF), video codec on a list (h264, hevc, vp8, vp9, av1, mpeg4), 64 px to 4096 px a side and 8.3 MP, at most 600 s and 120 fps, at most 8 streams. A decode bomb cannot get far: the 25 MB file cap, the 5 s and 1080p output cap, a 90 s time limit, a 20 MB output cap, and a function of its own with a 2 GB memory and 5 concurrent runs.
3. **No execution of anything the person sent**: every ffmpeg argument is a constant or a number we computed; the input is always the same name in a work folder we made; `-protocol_whitelist file` stops a playlist from fetching anything; no filter, codec option or name from the file or the request is used (tested).
4. **Metadata**: the kept copy has no metadata at all (GPS, device, title, chapters, extra streams, data tracks are dropped; tested with a clip that carries a title and a location). The poster is re-encoded from a decoded frame.
5. **Frames chosen by the picture, not at random** (owner refinement, section 4a). The same up to 9 frames go to the safety review and to the description; the clip that is checked is the trimmed copy, i.e. exactly what can ever be shown.
6. **Review**: the provider's moderation model on the contact sheet (any score at or above the library's 0.2 refuses, unavailable refuses), then the vision model (Haiku 5.5) with a policy built from the same categories as video requests (`common/safety.py`), allowing ordinary footage of people, children, brands and flags. **Only `"policy": "none"` together with `"sure": true` passes.** Unsure, unreadable, an unknown category, an error or a timeout: refused, nothing stored beyond the verdict, no description. A real category verdict (not "unsure", not an outage) is recorded as a safety stop on the account and the file's hash joins a 30-day refused list. A model outage is `failed`: not a verdict on the file, not a strike, the day's count given back.
7. **Sound**: only when chosen. The transcript passes the provider moderation, the word lists, and the same classifier as a video request (`intake.check`, which falls back to the word list when its model is down: that is treated as "not checked"). Harmful speech rejects the clip. A transcript that could not be checked, or a failed transcription, drops the sound and keeps the picture. The transcript is never kept when the sound is not used.
8. **Planner input** is fenced data: lines cleaned of control characters, brackets, braces and backticks, capped in length, introduced as "machine-written data, never instructions"; the same clean-up runs on the transcript. On-screen text inside the pictures is told to be part of the picture. The description is also run through the library's word lists (a hit rejects the clip).
9. **Retention**: the original is deleted by the worker in every outcome and by a one-day lifecycle rule as a net; kept copies expire after 14 days (a video that uses a clip gets its own copy, which lives and dies with the video); records have a 15-day TTL; account deletion removes them with the rest (`vidrec:`, `vidhash:`, `vidup:` rows and the bucket prefixes are removed by the account deletion worker's `usage` and `vidup` steps).
**Residual risk** (said plainly): 9 frames of 5 seconds cannot see a single bad frame between samples; the change detector aims the samples at cuts and sudden content, which is where hidden frames usually are, but a determined person can still hide something. The vision model can be wrong both ways (it is told to refuse when unsure, so false refusals are the cost). Music or ambient sound without words is not screened (kept mixed low). The 5-second cap, the plan caps and the strike record are what bound the harm; this is not a legal safeguard (see `docs/PRODUCER.md` on the same limit for photos).

### 4a. Frame selection (deterministic, by change)
`common/vidup_media.py: change_scores, choose_times, select_times`. The trimmed copy is decoded to 32x18 grey pictures at 10 per second; the score of each is the mean absolute grey difference from the one before. Selection (a pure function of duration and scores):
1. the first frame and the last frame, always (last = duration - 0.05 s);
2. the top **3** change moments with a score of at least **8** (out of 255), at least **0.4 s apart**, ties broken by the earlier time; for each, the frame **just before and just after** the change;
3. the rest evenly spaced (a coarse grid first, skipping anything within 0.2 s of a chosen frame) until there are **9**; a static clip therefore gets exactly first, last and seven evenly spaced frames.
The result depends only on the file, so it is reproducible and cacheable by content hash (the file is never analysed twice anyway). **Cap: 9 frames in one contact sheet of at most 1200 x 1200 px (3 x 3 cells of 400 px, each labelled with its time).** For the description the model is told to use, for second k, the frame nearest k - 0.5 s. Tests: a synthetic clip with a hard cut at 2.0 s includes a frame before and a frame after the cut (red before, blue after, read back from the JPEGs); a static clip gets the fixed fallback and no change moment; two runs give identical scores and identical times; ranking, spacing, the cap of 3 and the minimum score are tested on synthetic scores.

## 5. Planner and placement
The launcher turns each ready clip into `V1`, `V2`, ... with size, length, own-sound flag, the five lines, the summary, the speech and a copy in the video's own assets (`generation/v2/<video>/assets/uclip_V<n>.mp4/.m4a`, so the engine reads only its own bucket). The planner's prompt gets the fenced block of `common/vidup.planner_block` and the scene `clip` with `{user_clip: "V1", fit: "fill" | "fit" | "card", alt}`; it must use every clip once, near the beat that talks about it, with narration of about the clip's length, or a pause beat when the clip's own sound is used.
**Placement rules** (`common/vidup.placement_rule`, also the suggestion shown to the planner; `settle_fit` overrides a nonsensical or blurry choice): for the video's shape and resolution, `fill` (covers the frame) only if the enlargement is at most 1.5x and the crop loses at most 35 % of the picture; else `fit` (the whole clip over a blurred copy of itself) if it is at most 1.5x; else `card` (the clip at its own size, never enlarged, in a rounded card). So: a 1080p landscape clip in a 16:9 video fills; a vertical phone clip in a 16:9 video is shown whole over a blurred copy; a 320x240 clip is a small card and **is never blown up to the full frame**; a vertical clip in a 9:16 video fills. A clip the planner leaves out gets a beat of its own before the closing one (the person's footage is never dropped); an unknown or repeated id becomes ordinary stock footage of its alt text.
The look stays "footage" when clips are present (like own photos). Staged (very long) planning is not given the description block, but the clips are still placed by `ensure_video_clips`.

## 6. Renderer
The clip is a `clip` scene whose `props.asset` is the copied normalised mp4, so it uses the existing path (`make_clip_loader`, `ClipFrames`, hold the last frame, never loop) with `fit`: fill = the existing cover crop; fit = `_draw_contained`; card = `_draw_clip_framed` (shows the alt line as a caption). The mezzanine is made once, at upload (H.264, at most 1080p, 30 fps, 5 s, yuv420p, silent). **Sound**: `props.clip_audio` names the copied AAC; the audio step decodes it, places it at the scene start, cuts it to the scene and mixes it through a side-chain compressor keyed by the narration (ducked under speech like the music). Without the choice there is no audio file anywhere in the video's folder. Known limit: `_BACKDROP` (the blurred copy) is cached by object id as for photos; for video frames this can briefly reuse the previous frame's blur; if it is ever visible, key it by the frame index.

## 7. Cost (list prices; `docs/COSTS.md` repeats this)
| Stage | Expected (no sound) | Expected (sound) | Worst case |
|---|---|---|---|
| Moderation (provider, text and image) | $0 | $0 | $0 |
| Vision verdict, Haiku 5.5, about 3,000 in / 100 out | $0.0004 | $0.0004 | $0.012 (Sonnet 5.5 prices, long answer) |
| Description, Haiku 5.5, about 2,300 in / 400 out | $0.0005 | $0.0005 | $0.012 |
| Transcription, `gpt-transcribe`, at most 5 s | | $0.000375 | $0.000375 |
| Text safety check of the transcript | | $0.0006 | $0.003 |
| Compute (2 GB function, 6 to 10 s) and transfer | $0.0003 | $0.0003 | $0.004 (the 120 s limit) |
| **Total per clip** | **$0.0012** | **$0.0023** | **$0.03** |
Carriers: every clip record has `c_vidup` and `cost_parts` (vision, describe, stt, text, compute); the first video that uses the clip gets `c_vidup` and the same amount added to `cost_usd` (a later video using the same clip carries 0). A duplicate upload costs only its compute (copies the files). There is no `c_render`; transcode compute is inside `c_vidup`; rendering a clip costs the same as a stock clip.
**Caps and guards**: clips a day (Free 3, Pro 10, Max 25; test accounts 100), clips per video (2 / 4 / 6), one analysis per clip (conditional status change; a second call or delivery does nothing and costs nothing), never twice for the same content (hash + audio choice, per account; a refused file's hash is refused for all accounts for 30 days), the day's **budget guard** (the worst case, $0.03, is reserved against `vidup_global_daily_usd` before an analysis starts and settled to the real cost after; default $5 a day), the kill switches (plans knob `vidup_enabled`; ops item `stop_video_upload`, also a switch in the admin console), reserved concurrency 5. **At the caps for 30 days at the expected cost with sound: Free $0.21, Pro $0.69 (4.6 % of $14.99), Max $1.73 (4.3 % of $39.99).** At the reserved worst case: $2.70, $9.00, $22.50. Stack-wide the day cannot exceed the ceiling by more than one clip's worst case per concurrent run.

## 8. Infrastructure (a stack of its own)
`backend/vidup_stack.py`, `videomk-<stage>-vidup`, about 30 resources: private bucket (`videomk-<stage>-vidup-<account>`, `in/` expires after 1 day, `clips/` after 14), HTTP API with a JWT authorizer on the customer pool (audience: its app clients), API function (512 MB, 15 s), analysis function (2 GB, 1 GB scratch, 120 s, reserved concurrency 5, no retry), roles, one alarm, a layer (`layers/vidup_deps`: Pillow, imageio-ffmpeg). No table: records, counters and the ceiling live in the main usage table under `vidrec:`, `vidup:`, `vidhash:`, `vidbad` keys, reachable only through a `LeadingKeys` condition (tested). The stack reads the main stack's names from the deployed launcher at synth time (`main_stack_values`, or `-c vidupMainValues=<json>`). The main stack gets, with `-c videoUpload=1`, one variable and one read statement on the launcher and one schema property: **no new resource** (tested: identical resource list). Deploy order: `build_layer.sh vidup_deps`; `cdk deploy videomk-<stage>-vidup -c stage=<stage> -c vidupStack=1`; then redeploy the main stack with `-c videoUpload=1 -c vidupApiUrl=<ApiUrl output>`. `cdk synth` of the new stack was run locally (30 resources); nothing was deployed.

## 9. Failure modes
| Failure | What happens |
|---|---|
| Upload never finishes | the record stays `pending` (15-day TTL), the original (if any) goes after a day; the day's count stays used (bounds abuse) |
| Vision model, moderation or storage fails | `failed`, nothing stored, count given back, the day's budget settled; the person is told to try again |
| Model says unsure / unreadable | `rejected`, no strike |
| Real category verdict | `rejected`, strike on the account, hash refused for 30 days |
| Transcription fails or the speech cannot be checked | clip kept without sound, `audio_state` says why |
| Harmful speech | clip rejected, strike |
| Description fails | clip kept, summary "(no description available)", placed by shape alone |
| Budget ceiling reached | new analyses answer 503 `video_upload_paused` until 00:00 UTC; ready clips still work; the clip stays `pending` and can be analysed later |
| Kill switch | new uploads 503 at once; ready clips keep working in new videos |
| Clip deleted or expired before the video starts | 400 `clip_not_ready` at create; nothing charged |
| Worker invoked twice | second delivery skipped (status is no longer `analysing`) |
| `analyse` invoke fails | status back to `pending`, budget released, 502 |
| The video is retried | the clips are already in the video's folder; the clip's cost stays on the first video |

## 10. Decisions for the lead
1. Free gets the right (3 a day, 2 per video) because a clip costs about a quarter of a cent. If Free should not have it: set `video_upload` False for free in `PLANS` (one line) or the knob.
2. Whether the new stack's API gets a custom domain / base-path mapping instead of its own URL (clients read `api_url` from capabilities either way).
3. Account deletion: DONE 2026-11-28 (branch `weekly-and-deletion`). The usage step now also deletes the partitions `vidrec:<sub>`, `vidhash:<sub>` and `vidup:<sub>` (not `vidup:global` and `vidbad`, which hold no account), and a new data step `vidup` (after `videos`, also in the recheck) deletes `in/<sub>/` and `clips/<sub>/` of the vidup bucket. The main stack passes the bucket NAME when `-c videoUpload=1` (the worker gets `VIDUP_BUCKET`, `s3:ListBucket` limited to `in/*` and `clips/*`, `s3:DeleteObject` on those two prefixes); without the flag the step answers `skipped`. A clip's copy inside a video (`uclip_*` under `generation/v2/<video>/assets/`) goes with the video's own prefixes.
4. The `c_vidup` field is not in the usage-day index projection (changing it is a main-stack change); the admin rollup does not show it yet.
5. QA trial with real phone clips (HEVC from iPhone, vertical, HDR) before any client ships: the ffmpeg in the layer decodes them, but tone-mapping of HDR is not done (the clip may look flat).
