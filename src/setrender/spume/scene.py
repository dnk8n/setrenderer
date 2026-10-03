"""spume: alien foam, drawn on the GPU. Bubbles inside bubbles inside bubbles, soap films in the colours
of real thin-film interference, kaleidoscopes fading in and out, and the earth's elements in alternating
bubbles. Frames are pure functions of their index and of the whole set's plan (plan.py), so a slice draws
exactly the frames the full render has at those times."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from .. import analysis
from ..crop import music as cmusic
from ..timeline import _attack_release
from . import film, plan as planner
from .engine import Engine
from .plan import RATE, VOID

LAYERS = {"film": 0, "border": 1, "interior": 2, "sparkle": 3}


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
    """Moments worth a reel clip: drops that pop, new motifs, kaleidoscopes arriving and element surges.
    Returns (hints [(t, weight, label)], intro end, outro start) for reel.choose."""
    full, st, ex, seed, P = running_order(cfg, rng)
    names = planner.MOTIFS
    hints = [(t, 1.0, "pop") for t in P.pops]
    for s in P.spans:
        if s.look.motif == VOID:
            continue
        if s.why == "section":
            hints.append((s.t0, 0.5, f"motif {names[s.look.motif]}"))
        elif s.why == "kaleidoscope" and s.look.folds:
            hints.append((s.t0, 0.35, f"kaleidoscope {s.look.folds}"))
    hints += [(g.t0, 0.6, f"surge {planner.ELEMENTS[g.elem]}") for g in P.surges]
    # the reel's last clip should catch the final pop: it starts just before it
    return hints, P.intro[1], P.outro[1] - 2.2


class SpumeScene:
    pix_fmt = "nv12"

    def __init__(self, cfg: dict, tl, an_slice, rng, title: str, fingerprint: dict):
        clip = cfg["_clip"]
        self.cfg = cfg
        self.fps = float(tl.fps)
        self.start = float(clip["start"])
        self.title = title
        self.full, self.st, ex, self.seed, self.P = running_order(cfg, rng)
        full = self.full
        r = np.random.default_rng([self.seed, 3])
        # per-set palette: each element's hue nudged a little, the light's tint
        col = cfg.get("colour", {}) or {}
        spread = float(col.get("hue_spread", 0.06))
        self.pal = r.uniform(-spread, spread, 8).astype(np.float32)
        self.sat = float(col.get("saturation", 1.2))
        self.key_light = float(col.get("key_light", 0.22))
        fl = cfg.get("film", {}) or {}
        self.film_strength = float(fl.get("strength", 1.0))
        pu = cfg.get("pulse", {}) or {}
        self.pump = float(pu.get("exposure", 0.16))
        self.punch = float(pu.get("punch", 0.035))
        self.aberr = float(pu.get("aberration", 1.0))
        self.bloom = float(cfg.get("bloom", 0.25))
        self.surges_on = bool((cfg.get("surges", {}) or {}).get("enabled", True))
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
        self.pops = np.array(sorted(self.P.pops + ([self.P.outro[1]] if self.P.outro[1] < full.duration else [])))
        self.key_unwrapped = np.unwrap(self.P.key_hue * 2 * math.pi) / (2 * math.pi)
        self.debug = 0                 # 1 = ids (depth, element, bubble) for the criteria, 10 = one layer alone
        self.layers = (1.0, 1.0, 1.0, 1.0)
        self.force_elem = -1
        self.size = (int(clip.get("width", 1920)), int(clip.get("height", 1080)))
        lut = film.table()
        self.engine = Engine(*self.size, lut=lut)

    # ------------------------------------------------------------------ per-frame state
    def _curve(self, arr: np.ndarray, t: float) -> float:
        x = t * RATE
        k = int(min(max(math.floor(x), 0), len(arr) - 2))
        f = min(max(x - k, 0.0), 1.0)
        return float(arr[k] * (1 - f) + arr[k + 1] * f)

    def kick(self, t: float) -> tuple[float, int]:
        """Exposure pump: decays from 1 on each beat (kick bars), shown on the frame whose display interval
        contains the beat."""
        b = self.beats
        k = int(np.searchsorted(b, t + 1.0 / self.fps - 1e-6, side="right") - 1)
        if k < 0:
            return 0.0, k
        since = max(0.0, t - b[k])
        amp = 1.0 if self.kick_beat[min(k, len(self.kick_beat) - 1)] else 0.15
        return amp * math.exp(-since / 0.12), k

    def cam(self, t: float, k: int) -> float:
        P = self.P
        if len(P.beat_dir) == 0 or k < 0:
            return 0.0
        k = min(k, len(P.beat_dir) - 1)
        b = self.beats
        frac = min(max((t - b[k]) / 0.18, 0.0), 1.0)
        ease = 1.0 - (1.0 - frac) ** 3
        return float(P.beat_step[k] + P.beat_dir[k] * ease)

    def surge(self, t: float) -> tuple[float, float]:
        if not self.surges_on:
            return -1.0, 0.0
        bar = 4 * 60.0 / max(self.full.tempo, 60)
        for g in self.P.surges:
            if g.t0 - 0.2 <= t < g.t1 + bar:
                x = min((t - g.t0) / (bar / 4), 1.0) if t >= g.t0 else 0.0
                y = min(max((g.t1 + bar - t) / bar, 0.0), 1.0)
                return float(g.elem), float(g.strength * min(x, y))
            if g.t0 > t + 1:
                break
        return -1.0, 0.0

    def _look(self, L, t: float, cam: float, zoom: float, swirl: float, build: float) -> list[float]:
        z = (zoom * planner.DIVE_SCALE.get(L.motif, 1.0) + L.zoff) % planner.DIVE_WRAP.get(L.motif, 64.0)
        tw = L.twist * (1.0 + 1.8 * build)
        return [L.motif, z, L.cam0 + cam, L.seed, L.folds, tw, L.density, L.eoff,
                L.fbase, L.fswing, (swirl + L.seed * 10.0) % 6283.1853, L.hue, *L.m]

    def uniforms(self, t: float) -> np.ndarray:
        P = self.P
        fi = int(min(max(0, round(t * self.fps)), len(self.env["sub"]) - 1))
        e = {k: float(v[fi]) for k, v in self.env.items()}
        kick, k = self.kick(t)
        cam = self.cam(t, k)
        zoom = self._curve(P.zoom, t)
        swirl = self._curve(P.swirl, t)
        clock = self._curve(P.clock, t)
        calm = self._curve(P.calm, t)
        build = self._curve(P.build, t)
        A, B, x, kind = planner.span_at(P, t)
        bl = planner._ease(x) if B is not None else 0.0
        if kind == planner.COLLAPSE:
            bl = x
        la = self._look(A, t, cam, zoom, swirl, build)
        lb = self._look(B if B is not None else A, t, cam, zoom, swirl, build)
        ctr = (0.0, 0.0)
        if B is not None and kind == planner.IRIS:
            h = planner.h01(self.seed, B.seed, B.eoff, "iris")
            ctr = (0.9 * math.cos(h * 6.283), 0.45 * math.sin(h * 6.283))
        # pops: the flash and ring of a drop (and the very last bubble)
        age, pst = -1.0, 0.0
        if len(self.pops):
            j = int(np.searchsorted(self.pops, t + 1.0 / self.fps - 1e-6, side="right") - 1)
            if j >= 0 and t - self.pops[j] < 1.5:
                age, pst = max(0.0, t - self.pops[j]), 1.0
        se, ss = self.surge(t)
        hue = float(np.interp(t, P.key_t, self.key_unwrapped)) if len(P.key_t) else 0.0
        light = planner.light_rgb(hue, self.key_light)
        fade = 0.0
        sat = self.sat + 0.25 * build - 0.1 * calm
        exposure = 0.78 * (1.0 + self.pump * kick * (1.0 - calm))
        dbg = self.debug
        lay = self.layers
        if dbg >= 10:                  # isolating one layer: no pump, no bloom, no aberration
            exposure, bloom, ca = 0.78, 0.0, 0.0
        else:
            bloom = self.bloom * (0.8 + 0.5 * e["loud"])
            ca = self.aberr * (0.25 + 1.1 * e["bass"] + 0.6 * kick)
        v = [self.size[0], self.size[1], 2.0 / self.size[1], self.size[0] / self.size[1],
             clock, 0.0, 0.0, float(round(t * self.fps)),
             kick, e["sub"], e["bass"], e["lowmid"],
             e["highmid"], e["high"], e["loud"], calm,
             *la, *lb,
             bl, float(kind), *ctr,
             age, pst, se, ss,
             *light, sat,
             exposure, ca, 0.32, bloom,
             float(1 if dbg == 1 else 0), 0.0, fade, self.film_strength,
             *lay,
             *self.pal[:4], *self.pal[4:],
             build, float(self.force_elem), self.punch, 0.0]
        return np.array(v, np.float32)

    def isolate(self, layer: str | None):
        """Draw only one layer (film, border, interior, sparkle) for the band-response checks; None restores."""
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
