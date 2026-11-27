#!/usr/bin/env bash
# Archive the Beta build (QA backend, no debug code) and upload it to TestFlight.
# Needs the App Store Connect API key variables in the repo's .env (gitignored) and an app record for com.videomk.app in App Store Connect.
#   mobile/ios/scripts/testflight.sh            upload
#   mobile/ios/scripts/testflight.sh --local    only build a signed .ipa (no upload, no app record needed)
# The provider sign-in buttons follow the environment (project.yml keeps them off by default):
#   VMK_AUTH_GOOGLE=YES VMK_AUTH_APPLE=YES mobile/ios/scripts/testflight.sh
set -euo pipefail
root="$(cd "$(dirname "$0")/../../.." && pwd)"
get() { grep -E "^$1=" "$root/.env" | head -1 | cut -d= -f2- | sed -E "s/^['\"]//; s/['\"]$//; s/[[:space:]]+$//"; }
KID=$(get APP_STORE_CONNECT_API_KEY_KEY_ID); ISS=$(get APP_STORE_CONNECT_API_KEY_ISSUER_ID); KP=$(get APP_STORE_CONNECT_API_KEY_KEY_FILEPATH)
case "$KP" in /*) ;; *) KP="$root/$KP";; esac
[ -n "$KID" ] && [ -n "$ISS" ] && [ -f "$KP" ] || { echo "App Store Connect key variables or key file missing in .env" >&2; exit 1; }

out="${TMPDIR:-/tmp}/videomk-testflight"; rm -rf "$out"; mkdir -p "$out"
dest=upload; extra="<key>manageAppVersionAndBuildNumber</key><true/>"
[ "${1:-}" = "--local" ] && { dest=export; extra=""; }
cat > "$out/ExportOptions.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>method</key><string>app-store-connect</string><key>destination</key><string>$dest</string>
  <key>teamID</key><string>39ANXJNUTL</string><key>signingStyle</key><string>automatic</string>
  <key>uploadSymbols</key><true/>$extra
</dict></plist>
PLIST

cd "$root/mobile/ios"
xcodegen generate >/dev/null
# Archive unsigned (a development profile would need a registered test device); the export step signs for distribution.
switches=()
[ -n "${VMK_AUTH_GOOGLE:-}" ] && switches+=("VMK_AUTH_GOOGLE=$VMK_AUTH_GOOGLE")
[ -n "${VMK_AUTH_APPLE:-}" ] && switches+=("VMK_AUTH_APPLE=$VMK_AUTH_APPLE")
echo "sign-in switches: ${switches[*]:-none (email only)}"
xcodebuild archive -project VideoMK.xcodeproj -scheme VideoMK-TestFlight -configuration Beta -destination 'generic/platform=iOS' \
  -archivePath "$out/VideoMK.xcarchive" CODE_SIGNING_ALLOWED=NO CODE_SIGN_IDENTITY="" ${switches[@]+"${switches[@]}"} | tail -1
/usr/libexec/PlistBuddy -c "Print :VMKAuthGoogle" -c "Print :VMKAuthApple" "$out/VideoMK.xcarchive/Products/Applications/VideoMK.app/Info.plist" | paste -sd' ' - | sed 's/^/in the archive (Google Apple): /'
xcodebuild -exportArchive -archivePath "$out/VideoMK.xcarchive" -exportPath "$out/export" -exportOptionsPlist "$out/ExportOptions.plist" \
  -allowProvisioningUpdates -authenticationKeyPath "$KP" -authenticationKeyID "$KID" -authenticationKeyIssuerID "$ISS" 2>&1 | grep -E "error|EXPORT|Upload" || true
echo "output in $out"
