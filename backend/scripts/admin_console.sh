#!/usr/bin/env bash
# The owner console's own stack (docs/ADMIN_CONSOLE_DESIGN_2026-11-28.md, docs/ADMIN_RUNBOOK.md). Usage: scripts/admin_console.sh qa|prod synth|diff|deploy [extra cdk args]
# Refuses unless the AWS profile's account matches stages.json for that stage. Never touches the main stack.
set -euo pipefail
cd "$(dirname "$0")/.."
stage="${1:?usage: admin_console.sh qa|prod synth|diff|deploy [cdk args]}"; action="${2:?synth|diff|deploy}"; shift 2 || true
read -r account region profile < <(python3 -c "import json,sys;c=json.load(open('stages.json'))['$stage'];print(c['account'],c['region'],c['profile'])")
actual="$(aws sts get-caller-identity --profile "$profile" --query Account --output text)"
if [ "$actual" != "$account" ]; then echo "Refusing: profile '$profile' is account $actual, stage '$stage' expects $account" >&2; exit 1; fi
if [ "$stage" = "prod" ] && [ "$action" = "deploy" ]; then read -r -p "Deploy the console to PRODUCTION ($account)? type 'prod': " ok; [ "$ok" = "prod" ] || exit 1; fi
export AWS_PROFILE="$profile" AWS_REGION="$region" AWS_DEFAULT_REGION="$region"
case "$action" in
  synth)  npx --yes aws-cdk@latest synth "videomk-admin-$stage" -c admin=1 -c stage="$stage" -o cdk.admin.out "$@" >/dev/null && echo "synthesized to backend/cdk.admin.out" ;;
  diff)   npx --yes aws-cdk@latest diff "videomk-admin-$stage" -c admin=1 -c stage="$stage" -o cdk.admin.out "$@" ;;
  deploy) npx --yes aws-cdk@latest deploy "videomk-admin-$stage" -c admin=1 -c stage="$stage" -o cdk.admin.out --require-approval never "$@" ;;
  *) echo "synth|diff|deploy" >&2; exit 1 ;;
esac
