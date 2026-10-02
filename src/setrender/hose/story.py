"""The cartoon's running order, worked out once from the music of the whole set:

* an opening title card and a closing "THE END"
* acts of about ten minutes, each a boss fight cut at section boundaries; the fight has three
  phases, opens with READY? / GO! and ends in a KNOCKOUT and an iris-out on a downbeat
* long breakdowns become intermissions (bouncing-ball sing-along, the overworld map, a vaudeville
  number), builds wind the boss up and drops land with an exclamation and a super attack
* every shot, jump, parry and super is scheduled from beats, onsets and band energy, so any frame
  can be drawn on its own (frames are pure functions of their index)
* sound-classifier events (Neural Engine) and a few bar numbers trigger gags
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

import numpy as np

from ..analysis import Analysis

EXCLAIM = ["WHAM!", "HOT DOG!", "ZOWIE!", "OH BOY!", "BOP!", "WHOOPEE!", "SWELL!", "YOWZA!", "BOING!",
           "HOT DIGGITY!", "JEEPERS!", "KAPOW!"]
GO_WORDS = ["GO!", "GO!", "LET'S GO!", "HOP TO IT!", "GO!"]

# classifier label -> gag, minimum confidence
GAG_SOUNDS = {
    "saxophone": "horn", "trumpet": "horn", "brass_instrument": "horn", "trombone": "horn",
    "telephone": "phone", "ringtone": "phone", "telephone_bell_ringing": "phone",
    "cat_meow": "cat", "cat": "cat",
    "marimba_xylophone": "skeleton", "glockenspiel": "skeleton", "mallet_percussion": "skeleton",
    "theremin": "ghost", "foghorn": "steamboat", "boat_water_vehicle": "steamboat",
    "frog_croak": "frog", "frog": "frog", "baby_crying": "stork", "crying_sobbing": "stork",
    "piano": "piano", "electric_piano": "piano", "violin_fiddle": "fiddle", "banjo": "fiddle",
    "gong": "gong", "chicken": "chicken", "rooster_crow": "chicken", "disc_scratching": "scratch",
    "laughter": "laugh", "cheering": "audience", "applause": "audience", "crowd": "audience",
    "singing": "singalong", "whistling": "bird",
}
GAG_COOLDOWN = {"scratch": 240.0, "singalong": 180.0, "audience": 120.0, "piano": 150.0, "horn": 75.0}


def h01(*a) -> float:
    """Deterministic hash of anything to [0, 1)."""
    s = hashlib.blake2b(repr(a).encode(), digest_size=8).digest()
    return int.from_bytes(s, "little") / 2 ** 64


@dataclass
class Act:
    k: int
    t0: float
    t1: float
    boss: str
    stage: str
    sky: bool
    phases: list[float]
    go: float
    ko: float
    variant: int = 0
    go_word: str = "GO!"


@dataclass
class Inter:
    t0: float
    t1: float
    kind: str          # singalong | map | vaudeville
    act: int


@dataclass
class Card:
    t0: float
    t1: float
    text: str
    kind: str          # ready | go | ko | word | inter


@dataclass
class Gag:
    kind: str
    t0: float
    t1: float
    side: float        # -1 left, +1 right
    seed: float
    label: str = ""


@dataclass
class Shot:            # a boss projectile
    ts: float
    kind: str          # aimed | arc | wave | spread | rain | ring
    x0: float
    y0: float
    vx: float
    vy: float
    pink: bool
    size: float
    seed: float
    life: float
    end: str = "off"   # off | parry


@dataclass
class Jump:
    t0: float
    dur: float
    height: float
    parry: bool


@dataclass
class Plan:
    acts: list[Act] = field(default_factory=list)
    inters: list[Inter] = field(default_factory=list)
    cards: list[Card] = field(default_factory=list)
    gags: list[Gag] = field(default_factory=list)


class Music:
    """Fast per-time queries on the whole set's analysis."""

    def __init__(self, an: Analysis, st):
        self.an, self.st = an, st
        self.beats = an.beats if len(an.beats) > 4 else np.arange(0, an.duration, 60 / max(an.tempo, 60))
        self.db = st.downbeats
        self.dur = an.duration
        self.period = 60.0 / max(an.tempo, 60)
        # per-beat band energy at the beat (used to schedule shots)
        b = self.beats
        self.beat_high = an.at(an.bands.get("high", an.loudness), b + 0.06)
        self.beat_hmid = an.at(an.bands.get("highmid", an.loudness), b + 0.06)
        self.beat_sub = an.at(an.bands.get("sub", an.loudness), b + 0.03)
        self.beat_loud = an.at(an.loudness, b + 0.1)

    def beat_pos(self, t: float) -> float:
        b = self.beats
        k = int(np.searchsorted(b, t, side="right") - 1)
        if k < 0:
            return (t - b[0]) / self.period
        if k >= len(b) - 1:
            return k + (t - b[-1]) / self.period
        return k + (t - b[k]) / max(b[k + 1] - b[k], 1e-3)

    def beat_time(self, k: float) -> float:
        b = self.beats
        i = int(math.floor(k))
        f = k - i
        if i < 0:
            return b[0] + k * self.period
        if i >= len(b) - 1:
            return b[-1] + (k - len(b) + 1) * self.period
        return b[i] + f * (b[i + 1] - b[i])

    def bar_at(self, t: float) -> int:
        return int(max(0, np.searchsorted(self.db, t, side="right") - 1))

    def bar_pos(self, t: float) -> float:
        db = self.db
        k = self.bar_at(t)
        if k >= len(db) - 1:
            return k + (t - db[-1]) / (4 * self.period)
        return k + (t - db[k]) / max(db[k + 1] - db[k], 1e-3)

    def bar_time(self, k: int) -> float:
        db = self.db
        if k < 0:
            return db[0] + k * 4 * self.period
        if k >= len(db):
            return db[-1] + (k - len(db) + 1) * 4 * self.period
        return float(db[k])

    def snap_bar(self, t: float) -> float:
        db = self.db
        k = int(np.clip(np.searchsorted(db, t), 1, len(db) - 1))
        return float(db[k] if abs(db[k] - t) < abs(db[k - 1] - t) else db[k - 1])

    def band(self, name: str, t: float) -> float:
        return float(self.an.at(self.an.bands.get(name, self.an.loudness), t))

    def loud(self, t: float) -> float:
        return float(self.an.at(self.an.loudness, t))


# ---------------------------------------------------------------- the running order

def plan(m: Music, st, rng: np.random.Generator, roster: list[dict], cfg: dict, sounds=None) -> Plan:
    dur = m.dur
    P = Plan()
    bar = 4 * m.period
    intro_end = m.snap_bar(min(max(12.0, 6 * bar), dur * 0.2))
    outro0 = m.snap_bar(max(intro_end + bar, dur - max(14.0, 8 * bar))) if dur > 60 else dur
    P.intro = (0.0, intro_end)
    P.outro = (outro0, dur)

    # ---- acts: about act_len seconds each, cut at the section starts nearest the ideal points
    act_len = float(cfg.get("act_minutes", 10)) * 60
    core = outro0 - intro_end
    n_acts = max(1, int(round(core / act_len)))
    secs = np.array([s for s in m.an.sections if intro_end + bar * 8 < s < outro0 - bar * 8])
    drops = np.array([d.t0 for d in st.drops])
    cuts = [intro_end]
    for k in range(1, n_acts):
        ideal = intro_end + core * k / n_acts
        best, score = m.snap_bar(ideal), 1e9
        for s in secs:
            if abs(s - ideal) > act_len * 0.3 or s - cuts[-1] < act_len * 0.5:
                continue
            sc = abs(s - ideal) / act_len - (0.25 if len(drops) and np.min(np.abs(drops - s)) < 4 else 0.0)
            if sc < score:
                best, score = m.snap_bar(s), sc
        cuts.append(best)
    cuts.append(outro0)
    order = list(range(len(roster)))
    rng.shuffle(order)
    # don't start with a sky stage: the first fight should show the heroes on their feet
    if roster[order[0]]["sky"] and len(order) > 1:
        j = next((j for j in range(1, len(order)) if not roster[order[j]]["sky"]), 0)
        order[0], order[j] = order[j], order[0]
    for k in range(n_acts):
        t0, t1 = cuts[k], cuts[k + 1]
        b = roster[order[k % len(order)]]
        go = m.bar_time(m.bar_at(t0 + 0.05) + 2)
        ko = m.bar_time(max(m.bar_at(t1 - 0.05) - 3, m.bar_at(go) + 2))
        P.acts.append(Act(k, t0, t1, b["name"], b["stage"], b["sky"], [], go, ko, variant=k // len(order),
                          go_word=GO_WORDS[int(h01("go", k, rng.integers(1 << 30)) * len(GO_WORDS))]))

    # ---- intermissions from long breakdowns (not over READY/GO or the KNOCKOUT)
    kinds = ["singalong", "map", "vaudeville"]
    n_int = 0
    for bd in st.breakdowns:
        t0, t1 = m.snap_bar(bd.t0), m.snap_bar(bd.t1)
        if t1 - t0 < 15 * bar or t0 < intro_end or t1 > outro0:
            continue
        a = next((a for a in P.acts if a.t0 <= t0 < a.t1), None)
        if a is None or t0 < a.go + 2 * bar or t1 > a.ko - 2 * bar:
            continue
        if sum(1 for i in P.inters if i.act == a.k) >= 2:
            continue
        kind = kinds[(n_int + int(h01("int", a.k) * 3)) % 3]
        P.inters.append(Inter(t0, t1, kind, a.k))
        n_int += 1

    # ---- phases: three, split at the bars nearest a third and two thirds of the fighting time
    for a in P.acts:
        fight = [(a.go, a.ko)]
        for it in (i for i in P.inters if i.act == a.k):
            fight = [seg for (f0, f1) in fight for seg in ((f0, it.t0), (it.t1, f1)) if seg[1] - seg[0] > 0]
        total = sum(f1 - f0 for f0, f1 in fight)
        marks = []
        for frac in (1 / 3, 2 / 3):
            acc, target = 0.0, total * frac
            for f0, f1 in fight:
                if acc + (f1 - f0) >= target:
                    marks.append(m.snap_bar(f0 + target - acc))
                    break
                acc += f1 - f0
        a.phases = [a.go] + sorted(marks)

    # ---- lettering cards
    for a in P.acts:
        P.cards.append(Card(a.t0 + 0.5 * bar, a.go, "READY?", "ready"))
        P.cards.append(Card(a.go, a.go + bar, a.go_word, "go"))
        P.cards.append(Card(a.ko, a.ko + 2.2 * bar, "KNOCKOUT!", "ko"))
    for it in P.inters:
        if it.kind == "singalong":
            P.cards.append(Card(it.t0 + bar * 0.5, it.t0 + bar * 2.5, "FOLLOW THE BOUNCING BALL!", "inter"))
        elif it.kind == "vaudeville":
            P.cards.append(Card(it.t0 + bar * 0.5, it.t0 + bar * 2.5, "INTERMISSION", "inter"))
        P.cards.append(Card(it.t1, it.t1 + bar, "GO!", "go"))
    ex = 0
    for d in st.drops:
        t = m.snap_bar(d.t0)
        if t < intro_end or t > outro0 - bar * 2:
            continue
        if any(abs(c.t0 - t) < bar * 3 for c in P.cards):
            continue
        a = next((a for a in P.acts if a.go < t < a.ko), None)
        if a is None or any(i.t0 - bar <= t < i.t1 + bar for i in P.inters):
            continue
        P.cards.append(Card(t, t + bar, EXCLAIM[int(h01("ex", ex, t) * len(EXCLAIM))], "word"))
        ex += 1
    P.cards.sort(key=lambda c: c.t0)

    # ---- gags from the sound classifier, plus a few bar-number easter eggs
    last = {}
    for s in (sounds or []):
        g = GAG_SOUNDS.get(s.label)
        if g is None or s.peak < 0.6:
            continue
        t0 = s.t0 + 1.5
        if t0 < intro_end + bar * 2 or t0 > outro0 - bar * 4:
            continue
        if t0 - last.get(g, -1e9) < GAG_COOLDOWN.get(g, 45.0):
            continue
        if any(c.kind in ("ko", "ready") and c.t0 - 2 < t0 < c.t1 + 2 for c in P.cards):
            continue
        busy = [x for x in P.gags if x.t0 < t0 + 6 and x.t1 > t0]
        if len(busy) >= 2:
            continue
        last[g] = t0
        side = -1.0 if h01("side", g, t0) < 0.5 else 1.0
        dur_g = {"singalong": 0.0, "scratch": 4 * bar, "audience": 6.0, "steamboat": 10.0, "stork": 8.0,
                 "skeleton": 8 * bar, "ghost": 8.0}.get(g, 6.0)
        if g == "singalong":
            dur_g = min(max(s.t1 - s.t0, 6.0), 16.0)
        P.gags.append(Gag(g, t0, t0 + dur_g, side, h01("gag", g, t0), s.label))
    for bar_no, g in ((404, "burn"), (1928, "steamboat"), (1929, "skeleton"), (1337, "ghost")):
        if bar_no < len(m.db) - 8:
            t0 = m.bar_time(bar_no)
            if intro_end < t0 < outro0 - 8 * bar:
                P.gags.append(Gag(g, t0, t0 + (2.0 if g == "burn" else 8 * bar), 1.0, h01("egg", bar_no),
                                  f"bar {bar_no}"))
    P.gags.sort(key=lambda g: g.t0)
    return P


def fighting(P: Plan, t: float):
    """The act being fought at t (None during title cards, intermissions and the end card)."""
    if t < P.intro[1] or t >= P.outro[0]:
        return None
    for it in P.inters:
        if it.t0 <= t < it.t1:
            return None
    for a in P.acts:
        if a.t0 <= t < a.t1:
            return a
    return None


def act_at(P: Plan, t: float):
    for a in P.acts:
        if a.t0 <= t < a.t1:
            return a
    return P.acts[-1] if t >= P.acts[-1].t0 else P.acts[0]


def inter_at(P: Plan, t: float):
    for it in P.inters:
        if it.t0 <= t < it.t1:
            return it
    return None


def phase_of(a: Act, t: float) -> int:
    return int(np.searchsorted(a.phases, t, side="right") - 1) if a.phases else 0


# ---------------------------------------------------------------- fight choreography

class Fight:
    """Shots, jumps, parries and supers for one act, all scheduled up front."""

    def __init__(self, m: Music, P: Plan, a: Act, boss_info: dict, seed: int, cfg: dict):
        self.m, self.a = m, a
        self.seed = seed
        bar = 4 * m.period
        self.sky = a.sky
        self.ground = 905.0
        ex, ey = boss_info["emit"]
        pats = boss_info["patterns"]
        rate = float(cfg.get("attack_rate", 1.0))
        shots: list[Shot] = []
        bars = range(m.bar_at(a.go + 0.05) + 1, m.bar_at(a.ko - 0.05))
        inters = [i for i in P.inters if i.act == a.k]
        n_pink = 0
        for bk in bars:
            tb = m.bar_time(bk)
            if any(i.t0 - bar <= tb < i.t1 for i in inters):
                continue
            ph = phase_of(a, tb)
            kick = bool(m.st.bar_kick[min(bk, len(m.st.bar_kick) - 1)]) if len(m.st.bar_kick) else True
            if not kick:
                continue
            energy = float(m.st.bar_energy[min(bk, len(m.st.bar_energy) - 1)])
            per_bar = [1, 2, 4][ph] if energy > 0.35 else [1, 1, 2][ph]
            per_bar = max(1, int(round(per_bar * rate)))
            for j in range(per_bar):
                beat = j * 4 // per_bar
                ts = m.beat_time(m.beat_pos(tb) + beat)
                r = h01(seed, bk, j)
                kinds = pats[min(ph, len(pats) - 1)]
                kind = kinds[int(r * len(kinds))]
                pink = (n_pink % 4 == 3)
                n_pink += 1
                tgt_x = 200 + 600 * h01(seed, bk, j, "x")
                tgt_y = self.ground - 140 if not self.sky else 300 + 450 * h01(seed, bk, j, "y")
                if kind == "spread":
                    for s_ in (-1, 0, 1):
                        ang = math.atan2(tgt_y - ey, tgt_x - ex) + s_ * 0.22
                        sp = 680.0
                        shots.append(Shot(ts, "aimed", ex, ey, math.cos(ang) * sp, math.sin(ang) * sp,
                                          pink and s_ == 0, 1.0, h01(seed, bk, j, s_), 3.5))
                    continue
                if kind == "arc":
                    T = 1.5 * m.period * 2
                    vx = (tgt_x - ex) / T
                    vy = (self.ground - 30 - ey - 0.5 * 1400 * T * T) / T
                    shots.append(Shot(ts, "arc", ex, ey, vx, vy, pink, 1.1, r, T + 0.6))
                elif kind == "rain":
                    x = tgt_x + (h01(seed, bk, j, "rx") - 0.5) * 300
                    shots.append(Shot(ts, "rain", x, -60, -40.0, 520.0, pink, 1.0, r, 2.6))
                elif kind == "wave":
                    shots.append(Shot(ts, "wave", ex, tgt_y - 40, -520.0, 0.0, pink, 1.0, r, 3.6))
                elif kind == "ring":
                    shots.append(Shot(ts, "ring", ex, ey, -900.0, 0.0, False, 1.0, r, 1.6))
                else:
                    ang = math.atan2(tgt_y - ey, tgt_x - ex)
                    sp = 640.0 + 120 * ph
                    shots.append(Shot(ts, "aimed", ex, ey, math.cos(ang) * sp, math.sin(ang) * sp, pink, 1.0, r, 3.4))
        self.shots = shots

        # hero jumps: parry each pink shot when it reaches its target, plus hops on snares
        self.jumps: list[list[Jump]] = [[], []]
        self.parries: list[float] = []
        for s in shots:
            if not s.pink:
                continue
            h = 0 if h01(s.seed, "who") < 0.5 else 1
            # time the shot reaches the hero's area
            hx = self.hero_xy(h, s.ts)[0]
            tt = self._arrival(s, hx)
            if tt is None:
                continue
            s.end, s.life = "parry", tt - s.ts
            self.jumps[h].append(Jump(s.ts + tt - 0.32, 0.55, 150.0, True))
            self.parries.append(s.ts + tt)
        self.parries.sort()
        for k in range(len(m.beats)):
            tb = m.beats[k]
            if not (a.go + bar <= tb < a.ko - bar) or any(i.t0 <= tb < i.t1 for i in inters):
                continue
            if k % 4 in (1, 3) and m.beat_hmid[k] > 0.62 and h01(seed, "hop", k) < 0.3:
                h = int(h01(seed, "hh", k) * 2)
                if not any(abs(j.t0 - tb) < 1.2 for j in self.jumps[h]):
                    self.jumps[h].append(Jump(tb, m.period * 1.6, 120.0 + 60 * h01(seed, k), False))
        for js in self.jumps:
            js.sort(key=lambda j: j.t0)

        # supers: on drops inside the fight, once the cards are charged
        self.supers = []
        cards = 0
        pi = 0
        for d in sorted(m.st.drops, key=lambda d: d.t0):
            t = m.snap_bar(d.t0)
            if not (a.go + bar < t < a.ko - bar) or any(i.t0 <= t < i.t1 for i in inters):
                continue
            while pi < len(self.parries) and self.parries[pi] < t:
                pi += 1
            if pi - cards >= 2 or not self.supers:
                self.supers.append(t)
                cards = pi
        self.super_dur = 2 * bar

        # hero bullets: 8ths or 16ths while the hats are busy
        self.bullets: list[tuple[float, int]] = []
        for k in range(len(m.beats) - 1):
            tb = m.beats[k]
            if not (a.go <= tb < a.ko) or any(i.t0 <= tb < i.t1 for i in inters):
                continue
            hi = m.beat_high[k]
            if hi < 0.25:
                continue
            sub = 4 if hi > 0.6 else 2
            dt = (m.beats[k + 1] - tb) / sub
            for j in range(sub):
                for h in (0, 1):
                    if j % 2 == h or sub == 2:
                        self.bullets.append((tb + j * dt + h * 0.012, h))
        self.bullets.sort()
        self._bt = np.array([b[0] for b in self.bullets]) if self.bullets else np.zeros(0)
        self._st = np.array([s.ts for s in shots]) if shots else np.zeros(0)

    # ---- motion
    def _arrival(self, s: Shot, hx: float):
        for k in range(1, 90):
            tt = k * 0.04
            x, y = self.shot_xy(s, tt)
            if x <= hx + 40:
                return tt
        return None

    def shot_xy(self, s: Shot, tt: float):
        if s.kind == "arc":
            x = s.x0 + s.vx * tt
            y = s.y0 + s.vy * tt + 0.5 * 1400 * tt * tt
            T = 1.5 * self.m.period * 2
            if tt > T:     # bounces once along the floor
                y = min(y, self.ground - 30 - abs(math.sin((tt - T) * 6)) * 120 * math.exp(-(tt - T) * 2))
            return x, y
        if s.kind == "wave":
            return s.x0 + s.vx * tt, s.y0 + math.sin(tt * 7 + s.seed * 6) * 70
        return s.x0 + s.vx * tt, s.y0 + s.vy * tt

    def hero_xy(self, h: int, t: float):
        """Base position (feet for ground stages, plane centre for sky stages)."""
        m = self.m
        bk = m.bar_at(t)
        blk = bk // 2
        tb = m.bar_time(blk * 2)
        lo, hi = ((110, 470), (540, 900))[h]
        def tgt(j):
            return lo + (hi - lo) * h01(self.seed, "hx", h, j)
        u = min(1.0, max(0.0, (t - tb) / (m.period * 1.0)))
        e = u * u * (3 - 2 * u)
        x = tgt(blk - 1) + (tgt(blk) - tgt(blk - 1)) * e
        moving = 0.0 < u < 1.0 and abs(tgt(blk) - tgt(blk - 1)) > 30
        dirx = 1.0 if tgt(blk) >= tgt(blk - 1) else -1.0
        if self.sky:
            y = 260 + 420 * h01(self.seed, "hy", h, blk - 1)
            y2 = 260 + 420 * h01(self.seed, "hy", h, blk)
            y = y + (y2 - y) * e + math.sin(t * 2.1 + h * 2) * 26
            return x, y, moving, dirx
        return x, self.ground, moving, dirx

    def jump_at(self, h: int, t: float):
        for j in self.jumps[h]:
            if j.t0 <= t < j.t0 + j.dur:
                u = (t - j.t0) / j.dur
                return 4 * j.height * u * (1 - u), j, u
            if j.t0 > t:
                break
        return 0.0, None, 0.0

    def active_shots(self, t: float):
        if not len(self._st):
            return []
        i1 = int(np.searchsorted(self._st, t, side="right"))
        i0 = int(np.searchsorted(self._st, t - 4.0))
        return [s for s in self.shots[i0:i1] if t - s.ts < s.life]

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

    def cards_at(self, t: float) -> int:
        """Super meter cards (0..5): parries since the last super."""
        last = max([s for s in self.supers if s <= t], default=-1e9)
        n = sum(1 for p in self.parries if last <= p <= t)
        return min(5, n + 1)
