"""Automated checks for docs/criteria/CRITERIA-cymatics.md. Run:

    .venv/bin/python tests/criteria_cymatics.py [SET_AUDIO] [--full out/knisper_cymatics.mov]
        [--reel "out/<set>.cymatics_highlights.mp4"] [--only K6,K7]

Writes work/criteria-cymatics/report.json and prints a table. Human (H) items are for manual sign-off.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from setrender import cli, config, scenes, verify  # noqa: E402
from setrender.crop import music  # noqa: E402
from setrender.cymatics import plan as cpl  # noqa: E402
from setrender.timeline import Timeline  # noqa: E402

W = ROOT / "work" / "criteria-cymatics"
W.mkdir(parents=True, exist_ok=True)
if (ROOT / ".venv" / "bin" / "setrender").exists():
    BIN = [str(ROOT / ".venv" / "bin" / "setrender")]
else:
    BIN = [sys.executable, "-m", "setrender.cli"]
    os.environ["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + os.environ.get("PYTHONPATH", "")
SET = "/Users/dean/src/setstreamer/media/Pepper&Pumpernickl - Knisper 2026 (trimmed).WAV"
FPS = 60.0
results: dict[str, dict] = {}
# uniform slots (see cymatics/shaders.py COMMON): aud = kick, sub, bass, lowmid; aud2 = high mids, highs
U_SUB, U_BASS, U_LOWMID, U_HMID, U_HIGH = 9, 10, 11, 12, 13
U_SWEEP, U_AGE, U_PHASE, U_AZ = 51, 52, 55, 56


def rec(cid, ok, **info):
    results[cid] = {"pass": bool(ok), **info}
    print(f"{'PASS' if ok else 'FAIL'}  {cid:4s} {json.dumps(info, default=str)[:180]}", flush=True)


def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def render(audio, out, *extra):
    sh([*BIN, "render", str(audio), "-t", "cymatics", "-o", str(out), "--cpu", "4.5", *extra])
    return out


def quiet(fn, *a):
    with contextlib.redirect_stderr(io.StringIO()):
        return fn(*a)


def make_scene(audio: Path, start=0.0, keywords=(), sets=(), seed=0, title="T"):
    cfg = config.resolve("cymatics", None, list(keywords), list(sets))
    an, ah, _ = quiet(cli.get_analysis, audio, 0.0, None, None, False)
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
    mk("silence.wav", ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "12", "-c:a", "pcm_s16le"])
    mk("fmt_s24_48k.aiff", ["-ss", "3600", "-t", "4", "-i", str(set_audio), "-ar", "48000", "-c:a", "pcm_s24be"])
    mk("fmt_f32_96k_mono.wav", ["-ss", "3600", "-t", "4", "-i", str(set_audio), "-ar", "96000", "-ac", "1", "-c:a", "pcm_f32le"])
    mk("fmt_s32_44k.wav", ["-ss", "3600", "-t", "4", "-i", str(set_audio), "-c:a", "pcm_s32le"])
    return fx


def rgb(sc, t: float) -> np.ndarray:
    return np.frombuffer(sc.frame_at(t), np.uint8).reshape(1080, 1920, 4)[:, :, :3].copy()


def layer(sc, t: float, mode: int) -> np.ndarray:
    """The renderer's own debug layers: 1 = the experiment's field, 2 = what its mode predicts (R channel),
    the station in G, the circle of confusion in B."""
    sc.debug = mode
    try:
        return np.frombuffer(sc.frame_at(t), np.uint8).reshape(1080, 1920, 4).copy()
    finally:
        sc.debug = 0


def hist(fr):
    q = (fr // 32).reshape(-1, 3).astype(int)
    h = np.bincount(q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2], minlength=512).astype(float)
    return h / h.sum()


def station_starts(P) -> list:
    """The span that brings in each station (cut, rack focus or the intro), in order."""
    return [s for s in P.spans if s.look.station != cpl.VOID and (s.kind in (cpl.CUT, cpl.FOCUS) or s.why == "intro")]


def steady(P, t: float, settle: bool = True) -> bool:
    """t is inside a settled mode: no arrival, rack focus or overdrive under way, away from the start and end."""
    if t < P.intro[1] + 1 or t > P.outro[0] - 1:
        return False
    prev, cur, x, span = cpl.span_at(P, t)
    if cur.station == cpl.VOID or (settle and x < 1.0):
        return False
    if len(P.drops) and np.min(np.abs(np.array(P.drops) - t)) < 3.0:
        return False
    fs = [s.t0 for s in P.spans if s.kind == cpl.FOCUS]
    if fs and np.min(np.abs(np.array(fs) - t)) < 2.5:
        return False
    return True


def main():
    argv = sys.argv[1:]
    opts = ("--only", "--full", "--reel")
    args = [a for k, a in enumerate(argv) if not a.startswith("--") and (k == 0 or argv[k - 1] not in opts)]
    set_audio = Path(args[0] if args else SET)
    full = Path(argv[argv.index("--full") + 1]) if "--full" in argv else None
    reel_path = Path(argv[argv.index("--reel") + 1]) if "--reel" in argv else \
        ROOT / "out" / f"{set_audio.stem}.cymatics_highlights.mp4"
    only = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else None

    def want(*ids_):
        return only is None or bool(only & set(ids_))
    fx = fixtures(set_audio)
    if want("K1", "K4"):
        _k1_k4(fx, set_audio)
    if want("K2"):
        _k2(fx)
    if want("K3", "K12"):
        _k3_k12(fx, set_audio)
    sc = None
    if want("K6", "K7", "K8", "K9", "K10", "K11"):
        t0 = time.time()
        sc = make_scene(set_audio, title=set_audio.stem)
        print(f"(full-set scene built in {time.time() - t0:.0f}s)")
    if want("K6"):
        _k6(sc)
    if want("K7"):
        _k7(sc)
    if want("K8"):
        _k8(sc)
    if want("K9"):
        _k9(sc)
    if want("K10"):
        _k10(sc)
    if want("K11"):
        _k11(sc, fx)
    if want("K13"):
        _k13(fx)
    if want("K5", "K14", "K15"):
        _full_checks(full, set_audio)
    if want("K16"):
        _k16(reel_path, set_audio)
    order = [f"K{k}" for k in range(1, 17)]
    report = {k: results[k] for k in order if k in results}
    (W / ("report.json" if only is None else "report-partial.json")).write_text(json.dumps(report, indent=2, default=str))
    npass = sum(r["pass"] for r in report.values())
    print(f"\n{npass}/{len(report)} automated checks pass. Human checklist H1-H7: see docs/criteria/CRITERIA-cymatics.md")
    return 0 if npass == len(report) else 1


# ------------------------------------------------------------------ interface, output, sync
def _k1_k4(fx, set_audio):
    s0 = 3560.0
    out = render(set_audio, W / "k1.mov", "--start", str(s0), "--duration", "60")
    rep = verify.run(out, set_audio, s0, 60.0)
    c = rep["checks"]
    a11 = {k: v for k, v in c.items() if k.startswith("A11")}
    ok_fmt = all(v for v in a11.values() if isinstance(v, bool)) and c["A11_resolution"] == "1920x1080" and c["A11_fps"] == 60
    rec("K1", ok_fmt and c.get("A12_audio_sample_identical", False), **a11,
        audio_identical=c.get("A12_audio_sample_identical"))
    an, _, _ = quiet(cli.get_analysis, set_audio, 0.0, None, None, False)
    kb = kick_beats(an)
    kb = kb[(kb >= s0) & (kb < s0 + 60.0)] - s0
    bs = verify.beat_sync(picture_signal(out), kb, FPS)
    rec("K4", bs["hit_rate"] >= 0.9 and bs["median_offset_frames"] <= 1 and c["A7_ok"], **bs,
        av_diff_frames=c["A7_av_duration_diff_frames"])


def _k2(fx):
    fmt = {}
    for name in ("fmt_s24_48k.aiff", "fmt_f32_96k_mono.wav", "fmt_s32_44k.wav"):
        o = render(fx[name], W / f"{name}.mov", "--quality", "draft")
        r = verify.run(o, fx[name], 0.0, 4.0)
        fmt[name] = r["checks"].get("A12_audio_sample_identical", False) and r["checks"]["A7_ok"]
    rec("K2", all(fmt.values()), **fmt)


def _k3_k12(fx, set_audio):
    ts = [5.0, 11.7, 18.3, 25.0]                  # inside both test sets (60 s and 30 s)
    a = make_scene(fx["setA.wav"])
    fa = np.stack([rgb(a, t) for t in ts])
    fa2 = np.stack([rgb(make_scene(fx["setA.wav"]), t) for t in ts])
    fb = np.stack([rgb(make_scene(fx["setB.wav"]), t) for t in ts])
    fk = np.stack([rgb(make_scene(fx["setA.wav"], keywords=["dreamy"]), t) for t in ts])
    fs = np.stack([rgb(make_scene(fx["setA.wav"], seed=7), t) for t in ts])
    fset = np.stack([rgb(make_scene(fx["setA.wav"], sets=["camera.orbit=0.1"]), t) for t in ts])
    s_full = make_scene(set_audio, start=0.0, title=set_audio.stem)
    s0 = 600.0
    s_slice = make_scene(set_audio, start=s0, title=set_audio.stem)
    k0 = int(s0 * FPS)
    slice_ok = all(s_full.frame_rgba(k0 + i) == s_slice.frame_rgba(i) for i in (0, 37, 211))
    rec("K3", (fk != fa).any() and (fs != fa).any() and (fset != fa).any() and (fa2 == fa).all() and slice_ok,
        keywords_change=bool((fk != fa).any()), seed_changes=bool((fs != fa).any()), set_changes=bool((fset != fa).any()),
        same_inputs_identical=bool((fa2 == fa).all()), slice_matches_full=slice_ok)
    d_ab = float(np.mean([np.abs(hist(x) - hist(y)).sum() for x, y in zip(fa, fb)]))
    d_aa = float(np.mean([np.abs(hist(x) - hist(y)).sum() for x, y in zip(fa, fa2)]))
    rec("K12", d_ab > 0.3 and d_aa == 0.0, dist_different_sets=round(d_ab, 3), dist_same_set=round(d_aa, 3))


# ------------------------------------------------------------------ the six stations (K6)
def _k6(sc):
    P, st, an = sc.P, sc.st, sc.full
    db = st.downbeats
    bar = 4 * 60.0 / max(an.tempo, 60)
    min_bars = float(sc.cfg.get("min_bars", 16))

    def on_db(t):
        return float(np.min(np.abs(db - t))) * FPS <= 1.0
    seq = station_starts(P)
    names = [cpl.STATIONS[s.look.station] for s in seq]
    ends = [s.t0 for s in seq[1:]] + [P.outro[0]]
    lengths = [b - s.t0 for s, b in zip(seq, ends)]
    no_repeat = all(a != b for a, b in zip(names, names[1:]))
    long_enough = min(lengths[:-1]) >= min_bars * bar - 1.0 / FPS
    share = Counter()
    for s, ln in zip(seq, lengths):
        share[cpl.STATIONS[s.look.station]] += ln
    tot = sum(share.values())
    shares = {k: round(v / tot, 3) for k, v in sorted(share.items())}
    balanced = len(shares) == 6 and all(0.08 <= v <= 0.30 for v in shares.values())
    starts_db = all(on_db(s.t0) for s in seq[1:])
    # every section start changes the station, or (when it comes sooner than min_bars after the last change)
    # the mode; a change within 4 bars counts (sections are snapped to downbeats and merged with breakdowns)
    secs = [s for s in an.sections if P.intro[1] + 4 * bar <= s < P.outro[0] - 4 * bar]
    changes = [s.t0 for s in P.spans if s.look.station != cpl.VOID and s.t0 > P.intro[0]]
    sec_cov = [s for s in secs if not any(abs(c - s) <= 4 * bar + 1.0 / FPS for c in changes)]
    # the rack focus hides each change: fully out of focus on the frame that holds the downbeat
    foc = [s for s in seq if s.kind == cpl.FOCUS]
    hidden = []
    for s in foc:
        k = int(np.floor(s.t0 * FPS + 1e-9))
        u_at, u_before = sc.uniforms(k / FPS), sc.uniforms((k - 1) / FPS)
        hidden.append(u_at[50] >= 0.95 and u_before[50] >= 0.9 and int(round(u_at[32])) == s.look.station
                      and int(round(u_before[32])) != s.look.station)
    # every station is on screen in every 30-minute stretch
    win_missing = []
    for w0 in np.arange(P.intro[1], P.outro[0] - 1800 + 1e-6, 600.0):
        seen = {cpl.STATIONS[s.look.station] for s, e in zip(seq, ends) if s.t0 < w0 + 1800 and e > w0}
        if len(seen) < 6:
            win_missing.append(round(float(w0)))
    ok = no_repeat and long_enough and balanced and starts_db and not sec_cov and all(hidden) and not win_missing
    rec("K6", ok, stations=len(seq), shares=shares, no_station_twice_in_a_row=no_repeat,
        shortest_s=round(min(lengths[:-1]), 1), at_least_min_bars=long_enough, changes_on_downbeats=starts_db,
        sections=len(secs), sections_without_a_change=[round(x, 1) for x in sec_cov[:5]],
        rack_focus_changes=len(foc), hidden_in_focus=all(hidden), windows_missing_a_station=win_missing[:5])


# ------------------------------------------------------------------ the key's harmonics set the modes (K7)
def _k7(sc):
    P = sc.P
    ex = np.load(sc.cfg["_clip"]["extras"], allow_pickle=True)
    exd = {k: ex[k] for k in ex.files}
    sp = [s for s in P.spans if s.look.station != cpl.VOID]
    phr = np.asarray(sc.st.phrases, float)
    bar = 4 * 60.0 / max(sc.full.tempo, 60)
    key_bad, harm_bad, law_bad, n_plate = [], [], [], 0
    hmax = int((sc.cfg.get("drive", {}) or {}).get("harmonics", 6))
    for s in sp:
        nxt = phr[phr > s.t0 + bar]
        t1 = float(nxt[0]) if len(nxt) else s.t0 + 8 * bar
        if s.kind in (cpl.CUT, cpl.FOCUS) or s.why == "intro":
            t1 = s.t0 + 8 * bar
        # the key most often detected in the phrase (an independent count of the detector's output)
        kt = np.asarray(exd["key_t"], float)
        codes = [str(c) for c in exd["key_code"]][int(np.searchsorted(kt, s.t0)):int(np.searchsorted(kt, max(t1, s.t0 + 1)))]
        roots = [cpl.camelot_root(c) for c in codes]
        roots = [r for r in roots if r is not None]
        if roots:
            top = Counter(roots).most_common()
            best = top[0][1]
            if (s.look.root, s.look.minor) not in [r for r, n in top if n == best]:
                key_bad.append(round(s.t0, 1))
        ratio = s.look.hz / cpl.root_hz(s.look.root)
        if abs(ratio - round(ratio)) > 1e-6 or not 1 <= round(ratio) <= hmax:
            harm_bad.append(round(s.t0, 1))
        if s.look.station == 0:
            n_plate += 1
            m = s.look.m
            if m[0] < 0.5:
                want = s.look.hz / cpl.F_SQUARE
                near = sorted(cpl._square_modes(), key=lambda nm: abs(nm[0] ** 2 + nm[1] ** 2 - want))[:4]
                ok = (int(m[1]), int(m[2])) in near and (int(m[5]), int(m[6])) in near
            else:
                want = np.sqrt(s.look.hz / cpl.F_ROUND)
                near = sorted(cpl._round_modes(), key=lambda mn: abs(mn[0] + 2 * mn[1] - want))[:4]
                ok = (int(m[1]), int(m[2])) in near and (int(m[5]), int(m[6])) in near
            if not ok:
                law_bad.append(round(s.t0, 1))
    roots_used = len({s.look.root for s in sp})
    harms = sorted({s.look.harmonic for s in sp})
    rec("K7", not key_bad and not harm_bad and not law_bad and roots_used >= 6 and len(harms) == hmax,
        modes=len(sp), off_key=key_bad[:5], not_a_harmonic=harm_bad[:5], plate_modes=n_plate,
        against_chladnis_law=law_bad[:5], roots_used=roots_used, harmonics_used=harms)


# ------------------------------------------------------------------ the picture shows the physics (K8)
def _k8(sc):
    """Chladni: the sand in the picture lies on the nodal lines of the plate's mode. Rubens tube: the flames
    in the picture stand in the mode's wave. Both judged on settled frames every 10 s across the set."""
    P = sc.P
    dur = sc.full.duration
    chl, rub = [], []
    for t in np.arange(5.0, dur, 10.0):
        t = float(t)
        if not steady(P, t):
            continue
        cur = cpl.span_at(P, t)[1]
        if cur.station == 0 and len(chl) < 60:
            pic = rgb(sc, t).astype(np.float32) @ np.array([0.2126, 0.7152, 0.0722], np.float32)
            pred = layer(sc, t, 2)[:, :, 0].astype(np.float32)
            fld = layer(sc, t, 1)
            plate = (fld[:, :, 0] >= 5) & (fld[:, :, 2] < 40)  # on the plate, in focus enough to judge grains
            on = plate & (pred > 128)
            off = plate & (pred < 3)
            if on.sum() < 2000 or off.sum() < 2000:
                continue
            ref = np.median(pic[off])
            contrast = np.abs(pic - ref)
            chl.append(float(contrast[on].mean() / max(contrast[off].mean(), 1e-3)))
        elif cur.station == 3 and cur.m[0] < 0.5 and len(rub) < 60 and sc._curve(P.calm, t) == 0:
            # (in breakdowns the drive rests and the flames burn low and even, by design)
            pic = rgb(sc, t).astype(np.float32) @ np.array([0.2126, 0.7152, 0.0722], np.float32)
            pred = layer(sc, t, 2)[:, :, 0].astype(np.float32)
            fl = layer(sc, t, 1)[:, :, 0].astype(np.float32) > 20
            idx = np.nonzero(fl.sum(0) >= 3)[0]              # columns where flames stand
            if len(idx) < 300:
                continue
            # each column's flame height against the wave the mode predicts there, smoothed over about a
            # hole's width (columns between two flames hold less fire)
            height = np.array([np.ptp(np.nonzero(fl[:, c])[0]) for c in idx], np.float32)
            pa = np.array([pred[:, c][fl[:, c]].mean() for c in idx])
            k = 31
            sm = np.ones(k) / k
            rub.append(float(np.corrcoef(np.convolve(height, sm, "valid"), np.convolve(pa, sm, "valid"))[0, 1]))
    chl_ok = len(chl) >= 10 and float(np.median(chl)) >= 3.0 and min(chl) >= 1.5
    rub_ok = len(rub) >= 10 and float(np.median(rub)) >= 0.6 and min(rub) >= 0.3
    rec("K8", chl_ok and rub_ok, chladni_frames=len(chl),
        sand_on_lines_vs_off_median=round(float(np.median(chl)), 2) if chl else None,
        sand_on_lines_vs_off_min=round(min(chl), 2) if chl else None, rubens_frames=len(rub),
        flames_follow_wave_r_median=round(float(np.median(rub)), 3) if rub else None,
        flames_follow_wave_r_min=round(min(rub), 3) if rub else None)


# ------------------------------------------------------------------ builds sweep, breakdowns rest (K9)
def _motion(sc, t0: float, n: int = 120) -> float:
    fr = np.stack([np.frombuffer(sc.frame_at(t0 + k / FPS), np.uint8).reshape(1080, 1920, 4)[::8, ::8, :3]
                   .astype(np.float32) for k in range(n)])
    return float(np.abs(np.diff(fr, axis=0)).mean())


def _k9(sc):
    P = sc.P
    bar = 4 * 60.0 / max(sc.full.tempo, 60)
    sweeps = []
    for a, b in P.build_spans:
        if b - a < 2 * bar or a < P.intro[1] or b > P.outro[0]:
            continue
        f0 = 2 ** sc.uniforms(a + 0.02)[U_SWEEP]
        f1 = 2 ** sc.uniforms(b - 0.02)[U_SWEEP]
        mono = np.all(np.diff([sc.uniforms(t)[U_SWEEP] for t in np.linspace(a + 0.02, b - 0.02, 12)]) >= 0)
        sweeps.append(f1 / f0 >= 1.9 and bool(mono))
    # breakdowns of 8 bars or more: the picture moves less than half as much as in the bars before them
    ratios, where = [], []
    for a, b in P.calm_spans:
        if len(ratios) >= 12:
            break
        if b - a < 8 * bar or a < P.intro[1] + 8 * bar or b > P.outro[0] - 8 * bar:
            continue
        t_in = a + 0.5 * (b - a)
        t_out = a - 4 * bar
        ci, co = cpl.span_at(P, t_in), cpl.span_at(P, t_out)
        if ci[1].station != co[1].station or not steady(P, t_in) or not steady(P, t_out) or \
                sc._curve(P.calm, t_out) > 0:
            continue
        ratios.append(_motion(sc, t_in) / max(_motion(sc, t_out), 1e-6))
        where.append(round(a))
    ok = bool(sweeps) and all(sweeps) and len(ratios) >= 5 and max(ratios) < 0.5
    rec("K9", ok, builds=len(sweeps), builds_sweep_an_octave=round(float(np.mean(sweeps)), 3) if sweeps else None,
        breakdowns_measured=len(ratios), breakdown_motion_ratio_max=round(max(ratios), 3) if ratios else None,
        breakdown_motion_ratio_median=round(float(np.median(ratios)), 3) if ratios else None, at=where)


# ------------------------------------------------------------------ drops overdrive on their downbeat (K10)
def _k10(sc):
    P, st, an = sc.P, sc.st, sc.full
    db = st.downbeats
    bar = 4 * 60.0 / max(an.tempo, 60)
    drops = [d.t0 for d in st.drops if P.intro[1] + 2 * bar <= d.t0 < P.outro[0] - 2 * bar]
    covered = all(any(abs(p - db[int(np.argmin(np.abs(db - d)))]) * FPS <= 1.0 for p in P.drops) for d in drops)
    on_db = all(float(np.min(np.abs(db - p))) * FPS <= 1.0 for p in P.drops)
    shown = []
    for p in P.drops:
        k = int(np.floor(p * FPS + 1e-9))
        u, u0 = sc.uniforms(k / FPS), sc.uniforms((k - 1) / FPS)
        shown.append(0 <= u[U_AGE] < 1.0 / FPS + 1e-6 and not (0 <= u0[U_AGE] < 0.5 / FPS))
    # the overdrive is visible: the picture changes more in the half second after a drop than before it
    jumps = []
    for p in P.drops[::9][:10]:
        jumps.append(_motion(sc, p, 30) / max(_motion(sc, p - 0.55, 30), 1e-6))
    cut = [s for s in station_starts(P) if s.kind == cpl.CUT]
    cut_ok = all(any(abs(s.t0 - p) < 1e-6 for p in P.drops) for s in cut)
    ok = covered and on_db and all(shown) and float(np.median(jumps)) >= 1.5 and cut_ok
    rec("K10", ok, drops=len(drops), every_drop_overdrives=covered, on_downbeats=on_db, on_its_frame=all(shown),
        motion_after_vs_before_median=round(float(np.median(jumps)), 2), station_cuts_on_drops=len(cut))


# ------------------------------------------------------------------ bands drive layers (K11)
def _k11(sc, fx):
    """Each layer driven alone, the picture held still at one moment while one band plays through 60 s of
    the set: how much the layer follows its band."""
    P = sc.P
    n = 3600
    calm_t = np.arange(len(P.calm)) / cpl.RATE
    best = None
    for w0 in np.arange(P.intro[1] + 30, P.outro[0] - 120, 30.0):
        m = (calm_t >= w0) & (calm_t < w0 + 60)
        if P.calm[m].max() > 0:
            continue
        sd = float(np.std(sc.env["lowmid"][int(w0 * FPS):int((w0 + 60) * FPS)]))
        if best is None or sd > best[0]:
            best = (sd, float(w0))
    t0 = best[1] if best else 3560.0
    tt = t0 + np.arange(n) / FPS
    fi = np.clip(np.round(tt * FPS).astype(int), 0, len(sc.env["sub"]) - 1)

    def moment(station, kind=None):
        for t in np.arange(t0 + 60, P.outro[0] - 5, 5.0):
            prev, cur, x, span = cpl.span_at(P, float(t))
            if cur.station == station and steady(P, float(t)) and (kind is None or cur.m[0] == kind):
                return float(t)
        return None
    ph_t = np.interp(tt, np.arange(len(P.phase)) / cpl.RATE, P.phase)
    or_t = np.interp(tt, np.arange(len(P.orbit)) / cpl.RATE, P.orbit)
    slot = {"sub": U_SUB, "bass": U_BASS, "lowmid": U_LOWMID, "highmid": U_HMID, "high": U_HIGH}

    def frames(lay, band, t_ref, step=12):
        sc.isolate(lay)
        try:
            base = sc.uniforms(t_ref)
            out = []
            for k in range(n):
                u = base.copy()
                u[slot[band]] = sc.env[band][fi[k]]
                if band == "lowmid":
                    u[U_PHASE] = base[U_PHASE] + ph_t[k] - ph_t[0]
                    u[U_AZ] = base[U_AZ] + or_t[k] - or_t[0]
                a = np.frombuffer(sc.engine.render(u, out="rgba"), np.uint8).reshape(1080, 1920, 4)[::step, ::step, :3]
                out.append(a.astype(np.float32).mean(-1))
        finally:
            sc.isolate(None)
        return np.stack(out)
    corr, where = {}, {}
    # brightness: the flames' height (sub, Rubens tube), the accent light (bass), glints (highs, Chladni plate)
    for lay, band, station, kind, step in (("drive", "sub", 3, 0.0, 12), ("light", "bass", 2, None, 12),
                                           ("sparkle", "high", 0, None, 2)):
        t_ref = moment(station, kind)
        where[f"{band}->{lay}"] = (cpl.STATIONS[station], t_ref)
        act = frames(lay, band, t_ref, step).mean((1, 2))
        corr[f"{band}->{lay}"] = round(float(np.corrcoef(act, sc.env[band][fi])[0, 1]), 3)
    # how far the picture strays from the layer at rest: the sand's fizz and the flames' flicker (high mids)
    t_ref = moment(0)
    where["highmid->detail"] = ("chladni", t_ref)
    f = frames("detail", "highmid", t_ref, step=4)
    sc.isolate("detail")
    try:
        u = sc.uniforms(t_ref)
        u[U_HMID] = 0.0
        rest = np.frombuffer(sc.engine.render(u, out="rgba"), np.uint8).reshape(1080, 1920, 4)[::4, ::4, :3].astype(np.float32).mean(-1)
    finally:
        sc.isolate(None)
    act = np.abs(f - rest[None]).mean((1, 2))
    corr["highmid->detail"] = round(float(np.corrcoef(act, sc.env["highmid"][fi])[0, 1]), 3)
    # the low mids: how fast the camera circles and the patterns drift (motion, Faraday dish)
    t_ref = moment(1)
    where["lowmid->drift"] = ("faraday", t_ref)
    f = frames("drive", "lowmid", t_ref)
    motion = np.convolve(np.abs(np.diff(f, axis=0)).mean((1, 2)), np.ones(9) / 9, mode="same")
    lm = _lowmid_rate(sc, tt)
    corr["lowmid->drift"] = round(float(np.corrcoef(motion, lm[1:])[0, 1]), 3)

    def motion_of(audio, start=0.0):
        s = make_scene(audio, title="T")
        ts = start + 2.0 + np.arange(240) / FPS
        fr = np.stack([np.frombuffer(s.frame_at(float(t)), np.uint8).reshape(1080, 1920, 4)[::8, ::8, :3]
                       .astype(np.float32) for t in ts])
        return float(np.abs(np.diff(fr, axis=0)).mean())
    ms, mm = motion_of(fx["silence.wav"], 6.0), motion_of(fx["setA.wav"], 20.0)
    rec("K11", all(v >= 0.6 for v in corr.values()) and ms < 0.35 * mm, **corr, window_s=round(t0, 1),
        held_at={k: (v[0], round(v[1], 1)) for k, v in where.items()}, silence_motion=round(ms, 3),
        music_motion=round(mm, 3), silence_ratio=round(ms / max(mm, 1e-9), 3))


def _lowmid_rate(sc, tt):
    """The rate the low mids set for the drift (the plan's phase and orbit derivatives)."""
    P = sc.P
    ph = np.gradient(np.interp(tt, np.arange(len(P.phase)) / cpl.RATE, P.phase)) * FPS
    return ph


# ------------------------------------------------------------------ reproducible and resumable (K13)
def _k13(fx):
    o1 = render(fx["setB.wav"], W / "det1.mov", "--duration", "6", "-k", "dreamy")
    o2 = render(fx["setB.wav"], W / "det2.mov", "--duration", "6", "-k", "dreamy")
    side = json.loads(Path(str(o1) + ".json").read_text())
    cmd = BIN + shlex.split(side["reproduce"])[1:] + ["-o", str(W / "det3.mov")]
    sh(cmd)
    m1, m2, m3 = verify.frame_md5(o1), verify.frame_md5(o2), verify.frame_md5(W / "det3.mov")
    out_r = W / "resume.mov"
    parts = Path(str(out_r) + ".parts")
    for p in (out_r, parts):
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    rargs = [*BIN, "render", str(fx["setB.wav"]), "-t", "cymatics", "-o", str(out_r), "--chunk", "3", "--cpu", "4.5"]
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
    rec("K13", m1 == m2 == m3 and resumed_ok, md5=m1, sidecar_reproduces=m3 == m1, chunks_before_kill=n_before,
        resume_matches=resumed_ok)


# ------------------------------------------------------------------ the full render (K5, K14, K15)
def _scan(path: Path, w=64, h=36):
    """One streamed pass over every frame at w x h: the picture's brightness (beat sync) and the luminance
    and saturated-red share of nine quarter-screen windows (flashes)."""
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
    """Frame indices where a flash completes: a rise of at least thr followed by a fall of at least thr."""
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
        for k in ("K5", "K14", "K15"):
            rec(k, False, note="pass --full out/knisper_cymatics.mov")
        return
    print("(decoding the full render: a few tens of minutes)", flush=True)
    rep = verify.run(full, None)
    cf = rep["checks"]
    adur = float(verify._probe(full)["format"]["duration"])
    audio_ok = verify._audio_md5(set_audio, 0.0, adur) == verify._audio_md5(full)
    gray, lum_w, red_w = _scan(full)
    bs = verify.beat_sync(gray, kick_beats(an), FPS)
    rec("K5", bs["hit_rate"] >= 0.9 and bs["median_offset_frames"] <= 1 and cf["A7_ok"] and audio_ok, **bs,
        av_diff_frames=cf["A7_av_duration_diff_frames"], audio_identical=audio_ok, frames=len(gray))
    side = json.loads(Path(str(full) + ".json").read_text())
    log = ROOT / "work" / "full_render_cymatics.log"
    loads = [float(x) for x in re.findall(r"frames .* load ([0-9.]+)", log.read_text())] if log.exists() else []
    eng = side.get("engine", {})
    gpu = eng.get("gpu", {})
    rec("K14", bool(loads) and max(loads) <= 7.5 and isinstance(gpu, dict) and "Metal" in str(gpu.get("backend_type")),
        max_load_1m=max(loads) if loads else None, median_load_1m=float(np.median(loads)) if loads else None,
        samples_over_7=int(sum(x > 7 for x in loads)), samples=len(loads),
        render_min=round(side["render_seconds"] / 60, 1),
        realtime_ratio=round(side["audio"]["duration"] / side["render_seconds"], 2), gb=round(side["bytes"] / 1e9, 2),
        gpu=gpu, key_detection=bool(eng.get("extras_cache")), yuv_on_gpu=scenes.pix_fmt({"engine": "cymatics"}) == "nv12")
    worst_gen = max(_per_second_max(_flashes(lum_w[:, k], 0.10)) for k in range(lum_w.shape[1]))
    worst_red = max(_per_second_max(_flashes(red_w[:, k], 0.25)) for k in range(red_w.shape[1]))
    n_gen = sum(len(_flashes(lum_w[:, k], 0.10)) for k in range(lum_w.shape[1]))
    n_red = sum(len(_flashes(red_w[:, k], 0.25)) for k in range(red_w.shape[1]))
    np.savez(W / "scan.npz", gray=gray, lum_w=lum_w, red_w=red_w)
    rec("K15", worst_gen <= 3 and worst_red <= 3, most_general_flashes_in_1s=worst_gen, general_flashes=n_gen,
        red_flashes=n_red, most_red_flashes_in_1s=worst_red, frames=len(lum_w))


# ------------------------------------------------------------------ the reel (K16)
def _k16(reel_path: Path, set_audio: Path):
    meta = Path(str(reel_path) + ".json")
    if not reel_path.exists() or not meta.exists():
        rec("K16", False, note=f"run setrender reel first ({reel_path})")
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
    first_open = clips[0]["t0"] < P.intro[1] and clips[0]["t0"] + clips[0]["dur"] > P.intro[0]
    last_close = clips[-1]["t0"] + clips[-1]["dur"] > P.outro[0] and clips[-1]["t0"] < P.outro[1]
    centres = np.array([c["t0"] + c["dur"] / 2 for c in clips[1:-1]])
    gaps = np.diff(centres)
    even = bool(len(gaps) and np.all(np.abs(gaps - gaps.mean()) <= 0.5 * gaps.mean()))
    stations = {cpl.STATIONS[cpl.span_at(P, c["t0"] + c["dur"] / 2)[1].station] for c in clips
                if cpl.span_at(P, c["t0"] + c["dur"] / 2)[1].station != cpl.VOID}
    sr = 48000

    def pcm(args):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", *args, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-"],
                             check=True, capture_output=True).stdout
        return np.frombuffer(raw, np.float32)
    rr = pcm(["-i", str(reel_path)])
    corr, off = [], 0.0
    mg = sr // 10
    for c in clips:
        a = rr[int((off + 0.35) * sr): int((off + c["dur"] - 0.35) * sr)]
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
    rec("K16", 10 <= n <= 15 and all(2.0 <= x <= 3.0 for x in durs) and abs(total - 30) <= 2 and all(on_beat)
        and first_open and last_close and even and min(corr) >= 0.9 and len(stations) == 6, clips=n,
        clip_s=round(float(np.mean(durs)), 2), total_s=round(total, 2), cuts_on_beats=all(on_beat),
        first_is_lights_up=first_open, last_is_lights_down=last_close, evenly_spread=even,
        stations_shown=sorted(stations), gap_s=[round(float(g)) for g in gaps], audio_match_min_r=round(min(corr), 3),
        moments=[c["why"] for c in clips])


if __name__ == "__main__":
    t0 = time.time()
    rc = main()
    print(f"({time.time() - t0:.0f}s)")
    sys.exit(rc)
