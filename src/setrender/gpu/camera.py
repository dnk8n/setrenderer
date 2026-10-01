"""Camera maths and frame-uniform packing (layout mirrors `Frame` in shaders.py)."""
from __future__ import annotations

import math

import numpy as np

OFF = {"viewproj": 0, "inv_viewproj": 16, "cam_pos": 32, "cam_right": 36, "cam_up": 40, "cam_fwd": 44,
       "key_dir": 48, "key_col": 52, "sky_top": 56, "sky_hor": 60, "amb_sky": 64, "amb_gnd": 68, "fog_col": 72,
       "wind": 76, "audio": 80, "audio2": 84, "beat": 88, "misc": 92, "res": 96, "nl": 100, "sun_sky": 104,
       "moon_sky": 108, "lights": 112}


def perspective(fov_y: float, aspect: float, near: float, far: float) -> np.ndarray:
    f = 1.0 / math.tan(fov_y / 2)
    return np.array([[f / aspect, 0, 0, 0],
                     [0, f, 0, 0],
                     [0, 0, far / (near - far), near * far / (near - far)],
                     [0, 0, -1, 0]], np.float64)


def view_from(pos, yaw: float, pitch: float, roll: float):
    """yaw 0 looks along -z, positive yaw turns left (towards -x); pitch up positive; roll clockwise."""
    cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
    fwd = np.array([-sy * cp, sp, -cy * cp])
    right0 = np.array([cy, 0.0, -sy])
    up0 = np.cross(right0, fwd)
    cr, sr = math.cos(roll), math.sin(roll)
    right = right0 * cr - up0 * sr
    up = up0 * cr + right0 * sr
    V = np.eye(4)
    V[0, :3], V[1, :3], V[2, :3] = right, up, -fwd
    V[:3, 3] = -V[:3, :3] @ np.asarray(pos, float)
    return V, right, up, fwd


def look_angles(src, dst) -> tuple[float, float]:
    d = np.asarray(dst, float) - np.asarray(src, float)
    yaw = math.atan2(-d[0], -d[2])
    pitch = math.atan2(d[1], math.hypot(d[0], d[2]))
    return yaw, pitch


class Uniforms:
    def __init__(self, n_floats: int):
        self.a = np.zeros(n_floats, np.float32)

    def set(self, name: str, *vals):
        o = OFF[name]
        v = np.asarray(vals if len(vals) > 1 else vals[0], np.float32).ravel()
        self.a[o:o + len(v)] = v

    def camera(self, pos, yaw, pitch, roll, fov_y, aspect, near=0.08, far=1500.0):
        V, right, up, fwd = view_from(pos, yaw, pitch, roll)
        P = perspective(fov_y, aspect, near, far)
        VP = P @ V
        self.set("viewproj", VP.T)
        self.set("inv_viewproj", np.linalg.inv(VP).T)
        self.a[32:35] = pos
        self.a[36:39] = right
        self.a[39] = aspect
        self.a[40:43] = up
        self.a[43] = math.tan(fov_y / 2)
        self.a[44:47] = fwd
        return VP, right, up, fwd

    def lights(self, L: np.ndarray):
        """L: (k,16) rows of pos(xyz,range) col(rgb,intensity) dir(xyz,cos_outer or -2) ext(cos_inner,...)"""
        k = min(len(L), 24)
        o = OFF["lights"]
        self.a[o:o + 16 * 24] = 0
        if k:
            self.a[o:o + 16 * k] = np.asarray(L[:k], np.float32).ravel()
        self.a[OFF["nl"]] = k


def point_light(p, col, intensity, rng):
    return np.array([*p, rng, *col, intensity, 0, -1, 0, -2.0, 0, 0, 0, 0], np.float32)


def spot_light(p, d, col, intensity, rng, outer_deg, inner_deg):
    d = np.asarray(d, float)
    d = d / (np.linalg.norm(d) + 1e-9)
    return np.array([*p, rng, *col, intensity, *d, math.cos(math.radians(outer_deg)),
                     math.cos(math.radians(inner_deg)), 0, 0, 0], np.float32)
