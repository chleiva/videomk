"""The brand is written "VideoMK" wherever a person reads it (docs/BRAND.md). This reads every string literal of the backend's own code
(comments and docstrings are not text a person is shown) and fails on another spelling.

Lowercase "videomk" stays only in identifiers: videomk.com, hello@videomk.com, com.videomk.app, AWS names (videomk-qa-...), secret paths
(videomk/qa/...), i18n keys (wm.mode.videomk) and a string that is exactly "videomk" (the watermark mode id, the mail marker).
backend/lambdas/engine is checked too, with the lines its own agent still has to change listed in ENGINE_PENDING (empty it when done).
"""
import ast
import os
import re

BACKEND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
WRONG = re.compile(r"(?<![\w@./:\-])videomk(?![\w]|[.\-_/:]\w)", re.I)
SKIP_DIRS = {"tests", "cdk.out", "__pycache__", ".venv", "node_modules", "music-draft", "whiteboard_proto"}
# engine strings another agent owns right now (2026-11-27): remove each entry as it is fixed there
ENGINE_PENDING: set = set()   # emptied 2026-11-27: the closing card, the watermark message, the clip credits and the language refusal say VideoMK
# data labels, not sentences: stored with catalog items and compared as written
DATA_LABELS = {("lambdas/common/catalog.py", "videomk library")}


def mistakes(source: str):
    """[(line, text)] of string literals that write the brand another way. Docstrings are skipped."""
    tree = ast.parse(source)
    docs = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
                docs.add(id(first.value))
    out, parts = [], set()
    for node in ast.walk(tree):   # an f-string is read whole, each {value} standing as a letter: f"videomk-{stage}" is a name, f"{who} via videomk" is not
        if isinstance(node, ast.JoinedStr):
            parts.update(id(v) for v in node.values)
            text = "".join(v.value if isinstance(v, ast.Constant) and isinstance(v.value, str) else "X" for v in node.values)
            if WRONG.search(text.replace("VideoMK", "")):
                out.append((node.lineno, text))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docs and id(node) not in parts:
            text = node.value
            if text.strip() == "videomk":
                continue
            if WRONG.search(text.replace("VideoMK", "")):
                out.append((node.lineno, text))
    return sorted(out)


def _files():
    for base, dirs, names in os.walk(BACKEND):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".") and not d.startswith("cdk.out")]
        for n in names:
            if n.endswith(".py"):
                yield os.path.join(base, n)


def test_the_check_knows_a_name_from_an_identifier():
    assert mistakes('x = "Made with videomk"') == [(1, "Made with videomk")]
    assert mistakes('x = f"{who} via Videomk"')[0][0] == 1 and mistakes('x = f"videomk-{stage}-{acct}"') == []
    assert mistakes('x = "videomk"\ny = "VideoMK at videomk.com, hello@videomk.com, videomk-qa-media, videomk/qa/key, wm.mode.videomk"') == []
    assert mistakes('def f():\n    """videomk helper."""\n    return 1  # videomk') == []


def test_every_string_a_person_reads_says_VideoMK():
    found = []
    for path in _files():
        rel = os.path.relpath(path, BACKEND)
        try:
            bad = mistakes(open(path, encoding="utf-8").read())
        except SyntaxError:
            continue
        for line, text in bad:
            if (rel, text) in ENGINE_PENDING or (rel, text) in DATA_LABELS:
                continue
            found.append(f"{rel}:{line}: {text[:90]!r}")
    assert found == []
