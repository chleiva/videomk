#!/usr/bin/env bash
# The public website at videomk.com (privacy, terms, support, delete-account, landing page). Prod account, us-east-1.
#   scripts/site.sh build   assemble backend/build/site from the Astro build (only the public pages, never the app screens)
#   scripts/site.sh zone    create the hosted zone and point the domain's name servers at it
#   scripts/site.sh full    certificate, bucket, CloudFront, DNS records, upload (run after `zone`; DNS can take minutes to switch)
set -euo pipefail
cd "$(dirname "$0")/.."
export AWS_PROFILE=default AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1
[ "$(aws sts get-caller-identity --query Account --output text)" = "464863885161" ] || { echo "Refusing: not the prod account" >&2; exit 1; }
build() {
  (cd ../frontend && npx --yes astro build >/dev/null)
  rm -rf build/site && mkdir -p build/site
  for p in privacy terms support delete-account; do mkdir -p "build/site/$p"; cp "../frontend/dist/$p/index.html" "build/site/$p/"; done
  mkdir -p build/site/_astro; cp ../frontend/dist/_astro/*.css build/site/_astro/; cp ../frontend/dist/favicon.svg build/site/
  cp ../frontend/site-pages/index.html build/site/index.html; cp ../frontend/site-pages/404.html build/site/404.html
  # the shared layout loads the app's sign-in script; the public pages must not: keep only the styles
  find build/site -name '*.html' -exec python3 -c "import re,sys;f=sys.argv[1];s=open(f).read();s=re.sub(r'<script[^>]*>.*?</script>','',s,flags=re.S);open(f,'w').write(s)" {} \;
  echo "built backend/build/site"
}
case "${1:?build|zone|full}" in
  build) build ;;
  zone)
    build
    npx --yes aws-cdk@latest deploy videomk-site -c site=1 -c sitePhase=zone --require-approval never
    zone=$(aws route53 list-hosted-zones-by-name --dns-name videomk.com --query 'HostedZones[0].Id' --output text)
    ns=$(aws route53 get-hosted-zone --id "$zone" --query 'DelegationSet.NameServers' --output text)
    args=(); for n in $ns; do args+=("Name=$n"); done
    aws route53domains update-domain-nameservers --domain-name videomk.com --nameservers "${args[@]}"
    echo "name servers set: $ns" ;;
  full) build; npx --yes aws-cdk@latest deploy videomk-site -c site=1 -c sitePhase=full --require-approval never ;;
esac
