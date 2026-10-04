# setrender: completeness criteria for cymatics.tpl (draft v1, for review)

`cymatics.tpl` shares the CLI, output format, reproducibility and performance rules of `CRITERIA.md` (A1–A21).
This file adds what is specific to the cymatics brief (2026-10-04): a fifth template designed with full
artistic licence, clearly unlike the other four (8-bit rave, 3D farm festival, rubber-hose cartoon, psychedelic
foam). The design is sound made visible: a physics lab at night where every experiment is played by the set,
filmed like macro photography. Six stations take turns: sand gathering on the nodal lines of a Chladni plate,
Faraday waves in a dish, ferrofluid spikes, a Rubens tube of flames, water streams frozen into waves by a
strobe, and laser Lissajous figures drawing the chord of the key. The key's root note and its harmonics set the
modes, builds sweep the drive up an octave, drops overdrive the experiment, breakdowns let it rest, and each
section moves to the next station with a rack focus. It is finished like the other templates: a full render of
the trimmed Knisper set and a 30-second highlight reel.

This draft was written by the agent that built the template, for Dean to review: he owns how completeness is
measured, so any criterion can be tightened, loosened or dropped.

Each criterion is checked by an automated test (`K`, for Hans Jenny's *Kymatik*, the word cymatics comes from;
`C` is cropcircle's) or a human checklist (`H`). It is complete when every `K` passes and every `H` is ticked.
`tests/criteria_cymatics.py` runs the automated checks and writes `work/criteria-cymatics/report.json`.

## 1. Interface and output (shared rules applied to this template)
- K1. `setrender render <audio> -t cymatics` works with everything else defaulted. Output passes A11 (H.264 High, yuv420p, BT.709, closed GOP, faststart, 1920x1080 at 60 fps) and A12 (PCM audio sample-identical to the source).
- K2. WAV and AIFF input at 16/24/32-bit and 44.1/48/96 kHz, mono or stereo, render with sample-identical audio (A2).
- K3. Keywords, `--set` and `--seed` change the result. The same inputs give identical frames (A4, A14). A slice (`--start/--duration`) draws exactly the frames the full render has at those times.

## 2. Beat sync
- K4. On a 60 s slice of the set, the picture pulses within ±1 frame of at least 90% of the beats in bars where the kick plays, with a median offset of at most 1 frame (A6). Video and audio durations differ by at most 1 frame (A7).
- K5. The same holds for the full 2 h render, with no drift at the end, and its audio is sample-identical to the set.

## 3. The lab: six experiments
- K6. All six stations (Chladni plate, Faraday dish, ferrofluid, Rubens tube, frozen streams, laser Lissajous figures) appear in the Knisper set, each with between 8% and 30% of the time, and every 30-minute stretch shows all six. A station stays at least 16 bars, never follows itself and changes on a downbeat. Every section start changes the station, or the mode when it comes sooner than 16 bars after the last change (a change within 4 bars of the section start counts). A section change that isn't a drop is hidden in a rack focus: the frame holding the downbeat is the first of the new station, and it and the frame before it are fully out of focus.
- K7. The key sets the resonance: each mode's drive frequency is a whole-number harmonic (1 to 6) of the root of the key detected most often in its phrase (Camelot code to root, from the shared key detection), all six harmonics and at least six roots are used over the set, and every Chladni plate mode obeys Chladni's law: its nodal lines are among the four modes nearest the drive frequency (f ∝ n² + m² for the square plate, f ∝ (m + 2n)² for the round one).
- K8. The picture shows the physics, judged on settled frames every 10 s (away from drops, focus pulls and new modes): on the Chladni plate the sand lies on the nodal lines of the plate's mode (the picture's contrast against the bare plate is at least 3 times higher on the lines than away from them, median, and at least 1.5 times in every frame), and in the Rubens tube the flames stand in the mode's standing wave (each column's flame height against the wave predicted there, smoothed over about a hole's width: median r ≥ 0.6, every frame r ≥ 0.3; breakdowns, where the flames burn low and even by design, are not judged).

## 4. Following the music
- K9. Builds sweep the drive up an octave: the frequency multiplier rises steadily from the build's start to its end and ends at least 1.9 times higher. Breakdowns of 8 bars or more let the experiment rest: the picture moves less than half as much in the middle of the breakdown as 4 bars before it (same station, at least five breakdowns measured).
- K10. Every drop overdrives the experiment on the frame that holds its downbeat (the sand leaps and lands in a new pattern, the spikes shoot up, the flames roar, the streams shatter, the figures spin), and the picture moves at least 1.5 times as much in the half second after a drop as in the half second before it (median of the drops measured). Hard cuts to a new station happen only on drops.
- K11. At least five audio features each drive a different layer (kick: the experiment's jolt, an exposure lift and a camera turn; sub: the drive's amplitude; bass: the accent light; low mids: the camera's orbit and the patterns' drift; high mids: fine detail; highs: glints). With each layer driven alone and the picture held at one moment while one band plays through a minute of the set (a minute without a breakdown), its on-screen activity correlates with its band at r ≥ 0.6: flame brightness for the sub (Rubens tube), accent light for the bass (ferrofluid), glints for the highs and the sand's fizz for the high mids (Chladni plate), motion for the low mids (Faraday dish) (A8, A9). Silent input gives a near-static picture: under 35% of the motion with music (A10).

## 5. Distinct, reproducible, resumable, safe, fast enough
- K12. Two different sets differ measurably (colour-histogram distance above 0.3 on sampled frames), and the same set rendered twice is identical (A14, A17).
- K13. Re-running the command recorded in the sidecar reproduces the video frame for frame (A15). An interrupted render resumes and matches an uninterrupted one (A21).
- K14. The full Knisper set (1 h 55 m trimmed) at 1080p60 renders with the machine's load average at or below about 7 (every 1-minute sample in the render log at most 7.5). Frames are drawn on the GPU (Metal) and converted to YUV there; the sidecar records the GPU adapter and the key detection cache. Only free, open-source tools are used (A16).
- K15. Photosensitivity: across the full render, no one-second window has more than 3 general flashes (opposing luminance changes of at least 10% of full brightness over at least a quarter of the screen) or more than 3 red flashes (a quarter of the screen turning saturated red and back), following the Harding and WCAG 2.3.1 thresholds.

## 6. The highlight reel
- K16. `setrender reel <audio> -t cymatics` writes a reel of about 30 s (±2 s) made of 10 to 15 clips of 2 to 3 s each. Every cut lands on a beat (within 1 frame), the first clip shows the lights coming up on the first experiment, the last shows them going down, the clips in between are spread evenly through the set (each gap within ±50% of the average) at its salient moments (drops, new stations, new harmonics), all six stations appear, and each clip's audio is the set's own audio at that point (r ≥ 0.9).

## 7. Look and feel (human)
- H1. It reads as a real physics lab filmed in macro at night: sand, liquid, metal, fire, water and light look physical, with a shallow depth of field and dark surroundings.
- H2. Each experiment is recognisable: Chladni figures in sand, Faraday waves, ferrofluid spikes, a Rubens tube's flames, water frozen by a strobe, laser Lissajous figures.
- H3. The experiments are visibly played by the music: kicks jolt them, bass lights them, hats glint, builds tighten the patterns, drops overdrive them, breakdowns let them rest.
- H4. The rack focus between stations and the cuts on drops feel cinematic, not abrupt.
- H5. Two hours stay varied (materials, plate shapes, framings, modes), and different sets look different while staying true to the template.
- H6. It is clearly unlike knisper, cropcircle, rubberhose and spume, and everything in it is original (no copied artwork, logos or text).
- H7. The reel is a fair, punchy summary of the set.
