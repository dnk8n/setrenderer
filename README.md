# setrender

Turn a DJ set (WAV/AIFF) into a beat-synced, YouTube-ready music video, styled by a template.

```bash
./install.sh                                   # ffmpeg via Homebrew + local venv
.venv/bin/setrender render my_set.wav          # whole set -> out/my_set.knisper.mov
.venv/bin/setrender render my_set.wav --start 600 --duration 30   # preview a slice
.venv/bin/setrender still my_set.wav --at 60,600,3600             # PNG snapshots
.venv/bin/setrender templates                  # list templates and their keywords
.venv/bin/setrender verify out/my_set.knisper.mov --audio my_set.wav   # check sync/format
```

## How it works

| Stage | Tool | Notes |
|---|---|---|
| Decode | ffmpeg (soxr resampler) | any bit depth / rate / channel count |
| Analysis | librosa + numpy/scipy | 5 frequency bands, onsets, kick-weighted beat tracking in 90 s chunks (follows tempo drift), bars, sections (self-similarity novelty), set fingerprint. Cached in `~/.cache/setrender`. |
| Scene | pygame-ce (SDL) | pixel art at 480x270, every frame a pure function of the frame index, so rendering is deterministic and parallel |
| Encode | ffmpeg / x264 | nearest-neighbour upscale, CRT scanlines, H.264 High 4:2:0 BT.709, closed GOP, faststart, lossless PCM audio in MOV |

`--jobs N` splits the video into GOP-aligned segments rendered in parallel and joins them without re-encoding.

## Output presets

| `--quality` | Video | Audio (default) | Use |
|---|---|---|---|
| `youtube` (default) | H.264 CRF 16 | PCM, bit-identical to source | upload |
| `high` | H.264 CRF 12, preset medium | PCM | archival-ish upload |
| `draft` | H.264 CRF 26, veryfast | PCM | quick checks |
| `lossless` | FFV1 RGB in MKV | PCM | clips/masters (very large) |

`--audio-codec aac` gives a small MP4; `--encoder vt` uses the Apple VideoToolbox hardware encoder; `--resolution 1440p|2160p` for higher-res uploads (the pixel art scales by integer factors at 1080p and 2160p). The CLI estimates output size and refuses to start without enough disk (`--force` overrides).

## Templates

A template is a YAML `.tpl` file in `templates/`. It chooses scene elements, palettes, which audio band drives what, keywords, and how each set varies. Override anything without editing the file:

```bash
setrender render set.wav --keywords night,acid            # template-defined looks
setrender render set.wav --set elements.crowd.count=80 --set canvas.crt=0
setrender render set.wav --params my_overrides.yaml --seed 3
```

Precedence: template < `--params` < `--keywords` < `--set`. Every render writes `<output>.json` with the resolved parameters, audio hash, tool versions and a command that reproduces it exactly.

**Why sets look different:** the variation seed combines `--seed` with the audio's SHA-256, so palettes order, sky/floor style per section, crowd make-up, trees and jellyfish all differ per set. The set's key rotates the starting palette, and its tempo, energy and section structure drive the motion.

## Completeness

`CRITERIA.md` defines "done". `tests/criteria.py` runs every automated check and writes `work/criteria/report.json`.
