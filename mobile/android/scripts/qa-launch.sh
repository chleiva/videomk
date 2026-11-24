#!/bin/sh
# Launches the debug app on the connected emulator signed in as the QA test user (tokens are minted with the AWS profile `qa`).
# Needs: VMK_QA_MINT (a script that prints "ID_TOKEN REFRESH_TOKEN", default ~/.videomk-secrets/mint-tokens.sh). Never commit its output.
# Optional: VMK_MINUTES=1, VMK_PHOTOS=/a.jpg:/b.jpg
set -e
MINT="${VMK_QA_MINT:-$HOME/.videomk-secrets/mint-tokens.sh}"
set -- $("$MINT")
ID="$1"; REFRESH="$2"
EXTRA=""
[ -n "$VMK_MINUTES" ] && EXTRA="$EXTRA --es vmk_debug_default_minutes $VMK_MINUTES"
[ -n "$VMK_PHOTOS" ] && EXTRA="$EXTRA --es vmk_debug_photo_files $VMK_PHOTOS"
adb shell am force-stop com.videomk.app
# shellcheck disable=SC2086
adb shell am start -n com.videomk.app/.MainActivity --es vmk_debug_reset 1 --es vmk_debug_id_token "$ID" --es vmk_debug_refresh_token "$REFRESH" $EXTRA >/dev/null
