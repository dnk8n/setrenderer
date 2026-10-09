"""Soft-bodied voxel creatures in 3D (a nod to Karl Sims' evolved creatures, 1994): up to 3x3x3 voxels, each
empty, bone, flesh, or a muscle that stretches forward or up, simulated as a mass-spring lattice on a height
field. Same idea as the 2D creatures (the gait is locked to the beat, the loudness is their power), with a
third dimension, lower gravity on the moon, and a mountain made from the chapter's spectrum."""
from __future__ import annotations

import math

import numpy as np

from .. import draw as D
from .. import meshes as M
from .base import SIM_HZ, Outcome, Trial
from .soft import MAT_COL, MAT_EDGES, STIFF, beat_phase, soft_window

N3 = 3
NN3 = (N3 + 1) ** 3
NV3 = N3 ** 3
SUB3 = 3
DT3 = 1.0 / (SIM_HZ * SUB3)
DIM3 = NV3 * 3 + 2
EMPTY, RIGID, SOFT, AX, AY = 0, 1, 2, 3, 4


def nid(x, y, z):
    return (y * (N3 + 1) + z) * (N3 + 1) + x


def decode3(g):
    n = len(g)
    mat = np.searchsorted(MAT_EDGES[1:-1], g[:, :NV3], side="right").astype(np.int8)
    for i in range(n):
        m = mat[i].reshape(N3, N3, N3)           # (y, z, x)
        lab = np.zeros(m.shape, int)
        cur, sizes = 0, {}
        for idx in zip(*np.nonzero(m)):
            if lab[idx]:
                continue
            cur += 1
            stack, sz = [idx], 0
            lab[idx] = cur
            while stack:
                a = stack.pop()
                sz += 1
                for d in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)):
                    b = (a[0] + d[0], a[1] + d[1], a[2] + d[2])
                    if all(0 <= b[k] < N3 for k in range(3)) and m[b] and not lab[b]:
                        lab[b] = cur
                        stack.append(b)
            sizes[cur] = sz
        if not sizes or max(sizes.values()) < 4:
            m[:] = 0
            m[0, :, :] = SOFT
            m[0, 1, 0], m[0, 1, 2] = AX, AX
            m[0, 0, 1], m[0, 2, 1] = AY, AY
        else:
            best = max(sizes, key=lambda k: (sizes[k], -k))
            m[lab != best] = 0
        ys = np.nonzero(m.any((1, 2)))[0]
        if ys[0] > 0:
            m[:] = np.roll(m, -ys[0], axis=0)
        mat[i] = m.ravel()
    phase = g[:, NV3:2 * NV3]
    amp = 0.35 + 0.65 * g[:, 2 * NV3:3 * NV3]
    cyc = np.array([1.0, 2.0, 4.0])[np.minimum((g[:, 3 * NV3] * 3).astype(int), 2)]
    stiff = 0.7 + 0.6 * g[:, 3 * NV3 + 1]
    return mat, phase, amp, cyc, stiff


def _voxel_springs():
    """For one voxel: (node a, node b, rest dx, dy, dz) offsets from its corner (0, 0, 0)."""
    out = []
    corners = [(x, y, z) for x in (0, 1) for y in (0, 1) for z in (0, 1)]
    for a in corners:
        for b in corners:
            d = tuple(bb - aa for aa, bb in zip(a, b))
            if a < b and sum(abs(v) for v in d) in (1, 2):
                out.append((a, b, tuple(abs(v) for v in d)))
    return out


VSPR = _voxel_springs()          # 12 edges + 12 face diagonals
FACES = [((0, 0, 0), (0, 1, 0), (0, 1, 1), (0, 0, 1), (-1, 0, 0)), ((1, 0, 0), (1, 0, 1), (1, 1, 1), (1, 1, 0), (1, 0, 0)),
         ((0, 0, 0), (0, 0, 1), (1, 0, 1), (1, 0, 0), (0, -1, 0)), ((0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1), (0, 1, 0)),
         ((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0), (0, 0, -1)), ((0, 0, 1), (0, 1, 1), (1, 1, 1), (1, 0, 1), (0, 0, 1))]


class Bodies3:
    def __init__(self, g):
        n = self.n = len(g)
        mat, phase, amp, cyc, stiff = decode3(g)
        self.mat, self.cyc, self.phase_v, self.amp_v = mat, cyc, phase, amp
        si, sj, kk, ddx, ddy, ddz, vox = [], [], [], [], [], [], []
        used = np.zeros((n, NN3), bool)
        for i in range(n):
            a_, b_, k_, x_, y_, z_, v_ = [], [], [], [], [], [], []
            for v in range(NV3):
                m = mat[i, v]
                if m == 0:
                    continue
                vy, vz, vx = v // (N3 * N3), (v // N3) % N3, v % N3
                for (a, b, d) in VSPR:
                    ia = nid(vx + a[0], vy + a[1], vz + a[2])
                    ib = nid(vx + b[0], vy + b[1], vz + b[2])
                    a_.append(ia + i * NN3)
                    b_.append(ib + i * NN3)
                    k_.append(STIFF[m] * stiff[i] * (1.0 if sum(d) == 1 else 0.7))
                    x_.append(d[0])
                    y_.append(d[1])
                    z_.append(d[2])
                    v_.append(i * NV3 + v)
                    used[i, ia] = used[i, ib] = True
            si += a_
            sj += b_
            kk += k_
            ddx += x_
            ddy += y_
            ddz += z_
            vox += v_
        self.gi, self.gj = np.array(si, np.int64), np.array(sj, np.int64)
        self.gij = np.concatenate([self.gi, self.gj])
        self.K = np.array(kk)
        self.dx, self.dy, self.dz = np.array(ddx, float), np.array(ddy, float), np.array(ddz, float)
        self.vox = np.array(vox, np.int64)
        mv = mat.ravel()[self.vox]
        self.ax = (mv == AX).astype(float)
        self.ay = (mv == AY).astype(float)
        self.used = used
        idx = np.arange(NN3)
        self.rest = np.stack([idx % (N3 + 1), idx // ((N3 + 1) ** 2), (idx // (N3 + 1)) % (N3 + 1)], -1).astype(float)
        w = used.astype(float)
        self.w = w / np.maximum(w.sum(1, keepdims=True), 1)
        ry = self.rest[:, 1]
        self.top = np.array([(u & (ry == ry[u].max())) for u in used]) if n else np.zeros((0, NN3), bool)
        self.bot = np.array([(u & (ry == ry[u].min())) for u in used]) if n else np.zeros((0, NN3), bool)
        self.tall = np.array([ry[u].max() - ry[u].min() > 0 for u in used]) if n else np.zeros(0, bool)
        # exterior faces for drawing: (voxel, face) where the neighbour is empty
        self.faces = []
        for i in range(n):
            m = mat[i].reshape(N3, N3, N3)
            fl = []
            for v in np.nonzero(mat[i])[0]:
                vy, vz, vx = v // (N3 * N3), (v // N3) % N3, v % N3
                for f in FACES:
                    nx, ny, nz = vx + f[4][0], vy + f[4][1], vz + f[4][2]
                    if 0 <= nx < N3 and 0 <= ny < N3 and 0 <= nz < N3 and m[ny, nz, nx]:
                        continue
                    q = [nid(vx + c[0], vy + c[1], vz + c[2]) for c in f[:4]]
                    fl.append((*q, int(mat[i, v]), int(v)))
            self.faces.append(np.array(fl, np.int64).reshape(-1, 6))


class Ground3:
    """A height field on a regular (x, z) grid."""

    def __init__(self, H: np.ndarray, x0: float, z0: float, d: float):
        self.H, self.x0, self.z0, self.d = H, x0, z0, d
        self.gx = np.gradient(H, d, axis=1)
        self.gz = np.gradient(H, d, axis=0)

    def sample(self, x, z):
        fx = np.clip((x - self.x0) / self.d, 0, self.H.shape[1] - 1.001)
        fz = np.clip((z - self.z0) / self.d, 0, self.H.shape[0] - 1.001)
        i, j = fz.astype(np.int64), fx.astype(np.int64)
        u, v = fx - j, fz - i
        H = self.H
        h = (H[i, j] * (1 - u) * (1 - v) + H[i, j + 1] * u * (1 - v) + H[i + 1, j] * (1 - u) * v + H[i + 1, j + 1] * u * v)
        return h, self.gx[i, j], self.gz[i, j]


def simulate3(B: Bodies3, ground: Ground3, win: dict, start, steps: int, record: bool, g=25.0, mu=0.6, hooks=None,
              heading=0.0):
    n = B.n
    x = np.zeros((n, NN3))
    y = np.zeros((n, NN3))
    z = np.zeros((n, NN3))
    sx, sz = start
    ch, sh = math.cos(heading), math.sin(heading)
    rx, rz = B.rest[None, :, 0] - 1.5, B.rest[None, :, 2] - 1.5
    x[:] = sx + ch * rx - sh * rz
    z[:] = sz + sh * rx + ch * rz
    h0, _, _ = ground.sample(np.full(1, sx), np.full(1, sz))
    y[:] = h0[0] + 0.15 + B.rest[None, :, 1]
    vx, vy, vz = np.zeros_like(x), np.zeros_like(x), np.zeros_like(x)
    used = B.used.astype(float)
    alive = np.ones(n, bool)
    t_dead = np.full(n, np.inf)
    cause = np.zeros(n, np.int16)
    tsub = np.arange(steps * SUB3 + 1) * DT3
    bp = beat_phase(win["beats"], tsub, win["period"])
    power = np.interp(tsub, np.arange(len(win["power"])) / SIM_HZ, win["power"])
    rec = np.zeros((steps + 1, n, NN3, 3), np.float32) if record else None
    if record:
        rec[0] = np.stack([x, y, z], -1)
    gi, gj, gij = B.gi, B.gj, B.gij
    K, dx0, dy0, dz0, vox = B.K, B.dx, B.dy, B.dz, B.vox
    amp_v = 0.36 * B.amp_v
    inv_cyc = 1.0 / B.cyc[:, None]
    NT = n * NN3
    keep = 1.0 - 0.15 * DT3
    flipped = np.zeros(n)
    for f in range(steps):
        for s in range(SUB3):
            q = f * SUB3 + s
            a = (amp_v * (power[q] * np.sin(2 * np.pi * (bp[q] * inv_cyc + B.phase_v)))).ravel()[vox]
            L = np.sqrt((dx0 * (1 + a * B.ax)) ** 2 + (dy0 * (1 + a * B.ay)) ** 2 + dz0 ** 2)
            xf, yf, zf = x.ravel(), y.ravel(), z.ravel()
            ex, ey, ez = xf[gj] - xf[gi], yf[gj] - yf[gi], zf[gj] - zf[gi]
            dist = np.sqrt(ex * ex + ey * ey + ez * ez) + 1e-9
            ux, uy, uz = ex / dist, ey / dist, ez / dist
            vxf, vyf, vzf = vx.ravel(), vy.ravel(), vz.ravel()
            rel = (vxf[gj] - vxf[gi]) * ux + (vyf[gj] - vyf[gi]) * uy + (vzf[gj] - vzf[gi]) * uz
            fm = K * (dist - L) + 5.0 * rel
            Fx = np.bincount(gij, np.concatenate([fm * ux, -fm * ux]), NT).reshape(n, NN3)
            Fy = np.bincount(gij, np.concatenate([fm * uy, -fm * uy]), NT).reshape(n, NN3) - g
            Fz = np.bincount(gij, np.concatenate([fm * uz, -fm * uz]), NT).reshape(n, NN3)
            m = used * alive[:, None]
            vx = (vx + Fx * DT3) * keep * m
            vy = (vy + Fy * DT3) * keep * m
            vz = (vz + Fz * DT3) * keep * m
            x = x + vx * DT3
            y = y + vy * DT3
            z = z + vz * DT3
            h, gx, gz = ground.sample(x, z)
            pen = h - y
            hit = pen > 0
            if hit.any():
                inv = 1.0 / np.sqrt(1 + gx * gx + gz * gz)
                nx, ny, nz = -gx * inv, inv, -gz * inv
                vn = vx * nx + vy * ny + vz * nz
                dvn = np.where(hit, np.maximum(-vn, 0.0), 0.0)
                tx, ty, tz = vx - vn * nx, vy - vn * ny, vz - vn * nz
                tl = np.sqrt(tx * tx + ty * ty + tz * tz) + 1e-9
                lim = mu * (dvn + g * DT3)
                sc = np.where(hit, np.maximum(tl - lim, 0.0) / tl, 1.0)
                vn2 = vn + dvn
                vx = np.where(hit, vn2 * nx + tx * sc, vx)
                vy = np.where(hit, vn2 * ny + ty * sc, vy)
                vz = np.where(hit, vn2 * nz + tz * sc, vz)
                y = np.where(hit, h, y)
            if hooks is not None:
                c = hooks(tsub[q] + DT3, x, y, z, alive)
                newly = alive & (c > 0)
                if newly.any():
                    t_dead[newly] = tsub[q] + DT3
                    cause[newly] = c[newly]
                    alive &= ~newly
        up = ((y * B.top).sum(1) / np.maximum(B.top.sum(1), 1) - (y * B.bot).sum(1) / np.maximum(B.bot.sum(1), 1))
        flipped = np.where(B.tall & (up < -0.3), flipped + 1, 0)
        fl = alive & (flipped > 0.9 * SIM_HZ)
        if fl.any():
            t_dead[fl] = (f + 1) / SIM_HZ
            cause[fl] = 1
            alive &= ~fl
        if record:
            rec[f + 1] = np.stack([x, y, z], -1)
    if not record:
        rec = np.stack([x, y, z], -1)[None]
    return rec, t_dead, cause, alive


def creature_soup(B: Bodies3, P: np.ndarray, i: int, bp: float, alpha=1.0, tint=None, dim=False) -> np.ndarray:
    """Triangles (with normals and colours) for creature i's outer faces at node positions P (64, 3)."""
    F = B.faces[i]
    if len(F) == 0:
        return np.zeros((0, 10), np.float32)
    q = P[F[:, :4]]                                    # (f, 4, 3)
    nrm = np.cross(q[:, 2] - q[:, 0], q[:, 3] - q[:, 1])
    nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-9
    col = np.array([MAT_COL[int(m)] for m in F[:, 4]], np.float32)
    mus = np.isin(F[:, 4], (AX, AY))
    if mus.any():
        ph = B.phase_v[i, F[mus, 5]]
        col[mus] *= (0.75 + 0.45 * (0.5 + 0.5 * np.sin(2 * np.pi * (bp / B.cyc[i] + ph))))[:, None]
    col = np.clip(col, 0, 1)
    if tint is not None:
        col = col * 0.3 + np.asarray(tint, np.float32) * 0.7
    if dim:
        col = col * 0.4 + 0.2
    tri = np.concatenate([q[:, [0, 1, 2]], q[:, [0, 2, 3]]])
    nn = np.concatenate([nrm, nrm])
    cc = np.concatenate([col, col])
    out = np.zeros((len(tri), 3, 10), np.float32)
    out[:, :, 0:3] = tri
    out[:, :, 3:6] = nn[:, None, :]
    out[:, :, 6:9] = cc[:, None, :]
    out[:, :, 9] = alpha
    return out.reshape(-1, 10)


def terrain_mesh(G: Ground3, colour_fn) -> tuple[np.ndarray, np.ndarray]:
    H = G.H
    nz, nx = H.shape
    xs = G.x0 + np.arange(nx) * G.d
    zs = G.z0 + np.arange(nz) * G.d
    X, Z = np.meshgrid(xs, zs)
    nrm = np.stack([-G.gx, np.ones_like(H), -G.gz], -1)
    nrm /= np.linalg.norm(nrm, axis=-1, keepdims=True)
    col = colour_fn(X, H, Z, nrm)
    v = np.zeros((nz * nx, 10), np.float32)
    v[:, 0], v[:, 1], v[:, 2] = X.ravel(), H.ravel(), Z.ravel()
    v[:, 3:6] = nrm.reshape(-1, 3)
    v[:, 6:9] = col.reshape(-1, 3)
    v[:, 9] = 1.0
    i = np.arange(nz * nx).reshape(nz, nx)
    a, b, c, d = i[:-1, :-1].ravel(), i[:-1, 1:].ravel(), i[1:, 1:].ravel(), i[1:, :-1].ravel()
    idx = np.stack([a, c, b, a, d, c], 1).ravel().astype(np.uint32)
    return v, idx


IDENT = M.inst(M.trs([(0, 0, 0)], [1.0]), (1, 1, 1, 1))


class Soft3Trial(Trial):
    style = "lab"
    dims = "3D"
    dim = DIM3
    pop = 24
    ghosts = 3
    g_max = 45
    g_min = 12
    version = 1
    causes = ["OUT OF TIME", "FLIPPED", "FELL"]
    gravity = 25.0
    friction = 0.6

    def window(self, env, mu, t0, t1):
        return soft_window(mu, t0, t1)

    def describe(self, env, g):
        mat = decode3(g[None])[0][0]
        names = {RIGID: "bone", SOFT: "flesh", AX: "stride muscle", AY: "lift muscle"}
        cnt = {names[m]: int((mat == m).sum()) for m in names if (mat == m).any()}
        return f"{int((mat > 0).sum())} voxels: " + ", ".join(f"{v} {k}" for k, v in cnt.items())

    def optimizer(self, env, rng):
        from ..evolve import CMAES
        return CMAES(self.dim, self.pop, rng, sep=True, sigma=0.3)

    def ground(self, env) -> Ground3:
        return Ground3(env["H"], env["x0"], env["z0"], env["d"])

    def goal_reached(self, env, cx, cy, cz):
        raise NotImplementedError

    def progress(self, env, cx, cy, cz):
        raise NotImplementedError

    def rollout(self, env, win, G, record=False):
        steps = int(math.ceil(win["T"] * SIM_HZ))
        if len(G) == 0:
            o = Outcome(np.zeros(0), np.zeros(0, bool), np.zeros(0), np.zeros(0, np.int16))
            if record:
                o.states = {"X": np.zeros((steps + 1, 0, NN3, 3), np.float32)}
            return o
        B = Bodies3(G)
        n = B.n
        gr = self.ground(env)
        best = np.zeros(n)

        def hooks(t, x, y, z, alive):
            cx, cy, cz = (x * B.w).sum(1), (y * B.w).sum(1), (z * B.w).sum(1)
            np.maximum(best, self.progress(env, cx, cy, cz), out=best)
            return np.where(alive & self.goal_reached(env, cx, cy, cz), 99, 0)
        X, td, cause, alive = simulate3(B, gr, win, env["start"], steps, record, self.gravity, self.friction, hooks,
                                        env.get("heading", 0.0))
        succ = cause == 99
        t_end = np.where(np.isfinite(td), td, win["T"])
        fit = np.where(succ, 1.0 + 0.3 * (1 - t_end / win["T"]), np.clip(best, 0, 0.999))
        o = Outcome(fit, succ, t_end, np.where(succ, -1, cause).astype(np.int16))
        if record:
            o.states = {"X": X, "bodies": B}
        return o

    # ---- drawing
    def terrain_colour(self, X, H, Z, nrm):
        return np.stack([0.6 + 0 * H, 0.6 + 0 * H, 0.6 + 0 * H], -1)

    def scene_setup(self, sc, fr, env, focus, f, ctx):
        raise NotImplementedError

    def draw(self, sc, fr, env, win, rec, k, ctx):
        X = rec.states["X"]
        f = int(min(max(k, 0), len(X) - 1))
        T = len(X)
        B = rec.states.get("bodies")
        key = f"terrain-{self.key}-{id(env)}"
        if key not in sc.engine.meshes:
            v, i = terrain_mesh(self.ground(env), self.terrain_colour)
            sc.engine.add_mesh(key, v, i)
        fr.meshes.append((key, IDENT, False))
        if B is not None and B.n:
            c = (X[:, 0] * B.w[0][None, :, None]).sum(1)
            lo, hi = max(0, f - 50), min(T, f + 51)
            focus = c[lo:hi].mean(0)
        else:
            focus = None
        self.scene_setup(sc, fr, env, focus, f, ctx)
        if B is None or not B.n:
            return
        t = f / SIM_HZ
        bp = ctx["beat_phase"]
        soup_t = []
        for i in range(1, B.n):
            dead = t >= rec.t_end[i] and not rec.success[i]
            soup_t.append(creature_soup(B, X[f, i], i, bp, 0.12 if dead else 0.22, tint=(0.75, 0.85, 1.0)))
        if soup_t:
            fr.soup.append((np.concatenate(soup_t), True))
        dead0 = t >= rec.t_end[0] and not rec.success[0]
        fr.soup.append((creature_soup(B, X[f, 0], 0, bp, 1.0, dim=dead0), False))
        # eyes on the featured creature: two white spheres on its front-top
        P = X[f, 0]
        topf = B.top[0] & (B.rest[:, 0] == B.rest[B.used[0], 0].max())
        if topf.any():
            ctr = P[topf].mean(0)
            fwd = P[B.used[0] & (B.rest[:, 0] == B.rest[B.used[0], 0].max())].mean(0) - P[B.used[0]].mean(0)
            fwd /= np.linalg.norm(fwd) + 1e-9
            side = np.cross(fwd, (0, 1, 0))
            side /= np.linalg.norm(side) + 1e-9
            eyes = np.array([ctr + side * 0.3 + (0, 0.12, 0), ctr - side * 0.3 + (0, 0.12, 0)])
            fr.meshes.append(("sphere", M.inst(M.trs(eyes, 0.34), (1, 1, 1, 1), (0.4, 0, 0, 0)), False))
            fr.meshes.append(("sphere", M.inst(M.trs(eyes + fwd * 0.13, 0.16), (0.03, 0.03, 0.05, 1)), False))


class MoonWalk(Soft3Trial):
    key = "moonwalk"
    name = "MOON WALK"
    algo = "SEP-CMA-ES"
    physics = "3D soft bodies · a sixth of earth's gravity · dust"
    goal = "Bound across the craters to the beacon"
    affinity = {"calm": 0.7, "energy": -0.5, "bright": 0.2}
    accent = (0.6, 0.85, 1.0)
    gravity = 6.0
    friction = 0.5

    def level(self, feats):
        return 0.2 + 0.2 * min(1.0, 1.0 - feats["energy"])

    def env(self, mu, ch, rng, level):
        D_ = 4.0 + 12.0 * level
        d = 0.5
        nx, nz = int((D_ + 24) / d), int(24 / d)
        x0, z0 = -8.0, -12.0
        xs = x0 + np.arange(nx) * d
        zs = z0 + np.arange(nz) * d
        Xg, Zg = np.meshgrid(xs, zs)
        H = 0.25 * np.sin(Xg * 0.4) * np.cos(Zg * 0.33)
        hits = mu.events("bass", ch.t0, ch.t1)
        rr = np.random.default_rng([int(rng.integers(1 << 30)), 3])
        for k in range(min(len(hits), 14) if len(hits) else 6):
            cx, cz = rr.uniform(2, D_ + 4), rr.uniform(-8, 8)
            r = rr.uniform(1.0, 2.2 + 1.5 * level)
            dd = np.sqrt((Xg - cx) ** 2 + (Zg - cz) ** 2) / r
            H += -0.9 * r * 0.35 * np.exp(-dd * dd * 2.5) + 0.35 * r * 0.35 * np.exp(-((dd - 1.0) / 0.25) ** 2)
        H -= H[int(-z0 / d), int(-x0 / d)]
        return {"H": H, "x0": x0, "z0": z0, "d": d, "start": (0.0, 0.0), "goal": D_, "level": level}

    def goal_reached(self, env, cx, cy, cz):
        return cx >= env["goal"]

    def progress(self, env, cx, cy, cz):
        return cx / env["goal"]

    def terrain_colour(self, X, H, Z, nrm):
        base = 0.22 + 0.12 * np.clip(H, -1, 1) + 0.04 * np.sin(X * 3.1) * np.cos(Z * 2.7)
        return np.stack([base, base, base * 1.04], -1)

    def scene_setup(self, sc, fr, env, focus, f, ctx):
        g = env["goal"]
        if focus is None:
            x = ctx.get("reveal", 0.0)
            focus = np.array([g * x, 0.0, 0.0])
        tgt = focus + (1.5, 0.0, 0.0)
        eye = tgt + (-9.0, 5.5, 10.5)
        sc.backdrop(fr, (0.0, 0.0, 0.004), (0.004, 0.004, 0.012), horizon=0.5, stars=1.0, sun=(0.82, 0.18, 0.05))
        sc.cam3d(fr, eye, tgt, fov=0.85, sun=(0.6, 0.5, 0.25), sky=(0.02, 0.025, 0.04), ground=(0.05, 0.05, 0.055),
                 fog=0.002, sun_i=1.5, ambient=0.25, shadow_r=16.0)
        sc.tone(False)
        hb = float(self.ground(env).sample(np.array([g]), np.array([0.0]))[0][0])
        fr.meshes.append(("cylinder", M.inst(M.trs([(g, hb + 2.0, 0.0)], [(0.25, 4.0, 0.25)]), (0.8, 0.8, 0.85, 1)), False))
        fr.meshes.append(("sphere", M.inst(M.trs([(g, hb + 4.3, 0.0)], [0.8]),
                                           (0.3, 0.9, 1.0, 1), (2.5 + 1.5 * ctx["kick"], 0, 0, 0)), False))


class Summit(Soft3Trial):
    key = "summit"
    name = "SPECTRUM SUMMIT"
    algo = "ISLAND-MODEL GENETIC ALGORITHM"
    physics = "3D soft bodies · a mountain made of this stretch's spectrum"
    goal = "Climb to the summit of the spectrogram"
    affinity = {"dyn": 0.8, "drops": 0.4, "low": 0.2}
    accent = (1.0, 0.75, 0.3)
    pop = 24

    def level(self, feats):
        return 0.2 + 0.2 * min(1.0, feats["dyn"] * 4)

    def optimizer(self, env, rng):
        from ..evolve import IslandGA
        return IslandGA(self.dim, self.pop, rng, islands=4)

    def env(self, mu, ch, rng, level):
        prof = mu.profile(ch.t0, ch.t1, 16)            # (5 bands, 16 steps)
        d = 0.5
        nx, nz = 60, 44
        x0, z0 = -8.0, -11.0
        from scipy import ndimage
        P = ndimage.zoom(prof, (nz / prof.shape[0], nx / prof.shape[1]), order=1)[:nz, :nx]
        P = ndimage.gaussian_filter(P, 2.5)
        P = (P - P.min()) / max(P.max() - P.min(), 1e-6)
        Xg, Zg = np.meshgrid(x0 + np.arange(nx) * d, z0 + np.arange(nz) * d)
        hd = float(rng.uniform(-0.5, 0.5))
        dist = 4.0 + 8.0 * level
        px, pz = dist * math.cos(hd), dist * math.sin(hd)
        wdt = 3.0 + 3.0 * (1.0 - level)
        cone = np.exp(-((Xg - px) ** 2 + (Zg - pz) ** 2) / (2 * wdt * wdt))
        H = (0.4 + 0.8 * level) * P + (1.0 + 2.5 * level) * cone
        H -= H[int(-z0 / d), int(-x0 / d)]
        top = float(H[int(round((pz - z0) / d)), int(round((px - x0) / d))])
        return {"H": H, "x0": x0, "z0": z0, "d": d, "start": (0.0, 0.0), "peak": (px, top, pz), "level": level,
                "heading": math.atan2(pz, px), "dist": math.hypot(px, pz)}

    def goal_reached(self, env, cx, cy, cz):
        px, top, pz = env["peak"]
        return np.hypot(cx - px, cz - pz) < 1.6

    def progress(self, env, cx, cy, cz):
        px, top, pz = env["peak"]
        return 1.0 - np.hypot(cx - px, cz - pz) / env["dist"]

    def terrain_colour(self, X, H, Z, nrm):
        h = (H - H.min()) / max(H.max() - H.min(), 1e-6)
        stops = np.array([[0.02, 0.04, 0.16], [0.03, 0.22, 0.30], [0.22, 0.50, 0.10], [0.80, 0.45, 0.06], [0.9, 0.85, 0.8]])
        k = np.clip(h * 4, 0, 3.999)
        i = k.astype(int)
        u = (k - i)[..., None]
        c = stops[i] * (1 - u) + stops[i + 1] * u
        lines = (np.abs(((H * 4) % 1.0) - 0.5) > 0.47)[..., None] * 0.15
        return c * (1 - lines) + lines * 0.0

    def scene_setup(self, sc, fr, env, focus, f, ctx):
        px, top, pz = env["peak"]
        if focus is None:
            x = ctx.get("reveal", 0.0)
            ang = 2.4 * x
            focus = np.array([px * 0.5, top * 0.4, pz * 0.5])
            eye = focus + (15 * math.cos(ang + 3.6), 11.0, 15 * math.sin(ang + 3.6))
        else:
            hd = env["heading"]
            eye = focus + (-9.5 * math.cos(hd) + 5 * math.sin(hd), 7.5, -9.5 * math.sin(hd) - 5 * math.cos(hd))
        sc.backdrop(fr, (0.10, 0.25, 0.65), (0.65, 0.55, 0.50), horizon=0.55, stars=0.0, sun=(0.2, 0.2, 0.04))
        sc.cam3d(fr, eye, focus, fov=0.9, sun=(-0.4, 0.8, 0.35), sky=(0.25, 0.38, 0.6), ground=(0.12, 0.1, 0.08),
                 fog=0.004, sun_i=1.4, ambient=0.35, shadow_r=18.0)
        sc.tone(False)
        fr.meshes.append(("cone", M.inst(M.trs([(px, top + 0.8, pz)], [(0.5, 1.6, 0.5)]), (1.0, 0.3, 0.3, 1),
                                         (0.8 + ctx["kick"], 0, 0, 0)), False))
