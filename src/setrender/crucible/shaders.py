"""WGSL for crucible. The frame is drawn in layers into a 4x multisampled half-float canvas: a backdrop pass
(sky or wall, with the music's decor layers: the bass's accent light, the sub's floor glow, motes for the high
mids drifting with the low mids, sparkles for the highs), lit 3D meshes with a sun shadow map, then the 2D
world (triangles, signed-distance shapes and images) under a 2D camera. Pixel-art trials draw their world
into a 320x180 target first, which is scaled up by whole pixels. The broadcast overlay (text, the fitness
chart, the tally) is drawn into its own 8-bit target and laid over the graded picture, so its colours stay
exact. The post pass adds bloom, the kick's exposure pump, the vignette and the grade, and the result is
converted to BT.709 NV12 on the GPU (or read back as RGBA for stills).

Coordinates: world layers have y up in world units, the camera's half-height in world units; screen layers
are pixels with y down from the top-left corner.
"""

COMMON = r"""
struct U {
  res: vec4<f32>,   // w, h, 1/w, 1/h
  clk: vec4<f32>,   // time (s), frame index, kick pulse, beat phase 0..1
  aud: vec4<f32>,   // sub, bass, lowmid, highmid
  aud2: vec4<f32>,  // high, loudness, calm, drift (the low mids' integrated phase)
  camw: vec4<f32>,  // 2D world camera: centre x, y, half-height, rotation
  camp: vec4<f32>,  // pixel layer camera (same layout)
  bg0: vec4<f32>,   // backdrop mode, horizon (0 top .. 1 bottom), pixel cells across (0 = smooth), stars
  bgt: vec4<f32>,   // top colour, sun size
  bgb: vec4<f32>,   // bottom colour, haze
  acc: vec4<f32>,   // accent colour, accent light's x (0..1)
  post: vec4<f32>,  // exposure, vignette, bloom, tone (0 = filmic for 3D light, 1 = display colours)
  post2: vec4<f32>, // saturation, fade to black, the kick's lift in the shadows, overlay opacity
  lay: vec4<f32>,   // decor gains: floor glow (sub), accent light (bass), drift (low mids), motes (high mids)
  lay2: vec4<f32>,  // sparkles (highs), debug, sun x (0..1), sun y
  vp: mat4x4<f32>,  // 3D view-projection
  svp: mat4x4<f32>, // the sun's view-projection (shadow map)
  sun: vec4<f32>,   // direction to the sun, intensity
  sunc: vec4<f32>,  // sun colour, ambient
  sky: vec4<f32>,   // sky colour (fog and the upper hemisphere), fog density
  gnd: vec4<f32>,   // ground bounce colour, shadow strength
  eye: vec4<f32>,   // camera position, -
};
@group(0) @binding(0) var<uniform> u: U;

const PI: f32 = 3.14159265;
const TAU: f32 = 6.28318531;

fn pcg(x: u32) -> u32 {
  let v = x * 747796405u + 2891336453u;
  let w = ((v >> ((v >> 28u) + 4u)) ^ v) * 277803737u;
  return (w >> 22u) ^ w;
}
fn hash21(p: vec2<f32>) -> f32 {
  let h = pcg(bitcast<u32>(p.x + 0.0) ^ pcg(bitcast<u32>(p.y + 0.0) + 0x9e3779b9u));
  return f32(h >> 8u) / 16777216.0;
}
fn hash22(p: vec2<f32>) -> vec2<f32> {
  return vec2<f32>(hash21(p), hash21(p + vec2<f32>(17.31, 5.17)));
}
fn sst(a: f32, b: f32, x: f32) -> f32 {
  let t = clamp((x - a) / (b - a), 0.0, 1.0);
  return t * t * (3.0 - 2.0 * t);
}
fn luma(c: vec3<f32>) -> f32 { return dot(c, vec3<f32>(0.2126, 0.7152, 0.0722)); }

// world (y up) -> clip through a 2D camera
fn cam2clip(p: vec2<f32>, cam: vec4<f32>) -> vec2<f32> {
  let c = cos(cam.w);
  let s = sin(cam.w);
  let d = p - cam.xy;
  let r = vec2<f32>(c * d.x + s * d.y, -s * d.x + c * d.y);
  let aspect = u.res.x / u.res.y;
  return vec2<f32>(r.x / (cam.z * aspect), r.y / cam.z);
}
// screen pixels (y down) -> clip
fn px2clip(p: vec2<f32>) -> vec2<f32> {
  return vec2<f32>(p.x * u.res.z * 2.0 - 1.0, 1.0 - p.y * u.res.w * 2.0);
}
fn to_clip(p: vec2<f32>, space: f32) -> vec2<f32> {
  if (space > 1.5) { return cam2clip(p, u.camp); }
  if (space > 0.5) { return px2clip(p); }
  return cam2clip(p, u.camw);
}

struct FOut { @builtin(position) pos: vec4<f32>, @location(0) uv: vec2<f32> };

@vertex
fn vs_full(@builtin(vertex_index) vi: u32) -> FOut {
  var pts = array<vec2<f32>, 3>(vec2<f32>(-1.0, -1.0), vec2<f32>(3.0, -1.0), vec2<f32>(-1.0, 3.0));
  var o: FOut;
  let q = pts[vi];
  o.pos = vec4<f32>(q, 0.0, 1.0);
  o.uv = vec2<f32>(q.x * 0.5 + 0.5, 0.5 - q.y * 0.5);
  return o;
}
"""

# ---------------------------------------------------------------------------------------------------- backdrop
BACKDROP = COMMON + r"""
fn motes(px: vec2<f32>, cell: f32, drift: f32, seed: f32) -> f32 {
  let p = px + vec2<f32>(drift, 0.0);
  let c = floor(p / cell);
  var s = 0.0;
  for (var j = -1; j <= 1; j = j + 1) {
    for (var i = -1; i <= 1; i = i + 1) {
      let cc = c + vec2<f32>(f32(i), f32(j));
      let h = hash22(cc + seed);
      let ctr = (cc + 0.15 + 0.7 * h) * cell;
      let r = cell * (0.035 + 0.05 * hash21(cc + seed + 3.7));
      let d = length(p - ctr);
      s = s + (1.0 - sst(0.0, r, d)) * step(0.45, hash21(cc + seed + 9.1));
    }
  }
  return s;
}

@fragment
fn fs_bg(i: FOut) -> @location(0) vec4<f32> {
  var px = i.pos.xy;
  let cells = u.bg0.z;
  var cs = 1.0;
  if (cells > 0.5) {
    cs = u.res.x / cells;
    px = (floor(px / cs) + 0.5) * cs;
  }
  let uv = px * u.res.zw;
  let aspect = u.res.x / u.res.y;
  let hz = u.bg0.y;
  let mode = i32(u.bg0.x + 0.5);
  var c = mix(u.bgt.rgb, u.bgb.rgb, sst(0.0, 1.0, uv.y / max(hz, 0.05)));
  if (uv.y > hz) {
    c = mix(u.bgb.rgb, u.bgb.rgb * 0.55, sst(hz, 1.0, uv.y));
  }
  if (mode == 1) {
    // water: light shafts from the surface
    let sh = 0.5 + 0.5 * sin((uv.x * 9.0 + uv.y * 2.0) + 0.6 * sin(uv.x * 3.1 + u.clk.x * 0.3));
    c = c + u.bgt.rgb * 0.25 * sh * (1.0 - uv.y);
  }
  // the sun (or a moon, a lamp)
  if (u.bgt.w > 0.0) {
    let sd = length((uv - vec2<f32>(u.lay2.z, u.lay2.w)) * vec2<f32>(aspect, 1.0));
    c = c + vec3<f32>(1.0, 0.92, 0.75) * (1.0 - sst(u.bgt.w * 0.9, u.bgt.w, sd)) * 0.9
          + vec3<f32>(1.0, 0.8, 0.5) * exp(-sd * sd / (u.bgt.w * u.bgt.w * 9.0)) * 0.25;
  }
  // stars, twinkling with the highs
  let stars = u.bg0.w;
  // the bass's accent light: a broad soft glow behind the scene
  let ad = length((uv - vec2<f32>(u.acc.w, hz * 0.75)) * vec2<f32>(aspect * 0.6, 1.0));
  c = c + u.acc.rgb * (u.aud.y * u.lay.y) * exp(-ad * ad * 2.2) * 0.55;
  // the sub's floor glow along the horizon
  let fd = (uv.y - hz) * 9.0;
  c = c + u.acc.rgb * (u.aud.x * u.lay.x) * exp(-fd * fd) * 0.45;
  // motes for the high mids, drifting with the low mids
  let drift = u.aud2.w * u.lay.z * 140.0;
  let m = motes(px / cs * cs, 64.0, drift, 1.0) + 0.6 * motes(px, 41.0, drift * 1.6, 7.0);
  c = c + mix(vec3<f32>(1.0), u.acc.rgb, 0.4) * m * (0.08 + 0.55 * u.aud.w * u.lay.w) * 0.5 * (0.3 + 0.7 * u.lay.w);
  // sparkles for the highs (and stars at night)
  let sc = floor(px / 23.0);
  let sh2 = hash21(sc + 31.0);
  let spos = (sc + 0.2 + 0.6 * hash22(sc + 2.0)) * 23.0;
  let sdist = length(px - spos);
  let tw = 0.5 + 0.5 * sin(u.clk.x * (2.0 + 5.0 * sh2) + sh2 * 40.0);
  let spark = step(0.86, sh2) * (1.0 - sst(0.0, 1.6 + 1.2 * hash21(sc + 5.0), sdist));
  c = c + vec3<f32>(1.0, 0.97, 0.9) * spark * (stars * (0.35 + 0.35 * tw) + u.aud2.x * u.lay2.x * (0.4 + 0.6 * tw)) * (1.0 - sst(hz - 0.05, hz, uv.y));
  if (cells > 0.5) {
    c = floor(c * 12.0 + 0.5) / 12.0;
  }
  return vec4<f32>(c, 1.0);
}
"""

# ---------------------------------------------------------------------------------------------------- 3D meshes
MESH = COMMON + r"""
@group(1) @binding(0) var shadow_tex: texture_depth_2d;
@group(1) @binding(1) var shadow_smp: sampler_comparison;

struct VIn {
  @location(0) p: vec3<f32>,
  @location(1) n: vec3<f32>,
  @location(2) c: vec4<f32>,
  @location(3) m0: vec4<f32>,
  @location(4) m1: vec4<f32>,
  @location(5) m2: vec4<f32>,
  @location(6) col: vec4<f32>,
  @location(7) ex: vec4<f32>,
};
struct VOut {
  @builtin(position) pos: vec4<f32>,
  @location(0) w: vec3<f32>,
  @location(1) n: vec3<f32>,
  @location(2) c: vec4<f32>,
  @location(3) ex: vec4<f32>,
};

fn xform(v: VIn) -> vec3<f32> {
  let p = vec4<f32>(v.p, 1.0);
  return vec3<f32>(dot(v.m0, p), dot(v.m1, p), dot(v.m2, p));
}

@vertex
fn vs_mesh(v: VIn) -> VOut {
  var o: VOut;
  let w = xform(v);
  o.pos = u.vp * vec4<f32>(w, 1.0);
  o.w = w;
  let n = vec3<f32>(dot(v.m0.xyz, v.n), dot(v.m1.xyz, v.n), dot(v.m2.xyz, v.n));
  o.n = normalize(n);
  o.c = v.c * v.col;
  o.ex = v.ex;
  return o;
}

@vertex
fn vs_shadow(v: VIn) -> @builtin(position) vec4<f32> {
  return u.svp * vec4<f32>(xform(v), 1.0);
}

fn shadow_at(w: vec3<f32>, n: vec3<f32>) -> f32 {
  let q = u.svp * vec4<f32>(w + n * 0.02, 1.0);
  let s = q.xyz / q.w;
  let uv = vec2<f32>(s.x * 0.5 + 0.5, 0.5 - s.y * 0.5);
  if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0 || s.z > 1.0) { return 1.0; }
  var acc = 0.0;
  let t = 1.0 / 2048.0;
  for (var j = -1; j <= 1; j = j + 1) {
    for (var i = -1; i <= 1; i = i + 1) {
      acc = acc + textureSampleCompareLevel(shadow_tex, shadow_smp, uv + vec2<f32>(f32(i), f32(j)) * t, s.z - 0.0015);
    }
  }
  return acc / 9.0;
}

@fragment
fn fs_mesh(v: VOut, @builtin(front_facing) ff: bool) -> @location(0) vec4<f32> {
  var n = normalize(v.n);
  if (!ff) { n = -n; }
  let L = normalize(u.sun.xyz);
  let sh = mix(1.0, shadow_at(v.w, n), u.gnd.w);
  let diff = max(dot(n, L), 0.0) * sh;
  let hemi = mix(u.gnd.rgb, u.sky.rgb, 0.5 + 0.5 * n.y);
  let V = normalize(u.eye.xyz - v.w);
  let H = normalize(L + V);
  let spec = pow(max(dot(n, H), 0.0), 40.0) * 0.25 * sh * (1.0 - v.ex.y);
  let rim = pow(1.0 - max(dot(n, V), 0.0), 3.0) * 0.25;
  var c = v.c.rgb * (u.sunc.rgb * diff * u.sun.w + hemi * u.sunc.w) + vec3<f32>(spec) + u.sky.rgb * rim * 0.5;
  c = c + v.c.rgb * v.ex.x;
  // distance fog toward the sky
  let d = length(u.eye.xyz - v.w);
  let f = 1.0 - exp(-d * u.sky.w);
  c = mix(c, u.sky.rgb, clamp(f, 0.0, 1.0));
  return vec4<f32>(c, v.c.a);
}
"""

# ---------------------------------------------------------------------------------------------------- 2D layers
FLAT = COMMON + r"""
struct PIn { @location(0) p: vec2<f32>, @location(1) c: vec4<f32>, @location(2) sp: f32 };
struct POut { @builtin(position) pos: vec4<f32>, @location(0) c: vec4<f32> };

@vertex
fn vs_poly(v: PIn) -> POut {
  var o: POut;
  o.pos = vec4<f32>(to_clip(v.p, v.sp), 0.0, 1.0);
  o.c = v.c;
  return o;
}
@fragment
fn fs_poly(v: POut) -> @location(0) vec4<f32> {
  return v.c;
}

// signed-distance shapes: a = (p0, p1 or half size), b = (radius, angle, type, space), c = colour,
// d = (outline width, outline darkness, glow, -)
struct SIn {
  @location(0) a: vec4<f32>,
  @location(1) b: vec4<f32>,
  @location(2) c: vec4<f32>,
  @location(3) d: vec4<f32>,
};
struct SOut {
  @builtin(position) pos: vec4<f32>,
  @location(0) q: vec2<f32>,
  @location(1) a: vec4<f32>,
  @location(2) b: vec4<f32>,
  @location(3) c: vec4<f32>,
  @location(4) d: vec4<f32>,
};

fn shape_box(s: SIn) -> vec4<f32> {
  // bounding box (min xy, max xy) in the shape's own space
  let ty = i32(s.b.z + 0.5);
  let m = s.d.x + s.d.z + s.b.x;
  if (ty == 2) {
    let lo = min(s.a.xy, s.a.zw) - vec2<f32>(m);
    let hi = max(s.a.xy, s.a.zw) + vec2<f32>(m);
    return vec4<f32>(lo, hi);
  }
  if (ty == 1) {
    let e = length(s.a.zw) + m;
    return vec4<f32>(s.a.xy - vec2<f32>(e), s.a.xy + vec2<f32>(e));
  }
  let r = s.a.z + max(s.a.w, 0.0) + s.d.x + s.d.z;
  return vec4<f32>(s.a.xy - vec2<f32>(r), s.a.xy + vec2<f32>(r));
}

@vertex
fn vs_sdf(s: SIn, @builtin(vertex_index) vi: u32) -> SOut {
  var o: SOut;
  let bb = shape_box(s);
  // grow by a couple of pixels for the edge's smoothing
  var px = 2.0 * u.camw.z * u.res.w;
  if (s.b.w > 1.5) { px = 2.0 * u.camp.z / 180.0; }
  if (s.b.w > 0.5 && s.b.w < 1.5) { px = 1.0; }
  let g = vec4<f32>(-2.5 * px, -2.5 * px, 2.5 * px, 2.5 * px);
  let b = bb + g;
  var cs = array<vec2<f32>, 6>(vec2<f32>(0.0, 0.0), vec2<f32>(1.0, 0.0), vec2<f32>(0.0, 1.0),
                               vec2<f32>(1.0, 0.0), vec2<f32>(1.0, 1.0), vec2<f32>(0.0, 1.0));
  let k = cs[vi];
  let q = mix(b.xy, b.zw, k);
  o.pos = vec4<f32>(to_clip(q, s.b.w), 0.0, 1.0);
  o.q = q;
  o.a = s.a;
  o.b = s.b;
  o.c = s.c;
  o.d = s.d;
  return o;
}

fn sd_shape(q: vec2<f32>, a: vec4<f32>, b: vec4<f32>) -> f32 {
  let ty = i32(b.z + 0.5);
  if (ty == 1) {
    // rounded box, rotated by b.y
    let c = cos(b.y);
    let s = sin(b.y);
    let d = q - a.xy;
    let l = vec2<f32>(c * d.x + s * d.y, -s * d.x + c * d.y);
    let e = abs(l) - (a.zw - vec2<f32>(b.x));
    return length(max(e, vec2<f32>(0.0))) + min(max(e.x, e.y), 0.0) - b.x;
  }
  if (ty == 2) {
    // capsule from a.xy to a.zw, radius b.x
    let pa = q - a.xy;
    let ba = a.zw - a.xy;
    let h = clamp(dot(pa, ba) / max(dot(ba, ba), 1e-12), 0.0, 1.0);
    return length(pa - ba * h) - b.x;
  }
  if (ty == 3) {
    // ring: radius a.z, half thickness a.w
    return abs(length(q - a.xy) - a.z) - a.w;
  }
  if (ty == 4) {
    // four-pointed sparkle
    let d = abs(q - a.xy) / a.z;
    return (min(d.x, d.y) * 6.0 + max(d.x, d.y) - 1.0) * a.z * 0.5;
  }
  // circle (a.w > 0 grows a soft halo)
  return length(q - a.xy) - a.z;
}

fn shade_sdf(v: SOut, hard: bool) -> vec4<f32> {
  let d = sd_shape(v.q, v.a, v.b);
  var w = fwidth(d) * 0.75;
  if (hard) { w = 1e-5; }
  let ol = v.d.x;
  let fill = 1.0 - sst(-w, w, d);
  var col = v.c.rgb;
  if (ol > 0.0) {
    let inner = 1.0 - sst(-w, w, d + ol);
    col = mix(v.c.rgb * (1.0 - v.d.y), v.c.rgb, inner);
  }
  var a = fill * v.c.a;
  if (v.d.z > 0.0) {
    // glow: a soft falloff outside the shape
    let gl = exp(-max(d, 0.0) / max(v.d.z, 1e-6) * 2.5) * (1.0 - fill) * 0.6;
    let ta = a + gl * v.c.a;
    return vec4<f32>(col, ta);
  }
  return vec4<f32>(col, a);
}
@fragment
fn fs_sdf(v: SOut) -> @location(0) vec4<f32> { return shade_sdf(v, false); }
@fragment
fn fs_sdf_hard(v: SOut) -> @location(0) vec4<f32> {
  let c = shade_sdf(v, true);
  if (c.a < 0.5) { discard; }
  return vec4<f32>(c.rgb, 1.0);
}

// images: a = rect (x0, y0, x1, y1) in the space's units, b = uv rect, c = tint, d = (space, -, -, -)
@group(1) @binding(0) var img: texture_2d<f32>;
@group(1) @binding(1) var img_smp: sampler;
struct IIn { @location(0) a: vec4<f32>, @location(1) b: vec4<f32>, @location(2) c: vec4<f32>, @location(3) d: vec4<f32> };
struct IOut { @builtin(position) pos: vec4<f32>, @location(0) uv: vec2<f32>, @location(1) c: vec4<f32> };
@vertex
fn vs_img(s: IIn, @builtin(vertex_index) vi: u32) -> IOut {
  var cs = array<vec2<f32>, 6>(vec2<f32>(0.0, 0.0), vec2<f32>(1.0, 0.0), vec2<f32>(0.0, 1.0),
                               vec2<f32>(1.0, 0.0), vec2<f32>(1.0, 1.0), vec2<f32>(0.0, 1.0));
  let k = cs[vi];
  var o: IOut;
  let q = mix(s.a.xy, s.a.zw, k);
  o.pos = vec4<f32>(to_clip(q, s.d.x), 0.0, 1.0);
  o.uv = mix(s.b.xy, s.b.zw, k);
  o.c = s.c;
  return o;
}
@fragment
fn fs_img(v: IOut) -> @location(0) vec4<f32> {
  return textureSample(img, img_smp, v.uv) * v.c;
}

// text: a = rect (x, y, w, h) in pixels, b = uv rect, c = colour, d = (outline width, outline darkness,
// shadow, weight)
struct GOut { @builtin(position) pos: vec4<f32>, @location(0) uv: vec2<f32>, @location(1) c: vec4<f32>, @location(2) d: vec4<f32> };
@vertex
fn vs_glyph(s: IIn, @builtin(vertex_index) vi: u32) -> GOut {
  var cs = array<vec2<f32>, 6>(vec2<f32>(0.0, 0.0), vec2<f32>(1.0, 0.0), vec2<f32>(0.0, 1.0),
                               vec2<f32>(1.0, 0.0), vec2<f32>(1.0, 1.0), vec2<f32>(0.0, 1.0));
  let k = cs[vi];
  var o: GOut;
  o.pos = vec4<f32>(px2clip(s.a.xy + s.a.zw * k), 0.0, 1.0);
  o.uv = mix(s.b.xy, s.b.zw, k);
  o.c = s.c;
  o.d = s.d;
  return o;
}
@fragment
fn fs_glyph(v: GOut) -> @location(0) vec4<f32> {
  let d = textureSample(img, img_smp, v.uv).r;
  let w = max(fwidth(d) * 0.7, 1e-4);
  let edge = 0.5 - v.d.w;
  let fill = sst(edge - w, edge + w, d);
  var col = v.c.rgb;
  var a = fill;
  if (v.d.x > 0.0) {
    let o = sst(edge - v.d.x - w, edge - v.d.x + w, d);
    col = mix(v.c.rgb * (1.0 - v.d.y), v.c.rgb, fill);
    a = max(fill, o);
  }
  return vec4<f32>(col, a * v.c.a);
}
"""

# ---------------------------------------------------------------------------------------------------- post
POST = COMMON + r"""
@group(1) @binding(0) var src: texture_2d<f32>;
@group(1) @binding(1) var blur: texture_2d<f32>;
@group(1) @binding(2) var fin: texture_2d<f32>;
struct Dir { v: vec4<f32> };
@group(1) @binding(3) var<uniform> D: Dir;
@group(1) @binding(4) var hud: texture_2d<f32>;
@group(0) @binding(1) var smp: sampler;

@fragment
fn fs_down(i: FOut) -> @location(0) vec4<f32> {
  let px = D.v.xy;
  var c = vec4<f32>(0.0);
  c = c + textureSampleLevel(src, smp, i.uv + vec2<f32>(-px.x, -px.y), 0.0);
  c = c + textureSampleLevel(src, smp, i.uv + vec2<f32>(px.x, -px.y), 0.0);
  c = c + textureSampleLevel(src, smp, i.uv + vec2<f32>(-px.x, px.y), 0.0);
  c = c + textureSampleLevel(src, smp, i.uv + vec2<f32>(px.x, px.y), 0.0);
  // only what is bright enough feeds the bloom
  let l = luma(c.rgb * 0.25);
  let th = select(0.55, 1.0, u.post.w > 0.5);
  return c * 0.25 * sst(th, th + 0.8, l);
}

@fragment
fn fs_blur(i: FOut) -> @location(0) vec4<f32> {
  let w = array<f32, 5>(0.227027, 0.1945946, 0.1216216, 0.054054, 0.016216);
  var c = textureSampleLevel(blur, smp, i.uv, 0.0) * w[0];
  for (var k = 1; k < 5; k = k + 1) {
    let o = D.v.xy * f32(k) * 1.5;
    c = c + textureSampleLevel(blur, smp, i.uv + o, 0.0) * w[k];
    c = c + textureSampleLevel(blur, smp, i.uv - o, 0.0) * w[k];
  }
  return c;
}

fn aces(x: vec3<f32>) -> vec3<f32> {
  let a = 2.51; let b = 0.03; let c = 2.43; let d = 0.59; let e = 0.14;
  return clamp((x * (a * x + b)) / (x * (c * x + d) + e), vec3<f32>(0.0), vec3<f32>(1.0));
}

@fragment
fn fs_post(i: FOut) -> @location(0) vec4<f32> {
  let uv = i.uv;
  let ctr = uv - 0.5;
  let rpx = length(vec2<f32>(ctr.x * u.res.x / u.res.y, ctr.y));
  var c = textureSampleLevel(src, smp, uv, 0.0).rgb;
  let bl = textureSampleLevel(blur, smp, uv, 0.0).rgb;
  c = c + bl * u.post.z;
  c = c * u.post.x;
  if (u.post.w < 0.5) {
    c = pow(aces(c), vec3<f32>(1.0 / 2.2));
  } else {
    // display colours: a soft shoulder only above white
    c = select(c, 1.0 - 0.25 * exp(-(c - 0.75) * 4.0), c > vec3<f32>(0.75));
  }
  let l = luma(c);
  c = clamp(mix(vec3<f32>(l), c, u.post2.x), vec3<f32>(0.0), vec3<f32>(1.0));
  // the kick lifts the shadows and mid-tones, not the highlights (and survives the encoder in dark frames)
  c = c * (1.0 + u.post2.z * (1.0 - sst(0.25, 0.7, luma(c))));
  let v = 1.0 - u.post.y * pow(rpx * 1.05, 2.4);
  c = clamp(c * clamp(v, 0.0, 1.0), vec3<f32>(0.0), vec3<f32>(1.0));
  // the overlay (premultiplied), then the fade
  let h = textureLoad(hud, vec2<i32>(i.pos.xy), 0);
  c = c * (1.0 - h.a * u.post2.w) + h.rgb * u.post2.w;
  c = c * (1.0 - u.post2.y);
  return vec4<f32>(c, 1.0);
}

fn dith(p: vec2<f32>) -> f32 {
  return hash21(p + vec2<f32>(u.clk.y * 0.618, u.clk.y * 0.382)) + hash21(p * 1.37 + 11.0 + u.clk.y * 0.1) - 1.0;
}

@fragment
fn fs_y(i: FOut) -> @location(0) vec4<f32> {
  let c = textureLoad(fin, vec2<i32>(i.pos.xy), 0).rgb;
  let y = (16.0 + 219.0 * dot(c, vec3<f32>(0.2126, 0.7152, 0.0722)) + 0.5 * dith(i.pos.xy)) / 255.0;
  return vec4<f32>(y, 0.0, 0.0, 1.0);
}

@fragment
fn fs_uv(i: FOut) -> @location(0) vec4<f32> {
  let b = vec2<i32>(i.pos.xy) * 2;
  let c = (textureLoad(fin, b, 0).rgb + textureLoad(fin, b + vec2<i32>(1, 0), 0).rgb
         + textureLoad(fin, b + vec2<i32>(0, 1), 0).rgb + textureLoad(fin, b + vec2<i32>(1, 1), 0).rgb) * 0.25;
  let y = dot(c, vec3<f32>(0.2126, 0.7152, 0.0722));
  let cb = (128.0 + 224.0 * (c.b - y) / 1.8556 + 0.5 * dith(i.pos.xy + 3.3)) / 255.0;
  let cr = (128.0 + 224.0 * (c.r - y) / 1.5748 + 0.5 * dith(i.pos.xy + 7.7)) / 255.0;
  return vec4<f32>(cb, cr, 0.0, 1.0);
}

@fragment
fn fs_rgba(i: FOut) -> @location(0) vec4<f32> {
  return vec4<f32>(textureLoad(fin, vec2<i32>(i.pos.xy), 0).rgb, 1.0);
}
"""
