"""A festival crowd that comes and goes: people arrive through the corn, dance in different spots,
queue at the bar and the loos, sit by the fire, wander off and come back. Every position and pose
is a pure function of time (schedules are precomputed from the seed), so any frame renders alone.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass

import numpy as np

from .cast import POSE_INDEX
from .world import BAR_POS, CAMPFIRE, FLOOR_C, LOO_POS, path_x

WALK, DANCE, IDLE, SIT, HIDDEN, QUEUE = range(6)

STYLES = {
    "bounce": [("bounce_dn", "bounce_up")],
    "jump": [("jump", "bounce_up", "bounce_dn", "bounce_up")],
    "pump": [("pump_up", "pump_dn")],
    "sway": [("sway_l", "sway_r")],
    "robot": [("robot_a", "robot_b")],
    "clap": [("clap", "clap_open")],
    "shuffle": [("kick_l", "kick_r")],
    "headbang": [("headbang", "idle")],
    "vogue": [("vogue_a", "vogue_b")],
    "floss": [("floss_a", "floss_b")],
    "point": [("point", "pump_dn")],
    "sprinkler": [("sprinkler", "arms_out")],
    "mower": [("mower_a", "mower_b")],
    "wave": [("wave", "idle")],
    "hands": [("hands_up", "hands_wide")],
}
STYLE_W = {"bounce": 5, "jump": 2, "pump": 3, "sway": 3, "robot": 1, "clap": 1.5, "shuffle": 1.5, "headbang": 1.5,
           "vogue": 1.2, "floss": 0.8, "point": 1.5, "sprinkler": 0.6, "mower": 0.6, "wave": 1, "hands": 1.5}
HALF_BEAT = {"shuffle", "floss"}

ENTRANCES = [np.array([path_x(24.0), 24.0]), np.array([-24.5, 2.0]), np.array([24.0, 14.0]), np.array([22.0, -2.0])]


@dataclass
class Seg:
    t0: float
    t1: float
    kind: int
    p0: np.ndarray
    p1: np.ndarray
    style: str = "bounce"
    alt: str = "sway"
    hold: str = ""        # idle variant: drink / phone / torch


def dance_spot(rng) -> np.ndarray:
    # denser towards the stage, never on it
    while True:
        r = math.sqrt(float(rng.random()))
        a = float(rng.uniform(0, 2 * math.pi))
        x = FLOOR_C[0] + math.cos(a) * r * 11.5
        z = FLOOR_C[2] + math.sin(a) * r * 8.5
        z -= 2.0 * (1 - r)
        if z > -12.3 and abs(x) < 16:
            return np.array([x, z])


class Crowd:
    def __init__(self, rng: np.random.Generator, n: int, n_chars: int, clip_start: float, dur: float, total: float,
                 struct, styles: dict | None = None):
        self.n = n
        self.rng = rng
        self.dur = dur
        weights = dict(STYLE_W)
        weights.update(styles or {})
        names = list(weights)
        p = np.array([weights[k] for k in names], float)
        p /= p.sum()
        chars = rng.permutation(np.resize(np.arange(n_chars), n))
        self.char = chars.astype(int)
        self.segs: list[list[Seg]] = []
        self.t0s: list[list[float]] = []
        self.flag_until = np.full(n, -1.0)
        self.flag_name = [None] * n
        T0 = clip_start
        for k in range(n):
            segs = self._schedule(rng, T0, dur, total, names, p)
            self.segs.append(segs)
            self.t0s.append([s.t0 for s in segs])
        self.flag_windows = self._flag_windows(rng, dur)

    # ---------------------------------------------------------------- schedules
    def _schedule(self, rng, T0, dur, total, names, p) -> list[Seg]:
        """Simulate one person over [T0-900, T0+dur+60] in absolute time; store clip-local times."""
        start, end = T0 - 900.0, T0 + dur + 60.0
        segs: list[Seg] = []

        def presence(T):
            q = np.clip(T / max(total, 1), 0, 1)
            fill = min(1.0, q / 0.1) if total > 1200 else 1.0
            dawn = 1 - 0.45 * max(0.0, (q - 0.86) / 0.14) if total > 1200 else 1.0
            return 0.35 + 0.6 * fill * dawn

        t = start
        here = rng.random() < presence(start)
        pos = dance_spot(rng) if here else ENTRANCES[int(rng.integers(len(ENTRANCES)))].copy()
        style = names[int(rng.choice(len(names), p=p))]
        alt = names[int(rng.choice(len(names), p=p))]
        speed = float(rng.uniform(1.1, 1.6))
        if not here:
            away = float(rng.uniform(0, 1200))
            segs.append(Seg(t - T0, t + away - T0, HIDDEN, pos, pos))
            t += away
        while t < end:
            if rng.random() > presence(t) * 1.1:
                act = "away"
            else:
                act = rng.choice(["dance", "dance", "dance", "dance", "dance", "bar", "loo", "fire", "wander"],
                                 p=[0.15, 0.15, 0.15, 0.15, 0.12, 0.09, 0.05, 0.08, 0.06])
            if act == "dance":
                dest = dance_spot(rng)
                stay = float(rng.gamma(2.0, 70.0)) + 20
            elif act == "bar":
                dest = BAR_POS[[0, 2]] + np.array([float(rng.uniform(-2.2, 2.2)), float(rng.uniform(1.0, 2.8))])
                stay = float(rng.uniform(30, 110))
            elif act == "loo":
                dest = LOO_POS[[0, 2]] + np.array([-1.6 - float(rng.uniform(0, 3.0)), float(rng.uniform(0, 4.5))])
                stay = float(rng.uniform(20, 60))
            elif act == "fire":
                a = float(rng.uniform(0, 2 * math.pi))
                dest = CAMPFIRE[[0, 2]] + np.array([math.cos(a), math.sin(a)]) * 2.0
                stay = float(rng.uniform(60, 280))
            elif act == "wander":
                dest = np.array([float(rng.uniform(-16, 16)), float(rng.uniform(-8, 18))])
                stay = float(rng.uniform(10, 40))
            else:
                dest = ENTRANCES[int(rng.integers(len(ENTRANCES)))].copy()
                stay = float(rng.uniform(120, 900))
            d = float(np.linalg.norm(dest - pos))
            if d > 0.3:
                wt = d / speed
                segs.append(Seg(t - T0, t + wt - T0, WALK, pos.copy(), dest.copy()))
                t += wt
            kind = {"dance": DANCE, "bar": IDLE, "loo": QUEUE, "fire": SIT, "wander": IDLE, "away": HIDDEN}[act]
            hold = ""
            if act in ("bar",):
                hold = "drink"
            elif act == "wander":
                hold = rng.choice(["phone", "idle", "drink"])
            if act == "dance" and rng.random() < 0.4:
                style = names[int(rng.choice(len(names), p=p))]
            segs.append(Seg(t - T0, t + stay - T0, kind, dest.copy(), dest.copy(), style, alt, hold))
            t += stay
            pos = dest
            if act == "loo":   # inside the loo for a bit
                inside = float(rng.uniform(15, 45))
                segs.append(Seg(t - T0, t + inside - T0, HIDDEN, pos.copy(), pos.copy()))
                t += inside
        return segs

    def _flag_windows(self, rng, dur):
        """People bring out flags now and then and put them away again."""
        win = []
        t = float(rng.uniform(0, 40))
        while t < dur:
            k = int(rng.integers(self.n))
            length = float(rng.uniform(30, 120))
            win.append((t, t + length, k))
            t += float(rng.uniform(8, 35))
        return win

    # ---------------------------------------------------------------- evaluation
    def state(self, t: float, beat_idx: int, beat_phase: float, bar_idx: int, energy: float):
        n = self.n
        x = np.zeros(n)
        z = np.zeros(n)
        y = np.zeros(n)
        pose = np.zeros(n, int)
        vis = np.ones(n, bool)
        walking = np.zeros(n, bool)
        face = np.zeros((n, 2))
        kind = np.zeros(n, int)
        hb = beat_idx * 2 + (1 if beat_phase >= 0.5 else 0)
        stage = np.array([0.0, -16.0])
        for k in range(n):
            segs = self.segs[k]
            i = bisect.bisect_right(self.t0s[k], t) - 1
            if i < 0:
                vis[k] = False
                continue
            s = segs[i]
            kind[k] = s.kind
            if s.kind == HIDDEN or t >= s.t1:
                vis[k] = s.kind != HIDDEN and t < s.t1
                if s.kind == HIDDEN:
                    continue
            if s.kind == WALK:
                f = (t - s.t0) / max(s.t1 - s.t0, 1e-6)
                p = s.p0 + (s.p1 - s.p0) * f
                walking[k] = True
                d = s.p1 - s.p0
                face[k] = d / (np.linalg.norm(d) + 1e-9)
                pose[k] = POSE_INDEX[f"walk_{1 + (hb + k) % 4}"]
                y[k] = 0.03 * abs(math.sin(math.pi * beat_phase))
            else:
                p = s.p0
                tow = stage - p if s.kind in (DANCE, IDLE) else (CAMPFIRE[[0, 2]] - p if s.kind == SIT else np.array([1.0, 0.0]))
                face[k] = tow / (np.linalg.norm(tow) + 1e-9)
                if s.kind == DANCE:
                    st = s.style if (bar_idx // 8 + k) % 3 else s.alt
                    seq = STYLES[st][0]
                    step = (hb if st in HALF_BEAT else beat_idx) + k * 0
                    name = seq[step % len(seq)]
                    if st not in HALF_BEAT and len(seq) == 2 and beat_phase > 0.55 and st in ("bounce",):
                        name = seq[1]
                    pose[k] = POSE_INDEX[name]
                    if st == "jump" and step % 4 == 0:
                        y[k] = 0.45 * math.sin(math.pi * min(1.0, beat_phase * 1.6)) * (0.5 + energy)
                    # small sway in place so nobody is pinned to the floor
                    p = p + np.array([math.sin(t * 0.37 + k) * 0.25, math.cos(t * 0.29 + k * 1.7) * 0.2])
                elif s.kind == SIT:
                    pose[k] = POSE_INDEX["sit"]
                elif s.kind == QUEUE:
                    pose[k] = POSE_INDEX["idle" if (beat_idx + k) % 8 else "phone"]
                else:
                    h = s.hold or "idle"
                    pose[k] = POSE_INDEX[{"drink": "drink", "phone": "phone", "idle": "idle"}.get(h, "idle")]
                    if h == "idle" and (beat_idx // 2 + k) % 3 == 0:
                        pose[k] = POSE_INDEX["bounce_dn" if beat_phase < 0.4 else "bounce_up"]
            x[k], z[k] = p
        flags = [None] * n
        for (a, b, k) in self.flag_windows:
            if a <= t < b and vis[k] and kind[k] in (DANCE, IDLE):
                flags[k] = True
                pose[k] = POSE_INDEX["flag"]
        return {"x": x, "z": z, "y": y, "pose": pose, "vis": vis, "walking": walking, "face": face, "kind": kind,
                "flag": flags, "roll": np.zeros(n), "flash": np.zeros(n), "emote": [None] * n}
