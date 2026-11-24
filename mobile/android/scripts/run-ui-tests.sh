#!/bin/sh
# Runs the instrumented tests on the connected emulator against the QA backend.
#   scripts/run-ui-tests.sh                           everything quick: photo pipeline, UI flows, dictation granted + denied (no video is made)
#   scripts/run-ui-tests.sh com.videomk.app.E2ETest   makes one real 1-minute video from 4 photos (about 5-15 minutes, a few cents)
# Needs: a QA token minter (VMK_QA_MINT, default ~/.videomk-secrets/mint-tokens.sh, prints "ID_TOKEN REFRESH_TOKEN"; tokens last about an hour)
# and, for the photo tests, a directory with p1.jpg..p4.jpg (VMK_PHOTOS_DIR). Nothing secret is stored in the repository.
set -e
cd "$(dirname "$0")/.."
PKG=com.videomk.app
./gradlew :app:installDebug :app:installDebugAndroidTest -q
MINT="${VMK_QA_MINT:-$HOME/.videomk-secrets/mint-tokens.sh}"
TOK=$("$MINT")
ID=$(echo "$TOK" | awk '{print $1}'); REFRESH=$(echo "$TOK" | awk '{print $2}')
if [ -n "$VMK_PHOTOS_DIR" ]; then   # the debug build is debuggable: run-as lets us put the photos into its private files dir
  for f in p1 p2 p3 p4; do adb shell "run-as $PKG sh -c 'mkdir -p files; cat > files/$f.jpg'" < "$VMK_PHOTOS_DIR/$f.jpg"; done
fi
run() { adb shell am instrument -w -e class "$1" -e vmk_id_token "$ID" -e vmk_refresh_token "$REFRESH" $PKG.test/androidx.test.runner.AndroidJUnitRunner; }
if [ -n "$1" ]; then run "$1"; exit; fi
run com.videomk.app.PhotoPrepTest,com.videomk.app.QuickUiTest
adb shell pm grant $PKG android.permission.RECORD_AUDIO
run com.videomk.app.DictationUiTest#permissionGrantedMicButtonNeverCrashes
adb shell pm revoke $PKG android.permission.RECORD_AUDIO
run com.videomk.app.DictationUiTest#permissionDeniedMicButtonNeverCrashes
