# setrender: completeness criteria for rubberhose.tpl (draft v2)

`rubberhose.tpl` shares the CLI, output format, reproducibility and performance rules of `CRITERIA.md`
(A1–A21). This file adds what is specific to the rubberhose brief: a third template with full creative
licence that mimics the look and feel of Cuphead, free and open source, plus a 30-second highlight reel.
Draft v2 (2026-10-03) adds the fight mechanics brief: hearts and super cards per hero, boss shots that do
damage, EX shots and Super Arts, deaths, ghosts and revives by parrying, restarts after a lost take with
every boss beaten exactly once, more visible boss damage, and an easter egg every minute (R7, R9 and R10
updated; R16 to R18 new; H4 and H5 updated). The Knisper set is now the trimmed file
(`Pepper&Pumpernickl - Knisper 2026 (trimmed).WAV`).
Each criterion is checked by an automated test (`R`) or a human checklist (`H`). It is complete when every
`R` passes and every `H` is ticked. `tests/criteria_rubberhose.py` runs the automated checks and writes
`work/criteria-rubberhose/report.json`.

## 1. Interface and output (shared rules applied to this template)
- R1. `setrender render <audio> -t rubberhose` works with everything else defaulted. Output passes A11 (H.264 High, yuv420p, BT.709, closed GOP, faststart, 1920x1080 at 60 fps) and A12 (PCM audio sample-identical to the source).
- R2. WAV and AIFF input at 16/24/32-bit and 44.1/48/96 kHz, mono or stereo, render with sample-identical audio (A2).
- R3. Keywords, `--set` and `--seed` change the result. The same inputs give identical frames (A4, A14). A slice (`--start/--duration`) draws exactly the frames the full render has at those times.

## 2. Beat sync and the 24 fps cartoon clock
- R4. On a 60 s slice, the picture pulses within ±1 frame of at least 90% of the beats in bars where the kick plays, with a median offset of at most 1 frame (A6). Video and audio durations differ by at most 1 frame (A7).
- R5. The same holds for the full 2 h render, with no drift at the end.
- R6. Characters are animated on a 24-drawings-per-second clock like 1930s cartoons and Cuphead, while the camera and shots move at 60 fps: averaged over a fight, 22 to 30 new drawings per second, and a new drawing starts on 100% of beat frames.

## 3. A boss rush built from the music
- R7. The set is cut into one act per boss in the pool (eight by default) when the acts come to 5 to 20 minutes, each starting and ending on a downbeat. An act is one or more takes of the fight, each opening with READY? and GO!; every take but the last is lost, and the last is won with three phases and a KNOCKOUT!, so each boss is beaten exactly once. The same boss never fights twice in a row.
- R8. Breakdowns of at least 16 bars inside a fight become intermissions (at most two per act), starting and ending on downbeats; over the 2 h set all three kinds appear (bouncing-ball sing-along, overworld map, vaudeville number).
- R9. The fight follows the music: every boss shot is fired on a beat in a bar where the kick plays; the heroes' shots fall on the 8th or 16th-note grid only while the hi-hats are busy; every super starts on a drop; every pink shot is parried by a hero who is in the air when it arrives; every hit on a hero lands on a beat (within 1 frame), and every revive is the partner parrying the ghost in mid-air on a beat.

## 4. Text and gags
- R10. Lettering is limited to the cartoon's cards and the HUD: the title card (the set title, A RUBBER HOSE REVUE, STARRING and the heroes' names), ROUND n and the boss's name, READY?, the GO words, KNOCKOUT!, the drop exclamations, INTERMISSION, FOLLOW THE BOUNCING BALL!, sing-along syllables, BPM, TAKE n and THE END, plus the gag and egg sound words (RING!, MEOW!, RIBBIT!, GONG!, HA HA!, CLANG!, BOOM!, ACHOO!), the ? on a ? block and RIP on the tombstones. Checked on every second of the set.
- R11. The on-device sound classifier (Core ML) covers the whole set with a result at least every 2 s. At least 8 distinct sound-cued gag kinds are scheduled for the Knisper set, each starting within 2 s of the sound the classifier heard.

## 5. Distinct, reproducible, resumable, fast enough
- R12. Two different sets differ measurably (colour-histogram distance above the A17 threshold on sampled frames), and the same set rendered twice is identical (A14, A17).
- R13. Re-running the command recorded in the sidecar reproduces the video frame for frame (A15). An interrupted render resumes and matches an uninterrupted one (A21).
- R14. The full Knisper set (1 h 55 m trimmed) at 1080p60 renders with the machine's load average at or below about 7. Frames are drawn on the GPU (Metal) and converted to YUV there; the sidecar records the GPU adapter and the sound classifier. Only free, open-source tools are used (A16).

## 6. Fight mechanics
- R16. Health, deaths and restarts: each hero has 3 HP per take; a hit only lands on a hero who is up, costs exactly one HP and is followed by at least 1 s without another hit; a hero is down exactly when their HP reaches 0, and comes back with 1 HP only when the partner parries their ghost while it is still on screen; a take is lost exactly when both heroes are down at its end, and never in a won take. No boss shot passes through a hero without hitting them or being parried. For the Knisper set: at least half the bosses need more than one take, at least 5 revives, and at least one fight is finished by a hero alone.
- R17. Super cards: each hero's meter stays between 0 and 5 cards; it fills from bullets that land and +1 per parry; an EX shot needs and spends exactly one card; a Super Art needs all five and empties the meter. Both are used in the Knisper set.
- R18. Easter eggs: at least one per minute of the set on average, never more than 90 s apart, at least 20 kinds, and the same egg never twice within 10 minutes.

## 7. The highlight reel
- R15. `setrender reel <audio> -t rubberhose` writes a reel of about 30 s (±2 s) made of 10 to 15 clips of 2 to 3 s each. Every cut lands on a beat (within 1 frame), the first clip shows the title card, the last shows the end card, and the clips in between are spread evenly through the set (each gap within ±50% of the average) at its salient moments (drops, supers, knockouts, gags). Each clip's audio is the set's own audio at that point.

## 8. Look and feel (human)
- H1. It looks like a 1930s rubber-hose cartoon in the spirit of Cuphead: hand-inked outlines that boil, pie-cut eyes, white four-finger gloves, hose limbs, big shoes, watercolour backgrounds, and a film print with grain, dust, scratches, gate weave and flicker.
- H2. The heroes, bosses, stages and lettering are original rather than Cuphead's own characters or assets, so the video is safe to upload.
- H3. Everything bounces on the beat; drops land (exclamation, super attack, camera punch), builds wind the boss up, and breakdowns become intermissions.
- H4. Fights read like Cuphead: a big expressive boss with three phases that visibly change it and damage that builds up on it, attacks fired in time with the music that knock hearts off the heroes, pink shots parried, super cards filling and spent on EX shots and Super Arts, ghosts rising and parried back to life, lost takes ending in the TAKE card and a fresh restart, READY? / GO! / KNOCKOUT! cards and iris transitions.
- H5. Two hours stay varied: eight stages including plane levels, three kinds of intermission, and gags and nods that astute viewers catch (The Skeleton Dance, Steamboat Willie, a film burn at bar 404), with a surprising easter egg about every minute.
- H6. The reel is a fair, punchy summary of the set.
