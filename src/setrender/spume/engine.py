"""Offscreen WebGPU renderer for spume: one full-screen pass draws the foam into a half-float canvas, a
quarter-size blur chain gives the bloom, a post pass grades it, and the frame is converted to BT.709 NV12
on the GPU so it goes straight to the hardware encoder (or read back as RGBA for stills and checks)."""
from __future__ import annotations

import numpy as np
import wgpu

from . import film, shaders

HDR = "rgba16float"
NU = 21                     # vec4s in the uniform block (see shaders.COMMON)

U = wgpu.BufferUsage
TU = wgpu.TextureUsage
SS = wgpu.ShaderStage


class Engine:
    def __init__(self, width: int, height: int, lut: np.ndarray | None = None):
        self.W, self.H = int(width), int(height)
        adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
        self.adapter_info = dict(adapter.info)
        self.dev = d = adapter.request_device_sync()
        self.q = d.queue
        self.ubuf = d.create_buffer(size=NU * 16, usage=U.UNIFORM | U.COPY_DST)
        self.samp = d.create_sampler(mag_filter="linear", min_filter="linear",
                                     address_mode_u="clamp-to-edge", address_mode_v="clamp-to-edge")
        lut = film.table() if lut is None else lut
        self.lut = d.create_texture(size=(lut.shape[1], lut.shape[0], 1), format=HDR,
                                    usage=TU.TEXTURE_BINDING | TU.COPY_DST)
        self.q.write_texture({"texture": self.lut, "mip_level": 0, "origin": (0, 0, 0)},
                             np.ascontiguousarray(lut.astype(np.float16)).tobytes(),
                             {"offset": 0, "bytes_per_row": lut.shape[1] * 8, "rows_per_image": lut.shape[0]},
                             (lut.shape[1], lut.shape[0], 1))

        def mk(w, h, f, extra=0):
            return d.create_texture(size=(w, h, 1), format=f, usage=TU.RENDER_ATTACHMENT | TU.TEXTURE_BINDING | extra)
        self.canvas = mk(self.W, self.H, HDR)
        bw, bh = max(1, self.W // 4), max(1, self.H // 4)
        self.b1, self.b2 = mk(bw, bh, HDR), mk(bw, bh, HDR)
        self.final = mk(self.W, self.H, HDR)
        self.rgba = mk(self.W, self.H, "rgba8unorm", TU.COPY_SRC)
        self.ytex = mk(self.W, self.H, "r8unorm", TU.COPY_SRC)
        self.uvtex = mk(self.W // 2, self.H // 2, "rg8unorm", TU.COPY_SRC)
        self._build(bw, bh)
        self.pitch = (self.W + 255) // 256 * 256
        self.rb = d.create_buffer(size=self.pitch * (self.H + self.H // 2), usage=U.COPY_DST | U.MAP_READ)
        self.pitch4 = (self.W * 4 + 255) // 256 * 256
        self.rb4 = d.create_buffer(size=self.pitch4 * self.H, usage=U.COPY_DST | U.MAP_READ)

    def _build(self, bw, bh):
        d = self.dev
        tex = {"sample_type": "float", "view_dimension": "2d"}
        bgl0 = d.create_bind_group_layout(entries=[
            {"binding": 0, "visibility": SS.VERTEX | SS.FRAGMENT, "buffer": {"type": "uniform"}},
            {"binding": 1, "visibility": SS.FRAGMENT, "texture": tex},
            {"binding": 2, "visibility": SS.FRAGMENT, "sampler": {"type": "filtering"}}])
        self.bg0 = d.create_bind_group(layout=bgl0, entries=[
            {"binding": 0, "resource": {"buffer": self.ubuf, "offset": 0, "size": NU * 16}},
            {"binding": 1, "resource": self.lut.create_view()},
            {"binding": 2, "resource": self.samp}])
        sm = d.create_shader_module(code=shaders.SCENE)
        self.p_scene = d.create_render_pipeline(
            layout=d.create_pipeline_layout(bind_group_layouts=[bgl0]),
            vertex={"module": sm, "entry_point": "vs_full", "buffers": []},
            primitive={"topology": "triangle-list"},
            fragment={"module": sm, "entry_point": "fs_scene", "targets": [{"format": HDR}]})

        pm = d.create_shader_module(code=shaders.POST)
        bgl1 = d.create_bind_group_layout(entries=[
            {"binding": 0, "visibility": SS.FRAGMENT, "texture": tex},
            {"binding": 1, "visibility": SS.FRAGMENT, "texture": tex},
            {"binding": 2, "visibility": SS.FRAGMENT, "texture": tex},
            {"binding": 3, "visibility": SS.FRAGMENT, "buffer": {"type": "uniform"}}])
        pl = d.create_pipeline_layout(bind_group_layouts=[bgl0, bgl1])

        def pipe(fs, fmt):
            return d.create_render_pipeline(layout=pl, vertex={"module": pm, "entry_point": "vs_full", "buffers": []},
                                            primitive={"topology": "triangle-list"},
                                            fragment={"module": pm, "entry_point": fs, "targets": [{"format": fmt}]})
        self.p_bright, self.p_blur, self.p_post = pipe("fs_bright", HDR), pipe("fs_blur", HDR), pipe("fs_post", HDR)
        self.p_y, self.p_uv, self.p_rgba = pipe("fs_y", "r8unorm"), pipe("fs_uv", "rg8unorm"), pipe("fs_rgba", "rgba8unorm")

        def bg(src, blur, fin, dirv):
            ub = d.create_buffer_with_data(data=np.array(dirv, np.float32), usage=U.UNIFORM)
            return d.create_bind_group(layout=bgl1, entries=[
                {"binding": 0, "resource": src.create_view()},
                {"binding": 1, "resource": blur.create_view()},
                {"binding": 2, "resource": fin.create_view()},
                {"binding": 3, "resource": {"buffer": ub, "offset": 0, "size": 16}}])
        self.bg_bright = bg(self.canvas, self.b2, self.b2, [0, 0, 0, 0])
        self.bg_bh = bg(self.canvas, self.b1, self.final, [1 / bw, 0, 0, 0])
        self.bg_bv = bg(self.canvas, self.b2, self.final, [0, 1 / bh, 0, 0])
        self.bg_post = bg(self.canvas, self.b1, self.b2, [0, 0, 0, 0])
        self.bg_out = bg(self.canvas, self.b1, self.final, [0, 0, 0, 0])
        self.views = {k: getattr(self, k).create_view() for k in ("canvas", "b1", "b2", "final", "rgba", "ytex", "uvtex")}

    def _pass(self, enc, target, pipeline, bg):
        p = enc.begin_render_pass(color_attachments=[{"view": self.views[target], "load_op": "clear",
                                                      "store_op": "store", "clear_value": (0, 0, 0, 1)}])
        p.set_pipeline(pipeline)
        p.set_bind_group(0, self.bg0)
        if bg is not None:
            p.set_bind_group(1, bg)
        p.draw(3)
        p.end()

    def render(self, uni: np.ndarray, out: str = "nv12"):
        """uni: (NU * 4,) float32 uniforms for this frame. Returns NV12 bytes, or RGBA bytes with out='rgba'."""
        d, q = self.dev, self.q
        q.write_buffer(self.ubuf, 0, np.ascontiguousarray(uni, np.float32).tobytes())
        enc = d.create_command_encoder()
        self._pass(enc, "canvas", self.p_scene, None)
        self._pass(enc, "b1", self.p_bright, self.bg_bright)
        self._pass(enc, "b2", self.p_blur, self.bg_bh)
        self._pass(enc, "b1", self.p_blur, self.bg_bv)
        self._pass(enc, "final", self.p_post, self.bg_post)
        if out == "nv12":
            self._pass(enc, "ytex", self.p_y, self.bg_out)
            self._pass(enc, "uvtex", self.p_uv, self.bg_out)
            enc.copy_texture_to_buffer({"texture": self.ytex, "mip_level": 0, "origin": (0, 0, 0)},
                                       {"buffer": self.rb, "offset": 0, "bytes_per_row": self.pitch,
                                        "rows_per_image": self.H}, (self.W, self.H, 1))
            enc.copy_texture_to_buffer({"texture": self.uvtex, "mip_level": 0, "origin": (0, 0, 0)},
                                       {"buffer": self.rb, "offset": self.pitch * self.H, "bytes_per_row": self.pitch,
                                        "rows_per_image": self.H // 2}, (self.W // 2, self.H // 2, 1))
        else:
            self._pass(enc, "rgba", self.p_rgba, self.bg_out)
            enc.copy_texture_to_buffer({"texture": self.rgba, "mip_level": 0, "origin": (0, 0, 0)},
                                       {"buffer": self.rb4, "offset": 0, "bytes_per_row": self.pitch4,
                                        "rows_per_image": self.H}, (self.W, self.H, 1))
        q.submit([enc.finish()])
        buf, pitch, rows, width = ((self.rb, self.pitch, self.H + self.H // 2, self.W) if out == "nv12"
                                   else (self.rb4, self.pitch4, self.H, self.W * 4))
        buf.map_sync(wgpu.MapMode.READ)
        try:
            a = np.frombuffer(buf.read_mapped(), np.uint8).reshape(rows, pitch)
            return a[:, :width].tobytes()
        finally:
            buf.unmap()
