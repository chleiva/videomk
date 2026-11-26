#!/usr/bin/env bash
# The public website at videomk.com (privacy, terms, support, delete-account, landing page). Prod account, us-east-1.
#   scripts/site.sh build   assemble backend/build/site from the Astro build (only the public pages, never the app screens)
#   scripts/site.sh zone    create the hosted zone and point the domain's name servers at it
#   scripts/site.sh full    certificate, bucket, CloudFront, DNS records, upload (run after `zone`; DNS can take minutes to switch)
set -euo pipefail
cd "$(dirname "$0")/.."
export AWS_PROFILE=default AWS_REGION=us-east-1 AWS_DEFAULT_REGION=us-east-1
need_prod() { [ "$(aws sts get-caller-identity --query Account --output text)" = "464863885161" ] || { echo "Refusing: not the prod account" >&2; exit 1; }; }
# `build` touches no AWS account. SITE_OUT / SITE_ASTRO_OUT (absolute paths) let a test build into scratch folders (defaults: build/site, ../frontend/dist).
OUT="${SITE_OUT:-build/site}"; ASTRO_OUT="${SITE_ASTRO_OUT:-$PWD/../frontend/dist}"
build() {
  (cd ../frontend && npx --yes astro build --outDir "$ASTRO_OUT" >/dev/null)
  rm -rf "$OUT" && mkdir -p "$OUT"
  # English at /, Spanish at /es/ (docs/I18N.md): both languages of every public page
  for p in privacy terms support delete-account; do
    mkdir -p "$OUT/$p" "$OUT/es/$p"; cp "$ASTRO_OUT/$p/index.html" "$OUT/$p/"; cp "$ASTRO_OUT/es/$p/index.html" "$OUT/es/$p/"
  done
  mkdir -p "$OUT/_astro"; cp "$ASTRO_OUT"/_astro/*.css "$OUT/_astro/"; cp "$ASTRO_OUT/favicon.svg" "$OUT/"
  cp ../frontend/site-pages/index.html "$OUT/index.html"; cp ../frontend/site-pages/es/index.html "$OUT/es/index.html"; cp ../frontend/site-pages/404.html "$OUT/404.html"
  # the shared layout loads the app's sign-in script; the public pages must not: keep only the styles
  find "$OUT" -name '*.html' -exec python3 -c "import re,sys;f=sys.argv[1];s=open(f).read();s=re.sub(r'<script[^>]*>.*?</script>','',s,flags=re.S);open(f,'w').write(s)" {} \;
  # sitemap with the language alternates, so search engines pair each page with its translation
  python3 - "$OUT" <<'PY'
import sys
out = sys.argv[1]
rows = []
for p in ["", "privacy/", "terms/", "support/", "delete-account/"]:
    en, es = f"https://videomk.com/{p}", f"https://videomk.com/es/{p}"
    alts = f'<xhtml:link rel="alternate" hreflang="en" href="{en}"/><xhtml:link rel="alternate" hreflang="es" href="{es}"/><xhtml:link rel="alternate" hreflang="x-default" href="{en}"/>'
    rows += [f"<url><loc>{u}</loc>{alts}</url>" for u in (en, es)]
open(out + "/sitemap.xml", "w").write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">' + "".join(rows) + "</urlset>\n")
open(out + "/robots.txt", "w").write("User-agent: *\nAllow: /\nSitemap: https://videomk.com/sitemap.xml\n")
PY
  echo "built $OUT"
}
case "${1:?build|zone|full}" in
  build) build ;;
  zone)
    need_prod
    build
    npx --yes aws-cdk@latest deploy videomk-site -c site=1 -c sitePhase=zone --require-approval never
    zone=$(aws route53 list-hosted-zones-by-name --dns-name videomk.com --query 'HostedZones[0].Id' --output text)
    ns=$(aws route53 get-hosted-zone --id "$zone" --query 'DelegationSet.NameServers' --output text)
    args=(); for n in $ns; do args+=("Name=$n"); done
    aws route53domains update-domain-nameservers --domain-name videomk.com --nameservers "${args[@]}"
    echo "name servers set: $ns" ;;
  full) need_prod; build; npx --yes aws-cdk@latest deploy videomk-site -c site=1 -c sitePhase=full --require-approval never ;;
esac
