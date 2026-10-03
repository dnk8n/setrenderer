"""The whole set's plan, worked out once from the music so any frame can be drawn on its own:

* a look per section (a motif of nested bubbles, a palette, a foam layout), changing on the section's
  downbeat through a new bubble that inflates and swallows the screen; long breakdowns drift into a
  single giant soap film
* kaleidoscopes that fade in and out on phrase downbeats, with their fold counts and the elements'
  arrangement changing as they do
* drops that pop the bubble (a flash and a ring) on their downbeat
* the dive: how far the camera has fallen into the recursion at every moment, the camera's turn, the
  film's swirl and an animation clock that slows in quiet passages, all integrated up front
* element surges cued by instruments the on-device sound classifier hears (Neural Engine)
* the colour of the light, following the key around the circle of fifths
"""
from __future__ import annotations

import colorsys
import hashlib
import math
from dataclasses import dataclass, field

import numpy as np

from ..crop.music import Structure

MOTIFS = ["lather", "steiner", "hyperbolic", "droste", "raft", "film"]
ELEMENTS = ["fire", "water", "earth", "air", "metal", "ice", "lightning", "magma"]
VOID = 9                       # the motif id that draws nothing (black), before the first bubble and after the last

# how far one unit of the dive moves each motif (a level of lather is a 3x zoom; hyperbolic moves two cells)
DIVE_SCALE = {0: 1.0, 1: 0.9, 2: 0.22, 3: 1.4, 4: 0.75, 5: 1.2}
# the dive wraps at a whole number of each motif's periods (the shader hashes levels modulo 64), so its
# numbers stay small and the picture never jumps
DIVE_WRAP = {0: 64.0, 1: 72.0, 2: 2.0, 3: 64.0, 4: 64.0, 5: 128.0}

# classifier labels -> the element their sound becomes
ELEMENT_SOUNDS = {
    "fire": ["saxophone", "trumpet", "trombone", "brass_instrument", "french_horn", "electric_guitar"],
    "water": ["piano", "electric_piano", "steelpan", "marimba_xylophone", "vibraphone", "mallet_percussion", "harp",
              "liquid_dripping", "water"],
    "earth": ["tabla", "tambourine", "rattle_instrument", "bongo", "conga", "didgeridoo", "bass_guitar", "timpani"],
    "air": ["flute", "wind_instrument", "whistling", "singing", "choir_singing", "harmonica", "accordion", "bagpipes",
            "whoosh_swoosh_swish"],
    "metal": ["cymbal", "gong", "glockenspiel", "bell", "cowbell", "ringtone", "telephone", "telephone_bell_ringing",
              "singing_bowl", "chime", "wind_chime", "tuning_fork"],
    "ice": ["violin_fiddle", "bowed_string_instrument", "cello", "string_section", "orchestra", "zither"],
    "lightning": ["theremin", "reverse_beeps", "disc_scratching", "beep", "siren"],
    "magma": ["organ", "hammond_organ", "electronic_organ", "rapping", "power_tool"],
}
SOUND_ELEMENT = {lab: ELEMENTS.index(e) for e, labs in ELEMENT_SOUNDS.items() for lab in labs}
# transitions
DISSOLVE, IRIS, POP, MELT, COLLAPSE = 0, 1, 2, 3, 4
RATE = 50.0                    # samples per second of the integrated curves


def h01(*a) -> float:
    s = hashlib.blake2b(repr(a).encode(), digest_size=8).digest()
    return int.from_bytes(s, "little") / 2 ** 64


@dataclass
class Look:
    motif: int
    seed: float
    folds: int = 0
    twist: float = 0.5
    density: float = 0.3
    eoff: int = 0
    fbase: float = 430.0
    fswing: float = 260.0
    hue: float = 0.0
    m: tuple = (0.0, 0.0, 0.0, 0.0)
    zoff: float = 0.0
    cam0: float = 0.0


@dataclass
class Span:
    t0: float
    look: Look
    kind: int = DISSOLVE       # how this look arrives
    dur: float = 0.0           # how long the arrival takes
    why: str = ""
    section: int = 0


@dataclass
class Surge:
    t0: float
    t1: float
    elem: int
    label: str
    strength: float


@dataclass
class Plan:
    spans: list[Span] = field(default_factory=list)
    pops: list[float] = field(default_factory=list)
    surges: list[Surge] = field(default_factory=list)
    intro: tuple[float, float] = (0.0, 0.0)
    outro: tuple[float, float] = (0.0, 0.0)     # the last bubble starts collapsing, and pops
    calm_spans: list[tuple[float, float]] = field(default_factory=list)
    build_spans: list[tuple[float, float]] = field(default_factory=list)
    zoom: np.ndarray | None = None              # dive levels at RATE Hz
    swirl: np.ndarray | None = None
    clock: np.ndarray | None = None             # animation clock (s), slows when the music is quiet
    calm: np.ndarray | None = None
    build: np.ndarray | None = None
    key_hue: np.ndarray | None = None           # 1 Hz, hue 0..1 of the light (circle of fifths)
    key_t: np.ndarray | None = None
    beat_step: np.ndarray | None = None         # cumulative camera turn at each beat
    beat_dir: np.ndarray | None = None


def _ease(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def make_look(motif: int, r: np.random.Generator, cfg: dict, folds: int = 0) -> Look:
    tw = float(cfg.get("twist", 0.6))
    film = cfg.get("film", {}) or {}
    thick = float(film.get("thickness", 430.0))
    lk = Look(motif=motif, seed=float(r.random()), folds=folds, twist=tw * float(r.uniform(0.2, 1.6)),
              eoff=int(r.integers(8)), fbase=thick + float(r.uniform(-90, 90)), fswing=float(r.uniform(180, 320)),
              hue=float(r.uniform(-0.08, 0.08)), zoff=float(r.uniform(0, 7)), cam0=float(r.uniform(0, math.tau)))
    if motif == 0:
        lk.m = (float(r.choice([2.8, 3.2, 3.6])), 0.0, 0.0, 0.0)
        lk.density = float(r.uniform(0.26, 0.36))
    elif motif == 1:
        lk.m = (float(r.choice([6, 9, 12])), float(r.uniform(0.15, 0.45)), float(r.uniform(0, 6.3)), 0.0)
        lk.twist *= 0.5
    elif motif == 2:
        p, q = [(6, 4), (8, 4), (4, 6), (6, 6)][int(r.integers(4))]
        lk.m = (float(p), float(q), float(r.uniform(0, 6.3)), 0.0)
        lk.twist *= 0.4
    elif motif == 3:
        n, tw2 = [(6, 1), (8, 1), (8, 2), (10, 1), (6, 2)][int(r.integers(5))]
        lk.m = (float(n), float(tw2), 0.0, 0.0)
        lk.twist *= 0.3
    elif motif == 4:
        k = float(r.choice([4.5, 5.0]))
        lk.m = (k, 0.0, 0.0, 0.0)
        lk.density = 2.4 / k + 0.02
    elif motif == 5:
        lk.fbase = thick - 150.0 + float(r.uniform(-40, 40))
        lk.fswing = float(r.uniform(260, 340))
        lk.twist *= 0.5
    return lk


def plan(an, st: Structure, cfg: dict, seed: int, extras: dict | None, fps: float = 60.0) -> Plan:
    r = np.random.default_rng(seed)
    P = Plan()
    dur = an.duration
    db = np.asarray(st.downbeats, float)
    period = 60.0 / max(an.tempo, 60)
    bar = 4 * period
    beats = an.beats if len(an.beats) > 4 else np.arange(0.0, dur, period)
    names = [m for m in (cfg.get("motifs") or MOTIFS) if m in MOTIFS] or MOTIFS
    pool = [MOTIFS.index(m) for m in names]
    kal = cfg.get("kaleidoscope", {}) or {}
    share = float(kal.get("share", 0.5))
    folds_pool = [int(x) for x in (kal.get("folds") or [3, 4, 5, 6, 8, 10, 12])]

    def snap(t):
        if len(db) == 0:
            return t
        return float(db[int(np.argmin(np.abs(db - t)))])

    # intro: the first bubble inflates out of the dark over four bars from the first downbeat
    first = float(db[0]) if len(db) else 0.0
    if first > 4 * bar:
        first = 0.0
    intro_end = min(dur, first + 4 * bar)
    P.intro = (0.0, intro_end)
    # outro: the last bubble collapses over eight bars and pops
    k_out = int(np.searchsorted(db, dur - 26.0)) if len(db) else 0
    out0 = float(db[k_out]) if 0 < k_out < len(db) else max(intro_end, dur - 26.0)
    out1 = min(dur - 1.0, out0 + 8 * bar)
    if out0 <= intro_end + 4 * bar:          # very short audio: no separate outro
        out0, out1 = dur, dur
    P.outro = (out0, out1)

    # breakdowns (8+ bars without the kick) are calm; builds wind up
    P.calm_spans = [(b.t0, b.t1) for b in st.breakdowns if b.t1 - b.t0 >= 8 * bar - 0.05]
    P.build_spans = [(b.t0, b.t1) for b in st.builds]

    # ---- looks: one per section, phrase-level kaleidoscope and element changes inside it
    secs = [s for s in an.sections if intro_end - 1e-6 <= s < out0 - 2 * bar] if len(an.sections) else []
    secs = sorted(set([snap(s) for s in secs]))
    starts = [intro_end] + [s for s in secs if s > intro_end + 4 * bar - 1e-6]
    drops = [snap(d.t0) for d in st.drops if intro_end + bar <= d.t0 < out0 - bar]
    P.pops = sorted(set(drops))
    longcalm = [(a, b) for a, b in P.calm_spans if b - a >= 16 * bar - 0.05]

    def energy(t0, t1):
        if not len(db):
            return 0.5
        k0, k1 = int(np.searchsorted(db, t0)), int(np.searchsorted(db, t1))
        e = st.bar_energy[k0:max(k1, k0 + 1)]
        return float(np.mean(e)) if len(e) else 0.5

    order = list(pool)
    r.shuffle(order)
    last_motif = -1
    used: dict[int, int] = {}
    kal_on = False
    spans: list[Span] = []
    starts_set = list(starts) + [out0]
    for si, (s0, s1) in enumerate(zip(starts_set[:-1], starts_set[1:])):
        en = energy(s0, s1)
        calm_here = any(a <= s0 + bar and b >= min(s1, s0 + 16 * bar) - bar for a, b in longcalm)
        # the giant film for long breakdowns; otherwise the least used motif that isn't the last one
        if calm_here and 5 in pool and last_motif != 5:
            m = 5
        else:
            cand = [x for x in order if x != last_motif and (x != 5 or en < 0.45 or len(pool) <= 2)] or \
                [x for x in order if x != last_motif] or order
            m = min(cand, key=lambda x: (used.get(x, 0), order.index(x)))
        used[m] = used.get(m, 0) + 1
        last_motif = m
        rs = np.random.default_rng([seed, si, 17])
        kal_on = (m != 5) and (rs.random() < share * (0.7 + 0.6 * en))
        folds = int(rs.choice(folds_pool)) if kal_on else 0
        look = make_look(m, rs, cfg, folds)
        is_drop = any(abs(d - s0) < 0.5 * bar for d in P.pops)
        kind = POP if is_drop else IRIS
        tdur = (0.5 if is_drop else 1.0) * bar
        if si == 0:
            kind, tdur = IRIS, max(intro_end - first, bar)
        spans.append(Span(t0=s0 if si else first, look=look, kind=kind, dur=tdur,
                          why="drop" if is_drop else ("intro" if si == 0 else "section"), section=si))
        # phrases inside the section: kaleidoscopes fade in and out, the elements trade places
        ph = [p for p in st.phrases if s0 + 4 * bar <= p < s1 - 4 * bar]
        prev = look
        for pk, p0 in enumerate(ph):
            rp = np.random.default_rng([seed, si, pk, 29])
            if m == 5 or rp.random() > 0.55:
                continue
            nl = Look(**{**prev.__dict__})
            nl.eoff = (prev.eoff + int(rp.integers(1, 8))) % 8
            want_on = rp.random() < share * (0.7 + 0.6 * energy(p0, p0 + 8 * bar))
            nl.folds = int(rp.choice([f for f in folds_pool if f != prev.folds] or folds_pool)) if want_on else 0
            nl.hue = float(np.clip(prev.hue + rp.uniform(-0.05, 0.05), -0.12, 0.12))
            spans.append(Span(t0=p0, look=nl, kind=MELT if rp.random() < 0.5 else DISSOLVE, dur=bar,
                              why="kaleidoscope" if (nl.folds > 0) != (prev.folds > 0) else "phrase", section=si))
            prev = nl
    void = Look(motif=VOID, seed=0.0)
    spans.insert(0, Span(t0=-1.0, look=void, kind=DISSOLVE, dur=0.0, why="dark"))
    spans.append(Span(t0=out0, look=void, kind=COLLAPSE, dur=max(out1 - out0, 1e-3), why="the end"))
    P.spans = sorted(spans, key=lambda s: s.t0)

    # ---- integrated curves: dive, swirl, animation clock, calm, build
    n = int(math.ceil(dur * RATE)) + 2
    tt = np.arange(n) / RATE
    loud = np.clip(an.at(an.loudness, tt), 0, 1)
    lowmid = np.clip(an.at(an.bands.get("lowmid", an.loudness), tt), 0, 1)
    if len(db):
        bi = np.clip(np.searchsorted(db, tt, side="right") - 1, 0, len(db) - 1)
        be = st.bar_energy[bi] if len(st.bar_energy) else np.full(n, 0.5)
    else:
        be = np.full(n, 0.5)
    calm = np.zeros(n)
    for a, b in P.calm_spans:
        calm = np.maximum(calm, np.clip(np.minimum((tt - a) / bar, (b - tt) / bar), 0, 1))
    build = np.zeros(n)
    for a, b in P.build_spans:
        m_ = (tt >= a) & (tt < b)
        build[m_] = np.maximum(build[m_], (tt[m_] - a) / max(b - a, 1e-3))
    from scipy import ndimage
    loud_s = ndimage.uniform_filter1d(loud, int(RATE * 2))
    lpb = float((cfg.get("dive", {}) or {}).get("levels_per_bar", 0.12))
    rate = lpb / bar * (0.35 + 0.9 * be) * (1.0 - 0.75 * calm) * (1.0 + 1.6 * build) * (0.08 + 0.92 * np.clip(loud_s * 1.6, 0, 1))
    P.zoom = np.concatenate([[0.0], np.cumsum(rate[:-1]) / RATE])
    sw_rate = (0.15 + 1.6 * ndimage.uniform_filter1d(lowmid, int(RATE * 0.3))) * (1.0 - 0.4 * calm) * (0.1 + 0.9 * np.clip(loud_s * 1.6, 0, 1))
    P.swirl = np.concatenate([[0.0], np.cumsum(sw_rate[:-1]) / RATE])
    ck = 0.12 + 0.88 * np.clip(loud_s * 1.5, 0, 1)
    P.clock = np.concatenate([[0.0], np.cumsum(ck[:-1]) / RATE])
    P.calm, P.build = calm.astype(np.float32), build.astype(np.float32)

    # ---- camera: a turn on every kick beat, eased; direction flips each section
    kb = np.array([st.kick_at(b) for b in beats], bool) if len(beats) else np.zeros(0, bool)
    sec_of_beat = np.searchsorted(np.array([s.t0 for s in P.spans]), beats, side="right") - 1 if len(beats) else []
    dirs = np.array([1.0 if h01(seed, int(s), "dir") < 0.5 else -1.0 for s in sec_of_beat]) if len(beats) else np.zeros(0)
    calm_b = np.interp(beats, tt, calm) if len(beats) else np.zeros(0)
    steps = np.where(kb, 0.045, 0.012) * (1.0 - 0.85 * calm_b) * dirs if len(beats) else np.zeros(0)
    P.beat_step = np.concatenate([[0.0], np.cumsum(steps)]).astype(np.float64)
    P.beat_dir = steps

    # ---- surges: instruments the classifier hears become elements
    P.surges = _surges(st, beats, bar, intro_end, out0, seed)

    # ---- the key's colour (Camelot number around the circle of fifths), smoothed
    kt = np.arange(0, int(dur) + 2, 1.0)
    hue = np.full(len(kt), h01(seed, "hue"))
    if extras is not None and len(extras.get("key_t", [])):
        codes = [str(c) for c in extras["key_code"]]
        ktimes = np.asarray(extras["key_t"], float)
        vals = []
        last = None
        for c in codes:
            if c and c[:-1].isdigit():
                last = (int(c[:-1]) - 1) / 12.0 + (0.5 / 12.0 if c.endswith("B") else 0.0)
            vals.append(last)
        if any(v is not None for v in vals):
            first_v = next(v for v in vals if v is not None)
            vals = [first_v if v is None else v for v in vals]
            ang = np.array(vals) * math.tau
            xs = np.interp(kt, ktimes, np.cos(ang))
            ys = np.interp(kt, ktimes, np.sin(ang))
            xs = ndimage.uniform_filter1d(xs, 9, mode="nearest")
            ys = ndimage.uniform_filter1d(ys, 9, mode="nearest")
            hue = (np.arctan2(ys, xs) / math.tau) % 1.0
    P.key_t, P.key_hue = kt, hue.astype(np.float64)
    return P


def _surges(st: Structure, beats: np.ndarray, bar: float, t_min: float, t_max: float, seed: int) -> list[Surge]:
    out: list[Surge] = []
    last_any = -1e9
    last_el: dict[int, float] = {}
    for ev in sorted(st.sounds, key=lambda e: e.t0):
        el = SOUND_ELEMENT.get(ev.label)
        if el is None:
            continue
        heard = ev.t0 + 1.5               # the centre of the first window where the classifier heard it
        if not (t_min + bar <= heard < t_max - 2 * bar):
            continue
        if heard - last_any < 6.0 or heard - last_el.get(el, -1e9) < 40.0:
            continue
        k = int(np.searchsorted(beats, heard)) if len(beats) else 0
        t0 = float(beats[k]) if k < len(beats) and beats[k] - heard < 1.0 else heard
        length = float(np.clip(ev.t1 - ev.t0, 2 * bar, 8 * bar))
        out.append(Surge(t0=t0, t1=t0 + length, elem=el, label=ev.label, strength=float(min(1.0, 0.5 + ev.peak * 0.5))))
        last_any = t0
        last_el[el] = t0
    return out


def light_rgb(h: float, amount: float) -> tuple[float, float, float]:
    """The light's tint: a hue on the circle of fifths, mixed into white by `amount`."""
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, 1.0, 1.0)
    return (1.0 - amount + amount * r * 1.2, 1.0 - amount + amount * g * 1.2, 1.0 - amount + amount * b * 1.2)


def span_at(P: Plan, t: float) -> tuple[Look, Look | None, float, int]:
    """The look on screen at t, the next one arriving (or None) and how far it has arrived."""
    k = 0
    lo, hi = 0, len(P.spans) - 1
    while lo <= hi:                      # last span with t0 <= t
        mid = (lo + hi) // 2
        if P.spans[mid].t0 <= t:
            k, lo = mid, mid + 1
        else:
            hi = mid - 1
    s = P.spans[k]
    if k > 0 and s.dur > 0 and t < s.t0 + s.dur:
        x = (t - s.t0) / s.dur
        return P.spans[k - 1].look, s.look, x, s.kind
    return s.look, None, 0.0, DISSOLVE


def kal_fraction(P: Plan, t0: float, t1: float) -> float:
    """Share of [t0, t1) with a kaleidoscope on screen (the arriving look counts from halfway in)."""
    on = 0.0
    sp = P.spans
    for a, b in zip(sp, sp[1:] + [Span(t0=1e18, look=sp[-1].look)]):
        x0, x1 = max(t0, a.t0 + 0.5 * a.dur), min(t1, b.t0 + 0.5 * b.dur)
        if x1 > x0 and a.look.folds > 0 and a.look.motif != VOID:
            on += x1 - x0
    return on / max(t1 - t0, 1e-9)
