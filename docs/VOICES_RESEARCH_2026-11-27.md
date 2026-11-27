# Voice (TTS) research: is there something much better than Polly generative? (2026-11-27)

Read-only desk research. No accounts, purchases or paid API calls. Prices are list prices read on 2026-11-27.

Labels: **VERIFIED** = I read the provider's own page (or the independent leaderboard page itself) today. **SECONDARY** = blog, aggregator, press or a vendor-run benchmark. **UNVERIFIED** = not found in anything I read; do not rely on it.

Method note: where a number is in the table without a label, it comes from the source named in that row's section. "AA" = Artificial Analysis Speech Arena (`artificialanalysis.ai/text-to-speech/leaderboard`, page read 2026-11-27). Cost per minute assumes **900 characters = 1 minute** (150 words); Spanish runs a few percent longer in characters, so Spanish costs are slightly higher than shown.

---

## 0. Answer in one screen

1. **Anthropic: NO.** There is no Anthropic text-to-speech or voice-output API in 2026. VERIFIED (negative): the full Anthropic API docs index (`platform.claude.com/docs/llms.txt`, 109 KB) contains no mention of speech, audio, voice or TTS. VERIFIED: Anthropic's own cookbook page for a voice assistant uses ElevenLabs for TTS and Claude only for the text reply (`platform.claude.com/cookbook/third-party-elevenlabs-low-latency-stt-claude-tts`). SECONDARY: the Claude apps have a voice mode (eWeek, 9to5Mac; widened to 11 languages in July 2026) and The Decoder reported that Anthropic's terms list ElevenLabs as a text-to-speech subprocessor. So Claude can speak inside Anthropic's apps, but there are no Claude voices to buy through an API.
2. **OpenAI: do not build on it.** OpenAI's dedicated TTS models are **deprecated**: `tts-1` and `tts-1-hd` shut down 2027-01-06 and `gpt-4o-mini-tts` on 2027-01-14 (deprecations page; the TTS guide says 2027-01-06 for all three), replacement is `gpt-realtime-2.1-mini`, which is a Realtime (WebSocket voice-agent) model that "isn't a supported model for /v1/audio/speech". VERIFIED. The owner's suspicion that OpenAI has very good voices was right for 2025; in this arena it is no longer a TTS vendor that is competitive or even staying on the standard endpoint. In AA, OpenAI's best entry is TTS-1 HD at 1109 and GPT-Realtime-2 at 1070 (about Polly generative's level, 1063) and I found no `gpt-4o-mini-tts` row in the ranking.
3. **The best voices today are not Polly, not OpenAI.** On AA (English, blind votes, Sept to Nov 2026) the top is **ElevenLabs Eleven v4 Turbo 1343 and Eleven v4 1340**, then StepAudio 3 (1310), Qwen-Audio-3.1-TTS-Plus (1299), **Cartesia Sonic 3.6 (1297)**, **Speechify Simba 3.5 (1296)**, **Gemini 3.8 Flash TTS (1286)**, **Inworld Realtime TTS-2 (1272)**. **Polly Generative sits at 1063 (rank 61-72 of 106), tied with Google Chirp 3 HD (1062) and the 82M-parameter open model Kokoro (1060).** A 280-point gap means listeners prefer the top model in about 83 % of head-to-head clips (standard Elo formula). The owner's impression that Polly is "only slightly better than before" is consistent with this.
4. **Price is not the obstacle.** Gemini 3.8 Flash TTS costs about **$0.014 per minute until 2026-12-31 and $0.027 per minute from 2027-01-01** (Polly generative: $0.027). Speechify Simba 3.5 is $0.0135 per minute. ElevenLabs v4 is $0.072 per minute (2.7x Polly), v4 Turbo $0.036.
5. **Word timings are the real integration question.** Polly generative has no speech marks (VERIFIED, Polly docs: "Support for generating speech marks is currently not available"), which is why `engine/align.py` estimates words from the waveform (mean error 80 ms). ElevenLabs, Inworld, Speechify, Cartesia and Azure all return word (or character) timings natively; **Gemini and Google Chirp do not document any**, so Gemini would keep `align.py`.
6. **Suggested next step:** run the blind test in section 7 (six voices, about $1 and one afternoon) with ElevenLabs v4, Gemini 3.8 Flash, Cartesia Sonic 3.6, Inworld TTS-2, Speechify Simba 3.5 and Polly Ruth/Lucia as control.

---

## 1. Independent quality evidence

### 1.1 Artificial Analysis Speech Arena (English, blind, "Provider Voice" board)

VERIFIED (page read 2026-11-27; 108 models, 106 ranked). Listeners hear two clips of the same text from each model's own native voices and choose the more natural one. This is English only (accents US and UK) and short clips; it does not test 5-minute consistency or Spanish. Elo scale anchored at Zonos v0.1 = 1000. The "Knowledge Sharing" category column (closest to explainer narration) is read from the same page's embedded data and is also VERIFIED as page data.

| Model (provider) | All-categories Elo | Knowledge Sharing Elo | Samples | Released | AA price per 1M chars |
|---|---|---|---|---|---|
| Eleven v4 Turbo (ElevenLabs) | **1343** | **1327** | 2,927 | Sept 2026 | $40 |
| Eleven v4 (ElevenLabs) | 1340 | 1318 | 3,198 | Sept 2026 | $80 |
| StepAudio 3 TTS (StepFun, China) | 1310 | 1314 | 2,125 | Nov 2026 | $14 |
| Qwen-Audio-3.1-TTS-Plus (Alibaba) | 1299 | 1311 | 2,996 | Sept 2026 | $19.31 |
| Sonic 3.6 (Cartesia) | 1297 | 1292 | 3,877 | Aug 2026 | $49 |
| Simba 3.5 (Speechify) | 1296 | 1301 | 2,222 | Nov 2026 | $6.58 (list is $15, see 3.7) |
| Gemini 3.8 Flash TTS (Google) | 1286 | 1251 | 4,111 | Sept 2026 | $16.49 |
| Fish Audio Drama 3 (open weights) | 1278 | 1269 | 2,159 | Oct 2026 | $15 (list is $50, see 3.9) |
| Realtime TTS-2 (Inworld) | 1272 | 1283 | 3,205 | Aug 2026 | $20.83 |
| Gemini 3.8 Flash-Lite TTS | 1265 | 1231 | 4,022 | Sept 2026 | $11.03 |
| Realtime TTS-2 Flash (Inworld) | 1216 | 1239 | 3,563 | Aug 2026 | $10.42 |
| Gemini 3.1 Flash TTS (preview) | 1217 | 1219 | 5,066 | Apr 2026 | $18.31 |
| Voxtral 3 TTS (Mistral) | 1211 | 1219 | 2,557 | Oct 2026 | $13 |
| Eleven v3 | 1194 | 1194 | 5,768 | Feb 2026 | $100 |
| Speech 2.8 HD (MiniMax) | 1173 | 1193 | 5,863 | Feb 2026 | $100 |
| Azure HD 2.5 (Microsoft) | 1152 | 1158 | 3,552 | Mar 2026 | $22 |
| Chatterbox HD (Resemble, MIT) | 1112 | 1125 | 3,085 | May 2025 | $40 |
| TTS-1 HD (OpenAI, deprecated) | 1109 | 1118 | 4,142 | Nov 2023 | $30 |
| **Polly Generative (Amazon)** | **1063** | **1074** | 4,073 | May 2024 | $30 |
| Chirp 3: HD (Google) | 1062 | 1066 | 3,696 | Mar 2025 | $30 |
| Octave 2 (Hume) | 1060 | 1066 | 3,465 | Oct 2025 | $87.50 |
| Kokoro 82M v1.0 (open, Apache-2.0) | 1060 | 1093 | 5,697 | Jan 2025 | $0.65 hosted |
| GPT-Realtime-2 (OpenAI) | 1070 | 1078 | 2,684 | May 2026 | $191.56 |
| Polly Long-Form | 1029 | 1045 | 2,182 | Nov 2023 | $100 |
| Azure Neural (old) | 1033 | n/a | 1,156 | 2018 | $15 |
| Polly Neural | 895 | n/a | 3,045 | 2019 | $16 |

Not on the board at all (so no independent English Elo): Deepgram Aura-2, Play.ht, Sesame CSM, Orpheus, Dia, F5-TTS, Inworld TTS-1 family (retired). Expected preference against Polly Generative, from the Elo gap: Eleven v4 Turbo about 83 %, Simba 3.5 and Sonic 3.6 about 79 %, Inworld TTS-2 about 77 %, Gemini 3.8 Flash about 78 % (all categories) or 74 % (Knowledge Sharing), Azure HD 2.5 about 62 %, Chirp 3 HD and Kokoro about 50 %.

Caveats: the arena includes models each vendor tunes for short English clips; vendors with a clear lead (ElevenLabs) can also be the ones whose voices tire over minutes (unknown); the 95 % intervals are about plus or minus 10 to 16 points, so adjacent rows (for example Sonic 3.6, Simba 3.5, Qwen, StepAudio) are statistical ties. The same page has a second board using one set of cloned voices; there Qwen-Audio-3.1-TTS-Plus is first (1208), HeyGen Voice 1190, Simba 3.5 1185, Eleven v4 Turbo 1158, Gemini 3.8 Flash 1055. That board tests the model, not the stock voices; stock voices (what we need) matter more to us, so I used the Provider Voice board.

### 1.2 Spanish

There is **no neutral Spanish TTS arena** that includes the new models. What exists:
- SECONDARY (vendor-run, Speko, a voice-agent platform; blind A/B on 2026-07-21, before Eleven v4 existed): **ElevenLabs `eleven_v3_conversational` leads Spanish, Elo 1951 (95 % CI 1859 to 2142)**; their page says Gemini 3.1 Flash TTS leads Filipino and most other languages are statistical ties. Their model set and listening panel are not described on the page I read. Treat as a hint, not proof.
- SECONDARY (competitor-run, Gradium, April 2026): Spanish word-error rate 0.40 % for Gradium vs 0.99 % for ElevenLabs Flash v2.5. Not independent.
- Open models: Hugging Face "Open TTS Leaderboard" Spanish board is led by an open model called OmniVoice (WER 1.15, SECONDARY), commercial APIs not in it.
- Therefore: **Spanish quality must be judged by ear with our own paragraphs** (section 7), per variety (Spain and Latin America).

---

## 2. Anthropic (details)

| Question | Answer | Label |
|---|---|---|
| Does Anthropic offer TTS / voice output via API in 2026? | **No.** Docs index has no speech/audio/voice pages. | VERIFIED (negative search of `llms.txt`) |
| Does Claude "speak" at all? | Yes, in the consumer apps (voice mode, beta May 2025; 2026: Opus, Sonnet, Haiku, 11 languages, mobile/desktop/web). Not exposed as an API. | SECONDARY (eWeek, 9to5Mac, Outlook Business) |
| Who makes the voice? | ElevenLabs, per Anthropic's terms listing it as TTS subcontractor (as reported May 2025). I could not load the subprocessor page to re-check. | SECONDARY (The Decoder, Simon Willison) |
| Anthropic's own recommended path for developers | Pair Claude with ElevenLabs (cookbook). | VERIFIED |

Implication: Claude stays our script and director model; the voice comes from a third party. ElevenLabs is the vendor Anthropic itself uses.

---

## 3. Provider by provider

For each: models, price, Spanish, controls, dialogue, word timings, licence, hosting/GDPR.

### 3.1 OpenAI (not recommended: shutting down)

- Models: `gpt-4o-mini-tts`, `tts-1`, `tts-1-hd`. All **deprecated** (announced 2026-10-01). Shutdown 2027-01-06 for tts-1 and tts-1-hd and 2027-01-14 for gpt-4o-mini-tts on the deprecations table; the TTS guide says 2027-01-06 for all three. Replacement named: `gpt-realtime-2.1-mini`, not available on `/v1/audio/speech`. VERIFIED.
- Voices: 13 listed (alloy, ash, ballad, coral, echo, fable, nova, onyx, sage, shimmer, verse, marin, cedar), "marin or cedar" recommended; the page text also says "11 built-in voices", so counts conflict. VERIFIED.
- Steerability: natural-language `instructions` (accent, emotional range, intonation, impressions, speed, tone, whispering). VERIFIED. Our `OpenAITTS` class already passes `instructions`.
- Price: `gpt-4o-mini-tts` $0.60 per 1M text tokens in plus **$12 per 1M audio tokens out**; `tts-1` $15 and `tts-1-hd` $30 per 1M characters; `gpt-realtime-2.1-mini` audio $10 in / $20 out per 1M tokens; `gpt-realtime-2.1` audio $32 / $64. VERIFIED (OpenAI pricing page). Tokens per minute of speech are not stated on that page, so a per-minute cost for gpt-4o-mini-tts is UNVERIFIED. AA estimates GPT-Realtime-2 at $191.56 per 1M characters (about $0.17 per minute).
- Spanish: model "generally follows Whisper language support", voices "currently optimized for English". No Spanish quality evidence found. VERIFIED statement; quality UNVERIFIED.
- Streaming yes; max input not stated on the guide page (UNVERIFIED). Formats mp3, opus, aac, flac, wav, pcm (24 kHz). Word timings: **none** documented. VERIFIED (absent on the guide I read).
- Commercial terms: usage policy "requires clear disclosure to end users that the TTS voice they are hearing is AI-generated". VERIFIED. Custom voices need consent recording (we do not need).
- Hosting: separate OpenAI account; not on Bedrock (I found no Bedrock listing; UNVERIFIED). GDPR position not researched.
- Verdict: skip; a swap would be a migration to a Realtime API for a one-way narration job.

### 3.2 ElevenLabs (best quality)

- Models (VERIFIED, docs and pricing page): **Eleven v4** (flagship, "most emotive", 90+ languages, **100,000-character** request limit, multi-speaker dialogue, audio tags, no SSML, Style/Speed sliders not available), **v4 Turbo** (real-time, about 100 ms, v4 expressiveness), v3 (70+ languages, 5,000 chars, dialogue), v3 Conversational, Multilingual v2 (29 languages, 10,000 chars, "most stable on long-form"), Flash v2.5 (32 languages, 40,000 chars). Docs recommend v4 or Multilingual v2 for "audiobooks & video narration".
- Price (VERIFIED, pricing page): API **v4 $0.08 per 1K characters, v4 Turbo $0.04, v3 $0.08, Multilingual v2 $0.08, Flash/Turbo $0.04**. Plans: Free $0 (10,000 chars), Starter $6 (75,000 v3/v4 chars), Creator $22 (275,000), Pro $99 (1,238,000), Scale $299 (3,738,000), Business $990 (12,375,000), i.e. $0.08 per 1K at every tier for v4 (overage rates not read).
- Spanish: v4 supports Spanish (listed among 90+ languages; docs for Multilingual v2 list Spanish Spain and Mexico). Best available Spanish signal is the Speko result (3.1/1.2, SECONDARY).
- Expressiveness: audio tags such as `[whispering]`, `[laughing]`; docs admit tag-following is "not perfect yet". Stability and similarity sliders on older models; Voice Library has 10,000+ voices.
- Dialogue: **Text to Dialogue API** (v4 and v3), each turn its own text and voice, no speaker limit, keep input at or below 2,000 characters per request, nondeterministic (use `seed`). VERIFIED.
- Word timings: **`/v1/text-to-speech/:voice_id/with-timestamps`** returns `alignment` with `characters`, `character_start_times_seconds`, `character_end_times_seconds` (plus `normalized_alignment`); there is also a Forced Alignment API in the docs navigation. VERIFIED for the endpoint; I did not confirm that v4 specifically is supported on it (UNVERIFIED).
- Licence: commercial use only on a paid plan; free users non-commercial. VERIFIED (Terms of Use 1(c) and the Text to Dialogue page). You retain ownership of output. Prohibited Use Policy applies. No AI-disclosure duty found in the terms beyond the policy (UNVERIFIED; check policy text before launch).
- Hosting/GDPR: separate account. US storage by default; **EU data residency and Zero Retention Mode are Enterprise-only**; with ZRM plus EU residency processing can be limited to the EU. DPA exists; SOC 2 and GDPR "aligned" claims. VERIFIED (data residency page). Private deployment on AWS SageMaker/Marketplace exists (SECONDARY, search results; custom pricing). Not on Bedrock (not found).
- Docs note a deprecation of music_v1 only; no TTS deprecation announced for v4.

### 3.3 Google: Gemini TTS, Chirp 3 HD, Cloud TTS (best value; owner has a Google key)

Pricing (VERIFIED, `cloud.google.com/text-to-speech/pricing` and `ai.google.dev/gemini-api/docs/pricing`). Audio output is 25 tokens per second of audio = 1,500 tokens per minute.

| Model | Output price per 1M audio tokens | Per minute (audio only) | Notes |
|---|---|---|---|
| **Gemini 3.8 Flash TTS** (GA on Gemini API) | $9.00 through 2026-12-31; **$18.00 from 2027-01-01** | $0.0135; $0.027 | text in $0.50 then $1.00 per 1M tokens; **Batch API half price** ($4.50 then $9.00) |
| Gemini 3.8 Flash-Lite TTS | $6.00 then $12.00 | $0.009; $0.018 | text in $0.50 then $1.00 |
| Gemini 3.1 Flash TTS (preview) | $20.00 | $0.030 | text in $1.00 |
| Gemini 2.5 Flash TTS | $10.00 | $0.015 | |
| Gemini 2.5 Pro TTS | $20.00 | $0.030 | |
| Chirp 3: HD | $30 per 1M characters (first 1M chars/month free) | $0.027 | AA 1062, same as Polly |
| Neural2 / Polyglot | $16 per 1M characters | $0.0144 | legacy |
| Studio | $160 per 1M characters | $0.144 | legacy |

- **Where it runs:** Gemini 3.8 TTS is GA through the Gemini API (`generativelanguage.googleapis.com`, key in header; new "interactions" request shape) and the Agent Platform (Vertex successor) API; Google states 3.8 models "aren't available through the Cloud Text-to-Speech API". The Cloud TTS API serves 3.1 Flash, 2.5 Flash/Pro and Chirp 3. VERIFIED. Our `GeminiTTS` class uses `gemini-2.5-flash-preview-tts` through `generateContent`; it needs updating to a current model and the interactions shape.
- Free-tier trap: the Gemini API free tier and AI Studio are "Unpaid Services": Google uses prompts and outputs to improve products and human reviewers may read them; **the terms say you may use only Paid Services when serving users in the EEA, Switzerland or UK**. Use a billing-enabled project. VERIFIED (Gemini API terms).
- Spanish: 3.8 Flash supports "over 130 languages" with automatic language detection (Spanish listed); Cloud TTS Gemini list shows **Spanish (Spain) es-ES GA; Spanish (Mexico) es-MX and Latin America es-419 are Preview**. No separate accent-control parameter was found for the 3.8 API beyond voice and style (UNVERIFIED); accents are prompted in style text.
- Controls: natural-language per-turn `style` (for example "whispered urgently"), inline tags like `<short pause>`, `<sigh>`, `<laugh>`, 30 prebuilt voices (for example Kore, Puck, Sulafat "Warm", Sadaltager "Knowledgeable"), an Extended Voice Library via `GET /v1beta/voices` filterable by language, accent, persona ("Narrator"), voice design and remixing. VERIFIED.
- Dialogue: native multi-speaker, **up to 2 speakers with prebuilt voices per request**; more speakers by one request per turn. VERIFIED.
- Limits: input 8,192 tokens; output 16,384 tokens (about 655 seconds). Fine for per-beat synthesis (our beats are one or two sentences).
- **Word timings: none documented** (nothing in the speech-generation guide, the model page or the Cloud TTS Gemini page). Cloud TTS has SSML `<mark>` timepoints for older voices only; Chirp 3 HD and Gemini do not (UNVERIFIED for Chirp). Plan to keep `align.py`, possibly improved by a forced-alignment step.
- AI disclosure: not found in the pages read; EU-wide marking rules apply to us anyway (section 5).
- Hosting/GDPR: separate Google account (the owner's existing Google Cloud project is enough for Cloud TTS or Vertex/Agent Platform; the AI Studio-style Gemini API key is a separate product). Cloud TTS page says ML processing occurs in the selected region or multi-region (VERIFIED). Not on Bedrock.

### 3.4 Cartesia (Sonic 3.6)

- Sonic 3.6 GA, 44 languages including Spanish; dated snapshot 2026-08-27. VERIFIED (docs).
- Price (VERIFIED, pricing page): 1 credit per character. Free $0 (20K credits), **Pro $5 per month = 100K credits ($50 per 1M chars; commercial licence starts at Pro)**, Startup $49 = 1.25M ($39.20 per 1M), Scale $299 = 8M ($37.40 per 1M); Cartesia quotes about 750 to 800 credits per audio minute.
- Controls: emotion, speed, volume, SSML-ish tags, `<break>`; no instruction prompt (the model infers pacing from text). VERIFIED partially.
- Word timings: WebSocket TTS with `"add_timestamps": true` returns `word_timestamps` {words, start, end} and `phoneme_timestamps`. VERIFIED (API reference). Needs the WebSocket endpoint, not the plain HTTP bytes endpoint (UNVERIFIED which endpoints honour it).
- Multi-speaker dialogue: no dedicated dialogue endpoint found; synthesize per speaker (we already synthesize per beat). UNVERIFIED.
- GDPR: SOC 2 Type II; DPAs and BAAs only on Enterprise. Separate account; no Bedrock listing found. Watermarking page exists in docs (could not load; UNVERIFIED).

### 3.5 Inworld (Realtime TTS-2)

- Models: `inworld-tts-2` (flagship; natural-language steering; 200+ languages and locales; 100 ms) and `inworld-tts-2-flash` (cheapest; **no steering**). Earlier models discontinued 2026-06-15. VERIFIED (docs).
- Price (VERIFIED, pricing page): per 1M characters, TTS-2 **$25 on-demand**, $20 (Creator $25 per month), $17.50, $15, $12.50, as low as $5 on Enterprise; **Flash $15, $10, $9, $8, $7**; page uses about 1,000 characters per minute.
- **Spanish: strongest regional control seen.** Spanish is Tier 1; `es` defaults to es-ES; accepts es-MX, es-419 and es-AR, es-CO, es-CL, es-PE and about 15 other regional codes ("es-US falls back to es-ES"). A voice reproduces the accent it was cloned in; the regional code steers others. VERIFIED (multilingual docs).
- **Word timings: yes, and in every supported language**: `timestampType: WORD` returns word start/end plus phoneme details and visemes; `CHARACTER` also available; streaming sync or async. VERIFIED. Best match for our sync needs.
- Dialogue: no dedicated multi-speaker endpoint found (UNVERIFIED); per-beat synthesis fits.
- Licence/GDPR: not researched beyond "Compliance add-ons on Growth plan"; UNVERIFIED. Separate account.

### 3.6 Microsoft Azure

- Azure Speech prices (VERIFIED via the public Azure Retail Prices API, westeurope and eastus identical): **Neural $15 per 1M characters, Neural HD $22 per 1M characters** (effective 2026-03-01); Professional custom voice $24. MAI-Voice price not published (page shows no figure, AA lists N/A). Pricing page itself rendered without numbers.
- Quality: AA Azure HD 2.5 1152 (about 62 % preference over Polly generative); MAI-Voice-1 1026.
- **Dragon HD Omni**: multilingual with automatic language detection, `mstts:express-as` natural-language style control (documented for English; "styles are available on all English content"), paralinguistic tags (laughter, sighing), and **word boundary events** with AudioOffset (ms). VERIFIED (HD voices doc). Spanish HD voices and quality: UNVERIFIED.
- Dialogue: per-voice SSML; no single-call multi-speaker found.
- Hosting: separate Azure account (EU regions available, `westeurope`). Not on Bedrock.

### 3.7 Speechify (SpeechifyAI Simba 3.5) (best value in the top tier)

- `simba-3.5`: 48 languages under one model id (Spanish included), "every voice in the catalog speaks all 48"; `simba-3.0` also covers Spanish. VERIFIED (docs).
- Price (VERIFIED, speechify.ai API page): Simba 3.5 **$15 / $12 / $10 per 1M characters on Starter / Pro / Scale**; Simba 3.0/3.2 $10/$8/$6. **Free plan includes 500K characters per month with commercial use.** SECONDARY: launch pricing $10/$8/$6 until 2026-11-21 (now expired) and a halving of included characters after it; AA lists $6.58 (launch-era or blended figure; use $15 for planning).
- **Word timings: yes** ("speech marks" give every word's start and end in ms) via `/v1/audio/stream/with-timestamps` (20,000 spoken-character limit; `/v1/audio/speech` limit 2,000). VERIFIED.
- Controls: SSML (prosody pitch and volume, emphasis, `speechify:style` accepted "but not applied" on Simba 3.x per the page); no instruction prompt found. Pronunciation field (IPA or alias).
- GDPR: `eu.api.speechify.ai` pins **synthesis** to Europe but "not data residency: account data, keys, voices and logs stay in the US". SOC 2 mentioned. VERIFIED.
- Quality: AA Simba 3.5 1296 (Knowledge Sharing 1301, rank 5). Spanish quality UNVERIFIED.

### 3.8 Amazon (Polly generative, long-form, Nova Sonic) (what we use today)

- Polly prices (VERIFIED, aws.amazon.com/polly/pricing): Standard $4, Neural $16, **Long-Form $100, Generative $30 per 1M characters**; free tier: Generative 100K characters per month for 12 months. The page names no region; I did not find an eu-west-1 specific figure (UNVERIFIED for eu-west-1; the code assumes list prices).
- **Generative engine has no speech marks** (Polly docs, VERIFIED). **Long-Form supports all speech marks** but only in us-east-1 and Spanish only has Alba and Raul; AA Long-Form 1029, worse than Generative.
- Generative expansion 2026-03-20: 10 new voices (French, Italian, German, English variants), London and Canada regions, Bidirectional Streaming API (VERIFIED). Spanish generative voices: Lucia, Sergio (Spain), Mia, Andres (Mexico), Lupe, Pedro, Carlos (US Spanish) (feature page lists; matches `voices.py`).
- Nova 2 Sonic (Bedrock `amazon.nova-2-sonic-v1:0`): speech-to-speech conversational model; March 2026 update added "Polly-compatible voices"; a Bedrock model card mentions a Nova 2.5 Sonic dated 2026-10-05 (SECONDARY, unconfirmed). It is a voice-agent model, not a narration engine; no per-character TTS price and no word timings found. **There is no new Amazon narration model beyond Polly generative that I could find.**
- Hosting: in-account, IAM role, no data leaves AWS (the current design's best property).
- No Amazon-hosted third-party TTS model (ElevenLabs etc.) found on Bedrock; ElevenLabs is sold through AWS Marketplace as a private-deployment/enterprise product (SECONDARY).

### 3.9 Fish Audio (Drama 3, S2.1 Pro)

- Price (VERIFIED, docs.fish.audio): **`drama-3` $50 per 1M UTF-8 bytes list; promotional $10 through 2026-11-30 (ends in three days)**; `s2.1-pro` and `s2-pro` $15 per 1M bytes. 1M bytes is "about 180,000 English words, about 12 hours". Spanish accented letters are 2 bytes, so Spanish costs a few percent more. AA lists $15 for Drama 3 (stale).
- Quality: AA Drama 3 1278 (Knowledge Sharing 1269), best open-weights model on AA; S2.1 Pro 1181.
- Licence (SECONDARY): weights under the Fish Audio Community License: free for research, free commercially under US$500,000 yearly revenue, but offering the model as a service needs a licence; read the LICENSE file before relying on it. Spanish quality, timestamps and dialogue: UNVERIFIED (one blog says 83 languages and whole-scene dubbing).
- Concurrency tiers: 5 requests below $100 paid, 15 at $100+.

### 3.10 Others

| Provider | What I found | Label |
|---|---|---|
| **Hume Octave 2** | AA Elo 1060 (Polly level), AA price $87.50 per 1M chars; vendor pricing figures conflict ($0.10, $0.063, $0.025 per 1K); Spanish not confirmed (11 languages claimed). Not competitive on quality per dollar. | AA VERIFIED; rest SECONDARY |
| **Deepgram Aura-2 / Flux TTS** | Aura-2 **$0.030 per 1K chars** ($0.027 Growth), Aura-1 $0.015, Flux TTS $0.045. Not on AA. Spanish voices and word timings not checked. Built for voice agents. | pricing VERIFIED; rest UNVERIFIED |
| **MiniMax Speech 2.8 HD / Turbo** | AA 1173 / 1151 at $100 / $60 per 1M chars. Expensive for the quality. | AA VERIFIED |
| **Resemble (Chatterbox)** | Open model MIT, 23 languages incl. Spanish (HF card VERIFIED); AA Chatterbox 1021, HD 1112; hosted at about $1 per 1M chars (DeepInfra, SECONDARY). Managed Resemble pricing not found. | mixed |
| **Play.ht** | Not on AA; not researched. UNVERIFIED. | UNVERIFIED |
| **Qwen-Audio-3.1-TTS-Plus (Alibaba Cloud Model Studio)** | AA 1299, $19.31 per 1M chars. Alibaba's Singapore price for the Flash variant is token-based since 2026-09-22; Plus price and Spanish support not found. Data sits in Alibaba Cloud (Singapore or China regions): GDPR transfer questions. | AA VERIFIED; rest SECONDARY |
| **StepAudio 3 TTS (StepFun)** | AA 1310 (#3), $14. Chinese vendor; pricing in yuan (2.5 yuan per 10,000 chars, SECONDARY); Spanish and timestamps unconfirmed; one doc says no streaming WebSocket and cloned IDs fail on v3. | AA VERIFIED; rest SECONDARY |
| **Mistral Voxtral TTS** | EU (France) vendor; 9 languages incl. Spanish; voice-prompt driven (clone from 2 to 3 s sample, "no prosody tags"); open weights are **CC BY-NC 4.0 (not commercial)** (HF card VERIFIED); AA Voxtral 3 TTS 1211 at $13. API per-minute price not read. Interesting only if EU hosting becomes decisive. | mixed |
| **Gradium (France)** | AA 1152 to 1174, $47.78. EU company; not researched further. | AA VERIFIED |

### 3.11 Open source (only commercial-licence models; for a self-hosted fallback)

| Model | Licence (HF card, VERIFIED) | Spanish | AA Elo | Verdict |
|---|---|---|---|---|
| **Kokoro 82M v1.0** | Apache-2.0 | Yes: VOICES.md lists Spanish 1F 2M | 1060 (Knowledge 1093) | Same Elo as Polly generative at about $0.65 per 1M chars hosted or CPU-only self-host. Not better, only cheaper. Word timings: not verified. |
| Chatterbox | MIT | 23 languages incl. es | 1021 / HD 1112 | Below Polly; skip |
| Orpheus 3B | Apache-2.0 | English main model; separate Spanish/Italian "research release" (Apache-2.0 tag) | not on AA | Not competitive evidence |
| Dia 1.6B | Apache-2.0 | English only | not on AA | skip |
| Sesame CSM-1B | Apache-2.0 | English only | not on AA | skip |
| F5-TTS | **CC-BY-NC-4.0** | n/a | not on AA | **not allowed commercially** |
| Voxtral TTS weights | **CC-BY-NC-4.0** | es | 1094 (v1) | **not allowed commercially** (API route ok) |
| Qwen3-TTS 1.7B | Apache-2.0 | listed multilingual (not checked) | 932 to 942 | far below Polly |
| Fish Audio Drama 3 | Community License (SECONDARY) | UNVERIFIED | 1278 | competitive but licence needs a lawyer's read and GPU hosting |

Conclusion: no open model both beats Polly generative on AA and has a clean commercial licence, except Fish Drama 3 whose licence is conditional. Self-hosting is not worth it.

---

## 4. Comparison table (one row per serious candidate)

Cost per minute at 900 characters; "native words" = the provider returns word timings itself.

| Candidate | AA Elo (Knowledge) | $ / min | Spanish (ES / LatAm) | Controls | Dialogue | Native word timings | Separate account | Notes |
|---|---|---|---|---|---|---|---|---|
| **Polly Generative (now)** | 1063 (1074) | 0.027 | Lucia, Sergio (ES); Mia, Andres (MX); Lupe, Pedro, Carlos (US) | none (style ignored) | per-beat, by voice | **No** (align.py) | No (IAM) | in-account, no keys |
| **ElevenLabs v4** | 1340 (1318) | **0.072** | yes (90+ lang); Speko lead for ES (v3 Conv.) | audio tags | Text to Dialogue API | **chars** (with-timestamps) | Yes | best quality; 100K chars per request |
| ElevenLabs v4 Turbo | 1343 (1327) | 0.036 | yes | audio tags | yes | chars | Yes | half price, same quality class |
| **Gemini 3.8 Flash TTS** | 1286 (1251) | **0.0136 now / 0.027 from 2027** (batch half) | es-ES GA; es-MX, es-419 preview in Cloud list | style prompt + tags, 30 voices + library | 2 speakers per call | **No** | Google (owner has) | cheapest strong option; paid tier needed for EEA |
| Gemini 3.8 Flash-Lite TTS | 1265 (1231) | 0.009 / 0.018 | as above (100+ lang) | style | 2 speakers | No | Google | cheapest |
| **Cartesia Sonic 3.6** | 1297 (1292) | 0.035 (Startup) to 0.045 (Pro) | es (44 lang) | speed/emotion tags | per-beat | **words + phonemes** (WebSocket) | Yes | commercial licence from $5 plan |
| **Inworld Realtime TTS-2** | 1272 (1283) | 0.0225 (on-demand) | **Tier 1; es-ES, es-MX, es-419, es-AR... codes** | **natural-language steering** | per-beat | **words + phonemes, all languages** | Yes | best Spanish accent control |
| Inworld TTS-2 Flash | 1216 (1239) | 0.0135 | same | no steering | per-beat | words (docs say timestamps for TTS-2 models) | Yes | |
| **Speechify Simba 3.5** | 1296 (1301) | **0.0135** | es (48 lang) | SSML, pronunciations | per-beat | **words (speech marks)** | Yes | free 500K chars/mo commercial |
| Azure Dragon HD Omni / HD 2.5 | 1152 (1158) | 0.0198 | multilingual auto-detect; ES HD UNVERIFIED | express-as style (EN) | per-voice | **words (SDK event)** | Yes (Azure) | EU region available |
| Fish Audio Drama 3 | 1278 (1269) | 0.045 list (0.009 until 11-30) | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | Yes | licence conditional |
| Qwen-Audio-3.1-TTS-Plus | 1299 (1311) | 0.0174 (AA) | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | Yes (Alibaba) | GDPR transfer risk |
| StepAudio 3 TTS | 1310 (1314) | 0.0126 (AA) | UNVERIFIED | UNVERIFIED | UNVERIFIED | UNVERIFIED | Yes (China) | GDPR transfer risk |
| Google Chirp 3 HD | 1062 (1066) | 0.027 | es-ES, es-US etc. (not read) | few | no | No | Google | no gain over Polly |
| OpenAI gpt-4o-mini-tts / tts-1-hd | 1109 (tts-1-hd) | 0.027 (tts-1-hd) | "optimized for English" | `instructions` | no | No | Yes | **shuts down Jan 2027** |
| Hume Octave 2 | 1060 (1066) | 0.079 (AA) | UNVERIFIED | emotion prompts | no | UNVERIFIED | Yes | not competitive |
| Deepgram Aura-2 | not ranked | 0.027 | UNVERIFIED | few | no | UNVERIFIED | Yes | agent-oriented |
| MiniMax Speech 2.8 HD | 1173 (1193) | 0.09 (AA) | UNVERIFIED | | | UNVERIFIED | Yes | pricey |
| Kokoro (open) | 1060 (1093) | about 0.0006 hosted | 3 voices | none | no | UNVERIFIED | self-host | = Polly quality, cheaper |

---

## 5. Commercial terms, disclosure, privacy

- **Commercial use:** OpenAI allowed with AI-voice disclosure; ElevenLabs paid plan required (free is non-commercial); Cartesia commercial licence from Pro ($5); Speechify free plan already includes commercial use; Gemini paid tier required for EEA users; Polly commercial use fine (AWS Service Terms; not re-read today). Fish Drama 3 weights: revenue-capped licence (SECONDARY).
- **AI disclosure:** OpenAI: required by usage policy (VERIFIED). For EU users there is also the EU AI Act Article 50: generally applicable since 2026-08-02; the Digital Omnibus (Regulation 2026/1744, in force 2026-07-27) gives generative systems already on the market before 2026-08-02 until **2026-12-02** to meet the machine-readable marking duty of Article 50(2) (SECONDARY: law-firm summaries; the audio specifics were not covered by what I read, so this is my inference). Practical suggestion: label videos "AI-generated voice" in the player/metadata regardless of vendor, and ask each vendor whether its output carries a watermark. **Get a lawyer to confirm before launch** (we also have `docs/LEGAL_DRAFT_NOTES.md`).
- **Voice cloning and consent:** we need none; use stock voices only. Every vendor above requires consent for clones (OpenAI: consent recording; Gemini: "reference and consent audio"). Avoid "voice of a celebrity" prompts.
- **GDPR / data processing:** Polly is the best on this axis (in-account). Google (processing in chosen region; paid tier only for EEA) and Azure (EU regions) are next. ElevenLabs offers EU residency and zero retention only on Enterprise; standard accounts store in the US with a DPA. Speechify: EU synthesis pinned but accounts/logs in US. Cartesia: SOC 2, DPA on Enterprise. Alibaba/StepFun: data leaves the EU to Asia. Whatever we choose, the privacy policy (which already lists the TTS provider) must name it, and scripts must not carry personal data beyond what users write.
- **Bedrock/Marketplace:** only Polly (and Nova Sonic, a conversation model) are native to AWS. ElevenLabs is on AWS Marketplace as a private-deployment/enterprise offering (SECONDARY). Everything else needs its own account, key in SSM (`/videomk/<provider>_api_key`, existing pattern), and egress from the Lambda.

---

## 6. Cost per video

Characters: 1-minute video about 900, 5-minute video about 4,500 (script characters only; a video also has other costs, see `docs/COSTS.md`: a 1-minute video costs about $0.066 today of which Polly is $0.029).

| Option | $ per 1M chars (or equiv.) | 1-minute video | 5-minute video | Extra cost vs Polly generative on a 5-min video |
|---|---|---|---|---|
| Polly Neural | 16 | $0.014 | $0.072 | -$0.063 |
| **Polly Generative (today)** | 30 | **$0.027** | **$0.135** | 0 |
| Polly Long-Form | 100 | $0.090 | $0.450 | +$0.315 |
| Gemini 3.8 Flash-Lite TTS (to 2026-12-31 / 2027) | 6.2 to 12.2 equiv. | $0.009 / $0.018 | $0.046 / $0.091 | -$0.09 / -$0.044 |
| **Gemini 3.8 Flash TTS (to 2026-12-31)** | 15.1 equiv. | **$0.0136** | **$0.068** | -$0.067 |
| **Gemini 3.8 Flash TTS (from 2027-01-01)** | 30.2 equiv. | $0.027 | $0.136 | about 0 |
| Gemini 3.8 Flash TTS, Batch API (2027) | 15.1 equiv. | $0.0136 | $0.068 | -$0.067 |
| Gemini 3.1 Flash TTS preview | 33.5 equiv. | $0.030 | $0.151 | +$0.016 |
| Speechify Simba 3.5 (Starter / Scale) | 15 / 10 | $0.0135 / $0.009 | $0.068 / $0.045 | -$0.068 / -$0.09 |
| Inworld TTS-2 (on-demand / $20 tier) | 25 / 20 | $0.0225 / $0.018 | $0.113 / $0.090 | -$0.022 / -$0.045 |
| Inworld TTS-2 Flash | 15 | $0.0135 | $0.068 | -$0.068 |
| Azure Neural HD | 22 | $0.0198 | $0.099 | -$0.036 |
| Cartesia Sonic 3.6 (Startup / Pro rate) | 39.2 / 50 | $0.035 / $0.045 | $0.176 / $0.225 | +$0.04 / +$0.09 |
| Deepgram Aura-2 | 30 | $0.027 | $0.135 | 0 |
| **ElevenLabs v4 Turbo** | 40 | $0.036 | $0.180 | +$0.045 |
| **ElevenLabs v4** | 80 | **$0.072** | **$0.360** | +$0.225 |
| Fish Audio Drama 3 (list; promo to 11-30 is $10) | 50 | $0.045 | $0.225 | +$0.09 |
| Qwen-Audio-3.1-TTS-Plus (AA price) | 19.3 | $0.017 | $0.087 | -$0.048 |
| OpenAI tts-1-hd (shutting down) | 30 | $0.027 | $0.135 | 0 |
| OpenAI gpt-4o-mini-tts | $12 per 1M audio tokens | UNVERIFIED per minute | UNVERIFIED | n/a |

Reading: moving to the best-quality ElevenLabs v4 adds about 5 cents to a 1-minute video (about $0.066 to about $0.11) and 22 cents to a 5-minute video. Moving to Gemini 3.8 Flash TTS or Speechify lowers cost while raising AA preference from about 1063 to about 1290 (Gemini price doubles on 2027-01-01 to about Polly's level; Batch API or Speechify keep it low).

Credits impact: `docs/CREDITS.md` assumes voice $0.027 per minute; ElevenLabs v4 would make voice about $0.072 per minute and total about $0.085 per minute vs $0.04 plus $0.02 fixed today, which affects the credit price.

---

## 7. Recommendations (ranked)

1. **Best quality: ElevenLabs Eleven v4** (or v4 Turbo at half the price; the two are tied within error). Top two on AA overall and Knowledge Sharing, best Spanish signal in the vendor-run test, dialogue API, native character timings. Cost 1.3x to 2.7x Polly. Cons: US data storage unless Enterprise; separate account; v4 character timings should be tested; tags unreliable in places.
2. **Best value: Google Gemini 3.8 Flash TTS** (Batch for offline generation) or **Speechify Simba 3.5**. Gemini: rank 7 on AA (78 % preference over Polly), $0.0136 per minute until 2026-12-31, doubling on 2027-01-01; native style prompt, 2-speaker dialogue, no word timings (keep `align.py`); the owner already has Google Cloud. Speechify: rank 6, $0.0135 per minute, **native word timings**, free commercial tier for testing; weaker evidence for Spanish and a smaller vendor.
3. **Best for Spanish (to be confirmed by ear): Inworld Realtime TTS-2** for accent control (es-ES vs es-MX/es-419/es-AR codes, native word timings in Spanish) with ElevenLabs v4 as the quality benchmark; Gemini has es-ES GA but es-MX and es-419 only in preview.
4. **Best balance for our engine (my pick to test first): Inworld TTS-2 or Speechify Simba 3.5 for the native timings and low price, plus Gemini 3.8 Flash as the cheap alternative.** If the owner just wants the best sound and accepts the cost: ElevenLabs v4.
5. **Do not pursue:** OpenAI (shutting down), Hume, MiniMax, Chirp 3 HD, Azure Neural, Polly Long-Form (worse than generative on AA), any NC-licensed open weights, Chinese-hosted APIs unless GDPR is cleared.
6. **If nothing beats Polly by ear:** stay on Polly generative; it is the only option in-account with no key and has no timings issue we cannot handle (align.py measured 80 ms mean).

### Blind listening test (6 voices, about $1)

Voices (English and Spanish where available; hide names, randomise order, three listeners):

| # | Candidate | Setup |
|---|---|---|
| A | Polly Generative (control) | Ruth (en-US), Lucia (es-ES), Mia (es-MX) |
| B | ElevenLabs Eleven v4 | a calm narrator voice from the Voice Library (EN and ES), audio tags only where marked below. The free plan (10,000 chars) covers the test but is non-commercial: fine for listening only |
| C | Gemini 3.8 Flash TTS | voices Sulafat (warm) and Sadaltager (knowledgeable); `style`: "calm, warm explainer narrator, natural pace"; es-ES prompt "in neutral Castilian Spanish" and "in Mexican Spanish". Use a billing-enabled project, not the free tier |
| D | Cartesia Sonic 3.6 | Skylar (en-US) and a Spanish voice from the library (Spain and Mexico variants if available); Pro $5 plan or free credits |
| E | Inworld Realtime TTS-2 | a narrator voice, language `en`, `es-ES`, `es-MX`, steering "calm explainer, friendly" |
| F | Speechify Simba 3.5 | free plan (500K chars), best narrator voice per `GET /v1/audio/models` |
| optional G | Azure Dragon HD Omni (`en-us-ava:DragonHDOmniLatestNeural`) or Fish Drama 3 (promo ends 2026-11-30) | |

Generate each paragraph per beat (1 to 2 sentences, as the engine does) and also once as a whole paragraph to hear continuity differences.

**English paragraphs**
1. Explainer with numbers, acronyms and names: "In 1947, three physicists at Bell Labs built the first working transistor. It was about the size of a paperclip, yet it did the job of a vacuum tube that filled a drawer. By 1971 an Intel 4004 chip carried 2,300 of them; today a phone processor holds roughly 15 billion. That is a 6.5-million-fold increase in just over fifty years, and it is why a $200 device now outperforms a 1990s supercomputer."
2. Emotive storytelling: "The lighthouse keeper had not spoken to another person in eleven days. When the storm finally broke, he climbed the stairs one last time, and there, on the horizon, was a single small light. He whispered, 'They found us.' And for the first time in weeks, he smiled."
3. Two-speaker dialogue (use each vendor's multi-voice method): NARRATOR: "Maya asked the question everyone was thinking." MAYA: "Wait, so you're telling me the whole thing was a mistake?" DR. LIND: "A very lucky one. Penicillin exists because someone forgot to clean a dish." MAYA: "Okay, that is honestly wonderful."

**Spanish paragraphs** (run once with Spain voices and once with Latin American voices)
1. Explainer: "En 1947, tres físicos de los laboratorios Bell construyeron el primer transistor. Era del tamaño de un clip, pero hacía el trabajo de una válvula de vacío que llenaba un cajón. En 1971, el chip Intel 4004 reunía 2.300 de ellos; hoy, el procesador de un teléfono contiene unos 15.000 millones. Es decir, un aumento de 6,5 millones de veces en poco más de cincuenta años."
2. Emotive: "El farero llevaba once días sin hablar con nadie. Cuando por fin amainó la tormenta, subió las escaleras una última vez y allí, en el horizonte, vio una pequeña luz. Susurró: «Nos han encontrado». Y por primera vez en semanas, sonrió."
3. Dialogue: NARRADORA: "Maya hizo la pregunta que todos estaban pensando." MAYA: "O sea, ¿me estás diciendo que todo fue un error?" DR. LIND: "Un error muy afortunado. La penicilina existe porque alguien olvidó limpiar una placa." MAYA: "Pues la verdad es que es maravilloso."

Score each clip 1 to 5 on: naturalness, narrator warmth, pronunciation of numbers/acronyms/accents, pacing, and "would I publish this". Also have one listener check that Spanish numbers (2.300, 15.000 millones, 6,5 millones) are read correctly, and that the Latin American voice does not slip into Spain pronunciation (ceceo) or vice versa.

Cost of the test: about 3,600 characters per voice for narration plus the dialogue, roughly 25,000 characters in total; at the prices above under $1 in total (ElevenLabs free plan, Speechify free plan, Gemini a few cents).

---

## 8. Integration effort in the engine

Current design (`backend/lambdas/engine/tts.py`, `handlers/beat_handler.py`): `get_provider(name)` returns an object with `synth(text, voice, style) -> float32 mono 24 kHz array`; the beat handler stores the audio content-addressed by `hash(text, voice, style, provider)`, trims silence, then derives word timings from the waveform (`align.align_words`) and writes `audio/<hash>.words.json`. API keys come from SSM `/videomk/<provider>_api_key`; Polly is keyless via IAM. `OpenAITTS` and `GeminiTTS` already exist but are untested against real services and out of date (OpenAI is deprecated; Gemini model id `gemini-2.5-flash-preview-tts` and the `generateContent` shape are older than the 3.8 "interactions" API).

Two kinds of swap:

**A. Audio only, keep `align.py` (small)**, about half a day each: add a class to `tts.py` and register it in `get_provider`, plus an SSM key and Lambda egress.
- *Gemini 3.8 Flash TTS*: new request shape (`/v1beta/interactions`, `speech_metadata` style annotation), raw PCM 24 kHz (`audio/l16`, matches `SR`), no resampling; map `style` to the annotation; our director text must be a verbatim transcript (no stage directions in text; tags like `<short pause>` only). Needs the paid project (EEA). Effort: low.
- *Polly stays*: nothing.

**B. Native word timings (medium)**, about 1 to 2 days per provider including tests: change the interface to `synth(...) -> (samples, words|None)` (or an optional `synth_words`), have `_store_words` in `beat_handler.py` use provider words when present and fall back to `align.align_words`, and **shift word times by the amount `trim_silence` removes from the start** (otherwise captions drift by the leading silence). Provider formats:
- ElevenLabs: character start/end seconds -> group into words by whitespace on `alignment` (use `normalized_alignment` if numbers are expanded; our text-to-word mapping in `sync.py` expects the original tokens, so map by character index on the original string). Request `output_format=pcm_24000`; use `previous_text`/`next_text` (docs) to keep prosody continuous across our per-beat calls; per-request limit is not an issue.
- Inworld: `timestampInfo.wordAlignment` words (includes punctuation and whitespace tokens in order: filter to words), `wordStartTimeSeconds`/`wordEndTimeSeconds`; also gives phonemes and visemes (future lip-sync for avatars).
- Speechify: speech marks per word in ms from `/v1/audio/stream/with-timestamps` (limit 20,000 characters).
- Cartesia: WebSocket `add_timestamps` returns `word_timestamps`; requires a WebSocket client in the Lambda (the HTTP bytes endpoint may not return them; UNVERIFIED), so slightly more work.
- Azure: SDK `synthesis_word_boundary` events (needs the Azure Speech SDK or REST with SSML; extra Lambda package).

Other engine considerations when swapping:
- **Per-beat synthesis and voice continuity.** LLM-style models (Gemini, ElevenLabs v4) vary delivery between calls; the same voice and a constant short `style` string reduces drift (Google's own guidance: leave style empty or reuse one short constant string; make one call per turn). Test a 5-minute video for consistency; ElevenLabs offers `seed` and `previous_text`/`next_text`.
- **Cast and accents.** `voices.py` CATALOG is Polly-specific (names, accents). Each new provider needs its own catalogue (voice id, language, accent, gender) and a mapping for the director's region logic (`default_voice(language, region)`); budget half a day per provider for choosing voices.
- **Cost accounting** (`costs.py`, `PER_CHAR`): the new providers are billed per character (Inworld, Speechify, ElevenLabs, Cartesia credits) or per audio token (Gemini; compute from duration x 1,500 tokens per minute plus text tokens), so `cost_per_char` is not enough for Gemini.
- **Max-input guard**: Polly code truncates at 2,900 characters; set per-provider limits (Gemini 8,192 input tokens; Speechify 2,000 per `/speech` call, 20,000 stream; ElevenLabs dialogue 2,000).
- **Tests**: add `tests/fixtures/speech` samples and run `check_sync.py` against native timings to compare with `align.py`'s 80 ms mean error.
- **Edits**: the content hash includes provider and voice; switching providers re-synthesises old videos only if they are edited (no change needed).

Rough order of effort: Gemini (low, no timings) < Speechify / Inworld (medium, native timings, simple HTTP) < ElevenLabs (medium, character-to-word mapping) < Cartesia (WebSocket) < Azure (SDK).

---

## 9. Open items and things I could not verify

- Whether ElevenLabs v4 supports `with-timestamps`; Cartesia timestamps over plain HTTP; Gemini 3.8 word timings (none documented).
- Spanish quality for every vendor (no neutral benchmark); Fish Drama 3, Qwen, StepAudio Spanish and timestamps.
- OpenAI gpt-4o-mini-tts per-minute cost and max input length; whether `gpt-realtime-2.1-mini` can be used for plain narration.
- Polly generative price in eu-west-1; Polly generative availability of Spanish voices in the stack's region.
- Deepgram Aura-2 Spanish voices and timings; Play.ht status.
- Azure Dragon HD Omni Spanish voices and `express-as` in Spanish.
- Vendor watermarking and AI-disclosure terms (ElevenLabs Prohibited Use Policy, Google, Cartesia): read before launch.
- The EU AI Act audio-marking duty: confirm with counsel.
- AA prices for Speechify ($6.58) and Fish ($15) are lower than the vendors' current list prices ($15 and $50); I used the vendors' list.

## 10. Sources read (all fetched 2026-11-27)

Primary: `artificialanalysis.ai/text-to-speech/leaderboard` (and `/leaderboard/controlled-voice`, `/text-to-speech`); `developers.openai.com/api/docs/guides/text-to-speech`, `/pricing`, `/deprecations`; `elevenlabs.io/pricing/api`, `/docs/overview/models`, `/docs/overview/capabilities/text-to-speech`, `/eleven-v4`, `/text-to-dialogue`, `/docs/api-reference/text-to-speech/convert-with-timestamps`, `/docs/overview/administration/data-residency`, `/terms-of-use`; `cloud.google.com/text-to-speech/pricing` and `/docs/gemini-tts`; `ai.google.dev/gemini-api/docs/speech-generation`, `/pricing`, `/models/gemini-3.8-flash-tts`, `/terms`; `aws.amazon.com/polly/pricing`, `/polly/features`; `docs.aws.amazon.com/polly/latest/dg/generative-voices.html`, `/speechmarks.html`, `/long-form-voices.html`; `aws.amazon.com/about-aws/whats-new/2026/03/amazon-polly-expands-TTS-new-voices-and-bidirectional-streaming`; Azure Retail Prices API (`prices.azure.com/api/retail/prices`) and `learn.microsoft.com/azure/ai-services/speech-service/high-definition-voices`; `cartesia.ai/pricing`, `docs.cartesia.ai` (Sonic 3.6, WebSocket reference); `inworld.ai/pricing`, `docs.inworld.ai/tts/tts-models.md`, `/capabilities/timestamps.md`, `/capabilities/multilingual`; `speechify.ai/text-to-speech-api`, `docs.speechify.ai`; `docs.fish.audio/.../pricing-and-rate-limits.md`; `deepgram.com/pricing`; `docs.mistral.ai/.../text_to_speech`; Hugging Face model cards (Kokoro, Orpheus, Dia, F5-TTS, Chatterbox, CSM, Qwen3-TTS, Voxtral); `platform.claude.com/docs/llms.txt` and the Anthropic cookbook ElevenLabs page.

Secondary: The Decoder, eWeek, 9to5Mac, Simon Willison (Anthropic voice); Speko benchmarks page and data (vendor-run); Gradium WER post; eesel/mindstudio/oflight/magica (Fish licence); activepieces/eesel/usagepricing (Hume, StepFun, Alibaba pricing); DeepInfra (Chatterbox hosted); law-firm notes (Goodwin, Ropes & Gray, Taylor Wessing) on the EU AI Act timeline; AWS Marketplace listings and Nova release notes via search.
