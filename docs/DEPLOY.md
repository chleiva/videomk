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
