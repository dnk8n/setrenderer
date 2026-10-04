# Criteria report: spume.tpl (2026-10-04)

Run with `.venv/bin/python tests/criteria_spume.py --full out/knisper_spume.mov --reel out/knisper_spume_highlights.mp4` on the trimmed Knisper set (`Pepper&Pumpernickl - Knisper 2026 (trimmed).WAV`, 1 h 55 m), against CRITERIA-spume.md draft v1.2. The render was made with `setrender render <set> -t spume -o out/knisper_spume.mov --cpu 6 --force` (commit 4b66111) and the reel with `setrender reel <set> -t spume --source out/knisper_spume.mov -o out/knisper_spume_highlights.mp4 --phone`.

**18/18 automated checks pass.**

| ID | Result | Evidence |
|---|---|---|
| S1 | pass | a minute of the set (`--start 3560 --duration 60`), otherwise defaults: H.264 High, yuv420p, BT.709, closed GOP, faststart, 1920x1080@60; PCM audio sample-identical |
| S2 | pass | 24-bit 48 kHz AIFF, 32-bit float 96 kHz mono WAV, 32-bit int WAV: audio sample-identical |
| S3 | pass | keywords, `--set` and seed change frames; same inputs give identical frames; a slice at 600 s draws the full render's frames |
| S4 | pass | 60 s slice: 100% of 21 kick beats pulse within ±1 frame, median offset 0 (the minute holds a breakdown) |
| S5 | pass | **full video: 99.9% of 8,703 kick beats pulse within ±1 frame, median offset 0; A/V differ by 0.2 frame; audio sample-identical** |
| S6 | pass | no text code in the engine; Apple Vision read something in 21 of 692 frames sampled every 10 s, all bubble chains (`00`, `10090000`, `0 0`...) or one-off jumbles; the only three-letter reading at confidence 0.5 (`DAC`) was not read again half a second either side |
| S7 | pass | Vision's face, human-body and animal detectors found nothing in any of the 692 frames |
| S8 | pass | 97.3% of 626 frames (every 10 s, away from transitions) show 3 or more levels of recursion (median 5); the dive never runs backwards |
| S9 | pass | kaleidoscope on 40.6% of the time, 162 switches, fold counts 3, 4, 5, 6, 8, 10 and 12, every switch on a downbeat; frames with it on match themselves turned by one fold at r ≥ 0.914, frames with it off at r ≤ 0.17 |
| S10 | pass | 16.0 million neighbouring-bubble pixel pairs checked, none with the same element; all eight elements in every 10-minute window; classifier result every 1.5 s; 214 surges covering all eight elements, each within 0.45 s of the sound |
| S11 | pass | soap-film colours from the spectral thin-film model; median saturation 0.652 over 688 frames; every minute covers all 12 hue sectors |
| S12 | pass | sub to films r = 0.993, bass to borders 1.000, high mids to elements 0.999, hats to sparkle 0.989, low mids to swirl 0.748; silence moves 4.1% as much as music |
| S13 | pass | 120 motif segments, every section changes the look on a downbeat, all six motifs, never twice in a row; 91 drops, each popping on the frame of its downbeat; 51 breakdowns slow the dive to at most 0.30 of the bars around them; all 88 builds wind up |
| S14 | pass | colour-histogram distance between two sets 0.84; same set 0.0 |
| S15 | pass | two renders identical; sidecar command reproduces it; a render killed after 3 chunks resumes and matches |
| S16 | pass | render 65.8 min (1.75x real time), 17.3 GB (20 Mbit/s), GPU: Apple M1 Pro via Metal, YUV made on the GPU; **1-min load median 3.3, max 5.6, 0 of 775 samples above 7** (`--cpu 6`, two jobs) |
| S17 | pass | every frame scanned: at most 3 general flashes in any second in any quarter of the screen (the limit, reached in 82 of 6,910 seconds, never exceeded); at most 1 red flash a second (5 in all) |
| S18 | pass | 11 clips of 2.67 s (29.3 s), every cut on a beat, the first bubble forming first and the last pop last, evenly spread (gaps 617 to 1,087 s), each clip's sound matches the set (r ≥ 0.98 at 48 kHz) |

## What changed after the first full run

The first full render (same day, commit f65fa9d) passed 15 of 18. Two failures were in how things were measured and are recorded in the criteria draft v1.2: S6 (the recogniser read "Dog" and "Dot" in rings of bubbles at 0.5 confidence and nothing half a second either side; a word now has to be read again) and S11 (saturation measured on 64x36 thumbnails was 0.43, on the frames themselves 0.64). The third was real: S17 found up to 7 flashes a second in places, caused by each bubble's soap film turning about a point far outside the bubble, so every step of the swirl slid its pattern a long way and the films flickered. That was fixed, the brightness swings of the sub, bass and high-mid layers were narrowed and slowed, and the kick pump softened (commit 4b66111); the bitrate fell from 30 to 20 Mbit/s with the flicker.

knisper, cropcircle and rubberhose are untouched: stills at 600 s and 3600 s are byte-identical before and after this work.

The human checklist H1 to H8 (look and feel) is yours to tick from `out/knisper_spume.mov` and `out/knisper_spume_highlights.mp4`.
