# Criteria report: rubberhose.tpl, fight mechanics round two (2026-10-03)

Run with `.venv/bin/python tests/criteria_rubberhose.py --full out/knisper_rubberhose.mov --reel out/knisper_rubberhose_highlights.mp4` on the trimmed Knisper set (`Pepper&Pumpernickl - Knisper 2026 (trimmed).WAV`, 1 h 55 m). The checks follow CRITERIA-rubberhose.md draft v2, which adds R16 to R18 for the fight mechanics.

**18/18 automated checks pass.** In the full run R15 first failed at r = 0.887 on one reel clip. That was a measurement problem: the check compared audio at 8 kHz, and a sub-sample offset alone lowers the match on hi-hat-heavy passages. It now compares at 48 kHz, exact to the sample, keeping the 0.9 threshold, and every clip matches at r ≥ 0.98. R15 was re-run on its own after the fix.

| ID | Result | Evidence |
|---|---|---|
| R1 | pass | defaults only: H.264 High, yuv420p, BT.709, closed GOP, faststart, 1920x1080@60; PCM audio sample-identical |
| R2 | pass | 24-bit 48 kHz AIFF, 32-bit float 96 kHz mono WAV, 32-bit int WAV: audio sample-identical |
| R3 | pass | keywords, `--set` and seed change frames; same inputs give identical frames; a slice at 600 s draws the full render's frames |
| R4 | pass | 60 s slice: 93.2% of 88 kick beats have a picture pulse within ±1 frame, median offset 0 |
| R5 | pass | **full video: 99.6% of 8,703 kick beats pulse within ±1 frame, median offset 0; A/V differ by 0.2 frame; audio sample-identical** |
| R6 | pass | 23.6 new drawings per second over a fight; a new drawing on 256 of 256 beat frames |
| R7 | pass | 8 acts, one per boss, of 10.4 to 17.7 min, all on downbeats; takes per act 1, 3, 3, 1, 3, 2, 1, 3; the last take of each act won with three phases; every boss beaten exactly once; never the same boss twice in a row |
| R8 | pass | 15 intermissions (map, sing-along, vaudeville), all on downbeats, at most 2 per act; every eligible breakdown used |
| R9 | pass | 5,374 boss shots and sidekicks, all on beats in kick bars; 37,771 hero shots on the 8th/16th grid while the hats are busy; 35 Super Art starts, all on drops; 684 of 684 pink shots parried in mid-air or hitting a hero who jumped too early; 107 hits and 8 revives, all on beats |
| R10 | pass | 105 distinct strings drawn over every second of the set, every card and every easter egg; none outside the allowed list |
| R11 | pass | 4,605 classifier windows (every 1.5 s); 14 sound-cued gag kinds, 111 gags, each starting on its sound |
| R12 | pass | colour-histogram distance between two sets 0.39; same set 0.0 |
| R13 | pass | two renders identical; sidecar command reproduces it; a render killed after 3 chunks resumes and matches |
| R14 | pass | render 65.5 min (1.76x real time), 9.9 GB, GPU: Apple M1 Pro via Metal, YUV made on the GPU; **1-min load median 3.4, max 4.8, 0 of 771 samples above 7** (`--cpu 6`, two jobs) |
| R15 | pass | 11 clips of 2.67 s (29.3 s), every cut on a beat, title first and end card last, evenly spread (gaps 544 to 979 s), each clip's sound matches the set (r ≥ 0.98 at 48 kHz) |
| R16 | pass | 17 takes (9 lost), 5 of 8 bosses need retakes; 107 hits, 8 revives by ghost parry, 2 fights finished by one hero alone; 23 mistimed parries, 39 sidekick hits, 28 hearts grabbed and 43 missed or snatched; 2,476 near misses; HP bookkeeping consistent everywhere; no shot or sidekick passes through a hero |
| R17 | pass | 419 EX shots (one card each) and 48 Super Arts (a full hand each); meters always between 0 and 5 cards |
| R18 | pass | 115 easter eggs over 114.8 minutes, never more than 71 s apart, 26 kinds, the same one never within 652 s |

knisper and cropcircle are untouched by this work (only `src/setrender/hose/` changed): stills at 600 s and 3600 s from main and from this branch are byte-identical for both templates.

The human checklist H1 to H6 (look and feel) is yours to tick from `out/knisper_rubberhose.mov` and `out/knisper_rubberhose_highlights.mp4`.
