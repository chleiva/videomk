#!/usr/bin/env bash
# Deploy one stage. Usage: scripts/deploy.sh qa|prod [extra cdk args]
# Refuses to run unless the AWS profile's account matches stages.json for that stage.
set -euo pipefail
cd "$(dirname "$0")/.."
stage="${1:?usage: deploy.sh qa|prod [cdk args]}"; shift || true
read -r account region profile < <(python3 -c "import json,sys;c=json.load(open('stages.json'))['$stage'];print(c['account'],c['region'],c['profile'])")
actual="$(aws sts get-caller-identity --profile "$profile" --query Account --output text)"
if [ "$actual" != "$account" ]; then echo "Refusing: profile '$profile' is account $actual, stage '$stage' expects $account" >&2; exit 1; fi
if [ "$stage" = "prod" ]; then read -r -p "Deploy to PRODUCTION ($account)? type 'prod': " ok; [ "$ok" = "prod" ] || exit 1; fi
export AWS_PROFILE="$profile" AWS_REGION="$region" AWS_DEFAULT_REGION="$region"
npx --yes aws-cdk@2 bootstrap "aws://$account/$region" -c stage="$stage"
npx --yes aws-cdk@2 deploy "videomk-$stage" -c stage="$stage" -c engine=v2 --require-approval never "$@"
