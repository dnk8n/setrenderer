"""Combat for one act (one boss), planned up front from the music so any frame can be drawn on its own.
Cuphead's rules, played out on the cartoon's clock:

* each hero has 3 HP per take; a boss shot that reaches a hero costs 1 HP, knocks them back and leaves
  them blinking and untouchable for a moment
* at 0 HP the hero drops and their ghost rises; it glows pink, so the partner can run under it and
  parry it to bring them back with 1 HP; a ghost nobody parries floats away and leaves a little grave
* when both heroes are down the take is lost: the boss laughs, a TAKE card, and the fight restarts
  from the top with the boss fresh; the last take of every act is won, so each boss is beaten once
* five super cards per hero fill from the damage they deal and from parries; one card buys an EX shot,
  a full hand a Super Art on a drop, which spends all five
* the boss's damage shows on it (dents, bandages, black eyes, missing leaves...) and resets on a restart

Every boss shot is fired on a beat and travels a whole number of beats, so hits, dodges, parries and
revives land on the beat. Shots are aimed by role: a hit is aimed at a hero, a dodge at a hero's shins
(they hop it), a parry at a hero in mid-jump, and a miss over everyone's heads or into the floor; every
path is checked against both heroes' motion so nothing passes through anyone by accident.
"""
from __future__ import annotations

import bisect
import math
from dataclasses import dataclass

import numpy as np

from . import story
from .story import h01

import os
DEBUG = bool(os.environ.get("HOSE_DEBUG"))
HP = 3
INV_HIT = 1.5          # seconds untouchable after a hit
INV_REVIVE = 2.0       # ... and after a revive
GHOST_RISE = 90.0      # px/s
GHOST_Y0 = 170.0       # ghost starts this far above the feet
BULLET_CARD = 1 / 45   # super meter per peashooter bullet that lands
G = 1400.0             # arc gravity
GROUND = 905.0
SHOT_R = 26.0
HALF_W, TALL = 46.0, 255.0          # ground hero hitbox (feet at the bottom)
PLANE_RX, PLANE_RY = 150.0, 88.0    # plane hitbox


@dataclass
class Shot:            # a boss projectile
    ts: float
    kind: str          # aimed | arc | wave | rain | ring
    x0: float
    y0: float
    vx: float
    vy: float
    pink: bool
    size: float
    seed: float
    life: float
    end: str = "off"   # off | parry | hit | floor
    who: int = -1      # the hero it is meant for
    role: str = "miss"  # hit | dodge | parry | miss | side | ring
    arrive: float = 0.0


@dataclass
class Jump:
    t0: float
    dur: float
    height: float
    parry: bool
    kind: str = "hop"  # hop | dodge | parry | revive | egg


@dataclass
class Run:             # a stretch where a hero leaves their lane (to revive someone, or getting back up)
    t0: float
    t1: float
    t2: float
    t3: float
    x: float
    y: float


@dataclass
class Down:
    h: int
    t: float
    x: float
    y: float
    revive: float | None = None     # time the partner parries the ghost
    take: int = 1
    away: float = 0.0               # time the ghost leaves the screen (unrevived)


def _smooth(u):
    u = np.clip(u, 0.0, 1.0)
    return u * u * (3 - 2 * u)


class Fight:
    """Everything that happens in one act, for both heroes and the boss."""

    def __init__(self, m: story.Music, P: story.Plan, a: story.Act, boss_info: dict, seed: int, cfg: dict):
        self.m, self.a, self.P = m, a, P
        self.seed = seed
        self.bar = 4 * m.period
        self.sky = a.sky
        self.ground = GROUND
        self.ex, self.ey = boss_info["emit"]
        self.pats = boss_info["patterns"]
        self.rate = float(cfg.get("attack_rate", 1.0))
        self.inters = [i for i in P.inters if i.act == a.k]
        self.shots: list[Shot] = []
        self.jumps: list[list[Jump]] = [[], []]
        self.runs: list[list[Run]] = [[], []]
        self.hits: list[list[float]] = [[], []]
        self.downs: list[Down] = []
        self.parries: list[tuple] = []           # (t, hero, x, y, kind)
        self.revives: list[tuple] = []           # (t, by, of)
        self.bullets: list[tuple[float, int]] = []
        self.exs: list[tuple[float, int]] = []   # EX shots: (fire time, hero), they land one beat later
        self.supers: list[float] = []            # super start times (both heroes)
        self.super_by: list[tuple[float, int]] = []
        self.super_dur = 2 * self.bar
        self.inv: list[list[tuple[float, float]]] = [[], []]
        self.busy: list[list[tuple[float, float]]] = [[], []]
        self._blk: dict = {}
        self.anomalies = 0
        self.patterns: list[tuple] = []          # (take, won, script) for reports
        self.meter_t: list[list[float]] = [[], []]
        self.meter_v: list[list[float]] = [[], []]
        self.egg_hops(P)
        for tk in a.takes:
            self._plan_take(tk)
        self.shots.sort(key=lambda s: s.ts)
        self.bullets.sort()
        self._bt = np.array([b[0] for b in self.bullets]) if self.bullets else np.zeros(0)
        self._st = np.array([s.ts for s in self.shots]) if self.shots else np.zeros(0)
        self._validate()

    # ================================================================ hero motion
    def _tgt(self, h: int, blk: int):
        k = (h, blk)
        if k not in self._blk:
            lo, hi = ((110, 470), (540, 900))[h]
            self._blk[k] = (lo + (hi - lo) * h01(self.seed, "hx", h, blk), 260 + 420 * h01(self.seed, "hy", h, blk))
        return self._blk[k]

    def base(self, h: int, tt):
        """Lane position (vectorised): every two bars each hero shuffles to a new spot in their lane."""
        m = self.m
        tt = np.atleast_1d(np.asarray(tt, np.float64))
        db = m.db
        bk = np.clip(np.searchsorted(db, tt, side="right") - 1, 0, None)
        blk = bk // 2
        uniq, inv = np.unique(blk, return_inverse=True)
        t1 = np.array([self._tgt(h, int(b)) for b in uniq])
        t0 = np.array([self._tgt(h, int(b) - 1) for b in uniq])
        x1, y1 = t1[inv, 0], t1[inv, 1]
        x0, y0 = t0[inv, 0], t0[inv, 1]
        idx = blk * 2
        tb = np.where(idx < len(db), db[np.minimum(idx, len(db) - 1)], db[-1] + (idx - len(db) + 1) * 4 * m.period)
        e = _smooth((tt - tb) / m.period)
        x = x0 + (x1 - x0) * e
        if self.sky:
            y = y0 + (y1 - y0) * e + np.sin(tt * 2.1 + h * 2) * 26
        else:
            y = np.full_like(tt, self.ground)
        moving = (e > 0) & (e < 1) & (np.abs(x1 - x0) > 30)
        return x, y, moving, np.where(x1 >= x0, 1.0, -1.0)

    def lift(self, h: int, tt):
        tt = np.atleast_1d(np.asarray(tt, np.float64))
        out = np.zeros_like(tt)
        js = self.jumps[h]
        if not js:
            return out
        lo, hi = float(tt.min()), float(tt.max())
        i0 = max(0, bisect.bisect_left([j.t0 for j in js], lo - 1.5))
        for j in js[i0:]:
            if j.t0 > hi:
                break
            u = (tt - j.t0) / j.dur
            sel = (u >= 0) & (u < 1)
            out[sel] = np.maximum(out[sel], 4 * j.height * u[sel] * (1 - u[sel]))
        return out

    def pos(self, h: int, tt):
        """(x, y feet or plane centre, lift) with knockback and runs applied (vectorised)."""
        tt = np.atleast_1d(np.asarray(tt, np.float64))
        x, y, _, _ = self.base(h, tt)
        for r in self.runs[h]:
            if r.t3 < tt[0] or r.t0 > tt[-1]:
                continue
            w = np.where(tt < r.t1, _smooth((tt - r.t0) / max(r.t1 - r.t0, 1e-3)),
                         np.where(tt <= r.t2, 1.0, 1 - _smooth((tt - r.t2) / max(r.t3 - r.t2, 1e-3))))
            w = np.where((tt >= r.t0) & (tt <= r.t3), w, 0.0)
            x = x + w * (r.x - x)
            if self.sky:
                y = y + w * (r.y - y)
        for th in self.hits[h]:
            d = tt - th
            sel = (d >= 0) & (d < 0.8)
            if sel.any():
                x[sel] -= 80 * (1 - np.exp(-d[sel] / 0.05)) * np.exp(-d[sel] / 0.3)
        for dn in self.downs:
            if dn.h != h:
                continue
            end = dn.revive + 0.25 if dn.revive is not None else 1e18
            sel = (tt >= dn.t) & (tt < end)
            x = np.where(sel, dn.x, x)
            y = np.where(sel, dn.y, y)
        return x, y, self.lift(h, tt)

    def alive(self, h: int, tt):
        tt = np.atleast_1d(np.asarray(tt, np.float64))
        ok = np.ones(tt.shape, bool)
        for dn in self.downs:
            if dn.h == h:
                end = dn.revive + 0.25 if dn.revive is not None else self._take_end(dn.t)
                ok &= ~((tt >= dn.t) & (tt < end))
        return ok

    def _take_end(self, t: float) -> float:
        tk = story.take_at(self.a, t)
        nxt = [x.t0 for x in self.a.takes if x.t0 > tk.t0]
        return nxt[0] if nxt else 1e18

    def is_alive(self, h: int, t: float) -> bool:
        return bool(self.alive(h, [t])[0])

    def _inv(self, h: int, t: float) -> bool:
        return any(a <= t < b for a, b in self.inv[h])

    def _busy(self, h: int, t0: float, t1: float) -> bool:
        return any(a < t1 and t0 < b for a, b in self.busy[h])

    def _jumping(self, h: int, t0: float, t1: float) -> bool:
        return any(j.t0 < t1 and t0 < j.t0 + j.dur for j in self.jumps[h])

    def _add_jump(self, h: int, j: Jump, skip=None) -> bool:
        """Add a jump if it doesn't carry the hero into a shot already in the air."""
        self.jumps[h].append(j)
        self.jumps[h].sort(key=lambda x: x.t0)
        for s in self._shots_between(j.t0, j.t0 + j.dur):
            if s is skip or s.role == "ring":
                continue
            c = self._contact(s, h)
            want = (s.who == h and s.role in ("hit", "parry"))
            if c is not None and not (want and abs(c - s.arrive) < 0.05):
                self.jumps[h].remove(j)
                return False
        return True

    def _shots_between(self, t0: float, t1: float):
        return [s for s in self.shots if s.ts <= t1 and s.ts + s.life >= t0]

    # ================================================================ shots
    def shot_xy(self, s: Shot, tt):
        tt = np.asarray(tt, np.float64)
        if s.kind == "arc":
            return s.x0 + s.vx * tt, s.y0 + s.vy * tt + 0.5 * G * tt * tt
        if s.kind == "wave":
            return s.x0 + s.vx * tt, s.y0 + np.sin(tt * 7 + s.seed * 6) * 70
        return s.x0 + s.vx * tt, s.y0 + s.vy * tt

    def _life(self, s: Shot) -> float:
        """Until it leaves the screen or reaches the floor."""
        tt = np.arange(0.0, 6.0, 1 / 60)
        x, y = self.shot_xy(s, tt)
        out = (x < -160) | (x > 2100) | (y > 1200) | ((y < -400) & (np.arange(len(tt)) > 30))
        if not self.sky and s.kind in ("aimed", "arc", "rain", "wave"):
            floor = y > self.ground - 14
            if floor.any():
                k = int(np.argmax(floor))
                if not out[:k].any():
                    s.end = "floor"
                    return float(tt[k])
        return float(tt[int(np.argmax(out))]) if out.any() else 6.0

    def _contact(self, s: Shot, h: int, t_end: float | None = None):
        """First time the shot touches living hero h (None if it never does)."""
        life = s.life if t_end is None else t_end - s.ts
        if life <= 0:
            return None
        tt = np.arange(0.0, life + 1e-9, 1 / 120)
        sx, sy = self.shot_xy(s, tt)
        ta = s.ts + tt
        x, y, lf = self.pos(h, ta)
        al = self.alive(h, ta)
        r = SHOT_R * s.size
        if self.sky:
            cy = y - lf + 5
            inside = ((sx - (x - 10)) / (PLANE_RX + r)) ** 2 + ((sy - cy) / (PLANE_RY + r)) ** 2 < 1
        else:
            feet = y - lf
            inside = (np.abs(sx - x) < HALF_W + r) & (sy > feet - TALL - r) & (sy < feet + 8)
        inside &= al
        if not inside.any():
            return None
        return float(ta[int(np.argmax(inside))])

    def _clear(self, s: Shot, until: float | None = None, ignore=-1) -> bool:
        return all(self._contact(s, h, until) is None for h in (0, 1) if h != ignore)

    def _arrival(self, ts: float, n: int) -> float:
        return float(self.m.beat_time(self.m.beat_pos(ts) + n))

    def _aim(self, kind: str, ts: float, n: int, tx: float, ty: float, seed: float, pink=False) -> Shot:
        T = self._arrival(ts, n) - ts
        ex, ey = self.ex, self.ey
        if kind == "arc":
            vx = (tx - ex) / T
            vy = (ty - ey - 0.5 * G * T * T) / T
            s = Shot(ts, "arc", ex, ey, vx, vy, pink, 1.1, seed, T)
        elif kind == "wave":
            y0 = ty - math.sin(T * 7 + seed * 6) * 70
            s = Shot(ts, "wave", ex, y0, (tx - ex) / T, 0.0, pink, 1.0, seed, T)
        elif kind == "rain":
            s = Shot(ts, "rain", tx + 40 * T, ty - 520 * T, -40.0, 520.0, pink, 1.0, seed, T)
        else:
            s = Shot(ts, "aimed", ex, ey, (tx - ex) / T, (ty - ey) / T, pink, 1.0, seed, T)
        s.arrive = ts + T
        return s

    def _aim_edge(self, kind, ts, n, tx, ty, seed, h, ta, pink=False):
        """A shot at hero h that touches them exactly at ta: aimed at the centre first, then re-aimed at
        the point where that path first touches the hero, so it arrives (and pops) on the beat."""
        s = self._aim(kind, ts, n, tx, ty, seed, pink)
        if s.kind != "rain" and not (-250 < s.y0 < 1300):
            return None
        s.life = ta - ts + 0.3
        c = self._contact(s, h)
        if c is None or c > ta + 0.05:
            return None
        if c < ta - 0.03:
            px, py = self.shot_xy(s, c - ts)
            s = self._aim(kind, ts, n, float(px), float(py), seed, pink)
            s.life = ta - ts + 0.3
            c = self._contact(s, h)
            if c is None or abs(c - ta) > 0.05:
                return None
        s.life = ta - ts
        return s

    def _n_for(self, kind: str, ts: float, tx: float, ty: float, pink=False):
        """Beats of travel for a shot (fast enough to threaten, slow enough to read)."""
        p = self.m.period
        d = math.hypot(tx - self.ex, ty - self.ey)
        if kind == "arc":
            ns = [2, 3]
        elif kind == "wave":
            ns = [3, 4, 2]
        elif kind == "rain":
            ns = [max(2, int(round(1.9 / p))), max(2, int(round(1.9 / p))) + 1]
        else:
            n0 = int(np.clip(round(d / (760 * p)), 1, 4))
            ns = [n0, n0 + 1, max(1, n0 - 1)]
        if pink:
            ns = [max(2, n) for n in ns]
        return ns

    # ================================================================ planning one take
    def _slots(self, tk: story.Take):
        m, a = self.m, self.a
        bar = self.bar
        out = []
        n_pink = int(h01(self.seed, tk.n, "pk") * 4)
        for bk in range(m.bar_at(tk.go + 0.05) + 1, m.bar_at(tk.end - 0.05)):
            tb = m.bar_time(bk)
            if any(i.t0 - bar <= tb < i.t1 for i in self.inters):
                continue
            kick = bool(m.st.bar_kick[min(bk, len(m.st.bar_kick) - 1)]) if len(m.st.bar_kick) else True
            if not kick:
                continue
            ph = story.phase_of(a, tb)
            energy = float(m.st.bar_energy[min(bk, len(m.st.bar_energy) - 1)])
            per_bar = [1, 2, 4][ph] if energy > 0.35 else [1, 1, 2][ph]
            per_bar = max(1, int(round(per_bar * self.rate)))
            for j in range(per_bar):
                beat = j * 4 // per_bar
                ts = float(m.beat_time(m.beat_pos(tb) + beat))
                r = h01(self.seed, bk, j)
                kinds = self.pats[min(ph, len(self.pats) - 1)]
                kind = kinds[int(r * len(kinds))]
                pink = (n_pink % 4 == 3) and kind not in ("ring", "rain")
                n_pink += 1
                out.append({"ts": ts, "kind": kind, "ph": ph, "pink": pink, "seed": r, "bk": bk, "j": j, "used": False})
        return out

    def _script(self, tk: story.Take):
        """What should happen to the heroes this take: a list of (target time, hero) hits, and for each
        hero's deaths whether the partner revives them (in order)."""
        D = tk.end - tk.go
        key = (self.seed, self.a.k, tk.n)
        A = 0 if h01(key, "who") < 0.5 else 1
        B = 1 - A
        j = lambda tag: (h01(key, tag) - 0.5) * 0.08 * D  # noqa: E731
        at = lambda f, tag: tk.go + f * D + j(tag)  # noqa: E731
        fin = tk.end - 1.25 * self.bar
        r = h01(key, "pattern")
        if not tk.won:
            if r < 0.38:
                pat = "revive_then_wipe"      # A goes down, B saves them; later A falls for good, then B
                hits = [(at(0.16, 1), A), (at(0.3, 2), A), (at(0.44, 3), A), (at(0.78, 4), A),
                        (at(0.38, 5), B), (at(0.66, 6), B), (fin, B)]
                rev = {A: [True, False], B: [False]}
            elif r < 0.58:
                pat = "one_then_other"        # A's ghost floats off out of reach; B soldiers on, then falls
                hits = [(at(0.22, 1), A), (at(0.5, 2), A), (at(0.72, 3), A),
                        (at(0.4, 4), B), (at(0.86, 5), B), (fin, B)]
                rev = {A: [False], B: [False]}
            elif r < 0.78:
                pat = "both_revive"           # they save each other once each, then go down together
                hits = [(at(0.14, 1), A), (at(0.26, 2), A), (at(0.36, 3), A), (at(0.85, 4), A),
                        (at(0.3, 5), B), (at(0.5, 6), B), (at(0.62, 7), B), (fin, B)]
                rev = {A: [True, False], B: [True, False]}
            else:
                pat = "double"                # both run out of luck in the same bar or two
                hits = [(at(0.3, 1), A), (at(0.62, 2), A), (fin - 3 * self.m.period, A),
                        (at(0.42, 4), B), (at(0.72, 5), B), (fin, B)]
                rev = {A: [False], B: [False]}
        else:
            if r < 0.14:
                pat = "clean"
                hits = [(at(0.3 + 0.5 * h01(key, "c"), 1), A)]
                rev = {A: [], B: []}
            elif r < 0.32:
                pat = "scrape"                # both end on their last heart
                hits = [(at(0.25, 1), A), (at(0.7, 2), A), (at(0.4, 3), B), (at(0.85, 4), B)]
                rev = {A: [], B: []}
            elif r < 0.64:
                pat = "revive"
                hits = [(at(0.18, 1), A), (at(0.34, 2), A), (at(0.5, 3), A), (at(0.75, 4), B)]
                rev = {A: [True], B: []}
            elif r < 0.82:
                pat = "double_revive"         # each saves the other once on the way to the knockout
                hits = [(at(0.12, 1), A), (at(0.24, 2), A), (at(0.36, 3), A),
                        (at(0.3, 4), B), (at(0.5, 5), B), (at(0.62, 6), B)]
                rev = {A: [True], B: [True]}
            else:
                pat = "solo"                  # A's ghost floats off; B finishes the job alone
                hits = [(at(0.3, 1), A), (at(0.52, 2), A), (at(0.7, 3), A), (at(0.45, 4), B)]
                rev = {A: [False], B: []}
        hits = [(min(max(t, tk.go + 6.0), tk.end - 0.5 * self.bar), h) for t, h in hits]
        return pat, sorted(hits), rev

    def _plan_take(self, tk: story.Take):
        bar = self.bar
        slots = self._slots(tk)
        pat, hits, rev = self._script(tk)
        self.patterns.append((tk.n, tk.won, pat))
        hp = [HP, HP]
        n_dead = [0, 0]

        def free(h, t):
            return (self.is_alive(h, t) and not self._inv(h, t) and not self._busy(h, t - 0.5, t + 0.5)
                    and not self._jumping(h, t - 0.45, t + 0.45)
                    and not any(abs(t - dn.t) < 0.7 for dn in self.downs if dn.h != h))

        def place_hit(h, t_star, window, lo=None, hi=None, final=False):
            lo = tk.go + 2.0 if lo is None else lo
            hi = tk.end - 0.4 * bar if hi is None else hi
            cands = []
            for sl in slots:
                if sl["used"] or sl["pink"] and not final:
                    continue
                if sl["ts"] > t_star + window or sl["ts"] < t_star - window - 3.0:
                    continue
                kinds = [sl["kind"]] + [k for k in ("aimed", "arc", "wave") if k != sl["kind"]]
                for kind in kinds:
                    if kind == "ring":
                        continue
                    if kind == "spread":
                        kind = "aimed"
                    for n in range(1, 6):
                        ta = self._arrival(sl["ts"], n)
                        if not (lo <= ta <= hi) or abs(ta - t_star) > window:
                            continue
                        cands.append((abs(ta - t_star) + 0.05 * n + (0.3 if kind != sl["kind"] else 0), sl, kind, n, ta))
            cands.sort(key=lambda c: c[0])
            if DEBUG:
                print("place", h, round(t_star, 1), "cands", len(cands), "free", sum(free(h, c[4]) for c in cands[:40]))
            for _, sl, kind, n, ta in cands[:40]:
                if not free(h, ta) or (self._inv(h, ta)):
                    continue
                x, y, _ = self.pos(h, [ta])
                tx = float(x[0])
                ty = float(y[0]) - (130 if not self.sky else -5)
                if kind == "rain":
                    ty = float(y[0]) - (230 if not self.sky else 0)
                s = self._aim_edge(kind, sl["ts"], n, tx, ty, sl["seed"], h, ta)
                if DEBUG:
                    print("   try", kind, n, round(ta, 2), "edge", s is not None, "clear", s is not None and self._clear(s, ta, ignore=h))
                if s is None:
                    continue
                s.who, s.role, s.end = h, "hit", "hit"
                if not self._clear(s, ta, ignore=h):
                    continue
                sl["used"] = True
                self.shots.append(s)
                return ta
            return None

        def kill(h, t):
            x, y, _ = self.pos(h, [t])
            dn = Down(h, t, float(x[0]), float(y[0]), None, tk.n)
            dn.away = t + (y[0] - GHOST_Y0 + 120) / GHOST_RISE if not self.sky else t + (y[0] + 120) / GHOST_RISE
            self.downs.append(dn)
            return dn

        def try_revive(dn: Down, by: int):
            m = self.m
            for k in (4, 5, 3, 6):
                t_r = float(m.beat_time(round(m.beat_pos(dn.t)) + k))
                if t_r > tk.end - bar or any(i.t0 - 0.5 < t_r < i.t1 for i in self.inters):
                    continue
                if not self.is_alive(by, dn.t) or not self.is_alive(by, t_r):
                    continue
                if self._busy(by, t_r - 1.6, t_r + 0.5) or self._jumping(by, t_r - 1.6, t_r + 0.5):
                    continue
                if any(t_r - 1.8 <= th <= t_r + 0.5 for th in self.hits[by]):
                    continue
                gx, gy = self.ghost_xy(dn, t_r)
                run = Run(min(dn.t + m.period, t_r - 0.9), t_r - 0.32, t_r + 0.25, t_r + 0.25 + 2 * m.period,
                          gx - 30.0 if gx > 300 else gx + 30.0, gy + (150.0 if self.sky else 0.0))
                if self.sky:
                    lift = 150.0
                else:
                    lift = float(np.clip(self.ground - 230 - gy, 110, 240))
                self.runs[by].append(run)
                jmp = Jump(t_r - 0.3, 0.6, lift, True, "revive")
                if not self._add_jump(by, jmp) or not self._run_ok(by, run):
                    self.runs[by].remove(run)
                    if jmp in self.jumps[by]:
                        self.jumps[by].remove(jmp)
                    continue
                dn.revive = t_r
                self.busy[by].append((t_r - 1.6, t_r + 0.5))
                self.inv[dn.h].append((t_r, t_r + 0.25 + INV_REVIVE))
                # getting back up: back at the body, then home to the lane
                self.runs[dn.h].append(Run(t_r, t_r + 0.01, t_r + 0.3, t_r + 0.3 + 2 * m.period, dn.x, dn.y))
                self.parries.append((t_r, by, gx, gy, "ghost"))
                self.revives.append((t_r, by, dn.h))
                return True
            return False

        # ---- hits, deaths and revives, in time order
        for t_star, h in hits:
            other = 1 - h
            if not self.is_alive(h, t_star):
                continue
            last_standing = not self.is_alive(other, t_star) or hp[other] <= 0
            if tk.won and hp[h] == 1 and last_standing:
                continue        # the winning take never loses both heroes
            final = (not tk.won) and t_star >= tk.end - 1.3 * bar
            window = 1.6 * bar if final else 6.0 + 2 * bar
            ta = place_hit(h, t_star, window, final=final)
            if ta is None and final:
                ta = place_hit(h, t_star, 6 * bar, lo=tk.end - 6 * bar, final=True)
            step = t_star
            while ta is None and not final and step < tk.end - 8 * bar:
                step += 4 * bar          # no shots here (a quiet stretch): try a little later
                ta = place_hit(h, step, window, hi=tk.end - (4 if tk.won else 2) * bar)
            if ta is None:
                continue
            self.hits[h].append(ta)
            self.hits[h].sort()
            hp[h] -= 1
            self.inv[h].append((ta, ta + INV_HIT))
            if hp[h] <= 0:
                dn = kill(h, ta)
                plan = rev[h][n_dead[h]] if n_dead[h] < len(rev[h]) else False
                n_dead[h] += 1
                if plan and try_revive(dn, other):
                    hp[h] = 1
        # a lost take must end with both heroes down: finish off whoever is still standing
        if not tk.won:
            for _ in range(8):
                standing = [h for h in (0, 1) if self.is_alive(h, tk.end - 0.6 * bar)]
                if not standing:
                    break
                h = standing[-1]
                t_try = tk.end - 1.0 * bar
                ta = place_hit(h, t_try, 8 * bar, lo=tk.go + 2.0, hi=tk.end - 0.4 * bar, final=True)
                if ta is None:
                    break
                self.hits[h].append(ta)
                self.hits[h].sort()
                hp[h] -= 1
                self.inv[h].append((ta, ta + INV_HIT))
                if hp[h] <= 0:
                    kill(h, ta)
        # ---- pinks, dodges and misses for the rest of the slots
        p_dodge = 0.35
        for sl in slots:
            if sl["used"]:
                continue
            sl["used"] = True
            ts, kind = sl["ts"], sl["kind"]
            if kind == "ring":
                s = Shot(ts, "ring", self.ex, self.ey, -900.0, 0.0, False, 1.0, sl["seed"], 1.6)
                s.role = "ring"
                self.shots.append(s)
                continue
            if sl["pink"] and self._place_pink(sl, tk):
                continue
            if kind != "rain" and kind != "arc" and h01(self.seed, "dodge", ts) < p_dodge and self._place_dodge(sl, tk):
                continue
            self._place_miss(sl, tk)
        self._plan_bullets(tk)
        self._plan_cards(tk)

    def _run_ok(self, h: int, run: Run) -> bool:
        for s in self._shots_between(run.t0, run.t3):
            if s.role == "ring":
                continue
            c = self._contact(s, h)
            if c is not None and not (s.who == h and s.role in ("hit", "parry") and abs(c - s.arrive) < 0.05):
                return False
        return True

    def _hero_free(self, h: int, t: float, before=0.6, after=0.45) -> bool:
        return (self.is_alive(h, t - before) and self.is_alive(h, t + after) and not self._busy(h, t - before, t + after)
                and not self._jumping(h, t - before, t + after)
                and not any(t - before - 0.3 <= th <= t + after for th in self.hits[h]))

    def _place_pink(self, sl, tk) -> bool:
        order = (0, 1) if h01(self.seed, "ph", sl["ts"]) < 0.5 else (1, 0)
        kind = sl["kind"] if sl["kind"] in ("aimed", "wave", "arc") else "aimed"
        for h in order:
            for n in self._n_for(kind, sl["ts"], 600, 600, pink=True):
                ta = self._arrival(sl["ts"], n)
                if ta > tk.end - 0.5 * self.bar or not self._hero_free(h, ta, 0.7, 0.4):
                    continue
                x, y, _ = self.pos(h, [ta])
                apex = 150.0
                ty = float(y[0]) - apex - (140 if not self.sky else -5)
                j = Jump(ta - 0.3, 0.6, apex, True, "parry")
                self.jumps[h].append(j)
                self.jumps[h].sort(key=lambda q: q.t0)
                s = self._aim_edge(kind, sl["ts"], n, float(x[0]), ty, sl["seed"], h, ta, pink=True)
                ok = s is not None and self._clear(s, ta, ignore=h)
                self.jumps[h].remove(j)
                if not ok:
                    continue
                s.who, s.role, s.end = h, "parry", "parry"
                ty = float(self.shot_xy(s, ta - s.ts)[1])
                self.shots.append(s)
                if not self._add_jump(h, j, skip=s):
                    self.shots.remove(s)
                    continue
                self.parries.append((ta, h, float(x[0]), ty, "shot"))
                return True
        return False

    def _place_dodge(self, sl, tk) -> bool:
        kind = sl["kind"] if sl["kind"] in ("aimed", "wave") else "aimed"
        order = (0, 1) if h01(self.seed, "dh", sl["ts"]) < 0.5 else (1, 0)
        for h in order:
            for n in self._n_for(kind, sl["ts"], 600, 800):
                ta = self._arrival(sl["ts"], n)
                if ta > tk.end - 0.3 * self.bar or not self._hero_free(h, ta, 0.55, 0.45):
                    continue
                x, y, _ = self.pos(h, [ta])
                ty = float(y[0]) - (50 if not self.sky else -5)
                s = self._aim(kind, sl["ts"], n, float(x[0]), ty, sl["seed"])
                s.who, s.role = h, "dodge"
                if not (-200 < s.y0 < 1300):
                    continue
                s.life = self._life(s)
                j = Jump(ta - 0.3, 0.6, 175.0, False, "dodge")
                self.jumps[h].append(j)
                self.jumps[h].sort(key=lambda q: q.t0)
                ok = self._clear(s)
                self.jumps[h].remove(j)
                if not ok:
                    continue
                self.shots.append(s)
                if not self._add_jump(h, j, skip=s):
                    self.shots.remove(s)
                    continue
                return True
        return False

    def _place_miss(self, sl, tk):
        ts, kind, seed = sl["ts"], sl["kind"], sl["seed"]
        spread = kind == "spread"
        if spread:
            kind = "aimed"
        tries = []
        x0, _, _ = self.pos(0, [ts + 1.0])
        x1, _, _ = self.pos(1, [ts + 1.0])
        lo_x, hi_x = sorted((float(x0[0]), float(x1[0])))
        r = h01(self.seed, "miss", ts)
        if self.sky:
            for k in range(12):
                yy = 120 + ((k * 0.37 + r) % 1.0) * 860
                tries.append((kind if kind != "arc" else "aimed", -150.0, yy))
        elif kind == "rain":
            for k in range(6):
                xx = 60 + ((k * 0.41 + r) % 1.0) * 1150
                tries.append(("rain", xx, self.ground - 10))
        elif kind == "arc":
            for k in range(5):
                xx = hi_x + 170 + ((k * 0.3 + r) % 1.0) * max(60.0, self.ex - hi_x - 320)
                tries.append(("arc", xx, self.ground - 10))
            if hi_x - lo_x > 330:
                tries.append(("arc", (lo_x + hi_x) / 2, self.ground - 10))
        else:
            for k in range(4):
                tries.append((kind, -150.0, self.ground - 470 - 120 * ((k * 0.29 + r) % 1.0)))
            tries.append((kind, hi_x + 190 + 0.5 * max(0.0, self.ex - hi_x - 400), self.ground - 10))
        for kd, tx, ty in tries:
            n = self._n_for(kd, ts, tx, ty)[0]
            s = self._aim(kd, ts, n, tx, ty, seed)
            if kd != "rain" and not (-300 < s.y0 < 1400):
                continue
            s.role = "miss"
            s.life = self._life(s)
            if self._clear(s):
                self.shots.append(s)
                if spread:
                    self._spread_sides(s)
                return True
        return False

    def _spread_sides(self, s: Shot):
        ang = math.atan2(s.vy, s.vx)
        sp = math.hypot(s.vx, s.vy)
        for k in (-1, 1):
            a2 = ang + k * 0.22
            q = Shot(s.ts, "aimed", s.x0, s.y0, math.cos(a2) * sp, math.sin(a2) * sp, False, 1.0,
                     h01(s.seed, k), 3.0)
            q.role = "side"
            q.life = self._life(q)
            if self._clear(q):
                self.shots.append(q)

    # ================================================================ heroes' attacks and super cards
    def _plan_bullets(self, tk: story.Take):
        m = self.m
        for k in range(len(m.beats) - 1):
            tb = float(m.beats[k])
            if not (tk.go <= tb < tk.end) or any(i.t0 <= tb < i.t1 for i in self.inters):
                continue
            hi = m.beat_high[k]
            if hi < 0.25:
                continue
            sub = 4 if hi > 0.6 else 2
            dt = (m.beats[k + 1] - tb) / sub
            for j in range(sub):
                for h in (0, 1):
                    if j % 2 == h or sub == 2:
                        t = tb + j * dt + h * 0.012
                        if self.is_alive(h, t) and not any(0 <= t - th < 0.35 for th in self.hits[h]) \
                                and not self._busy(h, t - 0.05, t + 0.05):
                            self.bullets.append((t, h))

    def _plan_cards(self, tk: story.Take):
        """Super meters for this take: bullets that land and parries fill them; EX shots spend a card on
        strong downbeats; a full hand on a drop becomes a Super Art (both heroes can go at once)."""
        m = self.m
        bar = self.bar
        drops = sorted(m.snap_bar(d.t0) for d in m.st.drops)
        drops = [t for t in drops if tk.go + bar < t < tk.end - 2.5 * bar
                 and not any(i.t0 - bar <= t < i.t1 for i in self.inters)]
        exc = []
        for bk in range(m.bar_at(tk.go + 0.05) + 2, m.bar_at(tk.end - 0.05) - 1):
            t = m.bar_time(bk)
            if any(i.t0 - bar <= t < i.t1 for i in self.inters):
                continue
            en = float(m.st.bar_energy[min(bk, len(m.st.bar_energy) - 1)]) if len(m.st.bar_energy) else 0.5
            if en > 0.4:
                exc.append((t, bk))
        for h in (0, 1):
            ev = [(t, "b") for t, hh in self.bullets if hh == h and tk.go <= t < tk.end]
            ev += [(p[0], "p", p) for p in self.parries if p[1] == h and tk.go <= p[0] < tk.end]
            ev += [(t, "x", bk) for t, bk in exc if h01(self.seed, "ex", h, bk) < 0.2]
            ev += [(t, "s") for t in drops]
            ev.sort(key=lambda e: (e[0], {"b": 0, "p": 1, "s": 2, "x": 3}[e[1]]))
            mv = 0.0
            mt, vv = self.meter_t[h], self.meter_v[h]
            mt.append(tk.go)
            vv.append(0.0)
            last_ex = -1e9
            supers = []
            for e in ev:
                t, kind = e[0], e[1]
                if any(s0 <= t < s0 + self.super_dur for s0 in supers):
                    continue
                if kind == "b":
                    mv = min(5.0, mv + BULLET_CARD)
                elif kind == "p":
                    if e[2] not in self.parries:      # given up to make room for a Super Art
                        continue
                    mv = min(5.0, mv + 1.0)
                elif kind == "s":
                    if mv >= 5.0 - 1e-9 and self._super_free(h, t):
                        supers.append(t)
                        self.super_by.append((t, h))
                        if t not in self.supers:
                            self.supers.append(t)
                        mv = 0.0
                        self._clear_for_super(h, t)
                    else:
                        continue
                elif kind == "x":
                    nxt = next((d for d in drops if d > t), 1e18)
                    if mv < 1.0 or t - last_ex < 3 * bar or (mv >= 4.0 and nxt - t < 16.0):
                        continue
                    if not self._hero_free(h, t, 0.3, 0.5) or any(abs(t - s0) < bar for s0 in supers):
                        continue
                    mv -= 1.0
                    last_ex = t
                    self.exs.append((t, h))
                    self.busy[h].append((t - 0.05, t + 0.35))
                mt.append(t)
                vv.append(mv)
            mt.append(tk.end)
            vv.append(mv)
        self.supers.sort()
        self.super_by.sort()
        self.exs.sort()
        # no bullets from a hero while they perform a Super Art or fire an EX
        self.bullets = [(t, h) for t, h in self.bullets
                        if not any(s0 <= t < s0 + self.super_dur for s0, hh in self.super_by if hh == h)
                        and not any(0 <= t - te < 0.3 for te, hh in self.exs if hh == h)]

    def _super_free(self, h: int, t: float) -> bool:
        t1 = t + self.super_dur
        return (self.is_alive(h, t) and self.is_alive(h, t1) and not any(t - 0.3 <= th <= t1 for th in self.hits[h])
                and not self._busy(h, t - 0.3, t1))

    def _clear_for_super(self, h: int, t: float):
        """A hero mid-Super can't hop or parry: their pink and dodge shots in that window go overhead."""
        t1 = t + self.super_dur
        self.busy[h].append((t, t1))
        for j in [j for j in self.jumps[h] if j.t0 < t1 and t - 0.3 < j.t0 + j.dur and j.kind in ("parry", "dodge")]:
            self.jumps[h].remove(j)
            for s in [s for s in self.shots if s.who == h and abs(s.arrive - (j.t0 + 0.3)) < 0.02 and s.role in ("parry", "dodge")]:
                self.shots.remove(s)
                self.parries = [p for p in self.parries if not (p[1] == h and abs(p[0] - s.arrive) < 0.02)]
                sl = {"ts": s.ts, "kind": s.kind, "seed": s.seed}
                self._place_miss(sl, None)

    # ================================================================ eggs that the heroes join in
    def egg_hops(self, P: story.Plan):
        """The bowling ball and the banana peel: heroes hop the ball and slip on the peel. These are
        reserved first, so shots plan around them."""
        a = self.a
        for g in P.eggs:
            if not (a.go <= g.t0 < a.ko) or self.sky:
                continue
            if g.kind == "bowling":
                for h in (0, 1):
                    tx = self.egg_ball_time(g, h)
                    if tx is not None:
                        self.jumps[h].append(Jump(tx - 0.28, 0.56, 150.0, False, "egg"))
                        self.busy[h].append((tx - 0.6, tx + 0.5))
            elif g.kind == "banana":
                h = 0 if g.seed < 0.5 else 1
                t = g.t0 + 0.45 * (g.t1 - g.t0)
                self.jumps[h].append(Jump(t, 0.9, 60.0, False, "slip"))
                self.busy[h].append((t - 0.5, t + 1.6))
            elif g.kind == "qblock":
                h = 0 if g.seed < 0.5 else 1
                t = g.t0 + 0.5 * (g.t1 - g.t0)
                self.jumps[h].append(Jump(t - 0.3, 0.6, 200.0, False, "egg"))
                self.busy[h].append((t - 0.8, t + 0.6))
        for js in self.jumps:
            js.sort(key=lambda j: j.t0)

    def egg_ball_x(self, g, t: float) -> float:
        u = (t - g.t0) / (g.t1 - g.t0)
        return 2050 - 2300 * u if g.side > 0 else -130 + 2300 * u

    def egg_ball_time(self, g, h: int):
        for k in range(1, 400):
            t = g.t0 + k * (g.t1 - g.t0) / 400
            x, _, _ = self.pos(h, [t])
            if abs(self.egg_ball_x(g, t) - x[0]) < 25:
                return t
        return None

    # ================================================================ checks
    def _validate(self):
        """Count shots that touch a hero they weren't meant to (should be none)."""
        bad = 0
        for s in self.shots:
            if s.role == "ring":
                continue
            for h in (0, 1):
                c = self._contact(s, h)
                if c is None:
                    continue
                if s.who == h and s.role in ("hit", "parry") and abs(c - s.arrive) < 0.15:
                    continue
                bad += 1
        self.anomalies = bad

    # ================================================================ queries for drawing
    def ghost_xy(self, dn: Down, t: float):
        dt = t - dn.t
        x = dn.x + 26 * math.sin(2.6 * dt)
        y = dn.y - (GHOST_Y0 if not self.sky else 60) - GHOST_RISE * dt
        return x, y

    def hero_xy(self, h: int, t: float):
        x, y, lf = self.pos(h, [t])
        _, _, moving, dirx = self.base(h, [t])
        mv = bool(moving[0])
        dx = float(dirx[0])
        for r in self.runs[h]:
            if r.t0 <= t < r.t1:
                mv, dx = True, (1.0 if r.x > float(self.base(h, [r.t0])[0][0]) else -1.0)
        return float(x[0]), float(y[0]), mv, dx

    def jump_at(self, h: int, t: float):
        for j in self.jumps[h]:
            if j.t0 <= t < j.t0 + j.dur:
                u = (t - j.t0) / j.dur
                return 4 * j.height * u * (1 - u), j, u
            if j.t0 > t:
                break
        return 0.0, None, 0.0

    def down_at(self, h: int, t: float):
        """The death this hero is in at t (None if alive)."""
        for dn in self.downs:
            if dn.h == h and dn.t <= t:
                end = dn.revive + 0.25 if dn.revive is not None else self._take_end(dn.t)
                if t < end:
                    return dn
        return None

    def hp(self, h: int, t: float) -> int:
        tk = story.take_at(self.a, t)
        n = HP
        evs = [(th, -1) for th in self.hits[h] if tk.t0 <= th <= t]
        evs += [(r[0] + 0.25, 0) for r in self.revives if r[2] == h and tk.t0 <= r[0] + 0.25 <= t]
        for te, kind in sorted(evs):
            n = n - 1 if kind < 0 else 1
        return max(0, n)

    def last_hit(self, h: int, t: float):
        k = bisect.bisect_right(self.hits[h], t)
        return self.hits[h][k - 1] if k else None

    def meter(self, h: int, t: float) -> float:
        mt = self.meter_t[h]
        if not mt:
            return 0.0
        k = bisect.bisect_right(mt, t) - 1
        return float(self.meter_v[h][k]) if k >= 0 else 0.0

    def active_shots(self, t: float):
        if not len(self._st):
            return []
        i1 = int(np.searchsorted(self._st, t, side="right"))
        i0 = int(np.searchsorted(self._st, t - 6.0))
        return [s for s in self.shots[i0:i1] if t - s.ts < s.life + (0.18 if s.end in ("hit", "parry", "floor") else 0)]

    def active_bullets(self, t: float, travel: float = 0.42):
        if not len(self._bt):
            return []
        i1 = int(np.searchsorted(self._bt, t, side="right"))
        i0 = int(np.searchsorted(self._bt, t - travel - 0.15))
        return self.bullets[i0:i1]

    def super_at(self, t: float):
        for s in self.supers:
            if s <= t < s + self.super_dur:
                return s
        return None

    def supers_at(self, t: float):
        return [(s, h) for s, h in self.super_by if s <= t < s + self.super_dur]

    def ex_at(self, t: float):
        """EX shots in flight or landing: (fire time, hero, progress 0..1.6)."""
        p = self.m.period
        return [(te, h, (t - te) / p) for te, h in self.exs if 0 <= t - te < 1.6 * p]

    def dmg(self, t: float) -> float:
        """How beaten-up the boss looks, 0 (fresh) .. 1 (knocked out), for the take at t."""
        tk = story.take_at(self.a, t)
        if t < tk.go:
            return 0.0
        if tk.won and t >= tk.end:
            return 1.0
        f = story.fight_time(tk.go, min(t, tk.end), self.inters)
        return float(min(1.0, f / max(3 * self.a.phase_len, 1e-3)))

    def laugh(self, t: float) -> float:
        """The boss laughs after it downs a hero, and all the way to the TAKE card when both are down."""
        best = 0.0
        for dn in self.downs:
            d = t - dn.t
            if 0.15 <= d < 1.5 * self.bar:
                best = max(best, 1.0)
        tk = story.take_at(self.a, t)
        if not tk.won and t < tk.end and not self.is_alive(0, t) and not self.is_alive(1, t):
            best = 1.0
        return best

    def cards_at(self, t: float) -> int:
        """Whole super cards of the first hero (kept for older callers)."""
        return int(self.meter(0, t))
