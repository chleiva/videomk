# Creating a video: request check, options and capabilities (contract, decided 2026-11-25)

Owner decisions: a 15-45 s video still costs 1 credit (`MIN_MINUTES = 1`); vertical, square and 4:5 formats are being made to work now; **safety checks stop the video** (nothing is charged) and repeated violations are tracked per account; the planner may add about $0.03 and 25 s to a 3 minute video if the audit shows a quality gain; the owner reviews Spanish videos. Background and reasoning: `docs/PIPELINE_V3.md`, UI: `docs/UI_DESIGN.md` section (o).

## Creation options (all optional; absent means today's behaviour)
Sent in the body of `POST /users/{user}/videos/generate` next to `prompt`, `target_minutes`, `theme`, `captions`, `media`, `library_media`, `media_meta`, `max_images_per_minute`:
| Field | Values | Default | Meaning |
|---|---|---|---|
| `platform` | `youtube`, `shorts`, `tiktok`, `reels`, `instagram_feed`, `linkedin`, `x`, `other` | `other` | What the video is for. Only informs recommendations and the director's pacing; the format fields decide the picture. |
| `aspect` | `16:9`, `9:16`, `1:1`, `4:5` | `16:9` | Frame shape. |
| `resolution` | `720p`, `1080p` | `1080p` | The short side in pixels is 720 or 1080: 16:9 is 1280x720 or 1920x1080, 9:16 is 720x1280 or 1080x1920, 1:1 is 720x720 or 1080x1080, 4:5 is 720x900 or 1080x1350. |
| `captions` | boolean | true | Burned-in subtitles. |
| `language` | `auto`, or a language id from capabilities (`en`, `es`) | `auto` | Narration language; `auto` = the language of the description (today's detection). |
| `brief` | object (see below), at most 2 KB | none | The answers to the clarifying questions, passed to the planner/director. |
An unknown value is a 400 with a plain message. `aspect`/`resolution` not listed as `ready` in capabilities are refused with 400 ("This format is not available yet"). Credits depend on length only (not on format).

## Capabilities
`GET /users/{user}/capabilities` (authenticated) -> what the apps may offer; the apps must work with only what is listed.
```json
{"aspects": [{"id": "16:9", "label": "Landscape", "ready": true, "beta": false}, {"id": "9:16", "label": "Vertical", "ready": true, "beta": true}],
 "resolutions": [{"id": "720p", "label": "720p"}, {"id": "1080p", "label": "1080p"}],
 "platforms": [{"id": "linkedin", "label": "LinkedIn", "aspect": "4:5", "resolution": "1080p", "recommended_minutes": 1, "max_minutes": 10, "other_aspects": ["1:1", "16:9"], "note": "Portrait 4:5 · 1080p · about 1 min"}, ...],
 "languages": [{"id": "en", "label": "English"}, {"id": "es", "label": "Español"}],
 "lengths": {"min_minutes": 0.25, "max_minutes": 12, "presets": [0.25, 0.5, 0.75, 1, 2, 3, 5, 8, 12]}, "max_photos": 100, "intake": true}
```
**Lengths.** `target_minutes` is a number from 0.25 (15 s) to 12; `presets` are the chips to show (15 s, 30 s, 45 s, 1 min, 2 min ...). Credits are the started minutes, at least 1: 15, 30, 45 and 60 seconds cost 1 credit, 61 seconds costs 2. Under a minute the engine writes a short-form script (about 2 to 4 beats, hook in the first 2 seconds), see `docs/SHORT_VIDEOS.md`.

**Platform fields.** `aspect` and `resolution` are the recommendation; `recommended_minutes` (always one of the presets) is the length the app should preselect when the person picks the platform (the person may still choose any length: the chosen length always wins in the engine); `max_minutes` is the platform's soft limit (null = none), for a hint such as "TikTok videos can be longer, but 30 s works best"; `other_aspects` are acceptable alternatives to show as secondary choices; `note` is the one-line text under the chips ("Portrait 4:5 · 1080p · about 1 min"). Sources and doubts: `docs/CREATE_OPTIONS_FLOW.md`. Everything is server-driven.

`beta: true` means it works but not every scene has a native layout yet (a framed fallback is used for those scenes).

## Request check (intake)
`POST /users/{user}/videos/brief` (authenticated), called by the app when the person taps Create, BEFORE `generate`. Nothing is charged here.
Request: `{"prompt": "...", "options": {platform, aspect, resolution, captions, language, target_minutes}, "media_count": 0, "answers": [{"id": "audience", "option": "kids"} | {"id": "tone", "text": "warm"} | {"id": "focus", "skip": true}]}` (`answers` empty on the first call; on later calls it holds ALL answers so far).
Response (always HTTP 200 unless noted; the app treats any failure or a response slower than 8 s as `ok` with no brief):
* `{"status": "ok", "brief": {...}}` : proceed; send `brief` in `generate`.
* `{"status": "questions", "questions": [{"id": "audience", "text": "Who is this for?", "options": [{"id": "kids", "label": "Kids"}, ...], "allow_other": true}, ...]}` : at most 3 questions, each with 2 to 5 options, each answerable by one tap; the app shows them one at a time with Skip / 'You decide' and 'Make it now'. Questions are asked only when the answer would change the video materially and are never about things the form already captures (platform, format, length, captions, language, look). Clear requests get `ok` with no questions.
* `{"status": "not_supported", "message": "...", "suggestion": "..."}` : the request cannot be made well here (unsupported language, impossible format, not something a video can be); kind and short; nothing was charged.
* `{"status": "blocked", "message": "..."}` : safety stop. Neutral wording, no lecture, never names the policy detail; nothing was charged; recorded against the account.
* HTTP 429 `{"status": "paused", "message": "...", "retry_after": 3600}` : the account is temporarily paused after repeated safety stops (see Safety).
Question `id` is one of `audience`, `tone`, `focus` (which meaning, angle or period), `details` (a missing personal detail); an option's `id` is its label lower-cased with underscores (`complete_beginners`), so the answers carry all state. An option answer sets the field of its question id; free text on its own sets that field too; free text next to an option, or any text on `details`, goes to `notes`; `skip` adds nothing. Answers that are only option taps are merged without a model call. Invalid input (unknown id, bad option, text over 200 characters, more than 8 answers) is HTTP 400 `{message}`.
`brief` object (what `generate` accepts, validated server side by `common/intake.clean_brief`: an object of at most 2 KB, else 400; unknown keys dropped, `summary` recomputed; may be `{}` when nothing was asked): `{"audience": "kids", "tone": "calm", "focus": "causes", "notes": "free text from Other (<= 200 chars)", "summary": "For kids · Calm · Focus: causes"}`; every value is a short string.

## Safety (owner decision: a safety stop stops the video)
* Both `brief` and `generate` run the safety check on the request (the app cannot skip it by calling `generate` directly); a `blocked` verdict means no video, no charge, HTTP 400 `{"status": "blocked", "message": "..."}` from `generate`.
* Every block is recorded per account with a category, a time and a short excerpt kept 90 days (for review and abuse tracking; disclosed in the privacy policy). Zero-tolerance categories put the account on hold at once; otherwise 3 blocks in 24 h pause creation for 24 h, 8 in 30 days hold the account for review. A hold or pause returns 429 `paused`; staff clear it with `scripts/safety_admin.py`. `generate` also returns 429 `{status, message, retry_after}` with a `Retry-After` header. Details, thresholds and procedures: `docs/INTAKE_AND_SAFETY.md`. Log lines `SAFETY_STRIKE` and `SAFETY_HOLD` carry the account id and category only.
* If the model check cannot run, a deterministic screen of obvious terms decides; the director's own `legit` check remains a backstop.
