#!/usr/bin/env python3
"""Animation test of the five-character cast (docs/CHARACTER_LIBRARY.md): one short clip per character (idle + blink, talk, wave, point, walk) and one team video.

  AWS_PROFILE=qa python backend/scripts/vector_character_cast_demo.py --out DIR [--clips] [--team] [--size 1920x1080] [--store DIR] [--stills t1,t2]

* Backgrounds: scene packages of the cartoon vector catalog (--store: a folder holding one folder per scene id; VectorScene draws them with its own parallax).
* Narration: Polly (QA account, cents), one voice per character, cached as WAV in --cache. The speaking character's mouth follows the audio level; nods and hand beats fall on stressed syllables.
* Walking: the character crosses the scene by a smooth ease; the walk phase comes from the DISTANCE travelled (engine.vector_character.walk_feet), so planted feet do not skate.
Needs ffmpeg on PATH, resvg-py, Pillow, numpy. Offline demo (not a planner scene).
"""
import argparse
import math
import os
import subprocess
import sys
import time
import wave
from typing import Any, Dict, List, Tuple

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))
os.environ.setdefault("AWS_PROFILE", "qa")

import vector_character_demo as vd  # noqa: E402  (captions, fonts, wav helper)
from engine import vector_character as vc  # noqa: E402
from engine import vector_scene as vs  # noqa: E402
from engine.audio import SR  # noqa: E402

MUSIC_DIR = os.path.join(HERE, "..", "lambdas", "engine", "assets", "music")

# id, display name, role, EN voice(s) in order of preference
CAST: Dict[str, Dict[str, Any]] = {
    "ines": {"name": "Inés", "role": "senior teacher", "voices": ["Ruth"], "size": 1.0, "scene": "flower_meadow", "line": "Hello, I'm Inés. I taught for forty years, and I still love to learn."},
    "david": {"name": "David", "role": "software engineer", "voices": ["Matthew"], "size": 1.02, "scene": "modern_office_exterior", "line": "Hi, I'm David. I build apps that make everyday life a little easier."},
    "priya": {"name": "Priya", "role": "doctor", "voices": ["Kajal", "Danielle"], "size": 0.99, "scene": "laboratory_building", "line": "Hello, I'm Priya. A good check-up starts with a simple conversation."},
    "mateo": {"name": "Mateo", "role": "chef", "voices": ["Stephen"], "size": 1.03, "scene": "home_garden_backyard", "line": "Hey, I'm Mateo. Good food starts with fresh, simple ingredients."},
    "fox": {"name": "Fox", "role": "guide mascot", "voices": ["Gregory", "Joanna"], "size": 0.95, "scene": "autumn_forest_path", "line": "Hi! I'm Fox, your guide. Follow me, and let's explore together!"},
    # the animal cast (docs/PRESENTERS.md): used by vector_character_presenter_demo.py only
    "owl": {"name": "Hugo", "role": "owl professor", "voices": ["Brian", "Matthew"], "size": 0.95, "scene": "library_interior_view", "line": "Good day, I'm Hugo. Every question is the start of a discovery."},
    "bear": {"name": "Bruno", "role": "wellbeing friend", "voices": ["Stephen", "Matthew"], "size": 1.04, "scene": "bedroom_window_morning", "line": "Hello, I'm Bruno. Let's take a slow, deep breath together."},
}
ORDER = ["ines", "david", "priya", "mateo", "fox"]
TEAM_LINES = [("mateo", "Every healthy meal starts with fresh ingredients."),
              ("priya", "A good plate balances protein, vegetables and whole grains."),
              ("ines", "And the best habits are learned by cooking together."),
              ("david", "I plan the week's meals in a simple app, so nothing is wasted."),
              ("fox", "Small steps, every day, add up to big changes!")]
TEAM_X = {"mateo": 0.13, "priya": 0.315, "ines": 0.50, "david": 0.685, "fox": 0.87}
TEAM_SCENE = "home_garden_backyard"


def smooth(u: float) -> float:
    return vc._smooth(u)


def ramp(t: float, a: float, b: float) -> float:
    return smooth((t - a) / max(b - a, 1e-6))


def lerp2(a, b, w):
    return (a[0] + (b[0] - a[0]) * w, a[1] + (b[1] - a[1]) * w)


# ----------------------------------------------------------------------------- narration
def read_wav(path: str) -> np.ndarray:
    with wave.open(path, "rb") as w:
        return np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(np.float32) / 32768.0


def synth(cid: str, key: str, text: str, cache: str) -> np.ndarray:
    from engine import tts

    os.makedirs(cache, exist_ok=True)
    path = os.path.join(cache, f"{key}.wav")
    if os.path.exists(path):
        return read_wav(path)
    prov = tts.get_provider("polly", cfg={"region": os.environ.get("POLLY_REGION", "us-east-1"), "engine": "generative"})
    last = None
    for voice in CAST[cid]["voices"]:
        try:
            a = tts.synth_beat(prov, text, voice=voice)
            vd.write_wav(path, a)
            print(f"polly {voice}: {len(text)} chars")
            return a
        except Exception as e:  # noqa: BLE001
            last = e
            print(f"voice {voice} failed: {str(e)[:80]}")
    raise RuntimeError(f"no voice worked for {cid}: {last}")


# ----------------------------------------------------------------------------- animation of one character
class Actor:
    """One character with an action script. Pure functions of time plus a mouth state machine computed up front."""

    def __init__(self, cid: str, W: int, H: int, fps: int, ppu: float, seed: float):
        self.cid, self.fps, self.seed = cid, fps, seed
        self.size = CAST[cid]["size"]
        self.ppu = ppu
        self.ch = vc.load(cid, ppu, self.size, back_tint=0.93)
        self.stride_u = 0.5 * (vc.ULEG_U * (1 - vc.OVERLAP) + vc.LLEG_U) * 0.9 * self.size
        self.talk: List[Tuple[float, np.ndarray]] = []        # (start s, audio)
        self.gest: List[Tuple[str, float, float]] = []        # (kind, start, end): wave | point
        self.walk: Tuple[float, float, float, float] = (0.0, 0.0, 0.0, 0.0)   # t0, t1, x_from, x_to (px)
        self.x_fixed = 0.5 * W
        self._mouth: List[Tuple[float, float, List[str]]] = []
        self._stress: List[float] = []

    def add_talk(self, t0: float, audio: np.ndarray) -> None:
        env = vc.speech_envelope(audio, SR, self.fps)
        self._mouth.append((t0, len(audio) / SR, vc.mouth_track(env)))
        self._stress += [t0 + s for s in vc.stress_events(env, self.fps)]
        self.talk.append((t0, audio))

    def speaking(self, t: float) -> float:
        for t0, d, _ in self._mouth:
            if t0 - 0.05 <= t < t0 + d + 0.15:
                return 1.0
        return 0.0

    def mouth(self, t: float) -> str:
        for t0, d, tr in self._mouth:
            if t0 <= t < t0 + d:
                i = int((t - t0) * self.fps)
                return tr[min(i, len(tr) - 1)]
        return "closed"

    # --- walking
    def walk_x(self, t: float) -> Tuple[float, float, float]:
        """-> (x px, distance walked so far px, walking weight 0..1)."""
        t0, t1, xa, xb = self.walk
        if t1 <= t0:
            return self.x_fixed, 0.0, 0.0
        u = min(1.0, max(0.0, (t - t0) / (t1 - t0)))
        e = smooth(u)
        x = xa + (xb - xa) * e
        dist = abs(xb - xa) * e
        speed = abs(xb - xa) * 6 * u * (1 - u) / (t1 - t0)       # derivative of smoothstep
        w = ramp(speed, 12.0, 60.0) if 0 < u < 1 else 0.0
        return x, dist, w

    def pose(self, t: float, look: float = 0.0) -> Tuple[float, Dict[str, Any]]:
        x, dist, wk = self.walk_x(t)
        u = self.ppu
        D = self.stride_u
        dist_u = dist / (u * self.size)
        phase = math.pi * dist_u / D
        bob = 1.5 * (1 - math.cos(2 * phase)) / 2
        torso_sy, head_lift = vc.breath(t, 3.8 + 0.4 * self.seed, self.seed)
        hip_h = vc.HIP_H0 - bob * wk
        fa, fb = vc.walk_feet(phase, D, hip_h, 10.0)
        stand = (0.0, hip_h)
        feet = (lerp2(stand, fa, wk), lerp2(stand, fb, wk))
        arms = [vc.arm_angles("walk", t, phase, 0, wk), vc.arm_angles("walk", t, phase, 1, wk)]
        idle = [vc.arm_angles("idle", t, 0, 0), vc.arm_angles("idle", t, 0, 1)]
        arms = [lerp2(idle[i], arms[i], wk) for i in range(2)]
        # talking: head nods and hand beats on stressed syllables (spring pulses, so there is overshoot and settle)
        nod = 0.0
        beat = 0.0
        for te in self._stress:
            if -0.1 < t - te < 1.2:
                p = vc.spring_step(t - te, 4.2, 0.45) - vc.spring_step(t - te - 0.16, 4.2, 0.45)
                nod += p
                beat += p
        sp = self.speaking(t)
        arms[1] = (arms[1][0] + 22.0 * beat * sp * (1 - wk), arms[1][1] + 14.0 * beat * sp)
        for kind, a, b in self.gest:
            w = ramp(t, a, a + 0.35) * (1 - ramp(t, b - 0.3, b))
            if w > 0:
                tt = t - a
                if kind == "wave":
                    arms[1] = lerp2(arms[1], vc.arm_angles("wave", tt), w)
                else:
                    arms[1] = lerp2(arms[1], vc.arm_angles("point", tt), w)
        pose: Dict[str, Any] = {
            "feet": feet, "hip_h": hip_h, "arms": tuple(arms), "torso_sy": torso_sy,
            "tilt": 0.9 * math.sin(2 * phase) * wk + 0.5 * math.sin(2 * math.pi * t / (3.1 + self.seed) + self.seed) * (1 - wk),
            "head_tilt": -2.4 * math.sin(2 * phase - 0.8) * wk + 5.0 * nod * 0.35 * sp + 4.0 * look + 1.2 * math.sin(2 * math.pi * t / 4.7 + self.seed),
            "head_dy": head_lift + 1.0 * bob * 0.5 - 1.6 * nod * sp,
            "look": (3.5 * look, 0.0),
            "blink": vc.blink_natural(t, self.seed),
            "mouth": self.mouth(t),
        }
        return x, pose


def draw_label(img: Image.Image, text: str, alpha: float = 1.0) -> None:
    W, H = img.size
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    f = vd.font(round(H * 0.03))
    w = d.textlength(text, font=f) + H * 0.04
    d.rounded_rectangle([H * 0.03, H * 0.03, H * 0.03 + w, H * 0.03 + H * 0.06], radius=H * 0.02, fill=(18, 16, 36, int(190 * alpha)))
    d.text((H * 0.05, H * 0.06), text, font=f, fill=(255, 255, 255, int(255 * alpha)), anchor="lm")
    img.alpha_composite(ov)


# ----------------------------------------------------------------------------- one clip per character
def build_clip(cid: str, W: int, H: int, fps: int, store: str, cache: str) -> Tuple[Any, np.ndarray, float]:
    S = W / 1920.0
    ppu = 3.0 * S
    cfg = CAST[cid]
    ac = Actor(cid, W, H, fps, ppu, seed=0.3 + 0.17 * ORDER.index(cid))
    audio = synth(cid, f"clip_{cid}", cfg["line"], cache)
    t_talk = 0.9
    d = len(audio) / SR
    ac.add_talk(t_talk, audio)
    t_w = t_talk + d + 0.25          # wave
    ac.gest = [("wave", t_w, t_w + 1.3), ("point", t_w + 1.3, t_w + 2.5)]
    t_walk = t_w + 2.6
    total = t_walk + 2.2
    ac.walk = (t_walk, t_walk + 1.9, 0.40 * W, 0.66 * W)
    ac.x_fixed = 0.40 * W
    scene = vs.VectorScene(os.path.join(store, cfg["scene"]), W, H)
    labels = [(0.0, t_talk, "idle + blink"), (t_talk, t_talk + d + 0.2, "talk"), (t_w, t_w + 1.3, "wave"), (t_w + 1.3, t_w + 2.5, "point"), (t_walk, total, "walk")]
    ground = 0.835 * H

    def frame(t: float) -> Image.Image:
        img = scene.frame(t, total).convert("RGBA")
        x, pose = ac.pose(t)
        ac.ch.draw(img, x, ground, pose)
        if t_talk <= t < t_talk + d + 0.2:
            a = ramp(t, t_talk, t_talk + 0.2) * (1 - ramp(t, t_talk + d, t_talk + d + 0.2))
            vd.caption(img, cfg["line"], a)
        for a0, b0, name in labels:
            if a0 <= t < b0:
                draw_label(img, f"{cfg['name']} · {name}")
        fade = ramp(t, 0, 0.3) * (1 - ramp(t, total - 0.4, total))
        if fade < 1:
            img.alpha_composite(Image.new("RGBA", img.size, (0, 0, 0, int(255 * (1 - fade)))))
        return img.convert("RGB")

    a = np.zeros(int(total * SR) + SR, dtype=np.float32)
    s = int(t_talk * SR)
    a[s:s + len(audio)] += audio
    return frame, a, total


# ----------------------------------------------------------------------------- the team video
def build_team(W: int, H: int, fps: int, store: str, cache: str) -> Tuple[Any, np.ndarray, float]:
    S = W / 1920.0
    ppu = 2.4 * S
    actors = {cid: Actor(cid, W, H, fps, ppu, seed=0.2 + 0.19 * i) for i, cid in enumerate(TEAM_X)}
    audios = [synth(cid, f"team_{i}", text, cache) for i, (cid, text) in enumerate(TEAM_LINES)]
    t = 3.0
    starts: List[float] = []
    for (cid, _), a in zip(TEAM_LINES, audios):
        starts.append(t)
        actors[cid].add_talk(t, a)
        t += len(a) / SR + 0.55
    wave_t = t + 0.1
    total = wave_t + 2.2
    # the group walks into position together (same distance for all, so nobody crosses anybody), each starting a few frames apart so the steps are not in lock-step
    for i, cid in enumerate(["mateo", "priya", "ines", "david", "fox"]):
        t0 = 0.2 + 0.13 * i
        ac = actors[cid]
        ac.walk = (t0, t0 + 2.1, TEAM_X[cid] * W - 0.27 * W, TEAM_X[cid] * W)
        ac.x_fixed = TEAM_X[cid] * W
        ac.gest = [("wave", wave_t + 0.1 * i, total - 0.2)]
    scene = vs.VectorScene(os.path.join(store, TEAM_SCENE), W, H)
    ground = 0.835 * H
    order = sorted(TEAM_X, key=lambda c: actors[c].size)

    def speaker_at(tt: float):
        for (cid, text), s0, a in zip(TEAM_LINES, starts, audios):
            if s0 <= tt < s0 + len(a) / SR:
                return cid, text, s0, len(a) / SR
        return None

    def frame(tt: float) -> Image.Image:
        img = scene.frame(tt, total).convert("RGBA")
        sp = speaker_at(tt)
        for cid in order:
            ac = actors[cid]
            look = 0.0
            if sp and sp[0] != cid:
                look = max(-1.0, min(1.0, (TEAM_X[sp[0]] - TEAM_X[cid]) * 3.0)) * ramp(tt, sp[2] - 0.3, sp[2] + 0.2)
            x, pose = ac.pose(tt, look)
            ac.ch.draw(img, x, ground, pose)
        if sp:
            _, text, s0, d = sp
            a = ramp(tt, s0 - 0.05, s0 + 0.2) * (1 - ramp(tt, s0 + d - 0.1, s0 + d + 0.2))
            if a > 0.01:
                vd.caption(img, text, a)
        fade = ramp(tt, 0, 0.4) * (1 - ramp(tt, total - 0.6, total))
        if fade < 1:
            img.alpha_composite(Image.new("RGBA", img.size, (0, 0, 0, int(255 * (1 - fade)))))
        return img.convert("RGB")

    out = np.zeros(int(total * SR) + SR, dtype=np.float32)
    for s0, a in zip(starts, audios):
        s = int(s0 * SR)
        out[s:s + len(a)] += a
    return frame, out, total


# ----------------------------------------------------------------------------- encode
def pick_music(name: str) -> str:
    p = os.path.join(MUSIC_DIR, name)
    return p if os.path.exists(p) else vd.MUSIC


def encode(frame, audio: np.ndarray, total: float, W: int, H: int, fps: int, out: str, music: str, only_t: List[float] = None) -> None:
    if only_t:
        for s in only_t:
            frame(s).save(f"{os.path.splitext(out)[0]}_{s:05.2f}.png")
        return
    tmp = out + ".silent.mp4"
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-c:v", "libx264", "-preset", "medium",
                          "-crf", "17", "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
    n = int(total * fps)
    t1 = time.time()
    for i in range(n):
        p.stdin.write(frame(i / fps).tobytes())
    p.stdin.close()
    p.wait()
    print(f"{os.path.basename(out)}: {n} frames, {(time.time() - t1) / n * 1000:.0f} ms/frame")
    wav = out + ".voice.wav"
    vd.write_wav(wav, audio[:int(total * SR)])
    fade_out = max(0.0, total - 1.0)
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", tmp, "-i", wav, "-stream_loop", "-1", "-i", music, "-filter_complex",
           f"[2:a]atrim=0:{total:.3f},volume=0.11,afade=t=in:d=0.6,afade=t=out:st={fade_out:.2f}:d=1.0[m];[1:a]volume=1.0[v];[v][m]amix=inputs=2:duration=first:normalize=0[a]",
           "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", out]
    subprocess.run(cmd, check=True)
    os.remove(tmp)
    os.remove(wav)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--clips", action="store_true")
    ap.add_argument("--team", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--size", default="1920x1080")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--store", required=True)
    ap.add_argument("--cache", default=os.path.join(HERE, "..", "..", ".vchar_cache"))
    ap.add_argument("--stills", default="")
    a = ap.parse_args()
    W, H = (int(x) for x in a.size.lower().split("x"))
    os.makedirs(a.out, exist_ok=True)
    stills = [float(x) for x in a.stills.split(",")] if a.stills else None
    if a.clips:
        for cid in ORDER:
            if a.only and cid not in a.only:
                continue
            frame, audio, total = build_clip(cid, W, H, a.fps, a.store, a.cache)
            encode(frame, audio, total, W, H, a.fps, os.path.join(a.out, f"clip_{cid}.mp4"), pick_music("acoustic-warm.mp3"), stills)
    if a.team:
        frame, audio, total = build_team(W, H, a.fps, a.store, a.cache)
        encode(frame, audio, total, W, H, a.fps, os.path.join(a.out, "team.mp4"), pick_music("bright-pluck-morning.mp3"), stills)
    return 0


if __name__ == "__main__":
    sys.exit(main())
