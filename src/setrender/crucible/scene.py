"""crucible: twenty trials, evolved live from the set. Each stretch of the music poses a trial (a race over its
waveform, rocks falling on its kicks, a game whose obstacles follow its hats...) and a population of creatures
evolves to beat it while you watch, under a different optimiser each time: genetic algorithms, CMA-ES, MAP-Elites,
NEAT, Q-learning, ant colonies, particle swarms, novelty search, self-play. About nine attempts in ten fail on
screen before the solution clicks, often on a drop.

The evolution runs once per render, at render time (so a new render of the same set is a new run, unless its
run number is given), and is cached so a stopped render resumes the same run. Frames are pure functions of
their index, the plan and those results: each round's attempt is replayed exactly from its genomes."""
from __future__ import annotations

import hashlib
import math
import os
from collections import OrderedDict
from pathlib import Path

import numpy as np

from .. import analysis
from ..crop import music as cmusic
from ..timeline import _attack_release
from . import draw as D
from . import evolve, font, hud, meshes
from . import plan as planner
from .engine import Engine, Frame, Layer
from .music import Music
from .trials import TRIALS
from .trials.base import SIM_HZ


def _load(cfg: dict):
    clip = cfg["_clip"]
    full = analysis.load(Path(clip["analysis"]))
    ex = None
    if clip.get("extras") and Path(clip["extras"]).exists():
        z = np.load(clip["extras"], allow_pickle=True)
        ex = {k: z[k] for k in z.files}
    st = cmusic.build(full, ex, 0.0)
    return full, st, ex


def run_number(cfg: dict) -> int:
    r = (cfg.get("evolution", {}) or {}).get("run", 0)
    try:
        return int(r)
    except (TypeError, ValueError):
        return 0


def evo_seed(base: int, cfg: dict) -> int:
    s = hashlib.sha256(f"{base}:{run_number(cfg)}".encode()).hexdigest()
    return int(s[:12], 16)


def running_order(cfg: dict, rng):
    full, st, ex = _load(cfg)
    mu = Music(full, st, ex)
    seed = evo_seed(int(rng.integers(1 << 30)), cfg)
    return mu, seed, planner.plan(mu, cfg, seed)


def highlight_hints(cfg: dict, title: str, rng):
    """Moments worth a reel clip: each solution (the first of each trial weighs most), the dead ends and the
    reveals, from the run's own results. Returns (hints [(t, weight, label)], intro end, outro start)."""
    mu, seed, P = running_order(cfg, rng)
    clip = cfg["_clip"]
    hints = []
    for ch in P.chapters:
        name = TRIALS[ch.trial].key
        res = evolve.load_or_run(Path(clip["cache_dir"]), clip["audio_hash"], cfg, mu, ch, seed)
        first = True
        for rd, rr in zip(ch.rounds, res["rounds"]):
            if rr["role"] == "success" and rr["success"][0]:
                t_hit = rd.t0 + float(rr["t_end"][0])
                hints.append((max(rd.t0, t_hit - 2 * mu.beat), 1.1 if first else 0.6, f"{name} solved"))
                first = False
            elif rr["role"] == "dead end":
                hints.append((rd.t0 + mu.bar, 0.3, f"{name} dead end"))
        hints.append((ch.reveal[0] + mu.bar, 0.45, f"{name} revealed"))
    return hints, P.intro[1], P.outro[0] + 2 * mu.bar


def prepare_all(cfg: dict, log, cpu: float = 6.0):
    """Evolve every chapter before frames are drawn (one process per chapter, within the CPU budget)."""
    import multiprocessing as mp
    import time
    from ..cli import make_seed
    clip = cfg["_clip"]
    rng = np.random.default_rng(make_seed(int(cfg.get("_user_seed", 0)), clip["audio_hash"], cfg, 0.0))
    mu, seed, P = running_order(cfg, rng)
    # a slice needs only the trials it shows (the hall of champions at the end needs them all)
    a, b = cfg.get("_span") or (0.0, 1e12)
    need = [ch for ch in P.chapters if ch.t0 < b and ch.t1 > a] if b < P.outro[0] else list(P.chapters)
    todo = []
    for ch in need:
        p = Path(clip["cache_dir"]) / f"crucible-{evolve.cache_key(clip['audio_hash'], cfg, ch, seed)}.pkl.gz"
        if not p.exists():
            todo.append(ch.k)
    log(f"crucible: run {run_number(cfg)}, {len(P.chapters)} trials, {sum(len(c.rounds) for c in P.chapters)} rounds; "
        f"{len(todo)} to evolve")
    if not todo:
        return {"run": run_number(cfg), "trials": [c.trial for c in P.chapters]}
    t0 = time.time()
    jobs = max(1, min(len(todo), int(cpu) - 1, 6))
    sub = {k: v for k, v in cfg.items()}
    if jobs == 1:
        for k in todo:
            _evolve_one((sub, seed, k))
    else:
        ctx = mp.get_context("spawn")
        with ctx.Pool(jobs) as pool:
            for msg in pool.imap_unordered(_evolve_one, [(sub, seed, k) for k in todo]):
                log(f"{msg}  load {os.getloadavg()[0]:.1f}")
    log(f"crucible: evolution done in {time.time() - t0:.0f}s ({jobs} processes)")
    return {"run": run_number(cfg), "trials": [c.trial for c in P.chapters]}


def _evolve_one(job):
    cfg, seed, k = job
    full, st, ex = _load(cfg)
    mu = Music(full, st, ex)
    P = planner.plan(mu, cfg, seed)
    ch = P.chapters[k]
    lines = []
    res = evolve.load_or_run(Path(cfg["_clip"]["cache_dir"]), cfg["_clip"]["audio_hash"], cfg, mu, ch, seed, lines.append)
    return (lines[-1] if lines else f"  trial {k + 1}") + f" [{res['seconds']:.0f}s]"


class CrucibleScene:
    pix_fmt = "nv12"

    def __init__(self, cfg: dict, tl, an_slice, rng, title: str, fingerprint: dict):
        clip = cfg["_clip"]
        self.cfg = cfg
        self.fps = float(tl.fps)
        self.start = float(clip["start"])
        self.title = title
        self.mu, self.seed, self.P = running_order(cfg, rng)
        self.full = full = self.mu.an
        self.audio_hash = clip.get("audio_hash", "")
        self.cache_dir = Path(clip.get("cache_dir", "."))
        pu = cfg.get("pulse", {}) or {}
        self.pump = float(pu.get("exposure", 0.07))
        self.vignette = float((cfg.get("lens", {}) or {}).get("vignette", 0.25))
        self.bloom = float(cfg.get("bloom", 0.35))
        self.sat = float((cfg.get("colour", {}) or {}).get("saturation", 1.0))
        n = int(math.ceil(full.duration * self.fps)) + 2
        tt = (np.arange(n) + 0.5) / self.fps
        sm = cfg.get("smoothing", {}) or {}
        self.env = {}
        for k in ("sub", "bass", "lowmid", "highmid", "high"):
            a, rel = sm.get(k, [0.01, 0.15])
            self.env[k] = _attack_release(full.at(full.bands.get(k, full.loudness), tt).astype(np.float64),
                                          self.fps, a, rel).astype(np.float32)
        a, rel = sm.get("loudness", [0.2, 0.8])
        self.env["loud"] = _attack_release(full.at(full.loudness, tt).astype(np.float64), self.fps, a, rel).astype(np.float32)
        self.beats = self.mu.beats if len(self.mu.beats) else np.array([1e9])
        st = self.mu.st
        self.kick_beat = np.array([st.kick_at(b) for b in self.beats], bool) if len(full.beats) else np.zeros(1, bool)
        self.layers = (1.0, 1.0, 1.0, 1.0, 1.0)
        self.debug = 0
        self.size = (int(clip.get("width", 1920)), int(clip.get("height", 1080)))
        img, _, _ = font.atlas()
        self.engine = Engine(*self.size, img, meshes.library())
        self.results: dict[int, dict] = {}
        self.envs: dict[tuple, dict] = {}
        self.replays: OrderedDict = OrderedDict()
        self.t = 0.0

    # ------------------------------------------------------------------ evolution results and replays
    def result(self, ch) -> dict:
        if ch.k not in self.results:
            self.results[ch.k] = evolve.load_or_run(self.cache_dir, self.audio_hash, self.cfg, self.mu, ch, self.seed)
        return self.results[ch.k]

    def env_for(self, ch, level: float) -> dict:
        key = (ch.k, round(level, 6))
        if key not in self.envs:
            self.envs[key] = TRIALS[ch.trial].env(self.mu, ch, np.random.default_rng([self.seed, ch.seed, 2]), level)
        return self.envs[key]

    def replay(self, ch, rd):
        """The round's recorded attempt (rd None: the reveal, with nobody in the world yet)."""
        key = (ch.k, -1 if rd is None else rd.k)
        if key in self.replays:
            self.replays.move_to_end(key)
            return self.replays[key]
        tr = TRIALS[ch.trial]
        res = self.result(ch)
        if rd is None:
            env = self.env_for(ch, float(res["hist"]["level"][0]))
            win = tr.window(env, self.mu, ch.reveal[0], ch.reveal[1])
            rec = tr.rollout(env, win, np.zeros((0, tr.dim)), record=True)
            rr = None
        else:
            rr = res["rounds"][rd.k]
            env = self.env_for(ch, rr["level"])
            win = tr.window(env, self.mu, rd.t0, rd.t1)
            rec = tr.rollout(env, win, rr["G"].astype(np.float64), record=True)
        self.replays[key] = (env, win, rec, rr)
        while len(self.replays) > 3:
            self.replays.popitem(last=False)
        return self.replays[key]

    # ------------------------------------------------------------------ per-frame helpers for the trials
    def cam2d(self, fr, cx, cy, half_h, rot=0.0):
        self._u["camw"] = (cx, cy, half_h, rot)

    def campix(self, fr, cx, cy, half_h):
        self._u["camp"] = (cx, cy, half_h, 0.0)

    def backdrop(self, fr, top, bottom, horizon=0.6, sun=None, stars=0.0, mode=0, pixel=0, accent=None, accent_x=0.5):
        self._u["bg0"] = (mode, horizon, pixel, stars)
        self._u["bgt"] = (*top[:3], sun[2] if sun else 0.0)
        self._u["bgb"] = (*bottom[:3], 0.0)
        if sun:
            self._sun2d = (sun[0], sun[1])
        if accent is not None:
            self._u["acc"] = (*accent[:3], accent_x)

    def tone(self, display: bool):
        self._tone = 1.0 if display else 0.0

    def cam3d(self, fr, eye, target, fov=0.9, sun=(0.4, 0.8, 0.3), sky=(0.5, 0.6, 0.75), ground=(0.3, 0.28, 0.25),
              fog=0.01, sun_col=(1.0, 0.95, 0.85), sun_i=2.4, ambient=0.55, shadow_r=20.0, shadow_c=None):
        aspect = self.size[0] / self.size[1]
        V = D.look_at(eye, target)
        Pm = D.perspective(fov, aspect, 0.05, 400.0)
        sd = np.asarray(sun, float)
        sd = sd / np.linalg.norm(sd)
        self._u["vp"] = Pm @ V
        self._u["svp"] = D.sun_matrix(sd, target if shadow_c is None else shadow_c, shadow_r)
        self._u["sun"] = (*sd, sun_i)
        self._u["sunc"] = (*sun_col, ambient)
        self._u["sky"] = (*sky, fog)
        self._u["gnd"] = (*ground, 0.85)
        self._u["eye"] = (*eye, 0.0)
        fr.shadow = True

    # ------------------------------------------------------------------ music per frame
    def kick(self, t: float):
        b = self.beats
        k = int(np.searchsorted(b, t + 1.0 / self.fps - 1e-6, side="right") - 1)
        if k < 0:
            return 0.0, 9.0, k
        since = max(0.0, t - b[k])
        amp = 1.0 if self.kick_beat[min(k, len(self.kick_beat) - 1)] else 0.15
        return amp * math.exp(-since / 0.12), since, k

    def beat_phase(self, t: float) -> float:
        b = self.beats
        k = int(np.clip(np.searchsorted(b, t, side="right") - 1, 0, max(len(b) - 2, 0)))
        if len(b) < 2:
            return t / self.mu.beat
        return k + (t - b[k]) / max(b[k + 1] - b[k], 1e-6)

    # ------------------------------------------------------------------ frames
    def frame(self, i: int) -> bytes:
        return self.engine.render(self.build(self.start + i / self.fps), out="nv12")

    def frame_rgba(self, i: int) -> bytes:
        return self.engine.render(self.build(self.start + i / self.fps), out="rgba")

    def frame_at(self, t: float, out: str = "rgba") -> bytes:
        return self.engine.render(self.build(t), out=out)

    def build(self, t: float) -> Frame:
        self.t = t
        self._u = {"camw": (0, 0, 10, 0), "camp": (160, 90, 90, 0), "bg0": (0, 0.6, 0, 0.0),
                   "bgt": (0.06, 0.07, 0.10, 0), "bgb": (0.02, 0.02, 0.03, 0), "acc": (1.0, 0.5, 0.2, 0.5)}
        self._sun2d = (0.7, 0.3)
        self._tone = 1.0
        fr = Frame(uni=np.zeros(4))
        seg, ch, rd = planner.where(self.P, t)
        n = len(self.P.chapters)
        kick, since, kb = self.kick(t)
        hud_a = 1.0
        if seg == "intro":
            self._intro(fr, t)
        elif seg == "outro":
            self._outro(fr, t)
        else:
            tr = TRIALS[ch.trial]
            self._u["acc"] = (*tr.accent, 0.5)
            ctx = {"beat_phase": self.beat_phase(t), "show_dead": True, "kick": kick, "t": t}
            if seg == "reveal":
                env, win, rec, _ = self.replay(ch, None)
                k = (t - ch.reveal[0]) * SIM_HZ
                ctx["reveal"] = (t - ch.reveal[0]) / max(ch.reveal[1] - ch.reveal[0], 1e-3)
                tr.draw_reveal(self, fr, env, win, rec, k, ctx)
                hud.title_card(fr.hud, ch.k, n, tr, t - ch.reveal[0], ch.reveal[1] - ch.reveal[0])
            else:
                env, win, rec, rr = self.replay(ch, rd)
                k = (t - rd.t0) * SIM_HZ
                snaps = self.result(ch).get("snaps")
                if snaps:
                    ctx["snap"] = snaps[rr["hist"]]
                tr.draw(self, fr, env, win, rec, k, ctx)
                self._round_hud(fr, ch, rd, rr, tr, t, kick)
        fr.uni = self._uniforms(t, kick, hud_a)
        return fr

    def _round_hud(self, fr, ch, rd, rr, tr, t, kick):
        res = self.result(ch)
        L = fr.hud
        # a soft dark band behind the titles keeps them readable over bright skies
        L.add("poly", D.vgrad(0, 0, 1920, 230, (0, 0, 0, 0.42), (0, 0, 0, 0.0)))
        n = len(self.P.chapters)
        hud.header(L, ch.k, n, tr, 1.0, tr.accent)
        hist = res["hist"]
        hh = rr["hist"]
        runs = res["runs"]
        run = next((r for r in runs if rd.k in r["slots"]), runs[-1])
        marks = [(r["h0"], r["warm"]) for r in runs if r["h0"] > 0 and r["h0"] <= hh]
        role = rr["role"]
        unit = tr.unit.lower()
        if role == "success":
            line, warn = f"RUN {rr['run'] + 1} · THE SOLUTION", False
        elif role == "ancestor":
            pos = run["slots"].index(rd.k) if rd.k in run["slots"] else 0
            first = ["FIRST", "ON THE WAY", "ON THE WAY", "THE LAST BEFORE IT WORKED"]
            line, warn = f"RUN {rr['run'] + 1} · ANCESTOR {pos + 1}: {first[min(pos, 3)]}", False
            if len(run["slots"]) - 1 == pos + 1 and pos > 0:
                line = f"RUN {rr['run'] + 1} · ANCESTOR {pos + 1}: THE LAST BEFORE IT WORKED"
        elif role == "dead end":
            line, warn = f"RUN {rr['run'] + 1} · DEAD END: A FRESH POPULATION NEXT", True
        else:
            line, warn = f"RUN {rr['run'] + 1} · NO WAY THROUGH YET", True
        if run["warm"] and role != "dead end" and run["slots"] and rd.k == run["slots"][0]:
            line = f"RUN {rr['run'] + 1} · A HARDER WORLD"
        hud.algo_box(L, tr, rr["gen"], line, warn, 1.0, kick)
        hud.chart(L, hist, hh, tr.accent, resets=marks)
        local = t - rd.t0
        done = []
        for r in ch.rounds:
            if r.k < rd.k or (r.k == rd.k and local >= float(res["rounds"][r.k]["t_end"][0])):
                q = res["rounds"][r.k]
                done.append("S" if q["success"][0] else ("A" if q["role"] == "ancestor" else "D"))
        hud.tally(L, done, rd.k, len(ch.rounds), int(res["attempts"][hh]), int(res["fails"][hh]),
                  self.beat_phase(t))
        te = float(rr["t_end"][0])
        ok = bool(rr["success"][0])
        if local >= te:
            word = "SOLVED" if ok else tr.causes[max(0, int(rr["cause"][0]))]
            sub = f"{unit} {rr['gen'] * tr.unit_scale:,} · {te:.1f} s"
            if role == "dead end" and not ok:
                sub = f"dead end · {sub}"
            hud.stamp(L, word, sub, ok, local - te)
        hud.note(L, rr.get("note", ""), 0.9)
        if hasattr(tr, "hud_extra"):
            snaps = res.get("snaps")
            tr.hud_extra(self, L, rr, snaps[hh] if snaps else None, t - rd.t0)

    def _intro(self, fr, t):
        i0, i1 = self.P.intro
        x = (t - i0) / max(i1 - i0, 1e-3)
        self.backdrop(fr, (0.05, 0.06, 0.10), (0.02, 0.02, 0.04), horizon=0.75, stars=0.6)
        L = fr.hud
        a = hud._ease(x * 4)
        D.text(L, "CRUCIBLE", 960, 250, 150, (1, 1, 1, a), align=0.5, tracking=24)
        D.text(L, f"TWENTY TRIALS, EVOLVED LIVE FROM {self.title.upper()[:48]}", 960, 420, 30, (1, 1, 1, 0.75 * a),
               align=0.5, tracking=4)
        names = [TRIALS[c.trial].name for c in self.P.chapters]
        for j, nm in enumerate(names):
            r, c = divmod(j, 4)
            b = hud._ease((x - 0.15 - 0.03 * j) * 6)
            D.text(L, f"{j + 1:02d} {nm}", 300 + 340 * c, 520 + 46 * r, 24, (1, 1, 1, 0.8 * b), tracking=2)
        self._fade = 1.0 - hud._ease(x * 3)

    def _outro(self, fr, t):
        o0, o1 = self.P.outro
        x = (t - o0) / max(o1 - o0, 1e-3)
        self.backdrop(fr, (0.05, 0.06, 0.10), (0.02, 0.02, 0.04), horizon=0.75, stars=0.6)
        L = fr.hud
        a = hud._ease(x * 4)
        D.text(L, "HALL OF CHAMPIONS", 960, 120, 84, (1, 1, 1, a), align=0.5, tracking=10)
        tot_a = tot_f = wins = dead = 0
        for j, ch in enumerate(self.P.chapters):
            res = self.result(ch)
            tr = TRIALS[ch.trial]
            tot_a += int(res["attempts"][-1])
            tot_f += int(res["fails"][-1])
            nw = sum(1 for q in res["rounds"] if q["role"] == "success" and q["success"][0])
            wins += nw
            dead += sum(1 for r in res["runs"] if r["kind"] == "dead end")
            r, c = divmod(j, 2)
            b = hud._ease((x - 0.04 * j) * 5)
            D.text(L, f"{j + 1:02d} {tr.name}", 260 + 760 * c, 250 + 64 * r, 30, (1, 1, 1, 0.9 * b))
            label = f"solved {nw}x" if nw else "not solved"
            D.text(L, label, 860 + 760 * c, 250 + 64 * r, 26, (*tr.accent, 0.9 * b), align=1.0)
        D.text(L, f"{tot_a:,} ATTEMPTS · {wins} SOLUTIONS ON SCREEN · {dead} DEAD ENDS",
               960, 960, 30, (1, 1, 1, 0.8 * a), align=0.5, tracking=3)
        self._fade = hud._ease((x - 0.55) / 0.45)

    def _uniforms(self, t, kick, hud_a):
        fi = int(min(max(0, round(t * self.fps)), len(self.env["sub"]) - 1))
        e = {k: float(v[fi]) for k, v in self.env.items()}
        calm = planner.curve(self.P.calm, t)
        drift = planner.curve(self.P.drift, t)
        exposure = 1.0 + self.pump * kick * (1.0 - 0.5 * calm)
        lift = 2.5 * self.pump * kick * (1.0 - 0.5 * calm)
        fade = getattr(self, "_fade", 0.0)
        self._fade = 0.0
        g = self.layers
        if self.debug >= 10:
            exposure, lift = 1.0, 0.0
        u = dict(self._u)
        u.update(clk=(t, float(round(t * self.fps)), kick, self.beat_phase(t) % 1.0),
                 aud=(e["sub"], e["bass"], e["lowmid"], e["highmid"]), aud2=(e["high"], e["loud"], calm, drift),
                 post=(exposure, self.vignette, self.bloom, self._tone), post2=(self.sat, fade, lift, hud_a),
                 lay=g[:4], lay2=(g[4], float(self.debug), self._sun2d[0], self._sun2d[1]))
        return D.uniforms(self.size[0], self.size[1], **u)

    def isolate(self, layer: str | None):
        """Drive only one decor layer (floor, accent, drift, motes, sparkle) for the band checks."""
        names = ["floor", "accent", "drift", "motes", "sparkle"]
        if layer is None:
            self.debug, self.layers = 0, (1.0,) * 5
        else:
            g = [0.0] * 5
            g[names.index(layer)] = 1.0
            self.debug, self.layers = 10, tuple(g)
