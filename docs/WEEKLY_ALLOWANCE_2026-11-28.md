# Weekly allowance: cost comparison (R178)

Status: analysis for the owner to confirm; nothing built, no setting changed. Inputs are the **measured** cost per credit from `docs/PLANS_PROPOSAL_2026-11-27.md` section 1 (**$0.15 at p50, $0.20 at p90**, one credit = one started minute of video) and the plan ladder in `backend/lambdas/common/plans.py`. Everything else below is arithmetic on those two numbers, or **assumed** (marked).

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
