# Plans, phase 1: entitlements, limits, the free plan's cost controls (built 2026-11-27)

The owner approved the ladder of `docs/PLANS_PROPOSAL_2026-11-27.md` on 2026-11-27 and then tightened the Free plan the same day ("no funding to burn on free usage"). This document is the contract for the backend that exists now. **No store purchases yet**: plans are set by an admin; every answer says `can_upgrade: false`; the purchase routes exist and answer 501 (section 9).

Switch: plans are on by default in the stack (`backend/plans_feature.py`); `-c plans=0` removes all of it and every function behaves exactly as before. Code: `lambdas/common/plans.py` (the ladder and the knobs), `entitlements.py` (the record), `free_grants.py` (free allowance, eligibility, budget), `device_proof.py`, `plan_report.py`, `lambdas/plan_gate.py` (launcher side), `plans_api.py`, `gallery_api.py`, `device_api.py`, `plans_daily.py`. Tests: `tests/test_plans.py`, `tests/test_free_grants.py`, `tests/test_plans_cdk.py`.

## 1. The ladder (ONE place: `common/plans.PLANS`)

| | Free | Pro | Max |
|---|---|---|---|
| Price (US base; the stores decide once products exist) | 0 | $14.99 a month, $149.99 a year | $39.99 a month, $399.99 a year |
| Plan credits | none | 30 at each monthly date, unused ones end | 120 at each monthly date, unused ones carry over one month, plan balance never above 240 |
| Free credits | see section 3 (default: 2 welcome credits, once, from the mobile app; no daily credit) | | |
| Longest video | plan ceiling 1 minute; **active cap = the knob `free_max_seconds`, default 30 s** | 5 minutes | 12 minutes |
| Resolution | 720p, 1080p (knob `free_max_resolution`) | 720p, 1080p | 720p, 1080p, 4K (4K costs double credits, as before) |
| Watermark | forced: videomk with the name (`style: lockup`) and the end card | may remove it; "moments" mode | same, plus own logo |
| My media storage | 2 GB | 100 GB | 300 GB |
| Photos per video | 10 | 30 | 60 |
| Queue | standard | standard | priority (recorded on the video, section 5) |
| Premium looks (3D backgrounds) | no | no | yes (`premium_looks: true` in the workflow input) |
| Use | personal | commercial | commercial |

Unchanged rule: 1 credit per started minute (15 to 60 s = 1 credit), 4K doubles it. One plan per account, whatever the platform (one record, section 2).

**Unlimited test accounts** (the admin flag in the flags table, never honoured in production) keep working: they are never charged, bypass every free-plan rule, and have the **rights of Max** (12 minutes, 4K, own logo, 300 GB, 60 photos). Their videos are recorded with `plan: "test"`.

## 2. The entitlements record

One item per account in the entitlements table (`ENTITLEMENTS_TABLE`, key `user_id`):
`{plan: free|pro|max, state: active|grace|expired|refunded, source: admin|apple|google|web, interval: month|year, anchor, period_start, period_end (absent = no end), grace_until, renews, product_id, updated_at, log (last 20 changes)}`.

* **Who can write it:** nobody at runtime. The table is read-only for every function that serves a request (checked on the synthesized template for every function, `tests/test_plans_cdk.py`); the writers are an admin with AWS credentials (`scripts/wallet_admin.py plan ...`), the account-deletion worker (DeleteItem only) and, in phase 2, the purchase-verification functions. No route accepts a plan; a test fails if a request handler calls a writer.
* **Who can read it:** the owner of the account, through `GET /users/{user}/plan`, the wallet and capabilities (path user must equal the token's `sub`: another person's plan is a 403).
* **What applies now** is computed, not stored (`entitlements.evaluate`): an `active` record past `period_end` is expired without any job having to flip it; within `grace_until` it is `grace` (rights stay, no new credits); `expired` and `refunded` are Free.

| Transition | Rights | Plan credits |
|---|---|---|
| Plan set (admin now, purchase later) | the plan's, at once | the month's grant on the next wallet read |
| Renewal (phase 2: same `anchor`, new `period_end`) | unchanged | next monthly grant |
| Yearly plan | 12 months | **12 monthly grants**, never 360 or 1,440 at once |
| Billing grace (16 days by default, the stores' setting) | kept | none for the unpaid month; Max's carried month stays |
| Expired (date passed, or `plan free` by an admin) | Free | unused plan credits removed at the next read |
| Refunded | Free | unused plan credits removed (`wallet.revoke_plan_credits`); a balance never goes below zero; credits already spent are not clawed back |
| Upgrade Pro to Max mid-month | Max at once (a new `anchor`) | Pro's remaining credits keep their own date, Max's 120 arrive; plan balance capped at 240 |
| Downgrade Max to Pro | Pro | what is left keeps its own date; nothing new is added while the balance is at or above Pro's 30 |

**Plan credits** are a wallet bucket kind `plan`. A grant is keyed by plan, anchor and month (`PLAN#<plan>#<anchor>#<k>`), written in the same transaction as the bucket, so it happens once under any concurrency. Grants are made when the wallet is read or a video is started (no daily job): a wallet not opened for months catches up only on what is still valid. Spending order is unchanged: soonest to expire first (so a paying account's leftover welcome credits go before its plan credits).

Lapsed plans: storage over the Free limit becomes read-only (nothing is deleted, as designed in `docs/MEDIA_LIBRARY.md`), finished videos keep their look, a saved watermark setting the plan no longer allows falls back quietly to the videomk mark.

## 3. The Free plan and its knobs (the owner's cost controls)

**Problem:** a heavy free user costs $4 to $6 a month. So the Free plan is small by default and every number is a setting that changes **without a deploy**.

Where: one SSM parameter per stage, `/videomk/<stage>/plans/config`, a JSON object. It is not part of the stack: absent means every default, the first `config set` creates it, and a deploy can never reset it. Functions cache it for 60 seconds; an unreadable value keeps the last good one, an invalid knob falls back to its default. Change it with:
```
python backend/scripts/plans_admin.py config show [--stage qa|prod]
python backend/scripts/plans_admin.py config set <knob> <value> [--stage prod]      # checked before saving, live within a minute
python backend/scripts/plans_admin.py config reset <knob>
python backend/scripts/plans_admin.py gallery-only on|off                           # welcome_credits 0 + daily off, or back to the defaults
```

| Knob | Default | What it does |
|---|---|---|
| `welcome_credits` | **2** | One-time welcome allowance. 0 = none. |
| `welcome_valid_days` | 30 | How long the welcome credits last. |
| `free_daily_credits` | **0 (off)** | The recurring free credit. 1 switches the daily credit on (expires that night, as before). |
| `free_credit_cadence` | `daily` | `weekly` = the credit can be claimed on at most `free_credits_per_week` days of a calendar week. |
| `free_credits_per_week` | 3 | See above. |
| `free_max_seconds` | **30** | Longest Free video. The plan definition says "up to 1 minute"; this is the active cap (15 to 720). |
| `free_max_resolution` | `1080p` | Highest Free resolution (`720p` or `1080p`). |
| `free_daily_budget_credits` | **15** | The GLOBAL budget: all free credits spent by all accounts in one UTC day. At $0.15 per credit that is **about $2.25 a day, about $70 a month at the very worst**. Reached: free creation pauses until 00:00 UTC. 0 = no free creation. |
| `free_budget_unlimited` | false | true removes the global budget. |
| `cost_per_credit_usd` | 0.15 | The measured cost of a credit (p50, 85 QA videos). Only used to show dollars next to credits in the admin tools and reports. |
| `free_monthly_videos_cap` | 0 (off) | Per account and calendar month (UTC): videos paid with free credits. |
| `free_web` | **false** | May the web grant or spend free credits. Off: a Free account on the web is gallery-only. |
| `require_device_proof` | **true in production, false elsewhere** | Free creation needs a verified device proof (section 7). The stage default comes from the stack; the knob overrides it. |
| `device_proof_ios`, `device_check_ios`, `device_proof_android` | true, false, false | Which proofs are accepted (section 7). |
| `device_pass_minutes` | 15 | How long one verified proof lets the account spend free credits. |
| `block_disposable_email`, `email_domain_deny`, `email_domain_allow` | true, [], [] | Section 7. |
| `claims_per_ip_day`, `claims_per_ip_block_day`, `signups_per_ip_hour` | 3, 10, 5 | Velocity limits (0 = no limit). |
| `claim_retention_days` | 730 | How long a free-allowance claim (a salted hash) is kept. |
| `enforce` | true | false: plan limits are reported but not enforced at the launcher (an emergency switch). |

**Three states of the Free plan, all supported end to end** (`free_creation` in the wallet, capabilities and `GET .../plan`):

| `free_creation` | Knobs | What a Free account can do |
|---|---|---|
| `welcome` (default) | `welcome_credits` > 0, daily off | 2 short videos from the mobile app, then the paywall |
| `daily` | `free_daily_credits` > 0 | the welcome credits plus the recurring credit |
| `none` (**gallery-only**) | `welcome_credits` = 0, daily off | sign in, watch the gallery and its own videos, see the plans; Create is locked with the upgrade path |

In every state the apps read **`free`**: `{mode, available, reason, message, credits_left, max_seconds, budget_paused, resumes_at, pending}`. (`pending: true` only appears when a read-only call such as capabilities came before the account's first wallet read: the welcome credits are granted by `GET .../wallet`, by `generate` or by the device verify call, so read the wallet first.) `available: false` comes with one public `reason`:

| `reason` | Meaning | What the app shows |
|---|---|---|
| `off` | no free creation is offered (gallery-only mode) | the gallery and the paywall instead of Create |
| `app_only` | this is the web; free videos are made in the mobile apps | gallery, "get the app", paywall |
| `not_available` | not for this account (the server never says which rule) | paywall; the account still watches and can pay |
| `paused` | today's global free budget is used up (`budget_paused: true`, `resumes_at`) | "Free videos are done for today" + paywall; the person's credits are still there |
| `used` | no free credit left | paywall (and `next_free_credit_at` when the daily credit is on) |
| `monthly_cap` | the account reached `free_monthly_videos_cap` | paywall |

`message` is the localized sentence (EN/ES). Welcome credits are never lost to a pause: they stay in the wallet until their own date.

**The global budget** is one atomic counter (usage table, `fbudget` / UTC day). The launcher takes the credits from the wallet, then the free ones among them from the budget; if the budget cannot cover them the wallet gets everything back and the request answers 429 `free_budget_spent`. Forty simultaneous requests cannot overspend it (tested). A video that fails to start gives its share back; a video that fails later or is cancelled does not (it did cost money). Paid plans and paid credits never touch the budget.

**Paid-first ordering:** there is no queue today (the launcher starts the workflow directly). Max videos are recorded with `priority: 1` and every video with its `plan`, so the day a queue or a concurrency limit exists the order is one sort key away.

## 4. Enforcement (at the launcher, before anything is charged)

| Rule | Free | Pro | Max | Refusal |
|---|---|---|---|---|
| Length (`target_minutes`) | `free_max_seconds` (30 s) | 5 min | 12 min | 403 `plan_length` |
| No length given | the server default, shortened to the plan's longest (a deck's suggested length too) | | | never refused |
| Resolution | up to `free_max_resolution` | 1080p | 4K | 403 `plan_resolution` |
| Watermark `none` | no (forced lockup + end card; corner and size are the person's, opacity at least 0.65) | yes | yes | 403 `plan_watermark` (create), 403 `watermark_required` (saved setting) |
| Watermark `moments` | no | yes | yes | 403 `plan_watermark` (the mode itself must exist in the engine: see section 11) |
| Watermark `custom` (own logo) | no | no | yes | 403 `watermark_premium` (now with `requires_plan: "max"`) |
| Photos per video | 10 | 30 | 60 | 403 `plan_photos` |
| Premium looks | no | no | flagged | not a refusal: `premium_looks: true` is added to the workflow input for Max |
| Storage quota | 2 GB | 100 GB | 300 GB | the library's existing `quota` answers (`common/library.limits`) |
| Free credits spent from the web / without device proof | refused | n/a | n/a | 403 `free_not_available` |
| Global free budget, monthly cap | applies | no | no | 429 `free_budget_spent`, 429 `free_monthly_cap` |

The same gate runs for `POST .../retry`. Saved settings a plan no longer allows fall back quietly; only an explicit request is refused.

**Watermark rights reconciled** (`watermark_store.rights`): before plans, own logo came from any of the admin flag `watermark_custom`, an active Pro *storage* flag, or an unlimited account, and the forced mark was a stack switch (`forceWatermark`). With plans on: the **plan** decides; own logo is **Max only** (owner decision 6), so the Pro storage flag no longer gives it; the admin flag `watermark_custom` **stays an override** (own logo and nothing forced, on any plan, production included); unlimited test accounts are Max; `forceWatermark` is ignored (Free is always forced). The admin storage flag and extra GB still count for storage (the larger of flag and plan, plus add-on GB).

**Error shape** (all localized EN/ES, `code` never changes):
```json
{"code": "plan_length", "message": "Videos on your plan can be up to 0:30 long. Pro makes longer ones.", "feature": "length", "plan": "free", "requires_plan": "pro",
 "limit": {"max_seconds": 30, "max_minutes": 0.5}, "can_upgrade": false}
```
| HTTP | `code` | When | Extra fields |
|---|---|---|---|
| 403 | `plan_length` | the length is over the plan's longest | `requires_plan` (pro or max, null when no plan allows it), `limit.max_seconds` |
| 403 | `plan_resolution` | e.g. 4K below Max | `requires_plan`, `limit.resolutions` |
| 403 | `plan_photos` | more photos than the plan uses | `requires_plan`, `limit.photos_per_video` |
| 403 | `plan_watermark` | a watermark mode the plan lacks | `requires_plan` |
| 403 | `watermark_premium`, `watermark_required` | as before, now with `requires_plan` | |
| 403 | `free_not_available` | free credits cannot be spent on this request | `reason`: `app_only` or `not_available` |
| 429 | `free_budget_spent` | the day's global free budget is used up | `reason: "paused"`, `resumes_at` (ISO, next 00:00 UTC), `Retry-After` |
| 429 | `free_monthly_cap` | the account's monthly free videos are used | `reason: "monthly_cap"` |
| 402 | `insufficient_credits` | as before | now also `plan`, `can_upgrade` |
| 501 | `purchases_unavailable` | the purchase routes, until phase 2 | `can_upgrade: false` |
| 403 | `device_not_verified` | a device proof was refused (never says why) | |

## 5. API

* **`GET /users/{user}/capabilities`** gains (only where plans are on; read-only, nothing is granted here):
  * `plan`: `{id, name, state, source, managed_by, interval, period_start, period_end, grace_until, renews, previous_plan, test_account, can_upgrade, plan_credits, limits: {max_seconds, max_minutes, resolutions, watermark_modes, watermark_forced, storage_bytes, photos_per_video, priority_queue, premium_looks, commercial_use, credits_per_month, rollover_months, credits_cap, stt_premium, stt_seconds_per_day}, locked: [...], plans: [...]}`
  * `plan.locked`: what this plan cannot do and the cheapest plan that can, e.g. `{"feature": "resolution", "value": "2160p", "requires_plan": "max"}`, `{"feature": "length", "value": 300, "over_seconds": 30, "max_seconds": 300, "requires_plan": "pro"}`, `{"feature": "watermark", "value": "none", "requires_plan": "pro"}`; features: `length`, `resolution`, `watermark`, `storage`, `photos`, `priority_queue`, `premium_looks`, `commercial_use`, `stt_premium` (paid dictation: Pro 600 s a day, Max 1,200 s; knobs `stt_enabled`, `stt_max_clip_seconds`, `stt_global_daily_seconds`; `docs/SPEECH_TO_TEXT_2026-11-28.md`).
  * `plan.plans`: the three plans for a paywall: `{id, name, rank, limits, price_usd: {monthly, yearly}, products: {apple: {monthly, yearly}, google: {subscription, monthly, yearly}, web: {...}}}`.
  * `free_creation`, `free` (section 3), `can_upgrade` (false until phase 2).
  * **Existing lists keep every option** and gain a badge: `resolutions[].available` and `resolutions[].requires_plan` (so the 4K tile shows "Max"), `lengths.plan_max_seconds`, `lengths.plan_max_minutes`, `lengths.locked` (`lengths.max_minutes` stays the product's 12), `plan_max_photos` (`max_photos` stays 100), `watermark.modes[].requires_plan`.
* **`GET /users/{user}/wallet`**: the same `plan` (without `plans`), `free_creation`, `free`, `can_upgrade`; `buckets` may hold kind `plan`; `balance` counts only what this request could spend (a Free account's free credits read as 0 on the web). `next_free_credit_at` is `null` while the daily credit is off.
* **`GET /users/{user}/plan`** (Cognito, owner only, `no-store`): `{plan, plans, free_creation, free, can_upgrade, purchases: {apple, google, web}}`. The screen behind "Manage plan".
* **`GET /gallery`** (public): section 8. **Device proof routes**: section 7. **Purchase routes**: section 9.
* **What the apps send**: `X-Platform: ios` or `X-Platform: android` on every call (the web sends nothing and counts as web), next to `X-Locale`, `X-Timezone`, `X-Region`.

Upgrade moments the apps can build now (with `can_upgrade: false` they end on "coming soon" or the store page later): a locked tile (`requires_plan`), any 403 `plan_*`, 402, `free.reason` in `used`, `paused`, `off`, `app_only`, `not_available`, storage `quota`.

## 6. Admin
```
python backend/scripts/wallet_admin.py plan you@example.com --plan max [--until 2027-01-31] [--yearly] [--stage prod]   # monthly credits start now
python backend/scripts/wallet_admin.py plan you@example.com --plan free          # ends the plan at once (its unused credits go)
python backend/scripts/wallet_admin.py plan you@example.com --refund             # back to Free, unused plan credits removed
python backend/scripts/wallet_admin.py plan you@example.com --grace [--until 2027-02-10]
python backend/scripts/wallet_admin.py show you@example.com                      # credits, plan, state, dates, limits, storage
python backend/scripts/plans_admin.py config | gallery-only | showcase | report  # knobs, gallery, measurement
```
The older commands (`unlimited`, `give`, `storage`, `watermark`) are unchanged.

## 7. Abuse controls: one free allowance per person

An **eligibility step** (`free_grants.evaluate`) runs before any free credit is granted, and `spend_gate` before one is spent. The account always keeps working for watching and paying; the client only ever learns "free videos are not available for this account". Every refusal is logged once per account and reason (`FREE_CLAIM result=refused reason=<reason> ...`), counted in the metric `FreeClaimRefused{Reason}` and in the day's report.

| # | Rule | Reason code (logs, metrics) | State |
|---|---|---|---|
| 1 | One allowance per normalised email: lower case, `+tag` removed, and for gmail.com / googlemail.com the dots removed | `duplicate_email` (final for the account) | **live** |
| 1 | One allowance per Google or Apple sign-in identity (the federated subject), so a new address or Apple's hidden email does not reset it | `duplicate_identity` (final) | **live** |
| 1 | The claim survives account deletion and re-creation | | **live** |
| 2 | Disposable email domains get none: the public list `disposable-email-domains` (CC0 1.0, 10,455 domains, commit `9cf2bee` of 2026-11-21, in `lambdas/common/data/`; refresh with `plans_admin.py disposable-refresh`), plus `email_domain_deny` and `email_domain_allow` | `disposable` | **live** |
| 2 | No verified email and no federated identity | `identity` | **live** |
| 3 | The web never grants or spends free credits (`free_web` = false) | `web` | **live** |
| 3 | iOS App Attest: attestation of the app key (Apple's certificate chain, app id `39ANXJNUTL.com.videomk.app`, challenge, counter, production environment) and assertions; one allowance per attested key | `no_device`, `duplicate_device` | **built, behind `-c deviceProof=1`** (needs the `apple_deps` layer; no secret needed). Verified against a home-made certificate chain in tests, not yet against a real device |
| 3 | iOS DeviceCheck: two bits per device that survive reinstall (bit 0 = "this device had its allowance") | `duplicate_device` | **built, knob `device_check_ios` off: needs the owner's DeviceCheck key** (secret `videomk/<stage>/devicecheck`: `{team_id, key_id, private_key}`) |
| 3 | Android Play Integrity: Google decodes the token; the verdict must be our package, our challenge, fresh, `PLAY_RECOGNIZED`, `MEETS_DEVICE_INTEGRITY`; device recall bit = DeviceCheck's role | `no_device`, `duplicate_device` | **built, knob `device_proof_android` off: needs the Play setup below** |
| 3 | `require_device_proof`: without a fresh proof no free credit is granted or spent | `no_device` | **live; default true in production, false on QA** |
| 4 | Allowances per IP address per day (3), per /24 or /48 per day (10) | `ip`, `ip_block` (not final) | **live** |
| 4 | Accounts first seen per IP address per hour (5) | `signup_velocity` (not final) | **live** (counted when an account's wallet is first read: Cognito's sign-up trigger does not see the address) |
| 5 | Unlimited test accounts bypass all of it | | **live** |

**Consequence of the defaults:** in production, free creation is off for everyone until the apps send a device proof and the stack is deployed with `-c deviceProof=1` (`require_device_proof` is true there). To allow free creation in production before attestation is live, the owner sets `require_device_proof false` knowingly. On QA testing continues without a proof.

**What is stored (privacy).** A claim is one item in the free-claims table: `{pk: "e#"|"f#"|"d#" + HMAC-SHA256(per-stage secret, normalised email | federated id | device key hash), kind, day, n (accounts that tried to use it), ttl}`. No account id, no address, no identity. The secret is the stage's deletion key (Secrets Manager), under its own domain, so the hash cannot be recomputed by anyone without it and differs between stages. **Account deletion deletes everything else and keeps only this claim** (it has no link to the account to delete by; that is the point), for `claim_retention_days` (730). The app key of App Attest (public key and counter) is in the account's own wallet rows and is deleted with the account. Velocity counters are keyed by the HMAC of the address and expire in 8 days; the /24 or /48 block (not the address) is kept on the block counter for those 8 days so the report can name it.

**Privacy policy: NOT covered today.** `frontend/src/data/legal/privacy.ts` says account and credit records "are removed when you delete it" and lists no record kept for this purpose. Section 5 already names "stop abuse (for example repeated free sign-ups)" as a purpose and IP address as technical data, but the retention table and the device check are missing. Text to add (EN; ES to match) before this goes live in production:
* Retention table, new row: **"Free-credit record: a one-way scrambled code made from your email address, from your Google or Apple sign-in and, on the apps, from your app's device key. It holds no account details and cannot be turned back into them"** | **"2 years from the day free credits were given, also after you delete your account, so that free credits cannot be collected twice"**.
* Retention table, row "Account and credit records": add **"except the free-credit record below"**.
* Section on technical data: **"To keep free credits to one set per person, the apps ask Apple (App Attest, DeviceCheck) or Google (Play Integrity) to confirm that the request comes from a genuine copy of videomk on a genuine device. We receive that confirmation and a key that identifies the app installation, not your device's identifiers. We also count sign-ups and free-credit claims per IP address and network block; those counts are kept for up to 8 days."**
* The existing tombstone switch (`accountTombstone`, default off, 90 days) is a separate, older mechanism for the same worry; with plans on it is no longer needed for welcome credits.

**What the apps must send for the device proof** (only for Free accounts that want to create; skip when `plan.id != "free"`):
1. `POST /users/{user}/device/challenge` -> `{"challenge": "<base64url>", "expires_in": 300}` (one use, bound to the account).
2. iOS: `DCAppAttestService`: the first time `generateKey`, then `attestKey(keyId, clientDataHash: SHA256(challenge as UTF-8))`; afterwards `generateAssertion(keyId, clientDataHash: SHA256(challenge))`. Send `POST /users/{user}/device/verify` `{"platform": "ios", "challenge", "key_id": "<base64 key id>", "attestation": "<base64>"}` or `{..., "assertion": "<base64>"}`; add `"device_check_token"` (base64 of `DCDevice.generateToken`) once the owner switches DeviceCheck on. Keep the key id in the Keychain. If the server answers 403 for an assertion (unknown key after a restore), make a new key and attest again.
3. Android: Play Integrity **standard** request with `requestHash = challenge`; send `{"platform": "android", "challenge", "integrity_token"}`.
4. 200 `{"verified": true, "valid_until", "free_creation", "free": {...}}`: the welcome credits are granted in this call when the account is eligible; the pass lasts `device_pass_minutes`. Before a free create, if `valid_until` has passed, do steps 1 to 3 again (assertion only). 403 `{"code": "device_not_verified"}`: show `free.message` from the wallet; never retry in a loop. 404 or 403 from API Gateway: the server has no device routes yet.

**What the owner must do to switch the waiting pieces on**
* DeviceCheck: Apple Developer > Keys > new key with DeviceCheck; store `{"team_id": "39ANXJNUTL", "key_id": "...", "private_key": "<.p8 text>"}` as secret `videomk/<stage>/devicecheck`; `plans_admin.py config set device_check_ios true`.
* Play Integrity: Play Console > App integrity > link a Google Cloud project and enable the Play Integrity API there; switch on "device recall" for the app if offered; create a service account in that project with the roles Google's Play Integrity setup page asks for (Service Account User and Service Usage Consumer when this was written; check the page), download its JSON key and store it as secret `videomk/<stage>/play_integrity`; `plans_admin.py config set device_proof_android true`. The app must be installed from Google Play (internal testing counts) for `PLAY_RECOGNIZED`.
* App Attest: enable the App Attest capability for `com.videomk.app`; build the layer (`backend/layers/build_layer.sh apple_deps`) and deploy with `-c deviceProof=1`. No key needed. Development builds attest in Apple's development environment: accepted on QA, refused in production.

**Option not deployed: AWS WAF** in front of the API (and the Cognito user pool). It would add managed IP reputation lists, rate-based rules per address, Bot Control and a CAPTCHA or silent challenge on sign-up and on the free-credit routes, before any Lambda runs. Rough cost at today's traffic (AWS list prices as remembered on 2026-11-27, to be checked before deciding): web ACL $5 a month + $1 per rule a month + $0.60 per million requests; Bot Control $10 a month + $1 per million requests; CAPTCHA $0.40 per thousand attempts; Fraud Control account-creation prevention $10 a month + $1 per thousand sign-ups analysed after the first 10,000. So about **$20 to $30 a month** for an ACL with a rate rule, IP reputation, Bot Control and CAPTCHA on sign-up. It complements the rules above (it stops volume and scripts; it does not know that two accounts are one person).

## 8. Gallery (showcase)

`GET /gallery` is **public** (no sign-in, no credits) and lists videos made by videomk: for gallery-only Free accounts, signed-out screens and, later, the website.
```json
{"videos": [{"id": "forest", "title": "How a forest breathes", "title_i18n": {"en": "...", "es": "..."}, "description": "...", "description_i18n": {...},
             "prompt": "A calm explainer about ..." , "aspect": "16:9", "shape": "wide", "width": 1280, "height": 720, "seconds": 28, "lang": "en",
             "video_url": "https://...", "poster_url": "https://... or null"}], "count": 1, "expires_in": 3600}
```
* `title` and `description` follow `X-Locale` / `Accept-Language`. `prompt` is the real prompt or `null` ("title only"), the same rule as the website's samples. `video_url` and `poster_url` are private links valid one hour: fetch the list again instead of storing them (`Cache-Control: public, max-age=300`).
* **Only what an admin marked is ever listed.** The source is one file, `showcase/index.json` in the assets bucket, and each entry is a **copy** under `showcase/<id>/` (no expiry rule applies there; deleting the original changes nothing). The function may read `showcase/*` and nothing else, has no table access, and refuses to sign a key outside the prefix: a wrong entry cannot expose a customer's video (tested).
* Admin: `plans_admin.py showcase add <video id> --title-en "..." [--title-es --desc-en --desc-es --show-prompt --poster poster.jpg --id forest]` (takes a finished video whose owner is a staff account; `--made-by-us` after checking by hand otherwise), `showcase add --file cut.mp4 --id ... --aspect 16:9 --seconds 28 --title-en "..."` for a hand-made cut, `showcase remove <id>`, `showcase list`.
* The website's home page samples today are bundled files (`frontend/public/samples/*.mp4|webp`, described in `frontend/src/data/samples.ts`: id, file, poster, width, height, seconds, aspect wide|tall|square|portrait, lang, title {en, es}, prompt, description {en, es}). The endpoint returns the same fields (`shape` is the site's `aspect`), so the six samples can be uploaded with `showcase add --file` and the site can switch to the endpoint later; nothing in the frontend was changed.
* The showcase starts **empty**: someone has to add the videos (the six website cuts are the obvious first set).

## 9. Purchases: the contract of phase 2 (routes exist, answer 501 today)

| Route | Auth | Body | Today |
|---|---|---|---|
| `POST /users/{user}/purchases/apple` | Cognito, owner | `{"signed_transaction": "<StoreKit 2 JWS>"}`; the purchase carries `appAccountToken` = the account id | 501 `purchases_unavailable` |
| `POST /users/{user}/purchases/google` | Cognito, owner | `{"purchase_token": "...", "subscription_id": "videomk_pro"|"videomk_max"}`; `obfuscatedAccountId` = the account id | 501 |
| `POST /purchases/webhooks/apple` | public (signed payload) | App Store Server Notifications V2: `{"signedPayload": "<JWS>"}` | 501 |
| `POST /purchases/webhooks/google` | public | Pub/Sub push of real-time developer notifications: `{"message": {"data": "<base64>", "messageId": "..."}}` | 501 |
| `POST /purchases/webhooks/web` | public (signed) | the web merchant's event | 501 |

In phase 2 the two verify routes answer 200 with the body of `GET .../plan`. Until then: `can_upgrade` is false everywhere and `purchases` in `GET .../plan` is all false; **no app may show a buy button**.

Product ids (already in `plan.plans[].products`): App Store `com.videomk.app.pro.monthly`, `.pro.yearly`, `.max.monthly`, `.max.yearly` (one subscription group, Max level 1, Pro level 2); Google Play subscriptions `videomk_pro`, `videomk_max` with base plans `monthly` and `yearly`; web `pro_monthly`, `pro_yearly`, `max_monthly`, `max_yearly`.

**What phase 2 needs**
1. App Store: verify StoreKit 2 signed transactions (Apple's certificate chain), the **App Store Server API** (transaction history, subscription status) with an in-app purchase key, and **App Store Server Notifications V2** (subscribed, renewed, failed to renew and grace, expired, upgrade and downgrade, refund and refund reversal, revoke), production and sandbox URLs. Store setup from the proposal: Small Business Program, 16-day billing grace, the four products.
2. Google Play: the **Google Play Developer API** (`purchases.subscriptionsv2.get`, acknowledge) with a service account, **real-time developer notifications** (a Pub/Sub topic pushing to the webhook), grace period on.
3. A purchase function that is the **only runtime writer** of the entitlements table: calls `entitlements.set_plan(..., anchor=<original purchase date>, until=<expiry>, source, renews, product_id)` and `set_state`, each safe to receive twice (the store's transaction id as the idempotency key); on refund also `wallet.revoke_plan_credits`. Everything downstream (credits, limits, capabilities) already follows the record.
4. One plan per account across platforms: when `plan.managed_by` is another store, show "Managed in the App Store / Google Play" and no buy button. A store subscription outlives a deleted account: tell the person to cancel in the store when they delete.
5. `PURCHASES_LIVE = True` in `common/plans.py` (turns `can_upgrade` on), the paywall and restore in the apps, the legal wording for commercial use, the web checkout later.

## 10. Measurement

* **Live metrics** (namespace `videomk/Plans`, written through the functions' logs, no extra permission): `VideosStarted{Plan}`, `FreeCreditsSpent`, `PaidCreditsSpent`, `FreeBudgetRefused`, `FreeSpendRefused{Reason}`, `FreeClaimGranted`, `FreeClaimRefused{Reason}`, `PlanRefused{Code}`, `DeviceProofVerified{Platform}`, `DeviceProofRefused{Reason}`.
* **Daily metric** (`plans_daily`, 00:20 UTC, for the day before): `FreeVideosDay`, `PaidVideosDay`, `FreeUsersDay`, `FreeCreditsDay`, `FreeCostTrackedUsdDay` (the sum of `cost_usd` on free videos: models, speech, searches; not Lambda compute), `FreeCostEstimatedUsdDay` (free credits x `cost_per_credit_usd`, the all-in figure), `FreeCostPerUserUsdDay`, `ClaimsGrantedDay`, `ClaimsRefusedDay`.
* **Alarms, without actions** (there is no notification topic yet; attach one when it exists): `FreeCostEstimatedUsdDay` above `-c freeCostAlarmUsd` (default $3) and `FreeCreditsSpent` at or above `-c freeCreditsAlarm` (default 15) in a day, which is "the global budget was reached or raised".
* **Admin report**: `python backend/scripts/plans_admin.py report [--days 7] [--day YYYY-MM-DD] [--stage prod]`: per day free, paid and test videos, free users, free credits against the budget, estimated and tracked cost of free usage, cost per free user, allowances granted and refused; for the last day the refusals by reason, the top free users, the address blocks with the most allowances; and overall the claimed identities that more than one account tried to use.
* Every video row carries `plan` and `free_credits` from now on (older rows count as `unknown`). The daily job scans the videos table with a filter: fine at today's size, give the table an index by day when it grows.

## 11. Not done, and decisions to confirm

Not done (phase 2 or another owner):
* Store purchases, webhooks, paywall, restore (section 9). Web checkout.
* **The "moments" watermark exists since the merge of 2026-11-27, as an option of the videomk mark, not a mode:** `watermark: {"mode": "videomk", "presence": "moments"}` (docs/WATERMARK.md section 5). The plan rights still list `"moments"` in `watermark_modes` (Pro and Max); `watermark_store.resolve` and `PUT /watermark` read that entry as "this plan may use `presence: moments`": Free asking for it gets 403 `plan_watermark` with `requires_plan: "pro"`, a saved `moments` on a plan that ended quietly becomes `always`, and Pro or Max without a stated presence get `moments`. Capabilities shows it under `watermark.presences` (`available`, `requires_plan`), not in `watermark.modes`. The Free mark is the lockup for the whole video (`presence: "always"`) plus the end card; with plans on the person keeps the corner and the size (`forced_spec`), with plans off everything is fixed (`FORCED_SPEC`).
* **Premium looks**: the launcher adds `premium_looks: true` for Max; the engine does not read it yet (3D backgrounds are still a stack switch, `bgLoops`).
* A queue with paid-first ordering (no queue exists; the fields are recorded).
* The privacy policy text (section 7) and the commercial-use wording.
* Real-device verification of App Attest; DeviceCheck and Play Integrity wait for credentials. WAF is an option, not deployed.
* The website switching its samples to `GET /gallery`; the showcase itself is empty until an admin adds videos.
* `cost_report.py` by plan (the daily report covers free against paid; per-plan margins need the first paying accounts).

Decisions made while building, for the owner:
1. **Budget counts welcome credits too**, not only daily ones: with the daily credit off, a budget on daily credits alone would cap nothing.
2. **Free = 30 s by default** means a free video is the short-form kind; a request without a length gets 30 s instead of the old 3-minute default.
3. **Existing accounts keep their old welcome credits** (5, on their old dates) and are treated as having claimed; they get no extra 2. Their identity is not in the claims table, so the same person could still open one new account and claim once.
4. **Explicit requests the plan does not allow are refused** (403 with the plan that unlocks it) instead of silently changed; saved settings fall back quietly.
5. **Plan credits end with the plan** (expiry, refund, `plan free`), including Max's carried month. On a downgrade from Max to Pro what is left keeps its own date.
6. **Grants are lazy** (on wallet read or video start), not a daily job: same result, no moving part.
7. **Refunds do not claw back spent credits**; a repeat-refund flag belongs to phase 2.
8. **Claims are kept 2 years** (`claim_retention_days`); the privacy text must say so before production.
9. **`require_device_proof` true in production** means no free creation there until attestation is live.
10. The stack is near CloudFormation's limit: 421 resources before plans, **454 with plans, 465 with the device routes**, of 500. The next sizeable feature needs a second stack or nested stacks.
