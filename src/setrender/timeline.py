"""Per-video-frame control signals derived from the analysis (all precomputed, deterministic)."""
from __future__ import annotations

import numpy as np

from .analysis import Analysis


def _attack_release(x: np.ndarray, fps: float, attack: float, release: float) -> np.ndarray:
    a = 1.0 if attack <= 0 else 1 - np.exp(-1.0 / (attack * fps))
    r = 1.0 if release <= 0 else 1 - np.exp(-1.0 / (release * fps))
    out = np.empty_like(x)
    v = 0.0
    for i, s in enumerate(x.tolist()):
        v += (s - v) * (a if s > v else r)
        out[i] = v
    return out


class Timeline:
    def __init__(self, an: Analysis, fps: float, smoothing: dict):
        self.fps = fps
        self.n = int(round(an.duration * fps))
        t = np.arange(self.n) / fps
        # sample features at frame centres
        tc = t + 0.5 / fps
        self.t = t
        feats = {k: an.at(v, tc) for k, v in an.bands.items()}
        # take the per-frame max inside the frame window for punchy transients
        feats["onset"] = an.at(an.onset, tc)
        feats["loudness"] = an.at(an.loudness, tc)
        self.env = {}
        for k, v in feats.items():
            att, rel = smoothing.get(k, [0.01, 0.15])
            self.env[k] = _attack_release(v.astype(np.float64), fps, att, rel).astype(np.float32)

        beats = an.beats
        self.beats = beats
        if len(beats) == 0:
            beats = np.array([1e9])  # no beats (silence, ambient): no pulses
        # frame index at which each beat first shows
        # a beat shows on the frame whose display interval [t, t+1/fps) contains it
        tb = t + 1.0 / fps - 1e-9
        idx = np.searchsorted(beats, tb, side="right") - 1
        prev = np.where(idx >= 0, beats[np.clip(idx, 0, len(beats) - 1)], -1.0)
        nxt = beats[np.clip(idx + 1, 0, len(beats) - 1)]
        period = np.where(nxt > prev, nxt - prev, 60 / max(an.tempo, 1))
        self.beat_idx = idx
        self.since_beat = np.where(idx >= 0, np.maximum(t - prev, 0.0), 9.0)
        self.beat_phase = np.clip(self.since_beat / period, 0, 1)
        self.beat_env = np.exp(-self.since_beat / 0.11).astype(np.float32)
        self.env["beat"] = self.beat_env

        db = an.downbeats if len(an.downbeats) else np.array([1e9])
        didx = np.searchsorted(db, tb, side="right") - 1
        dprev = np.where(didx >= 0, db[np.clip(didx, 0, len(db) - 1)], -9.0)
        self.bar_idx = didx
        self.bar_env = np.exp(-np.maximum(t - dprev, 0.0) / 0.25).astype(np.float32)

        sec = an.sections
        sidx = np.clip(np.searchsorted(sec, t + 1e-9, side="right") - 1, 0, len(sec) - 1)
        self.section_idx = sidx
        self.section_energy = an.section_energy[sidx] if len(an.section_energy) else np.zeros(self.n)
        self.since_section = t - sec[sidx]
        self.tempo = an.tempo
