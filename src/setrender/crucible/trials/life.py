"""Three more worlds with their own rules:

* LANDER: a rocket on a vector screen must land softly on a pad between mountains drawn from the set's
  waveform, in a gravity set by the sub and gusts of wind on the hats; its pilot (a small neural network) is
  found by the cross-entropy method.
* COMMONS: game theory on a grid (Nowak and May's spatial prisoner's dilemma). A tribe holds the land with
  one strategy (how likely it is to cooperate after each outcome of the last round); defectors invade on the
  drops; every beat each cell copies its most successful neighbour. The temptation to defect grows with the
  music's energy. A genetic algorithm searches for a strategy that keeps the commons.
* SLIME: a slime mould (Jones' Physarum model): thousands of agents follow and lay a chemical trail, and a
  network grows between the food. The mould's sensing and turning are tuned by differential evolution until
  its network joins every oat flake the music has scattered."""
from __future__ import annotations

import math

import numpy as np
from scipy import ndimage

from .. import draw as D
from .base import SIM_HZ, Outcome, Trial


def _empty(record, states) -> Outcome:
    o = Outcome(np.zeros(0), np.zeros(0, bool), np.zeros(0), np.zeros(0, np.int16))
    if record:
        o.states = states
    return o


# ====================================================================================== lander
class Lander(Trial):
    key = "lander"
    name = "SOFT LANDING"
    algo = "CROSS-ENTROPY METHOD · EVOLVED AUTOPILOT"
    style = "vector"
    dims = "2D VECTOR"
    physics = "vector screen · gravity from the sub · gusts of wind on the hats · limited fuel"
    goal = "Touch down on the pad, slowly and upright"
    affinity = {"low": 0.6, "calm": 0.4, "energy": -0.2}
    accent = (1.0, 0.7, 0.25)
    causes = ["OUT OF TIME", "CRASHED", "MISSED THE PAD", "LOST IN SPACE", "OUT OF FUEL"]
    pop = 32
    ghosts = 7
    g_max = 70
    version = 1
    dim = 11

    def level(self, feats):
        return 0.25 + 0.2 * min(1.0, feats["low"] * 1.5)

    def optimizer(self, env, rng):
        from ..evolve import CEM
        return CEM(self.dim, self.pop, rng)

    def env(self, mu, ch, rng, level):
        r = np.random.default_rng([int(rng.integers(1 << 30)), 23])
        xs = np.linspace(0, 120, 241)
        prof = mu.loud_profile(ch.t0, ch.t1, len(xs))
        hs = 6 + (prof - prof.min()) / max(np.ptp(prof), 1e-6) * (10 + 18 * level)
        hs += 3 * np.sin(xs * 0.21 + r.uniform(0, 6))
        pad_x = r.uniform(48, 82)
        pw = 14.0 - 11.0 * level
        m = np.abs(xs - pad_x) <= pw / 2
        hs[m] = hs[m].mean()
        return {"xs": xs, "hs": hs, "pad": (pad_x - pw / 2, pad_x + pw / 2, float(hs[m].mean())), "level": level,
                "g": 1.6 + 3.4 * level, "wind": 2.0 + 13.0 * level, "seed": int(r.integers(1 << 30)), "fuel": 1.0}

    def window(self, env, mu, t0, t1):
        hats = mu.events("hat", t0, t1)[::4]
        sub = mu.curve("sub", t0, t1, 30.0)
        r = np.random.default_rng([env["seed"], int(round(t0 * 1000))])
        return {"T": t1 - t0, "t0": t0, "gusts": hats, "gsign": np.where(r.random(len(hats)) < 0.5, -1.0, 1.0),
                "sub": sub, "beats": mu.events("beat", t0, t1)}

    def rollout(self, env, win, G, record=False):
        steps = int(math.ceil(win["T"] * SIM_HZ))
        n = len(G)
        if n == 0:
            return _empty(record, {"S": np.zeros((steps + 1, 0, 5), np.float32), "U": np.zeros((steps + 1, 0), np.float32)})
        # the autopilot: steer toward the pad, tilt to make the wanted sideways speed, keep the wanted sink rate
        kx = 0.05 + 0.6 * G[:, 0]
        vxm = 1.0 + 9.0 * G[:, 1]
        kv = 0.02 + 0.4 * G[:, 2]
        kth = 0.5 + 6.0 * G[:, 3]
        kom = 0.1 + 3.0 * G[:, 4]
        v0 = 0.2 + 3.0 * G[:, 5]
        ky = 0.02 + 0.4 * G[:, 6]
        vym = 1.0 + 12.0 * G[:, 7]
        t0 = G[:, 8]
        kt = 0.1 + 3.0 * G[:, 9]
        hold = 4.0 + 30.0 * G[:, 10]
        p0, p1, py = env["pad"]
        pc = 0.5 * (p0 + p1)
        sx, sy = pc - 22.0 - 20.0 * env["level"], max(py + 26.0, float(np.max(env["hs"])) + 8.0)
        x = np.full(n, sx)
        y = np.full(n, sy)
        vx = np.full(n, 2.0)
        vy = np.zeros(n)
        th = np.full(n, 0.0)
        om = np.zeros(n)
        fuel = np.full(n, 1.0)
        alive = np.ones(n, bool)
        succ = np.zeros(n, bool)
        t_end = np.full(n, win["T"])
        cause = np.zeros(n, np.int16)
        p0, p1, py = env["pad"]
        pc = 0.5 * (p0 + p1)
        dt = 1.0 / (SIM_HZ * 2)
        rec = np.zeros((steps + 1, n, 5), np.float32) if record else None
        recu = np.zeros((steps + 1, n), np.float32) if record else None
        xs, hs = env["xs"], env["hs"]
        gusts, gs = win["gusts"], win["gsign"]
        best = np.full(n, 1e9)
        touch_d = np.full(n, np.nan)
        touch_v = np.full(n, np.nan)
        for f in range(steps):
            if record:
                rec[f] = np.stack([x, y, th, fuel, alive], 1)
            for s in range(2):
                t = (f * 2 + s) * dt
                g = env["g"] * (0.85 + 0.3 * win["sub"][min(int(t * 30), len(win["sub"]) - 1)])
                vxt = np.clip(kx * (pc - x), -vxm, vxm)
                tht = np.clip(kv * (vx - vxt), -0.6, 0.6)
                tq = np.clip(kth * (tht - th) - kom * om, -1.0, 1.0)
                over = np.abs(x - pc) < 0.5 * (p1 - p0)
                alt = y - py
                vyt = np.where(over, -np.clip(v0 + ky * alt, 0.3, vym), np.clip(0.3 * (py + hold - y), -vym, 2.0))
                thr = np.where(fuel > 0, np.clip(t0 + kt * (vyt - vy), 0.0, 1.0), 0.0)
                wind = 0.0
                if len(gusts):
                    dtg = t - gusts
                    on = dtg > 0
                    wind = float((gs * np.where(on, np.exp(-np.where(on, dtg, 0) / 0.35), 0.0)).sum()) * env["wind"]
                ax = -np.sin(th) * thr * 2.6 * env["g"] + wind * 0.6
                ay = np.cos(th) * thr * 2.6 * env["g"] - g
                vx = np.where(alive, vx + ax * dt, vx)
                vy = np.where(alive, vy + ay * dt, vy)
                om = np.where(alive, (om + tq * 3.0 * dt) * (1 - 0.6 * dt), om)
                th = np.where(alive, th + om * dt, th)
                x = np.where(alive, x + vx * dt, x)
                y = np.where(alive, y + vy * dt, y)
                fuel = np.where(alive, fuel - thr * dt / 9.0, fuel)
            if record:
                recu[f + 1] = thr * alive
            ground = np.interp(x, xs, hs)
            best = np.minimum(best, np.hypot(x - pc, np.maximum(y - py, 0)))
            touch = alive & (y - 1.2 <= ground)
            if touch.any():
                on_pad = (x >= p0 + 1) & (x <= p1 - 1)
                soft = (np.abs(vy) < 3.0) & (np.abs(vx) < 2.0) & (np.abs(th) < 0.4)
                ok = touch & on_pad & soft
                bad = touch & ~ok
                succ |= ok
                t_end = np.where(touch, (f + 1) / SIM_HZ, t_end)
                cause = np.where(bad, np.where(soft & ~on_pad, 2, 1), cause)
                touch_d = np.where(touch, np.abs(x - pc), touch_d)
                touch_v = np.where(touch, np.hypot(vx, vy) + 3.0 * np.abs(th), touch_v)
                alive &= ~touch
                y = np.where(touch, ground + 1.2, y)
            lost = alive & ((x < -5) | (x > 125) | (y > 90))
            if lost.any():
                t_end[lost] = (f + 1) / SIM_HZ
                cause[lost] = 3
                alive &= ~lost
        if record:
            rec[steps] = np.stack([x, y, th, fuel, alive], 1)
        cause = np.where(succ, -1, np.where(alive & (fuel <= 0), 4, cause)).astype(np.int16)
        dist0 = math.hypot(sx - pc, sy - py)
        touched = np.isfinite(touch_d)
        land = 0.45 + 0.3 * np.exp(-np.nan_to_num(touch_v, nan=99.0) / 4.0) + 0.2 * (1 - np.clip(np.nan_to_num(touch_d, nan=99.0) / 30, 0, 1))
        fit = np.where(succ, 1.0 + 0.3 * fuel, np.clip(np.where(touched, land, 0.4 * (1 - best / dist0)), 0, 0.999))
        o = Outcome(fit, succ, t_end, cause)
        if record:
            o.states = {"S": rec, "U": recu}
        return o

    def describe(self, env, g):
        return (f"autopilot: sink {0.2 + 3.0 * g[5]:.1f} m/s near the pad, cruise {4 + 30 * g[10]:.0f} m up, "
                f"steering gain {0.5 + 6.0 * g[3]:.1f}")

    def draw(self, sc, fr, env, win, rec, k, ctx):
        sc.backdrop(fr, (0.0, 0.0, 0.0), (0.02, 0.01, 0.0), horizon=1.0, stars=0.6)
        sc.cam2d(fr, 60.0, 33.75, 33.75)
        sc.tone(True)
        W = fr.world
        amber = (1.0, 0.72, 0.28)
        xs, hs = env["xs"], env["hs"]
        W.add("sdf", D.polyline(np.stack([xs, hs], 1), 0.16, (*amber, 1), glow=0.5))
        p0, p1, py = env["pad"]
        bl = 0.5 + 0.5 * math.cos(ctx["beat_phase"] * math.tau)
        W.add("sdf", D.segs([(p0, py)], [(p1, py)], 0.35, (0.4, 1.0, 0.6, 1), glow=0.6))
        W.add("sdf", D.circles([(p0, py + 0.6), (p1, py + 0.6)], 0.35, (1.0, 0.3, 0.2, 0.4 + 0.6 * bl), glow=0.8))
        S = rec.states["S"]
        if S.shape[1] == 0:
            return
        f = int(min(max(k, 0), len(S) - 1))
        t = f / SIM_HZ
        U = rec.states["U"]
        for i in range(S.shape[1] - 1, -1, -1):
            x, y, th, fuel, al = S[f, i]
            a = 1.0 if i == 0 else 0.25
            te = rec.t_end[i]
            crashed = t >= te and rec.cause[i] in (1, 3)
            col = (*amber, a) if i else (1.0, 0.95, 0.85, 1.0)
            if crashed and i == 0:
                age = t - te
                r_ = np.random.default_rng(i)
                ang = r_.uniform(0, 6.28, 10)
                d = (0.5 + 6.0 * min(age, 1.5)) * r_.uniform(0.5, 1.0, 10)
                p = np.stack([x + np.cos(ang) * d, y + np.sin(ang) * d - 4 * age * age], 1)
                W.add("sdf", D.segs(p, p + np.stack([np.cos(ang * 3), np.sin(ang * 3)], 1) * 0.8, 0.12,
                                    (1.0, 0.6, 0.3, max(0.0, 1 - age / 2)), glow=0.4))
                continue
            if crashed:
                continue
            c, s = math.cos(th), math.sin(th)

            def R(px, py_):
                return (x + px * c - py_ * s, y + px * s + py_ * c)
            body = [R(0, 2.4), R(1.2, -0.4), R(-1.2, -0.4), R(0, 2.4)]
            W.add("sdf", D.polyline(np.array(body), 0.12, col, glow=0.3 if i == 0 else 0.0))
            W.add("sdf", D.segs([R(-0.9, -0.4), R(0.9, -0.4)], [R(-1.6, -1.4), R(1.6, -1.4)], 0.1, col))
            thr = float(U[f, i])
            if thr > 0.05 and t < te:
                fl = 1.0 + 1.6 * thr * (0.8 + 0.4 * math.sin(sc.t * 40 + i))
                W.add("sdf", D.segs([R(-0.5, -0.6), R(0.5, -0.6)], [R(0, -0.6 - fl), R(0, -0.6 - fl)], 0.12,
                                    (1.0, 0.5, 0.2, a), glow=0.6))
        fuel = float(S[f, 0, 3])
        W.add("sdf", D.boxes([(6.0, 62.0)], (4.0, 0.6), (*amber, 0.25), corner=0.2))
        W.add("sdf", D.boxes([(2.0 + 4.0 * max(fuel, 0), 62.0)], (4.0 * max(fuel, 0), 0.6), (*amber, 0.9), corner=0.2))


# ====================================================================================== the commons
NAMES = {"ALWAYS COOPERATE": (1, 1, 1, 1), "ALWAYS DEFECT": (0, 0, 0, 0), "TIT FOR TAT": (1, 0, 1, 0),
         "WIN-STAY, LOSE-SHIFT": (1, 0, 0, 1), "GRIM TRIGGER": (1, 0, 0, 0), "GENEROUS TIT FOR TAT": (1, 0.33, 1, 0.33),
         "SUSPICIOUS": (0, 0, 1, 0)}


def strategy_name(p) -> str:
    best = min(NAMES, key=lambda k: float(np.abs(np.array(NAMES[k]) - np.asarray(p)).sum()))
    d = float(np.abs(np.array(NAMES[best]) - np.asarray(p)).sum())
    return best if d < 0.9 else "A MIXED STRATEGY"


def payoff(p, q, T, R=1.0, P=0.1, S=0.0, eps=0.02) -> float:
    """Long-run payoff per round of memory-one strategy p against q (cooperation probabilities after CC, CD,
    DC, DD from each player's own point of view), with a little noise."""
    p = np.clip(np.asarray(p, float), eps, 1 - eps)
    q = np.clip(np.asarray(q, float), eps, 1 - eps)
    qq = q[[0, 2, 1, 3]]
    M = np.zeros((4, 4))
    for s in range(4):
        a, b = p[s], qq[s]
        M[s] = [a * b, a * (1 - b), (1 - a) * b, (1 - a) * (1 - b)]
    w, v = np.linalg.eig(M.T)
    st = np.real(v[:, int(np.argmin(np.abs(w - 1)))])
    st = st / st.sum()
    return float(st @ np.array([R, S, T, P]))


class Commons(Trial):
    key = "commons"
    name = "THE COMMONS"
    algo = "GENETIC ALGORITHM · SPATIAL PRISONER'S DILEMMA"
    style = "pixel"
    dims = "GRID · GAME THEORY"
    physics = "every beat each cell copies its most successful neighbour · mistakes happen · invaders on the drops"
    goal = "Find a strategy that holds the land and keeps it prosperous"
    affinity = {"vocal": 1.0, "minor": -0.3, "calm": 0.2}
    accent = (0.35, 0.9, 1.0)
    causes = ["OUT OF TIME", "OVERRUN BY DEFECTORS"]
    dim = 4
    pop = 24
    ghosts = 0
    g_max = 50
    version = 1
    GX, GY = 64, 36

    def level(self, feats):
        return 0.35 + 0.25 * min(1.0, feats["energy"])

    def env(self, mu, ch, rng, level):
        return {"T": 1.4 + 0.6 * level, "level": level, "seed": int(rng.integers(1 << 30)), "need": 0.8 + 0.08 * level,
                "noise": 0.02 + 0.13 * level, "rich": 0.8 + 0.15 * level}

    def window(self, env, mu, t0, t1):
        beats = mu.events("beat", t0, t1)
        drops = mu.events("drop", t0, t1)
        bars = mu.events("bar", t0, t1)
        inv = sorted(set(np.round(np.concatenate([drops, bars[1::max(1, int(4 - 3 * env["level"]))]]), 3)))
        r = np.random.default_rng([env["seed"], int(round(t0 * 1000))])
        pts = r.integers([3, 3], [self.GX - 3, self.GY - 3], (len(inv), 2))
        return {"T": t1 - t0, "t0": t0, "beats": beats, "inv": np.array(inv), "pts": pts,
                "kind": r.integers(1, 4, len(inv))}

    def rollout(self, env, win, G, record=False):
        n = len(G)
        beats = win["beats"]
        nb = len(beats)
        if n == 0:
            return _empty(record, {"grid": np.zeros((nb + 1, 0, self.GY, self.GX), np.uint8), "beats": beats})
        types = [None, (0, 0, 0, 0), (0.5, 0.5, 0.5, 0.5), (1, 1, 1, 1)]
        Tm = env["T"]
        M = np.zeros((n, 4, 4))
        for i in range(n):
            st = [G[i]] + types[1:]
            for a in range(4):
                for b in range(4):
                    M[i, a, b] = payoff(st[a], st[b], Tm, eps=env.get("noise", 0.02))
        grid = np.zeros((n, self.GY, self.GX), np.int8)
        r = np.random.default_rng([env["seed"], 3])
        seedp = r.integers([0, 0], [self.GX, self.GY], (6, 2))
        for (x, y) in seedp:
            grid[:, y, x] = 1
        rec = np.zeros((nb + 1, n, self.GY, self.GX), np.uint8) if record else None
        if record:
            rec[0] = grid
        share = np.zeros(n)
        low = np.ones(n)
        # the verdict comes at 85% of the phrase (the rest of the round shows it)
        b_goal = int(np.argmin(np.abs(beats - 0.85 * win["T"]))) if nb else 0
        share_goal = np.zeros(n)
        failed_goal = np.zeros(n, bool)
        t_fail = np.full(n, win["T"])
        failed = np.zeros(n, bool)
        ii = np.arange(n)[:, None, None]
        inv_t, pts, kinds = win["inv"], win["pts"], win["kind"]
        k_inv = 0
        for b in range(nb):
            t = beats[b]
            while k_inv < len(inv_t) and inv_t[k_inv] <= t:
                x, y = pts[k_inv]
                grid[:, max(y - 4, 0):y + 5, max(x - 4, 0):x + 5] = kinds[k_inv]
                # and mutants everywhere: a few percent of the cells switch to an invading type
                mr = np.random.default_rng([env["seed"], k_inv, 41])
                mm = mr.random((self.GY, self.GX)) < 0.03 + 0.05 * env["level"]
                grid[:, mm] = mr.integers(1, 4, int(mm.sum())).astype(np.int8)
                k_inv += 1
            # payoff from the eight neighbours (and itself), then copy the best in the neighbourhood
            pay = np.zeros(grid.shape)
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    nb_ = np.roll(np.roll(grid, dy, 1), dx, 2)
                    pay += M[ii, grid, nb_]
            best_t = grid.copy()
            best_p = pay.copy()
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    pn = np.roll(np.roll(pay, dy, 1), dx, 2)
                    tn = np.roll(np.roll(grid, dy, 1), dx, 2)
                    better = pn > best_p + 1e-9
                    best_p = np.where(better, pn, best_p)
                    best_t = np.where(better, tn, best_t)
            grid = best_t
            share = (grid == 0).mean((1, 2))
            low = np.minimum(low, share)
            newf = ~failed & (share < 0.1)
            t_fail = np.where(newf, t, t_fail)
            failed |= newf
            if b == b_goal:
                share_goal, failed_goal = share.copy(), failed.copy()
            if record:
                rec[b + 1] = grid
        if nb == 0:
            share_goal, failed_goal = share, failed
        # the commons must also prosper: the tribe's own games must pay (mistakes and all)
        rich = M[:, 0, 0] >= env.get("rich", 0.8)
        succ = ~failed_goal & (share_goal >= env["need"]) & rich
        cause = np.where(succ, -1, np.where(failed_goal, 1, 0)).astype(np.int16)
        fit = np.where(succ, 1.0 + 0.3 * low, np.clip(0.55 * share_goal / env["need"] + 0.2 * low
                                                      + 0.24 * np.clip(M[:, 0, 0] / env.get("rich", 0.8), 0, 1), 0, 0.999))
        t_goal = float(beats[b_goal]) if nb else win["T"]
        t_end = np.where(succ, t_goal, np.minimum(t_fail, t_goal))
        o = Outcome(fit, succ, t_end, cause)
        if record:
            o.states = {"grid": rec, "beats": beats}
        return o

    def hud_extra(self, sc, L, rr, snap, local):
        from .. import hud
        x0, y0 = 1540, 330
        hud.panel(L, x0, y0, 1856, y0 + 214)
        rows = [((60 / 255, 210 / 255, 250 / 255), f"THE TRIBE: {strategy_name(rr['G'][0])}"),
                ((215 / 255, 90 / 255, 110 / 255), "DEFECTORS (ALWAYS DEFECT)"), ((150 / 255, 140 / 255, 160 / 255), "COIN FLIPPERS"),
                ((250 / 255, 230 / 255, 120 / 255), "SUCKERS (ALWAYS COOPERATE)")]
        for k, (c, label) in enumerate(rows):
            L.add("sdf", D.boxes([(x0 + 32, y0 + 38 + 44 * k)], (10, 10), (*c, 1), space=D.SCREEN, corner=2))
            D.text(L, label, x0 + 54, y0 + 26 + 44 * k, 18, (1, 1, 1, 0.8), shadow=False)

    def describe(self, env, g):
        return (f"{strategy_name(g)}: cooperates after both cooperated {g[0]:.0%}, after being cheated {g[1]:.0%}, "
                f"after cheating {g[2]:.0%}, after both defected {g[3]:.0%}")

    def draw(self, sc, fr, env, win, rec, k, ctx):
        from .pixel import px_rect
        from ..engine import Layer
        fr.pixel = Layer()
        fr.pixel_rect = (0.0, 0.0, 1920.0, 1080.0)
        sc.campix(fr, 160.0, 90.0, 90.0)
        sc.backdrop(fr, (0.02, 0.03, 0.05), (0.01, 0.01, 0.02), horizon=1.0, pixel=320)
        sc.tone(True)
        Gd = rec.states["grid"]
        beats = rec.states["beats"]
        t = k / SIM_HZ
        b = int(np.searchsorted(beats, t, side="right"))
        img = np.zeros((self.GY, self.GX, 4), np.uint8)
        img[..., 3] = 255
        if Gd.shape[1]:
            g = Gd[min(b, len(Gd) - 1), 0]
            prev = Gd[max(b - 1, 0), 0]
            cols = np.array([[60, 210, 250], [215, 90, 110], [150, 140, 160], [250, 230, 120]], np.uint8)
            img[..., :3] = cols[g]
            ch_ = (g != prev)
            fade = max(0.0, 1.0 - (t - (beats[b - 1] if b > 0 else 0.0)) / 0.25)
            img[ch_, :3] = np.clip(img[ch_, :3].astype(float) + 120 * fade, 0, 255).astype(np.uint8)
            lum = (np.indices((self.GY, self.GX)).sum(0) % 2) * 14
            img[..., :3] = np.clip(img[..., :3].astype(int) - lum[..., None], 0, 255).astype(np.uint8)
        else:
            img[..., :3] = (60, 210, 250)
        sc.engine.texture("commons", img[::-1].copy())
        fr.pixel.add("img", np.array([[0, 0, 320, 180, 0, 0, 1, 1, 1, 1, 1, 1, 2, 0, 0, 0]], np.float32), "commons")


# ====================================================================================== slime mould
class Slime(Trial):
    key = "slime"
    name = "SLIME MOULD"
    algo = "DIFFERENTIAL EVOLUTION · PHYSARUM MODEL"
    style = "grid"
    dims = "2D AGENTS"
    physics = "5,000 agents that follow and lay a trail · it diffuses and decays · oat flakes on the bass hits"
    goal = "Grow one network that joins every oat flake"
    affinity = {"calm": 0.6, "mid": 0.4, "minor": 0.3}
    accent = (0.95, 0.9, 0.3)
    causes = ["OUT OF TIME", "STARVED"]
    dim = 6
    pop = 12
    ghosts = 0
    g_max = 45
    version = 1
    GX, GY = 160, 90
    NA = 5000

    def level(self, feats):
        return 0.3 + 0.2 * min(1.0, feats["calm"] * 2)

    def optimizer(self, env, rng):
        from ..evolve import DE
        return DE(self.dim, self.pop, rng)

    def env(self, mu, ch, rng, level):
        r = np.random.default_rng([int(rng.integers(1 << 30)), 29])
        k = 5 + int(round(7 * level))
        pts = []
        while len(pts) < k:
            p = r.uniform([12, 10], [self.GX - 12, self.GY - 10])
            if all(np.hypot(*(p - q)) > 22 for q in pts):
                pts.append(p)
        return {"food": np.array(pts), "level": level, "seed": int(r.integers(1 << 30))}

    def window(self, env, mu, t0, t1):
        return {"T": t1 - t0, "t0": t0, "beats": mu.events("beat", t0, t1), "hz": 30.0}

    def decode(self, G):
        return {"sa": 0.2 + 1.0 * G[:, 0], "so": 2.0 + 10.0 * G[:, 1], "ra": 0.1 + 0.9 * G[:, 2],
                "ss": 0.6 + 1.6 * G[:, 3], "dep": 1.0 + 4.0 * G[:, 4], "dec": 0.02 + 0.18 * G[:, 5]}

    def rollout(self, env, win, G, record=False):
        n = len(G)
        hz = win["hz"]
        steps = int(win["T"] * hz)
        GX, GY, NA = self.GX, self.GY, self.NA
        food = env["food"]
        if n == 0:
            return _empty(record, {"trail": [], "hz": hz})
        p = self.decode(G)
        r = np.random.default_rng([env["seed"], int(round(win["t0"] * 1000))])
        # the mould starts on the first flake
        x0 = food[0, 0] + r.normal(0, 2.0, NA)
        y0 = food[0, 1] + r.normal(0, 2.0, NA)
        h0 = r.uniform(0, 2 * np.pi, NA)
        x = np.repeat(x0[None], n, 0)
        y = np.repeat(y0[None], n, 0)
        h = np.repeat(h0[None], n, 0)
        trail = np.zeros((n, GY, GX))
        fx = np.clip(food[:, 0].astype(int), 0, GX - 1)
        fy = np.clip(food[:, 1].astype(int), 0, GY - 1)
        jit = r.normal(0, 0.15, (steps, NA))
        rec = [] if record else None
        succ = np.zeros(n, bool)
        t_end = np.full(n, win["T"])
        conn = np.zeros(n)
        off = (np.arange(n) * GX * GY)[:, None]

        def sense(ang, dist):
            sx = np.clip((x + np.cos(ang) * dist[:, None]).astype(int), 0, GX - 1)
            sy = np.clip((y + np.sin(ang) * dist[:, None]).astype(int), 0, GY - 1)
            return trail.reshape(-1)[(sy * GX + sx + off).ravel()].reshape(n, NA)
        for s in range(steps):
            trail[:, fy, fx] += 3.0
            sa, so, ra = p["sa"][:, None], p["so"], p["ra"][:, None]
            L, C, R = sense(h + sa, so), sense(h, so), sense(h - sa, so)
            turn = np.where((C >= L) & (C >= R), 0.0, np.where(L > R, ra, -ra))
            h = h + turn + jit[s][None]
            nx = x + np.cos(h) * p["ss"][:, None]
            ny = y + np.sin(h) * p["ss"][:, None]
            out = (nx < 0) | (nx >= GX) | (ny < 0) | (ny >= GY)
            h = np.where(out, h + np.pi, h)
            x = np.where(out, x, nx)
            y = np.where(out, y, ny)
            ix = np.clip(x.astype(int), 0, GX - 1)
            iy = np.clip(y.astype(int), 0, GY - 1)
            trail += (np.bincount((iy * GX + ix + off).ravel(), minlength=n * GX * GY)
                      .reshape(n, GY, GX) * p["dep"][:, None, None] * 0.05)
            trail = ndimage.uniform_filter(trail, size=(1, 3, 3), mode="constant") * (1 - p["dec"][:, None, None])
            if record and s % 2 == 0:
                rec.append(trail[0].astype(np.float16))
            if s % int(hz / 2) == int(hz / 2) - 1:
                for i in range(n):
                    if succ[i]:
                        continue
                    # the veins: only the strongest trail counts as network
                    thr = max(1.0, 0.45 * float(np.percentile(trail[i], 99)))
                    lab, _ = ndimage.label(trail[i] > thr)
                    ids = lab[fy, fx]
                    if (ids > 0).all():
                        best = np.bincount(ids).max()
                    else:
                        best = np.bincount(ids[ids > 0]).max() if (ids > 0).any() else 0
                    conn[i] = max(conn[i], best / len(food))
                    if (ids > 0).all() and len(set(ids.tolist())) == 1:
                        succ[i] = True
                        t_end[i] = (s + 1) / hz
        cause = np.where(succ, -1, np.where(conn < 0.3, 1, 0)).astype(np.int16)
        fit = np.where(succ, 1.0 + 0.3 * (1 - t_end / win["T"]), np.clip(conn * 0.99, 0, 0.999))
        o = Outcome(fit, succ, t_end, cause)
        if record:
            o.states = {"trail": rec, "hz": hz}
        return o

    def describe(self, env, g):
        p = self.decode(g[None])
        return (f"sensors {math.degrees(p['sa'][0]):.0f}° apart, {p['so'][0]:.1f} cells ahead · turns "
                f"{math.degrees(p['ra'][0]):.0f}° · trail fades {100 * p['dec'][0]:.0f}% a step")

    def draw(self, sc, fr, env, win, rec, k, ctx):
        sc.backdrop(fr, (0.06, 0.05, 0.03), (0.02, 0.02, 0.01), horizon=1.0, stars=0.0)
        sc.cam2d(fr, self.GX / 2, self.GY / 2, self.GY / 2)
        sc.tone(True)
        W = fr.world
        W.add("sdf", D.circles([(self.GX / 2, self.GY / 2)], 52.0, (0.16, 0.13, 0.08, 1), outline=1.2, dark=-0.6))
        tr = rec.states["trail"]
        if tr:
            j = int(min(max(k / SIM_HZ * rec.states["hz"] / 2, 0), len(tr) - 1))
            v = np.clip(np.log1p(tr[j].astype(np.float32)) / 3.0, 0, 1)
            img = np.zeros((self.GY, self.GX, 4), np.uint8)
            img[..., 0] = (255 * np.clip(v * 1.3, 0, 1)).astype(np.uint8)
            img[..., 1] = (255 * np.clip(v * 1.15, 0, 1)).astype(np.uint8)
            img[..., 2] = (255 * np.clip(v * 0.35, 0, 1)).astype(np.uint8)
            img[..., 3] = (255 * np.clip(v * 1.6, 0, 1)).astype(np.uint8)
            sc.engine.texture("slime", img[::-1].copy(), linear=True)
            W.add("img", np.array([[0, 0, self.GX, self.GY, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0]], np.float32), "slime")
        f = env["food"]
        W.add("sdf", D.boxes(f, (1.6, 1.0), (0.95, 0.88, 0.70, 1), angle=0.5, corner=0.7, outline=0.25, dark=0.3))
