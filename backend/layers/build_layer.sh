#!/usr/bin/env bash
# Build a Lambda layer for linux/x86_64 + Python 3.12 from <layer>/requirements.txt.
# No Docker needed: pip is told to fetch manylinux wheels, so it works from macOS/Linux/CI alike.
#
#   backend/layers/build_layer.sh [video_deps|engine_deps ...]    (default: all layers)
set -euo pipefail
cd "$(dirname "$0")"

layers=("$@")
if [ ${#layers[@]} -eq 0 ]; then layers=(video_deps engine_deps); fi

for layer in "${layers[@]}"; do
  [ -f "$layer/requirements.txt" ] || { echo "skip $layer (no requirements.txt)"; continue; }
  echo "==> building $layer"
  rm -rf "$layer/python"
  mkdir -p "$layer/python"
  python3 -m pip install \
    --quiet --upgrade \
    --platform manylinux2014_x86_64 --platform manylinux_2_28_x86_64 \
    --implementation cp --python-version 3.12 \
    --only-binary=:all: \
    --target "$layer/python" \
    -r "$layer/requirements.txt"
  # Trim what Lambda never needs (the unzipped limit for function + layers is 250 MB).
  find "$layer/python" -type d \( -name __pycache__ -o -name tests -o -name test \) -prune -exec rm -rf {} + 2>/dev/null || true
  find "$layer/python" -name '*.pyi' -delete
  du -sh "$layer/python" | sed "s|^|    size: |"
done
