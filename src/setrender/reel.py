"""Highlight reels: about a dozen beat-length clips, spread evenly through the set, each placed on its
window's most salient moment (drops, energy jumps, section starts and whatever the template flags:
supers, knockouts, gags). Cuts land on beats; the reel opens on the title card and closes on the end.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .analysis import Analysis
from .audio import require_tool


@dataclass
class Clip:
    t0: float
    dur: float
    why: str
    score: float = 0.0


def salience(an: Analysis, st, hints: list[tuple[float, float, str]] | None = None):
    """Score every downbeat: (times, scores, reasons)."""
    db = st.downbeats
    if len(db) < 8:
        db = np.arange(0.0, an.duration, 2.0)
    period = 60.0 / max(an.tempo, 60)
    bar = 4 * period
    loud = an.loudness
    t_f = np.arange(len(loud)) / an.feature_rate

    def mean_loud(t0, t1):
        m = (t_f >= t0) & (t_f < t1)
        return float(loud[m].mean()) if m.any() else 0.0
    score = np.zeros(len(db))
    why = ["energy"] * len(db)
    ons = an.onset
    for k, t in enumerate(db):
        after, before = mean_loud(t, t + 2 * bar), mean_loud(t - 4 * bar, t)
        m = (t_f >= t) & (t_f < t + 2 * bar)
        busy = float(ons[m].mean()) if m.any() else 0.0
        score[k] = 1.2 * max(0.0, after - before) + 0.6 * after + 0.4 * busy
    for d in st.drops:
        k = int(np.argmin(np.abs(db - d.t0)))
        if abs(db[k] - d.t0) < bar:
            score[k] += 0.8 + 0.4 * d.strength
            why[k] = "drop"
    for s in an.sections[1:]:
        k = int(np.argmin(np.abs(db - s)))
        if abs(db[k] - s) < bar:
            score[k] += 0.25
            if why[k] == "energy":
                why[k] = "section"
    for t, w, label in hints or []:
        k = int(np.clip(np.searchsorted(db, t) - 1, 0, len(db) - 1))
        if abs(db[k] - t) < 2 * bar:
            score[k] += w
            why[k] = label
    return np.asarray(db, float), score, why


def fit(length: float, period: float, n: int | None = None, lo: float = 2.0, hi: float = 3.0):
    """Clip count and whole-beat clip length (between lo and hi seconds) that best fill `length`."""
    best = None
    for nn in ([n] if n else range(10, 16)):
        for nb in range(1, 64):
            cl = nb * period
            if not (lo <= cl <= hi) and not (n and nb == max(1, round(length / n / period))):
                continue
            err = abs(nn * cl - length) + (0.0 if n else 0.02 * abs(nn - 12))
            if best is None or err < best[0]:
                best = (err, nn, nb)
    return (best[1], best[2]) if best else (n or 12, max(1, round(length / (n or 12) / period)))


def choose(an: Analysis, st, n: int | None = None, length: float = 30.0, hints=None, intro: float | None = None,
           outro: float | None = None) -> list[Clip]:
    """About `length` seconds of whole-beat clips (2-3 s each, 10-15 of them unless n is given), cut
    on beats. The first shows the title card, the last the end."""
    period = 60.0 / max(an.tempo, 60)
    dur = an.duration
    beats = an.beats if len(an.beats) > 8 else np.arange(0.0, dur, period)
    n, nb = fit(length, period, n)
    clip_len = nb * period
    db, score, why = salience(an, st, hints)

    def snap_beat(t):
        k = int(np.clip(np.searchsorted(beats, t), 1, len(beats) - 1))
        return float(beats[k] if abs(beats[k] - t) < abs(beats[k - 1] - t) else beats[k - 1])

    clips = []
    t_open = min(3.0, max(0.0, (intro or 8.0) - clip_len - 0.5))
    k_open = int(np.searchsorted(beats, t_open))
    if k_open < len(beats) and beats[k_open] + clip_len <= (intro or beats[k_open] + clip_len):
        t_open = float(beats[k_open])
    clips.append(Clip(t_open, clip_len, "title"))
    lo = (intro or 0.0) + clip_len
    hi = (outro if outro is not None else dur) - clip_len * 1.5
    inner = n - 2
    edges = np.linspace(lo, hi, inner + 1)
    used: dict[str, int] = {}
    for k in range(inner):
        a, b = edges[k], edges[k + 1]
        mid, w = (a + b) / 2, b - a
        # only the middle half of each stretch, so neighbouring clips stay between half and one and a
        # half stretches apart
        m = (db >= mid - 0.25 * w) & (db < mid + 0.25 * w - clip_len)
        if not m.any():
            clips.append(Clip(snap_beat(mid), clip_len, "even"))
            continue
        idx = np.where(m)[0]
        # salience, gently pulled to the middle, and a little against repeating the same kind of moment
        kinds = [why[i].split(" ")[0] + " " + why[i].split(" ")[1] if " " in why[i] else why[i] for i in idx]
        s = score[idx] - 0.15 * np.abs(db[idx] - mid) / max(w, 1.0) - np.array([0.9 * used.get(x, 0) for x in kinds])
        jj = int(np.argmax(s))
        j = idx[jj]
        used[kinds[jj]] = used.get(kinds[jj], 0) + 1
        # start one beat before the moment so the hit lands inside the clip
        t0 = snap_beat(db[j] - period)
        clips.append(Clip(t0, clip_len, why[j], float(score[j])))
    t_end = (outro if outro is not None else dur - clip_len - 2.5)
    t_last = min(t_end + 1.0, dur - clip_len - 2.6)
    k_last = int(np.searchsorted(beats, t_last))
    if k_last < len(beats) and beats[k_last] + clip_len <= dur - 0.5:
        t_last = float(beats[k_last])
    clips.append(Clip(t_last, clip_len, "the end"))
    return clips


def build(clips: list[Clip], sources: list[tuple[Path, float]], audio: Path, out: Path, fps: float = 60.0,
          q: int = 62, fade_in: float = 0.3, fade_out: float = 1.0, scale: tuple[int, int] | None = None,
          audio_bitrate: str = "320k") -> None:
    """sources[k] = (file, offset in that file) holding clip k's picture. Audio comes straight from the
    source set, with a 12 ms ramp at every cut so nothing clicks."""
    ff = require_tool("ffmpeg")
    cmd = [ff, "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    for (src, off), c in zip(sources, clips):
        cmd += ["-ss", f"{off:.6f}", "-t", f"{c.dur:.6f}", "-i", str(src)]
    for c in clips:
        cmd += ["-ss", f"{c.t0:.6f}", "-t", f"{c.dur:.6f}", "-i", str(audio)]
    n = len(clips)
    parts = []
    total = sum(c.dur for c in clips)
    for k, c in enumerate(clips):
        vf = f"fps={fps},trim=duration={c.dur:.6f},setpts=PTS-STARTPTS"
        if scale:
            vf += f",scale={scale[0]}:{scale[1]}:flags=lanczos"
        vf += ",format=yuv420p"
        parts.append(f"[{k}:v]{vf}[v{k}]")
        parts.append(f"[{n + k}:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=duration={c.dur:.6f},"
                     f"asetpts=PTS-STARTPTS,afade=t=in:d=0.012,afade=t=out:st={max(0.0, c.dur - 0.012):.6f}:d=0.012[a{k}]")
    parts.append("".join(f"[v{k}][a{k}]" for k in range(n)) + f"concat=n={n}:v=1:a=1[vc][ac]")
    parts.append(f"[vc]fade=t=in:d={fade_in},fade=t=out:st={total - fade_out:.3f}:d={fade_out}[vo]")
    parts.append(f"[ac]afade=t=in:d={fade_in},afade=t=out:st={total - fade_out:.3f}:d={fade_out}[ao]")
    cmd += ["-filter_complex", ";".join(parts), "-map", "[vo]", "-map", "[ao]",
            "-c:v", "h264_videotoolbox", "-profile:v", "high", "-q:v", str(q), "-g", str(int(fps / 2)), "-bf", "0",
            "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
            "-c:a", "aac", "-b:a", audio_bitrate, "-movflags", "+faststart", str(out)]
    subprocess.run(cmd, check=True)
