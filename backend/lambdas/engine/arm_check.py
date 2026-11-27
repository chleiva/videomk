"""The arm instrument: measures what a character's arms do, frame by frame, and counts what a viewer reads as a defect (docs/PRESENTERS.md "Arms").

Pure maths on the solved skeleton (engine/vector_presenter.solve): no pixels, so the whole matrix (every character x gesture x transition x side) runs in a test.

Angles are measured from straight DOWN, positive AWAY from the body, for either arm:
  upper   the upper arm (shoulder -> elbow)        0 = hanging, 90 = straight out to the side
  fore    the forearm (elbow -> wrist)
  bend    fore - upper: the elbow. Positive = the forearm is turned further out / up than the upper arm ("open" side), negative = the forearm comes in across the body
  flex    the hand against the forearm (the wrist)

What is counted (thresholds are the constants below; they are the stated limits of the rig, tests hold the animation to them):
  wrong_way      a frame in which an arm is in a shape no arm takes in a front view:
                   tucked   the elbow inside the shoulder line (upper < TUCK_MIN): the upper arm crosses the chest and the forearm sticks out of the belly
                   wiper    the forearm swung out sideways from an upper arm that still hangs: the elbow is more than WIPER_TOL short of
                            ELBOW_OUT(forearm angle). Reads as an elbow broken sideways, the "windscreen wiper"
                   limit    the elbow past its joint limits (bend outside [BEND_MIN, BEND_MAX]) or the wrist past its (|flex| > FLEX_MAX)
                   flip     the elbow changes the side it bends to while the arm is raised or fast (upper > FLIP_UPPER, or faster than FLIP_SPEED): a snap through straight
  discontinuity  a frame in which a segment turns faster than SPEED_MAX, changes its speed by more than ACCEL_MAX, or the wrist falls faster than DROP_MAX
  stretch        a bone whose length is not its own (more than STRETCH_TOL off)
  penetration    the hand over the character's own face, across the body's centre line, or (when `keep_out` is given: the card's text area or the board, and
                 the body of another figure) inside that
  twin           both arms move and mirror each other (same angles within TWIN_DEG) for TWIN_RUN frames or more in a row: symmetric flapping
  dead           DEAD_S of rest during which neither bone of an arm turns DEAD_DEG (a frozen figure), or the forearm turns more than FIDGET_DEG (fidgeting)
DROP_MAX: a limp arm let go from the horizontal reaches about 7 arm lengths a second at the wrist (sqrt(3 g L)); a hand that is PUT down stays under 2.6.
"""
import math
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

Vec = Tuple[float, float]

TUCK_MIN = -6.0          # degrees: the upper arm may not swing further in than this
WIPER_TOL = 4.0          # degrees the elbow may be short of what the forearm's angle asks for (elbow_out)
# forearm angle -> how far out the upper arm must be. Stated here on its own (the rig's rule in vector_presenter.elbow_need is the same curve: a test compares them).
ELBOW_OUT = ((22.0, 0.0), (60.0, 19.0), (95.0, 7.0), (140.0, 2.0))
BEND_MIN, BEND_MAX = -150.0, 150.0
FLEX_MAX = 50.0
FLIP_UPPER = 38.0        # the elbow may pass through straight only while the upper arm is below this ...
FLIP_SPEED = 300.0       # ... and the bend changes slower than this (degrees per second)
FLIP_BAND = 3.0          # a bend smaller than this is "straight" (no side)
SPEED_MAX = 400.0        # degrees per second, any segment (13 degrees a frame at 30 fps)
ACCEL_MAX = 4500.0       # degrees per second squared (the speed may change by 5 degrees a frame, per frame)
DROP_MAX = 2.6           # arm lengths per second: the fastest a wrist may fall
STRETCH_TOL = 0.005
TWIN_DEG = 3.0
TWIN_RUN = 4
TWIN_SPEED = 90.0        # "moving": faster than this (degrees per second)
DEAD_DEG = 0.5           # peak-to-peak turn of the forearm within DEAD_S that still counts as alive
DEAD_S = 3.0
FIDGET_DEG = 18.0        # ... and more than this at rest is fidgeting
MIDLINE = 4.0            # units a wrist may cross the body's centre line (hands held together touch it)

CLASSES = ("wrong_way", "discontinuity", "stretch", "penetration", "twin", "dead")


def _wrap(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


def elbow_out(fore: float) -> float:
    if fore <= ELBOW_OUT[0][0]:
        return 0.0
    for (x0, y0), (x1, y1) in zip(ELBOW_OUT, ELBOW_OUT[1:]):
        if fore <= x1:
            return y0 + (y1 - y0) * (fore - x0) / (x1 - x0)
    return ELBOW_OUT[-1][1]


def _ang(v: Vec, side: int) -> float:
    return math.degrees(math.atan2(side * v[0], -v[1]))


def arm_state(sk: Dict[str, Any], i: int) -> Dict[str, float]:
    """Angles and lengths of arm i (0 = left of the picture, 1 = right) of a solved skeleton."""
    side = -1 if i == 0 else 1
    s, e, w, h = sk["shoulders"][i], sk["elbows"][i], sk["wrists"][i], sk["hand_dir"][i]
    up, fo = (e[0] - s[0], e[1] - s[1]), (w[0] - e[0], w[1] - e[1])
    upper, fore, hand = _ang(up, side), _ang(fo, side), _ang(h, side)
    if fore - upper < -180.0:                        # a forearm past straight up is 180 and more, not -180 and less
        fore += 360.0
    return {"upper": upper, "fore": fore, "bend": _wrap(fore - upper), "flex": _wrap(hand - fore), "len_u": math.hypot(*up), "len_f": math.hypot(*fo),
            "sx": s[0], "sy": s[1], "ex": e[0], "ey": e[1], "wx": w[0], "wy": w[1], "hx": h[0], "hy": h[1]}


def track(pose_at: Callable[[float], Tuple[Dict[str, Any], Dict[str, Any]]], t0: float, t1: float, fps: float = 30.0) -> List[Dict[str, Any]]:
    """Every frame of [t0, t1): pose_at(t) -> (skeleton, pose). -> [{t, arms: [state, state], neck, waist, head_dx}] with the angles unwrapped in time."""
    out: List[Dict[str, Any]] = []
    n = int(round((t1 - t0) * fps))
    prev: Optional[List[Dict[str, float]]] = None
    for k in range(n):
        t = t0 + k / fps
        sk, pose = pose_at(t)
        arms = [arm_state(sk, 0), arm_state(sk, 1)]
        if prev is not None:
            for a, p in zip(arms, prev):
                for key in ("upper", "fore"):
                    a[key] = p[key] + _wrap(a[key] - p[key])
        prev = arms
        out.append({"t": t, "arms": arms, "neck": sk["neck"], "waist": sk["waist"], "head_dx": pose.get("head_dx", 0.0), "head_dy": pose.get("head_dy", 0.0),
                    "shapes": pose.get("hand_shape", ("relaxed", "relaxed"))})
    return out


def check(frames: Sequence[Dict[str, Any]], geom: Any, fps: float = 30.0, active: Optional[Callable[[float], bool]] = None, head_w: float = 92.0,
          keep_out: Optional[Callable[[Vec], bool]] = None, cuts: Sequence[int] = ()) -> Dict[str, Any]:
    """Counts per defect class over a tracked stretch. `active(t)`: is a gesture (or a move between rest poses) under way at t; rest is everything else (for `dead`).
    `keep_out(point)`: True when a point (units, the skeleton's frame) is where a hand must not be (the card, another figure). `cuts`: frame indices that START a new
    shot (speeds are not measured across them, but the JUMP is: a pose that differs across a cut is a discontinuity).
    -> {class: number of frames, "detail": {name: [frame indices]}, "peak": {speed, accel, drop, bend_min, bend_max, upper_min, rest_move}}"""
    A = geom.arm
    d: Dict[str, List[int]] = {k: [] for k in ("tucked", "wiper", "limit", "flip", "speed", "accel", "drop", "cut", "stretch", "face", "midline", "keep_out", "twin", "dead", "fidget")}
    peak = {"speed": 0.0, "accel": 0.0, "drop": 0.0, "bend_min": 999.0, "bend_max": -999.0, "upper_min": 999.0, "upper_max": -999.0, "cut_jump": 0.0, "rest_move": None}
    cutset = set(cuts)
    n = len(frames)
    for k, f in enumerate(frames):
        for i, a in enumerate(f["arms"]):
            peak["bend_min"], peak["bend_max"] = min(peak["bend_min"], a["bend"]), max(peak["bend_max"], a["bend"])
            peak["upper_min"], peak["upper_max"] = min(peak["upper_min"], a["upper"]), max(peak["upper_max"], a["upper"])
            if a["upper"] < TUCK_MIN:
                d["tucked"].append(k)
            if a["upper"] < elbow_out(a["fore"]) - WIPER_TOL:
                d["wiper"].append(k)
            if not (BEND_MIN - 0.01 <= a["bend"] <= BEND_MAX + 0.01) or abs(a["flex"]) > FLEX_MAX + 0.01:
                d["limit"].append(k)
            if abs(a["len_u"] / geom.upper - 1.0) > STRETCH_TOL or abs(a["len_f"] / geom.fore - 1.0) > STRETCH_TOL:
                d["stretch"].append(k)
            side = -1 if i == 0 else 1
            # the hand as a disc half way to the finger tips
            hx, hy = a["wx"] + a["hx"] * 0.5 * geom.hand, a["wy"] + a["hy"] * 0.5 * geom.hand
            hcx, hcy = f["neck"][0] + f["head_dx"], f["neck"][1] + 50.0 + f["head_dy"]
            if ((hx - hcx) / (0.5 * head_w + 0.3 * geom.hand)) ** 2 + ((hy - hcy) / (50.0 + 0.3 * geom.hand)) ** 2 < 0.80:
                d["face"].append(k)
            if side * (a["wx"] - f["waist"][0]) < -MIDLINE:
                d["midline"].append(k)
            if keep_out is not None and (keep_out((hx, hy)) or keep_out((a["wx"] + a["hx"] * geom.hand, a["wy"] + a["hy"] * geom.hand))):
                d["keep_out"].append(k)
            if k == 0:
                continue
            p = frames[k - 1]["arms"][i]
            if k in cutset:
                jump = max(abs(a["upper"] - p["upper"]), abs(a["fore"] - p["fore"]), abs(_wrap(a["flex"] - p["flex"])))
                peak["cut_jump"] = max(peak["cut_jump"], jump)
                if jump > 2.0:
                    d["cut"].append(k)
                continue
            vu, vf = (a["upper"] - p["upper"]) * fps, (a["fore"] - p["fore"]) * fps
            vh = vf + _wrap(a["flex"] - p["flex"]) * fps
            sp = max(abs(vu), abs(vf), abs(vh))
            peak["speed"] = max(peak["speed"], sp)
            if sp > SPEED_MAX:
                d["speed"].append(k)
            drop = -((a["wy"] - a["sy"]) - (p["wy"] - p["sy"])) * fps / A
            peak["drop"] = max(peak["drop"], drop)
            if drop > DROP_MAX:
                d["drop"].append(k)
            if (a["bend"] > FLIP_BAND and p["bend"] < -FLIP_BAND) or (a["bend"] < -FLIP_BAND and p["bend"] > FLIP_BAND) or (abs(a["bend"]) <= FLIP_BAND and abs(p["bend"]) > FLIP_BAND):
                if a["upper"] > FLIP_UPPER or abs(_wrap(a["bend"] - p["bend"])) * fps > FLIP_SPEED:
                    d["flip"].append(k)
            if k >= 2 and (k - 1) not in cutset:
                q = frames[k - 2]["arms"][i]
                au, af = (a["upper"] - 2 * p["upper"] + q["upper"]) * fps * fps, (a["fore"] - 2 * p["fore"] + q["fore"]) * fps * fps
                ac = max(abs(au), abs(af))
                peak["accel"] = max(peak["accel"], ac)
                if ac > ACCEL_MAX:
                    d["accel"].append(k)
        if k > 0 and k not in cutset:
            l, r, pl, pr = f["arms"][0], f["arms"][1], frames[k - 1]["arms"][0], frames[k - 1]["arms"][1]
            moving = min(abs(l["fore"] - pl["fore"]), abs(r["fore"] - pr["fore"])) * fps > TWIN_SPEED and (l["fore"] - pl["fore"]) * (r["fore"] - pr["fore"]) > 0
            if moving and abs(l["fore"] - r["fore"]) < TWIN_DEG and abs(l["upper"] - r["upper"]) < TWIN_DEG:
                d["twin"].append(k)
    # rest: windows of DEAD_S without a gesture
    win = int(round(DEAD_S * fps))
    moves: List[float] = []
    if active is not None and n >= win:
        rest = [not active(f["t"]) for f in frames]
        k = 0
        while k + win <= n:
            if all(rest[k:k + win]) and not any((k + j) in cutset for j in range(1, win)):
                for i in (0, 1):
                    vals = [frames[k + j]["arms"][i]["fore"] for j in range(win)]
                    ups = [frames[k + j]["arms"][i]["upper"] for j in range(win)]
                    mv = max(max(vals) - min(vals), max(ups) - min(ups))
                    moves.append(mv)
                    if mv < DEAD_DEG:
                        d["dead"].extend(range(k, k + win))
                    if mv > FIDGET_DEG:
                        d["fidget"].extend(range(k, k + win))
                k += win
            else:
                k += 1
        if moves:
            peak["rest_move"] = (round(min(moves), 2), round(max(moves), 2))
    runs, run = [], []
    for k in sorted(set(d["twin"])):
        if run and k != run[-1] + 1:
            runs += run if len(run) >= TWIN_RUN else []
            run = []
        run.append(k)
    d["twin"] = runs + (run if len(run) >= TWIN_RUN else [])
    det = {k: sorted(set(v)) for k, v in d.items()}
    groups = {"wrong_way": ("tucked", "wiper", "limit", "flip"), "discontinuity": ("speed", "accel", "drop", "cut"), "stretch": ("stretch",),
              "penetration": ("face", "midline", "keep_out"), "twin": ("twin",), "dead": ("dead", "fidget")}
    out: Dict[str, Any] = {g: len(set().union(*[det[k] for k in ks])) for g, ks in groups.items()}
    out["frames"] = n
    out["detail"] = det
    out["peak"] = {k: (round(v, 1) if isinstance(v, float) else v) for k, v in peak.items()}
    return out


def add(total: Dict[str, Any], res: Dict[str, Any]) -> Dict[str, Any]:
    """Accumulate `check` results (counts and peaks) into `total` (start with {})."""
    for k in CLASSES + ("frames",):
        total[k] = total.get(k, 0) + res[k]
    det = total.setdefault("detail", {})
    for k, v in res["detail"].items():
        det[k] = det.get(k, 0) + len(v)
    pk = total.setdefault("peak", {})
    for k, v in res["peak"].items():
        if not isinstance(v, (int, float)):
            continue
        pk[k] = v if k not in pk else (min(pk[k], v) if k.endswith("_min") else max(pk[k], v))
    return total


# ----------------------------------------------------------------------------- the matrix (what the tests and backend/scripts/presenter_arms.py run)
LINES = {
    "en_greet": "Hello, friends! Today we look at three things: water, light, and air. This is very important, but it is not hard. Why does it happen? Look at this picture here. Great, exactly! Thanks, goodbye!",
    "en_plain": "Leaves make food from sunlight during the long summer days. When autumn comes the green fades slowly away. The tree keeps what it needs and lets the rest go.",
    "es_mix": "Hola, amigos. Primero el agua sube, segundo se enfría, y tercero cae como lluvia. Es muy importante, pero no es difícil. ¿Por qué pasa esto? Mira aquí. ¡Perfecto! Gracias, adiós.",
    "de_talk": "Bruno, warum werden die Blätter im Herbst bunt und fallen dann einfach vom Baum? Gute Frage, Fox! Im Sommer machen die Blätter mit grünem Blattgrün Nahrung aus Sonnenlicht.",
}


def fake_words(text: str, t0: float = 0.35, rate: float = 1.0) -> List[Tuple[str, float, float]]:
    """Word timings for a line without a voice: about 0.07 s a letter, a short gap between words, a pause after a sentence."""
    out, t = [], t0
    for w in text.split():
        d = (0.12 + 0.065 * len(w.strip(".,;:!?¿¡"))) / rate
        out.append((w, round(t, 3), round(t + d, 3)))
        t += d + (0.42 if w[-1:] in ".!?" else 0.16 if w[-1:] in ",;:" else 0.05)
    return out


def scenarios(kinds: Sequence[str], make: Callable[..., Any], pairs: bool = True, overlap: bool = False) -> List[Tuple[str, str, Any, float, float]]:
    """-> [(group, name, performance, t0, t1)]. `make(seed, content_side, lift)` builds an empty Performance. Groups: one gesture alone (each hand, each side of the
    content, low and raised framing), every ordered pair of gestures (the second as soon as the planner would allow; with `overlap` also cutting into the first one's
    hold), spoken lines (speaker), a listener."""
    out: List[Tuple[str, str, Any, float, float]] = []
    two = ("open", "shrug", "compare")
    for kind in kinds:
        for cs in (-1, 1):
            for lift in (0.0, 0.14):
                for hand in (("both",) if kind in two else ("l", "r")):
                    p = make(0.37, cs, lift)
                    p.gesture(kind, 1.3, 1.1, None if hand == "both" else hand, cs if kind == "present" else 0)
                    out.append((kind, f"{kind}/{hand}/content{cs:+d}/lift{lift}", p, 0.0, 4.6))
    if pairs:
        for a in kinds:
            for b in kinds:
                for cs in (-1, 1):
                    for mode in (("after", "cut") if overlap else ("after",)):
                        p = make(0.61, cs, 0.14)
                        p.gesture(a, 1.3, 0.9, None, cs if a == "present" else 0)
                        ga = p.gestures[-1]
                        p.gesture(b, (ga.t1 + 0.75) if mode == "after" else (ga.stroke + 0.55), 0.9, None, cs if b == "present" else 0)
                        out.append((f"{a}>{b}", f"{a}>{b}/{mode}/content{cs:+d}", p, 0.0, max(g.t1 for g in p.gestures) + 1.2))
    for key, text in LINES.items():
        for cs in (-1, 1):
            for seed in (0.13, 0.58, 0.91):
                for lift in (0.0, 0.14):
                    w = fake_words(text)
                    p = make(seed, cs, lift)
                    p.speak(w, None, w[-1][2])
                    out.append(("speech", f"speech/{key}/content{cs:+d}/seed{seed}/lift{lift}", p, 0.0, w[-1][2] + 1.5))
    for toward in (-1.0, 1.0):
        for seed in (0.13, 0.58):
            w = fake_words(LINES["en_plain"])
            p = make(seed, int(-toward), 0.14)
            p.listen(0.1, w[-1][2] + 0.1, toward, [a for (x, a, b) in w if len(x) > 5])
            out.append(("listen", f"listen/toward{toward:+.0f}/seed{seed}", p, 0.0, w[-1][2] + 1.0))
    return out


# ----------------------------------------------------------------------------- whole scenes (the element: layout, room, cuts)
TALK = (("fox", "Hello, friends! Bruno, why do the leaves turn yellow and red and then fall from the tree?"),
        ("bear", "Great question! In summer the leaves make food from sunlight with a green helper."),
        ("fox", "Oh! And in autumn the green goes away, but the yellow was always there?"),
        ("bear", "Exactly. First the tree takes the food back, second the leaf dries, and third it falls."),
        ("fox", "So the tree is getting ready for winter. Thanks, Bruno, and goodbye, everyone!"))


def conversation(cast: Sequence[str], talk: Sequence[Tuple[str, str]] = TALK, start: float = 0.0) -> List[Dict[str, Any]]:
    """Scenes of a conversation as the timeline links them: the speakers of `talk` are mapped onto `cast` in order of appearance (one name: a single presenter)."""
    from engine import align, presenter_policy
    from engine.scenes import ELEMENTS

    names: List[str] = []
    for who, _ in talk:
        if who not in names:
            names.append(who)
    scenes, t = [], start
    for i, (who, text) in enumerate(talk):
        speaker = cast[names.index(who) % len(cast)]
        words = [list(w) for w in align.estimate_words(text, 0.36 * len(text.split()) + 0.6, lead=0.4)]
        dur = round(words[-1][2] + 0.55, 3)
        props = {"character": speaker, "heading": "Why leaves fall", "points": ["Green fades", "Yellow shows", "Leaf drops"][: 1 + i % 3]}
        if len(cast) >= 2:
            props["cast"] = list(cast)
        scenes.append({"id": f"s{i + 1}", "type": "presenter", "start": round(t, 4), "duration": dur, "props": ELEMENTS["presenter"].sanitize(props), "words": words})
        t += dur
    presenter_policy.link(scenes)
    return scenes


def scene_tracks(scenes: Sequence[Dict[str, Any]], aspect: str = "16:9", fps: float = 30.0) -> Dict[str, Dict[str, Any]]:
    """Every character of every scene, tracked through the whole run -> {character: {frames, cuts, geom, result}}. The hands are checked against the content box
    and the other figures of each scene's layout (`keep_out`), and the pose is compared across every cut."""
    from engine import vector_presenter as vp
    from engine.frame import Frame
    from engine.scenes.base import SceneCtx
    from engine.scenes.elements import presenter as el

    ctx = SceneCtx(frame=Frame.parse(aspect, "720p"), captions=True)
    out: Dict[str, Dict[str, Any]] = {}
    for sc in scenes:
        props, dur = sc["props"], float(sc["duration"])
        lay = el.layout(props, ctx)
        figs = lay.get("figures") or [None]
        for fig in figs:
            cid = fig["character"] if fig else props["character"]
            ch = vp.load(cid, 0.5)
            g, size = ch.g, el.CAST[cid]["size"]
            x = fig["x"] if fig else lay["x"]
            u = (fig["ppu"] if fig else lay["ppu"]) * size
            ground = fig["ground"] if fig else lay["ground"]
            pad = 0.0 if (props.get("board") or props.get("asset")) else getattr(el, "CARD_PAD", 36.0)
            kw = {"room": el.rooms(lay, fig, g, size, ctx.frame.W, pad)} if hasattr(el, "rooms") else {}
            perf = el.performance(props, dur, fig["lift"] if fig else lay["lift"], "left" if (fig["content_side"] if fig else (1 if lay["side"] == "left" else -1)) > 0 else "right",
                                  cid, fig["slot"] if fig else 0, fig["toward"] if fig else 0.0, fig["content_side"] if fig else None, **kw)
            x0, y0, x1, y1 = lay["content"]
            x0, x1 = x0 + pad, x1 - pad
            beside = x1 > x0 and y1 > ground - 215.0 * u
            others = [(o["x"], 40.0 * o["ppu"]) for o in figs if o is not None and o is not fig]

            def keep_out(pt: Vec, x=x, u=u, ground=ground, beside=beside, box=(x0, y0, x1, y1), others=others, W=ctx.frame.W) -> bool:
                X, Y = x + pt[0] * u, ground - pt[1] * u
                if beside and box[0] <= X <= box[2] and box[1] <= Y <= box[3]:
                    return True
                return any(abs(X - ox) < half for ox, half in others)

            rec = out.setdefault(cid, {"frames": [], "cuts": [], "geom": g, "hits": [], "active": [], "head_w": ch.hw})
            n0 = len(rec["frames"])
            if n0:
                rec["cuts"].append(n0)

            def pose_at(t: float, perf=perf, g=g):
                pose, _ = perf.pose(t, g)
                return vp.solve(g, pose), pose

            fr = track(pose_at, 0.0, dur, fps)
            if rec["frames"]:                                  # keep the angles continuous across the cut (the same unwrapping as inside a scene)
                for a, p in zip(fr[0]["arms"], rec["frames"][-1]["arms"]):
                    for key in ("upper", "fore"):
                        d = _wrap(a[key] - p[key]) - (a[key] - p[key])
                        if abs(d) > 1.0:
                            for f in fr:
                                f["arms"][fr[0]["arms"].index(a)][key] += d
            res = check(fr, g, fps, head_w=ch.hw, keep_out=keep_out)
            rec["hits"] += [n0 + k for k in res["detail"]["keep_out"]]
            rec["active"] += [any(q.t0 - 0.1 <= f["t"] <= q.t1 + 0.6 for q in perf.gestures) or (hasattr(perf, "folded") and (0.001 < perf.folded(f["t"], 0) < 0.999 or 0.001 < perf.folded(f["t"], 1) < 0.999)) or any(abs(f["t"] - b[0]) < 0.7 for b in perf.beats) for f in fr]
            rec["frames"] += [dict(f, t=f["t"] + float(sc["start"])) for f in fr]
    for cid, rec in out.items():
        act = rec["active"]
        t0 = rec["frames"][0]["t"]
        res = check(rec["frames"], rec["geom"], fps, active=lambda t, act=act, t0=t0: act[min(len(act) - 1, max(0, int(round((t - t0) * fps))))], head_w=rec["head_w"], cuts=rec["cuts"])
        res["detail"]["keep_out"] = sorted(set(rec["hits"]))
        res["penetration"] = len(set(res["detail"]["face"]) | set(res["detail"]["midline"]) | set(rec["hits"]))
        rec["result"] = res
    return out
