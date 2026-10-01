"""WGSL shaders for the GPU scene engine (WebGPU via wgpu-native, Metal on macOS).

All passes share one per-frame uniform block (`Frame`). Layout must match `engine.FRAME_FIELDS`.
"""

PRELUDE = r"""
struct Light { pos: vec4f, col: vec4f, dir: vec4f, ext: vec4f };
struct Frame {
  viewproj: mat4x4f,
  inv_viewproj: mat4x4f,
  cam_pos: vec4f,     // w = time (s, clip-local)
  cam_right: vec4f,   // w = aspect
  cam_up: vec4f,      // w = tan(fov/2)
  cam_fwd: vec4f,     // w = psychedelic amount
  key_dir: vec4f,     // direction towards the key light (sun or moon), w = intensity
  key_col: vec4f,     // w = star visibility
  sky_top: vec4f,     // w = moon phase (0 new .. 0.5 full .. 1 new)
  sky_hor: vec4f,     // w = aurora amount
  amb_sky: vec4f,     // w = fog density
  amb_gnd: vec4f,     // w = fog height falloff
  fog_col: vec4f,     // w = cloud cover
  wind: vec4f,        // xy = direction, z = strength, w = integrated phase
  audio: vec4f,       // sub, bass, lowmid, highmid (0..1 envelopes)
  audio2: vec4f,      // high, onset, loudness, beat envelope
  beat: vec4f,        // beat phase, bar fraction, beat index, bar envelope
  misc: vec4f,        // section energy, section hue, kaleido seed, time of day
  res: vec4f,         // target W, H, 1/W, 1/H
  nl: vec4f,          // light count, absolute set clock (s), sun visibility, moon visibility
  sun_sky: vec4f,     // direction to sun, w = disk intensity
  moon_sky: vec4f,    // direction to moon, w = intensity
  lights: array<Light, 24>,
};
struct CropParams { p: array<vec4f, 64>, field: vec4f };

@group(0) @binding(0) var<uniform> F: Frame;
@group(0) @binding(1) var atlas: texture_2d<f32>;
@group(0) @binding(2) var samp_n: sampler;
@group(0) @binding(3) var cropmap: texture_2d<f32>;
@group(0) @binding(4) var<uniform> CP: CropParams;
@group(0) @binding(5) var samp_l: sampler;

const PI: f32 = 3.14159265;
const TAU: f32 = 6.2831853;

fn hash11(p: f32) -> f32 { var x = fract(p * 0.1031); x = x * (x + 33.33); return fract(x * (x + x)); }
fn hash21(p: vec2f) -> f32 { var p3 = fract(vec3f(p.xyx) * 0.1031); p3 = p3 + dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }
fn hash31(p: vec3f) -> f32 { var p3 = fract(p * 0.1031); p3 = p3 + dot(p3, p3.zyx + 31.32); return fract((p3.x + p3.y) * p3.z); }
fn hash22(p: vec2f) -> vec2f { var p3 = fract(vec3f(p.xyx) * vec3f(0.1031, 0.1030, 0.0973)); p3 = p3 + dot(p3, p3.yzx + 33.33); return fract((p3.xx + p3.yz) * p3.zy); }
fn noise2(p: vec2f) -> f32 {
  let i = floor(p); let f = fract(p); let u = f * f * (3.0 - 2.0 * f);
  return mix(mix(hash21(i), hash21(i + vec2f(1.0, 0.0)), u.x), mix(hash21(i + vec2f(0.0, 1.0)), hash21(i + vec2f(1.0, 1.0)), u.x), u.y);
}
fn fbm2(p0: vec2f) -> f32 {
  var p = p0; var a = 0.5; var s = 0.0;
  for (var k = 0; k < 5; k = k + 1) { s = s + a * noise2(p); p = p * 2.03 + vec2f(17.1, 9.2); a = a * 0.5; }
  return s;
}
fn hsv2rgb(h: f32, s: f32, v: f32) -> vec3f {
  let k = vec3f(1.0, 2.0 / 3.0, 1.0 / 3.0);
  let p = abs(fract(vec3f(h) + k) * 6.0 - 3.0);
  return v * mix(vec3f(1.0), clamp(p - 1.0, vec3f(0.0), vec3f(1.0)), s);
}

fn lights_at(p: vec3f, n: vec3f, wrap: f32) -> vec3f {
  var c = vec3f(0.0);
  let nl = u32(F.nl.x);
  for (var k = 0u; k < nl; k = k + 1u) {
    let L = F.lights[k];
    let dv = L.pos.xyz - p;
    let d2 = dot(dv, dv);
    if (d2 > L.pos.w * L.pos.w) { continue; }
    let dist = max(sqrt(d2), 1e-3);
    let d = dv / dist;
    var att = clamp(1.0 - dist / L.pos.w, 0.0, 1.0);
    att = att * att;
    if (L.dir.w > -1.5) {
      let cs = dot(-d, L.dir.xyz);
      att = att * smoothstep(L.dir.w, L.ext.x, cs);
    }
    let diff = max((dot(n, d) + wrap) / (1.0 + wrap), 0.0);
    c = c + L.col.rgb * (L.col.w * att * diff);
  }
  return c;
}
fn ambient(n: vec3f) -> vec3f { return mix(F.amb_gnd.rgb, F.amb_sky.rgb, n.y * 0.5 + 0.5); }
fn keylight(n: vec3f, wrap: f32) -> vec3f {
  return F.key_col.rgb * (F.key_dir.w * max((dot(n, F.key_dir.xyz) + wrap) / (1.0 + wrap), 0.0));
}
fn fog_amount(p: vec3f) -> f32 {
  // exponential height fog integrated along the view ray
  let ro = F.cam_pos.xyz;
  let d = distance(p, ro);
  let rdy = (p.y - ro.y) / max(d, 1e-4);
  let a = F.amb_sky.w;
  let b = F.amb_gnd.w;
  let base = a * exp(-b * max(ro.y, 0.0));
  var integ = base * d;
  if (abs(rdy) > 1e-3) { integ = base * (1.0 - exp(-b * rdy * d)) / (b * rdy); }
  return clamp(1.0 - exp(-integ), 0.0, 1.0);
}
fn apply_fog(c: vec3f, p: vec3f) -> vec3f {
  return mix(c, F.fog_col.rgb, fog_amount(p));
}
fn wind_off(xz: vec2f) -> vec2f {
  let dir = F.wind.xy;
  let w = dot(xz, dir) * 0.22 - F.wind.w;
  let wave = 0.5 + 0.5 * sin(w) + 0.3 * sin(w * 2.37 + xz.x * 0.11 + xz.y * 0.07);
  let fl = sin(F.cam_pos.w * 6.3 + xz.x * 1.7 + xz.y * 1.3) * 0.12;
  return (dir * (0.25 + 0.75 * wave) + vec2f(fl, -fl * 0.6)) * F.wind.z;
}
fn rotate_axis(v: vec3f, a: vec3f, ang: f32) -> vec3f {
  let c = cos(ang); let s = sin(ang);
  return v * c + cross(a, v) * s + a * dot(a, v) * (1.0 - c);
}
"""

# ---------------------------------------------------------------- full-screen sky
SKY = PRELUDE + r"""
struct VOF { @builtin(position) pos: vec4f, @location(0) uv: vec2f };
@vertex fn vs_full(@builtin(vertex_index) i: u32) -> VOF {
  var p = array<vec2f, 3>(vec2f(-1.0, -1.0), vec2f(3.0, -1.0), vec2f(-1.0, 3.0));
  var o: VOF;
  o.pos = vec4f(p[i], 1.0, 1.0);
  o.uv = vec2f(p[i].x * 0.5 + 0.5, 0.5 - p[i].y * 0.5);
  return o;
}

fn kaleido(rd: vec3f, t: f32) -> vec3f {
  // mirrored polar segments around the zenith, folded fractal, hue cycling with the beat
  let n = 6.0 + floor(F.misc.z * 4.0) * 2.0;
  var a = atan2(rd.z, rd.x) + t * 0.05;
  let seg = TAU / n;
  a = abs((a - seg * floor(a / seg)) - seg * 0.5);
  let r = acos(clamp(rd.y, -1.0, 1.0));
  var p = vec2f(cos(a), sin(a)) * r * 2.2;
  var acc = 0.0;
  for (var k = 0; k < 6; k = k + 1) {
    p = abs(p) / max(dot(p, p), 0.08) - vec2f(0.82 + 0.12 * sin(t * 0.13), 0.71);
    acc = acc + exp(-abs(length(p) - 0.6) * 6.0);
  }
  let h = fract(acc * 0.11 + t * 0.03 + F.beat.y * 0.25 + F.misc.y);
  return hsv2rgb(h, 0.8, 0.35 + 0.45 * clamp(acc * 0.25, 0.0, 1.0) * (0.6 + 0.6 * F.audio2.w));
}

@fragment fn fs_sky(in: VOF) -> @location(0) vec4f {
  let ndc = vec2f(in.uv.x * 2.0 - 1.0, 1.0 - in.uv.y * 2.0);
  let pf = F.inv_viewproj * vec4f(ndc, 1.0, 1.0);
  let pn = F.inv_viewproj * vec4f(ndc, 0.0, 1.0);
  let rd = normalize(pf.xyz / pf.w - pn.xyz / pn.w);
  let t = F.cam_pos.w;
  let y = rd.y;
  var c = mix(F.sky_hor.rgb, F.sky_top.rgb, pow(clamp(y, 0.0, 1.0), 0.45));
  if (y < 0.0) { c = mix(F.sky_hor.rgb, F.fog_col.rgb, clamp(-y * 8.0, 0.0, 1.0)); }

  // stars and the milky way
  let sv = F.key_col.w * smoothstep(-0.02, 0.15, y);
  if (sv > 0.001) {
    let g = rd * 160.0;
    let cell = floor(g);
    let h = hash31(cell);
    if (h > 0.985) {
      let off = vec3f(hash31(cell + 1.3), hash31(cell + 2.7), hash31(cell + 4.1));
      let d = length(fract(g) - off);
      let tw = 0.55 + 0.45 * sin(t * (3.0 + 6.0 * hash31(cell + 9.0)) + h * 50.0);
      let b = smoothstep(0.16, 0.0, d) * (0.4 + 2.6 * pow((h - 0.985) / 0.015, 3.0)) * mix(1.0, tw, 0.5 + 0.5 * F.audio2.x);
      c = c + vec3f(0.9, 0.95, 1.0) * b * sv;
    }
    let mwn = normalize(vec3f(0.35, 0.55, 0.76));
    let band = exp(-pow(dot(rd, mwn), 2.0) * 28.0);
    let mw = fbm2(vec2f(atan2(rd.z, rd.x) * 3.0, rd.y * 6.0)) * band;
    c = c + vec3f(0.45, 0.42, 0.6) * mw * 0.22 * sv;
  }
  // aurora curtains
  if (F.sky_hor.w > 0.001 && y > 0.0) {
    var acc = vec3f(0.0);
    for (var k = 0; k < 4; k = k + 1) {
      let hgt = 1.0 + f32(k) * 0.35;
      let q = rd.xz / (y + 0.08) * hgt * 0.35;
      let n = fbm2(q * vec2f(0.6, 2.2) + vec2f(t * 0.04, f32(k) * 3.1 - t * 0.02));
      let curtain = smoothstep(0.55, 0.85, n) * smoothstep(0.0, 0.25, y) * smoothstep(0.9, 0.3, y);
      acc = acc + mix(vec3f(0.1, 1.0, 0.45), vec3f(0.8, 0.2, 1.0), f32(k) / 3.0) * curtain;
    }
    c = c + acc * F.sky_hor.w * (0.25 + 0.55 * F.audio.w);
  }
  // sun
  if (F.sun_sky.w > 0.001) {
    let sd = max(dot(rd, F.sun_sky.xyz), 0.0);
    c = c + vec3f(1.0, 0.6, 0.3) * (pow(sd, 12.0) * 0.6 + pow(sd, 200.0) * 1.5) * F.sun_sky.w;
    c = c + vec3f(1.6, 1.2, 0.8) * smoothstep(0.9993, 0.9996, sd) * F.sun_sky.w * 4.0;
  }
  // moon with phase and maria
  if (F.moon_sky.w > 0.001) {
    let md = dot(rd, F.moon_sky.xyz);
    let rad = 0.032;
    if (md > cos(rad)) {
      let up = normalize(cross(F.moon_sky.xyz, vec3f(1.0, 0.0, 0.0)));
      let rt = cross(up, F.moon_sky.xyz);
      let lp = vec2f(dot(rd, rt), dot(rd, up)) / sin(rad);
      let z = sqrt(max(1.0 - dot(lp, lp), 0.0));
      let ph = F.sky_top.w * TAU;
      let lit = smoothstep(-0.08, 0.08, dot(vec3f(lp, z), vec3f(sin(ph), 0.0, -cos(ph))));
      let maria = 0.75 + 0.25 * fbm2(lp * 3.0 + 7.0);
      c = c + vec3f(1.1, 1.08, 0.95) * lit * maria * F.moon_sky.w * 2.2 + vec3f(0.03, 0.03, 0.05);
    }
    c = c + vec3f(0.35, 0.4, 0.55) * pow(max(md, 0.0), 300.0) * F.moon_sky.w * 0.6;
  }
  // clouds (flat layer), lit from below by the festival
  if (F.fog_col.w > 0.001 && y > 0.0) {
    let tp = 900.0 / (y + 0.02);
    let q = rd.xz * tp * 0.0009 + F.wind.xy * t * 0.004;
    let n = fbm2(q);
    let cov = smoothstep(1.0 - F.fog_col.w, 1.15 - F.fog_col.w * 0.6, n) * smoothstep(0.0, 0.12, y);
    let lit = F.amb_sky.rgb * 1.4 + vec3f(0.12, 0.06, 0.14) * F.audio.x * 0.6;
    c = mix(c, lit, cov * 0.85);
  }
  // psychedelic kaleidoscope sky
  if (F.cam_fwd.w > 0.001) {
    c = mix(c, kaleido(rd, t), F.cam_fwd.w * smoothstep(-0.05, 0.25, y));
  }
  return vec4f(c, 1.0);
}
"""

# ---------------------------------------------------------------- instanced meshes
MESH = PRELUDE + r"""
struct VIn {
  @location(0) pos: vec3f, @location(1) nrm: vec3f, @location(2) uv: vec2f, @location(3) col: vec4f,
  @location(4) r0: vec4f, @location(5) r1: vec4f, @location(6) r2: vec4f,
  @location(7) tint: vec4f, @location(8) emis: vec4f, @location(9) extra: vec4f,
};
struct VOut {
  @builtin(position) clip: vec4f,
  @location(0) wp: vec3f, @location(1) n: vec3f, @location(2) uv: vec2f, @location(3) col: vec4f,
  @location(4) emis: vec4f, @location(5) extra: vec4f, @location(6) @interpolate(flat) mat: u32,
  @location(7) lp: vec3f,
};

fn xf(in: VIn, p: vec3f) -> vec3f {
  return vec3f(dot(in.r0.xyz, p) + in.r0.w, dot(in.r1.xyz, p) + in.r1.w, dot(in.r2.xyz, p) + in.r2.w);
}

@vertex fn vs_mesh(in: VIn) -> VOut {
  var o: VOut;
  let mat = u32(in.tint.a + 0.5);
  var lp = in.pos;
  // cloth: flags flap in the wind, more at the free end
  if (mat == 1u && in.emis.a > 0.0) {
    let t = F.cam_pos.w;
    let w = in.emis.a * (0.35 + F.wind.z);
    lp.z = lp.z + sin(lp.x * 5.5 - t * 9.0 - F.wind.w * 0.7) * 0.11 * lp.x * w;
    lp.y = lp.y + sin(lp.x * 3.0 - t * 6.0) * 0.03 * lp.x * w;
  }
  let origin = vec3f(in.r0.w, in.r1.w, in.r2.w);
  var wp = xf(in, lp);
  var n = normalize(vec3f(dot(in.r0.xyz, in.nrm), dot(in.r1.xyz, in.nrm), dot(in.r2.xyz, in.nrm)));
  if (mat != 1u && in.emis.a > 0.0) {
    let h = clamp(lp.y, 0.0, 1.6);
    let o2 = wind_off(origin.xz) * in.emis.a * h * h;
    wp = wp + vec3f(o2.x, -0.15 * dot(o2, o2), o2.y);
  }
  var flat_k = 0.0;
  if (mat == 5u) {
    // crop circles: stalks inside a pattern are laid down in a swirl, in drawing order
    let fx = (origin.x - CP.field.x) / CP.field.z;
    let fz = (origin.z - CP.field.y) / CP.field.w;
    if (fx >= 0.0 && fx < 1.0 && fz >= 0.0 && fz < 1.0) {
      let dims = textureDimensions(cropmap);
      let c = textureLoad(cropmap, vec2i(i32(fx * f32(dims.x)), i32(fz * f32(dims.y))), 0);
      if (c.a > 0.5) {
        let pid = u32(c.g * 255.0 + 0.5);
        let pp = CP.p[pid];
        let tf = pp.x + c.r * pp.y;
        flat_k = clamp((F.nl.y - tf) / 0.7, 0.0, 1.0);
        if (flat_k > 0.0) {
          let sw = c.b * TAU;
          let dir = vec3f(cos(sw), 0.0, sin(sw));
          let axis = normalize(cross(vec3f(0.0, 1.0, 0.0), dir));
          let ang = flat_k * flat_k * 1.42;
          wp = origin + rotate_axis(wp - origin, axis, ang);
          n = rotate_axis(n, axis, ang);
        }
      }
    }
  }
  o.clip = F.viewproj * vec4f(wp, 1.0);
  o.wp = wp;
  o.n = n;
  o.uv = in.uv;
  o.col = vec4f(in.col.rgb * in.tint.rgb, flat_k);
  o.emis = in.emis;
  o.extra = in.extra;
  o.mat = mat;
  o.lp = lp;
  return o;
}

fn terrain_albedo(p: vec3f) -> vec3f {
  let r = length(p.xz * vec2f(1.0, 1.25));
  let g = fbm2(p.xz * 0.35);
  let g2 = noise2(p.xz * 3.1);
  var grass = mix(vec3f(0.16, 0.26, 0.08), vec3f(0.30, 0.36, 0.12), g) * (0.85 + 0.3 * g2);
  // dancefloor: trampled dirt and straw
  let floor_k = smoothstep(17.0, 11.0, r + (g - 0.5) * 4.0);
  let dirt = mix(vec3f(0.30, 0.21, 0.13), vec3f(0.55, 0.45, 0.25), smoothstep(0.55, 0.75, g2) * 0.7);
  var c = mix(grass, dirt, floor_k);
  // field soil under the corn
  let f = CP.field;
  let inside = step(f.x, p.x) * step(p.x, f.x + f.z) * step(f.y, p.z) * step(p.z, f.y + f.w);
  c = mix(c, vec3f(0.22, 0.15, 0.09) * (0.8 + 0.4 * g2), inside * 0.85);
  // paths
  let path = smoothstep(1.4, 0.6, abs(p.x + sin(p.z * 0.08) * 3.0)) * step(14.0, p.z);
  c = mix(c, vec3f(0.36, 0.28, 0.18), path * 0.8);
  return c;
}

fn crop_flat(p: vec3f) -> vec2f {
  // how far the crop pattern under this point has been laid (0..1), and the lay direction
  let fx = (p.x - CP.field.x) / CP.field.z;
  let fz = (p.z - CP.field.y) / CP.field.w;
  if (fx < 0.0 || fx >= 1.0 || fz < 0.0 || fz >= 1.0) { return vec2f(0.0); }
  let dims = textureDimensions(cropmap);
  let c = textureLoad(cropmap, vec2i(i32(fx * f32(dims.x)), i32(fz * f32(dims.y))), 0);
  if (c.a < 0.5) { return vec2f(0.0); }
  let pp = CP.p[u32(c.g * 255.0 + 0.5)];
  return vec2f(clamp((F.nl.y - (pp.x + c.r * pp.y)) / 0.7, 0.0, 1.0), c.b * TAU);
}

fn tv_screen(uv: vec2f, ch: f32, t: f32) -> vec3f {
  let k = u32(ch + 0.5);
  var c = vec3f(0.0);
  let q = vec2f(uv.x * 2.0 - 1.0, 1.0 - uv.y * 2.0);   // y down, like a screen
  if (k == 0u) { // acid smiley
    let r = length(q);
    let pulse = 0.85 + 0.15 * F.audio2.w;
    c = vec3f(1.0, 0.85, 0.0) * step(r, 0.8 * pulse);
    let e1 = length(q - vec2f(-0.28, -0.22) * pulse); let e2 = length(q - vec2f(0.28, -0.22) * pulse);
    c = c * step(0.1, e1) * step(0.1, e2);
    let m = abs(length(q - vec2f(0.0, -0.05)) - 0.48 * pulse);
    c = c * (1.0 - step(m, 0.06) * step(0.1, q.y));
  } else if (k == 1u) { // spectrum
    let b = u32(clamp(uv.x * 5.0, 0.0, 4.99));
    var v = F.audio.x;
    if (b == 1u) { v = F.audio.y; } else if (b == 2u) { v = F.audio.z; } else if (b == 3u) { v = F.audio.w; } else if (b == 4u) { v = F.audio2.x; }
    c = hsv2rgb(f32(b) * 0.18, 0.9, 1.0) * step(uv.y, v * 0.95) * step(0.15, fract(uv.x * 5.0));
  } else if (k == 2u) { // oscilloscope lissajous
    var best = 9.0;
    for (var s = 0; s < 48; s = s + 1) {
      let a = f32(s) / 48.0 * TAU;
      let p = vec2f(sin(a * 3.0 + t * 1.7), sin(a * 2.0 + t)) * 0.75 * (0.5 + 0.5 * F.audio.y);
      best = min(best, length(q - p));
    }
    c = vec3f(0.2, 1.0, 0.4) * smoothstep(0.09, 0.0, best);
  } else if (k == 3u) { // test card colour bars
    var bars = array<vec3f, 7>(vec3f(0.75), vec3f(0.75, 0.75, 0.0), vec3f(0.0, 0.75, 0.75), vec3f(0.0, 0.75, 0.0),
                               vec3f(0.75, 0.0, 0.75), vec3f(0.75, 0.0, 0.0), vec3f(0.0, 0.0, 0.75));
    c = bars[u32(clamp(uv.x * 7.0, 0.0, 6.99))];
    if (uv.y < 0.28) { c = vec3f(0.06); if (fract(uv.x * 4.0) < 0.25) { c = vec3f(0.9); } }
  } else if (k == 4u) { // static
    c = vec3f(hash21(floor(uv * vec2f(64.0, 48.0)) + floor(t * 30.0) * 7.0));
  } else if (k == 5u) { // pride stripes, scrolling
    let s = u32(fract(uv.y + t * 0.2) * 6.0);
    var pr = array<vec3f, 6>(vec3f(0.89, 0.01, 0.01), vec3f(1.0, 0.55, 0.0), vec3f(1.0, 0.93, 0.0),
                             vec3f(0.0, 0.5, 0.15), vec3f(0.14, 0.25, 0.56), vec3f(0.45, 0.16, 0.51));
    c = pr[s];
  } else if (k == 6u) { // hypno spiral
    let a = atan2(q.y, q.x); let r = length(q);
    c = hsv2rgb(fract(t * 0.1 + F.misc.y), 0.8, 1.0) * step(0.5, fract(a / TAU * 3.0 + r * 3.0 - t * 1.2));
  } else { // 8-bit invader, two frames on the beat
    let g = vec2i(floor(vec2f(uv.x, 1.0 - uv.y) * vec2f(11.0, 8.0)));
    var rows = array<u32, 8>(0x104u, 0x088u, 0x1FCu, 0x376u, 0x7FFu, 0x5FDu, 0x505u, 0x0D8u);
    if ((u32(F.beat.z) & 1u) == 1u) { rows = array<u32, 8>(0x104u, 0x489u, 0x5FDu, 0x777u, 0x7FFu, 0x3FEu, 0x104u, 0x202u); }
    var on = 0u;
    if (g.x >= 0 && g.x < 11 && g.y >= 0 && g.y < 8) { on = (rows[g.y] >> u32(10 - g.x)) & 1u; }
    c = vec3f(0.3, 1.0, 0.3) * f32(on);
  }
  let scan = 0.75 + 0.25 * sin(uv.y * 160.0);
  let vig = smoothstep(1.25, 0.6, length(q));
  return c * scan * vig * 1.6;
}

fn shade_lit(p: vec3f, n: vec3f, alb: vec3f, wrap: f32) -> vec3f {
  return alb * (ambient(n) + keylight(n, wrap) + lights_at(p, n, wrap));
}

@fragment fn fs_mesh(in: VOut) -> @location(0) vec4f {
  var n = normalize(in.n);
  if (dot(n, F.cam_pos.xyz - in.wp) < 0.0) { n = -n; }
  var alb = in.col.rgb;
  var em = in.emis.rgb;
  let t = F.cam_pos.w;
  switch (in.mat) {
    case 1u: { // atlas-textured (flags, banners, decals)
      let uv = mix(in.extra.xy, in.extra.zw, vec2f(in.uv.x, 1.0 - in.uv.y));
      let tx = textureSampleLevel(atlas, samp_n, uv, 0.0);
      if (tx.a < 0.3) { discard; }
      alb = alb * tx.rgb;
    }
    case 2u: {
      alb = terrain_albedo(in.wp);
      let cf = crop_flat(in.wp);
      if (cf.x > 0.0) {   // laid stalks: straw-coloured, with lay lines along the swirl
        let d = vec2f(cos(cf.y), sin(cf.y));
        let lines = 0.75 + 0.25 * sin(dot(in.wp.xz, vec2f(-d.y, d.x)) * 14.0);
        alb = mix(alb, vec3f(0.62, 0.52, 0.26) * lines, cf.x);
        let night = clamp(1.0 - F.nl.z * 2.0, 0.0, 1.0);
        em = em + hsv2rgb(F.misc.y + 0.45, 0.55, 1.0) * cf.x * night * (0.05 + 0.05 * F.audio.z + 0.04 * F.audio2.w);
      }
    }
    case 3u: { // hay
      let s = noise2(vec2f(in.lp.x * 40.0, in.lp.y * 6.0 + in.lp.z * 40.0));
      alb = alb * mix(vec3f(0.62, 0.50, 0.22), vec3f(0.85, 0.72, 0.38), s);
    }
    case 4u: { // wood planks
      let pl = fract(in.uv.y * 6.0);
      alb = alb * (0.75 + 0.25 * noise2(vec2f(in.uv.x * 30.0, floor(in.uv.y * 6.0) * 7.0))) * (0.6 + 0.4 * step(0.08, pl));
    }
    case 6u: { // speaker cone: rings and excursion highlight
      let r = length(in.uv - 0.5) * 2.0;
      let ring = step(0.82, r) * step(r, 0.95) + step(r, 0.22) * 0.7;
      alb = mix(vec3f(0.03), vec3f(0.18), ring);
      em = em + vec3f(0.25, 0.1, 0.35) * in.extra.x * smoothstep(0.95, 0.2, r) * 0.6;
    }
    case 7u: { // CRT television screen
      em = em + tv_screen(in.uv, in.extra.x, t + in.extra.y) * in.extra.z;
      alb = vec3f(0.02);
    }
    case 8u: { // car paint: fresnel sky reflection + specular from stage lights
      let v = normalize(F.cam_pos.xyz - in.wp);
      let fr = pow(1.0 - max(dot(n, v), 0.0), 4.0);
      em = em + mix(F.sky_hor.rgb, F.sky_top.rgb, 0.5) * fr * 0.6;
      let rf = reflect(-v, n);
      em = em + lights_at(in.wp + rf * 0.5, rf, 0.0) * 0.08;
    }
    case 9u: { // pure emissive
      return vec4f(apply_fog(em, in.wp), 1.0);
    }
    case 11u: { // foliage: leafy speckle, translucency
      let s = hash31(floor(in.wp * 6.0));
      alb = alb * (0.7 + 0.5 * s);
      em = em + lights_at(in.wp, -n, 0.0) * alb * 0.25;
    }
    case 5u: { // corn: flattened stalks catch more light (exposed, golden) and glow faintly at night
      let fk = in.col.a;
      alb = mix(alb * 0.85, alb * vec3f(1.7, 1.5, 0.9), fk);
      let night = clamp(1.0 - F.nl.z * 2.0, 0.0, 1.0);
      em = em + hsv2rgb(F.misc.y + 0.45, 0.55, 1.0) * fk * night * (0.10 + 0.08 * F.audio.z + 0.06 * F.audio2.w);
    }
    default: {}
  }
  var c = shade_lit(in.wp, n, alb, 0.25) + em;
  c = apply_fog(c, in.wp);
  return vec4f(c, 1.0);
}

fn flag_col(id: u32, y: f32) -> vec3f {
  let k = clamp(y, 0.0, 0.999);
  if (id == 2u) { var c = array<vec3f, 5>(vec3f(0.36, 0.81, 0.98), vec3f(0.96, 0.66, 0.72), vec3f(1.0), vec3f(0.96, 0.66, 0.72), vec3f(0.36, 0.81, 0.98)); return c[u32(k * 5.0)]; }
  if (id == 3u) { var c = array<vec3f, 3>(vec3f(0.84, 0.01, 0.44), vec3f(0.61, 0.31, 0.59), vec3f(0.0, 0.22, 0.66)); return c[u32(k * 3.0)]; }
  if (id == 4u) { var c = array<vec3f, 4>(vec3f(0.99, 0.96, 0.2), vec3f(1.0), vec3f(0.61, 0.35, 0.82), vec3f(0.17)); return c[u32(k * 4.0)]; }
  if (id == 5u) { var c = array<vec3f, 3>(vec3f(1.0, 0.13, 0.55), vec3f(1.0, 0.85, 0.0), vec3f(0.13, 0.69, 1.0)); return c[u32(k * 3.0)]; }
  var c = array<vec3f, 6>(vec3f(0.89, 0.01, 0.01), vec3f(1.0, 0.55, 0.0), vec3f(1.0, 0.93, 0.0), vec3f(0.0, 0.5, 0.15), vec3f(0.14, 0.25, 0.56), vec3f(0.45, 0.16, 0.51));
  return c[u32(k * 6.0)];
}

// additive translucent meshes: jellyfish bells, light domes
@fragment fn fs_jelly(in: VOut) -> @location(0) vec4f {
  var n = normalize(in.n);
  var emis = in.emis.rgb;
  if (in.extra.y > 0.5) { emis = flag_col(u32(in.extra.y + 0.5), 1.0 - in.lp.y) * max(length(emis), 0.2) * 0.7; }
  let v = normalize(F.cam_pos.xyz - in.wp);
  let fr = pow(1.0 - abs(dot(n, v)), 2.0);
  let rib = 0.65 + 0.35 * sin(atan2(in.lp.z, in.lp.x) * 8.0);
  let inner = smoothstep(0.35, 0.0, length(in.lp.xz)) * smoothstep(0.1, 0.5, in.lp.y);
  var c = emis * (0.12 + 1.6 * fr * rib + 0.8 * inner * in.extra.x);
  let d = distance(in.wp, F.cam_pos.xyz);
  c = c * exp(-d * F.amb_sky.w * 0.6);
  return vec4f(c, 0.0);
}
"""

# ---------------------------------------------------------------- sprites (billboards)
SPRITE = PRELUDE + r"""
struct SIn {
  @builtin(vertex_index) vi: u32,
  @location(0) pos: vec4f,   // feet position, w = roll
  @location(1) size: vec4f,  // width, height, anchor (0 feet .. 0.5 centre), mode
  @location(2) uv: vec4f,    // atlas rect
  @location(3) tint: vec4f,  // rgb multiply, a = flash
};
struct SOut {
  @builtin(position) clip: vec4f,
  @location(0) uv: vec2f, @location(1) wp: vec3f, @location(2) tint: vec4f, @location(3) n: vec3f,
  @location(4) q: vec2f, @location(5) @interpolate(flat) mode: u32,
};

@vertex fn vs_sprite(in: SIn) -> SOut {
  var corners = array<vec2f, 6>(vec2f(0.0, 0.0), vec2f(1.0, 0.0), vec2f(1.0, 1.0), vec2f(0.0, 0.0), vec2f(1.0, 1.0), vec2f(0.0, 1.0));
  let c = corners[in.vi];
  var o: SOut;
  let mode = u32(in.size.w + 0.5);
  var wp: vec3f;
  var n = vec3f(0.0, 1.0, 0.0);
  if (mode == 1u) { // flat on the ground (shadows, decals)
    wp = in.pos.xyz + vec3f((c.x - 0.5) * in.size.x, 0.0, (c.y - 0.5) * in.size.y);
  } else {
    let toc = F.cam_pos.xyz - in.pos.xyz;
    let v = normalize(toc);
    var right = cross(vec3f(0.0, 1.0, 0.0), v);
    if (length(right) < 0.15) { right = F.cam_right.xyz; }
    right = normalize(right);
    let up = cross(v, right);
    var ox = (c.x - 0.5) * in.size.x;
    var oy = (c.y - in.size.z) * in.size.y;
    let ca = cos(in.pos.w); let sa = sin(in.pos.w);
    let rx = ox * ca - oy * sa; let ry = ox * sa + oy * ca;
    wp = in.pos.xyz + right * rx + up * (ry + in.size.z * in.size.y);
    n = normalize(v + vec3f(0.0, 0.35, 0.0));
  }
  o.clip = F.viewproj * vec4f(wp, 1.0);
  o.uv = vec2f(mix(in.uv.x, in.uv.z, c.x), mix(in.uv.w, in.uv.y, c.y));
  o.wp = wp;
  o.tint = in.tint;
  o.n = n;
  o.q = c * 2.0 - 1.0;
  o.mode = mode;
  return o;
}

@fragment fn fs_sprite(in: SOut) -> @location(0) vec4f {
  let tx = textureSampleLevel(atlas, samp_n, in.uv, 0.0);
  if (tx.a < 0.3) { discard; }
  var c: vec3f;
  if (tx.a < 0.92) { // emissive pixels (glowsticks, LEDs, eyes) carry alpha ~0.75 in the atlas
    c = tx.rgb * 2.6;
  } else {
    let alb = tx.rgb * in.tint.rgb;
    c = alb * (ambient(in.n) * 1.3 + keylight(in.n, 0.6) + lights_at(in.wp, in.n, 0.7)) + alb * 0.04;
  }
  c = c + vec3f(in.tint.a);
  c = apply_fog(c, in.wp);
  return vec4f(c, 1.0);
}

@fragment fn fs_shadow(in: SOut) -> @location(0) vec4f {
  let r2 = dot(in.q, in.q);
  if (r2 > 1.0) { discard; }
  let a = pow(1.0 - r2, 1.5) * in.tint.a;
  return vec4f(0.0, 0.0, 0.0, a);
}
"""

# ---------------------------------------------------------------- additive glows: particles, beams, rings
GLOW = PRELUDE + r"""
struct GIn {
  @builtin(vertex_index) vi: u32,
  @location(0) p0: vec4f, @location(1) p1: vec4f, @location(2) col: vec4f, @location(3) par: vec4f, @location(4) uvr: vec4f,
};
struct GOut {
  @builtin(position) clip: vec4f,
  @location(0) q: vec2f, @location(1) col: vec4f, @location(2) par: vec4f, @location(3) uv: vec2f,
  @location(4) @interpolate(flat) mode: u32, @location(5) wp: vec3f,
};

@vertex fn vs_glow(in: GIn) -> GOut {
  var corners = array<vec2f, 6>(vec2f(-1.0, 0.0), vec2f(1.0, 0.0), vec2f(1.0, 1.0), vec2f(-1.0, 0.0), vec2f(1.0, 1.0), vec2f(-1.0, 1.0));
  let c = corners[in.vi];
  let mode = u32(in.par.x + 0.5);
  var o: GOut;
  var wp: vec3f;
  if (mode == 1u) { // beam ribbon from p0 to p1, facing the camera
    let a = in.p1.xyz - in.p0.xyz;
    let mid = mix(in.p0.xyz, in.p1.xyz, c.y);
    var side = cross(a, mid - F.cam_pos.xyz);
    if (length(side) < 1e-6) { side = F.cam_right.xyz; }
    side = normalize(side);
    wp = mid + side * c.x * mix(in.p0.w, in.p1.w, c.y);
    o.q = vec2f(c.x, c.y);
  } else if (mode == 4u) { // flat ring / disc on the ground
    let qq = vec2f(c.x, c.y * 2.0 - 1.0);
    wp = in.p0.xyz + vec3f(qq.x * in.p0.w, 0.0, qq.y * in.p0.w);
    o.q = qq;
  } else { // camera-facing quad
    let qq = vec2f(c.x, c.y * 2.0 - 1.0);
    let ca = cos(in.p1.w); let sa = sin(in.p1.w);
    let r = vec2f(qq.x * ca - qq.y * sa, qq.x * sa + qq.y * ca);
    wp = in.p0.xyz + (F.cam_right.xyz * r.x + F.cam_up.xyz * r.y) * in.p0.w;
    o.q = qq;
  }
  o.clip = F.viewproj * vec4f(wp, 1.0);
  o.col = in.col;
  o.par = in.par;
  o.uv = vec2f(mix(in.uvr.x, in.uvr.z, o.q.x * 0.5 + 0.5), mix(in.uvr.w, in.uvr.y, o.q.y * 0.5 + 0.5));
  o.mode = mode;
  o.wp = wp;
  return o;
}

@fragment fn fs_glow(in: GOut) -> @location(0) vec4f {
  var a = 0.0;
  if (in.mode == 0u) {
    let r2 = dot(in.q, in.q);
    a = exp(-r2 * in.par.y) * step(r2, 1.0);
  } else if (in.mode == 1u) {
    let s = 1.0 - in.q.x * in.q.x;
    a = pow(max(s, 0.0), in.par.y) * mix(1.0, 1.0 - in.q.y, in.par.z);
  } else if (in.mode == 2u) {
    let tx = textureSampleLevel(atlas, samp_n, in.uv, 0.0);
    return vec4f(tx.rgb * tx.a * in.col.rgb, 0.0);
  } else if (in.mode == 4u) {
    let r = length(in.q);
    a = exp(-pow((r - 0.85) / max(in.par.y, 0.01), 2.0)) * step(r, 1.0);
  } else { // mode 3: hard-edged dot (fairy bulbs, LEDs)
    let r2 = dot(in.q, in.q);
    a = smoothstep(1.0, 0.6, r2) + exp(-r2 * 3.0) * 0.4;
  }
  let d = distance(in.wp, F.cam_pos.xyz);
  let fogk = exp(-d * F.amb_sky.w * 0.5);
  return vec4f(in.col.rgb * a * fogk, 0.0);
}
"""

# ---------------------------------------------------------------- post: bloom chain + final grade
POST = r"""
struct VOF { @builtin(position) pos: vec4f, @location(0) uv: vec2f };
@vertex fn vs_full(@builtin(vertex_index) i: u32) -> VOF {
  var p = array<vec2f, 3>(vec2f(-1.0, -1.0), vec2f(3.0, -1.0), vec2f(-1.0, 3.0));
  var o: VOF;
  o.pos = vec4f(p[i], 0.0, 1.0);
  o.uv = vec2f(p[i].x * 0.5 + 0.5, 0.5 - p[i].y * 0.5);
  return o;
}
struct PassU { dir: vec4f };
@group(0) @binding(0) var<uniform> U: PassU;
@group(0) @binding(1) var src: texture_2d<f32>;
@group(0) @binding(2) var sl: sampler;

@fragment fn fs_bright(in: VOF) -> @location(0) vec4f {
  let px = U.dir.zw;
  var c = vec3f(0.0);
  for (var y = -1; y <= 1; y = y + 2) { for (var x = -1; x <= 1; x = x + 2) {
    c = c + textureSampleLevel(src, sl, in.uv + vec2f(f32(x), f32(y)) * px, 0.0).rgb;
  } }
  c = c * 0.25;
  let l = max(c.r, max(c.g, c.b));
  let k = smoothstep(U.dir.x, U.dir.x + U.dir.y, l);
  return vec4f(c * k, 1.0);
}
@fragment fn fs_blur(in: VOF) -> @location(0) vec4f {
  var w = array<f32, 5>(0.227027, 0.1945946, 0.1216216, 0.054054, 0.016216);
  var c = textureSampleLevel(src, sl, in.uv, 0.0).rgb * w[0];
  for (var k = 1; k < 5; k = k + 1) {
    let o = U.dir.xy * f32(k) * 1.4;
    c = c + textureSampleLevel(src, sl, in.uv + o, 0.0).rgb * w[k];
    c = c + textureSampleLevel(src, sl, in.uv - o, 0.0).rgb * w[k];
  }
  return vec4f(c, 1.0);
}
@fragment fn fs_copy(in: VOF) -> @location(0) vec4f {
  return vec4f(textureSampleLevel(src, sl, in.uv, 0.0).rgb, 1.0);
}
"""

COMPOSITE = r"""
struct VOF { @builtin(position) pos: vec4f, @location(0) uv: vec2f };
@vertex fn vs_full(@builtin(vertex_index) i: u32) -> VOF {
  var p = array<vec2f, 3>(vec2f(-1.0, -1.0), vec2f(3.0, -1.0), vec2f(-1.0, 3.0));
  var o: VOF;
  o.pos = vec4f(p[i], 0.0, 1.0);
  o.uv = vec2f(p[i].x * 0.5 + 0.5, 0.5 - p[i].y * 0.5);
  return o;
}
struct Post {
  a: vec4f,      // exposure, bloom strength, saturation, contrast
  lift: vec4f,   // rgb lift (shadows tint), w = vignette
  gain: vec4f,   // rgb gain (highlights tint), w = grain
  fx: vec4f,     // chromatic aberration, invert (impact frame), filter mode, filter amount
  fx2: vec4f,    // time, dither levels, scanline warp, hue rotate
  res: vec4f,    // out W, H, ssaa, unused
  bl: vec4f,     // bloom threshold, knee, unused, unused
};
@group(0) @binding(0) var<uniform> P: Post;
@group(0) @binding(1) var hdr: texture_2d<f32>;
@group(0) @binding(2) var bloom1: texture_2d<f32>;
@group(0) @binding(3) var bloom2: texture_2d<f32>;
@group(0) @binding(4) var sl: sampler;

fn hash21(p: vec2f) -> f32 { var p3 = fract(vec3f(p.xyx) * 0.1031); p3 = p3 + dot(p3, p3.yzx + 33.33); return fract((p3.x + p3.y) * p3.z); }
fn aces(x: vec3f) -> vec3f {
  let a = 2.51; let b = 0.03; let c = 2.43; let d = 0.59; let e = 0.14;
  return clamp((x * (a * x + b)) / (x * (c * x + d) + e), vec3f(0.0), vec3f(1.0));
}
fn hue_rot(c: vec3f, a: f32) -> vec3f {
  let k = vec3f(0.57735);
  let ca = cos(a);
  return c * ca + cross(k, c) * sin(a) + k * dot(k, c) * (1.0 - ca);
}
fn scene_at(uv: vec2f) -> vec3f {
  // box-filter the supersampled HDR target down to output resolution
  let ss = i32(P.res.z);
  let dims = vec2i(textureDimensions(hdr));
  let base = vec2i(floor(uv * vec2f(dims) / f32(ss))) * ss;
  var c = vec3f(0.0);
  for (var y = 0; y < ss; y = y + 1) { for (var x = 0; x < ss; x = x + 1) {
    c = c + textureLoad(hdr, clamp(base + vec2i(x, y), vec2i(0), dims - 1), 0).rgb;
  } }
  return c / f32(ss * ss);
}

@fragment fn fs_comp(in: VOF) -> @location(0) vec4f {
  var uv = in.uv;
  let t = P.fx2.x;
  let fmode = u32(P.fx.z + 0.5);
  if (fmode == 4u) { // VHS tracking wobble
    uv.x = uv.x + (sin(uv.y * 40.0 + t * 7.0) * 0.0015 + step(0.985, fract(uv.y * 3.0 - t * 0.7)) * 0.01) * P.fx.w;
  }
  var c: vec3f;
  let ca = P.fx.x;
  if (ca > 0.0001) {
    let d = (uv - 0.5) * ca;
    c = vec3f(scene_at(uv + d).r, scene_at(uv).g, scene_at(uv - d).b);
  } else {
    c = scene_at(uv);
  }
  c = c + (textureSampleLevel(bloom1, sl, uv, 0.0).rgb * 0.6 + textureSampleLevel(bloom2, sl, uv, 0.0).rgb * 0.9) * P.a.y;
  c = c * P.a.x;
  c = aces(c);
  // grade: lift / gain, saturation, contrast, hue rotation
  c = c * P.gain.rgb + P.lift.rgb * (1.0 - c);
  let l = dot(c, vec3f(0.299, 0.587, 0.114));
  c = mix(vec3f(l), c, P.a.z);
  c = clamp((c - 0.5) * P.a.w + 0.5, vec3f(0.0), vec3f(1.0));
  if (abs(P.fx2.w) > 0.0001) { c = clamp(hue_rot(c, P.fx2.w), vec3f(0.0), vec3f(1.0)); }
  // console filters: 1 handheld green, 2 CGA, 3 red visor, 4 VHS, 5 thermal
  let fa = P.fx.w;
  if (fmode == 1u) {
    let g = dot(c, vec3f(0.3, 0.59, 0.11));
    var shades = array<vec3f, 4>(vec3f(0.06, 0.22, 0.06), vec3f(0.19, 0.38, 0.19), vec3f(0.55, 0.67, 0.06), vec3f(0.61, 0.74, 0.06));
    let bay = hash21(floor(in.pos.xy)) * 0.25;
    let s = u32(clamp(g * 4.0 + bay - 0.12, 0.0, 3.99));
    c = mix(c, shades[s], fa);
  } else if (fmode == 2u) {
    let g = dot(c, vec3f(0.3, 0.59, 0.11));
    var pal = array<vec3f, 4>(vec3f(0.0), vec3f(0.33, 1.0, 1.0), vec3f(1.0, 0.33, 1.0), vec3f(1.0));
    let s = u32(clamp(g * 4.0, 0.0, 3.99));
    c = mix(c, pal[s], fa);
  } else if (fmode == 3u) {
    let g = dot(c, vec3f(0.3, 0.59, 0.11));
    c = mix(c, vec3f(g * 1.2, 0.0, 0.0), fa);
  } else if (fmode == 4u) {
    let g = dot(c, vec3f(0.3, 0.59, 0.11));
    var v = mix(c, vec3f(g) * vec3f(1.05, 0.95, 1.1), 0.35) + (hash21(in.pos.xy + t) - 0.5) * 0.08;
    c = mix(c, v, fa);
  } else if (fmode == 5u) {
    let g = dot(c, vec3f(0.3, 0.59, 0.11));
    let th = clamp(vec3f(g * 3.0 - 1.5, sin(g * 3.14) , 1.0 - g * 2.0), vec3f(0.0), vec3f(1.0));
    c = mix(c, th, fa);
  }
  if (P.fx.y > 0.001) { c = mix(c, vec3f(1.0) - c.gbr, P.fx.y); } // anime impact frame
  // vignette and grain
  let q = in.uv - 0.5;
  c = c * (1.0 - P.lift.w * dot(q, q) * 2.2);
  c = c + (hash21(in.pos.xy * 1.37 + vec2f(t * 61.0, t * 17.0)) - 0.5) * P.gain.w;
  // ordered dither to 5 bits per channel: 16-bit console colour depth
  var bayer = array<f32, 16>(0.0, 8.0, 2.0, 10.0, 12.0, 4.0, 14.0, 6.0, 3.0, 11.0, 1.0, 9.0, 15.0, 7.0, 13.0, 5.0);
  let bi = (u32(in.pos.y) % 4u) * 4u + (u32(in.pos.x) % 4u);
  let lv = P.fx2.y;
  if (lv > 1.0) { c = floor(c * lv + bayer[bi] / 16.0) / lv; }
  return vec4f(clamp(c, vec3f(0.0), vec3f(1.0)), 1.0);
}

// HUD: pixel-space quads, atlas glyphs or solid rectangles, alpha blended over the graded frame
struct HIn { @builtin(vertex_index) vi: u32, @location(0) rect: vec4f, @location(1) uv: vec4f, @location(2) col: vec4f };
struct HOut { @builtin(position) pos: vec4f, @location(0) uv: vec2f, @location(1) col: vec4f, @location(2) @interpolate(flat) solid: u32 };
@group(1) @binding(0) var hatlas: texture_2d<f32>;
@group(1) @binding(1) var hsamp: sampler;
@vertex fn vs_hud(in: HIn) -> HOut {
  var corners = array<vec2f, 6>(vec2f(0.0, 0.0), vec2f(1.0, 0.0), vec2f(1.0, 1.0), vec2f(0.0, 0.0), vec2f(1.0, 1.0), vec2f(0.0, 1.0));
  let c = corners[in.vi];
  let px = in.rect.xy + c * in.rect.zw;
  var o: HOut;
  o.pos = vec4f(px.x / P.res.x * 2.0 - 1.0, 1.0 - px.y / P.res.y * 2.0, 0.0, 1.0);
  o.uv = mix(in.uv.xy, in.uv.zw, c);
  o.col = in.col;
  o.solid = select(0u, 1u, in.uv.x < 0.0);
  return o;
}
@fragment fn fs_hud(in: HOut) -> @location(0) vec4f {
  if (in.solid == 1u) { return in.col; }
  let tx = textureSampleLevel(hatlas, hsamp, in.uv, 0.0);
  if (tx.a < 0.5) { discard; }
  return vec4f(tx.rgb * in.col.rgb, in.col.a);
}
"""
