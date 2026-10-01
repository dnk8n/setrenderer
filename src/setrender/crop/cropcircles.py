"""Crop-circle patterns pressed into the cornfield over the night.

Each pattern is rasterised into a shared RGBA8 map over the field: R = drawing order (0..1, so a
pattern is laid down progressively), G = pattern id, B = swirl direction, A = mask. The vertex
shader lays a stalk down once the set clock passes start + order * duration for its pattern.
"""
from __future__ import annotations

import math

import numpy as np

KINDS = ["rings", "julia", "flower", "triskelion", "invader", "smiley", "rosette", "pacman", "arecibo", "yinyang"]

INVADER = [0x104, 0x088, 0x1FC, 0x376, 0x7FF, 0x5FD, 0x505, 0x0D8]
ARECIBO = [0x0A8, 0x154, 0x2AA, 0x000, 0x1FF, 0x101, 0x17D, 0x145, 0x17D, 0x101, 0x1FF, 0x000, 0x038, 0x07C,
           0x0FE, 0x038, 0x044, 0x082]


def _pattern(kind: str, X: np.ndarray, Z: np.ndarray, R: float, sym: int, rng) -> tuple[np.ndarray, np.ndarray]:
    """Local coords X,Z in metres (centre 0,0). Returns (mask bool, order 0..1)."""
    r = np.hypot(X, Z)
    a = np.arctan2(Z, X)
    an = (a + math.pi) / (2 * math.pi)
    m = np.zeros_like(X, bool)
    order = np.clip(r / R, 0, 1)
    if kind == "rings":
        n = 3 + sym % 3
        w = R / (2 * n + 1)
        m = (r < w) | ((np.floor(r / w) % 2 == 0) & (r < R) & (np.abs(Z) > w * 0.35))
        order = np.clip(r / R, 0, 1)
    elif kind == "julia":   # the 1996 Stonehenge "Julia set": a spiral of shrinking circles
        m = r < R * 0.22
        order = np.zeros_like(r)
        n = 30
        for k in range(n):
            th = k * 0.42 + 0.3
            rr = R * 0.25 + k * R * 0.028
            cr = R * 0.12 * (1 - k / n) + 0.4
            cx, cz = rr * math.cos(th), rr * math.sin(th)
            hit = np.hypot(X - cx, Z - cz) < cr
            order = np.where(hit & ~m, (k + 1) / (n + 1), order)
            m |= hit
    elif kind == "flower":  # flower of life
        rc = R / 2.2
        m = np.hypot(X, Z) < rc
        for k in range(6):
            th = k * math.pi / 3
            m ^= np.hypot(X - rc * math.cos(th), Z - rc * math.sin(th)) < rc
        m |= np.abs(r - R * 0.97) < 0.6
        order = an
    elif kind == "triskelion":
        sp = np.mod(a * 3 / (2 * math.pi) * 3 - np.log(r + 1) * 2.2, 3.0)
        m = (sp < 1.0) & (r < R) | (r < R * 0.12)
        order = an
    elif kind in ("invader", "arecibo", "smiley", "pacman"):
        if kind in ("invader", "arecibo"):
            rows = INVADER if kind == "invader" else ARECIBO
            gw = 11 if kind == "invader" else 9
            gh = len(rows)
            cell = 2 * R / max(gw, gh)
            gx = np.floor(X / cell + gw / 2).astype(int)
            gz = np.floor(Z / cell + gh / 2).astype(int)
            ok = (gx >= 0) & (gx < gw) & (gz >= 0) & (gz < gh)
            bits = np.zeros_like(ok)
            for y, row in enumerate(rows):
                for x in range(gw):
                    if (row >> (gw - 1 - x)) & 1:
                        bits |= ok & (gx == x) & (gz == y)
            m = bits
            order = np.clip((gz + gx / gw) / gh, 0, 1)
        elif kind == "smiley":
            m = (r < R) & ~((np.hypot(X + R * 0.35, Z + R * 0.3) < R * 0.13) | (np.hypot(X - R * 0.35, Z + R * 0.3) < R * 0.13))
            mouth = (np.abs(r - R * 0.55) < R * 0.08) & (Z > R * 0.15)
            m &= ~mouth
            order = an
        else:
            mouth = (np.abs(a) < 0.6)
            m = (r < R * 0.7) & ~mouth
            for k in range(4):
                m |= np.hypot(X - R * (0.95 + k * 0.45), Z) < R * 0.12
            order = np.clip((X + R) / (3 * R), 0, 1)
    elif kind == "rosette":
        petal = np.abs(np.sin(a * sym / 2)) * R
        m = (r < petal) | (r < R * 0.15) | (np.abs(r - R * 1.02) < 0.5)
        order = an
    elif kind == "yinyang":
        top = Z < 0
        dot1 = np.hypot(X, Z + R / 2) < R / 2
        dot2 = np.hypot(X, Z - R / 2) < R / 2
        m = (r < R) & ((top & (X > 0)) | dot1) & ~dot2
        m |= np.hypot(X, Z - R / 2) < R * 0.1
        m |= np.abs(r - R) < 0.5
        order = an
    return m, np.clip(order, 0, 1)


class CropField:
    def __init__(self, rect=(-80.0, -50.0, 160.0, 150.0), res=512):
        self.rect = rect
        self.res = res
        self.img = np.zeros((res, res, 4), np.uint8)
        self.params = np.zeros((64, 4), np.float32)
        self.patterns: list[dict] = []
        x0, z0, w, h = rect
        self.xs = x0 + (np.arange(res) + 0.5) * w / res
        self.zs = z0 + (np.arange(res) + 0.5) * h / res

    def add(self, kind: str, cx: float, cz: float, R: float, rot: float, start: float, dur: float, sym: int, rng) -> dict:
        pid = len(self.patterns) + 1
        x0, z0, w, h = self.rect
        ix0 = int(max(0, (cx - R * 3.2 - x0) / w * self.res))
        ix1 = int(min(self.res, (cx + R * 3.2 - x0) / w * self.res + 1))
        iz0 = int(max(0, (cz - R * 1.6 - z0) / h * self.res))
        iz1 = int(min(self.res, (cz + R * 1.6 - z0) / h * self.res + 1))
        X, Z = np.meshgrid(self.xs[ix0:ix1] - cx, self.zs[iz0:iz1] - cz)
        c, s = math.cos(rot), math.sin(rot)
        Xr, Zr = X * c + Z * s, -X * s + Z * c
        m, order = _pattern(kind, Xr, Zr, R, sym, rng)
        sub = self.img[iz0:iz1, ix0:ix1]
        free = sub[:, :, 3] == 0
        m &= free
        sub[m, 0] = (order[m] * 255).astype(np.uint8)
        sub[m, 1] = pid
        swirl = (np.arctan2(Z, X) + math.pi / 2 + (0.3 if kind != "invader" else -math.pi / 2)) % (2 * math.pi)
        sub[m, 2] = (swirl[m] / (2 * math.pi) * 255).astype(np.uint8)
        sub[m, 3] = 255
        self.params[pid] = (start, dur, 0, 0)
        p = {"pid": pid, "kind": kind, "cx": cx, "cz": cz, "R": R, "start": start, "dur": dur}
        self.patterns.append(p)
        return p

    def mask_at(self, x: np.ndarray, z: np.ndarray) -> np.ndarray:
        x0, z0, w, h = self.rect
        ix = np.clip(((x - x0) / w * self.res).astype(int), 0, self.res - 1)
        iz = np.clip(((z - z0) / h * self.res).astype(int), 0, self.res - 1)
        return self.img[iz, ix, 3] > 0
