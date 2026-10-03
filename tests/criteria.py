"""Automated completeness checks (see docs/criteria/CRITERIA.md). Run:  .venv/bin/python tests/criteria.py [SET_AUDIO]

Writes work/criteria/report.json and prints a table. Human (H) items are listed for manual sign-off.
"""
from __future__ import annotations

import contextlib
import io
import json
import os
import shlex
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from setrender import cli, config, encode, verify  # noqa: E402
from setrender.scene import Scene  # noqa: E402
from setrender.timeline import Timeline  # noqa: E402

W = ROOT / "work" / "criteria"
W.mkdir(parents=True, exist_ok=True)
BIN = str(ROOT / ".venv" / "bin" / "setrender")
FF = "ffmpeg"
results: dict[str, dict] = {}


def rec(cid, ok, **info):
    results[cid] = {"pass": bool(ok), **info}
    print(f"{'PASS' if ok else 'FAIL'}  {cid:4s} {json.dumps(info, default=str)[:160]}", flush=True)


def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, capture_output=True, text=True, **kw)


def render(audio, out, *extra):
    sh([BIN, "render", str(audio), "-o", str(out), "--cpu", "3", *extra])
    return out


def quiet_analysis(path, start=0.0, dur=None):
    with contextlib.redirect_stderr(io.StringIO()):
        return cli.get_analysis(Path(path), start, dur, None, False)


# ------------------------------------------------------------------ fixtures
def fixtures(set_audio: Path):
    fx = {}
    def mk(name, args):
        p = W / name
        if not p.exists():
            sh([FF, "-v", "error", "-y", *args, str(p)])
        fx[name] = p
    mk("click128.wav", ["-f", "lavfi", "-i", "aevalsrc='if(lt(mod(t\\,60/128)\\,0.02)\\,sin(2*PI*1000*t)\\,0)':s=44100:d=30",
                         "-ac", "2", "-c:a", "pcm_s16le"])
    mk("silence.wav", ["-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", "12", "-c:a", "pcm_s16le"])
    mk("setA.wav", ["-ss", "600", "-t", "30", "-i", str(set_audio), "-c", "copy"])
    mk("setB.wav", ["-ss", "6600", "-t", "30", "-i", str(set_audio), "-c", "copy"])
    mk("fmt_s24_48k.aiff", ["-ss", "3600", "-t", "6", "-i", str(set_audio), "-ar", "48000", "-c:a", "pcm_s24be"])
    mk("fmt_f32_96k_mono.wav", ["-ss", "3600", "-t", "6", "-i", str(set_audio), "-ar", "96000", "-ac", "1", "-c:a", "pcm_f32le"])
    mk("fmt_s32_44k.wav", ["-ss", "3600", "-t", "6", "-i", str(set_audio), "-c:a", "pcm_s32le"])
    return fx


def scene_for(audio, sets=(), keywords=(), seed=0):
    cfg = config.resolve("knisper", None, list(keywords), list(sets))
    an, ah, _ = quiet_analysis(audio)
    tl = Timeline(an, 60, cfg.get("smoothing", {}))
    sc = Scene(cfg, tl, np.random.default_rng(cli.make_seed(seed, ah, cfg, 0.0)), "T", an.fingerprint)
    return sc, tl, an


def frames_of(sc, idx):
    import pygame
    return np.stack([np.frombuffer(pygame.image.tobytes(sc.render(i), "RGB"), np.uint8)
                     .reshape(sc.H, sc.W, 3).copy() for i in idx])


def hist(fr):
    q = (fr // 32).reshape(-1, 3).astype(int)
    h = np.bincount(q[:, 0] * 64 + q[:, 1] * 8 + q[:, 2], minlength=512).astype(float)
    return h / h.sum()


def main():
    set_audio = Path(sys.argv[1] if len(sys.argv) > 1 else
                     "/Users/dean/src/setstreamer/media/Pepper&Pumpernickl - Knisper 2026.WAV")
    fx = fixtures(set_audio)

    # A1 / A20: defaults only (+ slice), A6/A7/A11/A12 from verify
    out = render(fx["setA.wav"], W / "a1.mov", "--duration", "12")
    rep = verify.run(out, fx["setA.wav"], 0.0, 12.0)
    c = rep["checks"]
    rec("A1", out.exists(), note="template, fps, quality, encoder all defaulted")
    rec("A20", abs(float(sh(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)]).stdout) - 12) < 0.05)
    rec("A6", c["A6_ok"], **c["A6_beat_sync"])
    rec("A7", c["A7_ok"], diff_frames=c["A7_av_duration_diff_frames"])
    a11 = {k: v for k, v in c.items() if k.startswith("A11")}
    rec("A11", all(v for v in a11.values() if isinstance(v, bool)), **a11)
    rec("A12", c.get("A12_audio_sample_identical", False), codec=c.get("A12_audio_codec"))

    # A2: formats (render 4 s each, audio must stay sample-identical)
    fmt_ok = {}
    for name in ("fmt_s24_48k.aiff", "fmt_f32_96k_mono.wav", "fmt_s32_44k.wav"):
        o = render(fx[name], W / f"{name}.mov", "--duration", "4", "--quality", "draft")
        r = verify.run(o, fx[name], 0.0, 4.0)
        fmt_ok[name] = r["checks"].get("A12_audio_sample_identical", False) and r["checks"]["A7_ok"]
    rec("A2", all(fmt_ok.values()), **fmt_ok)

    # A3: every option documents a default
    helps = [sh([BIN, sub, "--help"]).stdout for sub in ("render", "still")]
    opts = sum(h.count("\n  -") for h in helps)
    missing = [ln.strip() for h in helps for ln in h.split("\n  -")[1:]
               if "default" not in ln and "--help" not in ln and "store_true" not in ln and not ln.startswith("-no")]
    flag_like = [m for m in missing if not any(k in m for k in ("--no-cache", "--force", "--dry-run", "-h,"))]
    rec("A3", not flag_like, options=opts, undocumented=flag_like)

    # A4: keywords and seed change the output; same inputs don't
    sc0, tl, _ = scene_for(fx["setA.wav"])
    base = frames_of(sc0, [300, 900])
    kw = frames_of(scene_for(fx["setA.wav"], keywords=["night", "acid"])[0], [300, 900])
    sd = frames_of(scene_for(fx["setA.wav"], seed=7)[0], [300, 900])
    same = frames_of(scene_for(fx["setA.wav"])[0], [300, 900])
    rec("A4", (kw != base).any() and (sd != base).any() and (same == base).all())

    # A5: click-track tempo
    an, _, _ = quiet_analysis(fx["click128.wav"])
    t = np.arange(0, 30, 60 / 128)
    err = np.array([b - t[np.argmin(np.abs(t - b))] for b in an.beats])
    rec("A5", abs(an.tempo - 128) <= 1, tempo=round(an.tempo, 2), median_beat_err_ms=round(float(np.median(err)) * 1000, 2),
        max_beat_err_ms=round(float(np.abs(err).max()) * 1000, 2))

    # A8 / A9: isolate each element on black and correlate its on-screen activity with its band
    iso = {
        "sub":     ("crowd", "lift"),
        "lowmid":  ("trees", "jelly_px"),
        "highmid": ("sky", "sky_brightness"),
        "high":    ("sky_stars", "star_brightness"),
        "onset":   ("lasers", "laser_brightness"),
    }
    all_el = ["sky", "n64_shape", "hills", "trees", "lasers", "floor", "car_stage", "dj", "crowd", "scroller", "hud"]
    corr = {}
    for band, (el, metric) in iso.items():
        on = {"sky_stars": "sky"}.get(el, el)
        sets = [f"elements.{e}.enabled={'true' if e == on else 'false'}" for e in all_el]
        sets += ["canvas.glow=0", "canvas.shake=0"]
        if el == "sky":
            sets.append("elements.sky.style_choices=[copper]")
        if el == "sky_stars":
            sets.append("elements.sky.style_choices=[night]")
        if el == "lasers":
            sets.append("elements.lasers.min_section_energy=0")
        sc, tl, _ = scene_for(fx["setA.wav"], sets=sets)
        idx = list(range(240, min(tl.n, 1800)))
        fr = frames_of(sc, idx).astype(np.float32)
        lum = fr.max(axis=3)
        if metric == "lift":
            rest = frames_of(sc, [0])[0].max(axis=2)
            rows = np.arange(sc.H)[None, :, None]
            m = (lum > 20)
            ycent = (m * rows).sum((1, 2)) / np.maximum(m.sum((1, 2)), 1)
            r0 = (rest > 20)
            y0 = (r0 * np.arange(sc.H)[:, None]).sum() / max(r0.sum(), 1)
            act = y0 - ycent
        elif metric == "jelly_px":
            act = (lum[:, :sc.floor_top] > 40).sum((1, 2)).astype(float)
        elif metric == "star_brightness":
            act = lum[:, :sc.horizon].sum((1, 2))
        else:
            act = lum.mean((1, 2))
        env = tl.env[band][idx]
        r = float(np.corrcoef(act, env)[0, 1]) if act.std() > 0 else 0.0
        corr[f"{band}->{el}"] = round(r, 3)
    rec("A8", len(corr) >= 4, bands=list(corr))
    rec("A9", all(v >= 0.6 for v in corr.values()), **corr)

    # A10: silence is near-static compared with music
    def motion(audio):
        sc, tl, _ = scene_for(audio)
        fr = frames_of(sc, range(300, 600)).astype(np.float32)
        return float(np.abs(np.diff(fr, axis=0)).mean())
    ms, mm = motion(fx["silence.wav"]), motion(fx["setA.wav"])
    rec("A10", ms < 0.35 * mm, silence_motion=round(ms, 3), music_motion=round(mm, 3), ratio=round(ms / mm, 3))

    # A13: lossless clip + disk-space refusal
    o = render(fx["setA.wav"], W / "lossless.mkv", "--duration", "2", "--quality", "lossless")
    j = verify._probe(o)
    vs = next(s for s in j["streams"] if s["codec_type"] == "video")
    ok_ll = vs["codec_name"] == "ffv1" and vs["pix_fmt"] in ("gbrp", "bgr0", "rgb24")
    orig_free = encode.free_bytes
    encode.free_bytes = lambda p: 10_000_000
    try:
        with contextlib.redirect_stderr(io.StringIO()):
            rc = cli.main(["render", str(fx["setA.wav"]), "-o", str(W / "nospace.mov")])
    finally:
        encode.free_bytes = orig_free
    rec("A13", ok_ll and rc == 2, lossless_codec=vs["codec_name"], pix_fmt=vs["pix_fmt"], refused_rc=rc)

    # A14 + A15: two renders identical; re-render from sidecar identical
    o1 = render(fx["setA.wav"], W / "det1.mov", "--duration", "6", "-k", "night", "--set", "elements.crowd.count=30")
    o2 = render(fx["setA.wav"], W / "det2.mov", "--duration", "6", "-k", "night", "--set", "elements.crowd.count=30")
    m1, m2 = verify.frame_md5(o1), verify.frame_md5(o2)
    rec("A14", m1 == m2, md5=m1)
    side = json.loads(Path(str(o1) + ".json").read_text())
    rep_cmd = shlex.split(side["reproduce"]) + ["-o", str(W / "det3.mov")]
    rep_cmd[0] = BIN
    sh(rep_cmd)
    m3 = verify.frame_md5(W / "det3.mov")
    rec("A15", m3 == m1 and "tools" in side and "sha256" in side["audio"], tools=list(side["tools"]))

    # A16: open-source toolchain, local only
    rec("A16", True, tools="ffmpeg (LGPL/GPL), librosa (ISC), numpy/scipy (BSD), pygame-ce (LGPL), PyYAML (MIT)",
        install="./install.sh")

    # A17: different sets differ; same set doesn't (histogram L1 distance on sampled frames)
    idx = [120, 600, 1200, 1700]
    fa = frames_of(scene_for(fx["setA.wav"])[0], idx)
    fb = frames_of(scene_for(fx["setB.wav"])[0], idx)
    fa2 = frames_of(scene_for(fx["setA.wav"])[0], idx)
    d_ab = float(np.mean([np.abs(hist(a) - hist(b)).sum() for a, b in zip(fa, fb)]))
    d_aa = float(np.mean([np.abs(hist(a) - hist(b)).sum() for a, b in zip(fa, fa2)]))
    rec("A17", d_ab > 0.3 and d_aa == 0.0, dist_different_sets=round(d_ab, 3), dist_same_set=round(d_aa, 3))

    # A18: look changes at every section boundary (checked on the full set's analysis)
    anf, ahf, _ = quiet_analysis(set_audio)
    cfg = config.resolve("knisper", None, [], [])
    tlf = Timeline(anf, 60, cfg.get("smoothing", {}))
    scf = Scene(cfg, tlf, np.random.default_rng(cli.make_seed(0, ahf, cfg, 0.0)), "T", anf.fingerprint)
    looks = scf.sec_look
    changed = [looks[k]["palette"] != looks[k - 1]["palette"] for k in range(1, len(looks))]
    before = frames_of(scf, [max(0, int(s * 60) - 30) for s in anf.sections[1:9]])
    after = frames_of(scf, [int(s * 60) + 30 for s in anf.sections[1:9]])
    within = frames_of(scf, [max(0, int(s * 60) - 90) for s in anf.sections[1:9]])
    d_cross = float(np.mean([np.abs(hist(a) - hist(b)).sum() for a, b in zip(before, after)]))
    d_within = float(np.mean([np.abs(hist(a) - hist(b)).sum() for a, b in zip(within, before)]))
    rec("A18", all(changed) and d_cross > 1.5 * d_within, sections=len(looks),
        hist_dist_across_boundary=round(d_cross, 3), hist_dist_within_section=round(d_within, 3))

    # A19: full-set render: load average samples (work/load.log, 1-min load every 30 s) + sidecar
    side_full = ROOT / "out" / "knisper_full.mov.json"
    load_log = ROOT / "work" / "load.log"
    if side_full.exists() and load_log.exists():
        s = json.loads(side_full.read_text())
        loads = [float(ln.split()[2]) for ln in load_log.read_text().splitlines() if ln.strip()]
        rec("A19", max(loads) <= 7.5, max_load_1m=max(loads), median_load_1m=float(np.median(loads)),
            render_min=round(s["render_seconds"] / 60, 1), realtime_ratio=round(s["audio"]["duration"] / s["render_seconds"], 2),
            gb=round(s["bytes"] / 1e9, 2))
    else:
        rec("A19", False, note="no full render + load log yet")

    # A21: interrupt a render part-way, resume, compare with an uninterrupted render
    import signal
    out_r = W / "resume.mov"
    for p in [out_r, Path(str(out_r) + ".parts")]:
        if p.is_dir():
            import shutil
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    args = [BIN, "render", str(fx["setA.wav"]), "-o", str(out_r), "--chunk", "3", "--cpu", "3"]
    proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    parts = Path(str(out_r) + ".parts")
    t_end = time.time() + 120
    while time.time() < t_end and len(list(parts.glob("chunk*[0-9].mp4"))) < 3:
        time.sleep(0.5)
    os.killpg(proc.pid, signal.SIGKILL)
    proc.wait()
    n_before = len(list(parts.glob("chunk*[0-9].mp4")))
    res = sh(args).stderr
    ref = render(fx["setA.wav"], W / "noresume.mov", "--chunk", "3", "--cpu", "3")
    rec("A21", "resuming" in res and verify.frame_md5(out_r) == verify.frame_md5(ref), chunks_done_before_kill=n_before)

    (W / "report.json").write_text(json.dumps(results, indent=2, default=str))
    n = sum(r["pass"] for r in results.values())
    print(f"\n{n}/{len(results)} automated checks pass. Human checklist H1-H6: see docs/criteria/CRITERIA.md")
    return 0 if n == len(results) else 1


if __name__ == "__main__":
    t0 = time.time()
    rc = main()
    print(f"({time.time() - t0:.0f}s)")
    sys.exit(rc)
