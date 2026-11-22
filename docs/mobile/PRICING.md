# Pricing, free allowance and AI-edit metering

Generated from `backend/scripts/pricing_model.py` (re-run it after changing any assumption; `backend/tests/test_pricing_model.py` guards the claims below).
**All costs are estimates** from `docs/ENGINE.md` (token prices, a TTS price, a Lambda speed measured locally). They have not been measured on real traffic.
The server already records `cost_usd` per video and `cost_rN` per edit revision, so the first real numbers will come from production.

## 1. The model in five lines
1. **One currency: credits.** A video costs **5 credits per started minute** (1 min = 5, 3 min = 15, 10 min = 50, max 12 min = 60).
2. **Three packs** through the stores only: **$9.99 → 100 credits**, **$19.99 → 220** (+10%), **$199.99 → 2,400** (+20%). Credits don't expire. (Store price points are fixed tiers; $199.99 is the nearest to your $200.)
3. **Free allowance:** 3 videos in the first 24 hours (up to 3 min, no watermark), then **1 free video per day** (up to 2 min, small watermark). Paid videos are up to 12 min, no watermark.
4. **Edits:** everything that needs no AI is free; actions that use AI cost credits, priced from their real cost (§5), with a few free ones per video.
5. **Everything above is server config**, so numbers can change without an app update.

## 2. What a video costs us

| Length | Planning | Voice | Photo review | Render | Overhead | **Total (mid)** | per minute |
|---|---|---|---|---|---|---|---|
| 1 min | $0.024 | $0.014 | $0.003 | $0.005 | $0.002 | **$0.049** | $0.049 |
| 2 min | $0.033 | $0.029 | $0.006 | $0.011 | $0.004 | **$0.083** | $0.042 |
| 3 min | $0.042 | $0.043 | $0.010 | $0.016 | $0.006 | **$0.117** | $0.039 |
| 5 min | $0.060 | $0.072 | $0.016 | $0.027 | $0.010 | **$0.185** | $0.037 |
| 10 min | $0.105 | $0.144 | $0.032 | $0.054 | $0.020 | **$0.355** | $0.036 |

Bands: low ×0.7, high ×1.6 (uncertainty in LLM prices, TTS vendor, real Lambda speed). A paid voice such as ElevenLabs would roughly triple the voice line.

Planning has a fixed part (the prompt and grounding notes), so very short videos cost slightly more per minute. That is why the credit price is *per started minute* with a 5-credit minimum rather than a lower per-minute rate.

## 3. Credits and margin

You asked for a **7x margin**. I define it as **store-net revenue ÷ our cost**, i.e. after the store's commission (15% for small-business programmes, 30% otherwise), so it is the number that reaches your bank versus what we spend.

### Packs and margin (store-net revenue ÷ our cost; target ≥ 7x)

| Pack | Credits | Price/credit | 3-min video, mid cost, 15% fee | 5-min | 1-min | 3-min, 30% fee | 3-min, HIGH cost, 15% fee | worst (1-min, high cost, 30% fee) |
|---|---|---|---|---|---|---|---|---|
| $9.99 | 100 | $0.0999 | **10.9x** | 11.5x | 8.7x | 9.0x | 6.8x | 4.5x |
| $19.99 | 220 | $0.0909 | **9.9x** | 10.4x | 7.9x | 8.2x | 6.2x | 4.1x |
| $199.99 | 2400 | $0.0833 | **9.1x** | 9.6x | 7.2x | 7.5x | 5.7x | 3.7x |


How to read it: the highlighted column is the target case (3-minute video, my mid cost estimate, 15% store fee). The formula was chosen by testing candidates across every length from 1 to 12 minutes; 4 credits per minute failed on 1-minute videos (6.3x) and 5 per minute holds **at least 7.2x in every pack at every length** under the mid estimate and 15% fee.
Be aware of the right-hand columns: if the real cost is 60% higher than my estimate, or you pay the 30% commission tier, the margin falls to roughly 4–6x. That is not a flaw in the formula; it is why the first job after launch is to measure real cost and re-run the model. The bonus credits on the big packs are the lever: shrinking them raises margin immediately.

## 4. Free allowance

## Free allowances: what they cost us

- **Welcome (first 24 h):** 3 × up to 3 min, watermark=False → worst case $0.351 per day per account ($10.53/month if used every day).
- **Daily:** 1 × up to 2 min, watermark=True → worst case $0.083 per day per account ($2.49/month if used every day).
- *Your original idea* (1 × 5 min clean + 10 × 1 min watermarked per day): worst case **$0.68/day = $20.25/month per account** if fully used.

A first $9.99 purchase leaves about **$7.52** after store fee and the cost of using all its credits. Break-even for the free tier: one payer covers the free usage of N free users, N = 7.52 ÷ (monthly free cost per user). A user who makes a free video 4 days a month costs about $0.33/month, so one payer funds ~23 of them.

**Why not the original idea** (1 clean 5-minute video plus 10 watermarked 1-minute videos every day): a fully used account would cost about **$20 a month** and bring in nothing, and a clean 5-minute free video is the same product you sell. The recommendation keeps the generous first impression (3 clean videos on day one), then a small daily taste that is good enough to show the product but is shorter and carries a watermark, so that longer and clean videos are the reason to buy.

**Watermark design (non-disruptive):** a small wordmark in the **bottom-right corner, below the caption band** (about 60% opacity, roughly 8% of the frame width), no end card, no motion. It never overlaps captions or the photo credit. It is burned in at render time; the chunk cache key includes the watermark flag, so a free and a paid render never share segments. **Remove watermark** later: re-render clean for **2 credits per minute** (config; our cost is only the render).

**Guardrails so a free tier can't hurt you:**
- Allowances are per account, with **device attestation** (App Attest / Play Integrity) before granting them at scale, so new accounts can't farm free videos.
- A **circuit breaker**: if free spend in a day passes a threshold (CloudWatch alarm on the cost metric), the server flips the config from daily to weekly and tells users honestly.
- Free videos never get the paid-only options (length over 2 min, clean render).

## 5. AI-edit metering (fair, simple to explain)

**Principle:** you pay credits only for *new AI work*; anything reused from cache or needing no AI is free. Every AI action is converted from its real cost to credits using the same 7x target.

One credit funds about **$0.0121** of real AI cost at the smallest pack. Price of an action = `max(1, ceil(AI cost ÷ $0.0121))`; ordinary compute (re-rendering a chunk, re-mixing audio, about half a cent) is bundled and bounded by the per-revision cost cap and daily edit limit that already exist.

| Action | AI cost | Compute (bundled) | Credits |
|---|---|---|---|
| re-voice a scene | $0.0067 | $0.0042 | **1** |
| find new photos (new query) | $0.0040 | $0.0027 | **1** |
| AI-rewrite a scene (planned) | $0.0187 | $0.0042 | **2** |
| reorder / delete / text, chart, timeline, look, music | $0.0000 | $0.0042 | **0** |

Rules the user sees:
1. **Free:** reorder, delete, change titles/bullets/chart/timeline/stat/quote text, choose a different *already-found* photo, look, music mood, chapter titles, preview renders.
2. **Costs credits (quoted before you tap Preview):** re-voice a scene (1), search for new photos (1), AI-rewrite a scene (2, planned feature).
3. **3 free AI actions per video**, so a light touch-up costs nothing.
4. **Cache hits are free:** changing text back to something already voiced, or re-publishing an approved preview, costs nothing.
5. **Failures refund:** a failed edit gives the credits back, like a failed video.
6. **Quote, then charge exactly the quote.** The server computes which beats need AI work (it already does: `edit_prep`) and returns the credit price before rendering starts.

## 6. What changes in the build
- **Server:** wallet + ledger; `quote` for create and for edits; free-allowance rules (welcome window, daily); length caps by tier; a `watermark` flag carried through the timeline and into the chunk hash; the renderer draws the wordmark; edit metering from `edit_prep`; per-user daily AI-spend cap; all numbers from config.
- **Apps:** show the quote before every spend; free-allowance and cost states (see `DESIGN_BRIEF.md`); a "remove watermark" action on free videos.
- **Models are recalibrated, not guessed:** a weekly job (or manual) reads real `cost_usd` per video length from DynamoDB, and `pricing_model.py` takes those averages instead of the assumed ones.

## 7. Decisions still needed
1. Confirm **5 credits/min** and the **100 / 220 / 2,400** packs, or choose a different bonus (more bonus = lower margin).
2. Confirm free tier limits: welcome 3 × ≤3 min clean, then 1/day ≤2 min watermarked.
3. Price of "remove watermark" (proposal: 2 credits/min).
4. Whether the three free AI edit actions per video should stay.
