# Better dictation, clients (web and iPhone) (2026-11-28; branch `better-dictation-clients`)

Client side of the paid dictation in `docs/SPEECH_TO_TEXT_2026-11-28.md` sections 9 and 10. Backend is deployed on QA. Android has it too (branch `android-better-dictation`, section "Android" at the end); same rules.

## Behaviour (same on both)
- **When**: `capabilities.dictation.available` is true and not `paused`, and the person has "Better dictation" on (Options, default on; web `localStorage` `vmk.better_dictation`, iOS `UserDefaults` `vmk.better_dictation`). Free: the switch is not shown. `premium: false` with `requires_plan`: one small line "Better dictation with Pro" in Options, no button.
- **Recording**: web `MediaRecorder` (`audio/webm;codecs=opus`, else ogg/mp4; 32 kbps, mono, 16 kHz requested); iOS `AVAudioRecorder` m4a/AAC, mono, 16 kHz, 32 kbps (`audio/mp4`). Nothing is logged; iOS deletes the temp file as soon as it is read, web keeps the clip in memory only.
- **Live preview**: the native engine keeps running while recording (same rules as before: append, rebase, restarts). It is also the fallback. On the web the mic also appears where there is no Web Speech (Firefox): then there is no preview.
- **On Stop**: the clip goes up as JSON base64 with `mime`, `seconds`, `languages: [app language]` (one language, plain) and `prompt` = the text that was in the box before dictation (last 400 characters). The mic shows "Improving the text..." meanwhile.
- **Where the text goes** (`placeBetterText`, pure, both platforms): field unchanged since the preview -> `base + better text` (the preview words are replaced, not doubled; with no preview it is the plain append of the native rules). Field edited by hand meanwhile -> untouched (never replaced); the id is still kept because the clip was paid.
- **Ids**: every returned id with text is remembered (`DictationIDs`: at most 20, newest kept, no repeats, 32 hex only) and sent as `dictation_ids` on the next create; cleared when the video is accepted. iOS: `AppModel.submit(... dictationIDs:)` -> `APIClient.startVideo`; web: `Composer.generate`.
- **Limits**: stops by itself at `min(max_clip_seconds, 360)` with the line "Recording stopped at 6 minutes."; a clip over `max_clip_bytes` is not uploaded.
- **Errors** (`dictation_plan`, `_quota`, `_too_long`, `_failed`, `_paused`, `bad_audio`, 401/403, network/offline): the native text already in the field stays. Lines: quota "Today's better dictation limit is reached. Your device's dictation was used."; failed/network/bad audio "Better dictation isn't available right now. Your device's dictation was used."; too long / 6 min stop; plan, paused, auth: silent. After quota/plan/paused the web re-reads capabilities.
- **Strings**: English and Spanish (the only app languages), web `app-create.*.json` (`create.better_*`), iOS `Localizable.xcstrings` (`better.*`). Disclosure text is the Options hint; the microphone permission copy is unchanged.

## Files
- Web: `frontend/src/lib/betterDictation.ts` (+ `.test.ts`), `Composer.tsx`, `create.ts` (`Capabilities.dictation`), `config.ts` (`apiGateway.dictation`).
- iOS: `VideoMKCore/BetterDictation.swift` (capabilities, preference, ids, `placeBetterText`, failures, clip body, `APIClient.dictate`, `BetterDictationResolution`), `VideoMK/BetterDictation.swift` (recorder + upload, wraps `Dictation`), `CreateView`, `CreateOptionsSheet`, `AppModel`, `APIClient.startVideo(dictationIDs:)`.

## Tests
- Web: `vitest` 14 new tests (caps, preference, ids, answers, text placement, fake `MediaRecorder` + fake send: upload on stop, error fallback keeps native text, hand edit untouched, 6 minute stop, byte limit, denied mic, no native engine). Existing dictation/create/app/i18n suites pass.
- iOS: `swift test` in `VideoMKCore`: 402 tests pass (new: capabilities lenient parse, preference, ids, text placement, error mapping, resolution = text/id/line, clip body, `dictate` against a stubbed server for success and each error, `dictation_ids` in the create body). App builds for the simulator; the 4 gates pass.
- Real QA call (once, account qa-tester6, Polly clip converted to m4a 32 kbps mono, 21 KB, `audio/mp4`): 200 with the exact text. Capabilities block as documented. Note: `seconds_left_today` was 7195 in the answer but 1200 in capabilities (`seconds_per_day` 1200): the backend counter and the capability do not agree, worth a look. Cost about USD 0.0004.

## Not verified
Real microphone, on both platforms: whether the phone allows the recorder and the native recognizer on the microphone at once (iOS: `AVAudioRecorder` next to the recognizer's `AVAudioEngine` on the same session; Chrome/Safari: `getUserMedia` next to `SpeechRecognition`), clip quality, the 6 minute stop on a real clock, interruptions (a call mid-recording), the clip start (the recorder starts right after the recognizer, a few tens of ms). Not tested in a real browser or the simulator UI; the web app was not run against QA.

## Phone test (English, then Spanish with the app language switched; Pro or Max account)
1. Options: "Better dictation" is on. Tap the mic, say "A video about how bees make honey", stop. Expect "Improving the text..." for a second or two, then the words with correct spelling replacing the live ones.
2. Type "Please make it fun." first, dictate "for my niece who is seven": typed text kept, speech appended.
3. Dictate, and while "Improving..." shows, type a word in the box: your text stays, nothing is overwritten.
4. Turn on aeroplane mode, dictate: the phone's own words stay and the line "Better dictation isn't available right now..." appears.
5. Options > turn Better dictation off: the mic behaves as before.
6. Create the video after two dictations; on QA the video row should list both `dictation_ids` and `c_stt`.
7. Free account: no Better dictation row; Options shows "Better dictation with Pro" only if capabilities say `requires_plan`.
8. (Long) record 6+ minutes: it stops by itself with the notice.

## Android (branch `android-better-dictation`)
Same behaviour as above. Pieces (`mobile/android/app/src/main/kotlin/com/videomk/app/`):
- `core/BetterDictation.kt` (pure): `DictationCaps` (parse of `capabilities.dictation`, `isUsable`, `showsUpgradeHint`, limits capped at 360 s / 3 MB), `BetterDictationRules`, `DictationIds` (20, newest, no repeats, 32 hex), `placeBetterText`, `BetterFailure.from(status, body)` and its line, `DictationClip.body()` (base64 JSON, last 400 characters of the draft), `BetterResolution`, `DictationService`.
- `core/BetterDictationEngine.kt`: a `DictationEngine` wrapping the native one (no Android classes, JVM-tested): native stays the live preview and the fallback, a `ClipRecorder` records, Stop uploads, 6 minute auto stop, byte limit, temp file deleted when read, `abandon()` on send/discard.
- `data/MediaRecorderClip.kt`: `MediaRecorder` AAC in MP4, mono, 16 kHz, 32 kbps, `audio/mp4`. If the phone refuses the second microphone client, `start` answers false and the native engine carries on alone (no crash); if the recognizer is the one that drops out, the clip is still recorded.
- `ApiClient.dictate` (`POST /users/{id}/dictation`, 90 s call timeout, same token/headers as other calls; never throws), `startVideo(dictationIds)` -> `dictation_ids` (kept with the pending video for retries; cleared when the video is accepted), `Capabilities.dictation`, Options row "Better dictation" (switch, default on, `SharedPreferences` `better_dictation`/`vmk.better_dictation`, on the local wipe list) and the "Better dictation with Pro" line, "Improving the text..." in the dock while working, the note line for a few seconds. Strings `better_*` in English and Spanish.
- Tests: `BetterDictationTest` (23: caps, preference rule, ids, text placement, errors, resolution, clip body, `dictate` against a fake server for success, every error and offline, `dictation_ids` in the create body, engine with fake native/recorder/service: replace preview, hand edit untouched, errors, 6 minute stop, byte limit, recorder cannot start or throws, no preview, not offered/off/denied, abandon, second start ignored, ids). Full JVM suite (499) passes.

### Android not verified
Real microphone: whether the phone lets `MediaRecorder` and `SpeechRecognizer` hold the microphone together (Android 10+ normally allows the foreground app a second client, but the recognizer runs in the Google app and a device can silence one of them), clip quality and start offset, the 6 minute stop on a real clock, interruptions (a call), the UI (no emulator was run), the Options row and the dock line on a device. No Play upload, no deploy.

### Android phone test (Pro or Max account, English then Spanish)
Steps 1 to 8 of the phone test above, with these Android notes:
1. First use: allow the microphone. Options > "Better dictation" is on. Tap the mic, say "A video about how bees make honey", tap Stop: "Improving the text..." in the dock, then the corrected words replace the live ones.
2. Watch the live words appear while recording. If none appear (the phone gave the microphone to the recorder) the better text still arrives after Stop; if the better text never arrives and the live words stay, the recorder was refused: note the phone model.
3. Aeroplane mode: the phone's words stay and "Better dictation isn't available right now. Your phone's dictation was used." shows for a few seconds.
4. Options > turn it off: the mic behaves as before. Free account: no row.
5. Make a video after two dictations: the QA video row lists both `dictation_ids` and `c_stt`.
6. Receive a phone call while recording, and lock the screen: the app must not crash; native text stays.
