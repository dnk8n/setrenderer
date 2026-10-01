"""Per-frame collector for instances handed to the GPU engine, plus small transform helpers."""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field

import numpy as np

from ..gpu.mesh import affine


def compose(parent: np.ndarray, child: np.ndarray) -> np.ndarray:
    """3x4 affine composition parent * child."""
    out = np.empty((3, 4))
    out[:, :3] = parent[:, :3] @ child[:, :3]
    out[:, 3] = parent[:, :3] @ child[:, 3] + parent[:, 3]
    return out


def apply(m: np.ndarray, p) -> np.ndarray:
    return m[:, :3] @ np.asarray(p, float) + m[:, 3]


def hue(h: float, s: float = 0.8, v: float = 1.0) -> tuple:
    h = h % 1.0
    i = int(h * 6)
    f = h * 6 - i
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    return [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)][i % 6]


def hue_np(h, s=0.8, v=1.0) -> np.ndarray:
    """Vectorised HSV -> RGB for an array of hues; returns (n, 3)."""
    h = np.mod(np.asarray(h, float), 1.0)
    k = np.stack([np.ones_like(h), np.full_like(h, 2 / 3), np.full_like(h, 1 / 3)], -1)
    p = np.abs(np.mod(h[..., None] + k, 1.0) * 6 - 3)
    return v * (1 - s + s * np.clip(p - 1, 0, 1))


@dataclass
class Ctx:
    """Everything a frame builder needs to know about time and music at one video frame."""
    i: int
    t: float                 # clip-local seconds
    T: float                 # absolute seconds into the set
    env: dict                # band envelopes 0..1: sub bass lowmid highmid high onset loudness beat
    beat_phase: float
    beat_idx: int
    bar_idx: int
    bar_frac: float          # 0..1 position within the bar
    bar_env: float
    energy: float            # section energy 0..1
    kick: bool
    bpm: float
    tod: float               # time of day 0..1 over the set
    wind: tuple              # (dx, dz, strength, phase)
    accents: list            # accent colours (0..1 floats)
    section: int
    cam_pos: np.ndarray = None
    cam_right: np.ndarray = None
    events: list = field(default_factory=list)
    night: float = 1.0       # 0 day .. 1 night
    flags_up: list = field(default_factory=list)


class Parts:
    def __init__(self):
        self.mesh: dict[str, list] = defaultdict(list)
        self.jelly: dict[str, list] = defaultdict(list)
        self.sprites: list = []
        self.shadows: list = []
        self.glows: list = []
        self.lights: list = []

    # meshes -------------------------------------------------------
    def m(self, mesh: str, M: np.ndarray, tint=(1, 1, 1), mat=0, emis=(0, 0, 0), sway=0.0, extra=(0, 0, 0, 0)):
        row = np.zeros(24, np.float32)
        row[0:12] = M.reshape(-1)
        row[12:15] = tint
        row[15] = mat
        row[16:19] = emis
        row[19] = sway
        row[20:24] = extra
        self.mesh[mesh].append(row)

    def mm(self, mesh: str, rows: np.ndarray):
        if len(rows):
            self.mesh[mesh].append(np.asarray(rows, np.float32).reshape(-1, 24))

    def j(self, mesh: str, M: np.ndarray, emis, extra=(0, 0, 0, 0)):
        row = np.zeros(24, np.float32)
        row[0:12] = M.reshape(-1)
        row[12:15] = 1
        row[15] = 10
        row[16:19] = emis
        row[20:24] = extra
        self.jelly[mesh].append(row)

    # sprites ------------------------------------------------------
    def sprite(self, pos, w, h, uv, tint=(1, 1, 1), flash=0.0, roll=0.0, anchor=0.0, flip=False):
        u0, v0, u1, v1 = uv
        if flip:
            u0, u1 = u1, u0
        self.sprites.append([pos[0], pos[1], pos[2], roll, w, h, anchor, 0, u0, v0, u1, v1, *tint, flash])

    def sprites_many(self, rows: np.ndarray):
        if len(rows):
            self.sprites.append(np.asarray(rows, np.float32).reshape(-1, 16))

    def shadow(self, x, z, w, d, alpha=0.5, y=0.02):
        self.shadows.append([x, y, z, 0, w, d, 0.5, 1, 0, 0, 0, 0, 0, 0, 0, alpha])

    # glows --------------------------------------------------------
    def dot(self, p, r, col, soft=3.0, mode=0, rot=0.0, uv=(0, 0, 0, 0)):
        self.glows.append([p[0], p[1], p[2], r, 0, 0, 0, rot, col[0], col[1], col[2], 1, mode, soft, 0, 0, *uv])

    def beam(self, p0, p1, w0, w1, col, soft=1.5, fade=0.0):
        self.glows.append([p0[0], p0[1], p0[2], w0, p1[0], p1[1], p1[2], w1, col[0], col[1], col[2], 1, 1, soft, fade, 0, 0, 0, 0, 0])

    def ring(self, p, r, col, width=0.08):
        self.glows.append([p[0], p[1], p[2], r, 0, 0, 0, 0, col[0], col[1], col[2], 1, 4, width, 0, 0, 0, 0, 0, 0])

    def glows_many(self, rows: np.ndarray):
        if len(rows):
            self.glows.append(np.asarray(rows, np.float32).reshape(-1, 20))

    # lights -------------------------------------------------------
    def point(self, p, col, intensity, rng):
        self.lights.append(np.array([*p, rng, *col, intensity, 0, -1, 0, -2.0, 0, 0, 0, 0], np.float32))

    def spot(self, p, d, col, intensity, rng, outer_deg, inner_deg):
        d = np.asarray(d, float)
        d = d / (np.linalg.norm(d) + 1e-9)
        self.lights.append(np.array([*p, rng, *col, intensity, *d, math.cos(math.radians(outer_deg)),
                                     math.cos(math.radians(inner_deg)), 0, 0, 0], np.float32))

    # finalise -----------------------------------------------------
    @staticmethod
    def _stack(lst, width):
        if not lst:
            return np.zeros((0, width), np.float32)
        arrs = [np.asarray(x, np.float32).reshape(-1, width) for x in lst]
        return np.concatenate(arrs)

    def mesh_arrays(self) -> dict:
        return {k: self._stack(v, 24) for k, v in self.mesh.items() if v}

    def jelly_arrays(self) -> dict:
        return {k: self._stack(v, 24) for k, v in self.jelly.items() if v}

    def sprite_array(self):
        return self._stack(self.sprites, 16)

    def shadow_array(self):
        return self._stack(self.shadows, 16)

    def glow_array(self):
        return self._stack(self.glows, 20)


def A(t=(0, 0, 0), s=(1, 1, 1), r=(0, 0, 0)):
    return affine(t, s, r)
