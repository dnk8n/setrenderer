"""Automated checks for CRITERIA-rubberhose.md. Run:

    .venv/bin/python tests/criteria_rubberhose.py [SET_AUDIO] [--full out/knisper_rubberhose.mov]
        [--reel "out/<set>.rubberhose_highlights.mp4"] [--only R7,R9]

Writes work/criteria-rubberhose/report.json and prints a table. Human (H) items are for manual sign-off.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import re
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
from setrender import cli, config, reel, scenes, verify  # noqa: E402
from setrender.crop import music  # noqa: E402
from setrender.hose import bosses, lettering, story  # noqa: E402
from setrender.timeline import Timeline  # noqa: E402

W = ROOT / "work" / "criteria-rubberhose"
W.mkdir(parents=True, exist_ok=True)
BIN = str(ROOT / ".venv" / "bin" / "setrender")
SET = "/Users/dean/src/setstreamer/media/Pepper&Pumpernickl - Knisper 2026.WAV"
results: dict[str, dict] = {}


def rec(cid, ok, **info):
    results[cid] = {"pass": bool(ok), **info}
    print(f"{'PASS' if ok else 'FAIL'}  {cid:4s} {json.dumps(info, default=str)[:170]}", flush=True)


def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def render(audio, out, *extra):
    sh([BIN, "render", str(audio), "-t", "rubberhose", "-o", str(out), "--cpu", "4.5", *extra])
    return out


def quiet(fn, *a):
    with contextlib.redirect_stderr(io.StringIO()):
        return fn(*a)


def make_scene(audio: Path, start=0.0, keywords=(), sets=(), seed=0, title="T"):
    cfg = config.resolve("rubberhose", None, list(keywords), list(sets))
    an, ah, _ = quiet(cli.get_analysis, audio, 0.0, None, None, False)
    quiet(scenes.prepare, cfg, audio, ah, start, cli.CACHE_DIR, lambda *a: None)
    cfg["_clip"].update(width=1920, height=1080)
    tl = Timeline(an, 60, cfg.get("smoothing", {}))
    return scenes.make(cfg, tl, an, np.random.default_rng(cli.make_seed(seed, ah, cfg, 0.0)), title).scene


def picture_signal(path: Path) -> np.ndarray:
    """Mean brightness of the picture per frame (decoded on the media engine, streamed small)."""
    cmd = ["nice", "-n", "10", "ffmpeg", "-v", "error", "-nostdin", "-hwaccel", "videotoolbox", "-i", str(path),
           "-map", "0:v:0", "-vf", "scale=32:18:flags=area,format=gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, 32 * 18).astype(np.float32).mean(1)


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


def rgb_frames(sc, idx):
    return np.stack([np.frombuffer(sc.frame_rgba(i), np.uint8).reshape(1080, 1920, 4)[:, :, :3].copy() for i in idx])


def hist(fr):
    q = (fr // 32).reshape(-1, 3).astype(int)
    h = np.bincount(q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2], minlength=512).astype(float)
    return h / h.sum()


def main():
    argv = sys.argv[1:]
    opts = ("--only", "--full", "--reel")
    args = [a for k, a in enumerate(argv) if not a.startswith("--") and (k == 0 or argv[k - 1] not in opts)]
    set_audio = Path(args[0] if args else SET)
    full = Path(argv[argv.index("--full") + 1]) if "--full" in argv else None
    reel_path = Path(argv[argv.index("--reel") + 1]) if "--reel" in argv else \
        ROOT / "out" / f"{set_audio.stem}.rubberhose_highlights.mp4"
    only = set(argv[argv.index("--only") + 1].split(",")) if "--only" in argv else None

    def want(*ids):
        return only is None or bool(only & set(ids))
    fx = fixtures(set_audio)
    if want("R1", "R4"):
        _r1_r4(fx)
    if want("R2"):
        _r2(fx)
    if want("R3", "R12"):
        _r3_r12(fx, set_audio)
    if want("R6", "R7", "R8", "R9", "R10", "R11"):
        _plan_checks(set_audio)
    if want("R13"):
        _r13(fx)
    if want("R5", "R14"):
        _r5_r14(full, set_audio)
    if want("R15"):
        _r15(reel_path, set_audio)
    order = [f"R{k}" for k in range(1, 16)]
    report = {k: results[k] for k in order if k in results}
    (W / ("report.json" if only is None else "report-partial.json")).write_text(json.dumps(report, indent=2, default=str))
    npass = sum(r["pass"] for r in report.values())
    print(f"\n{npass}/{len(report)} automated checks pass. Human checklist H1-H6: see CRITERIA-rubberhose.md")
    return 0 if npass == len(report) else 1


def _r1_r4(fx):
    out = render(fx["setA.wav"], W / "r1.mov")
    rep = verify.run(out, fx["setA.wav"], 0.0, None)
    c = rep["checks"]
    a11 = {k: v for k, v in c.items() if k.startswith("A11")}
    ok_fmt = all(v for v in a11.values() if isinstance(v, bool)) and c["A11_resolution"] == "1920x1080" and c["A11_fps"] == 60
    rec("R1", ok_fmt and c.get("A12_audio_sample_identical", False), **a11,
        audio_identical=c.get("A12_audio_sample_identical"))
    an_a, _, _ = quiet(cli.get_analysis, fx["setA.wav"], 0.0, None, None, False)
    bs = verify.beat_sync(picture_signal(out), kick_beats(an_a), 60.0)
    rec("R4", bs["hit_rate"] >= 0.9 and bs["median_offset_frames"] <= 1 and c["A7_ok"], **bs,
        av_diff_frames=c["A7_av_duration_diff_frames"])


def _r2(fx):
    fmt = {}
    for name in ("fmt_s24_48k.aiff", "fmt_f32_96k_mono.wav", "fmt_s32_44k.wav"):
        o = render(fx[name], W / f"{name}.mov", "--quality", "draft")
        r = verify.run(o, fx[name], 0.0, 4.0)
        fmt[name] = r["checks"].get("A12_audio_sample_identical", False) and r["checks"]["A7_ok"]
    rec("R2", all(fmt.values()), **fmt)


def _r3_r12(fx, set_audio):
    ix = [300, 700, 1100, 1500]          # inside both test sets (60 s and 30 s)
    a = make_scene(fx["setA.wav"])
    fa = rgb_frames(a, ix)
    fa2 = rgb_frames(make_scene(fx["setA.wav"]), ix)
    fb = rgb_frames(make_scene(fx["setB.wav"]), ix)
    fk = rgb_frames(make_scene(fx["setA.wav"], keywords=["twostrip"]), ix)
    fs = rgb_frames(make_scene(fx["setA.wav"], seed=7), ix)
    fset = rgb_frames(make_scene(fx["setA.wav"], sets=["boil=0"]), ix)
    # a slice draws the frames the full render has at the same times
    s0, s1 = 600.0, make_scene(set_audio, start=0.0, title=set_audio.stem)
    s_slice = make_scene(set_audio, start=s0, title=set_audio.stem)
    k0 = int(s0 * 60)
    slice_ok = all(s1.frame_rgba(k0 + i) == s_slice.frame_rgba(i) for i in (0, 37, 211))
    rec("R3", (fk != fa).any() and (fs != fa).any() and (fset != fa).any() and (fa2 == fa).all() and slice_ok,
        keywords_change=bool((fk != fa).any()), seed_changes=bool((fs != fa).any()), set_changes=bool((fset != fa).any()),
        same_inputs_identical=bool((fa2 == fa).all()), slice_matches_full=slice_ok)
    d_ab = float(np.mean([np.abs(hist(x) - hist(y)).sum() for x, y in zip(fa, fb)]))
    d_aa = float(np.mean([np.abs(hist(x) - hist(y)).sum() for x, y in zip(fa, fa2)]))
    rec("R12", d_ab > 0.3 and d_aa == 0.0, dist_different_sets=round(d_ab, 3), dist_same_set=round(d_aa, 3))


def _plan_checks(set_audio):
    t0 = time.time()
    sc = make_scene(set_audio, title=set_audio.stem)
    m, P = sc.m, sc.P
    st = m.st
    fps = 60.0
    print(f"(full-set scene built in {time.time() - t0:.0f}s)")
    db = m.db
    bar = 4 * m.period

    def on_bar(t):
        return float(np.min(np.abs(db - t))) * fps <= 1.0

    # R6: drawing clock over the first fight
    a = P.acts[0]
    fr = np.arange(int(a.go * fps), int(min(a.ko, a.go + 120) * fps))
    draw = np.array([sc.ctx(i / fps).drawing for i in fr])
    per_s = float((np.diff(draw) != 0).sum() / (len(fr) / fps))
    bt = m.beats[(m.beats > fr[0] / fps + 0.1) & (m.beats < fr[-1] / fps - 0.1)]
    beat_frames = [int(np.floor(b * fps)) for b in bt]
    new_on_beat = [sc.ctx(f / fps).drawing != sc.ctx((f - 1) / fps).drawing for f in beat_frames]
    rec("R6", 22 <= per_s <= 30 and all(new_on_beat), drawings_per_s=round(per_s, 2),
        beat_frames=len(new_on_beat), new_drawing_on_beat=round(float(np.mean(new_on_beat)), 4))

    # R7: acts
    lens = [(x.t1 - x.t0) / 60 for x in P.acts]
    cards = {(c.kind, round(c.t0, 3)) for c in P.cards}
    acts_ok = all(on_bar(x.t0) and on_bar(x.t1) or x.t1 >= P.outro[0] - 0.01 for x in P.acts)
    three = all(len(x.phases) == 3 for x in P.acts)
    has_cards = all(("ready", round(x.t0 + 0.5 * bar, 3)) in cards and ("go", round(x.go, 3)) in cards
                    and ("ko", round(x.ko, 3)) in cards for x in P.acts)
    pool = [b for b in (sc.cfg.get("bosses") or [])]
    seen = sorted({x.boss for x in P.acts})
    no_repeat = all(x.boss != y.boss for x, y in zip(P.acts[:-1], P.acts[1:]))
    rec("R7", all(5 <= v <= 15 for v in lens) and acts_ok and three and has_cards and set(pool) <= set(seen) and no_repeat,
        acts=len(P.acts), minutes=[round(v, 1) for v in lens], on_downbeats=acts_ok, three_phases=three,
        ready_go_ko_cards=has_cards, bosses_seen=seen, no_back_to_back=no_repeat)

    # R8: intermissions
    eligible = []
    for bd in st.breakdowns:
        t0b, t1b = m.snap_bar(bd.t0), m.snap_bar(bd.t1)
        x = next((x for x in P.acts if x.t0 <= t0b < x.t1), None)
        if t1b - t0b >= 15 * bar and x and t0b >= x.go + 2 * bar and t1b <= x.ko - 2 * bar:
            eligible.append((t0b, x.k))
    covered = [any(abs(i.t0 - t) < 1e-6 for i in P.inters) or sum(1 for i in P.inters if i.act == k) >= 2
               for t, k in eligible]
    kinds = sorted({i.kind for i in P.inters})
    bars_ok = all(on_bar(i.t0) and on_bar(i.t1) for i in P.inters)
    per_act = max([sum(1 for i in P.inters if i.act == x.k) for x in P.acts] or [0])
    rec("R8", all(covered) and len(kinds) == 3 and bars_ok and per_act <= 2, intermissions=len(P.inters),
        eligible_breakdowns=len(eligible), all_eligible_used=all(covered), kinds=kinds, on_downbeats=bars_ok,
        max_per_act=per_act)

    # R9: choreography follows the music
    n_shots = on_beat = in_kick = 0
    n_bul = bul_ok = 0
    sup_ok, n_sup = 0, 0
    pink = parried = 0
    drops = [m.snap_bar(d.t0) for d in st.drops]
    for x in P.acts:
        F = sc._fight(x)
        for s in F.shots:
            n_shots += 1
            on_beat += float(np.min(np.abs(m.beats - s.ts))) * fps <= 1.0
            in_kick += st.kick_at(s.ts)
            if s.pink:
                pink += 1
                h_air = False
                for h in (0, 1):
                    lift, j, _ = F.jump_at(h, s.ts + s.life)
                    h_air |= (j is not None and j.parry and lift > 0)
                parried += h_air and s.end == "parry"
        for ts, h in F.bullets:
            n_bul += 1
            k = int(np.searchsorted(m.beats, ts + 0.02) - 1)
            if 0 <= k < len(m.beats) - 1:
                frac = (ts - h * 0.012 - m.beats[k]) / (m.beats[k + 1] - m.beats[k])
                grid = min(abs(frac - g) for g in (0.0, 0.25, 0.5, 0.75, 1.0)) < 0.02
                bul_ok += grid and m.beat_high[k] >= 0.25
        for t in F.supers:
            n_sup += 1
            sup_ok += min(abs(t - d) for d in drops) * fps <= 1.0
    rec("R9", on_beat == n_shots and in_kick == n_shots and bul_ok == n_bul and sup_ok == n_sup and parried == pink,
        boss_shots=n_shots, on_beat=on_beat, in_kick_bars=in_kick, hero_shots=n_bul, hero_shots_on_grid_when_hats=bul_ok,
        supers=n_sup, supers_on_drops=sup_ok, pink=pink, parried=parried)

    # R10: every string the lettering draws, sampled every second of the set
    seen_txt = set()
    orig = lettering.words

    def spy(ink, s, *a, **k):
        seen_txt.add(s)
        return orig(ink, s, *a, **k)
    lettering.words = spy
    try:
        for t in np.arange(0.5, m.dur, 1.0):
            sc.build(float(t))
        for c in P.cards:                     # and the middle of every card, however short
            sc.build((c.t0 + c.t1) / 2)
    finally:
        lettering.words = orig
    title = " ".join(set_audio.stem.replace("_", " ").replace("&", " & ").split())
    parts = [p.strip() for p in title.split(" - ") if p.strip()]
    allowed = {"READY?", "KNOCKOUT!", "INTERMISSION", "FOLLOW THE BOUNCING BALL!", "THE END", "A RUBBER HOSE REVUE",
               "STARRING", "RING!", "MEOW!", "RIBBIT!", "GONG!", "HA HA!", "RIP", "LA", "DA", "DOO", "BOP", "HEY",
               *story.EXCLAIM, *story.GO_WORDS, *parts, " - ".join(parts[1:]), f"{sc.names[0]} & {sc.names[1]}"}
    rounds = {f"ROUND {x.k + 1}: {bosses.BY_NAME[x.boss]['title']}" for x in P.acts}
    bad = sorted(s for s in seen_txt if s not in allowed and s not in rounds and not re.fullmatch(r"BPM \d+", s))
    rec("R10", not bad, strings=len(seen_txt), unexpected=bad[:10])

    # R11: classifier coverage and sound-cued gags
    ex = np.load(sc.cfg["_clip"]["extras"], allow_pickle=True)
    t_sa = ex["sa_t"]
    # windows are 3 s long, centred on sa_t: the gap between results, and what the ends leave uncovered
    gaps = float(max(np.max(np.diff(t_sa)), t_sa[0] - 1.5, m.dur - (t_sa[-1] + 1.5)))
    labels = [str(x) for x in ex["sa_labels"]]
    sound_gags = [g for g in P.gags if g.label in story.GAG_SOUNDS]
    lat = []
    for g in sound_gags:
        col = ex["sa_p"][:, labels.index(g.label)]
        hot = t_sa[col > 0.45]
        lat.append(float(np.min(np.abs(hot - g.t0))) if len(hot) else 99.0)
    kinds11 = sorted({g.kind for g in sound_gags})
    rec("R11", gaps <= 2.0 and len(kinds11) >= 8 and max(lat or [99]) <= 2.0, classifier_windows=len(t_sa),
        max_gap_s=round(gaps, 2), sound_gag_kinds=kinds11, sound_gags=len(sound_gags),
        max_latency_s=round(max(lat or [0]), 2))


def _r13(fx):
    o1 = render(fx["setB.wav"], W / "det1.mov", "--duration", "6", "-k", "twostrip")
    o2 = render(fx["setB.wav"], W / "det2.mov", "--duration", "6", "-k", "twostrip")
    side = json.loads(Path(str(o1) + ".json").read_text())
    cmd = shlex.split(side["reproduce"]) + ["-o", str(W / "det3.mov")]
    cmd[0] = BIN
    sh(cmd)
    m1, m2, m3 = verify.frame_md5(o1), verify.frame_md5(o2), verify.frame_md5(W / "det3.mov")
    out_r = W / "resume.mov"
    parts = Path(str(out_r) + ".parts")
    import shutil
    for p in (out_r, parts):
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    rargs = [BIN, "render", str(fx["setB.wav"]), "-t", "rubberhose", "-o", str(out_r), "--chunk", "3", "--cpu", "4.5"]
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
    rec("R13", m1 == m2 == m3 and resumed_ok, md5=m1, sidecar_reproduces=m3 == m1, chunks_before_kill=n_before,
        resume_matches=resumed_ok)


def _r5_r14(full, set_audio):
    an, _, _ = quiet(cli.get_analysis, set_audio, 0.0, None, None, False)
    if full is None or not full.exists():
        rec("R5", False, note="pass --full out/knisper_rubberhose.mov")
        rec("R14", False, note="pass --full out/knisper_rubberhose.mov")
        return
    rep = verify.run(full, set_audio, 0.0, None)
    cf = rep["checks"]
    bs = verify.beat_sync(picture_signal(full), kick_beats(an), 60.0)
    rec("R5", bs["hit_rate"] >= 0.9 and bs["median_offset_frames"] <= 1 and cf["A7_ok"]
        and cf.get("A12_audio_sample_identical", False), **bs, av_diff_frames=cf["A7_av_duration_diff_frames"],
        audio_identical=cf.get("A12_audio_sample_identical"))
    side = json.loads(Path(str(full) + ".json").read_text())
    log = ROOT / "work" / "load_full_rubberhose.log"
    loads = [float(ln.split()[1]) for ln in log.read_text().splitlines() if len(ln.split()) > 1] if log.exists() else []
    eng = side.get("engine", {})
    gpu = eng.get("gpu", {})
    rec("R14", bool(loads) and max(loads) <= 7.5 and isinstance(gpu, dict) and "Metal" in str(gpu.get("backend_type")),
        max_load_1m=max(loads) if loads else None, median_load_1m=float(np.median(loads)) if loads else None,
        render_min=round(side["render_seconds"] / 60, 1),
        realtime_ratio=round(side["audio"]["duration"] / side["render_seconds"], 2), gb=round(side["bytes"] / 1e9, 2),
        gpu=gpu, classifier=eng.get("sound_classifier"), yuv_on_gpu=scenes.pix_fmt({"engine": "rubberhose"}) == "nv12",
        tools=side.get("tools", {}).get("ffmpeg"))


def _r15(reel_path: Path, set_audio: Path):
    meta = Path(str(reel_path) + ".json")
    if not reel_path.exists() or not meta.exists():
        rec("R15", False, note=f"run setrender reel first ({reel_path})")
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
    first_title = clips[0]["t0"] + clips[0]["dur"] <= P.intro[1]
    last_end = clips[-1]["t0"] >= P.outro[0]
    centres = np.array([c["t0"] + c["dur"] / 2 for c in clips[1:-1]])
    gaps = np.diff(centres)
    even = bool(len(gaps) and np.all(np.abs(gaps - gaps.mean()) <= 0.5 * gaps.mean()))
    # each clip's sound is the set's own sound at that time
    def pcm(args):
        raw = subprocess.run(["ffmpeg", "-v", "error", "-nostdin", *args, "-ac", "1", "-ar", "8000", "-f", "f32le", "-"],
                             check=True, capture_output=True).stdout
        return np.frombuffer(raw, np.float32)
    rr = pcm(["-i", str(reel_path)])
    corr, off = [], 0.0
    for c in clips:
        a = rr[int((off + 0.35) * 8000): int((off + c["dur"] - 0.35) * 8000)]
        b = pcm(["-ss", f"{c['t0'] + 0.35:.4f}", "-t", f"{c['dur'] - 0.7:.4f}", "-i", str(set_audio)])
        k = min(len(a), len(b)) - 1600
        # best match within ±100 ms (the AAC encoder's priming delay shifts the decoded audio slightly)
        best = max((float(np.corrcoef(a[800 + d: 800 + d + k], b[800: 800 + k])[0, 1]) for d in range(-800, 801, 8)),
                   default=0.0) if k > 100 else 0.0
        corr.append(best)
        off += c["dur"]
    rec("R15", 10 <= n <= 15 and all(2.0 <= x <= 3.0 for x in durs) and abs(total - 30) <= 2 and all(on_beat)
        and first_title and last_end and even and min(corr) >= 0.9, clips=n, clip_s=round(float(np.mean(durs)), 2),
        total_s=round(total, 2), cuts_on_beats=all(on_beat), first_is_title=first_title, last_is_end=last_end,
        evenly_spread=even, gap_s=[round(float(g)) for g in gaps], audio_match_min_r=round(min(corr), 3),
        moments=[c["why"] for c in clips])


if __name__ == "__main__":
    t0 = time.time()
    rc = main()
    print(f"({time.time() - t0:.0f}s)")
    sys.exit(rc)
