"""First-person camera director. The night is cut into shots on phrase boundaries; drops get a
cut on the downbeat and a signature move (barrel roll, dolly zoom, bullet-time orbit, crowd surf).
Inside a shot the camera walks, dances, pans on downbeats, punches in on kicks and bobs on steps.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .parts import Ctx
from .world import CAMPFIRE, DJ_POS, LOO_POS, PLAT_TOP, path_x

DJ_HEAD = np.array([0.0, PLAT_TOP + 1.75, -16.35])


def ease(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def h01(*a) -> float:
    v = 0
    for q in a:
        v = (v * 1000003 + int(q) * 2654435761 + 12345) & 0xFFFFFFFF
    v ^= v >> 13
    v = (v * 0x5BD1E995) & 0xFFFFFFFF
    v ^= v >> 15
    return (v & 0xFFFFFF) / 0x1000000


def catmull(pts: np.ndarray, s: float) -> np.ndarray:
    n = len(pts)
    if n == 1:
        return pts[0]
    f = min(max(s, 0.0), 0.9999) * (n - 1)
    i = int(f)
    u = f - i
    p0, p1 = pts[max(i - 1, 0)], pts[i]
    p2, p3 = pts[min(i + 1, n - 1)], pts[min(i + 2, n - 1)]
    return 0.5 * ((2 * p1) + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u + (-p0 + 3 * p1 - 3 * p2 + p3) * u ** 3)


def look(src, dst):
    d = np.asarray(dst, float) - np.asarray(src, float)
    return math.atan2(-d[0], -d[2]), math.atan2(d[1], math.hypot(d[0], d[2]))


@dataclass
class Shot:
    t0: float
    t1: float
    kind: str
    seed: int
    p: dict = field(default_factory=dict)
    moves: list = field(default_factory=list)   # (kind, t0, t1) overlays: roll, dolly, whip


class Director:
    def __init__(self, rng, struct, dur: float, world, crowd_pick, cfg: dict):
        self.rng = rng
        self.st = struct
        self.dur = dur
        self.world = world
        self.pick = crowd_pick
        self.cfg = cfg
        self.shots: list[Shot] = []
        self.forced: list[tuple] = []     # (t0, t1, kind, params) from events (e.g. the UFO)
        self.cut_pace = float(cfg.get("cut_pace", 1.0))

    def force(self, t0, t1, kind, **p):
        self.forced.append((t0, t1, kind, p))

    def plan(self):
        rng = self.rng
        st = self.st
        bounds = sorted(set([0.0] + [float(x) for x in st.phrases if 0 < x < self.dur]
                            + [d.t0 for d in st.drops if 0 < d.t0 < self.dur]
                            + [b.t0 for b in st.builds if 0 < b.t0 < self.dur]
                            + [f[0] for f in self.forced] + [f[1] for f in self.forced if f[1] < self.dur]))
        bounds.append(self.dur)
        t = 0.0
        prev = None
        k = 0
        while t < self.dur - 0.01:
            forced = next((f for f in self.forced if f[0] <= t + 0.01 < f[1]), None)
            if forced:
                t1 = min(forced[1], self.dur)
                self.shots.append(self._make(forced[2], t, t1, k, dict(forced[3])))
                t, prev, k = t1, forced[2], k + 1
                continue
            drop = st.in_segment(st.drops, t + 0.01)
            build = st.in_segment(st.builds, t + 0.01)
            brk = st.in_segment(st.breakdowns, t + 0.01)
            fresh_drop = drop is not None and abs(drop.t0 - t) < 0.05
            if fresh_drop:
                w = {"orbit": 2.0, "surf": 2.5, "stage": 2.5, "dance": 2.0, "drone": 1.2, "djzoom": 1.0}
            elif build is not None:
                w = {"djzoom": 6.0, "dance": 1.0, "stage": 0.6}
            elif brk is not None:
                w = {"tree": 3.0, "sky": 2.0, "fire": 1.6, "corn": 1.8, "drone": 1.5, "dance": 1.0, "walk": 1.0,
                     "surf": 0.4, "loo": 0.3}
            else:
                w = {"dance": 4.0, "walk": 4.0, "stage": 2.0, "djzoom": 1.2, "tree": 1.0, "chicken": 0.5, "loo": 0.35,
                     "corn": 0.7, "drone": 1.0, "fire": 0.4, "surf": 0.8, "bar": 0.4, "car": 1.0}
            if prev in w and len(w) > 1:
                w[prev] *= 0.1
            names = list(w)
            pw = np.array([w[n] for n in names])
            kind = names[int(rng.choice(len(names), p=pw / pw.sum()))]
            # length: one or two phrases, cut early at the next drop/build/forced boundary
            n_ph = 1 if (fresh_drop or rng.random() < 0.55 * self.cut_pace) else 2
            if kind in ("drone", "surf", "corn", "sky", "tree"):
                n_ph = max(n_ph, 1)
            j = int(np.searchsorted(bounds, t + 0.05))
            cand = [b for b in bounds[j:j + 6] if b > t + 4.0]
            t1 = self.dur
            cnt = 0
            for b in cand:
                is_hard = any(abs(b - d.t0) < 0.05 for d in st.drops) or any(abs(b - x.t0) < 0.05 for x in st.builds) \
                    or any(abs(b - f[0]) < 0.05 for f in self.forced)
                cnt += 1
                if is_hard or cnt >= n_ph:
                    t1 = b
                    break
            if kind == "orbit" and t1 - t > 10:
                t1 = t + min(t1 - t, 60 / max(self.st_bpm(), 60) * 8)
            sh = self._make(kind, t, t1, k, {})
            if fresh_drop:
                mv = rng.choice(["roll", "dolly", "whip", "none"], p=[0.3, 0.25, 0.25, 0.2])
                bar = 4 * 60 / max(self.st_bpm(), 60)
                if mv == "roll" and kind in ("dance", "surf", "stage", "drone"):
                    sh.moves.append(("roll", t, t + bar))
                elif mv == "dolly" and kind in ("dance", "djzoom", "stage"):
                    sh.moves.append(("dolly", t, t + bar))
                elif mv == "whip":
                    sh.moves.append(("whip", t, t + 0.35))
            elif prev is not None and rng.random() < 0.18:
                sh.moves.append(("whip", t, t + 0.3))
            self.shots.append(sh)
            t, prev, k = t1, kind, k + 1
        self._t0s = [s.t0 for s in self.shots]

    def st_bpm(self) -> float:
        return float(60 / np.median(np.diff(self.st.beats))) if len(self.st.beats) > 2 else 125.0

    def _make(self, kind, t0, t1, k, p) -> Shot:
        rng = self.rng
        seed = int(rng.integers(1 << 30))
        W = self.world
        if kind == "dance":
            spot = np.array([float(rng.uniform(-8, 8)), float(rng.uniform(-9, 2))])
            p.setdefault("spot", spot)
        elif kind == "walk":
            pts = [np.array([float(rng.uniform(-10, 10)), float(rng.uniform(-10, 6))]) for _ in range(4)]
            p.setdefault("pts", np.array(pts))
        elif kind == "djzoom":
            p.setdefault("pos", np.array([float(rng.uniform(-4, 4)), 2.5, float(rng.uniform(-3, 3))]))
            p.setdefault("fov0", float(rng.uniform(52, 64)))
            p.setdefault("fov1", float(rng.uniform(14, 24)))
        elif kind == "corn":
            z0 = float(rng.uniform(55, 75))
            p.setdefault("z0", z0)
            p.setdefault("z1", 18.0)
        elif kind == "tree":
            tr = W.trees[int(rng.integers(len(W.trees)))]
            a = float(rng.uniform(0, 2 * math.pi))
            p.setdefault("pos", np.array([tr["x"] + math.cos(a) * 1.8, 1.6, tr["z"] + math.sin(a) * 1.8]))
            p.setdefault("yaw0", float(rng.uniform(0, 2 * math.pi)))
        elif kind == "stage":
            side = float(rng.choice([-1, 1]))
            p.setdefault("pos", np.array([side * float(rng.uniform(2.2, 3.2)), 2.5, float(rng.uniform(-16.4, -14.9))]))
            p.setdefault("side", side)
        elif kind == "surf":
            x = float(rng.uniform(-6, 6))
            p.setdefault("pts", np.array([[x, -11.0], [x + float(rng.uniform(-3, 3)), -5.0], [x + float(rng.uniform(-3, 3)), 2.0]]))
        elif kind == "drone":
            made = [c for c in W.crop_sched if c["start"] + c["dur"] <= t0 + W.clip_start] or W.crop_sched[:1]
            cc = made[int(rng.integers(len(made)))] if made else {"cx": 0.0, "cz": 60.0, "R": 10}
            hi = float(rng.uniform(11, 24))
            pts = [[float(rng.uniform(-30, 30)), 3.0, float(rng.uniform(70, 95))],
                   [cc["cx"] + 12, hi, cc["cz"] + 18], [cc["cx"], hi + 6, cc["cz"]],
                   [cc["cx"] * 0.4, hi * 0.6, cc["cz"] * 0.4], [float(rng.uniform(-4, 4)), 3.5, float(rng.uniform(-2, 6))]]
            if rng.random() < 0.5:
                pts = pts[::-1]
            p.setdefault("pts", np.array(pts))
            p.setdefault("target", np.array([cc["cx"], 0.0, cc["cz"]]))
        elif kind == "chicken":
            p.setdefault("ck", int(rng.integers(len(W.chickens))) if W.chickens else 0)
        elif kind == "sky":
            b = W.bales[int(rng.integers(len(W.bales)))]
            p.setdefault("pos", np.array([b[0], 1.05, b[2]]))
            p.setdefault("yaw0", float(rng.uniform(0, 6.28)))
        elif kind == "fire":
            a = float(rng.uniform(0, 2 * math.pi))
            p.setdefault("pos", np.array([CAMPFIRE[0] + math.cos(a) * 2.6, 1.0, CAMPFIRE[2] + math.sin(a) * 2.6]))
        elif kind == "orbit":
            ag = self.pick(t0 + 0.2) if self.pick else None
            if ag is None:
                ag = (-1, 0.0, -5.0)
            p.setdefault("agent", ag[0])
            p.setdefault("center", np.array([ag[1], 0.0, ag[2]]))
            p.setdefault("a0", float(rng.uniform(0, 2 * math.pi)))
            p.setdefault("dirn", float(rng.choice([-1, 1])))
        elif kind == "car":
            p.setdefault("pos", np.array([float(rng.uniform(-4.5, -2.0)), float(rng.uniform(1.0, 1.7)), float(rng.uniform(-9.5, -7.0))]))
        elif kind == "loo":
            p.setdefault("pos", np.array([LOO_POS[0] - 4.5, 1.62, LOO_POS[2] + float(rng.uniform(0, 4))]))
        elif kind == "bar":
            p.setdefault("pos", np.array([-12.5, 1.62, 12.5 + float(rng.uniform(-1, 2))]))
        return Shot(t0, t1, kind, seed, p)

    def shot_at(self, t: float) -> Shot:
        i = max(0, int(np.searchsorted(self._t0s, t, side="right")) - 1)
        return self.shots[i]

    # ---------------------------------------------------------------- evaluation
    def camera(self, c: Ctx, crowd_xz=None):
        sh = self.shot_at(c.t)
        s = (c.t - sh.t0) / max(sh.t1 - sh.t0, 1e-6)
        bar_len = 4 * 60 / max(c.bpm, 60)
        since_bar = c.bar_frac * bar_len
        kick_pump = (c.env["beat"] if c.kick else 0.0)
        fov = 64.0
        roll = 0.0
        pos = np.array([0.0, 1.62, 0.0])
        yaw = pitch = 0.0

        def bar_step(seed, amp):
            a = (h01(seed, c.bar_idx - 1) - 0.5) * 2 * amp
            b = (h01(seed, c.bar_idx) - 0.5) * 2 * amp
            return a + (b - a) * ease(since_bar / 0.45)

        if sh.kind == "dance":
            sp = sh.p["spot"]
            bounce = (1 - c.beat_phase) ** 2 * (0.6 * kick_pump + 0.2)
            pos = np.array([sp[0] + math.sin(c.t * 0.21) * 0.3, 1.62 - 0.07 * bounce, sp[1] + math.cos(c.t * 0.17) * 0.3])
            yaw, pitch = look(pos, DJ_HEAD)
            yaw += bar_step(sh.seed, 0.55)
            pitch += bar_step(sh.seed + 7, 0.12) - 0.04
            roll = math.sin((c.beat_idx % 2 + c.beat_phase) * math.pi) * 0.03 * (0.4 + c.energy)
            fov = 66 - 2.5 * kick_pump
        elif sh.kind == "walk":
            pts = np.column_stack([sh.p["pts"][:, 0], np.full(len(sh.p["pts"]), 1.62), sh.p["pts"][:, 1]])
            pos = catmull(pts, s)
            ahead = catmull(pts, min(1.0, s + 0.04))
            yaw_path, _ = look(pos, ahead) if np.linalg.norm(ahead - pos) > 1e-3 else look(pos, DJ_HEAD)
            yaw_dj, pitch = look(pos, DJ_HEAD)
            mix = 0.5 + 0.5 * math.sin(c.t * 0.3 + sh.seed)
            yaw = yaw_path + _wrap(yaw_dj - yaw_path) * mix * 0.7 + bar_step(sh.seed, 0.3)
            pos[1] += 0.045 * abs(math.sin(math.pi * c.beat_phase))
            pitch = pitch * 0.6 - 0.03
            roll = math.sin(c.beat_idx * math.pi + c.beat_phase * math.pi) * 0.015
            fov = 68 - 2.0 * kick_pump
        elif sh.kind == "djzoom":
            pos = sh.p["pos"] + np.array([0.0, -0.03 * kick_pump, 0.0])
            target = DJ_HEAD + np.array([0.0, -0.45 * ease(s), 0.0])
            yaw, pitch = look(pos, target)
            steps = 6
            q = min(steps, math.floor(s * steps) + ease((s * steps % 1) / 0.2) if s < 1 else steps)
            fov = sh.p["fov0"] + (sh.p["fov1"] - sh.p["fov0"]) * ease(q / steps) - 1.5 * kick_pump
            yaw += math.sin(c.t * 0.7) * 0.01
        elif sh.kind == "corn":
            z = sh.p["z0"] + (sh.p["z1"] - sh.p["z0"]) * s
            x = float(path_x(z))
            pos = np.array([x, 1.6 + 0.04 * abs(math.sin(math.pi * c.beat_phase)), z])
            ahead = np.array([float(path_x(z - 3)), 1.55, z - 3])
            yaw, pitch = look(pos, ahead)
            yaw += math.sin(c.t * 0.5 + sh.seed) * 0.25 + bar_step(sh.seed, 0.2)
            pitch += 0.05 * math.sin(c.t * 0.3)
            fov = 70
        elif sh.kind == "tree":
            pos = sh.p["pos"].copy()
            yaw = sh.p["yaw0"] + c.t * 0.08 * (1 if sh.seed % 2 else -1)
            pitch = 0.75 + 0.15 * math.sin(c.t * 0.2)
            fov = 72
        elif sh.kind == "stage":
            pos = sh.p["pos"] + np.array([0.0, -0.04 * kick_pump, 0.0])
            target = np.array([-sh.p["side"] * 3.0 + math.sin(c.t * 0.13) * 6, 1.0, 2.0])
            yaw, pitch = look(pos, target)
            yaw += bar_step(sh.seed, 0.3)
            fov = 70 - 3 * kick_pump
        elif sh.kind == "surf":
            pts = np.column_stack([sh.p["pts"][:, 0], np.full(len(sh.p["pts"]), 2.35), sh.p["pts"][:, 1]])
            pos = catmull(pts, ease(s * 0.95 + 0.025))
            pos[1] += 0.12 * math.sin(c.t * 2.3) + 0.08 * kick_pump
            yaw = math.pi + math.sin(c.t * 0.35) * 0.8
            pitch = 0.95 + 0.35 * math.sin(c.t * 0.4) - 0.9 * ease((s - 0.75) / 0.25)
            roll = math.sin(c.t * 1.7) * 0.22 + (0.15 if c.beat_idx % 2 else -0.15) * c.env["beat"]
            fov = 74
        elif sh.kind == "drone":
            pts = sh.p["pts"]
            pos = catmull(pts, s)
            ahead = catmull(pts, min(1.0, s + 0.03))
            v = ahead - pos
            yaw, pitch = look(pos, ahead if np.linalg.norm(v) > 1e-3 else sh.p["target"])
            tgt_y, tgt_p = look(pos, sh.p["target"])
            near = math.exp(-((s - 0.5) / 0.22) ** 2)
            yaw = yaw + _wrap(tgt_y - yaw) * near
            pitch = pitch + (tgt_p - pitch) * near * 0.75
            a2 = catmull(pts, min(1.0, s + 0.06)) - ahead
            turn = _wrap(math.atan2(-a2[0], -a2[2]) - math.atan2(-v[0], -v[2])) if np.linalg.norm(a2) > 1e-4 else 0
            roll = max(-0.6, min(0.6, -turn * 3))
            fov = 82
        elif sh.kind == "chicken":
            W = self.world
            ck = W.chickens[sh.p["ck"]] if W.chickens else {"x": 0, "z": 8, "sp": 0.5, "ph": 0}
            x = ck["x"] + math.sin(c.t * 0.05 * ck["sp"] + ck["ph"] * 6) * 6
            z = ck["z"] + math.cos(c.t * 0.04 * ck["sp"] + ck["ph"] * 3) * 2
            pos = np.array([x, 0.4, z + 1.6])
            yaw, pitch = look(pos, np.array([x, 0.5, z - 6]))
            pitch += 0.12 + bar_step(sh.seed, 0.08)
            yaw += bar_step(sh.seed + 3, 0.35)
            fov = 78
        elif sh.kind == "sky":
            pos = sh.p["pos"].copy()
            yaw = sh.p["yaw0"] + c.t * 0.05
            pitch = 1.25
            roll = math.sin(c.t * 0.1) * 0.2
            fov = 80
        elif sh.kind == "fire":
            pos = sh.p["pos"].copy()
            look_fire = look(pos, CAMPFIRE + [0, 0.6, 0])
            look_stage = look(pos, DJ_HEAD)
            m = ease((math.sin(c.t * 0.12 + sh.seed) + 1) / 2)
            yaw = look_fire[0] + _wrap(look_stage[0] - look_fire[0]) * m
            pitch = look_fire[1] * (1 - m) + look_stage[1] * m
            fov = 62
        elif sh.kind == "orbit":
            ctr = sh.p["center"]
            ang = sh.p["a0"] + sh.p["dirn"] * ease(s) * math.pi * 1.2
            r = 3.2 - 0.8 * math.sin(math.pi * s)
            pos = np.array([ctr[0] + math.cos(ang) * r, 1.3 + 0.6 * math.sin(math.pi * s), ctr[2] + math.sin(ang) * r])
            yaw, pitch = look(pos, ctr + np.array([0, 1.4, 0]))
            fov = 55
        elif sh.kind == "car":
            pos = sh.p["pos"] + np.array([0.0, -0.03 * kick_pump, 0.0])
            tgt = np.array([-7.4, 1.0, -13.3]) + np.array([math.sin(c.t * 0.25) * 1.5, 0.3 * math.sin(c.t * 0.4), 0])
            yaw, pitch = look(pos, tgt)
            yaw += bar_step(sh.seed, 0.25)
            fov = 58 - 4 * kick_pump
        elif sh.kind == "loo":
            pos = sh.p["pos"] + np.array([0, 0.02 * math.sin(c.t), 0])
            yaw, pitch = look(pos, LOO_POS + np.array([0, 1.2, 2.2]))
            yaw += bar_step(sh.seed, 0.25)
            fov = 64
        elif sh.kind == "bar":
            pos = sh.p["pos"].copy()
            yaw, pitch = look(pos, np.array([0.0, 2.0, -12.0]))
            yaw += bar_step(sh.seed, 0.4)
            fov = 64
        elif sh.kind == "look":   # featured gag: a framed shot chosen by the event schedule
            p0 = np.array(sh.p["pos"], float)
            tgt = np.array(sh.p["target"], float)
            drift = np.array([math.sin(c.t * 0.3), 0.0, math.cos(c.t * 0.23)]) * 0.25
            pos = p0 + drift + np.array([0.0, -0.03 * kick_pump, 0.0])
            yaw, pitch = look(pos, tgt)
            yaw += bar_step(sh.seed, 0.06)
            fov = float(sh.p.get("fov", 55)) - 2.0 * kick_pump - 6.0 * ease(s)
        elif sh.kind == "ufo":
            pos = np.array(sh.p.get("pos", [0.0, 1.6, 8.0]), float)
            tgt = np.array(sh.p.get("target", [0.0, 20.0, 50.0]), float)
            yaw, pitch = look(pos, tgt)
            fov = 58 - 10 * ease(s)
        # overlays
        for (mv, a, b) in sh.moves:
            if a <= c.t < b:
                x = (c.t - a) / (b - a)
                if mv == "roll":
                    roll += ease(x) * 2 * math.pi
                elif mv == "dolly":
                    k = ease(x)
                    back = np.array([math.sin(yaw), 0.0, math.cos(yaw)])
                    d0 = np.linalg.norm(DJ_HEAD - pos)
                    pos = pos + back * (k * 7.0)
                    d1 = d0 + k * 7.0
                    fov = math.degrees(2 * math.atan(math.tan(math.radians(fov) / 2) * d0 / d1))
                elif mv == "whip":
                    yaw += (1 - ease(x)) * 1.4 * (1 if sh.seed % 2 else -1)
        if c.kick and c.energy > 0.6:
            sh_amt = 0.004 * c.env["beat"] * c.env["sub"]
            yaw += (h01(c.i, 1) - 0.5) * sh_amt
            pitch += (h01(c.i, 2) - 0.5) * sh_amt
        return pos, yaw, pitch, roll, math.radians(max(10.0, min(100.0, fov))), sh


def _wrap(a: float) -> float:
    return (a + math.pi) % (2 * math.pi) - math.pi
