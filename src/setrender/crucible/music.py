"""The music as crucible reads it: event times (kicks, hats, snares, drops), band curves for any window, and a
handful of features per stretch of the set that decide which trial it gets and how that trial's world is built."""
from __future__ import annotations

import math
from collections import Counter

import numpy as np
from scipy import ndimage

from ..crop.music import Structure

BANDS = ("sub", "bass", "lowmid", "highmid", "high")


def _peaks(x: np.ndarray, rate: float, gap_s: float = 0.09, k: float = 1.0) -> np.ndarray:
    """Onset times of a band: peaks of its rise, above the local mean plus k local deviations."""
    f = np.maximum(np.diff(x, prepend=x[:1]), 0.0)
    w = max(3, int(4.0 * rate))
    mu = ndimage.uniform_filter1d(f, w)
    sd = np.sqrt(np.maximum(ndimage.uniform_filter1d(f * f, w) - mu * mu, 0.0))
    g = max(1, int(gap_s * rate))
    loc = f == ndimage.maximum_filter1d(f, 2 * g + 1)
    idx = np.nonzero(loc & (f > mu + k * sd) & (f > 0.02))[0]
    return idx / rate


class Music:
    def __init__(self, an, st: Structure, extras: dict | None):
        self.an, self.st, self.ex = an, st, extras
        self.dur = float(an.duration)
        self.tempo = float(max(an.tempo, 60.0))
        self.beat = 60.0 / self.tempo
        self.bar = 4 * self.beat
        self.beats = an.beats if len(an.beats) > 4 else np.arange(0.0, self.dur, self.beat)
        kb = np.array([st.kick_at(b) for b in self.beats], bool) if len(self.beats) else np.zeros(0, bool)
        self.kicks = self.beats[kb] if len(self.beats) else self.beats
        r = an.feature_rate
        self.hats = _peaks(an.bands.get("high", an.onset), r, 0.07)
        self.snares = _peaks(an.bands.get("highmid", an.onset), r, 0.12, 1.3)
        self.bassh = _peaks(an.bands.get("bass", an.onset), r, 0.2, 1.2)
        self.drops = np.array(sorted(d.t0 for d in st.drops), float)
        self.downbeats = np.asarray(st.downbeats, float)
        self.phrases = np.asarray(st.phrases, float)

    # ------------------------------------------------------------------ curves and events in a window
    def curve(self, name: str, t0: float, t1: float, rate: float = 60.0) -> np.ndarray:
        n = max(1, int(math.ceil((t1 - t0) * rate)) + 1)
        t = t0 + np.arange(n) / rate
        arr = self.an.loudness if name == "loud" else (self.an.onset if name == "onset" else self.an.bands[name])
        return np.clip(self.an.at(arr, t), 0.0, 1.0).astype(np.float32)

    def events(self, name: str, t0: float, t1: float) -> np.ndarray:
        e = {"kick": self.kicks, "beat": self.beats, "hat": self.hats, "snare": self.snares, "bass": self.bassh,
             "drop": self.drops, "bar": self.downbeats}[name]
        return (e[(e >= t0) & (e < t1)] - t0).astype(np.float64)

    def key_at(self, t0: float, t1: float) -> tuple[int, bool]:
        ex = self.ex
        if ex is None or not len(ex.get("key_t", [])):
            return 9, True
        from ..cymatics.plan import camelot_root
        kt = np.asarray(ex["key_t"], float)
        codes = [str(c) for c in ex["key_code"]]
        sel = [codes[i] for i in np.nonzero((kt >= t0) & (kt < max(t1, t0 + 1.0)))[0]]
        if not sel:
            sel = [codes[int(np.clip(np.searchsorted(kt, t0) - 1, 0, len(kt) - 1))]]
        for code, _ in Counter(sel).most_common():
            r = camelot_root(code)
            if r is not None:
                return r
        return 9, True

    def feats(self, t0: float, t1: float) -> dict:
        """What a stretch of the set is like (raw values; the planner compares them across the set)."""
        an, st = self.an, self.st
        t = np.arange(t0, max(t1, t0 + 1.0), 0.25)
        b = {k: float(np.mean(an.at(an.bands[k], t))) for k in BANDS}
        loud = an.at(an.loudness, t)
        dbs = self.downbeats[(self.downbeats >= t0) & (self.downbeats < t1)]
        kickfrac = float(np.mean([st.kick_at(x) for x in dbs])) if len(dbs) else 0.0
        calm = sum(max(0.0, min(s.t1, t1) - max(s.t0, t0)) for s in st.breakdowns) / max(t1 - t0, 1.0)
        span_min = max((t1 - t0) / 60.0, 1e-3)
        root, minor = self.key_at(t0, t1)
        return {
            "energy": float(np.mean(loud)), "dyn": float(np.std(loud)), "low": 0.5 * (b["sub"] + b["bass"]),
            "mid": b["lowmid"], "bright": 0.5 * (b["highmid"] + b["high"]),
            "perc": float(np.mean(an.at(an.onset, t))), "kick": kickfrac, "calm": float(calm),
            "drops": float(len(self.events("drop", t0, t1)) / span_min),
            "hats": float(len(self.events("hat", t0, t1)) / span_min / 200.0),
            "vocal": float(np.mean(st.vocal_at(t))), "minor": 1.0 if minor else 0.0, "root": float(root),
            **{"b_" + k: v for k, v in b.items()},
        }

    def profile(self, t0: float, t1: float, n: int) -> np.ndarray:
        """(5, n): the five bands' mean over n equal steps of [t0, t1) (a coarse spectrogram)."""
        edges = np.linspace(t0, t1, n + 1)
        out = np.zeros((5, n), np.float32)
        for k, name in enumerate(BANDS):
            arr = self.an.bands[name]
            for j in range(n):
                tt = np.linspace(edges[j], edges[j + 1], 8)
                out[k, j] = float(np.mean(self.an.at(arr, tt)))
        return out

    def loud_profile(self, t0: float, t1: float, n: int) -> np.ndarray:
        tt = np.linspace(t0, t1, n)
        return ndimage.uniform_filter1d(self.an.at(self.an.loudness, tt), max(1, n // 40)).astype(np.float32)
