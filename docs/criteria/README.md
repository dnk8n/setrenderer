# Criteria: what "done" means

setrender is built criteria-first. Before a template or feature is built, its brief is turned into a list of criteria that say exactly what complete means, and each criterion is either:

- **automated** (IDs starting `A`, `C`, `R` or `S`): a script measures it on real renders. Beat sync to the frame, sample-identical audio, formats, determinism, resuming, distinctness between sets, the load on the machine, and each template's own rules (every boss shot on a beat, the camera cutting on downbeats, the crowd coming and going...);
- **human** (IDs starting `H`): a checklist item only a person can judge, such as "it looks like a 1930s rubber-hose cartoon".

Something is complete when every automated check passes and every human item is ticked. The reports record the latest full run of each.

| | Criteria | Latest report | Check script |
|---|---|---|---|
| CLI, output, reproducibility, performance, and knisper | [CRITERIA.md](CRITERIA.md) (A1 to A21, H1 to H6) | [CRITERIA_REPORT.md](CRITERIA_REPORT.md): 21/21 | `tests/criteria.py` |
| cropcircle | [CRITERIA-cropcircle.md](CRITERIA-cropcircle.md) (C1 to C16, H1 to H7) | [CRITERIA_REPORT-cropcircle.md](CRITERIA_REPORT-cropcircle.md): 16/16 | `tests/criteria_cropcircle.py` |
| rubberhose and the highlight reel | [CRITERIA-rubberhose.md](CRITERIA-rubberhose.md) (R1 to R18, H1 to H6) | [CRITERIA_REPORT-rubberhose.md](CRITERIA_REPORT-rubberhose.md): 18/18 | `tests/criteria_rubberhose.py` |
| spume (draft, for review) | [CRITERIA-spume.md](CRITERIA-spume.md) (S1 to S18, H1 to H8) | [CRITERIA_REPORT-spume.md](CRITERIA_REPORT-spume.md): 18/18 | `tests/criteria_spume.py` |

The template criteria build on the shared ones in `CRITERIA.md`: every template must meet the same output, sync, reproducibility and load rules.

## Running the checks

```bash
.venv/bin/python tests/criteria.py "/path/to/a/long/set.wav"
.venv/bin/python tests/criteria_cropcircle.py "/path/to/set.wav" --full out/<set>.cropcircle.mov
.venv/bin/python tests/criteria_rubberhose.py "/path/to/set.wav" --full out/<set>.rubberhose.mov --reel out/<set>.rubberhose_highlights.mp4
.venv/bin/python tests/criteria_rubberhose.py "/path/to/set.wav" --only R7,R9   # a subset
.venv/bin/python tests/criteria_spume.py "/path/to/set.wav" --full out/<set>.spume.mov --reel out/<set>.spume_highlights.mp4
```

Things to know before you run them:

- **They need a long set.** The scripts cut their test clips from the set itself, at 10 minutes, about an hour and 1 h 50 m, so pass a set of about two hours. Without an argument they use the maintainer's Knisper set, which only exists on the maintainer's machine.
- **Some checks need a full render.** `--full` points at a finished render of the whole set for the checks on two hours of sync, drift and the load during the render. The load check reads the render's own progress log from `work/full_render_<template>.log`, so keep that log (for example `setrender render ... 2>&1 | tee work/full_render_rubberhose.log`).
- **They render.** The scripts make short test renders, take minutes rather than seconds, and decoding a two-hour video for the full checks takes about 50 minutes. They respect the same load budget as normal renders.
- **They cache fixtures.** Test clips and renders go in `work/criteria*/`. If you switch to a different set, delete that folder first so the fixtures are cut again.
- **Results** are printed as a table and written to `work/criteria*/report.json` (`report-partial.json` with `--only`).
- **spume asks Apple's Vision models.** Its text, face, people and animal checks (S6, S7) run `tests/vision_check.swift` with the `swift` that comes with Xcode's command line tools, on-device; nothing is installed.

`setrender verify <video> --audio <set>` runs the format, audio and beat-sync checks on any single video.

## Writing criteria for something new

When you propose a new template or a feature with a visible effect, start with its criteria:

1. Write the brief in plain words: what should a viewer see and feel?
2. Turn every sentence into a criterion that is specific and checkable: a number, a threshold, a count, a timing tolerance. Keep the ones only a person can judge as `H` items.
3. Reuse the shared rules (`A1` to `A21`) rather than restating them.
4. Write the script that checks the automated ones, and a report of the run.

Changes to existing criteria are made by the maintainer, who owns these files, so propose them in an issue or a pull request description first.
