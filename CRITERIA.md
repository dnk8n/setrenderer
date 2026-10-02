# setrender: completeness criteria (draft v1)

Each criterion is checked by an automated test (`A`) or a human checklist (`H`).
A release is "complete" when every `A` passes and every `H` is ticked.

Template-specific criteria for cropcircle.tpl are in CRITERIA-cropcircle.md, and for rubberhose.tpl (and the highlight reel) in CRITERIA-rubberhose.md.

## 1. Interface
- A1. `setrender render <audio>` works with no other arguments (template `knisper.tpl` and every parameter defaulted).
- A2. Accepts WAV and AIFF: 16/24/32-bit, 44.1/48/96 kHz, mono or stereo.
- A3. Every parameter can be set by CLI flag or by a params file; `--help` lists each one with its default.
- A4. Keywords (`--keywords "neon,jellyfish,storm"`) and `--seed` change the result; templates are plain files you can copy and edit.

## 2. Beat sync
- A5. Synthetic 128 BPM click track: detected tempo within ±1 BPM.
- A6. From the rendered video, measure frame-to-frame visual "pulse" peaks and compare to detected beats: ≥90% of beats have a pulse within ±1 frame (±16.7 ms at 60 fps); median offset ≤1 frame.
- A7. Video and audio durations differ by ≤1 frame over the full set (no drift at the 2 h mark).

## 3. Frequency response
- A8. At least 4 bands (sub/bass, low-mid, high-mid, highs), each driving a different visual element.
- A9. Per band: correlation between band energy and its element's measured on-screen activity ≥0.6.
- A10. Silent input produces a near-static video (motion below a set threshold).

## 4. Output (YouTube upload)
- A11. `ffprobe` confirms: H.264 High, progressive, yuv420p, BT.709 tagged, closed GOP ≤ half the frame rate, 1920x1080 default (1440p/4K selectable), 30 or 60 fps, faststart.
- A12. Audio is lossless in the upload file (PCM, sample-identical to the source) by default; AAC 384k selectable.
- A13. `--quality lossless` gives mathematically lossless video (FFV1 or x264 qp0) for clips; the CLI estimates output size and refuses to start if the disk can't hold it.

## 5. Reproducibility
- A14. Same audio + template + params + seed renders bit-identical decoded frames on two runs.
- A15. Each render writes a sidecar JSON with all resolved parameters, analysis hash and tool versions; re-running from the sidecar reproduces the video.
- A16. Only free, open-source tools, running locally with no network at render time; one-command install.

## 6. Distinctness
- A17. Two different sets with the same template differ measurably (palette/histogram distance above threshold on sampled frames); same set twice does not (see A14).
- A18. Within a set, the scene changes at detected section boundaries (energy/novelty changes), with at least one visible variation per section.

## 7. knisper.tpl content (human)
- H1. Pixel-art 8-bit look with a modern twist (glow, smooth motion, CRT/scanlines).
- H2. Nods to C64, Amiga, Mega Drive, N64, NES (palettes, copper bars, boot text, sprites).
- H3. Burned-out car turned DJ stage, with a DJ who visibly drives the crowd.
- H4. Dancefloor of bouncing characters: blocky (Minecraft-like), stick figures, varied skin tones, hair, clothes and gender presentation.
- H5. Trees with jellyfish hanging in them, pulsing.
- H6. Vibrant colour pulsing that follows the music; feels like an underground rave.

## 8. Performance on the M1 Pro
- A19. Full 2 h 04 m set at 1080p60 renders with the machine's load average staying at or below ~7 (default `--cpu 7`), peak RAM ≤4 GB, analysis cached so re-renders skip it. Speed is secondary (overnight is fine).
- A21. An interrupted render resumes from the last finished chunk and produces the same frames as an uninterrupted one.
- A20. `--start/--duration` renders a slice for previews.
