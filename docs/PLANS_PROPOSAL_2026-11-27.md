# Paid plans proposal (2026-11-27)

Research and a proposal, no product code. Every number is marked **measured** (read from QA or from a vendor's page today) or **assumed**.

## 0. Summary

**Recommended ladder: Free, Pro, Max. Subscriptions only, monthly and yearly, sold in the App Store, Google Play and on app.videomk.com.**

| | Free | Pro | Max (the plan the page steers to) |
|---|---|---|---|
| Price a month | 0 | $14.99 / £12.99 / €14.99 | $39.99 / £34.99 / €39.99 |
| Price a year | | $149.99 / £129.99 / €149.99 (2 months free) | $399.99 / £349.99 / €399.99 (2 months free) |
| Credits | 5 welcome (30 days) + 1 a day, gone the same night | 30 a month, no rollover | 120 a month, unused credits roll over one month (balance never above 240) |
| Price per credit (US, monthly) | | $0.50 | $0.33 |
| Watermark | always "videomk" with the name, plus an end card | may remove it, or use the gentle "moments" mode | same, plus their own logo |
| Resolution | up to 1080p | up to 1080p | up to 4K (4K costs double credits, as decided) |
| Longest video | 1 minute | 5 minutes | 12 minutes |
| My media storage | 2 GB | 100 GB | 300 GB |
| Queue | standard | standard | priority |
| Extras | | web research, all looks | early access to premium looks (3D backgrounds), more photos per video |
| Use | personal, watermark must stay | commercial use allowed | commercial use allowed |

* **Cost per credit today (measured, 85 QA videos, 25 to 27 November): $0.15 at p50, $0.20 at p90.** This is twice the 24 November figure ($0.07).
* **Margin after store fee and VAT, if every credit is used:** Pro 53 to 65 % (p50 cost), 38 to 53 % (p90). Max 30 to 47 % (p50), 7 to 29 % (p90). At 60 % use of the credits (assumed typical): Pro 72 to 79 %, Max 58 to 68 % at p50 cost.
* **A heavy free user costs $4.20 to $6.00 a month** at today's cost. This is the weakest point of the design; section 5.4 says how to contain it.
* Prepaid credit packs are **not** proposed (the owner declined them); one paragraph in 5.6 records the option.

---

## 1. What a video costs today (measured on QA)

### 1.1 Method
* Source: the videos table on QA (`cost_usd` and its parts `c_script`, `c_speech`, `c_research`, `c_photos`, `c_stock`), the same records `backend/scripts/cost_report.py` reads. Videos created 2026-11-25 to 2026-11-27: **87 records, 85 completed**, by 6 staff and test accounts.
* Lambda compute is not in `cost_usd`. It was read from CloudWatch (billed seconds of the six engine functions per day) and shared out per minute of video made that day: **about $0.07 per minute at 720p/1080p** ($0.060 on the 25th, $0.081 on the 27th) and **about $0.17 per minute at 4K** (derived from the two days that had 4K videos; 5 videos, so a rough figure). The totals are measured; the split per video is an allocation.
* Prices were checked against the bill: on 26 November the Bedrock token counts times the price list in the code ($2 / $10 per million tokens for Sonnet 5.5, $0.10 / $0.50 for Haiku 5.5) give $30.00 and $0.486; Cost Explorer shows $30.00 and $0.486. Polly on the 25th: $3.87 tracked, $3.87 billed.
* Not included: data transfer to phones, web searches are counted at an assumed $0.008 each, failed runs, edits (free to the user, their compute is inside the daily compute totals).
* Limits of the sample: testers chose the lengths and options, not customers; 4K has 5 videos; "with photos" has 17.

### 1.2 Cost per video by length (720p and 1080p, all-in)

| Length | Videos | Tracked (AI and voice) p50 | All-in mean | All-in p50 | All-in p90 | Range |
|---|---|---|---|---|---|---|
| 15 s | 7 | $0.077 | $0.100 | $0.096 | $0.110 | 0.091 to 0.113 |
| 30 s | 10 | $0.097 | $0.130 | $0.132 | $0.137 | 0.118 to 0.137 |
| 45 s | 3 | $0.104 | $0.159 | $0.157 | $0.173 | 0.145 to 0.177 |
| 1 min | 25 | $0.107 | $0.175 | $0.178 | $0.206 | 0.134 to 0.245 |
| 2 min | 7 | $0.155 | $0.305 | $0.300 | $0.366 | 0.253 to 0.418 |
| 3 min | 17 | $0.232 | $0.444 | $0.443 | $0.519 | 0.321 to 0.537 |
| 5 min | 4 | $0.531 | $0.859 | $0.883 | $0.982 | 0.654 to 1.018 |
| 12 min | 7 | $1.339 | $2.106 | $2.180 | $2.256 | 1.818 to 2.256 |

### 1.3 Cost per credit charged

| Selection | Videos | Mean | p50 | p90 | Max |
|---|---|---|---|---|---|
| **All completed videos** | 85 | $0.154 | **$0.151** | **$0.195** | $0.245 |
| Last two days only (shorter beats, verified clips) | 31 | $0.156 | $0.137 | $0.204 | $0.245 |
| 1-credit videos (up to 1 minute) | 45 | $0.152 | $0.141 | $0.200 | $0.245 |
| 2 to 5 credits | 28 | $0.155 | $0.151 | $0.179 | $0.209 |
| 12 credits | 7 | $0.175 | $0.182 | $0.188 | $0.188 |
| 720p | 7 | $0.136 | $0.130 | $0.191 | $0.210 |
| 1080p | 59 | $0.159 | $0.160 | $0.196 | $0.245 |
| 4K (double credits, so the cost is spread over twice as many) | 5 | $0.132 | $0.129 | $0.152 | $0.164 |
| With the person's photos | 17 | $0.149 | $0.143 | $0.173 | $0.209 |
| Without photos | 68 | $0.155 | $0.152 | $0.197 | $0.245 |
| With web research | 23 | $0.169 | $0.169 | $0.200 | $0.245 |
| Without web research | 62 | $0.148 | $0.140 | $0.193 | $0.210 |

**Planning figures used below: $0.15 per credit at p50, $0.20 at p90.** A 4K credit costs slightly less than an HD one, so the double price for 4K covers its rendering.

### 1.4 Where the money goes (85 videos, 216 minutes of video)

| Part | Per minute of video | Share of the tracked cost |
|---|---|---|
| Script and planning (Sonnet 5.5) | $0.061 | 62 % |
| Voice (Polly generative) | $0.023 | 24 % |
| Web research | $0.012 | 12 % |
| Photo reviews | $0.002 | 2 % |
| Stock clip and photo checks (vision) | $0.001 | 1 % |
| Rendering (Lambda), added on top | about $0.07 (4K about $0.17) | |

Two things stand out, and both are ways to lower the cost before launch (the savings are **estimates, not measured**):
1. **The script step costs about $0.08 even for a 15-second video.** It is a fixed cost of each video (the large instructions sent to the model). CloudWatch shows no cached tokens at all on Bedrock, so prompt caching is not in use. Caching the fixed part could save an estimated $0.03 to $0.06 per video.
2. **The render functions are 10 GB and use at most 3.1 GB** (1.4 GB for 1080p according to `docs/FOUR_K.md`). Rendering 720p and 1080p on a 4 GB function and keeping 10 GB for 4K could cut the render cost by about half (an estimated $0.03 to $0.04 per minute).
With both, a credit would cost roughly $0.08 to $0.10. All margins below use today's measured cost, not this hope.

### 1.5 Fixed monthly infrastructure (Cost Explorer, 1 to 27 November)

| Account | Total so far | Fixed part (no traffic) | What it is |
|---|---|---|---|
| Production (464863885161) | $345, of which $274 domain registration (one-off) and $58 tax | **about $13 a month** | Secrets Manager $4.17, Route 53 $3.04, KMS $2.83, WAF $2.61, CloudWatch, S3, DynamoDB under $1 |
| QA (552357225438, shared with another project) | $147, of which $73 language models, $12 Lambda, $10 Polly, $12 one-off image and clip generation, $25 tax | **about $10 a month** | KMS $3.51, Secrets Manager $2.61, Route 53 $0.51, the rest is use |

Add (assumed, not AWS): Apple developer programme $99 a year, Google Play $25 once, Cognito free up to 10,000 monthly users (`docs/REQUIREMENTS_TRACKER.csv` R106). Fixed costs are small; the business is driven by the cost per credit.

### 1.6 Storage (My media)
From `docs/MEDIA_LIBRARY.md` (list prices, eu-west-1):

| | Per GB a month |
|---|---|
| S3 Intelligent-Tiering, first 30 days | $0.023 |
| After 30 days untouched | $0.0125 |
| After 90 days untouched | $0.004 |
| Monitoring | $0.0025 per 1,000 objects (about $0.002 per GB at 1.5 MB a photo) |
| Embedding (Cohere Embed v4), once per photo | estimated $0.1 to $0.5 per 1,000 photos (about $0.07 to $0.35 per GB, once). Measured so far: the whole of November cost $0.04 on QA |
| Vectors, thumbnails, DynamoDB | under $0.001 |

| Account full | First month | At rest (after 90 days) |
|---|---|---|
| Free, 2 GB | $0.05 | $0.01 |
| Pro, 100 GB | $2.50 plus about $7 to $30 once to index | $0.60 |
| Max, 300 GB | $7.50 plus about $20 to $90 once to index | $1.80 |

Very few accounts fill their storage; a 300 GB account holds about 200,000 photos at today's upload size. Finished videos add about 13 MB per minute of video kept (`docs/STORAGE.md`), under $0.001 a month.

### 1.7 What a free user costs

| Free user | Month 1 | Later months |
|---|---|---|
| **Heavy** (uses every credit, 1-minute videos): 5 + 29 credits, then 30 | $4.80 (p50) to $6.80 (p90) | $4.20 to $6.00 |
| Typical (assumed): the 5 welcome credits and 4 daily ones | $1.30 | $0.60 |
| Storage at 2 GB | $0.05 | $0.01 |

---

## 2. Market (prices read 2026-11-27)

Several vendors run Black Friday prices today; list prices are given where the page showed them. "Not verified" means the vendor's own page could not be read.

### 2.1 Video tools

| Product | Paid plans: monthly / yearly per month (USD) | Allowance | Rollover | Free plan and watermark | Resolution |
|---|---|---|---|---|---|
| InVideo AI | Starter $20 / $10, Plus $60 / $24, Max $150 / $60 | 400 / 2,000 / 5,000 credits | No | not verified | Starter has no 1080p or 4K models; Plus and Max do |
| Pictory | Starter $29, Professional $59, Teams $199 list (today $14.50 / $29.50 / $99.50) | about 30 / 90 / 300 video minutes | not stated | 14-day trial, 3 videos, watermark | trial 720p, paid 1080p |
| Synthesia | Starter $19 / $14, Pro $89 / $59 | about 12 / 60 minutes | not stated | 10 minutes a month, Synthesia logo | paid up to 1080p |
| HeyGen | Creator $29 / $24, Pro $49, Business $149 + $20 a seat | 600 / 1,000 / 1,500 credits | one extra month | 3 videos a month of 1 minute, watermark | Creator 1080p, Pro 4K |
| Fliki | Standard $21, Premium $66 (third party, unsettled) | 180 / 600 credits | not stated | 5 minutes a month, Fliki watermark | free 720p, paid 1080p |
| Lumen5 | Basic $19, Starter $59, Pro $149 (billed yearly) | unlimited videos, capped AI voice | not stated | 5 videos a month of 2 minutes, branded outro | 1080p from the $59 plan |
| Canva | Pro $18, Business $25 a person | "10x / 20x more AI than Free" | resets monthly | limited AI | not stated |
| CapCut | Pro £21.99 a month / £199.99 a year, Ultra £58 / £669 (iOS US: $9.99 and $19.99 a month, $89.99 a year) | 1,200 / 6,464 AI credits | not stated | exists, limits not stated | not verified |
| Veed | Creator $12, Pro $22 a user (third party) | 6,000 credits | No | conflicting reports | Creator 1080p, Pro 4K |
| Descript | Hobbyist $24 / $16, Creator $35 / $24, Business $65 / $50 | 400 / 800 / 1,500 AI credits | not stated | 1 hour a month, watermark | free 720p, Hobbyist 1080p, Creator 4K |

### 2.2 Consumer AI apps that sell credits

| App | Plans: monthly / yearly per month | Credits a month | Rollover | Free |
|---|---|---|---|---|
| Runway | $15 / $12, $35 / $28, $95 / $76 | 625 / 2,250 / 9,500 | only the top plan, one month | 125 once |
| Pika | $10 / $8, $35 / $28, $95 / $76 | 600 / 2,600 / 8,550 | No | none monthly |
| Luma | $30 / $25, $90 / $75, $300 / $250 | 10,000 / 40,000 / 150,000 | not stated | |
| Suno | $10 / $8, $30 / $24, $120 / $100 | 2,500 / 10,000 / 15,000 | No | 50 a day, no commercial use |
| ElevenLabs | $6 / $5, $22 / $18.33, $99 / $82.50 | 30k / 121k / 600k | up to 2 months | 10k |
| Captions (iOS) | $24.99, $69.99, up to $279.99 | 500 / 1,400 / 5,600 | up to 2 months | |

### 2.3 What the market says
* The first paid plan costs $15 to $29 billed monthly, $10 to $20 a month billed yearly. Yearly discounts of 17 to 50 %.
* Stock-and-narration video (videomk's kind) sells at about **$0.50 to $1.00 a minute** on entry plans; avatar video at $1.20 to $1.60.
* Three rungs named roughly Starter/Pro/Max, the top one 2.5 to 4 times the price of the first, are the norm (InVideo, Runway, Pika, Suno).
* Credits reset each month almost everywhere. Rollover, where it exists, is capped at one or two months and is used as a reason to take the higher plan (HeyGen, Runway Max, ElevenLabs, Captions).
* Free plans are capped three ways: a watermark or branded outro, 720p, and a small count a month (3 to 5 short videos). A free credit every day is unusual (Suno, Kling).
* 1080p arrives with the first or second paid plan, 4K with the second or third.
* Commercial use is a paid right where it is stated (Pika, Suno, Luma, ElevenLabs, Fliki).

---

## 3. Store rules that shape the design (official pages read 2026-11-27)

### 3.1 Fees
| | Rule |
|---|---|
| Apple, standard | 30 %; subscriptions 15 % after one year of paid service |
| Apple Small Business Program | **15 % on everything** while proceeds stay under $1M a year. New developers qualify; the Account Holder must enrol. The rate starts 15 days after the end of the fiscal month of approval, so enrol before the first sale |
| Apple, EU (new terms since 1 October 2026) | in-app purchase 26 %, or 15 % in the Small Business Program; a link to a web offer 15 % or 10 % on sales within 7 days of the tap |
| Apple, US | links and calls to action to a web checkout are allowed without an entitlement. The commission on them is reported as zero today (secondary source, August 2026); the courts are still setting a rate. Treat zero as temporary |
| Apple, UK and rest of world | 30 % / 15 %, **no link or call to action to other ways to pay inside the app** |
| Google Play (new model since 30 June 2026 in the US, EEA and UK) | 10 % service fee on subscriptions and on the first $1M a year, plus 5 % when Play Billing is used: **about 15 % all-in**, 10 % through alternative billing or web links (which need enrolment and reporting) |
| Google Play, other countries until the new model reaches them | 15 % on the first $1M and on subscriptions |

### 3.2 Saying "buy on the web" inside the app, today
| Region | iOS | Android |
|---|---|---|
| US | allowed | allowed after enrolling in Google's programmes |
| EU / EEA | allowed under the EU terms, with commission | allowed through the billing choice or external offers programmes |
| UK | **not allowed** (the CMA consulted on steering in June 2026; no decision found) | allowed through the billing choice programme since 30 June 2026 |
| Elsewhere | not allowed | not allowed |

Everywhere: emails and the website may promote the web checkout, and a plan bought on the web or on another platform may be used in the app provided the same plan is also sold as an in-app purchase there (Apple guideline 3.1.3(b)). So **one account, one plan, valid on iOS, Android and web** is permitted.

### 3.3 Subscriptions and credits
* A subscription may include credits (Apple 3.1.2(a)). Apple says credits **bought** as in-app purchases may not expire (3.1.1); it does not say that for credits granted each month by a subscription. Monthly credits that reset are common practice (section 2), but the official text does not address it: a small review risk.
* Apple: one subscription group, one active plan per group. An upgrade (Pro to Max) is immediate with a prorated refund; a downgrade applies at the next renewal; monthly to yearly of the same level is immediate.
* Google Play: one subscription with base plans (monthly, yearly) and offers. Play also has a "prepaid" base plan (a fixed period without auto-renewal); not used here.
* Paywall must show: the plan's name and length, what it gives, the **full price charged as the most prominent price** (a per-month figure for a yearly plan must be smaller), trial terms if any, a restore button, links to Terms and Privacy. Google adds: how to cancel, and an easy way to cancel from inside the app.
* Also required and already in place or tracked: in-app account deletion, a demo account for review.

### 3.4 Prices
* Apple: 800 price points; choose a base country and Apple converts for 174 storefronts, or set GBP and EUR by hand (Apple then leaves those alone). UK and EU prices include VAT.
* Google: a base price is converted, each country can be edited; UK and EU prices must include VAT.

### 3.5 Offers
* Apple: one introductory offer per plan (free trial, a lower price for some periods, or pay up front), once per customer per group; promotional offers for existing and lapsed subscribers; offer codes; win-back offers. Billing grace period of 3, 16 or 28 days.
* Google: free trial or introductory price per base plan; eligibility new customer, upgrade, or decided by the developer.

### 3.6 Refunds
* Apple decides refunds; the developer is told by server notification (`REFUND`, `REFUND_REVERSED`, `REVOKE`, and for renewals `DID_RENEW`, `DID_FAIL_TO_RENEW`, `GRACE_PERIOD_EXPIRED`, `EXPIRED`). Apple says the developer is responsible for acting on each refund and may take back what was granted, telling the user.
* Google handles requests in the first 48 hours, then the developer does. Refunds, chargebacks and revokes arrive as real-time notifications and through the Voided Purchases API.
* **Rule proposed for videomk:** on a refund, remove the unused credits of that period and return the account to Free. Credits already spent stay spent (the videos keep their paid rights); a second refund on the same account flags it for review.

### 3.7 Checking purchases
* Apple: StoreKit 2 signed transactions, the App Store Server API, Server Notifications V2. Set `appAccountToken` (a UUID tied to the videomk user) at purchase.
* Google: `purchases.subscriptionsv2.get` on the server, `obfuscatedAccountId` at purchase, **acknowledge within three days or Google refunds the purchase**.

### 3.8 Tax
* Store sales: Apple and Google charge and pay the VAT in the UK and EU. Agilegency receives the price minus VAT minus the fee. (Google states this on its page; Apple's Schedule 2 wording was not verified today.)
* Web sales by a UK company: UK VAT 20 %, registration threshold £90,000 of taxable turnover; sales to EU consumers carry the customer's country VAT from the first sale (non-Union One Stop Shop); US sales tax state by state (from memory, not verified).
* A merchant of record removes that work: Stripe Managed Payments 3.5 % on top of card processing (about 6.4 % + 30 c in the US), Paddle 5 % + 50 c.

---

## 4. What the customer pays and what Agilegency keeps

Exchange rates of 2026-11-26 (measured): £1 = $1.31, €1 = $1.10. VAT 20 % UK, 21 % EU (assumed average). Store fee 15 % (Small Business Program and Google's new model). Web: merchant of record at about 7.5 % + 30 c (assumed).

| Plan | Price | Before VAT, in USD | Kept after the store | Kept on the web | Kept per credit (store) |
|---|---|---|---|---|---|
| Pro monthly, US | $14.99 | $14.99 | $12.74 | $13.57 | $0.42 |
| Pro monthly, UK | £12.99 | $14.18 | $12.06 | $12.82 | $0.40 |
| Pro monthly, EU | €14.99 | $13.60 | $11.56 | $12.28 | $0.39 |
| Pro yearly, US | $149.99 ($12.50 a month) | $12.50 | $10.62 | $11.54 | $0.35 |
| Pro yearly, UK | £129.99 | $11.83 | $10.05 | $10.92 | $0.34 |
| Pro yearly, EU | €149.99 | $11.34 | $9.64 | $10.46 | $0.32 |
| Max monthly, US | $39.99 | $39.99 | $33.99 | $36.69 | $0.28 |
| Max monthly, UK | £34.99 | $38.21 | $32.48 | $35.04 | $0.27 |
| Max monthly, EU | €39.99 | $36.27 | $30.83 | $33.25 | $0.26 |
| Max yearly, US | $399.99 ($33.33 a month) | $33.33 | $28.33 | $30.81 | $0.24 |
| Max yearly, UK | £349.99 | $31.85 | $27.07 | $29.43 | $0.23 |
| Max yearly, EU | €399.99 | $30.23 | $25.70 | $27.94 | $0.21 |

**Margin on store sales** (what is kept minus the cost of the credits, as a share of what is kept). Cost per credit $0.15 (p50) and $0.20 (p90), measured. "60 % used" is an assumption about how much of an allowance people spend.

| Plan | Every credit used, p50 | Every credit used, p90 | 60 % used, p50 | 60 % used, p90 | Kept a month at 60 %, p50 |
|---|---|---|---|---|---|
| Pro monthly, US / UK / EU | 65 / 63 / 61 % | 53 / 50 / 48 % | 79 / 78 / 77 % | 72 / 70 / 69 % | $10.04 / $9.36 / $8.86 |
| Pro yearly | 58 / 55 / 53 % | 44 / 40 / 38 % | 75 / 73 / 72 % | 66 / 64 / 63 % | $7.92 / $7.35 / $6.94 |
| Max monthly | 47 / 45 / 42 % | 29 / 26 / 22 % | 68 / 67 / 65 % | 58 / 56 / 53 % | $23.19 / $21.68 / $20.03 |
| Max yearly | 36 / 34 / 30 % | 15 / 11 / 7 % | 62 / 60 / 58 % | 49 / 47 / 44 % | $17.53 / $16.27 / $14.90 |

Reading it: no plan loses money even when every credit is used at the p90 cost, but **Max yearly in the EU is thin there (7 %)**. Rollover makes heavy use of Max more likely. If the two cost savings of 1.4 bring a credit to about $0.09, Max yearly at full use rises to about 58 to 62 %.

---

## 5. The proposal

### 5.1 Recommended: Free, Pro, Max

| | Free | Pro | Max |
|---|---|---|---|
| For | trying it and spreading the name | people who make a video a day at most | creators and small businesses; the default choice on the paywall |
| Monthly | | $14.99 / £12.99 / €14.99 | $39.99 / £34.99 / €39.99 |
| Yearly | | $149.99 / £129.99 / €149.99 | $399.99 / £349.99 / €399.99 |
| Credits | 5 welcome (30 days), 1 a day (same night) | 30 at each monthly date; unused ones end | 120 at each monthly date; unused ones carry over once (balance capped at 240) |
| Yearly plans | | 30 credits each month, not 360 at once | 120 credits each month, not 1,440 at once |
| Watermark | forced: "videomk" with the name, and an end card | off, or "moments" mode | off, "moments", or own logo |
| Resolution | 720p, 1080p | 720p, 1080p | 720p, 1080p, 4K (double credits) |
| Longest video | 1 minute | 5 minutes | 12 minutes |
| Storage | 2 GB | 100 GB | 300 GB |
| Queue | standard | standard | priority |
| Photos per video (proposed numbers, check against the engine's limits) | 10 | 30 | 60 |
| Web research | yes | yes | yes |
| Looks | standard | all standard looks | early access to premium looks (3D backgrounds, animated vector scenes) |
| Use | personal and non-commercial; the watermark must stay | commercial use | commercial use |

**Why these numbers**
* **Pro at $14.99 for 30 credits ($0.50 a minute)** sits at the low end of the market for this kind of video ($0.50 to $1.00) and under the entry price of InVideo, Pictory, Synthesia and HeyGen. It is the same price per credit as the 20-credit pack proposed earlier in `docs/CREDITS.md`.
* **Max at $39.99 for 120 credits ($0.33 a minute)**: four times the credits for 2.7 times the price, three times the storage, and every premium right. This is the plan the paywall highlights; Pro exists mainly to make Max look like the obvious deal and to catch the price-sensitive.
* **Yearly at two months free (17 %)**, not the 40 to 50 % some competitors give: the margin on Max cannot carry more (section 4).
* **Credits each month on yearly plans**: handing 1,440 credits at once would let a refund or a burst cost more than the plan brings in.
* **No free trial of the paid plans**: the free plan is the trial, and a trial with 30 or 120 credits costs up to $4.50 or $18 in real money per person. Instead: an introductory price on the monthly plans (first month at half price, once per customer). See open decision 4.

**What makes Max compelling, and what each thing costs us**

| Max feature | Cost to us per use |
|---|---|
| 120 credits at $0.33 | real: $0.15 to $0.20 per credit used |
| Rollover of one month | real, indirect: more of the allowance gets used. Worst case in section 4 already assumes all of it |
| 4K | covered: a 4K credit costs $0.13 to $0.16 and the video takes double credits (5 videos measured) |
| Own logo | nothing |
| 12-minute videos | nothing extra: credits scale with length (12 credits cost $2.18 measured at 1080p, slightly more per credit than short videos) |
| Priority queue | nothing while capacity is free; it only orders the queue |
| 300 GB | real if filled: $7.50 in the first month, $1.80 a month at rest, plus $20 to $90 once to index 200,000 photos (estimate). Few will fill it |
| More photos per video | about $0.001 to $0.03 per video in photo reviews (measured range) |
| Premium looks (3D backgrounds) | **real**: the 3D loop draws at 296 ms a frame against 166 ms for a static background (`docs/` commit note of 2026-11-27), so scenes that use it cost about 1.8 times as much to render: roughly $0.03 to $0.05 more per minute of such scenes at today's function size (estimate) |
| Commercial use | nothing; needs the legal wording of open decision 7 |

**Commercial-use wording (draft for the legal page, to be reviewed)**
* Free: "Videos made on the free plan are for personal, non-commercial use and carry the videomk mark, which must not be removed or hidden."
* Pro and Max: "You may use the videos you make for commercial purposes, including advertising and client work, while your plan is active and afterwards for videos made during it. Stock photos, clips and music keep the licence terms of their sources."

### 5.2 Cheaper to build: one paid plan

Free plus a single **Pro** (the Pro of 5.1 with 4K, own logo and 12 minutes added, 40 credits, $19.99 / £17.99 / €19.99 a month, $199.99 a year), sold **only in the two stores**, with a subscription service such as RevenueCat doing the receipt checks and webhooks (its current price was not verified). Two products per store, one entitlement flag, no web checkout, no upgrade path to build, no rollover. Margin at full use: $16.99 kept in the US, $6.00 to $8.00 of cost, 53 to 65 %. It gives up the "Max is the obvious deal" effect and the higher revenue per customer, and can grow into the three-rung ladder later without changing what existing subscribers have.

### 5.3 Why subscriptions and not packs
The owner has declined prepaid credit packs for now. For the record only: top-ups for subscribers who run out mid-month are common in this market (HeyGen, Suno, Runway), and Apple requires that bought credits never expire. They can be added later without changing the ladder; they are not in the product list below.

### 5.4 The free plan: cost, and how it pushes towards paying

**The problem, plainly.** At today's cost a person who uses the daily credit every day costs $4.20 to $6.00 a month. One Pro subscriber leaves about $7 to $10 a month after their own videos. So **one payer funds about two heavy free users, or about 12 to 16 typical ones** (at the assumed $0.60 a month). With a usual free-to-paid conversion of a few per cent (assumed), the free plan as decided loses money unless free use is light or the cost per credit falls.

**Measures, without touching what is decided (5 welcome credits, 1 a day, watermark):**
1. **Lower the cost per credit first** (section 1.4): caching and a smaller render function are worth more to the free plan than any limit.
2. **Free videos last at most 1 minute.** The 5 welcome credits are then five short videos, not one 5-minute one, and every free credit is the cheapest kind.
3. **A daily budget for all free videos together** (already listed "to build" in `docs/CREDITS.md`): when the day's free budget is spent, free users see "Free videos are done for today; go Pro to make yours now". This puts a hard ceiling on the loss.
4. **Free credits only for verified devices and Apple or Google sign-in** (DeviceCheck / App Attest, Play Integrity: the key is in the owner's pending list), so one person cannot farm accounts.
5. **Paid videos go first** in the queue; free ones wait when it is busy.
6. **The watermark does the marketing**: name always visible and an end card "Made with videomk" with the link. Sharing stays free and unlimited: that is the point of the free plan.
7. Keep 1080p on Free. 720p would save little (measured $0.13 against $0.16 per credit, 7 videos) and would make the shared videos, which are the advertisement, look worse.

If the first month of real data shows free use near the heavy case, the next step is open decision 2 (the daily credit).

### 5.5 Upgrade moments in the product

| Moment | What the person sees | Leads to |
|---|---|---|
| Out of credits (the chip already says "See credits") | "Your next free credit arrives tomorrow. Make it now with Max: 120 videos a month." | paywall, Max highlighted |
| After the first shared video | the video with and without the watermark, side by side | "Remove the mark" (Pro), "Use your logo" (Max) |
| Choosing 4K, or a length over 1 minute (Free) or over 5 minutes (Pro) | the option is visible with a small plan badge, not hidden | paywall on that feature |
| Storage at 85 % and when full | the storage meter turns amber, then red; uploads stop, nothing is deleted | Pro (100 GB), Max (300 GB) |
| The daily free budget is spent, or the queue is busy | "Free videos are paused for today" / "Paid videos go first" | paywall |
| Pro subscriber uses more than 80 % of the credits two months running | "Max gives four times the credits for $25 more" | upgrade (Apple and Google prorate) |
| Welcome credits about to end (day 25) | "3 credits end in 5 days" | paywall with the introductory price |
| Choosing a premium look | preview plays, "Max" badge | paywall |

Paywall layout: Max in the middle, pre-selected, yearly toggle on by default, full yearly price as the largest figure (store rule), "2 months free" as the saving, restore button, Terms and Privacy links, how to cancel.

### 5.6 Store products to create

**App Store Connect** (bundle `com.videomk.app`). One subscription group, "videomk plans". Level 1 = Max (highest), level 2 = Pro.

| Product id | Type | Level | Price (US base; set UK and EU by hand) | Introductory offer |
|---|---|---|---|---|
| `com.videomk.app.max.monthly` | auto-renewable, 1 month | 1 | $39.99 / £34.99 / €39.99 | first month $19.99 (pay as you go, 1 period) |
| `com.videomk.app.max.yearly` | auto-renewable, 1 year | 1 | $399.99 / £349.99 / €399.99 | none |
| `com.videomk.app.pro.monthly` | auto-renewable, 1 month | 2 | $14.99 / £12.99 / €14.99 | first month $7.49 |
| `com.videomk.app.pro.yearly` | auto-renewable, 1 year | 2 | $149.99 / £129.99 / €149.99 | none |

Also in App Store Connect: enrol in the Small Business Program before the first sale; billing grace period 16 days; Server Notifications V2 URL for production and sandbox; EUR prices set once for all euro storefronts (VAT differs by country; Apple keeps the shelf price, the amount kept varies a little).

**Google Play Console** (two subscriptions, each with two base plans)

| Subscription id | Base plan id | Type | Price | Offer |
|---|---|---|---|---|
| `videomk_max` | `monthly` | auto-renewing, 1 month | $39.99 / £34.99 / €39.99 | `intro-half`: first month at 50 %, new customers |
| `videomk_max` | `yearly` | auto-renewing, 1 year | $399.99 / £349.99 / €399.99 | |
| `videomk_pro` | `monthly` | auto-renewing, 1 month | $14.99 / £12.99 / €14.99 | `intro-half` |
| `videomk_pro` | `yearly` | auto-renewing, 1 year | $149.99 / £129.99 / €149.99 | |

Also in Play Console: real-time developer notifications (a Pub/Sub topic), a service account for the Developer API, grace period on.

**Web (app.videomk.com)**: the same four prices with a merchant of record (Stripe Managed Payments or Paddle), ids `pro_monthly`, `pro_yearly`, `max_monthly`, `max_yearly`.

**Later, not at launch**: storage blocks as a second subscription group so they can sit next to a plan (for example `com.videomk.app.storage.100` at $2.99 a month for 100 GB; a full block costs $2.50 in its first month and $0.60 at rest). The stores do not sell "two of the same subscription", so each size is its own product.

### 5.7 What the backend needs (headlines)

1. **Entitlements record per account**: plan (`free`, `pro`, `max`), period end, source (apple, google, web), state (active, grace, expired, refunded). One function answers "what may this account do": watermark modes, resolutions, longest video, storage limit, queue priority, premium looks. Today's separate flags (`storage_plan`, `watermark_custom`) become derived from it. `GET /capabilities` already carries most of these to the apps.
2. **Monthly credit grant**: a new wallet bucket kind `plan` that ends at the next monthly date (Max: one extra month, balance capped at 240). Granted on purchase and on each renewal notification, once per period (the store's transaction id as the key, as `grant_paid` already does). Yearly plans get a monthly grant from a daily job. Spending order stays "soonest to expire first".
3. **Purchase check endpoints**: `POST /purchases/apple` (verify the StoreKit 2 signed transaction, match `appAccountToken` to the caller) and `POST /purchases/google` (call `subscriptionsv2.get`, match `obfuscatedAccountId`, acknowledge).
4. **Webhooks**: Apple Server Notifications V2, Google real-time notifications (Pub/Sub), the web provider. Each updates the entitlement and is safe to receive twice. Handle renewal, failed renewal and grace, expiry, upgrade and downgrade, refund and its reversal.
5. **Refund rule** (3.6): take back unused plan credits, return to Free, keep a log, flag repeats.
6. **One plan per account across platforms**: if an account with an Apple plan opens the Android paywall, show "Managed in the App Store" and no buy button, so nobody pays twice.
7. **Lapsed plans**: storage over the free limit becomes read-only (already designed in `docs/MEDIA_LIBRARY.md`); videos already made keep their look; the saved watermark setting falls back to the videomk mark for new videos.
8. **The free plan's controls** of 5.4: 1-minute cap, the daily free budget, device attestation, queue order.
9. **Apps**: a paywall screen, StoreKit 2 and Play Billing clients, restore, "Manage subscription" link, the upgrade moments of 5.5. Web: checkout and a billing page.
10. **Reporting**: extend `cost_report.py` to print cost per credit by plan, so the margins of section 4 are watched with real customers.

---

## 6. Future: enterprise and API (backlog, not to build now)

**Idea**: companies create any video from their own systems through an API, and pay for what they use.

**How others price video APIs** (read 2026-11-27)

| Product | Unit | Price |
|---|---|---|
| Shotstack (rendering from a template, no AI script or voice) | minute of rendered video | $0.20 pay as you go; plans $39 to $499 a month, $0.156 down to $0.05 a minute; 4K from the $99 plan |
| JSON2Video (rendering) | second of video (1 credit) | prepaid $49.95 for 120 minutes ($0.42 a minute); plans down to $0.17 a minute |
| Creatomate (rendering) | credits by length and resolution | $45 a month for 2,000 credits; a 30-second 720p video is 6.91 credits (about $0.31 a minute) |
| HeyGen API (avatar video) | seconds, by model and resolution, from a prepaid wallet | about $1 a minute (third-party sources, not verified) |
| Synthesia API | credits per minute, from the Pro plan up | 160 credits a minute (third party, not verified) |

**A sensible unit for videomk**: the **video-minute by resolution**, the same as a credit, so the app and the API share one meter. Rendering-only APIs sell at $0.05 to $0.40 a minute; videomk also writes the script, narrates and finds the pictures, so a list price of about $0.50 to $0.60 per HD minute and double for 4K, with volume steps down to about $0.30, fits both the market and the measured cost ($0.15 to $0.20). Billed monthly by invoice, with a minimum commitment for enterprise.

**What the ladder should leave room for**
* The entitlements record of 5.7 should accept more plan names (`business`, `enterprise`) and an `api` right, and limits that are data, not code.
* Usage metering per account and per API key (video-minutes by resolution), which the wallet and `credits_charged` already nearly provide.
* API keys with scopes and rotation, rate limits, webhooks for "video ready".
* Invoices, VAT numbers and reverse charge (business customers, outside the stores, so no store fee).
* Enterprise terms: service levels, a support contact, data-processing agreement, team seats and a shared brand kit (own logo, fonts, voices).
* Nothing in the consumer plans should promise "unlimited", so the API price is never undercut by a Max account used by a script; terms should forbid automated use of consumer plans.

---

## 7. Open decisions for the owner

| # | Decision | Recommended answer |
|---|---|---|
| 1 | Prices and credits of Pro and Max | As in 5.1: $14.99 for 30 and $39.99 for 120; yearly at two months free |
| 2 | The daily free credit costs up to $6 a month per heavy user. Keep it as decided? | Keep it for launch **with** the 1-minute cap and the daily free budget. Review after 30 days of real use: if the average active free user costs more than $1 a month, change to 3 free credits a week (a server setting) |
| 3 | Do the two cost savings (prompt caching, smaller render function for HD) before launch? | Yes, before the paywall work ships: they roughly halve the cost of every plan and of the free plan |
| 4 | Free trial or introductory price? | No free trial. First month at half price on the monthly plans |
| 5 | Is Max rollover worth its cost? | Yes, one month, capped at 240. It is the strongest reason to choose Max that costs nothing to build twice |
| 6 | Own logo only on Max (today's code gives it to the Pro storage plan) | Max only; Pro removes the mark or uses "moments" |
| 7 | Commercial-use wording and the music and stock licences behind it | Take the draft of 5.1 to the legal review already open in `docs/LEGAL_DRAFT_NOTES.md` |
| 8 | Web checkout at launch? | Stores first (they are where the users are). Web checkout second, with a merchant of record so Agilegency does not register for VAT in each EU country. Same prices as the stores |
| 9 | Tell app users about the web checkout? | Not at launch. Later: a link in the US iOS app and in the Android app where Google's programmes allow it; never in the UK iOS app until the rule changes |
| 10 | Build the receipt checks ourselves or use a service (RevenueCat or similar)? | Decide after checking its current price. A service saves about two to three weeks; own code avoids a share of revenue and a dependency |
| 11 | Storage add-on blocks | After launch; $2.99 a month per 100 GB as a second subscription group |
| 12 | Enrol in Apple's Small Business Program and accept the Paid Apps agreement; set up Google payments profile and tax forms | Now: the 15 % rate starts only after approval |
| 13 | Yearly plans: credits each month or all at once? | Each month |
| 14 | Enterprise and API | Record as backlog (section 6); design the entitlements record so it fits |

---

## 8. Sources (all accessed 2026-11-27)

**Measured here**: QA videos table `videomk-qa-VideosTable...` (85 completed videos, 25 to 27 November); CloudWatch Logs Insights on the six `v2_*` functions; CloudWatch `AWS/Bedrock` token counts; AWS Cost Explorer for accounts 552357225438 (QA) and 464863885161 (production); exchange rates from api.frankfurter.app (ECB reference, 2026-11-26). Repository documents: `docs/COSTS.md`, `docs/CREDITS.md`, `docs/FOUR_K.md`, `docs/STORAGE.md`, `docs/MEDIA_LIBRARY.md`, `docs/WATERMARK.md`.

**Competitors**
* https://invideo.io/pricing/ , https://invideo.io/help/billing/how-do-credits-work/ , https://apps.apple.com/us/app/invideo-ai-ai-video-generator/id6471394316
* https://pictory.ai/pricing
* https://www.synthesia.io/pricing
* https://www.heygen.com/pricing
* https://fliki.ai/pricing , https://toolradar.com/tools/fliki/pricing (third party)
* https://lumen5.com/pricing/
* https://www.canva.com/pricing/
* https://www.capcut.com/pricing , https://apps.apple.com/us/app/capcut-video-editor/id1500855883
* https://www.veed.io/pricing , https://toolradar.com/tools/veed/pricing (third party)
* https://www.descript.com/pricing
* https://runway.com/pricing , https://pika.art/pricing , https://lumalabs.ai/pricing , https://suno.com/pricing , https://elevenlabs.io/pricing , https://www.captions.ai/pricing
* APIs: https://shotstack.io/pricing/ , https://json2video.com/pricing/ , https://creatomate.com/pricing ; HeyGen and Synthesia API figures from third parties: https://www.arcade.software/post/heygen-pricing , https://magichour.ai/blog/synthesia-pricing-2026

**Apple**
* https://developer.apple.com/app-store/small-business-program/
* https://developer.apple.com/app-store/subscriptions/
* https://developer.apple.com/app-store/review/guidelines/ (3.1.1, 3.1.2, 3.1.3)
* https://developer.apple.com/support/dma-and-apps-in-the-eu/
* https://developer.apple.com/help/app-store-connect/manage-app-pricing/set-a-price/
* https://developer.apple.com/help/app-store-connect/manage-subscriptions/manage-pricing-for-auto-renewable-subscriptions/
* https://developer.apple.com/help/app-store-connect/manage-subscriptions/set-up-subscription-offer-codes/
* https://developer.apple.com/documentation/appstoreservernotifications/notificationtype
* https://developer.apple.com/documentation/appstoreserverapi/send-consumption-information
* https://developer.apple.com/documentation/storekit/handling-refund-notifications
* https://developer.apple.com/documentation/storekit/transaction/appaccounttoken
* https://developer.apple.com/help/glossary/price/
* US link-out commission (secondary): https://macdailynews.com/2026/08/14/u-s-supreme-court-clears-path-for-app-store-commission-showdown-as-apple-must-defend-its-rates-in-lower-court/

**Google**
* https://support.google.com/googleplay/android-developer/answer/112622 (service fees)
* https://android-developers.googleblog.com/2026/06/play-expanded-billing.html , https://android-developers.googleblog.com/2026/03/a-new-era-for-choice-and-openness.html
* https://support.google.com/googleplay/android-developer/answer/17161464 (billing choice)
* https://support.google.com/googleplay/android-developer/answer/15582165 (US programmes)
* https://support.google.com/googleplay/android-developer/answer/9858738 , https://support.google.com/googleplay/android-developer/answer/10281818 (payments policy)
* https://support.google.com/googleplay/android-developer/answer/12154973 (subscriptions, base plans, prepaid)
* https://support.google.com/googleplay/android-developer/answer/9900533 (subscriptions policy)
* https://support.google.com/googleplay/android-developer/answer/6334373 (prices)
* https://support.google.com/googleplay/android-developer/answer/138000 (tax)
* https://support.google.com/googleplay/answer/15574897 (refunds)
* https://developers.google.com/android-publisher/voided-purchases , https://developer.android.com/google/play/billing/rtdn-reference , https://developer.android.com/google/play/billing/integrate

**UK, EU, payments**
* https://www.gov.uk/guidance/the-cmas-programme-of-work-across-mobile-platforms
* https://www.gov.uk/vat-rates , https://www.gov.uk/how-vat-works/vat-thresholds
* https://www.gov.uk/guidance/the-vat-rules-if-you-supply-digital-services-to-private-consumers , https://vat-one-stop-shop.ec.europa.eu/one-stop-shop_en
* https://support.stripe.com/questions/managed-payments-pricing , https://www.paddle.com/pricing

**Not confirmed today**: Apple's commission on US web links; any CMA steering decision after 20 October 2026; Google's fee amounts for US web links; whether Apple accepts monthly expiry of subscription credits (not addressed in the text); Apple's Schedule 2 tax wording; InVideo's free plan; Veed, Fliki, Kling and HeyGen API prices from the vendors' own pages; US sales-tax thresholds; RevenueCat's price; the share of an allowance subscribers use (60 % is an assumption); free-to-paid conversion.
