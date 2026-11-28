#!/bin/sh
# Captures of the Create v2 dock in every state, on the debug build's fake server (see CreateV2UiTest#captures):
#   scripts/create-v2-shots.sh <out dir> [light dark es large small small-large]
# Needs ONE running emulator with the debug app and its test APK installed. No account, no network.
set +e
OUT="${1:?where to put the captures}"; shift || true
MODES="${*:-light dark es large small small-large}"
PKG=com.videomk.app
RUNNER=$PKG.test/androidx.test.runner.AndroidJUnitRunner
reset() {
  adb shell cmd uimode night no >/dev/null; adb shell settings put system font_scale 1.0
  adb shell cmd locale set-app-locales $PKG --locales en >/dev/null 2>&1 || true
  adb shell wm size reset; adb shell wm density reset
}
take() {
  adb shell am force-stop $PKG
  adb shell rm -rf /sdcard/Android/data/$PKG/files/looks/"$1"
  adb shell am instrument -w -e class "$PKG.CreateV2UiTest#captures" -e shots "$1" $RUNNER | tail -4
  rm -rf "$OUT/$1"; mkdir -p "$OUT"
  adb pull /sdcard/Android/data/$PKG/files/looks/"$1" "$OUT/$1" >/dev/null
}
small() { adb shell wm size 720x1280; adb shell wm density 320; }   # 360 x 640 dp
for m in $MODES; do
  reset
  case "$m" in
    light) take light ;;
    dark) adb shell cmd uimode night yes >/dev/null; take dark ;;
    es) adb shell cmd locale set-app-locales $PKG --locales es >/dev/null; take es ;;
    large) adb shell settings put system font_scale 2.0; take large ;;
    small) small; take small ;;
    small-large) small; adb shell settings put system font_scale 2.0; take small-large ;;
    *) echo "unknown mode $m"; exit 1 ;;
  esac
done
reset
