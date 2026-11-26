# Stock video clips (2026-11-24)

The planner can use short real footage behind the narration: a `clip` scene `{clip_query, alt}`. Since 2026-11-26 (owner feedback: a competitor used far more video clips) VISUAL
topics (places, nature, animals, science processes, history, food, travel, how things work, people at work) aim at **30 to 45 percent of the beats as clips**, each with short
narration (10 to 18 words, at most 20; a clip beat longer than 36 words becomes a photo in `validate_plan`), worded generically. Named people, places, brands, facts, numbers,
lists and abstract ideas stay with images, diagrams and charts; `allow_clips=false` (current events) still removes clips.
`CLIPS_ENABLED=0` (Lambda env) removes clips from the planner's menu.

## Flow
1. **Plan**: the director writes `clip` scenes like any other scene (sanitised; an empty one becomes a plain card).
2. **Beat step** (`engine/clips.py`, `beat_handler.make_clip`): search **Pexels** (only when `/videomk/pexels_api_key` exists in SSM), **Pixabay** (only when
   `/videomk/pixabay_api_key` exists; videos are cached 24 h as its terms require, 100 requests/60 s per key) and **Wikimedia Commons** (keyless), keep landscape footage of 3 s or more with an allowed licence, show the poster frames to the small vision model (same reviewer as photos, with a
   footage-editor prompt: no logos, no private people, must match), download the winner (≤ 70 MB, SSRF-safe fetch), and **normalise** it with ffmpeg: trimmed to the
   length the scene needs (a short clip loops inside its scene), cropped to 16:9, 1280x720, 30 fps, no audio, H.264 (about 1 MB per 10 s). Stored as
   `generation/v2/<video>/assets/clip_<beat>_<hash>.mp4` with the `retention=working` tag (expires after 7 days; the editor re-renders from it until then).
2b. **Verification**: the clip is then checked on one frame per 30 s of the footage actually used (one call, at most 3 frames; `CLIP_VERIFY=0` disables it); a failing clip is skipped for the next candidate.
3. **Fallbacks, so there is never a hole**: reviewer rejects everything / nothing found / download or decode fails (3 tries) → a still photo of the same subject
   (Unsplash/Openverse path) → a title card.
4. **Render** (chunk Lambda): the clip is decoded once per chunk to JPEG frames in memory and drawn like a photo scene (slow push-in, bottom scrim for captions,
   credit top-right). An outgoing clip holds its last frame during the crossfade. Measured on Lambda: ~190 ms per frame (a 1-minute video renders in parallel
   30-second chunks, about 3 minutes each at worst; chunk timeout is 10 minutes).
5. **Credits**: on-screen "Video: Name / Pexels" or "Video: Name (CC0)"; the description lists "Video by Name on Pexels (link)" or "Video by Name (CC0) via Wikimedia Commons (link)".

## Licensing (what the providers' own terms say)
- **Pexels** ("All photos and videos on Pexels are free to use", commercial use allowed, attribution not required; the API asks for a prominent link to Pexels and
  credit to the creator "when possible", which we give). Not allowed: selling unaltered copies, implying endorsement, recognisable people shown in a bad light,
  using content for machine-learning training, copying Pexels' core functionality. Our use (clips combined with narration and captions into a new video) is the intended
  pattern; we never serve the clips as a library. Default limit 200 requests/hour and 20,000/month: ask Pexels for a lift with a demo showing attribution before launch.
  **New API keys were reported paused when this was written.**
- **Pixabay** (Pixabay Content License: free for commercial use, attribution not required; the API asks to show where videos come from, done on screen and in the description; permanent hotlinking is not allowed, so videos are downloaded as working copies).
- **Wikimedia Commons**: only per-file CC0, public domain and plain CC BY (no -SA/-ND/-NC), the same bar as Openverse photos. Author and licence come from the file's own metadata.
- Not a licence matter but worth knowing: Pexels content showing logos or trademarks cannot be used commercially for goods and services; the reviewer rejects visible logos.

## Operating notes
- **Commons throttles clients without contact details in the User-Agent (HTTP 429 on downloads).** Set `-c httpUserAgent="videomk/1.0 (<a contact URL or email you are happy to publish>)"` at deploy
  (`deploy.sh`), which every outbound fetch uses. Without it clips fall back to stills on Commons-only deployments. Search itself works without.
- Pexels needs a key in SSM: `aws ssm put-parameter --name /videomk/pexels_api_key --type SecureString --value ...` (the beat Lambda already may read `/videomk/*_api_key`).
- The selftest Lambda (`engine_selftest`) now proves the whole clip path on the Lambda runtime (decoders h264/vp8/vp9/theora present, normalise, decode, render).
- Not built: choosing a clip in the editor (the editor lists clip beats and can change their narration; changing the clip needs a new `clip_query`), clips of the user's own phone videos,
  a second keyless provider (Internet Archive public-domain footage would be the next one), per-clip start offsets.


## Why clips fell back to photos in real use, and what changed (2026-11-24)
Measured since clips went live: 9 of 24 videos had a clip scene; of 10 clip scenes 6 got a real clip (all Pixabay), 4 fell back to a photo. Causes in the beat logs: Wikimedia downloads refused with HTTP 429 (8, no contact in the User-Agent), the reviewer rejecting every candidate (5), the verifier rejecting footage that did not fit a very specific narration (5), and the planner picking clips for news beats (an attack in Yemen) where generic footage can only mislead.
Changes: Commons is skipped unless the User-Agent carries contact details (`CLIPS_COMMONS=1/0` overrides), so Pixabay gets all the review slots (now 8 candidates); the planner's second wording (`alt`) is searched when the first finds nothing; current-events videos (web research) get photographs instead of clip scenes; when the brief asks for video or footage the planner uses clips freely (up to 1 beat in 3, worded generically); and the reviewer and verifier now reject footage that contradicts the narration or misses the intended subject, but accept a fair generic fit (footage is atmosphere, not an illustration of every detail).
Trade-off to know: a generic fit can be the wrong place (a canal at dusk under a Tiber video). Making the reviewers stricter brings back the fallbacks to photos; the prompts are `CLIP_REVIEW_SYSTEM` and `CLIP_VERIFY_SYSTEM`.

## Visual accuracy and no looping (owner, 2026-11-25)
Owner: odd clips appeared, and short clips visibly looped ("very bad"). Rules now: **a wrong clip is worse than none** (the beat gets a still photo instead).
* **Check on the footage we really show**: after the poster-frame review picks a clip, 3 frames (near the start, middle and end of the used footage) go to the vision model, which scores 0-10 how clearly the footage SHOWS the intended subject and flags text/logos/people/wrong landmark; a clip is used only with `ok` and score >= 7 (`VERIFY_MIN_SCORE`). The check **fails closed**: if it cannot run or be read, the clip is discarded. Up to 3 candidates are tried, then the photo fallback. The review prompt was tightened the same way (choose 0 unless an image clearly shows the subject).
* **Played once, never looped**: `-stream_loop` is gone; footage shorter than 75% of the scene (`MIN_FILL`) is not offered at all, and when a used clip is a little shorter than its scene the renderer holds its last frame (`ClipFrames.frame` clamps).
Trade-off: fewer clips, more photos, a little more cost per clip (3 frames instead of 1). `CLIP_VERIFY=0` switches the check off (tests only).


## More clips (2026-11-26): sources, supply, demand
Why only 6% of beats were clips (43 QA videos): the planner asked for clips only on request, Pexels has no key, Commons is skipped without a contact in the User-Agent, and
the strict checks (verify score >= 7, no looping) discard weak or short footage. The checks stay exactly as they are; supply and demand changed.

### What changed
* **NASA Image and Video Library** is a new keyless provider (`clips.nasa_search`, `CLIPS_NASA=0` switches it off). Credit "Video: NASA"; the ledger entry carries source `nasa`.
* **Several wordings per scene**: `scout_clip` searches the planner's `clip_query`, its `alt` and a shortened form (first two words), up to 3, and pools their results round-robin without duplicates
  (`query_variants`, `merge_pools`). The pool is 12 candidates (was 8); too-short footage is dropped BEFORE the cap. The old second `scout_clip` call for `alt` in `beat_handler.make_clip` is gone (it re-ran a whole review).
* **Planner**: clip share target and short clip beats (`plan.CLIP_DOC`, `images_rule(..., clips=True)`, `MAX_CLIP_NARRATION_WORDS`).
* `backend/scripts/clip_supply.py` measures all of this (read-only, QA account only).

### Measured supply (`clip_supply.py`, 25 planner-style queries, English and Spanish, 2026-11-26, QA, Pixabay key from SSM)
| source | candidates / query | >= 5 s and >= 1080p / query | queries with >= 1 usable | median duration | orientation |
|---|---|---|---|---|---|
| Pixabay | 11.2 | 10.8 | 25 of 25 | 18 s | all landscape |
| Wikimedia Commons (search only; downloads need a contact UA) | 5.4 | 3.0 | 17 of 25 | 235 s (long originals) | all landscape |
| NASA (4 per query cap) | 0.6 | 0.5 | 4 of 25 | 158 s | all landscape |
| Pexels | 0 (no key) | 0 | 0 | - | - |
| Internet Archive (CC0/PDM only, <= 70 MB, evaluation only, not a provider) | 0.2 | - | 3 of 25 | - | - |
NASA is a science/space source: it answers almost nothing for food, cities or business, and a lot for earth science, space, weather and climate. Internet Archive CC0/PDM videos are overwhelmingly long user uploads (hundreds of MB), so it was not built.

Pass rate through the real review (12 poster frames) and verify (3 frames, score >= 7) at 5 s scenes, same 12 queries before and after: **7 of 12 (58%) before, 9 of 12 (75%) after**; on all 25 queries after: **19 of 25 (76%)**
(18 Pixabay, 1 Commons; 2 rejected by the poster review, 4 had every candidate fail the verify). Failures were honest ones: coffee harvest on a farm, solar panels, rocket launch (visible logos/text), misty forest in Spanish.
Model cost measured from token counts: **$0.0007 per clip scene** (2.3 Haiku-class vision calls on average: 1 review of 12 posters plus 1 to 3 verifies; about 2,000 input tokens per call).
A 3-minute video with about 7 clip scenes therefore costs about $0.005 for clips; the wider pool adds roughly $0.0001-0.0002 per scene. Search APIs are free.
Planner before/after on 12 audit prompts (`docs/audit/prompts.json` ids sci-03 kid-01 tra-01 tra-03 rec-01 rec-02 his-01 his-02 tri-03 how-01 sci-02 tri-01, real Sonnet plans through `director.direct`): **clip share 12% of beats before (21 of 173) and 25% after (43 of 175)**; clip beats still average 27 words of narration (the model keeps clip narration near its normal beat length), so the 36-word guard is what stops long ones. The 30 to 45 percent target is NOT reached by prompt alone. With the measured pass rate, about 7% of beats (12% x 58%) ended as verified clips before and about 19% (25% x 76%) after.

### Source evaluation (terms read 2026-11-26; quotes are from the source's own page)
| source | licence evidence | API / limits | attribution | verdict |
|---|---|---|---|---|
| Pixabay | Content License: "You cannot sell or distribute Content ... on a Standalone basis", trademarks/logos not usable commercially (https://pixabay.com/service/license-summary/); API: 100 requests per 60 s, responses cached 24 h, no permanent hotlinking (https://pixabay.com/api/docs/) | key (exists) | requested: show where videos come from (done) | in use |
| NASA | "NASA content generally are not subject to copyright in the United States"; "NASA should be acknowledged as the source"; commercial material "must not explicitly or implicitly convey NASA's endorsement"; "clearances may be necessary for images that include any NASA logos or NASA employees" (https://www.nasa.gov/nasa-brand-center/images-and-media/); third-party material occasionally appears and needs its own clearance | keyless, https://images-api.nasa.gov/search, no published limit found (unverified) | credit "Video: NASA" | built; owner to accept the wording and the third-party/people caveat |
| Wikimedia Commons | per-file CC0/PD/CC BY only, filter exists | keyless; downloads need a contact User-Agent | credit line carries author and licence | in use (prod: waiting on the contact string) |
| Pexels | "All photos and videos on Pexels can be downloaded and used for free"; "Don't sell unaltered copies"; "Don't imply endorsement" (https://www.pexels.com/license/) | key required; **new keys are paused**: "New API key issuance is currently paused and cannot be requested" (https://www.pexels.com/api/); higher limits are free with acceptable attribution | "Always credit our photographers when possible" (we do) | code path ready, no key |
| Coverr | "Everything Coverr publishes is free for commercial and personal projects"; no AI training; partner items (Shutterstock, iStock, PremiumBeat) not covered (https://coverr.co/license) | REST API (https://api.coverr.co/docs/); Demo key needs signup; a Demo key requires credit to Coverr and the creator with links, and a download-tracking ping; premium/original files need a Production key | required on Demo keys | NOT built: needs an owner signup, video lists need extra signed-URL calls, small library (unverified size); revisit after a key exists |
| Mixkit | licence text sits behind a modal ("Stock Video Free License") that could not be read from the page (https://mixkit.co/license/) | no API found | unverified | rejected: no API, terms unreadable, scraping a site without an API is not acceptable |
| Videvo | page redirects to Freepik and returned HTTP 403 (https://www.videvo.net/stock-video-footage-license/) | no API found | unverified | rejected: terms unreadable, mixed licences |
| Internet Archive | per item `licenseurl`; only CC0/PDM would be accepted | https://archive.org/advancedsearch.php and /metadata (keyless) | none for CC0/PDM | measured, not built: 0.2 usable per query, files mostly 100s of MB |
| Library of Congress | rights vary per item; the JSON API needs no key and asks for rate limiting (https://www.loc.gov/apis/json-and-yaml/working-within-limits/) | keyless | per item | not built: per-item rights statements would need a parser; unverified |
| NOAA, USGS, ESA | NOAA and USGS terms pages returned no usable statement; the ESA terms URL tried returned 404 (ESA media is, to my knowledge, mostly CC BY-SA IGO, which our filter would exclude: unverified) | no clean video API found | - | rejected for now |

### Paid and AI options (not called, not signed up; prices from public pages, mostly third-party summaries: unverified unless marked)
| option | price | per 5 s clip | 3-minute video, 30% of the time as clips (about 54 s, 11 clips of 5 s) |
|---|---|---|---|
| Storyblocks API | free test keys, "custom pricing" for the API (https://developer.storyblocks.com) | quote only | quote only |
| Shutterstock (API) | API pricing not published; consumer HD clip about $79, 4K $179-199 | $79 (consumer) | about $870 (consumer prices, not viable) |
| Adobe Stock API | not published; plans from $29.99/month for 1 video | about $30 | not viable per video |
| Pond5 API | not published; single HD clip about $39 | about $39 | about $430 |
| Getty / iStock | not found | - | - |
| Amazon Nova Reel (Bedrock) | $0.08 per second of 720p/24 fps video per third-party sources; the AWS pricing page text did not show it; 6 s fixed length. **Not listed for the QA account in us-east-1, eu-west-1 or us-west-2** (`list-foundation-models`), and one source says it retires 2026-09-30 (unverified) | $0.48 (a 6 s clip) | about $5.3 |
| Google Veo 3.1 Fast (Gemini API) | $0.10 per second at 720p, $0.12 at 1080p; Vertex AI price not confirmed | $0.50-0.60 (4-8 s units) | about $5.5-6.6 |
| Runway API gen4_turbo | 5 credits per second at $0.01 per credit = $0.05 per second (https://docs.dev.runwayml.com/guides/pricing/) | $0.25 | about $2.75 |
Compare with $0.005 per video for stock clips. AI video also needs a visual-accuracy check (generated footage can show impossible things), a licence/terms review per vendor and an owner decision on "AI generated" disclosure. Recommendation: stock only for now; if the pass rate stays low for some topics, test Runway gen4_turbo on QA for those scenes only.

### Pexels: what the owner must do
1. Pexels currently refuses new API keys (page https://www.pexels.com/api/ says issuance is paused). Check that page; when a request form appears: sign in with a Pexels account, describe the use (educational explainer videos, credit and link to Pexels shown on screen and in the description), and submit. Whether support can grant a key while the form is paused is unverified.
2. Store it: `aws ssm put-parameter --name /videomk/pexels_api_key --type SecureString --value '<key>' --region <region>` (the beat Lambda can already read `/videomk/*_api_key`).
3. Nothing else: `pexels_search` is wired into `gather` and switches on when the parameter exists. Before launch ask Pexels for a limit lift (default 200 requests/hour and 20,000/month), which they grant free with proper attribution.

### Switches
`CLIPS_ENABLED=0` (no clips in the planner), `CLIPS_NASA=0`, `CLIPS_COMMONS=0|1`, `CLIP_VERIFY=0` (tests only).


## Clip montage (2026-11-26, second step)
Owner: get much closer to 30-45% of beats as video, with many SHORT clips, without converting named-place/person/landmark photo beats.

### What it is
A `clip` scene may carry `clip_queries: [2 to 4 generic wordings]` (the single `clip_query` stays and is the first one; a montage with one query is a plain clip). The beat step (`beat_handler.make_clip` -> `clips.scout_montage`):
1. each query is searched, reviewed (poster frames) and VERIFIED (the same strict 3-frame check, score >= 7, fails closed) on its own through `scout_clip`, against its own slice of the narration (words split evenly; word timings are not used); at most 2 run in parallel;
2. every segment is asked for footage long enough that the survivors cover the beat even if half fail (`cover / ceil(n/2) + 0.2 s`); a beat too short for the queries uses fewer clips (at least 2.5 s each: `MONTAGE_MIN_SLOT_S`);
3. a failed segment is dropped and its neighbours stretch (`plan_slots`): each can use its footage plus at most 0.5 s of held last frame, never a loop; fewer than half surviving, or footage that cannot cover the beat, returns None and the beat takes the existing photo path;
4. the survivors are assembled by ffmpeg into ONE normalised MP4 of the beat length (each trimmed to its slot, a 0.2 s dissolve between, hard cut when this ffmpeg has no `xfade`), stored as the beat's single `clip_asset`.

Because the result is an ordinary clip file, nothing downstream changed: timeline, renderer (`draw_clip`), `ClipFrames` memory (frames of one file of the beat's length, capped at 20 s like a single clip), 16:9 / 9:16 / 1:1 / 4:5, 720p/1080p (720p footage) and 4K (1080p footage, `hd`), captions and sync cues. Credits: the on-screen line joins the creators ("Video: A / Pixabay, B / NASA", cut at 90 characters); the ledger (description credits) gets ONE entry per clip (`media.ledgers`, `timeline_handler.credits_ledger`); `media.ledger` keeps the first for old readers.
Planner: `plan.sanitize_props` (2-4 distinct queries), `validate_plan` (a montage beat may carry up to 45 words, 36 for a single clip; about 6 words per clip, so 20 words keep at most 3 queries and under 12 words one clip; `allow_clips=false` still turns it into a photo), prompt (`CLIP_DOC`): beat by beat, filmable and not needing one exact named thing means clip or montage; queries must be stock-library staples, no metaphors or animations.
Editor: `set_scene` with `clip_queries` replaces a montage (the beat is remade because `needs_media` compares the whole query list), `delete` removes it, `editor_get` shows `segments` and `queries`; nothing new to refuse.

### Measured (12 audit prompts, real Sonnet plans, QA; supply is Pixabay + NASA + Commons search)
* Clip or montage share of beats: 12% (single clips only, original prompt) -> 24-27% across three runs of the final prompt (47 of 174 in the best run; 30-34 of those were montages). The prompt alone does not reach 30-45%: the director keeps photographs for beats that name things. Clip narration still averages 27-30 words.
* Survival through the strict check (real review + verify, sample of 42-47 clip/montage beats per run, two runs): singles 8 of 13 and 6 of 21; montages 13 of 34 and 11 of 21 end as a montage; only 18 of 49 planned segments survived in the second run (many beats keep one clip). About 40-45% of clip beats therefore end as video, so roughly 10-12% of ALL beats are video (before the montage work about 7%). Failures are verify rejections of creative queries (23 verify failures and 4 poster rejections in a 8-beat diagnostic); the planner is now told to ask only for stock staples.
* Cost: 186-220 vision calls for 42-47 beats = $0.050-0.062, i.e. **$0.0012-0.0013 per clip/montage beat** (a single clip was $0.0007), about 8,000-9,000 input tokens per beat for montages. A 3-minute video with 7-8 such beats adds about $0.01. Search APIs are free.
* Time: a montage beat takes a median 22-24 s in the beat step (searches, 2 workers, downloads, ffmpeg) against a few seconds for a single clip; the beat step runs beats in parallel, so a video's wall time grows by about one montage beat, not their sum. Assembly alone (3 segments, 12 s, 720p): 1.2 s.
* Render: a montage is a normal clip file, so per-frame cost is that of a clip scene: 57 ms per frame measured (1080p output, no encode), 12.0 s for an 8 s chunk including H.264 encode on this laptop, 26 MB of JPEG frames in memory for 8 s (about 3.3 MB per second; a 20 s clip about 65 MB at 720p footage; 4K videos use 1080p footage, about 2.5x). Peak RSS of the whole demo 405 MB. No change versus a single clip of the same length.
* Portrait: Pixabay returned no portrait footage for the three montage queries I tried (the provider filter keeps only tall footage for 9:16), so a vertical video's montages usually fall back to photos. Whether to accept landscape footage cropped to portrait (the renderer already crops it) is an owner decision; I did not change it.

### Not verified
* `xfade` on the Lambda's ffmpeg build (the hard-cut fallback exists and is tested); run the selftest/a QA montage after deploy.
* Per-segment credits switching on screen with each clip (the on-screen line is the joined list).
* Montage in the 4:5 and 1:1 frames beyond the shared `draw_clip` code path (portrait frame rendered and looked at; the others use the same code).
