# videomk for iPhone (SwiftUI, iOS 17+)

Thin native client for the videomk backend. Product spec: `docs/mobile/SPEC.md`. Status: milestones 1 and 2 of the spec (sign-in,
library, create, progress, player/share, settings). Sign in with Apple/Google exist behind build switches (`VMK_AUTH_APPLE`, `VMK_AUTH_GOOGLE` in `project.yml`, default NO). Not yet: push, Live Activity (clean seams exist, see Design system)
(sign-in is the Cognito hosted page, which supports email + password).

## Account deletion
Settings > Delete account (App Store 5.1.1(v)). Contract: `docs/ACCOUNT_DELETION.md`. Flow in `Packages/VideoMKCore/Sources/VideoMKCore/AccountDeletion.swift` (`AccountDeletionFlow`), screens in `VideoMK/DeleteAccountView.swift`, local clearing in `AppModel.finishDeletion`. Debug fixtures (never the real endpoint; fake-library runs always get the fake): `VMK_DEBUG_FAKE_DELETE=notlinked|available|off|unknown[,stale][,offline|forbidden|server|stuck|cancel][,slow]`, `VMK_DEBUG_SHEET=delete`, `VMK_DEBUG_DELETE_STATE=typed|working|signingin|error_<network|uncertain|server|forbidden|cancelled|stuck|wrong|reauthfailed|rejected>`, `VMK_DEBUG_DELETE_DONE=notlinked|available|off|unknown|assumed`, `VMK_DEBUG_REVOKE=ok|cancelled|mismatch|failed`. Do not run the real deletion on a shared QA account.

## What the app does
Home is one screen: the list of videos and, pinned at the bottom, a composer where you type or dictate (microphone button, on-device speech recognition when the iPhone supports it) what you want. Sending adds a placeholder row at once; it becomes a live row with stage and an estimated progress bar, then a finished video, while you keep browsing or ask for more. Length and look are in the options button next to the composer. The photo button next to the microphone (a two-item menu: Photo library, Media) attaches up to 100 of your photos (see `docs/PHOTOS.md`): they are cleaned on the phone, uploaded, and the video is built around them. Before the photo files are cleaned, their capture time and approximate place (rounded to about 1 km) are read and sent only in the generate request; two switches in Settings (Photos, default on) turn dates and locations off.

## Layout
- `project.yml`: the Xcode project definition ([XcodeGen](https://github.com/yonaskolb/XcodeGen); `brew install xcodegen`). The `.xcodeproj` is generated and not committed.
- `Packages/VideoMKCore`: models, API client, PKCE auth, Keychain storage. No UI, unit-tested with `swift test`.
- `VideoMK/`: the SwiftUI app. `VideoMKUITests/`: UI tests that run against the QA backend.

## Build and run
```
cd mobile/ios
xcodegen generate
open VideoMK.xcodeproj        # pick an iPhone simulator and press Run
```
The **Debug** configuration points at the QA backend (values in `project.yml`: `VMK_API_BASE`, `VMK_AUTH_DOMAIN`, `VMK_CLIENT_ID`).
**Release** has no server address until production is deployed; the app then shows "Not configured".

Sign in on the simulator with any account created through the sign-in page (email verification code) or, on QA, a user made with
`aws cognito-idp admin-create-user`.

## Install on your own iPhone
1. The team is set in `project.yml` (`DEVELOPMENT_TEAM: 39ANXJNUTL`, Agilegency Ltd). Xcode must have that Apple ID: Xcode, Settings, Accounts, `+`, Apple ID. Without it the build fails with "No Accounts" (a free Apple ID works for 7-day installs; TestFlight needs the paid program).
2. If `com.videomk.app` is taken for your team, change `PRODUCT_BUNDLE_IDENTIFIER` in `project.yml` **and** the redirect `com.videomk.app://auth/callback` in `backend/backend_stack.py` (the `MobileClient`), redeploy, then regenerate.
3. Connect the phone, select it as the destination, Run. Trust the developer profile on the phone (Settings, General, VPN & Device Management) the first time.

## Languages (English and Spanish)
Policy, glossary and tone: `docs/I18N.md` (section "iOS decisions" at the end). The app follows Settings > Language (Automatic, English, Español), else the iPhone language (per-app language in iOS Settings works too), else English.
- **Add a string**: add the key to `Packages/VideoMKCore/Sources/VideoMKCore/Strings/Localizable.xcstrings` with `en` and `es` (plurals: `one` and `other`, count as the FIRST argument; positional `%1$@`, `%2$lld` when the word order differs), then use `tr("area.key", args...)`. Never `Text("literal")`, never concatenate sentences. Dates, numbers, sizes: `Localization.shared` helpers. Permission texts: `VideoMK/InfoPlist.xcstrings`.
- **Gates** (run all before a TestFlight build):
```
python3 scripts/check_strings.py [--pseudo]   # catalog: Spanish for every key, translated state, placeholders, plurals, glossary words, unused/missing keys, longest-string report
python3 scripts/check_literals.py             # no hard-coded user-visible text in VideoMK/*.swift
VMK_FORCE_LANG=en swift test --package-path Packages/VideoMKCore
xcodebuild test ... -only-testing:VideoMKUITests/VideoMKSpanishUITests   # launches with -AppleLanguages "(es)" -AppleLocale es_ES
```
- **See Spanish**: `xcrun simctl launch <device> com.videomk.app -AppleLanguages "(es)" -AppleLocale es_ES`, or Settings > Language in the app. `VMK_FORCE_LANG=es|en` in the environment overrides the device language (tests, screenshots). Screenshots from the Spanish UI test: `TEST_RUNNER_VMK_SHOTS_DIR=/some/dir` (add `TEST_RUNNER_VMK_SHOTS_MODE=dark|large`). English UI tests pin `-AppleLanguages "(en)"` (`XCUIApplication.english()`).
- Server texts (messages, capability labels and notes) come back already localized; the app only sends `X-Locale`.

## Tests
```
swift test --package-path Packages/VideoMKCore                       # unit tests, no network

# UI tests (QA backend, creates one real video, about 5 minutes). Needs a QA user's tokens, never commit them:
export TEST_RUNNER_VMK_DEBUG_ID_TOKEN=...  TEST_RUNNER_VMK_DEBUG_REFRESH_TOKEN=...
xcodebuild test -project VideoMK.xcodeproj -scheme VideoMK -destination 'platform=iOS Simulator,name=iPhone 17 Pro'
```
Debug builds also accept `VMK_DEBUG_ID_TOKEN` / `VMK_DEBUG_REFRESH_TOKEN` / `VMK_DEBUG_RESET=1` in the launch environment to start
signed in or signed out. This code is compiled out of Release.

## TestFlight
One-time, in the browser: create the app record in App Store Connect (name videomk, bundle ID `com.videomk.app`, any SKU). Then:
```
mobile/ios/scripts/testflight.sh           # archive the Beta build (QA backend) and upload; uses the App Store Connect API key from .env
mobile/ios/scripts/testflight.sh --local   # only build a signed .ipa, no upload
```
The build appears under TestFlight in App Store Connect 10-30 minutes later. Without the app record the upload stops with `missingApp`.

## Design bar 2026 (iPhone)
Spec: `docs/DESIGN_BAR_2026.md`, mockups `docs/design_bar/mockups/phone_*.jpg`, captures of the app `docs/design_bar/ios/`. This replaces the look described in the next section where they differ.
- **Tokens**: `DesignTokens.swift` holds the section 4 table (colours light/dark, type roles, 20 pt gutter, radii, the action and brand gradients, motion, haptics); `Theme.swift` turns it into SwiftUI; `Typography.swift` has `Font.role(_:)` / `.textRole(_:)` (Dynamic Type styles, no fixed sizes).
- **Components** (`DesignKit.swift`, one of each): `PrimaryButton` / `PrimaryButtonStyle` (the ONE gradient action of a screen), `TonalButtonStyle`, `TextButtonStyle`, `IconButton` / `IconButtonFace` (quiet, glass, on media; a spoken label is required), `TopBar`, `Pill`, `SparkleChip`, `PlaySparkle`, `LiveRing`, `LiveSpinner`, `FloatingTabBar`, `TabBarFade`. Glass only floats over content and becomes an opaque surface with Reduce Transparency.
- **Create** (`CreateView.swift`): the caret and "A video about…", three examples that type themselves in, photos and mic icons, three pills, one Create button with its price. After the tap `CreateCapsule` (VideoMKCore, pure state machine) drives the live capsule: checking (Cancel), starting, and exactly one ending (question, refusal, Making, form restored).
- **Making** (`MakingCard.swift`, `MakingScreen.swift`, `Making.swift` in VideoMKCore): the optional `making` object of `docs/CREATE_API.md` is read leniently (`MakingInfo`, never fails the answer it arrives in). Pictures when the server sends them, brand-gradient tiles without, a calm indeterminate line without `making` at all. "Tell me when it's ready" is a local notification (`ReadyNotifier`): there is no push from the server yet.
- **Player** (`VideoDetailView.swift`): Share is the one primary; Save, Edit, Info, More are icons; the end card has Replay and New video; "Make another" chips (`RemixOption`) open Create filled in and are shown only when the server's capabilities can make that variant.
- **Debug fixtures**: `VMK_DEBUG_FAKE_VIDEOS=bar` (the mockup's list), `VMK_DEBUG_MAKING=thumbs|tiles|none`, `VMK_DEBUG_IMAGE_DIR=/path` (real pictures for `fake://` links), `VMK_DEBUG_FAKE_START=fail|blocked|paused|slow`, `VMK_DEBUG_AUTOPLAY=1` (plays to the end card), `VMK_DEBUG_CREATE=checking|checkingfast`.
- **Tests**: `MakingTests.swift` (lenient decoding, the capsule), UI tests `VideoMKDesignBarUITests` (fake only; `TEST_RUNNER_VMK_DEBUG_PLAYBACK_FILE` and `TEST_RUNNER_VMK_DEBUG_SHORT_FILE` point at local mp4 files for the player and the end card).

## Design audit of 2026-11-27 (what changed, where it lives)
Audit: `docs/audits/2026-11-27/IOS_AUDIT.md`. Captures after the fixes: `docs/audits/2026-11-27/ios_after/`.
- **Tab bar and floating bars**: `TabBarRoom` (DesignKit) is the bottom inset of each tab's root screen: that tab's own bars (upload, toasts, next step), then the room of the floating tab bar, with `TabBarFade` behind. Nothing is drawn over a whole tab any more. The bar is an overlay that ignores the keyboard, and is hidden on every pushed page (`tabBarHidden`, `mediaPushed`) and while selecting.
- **Undo over confirm**: `UndoCenter` (VideoMKCore, `AppModel.undo`) holds ONE pending delete for six seconds; the server call goes out when the time is up, when another delete starts, or when the app is left. `UndoToastHost` draws "Deleted · Undo" (and one-line notices such as "Cancelled · 2 credits back") on tab roots, pushed pages and the photo viewer. Used for videos (`AppModel.deleteVideo`: failed, cancelled, refused and finished ones), photos (`MediaModel.deletePhotos`) and collections. Only account deletion confirms. The editor still asks before discarding unsaved edits.
- **Videos**: `POST .../cancel` (`AppModel.cancelVideo`, Making's More menu and the Making card's long press), `VideoStatus.cancelled` with its own card, Delete in the player's More. The list is read at once when the app returns to the front (`AppModel.appBecameActive`, `foregroundEpoch` restarts the polling tasks), and a 401 refreshes the token and sends the call again once (`APIClient.perform`).
- **Create**: first run is YouTube · 1 min (`CreateOptions.defaultMinutes`, `CreateDefaults`), then the last choice. The photo icon is a menu: "Photo library" (the system picker, directly) and "Media" (`LibraryPickerSheet`). Closing keeps the draft (`CreateModel.open` only resets for a prefilled open). `PrimaryButtonStyle(looksDisabled:)` when Create cannot send; "Create · 1 min" when a shorter length is affordable. "Skip all" (`IntakeFlow.skipRest`). `KindStep`: paused offers OK and says when in its title.
- **Sheets**: `FittedSheet` (as tall as its content, opaque), `SheetHeader`, `SectionLabel`, `ChoiceChip` (the one chip shape), `SettingsCard` / `SettingsRow`. Options, questions, summary, refusals, Credits, Storage, Info, Add to collection, Rating, Feedback, Settings, Delete account, the editor and the scene editor are built from them.
- **Player**: one full-screen control, the system's. iPhone is portrait (`project.yml`); `OrientationLock` (PlayerView.swift) lets the system player's full screen turn a wide video sideways and turns back on exit.
- **Sign-in**: `sample_signin.mp4` (six silent seconds, in the bundle) loops over the still (`SampleLoop`; Reduce Motion keeps the still); the Apple button is drawn by us so its words scale.
- **Pull to refresh and empty state**: `SparkleRefreshScroll` draws the sparkle with the pull; `EmptyScene` is the "mountain cabin" cartoon in seven layers (`EmptyScene0...6`, rendered from `backend/lambdas/engine/assets/vector_scenes/mountain_cabin`).
- **New debug fixtures** (fake library only): `VMK_DEBUG_WALLET=buckets|nodate|dailyoff`, `VMK_DEBUG_FINISH_IN_BACKGROUND=1` (the fake server finishes running videos while the app is in the background), `VMK_DEBUG_FAKE_CANCEL=finished`, `VMK_DEBUG_FAKE_DELETE_VIDEO=busy`.
- **Tests**: `swift test` (`UndoTests.swift`: undo window, Info groups, rulings, expired session, cancel/delete/wallet answers), UI tests `VideoMKAuditUITests` (fake only; `TEST_RUNNER_VMK_SHOTS_DIR` writes `audit-*.png`), and in `VideoMKDesignBarUITests`: full screen, delete and undo, the failed page, cancel, back from the background.

## Design system (UX redesign, iPhone)
Spec: `docs/UX_REVIEW.md` (section "iOS implementation status" lists what is done). Where things live:
- **Tokens**: `Packages/VideoMKCore/Sources/VideoMKCore/DesignTokens.swift` is the one canonical place (colour roles light/dark, `live` accent, spacing, radii, sizes, elevation, motion durations, haptic list, WCAG contrast math). `VideoMK/Theme.swift` only turns them into `Color`s (`Theme.Space`, `Theme.Radii`, `Theme.Motion`, `Haptics.play(_:)`). `DesignTokensTests` checks every text/background pair for AA in light and dark. Android and web can mirror the same numbers (`docs/ux_review/tokens_v2.css` has the same values); there is no generator.
- **Type**: `VideoMK/Typography.swift`, `Font.vmk(15, weight:)` maps a point size to a Dynamic Type text style. `scripts/check_fonts.py` fails on any `.font(.system(size:))` in a view. The app lays out up to accessibility-extra-large (`DynamicTypeSize.appMax`, set at the root); one-line chrome (top bar, the New video button, the Create bottom bar) is capped lower with `vmkOneLineCap()` and the page below it scrolls.
- **Components**: `MakingCard.swift` (one waiting component, `.list` and `.detail`, `MakingSnapshot`; seams: `scene` for a scene counter and `thumbnails` for poster frames, both nil until the backend reports them; `AppModel.makingSnapshot` feeds both screens), `VideoCards.swift` (`VideoRow`, `FailedRow`, `GlassChip`), `Components.swift` (`CostLine`, `CostExplainer`, `WalletHero`, `EmptyState`).
- **Seams not built (need backend / owner)**: push and Live Activity (`AppModel` bumps `completions` when a video finishes: hook the notifier there; the card already shows the "you can leave" promise), per-scene progress, vertical version of a video, a sample video on the sign-in screen (drop `sample_signin.mp4` into the app bundle and play it from `SignInView`; there is none today).
- Debug fixtures added: `VMK_DEBUG_OPEN=v1|v2|v3` (opens that video of `VMK_DEBUG_FAKE_VIDEOS=1`), `VMK_DEBUG_SHEET=wallet`, `VMK_DEBUG_PLAYBACK_FILE=/path/video.mp4` (fake library only).
- Gates: `python3 scripts/check_strings.py`, `check_literals.py`, `check_fonts.py`; UI tests `VideoMKDynamicTypeUITests` (XL text, EN/ES, sign-in, home, first run, cost explainer).

## Add a presentation (PowerPoint or PDF to video)
Contract: `docs/CREATE_API.md` (section on decks), design: `docs/DECK_TO_VIDEO.md`. The feature is **hidden unless `capabilities.deck` is present** (the server flag `deckToVideo`). Not verified against a real server yet.
- **Flow** (`Packages/VideoMKCore/Sources/VideoMKCore/Deck.swift`): Create shows "Add a presentation" (also a link in the Add photos sheet) -> Files picker (formats from `capabilities.deck.formats`) -> local format and size check (`DeckFileCheck`, message before any upload) -> `DeckTempStore` copies the file (security-scoped access opened and closed inside `importFile`, random file name, no backup, protected) -> `POST /decks` -> multipart upload streamed from disk with progress and Cancel (`DeckS3Uploader`, foreground only: the screen says to keep the app open) -> the temp copy is deleted at once -> `process` -> poll (2 s, 4 s after 30 s, 6 s after 90 s, give up after 3 minutes with "Check again") -> ready card (file name, slides, suggested length, credits via `CostLine`, "we'll explain every slide"). `DeckJourney` is the testable state machine; `DeckCard` (VideoMK/DeckViews.swift) draws it.
- **Price**: the server's `suggested_credits` at the suggested length, the usual rule (started minutes, 4K doubles) for any other length chosen with the length chips; `target_minutes` is sent only when the person chose a length. The description is optional (placeholder "Who is this for?"), the request check (intake) is skipped for decks.
- **Errors**: each server `code` has its own localized title, message and action (`DeckProblem`); the server's text is only a fallback for unknown codes. `deck_convert_*` offers "Choose the file again" (a failed deck cannot be processed again, and the phone copy is already deleted).
- **Exclusion**: a deck and photos never mix; choosing one asks, then removes the other (`AttachRule`). Decks default to 16:9; a vertical shape shows a gentle warning with one tap back to 16:9.
- **Waiting**: `VideoItem.deckStage` (`stage` in the list) puts "Reading your slides." and "Writing the narration." in the shared MakingCard stage line; nothing deck-specific after completion.
- **Privacy**: file names are only shown on screen (never logged, never in analytics, never in the upload form); the temp folder `tmp/VideoMKDeck` is wiped on sign-out and account deletion (`LocalWipe` list in `AppModel.finishDeletion`, `DeckJourney.wipe`).
- **Debug fixtures** (debug builds, need `VMK_DEBUG_FAKE_LIBRARY=1`, never touch the network): `VMK_DEBUG_DECK=ok|short|long|slow|uploading|processing|offline|fail:<code>` turns the feature on in the fake capabilities and scripts the fake server (`uploading`/`processing` hold that state for screenshots, `offline` loses the first upload, `fail:deck_encrypted` etc.). `VMK_DEBUG_DECK_FILE="Quarterly review.pptx[:MB]"` picks that file the way the Files app would (a sparse file; `huge.pptx:80` shows the local too-large message, `old.ppt` the export hint, `notes.txt` the unsupported type). Use with `VMK_DEBUG_CREATE=empty|shorts|photos` (`shorts` shows the vertical warning, `photos` the exclusion). `VMK_DEBUG_FAKE_VIDEOS=deck` shows two waiting cards in the two deck stages. A video created from a fake deck becomes a fake running video (reading, then writing after 6 s).
- **Tests**: `swift test` (`DeckTests.swift`: checks, error mapping, price, form rules, status line, journey incl. retry/cancel/give-up/cleanup, client calls with `X-Locale`, upload form), UI tests `VideoMKDeckUITests` (EN, ES, XL text; fake only). Screenshots: `TEST_RUNNER_VMK_SHOTS_DIR=... xcodebuild test ... -only-testing:VideoMKUITests/VideoMKDeckUITests`.
