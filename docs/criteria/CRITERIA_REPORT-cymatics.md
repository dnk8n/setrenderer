# Criteria report: cymatics.tpl (2026-10-04)

Run with `.venv/bin/python tests/criteria_cymatics.py "<set>" --full out/knisper_cymatics.mov --reel out/knisper_cymatics_highlights.mp4` on the trimmed Knisper set (`Pepper&Pumpernickl - Knisper 2026 (trimmed).WAV`, 1 h 55 m), against CRITERIA-cymatics.md draft v1. The render was made with `setrender render <set> -t cymatics -o out/knisper_cymatics.mov --cpu 6 --restart` from the code in commit 43ddc2a, and the reel with `setrender reel <set> -t cymatics --source out/knisper_cymatics.mov -o out/knisper_cymatics_highlights.mp4 --phone`. The run took 44 minutes.

**16/16 automated checks pass.**

| ID | Result | Evidence |
|---|---|---|
| K1 | pass | a minute of the set (`--start 3560 --duration 60`), otherwise defaults: H.264 High, yuv420p, BT.709, closed GOP, faststart, 1920x1080@60; PCM audio sample-identical |
| K2 | pass | 24-bit 48 kHz AIFF, 32-bit float 96 kHz mono WAV, 32-bit int WAV: audio sample-identical |
| K3 | pass | keywords, `--set` and seed change frames; same inputs give identical frames; a slice at 600 s draws the full render's frames |
| K4 | pass | 60 s slice: 100% of 21 kick beats pulse within ±1 frame, median offset 0 |
| K5 | pass | **full video: 99.8% of 8,703 kick beats pulse within ±1 frame, median offset 0; A/V differ by 0.2 frame; audio sample-identical** |
| K6 | pass | 99 stations: chladni 12.8% of the time, faraday 18.3%, ferrofluid 18.5%, lissajous 17.1%, rubens 18.6%, stream 14.6%; all six in every 30-minute stretch; never the same twice in a row; shortest 29.1 s (16 bars); every change on a downbeat; all 79 sections change the station or the mode; all 70 rack focus changes hidden (the downbeat's frame is the new station, it and the frame before fully out of focus) |
| K7 | pass | 452 modes, every one a whole-number harmonic (1 to 6, all used) of the root of the key detected most often in its phrase; all 12 roots used; all 58 plate modes among the four nearest by Chladni's law |
| K8 | pass | Chladni plate, 60 settled frames: the sand's contrast is 9.5 times higher on the mode's nodal lines than off them (median; at least 5.1 in every frame). Rubens tube, 25 frames: flame heights follow the mode's standing wave at r = 0.77 (median; at least 0.64) |
| K9 | pass | all 88 builds sweep the drive up an octave, steadily; 12 breakdowns measured: the picture moves 0.18 as much as 4 bars before (median; at most 0.41) |
| K10 | pass | 91 drops, each overdriving the experiment on the frame of its downbeat; the picture moves 2.2 times as much in the half second after a drop (median); 28 hard cuts, all on drops |
| K11 | pass | sub to flame height (Rubens) r = 1.000, bass to the accent light (ferrofluid) 1.000, highs to glints (Chladni) 0.998, high mids to the sand's fizz (Chladni) 1.000, low mids to the drift (Faraday) 0.973; silence moves 25% as much as music |
| K12 | pass | colour-histogram distance between two sets 1.57; same set 0.0 |
| K13 | pass | two renders identical; the sidecar's command reproduces it; a render killed after 3 chunks resumes and matches |
| K14 | pass | render 54.4 min (2.12x real time), 5.08 GB (5.9 Mbit/s), GPU: Apple M1 Pro via Metal, YUV made on the GPU, key detection cached; **1-min load median 4.4, max 6.3, 0 of 644 samples above 7** (`--cpu 6`, two jobs) |
| K15 | pass | every frame scanned: at most 3 general flashes in any second in any quarter of the screen (the limit, reached in 6 of 6,910 seconds, never exceeded); no red flashes |
| K16 | pass | 11 clips of 2.67 s (29.3 s), every cut on a beat, the lights coming up first and going down last, evenly spread (gaps 617 to 946 s), all six stations shown, each clip's sound matches the set (r ≥ 0.98) |

## What changed after the first full run

The first full render (same day, same plan) passed 13 of 16. All three failures were real and were fixed in the code before the render above:

- **K4 and K5, beat sync (57% of kicks on the slice, 86.6% over the set).** Three causes. In dark frames the hardware encoder dropped the kick's 8% brightness lift (a 0.7-level change in a frame averaging 17 came out of the encoder unchanged), so the kick now also lifts the shadows and mid-tones by up to 25% in display space, never the highlights. The Faraday dish flipped its waves on the beat by passing through a flat surface, which mirrored the softbox as one big patch of light a few frames after the beat; the waves now slide half a wavelength instead and never go flat. And swelling the waves on the kick darkened the liquid-metal dish, cancelling the lift, so the kick shows there only as the flip and a ring.
- **K15, flashes (up to 5 in a second, 5,441 in all).** Mostly the flat-dish flip above, plus large areas lit by the bass (the ferrofluid's light table and the streams' backlight) swinging with a fast attack, and the all-green scope lasers jumping on the kick. The bass now rises over 80 ms and falls over 0.5 s, the large lit areas swing less, the laser kick and trace head are gentler, and the green scope is dimmer. 1,100 flashes in all now, at most 3 in a second.

The fixes were checked on 40 to 60 s slices of each affected station before the full render (100% of kicks in sync, at most 2 flashes a second on those slices). knisper, cropcircle, rubberhose and spume are untouched: stills at 600 s and 3600 s are byte-identical before and after this work.

The human checklist H1 to H7 (look and feel) is yours to tick from `out/knisper_cymatics.mov` and `out/knisper_cymatics_highlights.mp4`.
