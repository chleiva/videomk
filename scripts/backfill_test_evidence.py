#!/usr/bin/env python3
"""One-off: add RECONSTRUCTED ledger entries for results that were only written down in docs.

These are source=backfill. The original raw output no longer exists; the numbers are copied from the named doc,
the commit is the one that introduced that doc (the tested tree may differ), timestamps are that commit's time.
Idempotent: an entry already present (same label + doc) is skipped.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evidence_lib as E  # noqa: E402

CAVEAT = ("RECONSTRUCTED from the doc named in 'doc'; not original evidence. The original raw output no longer exists. "
          "The commit is the one that introduced the doc, not necessarily the exact tested tree.")

ENTRIES = [
    {"doc": "docs/POLLY_LIVELY_DEFAULTS_2026-11-27.md section 10", "sha": "2b315ca", "ts": "2026-11-27T22:45:41Z",
     "label": "backend-pytest-polly-lively-group1", "kind": "pytest", "passed": 605, "failed": 0, "skipped": None, "errors": 0,
     "result": "pass", "scope": "test_polly_lively, test_voice_quality, test_languages, test_length_fit, test_presenters, test_engine, test_art_direction, test_length, test_staged",
     "by": "unknown (agent, per doc)"},
    {"doc": "docs/POLLY_LIVELY_DEFAULTS_2026-11-27.md section 10", "sha": "2b315ca", "ts": "2026-11-27T22:45:41Z",
     "label": "backend-pytest-polly-lively-group2", "kind": "pytest", "passed": 377, "failed": 0, "skipped": None, "errors": 0,
     "result": "pass", "scope": "test_engine, test_silence, test_sync, test_quality_fixes, test_looks, test_skills, test_making_status, test_create_options, test_quality_backlog (whole suite was not run)",
     "by": "unknown (agent, per doc)"},
    {"doc": "docs/BETTER_DICTATION_CLIENTS_2026-11-28.md Tests", "sha": "96f1b66", "ts": "2026-11-28T08:51:21Z",
     "label": "ios-swift-test-videomkcore", "kind": "command", "passed": 402, "failed": 0, "skipped": None, "errors": 0,
     "result": "pass", "scope": "swift test in VideoMKCore", "by": "unknown (agent, per doc)"},
    {"doc": "docs/WHITEBOARD_PHASE_1A_2026-11-27.md table", "sha": "9ad0c6b", "ts": "2026-11-27T16:17:42Z",
     "label": "whiteboard-object-library-quality-gate", "kind": "manual", "passed": 354, "failed": 18, "skipped": None, "errors": 0,
     "result": "pass", "scope": "object library quality gate: 354 objects accepted, 18 dropped after three tries (420 attempts, 66 rejections)",
     "by": "unknown (agent, per doc)"},
]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=E.REPO_ROOT)
    a = ap.parse_args(argv)
    have = {(r.get("label"), r.get("doc")) for r in E.read_ledger(a.root)}
    n = 0
    for e in ENTRIES:
        if (e["label"], e["doc"]) in have:
            continue
        full = E._git(a.root, "rev-parse", e["sha"]) or e["sha"]
        rec = dict(e, sha=full, branch="unknown", dirty=None, source="backfill", caveat=CAVEAT,
                   command=None, exit_code=None, python=None, os=None, keep=False, release=False)
        E.append_record(a.root, rec)
        n += 1
    print(f"backfilled {n} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())
