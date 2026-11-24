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
