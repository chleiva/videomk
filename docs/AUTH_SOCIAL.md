# Sign in with Google and Sign in with Apple (contract for backend, web, iOS, Android)

Decided: both providers on web and both apps, through **Cognito federation** (hosted UI authorize endpoint with `identity_provider=`), not a custom
token exchange. Email and password stays. Every client keeps using Cognito tokens; the API never sees Google or Apple tokens.

Backend pieces: `backend/social_auth.py` (identity providers, outputs), `backend/lambdas/auth_presignup.py` (account linking), tests in
`backend/tests/test_social_auth.py`. Everything is OFF by default (CDK context flags), so today's stack deploys with no secrets.

## 1. Switching it on (CDK)
```
scripts/deploy.sh qa -c socialGoogle=1 -c socialApple=1      # either flag alone is fine
```
- Flags off: no identity providers, no trigger, both app clients list only `COGNITO` (template unchanged apart from three new outputs).
- Flags on: providers `Google` and `SignInWithApple` exist on the pool, **both** app clients (web `WebClient`, native `MobileClient`) list them next to `COGNITO`,
  and the pre sign-up trigger (account linking, section 4) is attached.
- Credentials are never in code, `cdk.json` or `stages.json`. The template holds CloudFormation dynamic references; CloudFormation reads the values at deploy time:

| Value | Where it lives (in the stage's own account and region) | Kind |
|---|---|---|
| Google OAuth client id | SSM parameter `/videomk/google_oauth_client_id` | String |
| Google OAuth client secret | Secrets Manager `/videomk/google_oauth_client_secret` | plain text secret |
| Apple Services ID | SSM parameter `/videomk/apple_services_id` | String |
| Apple Team ID (`39ANXJNUTL`) | SSM parameter `/videomk/apple_team_id` | String |
| Apple Key ID | SSM parameter `/videomk/apple_key_id` | String |
| Apple private key (.p8 file contents, including the BEGIN/END lines) | Secrets Manager `/videomk/apple_private_key` | plain text secret |

  (The two real secrets are in Secrets Manager because `ssm-secure` references are not accepted by the Cognito identity provider resource. About $0.40 per secret per month.)
- `app.py` checks, before synthesis, that every value needed by an enabled flag exists in the target account (using the stage's profile) and stops with the list of
  missing names. `-c socialSkipCheck=1` skips the check (synth only). CloudFormation would also fail at deploy with its own "can't find the specified secret/parameter" message.
- Stack outputs: `SocialProviders` (`none`, `Google`, `SignInWithApple` or both, comma separated), `SocialRedirectUri` (the exact URL to register,
  `https://<cognito domain>/oauth2/idpresponse`), `SocialAppleDomain` (the same host without the scheme, for Apple's Domains field). Cognito domain: QA uses
  `videomk-qa-<last 6 digits of the account>.auth.<region>.amazoncognito.com`; **prod uses our own host `login.videomk.com`** (`-c authDomain=login.videomk.com -c authCertArn=<ACM, us-east-1> -c authZoneId=<zone>`; `auth.videomk.com` is blocked by an external CloudFront alias conflict). The web app lives at **app.videomk.com**; Google's redirect URI stays `https://login.videomk.com/oauth2/idpresponse`, so the app host does not change the Google client. `AuthDomain` output.

## 2. Client contract (web and native)

Clients only change the authorize request; everything after it (callback, token exchange, refresh, logout) is the flow they already have.

**Authorize** (browser / `ASWebAuthenticationSession` / Android Custom Tab), `GET https://<AuthDomain>/oauth2/authorize` with query:

| Param | Value |
|---|---|
| `response_type` | `code` |
| `client_id` | web: `UserPoolClientId` output; native: `MobileClientId` output |
| `redirect_uri` | must exactly match a registered one. Web: `https://app.videomk.com/auth/callback` (dev `http://localhost:4321/auth/callback`; the CloudFront rewrite serves the folder page, so the registered string has no `index.html`). Native (both iOS and Android): `com.videomk.app://auth/callback` |
| `scope` | `openid email profile` |
| `state` | random per attempt, verified on return |
| `code_challenge_method` / `code_challenge` | `S256` / base64url(SHA-256(verifier)); PKCE on web too |
| `identity_provider` | `Google` or `SignInWithApple` (case sensitive). Omit it for the existing hosted form (email and password) |

With `identity_provider` set, Cognito skips its own page and redirects straight to Google or Apple. The user lands on `redirect_uri?code=...&state=...`.

**Token**: `POST https://<AuthDomain>/oauth2/token`, `Content-Type: application/x-www-form-urlencoded`, body `grant_type=authorization_code`, `client_id`, `code`,
`redirect_uri` (same as above), `code_verifier`. No client secret (both clients are public). Refresh as today (`grant_type=refresh_token`, native client refresh token lives 60 days).

**Logout**: `GET https://<AuthDomain>/logout?client_id=<id>&logout_uri=<registered logout url>` (web logout urls from `stages.json`; native `com.videomk.app://auth/signout`).
This ends the Cognito session only; the Google or Apple browser session stays (expected).

**What the id token looks like for a federated user**
- `sub`: the Cognito user id (a UUID). This is the only user id the API uses (`/users/{user}/...` must equal it). Unchanged.
- `cognito:username`: `Google_<google subject>` or `SignInWithApple_<apple subject>` for a user created by federation. For a user whose identity was **linked** to an existing
  email account, `cognito:username` and `sub` are those of the existing account and the provider shows only in `identities`.
- `identities`: JSON array like `[{"userId":"1234","providerName":"Google","providerType":"Google","issuer":null,"primary":"true","dateCreated":"..."}]` (absent for a pure email account).
- `email` always present when the provider gave one; `email_verified` is `true` for Apple, and for Google when Google says so. `name`, `given_name`, `family_name` when provided
  (Apple sends the name only the very first time the person authorises the app; it can be missing afterwards. Never require it).
- Clients should not branch on `identities`; they may show "Signed in with Google/Apple" from it.

**Errors and the retry rule** (the redirect comes back as `redirect_uri?error=...&error_description=...&state=...`)
1. **First federated sign-in after linking can fail** (documented Cognito behaviour): the description contains `Already found an entry for username Google_...`
   (or `SignInWithApple_...`). The link has been made; **start the authorize request again exactly once** (new `state` and PKCE pair, same `identity_provider`). The second attempt signs in.
   Match the text case-insensitively in `error_description`, whatever `error` says. If the second attempt fails the same way, show the generic error. Never loop.
2. `error=access_denied` (user cancelled at Google/Apple): return to the sign-in screen silently.
3. `PreSignUp failed with error ...` (the trigger refused, for example two confirmed accounts share the email): show "We could not sign you in. Contact support."
4. Anything else: generic "Sign-in failed, try again". Never show provider supplied text to the user, and never log tokens or the email.
5. Always verify `state`; reject a callback without a state this client created.

**Build-time switches** (clients only need to know whether to show each button; default OFF everywhere, set per environment):
| Client | Constants |
|---|---|
| Web | `PUBLIC_AUTH_GOOGLE=1`, `PUBLIC_AUTH_APPLE=1` (already read by `frontend/src/lib/config.ts`) |
| iOS / Android | `AUTH_GOOGLE`, `AUTH_APPLE` as 0/1 build settings per environment (debug/qa/prod), same meaning |
Turn a constant on only after that stage was deployed with the matching CDK flag and the owner steps below are done; a button for a provider that is not enabled on the pool
gets `invalid_request` from Cognito. Apple App Store review: once any third-party login is offered, Sign in with Apple must be offered too on iOS (guideline 4.8), so on iOS enable both together.

## 3. What to register at Google and Apple, per stage

Let `D` = the stage's `AuthDomain` host (e.g. `videomk-qa-225438.auth.eu-west-1.amazoncognito.com`, `videomk-prod-<tail>.auth.us-west-2.amazoncognito.com`).
**Federation never sends the browser from Google/Apple to the apps or the site directly**: both providers only ever call Cognito, so the app and web redirect URIs are
registered in Cognito (CDK does that), not at Google or Apple. The list per provider is therefore short and has one entry per stage.

**Google** (Google Cloud console, one project can hold all stages)
| Field | Value |
|---|---|
| OAuth client type | Web application (one client per stage, so each stage has its own secret) |
| Authorised JavaScript origins | `https://D` |
| Authorised redirect URIs | `https://D/oauth2/idpresponse` |
| Result | Client ID and Client secret |
No Android or iOS Google client is needed: the apps use the hosted UI in a browser sheet.

OAuth consent screen (once per project): User type **External**; app name VideoMK; support email; app home page `https://videomk.com`; privacy policy `https://videomk.com/privacy`;
terms `https://videomk.com/terms`; authorised domain `videomk.com` (verify it in Google Search Console first); scopes only `openid`, `email`, `profile` (non-sensitive: no Google verification review);
**Publishing status: In production** (in "Testing" only listed test users can sign in and refresh tokens die after 7 days).

**Apple** (developer.apple.com, team `39ANXJNUTL`)
1. The app's App ID (`com.videomk.app`) must have the **Sign in with Apple** capability (needed for the iOS app and as Primary App ID of the Services ID).
2. Identifiers, **Services IDs**, new (for example `com.videomk.signin.qa` and `com.videomk.signin.prod`, one per stage): enable Sign in with Apple, Configure:
   Primary App ID = the app's App ID; **Domains and Subdomains** = `D` (no scheme); **Return URLs** = `https://D/oauth2/idpresponse`.
3. Keys: new key with Sign in with Apple enabled (primary App ID as above). Download the `.p8` once (Apple will not show it again) and note the **Key ID**. One key can serve all stages.
- Apple does not accept `localhost` or http return URLs; none are needed (the return URL is Cognito's HTTPS domain).
- Domain association file: Apple's UI offers to verify a domain by a file at `/.well-known/apple-developer-domain-association.txt`. We cannot host files on `amazoncognito.com`. As far as
  documented setups show, Cognito's domain works without verifying it for sign-in; verification is only needed for Apple's "Email Sources" (sending mail to private relay addresses),
  which we do not use. **Not verified end to end**; if Apple refuses the unverified domain, the fallback is a Cognito custom domain on a hostname we control (`auth.videomk.com`,
  needs an ACM certificate in us-east-1 and DNS), which changes `D` for that stage.
- Client secret: Cognito builds Apple's client-secret JWT itself from Team ID, Services ID, Key ID and the private key, and refreshes it. Apple's 6 month maximum applies to a secret
  you sign by hand, not to this setup. **No rotation job is needed**; the only thing that can expire is the key if someone revokes it in the Apple console (then sign-in breaks:
  create a new key, update the two Secrets Manager/SSM values, redeploy).
- Apple sends name and email only on the first authorisation of a given Services ID. If a test person signs in once and the pool user is deleted, Apple will not resend the name until the
  person removes the app at appleid.apple.com, Sign in with Apple.

## 4. Account linking (the same person must not become two accounts)

Cognito **pre sign-up trigger** `auth_presignup` (only attached when a flag is on). For `PreSignUp_ExternalProvider` only; email and password sign-ups are not touched.
| Situation | Result |
|---|---|
| Provider email verified (Google `email_verified=true`; Apple: yes unless Apple says false) and exactly one **confirmed** pool user with that email and a verified email | Federated identity is linked to it (`AdminLinkProviderForUser`); `sub` stays the existing one; no new user, no second welcome credit |
| Provider email not verified, or missing | No lookup, no link. Federated user is created (auto-confirmed, email NOT marked verified) |
| Apple private relay address (`@privaterelay.appleid.com`) | Never matches anything: separate account. **Known limit, by design**: someone who hides their email from Apple gets a separate account from their email one |
| Existing email user is UNCONFIRMED, or its email unverified, or `FORCE_CHANGE_PASSWORD`, or not found | No link (an account whose email nobody proved could belong to an attacker who registered the victim's address first). Federated user created. Worst case is two accounts, never a takeover |
| Only another federated user has this email (for example Apple first, Google later) | Tries to link to that user; if Cognito refuses it falls back to a separate account. **Unverified** Cognito behaviour: needs one real test |
| Two or more confirmed users share the email | Trigger fails closed (error 3 above); support resolves |
| Same person signs up twice at once | The loser's "already linked" answer counts as success; the winner's result stands. Re-running the same event gives the same answer (idempotent) |
| Any unexpected Cognito error or throttle | Trigger raises, sign-in fails, client retries; it never silently creates a duplicate |
Least privilege: the function can call only `cognito-idp:ListUsers` and `cognito-idp:AdminLinkProviderForUser` on this pool. Logs carry a 10 character hash of the email, never the address.

### Welcome credit and abuse (checked)
- `common/wallet.ensure_grants` runs on the first wallet call of a `sub` (balance, charge, grant_paid) and grants the welcome credit through a conditional write on `META`
  (`attribute_not_exists`), so it happens **once per `sub`**, concurrent first calls included. A federated first sign-in is just a new `sub`, so it gets exactly one grant.
- Linking keeps the existing `sub`, so a linked person keeps one `META` row and cannot collect a second grant. Test: two sign-ups for one email end with one `sub` (trigger tests) and
  the wallet tests cover one grant per `sub`.
- Remaining gaps (documented, not new): (a) an Apple private relay user, or someone with several Google accounts, can still make several accounts, so several welcome grants;
  that is what DeviceCheck / App Attest (still waiting for the owner's key; unchanged here) and Play Integrity are for. (b) "free credits only for Apple/Google sign-in" in `docs/CREDITS.md`
  is still a plan: email sign-up still gets the welcome credit.

## 5. Account deletion (Apple and Google require it)

Built: see **docs/ACCOUNT_DELETION.md** (endpoint `POST /users/{user}/account/delete`, the SQS worker that removes every store and then the Cognito user, the staff script, the app contract).
Federated users are covered: the worker finds the pool user by `sub` (a federated user's Cognito username is `Google_...`/`SignInWithApple_...`, not the `sub`), and `AdminDeleteUser` drops the linked identities.
Afterwards the same Google/Apple account signing in creates a fresh account (new `sub`); an optional hashed tombstone (default off) withholds a second welcome credit.

**Apple token revocation** (required by Apple for apps with Sign in with Apple; guideline 5.1.1(v)): implemented behind the deploy flag `-c appleRevoke=1` (default off), exactly the design below, as a public callback `POST /account/apple-callback`
plus `POST /users/{user}/account/apple-revoke` (returns Apple's authorize URL with a signed state). Proven with a fake Apple server only; it has never run against Apple (docs/ACCOUNT_DELETION.md sections 4 and 9). The design, for reference:
1. Revoke call: `POST https://appleid.apple.com/auth/revoke` form fields `client_id`, `client_secret`, `token`, `token_type_hint=refresh_token`.
2. `client_secret` is an ES256 JWT signed with the `.p8` key: header `kid` = Key ID; claims `iss` = Team ID, `iat`, `exp` (at most 6 months ahead; one is minted per call, valid 5 minutes), `aud` = `https://appleid.apple.com`, `sub` = the `client_id` used in step 3.
3. The refresh token comes from `POST https://appleid.apple.com/auth/token` (`grant_type=authorization_code`, `code`, `client_id`, `client_secret`, `redirect_uri`). An authorization code is single use and must have been issued to **the same client_id** that exchanges it.
4. Cognito used the Services ID for the person's sign-in, so the only way to get a code for that same grant is to ask Apple again at deletion time (`https://appleid.apple.com/auth/authorize?client_id=<Services ID>&redirect_uri=<return URL>&response_type=code&response_mode=form_post&state=...`).
   The return URL is not Cognito's: add the stack output `AppleRevokeReturnUrl` as a **second Return URL** on the Services ID. (The native iOS dialog returns a code for the bundle id, which would revoke the app grant, not the hosted-UI Services ID grant; so it is not used.)
5. `cryptography` is in its own small layer `layers/apple_deps` (built with `layers/build_layer.sh apple_deps`, 12 MB); the `.p8` stays in Secrets Manager (`/videomk/apple_private_key`), Key ID and Team ID in SSM, readable only by the callback function.
Google needs no revocation call for Cognito federation (we keep no Google token).

## 6. Owner steps, in order
1. Google Cloud console, https://console.cloud.google.com/apis/credentials/consent : configure the consent screen as in section 3 and press **Publish app**. Verify `videomk.com` in https://search.google.com/search-console first.
2. https://console.cloud.google.com/apis/credentials : Create credentials, OAuth client ID, Web application, per stage: the origins and redirect URI from section 3 (get `D` from the `AuthDomain` output of the deployed stage; the pool domain exists today). Copy Client ID and Client secret.
3. https://developer.apple.com/account/resources/identifiers/list : confirm the App ID has Sign in with Apple; https://developer.apple.com/account/resources/identifiers/list/serviceId : create the Services ID per stage (section 3, fields: Description, Identifier, Sign in with Apple, Primary App ID, Domains `D`, Return URL).
4. https://developer.apple.com/account/resources/authkeys/list : create a key with Sign in with Apple, download the `.p8` (once), write down the Key ID.
5. Store the values in each stage's own account and region (profile of that stage):
   ```
   aws ssm put-parameter --profile <p> --region <r> --name /videomk/google_oauth_client_id --type String --value '<id>'
   aws ssm put-parameter ... --name /videomk/apple_services_id --type String --value 'com.videomk.signin.<stage>'
   aws ssm put-parameter ... --name /videomk/apple_team_id --type String --value 39ANXJNUTL
   aws ssm put-parameter ... --name /videomk/apple_key_id --type String --value '<key id>'
   aws secretsmanager create-secret ... --name /videomk/google_oauth_client_secret --secret-string '<secret>'
   aws secretsmanager create-secret ... --name /videomk/apple_private_key --secret-string file://AuthKey_<keyid>.p8
   ```
6. Deploy qa first: `scripts/deploy.sh qa -c socialGoogle=1 -c socialApple=1`. Redeploys must keep passing the flags (without them the providers are removed again).
7. Test on qa (nothing here was run against real Google or Apple): new Google user; new Apple user; email user then same-email Google (one `sub`, retry rule); Apple "Hide My Email" (separate account); cancel at provider; confirm the wallet shows one welcome grant.
8. Flip the client build constants for qa, then repeat for prod with prod's own Services ID, Google client and secrets.

| Per stage value | qa | prod |
|---|---|---|
| Google client id / secret | owner provides | owner provides |
| Apple Services ID | owner provides | owner provides |
| Apple Team ID | `39ANXJNUTL` | `39ANXJNUTL` |
| Apple Key ID / .p8 | owner provides (one key may serve both) | same or its own |
| Redirect URI / Apple Domain | from `SocialRedirectUri` / `SocialAppleDomain` of qa | same, from prod |

## 7. Unconfirmed sign-ups (abandoned email registrations)

Problem: a person who starts the hosted sign-up and does not enter the emailed code in time stays `UNCONFIRMED` with no password. They cannot sign in or reset the password (Cognito needs a verified email for `ForgotPassword`), and signing up again says "User already exists".

Fix (on by default): `backend/auth_cleanup.py` adds a scheduled Lambda (`lambdas/unconfirmed_cleanup.py`, EventBridge `rate(6 hours)`) that deletes pool users whose status is `UNCONFIRMED` and that were created more than 24 hours ago.
- Context: `-c unconfirmedMaxAgeHours=N` (default 24, minimum 1); `-c unconfirmedCleanup=0` removes the function and the rule.
- Safe by construction: an unconfirmed user has never signed in, so owns no data. Each user is re-read with `AdminGetUser` right before deletion and skipped unless still `UNCONFIRMED`; federated users (`EXTERNAL_PROVIDER` status, or any user with an `identities` attribute) are never touched; at most 200 deletions per run (a log line says when the cap is hit, the next run continues); throttling is retried with backoff.
- IAM: `cognito-idp:ListUsers`, `AdminGetUser`, `AdminDeleteUser` on this user pool only.
- Logs: counts and a short hash of the pool id only, never an email or username. Alarm on the line `UNCONFIRMED_CLEANUP deleted=N skipped=M` (a metric filter on `skipped` > 0 or a sudden large `deleted`).
- Manual fix before the cleanup runs: `aws cognito-idp admin-delete-user --user-pool-id <pool> --username <name>`.

App follow-up (not built): the apps' own sign-up UI should offer "Resend code" (`ResendConfirmationCode`) and a way back to the code screen when sign-up reports "User already exists" for an unconfirmed account, so people rarely wait for the cleanup.

## 8. The sign-in page (Managed Login, branded) - 2026-11-27
Owner feedback: the default Cognito page (grey header, "Sign in with your email and password", blue button) was ugly. It is replaced by **Cognito Managed Login** branded with the VideoMK lockup (since 2026-11-27 the B1 logo: the play and two stars on the action gradient tile, then the wordmark; `logo-light.svg`, `logo-dark.svg`, `favicon.svg` and `favicon.ico` in `backend/login_branding/` are written by `docs/brand/final/build_final.py` and reach the pools with the next backend deploy of each stage, because the branding is a CloudFormation resource of the stack).

- **Mechanism.** Pool domain on `ManagedLoginVersion` 2 (`NEWER_MANAGED_LOGIN`) plus one `AWS::Cognito::ManagedLoginBranding` per app client (web and mobile), from `backend/login_branding/` (settings document with light and dark, assets: lockup logo, page background gradient, favicons) wired by `login_branding/cdk.py` into `backend_stack.py`. On by default; `-c loginBranding=0` returns to the classic page. Tests: `backend/tests/test_login_branding.py` (colours well formed, WCAG AA contrast of every text/background pair in light and dark, no clutter, assets obey Cognito's rules, one branding per client, flag off).
- **Cost.** Managed Login needs the Essentials or Plus feature plan. Both pools are already on **Essentials**, so nothing changes in the bill: free up to 10,000 monthly active users per account (direct and social sign-ins), then USD 0.015 per MAU (third-party summary of AWS pricing, 2026-11-05; confirm on https://aws.amazon.com/cognito/pricing/). The classic page would have been only CSS plus a logo and cannot look like this.
- **Look.** Lockup above a single card, no heading clutter, one primary button (indigo `#4a3fc4` light, `#6a3fc4` dark, white text, 7.5:1 and 6.7:1), 14 px buttons, 12 px inputs, 20 px card, cyan focus ring on dark only, `colorSchemeMode: DYNAMIC` (follows the phone's light/dark setting). No side graphics, no header or footer. Social buttons (Google, Apple) sit ABOVE the email form with the standard provider icons.
- **Languages.** Cognito's own texts, English and Spanish: pass `lang=es` (or `en`) on `/oauth2/authorize`; without it the browser language decides. The apps already know their locale, so they should append `lang=<2-letter app language>` to the authorize URL (iOS `AuthService.beginSignIn`, Android `Auth.kt buildAuthorizeUrl`). Verified: `lang=es` gives "Iniciar sesion / Contrasena / Crear una cuenta".
- **When the social buttons show.** Managed Login lists the identity providers enabled on the app client. An authorize URL WITHOUT `identity_provider` shows the branded page with Google and Apple buttons above the email form (when enabled); WITH `identity_provider=Google` the page is skipped and Google opens straight away (what the app's own "Continue with Google" button does). Prod: Google is on. QA: no providers yet (no QA Google client, no Apple credentials), so only the email form shows there.
- **Managed Login also honours `prompt=login` and `max_age=0`** (the classic page ignored them), so the re-authentication step of account deletion (section 5, docs/ACCOUNT_DELETION.md) now really asks for the password again.
- **Editing the look.** Change `backend/login_branding/__init__.py` (colours, radii) or the SVGs in the same folder and redeploy. To iterate on QA without a deploy: `AWS_PROFILE=qa python backend/scripts/login_branding_preview.py --client <client id> [--scheme LIGHT|DARK|DYNAMIC]`; delete the preview branding (`--delete`) before a deploy that creates the same branding (a client can have only one). A change takes about 2-3 minutes to show (Cognito caches the page).
- **QA Google client (owner, unblocks the Google button on QA).** Google Cloud console, project of the prod client (or a separate one), Credentials, Create OAuth client ID, Web application: authorised JavaScript origin `https://videomk-qa-225438.auth.eu-west-1.amazoncognito.com`, authorised redirect URI `https://videomk-qa-225438.auth.eu-west-1.amazoncognito.com/oauth2/idpresponse`. Send me the downloaded JSON file path (or client id and secret) and I store them in QA (`/videomk/google_oauth_client_id` in SSM eu-west-1, `/videomk/google_oauth_client_secret` in Secrets Manager eu-west-1) and add `-c socialGoogle=1` to the QA deploy. Apple: section 6.
- **Known limits of Managed Login (verified 2026-11-27 on prod).** With a social provider enabled the page shows two small section headings ("With other accounts" / "With existing account"), the "Show password" checkbox and the Cognito wording: these texts cannot be changed (no custom-text API for them). Light and dark follow the device; there is no phone-width screenshot yet (the Chrome tool could not resize the viewport), the layout is a single centred column of 330 px and is responsive by design. Screenshots: `docs/ux_2026/signin/`.
