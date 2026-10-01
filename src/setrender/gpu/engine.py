"""Offscreen GPU renderer: WebGPU (wgpu-native on Metal) with a supersampled HDR scene pass,
a bloom chain, a graded/dithered composite and a pixel-space HUD. Deterministic: every frame is a
pure function of the data handed to `render`.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import wgpu

from . import shaders

FRAME_FLOATS = 112 + 24 * 16
POST_FLOATS = 28
MAX_LIGHTS = 24
MESH_INST = 24      # floats per mesh instance (6 x vec4)
SPRITE_INST = 16
GLOW_INST = 20
HUD_INST = 12

HDR = "rgba16float"
DEPTH = "depth32float"
OUT = "rgba8unorm"

U = wgpu.BufferUsage
TU = wgpu.TextureUsage
SS = wgpu.ShaderStage


@dataclass
class FrameData:
    uniforms: np.ndarray
    post: np.ndarray
    mesh: dict = field(default_factory=dict)     # mesh name -> (k, 24) instances, opaque
    jelly: dict = field(default_factory=dict)    # mesh name -> (k, 24) instances, additive
    sprites: np.ndarray | None = None            # (k, 16)
    shadows: np.ndarray | None = None            # (k, 16)
    glows: np.ndarray | None = None              # (k, 20)
    hud: np.ndarray | None = None                # (k, 12)


class MeshLibrary:
    """All static geometry in one vertex/index buffer; meshes are addressed by name."""

    def __init__(self):
        self.verts: list[np.ndarray] = []
        self.idx: list[np.ndarray] = []
        self.ranges: dict[str, tuple[int, int, int]] = {}
        self._nv = 0
        self._ni = 0

    def add(self, name: str, v: np.ndarray, i: np.ndarray):
        """v: (n, 12) float32 = pos3 nrm3 uv2 col4;  i: (m,) uint32"""
        v = np.ascontiguousarray(v, np.float32)
        i = np.ascontiguousarray(i, np.uint32)
        self.ranges[name] = (self._ni, len(i), self._nv)
        self.verts.append(v)
        self.idx.append(i)
        self._nv += len(v)
        self._ni += len(i)


def _vlayout_mesh():
    f4 = "float32x4"
    return [
        {"array_stride": 48, "step_mode": "vertex", "attributes": [
            {"format": "float32x3", "offset": 0, "shader_location": 0},
            {"format": "float32x3", "offset": 12, "shader_location": 1},
            {"format": "float32x2", "offset": 24, "shader_location": 2},
            {"format": f4, "offset": 32, "shader_location": 3}]},
        {"array_stride": MESH_INST * 4, "step_mode": "instance", "attributes": [
            {"format": f4, "offset": 16 * k, "shader_location": 4 + k} for k in range(6)]},
    ]


def _vlayout_inst(n_vec4: int):
    return [{"array_stride": n_vec4 * 16, "step_mode": "instance", "attributes": [
        {"format": "float32x4", "offset": 16 * k, "shader_location": k} for k in range(n_vec4)]}]


ADD = {"color": {"src_factor": "one", "dst_factor": "one", "operation": "add"},
       "alpha": {"src_factor": "one", "dst_factor": "one", "operation": "add"}}
ALPHA = {"color": {"src_factor": "src-alpha", "dst_factor": "one-minus-src-alpha", "operation": "add"},
         "alpha": {"src_factor": "one", "dst_factor": "one-minus-src-alpha", "operation": "add"}}


class Engine:
    def __init__(self, width: int, height: int, ssaa: int, atlas: np.ndarray, cropmap: np.ndarray,
                 meshes: MeshLibrary):
        self.W, self.H, self.ss = width, height, max(1, int(ssaa))
        self.SW, self.SH = self.W * self.ss, self.H * self.ss
        adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
        self.adapter_info = dict(adapter.info)
        self.dev = d = adapter.request_device_sync()
        self.q = d.queue

        # ---- static resources
        self.atlas = self._texture(atlas, "rgba8unorm")
        self.crop = self._texture(cropmap, "rgba8unorm")
        self.samp_n = d.create_sampler(mag_filter="nearest", min_filter="nearest",
                                       address_mode_u="clamp-to-edge", address_mode_v="clamp-to-edge")
        self.samp_l = d.create_sampler(mag_filter="linear", min_filter="linear",
                                       address_mode_u="clamp-to-edge", address_mode_v="clamp-to-edge")
        self.ubuf = d.create_buffer(size=FRAME_FLOATS * 4, usage=U.UNIFORM | U.COPY_DST)
        self.cbuf = d.create_buffer(size=65 * 16, usage=U.UNIFORM | U.COPY_DST)
        self.pbuf = d.create_buffer(size=POST_FLOATS * 4, usage=U.UNIFORM | U.COPY_DST)
        V = np.concatenate(meshes.verts) if meshes.verts else np.zeros((3, 12), np.float32)
        I = np.concatenate(meshes.idx) if meshes.idx else np.zeros(3, np.uint32)
        self.vbuf = d.create_buffer_with_data(data=V, usage=U.VERTEX)
        self.ibuf = d.create_buffer_with_data(data=I, usage=U.INDEX)
        self.mesh_ranges = meshes.ranges
        self.static: list[tuple[str, object, int]] = []   # (mesh, buffer, count)
        cap = {"mesh": 4 << 20, "sprite": 1 << 20, "glow": 2 << 20, "hud": 256 << 10}
        self.dyn = {k: d.create_buffer(size=v, usage=U.VERTEX | U.COPY_DST) for k, v in cap.items()}
        self.dyn_cap = cap

        # ---- targets
        self.hdr = d.create_texture(size=(self.SW, self.SH, 1), format=HDR,
                                    usage=TU.RENDER_ATTACHMENT | TU.TEXTURE_BINDING)
        self.depth = d.create_texture(size=(self.SW, self.SH, 1), format=DEPTH, usage=TU.RENDER_ATTACHMENT)
        bw, bh = max(1, self.W // 2), max(1, self.H // 2)
        cw, ch = max(1, self.W // 4), max(1, self.H // 4)
        mk = lambda w, h: d.create_texture(size=(w, h, 1), format=HDR,  # noqa: E731
                                           usage=TU.RENDER_ATTACHMENT | TU.TEXTURE_BINDING)
        self.b1, self.b1t = mk(bw, bh), mk(bw, bh)
        self.c1, self.c1t = mk(cw, ch), mk(cw, ch)
        self.bsize, self.csize = (bw, bh), (cw, ch)
        self.out = d.create_texture(size=(self.W, self.H, 1), format=OUT,
                                    usage=TU.RENDER_ATTACHMENT | TU.COPY_SRC)
        self.hdr_v, self.depth_v, self.out_v = self.hdr.create_view(), self.depth.create_view(), self.out.create_view()

        self._build_scene_pipelines()
        self._build_post_pipelines()

    # ------------------------------------------------------------------ setup helpers
    def _texture(self, img: np.ndarray, fmt: str):
        img = np.ascontiguousarray(img, np.uint8)
        h, w = img.shape[:2]
        t = self.dev.create_texture(size=(w, h, 1), format=fmt, usage=TU.TEXTURE_BINDING | TU.COPY_DST)
        self.q.write_texture({"texture": t, "mip_level": 0, "origin": (0, 0, 0)}, img,
                             {"offset": 0, "bytes_per_row": w * 4, "rows_per_image": h}, (w, h, 1))
        return t

    def set_crop_params(self, params: np.ndarray, field_rect: tuple[float, float, float, float]):
        a = np.zeros((65, 4), np.float32)
        a[:min(64, len(params))] = params[:64]
        a[64] = field_rect
        self.q.write_buffer(self.cbuf, 0, a.tobytes())

    def add_static(self, mesh: str, inst: np.ndarray):
        inst = np.ascontiguousarray(inst, np.float32).reshape(-1, MESH_INST)
        if len(inst) == 0:
            return
        b = self.dev.create_buffer_with_data(data=inst, usage=U.VERTEX)
        self.static.append((mesh, b, len(inst)))

    def _build_scene_pipelines(self):
        d = self.dev
        vis = SS.VERTEX | SS.FRAGMENT
        self.bgl0 = d.create_bind_group_layout(entries=[
            {"binding": 0, "visibility": vis, "buffer": {"type": "uniform"}},
            {"binding": 1, "visibility": vis, "texture": {"sample_type": "float", "view_dimension": "2d"}},
            {"binding": 2, "visibility": vis, "sampler": {"type": "filtering"}},
            {"binding": 3, "visibility": vis, "texture": {"sample_type": "float", "view_dimension": "2d"}},
            {"binding": 4, "visibility": vis, "buffer": {"type": "uniform"}},
            {"binding": 5, "visibility": vis, "sampler": {"type": "filtering"}},
        ])
        self.bg0 = d.create_bind_group(layout=self.bgl0, entries=[
            {"binding": 0, "resource": {"buffer": self.ubuf, "offset": 0, "size": self.ubuf.size}},
            {"binding": 1, "resource": self.atlas.create_view()},
            {"binding": 2, "resource": self.samp_n},
            {"binding": 3, "resource": self.crop.create_view()},
            {"binding": 4, "resource": {"buffer": self.cbuf, "offset": 0, "size": self.cbuf.size}},
            {"binding": 5, "resource": self.samp_l},
        ])
        pl = d.create_pipeline_layout(bind_group_layouts=[self.bgl0])
        ds_write = {"format": DEPTH, "depth_write_enabled": True, "depth_compare": "less"}
        ds_test = {"format": DEPTH, "depth_write_enabled": False, "depth_compare": "less"}
        ds_none = {"format": DEPTH, "depth_write_enabled": False, "depth_compare": "always"}
        prim = {"topology": "triangle-list", "cull_mode": "none"}

        def pipe(code, vs, fs, buffers, ds, blend=None):
            m = d.create_shader_module(code=code)
            tgt = {"format": HDR}
            if blend:
                tgt["blend"] = blend
            return d.create_render_pipeline(layout=pl, vertex={"module": m, "entry_point": vs, "buffers": buffers},
                                            primitive=prim, depth_stencil=ds, multisample={"count": 1},
                                            fragment={"module": m, "entry_point": fs, "targets": [tgt]})
        ds_sky = {"format": DEPTH, "depth_write_enabled": False, "depth_compare": "less-equal"}
        self.p_sky = pipe(shaders.SKY, "vs_full", "fs_sky", [], ds_sky)
        self.p_mesh = pipe(shaders.MESH, "vs_mesh", "fs_mesh", _vlayout_mesh(), ds_write)
        self.p_jelly = pipe(shaders.MESH, "vs_mesh", "fs_jelly", _vlayout_mesh(), ds_test, ADD)
        self.p_sprite = pipe(shaders.SPRITE, "vs_sprite", "fs_sprite", _vlayout_inst(4), ds_write)
        self.p_shadow = pipe(shaders.SPRITE, "vs_sprite", "fs_shadow", _vlayout_inst(4), ds_test, ALPHA)
        self.p_glow = pipe(shaders.GLOW, "vs_glow", "fs_glow", _vlayout_inst(5), ds_test, ADD)

    def _build_post_pipelines(self):
        d = self.dev
        self.pass_bgl = d.create_bind_group_layout(entries=[
            {"binding": 0, "visibility": SS.FRAGMENT, "buffer": {"type": "uniform"}},
            {"binding": 1, "visibility": SS.FRAGMENT, "texture": {"sample_type": "float", "view_dimension": "2d"}},
            {"binding": 2, "visibility": SS.FRAGMENT, "sampler": {"type": "filtering"}},
        ])
        ppl = d.create_pipeline_layout(bind_group_layouts=[self.pass_bgl])
        m = d.create_shader_module(code=shaders.POST)

        def fpipe(fs):
            return d.create_render_pipeline(layout=ppl, vertex={"module": m, "entry_point": "vs_full", "buffers": []},
                                            primitive={"topology": "triangle-list"},
                                            fragment={"module": m, "entry_point": fs, "targets": [{"format": HDR}]})
        self.p_bright, self.p_blur, self.p_copy = fpipe("fs_bright"), fpipe("fs_blur"), fpipe("fs_copy")
        bw, bh = self.bsize
        cw, ch = self.csize

        def pass_bg(src, vals):
            ub = d.create_buffer_with_data(data=np.array(vals, np.float32), usage=U.UNIFORM)
            return d.create_bind_group(layout=self.pass_bgl, entries=[
                {"binding": 0, "resource": {"buffer": ub, "offset": 0, "size": 16}},
                {"binding": 1, "resource": src.create_view()},
                {"binding": 2, "resource": self.samp_l}])
        self.bright_ub = d.create_buffer(size=16, usage=U.UNIFORM | U.COPY_DST)
        self.bg_bright = d.create_bind_group(layout=self.pass_bgl, entries=[
            {"binding": 0, "resource": {"buffer": self.bright_ub, "offset": 0, "size": 16}},
            {"binding": 1, "resource": self.hdr.create_view()},
            {"binding": 2, "resource": self.samp_l}])
        self.bg_b_h = pass_bg(self.b1, [1 / bw, 0, 0, 0])
        self.bg_b_v = pass_bg(self.b1t, [0, 1 / bh, 0, 0])
        self.bg_c_down = pass_bg(self.b1, [0, 0, 0, 0])
        self.bg_c_h = pass_bg(self.c1, [1 / cw, 0, 0, 0])
        self.bg_c_v = pass_bg(self.c1t, [0, 1 / ch, 0, 0])

        mc = d.create_shader_module(code=shaders.COMPOSITE)
        self.comp_bgl = d.create_bind_group_layout(entries=[
            {"binding": 0, "visibility": SS.FRAGMENT | SS.VERTEX, "buffer": {"type": "uniform"}},
            {"binding": 1, "visibility": SS.FRAGMENT, "texture": {"sample_type": "unfilterable-float", "view_dimension": "2d"}},
            {"binding": 2, "visibility": SS.FRAGMENT, "texture": {"sample_type": "float", "view_dimension": "2d"}},
            {"binding": 3, "visibility": SS.FRAGMENT, "texture": {"sample_type": "float", "view_dimension": "2d"}},
            {"binding": 4, "visibility": SS.FRAGMENT, "sampler": {"type": "filtering"}},
        ])
        self.hud_bgl = d.create_bind_group_layout(entries=[
            {"binding": 0, "visibility": SS.FRAGMENT, "texture": {"sample_type": "float", "view_dimension": "2d"}},
            {"binding": 1, "visibility": SS.FRAGMENT, "sampler": {"type": "filtering"}},
        ])
        self.bg_comp = d.create_bind_group(layout=self.comp_bgl, entries=[
            {"binding": 0, "resource": {"buffer": self.pbuf, "offset": 0, "size": self.pbuf.size}},
            {"binding": 1, "resource": self.hdr.create_view()},
            {"binding": 2, "resource": self.b1.create_view()},
            {"binding": 3, "resource": self.c1.create_view()},
            {"binding": 4, "resource": self.samp_l}])
        self.bg_hud = d.create_bind_group(layout=self.hud_bgl, entries=[
            {"binding": 0, "resource": self.atlas.create_view()},
            {"binding": 1, "resource": self.samp_n}])
        cpl = d.create_pipeline_layout(bind_group_layouts=[self.comp_bgl])
        hpl = d.create_pipeline_layout(bind_group_layouts=[self.comp_bgl, self.hud_bgl])
        self.p_comp = d.create_render_pipeline(
            layout=cpl, vertex={"module": mc, "entry_point": "vs_full", "buffers": []},
            primitive={"topology": "triangle-list"},
            fragment={"module": mc, "entry_point": "fs_comp", "targets": [{"format": OUT}]})
        self.p_hud = d.create_render_pipeline(
            layout=hpl, vertex={"module": mc, "entry_point": "vs_hud", "buffers": _vlayout_inst(3)},
            primitive={"topology": "triangle-list"},
            fragment={"module": mc, "entry_point": "fs_hud", "targets": [{"format": OUT, "blend": ALPHA}]})

    # ------------------------------------------------------------------ per frame
    def _upload(self, key: str, arrs: list[np.ndarray]) -> list[tuple[int, int]]:
        """Concatenate instance arrays into the dynamic buffer; returns (byte offset, count) per array."""
        out, blobs, off = [], [], 0
        for a in arrs:
            a = np.ascontiguousarray(a, np.float32)
            out.append((off, len(a)))
            blobs.append(a.reshape(-1))
            off += a.nbytes
        if off:
            if off > self.dyn_cap[key]:
                raise RuntimeError(f"too many {key} instances ({off} bytes)")
            self.q.write_buffer(self.dyn[key], 0, np.concatenate(blobs).tobytes())
        return out

    def render(self, fd: FrameData) -> memoryview:
        d, q = self.dev, self.q
        q.write_buffer(self.ubuf, 0, np.ascontiguousarray(fd.uniforms, np.float32).tobytes())
        q.write_buffer(self.pbuf, 0, np.ascontiguousarray(fd.post, np.float32).tobytes())
        q.write_buffer(self.bright_ub, 0, np.array([fd.post[24], fd.post[25], 1 / self.SW, 1 / self.SH], np.float32).tobytes())
        mesh_items = [(k, v) for k, v in fd.mesh.items() if v is not None and len(v)]
        jelly_items = [(k, v) for k, v in fd.jelly.items() if v is not None and len(v)]
        moffs = self._upload("mesh", [v for _, v in mesh_items] + [v for _, v in jelly_items])
        spr = [a for a in (fd.shadows, fd.sprites) if a is not None]
        soffs = self._upload("sprite", [fd.shadows if fd.shadows is not None else np.zeros((0, 16), np.float32),
                                        fd.sprites if fd.sprites is not None else np.zeros((0, 16), np.float32)])
        _ = spr
        goffs = self._upload("glow", [fd.glows if fd.glows is not None else np.zeros((0, 20), np.float32)])
        hoffs = self._upload("hud", [fd.hud if fd.hud is not None else np.zeros((0, 12), np.float32)])

        enc = d.create_command_encoder()
        rp = enc.begin_render_pass(
            color_attachments=[{"view": self.hdr_v, "load_op": "clear", "store_op": "store", "clear_value": (0, 0, 0, 1)}],
            depth_stencil_attachment={"view": self.depth_v, "depth_clear_value": 1.0, "depth_load_op": "clear",
                                      "depth_store_op": "store"})
        rp.set_bind_group(0, self.bg0)
        rp.set_pipeline(self.p_mesh)
        rp.set_vertex_buffer(0, self.vbuf)
        rp.set_index_buffer(self.ibuf, "uint32")
        for name, buf, n in self.static:
            fi, ic, bv = self.mesh_ranges[name]
            rp.set_vertex_buffer(1, buf)
            rp.draw_indexed(ic, n, fi, bv, 0)
        for (name, _), (off, n) in zip(mesh_items, moffs[:len(mesh_items)]):
            fi, ic, bv = self.mesh_ranges[name]
            rp.set_vertex_buffer(1, self.dyn["mesh"], off)
            rp.draw_indexed(ic, n, fi, bv, 0)
        (so, sn), (po, pn) = soffs
        if pn:
            rp.set_pipeline(self.p_sprite)
            rp.set_vertex_buffer(0, self.dyn["sprite"], po)
            rp.draw(6, pn)
        rp.set_pipeline(self.p_sky)      # sky last: only where nothing else was drawn
        rp.draw(3)
        if sn:
            rp.set_pipeline(self.p_shadow)
            rp.set_vertex_buffer(0, self.dyn["sprite"], so)
            rp.draw(6, sn)
        if jelly_items:
            rp.set_pipeline(self.p_jelly)
            rp.set_vertex_buffer(0, self.vbuf)
            for (name, _), (off, n) in zip(jelly_items, moffs[len(mesh_items):]):
                fi, ic, bv = self.mesh_ranges[name]
                rp.set_vertex_buffer(1, self.dyn["mesh"], off)
                rp.draw_indexed(ic, n, fi, bv, 0)
        go, gn = goffs[0]
        if gn:
            rp.set_pipeline(self.p_glow)
            rp.set_vertex_buffer(0, self.dyn["glow"], go)
            rp.draw(6, gn)
        rp.end()

        def fpass(target, pipeline, bg):
            p = enc.begin_render_pass(color_attachments=[{"view": target.create_view(), "load_op": "clear",
                                                          "store_op": "store", "clear_value": (0, 0, 0, 1)}])
            p.set_pipeline(pipeline)
            p.set_bind_group(0, bg)
            p.draw(3)
            p.end()
        fpass(self.b1, self.p_bright, self.bg_bright)
        fpass(self.b1t, self.p_blur, self.bg_b_h)
        fpass(self.b1, self.p_blur, self.bg_b_v)
        fpass(self.c1, self.p_copy, self.bg_c_down)
        fpass(self.c1t, self.p_blur, self.bg_c_h)
        fpass(self.c1, self.p_blur, self.bg_c_v)

        p = enc.begin_render_pass(color_attachments=[{"view": self.out_v, "load_op": "clear", "store_op": "store",
                                                      "clear_value": (0, 0, 0, 1)}])
        p.set_pipeline(self.p_comp)
        p.set_bind_group(0, self.bg_comp)
        p.draw(3)
        ho, hn = hoffs[0]
        if hn:
            p.set_pipeline(self.p_hud)
            p.set_bind_group(0, self.bg_comp)
            p.set_bind_group(1, self.bg_hud)
            p.set_vertex_buffer(0, self.dyn["hud"], ho)
            p.draw(6, hn)
        p.end()
        q.submit([enc.finish()])
        return q.read_texture({"texture": self.out, "mip_level": 0, "origin": (0, 0, 0)},
                              {"offset": 0, "bytes_per_row": self.W * 4, "rows_per_image": self.H},
                              (self.W, self.H, 1))
