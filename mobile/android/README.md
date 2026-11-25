# videomk for Android (Kotlin, Jetpack Compose, Material 3)

Native client for the videomk backend, feature parity with the iPhone app in `mobile/ios` (that app is the spec). Package / application id `com.videomk.app`,
minSdk 26, targetSdk 36, compileSdk 37. Single activity, `ViewModel` + `StateFlow`, a thin repository layer (`Backend`), OkHttp + kotlinx.serialization, coroutines,
manual DI (`AppContainer`). Release-ready (R8, signing from outside the repository) but nothing has been published: see `docs/ANDROID_RELEASE.md`.

## What the app does
Same as iOS: sign in with the Cognito hosted page (Authorization Code + PKCE in a Chrome Custom Tab, redirect `com.videomk.app://auth/callback`), one home screen
with the list of videos (pending rows, live rows with an honest progress estimate, finished videos) and a composer pinned at the bottom (text, dictation, up to 100
photos, length and look, credit cost), video page with Media3 ExoPlayer inline plus a landscape full screen, share/copy, editor (title, scenes, narration, photo
picks, reorder/delete, Preview and Publish), credits screen, settings. Unknown scene types from the server (it recently added `clip` and `gallery`) show as a
generic "Scene" and never crash the editor.

## Photo dates and approximate places
Before a photo is stripped, `PhotoExif` reads its capture time (`DateTimeOriginal`, else `DateTime`) and GPS from the **original** (the private cache copy made right after the pick). Latitude and
longitude are rounded to 2 decimals (about 1 km) on the phone and sent only in the generate request's optional `media_meta` (`{mediaId: {taken, lat, lon}}`, only photos and fields that exist). The uploaded
JPEG still has all metadata removed. Two switches in Settings > Photos (`PhotoSettings`, plain preferences, both default on) turn dates and locations off; when off they are not read at all. No
`ACCESS_MEDIA_LOCATION` and no prompt: the system photo picker / MediaStore redact GPS, so photos reached through it send no location, while gallery apps reached through the chooser often hand over the original.

## The interface (docs/UI_DESIGN.md)
Tokens (colours, radii, shadows) live in `ui/Theme.kt` and shared pieces in `ui/UiKit.kt`. Main screen: docked **composer card** (`ComposerBar.kt`: photo strip, two-line field, ONE
status line for price / reason / fix with a one-tap fix chip, toolbar with attach + count badge, options pill "3 min · ⚡3", mic, and a send button that is always drawn, tonal until
it can act) over a feed of **cards** (`LibraryScreen.kt`: Ready, Making with four named steps, Didn't finish with "Try again"). Options are a bottom sheet (`OptionsSheet.kt`). **Add photos**
is one sheet (`AddPhotosSheet.kt`): This phone | My media over one selection bar. No storage permission: "This phone" opens the system Photo Picker from inside the sheet and what it
returns lands in the strip at once. The Media tab shows the **upload journey** (`UploadJourney.kt`): local tiles with states, one collapsible upload bar, one completion toast.
Pure logic with tests: `core/ComposerLogic.kt` (status line state machine, cost fix, selection wording, tile states, upload summary).

## Layout
- `app/src/main/kotlin/com/videomk/app/core`: no Android classes, so it runs in plain JVM unit tests. Models, `ApiClient` (every endpoint and header), `AuthService`
  (PKCE, refresh with one request in flight), `LibraryMerge`/`ProgressEstimator`, `Editor` (snapshot, ops, diff), `Photos` (limits, geometry, multipart, presigned-POST
  uploader), `Dictation` (`DictationPlan`, `DictationLanguage`).
- `.../data`: Android implementations: `SecureTokenStore` (EncryptedSharedPreferences / Keystore, never crashes), `PhotoPrep` (decode, apply EXIF orientation to the
  pixels, scale to 2048 px, re-encode: no metadata survives), `DictationController` (`SpeechRecognizer` with partial results and a guarded fallback chain).
- `.../ui`: Compose screens and view models. `AppViewModel` (session, library, pending rows, polling) lives in the activity's `ViewModelStore`, so its `start()` work
  runs once per process, not once per rotation (the iOS root-task-ran-twice bug). `ComposerViewModel` keeps the half-typed brief, photos and dictation across rotation.
- `app/src/debug` / `app/src/release`: `DebugHooks` (test sign-in, default minutes, photo files). The release twin is a no-op, so none of it is in a release build.
- `scripts/`: `qa-launch.sh` (start the debug app signed in as the QA test user), `run-ui-tests.sh` (instrumented tests).

## Build and run
Needs JDK 17 (`JAVA_HOME`; Android Studio's bundled JBR or Zulu 17 both work) and the Android SDK (`ANDROID_HOME`, platform 37).
```
cd mobile/android
./gradlew assembleDebug                 # debug build: QA backend (same values as mobile/ios/project.yml), debuggable
./gradlew installDebug
```
The **debug** build points at the QA backend (`API_BASE`, `AUTH_DOMAIN`, `CLIENT_ID` in `app/build.gradle.kts`). The **release** build has no server address until
production is deployed, exactly like the iOS Release configuration: it starts and shows "Not configured". For a release-compiled build against QA (the iOS "Beta" /
TestFlight equivalent, what you put on the Play internal testing track first) add `-PvmkReleaseBackend=qa`. When production exists, pass or set `vmkProdApiBase`,
`vmkProdAuthDomain`, `vmkProdClientId` (gradle properties) or edit the defaults in `app/build.gradle.kts`.

Sign in on the emulator through the real hosted page (email + password / verification code), or start signed in with the debug hook below.

## Tests
```
./gradlew testDebugUnitTest              # 102 JVM unit tests, no network (MockWebServer): API client, auth/PKCE/refresh, dictation plan + locale,
                                         # library merge + progress estimator, photo geometry + multipart + uploader, editor diff/snapshot/view model, app view model
./scripts/run-ui-tests.sh                # instrumented tests on the running emulator, against QA (see below)
./scripts/run-ui-tests.sh com.videomk.app.E2ETest   # makes ONE real 1-minute video from 4 photos on QA (a few cents), plays it, full screen, edits it
```
The instrumented tests (8 + 11 + 3 Compose fixtures + 2, plus 3 end-to-end steps) are UiAutomator black-box tests (`QuickUiTest`, `DictationUiTest`, `E2ETest`) plus `PhotoPrepTest` (9 tests, real decoder: GPS/EXIF really stripped,
orientation applied to the pixels, at most 2048 px, under 10 MB). They need an emulator or device, and for the signed-in ones a QA session:
1. Create a QA user once: `aws cognito-idp admin-create-user` / `admin-set-user-password --permanent` in the `videomk-qa` pool (profile `qa`); give it unlimited credits with
   `backend/scripts/wallet_admin.py unlimited <email>`.
2. A small script that prints `ID_TOKEN REFRESH_TOKEN` (`aws cognito-idp admin-initiate-auth --auth-flow ADMIN_USER_PASSWORD_AUTH`), kept outside the repository, referenced
   by `VMK_QA_MINT` (default `~/.videomk-secrets/mint-tokens.sh`). Tokens last about an hour and are passed to the tests as instrumentation arguments, never stored.
3. `VMK_PHOTOS_DIR=/path/with/p1.jpg..p4.jpg` so the script copies the photos into the debug app's private files dir (`run-as`).
The dictation tests need the microphone permission set from outside (changing it from inside would kill the test process): the script does `pm grant` / `pm revoke`.

Debug builds also accept intent extras (see `app/src/debug/.../DebugHooks.kt`): `vmk_debug_id_token`, `vmk_debug_refresh_token`, `vmk_debug_reset=1`,
`vmk_debug_default_minutes`, `vmk_debug_photo_files=/a.jpg:/b.jpg`. `scripts/qa-launch.sh` uses them. This code is not in release builds.

## Verified on
Emulator `pi35` (Android 15, API 35, arm64 Pixel 6 image), against the QA backend. The other AVD (`Pixel_10_Pro_XL`, Android 17 preview image) booted to a black, locked
screen and refused to resolve any third-party activity in this environment, so it was not used. Start the emulator with `-gpu swiftshader_indirect` if the default GPU mode gives a black screen.

## Decisions worth knowing
- Android has no separate "speech recognition" permission: `DictationPlan.decide` gets the one RECORD_AUDIO state as both inputs. Fallback order as on iOS: own recognizer,
  then the keyboard's voice typing (field focused), then a clear message. No path throws.
- Narration plays whatever the ringer mode: the player uses the media stream (`USAGE_MEDIA`, `AUDIO_CONTENT_TYPE_MOVIE`) with audio focus; the ringer/silent switch does
  not mute that stream.
- Full screen is a separate landscape activity (`sensorLandscape`) that receives the URL and position and returns the position when closed.
- The editor reorders with up/down buttons (accessible, testable) instead of drag handles.
- The abuse controls planned for iOS (DeviceCheck / App Attest) have no Android counterpart yet: Play Integrity would be the equivalent (owner decision, backend work).
