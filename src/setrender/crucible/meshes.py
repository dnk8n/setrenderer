"""Meshes for the 3D trials (unit size, centred, white: instances carry the colour). Vertex layout:
position, normal, colour (10 floats)."""
from __future__ import annotations

import numpy as np


def _flat(tris: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(n, 3, 3) triangles -> flat-shaded vertices and indices."""
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    v = np.zeros((len(tris) * 3, 10), np.float32)
    v[:, 0:3] = tris.reshape(-1, 3)
    v[:, 3:6] = np.repeat(n, 3, axis=0)
    v[:, 6:10] = 1.0
    return v, np.arange(len(v), dtype=np.uint32)


def cube():
    c = np.array([[x, y, z] for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)], np.float32)
    faces = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    tris = []
    for a, b, cc, d in faces:
        tris += [(c[a], c[b], c[cc]), (c[a], c[cc], c[d])]
    return _flat(np.array(tris, np.float32))


def sphere(sub: int = 2):
    t = (1 + 5 ** 0.5) / 2
    v = [(-1, t, 0), (1, t, 0), (-1, -t, 0), (1, -t, 0), (0, -1, t), (0, 1, t), (0, -1, -t), (0, 1, -t),
         (t, 0, -1), (t, 0, 1), (-t, 0, -1), (-t, 0, 1)]
    f = [(0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2), (10, 7, 6),
         (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11), (6, 2, 10),
         (8, 6, 7), (9, 8, 1)]
    verts = [np.array(p, float) / np.linalg.norm(p) for p in v]
    for _ in range(sub):
        cache = {}
        nf = []

        def mid(a, b):
            k = (min(a, b), max(a, b))
            if k not in cache:
                m = verts[a] + verts[b]
                verts.append(m / np.linalg.norm(m))
                cache[k] = len(verts) - 1
            return cache[k]
        for a, b, c in f:
            ab, bc, ca = mid(a, b), mid(b, c), mid(c, a)
            nf += [(a, ab, ca), (b, bc, ab), (c, ca, bc), (ab, bc, ca)]
        f = nf
    P = np.array(verts, np.float32) * 0.5
    out = np.zeros((len(P), 10), np.float32)
    out[:, 0:3] = P
    out[:, 3:6] = P * 2
    out[:, 6:10] = 1
    return out, np.array(f, np.uint32).ravel()


def cylinder(n: int = 16):
    a = np.linspace(0, 2 * np.pi, n + 1)
    tris = []
    for k in range(n):
        p0 = (0.5 * np.cos(a[k]), 0.5 * np.sin(a[k]))
        p1 = (0.5 * np.cos(a[k + 1]), 0.5 * np.sin(a[k + 1]))
        b0, b1 = (p0[0], -0.5, p0[1]), (p1[0], -0.5, p1[1])
        t0, t1 = (p0[0], 0.5, p0[1]), (p1[0], 0.5, p1[1])
        tris += [(b0, t1, t0), (b0, b1, t1), (t0, t1, (0, 0.5, 0)), (b1, b0, (0, -0.5, 0))]
    return _flat(np.array(tris, np.float32))


def cone(n: int = 12):
    a = np.linspace(0, 2 * np.pi, n + 1)
    tris = []
    for k in range(n):
        p0 = (0.5 * np.cos(a[k]), -0.5, 0.5 * np.sin(a[k]))
        p1 = (0.5 * np.cos(a[k + 1]), -0.5, 0.5 * np.sin(a[k + 1]))
        tris += [(p0, (0, 0.5, 0), p1), (p1, (0, -0.5, 0), p0)]
    return _flat(np.array(tris, np.float32))


def bird():
    """A swept-wing dart pointing along +x (wings in the xz plane)."""
    nose, tail = (0.5, 0, 0), (-0.5, 0, 0)
    lw, rw = (-0.35, 0.02, 0.55), (-0.35, 0.02, -0.55)
    back, belly = (-0.1, 0.1, 0), (-0.1, -0.08, 0)
    tris = [(nose, lw, back), (nose, back, rw), (nose, belly, lw), (nose, rw, belly), (lw, tail, back),
            (back, tail, rw), (belly, tail, lw), (rw, tail, belly)]
    return _flat(np.array(tris, np.float32))


def library() -> dict:
    return {"cube": cube(), "sphere": sphere(2), "cylinder": cylinder(), "cone": cone(), "bird": bird()}


def trs(t: np.ndarray, s: np.ndarray, R: np.ndarray | None = None) -> np.ndarray:
    """Instance affines (n, 12): translation (n, 3), scale (n, 3) or (n,), rotation (n, 3, 3) or None."""
    t = np.asarray(t, np.float32).reshape(-1, 3)
    n = len(t)
    s = np.asarray(s, np.float32)
    if s.size == 1:
        s = np.full((n, 3), float(s.ravel()[0]), np.float32)
    elif s.ndim == 1 and len(s) == n and n != 3:
        s = np.repeat(s[:, None], 3, 1)
    else:
        s = np.broadcast_to(s.reshape(-1, 3) if s.size % 3 == 0 else s.reshape(n, 1), (n, 3))
    M = np.zeros((n, 3, 4), np.float32)
    if R is None:
        M[:, 0, 0], M[:, 1, 1], M[:, 2, 2] = s[:, 0], s[:, 1], s[:, 2]
    else:
        M[:, :, :3] = R * s[:, None, :]
    M[:, :, 3] = t
    return M.reshape(n, 12)


def inst(M: np.ndarray, color, extra=(0.0, 0.0, 0.0, 0.0)) -> np.ndarray:
    n = len(M)
    out = np.zeros((n, 20), np.float32)
    out[:, :12] = M
    out[:, 12:16] = np.broadcast_to(np.asarray(color, np.float32), (n, 4))
    out[:, 16:20] = np.broadcast_to(np.asarray(extra, np.float32), (n, 4))
    return out
