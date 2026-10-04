# AGENTS.md

Instructions for AI coding agents working in this repository. Humans: the same rules are explained for people in [CONTRIBUTING.md](CONTRIBUTING.md).

## What this is

setrender is a Python CLI that turns a DJ set (WAV or AIFF) into a beat-synced, YouTube-ready video styled by a template. It analyses the audio (librosa), plans per-frame signals, draws every frame as a pure function of its index (pygame-ce on the CPU, or wgpu on Metal), and encodes in resumable one-minute chunks with ffmpeg and Apple VideoToolbox. Templates are YAML files in `templates/`: `knisper` (8-bit rave, CPU), `cropcircle` (3D farm festival, GPU), `rubberhose` (1930s cartoon boss rush, GPU), `spume` (recursive psychedelic foam, GPU) and `cymatics` (a night physics lab of sound made visible, GPU). It targets macOS on Apple Silicon.

## Setup and commands

```bash
./install.sh                                  # ffmpeg (Homebrew), uv venv in .venv, pinned deps, editable install
export SETRENDER_CACHE=work/cache             # keep analysis caches in the repo while developing (git-ignored)
.venv/bin/setrender templates                 # list templates and keywords
.venv/bin/setrender still <set> -t <template> --at 60,600,3600 -o work/look.png   # stills, seconds each
.venv/bin/setrender render <set> -t <template> --start 600 --duration 30 -o work/slice.mov
.venv/bin/setrender verify work/slice.mov --audio <set> --start 600 --duration 30  # exit 0 = format, audio and beat sync pass
.venv/bin/setrender render <set> -t <template> --dry-run                         # plan and size only
.venv/bin/python tests/criteria_rubberhose.py <set> --only R7,R9                 # a subset of a template's criteria
```

There is no unit-test suite; verification is stills, `verify`, and the criteria scripts in `tests/` (see below). Python is 3.13 in `.venv`; always call tools through `.venv/bin/`.

## Repository map

- `src/setrender/cli.py`: commands, CPU budget (`plan_budget`), chunked resumable rendering, the JSON receipt
- `src/setrender/config.py`: template loading; precedence is template < `--params` < `--keywords` < `--set`
- `src/setrender/analysis.py`, `timeline.py`: audio analysis (cached by audio hash) and per-frame signals
- `src/setrender/scenes.py`: engine registry; `scene.py` + `sprites.py` (pixel engine), `gpu/`, `crop/` (cropcircle), `hose/` (rubberhose), `spume/` (spume), `cymatics/` (cymatics)
- `src/setrender/encode.py`, `reel.py`, `verify.py`: ffmpeg arguments, highlight reels, video checks
- `templates/*.tpl`: the templates; `tests/criteria*.py`: criteria checks; `docs/`: user and developer docs
- `docs/criteria/`: what "done" means (`CRITERIA*.md`) and the latest results (`CRITERIA_REPORT*.md`)

## Hard rules

- **Frames are pure functions of their index.** Never carry state between frames, read the clock, or use unseeded randomness. All randomness comes from the seeded `numpy.random.Generator` passed to the scene, or from hashes of stable values. Plan anything history-dependent up front.
- **Never commit or push rich media.** No renders, audio, video or images; `.gitignore` blocks them. The only exception is a few compressed JPEG screenshots in `docs/media/` (100 to 300 KB each), and only when the task is about the docs.
- **Stay under a load average of about 7** on the maintainer's 8-core machine. Use `--cpu` (default 7; 6 for full rubberhose renders) and never run two heavy renders at once. Prefer stills and short slices over full renders.
- **Don't break other templates.** A change to one template must leave the others' frames byte-identical: render stills of every template at `--at 600,3600` before and after and compare with `cmp`.
- **Criteria files are the maintainer's.** Don't edit `docs/criteria/CRITERIA*.md` unless asked to. You may add or update a `CRITERIA_REPORT*.md` after a full criteria run, with the command you ran and its real results.
- **Only free, open-source, local tools.** No network access at render time, no paid services. Apple's on-device frameworks are an allowed optional extra.
- **Original art only.** rubberhose is in the spirit of Cuphead with original characters; never copy characters, assets or lettering from existing works.
- **Ask before** adding a dependency, changing a default that alters existing renders, deleting files in `out/`, or rewriting git history.

## How to verify a change

1. Stills of the template you changed, at a few moments, and look at them.
2. A 30-60 s slice and `setrender verify` on it.
3. The regression stills of every template (byte-identical unless the change is meant to touch them).
4. For template or shared changes, that template's criteria script. Full-set checks (`--full`) need a complete render: start long renders in the background with `nohup`, log progress to `work/full_render_<template>.log` (the load check reads it), and keep `--cpu` at 6 or 7.
5. Determinism if you touched planning or drawing: render a short slice twice and compare `ffmpeg -map 0:v -f framemd5` output.

Report what you ran and the actual numbers. If a check fails or was skipped, say so.

## Conventions

- Match the surrounding code: type hints, `from __future__ import annotations`, short docstrings that explain why, lines up to about 120 characters, NumPy for per-frame and per-sample work.
- Engines take `(cfg, tl, an, rng, title)` via `scenes.make`; one-off work goes in `scenes.prepare` and is cached in `SETRENDER_CACHE`.
- Template values are read with `config.get_path(cfg, "a.b.c", default)` with a default that matches the shipped template, so older templates and `--set` keep working.
- Commit messages: `area: what changed, in plain words` (e.g. `reel: pick from the middle of each stretch`). Keep commits focused.
- When options, keywords, outputs or looks change, update `docs/reference.md`, the template's page in `docs/templates/`, and screenshots that no longer match (see `docs/media/README.md`).

## Pull requests

- Describe what a viewer or user notices before and after, how you verified it (commands and real output), and the criteria results.
- Disclose that an agent made or helped with the change, and which one, as [CONTRIBUTING.md](CONTRIBUTING.md#contributions-made-with-ai) asks. A person must review and send every issue, pull request and comment; don't post them unattended.
