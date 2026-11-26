# videomk for iPhone (SwiftUI, iOS 17+)

Thin native client for the videomk backend. Product spec: `docs/mobile/SPEC.md`. Status: milestones 1 and 2 of the spec (sign-in,
library, create, progress, player/share, settings). Sign in with Apple/Google exist behind build switches (`VMK_AUTH_APPLE`, `VMK_AUTH_GOOGLE` in `project.yml`, default NO). Not yet: push, Live Activity (clean seams exist, see Design system)
(sign-in is the Cognito hosted page, which supports email + password).

## Account deletion
Settings > Delete account (App Store 5.1.1(v)). Contract: `docs/ACCOUNT_DELETION.md`. Flow in `Packages/VideoMKCore/Sources/VideoMKCore/AccountDeletion.swift` (`AccountDeletionFlow`), screens in `VideoMK/DeleteAccountView.swift`, local clearing in `AppModel.finishDeletion`. Debug fixtures (never the real endpoint; fake-library runs always get the fake): `VMK_DEBUG_FAKE_DELETE=notlinked|available|off|unknown[,stale][,offline|forbidden|server|stuck|cancel][,slow]`, `VMK_DEBUG_SHEET=delete`, `VMK_DEBUG_DELETE_STATE=typed|working|signingin|error_<network|uncertain|server|forbidden|cancelled|stuck|wrong|reauthfailed|rejected>`, `VMK_DEBUG_DELETE_DONE=notlinked|available|off|unknown|assumed`, `VMK_DEBUG_REVOKE=ok|cancelled|mismatch|failed`. Do not run the real deletion on a shared QA account.

## What the app does
Home is one screen: the list of videos and, pinned at the bottom, a composer where you type or dictate (microphone button, on-device speech recognition when the iPhone supports it) what you want. Sending adds a placeholder row at once; it becomes a live row with stage and an estimated progress bar, then a finished video, while you keep browsing or ask for more. Length and look are in the options button next to the composer. The photo button next to the microphone attaches up to 100 of your photos (see `docs/PHOTOS.md`): they are cleaned on the phone, uploaded, and the video is built around them. Before the photo files are cleaned, their capture time and approximate place (rounded to about 1 km) are read and sent only in the generate request; two switches in Settings (Photos, default on) turn dates and locations off.

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
swift test --package-path Packages/VideoMKCore                       # 13 unit tests, no network

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
