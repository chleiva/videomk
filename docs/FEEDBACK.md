# User feedback loop (contract for backend, web, iPhone and Android)

A signed-in person can send one phrase of feedback (an idea, something the app cannot do, a complaint). It is stored in a DynamoDB table and the owner gets **one plain-text email a day** listing what is new, and **no email on days with nothing new**.
Code: `backend/feedback_loop.py` (CDK), `backend/lambdas/feedback_api.py` (the route), `common/feedback.py` (validation, id, rate limit, store), `feedback_digest.py` (the daily email), `common/deletion.py` `step_feedback` (account deletion).
Web: `frontend/src/components/FeedbackPage.tsx`, `src/lib/feedback.ts`. Tests: `backend/tests/test_feedback.py`, `test_feedback_cdk.py`, `frontend/src/lib/feedback.test.ts`.

## 1. The request

`POST /users/{userId}/feedback`, `Authorization: <id token>` and `X-Locale` like every route. `{userId}` must be the token subject (else 403).

```json
{"text": "string, 3..2000 characters after trim", "kind": "idea|problem|other (optional)", "app": "ios|android|web", "version": "optional, at most 32", "locale": "en|es (optional)", "context": "optional, at most 64, e.g. settings|after_video|rating_prompt"}
```

| Answer | When |
|---|---|
| **202** `{"ok": true}` | Stored |
| 400 `{"message": "..."}` (localized) | Bad JSON or body over 16 KB, text shorter than 3 or longer than 2000 characters after trimming (only spaces counts as empty), a `kind`, `app` or `locale` outside the lists, `version`/`context` too long or not strings |
| 401 / 403 | No valid token / `{userId}` is not the token subject |
| **429** `{"message": "...", "code": "rate_limited"}` + `Retry-After: 3600` | More than 10 in the clock hour or 30 in the UTC day for this person |
| 500 | Our side; call again |

The text is stored verbatim except that control characters and invisible formatting characters (bidi overrides, zero width) are removed and line endings become `\n`. HTML is never rendered anywhere (the email is plain text); the text is never written to logs.
A missing `kind` is stored as `other`. Apps should keep the typed text and offer retry on any failure.

## 2. The table

`FeedbackTable` (CDK-named, pay per request, AWS-managed encryption, point-in-time recovery on, `RETAIN` on stack delete, **no TTL**: the owner keeps feedback). Key `feedbackId` (ULID, sorts by time).

| Attribute | Meaning |
|---|---|
| `feedbackId` | ULID |
| `userId` | the Cognito sub; after account deletion `deleted:<keyed hash>` |
| `createdAt` | ISO UTC |
| `text`, `kind`, `app`, `version`, `locale`, `context` | as sent (`kind` defaults to `other`, absent strings are empty) |
| `category` | **empty now**, reserved for the later classification (section 6) |
| `status` | `"new"` (owner triage: nothing sets it to anything else yet) |
| `pending` | `"1"` until the item is mailed, then removed (this is the sparse GSI key) |
| `emailedAt` | set when mailed |

Indexes: `GSI_Pending` (`pending`, `feedbackId`, all attributes): holds only what has not been emailed, so the daily run reads exactly the new items (a scan would read the whole table every day and grow with it). `GSI_User` (`userId`, `feedbackId`, keys only): lets the account deletion find a person's rows without a scan.
Rate limit counters live in the usage table (`feedbackh:<sub>` per hour, `feedback:<sub>` per day, both removed by the account deletion; the hour slot is given back when the day limit refuses).

How to read it: AWS console, DynamoDB, table whose name starts `...FeedbackTable...`, "Explore items". Newest first: query on the table with descending order is not available on a hash-only key, so sort by `createdAt`/`feedbackId`. CLI: `aws dynamodb scan --table-name <name> --profile <stage profile>`; to see only unmailed: `aws dynamodb query --table-name <name> --index-name GSI_Pending --key-condition-expression "pending = :p" --expression-attribute-values '{":p":{"S":"1"}}'`. The name is the stack output `FeedbackTableName`.

## 3. The daily email

EventBridge rule at **09:00 UTC** every day (`-c feedbackHourUtc=<0-23>` to change) runs `feedback_digest`. It:
1. reads the recipient from SSM String parameter **`/videomk/feedback_email_to`**. Missing parameter (or not an address): logs `FEEDBACK_DIGEST_NO_RECIPIENT` as a warning and does nothing; items stay pending and go out when the parameter exists.
2. reads `GSI_Pending`. Nothing: no email.
3. builds a plain-text email grouped by kind (problem, idea, other) with counts, subject `videomk feedback: 3 new`; each item shows time, app and version, locale, context, and a short hash of the user id (never the email address), then the text.
4. sends through SES, and **only after the send succeeds** removes `pending` and sets `emailedAt` for those items. A send error raises (the log line has the error code, never the text) and the next run sends the same items. Marking is per email part, so a failure in part 3 leaves parts 1 and 2 marked.
5. splits large batches: at most 100 items or about 120,000 characters per email (subject `... (part 2/3)`), at most 2000 items per run; the rest goes the next day. Residual risk: if marking fails after a successful send, those items are mailed again next day (at-least-once).

Sender: prod sends from `hello@videomk.com` (the identity of the `videomk-mail` stack, SES **us-east-1**; the function calls SES there from us-west-2, same account; IAM allows `ses:SendEmail` only with that From address). Change with `-c feedbackFrom=`, `-c feedbackSesRegion=`.
QA has no SES: with no `feedbackFrom` the function logs `FEEDBACK_DIGEST_SKIPPED no sender configured` and does nothing. To test in QA, verify an address in QA's SES (eu-west-1) and deploy with `-c feedbackFrom=<that address>`; the recipient must also be verified while QA is in the SES sandbox.
Prod SES: if the prod account is still in the SES sandbox, the owner address must be a verified identity (the forwarding destination `chris@agilegency.com` already is, from `docs/EMAIL_FORWARDING.md`), otherwise sending is rejected (error logged, items stay pending).

## 4. Flag

`-c feedback=0` removes everything (table excluded: it is `RETAIN`, so after switching off it remains in the account; delete by hand if wanted). Default on. Both states are tested (`tests/test_feedback_cdk.py`).

## 5. Account deletion and privacy

Step `feedback` keeps the text (owner value) and replaces `userId` with `deleted:<HMAC hash>` (same keyed hash as the safety records), so the row is no longer linked to the person. The privacy page says so (section "Feedback you send us", `frontend/src/data/legal/privacy.ts` and `privacy.es.ts`; marked for the owner's legal review like the rest). A person asking for one message to be deleted is handled by hand (it is in the table, find it by text).

## 6. Later: LLM classification

Nothing is built. The plug-in point: a Lambda on a DynamoDB Stream of the table (INSERT) or a daily batch over items with `category = ""`, which calls a small model and writes `category` (a short fixed list, for example `feature_request`, `bug`, `praise`, `unsupported_request`, `other`) and optionally `status`. The digest already reads whole items, so it can group by `category` once it is filled. The worker for account deletion needs nothing new (it only touches `userId`). Note the privacy page would then have to name the AI provider that sees the text.

## 7. Deploy and setup

1. Deploy the backend stack as usual (the table is created; nothing else is needed for the route).
2. Create the recipient once per stage: `aws ssm put-parameter --name /videomk/feedback_email_to --type String --value <owner address> --profile <stage profile> --region <stack region>`.
3. Prod SES: the `videomk-mail` stack must be deployed (identity `videomk.com`, DKIM). In the sandbox the recipient must be verified.
4. Web: nothing to configure; the "Feedback" menu entry and the link after a video appear with the next site deploy. The iPhone and Android apps code against section 1.

## Rating prompt (Android)

Code: `core/RatingPrompt.kt` (pure: `WatchTracker`, `RatingState`, `RatingPrompt`, injected clock and storage), `data/RatingStore.kt` (SharedPreferences `videomk_rating`, wiped with the account), `data/StoreReview.kt`, `ui/RatingUi.kt`. Tests: `RatingPromptTest`.

### What counts as a completed video
A video counts when one player session (inline or full screen) both (1) played forward, continuously, the distinct seconds covering at least 90% of the duration, and (2) reached within 1 s of the end (or the player reported the end). A seek breaks continuity: the jumped-over time is not credited, so dragging the scrubber to the end never counts; neither does skipping a large middle part. A forward step of more than 2 s between two 500 ms samples is treated as a jump. Coverage is a set of distinct seconds, so replaying the first half does not replace the second. Each distinct video id counts once, ever (the last 200 ids are remembered; the counter itself is unbounded). Coverage is per session: half inline plus half in full screen does not count.

### State machine
State: `completedCount`, `completedIds` (bounded), `askedCount` (0..3), `askedAtCount`, `lastAskedAt`, `done`.

* `recordCompletion(id)`: new id and not done: `completedCount + 1`.
* Eligible: not done, `askedCount < 3`, and `completedCount >= 11` for the first ask (ten earlier complete views plus this one), otherwise `completedCount >= askedAtCount + 10` (normally the 21st, then the 31st).
* `shouldShow`: eligible, no video playing, not creating (Create open or a video being sent), at least 2 minutes since launch, not an instrumented or fake-data (screenshot) run. The host (`RatingHost`) only evaluates it while the library is on screen, 1.5 s after arriving, and looks again every 15 s inside the first two minutes. Debug builds only: an empty file `rating_force` in the app's files folder forces it (still never during playback).
* `onShown`: the pre-prompt appeared; it uses one ask at once (`askedCount + 1`, `askedAtCount = completedCount`, `lastAskedAt = now`). So swipe, back, tap outside, "Maybe later", "Not really" and a tap on "Rate videomk" all mean "ask again after 10 more completed videos", until 3 asks were used. No penalty text.
* `onAlreadyRated` ("I already rated it"): `done = true`; never again, nothing is counted any more. The only way to end it early.

### Screens
"Enjoying videomk?" (soft bottom sheet) -> Yes: "Rate videomk" / "Maybe later" / "I already rated it"; Not really: the feedback sheet with context `rating_prompt` and the line "Sorry about that. What would make it better?" (no store review for unhappy people).

### Why the in-app review and no result handling
"Rate videomk" uses the Google Play In-App Review API (`com.google.android.play:review-ktx`). Google limits how often the sheet can appear and, by design, never says whether it appeared or whether the person rated, so the app cannot (and must not) react to the outcome; that is why the prompt is capped at 3 asks and never promises anything. If the flow is unavailable (no Play Store, an error) the Play Store listing opens instead: `market://details?id=<applicationId>`, then `https://play.google.com/store/apps/details?id=<applicationId>`.

### Feedback entry points (Android)
Settings row "Send feedback / We read every message" (context `settings`), a quiet link under a finished video (`after_video`), and the "Not really" path (`rating_prompt`). One sheet (`ui/FeedbackUi.kt`): 3 to 2000 characters with counter, optional Idea / Problem / Other chips, a light haptic on Send, a thank-you with a check and "Done". A failed send (offline, 429, 5xx) keeps the text, in memory for the app's lifetime, says it is saved and offers Try again. Request: `POST /users/{userId}/feedback` `{"text","kind"?,"app":"android","version","locale","context"}`.

## Rating prompt (iOS)
Code: `mobile/ios/Packages/VideoMKCore/Sources/VideoMKCore/RatingPrompt.swift` (pure, clock and `UserDefaults` injected, tests in `FeedbackTests.swift`), UI in `VideoMK/RatingPromptView.swift`, hook in `LibraryView.considerRatingPrompt`, playback in `PlaybackWatcher`.

### What counts as a watched video
`PlaybackCompletion` gets the player position about every 0.5 s. A step counts as watched time only when the position moved forward by at most 3 s (normal play, also at 2x); seeks (bigger jumps, or backwards) add nothing. A video is complete when watched time is at least 90% of the duration and the position is within 1 s of the end (the end-of-playback notification also feeds the check). Scrubbing to the end, or skipping around, never counts. Each distinct video id counts once (`completedCount`; the id set is capped at 500, the count is never lowered).

### State machine
* Threshold for the first ask: 11 completed distinct videos (10 earlier plus this one). Next threshold is `askedAtCount + 10` (21, then 31 when asked on time). At most 3 asks.
* Showing the sheet is an ask (`didShow`). Swipe down, tap outside, "Maybe later" and "Not really" all just wait for the next threshold, with no penalty text.
* "Rate videomk" and "I already rated it" set `done`: never again. (Owner rule was ambiguous about tapping through; we cannot know whether a review was written, and asking again after the person went to the store would feel like nagging, so Rate ends it.)
* "Not really" opens the feedback sheet (context `rating_prompt`, line "Sorry about that. What would make it better?"), never the store.
* Never when: `done`, 3 asks reached, same app version as the last ask (once per version), less than 2 minutes since launch, a video is playing, Create (or an upload) is in progress, another sheet is open, the person is on a video screen (it waits for the home screen, 1.5 s after arriving), UI tests, screenshot mode (`VMK_SHOTS_DIR`), fake-library runs, or the App Store id is still the placeholder.
* State is one JSON blob in `UserDefaults` key `vmk.rating.state` (counts, asked, askedAtCount, lastAskedAt, lastAskedVersion, completed ids, done). Account deletion wipes it with the rest of the defaults.

### Store link and the system prompt
"Rate videomk" opens `https://apps.apple.com/app/id<ID>?action=write-review`. The id comes from the single constant `AppStoreInfo.appID` (TODO: owner replaces `0000000000`; while it is the placeholder the prompt never shows). We deliberately do not call `SKStoreReviewController.requestReview`: Apple forbids tying it to a button, it is limited to three displays a year and shows nothing when throttled, so a "Rate" button would silently do nothing. The write-review page always works. Unhappy users go to feedback, not the store.

### Debug
Debug builds only: `VMK_DEBUG_SHEET=rating` shows the question at launch, `VMK_DEBUG_SHEET=feedback` opens Settings with the feedback sheet (fake library: sending always succeeds). UI tests: `VideoMKFeedbackUITests`.

### Feedback sheet (iOS)
`FeedbackView.swift` + `Feedback.swift` (`FeedbackComposer`). Entries: Settings row (context `settings`), quiet link under a finished video (`after_video`), "Not really" (`rating_prompt`). Send is pinned above the keyboard. Failures keep the text and also save it in `UserDefaults` (`vmk.feedback.draft`), cleared only on success; 429 says to try later.
