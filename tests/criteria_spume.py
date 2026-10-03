"""Automated checks for docs/criteria/CRITERIA-spume.md. Run:

    .venv/bin/python tests/criteria_spume.py [SET_AUDIO] [--full out/knisper_spume.mov]
        [--reel "out/<set>.spume_highlights.mp4"] [--only S8,S9]

Writes work/criteria-spume/report.json and prints a table. Human (H) items are for manual sign-off.
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
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from setrender import cli, config, scenes, verify  # noqa: E402
from setrender.crop import music  # noqa: E402
from setrender.spume import film  # noqa: E402
from setrender.spume import plan as spl  # noqa: E402
from setrender.timeline import Timeline  # noqa: E402

W = ROOT / "work" / "criteria-spume"
W.mkdir(parents=True, exist_ok=True)
if (ROOT / ".venv" / "bin" / "setrender").exists():
    BIN = [str(ROOT / ".venv" / "bin" / "setrender")]
else:
    BIN = [sys.executable, "-m", "setrender.cli"]
    os.environ["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + os.environ.get("PYTHONPATH", "")
SET = "/Users/dean/src/setstreamer/media/Pepper&Pumpernickl - Knisper 2026 (trimmed).WAV"
FPS = 60.0
results: dict[str, dict] = {}
# what the text recogniser reads in chains of bubbles: digits, dots and round letters
ROUND = set("OoCcQ")


def is_word(text: str, confidence: float) -> bool:
    """A word the recogniser is sure of: three or more letters in a row that aren't all round shapes, with
    confidence 0.5 or more (bubble chains read as '00 00' or '00100100', frost as a low-confidence jumble)."""
    runs = re.findall(r"[A-Za-z]{3,}", text)
    return confidence >= 0.5 and any(any(ch not in ROUND for ch in r) for r in runs)


def rec(cid, ok, **info):
    results[cid] = {"pass": bool(ok), **info}
    print(f"{'PASS' if ok else 'FAIL'}  {cid:4s} {json.dumps(info, default=str)[:180]}", flush=True)


def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def render(audio, out, *extra):
    sh([*BIN, "render", str(audio), "-t", "spume", "-o", str(out), "--cpu", "4.5", *extra])
    return out


def quiet(fn, *a):
    with contextlib.redirect_stderr(io.StringIO()):
        return fn(*a)


def make_scene(audio: Path, start=0.0, keywords=(), sets=(), seed=0, title="T"):
    cfg = config.resolve("spume", None, list(keywords), list(sets))
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


def ids(sc, t: float) -> np.ndarray:
    """(depth, element, bubble hash) per pixel from the renderer's id layer."""
    sc.debug = 1
    try:
        a = np.frombuffer(sc.frame_at(t), np.uint8).reshape(1080, 1920, 4)
    finally:
        sc.debug = 0
    # the bubble's hash and the hash of the foam it belongs to, as one key
    return np.stack([a[:, :, 0] // 16, a[:, :, 1] // 16, a[:, :, 2].astype(np.int32) * 256 + a[:, :, 3],
                     a[:, :, 3]], -1).astype(np.int32)


def hist(fr):
    q = (fr // 32).reshape(-1, 3).astype(int)
    h = np.bincount(q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2], minlength=512).astype(float)
    return h / h.sum()


def steady(P, t: float) -> bool:
    """t is inside a look, not in a transition, and away from the intro and the end."""
    if t < P.intro[1] + 1 or t > P.outro[0] - 1:
        return False
    A, B, x, kind = spl.span_at(P, t)
    if B is not None:
        return False
    if len(P.pops) and np.min(np.abs(np.array(P.pops) - t)) < 2.0:
        return False
    return True


def main():
    argv = sys.argv[1:]
    opts = ("--only", "--full", "--reel")
    args = [a for k, a in enumerate(argv) if not a.startswith("--") and (k == 0 or argv[k - 1] not in opts)]
    set_audio = Path(args[0] if args else SET)
    full = Path(argv[argv.index("--full") + 1]) if "--full" in argv else None
    reel_path = Path(argv[argv.index("--reel") + 1]) if "--reel" in argv else \
        ROOT / "out" / f"{set_audio.stem}.spume_highlights.mp4"
    only = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else None

    def want(*ids_):
        return only is None or bool(only & set(ids_))
    fx = fixtures(set_audio)
    if want("S1", "S4"):
        _s1_s4(fx, set_audio)
    if want("S2"):
        _s2(fx)
    if want("S3", "S14"):
        _s3_s14(fx, set_audio)
    sc = None
    if want("S8", "S9", "S10", "S11", "S12", "S13"):
        t0 = time.time()
        sc = make_scene(set_audio, title=set_audio.stem)
        print(f"(full-set scene built in {time.time() - t0:.0f}s)")
    if want("S8", "S10"):
        _s8_s10(sc)
    if want("S9"):
        _s9(sc)
    if want("S12"):
        _s12(sc, fx)
    if want("S13"):
        _s13(sc)
    if want("S15"):
        _s15(fx)
    if want("S5", "S6", "S7", "S11", "S16", "S17"):
        _full_checks(full, set_audio, sc)
    if want("S18"):
        _s18(reel_path, set_audio)
    order = [f"S{k}" for k in range(1, 19)]
    report = {k: results[k] for k in order if k in results}
    (W / ("report.json" if only is None else "report-partial.json")).write_text(json.dumps(report, indent=2, default=str))
    npass = sum(r["pass"] for r in report.values())
    print(f"\n{npass}/{len(report)} automated checks pass. Human checklist H1-H8: see docs/criteria/CRITERIA-spume.md")
    return 0 if npass == len(report) else 1


# ------------------------------------------------------------------ interface, output, sync
def _s1_s4(fx, set_audio):
    # a minute of the set itself (spume plans from the whole set, so a slice is the real thing)
    s0 = 3560.0
    out = render(set_audio, W / "s1.mov", "--start", str(s0), "--duration", "60")
    rep = verify.run(out, set_audio, s0, 60.0)
    c = rep["checks"]
    a11 = {k: v for k, v in c.items() if k.startswith("A11")}
    ok_fmt = all(v for v in a11.values() if isinstance(v, bool)) and c["A11_resolution"] == "1920x1080" and c["A11_fps"] == 60
    rec("S1", ok_fmt and c.get("A12_audio_sample_identical", False), **a11,
        audio_identical=c.get("A12_audio_sample_identical"))
    an, _, _ = quiet(cli.get_analysis, set_audio, 0.0, None, None, False)
    kb = kick_beats(an)
    kb = kb[(kb >= s0) & (kb < s0 + 60.0)] - s0
    bs = verify.beat_sync(picture_signal(out), kb, FPS)
    rec("S4", bs["hit_rate"] >= 0.9 and bs["median_offset_frames"] <= 1 and c["A7_ok"], **bs,
        av_diff_frames=c["A7_av_duration_diff_frames"])


def _s2(fx):
    fmt = {}
    for name in ("fmt_s24_48k.aiff", "fmt_f32_96k_mono.wav", "fmt_s32_44k.wav"):
        o = render(fx[name], W / f"{name}.mov", "--quality", "draft")
        r = verify.run(o, fx[name], 0.0, 4.0)
        fmt[name] = r["checks"].get("A12_audio_sample_identical", False) and r["checks"]["A7_ok"]
    rec("S2", all(fmt.values()), **fmt)


def _s3_s14(fx, set_audio):
    ts = [5.0, 11.7, 18.3, 25.0]                  # inside both test sets (60 s and 30 s)
    a = make_scene(fx["setA.wav"])
    fa = np.stack([rgb(a, t) for t in ts])
    fa2 = np.stack([rgb(make_scene(fx["setA.wav"]), t) for t in ts])
    fb = np.stack([rgb(make_scene(fx["setB.wav"]), t) for t in ts])
    fk = np.stack([rgb(make_scene(fx["setA.wav"], keywords=["acid"]), t) for t in ts])
    fs = np.stack([rgb(make_scene(fx["setA.wav"], seed=7), t) for t in ts])
    fset = np.stack([rgb(make_scene(fx["setA.wav"], sets=["twist=1.5"]), t) for t in ts])
    # a slice draws the frames the full render has at the same times
    s_full = make_scene(set_audio, start=0.0, title=set_audio.stem)
    s0 = 600.0
    s_slice = make_scene(set_audio, start=s0, title=set_audio.stem)
    k0 = int(s0 * FPS)
    slice_ok = all(s_full.frame_rgba(k0 + i) == s_slice.frame_rgba(i) for i in (0, 37, 211))
    rec("S3", (fk != fa).any() and (fs != fa).any() and (fset != fa).any() and (fa2 == fa).all() and slice_ok,
        keywords_change=bool((fk != fa).any()), seed_changes=bool((fs != fa).any()), set_changes=bool((fset != fa).any()),
        same_inputs_identical=bool((fa2 == fa).all()), slice_matches_full=slice_ok)
    d_ab = float(np.mean([np.abs(hist(x) - hist(y)).sum() for x, y in zip(fa, fb)]))
    d_aa = float(np.mean([np.abs(hist(x) - hist(y)).sum() for x, y in zip(fa, fa2)]))
    rec("S14", d_ab > 0.3 and d_aa == 0.0, dist_different_sets=round(d_ab, 3), dist_same_set=round(d_aa, 3))


# ------------------------------------------------------------------ recursion and elements (S8, S10)
def _s8_s10(sc):
    P = sc.P
    dur = sc.full.duration
    times = [t for t in np.arange(5.0, dur, 10.0) if steady(P, t)]
    deep, n_ok = [], 0
    pairs = bad_pairs = 0
    bad_where = []
    elem_t: list[tuple[float, set]] = []
    for t in times:
        d = ids(sc, float(t))
        dep, el, hid, fid = d[:, :, 0], d[:, :, 1], d[:, :, 2], d[:, :, 3]
        counts = np.bincount(dep.ravel(), minlength=16)
        levels = int((counts >= 0.001 * dep.size).sum())
        deep.append(levels)
        n_ok += levels >= 3
        # neighbouring bubbles in the same foam never hold the same element (the film itself is 8); only
        # bubbles at least 3 px across are judged (smaller ones are dots that fall between pixels)
        H_, W_ = hid.shape
        for ax in (1, 0):
            def sh_(arr, k):
                return arr[:, 2 + k:W_ - 3 + k] if ax == 1 else arr[2 + k:H_ - 3 + k, :]
            same_a = (sh_(hid, -2) == sh_(hid, 0)) & (sh_(hid, -1) == sh_(hid, 0))
            same_b = (sh_(hid, 2) == sh_(hid, 1)) & (sh_(hid, 3) == sh_(hid, 1))
            m = (sh_(hid, 0) != sh_(hid, 1)) & (sh_(dep, 0) == sh_(dep, 1)) & (sh_(fid, 0) == sh_(fid, 1)) & \
                (sh_(el, 0) < 8) & (sh_(el, 1) < 8) & same_a & same_b
            elA, elB = sh_(el, 0), sh_(el, 1)
            pairs += int(m.sum())
            nb = int((m & (elA == elB)).sum())
            bad_pairs += nb
            if nb and len(bad_where) < 5:
                bad_where.append(round(float(t), 1))
        present = {int(x) for x in np.unique(el) if x < 8 and (el == x).sum() >= 0.001 * el.size}
        elem_t.append((float(t), present))
    zoom_ok = bool(np.all(np.diff(P.zoom) >= 0))
    share = n_ok / max(len(times), 1)
    rec("S8", share >= 0.95 and zoom_ok, frames=len(times), with_3_levels=round(share, 4),
        levels_median=float(np.median(deep)), levels_min=int(min(deep)), zoom_never_backwards=zoom_ok)
    # every 10-minute window shows all eight elements
    windows, missing = 0, []
    t_lo, t_hi = P.intro[1], P.outro[0]
    for w0 in np.arange(t_lo, t_hi - 600 + 1e-6, 600.0):
        s = set().union(*[e for t, e in elem_t if w0 <= t < w0 + 600]) if elem_t else set()
        windows += 1
        if len(s) < 8:
            missing.append((round(float(w0)), sorted(set(range(8)) - s)))
    # the classifier covers the set, and surges start within 2 s of the sound it heard
    ex = np.load(sc.cfg["_clip"]["extras"], allow_pickle=True)
    t_sa = ex["sa_t"]
    gaps = float(max(np.max(np.diff(t_sa)), t_sa[0] - 1.5, dur - (t_sa[-1] + 1.5))) if len(t_sa) > 1 else 99.0
    labels = [str(x) for x in ex["sa_labels"]]
    lat = []
    for g in P.surges:
        col = ex["sa_p"][:, labels.index(g.label)].astype(np.float32)
        hot = t_sa[col > 0.45]
        lat.append(float(np.min(np.abs(hot - g.t0))) if len(hot) else 99.0)
    kinds = sorted({spl.ELEMENTS[g.elem] for g in P.surges})
    rec("S10", bad_pairs == 0 and not missing and gaps <= 2.0 and len(P.surges) >= 6 and max(lat or [99]) <= 2.0,
        neighbour_pairs=pairs, same_element_neighbours=bad_pairs, first_bad_frames=bad_where,
        ten_minute_windows=windows, windows_missing=missing[:4], classifier_max_gap_s=round(gaps, 2),
        surges=len(P.surges), surge_elements=kinds, max_latency_s=round(max(lat or [0]), 2))


# ------------------------------------------------------------------ kaleidoscopes (S9)
def _rot_corr(fr: np.ndarray, n: int) -> float:
    """Correlation of the picture with itself turned by one fold, on a polar grid round the centre."""
    g = fr.astype(np.float32) @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    rr = np.linspace(40, 500, 60)
    aa = np.linspace(0, 2 * np.pi, 360, endpoint=False)
    R, A = np.meshgrid(rr, aa)

    def sample(ang):
        x = 960 + R * np.cos(ang)
        y = 540 - R * np.sin(ang)
        return g[np.clip(np.round(y).astype(int), 0, 1079), np.clip(np.round(x).astype(int), 0, 1919)]
    a, b = sample(A), sample(A + 2 * np.pi / n)
    return float(np.corrcoef(a.ravel(), b.ravel())[0, 1])


def _s9(sc):
    P = sc.P
    db = sc.st.downbeats
    sp = [s for s in P.spans if s.look.motif != spl.VOID]
    frac = spl.kal_fraction(P, P.intro[1], P.outro[0])
    switches = [(a, b) for a, b in zip(sp, sp[1:]) if (a.look.folds > 0) != (b.look.folds > 0)]
    on_db = all(float(np.min(np.abs(db - b.t0))) * FPS <= 1.0 for a, b in switches)
    folds = sorted({s.look.folds for s in sp if s.look.folds})
    # pictures: rotationally symmetric when on, not when off
    on_c, off_c = [], []
    rs = np.random.default_rng(5)
    cand = [s for s in sp if s.dur > 0]
    for s, nxt in zip(cand, cand[1:] + [None]):
        t_end = nxt.t0 if nxt else P.outro[0]
        t = s.t0 + s.dur + 0.3 * (t_end - s.t0 - s.dur)
        if not steady(P, t) or t_end - s.t0 < 4:
            continue
        if s.look.folds and len(on_c) < 24:
            on_c.append(_rot_corr(rgb(sc, t), s.look.folds))
        elif not s.look.folds and s.look.motif != 5 and len(off_c) < 24:
            off_c.append(_rot_corr(rgb(sc, t), int(rs.choice([5, 7]))))
    ok = 0.25 <= frac <= 0.75 and len(switches) >= 30 and len(folds) >= 4 and on_db and \
        min(on_c or [0]) >= 0.9 and max(off_c or [1]) < 0.9
    rec("S9", ok, share_on=round(frac, 3), switches=len(switches), fold_counts=folds, switches_on_downbeats=on_db,
        symmetric_when_on_min=round(min(on_c or [0]), 3), symmetric_when_off_max=round(max(off_c or [1]), 3),
        frames_on=len(on_c), frames_off=len(off_c))


# ------------------------------------------------------------------ bands drive layers (S12)
def _s12(sc, fx):
    """Each layer rendered alone, the picture held still at one moment while one band plays through 60 s of
    the set: how much the layer moves with its band."""
    P = sc.P
    n = 3600
    # a minute of the set with no breakdown in it (breakdowns slow everything on purpose) where the low mids
    # move the most; the picture is held at a moment just after it
    calm_t = np.arange(len(P.calm)) / spl.RATE
    best = None
    for w0 in np.arange(P.intro[1] + 30, P.outro[0] - 120, 30.0):
        m = (calm_t >= w0) & (calm_t < w0 + 60)
        if P.calm[m].max() > 0:
            continue
        sd = float(np.std(sc.env["lowmid"][int(w0 * FPS):int((w0 + 60) * FPS)]))
        if best is None or sd > best[0]:
            best = (sd, float(w0))
    t0 = best[1] if best else 3560.0
    t_ref = t0 + 65.0
    while spl.span_at(P, t_ref)[0].motif in (5, spl.VOID) and t_ref < t0 + 600:
        t_ref += 15.0                       # a motif with bubbles (the giant film has no sparkle)
    tt = t0 + np.arange(n) / FPS
    fi = np.clip(np.round(tt * FPS).astype(int), 0, len(sc.env["sub"]) - 1)
    sw_t = np.interp(tt, np.arange(len(P.swirl)) / spl.RATE, P.swirl)
    # aud = kick, sub, bass, lowmid (8..11), aud2 = highmid, high (12, 13); a look's swirl phase is 26 / 42
    slot = {"sub": 9, "bass": 10, "lowmid": 11, "highmid": 12, "high": 13}

    def frames(layer, band):
        sc.isolate(layer)
        try:
            base = sc.uniforms(t_ref)
            out = []
            for k in range(n):
                u = base.copy()
                u[slot[band]] = sc.env[band][fi[k]]
                if band == "lowmid":
                    u[26] = (base[26] + sw_t[k] - sw_t[0]) % 6283.1853
                    u[42] = (base[42] + sw_t[k] - sw_t[0]) % 6283.1853
                a = np.frombuffer(sc.engine.render(u, out="rgba"), np.uint8).reshape(1080, 1920, 4)[::12, ::12, :3]
                out.append(a.astype(np.float32).mean(-1))
        finally:
            sc.isolate(None)
        return np.stack(out)
    corr = {}
    # brightness layers: the film (sub), the Plateau borders' neon (bass), the elements (high mids), sparkle (highs)
    for layer, band in (("film", "sub"), ("border", "bass"), ("interior", "highmid"), ("sparkle", "high")):
        act = frames(layer, band).mean((1, 2))
        corr[f"{band}->{layer}"] = round(float(np.corrcoef(act, sc.env[band][fi])[0, 1]), 3)
    # the film's swirl (low mids): how much the film moves from frame to frame
    f = frames("film", "lowmid")
    motion = np.convolve(np.abs(np.diff(f, axis=0)).mean((1, 2)), np.ones(9) / 9, mode="same")
    corr["lowmid->swirl"] = round(float(np.corrcoef(motion, sc.env["lowmid"][fi[1:]])[0, 1]), 3)

    # A10: silence is near-static compared with music (both rendered from their own set)
    def motion_of(audio, start=0.0):
        s = make_scene(audio, title="T")
        ts = start + 2.0 + np.arange(240) / FPS
        fr = np.stack([np.frombuffer(s.frame_at(float(t)), np.uint8).reshape(1080, 1920, 4)[::8, ::8, :3]
                       .astype(np.float32) for t in ts])
        return float(np.abs(np.diff(fr, axis=0)).mean())
    ms, mm = motion_of(fx["silence.wav"], 6.0), motion_of(fx["setA.wav"], 20.0)
    rec("S12", all(v >= 0.6 for v in corr.values()) and ms < 0.35 * mm, **corr, window_s=round(t0, 1),
        held_at_s=round(t_ref, 1), silence_motion=round(ms, 3),
        music_motion=round(mm, 3), silence_ratio=round(ms / max(mm, 1e-9), 3))


# ------------------------------------------------------------------ structure (S13)
def _s13(sc):
    P, st, an = sc.P, sc.st, sc.full
    db = st.downbeats
    bar = 4 * 60.0 / max(an.tempo, 60)

    def on_db(t):
        return float(np.min(np.abs(db - t))) * FPS <= 1.0
    sp = [s for s in P.spans if s.look.motif != spl.VOID]
    # a segment is a new motif: the first span of each section index
    firsts = {}
    for s in sp:
        firsts.setdefault(s.section, s)
    seq = [firsts[k] for k in sorted(firsts)]
    motifs = [spl.MOTIFS[s.look.motif] for s in seq]
    no_repeat = all(a != b for a, b in zip(motifs, motifs[1:]))
    all_six = len(set(motifs)) == 6
    starts_db = all(on_db(s.t0) for s in seq[1:])
    secs = [s for s in an.sections if P.intro[1] + 4 * bar <= s < P.outro[0] - 4 * bar]
    # a section that starts next to a breakdown's edge changes the look on that edge (within 4 bars)
    sec_cov = all(any(abs(x.t0 - s) <= 4 * bar + 1.0 / FPS for x in seq) for s in secs)
    pops_ok = all(on_db(p) for p in P.pops)
    drops = [d.t0 for d in st.drops if P.intro[1] + 2 * bar <= d.t0 < P.outro[0] - 2 * bar]
    drops_popped = all(any(abs(p - db[int(np.argmin(np.abs(db - d)))]) * FPS <= 1.0 for p in P.pops) for d in drops)
    # pops show on the frame whose display interval holds the downbeat
    shown = []
    for p in P.pops[:40]:
        k = int(np.floor(p * FPS + 1e-9))
        u = sc.uniforms(k / FPS)
        u0 = sc.uniforms((k - 1) / FPS)
        shown.append(u[52] >= 0 and u[52] < 1.0 / FPS + 1e-6 and not (0 <= u0[52] < 0.5 / FPS))
    # breakdowns slow the dive to under half the bars around them; builds speed it and saturate
    rate = np.gradient(P.zoom) * spl.RATE
    t_r = np.arange(len(rate)) / spl.RATE
    calm_t = np.interp(t_r, np.arange(len(P.calm)) / spl.RATE, P.calm)
    slow = []
    for a, b in P.calm_spans:
        if b - a < 8 * bar or a < P.intro[1] + 8 * bar or b > P.outro[0] - 8 * bar:
            continue
        inside = rate[(t_r >= a + bar) & (t_r < b - bar)].mean()
        near = ((t_r >= a - 8 * bar) & (t_r < a)) | ((t_r >= b) & (t_r < b + 8 * bar))
        near &= calm_t == 0                      # the bars around it that are not themselves a breakdown
        if near.sum() < spl.RATE * bar:
            continue
        slow.append(inside / max(rate[near].mean(), 1e-9))
    # builds wind up: the vortex tightens and the colour saturates from the build's start to its end
    wind = []
    for a, b in P.build_spans:
        if b - a < 2 * bar or a < P.intro[1] or b > P.outro[0]:
            continue
        u0, u1 = sc.uniforms(a + 0.05), sc.uniforms(b - 0.05)
        tw0 = u0[21] / max(spl.span_at(P, a + 0.05)[0].twist, 1e-6)
        tw1 = u1[21] / max(spl.span_at(P, b - 0.05)[0].twist, 1e-6)
        wind.append(tw1 > tw0 and u1[59] > u0[59])
    ok = no_repeat and all_six and starts_db and sec_cov and pops_ok and drops_popped and all(shown) and \
        (max(slow) < 0.5 if slow else True) and (all(wind) if wind else True)
    rec("S13", ok, segments=len(seq), motifs_used=sorted(set(motifs)), no_motif_twice_in_a_row=no_repeat,
        starts_on_downbeats=starts_db, every_section_changes_look=sec_cov, pops=len(P.pops), drops=len(drops),
        every_drop_pops=drops_popped, pops_on_downbeats=pops_ok, pop_on_its_frame=all(shown),
        breakdowns=len(slow), breakdown_dive_speed_max=round(max(slow), 3) if slow else None,
        builds=len(wind), builds_wind_up=round(float(np.mean(wind)), 3) if wind else None)


# ------------------------------------------------------------------ reproducible and resumable (S15)
def _s15(fx):
    o1 = render(fx["setB.wav"], W / "det1.mov", "--duration", "6", "-k", "acid")
    o2 = render(fx["setB.wav"], W / "det2.mov", "--duration", "6", "-k", "acid")
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
    rargs = [*BIN, "render", str(fx["setB.wav"]), "-t", "spume", "-o", str(out_r), "--chunk", "3", "--cpu", "4.5"]
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
    rec("S15", m1 == m2 == m3 and resumed_ok, md5=m1, sidecar_reproduces=m3 == m1, chunks_before_kill=n_before,
        resume_matches=resumed_ok)


# ------------------------------------------------------------------ the full render (S5, S6, S7, S11, S16, S17)
def _scan(path: Path, w=64, h=36, every=120):
    """One streamed pass over every frame at w x h: the picture's brightness (beat sync), the luminance and
    saturated-red share of nine quarter-screen windows (flashes), and every `every`-th frame kept for colour."""
    cmd = ["nice", "-n", "10", "ffmpeg", "-v", "error", "-nostdin", "-hwaccel", "videotoolbox", "-i", str(path),
           "-map", "0:v:0", "-vf", f"scale={w}:{h}:flags=area,format=rgb24", "-f", "rawvideo", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    n = w * h * 3
    wins = [(y0, x0) for y0 in (0, h // 4, h // 2) for x0 in (0, w // 4, w // 2)]
    gray, lum_w, red_w, kept = [], [], [], []
    i0 = 0
    while True:
        b = proc.stdout.read(n * 1200)
        if not b:
            break
        f = np.frombuffer(b, np.uint8).reshape(-1, h, w, 3).astype(np.float32) / 255.0
        gray.append(f @ np.array([0.2126, 0.7152, 0.0722], np.float32))
        lin = np.where(f <= 0.04045, f / 12.92, ((f + 0.055) / 1.055) ** 2.4)
        lum = lin @ np.array([0.2126, 0.7152, 0.0722], np.float32)
        red = ((lin[..., 0] / np.maximum(lin.sum(-1), 1e-6) >= 0.8) & (lin[..., 0] > 0.05)).astype(np.float32)
        lum_w.append(np.stack([lum[:, y0:y0 + h // 2, x0:x0 + w // 2].mean((1, 2)) for y0, x0 in wins], 1))
        red_w.append(np.stack([red[:, y0:y0 + h // 2, x0:x0 + w // 2].mean((1, 2)) for y0, x0 in wins], 1))
        idx = np.arange(i0, i0 + len(f))
        kept.append((idx[idx % every == 0], f[idx % every == 0]))
        gray[-1] = gray[-1].mean((1, 2))
        i0 += len(f)
    proc.wait()
    ki = np.concatenate([k for k, _ in kept])
    kf = np.concatenate([x for _, x in kept])
    return np.concatenate(gray) * 255.0, np.concatenate(lum_w), np.concatenate(red_w), ki, kf


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


def _full_checks(full: Path | None, set_audio: Path, sc):
    an, _, _ = quiet(cli.get_analysis, set_audio, 0.0, None, None, False)
    # S6 part one: nothing in the engine draws text (no font, glyph or lettering code)
    src = "\n".join(p.read_text() for p in (ROOT / "src" / "setrender" / "spume").glob("*.py"))
    no_text_code = not re.search(r"\b(font|glyph|lettering|freetype|render_text|draw_text)\b", src, re.I)
    if full is None or not full.exists():
        for k in ("S5", "S6", "S7", "S11", "S16", "S17"):
            rec(k, False, note="pass --full out/knisper_spume.mov")
        return
    print("(decoding the full render: a few tens of minutes)", flush=True)
    rep = verify.run(full, None)
    cf = rep["checks"]
    adur = float(verify._probe(full)["format"]["duration"])
    audio_ok = verify._audio_md5(set_audio, 0.0, adur) == verify._audio_md5(full)
    gray, lum_w, red_w, ki, kf = _scan(full)
    bs = verify.beat_sync(gray, kick_beats(an), FPS)
    rec("S5", bs["hit_rate"] >= 0.9 and bs["median_offset_frames"] <= 1 and cf["A7_ok"] and audio_ok, **bs,
        av_diff_frames=cf["A7_av_duration_diff_frames"], audio_identical=audio_ok, frames=len(gray))
    # S6 / S7: Apple's Vision models on frames sampled every 10 s (keyframes, decoded full size)
    vd = W / "vision"
    if vd.exists():
        shutil.rmtree(vd)
    vd.mkdir()
    sh(["ffmpeg", "-v", "error", "-nostdin", "-skip_frame", "nokey", "-i", str(full), "-map", "0:v:0",
        "-vf", "select='isnan(prev_selected_t)+gte(t-prev_selected_t\\,9.99)'", "-fps_mode", "vfr",
        "-q:v", "2", str(vd / "f%05d.jpg")])
    out = subprocess.run(["swift", str(ROOT / "tests" / "vision_check.swift"), str(vd)], check=True,
                         capture_output=True, text=True).stdout
    rows = [json.loads(x) for x in out.splitlines() if x.startswith("{")]
    (W / "vision.json").write_text(json.dumps(rows, indent=1))
    raw_text = [(r["file"], w["text"], round(float(w["confidence"]), 2)) for r in rows for w in r.get("text", [])]
    words = [x for x in raw_text if is_word(x[1], x[2])]
    rec("S6", no_text_code and not words and len(rows) >= 0.95 * an.duration / 10, frames=len(rows),
        engine_has_no_text_code=no_text_code, words_found=words[:8], frames_with_any_reading=len({x[0] for x in raw_text}),
        readings=raw_text[:12])
    hits = [bool(r.get("faces") or r.get("humans") or r.get("animals")) for r in rows]
    consecutive = any(a and b for a, b in zip(hits, hits[1:]))
    rec("S7", sum(hits) <= 0.01 * len(rows) and not consecutive, frames=len(rows), frames_with_detections=sum(hits),
        in_a_row=consecutive, detections=[(r["file"], [k for k in ("faces", "humans", "animals") if r.get(k)])
                                          for r in rows if r.get("faces") or r.get("humans") or r.get("animals")][:8])
    # S11: saturation and hue coverage on frames every 2 s, from the intro's end to the outro
    P = sc.P if sc is not None else None
    lo_t = P.intro[1] if P else 10.0
    hi_t = P.outro[0] if P else an.duration - 30
    tk = ki / FPS
    sel = (tk >= lo_t) & (tk < hi_t)
    f = kf[sel]
    mx, mn = f.max(-1), f.min(-1)
    sat = np.where(mx > 1e-6, (mx - mn) / np.maximum(mx, 1e-6), 0.0)
    med_sat = float(np.median(sat))
    r_, g_, b_ = f[..., 0], f[..., 1], f[..., 2]
    d = np.maximum(mx - mn, 1e-6)
    hue = np.where(mx == r_, ((g_ - b_) / d) % 6, np.where(mx == g_, (b_ - r_) / d + 2, (r_ - g_) / d + 4)) / 6.0
    worst, mins = 12, 0
    tks = tk[sel]
    for m0 in np.arange(lo_t, hi_t - 60 + 1e-6, 60.0):
        msk = (tks >= m0) & (tks < m0 + 60)
        hs = hue[msk][(sat[msk] > 0.25) & (mx[msk] > 0.15)]
        mins += 1
        if len(hs) == 0:
            worst = 0
            continue
        h12 = np.bincount(np.clip((hs * 12).astype(int), 0, 11), minlength=12) / len(hs)
        worst = min(worst, int((h12 >= 0.01).sum()))
    tbl = film.table()
    # the table is the spectral model's own output: zero thickness reflects nothing, and colour varies with it
    R = film.reflectance(np.array([0.0, 250.0]), film.LAMBDA, 1.335 + 0j, 1.0 + 0j)
    spectral_ok = bool(R[0].max() < 1e-12 and tbl[0, 0, :3].max() < 1e-6 and np.ptp(R[1]) > 0.05)
    rec("S11", spectral_ok and med_sat >= 0.45 and worst >= 10, spectral_film_model=spectral_ok,
        median_saturation=round(med_sat, 3), minutes=mins, fewest_hue_sectors_in_a_minute=worst)
    # S16: load during the render, GPU and classifier recorded
    side = json.loads(Path(str(full) + ".json").read_text())
    log = ROOT / "work" / "full_render_spume.log"
    loads = [float(x) for x in re.findall(r"frames .* load ([0-9.]+)", log.read_text())] if log.exists() else []
    eng = side.get("engine", {})
    gpu = eng.get("gpu", {})
    rec("S16", bool(loads) and max(loads) <= 7.5 and isinstance(gpu, dict) and "Metal" in str(gpu.get("backend_type")),
        max_load_1m=max(loads) if loads else None, median_load_1m=float(np.median(loads)) if loads else None,
        samples_over_7=int(sum(x > 7 for x in loads)), samples=len(loads),
        render_min=round(side["render_seconds"] / 60, 1),
        realtime_ratio=round(side["audio"]["duration"] / side["render_seconds"], 2), gb=round(side["bytes"] / 1e9, 2),
        gpu=gpu, classifier=eng.get("sound_classifier"), yuv_on_gpu=scenes.pix_fmt({"engine": "spume"}) == "nv12")
    # S17: general flashes (relative luminance on a 200 cd/m2 display: 20 cd/m2 is 10%) over any quarter of
    # the screen, and saturated red flashes; at most 3 general flashes in any second, no red ones
    worst_gen = max(_per_second_max(_flashes(lum_w[:, k], 0.10)) for k in range(lum_w.shape[1]))
    worst_red = max(_per_second_max(_flashes(red_w[:, k], 0.25)) for k in range(red_w.shape[1]))
    n_red = sum(len(_flashes(red_w[:, k], 0.25)) for k in range(red_w.shape[1]))
    rec("S17", worst_gen <= 3 and n_red == 0, most_general_flashes_in_1s=worst_gen, red_flashes=n_red,
        most_red_flashes_in_1s=worst_red, frames=len(lum_w))


# ------------------------------------------------------------------ the reel (S18)
def _s18(reel_path: Path, set_audio: Path):
    meta = Path(str(reel_path) + ".json")
    if not reel_path.exists() or not meta.exists():
        rec("S18", False, note=f"run setrender reel first ({reel_path})")
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
    first_open = clips[0]["t0"] + clips[0]["dur"] <= P.intro[1] + 1e-6
    last_pop = clips[-1]["t0"] <= P.outro[1] <= clips[-1]["t0"] + clips[-1]["dur"]
    centres = np.array([c["t0"] + c["dur"] / 2 for c in clips[1:-1]])
    gaps = np.diff(centres)
    even = bool(len(gaps) and np.all(np.abs(gaps - gaps.mean()) <= 0.5 * gaps.mean()))
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
    rec("S18", 10 <= n <= 15 and all(2.0 <= x <= 3.0 for x in durs) and abs(total - 30) <= 2 and all(on_beat)
        and first_open and last_pop and even and min(corr) >= 0.9, clips=n, clip_s=round(float(np.mean(durs)), 2),
        total_s=round(total, 2), cuts_on_beats=all(on_beat), first_is_opening=first_open, last_has_final_pop=last_pop,
        evenly_spread=even, gap_s=[round(float(g)) for g in gaps], audio_match_min_r=round(min(corr), 3),
        moments=[c["why"] for c in clips])


if __name__ == "__main__":
    t0 = time.time()
    rc = main()
    print(f"({time.time() - t0:.0f}s)")
    sys.exit(rc)
