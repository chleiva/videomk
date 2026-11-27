# VideoMK for Android (Kotlin, Jetpack Compose, Material 3)

Native client for the VideoMK backend, feature parity with the iPhone app in `mobile/ios` (that app is the spec). Package / application id `com.videomk.app`,
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

## Creating a video (docs/UI_DESIGN.md section o, docs/CREATE_API.md)
The home screen has no text input: a labelled "New video" button (an extended FAB that shrinks on scroll; a full-width button on the empty home) opens the **Create screen**
(`ui/CreateScreen.kt`): prompt with dictation, one "Add photos" row (the unified sheet), "What is it for?" chips driven by `GET .../capabilities`, the plain-words recommendation,
length chips with prices, collapsed More options (look, subtitles, language, format, resolution) and a bottom bar with the status line and "Create video · ⚡N" that is always drawn.
On Create the app asks `POST .../videos/brief` (2.5 s before the skeleton, 8 s budget, any failure means "go on"), shows up to three questions one at a time and a summary
(`ui/CreateSheets.kt`), or the kind "We can't make this one" sheet, then calls generate with `platform`, `aspect`, `resolution`, `language` and `brief` (only values away from the defaults are sent).
A server without the new endpoints degrades to landscape 16:9 at 1080p and no check. Choices are remembered per person (`CreatePrefsStore`). Pure logic with tests: `core/CreateLogic.kt`, `core/CreateModels.kt`.

## Presentations to video (PowerPoint or PDF; docs/CREATE_API.md, docs/DECK_TO_VIDEO.md)
Only where the server lists it: `capabilities.deck {max_mb, max_slides, formats}` is absent while the feature is off, and then nothing about it is drawn.
- **Entry**: "Add a presentation" is a row at the top of the Add photos sheet (`DeckEntryRow`); it closes the sheet and opens the system document picker (`ActivityResultContracts.OpenDocument`, MIME types from
  `formats`). Photos and a presentation exclude each other: with photos chosen the row first asks ("Use a presentation instead?"); choosing photos (phone or My media) later drops the presentation and deletes its copy.
- **Journey** (`core/Deck.kt`, one `DeckJourney` in the composer's ViewModel, so a rotation keeps it): format and size are checked from the picker's own name, type and size before anything is copied;
  the file is streamed into a private copy under `cacheDir/deck` (random name, never the file name; hard stop at `max_mb`; first bytes checked: `%PDF` or `PK`); `POST /decks`; a streaming multipart upload with
  progress and Cancel (`DeckFormBody`, 64 KB at a time, no login token sent to storage; the photo uploader holds whole files in memory, so it was not reused); the copy is deleted the moment the upload ends;
  `POST /decks/{id}/process`; `GET /decks/{id}` every 2 s (slowing to 5 s), giving up after 3 minutes (or 5 failed calls in a row) with "Keep waiting".
  The read grant of the picker is used once and never made persistable. Nothing about the file is logged.
- **Ready card** (`ui/DeckUi.kt`, `DeckCard`): file name, slides, suggested length, credits (`CostLine`) and the promise "We'll explain every slide in the narration." Failures map the server's `code` to the app's own
  localized, specific messages with one next step (`DeckProblem`: choose another file, choose it again, try again, keep waiting, or nothing for the daily limit and "not available"); an unknown code shows the
  server's message.
- **Create form**: the description is optional (a deck-aware hint; the server wants 10 characters or none), 16:9 is chosen when a deck is picked, a vertical or portrait format shows a gentle warning with a one-tap
  "Use landscape", and a "Suggested" length chip comes first. At the suggested length the request sends **no** `target_minutes` and the price is the server's `suggested_credits`; picking another length sends it
  and the usual started-minutes price applies. The request check (`/videos/brief`) is skipped for decks.
- **Waiting**: the video item's `stage` (`deck_reading`, `deck_writing`, only while `PLOT_CREATION`) becomes `VideoStatus.Running(stage, deck)`; `MakingCard` shows "Reading your slides." then "Writing the narration."
  inside the first step before the usual ones. A failed deck video has no Retry (the deck is gone once planning starts): make it again from Create.
- **Privacy and deletion**: the temporary copy lives only under `cacheDir/deck`; it is deleted after the upload, on Cancel/Remove, on sign-out (`VideoMkRoot`), at the next app start, and by `LocalDataWiper` (explicit
  `deck-cache` step; account deletion also cancels a running upload before wiping).
- **Try it without the server** (debug build): create `files/fake_deck` (a mode: `ok`, `uploading`, `processing`, `slowready`, `stalled`, `offline`, `offline_upload`, `upload_failed`, `too_many_decks`, `unavailable` or any
  server code such as `deck_encrypted`), plus `fake_backend` and `fake_intake`; `--es vmk_debug_deck_file /data/data/com.videomk.app/files/x.pptx` picks that file when Create opens (the system picker is not driven in
  screenshots). `FakeDeckApi` (debug) answers the three calls; `FakeDebugBackend` adds two videos at `deck_reading` and `deck_writing`. Needs the real server flag (`-c deckToVideo=1`) to verify the true upload to
  storage, the real status codes and messages, and a real `generate`.

## Design bar 2026 (docs/DESIGN_BAR_2026.md; this section wins where older sections below differ)
Every screen was rebuilt to the design bar and its phone mockups (`docs/design_bar/mockups/phone_*.jpg`); captures of the result are in `docs/design_bar/android/`.
- **Tokens**: `core/DesignTokens.kt` is the one source (the colour table of section 4, light and dark, the 20 dp gutter, radii, sizes, motion, haptics; `DesignTokensTest` checks the table value by value and the contrast pairs).
  `ui/Theme.kt` turns it into the Material 3 colour scheme, `VmkColors` and the type roles (sp, no literal sizes in screens). `ui/UiKit.kt` has the shared pieces: `PrimaryButton` (the ONE gradient button per screen),
  `GlassIconButton` (the one icon button: quiet, on-dark, raised or filled), `VmkTopBar` (large title or back), `Pill`, `SparkleChip`, `LiveRing`. Icons are Material Symbols Rounded as vector drawables (`res/drawable/sym_*.xml`, `ui/Sym.kt`).
- **Create** (`ui/CreateScreen.kt`): the prompt at the top ("A video about…"), three example chips that type themselves in, photos and mic on the left and options on the right, three value pills (platform, length, look),
  one gradient Create button with its price. After the tap the button becomes the live capsule ("Checking your request", then "Starting your video") with the ring and Cancel; the form is dimmed and locked.
  The capsule is a state machine with no UI in it (`core/CreateSubmit.kt` `CreateCapsule`, `CreateSubmitTest`): a run ends in a question, a refusal, the Making screen, or the form restored intact.
- **Videos** (`ui/LibraryScreen.kt`, `core/DayGroup.kt` `FeedLayout`): large title, the Making card with scene tiles, the newest video as a large poster and the rest two by two, skeletons in the final shapes.
  The tab pill and the round New video button (play-sparkle glyph) float over the list, which fades out beneath them (`ui/Root.kt` `FloatingBar`, `LocalBarSpace`).
- **Making** (`ui/MakingUi.kt`, `core/Making.kt`): the optional `making` object of a video item (docs/CREATE_API.md "Making status") is read leniently (`MakingInfo.fromJson`: every field optional, junk never crashes; `MakingTest`).
  With it: the newest finished scene large inside the live ring, the film strip, "Scene 5 of 9", the live line as received and the sentence being narrated. Scene pictures are cached by video id and scene index, never by their signed link.
  Without it (an older server, or before the plan exists): the title and one calm line. No step names, no percentages. "Tell me when it's ready" (`data/ReadyNotifier.kt`) posts a local notification when the app,
  while off screen, sees the video finish: there is no push yet, so it works for as long as Android keeps the app alive (it keeps checking every 15 s for up to 30 minutes). `POST_NOTIFICATIONS` is asked only when the switch is turned on.
- **Player** (`ui/VideoDetailScreen.kt`): the picture, the title and "1:31 · 1080p", Share as the one labelled gradient button, Save, Edit, Info and More as quiet icons, an end card with Replay and New video.
  "Make another" chips (`core/Remix.kt`, `RemixTest`) open Create prefilled with the idea and one choice changed (a Short, the other language, a 30-second cut); they are drawn only when this server can make that change, and nothing is sent until Create is tapped.
  The idea is what the person wrote when the app still knows it (videos made in this session), else the video's title: the video list does not carry the prompt.
- **Sign-in** (`ui/SignInScreen.kt`): a still of a sample video fills the top (`res/drawable-nodpi/signin_sample.jpg`; `res/raw/sample_intro.mp4` plays there instead when it exists), the mark, the promise, and the ways in.
  Google and Apple buttons are drawn only when the build has them on; beside them email is the text button "Use email", alone it is the one primary button.
- **Media, Settings**: tokens, the 20 dp gutter, a tonal "Add photos" under the search field, a floating selection bar ("Make a video · N" as the one primary).
- **Screenshots without an account**: the debug build's file flags (`files/fake_backend`, `fake_media`, `fake_intake`), plus `files/fake_pics/*.jpg` (posters and scene pictures for the canned videos), `files/fake_making`
  (`none`, `plain`, `render`) and `files/fake_video.mp4`, with an unsigned token in `vmk_debug_id_token`.

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

Social sign-in (Google, Apple) is built but OFF: pass `-PvmkAuthGoogle=true` and/or `-PvmkAuthApple=true` (BuildConfig `VMK_AUTH_GOOGLE` / `VMK_AUTH_APPLE`) once the
Cognito identity providers exist. It is the same hosted-UI request plus `identity_provider=Google|SignInWithApple`. Debug builds can force the buttons for screenshots with
`adb shell "run-as com.videomk.app sh -c 'echo both > files/fake_social'"` (both, google, apple).

Sign in on the emulator through the real hosted page (email + password / verification code), or start signed in with the debug hook below.

## Design system and UX redesign (docs/UX_REVIEW.md)
Android implements phases 1 to 3 of the spec (the iPhone app did the same in parallel; values are identical).
- **Tokens, one place**: `core/DesignTokens.kt` (plain Kotlin, no UI) holds colours (light/dark), spacing (4 dp base), radii, sizes (48 dp touch target), elevation, motion (ms) and the haptic list; `ui/Theme.kt` turns them into `VmkColors` and the M3 `ColorScheme`
  (primary, containers, error, tertiary = the `live` accent), `ui/Theme.kt` `VmkType` is the type scale (M3 roles with explicit `lineHeight`; extra roles `prompt`, `question`, `cta`, `hero`, `wordmark`), `Vmk.space/radii/minTouch` the dp tokens.
  `DesignTokensTest` computes WCAG AA for 19 foreground/background pairs in light and dark. `textTertiary` is `#5F6585` / `#8A92B0`. Gradient buttons use `onPrimary` text (white on the light-dark gradient was 2.9:1). Haptics: `ui/Haptics.kt` maps the five allowed moments (send, selection, warning, video ready, upload done).
- **No fixed text sizes**: the screens use the `VmkType`/M3 roles only (sp with line heights). Cards and rows are text-driven (no fixed heights around text); from font scale 1.5 compact layouts stack (`isLargeText()`); chips wrap (`FlowRow`). `FontScaleLayoutTest` (androidTest, no server or account) checks sign-in and the home components at 2.0 and 1.0, 360 dp wide, English and Spanish: nothing leaves the screen and buttons are at least 48 dp.
- **Components** (`ui/Components.kt`): `VideoRow` (128x72 poster, duration, 2-line title; stacks at large text), `FailedRow` (danger/warning container, reason, "no credits used", Try again), `DayHeader` + `core/DayGroup.kt` (Today / Yesterday / Earlier; running videos stay on top), `MakingCard` (the ONE waiting component: `MakingLayout.List` on the home list, `Detail` on the video screen, both fed by the same `core/MakingModel.kt` `MakingSnapshot`; stage verbs, ETA, four segments, "you can leave" copy; cross-fades into the ready row or player), `CostLine`/`CostSheet`/`CreditsExplainer` ("What does this cost?"), `WalletHero`.
  Seams (hidden until the backend reports them): `MakingSnapshot.scene` (scene counter), `.thumbnails` (poster strip), `.narrationLine`; `AppViewModel.makingEvents` (`MakingEvents.onFinished`, for push or an ongoing notification: nothing subscribes today); `res/raw/sample_intro.mp4` (a muted looping sample on the sign-in screen appears when the file exists).
- **Screens**: home (day groups, thumbnail rows, Create docked above the tab bar so it never covers a row; first-run card with the prefilled 30 s prompt and "Make my first video"), video screen (edge-to-edge player, Share primary, Save to gallery on Android 10+, Edit, "Make another video"; "Copy title" removed, "Copy description with credits" lives inside the credits disclosure), Create (prompt first, wrapping platform chips, "What does this cost?" sheet, the first-time length is 30 s), wallet (gradient hero, "How credits work" in the body, no disabled button, the unlimited test label only in debug builds), sign-in (tagline equals the home headline), settings (Sign out in the primary colour, Terms and Support rows).
- Not done: a Style row + sheet (the format and length chips stay visible: they set the price), Create in the tab bar centre, a tablet layout, scene progress and thumbnails (backend), push (backend and owner decision), the sample video asset, question-sheet edge polish.

## Languages: English and Spanish (docs/I18N.md)
English is the base (`res/values`), Spanish is `res/values-es`; the contract (policy, glossary, tone, key names) is `docs/I18N.md`.
- **Selection order**: the person's explicit choice in Settings > Language (Same as my phone / English / Español) > the device language > English. Any `es-*` is Spanish, any other language is English
  (`core/Txt.kt` `AppLocale`, tested). Android 13+ stores the choice in the system (`LocaleManager`, so Settings > System > App languages agrees, `res/xml/locales_config.xml`); Android 12 and older store it
  in preferences and each activity wraps its context in `attachBaseContext` (`data/AppLanguage.kt`). The narration language of a video (`auto|en|es`) is a separate option and is unchanged.
- **`X-Locale: en|es`** goes on every API call (`ApiClient`, from the effective app language). Server messages, capability labels/notes and the intake model's text come back localized or in the request language
  and are shown as received: never translate them in the app.
- **Add a string**: add it to `res/values/strings_<area>.xml` AND `res/values-es/strings_<area>.xml` (key `area_name`, lower snake case; `%1$s`/`%1$d` placeholders, same order and types in both; counts use `<plurals>` with
  `one` and `other`; never build a sentence from pieces). In Compose use `stringResource` / `pluralStringResource`. Outside Compose (logic objects, view models, error mappers) use `Txt.s(R.string.x, args)` and
  `Txt.n(R.plurals.x, count, extra...)` at the moment the text is needed (never in a field initialised once: the language can change). `contentDescription`, `onClickLabel` and `stateDescription` are strings too.
  Dates, numbers, durations and sizes use `Txt.locale` formatters. Brand names, codes, `testTag`s, log lines and debug-only fixtures (`src/debug`) stay literal.
- **Gates** (all in `./gradlew testDebugUnitTest lintDebug`): `LocalizationTest` checks key parity, placeholder parity (type and order), plural completeness, the locale policy, the `X-Locale` header and scans
  `ui/*.kt` for new user-visible English literals; lint treats `MissingTranslation` and `ExtraTranslation` as errors. Plain JVM tests read the real `strings*.xml` through `JvmStringProvider` (English by default;
  `Txt.provider = JvmStringProvider("es")` for a Spanish assertion).
- **Try Spanish**: `adb shell cmd locale set-app-locales com.videomk.app --locales es` (reset with `--locales ""`), or pick Español in Settings. For screenshots without an account, create the file flag
  `files/fake_backend` (plus `fake_media`, `fake_intake`, `fake_social`; see `DebugHooks`) and start with a locally made, unsigned token in `vmk_debug_id_token`: `FakeDebugBackend` serves canned videos, wallet and editor data.
  Check at 360x640 dp, font scale 1.0 and 2.0, light and dark: Spanish is about 25 to 35 percent longer.
- State held in a view model (for example an error banner) keeps the language it was created in until it is replaced; screens re-render in the new language on the activity recreation a language change causes.

## Tests
```
./gradlew testDebugUnitTest              # 404 JVM unit tests, no network (MockWebServer): API client, auth/PKCE/refresh, dictation plan + locale,
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
