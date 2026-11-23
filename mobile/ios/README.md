# videomk for iPhone (SwiftUI, iOS 17+)

Thin native client for the videomk backend. Product spec: `docs/mobile/SPEC.md`. Status: milestones 1 and 2 of the spec (sign-in,
library, create, progress, player/share, settings). Not yet: editor, credits/purchases, push, Live Activity, Sign in with Apple/Google
(sign-in is the Cognito hosted page, which supports email + password), account deletion.

## What the app does
Home is one screen: the list of videos and, pinned at the bottom, a composer where you type or dictate (microphone button, on-device speech recognition when the iPhone supports it) what you want. Sending adds a placeholder row at once; it becomes a live row with stage and an estimated progress bar, then a finished video, while you keep browsing or ask for more. Length and look are in the options button next to the composer. The photo button next to the microphone attaches up to 10 of your photos (see `docs/PHOTOS.md`): they are cleaned on the phone, uploaded, and the video is built around them.

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
