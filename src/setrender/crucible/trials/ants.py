"""An ant colony on a grid (Dorigo's ant colony optimisation): ants leave the nest, choose their next cell by
pheromone and by the scent of the food, and when they find it they lay pheromone along the way they came, more
for a shorter way; pheromone evaporates. A trail forms; the trial is solved when the strongest trail from the
nest to the food is within 15% of the shortest way through the maze. The maze is cut from the chapter's onsets,
and walls move on the drops. The colony's own settings (how much it trusts pheromone and scent, how fast
pheromone fades, how many ants) are bred by a genetic algorithm: each attempt is a whole colony."""
from __future__ import annotations

import heapq
import math

import numpy as np

from .. import draw as D
from .base import SIM_HZ, Outcome, Trial

GW, GH = 32, 18
CELL = 60.0                                      # pixels per cell at 1080p
NB8 = np.array([(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)])
STEP_LEN = np.sqrt((NB8 ** 2).sum(1)).astype(float)


def shortest(walls: np.ndarray, a: tuple, b: tuple) -> float:
    """Dijkstra on the 8-connected grid (no corner cutting)."""
    dist = np.full(walls.shape, np.inf)
    dist[a[1], a[0]] = 0.0
    pq = [(0.0, a)]
    while pq:
        d, (x, y) = heapq.heappop(pq)
        if (x, y) == b:
            return d
        if d > dist[y, x]:
            continue
        for (dx, dy), L in zip(NB8, STEP_LEN):
            nx, ny = x + dx, y + dy
            if 0 <= nx < GW and 0 <= ny < GH and not walls[ny, nx] and not (dx and dy and (walls[y, nx] or walls[ny, x])):
                nd = d + L
                if nd < dist[ny, nx]:
                    dist[ny, nx] = nd
                    heapq.heappush(pq, (nd, (nx, ny)))
    return np.inf


def _loop_erase(seg: np.ndarray) -> np.ndarray:
    """The path without its loops (back to a cell already on it: cut the loop out)."""
    out, where = [], {}
    for c in map(tuple, seg.tolist()):
        if c in where:
            k = where[c]
            for d in out[k + 1:]:
                where.pop(d, None)
            out = out[:k + 1]
        else:
            where[c] = len(out)
            out.append(c)
    return np.array(out, np.int16)


class Ants(Trial):
    key = "ants"
    name = "ANT HIGHWAY"
    algo = "ANT COLONY OPTIMISATION · TUNED BY A GA"
    style = "grid"
    dims = "2D GRID"
    physics = "pheromone that evaporates · a maze cut from the onsets · walls move on drops"
    goal = "Lay a trail to the sugar, nearly as short as the shortest way, in time"
    affinity = {"perc": 0.7, "hats": 0.5, "kick": -0.2}
    accent = (1.0, 0.8, 0.3)
    causes = ["OUT OF TIME", "LONG WAY ROUND", "LOST"]
    dim = 6
    pop = 20
    ghosts = 0
    g_max = 50
    version = 1
    AMAX = 48

    def level(self, feats):
        return 0.25 + 0.2 * min(1.0, feats["perc"] * 2)

    def env(self, mu, ch, rng, level):
        r = np.random.default_rng([int(rng.integers(1 << 30)), 11])
        ons = mu.events("snare", ch.t0, ch.t1)
        for attempt in range(40):
            # every random choice is drawn up front, so a harder level only adds walls to the same maze
            KW = 7
            xs = np.linspace(5, GW - 6, KW).astype(int) + r.integers(-1, 2, KW)
            gaps = [(int(r.integers(1, GH - 4)), int(r.integers(2, 5)), int(r.integers(1, GH - 4)), int(r.integers(2, 4)),
                     r.random()) for _ in range(KW)]
            blocks = [(int(r.integers(3, GW - 4)), int(r.integers(1, GH - 2)), int(r.integers(1, 4)), int(r.integers(1, 4)))
                      for _ in range(24)]
            nest = (2, int(r.integers(3, GH - 3)))
            food = (GW - 3, int(r.integers(3, GH - 3)))
            k = 3 + int(round(4 * min(level * 1.25, 1.0)))
            order = np.argsort(r.random(KW))[:k]
            walls = np.zeros((GH, GW), bool)
            walls[0, :] = walls[-1, :] = walls[:, 0] = walls[:, -1] = True
            for j in sorted(order):
                x = xs[j]
                g0, h0, g1, h1, two = gaps[j]
                walls[1:-1, x] = True
                walls[g0:g0 + h0, x] = False
                if two < 0.6 - 0.4 * level:
                    walls[g1:g1 + h1, x] = False
            for (bx, by, bw, bh) in blocks[:4 + int(len(ons) / 200) + int(10 * level)]:
                walls[by:by + bh, bx:bx + bw] = True
            for (x, y) in (nest, food):
                walls[y - 2:y + 3, x - 2:x + 3] = False
                walls[0, :] = walls[-1, :] = walls[:, 0] = walls[:, -1] = True
            L = shortest(walls, nest, food)
            if np.isfinite(L) and L <= 1.7 * np.hypot(food[0] - nest[0], food[1] - nest[1]):
                break
        # what a drop does: one wall slides a quarter of the way along (only if the sugar stays reachable)
        moved, moved_col = None, None
        cols = np.nonzero(walls[1:-1].sum(0) > GH * 0.5)[0]
        for c in [int(cols[len(cols) // 2])] if len(cols) else []:
            for sh in (GH // 4, -GH // 4, GH // 3, -GH // 3):
                w2 = walls.copy()
                w2[1:-1, c] = np.roll(walls[1:-1, c], sh)
                if np.isfinite(shortest(w2, nest, food)):
                    moved, moved_col = w2, c
                    break
        return {"walls": walls, "nest": nest, "food": food, "short": float(L), "level": level, "moved": moved,
                "moved_col": moved_col,
                "seed": int(r.integers(1 << 30)), "tol": 1.3 - 0.27 * level, "time": 1.0 - 0.5 * level}

    def window(self, env, mu, t0, t1):
        step = mu.beat / 12.0
        return {"T": t1 - t0, "t0": t0, "step": step, "ticks": max(8, int((t1 - t0) / step)),
                "drops": mu.events("drop", t0, t1), "beat": mu.beat}

    def decode(self, G):
        return {"alpha": 0.5 + 2.5 * G[:, 0], "beta": 6.0 * G[:, 1], "rho": 0.002 + 0.06 * G[:, 2],
                "q": 0.5 + 6.0 * G[:, 3], "n": (12 + np.round(36 * G[:, 4])).astype(int), "eps": 0.15 * G[:, 5]}

    def rollout(self, env, win, G, record=False):
        ticks = win["ticks"]
        walls = env["walls"]
        nest, food = env["nest"], env["food"]
        n = len(G)
        A = self.AMAX
        if n == 0:
            o = Outcome(np.zeros(0), np.zeros(0, bool), np.zeros(0), np.zeros(0, np.int16))
            if record:
                o.states = {"ants": np.zeros((ticks + 1, 0, A, 3), np.int16), "ph": [], "ticks": ticks,
                            "step": win["step"], "path": []}
            return o
        p = self.decode(G)
        r = np.random.default_rng([env["seed"], int(round(win["t0"] * 1000))])
        U = r.random((ticks, A))
        E = r.random((ticks, A))
        free = ~walls
        # the food's scent: closeness by the grid distance
        fy, fx = np.mgrid[0:GH, 0:GW]
        scent = 1.0 / (1.0 + np.hypot(fx - food[0], fy - food[1]) * 0.35)
        ph = np.full((n, GH, GW), 0.05)
        pos = np.zeros((n, A, 2), np.int64)
        pos[..., 0], pos[..., 1] = nest
        mode = np.zeros((n, A), np.int8)                 # 0 searching, 1 carrying home along its path
        active = np.arange(A)[None, :] < p["n"][:, None]
        # stagger the start: one ant leaves per tick
        start = (np.arange(A)[None, :] % np.maximum(p["n"][:, None], 1)) * 1
        ML = 400
        path = np.zeros((n, A, ML, 2), np.int16)
        plen = np.zeros((n, A), np.int64)
        path[:, :, 0, 0], path[:, :, 0, 1] = nest
        plen[:] = 1
        visited = np.zeros((n, A, GH, GW), bool)
        visited[:, :, nest[1], nest[0]] = True
        rec = np.zeros((ticks + 1, n, A, 3), np.int16) if record else None
        rec_ph = []
        best_len = np.full(n, np.inf)
        t_end = np.full(n, win["T"])
        succ = np.zeros(n, bool)
        lost = np.zeros(n)
        ii, aa = np.meshgrid(np.arange(n), np.arange(A), indexing="ij")
        target = env["tol"] * env["short"]
        drops = win["drops"]
        walls_now = walls.copy()
        moved_walls = None
        for k in range(ticks):
            t = (k + 1) * win["step"]
            if len(drops) and moved_walls is None and t >= drops[0] and env["level"] > 0.0:
                # a drop shifts part of the maze: one wall column slides
                moved_walls = -1
                walls_now = env["moved"] if env.get("moved") is not None else walls
                if env.get("moved") is not None:
                    moved_walls = env["moved_col"]
                free = ~walls_now
            go = active & (k >= start) & (mode == 0)
            back = active & (mode == 1)
            # searching ants: choose among free, unvisited neighbours
            cx, cy = pos[..., 0], pos[..., 1]
            nx = np.clip(cx[..., None] + NB8[:, 0], 0, GW - 1)
            ny = np.clip(cy[..., None] + NB8[:, 1], 0, GH - 1)
            ok = free[ny, nx]
            diag = (NB8[:, 0] != 0) & (NB8[:, 1] != 0)
            ok &= ~(diag[None, None, :] & (walls_now[cy[..., None], nx] | walls_now[ny, cx[..., None]]))
            seen = np.take_along_axis(visited.reshape(n, A, -1), ny * GW + nx, 2)
            tau = ph[ii[..., None], ny, nx]
            w = (tau ** p["alpha"][:, None, None]) * (scent[ny, nx] ** p["beta"][:, None, None]) * ok * np.where(seen, 0.04, 1.0)
            ws = w.sum(-1)
            stuck = go & (ws <= 0)
            rand = (E[k][None, :] < p["eps"][:, None]) & go
            w = np.where(rand[..., None], ok.astype(float), w)
            ws = w.sum(-1)
            cum = np.cumsum(w, -1) / np.maximum(ws[..., None], 1e-30)
            ch_ = (cum < U[k][None, :, None]).sum(-1)
            ch_ = np.clip(ch_, 0, 7)
            mv = go & (ws > 0)
            npx = np.where(mv, np.take_along_axis(nx, ch_[..., None], 2)[..., 0], cx)
            npy = np.where(mv, np.take_along_axis(ny, ch_[..., None], 2)[..., 0], cy)
            visited[ii[mv], aa[mv], npy[mv], npx[mv]] = True
            li = np.minimum(plen, ML - 1)
            path[ii[mv], aa[mv], li[mv], 0] = npx[mv]
            path[ii[mv], aa[mv], li[mv], 1] = npy[mv]
            plen = np.where(mv, np.minimum(plen + 1, ML - 1), plen)
            # lost ants (nowhere new to go, or wandering too long) start over from the nest
            lost_now = stuck | (go & (plen >= ML - 2))
            lost += lost_now.sum(1)
            # returning ants walk their path back, one cell per tick
            bk = back
            plen = np.where(bk, plen - 1, plen)
            li = np.maximum(plen - 1, 0)
            bx = path[ii, aa, li, 0]
            by = path[ii, aa, li, 1]
            npx = np.where(bk, bx, npx)
            npy = np.where(bk, by, npy)
            home = bk & (plen <= 1)
            pos[..., 0], pos[..., 1] = npx, npy
            # found the food: lay pheromone on the way it came (more for a shorter way), then head home
            found = go & (np.abs(npx - food[0]) <= 1) & (np.abs(npy - food[1]) <= 1)
            if found.any():
                fi, fa = np.nonzero(found)
                for i_, a_ in zip(fi, fa):
                    L = int(plen[i_, a_])
                    seg = _loop_erase(path[i_, a_, :L])
                    path[i_, a_, :len(seg)] = seg
                    plen[i_, a_] = len(seg)
                    d = np.sqrt((np.diff(seg.astype(float), axis=0) ** 2).sum(1)).sum()
                    ph[i_, seg[:, 1], seg[:, 0]] += p["q"][i_] / max(d, 1.0) * 10.0
                    best_len[i_] = min(best_len[i_], d)
                mode[found] = 1
            reset = lost_now | home
            if reset.any():
                ri, ra = np.nonzero(reset)
                pos[ri, ra, 0], pos[ri, ra, 1] = nest
                visited[ri, ra] = False
                visited[ri, ra, nest[1], nest[0]] = True
                plen[ri, ra] = 1
                mode[ri, ra] = 0
            ph *= (1.0 - p["rho"][:, None, None])
            ph = np.maximum(ph, 0.01)
            # every beat: does the colony's strongest trail reach the food, short enough?
            if (k + 1) % 12 == 0 and t <= env.get("time", 1.0) * win["T"] + 1e-6:
                L = self.trail_length(ph, walls_now, nest, food)
                ok_ = ~succ & (L <= target)
                t_end = np.where(ok_, t, t_end)
                succ |= ok_
                if record:
                    rec_ph.append((k + 1, ph.astype(np.float16).copy()))
            if record:
                rec[k + 1, :, :, 0], rec[k + 1, :, :, 1] = pos[..., 0], pos[..., 1]
                rec[k + 1, :, :, 2] = mode + 2 * (~(active & (k >= start))).astype(np.int8)
        if record:
            rec[0, :, :, 0], rec[0, :, :, 1] = nest
            rec[0, :, :, 2] = 2
        L = self.trail_length(ph, walls_now, nest, food)
        cause = np.where(succ, -1, np.where(np.isfinite(L), 1, np.where(lost > 3 * p["n"], 2, 0))).astype(np.int16)
        q = np.where(np.isfinite(L), target / np.maximum(L, target), 0.0)
        fit = np.where(succ, 1.0 + 0.3 * (1 - t_end / win["T"]), np.clip(0.3 * np.isfinite(best_len) + 0.69 * q, 0, 0.999))
        o = Outcome(fit, succ, t_end, cause)
        if record:
            o.states = {"ants": rec, "ph": rec_ph, "ticks": ticks, "step": win["step"], "walls2": walls_now,
                        "moved": (moved_walls, float(drops[0]) if len(drops) else 1e9)}
        return o

    def trail_length(self, ph, walls, nest, food, maxlen=400) -> np.ndarray:
        """Follow the strongest pheromone from the nest (never back on itself): its length if it reaches the food."""
        n = len(ph)
        out = np.full(n, np.inf)
        for i in range(n):
            x, y = nest
            seen = {(x, y)}
            d = 0.0
            for _ in range(maxlen):
                best, bv = None, -1.0
                for (dx, dy), L in zip(NB8, STEP_LEN):
                    nx, ny = x + dx, y + dy
                    if not (0 <= nx < GW and 0 <= ny < GH) or walls[ny, nx] or (nx, ny) in seen:
                        continue
                    if dx and dy and (walls[y, nx] or walls[ny, x]):
                        continue
                    v = ph[i, ny, nx]
                    if v > bv:
                        best, bv = (nx, ny, L), v
                if best is None or bv <= 0.012:
                    break
                x, y, L = best
                seen.add((x, y))
                d += L
                if abs(x - food[0]) <= 1 and abs(y - food[1]) <= 1:
                    out[i] = d
                    break
        return out

    def describe(self, env, g):
        p = self.decode(g[None])
        return (f"{int(p['n'][0])} ants · trust in pheromone {p['alpha'][0]:.1f} · in scent {p['beta'][0]:.1f} · "
                f"evaporation {100 * p['rho'][0]:.1f}% a step")

    def draw(self, sc, fr, env, win, rec, k, ctx):
        st = rec.states
        sc.backdrop(fr, (0.30, 0.24, 0.15), (0.24, 0.19, 0.12), horizon=1.0, stars=0.0)
        sc.cam2d(fr, GW / 2, GH / 2, GH / 2 * 1.0)
        sc.tone(True)
        W = fr.world
        tt = k / SIM_HZ
        mv, tdrop = st.get("moved", (None, 1e9))
        walls = st.get("walls2") if (mv is not None and tt >= tdrop) else env["walls"]
        tick = int(min(max(tt / st["step"], 0), st["ticks"]))
        # pheromone, the latest snapshot (every beat), as a glowing texture
        phs = [p for p in st["ph"] if p[0] <= tick]
        img = np.zeros((GH, GW, 4), np.uint8)
        if phs:
            P = phs[-1][1][0].astype(np.float32)
            v = np.clip(np.log1p(P * 10.0) / 2.0, 0, 1)
            img[..., 0] = (255 * np.clip(v * 1.2, 0, 1)).astype(np.uint8)
            img[..., 1] = (255 * np.clip(v * 0.75, 0, 1)).astype(np.uint8)
            img[..., 2] = (255 * np.clip(v * 0.25, 0, 1)).astype(np.uint8)
            img[..., 3] = (255 * np.clip(v * 1.5, 0, 1)).astype(np.uint8)
        sc.engine.texture("ants-ph", img[::-1].copy(), linear=True)
        W.add("img", np.array([[0, 0, GW, GH, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 0, 0]], np.float32), "ants-ph")
        wy, wx = np.nonzero(walls)
        W.add("sdf", D.boxes(np.stack([wx + 0.5, GH - wy - 0.5], 1), (0.5, 0.5), (0.45, 0.36, 0.26, 1), corner=0.12,
                             outline=0.06, dark=0.35))
        nx, ny = env["nest"]
        fx, fy = env["food"]
        W.add("sdf", D.circles([(nx + 0.5, GH - ny - 0.5)], 1.4, (0.05, 0.03, 0.02, 1), outline=0.25, dark=-1.5))
        W.add("sdf", D.boxes([(fx + 0.1, GH - fy - 0.1), (fx + 0.9, GH - fy - 0.6), (fx + 0.4, GH - fy - 1.1)],
                             (0.4, 0.4), (1, 1, 1, 1), corner=0.06, outline=0.06, dark=0.15))
        A = st["ants"]
        if A.shape[1] == 0:
            return
        f0 = int(math.floor(tt / st["step"]))
        f0 = min(max(f0, 0), st["ticks"] - 1)
        u = min(max(tt / st["step"] - f0, 0.0), 1.0)
        a0, a1 = A[f0, 0], A[f0 + 1, 0]
        live = a1[:, 2] < 2
        x = a0[:, 0] * (1 - u) + a1[:, 0] * u + 0.5
        y = GH - (a0[:, 1] * (1 - u) + a1[:, 1] * u) - 0.5
        dx, dy = (a1[:, 0] - a0[:, 0]).astype(float), -(a1[:, 1] - a0[:, 1]).astype(float)
        ln = np.sqrt(dx * dx + dy * dy) + 1e-6
        dx, dy = np.where(ln > 0.1, dx / ln, 1.0), np.where(ln > 0.1, dy / ln, 0.0)
        # an ant: abdomen, thorax and head in a line, with legs that scuttle
        dark = (0.06, 0.04, 0.03, 1)
        for off, r_ in ((-0.22, 0.13), (0.0, 0.08), (0.17, 0.09)):
            W.add("sdf", D.circles(np.stack([x + dx * off, y + dy * off], 1)[live], r_, dark))
        wig = 0.06 * np.sin(sc.t * 40 + np.arange(len(x)))
        for side in (-1, 1):
            lx, ly = -dy * side, dx * side
            leg0 = np.stack([x, y], 1)[live]
            leg1 = np.stack([x + lx * 0.2 + dx * wig, y + ly * 0.2 + dy * wig], 1)[live]
            W.add("sdf", D.segs(leg0, leg1, 0.025, dark))
        carry = live & (a1[:, 2] == 1)
        if carry.any():
            W.add("sdf", D.circles(np.stack([x + dx * 0.42, y + dy * 0.42], 1)[carry], 0.13, (1, 1, 1, 1)))

    def draw_reveal(self, sc, fr, env, win, rec, k, ctx):
        self.draw(sc, fr, env, win, rec, k, ctx)
