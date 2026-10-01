"""The festival world: a farm at night. Static layout plus per-frame props that move with the music.

Coordinates in metres, y up. The stage faces +z; the dancefloor is centred on (0, -4); the
cornfield wraps the west and south; cows graze in a fenced pasture to the east.
"""
from __future__ import annotations

import math

import numpy as np

from ..gpu import mesh as M
from .cast import FLAGS, PRIDE_FLAGS
from .cropcircles import CropField
from .parts import A, Ctx, Parts, apply, compose, hue, hue_np

STAGE_Z = -16.0
PLAT_TOP = 0.9
TABLE_Y = PLAT_TOP + 0.85
DJ_POS = np.array([0.0, PLAT_TOP, -16.35])
FLOOR_C = np.array([0.0, 0.0, -4.0])
CAR_POS = np.array([-7.4, 0.0, -13.3])
CAR_YAW = math.atan2(7.4, 11.0)
TRACTOR_POS = np.array([8.9, 0.0, -13.6])
TRACTOR_YAW = math.atan2(-8.9, 11.5)
TRUSS_Y = 5.6
CAMPFIRE = np.array([-4.5, 0.0, 14.0])
BAR_POS = np.array([-16.0, 0.0, 13.0])
LOO_POS = np.array([16.5, 0.0, 10.0])
PATH_X = 3.0
FIELD = (-80.0, -50.0, 160.0, 150.0)
TREE_SPOTS = [(-18.5, -12.0), (-19.5, -3.5), (-18.0, 5.0), (18.5, -12.0), (19.5, -3.5), (18.0, 5.0),
              (-11.5, 16.0), (12.0, 17.5)]
FLAGPOLES = [(-12.5, -12.5), (12.5, -12.5), (-14.5, -1.0), (14.5, -1.0), (-10.0, 8.5), (10.0, 8.5)]
SPEAKERS = [(-5.0, -15.2), (5.0, -15.2)]

RGB = lambda c: tuple(v / 255 for v in c)  # noqa: E731


def path_x(z):
    return PATH_X + np.sin(np.asarray(z) * 0.09) * 3.0


def in_festival(x, z):
    return (np.abs(x) < 23.5) & (z < 21.5) & (z > -24)


def corn_ok(x, z):
    west = (x < -24) & (z > -48) & (z < 22)
    south = (z > 23) & (z < 98) & (np.abs(x) < 78)
    nw = (x < -24) & (z <= -48)
    path = (np.abs(x - path_x(z)) < 1.3) & (z > 15)
    side_path = (np.abs(z - 2.0 - np.sin(x * 0.12) * 2) < 1.2) & (x < -20)
    return (west | south | nw) & ~path & ~side_path & ~in_festival(x, z)


class World:
    def __init__(self, rng: np.random.Generator, cfg: dict, clip_start: float, total: float, struct, tinfo):
        self.tinfo = tinfo
        self.rng = rng
        self.cfg = cfg
        self.clip_start, self.total = clip_start, total
        self.struct = struct
        self.static: dict[str, list] = {}
        el = cfg.get("elements", {})
        self.el = el
        self.car_col = RGB([(40, 140, 140), (200, 160, 40), (130, 30, 40), (120, 170, 220), (220, 90, 30),
                            (90, 60, 140)][int(rng.integers(6))])
        self.tractor_col = RGB([(200, 30, 20), (40, 130, 50), (40, 80, 170)][int(rng.integers(3))])
        self.corn_tone = float(rng.uniform(0.0, 1.0))
        self._build_static()
        self._build_trees()
        self._build_corn()
        self._build_crop_circles()
        self._build_tetris()
        self.cows = [{"x": float(rng.uniform(28, 52)), "z": float(rng.uniform(-36, -10)), "ph": float(rng.random()),
                      "flip": bool(rng.random() < 0.5)} for _ in range(int(el.get("pasture", {}).get("cows", 6)))]
        self.sheep = [{"x": float(rng.uniform(30, 50)), "z": float(rng.uniform(-30, -12)), "ph": float(rng.random())}
                      for _ in range(3)]
        self.chickens = [{"x": float(rng.uniform(-10, 10)), "z": float(rng.uniform(6, 13)), "ph": float(rng.random()),
                          "sp": float(rng.uniform(0.3, 0.8))} for _ in range(int(el.get("chickens", {}).get("count", 6)))]
        self.flag_sched = self._flag_schedule()

    # ------------------------------------------------------------------ static geometry
    def _add(self, mesh, m, tint=(1, 1, 1), mat=0, emis=(0, 0, 0), sway=0.0, extra=(0, 0, 0, 0)):
        self.static.setdefault(mesh, []).append(M.inst(m, tint, mat, emis, sway, extra))

    def _build_static(self):
        rng = self.rng
        self._add("terrain", A(), (1, 1, 1), 2)
        # hay-bale stage platform (two layers)
        for layer in range(2):
            for zi in range(5):
                for xi in range(6):
                    x = -3.0 + xi * 1.2 + (0.6 if (zi + layer) % 2 else 0) - 0.3
                    z = -17.6 + zi * 0.62 + 0.31
                    self._add("box", A((x, layer * 0.45, z), (1.18, 0.45, 0.6)), (1, 1, 1), 3)
        # DJ table, decks, mixer, a silver bassline box and a beige home computer
        self._add("box", A((0, TABLE_Y - 0.06, -15.55), (2.7, 0.06, 0.8)), (0.55, 0.38, 0.22), 4)
        for x in (-1.25, 1.25):
            for z in (-15.85, -15.25):
                self._add("box", A((x, PLAT_TOP, z), (0.06, 0.8, 0.06)), (0.3, 0.2, 0.12), 4)
        for x in (-0.72, 0.72):
            self._add("box", A((x, TABLE_Y, -15.55), (0.46, 0.09, 0.36)), (0.12, 0.12, 0.13), 0)
        self._add("box", A((0, TABLE_Y, -15.55), (0.32, 0.1, 0.36)), (0.08, 0.08, 0.09), 0)
        self._add("box", A((-1.12, TABLE_Y, -15.5), (0.32, 0.05, 0.18)), (0.75, 0.75, 0.78), 8)
        self._add("box", A((1.12, TABLE_Y, -15.5), (0.4, 0.06, 0.2), (0.12, 0, 0)), (0.82, 0.76, 0.62), 0)
        self._add("box", A((1.12, TABLE_Y + 0.05, -15.47), (0.34, 0.02, 0.1), (0.12, 0, 0)), (0.25, 0.22, 0.2), 0)
        # TV wall behind the DJ
        self.tvs = []
        for row in range(3):
            for col in range(5):
                x = -1.44 + col * 0.72
                y = PLAT_TOP + row * 0.56
                tint = [(0.16, 0.15, 0.14), (0.75, 0.7, 0.6), (0.3, 0.28, 0.26)][(row * 5 + col * 3) % 3]
                self._add("box", A((x, y, -17.35), (0.7, 0.55, 0.5)), tint, 0)
                self.tvs.append(np.array([x, y + 0.275, -17.35 + 0.255]))
        # truss
        for x in (-4.6, 4.6):
            self._add("box", A((x, 0, -15.6), (0.28, TRUSS_Y, 0.28)), (0.55, 0.56, 0.6), 8)
        self._add("box", A((0, TRUSS_Y, -15.6), (9.5, 0.32, 0.32)), (0.55, 0.56, 0.6), 8)
        # speaker stacks
        self.cones = []
        for (x, z) in SPEAKERS:
            for k, (h, y) in enumerate([(1.1, 0.0), (1.1, 1.1), (0.55, 2.2)]):
                self._add("box", A((x, y, z), (1.1, h, 0.85)), (0.07, 0.07, 0.08), 0)
                if k < 2:
                    for dy in (0.3, 0.78):
                        self.cones.append((np.array([x, y + dy, z + 0.43]), 0.42 if dy < 0.5 else 0.3))
                else:
                    self.cones.append((np.array([x, y + 0.28, z + 0.43]), 0.22))
        # tractor (static body; beacon animated)
        T = A(tuple(TRACTOR_POS), (1, 1, 1), (0, TRACTOR_YAW, 0))
        tc = self.tractor_col
        for (t, s, col, mat) in [((0, 0.55, 0.2), (1.3, 0.7, 2.6), tc, 8), ((0, 1.25, 0.9), (1.0, 0.5, 1.3), tc, 8),
                                 ((0, 1.25, -0.6), (1.3, 0.08, 1.2), (0.15, 0.15, 0.15), 0),
                                 ((0, 2.4, -0.6), (1.4, 0.08, 1.3), tc, 8)]:
            self._add("box", compose(T, A(t, s)), col, mat)
        for sx in (-0.62, 0.62):
            for sz in (-1.15, 0.0):
                self._add("box", compose(T, A((sx, 1.25, -0.6 + sz * 0.5 + 0.3), (0.06, 1.15, 0.06))), (0.1, 0.1, 0.1), 0)
        for sx in (-0.85, 0.85):
            self._add("cyl", compose(T, A((sx, 0.78, -0.7), (1.5, 0.45, 1.5), (0, 0, math.pi / 2))), (0.06, 0.06, 0.06), 0)
            self._add("cyl", compose(T, A((sx * 0.85, 0.42, 1.3), (0.8, 0.3, 0.8), (0, 0, math.pi / 2))), (0.06, 0.06, 0.06), 0)
        self._add("cyl", compose(T, A((0.35, 1.5, 1.3), (0.1, 1.2, 0.1))), (0.2, 0.2, 0.2), 0)
        self.tractor_T = T
        # portaloos, bar tent, campfire and bales
        for k in range(4):
            p = LOO_POS + np.array([0, 0, k * 1.45])
            self._add("box", A(tuple(p), (1.3, 2.3, 1.3)), (0.15, 0.35, 0.8), 0)
            self._add("box", A(tuple(p + [0, 2.3, 0]), (1.4, 0.12, 1.4)), (0.85, 0.85, 0.9), 0)
            self._add("box", A(tuple(p + [-0.66, 0.1, 0]), (0.02, 2.0, 1.0)), (0.12, 0.3, 0.7), 0)
        B = BAR_POS
        self._add("box", A(tuple(B), (5.0, 1.05, 1.2)), (0.45, 0.3, 0.18), 4)
        for sx in (-2.4, 2.4):
            for sz in (-1.5, 1.5):
                self._add("box", A(tuple(B + [sx, 0, sz]), (0.12, 2.8, 0.12)), (0.4, 0.3, 0.2), 4)
        self._add("prism", A(tuple(B + [0, 2.8, 0]), (5.4, 1.4, 3.6), (0, math.pi / 2, 0)), (0.9, 0.9, 0.85), 0)
        for k in range(6):
            a = k / 6 * 2 * math.pi
            self._add("box", A(tuple(CAMPFIRE + [math.cos(a) * 2.6, 0, math.sin(a) * 2.6]), (1.15, 0.45, 0.55), (0, -a, 0)), (1, 1, 1), 3)
        for k in range(5):
            a = k / 5 * 2 * math.pi
            self._add("cyl", A(tuple(CAMPFIRE + [math.cos(a) * 0.3, 0.12, math.sin(a) * 0.3]), (0.18, 0.9, 0.18), (math.pi / 2 - 0.4, a, 0)), (0.3, 0.2, 0.12), 4)
        # spare bales around the dancefloor (seats; they bounce on kicks in the dynamic pass)
        self.bales = [np.array([x, 0, z]) for x, z in [(-13, -9), (13.5, -8), (-12, 4), (12, 5), (-6, 9.5), (6.5, 10)]]
        # flag poles
        for (x, z) in FLAGPOLES:
            self._add("cyl6", A((x, 0, z), (0.08, 5.2, 0.08)), (0.8, 0.8, 0.8), 8)
        # pasture fence
        for x in np.arange(24.0, 58.0, 2.5):
            for z in (-42.0, -4.0):
                self._add("box", A((x, 0, z), (0.12, 1.2, 0.12)), (0.4, 0.3, 0.2), 4)
            self._add("box", A((x + 1.25, 0.8, -42.0), (2.5, 0.08, 0.06)), (0.45, 0.33, 0.2), 4)
            self._add("box", A((x + 1.25, 0.8, -4.0), (2.5, 0.08, 0.06)), (0.45, 0.33, 0.2), 4)
        for z in np.arange(-42.0, -4.0, 2.5):
            for x in (24.0, 58.0):
                self._add("box", A((x, 0, z), (0.12, 1.2, 0.12)), (0.4, 0.3, 0.2), 4)
                self._add("box", A((x, 0.8, z + 1.25), (0.06, 0.08, 2.5)), (0.45, 0.33, 0.2), 4)
        # camping tents (A-frames)
        for k in range(10):
            x, z = float(rng.uniform(27, 52)), float(rng.uniform(4, 26))
            self._add("prism", A((x, 0, z), (2.0, 1.3, 2.4), (0, float(rng.uniform(0, 3.1)), 0)),
                      hue(float(rng.random()), 0.6, 0.8), 0)
        # barn, silo, farmhouse, windpump tower
        bx, bz = -42.0, -62.0
        self._add("box", A((bx, 0, bz), (14, 7, 10)), (0.55, 0.1, 0.08), 4)
        self._add("prism", A((bx, 7, bz), (14.6, 4.5, 10.4), (0, math.pi / 2, 0)), (0.25, 0.22, 0.22), 0)
        self._add("box", A((bx, 0, bz + 5.02), (4, 5, 0.1)), (0.9, 0.85, 0.8), 4)
        self._add("cyl", A((bx + 10, 0, bz - 2), (5, 14, 5)), (0.6, 0.62, 0.66), 8)
        self._add("ico2", A((bx + 10, 14, bz - 2), (5, 4, 5)), (0.5, 0.52, 0.56), 8)
        fx, fz = 34.0, -68.0
        self._add("box", A((fx, 0, fz), (10, 5, 8)), (0.85, 0.82, 0.72), 0)
        self._add("prism", A((fx, 5, fz), (10.6, 3.2, 8.4), (0, math.pi / 2, 0)), (0.3, 0.12, 0.1), 0)
        self.house_windows = [np.array([fx + dx, 2.4, fz + 4.05]) for dx in (-3, 0, 3)]
        wx, wz = 52.0, -48.0
        for a in (0.0, math.pi / 2):
            self._add("box", A((wx, 0, wz), (0.3, 11, 0.3), (0.07 * math.cos(a), a, 0.07)), (0.5, 0.5, 0.55), 8)
            self._add("box", A((wx, 0, wz), (0.3, 11, 0.3), (-0.07 * math.cos(a), a, -0.07)), (0.5, 0.5, 0.55), 8)
        self.windpump = np.array([wx, 11.0, wz + 0.4])
        # wind turbines on the hills
        self.turbines = []
        for k in range(6):
            a = -0.9 + k * 0.38 + float(rng.uniform(-0.08, 0.08))
            r = float(rng.uniform(260, 340))
            x, z = math.sin(a) * r, -math.cos(a) * r
            y = M.height_at(self.tinfo, x, z)
            self.turbines.append(np.array([x, y, z]))
        # distant tree line silhouettes
        for k in range(70):
            a = float(rng.uniform(0, 2 * math.pi))
            r = float(rng.uniform(120, 200))
            x, z = math.cos(a) * r, math.sin(a) * r
            y = M.height_at(self.tinfo, x, z)
            s = float(rng.uniform(6, 12))
            g = (0.10 + 0.06 * float(rng.random()), 0.17 + 0.08 * float(rng.random()), 0.07)
            self._add("cyl6", A((x, y, z), (0.8, s * 0.5, 0.8)), (0.25, 0.18, 0.1), 4)
            for q in range(3):
                ox, oz = float(rng.uniform(-s, s)) * 0.3, float(rng.uniform(-s, s)) * 0.3
                ss = s * float(rng.uniform(0.6, 0.9))
                self._add("ico", A((x + ox, y + s * 0.55 + float(rng.uniform(0, s * 0.4)), z + oz), (ss, ss * 0.9, ss)), g, 11)

    def _build_trees(self):
        rng = self.rng
        self.trees = []
        n_jelly = self.el.get("trees", {}).get("jellyfish_per_tree", [4, 7])
        for (x, z) in TREE_SPOTS:
            x += float(rng.uniform(-1, 1))
            z += float(rng.uniform(-1, 1))
            h = float(rng.uniform(4.2, 5.4))
            self._add("cyl", A((x, 0, z), (0.55, h + 1.0, 0.55)), (0.32, 0.22, 0.14), 4)
            for k in range(3):
                a = k * 2.1 + float(rng.uniform(0, 1))
                self._add("cyl6", A((x, h - 0.6, z), (0.18, 2.2, 0.18), (0.9, a, 0)), (0.3, 0.2, 0.12), 4)
            blobs = []
            for k in range(int(rng.integers(5, 8))):
                bx = x + float(rng.uniform(-2.2, 2.2))
                bz = z + float(rng.uniform(-2.2, 2.2))
                by = h + float(rng.uniform(0.6, 2.6))
                s = float(rng.uniform(2.4, 3.8))
                g = (0.10 + 0.08 * float(rng.random()), 0.22 + 0.12 * float(rng.random()), 0.08)
                self._add("ico", A((bx, by, bz), (s, s * 0.85, s)), g, 11, sway=0.06)
                blobs.append((bx, by, bz, s))
            jel = []
            for k in range(int(rng.integers(n_jelly[0], n_jelly[1] + 1))):
                a = float(rng.uniform(0, 2 * math.pi))
                r = float(rng.uniform(0.8, 2.6))
                ax, az = x + math.cos(a) * r, z + math.sin(a) * r
                jel.append({"anchor": np.array([ax, h + float(rng.uniform(0.2, 0.9)), az]),
                            "L": float(rng.uniform(0.6, 2.0)), "size": float(rng.uniform(0.28, 0.5)),
                            "hue": float(rng.random()), "ph": float(rng.random() * 6.28), "lag": float(rng.uniform(0.05, 0.35)),
                            "n_t": int(rng.integers(5, 8))})
            self.trees.append({"x": x, "z": z, "h": h, "blobs": blobs, "jelly": jel})
        # fairy-light strings between neighbouring trees and to the truss
        pts = [(t["x"], t["h"] + 0.6, t["z"]) for t in self.trees]
        pairs = [(0, 1), (1, 2), (3, 4), (4, 5), (2, 6), (5, 7)]
        self.strings = []
        for a, b in pairs:
            self.strings.append((np.array(pts[a]), np.array(pts[b]), 1.2))
        self.strings.append((np.array(pts[0]), np.array([-4.6, TRUSS_Y - 0.4, -15.6]), 1.6))
        self.strings.append((np.array(pts[3]), np.array([4.6, TRUSS_Y - 0.4, -15.6]), 1.6))
        bulbs = []
        for (p0, p1, sag) in self.strings:
            n = int(np.linalg.norm(p1 - p0) / 0.55)
            for k in range(n + 1):
                s = k / max(n, 1)
                p = p0 + (p1 - p0) * s
                p[1] -= sag * 4 * s * (1 - s)
                bulbs.append(p)
        self.bulbs = np.array(bulbs)
        # bunting across the dancefloor: truss to the front trees
        self.bunting = []
        for (p0, p1, sag) in [(np.array([-4.6, TRUSS_Y - 0.2, -15.6]), np.array(pts[2]), 2.2),
                              (np.array([4.6, TRUSS_Y - 0.2, -15.6]), np.array(pts[5]), 2.2),
                              (np.array(pts[1]), np.array(pts[4]), 1.4)]:
            n = int(np.linalg.norm(p1 - p0) / 0.5)
            line = []
            for k in range(n):
                s = k / n
                p = p0 + (p1 - p0) * s
                p[1] -= sag * 4 * s * (1 - s)
                line.append(p)
            self.bunting.append((line, (p1 - p0) / np.linalg.norm(p1 - p0)))

    def _build_corn(self):
        rng = self.rng
        sp_row, sp_plant = 0.9, 0.62
        xs = np.arange(FIELD[0] + 0.5, FIELD[0] + FIELD[2], sp_row)
        zs = np.arange(FIELD[1] + 0.3, FIELD[1] + FIELD[3], sp_plant)
        X, Z = np.meshgrid(xs, zs)
        X = X + rng.uniform(-0.12, 0.12, X.shape)
        Z = Z + rng.uniform(-0.2, 0.2, Z.shape)
        ok = corn_ok(X, Z)
        X, Z = X[ok], Z[ok]
        n = len(X)
        H = rng.uniform(2.0, 2.7, n)
        Y = np.zeros(n)
        S = np.stack([np.ones(n) * rng.uniform(0.85, 1.2, n), H, np.ones(n)], 1)
        Mx = M.trs_many(np.stack([X, Y, Z], 1), S, rng.uniform(0, 2 * np.pi, n))
        g = rng.random(n)
        tone = self.corn_tone
        tint = np.stack([0.75 + 0.35 * g * tone, 0.85 + 0.15 * g, 0.55 + 0.1 * g], 1)
        rows = M.inst_many(Mx, tint, 5, sway=np.full(n, 0.22))
        near = np.hypot(X, Z - 10) < 48
        self.corn, self.corn_far = rows[near], rows[~near]
        self.corn_xz = np.stack([X, Z], 1)

    def _build_crop_circles(self):
        rng = self.rng
        self.crop = CropField(FIELD, 512)
        n = int(self.el.get("crop_circles", {}).get("count", 8))
        span = self.total
        # patterns are laid in the night, spread over the set; each takes 16-32 s to draw
        sites = [(-6.0, 58.0), (30.0, 52.0), (-38.0, 48.0), (-50.0, 0.0), (12.0, 80.0), (-30.0, 80.0),
                 (48.0, 75.0), (-55.0, -30.0), (-35.0, -22.0), (55.0, 40.0)]
        order = rng.permutation(len(sites))
        kinds = list(rng.permutation(["rings", "julia", "flower", "triskelion", "invader", "smiley", "rosette",
                                      "pacman", "arecibo", "yinyang"]))
        sym = 5 + int(self.struct_key() % 4)
        self.crop_sched = []
        for k in range(n):
            cx, cz = sites[order[k % len(sites)]]
            start = span * (0.08 + 0.84 * (k + float(rng.uniform(0.1, 0.9))) / n)
            dur = float(rng.uniform(16, 32))
            R = float(rng.uniform(7, 12))
            p = self.crop.add(kinds[k % len(kinds)], cx, cz, R, float(rng.uniform(0, 6.28)), start, dur, sym, rng)
            self.crop_sched.append(p)

    def struct_key(self) -> int:
        return int(self.cfg.get("_key_pc", 0))

    # ---------------------------------------------------------------- tetris bales
    def _build_tetris(self):
        """A Tetris game played with hay bales beside the stage: one row per beat, lines clear."""
        rng = self.rng
        W, Hh = 6, 9
        beats = self.struct.beats
        nb = len(beats)
        shapes = [[(0, 0), (1, 0), (2, 0), (3, 0)], [(0, 0), (1, 0), (0, 1), (1, 1)], [(0, 0), (1, 0), (2, 0), (1, 1)],
                  [(0, 0), (1, 0), (2, 0), (2, 1)], [(0, 0), (1, 0), (2, 0), (0, 1)], [(0, 0), (1, 0), (1, 1), (2, 1)],
                  [(1, 0), (2, 0), (0, 1), (1, 1)]]
        cols = [(0, 0.9, 0.9), (0.95, 0.9, 0.1), (0.7, 0.2, 0.9), (0.95, 0.55, 0.1), (0.2, 0.35, 1.0), (0.2, 0.9, 0.3), (0.95, 0.2, 0.2)]
        board = np.zeros((Hh + 4, W), np.int8)
        self.tet_board = np.zeros((max(nb, 1), Hh, W), np.int8)
        self.tet_piece = np.full((max(nb, 1), 4, 3), -1, np.int16)   # x, y, colour per cell (falling piece)
        self.tet_clear = np.zeros(max(nb, 1), np.int8)
        piece, px, py, pc = None, 0, Hh + 1, 0
        for b in range(nb):
            if piece is None:
                k = int(rng.integers(len(shapes)))
                piece, pc = shapes[k], k + 1
                # pick the column that keeps the stack lowest
                best, bx = 1e9, 0
                for x0 in range(W - max(c[0] for c in piece)):
                    y = Hh + 2
                    while y > 0 and all(board[y - 1 + c[1], x0 + c[0]] == 0 for c in piece):
                        y -= 1
                    score = y + float(rng.random()) * 0.6
                    if score < best:
                        best, bx = score, x0
                px, py = bx, Hh + 1
            # fall one row
            if py > 0 and all(board[py - 1 + c[1], px + c[0]] == 0 for c in piece):
                py -= 1
            else:
                for c in piece:
                    board[py + c[1], px + c[0]] = pc
                piece = None
                full = [y for y in range(Hh + 4) if board[y].all()]
                if full:
                    self.tet_clear[b] = len(full)
                    keep = [board[y] for y in range(Hh + 4) if y not in full]
                    board = np.array(keep + [np.zeros(W, np.int8)] * len(full), np.int8)
                if board[Hh - 1:].any():          # topped out: the stack collapses, new game
                    board[:] = 0
                    self.tet_clear[b] = 9
            self.tet_board[b] = board[:Hh]
            if piece is not None:
                for q, c in enumerate(piece):
                    self.tet_piece[b, q] = (px + c[0], py + c[1], pc)
        self.tet_cols = cols
        self.tet_origin = np.array([10.8, 0.0, -21.0])

    # ---------------------------------------------------------------- flags over the night
    def _flag_schedule(self):
        """Which flag flies on each pole, and when the bunting is up; changes at sections."""
        rng = self.rng
        secs = list(self.struct.phrases[::4]) + [self.struct.duration]
        sched = []
        names = PRIDE_FLAGS + ["smiley", "spiral"]
        for a, b in zip(secs[:-1], secs[1:]):
            poles = []
            for k in range(len(FLAGPOLES)):
                poles.append(names[int(rng.integers(len(names)))] if rng.random() < 0.7 else None)
            sched.append((a, b, poles, bool(rng.random() < 0.65), int(rng.integers(6))))
        return sched

    def flags_at(self, t: float):
        for a, b, poles, bunt, style in self.flag_sched:
            if a <= t < b:
                raise_k = min(1.0, (t - a) / 2.0, (b - t) / 2.0)
                return poles, bunt, style, raise_k
        return [None] * len(FLAGPOLES), False, 0, 0.0

    # ================================================================== per frame
    def frame(self, c: Ctx, P: Parts, at_rects: dict):
        self._car(c, P)
        self._stage(c, P, at_rects)
        self._trees(c, P)
        self._fairy_lights(c, P)
        self._flags(c, P, at_rects)
        self._farm(c, P, at_rects)
        self._tetris(c, P)
        self._turbines(c, P)

    def _car(self, c: Ctx, P: Parts):
        sub = c.env["sub"]
        kick = c.kick
        hop = 0.0
        for ev in c.events:
            if ev.kind == "drop" and 0 <= c.t - ev.t0 < 1.2:
                x = (c.t - ev.t0) / 1.2
                hop = math.sin(math.pi * x) * 0.35
        bounce = (0.05 * sub * c.env["beat"] if kick else 0.0)
        T = A(tuple(CAR_POS + [0, -bounce * 0.5, 0]), (1, 1, 1), (-hop * 0.5, CAR_YAW, 0))
        T[:, 3] += [0, hop * 0.6, 0]
        col = self.car_col
        rust = (0.35, 0.18, 0.1)
        parts = [((0, 0.32, 0), (1.72, 0.58, 4.1), col, 8), ((0, 0.9, -0.35), (1.52, 0.55, 2.1), col, 8),
                 ((0, 0.92, -0.35), (1.55, 0.42, 2.0), (0.06, 0.08, 0.1), 8),
                 ((0, 0.3, 2.06), (1.78, 0.16, 0.12), (0.12, 0.12, 0.12), 0), ((0, 0.3, -2.06), (1.78, 0.16, 0.12), (0.12, 0.12, 0.12), 0),
                 ((0.5, 0.55, 1.2), (0.5, 0.05, 0.6), rust, 0)]
        for t, s, cl, mat in parts:
            P.m("box", compose(T, A(t, s)), cl, mat)
        for sx in (-0.82, 0.82):
            for sz in (-1.3, 1.3):
                P.m("cyl", compose(T, A((sx - 0.1 * np.sign(sx), 0.31, sz), (0.62, 0.22, 0.62), (0, 0, math.pi / 2))), (0.05, 0.05, 0.05), 0)
        # headlights pump with the kick; hazards blink in breakdowns
        if kick:
            hl = 0.4 + 1.3 * sub * (0.4 + 0.6 * c.env["beat"])
        else:
            hl = 0.25 + 0.2 * c.env["lowmid"]
        high = any(ev.kind == "drop" and 0 <= c.t - ev.t0 < 3.0 for ev in c.events)
        if high:
            hl *= 1.6
        warm = (1.0, 0.92, 0.75)
        fwd = apply(T, (0, 0, 1)) - apply(T, (0, 0, 0))
        for sx in (-0.55, 0.55):
            p = apply(T, (sx, 0.6, 2.08))
            P.m("box", A(tuple(p - [0, 0.09, 0]), (0.36, 0.18, 0.04), (0, CAR_YAW, 0)), (1, 1, 1), 9, emis=tuple(v * hl * 2.5 for v in warm))
            d = fwd + np.array([-sx * 0.04, -0.06, 0])
            P.beam(p, p + d * 16, 0.12, 3.2, tuple(v * 0.05 * hl for v in warm), soft=1.6, fade=0.85)
        pL, pR = apply(T, (-0.55, 0.6, 2.1)), apply(T, (0.55, 0.6, 2.1))
        mid = (pL + pR) / 2
        P.spot(tuple(mid), tuple(fwd + np.array([0, -0.06, 0])), warm, 1.6 * hl, 34.0, 26.0, 12.0)
        haz = (not kick) and (c.beat_idx % 2 == 0) and c.beat_phase < 0.5
        for sx, sz in ((-0.85, 2.0), (0.85, 2.0), (-0.85, -2.0), (0.85, -2.0)):
            p = apply(T, (sx, 0.5, sz))
            on = haz
            P.m("box", A(tuple(p), (0.12, 0.1, 0.06), (0, CAR_YAW, 0)), (1, 0.5, 0.0), 9,
                emis=(2.5, 1.2, 0.0) if on else (0.1, 0.05, 0.0))
            if on:
                P.dot(p, 0.35, (0.6, 0.3, 0.0), soft=3.0)
        for sx in (-0.6, 0.6):
            p = apply(T, (sx, 0.55, -2.09))
            P.m("box", A(tuple(p), (0.3, 0.14, 0.04), (0, CAR_YAW, 0)), (1, 0, 0), 9, emis=(1.4 + 1.5 * c.env["bass"], 0.05, 0.05))
        # neon underglow
        ug = hue(c.T * 0.05 + c.bar_idx * 0.125, 0.9, 1.0)
        for sz in (-1.4, 0.0, 1.4):
            P.dot(apply(T, (0, 0.06, sz)) + [0, 0.02, 0], 1.3, tuple(v * (0.15 + 0.45 * c.env["bass"]) for v in ug), soft=2.0)
        P.point(tuple(apply(T, (0, 0.1, 0))), ug, 0.6 + 1.2 * c.env["bass"], 4.0)
        self.car_T = T

    def _stage(self, c: Ctx, P: Parts, at_rects):
        # speaker cones
        for (p, r) in self.cones:
            k = 1.0 + 0.12 * c.env["sub"] * (1.0 if c.kick else 0.3) * (0.5 + c.env["beat"])
            P.m("quad", A(tuple(p), (r * 2 * k, r * 2 * k, 1)), (1, 1, 1), 6, extra=(c.env["sub"], 0, 0, 0))
        # TV wall channels change on bars; whole wall syncs on phrase downbeats
        bi = c.bar_idx
        for k, p in enumerate(self.tvs):
            h = (k * 2654435761 + bi * 40503) & 0xFFFF
            if c.energy < 0.35:
                ch = [3, 4, 2][h % 3]
            elif c.events and any(ev.kind == "vocals" for ev in c.events):
                ch = [5, 0, 1][h % 3]
            else:
                ch = h % 8
            if bi % 8 == 0:
                ch = (bi // 8) % 8
            bright = 0.9 + 0.5 * c.env["beat"]
            P.m("quad", A(tuple(p), (0.58, 0.44, 1)), (1, 1, 1), 7, extra=(ch, k * 0.37, bright, 0))
        P.point((0, PLAT_TOP + 1.2, -16.6), (0.6, 0.7, 1.0), 0.8 + 0.6 * c.env["beat"], 5.0)
        # turntable platters
        for x in (-0.72, 0.72):
            P.m("cyl", A((x, TABLE_Y + 0.09, -15.55), (0.3, 0.02, 0.3), (0, c.t * 3.5, 0)), (0.18, 0.18, 0.2), 8)
        # moving heads on the truss
        acc = c.accents
        n = 4
        strobe = any(ev.kind == "drop" and 0 <= c.t - ev.t0 < 2.0 for ev in c.events)
        for k in range(n):
            x = -3.3 + k * 2.2
            ph = c.beat_idx // 2 + k
            target_x = math.sin(ph * 1.7 + k) * 9 + math.sin(c.t * 0.4 + k) * 2
            target_z = -4 + math.cos(ph * 1.3 + k * 2) * 6
            # ease towards the new target over the first part of each beat
            e = min(1.0, c.beat_phase * 3) if c.beat_idx % 2 == 0 else 1.0
            prev_ph = ph - 1
            px_ = math.sin(prev_ph * 1.7 + k) * 9 + math.sin(c.t * 0.4 + k) * 2
            pz_ = -4 + math.cos(prev_ph * 1.3 + k * 2) * 6
            tx = px_ + (target_x - px_) * (e * e * (3 - 2 * e))
            tz = pz_ + (target_z - pz_) * (e * e * (3 - 2 * e))
            src = np.array([x, TRUSS_Y - 0.45, -15.6])
            d = np.array([tx, 0.0, tz]) - src
            d /= np.linalg.norm(d)
            col = acc[(k + c.bar_idx) % len(acc)]
            inten = (0.4 + 1.1 * c.energy) * (0.6 + 0.4 * c.env["highmid"])
            if strobe and (c.i // 3) % 2:
                inten *= 0.1
            if c.night < 0.3:
                inten *= 0.4
            P.m("box", A(tuple(src), (0.3, 0.35, 0.3)), (0.1, 0.1, 0.12), 0)
            P.m("box", A(tuple(src - [0, 0.05, 0]), (0.16, 0.06, 0.16)), (1, 1, 1), 9, emis=tuple(v * 3 * inten for v in col))
            P.spot(tuple(src), tuple(d), col, 2.2 * inten, 30.0, 11.0, 5.0)
            end = src + d * (src[1] / max(-d[1], 0.05))
            P.beam(src, end, 0.04, 0.9, tuple(v * 0.06 * inten for v in col), soft=2.0, fade=0.5)
        # lasers in energetic sections at night
        if c.energy > float(self.el.get("lasers", {}).get("min_energy", 0.55)) and c.night > 0.5 and c.kick:
            nl = 8
            src = np.array([0, TRUSS_Y - 0.3, -15.4])
            lcol = [(0.1, 1.0, 0.2), (1.0, 0.1, 0.1), (0.2, 0.3, 1.0)][(c.bar_idx // 4) % 3]
            amp = 0.5 + c.env["onset"]
            for k in range(nl):
                a = (k - (nl - 1) / 2) * 0.12 * amp + math.sin(c.t * 1.3) * 0.5
                el_ = -0.05 + 0.08 * math.sin(c.t * 0.9 + k * 0.4)
                d = np.array([math.sin(a), el_, math.cos(a)])
                P.beam(src, src + d * 70, 0.012, 0.05, tuple(v * 0.9 * (0.3 + c.env["highmid"]) for v in lcol), soft=1.2)
        # DJ wash light
        P.point((0, TRUSS_Y - 1.0, -14.8), acc[c.bar_idx % len(acc)], 1.2 + 1.5 * c.env["beat"] * c.energy, 9.0)
        # tractor beacon: one revolution every two beats
        T = self.tractor_T
        bp = apply(T, (0, 2.55, -0.6))
        ang = (c.beat_idx + c.beat_phase) * math.pi
        P.m("cyl", A(tuple(bp), (0.22, 0.2, 0.22)), (1, 0.5, 0), 9, emis=(3.0, 1.2, 0.0))
        d = np.array([math.cos(ang), -0.15, math.sin(ang)])
        P.spot(tuple(bp), tuple(d), (1.0, 0.45, 0.0), 1.8, 22.0, 20.0, 8.0)
        P.beam(bp, bp + d * 8, 0.05, 0.8, (0.12, 0.05, 0.0), soft=2.0, fade=0.8)
        # exhaust smoke ring each bar
        ex = apply(T, (0.35, 2.7, 1.3))
        age = c.bar_frac * (60 / max(c.bpm, 60)) * 4
        P.dot(ex + [0.2 * age, 0.6 * age, 0], 0.15 + 0.3 * age, (0.08 * max(0, 1 - age / 1.8),) * 3, soft=2.5)
        # campfire
        fl = 0.8 + 0.4 * c.env["high"] + 0.2 * math.sin(c.t * 13)
        for k in range(10):
            life = ((c.t * 0.9 + k / 10) % 1.0)
            jx = math.sin(c.t * 3 + k * 1.7) * 0.2 * (1 - life)
            p = CAMPFIRE + [jx, 0.2 + life * 1.4 * fl, math.cos(k * 2.1) * 0.15]
            P.dot(p, 0.28 * (1 - life) + 0.08, (0.7 * (1 - life), 0.28 * (1 - life) ** 2, 0.03), soft=2.5)
        P.point(tuple(CAMPFIRE + [0, 0.8, 0]), (1.0, 0.5, 0.15), 1.6 * fl, 8.0)
        # bar tent glow
        P.point(tuple(BAR_POS + [0, 2.2, 0]), (1.0, 0.8, 0.5), 1.2, 7.0)
        # bales bounce on the kick (squash and stretch)
        sq = (0.12 * c.env["sub"] * (1 - c.beat_phase)) if c.kick else 0.0
        for k, b in enumerate(self.bales):
            hop = sq * (1.0 if (k + c.beat_idx) % 2 == 0 else 0.4)
            P.m("box", A(tuple(b + [0, hop * 0.8, 0]), (1.2 * (1 + hop * 0.3), 0.5 * (1 - hop * 0.6), 0.6)), (1, 1, 1), 3)

    def _jelly_arrays(self):
        J = [(ti, j) for ti, tr in enumerate(self.trees) for j in tr["jelly"]]
        self.j_tree = np.array([ti for ti, _ in J])
        self.j_anchor = np.array([j["anchor"] for _, j in J])
        self.j_L = np.array([j["L"] for _, j in J])
        self.j_size = np.array([j["size"] for _, j in J])
        self.j_hue = np.array([j["hue"] for _, j in J])
        self.j_ph = np.array([j["ph"] for _, j in J])
        self.j_lag = np.array([j["lag"] for _, j in J])

    def _trees(self, c: Ctx, P: Parts):
        if not hasattr(self, "j_anchor"):
            self._jelly_arrays()
        wdx, wdz, ws, wph = c.wind
        lowmid, hi = c.env["lowmid"], c.env["high"]
        pride = any(ev.kind == "pride_jelly" for ev in c.events)
        t = c.t
        A_, L, sz0, ph, lag = self.j_anchor, self.j_L, self.j_size, self.j_ph, self.j_lag
        nJ = len(L)
        w0 = self.wind_hist(t - lag)
        ang = 0.55 * w0 + np.sin(t * 1.3 + ph) * 0.08 + np.sin(t * 2.9 + ph * 2) * 0.03
        sa, ca = np.sin(ang), np.cos(ang)
        pos = A_ + np.stack([wdx * sa * L, -ca * L, wdz * sa * L], 1)
        pulse = 0.5 + 0.15 * np.sin(t * 3.0 + ph) + lowmid * 0.5
        sz = sz0 * (1 + 0.15 * pulse)
        hsy = sz * (1.1 - 0.25 * pulse)
        cols = hue_np(self.j_hue + c.T * 0.01, 0.75, 1.0)
        glow = 0.35 + 1.4 * hi + 0.4 * c.env["beat"]
        emis = cols * glow
        base = pos - np.stack([np.zeros(nJ), hsy * 0.25, np.zeros(nJ)], 1)
        # bell instances: scale (2sz, hsy, 2sz), small tilt with the swing
        rx, rz = ang * wdz * 0.8, -ang * wdx * 0.8
        cx_, sx_, cz_, sz_ = np.cos(rx), np.sin(rx), np.cos(rz), np.sin(rz)
        R = np.zeros((nJ, 3, 3))
        R[:, 0, 0], R[:, 0, 1] = cz_, -sz_
        R[:, 1, 0], R[:, 1, 1], R[:, 1, 2] = cx_ * sz_, cx_ * cz_, -sx_
        R[:, 2, 0], R[:, 2, 1], R[:, 2, 2] = sx_ * sz_, sx_ * cz_, cx_
        S = np.stack([sz * 2, hsy, sz * 2], 1)
        Mx = np.zeros((nJ, 3, 4))
        Mx[:, :, :3] = R * S[:, None, :]
        Mx[:, :, 3] = base
        rows = np.zeros((nJ, 24), np.float32)
        rows[:, 0:12] = Mx.reshape(nJ, 12)
        rows[:, 12:15] = 1
        rows[:, 15] = 10
        rows[:, 16:19] = emis
        rows[:, 20] = 0.5 + hi
        if pride:
            k = np.arange(nJ)
            rows[:, 21] = np.where((k + self.j_tree) % 2 == 0, 1 + (k + self.j_tree) % 5, 0)
        P.jelly["bell"].append(rows)
        # strings
        top = pos + np.stack([np.zeros(nJ), hsy * 0.7, np.zeros(nJ)], 1)
        sr = np.zeros((nJ, 20), np.float32)
        sr[:, 0:3], sr[:, 3], sr[:, 4:7], sr[:, 7] = A_, 0.006, top, 0.006
        sr[:, 8:11], sr[:, 11], sr[:, 12], sr[:, 13] = 0.06, 1, 1, 1.0
        P.glows_many(sr)
        # tentacles trail the bell, each segment lagging further behind the gusts
        Q, NS = 6, 6
        th = np.arange(Q) / Q * 2 * np.pi
        p = base[:, None, :] + np.stack([np.cos(th)[None] * sz[:, None] * 0.8, np.zeros((nJ, Q)),
                                         np.sin(th)[None] * sz[:, None] * 0.8], -1)
        seg = 0.13 + 0.05 * (np.arange(Q) % 3)
        qq = np.arange(Q)[None, :]
        out = []
        tcol = emis * 0.35
        for s_ in range(NS):
            wl = self.wind_hist(t - lag - 0.09 * (s_ + 1))
            aa = 0.9 * wl[:, None] + 0.25 * np.sin(t * 4 + qq + s_ * 0.7 + ph[:, None])
            d = np.stack([wdx * np.sin(aa) + 0.1 * np.sin(t * 2 + qq), -np.cos(aa), wdz * np.sin(aa)], -1)
            p2 = p + d * seg[None, :, None]
            w = 0.03 * (1 - s_ / 7)
            r = np.zeros((nJ, Q, 20), np.float32)
            r[..., 0:3], r[..., 3], r[..., 4:7], r[..., 7] = p, w, p2, w * 0.8
            r[..., 8:11] = tcol[:, None, :]
            r[..., 11], r[..., 12], r[..., 13] = 1, 1, 1.2
            out.append(r.reshape(-1, 20))
            p = p2
        P.glows_many(np.concatenate(out))
        # one light per tree from its jellyfish
        for ti, tr in enumerate(self.trees):
            m = self.j_tree == ti
            if m.any():
                P.point((tr["x"], tr["h"] - 0.2, tr["z"]), tuple(cols[m].mean(0) * glow), 0.9 + 0.8 * hi, 7.0)

    def _fairy_lights(self, c: Ctx, P: Parts):
        n = len(self.bulbs)
        k = np.arange(n)
        chase = ((k + c.beat_idx * 3) % 7 == 0).astype(float)
        hi = c.env["high"]
        b = 0.25 + 0.5 * hi + 1.2 * chase * c.env["beat"]
        hues = (k * 0.13 + c.bar_idx * 0.05) % 1.0
        cols = hue_np(hues[: min(n, 400)], 0.7, 1.0)
        rows = np.zeros((len(cols), 20), np.float32)
        rows[:, 0:3] = self.bulbs[: len(cols)]
        rows[:, 3] = 0.07
        rows[:, 8:11] = cols * b[: len(cols), None] * 2.2
        rows[:, 11] = 1
        rows[:, 12] = 3
        rows[:, 13] = 3
        P.glows_many(rows)

    def _flags(self, c: Ctx, P: Parts, at_rects):
        poles, bunt, style, rk = self.flags_at(c.t)
        wdx, wdz = c.wind[0], c.wind[1]
        yaw = math.atan2(wdx, wdz) - math.pi / 2
        c.flags_up = [p for p in poles if p]
        for (x, z), name in zip(FLAGPOLES, poles):
            if not name:
                continue
            uv = at_rects[f"flag_{name}"]
            y = 3.6 + 1.0 * rk
            P.m("flag", A((x, y, z), (1.7, 1.05, 1.0), (0, yaw, 0)), (1, 1, 1), 1, sway=1.0 + c.env["beat"], extra=uv)
        if bunt and rk > 0:
            names = PRIDE_FLAGS
            for li, (line, dirv) in enumerate(self.bunting):
                yawb = math.atan2(dirv[0], dirv[2]) - math.pi / 2
                for k, p in enumerate(line):
                    fl = FLAGS.get(names[(li * 3 + style) % len(names)]) or FLAGS["rainbow"]
                    col = tuple(max(0.22, v / 255) for v in fl[k % len(fl)])
                    s = 0.42 * rk
                    P.m("pennant", A(tuple(p), (s, -s * 1.1, 1), (0, yawb, 0)), col, 0, sway=0.6)

    def _farm(self, c: Ctx, P: Parts, at_rects):
        # cows head-bang in the pasture on the beat
        for k, cow in enumerate(self.cows):
            frame = "bang" if (c.kick and (c.beat_idx + k) % 2 == 0 and c.beat_phase < 0.35) else ("chew" if (c.bar_idx + k) % 3 else "stand")
            uv = at_rects[f"cow_{frame}"]
            P.sprite((cow["x"], 0, cow["z"]), 2.4, 1.6, uv, flip=cow["flip"])
            P.shadow(cow["x"], cow["z"], 2.2, 0.9)
        for k, sh in enumerate(self.sheep):
            jump = c.beat_idx % 4 == k % 4 and c.beat_phase < 0.5
            uv = at_rects[f"sheep{1 if jump else 0}"]
            P.sprite((sh["x"], 0.25 * math.sin(math.pi * min(1, c.beat_phase * 2)) if jump else 0, sh["z"]), 1.1, 0.8, uv)
        # chickens peck and head-bob in perfect sync with the beat
        for k, ch in enumerate(self.chickens):
            x = ch["x"] + math.sin(c.t * 0.05 * ch["sp"] + ch["ph"] * 6) * 6
            z = ch["z"] + math.cos(c.t * 0.04 * ch["sp"] + ch["ph"] * 3) * 2
            fr = "fwd" if c.beat_phase < 0.5 else "back"
            if (c.bar_idx + k) % 4 == 3:
                fr = "peck" if c.beat_phase < 0.5 else "stand"
            P.sprite((x, 0, z), 0.6, 0.6, at_rects[f"chicken_{fr}"], flip=math.cos(c.t * 0.05 * ch["sp"] + ch["ph"] * 6) < 0)
        # the vibing cat on the car roof nods on every beat
        T = self.car_T
        p = apply(T, (0.15, 1.18, -0.5))
        fr = ["l", "c", "r", "c"][(c.beat_idx % 2) * 2 + (1 if c.beat_phase > 0.5 else 0)]
        P.sprite(tuple(p), 0.55, 0.55, at_rects[f"cat_{fr}"])
        # windpump wheel turns with the wind
        wp = self.windpump
        ang = c.wind[3] * 0.8
        for k in range(8):
            a = ang + k * math.pi / 4
            P.m("box", A(tuple(wp + [math.cos(a) * 1.2, math.sin(a) * 1.2, 0]), (0.25, 2.2, 0.05), (0, 0, a - math.pi / 2)), (0.8, 0.8, 0.82), 8)
        # farmhouse windows
        for k, wpos in enumerate(self.house_windows):
            on = 0.6 if c.night > 0.4 and k != 1 else 0.0
            P.m("quad", A(tuple(wpos), (1.2, 1.2, 1)), (1, 1, 1), 9, emis=(on * 1.5, on * 1.1, on * 0.5))

    def _tetris(self, c: Ctx, P: Parts):
        b = int(np.clip(c.beat_idx, 0, len(self.tet_board) - 1))
        o = self.tet_origin
        board = self.tet_board[b]
        s = 0.62
        flash = 0.0
        if self.tet_clear[b] and c.beat_phase < 0.5:
            flash = 1.0 - c.beat_phase * 2
        ys, xs = np.nonzero(board)
        for y, x in zip(ys, xs):
            col = self.tet_cols[board[y, x] - 1]
            P.m("box", A(tuple(o + [x * s, y * s * 0.8, 0]), (s * 0.97, s * 0.78, 0.7)), tuple(0.45 + 0.55 * v for v in col), 3,
                emis=tuple(v * 0.25 + flash for v in col))
        fall = c.beat_phase
        for (x, y, k) in self.tet_piece[b]:
            if k < 0:
                continue
            col = self.tet_cols[k - 1]
            yy = (y + 1 - min(1.0, fall * 4)) * s * 0.8
            P.m("box", A(tuple(o + [x * s, yy, 0]), (s * 0.97, s * 0.78, 0.7)), tuple(0.45 + 0.55 * v for v in col), 3,
                emis=tuple(v * 0.4 for v in col))

    def _turbines(self, c: Ctx, P: Parts):
        for k, p in enumerate(self.turbines):
            P.m("cyl6", A(tuple(p), (2.2, 62, 2.2)), (0.75, 0.76, 0.8), 0)
            hub = p + [0, 62, 1.5]
            P.m("box", A(tuple(hub - [0, 1.2, 2.5]), (2.0, 2.4, 6)), (0.75, 0.76, 0.8), 0)
            rot = (c.beat_idx + c.beat_phase) / 4 * 2 * math.pi / 3 + k
            for b in range(3):
                a = rot + b * 2 * math.pi / 3
                P.m("box", A(tuple(hub + [0, 0, 0.6]), (1.6, 28, 0.3), (0, 0, a - math.pi / 2)), (0.8, 0.8, 0.85), 0)
            on = (c.beat_idx + k) % 4 == 0 and c.beat_phase < 0.4
            P.dot(hub + [0, 2.6, 0], 2.2, (1.5, 0.05, 0.05) if on else (0.15, 0.0, 0.0), soft=3.0)

    def wind_hist(self, t):
        """Wind gust strength at clip time t (scalar or array), defined by the scene."""
        return self._wind_fn(t)
