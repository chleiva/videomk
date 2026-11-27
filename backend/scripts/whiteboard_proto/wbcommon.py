"""Shared paths and the spend log of the whiteboard prototype (docs/WHITEBOARD_PROTOTYPE_2026-11-27.md).

Everything generated (art, audio, frames, videos, the spend log) lives OUTSIDE the repository, under WB_WORK
(default ~/Downloads/videomk-whiteboard/_work). Only code, the bundled OFL font and the doc are in git.
"""
import datetime
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.expanduser(os.environ.get("WB_OUT", "~/Downloads/videomk-whiteboard"))
WORK = os.path.expanduser(os.environ.get("WB_WORK", os.path.join(OUT, "_work")))
ART = os.path.join(WORK, "art")
AUDIO = os.path.join(WORK, "audio")
SPEND_LOG = os.path.join(WORK, "spend_log.jsonl")
SPEND_CAP_USD = 3.0
FONT = os.path.join(HERE, "fonts", "PatrickHand-Regular.ttf")

for d in (OUT, WORK, ART, AUDIO):
    os.makedirs(d, exist_ok=True)


def spent() -> float:
    if not os.path.exists(SPEND_LOG):
        return 0.0
    return sum(json.loads(line)["usd"] for line in open(SPEND_LOG) if line.strip())


def reserve(what: str, usd: float) -> None:
    """Called BEFORE every paid call: refuses the call when it could pass the cap."""
    if spent() + usd > SPEND_CAP_USD:
        raise RuntimeError(f"{what} (${usd:.3f}) would pass the ${SPEND_CAP_USD:.2f} cap (spent ${spent():.3f})")


def charge(what: str, usd: float, **extra) -> None:
    row = {"ts": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "what": what, "usd": round(usd, 6), **extra}
    with open(SPEND_LOG, "a") as f:
        f.write(json.dumps(row) + "\n")
    print(f"  spend: {what}: ${usd:.4f} (total ${spent():.4f} of ${SPEND_CAP_USD:.2f})")
