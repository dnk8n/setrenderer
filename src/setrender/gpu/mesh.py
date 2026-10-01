"""Low-poly mesh builders. Every mesh is (verts (n,12): pos3 nrm3 uv2 rgba4, indices (m,))."""
from __future__ import annotations

import math

import numpy as np


def _v(p, n, uv, c):
    return [*p, *n, *uv, *c]


def box(color=(1, 1, 1, 1)):
    """Unit box, x/z in [-0.5, 0.5], y in [0, 1]."""
    faces = [
        ((1, 0, 0), (0, 0, -1), (0, 1, 0)), ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
        ((0, 1, 0), (1, 0, 0), (0, 0, -1)), ((0, -1, 0), (1, 0, 0), (0, 0, 1)),
        ((0, 0, 1), (1, 0, 0), (0, 1, 0)), ((0, 0, -1), (-1, 0, 0), (0, 1, 0)),
    ]
    V, I = [], []
    for n, u, w in faces:
        n, u, w = np.array(n, float), np.array(u, float), np.array(w, float)
        c0 = n * 0.5 + np.array([0, 0.5, 0])
        base = len(V)
        for (a, b) in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            p = c0 + u * 0.5 * a + w * 0.5 * b
            V.append(_v(p, n, ((a + 1) / 2, (b + 1) / 2), color))
        I += [base, base + 1, base + 2, base, base + 2, base + 3]
    return np.array(V, np.float32), np.array(I, np.uint32)


def cylinder(n=12, color=(1, 1, 1, 1), caps=True, r_top=0.5, r_bot=0.5):
    V, I = [], []
    for k in range(n + 1):
        a = k / n * 2 * math.pi
        ca, sa = math.cos(a), math.sin(a)
        nr = np.array([ca, (r_bot - r_top), sa])
        nr /= np.linalg.norm(nr)
        V.append(_v((r_bot * ca, 0, r_bot * sa), nr, (k / n, 0), color))
        V.append(_v((r_top * ca, 1, r_top * sa), nr, (k / n, 1), color))
    for k in range(n):
        a, b = 2 * k, 2 * k + 2
        I += [a, b, b + 1, a, b + 1, a + 1]
    if caps:
        for y, r, ny in ((1, r_top, 1), (0, r_bot, -1)):
            c = len(V)
            V.append(_v((0, y, 0), (0, ny, 0), (0.5, 0.5), color))
            for k in range(n):
                a = k / n * 2 * math.pi
                V.append(_v((r * math.cos(a), y, r * math.sin(a)), (0, ny, 0),
                            (0.5 + 0.5 * math.cos(a), 0.5 + 0.5 * math.sin(a)), color))
            for k in range(n):
                I += [c, c + 1 + k, c + 1 + (k + 1) % n]
    return np.array(V, np.float32), np.array(I, np.uint32)


def icosphere(sub=1, color=(1, 1, 1, 1), flat=True):
    t = (1 + 5 ** 0.5) / 2
    P = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
         (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    P = [np.array(p, float) / np.linalg.norm(p) for p in P]
    F = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6),
         (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10),
         (8, 6, 7), (9, 8, 1)]
    for _ in range(sub):
        cache = {}

        def mid(a, b):
            key = (min(a, b), max(a, b))
            if key not in cache:
                m = P[a] + P[b]
                P.append(m / np.linalg.norm(m))
                cache[key] = len(P) - 1
            return cache[key]
        nf = []
        for a, b, c in F:
            ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
            nf += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        F = nf
    V, I = [], []
    for a, b, c in F:
        pa, pb, pc = P[a] * 0.5, P[b] * 0.5, P[c] * 0.5
        if flat:
            n = np.cross(pb - pa, pc - pa)
            n /= np.linalg.norm(n)
            if np.dot(n, pa) < 0:
                n = -n
            ns = (n, n, n)
        else:
            ns = (P[a], P[b], P[c])
        base = len(V)
        for p, n in zip((pa, pb, pc), ns):
            V.append(_v(p, n, (0.5 + p[0], 0.5 + p[1]), color))
        I += [base, base + 1, base + 2]
    return np.array(V, np.float32), np.array(I, np.uint32)


def bell(n=16, rings=7, color=(1, 1, 1, 1)):
    """Jellyfish bell: dome from y=1 (top) to a flared rim at y=0, radius ~0.5, open underneath."""
    prof = []
    for r in range(rings + 1):
        s = r / rings
        y = 1 - s
        rad = 0.5 * math.sin(min(1.0, s * 1.25) * math.pi / 2) + 0.06 * max(0, s - 0.8) / 0.2
        prof.append((rad, y))
    V, I = [], []
    for k in range(n + 1):
        a = k / n * 2 * math.pi
        for r, (rad, y) in enumerate(prof):
            nr = np.array([math.cos(a) * (y + 0.2), rad + 0.2, math.sin(a) * (y + 0.2)])
            nr /= np.linalg.norm(nr) + 1e-9
            V.append(_v((rad * math.cos(a), y, rad * math.sin(a)), nr, (k / n, y), color))
    m = rings + 1
    for k in range(n):
        for r in range(rings):
            a, b = k * m + r, (k + 1) * m + r
            I += [a, b, b + 1, a, b + 1, a + 1]
    return np.array(V, np.float32), np.array(I, np.uint32)


def prism(color=(1, 1, 1, 1)):
    """Triangular prism (roof): base y=0 spanning x in [-0.5,0.5], ridge at y=1, z in [-0.5,0.5]."""
    b = Builder()
    tri = [(-0.5, 0), (0.5, 0), (0, 1)]
    for z, nz in ((0.5, 1), (-0.5, -1)):
        base = len(b.V)
        for x, y in tri:
            b.V.append(_v((x, y, z), (0, 0, nz), (x + 0.5, y), color))
        b.I += [base, base + 1, base + 2] if nz > 0 else [base, base + 2, base + 1]
    for (x0, y0), (x1, y1) in ((tri[0], tri[2]), (tri[2], tri[1]), (tri[1], tri[0])):
        n = np.array([y1 - y0, -(x1 - x0), 0.0])
        n = -n / (np.linalg.norm(n) + 1e-9) if (x0 + x1) * n[0] + (y0 + y1) * n[1] - 0.66 * n[1] < 0 else n / (np.linalg.norm(n) + 1e-9)
        base = len(b.V)
        for (x, y, z, u, v) in ((x0, y0, -0.5, 0, 0), (x1, y1, -0.5, 1, 0), (x1, y1, 0.5, 1, 1), (x0, y0, 0.5, 0, 1)):
            b.V.append(_v((x, y, z), n, (u, v), color))
        b.I += [base, base + 1, base + 2, base, base + 2, base + 3]
    return b.build()


def pennant(color=(1, 1, 1, 1)):
    """Bunting triangle: top edge x in [0,1] at y=0, tip at (0.5,1); scale y negative to hang it."""
    V = [_v((0, 0, 0), (0, 0, 1), (0, 1), color), _v((1, 0, 0), (0, 0, 1), (1, 1), color),
         _v((0.5, 1, 0), (0, 0, 1), (0.5, 0), color)]
    return np.array(V, np.float32), np.array([0, 1, 2], np.uint32)


def plane_xy(nx=1, ny=1, color=(1, 1, 1, 1)):
    """x in [0,1], y in [0,1], z = 0, facing +z."""
    V, I = [], []
    for j in range(ny + 1):
        for i in range(nx + 1):
            V.append(_v((i / nx, j / ny, 0), (0, 0, 1), (i / nx, j / ny), color))
    for j in range(ny):
        for i in range(nx):
            a = j * (nx + 1) + i
            I += [a, a + 1, a + nx + 2, a, a + nx + 2, a + nx + 1]
    return np.array(V, np.float32), np.array(I, np.uint32)


def plane_xy_centered(color=(1, 1, 1, 1)):
    v, i = plane_xy(1, 1, color)
    v[:, 0] -= 0.5
    v[:, 1] -= 0.5
    return v, i


def _quad_strip(b, p0, p1, w0, w1, side, color, n=None):
    side = np.asarray(side, float)
    if n is None:
        n = np.cross(np.asarray(p1, float) - np.asarray(p0, float), side)
        n /= np.linalg.norm(n) + 1e-9
    base = len(b.V)
    for p in (np.asarray(p0) - side * w0, np.asarray(p0) + side * w0, np.asarray(p1) + side * w1, np.asarray(p1) - side * w1):
        b.V.append(_v(p, n, (0, p[1]), color))
    b.I += [base, base + 1, base + 2, base, base + 2, base + 3]


def corn(color_stalk=(0.32, 0.45, 0.14, 1), color_leaf=(0.36, 0.52, 0.16, 1), lod=0):
    """Corn plant, base at origin, height 1 (instance scales to ~2.2 m). lod=1 is a cheap far version."""
    b = Builder()
    # stalk: two crossed quads
    for side in ((1, 0, 0), (0, 0, 1)):
        _quad_strip(b, (0, 0, 0), (0, 1.0, 0), 0.025, 0.015, side, color_stalk)
    leaves = [(0.28, 0.0), (0.42, 2.3), (0.55, 4.4), (0.68, 1.1), (0.8, 3.3)] if lod == 0 else [(0.4, 0.6), (0.62, 3.6)]
    for k, (h, a) in enumerate(leaves):
        L = 0.42 - 0.04 * k
        ca, sa = math.cos(a), math.sin(a)
        p0 = np.array([0, h, 0])
        p1 = np.array([ca * L * 0.55, h + 0.16, sa * L * 0.55])
        p2 = np.array([ca * L, h + 0.02, sa * L])
        side = np.array([-sa, 0, ca]) * 0.045
        n = np.cross(p1 - p0, side)
        n /= np.linalg.norm(n) + 1e-9
        base = len(b.V)
        for p in (p0 - side, p0 + side, p1 + side * 0.6, p1 - side * 0.6, p2):
            b.V.append(_v(p, n, (0, p[1]), color_leaf))
        b.I += [base, base + 1, base + 2, base, base + 2, base + 3, base + 3, base + 2, base + 4]
    if lod == 0:
        # cob and tassel as crossed quads
        for side in ((1, 0, 0), (0, 0, 1)):
            _quad_strip(b, (0.05, 0.45, 0), (0.09, 0.66, 0), 0.035, 0.025, side, (0.85, 0.72, 0.25, 1))
        for a in (0.4, 2.0):
            _quad_strip(b, (0, 0.97, 0), (0.12 * math.cos(a), 1.1, 0.12 * math.sin(a)), 0.012, 0.004, (math.sin(a), 0, -math.cos(a)), (0.78, 0.66, 0.35, 1))
    return b.build()


def terrain(size=600.0, n=160, flat_r=70.0, seed=3, color=(1, 1, 1, 1)):
    """Grid centred on the origin; flat festival area, rolling hills beyond."""
    rng = np.random.default_rng(seed)
    xs = np.linspace(-size / 2, size / 2, n + 1)
    X, Z = np.meshgrid(xs, xs)
    Hh = np.zeros_like(X)
    for k in range(6):
        f = 0.004 * (2 ** k) * (0.8 + 0.4 * rng.random())
        ph = rng.random(2) * 100
        Hh += (22 / (1.9 ** k)) * np.sin(X * f + ph[0]) * np.cos(Z * f * 1.13 + ph[1])
    r = np.hypot(X, Z)
    w = np.clip((r - flat_r) / 120, 0, 1) ** 2
    Y = (Hh + 14) * w
    # normals
    dx = np.gradient(Y, xs, axis=1)
    dz = np.gradient(Y, xs, axis=0)
    N = np.stack([-dx, np.ones_like(Y), -dz], -1)
    N /= np.linalg.norm(N, axis=-1, keepdims=True)
    V = np.zeros(((n + 1) ** 2, 12), np.float32)
    V[:, 0], V[:, 1], V[:, 2] = X.ravel(), Y.ravel(), Z.ravel()
    V[:, 3:6] = N.reshape(-1, 3)
    V[:, 6] = (X.ravel() / size + 0.5)
    V[:, 7] = (Z.ravel() / size + 0.5)
    V[:, 8:12] = color
    I = []
    for j in range(n):
        for i in range(n):
            a = j * (n + 1) + i
            I += [a, a + n + 1, a + n + 2, a, a + n + 2, a + 1]
    return V, np.array(I, np.uint32), (xs, Y)


def height_at(tinfo, x, z):
    xs, Y = tinfo
    fx = np.interp(x, xs, np.arange(len(xs)))
    fz = np.interp(z, xs, np.arange(len(xs)))
    i, j = int(np.clip(fx, 0, len(xs) - 2)), int(np.clip(fz, 0, len(xs) - 2))
    u, v = fx - i, fz - j
    return float((Y[j, i] * (1 - u) + Y[j, i + 1] * u) * (1 - v) + (Y[j + 1, i] * (1 - u) + Y[j + 1, i + 1] * u) * v)


# ---------------------------------------------------------------- composition

def affine(t=(0, 0, 0), scale=(1, 1, 1), rot=(0, 0, 0)) -> np.ndarray:
    """3x4 affine: scale, then rotate (x, y, z Euler radians, applied z then x then y), then translate."""
    rx, ry, rz = rot
    cx, sx, cy, sy, cz, sz = math.cos(rx), math.sin(rx), math.cos(ry), math.sin(ry), math.cos(rz), math.sin(rz)
    Rx = np.array([[1, 0, 0], [0, cx, -sx], [0, sx, cx]])
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    Rz = np.array([[cz, -sz, 0], [sz, cz, 0], [0, 0, 1]])
    R = Ry @ Rx @ Rz
    M = np.zeros((3, 4))
    M[:, :3] = R * np.array(scale)[None, :]
    M[:, 3] = t
    return M


class Builder:
    def __init__(self):
        self.V: list = []
        self.I: list = []

    def add(self, v, i, m=None, color=None):
        v = np.array(v, np.float64)
        if m is not None:
            p = v[:, 0:3] @ m[:, :3].T + m[:, 3]
            n = v[:, 3:6] @ m[:, :3].T
            n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
            v[:, 0:3], v[:, 3:6] = p, n
        if color is not None:
            v[:, 8:12] = color
        base = len(self.V)
        self.V.extend(v.tolist())
        self.I.extend((np.asarray(i) + base).tolist())
        return self

    def build(self):
        return np.array(self.V, np.float32), np.array(self.I, np.uint32)


def inst(m: np.ndarray, tint=(1, 1, 1), mat=0, emis=(0, 0, 0), sway=0.0, extra=(0, 0, 0, 0)) -> np.ndarray:
    """One mesh instance row (24 floats)."""
    out = np.zeros(24, np.float32)
    out[0:12] = m.reshape(-1)
    out[12:15] = tint
    out[15] = mat
    out[16:19] = emis
    out[19] = sway
    out[20:24] = extra
    return out


def inst_many(M: np.ndarray, tint, mat, emis=None, sway=None, extra=None) -> np.ndarray:
    """Vectorised instances: M (k,3,4); tint (k,3) or (3,)."""
    k = len(M)
    out = np.zeros((k, 24), np.float32)
    out[:, 0:12] = M.reshape(k, 12)
    out[:, 12:15] = tint
    out[:, 15] = mat
    if emis is not None:
        out[:, 16:19] = emis
    if sway is not None:
        out[:, 19] = sway
    if extra is not None:
        out[:, 20:24] = extra
    return out


def trs_many(t: np.ndarray, s: np.ndarray, yaw: np.ndarray) -> np.ndarray:
    """(k,3) translations, (k,3) scales, (k,) yaw -> (k,3,4) affine."""
    k = len(t)
    c, sn = np.cos(yaw), np.sin(yaw)
    M = np.zeros((k, 3, 4), np.float32)
    M[:, 0, 0], M[:, 0, 2] = c * s[:, 0], sn * s[:, 2]
    M[:, 1, 1] = s[:, 1]
    M[:, 2, 0], M[:, 2, 2] = -sn * s[:, 0], c * s[:, 2]
    M[:, :, 3] = t
    return M
