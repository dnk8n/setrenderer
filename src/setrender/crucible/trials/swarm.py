"""Swarms in 3D: a particle swarm searching a landscape made of the chapter's spectrum for its highest peak
(Kennedy and Eberhart's particle swarm optimisation, with the swarm's own coefficients bred by a genetic
algorithm, so the creature here is the swarm), and a murmuration of birds crossing a valley while hawks dive
on the snares (Reynolds' boids, with the flocking rules' weights evolved by an evolution strategy)."""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from .. import meshes as M
from .base import SIM_HZ, Outcome, Trial
from .three import IDENT, Ground3, terrain_mesh


def _empty(steps, record, extra) -> Outcome:
    o = Outcome(np.zeros(0), np.zeros(0, bool), np.zeros(0), np.zeros(0, np.int16))
    if record:
        o.states = extra
    return o


# ====================================================================================== particle swarm
class SwarmSearch(Trial):
    key = "swarm"
    name = "SPECTRAL SWARM"
    algo = "PARTICLE SWARM · TUNED BY A GA"
    unit = "GENERATION"
    style = "lab"
    dims = "3D"
    physics = "a landscape made of this stretch's spectrum · one swarm per attempt"
    goal = "Find the highest peak and gather on it in time (less time, the harder the world)"
    affinity = {"bright": 0.7, "hats": 0.5, "perc": 0.2}
    accent = (0.4, 1.0, 0.8)
    causes = ["OUT OF TIME", "STUCK ON A FOOTHILL", "SCATTERED"]
    dim = 6
    pop = 24
    ghosts = 0
    g_max = 60
    version = 1
    NMAX = 40
    GRID = 96
    SIZE = 20.0

    def level(self, feats):
        return 0.25 + 0.2 * min(1.0, feats["bright"] * 2)

    def env(self, mu, ch, rng, level):
        G = self.GRID
        prof = mu.profile(ch.t0, ch.t1, 16)
        P = ndimage.zoom(prof, (G / prof.shape[0], G / prof.shape[1]), order=1)[:G, :G]
        P = ndimage.gaussian_filter(P, 4.0)
        P = (P - P.min()) / max(P.max() - P.min(), 1e-6)
        yy, xx = np.mgrid[0:G, 0:G] / (G - 1)
        r = np.random.default_rng([int(rng.integers(1 << 30)), 5])
        F = 0.35 * P
        # the swarm is released from the hive in one corner; foothills sit between it and the true summit,
        # which is far away, narrow, and narrower the harder the trial
        gx, gy = r.uniform(0.2, 0.8, 2)
        # the hive is a fair way from the summit (more than half the land's width)
        ang = r.uniform(0, 2 * np.pi)
        dist = 0.55
        u = np.array([np.cos(ang), np.sin(ang)])
        hive = np.clip(np.array([gx, gy]) + dist * u, 0.06, 0.94)
        if np.hypot(*(hive - np.array([gx, gy]))) < 0.8 * dist:
            hive = np.clip(np.array([gx, gy]) - dist * u, 0.06, 0.94)
        hills = r.uniform([0.1, 0.1, 0.06, 0.7], [0.9, 0.9, 0.14, 0.92], (10, 4))
        for cx, cy, s, a in hills[:7]:
            F += a * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * s * s))
        s = 0.06 - 0.025 * level
        F += 1.0 * np.exp(-((xx - gx) ** 2 + (yy - gy) ** 2) / (2 * s * s))
        # a broad, low rise around the summit (the clue a good swarm can follow past the foothills)
        F += 0.12 * np.exp(-((xx - gx) ** 2 + (yy - gy) ** 2) / (2 * 0.3 ** 2))
        F = (F - F.min()) / (F.max() - F.min())
        k = np.unravel_index(int(np.argmax(F)), F.shape)
        return {"F": F, "peak": (k[1] / (G - 1), k[0] / (G - 1)), "level": level, "seed": int(r.integers(1 << 30)),
                "eps": 0.01, "rad": 0.08, "hive": hive}

    def window(self, env, mu, t0, t1):
        step = mu.beat / 4.0
        n_it = max(4, int((t1 - t0) / step))
        return {"T": t1 - t0, "t0": t0, "step": step, "iters": n_it}

    def f_at(self, F, p):
        G = F.shape[0]
        q = np.clip(p, 0, 1) * (G - 1.001)
        i, j = q[..., 1].astype(int), q[..., 0].astype(int)
        u, v = q[..., 0] - j, q[..., 1] - i
        return F[i, j] * (1 - u) * (1 - v) + F[i, j + 1] * u * (1 - v) + F[i + 1, j] * (1 - u) * v + F[i + 1, j + 1] * u * v

    def decode(self, G):
        w = 0.2 + 0.85 * G[:, 0]
        c1, c2 = 2.5 * G[:, 1], 2.5 * G[:, 2]
        vmax = 0.01 + 0.24 * G[:, 3]
        ring = G[:, 4] > 0.5
        N = (8 + np.round(24 * G[:, 5])).astype(int)
        return w, c1, c2, vmax, ring, N

    def rollout(self, env, win, G, record=False):
        it = win["iters"]
        F = env["F"]
        if len(G) == 0:
            return _empty(0, record, {"P": np.zeros((it + 1, 0, self.NMAX, 2), np.float32), "iters": it,
                                      "step": win["step"]})
        n = len(G)
        w, c1, c2, vmax, ring, N = self.decode(G)
        r = np.random.default_rng([env["seed"], int(round(win["t0"] * 1000))])
        # scattered over the land, but nobody starts within sight of the summit (further away, the harder)
        X0 = r.random((self.NMAX * 8, 2))
        far = np.hypot(*(X0 - np.array(env["peak"])).T) > 0.35 + 0.2 * env["level"]
        X0 = X0[far][:self.NMAX]
        ang = r.uniform(0, 2 * np.pi, self.NMAX)
        V0 = np.stack([np.cos(ang), np.sin(ang)], 1) * r.uniform(0.0, 0.05, (self.NMAX, 1))
        R1 = r.random((it, self.NMAX, 2))
        R2 = r.random((it, self.NMAX, 2))
        X = np.repeat(X0[None], n, 0)
        V = np.repeat(V0[None], n, 0)
        act = np.arange(self.NMAX)[None, :] < N[:, None]
        fx = np.where(act, self.f_at(F, X), -1.0)
        pb, pbv = X.copy(), fx.copy()
        rec = np.zeros((it + 1, n, self.NMAX, 2), np.float32) if record else None
        best_rec = np.zeros((it + 1, n, 2), np.float32) if record else None
        if record:
            rec[0] = X
        peak = np.array(env["peak"])
        t_end = np.full(n, win["T"])
        cause = np.zeros(n, np.int16)
        done = np.zeros(n, bool)
        succ = np.zeros(n, bool)
        idx = np.arange(self.NMAX)
        for k in range(it):
            gi = np.argmax(pbv, 1)
            gb = pb[np.arange(n), gi]
            if ring.any():
                left = (idx[None, :] - 1) % N[:, None]
                right = (idx[None, :] + 1) % N[:, None]
                cand = np.stack([left, np.broadcast_to(idx, left.shape), right], -1)
                cv = np.take_along_axis(pbv[:, None, :].repeat(self.NMAX, 1), cand, 2)
                bi = np.take_along_axis(cand, np.argmax(cv, -1)[..., None], 2)[..., 0]
                lb = np.take_along_axis(pb, bi[..., None].repeat(2, -1), 1)
                soc = np.where(ring[:, None, None], lb, gb[:, None, :])
            else:
                soc = np.repeat(gb[:, None, :], self.NMAX, 1)
            V = (w[:, None, None] * V + c1[:, None, None] * R1[k][None] * (pb - X)
                 + c2[:, None, None] * R2[k][None] * (soc - X))
            sp = np.sqrt((V * V).sum(-1, keepdims=True)) + 1e-12
            V = np.where(sp > vmax[:, None, None], V / sp * vmax[:, None, None], V)
            V = np.where(done[:, None, None] | ~act[..., None], 0.0, V)
            X = np.clip(X + V, 0.0, 1.0)
            fx = np.where(act, self.f_at(F, X), -1.0)
            better = fx > pbv
            pb = np.where(better[..., None], X, pb)
            pbv = np.where(better, fx, pbv)
            dpk = np.sqrt(((X - peak) ** 2).sum(-1))
            near = ((dpk < env["rad"]) & act).sum(1) / N
            gbv = pbv.max(1)
            # the harder the world, the sooner the swarm must have gathered on the summit
            ok = ~done & (gbv >= 1.0 - env["eps"]) & (near >= 0.5) & (k < it * (1.0 - 0.6 * env["level"]))
            t_now = (k + 1) * win["step"]
            succ |= ok
            t_end = np.where(ok, t_now, t_end)
            done |= ok
            if record:
                rec[k + 1] = X
                best_rec[k + 1] = pb[np.arange(n), np.argmax(pbv, 1)]
        gbv = pbv.max(1)
        gb = pb[np.arange(n), np.argmax(pbv, 1)]
        spread = np.median(np.where(act, np.sqrt(((X - gb[:, None]) ** 2).sum(-1)), np.nan), 1)
        on_peak = np.sqrt(((gb - peak) ** 2).sum(-1)) < env["rad"]
        cause = np.where(succ, -1, np.where((spread < 0.08) & ~on_peak, 1, np.where(spread > 0.2, 2, 0))).astype(np.int16)
        near_end = ((np.sqrt(((X - peak) ** 2).sum(-1)) < env["rad"]) & act).sum(1) / N
        fit = np.where(succ, 1.0 + 0.3 * (1 - t_end / win["T"]), np.clip(0.6 * gbv + 0.39 * near_end, 0, 0.999))
        o = Outcome(fit, succ, t_end, cause)
        if record:
            o.states = {"P": rec, "best": best_rec, "N": N, "iters": it, "step": win["step"]}
        return o

    def describe(self, env, g):
        w, c1, c2, vmax, ring, N = self.decode(g[None])
        return (f"{int(N[0])} particles · inertia {w[0]:.2f} · pull to own best {c1[0]:.2f} · to the "
                f"{'neighbours' if ring[0] else 'swarm'}' best {c2[0]:.2f}")

    def world_xyz(self, env, p, lift=0.25):
        S, H = self.SIZE, 4.0
        h = self.f_at(env["F"], p) * H
        return np.stack([(p[..., 0] - 0.5) * S, h + lift, (p[..., 1] - 0.5) * S], -1)

    def draw(self, sc, fr, env, win, rec, k, ctx):
        S, Hs = self.SIZE, 4.0
        key = f"terrain-swarm-{id(env)}"
        if key not in sc.engine.meshes:
            F = env["F"]
            G = F.shape[0]
            gr = Ground3(F * Hs, -S / 2, -S / 2, S / (G - 1))

            def col(X, H, Z, nrm):
                h = H / Hs
                return np.stack([0.01 + 0.10 * h ** 2, 0.03 + 0.30 * h ** 2, 0.08 + 0.25 * h ** 2], -1)
            v, i = terrain_mesh(gr, col)
            sc.engine.add_mesh(key, v, i)
        fr.meshes.append((key, IDENT, False))
        ang = 0.55 + 0.25 * sc.t / 60.0 + 0.6 * ctx.get("reveal", 0.0)
        tgt = np.array([0.0, 1.2, 0.0])
        st = rec.states
        if st["P"].shape[1]:
            # frame the swarm: the camera's target follows its centre (averaged over a few seconds)
            it = st["iters"]
            x = min(k / SIM_HZ / st["step"], it)
            lo, hi = int(max(0, x - 20)), int(min(it, x + 20)) + 1
            N = int(st["N"][0])
            c = st["P"][lo:hi, 0, :N].astype(float).mean((0, 1))
            tgt = 0.4 * tgt + 0.6 * self.world_xyz(env, c[None], 0.0)[0]
        eye = tgt + (14 * math.cos(ang), 10.0, 14 * math.sin(ang))
        sc.backdrop(fr, (0.002, 0.004, 0.012), (0.01, 0.02, 0.035), horizon=0.45, stars=0.7)
        sc.cam3d(fr, eye, tgt, fov=0.8, sun=(0.3, 0.9, 0.2), sky=(0.05, 0.1, 0.16), ground=(0.02, 0.04, 0.05),
                 fog=0.008, sun_i=1.8, ambient=0.35, shadow_r=15.0)
        sc.tone(False)
        P = st["P"]
        if P.shape[1] == 0:
            return
        tt = k / SIM_HZ
        it = st["iters"]
        x = min(tt / st["step"], it)
        a = int(min(math.floor(x), it - 1))
        u = x - a
        N = int(st["N"][0])
        pos = (P[a, 0, :N] * (1 - u) + P[a + 1, 0, :N] * u)
        w = self.world_xyz(env, pos, 0.35)
        glow = 1.6 + 1.5 * ctx["kick"]
        fr.meshes.append(("sphere", M.inst(M.trs(w, 0.42), (0.45, 1.0, 0.85, 1), (glow, 0, 0, 0)), False))
        # trails: where each particle was over the last few iterations
        tr = []
        for d in range(1, 6):
            b = max(a - d, 0)
            tr.append(self.world_xyz(env, P[b, 0, :N].astype(float), 0.35))
        tr = np.concatenate(tr)
        fr.meshes.append(("sphere", M.inst(M.trs(tr, 0.12), (0.3, 0.9, 0.8, 0.35), (0.8, 0, 0, 0)), True))
        b = st["best"][min(a + 1, it), 0]
        bw = self.world_xyz(env, b[None].astype(float), 0.0)[0]
        fr.meshes.append(("cylinder", M.inst(M.trs([bw + (0, 2.5, 0)], [(0.12, 5.0, 0.12)]), (1.0, 0.9, 0.4, 0.6),
                                             (2.0, 0, 0, 0)), True))
        if tt >= rec.t_end[0] and rec.success[0]:
            pk = self.world_xyz(env, np.array([env["peak"]]), 0.0)[0]
            fr.meshes.append(("cone", M.inst(M.trs([pk + (0, 1.2, 0)], [(0.6, 1.4, 0.6)]), (1.0, 0.4, 0.3, 1),
                                             (1.5, 0, 0, 0)), False))

    def draw_reveal(self, sc, fr, env, win, rec, k, ctx):
        self.draw(sc, fr, env, win, rec, k, ctx)


# ====================================================================================== boids
class Flock(Trial):
    key = "flock"
    name = "MURMURATION"
    algo = "OPENAI EVOLUTION STRATEGIES"
    style = "lab"
    dims = "3D"
    physics = "3D boids · separation, alignment, cohesion · hawks dive on the snares"
    goal = "Get most of the flock to the roost alive"
    affinity = {"mid": 0.6, "vocal": 0.4, "bright": 0.3}
    accent = (0.95, 0.8, 0.55)
    causes = ["OUT OF TIME", "EATEN", "SCATTERED"]
    dim = 8
    pop = 24
    ghosts = 0
    g_max = 60
    version = 1
    NB = 36

    def level(self, feats):
        return 0.25 + 0.2 * min(1.0, feats["mid"] * 1.5)

    def optimizer(self, env, rng):
        from ..evolve import OpenES
        return OpenES(self.dim, self.pop, rng, sigma=0.1, lr=0.05)

    def env(self, mu, ch, rng, level):
        D_ = 40.0 + 40.0 * level
        r = np.random.default_rng([int(rng.integers(1 << 30)), 9])
        d = 1.0
        nx, nz = int(D_ + 30), 24
        x0, z0 = -10.0, -12.0
        Xg, Zg = np.meshgrid(x0 + np.arange(nx) * d, z0 + np.arange(nz) * d)
        prof = mu.loud_profile(ch.t0, ch.t1, nx)
        H = 0.035 * (Zg ** 2) + 2.0 * (prof[None, :] - prof.mean()) + 0.6 * np.sin(Xg * 0.3 + r.uniform(0, 6))
        return {"H": H, "x0": x0, "z0": z0, "d": d, "goal": D_, "level": level, "seed": int(r.integers(1 << 30)),
                "every": 2 if level < 0.5 else 1, "hawks": 2 + int(2 * level), "need": 0.7}

    def window(self, env, mu, t0, t1):
        sn = mu.events("snare", t0, t1)
        if len(sn) < 4:
            sn = mu.events("kick", t0, t1)[::2]
        return {"T": t1 - t0, "t0": t0, "dives": sn[::2] if env["level"] < 0.4 else sn}

    def decode(self, G):
        return {"sep": 0.5 + 3.0 * G[:, 0], "ali": 2.0 * G[:, 1], "coh": 2.0 * G[:, 2], "goal": 0.2 + 1.8 * G[:, 3],
                "flee": 4.0 * G[:, 4], "rn": 1.0 + 3.0 * G[:, 5], "rf": 2.0 + 6.0 * G[:, 6], "spd": 2.2 + 2.6 * G[:, 7]}

    def rollout(self, env, win, G, record=False):
        steps = int(math.ceil(win["T"] * SIM_HZ))
        n = len(G)
        NB = self.NB
        r = np.random.default_rng([env["seed"], int(round(win["t0"] * 1000))])
        P0 = np.stack([r.uniform(-4, -1, NB), r.uniform(4, 6, NB), r.uniform(-2, 2, NB)], 1)
        dives = win["dives"]
        nh = env["hawks"]
        if n == 0:
            return _empty(steps, record, {"B": np.zeros((steps + 1, 0, NB, 3), np.float32),
                                          "H": np.zeros((steps + 1, 0, nh, 3), np.float32)})
        p = self.decode(G)
        gr = Ground3(env["H"], env["x0"], env["z0"], env["d"])
        X = np.repeat(P0[None], n, 0)
        V = np.zeros_like(X)
        V[..., 0] = 2.0
        alive = np.ones((n, NB), bool)
        home = np.zeros((n, NB), bool)
        hk = np.zeros((n, nh, 3))
        hk[..., 0], hk[..., 1] = -6.0, 14.0
        hv = np.zeros_like(hk)
        dive_end = np.full((n, nh), -1.0)
        goal = np.array([env["goal"], 0.0, 0.0])
        gy = float(gr.sample(np.array([goal[0]]), np.array([0.0]))[0][0])
        goal[1] = gy + 3.0
        recB = np.zeros((steps + 1, n, NB, 3), np.float32) if record else None
        recH = np.zeros((steps + 1, n, nh, 3), np.float32) if record else None
        recA = np.zeros((steps + 1, n, NB), np.uint8) if record else None
        dt = 1.0 / SIM_HZ
        t_end = np.full(n, win["T"])
        succ = np.zeros(n, bool)
        di = 0
        for f in range(steps):
            t = f * dt
            live = alive & ~home
            # neighbours (each bird sees birds within rn)
            dX = X[:, None, :, :] - X[:, :, None, :]                     # (n, i, j, 3): j - i
            d2 = (dX * dX).sum(-1) + np.eye(NB)[None] * 1e9
            lv = live[:, None, :] & live[:, :, None]
            nb = (d2 < p["rn"][:, None, None] ** 2) & lv
            cnt = nb.sum(-1, keepdims=True)
            coh = (np.where(nb[..., None], dX, 0.0).sum(2)) / np.maximum(cnt, 1)
            ali = (np.where(nb[..., None], V[:, None, :, :], 0.0).sum(2)) / np.maximum(cnt, 1) - V
            close = nb & (d2 < 1.0)
            sep = -(np.where(close[..., None], dX / (d2[..., None] + 0.05), 0.0).sum(2))
            to_goal = goal[None, None, :] - X
            to_goal /= np.sqrt((to_goal * to_goal).sum(-1, keepdims=True)) + 1e-9
            # hawks: flee those within sensing range
            dh = X[:, :, None, :] - hk[:, None, :, :]
            dh2 = (dh * dh).sum(-1)
            fl = (np.where((dh2 < p["rf"][:, None, None] ** 2)[..., None], dh / (dh2[..., None] + 0.5), 0.0)).sum(2)
            h, gxx, gzz = gr.sample(X[..., 0], X[..., 2])
            avoid = np.zeros_like(X)
            avoid[..., 1] = np.where(X[..., 1] < h + 1.5, 4.0, 0.0) - np.where(X[..., 1] > h + 9.0, 2.0, 0.0)
            avoid[..., 2] = -np.clip(X[..., 2] / 6.0, -1, 1) ** 3 * 4.0
            A = (p["sep"][:, None, None] * sep + p["ali"][:, None, None] * ali + p["coh"][:, None, None] * coh * 0.6
                 + p["goal"][:, None, None] * to_goal * 2.0 + p["flee"][:, None, None] * fl * 4.0 + avoid)
            V = V + A * dt * 3.0
            sp = np.sqrt((V * V).sum(-1, keepdims=True)) + 1e-9
            vmax = p["spd"][:, None, None]
            V = np.where(sp > vmax, V / sp * vmax, V)
            V = np.where(sp < 1.5, V / sp * 1.5, V)
            V = np.where(live[..., None], V, 0.0)
            X = X + V * dt
            # landing at the roost
            arrive = live & ((X[..., 0] > goal[0] - 1.5) & (np.abs(X[..., 2]) < 4.0))
            home |= arrive
            # hawk dives on the snares: each hawk takes its turn, aiming where the flock will be
            while di < len(dives) and dives[di] <= t:
                hh = di % nh
                fl_c = (X * live[..., None]).sum(1) / np.maximum(live.sum(1, keepdims=True), 1)
                fl_v = (V * live[..., None]).sum(1) / np.maximum(live.sum(1, keepdims=True), 1)
                aim = fl_c + fl_v * 0.6
                start = aim + np.array([-3.0, 7.0, 2.0 * (1 if hh % 2 else -1)])
                hk[:, hh] = start
                hv[:, hh] = (aim - start) / 0.6
                dive_end[:, hh] = t + 0.9
                di += 1
            diving = dive_end > t
            hk = np.where(diving[..., None], hk + hv * dt, hk + np.array([2.5, 0.0, 0.0]) * dt * 0.0
                          + (np.array([0.0, 14.0, 0.0]) - hk) * np.array([0.0, 0.02, 0.0]))
            hk[..., 0] = np.where(diving, hk[..., 0], hk[..., 0] + (X[..., 0].mean(1, keepdims=True) - 5.0 - hk[..., 0]) * 0.02)
            caught = (((X[:, :, None, :] - hk[:, None, :, :]) ** 2).sum(-1) < 1.44) & diving[:, None, :]
            alive &= ~(caught.any(-1) & ~home)
            frac_home = home.sum(1) / NB
            ok = ~succ & (frac_home >= env["need"])
            t_end = np.where(ok, t + dt, t_end)
            succ |= ok
            if record:
                recB[f + 1] = X
                recH[f + 1] = hk
                recA[f + 1] = alive.astype(np.uint8) + 2 * home.astype(np.uint8)
        if record:
            recB[0] = np.repeat(P0[None], n, 0)
            recH[0] = np.array([-6.0, 14.0, 0.0])
            recA[0] = 1
        frac_home = home.sum(1) / NB
        frac_dead = 1 - alive.sum(1) / NB
        cx = np.where(alive, X[..., 0], 0).sum(1) / np.maximum(alive.sum(1), 1)
        prog = np.clip(cx / env["goal"], 0, 1)
        cause = np.where(succ, -1, np.where(frac_dead > 1 - env["need"], 1, np.where(prog < 0.5, 2, 0))).astype(np.int16)
        # a doomed flock ends when the hawks have taken too many to make it
        fit = np.where(succ, 1.0 + 0.3 * (1 - t_end / win["T"]),
                       np.clip(0.6 * frac_home / env["need"] + 0.3 * prog - 0.3 * frac_dead, 0, 0.999))
        o = Outcome(fit, succ, t_end, cause)
        if record:
            o.states = {"B": recB, "H": recH, "A": recA}
        return o

    def describe(self, env, g):
        p = self.decode(g[None])
        return (f"separation {p['sep'][0]:.1f} · alignment {p['ali'][0]:.1f} · cohesion {p['coh'][0]:.1f} · "
                f"flee {p['flee'][0]:.1f} · sight {p['rf'][0]:.1f} m")

    def draw(self, sc, fr, env, win, rec, k, ctx):
        key = f"terrain-flock-{id(env)}"
        gr = Ground3(env["H"], env["x0"], env["z0"], env["d"])
        if key not in sc.engine.meshes:
            def col(X, H, Z, nrm):
                g = np.clip(nrm[..., 1], 0, 1)
                c = np.stack([0.08 + 0.08 * g, 0.18 + 0.12 * g, 0.06 + 0.02 * g], -1)
                return c * (0.85 + 0.15 * np.sin(X * 1.7) * np.cos(Z * 1.3))[..., None]
            v, i = terrain_mesh(gr, col)
            sc.engine.add_mesh(key, v, i)
        fr.meshes.append((key, IDENT, False))
        st = rec.states
        B = st["B"]
        f = int(min(max(k, 0), len(B) - 1))
        goal = env["goal"]
        if B.shape[1]:
            al = st["A"][f, 0]
            pos = B[f, 0]
            c = pos[al == 1].mean(0) if (al == 1).any() else np.array([goal, 4.0, 0.0])
            lo, hi = max(0, f - 60), min(len(B), f + 61)
            cs = B[lo:hi, 0].mean((0, 1))
            focus = 0.5 * c + 0.5 * cs
        else:
            focus = np.array([goal * ctx.get("reveal", 0.0), 5.0, 0.0])
        gy0 = float(gr.sample(np.array([focus[0]]), np.array([0.0]))[0][0])
        eye = np.array([focus[0] - 15.0, max(focus[1], gy0) + 7.0, 8.0])
        sc.backdrop(fr, (0.20, 0.38, 0.74), (0.90, 0.60, 0.38), horizon=0.6, sun=(0.75, 0.38, 0.05), stars=0.0)
        sc.cam3d(fr, eye, focus, fov=0.85, sun=(0.5, 0.7, 0.4), sky=(0.35, 0.45, 0.65), ground=(0.12, 0.12, 0.08),
                 fog=0.008, sun_i=1.4, ambient=0.4, shadow_r=22.0)
        sc.tone(False)
        gy = float(gr.sample(np.array([goal]), np.array([0.0]))[0][0])
        fr.meshes.append(("cylinder", M.inst(M.trs([(goal, gy + 2.0, 0)], [(0.7, 4.0, 0.7)]), (0.35, 0.22, 0.12, 1)), False))
        fr.meshes.append(("sphere", M.inst(M.trs([(goal, gy + 5.0, 0)], [(5.0, 3.6, 5.0)]), (0.25, 0.5, 0.25, 1)), False))
        if not B.shape[1]:
            return
        al = st["A"][f, 0]
        V = B[min(f + 1, len(B) - 1), 0] - B[max(f - 1, 0), 0]
        flap = 1.0 + 0.25 * np.sin(sc.t * 18.0 + np.arange(len(al)))
        live = al == 1
        if live.any():
            fr.meshes.append(("bird", M.inst(_orient(B[f, 0][live], V[live], 0.9, flap[live]), (0.08, 0.08, 0.1, 1)), False))
        H = st["H"][f, 0]
        Hv = st["H"][min(f + 1, len(B) - 1), 0] - st["H"][max(f - 1, 0), 0]
        fr.meshes.append(("bird", M.inst(_orient(H, Hv, 1.6, np.ones(len(H))), (0.55, 0.18, 0.1, 1)), False))
        dead = al == 0
        if dead.any():
            fr.meshes.append(("sphere", M.inst(M.trs(B[f, 0][dead], 0.12), (1, 1, 1, 0.5)), True))

    def draw_reveal(self, sc, fr, env, win, rec, k, ctx):
        self.draw(sc, fr, env, win, rec, k, ctx)


def _orient(P, V, size, flap):
    """Affines pointing the bird mesh (+x) along V, wings flapping by scaling z."""
    v = V / (np.linalg.norm(V, axis=1, keepdims=True) + 1e-9)
    v = np.where(np.linalg.norm(V, axis=1, keepdims=True) < 1e-6, np.array([1.0, 0, 0]), v)
    up = np.array([0.0, 1.0, 0.0])
    s = np.cross(v, up)
    s /= np.linalg.norm(s, axis=1, keepdims=True) + 1e-9
    u = np.cross(s, v)
    R = np.stack([v, u, -s], -1)                  # columns: x -> v, y -> u, z -> -s
    sc = np.stack([np.full(len(P), size), np.full(len(P), size), size * flap], 1)
    return M.trs(P, sc, R)
