# Creation options: where each option travels (platform, aspect, resolution, captions, language, brief)

Contract: `docs/CREATE_API.md`. Design: `docs/PIPELINE_V3.md` sections 6 and 7, `docs/UI_DESIGN.md` (o). Geometry: `engine/frame.py` (design units, 720p is a 2/3 scale).

## Pixel table (short side 720, 1080 or 2160)
| aspect | 720p | 1080p | 2160p (4K) |
|---|---|---|---|
| 16:9 | 1280x720 | 1920x1080 | 3840x2160 |
| 9:16 | 720x1280 | 1080x1920 | 2160x3840 |
| 1:1 | 720x720 | 1080x1080 | 2160x2160 |
| 4:5 | 720x900 | 1080x1350 | 2160x2700 |
Draft (preview) renders are half size rounded to an even number (4:5 at 1080p: 540x674) because yuv420p needs even sides; the draft of a 4K video is the same size as the draft of a 1080p one. A test checks the table. 4K (how it is rendered, what it costs, how it is switched on): `docs/FOUR_K.md`.

## Path, file by file
1. `backend_stack.py`: the generate request model accepts `platform`, `aspect`, `resolution` (enums), `language` (`auto` or two letters), `brief` (object). `additionalProperties` is unchanged. A `RequestOptions` block (one call) adds the capabilities route.
2. `request_options.py` (construct) + `lambdas/capabilities_api.py`: `GET /users/{user_id}/capabilities`, Cognito, path user must be the token user (403 otherwise), no data access, no IAM beyond logs. The body is built by `engine/format_options.capabilities()`. It also gives the launcher the same settings (env).
3. `lambdas/sf_launcher.py` `validate_options`: strict 400 messages; a format or language that is not ready: 400 `This format is not available yet` / `This language is not available yet`. `brief` is cleaned by `common/intake.clean_brief` (handler, owned by the intake work). All options are in the duplicate fingerprint and in the state machine input. Only fields the client sent are forwarded (no new field: input identical to before). Credits depend on length only.
4. `engine/handlers/plan_handler.py`: `language` `auto` is detected, an explicit one overrides; `platform`/`aspect`/`brief` go to `director.direct(options=...)` which appends `plan.frame_prompt(options)` (empty for plain 16:9) to the craft guides; the plan stores `plan["frame"]` = `{aspect, resolution, width, height, orientation, platform}` and `plan["captions"]`.
5. Everything after the plan reads the plan or timeline, not the Step Functions input: `timeline_handler` builds the timeline at `frame_of(plan)` size and stores `tl["frame"]`; `chunk_plan` hashes width and height (two sizes never share cached segments); `chunk_timeline` carries `frame`; `render_chunk_handler` -> `pipeline.render_chunk` -> `Renderer` (canvas = timeline size, draft = half, even) -> `media.encode_segment(width, height)`; `finalize_handler` stores `aspect`/`resolution` on the video item (returned by the list route so apps can size players); the preview GIF keeps the video's shape (320 wide).
6. Edits: the plan keeps its `frame` through every edit op (deep copy), so `edit_prep` -> `timeline_handler` re-render at the original size. `editor_get` returns `frame`. A plan with no `frame` (made before this) means 16:9 1080p.

## Switching a format on (server settings, no code change)
Not-ready formats are refused by `generate` and shown `ready: false` by capabilities.
`cdk deploy videomk-qa -c stage=qa -c engine=v2 -c readyAspects=16:9,9:16 -c betaAspects=9:16`
* `readyAspects`: comma list (default `16:9`) -> env `READY_ASPECTS` on the capabilities and launcher Lambdas.
* `betaAspects`: ready formats still using a framed fallback for some scenes -> `beta: true`.
* `readyLanguages`: default `en,es`. `intakeEnabled=1` -> `intake: true`.
* `readyResolutions`: comma list (default `720p,1080p`) -> env `READY_RESOLUTIONS`. Add `2160p` to offer 4K: capabilities then lists it and `generate` accepts it (at double credits); without it a 4K request is a 400 `This resolution is not available yet`. The deploy refuses 4K on a stage whose functions are capped below 10 GB of memory (`docs/FOUR_K.md`).
Both Lambdas get the same values from the same context keys, so they cannot disagree. Context keys must be passed on every deploy (cdk.context.json can hold them for a stage).

## Platform recommendations: what was verified
Searched official pages 2026-11-25. YouTube Shorts: Google Ads help says 9:16 at 1080x1920 is recommended for Shorts (verified). LinkedIn: its ad help page lists 16:9, 1:1, 4:5 (recommended for vertical) and 9:16 as supported; for organic posts only third-party sources, so LinkedIn stays 16:9 with a note that 1:1 and 4:5 work. Instagram feed 4:5 1080x1350 and Reels/TikTok 9:16: only third-party guides found (no official page retrieved). X 16:9: not verified from an official page. Treat these as defaults, they are changeable in `engine/format_options.PLATFORMS`.


## Platform length and format recommendations (2026-11-25, short videos)
Each platform now carries `recommended_minutes` (a preset), `max_minutes` (soft limit or null), `other_aspects` and a note "Shape ratio · 1080p · about N". They are defaults for the app; the length the person picks always wins, and `frame_prompt` tells the director the platform's default and style in one line (never the limit).

| Platform | Format | Recommended | max_minutes | Other aspects |
|---|---|---|---|---|
| YouTube | 16:9 1080p | 3 min | none | 1:1, 4:5 |
| YouTube Shorts | 9:16 1080p | 45 s | 3 | 1:1 |
| TikTok | 9:16 1080p | 30 s | 30 | 1:1 |
| Instagram Reels | 9:16 1080p | 30 s | 3 | 4:5, 1:1 |
| Instagram feed | 4:5 1080p | 30 s | none | 1:1, 9:16, 16:9 |
| LinkedIn | 4:5 1080p | 1 min | 10 | 1:1, 16:9 |
| X | 16:9 1080p | 45 s | 2.33 (2:20) | 1:1, 9:16 |
| Just a video | 16:9 1080p | 3 min | none | 9:16, 1:1, 4:5 |

Sources checked (searches of the official help centres, 2026-11-25) and doubts:
* YouTube Shorts: help.google.com "Understand three-minute YouTube Shorts": vertical or square videos up to 3 minutes are Shorts (since 15 Oct 2024). Verified. 45 s is our editorial choice (the feed is built for under a minute; music licences allow up to 60 or 90 s).
* Instagram Reels: the current help article says reels can be up to 20 minutes but reels over 3 minutes are not recommended to new audiences; an older help page and the Reels marketing page still say 3 minutes. We keep 3 as the soft limit because it is the recommendation boundary. Feed video has no limit we could confirm, so null.
* TikTok: the support page says uploads can be up to 30 minutes (the in-app recorder offers 15 s, 60 s and 10 min). The owner's figure was 10 minutes; the official upload limit is higher, so `max_minutes` is 30. 720x1280 or higher is the stated minimum.
* LinkedIn: the sources disagree. Help for Pages says up to 10 minutes and 1:2.4 to 2.4:1 (any ratio between); another help article says 15 minutes on desktop and 10 on the mobile app; the ads help recommends 4:5 for vertical and lists 16:9, 1:1, 4:5, 9:16 for ads, 15 to 30 seconds. We use 4:5 (most screen in the mobile feed), 1:1 and 16:9 as alternatives, and 10 minutes as the soft limit (the lower figure).
* X: the help page says accounts without Premium can upload videos up to 140 seconds (2:20), 512 MB; aspect ratio 1:2.39 to 2.39:1. Ads: 2:20, recommending 15 s or less. Verified. Premium accounts can upload much longer videos, so `max_minutes` 2.33 is for standard accounts only.
* Instagram feed 4:5 1080x1350 and 1080p everywhere remain third-party recommendations (no official page retrieved earlier). Retune in `engine/format_options.PLATFORMS`.
