"""Pixel-art games, drawn at 320x180 and scaled up by whole pixels, each with its own learner:

* FLAP: a puffball flaps through pipes whose gaps follow the music's brightness, one pipe every two beats;
  its brain is evolved by NEAT (Stanley and Miikkulainen 2002, through neat-python), which grows the network.
* SNAKE: moves one cell every quarter beat and learns by Q-learning, episode after episode.
* MAZE: a little robot with range finders in a maze cut from the music, evolved by novelty search
  (Lehman and Stanley 2011), which rewards new places rather than closeness to the exit.
* CROSSING: hop across lanes of traffic that arrive on the kicks, snares and hats, learned by SARSA.
* RUNNER: a platformer whose pits, ledges and spikes come from the music; a genetic algorithm evolves the
  sequence of jumps itself.

All original characters and art (no copied sprites or logos)."""
from __future__ import annotations

import math

import numpy as np

from .. import draw as D
from .base import SIM_HZ, Outcome, Trial

PW, PH = 320.0, 180.0


def _empty(record, states) -> Outcome:
    o = Outcome(np.zeros(0), np.zeros(0, bool), np.zeros(0), np.zeros(0, np.int16))
    if record:
        o.states = states
    return o


class PixelTrial(Trial):
    style = "pixel"
    dims = "PIXEL ART"
    version = 1
    palette = {"bg": (0.1, 0.1, 0.12)}

    def pixel_setup(self, sc, fr, top, bottom):
        from ..engine import Layer
        fr.pixel = Layer()
        fr.pixel_rect = (0.0, 0.0, 1920.0, 1080.0)
        sc.campix(fr, PW / 2, PH / 2, PH / 2)
        sc.backdrop(fr, top, bottom, horizon=1.0, pixel=320)
        sc.tone(True)
        return fr.pixel


def _neat_forward(*a):
    from ..evolve import neat_forward
    return neat_forward(*a)


def px_rect(L, x, y, w, h, col):
    """Axis-aligned pixel rectangles (x, y = bottom-left, y up)."""
    x, y, w, h = (np.atleast_1d(np.asarray(v, float)) for v in (x, y, w, h))
    n = max(len(x), len(y), len(w), len(h))
    x, y, w, h = (np.broadcast_to(v, (n,)) for v in (x, y, w, h))
    q = np.stack([np.stack([x, y], 1), np.stack([x + w, y], 1), np.stack([x + w, y + h], 1), np.stack([x, y + h], 1)], 1)
    L.add("poly", D.quads(np.round(q), col, space=D.PIXEL))


class Flap(PixelTrial):
    key = "flap"
    name = "FLAP"
    algo = "NEAT · NEUROEVOLUTION OF AUGMENTING TOPOLOGIES"
    physics = "pixel art · gravity and flaps · a pipe every two beats, its gap following the treble"
    goal = "Keep flying through the pipes for most of the phrase"
    affinity = {"hats": 0.6, "bright": 0.5, "perc": 0.3}
    accent = (1.0, 0.85, 0.25)
    causes = ["OUT OF TIME", "HIT A PIPE", "HIT THE GROUND", "FLEW TOO HIGH"]
    pop = 40
    ghosts = 15
    g_max = 60
    round_bars = 4
    HMAX = 16
    dim = (5 + 17) * 17 + 2 * 17

    def level(self, feats):
        return 0.25 + 0.2 * min(1.0, feats["hats"] * 2)

    def optimizer(self, env, rng):
        from ..evolve import NEATPy
        return NEATPy(5, self.pop, rng, self.HMAX)

    def env(self, mu, ch, rng, level):
        return {"gap": 70.0 - 46.0 * level, "speed": 70.0 + 40.0 * level, "every": 1 if level > 0.6 else 2,
                "level": level, "swing": 0.4 + 0.8 * level}

    def window(self, env, mu, t0, t1):
        beats = mu.events("beat", t0, t1 + 4 * mu.beat)
        tp = beats[::env["every"]]
        tp = tp[tp > 1.6]
        hm = mu.curve("highmid", t0, t1 + 4 * mu.beat, 20.0)
        br = np.interp(tp, np.arange(len(hm)) / 20.0, hm)
        y = 90 + (br - 0.5) * 120 * env["swing"]
        return {"T": t1 - t0, "t0": t0, "pipes": tp, "gy": np.clip(y, 22 + env["gap"] / 2, 172 - env["gap"] / 2)}

    def rollout(self, env, win, G, record=False):
        steps = int(math.ceil(win["T"] * SIM_HZ))
        n = len(G)
        tp, gy = win["pipes"], win["gy"]
        if n == 0:
            return _empty(record, {"Y": np.zeros((steps + 1, 0), np.float32), "F": np.zeros((steps + 1, 0), np.uint8)})
        y = np.full(n, 90.0)
        vy = np.zeros(n)
        alive = np.ones(n, bool)
        t_end = np.full(n, win["T"])
        cause = np.zeros(n, np.int16)
        passed = np.zeros(n)
        cool = np.zeros(n)
        BX = 70.0
        sp = env["speed"]
        g = env["gap"] / 2
        Y = np.zeros((steps + 1, n), np.float32) if record else None
        Fl = np.zeros((steps + 1, n), np.uint8) if record else None
        if record:
            Y[0] = y
        dt = 1.0 / SIM_HZ
        in_win = tp[tp < win["T"]]
        # the goal: still flying when 85% of the phrase has gone by (the rest of the round shows the verdict)
        t_goal = 0.85 * win["T"]
        succ = np.zeros(n, bool)
        for f in range(steps):
            t = f * dt
            if t < t_goal <= t + dt:
                succ = alive.copy()
            px = BX + sp * (tp - t)
            ahead = np.nonzero(px > BX - 14)[0]
            k = ahead[0] if len(ahead) else len(tp) - 1
            x_in = np.stack([y / 180, vy / 200, np.full(n, (px[k] - BX) / 320), np.full(n, (gy[k] + g) / 180) - y / 180,
                             y / 180 - np.full(n, (gy[k] - g) / 180)], 1)
            out = _neat_forward(G, x_in, 5, self.HMAX)
            flap = alive & (out > 0.0) & (cool <= 0)
            vy = np.where(flap, 150.0, vy - 520.0 * dt)
            cool = np.where(flap, 0.12, cool - dt)
            y = np.where(alive, y + vy * dt, y)
            hit_pipe = np.zeros(n, bool)
            near = np.abs(px - BX) < 12.0
            for j in np.nonzero(near)[0]:
                hit_pipe |= (y > gy[j] + g - 4) | (y < gy[j] - g + 4)
            for msk, code in ((hit_pipe, 1), (y < 14, 2), (y > 178, 3)):
                m = alive & msk
                if m.any():
                    t_end[m] = t + dt
                    cause[m] = code
                    alive &= ~m
            if record:
                Y[f + 1] = y
                Fl[f + 1] = flap
        in_goal = in_win[in_win < t_goal]
        npipes = max(len(in_goal), 1)
        passed = np.array([(in_goal < te).sum() for te in t_end], float)
        fit = np.where(succ, 1.0 + 0.3, np.clip(passed / npipes + 0.02 * t_end / t_goal, 0, 0.999))
        cause = np.where(succ, -1, np.where(t_end < t_goal, cause, 0)).astype(np.int16)
        o = Outcome(fit, succ, np.where(succ, t_goal, np.minimum(t_end, t_goal)), cause)
        if record:
            o.states = {"Y": Y, "F": Fl}
        return o

    def _net(self, g):
        """(weights (I+N, N), which of the N slots are live neurons) from an encoded NEAT network."""
        N = self.HMAX + 1
        W = g[:(5 + N) * N].reshape(5 + N, N)
        live = (np.abs(W).sum(0) > 0)
        live[-1] = True
        return W, live

    def hud_extra(self, sc, L, rr, snap, local):
        """The featured bird's brain as NEAT grew it: inputs on the left, its neurons, the flap on the right."""
        from .. import hud
        W, live = self._net(rr["G"][0].astype(float))
        N = self.HMAX + 1
        x0, y0, x1, y1 = 1500, 330, 1856, 600
        hud.panel(L, x0, y0, x1, y1)
        species = f" · {int(snap[0])} SPECIES" if snap is not None else ""
        D.text(L, "BRAIN" + species, x0 + 18, y0 + 10, 20, (1, 1, 1, 0.7), tracking=3, shadow=False)
        names = ["HEIGHT", "SPEED", "PIPE", "ROOM UP", "ROOM DOWN"]
        pos = {}
        for i in range(5):
            pos[i] = (x0 + 110, y0 + 70 + i * 42)
            D.text(L, names[i], x0 + 92, pos[i][1] - 10, 16, (1, 1, 1, 0.55), align=1.0, shadow=False)
        hid = [j for j in range(N - 1) if live[j]]
        for k, j in enumerate(hid):
            pos[5 + j] = (x0 + 190 + 44 * (k % 3), y0 + 70 + (k * 180 / max(len(hid), 1)) + 10)
        pos[5 + N - 1] = (x1 - 50, (y0 + y1) / 2 + 10)
        a0, a1, cs = [], [], []
        for a in range(5 + N):
            for b in range(N):
                if W[a, b] != 0 and a in pos and (5 + b) in pos:
                    a0.append(pos[a])
                    a1.append(pos[5 + b])
                    cs.append((0.4, 0.9, 1.0, 0.8) if W[a, b] > 0 else (1.0, 0.45, 0.4, 0.8))
        if a0:
            L.add("sdf", D.segs(a0, a1, 1.6, np.array(cs, np.float32), space=D.SCREEN))
        pts = np.array(list(pos.values()))
        L.add("sdf", D.circles(pts, 7, (1, 1, 1, 0.95), space=D.SCREEN, outline=2, dark=0.6))
        D.text(L, "FLAP", x1 - 50, pos[5 + N - 1][1] + 14, 16, (1, 1, 1, 0.6), align=0.5, shadow=False)

    def describe(self, env, g):
        W, live = self._net(g)
        return f"network grown by NEAT: {int(live[:-1].sum())} hidden neurons, {int((W != 0).sum())} connections"

    def draw(self, sc, fr, env, win, rec, k, ctx):
        L = self.pixel_setup(sc, fr, (0.36, 0.72, 0.92), (0.75, 0.90, 0.95))
        f = int(min(max(k, 0), len(rec.states["Y"]) - 1))
        t = f / SIM_HZ
        sp = env["speed"]
        BX = 70.0
        # ground scrolling
        off = (t * sp) % 16
        px_rect(L, 0, 0, 320, 14, (0.85, 0.72, 0.42, 1))
        px_rect(L, np.arange(-16, 336, 16) - off, 10, 8, 4, (0.62, 0.78, 0.30, 1))
        # skyline far back
        hx = np.arange(0, 340, 20) - (t * sp * 0.25) % 20
        hh = 20 + 14 * np.abs(np.sin(np.arange(len(hx)) * 1.7 + np.floor(t * sp * 0.25 / 20) * 1.7))
        px_rect(L, hx, 14, 18, hh, (0.62, 0.82, 0.90, 1))
        g = env["gap"] / 2
        tp, gy = win["pipes"], win["gy"]
        px = BX + sp * (tp - t)
        vis = (px > -20) & (px < 340)
        for x, y in zip(px[vis], gy[vis]):
            px_rect(L, x - 10, y + g, 20, 180 - (y + g), (0.30, 0.70, 0.30, 1))
            px_rect(L, x - 12, y + g, 24, 6, (0.22, 0.55, 0.22, 1))
            px_rect(L, x - 10, 14, 20, y - g - 14, (0.30, 0.70, 0.30, 1))
            px_rect(L, x - 12, y - g - 6, 24, 6, (0.22, 0.55, 0.22, 1))
            px_rect(L, x - 7, 14, 3, 166, (0.55, 0.85, 0.45, 0.6))
        Y = rec.states["Y"]
        if Y.shape[1] == 0:
            return
        Fl = rec.states["F"]
        for i in range(Y.shape[1] - 1, -1, -1):
            te = rec.t_end[i]
            dead = t >= te and not rec.success[i]
            ff = min(f, int(te * SIM_HZ)) if dead else f
            y = float(Y[ff, i])
            if dead:
                y = max(14.0, y - (t - te) * 160.0)
            x = BX - (t - te) * sp * 0.7 if dead else BX
            if x < -10:
                continue
            flap = bool(Fl[max(ff - 3, 0):ff + 1, i].any())
            _puffball(L, x, y, i == 0, dead, flap)


def _puffball(L, x, y, featured, dead, flap):
    a = 1.0 if featured else 0.35
    body = (1.0, 0.82, 0.25, a) if featured else (1.0, 1.0, 1.0, a)
    L.add("sdf", D.circles([(x, y)], 6.5, body, space=D.PIXEL))
    L.add("sdf", D.circles([(x + 3, y + 2)], 2.2, (1, 1, 1, a), space=D.PIXEL))
    L.add("sdf", D.circles([(x + 3.6, y + 2)], 1.0 if not dead else 0.5, (0.05, 0.05, 0.1, a), space=D.PIXEL))
    px_rect(L, x + 5, y - 2, 4, 2, (1.0, 0.45, 0.2, a))
    wy = y + (2 if flap else -2)
    px_rect(L, x - 6, wy - 1, 5, 3, (0.95, 0.65, 0.15, a) if featured else (0.9, 0.9, 0.9, a))


# ====================================================================================== Q-learning on a grid
class TabularQ:
    """Batch tabular Q-learning (or SARSA): each generation plays a batch of episodes with the same table
    (epsilon-greedy, each its own seed), then the table learns from all of their steps."""

    def __init__(self, n_states, n_actions, pop, rng, alpha=0.3, gamma=0.92, eps0=0.35, sarsa=False):
        self.S, self.A, self.pop, self.r = n_states, n_actions, pop, rng
        self.Q = np.zeros((n_states, n_actions))
        self.alpha, self.gamma, self.eps, self.sarsa = alpha, gamma, eps0, sarsa
        self.g = 0

    def ask(self):
        seeds = self.r.random(self.pop)
        eps = np.full(self.pop, self.eps)
        eps[0] = 0.0                                  # one greedy run per batch
        Q = np.repeat(self.Q.ravel()[None], self.pop, 0)
        return np.concatenate([seeds[:, None], eps[:, None], (np.tanh(Q / 8) + 1) / 2], 1)

    def tell(self, G, out):
        for tr in out.extra.get("trans", []):
            for (s, a, rwd, s2, a2, done) in tr:
                tgt = rwd if done else rwd + self.gamma * (self.Q[s2, a2] if self.sarsa else self.Q[s2].max())
                self.Q[s, a] += self.alpha * (tgt - self.Q[s, a])
        self.g += 1
        self.eps = max(0.03, self.eps * 0.93)


def q_of(G, S, A):
    x = np.clip(G[:, 2:2 + S * A], 1e-6, 1 - 1e-6)
    return (np.arctanh(2 * x - 1) * 8).reshape(len(G), S, A)


class Snake(PixelTrial):
    key = "snake"
    name = "SNAKE CHARMER"
    algo = "Q-LEARNING · REINFORCEMENT LEARNING"
    unit = "EPISODE"
    unit_scale = 16
    physics = "pixel art · one step every quarter beat"
    goal = "Grow the snake to its target length before the phrase ends"
    affinity = {"perc": 0.5, "kick": 0.3, "mid": 0.2}
    accent = (0.4, 1.0, 0.4)
    causes = ["OUT OF TIME", "HIT THE WALL", "BIT ITSELF"]
    pop = 16
    ghosts = 0
    g_max = 160
    GX, GY = 32, 18
    NS = 2 ** 11
    dim = 2 + NS * 3

    def level(self, feats):
        return 0.15 + 0.2 * min(1.0, feats["perc"] * 2)

    def optimizer(self, env, rng):
        return TabularQ(self.NS, 3, self.pop, rng)

    def env(self, mu, ch, rng, level):
        r = np.random.default_rng([int(rng.integers(1 << 30)), 13])
        walls = np.zeros((self.GY, self.GX), bool)
        nb = int(3 + 8 * level)
        for _ in range(nb):
            x, y = int(r.integers(4, self.GX - 6)), int(r.integers(3, self.GY - 4))
            if r.random() < 0.5:
                walls[y, x:x + int(r.integers(3, 7))] = True
            else:
                walls[y:y + int(r.integers(3, 6)), x] = True
        walls[7:11, 2:8] = False
        return {"walls": walls, "target": 6 + int(round(10 * level)), "seed": int(r.integers(1 << 30)), "level": level}

    def window(self, env, mu, t0, t1):
        step = mu.beat / 4.0
        return {"T": t1 - t0, "t0": t0, "step": step, "moves": int((t1 - t0) / step)}

    def rollout(self, env, win, G, record=False):
        M = win["moves"]
        n = len(G)
        GX, GY = self.GX, self.GY
        walls = env["walls"]
        if n == 0:
            return _empty(record, {"body": [], "food": np.zeros((M + 1, 0, 2), np.int16), "moves": M, "step": win["step"]})
        Q = q_of(G, self.NS, 3)
        rf = np.random.default_rng([env["seed"], int(round(win["t0"] * 1000))])
        foods = np.stack([rf.integers(1, GX - 1, 400), rf.integers(1, GY - 1, 400)], 1)
        foods = foods[~walls[foods[:, 1], foods[:, 0]]]
        DIRS = np.array([(1, 0), (0, 1), (-1, 0), (0, -1)])
        bodies = [[(5, 9), (4, 9), (3, 9)] for _ in range(n)]
        d = np.zeros(n, int)
        fi = np.zeros(n, int)
        alive = np.ones(n, bool)
        t_end = np.full(n, win["T"])
        cause = np.zeros(n, np.int16)
        trans = [[] for _ in range(n)]
        rngs = [np.random.default_rng([int(g * (1 << 30)), 99]) for g in G[:, 0]]
        eps = G[:, 1]
        target = env["target"]
        rec_b = [] if record else None
        rec_f = np.zeros((M + 1, n, 2), np.int16) if record else None
        succ = np.zeros(n, bool)

        def state(i):
            hx, hy = bodies[i][0]
            occ = set(bodies[i][:-1])

            def danger(dd):
                x, y = hx + DIRS[dd][0], hy + DIRS[dd][1]
                return x <= 0 or y <= 0 or x >= GX - 1 or y >= GY - 1 or walls[y, x] or (x, y) in occ
            fx, fy = foods[fi[i] % len(foods)]
            bits = [danger(d[i]), danger((d[i] + 1) % 4), danger((d[i] + 3) % 4), d[i] == 0, d[i] == 1, d[i] == 2,
                    d[i] == 3, fx < hx, fx > hx, fy < hy, fy > hy]
            return int(sum(int(b) << k for k, b in enumerate(bits)))
        s_cur = [state(i) for i in range(n)]
        a_cur = [0] * n
        for i in range(n):
            a_cur[i] = int(np.argmax(Q[i, s_cur[i]])) if rngs[i].random() >= eps[i] else int(rngs[i].integers(3))
        for m in range(M):
            if record:
                rec_b.append([list(b) for b in bodies])
                rec_f[m] = foods[fi % len(foods)]
            for i in range(n):
                if not alive[i]:
                    continue
                a = a_cur[i]
                d[i] = (d[i] + (0, 1, 3)[a]) % 4
                hx, hy = bodies[i][0]
                nx, ny = hx + DIRS[d[i]][0], hy + DIRS[d[i]][1]
                fx, fy = foods[fi[i] % len(foods)]
                reward = -0.01
                done = False
                if nx <= 0 or ny <= 0 or nx >= GX - 1 or ny >= GY - 1 or walls[ny, nx]:
                    cause[i], done, reward = 1, True, -1.0
                elif (nx, ny) in set(bodies[i][:-1]):
                    cause[i], done, reward = 2, True, -1.0
                else:
                    bodies[i].insert(0, (nx, ny))
                    if (nx, ny) == (fx, fy):
                        fi[i] += 1
                        reward = 1.0
                        if len(bodies[i]) >= target:
                            succ[i], done = True, True
                    else:
                        bodies[i].pop()
                if done:
                    alive[i] = False
                    t_end[i] = (m + 1) * win["step"]
                    trans[i].append((s_cur[i], a, reward, 0, 0, True))
                    continue
                s2 = state(i)
                a2 = int(np.argmax(Q[i, s2])) if rngs[i].random() >= eps[i] else int(rngs[i].integers(3))
                trans[i].append((s_cur[i], a, reward, s2, a2, False))
                s_cur[i], a_cur[i] = s2, a2
        if record:
            rec_b.append([list(b) for b in bodies])
            rec_f[M] = foods[fi % len(foods)]
        length = np.array([len(b) for b in bodies], float)
        cause = np.where(succ, -1, cause).astype(np.int16)
        fit = np.where(succ, 1.0 + 0.3 * (1 - t_end / win["T"]), np.clip((length - 3) / max(target - 3, 1), 0, 0.999))
        o = Outcome(fit, succ, t_end, cause, extra={"trans": trans})
        if record:
            o.states = {"body": rec_b, "food": rec_f, "moves": M, "step": win["step"]}
        return o

    def describe(self, env, g):
        return f"a table of {self.NS * 3:,} values learned from every step so far · exploring {100 * g[1]:.0f}% of moves"

    def draw(self, sc, fr, env, win, rec, k, ctx):
        L = self.pixel_setup(sc, fr, (0.08, 0.12, 0.10), (0.05, 0.08, 0.07))
        st = rec.states
        C = 10.0
        px_rect(L, 0, 0, 320, 180, (0.10, 0.16, 0.12, 1))
        gx, gy = np.meshgrid(np.arange(self.GX), np.arange(self.GY))
        chk = ((gx + gy) % 2 == 0)
        px_rect(L, gx[chk] * C, gy[chk] * C, C, C, (0.12, 0.19, 0.14, 1))
        w = env["walls"].copy()
        w[0, :] = w[-1, :] = w[:, 0] = w[:, -1] = True
        wy, wx = np.nonzero(w)
        px_rect(L, wx * C, wy * C, C, C, (0.30, 0.40, 0.32, 1))
        px_rect(L, wx * C + 1, wy * C + 6, C - 2, 3, (0.42, 0.55, 0.44, 1))
        if not st["body"]:
            return
        t = k / SIM_HZ
        m = int(min(max(t / st["step"], 0), st["moves"]))
        bodies = st["body"][min(m, len(st["body"]) - 1)]
        b = np.array(bodies[0])
        fx, fy = st["food"][m, 0]
        pulse = 1 if (ctx["beat_phase"] % 1) < 0.25 else 0
        px_rect(L, fx * C + 2 - pulse, fy * C + 2 - pulse, 6 + 2 * pulse, 6 + 2 * pulse, (1.0, 0.3, 0.35, 1))
        px_rect(L, fx * C + 5, fy * C + 8, 1, 2, (0.4, 0.8, 0.3, 1))
        dead = t >= rec.t_end[0] and not rec.success[0]
        cols = np.linspace(1.0, 0.55, len(b))
        for j, (x, y) in enumerate(b):
            c = (0.35 * cols[j], 0.95 * cols[j], 0.45 * cols[j], 1) if not dead else (0.6, 0.6, 0.6, 1)
            px_rect(L, x * C + 1, y * C + 1, C - 2, C - 2, c)
        hx, hy = b[0]
        px_rect(L, hx * C + 3, hy * C + 5, 2, 2, (0.05, 0.05, 0.05, 1))
        px_rect(L, hx * C + 6, hy * C + 5, 2, 2, (0.05, 0.05, 0.05, 1))


class Crossing(PixelTrial):
    key = "crossing"
    name = "RUSH HOUR"
    algo = "SARSA · REINFORCEMENT LEARNING"
    unit = "EPISODE"
    unit_scale = 16
    physics = "pixel art · lanes of traffic: trucks on the kicks, cars on the snares, bikes on the hats"
    goal = "Hop across the traffic again and again before the phrase ends"
    affinity = {"perc": 0.6, "energy": 0.4, "kick": 0.2}
    accent = (1.0, 0.5, 0.8)
    causes = ["OUT OF TIME", "SQUASHED"]
    pop = 16
    ghosts = 0
    g_max = 160
    round_bars = 8
    GX, GY = 16, 9
    NS = 16 * 9 * 8
    dim = 2 + NS * 5

    def level(self, feats):
        return 0.15 + 0.2 * min(1.0, feats["perc"] * 2)

    def optimizer(self, env, rng):
        return TabularQ(self.NS, 5, self.pop, rng, sarsa=True, gamma=0.9)

    def env(self, mu, ch, rng, level):
        r = np.random.default_rng([int(rng.integers(1 << 30)), 17])
        lanes = []
        for row in range(1, self.GY - 1):
            src = ["kick", "snare", "hat", "bass"][(row - 1) % 4]
            lanes.append({"row": row, "dir": 1 if row % 2 else -1, "speed": 4.0 + 6.0 * level * r.random() + 2.0 * (row % 3),
                          "src": src, "len": 3 if src == "kick" else (2 if src in ("snare", "bass") else 1)})
        return {"lanes": lanes, "need": 2 + int(round(3 * level)), "level": level, "keep": 0.5 + 0.5 * level}

    def window(self, env, mu, t0, t1):
        step = mu.beat / 4.0
        cars = []
        for ln in env["lanes"]:
            ev = mu.events(ln["src"], t0 - 6.0, t1)
            keep = env["keep"] if ln["src"] in ("hat", "snare") else 1.0
            ev = ev[:: max(1, int(round(1 / keep)))] if keep < 1 else ev
            if ln["src"] == "hat":
                ev = ev[::3]
            cars.append(ev)
        return {"T": t1 - t0, "t0": t0, "step": step, "moves": int((t1 - t0) / step), "cars": cars}

    def car_x(self, ln, t_spawn, t):
        x0 = -3.0 if ln["dir"] > 0 else self.GX + 2.0
        return x0 + ln["dir"] * ln["speed"] * (t - t_spawn)

    def occupied(self, env, win, t):
        """(GY, GX) cells covered by a vehicle at time t."""
        occ = np.zeros((self.GY, self.GX), bool)
        for ln, ev in zip(env["lanes"], win["cars"]):
            if not len(ev):
                continue
            x = self.car_x(ln, ev, t)
            vis = (x > -4) & (x < self.GX + 4)
            for xx in x[vis]:
                a = int(math.floor(min(xx, xx - ln["dir"] * (ln["len"] - 1))))
                b = int(math.floor(max(xx, xx - ln["dir"] * (ln["len"] - 1))))
                occ[ln["row"], max(a, 0):max(min(b + 1, self.GX), 0)] = True
        return occ

    def rollout(self, env, win, G, record=False):
        M = win["moves"]
        n = len(G)
        if n == 0:
            return _empty(record, {"pos": np.zeros((M + 1, 0, 2), np.int16), "moves": M, "step": win["step"]})
        Q = q_of(G, self.NS, 5)
        occ_t = [self.occupied(env, win, m * win["step"]) for m in range(M + 2)]
        pos = np.zeros((n, 2), int)
        pos[:, 0], pos[:, 1] = self.GX // 2, 0
        alive = np.ones(n, bool)
        crossed = np.zeros(n, int)
        t_end = np.full(n, win["T"])
        cause = np.zeros(n, np.int16)
        trans = [[] for _ in range(n)]
        rngs = [np.random.default_rng([int(g * (1 << 30)), 77]) for g in G[:, 0]]
        eps = G[:, 1]
        MV = [(0, 0), (0, 1), (0, -1), (-1, 0), (1, 0)]
        rec = np.zeros((M + 1, n, 2), np.int16) if record else None
        succ = np.zeros(n, bool)
        best_row = np.zeros(n)

        def state(i, m):
            x, y = pos[i]
            o = occ_t[min(m + 1, M + 1)]
            bits = [y + 1 < self.GY and o[y + 1, x], x > 0 and o[y, x - 1], x < self.GX - 1 and o[y, x + 1]]
            return ((y * self.GX + x) * 8 + sum(int(b) << k for k, b in enumerate(bits)))

        def pick(i, s):
            return int(np.argmax(Q[i, s])) if rngs[i].random() >= eps[i] else int(rngs[i].integers(5))
        s_cur = [state(i, 0) for i in range(n)]
        a_cur = [pick(i, s_cur[i]) for i in range(n)]
        for m in range(M):
            if record:
                rec[m] = pos
            o_next = occ_t[m + 1]
            for i in range(n):
                if not alive[i]:
                    continue
                a = a_cur[i]
                x = int(np.clip(pos[i, 0] + MV[a][0], 0, self.GX - 1))
                y = int(np.clip(pos[i, 1] + MV[a][1], 0, self.GY - 1))
                pos[i] = (x, y)
                reward, done = -0.02 + 0.05 * (MV[a][1] > 0), False
                best_row[i] = max(best_row[i], y + crossed[i] * self.GY)
                if o_next[y, x]:
                    cause[i], done, reward = 1, True, -1.0
                elif y == self.GY - 1:
                    crossed[i] += 1
                    reward = 1.0
                    pos[i] = (self.GX // 2, 0)
                    if crossed[i] >= env["need"]:
                        succ[i], done = True, True
                if done:
                    alive[i] = False
                    t_end[i] = (m + 1) * win["step"]
                    trans[i].append((s_cur[i], a, reward, 0, 0, True))
                    continue
                s2 = state(i, m + 1)
                a2 = pick(i, s2)
                trans[i].append((s_cur[i], a, reward, s2, a2, False))
                s_cur[i], a_cur[i] = s2, a2
        if record:
            rec[M] = pos
        cause = np.where(succ, -1, cause).astype(np.int16)
        fit = np.where(succ, 1.0 + 0.3 * (1 - t_end / win["T"]),
                       np.clip(best_row / (env["need"] * self.GY), 0, 0.999))
        o = Outcome(fit, succ, t_end, cause, extra={"trans": trans})
        if record:
            o.states = {"pos": rec, "moves": M, "step": win["step"], "crossed": crossed}
        return o

    def describe(self, env, g):
        return f"learning which hop is safe in each square · exploring {100 * g[1]:.0f}% of hops"

    def draw(self, sc, fr, env, win, rec, k, ctx):
        L = self.pixel_setup(sc, fr, (0.12, 0.10, 0.16), (0.08, 0.07, 0.10))
        C = 20.0
        t = k / SIM_HZ
        px_rect(L, 0, 0, 320, 20, (0.25, 0.55, 0.30, 1))
        px_rect(L, 0, 160, 320, 20, (0.25, 0.55, 0.30, 1))
        px_rect(L, 0, 20, 320, 140, (0.20, 0.20, 0.24, 1))
        for row in range(2, self.GY - 1):
            dash = np.arange(0, 320, 16) + (4 if row % 2 else 0)
            px_rect(L, dash, row * C - 1, 8, 2, (0.85, 0.80, 0.55, 1))
        cols = {"kick": (0.85, 0.30, 0.25), "snare": (0.30, 0.55, 0.95), "hat": (0.95, 0.85, 0.30), "bass": (0.75, 0.45, 0.95)}
        for ln, ev in zip(env["lanes"], win["cars"]):
            if not len(ev):
                continue
            x = self.car_x(ln, ev, t)
            vis = (x > -5) & (x < self.GX + 5)
            for xx in x[vis]:
                lx = min(xx, xx - ln["dir"] * (ln["len"] - 1))
                px_rect(L, lx * C + 1, ln["row"] * C + 3, ln["len"] * C - 2, C - 6, (*cols[ln["src"]], 1))
                fx = (lx + ln["len"]) * C - 4 if ln["dir"] > 0 else lx * C + 1
                px_rect(L, fx, ln["row"] * C + 6, 3, 8, (1.0, 0.95, 0.7, 1))
        P = rec.states["pos"]
        if P.shape[1] == 0:
            return
        m = int(min(max(t / rec.states["step"], 0), rec.states["moves"]))
        x, y = P[m, 0]
        dead = t >= rec.t_end[0] and not rec.success[0]
        if dead:
            px_rect(L, x * C + 2, y * C + 7, C - 4, 6, (0.4, 0.8, 0.35, 1))
        else:
            hop = 2 if (ctx["beat_phase"] * 4 % 1) < 0.5 else 0
            px_rect(L, x * C + 4, y * C + 4 + hop, C - 8, C - 8, (0.40, 0.90, 0.40, 1))
            px_rect(L, x * C + 6, y * C + 11 + hop, 3, 3, (1, 1, 1, 1))
            px_rect(L, x * C + 11, y * C + 11 + hop, 3, 3, (1, 1, 1, 1))


# ====================================================================================== novelty search maze
class Maze(PixelTrial):
    key = "maze"
    name = "DECEPTIVE MAZE"
    algo = "NOVELTY SEARCH"
    physics = "pixel art · a robot with five range finders and a compass · walls cut from the music"
    goal = "Find the exit (going straight for it leads into a trap)"
    affinity = {"minor": 0.6, "calm": 0.3, "mid": 0.2}
    accent = (0.6, 0.8, 1.0)
    causes = ["OUT OF TIME", "STUCK"]
    pop = 32
    ghosts = 15
    g_max = 80
    dim = 9 * 6 + 6 + 6 * 2 + 2
    CW, CH = 8, 5

    def level(self, feats):
        return 0.3 + 0.2 * min(1.0, feats["minor"])

    def optimizer(self, env, rng):
        from ..evolve import Novelty
        return Novelty(self.dim, self.pop, rng)

    def env(self, mu, ch, rng, level):
        r = np.random.default_rng([int(rng.integers(1 << 30)), 19])
        CW, CH = 5 + int(round(5 * level)), 3 + int(round(3 * level))
        # a perfect maze (depth-first), then a few extra openings so there is more than one way
        right = np.ones((CH, CW), bool)
        up = np.ones((CH, CW), bool)
        seen = np.zeros((CH, CW), bool)
        stack = [(0, 0)]
        seen[0, 0] = True
        while stack:
            x, y = stack[-1]
            nb = [(x + dx, y + dy) for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))
                  if 0 <= x + dx < CW and 0 <= y + dy < CH and not seen[y + dy, x + dx]]
            if not nb:
                stack.pop()
                continue
            nx, ny = nb[r.integers(len(nb))]
            if nx > x:
                right[y, x] = False
            elif nx < x:
                right[y, nx] = False
            elif ny > y:
                up[y, x] = False
            else:
                up[ny, x] = False
            seen[ny, nx] = True
            stack.append((nx, ny))
        extra = int(round(8 * (1 - level))) + 2
        for _ in range(extra):
            x, y = int(r.integers(0, CW - 1)), int(r.integers(0, CH - 1))
            if r.random() < 0.5:
                right[y, x] = False
            else:
                up[y, x] = False
        cw, chh = 300.0 / CW, 160.0 / CH
        segs = [(10, 10, 310, 10), (10, 170, 310, 170), (10, 10, 10, 170), (310, 10, 310, 170)]
        for y in range(CH):
            for x in range(CW):
                if right[y, x] and x < CW - 1:
                    segs.append((10 + (x + 1) * cw, 10 + y * chh, 10 + (x + 1) * cw, 10 + (y + 1) * chh))
                if up[y, x] and y < CH - 1:
                    segs.append((10 + x * cw, 10 + (y + 1) * chh, 10 + (x + 1) * cw, 10 + (y + 1) * chh))
        return {"segs": np.array(segs, float), "start": (10 + cw / 2, 10 + chh / 2), "exit": (310 - cw / 2, 170 - chh / 2),
                "level": level, "speed": 46.0 - 16.0 * level}

    def sensors(self, segs, x, y, h):
        """Distances along five rays (n,) for robots at (x, y) heading h, up to 60 px."""
        angs = np.array([-1.57, -0.785, 0.0, 0.785, 1.57])
        a = h[:, None] + angs[None]
        dx, dy = np.cos(a), np.sin(a)
        x1, y1, x2, y2 = (segs[:, k][None, None, :] for k in range(4))
        ex, ey = x2 - x1, y2 - y1
        den = dx[..., None] * ey - dy[..., None] * ex
        den = np.where(np.abs(den) < 1e-9, 1e-9, den)
        wx, wy = x1 - x[:, None, None], y1 - y[:, None, None]
        tt = (wx * ey - wy * ex) / den
        uu = (wx * dy[..., None] - wy * dx[..., None]) / den
        hit = (tt > 0) & (uu >= 0) & (uu <= 1)
        return np.minimum(np.where(hit, tt, 60.0).min(-1), 60.0)

    def rollout(self, env, win, G, record=False):
        steps = int(math.ceil(win["T"] * SIM_HZ))
        n = len(G)
        if n == 0:
            return _empty(record, {"P": np.zeros((steps + 1, 0, 3), np.float32)})
        W1 = (G[:, :54].reshape(n, 9, 6) - 0.5) * 4
        b1 = (G[:, 54:60] - 0.5) * 2
        W2 = (G[:, 60:72].reshape(n, 6, 2) - 0.5) * 4
        b2 = (G[:, 72:74] - 0.5) * 2
        segs = env["segs"]
        x = np.full(n, env["start"][0])
        y = np.full(n, env["start"][1])
        h = np.zeros(n)
        ex, ey = env["exit"]
        alive = np.ones(n, bool)
        t_end = np.full(n, win["T"])
        succ = np.zeros(n, bool)
        dmin = np.full(n, np.hypot(ex - x[0], ey - y[0]))
        d0 = dmin[0]
        rec = np.zeros((steps + 1, n, 3), np.float32) if record else None
        dt = 1.0 / SIM_HZ
        still = np.zeros(n)
        for f in range(steps):
            if record:
                rec[f, :, 0], rec[f, :, 1], rec[f, :, 2] = x, y, h
            if f % 2 == 0:
                s = self.sensors(segs, x, y, h) / 60.0
                ang = np.arctan2(ey - y, ex - x) - h
                ang = (ang + np.pi) % (2 * np.pi) - np.pi
                radar = np.stack([np.abs(ang) < 0.785, (ang >= 0.785) & (ang < 2.36), np.abs(ang) >= 2.36,
                                  (ang <= -0.785) & (ang > -2.36)], 1).astype(float)
                inp = np.concatenate([s, radar], 1)
                hid = np.tanh(np.einsum("ni,nij->nj", inp, W1) + b1)
                out = np.tanh(np.einsum("ni,nij->nj", hid, W2) + b2)
                turn, fwd = out[:, 0] * 3.0, (out[:, 1] * 0.5 + 0.5)
            h = np.where(alive, h + turn * dt, h)
            nx = x + np.cos(h) * fwd * env["speed"] * dt
            ny = y + np.sin(h) * fwd * env["speed"] * dt
            # stop at walls: the step is refused if it would cross a wall or come within 3 px of one
            x1, y1, x2, y2 = (segs[:, k][None, :] for k in range(4))
            px, py = nx[:, None] - x1, ny[:, None] - y1
            sx, sy = x2 - x1, y2 - y1
            u = np.clip((px * sx + py * sy) / (sx * sx + sy * sy), 0, 1)
            dd = np.hypot(px - u * sx, py - u * sy).min(1)
            ok = alive & (dd > 3.0)
            moved = np.hypot(nx - x, ny - y)
            x = np.where(ok, nx, x)
            y = np.where(ok, ny, y)
            still = np.where(ok & (moved > 0.05), 0, still + 1)
            dist = np.hypot(ex - x, ey - y)
            dmin = np.minimum(dmin, dist)
            got = alive & (dist < 10.0)
            succ |= got
            t_end = np.where(got, (f + 1) * dt, t_end)
            alive &= ~got
        if record:
            rec[steps, :, 0], rec[steps, :, 1], rec[steps, :, 2] = x, y, h
        cause = np.where(succ, -1, np.where(still > 3 * SIM_HZ, 1, 0)).astype(np.int16)
        fit = np.where(succ, 1.0 + 0.3 * (1 - t_end / win["T"]), np.clip(1.0 - dmin / d0, 0, 0.999))
        o = Outcome(fit, succ, t_end, cause, behaviour=np.stack([x / 320, y / 180], 1))
        if record:
            o.states = {"P": rec}
        return o

    def describe(self, env, g):
        return "a small brain: five range finders and a compass in, steering and speed out"

    def draw(self, sc, fr, env, win, rec, k, ctx):
        L = self.pixel_setup(sc, fr, (0.05, 0.06, 0.12), (0.03, 0.03, 0.07))
        px_rect(L, 10, 10, 300, 160, (0.08, 0.10, 0.18, 1))
        for (x1, y1, x2, y2) in env["segs"]:
            px_rect(L, min(x1, x2) - 2, min(y1, y2) - 2, abs(x2 - x1) + 4, abs(y2 - y1) + 4, (0.45, 0.55, 0.95, 1))
        ex, ey = env["exit"]
        b = 1 if (ctx["beat_phase"] % 1) < 0.3 else 0
        px_rect(L, ex - 6 - b, ey - 6 - b, 12 + 2 * b, 12 + 2 * b, (0.35, 1.0, 0.55, 1))
        snap = ctx.get("snap")
        if snap is not None and len(snap):
            a = np.asarray(snap, float)
            px_rect(L, a[:, 0] * 320 - 1, a[:, 1] * 180 - 1, 2, 2, (1.0, 0.7, 0.3, 0.55))
        P = rec.states["P"]
        if P.shape[1] == 0:
            return
        f = int(min(max(k, 0), len(P) - 1))
        t = f / SIM_HZ
        for i in range(P.shape[1] - 1, -1, -1):
            x, y, h = P[f, i]
            c = (1.0, 0.85, 0.3, 1) if i == 0 else (0.8, 0.85, 1.0, 0.35)
            s = 4 if i == 0 else 3
            px_rect(L, x - s, y - s, 2 * s, 2 * s, c)
            px_rect(L, x + math.cos(h) * 4 - 1, y + math.sin(h) * 4 - 1, 2, 2, (1, 1, 1, c[3]))
        if not (t >= rec.t_end[0] and not rec.success[0]):
            tr = P[max(0, f - 240):f + 1:6, 0]
            px_rect(L, tr[:, 0] - 0.5, tr[:, 1] - 0.5, 1, 1, (1.0, 0.85, 0.3, 0.6))


# ====================================================================================== the runner
class Runner(PixelTrial):
    key = "platform"
    name = "BEAT RUNNER"
    algo = "GENETIC ALGORITHM · EVOLVED BUTTON PRESSES"
    physics = "pixel art · a level built from the music: pits on the drops, ledges on the melody, spikes on the hats"
    goal = "Run and jump to the flag at the end of the phrase"
    affinity = {"energy": 0.5, "bright": 0.5, "kick": 0.2}
    accent = (1.0, 0.45, 0.35)
    causes = ["OUT OF TIME", "FELL IN A PIT", "SPIKED"]
    pop = 40
    ghosts = 15
    g_max = 80
    dim = 160

    def level(self, feats):
        return 0.25 + 0.2 * min(1.0, feats["energy"])

    def optimizer(self, env, rng):
        from ..evolve import GA
        return GA(self.dim, self.pop, rng, sigma=0.25, p_mut=0.04)

    def env(self, mu, ch, rng, level):
        return {"level": level, "speed": 60.0, "seed": int(rng.integers(1 << 30))}

    def window(self, env, mu, t0, t1):
        """The level for this phrase: ground tiles (16 px) with pits and ledges, spikes on hats."""
        T = t1 - t0
        sp = env["speed"]
        lv = 0.8 * env["level"]
        L = int((T * sp + 120) / 16) + 2
        ground = np.full(L, 2)                       # height in tiles
        r = np.random.default_rng([env["seed"], int(round(t0 * 1000))])
        beats = mu.events("beat", t0, t1)
        kicks = mu.events("kick", t0, t1)
        cen = mu.curve("highmid", t0, t1, 4.0)
        for j in range(6, L - 6):
            tt = (j * 16 - 40) / sp
            c = cen[min(int(tt * 4), len(cen) - 1)] if tt > 0 else 0.5
            ground[j] = 2 + int(np.clip(round((c - 0.4) * 6 * lv), -1, 3))
        pits = []
        for tk in kicks[2::max(2, int(6 - 4 * lv))]:
            j = int((tk * sp + 40) / 16)
            if 8 < j < L - 8 and r.random() < 0.5 + 0.4 * lv:
                wdt = 1 + int(r.random() < lv)
                ground[j:j + wdt] = -9
                pits.append(j)
        spikes = []
        hats = mu.events("hat", t0, t1)
        for th in hats[::max(3, int(10 - 7 * lv))]:
            j = int((th * sp + 70) / 16)
            if 8 < j < L - 8 and ground[j] > 0 and ground[j - 1] == ground[j] and ground[j + 1] == ground[j]:
                spikes.append(j)
        flag = int((T * sp * 0.92 + 40) / 16)
        ground[flag - 2:flag + 3] = ground[flag]
        if ground[flag] < 0:
            ground[flag - 2:flag + 3] = 2
        return {"T": T, "t0": t0, "ground": ground, "spikes": np.array(sorted(set(spikes)), int), "flag": flag,
                "beat": mu.beat, "beats": beats}

    def rollout(self, env, win, G, record=False):
        steps = int(math.ceil(win["T"] * SIM_HZ))
        n = len(G)
        gr = win["ground"]
        if n == 0:
            return _empty(record, {"P": np.zeros((steps + 1, 0, 2), np.float32)})
        sp = env["speed"]
        dt = 1.0 / SIM_HZ
        x = np.full(n, 24.0)
        y = np.full(n, gr[1] * 16.0)
        vy = np.zeros(n)
        alive = np.ones(n, bool)
        succ = np.zeros(n, bool)
        t_end = np.full(n, win["T"])
        cause = np.zeros(n, np.int16)
        slot = win["beat"] / 4.0
        rec = np.zeros((steps + 1, n, 2), np.float32) if record else None
        spk = set(win["spikes"].tolist())
        fx = win["flag"] * 16.0
        for f in range(steps):
            t = f * dt
            if record:
                rec[f, :, 0], rec[f, :, 1] = x, y
            j = np.clip((x / 16).astype(int), 0, len(gr) - 1)
            gh = gr[j] * 16.0
            on = alive & (np.abs(y - gh) < 0.5) & (gr[j] >= 0)
            s = min(int(t / slot), self.dim - 1)
            press = G[:, s]
            jump = on & (press > 0.72)
            vy = np.where(jump, np.where(press > 0.88, 300.0, 230.0), vy)
            vy = np.where(on & ~jump, 0.0, vy - 900.0 * dt)
            ny = y + vy * dt
            nx = x + sp * dt
            j2 = np.clip((nx / 16).astype(int), 0, len(gr) - 1)
            g2 = gr[j2] * 16.0
            # walls: running into a higher ledge stops the runner
            wall = alive & (g2 > ny + 2) & (gr[j2] > gr[j])
            nx = np.where(wall, x, nx)
            land = (ny <= g2) & (vy <= 0) & (gr[j2] >= 0) & (y >= g2 - 2)
            ny = np.where(land, g2, ny)
            vy = np.where(land, 0.0, vy)
            x = np.where(alive, nx, x)
            y = np.where(alive, ny, y)
            jj = (x / 16).astype(int)
            spiked = alive & np.array([(a in spk) for a in jj]) & (np.abs(y - gr[np.clip(jj, 0, len(gr) - 1)] * 16) < 4)
            fell = alive & (y < -30)
            for m, code in ((fell, 1), (spiked, 2)):
                if m.any():
                    t_end[m] = t + dt
                    cause[m] = code
                    alive &= ~m
            won = alive & (x >= fx)
            succ |= won
            t_end = np.where(won, t + dt, t_end)
            alive &= ~won
        if record:
            rec[steps, :, 0], rec[steps, :, 1] = x, y
        cause = np.where(succ, -1, cause).astype(np.int16)
        fit = np.where(succ, 1.0 + 0.3 * (1 - t_end / win["T"]), np.clip((x - 24) / (fx - 24), 0, 0.999))
        o = Outcome(fit, succ, t_end, cause)
        if record:
            o.states = {"P": rec}
        return o

    def describe(self, env, g):
        return f"{int((g > 0.72).sum())} jumps planned, {int((g > 0.88).sum())} of them long"

    def draw(self, sc, fr, env, win, rec, k, ctx):
        L = self.pixel_setup(sc, fr, (0.98, 0.70, 0.55), (0.98, 0.88, 0.72))
        P = rec.states["P"]
        f = int(min(max(k, 0), len(P) - 1))
        t = f / SIM_HZ
        if P.shape[1]:
            lo, hi = max(0, f - 30), min(len(P), f + 31)
            cam = float(P[lo:hi, 0, 0].mean()) - 110
        else:
            cam = env["speed"] * t
        cam = max(cam, 0.0)
        gr = win["ground"]
        hx = np.arange(-1, 22) * 24 - (cam * 0.3) % 24
        px_rect(L, hx, 30, 20, 30 + 10 * np.abs(np.sin(np.arange(23) * 2.3 + math.floor(cam * 0.3 / 24))),
                (0.95, 0.60, 0.50, 1))
        j0 = int(cam // 16)
        for j in range(j0, min(j0 + 22, len(gr))):
            if gr[j] < 0:
                continue
            x = j * 16 - cam
            px_rect(L, x, 0, 16, gr[j] * 16, (0.50, 0.30, 0.25, 1))
            px_rect(L, x, gr[j] * 16 - 4, 16, 4, (0.35, 0.75, 0.40, 1))
            px_rect(L, x + 3, gr[j] * 16 - 12, 2, 2, (0.6, 0.4, 0.3, 1))
        for j in win["spikes"]:
            if j0 <= j < j0 + 22:
                x = j * 16 - cam
                for s in range(4):
                    L.add("poly", D.tris([[(x + s * 4, gr[j] * 16), (x + s * 4 + 4, gr[j] * 16), (x + s * 4 + 2, gr[j] * 16 + 6)]],
                                         (0.9, 0.9, 0.95, 1), space=D.PIXEL))
        fx = win["flag"] * 16 - cam
        fy = gr[win["flag"]] * 16
        px_rect(L, fx, fy, 2, 40, (1, 1, 1, 1))
        px_rect(L, fx + 2, fy + 28, 14, 10, (1.0, 0.35, 0.35, 1))
        if P.shape[1] == 0:
            return
        for i in range(P.shape[1] - 1, -1, -1):
            te = rec.t_end[i]
            dead = t >= te and not rec.success[i]
            ff = min(f, int(te * SIM_HZ)) if (dead or rec.success[i]) else f
            x, y = P[ff, i]
            x -= cam
            if x < -16 or x > 336:
                continue
            a = 1.0 if i == 0 else 0.3
            body = (1.0, 0.45, 0.35, a) if i == 0 else (1, 1, 1, a)
            step_ = int(t * 8) % 2 if not dead else 0
            px_rect(L, x - 5, y + 2, 10, 10, body)
            px_rect(L, x - 3 + 3 * step_, y, 3, 3, (0.2, 0.2, 0.3, a))
            px_rect(L, x + 1 - 3 * step_, y, 3, 3, (0.2, 0.2, 0.3, a))
            px_rect(L, x + 1, y + 7, 3, 3, (1, 1, 1, a))
            if dead:
                px_rect(L, x - 6, y + 13, 12, 2, (0.9, 0.2, 0.2, a))
