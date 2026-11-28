"""Shared helpers for the test-evidence log (stdlib only). See test-evidence/README.md."""
import datetime
import fcntl
import gzip
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys

ZERO = "0" * 64
SCHEMA = 1
ARTIFACT_COPY_MAX = 2 * 1024 * 1024

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

_REDACTIONS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S), "[REDACTED-PRIVATE-KEY]"),
    (re.compile(r"\b(?:AKIA|ASIA|AIDA|AROA)[A-Z0-9]{16}\b"), "[REDACTED-AWS-KEY-ID]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]*"), "[REDACTED-JWT]"),
    (re.compile(r"\b(?:ghp|gho|ghs|ghu|ghr)_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "[REDACTED-GITHUB-TOKEN]"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}"), "[REDACTED-SLACK-TOKEN]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{20,}"), "[REDACTED-API-KEY]"),
    (re.compile(r"(?i)\b(bearer|basic)\s+[A-Za-z0-9._~+/=-]{12,}"), r"\1 [REDACTED]"),
    (re.compile(r"(?i)\b([A-Za-z0-9_.-]*(?:password|passwd|secret|token|api[_-]?key|access[_-]?key|authorization)[A-Za-z0-9_.-]*)(\s*[=:]\s*)(['\"]?)[^\s'\",;]{4,}"),
     r"\1\2\3[REDACTED]"),
    (re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+"), "[REDACTED-EMAIL]"),
]


def redact(text):
    for rx, rep in _REDACTIONS:
        text = rx.sub(rep, text)
    return text


def sha256_bytes(b):
    return hashlib.sha256(b).hexdigest()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(root, *args):
    try:
        r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


def git_info(root):
    sha = _git(root, "rev-parse", "HEAD")
    branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD")
    status = _git(root, "status", "--porcelain", "--", ".", ":(exclude)test-evidence")
    return {"sha": sha or "unknown", "branch": branch or "unknown",
            "dirty": bool(status) if status is not None else None}


def now_utc():
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)


def env_info():
    return {"python": platform.python_version(), "os": f"{platform.system()} {platform.release()} {platform.machine()}"}


def safe_label(label):
    return re.sub(r"[^A-Za-z0-9._-]+", "-", label).strip("-")[:60] or "run"


def evidence_dir(root):
    return os.path.join(root, "test-evidence")


def ledger_path(root):
    return os.path.join(evidence_dir(root), "ledger.jsonl")


def read_ledger_lines(root):
    p = ledger_path(root)
    if not os.path.exists(p):
        return []
    with open(p, "rb") as f:
        data = f.read()
    return [ln for ln in data.split(b"\n") if ln.strip()]


def read_ledger(root):
    return [json.loads(ln) for ln in read_ledger_lines(root)]


def parse_pytest_summary(text):
    """Counts from a pytest summary line, plus the names of failed/errored tests."""
    counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
    found = False
    for line in text.splitlines():
        line = line.strip().strip("=").strip()
        if not re.search(r"\bin [0-9.]+s\b", line):
            continue
        hits = re.findall(r"(\d+) (passed|failed|skipped|errors?|xfailed|xpassed|deselected|warnings?)", line)
        if not hits:
            continue
        found = True
        counts = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}
        for n, k in hits:
            if k in ("passed", "failed", "skipped"):
                counts[k] += int(n)
            elif k.startswith("error"):
                counts["errors"] += int(n)
    failed = sorted({m.group(2).split(" - ")[0].strip() for m in
                     re.finditer(r"^(FAILED|ERROR) (\S.*)$", text, re.M)})
    return (counts if found else None), failed


def append_record(root, record, log_text=None, write_log=False, artifacts=()):
    """Append one evidence record (hash chained). Returns the record as written."""
    ts = now_utc()
    record = dict(record)
    record.setdefault("schema", SCHEMA)
    record.setdefault("ts", ts.strftime("%Y-%m-%dT%H:%M:%SZ"))
    when = datetime.datetime.strptime(record["ts"], "%Y-%m-%dT%H:%M:%SZ")
    ev = evidence_dir(root)
    os.makedirs(ev, exist_ok=True)
    if log_text is not None:
        log_text = redact(log_text)
        raw = log_text.encode("utf-8", "replace")
        record["output_sha256"] = sha256_bytes(raw)
        record["output_bytes"] = len(raw)
        if write_log:
            sub = os.path.join("runs", when.strftime("%Y"), when.strftime("%m"))
            os.makedirs(os.path.join(ev, sub), exist_ok=True)
            name = f"{when.strftime('%Y%m%dT%H%M%SZ')}_{record['sha'][:7]}_{safe_label(record['label'])}.log.gz"
            rel = os.path.join(sub, name)
            n = 1
            while os.path.exists(os.path.join(ev, rel)):
                rel = rel.replace(".log.gz", f"_{n}.log.gz"); n += 1
            with open(os.path.join(ev, rel), "wb") as f:
                with gzip.GzipFile(fileobj=f, mode="wb", mtime=0) as gz:
                    gz.write(raw)
            record["log"] = rel.replace(os.sep, "/")
            record["log_sha256"] = sha256_file(os.path.join(ev, rel))
        else:
            record["log"] = None
    arts = []
    for a in artifacts:
        entry = {"name": os.path.basename(a), "sha256": sha256_file(a), "bytes": os.path.getsize(a), "stored": None}
        if entry["bytes"] <= ARTIFACT_COPY_MAX:
            sub = os.path.join("artifacts", when.strftime("%Y"), when.strftime("%m"))
            os.makedirs(os.path.join(ev, sub), exist_ok=True)
            rel = os.path.join(sub, f"{entry['sha256'][:12]}_{os.path.basename(a)}")
            shutil.copyfile(a, os.path.join(ev, rel))
            entry["stored"] = rel.replace(os.sep, "/")
        arts.append(entry)
    if arts:
        record["artifacts"] = arts
    lp = ledger_path(root)
    with open(lp, "ab+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.seek(0)
        lines = [ln for ln in f.read().split(b"\n") if ln.strip()]
        record["prev"] = sha256_bytes(lines[-1]) if lines else ZERO
        f.seek(0, 2)
        f.write(json.dumps(record, sort_keys=True, separators=(",", ":")).encode() + b"\n")
        f.flush()
        os.fsync(f.fileno())
    return record


def verify(root):
    """Return (errors, count, head_hash)."""
    errors = []
    lines = read_ledger_lines(root)
    prev = ZERO
    ev = evidence_dir(root)
    for i, ln in enumerate(lines, 1):
        try:
            rec = json.loads(ln)
        except ValueError:
            errors.append(f"line {i}: not valid JSON")
            prev = sha256_bytes(ln)
            continue
        if rec.get("prev") != prev:
            errors.append(f"line {i}: hash chain broken (previous line altered, removed or reordered)")
        prev = sha256_bytes(ln)
        log = rec.get("log")
        if log:
            p = os.path.join(ev, log)
            if not os.path.exists(p):
                errors.append(f"line {i}: log file missing: {log}")
            elif sha256_file(p) != rec.get("log_sha256"):
                errors.append(f"line {i}: log file hash mismatch: {log}")
            else:
                try:
                    with gzip.open(p, "rb") as g:
                        if sha256_bytes(g.read()) != rec.get("output_sha256"):
                            errors.append(f"line {i}: decompressed output hash mismatch: {log}")
                except Exception as e:
                    errors.append(f"line {i}: log unreadable: {log} ({e})")
        for a in rec.get("artifacts", []):
            if a.get("stored"):
                p = os.path.join(ev, a["stored"])
                if not os.path.exists(p):
                    errors.append(f"line {i}: artifact missing: {a['stored']}")
                elif sha256_file(p) != a.get("sha256"):
                    errors.append(f"line {i}: artifact hash mismatch: {a['stored']}")
    return errors, len(lines), prev
