"""Slides to images. pptx: LibreOffice Impress headless converts to PDF (hard timeout, scrubbed environment, throwaway profile and temp dir, resource limits), then
poppler's pdftoppm draws each page. pdf: pdftoppm directly. Animations and transitions are ignored by the conversion: every slide is its final state."""
import os
import resource
import shutil
import subprocess
import tempfile
from typing import Any, Dict, List, Optional

from deck_safe import DeckError

SOFFICE = os.environ.get("SOFFICE_BIN", "soffice")
CONVERT_TIMEOUT_S = int(os.environ.get("DECK_CONVERT_TIMEOUT_S", "240"))
RASTER_TIMEOUT_S = int(os.environ.get("DECK_RASTER_TIMEOUT_S", "180"))
SLIDE_WIDTH_PX = int(os.environ.get("DECK_SLIDE_WIDTH_PX", "2560"))   # a 4K frame shows the slide at most about 3400 px wide; 2560 keeps text crisp at 1080p and acceptable at 4K


def _limits():
    """Applied in the child before exec: no core files, bounded CPU time, file size and open files. (Address-space limits break LibreOffice's own startup, so the memory
    bound is the function's configured memory; the network bound is the function's subnet, which has no route out: docs/DECK_TO_VIDEO.md.)"""
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_CPU, (CONVERT_TIMEOUT_S + 30, CONVERT_TIMEOUT_S + 30))
    resource.setrlimit(resource.RLIMIT_FSIZE, (1 << 30, 1 << 30))
    resource.setrlimit(resource.RLIMIT_NOFILE, (512, 512))
    os.setsid()


def _env(home: str) -> Dict[str, str]:
    """No AWS credentials, no proxy variables, nothing inherited from the function."""
    return {"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": home, "LANG": "C.UTF-8", "TMPDIR": home, "SAL_USE_VCLPLUGIN": "svp", "SAL_DISABLE_OPENCL": "1"}


def _run(cmd: List[str], cwd: str, timeout: int, env: Dict[str, str]) -> subprocess.CompletedProcess:
    p = subprocess.Popen(cmd, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, preexec_fn=_limits)
    try:
        out, err = p.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, 9)
        except Exception:
            p.kill()
        p.communicate()
        raise DeckError("deck_convert_timeout", f"{os.path.basename(cmd[0])} exceeded {timeout}s")
    return subprocess.CompletedProcess(cmd, p.returncode, out, err)


def pdf_pages(pdf: str, cwd: str, env: Dict[str, str]) -> int:
    r = _run(["pdfinfo", pdf], cwd, 30, env)
    for line in r.stdout.decode("utf-8", "replace").splitlines():
        if line.startswith("Pages:"):
            return int(line.split()[1])
    if b"Incorrect password" in r.stderr or b"Encrypted" in r.stdout:
        raise DeckError("deck_encrypted", "pdf asks for a password")
    raise DeckError("deck_corrupt", "pdfinfo could not read the pdf")


def pptx_to_pdf(pptx_path: str, work: str) -> str:
    home = os.path.join(work, "home")
    os.makedirs(home, exist_ok=True)
    profile = "file://" + os.path.join(home, "lo_profile")
    r = _run([SOFFICE, f"-env:UserInstallation={profile}", "--headless", "--norestore", "--nolockcheck", "--nodefault", "--nologo", "--convert-to", "pdf:impress_pdf_Export",
              "--outdir", work, pptx_path], work, CONVERT_TIMEOUT_S, _env(home))
    pdf = os.path.join(work, os.path.splitext(os.path.basename(pptx_path))[0] + ".pdf")
    if not os.path.exists(pdf) or os.path.getsize(pdf) < 200:
        raise DeckError("deck_convert_failed", f"soffice exit {r.returncode}")
    return pdf


def rasterize(pdf: str, work: str, max_pages: int, width_px: int = SLIDE_WIDTH_PX, fmt: str = "png") -> List[str]:
    env = _env(os.path.join(work, "home"))
    n = pdf_pages(pdf, work, env)
    if n < 1:
        raise DeckError("deck_empty", "no pages")
    if n > max_pages:
        raise DeckError("deck_too_many_slides", f"{n} pages")
    out = os.path.join(work, "slide")
    r = _run(["pdftoppm", f"-{fmt}", "-scale-to-x", str(width_px), "-scale-to-y", "-1", "-f", "1", "-l", str(n), pdf, out], work, RASTER_TIMEOUT_S, env)
    files = sorted(f for f in os.listdir(work) if f.startswith("slide-") and f.endswith("." + fmt))
    if r.returncode != 0 or not files:
        raise DeckError("deck_convert_failed", f"pdftoppm exit {r.returncode}")
    return [os.path.join(work, f) for f in files]


def pdf_text(pdf: str, work: str, n: int) -> List[str]:
    env = _env(os.path.join(work, "home"))
    out = []
    for i in range(1, n + 1):
        r = _run(["pdftotext", "-f", str(i), "-l", str(i), "-layout", "-enc", "UTF-8", pdf, "-"], work, 30, env)
        out.append(r.stdout.decode("utf-8", "replace")[:20000])
    return out


def make_workdir() -> str:
    return tempfile.mkdtemp(prefix="deck_", dir=os.environ.get("DECK_TMP", None))


def cleanup(work: str) -> None:
    shutil.rmtree(work, ignore_errors=True)
