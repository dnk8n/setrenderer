"""cymatics: sound made visible. A physics lab at night where each experiment is played by the set: sand on
a Chladni plate, Faraday waves in a dish, ferrofluid spikes, a Rubens tube of flames, water streams frozen
by a strobe and laser Lissajous figures drawing the chord of the key, filmed like macro photography. Frames
are pure functions of their index and of the whole set's plan (plan.py), so a slice draws exactly the
frames the full render has at those times."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from .. import analysis
from ..crop import music as cmusic
from ..timeline import _attack_release
from . import plan as planner
from .engine import Engine
from .plan import FOCUS, RATE, VOID

LAYERS = {"drive": 0, "detail": 1, "sparkle": 2, "light": 3}


def _load(cfg: dict):
    clip = cfg["_clip"]
    full = analysis.load(Path(clip["analysis"]))
    ex = None
    if clip.get("extras") and Path(clip["extras"]).exists():
        z = np.load(clip["extras"], allow_pickle=True)
        ex = {k: z[k] for k in z.files}
    st = cmusic.build(full, ex, 0.0)
    return full, st, ex


def running_order(cfg: dict, rng):
    """The plan for the whole set (no GPU needed)."""
    full, st, ex = _load(cfg)
    seed = int(rng.integers(1 << 30))
    P = planner.plan(full, st, cfg, seed, ex)
    return full, st, ex, seed, P


def highlight_hints(cfg: dict, title: str, rng):
    """Moments worth a reel clip: drops that overdrive the experiment, new stations, new harmonics.
    Returns (hints [(t, weight, label)], intro end, outro start) for reel.choose."""
    full, st, ex, seed, P = running_order(cfg, rng)
    names = planner.STATIONS
    # labels start "<station> at", the reel's kind of moment, so it spreads its clips over the stations
    hints = [(t, 1.0, f"{names[planner.span_at(P, t + 0.01)[1].station]} at the drop") for t in P.drops]
    for s in P.spans:
        if s.look.station == VOID:
            continue
        if s.why == "section":
            hints.append((s.t0, 0.6, f"{names[s.look.station]} at its arrival"))
        elif s.why in ("harmonic", "key"):
            hints.append((s.t0, 0.3, f"{names[s.look.station]} at harmonic {s.look.harmonic}"))
    # the reel's last clip catches the lights going down
    return hints, P.intro[1], P.outro[1] - 3.5


class CymaticsScene:
    pix_fmt = "nv12"

    def __init__(self, cfg: dict, tl, an_slice, rng, title: str, fingerprint: dict):
        clip = cfg["_clip"]
        self.cfg = cfg
        self.fps = float(tl.fps)
        self.start = float(clip["start"])
        self.title = title
        self.full, self.st, ex, self.seed, self.P = running_order(cfg, rng)
        full = self.full
        self.bar = 4 * 60.0 / max(full.tempo, 60)
        pu = cfg.get("pulse", {}) or {}
        self.pump = float(pu.get("exposure", 0.10))
        self.aberr = float(pu.get("aberration", 0.6))
        lens = cfg.get("lens", {}) or {}
        self.dof = float(lens.get("depth_of_field", 0.7))
        self.vignette = float(lens.get("vignette", 0.35))
        self.bloom = float(cfg.get("bloom", 0.3))
        self.sat = float((cfg.get("colour", {}) or {}).get("saturation", 1.05))
        self.exposure = float((cfg.get("colour", {}) or {}).get("exposure", 1.0))
        # smoothed band envelopes for the whole set, one value per video frame
        n = int(math.ceil(full.duration * self.fps)) + 2
        tt = (np.arange(n) + 0.5) / self.fps
        sm = cfg.get("smoothing", {}) or {}
        self.env = {}
        for k in ("sub", "bass", "lowmid", "highmid", "high"):
            a, rel = sm.get(k, [0.01, 0.15])
            self.env[k] = _attack_release(full.at(full.bands.get(k, full.loudness), tt).astype(np.float64),
                                          self.fps, a, rel).astype(np.float32)
        a, rel = sm.get("loudness", [0.2, 0.8])
        self.env["loud"] = _attack_release(full.at(full.loudness, tt).astype(np.float64), self.fps, a, rel).astype(np.float32)
        self.beats = full.beats if len(full.beats) else np.array([1e9])
        self.kick_beat = np.array([self.st.kick_at(b) for b in self.beats], bool) if len(full.beats) else np.zeros(1, bool)
        self.focus_t = np.array([s.t0 for s in self.P.spans if s.kind == FOCUS] or [1e18])
        self.drops = np.array(self.P.drops or [1e18])
        self.debug = 0                 # 1 = the experiment's own field, 2 = what its mode predicts (criteria)
        self.layers = (1.0, 1.0, 1.0, 1.0)
        self.size = (int(clip.get("width", 1920)), int(clip.get("height", 1080)))
        self.engine = Engine(*self.size)

    # ------------------------------------------------------------------ per-frame state
    def _curve(self, arr: np.ndarray, t: float) -> float:
        x = t * RATE
        k = int(min(max(math.floor(x), 0), len(arr) - 2))
        f = min(max(x - k, 0.0), 1.0)
        return float(arr[k] * (1 - f) + arr[k + 1] * f)

    def kick(self, t: float) -> tuple[float, float, float, int]:
        """The beat shown on the frame whose display interval contains it: (pulse decaying from its strength,
        its strength (1 in bars with the kick), time since it, beat index)."""
        b = self.beats
        k = int(np.searchsorted(b, t + 1.0 / self.fps - 1e-6, side="right") - 1)
        if k < 0:
            return 0.0, 0.0, 9.0, k
        since = max(0.0, t - b[k])
        amp = 1.0 if self.kick_beat[min(k, len(self.kick_beat) - 1)] else 0.15
        return amp * math.exp(-since / 0.12), amp, since, k

    def turn(self, t: float, k: int) -> float:
        P = self.P
        if len(P.beat_dir) == 0 or k < 0:
            return 0.0
        k = min(k, len(P.beat_dir) - 1)
        frac = min(max((t - self.beats[k]) / 0.18, 0.0), 1.0)
        return float(P.beat_step[k] + P.beat_dir[k] * (1.0 - (1.0 - frac) ** 3))

    def defocus(self, t: float) -> float:
        j = int(np.searchsorted(self.focus_t, t))
        best = 0.0
        for c in (j - 1, j):
            if 0 <= c < len(self.focus_t):
                d = abs(t - self.focus_t[c])
                if d < 0.5 * self.bar:
                    best = max(best, 1.0 - planner._ease(d / (0.5 * self.bar)))
        return best

    def gain(self, t: float) -> tuple[float, float]:
        """(drive gain: the experiment switching on and off, fade to black: the lights)."""
        P = self.P
        i0, i1 = P.intro
        o0, o1 = P.outro
        g = planner._ease((t - i0) / max(i1 - i0, 1e-3)) if t < i1 else 1.0
        fade = 1.0 - planner._ease((t - i0) / max(0.5 * (i1 - i0), 1e-3)) if t < i1 else 0.0
        if t >= o0:
            g = min(g, 1.0 - planner._ease((t - o0) / max(0.6 * (o1 - o0), 1e-3)))
            fade = max(fade, planner._ease((t - o0 - 0.4 * (o1 - o0)) / max(0.6 * (o1 - o0), 1e-3)))
        return g, fade

    @staticmethod
    def _look(L) -> list[float]:
        m = list(L.m) + [0.0] * (8 - len(L.m))
        return [float(L.station), L.seed, L.hz, float(L.harmonic), *m[:8], *L.pal[:3], 0.0]

    def uniforms(self, t: float) -> np.ndarray:
        P = self.P
        fi = int(min(max(0, round(t * self.fps)), len(self.env["sub"]) - 1))
        e = {k: float(v[fi]) for k, v in self.env.items()}
        kick, kamp, since, k = self.kick(t)
        # the flip (the dish's period doubling, the streams' slip) starts just after the beat's frame, so that
        # frame carries the brightness pulse on a still pattern
        flip = (k + planner._ease((since - 0.04) / 0.22)) if k >= 0 else 0.0
        calm = self._curve(P.calm, t)
        # a change shows on the frame whose display interval holds its downbeat (like the beats)
        prev, cur, x, span = planner.span_at(P, t + 1.0 / self.fps - 1e-6)
        x = 1.0 if span.dur <= 0 else min(max((t - span.t0) / span.dur, 0.0), 1.0)
        j = int(np.searchsorted(self.drops, t + 1.0 / self.fps - 1e-6, side="right") - 1)
        age = max(0.0, t - self.drops[j]) if j >= 0 and t - self.drops[j] < 4.0 else -1.0
        g, fade = self.gain(t)
        st = cur.station
        orbit = self._curve(P.orbit, t)
        az, el, dist, off = cur.cam
        if st in (0, 1, 2):
            cam = [az + orbit + self.turn(t, k), el, dist, off]
        elif st == 3:
            cam = [az + 0.2 * math.sin(3.0 * self.turn(t, k)), 0.0, dist, off]
        elif st == 4:
            cam = [0.0, 0.0, dist * (1.0 + 0.01 * kick), off]
        else:
            cam = [0.0, el + 0.5 * self.turn(t, k), dist, off]
        exposure = self.exposure * (1.0 + self.pump * kick * (1.0 - 0.5 * calm))
        lift = 2.5 * self.pump * kick * (1.0 - 0.5 * calm) * g
        ca = self.aberr * (0.2 + 0.8 * kick)
        bloom = self.bloom * (0.8 + 0.4 * e["loud"])
        if self.debug >= 10:           # isolating one layer: no pump, no aberration
            exposure, ca, lift = self.exposure, 0.0, 0.0
        v = [self.size[0], self.size[1], 2.0 / self.size[1], self.size[0] / self.size[1],
             self._curve(P.clock, t), flip, since, float(round(t * self.fps)),
             kick, e["sub"], e["bass"], e["lowmid"],
             e["highmid"], e["high"], e["loud"], calm,
             *self._look(prev), *self._look(cur),
             x, kamp, self.defocus(t), self._curve(P.sweep, t),
             age, 1.0 if age >= 0 else 0.0, g, self._curve(P.phase, t),
             *cam,
             exposure, ca, self.vignette, bloom,
             float(self.debug if self.debug in (1, 2) else 0), self.dof, fade, self.sat,
             *self.layers,
             lift, 0.0, 0.0, 0.0]
        return np.array(v, np.float32)

    def isolate(self, layer: str | None):
        """Drive only one layer (drive, detail, sparkle, light) for the band-response checks; None restores."""
        if layer is None:
            self.debug, self.layers = 0, (1.0, 1.0, 1.0, 1.0)
        else:
            g = [0.0] * 4
            g[LAYERS[layer]] = 1.0
            self.debug, self.layers = 10, tuple(g)

    # ------------------------------------------------------------------ frames
    def frame(self, i: int) -> bytes:
        return self.engine.render(self.uniforms(self.start + i / self.fps), out="nv12")

    def frame_rgba(self, i: int) -> bytes:
        return self.engine.render(self.uniforms(self.start + i / self.fps), out="rgba")

    def frame_at(self, t: float, out: str = "rgba") -> bytes:
        return self.engine.render(self.uniforms(t), out=out)
