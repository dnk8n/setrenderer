"""Offscreen WebGPU renderer for crucible. A frame is a list of draws in layers: the backdrop, lit 3D meshes
(instanced, with a sun shadow map, plus per-frame triangle soups for soft bodies), the pixel layer (drawn at
320x180 and scaled up by whole pixels), the 2D world (triangles, signed-distance shapes, images) and the
overlay (text and charts in their own 8-bit target, laid over the graded picture). Everything is 4x
multisampled; the frame is graded and converted to BT.709 NV12 on the GPU (or read back as RGBA)."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import wgpu

from . import shaders

HDR = "rgba16float"
LDR = "rgba8unorm"
DEPTH = "depth32float"
NU = 32                      # vec4s in the uniform block (see shaders.COMMON; 28 used)
MSAA = 4
PIX_W, PIX_H = 320, 180      # the pixel-art layer (6x up to 1080p)
SHADOW = 2048

U = wgpu.BufferUsage
TU = wgpu.TextureUsage
SS = wgpu.ShaderStage

POLY_F = 7                   # x, y, r, g, b, a, space
INST_F = 16                  # four vec4s per shape, image or glyph
MESH_V = 10                  # position, normal, colour
MESH_I = 20                  # three rows of the affine, colour, extra (emissive, matte, -, -)

ALPHA = {"color": {"src_factor": "src-alpha", "dst_factor": "one-minus-src-alpha", "operation": "add"},
         "alpha": {"src_factor": "one", "dst_factor": "one-minus-src-alpha", "operation": "add"}}


@dataclass
class Layer:
    """Draws in order: ("poly", (n, 7)), ("sdf", (n, 16)), ("img", key, (n, 16)), ("glyph", (n, 16))."""
    items: list = field(default_factory=list)

    def add(self, kind: str, arr: np.ndarray, key: str | None = None):
        if arr is None or len(arr) == 0:
            return
        a = np.ascontiguousarray(arr, np.float32)
        if self.items and self.items[-1][0] == kind and kind in ("poly", "sdf", "glyph") and kind != "img":
            self.items[-1] = (kind, np.concatenate([self.items[-1][1], a]), None)
        else:
            self.items.append((kind, a, key))


@dataclass
class Frame:
    uni: np.ndarray
    backdrop: bool = True
    shadow: bool = False
    meshes: list = field(default_factory=list)       # (mesh name, instances (n, 20), translucent)
    soup: list = field(default_factory=list)         # (vertices (n, 10) as triangles, translucent)
    pixel: Layer | None = None
    pixel_rect: tuple = (0.0, 0.0, 1920.0, 1080.0)
    world: Layer = field(default_factory=Layer)
    hud: Layer = field(default_factory=Layer)


def _mesh_layout():
    return [{"array_stride": MESH_V * 4, "step_mode": "vertex",
             "attributes": [{"format": "float32x3", "offset": 0, "shader_location": 0},
                            {"format": "float32x3", "offset": 12, "shader_location": 1},
                            {"format": "float32x4", "offset": 24, "shader_location": 2}]},
            {"array_stride": MESH_I * 4, "step_mode": "instance",
             "attributes": [{"format": "float32x4", "offset": 16 * k, "shader_location": 3 + k} for k in range(5)]}]


def _inst_layout():
    return [{"array_stride": INST_F * 4, "step_mode": "instance",
             "attributes": [{"format": "float32x4", "offset": 16 * k, "shader_location": k} for k in range(4)]}]


def _poly_layout():
    return [{"array_stride": POLY_F * 4, "step_mode": "vertex",
             "attributes": [{"format": "float32x2", "offset": 0, "shader_location": 0},
                            {"format": "float32x4", "offset": 8, "shader_location": 1},
                            {"format": "float32", "offset": 24, "shader_location": 2}]}]


class Engine:
    def __init__(self, width: int, height: int, font_img: np.ndarray, meshes: dict):
        self.W, self.H = int(width), int(height)
        adapter = wgpu.gpu.request_adapter_sync(power_preference="high-performance")
        self.adapter_info = dict(adapter.info)
        self.dev = d = adapter.request_device_sync()
        self.q = d.queue
        self.ubuf = d.create_buffer(size=NU * 16, usage=U.UNIFORM | U.COPY_DST)
        self.lin = d.create_sampler(mag_filter="linear", min_filter="linear",
                                    address_mode_u="clamp-to-edge", address_mode_v="clamp-to-edge")
        self.near = d.create_sampler(mag_filter="nearest", min_filter="nearest",
                                     address_mode_u="clamp-to-edge", address_mode_v="clamp-to-edge")
        self.cmp = d.create_sampler(compare="less-equal", mag_filter="linear", min_filter="linear")

        def tex(w, h, f, usage, samples=1):
            return d.create_texture(size=(w, h, 1), format=f, usage=usage, sample_count=samples)
        RT, TB, CS = TU.RENDER_ATTACHMENT, TU.TEXTURE_BINDING, TU.COPY_SRC
        W, H = self.W, self.H
        self.t = {
            "canvas_ms": tex(W, H, HDR, RT, MSAA), "canvas": tex(W, H, HDR, RT | TB),
            "depth_ms": tex(W, H, DEPTH, RT, MSAA),
            "hud_ms": tex(W, H, LDR, RT, MSAA), "hud": tex(W, H, LDR, RT | TB),
            "pix": tex(PIX_W, PIX_H, LDR, RT | TB),
            "shadow": tex(SHADOW, SHADOW, DEPTH, RT | TB),
            "q1": tex(W // 4, H // 4, HDR, RT | TB), "q2": tex(W // 4, H // 4, HDR, RT | TB),
            "final": tex(W, H, HDR, RT | TB),
            "rgba": tex(W, H, LDR, RT | CS), "ytex": tex(W, H, "r8unorm", RT | CS),
            "uvtex": tex(W // 2, H // 2, "rg8unorm", RT | CS),
        }
        self.v = {k: t.create_view() for k, t in self.t.items()}
        self.textures: dict[str, tuple] = {}
        self.bind_tex: dict[str, object] = {}
        self._layouts()
        self._pipelines()
        self.font = self.texture("font", font_img, linear=True)
        self.pix_bg = self._tex_bind(self.v["pix"], self.near)
        # dynamic buffers, written once per frame
        self.cap = {"poly": 900_000, "inst": 160_000, "minst": 120_000, "soup": 600_000}
        self.b_poly = d.create_buffer(size=self.cap["poly"] * POLY_F * 4, usage=U.VERTEX | U.COPY_DST)
        self.b_inst = d.create_buffer(size=self.cap["inst"] * INST_F * 4, usage=U.VERTEX | U.COPY_DST)
        self.b_minst = d.create_buffer(size=self.cap["minst"] * MESH_I * 4, usage=U.VERTEX | U.COPY_DST)
        self.b_soup = d.create_buffer(size=self.cap["soup"] * MESH_V * 4, usage=U.VERTEX | U.COPY_DST)
        self.ident = d.create_buffer_with_data(
            data=np.array([1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 1, 1, 1, 1, 0, 0, 0, 0], np.float32), usage=U.VERTEX)
        self.meshes: dict[str, tuple] = {}
        for k, (vv, ii) in meshes.items():
            self.add_mesh(k, vv, ii)
        self.pitch = (W + 255) // 256 * 256
        self.rb = d.create_buffer(size=self.pitch * (H + H // 2), usage=U.COPY_DST | U.MAP_READ)
        self.pitch4 = (W * 4 + 255) // 256 * 256
        self.rb4 = d.create_buffer(size=self.pitch4 * H, usage=U.COPY_DST | U.MAP_READ)

    # ------------------------------------------------------------------ resources
    def add_mesh(self, name: str, verts: np.ndarray, idx: np.ndarray):
        d = self.dev
        vb = d.create_buffer_with_data(data=np.ascontiguousarray(verts, np.float32), usage=U.VERTEX)
        ib = d.create_buffer_with_data(data=np.ascontiguousarray(idx, np.uint32), usage=U.INDEX)
        self.meshes[name] = (vb, ib, int(len(idx)))

    def texture(self, key: str, img: np.ndarray, linear: bool = False):
        """Create or update an RGBA8 (or R8) texture from an (h, w, c) uint8 array."""
        img = np.ascontiguousarray(img, np.uint8)
        h, w = img.shape[:2]
        ch = 1 if img.ndim == 2 else img.shape[2]
        fmt = {1: "r8unorm", 4: "rgba8unorm"}[ch]
        old = self.textures.get(key)
        if old is None or old[1] != (w, h, fmt):
            t = self.dev.create_texture(size=(w, h, 1), format=fmt, usage=TU.TEXTURE_BINDING | TU.COPY_DST)
            self.textures[key] = (t, (w, h, fmt))
            self.bind_tex[key] = self._tex_bind(t.create_view(), self.lin if linear else self.near)
        t = self.textures[key][0]
        self.q.write_texture({"texture": t, "mip_level": 0, "origin": (0, 0, 0)}, img.tobytes(),
                             {"offset": 0, "bytes_per_row": w * ch, "rows_per_image": h}, (w, h, 1))
        return t

    def _tex_bind(self, view, smp):
        return self.dev.create_bind_group(layout=self.bgl_tex, entries=[
            {"binding": 0, "resource": view}, {"binding": 1, "resource": smp}])

    def _layouts(self):
        d = self.dev
        self.bgl0 = d.create_bind_group_layout(entries=[
            {"binding": 0, "visibility": SS.VERTEX | SS.FRAGMENT, "buffer": {"type": "uniform"}},
            {"binding": 1, "visibility": SS.FRAGMENT, "sampler": {"type": "filtering"}}])
        self.bg0 = d.create_bind_group(layout=self.bgl0, entries=[
            {"binding": 0, "resource": {"buffer": self.ubuf, "offset": 0, "size": NU * 16}},
            {"binding": 1, "resource": self.lin}])
        self.bgl_tex = d.create_bind_group_layout(entries=[
            {"binding": 0, "visibility": SS.FRAGMENT, "texture": {"sample_type": "float", "view_dimension": "2d"}},
            {"binding": 1, "visibility": SS.FRAGMENT, "sampler": {"type": "filtering"}}])
        self.bgl_shadow = d.create_bind_group_layout(entries=[
            {"binding": 0, "visibility": SS.FRAGMENT, "texture": {"sample_type": "depth", "view_dimension": "2d"}},
            {"binding": 1, "visibility": SS.FRAGMENT, "sampler": {"type": "comparison"}}])
        self.bg_shadow = d.create_bind_group(layout=self.bgl_shadow, entries=[
            {"binding": 0, "resource": self.v["shadow"]}, {"binding": 1, "resource": self.cmp}])
        tx = {"sample_type": "float", "view_dimension": "2d"}
        self.bgl_post = d.create_bind_group_layout(entries=[
            {"binding": 0, "visibility": SS.FRAGMENT, "texture": tx},
            {"binding": 1, "visibility": SS.FRAGMENT, "texture": tx},
            {"binding": 2, "visibility": SS.FRAGMENT, "texture": tx},
            {"binding": 3, "visibility": SS.FRAGMENT, "buffer": {"type": "uniform"}},
            {"binding": 4, "visibility": SS.FRAGMENT, "texture": tx}])

    def _pipelines(self):
        d = self.dev
        m_bg = d.create_shader_module(code=shaders.BACKDROP)
        m_mesh = d.create_shader_module(code=shaders.MESH)
        m_flat = d.create_shader_module(code=shaders.FLAT)
        m_post = d.create_shader_module(code=shaders.POST)
        pl0 = d.create_pipeline_layout(bind_group_layouts=[self.bgl0])
        pl_tex = d.create_pipeline_layout(bind_group_layouts=[self.bgl0, self.bgl_tex])
        pl_mesh = d.create_pipeline_layout(bind_group_layouts=[self.bgl0, self.bgl_shadow])
        pl_post = d.create_pipeline_layout(bind_group_layouts=[self.bgl0, self.bgl_post])

        def ds(write=False, cmp="always"):
            return {"format": DEPTH, "depth_write_enabled": write, "depth_compare": cmp}

        def pipe(mod, vs, fs, buffers, fmt, samples, depth, layout, blend=ALPHA, topology="triangle-list"):
            desc = dict(layout=layout, vertex={"module": mod, "entry_point": vs, "buffers": buffers},
                        primitive={"topology": topology, "cull_mode": "none"},
                        multisample={"count": samples},
                        fragment={"module": mod, "entry_point": fs, "targets": [{"format": fmt, "blend": blend}]})
            if depth is not None:
                desc["depth_stencil"] = depth
            return d.create_render_pipeline(**desc)
        P = {}
        P["bg"] = pipe(m_bg, "vs_full", "fs_bg", [], HDR, MSAA, ds(), pl0, blend=None)
        P["mesh"] = pipe(m_mesh, "vs_mesh", "fs_mesh", _mesh_layout(), HDR, MSAA, ds(True, "less"), pl_mesh, blend=None)
        P["mesh_t"] = pipe(m_mesh, "vs_mesh", "fs_mesh", _mesh_layout(), HDR, MSAA, ds(False, "less"), pl_mesh)
        P["shadow"] = d.create_render_pipeline(
            layout=pl0, vertex={"module": m_mesh, "entry_point": "vs_shadow", "buffers": _mesh_layout()},
            primitive={"topology": "triangle-list", "cull_mode": "none"},
            depth_stencil={"format": DEPTH, "depth_write_enabled": True, "depth_compare": "less",
                           "depth_bias": 2, "depth_bias_slope_scale": 2.0},
            multisample={"count": 1}, fragment=None)
        for tgt, fmt, samples, depth in (("w", HDR, MSAA, ds()), ("h", LDR, MSAA, None), ("p", LDR, 1, None)):
            P["poly" + tgt] = pipe(m_flat, "vs_poly", "fs_poly", _poly_layout(), fmt, samples, depth, pl0)
            P["sdf" + tgt] = pipe(m_flat, "vs_sdf", "fs_sdf_hard" if tgt == "p" else "fs_sdf", _inst_layout(),
                                  fmt, samples, depth, pl0)
            P["img" + tgt] = pipe(m_flat, "vs_img", "fs_img", _inst_layout(), fmt, samples, depth, pl_tex)
            P["glyph" + tgt] = pipe(m_flat, "vs_glyph", "fs_glyph", _inst_layout(), fmt, samples, depth, pl_tex)

        def fp(fs, fmt):
            return pipe(m_post, "vs_full", fs, [], fmt, 1, None, pl_post, blend=None)
        P["down"], P["blur"], P["post"] = fp("fs_down", HDR), fp("fs_blur", HDR), fp("fs_post", HDR)
        P["y"], P["uv"], P["rgba"] = fp("fs_y", "r8unorm"), fp("fs_uv", "rg8unorm"), fp("fs_rgba", LDR)
        self.P = P
        qw, qh = self.W // 4, self.H // 4

        def pbg(src, blur, fin, dirv):
            ub = d.create_buffer_with_data(data=np.array(dirv, np.float32), usage=U.UNIFORM)
            return d.create_bind_group(layout=self.bgl_post, entries=[
                {"binding": 0, "resource": self.v[src]}, {"binding": 1, "resource": self.v[blur]},
                {"binding": 2, "resource": self.v[fin]}, {"binding": 3, "resource": {"buffer": ub, "offset": 0, "size": 16}},
                {"binding": 4, "resource": self.v["hud"]}])
        self.pb = {"down": pbg("canvas", "q2", "final", [1 / self.W, 1 / self.H, 0, 0]),
                   "bh": pbg("canvas", "q1", "final", [1 / qw, 0, 0, 0]),
                   "bv": pbg("canvas", "q2", "final", [0, 1 / qh, 0, 0]),
                   "post": pbg("canvas", "q1", "q2", [0, 0, 0, 0]),
                   "out": pbg("canvas", "q1", "final", [0, 0, 0, 0])}

    # ------------------------------------------------------------------ frame
    def _stage(self, fr: Frame):
        """Pack every layer's data into the four dynamic buffers; returns the draw lists with offsets."""
        polys, insts, minst, soup = [], [], [], []
        n = {"poly": 0, "inst": 0, "minst": 0, "soup": 0}

        def layer(L: Layer | None):
            out = []
            if L is None:
                return out
            for kind, a, key in L.items:
                if kind == "poly":
                    out.append(("poly", n["poly"], len(a), None))
                    polys.append(a)
                    n["poly"] += len(a)
                else:
                    out.append((kind, n["inst"], len(a), key))
                    insts.append(a)
                    n["inst"] += len(a)
            return out
        draws = {"pixel": layer(fr.pixel), "world": layer(fr.world), "hud": layer(fr.hud)}
        mesh_draws = []
        for name, inst, trans in fr.meshes:
            if len(inst):
                mesh_draws.append((name, n["minst"], len(inst), trans))
                minst.append(np.ascontiguousarray(inst, np.float32))
                n["minst"] += len(inst)
        soup_draws = []
        for verts, trans in fr.soup:
            if len(verts):
                soup_draws.append((n["soup"], len(verts), trans))
                soup.append(np.ascontiguousarray(verts, np.float32))
                n["soup"] += len(verts)
        for k, buf, parts in (("poly", self.b_poly, polys), ("inst", self.b_inst, insts),
                              ("minst", self.b_minst, minst), ("soup", self.b_soup, soup)):
            if n[k] > self.cap[k]:
                raise RuntimeError(f"crucible: frame too busy ({k}: {n[k]} > {self.cap[k]})")
            if parts:
                self.q.write_buffer(buf, 0, np.concatenate(parts).tobytes())
        return draws, mesh_draws, soup_draws

    def _draw_layer(self, p, items, tgt: str):
        for kind, off, cnt, key in items:
            if kind == "poly":
                p.set_pipeline(self.P["poly" + tgt])
                p.set_bind_group(0, self.bg0)
                p.set_vertex_buffer(0, self.b_poly, off * POLY_F * 4, cnt * POLY_F * 4)
                p.draw(cnt)
                continue
            p.set_pipeline(self.P[kind + tgt])
            p.set_bind_group(0, self.bg0)
            if kind == "img":
                p.set_bind_group(1, self.pix_bg if key == "@pixel" else self.bind_tex[key])
            elif kind == "glyph":
                p.set_bind_group(1, self.bind_tex["font"])
            p.set_vertex_buffer(0, self.b_inst, off * INST_F * 4, cnt * INST_F * 4)
            p.draw(6, cnt)

    def _meshes(self, p, mesh_draws, soup_draws, shadow: bool):
        for trans in (False, True):
            for name, off, cnt, tr in mesh_draws:
                if tr != trans or (shadow and tr):
                    continue
                vb, ib, ni = self.meshes[name]
                if not shadow:
                    p.set_pipeline(self.P["mesh_t" if tr else "mesh"])
                    p.set_bind_group(1, self.bg_shadow)
                p.set_bind_group(0, self.bg0)
                p.set_vertex_buffer(0, vb)
                p.set_vertex_buffer(1, self.b_minst, off * MESH_I * 4, cnt * MESH_I * 4)
                p.set_index_buffer(ib, "uint32")
                p.draw_indexed(ni, cnt)
            for off, cnt, tr in soup_draws:
                if tr != trans or (shadow and tr):
                    continue
                if not shadow:
                    p.set_pipeline(self.P["mesh_t" if tr else "mesh"])
                    p.set_bind_group(1, self.bg_shadow)
                p.set_bind_group(0, self.bg0)
                p.set_vertex_buffer(0, self.b_soup, off * MESH_V * 4, cnt * MESH_V * 4)
                p.set_vertex_buffer(1, self.ident)
                p.draw(cnt, 1)

    def _fpass(self, enc, target, pipeline, bg):
        p = enc.begin_render_pass(color_attachments=[{"view": self.v[target], "load_op": "clear",
                                                      "store_op": "store", "clear_value": (0, 0, 0, 1)}])
        p.set_pipeline(self.P[pipeline])
        p.set_bind_group(0, self.bg0)
        p.set_bind_group(1, self.pb[bg])
        p.draw(3)
        p.end()

    def render(self, fr: Frame, out: str = "nv12") -> bytes:
        d, q = self.dev, self.q
        q.write_buffer(self.ubuf, 0, np.ascontiguousarray(fr.uni, np.float32).tobytes())
        draws, mesh_draws, soup_draws = self._stage(fr)
        enc = d.create_command_encoder()
        has3d = bool(mesh_draws or soup_draws)
        if has3d and fr.shadow:
            p = enc.begin_render_pass(color_attachments=[], depth_stencil_attachment={
                "view": self.v["shadow"], "depth_clear_value": 1.0, "depth_load_op": "clear", "depth_store_op": "store"})
            p.set_pipeline(self.P["shadow"])
            self._meshes(p, mesh_draws, soup_draws, shadow=True)
            p.end()
        elif has3d:
            p = enc.begin_render_pass(color_attachments=[], depth_stencil_attachment={
                "view": self.v["shadow"], "depth_clear_value": 1.0, "depth_load_op": "clear", "depth_store_op": "store"})
            p.end()
        if fr.pixel is not None:
            p = enc.begin_render_pass(color_attachments=[{"view": self.v["pix"], "load_op": "clear",
                                                          "store_op": "store", "clear_value": (0, 0, 0, 0)}])
            self._draw_layer(p, draws["pixel"], "p")
            p.end()
        p = enc.begin_render_pass(
            color_attachments=[{"view": self.v["canvas_ms"], "resolve_target": self.v["canvas"], "load_op": "clear",
                                "store_op": "discard", "clear_value": (0, 0, 0, 1)}],
            depth_stencil_attachment={"view": self.v["depth_ms"], "depth_clear_value": 1.0, "depth_load_op": "clear",
                                      "depth_store_op": "discard"})
        if fr.backdrop:
            p.set_pipeline(self.P["bg"])
            p.set_bind_group(0, self.bg0)
            p.draw(3)
        if has3d:
            self._meshes(p, mesh_draws, soup_draws, shadow=False)
        if fr.pixel is not None:
            x0, y0, x1, y1 = fr.pixel_rect
            quad = np.array([[x0, y0, x1, y1, 0, 0, 1, 1, 1, 1, 1, 1, 1, 0, 0, 0]], np.float32)
            # (the pixel layer's quad goes through the instance buffer like any image)
            self.q.write_buffer(self.b_inst, (self.cap["inst"] - 1) * INST_F * 4, quad.tobytes())
            p.set_pipeline(self.P["imgw"])
            p.set_bind_group(0, self.bg0)
            p.set_bind_group(1, self.pix_bg)
            p.set_vertex_buffer(0, self.b_inst, (self.cap["inst"] - 1) * INST_F * 4, INST_F * 4)
            p.draw(6, 1)
        self._draw_layer(p, draws["world"], "w")
        p.end()
        p = enc.begin_render_pass(color_attachments=[{"view": self.v["hud_ms"], "resolve_target": self.v["hud"],
                                                      "load_op": "clear", "store_op": "discard",
                                                      "clear_value": (0, 0, 0, 0)}])
        self._draw_layer(p, draws["hud"], "h")
        p.end()
        self._fpass(enc, "q1", "down", "down")
        for _ in range(2):
            self._fpass(enc, "q2", "blur", "bh")
            self._fpass(enc, "q1", "blur", "bv")
        self._fpass(enc, "final", "post", "post")
        W, H = self.W, self.H
        if out == "nv12":
            self._fpass(enc, "ytex", "y", "out")
            self._fpass(enc, "uvtex", "uv", "out")
            enc.copy_texture_to_buffer({"texture": self.t["ytex"], "mip_level": 0, "origin": (0, 0, 0)},
                                       {"buffer": self.rb, "offset": 0, "bytes_per_row": self.pitch, "rows_per_image": H},
                                       (W, H, 1))
            enc.copy_texture_to_buffer({"texture": self.t["uvtex"], "mip_level": 0, "origin": (0, 0, 0)},
                                       {"buffer": self.rb, "offset": self.pitch * H, "bytes_per_row": self.pitch,
                                        "rows_per_image": H // 2}, (W // 2, H // 2, 1))
        else:
            self._fpass(enc, "rgba", "rgba", "out")
            enc.copy_texture_to_buffer({"texture": self.t["rgba"], "mip_level": 0, "origin": (0, 0, 0)},
                                       {"buffer": self.rb4, "offset": 0, "bytes_per_row": self.pitch4, "rows_per_image": H},
                                       (W, H, 1))
        q.submit([enc.finish()])
        buf, pitch, rows, width = ((self.rb, self.pitch, H + H // 2, W) if out == "nv12"
                                   else (self.rb4, self.pitch4, H, W * 4))
        buf.map_sync(wgpu.MapMode.READ)
        try:
            a = np.frombuffer(buf.read_mapped(), np.uint8).reshape(rows, pitch)
            return a[:, :width].tobytes()
        finally:
            buf.unmap()
