#!/bin/sh
# Captures of the Look picker and the Characters picker in every state (the same list and names as the iPhone review set), on the debug build's fake server:
#   scripts/look-shots.sh <out dir> [light dark es large small pills]
# Needs ONE running emulator with the debug app and its test APK installed (./gradlew :app:installDebug :app:installDebugAndroidTest). No account, no network.
# Each mode restarts the app, runs LookUiTest#captures with the device set up for it, pulls the pictures and puts the device back.
set -e
OUT="${1:?where to put the captures}"; shift || true
MODES="${*:-light dark es large small pills}"
PKG=com.videomk.app
RUNNER=$PKG.test/androidx.test.runner.AndroidJUnitRunner
reset() {
  adb shell cmd uimode night no >/dev/null; adb shell settings put system font_scale 1.0
  adb shell cmd locale set-app-locales $PKG --locales en >/dev/null 2>&1 || true
  adb shell wm size reset; adb shell wm density reset
}
take() {  # folder, test method
  adb shell am force-stop $PKG
  adb shell rm -rf /sdcard/Android/data/$PKG/files/looks/"$1"
  adb shell am instrument -w -e class "$PKG.LookUiTest#$2" -e shots "$1" $RUNNER | tail -4
  mkdir -p "$OUT/$(dirname "$1")"; rm -rf "$OUT/$1"
  adb pull /sdcard/Android/data/$PKG/files/looks/"$1" "$OUT/$1" >/dev/null
}
small() { adb shell wm size 720x1280; adb shell wm density 320; }   # 360 x 640 dp
for m in $MODES; do
  reset
  case "$m" in
    light) take light captures ;;
    dark) adb shell cmd uimode night yes >/dev/null; take dark captures ;;
    es) adb shell cmd locale set-app-locales $PKG --locales es >/dev/null; take es captures ;;
    large) adb shell settings put system font_scale 2.0; take large captures ;;
    small) small; take small captures ;;
    pills)  # the pills in two rows at most: a small phone, default and largest text, English and Spanish
      small; take pill-rows/small-default-en capturesOfThePillRows
      adb shell cmd locale set-app-locales $PKG --locales es >/dev/null; take pill-rows/small-default-es capturesOfThePillRows
      adb shell settings put system font_scale 2.0; take pill-rows/small-largest-text-es capturesOfThePillRows
      adb shell cmd locale set-app-locales $PKG --locales en >/dev/null; take pill-rows/small-largest-text-en capturesOfThePillRows ;;
    *) echo "unknown mode $m"; exit 1 ;;
  esac
done
reset
