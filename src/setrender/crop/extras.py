"""Extra analysis for cropcircle, computed once per audio file and cached:

* sound events from Apple's built-in on-device sound classifier (303 classes, Core ML; runs on
  the Neural Engine/GPU) - cowbells, vocals, scratching, air horns, cheering, sirens...
* loudness in LUFS (ITU-R BS.1770 K-weighting, momentary 400 ms and short-term 3 s)
* key per window (Krumhansl-Kessler profiles on chroma), shown in Camelot notation
* spectral centroid and a three-band waveform for the CDJ-style overview in the HUD

Everything is streamed in one-minute chunks so a two-hour set stays small in memory.
"""
from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path

import numpy as np
from scipy import signal

from ..audio import require_tool

EXTRAS_VERSION = 2
SR = 22050
HOP = 2048          # ~10.8 Hz feature rate
RATE = SR / HOP

MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
# Camelot wheel: pitch class -> number, for major (B) and minor (A)
CAMELOT_MAJ = {0: 8, 7: 9, 2: 10, 9: 11, 4: 12, 11: 1, 6: 2, 1: 3, 8: 4, 3: 5, 10: 6, 5: 7}
CAMELOT_MIN = {9: 8, 4: 9, 11: 10, 6: 11, 1: 12, 8: 1, 3: 2, 10: 3, 5: 4, 0: 5, 7: 6, 2: 7}


def _biquad_shelf(fs):
    G, Q, fc = 3.99984385397, 0.7071752369554193, 1681.9744509555319
    A = 10 ** (G / 40)
    w0 = 2 * math.pi * fc / fs
    al = math.sin(w0) / (2 * Q)
    c = math.cos(w0)
    b = [A * ((A + 1) + (A - 1) * c + 2 * math.sqrt(A) * al), -2 * A * ((A - 1) + (A + 1) * c),
         A * ((A + 1) + (A - 1) * c - 2 * math.sqrt(A) * al)]
    a = [(A + 1) - (A - 1) * c + 2 * math.sqrt(A) * al, 2 * ((A - 1) - (A + 1) * c),
         (A + 1) - (A - 1) * c - 2 * math.sqrt(A) * al]
    return np.array(b) / a[0], np.array(a) / a[0]


def _biquad_hp(fs):
    Q, fc = 0.5003270373253953, 38.13547087613982
    w0 = 2 * math.pi * fc / fs
    al = math.sin(w0) / (2 * Q)
    c = math.cos(w0)
    b = [(1 + c) / 2, -(1 + c), (1 + c) / 2]
    a = [1 + al, -2 * c, 1 - al]
    return np.array(b) / a[0], np.array(a) / a[0]


def camelot(pc: int, minor: bool) -> str:
    return f"{(CAMELOT_MIN if minor else CAMELOT_MAJ)[pc]}{'A' if minor else 'B'}"


def _stream_features(path: Path, log) -> dict:
    import librosa
    cmd = [require_tool("ffmpeg"), "-nostdin", "-v", "error", "-i", str(path), "-ac", "2", "-ar", str(SR),
           "-af", "aresample=resampler=soxr", "-f", "f32le", "-"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE)
    shelf, hp = _biquad_shelf(SR), _biquad_hp(SR)
    zs = [signal.lfilter_zi(*shelf) * 0 for _ in range(2)]
    zh = [signal.lfilter_zi(*hp) * 0 for _ in range(2)]
    chunk = SR * 60 * 2 * 4     # bytes: one minute of stereo float32
    ms_blocks, chroma, cent, wave = [], [], [], []
    tail = np.zeros((0, 2), np.float32)
    freqs = librosa.fft_frequencies(sr=SR, n_fft=4096)
    bands = [(20, 200), (200, 2000), (2000, 11000)]
    masks = [(freqs >= a) & (freqs < b) for a, b in bands]
    cfb = librosa.filters.chroma(sr=SR, n_fft=4096)
    n = 0
    while True:
        raw = proc.stdout.read(chunk)
        if not raw:
            break
        x = np.frombuffer(raw, np.float32).reshape(-1, 2)
        n += len(x)
        # K-weighted mean square per hop
        kw = np.empty_like(x)
        for ch in range(2):
            y, zs[ch] = signal.lfilter(*shelf, x[:, ch], zi=zs[ch])
            y, zh[ch] = signal.lfilter(*hp, y, zi=zh[ch])
            kw[:, ch] = y
        buf = np.concatenate([tail, kw])
        nb = len(buf) // HOP
        ms_blocks.append((buf[:nb * HOP] ** 2).reshape(nb, HOP, 2).mean(1).sum(1))
        tail = buf[nb * HOP:]
        mono = x.mean(1)
        S = np.abs(librosa.stft(mono, n_fft=4096, hop_length=HOP, center=False)) ** 2
        if S.shape[1] == 0:
            continue
        chroma.append((cfb @ S).T)
        cent.append((freqs[:, None] * S).sum(0) / (S.sum(0) + 1e-12))
        wave.append(np.stack([np.sqrt(S[m].sum(0)) for m in masks], 1))
    proc.wait()
    ms = np.concatenate(ms_blocks) if ms_blocks else np.zeros(1)
    return {"ms": ms, "chroma": np.concatenate(chroma), "centroid": np.concatenate(cent),
            "wave": np.concatenate(wave), "n_samples": n}


def _keys(chroma: np.ndarray, win_s=30.0, step_s=4.0) -> tuple[np.ndarray, list[str]]:
    w, st = int(win_s * RATE), int(step_s * RATE)
    times, codes = [], []
    prof = []
    for k in range(12):
        prof.append(("maj", k, np.roll(MAJOR, k)))
        prof.append(("min", k, np.roll(MINOR, k)))
    for a in range(0, max(1, len(chroma) - 1), st):
        c = chroma[max(0, a - w // 2):a + w // 2].sum(0)
        if c.sum() <= 0:
            codes.append("--")
        else:
            cs = [np.corrcoef(c, p)[0, 1] for _, _, p in prof]
            m, pc, _ = prof[int(np.argmax(cs))]
            codes.append(camelot(pc, m == "min"))
        times.append(a / RATE)
    return np.array(times), codes


def classify_sounds(path: Path, log) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """Run Apple's SoundAnalysis built-in classifier over the whole file (macOS only)."""
    import objc
    import SoundAnalysis as SA
    from Foundation import NSURL, NSObject
    proto = objc.protocolNamed("SNResultsObserving")

    class Obs(NSObject, protocols=[proto]):
        def init(self):
            self = objc.super(Obs, self).init()
            self.rows = []
            return self

        def request_didProduceResult_(self, req, res):
            tr = res.timeRange()
            t0 = tr[0][0] / tr[0][1]
            dur = tr[1][0] / tr[1][1]
            self.rows.append((t0 + dur / 2, {c.identifier(): c.confidence() for c in res.classifications()}))

        def request_didFailWithError_(self, req, err):
            log(f"  sound classifier failed: {err}")

        def requestDidComplete_(self, req):
            pass

    req, err = SA.SNClassifySoundRequest.alloc().initWithClassifierIdentifier_error_(SA.SNClassifierIdentifierVersion1, None)
    req.setOverlapFactor_(0.5)
    labels = [str(x) for x in req.knownClassifications()]
    an, err = SA.SNAudioFileAnalyzer.alloc().initWithURL_error_(NSURL.fileURLWithPath_(str(path)), None)
    obs = Obs.alloc().init()
    an.addRequest_withObserver_error_(req, obs, None)
    an.analyze()
    rows = sorted(obs.rows, key=lambda r: r[0])
    t = np.array([r[0] for r in rows], np.float32)
    P = np.array([[r[1].get(lab, 0.0) for lab in labels] for r in rows], np.float16)
    return t, P, labels


def compute(path: Path, log=print) -> dict:
    log("  extras: loudness, key, centroid, waveform …")
    f = _stream_features(path, log)
    ms = f["ms"]
    def lufs(win):
        k = max(1, int(round(win * RATE)))
        m = np.convolve(ms, np.ones(k) / k, mode="same")
        return (-0.691 + 10 * np.log10(m + 1e-12)).astype(np.float32)
    kt, kc = _keys(f["chroma"])
    out = {"rate": RATE, "lufs_m": lufs(0.4), "lufs_s": lufs(3.0), "centroid": f["centroid"].astype(np.float32),
           "wave": f["wave"].astype(np.float32), "key_t": kt.astype(np.float32), "key_code": np.array(kc),
           "duration": f["n_samples"] / SR}
    try:
        log("  extras: on-device sound classifier (Core ML) …")
        t, P, labels = classify_sounds(path, log)
        out.update({"sa_t": t, "sa_p": P, "sa_labels": np.array(labels)})
    except Exception as e:  # noqa: BLE001  (not on macOS, or framework missing)
        log(f"  sound classifier unavailable ({type(e).__name__}); sound-triggered events use audio features only")
        out.update({"sa_t": np.zeros(0, np.float32), "sa_p": np.zeros((0, 0), np.float16), "sa_labels": np.array([])})
    return out


def load_or_compute(path: Path, audio_hash: str, cache_dir: Path, log=print) -> tuple[dict, Path]:
    cp = cache_dir / f"extras-v{EXTRAS_VERSION}-{audio_hash[:16]}.npz"
    if cp.exists():
        z = np.load(cp, allow_pickle=False)
        return {k: z[k] for k in z.files}, cp
    d = compute(path, log)
    cp.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(cp, **d)
    z = np.load(cp, allow_pickle=False)
    return {k: z[k] for k in z.files}, cp


def info(d: dict) -> dict:
    return {"duration": float(d["duration"]), "sound_classes": int(len(d["sa_labels"])),
            "sound_windows": int(len(d["sa_t"])), "keys": sorted(set(map(str, d["key_code"])))[:8]}


if __name__ == "__main__":
    import sys
    d = compute(Path(sys.argv[1]))
    print(json.dumps(info(d), indent=1))
