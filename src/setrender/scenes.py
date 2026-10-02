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


class _Nv12Scene:
    """Frames arrive already converted to BT.709 NV12 on the GPU."""
    pix_fmt = "nv12"

    def __init__(self, scene):
        self.scene = scene

    def frame(self, i: int) -> bytes:
        return self.scene.frame(i)

    def frame_rgba(self, i: int) -> bytes:
        return self.scene.frame_rgba(i)


def engine_of(cfg: dict) -> str:
    return str(cfg.get("engine", "pixel"))


def gpu(cfg: dict) -> bool:
    return engine_of(cfg) in ("cropcircle", "rubberhose")


def native(cfg: dict) -> bool:
    """Engines that draw at the output resolution, in absolute set time (a slice renders the same
    frames as the full render), and hand over YUV frames."""
    return engine_of(cfg) == "rubberhose"


def pix_fmt(cfg: dict) -> str:
    return {"cropcircle": "rgba", "rubberhose": "nv12"}.get(engine_of(cfg), "rgb24")


def make(cfg: dict, tl, an, rng, title: str):
    if engine_of(cfg) == "rubberhose":
        from .hose.scene import HoseScene
        return _Nv12Scene(HoseScene(cfg, tl, an, rng, title, an.fingerprint))
    if engine_of(cfg) == "cropcircle":
        from .crop.scene import CropScene
        return _GpuScene(CropScene(cfg, tl, an, rng, title, an.fingerprint))
    from .scene import Scene
    return _PygameScene(Scene(cfg, tl, rng, title, an.fingerprint))


def prepare(cfg: dict, src: Path, audio_hash: str, start: float, cache_dir: Path, log) -> dict:
    """Work that must happen once, in the parent process, before frames render (extra analysis)."""
    if engine_of(cfg) == "rubberhose":
        return _prepare_hose(cfg, src, audio_hash, start, cache_dir, log)
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


def _prepare_hose(cfg: dict, src: Path, audio_hash: str, start: float, cache_dir: Path, log) -> dict:
    """rubberhose plans the whole cartoon from the whole set, so a slice needs the full analysis
    (cached) and the sound classifier's events (Core ML on the Neural Engine, cached)."""
    from . import analysis, audio
    from .crop import extras
    total = audio.probe(src).duration
    bands = cfg.get("bands") or analysis.DEFAULT_BANDS
    cpath = cache_dir / f"analysis-{analysis.cache_key(audio_hash, 0.0, None, bands)}.npz"
    if not cpath.exists():
        log("analysis of the whole set (rubberhose plans acts from it): running")
        a = analysis.analyse(src, 0.0, None, bands, log=log)
        analysis.save(a, cpath)
    ex, path = extras.load_or_compute(src, audio_hash, cache_dir, log)
    info = extras.info(ex)
    cfg["_clip"] = {**(cfg.get("_clip") or {}), "start": float(start), "total": float(total),
                    "analysis": str(cpath), "extras": str(path)}
    out = {"name": "rubberhose", "analysis_cache": cpath.name, "extras_cache": path.name, "set_duration": total,
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


def highlight_hints(cfg: dict, title: str, rng):
    """Template-specific highlight moments for `setrender reel` (needs prepare() first)."""
    if engine_of(cfg) == "rubberhose":
        from .hose.scene import highlight_hints as hh
        return hh(cfg, title, rng)
    return [], None, None
