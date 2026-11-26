#!/usr/bin/env python3
"""Fails if a view uses a fixed font size: all text goes through Font.vmk (Typography.swift) so it follows Dynamic Type."""
import pathlib, re, sys
root = pathlib.Path(__file__).resolve().parent.parent / "VideoMK"
bad = []
for f in sorted(root.glob("*.swift")):
    if f.name == "Typography.swift": continue
    for i, line in enumerate(f.read_text().splitlines(), 1):
        if re.search(r"\.system\(size:", line): bad.append(f"{f.name}:{i}: {line.strip()[:100]}")
if bad: print("\n".join(bad)); print(f"check_fonts: {len(bad)} fixed font size(s)"); sys.exit(1)
print("check_fonts: ok")
