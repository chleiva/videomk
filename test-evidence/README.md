# Test evidence log

Purpose: every quality test, unit test and verification we run stays as a permanent, tamper-evident record in the repo,
for audit (SOC2 / ISO 27001 style evidence: what was tested, when, on which commit, by whom, with what result).

## What is here

| Path | What |
|---|---|
| `ledger.jsonl` | Append-only, one JSON line per run. Each line carries `prev` = sha256 of the previous line (hash chain). |
| `runs/YYYY/MM/<utc>_<sha7>_<label>.log.gz` | Raw output (redacted, gzip). Only for failures, `--keep` and release runs. |
| `artifacts/YYYY/MM/` | Small files attached to manual records (copies, up to 2 MB; larger ones are only hashed). |
| `INDEX.md` | Generated human-readable summary. Never edit by hand. |

A record holds: UTC timestamp, commit sha, branch, dirty flag (ignoring `test-evidence/`), `by` (person or agent label),
command, Python and OS, counts (passed / failed / skipped / errors), duration, failed test names, exit code, result,
`output_sha256` (hash of the stored, redacted output), `source` (`live` or `backfill`), and for manual records notes
and artifact hashes. Secrets are redacted before anything is written (AWS key ids, JWTs, bearer tokens, GitHub/Slack/API
keys, private keys, `password=`/`token=`-style values, email addresses).

## How to record

```
scripts/record_test_run.py --by <agent-or-user> --label backend-pytest                 # default: pytest in backend/
scripts/record_test_run.py --by <who> --label cdk-synth -- cdk synth                    # any command (after --)
scripts/record_test_run.py --by <who> --label web-vitest --keep -- npm test             # --keep stores the raw log
scripts/record_test_run.py --by <who> --label qa-video-check --manual --result pass \
    --notes "3 videos watched, audio in sync" --artifact path/to/report.png            # non-command verification
```

The wrapper passes the command's exit code through. Release runs: add `--release` (or `VMK_RELEASE=1`).

A plain `pytest` run can write its own record without the wrapper: `pytest --evidence` or `VMK_EVIDENCE=1`
(optional `VMK_EVIDENCE_BY`, `VMK_EVIDENCE_LABEL`). Off by default so local iteration does not spam the repo; CI and
release runs set `VMK_EVIDENCE=1` (and `VMK_RELEASE=1` for releases). The plugin's log is a per-test outcome list,
not the full terminal output. The wrapper sets `VMK_EVIDENCE_WRAPPED=1` so a run is never recorded twice.

## How to verify

```
scripts/verify_test_evidence.py      # exit 0 intact, exit 1 on tampering
scripts/test_evidence_index.py       # regenerate INDEX.md
```

Verification checks the hash chain (edited, deleted, inserted or reordered lines), the hash of every stored log and
artifact, and that each log decompresses to its `output_sha256`. `backend/tests/test_test_evidence.py` also checks the
committed ledger on every normal test run.

Limit: a hash chain cannot detect removal of the newest lines or a full rewrite of the whole chain. Git history is the
second control: commit evidence with the work, protect the branch, and record the head hash printed by the verifier in
release notes when you want an external anchor.

## Retention and policy

- Summaries (the ledger line) are kept forever. Raw logs are kept forever too; they are small (gzip) and only written for
  failures, `--keep` and release runs.
- Rough growth: ledger line about 0.7 KB, so 20 recorded runs a day is about 5 MB a year; raw logs maybe 5 to 20 MB a year.
  If it ever matters, move old `runs/YYYY/` folders to cold storage but keep their ledger lines and hashes in the repo.
- Never edit or delete ledger lines or logs. Mistakes are corrected by appending a new record (a manual one with notes).
- Backfilled entries (`source: backfill`) are reconstructions from docs, flagged with a `caveat`; they are not original evidence.

## Who may write

Anyone or any agent who runs a test, through `scripts/record_test_run.py`, with an honest `--by`. Evidence files are
committed together with the work they cover. Do not write to the ledger by hand.
