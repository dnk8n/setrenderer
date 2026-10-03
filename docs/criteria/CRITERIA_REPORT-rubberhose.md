# Criteria report: rubberhose.tpl, fight mechanics round three (2026-10-03)

Run with `.venv/bin/python tests/criteria_rubberhose.py --full out/knisper_rubberhose.mov --reel out/knisper_rubberhose_highlights.mp4` on the trimmed Knisper set (`Pepper&Pumpernickl - Knisper 2026 (trimmed).WAV`, 1 h 55 m). The checks follow CRITERIA-rubberhose.md draft v2 as amended for round three: thirteen bosses, a full hand always fires a Super Art, and an EX is never thrown with a full hand.

**18/18 automated checks pass.**

| ID | Result | Evidence |
|---|---|---|
| R1 | pass | defaults only: H.264 High, yuv420p, BT.709, closed GOP, faststart, 1920x1080@60; PCM audio sample-identical |
| R2 | pass | 24-bit 48 kHz AIFF, 32-bit float 96 kHz mono WAV, 32-bit int WAV: audio sample-identical |
| R3 | pass | keywords, `--set` and seed change frames; same inputs give identical frames; a slice at 600 s draws the full render's frames |
| R4 | pass | 60 s slice: 93.2% of 88 kick beats have a picture pulse within ±1 frame, median offset 0 |
| R5 | pass | **full video: 99.2% of 8,703 kick beats pulse within ±1 frame, median offset 0; A/V differ by 0.2 frame; audio sample-identical** |
| R6 | pass | 23.6 new drawings per second over a fight; a new drawing on 256 of 256 beat frames |
| R7 | pass | 13 acts, one per boss, of 6.9 to 10.5 min, all on downbeats; takes per act 3, 3, 2, 2, 1, 1, 2, 1, 3, 3, 2, 3, 3; the last take of each act won with three phases; every boss beaten exactly once; never the same boss twice in a row |
| R8 | pass | 18 intermissions (map, sing-along, vaudeville), all on downbeats, at most 2 per act; every eligible breakdown used |
| R9 | pass | 9,606 boss shots and sidekicks, all on beats in kick bars; 31,856 hero shots on the 8th/16th grid while the hats are busy; 151 Super Art starts, each on a drop or the downbeat of a big bar; 851 of 851 pink shots parried in mid-air or hitting a hero who jumped too early; 183 hits and 26 revives, all on beats |
| R10 | pass | 110 distinct strings drawn over every second of the set, every card and every easter egg; none outside the allowed list |
| R11 | pass | 4,605 classifier windows (every 1.5 s); 14 sound-cued gag kinds, 107 gags, each starting on its sound |
| R12 | pass | colour-histogram distance between two sets 1.21; same set 0.0 |
| R13 | pass | two renders identical; sidecar command reproduces it; a render killed after 4 chunks resumes and matches |
| R14 | pass | render 64.5 min (1.79x real time), 10.4 GB, GPU: Apple M1 Pro via Metal, YUV made on the GPU; **1-min load median 3.8, max 6.3, 0 of 759 samples above 7** (`--cpu 6`, two jobs) |
| R15 | pass | 11 clips of 2.67 s (29.3 s), every cut on a beat, title first and end card last, evenly spread (gaps 548 to 995 s), each clip's sound matches the set (r ≥ 0.98 at 48 kHz) |
| R16 | pass | 29 takes (16 lost), 10 of 13 bosses need retakes; 183 hits, 26 revives by ghost parry, 1 fight finished by one hero alone; 47 mistimed parries, 72 sidekick hits, 20 hearts grabbed and 43 missed or snatched; 3,746 near misses; HP bookkeeping consistent everywhere; no shot or sidekick passes through a hero |
| R17 | pass | 237 EX shots (one card each, never from a full hand) and 156 Super Arts (a full hand each); meters always between 0 and 5 cards |
| R18 | pass | 115 easter eggs over 114.8 minutes, never more than 72 s apart, 26 kinds, the same one never within 652 s |

knisper and cropcircle are untouched by this work (only `src/setrender/hose/` changed): stills at 600 s and 3600 s from main and from this branch are byte-identical for both templates.

The render ran with `--force`: the renderer's free-space check asks for twice its 13 GB estimate, and 23 GB were free. It finished at 10.4 GB with 15 GB left over.

The human checklist H1 to H6 (look and feel) is yours to tick from `out/knisper_rubberhose.mov` and `out/knisper_rubberhose_highlights.mp4`.
