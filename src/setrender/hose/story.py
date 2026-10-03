"""The cartoon's running order, worked out once from the music of the whole set:

* an opening title card and a closing "THE END"
* one act per boss in the pool (so every boss is beaten exactly once), cut at section boundaries;
  an act is one or more takes of the fight: lost takes end when both heroes are down (a TAKE card,
  then the fight restarts from the top at a section change), and the last take is won, three phases
  in, with a KNOCKOUT and an iris-out on a downbeat
* long breakdowns become intermissions (bouncing-ball sing-along, the overworld map, a vaudeville
  number), builds wind the boss up and drops land with an exclamation and a super attack
* every shot, hit, jump, parry, revive and super is scheduled from beats, onsets and band energy
  (see combat.py), so any frame can be drawn on its own (frames are pure functions of their index)
* sound-classifier events (Neural Engine) and a few bar numbers trigger gags, and an easter egg
  turns up about once a minute
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
class Take:
    """One attempt at a boss fight."""
    n: int             # take number, 1 = the first attempt
    t0: float          # the stage irises open (READY? follows half a bar later)
    go: float
    end: float         # lost: the TAKE card slams in here; won: KNOCKOUT
    won: bool
    phases: list[float] = field(default_factory=list)


@dataclass
class Act:
    k: int
    t0: float
    t1: float
    boss: str
    stage: str
    sky: bool
    phases: list[float]  # the winning take's phases
    go: float            # the first take's GO
    ko: float
    variant: int = 0
    go_word: str = "GO!"
    takes: list[Take] = field(default_factory=list)
    phase_len: float = 0.0   # seconds of fighting per boss phase (the boss's stamina)


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
    kind: str          # ready | go | ko | word | inter | take


@dataclass
class Gag:
    kind: str
    t0: float
    t1: float
    side: float        # -1 left, +1 right
    seed: float
    label: str = ""


@dataclass
class Plan:
    acts: list[Act] = field(default_factory=list)
    inters: list[Inter] = field(default_factory=list)
    cards: list[Card] = field(default_factory=list)
    gags: list[Gag] = field(default_factory=list)
    eggs: list[Gag] = field(default_factory=list)


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
    P.period = m.period

    # ---- acts: about act_len seconds each, but no more acts than bosses in the pool unless the set is
    # very long (each boss is beaten exactly once); cut at the section starts nearest the ideal points
    act_len = float(cfg.get("act_minutes", 8)) * 60
    core = outro0 - intro_end
    n_acts = max(1, int(round(core / act_len)))
    if n_acts > len(roster) and core / len(roster) <= 2.2 * act_len:
        n_acts = len(roster)
    act_len = core / n_acts
    secs = np.array([s for s in m.an.sections if intro_end + bar * 8 < s < outro0 - bar * 8])
    drops = np.array([d.t0 for d in st.drops])
    cuts = [intro_end]
    for k in range(1, n_acts):
        ideal = intro_end + core * k / n_acts
        best, score = m.snap_bar(ideal), 1e9
        for s in secs:
            if abs(s - ideal) > act_len * 0.22 or s - cuts[-1] < act_len * 0.5:
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

    # ---- takes: most fights are lost a time or two first (a restart at a section change), the last
    # take is won; phases split the winning take's fighting time in three
    for a in P.acts:
        _plan_takes(m, a, [i for i in P.inters if i.act == a.k], cfg, rng)

    # ---- lettering cards
    for a in P.acts:
        for tk in a.takes:
            go_word = a.go_word if tk.n == 1 else GO_WORDS[int(h01("go", a.k, tk.n) * len(GO_WORDS))]
            P.cards.append(Card(tk.t0 + 0.5 * bar, tk.go, "READY?", "ready"))
            P.cards.append(Card(tk.go, tk.go + bar, go_word, "go"))
            if not tk.won:
                P.cards.append(Card(tk.end, tk.end + TAKE_CARD * bar, f"TAKE {tk.n + 1}", "take"))
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
        tk = take_at(a, t)
        if not (tk.go + bar < t < tk.end - 3 * bar):
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
        if any(c.kind in ("ko", "ready", "take") and c.t0 - 2 < t0 < c.t1 + 2 for c in P.cards):
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
    P.eggs = schedule_eggs(m, P, float(rng.random()))
    return P


TAKE_CARD = 2      # bars the TAKE card holds
TAKE_GAP = 4       # bars from a lost take's TAKE card to the next GO!


def fight_time(t0: float, t1: float, inters) -> float:
    """Seconds of fighting in [t0, t1), intermissions excluded."""
    s = t1 - t0
    for i in inters:
        s -= max(0.0, min(t1, i.t1) - max(t0, i.t0))
    return max(0.0, s)


def advance(t: float, secs: float, inters) -> float:
    """The time `secs` seconds of fighting after t (intermissions don't count)."""
    for i in sorted(inters, key=lambda i: i.t0):
        if i.t1 <= t:
            continue
        if t + secs <= i.t0:
            break
        if i.t0 > t:
            secs -= i.t0 - t
        t = i.t1
    return t + secs


def _plan_takes(m: Music, a: Act, inters, cfg: dict, rng):
    """Lost takes end at section starts (or short breakdowns) with the kick playing into them, away
    from intermissions; the winning take keeps at least ~40% of the act and is the longest."""
    bar = 4 * m.period
    total = fight_time(a.go, a.ko, inters)
    key = int(rng.integers(1 << 30))
    r = h01("takes", a.k, key)
    weights = cfg.get("retake_weights", [0.04, 0.3, 0.42, 0.24])   # P(0, 1, 2, 3 lost takes)
    nf, acc = 0, 0.0
    for k, w in enumerate(weights):
        acc += w / max(sum(weights), 1e-9)
        if r < acc:
            nf = k
            break
    kick = m.st.bar_kick

    def ok(F):
        if not (a.go + 12 * bar <= F <= a.ko - 20 * bar):
            return False
        if any(i.t0 - 4 * bar < F + (TAKE_GAP + 6) * bar and F - 6 * bar < i.t1 for i in inters):
            return False
        bk = m.bar_at(F + 0.05)
        return all(bool(kick[min(max(bk - j, 0), len(kick) - 1)]) for j in (1, 2, 3)) if len(kick) else True
    cands = sorted({m.snap_bar(s) for s in m.an.sections} | {m.snap_bar(b.t0) for b in m.st.breakdowns}
                   | {m.bar_time(k) for k in range(m.bar_at(a.go), m.bar_at(a.ko) + 1) if k % 16 == 0})   # phrase starts
    cands = [F for F in cands if ok(F)]
    fracs = {0: [], 1: [0.42], 2: [0.24, 0.47], 3: [0.16, 0.33, 0.5]}[min(nf, 3)]
    while True:
        fails = []
        for j, fr in enumerate(fracs):
            target = advance(a.go, total * (fr + (h01("tf", a.k, j, key) - 0.5) * 0.08), inters)
            lo = fails[-1] if fails else a.go
            go_prev = m.bar_time(m.bar_at(lo + 0.05) + TAKE_GAP) if fails else a.go
            pool = [F for F in cands if F > lo and fight_time(go_prev, F, inters) >= 45.0
                    and abs(F - target) < 0.18 * total]
            if pool:
                fails.append(min(pool, key=lambda F: abs(F - target)))
        gos = [a.go] + [m.bar_time(m.bar_at(F + 0.05) + TAKE_GAP) for F in fails]
        win = fight_time(gos[-1], a.ko, inters)
        lost = [fight_time(g, F, inters) for g, F in zip(gos, fails)]
        if not fails or (win >= max(0.33 * total, 150.0) and all(x < 0.88 * win for x in lost)):
            break
        fracs = fracs[:-1]
    a.phase_len = win / 3.0
    a.takes = []
    for n, (g, F) in enumerate(zip(gos, fails + [a.ko]), 1):
        t0 = a.t0 if n == 1 else m.bar_time(m.bar_at(fails[n - 2] + 0.05) + TAKE_CARD)
        tk = Take(n, t0, g, F, n == len(gos))
        tk.phases = [g]
        for j in (1, 2):
            tm = advance(g, j * a.phase_len, inters)
            if tm >= F - 2 * bar:
                break
            tm = m.snap_bar(tm)
            for i in inters:
                if i.t0 - 0.01 <= tm < i.t1:
                    tm = i.t1
            if tm - tk.phases[-1] >= 4 * bar and tm < F - 2 * bar:
                tk.phases.append(tm)
        a.takes.append(tk)
    a.phases = list(a.takes[-1].phases)


def take_at(a: Act, t: float) -> Take:
    tk = a.takes[0]
    for x in a.takes:
        if x.t0 <= t:
            tk = x
    return tk


# ---------------------------------------------------------------- easter eggs, about one a minute

# name: (seconds, where): any = also on title/intermission screens; fight = boss stages; ground = boss
# stages with a floor; sky = plane stages
EGGS = {
    "pie": (5.0, "fight"), "anvil": (4.5, "fight"), "pencil": (7.0, "fight"), "fly": (5.0, "any"),
    "shadow": (6.0, "any"), "slip": (2.4, "any"), "balloons": (8.0, "any"), "ufo": (8.0, "any"),
    "jelly": (8.0, "any"), "smiley": (6.0, "any"), "discoball": (8.0, "fight"), "cassette": (6.0, "any"),
    "invader": (7.0, "any"), "qblock": (5.0, "ground"), "pipe": (6.0, "ground"), "stagehand": (6.0, "ground"),
    "bowling": (4.0, "ground"), "bomb": (5.0, "ground"), "metronome": (8.0, "any"), "cuckoo": (5.0, "any"),
    "plane": (7.0, "any"), "hotair": (10.0, "any"), "car": (8.0, "ground"), "bat": (7.0, "any"),
    "konami": (6.0, "any"), "banana": (4.0, "ground"),
}


def schedule_eggs(m: Music, P: Plan, key: float) -> list[Gag]:
    """One easter egg in every minute of the set (on a downbeat, clear of title cards and transitions),
    dealt from a shuffled deck so the same egg doesn't come back for a while."""
    bar = 4 * m.period
    deck = sorted(EGGS, key=lambda e: h01("deck", e, key))
    out: list[Gag] = []
    blocked = [(c.t0 - bar, c.t1 + bar) for c in P.cards if c.kind != "word"]
    blocked += [(a.t0 - 2 * bar, a.t0 + 2 * bar) for a in P.acts]
    blocked += [(i.t0 - 2 * bar, i.t0 + 2 * bar) for i in P.inters] + [(i.t1 - bar, i.t1 + 2 * bar) for i in P.inters]
    blocked += [(tk.end - 3 * bar, tk.end + (TAKE_CARD + 1) * bar) for a in P.acts for tk in a.takes if not tk.won]
    blocked += [(a.ko - 2 * bar, a.t1 + 2 * bar) for a in P.acts]

    def mode(t):
        if t < P.intro[1] or t >= P.outro[0]:
            return "card"
        if any(i.t0 <= t < i.t1 for i in P.inters):
            return "inter"
        a = act_at(P, t)
        return "sky" if a.sky else "ground"
    n_min = int(m.dur // 60)
    for k in range(1, n_min + 1):
        lo, hi = 60.0 * k - 30, 60.0 * k + 15
        bk0, bk1 = m.bar_at(lo) + 1, m.bar_at(hi)
        cands = []
        for bk in range(bk0, bk1 + 1):
            t = m.bar_time(bk)
            if not (lo <= t <= hi) or t < P.intro[1] + 2 * bar or t > P.outro[0] - 4 * bar:
                continue
            cands.append(t)
        cands.sort(key=lambda t: abs(t - 60.0 * k + 8))
        placed = False
        for t, fresh in [(t, f) for f in (True, False) for t in cands]:
            md = mode(t)
            for j, e in enumerate(deck):
                d, where = EGGS[e]
                if md == "card" or (md == "inter" and where != "any") or (md == "sky" and where == "ground"):
                    continue
                if fresh and any(x.kind == e and t - x.t0 < 610 for x in out):
                    continue        # not the same egg twice in eight minutes, if anything else fits
                if any(b0 < t + d and t < b1 for b0, b1 in blocked) or mode(t + d) != md:
                    continue
                if out and t < out[-1].t1 + 2 * bar:
                    continue
                out.append(Gag(e, t, t + d, -1.0 if h01("eside", k, key) < 0.5 else 1.0, h01("egg", k, key), "egg"))
                deck.append(deck.pop(j))
                placed = True
                break
            if placed:
                break
    return out


def fighting(P: Plan, t: float):
    """The act being fought at t (None during title cards, intermissions, TAKE cards and the end card)."""
    if t < P.intro[1] or t >= P.outro[0] or inter_at(P, t) or take_card_at(P, t):
        return None
    for a in P.acts:
        if a.t0 <= t < a.t1:
            return a
    return None


def take_card_at(P: Plan, t: float):
    """The lost take whose TAKE card is up at t, as (act, take), or None."""
    for a in P.acts:
        if a.t0 <= t < a.t1:
            for tk in a.takes:
                if not tk.won and tk.end <= t < tk.end + TAKE_CARD * 4 * P.period:
                    return a, tk
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
    ph = take_at(a, t).phases if a.takes else a.phases
    return max(0, int(np.searchsorted(ph, t, side="right") - 1)) if ph else 0
