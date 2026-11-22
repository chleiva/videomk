# videomk native apps: product and technical spec (draft 2)

Fully native clients: **iOS in Swift/SwiftUI, Android in Kotlin/Jetpack Compose.** No cross-platform runtime, no web views for product UI.
This document is the source of truth for what gets built; `DESIGN_BRIEF.md` is what the design agent works from.
Decisions made so far are in §9. Items marked **[DECIDE]** still need a product decision; everything else is a proposal to be challenged.

## 1. Product scope

videomk turns a topic into a narrated, animated explainer video and lets the creator review and change any part of it. The apps are
**thin clients**: all generation, rendering and editing validation happens on the server (Lambda + Step Functions + S3). A phone never
renders video.

### 1.1 Who and what
- **Creator (primary):** makes explainers for YouTube/social, wants a publishable video without editing software, and wants control over the script, visuals and photos.
- **Reviewer (secondary):** opens a shared video to watch, comment or approve (later; out of v1 unless decided).

### 1.2 v1 feature set
| # | Feature | Notes |
|---|---|---|
| 1 | Sign in with **Apple** and **Google** (native), sign out, delete account | §11 |
| 2 | Library | all videos with live status, pull to refresh, push when done |
| 3 | Create | prompt, length, look, music mood; shows what the video will cost (free allowance or credits) |
| 3b | Credits | free allowance, buy credit packs through the store, balance + history (§10) |
| 4 | Progress | stages, not a spinner; cancel is out of scope |
| 5 | Player | play, scrub, chapters, share/save, copy title + description (with photo credits) |
| 6 | Editor | every part of the video (see §4); preview vs publish; revisions |
| 7 | Notifications | render finished / failed (APNs, FCM) |
| 8 | Safety | report content in-app (store requirement), clear rejection messages |
| 9 | Settings | account, appearance, notifications, legal, feedback |

### 1.3 Native differentiators (planned, after the core flows are solid)
iOS: Live Activity for render progress, App Intents/Shortcuts ("make a video about …"), share extension, widgets, Spotlight indexing.
Android: ongoing progress notification, App Shortcuts/Actions, share target, widgets. Both: haptics on reorder, system share sheet, dictation for prompts.

### 1.4 Explicitly out of v1
On-device rendering or editing of video, uploading user photos/video/audio, voice cloning, collaboration/comments, in-app YouTube upload,
tablet-specific features beyond adaptive layout, languages other than English (strings are localization-ready).

## 2. Platform baselines  **[DECIDE: confirm]**
| | iOS | Android |
|---|---|---|
| Language/UI | Swift 6, SwiftUI (UIKit only where SwiftUI can't: e.g. reorder polish, share extension plumbing) | Kotlin, Jetpack Compose, Material 3 |
| Minimum OS | iOS 17 (Observation, modern SwiftUI) | Android 8 / API 26 (target the API level Google Play requires at submission) |
| Devices | iPhone + iPad (adaptive: `NavigationSplitView`) | Phones + tablets/foldables (window size classes) |
| Architecture | MVVM with `@Observable`; unidirectional state per feature | MVVM + `StateFlow`; unidirectional state per feature |
| Modules | SwiftPM: `Core` (models, API, auth, editor logic), `DesignSystem`, `Features/*`, app target | Gradle: `:core`, `:designsystem`, `:feature:*`, `:app` |
| Concurrency | async/await, actors | coroutines/Flow |
| DI | constructor injection, a small `Environment` container | Hilt |
| Networking | `URLSession` + generated client | OkHttp/Ktor + generated client, `kotlinx.serialization` |
| Auth | `ASWebAuthenticationSession`, tokens in Keychain | AppAuth (Custom Tabs), tokens encrypted with Keystore |
| Video | `AVPlayer` / `AVKit` | Media3 ExoPlayer |
| Push | APNs (+ ActivityKit for Live Activities) | FCM |
| Local storage | SwiftData or a small file cache for library + drafts | Room (library + drafts) |
| Quality | Swift Testing/XCTest, snapshot tests, UI tests | JUnit, Compose UI tests, screenshot tests (Paparazzi/Roborazzi) |

## 3. Screens and flows

```
Sign in ─▶ Library ─▶ Video detail/Player ─▶ Editor ─▶ (Preview) ─▶ Publish
              │                                  ▲
              └─▶ Create ─▶ Progress ────────────┘
Settings (account, notifications, appearance, legal, report, delete account)
```

### 3.1 Library
- Grid on tablets, list on phones; each item: poster (preview GIF or first frame), title, status chip, duration, age.
- Statuses map to server statuses: running (PLOT_CREATION/ASSETS_CREATION/…), complete, failed, rejected (shows the reason: "This request can't be turned into a video"), editing (render in progress on an existing video).
- Pull to refresh; background refresh via push. Cached for offline viewing of the list (not playback).
- Empty state teaches by example (3 tappable sample prompts).
- Acceptance: a video created on one device appears on the other after refresh; a rejected prompt shows its reason; rotating or resizing never loses scroll position.

### 3.2 Create
- Prompt field (10–2000 chars, validated before sending, counter), dictation, 3–5 rotating example prompts.
- Options: **length** (1–12 min, default 3), **look** (Midnight/Paper/Sunrise), **music mood**. *(Server gap: only `prompt` is accepted today.)*
- Shows the **cost before you commit** ("Free video" or "N credits") and the balance. When there is no free allowance and not enough credits, the primary button becomes "Get credits" (opens the store sheet, §10). When a free video returns, say when ("Your next free video is in 3 days"). No dark patterns, no countdown pressure.
- Sends `client_request_id` (UUID per attempt) so a retry never double-bills.
- Acceptance: airplane-mode submit fails cleanly with the draft preserved; double-tap creates one video and charges once; insufficient credits routes to purchase and returns to Create with the draft intact.

### 3.3 Progress
Stages the user can understand: *Researching → Writing the script → Recording the voice → Choosing photos → Rendering → Finishing*.
*(Server gap: today only coarse statuses; add `progress {stage, done, total}`.)* Push notification on finish/fail; on iOS a Live Activity, on Android an ongoing notification.
Failure shows what happened in plain words and that no quota was consumed.

### 3.4 Player / detail
- Player with scrubber, chapter markers (from `chapters`), playback speed, picture-in-picture/background audio off.
- Actions: **Edit**, **Share** (system sheet with the MP4 via signed URL download), **Save to Photos/Gallery**, **Copy title**, **Copy description** (includes chapters + *Image credits* + *Sources*), **Report**.
- Shows which revision is published and whether a newer preview exists.

### 3.5 Editor (the core of the app)
Mirrors the web editor's capabilities, redesigned for touch.
- **Scene list:** long-press-drag reorder with haptics, swipe to delete (with undo), "+" to insert after, each row shows type, narration excerpt, duration, and an *edited* / *needs attention* marker.
- **Inspector** (bottom sheet on phones, side panel on tablets): narration with live word count and spoken-time estimate; scene type; a form per type:
  title, bullets, diagram (steps as chips/rows with a mini-preview, **not** typed arrows), chart (rows of label/value + bar/line toggle), timeline (rows of date/label), stat, quote, **photo** (query field + candidate grid with photographer and "Unsplash" credit as tappable links);
  chapter title; delete.
- **Preview / Publish:** *Preview* renders a draft (server, fast); player shows draft vs published tabs; *Publish* renders the full-quality version; earlier versions are kept.
- **State model:** the UI edits a **local working copy** and submits `diff(server, local)` (see §5.3); validation mirrors the server and shows errors beside the field; editing locks while a render runs; drafts persist across app restarts; undo/redo.
- **Conflicts:** server returns 409 with the current revision → offer "Reload" or "Keep my changes and re-apply" (re-diff against the new server state).
- Acceptance: every op the server supports can be produced from the UI; the golden diff vectors (§5.3) pass; a stale device gets a clear conflict flow; killing the app mid-edit restores the draft.

### 3.6 Settings / account / safety
Sign out; **delete account** (in-app: removes videos, files, wallet and the Cognito user, and **revokes the Sign in with Apple token**; Apple requires this for apps with account creation: verify current wording); notification preferences; appearance (system/light/dark); legal (privacy, terms); send feedback; **Report** on any video and inside the editor (Google Play requires in-app reporting for apps that generate AI content: verify current policy text).

## 4. Native quality bar
- **Accessibility:** Dynamic Type / font scale to the maximum sizes without truncation of essential text; VoiceOver/TalkBack labels, actions for reorder (accessibility actions, not drag only), focus order; 4.5:1 contrast; Reduce Motion respected; captions are burned into videos already (no soft captions v1).
- **Performance budgets:** cold start to interactive library < 2 s on a mid-range device; scrolling at display refresh with no dropped frames in lists of 200 videos; editor interactions < 100 ms to feedback; video starts < 1.5 s on Wi-Fi.
- **Resilience:** every network call has a timeout, retry with backoff for idempotent calls, and an offline state; no spinner without a way out.
- **Security/privacy:** tokens only in Keychain/Keystore; no secrets in the app (Unsplash and TTS keys stay server-side); pin nothing initially, TLS only; log no prompts/tokens; privacy manifest (iOS) and data-safety form (Play) kept in sync with real behaviour; no tracking, so no ATT prompt.
- **Appearance:** light/dark, platform-idiomatic navigation (large titles, sheets, context menus on iOS; top app bars, bottom sheets, predictive back on Android), one shared brand.

## 5. API contract (single source of truth)

### 5.1 Contract first
Add `api/openapi.yaml` describing every endpoint, schema, error shape and the editor operations. Generate clients (Swift: swift-openapi-generator; Kotlin: openapi-generator or a thin hand-written Ktor client verified by tests) and the web's TypeScript types from it. The CDK stack and the spec are checked against each other in CI.

### 5.2 Existing endpoints (all Cognito-authorised, `Authorization: Bearer <id_token>`)
`POST /users/{u}/videos/generate` · `GET /users/{u}/videos` · `GET /users/{u}/videos/{v}` (signed URL; `?download=1`) ·
`GET /users/{u}/videos/{v}/plan` · `POST /users/{u}/videos/{v}/edits`.

### 5.3 Shared logic, tested by shared vectors
`diff(server, local) → ops`, per-scene validation and the text↔props conversions exist in TypeScript today. They are re-implemented natively, so they are pinned by **golden fixtures** in `api/fixtures/` (input beats → expected ops / error messages) run by all three platforms' test suites. The server's `edits.py` remains the authority; clients only mirror it for instant feedback.

### 5.4 New backend work required by the apps  **(none of this exists yet)**
| Need | Why |
|---|---|
| `POST /…/generate` accepts `target_minutes`, `theme`, `mood` | Create options |
| Wallet & entitlements (§10): `GET /users/{u}/wallet`, cost quote on create, credit ledger, purchase verification, store server notifications | Free allowance + paid credits; **replaces the daily quota** |
| `POST /auth/social` (Apple/Google ID-token exchange) + provider flags in `/config` (§11) | Native one-tap sign-in |
| `POST /telemetry` (batched events + crash/hang reports) → structured CloudWatch logs and metrics (§12) | Our own analytics and crash reporting |
| Progress: `progress {stage, done, total}` on the video item/list | Real progress UI, Live Activity |
| Cursor pagination + `ETag`/`If-None-Match` on the list | Large libraries, cheap refresh |
| `POST /devices` (register APNs/FCM token), `DELETE /devices/{id}`; send on COMPLETE/FAILED/EDIT_READY | Push (APNs direct for Live Activity updates; FCM for Android) |
| `DELETE /users/{u}` | Account deletion (store requirement) |
| `POST /reports` + a review queue | In-app reporting (store requirement) |
| `GET /…/revisions`, `POST /…/restore` | Revision list and restore in the editor |
| Signed URL for a beat's narration audio | "Listen to this scene" in the editor |
| `GET /config` (unauthenticated): min supported app version, feature flags, legal URLs | Forced upgrade, kill switches |
| `X-App-Version`, `X-Platform` headers + `/v1` versioning | Safe evolution of an API that installed apps keep calling |
| Cognito mobile app client; federated Google/Apple for the web's Hosted UI (S256 PKCE only) | Web parity; native apps use `/auth/social` |

## 6. Build, test, release
- **Repo layout:** `mobile/ios`, `mobile/android`, `api/`, `design/tokens.json` (design tokens exported by the design agent and compiled to Swift/Kotlin by a script).
- **CI:** build + unit + UI/screenshot tests for both apps on every PR; contract tests against the OpenAPI spec; lint (SwiftLint/ktlint/detekt).
- **Distribution:** TestFlight and Play internal/closed testing tracks; staged rollouts. Crash reporting and analytics are our own (§12): no third-party SDKs.
- **Store readiness:** privacy policy matching actual data handling (including telemetry and purchases), App Privacy "nutrition label" and Play Data safety form, age/content rating questionnaires (declare AI-generated content), account-deletion path, in-app reporting, review notes with a demo account and sample prompts, export-compliance answers (HTTPS only). Google Play: a new *personal* developer account must run a closed test with 12 testers for 14 days first; organisation accounts are exempt.
- **Payments:** credits are consumable digital goods sold only through Apple/Google billing (§10); there is no web checkout.

## 7. Build constraints and how we handle them
- **iOS cannot be compiled or run in the cloud sandbox this assistant works in** (Xcode needs macOS). Without a connected Mac, Swift UI code would be written blind. Plan: put everything that isn't UI (models, API client, auth state machine, diff/validation, formatting) in plain Swift packages that are unit-tested against the shared fixtures, and do UI work with a Mac connected (simulator builds, screenshots, XCUITests). Android has no such limit.
- Design handoff must be machine-readable (tokens, component specs, redlines) so implementation doesn't depend on eyeballing mockups.

## 8. Milestones (sequence, not durations)
0. **Contract and design foundations:** OpenAPI spec + fixtures; design tokens, component inventory and key-screen designs approved; Cognito mobile client; backend gaps from §5.4 that block later steps (generate options, quota, progress, config).
1. **Skeleton apps:** sign-in, token refresh, library list, settings/sign-out; CI green.
2. **Create → progress → player:** end to end on both platforms, with push on completion.
3. **Editor:** list, inspector for all scene types, photo picker, diff/submit, preview/publish, revisions, conflicts, drafts.
4. **Native extras:** Live Activity / ongoing notification, widgets, share targets, App Intents/Shortcuts.
5. **Hardening and store readiness:** accessibility audit, performance budgets, safety/reporting, account deletion, beta tracks, review submissions.

## 9. Decisions

### Made
| # | Decision |
|---|---|
| 1 | **Platforms:** SwiftUI iOS 17+ (iPhone + iPad adaptive) and Compose Android 8+ (phones + tablets/foldables). Fully native, no cross-platform runtime. |
| 2 | **Money:** 3 free videos on day one, then 1 free video per day (length-capped, watermarked); credits in three packs bought **only through the stores**; AI edits metered from real cost. Pricing, allowances and credit costs are **server-driven and changeable without an app update** (§10, `PRICING.md`). |
| 3 | **Sign-in:** native Sign in with **Apple** and **Google**; providers are server-configurable; email/password exists only as a hidden reviewer/test path (§11). |
| 4 | **Analytics and crash reporting:** our own, minimal, logged to CloudWatch, plus the stores' own crash consoles. No analytics or crash vendors (§12). |
| 5 | **Collaboration / reviewers:** not in v1. Revisit later. |
| 6 | **Identity:** name **videomk** (domain videomk.com). Organisation accounts exist for Apple and Google Play. Proposed ids: iOS `com.videomk.app`, Android `com.videomk.app`; confirm before registering. |
| 7 | **Android colour:** brand-first, with *Use system colours* (Material You dynamic colour) as an opt-in setting on Android 12+. Rationale: videomk's identity is tied to the video looks users see; dynamic colour stays available for people who expect it. Status colours (success/warning/danger) never follow the wallpaper. |
| 8 | **Type:** system fonts for UI (SF Pro on iOS, Roboto Flex/system on Android) for best Dynamic Type/font-scaling, platform feel and no bundling. Brand expression comes from colour, motion, iconography and the wordmark. Inter remains the typeface *inside the generated videos*. |

### Still open
- Confirm the credit formula/packs, price of "remove watermark" and whether to keep 3 free AI actions per video (`PRICING.md` §7).

## 10. Credits, free allowance and purchases

### 10.1 Product rules (decided; every value lives in server config; numbers and derivation in `PRICING.md`)
- **Welcome allowance:** first 24 hours after account creation: **3 free videos**, up to 3 minutes each, no watermark.
- **Daily free video:** afterwards **1 free video per day**, up to 2 minutes, small watermark (bottom-right, below the caption band).
- **Credits:** consumable packs bought only through the stores: **$9.99 → 100**, **$19.99 → 220**, **$199.99 → 2,400** credits. A video costs **5 credits per started minute** (max 12 minutes). Credits never expire.
- **Spending order:** free allowance first, then credits. Paid videos are never watermarked; free videos can be re-rendered clean for 2 credits per minute.
- **Quote, then charge:** the app asks the server for a quote before create and before an AI edit, shows it, and the server charges exactly the quote.
- **Failures are free:** rejected prompts and failed renders/edits refund the charge.
- **Server-driven:** allowances, caps, credit cost, packs, watermark rules and AI-action prices come from `/config` and the wallet endpoint. Only store product ids and prices are fixed by the stores.

### 10.2 Unit economics
Target: **7x store-net revenue ÷ our cost.** The chosen formula and packs hold at least 7.2x at every length (1–12 min) under the mid cost estimate and a 15% store fee, and fall to roughly 4–6x if real cost is 60% higher or the 30% commission applies. Costs are estimates until real `cost_usd` data exists: see `PRICING.md` for the tables, sensitivity and recalibration plan.

### 10.3 Edits
Everything that needs no AI is free (reorder, delete, text/data changes, look, music, picking an already-found photo, previews). **AI actions cost credits priced from their real cost** (re-voice a scene 1, new photo search 1, AI-rewrite a scene 2 when it exists), with **3 free AI actions per video**, cache hits free, failures refunded, and a quote shown before rendering starts.

### 10.4 Architecture
- **Server owns the wallet.** A DynamoDB ledger (append-only transactions keyed by an idempotency id) + a balance item updated with conditional writes. Charge happens at `generate` (reservation), refund on reject/fail, so the existing REJECTED/failed paths keep working.
- **iOS purchase:** StoreKit 2 `Product.purchase(options: [.appAccountToken(userUUID)])` → send the signed transaction (JWS) to `POST /purchases/apple` → server verifies the Apple signature chain / queries the App Store Server API, credits the wallet **idempotently by transaction id**, then the app calls `transaction.finish()`. Server also subscribes to **App Store Server Notifications V2** (refunds/revocations → debit or flag).
- **Android purchase:** Play Billing Library `launchBillingFlow` with `obfuscatedAccountId` → send the purchase token to `POST /purchases/google` → server verifies with the **Google Play Developer API**, grants credits idempotently, then **consumes** the purchase (consumables must be consumed/acknowledged within the allowed window). Server subscribes to **Real-time developer notifications** for voided purchases.
- **Pending/deferred purchases** (Ask to Buy, slow payment methods) are handled as a visible "pending" state; credits arrive when the store confirms.
- **Abuse:** free allowance is per account; consider device attestation (App Attest / Play Integrity) before granting free allowances at scale.
- No purchases, prices or external payment links on the web app for now (store-policy risk).
- Verify against current Apple/Google billing documentation before implementing; the store rules and APIs change.

## 11. Sign-in

- **Providers:** Sign in with Apple (`ASAuthorizationController`) and Sign in with Google (Credential Manager on Android; Google Sign-In on iOS). Apple requires an equivalent privacy-preserving option when third-party login is offered, and we offer Apple itself.
- **Native one-tap, server-verified:** the app obtains the provider's ID token (with a nonce) and calls `POST /auth/social`. The server verifies signature (provider JWKS, cached), issuer, audience (our client ids), expiry and nonce, then maps to a **Cognito user** (link by provider subject; verified-email linking only when the provider asserts it) and returns normal Cognito tokens (custom-auth challenge flow). No passwords are stored. The web app keeps Cognito Hosted UI with the same federated providers.
- **Apple specifics:** the user's name is only delivered on first authorisation (store it then); private-relay emails are valid identities; on account deletion the server calls Apple's token-revocation endpoint.
- **Changeable:** enabled providers come from `/config`. An email/password path is kept behind a flag for App Review and QA (Apple reviewers need working credentials), and can be hidden in production builds.
- Tokens live in Keychain / Keystore-encrypted storage; refresh is silent; sign-out revokes the refresh token server-side.

## 12. Analytics and crash reporting (our own)

- **Principle:** the smallest thing that answers real questions. Nothing is sent to third parties; the stores' own consoles cover crashes/ANRs too (App Store Connect/Xcode Organizer, Play Console Android vitals).
- **Transport:** `POST /telemetry` (batched, gzip, size- and rate-limited) → a Lambda writes **one structured JSON log line per event** and emits **CloudWatch Embedded Metric Format** counters. Dashboards and ad-hoc questions use CloudWatch Logs Insights; alarms on a few metrics (e.g. crash-free sessions, sign-in failures, purchase-verification failures, render failures, API 5xx). Short log retention (e.g. 30 days). No idle cost.
- **Events (allowlist, versioned schema):** app_open, sign_in_started/succeeded/failed (provider only), create_started/succeeded/failed (length, look; **never the prompt text**), render_completed (duration), editor_opened, edit_submitted (op counts by type), preview/publish, purchase_started/succeeded/failed/pending, paywall_viewed, share, report_submitted, notification_permission result, screen views.
- **Crashes and hangs:** iOS via **MetricKit** diagnostics (crashes, hangs, CPU/disk exceptions) delivered on next launch; Android via an `UncaughtExceptionHandler` that writes a report to disk plus **`ApplicationExitInfo`** (ANRs, native crashes, OOM kills), uploaded on next launch. Each report carries app version/build, OS version, device model class, stack and a short breadcrumb trail (screen names, no content).
- **Symbolication:** keep each release's **dSYMs** and Android **R8 mapping files** in S3; a small script symbolicates a report on demand.
- **Privacy:** an install id (random, resettable, **not linked to the account**) instead of user ids; no prompts, narration, photo queries, emails or tokens; coarse OS/device class only. This lets the privacy label state diagnostics/analytics are not linked to identity: confirm against what actually ships.
- **Abuse:** the endpoint accepts anonymous traffic (crashes can precede sign-in), so it has an API key, payload and rate caps, schema validation and is never trusted for decisions.

## 13. What you will need to provide (never paste secrets into chat)

| Item | Where it goes |
|---|---|
| Apple: Team ID; register `com.videomk.app` with capabilities **Sign in with Apple, Push Notifications, In-App Purchase, Associated Domains**; App Store Connect API key (Issuer ID, Key ID, `.p8`) for CI uploads; APNs auth key (`.p8`); Sign in with Apple key; IAP products created for the three packs; App Store Server Notifications V2 URL set to our endpoint | CI secrets / AWS SSM SecureString (I'll tell you the exact names) |
| Google: Play Console app with application id `com.videomk.app`; Play App Signing SHA-256 fingerprint; service account JSON with Play Developer API access (for publishing and purchase verification); OAuth client ids (Android + Web) for Sign in with Google; a **Firebase project used only as the FCM push transport** (no Analytics SDK); Pub/Sub topic for real-time developer notifications; in-app products created for the packs | CI secrets / AWS SSM |
| Domain: host the `apple-app-site-association` and `assetlinks.json` files on videomk.com (universal/app links) | videomk.com |
| Legal: privacy policy and terms that match §10–12; support URL; data-safety/App Privacy answers; age/content ratings | store consoles |
| Accounts: tax/banking agreements completed in both consoles (required to sell) | store consoles |
| AWS: the target account/region for the backend (see the earlier question about the old account) | `backend` stage config |

## 14. Backend work this adds, in order of dependency
1. OpenAPI spec + golden fixtures. 2. Wallet/ledger, quote, free-allowance rules, config endpoint (replaces the daily quota). 3. `/auth/social`. 4. Purchase verification (Apple, Google) + store notifications. 5. Progress stages, pagination/ETag, devices + push, account deletion, reports, revisions, beat audio URLs. 6. Telemetry endpoint, dashboards and alarms.
