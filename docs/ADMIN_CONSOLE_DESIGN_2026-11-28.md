# Owner console and observability: design (2026-11-28)

Tracker row: R151. Status: design for the owner's review. Nothing is built.

**What you asked for (2026-11-28):** one place, only for you, that tells you whether everything is healthy and how the business is going: failed videos and what they cost us, the cost of prompts, the customer funnel and life cycle, churn risk, happiness, charts, and kill switches for emergencies. No third party. Very strict security, yet usable from your phone and from home. Cheap and easy to build.

## 0. The short version

* **What it is:** a private web page (works on the phone) at its own address, in its **own stack** (`videomk-admin-<stage>`), with its own sign-in that has nothing to do with customer accounts.
* **Sign-in:** a separate Amazon Cognito user pool with exactly one user (you), no sign-up, a **passkey** (Face ID or fingerprint) as the normal way in, and a long password plus authenticator code kept only as the recovery way. Sessions last minutes. A second Face ID tap is asked before any kill switch and before reading a customer's prompt.
* **Data:** a small job runs every hour, counts everything, and writes compact daily summaries ("rollups") to one small table. The console reads those. It does not copy prompts or build a second customer database.
* **What the console can change:** only "off" switches (stop creation, stop free creation, and later a few more) and suspending one account. It cannot give credits, change plans, raise budgets or delete anything. If someone ever got in, the worst they could do is stop things and read numbers.
* **Slice one (about 5 working days, about $4 a month):** six numbers, the free-budget gauge, the list of failed videos with what each cost, two kill switches, and email alerts. Section 6.
* **Monthly AWS cost of the whole thing:** about **$4 at 100 videos a day, $5 at 1,000, $7 at 10,000** (section 2.6). The optional paid firewall adds about $8.
* **Everything is AWS.** No outside service of any kind.

Words used: a **rollup** is one small record of totals for a day. A **kill switch** is a setting that stops something within a minute, without a deploy.

---

## 1. What the console answers

For each question: how it is measured, where the data is today, and what is missing. "Videos table" is the DynamoDB table of video records. Checked on QA on 2026-11-27: 216 records, 203 complete, 5 failed (2.3 %), 2 rejected, 12 accounts, $33.61 of tracked cost; the 5 failures carry only an error name (`AccessDenied` x2, `ValueError` x2, `ReadTimeoutError` x1) and 3 of them carry a cost ($0.145 together).

### 1.1 Health

| Question | Definition | Data today | Missing |
|---|---|---|---|
| Are videos being made? | Started, finished, failed, cancelled, rejected, in progress: last hour, today, 7 days | Videos table: `status`, `created_at`, `usage_day` | No way to read "one day" without reading the whole table: add an index by day (2.3) |
| Failure rate | failed / (complete + failed), by hour and day. Cancelled by the person and rejected requests are shown beside it, not inside it | `status` | Nothing |
| Failures by step | The workflow step where it broke (plan, beats, timeline, render chunk, audio, finalize) | Not on the record. Step Functions keeps the history of each run for 90 days | Slice one reads the step from the run history of failed runs only (few calls, and without the request text: `includeExecutionData=false`). Later the engine writes `failed_step` itself |
| Failures by cause | Grouped error name, with a plain label ("model timeout", "permission", "bad plan") | `failure_code` = the error class only | A plain-language map of error names; the first line of the cause, with any request text removed |
| Time to make a video, p50 and p95 | Run end minus run start, for completed first renders (edits apart) | Step Functions run start and stop times; `created_at`, `last_rendered_at` | Per-step times: not recorded. Later: the engine writes `made_ms` and `step_ms` |
| Stuck runs | Runs still going after 30 minutes (to be tuned once p95 is known) | Step Functions list of running runs | Nothing |
| Error budget | Target: 98 % of started videos complete (30-day window). Shows how much of the allowed 2 % is used | Rollups | The target itself is your decision (7.8) |
| Bedrock | Calls, throttles, server errors, latency per model | CloudWatch `AWS/Bedrock` (free, already there) | Nothing |
| Polly | Characters, errors, latency (it runs in us-east-1) | CloudWatch `AWS/Polly` | Nothing |
| Stock providers and web search (Unsplash, Pixabay, Pexels, Wikimedia, NASA, Tavily) | Calls, failures, empty answers per provider | Nothing | A counter per provider and outcome written by the engine (slice four) |
| The request check falling back | Share of checks answered by the simple screen instead of the model | Log line `BRIEF_CHECK source=fallback` | A counter (slice three) |
| What is deployed on each stage | Commit and time of the last deploy, QA and prod | Not recorded anywhere | `deploy.sh` writes the commit and time to one parameter per stage (no stack change) |
| Background jobs | Account deletion failures, mail forwarder dead letters | Two alarms exist, with no notification attached | Attach the alert topic |

### 1.2 Money

| Question | Definition | Data today | Missing |
|---|---|---|---|
| Cost per video and per credit, today / 7 / 30 days | **Tracked cost** = `cost_usd` (models, speech, searches). **Compute** = Lambda seconds x memory x price for the engine functions. **All-in** = tracked + compute. Per credit = all-in / credits charged and not refunded | `cost_usd` and the parts `c_speech`, `c_script`, `c_research`, `c_photos`, `c_stock` on each record; compute from CloudWatch (`cost_report.py` does this by hand today) | Compute is not known per video, only per day: it is shared out evenly. Good enough |
| Cost by step | Sum of each `c_*` part | On the record (138 of 216 QA records have the split) | Older records have only the total |
| Cost by model | Dollars per model (Sonnet, Haiku, Polly) | **Not stored.** The parts are by step, not by model | The engine adds a small `c_models` map (slice four). Until then: step is a close stand-in (script = Sonnet, checks = Haiku, speech = Polly) |
| **Cost of failed and cancelled videos** (we do not charge for these) | Sum of `cost_usd` on FAILED and CANCELLED records + their share of compute. Rejected requests and safety stops shown beside it (they cost one small model call each) | `cost_usd` is on a failed record only when the failure came after the plan was written (3 of 5 on QA) | Whether a cancelled video keeps its cost on the record must be checked when the cancel work lands. Failures before the plan cost almost nothing |
| Cost of free users against the daily budget | Free credits spent today / `free_daily_budget_credits` (15), in credits and dollars | The budget counter (`fbudget`, usage table); daily metrics `FreeCreditsDay`, `FreeCostEstimatedUsdDay` | Nothing |
| Revenue | Paying accounts x plan price, minus store fee and VAT (estimate), by month | **None: purchases are not built** (plans phase 2) | Arrives with phase 2. The console shows "0, purchases not live" until then |
| Margin per plan and per account | (What we keep from the plan) minus (all-in cost of that account's videos in the period) | `plan` on each video (new records only), entitlements table | Needs revenue. Until then: **cost per account**, which already shows who is expensive |
| Forecast of the AWS bill | AWS's own month-end forecast and yesterday's real spend by service | AWS Cost Explorer (the real bill, a day behind) | One call a day, $0.01 each. Cost Explorer must be switched on in the account |
| Does our tracking match the bill? | Tracked + compute against the real Bedrock, Polly and Lambda lines | Both sides exist | The comparison. A gap above 15 % means the list prices in the code are out of date |
| On-demand clip budget | Clips generated, dollars spent, against the per-account, daily and monthly caps | Being built (R150, branch `clips-on-demand`) | Its counters, once merged |

### 1.3 Customers

Test accounts (the unlimited flag) and our own accounts are left out of every number.

| Question | Definition | Data today | Missing |
|---|---|---|---|
| Sign-ups | New confirmed accounts per day, by method (email, Google, Apple) | Cognito user list (creation date) | Read once a day by the job. Nothing to build in the main stack |
| Activation | Share of sign-ups with a first COMPLETE video within 24 hours and within 7 days | Videos table | Nothing |
| Funnel | Sign-up, first video started, first video complete, second video, paying. Each as a count and a share of the step before | Videos table, entitlements | "Paying" needs phase 2 |
| Retention by week | Group accounts by sign-up week. For each later week: share that started at least one video | Videos table | Only creation is known. Opening the app or watching is not recorded per person (a `last_seen` day stamp could be added later; it is one more thing to store, so not by default) |
| Who is active | Accounts with a video today, in 7 days, in 30 days | Videos table | Nothing |
| Who went quiet (churn risk) | A list, in this order: (1) paying, no video for 14 days; (2) paying, more than 70 % of the month's credits unused a week before renewal; (3) last video failed or was cancelled and no return in 3 days; (4) made one video and none in the next 7 days; (5) sent a complaint | Videos, wallet, entitlements, feedback | The "Not really" answer of the in-app rating prompt stays on the phone today: it never reaches the server |
| Plan mix | Accounts per plan and state (active, grace, expired) | Entitlements table | Nothing |
| Credits unused | Plan credits and free credits sitting in wallets, and credits that expired unused last month | Wallet table | Nothing |

### 1.4 Usage

| Question | Definition | Data today | Missing |
|---|---|---|---|
| What people use it for | Kind of use and the 1 to 5 use rating, as shares per day | **Not built** (R140, queued) | Depends on R140. Privacy limits in 2.4 |
| Lengths, shapes, resolution | Distribution of `duration_s`, `aspect`, `resolution` | On the record (aspect and resolution on newer records only) | Nothing |
| Looks, languages, photos or not, research or not | Shares per day | Partly inside `request_json` (kept on 38 of 216 records); research = `c_research` above zero; photos = `c_photos` | The launcher writes four small fields on every new record: `look`, `lang`, `has_photos`, `has_deck`. No new resources |
| What fails the request check and why | Outcomes of the check: ok, questions asked, not supported (with which reason), stopped | Only stops are stored (safety table). Refusals for plan limits: metric `PlanRefused{Code}` | A counter per outcome (slice three) |
| Feedback | New messages by kind (problem, idea, other), app and version | Feedback table and the daily email | Nothing. The console lists them; the email stays |
| Ratings | "Enjoying VideoMK?" yes or not really; store reviews | On the device only | An optional tiny report from the apps (a count, no text). Store ratings stay in the stores' own consoles |
| Best prospects | Accounts with a steady use rating of 4 or 5, ordered by videos made | Not built (R140) | Depends on R140. A person decides whom to contact; the console only lists |

### 1.5 Abuse and safety

| Question | Definition | Data today | Missing |
|---|---|---|---|
| Stops by category | Safety stops per day and category | Safety table (90 days) | Nothing |
| Strikes, paused and held accounts | Accounts paused for 24 hours, held for review, held by staff | Computed from the safety table and the flags table (`safety:<id>`) | A list view. Review needs the 160-character excerpt, which is kept for exactly this purpose |
| Free-credit refusals | Refused claims by reason (duplicate email, duplicate device, throwaway address, IP limits) | Metrics `FreeClaimRefused{Reason}`, the daily plan report | Nothing |
| Velocity | Sign-ups and claims per network block, top blocks today | Usage table counters (8 days), plan report | Nothing |
| Device proof | Verified and refused proofs by platform | Metrics `DeviceProofVerified`, `DeviceProofRefused` | Nothing |

### 1.6 Operations

| Question | Definition | Data today | Missing |
|---|---|---|---|
| Switches and settings in force | Every kill switch, the plan knobs, the looks switched on per stage, the model ids | SSM parameter `/videomk/<stage>/plans/config`; looks and models are fixed at deploy (`stages.json`, function settings) | One read-only screen that shows them all |
| Budgets used | Free daily budget, clip budgets, the AWS monthly budget | Counters as above | AWS Budgets is not set up yet (free, section 5) |
| Alarms | Every alarm and its state | 4 alarms exist on QA, **none notifies anyone** | The alert topic (section 5) |
| Who did what in the console | Every sign-in and action | Nothing | The audit log (3.4) |

---

## 2. The data layer

### 2.1 Three ways compared

| | (a) Read the tables live | (b) Hourly rollups in one small table | (c) Events to S3 + Athena |
|---|---|---|---|
| How | The console's API queries DynamoDB and CloudWatch each time a screen opens | A job counts once an hour and stores small daily records; the console reads those | Every event is written to S3; questions are SQL queries |
| Build | Least code at first | Small: one job, one table | Most: event stream, formats, tables, queries |
| Speed on the phone | Slow and slower as data grows (a 30-day chart reads 30 days of records) | Instant: one read gets 90 days of history | Seconds per query |
| Cost as it grows | Grows with every screen opened | Flat: one pass over the day's records per hour | Low, but a fixed pipeline to run |
| History after a customer deletes their account | Lost: the records are gone | Kept as counts, which hold no personal data | Kept only if the events are scrubbed, which is hard |
| Risk | The console's API needs wide read access to customer tables all the time | The API reads only the rollup table. Only the job reads customer tables | A second copy of customer data in S3 to protect and to delete from |

### 2.2 Recommendation: (b), with two small live reads

Hourly rollups. Two things are read live because they are tiny and must be current: the runs in progress (one Step Functions call) and the switches in force (one parameter read). CloudWatch metrics are used only where an alarm needs them. Athena is not needed at this scale and can be added later without changing anything.

### 2.3 The job

* `admin_rollup`, every hour (EventBridge Scheduler), in the admin stack. Read-only on customer data.
* Each run recomputes **today and yesterday** from the records and overwrites their rollups. Recomputing (not adding one) means a run that fails or runs twice does no harm. Days older than two days are frozen: they stay as they were even after accounts are deleted.
* It needs one change in the main stack: an **index by day** on the videos table (`usage_day` + `created_at`, carrying only the small fields: status, plan, account id, costs, length, shape, failure code; **not the prompt**). An index is part of the table, so it adds no CloudFormation resources. Without it the job would read the whole table every hour, which costs more every month.
* Once a day it also reads the Cognito user list (sign-ups), the entitlements and wallet tables (plan mix, unused credits), Cost Explorer (the real bill) and the Lambda metrics (compute).
* A heartbeat metric is written at the end of each run; an alarm fires when it stops (section 5).

### 2.4 The table (`AdminRollups`, pay per request)

One table. `pk` and `sk` are text.

| pk | sk | What it holds | Kept |
|---|---|---|---|
| `day#2026-11-28` | `all` | started, complete, failed, cancelled, rejected, blocked; credits charged, free credits; tracked cost and its parts; compute cost; cost of failed, of cancelled; make time p50, p95; sign-ups by method; active accounts; first videos, second videos | 3 years |
| `day#2026-11-28` | `plan#free` (one per plan) | The same counts and costs for that plan | 3 years |
| `day#2026-11-28` | `fail#render_chunk#ReadTimeoutError` | Count and cost for one step and cause | 3 years |
| `day#2026-11-28` | `dim#look#whiteboard`, `dim#lang#es`, `dim#aspect#9:16`, `dim#use#business`... | Count per value | 3 years |
| `day#2026-11-28` | `safety#<category>`, `claim#<reason>` | Counts | 3 years |
| `hour#2026-11-28T14` | `all` | The same headline counts for one hour (for the 48-hour chart) | 14 days |
| `cohort#2026-W48` | `all` | Accounts that signed up that week, and for each later week how many made a video | 3 years |
| `bill#2026-11-27` | `all` | Yesterday's real AWS spend by service, and AWS's month-end forecast | 3 years |
| `fail#2026-11-28` | `<time>#<video id>` | One failed or cancelled video: step, cause, cost, plan, length, a short code for the account. **No prompt** | 90 days |
| `acct#<account id>` | `summary` | Sign-up day, first and last video day, videos made, failed, credits spent, cost, plan, churn-risk reason | Rewritten daily; removed 35 days after the last rewrite; removed by account deletion |

Rules:
* Everything except `acct#` and `fail#` is **counts only**: no account ids, no text. That is why it can be kept for years.
* `acct#` is personal data. It is the only new store of it. It must be added to the account-deletion steps and to the deletion coverage test, and to the retention table of the privacy policy if you want it listed separately (it is derived from "account and credit records").
* No email addresses in the table. The console shows a short code for an account; the email is looked up from Cognito only when you open that account.
* The use rating (R140) keeps its own rules: the console reads it, never copies it, and shows nothing for an account that objected.

### 2.5 Prompts and privacy

What the published privacy policy says today (`frontend/src/data/legal/privacy.ts`):
* Section 7: "staff do not read your prompts or look at your photos as a matter of course (see section 5 for the narrow exceptions)".
* **A gap found while checking:** that sentence points to "section 5", but section 5 is "Your photos" and lists no exceptions. The exceptions are not written out anywhere. The nearest text is the table of purposes in section 3: keeping the service secure, **stopping abuse, fixing faults**, enforcing the rules, **answering you**, and legal obligations. The policy should state the exceptions in one sentence (7.6).
* Section 17: the analysis of requests is done by an AI model; "Only the people who run VideoMK can see the ratings"; no sensitive characteristics are worked out or stored.
* Section 12: "staff access to production data is limited".

What that allows, in plain words: reading a prompt is defensible when there is a reason from that list (a failed video you are investigating, an abuse review, a support request from that person, a legal need). Browsing prompts out of interest is not allowed: the policy promises staff do not. So the console is built this way:

1. **Default view: no prompt text anywhere.** Lists show the options (length, shape, look, language), the kind of use and the rating once R140 exists, the status and the cost.
2. **A prompt opens only on an explicit tap**, after a fresh Face ID check, and after choosing a reason: *fault*, *abuse review*, *support request*, *legal*. The tap, the reason, the video id and the time go to the audit log. The text is shown once and never stored by the console.
3. **Safety excerpts** (the first 160 characters of a stopped request) are shown in the abuse review screen without the extra step: they are kept for exactly that purpose, for 90 days.
4. **Feedback messages** are shown freely: people sent them to you on purpose.
5. **Kinds of use** come from a short fixed list (for example: business or product, teaching or how-to, news, travel and places, family and celebrations, fun, test). Sensitive subjects are never a label: such requests are counted as "other". This follows condition 2 of the assessment in `docs/LIA_USAGE_SCORING_2026-11-27.md`.
6. The Step Functions run history contains the request text. The job reads it with the data left out, and the console's API has no permission to read it at all.

This is not legal advice. If you want to read prompts more freely (for product research), the policy must say so first; that is a decision for you and a lawyer (7.6).

### 2.6 Monthly AWS cost of the console

Prices read on 2026-11-27 (sources at the end). Assumptions: the day index carries about 0.4 KB per video and each video record is written about 10 times while it is made; you open the console a few times a day.

| Item | 100 videos a day | 1,000 a day | 10,000 a day |
|---|---|---|---|
| Day index on the videos table (extra writes, storage) | $0.02 | $0.20 | $2.00 |
| Rollup job: reads, writes, Lambda | $0.05 | $0.10 | $0.60 |
| Rollup table storage | under $0.01 | $0.01 | $0.05 |
| CloudWatch: about 8 metrics for alarms ($0.30 each) and 8 alarms ($0.10 each), metric reads | $3.40 | $3.40 | $3.40 |
| Cost Explorer: 2 calls a day at $0.01 | $0.60 | $0.60 | $0.60 |
| Sign-in (one user), the web page, the API, emails, audit storage | under $0.10 | under $0.10 | under $0.10 |
| **Total** | **about $4** | **about $5** | **about $7** |
| Optional: firewall paid by use (section 3.3) | + $8 | + $8 | + $8 |

Some of the CloudWatch lines may fall inside the free allowance (10 metrics, 10 alarms per account), so the real figure can be lower. The use rating (R140) has its own model cost and is not counted here.

---

## 3. The console: where it lives and who can get in

### 3.1 The options, honestly

| | (a) Own web page + API, own Cognito pool with a passkey | (b) AWS IAM Identity Center | (c) No public address: VPN or Verified Access | (d) Email reports with links |
|---|---|---|---|---|
| Only AWS? | Yes | Yes | AWS Client VPN and Verified Access: yes. Tailscale and similar: **no**, third party | Yes |
| Works from a phone on mobile data | Yes, any browser | The AWS console and AWS's phone app work. A custom page needs a SAML set-up and an organisation instance | Client VPN needs a VPN app and a profile on the phone. Verified Access works in a browser | Yes, it is email |
| Cost a month | About $0 ($8 with the paid firewall) | $0 | Client VPN: about $73 just to exist ($0.10 an hour) plus $0.05 per connected hour. Verified Access: about $200 ($0.27 an hour) | $0 |
| Passkey or Face ID | Yes, as the main way in | Only as a second step after a password | Depends on the identity behind it | No sign-in |
| Business screens, kill switches | Yes | Only what AWS's own dashboards can show; no funnel, no one-tap switches | Yes (it still needs the page of option a behind it) | Read only. No switches |
| Exposed to the internet | Yes: a sign-in page and an API that answers nothing without a valid token | AWS's own sign-in | No | No |
| Verdict | **Recommended** | Good as the emergency door (it is how you already reach AWS) | Too expensive for one person; pays $70 to $200 a month to hide a page that a passkey already protects | **Build it too**: it is the daily digest of section 5 |

### 3.2 Recommendation

**(a), with (d) alongside.** Reasons:
* It is the only option that gives you the business screens and the switches from a phone on mobile data for about nothing.
* A passkey cannot be phished and cannot be guessed: there is no secret to type. That removes the main reason for hiding the address behind a VPN.
* "Not on the internet" would cost $70 to $200 a month, or a server to look after, which is against how the rest of VideoMK is built (nothing running when idle).
* An IP allow-list does not fit: mobile data changes address all the time. A **country allow-list** does fit and is free (3.3).

### 3.3 How it is put together

* **Stack:** `videomk-admin-<stage>`, in the stage's own account and region (QA first). The main stack is at about 454 of CloudFormation's 500 resources, so nothing of this goes there except the day index and a few lines of code. The admin stack owns no customer data: deleting it loses nothing.
* **Page:** one static page in a private S3 bucket behind CloudFront. No framework needed, no outside scripts, fonts or analytics; charts are drawn by the page itself. Headers: strict Content-Security-Policy (only its own address and the Cognito endpoint), HSTS, no framing, no referrer, `noindex`.
* **Address:** a name that does not say "admin". Be aware that every certificate is listed in public logs, so the name is discoverable unless a wildcard certificate (`*.videomk.com`) is used. Use the wildcard, and do not rely on the name being secret.
* **API:** its own API Gateway (HTTP API). Every route requires a token from the admin pool, checked by API Gateway itself **before any of our code runs**. Throttled to a few requests a second. Only the console's own address may call it from a browser.
* **Sign-in:** a dedicated Cognito user pool (Essentials tier, needed for passkeys):
  * self sign-up off; one user, created by you from the command line;
  * MFA **required**; passkey with user verification counts as both factors (Cognito setting `MULTI_FACTOR_WITH_USER_VERIFICATION`);
  * Cognito demands one other sign-in method beside the passkey, and a first sign-in before a passkey can be registered: that is a 40-character random password plus an authenticator app code. Keep both off the phone (printed, or in a password manager). They are the recovery path and are never typed in normal use;
  * tokens live 10 minutes, renewal for at most 1 hour, kept in memory only (closing the tab signs you out); device remembering off;
  * no hosted sign-in page and no Google or Apple sign-in for this pool.
* **Step-up:** the API refuses a kill switch, an account suspension or a prompt view unless the sign-in happened in the last 5 minutes (the token says when). The page then asks for the passkey again: one Face ID tap.
* **Firewall:** CloudFront's free flat-rate plan includes AWS WAF with up to 5 rules at no charge (*assumption to confirm when building: that the plan can be chosen for this one distribution next to the existing ones*). Rules: a rate limit, AWS's bad-address list, and a country allow-list (the countries you are in; change it before you travel, or sign in through the emergency door). If the free plan is not available: WAF paid by use is about $8 a month, or skip it, because the page holds no data and the API answers nothing without a token. WAF cannot be attached to this kind of API directly; if you want the firewall in front of the API as well, the API is served through the same CloudFront address (a small variation, same cost).
* **Not reachable from the customer side:** different user pool (a customer's token is refused by API Gateway), different API, different address, no admin route in the customer API, no admin code in the apps or the website. The option of "an admin group in the customer pool" is rejected: one mistake in one route would expose everything.

### 3.4 Permissions and the audit log

| Part | May read | May write |
|---|---|---|
| Rollup job | Videos (through the day index), wallet, entitlements, safety, feedback, flags, usage tables; Cognito user list; Step Functions run list; CloudWatch; Cost Explorer | The rollup table only |
| Console API, "read" function | The rollup table; alarms and metrics; the switch parameter; running runs | Nothing |
| Console API, "detail" function (account view, failed video, prompt view; step-up for prompts) | One video record or one account's records at a time; one Cognito user | The audit log |
| Console API, "act" function (step-up always) | The switch parameter; one account's safety flag | The switch parameter `/videomk/<stage>/ops/config`; flag items whose key starts with `safety:`; the audit log |

* No function of the console can write credits, wallets, entitlements, plans, videos or the plan knobs. Those stay with the command-line tools and your AWS credentials, as today.
* **Switches can only restrict.** The code that reads `ops/config` treats every value as "off" or "less". A wrong or hostile value can stop the service; it cannot hand out anything.
* **Audit log:** every sign-in, every action, every prompt view is written as one small file to an S3 bucket with Object Lock (compliance mode, 400 days): nobody, not even the account's root user, can change or delete an entry before that. Entries hold the action, the time, the video or account id and the reason. Never a prompt, never an email address. In addition, AWS keeps the change history of the switch parameter, and CloudTrail records the parameter writes.
* Every sign-in and every action also sends you an email at once (section 5). If you get one you did not cause, you know.

### 3.5 What could go wrong

| Threat | What limits it |
|---|---|
| **Stolen phone** | The passkey needs Face ID or the phone's passcode. Someone who has the phone **and** its passcode can sign in: turn on Apple's Stolen Device Protection (it demands Face ID for passkeys away from home). Sessions end after minutes. From any computer: `aws cognito-idp admin-disable-user` locks the console in one command. The console can only stop things and read numbers; it cannot move credits or data out in bulk |
| **Phished password** | In normal use there is no password to type, and a passkey only works on the real address. The recovery password is useless without the authenticator code; keep both off the phone and never type them into a link from an email |
| **Leaked address** | The page is an empty shell with no data. The API refuses everything without a valid, fresh token. The firewall limits guessing |
| **A bug in the console's API showing customer data** | The token is checked by AWS before our code. The everyday function can read only counts. Customer records are read one at a time by a separate function. Prompts need step-up and a reason, and are logged. No bulk export exists |
| **A hijacked session flipping a kill switch** | Each switch needs a passkey check made in the last 5 minutes. Switches only stop things. You get an email the same minute. Undo is one tap, or one command from a computer. Nothing is deleted by any switch |
| **The admin stack itself is attacked or broken** | It owns no customer data. Delete the stack and the product keeps working; the command-line tools still do everything |
| **The audit log is tampered with** | Object Lock: it cannot be |
| **Your AWS login is taken** | Outside this design, but it matters more than all of the above: the root user and your admin user must have MFA. Worth a check (7.9) |

**Emergency door (break-glass):** the console is never the only way. Every switch is one parameter that can be set with the AWS command line or the AWS console in the browser; `plans_admin.py`, `safety_admin.py` and `wallet_admin.py` keep working. If you are locked out of the console: reset the admin user from the command line. This goes into a one-page runbook with the exact commands.

---

## 4. Kill switches and controls

All switches live in one parameter per stage, `/videomk/<stage>/ops/config`, read by the functions with the same 60-second cache as the plan knobs. A flip is a **setting change, live within about a minute, with no deploy**. An unreadable parameter keeps the last good values, and with none, everything is on (a storage error must never stop paying customers). Videos already being made always finish. Nothing is deleted by any switch.

| Switch | What it does exactly | Who is affected | Undo | Today |
|---|---|---|---|---|
| **Stop all new videos** | Generate, retry and deck-to-video answer "VideoMK is briefly paused for maintenance" (EN/ES, text editable). Capabilities says creation is paused so the apps can show it before the tap. Watching, the library and sign-in keep working | Everyone | Switch back | **To build.** A few lines in the launcher and capabilities; the apps need to show the message (older app builds show a generic error) |
| **Stop free videos** | Free creation is off (same as gallery-only): free accounts see the plans screen. Paid credits work | Free accounts | Switch back | **Exists**: `plans_admin.py gallery-only on`, or `free_daily_budget_credits 0`. The console adds its own restrict-only copy of the switch |
| **Stop on-demand clips** | No new clip is generated; the director falls back to stock clips and photos. No video fails because of it | Max accounts, invisibly | Switch back | **Being built** with R150 (its own kill switch and budgets). The console shows and flips it once merged |
| **Switch a look off** (whiteboard, cartoon, presenters, 3D backgrounds, moving backgrounds) | New videos do not get that look. A person who asked for it gets the standard look and the existing "adapted" note. Finished videos keep their look | Whoever would have got that look | Switch back | **Deploy only today** (`stages.json`, `-c whiteboard=1`...). To build: a runtime "off" list read where the look is decided (`common/looks.py`) and where the director chooses by itself |
| **Web research off** | No Tavily searches and no research model. Topics that need current facts are made from what the model knows, or declined with a clear message (your choice, 7.7) | Videos on news and recent topics | Switch back | **To build.** No switch exists |
| **Daily spend cap** | A counter of today's estimated spend (credits started x cost per credit). At the cap, new videos stop for everyone until 00:00 UTC with "We are at capacity today". Alerts at 80 % and 100 % | Everyone, once reached | Raise the cap from the command line (the console can only lower it), or wait for midnight | **Partly.** The free daily budget exists and works the same way. The cap for all usage is to build. `MAX_VIDEO_COST_USD` ($1.50 per video) exists but is fixed at deploy |
| **Suspend one account** | That account's generate answers "paused" (429). It can still sign in and watch. Reason is logged | One account | "Clear" in the console or `safety_admin.py clear` | **Exists** as `safety_admin.py hold` / `clear`. The console adds the button |
| **Sign-ups off** | New accounts cannot be created (email, Google, Apple): the sign-up step answers "Sign-ups are paused". Existing accounts sign in as usual | New people only | Switch back | **To build.** A check in the existing sign-up trigger (`auth_presignup.py`). Not by changing the user pool's own settings, which is risky |
| **Force the cheaper model** | Script and research run on the small model for new videos. Quality drops visibly; cost of the script falls by roughly two thirds (to be measured) | All new videos | Switch back | **Deploy only today** (`-c planModelId=`). To build: the engine reads the override when it calls the model. Note your rule "research never below Sonnet at medium": this switch knowingly breaks it, for emergencies |

Order of use in an emergency, cheapest harm first: suspend the account, then stop free videos, then the look or research that is misbehaving, then the spend cap, and only then stop everything.

---

## 5. Alerts, with no third party

### 5.1 How an alert reaches you

| Way | Cost | Reliability | Build | Verdict |
|---|---|---|---|---|
| **Email through SES** (already set up for hello@videomk.com; your address is verified, so the SES sandbox is not a problem) | $0.10 per 1,000 emails | Good. Can sit unread: mark the sender as VIP on the phone so it notifies | Small | **Slice one. Everything goes here** |
| **Push from AWS's own phone app** (AWS Console Mobile App, through AWS User Notifications, on alarm changes) | No extra charge | Good; a real push on the lock screen | Configuration only, no code. You install AWS's app and sign in to it | **Slice two, for the few "wake me" alerts** |
| **SMS through AWS** | A few cents per message (the exact price for your country was not confirmed today); some countries need a registered sender (US: about $2 to $10 a month and paperwork; Australia: $22 a month) | Works without data coverage | Small, plus the registration | Only if push proves unreliable |
| **Push through the VideoMK app itself** | About $1 per million | Good | Large: the apps have no push today (no APNs or FCM set-up exists in the backend). And it would put an admin path inside the customer app, which section 3 forbids | No. Reconsider only if the app gets "your video is ready" notifications, and even then keep admin alerts out of it |

One SNS topic per stage in the admin stack ("ops alerts"); every alarm points at it, including the four that exist today with nobody listening.

### 5.2 The few alerts that matter

| Alert | Fires when | Way |
|---|---|---|
| Videos are failing | 3 or more failures in an hour **and** more than 20 % of that hour's finished videos. (At higher volume: above 5 % for an hour) | Email + push |
| Stuck workflow | Any run still going after 30 minutes | Email + push |
| Cost spike | Today's tracked cost is above twice the 7-day average for this time of day and above $5; or one video above $1 | Email |
| Free budget | 80 % and 100 % of the day's free credits | Email (100 % is information: the budget did its job) |
| AWS bill | AWS Budgets: 80 % and 100 % of the monthly amount you set, and "forecast to pass 100 %" | Email from AWS itself. Free, no code, and independent of our own tracking |
| Spend cap (once built) | 80 % and 100 % | Email + push |
| Someone signed in to the console | Every sign-in | Email |
| A switch was used, an account was suspended or cleared, a prompt was opened | Every time | Email |
| An account was held for a zero-tolerance stop | Every time (rare; needs your review) | Email |
| The rollup job stopped | No heartbeat for 2 hours | Email |
| Account deletion failed; mail forwarder dead letter | The existing alarms | Email |

Provider trouble (Bedrock throttling, Polly errors) is shown on the health screen and in the digest; it pages you only through "videos are failing", so you are not woken for a blip that hurt nobody.

### 5.3 The two regular emails

* **Daily digest** (one email, at an hour you choose, also on quiet days so that silence means "broken"): videos made, failed, cancelled; failure rate; time to make; cost yesterday and per video; **what failures and cancellations cost**; free budget used; sign-ups and first videos; new feedback count; any alarm that fired; one link into the console. No prompt text, no customer names.
* **Weekly business summary** (Monday): the funnel for the week, retention of the last four sign-up weeks, plan mix and changes, churn-risk list size with the top five, cost and (later) revenue and margin against the week before, the AWS bill so far and the forecast, the three most common failure causes.

The existing daily feedback email stays as it is.

---

## 6. Slices

Effort is in working days for one builder (an agent with your review), QA first, then prod when you say.

### Slice one: "Is it healthy and what is it costing me" (about 5 days, about $4 a month)

Contents:
1. The admin stack on QA: rollup table, hourly job, the API (read and act functions), the admin sign-in with passkey, the page, the audit log, the alert topic.
2. In the main stack, no new resources: the day index on the videos table; the launcher and capabilities read `ops/config` for the two switches; the four existing alarms get the alert topic.
3. **Six numbers**, each for today with a 7-day line behind it:
   * videos made (and in progress now);
   * failure rate;
   * time to make a video, p50 and p95;
   * cost today, all-in, and per video;
   * **money lost on failed and cancelled videos**;
   * people: sign-ups and active accounts.
4. **Free-budget gauge**: credits used of today's 15, in credits and dollars.
5. **Failures list**: the last 50 failed or cancelled videos with time, step, cause, cost, plan and length. Tap one for its detail (no prompt in slice one).
6. **Two kill switches**: stop all new videos; stop free videos. Each behind a fresh Face ID check, each emails you when used.
7. **Alerts by email**: videos failing, stuck workflow, free budget, sign-in, switch used, job stopped. AWS Budgets set up by hand (10 minutes, free).
8. The runbook page with the emergency commands.

Not in slice one: customers and funnel, prompts, usage, abuse screens, the other switches, push.

What you can do with it alone: open one page on the phone and know in ten seconds whether videos are being made, what today cost, what failures cost, and stop the bleeding with one tap if something goes wrong.

**Home screen on the phone (slice one):**

```
+--------------------------------+
| VideoMK ops        prod  14:32 |
| All good            updated 9m |
+--------------------------------+
| MADE TODAY     | FAILURE RATE  |
| 142            | 2.1 %         |
| 3 in progress  | 3 of 145      |
| ▁▂▃▅▆▇▆ 7 days | ▁▁▂▁▁▃▁       |
+----------------+---------------+
| TIME TO MAKE   | COST TODAY    |
| 2 m 10 s       | $21.40        |
| p95 4 m 05 s   | $0.15 a video |
| ▃▃▄▃▃▅▃        | ▂▃▃▅▆▇▆       |
+----------------+---------------+
| LOST ON FAILED | PEOPLE        |
| $0.38 today    | 12 sign-ups   |
| $2.10 in 7 d   | 61 active     |
| 3 failed 1 canc| ▂▃▃▄▄▅▆       |
+--------------------------------+
| FREE BUDGET TODAY              |
| [#########------]  9 of 15     |
| about $1.35 of $2.25           |
+--------------------------------+
| FAILED AND CANCELLED         > |
| 14:02 render  timeout   $0.11  |
| 11:47 plan    model err $0.03  |
| 09:15 cancelled by user $0.06  |
+--------------------------------+
| SWITCHES                       |
| New videos       [ ON  ]       |
| Free videos      [ ON  ]       |
| (Face ID to change)            |
+--------------------------------+
| Alarms: 0 firing             > |
+--------------------------------+
```

The top line turns amber or red and says why ("Failure rate 24 % this hour", "Free videos are OFF since 13:05"). A stage switch (prod / QA) sits in the header. Numbers are examples.

### Slice two: "Who are my customers" (about 5 days, + about $1 a month)

* The account summaries, and with them: funnel, activation, weekly retention table, active accounts, churn-risk list, plan mix, unused credits, cost per account (margin once revenue exists).
* The real AWS bill and forecast (Cost Explorer), and the check that our tracking matches it.
* The daily digest and the weekly summary emails.
* Push for the two "wake me" alerts through AWS's phone app.
* Account view (by short code; email shown on a tap) with the suspend and clear buttons.
* You get: the answer to "is the business growing, and who is about to leave".

### Slice three: "What do they ask for, and who abuses it" (about 6 days, + under $1 a month)

* Usage screens: lengths, shapes, looks, languages, photos, research. Kinds of use and the best-prospects list as soon as the use rating (R140) is live.
* Request-check outcomes; safety stops, strikes, paused and held accounts with the review screen; free-claim refusals and velocity.
* Prompt view on an explicit, logged tap with a reason (2.5).
* Feedback list in the console.
* The remaining switches: looks off, research off, sign-ups off, daily spend cap, cheaper model, on-demand clips.
* You get: product direction, the abuse review in one place, and the full set of emergency controls.

### Slice four: "Depth" (about 4 days, + $0 to $13 a month)

* The engine writes the step that failed, per-step times and cost per model on each record; health and cost screens become exact instead of estimated.
* Counters for the stock providers and web search; third-party health tiles.
* Error budget screen; deployed version per stage.
* Revenue and true margin per plan and per account (needs purchases, plans phase 2).
* Optional: a test video made automatically every few hours on prod to catch a silent break before a customer does (about $0.07 each: 6 a day is about $13 a month).
* You get: precise answers to "where exactly does it break and where exactly does the money go".

---

## 7. Risks and decisions for you

1. **Passkey sign-in on a public address, or pay to hide it?** Recommended: passkey on a public address (section 3). Hiding it costs $70 to $200 a month and protects against little that the passkey does not already stop.
2. **Which stage first?** Recommended: QA, with the same console pointing at prod only after you have used it for a few days. One console per stage, each in its own account; no cross-account access.
3. **The day index on the prod videos table** is a change to the main stack (safe, done online by DynamoDB, no new resources). Recommended: yes; without it the hourly job gets dearer every month.
4. **Country allow-list.** Recommended: yes, with the countries you live and travel in. Cost: you must change it before a trip, or use the emergency door.
5. **How long to keep the audit log, knowing it cannot be shortened afterwards?** Recommended: 400 days.
6. **Prompts.** Recommended: build the console as designed (no browsing; a tap with a reason, logged), and add one sentence to the privacy policy that names the exceptions its section 7 refers to but never lists: fixing a fault, reviewing abuse, answering a support request from that person, a legal need. If you want to read prompts for product research, change the privacy policy first and ask a lawyer.
7. **Research off: make the video without fresh facts, or decline it?** Recommended: decline topics that need current facts with a clear message; a confident video with stale facts is worse than no video.
8. **The success target** for the error budget. Recommended: 98 % of started videos complete, reviewed after a month of real numbers.
9. **Your AWS logins.** The console is only as safe as the AWS account under it. Recommended: confirm MFA on the root user and on your admin user of both accounts before slice one goes to prod.
10. **Does the daily spend cap stop paying customers too?** Recommended: yes, but set high (about five times a normal day), because its job is to stop a runaway, and alerts at 80 % give you time to raise it.
11. **The account summaries are a new store of personal data** (small, deleted with the account). Recommended: accept, add it to the deletion steps and test, and mention it in the next privacy policy update.
12. **Risk: estimates.** Compute cost per video, the cost of failures before the plan step, and the step of a failure are estimates until slice four. They are marked as estimates on screen.
13. **Risk: the apps and the maintenance message.** App builds already in people's hands will show a generic error when creation is stopped. Recommended: add the message handling to the next iPhone and Android builds, independent of the console.
14. **Risk: more alerts than you read.** Recommended: start with the short list of 5.2 and add nothing for a month.

---

## Sources (all read 2026-11-27) and assumptions

Prices are AWS list prices in US dollars for US regions unless noted; the prod stack is in us-west-2 and the web hosting in us-east-1. Check them again before building.

* Amazon Cognito pricing and feature tiers (Essentials $0.015 per monthly user, first 10,000 free; passkeys need Essentials or Plus; TOTP on every tier): https://aws.amazon.com/cognito/pricing/ and https://docs.aws.amazon.com/cognito/latest/developerguide/cognito-sign-in-feature-plans.html
* Cognito passkeys with required MFA (`MULTI_FACTOR_WITH_USER_VERIFICATION`), need for one other sign-in method, first sign-in before registering a passkey, relying-party id: https://docs.aws.amazon.com/cognito/latest/developerguide/user-pool-settings-mfa.html and https://docs.aws.amazon.com/cognito/latest/developerguide/amazon-cognito-user-pools-authentication-flow-methods.html
* AWS WAF pricing ($5 per web ACL, $1 per rule, $0.60 per million requests until 31 January 2027; from 1 February 2027 $0.01 per protected resource-hour) and what it can attach to (not HTTP APIs): https://aws.amazon.com/waf/pricing/ and https://docs.aws.amazon.com/waf/latest/developerguide/how-aws-waf-works-resources.html
* CloudFront flat-rate plans (Free plan: $0, 1 million requests, 100 GB, WAF with 5 rules): https://aws.amazon.com/cloudfront/pricing/
* CloudFront response headers (Content-Security-Policy and the others): https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/understanding-response-headers-policies.html
* API Gateway pricing and HTTP API features (HTTP API $1.00 per million, built-in JWT authorizer, no WAF): https://aws.amazon.com/api-gateway/pricing/ and https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-vs-rest.html
* DynamoDB on-demand ($0.625 per million writes, $0.125 per million reads, $0.25 per GB-month): https://aws.amazon.com/dynamodb/pricing/on-demand/
* DynamoDB permissions per action (append-only by granting PutItem only): https://docs.aws.amazon.com/amazondynamodb/latest/developerguide/specifying-conditions.html
* Lambda ($0.0000166667 per GB-second on x86, $0.20 per million requests), EventBridge Scheduler ($1.00 per million, 14 million free), Step Functions: https://aws.amazon.com/lambda/pricing/ , https://aws.amazon.com/eventbridge/pricing/ , https://aws.amazon.com/step-functions/pricing/
* CloudWatch (custom metric $0.30 a month, standard alarm $0.10, metric reads $0.01 per 1,000 metrics, free allowance of 10 metrics and 10 alarms): https://aws.amazon.com/cloudwatch/pricing/
* Athena ($5 per TB scanned), S3 ($0.023 per GB-month), Firehose ($0.029 per GB): https://aws.amazon.com/athena/pricing/ , https://aws.amazon.com/s3/pricing/ , https://aws.amazon.com/firehose/pricing/
* S3 Object Lock, compliance mode: https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html
* Cost Explorer API ($0.01 per request) and AWS Budgets (alerts free): https://aws.amazon.com/aws-cost-management/aws-cost-explorer/pricing/ and https://aws.amazon.com/aws-cost-management/aws-budgets/pricing/
* SES ($0.10 per 1,000 emails): https://aws.amazon.com/ses/pricing/
* AWS User Notifications and push in the AWS Console Mobile App (no additional cost to configure and view): https://aws.amazon.com/notifications/faqs and https://docs.aws.amazon.com/consolemobileapp/latest/userguide/managing-notifications.html
* SMS and push through AWS End User Messaging (US registration and number fees, Australia number fee, push $1.00 per million): https://aws.amazon.com/end-user-messaging/pricing/ and https://aws.amazon.com/sns/sms-pricing/
* AWS Verified Access ($0.27 per app-hour) and Client VPN ($0.10 per hour per endpoint association, $0.05 per connection-hour); both figures are from the pricing pages' us-east-2 examples: https://aws.amazon.com/verified-access/pricing/ and https://aws.amazon.com/vpn/pricing/
* IAM Identity Center (no extra charge; passkeys as MFA after a password; custom applications by SAML only, with an organisation instance): https://aws.amazon.com/iam/identity-center/faqs/ , https://docs.aws.amazon.com/singlesignon/latest/userguide/mfa-types.html , https://docs.aws.amazon.com/singlesignon/latest/userguide/customermanagedapps.html

**Not confirmed today:** the price of one SMS to your country; whether a sender registration is needed there; that CloudFront's free flat-rate plan can be applied to this one distribution in the prod account; that AWS User Notifications can carry our own events directly (the design routes them through alarms, which it does support); Cognito's exact minimum token lifetimes (the design asks for 10 minutes and 1 hour).

**Assumptions:** one admin, a few console visits a day; a video record is written about 10 times while it is made; the day index carries about 0.4 KB per video; QA figures (216 videos, 2.3 % failures) are test traffic and say little about prod; effort assumes the same way of working as the rest of the project (an agent builds, tests on QA, you review).

**In the repository:** `docs/PLANS.md` (knobs, free budget, metrics `videomk/Plans`, alarms without notification, the 454-resource count), `docs/COSTS.md` and `backend/scripts/cost_report.py` (cost fields), `docs/INTAKE_AND_SAFETY.md` (stops, holds, `safety_admin.py`), `docs/LIA_USAGE_SCORING_2026-11-27.md` (conditions for the use rating), `docs/FEEDBACK.md` (table, daily email, rating prompt), `docs/CREATE_API.md` (statuses, cancel, retry), `docs/EMAIL_FORWARDING.md` (SES), `docs/DEPLOY.md` and `backend/stages.json` (stages, looks, models), `backend/engine_v2.py` and `lambdas/generate_video/handlers/mark_failed_handler.py` (where a failure is recorded), `frontend/src/data/legal/privacy.ts` (sections 3, 7, 10, 12, 17).
