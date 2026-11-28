#!/usr/bin/env python3
"""The standing presenter and its automatic gestures (docs/CHARACTER_ANIMATION_PROOF.md, "Second pass"): talk clips, the team clip, before/after, framing presets.

  AWS_PROFILE=qa python backend/scripts/vector_character_presenter_demo.py --out DIR --store SCENES [--talk] [--team] [--compare david priya] [--framing] [--only ID ...]
        [--size 1280x720] [--peaks] [--plan]

* Narration: Polly generative through engine.tts (QA account, cents), one voice per character, cached as WAV in --cache. Word timings come from the audio itself
  (engine.align.align_words), loudness per word from the speech level: that is all the gesture planner gets (engine.character_gestures). No model picks a gesture.
* --talk     one 15 to 20 s talk per character beside a content card; --peaks also writes a still at every gesture stroke (to check by eye); --plan prints the plan only.
* --team     the five take turns in a garden: they step in (no walk), the listeners look at the speaker and nod, everyone waves at the end.
* --compare  the old rig (bent legs, walk, one hand sprite) and the new one side by side on the same narration.
* --framing  a still sheet of the framing presets in 16:9, 9:16, 1:1 and 4:5, and one tall and one square clip.
One ffmpeg at a time, run with `nice`. Offline demo: the characters are not wired into the planner.
"""
import argparse
import os
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "lambdas"))
os.environ.setdefault("AWS_PROFILE", "qa")

import vector_character_cast_demo as old  # noqa: E402  (the first rig's demo: voices, Actor for the BEFORE side)
import vector_character_demo as vd  # noqa: E402  (captions, fonts, wav helper)
from engine import align  # noqa: E402
from engine import character_gestures as cg  # noqa: E402
from engine import vector_character as vc  # noqa: E402
from engine import vector_presenter as vp  # noqa: E402
from engine import vector_scene as vs  # noqa: E402
from engine.audio import SR  # noqa: E402

ORDER = ["ines", "david", "priya", "mateo", "fox"]
ANIMALS = ["owl", "bear", "cat", "parrot", "turtle"]                # the animal cast: rendered when named in --only (talk) or with --animals (the group still)
TAILS = {"fox", "owl", "cat", "parrot", "turtle"}
# script, framing, side of the frame where the character stands, the card beside it (title, [(word that reveals the line, line)])
TALK: Dict[str, Dict[str, Any]] = {
    "ines": {"text": "Hello, I'm Inés. Learning something new takes three things: time, practice and patience. Some days it feels slow, but every small step counts. So, what will you learn today? Thank you for listening!",
             "framing": "full", "side": "left", "scene": "flower_meadow", "card": ("Learning takes", [("time,", "Time"), ("practice", "Practice"), ("patience.", "Patience")])},
    "david": {"text": "Hi, I'm David. A fast app comes down to three steps: measure, simplify and cache. Guessing is easy, but measuring is what works. Look at this chart: every second really matters. Thanks for watching!",
              "framing": "three_quarter", "side": "left", "scene": "modern_office_exterior", "card": ("A faster app", [("measure,", "1  Measure"), ("simplify", "2  Simplify"), ("cache.", "3  Cache")])},
    "priya": {"text": "Hello, I'm Priya. A good check-up starts with a simple conversation. First, we talk about how you feel. Second, we check your heart and lungs. And remember: small habits are the best medicine. Thank you, and take care!",
              "framing": "waist_up", "side": "right", "scene": "laboratory_building", "card": ("Your check-up", [("First,", "1  How you feel"), ("Second,", "2  Heart and lungs"), ("remember:", "Small habits, every day")])},
    "mateo": {"text": "Hey, I'm Mateo. Good food starts with fresh ingredients. Look at these tomatoes: ripe, red and full of flavour. Do you need a fancy kitchen? Not at all. Great food is simple. Thanks, and enjoy your meal!",
              "framing": "full", "side": "right", "scene": "home_garden_backyard", "card": ("Fresh tomatoes", [("ripe,", "Ripe"), ("red", "Red"), ("flavour.", "Full of flavour")])},
    "fox": {"text": "Hi! I'm Fox, your guide. Today we explore the forest together. On one side there are tall old trees, but on the other side, a quiet river. Stay close, and remember: every path leads home. Ready? Great, follow me!",
            "framing": "three_quarter", "side": "left", "scene": "autumn_forest_path", "card": ("The forest", [("trees,", "Tall old trees"), ("river.", "A quiet river")])},
    "owl": {"text": "Good day! I'm Otto. Why is the sky blue? Sunlight is made of many colours. First, it meets the air. Second, the blue light scatters the most. So look up: that blue is sunlight, playing. Thank you for listening!",
            "framing": "three_quarter", "side": "left", "scene": "library_interior_view", "card": ("Why the sky is blue", [("colours.", "Light has many colours"), ("First,", "1  It meets the air"), ("Second,", "2  Blue scatters most")])},
    "bear": {"text": "Hello, I'm Bruno. Feeling worried is okay. Here are three things that help: breathe slowly, name the feeling, and tell someone you trust. Big feelings come, but they also go. You are doing great. Sleep well!",
             "framing": "three_quarter", "side": "right", "scene": "bedroom_window_morning", "card": ("When you feel worried", [("slowly,", "Breathe slowly"), ("name", "Name the feeling"), ("tell", "Tell someone you trust")])},
    "cat": {"text": "Hi, I'm Mika! How does a robot work? It needs three things: sensors, a brain and motors. First, the sensors look around. Second, the brain decides. And look at this: the motors make it move. Thanks for watching!",
            "framing": "three_quarter", "side": "left", "scene": "robotics_lab_window", "card": ("How a robot works", [("sensors,", "Sensors: it looks"), ("brain", "Brain: it decides"), ("motors.", "Motors: it moves")])},
    # the parrot speaks Spanish (a Spanish Polly voice): the natural Spanish-first character
    "parrot": {"text": "¡Hola! Soy Paco. Hoy aprendemos a saludar en tres idiomas. Primero, en español: hola. Segundo, en inglés: hello. Y tercero, en francés: bonjour. Mira qué fácil. ¡Gracias, y buen viaje!",
               "framing": "three_quarter", "side": "right", "scene": "tropical_river_jungle", "card": ("Saludar en tres idiomas", [("Primero,", "Español: hola"), ("Segundo,", "Inglés: hello"), ("tercero,", "Francés: bonjour")])},
    "turtle": {"text": "Hello, I'm Tula. The sea is full of life. First, sunlight feeds tiny plants. Second, small fish eat them. Third, bigger fish follow. Take your time and look closely: the sea tells its story. Thank you!",
               "framing": "three_quarter", "side": "left", "scene": "deep_ocean_reef", "card": ("Life in the sea", [("First,", "1  Sunlight feeds tiny plants"), ("Second,", "2  Small fish eat them"), ("Third,", "3  Bigger fish follow")])},
}
SIZE = {c: old.CAST[c]["size"] for c in ORDER + ANIMALS}


def ramp(t: float, a: float, b: float) -> float:
    return vc._smooth((t - a) / max(b - a, 1e-6))


# ----------------------------------------------------------------------------- narration -> words, loudness, mouth
def narrate(cid: str, key: str, text: str, cache: str, fps: int) -> Dict[str, Any]:
    audio = old.synth(cid, key, text, cache)
    dur = len(audio) / SR
    words, conf = align.align_words(audio, SR, text)
    if conf < 0.35 or not words:
        words = align.estimate_words(text, dur)
    env = vc.speech_envelope(audio, SR, fps)
    return {"audio": audio, "dur": dur, "words": words, "env": env, "mouth": vc.mouth_track(env), "level": cg.word_levels(words, env, fps), "text": text, "conf": conf}


def shifted(words: List[cg.Word], t0: float) -> List[cg.Word]:
    return [(w, a + t0, b + t0) for w, a, b in words]


def performer(cid: str, n: Dict[str, Any], t0: float, fps: int, seed: float, content_side: int, lift: float = 0.0) -> cg.Performance:
    perf = cg.Performance(seed=seed, content_side=content_side, tail=cid in TAILS, lift=lift)
    perf.speak(shifted(n["words"], t0), n["level"], t0 + n["dur"])
    perf.mouth(t0, fps, n["mouth"])
    return perf


def draw_actor(img: Image.Image, ch: vp.Presenter, perf: cg.Performance, t: float, x: float, ground: float) -> None:
    pose, ex = perf.pose(t, ch.g)
    if ex["alpha"] <= 0.003:
        return
    xx = x + ex["x"] * ch.ppu
    if ex["alpha"] >= 0.997:
        ch.draw(img, xx, ground, pose)
        return
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ch.draw(layer, xx, ground, pose)
    a = np.array(layer)
    a[..., 3] = (a[..., 3].astype(np.float32) * ex["alpha"]).astype(np.uint8)
    img.alpha_composite(Image.fromarray(a, "RGBA"))


# ----------------------------------------------------------------------------- the card the presenter talks beside
def draw_card(img: Image.Image, rect: Tuple[float, float, float, float], title: str, lines: List[Tuple[float, str]], t: float, t_in: float) -> None:
    x0, y0, x1, y1 = rect
    if x1 - x0 < 10:
        return
    W, H = img.size
    a = ramp(t, t_in, t_in + 0.45)
    if a <= 0:
        return
    w, h = x1 - x0, y1 - y0
    ch = min(h, w * 0.62)
    cy0 = y0 + (h - ch) / 2 + (1 - a) * 0.02 * H
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    r = min(W, H) * 0.03
    d.rounded_rectangle([x0 + 4, cy0 + 6, x1 + 4, cy0 + ch + 6], radius=r, fill=(20, 24, 40, int(50 * a)))
    d.rounded_rectangle([x0, cy0, x1, cy0 + ch], radius=r, fill=(255, 255, 255, int(238 * a)), outline=(36, 32, 52, int(255 * a)), width=max(2, round(min(W, H) * 0.004)))
    ft = vd.font(round(ch * 0.115))
    d.text((x0 + w * 0.07, cy0 + ch * 0.15), title, font=ft, fill=(36, 32, 52, int(255 * a)), anchor="lm")
    d.line([x0 + w * 0.07, cy0 + ch * 0.27, x1 - w * 0.07, cy0 + ch * 0.27], fill=(222, 108, 62, int(255 * a)), width=max(2, round(ch * 0.012)))
    fl = vd.font(round(ch * 0.092))
    for i, (tl, text) in enumerate(lines):
        b = ramp(t, tl, tl + 0.3) * a
        if b <= 0:
            continue
        yy = cy0 + ch * (0.42 + 0.18 * i)
        d.ellipse([x0 + w * 0.075, yy - ch * 0.022, x0 + w * 0.075 + ch * 0.044, yy + ch * 0.022], fill=(222, 108, 62, int(255 * b)))
        d.text((x0 + w * 0.075 + ch * 0.09 + (1 - b) * w * 0.02, yy), text, font=fl, fill=(36, 32, 52, int(255 * b)), anchor="lm")
    img.alpha_composite(ov)


def caption(img: Image.Image, words: List[cg.Word], t: float, y_frac: float = 0.935) -> None:
    """The sentence being spoken, at the bottom."""
    for idx in cg.sentences(words):
        a, b = words[idx[0]][1], words[idx[-1]][2]
        if a - 0.1 <= t < b + 0.25:
            al = ramp(t, a - 0.1, a + 0.12) * (1 - ramp(t, b + 0.05, b + 0.25))
            if al > 0.01:
                vd.caption(img, " ".join(words[i][0] for i in idx), al)
            return


def caption_at(img: Image.Image, words: List[cg.Word], t: float, rect: Tuple[float, float, float, float]) -> None:
    """The sentence being spoken inside a given strip (tall and square frames: under the card, above the presenter's head, never over the face)."""
    x0, y0, x1, y1 = rect
    for idx in cg.sentences(words):
        a, b = words[idx[0]][1], words[idx[-1]][2]
        if a - 0.1 <= t < b + 0.25:
            al = ramp(t, a - 0.1, a + 0.12) * (1 - ramp(t, b + 0.05, b + 0.25))
            if al <= 0.01:
                return
            ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(ov)
            f = vd.font(round(min((y1 - y0) * 0.30, (x1 - x0) * 0.047)))
            lines = vd.wrap_text(d, " ".join(words[i][0] for i in idx), f, int(x1 - x0 - (y1 - y0) * 0.3))[:2]
            lh = f.size * 1.3
            w = max(d.textlength(ln, font=f) for ln in lines) + f.size * 1.4
            h = lh * len(lines) + f.size * 0.7
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            d.rounded_rectangle([cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2], radius=f.size * 0.7, fill=(18, 16, 36, int(185 * al)))
            for i, ln in enumerate(lines):
                d.text((cx, cy - h / 2 + f.size * 0.35 + lh * (i + 0.5)), ln, font=f, fill=(255, 255, 255, int(255 * al)), anchor="mm")
            img.alpha_composite(ov)
            return


def label(img: Image.Image, text: str, x: float, y: float, fill=(18, 16, 36, 215)) -> None:
    W, H = img.size
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    f = vd.font(round(H * 0.034))
    w = d.textlength(text, font=f) + H * 0.04
    d.rounded_rectangle([x, y, x + w, y + H * 0.062], radius=H * 0.02, fill=fill)
    d.text((x + H * 0.02, y + H * 0.031), text, font=f, fill=(255, 255, 255, 255), anchor="lm")
    img.alpha_composite(ov)


def backdrop(store: str, scene: str, W: int, H: int, dim: float = 0.0):
    sc = vs.VectorScene(os.path.join(store, scene), W, H) if store and os.path.isdir(os.path.join(store, scene)) else None

    def frame(t: float, total: float) -> Image.Image:
        if sc is None:
            return Image.new("RGBA", (W, H), (232, 238, 246, 255))
        im = sc.frame(t, total).convert("RGBA")
        if dim > 0:
            im.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, int(255 * dim))))
        return im
    return frame


# ----------------------------------------------------------------------------- one talk
def build_talk(cid: str, W: int, H: int, fps: int, store: str, cache: str, framing: Optional[str] = None, side: Optional[str] = None, captions: bool = True):
    cfg = TALK[cid]
    fr = vp.framing(framing or cfg["framing"], side or cfg["side"], W, H)
    seed = 0.3 + 0.17 * (ORDER + ANIMALS).index(cid)
    ch = vp.load(cid, fr["ppu"], SIZE[cid])
    n = narrate(cid, f"talk3_{cid}", cfg["text"], cache, fps)
    t_talk = 1.0
    content_side = 1 if fr["side"] == "left" else -1 if fr["side"] == "right" else 0
    perf = performer(cid, n, t_talk, fps, seed, content_side, fr["lift"])
    perf.enter(0.15, from_side=-content_side or -1, distance=55.0)
    total = max(t_talk + n["dur"] + 0.9, max([g.t1 for g in perf.gestures] or [0]) + 0.5)
    words = shifted(n["words"], t_talk)
    title, items = cfg["card"]
    lines = []
    for key, text in items:
        tw = next((a for w, a, _ in words if w == key), next((a for w, a, _ in words if w.lower().startswith(key.lower().rstrip(",.:"))), t_talk + 2.0))
        lines.append((tw - 0.05, text))
    bg = backdrop(store, cfg["scene"], W, H, 0.10)
    ground = fr["ground"]

    wide = W / H >= 1.3
    card = fr["content"]
    strip = (card[0], card[3] - 0.105 * H, card[2], card[3])        # tall and square frames: the caption has its own strip under the card
    if not wide:
        card = (card[0], card[1], card[2], card[3] - 0.115 * H)

    def frame(t: float) -> Image.Image:
        img = bg(t, total)
        draw_card(img, card, title, lines, t, 0.5)
        draw_actor(img, ch, perf, t, fr["x"], ground)
        if captions and wide:
            caption(img, words, t)
        elif captions:
            caption_at(img, words, t, strip)
        fade = ramp(t, 0, 0.3) * (1 - ramp(t, total - 0.35, total))
        if fade < 1:
            img.alpha_composite(Image.new("RGBA", img.size, (0, 0, 0, int(255 * (1 - fade)))))
        return img.convert("RGB")

    audio = np.zeros(int(total * SR) + SR, dtype=np.float32)
    s = int(t_talk * SR)
    audio[s:s + len(n["audio"])] += n["audio"]
    return frame, audio, total, perf, n


# ----------------------------------------------------------------------------- before / after
def build_compare(cid: str, W: int, H: int, fps: int, store: str, cache: str):
    """Left: the first rig doing what it did in the first review (talk with hand beats, wave, point, walk). Right: the standing presenter on the same narration."""
    cfg = TALK[cid]
    n = narrate(cid, f"talk3_{cid}", cfg["text"], cache, fps)
    t_talk = 1.0
    hw = W // 2
    ppu = 0.70 * H / 290.0
    ground = 0.90 * H
    seed = 0.3 + 0.17 * (ORDER + ANIMALS).index(cid)
    ac = old.Actor(cid, hw, H, fps, ppu, seed)
    ac.add_talk(t_talk, n["audio"])
    t_w = t_talk + n["dur"] + 0.2
    ac.gest = [("wave", t_talk - 0.3, t_talk + 1.1), ("point", t_talk + n["dur"] * 0.62, t_talk + n["dur"] * 0.62 + 1.4)]
    ac.walk = (t_w, t_w + 1.9, 0.36 * hw, 0.64 * hw)
    ac.x_fixed = 0.36 * hw
    total = t_w + 2.2
    ch = vp.load(cid, ppu, SIZE[cid])
    perf = performer(cid, n, t_talk, fps, seed, 0)
    perf.side_step(t_w + 0.1, 16.0)
    words = shifted(n["words"], t_talk)
    bg = backdrop(store, cfg["scene"], hw, H, 0.12)

    def frame(t: float) -> Image.Image:
        img = Image.new("RGBA", (W, H), (255, 255, 255, 255))
        left = bg(t, total)
        x, pose = ac.pose(t)
        ac.ch.draw(left, x, ground, pose)
        label(left, "BEFORE", H * 0.03, H * 0.03, (150, 48, 40, 225))
        right = bg(t, total)
        draw_actor(right, ch, perf, t, 0.5 * hw, ground)
        label(right, "AFTER", H * 0.03, H * 0.03, (30, 110, 70, 225))
        img.paste(left, (0, 0))
        img.paste(right, (W - hw, 0))
        ImageDraw.Draw(img).line([hw, 0, hw, H], fill=(255, 255, 255, 255), width=max(2, W // 400))
        caption(img, words, t)
        fade = ramp(t, 0, 0.3) * (1 - ramp(t, total - 0.35, total))
        if fade < 1:
            img.alpha_composite(Image.new("RGBA", img.size, (0, 0, 0, int(255 * (1 - fade)))))
        return img.convert("RGB")

    audio = np.zeros(int(total * SR) + SR, dtype=np.float32)
    s = int(t_talk * SR)
    audio[s:s + len(n["audio"])] += n["audio"]
    return frame, audio, total, perf, n


# ----------------------------------------------------------------------------- the team, without walking
def build_team(W: int, H: int, fps: int, store: str, cache: str):
    S = W / 1920.0
    ppu = 2.4 * S
    ids = list(old.TEAM_X)
    chars = {c: vp.load(c, ppu, SIZE[c]) for c in ids}
    perfs = {c: cg.Performance(seed=0.2 + 0.19 * i, tail=c == "fox") for i, c in enumerate(ids)}
    ns = [narrate(c, f"team_{i}", text, cache, fps) for i, (c, text) in enumerate(old.TEAM_LINES)]
    t = 2.1
    turns = []
    for (c, text), n in zip(old.TEAM_LINES, ns):
        turns.append((c, t, n))
        perfs[c].speak(shifted(n["words"], t), n["level"], t + n["dur"])
        perfs[c].mouth(t, fps, n["mouth"])
        t += n["dur"] + 0.5
    for c, t0, n in turns:                                # everyone else listens to the speaker
        stress = [a + t0 for (w, a, b), lv in zip(n["words"], n["level"]) if lv > 0.75 and len(w) > 4]
        for o in ids:
            if o != c:
                perfs[o].listen(t0 - 0.25, t0 + n["dur"] + 0.1, (old.TEAM_X[c] - old.TEAM_X[o]) * 3.0, stress)
    wave_t = t + 0.25
    total = wave_t + 2.3
    for i, c in enumerate(ids):
        perfs[c].enter(0.15 + 0.16 * i, from_side=-1 if i < 3 else 1, distance=48.0, dur=0.8)   # a short step in from the nearer side, one after another
        perfs[c].gesture("wave", wave_t + 0.09 * ((i * 3) % 5), hold=1.25 + 0.06 * i)
    scene = vs.VectorScene(os.path.join(store, old.TEAM_SCENE), W, H)
    ground = 0.835 * H
    order = sorted(ids, key=lambda c: SIZE[c])

    def frame(tt: float) -> Image.Image:
        img = scene.frame(tt, total).convert("RGBA")
        for c in order:
            draw_actor(img, chars[c], perfs[c], tt, old.TEAM_X[c] * W, ground)
        for c, t0, n in turns:
            if t0 - 0.1 <= tt < t0 + n["dur"] + 0.25:
                a = ramp(tt, t0 - 0.05, t0 + 0.2) * (1 - ramp(tt, t0 + n["dur"] - 0.1, t0 + n["dur"] + 0.2))
                if a > 0.01:
                    vd.caption(img, n["text"], a)
        fade = ramp(tt, 0, 0.4) * (1 - ramp(tt, total - 0.5, total))
        if fade < 1:
            img.alpha_composite(Image.new("RGBA", img.size, (0, 0, 0, int(255 * (1 - fade)))))
        return img.convert("RGB")

    audio = np.zeros(int(total * SR) + SR, dtype=np.float32)
    for c, t0, n in turns:
        s = int(t0 * SR)
        audio[s:s + len(n["audio"])] += n["audio"]
    return frame, audio, total, perfs, ns


# ----------------------------------------------------------------------------- framing presets (stills)
def framing_sheet(out: str, store: str, cell_h: int = 420) -> None:
    shapes = [("16:9", 16 / 9), ("9:16", 9 / 16), ("1:1", 1.0), ("4:5", 0.8)]
    cast = ["david", "priya", "mateo"]
    cells = []
    for name, ar in shapes:
        for j, preset in enumerate(vp.FRAMINGS):
            W, H = round(cell_h * ar), cell_h
            side = "left" if j != 1 else "right"
            fr = vp.framing(preset, side, W, H)
            cid = cast[j]
            ch = vp.load(cid, round(fr["ppu"], 4), SIZE[cid])
            img = backdrop(store, TALK[cid]["scene"], W, H, 0.12)(1.0, 4.0)
            title, items = TALK[cid]["card"]
            draw_card(img, fr["content"], title, [(0.0, tx) for _, tx in items], 2.0, 0.0)
            A = ch.g.arm
            cs = 1 if side == "left" else -1
            hands = [None, None]
            hands[1 if cs > 0 else 0] = (cg.KEY["present"][0][0] * A, cg.KEY["present"][0][1] * A)
            shp = ["relaxed", "relaxed"]
            shp[1 if cs > 0 else 0] = "open"
            ch.draw(img, fr["x"], fr["ground"], {"hands": tuple(hands), "hand_shape": tuple(shp), "wrist": (8.0, 8.0), "lean": 1.4 * cs, "head_tilt": 3.0 * cs, "look": (2.5 * cs, 0.0), "mouth": "half"})
            label(img, f"{name}  {preset}  {side}", H * 0.02, H * 0.02)
            cells.append(img.convert("RGB"))
    pad = 14
    rows = [cells[i:i + 3] for i in range(0, len(cells), 3)]
    Wt = max(sum(c.width for c in r) + pad * 4 for r in rows)
    sheet = Image.new("RGB", (Wt, (cell_h + pad) * len(rows) + pad), (24, 22, 36))
    for ri, r in enumerate(rows):
        x = (Wt - sum(c.width for c in r) - pad * 2) // 2
        for c in r:
            sheet.paste(c, (x, pad + ri * (cell_h + pad)))
            x += c.width + pad
    sheet.save(out, quality=88)
    print("wrote", out)


# ----------------------------------------------------------------------------- encode
def animal_group(out: str, store: str, W: int = 1920, H: int = 1080, scene: str = "flower_meadow") -> None:
    """One still of the six animals together (the fox and the animal cast), each at a different gesture, on a cartoon scene."""
    ids = ["fox"] + ANIMALS
    img = backdrop(store, scene, W, H, 0.06)(2.0, 10.0)
    ppu = H / 425.0
    K = cg.KEY
    kinds = ["wave", "count", "thumb", "count", "thumb", "wave"]            # gestures that stay close to the body: six figures stand shoulder to shoulder
    shapes = ["open", "two", "thumb", "three", "thumb", "open"]
    for i, cid in enumerate(ids):
        ch = vp.load(cid, ppu, SIZE[cid])
        A = ch.g.arm
        kind = kinds[i % len(kinds)]
        key = (K[kind][0][0] * A, K[kind][0][1] * A)
        shape = shapes[i % len(shapes)]
        left = i < len(ids) / 2                                  # the outer arm gestures: the left arm on the left half of the picture
        rest = (cg.REST_WRIST, K[kind][1])
        pose: Dict[str, Any] = {"hands": (key, key) if kind == "open" else (key, None) if left else (None, key),
                                "hand_shape": (shape, shape) if kind == "open" else (shape, "relaxed") if left else ("relaxed", shape),
                                "wrist": (K[kind][1], K[kind][1]) if kind == "open" else rest[::-1] if left else rest, "mouth": ("half", "closed", "wide")[i % 3], "tail": (-5.0, 4.0)[i % 2]}
        ch.draw(img, W * (0.09 + 0.158 * i), H * 0.93, pose)
        label(img, old.CAST[cid]["name"], W * (0.09 + 0.158 * i) - W * 0.035, H * 0.94)
    img.convert("RGB").save(out, quality=90)
    print("wrote", out)


def encode(frame, audio: np.ndarray, total: float, W: int, H: int, fps: int, out: str, music: Optional[str] = None) -> None:
    tmp = out + ".silent.mp4"
    p = subprocess.Popen(["nice", "-n", "12", "ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-", "-c:v", "libx264",
                          "-preset", "veryfast", "-crf", "17", "-threads", "3", "-pix_fmt", "yuv420p", tmp], stdin=subprocess.PIPE)
    n = int(total * fps)
    t1 = time.time()
    for i in range(n):
        p.stdin.write(frame(i / fps).tobytes())
    p.stdin.close()
    p.wait()
    print(f"{os.path.basename(out)}: {n} frames, {(time.time() - t1) / n * 1000:.0f} ms/frame")
    wav = out + ".voice.wav"
    vd.write_wav(wav, audio[:int(total * SR)])
    if music and os.path.exists(music):
        fo = max(0.0, total - 1.0)
        cmd = ["nice", "-n", "12", "ffmpeg", "-v", "error", "-y", "-i", tmp, "-i", wav, "-stream_loop", "-1", "-i", music, "-filter_complex",
               f"[2:a]atrim=0:{total:.3f},volume=0.08,afade=t=in:d=0.6,afade=t=out:st={fo:.2f}:d=1.0[m];[1:a]volume=1.0[v];[v][m]amix=inputs=2:duration=first:normalize=0[a]",
               "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", out]
    else:
        cmd = ["nice", "-n", "12", "ffmpeg", "-v", "error", "-y", "-i", tmp, "-i", wav, "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-shortest", out]
    subprocess.run(cmd, check=True)
    os.remove(tmp)
    os.remove(wav)


def peaks(frame, perf: cg.Performance, out_prefix: str, cols: int = 4) -> None:
    """A contact sheet with one still per gesture, a little after its stroke (and at each step of a count or a comparison)."""
    ts: List[Tuple[float, str]] = []
    for g in perf.gestures:
        ts.append((g.stroke + 0.2, f"{g.kind} '{g.word}'"))
        ts += [(s[0] + 0.2, f"{g.kind} step {s[1]}") for s in g.steps[1:] if g.kind == "count"] + [(s[0] + 0.25, "compare 2nd hand") for s in g.steps if g.kind == "compare"]
    ts += [(b[0] + 0.02, "beat") for b in perf.beats[:2]]
    ts.sort()
    ims = []
    for t, name in ts:
        im = frame(t).convert("RGBA")
        label(im, f"{t:.2f}s {name}", im.height * 0.03, im.height * 0.03)
        ims.append(im.convert("RGB").resize((640, round(640 * im.height / im.width)), Image.LANCZOS))
    if not ims:
        return
    rows = (len(ims) + cols - 1) // cols
    sheet = Image.new("RGB", (640 * cols, ims[0].height * rows), (20, 20, 30))
    for i, im in enumerate(ims):
        sheet.paste(im, (640 * (i % cols), im.height * (i // cols)))
    sheet.save(out_prefix + "_peaks.jpg", quality=86)
    print("wrote", out_prefix + "_peaks.jpg")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--store", default="")
    ap.add_argument("--talk", action="store_true")
    ap.add_argument("--team", action="store_true")
    ap.add_argument("--compare", nargs="*")
    ap.add_argument("--framing", action="store_true")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--size", default="1280x720")
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--cache", default=os.path.join(HERE, "..", "..", ".vchar_cache"))
    ap.add_argument("--peaks", action="store_true")
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--no-video", action="store_true")
    ap.add_argument("--animals", action="store_true", help="one still of the six animals together (animal_cast_all.jpg)")
    a = ap.parse_args()
    W, H = (int(x) for x in a.size.lower().split("x"))
    os.makedirs(a.out, exist_ok=True)
    music = os.path.join(HERE, "..", "music-draft", "playful-kids.mp3")

    def run(name: str, built) -> None:
        frame, audio, total, perf, n = built
        if a.plan and isinstance(perf, cg.Performance):
            print(name, f"{total:.1f}s", "align conf", round(n["conf"], 2))
            for g in perf.gestures:
                print("  ", g, g.steps)
            print("   beats", [(round(b[0], 2), b[1]) for b in perf.beats], "nods", [round(x[0], 2) for x in perf.nods])
        if a.peaks and isinstance(perf, cg.Performance):
            peaks(frame, perf, os.path.join(a.out, name))
        if not a.no_video:
            encode(frame, audio, total, W, H, a.fps, os.path.join(a.out, name + ".mp4"), music)

    if a.animals:
        animal_group(os.path.join(a.out, "animal_cast_all.jpg"), a.store)
    if a.talk:
        for cid in ORDER + [c for c in ANIMALS if c in (a.only or [])]:
            if a.only and cid not in a.only:
                continue
            run(f"talk_{cid}", build_talk(cid, W, H, a.fps, a.store, a.cache))
    for cid in a.compare or []:
        run(f"compare_{cid}", build_compare(cid, W, H, a.fps, a.store, a.cache))
    if a.team:
        run("team", build_team(W, H, a.fps, a.store, a.cache))
    if a.framing:
        framing_sheet(os.path.join(a.out, "framing_presets.jpg"), a.store)
        for cid, size, preset, side in (("priya", (720, 1280), "waist_up", "right"), ("mateo", (1080, 1080), "three_quarter", "left"), ("fox", (864, 1080), "full", "right")):
            if a.only and cid not in a.only:
                continue
            w, h = size
            frame, audio, total, perf, n = build_talk(cid, w, h, a.fps, a.store, a.cache, preset, side)
            if not a.no_video:
                encode(frame, audio, total, w, h, a.fps, os.path.join(a.out, f"framing_{cid}_{w}x{h}.mp4"), music)
    return 0


if __name__ == "__main__":
    sys.exit(main())
