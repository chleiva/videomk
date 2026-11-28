# Video upload on the web (Create composer), built 2026-11-28

Spec: `docs/VIDEO_UPLOAD_CLIENTS_2026-11-28.md`. API: `docs/VIDEO_UPLOAD_2026-11-28.md`. Branch `video-upload-web`, frontend only.

## What it does
- **Entry**: the Add menu in the composer ("Add photos or a video") gets "Add a video", "Record a video" (touch devices) and "Recent clips" (GET /video-uploads, last 14 days), only when `capabilities.video_upload.enabled`. A locked item shows its reason (paused / no clips left today / plan). Files can also be dropped or pasted on the card.
- **Dialog** (`ClipSheet.tsx`, before any upload): the "first 5 seconds" notice (with the real length when longer), the sound question with NO default and the one-line transcription explanation, the privacy lines. Hidden (silent) only when the browser can see there is no audio track. Pre-checks: type, size (25 MB from caps), absurd length (> 600 s).
- **Large file** (over `max_bytes`): `localVideo.trimClip` plays the first 5 s through `captureStream` + `MediaRecorder` (WebM, or MP4 in Safari) and uploads that, with a progress bar and Cancel. Where the browser cannot, it is blocked with "That video is too large. The limit is 25 MB." A 35 MB / 12 s file became a 2.3 MB WebM in Chrome.
- **Upload** (`videoClips.ts` ClipUploader, network injected): sha256, POST /video-uploads `{size_bytes, content_type, use_audio, sha256}`, `duplicate` shortcut, presigned POST with progress, POST analyse, poll 1.5 s / 3 s after 20 s, "taking longer" line at 90 s (keeps checking, gives up at 10 min), Try again = fresh slot, remove = abort + DELETE.
- **States** in the same attachment strip as photos: tile in the clip's own shape, play badge, "5 s" chip, speaker badge ("Sound on"), % while uploading, spinner while checking, "!" on failure, x remove. Notes under the strip: status line, reasons with Try again / Remove / Help, "First 5 seconds used", "We used your video without its sound." Rejected never says why. Server `message` is shown as is; our own EN/ES sentence otherwise (503 `video_upload_paused`, 429 quota, 403 plan, 413, 400, safety pause, network).
- **Create**: ready ids go as `video_assets` (not with a deck); Create waits while a clip is busy; the create request key includes them, so idempotency is unchanged. Clips count as own footage for the look reset.
- **A11y**: dialog trap and Escape (shared Sheet), native radios with visible focus ring, live-region announcements only on state changes, 44 px targets, reduced motion (fade only), light/dark, 320 px.

## Deviations and notes
- "Audio on/off toggle" on the tile is a badge, not a toggle: `use_audio` is fixed at upload (it is part of the hash and the slot), so changing it means a new upload.
- Fixed a base bug: `.app-shell .compose > :not(.compose-aura)` forced `position: relative` on any sheet child of the composer, so every sheet there (My media picker, questions) rendered in the page flow instead of over it.
- QA capabilities currently report `video_upload.enabled: false, api_url: null` (main stack not redeployed with `-c videoUpload=1`); the web shows nothing until it does.
