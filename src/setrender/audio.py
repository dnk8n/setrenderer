"""Audio decoding and probing via ffmpeg/ffprobe."""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass
class AudioInfo:
    path: Path
    duration: float
    sample_rate: int
    channels: int
    codec: str
    bits: int


def require_tool(name: str) -> str:
    p = shutil.which(name)
    if not p:
        raise SystemExit(f"setrender: '{name}' not found on PATH (install with: brew install ffmpeg)")
    return p


def probe(path: Path, start: float = 0.0, duration: float | None = None) -> AudioInfo:
    out = subprocess.run(
        [require_tool("ffprobe"), "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=sample_rate,channels,codec_name,bits_per_sample,bits_per_raw_sample:format=duration",
         "-of", "json", str(path)],
        check=True, capture_output=True, text=True,
    ).stdout
    j = json.loads(out)
    if not j.get("streams"):
        raise SystemExit(f"setrender: no audio stream in {path}")
    s = j["streams"][0]
    total = float(j["format"]["duration"])
    dur = max(0.0, total - start)
    if duration is not None:
        dur = min(dur, duration)
    bits = int(s.get("bits_per_sample") or s.get("bits_per_raw_sample") or 16)
    return AudioInfo(path, dur, int(s["sample_rate"]), int(s["channels"]), s["codec_name"], bits)


def decode_mono(path: Path, sr: int, start: float = 0.0, duration: float | None = None) -> np.ndarray:
    """Decode to mono float32 at `sr` using ffmpeg (deterministic resampler)."""
    cmd = [require_tool("ffmpeg"), "-nostdin", "-v", "error", "-ss", f"{start:.6f}"]
    if duration is not None:
        cmd += ["-t", f"{duration:.6f}"]
    cmd += ["-i", str(path), "-ac", "1", "-ar", str(sr), "-af", "aresample=resampler=soxr",
            "-f", "f32le", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(raw, dtype=np.float32).copy()


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8 << 20):
            h.update(chunk)
    return h.hexdigest()
