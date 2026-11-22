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

## Secrets (never in chat or git)
```
aws ssm put-parameter --profile qa --region eu-west-1 --type SecureString --name /videomk/openai_api_key --value '...'
aws ssm put-parameter --profile qa --region eu-west-1 --type SecureString --name /videomk/gemini_api_key --value '...'
aws ssm put-parameter --profile qa --region eu-west-1 --type SecureString --name /videomk/unsplash_access_key --value '...'
```
Also enable Bedrock model access for the Claude models in eu-west-1 (console, Bedrock, Model access).

## Frontend against QA
Set `PUBLIC_API_BASE`, `PUBLIC_AUTH_DOMAIN`, `PUBLIC_COGNITO_CLIENT_ID` from the outputs. Production's custom domain is off until a Route 53 zone exists in the prod account (`domain` in stages.json).
