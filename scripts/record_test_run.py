#!/usr/bin/env python3
"""Run a test command and append an immutable evidence record (see test-evidence/README.md).

  scripts/record_test_run.py --by agent-x --label backend-unit                  # default pytest in backend/
  scripts/record_test_run.py --by me --label cdk-synth -- cdk synth             # any command
  scripts/record_test_run.py --by me --label qa-video --manual --result pass \
        --notes "watched 3 videos" --artifact report.png
Raw output (redacted, gzip) is kept for failures, --keep and --release (or VMK_RELEASE=1) runs; otherwise only the summary.
"""
import argparse
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evidence_lib as E  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--by", required=True, help="who/what ran it: a user name or an agent label")
    ap.add_argument("--label", default="backend-pytest", help="suite / verification name")
    ap.add_argument("--keep", action="store_true", help="store the raw output even if it passed")
    ap.add_argument("--release", action="store_true", help="release run: store the raw output (also VMK_RELEASE=1)")
    ap.add_argument("--manual", action="store_true", help="record a non-command verification")
    ap.add_argument("--result", choices=["pass", "fail"], help="with --manual")
    ap.add_argument("--notes", default="", help="free text (redacted)")
    ap.add_argument("--artifact", action="append", default=[], help="file to hash (and copy when small)")
    ap.add_argument("--root", default=E.REPO_ROOT, help=argparse.SUPPRESS)
    ap.add_argument("--cwd", default=None, help="directory to run the command in")
    ap.add_argument("command", nargs=argparse.REMAINDER)
    a = ap.parse_args(argv)
    cmd = a.command[1:] if a.command[:1] == ["--"] else a.command

    release = a.release or os.environ.get("VMK_RELEASE") == "1"
    rec = {"by": a.by, "label": a.label, "source": "live", **E.git_info(a.root), **E.env_info(),
           "keep": a.keep, "release": release}
    if a.notes:
        rec["notes"] = E.redact(a.notes)
    for p in a.artifact:
        if not os.path.isfile(p):
            ap.error(f"artifact not found: {p}")

    if a.manual:
        if not a.result:
            ap.error("--manual needs --result pass|fail")
        rec.update(kind="manual", command=None, result=a.result, exit_code=0 if a.result == "pass" else 1)
        out = E.append_record(a.root, rec, log_text=None, artifacts=a.artifact)
        print(f"recorded manual {a.result}: {a.label}")
        return 0

    default_pytest = not cmd
    if default_pytest:
        cmd = [sys.executable, "-m", "pytest", "-q", "-rfE"]
        cwd = a.cwd or os.path.join(a.root, "backend")
    else:
        cwd = a.cwd or os.getcwd()
    is_pytest = default_pytest or any("pytest" in c for c in cmd[:3])
    env = dict(os.environ, VMK_EVIDENCE_WRAPPED="1")
    t0 = time.time()
    proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, errors="replace")
    dur = round(time.time() - t0, 2)
    text = proc.stdout + (("\n--- stderr ---\n" + proc.stderr) if proc.stderr else "")
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)

    counts, failed = (E.parse_pytest_summary(text) if is_pytest else (None, []))
    rec.update(kind="pytest" if is_pytest else "command", command=" ".join(cmd), exit_code=proc.returncode,
               result="pass" if proc.returncode == 0 else "fail", duration_s=dur,
               failed_tests=failed[:200])
    if counts:
        rec.update(counts)
    store = proc.returncode != 0 or a.keep or release
    out = E.append_record(a.root, rec, log_text=text, write_log=store, artifacts=a.artifact)
    print(f"\n[evidence] {out['result']} recorded in test-evidence/ledger.jsonl"
          + (f" (raw log {out['log']})" if out.get("log") else " (summary only)"), file=sys.stderr)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main())
