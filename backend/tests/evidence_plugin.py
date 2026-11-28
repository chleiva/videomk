"""Opt-in evidence record for a plain `pytest` run (off by default).

Turn on with `pytest --evidence` or VMK_EVIDENCE=1 (CI/release runs set it; release also VMK_RELEASE=1 to keep
the raw log). Skipped when scripts/record_test_run.py wraps the run (it sets VMK_EVIDENCE_WRAPPED=1).
The stored log is a compact per-test outcome list (names, outcomes), not the full terminal output.
"""
import os
import sys
import time

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_START = {}


def pytest_addoption(parser):
    parser.addoption("--evidence", action="store_true", default=False,
                     help="append a test-evidence ledger record for this run (or set VMK_EVIDENCE=1)")


def _enabled(config):
    if os.environ.get("VMK_EVIDENCE_WRAPPED") == "1":
        return False
    return bool(config.getoption("--evidence", default=False)) or os.environ.get("VMK_EVIDENCE") == "1"


def pytest_sessionstart(session):
    _START["t"] = time.time()


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    if not _enabled(config):
        return
    sys.path.insert(0, os.path.join(_ROOT, "scripts"))
    import evidence_lib as E
    st = terminalreporter.stats
    n = lambda k: len(st.get(k, []))
    lines, failed = [], []
    for kind in ("passed", "failed", "error", "skipped", "xfailed", "xpassed"):
        for rep in st.get(kind, []):
            lines.append(f"{kind.upper():8} {getattr(rep, 'nodeid', '?')}")
            if kind in ("failed", "error"):
                failed.append(getattr(rep, "nodeid", "?"))
    release = os.environ.get("VMK_RELEASE") == "1"
    rec = {"by": os.environ.get("VMK_EVIDENCE_BY", "ci" if os.environ.get("CI") else os.environ.get("USER", "unknown")),
           "label": os.environ.get("VMK_EVIDENCE_LABEL", "backend-pytest"), "source": "live", "kind": "pytest",
           **E.git_info(_ROOT), **E.env_info(), "keep": False, "release": release,
           "command": "pytest " + " ".join(config.invocation_params.args),
           "exit_code": int(exitstatus), "result": "pass" if int(exitstatus) == 0 else "fail",
           "duration_s": round(time.time() - _START.get("t", time.time()), 2),
           "passed": n("passed"), "failed": n("failed"), "skipped": n("skipped"), "errors": n("error"),
           "failed_tests": sorted(failed)[:200], "recorded_by_plugin": True}
    out = E.append_record(_ROOT, rec, log_text="\n".join(lines) + "\n", write_log=(int(exitstatus) != 0 or release))
    terminalreporter.write_line(f"[evidence] recorded {out['result']} in test-evidence/ledger.jsonl")
