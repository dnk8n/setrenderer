"""The whole set's running order, worked out once from the music so any frame can be drawn on its own:

* the trial board comes up over the intro, the hall of champions closes the set
* the set is split into up to twenty chapters (on downbeats, at least a couple of minutes each); the music
  of each chapter picks its trial (an assignment over the whole set, so every trial appears once in a long
  set and its place depends on what the music is doing there)
* each chapter opens with a reveal of the trial's world (a phrase), then rounds of attempts; what each round
  shows (an ancestor on the way to a success, the success, a dead end) is decided by the evolution itself
* curves for the decor (the low mids' drift, the breakdowns' calm), integrated up front
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import linear_sum_assignment

from .music import Music

RATE = 50.0                    # samples per second of the integrated curves


def h01(*a) -> float:
    s = hashlib.blake2b(repr(a).encode(), digest_size=8).digest()
    return int.from_bytes(s, "little") / 2 ** 64


@dataclass
class Round:
    t0: float
    t1: float
    k: int                      # index in its chapter


@dataclass
class Chapter:
    k: int
    trial: str
    t0: float
    t1: float
    reveal: tuple[float, float]
    rounds: list[Round] = field(default_factory=list)
    feats: dict = field(default_factory=dict)
    seed: int = 0


@dataclass
class Plan:
    chapters: list[Chapter] = field(default_factory=list)
    intro: tuple[float, float] = (0.0, 0.0)
    outro: tuple[float, float] = (0.0, 0.0)
    drift: np.ndarray | None = None
    calm: np.ndarray | None = None
    bar: float = 2.0


def _z(feats: list[dict], key: str) -> np.ndarray:
    v = np.array([f[key] for f in feats], float)
    sd = v.std()
    return (v - v.mean()) / sd if sd > 1e-9 else np.zeros_like(v)


def assign(feats: list[dict], pool: list[str], seed: int) -> list[str]:
    """Which trial each chapter gets: the best fit of the chapters' music to the trials' affinities (each trial
    at most once while there are enough), then swaps so the same kind of world doesn't come twice in a row."""
    from .trials import TRIALS
    n = len(feats)
    keys = sorted({k for t in pool for k in TRIALS[t].affinity})
    Z = {k: _z(feats, k) for k in keys}
    A = np.zeros((n, len(pool)))
    for j, t in enumerate(pool):
        for k, w in TRIALS[t].affinity.items():
            A[:, j] += w * Z[k]
        A[:, j] += np.array([0.6 * (h01(seed, "fit", t, c) - 0.5) for c in range(n)])
    order: list[str] = []
    done = 0
    while done < n:
        m = min(n - done, len(pool))
        r, c = linear_sum_assignment(-A[done:done + m])
        pick = [pool[j] for j in c[np.argsort(r)]]
        order += pick
        done += m
    style = {t: TRIALS[t].style for t in pool}
    for _ in range(3):
        for i in range(1, n):
            if style[order[i]] != style[order[i - 1]]:
                continue
            best = None
            for j in range(i + 1, n):
                if style[order[j]] == style[order[i - 1]]:
                    continue
                if i + 1 < n and j != i + 1 and style[order[i]] == style.get(order[j + 1] if j + 1 < n else "", ""):
                    continue
                cost = (A[i, pool.index(order[i])] + A[j, pool.index(order[j])]
                        - A[i, pool.index(order[j])] - A[j, pool.index(order[i])])
                if best is None or cost < best[0]:
                    best = (cost, j)
            if best is not None:
                j = best[1]
                order[i], order[j] = order[j], order[i]
    return order


def plan(mu: Music, cfg: dict, seed: int) -> Plan:
    from .trials import TRIALS
    P = Plan()
    dur = mu.dur
    bar = mu.bar
    P.bar = bar
    db = mu.downbeats if len(mu.downbeats) else np.arange(0.0, dur, bar)

    def snap(t):
        return float(db[int(np.argmin(np.abs(db - t)))]) if len(db) else t
    names = [t for t in (cfg.get("trials") or list(TRIALS)) if t in TRIALS] or list(TRIALS)
    first = float(db[0]) if len(db) and db[0] < 4 * bar else 0.0
    intro_bars = 8 if dur > 120 else 4
    i1 = min(dur, first + intro_bars * bar)
    P.intro = (first, i1)
    tail = min(30.0, max(4 * bar, 0.06 * dur)) if dur > 60 else min(4 * bar, 0.2 * dur)
    o0 = snap(dur - tail) if dur > 60 else dur - tail
    o0 = max(o0, i1)
    P.outro = (o0, max(o0, dur - 0.3))
    span = o0 - i1
    min_s = float(cfg.get("chapter_minutes", 2.5)) * 60.0
    rb_scale = 1.0
    if span < 3.0 * 8 * bar:
        # a short clip: one small chapter (the criteria's fixtures, previews)
        rb_scale = 0.5
    n = int(min(int(cfg.get("chapters", 20)), max(1 if span > 8 * bar * rb_scale else 0, math.floor(span / min_s)))) if span > 0 else 0
    if n == 0:
        P.outro = (i1, max(i1, dur - 0.3))
        _curves(P, mu, dur, bar)
        return P
    feats = []
    edges = [i1]
    for k in range(1, n):
        edges.append(snap(i1 + span * k / n))
    edges.append(o0)
    feats = [mu.feats(a, b) for a, b in zip(edges[:-1], edges[1:])]
    order = assign(feats, names, seed)
    for k in range(n):
        tr = TRIALS[order[k]]
        rb = max(2, int(round(tr.round_bars * rb_scale)))
        R = rb * bar
        reveal_bars = max(2, int(round(8 * rb_scale)))
        a, end = edges[k], edges[k + 1]
        reveal = (a, min(end, a + reveal_bars * bar))
        n_rounds = max(1, int((end - reveal[1]) // R))
        rounds = []
        t = reveal[1]
        for i in range(n_rounds):
            t1 = end if i == n_rounds - 1 else t + R
            rounds.append(Round(t, t1, i))
            t = t1
        P.chapters.append(Chapter(k=k, trial=order[k], t0=a, t1=end, reveal=reveal, rounds=rounds, feats=feats[k],
                                  seed=int(h01(seed, "chapter", k, order[k]) * 2 ** 31)))
    P.outro = (P.chapters[-1].t1, max(P.chapters[-1].t1, dur - 0.3))
    _curves(P, mu, dur, bar)
    return P


def _curves(P: Plan, mu: Music, dur: float, bar: float):
    from ..timeline import _attack_release
    n = int(math.ceil(dur * RATE)) + 2
    tt = np.arange(n) / RATE
    lowmid = np.clip(mu.an.at(mu.an.bands.get("lowmid", mu.an.loudness), tt), 0, 1)
    calm = np.zeros(n)
    for b in mu.st.breakdowns:
        if b.t1 - b.t0 >= 8 * bar - 0.05:
            calm = np.maximum(calm, np.clip(np.minimum((tt - b.t0) / bar, (b.t1 - tt) / bar), 0, 1))
    lm = _attack_release(lowmid.astype(np.float64), RATE, 0.25, 0.8)
    rate = (0.05 + 1.2 * lm) * (1.0 - 0.6 * calm)
    P.drift = np.concatenate([[0.0], np.cumsum(rate[:-1]) / RATE]).astype(np.float64)
    P.calm = calm.astype(np.float32)


def curve(arr: np.ndarray, t: float) -> float:
    x = t * RATE
    k = int(min(max(math.floor(x), 0), len(arr) - 2))
    f = min(max(x - k, 0.0), 1.0)
    return float(arr[k] * (1 - f) + arr[k + 1] * f)


def where(P: Plan, t: float):
    """(segment, chapter, round) at time t: segment is 'intro', 'reveal', 'round', 'outro'."""
    if not P.chapters or t < P.chapters[0].t0:
        return ("intro", None, None) if t < P.outro[0] or not P.chapters else ("outro", None, None)
    if t >= P.chapters[-1].t1:
        return "outro", None, None
    lo, hi = 0, len(P.chapters) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if P.chapters[mid].t0 <= t:
            lo = mid
        else:
            hi = mid - 1
    ch = P.chapters[lo]
    if t < ch.reveal[1] or not ch.rounds or t < ch.rounds[0].t0:
        return "reveal", ch, None
    for r in ch.rounds:
        if r.t0 <= t < r.t1:
            return "round", ch, r
    return "round", ch, ch.rounds[-1]
