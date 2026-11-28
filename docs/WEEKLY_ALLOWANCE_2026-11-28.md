# Weekly allowance: cost comparison (R178)

Status: analysis for the owner to confirm. **Implemented 2026-11-28 on branch `weekly-and-deletion` (QA only; plans stay off in production), see "Implementation" at the end.** Inputs are the **measured** cost per credit from `docs/PLANS_PROPOSAL_2026-11-27.md` section 1 (**$0.15 at p50, $0.20 at p90**, one credit = one started minute of video) and the plan ladder in `backend/lambdas/common/plans.py`. Everything else below is arithmetic on those two numbers, or **assumed** (marked).

## Free: 1 credit a day (today) against a weekly allowance

Today the daily credit is gone at midnight. A month of 30 days gives at most 30 credits to someone who comes back every single day.

| Rule | Most a person can spend in a month | Worst-case cost a month (p50 to p90) |
|---|---|---|
| 1 a day, gone the same night (today) | 30 | $4.50 to $6.00 |
| 4 a week, renewing on a day the person sees (the idea) | about 17 (4 x 4.35 weeks) | $2.60 to $3.50 |
| 3 a week | about 13 | $2.00 to $2.60 |
| 5 a week | about 22 | $3.30 to $4.35 |

Three kinds of person (**assumed** behaviours, to be replaced by measured ones after 30 days of use, R177):

| Person | Daily rule | 4 a week |
|---|---|---|
| Every-day user, one video a day | 30 credits, $4.50 to $6.00 | 17 credits, $2.60 to $3.50: they hit the wall by midweek and see why the paywall exists |
| Occasional, 4 active days a month, one video each | 4 credits, $0.60 | 4 credits, $0.60: no change |
| Bursty, one session a week with 3 videos | 1 credit (the other two days of the burst are refused), $0.15 | 12 credits, $1.80 to $2.40: happier, and still below the heavy daily user |

So a weekly allowance **lowers the worst case by about 40 percent** (4 a week) and **raises the cost of the bursty person**, who today loses most of what they would have used. The total cost of the free tier changes by the share of free users who are heavy against bursty; with the welcome credits (5, 30 days) added, month one is unchanged.

## Paid: release the bundle weekly

The monthly bundle stays (Pro 30, Max 120 with one month of rollover). Releasing about a quarter a week (Pro 7.5, Max 30) with unused credits carrying to the next week inside the month:

* The cost of a fully used month does not change: Pro 30 x $0.15 = $4.50 (p90 $6.00) against $14.99; Max 120 x $0.15 = $18 (p90 $24) against $39.99.
* The cost of a **burst** is bounded: today a Pro account can spend all 30 credits in the first hour of the month (about 30 minutes of finished video, rendering all in parallel); weekly release caps that at 7.5 plus any carry.
* Unused credits ("breakage") are unchanged in total; the carry inside the month means a quiet week is not lost.

## What the numbers say

1. For Free, weekly beats daily on the person's side (a day off is not lost) and on the worst-case cost side (17 instead of 30 credits). The price of it is the bursty person costing more than today.
2. The weekly number is a lever: 3 a week is $2.00 to $2.60 worst case, 5 a week $3.30 to $4.35.
3. For paid plans weekly release is a protection against bursts, not a change of price.
4. Keep credit = one started minute (already priced), show the price before Create, and show the renewal day in the apps.

## Decision needed from the owner

* Free: 3, 4 or 5 credits a week, and which day it renews (the day the person signed up is the simplest and spreads the load).
* Paid: weekly release of the monthly bundle, yes or no.
* Then it is server settings in the plans config (no release needed for the numbers; the renewal-day text in the apps is client work).

Related: the sketch-only free video (R175) is not cheaper today (whiteboard $0.26 to $0.31 a minute), so it does not change these numbers.

## Implementation (R178)

Knobs (`common/plans.py`, `scripts/plans_admin.py config set <knob> <value>`; read only where plans are on): `weekly_allowance` (default on), `free_weekly_credits` (4), `plan_weekly_release` (default on). Setting a knob off returns to the earlier rules without a deploy.

**Free.** Windows are 7 x 86400 s counted from 00:00 UTC of the signup day, so they have no daylight-saving shift and no `X-Timezone` can move or repeat one. Window 0 (the signup week) has no allowance: the welcome credits cover it, as the first day did before. From window 1 the first wallet read, or video start, of a window grants `free_weekly_credits` once (kind `weekly`, expires at the window end, nothing is carried; a missed window is not back-filled). Exactly once under concurrency: `weekly_k` on the wallet META row moves forward in the same transaction as the bucket, conditional on being behind. The welcome credits (knob `welcome_credits`, 5 in the plan, 30 days), the 1-minute cap (`free_max_seconds`) and the forced watermark are untouched. A weekly credit is a free credit for every gate (app only, device proof, global budget, monthly cap). Unlimited and paid accounts: no weekly free credit.

**Paid.** The monthly bundle is split in four parts, `floor(bundle / 4)` for weeks 1 to 3 and the remainder in week 4 (Pro 30 = 7 + 7 + 7 + 9; Max 120 = 4 x 30), so a month always adds up exactly. Part j of cycle k is released at the cycle start (the subscription anchor plus k calendar months, as before) plus j x 7 days; part 4 starts on day 21, inside every month. Released credits keep the old expiry (Pro: the next monthly date; Max: one date later, balance cap 240), so unused credits carry from week to week inside the month. Each part has a marker row `PLAN#<plan>#<anchor>#<cycle>#w<j>` written in the same transaction as its bucket (idempotent under concurrency); the old monthly marker `PLAN#<plan>#<anchor>#<cycle>` still means "the whole cycle is done".

Edge cases:
* **First read mid-cycle** (a purchase recorded late, or an entitlement whose anchor is earlier than now): the parts whose start has passed are released at once, so the first release is pro-rated to the weeks that have begun (for example 15 days into a Pro cycle: 7 + 7 + 7 = 21 now, the last 9 on day 21), never more than the cycle's parts. The monthly total is unchanged.
* **A plan that ends** (`period_end`): no part whose start is on or after the end is released; plan credits are removed with the plan, as before.
* **Switch the knob back to monthly mid-cycle:** the parts not yet released are granted in one go and the cycle is marked done (no double grant); switching on again grants nothing more in that cycle.
* **Max cap 240:** applied part by part against the live plan credits, as the whole bundle was.
* **Upgrade/downgrade:** the plan id is in the marker, so a new plan starts its own parts; the old plan's credits follow the existing rules.

What the apps get (`GET .../wallet`, and `GET .../capabilities`, `plan.allowance`): `free_creation: "weekly"`, `free.mode: "weekly"`, `next_renewal_at` (ISO 8601 UTC, when the next window starts), `renews_on` (its UTC date), `next_free_credits` and `credits_per_week` (Free) or `next_release_credits` and `release: "weekly"` (paid). The bucket kind `weekly` is new: clients should treat an unknown kind as a plain credit.

Also fixed: capabilities showed Max's 1200 s/day dictation for unlimited test accounts while the dictation service allowed 7200; both now read `plans.unlimited_stt_seconds()` (env `UNLIMITED_DAILY_STT_SECONDS`, default 7200).
