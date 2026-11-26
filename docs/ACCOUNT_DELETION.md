# Account deletion (contract for backend, iPhone, Android and web)

Apple (guideline 5.1.1(v)) and Google Play require deleting an account from inside the app. This file is the contract the two app builders implement and the description of what the backend does.
Code: `backend/lambdas/account_api.py` (the API), `common/deletion.py` (the steps), `account_deleter.py` (the worker), `common/apple.py` + `apple_revoke.py` (Sign in with Apple), `backend/account_deletion.py` (CDK),
`backend/scripts/account_admin.py` (staff). Tests: `tests/test_account_deletion*.py`, `tests/test_account_apple.py`.

## 1. The request

`POST /users/{user_id}/account/delete`, `Authorization: <id token>` like every other route, body `{"confirm": "DELETE"}`. `{user_id}` must be the token's `sub` (same rule as every API).

| Answer | When | Body |
|---|---|---|
| **202** | Deletion started, or already under way, or already finished (calling again is harmless and needs no new sign-in) | `{"status": "deleting", "apple": "not_linked" \| "revoke_available" \| "revoke_off" \| "unknown"}` |
| **401** | The sign-in is older than 10 minutes (or `auth_time` is missing): see section 2 | `{"message": "...", "code": "reauth_required", "max_age_seconds": 600}` |
| 401 | No valid token | `{"message": "Unauthorized"}` (API Gateway's own 401 comes before this) |
| 403 | `{user_id}` is not the token's `sub` | `{"message": "Forbidden"}` |
| 400 | Body is not JSON, or `confirm` is not exactly `"DELETE"` | `{"message": "...", "code": "confirmation_required"}` for a wrong word |
| 500 | Something failed on our side; nothing was started, call again | `{"message": "Something went wrong. Please try again."}` |

`apple`: what the app must do about the person's Sign in with Apple grant (section 4). Older app builds can ignore the field.
The 202 means "accepted": the deletion runs in the background (section 5). The call is idempotent: a second call while deleting, after a retry by the network layer, or after completion answers 202 again (a deletion that got stuck is also restarted by calling again).

## 2. Recent sign-in (re-authentication)

The token's `auth_time` claim must be at most **10 minutes** old, otherwise 401 `reauth_required` and **nothing is started**. The app then runs a full interactive sign-in again (password, or Google/Apple) and repeats the call with the new token.
Do not use the refresh token for this: a refreshed token does not prove a new sign-in (the Cognito docs do not say that `auth_time` changes on refresh; treat it as unchanged).

**Which parameter makes the Cognito sign-in page ask again.** Checked in the Cognito documentation (https://docs.aws.amazon.com/cognito/latest/developerguide/authorization-endpoint.html):
* `prompt=login` ("Amazon Cognito requires users to re-authenticate even if they have an existing session") is **"Available in the managed login branding version only, not in the classic hosted UI"**.
* `max_age=<seconds>` is documented for step-up authentication and: "With the hosted UI (classic), Amazon Cognito silently ignores `acr_values` and `max_age`".
* Our pool uses the **classic hosted UI** (`user_pool.add_domain(cognito_domain=...)` without `managed_login_version`), so today neither parameter has an effect on the sign-in page.

What the apps must do now (works with the classic hosted UI, verified only by reading the docs, test it on qa):
1. End the hosted-UI browser session first: open `GET {AuthDomain}/logout?client_id={MobileClientId}&logout_uri=com.videomk.app://auth/signout` (the sign-out URL the app already uses) and wait for the redirect back. On the web, the same with the web client and logout URL.
2. Then open the normal `/oauth2/authorize` (code + PKCE as for sign-in). On iPhone also use `ASWebAuthenticationSession.prefersEphemeralWebBrowserSession = true` so no earlier cookie is reused.
3. Also append `prompt=login&max_age=0` to the authorize URL. The classic UI ignores them, but they make this correct without an app change if the owner later moves the pool to managed login (which adds the Essentials plan cost and a branding setup; not done).
4. After sign-in, use the **new** id token for the delete call. If the answer is still 401 `reauth_required` the sign-in was reused: tell the person to try again and, on failure, point at the email route.
For people who sign in with Google or Apple, Cognito only forwards `prompt` (not `max_age`) to the provider and only in managed login, so Google/Apple may sign the person in silently with their own session. The backend rule (a fresh `auth_time` from Cognito, set when Cognito completes the authentication) still decides.
**Unverified** until tried on qa with a real Cognito pool: that `auth_time` is fresh after a hosted-UI sign-in that reused a session, and for federated sign-in. If it is not, the failure is safe (401), and switching the pool to managed login is the fix.

## 3. What the app does around it

Before: a confirmation screen: "This deletes your account, videos, photos and credits for good. Credits you have left are lost." Ask the person to type `DELETE`, then re-authenticate (section 2).
After 202 (and, if `apple` is `revoke_available`, after the Apple step in section 4):
* sign out of the app (do **not** call the Cognito sign-out of the hosted UI as a way to "finish": the account is already switched off server side), delete the stored tokens, and
* clear everything local: Keychain/Keystore tokens and Apple credential, caches of videos, thumbnails and library photos, downloaded files, the user id, drafts, saved prompts, settings that belong to the person (language and similar can stay), any analytics id, and push token registration if the app has one;
* show: "Your account is being deleted. Your data is removed within minutes and your sign-in within about an hour or two. If you want to sign up again with the same email, please wait until then." Then return to the signed-out screen.
If the call fails (network, 5xx), keep the person signed in, say it did not go through, and let them retry; the call is idempotent. After a 202, a later sign-in attempt fails (the account is disabled at once, and later removed): the app shows the normal sign-in error.

## 4. Sign in with Apple (required by Apple when the app offers it)

Cognito never gives Apple's refresh token to anyone, so the app must ask Apple again, at deletion time, for a fresh authorization code and the backend revokes it. Behind the deploy flag `-c appleRevoke=1` (default OFF, so `apple` is `revoke_off` for linked accounts until the owner finishes section 8).

When the delete answer says `"apple": "revoke_available"` (the person's account has a Sign in with Apple identity, found from the Cognito `identities` attribute, also when Apple was linked to an email account):
1. `POST /users/{user_id}/account/apple-revoke` with `{"return": "app"}` (`"web"` on the website). Needs a deletion under way. Answer `200 {"authorize_url": "https://appleid.apple.com/auth/authorize?...", "expires_in": 600}`. Errors: 404 `apple_revoke_off`, 409 `not_deleting`, 409 `no_apple_identity`, 410 `account_deleted`.
2. Open `authorize_url` in `ASWebAuthenticationSession` (iPhone), a Chrome Custom Tab (Android) or a normal redirect (web). The person confirms with Apple (Face ID or Apple ID password). Apple POSTs to our public callback, which exchanges the code, checks that the Apple account is the one linked to this person, revokes the refresh token at Apple, and **redirects the browser** to `com.videomk.app://auth/apple-revoked?status=<s>` (app) or `https://<site>/delete-account?status=<s>` (web).
   `<s>`: `ok`, `cancelled` (the person closed Apple's page), `mismatch` (they chose a different Apple account: nothing was revoked), `failed` (Apple or our side failed), `invalid` (expired after 10 minutes or not ours). The app registers the custom scheme `com.videomk.app://auth/apple-revoked` (same scheme as sign-in).
3. On anything but `ok` show: "To finish, open Settings on your iPhone, tap your name, Sign in with Apple, videomk, and choose Stop using Apple ID." The deletion itself never waits for this and is never blocked by it. The step can be done any time in the first hour (until the account is removed); a person who skips it just keeps an unused entry in their Apple settings.
The Apple step may be done right after the 202, with the same token (still valid for an hour). On `revoke_off`/`unknown`/`not_linked` skip it (for `revoke_off` show the manual instruction above).
Google needs nothing: we keep no Google token. Telling the person to remove videomk under Google Account, Security, Third-party access is optional and in the web text.
Design notes (section 8 for what is proven): the code is issued to the **Services ID** (the same client Cognito used), so the backend must use the Services ID, not the bundle id; the `state` is HMAC-signed, names the account and the expected Apple user id, and lives 10 minutes; tokens exist in memory only for the two Apple calls and are never stored or logged; the private key is readable only by the callback function.

## 5. What the backend does, and how long it takes

`202` writes a job (`job#<sub>` in the deletion table) and queues one SQS message; a worker runs the steps in order and records each one. Every step is idempotent. A failing step is logged `ACCOUNT_DELETION_FAILED user=<sub> step=<step> error=<class>/<aws code> attempt=<n>`, retried with backoff (30 s doubling, at most 15 min, 30 tries in a row, about 7 hours), then the job is `stuck` (`ACCOUNT_DELETION_STUCK`) and staff finish it. Nothing is ever skipped silently; no address is ever in a log line. The Cognito user is deleted **last**.

| # | Step | What |
|---|---|---|
| 1 | begin | Disable sign-in (`AdminDisableUser`) and revoke refresh tokens (`AdminUserGlobalSignOut`). The wait of step 10 starts here. |
| 2 | executions | Stop the person's running video workflows (generation executions are named `<video id>`; edit executions `<video id>-r...`), so nothing is written during the rest |
| 3 | media | Library: S3 Vectors keys `<sub>:<photo>` (strict: an error stops the step), S3 media bucket `o/<sub>/` and `t/<sub>/`, then every row of the media table partition (`m#` photos, `h#` hashes, `c#` collections, `cm#` collection items, `prefs`, `facets`, `stats`). Vectors of photos without a row are found through their files. |
| 4 | videos | For every video (rows of GSI `GSI_UserVideos` plus ids found in `videos/<sub>/`): S3 `generation/v2/<video>/` and `generation/assets/<video>/` (plans, audio, assets, previews, segments); then `videos/<sub>/` and `uploads/<sub>/` (which includes uploaded decks and their prepared slides; the quota counters `deck:`/`deckproc:` are in the usage prefixes, `uploads/<sub>/decks/`, docs/DECK_TO_VIDEO.md); the rows of the videos table last |
| 5 | wallet | Every row of the wallet partition (`META`, `B#...` buckets, `REF#...` purchase ids) |
| 6 | usage | Usage partitions `<sub>`, `upload:<sub>`, `libup:<sub>`, `libsearch:<sub>`, `brief:<sub>`, `unlimited:<sub>`, `dup:<sub>`, `edit:<sub>` |
| 7 | flags | Flags table keys `<sub>` (entitlements, unlimited) and `safety:<sub>` (hold, cleared-at) |
| 8 | safety | Safety table records of the person are **re-keyed** (section 6) |
| 9 | tombstone | Only with `-c accountTombstone=1` (section 7) |
| 10 | settle | Wait until every token issued before step 1 has expired: 65 minutes (3600 s token life + 300 s). Without it a token still valid for an hour could recreate a row after the deletion. |
| 11 | recheck | All data steps again (a late request, a late upload, a workflow that ended after being stopped) |
| 12 | cognito | `AdminDeleteUser` (drops linked Google and Apple identities; the same Google/Apple account signing in later is a brand new account) |
| 13 | finish | Job marked done; the job record (user id and step times only) is removed by DynamoDB TTL after 30 days |

**Timing for the person's message**: the data is gone in minutes (a person with thousands of photos: a few more messages of 10 minutes each); the sign-in is switched off at once; the Cognito account disappears about **65 to 75 minutes** after the request (same email can sign up again then). A new `sub` that signs in with the same email earlier gets "an account with this email exists" from Cognito.
The wallet refuses a welcome credit or any new row to an account whose job exists (`common/wallet.ensure_grants`), so a valid old token cannot make a new wallet.

Not deletable by us, to say honestly: Step Functions keeps each execution's history (it contains the request text, input of the workflow) for 90 days after the execution ends, and there is no API to delete it; CloudWatch logs expire after 14 days (they hold the user id, no address); AI providers see the text and images at request time and are not allowed to keep or train on them (see the privacy policy); Apple and Google keep their own purchase and sign-in records; DynamoDB point-in-time backups (prod, wallet/flags/safety/videos tables) roll off after 35 days. The privacy page says logs are deleted after 14 days: the 90-day Step Functions history is a gap to disclose or close (owner, section 9).

## 6. Safety records (privacy policy: "type of reason, time, short excerpt (160 characters), fingerprint of the request, 90 days")

At deletion each record of the person is copied to the same table under `user_id = "deleted:" + HMAC(key, "acct" + sub)[:32]` with exactly `category`, `severity` (derived from the category), `ts`, `excerpt` (<= 160), `prompt_hash` (the request fingerprint) and the **original expiry** (90 days from the stop, not restarted), then the original is deleted. Dropped: `source`, the sub itself, everything else. Expired records are simply dropped. Enforcement (pauses, holds) reads by `sub` and therefore no longer sees them: a person who deletes the account while on hold also leaves the hold behind (documented gap, owner decision in section 9).
The privacy page gets one added clause for this (marked for owner review).

## 7. Welcome credit after delete-and-sign-up-again (tombstone) , OWNER DECISION

Without anything, deleting and signing up again gives a new `sub` and a new welcome grant (5 credits, 30 days). Option, switched off by default (more private): `-c accountTombstone=1 [-c tombstoneDays=90]`.
* Stored at deletion: `tomb#e#<HMAC(key, "email" + normalised verified email)>` and, for Google/Apple users, `tomb#u#<HMAC(key, "username" + Cognito username)>` (Google/Apple provider id). Normalised: lower case, no `+tag`, no dots for gmail. Only **verified** emails; hashes only, with an expiry (`expires_at`, also the DynamoDB TTL). No email, no sub, no link to the deleted account.
* Checked once per new `sub`, at its first wallet call: a match withholds only the one-time welcome credits (the daily free credit still works; the person is not blocked). Fails closed on a lookup error (the wallet call is retried).
* The key is a Secrets Manager secret generated by the stack (`videomk/<stage>/deletion_key`, about 0.40 USD a month); without the key the hashes cannot be recomputed or guessed.
* Period: 90 days, the same window the policy already uses for safety records; it must be at least the welcome credits' 30 days, and longer only adds privacy cost. Weakness: a different email, an Apple relay address, or a different Google account gets through (as with any account today; DeviceCheck/App Attest/Play Integrity are the real answer).
* Proposed privacy sentence if switched on (owner/legal to approve): "To stop the one-time welcome credits being collected twice, when you delete your account we keep a scrambled one-way code (a hash) of your verified email address or sign-in name for 90 days. It cannot be turned back into your address and is not linked to any of your content."
Recommendation: leave it OFF until abuse is seen; it is easy to switch on (one flag, redeploy). When OFF the deletion table never holds an email-derived value.

## 8. Operations and owner steps

* **Deploy** (qa first): `scripts/deploy.sh qa` creates the routes, queue, worker, table, secret and alarms. The stack gains `AccountDeletionTable`, `DeletionKey` secret, `DeletionQueue`/`DeletionDlq`, functions `account_api` and `account_deleter`, a log metric filter and two alarms (`ACCOUNT_DELETION_FAILED|STUCK|WORKER_ERROR` in the log, and any message in the dead-letter queue). **No alarm action is attached: choose one** (SNS topic to email or chat).
* **Staff**: `AWS_PROFILE=qa python backend/scripts/account_admin.py show|delete|retry|complete <email|sub> [--now]` (inspect, start at a written request, requeue a stuck job, run it to the end with your credentials; `--now` skips the 65 minute wait). `delete` is the tool for the email route of the web page.
* **Apple (flag)**: needs `backend/layers/build_layer.sh apple_deps` (cryptography 43, 12 MB) and the values of `docs/AUTH_SOCIAL.md` section 6 (Services ID, Team ID, Key ID in SSM, the `.p8` in Secrets Manager `/videomk/apple_private_key`). Deploy `scripts/deploy.sh qa -c appleRevoke=1` (plus the social flags you already pass; **redeploys must keep passing every flag**). Take the stack output `AppleRevokeReturnUrl` and add it as an additional **Return URL** of the Apple Services ID (Apple developer account, Identifiers, Services IDs, Configure). The key must have Sign in with Apple enabled.
* Redeploys must keep `-c accountTombstone=1` if you switch it on, or the check stops (the deletion table keeps its rows).

## 9. What is proven and what is not

Proven by tests (no network): every step on fake AWS, each store empty afterwards and another person's data untouched, resume after a failed step and after running out of time, stuck and retry, the Cognito user deleted last and only after the stores are empty, idempotency, path user must equal token sub, the recent sign-in rule and its edges, the safety re-key (allowed fields, original expiry, hashed reference), the tombstone (off by default, hashes only, plus/dots, expiry, fails closed), the Apple client secret (ES256, claims, signature verified with the public key), the signed state, the callback against a fake Apple server (single-use code, mismatch, errors, no secrets in logs), CDK: the routes and authorizer, every table, bucket and vector index of the stack is either cleaned or explicitly exempt (a new one fails the build), the S3 prefixes and usage keys the code writes are all covered, the worker's IAM has no wildcard resource and no read of user data, only the worker can delete Cognito users or stop executions, only the Apple function can read the Apple key.
**Not proven (needs a deployed qa, and for Apple the owner's credentials)**: that the hosted-UI sign-in after `/logout` yields a fresh `auth_time` (also for Google/Apple); that Apple accepts a code obtained with `response_mode=form_post` and no `scope` and issues a refresh token for the revoke (Apple's documentation describes it; never run); that the redirect from the callback (HTTP 303 to a custom scheme) is picked up by `ASWebAuthenticationSession` and Chrome Custom Tabs; the real S3 Vectors `DeleteVectors` call on a missing key (assumed idempotent); Step Functions `StopExecution` on an already finished execution (handled either way); the CloudWatch metric filter and alarms attach (synth only); the 12 MB layer on real Lambda.
**Owner decisions**: tombstone on or off (section 7); alarm action; whether to move the pool to managed login for a real `prompt=login`; the 90-day Step Functions history versus the policy's "14 days"; whether a deleted account on a safety hold may leave the hold behind; purchase records (the wallet table holds credit rows, not receipts; no purchase flow exists yet, so nothing is kept: when real purchases arrive, decide what accounting records to keep and add them as a separate, minimal table that the worker leaves alone); legal wording of the web page and the privacy sentences (marked `OWNER REVIEW` in the sources).
