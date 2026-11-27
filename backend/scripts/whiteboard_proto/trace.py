"""From a marker drawing to a hidden, ordered reveal path (own code: NumPy + SciPy only, no GPL tracer).

  cut_sheet(png)            -> the separate drawings of a generated sheet (ink alpha, 0..1 float)
  skeleton(mask)            -> one-pixel centre line (Zhang-Suen thinning, vectorised with look-up tables)
  segments(skel, width)     -> the centre line as a graph: polyline pieces between junctions and ends, short spurs dropped
  order_scan(segs)          -> strategy A, the naive baseline: every piece on its own, top to bottom, as traced
  order_human(segs, shape)  -> strategy B: pieces joined through junctions by good continuation into long strokes, the big outline first,
                               then the rest by shortest pen travel with a preferred direction (left to right, top to bottom, clockwise)
  time_map(alpha, strokes)  -> for every ink pixel, WHEN the pen passes it (0..1 of the drawing's pen time). The art is never redrawn:
                               a frame shows the real art where time_map <= progress. That is the reveal.
"""
import math
from typing import Dict, List, Tuple

import numpy as np
from scipy import ndimage

Stroke = np.ndarray  # (n, 2) float, x then y, in the drawing's own pixels


# ----------------------------------------------------------------------------- cutting a sheet
def load_ink(path: str) -> np.ndarray:
    """-> ink amount 0..1. The image model returns black ink either on white or on a transparent background."""
    from PIL import Image

    im = Image.open(path)
    if im.mode == "RGBA":
        a = np.asarray(im, np.float32) / 255.0
        ink_a = a[..., 3] * (1.0 - a[..., :3].mean(axis=2))
        if a[..., 3].mean() > 0.9:  # opaque picture on white
            ink_a = 1.0 - a[..., :3].mean(axis=2)
        return ink_a
    return 1.0 - np.asarray(im.convert("L"), np.float32) / 255.0


def cut_sheet(ink: np.ndarray, cols: int, rows: int, pad: int = 14) -> List[np.ndarray]:
    """The drawings of a sheet in reading order. Ink is grouped by closeness (a sun's rays belong to the sun), then each group goes to the grid cell of its centre."""
    mask = ink > 0.5
    lab, n = ndimage.label(ndimage.binary_dilation(mask, iterations=1), structure=np.ones((3, 3)))
    H, W = mask.shape
    boxes: Dict[Tuple[int, int], List[int]] = {}
    for i, sl in enumerate(ndimage.find_objects(lab), 1):
        comp = lab[sl] == i
        if comp.sum() < 30:
            continue
        ys, xs = np.nonzero(comp)
        cy, cx = ys.mean() + sl[0].start, xs.mean() + sl[1].start
        cell = (min(rows - 1, int(cy / H * rows)), min(cols - 1, int(cx / W * cols)))
        b = boxes.setdefault(cell, [W, H, 0, 0])
        b[0], b[1] = min(b[0], sl[1].start), min(b[1], sl[0].start)
        b[2], b[3] = max(b[2], sl[1].stop), max(b[3], sl[0].stop)
    out = []
    for r in range(rows):
        for c in range(cols):
            x0, y0, x1, y1 = boxes[(r, c)]
            out.append(np.pad(ink[y0:y1, x0:x1], pad))
    return out


# ----------------------------------------------------------------------------- thinning
def _luts():
    s1, s2 = np.zeros(256, bool), np.zeros(256, bool)
    for code in range(256):
        p = [(code >> i) & 1 for i in range(8)]          # P2..P9 = N, NE, E, SE, S, SW, W, NW
        b = sum(p)
        a = sum(1 for i in range(8) if p[i] == 0 and p[(i + 1) % 8] == 1)
        if 2 <= b <= 6 and a == 1:
            s1[code] = p[0] * p[2] * p[4] == 0 and p[2] * p[4] * p[6] == 0
            s2[code] = p[0] * p[2] * p[6] == 0 and p[0] * p[4] * p[6] == 0
    return s1, s2


_S1, _S2 = _luts()
_NB = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]


def _codes(m: np.ndarray) -> np.ndarray:
    p = np.pad(m, 1).astype(np.uint8)
    H, W = m.shape
    code = np.zeros((H, W), np.uint8)
    for i, (dy, dx) in enumerate(_NB):
        code |= p[1 + dy:1 + dy + H, 1 + dx:1 + dx + W] << i
    return code


def skeleton(mask: np.ndarray) -> np.ndarray:
    m = mask.copy()
    while True:
        changed = False
        for lut in (_S1, _S2):
            kill = m & lut[_codes(m)]
            if kill.any():
                m &= ~kill
                changed = True
        if not changed:
            break
    # Zhang-Suen leaves staircase corners (two 4-neighbours that already touch diagonally): remove them so every line pixel has exactly two neighbours
    for a, b, opp in ((0, 2, (4, 5, 6)), (2, 4, (6, 7, 0)), (4, 6, (0, 1, 2)), (6, 0, (2, 3, 4))):
        code = _codes(m)
        has = ((code >> a) & 1) & ((code >> b) & 1)
        free = np.ones_like(has)
        for o in opp:
            free &= 1 - ((code >> o) & 1)
        m &= ~((has & free).astype(bool))
    return m


def line_width(mask: np.ndarray, skel: np.ndarray) -> float:
    """Median marker width in pixels, measured on the centre line."""
    d = ndimage.distance_transform_edt(mask)
    return float(np.median(d[skel]) * 2.0 - 1.0) if skel.any() else 1.0


# ----------------------------------------------------------------------------- centre line as a graph
class Seg:
    __slots__ = ("pts", "a", "b", "length")

    def __init__(self, pts: np.ndarray, a: int, b: int):
        self.pts, self.a, self.b = pts, a, b          # a, b: node ids at the two ends (-1: a closed loop with no node)
        d = np.diff(pts, axis=0)
        self.length = float(np.hypot(d[:, 0], d[:, 1]).sum())


def segments(skel: np.ndarray, width: float) -> Tuple[List[Seg], Dict[int, Tuple[float, float]]]:
    """-> (pieces, {node id: (x, y)}). Nodes are line ends and junctions (touching junction pixels count as one)."""
    H, W = skel.shape
    code = _codes(skel)
    deg = np.zeros((H, W), np.uint8)
    for i in range(8):
        deg += (code >> i) & 1
    deg[~skel] = 0
    junc = skel & (deg >= 3)
    jl, _ = ndimage.label(junc, structure=np.ones((3, 3)))
    node_of: Dict[Tuple[int, int], int] = {}
    nodes: Dict[int, Tuple[float, float]] = {}
    for i, sl in enumerate(ndimage.find_objects(jl), 1):
        ys, xs = np.nonzero(jl[sl] == i)
        for y, x in zip(ys + sl[0].start, xs + sl[1].start):
            node_of[(int(y), int(x))] = i
        nodes[i] = (float(xs.mean() + sl[1].start), float(ys.mean() + sl[0].start))
    nid = len(nodes) + 1
    for y, x in zip(*np.nonzero(skel & (deg <= 1))):
        node_of[(int(y), int(x))] = nid
        nodes[nid] = (float(x), float(y))
        nid += 1

    def nbrs(y, x):
        # 4-neighbours first, so a path never cuts a corner diagonally when a straight step exists
        for dy, dx in ((-1, 0), (0, 1), (1, 0), (0, -1), (-1, 1), (1, 1), (1, -1), (-1, -1)):
            yy, xx = y + dy, x + dx
            if 0 <= yy < H and 0 <= xx < W and skel[yy, xx]:
                yield yy, xx

    visited = np.zeros((H, W), bool)
    segs: List[Seg] = []
    done_pairs = set()
    for (y, x), n in list(node_of.items()):
        for sy, sx in nbrs(y, x):
            if (sy, sx) in node_of:
                m = node_of[(sy, sx)]
                key = (min(n, m), max(n, m))
                if m != n and key not in done_pairs:
                    done_pairs.add(key)
                    segs.append(Seg(np.array([nodes[n], nodes[m]], np.float32), n, m))
                continue
            if visited[sy, sx]:
                continue
            path = [nodes[n], (float(sx), float(sy))]
            visited[sy, sx] = True
            py, px, cy, cx = y, x, sy, sx
            end = None
            while end is None:
                nxt = None
                for yy, xx in nbrs(cy, cx):
                    if (yy, xx) == (py, px):
                        continue
                    if (yy, xx) in node_of:
                        if node_of[(yy, xx)] == n and len(path) < 4:
                            continue
                        end = node_of[(yy, xx)]
                        break
                    if not visited[yy, xx]:
                        nxt = (yy, xx)
                        break
                if end is not None:
                    path.append(nodes[end])
                    break
                if nxt is None:
                    end = -2
                    break
                visited[nxt] = True
                path.append((float(nxt[1]), float(nxt[0])))
                py, px, cy, cx = cy, cx, nxt[0], nxt[1]
            segs.append(Seg(np.array(path, np.float32), n, end if end != -2 else n))
    # closed loops that touch no node
    rest = skel & ~visited
    for (y, x) in node_of:
        rest[y, x] = False
    while rest.any():
        ys, xs = np.nonzero(rest)
        y, x = int(ys[0]), int(xs[0])
        path = [(float(x), float(y))]
        rest[y, x] = False
        cy, cx = y, x
        while True:
            nxt = next(((yy, xx) for yy, xx in nbrs(cy, cx) if rest[yy, xx]), None)
            if nxt is None:
                break
            rest[nxt] = False
            path.append((float(nxt[1]), float(nxt[0])))
            cy, cx = nxt
        if len(path) > 3:
            path.append(path[0])
            segs.append(Seg(np.array(path, np.float32), -1, -1))

    # drop spurs: a short piece with a free end hanging off a junction is thinning noise, not a pen stroke
    free_deg: Dict[int, int] = {}
    for s in segs:
        for e in (s.a, s.b):
            free_deg[e] = free_deg.get(e, 0) + 1
    keep = []
    for s in segs:
        ends_free = [free_deg.get(e, 0) == 1 for e in (s.a, s.b)]
        if s.a != -1 and any(ends_free) and not all(ends_free) and s.length < 1.3 * width:
            continue
        if s.length < 2.0 and s.a == s.b:
            continue
        keep.append(s)
    return keep, nodes


def _smooth(pts: np.ndarray, k: int = 5) -> np.ndarray:
    if len(pts) < k + 2:
        return pts
    closed = np.allclose(pts[0], pts[-1])
    ker = np.ones(k, np.float32) / k
    if closed:
        ext = np.concatenate([pts[-k:-1], pts, pts[1:k]])
        out = np.stack([np.convolve(ext[:, i], ker, "same") for i in (0, 1)], 1)[k - 1:k - 1 + len(pts)]
        out[-1] = out[0]
        return out
    out = np.stack([np.convolve(np.pad(pts[:, i], k // 2, mode="edge"), ker, "valid") for i in (0, 1)], 1)
    out[0], out[-1] = pts[0], pts[-1]
    return out


def _dir(pts: np.ndarray, at_start: bool, span: float = 14.0) -> np.ndarray:
    """Unit direction LEAVING the piece's end (pointing away from the junction into the piece)."""
    p = pts if at_start else pts[::-1]
    d = np.hypot(*(p - p[0]).T)
    j = int(np.searchsorted(d, span)) if d[-1] > span else len(p) - 1
    v = p[max(1, j)] - p[0]
    n = float(np.hypot(*v)) or 1.0
    return v / n


def length_of(pts: np.ndarray) -> float:
    d = np.diff(pts, axis=0)
    return float(np.hypot(d[:, 0], d[:, 1]).sum())


# ----------------------------------------------------------------------------- strategy A: the naive baseline
def order_scan(segs: List[Seg]) -> List[Stroke]:
    """Every traced piece is its own stroke, in the order a scan finds them (top to bottom), drawn in the direction it was traced."""
    out = [_smooth(s.pts) for s in segs]
    out.sort(key=lambda p: (p[:, 1].min(), p[:, 0].min()))
    return out


# ----------------------------------------------------------------------------- strategy B: join, outline first, shortest travel
def join_strokes(segs: List[Seg], max_turn_deg: float = 62.0) -> List[Stroke]:
    """Pieces that meet at a junction are joined when one continues the other (the smallest turn wins); where exactly two pieces meet they are always one stroke
    (a pen does not lift at a corner)."""
    ends: Dict[int, List[Tuple[int, bool]]] = {}
    for i, s in enumerate(segs):
        if s.a == -1:
            continue
        ends.setdefault(s.a, []).append((i, True))
        ends.setdefault(s.b, []).append((i, False))
    link: Dict[Tuple[int, bool], Tuple[int, bool]] = {}
    for node, es in ends.items():
        if len(es) < 2:
            continue
        cand = []
        for i in range(len(es)):
            for j in range(i + 1, len(es)):
                (si, ai), (sj, aj) = es[i], es[j]
                if si == sj and len(es) > 2:
                    continue
                di, dj = _dir(segs[si].pts, ai), _dir(segs[sj].pts, aj)
                turn = math.degrees(math.acos(float(np.clip(-(di * dj).sum(), -1, 1))))    # 0 = straight on
                cand.append((turn, es[i], es[j]))
        cand.sort(key=lambda c: c[0])
        used = set()
        for turn, e1, e2 in cand:
            if e1 in used or e2 in used:
                continue
            if turn <= max_turn_deg or len(es) == 2:
                link[e1], link[e2] = e2, e1
                used.update((e1, e2))
    done = [False] * len(segs)
    strokes: List[Stroke] = []
    for i, s in enumerate(segs):
        if done[i]:
            continue
        if s.a == -1:
            done[i] = True
            strokes.append(_smooth(s.pts))
            continue
        # walk back to the stroke's beginning, then forward
        cur, at_start = i, True
        seen = {i}
        while (cur, at_start) in link:
            nxt, nstart = link[(cur, at_start)]
            if nxt in seen:
                break
            seen.add(nxt)
            cur, at_start = nxt, not nstart      # we arrive at nxt's `nstart` end; keep going out of its other end
        chain = []
        end_is_start = at_start                   # the free end of the first piece
        while True:
            done[cur] = True
            pts = segs[cur].pts if end_is_start else segs[cur].pts[::-1]
            chain.append(pts if not chain else pts[1:])
            leave = (cur, not end_is_start)
            if leave not in link:
                break
            nxt, nstart = link[leave]
            if done[nxt]:
                break
            cur, end_is_start = nxt, nstart
        pts = np.concatenate(chain)
        if length_of(pts) > 0 and np.hypot(*(pts[0] - pts[-1])) < 3.0 and len(pts) > 8:
            pts = np.concatenate([pts, pts[:1]])
        strokes.append(_smooth(pts))
    return strokes


def _is_closed(p: np.ndarray, tol: float = 4.0) -> bool:
    return len(p) > 8 and float(np.hypot(*(p[0] - p[-1]))) < tol


def _orient_closed(p: np.ndarray) -> np.ndarray:
    """A closed outline starts at its top (slightly left of the top) and runs clockwise: how most right-handers draw a circle or a cloud."""
    q = p[:-1]
    start = int(np.argmin(q[:, 1] + 0.15 * q[:, 0]))
    q = np.roll(q, -start, axis=0)
    area = 0.5 * float(np.sum(q[:, 0] * np.roll(q[:, 1], -1) - np.roll(q[:, 0], -1) * q[:, 1]))   # > 0: clockwise on screen (y down)
    if area < 0:
        q = np.concatenate([q[:1], q[1:][::-1]])
    return np.concatenate([q, q[:1]])


def _orient_open(p: np.ndarray) -> np.ndarray:
    """An open stroke on its own starts at its left end, or at its top end when it is mostly vertical."""
    dx, dy = p[-1] - p[0]
    if abs(dx) >= abs(dy):
        return p if dx >= 0 else p[::-1]
    return p if dy >= 0 else p[::-1]


def order_human(segs: List[Seg], shape: Tuple[int, int]) -> List[Stroke]:
    strokes = [s for s in join_strokes(segs) if len(s) >= 2]
    if not strokes:
        return []
    H, W = shape
    diag = math.hypot(H, W)

    def extent(p):
        return math.hypot(float(np.ptp(p[:, 0])), float(np.ptp(p[:, 1])))

    # the main outline: the stroke that spans most of the drawing (a long closed outline beats a long open line)
    score = [extent(p) * (1.35 if _is_closed(p) else 1.0) + 0.15 * length_of(p) for p in strokes]
    order = [int(np.argmax(score))]
    if not _is_closed(strokes[order[0]]):
        # several lines of about the same size (rows of waves, rain): there is no "main outline", a person starts with the top one
        peers = [i for i, sc in enumerate(score) if sc >= 0.8 * score[order[0]] and not _is_closed(strokes[i])]
        if len(peers) > 1:
            order = [min(peers, key=lambda i: float(strokes[i][:, 1].mean()) + 0.2 * float(strokes[i][:, 0].min()))]
    first = strokes[order[0]]
    out = [_orient_closed(first) if _is_closed(first) else _orient_open(first)]
    left = [i for i in range(len(strokes)) if i != order[0]]
    big = max(length_of(p) for p in strokes)
    pen = out[-1][-1]
    while left:
        best = None
        for i in left:
            p = strokes[i]
            L = length_of(p)
            tier = 0.0 if L > 0.45 * big else 0.35 * diag if L > 0.12 * big else 0.5 * diag     # long strokes before details, details before small marks
            if _is_closed(p):
                q = _orient_closed(p)
                c = float(np.hypot(*(q[0] - pen))) + tier
                cand = (c, i, q)
            else:
                cand = None
                for q in (p, p[::-1]):
                    travel = float(np.hypot(*(q[0] - pen)))
                    against = 0.0 if np.array_equal(q, _orient_open(p)) else 0.06 * diag     # mild preference for left-to-right / top-to-bottom
                    c = travel + against + tier
                    if cand is None or c < cand[0]:
                        cand = (c, i, q)
            if best is None or cand[0] < best[0]:
                best = cand
        _, i, q = best
        out.append(q)
        left.remove(i)
        pen = q[-1]
    return out


# ----------------------------------------------------------------------------- the reveal: when does the pen pass each ink pixel
def stroke_times(strokes: List[Stroke], travel_speed: float = 3.0) -> Tuple[List[np.ndarray], float]:
    """-> (per stroke: pen time at each point, in pen-length units), total. Moving between strokes with the pen up is `travel_speed` times faster than drawing."""
    t, out = 0.0, []
    prev = None
    for p in strokes:
        if prev is not None:
            t += float(np.hypot(*(p[0] - prev))) / travel_speed
        d = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(p, axis=0).T))])
        out.append(t + d)
        t += float(d[-1])
        prev = p[-1]
    return out, max(t, 1e-6)


def time_map(alpha: np.ndarray, strokes: List[Stroke], tip_radius: float) -> Tuple[np.ndarray, List[np.ndarray], float]:
    """-> (T, per-stroke point times 0..1, pen length). T[y, x] in 0..1 is when the pen uncovers that pixel of the art; 2.0 where there is no ink.
    Each ink pixel takes the time of the nearest centre-line point, moved a little earlier towards the middle of the line so the growing end is round like a marker tip."""
    H, W = alpha.shape
    times, total = stroke_times(strokes)
    tgrid = np.full((H, W), np.inf, np.float32)
    for p, tt in zip(strokes, times):
        # dense resample so every centre-line pixel gets a time
        d = np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(p, axis=0).T))])
        n = max(2, int(d[-1] * 2))
        u = np.linspace(0, d[-1], n)
        xs = np.clip(np.rint(np.interp(u, d, p[:, 0])).astype(int), 0, W - 1)
        ys = np.clip(np.rint(np.interp(u, d, p[:, 1])).astype(int), 0, H - 1)
        tv = np.interp(u, d, tt).astype(np.float32)
        np.minimum.at(tgrid, (ys, xs), tv)
    src = np.isfinite(tgrid)
    if not src.any():
        return np.full((H, W), 2.0, np.float32), [], 1.0
    dist, (iy, ix) = ndimage.distance_transform_edt(~src, return_indices=True)
    T = tgrid[iy, ix] - np.sqrt(np.clip(tip_radius ** 2 - dist ** 2, 0, None)).astype(np.float32)
    # where strokes meet, ink nearest to the LATER stroke would stay white until that stroke comes: the earliest pen pass within a tip's reach wins
    T = np.where(alpha >= 0.02, T, np.inf)
    T = ndimage.minimum_filter(T, size=max(3, int(tip_radius * 1.5) | 1))
    T = np.clip(np.where(np.isfinite(T), T, 0.0) / total, 0.0, 1.0).astype(np.float32)
    T[alpha < 0.02] = 2.0
    return T, [tt / total for tt in times], total


# ----------------------------------------------------------------------------- colour regions come from the art itself
def enclosed_regions(alpha: np.ndarray, min_frac: float = 0.004) -> List[np.ndarray]:
    """White areas fully enclosed by the line (so a fill can never miss its shape). Biggest first; each grown slightly so it tucks under the line."""
    ink = alpha > 0.35
    closed = ndimage.binary_dilation(ink, iterations=2)         # closes hairline gaps in the outline
    lab, n = ndimage.label(~closed)
    border = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])))
    out = []
    for i in range(1, n + 1):
        if i in border:
            continue
        m = lab == i
        if m.sum() >= min_frac * alpha.size:
            out.append(ndimage.binary_dilation(m, iterations=4))
    out.sort(key=lambda m: -int(m.sum()))
    return out


def trace(alpha: np.ndarray, strategy: str = "human"):
    """-> dict(strokes, width, skel). The whole offline build for one drawing."""
    mask = alpha > 0.5
    sk = skeleton(mask)
    w = line_width(mask, sk)
    segs, _ = segments(sk, w)
    strokes = order_human(segs, alpha.shape) if strategy == "human" else order_scan(segs)
    return {"strokes": strokes, "width": w, "skel": sk, "pieces": len(segs)}
