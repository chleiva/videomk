# Library media on demand: clips, images, whiteboard sketch objects (2026-11-27 and 28)

**One framework, three media types** (owner, 2026-11-28: "limits for images, limits for videos, limits for objects in the sketch"):

    generalise the search -> check OUR library -> generate -> quality gate -> into OUR library -> only then into the video

* **Max plan only generates** (test and admin-granted accounts from their own budgets); **every plan reuses** what the library holds.
* **One invariant per account.** The month's allowance confirmed for clips ($2.90 monthly Max, $0.35 yearly; section 2) is ONE counter that clips, images and objects all draw from, so
  `kept - cost of credits - library spend >= floor` holds for the three together. Inside it each type has its own ceiling (owner, 2026-11-28: "go ahead, 3 instead of 5").
* **One transaction** reserves a generation on five counters: this video's count for the type, the account's total, the account's share for the type, the type's day budget, the type's month budget.
* **One config parameter** (`/videomk/<stage>/clips/config`), one deploy flag (`clipsOnDemand`), a master switch (`master_enabled`) and one switch per type (`enabled` = clips, `image_enabled`, `object_enabled`; all three off by default).
* **One report** (`clips_admin.py report`), one ledger, the same reason codes.

| | Clips (sections 0 to 13) | Images (part A) | Sketch objects (part B) |
|---|---|---|---|
| Provider, tier | Gemini Omni 1.2 Flash, 720p, 8 or 10 s | OpenAI gpt-image-2.6-flare, 2048x1152, high (the catalog's) | the same OpenAI model, one 2048x1152 medium sheet of up to 6 drawings |
| Charged per generation | $0.581 / $0.72 | $0.05 | $0.04 a call + $0.007 an object |
| Measured: provider cost, time, kept | $0.563 to $0.566; 34 to 41 s; 3 of 3 | $0.0442; 7 to 10 s; 2 of 3 (batch of 154: 64 %) | $0.0375 a sheet; 10 to 15 s for the whole call; 10 of 11 (library build: 92 % first try) |
| Account share of the month (monthly Max, total $2.90) | $1.75 = 3 | $1.00 = 20 generations | $0.15 = 2 to 3 calls |
| Yearly Max (total $0.35) | none | up to 7 | up to 2 calls |
| Per video | 2 | 4 | 1 call (up to 6 drawings) |
| Platform stop, paying accounts | $10 a day, $150 a month | $3 a day, $40 a month | $1 a day, $10 a month |
| Test and comped accounts | $3 an account; $2 a day, $20 a month | $1 an account; $1 a day, $10 a month | $0.30 an account; $0.50 a day, $5 a month |
| Where it runs, time limit | beat step, 150 s | beat step, 75 s | plan step, 30 s |
| Fallback | stock clip or photo | stock photo | the approximate drawing or the written label, as today |
| On-screen credit | "Video: VideoMK library" | **none** | none (drawings never had one) |
| Code | `engine/clip_ondemand.py` | `engine/image_ondemand.py` | `engine/object_ondemand.py` |

Shared code: `engine/ondemand.py` (entitlement, the allowance, `reserve`, decisions, metrics), `common/clip_config.py` (every knob, `limits()`), `common/clip_store.py` (rows and files), `engine/clip_brief.py` (reusable or not; clips and images).
Status: clips are built, tested and proven (sections 11 and 13). Images and objects are built behind the same flag, tested, and proven with small real runs (parts A and B). Nothing is merged or deployed.
Added 2026-11-27 (parts C, D and E at the end): **one safety policy** for everything we generate and own, with an audit of what the library already holds and a takedown command (part C);
**the tracer function** that lets sketch objects be made on Lambda, in a stack of its own (part D); **stock photo sources ranked so that Unsplash is the last resort** (part E).


Owner's requirement (condensed): instead of buying 100 random clips, VideoMK makes a clip when a Max customer's video asks for footage that our library does not have. Only when the
clip is general enough to be reused. Ours first (library), then their video. Hard limits so that no account and no day can lose money. Invisible to the customer. Observable.

Status: the owner confirmed the numbers and decisions D1 to D4 on 2026-11-27 (section 12). Sections 1 to 10 are the design; section 11 says what is built and tested; section 13 is the end-to-end proof. Everything is behind the flag `CLIPS_ON_DEMAND` (off everywhere)
and a live kill switch (`enabled`, off by default). Nothing is deployed.

## 0. The recommended numbers on one page

| What | Recommended | Why |
|---|---|---|
| Provider, size | Gemini Omni 1.2 Flash, **720p, 8 s** (10 s when the beat is longer than 8.5 s), 16:9 or 9:16 | cheapest top-quality option (docs/VIDEO_PROVIDERS_2026-11-27.md); 1080p and 4K are upsampled, so paying for them buys nothing (docs/FOUR_K.md); the pilot showed 5 s is too short |
| Cost of one generation | **$0.58** (8 s) or **$0.72** (10 s), checks included | section 1 |
| Expected rejections | **35 %** planned (to be measured), so about **$0.89 per kept 8 s clip** | section 1 |
| Max monthly account | **$2.90 a calendar month** for clips, images and objects together; clips up to **$1.75 = 3 generations** (changed from 5 on 2026-11-28 to leave room for images and objects) | half of what is left after all 120 credits at the p90 cost and a $1 floor, at the lowest (EU) price: section 2 |
| Max yearly account | **$0.35 a month: less than one clip, so none**; it still gets every clip already in the library | the EU yearly margin at p90 is $1.70: section 2 |
| Per video | at most **2 generations** | bounds the wait and spreads the allowance over 3 videos or more |
| Tightening | every credit used above the month's 120 (rolled-over credits) takes **$0.10** off the allowance; it is zero from 149 credits | section 2.3 |
| Platform budget, paying accounts | **$10 a day, $150 a month**, hard stop | section 3 |
| Test and comped accounts | **$3 an account a month**, 2 per video, from a separate budget of **$2 a day, $20 a month** | they bring no revenue, so they never touch the paying budget |
| Wait | generation may take at most **150 s**; never started later than 60 s into the beat; otherwise the stock clip or a photo | section 5 |
| Reuse | library clips serve **every plan**; only generation is Max-only | owner decision D1 (confirmed) |

## 1. What one clip costs (prices read 2026-11-27)

Source: Google's own price list, https://aistudio.google.com/docs/pricing (ai.google.dev/gemini-api/docs/pricing redirects there), read 2026-11-27. `gemini-omni-1.2-flash`: video output
**$12.00 per 1M tokens**; "Billing is based on total output token consumption, calculated at a rate of 5,792 tokens per second of 720p video". The page's own table: 360p 1,931 tokens/s
($0.023/s), 720p 5,792 ($0.0695/s), 1080p "with upsampling" 8,688 ($0.104/s), 4K "with upsampling" 17,376 ($0.209/s); "about $0.70 for a 10 s 720p clip". Input (the prompt) $1.50 per
1M tokens: under $0.001. Length 3 to 15 s in whole seconds, 16:9 or 9:16. Audio is generated by default and the page names no cheaper silent price (we strip the audio).
Note: `gemini-omni-1.1-flash` ($17.50 per 1M) is routed to 1.2 from 2026-12-03. Prices move: the price per second is a live knob (`price_per_second_usd`), not a constant in code.

| Length | 720p (native) | 1080p (upsampled) | 4K (upsampled) |
|---|---|---|---|
| 6 s | $0.417 | $0.626 | $1.251 |
| **8 s** | **$0.556** | $0.834 | $1.668 |
| **10 s** | **$0.695** | $1.043 | $2.085 |

Added per generation (model prices from docs/PLANS_PROPOSAL_2026-11-27.md, checked there against the bill): the reusability decision, one small-model call, about $0.0002; the provider's own "thought" tokens, billed as text output (measured on a real call: 1,166 tokens, about $0.010; not on the price page as such, so treat as measured, not quoted); the quality
gate, 6 frames to the large vision model (Sonnet-class, $2 per 1M input), about $0.010; the normal 3-frame check against the narration, $0.0003; two Cohere embeddings (brief text,
middle frame), under $0.001 (Cohere's price was not re-read today: unverified, but it is three orders of magnitude below the clip). **Overhead $0.025** (knob `overhead_usd`), so **$0.58 for 8 s and $0.72 for 10 s**. Measured on the first real call (3 s, 360p): the answer's usage block said 5,793 video tokens = exactly 1,931 a second, as the price list says.

Rejections: the 10-clip Gemini pilot ($3.75, tracker R065) left no reject count in the repository and its files are no longer on this machine, so there is no measured rate.
docs/VIDEO_CATALOG.md expects 20 to 40 % for calm, people-free scenes and 60 % or more with people, hands or crowds. The briefs here are written to be the first kind (section 4), so the
plan is **35 %**: $0.89 per kept 8 s clip ($1.16 at 50 %). The budgets count every generation, kept or not, so a worse rate means fewer clips, never more money. The real rate is a metric (section 9).

## 2. The cap per Max account

### 2.1 What is left of a Max subscription
Kept per subscriber per month after the store fee (15 %) and VAT, from docs/PLANS_PROPOSAL_2026-11-27.md section 4. Credits: 120 a month; cost per credit $0.15 (p50) and $0.20 (p90).

| Plan | Kept a month | Left if all 120 credits are used, p50 ($18) | Left at p90 ($24) | After a $1 floor (p90) | Half of that = the allowance | Generations of 8 s ($0.58) |
|---|---|---|---|---|---|---|
| Max monthly, US | $33.99 | $15.99 | $9.99 | $8.99 | $4.50 | 7 |
| Max monthly, UK | $32.48 | $14.48 | $8.48 | $7.48 | $3.74 | 6 |
| **Max monthly, EU** | **$30.83** | $12.83 | $6.83 | $5.83 | **$2.92** | **5** |
| Max yearly, US | $28.33 | $10.33 | $4.33 | $3.33 | $1.67 | 2 |
| Max yearly, UK | $27.07 | $9.07 | $3.07 | $2.07 | $1.04 | 1 |
| **Max yearly, EU** | **$25.70** | $7.70 | $1.70 | $0.70 | **$0.35** | **0** |

### 2.2 The rule (one formula)
```
allowance this calendar month = min( account_cap_usd,
                                     share x ( kept[interval] - floor_usd - credit_cost_usd x max(120, credits used this month) ) )
a generation is allowed only if   clip spend this month + its cost <= allowance   (and the per-video and platform limits also pass)
```
Recommended values: `kept` = **the EU figure of the interval** ($30.83 monthly, $25.70 yearly), because the entitlement record does not say which storefront sold the plan, so the
lowest is the only safe one; `credit_cost_usd` = **$0.20** (p90, not p50); `floor_usd` = **$1.00** (what must remain per account per month whatever happens); `share` = **0.5**;
`account_cap_usd` = **$3.00** (a ceiling over the formula, so a later change of the other knobs cannot quietly raise the cap). Result: **$2.90 a month for a monthly Max account
(the formula gives $2.915), $0.35 for a yearly one.**

Why p90 and all 120 credits from the first day: an allowance that looked at the credits used so far would be generous on day 1 and wrong on day 30 (the clips are bought, then the
customer uses the rest of the credits). Reserving the whole month's grant at the high cost means the invariant
**kept - cost of credits - clip spend >= floor** holds at the end of the month for every way the month can go: with all 120 credits used at p90 a monthly EU account still keeps
$30.83 - $24.00 - $2.90 = **$3.93**, a US one $7.09. At the p50 cost, or with credits left unused (the 60 % assumption of the proposal), it keeps far more.

Why half: the reserve counts only the measured cost of credits. It does not count the account's storage (Max allows 300 GB), fixed infrastructure, refunds, support, or a video above
the p90 cost. Half of the remainder stays as the buffer for those; the other half buys library clips, which are an asset that also serves every other customer.

### 2.3 The automatic tightening
Max credits roll over for a month, so an account can use up to 240 credits in one month. The 120 rolled-over credits were reserved by the month that granted them, but a month in
which they are burnt is a heavy month, so the formula uses `max(120, credits used this month)`: **each credit above 120 removes $0.10 (share x $0.20) from the allowance, and from 149
credits the allowance is zero** (yearly: from 123). Credits used = credits charged to the account's videos created this calendar month (UTC) that were not refunded (failed, cancelled
and rejected videos give their credits back and do not count). Honest limit: if clips were bought early and the account later burns more than 134 rolled-over credits in the same
month, that single month dips under the floor; the two months together do not, because the earlier month kept the reserve of the credits it did not use.

### 2.4 Yearly subscribers and the thin EU case
A yearly plan keeps less per month (two months free) and the EU yearly margin at p90 is $1.70. The same formula gives $0.35 a month, less than one clip. **Recommendation: yearly
accounts generate nothing for now and still receive every clip already in the library** (reuse costs nothing). Two ways to open it later, both owner decisions: (1) when purchases
are live and the entitlement records the storefront, use the storefront's own figure (US yearly $1.67 = 2 generations, UK $1.04 = 1); (2) when the cost per credit falls (the two
savings in the proposal bring it to about $0.09), lower `credit_cost_usd` and every allowance grows by itself.

### 2.5 Per video
At most **2 generations per video** (`video_cap_clips`). A 3-minute video has about 7 clip beats; two bound the extra wait and the money one video can take ($1.16), and leave the month's
allowance for at least three videos. Montage beats (2 to 4 short clips) only ask for a generation when the whole montage would otherwise fall back to a photo.

### 2.6 Accounts that pay nothing
Unlimited test accounts (`plan: test`) and Max plans granted by an admin (`source: admin`; today every Max account, because purchases are not live) bring no revenue. They follow the
same per-video and per-account limits (**$3.00 a month**, a flat cap, since there is no revenue to put in the formula) and draw from the **test budget**, never from the paying one.
Free and Pro never generate. A plan in its billing grace period does not generate either (the renewal has not been paid).

## 3. Global guardrails (live config)

One SSM parameter, `/videomk/<stage>/clips/config` (a JSON object, same pattern as the plans knobs: read with a 60 s cache, a missing or invalid knob falls back to its default, the
stack never creates or resets it; `backend/scripts/clips_admin.py config show|set|reset`). A read failure keeps the last good values; with none, the defaults, in which `enabled` is false.

| Knob | Default | Meaning |
|---|---|---|
| `enabled` | **false** | the kill switch. Generation needs BOTH the deploy flag `CLIPS_ON_DEMAND=1` and this. Off: no generation; library reuse continues (`reuse_enabled`) |
| `reuse_enabled` | true | library clips are offered to videos at all (second switch: off removes the own library from the beat step) |
| `reuse_plans` | free, pro, max, test | plans whose videos may use library clips |
| `platform_day_usd` / `platform_month_usd` | 10 / 150 | all on-demand spend of paying accounts in a UTC day / calendar month; reached = no generation until the next day / month |
| `test_day_usd` / `test_month_usd` | 2 / 20 | the same for test and comped accounts |
| `master_enabled`, `image_enabled`, `object_enabled` | true, false, false | the master switch and the other two types' switches; their own limits are in the table at the top and in `common/clip_config.py` (`image_*`, `object_*`, `clip_account_cap_usd` 1.75) |
| `account_cap_usd`, `share`, `floor_usd`, `credit_cost_usd`, `kept_usd_month`, `kept_usd_year` | 3.00, 0.5, 1.00, 0.20, 30.83, 25.70 | section 2.2 |
| `test_account_cap_usd` | 3.00 | section 2.6 |
| `video_cap_clips` | 2 | section 2.5 |
| `price_per_second_usd`, `overhead_usd` | 0.0695, 0.025 | what a generation is charged to the budgets (the provider reports no dollar amount) |
| `clip_seconds`, `clip_seconds_long` | 8, 10 | lengths generated |
| `gen_timeout_s`, `start_deadline_s` | 150, 60 | section 5 |
| `search_min_score`, `reuse_min_score` | 0.35, 0.62 | library search floor (text to clip); "the library already has this brief" (brief to brief) |
| `min_demand`, `tight_share`, `min_demand_tight` | 1, 0.5, 2 | section 4: when half of the day's budget is spent, only briefs asked for by 2 or more videos are generated |
| `gate_min_score` | 7 | section 5 |
| `model` | gemini-omni-1.2-flash | the provider's model id |

Why $150 a month: it is the full allowance of about 52 monthly Max accounts. There are no paying subscribers yet, so it is a ceiling, not a forecast; raise it with the subscriber count
(the report shows the share used). $10 a day stops a burst (17 generations) long before the month is gone.
Order of checks, all in ONE DynamoDB transaction (section 8): per video, per account, platform day, platform month. The first that fails is the reason logged.

## 4. "Is it reusable?": from a specific search to a general brief

The director writes a specific wording for its beat. A library clip must fit many videos. The step between them (`engine/clip_brief.py`):

1. **Deterministic refusals before any model call** (free): the video has the person's own photos or is a deck; the plan forbids clips (`allow_clips=false`, current events and web
   research videos); the wording or its narration slot trips the privacy filter already used for the image demand log (`common/catalog_privacy`: names, possessives, digits, dates,
   addresses) or the list of news, brand and identity words (election, president, war, protest, logo, brand, celebrity, ...).
2. **One small-model call with a strict rubric** (`BRIEF_SYSTEM`): returns `{reusable, reason, brief, tags, people, motion}`. It must refuse when the point of the search is a
   named person, brand, logo, specific place, landmark, event, date, text on screen, a screen or document, anything news-like, anything a real person could be identified in, a
   diagram or animation, or when making it general would lose the point. Otherwise it writes the GENERAL scene: "woman in a red coat buying mangoes in Oaxaca market on a rainy
   Tuesday" becomes "busy outdoor fruit market, close on hands choosing fruit". The model's answer is data: an unreadable answer is a refusal (fails closed).
3. **Deterministic filters on the answer**: 4 to 22 words, no digits, no capitalised proper nouns, none of the banned words, `people` must be `none`, `hands` or `distant`
   (never `faces`), `motion` not `fast`.
4. **Library and demand first**: the brief is embedded (Cohere Embed v4) and compared with the library; a clip at or above `reuse_min_score` is used and nothing is generated.
   Then the demand log (one row per general brief, joined by embedding to an earlier brief when they are the same scene): it counts the distinct videos that asked. `min_demand`
   = 1 generates at the first ask; when half of the day's budget is gone only briefs with 2 or more askers are generated, so the money left goes to what is asked repeatedly.
5. **The prompt** (`build_prompt`, deterministic, the model never writes it): the brief plus fixed clauses against the known failure modes of video models: one continuous shot,
   slow steady camera, natural light, photorealistic, main subject centred (so a crop to vertical or square keeps it), no text, signs, logos or watermarks, no faces (people only
   from behind, at a distance, or hands), no fast motion, no crowds, no cuts or transitions, ambient sound only.

Every decision is logged with its reason code (`CLIP_DECISION` log line and metric `Decisions{Outcome}`): `not_entitled`, `own_photos`, `no_clips_plan`, `filter:<why>`,
`not_reusable:<why>`, `library_hit`, `low_demand`, `cap_video`, `cap_account`, `budget_day`, `budget_month`, `in_flight`, `too_late`, `too_long`, `generated`, `gate_rejected:<why>`,
`provider_failed`, `timeout`, `kill_switch`.

## 5. The flow: ours first

```
beat step (clip beat)                                             time
 1. own library search (embedding) -> normal checks -> USE        ~3 s    every plan in reuse_plans, costs nothing
 2. not there: decide (entitled? reusable? caps? budgets?)        ~2 s    Max and test only
 3. yes: GENERATE in the background  ||  stock search as today    stock runs meanwhile and is the fallback
 4. quality gate on the generated clip (6 frames)                 ~10 s
 5. pass: STORE IN OUR LIBRARY (file, poster, metadata, vectors)
 6. only then: select it for this video THROUGH the own-library provider (trim, crop, the normal 3-frame check against the narration)
 7. used -> the video shows our clip; anything else -> the stock clip found in 3, or a photo, exactly as today
```

* **Ours first is literal**: step 6 reads the clip back from the library by its id; there is no path from the provider to a customer's video that skips the library.
* **Quality gate** (`engine/clip_gate.py`): deterministic checks (length at least 90 % of what was asked, at least 1280x720 or 720x1280, not black or blank, the picture moves) and
  one call to the large vision model with 6 frames in order: it scores 0 to 10 how well the clip shows the brief and answers yes or no to artefacts or morphing (melting shapes,
  extra limbs or fingers, objects appearing or vanishing), visible text, logo or brand, an identifiable real person, anything unsafe, a cut or scene change, and whether the main subject stays in the
  central third (`center_safe`, which decides the crops of section 7). Kept only with every flag clean and score >= `gate_min_score`. **Fails closed**: unreadable answer or error = rejected.
* **A rejected clip** is never used and never stored for reuse: only a ledger row (brief, reason, cost) is written. Its cost counts against every budget.
* **Stored with**: brief, tags, the exact prompt, provider and model, cost, licence `VideoMK library`, both vectors, aspect, size, duration, gate verdict, the salted reference of
  the video that caused it, `created`, `uses`.
* **Human review** stays possible and cheap: `clips_admin.py sheet` makes a contact sheet of new clips; `clips_admin.py retire <id>` removes one from search.

### Where generation sits in time: inside the request
The owner wants the clip in THEIR video, so generation runs inside the beat step, in parallel with the stock search that already runs there. Beats are made in parallel (12 at a
time), so a video waits for its slowest beat, not for the sum: **the video is at most about 3 minutes later** than without the feature, and only when a generation runs right up to its limit.
* `gen_timeout_s` = 150: the provider call is abandoned after 150 s. `start_deadline_s` = 60: no generation starts later than 60 s into the beat. The beat function has 300 s:
  narration (about 10 s) + decision + 150 + gate and checks (about 25 s) stays under 250 s.
* Slow, failed, refused by the provider's filter, rejected by the gate, or not fitting the narration: the beat uses the stock clip it found meanwhile, or a photo. **The video never
  fails and never waits past the limit because of this feature**; every exception in the path is caught and becomes the fallback.
* A generation that times out is assumed billed (the API is synchronous and documents no way to collect a late result), so it stays in the budgets; the timeout rate is a metric.
* The alternative (generate after the video, for the next customer) is safer for latency but gives the paying customer nothing and was not chosen. It remains available as a
  one-knob change later (`start_deadline_s` = 0 would disable in-request generation), not built as a separate path.
* A retried beat (Step Functions retries a failed beat) never pays twice: the first attempt leaves a claim row per video and beat; the retry reuses its clip or goes to stock.

## 6. Who gets it
* **Generation**: effective plan Max in state active (not grace) with a store or web source: paying budget and the formula. Test accounts and admin-granted Max: test budget.
  Never Free or Pro. Never on a video made of the person's own photos, never on a deck, never during an edit of an existing video (edits reuse the library only).
* **Reuse**: every plan in `reuse_plans`.
* **Transparent**: no UI, no setting, no message. The on-screen credit of a library clip reads "Video: VideoMK library"; the description's credit block leaves the source out, as
  for library images. The customer is never charged credits for a generation.

## 7. Aspect ratios and 4K
* The provider makes 16:9 and 9:16. A landscape or square video generates **16:9**; a vertical (9:16 or 4:5) video generates **9:16**.
* Serving other shapes: a 16:9 library clip serves a 9:16, 4:5 or 1:1 video by the centre crop the engine already applies to stock footage (centre horizontally), **only when the
  gate marked it `center_safe`**, and the normal check then judges the cropped frames, so a subject the crop loses still fails. A 9:16 clip serves vertical and 4:5 videos and is
  never cropped to landscape (it would keep a third of the picture). Same-shape clips are preferred in search.
* 4K videos: clips are generated at 720p only and shown in the framed native-size window (docs/FOUR_K.md, built 2026-11-27): `transcode` keeps a source under 1900 px wide at
  1280x720 and the renderer windows it. Never upscaled full screen. Nothing new was needed.

## 8. Storage, budgets and promotion (no new stack resources)
* **Files**: the existing assets bucket, prefix `cliplib/`: `v/<id>.mp4` (the provider's file, audio stripped), `p/<id>.jpg` (poster), `m/<id>.json` (all metadata and both vectors: the
  source of truth). `<id>` is the SHA-256 of the video. No lifecycle rule touches the prefix: a clip costs $0.58 once and about $0.0001 a month to keep (4 to 6 MB; 1,000 clips are
  about 5 GB, $0.12 a month).
* **Index, budgets, demand, claims**: rows in the existing usage table under the partition prefix `clipgen:` (the table already holds the free-plan budget rows the same way).
  The library index row carries the vectors (2 x 1024 float32 = 8 KB); search is an exact cosine comparison in the function over all rows (cached while warm). That is right up to a
  few thousand clips; beyond that the index should move to S3 Vectors in a small separate stack (not needed now, said here so it is not forgotten). The usage table has no backups and
  is destroyed with a non-production stack: the index is rebuilt from `cliplib/m/` with `clips_admin.py reindex`.
* **No double spend**: a generation first RESERVES its price in one `TransactWriteItems` over four counters (video, account-month, platform-day, platform-month; or the test ones),
  each with the condition `spent + price <= limit`. Two beats racing for the last dollar: one transaction fails, that beat goes to stock. A provider failure before billing releases
  the reservation; otherwise it stays (settled to the configured price). A brief being generated holds a 10-minute lock row, so two beats never buy the same scene at once.
* **QA to prod without paying twice**: `clips_admin.py promote --from qa --to prod` copies the three objects and the index row of each chosen clip (by id; idempotent; `--dry-run`
  by default; prod needs `--yes-prod`). It never calls the provider or the embedder: the vectors travel with the clip. A local folder (`local:<dir>`) is a third kind of store, so a
  library made on a laptop can be promoted the same way.
* **IAM added to the beat function only when the flag is on** (statements on its existing policy, no new resource): the usage table (read, write, transactions), `cliplib/*` in
  the assets bucket (get, put), the config parameter (read). The provider key is read from `/videomk/gemini_api_key` (SecureString, which the function may already read as `/videomk/*_api_key`) **at every call and never kept**: the owner rotates the key in SSM and the next generation uses the new one, with no deploy and no restart. The usage-table statement is limited to partitions that start with `clipgen:`.
* **Room for exclusive media later (backlog, not built)**: every clip record carries `scope`, today always `library`. Search reads only `scope = library`, `add_clip` refuses any other scope, and promotion skips it, so a future clip made for and owned by one customer (`scope: exclusive`, `owner`) can never reach another account through the shared library; it will need its own store path and rights.

## 9. Observability
* **Metrics** (embedded metric format, namespace `videomk/Clips`, no API call): `Decisions{Outcome}`, `Generated`, `Rejected{Reason}`, `Used{Source=library|generated}`,
  `SpendUsd{Kind=paid|test}`, `CapHit{Cap=video|account|platform_day|platform_month|test_day|test_month}`, `BudgetStop{Kind}` (a platform budget refused a generation),
  `GenerationSeconds`, `Timeout`, `ProviderError`.
* **Rows the report reads**: day and month spend, per-account month spend and count, each clip's `uses` and distinct `videos`, the ledger of every generation (kept or rejected), the demand log.
* **Report**: `backend/scripts/clips_admin.py report --store qa|prod|local:<dir> [--days 30] [--json]`: generated, rejected by reason, rejection rate, spend by day and by account (salted refs), cap hits and
  budget stops, latency p50/p95, library size, top clips by reuse, the most-asked briefs without a clip, and the **reuse rate**.
* **Reuse rate, the test of "general"**: a clip older than 30 days used by fewer than 2 different videos is a **miss**. The report lists misses and gives `misses / clips older than
  30 days`. Target: under 40 %. Above it the generalisation rubric is too permissive: tighten the rubric or raise `min_demand` to 2.
* **Alarms**: two, in a separate optional stack (`-c clipsAlarms=1`, `backend/clips_obs.py`, 2 resources, no action because there is no notification topic yet): any `BudgetStop` in a
  day; `SpendUsd` in a day at or above 80 % of the daily budget. Not in the main stack (it is close to 500 resources).

## 10. Legal and policy facts (for the Terms and Privacy pages; plain facts, not legal advice)
1. Some clips in VideoMK videos are made by VideoMK with a commercial generative video model (today Google's Gemini Omni through the Gemini API) from prompts VideoMK's system writes.
   They are part of VideoMK's own media library (Terms section 12 already describes it; docs/LEGAL_DRAFT_NOTES.md section 5).
2. A library clip is made from a general description (for example "a fruit market, hands choosing fruit"). The customer's prompt, script, photos, name or any personal data are
   never sent to the video provider: only the general brief is. Briefs that would name a person, brand, place or event are refused before anything is sent.
3. Library clips never intend to show a real person. Prompts ask for no faces; an automatic check rejects clips in which a person could be identified, and clips with logos, brands or text.
4. VideoMK owns or controls the rights it has in library clips and may reuse each clip in other customers' videos. A customer gets the same right to a library clip inside their
   video as to the rest of the video (commercial use on Pro and Max). No customer gets exclusivity over a library clip, and raw clips are not offered for download.
5. Purely AI-generated footage may have limited or no copyright protection in some countries (US Copyright Office, 2025); VideoMK's right to use it comes from the provider's terms.
   Google's Gemini API terms say Google does not claim ownership of generated content (docs/VIDEO_CATALOG.md section 3). Google's generative-AI indemnity names Veo on Vertex, not
   Gemini Omni through the Gemini API: there is **no confirmed indemnity** for these clips (open question in docs/VIDEO_PROVIDERS_2026-11-27.md).
6. Labelling: the on-screen credit reads "VideoMK library". Where a platform or a law asks that AI-generated footage be labelled, the Terms already say VideoMK labels "where a
   platform or the app asks for it"; the ledger of every video records which beats use a library clip, so a label can be added later without regenerating.
7. Sub-processor to list in the Privacy policy if not already there: Google (Gemini API) receives general scene descriptions only, no personal data. The API requires the request to be stored on Google's side for the delivery method used (`store=true`), so the general description and the generated clip are kept by Google under its own retention terms (not read for this work: check before launch).
8. Customers are not charged for generation and are not told when one happens. Nothing in the plan promises generated clips; the Terms should not promise them either.

## 11. What is built (branch `clips-on-demand`; not merged, not deployed)

Everything is behind the stack flag `-c clipsOnDemand=1` (or `"clipsOnDemand": true` in stages.json), which sets `CLIPS_ON_DEMAND=1` on the beat function, and the knob `enabled`.
Both are off everywhere. With the flag off the beat step makes exactly the calls it made before (tested) and the stack's template has no trace of the feature (tested).

| Part | Where | Notes |
|---|---|---|
| The knobs | `lambdas/common/clip_config.py` | one SSM parameter, 60 s cache, bad value = default, read failure = last good or defaults (generation off); the allowance formula and the price live here |
| Storage and the transaction | `lambdas/common/clip_store.py` | `AwsStore` (assets bucket `cliplib/`, usage table `clipgen:*`) and `LocalStore` (a folder); `reserve()` moves the four counters in one `TransactWriteItems` or none |
| The library | `lambdas/engine/clip_library.py` | add, Cohere embedding search (text and frame vectors), shape rules, `scope` (only `library` is ever searched), use counts per distinct video, retire, reindex, promote |
| Reusable or not | `lambdas/engine/clip_brief.py` | deterministic filters, the rubric (`BRIEF_SYSTEM`), filters on the answer, the prompt builder |
| The provider | `lambdas/engine/clip_gen.py` | interface `Provider`; `GeminiOmni` (plain HTTPS, key read at every call, never in a URL or an error text), `Mock`; errors say whether they could have been billed |
| The quality gate | `lambdas/engine/clip_gate.py` | technical checks, then 6 frames to the large vision model; fails closed |
| The flow | `lambdas/engine/clip_ondemand.py` | entitlement, decision with reason codes, demand log, lock, reservation, background generation, ledger, metrics, wait with a deadline |
| The beat step | `lambdas/engine/clips.py` (`scout_own`, `own_library`, the credit line), `lambdas/engine/handlers/beat_handler.py` (`make_clip`) | ours first; generation in parallel with the stock search; the clip is read back from the library; fallback to stock or a photo |
| Which budget pays | `lambdas/plan_gate.py` (`record`) | the video row now also carries `plan_interval`, `plan_source`, `plan_state` of a paid plan |
| Account deletion | `lambdas/common/deletion.py` | the account's allowance rows (`clipgen:acct:<user>`) are removed with the account |
| Stack | `backend_stack.py` (flag: 3 variables, 3 policy statements, **0 new resources**), `clips_obs.py` + `app.py` (`-c clipsAlarms=1`: a separate stack of 2 alarms) | |
| Admin | `scripts/clips_admin.py` | `config show/set/reset`, `list`, `report`, `sheet`, `retire`/`restore`, `reindex`, `promote` |
| Proof | `scripts/clips_on_demand_proof.py` | section 13 |

Tests (`backend/tests/test_clips_on_demand.py`, 133; `test_clips_on_demand_cdk.py`, 4; no network, provider mocked): the two switches; bad and unreadable config; the price; the
allowance formula and the invariant for every storefront; entitlement (Free, Pro, grace, admin-granted, test); own photos, decks, edits; too late, too long; 15 refusals without
a model call and 11 refusals of model answers; the prompt clauses; every gate flag, the technical checks, fail-closed; stored-before-used with full metadata and no customer
data; rejected never stored but charged; refund when the provider refused before making anything; timeout; crash containment; library hit; a retried beat; two beats on one scene;
the per-video cap; the account allowance (5 then stop); yearly; tightening; unreadable credits; the daily and monthly stops; test budgets kept apart; the low-demand rule;
12 threads racing for a budget of 2; the DynamoDB transaction (moto) and the whole flow on DynamoDB and S3; search, shapes and crops; exclusive scope; retire, reindex, use
counts; promotion without embedding or generating; the provider client (request shape, key handling, rotation, error kinds); the beat step with real ffmpeg (generated clip used,
reuse by a Free video, four fallbacks, flag off, 4K stays 720p, vertical asks 9:16); the report; the stack (no new resource, least privilege, the alarms stack).
Also run and green: `test_clips.py`, `test_four_k.py`, `test_clip_framed_4k.py`, `test_plans.py`, `test_account_deletion.py`. The full suite was NOT run (machine rule).

### To switch it on in QA (when the owner says)
1. Put the provider key in SSM: `aws ssm put-parameter --name /videomk/gemini_api_key --type SecureString --value '<key>' --profile qa --region eu-west-1` (the proof used the key in the repository's `.env`; QA has none in SSM as far as this work knows: unverified).
2. Deploy QA with `-c clipsOnDemand=1` (or add `"clipsOnDemand": true` to the qa stage). Library reuse is then on for every plan; generation is still off.
3. Optional: `clips_admin.py promote --from local:$HOME/Downloads/videomk-looks/clip_library_proof --to qa --no-dry-run` puts the three clips of the proof in QA's library without paying again.
4. `clips_admin.py config set enabled true --stage qa`. Kill switch: `config set enabled false` (live within a minute).
5. Optional alarms: `cdk deploy videomk-qa-clips-obs -c stage=qa -c clipsAlarms=1`.

### Not done
* **The 10 pilot clips were not seeded**: they are not on this machine and the document that would say where is not on this branch. The library starts with the 3 proof clips (step 3).
* Not run on Lambda: the 150 s wait, the IAM statements and the usage-table condition key (`dynamodb:LeadingKeys`) are tested in the template and with moto, not against AWS. First QA run should watch one generation end to end.
* The storefront of a plan is not recorded, so every paying account uses the EU figure (section 2.4). Purchases are not live, so today every Max account is admin-granted and draws from the test budget.
* A generation abandoned at the deadline is lost money (the API is synchronous here; its background mode is not documented well enough to build on). Measured latency was 34 to 41 s, far from the 150 s limit.
* Montage beats only ask for a generation when the whole montage fails; their segments reuse the library.
* The search index is exact comparison in the function; S3 Vectors in a small separate stack when the library passes a few thousand clips.
* The reuse and search thresholds (`search_min_score` 0.35, `reuse_min_score` 0.62, `demand_join_score` 0.80) are first values, checked on a handful of real searches in the proof, not tuned on real traffic.
* No human review step is forced: `clips_admin.py sheet` and `retire` exist; nobody is told to look.
* Exclusive media for one customer (owner's backlog item): only the `scope` field and the guards exist.
* Terms and Privacy pages: section 10 lists the facts; no page was edited. The requirements tracker was not edited on this branch (the main session owns it).

## 12. Owner decisions (confirmed 2026-11-27)
* **D1** Library clips are reusable by **every plan**; only Max triggers generation ("it comes to the library, and the library is for all"). Knob `reuse_plans`.
* **D2** The numbers of section 0 as proposed.
* **D3** The Gemini API key. The owner will rotate it: the key is read from SSM at every call and never cached or copied, so a rotation needs no code change or deploy.
* **D4** On-screen credit "Video: VideoMK library", like a stock source.
* **Backlog (not built)**: a very premium option where media is generated exclusively for one customer, never enters the shared library and is owned by them. The data model keeps room for it (`scope`, section 8).

## 13. End-to-end proof (2026-11-27, this laptop, real provider; ledger in docs/CLIPS_ON_DEMAND_LEDGER.md)

`AWS_PROFILE=qa python backend/scripts/clips_on_demand_proof.py OUT --env-file <.env>`: the real beat step, models, embeddings, Polly, stock search, provider, ffmpeg and renderer;
S3, the library and the counters are local folders; who owns each video is told to the engine by the script. Every knob at its default except `enabled`.

**Reusable or not, on 9 specific searches** (7 refused by the free filters before any model call, 2 generalised by the small model):

| Search | Decision |
|---|---|
| woman in a red coat buying mangoes in Oaxaca market on a rainy Tuesday | refused: proper noun (the place name), before any model call |
| president giving a speech at a podium | refused: news |
| coca-cola bottle on a table | refused: brand |
| Eiffel Tower at sunset | refused: proper noun |
| stock market chart on a trading screen | refused: text or graphic |
| close-up of a surgeon making an incision | refused: unsafe |
| footballer scoring the winning goal | refused: identity |
| rain falling on a quiet pond | brief: "raindrops falling on a quiet still pond surface, creating gentle ripples in soft overcast light" |
| old wooden fishing boat tied at a jetty | brief: "small wooden boat moored at a quiet jetty in calm harbour water, soft morning light" |

**Three videos, in order**

| Video | Beat (search) | What happened | On screen |
|---|---|---|---|
| A: test account, 16:9, four clip beats made in parallel | bees on lavender flowers | **generated** (8 s, 34 s to make), gate 8/10, stored, read back, checked against the narration | Video: VideoMK library |
| | baker hands kneading bread dough | **generated** (8 s, 38 s), gate 8/10, stored, read back | Video: VideoMK library |
| | golden wheat field swaying in the wind | refused: `cap_video` (the video already had its 2); the stock clip found meanwhile was used | Video: ulleo / Pixabay |
| | steam rising from a cup of coffee | refused: `low_demand` (58 % of the day's $2 test budget was reserved, so a scene needs two askers); stock | Video: Life-Of-Vids / Pixabay |
| B: a **Free** account, 16:9 | kneading dough by hand | **library reuse** of the dough clip: no generation, no stock search | Video: VideoMK library |
| | wheat field at sunset | not in the library, Free never generates: stock | Video: JoshuaWoroniecki / Pixabay |
| C: second test account, **9:16** | steam rising from coffee cup | second asker of that scene: **generated in 9:16** (8 s, 38 s), gate 8/10 | Video: VideoMK library |
| | bees on lavender flowers | **library reuse** of the 16:9 bees clip, centre-cropped (the gate had marked it centre-safe; the 3-frame check passed on the crop) | Video: VideoMK library |

* **Gate**: 3 of 3 passed (score 8, no flag). Three clips are no rejection rate; the 35 % plan stands until real traffic says otherwise. I looked at six frames of each: clean, no text, no faces; the dough clip shows an apron and forearms as well as hands; the coffee steam is prettier than real steam.
* **Money**: charged to the test budget $1.743 (3 x $0.581); the provider's own token counts come to $0.563 to $0.566 a clip at list price, so the charge covers the provider, the gate ($0.005 to $0.010 measured) and the checks. Day counter $1.743 of $2.00: a fourth generation would have been a budget stop.
* **Time**: video A's beat step took 44.7 s with two generations in it and 10.4 s when the same beats were made again from the library: **the customer's video was about 34 s later**, against a worst-case limit of about 3 minutes.
* **Report** (`clips_admin.py report --store local:...`): 3 generations, 3 kept, spend $1.74, $0.58 per kept clip, latency p50 40.4 s and p95 41.4 s, cap hits `video: 2`, decisions `generated 3, cap_video 2, low_demand 2`, used `generated 3, library 4`, dough and bees each used by 2 distinct videos, the wheat brief listed as asked for without a clip.
* **Promotion**: the three clips were copied to a second store with `promote` (3 copied; a second run: 3 already there); nothing was generated or embedded.
* **The video** (30.4 s, narrated, captions on): `~/Downloads/videomk-looks/web/clipgen_video_from_field_to_breakfast.mp4`, with the three clips, the vertical crop and the library sheet beside it (`clipgen_*`, captions in `captions_clipgen.json`).
* Found and fixed by the proof: the provider requires `store=true` for URI delivery; the provider bills about 700 to 1,200 "thought" tokens a call (overhead raised from $0.012 to $0.025).
* What the proof did not exercise: DynamoDB and S3 (covered by tests with moto), a paying account's formula (tests), a gate rejection or a timeout on real footage (tests), 4K (tests).

## Part A. Images on demand (2026-11-28)

Owner: "I am very annoyed by the credits that we have to put at the top of the video for the images. So I want to start creating my own image library... make it part of the
library, make it our own image." Built on the existing catalog (docs/IMAGE_CATALOG.md: 98 images on QA, OpenAI model, check, Cohere vectors in S3 Vectors, promotion).

### A1. Cost
* **Price list** (https://developers.openai.com/api/docs/pricing, read 2026-11-27; the page shows no date): `gpt-image-2.6-flare` image output **$30 per 1M tokens**, text input $5, image
  input $8; batch half. No per-image table. A 2048x1152 high image is 1,413 output tokens = **$0.0424**.
* **The catalog's own ledger** (`docs/image_catalog/spend_log.jsonl`): 164 generations, $7.255, **$0.0442 each**; check $0.0003; embedding $0.0005.
* **This proof**: three generations, $0.04423 to $0.04426 each by the provider's token counts. **Charged to the budgets: $0.05** (`image_price_usd`).
* **Rejections**: batch 1 kept 98 of 154 (36 % rejected, mostly "does not survive the 9:16 or 1:1 crop"), so about **$0.07 to $0.08 per kept image**. The proof: 2 kept of 3 (the third: bright table edge under the captions).

### A2. Limits (confirmed 2026-11-28)
Account share $1.00 of the one monthly allowance (about 20 generations, 13 kept); a yearly account's whole $0.35 may go to images (7). 4 per video. Platform $3 a day and $40 a month;
test accounts $1 each from $1 a day and $10 a month. All knobs (`image_*`).

### A3. The flow (`engine/image_ondemand.py`, hooked into `beat_handler.make_photo`)
1. The person's own photo and a pick made in the editor are untouched. The catalog is searched first, as before (`catalog_pick.try_catalog`): a hit is used, no credit.
2. No hit: entitled (Max or test), switches on, not an edit, not own photos or a deck. The search is made general by the same step as clips (`clip_brief`, image rubric): names,
   brands, places, text, news and faces are refused. The brief is searched in the catalog again (a general wording often finds what the specific one missed).
3. Reserve $0.05 on the five counters; generate **in the background while the stock search runs** (limit 75 s; measured 7 to 10 s).
4. The catalog's own check (`common/catalog_make.py`, shared with the batch tool: adherence and quality >= 7, no text, logo, real person, anatomy or warping problem, survives the
   centred 9:16 and 1:1 crops, calm bottom quarter, editorial style; fails closed). A duplicate of a picture we already own (image vector >= 0.92) is not stored: the existing one is used.
5. **Marked as ours** (A4, layer a), then stored in the catalog: original, preview, thumbnail, vector, and the row last (`on_demand`, `scope: library`, `marked`, `watermark: pending`).
6. Only then used: read back from the catalog, checked against the narration by the catalog's verifier, cut to the video's shape. **No on-screen credit.** Otherwise the stock photo found meanwhile, credited as its terms ask.

### A4. Ownership marking: three layers, and what each survives
| Layer | What it is | Survives | Does not survive | Status |
|---|---|---|---|---|
| (a) Embedded metadata | EXIF Artist and Copyright; XMP `dc:creator` and `xmpRights:Owner` = Agilegency Ltd, `dc:rights`, `photoshop:Credit` = VideoMK, contact hello@videomk.com, IPTC `DigitalSourceType` = `trainedAlgorithmicMedia` (the standard AI disclosure), `videomk:AssetId`. Written without touching a pixel (`common/ownership.py`) | copying the file, most desktop tools | anything that re-encodes or strips: social platforms, screenshots, and **our own renderer** (the picture becomes video frames). It marks the library FILE, not a customer's video | built; verified at every ingest and by tests; backfill script `scripts/ownership_admin.py` |
| (b) C2PA Content Credentials | a signed provenance manifest | viewers that read C2PA | re-encoding without re-signing | **not now** (below) |
| (c) Invisible watermark | Adobe TrustMark (variant Q, BCH_5) carrying the first 60 bits of the asset id in the pixels | measured below: JPEG re-save, resize, Ken Burns, captions drawn over it, **our H.264 render at 1080p and a 720p web copy, a screenshot of the video** | **the centre crop to 9:16** (a vertical video shows a third of the picture's width) | chosen; applied offline by the same script (needs PyTorch: it cannot run inside the engine's functions) |

**(b) C2PA, measured**: the catalog's originals (the API's JPEG output) carry **no** C2PA manifest and no metadata at all (5 files inspected: only the JFIF header). The same API's **PNG**
output does carry one (a 23,660-byte `caBX` chunk on a probe image). To keep OpenAI's credential we would have to store PNGs (about six times larger) and never touch them; our own
metadata, the watermark or a conversion would each break its hash unless we re-sign. Adding OUR signed assertion needs the C2PA SDK and a signing certificate from a certificate
authority on the C2PA trust list (price not checked: unverified), and it would still be lost in the rendered video. **Recommendation: not worth it now.** Revisit if a platform starts demanding it.

**(c) Invisible watermark, measured on 5 catalog images** (2048x1152; the id embedded, then each thing our pipeline does, then read back; exact id recovered in N of 5):

| | TrustMark Q (MIT) | invisible-watermark `dwtDctSvd` (MIT) | invisible-watermark `dwtDct` (MIT) |
|---|---|---|---|
| PSNR against the original | **42.5 to 47.9 dB** | 41.0 to 42.0 | 41.0 to 41.8 |
| SSIM | **0.9935 to 0.9983** | 0.975 to 0.985 | 0.951 to 0.962 |
| By eye at 100 % (sand, the hardest of the five) | no difference seen | not looked at (fails below) | not looked at |
| Stored as JPEG q92 | **5/5** | 5/5 | 0/5 |
| JPEG re-save q80 | **5/5** | 0/5 | 0/5 |
| Resize to 1920x1080 + JPEG q90 (our working copy) | **5/5** | 0/5 | 0/5 |
| Ken Burns zoom 1.08 | **5/5** | 0/5 | 0/5 |
| Captions and scrim drawn over the bottom | **5/5** | 0/5 | 0/5 |
| H.264 1080p crf 20 with a slow zoom (our render), one frame | **5/5** | 0/5 | 0/5 |
| H.264 720p crf 28 (a web copy), one frame | **5/5** | 0/5 | 0/5 |
| Screenshot (1280x720, JPEG q75) | **5/5** | 0/5 | 0/5 |
| Phone screenshot of the 720p video (scaled, JPEG q80) | **5/5** | 0/5 | 0/5 |
| Centre crop to 9:16 (and its H.264) | **0/5** | 0/5 | 0/5 |
| False read on the unmarked originals | 0/5 | 0/5 | 0/5 |

Licences read in the installed packages: TrustMark 0.9.2 `LICENSE` = MIT (Copyright 2023 Adobe); invisible-watermark 0.2.0 = MIT. The licence of TrustMark's model files (fetched from Adobe on first use, 143 MB) was not checked separately: unverified.
A second mark in the centre column was tried so the vertical crop would also carry the id: with the whole picture marked last, the crop read 0 of 5; with the column marked last, the crop read 5 of 5 but the whole picture only 3 of 5. Not adopted.
**Recommendation: TrustMark on every library image; it survives our landscape and square pipeline including video encoding and screenshots. Say plainly: it does NOT prove ownership of a picture seen in a VERTICAL video, and it is not a legal instrument. The proof of ownership is, in this order: the library record (asset id, prompt, date, cost), the provider's generation receipt, the metadata in our file, and the watermark where it can be read.**
On-demand images get the metadata at once and the watermark later (`watermark: pending`, finished by `ownership_admin.py mark --watermark`), so the first video that uses a new image has it unwatermarked.

**Backfill of the 98 QA images**: `ownership_admin.py mark --store qa --watermark` (dry run: 98 would be marked, 0 refused). **Run for real on 2 images** and verified from the bucket (metadata reads back, watermark reads back, the row carries the new file hash, the picture decodes at 2048x1152); **the run on the remaining 96 was stopped by this session's permission system**, so it is one command for the owner: `AWS_PROFILE=qa python backend/scripts/ownership_admin.py mark --store qa --watermark --no-dry-run` (in an environment with `pip install trustmark boto3`). The bucket is versioned; ids do not change; `catalog_promote.py` now checks a marked file against the hash recorded on its row.

### A5. Credits on screen
* **Our own images: no on-screen credit, and none in the description.** Confirmed in code and by test: a catalog image is returned with `credit: ""` and `assets.credits_block` leaves the source `videomk-library` out. Library clips show "Video: VideoMK library", as the owner agreed.
* **What each stock source actually requires** (the sources' own pages, read 2026-11-27 through a tool that returns excerpts: quotes are fragments):

| Source | Attribution | What the terms say | Where it may go |
|---|---|---|---|
| Unsplash, plain licence | not required | "Even though attribution isn't required, Unsplash photographers appreciate it" (unsplash.com/license) | anywhere or nowhere |
| **Unsplash through the API (what the engine uses)** | **required by contract** | "each time you or your Developer App displays an Image, your Developer App must attribute Unsplash, the Unsplash photographer", with a link to the profile; "you must directly use or embed the related image URLs returned by the API" (unsplash.com/api-terms, sections 9 and 6); links with utm parameters; a download ping on use | tied to each display; nothing in the terms covers a rendered video or approves a description-only credit |
| Openverse / CC BY 4.0 (and BY-SA) | required | creator, licence notice and link, source "to the extent reasonably practicable", changes indicated; "in any reasonable manner based on the medium, means, and context" (legal code 3(a)(2)); CC's practice page: video "can be attributed within the audio/video, and in the description text", "provide a credit list" | in the video and/or the description, or a credits list. BY-SA also puts share-alike on the video: the engine already excludes it |
| CC0 / Public Domain Mark | not required | "you are not required to give attribution at all" (CC FAQ) | - |
| Pixabay | not required by the licence; the API asks | "Use Content without having to attribute the author"; API: "show your users where the images and videos are from, whenever search results are displayed" | the request is about search results (the editor's picker), not the finished video |
| Pexels (no key today) | not required by the licence; the API asks | "Attribution is not required."; API: "show a prominent link to Pexels", "Always credit our photographers when possible" | unspecified; a credits list satisfies "when possible" |
| Wikimedia Commons | per file: CC BY as above; public domain recommended only | reusers "can choose format of the credit line" (a Commons essay, not policy) | a credits list; a collective list is not explicitly approved: unverified |
| NASA | acknowledgement expected | "NASA should be acknowledged as the source of the material"; no endorsement implied | unspecified; a credits list covers it |

* **Built 2026-11-27 (owner: "2 ok"): the other sources are ranked ahead of Unsplash, which is now the last resort (part E).** No credit was removed or changed.
* **Recommendation (the rest is still not changed in the engine: a licence decision is the owner's)**: (1) keep own library first, so credits disappear as it grows; (2) move the credit of **Pixabay, Pexels, CC0 and public-domain** media off the frame into the description and Info sheet, where the list already is: their terms do not ask for more; (3) **CC BY and NASA**: the description list is enough by CC's own guidance; an end card is the cautious extra; (4) **Unsplash is the one that needs the on-frame line**: its API terms tie the credit to each display and nothing approves a description-only credit for video, so either keep the small on-frame credit for Unsplash photos only, or ask Unsplash in writing, or prefer the other sources and our own images ahead of Unsplash. Note also that the API terms ask to hotlink their URLs, which a rendered video cannot do: that question exists today, with or without this change.

### A6. Proof (2026-11-28, laptop, real OpenAI calls, QA models, local catalog)
| Video | Search | Result |
|---|---|---|
| test account | wooden beehives in a meadow | brief "row of wooden beehive boxes standing among tall wildflowers in a sunlit summer meadow"; generated in 9.7 s, check 8/10, marked, stored, used; **credit: none** |
| test account | president signing a law | refused by the filter (news), no model call |
| test account | jar of honey on a table | generated in 7.2 s, **rejected** (bright surface under the captions), not stored, charged |
| second test account | empty classroom with wooden desks | generated in 9.6 s, 8/10, stored, used; credit none |
| Free account | bee hives in a field / school classroom / city traffic at night | reused the beehives (score 0.57) and the classroom (0.46), no generation; nothing for traffic (0.07): stock |
Both stored files read back with the full ownership metadata. I looked at both: natural editorial pictures, no text, no people. Copies: `~/Downloads/videomk-looks/web/ondemand_image_*.jpg`.

### A7. Not done (images)
* Not run on Lambda or against the QA catalog (the proof used a local catalog); the three write statements for the beat function exist under the flag and are untested on AWS.
* The watermark is applied offline; nothing schedules it. Only 2 of QA's 98 images are marked so far (above).
* 4:5 and 1:1 use the catalog's centre crop; the check requires the subject to survive it.
* The catalog's demand log is not yet fed by on-demand decisions (the on-demand ledger has them).

## Part B. Whiteboard sketch objects on demand (2026-11-28)

**The owner's question: can a missing object be made on the go? Yes, measured.**

| Call | Asked | Whole call (sheet, cut, trace, gate and naming) | Accepted |
|---|---|---|---|
| 1 | violin | 14.9 s | 0 of 1 (the gate: "neck is drawn like a pencil") |
| 2 | honeycomb, beehive, skateboard, violin, kite, teapot | **10.3 s** | **6 of 6** |
| 3 | igloo, accordion, sundial, trowel | **11.7 s** | 4 of 4 |
10 of 11 accepted (the library build: 344 of 372 on the first try). $0.0375 a sheet by the provider's token counts, $0.006 to $0.007 a gate call; charged $0.04 + $0.007 an object. All far inside the 30 s limit.
What the boards got instead before: the honeycomb and the beehive were both drawn as a **bee**, the skateboard as a scooter, the kite as a **helicopter**, the teapot as a pot, the igloo as an iceberg, the sundial as an hourglass, the trowel as a broom; the violin and the accordion were written as words. After: the ten real drawings (`~/Downloads/videomk-looks/web/ondemand_objects_sheet.jpg`; I looked at it: clean, on style, sensibly coloured).

### B1. The finding that changed the design
The usual miss is NOT a written label. The library answers a missing name **by meaning** with its closest drawing (floor 0.30), and docs/WHITEBOARD_PHASE_1A says correct and wrong matches overlap
(0.31 and up against 0.16 to 0.37). That is how a honeycomb became a cheese on QA. So with the flag on, a drawing resolved by meaning only is remembered on the item (`asked`, `match`), and one
below `object_sure_score` (0.55) counts as missing together with the boxed labels. Without the flag the plan is byte for byte what it was.

### B2. The flow (`engine/object_ondemand.py`, called by `plan_handler` after the director has settled the boards)
1. Collect the plan's missing drawings (distinct, at most 6). Names that can never be a general drawing (brand, flag, person, text) are left alone.
2. Entitled (Max or test), switches on, not an edit. Reserve `$0.04 + $0.007 x n` on the five counters. **One call per video.**
3. ONE image call: a sheet of the missing objects in the house style (the builder's own prompt), cut, traced to a pen path, and each object shown to the library's gate, which also names it
   in English and Spanish, colours its areas and orders its strokes (the part-naming call). The builder's own code is used, not a copy (`scripts/whiteboard_proto/lib_build.py`).
4. Accepted drawings go into OUR library first: the package under `w/<id>.json` in the catalog bucket (where the renderer reads every drawing), an index row with names, synonyms and the Cohere
   vector (so later plans find it by name or by meaning, in both languages; `load_dynamic` reads them at the start of every plan). An existing id is never overwritten.
5. Only then the boards: the new drawing replaces the stand-in or the label. A rejected one keeps what it had.
6. The plan step waits at most `object_timeout_s` (30 s). Late or failed: nothing changes, the plan goes on.

### B3. Limits and who
Cost is cents, so the limits are about latency and quality: 1 call a video (up to 6 drawings), 30 s; account share $0.15 a month; platform $1 a day and $10 a month; test $0.30 an account from $0.50 a day and $5 a month.
**Max only, as the owner said** (knob `object_plans`). My recommendation stays: open it to Pro once a week of rejection data exists; a call is under 1 % of Pro's margin. Opening it needs Pro's own "kept" figures in the allowance formula, which today knows Max only: not built.

### B4. What going live on Lambda needs (built 2026-11-27 as option 1: see part D; not deployed)
The tracer uses **scipy** (`ndimage` and `interpolate`) and **vtracer**, and the engine's layer has neither. The layer is 148 MB; scipy is about 97 MB installed; the limit for a function with
its layers is 250 MB, so scipy does not simply fit. In the engine's functions `fill` therefore answers `no_tracer`, spends nothing and leaves the plan alone (tested). Two ways to go live:
1. **A small tracer function of its own** (a container image, in a separate small stack; the plan step invokes it with the 30 s limit). Clean, no risk to the engine layer. My recommendation.
2. A trimmed scipy (only `ndimage` and `interpolate`) plus vtracer in the engine layer: no new resource, but it must be built and proven on Lambda.
Either way the tracing code (`trace.py`, `vectorize.py`, the cutter and gate of `lib_build.py`) should move from `scripts/whiteboard_proto/` into `lambdas/`; I left it where it is because the whiteboard work is still changing those files.
Until then the same result can be had after the video: `fill` works on a laptop today, so a nightly run over the day's missing names would stock the library for the next video.

### B5. Not done (objects)
* Not running on Lambda yet: the tracer function is built and tested but not deployed (part D). The plan function's rights and variables exist under the flag.
* The proof ran `fill` on boards built by the real `_sanitize`, not inside a full plan step, and no board was rendered with the new drawings (the packages are the builder's own format, which the renderer already draws).
* The boards were laid out and scored before the swap; a drawing of a very different shape than its stand-in is laid out again at render time but the self-check does not run again.
* `object_sure_score` 0.55 is a first value; all eight wrong stand-ins in the proof were under it, and no correct match was tested against it.

## Tests added for parts A and B
`backend/tests/test_library_on_demand.py` (21): ownership metadata (lossless, replaced not duplicated, the backfill, promotion of marked files), images (stored and marked before use, no credit, every
gate flag, who may, the switches, catalog hit, duplicate, 4 a video, the type share, day stop, test budget, yearly gets images but no clip, **clips and images on one account total**,
provider failures and timeout, the OpenAI client, the photo step with fallback and with the flag off), objects (made, stored, drawn; rejected keeps its label; one call a video; who may; no tracer; slow or failing call; never overwrite; the meaning-match rule).
With the clip tests and the neighbours: see the run at the end of the work. The full suite was not run.


## Part C. Safety of everything we generate and own (2026-11-27, tracker R160)

Owner: "We must ensure images are safe, on the safe side, I don't want to generate and own images that are risky, controversial, etc."

### C1. The policy (ONE module: `backend/lambdas/common/media_policy.py`, version 2026-11-27)
A library asset is reused in many videos about topics nobody can foresee, so it must be harmless under ANY narration. **Refused, for clips, images and sketch objects alike:**

| Code | What |
|---|---|
| `politics` | politicians, parties, elections, voting, governments, parliaments, campaigns, protests, riots, activism, propaganda, political symbols |
| `religion` | places of worship, clergy, prayer, rituals, religious symbols, clothing, texts, figures and holidays of any faith |
| `war_weapons` | armed conflict, soldiers, armies, military vehicles, guns, blades shown as weapons, bombs, explosives, ammunition |
| `violence` | fighting, attacks, abuse, threats, killing, torture, kidnapping, robbery, arrests, prisons, bullying |
| `injury_medical` | blood, wounds, surgery, needles and injections, vaccines, exposed or realistic organs, broken bones, burns, visible suffering |
| `sexual` | nudity or partial nudity, underwear or swimwear as the subject, kissing, seductive poses, anything erotic |
| `drugs_alcohol_tobacco` | narcotics and their use, pills as drugs, beer, wine, spirits, bars and drinking, cigarettes, cigars, pipes, vaping |
| `gambling` | casinos, betting, slot machines, roulette, poker, lotteries |
| `tragedy_disaster` | natural disasters, accidents, crashes, destructive fires, wreckage, death, funerals, graves, grief, poverty and suffering |
| `children` | babies, toddlers, children or teenagers as the main subject (toys or an empty classroom are fine; a child is not) |
| `flags_maps` | any country's flag, national emblem or anthem scene, any map, a globe with country outlines, borders, checkpoints, disputed territory |
| `stereotypes` | people shown as typical of a nationality, ethnicity, race, religion, gender, age, class, disability or profession; ethnic costume as shorthand for a people |
| `real_people` | any named, famous or recognisable person, any real face clear enough to be recognised, portraits, look-alikes |
| `brands_ip` | brands, logos, packaging, recognisable product design, mascots, film, game, comic or cartoon characters, team kits, franchises |
| `hate` | nazi, supremacist or extremist symbols, slurs, racist caricature, harassment of a group |
| `self_harm` | suicide, self-injury, eating disorders, overdose, nooses |
| `frightening` | horror, monsters, skulls and skeletons, ghosts, screaming, menace, disgust, shocking or disturbing scenes |

**When unsure, refuse.** The video then uses stock media (clips, images) or keeps its written label (sketch objects): the fallbacks that already existed. `python backend/scripts/library_safety.py policy` prints the policy as the models read it.

### C2. The layers, cheapest first, and where each one sits
| Layer | Clips | Images | Sketch objects | Cost |
|---|---|---|---|---|
| 1. Word lists, English and Spanish, accents and case ignored (`text_reason`) on the director's own wording | `clip_brief.pre_filter` | the same | `object_ondemand.missing` | free |
| 2. The policy inside the model rubric (`TEXT_RUBRIC`): the answer must say `"policy": "none"` | the brief call that already existed | the same | `judge_names`: ONE small-model call a video, which also returns the plain English name | none extra; about $0.0003 a video for objects |
| 3. Word lists again, on the English brief or name the model wrote, plus "plain English only" | `clip_brief.post_filter` | the same | inside `judge_names` | free |
| 4. Provider's own moderation of the exact prompt, BEFORE paying | Gemini Omni filters the prompt itself (a blocked prompt is not billed and nothing is stored) | OpenAI moderation endpoint on the prompt; refused or unavailable = nothing generated, the reservation goes back | the same, on the sheet's prompt (`object_maker.sheet`) | free |
| 5. The provider's own filter during generation | Gemini Omni: "applies content safety filters to both input prompts and generated video" | `moderation: "auto"` sent explicitly | the same | free |
| 6. After generation: the policy inside the vision check (`VISION_RUBRIC`), answer must say `"policy": "none"` | the 6-frame gate (`clip_gate.judge`) | the catalog's check (`catalog_make.judge`), which the offline batch tool shares | `vision_check` on every finished drawing (one small-model call each, in parallel) | none extra for clips and images; about $0.0002 a drawing |
| 7. Provider's own moderation of the result | none exists for video outside the generation call | OpenAI moderation endpoint on the picture | on the whole sheet | free |

Every layer **fails closed**: a missing `"policy"` field, an unknown word in it, an unreadable answer, an error, a moderation service that does not answer, a drawing without a picture to judge, an answer that is not sure: all are refusals. **Rejected media is never stored**: only a ledger row with the reason (`policy:<code>`, `moderation:<category>`) and the cost. A refusal before the provider is paid gives the reservation back (`policy_refused`); one after it is charged like any rejected generation.

**Provider moderation, as read on the providers' own pages on 2026-11-27** (not from memory):
* OpenAI (images and sketch sheets): `POST /v1/moderations`, model `omni-moderation-latest`, "The moderation endpoint is free to use"; input is text and/or pictures (a base64 data URL is accepted); pictures are scored for sexual, violence, violence/graphic and the self-harm categories only (hate, harassment, illicit and sexual/minors are text only), which is why the prompt is checked as text as well. We refuse on the provider's own `flagged` and, stricter, on any category score at or above 0.2 (`MODERATION_MAX_SCORE`). The image generation parameter `moderation` is `"auto"` (default) or `"low"` ("less restrictive"); we send `"auto"` explicitly. Source: developers.openai.com/api/docs/guides/moderation and /api/reference/resources/images.
* Google Gemini Omni (clips): the Omni page says "Omni applies content safety filters to both input prompts and generated video" and "Prompts that violate usage policies are blocked"; it documents no safety parameter for video and no separate moderation endpoint. The Interactions API's safety page describes adjustable thresholds (`safety_settings`, strictest `block_low_and_above`, default off for recent text models) but does not mention the video model, so **no threshold is sent for clips**: an undocumented parameter could break every generation. A blocked request answers HTTP 400 with code `safety`, `jailbreak`, `prohibited_content` or `blocklist`; the client treats all four as "blocked, not billed". Source: aistudio.google.com/docs/omni and /docs/safety-settings. Not verified with a real blocked call.

### C3. Languages
The word lists are **English and Spanish** (every wording is checked against both, whatever language it claims to be). Seven more video languages are coming (French, German, Italian, Brazilian Portuguese, Dutch, Polish, Finnish). They are handled by construction, not by seven more word lists:
* **The generator is only ever sent English that we checked.** For clips and images that is the general brief the model writes ("Write the brief in English whatever the language of the search"); a brief with any letter outside plain English is refused (`english_only`), and the English word lists then read it. For sketch objects, `judge_names` turns each name into its plain English name, and only that name reaches the generator (a German "geige" is drawn from "violin"; the board keeps its own wording).
* The director's own wording, in whatever language, is read by the model rubric, which is told to apply the policy "to the meaning, in whatever language the wording is written".
* So a language without a word list is covered by the rubric on the way in and by the English lists on what is actually generated. What it does not get is the free refusal before the model call: a French wording costs one small-model call (about $0.0002) to be refused. Adding a language's words to `CATEGORIES` is a one-line change per category.
* Honest limit: a brief written in Spanish without accents would pass `english_only` (it only looks at the letters); the Spanish word lists still read it, and the rubric asks for English.

### C4. The audit of what the library already holds (read only)
`python backend/scripts/library_safety.py audit --store qa [--media images,objects,clips] [--vision none|small|large] [--ids a,b] [--json out.json]`. Word lists on every title, subject and name; the policy's vision check on every picture; the provider's moderation on images. Verdicts: **remove** = a check of the picture itself named a category or the provider's moderation refused it; **review** = only words matched, or a check was unsure or could not run; **ok**. It never changes anything (tested: not one byte of either store differs after a run).

**Run on QA, 2026-11-27** (`AWS_PROFILE=qa`, read only; full rows in `docs/clips_on_demand/safety_audit_qa_2026-11-27.json`; model calls $0.57; nothing was changed or deleted):

| | Checked | ok | review | remove (the checker's word) |
|---|---|---|---|---|
| Catalog images (large vision model, and OpenAI moderation: 98 of 98 clean) | 98 | 87 | 6 | 5 |
| Sketch objects, the 354 bundled drawings (small vision model) | 354 | 338 | 2 | 14 |
| Library clips | 0 | | | QA holds none (not deployed) |

The checker is told "when unsure, it does" and it behaves so. I looked at the 11 images myself (a contact sheet): none is offensive; the question for each is only whether it sits inside the owner's list. **What I recommend, in two tiers:**

*Images: remove (inside the written list):*
* `c02e27543388a36b3bf1ae927c2b643793ec9e2f636818a92826bbc810f7bfe9` "Compass and old map": an old map with border-like lines fills the frame (maps and borders).
* `486c23bcb869d44b4f1d2a432ee3d64a9bc528202021365ca66857ee14584a8f` "Old stone ruins with columns": it is a Greek temple (a place of worship, and it reads as a specific landmark).

*Images: the owner's call (the checker refused; a reasonable person could keep them):*
* `1714b43d4ea432270fd83c40ec7e51990529538322985071ef39b9f9e34cd201` "Person meditating at sunrise": a lotus-pose silhouette can read as a spiritual practice.
* `c3e43c811d59799c9d9d349e2ce0d3837ca0f3108cd54675dab7ac4f71ea2b15` "Single candle in the dark": reads as vigil, mourning or prayer under the wrong narration.
* `eec6aae2d1e39b725c7df32f7b37b6c8c0addd08e66d1243d83e5a2fa5ae39ee` "Robot hand and human hand": echoes Michelangelo's Creation of Adam.

*Images: reviewed, keep (the checker was only "unsure"; I see nothing)*: `1a069c13...` cup of coffee (the word "logos" is in its own negative prompt), `1c8794fc...` open book (blurred, unreadable text), `1e490d4d...` hand holding a blank black phone, `94711f87...` train (a livery, no logo), `a54320b5...` closed plain laptop, `e1393324...` chess pieces (the king's cross).

*Sketch objects: remove (inside the written list):* `baby`, `child`, `family` (children as the subject), `church` (religion; the drawing has a cross), `map` (maps), `syringe` (needles and injections), `explosion` (explosions), `leader` (a person holding a flag).
*Sketch objects: the owner's call:* `pill` and `medicine_bottle` (medicine, which the strict reading files under drugs), `flag` and `mountain_flag` (a plain flag, no country), `compass_rose` (a map element), `crown` (monarchy), `old_person` (a person with a cane: age), `peace_dove` (a peace symbol: activism, also religious).
The bundled drawings are named in `backend/lambdas/engine/assets/whiteboard/library_index.json`: removing one for good is deleting its entry there and deploying; the takedown below takes it out of service before that.

Honest limits of the audit: the small model's answers vary between runs (two drawings refused on the second look passed on the third); the first pass cut 21 answers short because the answer limit was too low for a model that thinks before answering (fixed: the limit is now 1,000 tokens, and a cut answer was always a refusal, never a pass); the image audit used one large-model call per image, not several; the vector cartoon backgrounds and characters (`vector_catalog_*`, `vector_character_*`) are other libraries and were not audited; prod was not audited.

### C5. Takedown: one asset out of the library at once
`python backend/scripts/library_safety.py takedown image|clip|object <id> --store <store> --reason "why" [--no-dry-run]` (`restore` undoes it; `taken` lists the record). Dry run by default; production asks to type `prod`. Code: `backend/lambdas/common/takedown.py`. In this order, so a failure half-way still leaves the asset out of service:
1. **The row first.** Image: `review_status` becomes `taken_down` (every use reads the row and requires `approved`: the next video cannot get it). Clip and on-demand drawing: `status` becomes `taken_down` (search loads only `active` rows; the clip's metadata document says the same, so a rebuilt index and a promotion keep it out).
2. **Out of search.** The image's vector is removed from the index (a copy is kept in quarantine so it can be restored).
3. **The files go to quarantine, copied first, then deleted at the original key**: `quarantine/o|p|t/<id>.jpg` and `quarantine/w/<id>.json` in the catalog bucket (which is versioned: the original key also keeps its versions), `cliplib/q/v|p/<id>` for clips (**the assets bucket is NOT versioned**, checked on QA: for a clip the quarantine copy is the only one). Nothing is hard-deleted.
4. A takedown record (when, why, what moved) under `clipgen:takedown` in the usage table.

How immediate, honestly: an image is immediate (the row is read at every use). A clip leaves search for every new function instance at once and for a warm one within 2 minutes (its row cache); a warm instance that still holds the row can no longer fetch the file, so the beat falls back to stock. A drawing made on demand is not loaded by the next plan step. **A bundled drawing** is put on the takedown list, which the plan step reads only when library media on demand is deployed (`CLIPS_ON_DEMAND`); with the flag off (QA and prod today) the package's removal stops new render instances from loading it (the board then writes its label) but a warm instance may keep its cached copy until it is recycled, so the lasting removal is its entry in `library_index.json` plus a deploy.
Built and tested against local stores only. **Not run against QA or prod.** The engine's functions have no right to `quarantine/`; the command runs with the operator's own credentials.

### C6. What is not done (safety)
* The policy's wording and word lists are a first version written by the builder; the owner should read the table in C1. Loosening or tightening is editing one tuple.
* Deliberately NOT refused by the word lists (the rubric decides): kitchen knives, dice and playing cards, ambulances, medicine in general, a globe without borders.
* The offline sketch-library builder (`lib_build.py`) and the vector libraries do not call the policy; the image batch tool does (it shares the check).
* Clips have no second, independent moderation of the finished frames (the provider documents none). OpenAI's free moderation could read the six frames if the owner accepts sending our generated frames to a second provider: not built.
* No real refusal by either provider's moderation was provoked (it would mean sending a bad prompt on purpose); the clients are tested against stand-ins of the documented answers.
* The kill switches are the existing ones: `master_enabled` and the per-type switches (`clips_admin.py config set master_enabled false`, live within a minute).

## Part D. The tracer function: sketch objects on Lambda (2026-11-27, tracker R153; built, tested, NOT deployed)

**Why its own stack**: the maker needs scipy and vtracer; the engine layer is 148 MB and may not grow by about 100 MB (250 MB limit); the main stack `videomk-<stage>` is near 500 resources.
**What it is**: `videomk-<stage>-wb-tracer`, **5 resources**: one zip function (Python 3.12, 3008 MB, 60 s), its own layer `tracer_deps` (numpy, scipy, Pillow, vtracer, resvg: **161 MB unpacked, 54 MB zipped**, all manylinux wheels, built by the same `build_layer.sh`, **no Docker and no container registry**), a role, its policy, a log group (30 days). Its only two rights: `bedrock:InvokeModel` (the builder's gate) and `ssm:GetParameter` on `/videomk/openai_api_key` (read at every call, never kept). It has no table, no bucket, no account or video data.
**What it does** (`backend/tracer/handler.py` -> `lambdas/common/object_maker.py`, the library builder's own code from `scripts/whiteboard_proto`, bundled at synth time, not a copy): plain English names in; moderation of the prompt; ONE sheet from the image provider; moderation of the sheet; cut, trace, the builder's gate (which names, colours and orders); the accepted packages and a JPEG of each drawing out. The plan step then runs the policy's vision check on each drawing and stores the accepted ones in OUR library itself: the function writes nothing.
**How the engine calls it** (`object_ondemand.tracer_maker`): one synchronous `lambda:Invoke`, no retry, read timeout = the plan step's own limit (`object_timeout_s`, 30 s) + 2 s, and only after every existing condition passed (the flag, `object_enabled`, `master_enabled`, entitlement, not an edit, names cleared by the policy, money reserved). **Function missing, not allowed, throttled, slow, failing or answering nonsense: the boards keep exactly what they had** (tested for eight failure kinds). When the failure happened before the image provider could be paid (function missing, access denied, no key, prompt refused) the reservation is given back; otherwise it stays, like any failed generation.

**Added to the main stack, exactly** (only under the existing `clipsOnDemand` flag; **0 resources**): on the plan function, one environment variable `OBJECT_TRACER_FUNCTION=videomk-<stage>-wb-tracer` and one IAM statement `lambda:InvokeFunction` on `arn:aws:lambda:<region>:<account>:function:videomk-<stage>-wb-tracer`. No cross-stack reference: the two stacks share only that name, so either deploys or is deleted without the other.

**Deploy on QA** (not run; the main session deploys):
```
cd backend
layers/build_layer.sh tracer_deps                      # once, and when layers/tracer_deps/requirements.txt changes
AWS_PROFILE=qa npx --yes aws-cdk@latest deploy videomk-qa-wb-tracer -c stage=qa -c objectTracer=1 --require-approval never
# smoke test: expects {"ok": true, "tracer": true}
AWS_PROFILE=qa aws lambda invoke --region eu-west-1 --function-name videomk-qa-wb-tracer --cli-binary-format raw-in-base64-out --payload '{"action":"ping"}' /dev/stdout
```
If the QA engine is deployed with `-c planModelId=<id>`, pass the same to the tracer stack (it is the gate's model). Then, when the owner says: the main stack with `-c clipsOnDemand=1` (the variable and the statement above, with the rest of the flag) and `clips_admin.py config set object_enabled true --stage qa`. Remove: `cdk destroy videomk-qa-wb-tracer -c stage=qa -c objectTracer=1`.

**Measured**: the stack synthesises (5 resources) and `cdk diff` against QA shows exactly those 5 as new, with the two rights above (2026-11-27; the diff publishes the template file to the CDK bucket and creates no stack: checked afterwards). On a laptop, with the provider and the gate's model replaced by stand-ins, cut + trace + package of 3 drawings takes **0.7 s** (0.2 to 0.3 s each, in parallel); the earlier real runs (part B) were 10 to 15 s for a whole call, almost all of it the image provider and the gate.
**Not verified** (it needs the deploy): the cold start with a 161 MB layer (expect a few seconds; it fits the 30 s limit only if the sheet itself takes its usual 8 to 10 s), the function's two rights against AWS, the layer's Linux wheels at run time (they are the versions of the laptop proofs: numpy 2.5.5, scipy 1.18.1, built for Python 3.12 manylinux; the code bundle is tested to import alone in a fresh interpreter, on macOS), and one real object made end to end on Lambda. The first QA run should watch one video with a missing drawing.

## Part E. Stock photo sources: Unsplash is the last resort (2026-11-27, tracker R155)

**Where the engine ranked sources**: `engine/stock.py`. Photos come from two sources only: Unsplash (API) and Openverse (CC0, public domain, CC BY). `gather()` used to interleave them Unsplash first and show the reviewer six at once.
**The change** (small, in `gather()` and `scout_reviewed()`): the other sources come first; the reviewer is shown them alone; **an Unsplash photo is looked at only when the reviewer finds nothing suitable among the others**, or when there are none, or when the chosen one cannot be downloaded. When an Unsplash photo is used, its on-frame credit ("Photo: name / Unsplash"), its description credit and the download ping are exactly as before (tested). `LAST_RESORT = ("unsplash",)` is the one place that says so. A lone candidate from another source is still reviewed before it can displace Unsplash; a failing reviewer never takes an unreviewed Openverse photo while Unsplash has candidates. Cost: one more small-model review (about $0.0005) only when the first group is rejected.

**Measured on 15 real searches** (2026-11-27; real Openverse and Unsplash searches, the real reviewer, nothing downloaded in full; `docs/clips_on_demand/unsplash_ranking_measure_2026-11-27.jsonl`):

| | Unsplash picked | Another source picked |
|---|---|---|
| Before (interleaved, one review) | **15 of 15** | 0 |
| After | **5 of 15** | 10 (all CC0) |

In all 10 searches where the reviewer could see the other sources' photos it found a suitable one. **All 5 remaining Unsplash picks were Openverse's thumbnails failing to load** (its anonymous API, which answers errors when asked for several thumbnails quickly), not the reviewer preferring Unsplash; a registered (free) Openverse key or a retry would bring them back. Fifteen searches are a sample, not a rate.
**Say plainly:**
* **This does not remove the on-frame credit.** An Openverse photo still gets its own on-frame line today ("Photo: name (CC0 1.0)"). What changed is that the credit is no longer the Unsplash one, whose terms tie it to the frame. Taking CC0, public-domain and CC BY credits off the frame (they stay in the description list) is recommendation (2) and (3) of A5: a licence decision, not built here.
* **Picture quality may drop.** Openverse is Flickr, museums and public archives; the reviewer accepted "vintage" photographs twice in the sample. Unsplash was the better photography, which is why it used to come first. The reviewer still rejects what does not fit, and the lasting answer is our own library.
* Pixabay and Pexels are not photo sources of the engine today (only video sources); adding Pixabay photos (the key exists) would give the first group better pictures: not built.
* The editor's candidate list shows the other sources first too.

## Tests added on 2026-11-27 (targeted files; the full suite was NOT run)
| File | Tests | What |
|---|---|---|
| `backend/tests/test_media_policy.py` | 20 | the word lists in both languages (every category, 30 ordinary wordings left alone); one rubric in all six prompts; fail-closed parsing; the brief step (refused before any model call, the model's `policy`, plain English, tags); the clip gate and the image check; provider moderation before paying and after, with the reservation given back; the moderation client (request shape, stricter threshold, six kinds of failure, the key never in the request body); the vision check; object names (any language in, English out); drawings refused by the vision check never stored; the sheet between two moderation checks; the audit (verdicts, read only, budget stop); takedown and restore of an image, a clip, an on-demand and a bundled drawing; the command line (dry run by default, a reason required, production asks) |
| `backend/tests/test_stock_ranking.py` | 9 | other sources first; Unsplash only when nothing else suits, its credit unchanged; nothing suitable anywhere; a lone candidate; a failed download; a failing reviewer; one source down |
| `backend/tests/test_object_tracer.py` | 17 | the engine's call (only English names, nothing of the customer); eight ways the function can fail, each leaving the labels and the right money; switches and entitlement; the handler (answer shape, bad requests, the policy, every failure an answer); the code bundle importing alone in a fresh interpreter; the REAL cut, trace and gate on a sheet drawn in the test; the stack (5 resources, 2 rights, no tie to the main stack) |
| `backend/tests/test_clips_on_demand_cdk.py` | 5 (1 new) | the main stack gets one variable and one statement on the plan function, and still no resource |
Also run and green after the changes: `test_clips_on_demand.py` (134), `test_library_on_demand.py` (21), `test_image_catalog.py` (75), `test_four_k.py` (37), `test_photos.py` (25), `test_clips.py` (72), `test_engine.py` (not slow). Their stand-in model answers now carry `"policy": "none"`.

**Spend of this work** (limit $2): **$0.58**, all Bedrock: the audit's vision checks $0.57 (98 images with the large model $0.49 including a 3-image trial; 354 drawings with the small model, and the second and third looks, $0.08) and the 25 reviews of the ranking measurement $0.007. OpenAI's moderation endpoint (101 calls) is free. No image, sheet or clip was generated.
