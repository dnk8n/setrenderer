"""Automated checks for docs/criteria/CRITERIA-crucible.md. Run:

    .venv/bin/python tests/criteria_crucible.py [SET_AUDIO] [--full out/knisper_crucible.mov]
        [--reel "out/<set>.crucible_highlights.mp4"] [--only E6,E9] [--run N]

The full render's run number (from its sidecar) is used for every check on the whole set, so they look at the
same evolution the video shows. Writes work/criteria-crucible/report.json and prints a table. Human (H) items
are for manual sign-off.
"""
from __future__ import annotations

import contextlib
import io
import json
import math
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
for _v in ("OMP_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "OPENBLAS_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from setrender import cli, config, scenes, verify  # noqa: E402
from setrender.crop import music  # noqa: E402
from setrender.crucible import evolve, plan as xplan  # noqa: E402
from setrender.crucible.music import Music  # noqa: E402
from setrender.crucible.trials import TRIALS  # noqa: E402
from setrender.crucible.trials.base import SIM_HZ  # noqa: E402
from setrender.timeline import Timeline  # noqa: E402

W = ROOT / "work" / "criteria-crucible"
W.mkdir(parents=True, exist_ok=True)
if (ROOT / ".venv" / "bin" / "setrender").exists():
    BIN = [str(ROOT / ".venv" / "bin" / "setrender")]
else:
    BIN = [sys.executable, "-m", "setrender.cli"]
    os.environ["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + os.environ.get("PYTHONPATH", "")
SET = "/Users/dean/src/setstreamer/media/Pepper&Pumpernickl - Knisper 2026 (trimmed).WAV"
FPS = 60.0
RUN = 1                      # replaced by the full render's run number when there is one
results: dict[str, dict] = {}
# uniform floats (see crucible/shaders.py COMMON): aud = sub, bass, lowmid, highmid; aud2 = high, loud, calm, drift
U_SUB, U_BASS, U_LOWMID, U_HMID, U_HIGH, U_DRIFT = 8, 9, 10, 11, 12, 15


def rec(cid, ok, **info):
    results[cid] = {"pass": bool(ok), **info}
    print(f"{'PASS' if ok else 'FAIL'}  {cid:4s} {json.dumps(info, default=str)[:200]}", flush=True)


def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def render(audio, out, *extra):
    return sh([*BIN, "render", str(audio), "-t", "crucible", "-o", str(out), "--cpu", "4.5", *extra]), out


def quiet(fn, *a):
    with contextlib.redirect_stderr(io.StringIO()):
        return fn(*a)


def make_scene(audio: Path, start=0.0, keywords=(), sets=(), seed=0, title="T", run=None):
    sets = list(sets) + [f"evolution.run={RUN if run is None else run}"]
    cfg = config.resolve("crucible", None, list(keywords), sets)
    an, ah, _ = quiet(cli.get_analysis, audio, 0.0, None, None, False)
    cfg["_user_seed"] = seed
    quiet(scenes.prepare, cfg, audio, ah, start, cli.CACHE_DIR, lambda *a: None)
    cfg["_clip"].update(width=1920, height=1080)
    tl = Timeline(an, FPS, cfg.get("smoothing", {}))
    return scenes.make(cfg, tl, an, np.random.default_rng(cli.make_seed(seed, ah, cfg, 0.0)), title).scene


def kick_beats(an) -> np.ndarray:
    st = music.build(an, None, 0.0)
    return an.beats[np.array([st.kick_at(b) for b in an.beats], bool)] if len(an.beats) else an.beats


def picture_signal(path: Path) -> np.ndarray:
    cmd = ["nice", "-n", "10", "ffmpeg", "-v", "error", "-nostdin", "-hwaccel", "videotoolbox", "-i", str(path),
           "-map", "0:v:0", "-vf", "scale=32:18:flags=area,format=gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, 32 * 18).astype(np.float32).mean(1)


def fixtures(set_audio: Path):
    fx = {}

    def mk(name, args):
        p = W / name
        if not p.exists():
            sh(["ffmpeg", "-v", "error", "-y", *args, str(p)])
        fx[name] = p
    mk("setA.wav", ["-ss", "3560", "-t", "60", "-i", str(set_audio), "-c", "copy"])
    mk("setB.wav", ["-ss", "6600", "-t", "30", "-i", str(set_audio), "-c", "copy"])
    mk("half1.wav", ["-t", "3450", "-i", str(set_audio), "-c", "copy"])
    mk("half2.wav", ["-ss", "3450", "-i", str(set_audio), "-c", "copy"])
    mk("silence.wav", ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "12", "-c:a", "pcm_s16le"])
    mk("fmt_s24_48k.aiff", ["-ss", "3600", "-t", "4", "-i", str(set_audio), "-ar", "48000", "-c:a", "pcm_s24be"])
    mk("fmt_f32_96k_mono.wav", ["-ss", "3600", "-t", "4", "-i", str(set_audio), "-ar", "96000", "-ac", "1", "-c:a", "pcm_f32le"])
    mk("fmt_s32_44k.wav", ["-ss", "3600", "-t", "4", "-i", str(set_audio), "-c:a", "pcm_s32le"])
    return fx


def rgb(sc, t: float) -> np.ndarray:
    return np.frombuffer(sc.frame_at(t), np.uint8).reshape(1080, 1920, 4)[:, :, :3].copy()


def hist(fr):
    q = (fr // 32).reshape(-1, 3).astype(int)
    h = np.bincount(q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2], minlength=512).astype(float)
    return h / h.sum()


def spearman(a, b) -> float:
    ra = np.argsort(np.argsort(a))
    rb = np.argsort(np.argsort(b))
    if np.std(ra) == 0 or np.std(rb) == 0:
        return 0.0
    return float(np.corrcoef(ra, rb)[0, 1])


def main():
    global RUN
    argv = sys.argv[1:]
    opts = ("--only", "--full", "--reel", "--run")
    args = [a for k, a in enumerate(argv) if not a.startswith("--") and (k == 0 or argv[k - 1] not in opts)]
    set_audio = Path(args[0] if args else SET)
    full = Path(argv[argv.index("--full") + 1]) if "--full" in argv else None
    reel_path = Path(argv[argv.index("--reel") + 1]) if "--reel" in argv else \
        ROOT / "out" / f"{set_audio.stem}.crucible_highlights.mp4"
    only = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else None
    if full is not None and Path(str(full) + ".json").exists():
        RUN = int(json.loads(Path(str(full) + ".json").read_text())["template"]["evolution"]["run"])
    if "--run" in argv:
        RUN = int(argv[argv.index("--run") + 1])
    print(f"(checking evolution run {RUN})")

    def want(*ids_):
        return only is None or bool(only & set(ids_))
    fx = fixtures(set_audio)
    if want("E1", "E4"):
        _e1_e4(fx, set_audio)
    if want("E2"):
        _e2(fx)
    if want("E8"):
        _e8(fx)
    if want("E3", "E15"):
        _e3_e15(fx, set_audio)
    sc = None
    if want("E6", "E7", "E9", "E10", "E11", "E12", "E13", "E14"):
        t0 = time.time()
        sc = make_scene(set_audio, title=set_audio.stem)
        print(f"(full-set scene built in {time.time() - t0:.0f}s)", flush=True)
    if want("E6"):
        _e6(sc, fx)
    if want("E7"):
        _e7(sc)
    if want("E9", "E10", "E11", "E12", "E13"):
        res = _results(sc) if want("E9", "E10", "E11") else {}
        if want("E9"):
            _e9(sc, res)
        if want("E10"):
            _e10(sc, res)
        if want("E11"):
            _e11(sc, res)
        if want("E12"):
            _e12(sc)
        if want("E13"):
            _e13(sc)
    if want("E14"):
        _e14(sc, fx)
    if want("E16"):
        _e16(fx)
    if want("E5", "E17", "E18"):
        _full_checks(full, set_audio)
    if want("E19"):
        _e19(reel_path, set_audio)
    order = [f"E{k}" for k in range(1, 20)]
    report = {k: results[k] for k in order if k in results}
    (W / ("report.json" if only is None else "report-partial.json")).write_text(json.dumps(report, indent=2, default=str))
    npass = sum(r["pass"] for r in report.values())
    print(f"\n{npass}/{len(report)} automated checks pass. Human checklist H1-H7: see docs/criteria/CRITERIA-crucible.md")
    return 0 if npass == len(report) else 1


# ------------------------------------------------------------------ interface, output, sync
def _e1_e4(fx, set_audio):
    s0 = 3560.0
    _, out = render(set_audio, W / "e1.mov", "--start", str(s0), "--duration", "60", "--set", f"evolution.run={RUN}")
    rep = verify.run(out, set_audio, s0, 60.0)
    c = rep["checks"]
    a11 = {k: v for k, v in c.items() if k.startswith("A11")}
    ok_fmt = all(v for v in a11.values() if isinstance(v, bool)) and c["A11_resolution"] == "1920x1080" and c["A11_fps"] == 60
    rec("E1", ok_fmt and c.get("A12_audio_sample_identical", False), **a11,
        audio_identical=c.get("A12_audio_sample_identical"))
    an, _, _ = quiet(cli.get_analysis, set_audio, 0.0, None, None, False)
    kb = kick_beats(an)
    kb = kb[(kb >= s0) & (kb < s0 + 60.0)] - s0
    bs = verify.beat_sync(picture_signal(out), kb, FPS)
    rec("E4", bs["hit_rate"] >= 0.9 and bs["median_offset_frames"] <= 1 and c["A7_ok"], **bs,
        av_diff_frames=c["A7_av_duration_diff_frames"])


def _e2(fx):
    fmt = {}
    for name in ("fmt_s24_48k.aiff", "fmt_f32_96k_mono.wav", "fmt_s32_44k.wav"):
        _, o = render(fx[name], W / f"{name}.mov", "--quality", "draft")
        r = verify.run(o, fx[name], 0.0, 4.0)
        fmt[name] = r["checks"].get("A12_audio_sample_identical", False) and r["checks"]["A7_ok"]
    rec("E2", all(fmt.values()), **fmt)


def _e8(fx):
    """Fresh runs differ; the recorded run number replays one exactly; the evolution is logged first."""
    outs = []
    for k in range(2):
        p = W / f"fresh{k}.mov"
        for q in (p, Path(str(p) + ".parts")):
            if q.is_dir():
                shutil.rmtree(q)
        r, _ = render(fx["setA.wav"], p, "--duration", "20", "--restart")
        side = json.loads(Path(str(p) + ".json").read_text())
        outs.append((p, int(side["template"]["evolution"]["run"]), r.stderr))
    m0, m1 = verify.frame_md5(outs[0][0]), verify.frame_md5(outs[1][0])
    _, p2 = render(fx["setA.wav"], W / "replay.mov", "--duration", "20", "--set", f"evolution.run={outs[0][1]}", "--restart")
    m2 = verify.frame_md5(p2)
    log = outs[0][2]
    evo_first = ("crucible: run" in log and "evolution done" in log
                 and log.index("evolution done") < log.index("cpu budget"))
    rec("E8", m0 != m1 and m2 == m0 and outs[0][1] != outs[1][1] and evo_first, runs=[o[1] for o in outs],
        fresh_runs_differ=m0 != m1, replay_matches=m2 == m0, evolution_logged_before_frames=evo_first)


def _e3_e15(fx, set_audio):
    ts = [5.0, 11.7, 18.3, 25.0]
    a = make_scene(fx["setA.wav"])
    fa = np.stack([rgb(a, t) for t in ts])
    fa2 = np.stack([rgb(make_scene(fx["setA.wav"]), t) for t in ts])
    fb = np.stack([rgb(make_scene(fx["setB.wav"]), t) for t in ts])
    fk = np.stack([rgb(make_scene(fx["setA.wav"], keywords=["vivid"]), t) for t in ts])
    fs = np.stack([rgb(make_scene(fx["setA.wav"], seed=7), t) for t in ts])
    fset = np.stack([rgb(make_scene(fx["setA.wav"], sets=["lens.vignette=0.6"]), t) for t in ts])
    s_full = make_scene(set_audio, start=0.0, title=set_audio.stem)
    s0 = 600.0
    s_slice = make_scene(set_audio, start=s0, title=set_audio.stem)
    k0 = int(s0 * FPS)
    slice_ok = all(s_full.frame_rgba(k0 + i) == s_slice.frame_rgba(i) for i in (0, 37, 211))
    rec("E3", (fk != fa).any() and (fs != fa).any() and (fset != fa).any() and (fa2 == fa).all() and slice_ok,
        keywords_change=bool((fk != fa).any()), seed_changes=bool((fs != fa).any()), set_changes=bool((fset != fa).any()),
        same_inputs_identical=bool((fa2 == fa).all()), slice_matches_full=slice_ok)
    d_ab = float(np.mean([np.abs(hist(x) - hist(y)).sum() for x, y in zip(fa, fb)]))
    d_aa = float(np.mean([np.abs(hist(x) - hist(y)).sum() for x, y in zip(fa, fa2)]))
    rec("E15", d_ab > 0.3 and d_aa == 0.0, dist_different_sets=round(d_ab, 3), dist_same_set=round(d_aa, 3))


# ------------------------------------------------------------------ the twenty trials (E6, E7)
def _total_fit(feats, order):
    keys = sorted({k for t in TRIALS.values() for k in t.affinity})
    Z = {k: xplan._z(feats, k) for k in keys}
    return float(sum(sum(w * Z[k][c] for k, w in TRIALS[t].affinity.items()) for c, t in enumerate(order)))


def _e6(sc, fx):
    P, mu = sc.P, sc.mu
    trials = [c.trial for c in P.chapters]
    dur = [(c.t1 - c.t0) / 60 for c in P.chapters]
    db = mu.downbeats
    on_db = all(float(np.min(np.abs(db - c.t0))) * FPS <= 1.0 for c in P.chapters)
    feats = [c.feats for c in P.chapters]
    fit = _total_fit(feats, trials)
    r = np.random.default_rng(3)
    rand = [_total_fit(feats, list(r.permutation(trials))) for _ in range(2000)]
    pct = float(np.mean(np.array(rand) < fit))
    orders = []
    for name in ("half1.wav", "half2.wav"):
        s = make_scene(fx[name], title=name)
        orders.append([c.trial for c in s.P.chapters])
    differ = orders[0] != orders[1][:len(orders[0])]
    rec("E6", len(trials) == 20 and len(set(trials)) == 20 and min(dur) >= 2.5 and max(dur) <= 9.0 and on_db
        and pct >= 0.99 and differ, trials=len(trials), distinct=len(set(trials)), minutes=(round(min(dur), 2), round(max(dur), 2)),
        on_downbeats=on_db, fits_music_better_than_random_orders=round(pct, 4), halves_get_different_orders=differ,
        order=trials, half_orders=orders)


def _frame_close(t, events) -> bool:
    return len(events) > 0 and float(np.min(np.abs(np.asarray(events) - t))) * FPS <= 1.0


def _e7(sc):
    """Hazards land on their audio events; gaits beat with the beats; worlds made from the music follow it."""
    mu, P = sc.mu, sc.P
    checks, notes = {}, {}
    for ch in P.chapters:
        tr = TRIALS[ch.trial]
        res = sc.result(ch)
        rd = ch.rounds[len(ch.rounds) // 2]
        env = sc.env_for(ch, res["rounds"][rd.k]["level"])
        win = tr.window(env, mu, rd.t0, rd.t1)
        t0, t1 = rd.t0, rd.t1
        k = ch.trial
        if k == "boulders":
            haz = tr.hazards(env, win)
            kicks = mu.events("kick", t0, t1)
            acc = 2 * 22.0 / haz["fall"] ** 2
            # each rock's bottom reaches its landing height exactly when its kick plays
            land = []
            for tk, y in zip(haz["t"], haz["y"]):
                yy = y + 0.5 * acc * max(tk - tk, 0) ** 2
                land.append(_frame_close(tk, kicks) and abs(yy - y) < 1e-9)
            checks[k] = bool(len(land) and all(land))
            notes[k] = f"{len(land)} rocks on kicks"
        elif k == "flap":
            beats = mu.events("beat", t0, t1 + 4 * mu.beat)
            ok = all(_frame_close(tp, beats) for tp in win["pipes"])
            checks[k], notes[k] = ok and len(win["pipes"]) > 0, f"{len(win['pipes'])} pipes on beats"
        elif k == "crossing":
            ok, n = True, 0
            for ln, ev in zip(env["lanes"], win["cars"]):
                src = mu.events(ln["src"], t0 - 6.0, t1)
                ok &= all(_frame_close(e, src) for e in ev)
                n += len(ev)
            checks[k], notes[k] = ok and n > 0, f"{n} vehicles set off on their onsets"
        elif k == "flock":
            sn = np.concatenate([mu.events("snare", t0, t1), mu.events("kick", t0, t1)])
            checks[k] = bool(len(win["dives"])) and all(_frame_close(d, sn) for d in win["dives"])
            notes[k] = f"{len(win['dives'])} dives on snares"
        elif k == "lander":
            hats = mu.events("hat", t0, t1)
            checks[k] = all(_frame_close(g, hats) for g in win["gusts"])
            prof = mu.loud_profile(ch.t0, ch.t1, len(env["xs"]))
            m = ~((env["xs"] >= env["pad"][0]) & (env["xs"] <= env["pad"][1]))
            rr = float(np.corrcoef(prof[m], env["hs"][m])[0, 1])
            checks[k + " mountains"] = rr >= 0.8
            notes[k] = f"{len(win['gusts'])} gusts on hats, mountains follow loudness r={rr:.2f}"
        elif k == "commons":
            ev = np.concatenate([mu.events("bar", t0, t1), mu.events("drop", t0, t1)])
            checks[k] = len(win["inv"]) > 0 and all(_frame_close(e, ev) for e in win["inv"])
            notes[k] = f"{len(win['inv'])} invasions on bars and drops"
        elif k in ("sprint", "canyon", "boulders", "stairway", "courier", "swim", "sumo", "moonwalk", "summit"):
            from setrender.crucible.trials.soft import beat_phase
            bt = win["beats"] if "beats" in win else mu.events("beat", t0, t1)
            ph = beat_phase(bt, bt, win.get("period", mu.beat))
            checks[k + " gait"] = bool(np.allclose(ph, np.round(ph), atol=1e-6))
            notes[k + " gait"] = "muscles in phase with every beat"
            if k == "sprint":
                prof = mu.loud_profile(ch.t0, ch.t1, len(env["xs"]))
                m = env["xs"] > 8.0
                rr = float(np.corrcoef(prof[m], env["hs"][m])[0, 1])
                checks["sprint ground"] = rr >= 0.9
                notes["sprint ground"] = f"ground follows loudness r={rr:.2f}"
        if k == "swarm":
            prof = mu.profile(ch.t0, ch.t1, 16)
            from scipy import ndimage
            Fz = ndimage.zoom(prof, (env["F"].shape[0] / 5, env["F"].shape[1] / 16), order=1)[:env["F"].shape[0], :env["F"].shape[1]]
            rr = float(np.corrcoef(Fz.ravel(), env["F"].ravel())[0, 1])
            checks["swarm landscape"] = rr >= 0.2
            notes["swarm landscape"] = f"landscape contains the spectrum r={rr:.2f}"
    rec("E7", all(checks.values()) and len(checks) >= 12, checked=len(checks), failed=[k for k, v in checks.items() if not v],
        notes=notes)


# ------------------------------------------------------------------ the evolution (E9-E13)
def _results(sc):
    return {ch.k: sc.result(ch) for ch in sc.P.chapters}


def _e9(sc, res):
    """Re-simulate every round's attempt from its genome: it ends exactly as shown; every trial is solved."""
    mu = sc.mu
    bad, n, wins, unsolved = [], 0, 0, []
    for ch in sc.P.chapters:
        tr = TRIALS[ch.trial]
        r = res[ch.k]
        got = 0
        for rd, rr in zip(ch.rounds, r["rounds"]):
            env = sc.env_for(ch, rr["level"])
            win = tr.window(env, mu, rd.t0, rd.t1)
            o = tr.rollout(env, win, rr["G"][:1].astype(np.float64))
            n += 1
            if bool(o.success[0]) != bool(rr["success"][0]) or int(o.cause[0]) != int(rr["cause"][0]):
                bad.append((ch.trial, rd.k))
            if rr["role"] == "success":
                if not rr["success"][0]:
                    bad.append((ch.trial, rd.k, "success round without a success"))
                got += 1
        wins += got
        if not got:
            unsolved.append(ch.trial)
    rec("E9", not bad and not unsolved, attempts_resimulated=n, mismatches=bad[:10], unsolved=unsolved,
        successes_on_screen=wins)


def _e10(sc, res):
    journey = total = 0.0
    shapes_ok = True
    worst = None
    for ch in sc.P.chapters:
        r = res[ch.k]
        for run in r["runs"]:
            rr = [r["rounds"][k] for k in run["slots"]]
            hs = [x["hist"] for x in rr]
            dur = sum(ch.rounds[k].t1 - ch.rounds[k].t0 for k in run["slots"])
            total += dur
            if run["kind"] == "success":
                journey += dur
                roles = [x["role"] for x in rr]
                ok = roles[-1] == "success" and all(x == "ancestor" for x in roles[:-1]) and len(rr) <= 5
                ok &= hs == sorted(hs) and hs[0] == run["h0"] and (len(hs) < 2 or hs[-2] == max(run["h0"], run["h1"] - 1))
                ok &= hs[-1] == run["h1"]
            else:
                hs_ = [x["hist"] for x in rr]
                ok = hs_ == sorted(hs_) and hs_[0] == run["h0"] and hs_[-1] == run["h1"] and rr[-1]["role"] == "dead end"
            if not ok:
                shapes_ok = False
                worst = (ch.trial, run["run"], run["kind"])
    share = journey / max(total, 1e-9)
    rec("E10", shapes_ok and 0.7 <= share <= 0.9, journey_share=round(share, 3), dead_end_share=round(1 - share, 3),
        journeys_and_dead_ends_well_formed=shapes_ok, first_bad=worst)


def _e11(sc, res):
    wrong_best, back, early_dead, too_fast, not_harder, counts_ok = [], [], [], [], [], True
    for ch in sc.P.chapters:
        r = res[ch.k]
        tr = TRIALS[ch.trial]
        hist = r["hist"]
        gens = [x["gen"] for x in r["rounds"]]
        if any(b < a for a, b in zip(gens, gens[1:])):
            back.append(ch.trial)
        for x in r["rounds"]:
            if float(x["fitness"][0]) < -1e9:
                wrong_best.append(ch.trial)
        prev = None
        for run in r["runs"]:
            n_gen = run["h1"] - run["h0"] + 1
            if run["kind"] == "dead end" and n_gen < tr.g_max:
                early_dead.append((ch.trial, run["run"], n_gen))
            if run["kind"] == "success":
                last_chance = n_gen > tr.g_max or run["level"] == 0.0
                if n_gen < max(4, tr.g_min // 2) and run["level"] < 1.0 and not last_chance and run.get("tries", 0) < 5:
                    too_fast.append((ch.trial, run["run"], n_gen))
                if prev is not None and prev["kind"] == "success" and run["level"] <= prev["level"] and run["level"] < 1.0:
                    not_harder.append((ch.trial, run["run"]))
            prev = run
        a = np.asarray(r["attempts"])
        counts_ok &= bool(np.all(np.diff(a) > 0)) and int(a[-1]) == int(np.sum(hist["pop"]))
    rec("E11", not (wrong_best or back or early_dead or too_fast or not_harder) and counts_ok,
        generations_backward=back, early_dead_ends=early_dead, solved_too_fast=too_fast,
        not_harder_after_success=not_harder, overlay_counts_match=counts_ok)


def _e12(sc):
    algos = sorted({TRIALS[c.trial].algo for c in sc.P.chapters})
    text = " ".join(algos)
    fam = {"reinforcement learning": "Q-LEARNING" in text or "SARSA" in text,
           "genetic algorithms": "GENETIC" in text,
           "evolution strategies": "CMA-ES" in text or "EVOLUTION STRATEG" in text,
           "swarm intelligence": "ANT COLONY" in text and "PARTICLE SWARM" in text,
           "quality diversity / novelty": "MAP-ELITES" in text or "NOVELTY" in text,
           "neuroevolution": "NEAT" in text, "self-play / game theory": "SELF-PLAY" in text or "DILEMMA" in text}
    styles = sorted({TRIALS[c.trial].style for c in sc.P.chapters})
    gravities = {"earth (soft bodies)": 25.0, "moon": TRIALS["moonwalk"].gravity, "water (none)": 0.0}
    rec("E12", len(algos) >= 15 and all(fam.values()) and len(styles) >= 4 and len(set(gravities.values())) >= 3,
        optimisers=len(algos), families=fam, worlds=styles, gravities=gravities)


def _e13(sc):
    """The optimisers the trials build come from the reference libraries."""
    rng = np.random.default_rng(0)
    checks = {}
    for key, lib in (("canyon", "cma"), ("moonwalk", "cma"), ("stairway", "ribs"), ("flap", "neat")):
        tr = TRIALS[key]
        o = tr.optimizer({}, rng)
        inner = getattr(o, "es", None) or getattr(o, "sched", None) or getattr(o, "pop", None)
        checks[key] = type(inner).__module__.split(".")[0] == lib
    from setrender.crucible import evolve as ev
    import inspect
    checks["genetic algorithms (DEAP)"] = "from deap import tools" in inspect.getsource(ev.GA.tell)
    rec("E13", all(checks.values()), **checks)


# ------------------------------------------------------------------ decor follows the bands (E14)
def _e14(sc, fx):
    mu, P = sc.mu, sc.P
    # a minute without a breakdown, inside a 2D trial whose sky is visible
    flat = [c for c in P.chapters if TRIALS[c.trial].style == "flat" and TRIALS[c.trial].key not in ("swim", "sumo")]
    ch = flat[0] if flat else P.chapters[0]
    t0 = ch.rounds[2].t0
    for c in [ch] + flat[1:]:
        cand = c.rounds[2].t0
        if all(not (b.t0 < cand + 60 and b.t1 > cand) for b in mu.st.breakdowns):
            ch, t0 = c, cand
            break
    n = 600
    fi = (np.round((t0 + np.arange(n) / 10.0) * FPS)).astype(int)
    fr = sc.build(t0)
    base = fr.uni.copy()
    corr = {}

    def frames(layer, slot, values, step=6):
        sc.isolate(layer)
        try:
            f0 = sc.build(t0)
            u0 = f0.uni.copy()
            out = []
            for v in values:
                f0.uni = u0.copy()
                f0.uni[slot] = v
                a = np.frombuffer(sc.engine.render(f0, out="rgba"), np.uint8).reshape(1080, 1920, 4)[::step, ::step, :3]
                out.append(a.astype(np.float32).mean(-1))
        finally:
            sc.isolate(None)
        return np.stack(out)
    for layer, band, slot in (("floor", "sub", U_SUB), ("accent", "bass", U_BASS), ("motes", "highmid", U_HMID),
                              ("sparkle", "high", U_HIGH)):
        env = sc.env[band][fi]
        act = frames(layer, slot, env).mean((1, 2))
        corr[f"{band}->{layer}"] = round(float(np.corrcoef(act, env)[0, 1]), 3)
    # the low mids drive the motes' drift: motion between frames against the drift's rate
    dr = np.array([xplan.curve(P.drift, t0 + k / 10.0) for k in range(n)])
    f = frames("drift", U_DRIFT, dr, step=3)
    motion = np.convolve(np.abs(np.diff(f, axis=0)).mean((1, 2)), np.ones(5) / 5, mode="same")
    rate = np.diff(dr)
    corr["lowmid->drift"] = round(float(np.corrcoef(motion, rate)[0, 1]), 3)

    def motion_of(audio, start):
        s = make_scene(audio, title="T")
        ts = start + np.arange(240) / FPS
        fr_ = np.stack([np.frombuffer(s.frame_at(float(t)), np.uint8).reshape(1080, 1920, 4)[::8, ::8, :3]
                        .astype(np.float32) for t in ts])
        return float(np.abs(np.diff(fr_, axis=0)).mean())
    ms, mm = motion_of(fx["silence.wav"], 6.0), motion_of(fx["setA.wav"], 20.0)
    rec("E14", all(v >= 0.6 for v in corr.values()) and ms < 0.35 * mm, **corr, held_in=(ch.trial, round(t0, 1)),
        silence_motion=round(ms, 3), music_motion=round(mm, 3), silence_ratio=round(ms / max(mm, 1e-9), 3))


# ------------------------------------------------------------------ reproducible and resumable (E16)
def _e16(fx):
    _, o1 = render(fx["setB.wav"], W / "det1.mov", "--duration", "6", "-k", "vivid", "--restart")
    side = json.loads(Path(str(o1) + ".json").read_text())
    cmd = BIN + shlex.split(side["reproduce"])[1:] + ["-o", str(W / "det3.mov"), "--restart"]
    sh(cmd)
    m1, m3 = verify.frame_md5(o1), verify.frame_md5(W / "det3.mov")
    out_r = W / "resume.mov"
    parts = Path(str(out_r) + ".parts")
    for p in (out_r, parts):
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    rargs = [*BIN, "render", str(fx["setB.wav"]), "-t", "crucible", "-o", str(out_r), "--chunk", "3", "--cpu", "4.5"]
    proc = subprocess.Popen(rargs, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    t_end = time.time() + 300
    while time.time() < t_end and len(list(parts.glob("chunk*[0-9].mp4"))) < 3:
        time.sleep(0.5)
    os.killpg(proc.pid, signal.SIGKILL)
    proc.wait()
    n_before = len(list(parts.glob("chunk*[0-9].mp4")))
    run0 = json.loads((parts / "manifest.json").read_text())["cfg"]["evolution"]["run"]
    res = sh(rargs).stderr
    run1 = json.loads(Path(str(out_r) + ".json").read_text())["template"]["evolution"]["run"]
    _, ref = render(fx["setB.wav"], W / "noresume.mov", "--chunk", "3", "--set", f"evolution.run={run0}", "--restart")
    resumed_ok = "resuming" in res and run0 == run1 and verify.frame_md5(out_r) == verify.frame_md5(ref)
    rec("E16", m1 == m3 and resumed_ok, sidecar_reproduces=m3 == m1, chunks_before_kill=n_before, run=run0,
        resumed_same_run=run0 == run1, resume_matches=resumed_ok)


# ------------------------------------------------------------------ the full render (E5, E17, E18)
def _scan(path: Path, w=64, h=36):
    cmd = ["nice", "-n", "10", "ffmpeg", "-v", "error", "-nostdin", "-hwaccel", "videotoolbox", "-i", str(path),
           "-map", "0:v:0", "-vf", f"scale={w}:{h}:flags=area,format=rgb24", "-f", "rawvideo", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    n = w * h * 3
    wins = [(y0, x0) for y0 in (0, h // 4, h // 2) for x0 in (0, w // 4, w // 2)]
    gray, lum_w, red_w = [], [], []
    while True:
        b = proc.stdout.read(n * 1200)
        if not b:
            break
        f = np.frombuffer(b, np.uint8).reshape(-1, h, w, 3).astype(np.float32) / 255.0
        gray.append((f @ np.array([0.2126, 0.7152, 0.0722], np.float32)).mean((1, 2)))
        lin = np.where(f <= 0.04045, f / 12.92, ((f + 0.055) / 1.055) ** 2.4)
        lum = lin @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        red = ((lin[..., 0] / np.maximum(lin.sum(-1), 1e-6) >= 0.8) & (lin[..., 0] > 0.05)).astype(np.float32)
        lum_w.append(np.stack([lum[:, y0:y0 + h // 2, x0:x0 + w // 2].mean((1, 2)) for y0, x0 in wins], 1))
        red_w.append(np.stack([red[:, y0:y0 + h // 2, x0:x0 + w // 2].mean((1, 2)) for y0, x0 in wins], 1))
    proc.wait()
    return np.concatenate(gray) * 255.0, np.concatenate(lum_w), np.concatenate(red_w)


def _flashes(sig: np.ndarray, thr: float) -> np.ndarray:
    out = []
    direction = 0
    lo = hi = float(sig[0])
    for i, v in enumerate(sig.tolist()):
        if v > hi:
            hi = v
        if v < lo:
            lo = v
        if direction <= 0 and v - lo >= thr:
            direction, hi = 1, v
        elif direction >= 0 and hi - v >= thr:
            if direction == 1:
                out.append(i)
            direction, lo = -1, v
    return np.array(out, int)


def _per_second_max(ev: np.ndarray) -> int:
    if not len(ev):
        return 0
    return int((np.searchsorted(ev, ev + int(FPS)) - np.arange(len(ev))).max())


def _full_checks(full: Path | None, set_audio: Path):
    an, _, _ = quiet(cli.get_analysis, set_audio, 0.0, None, None, False)
    if full is None or not full.exists():
        for k in ("E5", "E17", "E18"):
            rec(k, False, note="pass --full out/knisper_crucible.mov")
        return
    print("(decoding the full render: a few tens of minutes)", flush=True)
    rep = verify.run(full, None)
    cf = rep["checks"]
    adur = float(verify._probe(full)["format"]["duration"])
    audio_ok = verify._audio_md5(set_audio, 0.0, adur) == verify._audio_md5(full)
    gray, lum_w, red_w = _scan(full)
    bs = verify.beat_sync(gray, kick_beats(an), FPS)
    rec("E5", bs["hit_rate"] >= 0.9 and bs["median_offset_frames"] <= 1 and cf["A7_ok"] and audio_ok, **bs,
        av_diff_frames=cf["A7_av_duration_diff_frames"], audio_identical=audio_ok, frames=len(gray))
    side = json.loads(Path(str(full) + ".json").read_text())
    log = ROOT / "work" / "full_render_crucible.log"
    txt = log.read_text() if log.exists() else ""
    loads = [float(x) for x in re.findall(r"load ([0-9.]+)", txt)]
    sampled = ROOT / "work" / "load_full_crucible.log"
    if sampled.exists():
        loads += [float(x) for x in re.findall(r"\{ ([0-9.]+)", sampled.read_text())]
    evo = re.findall(r"evolution done in ([0-9]+)s", txt)
    eng = side.get("engine", {})
    gpu = eng.get("gpu", {})
    rec("E17", bool(loads) and max(loads) <= 7.5 and isinstance(gpu, dict) and "Metal" in str(gpu.get("backend_type"))
        and bool(eng.get("evolution")), max_load_1m=max(loads) if loads else None,
        median_load_1m=float(np.median(loads)) if loads else None, samples_over_7=int(sum(x > 7 for x in loads)),
        samples=len(loads), evolution_s=int(evo[-1]) if evo else None, render_min=round(side["render_seconds"] / 60, 1),
        realtime_ratio=round(side["audio"]["duration"] / side["render_seconds"], 2), gb=round(side["bytes"] / 1e9, 2),
        gpu=gpu, run=side["template"]["evolution"]["run"], yuv_on_gpu=scenes.pix_fmt({"engine": "crucible"}) == "nv12")
    worst_gen = max(_per_second_max(_flashes(lum_w[:, k], 0.10)) for k in range(lum_w.shape[1]))
    worst_red = max(_per_second_max(_flashes(red_w[:, k], 0.25)) for k in range(red_w.shape[1]))
    n_gen = sum(len(_flashes(lum_w[:, k], 0.10)) for k in range(lum_w.shape[1]))
    n_red = sum(len(_flashes(red_w[:, k], 0.25)) for k in range(red_w.shape[1]))
    np.savez(W / "scan.npz", gray=gray, lum_w=lum_w, red_w=red_w)
    rec("E18", worst_gen <= 3 and worst_red <= 3, most_general_flashes_in_1s=worst_gen, general_flashes=n_gen,
        red_flashes=n_red, most_red_flashes_in_1s=worst_red, frames=len(lum_w))


# ------------------------------------------------------------------ the reel (E19)
def _e19(reel_path: Path, set_audio: Path):
    meta = Path(str(reel_path) + ".json")
    if not reel_path.exists() or not meta.exists():
        rec("E19", False, note=f"run setrender reel first ({reel_path})")
        return
    d = json.loads(meta.read_text())
    clips = d["clips"]
    an, _, _ = quiet(cli.get_analysis, set_audio, 0.0, None, None, False)
    sc = make_scene(set_audio, title=set_audio.stem)
    P = sc.P
    n = len(clips)
    durs = [c["dur"] for c in clips]
    total = sum(durs)
    on_beat = [float(np.min(np.abs(an.beats - c["t0"]))) * 60 <= 1.0 for c in clips]
    first_open = clips[0]["t0"] < P.intro[1]
    last_close = clips[-1]["t0"] + clips[-1]["dur"] > P.outro[0]
    centres = np.array([c["t0"] + c["dur"] / 2 for c in clips[1:-1]])
    gaps = np.diff(centres)
    even = bool(len(gaps) and np.all(np.abs(gaps - gaps.mean()) <= 0.5 * gaps.mean()))
    trials, wins = set(), 0
    for c in clips[1:-1]:
        seg, ch, rd = xplan.where(P, c["t0"] + c["dur"] / 2)
        if ch is not None:
            trials.add(ch.trial)
            if rd is not None:
                rr = sc.result(ch)["rounds"][rd.k]
                t_hit = rd.t0 + float(rr["t_end"][0])
                wins += bool(rr["role"] == "success" and rr["success"][0] and c["t0"] - 1.0 <= t_hit <= c["t0"] + c["dur"] + 1.0)
    sr = 48000

    def pcm(args):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", *args, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                             check=True, capture_output=True).stdout
        return np.frombuffer(raw, np.float32)
    rr_ = pcm(["-i", str(reel_path)])
    corr, off = [], 0.0
    mg = sr // 10
    for c in clips:
        a = rr_[int((off + 0.35) * sr): int((off + c["dur"] - 0.35) * sr)]
        b = pcm(["-ss", f"{c['t0'] + 0.35:.4f}", "-t", f"{c['dur'] - 0.7:.4f}", "-i", str(set_audio)])
        k = min(len(a), len(b)) - 2 * mg

        def r_at(dl):
            return float(np.corrcoef(a[mg + dl: mg + dl + k], b[mg: mg + k])[0, 1])
        if k > 100:
            coarse = max(range(-mg, mg + 1, 48), key=r_at)
            corr.append(max(r_at(dl) for dl in range(max(-mg, coarse - 48), min(mg, coarse + 48) + 1)))
        else:
            corr.append(0.0)
        off += c["dur"]
    rec("E19", 10 <= n <= 15 and all(2.0 <= x <= 3.0 for x in durs) and abs(total - 30) <= 2 and all(on_beat)
        and first_open and last_close and even and min(corr) >= 0.9 and len(trials) >= 8 and wins >= 3, clips=n,
        clip_s=round(float(np.mean(durs)), 2), total_s=round(total, 2), cuts_on_beats=all(on_beat),
        first_is_board=first_open, last_is_hall=last_close, evenly_spread=even, trials_shown=len(trials),
        successes_shown=wins, gap_s=[round(float(g)) for g in gaps], audio_match_min_r=round(min(corr), 3),
        moments=[c["why"] for c in clips])


if __name__ == "__main__":
    t0 = time.time()
    rc = main()
    print(f"({time.time() - t0:.0f}s)")
    sys.exit(rc)
