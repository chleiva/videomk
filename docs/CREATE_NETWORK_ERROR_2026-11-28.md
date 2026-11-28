# Create showed "Network problem" but the video was made (28 Nov 2026)

## What the owner saw
Android Create v2, cellular, 13:51 UTC. After Create with a Spanish prompt and 3 photos: "Network problem. Check your connection and try again. Tap Create to try again."

## Evidence (QA, eu-west-1, read-only)
- `VideoGenerationSFLauncher`: exactly ONE invocation in 13:44-13:55Z: START 13:51:14.07, `UNLIMITED_ACCOUNT_USE credits=2 minutes=0.5`, `VideosStarted=1`, duration 3.64 s (+0.80 s cold init). No second request, no error.
- `uploads_api`: slot requests at 13:51:12.2 (0.14 s) and earlier at 13:48:59 (a first attempt's slots, or an earlier session). No later call.
- API Gateway has no access logging on QA (`prod` stage shows none), so the HTTP status/latency seen by the edge cannot be read. Not verifiable here.

So the server accepted the one request in 4.4 s billed. The Android call timeout for generate is 30 s (`Api.kt` `callTimeoutSeconds = 30`, connect 20 s, read 30 s), so the server was well inside it. The only way for the app to report `ApiError.Network` is an `IOException` on the response path: the phone's cellular link dropped or switched while the answer was coming back. Most likely cause: lost response. Cannot be proven from server logs.

## Was a double charge possible?
Backend: `client_request_id` already makes the video id deterministic (`uuid5(user:key)`); a replay with the same key returns the existing video before any gate or charge, and a race is refunded by the conditional put. There is also a 2-minute duplicate fingerprint (prompt + options).
Android gap (real): `submitAwait` created a NEW `PendingVideo` (new UUID) on every Create tap and dropped it on a network failure. The retry after this message therefore used a new key. The fingerprint did not save it when photos were re-uploaded (new media ids change the fingerprint) or after 2 minutes. So yes: a second video and a second charge were possible on Android (not for unlimited test accounts). Web already kept the key per identical content; iOS keeps the pending card's id on Retry (key reused).

## Fixes
1. Android: same Create content (text, options, photos, library, deck, dictations) after a network failure reuses the request id (`AppViewModel.lostAnswer`). A different Create gets a new id.
2. Recovery: all three clients replay the create once with the SAME key after a network failure (1.5 s wait). If the first request got through, the server returns the existing video and the user sees success. Android `AppViewModel.send`, web `startGeneration`, iOS `StartReplay.once` (in VideoMKCore, used by `AppModel.create`). I used the same-key replay rather than polling the video list: the client cannot derive the server's uuid5 id, and the replay is the same check done by the authority. Background (non-interactive) sends do not replay on Android; they keep their Failed card and Retry, which reuses the id.
3. Copy: the Create network message no longer says "try again" twice. Android: `err_network_create` "Network problem. Check your connection, then tap Create again. You won't be charged twice." (es: "Problema de conexión. Revisa tu conexión y toca Crear de nuevo. No se cobrará dos veces."); `create_error_retry` is now just the message. Web: `api.network_create` (en/es), same sense with "press Create". iOS: unchanged text (it shows a failed card with a Retry button, so there is no doubled sentence); its generic network string was left alone.
   "We may have already started your video" was not used: after the replay and key reuse, tapping Create again is safe, so the honest short sentence is the one above.
4. Backend: no code change (already idempotent). Added two tests pinning the contract.

## Tests (recorded in test-evidence/)
- Android `AppViewModelTest`: offline create replays once with same key; manual retry reuses the key; lost answer recovered by replay (accepted, no message); different create gets a new key.
- Backend `tests/test_duplicates.py` (9 pass): same key replay an hour later with changed options is one video and one charge; a fresh key after the window is a second video (documents why clients reuse the key).
- Web `api.replay.test.ts`: replay with the same id ends accepted; two failures end as one error after two fetches.
- iOS `StartReplayTests` (swift test): replay once, two failures, refusals never replayed.
Not run: iOS app target build (AppModel.swift edit is a one-line call-site change, compiled only through the package test), Android instrumented/UI tests, a real cellular drop, any paid video creation.

## Deploy
Nothing backend. Ship the web bundle and new Android/iOS builds. Existing apps keep the old behaviour.
