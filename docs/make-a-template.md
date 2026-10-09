# Make a template

There are two levels to making your own world. Most ideas only need the first.

1. **A new template** is a YAML file. You choose palettes, what listens to which part of the music, how many of everything there are, and keywords. No code. This page walks through one.
2. **A new engine** is Python that draws frame *i*. You need one for a new kind of picture (a new art style, a new camera, new characters). The [end of this page](#when-yaml-is-not-enough-a-new-engine) shows the contract, and [CONTRIBUTING.md](../CONTRIBUTING.md) the workflow.

## Your first template in ten minutes

We'll turn knisper into a seaside rave at dusk: a pastel palette, jellyfish that sparkle with the hi-hats and a crowd that bounces to the bassline.

**1. Copy a template.** Any file path works with `-t`, so you can keep your template anywhere:

```bash
cp templates/knisper.tpl ~/myrave.tpl
```

**2. Give it a name and a description.** The name is used in output file names (`out/<set>.myrave.mov`).

```yaml
name: myrave
description: >-
  My first world: a seaside rave at dusk, all pastels and bass.
```

**3. Set up a quick preview loop.** Stills take a few seconds, so you can tweak and look, over and over:

```bash
setrender still set.wav -t ~/myrave.tpl --at 60,900,2400 -o out/myrave.png && open out/myrave_00.png
```

**4. Add a palette.** Palettes are lists of hex colours. The engine takes the first as the darkest background colour and sorts the rest by brightness for skies, floors and accents, so a mix of darks, mids and brights works best (the built-in ones have 12):

```yaml
palettes:
  seaside: ["#0b1d3a", "#1e5f8c", "#4fb3bf", "#a7e8e0", "#f7d6bf", "#f29e8e",
            "#e8647a", "#ffffff", "#ffd166", "#06d6a0", "#118ab2", "#073b4c"]
  # ...keep or delete the others
```

**5. Rewire what listens to what.** Each entry in `mapping:` names a feature (`sub`, `bass`, `lowmid`, `highmid`, `high`, `onset`, `loudness` or `beat`) and a gain:

```yaml
mapping:
  crowd_bounce:  {band: bass, gain: 1.3}    # bounce to the bassline instead of the kick
  jellyfish:     {band: high, gain: 1.5}    # jellyfish sparkle with the hi-hats
```

How a feature reacts over time is set in `smoothing:` as attack and release in seconds: a short release makes things snap, a long one makes them glide.

**6. Add a keyword** that bundles your look. A keyword maps dotted paths to values, exactly like a set of `--set` overrides (`palette_order` is a shortcut that also turns off palette shuffling):

```yaml
keywords:
  seaside: {palette_order: [seaside, vapor, seaside], elements.sky.style_choices: [gradient]}
```

```bash
setrender still set.wav -t ~/myrave.tpl -k seaside --at 900 -o out/seaside.png
```

**7. Adjust the elements.** Everything under `elements:` can be resized, restyled or switched off with `enabled: false`: the crowd's size and make-up (`types: {blocky, stick, sprite}`), flags and glowsticks, trees and jellyfish per tree, sky and floor styles, lasers, smoke and flames on the car, and the scroller's messages (`{title}` and `{bpm}` are filled in).

**8. Decide how sets differ.** The `variation:` block says what the set's own seed is allowed to change: the palette order and whether to shuffle it, the crowd layout, and whether the sky and floor change with each section.

**9. Render.**

```bash
setrender render set.wav -t ~/myrave.tpl -k seaside --start 900 --duration 30
```

That's a new world. To use it by name (`-t myrave`), put it in `templates/`. To share it, open a pull request with the template and a still or two in the description ([CONTRIBUTING.md](../CONTRIBUTING.md)).

## Tweaking the GPU templates

cropcircle, rubberhose, spume, cymatics and crucible work the same way with their own keys: crowd size and kinds, events per hour, camera pace, fog and aurora (cropcircle); bosses, act length, attack rate, retakes, film grade, grain and line boil (rubberhose); motifs, dive speed, kaleidoscope share and folds, twist, film thickness and strength, saturation and the key's light (spume); stations, the minimum bars per station, harmonics, settle time, the camera's orbit, depth of field and materials (cymatics); the trials, chapters, chapter length and the evolution's run number (crucible). Their [template pages](templates/README.md) list the keys and the names you can use. Their `mapping:` blocks document the built-in wiring rather than control it (the GPU engines don't read them), so rewiring those means changing the engine. `smoothing:` works for every template.

## Make a world from a description

Templates are a good fit for coding agents. Something like this works well as a prompt in this repo:

> Make a new template `templates/neonsurf.tpl` based on knisper: a night surf contest, palettes from 80s surf posters, the crowd mostly stick figures waving towels, jellyfish following the highs, and keywords `dawn` and `stormy`. Check it with `setrender still` at three times on a test set and show me the stills.

[AGENTS.md](../AGENTS.md) tells agents how to work here.

## When YAML is not enough: a new engine

An engine is a Python class that draws one frame. The rules that keep setrender reproducible and resumable apply to every engine:

- **Each frame is a pure function of its index.** `frame(i)` may read the plan, the timeline and the settings, but nothing left behind by frame `i - 1`. Anything that depends on history (who is where, which fight is on) is planned up front, in the constructor, from the analysis.
- **All randomness comes from the seeded generator** handed to the constructor (or from hashes of stable values). Never the clock, never `random` without a seed.
- **Expensive one-off work** (extra analysis, a classifier pass) goes in a `prepare` step that runs once in the parent process and caches its results.

The wiring lives in [`src/setrender/scenes.py`](../src/setrender/scenes.py):

| Function | What an engine adds there |
|---|---|
| `make(cfg, tl, an, rng, title)` | construct your scene; it receives the resolved template, the per-frame `Timeline`, the `Analysis`, the seeded generator, the title (and `an.fingerprint`) |
| `prepare(cfg, src, audio_hash, start, cache_dir, log)` | one-off work before rendering; returns a dict recorded in the receipt |
| `gpu(cfg)` | whether the engine draws on the GPU (it gets a slightly different CPU budget) |
| `native(cfg)` | whether it draws at the output resolution in absolute set time (slices equal the full render) |
| `pix_fmt(cfg)` | what `frame(i)` returns: `rgb24` or `rgba` bytes at the canvas size, or `nv12` at the output size |
| `highlight_hints` / `highlight_acts` | optional: moments the reel should prefer |

What the `Timeline` gives you for frame `i`: `env[band][i]` for each band, `onset`, `loudness` and `beat` (all 0 to 1, smoothed), `beat_phase[i]`, `since_beat[i]`, `beat_idx[i]`, `bar_idx[i]` and `bar_env[i]`, `section_idx[i]`, `section_energy[i]` and `since_section[i]`, plus `tempo`. The three existing engines are worked examples: [`scene.py`](../src/setrender/scene.py) (pygame), [`crop/`](../src/setrender/crop/) and [`hose/`](../src/setrender/hose/) (wgpu).

Before writing an engine, write down what "done" means for it as a criteria file, the way each template has one in [docs/criteria](criteria/README.md). [CONTRIBUTING.md](../CONTRIBUTING.md) explains the workflow.
