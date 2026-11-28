# Paid speech-to-text (dictation) for paying customers: research and plan (2026-11-28)

Scope: **speech INPUT** (the person dictates the video request). It is not the "Polly only for speech" rule, which is about the voice of the videos (speech OUTPUT). Free customers keep the phone's built-in engine and the browser's; paying customers (Pro and Max) get a server-side model.

Labels: **V** = the provider's own page, read today 2026-11-28. **S** = a third party (named). **T** = measured by me today in our QA account. **CNV** = could not verify (what was tried is said). Prices are USD, list, pay as you go.

## 1. Decision

1. **Default model: OpenAI `gpt-transcribe`, batch (record, stop, upload, text), at $0.0045 per minute (V).** It is OpenAI's current recommended transcription model, accepts several language hints for code-switching (V), supports a streamed-text response for a file (V), is eligible for zero data retention and API data is not used for training (V). It is the *only* OpenAI transcription model without a shutdown date: `whisper-1`, `gpt-4o-transcribe`, `gpt-4o-mini-transcribe` and `gpt-4o-transcribe-diarize` all shut down **2027-02-26** (notice 2026-08-26) and name `gpt-transcribe` or `gpt-live-transcribe` as the replacement (V, deprecations page). **Never build on the three old ones.** (The earlier note about OpenAI text-to-speech shutting down 2027-01-06 is confirmed on the same page, and is a different product.)
2. **Feel: hybrid.** While the person talks, the phone's own engine keeps showing live words (free, instant, may be imperfect). When they press stop, the audio goes to the server and the better text replaces the preview within about 1 to 2 seconds for a 10 to 30 second dictation (T: 0.5 to 2.3 s for 10 s clips). No paid live streaming in version 1: realtime transcription (`gpt-live-transcribe`, `gpt-realtime-whisper`) is $0.017 a minute, 3.8 times dearer (V), needs a WebSocket session per user with a key or short-lived secret on the phone, and adds work for a small gain on a "tell me your idea" box where people speak 15 to 90 seconds and then review.
3. **Challenger to test when the owner provides a key: ElevenLabs Scribe v3** ($0.20 per hour batch = $0.0033 a minute, V; lowest word error rate on the Artificial Analysis index, 1.95 %, S). I had no key and did not sign up, so it is untested here; its API data-training terms are CNV. It is the sensible second provider behind a small interface (work package 1) if OpenAI's price, availability or terms change.
4. **Amazon Transcribe: comparison only, not recommended** (owner does not trust AWS). Listed in the tables for reference.
5. **Anthropic has no speech-to-text.** I read the Claude API features overview on `platform.claude.com/docs/en/build-with-claude/overview` today (V): it lists vision (images) and PDF support, and no audio or speech input of any kind. I did not read every Anthropic page (CNV that no other page mentions one), but the features overview, which is where a new input type would appear, has none. Claude therefore cannot be the dictation engine.
6. **Cost: 1 minute of speech = $0.0045, 3 minutes = $0.0135, 5 minutes = $0.0225** (section 4). That is 3 to 15 percent of a credit ($0.15 at the median). Cap it per user per day in seconds (section 6).

## 2. Evidence: the candidates

Prices per minute of audio. "Stream" = live partial words while speaking. Language counts are what each page says; none is guaranteed good on every language.

| Provider / model | Batch $/min | Stream $/min | Languages (what the page says) | Max audio | Source |
|---|---|---|---|---|---|
| **OpenAI `gpt-transcribe`** | **0.0045** | file stream=true at same price; live: `gpt-live-transcribe` 0.017 | list not given on its model page (CNV); accepts `languages` array (ISO 639-1 such as en, es, fr; some 639-3); multilingual and code-switching hints | file 25 MB; no duration limit stated | V `developers.openai.com/api/docs/pricing`, `/guides/speech-to-text`, `/models/gpt-transcribe`, `/guides/realtime-transcription` |
| OpenAI `gpt-4o-transcribe` | 0.006 | not on file endpoint | 98 languages claimed for Whisper family, accuracy varies | 25 MB | V pricing; **shuts down 2027-02-26** (V) |
| OpenAI `gpt-4o-mini-transcribe` | 0.003 | | same | 25 MB | V pricing; **shuts down 2027-02-26** (V) |
| OpenAI `whisper-1` | 0.006 | no | 98 | 25 MB | V; **shuts down 2027-02-26** (V) |
| Deepgram Nova-3 Multilingual | 0.0052 | 0.0058 (promo, was 0.0092) | 50+ listed incl. English, Spanish, French, German, Italian, Portuguese, Dutch, Korean | CNV | V `deepgram.com/pricing`, `developers.deepgram.com/docs/models-languages-overview` |
| ElevenLabs Scribe v3 | 0.0033 ($0.20 per hour) | 0.0037 ($0.22 per hour, Scribe v3 Live) | 90+; secondary language codes for mixed audio; Live "follows switches in the middle of a sentence" | 5 GB, up to 15 hours | V `elevenlabs.io/pricing/api`, `/docs/overview/capabilities/speech-to-text` |
| AssemblyAI (Universal-2 batch; multilingual realtime) | 0.0025 ($0.15 per hour) | 0.005 ($0.30 per hour, AssemblyAI-STT-3.7-Realtime) | "32" languages for the newest model, "the other 99" on Universal-2 | CNV | V `assemblyai.com/pricing` |
| Speechmatics Standard / Enhanced | 0.0075 / 0.0125 | 0.0075 / 0.0133 | 55+ | CNV | V `speechmatics.com/pricing` |
| Google Speech-to-Text v2, Chirp 3 | **CNV** (both Google pricing pages rendered no table to my reader). Artificial Analysis lists $16 per 1,000 min = 0.016 | CNV | CNV | CNV | S `artificialanalysis.ai/speech-to-text` |
| Amazon Transcribe (comparison only) | 0.006 (US East) | 0.01 | CNV | CNV | V `aws.amazon.com/transcribe/pricing/` |

### Accuracy evidence (independent, with limits stated)

Artificial Analysis STT leaderboard, read today (S, `artificialanalysis.ai/speech-to-text`), "AA-WER": lower is better. It is **mostly English** (50 % agent-talk, 25 % VoxPopuli, 25 % Earnings22 per the search summary of its methodology page; I did not read that page myself, so treat the composition as CNV) and I found **no per-language table** on it.

| Model | AA-WER | Speed factor (s audio per s) | Their price per 1,000 min |
|---|---|---|---|
| ElevenLabs Scribe v3 | 1.95 % (2nd of 73) | 55.7 | $3.33 |
| AssemblyAI Universal-3.5 Pro | 2.99 % | 104.3 | $3.50 |
| OpenAI GPT-4o Transcribe | 3.96 % | 40.2 | $6.00 |
| Whisper Large v3 (fal.ai) | 4.07 % | 120.1 | $1.15 |
| Amazon Transcribe | 4.12 % | 34.9 | $6.00 |
| Google Chirp 3 | 4.32 % | 30.4 | $16.00 |
| Speechmatics Melia | 4.87 % | 209.5 | $4.00 |
| Deepgram Nova-3 | 5.18 % | 655.7 | $4.30 |

**`gpt-transcribe` is not on the part of the table I could read** and its model page gives no WER (V: "makes a general high-accuracy claim but gives no benchmark figures"). So the claim "best" for it rests on OpenAI's recommendation plus my small test (section 3), not on an independent benchmark. Multilingual evidence: the Hugging Face Open ASR Leaderboard has a multilingual track (German, French, Italian, Spanish, Portuguese on FLEURS and CoVoST-2; S, via search result, not read in detail). Vendor-run per-language numbers (Gladia) exist but are marketing; I did not use them. **Honest summary: ElevenLabs Scribe v3 leads the English-weighted independent index; for the multilingual tracks I have no independent number that ranks the candidates, so the decision uses price, retention terms, the shutdown dates and my 5-language test.**

### Data, privacy, retention (user voice is sensitive)

| Provider | Training on your audio | Retention | Source |
|---|---|---|---|
| OpenAI `/v1/audio/transcriptions` | Not used for training unless you opt in (V: "As of March 1, 2023, data sent to the OpenAI API is not used to train or improve OpenAI models") | Abuse-monitoring retention "None", application-state retention "None"; zero data retention eligible: yes | V `developers.openai.com/api/docs/guides/your-data` |
| Deepgram | CNV default; opt out with `mip_opt_out=true` (which is zero data retention) | CNV | V `developers.deepgram.com/docs/data-privacy-compliance` (partial) |
| ElevenLabs | CNV for ElevenLabs itself; zero retention mode is "available to select enterprise customers" only | CNV | V zero-retention page |
| AssemblyAI | "Only certain files ... are used for model training"; excluded if you opt out, use EU servers or have a BAA | Batch audio deleted at 24 to 48 hours; zero retention for streaming if opted out | V `assemblyai.com/docs/faq/...` |
| Speechmatics | Never used unless you opt in to a discount | Real-time never stored; batch auto-deletes after 7 days | V pricing page |
| Google | Not by default ("By default, Cloud Speech-to-Text does not log customer audio data or transcripts"); logging is opt-in for a discount | none by default | V `docs.cloud.google.com/speech-to-text/docs/data-logging` |

OpenAI's "zero data retention eligible" needs an account agreement for formal zero retention, which I did not check (CNV); the table says no retention at the endpoint level by default. We do not store the audio ourselves either (section 5).

### Streaming, latency, code-switching, accents

- **Latency (T, our QA account to OpenAI, 10 s clips, Ogg Opus 16 kHz):** `gpt-transcribe` 0.45 to 1.5 s, `gpt-4o-transcribe` 0.95 to 2.3 s, `gpt-4o-mini-transcribe` 0.7 to 1.3 s, `whisper-1` 1.0 to 2.1 s. Scale for longer audio is not measured (CNV for a 5 minute file).
- **Code-switching:** OpenAI `gpt-transcribe` takes a `languages` array (V). My mixed English/Spanish test passed with it (3.2 % without the hint, 0 % with it, section 3). Scribe v3 and Scribe v3 Live have an explicit mid-sentence multilingual mode (V). Deepgram's code-switching list on its docs page is for `nova-3-medical` and `nova-2`, not general Nova-3 (V), so for mixed speech Deepgram is the weakest of the three.
- **Accents:** no provider publishes a per-accent number I could read. Latin American Spanish: my one clip (Polly es-US voice) was transcribed perfectly by all four OpenAI models, which proves little (a synthetic voice is clean). CNV for real accents; plan a test with real recordings (work package 10).
- **Korean (soon):** Deepgram Nova-3 lists Korean (V); Scribe 90+ languages (V); OpenAI's `gpt-transcribe` page does not list languages (CNV), so Korean must be tested before the Korean launch.

## 3. The 5-language test (T, 2026-11-28, QA account, region eu-west-1)

Clips: Amazon Polly neural voices (Polly is fine for test audio; generative voices were not accepted by my CLI call, so neural voices were used), 8.5 to 10.4 seconds each, re-encoded as Ogg Opus 16 kHz mono 24 kbps (what a phone would send). Languages: English (Matthew), Spanish es-US (Lupe), French (Lea), German (Vicki), Italian (Bianca), plus a mixed clip (English with "buenos dias amigos" and "mucho gusto"), plus English and Spanish with pink noise added. 8 files per model, 40 calls. Word error rate is case, accent and punctuation insensitive. **Caveat: synthetic, clean, 10-second clips: a smoke test, not a benchmark.** It cannot rank models separated by one or two percent.

| Clip | gpt-transcribe | gpt-4o-transcribe | gpt-4o-mini-transcribe | whisper-1 |
|---|---|---|---|---|
| English | 5.4 %* | 5.4 %* | 5.4 %* | 10.8 %* |
| Spanish | 0 % | 0 % | 0 % | 3.1 % |
| French | 0 % | 0 % | 0 % | 0 % |
| German | 0 % | 4.0 % (0 % with `language=de`) | 0 % | 4.0 % |
| Italian | 0 % | 0 % | 0 % | 0 % |
| Mixed EN/ES, auto language | 3.2 % | 0 % | 0 % | 3.2 % |
| Mixed EN/ES, with hint | 0 % (`languages=["en","es"]`) | 0 % | 0 % | not run |
| English, noisy | 5.4 %* | 5.4 %* | 5.4 %* | 10.8 %* |
| Spanish, noisy | 0 % | 0 % | 0 % | 3.1 % |

\* The English errors are not mishearings: the reference says "eight to four" and "two minute"; the models wrote "8 to 4" and "two-minute" (whisper-1: "8-4" and "2-minute"). Numerals are a formatting difference, which is fine for a video request. Read the English row as "all correct".

Findings:
- All four models were essentially correct on all five languages; `whisper-1` is the only one with small real slips (Spanish 3.1 %, German 4.0 %, "2-minute"/"8-4" formatting) and is shutting down anyway.
- `gpt-transcribe` auto-detected every language, including mixed English/Spanish (one wording slip without hints, fixed with the `languages` hint).
- **I could not get the single-language hint to work for `gpt-transcribe`** (`languages=["es"]` and `["de"]` returned `invalid_request_error: invalid_value`, probably my form encoding or the format it expects; the array with two entries worked). Work package 3 must settle the exact parameter form before shipping; auto-detect alone already passed.
- Cost of the test: about 6.7 minutes of audio in total across 40 calls, at $0.003 to $0.006 a minute: **about USD 0.03** (an estimate from audio length and list price, not read from the OpenAI usage page). Budget was $0.50.
- Not tested (no key, no sign-ups): Deepgram, ElevenLabs, Google, AssemblyAI, Speechmatics, Amazon.

## 4. Cost per minute and per video (to add to the per-video cost scheme)

A credit costs $0.15 at the median; a 1-minute video costs about $0.169 all-in (docs/PLANS_PROPOSAL_2026-11-27.md). Dictation happens *before* the video exists, and 1 to 5 minutes of speech is the owner's range for the request.

| Speech dictated | gpt-transcribe (default) | gpt-4o-mini-transcribe (cheaper, dies 2027-02-26) | Scribe v3 | Nova-3 multi | gpt-live-transcribe (live) | Transcribe (comparison) |
|---|---|---|---|---|---|---|
| 1 min | **$0.0045** | $0.0030 | $0.0033 | $0.0052 | $0.017 | $0.006 |
| 3 min | **$0.0135** | $0.0090 | $0.0100 | $0.0156 | $0.051 | $0.018 |
| 5 min | **$0.0225** | $0.0150 | $0.0167 | $0.0260 | $0.085 | $0.030 |
| 3 min as share of a $0.15 credit | 9 % | 6 % | 7 % | 10 % | 34 % | 12 % |

New cost field: **`c_stt`** next to `c_speech` in the video's cost record = seconds of paid dictation attached to that video times the model rate. If a person dictates, re-dictates twice and sends, all three recordings are charged to that video (they were all paid for). Add an "stt_seconds" figure so the rate can change later.

### Monthly scenario, 1,000 paying users
Assumptions (stated, not measured): 20 videos a month per paying user, 70 % of requests dictated by voice, so 14,000 dictations a month; a retry factor of 1.3 (people re-record) is included in the second column. Revenue assumption: average $20 a month per paying user = $20,000 (Pro $14.99, Max $39.99, PRICES_USD in plans.py).

| Average speech per dictation | Billed minutes | Cost at $0.0045 | With 1.3 retries | Share of $20,000 revenue (with retries) |
|---|---|---|---|---|
| 1 min | 14,000 | $63 | $82 | 0.4 % |
| 3 min | 42,000 | $189 | $246 | 1.2 % |
| 5 min | 70,000 | $315 | $410 | 2.0 % |

The ceiling (everyone dictating 5 minutes, always) is about 2 % of revenue. Even then it is smaller than any of rendering, the script model or voice. If the owner instead picked live `gpt-live-transcribe` the same rows would be 3.8 times as much ($1,560 for the 5 minute row with retries).

Add these lines to `docs/COSTS.md` (done in the same commit).

## 5. Product and technical design

**Batch vs streaming for a "tell me your video idea" box.** Batch with a live native preview is right: people speak in bursts, then read and fix the text before sending, so a 1 to 2 second wait after stop costs nothing, while paid live streaming costs 3.8 times more and brings a socket, token minting and reconnect logic. It also removes today's bugs by construction: the recording is controlled by our app (no engine ending the session when you pause; no engine replacing earlier text). The transcript is **appended** to the text box at the cursor, never replacing it.

**Where the UI lives.** The composer is the web app (`frontend/src/lib/dictation.ts`, `Composer`) inside the iOS and Android shells (`mobile/ios`, `mobile/android`); I did not read how the shells expose the microphone (CNV). The plan therefore records with the browser `MediaRecorder` in the web layer (works in WKWebView on iOS 14.3+ and in Android WebView/Chrome); if a shell blocks it, a small native recorder plugin is the fallback (iOS AVAudioRecorder, Android MediaRecorder), same upload contract.

**Recording format and size.** Android/Chrome: `audio/webm;codecs=opus`; iOS Safari/WebView: `audio/mp4` (AAC). Both are accepted by OpenAI (V: flac, mp3, mp4, mpeg, mpga, m4a, ogg, wav, webm). Mono, 16 kHz where possible, 24 to 32 kbps: **5 minutes is about 0.9 to 1.2 MB** (my 10 s Ogg clips were 25 to 31 KB, i.e. 2.5 to 3 KB a second, so 300 s is about 0.8 to 0.9 MB), far under OpenAI's 25 MB.

**Upload path: direct to a small Lambda (recommended), no S3.** `POST /users/{user_id}/dictation` with the audio as a binary body (API Gateway/Lambda limit 6 MB, we cap at 3 MB and 360 seconds). The Lambda checks plan right and quota, calls OpenAI with the key from SSM (`/videomk/openai_api_key`, already present in QA; the app never holds a key), returns `{text, language, seconds, id}`, and writes only counters (seconds, model, language, cost) to DynamoDB. **The audio is never stored by us**: nothing to leak, nothing to delete on account deletion, and it keeps the privacy copy short. Presigned S3 upload is the fallback only if recordings must exceed about 4 MB (10+ minutes) or we later want retries from stored audio (we should not).

**Plan right and caps.** New right on each plan in `backend/lambdas/common/plans.py` (`PLANS` dict): `stt_premium` (False for free, True for pro and max) and `stt_seconds_per_day` (proposal: Pro 900, Max 3,600; Free 0), plus knobs in `KNOBS`: `stt_enabled` (kill switch), `stt_max_clip_seconds` (default 360), `stt_global_daily_seconds` (a ceiling across all users, like `free_daily_budget_credits`). Daily usage counted in UTC per user in DynamoDB (atomic `ADD` with a condition), the same way the plans' other daily counters work. 900 seconds a day costs at most $0.07, 3,600 at most $0.27, per user per day: the worst-case abuse bound. Over quota or plan lacking the right returns the existing structured plan error (so the app shows the upgrade or "come back tomorrow" text), and the app falls back to native.

**Cost record.** `c_stt` is added where `c_speech` is built. Because dictation precedes the video, the create-video request carries the list of `dictation ids` used (or the app sums them); the launcher sums their cost from the dictation records into `c_stt` and `stt_seconds`, and adds it to `cost_usd`. Files touched: `backend/lambdas/sf_launcher.py` or the create handler, `backend/scripts/cost_report.py`, `backend/admin_console/lambdas/admin_rollup.py`, `backend/lambdas/video_retry.py` (does not re-charge), `docs/COSTS.md`. Dictations never used in a video are still counted in a daily "dictation without video" line in cost_report so nothing is hidden.

**What the apps show.** Paid plans: in the mic menu a mode **"Better dictation"** (default on for paid; the mic button is unchanged for Free). Free: native engine, with a plain upgrade hint where plans UI already allows it (`PURCHASES_LIVE` is False today, so no buy button yet). Offline, over quota, a server error or no right: silently use native and show one line ("Using your phone's dictation"). While recording: native live words as preview, a timer, a visible limit (6 min), a cancel. After stop: spinner "Polishing your words", then the text replaces the preview inside the dictated span only, not the whole box.

**Language.** Send the UI language as `languages=[ui_lang]` hint plus any other languages the person has chosen in settings (Latin American Spanish: `es`; OpenAI takes ISO 639-1). Default is **auto-detect plus hint** (the hint helps proper nouns and mixed speech; my test auto-detected all five). Add a "Dictation language: Auto / <list>" setting. Pass a short `prompt` (context: "A request for a short explainer video") and keywords such as place names from the current draft, to improve names and products (V: `prompt` and keyword hints are supported).

**Privacy copy (privacy policy).** Add: voice dictation for paid plans sends the recording to our speech provider (OpenAI) for transcription only; we do not keep the audio, we keep only the length and the cost; the provider does not use API data for training and keeps no copy by default (state exactly what the provider's terms say on the date of writing and link them); Free dictation uses the phone's own speech engine under Apple's or Google's terms; the microphone permission is requested only when you tap the mic. Also the App Store privacy label ("Audio Data", linked to user, used for app functionality) and Play Data safety form (voice or sound recordings, shared with a service provider, processed ephemerally). These form changes need the owner. The policy text must be reviewed by whoever owns legal; I did not read OpenAI's service terms for children's data or regional restrictions (CNV).

## 6. Implementation plan (work packages)

Effort is one engineer-day (d) with an AI assistant; no code was written in this task.

1. **Provider interface and OpenAI adapter (0.5 d).** `backend/lambdas/common/stt.py`: `transcribe(audio, mime, languages, prompt) -> {text, language, seconds, cost, model}`, an `OpenAIProvider` (model name from config, default `gpt-transcribe`; rate table with `gpt-transcribe` 0.0045 per minute, prices kept next to code like `tts.PER_CHAR`), room for a Scribe adapter. Test: `backend/tests/test_stt.py` with a fake HTTP layer (success, 4xx, timeout, price math).
2. **Plans: rights, knobs, counters (0.5 d).** `plans.py` (`PLANS`, `KNOBS`, `rights`), `plans_admin.py` shows them, `docs/PLANS.md`. Daily counter helper beside the other counters. Tests in `test_plans*.py`: free refused, pro/max allowed, cap reached, kill switch, global ceiling.
3. **Dictation Lambda and route (1 d).** New `backend/lambdas/dictation_api.py`; stack route `POST /users/{user_id}/dictation` in `backend_stack.py` with Cognito auth like `uploads_api.py`; SSM read of the key with caching; 3 MB and duration checks; log only counters; reserved concurrency and a CloudWatch alarm on error rate and daily seconds. Settle the exact OpenAI `languages` form (my single-language attempt failed). Tests: handler tests with the fake provider; one QA smoke test.
4. **Cost record (0.5 d).** `c_stt`, `stt_seconds` in the video record, `cost_report.py`, `admin_rollup.py`, `COSTS.md` table, `test_costs.py`; retried videos are not charged twice.
5. **Recorder and uploader in the web app (1.5 d).** `frontend/src/lib/dictation.ts` (+ `dictation.test.ts`): `MediaRecorder` capture with mime negotiation, level meter, 6 min limit, upload, append at the cursor; native preview kept; graceful fallback to native on any failure. Does not replace text on the next press (R176 bug).
6. **UI: "Better dictation" mode and messages (1 d).** `Composer` mic menu, plan-aware, offline detection, over-quota and upgrade strings in all app languages (en, es, fr, de, it, pt, nl; Korean when it lands), accessibility labels.
7. **Android pause bug and iOS dropped words in native mode (0.5 to 1 d, separate from paid).** The recorder in package 5 avoids both for paid users; for Free, fix the native engine handling (restart on `onend` while the button is held, accumulate finals in a buffer). Tracked as R176 part 1.
8. **Privacy: policy, store forms, in-app disclosure (0.5 d + owner review).** Text in section 5; update the privacy page in `frontend/site-pages` and the store declarations.
9. **Deploy to QA, owner trial, then prod (0.5 d).** Per memory, deploy QA and prod without asking; flip `stt_enabled` on in QA first.
10. **Real-voice evaluation (0.5 d, needs owner time).** 15 to 20 real recordings from the owner and testers: accents (Latin American, Spain, UK, Indian English), a pause-heavy dictation, noise, code-switching, and a first Korean sample. Compare `gpt-transcribe` with Scribe v3 once there is a key; change the default if clearly better. Includes timing of a 5 minute upload on a mobile connection.
11. **Optional later: live mode (2 d).** Only if owners want live paid words: `gpt-live-transcribe` over a WebSocket with a short-lived credential. $0.017 a minute; not recommended for v1.

Total for packages 1 to 6, 8 and 9: about 5.5 to 6 days.

## 7. Owner decisions and risks

Decisions:
1. Which plans get "Better dictation": Pro and Max (proposed) or Max only? Pro costs at most $0.07 per user per day at the 900 s cap.
2. Daily caps (proposal: Pro 900 s, Max 3,600 s, a clip max of 6 minutes) and a global daily ceiling.
3. Approve OpenAI as the processor of voice, and the privacy-policy and store-form changes (App Store "Audio Data", Play Data safety).
4. Supply an ElevenLabs (and optionally Deepgram) API key if a head-to-head on real voices is wanted; I did not sign up.
5. Does Free get a trial of better dictation (for example 3 clips a day)? Not proposed; cost is small (about $0.002 a clip) but the abuse surface is larger.

Risks:
- **OpenAI model churn:** three older transcription models die 2027-02-26 and the TTS models 2027-01-06. `gpt-transcribe` is the replacement, but a single-snapshot model name with no pinned version can change under us (V: only one snapshot is listed). Mitigation: provider interface, a nightly canary clip, the kill switch and native fallback.
- **No independent accuracy figure for `gpt-transcribe`** and no per-language benchmark I could read; my test is 10 s clean synthetic clips. Scribe v3 leads the English-weighted index. Mitigation: package 10.
- **Single-language hint parameter** unresolved in my test (package 3).
- **Price facts that are volatile:** Deepgram streaming is a promo price ($0.0058, was $0.0092); AssemblyAI lists models as deprecated and replaced; Google pricing I could not read.
- **Data terms:** formal zero retention on OpenAI needs an account agreement (CNV); ElevenLabs and Deepgram default training terms are CNV.
- **Webview microphone behavior** (permission prompts, background interruptions, Safari mp4 files) is untested here.
- **Abuse:** bounded by per-user daily seconds, clip length, a global ceiling, and the plan check (dictation endpoint is paid-only).
- **Unreported:** I did not check Korean on any model; Latin American accents on real voices are untested.
