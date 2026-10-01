# setrender: completeness criteria for cropcircle.tpl (draft v1)

`cropcircle.tpl` shares the CLI, output format, reproducibility and performance rules of `CRITERIA.md`
(A1–A21). This file adds what is specific to the cropcircle brief. Each criterion is checked by an automated
test (`C`) or a human checklist (`H`). It is complete when every `C` passes and every `H` is ticked.
`tests/criteria_cropcircle.py` runs the automated checks and writes `work/criteria-cropcircle/report.json`.

## 1. Interface and output (shared rules applied to this template)
- C1. `setrender render <audio> -t cropcircle` works with everything else defaulted. Output passes A11 (H.264 High, yuv420p, BT.709, closed GOP, faststart, 1920x1080 at 60 fps) and A12 (PCM audio sample-identical to the source).
- C2. WAV and AIFF input at 16/24/32-bit and 44.1/48/96 kHz, mono or stereo, render with sample-identical audio (A2).
- C3. Keywords, `--set` and `--seed` change the result. The same inputs give identical frames (A4).

## 2. Beat sync
- C4. On a 60 s slice, the scene's brightness pulses within ±1 frame of at least 90% of the beats in bars where the kick plays, with a median offset of 0 frames. Video and audio durations differ by at most 1 frame (A6/A7, measured on the scene rather than a dancefloor region).
- C5. The same holds for the full 2 h render, with no drift at the end.

## 3. First-person camera that pans and zooms
- C6. Over the full set, the camera moves (position or angle) in at least 95% of frames. Its field of view spans at least 30°, at least 10 different kinds of shot are used, and at least 95% of cuts land within 1 frame of a downbeat, phrase start or drop.

## 4. Characters come and go and move around
- C7. Over the full set, the number of people on site varies (minimum below 70% of maximum). At least 90% of people walk to a new place at least once, the average person relocates at least 3 times, and every 10-minute window has at least one arrival and one departure.

## 5. Wind, jellyfish and the car stage
- C8. In bars with a kick, the wind strength correlates with the beat envelope (r ≥ 0.5). The jellyfish swing angle follows the wind (r ≥ 0.8).
- C9. In bars with a kick, the car's headlight brightness correlates with the sub-bass envelope (r ≥ 0.6). In breakdowns, the hazard lights blink on the beat.

## 6. Text, flags and symbols
- C10. The only text on screen is BPM and music stats. Every string the HUD draws over the full set uses only `BPM`, `BAR`, `PHR`, `KEY`, `LUFS`, `INF`, digits, Camelot codes, `.` `-` and the dance-arrow glyphs.
- C11. Identity flags appear and disappear. Over the full set there are at least 20 flag changes on the poles and at least 5 times the bunting goes up and comes down. All 12 identity flags in the cast are shown at least once.

## 7. Jokes, easter eggs and the Neural Engine
- C12. The on-device sound classifier (Core ML) covers the whole set with at least one result every 2 s. At least 8 distinct sound-triggered gags are scheduled for the Knisper set, and each starts within 2 s of the sound the classifier heard.
- C13. At least 25 distinct kinds of event happen over the full set, and at least 60% of the gags that can be framed get a camera shot that shows them.

## 8. Distinct, reproducible, resumable, fast enough
- C14. Two different sets differ measurably (colour-histogram distance above the A17 threshold on sampled frames), and the same set rendered twice is identical (A14/A17).
- C15. Re-running the command recorded in the sidecar reproduces the video frame for frame (A15). An interrupted render resumes and matches an uninterrupted one (A21).
- C16. The full 2 h 04 m set at 1080p60 renders with the machine's load average at or below about 7. Frames are drawn on the GPU (Metal), and the sidecar records the GPU adapter and the sound classifier.

## 9. Look and feel (human)
- H1. It feels first-person: walking, dancing, crowd-surfing, drone and close-ups, with panning and zooming that follow the music.
- H2. Characters come and go and change places, rather than bouncing on one spot for 2 hours.
- H3. Jellyfish hang in trees and blow in a wind that pulses with the beat. There are cornfields, an outdoor festival on a farm, and a parked car with headlights that move with the music, built into the DJ stage.
- H4. The only text is BPM and geeky music stats. Flags and identity symbols appear and disappear through the set.
- H5. It feels retro (pixel art, dither, CRT) and modern (real-time 3D on the GPU, volumetric beams, bloom, an on-device ML classifier).
- H6. There are easter eggs and cultural references that astute viewers get, and comedy in silly, rhythmic movements.
- H7. Styles mix: anime, gaming, underground music, geek, identity expression and psychedelic.
