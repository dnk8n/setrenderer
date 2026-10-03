# Criteria report: knisper.tpl (2026-10-01)

Run with `.venv/bin/python tests/criteria.py`, plus `setrender verify` on the full render.

**21/21 automated checks pass.** A3 failed on the first run (some options didn't show a default in `--help`). It was fixed and rechecked.

| ID | Result | Evidence |
|---|---|---|
| A1 | pass | `setrender render <audio>` with every option defaulted |
| A2 | pass | 24-bit 48 kHz AIFF, 32-bit float 96 kHz mono WAV, 32-bit int WAV: audio sample-identical in output |
| A3 | pass | all 38 options list a default |
| A4 | pass | keywords and seed change frames; same inputs give identical frames |
| A5 | pass | 128 BPM click track: tempo 127.96, median beat error 1.1 ms, max 4.8 ms |
| A6 | pass | **full 2 h video: 98.6% of 16,240 beats have a visual pulse within ±1 frame, median offset 0** |
| A7 | pass | full 2 h video: audio/video duration differ by 0.17 frame |
| A8/A9 | pass | band → element correlation: sub→crowd 0.87, low-mid→jellyfish 0.79, high-mid→sky bars 0.73, highs→stars 0.84, onsets→lasers 0.96 |
| A10 | pass | silence produces 13% of the motion of music |
| A11 | pass | H.264 High, yuv420p, progressive, BT.709, closed GOP 30, faststart, 1920x1080@60 |
| A12 | pass | full 2 h PCM audio is sample-identical to the source WAV |
| A13 | pass | lossless = FFV1 RGB; render refuses when disk is too small |
| A14 | pass | two renders: identical frame MD5 |
| A15 | pass | re-render from sidecar command: identical frame MD5 |
| A16 | pass | ffmpeg, librosa, numpy/scipy, pygame-ce, PyYAML; `./install.sh` with pinned `requirements.lock` |
| A17 | pass | colour-histogram distance between two different sets 1.25; same set 0.0 |
| A18 | pass | 78 sections; histogram change across a section boundary 1.41 vs 0.31 within a section |
| A19 | pass | full 2 h 04 m render: 38 min, 1-min load max 6.3 (median 5.0), 12.2 GB, analysis 18 s / 2.1 GB RAM |
| A20 | pass | `--start/--duration` slice is exact |
| A21 | pass | render killed after 3 chunks, rerun resumed and matched an uninterrupted render frame for frame |

Human checklist H1 to H6 (look and feel) is yours to tick from the previews and `out/knisper_full.mov`.
