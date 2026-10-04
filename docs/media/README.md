# Screenshots

The images in the docs are real frames from setrender, compressed to JPEG (about 2.3 MB in total). They are the only images in the repository: renders, audio and other media stay out of git (see `.gitignore`), so keep additions few and small, around 100 to 300 KB each.

Most come from the trimmed Knisper 2026 set by Pepper & Pumpernickl. The tiles were labelled and joined with ffmpeg's `drawtext` and `xstack` filters at 640x360 per tile, and saved with `-q:v 4` or `5`.

| Image | Made from |
|---|---|
| `hero.jpg` | the three single stills below, side by side |
| `knisper.jpg` | `setrender still <set> --at 600` (knisper, untrimmed set) |
| `knisper-variations.jpg` | `setrender still <set> --at 1500 --title "Pepper & Pumpernickl - Knisper 2026"` with no keyword, `-k acid`, `-k c64`, `-k amiga`, `-k night,packed` and `--seed 7` |
| `cropcircle.jpg`, `cropcircle-moments.jpg` | frames from the cropcircle highlight reel of the full render (`setrender reel <set> -t cropcircle`) |
| `cropcircle-variations.jpg` | `setrender still <set> -t cropcircle --at 2400` with no change, `--set "elements.crowd.kinds={anime: 0.6}"`, `--set "elements.crowd.kinds={blocky: 0.6}"` and `-k anime` |
| `rubberhose.jpg` | `setrender still <set> -t rubberhose --at 600` |
| `rubberhose-moments.jpg` | the title card (`--at 2.5 --title "Pepper & Pumpernickl - Knisper 2026"`) and frames from the per-boss reel (`setrender reel <set> -t rubberhose --per-act --length 120`) |
| `rubberhose-grades.jpg` | `setrender still <set> -t rubberhose --at 600` with `--set film.grade=` `twostrip`, `mono` and `clean`, then `-k spooky` and `-k party` |
| `rubberhose-bosses.jpg` | six rubberhose stills from development of the round-three bosses, captioned |
| `spume.jpg` | a frame of the full spume render of the trimmed set at 3625 s (`ffmpeg -ss 3625 -i out/knisper_spume.mov -frames:v 1`), scaled to 1280x720 |
| `spume-motifs.jpg` | frames of the full spume render at 244.6, 315.4, 1138.6, 1868.6, 2547.9 and 2154.5 s, one per motif, labelled |
| `two-sets.jpg` | `setrender still` at 25 s on two 30-second clips of the set (from 10 minutes and 1 h 50 m), with knisper and rubberhose |

When a template's look changes, regenerate its images the same way so the docs stay true to what the code renders.
