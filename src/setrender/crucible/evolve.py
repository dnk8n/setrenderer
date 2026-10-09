"""The optimisers, and the evolution of one chapter at render time.

Every chapter's trial is evolved for real, once per render, before frames are drawn (in the render's prepare
step, one process per chapter within the CPU budget), and cached so a stopped render resumes the same run.
Nothing is decided in advance except the world (built from the music) and how fitness is measured.

A chapter is a row of rounds (each a stretch of the music). The evolution fills it with runs, one after the
other:

* a run evolves until something meets the goal in the music of the round where its success would be shown.
  A run that succeeds is shown as a journey: the best of its first generation, two from the middle and the
  generation just before success (four ancestors), then the success. A run that solves its world within a
  handful of generations is taken as a sign the world was too easy: it is made harder before anything is
  shown, and evolved again.
* after a success the next run faces a harder version of the world, carrying on with the same population.
* a run that reaches its last generation without success is a dead end: its first generation, three from
  the middle and its last (in the very round it was trying to pass) are shown, then it resets with a fresh population on a slightly easier world (as POET's
  environments do when nothing can solve them), and the overlay says so.

Every round shows the best individual of the generation it names, replayed in that round's own music, with a
few of its siblings as ghosts. Rollouts are batch-independent (every individual's arithmetic is its own), so
replaying a round while drawing gives exactly what was recorded.

Where a reference implementation exists it is used: CMA-ES is Hansen's pycma, CMA-ME (MAP-Elites with CMA-ES
emitters) is pyribs, NEAT is neat-python, and the genetic algorithms use DEAP's operators. The others follow
their papers: OpenAI-ES (Salimans et al. 2017), differential evolution (Storn and Price 1997), the
cross-entropy method (Rubinstein 1999), parallel tempering (Swendsen and Wang 1986), ALPS (Hornby 2006),
novelty search (Lehman and Stanley 2011) and the (mu, lambda)-ES with self-adaptation (Beyer and Schwefel 2002).
"""
from __future__ import annotations

import copy
import gzip
import hashlib
import json
import math
import os
import pickle
import random
import time
from pathlib import Path

import numpy as np

from .trials.base import concat

VERSION = 2


# ====================================================================================== optimisers
class Opt:
    name = ""

    def ask(self) -> np.ndarray:
        raise NotImplementedError

    def tell(self, G: np.ndarray, out) -> None:
        raise NotImplementedError


class _Ind(list):
    """A DEAP individual: a list of genes with a plain float fitness (all DEAP's operators need)."""
    fitness = 0.0


class GA(Opt):
    """A generational genetic algorithm with DEAP's operators: tournament selection (3), uniform crossover,
    Gaussian mutation per gene, and the best few carried over unchanged. Genes live in [0, 1]."""

    def __init__(self, dim, pop, rng, sigma=0.12, p_mut=0.15, elite=2, cxpb=0.9, x0=None):
        self.dim, self.pop, self.sigma, self.p_mut, self.elite, self.cxpb = dim, pop, sigma, p_mut, elite, cxpb
        self.seed = int(rng.integers(1 << 30))
        self.calls = 0
        self.P = rng.random((pop, dim)) if x0 is None else np.clip(x0 + rng.normal(0, 0.2, (pop, dim)), 0, 1)

    def ask(self):
        return self.P.copy()

    def tell(self, G, out):
        from deap import tools as t
        random.seed(self.seed * 1000003 + self.calls)      # DEAP draws from Python's random: seed it per step
        self.calls += 1
        inds = []
        for g, f in zip(G, out.fitness):
            ind = _Ind(g.tolist())
            ind.fitness = float(f)
            inds.append(ind)
        best = sorted(inds, key=lambda i: -i.fitness)[:self.elite]
        nxt = [_Ind(b) for b in best]
        while len(nxt) < self.pop:
            a, b = (_Ind(x) for x in t.selTournament(inds, 2, tournsize=3))
            if random.random() < self.cxpb:
                t.cxUniform(a, b, indpb=0.5)
            t.mutGaussian(a, mu=0.0, sigma=self.sigma, indpb=self.p_mut)
            nxt.append(a)
        self.P = np.clip(np.array(nxt[:self.pop], float), 0, 1)


class IslandGA(Opt):
    """Island-model GA: four DEAP GAs evolving apart, the best of each migrating to the next every few
    generations (a ring)."""

    def __init__(self, dim, pop, rng, islands=4, every=5):
        self.k, self.every = islands, every
        self.n = pop // islands
        self.isl = [GA(dim, self.n, rng, elite=1) for _ in range(islands)]
        self.g = 0

    def ask(self):
        return np.concatenate([i.ask() for i in self.isl])

    def tell(self, G, out):
        from .trials.base import Outcome
        self.g += 1
        best = []
        for j, isl in enumerate(self.isl):
            sl = slice(j * self.n, (j + 1) * self.n)
            isl.tell(G[sl], Outcome(out.fitness[sl], out.success[sl], out.t_end[sl], out.cause[sl]))
            best.append(G[sl][int(np.argmax(out.fitness[sl]))])
        if self.g % self.every == 0:
            for j, isl in enumerate(self.isl):
                isl.P[-1] = best[(j - 1) % self.k]


class CMAES(Opt):
    """CMA-ES through Hansen's reference implementation (pycma); sep=True keeps a diagonal covariance
    (sep-CMA-ES, Ros and Hansen 2008), which scales to many genes."""

    def __init__(self, dim, pop, rng, x0=None, sigma=0.25, sep=False):
        import warnings
        warnings.filterwarnings("ignore", module="cma")
        import cma
        opts = {"popsize": pop, "seed": int(rng.integers(1, 1 << 30)), "bounds": [0.0, 1.0], "verbose": -9,
                "CMA_diagonal": bool(sep), "tolx": 0, "tolfun": 0, "tolflatfitness": 10 ** 9, "tolstagnation": 10 ** 9}
        self.es = cma.CMAEvolutionStrategy(np.full(dim, 0.5) if x0 is None else np.asarray(x0, float), sigma, opts)

    def ask(self):
        self.X = self.es.ask()
        return np.clip(np.array(self.X, float), 0, 1)

    def tell(self, G, out):
        self.es.tell(self.X, [-float(f) for f in out.fitness])     # pycma minimises


class CMAME(Opt):
    """CMA-ME (Fontaine et al. 2020) through pyribs: MAP-Elites' archive of the best individual for each kind
    of body (a grid of two behaviour descriptors), filled by CMA-ES emitters that rank offspring by how much
    they improve the archive."""

    def __init__(self, dim, pop, rng, bins=6, sigma=0.2):
        from ribs.archives import GridArchive
        from ribs.emitters import EvolutionStrategyEmitter
        from ribs.schedulers import Scheduler
        s = int(rng.integers(1 << 30))
        self.bins = bins
        self.archive = GridArchive(solution_dim=dim, dims=[bins, bins], ranges=[(0.0, 1.0), (0.0, 1.0)], seed=s)
        # (no bounds on the emitters: with many genes, resampling into a box can loop for ever; genes are
        # clipped to [0, 1] where they are used instead)
        ems = [EvolutionStrategyEmitter(self.archive, x0=np.full(dim, 0.5), sigma0=sigma, ranker="2imp",
                                        batch_size=pop // 2, seed=s + 1 + k) for k in range(2)]
        self.sched = Scheduler(self.archive, ems)

    def ask(self):
        self.X = self.sched.ask()
        return np.clip(np.asarray(self.X, float), 0, 1)

    def tell(self, G, out):
        self.sched.tell(np.asarray(out.fitness, float), np.clip(np.asarray(out.behaviour, float)[:, :2], 0.0, 0.999))

    def snapshot(self) -> np.ndarray:
        a = np.full((self.bins, self.bins), np.nan, np.float32)
        d = self.archive.data(fields=["index", "objective"])
        if len(d["index"]):
            i, j = np.unravel_index(d["index"], (self.bins, self.bins))
            a[i, j] = d["objective"]
        return a


class NEATPy(Opt):
    """NEAT (Stanley and Miikkulainen 2002) through neat-python: genomes start as inputs wired straight to
    the output and grow neurons and connections by mutation, crossover lines genes up by innovation number,
    and species share fitness so new structures get time to improve. Each genome's feed-forward network is
    encoded as a fixed-size array (inputs, up to `hmax` hidden neurons in evaluation order, the output) so it
    can be stored and replayed exactly."""

    def __init__(self, n_in, pop, rng, hmax=16):
        import neat
        self.I, self.H = n_in, hmax
        self.N = hmax + 1
        self.dim = (n_in + self.N) * self.N + 2 * self.N
        text = NEAT_CONFIG.format(pop=pop, n_in=n_in)
        path = Path(os.environ.get("SETRENDER_CACHE", Path.home() / ".cache" / "setrender")) / f"neat-{pop}-{n_in}.cfg"
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists() or path.read_text() != text:
            path.write_text(text)
        self.config = neat.Config(neat.DefaultGenome, neat.DefaultReproduction, neat.DefaultSpeciesSet,
                                  neat.DefaultStagnation, str(path))
        self.pop = neat.Population(self.config, seed=int(rng.integers(1 << 30)))
        self.seed = int(rng.integers(1 << 30))
        self.calls = 0

    def encode(self, genome) -> np.ndarray:
        import neat
        net = neat.nn.FeedForwardNetwork.create(genome, self.config)
        I, N = self.I, self.N
        W = np.zeros((I + N, N))
        bias, resp = np.zeros(N), np.ones(N)
        idx = {k: i for i, k in enumerate(self.config.genome_config.input_keys)}
        evals = list(net.node_evals)[-N:]
        off = N - len(evals)                      # pad at the front, so the output is always the last node
        for j, (node, _a, _g, b, r, links) in enumerate(evals):
            jj = off + j
            idx[node] = I + jj
            bias[jj], resp[jj] = b, r
            for i, w in links:
                if i in idx:
                    W[idx[i], jj] = w
        return np.concatenate([W.ravel(), bias, resp])

    def ask(self):
        self.items = sorted(self.pop.population.items())
        return np.array([self.encode(g) for _, g in self.items])

    def tell(self, G, out):
        random.seed(self.seed * 1000003 + self.calls)
        self.calls += 1
        p = self.pop
        for (_, g), f in zip(self.items, out.fitness):
            g.fitness = float(f)
        p.population = p.reproduction.reproduce(p.config, p.species, p.config.pop_size, p.generation)
        if not p.species.species:
            p.population = p.reproduction.create_new(p.config.genome_type, p.config.genome_config, p.config.pop_size)
        p.species.speciate(p.config, p.population, p.generation)
        p.generation += 1

    def snapshot(self):
        return np.array([len(self.pop.species.species)], np.float32)


def neat_forward(G: np.ndarray, x: np.ndarray, n_in: int, hmax: int = 16) -> np.ndarray:
    """Run encoded NEAT networks (n, dim) on inputs (n, n_in): the output neuron's value (tanh)."""
    n = len(G)
    N = hmax + 1
    W = G[:, :(n_in + N) * N].reshape(n, n_in + N, N)
    b = G[:, (n_in + N) * N:(n_in + N) * N + N]
    r = G[:, (n_in + N) * N + N:]
    v = np.zeros((n, n_in + N))
    v[:, :n_in] = x
    for j in range(N):
        s = np.einsum("ni,ni->n", v[:, :n_in + j], W[:, :n_in + j, j])
        v[:, n_in + j] = np.tanh(b[:, j] + r[:, j] * s)
    return v[:, -1]


NEAT_CONFIG = """[NEAT]
fitness_criterion     = max
fitness_threshold     = 1e9
pop_size              = {pop}
reset_on_extinction   = True
no_fitness_termination = True

[DefaultGenome]
activation_default      = tanh
activation_mutate_rate  = 0.0
activation_options      = tanh
aggregation_default     = sum
aggregation_mutate_rate = 0.0
aggregation_options     = sum
bias_init_mean          = 0.0
bias_init_stdev         = 1.0
bias_max_value          = 30.0
bias_min_value          = -30.0
bias_mutate_power       = 0.5
bias_mutate_rate        = 0.7
bias_replace_rate       = 0.1
compatibility_disjoint_coefficient = 1.0
compatibility_weight_coefficient   = 0.5
conn_add_prob           = 0.3
conn_delete_prob        = 0.1
enabled_default         = True
enabled_mutate_rate     = 0.01
feed_forward            = True
initial_connection      = full_direct
node_add_prob           = 0.1
node_delete_prob        = 0.05
num_hidden              = 0
num_inputs              = {n_in}
num_outputs             = 1
response_init_mean      = 1.0
response_init_stdev     = 0.0
response_max_value      = 30.0
response_min_value      = -30.0
response_mutate_power   = 0.0
response_mutate_rate    = 0.0
response_replace_rate   = 0.0
weight_init_mean        = 0.0
weight_init_stdev       = 1.0
weight_max_value        = 30
weight_min_value        = -30
weight_mutate_power     = 0.5
weight_mutate_rate      = 0.8
weight_replace_rate     = 0.1
single_structural_mutation = False
structural_mutation_surer  = default

[DefaultSpeciesSet]
compatibility_threshold = 3.0

[DefaultStagnation]
species_fitness_func = max
max_stagnation       = 15
species_elitism      = 2

[DefaultReproduction]
elitism            = 2
survival_threshold = 0.2
min_species_size   = 2
"""


class OpenES(Opt):
    """OpenAI evolution strategies: mirrored noise around one parameter vector, rank-shaped fitness, Adam."""

    def __init__(self, dim, pop, rng, sigma=0.08, lr=0.04, x0=None):
        self.n, self.half, self.r = dim, pop // 2, rng
        self.sigma, self.lr = sigma, lr
        self.theta = np.full(dim, 0.5) if x0 is None else np.asarray(x0, float).copy()
        self.mo, self.v, self.t = np.zeros(dim), np.zeros(dim), 0

    def ask(self):
        self.eps = self.r.standard_normal((self.half, self.n))
        eps = np.concatenate([self.eps, -self.eps])
        return np.clip(self.theta + self.sigma * eps, 0, 1)

    def tell(self, G, out):
        f = out.fitness
        rk = np.empty(len(f))
        rk[np.argsort(f)] = np.arange(len(f))
        s = rk / (len(f) - 1) - 0.5
        eps = np.concatenate([self.eps, -self.eps])
        g = (s @ eps) / (len(f) * self.sigma)
        self.t += 1
        self.mo = 0.9 * self.mo + 0.1 * g
        self.v = 0.999 * self.v + 0.001 * g * g
        mh = self.mo / (1 - 0.9 ** self.t)
        vh = self.v / (1 - 0.999 ** self.t)
        self.theta = np.clip(self.theta + self.lr * mh / (np.sqrt(vh) + 1e-8), 0, 1)


class DE(Opt):
    """Differential evolution, rand/1/bin."""

    def __init__(self, dim, pop, rng, F=0.6, CR=0.8):
        self.n, self.pop, self.r, self.F, self.CR = dim, pop, rng, F, CR
        self.X = rng.random((pop, dim))
        self.fx = None

    def ask(self):
        if self.fx is None:
            return self.X.copy()
        r = self.r
        T = np.empty_like(self.X)
        for i in range(self.pop):
            a, b, c = r.choice([j for j in range(self.pop) if j != i], 3, replace=False)
            v = self.X[a] + self.F * (self.X[b] - self.X[c])
            m = r.random(self.n) < self.CR
            m[r.integers(self.n)] = True
            T[i] = np.clip(np.where(m, v, self.X[i]), 0, 1)
        return T

    def tell(self, G, out):
        if self.fx is None:
            self.X, self.fx = G.copy(), out.fitness.copy()
            return
        better = out.fitness >= self.fx
        self.X[better] = G[better]
        self.fx[better] = out.fitness[better]


class CEM(Opt):
    """Cross-entropy method: sample from a diagonal Gaussian, refit it to the elite fifth, keep some noise."""

    def __init__(self, dim, pop, rng, elite=0.2, sigma=0.3, floor=0.02):
        self.n, self.pop, self.r = dim, pop, rng
        self.mu, self.sd = np.full(dim, 0.5), np.full(dim, sigma)
        self.ne = max(2, int(pop * elite))
        self.floor = floor

    def ask(self):
        return np.clip(self.mu + self.sd * self.r.standard_normal((self.pop, self.n)), 0, 1)

    def tell(self, G, out):
        e = G[np.argsort(-out.fitness)[:self.ne]]
        self.mu = 0.7 * e.mean(0) + 0.3 * self.mu
        self.sd = np.maximum(0.7 * e.std(0) + 0.3 * self.sd, self.floor)


class Tempering(Opt):
    """Parallel tempering: a ladder of annealing chains at different temperatures; neighbours swap states."""

    def __init__(self, dim, pop, rng):
        self.n, self.k, self.r = dim, pop, rng
        self.T = 0.002 * (60.0 ** (np.arange(pop) / max(pop - 1, 1)))
        self.X = rng.random((pop, dim))
        self.fx = None

    def ask(self):
        if self.fx is None:
            return self.X.copy()
        step = 0.04 + 0.5 * np.sqrt(self.T)[:, None]
        return np.clip(self.X + self.r.normal(0, 1, self.X.shape) * step, 0, 1)

    def tell(self, G, out):
        f = out.fitness
        if self.fx is None:
            self.X, self.fx = G.copy(), f.copy()
            return
        acc = (f >= self.fx) | (self.r.random(self.k) < np.exp(np.minimum(0, (f - self.fx) / self.T)))
        self.X[acc], self.fx[acc] = G[acc], f[acc]
        for i in range(self.k - 1):
            d = (self.fx[i + 1] - self.fx[i]) * (1 / self.T[i] - 1 / self.T[i + 1])
            if d > 0 or self.r.random() < math.exp(d):
                self.X[[i, i + 1]] = self.X[[i + 1, i]]
                self.fx[[i, i + 1]] = self.fx[[i + 1, i]]


class ALPS(Opt):
    """Age-layered population structure (Hornby 2006): layers of the population are capped by age (how many
    generations their oldest lineage has been evolving), and the youngest layer is refilled with newcomers
    every few generations, so fresh ideas keep arriving without having to beat the veterans at once."""

    def __init__(self, dim, pop, rng, layers=4, gap=6):
        self.dim, self.pop, self.r = dim, pop, rng
        self.L, self.gap = layers, gap
        self.n = pop // layers
        self.P = rng.random((pop, dim))
        self.age = np.zeros(pop)
        self.g = 0
        self.ga = GA(dim, 2, rng)

    def ask(self):
        return self.P.copy()

    def tell(self, G, out):
        f = out.fitness
        r = self.r
        self.g += 1
        cap = np.array([self.gap * (2 ** k) for k in range(self.L)], float)
        cap[-1] = 1e9
        layer = np.minimum(np.searchsorted(cap, self.age, side="right"), self.L - 1)
        nxt, nage = [], []
        for k in range(self.L):
            idx = np.nonzero(layer <= k)[0]
            idx = idx[np.argsort(-f[idx])][: max(2, self.n * 2)]
            if len(idx) == 0:
                idx = np.argsort(-f)[:2]
            nxt.append(G[idx[0]].copy())
            nage.append(self.age[idx[0]] + 1)
            for _ in range(self.n - 1):
                a, b = idx[r.integers(len(idx))], idx[r.integers(len(idx))]
                if f[b] > f[a]:
                    a, b = b, a
                c = np.where(r.random(self.dim) < 0.5, G[a], G[b])
                c = np.clip(c + (r.random(self.dim) < 0.15) * r.normal(0, 0.12, self.dim), 0, 1)
                nxt.append(c)
                nage.append(max(self.age[a], self.age[b]) + 1)
        self.P = np.array(nxt[:self.pop])
        self.age = np.array(nage[:self.pop])
        if self.g % self.gap == 0:
            # newcomers: the youngest layer starts over from random
            self.P[:self.n] = r.random((self.n, self.dim))
            self.age[:self.n] = 0


class Novelty(Opt):
    """Novelty search (Lehman and Stanley): selection rewards behaving differently (the mean distance to the
    nearest behaviours seen so far), not being closer to the goal, which escapes deceptive traps."""

    def __init__(self, dim, pop, rng, k=10):
        self.ga = GA(dim, pop, rng, sigma=0.15, p_mut=0.2)
        self.archive = np.zeros((0, 2))
        self.k, self.r = k, rng

    def ask(self):
        return self.ga.ask()

    def snapshot(self):
        return self.archive.astype(np.float16).copy()

    def tell(self, G, out):
        from .trials.base import Outcome
        b = out.behaviour[:, :2]
        ref = np.concatenate([self.archive, b]) if len(self.archive) else b
        d = np.sqrt(((b[:, None, :] - ref[None, :, :]) ** 2).sum(-1))
        d.sort(1)
        nov = d[:, 1:self.k + 1].mean(1)
        add = self.r.random(len(b)) < 0.15
        self.archive = np.concatenate([self.archive, b[add]])[-400:]
        self.last = b.copy()
        # a small pull toward the goal once novelty has spread the population
        score = nov + 0.05 * out.fitness
        self.ga.tell(G, Outcome(score, out.success, out.t_end, out.cause))


class MuLambdaES(Opt):
    """(mu, lambda) evolution strategy with a self-adapting step size per individual (Beyer and Schwefel)."""

    def __init__(self, dim, pop, rng, mu=None):
        self.n, self.lam, self.r = dim, pop, rng
        self.mu = mu or max(2, pop // 5)
        self.P = rng.random((pop, dim))
        self.s = np.full(pop, 0.15)

    def ask(self):
        return self.P.copy()

    def tell(self, G, out):
        par = np.argsort(-out.fitness)[:self.mu]
        tau = 1 / math.sqrt(2 * self.n)
        idx = par[self.r.integers(self.mu, size=self.lam)]
        s = self.s[idx] * np.exp(tau * self.r.standard_normal(self.lam))
        self.s = np.clip(s, 0.01, 0.4)
        self.P = np.clip(G[idx] + self.s[:, None] * self.r.standard_normal((self.lam, self.n)), 0, 1)
        self.P[0] = G[par[0]]


# ====================================================================================== one chapter
PATIENCE = 1.4            # generations a run gets before it is a dead end, as a multiple of the trial's g_max
STEP_UP = 0.04            # how much harder the world gets after a success
TOO_FAST = 0.04           # how much harder a world that was solved too fast becomes (before anything is shown)
EASE = 0.15               # how much the world eases after a dead end (half as much again after two in a row)


def evaluate(trial, env, wins, G):
    return concat([trial.rollout(env, w, G) for w in wins])


def _spread(lo: int, hi: int, k: int) -> list[int]:
    """k generation indices from lo to hi inclusive, as evenly spread as possible (repeats when too few)."""
    if k <= 0:
        return []
    if k == 1:
        return [hi]
    return [int(round(lo + (hi - lo) * i / (k - 1))) for i in range(k)]


def run_chapter(trial, mu, ch, seed: int, log=None) -> dict:
    """Evolve the chapter's trial as a series of runs that fill its rounds. Deterministic in (music, chapter,
    seed); see the module's docstring for the story it tells."""
    t_start = time.time()
    slots = ch.rounds
    level = float(np.clip(trial.level(ch.feats), 0.0, 1.0))
    hist = {"run": [], "gen": [], "level": [], "best": [], "mean": [], "nsucc": [], "pop": [], "snap": []}
    pops: list = []
    runs: list[dict] = []
    rounds: list = [None] * len(slots)
    cur = 0
    opt = None
    dead_in_row = 0
    run_no = 0
    gen = 0
    solved_any = False
    rng_pick = np.random.default_rng([seed, ch.seed, 4])
    last = None
    while cur < len(slots):
        remaining = len(slots) - cur
        J = min(4, remaining - 1)                       # ancestors shown before the success
        exam = slots[cur + J]
        rescue = not solved_any and remaining <= 5      # the last chance for this trial's first success
        if rescue:
            level = 0.0
        warm = opt is not None
        tries = 0
        while True:
            env = trial.env(mu, ch, np.random.default_rng([seed, ch.seed, 2]), level)
            win = trial.window(env, mu, exam.t0, exam.t1)
            if warm:
                o = copy.deepcopy(opt)
            else:
                o = trial.optimizer(env, np.random.default_rng([seed, ch.seed, 3, run_no, tries]))
                if last is not None and hasattr(trial, "carry_over"):
                    trial.carry_over(last, o)       # e.g. self-play keeps its hall of fame across a reset
            th = {k: [] for k in hist}
            tp = []
            found = None
            g_lim = int(trial.g_max * PATIENCE * (2 if rescue else 1))
            for g in range(1, g_lim + 1):
                # genomes are kept as float32, so they are evaluated exactly as they are stored and replayed
                G = np.asarray(o.ask(), np.float32).astype(np.float64)
                out = trial.rollout(env, win, G)
                o.tell(G, out)
                th["run"].append(run_no)
                th["gen"].append(gen + g)
                th["level"].append(level)
                th["best"].append(float(out.fitness.max()))
                th["mean"].append(float(out.fitness.mean()))
                th["nsucc"].append(int(out.success.sum()))
                th["pop"].append(len(G))
                th["snap"].append(o.snapshot() if hasattr(o, "snapshot") else None)
                tp.append((G.astype(np.float32), out.fitness.astype(np.float32), out.success.copy()))
                if out.success.any():
                    found = g - 1
                    break
            if found is not None and found + 1 < max(4, trial.g_min // 2) and level < 1.0 and tries < 5 and not rescue:
                # solved within a handful of generations: the world was too easy, so make it harder first
                level = min(1.0, level + TOO_FAST)
                tries += 1
                continue
            break
        h0 = len(pops)
        for k in hist:
            hist[k] += th[k]
        pops += tp
        gen += len(tp)
        if found is not None:
            hf = h0 + found
            anc = _spread(h0, max(h0, hf - 1), J) if found > 0 else [hf] * J
            for slot, hh in zip(range(cur, cur + J), anc):
                rounds[slot] = _show(trial, mu, ch, slots[slot], hh, hist, pops, rng_pick, seed, "ancestor", run_no)
            rounds[cur + J] = _show(trial, mu, ch, exam, hf, hist, pops, rng_pick, seed, "success", run_no)
            runs.append({"kind": "success", "run": run_no, "h0": h0, "h1": hf, "level": level, "warm": warm,
                         "slots": list(range(cur, cur + J + 1)), "tries": tries})
            if log:
                log(f"  trial {ch.k + 1:2d} {trial.key:9s} run {run_no + 1}: solved in {found + 1} "
                    f"{trial.unit.lower()}s at level {level:.2f}")
            cur += J + 1
            solved_any = True
            dead_in_row = 0
            opt = o
            level = min(1.0, level + STEP_UP)
        else:
            # a dead end is shown like a journey, and its last round is the exam it never passed
            K = J + 1
            h1 = len(pops) - 1
            picks = _spread(h0, h1, K)
            for i, (slot, hh) in enumerate(zip(range(cur, cur + K), picks)):
                rounds[slot] = _show(trial, mu, ch, slots[slot], hh, hist, pops, rng_pick, seed,
                                     "dead end" if i == K - 1 else "stuck", run_no)
            runs.append({"kind": "dead end", "run": run_no, "h0": h0, "h1": h1, "level": level, "warm": warm,
                         "slots": list(range(cur, cur + K)), "tries": tries})
            if log:
                log(f"  trial {ch.k + 1:2d} {trial.key:9s} run {run_no + 1}: dead end at level {level:.2f} "
                    f"(best fitness {max(th['best']):.2f})")
            cur += K
            opt = None
            last = o
            dead_in_row += 1
            level = max(0.0, level - EASE * (1.5 if dead_in_row >= 2 else 1.0))
        run_no += 1
    snaps = hist.pop("snap")
    pop_sizes = np.array(hist["pop"])
    nfail = np.array([p - s for p, s in zip(hist["pop"], hist["nsucc"])])
    if log:
        n_ok = sum(1 for r in runs if r["kind"] == "success")
        log(f"  trial {ch.k + 1:2d} {trial.key:9s} {n_ok} solved, {len(runs) - n_ok} dead ends, "
            f"{len(pops)} {trial.unit.lower()}s in {time.time() - t_start:.0f}s")
    return {"trial": trial.key, "version": VERSION, "hist": {k: np.array(v) for k, v in hist.items()}, "snaps": snaps,
            "runs": runs, "rounds": rounds, "solved": solved_any,
            "attempts": np.cumsum(pop_sizes), "fails": np.cumsum(nfail), "seconds": round(time.time() - t_start, 1)}


def _show(trial, mu, ch, slot, hh, hist, pops, rng, seed, role, run_no) -> dict:
    """The best individual of generation hh (or, for a success, the best that succeeded), replayed in the
    slot's own music with a few siblings as ghosts."""
    G, fx, ok = pops[hh]
    if role == "success" and ok.any():
        idx = np.nonzero(ok)[0]
        gi = int(idx[np.argmax(fx[idx])])
    else:
        gi = int(np.argmax(fx))
    env = trial.env(mu, ch, np.random.default_rng([seed, ch.seed, 2]), float(hist["level"][hh]))
    win = trial.window(env, mu, slot.t0, slot.t1)
    others = [j for j in range(len(G)) if j != gi]
    k = min(trial.ghosts, len(others))
    gh = list(rng.choice(others, k, replace=False)) if k else []
    B = G[[gi] + gh].astype(np.float64)
    o = trial.rollout(env, win, B)
    return {"k": slot.k, "hist": int(hh), "run": int(run_no), "gen": int(hist["gen"][hh]), "level": float(hist["level"][hh]),
            "role": role, "G": B.astype(np.float32), "fitness": o.fitness.astype(np.float32), "success": o.success.copy(),
            "t_end": o.t_end.astype(np.float32), "cause": o.cause.astype(np.int16), "note": trial.describe(env, B[0])}


# ====================================================================================== cache
_CODE = None


def code_hash() -> str:
    """A fingerprint of the evolution's code, so cached runs are redone whenever it changes."""
    global _CODE
    if _CODE is None:
        root = Path(__file__).parent
        h = hashlib.sha256()
        for p in sorted([*root.glob("trials/*.py"), root / "evolve.py", root / "plan.py", root / "music.py"]):
            h.update(p.read_bytes())
        _CODE = h.hexdigest()[:12]
    return _CODE


def cache_key(audio_hash: str, cfg: dict, ch, seed: int) -> str:
    from .trials import TRIALS
    s = json.dumps([VERSION, code_hash(), audio_hash, seed, ch.trial, round(ch.t0, 3), round(ch.t1, 3),
                    [(round(r.t0, 3), round(r.t1, 3)) for r in ch.rounds], TRIALS[ch.trial].version,
                    cfg.get("evolution", {})], sort_keys=True, default=str)
    return hashlib.sha256(s.encode()).hexdigest()[:20]


def load_or_run(cache_dir: Path, audio_hash: str, cfg: dict, mu, ch, seed: int, log=None) -> dict:
    from .trials import TRIALS
    p = Path(cache_dir) / f"crucible-{cache_key(audio_hash, cfg, ch, seed)}.pkl.gz"
    if p.exists():
        with gzip.open(p, "rb") as f:
            return pickle.load(f)
    res = run_chapter(TRIALS[ch.trial], mu, ch, seed, log)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(p.name + f".tmp{os.getpid()}")
    with gzip.open(tmp, "wb", compresslevel=3) as f:
        pickle.dump(res, f, protocol=5)
    tmp.rename(p)
    return res
