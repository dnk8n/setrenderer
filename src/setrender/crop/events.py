"""Happenings: drops and breakdowns, sound-triggered gags (more cowbell, the theremin UFO, the sax
solo...), crowd routines (conga, YMCA, row-the-boat, dance circle), internet-culture cameos and
easter eggs for people who read the bar counter. Scheduled once from the seed and the analysis.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from .cast import POSE_INDEX
from .crowd import DANCE, IDLE
from .director import ease, h01
from .parts import A, Ctx, Parts, apply, hue
from .world import CAR_POS, DJ_POS, FLOOR_C, PLAT_TOP, TRUSS_Y, path_x

SOUND_MAP = {  # classifier label -> (event, cooldown s, minimum confidence)
    "cowbell": ("cowbell", 90, 0.45), "theremin": ("ufo", 300, 0.5), "cat_meow": ("cat", 60, 0.5),
    "cat": ("cat", 60, 0.55), "chicken": ("chickens", 120, 0.45), "chicken_cluck": ("chickens", 120, 0.45),
    "rooster_crow": ("rooster", 120, 0.45), "fowl": ("chickens", 120, 0.5), "sheep_bleat": ("sheep", 120, 0.45),
    "laughter": ("laugh", 45, 0.45), "giggling": ("laugh", 45, 0.5), "belly_laugh": ("laugh", 45, 0.45),
    "ringtone": ("phones", 90, 0.5), "telephone": ("phones", 90, 0.5), "telephone_bell_ringing": ("phones", 90, 0.5),
    "saxophone": ("sax", 90, 0.5), "person_shuffling": ("shuffle", 60, 0.5), "gong": ("gong", 30, 0.45),
    "electric_guitar": ("airguitar", 60, 0.6), "guitar": ("airguitar", 90, 0.7), "brass_instrument": ("confetti", 45, 0.65),
    "trumpet": ("confetti", 45, 0.6), "trombone": ("confetti", 45, 0.6), "organ": ("godrays", 90, 0.55),
    "choir_singing": ("godrays", 90, 0.5), "didgeridoo": ("psychedelic", 120, 0.5), "flute": ("birds", 90, 0.55),
    "bird": ("birds", 90, 0.5), "piano": ("pianohands", 60, 0.72), "cheering": ("cheer", 45, 0.4),
    "applause": ("cheer", 45, 0.4), "clapping": ("cheer", 45, 0.45), "dog_bark": ("dog", 120, 0.45),
    "dog": ("dog", 120, 0.5), "whistling": ("cheer", 60, 0.45), "steelpan": ("pride_jelly", 60, 0.5),
    "marimba_xylophone": ("qblocks", 90, 0.6),
}
DURATION = {"cowbell": 9, "ufo": 26, "cat": 4, "chickens": 12, "rooster": 5, "sheep": 10, "laugh": 1.2, "phones": 6,
            "sax": 12, "shuffle": 16, "gong": 3, "airguitar": 10, "confetti": 4, "godrays": 14, "psychedelic": 20,
            "birds": 14, "pianohands": 8, "cheer": 5, "dog": 10, "pride_jelly": 30, "qblocks": 20}


@dataclass
class Event:
    kind: str
    t0: float
    t1: float
    p: dict = field(default_factory=dict)
    eid: int = 0


class Events:
    def __init__(self, scene, rng):
        self.sc = scene
        self.rng = rng
        self.ev: list[Event] = []
        self._schedule()
        self._index()

    # ---------------------------------------------------------------- scheduling
    def add(self, kind, t0, t1, **p):
        if t1 <= 0 or t0 >= self.sc.dur:
            return None
        e = Event(kind, t0, t1, p, len(self.ev))
        self.ev.append(e)
        return e

    def _schedule(self):
        sc, st, rng = self.sc, self.sc.struct, self.rng
        dur = sc.dur
        bar = 4 * 60 / max(sc.bpm0, 60)
        for d in st.drops:
            self.add("drop", d.t0, d.t0 + 2 * bar, strength=d.strength)
        for b in st.builds:
            self.add("build", b.t0, b.t1)
        last_row = last_torch = last_nyan = -1e9
        for b in st.breakdowns:
            self.add("breakdown", b.t0, b.t1, strength=b.strength)
            long_ = b.t1 - b.t0
            if long_ > 16 * bar * 0.95 and rng.random() < 0.45 and b.t0 - last_row > 420:
                self.add("rowboat", b.t0 + 2 * bar, min(b.t1, b.t0 + 10 * bar))
                last_row = b.t0
            elif long_ > 8 * bar and rng.random() < 0.6 and b.t0 - last_torch > 240:
                self.add("torches", b.t0 + bar, b.t1)
                last_torch = b.t0
            if long_ > 8 * bar and (rng.random() < 0.45 or long_ > 32 * bar):
                self.add("psychedelic", b.t0, b.t1)
            if long_ > 8 * bar and rng.random() < 0.25 and b.t0 - last_nyan > 600:
                self.add("nyan", b.t0 + bar, b.t0 + bar + 9)
                last_nyan = b.t0
        # sound-triggered gags
        last = {}
        for s in st.sounds:
            m = SOUND_MAP.get(s.label)
            if not m:
                continue
            kind, cool, conf = m
            if s.peak < conf or s.t0 < -1:
                continue
            if s.t0 - last.get(kind, -1e9) < cool:
                continue
            last[kind] = s.t0
            t0 = max(0.0, s.t0 + 1.0)
            self.add(kind, t0, t0 + DURATION.get(kind, 8), label=s.label, conf=s.peak)
        # UFO visits draw the crop circles (cause and effect)
        for c in sc.world.crop_sched:
            t0 = c["start"] - sc.clip_start
            if -c["dur"] < t0 < dur:
                self.add("ufo", t0 - 6, t0 + c["dur"] + 6, target=(c["cx"], c["cz"]), crop=True)
        # routines and cameos at phrase starts
        rates = {"conga": 2.5, "cypher": 3, "ymca": 1.2, "floss": 1, "robotmob": 1, "wave": 3, "pacman": 3,
                 "hotdog": 2, "baby": 2, "balloon": 1.5, "kites": 1.5, "smiley": 2.5, "farmer": 2.5, "dog": 2,
                 "filter": 5, "qblocks": 3, "pride_jelly": 5, "creeper": 2, "birds": 2, "goat": 3, "mushrooms": 3,
                 "singalong": 2}
        rates.update(sc.cfg.get("events", {}).get("rates", {}) or {})
        boost = max(1.0, 600.0 / max(dur, 1.0)) if dur < 600 else 1.0
        phr = [float(x) for x in st.phrases if 0 <= x < dur]
        busy_until = {}
        for t in phr:
            e = float(np.interp(t, st.downbeats, st.bar_energy)) if len(st.downbeats) else 0.5
            brk = st.in_segment(st.breakdowns, t + 0.1) is not None
            for kind, rate in rates.items():
                if busy_until.get(kind, -1) > t:
                    continue
                p = rate / 3600 * 8 * bar * boost
                ok = {"conga": e > 0.55 and not brk, "cypher": not brk, "ymca": e > 0.6 and not brk,
                      "floss": not brk, "robotmob": not brk, "wave": e > 0.5, "balloon": True, "kites": True,
                      "goat": not brk, "mushrooms": brk, "singalong": True}.get(kind, True)
                if not ok or rng.random() > p:
                    continue
                L = {"conga": 8, "cypher": 8, "ymca": 4, "floss": 4, "robotmob": 4, "wave": 4, "pacman": 6,
                     "hotdog": 8, "baby": 8, "balloon": 48, "kites": 32, "smiley": 16, "farmer": 12, "dog": 4,
                     "filter": 4, "qblocks": 8, "pride_jelly": 16, "creeper": 12, "birds": 6, "goat": 2,
                     "mushrooms": 12, "singalong": 8}[kind] * bar
                p2 = {}
                if kind == "filter":
                    p2["mode"] = int(rng.choice([1, 2, 3, 4, 5], p=[0.4, 0.15, 0.08, 0.3, 0.07]))
                if kind == "cypher":
                    p2["center"] = (float(rng.uniform(-5, 5)), float(rng.uniform(-8, 0)))
                if kind in ("pacman",):
                    p2["dir"] = float(rng.choice([-1, 1]))
                self.add(kind, t, t + L, **p2)
                busy_until[kind] = t + L + 60
        # numbers for people who read the HUD
        db = st.downbeats
        for bar_no, kind in ((1337, "konami"), (404, "bar404"), (420, "smokering"), (999, "rollover")):
            if bar_no < len(db) and 0 <= db[bar_no] < dur:
                self.add(kind, float(db[bar_no]), float(db[min(len(db) - 1, bar_no + 1)]) if kind != "konami" else float(db[bar_no]) + 2 * bar)
        # fireworks at the biggest drop and in the last half minute
        if st.drops:
            big = max(st.drops, key=lambda d: d.strength * (1 + 0.2 * h01(d.t0)))
            self.add("fireworks", big.t0, big.t0 + 20)
        if dur > 120:
            self.add("fireworks", dur - 30, dur)
        # shooting stars on strong onsets at night
        on = sc.tl.env["onset"]
        cand = np.nonzero(on > 0.92)[0]
        last_t = -1e9
        for i in cand[:: max(1, len(cand) // 400)]:
            t = i / sc.fps
            if t - last_t > 25 and rng.random() < 0.5:
                self.add("shootingstar", t, t + 1.2, a=float(rng.uniform(0, 6.28)), h=float(rng.uniform(0.25, 0.6)))
                last_t = t
        # the alien stays after the first UFO
        first_ufo = min([e.t0 for e in self.ev if e.kind == "ufo"] or [1e9])
        self.alien_from = first_ufo + 20

    def features(self) -> list[tuple]:
        """Framed shots for the gags, so viewers actually see them: (t0, t1, pos, target, fov)."""
        rng = self.rng
        bar = 4 * 60 / max(self.sc.bpm0, 60)
        out = []
        last = -1e9
        for e in self.ev:
            k = e.kind
            spec = None
            if k == "conga":
                spec = ((0.0, 2.8, 6.5), (0.0, 0.8, -4.0), 58)
            elif k == "cypher":
                cx, cz = e.p["center"]
                spec = ((cx + 3.5, 1.9, cz + 3.5), (cx, 0.8, cz), 52)
            elif k == "rowboat":
                spec = ((0.3, 1.1, -9.8), (0.0, 0.5, -5.0), 62)
            elif k == "cowbell":
                spec = ((-8.0, 1.5, -5.5), (-12.0, 1.0, -9.5), 46)
            elif k in ("sax", "baby"):
                x = 2.4 if k == "sax" else -2.2
                spec = ((x * 0.5, 2.3, -9.5), (x, PLAT_TOP + 1.1, -15.2), 38)
            elif k == "pacman":
                spec = ((0.0, 1.3, 3.5), (0.0, 0.4, -3.0), 64)
            elif k == "hotdog":
                spec = ((5.0, 1.5, 1.5), (5.5, 1.0, -2.5), 50)
            elif k == "chickens":
                spec = ((-3.0, 0.5, 3.5), (-6.0, 0.4, -2.0), 70)
            elif k == "nyan":
                spec = ((-5.0, 1.6, 2.0), (-20.0, 26.0, -45.0), 60)
            elif k in ("ymca", "robotmob", "floss"):
                spec = ((5.5, 2.6, -14.8), (-1.0, 0.9, -3.0), 66)
            elif k == "goat":
                spec = ((20.5, 1.7, -6.0), (24.4, 1.4, -10.0), 50)
            elif k == "sheep":
                spec = ((32.0, 1.8, 4.0), (41.0, 0.8, -4.0), 52)
            elif k == "fireworks":
                spec = ((0.0, 1.4, 8.0), (0.0, 40.0, -55.0), 70)
            elif k == "smiley":
                spec = ((0.0, 1.7, -4.0), (0.0, TRUSS_Y + 3.0, -17.5), 60)
            elif k == "creeper":
                spec = ((6.0, 1.6, 3.5), (5.0, 1.0, -1.0), 55)
            elif k == "balloon":
                spec = ((0.0, 1.6, 10.0), (0.0, 45.0, -80.0), 60)
            if spec is None or e.t0 - last < 25 or rng.random() > 0.8:
                continue
            t0 = e.t0 + (bar if e.t1 - e.t0 > 3 * bar else 0.0)
            t1 = min(e.t1, t0 + min(2.5 * bar, 8.0))
            if k == "fireworks":
                t0, t1 = e.t0 + 2.0, e.t0 + 9.0
            if k == "balloon":
                t0, t1 = e.t0 + (e.t1 - e.t0) * 0.45, e.t0 + (e.t1 - e.t0) * 0.45 + 7.0
            out.append((t0, t1, spec[0], spec[1], spec[2]))
            last = t0
        return out

    def _index(self):
        self.ev.sort(key=lambda e: e.t0)
        for k, e in enumerate(self.ev):
            e.eid = k
        nb = int(self.sc.dur) + 2
        self.buckets = [[] for _ in range(nb)]
        for e in self.ev:
            for s in range(max(0, int(e.t0)), min(nb, int(e.t1) + 1)):
                self.buckets[s].append(e)

    def active(self, t: float) -> list[Event]:
        s = int(min(max(t, 0), len(self.buckets) - 1))
        return [e for e in self.buckets[s] if e.t0 <= t < e.t1]

    # ---------------------------------------------------------------- crowd routines
    def crowd(self, c: Ctx, S: dict):
        n = len(S["x"])
        dancing = S["vis"] & ((S["kind"] == DANCE) | (S["kind"] == IDLE)) & ~S["walking"]
        idx = np.nonzero(dancing)[0]
        for e in c.events:
            k = e.kind
            age = c.t - e.t0
            order = sorted(idx, key=lambda q: h01(e.eid, q))
            if k == "drop" and age < 2 * 4 * 60 / max(c.bpm, 60):
                for q in idx:
                    if (c.beat_idx + q) % 2 == 0:
                        S["pose"][q] = POSE_INDEX["jump"]
                        S["y"][q] = 0.5 * math.sin(math.pi * min(1, c.beat_phase * 1.5))
                    else:
                        S["pose"][q] = POSE_INDEX["hands_up"]
                    if h01(e.eid, q) < 0.25 and age < 1.0:
                        S["emote"][q] = "bang"
            elif k == "build":
                frac = ease((c.t - e.t0) / max(e.t1 - e.t0, 1))
                for q in idx:
                    if h01(e.eid, q) < frac * 0.8:
                        S["pose"][q] = POSE_INDEX["hands_up" if c.beat_phase < 0.5 else "hands_wide"]
            elif k == "laugh":
                for q in np.nonzero(S["vis"])[0]:
                    S["pose"][q] = POSE_INDEX["laugh"]
            elif k == "phones":
                for q in order[: max(1, len(order) // 3)]:
                    S["pose"][q] = POSE_INDEX["phone"]
            elif k == "torches":
                for q in order[: int(len(order) * 0.45)]:
                    S["pose"][q] = POSE_INDEX["torch"]
                    S["emote"][q] = "torch"
            elif k in ("airguitar", "pianohands", "cheer", "shuffle"):
                frac = {"airguitar": 0.25, "pianohands": 0.4, "cheer": 0.5, "shuffle": 0.45}[k]
                for q in order[: int(len(order) * frac)]:
                    if k == "airguitar":
                        S["pose"][q] = POSE_INDEX["airguitar"]
                    elif k == "pianohands":
                        S["pose"][q] = POSE_INDEX["hands_up"]
                    elif k == "cheer":
                        S["pose"][q] = POSE_INDEX["cheer" if (c.beat_idx + q) % 2 else "clap"]
                    else:
                        hb = c.beat_idx * 2 + (c.beat_phase >= 0.5)
                        S["pose"][q] = POSE_INDEX["kick_l" if hb % 2 else "kick_r"]
            elif k in ("ymca", "floss", "robotmob"):
                ch = {"ymca": ["hands_wide", "ymca_m", "ymca_c", "ymca_a"], "floss": ["floss_a", "floss_b"],
                      "robotmob": ["robot_a", "robot_b", "robot_a", "arms_out"]}[k]
                step = c.beat_idx if k != "floss" else c.beat_idx * 2 + (c.beat_phase >= 0.5)
                for q in idx:
                    S["pose"][q] = POSE_INDEX[ch[step % len(ch)]]
            elif k == "wave":
                period = 4 * 60 / max(c.bpm, 60) * 2
                wx = -16 + 32 * ((c.t - e.t0) % period) / period
                for q in idx:
                    if abs(S["x"][q] - wx) < 1.6:
                        S["pose"][q] = POSE_INDEX["hands_up"]
                        S["y"][q] = 0.15
            elif k == "conga":
                part = order[:10]
                L = len(part)
                fade = min(1.0, age / 2.0, (e.t1 - c.t) / 2.0)
                for j, q in enumerate(part):
                    s = (age * 1.2 - j * 0.85) / 30.0 * 2 * math.pi
                    px, pz = FLOOR_C[0] + math.cos(s) * 7.5, FLOOR_C[2] + math.sin(s) * 5.0
                    S["x"][q] += (px - S["x"][q]) * fade
                    S["z"][q] += (pz - S["z"][q]) * fade
                    hb = c.beat_idx * 2 + (c.beat_phase >= 0.5)
                    S["pose"][q] = POSE_INDEX[f"walk_{1 + (hb + j) % 4}"] if j else POSE_INDEX["wave"]
                    S["walking"][q] = fade > 0.5
                    S["face"][q] = (-math.sin(s), math.cos(s))
                    if c.beat_idx % 4 == 3 and c.beat_phase < 0.4:   # the conga kick
                        S["pose"][q] = POSE_INDEX["kick_l" if j % 2 else "kick_r"]
                        S["walking"][q] = False
                _ = L
            elif k == "rowboat":
                part = order[:10]
                fade = min(1.0, age / 2.0, (e.t1 - c.t) / 2.0)
                for j, q in enumerate(part):
                    px, pz = -4.5 + j * 0.95, -5.0
                    S["x"][q] += (px - S["x"][q]) * fade
                    S["z"][q] += (pz - S["z"][q]) * fade
                    S["pose"][q] = POSE_INDEX["row_a" if (c.beat_idx // 2 + (c.beat_phase > 0.5)) % 2 else "row_b"]
                    S["face"][q] = (0.0, -1.0)
                    S["walking"][q] = False
            elif k == "cypher":
                part = order[:10]
                cx, cz = e.p["center"]
                fade = min(1.0, age / 2.0, (e.t1 - c.t) / 2.0)
                for j, q in enumerate(part):
                    if j == 0:
                        px, pz = cx, cz
                        spin = (c.t - e.t0) * 7.0
                        mode = (c.bar_idx // 2) % 3
                        S["pose"][q] = POSE_INDEX[["jump", "kick_l", "hands_wide"][mode]]
                        S["roll"][q] = spin * fade if mode != 2 else math.pi * fade
                        S["y"][q] = 0.1 if mode == 2 else 0.4
                    else:
                        a = (j - 1) / 9 * 2 * math.pi
                        px, pz = cx + math.cos(a) * 2.4, cz + math.sin(a) * 2.4
                        S["pose"][q] = POSE_INDEX["clap" if (c.beat_idx + j) % 2 else "cheer"]
                        S["face"][q] = (cx - px, cz - pz)
                    S["x"][q] += (px - S["x"][q]) * fade
                    S["z"][q] += (pz - S["z"][q]) * fade
                    S["walking"][q] = False
            elif k == "ufo":
                for q in order[: max(1, len(order) // 5)]:
                    if (c.beat_idx // 2 + q) % 2:
                        S["pose"][q] = POSE_INDEX["scared" if age < 8 else "phone"]
                        S["emote"][q] = "sweat" if age < 8 else None
            elif k == "bar404":
                if len(idx):
                    S["vis"][idx[int(h01(e.eid) * len(idx))]] = False
            elif k == "konami":
                seq = ["jump", "jump", "bounce_dn", "bounce_dn", "kick_l", "kick_r", "kick_l", "kick_r"]
                b = int((c.t - e.t0) / (60 / max(c.bpm, 60)))
                for q in idx:
                    S["pose"][q] = POSE_INDEX[seq[min(b, 7)]]
        return S

    # ---------------------------------------------------------------- props and particles
    def frame(self, c: Ctx, P: Parts, at: dict):
        sc = self.sc
        for e in c.events:
            k = e.kind
            age = c.t - e.t0
            f = getattr(self, "_f_" + k, None)
            if f:
                f(e, age, c, P, at)

    def _f_drop(self, e, age, c, P, at):
        if age < 1.4:   # shockwave across the dancefloor
            r = 1 + age * 16
            P.ring((FLOOR_C[0], 0.05, FLOOR_C[2]), r, tuple(v * 1.5 * (1 - age / 1.4) for v in c.accents[0]), width=0.06)
        self._confetti(e, age, c, P, n=260 if e.p.get("strength", 1) > 0.5 else 140)

    def _confetti(self, e, age, c, P, n=200, origin=None):
        if age > 6:
            return
        rng = np.random.default_rng(e.eid * 7919 + 13)
        k = np.arange(n)
        side = np.where(k % 2 == 0, -1.0, 1.0)
        o = np.array(origin if origin is not None else (0, TRUSS_Y, -15.0))
        v0 = np.stack([side * rng.uniform(1, 6, n), rng.uniform(5, 11, n), rng.uniform(4, 10, n)], 1)
        drag = 0.9
        tt = age
        dec = (1 - np.exp(-drag * tt)) / drag
        pos = o + v0 * dec[None] if np.ndim(dec) else o + v0 * dec
        pos[:, 1] -= 2.5 * tt * tt * 0.5 * 0.6 + 0.9 * tt
        pos[:, 0] += np.sin(tt * 5 + k) * 0.2 * tt
        alive = pos[:, 1] > 0.02
        cols = np.array([hue(h, 0.85, 1.0) for h in rng.random(n)])
        rows = np.zeros((n, 20), np.float32)
        rows[:, 0:3] = pos
        rows[:, 3] = 0.05
        rows[:, 7] = tt * 6 + k
        rows[:, 8:11] = cols * 0.9 * min(1.0, (6 - age) / 2)
        rows[:, 11] = 1
        rows[:, 12] = 3
        rows[:, 13] = 4
        P.glows_many(rows[alive])

    def _f_confetti(self, e, age, c, P, at):
        self._confetti(e, age, c, P, n=180)

    def _f_gong(self, e, age, c, P, at):
        if age < 2.5:
            for d in (0.0, 0.25, 0.5):
                a = age - d
                if a > 0:
                    P.ring((FLOOR_C[0], 0.06, FLOOR_C[2]), 1 + a * 12, (1.2 * (1 - a / 2.5), 0.9 * (1 - a / 2.5), 0.3), width=0.05)

    def _f_breakdown(self, e, age, c, P, at):
        # fireflies drift out of the trees
        n = 120
        k = np.arange(n)
        W = self.sc.world
        tx = np.array([W.trees[q % len(W.trees)]["x"] for q in k])
        tz = np.array([W.trees[q % len(W.trees)]["z"] for q in k])
        ph = k * 1.37
        x = tx + np.sin(c.t * 0.3 + ph) * 3 + np.sin(c.t * 0.71 + ph * 2) * 1.2
        z = tz + np.cos(c.t * 0.27 + ph) * 3
        y = 1.0 + 2.5 * (0.5 + 0.5 * np.sin(c.t * 0.4 + ph * 3))
        blink = (0.5 + 0.5 * np.sin(c.t * 3 + ph * 5)) ** 4
        fade = min(1.0, age / 4.0, (e.t1 - c.t) / 2.0)
        rows = np.zeros((n, 20), np.float32)
        rows[:, 0], rows[:, 1], rows[:, 2] = x, y, z
        rows[:, 3] = 0.06
        rows[:, 8] = 0.9 * blink * fade
        rows[:, 9] = 1.4 * blink * fade
        rows[:, 10] = 0.3 * blink * fade
        rows[:, 11] = 1
        rows[:, 13] = 2.5
        P.glows_many(rows)

    def _f_torches(self, e, age, c, P, at):
        pass   # handled with the crowd sprites (emote "torch")

    def _f_cowbell(self, e, age, c, P, at):
        x, z = -12.0, -9.5
        fr = "dance" if 0.6 < age < e.t1 - e.t0 - 0.6 else "stand"
        hop = 0.25 * abs(math.sin(math.pi * c.beat_phase)) if fr == "dance" else 0
        P.sprite((x, hop, z), 2.4, 1.6, at[f"cow_{fr}"], flash=0.15 * c.env["beat"])
        P.shadow(x, z, 1.6, 0.7)
        if fr == "dance" and c.beat_phase < 0.25:
            P.dot((x + 0.05, 1.05 + hop, z), 0.12, (0.9, 0.7, 0.2), soft=3)

    def _f_cat(self, e, age, c, P, at):
        T = self.sc.world.car_T
        base = apply(T, (0.15, 1.75, -0.5))
        for q in range(4):
            a = age - q * 0.5
            if 0 < a < 2.5:
                P.dot(base + [math.sin(a * 3 + q) * 0.2, a * 0.6, 0], 0.18, (1.6, 0.3, 0.8), mode=2, uv=at["heart"])

    def _f_chickens(self, e, age, c, P, at):
        for q in range(12):
            x = -22 + (age * 5.5) - q * 0.9 + math.sin(q * 3) * 0.6
            z = -2.0 + math.sin(q * 1.7) * 3.5
            fr = "run1" if (c.beat_idx * 2 + (c.beat_phase > 0.5) + q) % 2 else "run2"
            P.sprite((x, 0.08 * abs(math.sin(c.t * 18 + q)), z), 0.6, 0.6, at[f"chicken_{fr}"])
        fx = -22 + age * 5.0 - 13
        self.sc.char_sprite(P, self.sc.special["farmer"], f"walk_{1 + (c.beat_idx * 2 + (c.beat_phase > 0.5)) % 4}",
                            (fx, 0, -1.5), face=(1.0, 0.0))

    def _f_rooster(self, e, age, c, P, at):
        x, z = 26.0, -6.0
        P.sprite((x, 1.2, z), 0.9, 0.9, at["chicken_fwd" if age < 1.5 else "chicken_flap"])

    def _f_sheep(self, e, age, c, P, at):
        for q in range(3):
            a = (age * 0.8 + q / 3) % 1.0
            x = 40 + q * 2.0
            z = -4.0 + (a - 0.5) * 4
            y = 1.4 * math.sin(math.pi * a)
            P.sprite((x, y, z), 1.1, 0.8, at[f"sheep{1 if 0.2 < a < 0.8 else 0}"])

    def _f_dog(self, e, age, c, P, at):
        x = 22 - age * 5.0
        z = 2 + math.sin(age) * 2
        P.sprite((x, 0, z), 1.1, 0.75, at[f"dog{(c.beat_idx * 2 + (c.beat_phase > 0.5)) % 2}"], flip=True)

    def _f_sax(self, e, age, c, P, at):
        ci = self.sc.cast_for(e.eid)
        pose = "sax_a" if c.beat_idx % 2 == 0 else "sax_b"
        self.sc.char_sprite(P, ci, pose, (2.4, PLAT_TOP, -15.3), face=(0, 1), y=0.05 * (c.beat_idx % 2))

    def _f_godrays(self, e, age, c, P, at):
        fade = min(1.0, age / 3, (e.t1 - c.t) / 3)
        src = np.array([0, 60, -60.0])
        for q in range(6):
            dst = np.array([-9 + q * 3.6 + math.sin(c.t * 0.3 + q) * 2, 0, -6 + math.cos(q) * 4])
            P.beam(src, dst, 0.5, 3.0, (0.18 * fade, 0.16 * fade, 0.1 * fade), soft=2.5, fade=0.3)

    def _f_birds(self, e, age, c, P, at):
        for q in range(14):
            x = -60 + age * 9 + (q % 5) * 1.6 - abs(q - 7) * 0.8
            y = 22 + abs(q - 7) * 0.9 + math.sin(age * 2 + q) * 0.3
            z = -30 + (q - 7) * 1.4
            P.sprite((x, y, z), 0.9, 0.7, at[f"crow{(int(c.t * 6) + q) % 2}"])

    def _f_nyan(self, e, age, c, P, at):
        x = -70 + age * 16
        y, z = 28 + math.sin(age * 3) * 1.5, -45.0
        P.sprite((x, y, z), 4.0, 2.6, at[f"nyan{int(c.t * 8) % 2}"], anchor=0.5)
        rb = [(1.0, 0.0, 0.0), (1.0, 0.5, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0), (0.1, 0.3, 1.0), (0.5, 0.0, 1.0)]
        for q, col in enumerate(rb):
            yy = y + 0.75 - q * 0.3
            P.beam((x - 1.9, yy + 0.1 * math.sin(c.t * 10 + q), z), (x - 40, yy, z), 0.15, 0.15, tuple(v * 0.8 for v in col), soft=0.6)

    def _f_pacman(self, e, age, c, P, at):
        d = e.p.get("dir", 1)
        x0 = -16 * d
        x = x0 + d * age * 3.0
        z = -3.0
        P.sprite((x, 0.35, z), 0.7, 0.7, at[f"chomp{int(c.t * 10) % 4}"], flip=d < 0)
        for q, g in enumerate(["ghost_r", "ghost_p", "ghost_c", "ghost_o"]):
            name = g if (c.bar_idx // 2) % 4 else "ghost_b"
            P.sprite((x - d * (1.4 + q * 0.9), 0.35, z + 0.1 * q), 0.7, 0.7, at[f"{name}{int(c.t * 6) % 2}"])
        for q in range(12):
            px = x + d * (0.8 + q * 0.7)
            P.dot((px, 0.35, z), 0.06, (1.2, 1.0, 0.6), mode=3)

    def _f_hotdog(self, e, age, c, P, at):
        x, z = 5.5, -2.5
        P.sprite((x, 0.15 * abs(math.sin(math.pi * c.beat_phase)), z), 0.9, 1.8, at[f"hotdog{c.beat_idx % 2}"])

    def _f_baby(self, e, age, c, P, at):
        pose = ["bounce_dn", "bounce_up", "hands_up", "sway_l", "sway_r", "jump"][(c.beat_idx // 1) % 6]
        self.sc.char_sprite(P, self.sc.special["baby"], pose, (-2.2, PLAT_TOP, -15.2), face=(0, 1), scale=0.8)

    def _f_goat(self, e, age, c, P, at):
        x, z = 24.4, -10.0
        scream = c.beat_phase < 0.5 and c.kick
        P.sprite((x, 1.1, z), 1.2, 1.1, at[f"goat{1 if scream else 0}"])

    def _f_balloon(self, e, age, c, P, at):
        L = e.t1 - e.t0
        s = age / L
        x = -120 + 240 * s
        y = 45 + 10 * math.sin(s * 3)
        z = -90 + 30 * s
        for q in range(6):
            col = [(0.9, 0.05, 0.05), (1, 0.5, 0), (1, 0.9, 0), (0, 0.6, 0.2), (0.1, 0.25, 0.8), (0.5, 0.1, 0.6)][q]
            P.m("ico2", A((x, y + 5.6 - q * 2.1, z), (12.3 - abs(q - 2.5) * 1.6, 2.2, 12.3 - abs(q - 2.5) * 1.6)), col, 0)
        P.m("box", A((x, y - 9, z), (2, 1.6, 2)), (0.45, 0.3, 0.15), 4)
        if (c.bar_idx % 4) == 0 and c.bar_frac < 0.15:
            P.dot((x, y - 7.5, z), 2.5, (2.0, 0.9, 0.2), soft=2)

    def _f_kites(self, e, age, c, P, at):
        names = ["progress", "trans", "nonbinary", "bi", "pan", "lesbian", "rainbow"]
        for q in range(5):
            bx, bz = -20 + q * 10, 35 + (q % 2) * 8
            h = 14 + q % 3 * 3
            sw = math.sin(c.t * 0.8 + q) * 3 + c.wind[2] * 4
            x, y, z = bx + sw * c.wind[0], h + math.sin(c.t * 1.3 + q), bz + sw * c.wind[1]
            uv = at[f"flag_{names[(q + e.eid) % len(names)]}"]
            P.m("flag", A((x, y, z), (2.2, 1.4, 1), (0.3 * math.sin(c.t + q), math.atan2(c.wind[0], c.wind[1]), 0.6)), (1, 1, 1), 1, sway=0.8, extra=uv)
            P.beam((x, y, z), (bx, 1.2, bz), 0.006, 0.006, (0.05, 0.05, 0.05), soft=1)

    def _f_smiley(self, e, age, c, P, at):
        rise = ease(min(1.0, age / 4, (e.t1 - c.t) / 4))
        y = TRUSS_Y + 0.5 + 3.5 * rise + 0.2 * math.sin(c.t * 1.3)
        s = 4.0 * (1 + 0.05 * c.env["beat"])
        P.sprite((0, y, -17.5), s, s, at["smiley"], anchor=0.0, flash=0.15 * c.env["beat"], roll=0.08 * math.sin(c.t * 0.9))

    def _f_farmer(self, e, age, c, P, at):
        L = e.t1 - e.t0
        s = age / L
        x = -14 + 28 * s
        z = 4 - 9 * math.sin(math.pi * s)
        pose = f"walk_{1 + (c.beat_idx * 2 + (c.beat_phase > 0.5)) % 4}" if (c.bar_idx % 4) else "scared"
        self.sc.char_sprite(P, self.sc.special["farmer"], pose, (x, 0, z), face=(1.0, -0.3))

    def _f_qblocks(self, e, age, c, P, at):
        for q in range(4):
            x, z = -6 + q * 4, -6 + (q % 2) * 3
            hit = (c.bar_idx + q) % 4 == 0 and c.bar_frac < 0.12
            y = 3.6 + (0.15 if hit else 0)
            P.sprite((x, y, z), 0.7, 0.7, at["qblock"], anchor=0.5)
            if (c.bar_idx + q) % 4 == 0 and c.bar_frac < 0.25:
                a = c.bar_frac / 0.25
                P.sprite((x, y + 0.5 + a * 1.2, z), 0.45, 0.6, at[f"coin{int(c.t * 12) % 4}"], anchor=0.5)

    def _f_pride_jelly(self, e, age, c, P, at):
        pass   # world reads this from c.events

    def _f_creeper(self, e, age, c, P, at):
        L = e.t1 - e.t0
        x = 9 - 6 * min(1.0, age / (L * 0.7))
        z = -1.0
        if age < L * 0.8:
            pose = "walk_2" if (c.beat_idx % 2) else "walk_1"
            self.sc.char_sprite(P, self.sc.creeper_char, pose, (x, 0, z), face=(-1, 0))
        else:
            a = age - L * 0.8
            if a < 3:
                self._confetti(e, a, c, P, n=90, origin=(x, 1.0, z))

    def _f_mushrooms(self, e, age, c, P, at):
        W = self.sc.world
        grow = ease(min(1.0, age / 6, (e.t1 - c.t) / 4))
        for ti, tr in enumerate(W.trees):
            for q in range(3):
                a = q * 2.1 + ti
                x, z = tr["x"] + math.cos(a) * 1.0, tr["z"] + math.sin(a) * 1.0
                s = 0.5 * grow * (1 + 0.25 * c.env["lowmid"])
                col = hue(0.8 + 0.1 * q + c.t * 0.05, 0.8, 1.0)
                P.m("cyl6", A((x, 0, z), (0.12 * s * 2, 0.5 * s * 2, 0.12 * s * 2)), (0.9, 0.9, 0.85), 0)
                P.j("bell", A((x, s * 0.9, z), (s * 1.3, s * 0.6, s * 1.3)), tuple(v * 1.2 for v in col), extra=(1.0, 0, 0, 0))

    def _f_singalong(self, e, age, c, P, at):
        for q in range(8):
            a = (age * 0.5 + q / 8) % 1.0
            x = -8 + q * 2.2 + math.sin(c.t + q) * 0.5
            P.dot((x, 2.2 + a * 3, -4 + math.cos(q) * 3), 0.2, (1.4 * (1 - a), 1.4 * (1 - a), 1.6 * (1 - a)), mode=2, uv=at["note"])

    def _f_fireworks(self, e, age, c, P, at):
        rng = np.random.default_rng(e.eid * 31 + 7)
        for b in range(int(min(age / 1.3, 14)) + 1):
            t0 = b * 1.3
            a = age - t0
            if a < 0 or a > 2.6:
                continue
            ctr = np.array([rng.uniform(-40, 40), rng.uniform(35, 55), rng.uniform(-70, -40)])
            col = np.array(hue(rng.random(), 0.7, 1.0))
            n = 60
            th = rng.uniform(0, 2 * math.pi, n)
            ph = np.arccos(rng.uniform(-1, 1, n))
            v = np.stack([np.sin(ph) * np.cos(th), np.cos(ph), np.sin(ph) * np.sin(th)], 1) * 9
            p = ctr + v * (1 - math.exp(-a * 1.5)) / 1.5
            p[:, 1] -= 2.0 * a * a
            rows = np.zeros((n, 20), np.float32)
            rows[:, 0:3] = p
            rows[:, 3] = 0.5
            rows[:, 8:11] = col * 2.5 * max(0.0, 1 - a / 2.6)
            rows[:, 11] = 1
            rows[:, 13] = 3
            P.glows_many(rows)

    def _f_shootingstar(self, e, age, c, P, at):
        if c.night < 0.5:
            return
        a, h = e.p["a"], e.p["h"]
        d = np.array([math.cos(a), -0.25, math.sin(a)])
        start = np.array([math.cos(a + 1.5) * 300, 300 * h + 60, math.sin(a + 1.5) * 300])
        p = start + d * age * 220
        P.beam(p, p - d * 40, 0.6, 0.05, (1.5, 1.5, 1.8), soft=1.5, fade=1.0)

    def _f_ufo(self, e, age, c, P, at):
        L = e.t1 - e.t0
        tx, tz = e.p.get("target", (-8.0, 46.0))
        arrive = ease(min(1.0, age / 5.0))
        leave = ease(max(0.0, (age - (L - 5)) / 5.0))
        x = tx + (1 - arrive) * -80 + leave * 120
        y = 18 + (1 - arrive) * 30 + leave * 60 + math.sin(age * 1.7) * 0.6
        z = tz + (1 - arrive) * -40 - leave * 60
        tilt = 0.12 * math.sin(age * 2.1)
        T = A((x, y, z), (1, 1, 1), (tilt, age * 0.8, 0))
        P.m("cyl", A((x, y, z), (12, 0.8, 12), (tilt, age * 0.8, 0)), (0.6, 0.62, 0.68), 8)
        P.m("ico2", A((x, y + 0.6, z), (5, 3.2, 5)), (0.3, 0.6, 0.7), 8, emis=(0.1, 0.4, 0.5))
        n = 12
        for q in range(n):
            ang = q / n * 2 * math.pi + age * 0.8
            on = (q + c.beat_idx * 2 + (c.beat_phase > 0.5)) % 3 == 0
            col = hue(q / n + age * 0.1, 0.9, 1.0)
            p = (x + math.cos(ang) * 5.8, y + 0.35, z + math.sin(ang) * 5.8)
            P.dot(p, 0.6 if on else 0.35, tuple(v * (2.5 if on else 0.6) for v in col), soft=3)
        beam = arrive * (1 - leave)
        if beam > 0.05:
            P.beam((x, y - 0.2, z), (x, 0.0, z), 1.2, 6.0, (0.25 * beam, 0.6 * beam, 0.4 * beam), soft=1.4, fade=0.2)
            P.spot((x, y - 0.5, z), (0, -1, 0), (0.4, 1.0, 0.7), 4.0 * beam, y + 6, 18.0, 12.0)
            P.ring((x, 0.08, z), 5.5 + math.sin(age * 4) * 0.4, (0.3 * beam, 0.9 * beam, 0.6 * beam), width=0.1)
            if not e.p.get("crop"):
                rise = ease(min(1.0, max(0.0, (age - 6) / 10)))
                P.sprite((x, rise * (y - 2), z), 2.4, 1.6, at["cow_moo"], roll=rise * 1.2, anchor=0.5)

    def _f_konami(self, e, age, c, P, at):
        pass   # HUD arrows; crowd steps along

    def _f_smokering(self, e, age, c, P, at):
        T = self.sc.world.tractor_T
        ex = apply(T, (0.35, 2.7, 1.3))
        for q in range(3):
            a = age - q * 0.4
            if a > 0:
                P.ring(ex + [0, a * 1.5, 0], 0.3 + a * 0.4, (0.15, 0.15, 0.15), width=0.15)

    # ---------------------------------------------------------------- post effects and HUD
    def post(self, c: Ctx) -> dict:
        out = {"invert": 0.0, "filter": 0, "filter_amt": 0.0, "psy": 0.0, "hue": 0.0, "ca": 0.0}
        for e in c.events:
            age = c.t - e.t0
            if e.kind == "drop":
                if age < 2.5 / self.sc.fps and e.p.get("strength", 0) > 0.4:
                    out["invert"] = 1.0
                out["ca"] = max(out["ca"], 0.012 * max(0.0, 1 - age / 1.5))
            elif e.kind == "filter":
                a = min(1.0, age / 0.5, (e.t1 - c.t) / 0.5)
                out["filter"], out["filter_amt"] = e.p.get("mode", 1), a * 0.9
            elif e.kind == "psychedelic":
                a = min(1.0, age / 6, (e.t1 - c.t) / 3)
                out["psy"] = max(out["psy"], a * (0.55 + 0.35 * c.env["lowmid"]))
                out["hue"] = 0.15 * math.sin(c.t * 0.2) * a
            elif e.kind == "rollover":
                out["filter"], out["filter_amt"] = 4, 1.0
            elif e.kind == "gong" and age < 0.15:
                out["invert"] = 0.6
        return out

    def konami(self, c: Ctx):
        for e in c.events:
            if e.kind == "konami":
                return (c.t - e.t0)
        return None
