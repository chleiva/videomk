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

## Cost levers, 28 Nov 2026 (docs/COST_LEVERS_2026-11-28.md, not deployed)
- **Whiteboard plans cost $0.14 to $0.33** (measured): a script call of $0.064, a trim retry that thinks to the output limit and is thrown away ($0.12, in 2 of 3 plans), a board review ($0.04 to $0.10). Normal 60 s plan: one script call of $0.043 (two with a retry).
- **Prompt caching** of the first 8,239 tokens of the script prompt (same in every language and look) on Bedrock for Sonnet 5.5: a cache read saves $0.0157 a call, a write costs $0.0041 extra. Normal 60 s plan: $0.086 off, $0.073 on (cold, with a retry), $0.049 on (warm). Switch `PROMPT_CACHE=off`; falls back by itself if a model rejects it. `cache_read_tokens` / `cache_write_tokens` on the video; `c_script` includes the cached-token prices.
- **`c_render` / `render_gbs`** on the video: the render chunks' GB-seconds x $0.0000166667, estimated; not in `cost_usd` (its cap would trip on long 4K videos); the plans economics should use `cost_usd + c_render`.
- **HD render on a 4,096 MB function** (4K stays 10,240 MB): estimated $0.07 -> $0.028 a minute, to be proven on QA first (`-c hdRenderMemoryMb=0` turns it off).
