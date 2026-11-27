#!/usr/bin/env bash
# The public website at videomk.com (privacy, terms, support, delete-account, landing page). Prod account, us-east-1.
#   scripts/site.sh build   assemble backend/build/site from the Astro build (only the public pages, never the app screens)
#   scripts/site.sh zone    create the hosted zone and point the domain's name servers at it
#   scripts/site.sh full    certificate, bucket, CloudFront, DNS records, upload (run after `zone`; DNS can take minutes to switch)
#   scripts/site.sh app-build  assemble backend/build/app: the web app's screens (app.videomk.com) built for the prod stack, nothing public
#   scripts/site.sh app        app-build, then the stack `videomk-app-site` (bucket, CloudFront, certificate, DNS, upload); idempotent
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
  for f in apple-touch-icon.png icon-192.png icon-512.png site.webmanifest; do [ -f "$ASTRO_OUT/$f" ] && cp "$ASTRO_OUT/$f" "$OUT/$f"; done   # linked from every page head
  # the home pages come from the Astro build (components/Landing.astro, both languages); only the 404 page is still hand-written
  cp "$ASTRO_OUT/index.html" "$OUT/index.html"; cp "$ASTRO_OUT/es/index.html" "$OUT/es/index.html"; cp ../frontend/site-pages/404.html "$OUT/404.html"
  # the home page's sample videos, posters and share image (frontend/public/samples, og.jpg)
  mkdir -p "$OUT/samples"; cp "$ASTRO_OUT"/samples/* "$OUT/samples/"; cp "$ASTRO_OUT/og.jpg" "$OUT/og.jpg"
  # the shared layout loads the app's sign-in script; the public pages must not: keep only the styles. The one exception is an inline block marked `data-keep`
  # (the home page's ~1.5 KB video player script and its JSON-LD): it imports nothing and touches no sign-in code.
  find "$OUT" -name '*.html' -exec python3 -c "import re,sys;f=sys.argv[1];s=open(f).read();s=re.sub(r'<script[^>]*>.*?</script>',lambda m:m.group(0) if 'data-keep' in m.group(0).split('>')[0] else '',s,flags=re.S);open(f,'w').write(s)" {} \;
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
# The web app (docs/WEB_REDESIGN_2026.md): same Astro project, only the app screens, built with the PROD values. Everything PUBLIC_* is public by design
# (client id, hosts); no secret is involved. APP_OUT / APP_ASTRO_OUT let a test build into scratch folders.
APP_OUT="${APP_OUT:-build/app}"; APP_ASTRO_OUT="${APP_ASTRO_OUT:-$PWD/../frontend/dist-app}"
app_build() {
  (cd ../frontend && PUBLIC_API_BASE="${PUBLIC_API_BASE:-https://backend.videomk.com}" PUBLIC_AUTH_DOMAIN="${PUBLIC_AUTH_DOMAIN:-https://login.videomk.com}" \
     PUBLIC_COGNITO_CLIENT_ID="${PUBLIC_COGNITO_CLIENT_ID:-55borf73gh37uka0t3vj965dkc}" PUBLIC_AUTH_GOOGLE="${PUBLIC_AUTH_GOOGLE:-1}" \
     npx --yes astro build --outDir "$APP_ASTRO_OUT" >/dev/null)
  rm -rf "$APP_OUT" && mkdir -p "$APP_OUT/auth"
  for p in signin generations new media settings wallet watch edit feedback questions delete-account; do mkdir -p "$APP_OUT/$p"; cp "$APP_ASTRO_OUT/$p/index.html" "$APP_OUT/$p/"; done
  mkdir -p "$APP_OUT/es/delete-account"; cp "$APP_ASTRO_OUT/es/delete-account/index.html" "$APP_OUT/es/delete-account/"   # Apple's revoke page returns to /delete-account: its language switch needs the Spanish page too
  mkdir -p "$APP_OUT/auth/callback"; cp "$APP_ASTRO_OUT/auth/callback/index.html" "$APP_OUT/auth/callback/"
  cp -R "$APP_ASTRO_OUT/_astro" "$APP_OUT/_astro"
  for f in favicon.svg apple-touch-icon.png icon-192.png icon-512.png site.webmanifest; do [ -f "$APP_ASTRO_OUT/$f" ] && cp "$APP_ASTRO_OUT/$f" "$APP_OUT/$f"; done
  # The root and any unknown address (CloudFront answers /index.html for them): signed-in people go to their videos, the sign-in page handles the rest.
  cat > "$APP_OUT/index.html" <<'HTML'
<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="robots" content="noindex"><title>videomk</title>
<meta http-equiv="refresh" content="1;url=/generations"><link rel="icon" type="image/svg+xml" href="/favicon.svg"></head>
<body><script>location.replace("/generations")</script><noscript><a href="/generations">videomk</a></noscript></body></html>
HTML
  echo "built $APP_OUT"
}
case "${1:?build|zone|full|app-build|app}" in
  app-build) app_build ;;
  app) need_prod; app_build; npx --yes aws-cdk@latest deploy videomk-app-site -c appSite=1 --require-approval never ;;
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
