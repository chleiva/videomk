# Request check (intake) and safety (built 2026-11-25)

Contract with the apps: `docs/CREATE_API.md`. Design background: `docs/PIPELINE_V3.md` section 4. Measured behaviour: `docs/INTAKE_EVAL.md`.

## How it works
`POST /users/{user}/videos/brief` (Lambda `video_brief`) is called when the person taps Create. It makes **one** small-model call (`llm.REVIEW_MODEL`, Claude Haiku 5.5, effort low, hard 4 s timeout, one retry) that returns safety, support and clarity together as JSON `{block, unsupported, questions}`. Code (`common/intake.py`) validates everything the model says and composes everything the person sees except the question texts and the not-supported sentence.
* **Safety** (`common/safety.py` holds the policy): category ids with severity. Zero-tolerance: `minors_sexual`, `violence_instructions`, `private_targeting`. Standard: `sexual_explicit`, `graphic_gore`, `self_harm_methods`, `weapons_drugs`, `hate_harassment`, `fraud_deception`, `malware`, `extremist_propaganda`, `nonconsensual_intimate`, `disinformation`, `other_harm`. The classifier prompt lists them with a rubric: educational, news, historical, fictional and medical-information requests that discuss a topic are allowed; a block is for requests whose purpose or content IS the harm; when unsure, allow. The person only sees a fixed neutral sentence (English or Spanish), never the category.
* A zero-tolerance verdict is **confirmed by a second small call** before it holds the account (a "no" makes it an ordinary stop). If the platform refuses to read the request (`stop_reason: refusal`, empty answer, seen for explosives instructions) that counts as a block; the deterministic screen names the category when it can.
* **Support**: unsupported language, editing an existing video, live-action, not a narrated video -> `not_supported` with a one-sentence reason and suggestion in the person's language.
* **Questions**: only ids `audience`, `tone`, `focus`, `details`; at most 3; 2 to 5 options of at most 28 characters; text at most 70; none that ask about what the form owns (a regex backstop drops them); none when answers are given. Option id = the label lower-cased with underscores, so the answer carries its own meaning and **no server state or second model call** is needed to merge it.
* **Answers** (`[{id, option | text | skip}]`, all answers so far each time): an option or a free text sets the field of that id (`audience`, `tone`, `focus`); free text next to an option, or any text on `details`, goes to `notes` (200 chars). The `brief` is `{audience, tone, focus, notes, summary}`; `summary` is composed in code (`For kids · Calm · Focus: causes`). Answers with only option taps return `ok` without a model call (the request was checked in round one, and `generate` checks it again). Free text in answers is sent to the model as data with the prompt, so it cannot change a verdict.
* **Failure behaviour**: the call is tried twice (4 s each) in `brief`, once in `generate`; a timeout, throttle or unusable output falls back to the deterministic screen (`common/safety.screen`, narrow English and Spanish patterns such as "how to make a bomb", "child porn", "dox"; never a bare topic word). No hit means `ok`, no questions. The director's own `legit` check remains a backstop.
* **Rate limit**: 400 `brief` calls per account per day (`BRIEF_DAILY_LIMIT`, counted with `usage.consume` as `brief:<sub>`); beyond it only the free screen runs.
* **Identity**: Cognito `sub` only; the path user must equal the token user.

## The gate in generate
`sf_launcher.safety_gate` runs after body validation and the idempotent-replay lookup, **before** photo checks and copies, the duplicate-request fingerprint and any charge. Paused/held account -> 429 `{status: paused, message, retry_after}` (header `Retry-After`); block -> recorded, 400 `{status: blocked, message}`; nothing is charged and no workflow starts. It checks the prompt plus the brief's text. The optional `brief` is validated with `common.intake.clean_brief` (object, at most 2 KB else 400, known keys only, strings clipped, summary recomputed) and passed in the workflow input. The gate is active only when `SAFETY_TABLE` is set (the CDK construct sets it); without it `generate` behaves exactly as before. A clear prompt costs about 0.5 s of model time in `generate` (the same check also runs in `brief`; there is no signed attestation yet, see Risks).

## What is stored and for how long
Table `SafetyTable` (pay-per-request, TTL attribute `ttl`): `user_id` (HASH), `ts` (RANGE, epoch ms), `category`, `severity`, `source` (`model` or `fallback`), `prompt_hash` (first 32 hex of SHA-256 of the normalised prompt), `excerpt` (first 160 characters), `ttl` = 90 days. Only **stops** are recorded. No model reasoning, no full prompt, nothing for requests that pass. The privacy policy says so (`frontend/src/pages/privacy.astro`, "How long we keep data"). Logs: `SAFETY_STRIKE user=<sub> category=<id>`, `SAFETY_HOLD user=<sub> reason=<admin_hold|zero_tolerance|repeated_30d|pause_24h>`, `BRIEF_CHECK ms= source= ...` (never the prompt).

## Enforcement (computed from the table; no counters)
| Rule | Result |
|---|---|
| any zero-tolerance stop (records live 90 days) | hold at once, until staff `clear` or the record expires |
| 3 standard stops within 24 h | paused until 24 h after the third (`retry_after` counts down) |
| 8 standard stops within 30 days | hold for review |
| staff `hold` | hold until `clear` |
Stops are not recorded while an account is paused or held (the 429 comes first), so a pause does not extend itself. If the tables cannot be read, the account is treated as fine and it is logged (`SAFETY_STATE_UNAVAILABLE`): a storage error must not stop paying people.

## Staff procedures (`backend/scripts/safety_admin.py`)
```
AWS_PROFILE=qa python backend/scripts/safety_admin.py show you@example.com    # recent stops (category, severity, source, time, excerpt), counts/cleared, current state
AWS_PROFILE=qa python backend/scripts/safety_admin.py clear you@example.com   # earlier stops stop counting, hold lifted; records stay until their 90 days
AWS_PROFILE=qa python backend/scripts/safety_admin.py hold you@example.com
```
`clear` and `hold` write `safety_cleared_at` / `safety_hold` to the **admin-only** AccountFlagsTable under the key `safety:<sub>` (a separate item from the credits flags); runtime roles can only read that table, so an account can never clear itself. Review a hold: `show`, read the excerpts, `clear` if it was a mistake. Prod asks you to type `prod` for changes. A person who contacts support about a "paused" message is answered from `show`.

## Tuning
* Policy wording, categories and examples: `common/safety.CATEGORIES` and the rubric in `common/intake.SYSTEM`. Thresholds: constants at the top of the record section in `common/safety.py`. Fallback screen patterns: `_SCREEN`.
* After any prompt change run `AWS_PROFILE=qa python backend/scripts/intake_eval.py --runs 3 --stress` (about 3 cents) and update `docs/INTAKE_EVAL.md`. Bars: clear prompts at least 95 percent `ok` with 0 questions, no false blocks on the borderline set, no missed harmful prompts.
* The small model id comes from `REVIEW_MODEL_ID` (CDK context `reviewModelId`, same override as the video functions).

## Infra
`backend/request_intake.py` (CDK construct, wired by one block in `backend_stack.py`): Lambda `video_brief` (512 MB, 20 s), `SafetyTable`, route `POST /users/{user_id}/videos/brief` (Cognito). IAM: the table read/write for `video_brief` and the launcher, `AccountFlagsTable` read only, `usage_table` read/write for `video_brief`, `bedrock:InvokeModel` on Anthropic models only. The launcher also gets `SAFETY_TABLE` (and `REVIEW_MODEL_ID` when overridden). Uses the 10 s launcher timeout: the gate makes one 4 s attempt.

## Risks and follow-ups
* `generate` repeats the model call (about 0.5 s). A signed attestation from `brief` (HMAC of user, prompt hash, expiry) would remove it for clear prompts; not built to keep the "generate cannot be bypassed" argument simple.
* A false zero-tolerance hold is the worst outcome: it is confirmed by a second call, and staff can clear it; watch `SAFETY_HOLD` lines in the first weeks.
* Hits to the Bedrock quota would push traffic to the fallback screen (weaker); watch `BRIEF_CHECK source=fallback`.
* Prompts in languages other than English and Spanish are judged by the model in the same way, but the fallback screen only knows English and Spanish.
