"""Music analysis: frequency bands, onsets, beats, bars, sections and a per-set fingerprint.

Everything is computed in fixed-size chunks so a 2+ hour set stays within a few GB of RAM.
Results are cached as .npz keyed by the audio hash and analysis parameters.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy import ndimage, signal

from . import audio

ANALYSIS_VERSION = 7
SR = 22050
HOP = 512
N_FFT = 2048
N_FFT_ONSET = 512
ONSET_BIAS_S = 0.0  # calibrated on a click track (see tests)
FEATURE_RATE = SR / HOP  # ~43.07 Hz
CHUNK_S = 60.0
TEMPO_PRIOR = 128.0

DEFAULT_BANDS = {
    "sub": (20, 90),
    "bass": (90, 250),
    "lowmid": (250, 1000),
    "highmid": (1000, 4000),
    "high": (4000, 11000),
}


@dataclass
class Analysis:
    duration: float
    feature_rate: float
    bands: dict[str, np.ndarray]          # normalised 0..1 per feature frame
    band_ranges: dict[str, tuple[float, float]]
    onset: np.ndarray                     # normalised onset strength 0..1
    loudness: np.ndarray                  # normalised RMS 0..1
    beats: np.ndarray                     # beat times (s)
    downbeats: np.ndarray                 # bar start times (s)
    sections: np.ndarray                  # section start times (s), first is 0
    section_energy: np.ndarray            # mean loudness per section 0..1
    tempo: float
    fingerprint: dict = field(default_factory=dict)

    def at(self, arr: np.ndarray, t: np.ndarray | float) -> np.ndarray:
        idx = np.asarray(t) * self.feature_rate
        return np.interp(idx, np.arange(len(arr)), arr)


# ---------------------------------------------------------------- helpers

def _adaptive_norm(x: np.ndarray, win_s: float = 12.0) -> np.ndarray:
    """Normalise a log-energy curve against its local floor/ceiling so quiet and loud
    passages both move, while keeping dynamics inside each window."""
    w = max(3, int(win_s * FEATURE_RATE))
    lo = ndimage.uniform_filter1d(ndimage.minimum_filter1d(x, w, mode="nearest"), w, mode="nearest")
    hi = ndimage.uniform_filter1d(ndimage.maximum_filter1d(x, w, mode="nearest"), w, mode="nearest")
    # keep a sane span so near-silence doesn't get amplified into noise
    span = np.maximum(hi - lo, 6.0)
    return np.clip((x - lo) / span, 0.0, 1.0).astype(np.float32)


def _global_norm(x: np.ndarray, lo_pct=5, hi_pct=99) -> np.ndarray:
    lo, hi = np.percentile(x, [lo_pct, hi_pct])
    return np.clip((x - lo) / max(hi - lo, 1e-9), 0, 1).astype(np.float32)


def _checkerboard_novelty(feat: np.ndarray, half: int) -> np.ndarray:
    """Foote novelty on a (frames, dims) feature matrix, computed band-diagonally."""
    f = feat - feat.mean(0)
    f /= np.linalg.norm(f, axis=1, keepdims=True) + 1e-9
    n = len(f)
    nov = np.zeros(n)
    g = signal.windows.gaussian(2 * half, half / 2)
    ker = np.outer(g, g)
    ker[:half, half:] *= -1
    ker[half:, :half] *= -1
    for i in range(half, n - half):
        blk = f[i - half:i + half]
        nov[i] = np.sum((blk @ blk.T) * ker)
    nov = np.maximum(nov, 0)
    return nov / (nov.max() + 1e-9)


def _refine_beats(beats: np.ndarray, oenv: np.ndarray) -> np.ndarray:
    """Move each beat to the parabolic peak of the onset envelope within ±2 hops (sub-hop precision)."""
    out = []
    n = len(oenv)
    for b in beats:
        f = int(round(b * FEATURE_RATE))
        a, z = max(1, f - 2), min(n - 2, f + 2)
        if z <= a:
            out.append(b)
            continue
        k = a + int(np.argmax(oenv[a:z + 1]))
        y0, y1, y2 = oenv[k - 1], oenv[k], oenv[k + 1]
        den = y0 - 2 * y1 + y2
        delta = 0.5 * (y0 - y2) / den if abs(den) > 1e-12 else 0.0
        # onset flux at frame k measures change from k-1 to k: the attack sits half a hop earlier
        out.append((k + float(np.clip(delta, -0.5, 0.5))) / FEATURE_RATE + ONSET_BIAS_S)
    return np.array(out)


def _smooth_grid(b: np.ndarray, half: int = 4) -> np.ndarray:
    """Replace each beat with a local linear fit over its neighbours: keeps phase and slow tempo
    changes (DJ transitions) but removes per-beat jitter from hats and snares."""
    n = len(b)
    if n < 2 * half + 1:
        return b
    out = b.copy()
    idx = np.arange(n, dtype=float)
    for i in range(n):
        a, z = max(0, i - half), min(n, i + half + 1)
        x, y = idx[a:z], b[a:z]
        k, c = np.polyfit(x, y, 1)
        res = np.abs(y - (k * x + c))
        keep = res < max(0.03, 2.5 * np.median(res))
        if keep.sum() >= 3 and not keep.all():
            k, c = np.polyfit(x[keep], y[keep], 1)
        out[i] = k * i + c
    return out


# ---------------------------------------------------------------- main

def analyse(path: Path, start: float = 0.0, duration: float | None = None,
            bands: dict | None = None, section_min_s: float = 45.0,
            log=print) -> Analysis:
    import librosa  # imported lazily: slow import

    bands = bands or DEFAULT_BANDS
    info = audio.probe(path, start, duration)
    log(f"  decoding {info.duration/60:.1f} min of audio …")
    y = audio.decode_mono(path, SR, start, info.duration)
    n_frames = 1 + len(y) // HOP
    freqs = librosa.fft_frequencies(sr=SR, n_fft=N_FFT)
    mel_fb = librosa.filters.mel(sr=SR, n_fft=N_FFT, n_mels=96)
    mel_fb_on = librosa.filters.mel(sr=SR, n_fft=N_FFT_ONSET, n_mels=40)
    chroma_fb = librosa.filters.chroma(sr=SR, n_fft=N_FFT)
    band_masks = {k: (freqs >= lo) & (freqs < hi) for k, (lo, hi) in bands.items()}

    band_e = {k: np.zeros(n_frames, np.float32) for k in bands}
    rms = np.zeros(n_frames, np.float32)
    onset = np.zeros(n_frames, np.float32)
    mel_sec = []   # 1 Hz summary for sectioning
    chroma_acc = np.zeros(12)
    centroid_acc = 0.0
    centroid_n = 0

    chunk = int(CHUNK_S * FEATURE_RATE)
    pad = N_FFT
    prev_mel = None
    prev_kick = None
    kick = np.zeros(n_frames, np.float32)
    kick_mask = librosa.fft_frequencies(sr=SR, n_fft=N_FFT_ONSET) < 150
    log(f"  analysing spectrum in {int(np.ceil(n_frames / chunk))} chunks …")
    for c0 in range(0, n_frames, chunk):
        c1 = min(n_frames, c0 + chunk)
        s0 = c0 * HOP - pad
        s1 = c1 * HOP + pad
        seg = y[max(0, s0):min(len(y), s1)]
        seg = np.pad(seg, (max(0, -s0), max(0, s1 - len(y))))
        S = np.abs(librosa.stft(seg, n_fft=N_FFT, hop_length=HOP, center=True)) ** 2
        off = pad // HOP
        S = S[:, off:off + (c1 - c0)]
        for k, m in band_masks.items():
            band_e[k][c0:c1] = 10 * np.log10(S[m].sum(0) + 1e-10)
        rms[c0:c1] = 10 * np.log10(S.sum(0) + 1e-10)
        M = librosa.power_to_db(mel_fb @ S, ref=1.0, top_db=None)
        # onset flux from a short window for timing precision
        Ss = np.abs(librosa.stft(seg, n_fft=N_FFT_ONSET, hop_length=HOP, center=True)) ** 2
        Ss = Ss[:, off:off + (c1 - c0)]
        Ms = librosa.power_to_db(mel_fb_on @ Ss, ref=1.0, top_db=None)
        if prev_mel is None:
            prev_mel = Ms[:, :1]
        dM = np.diff(np.concatenate([prev_mel, Ms], axis=1), axis=1)
        onset[c0:c1] = np.maximum(dM, 0).mean(0)
        prev_mel = Ms[:, -1:]
        kl = 10 * np.log10(Ss[kick_mask].sum(0) + 1e-10)
        if prev_kick is None:
            prev_kick = kl[:1]
        kick[c0:c1] = np.maximum(np.diff(np.concatenate([prev_kick, kl])), 0)
        prev_kick = kl[-1:]
        C = chroma_fb @ S
        chroma_acc += C.sum(1)
        cen = (freqs[:, None] * S).sum(0) / (S.sum(0) + 1e-10)
        loud = S.sum(0) > np.percentile(S.sum(0), 20)
        centroid_acc += cen[loud].sum()
        centroid_n += int(loud.sum())
        # 1-second summaries for sectioning
        step = int(round(FEATURE_RATE))
        for j in range(0, M.shape[1] - step + 1, step):
            mel_sec.append(np.concatenate([M[::4, j:j + step].mean(1),
                                           (C[:, j:j + step].mean(1) / (C[:, j:j + step].mean(1).sum() + 1e-9)) * 40]))

    # ---- beats: per-chunk tracking copes with tempo drift across a DJ set
    log("  tracking beats …")
    # kick-weighted onset envelope: DJ sets are carried by the kick drum
    def _z(x):
        return x / (np.percentile(x, 99) + 1e-9)
    oenv = _z(kick) + 0.35 * _z(onset)
    beats = []
    bchunk = int(90 * FEATURE_RATE)
    ov = int(8 * FEATURE_RATE)
    for c0 in range(0, n_frames, bchunk):
        a = max(0, c0 - ov)
        b = min(n_frames, c0 + bchunk + ov)
        if b - a < FEATURE_RATE * 4:
            continue
        # tempo prior centred on club tempo keeps short or sparse passages from halving/doubling
        bpm = float(librosa.feature.tempo(onset_envelope=oenv[a:b], sr=SR, hop_length=HOP,
                                          start_bpm=TEMPO_PRIOR, std_bpm=0.5)[0])
        _, bf = librosa.beat.beat_track(onset_envelope=oenv[a:b], sr=SR, hop_length=HOP,
                                        bpm=bpm, trim=False)
        bt = (bf + a) / FEATURE_RATE
        keep = (bt >= c0 / FEATURE_RATE) & (bt < min(n_frames, c0 + bchunk) / FEATURE_RATE)
        beats.extend(bt[keep].tolist())
    beats = np.array(sorted(beats))
    if len(beats) > 1:  # drop near-duplicates at chunk seams
        beats = beats[np.concatenate([[True], np.diff(beats) > 0.2])]
    beats = _smooth_grid(_refine_beats(beats, oenv))
    if len(beats) > 2:
        d = np.diff(beats)
        med = np.median(d)
        tempo = float(60.0 / d[np.abs(d - med) < 0.05 * med].mean())
    else:
        tempo = 120.0

    # downbeats: choose the 4-beat phase with the most low-end energy
    sub_raw = band_e[list(bands)[0]]
    if len(beats) >= 8:
        bidx = np.clip((beats * FEATURE_RATE).astype(int), 0, n_frames - 1)
        e = sub_raw[bidx]
        phase = int(np.argmax([e[p::4].mean() for p in range(4)]))
        downbeats = beats[phase::4]
    else:
        downbeats = beats[::4]

    # ---- sections via self-similarity novelty on 1 Hz features
    log("  finding sections …")
    F = np.array(mel_sec) if mel_sec else np.zeros((1, 36))
    F = ndimage.uniform_filter1d(F, 4, axis=0)
    half = 16
    if len(F) > 4 * half:
        nov = _checkerboard_novelty(F, half)
        peaks, _ = signal.find_peaks(nov, distance=int(section_min_s), height=0.15, prominence=0.08)
        sec = np.concatenate([[0.0], peaks.astype(float)])
    else:
        sec = np.array([0.0])
    # snap section starts to nearest downbeat for musical changes
    if len(downbeats):
        sec = np.array([0.0] + [float(downbeats[np.argmin(np.abs(downbeats - s))]) for s in sec[1:]])
        sec = np.unique(sec)

    # ---- normalisation
    band_n = {k: _adaptive_norm(v) for k, v in band_e.items()}
    loud_n = _global_norm(rms)
    onset_n = _global_norm(ndimage.uniform_filter1d(onset, 2), 5, 99.5)
    sec_idx = np.clip((sec * FEATURE_RATE).astype(int), 0, n_frames - 1)
    bounds = np.concatenate([sec_idx, [n_frames]])
    sec_energy = np.array([loud_n[a:b].mean() if b > a else 0 for a, b in zip(bounds[:-1], bounds[1:])])

    chroma = chroma_acc / (chroma_acc.sum() + 1e-9)
    raw_bands = {k: float(np.mean(v)) for k, v in band_e.items()}
    fp = {
        "tempo": round(tempo, 2),
        "key_pc": int(np.argmax(chroma)),
        "chroma": [round(float(c), 4) for c in chroma],
        "centroid_hz": round(centroid_acc / max(centroid_n, 1), 1),
        "band_db": {k: round(v, 2) for k, v in raw_bands.items()},
        "dynamic_range_db": round(float(np.percentile(rms, 95) - np.percentile(rms, 10)), 2),
        "onset_density": round(float((onset_n > 0.5).mean()), 4),
        "n_sections": int(len(sec)),
    }
    return Analysis(
        duration=info.duration, feature_rate=FEATURE_RATE, bands=band_n,
        band_ranges=dict(bands), onset=onset_n, loudness=loud_n, beats=beats,
        downbeats=downbeats, sections=sec, section_energy=sec_energy.astype(np.float32),
        tempo=tempo, fingerprint=fp,
    )


# ---------------------------------------------------------------- cache

def cache_key(audio_hash: str, start: float, duration: float | None, bands: dict) -> str:
    import hashlib
    s = json.dumps([ANALYSIS_VERSION, audio_hash, round(start, 3),
                    None if duration is None else round(duration, 3),
                    {k: list(v) for k, v in sorted(bands.items())}])
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def save(a: Analysis, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path, duration=a.duration, feature_rate=a.feature_rate, onset=a.onset, loudness=a.loudness,
        beats=a.beats, downbeats=a.downbeats, sections=a.sections, section_energy=a.section_energy,
        tempo=a.tempo, band_names=np.array(list(a.bands)),
        band_ranges=np.array([a.band_ranges[k] for k in a.bands]),
        fingerprint=json.dumps(a.fingerprint),
        **{f"band_{k}": v for k, v in a.bands.items()},
    )


def load(path: Path) -> Analysis:
    z = np.load(path, allow_pickle=False)
    names = [str(n) for n in z["band_names"]]
    return Analysis(
        duration=float(z["duration"]), feature_rate=float(z["feature_rate"]),
        bands={k: z[f"band_{k}"] for k in names},
        band_ranges={k: tuple(r) for k, r in zip(names, z["band_ranges"])},
        onset=z["onset"], loudness=z["loudness"], beats=z["beats"], downbeats=z["downbeats"],
        sections=z["sections"], section_energy=z["section_energy"], tempo=float(z["tempo"]),
        fingerprint=json.loads(str(z["fingerprint"])),
    )
