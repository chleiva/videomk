import json
import os
import subprocess
import sys

import pytest

SCRIPTS = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
sys.path.insert(0, SCRIPTS)
import evidence_lib as E  # noqa: E402
import record_test_run  # noqa: E402
import test_evidence_index  # noqa: E402
import verify_test_evidence  # noqa: E402


@pytest.fixture
def root(tmp_path):
    return str(tmp_path)


def rec(root, argv):
    return record_test_run.main(["--root", root, *argv])


def test_redaction_patterns():
    text = ("key AKIAABCDEFGHIJKLMNOP and mail bob.smith@example.com\n"
            "Authorization: Bearer abcdefghijklmnop1234\ntoken=supersecretvalue99\n"
            "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcDEF123_-xyz\n"
            "ghp_abcdefghijklmnopqrstuvwxyz0123456789\nsk-abcdefghijklmnopqrstuvwxyz\n"
            "-----BEGIN RSA PRIVATE KEY-----\nMIIBOgIBAAJB\n-----END RSA PRIVATE KEY-----\n")
    out = E.redact(text)
    for leak in ["AKIAABCDEFGHIJKLMNOP", "bob.smith@example.com", "abcdefghijklmnop1234", "supersecretvalue99",
                 "eyJzdWIi", "ghp_abcdef", "sk-abcdef", "MIIBOgIBAAJB"]:
        assert leak not in out
    assert "REDACTED" in out


def test_parse_pytest_summary():
    text = "FAILED tests/test_a.py::test_x - assert 1 == 2\nERROR tests/test_b.py::test_y\n== 2 failed, 10 passed, 1 skipped, 1 error in 3.21s ==\n"
    counts, failed = E.parse_pytest_summary(text)
    assert counts == {"passed": 10, "failed": 2, "skipped": 1, "errors": 1}
    assert failed == ["tests/test_a.py::test_x", "tests/test_b.py::test_y"]
    assert E.parse_pytest_summary("nothing here")[0] is None


def test_record_command_pass_summary_only_and_chain(root, capsys):
    assert rec(root, ["--by", "unit", "--label", "echo", "--", sys.executable, "-c", "print('ok')"]) == 0
    assert rec(root, ["--by", "unit", "--label", "echo", "--", sys.executable, "-c", "print('ok2')"]) == 0
    recs = E.read_ledger(root)
    assert len(recs) == 2 and recs[0]["prev"] == E.ZERO
    assert recs[0]["log"] is None  # passed, not kept: summary only
    assert recs[0]["by"] == "unit" and recs[0]["result"] == "pass" and recs[0]["output_sha256"]
    assert not os.path.exists(os.path.join(root, "test-evidence", "runs"))
    for k in ("ts", "sha", "branch", "dirty", "python", "os", "command", "duration_s", "exit_code"):
        assert k in recs[0]
    assert verify_test_evidence.main(["--root", root]) == 0


def test_failure_and_keep_store_gzip_log_redacted(root):
    code = "import sys;print('mail me@corp.io');sys.exit(3)"
    assert rec(root, ["--by", "u", "--label", "bad", "--", sys.executable, "-c", code]) == 3
    assert rec(root, ["--by", "u", "--label", "kept", "--keep", "--", sys.executable, "-c", "print('hi')"]) == 0
    a, b = E.read_ledger(root)
    assert a["result"] == "fail" and a["log"].endswith(".log.gz") and "/runs/" not in a["log"][:1]
    assert b["log"]
    import gzip
    with gzip.open(os.path.join(root, "test-evidence", a["log"])) as g:
        body = g.read().decode()
    assert "me@corp.io" not in body and "REDACTED-EMAIL" in body
    assert verify_test_evidence.main(["--root", root]) == 0


def test_real_pytest_counts_and_failed_names(root, tmp_path):
    t = tmp_path / "sub"
    t.mkdir()
    (t / "test_x.py").write_text("def test_a():\n    pass\ndef test_b():\n    assert 0\n")
    rc = rec(root, ["--by", "u", "--label", "p", "--cwd", str(t), "--", sys.executable, "-m", "pytest", "-q", "-rfE", "-p", "no:cacheprovider", "test_x.py"])
    assert rc != 0
    r = E.read_ledger(root)[0]
    assert (r["passed"], r["failed"]) == (1, 1) and r["failed_tests"] == ["test_x.py::test_b"]
    assert r["log"]


def test_manual_record_with_artifact(root, tmp_path):
    art = tmp_path / "shot.txt"
    art.write_text("evidence")
    assert rec(root, ["--by", "me", "--label", "qa-video", "--manual", "--result", "pass", "--notes", "ok token=abcd1234efgh", "--artifact", str(art)]) == 0
    r = E.read_ledger(root)[0]
    assert r["kind"] == "manual" and r["result"] == "pass" and "abcd1234efgh" not in r["notes"]
    assert r["artifacts"][0]["sha256"] == E.sha256_file(str(art)) and r["artifacts"][0]["stored"]
    assert verify_test_evidence.main(["--root", root]) == 0
    with pytest.raises(SystemExit):
        rec(root, ["--by", "me", "--manual"])  # needs --result


def _three(root):
    rec(root, ["--by", "u", "--label", "a", "--keep", "--", sys.executable, "-c", "print(1)"])
    rec(root, ["--by", "u", "--label", "a", "--", sys.executable, "-c", "print(2)"])
    rec(root, ["--by", "u", "--label", "a", "--", sys.executable, "-c", "print(3)"])


def test_verify_detects_edited_line(root, capsys):
    _three(root)
    p = E.ledger_path(root)
    s = open(p).read().replace('"by":"u"', '"by":"x"', 1)
    open(p, "w").write(s)
    assert verify_test_evidence.main(["--root", root]) == 1


def test_verify_detects_deleted_and_reordered_line(root):
    _three(root)
    p = E.ledger_path(root)
    lines = open(p).read().splitlines()
    open(p, "w").write("\n".join([lines[0], lines[2]]) + "\n")
    assert verify_test_evidence.main(["--root", root]) == 1
    open(p, "w").write("\n".join([lines[1], lines[0], lines[2]]) + "\n")
    assert verify_test_evidence.main(["--root", root]) == 1


def test_verify_detects_log_tampering_and_missing(root):
    _three(root)
    log = os.path.join(root, "test-evidence", E.read_ledger(root)[0]["log"])
    with open(log, "ab") as f:
        f.write(b"x")
    assert verify_test_evidence.main(["--root", root]) == 1
    os.remove(log)
    assert verify_test_evidence.main(["--root", root]) == 1


def test_verify_detects_artifact_tampering(root, tmp_path):
    art = tmp_path / "a.txt"
    art.write_text("one")
    rec(root, ["--by", "u", "--label", "m", "--manual", "--result", "pass", "--artifact", str(art)])
    stored = os.path.join(root, "test-evidence", E.read_ledger(root)[0]["artifacts"][0]["stored"])
    open(stored, "w").write("two")
    assert verify_test_evidence.main(["--root", root]) == 1


def test_empty_ledger_verifies(root):
    assert verify_test_evidence.main(["--root", root]) == 0


def test_index_generation(root):
    _three(root)
    rec(root, ["--by", "u", "--label", "b", "--manual", "--result", "fail"])
    test_evidence_index.main(["--root", root])
    md = open(os.path.join(root, "test-evidence", "INDEX.md")).read()
    assert "## a" in md and "## b" in md and "Pass rate" in md


def test_plugin_off_by_default_and_on_with_flag(tmp_path):
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    ledger = os.path.join(repo, "test-evidence", "ledger.jsonl")
    before = os.path.getsize(ledger) if os.path.exists(ledger) else 0
    # a throwaway project that loads only the plugin, writing into a temp root via a copied scripts dir
    proj = tmp_path / "proj"
    (proj / "backend" / "tests").mkdir(parents=True)
    (proj / "scripts").mkdir()
    for f in os.listdir(SCRIPTS):
        if f.endswith(".py"):
            (proj / "scripts" / f).write_bytes(open(os.path.join(SCRIPTS, f), "rb").read())
    (proj / "backend" / "tests" / "evidence_plugin.py").write_bytes(open(os.path.join(os.path.dirname(__file__), "evidence_plugin.py"), "rb").read())
    (proj / "backend" / "tests" / "test_t.py").write_text("def test_ok():\n    pass\n")
    env = {k: v for k, v in os.environ.items() if not k.startswith("VMK_")}
    base = [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "-p", "tests.evidence_plugin", "backend/tests"]
    run = lambda extra, e=env: subprocess.run(base[:3] + extra + base[3:], cwd=proj, env={**e, "PYTHONPATH": str(proj / "backend")}, capture_output=True, text=True)
    r = run([])
    assert r.returncode == 0 and not (proj / "test-evidence").exists()
    r = run(["--evidence"])
    assert r.returncode == 0, r.stdout + r.stderr
    recs = E.read_ledger(str(proj))
    assert len(recs) == 1 and recs[0]["passed"] == 1 and recs[0]["recorded_by_plugin"]
    r = run([], {**env, "VMK_EVIDENCE": "1"})
    assert len(E.read_ledger(str(proj))) == 2
    r = run([], {**env, "VMK_EVIDENCE": "1", "VMK_EVIDENCE_WRAPPED": "1"})
    assert len(E.read_ledger(str(proj))) == 2  # wrapper owns the record
    assert (os.path.getsize(ledger) if os.path.exists(ledger) else 0) == before
    assert E.verify(str(proj))[0] == []


def test_repo_ledger_is_intact():
    """The committed ledger must always verify (this is the tamper alarm in normal test runs)."""
    repo = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    errors, _, _ = E.verify(repo)
    assert errors == []
