# Video upload: what the web, iOS and Android apps do (spec, 2026-11-28)

Backend and rules: `docs/VIDEO_UPLOAD_2026-11-28.md`. Nothing here is built yet. Wording is English; keep it this simple. Spanish strings follow the same keys later (the server already sends localized `message` for errors: show it as is).

## 1. When to show it
Read `GET .../capabilities` → `video_upload`. Show **"Add a video"** next to "Add photos" only if `enabled`. If `available` is false: keep the button, disabled, and show the reason: `paused` → "Adding videos is paused for a while. Photos still work."; `clips_left_today` 0 → "You have added today's video clips. They come back tomorrow."; `requires_plan` set → the plan name on the tile. Send clip requests to `video_upload.api_url` (not the main API) with the same token.

## 2. Picker
Web: file input, `video/mp4, video/quicktime, video/webm`. iOS: PHPicker (videos only), export the original or a medium-quality version; Android: Photo Picker (video only). Offer the **camera** too (record, max 5 s is not forced: the server trims). Before any upload, check locally: file size ≤ `max_bytes` (25 MB), type in `formats`; else show "That video is too large. The limit is 25 MB." (iOS/Android: re-export at medium quality first, then check again). Do not trim on the phone; do show the notice below.

## 3. The two questions (one sheet, shown before upload starts)
1. Notice, always: **"Only the first 5 seconds of a video are used."** If the picked file is longer than 5 s (the apps can read the length), add the length: "Your video is 18 seconds. We will use the first 5." Optional preview that marks the 5-second point.
2. **"Use this video's own sound?"** buttons: **"Yes, use its sound"** / **"No, silent"**. Helper line under Yes: "We turn the words into text so the video can follow your story. Only use sound you are happy to share." Hide the question (silent) if the app can see the file has no audio track. The choice is sent as `use_audio` and cannot be left empty. Default selection: none (the person must tap).
Then **"Add video"**.

## 4. Upload and progress (three steps, one progress bar)
1. `POST /video-uploads {size_bytes, content_type, use_audio, sha256}` (compute SHA-256 of the file; on `200 duplicate` skip to the end: the clip is already ready). 
2. POST the file to `upload.url` with `upload.fields` (form fields first, `file` last), show real upload progress ("Uploading 42%").
3. `POST .../{id}/analyse`, then poll `GET .../{id}` every 1.5 s (back off to 3 s after 20 s, give up after 90 s with "This is taking longer than usual. We will keep checking. You can leave this screen."). Label while analysing: **"Checking your video..."** (never "scanning" or anything alarming).
Keep the pending clip in the media strip with the poster-less placeholder and a spinner; on `ready` show `thumb_url` (signed, 15 minutes: re-fetch the clip to get a fresh link, do not cache it) with the length badge "5 s".

## 5. States and exact wording
| Server | Show |
|---|---|
| `ready` | the clip with its poster and "5 s". If `trimmed`: small note "First 5 seconds used". If `audio_used`: a speaker icon and "Sound on". If `use_audio` was yes but `audio_state` is `unscreened` or `unavailable`: "We used your video without its sound." |
| `rejected` (code `rejected`) | "We could not use this clip. Please choose a different one." (never say why; no appeal button here; link to Help) |
| `failed` (code `check_failed`) | "We could not check that clip this time. Please try again." with **Try again** (a fresh upload; it does not count against today's clips) |
| 413 `too_big` | "That video is too large. The limit is 25 MB." |
| 400 `bad_request` | "We could not use that video. Try another one, or record it again." |
| 429 `video_upload_quota` | "You have added today's video clips. {plan} allows more. They come back tomorrow." (plan line only when `can_upgrade`) |
| 503 `video_upload_paused` | "Adding video clips is paused for a while. Photos still work." |
| 403 `video_upload_plan` | the plan's paywall |
| 429 `paused` / safety body | the same account message as video creation |
| network error during upload | "The upload stopped. Check your connection and try again." with **Try again** (new slot; the old pending record expires on its own) |
Use the server's `message` when it sends one. Never show codes or raw errors.

## 6. Using clips in a video
In the create screen the media strip can hold photos and clips; a clip is a tile with the poster and a "5 s" badge. At most `clips_per_video` clips (message from the server, 400 plan error: "{plan} lets you use more video clips in one video."). Send the ready ids as `video_assets` in `POST /videos`. A clip that is not ready cannot be selected (disabled tile with the spinner). Tell the person what will happen once, under the strip: "Your clips are used for up to 5 seconds each, where your story talks about them." Do not offer placement controls in v1 (the planner decides; the editor shows the clip scene like other clips).
Show clips in My media? Not in v1 (clips expire after 14 days unless used; a video that uses one keeps its own copy). The strip lists `GET /video-uploads` for the last 14 days ("Recent clips").
**Delete**: long-press / swipe on a clip tile → "Remove video" → `DELETE`. A video already made keeps its copy.

## 7. Privacy lines (settings and the sheet)
"We check your video for safety. We keep a small 5-second copy so we can use it in your videos. The original is deleted straight away. Copies you do not use are deleted after 14 days." If sound is used: "If you choose sound, we turn the words into text with OpenAI (see our privacy page)."

## 8. Accessibility and layout
Buttons and tiles ≥ 44 pt; the sheet is a bottom sheet on phones and a dialog on web; progress is announced ("Uploading", "Checking your video", "Ready"); the speaker and "5 s" badges have text labels. Portrait and landscape files both appear at their own shape in the tile (no stretching).

## 9. Tests the apps need
Picker + size limit; the two questions cannot be skipped; the hash shortcut (`duplicate`); each state of section 5 with a mock; poll timeout; a longer-than-5-second file shows the notice; `video_assets` is sent only with ready ids; kill-switch and quota states disable the button with the right text; token and `api_url` from capabilities.
