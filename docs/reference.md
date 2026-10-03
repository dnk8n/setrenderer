# Reference

Everything the command line accepts, what it writes, and where things live. `setrender <command> --help` prints the same options with their defaults.

- [Commands](#commands)
- [Options shared by render, still and reel](#options-shared-by-render-still-and-reel)
- [render](#render) · [still](#still) · [reel](#reel) · [analyze](#analyze) · [templates](#templates) · [verify](#verify)
- [Quality presets](#quality-presets)
- [Files setrender writes](#files-setrender-writes)
- [Template file keys](#template-file-keys)
- [Environment](#environment)

## Commands

| Command | What it does |
|---|---|
| `setrender render <audio>` | render a video |
| `setrender still <audio>` | render PNG snapshots at given times |
| `setrender reel <audio>` | cut a highlight reel: beat-length clips spread evenly at salient moments |
| `setrender analyze <audio>` | print the audio analysis as JSON |
| `setrender templates` | list templates, their descriptions and keywords |
| `setrender verify <video>` | measure a rendered video against the completeness criteria |

`<audio>` is a WAV or AIFF file (16, 24 or 32-bit, integer or float, any sample rate, mono or stereo), or anything else ffmpeg can decode.

## Options shared by render, still and reel

| Option | Default | Meaning |
|---|---|---|
| `-t, --template NAME_OR_PATH` | `knisper` | a template name from `templates/`, or a path to any `.tpl` file |
| `--params FILE` | none | a YAML file merged over the template |
| `--set KEY=VALUE` | none | override one template value by its dotted path, e.g. `elements.crowd.count=80`; the value is parsed as YAML; repeatable |
| `-k, --keywords LIST` | none | comma-separated keywords; known ones switch on template-defined looks, and all of them also seed the variation |
| `--seed N` | `0` | variation seed, combined with the audio's SHA-256 |
| `--start SECONDS` | `0` | start offset |
| `--duration SECONDS` | whole file | render only this many seconds |
| `--fps N` | `60` | frame rate |
| `--title TEXT` | file name | title shown in the video (knisper's scroller, rubberhose's title card, which also casts heroes it names) |
| `--no-cache` | off | re-run the audio analysis even if cached |
| `-o, --output PATH` | see each command | output file |

Precedence, last wins: template file, then `--params`, then `--keywords`, then `--set`.

## render

| Option | Default | Meaning |
|---|---|---|
| `-o, --output` | `out/<audio name>.<template>.mov` | `.mp4` with `--audio-codec aac`, `.mkv` with `--quality lossless` |
| `--resolution` | `1080p` | `720p`, `1080p`, `1440p`, `2160p` (or `4k`), or `WxH` |
| `--quality` | `youtube` | `draft`, `youtube`, `high` or `lossless`; see [quality presets](#quality-presets) |
| `--encoder` | `vt` | `vt` is Apple's media engine (hardware, near-zero CPU); `x264` is software, slightly better per bit |
| `--crf` | template's default | quality value: VideoToolbox q (1 to 100, higher is better) or x264 CRF (lower is better) |
| `--preset` | by quality | x264 preset |
| `--audio-codec` | `pcm` | `pcm` (lossless, same bit depth as the source), `aac` (384 kbit/s, 48 kHz) or `flac` |
| `--cpu` | `7` | CPU budget: roughly the load average the render may add; parallel jobs and encoder threads fit inside it |
| `--nice` | `10` | process niceness, 0 to 20 (higher is gentler) |
| `--chunk` | `60` | seconds per resumable chunk |
| `--restart` | off | discard partial chunks rendered with different settings |
| `--keep-parts` | off | keep the chunks after joining |
| `--force` | off | skip the free-disk-space check |
| `--dry-run` | off | print the plan and size estimate, then stop |

## still

| Option | Default | Meaning |
|---|---|---|
| `--at LIST` | `30` | comma-separated times in seconds |
| `-o, --output` | `still.png` | with several times, `_00`, `_01`... are added before the extension |

Stills are 1920x1080 PNGs (pixel-art templates are scaled up by whole pixels).

## reel

| Option | Default | Meaning |
|---|---|---|
| `-o, --output` | `out/<audio name>.<template>_highlights.mp4` | |
| `--length` | `30` | target length in seconds |
| `--clips` | 10 to 15, whichever fills `--length` best | number of clips including the title and the end |
| `--per-act` | off | one clip per act (each boss) on its best moment, plus a map walk and an intermission (rubberhose) |
| `--source` | `out/<audio name>.<template>.mov` if complete | the full render to cut from; without one, only the needed clips are rendered |
| `--cpu` | `7` | CPU budget when clips have to be rendered |
| `--nice` | `10` | niceness |
| `--q` | `62` | VideoToolbox quality for the reel |
| `--phone` | off | also write a 720p30 copy, `<output>_phone.mp4` |

## analyze

`setrender analyze <audio> [--start S] [--duration D] [--no-cache]` prints JSON: the audio's SHA-256, the cache file, duration, tempo, number of beats, section starts, section energy and the set fingerprint.

## templates

`setrender templates` lists every `.tpl` in `templates/` with its path, description and keywords.

## verify

`setrender verify <video> [--audio SOURCE] [--start S] [--duration D]` checks the format (H.264 High, yuv420p, progressive, BT.709, closed GOP, faststart, resolution and frame rate) and, with `--audio`, that the audio is sample-identical to the source, that picture and sound have the same length, and that the picture pulses on the beats. It prints a JSON report and exits with status 0 only if everything passes. Pass the same `--start` and `--duration` you rendered with when checking a slice.

## Quality presets

| `--quality` | Video (VideoToolbox / x264) | Container | Use |
|---|---|---|---|
| `draft` | q50 / CRF 26 veryfast | MOV | quick checks |
| `youtube` | q70 (templates can lower it: cropcircle 60, rubberhose 58) / CRF 16 faster | MOV | upload (default) |
| `high` | q80 / CRF 12 medium | MOV | archival-ish upload |
| `lossless` | FFV1 (RGB for knisper and cropcircle), every frame a keyframe | MKV | masters and clips (very large) |

Every preset except `lossless` writes H.264 High, 4:2:0, progressive, BT.709, a closed GOP of half a second and faststart, which is what YouTube recommends. Audio follows `--audio-codec` (lossless PCM by default).

## Files setrender writes

| Path | What |
|---|---|
| `out/<name>.<template>.mov` | the video (relative to the folder you run the command in) |
| `out/<name>.<template>.mov.json` | the receipt: audio hash, every resolved template value, tool versions, GPU, timing, and a `reproduce` command |
| `out/<name>.<template>.mov.parts/` | resumable chunks while rendering; removed after joining unless `--keep-parts` |
| `out/<name>.<template>_highlights.mp4` and `.json` | a reel and its clip list (`_phone.mp4` with `--phone`) |
| `work/reel/<name>.<template>/` | clips rendered for a reel when there is no full render |
| `~/.cache/setrender/analysis-*.npz` | cached analyses, keyed by audio hash and settings |
| `~/.cache/setrender/extras-*.npz` | cached sound-classifier, loudness and key results (cropcircle, rubberhose) |

## Template file keys

Templates are YAML. The keys every engine understands:

| Key | Meaning |
|---|---|
| `name` | the template's name, used in output file names |
| `engine` | `pixel` (the default, knisper's pygame engine), `cropcircle` or `rubberhose` |
| `description` | shown by `setrender templates` |
| `canvas` | internal resolution and finishing (`width`, `height`, `crt`, and engine-specific values) |
| `encode` | per-template encoder defaults: `vt_q`, `crf`, `est_mbps` (for the disk check) |
| `smoothing` | attack and release in seconds per audio feature: `sub`, `bass`, `lowmid`, `highmid`, `high`, `onset`, `loudness` |
| `bands` | optional frequency ranges in Hz per band, e.g. `{sub: [20, 90], ...}`; keep the names (engines refer to them); the first band decides where bars start |
| `mapping` | which feature drives which element (`{band: ..., gain: ...}`); read by the pixel engine, while the GPU templates use it to document their built-in wiring |
| `keywords` | each keyword maps dotted paths to values, exactly like a set of `--set` overrides (`palette_order` is a knisper shortcut) |

Engine-specific keys (`elements`, `palettes`, `variation`, `camera`, `sky`, `events`, `film`, `boil`, `story`, `bosses`, `hud`) are documented in each template file and on the [template pages](templates/README.md).

## Environment

| Variable | Meaning |
|---|---|
| `SETRENDER_CACHE` | where analyses are cached (default `~/.cache/setrender`) |
| `OMP_NUM_THREADS` and friends | setrender sets these to 1 itself, so numeric libraries don't oversubscribe the CPU budget |
