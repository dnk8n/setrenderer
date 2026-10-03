# setrender: completeness criteria for spume.tpl (draft v1)

`spume.tpl` shares the CLI, output format, reproducibility and performance rules of `CRITERIA.md` (A1–A21).
This file adds what is specific to the spume brief (2026-10-03): a fourth template with full artistic licence
that is pattern based, recursive and psychedelic ("I mean psychedelic psychedelic"), in vibrant colours, with no
characters and no letters; for example an alien depiction of foam in all its twisted forms, the endless colours
of water and soap films, fading in and out of kaleidoscopes, with the earth's elements inside alternating
bubbles. It is finished like the other templates: a full render of the trimmed Knisper set and a 30-second
highlight reel.

Each criterion is checked by an automated test (`S`) or a human checklist (`H`). It is complete when every `S`
passes and every `H` is ticked. `tests/criteria_spume.py` runs the automated checks and writes
`work/criteria-spume/report.json`.

## 1. Interface and output (shared rules applied to this template)
- S1. `setrender render <audio> -t spume` works with everything else defaulted. Output passes A11 (H.264 High, yuv420p, BT.709, closed GOP, faststart, 1920x1080 at 60 fps) and A12 (PCM audio sample-identical to the source).
- S2. WAV and AIFF input at 16/24/32-bit and 44.1/48/96 kHz, mono or stereo, render with sample-identical audio (A2).
- S3. Keywords, `--set` and `--seed` change the result. The same inputs give identical frames (A4, A14). A slice (`--start/--duration`) draws exactly the frames the full render has at those times.

## 2. Beat sync
- S4. On a 60 s slice, the picture pulses within ±1 frame of at least 90% of the beats in bars where the kick plays, with a median offset of at most 1 frame (A6). Video and audio durations differ by at most 1 frame (A7).
- S5. The same holds for the full 2 h render, with no drift at the end.

## 3. The brief: patterns only, recursive, psychedelic
- S6. No letters: nothing in the engine draws text, and Apple's on-device text recogniser (Vision, accurate mode) finds no text in frames sampled every 10 s across the full render.
- S7. No characters: Apple's on-device face, human-body and animal detectors (Vision) find nothing in at least 99% of the same sampled frames, and never in two samples in a row.
- S8. Recursive: in at least 95% of frames sampled across the full set, the picture shows patterns nested at least three levels deep (bubbles inside bubbles inside bubbles), read from the renderer's own depth layer. The camera dives continuously into the recursion: its zoom never runs backwards.
- S9. Kaleidoscopes fade in and out: over the full set the mirror symmetry is on for between 25% and 75% of the time, switches on or off at least 30 times, uses at least four different fold counts, and every switch starts on a downbeat. In sampled frames where it is on, the picture matches itself rotated by one fold (correlation at least 0.9); where it is off, it does not.
- S10. The elements: every bubble holds one of eight elements (fire, water, earth, air, metal, ice, lightning, magma), neighbouring bubbles never hold the same one, and all eight appear in every 10-minute window. The on-device sound classifier (Core ML) covers the whole set with a result at least every 2 s, and at least 6 element surges are cued by instruments it hears (brass to fire, keys to water, drums to earth...), each starting within 2 s of the sound.
- S11. Vibrant, endless colour: film colours come from a spectral thin-film interference model, the median saturation of sampled frames is at least 0.45, and every minute of the set covers at least 10 of 12 hue sectors (each holding at least 1% of the pixels).

## 4. Following the music
- S12. At least five audio features each drive a different layer of the picture (kick: bubble pulse and exposure; sub: film thickness and colour swell; bass: the glowing Plateau borders; low mids: the film's swirl; high mids: how fiercely the elements burn; highs: sparkle and fizz). Rendering each layer on its own over a 60 s slice, its on-screen activity correlates with its band at r ≥ 0.6 (A8, A9). Silent input gives a near-static picture (A10).
- S13. The structure is heard: the look (motif, fold count, palette) changes at every section start, on a downbeat, with no motif twice in a row and all six motifs in the Knisper set. Every drop lands with a pop within 1 frame of its downbeat. Breakdowns of at least 8 bars slow the motion to under half the speed of the bars around them, and builds wind up (zoom speed and saturation rise across the build).

## 5. Distinct, reproducible, resumable, safe, fast enough
- S14. Two different sets differ measurably (colour-histogram distance above the A17 threshold on sampled frames), and the same set rendered twice is identical (A14, A17).
- S15. Re-running the command recorded in the sidecar reproduces the video frame for frame (A15). An interrupted render resumes and matches an uninterrupted one (A21).
- S16. The full Knisper set (1 h 55 m trimmed) at 1080p60 renders with the machine's load average at or below about 7. Frames are drawn on the GPU (Metal) and converted to YUV there; the sidecar records the GPU adapter and the sound classifier. Only free, open-source tools are used (A16).
- S17. Photosensitivity: across the full render, no one-second window has more than 3 general flashes (opposing luminance changes of at least 10% of full brightness over at least a quarter of the screen) or any red flash, following the thresholds of the Harding and WCAG flash guidelines.

## 6. The highlight reel
- S18. `setrender reel <audio> -t spume` writes a reel of about 30 s (±2 s) made of 10 to 15 clips of 2 to 3 s each. Every cut lands on a beat (within 1 frame), the first clip shows the opening (the first bubble forming), the last shows the closing (the last pop), and the clips in between are spread evenly through the set (each gap within ±50% of the average) at its salient moments (drops, motif changes, kaleidoscopes, element surges). Each clip's audio is the set's own audio at that point.

## 7. Look and feel (human)
- H1. It is psychedelic psychedelic: trippy, alien and hypnotic, not a screensaver.
- H2. It reads as foam: bubbles, soap films and Plateau borders, with the endless colours of soap and water, twisting into weird forms.
- H3. It is recursive: bubbles inside bubbles, kaleidoscopes fading in and out, and an endless dive.
- H4. The elements are recognisable inside alternating bubbles.
- H5. It moves with the music: kicks, bass, hats, drops and breakdowns can be felt.
- H6. Two hours stay varied, and different sets look different while staying true to the template.
- H7. There are no characters, no letters and nothing that reads as a logo.
- H8. The reel is a fair, punchy summary of the set.
