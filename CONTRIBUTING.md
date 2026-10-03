# Contributing to setrender

Thanks for wanting to help. setrender is a small project with big ambitions: any DJ set, any world, rendered beautifully, reproducibly and on your own machine. There is room for everyone, from someone who tried it on their set and has an opinion, to someone writing a new GPU engine.

- [Ways to contribute](#ways-to-contribute)
- [The ground rules](#the-ground-rules)
- [Set up for development](#set-up-for-development)
- [How the code is laid out](#how-the-code-is-laid-out)
- [Making a change](#making-a-change)
- [Checking your change](#checking-your-change)
- [Contributions made with AI](#contributions-made-with-ai)
- [Ideas to pick up](#ideas-to-pick-up)

## Ways to contribute

**No code needed**

- **Render your set and tell us how it went.** What looked great, what fell flat, where the beat felt off. An issue with a timestamp and a still is gold.
- **Report a bug** with the command you ran, what you expected, and the receipt (`out/<name>.mov.json`), which has every setting and tool version in it.
- **Pitch a world.** New templates start as a brief: describe the world, what should move to what, and what a viewer should feel. There is an issue form for it.
- **Improve the docs.** If something confused you, it will confuse the next person. Fixes to wording, examples and screenshots are very welcome.

**Code**

- fixes and small features to the CLI, analysis, encoding or reels,
- new keywords and options for an existing template,
- a new template in YAML (see [Make a template](docs/make-a-template.md)),
- a new engine, for a new kind of picture.

For anything bigger than a fix, please open an issue first so we can agree on the brief and its criteria before you put the hours in.

## The ground rules

These are what make setrender trustworthy. Every change keeps them:

1. **Every frame is a pure function of its index.** `frame(i)` depends only on `i`, the plan made from the analysis, and the settings: no state carried between frames, no wall clock, no unseeded randomness. This is what makes renders reproducible, parallel and resumable.
2. **Same inputs, same video.** The same audio, template, settings and seed must give bit-identical frames. Different sets must look measurably different.
3. **Free, open-source and local.** Only free, open-source tools, with nothing sent over the network at render time. Apple's on-device frameworks are fine as an optional extra (they ship with macOS and run locally).
4. **Kind to the machine.** A render stays within its `--cpu` budget (about a load of 7 on an 8-core Mac by default). Heavy work goes to the GPU or the media engine where possible.
5. **Criteria first.** A change with a visible or measurable effect comes with criteria that define it, and their automated checks pass. See [docs/criteria](docs/criteria/README.md).
6. **Don't break the neighbours.** Changing one template must leave the others' frames byte-identical (unless the change is meant to touch shared code, and then say so).
7. **No rich media in git.** Renders, audio, video and images stay out of the repository; `.gitignore` blocks them. The one exception is the small set of compressed screenshots in [`docs/media/`](docs/media/README.md).
8. **Original art.** rubberhose is inspired by 1930s cartoons and Cuphead but uses no one else's characters or assets. Keep it that way in every template.

## Set up for development

You need macOS on Apple Silicon (other platforms are untested, and reports are welcome), [Homebrew](https://brew.sh) and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/dnk8n/setrenderer.git && cd setrenderer
./install.sh                     # ffmpeg via Homebrew, Python 3.13 venv, pinned deps, editable install
source .venv/bin/activate        # optional: `setrender` instead of `.venv/bin/setrender`
setrender templates
```

The install is editable, so your edits take effect immediately. While developing, keep the analysis cache inside the repo, where it is ignored by git and easy to clear:

```bash
export SETRENDER_CACHE=work/cache
```

Output goes to `out/` and scratch work to `work/`, both ignored. For test audio, any long DJ set works; the criteria scripts expect one of about two hours.

## How the code is laid out

```
setrender/
├── install.sh, pyproject.toml, requirements.lock   install and pinned dependencies
├── templates/              knisper.tpl, cropcircle.tpl, rubberhose.tpl (YAML)
├── src/setrender/
│   ├── cli.py              commands, CPU budget, chunked resumable rendering, the receipt
│   ├── config.py           template loading and precedence (template < --params < -k < --set)
│   ├── audio.py            probing, hashing and decoding with ffmpeg
│   ├── analysis.py         bands, onsets, beats, bars, sections, fingerprint, cache
│   ├── timeline.py         per-frame signals every engine reads
│   ├── scenes.py           engine registry: make, prepare, gpu, native, pix_fmt
│   ├── encode.py           ffmpeg arguments, quality presets, joining and muxing
│   ├── reel.py             highlight reels
│   ├── verify.py           format, audio and beat-sync checks on a rendered video
│   ├── scene.py, sprites.py     the pixel engine (knisper)
│   ├── gpu/                shared wgpu engine, meshes, camera, shaders
│   ├── crop/               the cropcircle engine: world, cast, crowd, director, events, HUD, sound classifier
│   └── hose/               the rubberhose engine: story, combat, heroes, bosses, stages, gags, eggs, ink, shaders
├── tests/                  criteria check scripts, one per criteria file
└── docs/                   user and developer docs, criteria and reports, screenshots
```

[How it works](docs/how-it-works.md) explains the pipeline and [Make a template](docs/make-a-template.md#when-yaml-is-not-enough-a-new-engine) the engine contract.

## Making a change

1. **Agree on the brief** in an issue for anything non-trivial. For a new template or a visible feature, that includes draft criteria.
2. **Branch** from `main` and keep the change focused: one idea per pull request.
3. **Match the surrounding code.** Type hints and `from __future__ import annotations`, short docstrings that explain why rather than what, lines up to about 120 characters, NumPy for anything per-frame or per-sample, and no new dependency unless it clearly earns its place (if it does, add it to `pyproject.toml` and pin it in `requirements.lock`, which is what `install.sh` installs).
4. **Keep the docs true.** If you change an option, a keyword, an output or a look, update the [reference](docs/reference.md), the template page, and screenshots if they no longer match.
5. **Commit messages** follow the history: a short area, a colon, and what changed in plain words, e.g. `cropcircle: cuts snap to downbeats, gags get framed shots`.
6. **Open a pull request** that says what a viewer or user would notice before and after, how you checked it (commands, numbers, a still or two in the description), and the criteria results. The pull request template walks through it.

## Checking your change

**Quick look.** Stills are seconds once a set is analysed:

```bash
setrender still set.wav -t rubberhose --at 60,600,3600 -o work/look.png
```

**A slice with sync checks.**

```bash
setrender render set.wav -t cropcircle --start 600 --duration 30 -o work/slice.mov
setrender verify work/slice.mov --audio set.wav --start 600 --duration 30
```

**Neighbours unchanged.** Render stills of every template before and after your change and compare the bytes:

```bash
SET=/path/to/set.wav
for t in knisper cropcircle rubberhose; do setrender still "$SET" -t $t --at 600,3600 -o work/regress/before_$t.png; done
# ...make your change...
for t in knisper cropcircle rubberhose; do setrender still "$SET" -t $t --at 600,3600 -o work/regress/after_$t.png; done
for f in work/regress/before_*; do cmp -s "$f" "${f/before/after}" && echo "same     $f" || echo "CHANGED  $f"; done
```

**Determinism.** Render the same short slice twice and compare frame hashes: `ffmpeg -v error -i a.mov -map 0:v -f framemd5 - > a.md5` for each, then `diff a.md5 b.md5`.

**The criteria.** For changes to a template or to shared behaviour, run that template's check script ([how](docs/criteria/README.md#running-the-checks)) and include the summary in your pull request. Changes that affect two-hour behaviour (drift, load, planning) need a full render and the `--full` checks.

**Load.** Long renders print the load average with their progress. If your change makes rendering heavier, check that a full render still stays at or below about 7 on an 8-core Mac at the default `--cpu`.

## Contributions made with AI

AI coding agents are welcome here. This project itself was built with one, against the criteria in this repository. What matters is that a person stands behind every contribution.

- **You are accountable.** You have read and understood every line you submit, you have run it, and you can explain and defend it in review. "The agent wrote it" is not an answer to a review question.
- **Disclose it.** Say in the pull request which tool or agent you used and how much it did: human-written, AI-assisted (completion, refactoring, drafts) or AI-generated (an agent wrote most of it). A `Co-Authored-By` trailer is a welcome extra. Disclosure doesn't count against you; it helps reviewers know where to look.
- **Bring evidence, not volume.** Show the commands you ran and their output, stills, and criteria results. Pull requests that show no sign of having been run, or that change much more than the task needs, will be closed.
- **A human opens the door.** Agents should not open issues or pull requests, or comment on them, without a person reviewing and sending them. No unattended bulk changes.
- **Same rules for everyone.** Agent-made changes follow the ground rules above, including original art and no media in git.

Pointing an agent at this repo? It will find [AGENTS.md](AGENTS.md), which has the commands, the rules and how to verify work, written for agents.

## Ideas to pick up

Some open directions, roughly from small to large. Open an issue to claim one or to discuss it.

- **Try it beyond macOS.** knisper with `--encoder x264` may well run on Linux; find out what breaks.
- **A fast smoke test.** The criteria scripts need a two-hour set and take a while. A test suite that runs in a minute on synthetic audio (a click track, silence, a sweep) would make every change safer, and could run in CI.
- **More keywords** for the existing templates, each a small, well-defined look.
- **Vertical reels** for Shorts, Reels and TikTok.
- **A new template.** Write the brief and criteria first; the [issue form](https://github.com/dnk8n/setrenderer/issues/new/choose) helps.
- **Packaging**, so installing doesn't need a clone.

## Code of conduct

Everyone is welcome here: no dress code, no gender code, just bass. Please read the [code of conduct](CODE_OF_CONDUCT.md).

## License

A license has not been chosen yet. Until one is added, contributions can't be merged under clear terms, so please open an issue before starting substantial work.
