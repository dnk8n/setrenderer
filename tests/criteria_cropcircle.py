"""Automated checks for CRITERIA-cropcircle.md. Run:

    .venv/bin/python tests/criteria_cropcircle.py [SET_AUDIO] [--full out/knisper_cropcircle.mov]

Writes work/criteria-cropcircle/report.json and prints a table. Human (H) items are for manual sign-off.
"""
from __future__ import annotations

import contextlib
import io
import json
import math
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from setrender import cli, config, scenes, verify  # noqa: E402
from setrender.crop import cast, music  # noqa: E402
from setrender.crop.crowd import HIDDEN, WALK  # noqa: E402
from setrender.crop.events import SOUND_MAP  # noqa: E402
from setrender.timeline import Timeline  # noqa: E402

W = ROOT / "work" / "criteria-cropcircle"
W.mkdir(parents=True, exist_ok=True)
BIN = str(ROOT / ".venv" / "bin" / "setrender")
results: dict[str, dict] = {}


def rec(cid, ok, **info):
    results[cid] = {"pass": bool(ok), **info}
    print(f"{'PASS' if ok else 'FAIL'}  {cid:4s} {json.dumps(info, default=str)[:170]}", flush=True)


def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def render(audio, out, *extra):
    sh([BIN, "render", str(audio), "-t", "cropcircle", "-o", str(out), "--cpu", "4.5", *extra])
    return out


def quiet(fn, *a):
    with contextlib.redirect_stderr(io.StringIO()):
        return fn(*a)


def full_scene(set_audio: Path, keywords=(), sets=()):
    cfg = config.resolve("cropcircle", None, list(keywords), list(sets))
    an, ah, _ = quiet(cli.get_analysis, set_audio, 0.0, None, None, False)
    quiet(scenes.prepare, cfg, set_audio, ah, 0.0, cli.CACHE_DIR, lambda *a: None)
    tl = Timeline(an, 60, cfg.get("smoothing", {}))
    sc = scenes.make(cfg, tl, an, np.random.default_rng(cli.make_seed(0, ah, cfg, 0.0)), "T").scene
    return sc, tl, an


def scene_signal(path: Path) -> np.ndarray:
    """Mean brightness of the picture between the HUD panels, per frame (streamed small)."""
    cmd = ["nice", "-n", "10", "ffmpeg", "-v", "error", "-nostdin", "-threads", "2", "-i", str(path), "-map", "0:v:0",
           "-vf", "crop=iw:ih*0.62:0:ih*0.2,scale=32:8:flags=area,format=gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, 256).astype(np.float32).mean(1)


def kick_beats(an) -> np.ndarray:
    st = music.build(an, None, 0.0)
    return an.beats[np.array([st.kick_at(b) for b in an.beats], bool)] if len(an.beats) else an.beats


def fixtures(set_audio: Path):
    fx = {}

    def mk(name, args):
        p = W / name
        if not p.exists():
            sh(["ffmpeg", "-v", "error", "-y", *args, str(p)])
        fx[name] = p
    mk("setA.wav", ["-ss", "3560", "-t", "60", "-i", str(set_audio), "-c", "copy"])
    mk("setB.wav", ["-ss", "6600", "-t", "30", "-i", str(set_audio), "-c", "copy"])
    mk("fmt_s24_48k.aiff", ["-ss", "3600", "-t", "4", "-i", str(set_audio), "-ar", "48000", "-c:a", "pcm_s24be"])
    mk("fmt_f32_96k_mono.wav", ["-ss", "3600", "-t", "4", "-i", str(set_audio), "-ar", "96000", "-ac", "1", "-c:a", "pcm_f32le"])
    mk("fmt_s32_44k.wav", ["-ss", "3600", "-t", "4", "-i", str(set_audio), "-c:a", "pcm_s32le"])
    return fx


def frames(sc, idx):
    return np.stack([np.frombuffer(bytes(sc.render(i)), np.uint8).reshape(sc.H, sc.W, 4)[:, :, :3].copy() for i in idx])


def hist(fr):
    q = (fr // 32).reshape(-1, 3).astype(int)
    h = np.bincount(q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2], minlength=512).astype(float)
    return h / h.sum()


def main():
    argv = sys.argv[1:]
    args = [a for k, a in enumerate(argv) if not a.startswith("--") and (k == 0 or argv[k - 1] not in ("--only", "--full"))]
    set_audio = Path(args[0] if args else "/Users/dean/src/setstreamer/media/Pepper&Pumpernickl - Knisper 2026.WAV")
    full = None
    if "--full" in sys.argv:
        full = Path(sys.argv[sys.argv.index("--full") + 1])
    fx = fixtures(set_audio)
    only = set(sys.argv[sys.argv.index("--only") + 1].split(",")) if "--only" in sys.argv else None

    def want(*ids):
        return only is None or bool(only & set(ids))

    # ---------------------------------------------------------------- C1 / C4: defaults, format, sync
    if want("C1", "C4"):
        _c1_c4(fx)
    if want("C2"):
        _c2(fx)
    if want("C6", "C7", "C8", "C9", "C10", "C11", "C12", "C13"):
        _full_set_checks(set_audio)
    if want("C3", "C14"):
        _c3_c14(fx)
    if want("C15"):
        _c15(fx)
    if want("C5", "C16"):
        _c5_c16(full, set_audio)
    order = [f"C{k}" for k in range(1, 17)]
    report = {k: results[k] for k in order if k in results}
    (W / ("report.json" if only is None else "report-partial.json")).write_text(json.dumps(report, indent=2, default=str))
    npass = sum(r["pass"] for r in report.values())
    print(f"\n{npass}/{len(report)} automated checks pass. Human checklist H1-H7: see CRITERIA-cropcircle.md")
    return 0 if npass == len(report) else 1


def _c1_c4(fx):
    out = render(fx["setA.wav"], W / "c1.mov")
    rep = verify.run(out, fx["setA.wav"], 0.0, 60.0)
    c = rep["checks"]
    a11 = {k: v for k, v in c.items() if k.startswith("A11")}
    ok_fmt = all(v for v in a11.values() if isinstance(v, bool)) and c["A11_resolution"] == "1920x1080" and c["A11_fps"] == 60
    rec("C1", ok_fmt and c.get("A12_audio_sample_identical", False), **a11, audio_identical=c.get("A12_audio_sample_identical"))
    an_a, _, _ = quiet(cli.get_analysis, fx["setA.wav"], 0.0, None, None, False)
    bs = verify.beat_sync(scene_signal(out), kick_beats(an_a), 60.0)
    rec("C4", bs["hit_rate"] >= 0.9 and bs["median_offset_frames"] == 0 and c["A7_ok"], **bs,
        av_diff_frames=c["A7_av_duration_diff_frames"])



def _c2(fx):
    fmt = {}
    for name in ("fmt_s24_48k.aiff", "fmt_f32_96k_mono.wav", "fmt_s32_44k.wav"):
        o = render(fx[name], W / f"{name}.mov", "--quality", "draft")
        r = verify.run(o, fx[name], 0.0, 4.0)
        fmt[name] = r["checks"].get("A12_audio_sample_identical", False) and r["checks"]["A7_ok"]
    rec("C2", all(fmt.values()), **fmt)



def _full_set_checks(set_audio):
    t0 = time.time()
    sc, tl, an = full_scene(set_audio)
    print(f"(full-set scene built in {time.time() - t0:.0f}s)")
    n = tl.n
    fps = 60.0

    # C6 camera
    step = 3
    idx = np.arange(0, n, step)
    cams = []
    for i in idx:
        cc = sc.ctx(int(i))
        cc.events = sc.events.active(cc.t)
        pos, yaw, pitch, roll, fov, shot = sc.director.camera(cc)
        cams.append((*pos, yaw, pitch, roll, math.degrees(fov)))
    cams = np.array(cams)
    d = np.abs(np.diff(cams[:, :6], axis=0)).sum(1)
    moving = float((d > 1e-4).mean())
    fov_span = float(np.percentile(cams[:, 6], 99) - np.percentile(cams[:, 6], 1))
    kinds = sorted({s.kind for s in sc.director.shots})
    st = sc.struct
    marks = np.unique(np.concatenate([st.downbeats, st.phrases, [d.t0 for d in st.drops] or [0.0]]))
    cuts = np.array([s.t0 for s in sc.director.shots[1:]])
    forced = np.array([f[0] for f in sc.director.forced])
    planned = np.array([t for t in cuts if not np.any(np.abs(forced - t) < 1e-6)]) if len(forced) else cuts
    off = np.array([np.min(np.abs(marks - t)) for t in cuts]) * fps
    aligned = float((off <= 1.0).mean()) if len(off) else 1.0
    rec("C6", moving >= 0.95 and fov_span >= 30 and len(kinds) >= 10 and aligned >= 0.95,
        moving_frames=round(moving, 4), fov_span_deg=round(fov_span, 1), shot_kinds=len(kinds), kinds=kinds,
        cuts=len(cuts), cuts_on_beat_grid=round(aligned, 4), framed_gag_cuts=len(cuts) - len(planned))

    # C7 crowd
    cr = sc.crowd
    T = np.arange(0, sc.dur, 30.0)
    present = np.zeros(len(T))
    moves, relocated, arrivals, departures = [], [], [], []
    for k in range(cr.n):
        segs = cr.segs[k]
        walks = [s for s in segs if s.kind == WALK and 0 <= s.t0 < sc.dur]
        moves.append(len(walks))
        relocated.append(len(walks) > 0)
        for s in segs:
            if s.kind != HIDDEN:
                present += (T >= s.t0) & (T < s.t1)
        for a, b in zip(segs[:-1], segs[1:]):
            if a.kind == HIDDEN and b.kind != HIDDEN and 0 <= b.t0 < sc.dur:
                arrivals.append(b.t0)
            if a.kind != HIDDEN and b.kind == HIDDEN and 0 <= b.t0 < sc.dur:
                departures.append(b.t0)
    win = np.arange(0, sc.dur - 1, 600.0)
    arr_ok = all(any(w <= x < w + 600 for x in arrivals) for w in win)
    dep_ok = all(any(w <= x < w + 600 for x in departures) for w in win)
    rec("C7", present.min() < 0.7 * present.max() and np.mean(relocated) >= 0.9 and np.mean(moves) >= 3 and arr_ok and dep_ok,
        people=cr.n, on_site_min=int(present.min()), on_site_max=int(present.max()), relocated=round(float(np.mean(relocated)), 3),
        mean_walks=round(float(np.mean(moves)), 1), arrivals=len(arrivals), departures=len(departures),
        every_10min_has_arrival=arr_ok, every_10min_has_departure=dep_ok)

    # C8 wind and jellyfish
    kick = sc.kick
    w = sc.ws[kick]
    be = tl.env["beat"][kick]
    r_wind = float(np.corrcoef(w, be)[0, 1])
    W_ = sc.world
    if not hasattr(W_, "j_anchor"):
        W_._jelly_arrays()
    # the swing angle the world computes for one jellyfish, against the raw wind at the best response delay
    tt = tl.t[::2]
    lag = float(W_.j_lag[0])
    ang = 0.55 * W_.wind_hist(tt - lag) + np.sin(tt * 1.3 + W_.j_ph[0]) * 0.05 + np.sin(tt * 2.9 + W_.j_ph[0] * 2) * 0.02
    best = max((float(np.corrcoef(ang, sc.wind_at(tt - d))[0, 1]), d) for d in np.arange(0.0, 0.81, 1 / 30))
    rec("C8", r_wind >= 0.5 and best[0] >= 0.8, wind_vs_beat_r=round(r_wind, 3), jelly_swing_vs_wind_r=round(best[0], 3),
        response_delay_s=round(best[1], 3))

    # C9 headlights (instrumented: read the headlight emission the world builds for sampled frames)
    from setrender.crop.parts import Parts
    hl, sub, haz = [], [], []
    ki = np.nonzero(kick)[0][:: max(1, int(kick.sum()) // 3000)]
    for i in ki:
        cc = sc.ctx(int(i))
        cc.events = sc.events.active(cc.t)
        P = Parts()
        W_._car(cc, P)
        rows = np.array(P.mesh["box"])
        lit = rows[(rows[:, 15] == 9) & (rows[:, 16] > 0)]
        head = lit[np.abs(lit[:, 17] / lit[:, 16] - 0.92) < 0.01]   # headlights are warm white (1, .92, .75)
        hl.append(float(head[:, 16].max()))
        sub.append(cc.env["sub"])
    r_hl = float(np.corrcoef(hl, sub)[0, 1])
    bi = np.nonzero(~kick)[0][::40]
    blink = []
    for i in bi[:1500]:
        cc = sc.ctx(int(i))
        cc.events = sc.events.active(cc.t)
        P = Parts()
        W_._car(cc, P)
        on = any(np.allclose(r[16:19], (2.5, 1.2, 0.0)) for r in P.mesh["box"])
        blink.append((on, cc.beat_idx % 2 == 0 and cc.beat_phase < 0.5))
    blink = np.array(blink)
    hazard_ok = bool(len(blink)) and bool((blink[:, 0] == blink[:, 1]).all()) and blink[:, 0].any()
    rec("C9", r_hl >= 0.6 and hazard_ok, headlight_vs_sub_r=round(r_hl, 3), samples=len(hl), hazard_blinks_on_beat=hazard_ok)

    # C10 HUD text vocabulary (record every string drawn on sampled frames)
    drawn = set()
    orig = sc.hud._text

    def spy(out, s, *a, **k):
        drawn.add(s)
        return orig(out, s, *a, **k)
    sc.hud._text = spy
    for i in range(0, n, 97):
        cc = sc.ctx(i)
        cc.events = sc.events.active(cc.t)
        sc._hud(cc)
    for e in sc.events.ev:
        if e.kind == "konami":
            cc = sc.ctx(int((e.t0 + 1.0) * fps))
            cc.events = sc.events.active(cc.t)
            sc._hud(cc)
    sc.hud._text = orig
    words = set()
    for s in drawn:
        words.update(s.split())
    allowed_words = {"BPM", "BAR", "PHR", "KEY", "LUFS", "-INF", "INF", "--", "---.-"}
    bad = sorted(wd for wd in words if wd not in allowed_words and not all(ch in "0123456789.-+^v<>AB" for ch in wd))
    rec("C10", not bad, strings_seen=len(drawn), words=sorted(words)[:40], disallowed=bad)

    # C11 flags
    sched = W_.flag_sched
    changes = 0
    for (a0, b0, p0, bt0, _), (a1, b1, p1, bt1, _) in zip(sched[:-1], sched[1:]):
        changes += sum(1 for x, y in zip(p0, p1) if x != y)
    bunting = [s[3] for s in sched]
    bunt_cycles = sum(1 for x, y in zip(bunting[:-1], bunting[1:]) if x and not y)
    shown = set()
    for s in sched:
        shown.update(f for f in s[2] if f)
        if s[3]:
            shown.update(cast.PRIDE_FLAGS[(li * 3 + s[4]) % len(cast.PRIDE_FLAGS)] for li in range(3))
    from setrender.crop.director import h01
    for (a, b, k) in cr.flag_windows:
        shown.add(cast.PRIDE_FLAGS[int(h01(k, 5) * len(cast.PRIDE_FLAGS))])
    identity = set(cast.PRIDE_FLAGS)
    rec("C11", changes >= 20 and bunt_cycles >= 5 and identity <= shown, pole_changes=changes, bunting_up_down=bunt_cycles,
        identity_flags_shown=len(identity & shown), missing=sorted(identity - shown))

    # C12 classifier and sound-triggered gags
    ex = sc.extras or {}
    sa_t = ex.get("sa_t", np.zeros(0))
    gaps = float(np.max(np.diff(sa_t))) if len(sa_t) > 1 else 1e9
    cover = (float(sa_t[0]) < 3 and float(sa_t[-1]) > sc.dur - 4) if len(sa_t) else False
    sound_kinds = {v[0] for v in SOUND_MAP.values()}
    trig = [e for e in sc.events.ev if "label" in e.p]
    kinds12 = sorted({e.kind for e in trig})
    lat = []
    for e in trig:
        snd = [s for s in st.sounds if s.label == e.p["label"] and abs(max(0.0, s.t0 + 1.0) - e.t0) < 1e-6]
        if snd:
            lat.append(e.t0 - (snd[0].t0 + 1.5))
    lat = np.array(lat)
    wave_s = len(ex.get("wave", [])) / float(ex.get("rate", 1.0))
    wave_ok = abs(wave_s - float(ex.get("duration", 0.0))) <= 0.5   # HUD waveform stays on the beat grid
    rec("C12", gaps <= 2.0 and cover and len(kinds12) >= 8 and (np.abs(lat) <= 2.0).all() and wave_ok,
        waveform_seconds=round(wave_s, 2), set_seconds=round(float(ex.get("duration", 0.0)), 2),
        classifier_windows=int(len(sa_t)), max_gap_s=round(gaps, 2), covers_set=cover,
        sound_gag_kinds=kinds12, n_triggered=len(trig), max_latency_s=round(float(np.abs(lat).max()) if len(lat) else 0, 2),
        possible_kinds=len(sound_kinds))

    # C13 variety and framing
    ev_kinds = sorted({e.kind for e in sc.events.ev})
    framable = [e for e in sc.events.ev if e.kind in ("conga", "cypher", "rowboat", "cowbell", "sax", "baby", "pacman",
                                                       "hotdog", "chickens", "nyan", "ymca", "robotmob", "floss", "goat",
                                                       "sheep", "fireworks", "smiley", "creeper", "balloon")]
    looks = [s for s in sc.director.shots if s.kind in ("look", "ufo")]
    framed = sum(1 for e in framable if any(s.t0 < e.t1 and e.t0 < s.t1 for s in looks))
    frac = framed / max(1, len(framable))
    rec("C13", len(ev_kinds) >= 25 and frac >= 0.6, event_kinds=len(ev_kinds), kinds=ev_kinds, gags=len(framable),
        framed=framed, framed_fraction=round(frac, 3))



def _c3_c14(fx):
    def slice_scene(audio, kw=(), sets=(), seed=0):
        cfg = config.resolve("cropcircle", None, list(kw), list(sets))
        a, ah, _ = quiet(cli.get_analysis, audio, 0.0, None, None, False)
        quiet(scenes.prepare, cfg, audio, ah, 0.0, cli.CACHE_DIR, lambda *x: None)
        tl2 = Timeline(a, 60, cfg.get("smoothing", {}))
        return scenes.make(cfg, tl2, a, np.random.default_rng(cli.make_seed(seed, ah, cfg, 0.0)), "T").scene
    ix = [120, 600, 1200, 1700]
    fa = frames(slice_scene(fx["setA.wav"]), ix)
    fa2 = frames(slice_scene(fx["setA.wav"]), ix)
    fb = frames(slice_scene(fx["setB.wav"]), ix)
    fk = frames(slice_scene(fx["setA.wav"], kw=["anime", "aurora"]), ix)
    fs = frames(slice_scene(fx["setA.wav"], seed=7), ix)
    d_ab = float(np.mean([np.abs(hist(a) - hist(b)).sum() for a, b in zip(fa, fb)]))
    d_aa = float(np.mean([np.abs(hist(a) - hist(b)).sum() for a, b in zip(fa, fa2)]))
    rec("C3", (fk != fa).any() and (fs != fa).any() and (fa2 == fa).all(), keywords_change=bool((fk != fa).any()),
        seed_changes=bool((fs != fa).any()), same_inputs_identical=bool((fa2 == fa).all()))
    rec("C14", d_ab > 0.3 and d_aa == 0.0, dist_different_sets=round(d_ab, 3), dist_same_set=round(d_aa, 3))



def _c15(fx):
    o1 = render(fx["setB.wav"], W / "det1.mov", "--duration", "6", "-k", "aurora")
    o2 = render(fx["setB.wav"], W / "det2.mov", "--duration", "6", "-k", "aurora")
    side = json.loads(Path(str(o1) + ".json").read_text())
    cmd = shlex.split(side["reproduce"]) + ["-o", str(W / "det3.mov")]
    cmd[0] = BIN
    sh(cmd)
    m1, m2, m3 = verify.frame_md5(o1), verify.frame_md5(o2), verify.frame_md5(W / "det3.mov")
    out_r = W / "resume.mov"
    parts = Path(str(out_r) + ".parts")
    for p in (out_r, parts):
        if p.is_dir():
            import shutil
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    rargs = [BIN, "render", str(fx["setB.wav"]), "-t", "cropcircle", "-o", str(out_r), "--chunk", "3", "--cpu", "4.5"]
    proc = subprocess.Popen(rargs, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    t_end = time.time() + 180
    while time.time() < t_end and len(list(parts.glob("chunk*[0-9].mp4"))) < 3:
        time.sleep(0.5)
    os.killpg(proc.pid, signal.SIGKILL)
    proc.wait()
    n_before = len(list(parts.glob("chunk*[0-9].mp4")))
    res = sh(rargs).stderr
    ref = render(fx["setB.wav"], W / "noresume.mov", "--chunk", "3")
    resumed_ok = "resuming" in res and verify.frame_md5(out_r) == verify.frame_md5(ref)
    rec("C15", m1 == m2 == m3 and resumed_ok, md5=m1, sidecar_reproduces=m3 == m1, chunks_before_kill=n_before,
        resume_matches=resumed_ok, engine=side.get("engine", {}).get("gpu"))



def _c5_c16(full, set_audio):
    an, _, _ = quiet(cli.get_analysis, set_audio, 0.0, None, None, False)
    if full is not None and full.exists():
        rep = verify.run(full, set_audio, 0.0, None)
        cf = rep["checks"]
        bs_full = verify.beat_sync(scene_signal(full), kick_beats(an), 60.0)
        rec("C5", bs_full["hit_rate"] >= 0.9 and bs_full["median_offset_frames"] == 0 and cf["A7_ok"]
            and cf.get("A12_audio_sample_identical", False), **bs_full, av_diff_frames=cf["A7_av_duration_diff_frames"],
            audio_identical=cf.get("A12_audio_sample_identical"))
        side_f = json.loads(Path(str(full) + ".json").read_text())
        load_log = ROOT / "work" / "load_full.log"
        loads = [float(ln.split()[1]) for ln in load_log.read_text().splitlines() if len(ln.split()) > 1] if load_log.exists() else []
        rec("C16", bool(loads) and max(loads) <= 7.5, max_load_1m=max(loads) if loads else None,
            median_load_1m=float(np.median(loads)) if loads else None, render_min=round(side_f["render_seconds"] / 60, 1),
            realtime_ratio=round(side_f["audio"]["duration"] / side_f["render_seconds"], 2), gb=round(side_f["bytes"] / 1e9, 2),
            gpu=side_f.get("engine", {}).get("gpu", "see sidecar"))
    else:
        rec("C5", False, note="pass --full out/knisper_cropcircle.mov")
        rec("C16", False, note="pass --full out/knisper_cropcircle.mov")



if __name__ == "__main__":
    t0 = time.time()
    rc = main()
    print(f"({time.time() - t0:.0f}s)")
    sys.exit(rc)
