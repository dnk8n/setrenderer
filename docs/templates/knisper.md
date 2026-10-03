# knisper: an 8-bit underground rave

<p align="center"><img src="../media/knisper.jpg" alt="knisper: a pixel-art crowd waving pride flags in front of a burned-out car DJ stage, under a psychedelic plasma sky" width="100%"></p>

Retro gaming and 90s nostalgia, played as an underground rave. A burned-out car is the DJ stage, jellyfish hang in blocky trees, and a crowd of every kind bounces on a lit dancefloor: Minecraft-like blocky people, stick figures and NES-style sprites, with every skin tone, hair, outfit and gender presentation, some waving pride, trans and non-binary flags. The palettes, sky and floor nod to the Commodore 64, Amiga, Mega Drive, Nintendo 64 and NES, with a modern twist of glow, smooth motion and CRT scanlines.

```bash
setrender render set.wav            # knisper is the default template
setrender render set.wav -t knisper -k amiga
```

knisper is the default and the lightest template: it draws pixel art at 480x270 on the CPU and scales it up to 1080p with crisp nearest-neighbour pixels. A two-hour set renders in about 40 minutes on an M1 Pro.

## What moves to what

Every element listens to one part of the music. The wiring lives in the template's `mapping:` block, so you can rewire it (see [Make a template](../make-a-template.md)).

| On screen | Driven by | Why it feels right |
|---|---|---|
| crowd bouncing, speaker cones | sub bass (20 to 90 Hz) | the kick is what bodies move to |
| DJ | bass (90 to 250 Hz) | the bassline is what the DJ rides |
| tree sway, jellyfish pulse | low mids (250 Hz to 1 kHz) | pads and chords breathe slowly |
| raised arms, sky bars | high mids (1 to 4 kHz) | snares, claps and vocals |
| stars, jellyfish glow, flames | highs (4 to 11 kHz) | hi-hats and shakers sparkle |
| lasers | onsets | every new hit fires a beam |
| dancefloor pulse | the beat | lights flash on every beat, on the exact frame |
| colour hue | loudness | builds and drops shift the whole palette |

On a full two-hour set, 98.6% of 16,240 beats show a visual pulse within one frame, and each band's element follows its band with a correlation between 0.73 and 0.96 ([criteria report](../criteria/CRITERIA_REPORT.md)).

## How each set gets its own look

The set's audio fingerprint, combined with `--seed`, picks the palette order (`c64`, `nes`, `amiga`, `megadrive`, `n64`, `acid`, `vapor`), a sky style per section (copper bars, plasma, gradient, starfield), a floor per section (checker, grid, tiles), the trees and their jellyfish, and the crowd's make-up, positions and dance styles. The set's key rotates the starting palette, and its tempo, energy and sections drive the motion. The scene changes at every section boundary the analysis finds.

## Keywords

<p align="center"><img src="../media/knisper-variations.jpg" alt="Six versions of the same moment: default, acid, c64, amiga, night plus packed, and seed 7" width="100%"><br>
<sub>The same second with <code>-k acid</code>, <code>-k c64</code>, <code>-k amiga</code>, <code>-k night,packed</code> and <code>--seed 7</code>. Keywords also reshuffle the set's variation, so the crowd changes too.</sub></p>

| Keyword | What it does |
|---|---|
| `night` | night skies only: night, starfield or gradient |
| `acid` | acid, vapor and NES palettes, in that order |
| `c64` | Commodore 64 and NES palettes |
| `amiga` | Amiga and vapor palettes with copper-bar skies |
| `minimal` | a crowd of 20 and no lasers |
| `packed` | a crowd of 80 |
| `calm` | no screen shake and less glow |
| `nolasers` | no lasers |

Combine them with commas: `-k night,acid,packed`. Any other word you pass is not an error: it simply seeds a different variation.

## Things you can change with `--set`

A few useful ones (the full list is the template file, [`templates/knisper.tpl`](../../templates/knisper.tpl)):

```bash
--set elements.crowd.count=120             # how many people
--set "elements.crowd.types={stick: 1}"    # only stick figures
--set elements.crowd.flags=0.5             # half the crowd waves a flag
--set canvas.crt=0                         # no scanlines
--set canvas.glow=0.9                      # more bloom
--set elements.lasers.enabled=false        # switch any element off
--set "elements.scroller.messages=['{title} * {bpm} BPM * HELLO WORLD']"   # your own scroller
```

## Under the hood

| Stage | Tool | Notes |
|---|---|---|
| Decode | ffmpeg (soxr resampler) | any bit depth, rate or channel count |
| Analysis | librosa, NumPy, SciPy | five frequency bands, onsets, kick-weighted beat tracking in 90 s chunks (follows tempo drift), bars, sections (self-similarity novelty) and a set fingerprint, cached in `~/.cache/setrender` |
| Scene | pygame-ce (SDL) | pixel art at 480x270; every frame is a pure function of its index, so rendering is deterministic and parallel |
| Encode | ffmpeg and Apple VideoToolbox (the media engine) | nearest-neighbour upscale, CRT scanlines, H.264 High 4:2:0 BT.709, closed GOP, faststart, lossless PCM audio in MOV; `--encoder x264` for software encoding |

Measured on the full two-hour Knisper set: 38 minutes, a one-minute load average of at most 6.3, 12.2 GB, and audio sample-identical to the source.

**What "done" means for knisper:** [docs/criteria/CRITERIA.md](../criteria/CRITERIA.md), with the results in [CRITERIA_REPORT.md](../criteria/CRITERIA_REPORT.md).
