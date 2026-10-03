# Criteria report: cropcircle.tpl (2026-10-01)

Run with `.venv/bin/python tests/criteria_cropcircle.py --full out/knisper_cropcircle.mov` (50 min, most of it decoding the 2 h video).

**16/16 automated checks pass.** The first run found four real problems, which were fixed before the final render:
- The HUD waveform drifted by up to 23 s by the end of the set (C12).
- 12% of camera cuts landed off the downbeat (C6).
- Half the gags had no shot that showed them (C13).
- A 60 s test file got all eight crop circles and UFO visits (C4).

| ID | Result | Evidence |
|---|---|---|
| C1 | pass | defaults only: H.264 High, yuv420p, BT.709, closed GOP, faststart, 1920x1080@60; PCM audio sample-identical |
| C2 | pass | 24-bit 48 kHz AIFF, 32-bit float 96 kHz mono WAV, 32-bit int WAV: audio sample-identical |
| C3 | pass | keywords and seed change frames; same inputs give identical frames |
| C4 | pass | 60 s slice: 99.2% of 125 kick beats have a scene pulse within ±1 frame, median offset 0 |
| C5 | pass | **full 2 h video: 99.2% of 9,566 kick beats pulse within ±1 frame, median offset 0; A/V differ by 0.17 frame; audio sample-identical** |
| C6 | pass | camera moves in 97.7% of frames, FOV spans 64.5°, 17 shot kinds, 606 cuts, 98.4% on the beat grid |
| C7 | pass | 110 people; 23–110 on site; all relocate (45 walks each on average); 397 arrivals, 368 departures, every 10 min |
| C8 | pass | wind vs beat r = 0.87; jellyfish swing vs wind r = 0.86 at a 0.33 s response delay |
| C9 | pass | headlights vs sub-bass r = 0.63; hazard lights blink on the beat in breakdowns |
| C10 | pass | 9,201 HUD strings, only BPM/BAR/PHR/KEY/LUFS, numbers, Camelot codes and arrows |
| C11 | pass | 698 flag changes on the poles, bunting up and down 27 times, all 12 identity flags shown |
| C12 | pass | 4,973 classifier windows (every 1.5 s); waveform spans 7,462.4 s of 7,462.3 s; 18 sound-triggered gag kinds, all within 2 s |
| C13 | pass | 48 kinds of event; 60 of 60 gags get a framed shot |
| C14 | pass | colour-histogram distance between two sets 0.95; same set 0.0 |
| C15 | pass | two renders identical; sidecar command reproduces it; render killed after 4 chunks resumes and matches |
| C16 | pass | full 2 h 04 m render in 60.9 min (2.0x real time), 19.3 GB, 1-min load max 5.6 (median 4.1), GPU: Apple M1 Pro via Metal |

The human checklist H1 to H7 (look and feel) is yours to tick from `out/knisper_cropcircle.mov`.
