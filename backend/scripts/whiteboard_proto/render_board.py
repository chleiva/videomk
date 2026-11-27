#!/usr/bin/env python3
"""Render a board spec (docs/WHITEBOARD_BOARD_SPEC.md) to video: any aspect, any size up to 4K, any passage. Deterministic and chunkable.

  AWS_PROFILE=qa render_board.py boards/photosynthesis.json [--lang es] [--aspect 9:16] [--size 1080x1920] [--from S --to S] [--out FILE] [--still T] [--music] [--no-tip]

The narration is synthesised once per (text, voice) with the engine's TTS and word alignment (narrate.py) and cached; everything else is a pure function
of the spec, the word times, the aspect and the size. `--from/--to` renders a passage alone: that is a chunk.
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "..", "lambdas"))
import board as bd  # noqa: E402
import boardspec as bs  # noqa: E402
import wbcommon as common  # noqa: E402
import narrate  # noqa: E402

FPS = 30
DEFAULT_SIZE = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350)}
MUSIC = os.path.join(HERE, "..", "..", "music-draft", "calm-pad-dawn.mp3")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("spec")
    ap.add_argument("--lang", default="")
    ap.add_argument("--aspect", default="16:9")
    ap.add_argument("--size", default="")
    ap.add_argument("--from", dest="t0", type=float, default=0.0)
    ap.add_argument("--to", dest="t1", type=float, default=None)
    ap.add_argument("--out", default="")
    ap.add_argument("--still", type=float, default=None)
    ap.add_argument("--music", action="store_true")
    ap.add_argument("--no-tip", action="store_true")
    ap.add_argument("--theme", default="")
    ap.add_argument("--hand", default="", help="override the board's default handwriting: neat | casual")
    ap.add_argument("--tool", default="", help="override the board's default writing tool: pen | marker")
    ap.add_argument("--tag", default="")
    a = ap.parse_args()
    spec = bs.load_spec(a.spec)
    if a.theme:
        spec["theme"] = a.theme
    if a.hand:
        spec["hand"] = a.hand
    if a.tool:
        spec["tool"] = a.tool
    lang = a.lang or spec.get("lang", "en")
    loc = (spec.get("i18n") or {}).get(lang, {}) if lang != spec.get("lang", "en") else {}
    sentences, voice = loc.get("narration", spec["narration"]), loc.get("voice", spec.get("voice", "Ruth"))
    wav, words = narrate.synth(sentences, voice, f"{spec['id']}_{lang}")
    size = tuple(map(int, a.size.split("x"))) if a.size else DEFAULT_SIZE[a.aspect]
    t0 = time.time()
    b, cam, dur, report = bs.compile_board(spec, words, a.aspect, size, lang if loc else None)
    report["compile_s"] = round(time.time() - t0, 1)
    tag = f"{spec['id']}_{lang}_{a.aspect.replace(':', 'x')}_{size[1]}p" + ("_chalk" if spec.get("theme") == "chalk" else "") + (("_" + a.tag) if a.tag else "")
    print(f"{tag}: compiled in {report['compile_s']} s; pen busy {report['pen_busy_share'] * 100:.0f} %, longest idle {report['longest_idle_s']} s, idle over 1.5 s (at, length) {report['idle_over_1_5s']}, late {[x for x in report['late'] if x[1] > 0.25]}, warnings {report['warnings']}")
    if a.still is not None:
        out = a.out or os.path.join(common.WORK, f"{tag}_{a.still:.1f}.jpg")
        b.frame(a.still if a.still >= 0 else dur, cam.at(a.still if a.still >= 0 else dur), size, tip=not a.no_tip).save(out, quality=90)
        print(out)
        return 0
    t1 = a.t1 if a.t1 is not None else dur
    n0, n1 = int(round(a.t0 * FPS)), int(round(t1 * FPS))
    out = a.out or os.path.join(common.OUT, "demos", tag + ".mp4")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    audio = os.path.join(common.AUDIO, tag + "_mix.wav")
    filt = f"[0:a]apad=whole_dur={dur:.2f}[v]"
    cmd = ["nice", "-n", "10", "ffmpeg", "-y", "-loglevel", "error", "-i", wav]
    if a.music and os.path.exists(MUSIC):
        cmd += ["-stream_loop", "-1", "-i", MUSIC]
        filt += f";[1:a]volume=0.10,afade=t=in:d=1.5,afade=t=out:st={dur - 2.5:.2f}:d=2.5[m];[v][m]amix=inputs=2:duration=first:normalize=0[a]"
    else:
        filt += ";[v]anull[a]"
    subprocess.run(cmd + ["-filter_complex", filt, "-map", "[a]", "-ss", f"{a.t0:.3f}", "-t", f"{t1 - a.t0:.3f}", "-ar", "48000", audio], check=True)
    t0 = time.time()
    bd.encode((b.frame(i / FPS, cam.at(i / FPS), size, tip=not a.no_tip) for i in range(n0, n1)), out, FPS, size, audio=audio, crf=18 if max(size) <= 1920 else 20)
    el = time.time() - t0
    report.update(frames=n1 - n0, render_s=round(el, 1), ms_per_frame=round(el / max(1, n1 - n0) * 1000, 1), mb=round(os.path.getsize(out) / 1e6, 2), file=out)
    json.dump(report, open(os.path.join(common.WORK, tag + "_report.json"), "w"), indent=1)
    print(f"{out}: {n1 - n0} frames, {report['ms_per_frame']} ms per frame incl. x264, {report['mb']} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
