# Templates

A template is a world for your set to play in. Pick one with `-t`, list them with `setrender templates`.

| | [knisper](knisper.md) | [cropcircle](cropcircle.md) | [rubberhose](rubberhose.md) |
|---|---|---|---|
| | <img src="../media/knisper.jpg" alt="knisper still" width="260"> | <img src="../media/cropcircle.jpg" alt="cropcircle still" width="260"> | <img src="../media/rubberhose.jpg" alt="rubberhose still" width="260"> |
| **The world** | an 8-bit underground rave around a burned-out car | a first-person night at a farm festival, sunset to sunrise | a 1930s rubber-hose cartoon boss rush, one boss per act |
| **Looks like** | 480x270 pixel art with glow and CRT scanlines | HD-2D: a 3D farm with pixel-art people, bloom and fog | hand-inked cartoon at full resolution through a film print |
| **Drawn on** | CPU (pygame-ce) | GPU (WebGPU on Metal) | GPU (WebGPU on Metal) |
| **Listens for** | beats, 5 bands, onsets, loudness, sections | all of that, plus key, LUFS and 303 kinds of sound | all of that, plus drops, breakdowns and sound-cued gags |
| **2 h set on an M1 Pro** | about 40 min, 12 GB | about 60 min, 19 GB | about 65 min, 10 GB |
| **Watch** | no video yet | [the whole Knisper set](https://youtu.be/DOuO45YCyCs) | [30 s reel](https://youtu.be/JZnURn199K0) · [2 min reel](https://youtu.be/d__gZC1iRnI) |
| **Keywords** | `night` `acid` `c64` `amiga` `minimal` `packed` `calm` `nolasers` | `aurora` `anime` `blocky` `packed` `intimate` `foggy` `clear` `frantic` `chill` `partytime` `retro` `hd` `smooth` `nohud` `dawn` | `twostrip` `mono` `clean` `pristine` `steady` `nohud` `short` `long` `frantic` `chill` `sky` `spooky` `classic` `party` `flawless` `hardcore` `nosidekicks` |

## What every template shares

- **One command.** `setrender render set.wav -t <name>` with everything else defaulted gives a YouTube-ready 1080p60 video with your original audio, untouched.
- **The beat is law.** Every template pulses on the beat to the frame: the automated checks measure a visual pulse within ±1 frame (16.7 ms) of at least 90% of the beats, and the full renders score 98.6% to 99.2%.
- **Your set, your look.** The set's own audio seeds the variation, so two sets never look the same, and the same set always renders the same video.
- **Keywords, `--set` and `--seed`.** Keywords switch on a bundled look, `--set path=value` changes any single value in the template, and `--seed` gives another take.
- **Resumable and polite.** One-minute chunks, a CPU budget, low priority, and a disk-space check before starting.

## Same moment, different sets

Two 30-second test sets cut from different hours of a mix, rendered with no settings changed:

<p align="center"><img src="../media/two-sets.jpg" alt="Two different test sets rendered at the same moment with knisper and rubberhose: different palettes, crowds, heroes and bosses" width="80%"></p>

## Make your own

Templates are YAML files in [`templates/`](../../templates/). Copy one and change it, or pass any `.tpl` file by path: `-t ~/my-world.tpl`. See [Make a template](../make-a-template.md).
