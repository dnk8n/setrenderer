"""ffmpeg encoding: raw frames on stdin + original audio -> YouTube-ready file."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .audio import AudioInfo, require_tool

RESOLUTIONS = {"720p": (1280, 720), "1080p": (1920, 1080), "1440p": (2560, 1440), "2160p": (3840, 2160), "4k": (3840, 2160)}

# rough video bitrates (bit/s at 1080p60) used only for the disk-space estimate
EST_BPS = {"youtube": 16e6, "high": 30e6, "draft": 5e6, "lossless": 400e6}


def parse_resolution(s: str) -> tuple[int, int]:
    if s.lower() in RESOLUTIONS:
        return RESOLUTIONS[s.lower()]
    w, h = s.lower().split("x")
    return int(w), int(h)


def audio_args(info: AudioInfo, codec: str) -> list[str]:
    if codec == "aac":
        return ["-c:a", "aac", "-b:a", "384k", "-ar", "48000"]
    if codec == "flac":
        return ["-c:a", "flac"]
    # lossless PCM, same bit depth as the source
    pcm = {16: "pcm_s16le", 24: "pcm_s24le", 32: "pcm_s32le"}.get(info.bits, "pcm_s24le")
    if info.codec.startswith("pcm_f"):
        pcm = "pcm_f32le"
    return ["-c:a", pcm]


def container_for(quality: str, audio_codec: str) -> str:
    if quality == "lossless":
        return ".mkv"
    return ".mp4" if audio_codec == "aac" else ".mov"


def estimate_bytes(quality: str, duration: float, out_wh, fps: float, info: AudioInfo, audio_codec: str) -> int:
    px_scale = (out_wh[0] * out_wh[1]) / (1920 * 1080) * (fps / 60)
    v = EST_BPS.get(quality, 16e6) * px_scale
    a = 384e3 if audio_codec == "aac" else info.sample_rate * info.channels * max(info.bits, 16)
    return int((v + a) * duration / 8)


def free_bytes(path: Path) -> int:
    return shutil.disk_usage(path if path.exists() else path.parent).free


def video_args(in_wh, out_wh, fps: float, quality: str, encoder: str, crf, preset, crt: float,
               enc_threads: int = 4) -> list[str]:
    """Filter chain + encoder. Colour conversion happens at the small internal size (cheap), then a
    nearest-neighbour upscale; 4:2:0 subsampling after the upscale keeps pixel edges exact."""
    W, H = in_wh
    OW, OH = out_wh
    line = max(2, OH // H)
    grid = [f"drawgrid=w=iw:h={line}:t=1:c=black@{crt:.3f}"] if crt > 0 else []
    if quality == "lossless":
        vf = [f"scale={OW}:{OH}:flags=neighbor"] + grid + ["format=gbrp"]
        venc = ["-c:v", "ffv1", "-level", "3", "-g", "1", "-slices", "16", "-slicecrc", "1",
                "-threads", str(enc_threads)]
    else:
        vf = ["scale=out_color_matrix=bt709:out_range=tv", "format=yuv444p",
              f"scale={OW}:{OH}:flags=neighbor", "format=yuv420p"] + grid
        gop = max(1, int(round(fps / 2)))
        color = ["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]
        if encoder == "vt":
            # Apple media engine (hardware): almost no CPU
            q = {"draft": 50, "youtube": 70, "high": 80}.get(quality, 70) if crf is None else int(crf)
            venc = ["-c:v", "h264_videotoolbox", "-profile:v", "high", "-q:v", str(q),
                    "-g", str(gop), "-bf", "0", "-prio_speed", "0"] + color
        else:
            c = {"draft": 26, "youtube": 16, "high": 12}.get(quality, 16) if crf is None else crf
            p = preset or {"draft": "veryfast", "youtube": "faster", "high": "medium"}.get(quality, "faster")
            venc = ["-c:v", "libx264", "-preset", p, "-crf", f"{c}", "-profile:v", "high",
                    "-g", str(gop), "-keyint_min", str(gop), "-bf", "2", "-flags", "+cgop",
                    "-x264-params", f"scenecut=0:threads={enc_threads}:lookahead_threads=1:"
                                    "colorprim=bt709:transfer=bt709:colormatrix=bt709",
                    "-pix_fmt", "yuv420p"] + color
    return ["-filter_threads", "1", "-vf", ",".join(vf)] + venc


def raw_input_args(in_wh, fps: float) -> list[str]:
    W, H = in_wh
    return ["-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-framerate", f"{fps}",
            "-thread_queue_size", "64", "-i", "-"]


def direct_cmd(out: Path, vargs, in_wh, fps, info: AudioInfo, start, duration, audio_codec) -> list[str]:
    cmd = [require_tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    cmd += raw_input_args(in_wh, fps)
    cmd += ["-ss", f"{start:.6f}", "-t", f"{duration:.6f}", "-i", str(info.path)]
    cmd += ["-map", "0:v:0", "-map", "1:a:0"] + vargs + audio_args(info, audio_codec)
    if out.suffix in (".mov", ".mp4"):
        cmd += ["-movflags", "+faststart+write_colr"]
    return cmd + [str(out)]


def segment_cmd(out: Path, vargs, in_wh, fps) -> list[str]:
    cmd = [require_tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    return cmd + raw_input_args(in_wh, fps) + vargs + [str(out)]


def mux_cmd(out: Path, list_file: Path, info: AudioInfo, start, duration, audio_codec) -> list[str]:
    cmd = [require_tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
           "-f", "concat", "-safe", "0", "-i", str(list_file),
           "-ss", f"{start:.6f}", "-t", f"{duration:.6f}", "-i", str(info.path),
           "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy"] + audio_args(info, audio_codec)
    if out.suffix != ".mkv":
        # stamp BT.709 into the H.264 VUI (the hardware encoder leaves primaries/transfer unset)
        cmd += ["-bsf:v", "h264_metadata=colour_primaries=1:transfer_characteristics=1:matrix_coefficients=1",
                "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv"]
    if out.suffix in (".mov", ".mp4"):
        cmd += ["-movflags", "+faststart+write_colr"]
    return cmd + [str(out)]


def tool_versions() -> dict:
    import platform
    out = {"python": platform.python_version(), "platform": platform.platform()}
    try:
        v = subprocess.run([require_tool("ffmpeg"), "-version"], capture_output=True, text=True).stdout.splitlines()[0]
        out["ffmpeg"] = v
    except Exception:  # noqa: BLE001
        pass
    for mod in ("numpy", "scipy", "librosa", "pygame", "yaml"):
        try:
            m = __import__(mod)
            out[mod] = getattr(m, "__version__", getattr(m, "version", "?"))
            if mod == "pygame":
                out[mod] = m.version.ver
        except Exception:  # noqa: BLE001
            pass
    return out
