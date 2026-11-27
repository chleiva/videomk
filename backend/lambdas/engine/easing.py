

def clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def progress(t: float, start: float, dur: float) -> float:
    """0..1 progress of an animation that starts at `start` and lasts `dur` seconds."""
    if dur <= 0:
        return 1.0 if t >= start else 0.0
    return clamp01((t - start) / dur)


def linear(p: float) -> float:
    return clamp01(p)


def ease_out_cubic(p: float) -> float:
    p = clamp01(p)
    return 1 - (1 - p) ** 3


def ease_in_out_cubic(p: float) -> float:
    p = clamp01(p)
    return 4 * p ** 3 if p < 0.5 else 1 - ((-2 * p + 2) ** 3) / 2


def ease_out_back(p: float, s: float = 1.4) -> float:
    p = clamp01(p)
    c3 = s + 1
    return 1 + c3 * (p - 1) ** 3 + s * (p - 1) ** 2


def ease_out_expo(p: float) -> float:
    p = clamp01(p)
    return 1.0 if p >= 1 else 1 - 2 ** (-10 * p)


def smoothstep(p: float) -> float:
    p = clamp01(p)
    return p * p * (3 - 2 * p)


def reveal_times(n: int, duration: float, cues=None, first=0.10, last=0.72):
    """Start time (seconds, scene-local) for each of n revealed items.

    Uses narration cues when supplied, else spreads items between `first` and `last` of the scene.
    """
    if cues and len(cues) >= n:
        return [max(0.0, float(c)) for c in cues[:n]]
    if n <= 1:
        return [duration * first]
    a, b = duration * first, duration * last
    return [a + (b - a) * i / (n - 1) for i in range(n)]


COUNT_RUN_S = 1.5     # a count-up lasts about a second and a half (1.2 to 1.8 s is the range the best apps use), never more than 40% of the scene
COUNT_FLOOR = 0.2     # a number that counts up from nothing starts at 20% of its value: no frame ever reads as "0 <unit>", and no static zero is shown before the count


def count_run(scene_dur: float, run: float = COUNT_RUN_S) -> float:
    """Seconds the count takes: `run`, at most 40% of the scene, at least half a second."""
    return max(0.5, min(run, 0.4 * float(scene_dur)))


def count_up(lt: float, scene_dur: float, floor: float = COUNT_FLOOR) -> float:
    """Fraction of the final value to show at scene time `lt`: starts at once (no hold), eases out (fast, then settling), holds exactly 1.0 after `count_run`.
    `floor` is where it starts (0.2 when a number counts up from nothing; 0.0 only when the director gave an explicit start value)."""
    return floor + (1.0 - floor) * ease_out_cubic(progress(lt, 0.0, count_run(scene_dur)))
