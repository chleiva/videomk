# Creation options: where each option travels (platform, aspect, resolution, captions, language, brief)

Contract: `docs/CREATE_API.md`. Design: `docs/PIPELINE_V3.md` sections 6 and 7, `docs/UI_DESIGN.md` (o). Geometry: `engine/frame.py` (design units, 720p is a 2/3 scale).

## Pixel table (short side 720 or 1080)
| aspect | 720p | 1080p |
|---|---|---|
| 16:9 | 1280x720 | 1920x1080 |
| 9:16 | 720x1280 | 1080x1920 |
| 1:1 | 720x720 | 1080x1080 |
| 4:5 | 720x900 | 1080x1350 |
Draft (preview) renders are half size rounded to an even number (4:5 at 1080p: 540x674) because yuv420p needs even sides. A test checks the table.

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
Both Lambdas get the same values from the same context keys, so they cannot disagree. Context keys must be passed on every deploy (cdk.context.json can hold them for a stage).

## Platform recommendations: what was verified
Searched official pages 2026-11-25. YouTube Shorts: Google Ads help says 9:16 at 1080x1920 is recommended for Shorts (verified). LinkedIn: its ad help page lists 16:9, 1:1, 4:5 (recommended for vertical) and 9:16 as supported; for organic posts only third-party sources, so LinkedIn stays 16:9 with a note that 1:1 and 4:5 work. Instagram feed 4:5 1080x1350 and Reels/TikTok 9:16: only third-party guides found (no official page retrieved). X 16:9: not verified from an official page. Treat these as defaults, they are changeable in `engine/format_options.PLATFORMS`.
