"""Soft-bodied voxel creatures in 2D (after EvoGym, Bhatia et al. 2021): a body of up to 5x5 voxels, each empty,
rigid, soft, or a muscle that stretches sideways or up and down, simulated as a mass-spring lattice. The genome
holds the body and the gait: each muscle's phase and strength in a rhythm locked to the set's beats, so the
creatures literally walk to the music, and the music's loudness is their power. Many genomes run at once as
one set of arrays, each creature's arithmetic its own (batch-independent, so a replay is exact).

The physics (gravity, friction, water, falling rocks, an egg to carry, an opponent to push) is switched on per
trial; the trials built on it are below."""
from __future__ import annotations

import math

import numpy as np

from .. import draw as D
from .base import SIM_HZ, Outcome, Trial

GS = 5                       # voxels per side
NN = (GS + 1) ** 2           # nodes per creature
NV = GS * GS
NS = NV * 6                  # springs per creature (4 edges and 2 diagonals per voxel)
SUB = 3                      # substeps per frame
DT = 1.0 / (SIM_HZ * SUB)
EMPTY, RIGID, SOFT, HACT, VACT = 0, 1, 2, 3, 4
MAT_EDGES = np.array([0.0, 0.17, 0.36, 0.55, 0.78, 1.0])
STIFF = np.array([0.0, 1500.0, 380.0, 650.0, 650.0])
DIM = NV * 3 + 3

MAT_COL = {RIGID: (0.20, 0.24, 0.32), SOFT: (0.78, 0.80, 0.84), HACT: (1.00, 0.55, 0.16), VACT: (0.14, 0.72, 0.78)}


def decode(g: np.ndarray):
    """genes (n, DIM) -> materials (n, 25), phases, strengths, cycle in beats, stiffness scale."""
    n = len(g)
    mat = np.searchsorted(MAT_EDGES[1:-1], g[:, :NV], side="right").astype(np.int8)
    # keep the largest 4-connected piece; a body of fewer than four voxels gets a default block
    for i in range(n):
        m = mat[i].reshape(GS, GS)
        lab = np.zeros((GS, GS), int)
        cur = 0
        sizes = {}
        for r in range(GS):
            for c in range(GS):
                if m[r, c] and not lab[r, c]:
                    cur += 1
                    stack = [(r, c)]
                    lab[r, c] = cur
                    sz = 0
                    while stack:
                        a, b = stack.pop()
                        sz += 1
                        for da, db in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                            x, y = a + da, b + db
                            if 0 <= x < GS and 0 <= y < GS and m[x, y] and not lab[x, y]:
                                lab[x, y] = cur
                                stack.append((x, y))
                    sizes[cur] = sz
        if not sizes or max(sizes.values()) < 4:
            m[:] = 0
            m[0, 1:4] = (HACT, RIGID, HACT)
            m[1, 1:4] = (VACT, SOFT, VACT)
        else:
            best = max(sizes, key=lambda k: (sizes[k], -k))
            m[lab != best] = 0
        # rest the body on its lowest row
        rows = np.nonzero(m.any(1))[0]
        if rows[0] > 0:
            m[:] = np.roll(m, -rows[0], axis=0)
        cols = np.nonzero(m.any(0))[0]
        if cols[0] > 0:
            m[:] = np.roll(m, -cols[0], axis=1)
        mat[i] = m.ravel()
    phase = g[:, NV:2 * NV]
    amp = 0.35 + 0.65 * g[:, 2 * NV:3 * NV]
    cyc = np.array([1.0, 2.0, 4.0])[np.minimum((g[:, 3 * NV] * 3).astype(int), 2)]
    stiff = 0.7 + 0.6 * g[:, 3 * NV + 1]
    return mat, phase, amp, cyc, stiff


def skew_of(g: np.ndarray) -> np.ndarray:
    """How lopsided each muscle's stroke is (-1..1): a quick push and a slow return, or the other way."""
    return 2.0 * g[:, 3 * NV + 2] - 1.0 if g.shape[1] > 3 * NV + 2 else np.zeros(len(g))


class Bodies:
    """The springs and nodes of n creatures (fixed slots, unused ones inert)."""

    def __init__(self, g: np.ndarray):
        n = self.n = len(g)
        mat, phase, amp, cyc, stiff = decode(g)
        self.mat, self.cyc = mat, cyc
        self.skew = skew_of(g)[:, None]
        si = np.zeros((n, NS), np.int64)
        sj = np.zeros((n, NS), np.int64)
        L0 = np.ones((n, NS))
        k = np.zeros((n, NS))
        kind = np.zeros((n, NS), np.int8)     # 0 passive, 1 stretches with the voxel's sideways muscle, 2 up/down, 3 diagonal
        ph = np.zeros((n, NS))
        am = np.zeros((n, NS))
        mv = np.zeros((n, NS), np.int8)
        used = np.zeros((n, NN), bool)
        surf = np.zeros((n, NS), bool)
        mg = mat.reshape(n, GS, GS)
        pad = np.zeros((n, GS + 2, GS + 2), np.int8)
        pad[:, 1:-1, 1:-1] = mg
        for v in range(NV):
            r, c = divmod(v, GS)
            # edges facing an empty neighbour are the body's surface (only they push on water)
            nbr = (pad[:, r, c + 1], pad[:, r + 2, c + 1], pad[:, r + 1, c], pad[:, r + 1, c + 2])
            for e in range(4):
                surf[:, v * 6 + e] = (mat[:, v] > 0) & (nbr[e] == 0)
            bl, br, tl, tr = r * (GS + 1) + c, r * (GS + 1) + c + 1, (r + 1) * (GS + 1) + c, (r + 1) * (GS + 1) + c + 1
            pairs = ((bl, br, 1.0, 1), (tl, tr, 1.0, 1), (bl, tl, 1.0, 2), (br, tr, 1.0, 2),
                     (bl, tr, math.sqrt(2), 3), (br, tl, math.sqrt(2), 3))
            m = mat[:, v]
            on = m > 0
            for e, (a, b, l0, kd) in enumerate(pairs):
                s = v * 6 + e
                si[:, s], sj[:, s], L0[:, s] = a, b, l0
                k[:, s] = STIFF[m] * stiff * (1.0 if kd < 3 else 0.7)
                act = ((m == HACT) & (kd == 1)) | ((m == VACT) & (kd == 2)) | (((m == HACT) | (m == VACT)) & (kd == 3))
                kind[:, s] = np.where(act, kd, 0)
                ph[:, s], am[:, s] = phase[:, v], amp[:, v]
                mv[:, s] = m
            for a in (bl, br, tl, tr):
                used[:, a] |= on
        self.si, self.sj, self.L0, self.k, self.kind, self.ph, self.am, self.mv = si, sj, L0, k, kind, ph, am, mv
        self.used = used
        self.phase_v, self.amp_v = phase, amp
        # only the springs that exist, creature by creature in a fixed order (batch-independent sums)
        live = (k > 0).ravel()
        off = (np.arange(n) * NN)[:, None]
        self.gi = (si + off).ravel()[live]
        self.gj = (sj + off).ravel()[live]
        self.gij = np.concatenate([self.gi, self.gj])
        self.K = k.ravel()[live]
        self.surf = surf.ravel()[live]
        self.L0c = L0.ravel()[live]
        kd = kind.ravel()[live]
        self.edge_act = ((kd == 1) | (kd == 2)).astype(np.float64)
        self.is_diag_act = kd == 3
        vox = np.repeat(np.arange(NV), 6)[None, :] + (np.arange(n) * NV)[:, None]
        self.vox = vox.ravel()[live]
        self.hact = (mv == HACT)
        self.vact = (mv == VACT)
        rows = np.arange(NN) // (GS + 1)
        cols = np.arange(NN) % (GS + 1)
        self.rest = np.stack([cols, rows], -1).astype(np.float64)        # (36, 2) in voxel units
        w = used.astype(np.float64)
        self.w = w / np.maximum(w.sum(1, keepdims=True), 1)
        self.width = np.array([cols[u].max() - cols[u].min() if u.any() else 1 for u in used], float)
        self.height = np.array([rows[u].max() - rows[u].min() if u.any() else 1 for u in used], float)


class World:
    """Ground and forces for a soft-body trial. The ground is a height field on a regular grid; a step taller
    than half a voxel is a wall (it stops the creature instead of lifting it)."""

    def __init__(self, xs=None, hs=None, gravity=25.0, mu=0.9, water=False, floor_kill=-1e9, drag=0.15, cd=1.6,
                 act=0.36):
        self.cd, self.act = cd, act
        if xs is None:
            xs, hs = np.arange(-1000.0, 1000.5, 0.5), np.zeros(4001)
        self.xs = np.asarray(xs, np.float64)
        self.hs = np.asarray(hs, np.float64)
        self.x0, self.dx = float(self.xs[0]), float(self.xs[1] - self.xs[0])
        self.dh = np.diff(self.hs)
        self.slope = self.dh / self.dx
        self.nrm = 1.0 / np.sqrt(1.0 + self.slope ** 2)
        self.g, self.mu, self.water, self.floor_kill, self.drag = gravity, mu, water, floor_kill, drag

    def _k(self, x):
        k = ((x - self.x0) / self.dx).astype(np.int64)
        return np.clip(k, 0, len(self.dh) - 1)

    def height(self, x):
        x = np.asarray(x, np.float64)
        k = self._k(x)
        return self.hs[k] + (x - self.xs[k]) * self.slope[k]


class State:
    """Node positions and velocities as separate (n, 36) arrays (faster than (n, 36, 2))."""

    def __init__(self, n):
        self.x = np.zeros((n, NN))
        self.y = np.zeros((n, NN))
        self.vx = np.zeros((n, NN))
        self.vy = np.zeros((n, NN))


def beat_phase(beats: np.ndarray, t: np.ndarray, period: float) -> np.ndarray:
    """Beats elapsed at times t (fractional, locked to the detected beats, extrapolated at the ends)."""
    if len(beats) < 2:
        return t / period
    k = np.clip(np.searchsorted(beats, t, side="right") - 1, 0, len(beats) - 2)
    span = beats[k + 1] - beats[k]
    x = k + (t - beats[k]) / np.maximum(span, 1e-6)
    x = np.where(t < beats[0], (t - beats[0]) / period, x)
    return np.where(t > beats[-1], len(beats) - 1 + (t - beats[-1]) / period, x)


def simulate(B: Bodies, world: World, win: dict, x0, steps: int, record: bool, hooks=None, y0=None,
             forces=None, mirror=None, frame_cb=None, mass=None):
    """Run n creatures for `steps` frames. hooks(t, S, alive) may push nodes and end attempts (it returns a (n,)
    array of cause codes, 0 = carry on); forces(t, S, Fx, Fy) adds forces. Returns (positions per frame (or the
    last) as (steps + 1, n, 36, 2), time each attempt ended, its cause, still running)."""
    n = B.n
    S = State(n)
    x0 = np.broadcast_to(np.asarray(x0, np.float64), (n,))
    base = world.height(x0) if y0 is None else np.broadcast_to(np.asarray(y0, np.float64), (n,))
    rx = B.rest[None, :, 0] - 0.5 * B.width[:, None]
    if mirror is not None:
        rx = np.where(np.asarray(mirror)[:, None], -rx, rx)
    S.x[:] = x0[:, None] + rx
    S.y[:] = base[:, None] + 0.05 + B.rest[None, :, 1]
    used = B.used.astype(np.float64)
    alive = np.ones(n, bool)
    t_dead = np.full(n, np.inf)
    cause = np.zeros(n, np.int16)
    tsub = np.arange(steps * SUB + 1) * DT
    bp = beat_phase(win["beats"], tsub, win["period"])
    power = np.interp(tsub, np.arange(len(win["power"])) / SIM_HZ, win["power"])
    rec = np.zeros((steps + 1, n, NN, 2), np.float32) if record else None
    if record:
        rec[0, :, :, 0], rec[0, :, :, 1] = S.x, S.y
    flipped = np.zeros(n)
    w = B.w
    rcx = (rx * w).sum(1, keepdims=True)
    rcy = (B.rest[None, :, 1] * w).sum(1, keepdims=True)
    r0x, r0y = rx - rcx, B.rest[None, :, 1] - rcy
    gi, gj, gij = B.gi, B.gj, B.gij
    K, L0 = B.K, B.L0c
    ea, da, vox = B.edge_act, B.is_diag_act, B.vox
    amp_v = world.act * B.amp_v
    ph_v = B.phase_v
    skew = 0.45 * B.skew
    inv_cyc = 1.0 / B.cyc[:, None]
    c_damp = 5.0
    keep = 1.0 - world.drag * DT
    NT = n * NN
    for f in range(steps):
        for sub in range(SUB):
            q = f * SUB + sub
            t = tsub[q]
            th = 2 * np.pi * (bp[q] * inv_cyc + ph_v)
            av = (amp_v * (power[q] * (np.sin(th) + skew * np.sin(2 * th)))).ravel()[vox]
            L = np.where(da, np.sqrt((1 + av) ** 2 + 1.0), L0 * (1 + av * ea))
            xf, yf = S.x.ravel(), S.y.ravel()
            dx = xf[gj] - xf[gi]
            dy = yf[gj] - yf[gi]
            dist = np.sqrt(dx * dx + dy * dy) + 1e-9
            ux, uy = dx / dist, dy / dist
            vxf, vyf = S.vx.ravel(), S.vy.ravel()
            rel = (vxf[gj] - vxf[gi]) * ux + (vyf[gj] - vyf[gi]) * uy
            fm = K * (dist - L) + c_damp * rel
            fx, fy = fm * ux, fm * uy
            Fx = np.bincount(gij, np.concatenate([fx, -fx]), NT).reshape(n, NN)
            Fy = np.bincount(gij, np.concatenate([fy, -fy]), NT).reshape(n, NN)
            if world.water:
                _water(B, S, Fx, Fy, win["current"][min(q, len(win["current"]) - 1)] if "current" in win else 0.0,
                       ux, uy, gi, gj, NT, world.cd)
            if forces is not None:
                forces(t, S, Fx, Fy)
            if mass is not None:
                Fx /= mass[:, None]
                Fy /= mass[:, None]
            if not world.water:
                Fy -= world.g
            m = used * alive[:, None]
            S.vx = (S.vx + Fx * DT) * keep * m
            S.vy = (S.vy + Fy * DT) * keep * m
            px = S.x
            S.x = S.x + S.vx * DT
            S.y = S.y + S.vy * DT
            if not world.water:
                _ground(world, S, px)
            if hooks is not None:
                c = hooks(t + DT, S, alive)
                newly = alive & (c > 0)
                if newly.any():
                    t_dead[newly] = t + DT
                    cause[newly] = c[newly]
                    alive &= ~newly
        # a creature on its back for most of a second is out; so is one that falls off the world
        cx = (S.x * w).sum(1)
        cy = (S.y * w).sum(1)
        rx, ry = S.x - cx[:, None], S.y - cy[:, None]
        ang = np.arctan2(((r0x * ry - r0y * rx) * w).sum(1), ((r0x * rx + r0y * ry) * w).sum(1))
        flipped = np.where(np.abs(ang) > 2.2, flipped + 1, 0)
        tf = (f + 1) / SIM_HZ
        fl = alive & (flipped > 0.9 * SIM_HZ)
        fall = alive & (cy < world.floor_kill)
        for msk, code in ((fl, 1), (fall, 2)):
            if msk.any():
                t_dead[msk] = tf
                cause[msk] = code
                alive &= ~msk
        if record:
            rec[f + 1, :, :, 0], rec[f + 1, :, :, 1] = S.x, S.y
        if frame_cb is not None:
            frame_cb(f + 1, S)
    if not record:
        rec = np.stack([S.x, S.y], -1)[None]
    return rec, t_dead, cause, alive


def _ground(world: World, S: State, px):
    k = world._k(S.x)
    h = world.hs[k] + (S.x - world.xs[k]) * world.slope[k]
    pen = h - S.y
    hit = pen > 0
    if not hit.any():
        return
    idx = np.nonzero(hit.ravel())[0]
    x, y = S.x.ravel(), S.y.ravel()
    vx, vy = S.vx.ravel(), S.vy.ravel()
    kk = k.ravel()[idx]
    p = pen.ravel()[idx]
    wall = p > 0.55
    if wall.any():
        # a cliff face: back to where the node was, no sideways speed
        wi = idx[wall]
        x[wi] = px.ravel()[wi]
        vx[wi] = 0.0
        idx, kk, p = idx[~wall], kk[~wall], p[~wall]
    s = world.slope[kk]
    inv = world.nrm[kk]
    nx, ny = -s * inv, inv
    a, b = vx[idx], vy[idx]
    vn = a * nx + b * ny
    dvn = np.maximum(-vn, 0.0)
    vt = a * ny - b * nx
    lim = world.mu * (dvn + world.g * DT)
    vt2 = np.sign(vt) * np.maximum(np.abs(vt) - lim, 0.0)
    vn2 = vn + dvn
    vx[idx] = vn2 * nx + vt2 * ny
    vy[idx] = vn2 * ny - vt2 * nx
    y[idx] = y[idx] + p
    S.x, S.y = x.reshape(S.x.shape), y.reshape(S.y.shape)
    S.vx, S.vy = vx.reshape(S.vx.shape), vy.reshape(S.vy.shape)


def _water(B, S, Fx, Fy, current, ux, uy, gi, gj, NT, cd=1.6):
    """Drag on every spring across its own direction (thrust from undulation), against the current."""
    vxf, vyf = S.vx.ravel(), S.vy.ravel()
    mx = 0.5 * (vxf[gi] + vxf[gj]) - current
    my = 0.5 * (vyf[gi] + vyf[gj])
    nx, ny = -uy, ux
    vn = mx * nx + my * ny
    f = -cd * (np.abs(vn) + 0.3) * vn * B.surf
    gg = np.concatenate([gi, gj])
    n = Fx.shape
    Fx += np.bincount(gg, np.concatenate([f * nx, f * nx]), NT).reshape(n)
    Fy += np.bincount(gg, np.concatenate([f * ny, f * ny]), NT).reshape(n)


# ====================================================================================== drawing
def creature_quads(B: Bodies, X: np.ndarray, i: int, act_t: float, cyc_phase: float):
    """(quads (m, 4, 2), colours (m, 4)) for creature i at positions X (36, 2)."""
    vs = np.nonzero(B.mat[i] > 0)[0]
    if len(vs) == 0:
        return np.zeros((0, 4, 2)), np.zeros((0, 4))
    r, c = vs // GS, vs % GS
    bl = r * (GS + 1) + c
    q = np.stack([X[bl], X[bl + 1], X[bl + GS + 2], X[bl + GS + 1]], 1)
    cols = np.array([MAT_COL[int(m)] for m in B.mat[i, vs]], np.float32)
    mus = np.isin(B.mat[i, vs], (HACT, VACT))
    if mus.any():
        ph = B.ph[i, vs * 6]
        lift = 0.5 + 0.5 * np.sin(2 * np.pi * (cyc_phase / B.cyc[i] + ph))
        cols[mus] = cols[mus] * (0.75 + 0.45 * lift[mus, None])
    return q, np.concatenate([np.clip(cols, 0, 1), np.ones((len(vs), 1), np.float32)], 1)


def draw_creature(L, B: Bodies, X: np.ndarray, i: int, cyc_phase: float, alpha: float = 1.0, dead: bool = False,
                  shadow_y: float | None = None, look=(1.0, 0.0), tint=None):
    q, cols = creature_quads(B, X, i, 0.0, cyc_phase)
    if len(q) == 0:
        return
    if tint is not None:
        cols[:, :3] = cols[:, :3] * 0.35 + np.asarray(tint[:3], np.float32) * 0.65
    if dead:
        cols[:, :3] = cols[:, :3] * 0.45 + 0.25
    cols[:, 3] = alpha
    if shadow_y is not None and alpha > 0.5:
        cx = float(q[..., 0].mean())
        L.add("sdf", D.boxes([(cx, shadow_y + 0.05)], (0.6 * (q[..., 0].max() - q[..., 0].min()) + 0.3, 0.12),
                             (0, 0, 0, 0.22 * alpha), corner=0.12))
    L.add("poly", D.quads(q, cols))
    if alpha > 0.5:
        # outlines between voxels
        e0 = np.concatenate([q[:, 0], q[:, 1], q[:, 2], q[:, 3]])
        e1 = np.concatenate([q[:, 1], q[:, 2], q[:, 3], q[:, 0]])
        L.add("sdf", D.segs(e0, e1, 0.035, (0.05, 0.06, 0.09, 0.85 * alpha)))
        # eyes on the front of the top row
        vs = np.nonzero(B.mat[i] > 0)[0]
        top = vs[vs // GS == (vs // GS).max()]
        v = int(top.max())
        r, c = divmod(v, GS)
        bl = r * (GS + 1) + c
        P = np.stack([X[bl], X[bl + 1], X[bl + GS + 2], X[bl + GS + 1]])

        def at(a, b):
            return (P[0] * (1 - a) * (1 - b) + P[1] * a * (1 - b) + P[2] * a * b + P[3] * (1 - a) * b)
        eyes = np.array([at(0.38, 0.62), at(0.78, 0.62)])
        L.add("sdf", D.circles(eyes, 0.2, (1, 1, 1, alpha), outline=0.04, dark=0.8))
        if dead:
            for e in eyes:
                L.add("sdf", D.segs([e + (-0.12, -0.12), e + (-0.12, 0.12)], [e + (0.12, 0.12), e + (0.12, -0.12)],
                                    0.035, (0.05, 0.05, 0.08, alpha)))
        else:
            lk = np.asarray(look, float)
            lk = lk / (np.linalg.norm(lk) + 1e-9) * 0.08
            L.add("sdf", D.circles(eyes + lk, 0.095, (0.05, 0.05, 0.08, alpha)))


# ====================================================================================== trials
def soft_window(mu, t0, t1, extra=None) -> dict:
    T = t1 - t0
    loud = mu.curve("loud", t0, t1)
    w = {"T": T, "t0": t0, "beats": mu.events("beat", t0 - 4 * mu.beat, t1 + 4 * mu.beat), "period": mu.beat,
         "power": (0.62 + 0.38 * loud).astype(np.float64), "kicks": mu.events("kick", t0, t1),
         "hats": mu.events("hat", t0, t1), "drops": mu.events("drop", t0, t1)}
    if extra:
        w.update(extra)
    return w


CAUSES = ["OUT OF TIME", "FLIPPED", "FELL", "CRUSHED", "EGG BROKEN", "STUNG", "PUSHED OUT", "SWEPT AWAY"]
WIN = 99


def _empty(steps, record, extra) -> Outcome:
    o = Outcome(np.zeros(0), np.zeros(0, bool), np.zeros(0), np.zeros(0, np.int16))
    if record:
        o.states = {"X": np.zeros((steps + 1, 0, NN, 2), np.float32), **extra}
    return o


def _smooth_terrain(xs, prof, amp, flat_until=2.0, ramp=6.0):
    hs = (prof - prof.mean()) * amp
    hs = hs - np.interp(0.0, xs, hs)
    return hs * np.clip((xs - flat_until) / ramp, 0.0, 1.0)


class SoftTrial(Trial):
    style = "flat"
    dims = "2D"
    dim = DIM
    causes = CAUSES
    pop = 32
    ghosts = 7
    g_max = 70
    g_min = 12
    version = 1
    x_start = 0.0
    palette = {"top": (0.98, 0.62, 0.42), "bottom": (0.99, 0.86, 0.66), "horizon": 0.62, "sun": (0.72, 0.42, 0.06),
               "stars": 0.0, "far": ((0.96, 0.62, 0.52), (0.93, 0.55, 0.47)), "ground": ((0.55, 0.30, 0.22), (0.30, 0.15, 0.12)),
               "edge": (1.0, 0.88, 0.62), "mode": 0, "zoom": 9.0, "ghost": (0.75, 0.85, 1.0)}

    def window(self, env, mu, t0, t1):
        return soft_window(mu, t0, t1)

    def describe(self, env, g):
        mat = decode(g[None])[0][0]
        names = {RIGID: "bone", SOFT: "flesh", HACT: "side muscle", VACT: "lift muscle"}
        cnt = {names[m]: int((mat == m).sum()) for m in names if (mat == m).any()}
        return f"{int((mat > 0).sum())} voxels: " + ", ".join(f"{v} {k}" for k, v in cnt.items())

    # ---- physics
    def world(self, env):
        return World(env["xs"], env["hs"], gravity=25.0, mu=0.55, floor_kill=env.get("kill", -30.0))

    def goal_x(self, env):
        return env["goal"]

    def hazards(self, env, win) -> dict:
        return {}

    def extra(self, env, win, B, haz, n):
        """(hook(t, S, alive) -> codes, forces(t, S, Fx, Fy), frame callback, recorded dict)"""
        return None, None, None, {}

    def bodies(self, G):
        return Bodies(G)

    def masses(self, env, nb):
        return None

    def start(self, env, n):
        return self.x_start, None, None

    def rollout(self, env, win, G, record=False):
        steps = int(math.ceil(win["T"] * SIM_HZ))
        haz = self.hazards(env, win)
        if len(G) == 0:
            return _empty(steps, record, {"haz": haz})
        n = len(G)
        B = self.bodies(G)
        nb = B.n
        gx = self.goal_x(env)
        x0, y0, mirror = self.start(env, nb)
        x00 = float(np.asarray(x0).ravel()[0])
        best = np.full(nb, x00)
        hk, fc, fcb, extra = self.extra(env, win, B, haz, n)

        def hooks(t, S, alive):
            cx = (S.x * B.w).sum(1)
            np.maximum(best, cx, out=best)
            codes = np.where(alive & (cx >= gx), WIN, 0)
            if hk is not None:
                c2 = hk(t, S, alive)
                codes = np.where(codes == 0, c2, codes)
            return codes
        Xr, td, cause, alive = simulate(B, self.world(env), win, x0, steps, record, hooks, y0=y0, forces=fc,
                                        mirror=mirror, frame_cb=fcb, mass=self.masses(env, nb))
        cause, td, best_n = cause[:n], td[:n], best[:n]
        succ = cause == WIN
        t_end = np.where(np.isfinite(td), td, win["T"])
        prog = np.clip((best_n - x00) / max(gx - x00, 1e-6), 0.0, 0.999)
        fit = np.where(succ, 1.0 + 0.3 * (1.0 - t_end / win["T"]), self.shape_fitness(prog, cause, t_end, win))
        o = Outcome(fit, succ, t_end, np.where(succ, -1, cause).astype(np.int16),
                    np.stack([B.width[:n] / GS, B.height[:n] / GS], 1))
        if record:
            o.states = {"X": Xr, "bodies": B, "haz": haz, **extra}
        return o

    def shape_fitness(self, prog, cause, t_end, win):
        return prog

    # ---- drawing
    def cam_target(self, env, rec, f, ctx):
        X = rec.states["X"]
        T = len(X)
        B = rec.states.get("bodies")
        if B is not None and B.n:
            cxs = (X[:, 0, :, 0] * B.w[0][None]).sum(1)
            lo, hi = max(0, f - 40), min(T, f + 41)
            return float(np.mean(cxs[lo:hi])) + 3.5
        g = self.goal_x(env)
        x = ctx.get("reveal", f / max(T - 1, 1))
        return g * hud_ease(x) * 0.95 + 3.0

    def draw(self, sc, fr, env, win, rec, k, ctx):
        X = rec.states["X"]
        f = int(min(max(k, 0), len(X) - 1))
        pal = self.palette
        xs, hs = env["xs"], env["hs"]
        cam_x = self.cam_target(env, rec, f, ctx)
        cam_y = float(np.interp(cam_x, xs, hs)) + 0.5 * pal["zoom"]
        cam_y = max(cam_y, env.get("cam_floor", -1e9))
        sc.cam2d(fr, cam_x, cam_y, pal["zoom"])
        sc.backdrop(fr, top=pal["top"], bottom=pal["bottom"], horizon=pal["horizon"], sun=pal["sun"],
                    stars=pal["stars"], mode=pal["mode"], accent=self.accent)
        W = fr.world
        span = 2.4 * pal["zoom"]
        vis = (xs > cam_x - span) & (xs < cam_x + span)
        px = xs[vis]
        if pal.get("far"):
            far = np.interp((px - cam_x) * 0.5 + cam_x * 0.3, xs, hs) * 0.5 + cam_y - 0.35 * pal["zoom"]
            W.add("poly", D.strip(px, far, cam_y - 2 * pal["zoom"], (*pal["far"][0], 1), (*pal["far"][1], 1)))
        self.draw_back(sc, W, env, rec, f, ctx, cam_x, cam_y)
        W.add("poly", D.strip(px, hs[vis], np.minimum(hs[vis], cam_y - 2 * pal["zoom"]) - 1, (*pal["ground"][0], 1),
                              (*pal["ground"][1], 1)))
        W.add("sdf", D.polyline(np.stack([px, hs[vis]], 1), 0.08, (*pal["edge"], 1)))
        self.draw_props(sc, W, env, rec, f, ctx, cam_x)
        B = rec.states.get("bodies")
        if B is not None and B.n:
            self.draw_creatures(sc, W, env, rec, f, ctx)
        self.draw_front(sc, W, env, rec, f, ctx, cam_x)

    def draw_back(self, sc, W, env, rec, f, ctx, cam_x, cam_y):
        pass

    def draw_front(self, sc, W, env, rec, f, ctx, cam_x):
        pass

    def draw_props(self, sc, W, env, rec, f, ctx, cam_x):
        g = self.goal_x(env)
        gy = float(np.interp(g, env["xs"], env["hs"]))
        flag(W, g, gy, sc.t)

    def draw_creatures(self, sc, W, env, rec, f, ctx):
        draw_soft_batch(sc, W, rec.states["bodies"], rec.states["X"], f, rec, ctx, env["xs"], env["hs"],
                        ghost=self.palette["ghost"])


def hud_ease(x):
    x = min(max(x, 0.0), 1.0)
    return x * x * (3 - 2 * x)


def flag(W, x, y, t, col=(0.15, 0.85, 0.45)):
    W.add("sdf", D.segs([(x, y)], [(x, y + 5.0)], 0.08, (0.95, 0.95, 0.95, 1)))
    wave = 0.25 * math.sin(t * 6.0)
    W.add("poly", D.tris([[(x, y + 5.0), (x + 2.0, y + 4.4 + wave), (x, y + 3.8)]], (*col, 1)))


def draw_soft_batch(sc, W, B, X, f, rec, ctx, xs=None, hs=None, look=(1.0, 0.0), ghost=(0.75, 0.85, 1.0), n=None):
    """Ghosts first (outlined and faded), then the featured creature (index 0)."""
    t = f / SIM_HZ
    bp = ctx["beat_phase"]
    n = B.n if n is None else n
    for i in range(n - 1, 0, -1):
        dead = t >= rec.t_end[i] and not rec.success[i]
        q, cols = creature_quads(B, X[f, i], i, 0.0, bp)
        if len(q):
            W.add("poly", D.quads(q, (*ghost, 0.10 if dead else 0.18)))
            e0 = np.concatenate([q[:, 0], q[:, 1], q[:, 2], q[:, 3]])
            e1 = np.concatenate([q[:, 1], q[:, 2], q[:, 3], q[:, 0]])
            W.add("sdf", D.segs(e0, e1, 0.03, (*ghost, 0.18 if dead else 0.4)))
    dead = t >= rec.t_end[0] and not rec.success[0]
    sy = float(np.interp(float(X[f, 0, :, 0].mean()), xs, hs)) if xs is not None else None
    draw_creature(W, B, X[f, 0], 0, bp, 1.0, dead and ctx["show_dead"], shadow_y=sy, look=look)


# ====================================================================================== the trials
class Sprint(SoftTrial):
    key = "sprint"
    name = "WAVEFORM SPRINT"
    algo = "GENETIC ALGORITHM · BODY + GAIT"
    physics = "2D soft bodies · gravity · grip"
    goal = "Cross the set's waveform to the flag before the phrase ends"
    affinity = {"energy": 1.0, "kick": 0.8, "perc": 0.5}
    accent = (1.0, 0.55, 0.2)

    def level(self, feats):
        return 0.2 + 0.2 * min(1.0, feats["energy"])

    def env(self, mu, ch, rng, level):
        g = 6.0 + 26.0 * level
        xs = np.arange(-20.0, g + 40.0, 0.5)
        hs = _smooth_terrain(xs, mu.loud_profile(ch.t0, ch.t1, len(xs)), 0.4 + 3.0 * level)
        return {"xs": xs, "hs": hs, "goal": g, "level": level}

    def draw_props(self, sc, W, env, rec, f, ctx, cam_x):
        xs, hs = env["xs"], env["hs"]
        for m in np.arange(0, env["goal"] + 1, 5.0):
            if abs(m - cam_x) < 22:
                y = float(np.interp(m, xs, hs))
                W.add("sdf", D.segs([(m, y)], [(m, y + 0.8)], 0.05, (1, 0.92, 0.8, 0.8)))
        super().draw_props(sc, W, env, rec, f, ctx, cam_x)


class Canyon(SoftTrial):
    key = "canyon"
    name = "BASS CANYON"
    algo = "CMA-ES"
    physics = "2D soft bodies · a gap as wide as the bass is deep"
    goal = "Get across the canyon to the far flag"
    affinity = {"low": 1.0, "drops": 0.5, "dyn": 0.3}
    accent = (0.55, 0.45, 1.0)
    palette = {"top": (0.05, 0.05, 0.16), "bottom": (0.20, 0.12, 0.30), "horizon": 0.66, "sun": (0.25, 0.22, 0.035),
               "stars": 0.9, "far": ((0.16, 0.10, 0.24), (0.10, 0.06, 0.16)), "ground": ((0.34, 0.22, 0.36), (0.12, 0.07, 0.14)),
               "edge": (0.75, 0.6, 1.0), "mode": 0, "zoom": 8.0, "ghost": (0.7, 0.75, 1.0)}

    def level(self, feats):
        return 0.2 + 0.2 * min(1.0, feats["low"] * 1.4)

    def optimizer(self, env, rng):
        from ..evolve import CMAES
        return CMAES(self.dim, self.pop, rng, sep=True, sigma=0.3)

    def env(self, mu, ch, rng, level):
        gap0 = 7.0
        gw = 0.5 + 2.6 * level
        g = gap0 + gw + 6.0
        xs = np.arange(-20.0, g + 30.0, 0.5)
        prof = mu.loud_profile(ch.t0, ch.t1, len(xs))
        hs = (prof - prof.mean()) * 0.6
        hs -= np.interp(0.0, xs, hs)
        hs[(xs > gap0) & (xs < gap0 + gw)] = -40.0
        return {"xs": xs, "hs": hs, "goal": g, "gap": (gap0, gap0 + gw), "kill": -6.0, "level": level}

    def draw_back(self, sc, W, env, rec, f, ctx, cam_x, cam_y):
        a, b = env["gap"]
        W.add("poly", D.quads([[(a, -40), (b, -40), (b, 0), (a, 0)]], (0.03, 0.02, 0.06, 1)))
        # strata on the walls follow the bass
        for k in range(6):
            y = -1.2 - 1.6 * k
            W.add("sdf", D.segs([(a - 6, y), (b, y)], [(a, y - 0.3), (b + 6, y - 0.3)], 0.12,
                                (0.5, 0.35, 0.7, 0.25 + 0.1 * (k % 2))))


class Boulders(SoftTrial):
    key = "boulders"
    name = "BOULDER STORM"
    algo = "AGE-LAYERED GENETIC ALGORITHM (ALPS)"
    physics = "2D soft bodies · rocks land on the kicks and shatter"
    goal = "Reach the cave while rocks fall on the kicks"
    affinity = {"kick": 1.0, "low": 0.5, "energy": 0.5}
    accent = (1.0, 0.35, 0.15)
    palette = {"top": (0.35, 0.18, 0.16), "bottom": (0.78, 0.42, 0.25), "horizon": 0.64, "sun": (0.3, 0.3, 0.05),
               "stars": 0.0, "far": ((0.42, 0.22, 0.18), (0.30, 0.14, 0.12)), "ground": ((0.28, 0.20, 0.18), (0.12, 0.08, 0.08)),
               "edge": (1.0, 0.55, 0.3), "mode": 0, "zoom": 9.0, "ghost": (1.0, 0.85, 0.75)}

    def level(self, feats):
        return 0.2 + 0.2 * min(1.0, feats["kick"])

    def optimizer(self, env, rng):
        from ..evolve import ALPS
        return ALPS(self.dim, self.pop, rng)

    def env(self, mu, ch, rng, level):
        g = 5.0 + 14.0 * level
        xs = np.arange(-20.0, g + 30.0, 0.5)
        hs = _smooth_terrain(xs, mu.loud_profile(ch.t0, ch.t1, len(xs)), 1.5) + np.clip(xs, 0, None) * 0.06
        return {"xs": xs, "hs": hs, "goal": g, "level": level, "every": 4 if level < 0.5 else (2 if level < 0.8 else 1), "gap": 12.0 - 6.0 * level,
                "rmax": 0.7 + 0.6 * level, "seed": int(rng.integers(1 << 30))}

    def hazards(self, env, win):
        """A rolling barrage: rocks land on the kicks just ahead of and just behind a safe gap that moves toward
        the cave at the pace the trial needs; they shatter as they land."""
        kicks = win["kicks"][::env["every"]]
        r = np.random.default_rng([env["seed"], int(win["t0"] * 1000)])
        n = len(kicks)
        T = win["T"]
        v = (env["goal"] - 0.5) / (0.85 * T)
        gap = env["gap"]
        side = np.where(r.random(n) < 0.5, -1.0, 1.0)
        rad = r.uniform(0.45, env["rmax"], n)
        x = 0.5 + v * kicks + side * (0.5 * gap + rad + r.uniform(0.0, 0.8, n))
        y_land = np.interp(x, env["xs"], env["hs"]) + rad
        return {"t": kicks, "x": x, "r": rad, "y": y_land, "fall": 0.8, "v": v, "gap": gap}

    def rock_pos(self, haz, t):
        dt = haz["t"] - t
        g = 2 * 22.0 / haz["fall"] ** 2 * 0.5
        y = haz["y"] + np.where(dt > 0, 0.5 * (2 * 22.0 / haz["fall"] ** 2) * dt * dt, 0.0)
        vis = t > haz["t"] - haz["fall"]
        return y, vis, g

    def extra(self, env, win, B, haz, n):
        if len(haz["t"]) == 0:
            return None, None, None, {}
        acc = 2 * 22.0 / haz["fall"] ** 2

        def hook(t, S, alive):
            dt = haz["t"] - t
            act = (dt < haz["fall"]) & (dt > -0.05)
            if not act.any():
                return np.zeros(len(alive), int)
            rx, rr = haz["x"][act], haz["r"][act]
            ry = haz["y"][act] + np.where(dt[act] > 0, 0.5 * acc * dt[act] ** 2, 0.0)
            falling = dt[act] > 0
            ddx = S.x[:, :, None] - rx[None, None, :]
            ddy = S.y[:, :, None] - ry[None, None, :]
            d = np.sqrt(ddx * ddx + ddy * ddy) + 1e-9
            pen = rr[None, None, :] + 0.1 - d
            hit = pen > 0
            codes = np.zeros(len(alive), int)
            if not hit.any():
                return codes
            crush = (hit & falling[None, None, :] & (pen > 0.12)).any((1, 2))
            codes[crush & alive] = 3
            # resting rocks are obstacles: push nodes out
            p = np.where(hit, pen, 0.0)
            S.x = S.x + (p * ddx / d).sum(2)
            S.y = S.y + (p * ddy / d).sum(2)
            return codes
        return hook, None, None, {}

    def draw_props(self, sc, W, env, rec, f, ctx, cam_x):
        haz = rec.states["haz"]
        t = f / SIM_HZ
        g = env["goal"]
        gy = float(np.interp(g, env["xs"], env["hs"]))
        # the cave
        W.add("sdf", D.circles([(g + 1.2, gy)], 3.2, (0.08, 0.05, 0.05, 1)))
        W.add("sdf", D.rings([(g + 1.2, gy)], 3.2, 0.25, (0.45, 0.28, 0.22, 1)))
        if len(haz.get("t", [])):
            acc = 2 * 22.0 / haz["fall"] ** 2
            dt = haz["t"] - t
            # a warning ring on the ground a beat before each rock lands
            warn = (dt > 0) & (dt < 0.9)
            for x, r_, d in zip(haz["x"][warn], haz["r"][warn], dt[warn]):
                y = float(np.interp(x, env["xs"], env["hs"]))
                W.add("sdf", D.rings([(x, y + 0.05)], r_ * (0.6 + 0.6 * (1 - d / 0.9)), 0.06, (1, 0.3, 0.15, 0.8)))
            vis = (dt < haz["fall"]) & (dt > -0.06)
            ry = haz["y"] + np.where(dt > 0, 0.5 * acc * dt * dt, 0.0)
            # shards of the rocks that have landed
            sh = (dt <= 0) & (dt > -0.7)
            for x, y, r_, d in zip(haz["x"][sh], haz["y"][sh], haz["r"][sh], dt[sh]):
                a = np.linspace(0.3, 2.84, 6)
                age = -d
                px = x + np.cos(a) * (0.3 + 3.0 * age) * r_
                py = y - r_ + np.sin(a) * (2.5 * age - 6.0 * age * age) * r_ + 0.2
                W.add("sdf", D.circles(np.stack([px, py], 1), 0.16 * r_, (0.36, 0.30, 0.30, 1.0 - age / 0.7)))
            if vis.any():
                W.add("sdf", D.circles(np.stack([haz["x"][vis], ry[vis]], 1), haz["r"][vis], (0.36, 0.30, 0.30, 1),
                                       outline=0.08, dark=0.5))
                land = vis & (dt < 0) & (dt > -0.4)
                if land.any():
                    W.add("sdf", D.rings(np.stack([haz["x"][land], haz["y"][land] - haz["r"][land]], 1),
                                         haz["r"][land] * (1.2 - 2.0 * dt[land]), 0.05, (1, 0.8, 0.6, 0.6)))


class Stairway(SoftTrial):
    key = "stairway"
    name = "SPECTRUM STAIRS"
    algo = "CMA-ME · MAP-ELITES WITH CMA-ES EMITTERS"
    physics = "2D soft bodies · steps cut from the spectrum"
    goal = "Climb the staircase built from this stretch's spectrum"
    affinity = {"mid": 0.6, "bright": 0.4, "minor": -0.4}
    accent = (0.3, 0.85, 1.0)
    palette = {"top": (0.82, 0.90, 0.98), "bottom": (0.95, 0.96, 0.98), "horizon": 0.7, "sun": None,
               "stars": 0.0, "far": None, "ground": ((0.25, 0.42, 0.62), (0.12, 0.22, 0.36)),
               "edge": (0.85, 0.95, 1.0), "mode": 0, "zoom": 8.0, "ghost": (0.3, 0.45, 0.7)}
    g_max = 60

    def level(self, feats):
        return 0.2 + 0.2 * min(1.0, feats["mid"] * 1.5)

    def optimizer(self, env, rng):
        from ..evolve import CMAME
        return CMAME(self.dim, self.pop, rng)

    def env(self, mu, ch, rng, level):
        prof = mu.profile(ch.t0, ch.t1, 8)
        steps = 3 + int(round(4 * level))
        w = 3.2
        xs = np.arange(-20.0, 8.0 + steps * w + 25.0, 0.25)
        hs = np.zeros_like(xs)
        top = 0.0
        tops = []
        for k in range(steps):
            band = prof[k % 5, k % prof.shape[1]] - prof.mean()
            h = (0.15 + 0.6 * level) * (0.6 + 1.6 * min(abs(band) * 3, 1.0))
            top += min(h, 0.95)
            tops.append(top)
            hs[xs >= 6.0 + k * w] = top
        g = 6.0 + (steps - 1) * w + 1.0
        return {"xs": xs, "hs": hs, "goal": g, "tops": tops, "w": w, "level": level, "prof": prof}

    def hud_extra(self, sc, L, rr, snap, local):
        """The archive of elites: the best climber found so far for each body shape (CMA-ME, pyribs)."""
        from .. import hud
        if snap is None:
            return
        a = np.asarray(snap, float)
        x0, y0, cell = 1590, 330, 40
        n = a.shape[0]
        hud.panel(L, x0 - 70, y0 - 50, x0 + n * cell + 20, y0 + n * cell + 60)
        D.text(L, "ARCHIVE OF ELITES", x0 - 52, y0 - 42, 20, (1, 1, 1, 0.7), tracking=3, shadow=False)
        for i in range(n):
            for j in range(n):
                v = a[i, n - 1 - j]
                if np.isnan(v):
                    col = (1, 1, 1, 0.06)
                else:
                    q = min(max(v, 0.0), 1.2) / 1.2
                    col = (0.15 + 0.85 * q, 0.35 + 0.6 * q, 1.0 - 0.6 * q, 0.9)
                L.add("sdf", D.boxes([(x0 + i * cell + cell / 2, y0 + j * cell + cell / 2)], (cell / 2 - 2, cell / 2 - 2),
                                     col, space=D.SCREEN, corner=4))
        D.text(L, "WIDER →", x0 + n * cell / 2, y0 + n * cell + 8, 16, (1, 1, 1, 0.55), align=0.5, shadow=False)
        D.text(L, "TALLER ↑", x0 - 10, y0 + n * cell / 2 - 8, 16, (1, 1, 1, 0.55), align=1.0, shadow=False)

    def draw_props(self, sc, W, env, rec, f, ctx, cam_x):
        prof = env["prof"]
        for k, top in enumerate(env["tops"]):
            x = 6.0 + k * env["w"]
            col = [(0.3, 0.85, 1.0), (1.0, 0.75, 0.3), (0.9, 0.4, 0.8), (0.4, 1.0, 0.6), (1.0, 0.45, 0.4)][k % 5]
            W.add("sdf", D.boxes([(x + env["w"] / 2, top - 0.08)], (env["w"] / 2 - 0.05, 0.08), (*col, 0.9), corner=0.04))
        super().draw_props(sc, W, env, rec, f, ctx, cam_x)


class Courier(SoftTrial):
    key = "courier"
    name = "EGG COURIER"
    algo = "PARALLEL TEMPERING"
    physics = "2D soft bodies · a fragile egg on top · bumps on the onsets"
    goal = "Carry the egg to the nest without dropping it"
    affinity = {"calm": 0.5, "dyn": -0.4, "perc": -0.3, "vocal": 0.3}
    accent = (1.0, 0.85, 0.35)
    palette = {"top": (0.55, 0.70, 0.88), "bottom": (0.85, 0.88, 0.92), "horizon": 0.62, "sun": (0.3, 0.25, 0.05),
               "stars": 0.0, "far": ((0.50, 0.60, 0.75), (0.40, 0.50, 0.66)), "ground": ((0.36, 0.48, 0.40), (0.18, 0.26, 0.22)),
               "edge": (0.8, 0.95, 0.75), "mode": 0, "zoom": 8.0, "ghost": (0.25, 0.35, 0.5)}

    def level(self, feats):
        return 0.2 + 0.2 * min(1.0, feats["perc"] * 2)

    def optimizer(self, env, rng):
        from ..evolve import Tempering
        return Tempering(self.dim, self.pop, rng)

    def env(self, mu, ch, rng, level):
        g = 5.0 + 14.0 * level
        xs = np.arange(-20.0, g + 30.0, 0.25)
        hs = np.zeros_like(xs)
        on = mu.events("snare", ch.t0, ch.t1)
        if len(on):
            bx = 3.0 + (on / max(ch.t1 - ch.t0, 1)) * (g + 10)
            for x in bx[:: max(1, len(bx) // 12)]:
                hs += (0.1 + 0.35 * level) * np.exp(-((xs - x) / 0.6) ** 2)
        return {"xs": xs, "hs": hs, "goal": g, "level": level}

    def extra(self, env, win, B, haz, n):
        nb = B.n
        rows = np.arange(NN) // (GS + 1)
        top = np.where(B.used, rows[None, :], -1).max(1)
        cx0 = self.x_start
        egg = {"x": np.full(nb, cx0), "y": top + 0.05 + 0.55 + np.interp(cx0, env["xs"], env["hs"]),
               "vx": np.zeros(nb), "vy": np.zeros(nb)}
        hist = []
        R = 0.45
        world = self.world(env)

        def hook(t, S, alive):
            e = egg
            e["vy"] = np.where(alive, e["vy"] - 25.0 * DT, 0.0)
            e["vx"] = np.where(alive, e["vx"], 0.0)
            e["x"] = e["x"] + e["vx"] * DT
            e["y"] = e["y"] + e["vy"] * DT
            ddx = e["x"][:, None] - S.x
            ddy = e["y"][:, None] - S.y
            d = np.sqrt(ddx * ddx + ddy * ddy) + 1e-9
            pen = np.where(B.used, R + 0.12 - d, 0.0)
            hit = pen > 0
            if hit.any():
                p = np.where(hit, pen, 0.0)
                nx = (p * ddx / d).sum(1)
                ny = (p * ddy / d).sum(1)
                e["x"] = e["x"] + nx * 0.8
                e["y"] = e["y"] + ny * 0.8
                ln = np.sqrt(nx * nx + ny * ny) + 1e-9
                ux, uy = nx / ln, ny / ln
                # the egg takes the speed of what it rests on (with a little slip)
                vxs = (np.where(hit, S.vx, 0.0)).sum(1) / np.maximum(hit.sum(1), 1)
                vys = (np.where(hit, S.vy, 0.0)).sum(1) / np.maximum(hit.sum(1), 1)
                h = hit.any(1)
                rvx, rvy = e["vx"] - vxs, e["vy"] - vys
                vn = rvx * ux + rvy * uy
                rvx = np.where(h & (vn < 0), rvx - vn * ux, rvx) * np.where(h, 0.9, 1.0)
                rvy = np.where(h & (vn < 0), rvy - vn * uy, rvy) * np.where(h, 0.9, 1.0)
                e["vx"] = np.where(h, rvx + vxs, e["vx"])
                e["vy"] = np.where(h, rvy + vys, e["vy"])
            ground = world.height(e["x"])
            broke = alive & (e["y"] - R < ground + 0.02)
            return np.where(broke, 4, 0)

        def fcb(f, S):
            hist.append(np.stack([egg["x"], egg["y"]], 1).copy())
        return hook, None, fcb, {"egg": hist, "egg0": np.stack([egg["x"], egg["y"]], 1).copy()}

    def draw_props(self, sc, W, env, rec, f, ctx, cam_x):
        g = env["goal"]
        gy = float(np.interp(g, env["xs"], env["hs"]))
        W.add("sdf", D.boxes([(g + 1.0, gy + 0.6)], (1.6, 0.6), (0.55, 0.38, 0.22, 1), corner=0.5))
        W.add("sdf", D.boxes([(g + 1.0, gy + 1.15)], (1.3, 0.12), (0.35, 0.22, 0.12, 1), corner=0.1))
        flag(W, g + 2.6, gy, sc.t, (1.0, 0.85, 0.35))

    def draw_creatures(self, sc, W, env, rec, f, ctx):
        super().draw_creatures(sc, W, env, rec, f, ctx)
        eg = rec.states.get("egg")
        if not eg:
            return
        E = eg[min(max(f - 1, 0), len(eg) - 1)] if f > 0 else rec.states["egg0"]
        t = f / SIM_HZ
        for i in range(len(E) - 1, -1, -1):
            broke = t >= rec.t_end[i] and rec.cause[i] == 4
            a = 1.0 if i == 0 else 0.25
            if broke:
                y = float(np.interp(E[i, 0], env["xs"], env["hs"]))
                W.add("sdf", D.boxes([(E[i, 0], y + 0.08)], (0.6, 0.08), (1.0, 0.85, 0.2, a), corner=0.08))
                W.add("sdf", D.circles([(E[i, 0] - 0.4, y + 0.25), (E[i, 0] + 0.45, y + 0.2)], 0.18, (1, 0.97, 0.9, a)))
            else:
                W.add("sdf", D.boxes([E[i]], (0.36, 0.45), (1.0, 0.97, 0.9, a), corner=0.34, outline=0.04, dark=0.3))


class Swim(SoftTrial):
    key = "swim"
    name = "DEEP CURRENT"
    algo = "(μ, λ) EVOLUTION STRATEGY"
    physics = "2D soft bodies in water · drag · a current that follows the bass"
    goal = "Swim upstream to the lantern, past the jellyfish"
    affinity = {"calm": 0.6, "low": 0.4, "bright": -0.3}
    accent = (0.2, 0.9, 1.0)
    palette = {"top": (0.10, 0.45, 0.62), "bottom": (0.02, 0.10, 0.20), "horizon": 1.0, "sun": None,
               "stars": 0.0, "far": None, "ground": ((0.10, 0.20, 0.25), (0.05, 0.10, 0.14)),
               "edge": (0.4, 0.8, 0.9), "mode": 1, "zoom": 8.0, "ghost": (0.6, 0.9, 1.0)}

    def level(self, feats):
        return 0.2 + 0.2 * min(1.0, feats["low"] * 1.4)

    def optimizer(self, env, rng):
        from ..evolve import MuLambdaES
        return MuLambdaES(self.dim, self.pop, rng)

    def world(self, env):
        return World(env["xs"], env["hs"], gravity=0.0, mu=0.5, water=True, drag=0.05, cd=4.0, act=0.6)

    def env(self, mu, ch, rng, level):
        g = 3.0 + 8.0 * level
        xs = np.arange(-20.0, g + 30.0, 0.5)
        hs = np.full_like(xs, -9.0)
        return {"xs": xs, "hs": hs, "goal": g, "level": level, "cur": 0.05 + 0.4 * level,
                "jelly": int(round(3.5 * level)), "seed": int(rng.integers(1 << 30)), "cam_floor": -1.0}

    def window(self, env, mu, t0, t1):
        w = soft_window(mu, t0, t1)
        bass = mu.curve("bass", t0, t1, SIM_HZ * SUB)
        w["current"] = -env["cur"] * (0.35 + 0.65 * bass.astype(np.float64))
        return w

    def start(self, env, n):
        return 0.0, np.full(n, -2.5), None

    def hazards(self, env, win):
        r = np.random.default_rng([env["seed"], 7])
        J = env["jelly"]
        x = np.linspace(5.0, max(env["goal"] - 0.5, 5.5), J) + r.uniform(-0.5, 0.5, J)
        return {"x": x, "y0": r.uniform(-3.0, -1.0, J), "amp": r.uniform(1.0, 2.0, J), "ph": r.uniform(0, 6.28, J),
                "r": np.full(J, 0.55)}

    def jelly_at(self, haz, t, period):
        y = haz["y0"] + haz["amp"] * np.sin(2 * np.pi * t / (8 * period) + haz["ph"])
        return haz["x"], y

    def extra(self, env, win, B, haz, n):
        period = win["period"]

        def hook(t, S, alive):
            jx, jy = self.jelly_at(haz, t, period)
            ddx = S.x[:, :, None] - jx[None, None, :]
            ddy = S.y[:, :, None] - jy[None, None, :]
            hit = ((ddx * ddx + ddy * ddy) < (haz["r"][None, None, :] + 0.15) ** 2) & B.used[:, :, None]
            cy = (S.y * B.w).sum(1)
            cx = (S.x * B.w).sum(1)
            codes = np.where(hit.any((1, 2)), 5, 0)
            codes = np.where((cx < -6.0) | (np.abs(cy) > 9.0), 7, codes)
            return codes
        return hook, None, None, {}

    def draw_props(self, sc, W, env, rec, f, ctx, cam_x):
        t = f / SIM_HZ
        g = env["goal"]
        W.add("sdf", D.circles([(g, 0.0)], 0.5, (1.0, 0.85, 0.4, 1), glow=1.2))
        W.add("sdf", D.segs([(g, 0.5)], [(g, 3.0)], 0.05, (0.7, 0.8, 0.85, 0.8)))
        haz = rec.states["haz"]
        if len(haz.get("x", [])):
            jx, jy = self.jelly_at(haz, t, sc.mu.beat)
            pulse = 0.9 + 0.1 * math.sin(ctx["beat_phase"] * math.tau)
            W.add("sdf", D.circles(np.stack([jx, jy], 1), haz["r"] * pulse, (0.95, 0.45, 0.85, 0.75), glow=0.6))
            for x, y in zip(jx, jy):
                tl = np.linspace(0, 1.6, 6)
                for o in (-0.35, 0.0, 0.35):
                    pts = np.stack([x + o + 0.15 * np.sin(tl * 4 + t * 3 + o), y - 0.4 - tl], 1)
                    W.add("sdf", D.polyline(pts, 0.04, (0.95, 0.5, 0.9, 0.6)))
        # the current, drawn as streaks drifting with it
        cur = 0.5
        xs = np.arange(math.floor(cam_x - 20), cam_x + 20, 2.3)
        for j, x in enumerate(xs):
            y = -7 + (j * 2.71) % 14
            off = (t * 3.0 * cur + j * 0.37) % 2.3
            W.add("sdf", D.segs([(x - off, y)], [(x - off + 0.9, y)], 0.03, (0.7, 0.9, 1.0, 0.25)))

    def draw(self, sc, fr, env, win, rec, k, ctx):
        super().draw(sc, fr, env, win, rec, k, ctx)


class Sumo(SoftTrial):
    key = "sumo"
    name = "SUMO RING"
    algo = "SELF-PLAY · HALL OF FAME"
    physics = "2D soft bodies · two creatures · the champion grows heavier the harder the world"
    goal = "Push the reigning champion off the ring (the winner becomes the next champion)"
    affinity = {"energy": 0.7, "kick": 0.7, "low": 0.3}
    accent = (1.0, 0.3, 0.45)
    dim = DIM * 2 + 1
    ghosts = 0
    causes = CAUSES
    palette = {"top": (0.08, 0.04, 0.10), "bottom": (0.22, 0.10, 0.18), "horizon": 0.6, "sun": None,
               "stars": 0.5, "far": None, "ground": ((0.85, 0.75, 0.55), (0.35, 0.25, 0.18)),
               "edge": (1.0, 0.4, 0.55), "mode": 0, "zoom": 7.5, "ghost": (1, 1, 1)}

    def level(self, feats):
        return 0.25

    def optimizer(self, env, rng):
        return SelfPlay(DIM, self.pop, rng)

    def carry_over(self, old, new):
        """A reset starts a fresh population, but the reigning champion stays the champion."""
        new.hof = list(old.hof)

    def env(self, mu, ch, rng, level):
        half = 5.0
        xs = np.arange(-30.0, 30.0, 0.25)
        hs = np.where(np.abs(xs) <= half, 0.0, -40.0)
        return {"xs": xs, "hs": hs, "goal": 1e9, "half": half, "kill": -1e9, "level": level, "cam_floor": 3.0}

    def bodies(self, G):
        self._class = G[:, -1].copy()
        return Bodies(np.concatenate([G[:, :DIM], G[:, DIM:2 * DIM]]))

    def masses(self, env, nb):
        """The champion is heavier the harder the world (its nodes weigh 1 + 4 x level), and half as heavy again
        for every title it has won (its weight class is the genome's last gene)."""
        n = nb // 2
        return np.concatenate([np.ones(n), (1.0 + 4.0 * env["level"]) * (1.0 + self._class)])

    def start(self, env, nb):
        n = nb // 2
        x0 = np.concatenate([np.full(n, -2.2), np.full(n, 2.2)])
        mirror = np.concatenate([np.zeros(n, bool), np.ones(n, bool)])
        return x0, np.zeros(nb), mirror

    def extra(self, env, win, B, haz, n):
        def forces(t, S, Fx, Fy):
            a, b = slice(0, n), slice(n, 2 * n)
            ddx = S.x[a][:, :, None] - S.x[b][:, None, :]
            ddy = S.y[a][:, :, None] - S.y[b][:, None, :]
            d2 = ddx * ddx + ddy * ddy
            m = (d2 < 0.36) & B.used[a][:, :, None] & B.used[b][:, None, :]
            if not m.any():
                return
            d = np.sqrt(d2) + 1e-6
            f = np.where(m, 900.0 * (0.6 - d), 0.0)
            fx, fy = f * ddx / d, f * ddy / d
            Fx[a] += fx.sum(2)
            Fy[a] += fy.sum(2)
            Fx[b] -= fx.sum(1)
            Fy[b] -= fy.sum(1)

        def hook(t, S, alive):
            cy = (S.y * B.w).sum(1)
            codes = np.zeros(2 * n, int)
            own_out = cy[:n] < -1.5
            opp_out = cy[n:] < -1.5
            codes[:n] = np.where(own_out, 6, np.where(opp_out, WIN, 0))
            codes[n:] = np.where(opp_out | own_out, 6, 0)
            return codes
        return hook, forces, None, {}

    def rollout(self, env, win, G, record=False):
        o = super().rollout(env, win, G, record)
        if len(G) and not record:
            pass
        return o

    def shape_fitness(self, prog, cause, t_end, win):
        return np.where(cause == 6, 0.2 * t_end / win["T"], 0.5)

    def cam_target(self, env, rec, f, ctx):
        return 0.0

    def draw_props(self, sc, W, env, rec, f, ctx, cam_x):
        h = env["half"]
        W.add("sdf", D.boxes([(0.0, -0.6)], (h, 0.6), (0.9, 0.8, 0.6, 1), corner=0.1))
        W.add("sdf", D.segs([(-h, 0.0)], [(h, 0.0)], 0.06, (1.0, 0.4, 0.55, 1), glow=0.4))
        W.add("sdf", D.rings([(0.0, -0.6)], 1.4, 0.05, (0.6, 0.2, 0.25, 0.8)))

    def draw_creatures(self, sc, W, env, rec, f, ctx):
        B, X = rec.states["bodies"], rec.states["X"]
        n = B.n // 2
        t = f / SIM_HZ
        bp = ctx["beat_phase"]
        own_dead = t >= rec.t_end[0] and not rec.success[0]
        draw_creature(W, B, X[f, n], n, bp, 1.0, rec.success[0] and t >= rec.t_end[0], shadow_y=0.0, look=(-1, 0),
                      tint=(1.0, 0.35, 0.4))
        draw_creature(W, B, X[f, 0], 0, bp, 1.0, own_dead, shadow_y=0.0, look=(1, 0))


class SelfPlay:
    """Coevolution by self-play (as in Sims 1994 and Bansal et al. 2018): the population's genomes carry their
    opponent, the reigning champion. Whoever beats the champion becomes the next champion, so every success
    raises the bar for the next run."""

    def __init__(self, dim, pop, rng):
        from ..evolve import GA
        self.ga = GA(dim, pop, rng)
        # the first champion: a broad block of bone, three high, with muscles along its base
        first = np.zeros(dim)
        for v in range(15):
            first[v] = 0.25
        first[[0, 2, 4]] = 0.6
        first[NV:2 * NV] = rng.random(NV)
        first[2 * NV:3 * NV] = 0.8
        self.hof = [first]

    def ask(self):
        P = self.ga.ask()
        cls = np.full((len(P), 1), 0.5 * (len(self.hof) - 1))
        return np.concatenate([P, np.repeat(self.hof[-1][None], len(P), 0), cls], 1)

    def tell(self, G, out):
        d = (G.shape[1] - 1) // 2
        self.ga.tell(G[:, :d], out)
        if out.success.any():
            i = int(np.argmax(np.where(out.success, out.fitness, -1e9)))
            self.hof.append(G[i, :d].copy())
