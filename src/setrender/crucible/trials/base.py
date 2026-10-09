"""What every trial provides: its world built from the music, a window's music-driven events, an optimiser,
a vectorised rollout of many genomes at once (recorded for drawing), and how to draw it."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

SIM_HZ = 60.0                 # every trial records its state at the video's frame rate


@dataclass
class Outcome:
    fitness: np.ndarray            # (n,) progress toward the goal: 1 or more means the goal was met
    success: np.ndarray            # (n,) bool
    t_end: np.ndarray              # (n,) when the attempt ended (success, failure, or the window's end)
    cause: np.ndarray              # (n,) int: index into the trial's causes (0 = out of time) or -1 for success
    behaviour: np.ndarray | None = None      # (n, k) descriptors (novelty search, MAP-Elites)
    extra: dict = field(default_factory=dict)
    states: dict | None = None     # recorded per step when asked (arrays (steps + 1, n, ...))


def concat(outs: list[Outcome]) -> Outcome:
    """Several windows' outcomes for the same genomes: success means every window, fitness the mean."""
    if len(outs) == 1:
        return outs[0]
    fit = np.mean([o.fitness for o in outs], 0)
    ok = np.all([o.success for o in outs], 0)
    t_end = np.max([o.t_end for o in outs], 0)
    cause = outs[0].cause.copy()
    for o in outs[1:]:
        cause = np.where(cause < 0, o.cause, cause)
    beh = outs[0].behaviour
    extra = {}
    for o in outs:
        for k, v in o.extra.items():
            if isinstance(v, list):
                extra.setdefault(k, []).extend(v)
            else:
                extra.setdefault(k, []).append(v)
    return Outcome(fit, ok, t_end, cause, beh, extra)


class Trial:
    key = ""
    name = ""
    algo = ""                      # the optimiser's name as the overlay shows it
    unit = "GENERATION"            # what one step of the optimiser is called
    unit_scale = 1                 # attempts per step shown in the counter (episodes per batch for the learners)
    style = "flat"                 # flat (2D), lab (3D), pixel, grid
    dims = "2D"
    physics = ""                   # one line for the overlay
    goal = ""
    round_bars = 8
    pop = 32
    ghosts = 7
    g_max = 80
    g_min = 12
    max_resets = 3
    affinity: dict = {}
    causes = ["OUT OF TIME"]
    accent = (1.0, 0.6, 0.2)
    version = 1

    # ---- the world
    def level(self, feats: dict) -> float:
        """Starting difficulty from the music (0 easy .. 1 hard)."""
        return 0.6

    def env(self, mu, ch, rng: np.random.Generator, level: float) -> dict:
        raise NotImplementedError

    def window(self, env: dict, mu, t0: float, t1: float) -> dict:
        return {"T": t1 - t0, "t0": t0}

    # ---- evolution
    dim = 8

    def optimizer(self, env: dict, rng: np.random.Generator):
        from ..evolve import GA
        return GA(self.dim, self.pop, rng)

    def rollout(self, env: dict, win: dict, G: np.ndarray, record: bool = False) -> Outcome:
        raise NotImplementedError

    def describe(self, env: dict, g: np.ndarray) -> str:
        """A short note on an individual for the overlay (its strategy, its body)."""
        return ""

    # ---- drawing
    def draw(self, sc, fr, env: dict, win: dict, rec: Outcome, k: float, ctx: dict):
        raise NotImplementedError

    def draw_reveal(self, sc, fr, env: dict, win: dict, rec: Outcome, k: float, ctx: dict):
        self.draw(sc, fr, env, win, rec, k, ctx)
