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
The default provider is **Amazon Polly** (neural engine, voice Ruth): no key, the Lambda's IAM role is the credential, nothing leaves AWS. Change the voice with `-c ttsVoice=Matthew` (Stephen, Joanna, Amy, Brian also work in eu-west-1). `-c ttsProvider=gemini|openai|mock` selects another provider; those need the keys below (mock needs none).

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
