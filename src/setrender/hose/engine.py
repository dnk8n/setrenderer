"""Offscreen WebGPU renderer for rubberhose: one pass of instanced distance-field primitives into a
half-float canvas, a small blur chain for halation and soft focus, the film pass, and an NV12
(BT.709, limited range) conversion so frames go straight to the hardware encoder."""
from __future__ import annotations

import numpy as np
import wgpu

from . import shaders

INST = 32                  # floats per primitive
FILM_FLOATS = 4 * (6 + 4 + 24 + 4)
HDR = "rgba16float"

U = wgpu.BufferUsage
TU = wgpu.TextureUsage
SS = wgpu.ShaderStage

PREMUL = {"color": {"src_factor": "one", "dst_factor": "one-minus-src-alpha", "operation": "add"},
          "alpha": {"src_factor": "one", "dst_factor": "one-minus-src-alpha", "operation": "add"}}


class Engine:
    def __init__(self, width: int, height: int, design=(1920, 1080), max_prims: int = 16384):
        self.W, self.H = int(width), int(height)
        self.design = design
        adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
        self.adapter_info = dict(adapter.info)
        self.dev = d = adapter.request_device_sync()
        self.q = d.queue
        self.max_prims = max_prims
        self.ibuf = d.create_buffer(size=max_prims * INST * 4, usage=U.VERTEX | U.COPY_DST)
        self.sbuf = d.create_buffer(size=32, usage=U.UNIFORM | U.COPY_DST)
        self.fbuf = d.create_buffer(size=FILM_FLOATS * 4, usage=U.UNIFORM | U.COPY_DST)
        self.samp = d.create_sampler(mag_filter="linear", min_filter="linear",
                                     address_mode_u="mirror-repeat", address_mode_v="mirror-repeat")

        mk = lambda w, h, f, extra=0: d.create_texture(  # noqa: E731
            size=(w, h, 1), format=f, usage=TU.RENDER_ATTACHMENT | TU.TEXTURE_BINDING | extra)
        self.canvas = mk(self.W, self.H, HDR)
        bw, bh = max(1, self.W // 4), max(1, self.H // 4)
        self.b1, self.b2 = mk(bw, bh, HDR), mk(bw, bh, HDR)
        self.final = mk(self.W, self.H, "rgba8unorm", TU.COPY_SRC)
        self.ytex = mk(self.W, self.H, "r8unorm", TU.COPY_SRC)
        self.uvtex = mk(self.W // 2, self.H // 2, "rg8unorm", TU.COPY_SRC)
        self._build(bw, bh)
        # one readback buffer for both NV12 planes (rows padded to 256 bytes)
        self.pitch = (self.W + 255) // 256 * 256
        self.rb = d.create_buffer(size=self.pitch * (self.H + self.H // 2), usage=U.COPY_DST | U.MAP_READ)
        self.pitch4 = (self.W * 4 + 255) // 256 * 256
        self.rb4 = d.create_buffer(size=self.pitch4 * self.H, usage=U.COPY_DST | U.MAP_READ)

    def _build(self, bw, bh):
        d = self.dev
        bgl0 = d.create_bind_group_layout(entries=[
            {"binding": 0, "visibility": SS.VERTEX | SS.FRAGMENT, "buffer": {"type": "uniform"}}])
        self.bg0 = d.create_bind_group(layout=bgl0, entries=[
            {"binding": 0, "resource": {"buffer": self.sbuf, "offset": 0, "size": 32}}])
        pm = d.create_shader_module(code=shaders.PRIM)
        layout = [{"array_stride": INST * 4, "step_mode": "instance", "attributes": [
            {"format": "float32x4", "offset": 16 * k, "shader_location": k} for k in range(8)]}]
        self.p_prim = d.create_render_pipeline(
            layout=d.create_pipeline_layout(bind_group_layouts=[bgl0]),
            vertex={"module": pm, "entry_point": "vs_prim", "buffers": layout},
            primitive={"topology": "triangle-list", "cull_mode": "none"},
            fragment={"module": pm, "entry_point": "fs_prim", "targets": [{"format": HDR, "blend": PREMUL}]})

        fm = d.create_shader_module(code=shaders.FILM)
        tex = {"sample_type": "float", "view_dimension": "2d"}
        bgl1 = d.create_bind_group_layout(entries=[
            {"binding": 0, "visibility": SS.FRAGMENT, "buffer": {"type": "uniform"}},
            {"binding": 1, "visibility": SS.FRAGMENT, "texture": tex},
            {"binding": 2, "visibility": SS.FRAGMENT, "texture": tex},
            {"binding": 3, "visibility": SS.FRAGMENT, "sampler": {"type": "filtering"}},
            {"binding": 4, "visibility": SS.FRAGMENT, "buffer": {"type": "uniform"}},
            {"binding": 5, "visibility": SS.FRAGMENT, "texture": tex},
        ])
        pl = d.create_pipeline_layout(bind_group_layouts=[bgl0, bgl1])

        def pipe(fs, fmt):
            return d.create_render_pipeline(layout=pl, vertex={"module": fm, "entry_point": "vs_full", "buffers": []},
                                            primitive={"topology": "triangle-list"},
                                            fragment={"module": fm, "entry_point": fs, "targets": [{"format": fmt}]})
        self.p_bright, self.p_blur = pipe("fs_bright", HDR), pipe("fs_blur", HDR)
        self.p_film = pipe("fs_film", "rgba8unorm")
        self.p_y, self.p_uv = pipe("fs_y", "r8unorm"), pipe("fs_uv", "rg8unorm")

        def bg(src, blur, dirv, fin):
            ub = d.create_buffer_with_data(data=np.array(dirv, np.float32), usage=U.UNIFORM)
            return d.create_bind_group(layout=bgl1, entries=[
                {"binding": 0, "resource": {"buffer": self.fbuf, "offset": 0, "size": FILM_FLOATS * 4}},
                {"binding": 1, "resource": src.create_view()},
                {"binding": 2, "resource": blur.create_view()},
                {"binding": 3, "resource": self.samp},
                {"binding": 4, "resource": {"buffer": ub, "offset": 0, "size": 16}},
                {"binding": 5, "resource": fin.create_view()}])
        # binding 5 is only read by the YUV passes; elsewhere it holds any texture the pass does not write
        self.bg_bright = bg(self.canvas, self.canvas, [0, 0, 0, 0], self.b2)
        self.bg_bh = bg(self.canvas, self.b1, [1 / bw, 0, 0, 0], self.final)
        self.bg_bv = bg(self.canvas, self.b2, [0, 1 / bh, 0, 0], self.final)
        self.bg_film = bg(self.canvas, self.b1, [0, 0, 0, 0], self.b2)
        self.bg_yuv = bg(self.canvas, self.b1, [0, 0, 0, 0], self.final)
        self.views = {k: getattr(self, k).create_view() for k in ("canvas", "b1", "b2", "final", "ytex", "uvtex")}

    def _pass(self, enc, target, pipeline, bg, clear=(0, 0, 0, 1)):
        p = enc.begin_render_pass(color_attachments=[{"view": self.views[target], "load_op": "clear",
                                                      "store_op": "store", "clear_value": clear}])
        p.set_pipeline(pipeline)
        p.set_bind_group(0, self.bg0)
        p.set_bind_group(1, bg)
        p.draw(3)
        p.end()

    def render(self, prims: np.ndarray, clock, film: np.ndarray, paper=(0.95, 0.9, 0.78), out: str = "nv12"):
        """prims: (n, 32) float32 in painter's order. Returns NV12 bytes, or RGBA bytes with out='rgba'."""
        d, q = self.dev, self.q
        n = min(len(prims), self.max_prims)
        q.write_buffer(self.sbuf, 0, np.array([self.W, self.H, self.design[0], self.design[1], *clock], np.float32).tobytes())
        q.write_buffer(self.fbuf, 0, np.ascontiguousarray(film, np.float32).tobytes())
        if n:
            q.write_buffer(self.ibuf, 0, np.ascontiguousarray(prims[:n], np.float32).tobytes())
        enc = d.create_command_encoder()
        rp = enc.begin_render_pass(color_attachments=[{"view": self.views["canvas"], "load_op": "clear",
                                                       "store_op": "store", "clear_value": (*paper, 1.0)}])
        if n:
            rp.set_pipeline(self.p_prim)
            rp.set_bind_group(0, self.bg0)
            rp.set_vertex_buffer(0, self.ibuf)
            rp.draw(6, n)
        rp.end()
        self._pass(enc, "b1", self.p_bright, self.bg_bright)
        self._pass(enc, "b2", self.p_blur, self.bg_bh)
        self._pass(enc, "b1", self.p_blur, self.bg_bv)
        self._pass(enc, "final", self.p_film, self.bg_film)
        if out == "nv12":
            self._pass(enc, "ytex", self.p_y, self.bg_yuv)
            self._pass(enc, "uvtex", self.p_uv, self.bg_yuv)
            enc.copy_texture_to_buffer({"texture": self.ytex, "mip_level": 0, "origin": (0, 0, 0)},
                                       {"buffer": self.rb, "offset": 0, "bytes_per_row": self.pitch,
                                        "rows_per_image": self.H}, (self.W, self.H, 1))
            enc.copy_texture_to_buffer({"texture": self.uvtex, "mip_level": 0, "origin": (0, 0, 0)},
                                       {"buffer": self.rb, "offset": self.pitch * self.H, "bytes_per_row": self.pitch,
                                        "rows_per_image": self.H // 2}, (self.W // 2, self.H // 2, 1))
        elif out == "rgba":
            enc.copy_texture_to_buffer({"texture": self.final, "mip_level": 0, "origin": (0, 0, 0)},
                                       {"buffer": self.rb4, "offset": 0, "bytes_per_row": self.pitch4,
                                        "rows_per_image": self.H}, (self.W, self.H, 1))
        q.submit([enc.finish()])
        if out == "none":
            return None
        buf, pitch, rows, width = ((self.rb, self.pitch, self.H + self.H // 2, self.W) if out == "nv12"
                                   else (self.rb4, self.pitch4, self.H, self.W * 4))
        buf.map_sync(wgpu.MapMode.READ)
        try:
            a = np.frombuffer(buf.read_mapped(), np.uint8).reshape(rows, pitch)
            return a[:, :width].tobytes()
        finally:
            buf.unmap()
