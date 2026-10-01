# setrender

Turn a DJ set (WAV/AIFF) into a beat-synced, YouTube-ready music video, styled by a template.

```bash
./install.sh                                   # ffmpeg via Homebrew + local venv
.venv/bin/setrender render my_set.wav          # whole set -> out/my_set.knisper.mov
.venv/bin/setrender render my_set.wav -t cropcircle   # first-person 3D farm festival (GPU)
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
| Encode | ffmpeg + Apple VideoToolbox (media engine) | nearest-neighbour upscale, CRT scanlines, H.264 High 4:2:0 BT.709, closed GOP, faststart, lossless PCM audio in MOV; `--encoder x264` for software encoding |

Rendering is split into 60 s chunks (`--chunk`), each written atomically, so an interrupted render resumes when you rerun the same command. `--cpu 7` (default) caps jobs and encoder threads to roughly that load average; `--nice` lowers priority.

## Output presets

| `--quality` | Video | Audio (default) | Use |
|---|---|---|---|
| `youtube` (default) | H.264, VideoToolbox q70 (or x264 CRF 16) | PCM, bit-identical to source | upload |
| `high` | H.264 CRF 12, preset medium | PCM | archival-ish upload |
| `draft` | H.264 CRF 26, veryfast | PCM | quick checks |
| `lossless` | FFV1 RGB in MKV | PCM | clips/masters (very large) |

`--audio-codec aac` gives a small MP4; `--encoder x264` uses the software encoder (better per bit, much more CPU); `--resolution 1440p|2160p` for higher-res uploads (the pixel art scales by integer factors at 1080p and 2160p). The CLI estimates output size and refuses to start without enough disk (`--force` overrides).

## Templates

A template is a YAML `.tpl` file in `templates/`. It chooses scene elements, palettes, which audio band drives what, keywords, and how each set varies. Override anything without editing the file:

```bash
setrender render set.wav --keywords night,acid            # template-defined looks
setrender render set.wav --set elements.crowd.count=80 --set canvas.crt=0
setrender render set.wav --params my_overrides.yaml --seed 3
```

Precedence: template < `--params` < `--keywords` < `--set`. Every render writes `<output>.json` with the resolved parameters, audio hash, tool versions and a command that reproduces it exactly.

**Why sets look different:** the variation seed combines `--seed` with the audio's SHA-256, so palettes order, sky/floor style per section, crowd make-up, trees and jellyfish all differ per set. The set's key rotates the starting palette, and its tempo, energy and section structure drive the motion.

## Templates in the box

| Template | Engine | Look |
|---|---|---|
| `knisper` | pygame (CPU), 480x270 pixel art | 8-bit underground rave: burned-out car stage, jellyfish trees, bouncing crowd, C64/Amiga/Mega Drive/N64/NES nods |
| `cropcircle` | WebGPU on Metal (GPU), 640x360 HD-2D | first-person night at a farm festival, sunset to sunrise: crop circles, jellyfish in a beat-gusting wind, a car built into the DJ stage, a crowd that comes and goes |

A template picks its scene engine with `engine:` (default: the pygame pixel-art engine).

### cropcircle

| Stage | Tool | Notes |
|---|---|---|
| Extra analysis | Apple SoundAnalysis built-in classifier (Core ML, on-device; Neural Engine capable), librosa, scipy | 303 sound classes every 1.5 s (cowbell, theremin, sax, vocals, scratching, laughter, phones...), LUFS (BS.1770 K-weighting), key per window in Camelot notation, 3-band waveform. One pass, about 50 s for a 2 h set, cached next to the analysis. |
| Scene | wgpu (WebGPU, Metal backend) | supersampled HDR 3D: instanced corn (30k plants) with crop circles laid in the vertex shader, low-poly farm, pixel-art billboards (front, back and side views), additive volumetric beams, height fog, bloom, ACES, 5-bit ordered dither, console filters |
| Direction | numpy | crowd schedules (arrive, dance, queue, sit, leave), camera shots cut on phrases and drops, events triggered by structure, sounds and bar numbers. Every frame is still a pure function of its index. |
| Encode | same as above | 640x360 upscaled 3x to 1080p, VideoToolbox q60 by default for this template |

It renders at about 150–190 fps with three jobs (`--cpu 7`), so a 2 h set takes about 45 minutes. The only text on screen is tempo and music stats: BPM, bar.beat, phrase, Camelot key, LUFS, a five-band meter and a CDJ-style waveform. Keywords: `aurora`, `anime`, `blocky`, `packed`, `intimate`, `foggy`, `clear`, `frantic`, `chill`, `partytime`, `retro`, `hd`, `smooth`, `nohud`, `dawn`.

Things to look out for: UFOs that lay crop circles through the night (one also turns up whenever the classifier hears a theremin), a cow with a cowbell when the classifier hears one, a sax player when it hears a sax, a vibing cat on the car roof, Tetris played with hay bales, the Konami code at bar 1337, someone missing at bar 404, portaloo doors that fly open on the beat, row-the-boat in long breakdowns, conga lines, YMCA, Pac-Man, a Nyan cat, a dancing hot dog and Game Boy/VHS/CGA filter moments.

## Completeness

`CRITERIA.md` defines "done" for the CLI and `knisper`; `tests/criteria.py` runs its automated checks and writes `work/criteria/report.json`. `CRITERIA-cropcircle.md` adds the cropcircle brief; `tests/criteria_cropcircle.py [--full out/<render>.mov]` writes `work/criteria-cropcircle/report.json`.
