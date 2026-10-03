# Cookbook

Short recipes for things people do with setrender, roughly from first preview to production. Each one is a command you can copy. Commands are written as `setrender`; inside the repo folder that is `.venv/bin/setrender`, or run `source .venv/bin/activate` once. Put paths with spaces in quotes, or drag the file into the Terminal.

For every option and its default, see the [reference](reference.md).

- [Preview before you commit](#preview-before-you-commit)
- [Choose and tweak a look](#choose-and-tweak-a-look)
- [Output for YouTube, 4K, phones and archives](#output-for-youtube-4k-phones-and-archives)
- [Long renders, gently](#long-renders-gently)
- [Highlight reels](#highlight-reels)
- [Check, reproduce and inspect](#check-reproduce-and-inspect)
- [Many sets at once](#many-sets-at-once)

## Preview before you commit

**Snapshots at a few moments.** The fastest way to judge a look: a still takes a few seconds once the set is analysed.

```bash
setrender still set.wav -t cropcircle --at 60,900,3600,6000 -o out/look.png   # out/look_00.png ... look_03.png
```

**A short slice with sound.**

```bash
setrender render set.wav --start 1800 --duration 30          # 30 s from the 30-minute mark
setrender render set.wav --start 1800 --duration 30 --quality draft   # smaller and quicker to encode
```

For rubberhose, a slice draws exactly the frames the full render will have at those times, because it plans the whole set first. For knisper and cropcircle a slice is its own little render, analysed on its own, so it shows the look rather than the exact frames of the full render.

**How big will it be, and is there room?**

```bash
setrender render set.wav -t rubberhose --dry-run
# input: set.wav  115.2 min  44100 Hz 16-bit 2ch
# output: out/set.rubberhose.mov  1920x1080 @ 60 fps  quality=youtube encoder=vt
# estimated size: 13.3 GB (free: 76.7 GB)
```

## Choose and tweak a look

**Pick a template.** `-t knisper` (the default), `-t cropcircle` or `-t rubberhose`. `setrender templates` lists them with their keywords.

**Keywords** switch on looks the template defines. Combine them with commas:

```bash
setrender render set.wav -k night,acid
setrender render set.wav -t cropcircle -k aurora,packed,partytime
setrender render set.wav -t rubberhose -k mono,steady,hardcore
```

**Another take on the same set.** The variation seed combines `--seed` with the audio's own hash, so each seed is a different, repeatable version:

```bash
setrender still set.wav --at 1500 --seed 1 -o out/seed1.png
setrender still set.wav --at 1500 --seed 2 -o out/seed2.png
```

**Change any single value with `--set`.** Use the dotted path into the template file. Values are read as YAML, so numbers, `true`/`false`, lists `[a, b]` and maps `{a: 1}` all work (quote the whole argument when it has spaces or braces):

```bash
setrender render set.wav --set elements.crowd.count=80 --set canvas.crt=0
setrender render set.wav -t cropcircle --set "events.rates={conga: 6, ymca: 3}"
setrender render set.wav -t rubberhose --set "bosses=[kettle, hamhock, projectionist]" --set film.grade=twostrip
```

<p align="center"><img src="media/cropcircle-variations.jpg" alt="The same cropcircle moment four ways: default, --set anime-heavy crowd, --set blocky-heavy crowd (same shot), and -k anime (a different shot)" width="90%"></p>

**Keywords or `--set`?** A keyword is a named bundle of `--set` values, and it also feeds into the variation seed, so the set reshuffles (above, bottom right: `-k anime` gives a different camera shot). `--set` changes only the value you name, which is what you want when you are fine-tuning a look you already like (top right and bottom left keep the same shot). Any word you pass with `-k` that the template doesn't know is not an error: it just seeds a new variation, so `-k birthday` is a perfectly good way to get a fresh take with a name you will remember.

**Keep your tweaks in a file.** A params file is YAML merged over the template:

```yaml
# my-look.yaml
canvas:
  crt: 0
  glow: 0.8
elements:
  crowd:
    count: 70
    flags: 0.4
```

```bash
setrender render set.wav --params my-look.yaml
```

The order of precedence is: the template, then `--params`, then `--keywords`, then `--set` (last wins).

**Your own title.** `--title` replaces the file name in knisper's scroller and on rubberhose's title card, where it also casts the heroes it names:

```bash
setrender render set.wav -t rubberhose --title "Salt & Sugar live at the Barn"
```

## Output for YouTube, 4K, phones and archives

| Goal | Command |
|---|---|
| YouTube, best default (H.264 1080p60, lossless PCM audio, `.mov`) | `setrender render set.wav` |
| 4K upload (YouTube streams 4K at a higher bitrate) | `setrender render set.wav --resolution 2160p` |
| 1440p | `--resolution 1440p` |
| a small MP4 with AAC 384k audio | `--audio-codec aac` |
| FLAC audio instead of PCM | `--audio-codec flac` |
| 30 fps | `--fps 30` |
| a quick draft | `--quality draft` |
| more bits, for archiving an upload | `--quality high` |
| a mathematically lossless master (FFV1 in MKV, very large) | `--quality lossless` |
| software x264 instead of the Apple media engine (better per bit, far more CPU) | `--encoder x264 --cpu 7` |
| a specific encoder quality | `--crf 65` (VideoToolbox q, higher is better) or `--encoder x264 --crf 14 --preset slow` |
| your own file name | `-o "out/Knisper 2026.mov"` |

The pixel-art templates scale by whole-number factors at 1080p (4x for knisper, 3x for cropcircle) and 2160p, so pixels stay perfectly square there. rubberhose draws at the output resolution, so it is sharp at any size.

## Long renders, gently

**Stay under a load.** `--cpu N` is roughly the load average the render may add; it decides how many frames are drawn in parallel and how many threads the encoder gets. The default is 7 (for an 8-core Mac). `--nice 10` (the default) runs at low priority.

```bash
setrender render set.wav -t rubberhose --cpu 4        # while you work
setrender render set.wav -t cropcircle --cpu 7        # overnight
```

**Stop and resume.** Every minute of video is written to `out/<name>.mov.parts/` as it finishes. Press <kbd>Ctrl C</kbd>, close the lid, reboot: run the same command and it continues from the last finished chunk, frame-identical to an uninterrupted render.

```bash
setrender render set.wav -t rubberhose     # Ctrl C after a while...
setrender render set.wav -t rubberhose     # resuming: 23/116 chunks already rendered
```

If you change a setting in between, setrender refuses to mix the two and says so. Add `--restart` to discard the old chunks, or `-o` to render to a different file. `--chunk 30` makes chunks shorter (resume loses less), and `--keep-parts` keeps them after joining.

**Not enough disk?** The render estimates its size and refuses to start if it would not fit, asking for twice the estimate because the chunks and the final file exist together for a moment while joining. Use `--force` if you know there is room.

## Highlight reels

```bash
setrender reel set.wav -t knisper                          # about 30 s, 10 to 15 beat-length clips
setrender reel set.wav -t rubberhose --phone               # plus a 720p30 copy for phones
setrender reel set.wav -t rubberhose --per-act --length 30   # one clip per boss
setrender reel set.wav -t rubberhose --per-act --length 120  # a two-minute version, about 8 s a boss
setrender reel set.wav --length 60 --clips 20              # longer, with exactly 20 clips
```

Clips are 2 to 3 seconds and there are 10 to 15 of them unless you say otherwise, so for a regular reel longer than about 45 seconds, raise `--clips` too. `--per-act` reels stretch their clips to fill `--length`.

Every cut lands on a beat, the reel opens on the title and ends on the closing, and the clips in between are spread evenly through the set, each on the most salient moment of its stretch: drops, energy jumps, section starts, and whatever the template flags (rubberhose flags supers, knockouts, saves, lost takes and gags). The audio of each clip is the set's own audio at that point.

If the full render exists at `out/<name>.<template>.mov`, the reel is cut from it in about a minute. Otherwise it renders only the clips it needs. Point it at a render elsewhere with `--source path/to/render.mov`. Reels are written as `out/<name>.<template>_highlights.mp4` with a `.json` listing every clip and why it was chosen.

## Check, reproduce and inspect

**Check a video against the criteria.** `verify` measures the format, the audio and the beat sync, prints a JSON report and exits non-zero if anything fails:

```bash
setrender verify "out/set.knisper.mov" --audio set.wav
#   "A11_codec_h264_high": true, "A11_bt709": true, "A12_audio_sample_identical": true,
#   "A6_beat_sync": {"beats": 54, "hit_rate": 1.0, "median_offset_frames": 0.0}, ...
#   "pass": true
```

For a slice, pass the same `--start` and `--duration` you rendered with.

**Reproduce a render.** Every render writes a receipt next to it, `<output>.json`, with the audio's SHA-256, every resolved template value, the tool versions, the GPU, and a `reproduce` command that makes the same video again:

```bash
grep '"reproduce"' "out/set.rubberhose.mov.json"
```

**See what setrender heard.** `analyze` prints the tempo, beat count, section starts and their energy, and the set's fingerprint:

```bash
setrender analyze set.wav
```

Analyses are cached in `~/.cache/setrender`, keyed by the audio's hash. Set `SETRENDER_CACHE=/some/folder` to keep them elsewhere, and `--no-cache` to force a fresh analysis.

## Many sets at once

```bash
for f in ~/Music/sets/*.wav; do
  setrender render "$f" -t rubberhose --cpu 6 && setrender reel "$f" -t rubberhose --phone
done
```

Each set gets its own look from its own audio, and each output is named after its file, so nothing collides. If the loop is interrupted, running it again resumes the set it was on, but it would also render the finished ones again from scratch (their chunks are cleaned up after joining). To skip finished sets, check for the output first:

```bash
for f in ~/Music/sets/*.wav; do
  n=$(basename "${f%.*}"); [ -f "out/$n.rubberhose.mov" ] && continue
  setrender render "$f" -t rubberhose
done
```
