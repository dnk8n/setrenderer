"""Automated checks against CRITERIA.md for a rendered video."""
from __future__ import annotations

import json
import subprocess
from fractions import Fraction
from pathlib import Path

import numpy as np

from .audio import require_tool


def _probe(path: Path) -> dict:
    out = subprocess.run([require_tool("ffprobe"), "-v", "error", "-show_streams", "-show_format", "-of", "json",
                          str(path)], check=True, capture_output=True, text=True).stdout
    return json.loads(out)


def _keyframe_gap(path: Path, fps: float) -> int:
    out = subprocess.run([require_tool("ffprobe"), "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "packet=flags", "-of", "csv=p=0", str(path)], check=True, capture_output=True, text=True).stdout
    flags = [ln.startswith("K") for ln in out.split()]
    ks = [i for i, k in enumerate(flags) if k]
    ks.append(len(flags))
    return int(max(np.diff(ks))) if len(ks) > 1 else len(flags)


def _faststart(path: Path) -> bool:
    with open(path, "rb") as f:
        data = f.read(1 << 16)
    m, d = data.find(b"moov"), data.find(b"mdat")
    return m != -1 and (d == -1 or m < d)


def _audio_md5(path: Path, start=0.0, duration=None) -> str:
    cmd = [require_tool("ffmpeg"), "-v", "error", "-nostdin"]
    if start:
        cmd += ["-ss", f"{start:.6f}"]
    if duration is not None:
        cmd += ["-t", f"{duration:.6f}"]
    cmd += ["-i", str(path), "-map", "0:a:0", "-c:a", "pcm_s32le", "-f", "md5", "-"]
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()


def floor_signal(path: Path) -> np.ndarray:
    """Mean brightness of the dancefloor region per frame (streamed small, so a 2 h video is fine)."""
    cmd = ["nice", "-n", "10", require_tool("ffmpeg"), "-v", "error", "-nostdin", "-threads", "2",
           "-i", str(path), "-map", "0:v:0",
           "-vf", "crop=iw:ih*0.21:0:ih*0.72,scale=32:8:flags=area,format=gray", "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, check=True, capture_output=True).stdout
    return np.frombuffer(raw, np.uint8).reshape(-1, 8 * 32).astype(np.float32).mean(axis=1)


def frame_md5(path: Path) -> str:
    cmd = [require_tool("ffmpeg"), "-v", "error", "-nostdin", "-i", str(path), "-map", "0:v:0", "-f", "md5", "-"]
    return subprocess.run(cmd, check=True, capture_output=True, text=True).stdout.strip()


def beat_sync(floor: np.ndarray, beats: np.ndarray, fps: float, skip_s: float = 4.0) -> dict:
    """Pulse = rise in floor-region brightness. For each beat find the nearest pulse peak."""
    rise = np.maximum(np.diff(floor, prepend=floor[0]), 0)
    thr = np.percentile(rise, 75)
    peaks = np.where((rise > thr) & (rise >= np.roll(rise, 1)) & (rise >= np.roll(rise, -1)))[0]
    bf = np.floor(beats * fps).astype(int)
    bf = bf[(bf / fps > skip_s) & (bf < len(floor) - 1)]
    if len(bf) == 0 or len(peaks) == 0:
        return {"beats": int(len(bf)), "hit_rate": 0.0, "median_offset_frames": None}
    j = np.searchsorted(peaks, bf)
    cand = np.stack([peaks[np.clip(j - 1, 0, len(peaks) - 1)], peaks[np.clip(j, 0, len(peaks) - 1)]])
    off = cand - bf
    best = off[np.argmin(np.abs(off), axis=0), np.arange(len(bf))]
    return {"beats": int(len(bf)), "hit_rate": round(float((np.abs(best) <= 1).mean()), 4),
            "median_offset_frames": float(np.median(best))}


def run(video: Path, audio: Path | None, start: float = 0.0, duration: float | None = None) -> dict:
    j = _probe(video)
    vs = next(s for s in j["streams"] if s["codec_type"] == "video")
    as_ = next((s for s in j["streams"] if s["codec_type"] == "audio"), None)
    fps = float(Fraction(vs["r_frame_rate"]))
    rep: dict = {"video": str(video), "checks": {}}
    c = rep["checks"]
    is_lossless = vs["codec_name"] == "ffv1"
    if not is_lossless:
        c["A11_codec_h264_high"] = vs["codec_name"] == "h264" and vs.get("profile") == "High"
        c["A11_yuv420p"] = vs.get("pix_fmt") == "yuv420p"
        c["A11_progressive"] = vs.get("field_order", "progressive") == "progressive"
        c["A11_bt709"] = vs.get("color_space") == "bt709" and vs.get("color_primaries") == "bt709"
        gap = _keyframe_gap(video, fps)
        c["A11_closed_gop_le_half_fps"] = gap <= int(round(fps / 2))
        c["A11_faststart"] = _faststart(video)
    c["A11_resolution"] = f"{vs['width']}x{vs['height']}"
    c["A11_fps"] = fps
    vdur = float(vs.get("duration") or j["format"]["duration"])
    if as_:
        adur = float(as_.get("duration") or j["format"]["duration"])
        c["A7_av_duration_diff_frames"] = round(abs(vdur - adur) * fps, 3)
        c["A7_ok"] = abs(vdur - adur) * fps <= 1.0
        c["A12_audio_codec"] = as_["codec_name"]
    if audio and as_:
        src = _audio_md5(audio, start, duration if duration is not None else adur)
        dst = _audio_md5(video)
        c["A12_audio_sample_identical"] = src == dst
    if audio:
        from . import analysis
        from .cli import CACHE_DIR, get_analysis
        an, _, _ = get_analysis(audio, start, duration, None, False)
        c["A6_beat_sync"] = bs = beat_sync(floor_signal(video), an.beats, fps)
        c["A6_ok"] = bs["hit_rate"] >= 0.9 and bs["median_offset_frames"] is not None and abs(bs["median_offset_frames"]) <= 1
        _ = (analysis, CACHE_DIR)
    bools = [v for v in c.values() if isinstance(v, bool)]
    rep["pass"] = all(bools)
    return rep
