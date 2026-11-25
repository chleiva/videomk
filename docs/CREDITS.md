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

## Proposed packs (not yet in the stores)
20 / 45 / 500 credits for $9.99 / $19.99 / $199.99 (about $0.50 / $0.44 / $0.40 per credit), relabelled from the earlier 100 / 220 / 2400 at 5
credits per minute: same economics.

## Cost basis (estimates, +-30%; measure again with real data)
About $0.02 fixed plus $0.04 per minute (voice $0.027/min with Polly generative, render about $0.015/min, planning the rest):
1 min is about $0.06, 3 min $0.14, 12 min $0.50. Worst cost per credit is a 1-minute video, about $0.06, so a $0.50 credit is about 8x
before store fees (about 5-7x after). Free exposure per active free user (daily credit set to 1 on 2026-11-23): first month 5 + 29 = 34 credits, about $1.70-2.05 if every one is used
(realistically a fraction of that), then about 30 credits a month, $1.50-1.80. The daily amount is a server setting (`WALLET_DAILY_CREDITS`).

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
