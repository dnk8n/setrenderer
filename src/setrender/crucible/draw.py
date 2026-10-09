"""Helpers that turn shapes into the engine's arrays (vectorised, so a frame with thousands of shapes stays
cheap in Python), and the 3D camera matrices."""
from __future__ import annotations

import math

import numpy as np

from . import font
from .engine import Layer

WORLD, SCREEN, PIXEL = 0.0, 1.0, 2.0
CIRCLE, BOX, SEG, RING, SPARK = 0, 1, 2, 3, 4


def rgba(c, a: float | None = None) -> tuple:
    c = tuple(float(x) for x in c)
    if len(c) == 3:
        c = c + (1.0,)
    if a is not None:
        c = c[:3] + (float(a),)
    return c


def hexc(h: str, a: float = 1.0) -> tuple:
    h = h.lstrip("#")
    return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255, a)


def mix(a, b, t: float) -> tuple:
    return tuple(float(x) * (1 - t) + float(y) * t for x, y in zip(a, b))


def _cols(color, n: int) -> np.ndarray:
    c = np.asarray(color, np.float32)
    if c.ndim == 1:
        if len(c) == 3:
            c = np.append(c, 1.0)
        return np.broadcast_to(c, (n, 4))
    if c.shape[1] == 3:
        c = np.concatenate([c, np.ones((len(c), 1), np.float32)], 1)
    return c


def sdf(kind: int, a: np.ndarray, r, color, space: float = WORLD, angle=0.0, outline=0.0, dark=0.35,
        glow=0.0) -> np.ndarray:
    """Shape instances: a is (n, 4) (centre + size, or two end points), r the radius or corner (n,) or scalar."""
    a = np.asarray(a, np.float32).reshape(-1, 4)
    n = len(a)
    out = np.zeros((n, 16), np.float32)
    out[:, 0:4] = a
    out[:, 4] = r
    out[:, 5] = angle
    out[:, 6] = kind
    out[:, 7] = space
    out[:, 8:12] = _cols(color, n)
    out[:, 12] = outline
    out[:, 13] = dark
    out[:, 14] = glow
    return out


def circles(xy, r, color, space=WORLD, outline=0.0, dark=0.35, glow=0.0) -> np.ndarray:
    xy = np.asarray(xy, np.float32).reshape(-1, 2)
    a = np.zeros((len(xy), 4), np.float32)
    a[:, :2] = xy
    a[:, 2] = r
    return sdf(CIRCLE, a, 0.0, color, space, 0.0, outline, dark, glow)


def rings(xy, r, half_w, color, space=WORLD, glow=0.0) -> np.ndarray:
    xy = np.asarray(xy, np.float32).reshape(-1, 2)
    a = np.zeros((len(xy), 4), np.float32)
    a[:, :2] = xy
    a[:, 2] = r
    a[:, 3] = half_w
    return sdf(RING, a, 0.0, color, space, glow=glow)


def boxes(xy, half, color, space=WORLD, angle=0.0, corner=0.0, outline=0.0, dark=0.35, glow=0.0) -> np.ndarray:
    xy = np.asarray(xy, np.float32).reshape(-1, 2)
    a = np.zeros((len(xy), 4), np.float32)
    a[:, :2] = xy
    a[:, 2:4] = np.broadcast_to(np.asarray(half, np.float32).reshape(-1, 2) if np.ndim(half) else half, (len(xy), 2))
    return sdf(BOX, a, corner, color, space, angle, outline, dark, glow)


def segs(p0, p1, r, color, space=WORLD, outline=0.0, dark=0.35, glow=0.0) -> np.ndarray:
    p0 = np.asarray(p0, np.float32).reshape(-1, 2)
    p1 = np.asarray(p1, np.float32).reshape(-1, 2)
    return sdf(SEG, np.concatenate([p0, p1], 1), r, color, space, 0.0, outline, dark, glow)


def polyline(pts, r, color, space=WORLD, glow=0.0) -> np.ndarray:
    pts = np.asarray(pts, np.float32).reshape(-1, 2)
    if len(pts) < 2:
        return np.zeros((0, 16), np.float32)
    c = np.asarray(color, np.float32)
    if c.ndim == 2:
        c = c[:-1]
    return segs(pts[:-1], pts[1:], r, c, space, glow=glow)


def sparks(xy, r, color, space=WORLD, glow=0.0) -> np.ndarray:
    xy = np.asarray(xy, np.float32).reshape(-1, 2)
    a = np.zeros((len(xy), 4), np.float32)
    a[:, :2] = xy
    a[:, 2] = r
    return sdf(SPARK, a, 0.0, color, space, glow=glow)


def tris(pts, color, space=WORLD) -> np.ndarray:
    """Triangles (n, 3, 2) with one colour each (n, 4) or one colour."""
    pts = np.asarray(pts, np.float32).reshape(-1, 3, 2)
    n = len(pts)
    out = np.zeros((n, 3, 7), np.float32)
    out[:, :, 0:2] = pts
    c = _cols(color, n)
    out[:, :, 2:6] = c[:, None, :]
    out[:, :, 6] = space
    return out.reshape(-1, 7)


def quads(q, color, space=WORLD) -> np.ndarray:
    """Convex quads (n, 4, 2), corners in order, one colour each."""
    q = np.asarray(q, np.float32).reshape(-1, 4, 2)
    t = np.concatenate([q[:, [0, 1, 2]], q[:, [0, 2, 3]]], 0)
    c = _cols(color, len(q))
    return tris(t, np.concatenate([c, c], 0), space)


def rect(x0, y0, x1, y1, color, space=SCREEN) -> np.ndarray:
    return quads(np.array([[[x0, y0], [x1, y0], [x1, y1], [x0, y1]]], np.float32), color, space)


def vgrad(x0, y0, x1, y1, c_top, c_bot, space=SCREEN) -> np.ndarray:
    """A rectangle with a vertical gradient (top and bottom colours)."""
    v = np.array([[x0, y0, *rgba(c_top), space], [x1, y0, *rgba(c_top), space], [x1, y1, *rgba(c_bot), space],
                  [x0, y0, *rgba(c_top), space], [x1, y1, *rgba(c_bot), space], [x0, y1, *rgba(c_bot), space]],
                 np.float32)
    return v


def strip(xs, ytop, ybot, ctop, cbot, space=WORLD) -> np.ndarray:
    """A filled band between two curves sampled at xs (terrain, water), with top and bottom colours."""
    xs = np.asarray(xs, np.float32)
    ytop = np.broadcast_to(np.asarray(ytop, np.float32), xs.shape)
    ybot = np.broadcast_to(np.asarray(ybot, np.float32), xs.shape)
    n = len(xs) - 1
    ct = np.asarray(rgba(ctop), np.float32)
    cb = np.asarray(rgba(cbot), np.float32)
    v = np.zeros((n, 6, 7), np.float32)
    a = np.stack([xs[:-1], ytop[:-1]], 1)
    b = np.stack([xs[1:], ytop[1:]], 1)
    c = np.stack([xs[1:], ybot[1:]], 1)
    d = np.stack([xs[:-1], ybot[:-1]], 1)
    for k, (p, col) in enumerate(((a, ct), (b, ct), (c, cb), (a, ct), (c, cb), (d, cb))):
        v[:, k, 0:2] = p
        v[:, k, 2:6] = col
    v[:, :, 6] = space
    return v.reshape(-1, 7)


def text(L: Layer, s: str, x: float, y: float, size: float, color=(1, 1, 1, 1), align: float = 0.0,
         tracking: float = 0.0, outline: float = 0.0, dark: float = 0.85, shadow: bool = True):
    """A line of overlay text; a soft drop shadow keeps it readable over any picture."""
    if shadow:
        sh = font.glyphs(s, x + size * 0.04, y + size * 0.05, size, (0, 0, 0, 0.55 * rgba(color)[3]), align, tracking,
                         weight=0.06)
        L.add("glyph", sh)
    L.add("glyph", font.glyphs(s, x, y, size, rgba(color), align, tracking, outline, dark))


# ------------------------------------------------------------------ 3D cameras
def look_at(eye, target, up=(0.0, 1.0, 0.0)) -> np.ndarray:
    eye, target, up = (np.asarray(v, np.float64) for v in (eye, target, up))
    f = target - eye
    f /= np.linalg.norm(f)
    s = np.cross(f, up)
    s /= np.linalg.norm(s) + 1e-12
    u = np.cross(s, f)
    M = np.eye(4)
    M[0, :3], M[1, :3], M[2, :3] = s, u, -f
    M[:3, 3] = -M[:3, :3] @ eye
    return M


def perspective(fovy: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1.0 / math.tan(fovy / 2)
    M = np.zeros((4, 4))
    M[0, 0], M[1, 1] = f / aspect, f
    M[2, 2] = far / (near - far)
    M[2, 3] = near * far / (near - far)
    M[3, 2] = -1.0
    return M


def ortho(half_w: float, half_h: float, near: float, far: float) -> np.ndarray:
    M = np.eye(4)
    M[0, 0], M[1, 1] = 1 / half_w, 1 / half_h
    M[2, 2] = -1.0 / (far - near)
    M[2, 3] = -near / (far - near)
    return M


def sun_matrix(sun_dir, centre, radius: float) -> np.ndarray:
    d = np.asarray(sun_dir, np.float64)
    d /= np.linalg.norm(d)
    c = np.asarray(centre, np.float64)
    V = look_at(c + d * radius * 2.0, c, (0.0, 1.0, 0.0) if abs(d[1]) < 0.95 else (1.0, 0.0, 0.0))
    return ortho(radius, radius, 0.01, radius * 4.0) @ V


# ------------------------------------------------------------------ uniforms
SLOTS = ["res", "clk", "aud", "aud2", "camw", "camp", "bg0", "bgt", "bgb", "acc", "post", "post2", "lay", "lay2",
         "vp", "vp1", "vp2", "vp3", "svp", "svp1", "svp2", "svp3", "sun", "sunc", "sky", "gnd", "eye"]


def uniforms(W: int, H: int, **kw) -> np.ndarray:
    """Pack named vec4s (and the vp/svp matrices) into the engine's uniform block."""
    from .engine import NU
    u = np.zeros((NU, 4), np.float32)
    u[0] = (W, H, 1.0 / W, 1.0 / H)
    for k, v in kw.items():
        if k in ("vp", "svp"):
            i = SLOTS.index(k)
            u[i:i + 4] = np.asarray(v, np.float32).T      # WGSL matrices are column-major
        else:
            v = list(v) + [0.0] * (4 - len(v))
            u[SLOTS.index(k)] = v[:4]
    return u.ravel()
