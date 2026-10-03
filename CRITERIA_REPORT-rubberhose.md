# Criteria report: rubberhose.tpl (2026-10-03)

Run with `.venv/bin/python tests/criteria_rubberhose.py --full out/knisper_rubberhose.mov --reel out/knisper_rubberhose_highlights.mp4` (about an hour, most of it decoding the 2 h video).

**14/15 automated checks pass.** R14 fails narrowly: the load went above 7 for about 90 seconds early in the render. The first run of these checks found three real problems, which were fixed before the final render:
- Pink parry shots were never drawn, because a lifetime bug left them always expired (R9).
- The HUD tempo dropped to "BPM 6" where the beat grid has gaps near the end of the set.
- The title and end clips of the reel did not start on a beat (R15).

| ID | Result | Evidence |
|---|---|---|
| R1 | pass | defaults only: H.264 High, yuv420p, BT.709, closed GOP, faststart, 1920x1080@60; PCM audio sample-identical |
| R2 | pass | 24-bit 48 kHz AIFF, 32-bit float 96 kHz mono WAV, 32-bit int WAV: audio sample-identical |
| R3 | pass | keywords, `--set` and seed change frames; same inputs give identical frames; a slice at 600 s draws the full render's frames |
| R4 | pass | 60 s slice: 95.2% of 125 kick beats have a picture pulse within ±1 frame, median offset 0 |
| R5 | pass | **full 2 h video: 99.7% of 9,566 kick beats pulse within ±1 frame, median offset 0; A/V differ by 0.17 frame; audio sample-identical** |
| R6 | pass | 23.4 new drawings per second over a fight; a new drawing on 239 of 239 beat frames |
| R7 | pass | 12 acts of 9.0 to 11.9 min, all on downbeats, three phases each, READY?/GO!/KNOCKOUT! cards; all 8 bosses fight; never the same boss twice in a row |
| R8 | pass | 18 intermissions (map, sing-along, vaudeville), all on downbeats, at most 2 per act; every eligible breakdown used |
| R9 | pass | 7,404 boss shots, all on beats in kick bars; 43,768 hero shots, all on the 8th/16th grid while the hats are busy; 64 supers, all on drops; 1,090 of 1,090 pink shots parried by a hero in the air |
| R10 | pass | 96 distinct strings drawn over every second of the set, none outside the allowed cards, HUD and gag words |
| R11 | pass | 4,973 classifier windows (every 1.5 s, ends covered); 14 sound-cued gag kinds, 126 gags, each starting on the sound |
| R12 | pass | colour-histogram distance between two sets 1.53; same set 0.0 |
| R13 | pass | two renders identical; sidecar command reproduces it; a render killed after 4 chunks resumes and matches |
| R14 | **fail** | render 60.6 min (2.05x real time), 10.4 GB, GPU: Apple M1 Pro via Metal, YUV made on the GPU. 1-min load median 5.2, but **17 of 715 samples above 7 (max 7.7)** during one stretch about 8 minutes in; the first full render had a similar 45 s spike to 9.1. The render's own load stays near 5, so the spikes need little else running to cross 7; `--cpu 6` (two jobs) would leave more headroom at about 1.5x real time |
| R15 | pass | 11 clips of 2.68 s (29.5 s), every cut on a beat, title first and end card last, evenly spread (gaps 588 to 1,055 s), each clip's sound matches the set (r ≥ 0.97) |

The human checklist H1 to H6 (look and feel) is yours to tick from `out/knisper_rubberhose.mov` and `out/knisper_rubberhose_highlights.mp4`.
