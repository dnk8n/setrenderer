"""Primitive builder: shapes in painter's order with a transform stack, shared outlines for groups
and per-object seeds, packed into the (n, 32) float rows the GPU engine draws.

Row layout (see shaders.PRIM):
  0 a.x a.y b.x b.y | 4 c.x c.y r0 r1 | 8 fill rgba | 12 ink rgb, ink width
  16 type soft shade boil | 20 material p0 p1 rot | 24 dilate band seed fade | 28 fill2 rgba
"""
from __future__ import annotations

import math
from contextlib import contextmanager

import numpy as np

ELLIPSE, CAPSULE, BEZIER, BOX, PIE, STAR, TRI, ARC, HEART, RAYS, RINGS, WAVE = range(12)
CEL, WATER, GLOW = 0.0, 1.0, 2.0

INK = (0.12, 0.085, 0.07)
NONE4 = (0.0, 0.0, 0.0, 0.0)


def rgb(h: str, a: float = 1.0) -> tuple:
    h = h.lstrip("#")
    return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, a)


def mix(c1, c2, t: float) -> tuple:
    return tuple(x + (y - x) * t for x, y in zip(c1, c2))


def shade(c, k: float) -> tuple:
    """k < 0 darkens, k > 0 lightens towards cream."""
    if k < 0:
        return (c[0] * (1 + k), c[1] * (1 + k), c[2] * (1 + k * 1.05), c[3] if len(c) > 3 else 1.0)
    return mix(c if len(c) > 3 else (*c, 1.0), (0.98, 0.95, 0.86, c[3] if len(c) > 3 else 1.0), k)


class Ink:
    def __init__(self, boil: float = 1.0, line: float = 1.0):
        self.rows: list[list] = []
        self.m = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)      # x' = a x + c y + e ; y' = b x + d y + f
        self._stack: list = []
        self.ink = INK
        self.boil = boil
        self.line = line          # global line-weight multiplier
        self.fade = 0.0           # 0 = opaque, 1 = invisible
        self.soft = 0.0           # extra blur (depth of field)
        self.mat = CEL
        self._seed = 0.0
        self._n = 0

    # ------------------------------------------------------------------ state
    @contextmanager
    def at(self, x=0.0, y=0.0, rot=0.0, sx=1.0, sy=None, *, fade=None, soft=None, seed=None, mat=None,
           ink=None, boil=None):
        """Push a local frame: translate, rotate, then scale (scale applies first to local shapes)."""
        sy = sx if sy is None else sy
        saved = (self.m, self.fade, self.soft, self._seed, self._n, self.mat, self.ink, self.boil)
        a, b, c, d, e, f = self.m
        cr, sr = math.cos(rot), math.sin(rot)
        # local matrix L = R * S ; new = M * L
        la, lb, lc, ld = cr * sx, sr * sx, -sr * sy, cr * sy
        self.m = (a * la + c * lb, b * la + d * lb, a * lc + c * ld, b * lc + d * ld,
                  a * x + c * y + e, b * x + d * y + f)
        if fade is not None:
            self.fade = 1 - (1 - self.fade) * (1 - fade)
        if soft is not None:
            self.soft = self.soft + soft
        if seed is not None:
            self._seed, self._n = float(seed % 997), 0
        if mat is not None:
            self.mat = mat
        if ink is not None:
            self.ink = ink
        if boil is not None:
            self.boil = boil
        try:
            yield self
        finally:
            self.m, self.fade, self.soft, self._seed, self._n, self.mat, self.ink, self.boil = saved

    @contextmanager
    def outlined(self, w: float = 4.0, ink=None):
        """Everything drawn inside shares one outline: silhouettes in ink (dilated), then fills."""
        start = len(self.rows)
        yield self
        rows = self.rows[start:]
        del self.rows[start:]
        s = self.scale()
        ic = ink or self.ink
        ww = w * s * self.line
        for r in rows:
            if r[16] in (RAYS, RINGS) or r[20] == GLOW:
                continue
            o = list(r)
            o[8:12] = (ic[0], ic[1], ic[2], 1.0)
            o[12:16] = (0.0, 0.0, 0.0, 0.0)
            o[18] = 0.0
            o[24] = r[24] + ww
            o[28:32] = NONE4
            self.rows.append(o)
        for r in rows:
            r[15] = 0.0
            self.rows.append(r)

    def scale(self) -> float:
        a, b, c, d, _, _ = self.m
        return math.sqrt(abs(a * d - b * c))

    def tp(self, x, y):
        a, b, c, d, e, f = self.m
        return a * x + c * y + e, b * x + d * y + f

    def _rot(self) -> float:
        return math.atan2(self.m[1], self.m[0])

    def _row(self, ty, a, b, c, r0, r1, fill, ink, w, shade, mat, p0, p1, rot, soft, boil, fill2,
             dilate=0.0, band=0.0, seed=None):
        self._n += 1
        sd = self._seed * 13.7 + self._n * 1.618 if seed is None else seed
        f = fill if len(fill) == 4 else (*fill, 1.0)
        f2 = NONE4 if fill2 is None else (fill2 if len(fill2) == 4 else (*fill2, 1.0))
        self.rows.append([a[0], a[1], b[0], b[1], c[0], c[1], r0, r1,
                          f[0], f[1], f[2], f[3], ink[0], ink[1], ink[2], w,
                          float(ty), soft + self.soft, shade, self.boil * boil,
                          self.mat if mat is None else mat, p0, p1, rot,
                          dilate, band, sd, self.fade, f2[0], f2[1], f2[2], f2[3]])

    def _w(self, ink):
        if ink is None or ink is False:
            return 0.0
        return float(ink) * self.scale() * self.line

    # ------------------------------------------------------------------ shapes (local coordinates)
    def ellipse(self, x, y, rx, ry=None, fill=(1, 1, 1, 1), ink=3.0, rot=0.0, shade=0.5, fill2=None, mat=None,
                soft=0.0, boil=1.0, ink_col=None, seed=None):
        ry = rx if ry is None else ry
        a, b, c, d, _, _ = self.m
        cr, sr = math.cos(rot), math.sin(rot)
        ux, uy = (a * cr + c * sr) * rx, (b * cr + d * sr) * rx
        vx, vy = (-a * sr + c * cr) * ry, (-b * sr + d * cr) * ry
        r0, r1 = math.hypot(ux, uy), math.hypot(vx, vy)
        ang = math.atan2(uy, ux)
        self._row(ELLIPSE, self.tp(x, y), (0, 0), (0, 0), r0, r1, fill, ink_col or self.ink, self._w(ink), shade,
                  mat, 0.0, 0.0, ang, soft, boil, fill2, seed=seed)

    circle = ellipse

    def capsule(self, x0, y0, x1, y1, r0, r1=None, fill=(1, 1, 1, 1), ink=3.0, shade=0.4, fill2=None, mat=None,
                soft=0.0, boil=1.0, ink_col=None, seed=None):
        s = self.scale()
        r1 = r0 if r1 is None else r1
        self._row(CAPSULE, self.tp(x0, y0), self.tp(x1, y1), (0, 0), r0 * s, r1 * s, fill, ink_col or self.ink,
                  self._w(ink), shade, mat, 0.0, 0.0, 0.0, soft, boil, fill2, seed=seed)

    def bez(self, x0, y0, cx, cy, x1, y1, r0, r1=None, fill=(1, 1, 1, 1), ink=3.0, shade=0.4, fill2=None,
            mat=None, soft=0.0, boil=1.0, ink_col=None, seed=None):
        s = self.scale()
        r1 = r0 if r1 is None else r1
        a, c = self.tp(x0, y0), self.tp(x1, y1)
        b = self.tp(cx, cy)
        self._row(BEZIER, a, b, c, r0 * s, r1 * s, fill, ink_col or self.ink, self._w(ink), shade, mat,
                  0.0, 0.0, 0.0, soft, boil, fill2, seed=seed)

    def box(self, x, y, hw, hh, r=0.0, fill=(1, 1, 1, 1), ink=3.0, rot=0.0, shade=0.3, fill2=None, mat=None,
            soft=0.0, boil=1.0, ink_col=None, seed=None):
        a, b, c, d, _, _ = self.m
        sx, sy = math.hypot(a, b), math.hypot(c, d)
        self._row(BOX, self.tp(x, y), (hw * sx, hh * sy), (0, 0), r * min(sx, sy), 0.0, fill, ink_col or self.ink,
                  self._w(ink), shade, mat, 0.0, 0.0, rot + self._rot(), soft, boil, fill2, seed=seed)

    def pie(self, x, y, rx, ry, cut=0.6, half=0.35, fill=INK, ink=0.0, rot=0.0, soft=0.0, boil=1.0):
        a, b, c, d, _, _ = self.m
        sx, sy = math.hypot(a, b), math.hypot(c, d)
        self._row(PIE, self.tp(x, y), (0, 0), (0, 0), rx * sx, ry * sy, fill, self.ink, self._w(ink), 0.0, CEL,
                  cut, half, rot + self._rot(), soft, boil, None)

    def star(self, x, y, r, n=5, m=None, fill=(1, 1, 1, 1), ink=3.0, rot=0.0, shade=0.2, fill2=None, mat=None,
             soft=0.0, boil=1.0, ink_col=None):
        m = n * 0.45 if m is None else m
        self._row(STAR, self.tp(x, y), (0, 0), (0, 0), r * self.scale(), 0.0, fill, ink_col or self.ink,
                  self._w(ink), shade, mat, float(n), float(max(2.0, m)), rot + self._rot(), soft, boil, fill2)

    def tri(self, p0, p1, p2, fill=(1, 1, 1, 1), ink=3.0, rnd=0.0, shade=0.2, mat=None, soft=0.0, boil=1.0,
            fill2=None, ink_col=None):
        self._row(TRI, self.tp(*p0), self.tp(*p1), self.tp(*p2), rnd * self.scale(), 0.0, fill,
                  ink_col or self.ink, self._w(ink), shade, mat, 0.0, 0.0, 0.0, soft, boil, fill2)

    def arc(self, x, y, r, thick, half, rot=0.0, fill=INK, ink=0.0, soft=0.0, boil=1.0, mat=None):
        """Arc stroke centred on angle `rot` (0 = pointing down/+y), half-aperture `half` radians."""
        s = self.scale()
        self._row(ARC, self.tp(x, y), (0, 0), (0, 0), r * s, thick * s, fill, self.ink, self._w(ink), 0.0, mat,
                  half, 0.0, rot + self._rot(), soft, boil, None)

    def heart(self, x, y, size, fill=(0.9, 0.3, 0.4, 1), ink=3.0, rot=0.0, shade=0.3, soft=0.0, mat=None):
        self._row(HEART, self.tp(x, y), (0, 0), (0, 0), size * self.scale(), 0.0, fill, self.ink, self._w(ink),
                  shade, mat, 0.0, 0.0, rot + self._rot(), soft, 1.0, None)

    def rays(self, x, y, n, c1, c2, duty=0.5, phase=0.0, radius=0.0, mat=None):
        self._row(RAYS, self.tp(x, y), (0, 0), (0, 0), 0.0, radius * self.scale(), c1, self.ink, 0.0, 0.0, mat,
                  float(n), duty, phase, 0.0, 0.0, c2)

    def rings(self, x, y, width, c1, c2, duty=0.5, phase=0.0, radius=0.0, mat=None):
        self._row(RINGS, self.tp(x, y), (0, 0), (0, 0), width * self.scale(), radius * self.scale(), c1, self.ink,
                  0.0, 0.0, mat, 0.0, duty, phase, 0.0, 0.0, c2)

    def wave(self, y, amp, wavelength, phase, fill, x0=-60.0, x1=1980.0, bottom=1140.0, ink=0.0, fill2=None,
             mat=None, shade=0.0, soft=0.0, boil=0.0, seed=None):
        """A band filled below a wavy line (hills, water, ground). Screen space, no transform."""
        self._row(WAVE, (0.0, y), (x0, bottom), (x1, 0.0), amp, wavelength, fill, self.ink, self._w(ink), shade,
                  mat, phase, 0.0, 0.0, soft, boil, fill2, seed=seed)

    def glow(self, x, y, r, col, soft=30.0, ry=None):
        self.ellipse(x, y, r, ry, fill=col, ink=0.0, shade=0.0, mat=GLOW, soft=soft * self.scale(), boil=0.0)

    def line(self, pts, w=3.0, col=None, boil=1.0):
        """A plain ink stroke through points (capsules)."""
        col = col or self.ink
        for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
            self.capsule(x0, y0, x1, y1, w * 0.5, fill=col, ink=0.0, shade=0.0, boil=boil)

    # ------------------------------------------------------------------ output
    def array(self) -> np.ndarray:
        if not self.rows:
            return np.zeros((0, 32), np.float32)
        return np.asarray(self.rows, np.float32)
