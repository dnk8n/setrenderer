"""The whole set's plan, worked out once from the music so any frame can be drawn on its own:

* a station (one of six experiments) per section, changing on the section's downbeat with a rack focus,
  or with a hard cut when a drop lands there
* the drive: each phrase plays a harmonic of the key's root note, so the key and the harmonic set the
  experiment's mode (Chladni's law for the plates, capillary waves for the dish, standing waves for the
  flame tube...), and the sand or the liquid re-forms into the new pattern over a bar or two
* builds sweep the drive up an octave (the patterns get finer), breakdowns let the experiment come to rest
* drops overdrive it on their downbeat: the sand leaps, the spikes shoot up, the flames roar
* the camera's slow orbit and a turn on every kick, and an animation clock that slows in quiet passages,
  all integrated up front
"""
from __future__ import annotations

import hashlib
import math
from collections import Counter
from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage

from ..crop.music import Structure

STATIONS = ["chladni", "faraday", "ferrofluid", "rubens", "stream", "lissajous"]
VOID = 9                       # draws nothing (black): before the lights come up and after they go down
CUT, FOCUS, MODE = 0, 1, 2     # how a look arrives: hard cut (drops), rack focus (sections), a new mode
RATE = 50.0                    # samples per second of the integrated curves

# light pairs (key light hue, accent hue) and the materials each station can use
PALETTES = [(0.08, 0.55), (0.95, 0.50), (0.12, 0.62), (0.02, 0.75), (0.58, 0.08), (0.80, 0.13), (0.45, 0.92),
            (0.30, 0.85), (0.66, 0.02)]
MATERIALS = {0: 4, 1: 3, 2: 3, 3: 3, 4: 3, 5: 3}

# Chladni's law: a plate's mode frequency grows with the square of its nodal lines; these are the drive
# frequency (Hz) per unit of n^2 + m^2 (square plate) and of (m + 2n)^2 (round plate)
F_SQUARE, F_ROUND = 3.2, 2.4


def h01(*a) -> float:
    s = hashlib.blake2b(repr(a).encode(), digest_size=8).digest()
    return int.from_bytes(s, "little") / 2 ** 64


def root_hz(pc: int) -> float:
    """The key's root an octave below the bass register (A1 = 55 Hz up to G#2)."""
    return 55.0 * 2.0 ** (((pc - 9) % 12) / 12.0)


def camelot_root(code: str) -> tuple[int, bool] | None:
    """Camelot code -> (root pitch class, minor). 8B is C major, 8A is A minor."""
    if not code or not code[:-1].isdigit() or code[-1] not in "AB":
        return None
    n = int(code[:-1])
    major = (11 + 7 * (n - 1)) % 12
    return ((major - 3) % 12, True) if code[-1] == "A" else (major, False)


@dataclass
class Look:
    station: int
    seed: float
    hz: float = 110.0              # drive frequency (root x harmonic)
    harmonic: int = 1
    root: int = 9                  # pitch class of the key's root
    minor: bool = True
    m: tuple = (0.0,) * 8          # the mode (station-specific, see shaders.py)
    pal: tuple = (0.08, 0.55, 0.0, 0.0)   # key light hue, accent hue, material, framing
    cam: tuple = (0.0, 1.0, 3.0, 0.0)     # azimuth offset, elevation, distance, target offset


@dataclass
class Span:
    t0: float
    look: Look
    kind: int = MODE
    dur: float = 0.0               # how long the new mode takes to settle (or the focus pull)
    why: str = ""
    section: int = 0


@dataclass
class Plan:
    spans: list[Span] = field(default_factory=list)
    drops: list[float] = field(default_factory=list)
    intro: tuple[float, float] = (0.0, 0.0)     # the lights come up
    outro: tuple[float, float] = (0.0, 0.0)     # the drive stops and the lights go down
    calm_spans: list[tuple[float, float]] = field(default_factory=list)
    build_spans: list[tuple[float, float]] = field(default_factory=list)
    clock: np.ndarray | None = None             # animation clock (s), slows when the music is quiet
    orbit: np.ndarray | None = None             # the camera's slow orbit (radians)
    phase: np.ndarray | None = None             # a phase that runs with the low mids (drifts, slips, spins)
    calm: np.ndarray | None = None
    sweep: np.ndarray | None = None             # 0..1 through each build: the drive glides up an octave
    beat_step: np.ndarray | None = None         # cumulative camera turn at each beat
    beat_dir: np.ndarray | None = None
    phrase_keys: list[tuple[float, int, bool]] = field(default_factory=list)


def _ease(x: float) -> float:
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


# ---------------------------------------------------------------- modes
def _square_modes() -> list[tuple[int, int]]:
    return [(n, m) for n in range(1, 12) for m in range(0, n) if n + m >= 3]


def _round_modes() -> list[tuple[int, int]]:
    return [(m, n) for m in range(0, 9) for n in range(1, 7) if m + n >= 2]


def make_mode(st: int, hz: float, r: np.random.Generator, prev: Look | None) -> tuple:
    """The mode a station shows when driven at hz. Plates pick the nearest mode by Chladni's law (several
    modes share a frequency, so the choice varies); the others scale continuously in the shader."""
    if st == 0:
        shape = prev.m[0] if prev is not None else float(r.random() < 0.4)
        # the nearest modes ring together (they share the frequency), which gives the richer figures
        if shape < 0.5:
            want = hz / F_SQUARE
            modes = sorted(_square_modes(), key=lambda nm: abs(nm[0] ** 2 + nm[1] ** 2 - want))[:4]
            i, j = r.choice(len(modes), 2, replace=False)
            (n, m), (n2, m2) = modes[int(i)], modes[int(j)]
            sign = 1.0 if r.random() < 0.5 else -1.0
            return (0.0, float(n), float(m), sign, float(r.integers(4)) * 0.5 * math.pi, float(n2), float(m2),
                    float(r.uniform(0.0, 0.8)))
        want = math.sqrt(hz / F_ROUND)
        modes = sorted(_round_modes(), key=lambda mn: abs(mn[0] + 2 * mn[1] - want))[:4]
        i, j = r.choice(len(modes), 2, replace=False)
        (m, n), (m2, n2) = modes[int(i)], modes[int(j)]
        return (1.0, float(m), float(n), 0.0, float(r.uniform(0, math.tau)), float(m2), float(n2),
                float(r.uniform(0.0, 0.8)))
    if st == 1:
        nd = int(r.choice([2, 3, 3, 4, 5, 6]))
        return (float(nd), 0.0, float(r.uniform(0, math.tau)), float(r.random()), 0.0, 0.0, 0.0, 0.0)
    if st == 2:
        lattice = prev.m[0] if prev is not None else float(r.random() < 0.35)
        return (lattice, 0.0, float(r.uniform(0, math.tau)), float(r.uniform(0.85, 1.15)), 0.0, 0.0, 0.0, 0.0)
    if st == 3:
        kind = float(r.choice([0, 0, 1, 2]))     # standing wave, spectrum, standing wave + travelling pulses
        return (kind, float(r.uniform(0, 1)), 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
    if st == 4:
        count = prev.m[0] if prev is not None else float(r.choice([3, 5, 7, 9, 11]))
        return (count, float(r.random() < 0.5), float(r.uniform(0.7, 1.3)), float(r.random()), 0.0, 0.0, 0.0, 0.0)
    return (0.0, float(r.random() < 0.3), float(r.random()), 0.0, 0.0, 0.0, 0.0, 0.0)


def chord(minor: bool, harmonic: int, tension: float = 0.0) -> list[tuple[int, int]]:
    """Three lasers draw the triad as frequency ratios against the root: unison drifting (a circle), the
    fifth (2:3) and the third (4:5 major, 5:6 minor). Higher harmonics swap in the octave, the fourth and the
    sixth; tension (builds) reaches for the dissonant seconds."""
    third = (5, 6) if minor else (4, 5)
    sets = [[(1, 1), (2, 3), third], [(1, 2), (2, 3), third], [(1, 1), (3, 4), (3, 5) if not minor else (5, 8)],
            [(1, 2), third, (3, 4)]]
    out = sets[(harmonic - 1) % len(sets)]
    if tension > 0.5:
        out = [out[0], (8, 9), (15, 16)]
    return out


def _framing(st: int, r: np.random.Generator) -> tuple:
    """Per segment: azimuth offset, elevation (radians), distance, target offset (or 2D zoom and pan)."""
    close = r.random() < 0.4
    if st == 0:
        return (float(r.uniform(0, math.tau)), float(r.uniform(0.95, 1.35)), 1.75 if close else 2.75,
                float(r.uniform(0.15, 0.4)) if close else 0.0)
    if st == 1:
        return (float(r.uniform(0, math.tau)), float(r.uniform(0.85, 1.2)), 1.5 if close else 2.2,
                float(r.uniform(0.1, 0.3)) if close else 0.0)
    if st == 2:
        return (float(r.uniform(0, math.tau)), float(r.uniform(0.32, 0.55)), 1.55 if close else 2.35,
                float(r.uniform(0.0, 0.25)) if close else 0.0)
    if st == 3:
        return (float(r.uniform(-0.6, 0.6)), 0.0, 1.9 if close else 1.0, float(r.uniform(-0.3, 0.3)))
    if st == 4:
        return (0.0, 0.0, 1.35 if close else 1.0, float(r.uniform(-0.3, 0.3)) if close else 0.0)
    return (0.0, float(r.uniform(-0.15, 0.15)), 1.0, 0.0)


def make_look(st: int, seed_r: np.random.Generator, key: tuple[int, bool], harmonic: int, cfg: dict,
              prev: Look | None = None) -> Look:
    pc, minor = key
    hz = root_hz(pc) * harmonic
    if prev is None:
        pal = PALETTES[int(seed_r.integers(len(PALETTES)))]
        mats = (cfg.get("materials", {}) or {}).get(STATIONS[st])
        mat = int(seed_r.integers(MATERIALS[st])) if mats is None else int(mats)
        palt = (pal[0] + float(seed_r.uniform(-0.03, 0.03)), pal[1] + float(seed_r.uniform(-0.03, 0.03)), float(mat), 0.0)
        cam = _framing(st, seed_r)
        seed = float(seed_r.random())
    else:
        palt, cam, seed = prev.pal, prev.cam, prev.seed
    lk = Look(station=st, seed=seed, hz=hz, harmonic=harmonic, root=pc, minor=minor, pal=palt, cam=cam)
    lk.m = make_mode(st, hz, seed_r, prev)
    if st == 5:
        lk.m = (*[float(x) for ab in chord(minor, harmonic) for x in ab], float(lk.m[1]), lk.m[2])
    return lk


# ---------------------------------------------------------------- the plan
def phrase_key(extras: dict | None, t0: float, t1: float, fallback: tuple[int, bool]) -> tuple[int, bool]:
    """The key most often detected in [t0, t1) (the detector wobbles between neighbours on the wheel)."""
    if extras is None or not len(extras.get("key_t", [])):
        return fallback
    kt = np.asarray(extras["key_t"], float)
    codes = [str(c) for c in extras["key_code"]]
    sel = [codes[i] for i in np.nonzero((kt >= t0) & (kt < max(t1, t0 + 1.0)))[0]]
    if not sel:
        k = int(np.clip(np.searchsorted(kt, t0) - 1, 0, len(kt) - 1))
        sel = [codes[k]]
    for code, _ in Counter(sel).most_common():
        r = camelot_root(code)
        if r is not None:
            return r
    return fallback


def plan(an, st: Structure, cfg: dict, seed: int, extras: dict | None, fps: float = 60.0) -> Plan:
    P = Plan()
    dur = an.duration
    db = np.asarray(st.downbeats, float)
    period = 60.0 / max(an.tempo, 60)
    bar = 4 * period
    beats = an.beats if len(an.beats) > 4 else np.arange(0.0, dur, period)
    names = [m for m in (cfg.get("stations") or STATIONS) if m in STATIONS] or STATIONS
    pool = [STATIONS.index(m) for m in names]
    drive = cfg.get("drive", {}) or {}
    hmax = int(drive.get("harmonics", 6))
    settle_bars = float(drive.get("settle_bars", 1.5))

    def snap(t):
        if len(db) == 0:
            return t
        return float(db[int(np.argmin(np.abs(db - t)))])

    # intro: the lights come up over four bars from the first downbeat while the sand settles
    first = float(db[0]) if len(db) else 0.0
    if first > 4 * bar:
        first = 0.0
    intro_end = min(dur, first + 4 * bar)
    P.intro = (first, intro_end)
    tail = min(26.0, max(2 * bar, 0.08 * dur))
    k_out = int(np.searchsorted(db, dur - tail)) if len(db) else 0
    out0 = float(db[k_out]) if 0 < k_out < len(db) else max(intro_end, dur - tail)
    out1 = min(dur - 0.4, out0 + 8 * bar)
    if out0 <= intro_end + 4 * bar:
        out0, out1 = dur, dur
    P.outro = (out0, out1)
    P.calm_spans = [(b.t0, b.t1) for b in st.breakdowns if b.t1 - b.t0 >= 8 * bar - 0.05]
    P.build_spans = [(b.t0, b.t1) for b in st.builds]

    # ---- segments: sections (and long breakdowns' edges), long ones split on phrases every couple of minutes
    drops = [snap(d.t0) for d in st.drops if intro_end + 2 * bar <= d.t0 < out0 - 2 * bar]
    P.drops = sorted(set(drops))
    longcalm = [(snap(a), snap(b)) for a, b in P.calm_spans if b - a >= 16 * bar - 0.05]
    longcalm = [(a, b) for a, b in longcalm if a >= intro_end and b <= out0 - 2 * bar and b - a >= 12 * bar]
    secs = [snap(s) for s in an.sections if intro_end + 4 * bar <= s < out0 - 4 * bar] if len(an.sections) else []
    cuts = sorted(set(secs + [a for a, _ in longcalm] + [b for _, b in longcalm]))
    # a station stays for at least min_bars; a section that starts sooner gets a new mode instead
    min_seg = float(cfg.get("min_bars", 16)) * bar
    seg = [first]
    forced = []
    for c in cuts:
        if c - seg[-1] >= min_seg - 1e-6 and out0 - c >= 4 * bar:
            seg.append(c)
        else:
            forced.append(c)
    seg.append(out0)
    phr = np.asarray(st.phrases, float)
    split = [seg[0]]
    for s0, s1 in zip(seg[:-1], seg[1:]):
        t = s0
        while s1 - t > 170.0:
            want = t + 140.0
            cand = phr[(phr > t + 60.0) & (phr < s1 - 30.0)] if len(phr) else np.zeros(0)
            nxt = float(cand[np.argmin(np.abs(cand - want))]) if len(cand) else snap(want)
            if nxt <= t + 4 * bar or nxt >= s1 - 4 * bar:
                break
            split.append(nxt)
            t = nxt
        split.append(s1)
    seg = split

    fallback = (int(h01(seed, "root") * 12), h01(seed, "minor") < 0.6)
    order = list(pool)
    np.random.default_rng([seed, 5]).shuffle(order)
    last_st = -1
    used: dict[int, int] = {}
    spans: list[Span] = []
    for si, (s0, s1) in enumerate(zip(seg[:-1], seg[1:])):
        cand = [x for x in order if x != last_st] or order
        sti = min(cand, key=lambda x: (used.get(x, 0), order.index(x)))
        used[sti] = used.get(sti, 0) + 1
        last_st = sti
        rs = np.random.default_rng([seed, si, 17])
        key = phrase_key(extras, s0, s0 + 8 * bar, fallback)
        harm = int(rs.integers(1, min(3, hmax) + 1))
        look = make_look(sti, rs, key, harm, cfg)
        is_drop = any(abs(d - s0) < 0.5 * bar for d in P.drops)
        if si == 0:
            kind, why, tdur = MODE, "intro", max(intro_end - first, bar)
        elif is_drop:
            kind, why, tdur = CUT, "drop", settle_bars * bar
        else:
            kind, why, tdur = FOCUS, "section", bar
        spans.append(Span(t0=s0, look=look, kind=kind, dur=tdur, why=why, section=si))
        P.phrase_keys.append((s0, *key))
        # phrases inside the segment: a new harmonic (or the key moved), the pattern re-forms; drops overdrive
        ph = [(p, False) for p in phr if s0 + 4 * bar <= p < s1 - 2 * bar]
        ph += [(c, False) for c in forced if s0 + 2 * bar <= c < s1 - 2 * bar and c not in set(ph_t for ph_t, _ in ph)]
        ph += [(d, True) for d in P.drops if s0 + 2 * bar <= d < s1 - 2 * bar]
        ph.sort()
        prev = look
        last_t = s0
        for pk, (p0, drop) in enumerate(ph):
            if p0 - last_t < 2 * bar:
                continue
            rp = np.random.default_rng([seed, si, pk, 29])
            nxt_p = phr[phr > p0 + bar]
            key = phrase_key(extras, p0, float(nxt_p[0]) if len(nxt_p) else p0 + 8 * bar, (prev.root, prev.minor))
            moved = key != (prev.root, prev.minor)
            if not drop and not moved and p0 not in forced and rp.random() > 0.7:
                continue
            step = int(rp.choice([-2, -1, 1, 1, 2]))
            harm = int(np.clip(prev.harmonic + step, 1, hmax))
            if harm == prev.harmonic and not moved:
                harm = prev.harmonic + 1 if prev.harmonic < hmax else prev.harmonic - 1
            nl = make_look(sti, rp, key, harm, cfg, prev=prev)
            why = "drop" if drop else ("key" if moved else "harmonic")
            spans.append(Span(t0=p0, look=nl, kind=MODE, dur=settle_bars * bar, why=why, section=si))
            P.phrase_keys.append((p0, *key))
            prev = nl
            last_t = p0
    void = Look(station=VOID, seed=0.0)
    spans.insert(0, Span(t0=-1.0, look=void, kind=CUT, dur=0.0, why="dark"))
    P.spans = sorted(spans, key=lambda s: s.t0)

    # ---- integrated curves: animation clock, orbit, calm, sweep
    n = int(math.ceil(dur * RATE)) + 2
    tt = np.arange(n) / RATE
    loud = np.clip(an.at(an.loudness, tt), 0, 1)
    lowmid = np.clip(an.at(an.bands.get("lowmid", an.loudness), tt), 0, 1)
    calm = np.zeros(n)
    for a, b in P.calm_spans:
        calm = np.maximum(calm, np.clip(np.minimum((tt - a) / bar, (b - tt) / bar), 0, 1))
    sweep = np.zeros(n)
    for a, b in P.build_spans:
        m_ = (tt >= a) & (tt < b)
        sweep[m_] = np.maximum(sweep[m_], (tt[m_] - a) / max(b - a, 1e-3))
    loud_s = ndimage.uniform_filter1d(loud, int(RATE * 2))
    ck = (0.12 + 0.88 * np.clip(loud_s * 1.5, 0, 1)) * (1.0 - 0.5 * calm)
    P.clock = np.concatenate([[0.0], np.cumsum(ck[:-1]) / RATE])
    from ..timeline import _attack_release
    lm = _attack_release(lowmid.astype(np.float64), RATE, 0.25, 0.8)
    orate = float((cfg.get("camera", {}) or {}).get("orbit", 0.035)) * (0.3 + 1.4 * lm) * (1.0 - 0.6 * calm)
    P.orbit = np.concatenate([[0.0], np.cumsum(orate[:-1]) / RATE])
    prate = (0.12 + 1.3 * lm) * (1.0 - 0.6 * calm)
    P.phase = np.concatenate([[0.0], np.cumsum(prate[:-1]) / RATE])
    P.calm, P.sweep = calm.astype(np.float32), sweep.astype(np.float32)

    # ---- camera: a small turn on every kick beat, eased; the direction flips each segment
    kb = np.array([st.kick_at(b) for b in beats], bool) if len(beats) else np.zeros(0, bool)
    seg_of_beat = np.searchsorted(np.array(seg[:-1]), beats, side="right") - 1 if len(beats) else []
    dirs = np.array([1.0 if h01(seed, int(s), "dir") < 0.5 else -1.0 for s in seg_of_beat]) if len(beats) else np.zeros(0)
    calm_b = np.interp(beats, tt, calm) if len(beats) else np.zeros(0)
    turn = float((cfg.get("camera", {}) or {}).get("kick_turn", 0.02))
    steps = np.where(kb, turn, 0.25 * turn) * (1.0 - 0.85 * calm_b) * dirs if len(beats) else np.zeros(0)
    P.beat_step = np.concatenate([[0.0], np.cumsum(steps)]).astype(np.float64)
    P.beat_dir = steps
    return P


def span_at(P: Plan, t: float) -> tuple[Look, Look, float, Span]:
    """(previous look, current look, how far the current one has arrived 0..1, current span)."""
    k = 0
    lo, hi = 0, len(P.spans) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if P.spans[mid].t0 <= t:
            k, lo = mid, mid + 1
        else:
            hi = mid - 1
    s = P.spans[k]
    x = 1.0 if s.dur <= 0 else min(max((t - s.t0) / s.dur, 0.0), 1.0)
    prev = P.spans[k - 1].look if k > 0 else s.look
    if s.why != "intro" and (s.kind != MODE or prev.station != s.look.station):
        prev = s.look                    # (the intro arrives from nothing: the experiment switches on)
    return prev, s.look, x, s

