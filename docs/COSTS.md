# What a video costs (measured 2026-11-24 on QA, 59 videos)

Run `python backend/scripts/cost_report.py [--since 2026-11-24] [--user <id prefix>] [--hours 24]` at any time. It reads the videos table and CloudWatch.

| | videos | mean | median | range |
|---|---|---|---|---|
| completed, about 1 minute (4 beats) | 41 | **$0.048** | $0.044 | $0.026 - $0.101 |
| completed, about 3 minutes (13 beats, news/research) | 12 | **$0.121** | $0.125 | up to $0.172 |
| failed run (credits refunded) | 3 | $0.048 | | |

Add about **$0.025 of Lambda compute per video** (96 % of it is the render chunks; measured from CloudWatch: 78,000 GB-s for 57 videos in 24 h, edits and failed runs included). All-in: roughly **$0.07 per 1-minute video and $0.15 per 3-minute video**. Step Functions, S3, DynamoDB and Cognito are under a tenth of a cent per video. A credit is one started minute, so the cost per credit is about $0.07 for short videos and $0.05 for long ones.

## Where it goes
Videos now carry their own breakdown (`c_speech`, `c_script`, `c_research`, `c_photos`, `c_stock` next to `cost_usd`). Two examples:
- 1-minute Christmas-market video, $0.066: script's language model (Sonnet 5.5) $0.035, Polly generative speech $0.029, stock photo/clip reviews and checks (Haiku 5.5) $0.002.
- 1-minute Tiber video with web research, $0.115: script $0.049, web research (Tavily searches and the research model) $0.034, speech $0.030, reviews $0.002.
Speech is about $0.03 per minute of narration (Polly generative, $30 per million characters, about 900 characters a minute) and is the largest fixed cost; the script's model is next; reviews of photos and clips are almost free.

## Not counted
Bedrock and Polly prices are list prices in the code (`llm.DEFAULT_PRICES`, `tts.PollyProvider.PER_CHAR`); Tavily is $0.008 per search by assumption; Unsplash, Pixabay and Wikimedia calls are free. Data transfer to phones and storage (see `docs/STORAGE.md`) are not in the table.

## Paid dictation (speech-to-text), planned 2026-11-28
Details and evidence: `docs/SPEECH_TO_TEXT_2026-11-28.md`. For Pro and Max the dictated video request would go to OpenAI `gpt-transcribe`, **$0.0045 per minute of speech** (OpenAI's pricing page, read 2026-11-28; Free keeps the phone's own engine at no cost to us).
- Per video: **1 minute $0.0045, 3 minutes $0.0135, 5 minutes $0.0225** (about 3 to 15 % of a $0.15 credit). New cost field `c_stt` next to `c_speech`, added to `cost_usd`; every dictation attached to the video is charged to it, retries included.
- 1,000 paying users, 20 videos a month, 70 % dictated, 1.3 retries: $82 (1 min), $246 (3 min), $410 (5 min) a month, 0.4 to 2 % of about $20,000 revenue.
- Live (streaming) words would cost 3.8 times as much ($0.017 a minute); not planned. Caps (decided 2026-11-28, `docs/SPEECH_TO_TEXT_2026-11-28.md` section 8): Pro 600 s, Max 1,200 s a day; worst case a user maxes every day for 30 days: Pro $1.35 (9 % of $14.99), Max $2.70 (7 % of $39.99). Built on branch `paid-dictation` (not deployed): `c_stt`/`stt_seconds` on the video row via the create request's `dictation_ids`.
- Tested 2026-11-28 on 5 languages (clips from Polly): about $0.03 of API calls in total.

## Video upload (the person's own 5-second clips), built 2026-11-28
Details: `docs/VIDEO_UPLOAD_2026-11-28.md` section 7. List prices in the code (Haiku 5.5 $0.10 / $0.50 and Sonnet 5.5 $2 / $10 per million tokens in `llm.DEFAULT_PRICES`, `gpt-transcribe` $0.0045 a minute, Lambda $0.0000166667 per GB-s). Every stage is recorded on the clip as `c_vidup` (`cost_parts`: vision, describe, stt, text, compute); the first video that uses a clip carries it in `c_vidup` and `cost_usd`.
- **Per clip, expected: $0.0013 without the clip's sound, $0.0024 with it.** Vision safety check on one contact sheet $0.0004 + description $0.0005 + transcription of at most 5 s $0.000375 + the text safety check of the transcript about $0.0006 + 6 to 10 s of a 2 GB function $0.0003; S3 and DynamoDB are under $0.0001.
- **Per clip, worst case: $0.03** (what the budget guard reserves before each analysis): both model calls on Sonnet 5.5 prices with long answers, transcription, text check and the full 120 s timeout of the function.
- At the caps, every day for 30 days, at the expected cost with sound on every clip: Free 90 clips $0.21, Pro 300 clips **$0.69 (4.6 % of $14.99)**, Max 750 clips **$1.73 (4.3 % of $39.99)**. At the reserved worst case: Free $2.70, Pro $9.00, Max $22.50 (never reached in practice; the global ceiling below stops it first).
- Hard stops: per-plan clips a day (Free 3, Pro 10, Max 25), clips per video (2 / 4 / 6), one analysis per clip, never twice for the same file (content hash), a global daily ceiling of **$5 reserved at $0.03 a clip** (knob `vidup_global_daily_usd`), kill switches `vidup_enabled` and `stop_video_upload`.
- Rendering a clip costs no more than a stock clip (one local decode); mixing its sound is one more ffmpeg input (under a second). Not metered separately: the render stays in `cost_usd`; `c_render` does not exist in the code, so transcode compute is inside `c_vidup`.
