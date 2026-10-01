"""Scene engines. A template picks one with `engine:` (default: the pygame pixel-art engine)."""
from __future__ import annotations

from pathlib import Path


class _PygameScene:
    pix_fmt = "rgb24"

    def __init__(self, scene):
        import pygame
        self._pg = pygame
        self.scene = scene

    def frame(self, i: int) -> bytes:
        return self._pg.image.tobytes(self.scene.render(i), "RGB")


class _GpuScene:
    pix_fmt = "rgba"

    def __init__(self, scene):
        self.scene = scene

    def frame(self, i: int) -> bytes:
        return bytes(self.scene.render(i))


def engine_of(cfg: dict) -> str:
    return str(cfg.get("engine", "pixel"))


def pix_fmt(cfg: dict) -> str:
    return "rgba" if engine_of(cfg) == "cropcircle" else "rgb24"


def make(cfg: dict, tl, an, rng, title: str):
    if engine_of(cfg) == "cropcircle":
        from .crop.scene import CropScene
        return _GpuScene(CropScene(cfg, tl, an, rng, title, an.fingerprint))
    from .scene import Scene
    return _PygameScene(Scene(cfg, tl, rng, title, an.fingerprint))


def prepare(cfg: dict, src: Path, audio_hash: str, start: float, cache_dir: Path, log) -> dict:
    """Work that must happen once, in the parent process, before frames render (extra analysis)."""
    if engine_of(cfg) != "cropcircle":
        return {}
    from . import audio
    from .crop import extras
    total = audio.probe(src).duration
    ex, path = extras.load_or_compute(src, audio_hash, cache_dir, log)
    info = extras.info(ex)
    log(f"extras: {info['sound_windows']} sound-classifier windows, keys {', '.join(info['keys'][:4])} …")
    cfg["_clip"] = {"start": float(start), "total": float(total), "extras": str(path)}
    out = {"name": "cropcircle", "extras_cache": path.name, "set_duration": total,
           "sound_classifier": ("Apple SoundAnalysis built-in classifier v1 (Core ML, on-device), "
                                f"{info['sound_classes']} classes, {info['sound_windows']} windows")
           if info["sound_classes"] else "unavailable"}
    try:
        import wgpu
        a = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
        out["gpu"] = {k: a.info.get(k) for k in ("device", "backend_type", "adapter_type")}
        out["wgpu"] = wgpu.__version__
    except Exception as e:  # noqa: BLE001
        out["gpu"] = f"unavailable: {e}"
    return out
