# setrender: completeness criteria for crucible.tpl (draft v2, for review)

`crucible.tpl` shares the CLI, output format, reproducibility and performance rules of `CRITERIA.md` (A1–A21).
This file adds what is specific to the crucible brief (Dean, 2026-10-05, in four messages): a sixth template,
designed with full licence and clearly unlike the other five, that poses twenty environment challenges and
evolves creatures at render time to accomplish them. The music shapes each challenge (which trial a stretch of
the set gets, how its world is built, and the hazards the creatures face), so no two sets are alike. The
optimisers are real ones from the literature, through reference open-source implementations where they exist
(pycma, pyribs, neat-python, DEAP), over reinforcement learning, genetic and evolutionary algorithms, ant
colonies, particle swarms, quality diversity, neuroevolution, novelty search and self-play; the physics varies
between 2D, 3D, pixel-art games and game theory on a grid. Nothing is staged: all that is designed is the
world and how fitness is measured; creatures fail because the world is hard and succeed when evolution finds
a way. A world solved within a handful of generations was too easy, so it is made harder. Each success is shown
as a journey (its first generation, two from the middle, the generation just before success, then the
success); about 80% of the screen time goes to journeys that end in success and about 20% to runs that end in
a dead end. Every trial succeeds at least once, usually more often. Every new render is a new run of the
evolution, so the results are a surprise each time; a stopped render resumes its own run. It is finished like
the other templates: a full render of the trimmed Knisper set and a 30-second highlight reel.

This draft was written by the agent that built the template, for Dean to review: he owns how completeness is
measured, so any criterion can be tightened, loosened or dropped.

Each criterion is checked by an automated test (`E`, for evolution) or a human checklist (`H`). It is
complete when every `E` passes and every `H` is ticked. `tests/criteria_crucible.py` runs the automated checks
and writes `work/criteria-crucible/report.json`. Run numbers below are the `evolution.run` value recorded in
each render's receipt (sidecar JSON).

## 1. Interface and output (shared rules applied to this template)
- E1. `setrender render <audio> -t crucible` works with everything else defaulted. Output passes A11 (H.264 High, yuv420p, BT.709, closed GOP, faststart, 1920x1080 at 60 fps) and A12 (PCM audio sample-identical to the source).
- E2. WAV and AIFF input at 16/24/32-bit and 44.1/48/96 kHz, mono or stereo, render with sample-identical audio (A2).
- E3. Keywords, `--set` and `--seed` change the result. The same inputs with the same run number give identical frames (A4, A14). A slice (`--start/--duration`) draws exactly the frames the full render of the same run has at those times.

## 2. Beat sync
- E4. On a 60 s slice of the set, the picture pulses within ±1 frame of at least 90% of the beats in bars where the kick plays, with a median offset of at most 1 frame (A6). Video and audio durations differ by at most 1 frame (A7).
- E5. The same holds for the full 2 h render, with no drift at the end, and its audio is sample-identical to the set.

## 3. Twenty trials, chosen and built by the music
- E6. The Knisper set gets twenty trials, each a different one of the twenty, in an order the music decides: each stretch's measured character (energy, low end, brightness, percussion, vocals, key, breakdowns, drops) is matched to the trials' affinities, so the order is the best assignment of trials to stretches (no other order fits the music better), and two different sets get different orders. Each trial lasts between 2.5 and 9 minutes and starts on a downbeat.
- E7. The music builds the world. Every hazard or obstacle that is timed by the audio lands on its event within one frame (rocks land on kicks, pipes arrive on beats, traffic sets off on kicks, snares, hats and bass hits, hawks dive on snares, gusts of wind blow on hats, invaders arrive on bars and drops, walls move on drops), the soft-bodied creatures' muscles beat in phase with the detected beats, and the worlds made from the music follow it: the sprint's ground and the lander's mountains correlate with the stretch's loudness (r ≥ 0.9), and the swarm's and the summit's landscapes with its spectrum (r ≥ 0.9).

## 4. Evolution at render time, as it really happens
- E8. The evolution runs at render time: a render without a run number draws a fresh one, records it in the receipt and logs each trial's evolution before frames are drawn; two fresh renders of the same slice differ, and rendering again with the recorded run number reproduces the first exactly.
- E9. Every trial is solved on screen at least once. Every round's attempt, re-simulated from its genome in that round's music, ends exactly as shown (success, or the failure the overlay names), and every success round shows an attempt that reaches the goal.
- E10. Journeys and dead ends: each success is preceded by up to four ancestors from the same run (its first generation, two from the middle and the generation just before success, in that order, as room allows); dead ends show the run's first generation, three from the middle and its last, in the round whose music it never passed. Journeys to success take between 70% and 90% of the trials' round time (aim: 80%), dead ends the rest.
- E11. Honest evolution: every round shows the best individual of the generation it names, according to the evolution's own record; generations never go backward within a trial; a run is called a dead end only after its last generation without success; every run shown succeeding needed at least half the trial's minimum number of generations (a world solved faster was made harder first) unless its world was already at the hardest level or it was the trial's last chance; after a success the next run's world is harder; and the overlay's counts (attempts, solutions found) match the record.
- E12. Variety: at least 15 different optimisers are named on screen across the set, covering reinforcement learning, genetic algorithms, evolution strategies, swarm intelligence (ant colonies and particle swarms), quality diversity or novelty search, neuroevolution and self-play or game theory; and at least four kinds of world (2D physics, 3D physics, pixel-art games, grids or agents) with at least three different gravities.
- E13. Reference implementations: CMA-ES runs in pycma, MAP-Elites in pyribs (CMA-ME), NEAT in neat-python, and the genetic algorithms use DEAP's operators (checked on the optimisers the trials actually build).

## 5. Following the music (the picture's decor)
- E14. Five bands each drive a different layer (A8, A9): the floor glow (sub), the accent light (bass), the motes' drift (low mids), the motes' brightness (high mids) and the sparkles (highs); with each layer driven alone and the picture held at one moment while its band plays through a minute of the set, its on-screen activity correlates with the band at r ≥ 0.6. Silent input gives a near-static picture: under 35% of the motion with music (A10).

## 6. Distinct, reproducible, resumable, safe, fast enough
- E15. Two different sets differ measurably (colour-histogram distance above 0.3 on sampled frames), and the same set and run rendered twice is identical (A14, A17).
- E16. Re-running the command recorded in the sidecar reproduces the video frame for frame, run number included (A15). An interrupted render resumes the same run and matches an uninterrupted one (A21).
- E17. The full Knisper set (1 h 55 m trimmed) at 1080p60 renders with the machine's load average at or below about 7 (every sample in the render log, the evolution included, at most 7.5). Frames are drawn on the GPU (Metal) and converted to YUV there; the sidecar records the GPU adapter and the run. Only free, open-source tools are used (A16).
- E18. Photosensitivity: across the full render, no one-second window has more than 3 general flashes (opposing luminance changes of at least 10% of full brightness over at least a quarter of the screen) or more than 3 red flashes, following the Harding and WCAG 2.3.1 thresholds.

## 7. The highlight reel
- E19. `setrender reel <audio> -t crucible` writes a reel of about 30 s (±2 s) made of 10 to 15 clips of 2 to 3 s each, cut from the full render's run. Every cut lands on a beat (within 1 frame), the first clip shows the opening board, the last shows the hall of champions, the clips in between are spread evenly through the set (each gap within ±50% of the average), at least eight different trials appear, at least three clips show a success, and each clip's audio is the set's own audio at that point (r ≥ 0.9).

## 8. Look and feel (human)
- H1. It reads as a broadcast from an evolution lab: in every trial the goal, the creature and what went wrong are clear within a few seconds, and the overlay (trial, optimiser, generation, fitness chart, tally) helps rather than clutters.
- H2. The failures are varied, legible and often funny (flipping over, being crushed, dropping the egg, overshooting the pad), the journeys show real progress from the first generation to the solution, and the successes feel earned.
- H3. The music visibly shapes the trials: hazards on the beat, creatures walking to the beat, worlds that change with the set.
- H4. The creatures, games and worlds are original; the genre nods (a flappy bird, a snake, a frog crossing, a lander, a platformer) are original parodies with no copied characters, art or names.
- H5. Two hours stay varied (twenty different worlds and optimisers), and two different sets, or two renders of the same set, feel like different runs.
- H6. It is clearly unlike knisper, cropcircle, rubberhose, spume and cymatics.
- H7. The reel is a fair, punchy summary of the set.
