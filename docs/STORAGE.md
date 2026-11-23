# Storage: what a video leaves behind and what it costs (measured on QA, 2026-11-23)

S3 Standard is about $0.023 per GB-month. Measured on 36 QA videos (mostly 1 minute): final videos 374 MB (about 9-10 MB per minute),
working files in `generation/v2/` 535 MB (about 14 MB per video): video segments 329 MB (a second copy of the video), narration audio 108 MB,
audio mixes 65 MB, photos and plans under 8 MB. Before 2026-11-23 nothing ever expired.

## Policy now (bucket lifecycle, `backend_stack.py`)
| What | Rule | Why it is safe |
|---|---|---|
| Video segments (`segments/*.ts`) and audio mixes (`audio/mix_*`) | tagged `retention=working` by the engine, deleted after 7 days | an edit re-renders missing segments (they are cached by content hash) and rebuilds the mix on every render; verified on QA by deleting them and editing |
| Finished videos (`videos/`) | S3 Intelligent-Tiering from day 0: about 45% cheaper after 30 days unwatched, about 83% after 90 days, still instant, no retrieval fees | none needed |
| Narration audio, photos, plans | kept | an edit does not rebuild missing narration yet (the engine only checks the audio's hash, not that the file exists) and photos are referenced by the plan |

Never put the `working` tag on anything an edit cannot rebuild itself (`awsio.upload(..., working=True)` is for segments and mixes only; a test
enforces it).

## Numbers (estimates)
Per minute of video: before about 23 MB kept (9.5 final + 14 working); after the first week about 13 MB (9.5 final + 3 narration + photos).
A 3-minute video kept a year: about $0.019 before, about $0.005 now. At 1,000 three-minute videos a day: about $590 a month by the end of the
first year before (25 TB), roughly $140-210 a month now. Compared with making a video ($0.14 for 3 minutes), storage is small per video; it only
matters because it grows without limit.

## Next levers
1. Store narration compressed (m4a or opus, about a tenth of the size of wav) and make the engine rebuild missing narration, then expire it too.
2. A retention policy for free accounts (for example delete after 6 to 12 months with notice). With Intelligent-Tiering a 28 MB video costs
   about $0.0001 a month once archived, so this is optional, not urgent.
3. Account deletion must delete `videos/<user>/` and every `generation/v2/<video>/` of that user (required by the stores anyway).
4. Data transfer out is about $0.09 per GB after the first 100 GB a month: a full watch of a 3-minute video is about $0.0025. If watching
   grows, serve videos through CloudFront (its first 1 TB a month is free).
