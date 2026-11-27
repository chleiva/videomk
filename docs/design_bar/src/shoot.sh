#!/bin/bash
# Renders html/*.html with headless Chrome into ../mockups (JPEG, under ~400 KB each). Needs Google Chrome and the repo venv (Pillow).
set -e
cd "$(dirname "$0")"
CH="/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
TMP=$(mktemp -d); OUT=../mockups; mkdir -p $OUT
shot() { # name w h scale
  "$CH" --headless=new --disable-gpu --hide-scrollbars --force-device-scale-factor=$4 --window-size=$2,$3 --screenshot="$TMP/$1.png" "file://$PWD/html/$1.html" >/dev/null 2>&1
}
while read n w h; do [ -n "$n" ] && shot $n $w $h 1.5; done < html/phone.txt
while read n w h; do [ -n "$n" ] && shot $n $w $h 1.5; done < html/web.txt
../../../.venv/bin/python - "$TMP" "$OUT" <<'PY'
import sys, glob, os
from PIL import Image
tmp, out = sys.argv[1], sys.argv[2]
for f in sorted(glob.glob(tmp + "/*.png")):
    im = Image.open(f).convert("RGB"); name = os.path.basename(f)[:-4] + ".jpg"
    for q in (86, 80, 74, 68, 60):
        im.save(os.path.join(out, name), quality=q, optimize=True, progressive=True)
        if os.path.getsize(os.path.join(out, name)) < 400_000: break
    print(name, im.size, os.path.getsize(os.path.join(out, name)) // 1024, "KB")
PY
rm -rf "$TMP"
