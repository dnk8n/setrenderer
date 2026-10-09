"""The broadcast overlay: which trial, which optimiser and generation, the fitness chart, the tally of failed and
solved attempts, the stamp when an attempt ends, and the cards between trials."""
from __future__ import annotations

import math

import numpy as np

from . import draw as D
from . import font

WHITE = (1.0, 1.0, 1.0, 1.0)
DIM = (1.0, 1.0, 1.0, 0.62)
RED = (1.0, 0.32, 0.30, 1.0)
GREEN = (0.35, 1.0, 0.55, 1.0)
PANEL = (0.04, 0.05, 0.08, 0.55)


def _ease(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def panel(L, x0, y0, x1, y1, a=1.0):
    c = (PANEL[0], PANEL[1], PANEL[2], PANEL[3] * a)
    L.add("sdf", D.boxes([((x0 + x1) / 2, (y0 + y1) / 2)], ((x1 - x0) / 2, (y1 - y0) / 2), c, space=D.SCREEN, corner=12))


def fit(s: str, size: float, width: float, tracking: float = 0.0) -> float:
    """The largest size up to `size` at which s fits in width pixels."""
    w = font.text_width(s, size, tracking)
    return size if w <= width else size * width / w


def header(L, k: int, n: int, trial, alpha: float = 1.0, accent=(1, 1, 1)):
    a = alpha
    D.text(L, f"TRIAL {k + 1:02d} / {n:02d}", 64, 46, 30, (*accent, 0.95 * a), tracking=5)
    D.text(L, trial.name, 64, 80, 64, (1, 1, 1, a))
    D.text(L, trial.goal, 66, 150, fit(trial.goal, 26, 840), (1, 1, 1, 0.75 * a))


def algo_box(L, trial, gen: int, line: str, warn: bool, alpha: float = 1.0, pulse: float = 0.0):
    a = alpha
    x = 1920 - 64
    D.text(L, trial.algo, x, 46, fit(trial.algo, 26, 820, 3), (1, 1, 1, 0.8 * a), align=1.0, tracking=3)
    s = 64 * (1.0 + 0.05 * pulse)
    D.text(L, f"{trial.unit} {gen * trial.unit_scale:,}", x, 78, s, (1, 1, 1, a), align=1.0)
    D.text(L, line, x, 78 + s + 6, fit(line, 24, 820), (1, 0.8, 0.5, 0.9 * a) if warn else (0.75, 1, 0.8, 0.85 * a),
           align=1.0, tracking=1)


def chart(L, hist: dict, upto: int, accent, x0=64, y0=840, w=560, h=180, alpha=1.0, resets=()):
    """Best and mean fitness per generation so far (1.0 = the goal), with resets marked."""
    panel(L, x0 - 18, y0 - 46, x0 + w + 18, y0 + h + 18, alpha)
    D.text(L, "FITNESS", x0, y0 - 38, 22, (1, 1, 1, 0.7 * alpha), tracking=4, shadow=False)
    best = np.asarray(hist["best"], float)[:upto + 1]
    mean = np.asarray(hist["mean"], float)[:upto + 1]
    n = max(len(best), 2)
    top = max(1.25, float(best.max()) * 1.05 if len(best) else 1.25)

    def P(i, v):
        return x0 + w * i / (n - 1), y0 + h - h * min(v, top) / top
    gy = P(0, 1.0)[1]
    xs = np.linspace(x0, x0 + w, 40)
    L.add("sdf", D.segs(np.stack([xs[::2], np.full(20, gy)], 1), np.stack([xs[1::2], np.full(20, gy)], 1), 1.2,
                        (0.35, 1.0, 0.55, 0.7 * alpha), space=D.SCREEN))
    D.text(L, "GOAL", x0 + w - 2, gy - 26, 18, (0.35, 1.0, 0.55, 0.8 * alpha), align=1.0, shadow=False)
    # a new run: green when the world got harder after a success, amber after a dead end
    for r, warm in resets:
        if r <= upto:
            rx = P(r, 0)[0]
            col = (0.35, 1.0, 0.55, 0.6 * alpha) if warm else (1, 0.8, 0.4, 0.6 * alpha)
            L.add("sdf", D.segs([(rx, y0)], [(rx, y0 + h)], 1.2, col, space=D.SCREEN))
    if len(best) >= 2:
        pm = np.array([P(i, v) for i, v in enumerate(mean)])
        pb = np.array([P(i, v) for i, v in enumerate(best)])
        brk = {r for r, _ in resets}
        for pts, col, r in ((pm, (1, 1, 1, 0.35 * alpha), 1.6), (pb, (*accent, alpha), 2.6)):
            seg0, seg1 = [], []
            for i in range(len(pts) - 1):
                if i + 1 in brk:
                    continue
                seg0.append(pts[i])
                seg1.append(pts[i + 1])
            if seg0:
                L.add("sdf", D.segs(seg0, seg1, r, col, space=D.SCREEN))
        L.add("sdf", D.circles([pb[-1]], 6, (*accent, alpha), space=D.SCREEN, glow=6))


def tally(L, rounds_done: list, current: int, n_rounds: int, attempts: int, fails: int, beat: float, alpha=1.0):
    """One pip per round of this trial: a green tick for a success, an amber cross for an ancestor on the way
    to one, a grey cross for an attempt in a run that ended in a dead end."""
    x1 = 1920 - 64
    per = min(30, int(620 / max(n_rounds, 1)))
    x0 = x1 - per * n_rounds
    y = 1000
    panel(L, x0 - 24, y - 92, x1 + 18, y + 34, alpha)
    D.text(L, f"ATTEMPTS {attempts:,}", x0, y - 84, 24, (1, 1, 1, 0.8 * alpha), tracking=2, shadow=False)
    D.text(L, f"SOLVED {attempts - fails:,}", x1, y - 84, 24, (0.55, 1.0, 0.65, 0.85 * alpha), align=1.0, tracking=2,
           shadow=False)
    r = per * 0.34
    w = max2(per)
    for i in range(n_rounds):
        cx = x0 + per * (i + 0.5)
        if i < len(rounds_done):
            k = rounds_done[i]
            if k == "S":
                L.add("sdf", D.segs([(cx - r, y), (cx - r * 0.2, y + r * 0.8)], [(cx - r * 0.2, y + r * 0.8), (cx + r, y - r)],
                                    w, (*GREEN[:3], alpha), space=D.SCREEN))
            else:
                col = (1.0, 0.62, 0.25) if k == "A" else (0.62, 0.55, 0.6)
                L.add("sdf", D.segs([(cx - r, y - r), (cx - r, y + r)], [(cx + r, y + r), (cx + r, y - r)],
                                    w, (*col, alpha), space=D.SCREEN))
        elif i == current:
            a = 0.5 + 0.5 * math.cos(beat * math.tau)
            L.add("sdf", D.rings([(cx, y)], r * 0.8, max(1.5, per * 0.05), (1, 1, 1, (0.4 + 0.6 * a) * alpha), space=D.SCREEN))
        else:
            L.add("sdf", D.circles([(cx, y)], max(2.0, per * 0.09), (1, 1, 1, 0.3 * alpha), space=D.SCREEN))


def max2(per):
    return max(2.0, per * 0.08)


def stamp(L, word: str, sub: str, ok: bool, age: float):
    """The verdict when the featured attempt ends: pops in, holds, then settles small."""
    if age < 0:
        return
    pop = _ease(age / 0.18)
    s = 1.0 + 0.25 * (1 - pop) + 0.04 * math.exp(-age * 6)
    a = pop
    col = GREEN if ok else RED
    size = 96 * s
    cx, cy = 960, 250
    w = font.text_width(word, size, 8) / 2 + 40
    L.add("sdf", D.boxes([(cx, cy + size * 0.52)], (w, size * 0.62), (0.03, 0.03, 0.05, 0.55 * a), space=D.SCREEN, corner=18,
                         outline=4, dark=-2.0))
    D.text(L, word, cx, cy, size, (*col[:3], a), align=0.5, tracking=8)
    if sub:
        D.text(L, sub, cx, cy + size * 1.12, 30, (1, 1, 1, 0.85 * a), align=0.5, tracking=2)


def note(L, s: str, alpha=1.0):
    if s:
        D.text(L, s, 960, 1032, fit(s, 24, 620), (1, 1, 1, 0.7 * alpha), align=0.5)


def title_card(L, k: int, n: int, trial, age: float, dur: float):
    """The trial's card over its reveal: number, name, the optimiser and the rules."""
    a = _ease(age / 0.4) * (1.0 - _ease((age - dur + 0.6) / 0.6))
    if a <= 0:
        return
    rise = 30 * (1 - _ease(age / 0.6))
    panel(L, 380, 300 + rise, 1540, 760 + rise, a)
    D.text(L, f"TRIAL {k + 1:02d} OF {n:02d}", 960, 340 + rise, 34, (*trial.accent, a), align=0.5, tracking=8)
    D.text(L, trial.name, 960, 392 + rise, 104, (1, 1, 1, a), align=0.5)
    D.text(L, trial.goal, 960, 520 + rise, fit(trial.goal, 32, 1080), (1, 1, 1, 0.9 * a), align=0.5)
    D.text(L, trial.algo, 960, 600 + rise, fit(trial.algo, 30, 1080, 4), (1, 1, 1, 0.75 * a), align=0.5, tracking=4)
    D.text(L, trial.physics, 960, 648 + rise, fit(trial.physics, 26, 1080), (1, 1, 1, 0.6 * a), align=0.5)
    D.text(L, f"{trial.dims} · {trial.pop} PER {trial.unit}", 960, 694 + rise, 24, (1, 1, 1, 0.5 * a), align=0.5, tracking=3)
