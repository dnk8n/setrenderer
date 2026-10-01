"""setrender command line."""
from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
# keep numeric libraries single-threaded: the CPU budget is managed explicitly (see --cpu)
for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "MKL_NUM_THREADS", "NUMBA_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

from . import analysis, audio, config, encode

CACHE_DIR = Path(os.environ.get("SETRENDER_CACHE", Path.home() / ".cache" / "setrender"))


def log(*a):
    print(*a, file=sys.stderr, flush=True)


# ---------------------------------------------------------------- shared steps

def get_analysis(path: Path, start: float, duration: float | None, bands: dict | None, no_cache: bool):
    bands = bands or analysis.DEFAULT_BANDS
    log(f"hashing {path.name} …")
    ah = audio.file_hash(path)
    key = analysis.cache_key(ah, start, duration, bands)
    cpath = CACHE_DIR / f"analysis-{key}.npz"
    if cpath.exists() and not no_cache:
        log(f"analysis: cached ({cpath.name})")
        return analysis.load(cpath), ah, cpath
    log("analysis: running")
    t0 = time.time()
    a = analysis.analyse(path, start, duration, bands, log=log)
    analysis.save(a, cpath)
    log(f"analysis: done in {time.time() - t0:.1f}s, tempo {a.tempo:.1f} BPM, "
        f"{len(a.beats)} beats, {len(a.sections)} sections")
    return a, ah, cpath


def make_seed(user_seed: int, audio_hash: str, cfg: dict, start: float) -> int:
    s = json.dumps([user_seed, audio_hash, cfg.get("name"), sorted(cfg.get("_keywords", [])), round(start, 3)])
    return int(hashlib.sha256(s.encode()).hexdigest()[:15], 16)


def _title(path: Path, given: str | None) -> str:
    return given or path.stem


# ---------------------------------------------------------------- frame worker

def _render_chunks(job):
    """Render a list of chunks; each is piped into its own ffmpeg and renamed into place only when
    complete, so an interrupted render resumes from the last finished chunk."""
    (cache_path, cfg, fps, seed, title, chunks, vargs, in_wh, progress) = job
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import numpy as np
    import pygame

    from .scene import Scene
    from .timeline import Timeline
    an = analysis.load(Path(cache_path))
    tl = Timeline(an, fps, cfg.get("smoothing", {}))
    scene = Scene(cfg, tl, np.random.default_rng(seed), title, an.fingerprint)
    for (a, b, final) in chunks:
        final = Path(final)
        tmp = final.with_name(final.stem + ".tmp" + final.suffix)
        proc = subprocess.Popen(encode.segment_cmd(tmp, vargs, in_wh, fps), stdin=subprocess.PIPE)
        for i in range(a, b):
            proc.stdin.write(pygame.image.tobytes(scene.render(i), "RGB"))
            if (i - a) % 30 == 29:
                with progress.get_lock():
                    progress.value += 30
        proc.stdin.close()
        if proc.wait() != 0:
            raise SystemExit(f"ffmpeg failed on {tmp.name}")
        tmp.rename(final)
        with progress.get_lock():
            progress.value += (b - a) % 30
    return 0


def plan_budget(cpu: float, encoder: str, quality: str) -> tuple[int, int]:
    """Split a CPU budget (roughly the load average you allow) into parallel jobs and encoder threads.
    Each job = 1 Python renderer + 1 ffmpeg filter thread + its encoder."""
    if quality != "lossless" and encoder == "vt":
        return max(1, int(cpu // 2.5)), 1      # hardware encoder: ~0.5 core of driver work
    return 1, max(1, int(cpu) - 2)             # software encoder gets the rest of the budget


# ---------------------------------------------------------------- commands

def cmd_render(args) -> int:
    if args.nice:
        os.nice(max(0, min(20, args.nice)))  # inherited by render workers and ffmpeg
    src = Path(args.audio).expanduser().resolve()
    info = audio.probe(src, args.start, args.duration)
    cfg = config.resolve(args.template, args.params, _kw(args.keywords), args.set or [])
    fps = float(args.fps)
    out_wh = encode.parse_resolution(args.resolution)
    in_wh = (int(config.get_path(cfg, "canvas.width", 480)), int(config.get_path(cfg, "canvas.height", 270)))
    crt = float(config.get_path(cfg, "canvas.crt", 0.2))
    acodec = args.audio_codec
    ext = encode.container_for(args.quality, acodec)
    out = Path(args.output).expanduser() if args.output else Path("out") / f"{src.stem}.{cfg.get('name', 'render')}{ext}"
    out.parent.mkdir(parents=True, exist_ok=True)

    est = encode.estimate_bytes(args.quality, info.duration, out_wh, fps, info, acodec)
    free = encode.free_bytes(out.parent)
    tmp_factor = 2  # chunks + joined file exist together briefly
    log(f"input: {src.name}  {info.duration/60:.1f} min  {info.sample_rate} Hz {info.bits}-bit {info.channels}ch")
    log(f"output: {out}  {out_wh[0]}x{out_wh[1]} @ {fps:g} fps  quality={args.quality} encoder={args.encoder}")
    log(f"estimated size: {est/1e9:.1f} GB (free: {free/1e9:.1f} GB)")
    if est * tmp_factor > free * 0.95 and not args.force:
        log("setrender: not enough free disk space for this render. Use a lower --quality, "
            "a shorter --duration, or --force.")
        return 2
    if args.dry_run:
        return 0

    bands = cfg.get("bands")
    an, ah, cpath = get_analysis(src, args.start, args.duration, bands, args.no_cache)
    seed = make_seed(args.seed, ah, cfg, args.start)
    title = _title(src, args.title)
    n_frames = int(round(an.duration * fps))
    vargs = encode.video_args(in_wh, out_wh, fps, args.quality, args.encoder, args.crf, args.preset, crt)

    jobs, enc_threads = plan_budget(args.cpu, args.encoder, args.quality)
    vargs = encode.video_args(in_wh, out_wh, fps, args.quality, args.encoder, args.crf, args.preset, crt,
                              enc_threads=enc_threads)
    gop = max(1, int(round(fps / 2)))
    chunk_frames = max(gop, int(round(args.chunk * fps / gop)) * gop)
    parts = out.with_name(out.name + ".parts")
    manifest = {"v": 2, "audio": ah, "start": args.start, "duration": an.duration, "fps": fps, "res": out_wh,
                "vargs": vargs, "seed": seed, "chunk_frames": chunk_frames,
                "cfg": {k: v for k, v in cfg.items() if not k.startswith("_")}}
    mhash = hashlib.sha256(json.dumps(manifest, sort_keys=True, default=str).encode()).hexdigest()[:16]
    mfile = parts / "manifest.json"
    if parts.exists() and mfile.exists() and json.loads(mfile.read_text()).get("hash") != mhash:
        if not args.restart:
            log(f"setrender: {parts} holds a render with different settings; use --restart to discard it")
            return 2
        import shutil
        shutil.rmtree(parts)
    parts.mkdir(parents=True, exist_ok=True)
    mfile.write_text(json.dumps({"hash": mhash, **manifest}, indent=1, default=str))
    for stale in parts.glob("*.tmp.*"):
        stale.unlink()
    seg_ext = ".mkv" if args.quality == "lossless" else ".mp4"
    all_chunks = [(a, min(a + chunk_frames, n_frames), str(parts / f"chunk{k:05d}{seg_ext}"))
                  for k, a in enumerate(range(0, n_frames, chunk_frames))]
    todo = [c for c in all_chunks if not Path(c[2]).exists()]
    done_frames = n_frames - sum(b - a for a, b, _ in todo)
    if done_frames:
        log(f"resuming: {len(all_chunks) - len(todo)}/{len(all_chunks)} chunks already rendered")
    jobs = max(1, min(jobs, len(todo))) if todo else 1
    log(f"cpu budget {args.cpu:g}: {jobs} job(s), encoder threads {enc_threads}, nice {args.nice}, "
        f"{len(all_chunks)} chunks of {chunk_frames / fps:.0f}s")

    t0 = time.time()
    if todo:
        ctx = mp.get_context("spawn")
        prog = ctx.Value("i", 0)
        procs = []
        for j in range(jobs):
            p = ctx.Process(target=_render_chunks,
                            args=((str(cpath), cfg, fps, seed, title, todo[j::jobs], vargs, in_wh, prog),))
            p.start()
            procs.append(p)
        todo_frames = n_frames - done_frames
        _progress(lambda: prog.value, todo_frames, fps, t0, lambda: any(p.is_alive() for p in procs))
        for p in procs:
            p.join()
        if any(p.exitcode != 0 for p in procs):
            log("setrender: a render worker failed; rerun the same command to resume")
            return 1
    lst = parts / "list.txt"
    lst.write_text("".join(f"file '{Path(c[2]).name}'\n" for c in all_chunks))
    log("joining chunks with the audio …")
    subprocess.run(encode.mux_cmd(out, lst, info, args.start, info.duration, acodec), check=True)
    if not args.keep_parts:
        import shutil
        shutil.rmtree(parts)

    elapsed = time.time() - t0
    size = out.stat().st_size
    log(f"done: {out} ({size/1e9:.2f} GB) in {elapsed/60:.1f} min "
        f"({info.duration/elapsed:.2f}x real time)")
    sidecar = {
        "setrender_version": "0.1.0",
        "output": str(out), "bytes": size, "render_seconds": round(elapsed, 1),
        "audio": {"path": str(src), "sha256": ah, "start": args.start, "duration": info.duration,
                  "sample_rate": info.sample_rate, "bits": info.bits, "channels": info.channels},
        "analysis": {"cache": cpath.name, "tempo": an.tempo, "beats": int(len(an.beats)),
                     "sections": [round(float(s), 3) for s in an.sections], "fingerprint": an.fingerprint},
        "render": {"fps": fps, "resolution": out_wh, "internal": in_wh, "quality": args.quality,
                   "encoder": args.encoder, "crf": args.crf, "preset": args.preset, "audio_codec": acodec,
                   "seed": args.seed, "derived_seed": seed, "jobs": jobs, "cpu": args.cpu, "chunk_s": args.chunk, "title": title,
                   "keywords": cfg.get("_keywords", []), "set": args.set or [], "params": args.params},
        "template": {k: v for k, v in cfg.items() if not k.startswith("_")},
        "template_path": cfg.get("_template_path"),
        "tools": encode.tool_versions(),
        "reproduce": _repro_cmd(args),
    }
    Path(str(out) + ".json").write_text(json.dumps(sidecar, indent=2, default=str))
    return 0


def _repro_cmd(args) -> str:
    parts = ["setrender", "render", json.dumps(str(Path(args.audio).expanduser().resolve())),
             "-t", args.template, "--fps", str(args.fps), "--resolution", args.resolution,
             "--quality", args.quality, "--encoder", args.encoder, "--audio-codec", args.audio_codec,
             "--seed", str(args.seed), "--start", str(args.start), "--cpu", str(args.cpu),
             "--chunk", str(args.chunk)]
    if args.duration is not None:
        parts += ["--duration", str(args.duration)]
    if args.keywords:
        parts += ["--keywords", json.dumps(args.keywords)]
    for s in args.set or []:
        parts += ["--set", json.dumps(s)]
    if args.params:
        parts += ["--params", json.dumps(args.params)]
    if args.crf is not None:
        parts += ["--crf", str(args.crf)]
    if args.preset:
        parts += ["--preset", args.preset]
    if args.title:
        parts += ["--title", json.dumps(args.title)]
    return " ".join(parts)


def _progress(get, total, fps, t0, alive):
    last = 0.0
    while alive():
        time.sleep(0.5)
        now = time.time()
        if now - last < 5 and alive():
            continue
        last = now
        done = get()
        el = now - t0
        rate = done / el if el > 0 else 0
        eta = (total - done) / rate if rate > 0 else 0
        load = os.getloadavg()[0]
        log(f"  {done}/{total} frames  {rate:.0f} fps ({rate/fps:.2f}x)  eta {eta/60:.1f} min  load {load:.1f}")


def cmd_still(args) -> int:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    import numpy as np
    import pygame

    from .scene import Scene
    from .timeline import Timeline
    src = Path(args.audio).expanduser().resolve()
    cfg = config.resolve(args.template, args.params, _kw(args.keywords), args.set or [])
    an, ah, _ = get_analysis(src, args.start, args.duration, cfg.get("bands"), args.no_cache)
    fps = float(args.fps)
    tl = Timeline(an, fps, cfg.get("smoothing", {}))
    scene = Scene(cfg, tl, np.random.default_rng(make_seed(args.seed, ah, cfg, args.start)),
                  _title(src, args.title), an.fingerprint)
    out = Path(args.output or "still.png")
    frames = [int(float(x) * fps) for x in args.at.split(",")]
    for k, f in enumerate(frames):
        surf = scene.render(min(f, tl.n - 1))
        big = pygame.transform.scale(surf, (surf.get_width() * 4, surf.get_height() * 4))
        p = out if len(frames) == 1 else out.with_name(f"{out.stem}_{k:02d}{out.suffix}")
        pygame.image.save(big, str(p))
        log(f"wrote {p}")
    return 0


def cmd_analyze(args) -> int:
    src = Path(args.audio).expanduser().resolve()
    an, ah, cpath = get_analysis(src, args.start, args.duration, None, args.no_cache)
    print(json.dumps({"audio_sha256": ah, "cache": str(cpath), "duration": an.duration, "tempo": an.tempo,
                      "beats": int(len(an.beats)), "sections": [round(float(s), 2) for s in an.sections],
                      "section_energy": [round(float(e), 3) for e in an.section_energy],
                      "fingerprint": an.fingerprint}, indent=2))
    return 0


def cmd_templates(args) -> int:
    import yaml
    for p in config.list_templates():
        d = yaml.safe_load(p.read_text()) or {}
        print(f"{p.stem:12s} {p}\n    {' '.join(str(d.get('description', '')).split())}\n"
              f"    keywords: {', '.join((d.get('keywords') or {}).keys())}")
    return 0


def cmd_verify(args) -> int:
    from . import verify
    rep = verify.run(Path(args.video), Path(args.audio).expanduser() if args.audio else None,
                     start=args.start, duration=args.duration)
    print(json.dumps(rep, indent=2))
    return 0 if rep.get("pass") else 1


class _Help(argparse.HelpFormatter):
    """Show every option's default, including unset ones."""
    def _get_help_string(self, action):
        h = action.help or ""
        if "default" in h or action.default is argparse.SUPPRESS:
            return h
        if action.option_strings:
            d = {None: "none", False: "off", True: "on"}.get(action.default, "%(default)s")
            h += f" (default: {d})"
        return h


def _kw(s: str | None) -> list[str]:
    return [k.strip().lower() for k in (s or "").split(",") if k.strip()]


def _common(p, render=True):
    p.add_argument("audio", help="WAV or AIFF (anything ffmpeg can decode)")
    p.add_argument("-t", "--template", default="knisper", help="template name or path (default: knisper)")
    p.add_argument("--params", help="YAML file merged over the template")
    p.add_argument("--set", action="append", metavar="KEY=VALUE",
                   help="override one template value, e.g. --set elements.crowd.count=80 (repeatable)")
    p.add_argument("-k", "--keywords", help="comma-separated keywords, e.g. night,acid (template-defined looks; all keywords also seed variation)")
    p.add_argument("--seed", type=int, default=0, help="variation seed (default: 0; combined with the audio's hash)")
    p.add_argument("--start", type=float, default=0.0, help="start offset in seconds (default: 0)")
    p.add_argument("--duration", type=float, default=None, help="render only this many seconds (default: whole file)")
    p.add_argument("--fps", type=float, default=60, help="frame rate (default: 60)")
    p.add_argument("--title", help="title shown in the scroller (default: file name)")
    p.add_argument("--no-cache", action="store_true", help="re-run audio analysis even if cached")
    p.add_argument("-o", "--output", help="output file (default: out/<name>.<template>.mov)")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="setrender", description="Beat-synced music visualisation videos from DJ sets.",
                                 formatter_class=_Help)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="render a video", formatter_class=_Help)
    _common(r)
    r.add_argument("--resolution", default="1080p", help="720p, 1080p, 1440p, 2160p or WxH")
    r.add_argument("--quality", default="youtube", choices=["draft", "youtube", "high", "lossless"],
                   help="youtube = H.264 CRF16 + lossless PCM audio; lossless = FFV1 RGB + FLAC in MKV")
    r.add_argument("--encoder", default="vt", choices=["vt", "x264"], help="vt = Apple media engine (hardware, near-zero CPU); x264 = software, slightly better quality per bit")
    r.add_argument("--crf", type=float, default=None, help="override quality value (x264 CRF or VideoToolbox q)")
    r.add_argument("--preset", default=None, help="x264 preset override")
    r.add_argument("--audio-codec", default="pcm", choices=["pcm", "aac", "flac"], help="audio in the output")
    r.add_argument("--cpu", type=float, default=7,
                   help="CPU budget, roughly the load average the render may add (jobs and encoder threads fit inside it)")
    r.add_argument("--nice", type=int, default=10, help="process priority niceness (0-20, higher = gentler)")
    r.add_argument("--chunk", type=float, default=60, help="seconds per resumable chunk")
    r.add_argument("--restart", action="store_true", help="discard partial chunks rendered with different settings")
    r.add_argument("--keep-parts", action="store_true", help="keep the rendered chunks after joining")
    r.add_argument("--force", action="store_true", help="skip the free-disk-space check")
    r.add_argument("--dry-run", action="store_true", help="print the plan and size estimate only")
    r.set_defaults(func=cmd_render)

    s = sub.add_parser("still", help="render preview PNG(s) at given times", formatter_class=_Help)
    _common(s)
    s.add_argument("--at", default="30", help="comma-separated times in seconds")
    s.set_defaults(func=cmd_still)

    a = sub.add_parser("analyze", help="print the audio analysis")
    a.add_argument("audio")
    a.add_argument("--start", type=float, default=0.0)
    a.add_argument("--duration", type=float, default=None)
    a.add_argument("--no-cache", action="store_true")
    a.set_defaults(func=cmd_analyze)

    t = sub.add_parser("templates", help="list templates")
    t.set_defaults(func=cmd_templates)

    v = sub.add_parser("verify", help="measure a rendered video against the completeness criteria")
    v.add_argument("video")
    v.add_argument("--audio", help="source audio (enables sync checks)")
    v.add_argument("--start", type=float, default=0.0)
    v.add_argument("--duration", type=float, default=None)
    v.set_defaults(func=cmd_verify)

    args = ap.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
