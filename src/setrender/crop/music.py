"""Musical structure for the director: bars, phrases, kick presence, breakdowns, builds and drops,
local tempo, plus sound-event timelines from the on-device classifier."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy import ndimage

from ..analysis import Analysis

VOCALS = ("singing", "rapping", "speech", "choir_singing")


@dataclass
class Segment:
    kind: str          # "breakdown" | "drop" | "build"
    t0: float
    t1: float
    strength: float = 1.0


@dataclass
class SoundEvent:
    label: str
    t0: float
    t1: float
    peak: float


@dataclass
class Structure:
    duration: float
    beats: np.ndarray
    downbeats: np.ndarray
    bar_kick: np.ndarray            # per downbeat: 1 if the kick plays in that bar
    bar_energy: np.ndarray          # per downbeat: 0..1 intensity
    phrases: np.ndarray             # phrase start times (8-bar groups aligned to sections)
    breakdowns: list[Segment] = field(default_factory=list)
    drops: list[Segment] = field(default_factory=list)
    builds: list[Segment] = field(default_factory=list)
    sounds: list[SoundEvent] = field(default_factory=list)
    vocal_t: np.ndarray | None = None     # classifier window centres
    vocal_p: np.ndarray | None = None     # vocal probability per window

    def bar_at(self, t: float) -> int:
        return int(np.clip(np.searchsorted(self.downbeats, t, side="right") - 1, 0, max(len(self.downbeats) - 1, 0)))

    def kick_at(self, t: float) -> bool:
        return bool(len(self.bar_kick) and self.bar_kick[self.bar_at(t)])

    def in_segment(self, segs: list[Segment], t: float) -> Segment | None:
        for s in segs:
            if s.t0 <= t < s.t1:
                return s
        return None

    def vocal_at(self, t) -> np.ndarray:
        if self.vocal_t is None or len(self.vocal_t) == 0:
            return np.zeros_like(np.asarray(t, float))
        return np.interp(t, self.vocal_t, self.vocal_p)


def _sample(an: Analysis, arr: np.ndarray, t: np.ndarray) -> np.ndarray:
    return np.interp(np.asarray(t) * an.feature_rate, np.arange(len(arr)), arr)


def build(an: Analysis, extras: dict | None, clip_start: float) -> Structure:
    beats, db = an.beats, an.downbeats
    dur = an.duration
    if len(db) < 4:
        db = np.arange(0.0, dur, 60.0 / max(an.tempo, 60) * 4)
    period = 60.0 / max(an.tempo, 60)
    sub = an.bands.get("sub", an.loudness)
    # kick presence: beat-synchronous contrast of the sub band (kick on the beat vs between beats)
    if len(beats) > 8:
        on = np.max(np.stack([_sample(an, sub, beats + d) for d in (0.0, 0.025, 0.05, 0.075)]), 0)
        off = np.mean(np.stack([_sample(an, sub, beats + period * f) for f in (0.4, 0.5, 0.6)]), 0)
        contrast = on - off
        bidx = np.clip(np.searchsorted(beats, db - 0.05), 0, len(beats) - 1)
        per_bar = np.array([contrast[i:i + 4].mean() for i in bidx])
        per_bar = ndimage.median_filter(per_bar, 3, mode="nearest")
        ref = np.percentile(per_bar, 90) if len(per_bar) else 1.0
        kick = (per_bar > 0.35 * ref).astype(np.int8)
    else:
        kick = np.ones(len(db), np.int8)
    loud = _sample(an, an.loudness, db + 2 * period)
    ons = _sample(an, ndimage.uniform_filter1d(an.onset, 40), db + 2 * period)
    energy = np.clip(0.55 * loud + 0.25 * ons + 0.2 * kick, 0, 1)

    # breakdowns = runs of >= 4 bars without kick; the bar where the kick returns is a drop
    breakdowns, drops, builds = [], [], []
    k = 0
    n = len(db)
    while k < n:
        if kick[k] == 0:
            j = k
            while j < n and kick[j] == 0:
                j += 1
            if j - k >= 4:
                t0, t1 = float(db[k]), float(db[j]) if j < n else dur
                breakdowns.append(Segment("breakdown", t0, t1, min(1.0, (j - k) / 16)))
                if j < n:
                    nb = min(8, j - k)
                    builds.append(Segment("build", float(db[j - nb]), t1, min(1.0, (j - k) / 16)))
                    end = float(db[min(n - 1, j + 8)]) if j + 8 < n else dur
                    drops.append(Segment("drop", t1, end, min(1.0, (j - k) / 16)))
            k = j
        else:
            k += 1
    # big section energy jumps count as drops too
    for s, e0, e1 in zip(an.sections[1:], an.section_energy[:-1], an.section_energy[1:]):
        if e1 - e0 > 0.18 and not any(abs(d.t0 - s) < 8 for d in drops):
            drops.append(Segment("drop", float(s), float(s) + 16 * period, float(min(1.0, (e1 - e0) * 3))))
    drops.sort(key=lambda s: s.t0)

    # phrases: every 8 bars, restarting at each section boundary
    phr = []
    sec = list(an.sections) + [dur]
    for a, b in zip(sec[:-1], sec[1:]):
        i0 = int(np.searchsorted(db, a - 0.05))
        i1 = int(np.searchsorted(db, b - 0.05))
        phr += [float(db[i]) for i in range(i0, max(i0 + 1, i1), 8) if i < n]
    phrases = np.unique(np.array([0.0] + phr))

    st = Structure(duration=dur, beats=beats, downbeats=db, bar_kick=kick, bar_energy=energy.astype(np.float32),
                   phrases=phrases, breakdowns=breakdowns, drops=drops, builds=builds)

    # sound events (classifier probabilities, sliced to the clip)
    if extras is not None and len(extras.get("sa_t", [])):
        labels = [str(x) for x in extras["sa_labels"]]
        t = extras["sa_t"].astype(np.float64) - clip_start
        P = extras["sa_p"].astype(np.float32)
        keep = (t >= -3) & (t <= dur + 3)
        t, P = t[keep], P[keep]
        voc = np.max(np.stack([P[:, labels.index(v)] for v in VOCALS if v in labels]), 0) if len(P) else np.zeros(0)
        st.vocal_t, st.vocal_p = t, voc
        for lab in labels:
            v = P[:, labels.index(lab)]
            if len(v) == 0 or v.max() < 0.45:
                continue
            hot = v > 0.45
            k = 0
            while k < len(v):
                if hot[k]:
                    j = k
                    while j < len(v) and hot[j]:
                        j += 1
                    st.sounds.append(SoundEvent(lab, float(t[k] - 1.5), float(t[j - 1] + 1.5), float(v[k:j].max())))
                    k = j
                else:
                    k += 1
        st.sounds.sort(key=lambda s: s.t0)
    return st


def local_bpm(beats: np.ndarray, t: np.ndarray, fallback: float) -> np.ndarray:
    if len(beats) < 9:
        return np.full(len(t), fallback, np.float32)
    ibi = np.diff(beats)
    mid = beats[:-1] + ibi / 2
    sm = ndimage.median_filter(ibi, 9, mode="nearest")
    sm = ndimage.uniform_filter1d(sm, 9, mode="nearest")
    return (60.0 / np.interp(t, mid, sm)).astype(np.float32)
