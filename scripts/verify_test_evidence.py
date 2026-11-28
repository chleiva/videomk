#!/usr/bin/env python3
"""Verify the test-evidence hash chain and file hashes. Exit 1 on any tampering."""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evidence_lib as E  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=E.REPO_ROOT)
    a = ap.parse_args(argv)
    errors, n, head = E.verify(a.root)
    for e in errors:
        print("TAMPERING/ERROR:", e)
    if errors:
        print(f"FAILED: {len(errors)} problem(s) in {n} ledger entries")
        return 1
    print(f"OK: {n} ledger entries, chain intact. head={head}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
