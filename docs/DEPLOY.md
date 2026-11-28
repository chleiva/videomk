# Deploying (stages)

`backend/stages.json` maps a stage to an AWS account, region and CLI profile. The stack is created per stage and account (DynamoDB, S3 bucket `videomk-<stage>-<account>`, Cognito pool, API). Nothing is imported from or shared with any other account; the former hard-wired account has been removed from the repo.

| stage | profile | account | region | purpose |
|---|---|---|---|---|
| qa | `qa` | 552357225438 | eu-west-1 | QA, deploy freely |
| prod | `default` | 464863885161 | us-west-2 | go-live (asks for confirmation) |

## QA deploy (run on your computer, where the credentials are)
```
git fetch origin ccr-3c41ecff-680028 && git checkout ccr-3c41ecff-680028
cd backend && pip install -r requirements.txt   # or your venv
bash layers/build_layer.sh                     # engine layer (needs Docker or the script's pip platform flags)
scripts/deploy.sh qa
```
The script refuses unless the profile's account matches the stage. Outputs: `ApiUrl`, `UserPoolId`, `UserPoolClientId`, `AuthDomain`, `AssetsBucketName`.

## Web hosting: videomk.com and app.videomk.com (prod account, us-east-1)
Two static sites, each in its own stack, both in the prod account next to the `videomk.com` hosted zone (decision 2026-11-27, docs/WEB_REDESIGN_2026.md):
- **videomk.com** (stack `videomk-site`, `backend/scripts/site.sh full`): the public pages (home, privacy, terms, support, delete-account, EN + ES). The old app addresses (`/signin`, `/generations`, `/wallet`, `/feedback`, `/watch`, `/edit`, `/questions`, `/auth/callback`) answer a **301** to the same path on app.videomk.com (query string kept) from the CloudFront Function in `backend/site_stack.py`.
- **app.videomk.com** (stack `videomk-app-site`, `backend/scripts/site.sh app`): the signed-in web app. `site.sh app-build` assembles `backend/build/app` from the Astro project (only the app screens, built with the prod values: `PUBLIC_API_BASE=https://backend.videomk.com`, `PUBLIC_AUTH_DOMAIN=https://login.videomk.com`, `PUBLIC_COGNITO_CLIENT_ID` = the prod web client, `PUBLIC_AUTH_GOOGLE=1`; every one can be overridden from the environment); `site.sh app` also deploys the stack. Private bucket + CloudFront (OAC), TLS 1.2+, HSTS, CSP, `noindex`; hashed `_astro/*` files are cached for a year, HTML is `no-cache`; an unknown address answers the app root (`/index.html`, which sends people to `/generations`). /privacy, /terms and /support on the app host 301 back to videomk.com; /delete-account is served by the app (the Apple/Google web return address).
- **backend.videomk.com** (the API's own host; `stages.json` prod `apiHost`): the prod stage has `"domain": "videomk.com"`, so the app stack creates the regional certificate (us-west-2, DNS-validated), the API Gateway custom domain, the base-path mapping and the Route 53 alias. **`api.videomk.com` cannot be used**: API Gateway answers "The domain name you provided already exists" (checked 2026-11-27: no such domain in the prod account in us-west-2 or us-east-1, so another AWS account still holds it, like the `auth.videomk.com` CloudFront alias conflict). If you release it there, set `apiHost` to `api.videomk.com` again (default when `apiHost` is absent). The execute-api URL keeps working.
- Cognito web client (prod): callbacks `https://app.videomk.com/auth/callback` and `https://videomk.com/auth/callback` (the second only while old tabs and links drain; remove it later), logout `https://app.videomk.com/` and `https://videomk.com/`. No localhost in prod. QA keeps `http://localhost:4321/...`.
- Redirect URI of the web app is exactly `<origin>/auth/callback` (no `/index.html`: Cognito matches the string).
- Never deploy the app stack from a dirty tree without `cdk diff`: it should only ever show the app bucket, distribution, certificate, function, policy and records.

## Voice (TTS)
The default provider is **Amazon Polly**, **generative** engine, voice Ruth, called in **us-east-1** (the generative engine is not offered in eu-west-1; it is in eu-central-1, eu-west-2, us-east-1 and us-west-2). No key: the Lambda's IAM role is the credential. Narration text therefore leaves the stack's region for us-east-1, still inside AWS: mention it in the privacy policy.
- Languages: English and Spanish. The brief's language is detected first (free for clear briefs, a small model call otherwise; callers may pass `language: "en"|"es"`); research reads that language's Wikipedia, the script, captions and voices are in it, and any other language is declined with a clear message.
- Voices: a small balanced set, not Polly's whole catalogue (`lambdas/engine/voices.py`). English: American (Ruth, Danielle, Matthew, Stephen), British (Amy, Brian), Australian (Olivia, Russell), Indian (Kajal, Arjun). Spanish: Latin American US (Lupe, Pedro), Mexican (Mia, Andres), Spain (Lucia, Sergio). Ruth (English) and Lupe (Spanish) are the house voices the director leans on. The director casts one narrator by default; when the user asks for a conversation, interview or debate it casts up to 3 speaking characters plus an optional narrator, each with a different voice of the video's language, and tags each beat with its `speaker`. Unknown, wrong-language or duplicate voices are corrected (characters choose first; the narrator takes what is left). The editor can reassign a beat's speaker (`set_speaker`) or a speaker's voice (`set_voice` with `speaker`).
- To force one voice for everything (testing), set `-c ttsVoice=Matthew`: it overrides the casting and disables dialogue.
- Engine and region: `-c pollyEngine=generative|neural|long-form` and `-c pollyRegion=us-east-1`. Long-form is only in us-east-1 (Ruth, Danielle, Gregory, Patrick) and costs about 3x generative.
- The engine and region are saved in each video's plan, so edits months later keep the same voice. Plans made before this keep the neural engine.
- List prices (verify): neural $16, generative $30, long-form $100 per 1M characters (about 900 characters per spoken minute).
- `-c ttsProvider=gemini|openai|mock` selects another provider; those need the keys below (mock needs none).

## Image catalog (optional, default off)
`-c imageCatalog=1` adds videomk's own generated-image library to a stage (private bucket, items table, S3 Vectors index `catalog-images`, demand table) and lets the director try it before stock photos; `-c catalogMinScore=0.35` overrides the match threshold. Needs the v2 engine. Before switching on: create the salt `aws ssm put-parameter --name /videomk/catalog_demand_salt --type SecureString --value "$(openssl rand -hex 32)"`, then fill the catalog (generate in QA or on a laptop, copy to prod with `catalog_promote.py`). Everything is in docs/IMAGE_CATALOG.md.

## Secrets (never in chat or git)
Only for photos and optional providers:
```
aws ssm put-parameter --profile qa --region eu-west-1 --type SecureString --name /videomk/unsplash_access_key --value '...'   # photos (recommended)
aws ssm put-parameter --profile qa --region eu-west-1 --type SecureString --name /videomk/gemini_api_key --value '...'       # only with ttsProvider=gemini
aws ssm put-parameter --profile qa --region eu-west-1 --type SecureString --name /videomk/openai_api_key --value '...'       # only with ttsProvider=openai
```
Also enable Bedrock model access for the Claude models in eu-west-1 (console, Bedrock, Model access).

## Frontend against QA
Set `PUBLIC_API_BASE`, `PUBLIC_AUTH_DOMAIN`, `PUBLIC_COGNITO_CLIENT_ID` from the outputs. Production's custom domain is off until a Route 53 zone exists in the prod account (`domain` in stages.json).


## Production and the Claude models (found 2026-11-25)
The production AWS account (us-west-2) can call Claude 4.x on Bedrock (`us.anthropic.claude-sonnet-4-6`, `us.anthropic.claude-haiku-4-5-20251001-v1:0`, Opus 4.5 and 4.6) but is denied every Claude 5.x model (`AccessDeniedException ... not available for this account`), while QA has them. The engine defaults to Claude 5.5, so until the account is granted access prod is deployed with the older models:
```
npx aws-cdk@latest deploy videomk-prod -c stage=prod -c engine=v2 -c "@aws-cdk/core:bootstrapQualifier=vmk" \
  -c planModelId=us.anthropic.claude-sonnet-4-6 -c reviewModelId=us.anthropic.claude-haiku-4-5-20251001-v1:0 --require-approval never
```
(`planModelId` writes the script model and `reviewModelId` the small model, in the video functions and in the photo library functions.) When Claude 5.x is enabled for the account (Bedrock console, Model access / the Anthropic use-case form, in us-west-2), redeploy without the two `-c` model flags and check with the probe in this section's history (invoke `us.anthropic.claude-sonnet-5-5` and `us.anthropic.claude-haiku-5-5`).

## Which model does what (2026-11-25)
* **Research** (the web-research agent that gathers the facts a video is built on): the script model at **medium effort** (`RESEARCH_MODEL_ID`, default = `PLAN_MODEL_ID`, i.e. Sonnet 5.5 on QA; `RESEARCH_EFFORT`, default `medium`). Owner rule: never below Sonnet 5.5 medium. It ran on the small model at low effort before.
* **Script / plan** (writes everything that is said and shown): `PLAN_MODEL_ID`, Sonnet 5.5, medium effort.
* **Small jobs** (photo and clip review, clip verification, request check, whether to research): `REVIEW_MODEL_ID`, Haiku 5.5, low effort.
* Prod cannot call Claude 5.x yet, so there research and script both run on Sonnet 4.6 until access is granted.
* **Endpoints (owner, 2026-11-25)**: Sonnet 5.5 and Haiku 5.5 are called through Amazon Bedrock's **global** inference profiles (`global.anthropic.claude-sonnet-5-5`, `global.anthropic.claude-haiku-5-5`), not the regional `eu.`/`us.` ones; the functions' policies allow the regionless `arn:aws:bedrock:::foundation-model/*` the global route uses. Requests may be processed in any commercial region. Cohere embeddings (private photos) stay on the regional profile.

## Raising the Lambda memory cap in the prod account (needed for 4K and the heaviest render steps)
The prod account (464863885161, us-west-2) rejects Lambda memory above 3008 MB (new-account limit; QA allows 10240 MB). The stack caps memory per stage (`lambdaMemoryCap`, 3008 in prod) and refuses `2160p` below 10240 MB. Service Quotas does not list a function-memory quota for this account and the CLI cannot open support cases without a paid support plan, so the owner opens one case in the console:
1. Sign in to the prod account, Support Center, **Create case**, type **Service quota increase** (Account and billing support is available on the Basic plan), Service: **Lambda**, Region **US West (Oregon)**.
2. Request: "Please raise the Lambda function memory limit for this account from 3,008 MB to 10,240 MB in us-west-2 (and us-east-1). We render video in Lambda (ffmpeg and frame drawing need about 6 GB for 4K output) and run a document converter. Our QA account already uses 10,240 MB." Use case: video generation service, compute-bound steps of a few minutes each, concurrency under 50.
3. When AWS confirms, check with a dry deployment: `cd backend && ... deploy videomk-prod -c lambdaMemoryCap=10240` (all other flags as in `/tmp/deploy_stack.sh prod`) and add `readyResolutions=720p,1080p,2160p` when 4K should be offered.
Until then prod renders at 1080p and below with 3008 MB functions (measured fine at 1080p).

## Owner console (its own stack per stage, built 2026-11-27)
`backend/scripts/admin_console.sh qa diff|deploy` deploys `videomk-admin-<stage>` and nothing else (design: docs/ADMIN_CONSOLE_DESIGN_2026-11-28.md; commands for emergencies, first sign-in and travel: docs/ADMIN_RUNBOOK.md). It reads the main stack's table, workflow and pool names from the deployed launcher's settings when it is synthesized: nothing is exported from, or added to, the main stack. The main stack carries two things for it: the day index `GSI_UsageDay` on the videos table and the launcher's read of the switches item (`ops:switches` in the account-flags table, `lambdas/common/ops_switches.py`); both go out with the usual `scripts/deploy.sh`. A new stage needs two deploys (the passkey is bound to the console's address: put the output `ConsoleHost` in `stages.json` as `adminHost`, deploy again). The `aws-cdk` client has been seen to hang after the stack reached CREATE_COMPLETE; check `aws cloudformation describe-stacks` before waiting longer.

## Compliance: test evidence (R181)

Every test run and verification that matters is kept as a permanent, hash-chained log in the repo (`test-evidence/`),
as audit evidence (commit sha, who, what, counts, redacted raw output for failures and releases). Record with
`scripts/record_test_run.py --by <who> --label <suite>`, verify with `scripts/verify_test_evidence.py`, summary in
`test-evidence/INDEX.md`. Release and CI runs must set `VMK_EVIDENCE=1 VMK_RELEASE=1`, and the verifier must pass before
a release. Details and retention: `test-evidence/README.md`.
