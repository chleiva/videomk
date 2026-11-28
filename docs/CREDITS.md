# Credits (decided 2026-11-23; daily free credit lowered from 2 to 1 the same day)

**1 credit = 1 started minute of video**, at least 1 and at most 12 per video: a 10 s video costs 1, 60 s costs 1, 61 s costs 2. The length
the user picks is the length that is billed and made (the launcher passes it to the workflow). Failed or declined videos refund exactly the
buckets they were charged to, once.

**A 4K (2160p) video costs double** (decided 2026-11-25): the started minutes times 2, so 1 minute is 2 credits, 3 minutes 6, 12 minutes 24.
720p and 1080p cost the same as before. One function owns the rule, `common/wallet.credits_for_minutes(minutes, resolution)`; the multiplier
per resolution is data in `engine/format_options.RESOLUTIONS` and is what `GET /capabilities` shows the apps. A failed 4K video refunds the
doubled amount; edits stay free. Render cost and reasoning: `docs/FOUR_K.md`.

## What users get (server config, no app update: `WALLET_*` env, see `common/wallet.py`)
| Credits | Amount | Expiry |
|---|---|---|
| Welcome | 5, on first sight of the account | 30 days |
| Daily free | 1 per local day (the day starts at the user's timezone midnight, sent as `X-Timezone`; first day has none, the welcome credits cover it) | the same night |
| Purchased | packs below | never |
| Returned | a 24 h make-good when a refund finds its bucket expired | 24 h |

Spending order: soonest-expiring first (daily, welcome, returned, purchased). Daily credits can be claimed once per UTC day **and** local day, so
sending different timezones earns nothing extra.

## Weekly allowance (R178, 2026-11-28; where plans are on, QA only)
Knobs `weekly_allowance` (on), `free_weekly_credits` (4), `plan_weekly_release` (on), switchable without a deploy; details and edge cases in `docs/WEEKLY_ALLOWANCE_2026-11-28.md`.
| Credits | Amount | Expiry |
|---|---|---|
| Welcome | 5 (knob), once | 30 days |
| Weekly (Free) | 4 per 7-day window counted from 00:00 UTC of the signup day; none in the signup week | the end of the window, not carried |
| Plan (Pro, Max) | the monthly bundle in 4 weekly parts: floor(bundle/4) x 3, remainder in week 4 (Pro 7+7+7+9, Max 30 x 4), pro-rated first release when first read mid-cycle | as before (Pro: next monthly date; Max one date later, cap 240) |
The wallet and capabilities answers carry `next_renewal_at` and `renews_on` so the apps can show the renewal day.

## Proposed packs (not yet in the stores)
20 / 45 / 500 credits for $9.99 / $19.99 / $199.99 (about $0.50 / $0.44 / $0.40 per credit), relabelled from the earlier 100 / 220 / 2400 at 5
credits per minute: same economics.

## Cost basis (corrected 2026-11-28 with QA measurements)
The earlier estimate (about $0.02 fixed plus $0.04 per minute, "1 min is about $0.06") was the plain look's script only and left out the render and the whiteboard review: it is **wrong as a cost per credit**.
Measured on QA (`docs/COSTS.md`, `docs/COST_LEVERS_2026-11-28.md`): a 1-minute video costs about **$0.22 to $0.24 per credit including the render** (one 1-minute Spanish whiteboard video: script $0.233, speech $0.036,
render $0.029, total $0.269; the whiteboard script call with its board review is the biggest part, $0.14 to $0.33). A plain-look 1-minute video measured $0.048 on average before the render (`docs/COSTS.md`, 41 videos), so the $0.22 to $0.24 is the figure to plan with until a measurement of every look says otherwise.
Plan on **$0.22 to $0.24 per credit**, not $0.06: a $0.50 credit is then about 2x cost before store fees (about 1.6x after), not 8x. Free exposure per active free user (daily credit set to 1 on 2026-11-23): first month 5 + 29 = 34 credits,
about $7 to $8 if every one is used at this cost (realistically a fraction of that), then about 30 credits a month, $6.60 to $7.20. The daily amount is a server setting (`WALLET_DAILY_CREDITS`); the free exposure figures above must be reviewed with it.

## Abuse controls
Built: spend is conditional per bucket (no overspend under concurrency), refunds are idempotent, daily claim limited per UTC day,
welcome credits only once per account.
To build (needs keys or store setup): Apple DeviceCheck / App Attest (one welcome grant per device, genuine app only; Play Integrity on
Android), free credits only for Apple/Google sign-in, a global daily budget for free videos that pauses free generation when spent, limits per
IP and device on sign-ups, alarms on hourly spend, store-verified purchases (one transaction id grants once: `grant_paid` is ready).

## Unlimited test accounts: how the exception is protected (2026-11-23)
Purpose: staff and test accounts that are never charged. Threats considered and the controls:
| Threat | Control |
|---|---|
| A user (or a bug in code that handles user input) grants itself the flag | The flag is in its own table (`AccountFlagsTable`) that **no Lambda role can write** (only the launcher and wallet function can read it); the only writer is a person with AWS admin credentials running `scripts/wallet_admin.py`. No API route sets it, and a test fails if any handler calls `set_unlimited`. Verified with the IAM policy simulator. |
| The flag leaks into production | The stack sets `ALLOW_UNLIMITED_ACCOUNTS=0` for prod (all functions, checked on the synthesized template) and the code treats anything but `"1"` as off, so even a flag written in prod is ignored. |
| Flag keyed by something a user can change | Keyed by the immutable Cognito `sub`, never by email; only an exact boolean `true` counts. |
| An unlimited account's token is stolen and used to burn money | Unlimited accounts still have a daily ceiling (`UNLIMITED_DAILY_VIDEOS`, default 50), every use is logged as `UNLIMITED_ACCOUNT_USE` (alarm on it), and the per-video cost cap still applies. |
| Unlimited use hides failures | Nothing is charged, so nothing is refunded; refunds only ever return what was actually taken. |
Keep the flag to a handful of staff accounts; review with `wallet_admin.py show`. Before launch also add a CloudWatch alarm on `UNLIMITED_ACCOUNT_USE`.

## With plans on (2026-11-27): see `docs/PLANS.md`
Where the stack has plans on, the free amounts above are replaced by the owner's knobs (defaults: **2 welcome credits** valid 30 days, **daily credit off**, free videos up to 30 s, a **global budget of 15 free credits a day** for all accounts, about $2.25 a day at $0.15 a credit), a free credit is granted only after the eligibility step (one allowance per person, mobile apps only), and paid plans add a `plan` bucket (Pro 30 a month, Max 120 a month with one month of rollover, capped at 240). The `WALLET_*` env values only apply where plans are off. The global daily budget and the device attestation listed under "To build" above are built there (attestation partly waiting for keys).
