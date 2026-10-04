"""WGSL for cymatics. One full-screen fragment shader draws every pixel from scratch: the station on screen
(a Chladni plate, a dish of liquid, ferrofluid, a Rubens tube, frozen water streams or laser Lissajous
figures) is evaluated from its mode and the music's bands, and lit like a macro shot in a dark lab. The
canvas keeps each pixel's circle of confusion in alpha; the post pass blurs by it (depth of field and the
rack focus between stations), adds bloom, grades and converts to BT.709 NV12 on the GPU.

Coordinates: p has y up, 1 unit = half the screen height, origin at the centre. The plate, dish and
ferrofluid stations are y-up worlds seen by an orbiting camera; the flame tube and the streams stand in the
plane z = 0. All motion is a pure function of the uniforms, which the Python side computes from the planned
set for each frame index.
"""

COMMON = r"""
struct U {
  res: vec4<f32>,     // w, h, pixel size in p units, aspect
  clk: vec4<f32>,     // animation clock (s), beat flip (beats + eased phase), time since the beat (s), frame
  aud: vec4<f32>,     // kick, sub, bass, lowmid
  aud2: vec4<f32>,    // highmid, high, loudness, calm (0..1)
  a0: vec4<f32>,      // previous mode: station, seed, drive Hz, harmonic
  a1: vec4<f32>,      //   mode parameters 0..3
  a2: vec4<f32>,      //   mode parameters 4..7
  a3: vec4<f32>,      //   key light hue, accent hue, material, -
  b0: vec4<f32>,      // current mode (same layout)
  b1: vec4<f32>,
  b2: vec4<f32>,
  b3: vec4<f32>,
  mixv: vec4<f32>,    // arrival 0..1 (previous -> current), strength of the last beat, defocus 0..1, sweep 0..1
  fx: vec4<f32>,      // drop age (s, -1 none), drop strength, drive gain (lights up / down), low-mid phase
  cam: vec4<f32>,     // azimuth, elevation, distance, target offset
  post: vec4<f32>,    // exposure, chromatic aberration, vignette, bloom
  dbg: vec4<f32>,     // debug mode, depth of field strength, fade to black, saturation
  lay: vec4<f32>,     // layer gains: drive (sub), detail (high mids), sparkle (highs), accent light (bass)
  ext: vec4<f32>,     // the kick's lift in the shadows (display space), -, -, -
};
@group(0) @binding(0) var<uniform> u: U;

const PI: f32 = 3.14159265;
const TAU: f32 = 6.28318531;

fn pcg(x: u32) -> u32 {
  let v = x * 747796405u + 2891336453u;
  let w = ((v >> ((v >> 28u) + 4u)) ^ v) * 277803737u;
  return (w >> 22u) ^ w;
}
fn hbits(p: vec2<f32>) -> u32 {
  return pcg(bitcast<u32>(p.x + 0.0) ^ pcg(bitcast<u32>(p.y + 0.0) + 0x9e3779b9u));
}
fn hash21(p: vec2<f32>) -> f32 {
  return f32(hbits(p) >> 8u) / 16777216.0;
}
fn hash22(p: vec2<f32>) -> vec2<f32> {
  let h = hbits(p);
  return vec2<f32>(f32(h >> 8u) / 16777216.0, f32(pcg(h) >> 8u) / 16777216.0);
}
fn hash23(p: vec2<f32>) -> vec3<f32> {
  let h = hbits(p);
  let h2 = pcg(h);
  return vec3<f32>(f32(h >> 8u) / 16777216.0, f32(h2 >> 8u) / 16777216.0, f32(pcg(h2) >> 8u) / 16777216.0);
}
fn vnoise(p: vec2<f32>) -> f32 {
  let i = floor(p);
  let f = fract(p);
  let w = f * f * (3.0 - 2.0 * f);
  let a = hash21(i);
  let b = hash21(i + vec2<f32>(1.0, 0.0));
  let c = hash21(i + vec2<f32>(0.0, 1.0));
  let d = hash21(i + vec2<f32>(1.0, 1.0));
  return mix(mix(a, b, w.x), mix(c, d, w.x), w.y);
}
fn fbm(p: vec2<f32>, oct: i32) -> f32 {
  var s = 0.0;
  var a = 0.5;
  var q = p;
  for (var k = 0; k < oct; k = k + 1) {
    s = s + a * vnoise(q);
    q = mat2x2<f32>(vec2<f32>(1.6, 1.2), vec2<f32>(-1.2, 1.6)) * q + vec2<f32>(3.1, 1.7);
    a = a * 0.5;
  }
  return s;
}
fn rot(a: f32) -> mat2x2<f32> {
  let c = cos(a);
  let s = sin(a);
  return mat2x2<f32>(vec2<f32>(c, s), vec2<f32>(-s, c));
}
fn luma(c: vec3<f32>) -> f32 { return dot(c, vec3<f32>(0.2126, 0.7152, 0.0722)); }
fn hsv(h: f32, s: f32, v: f32) -> vec3<f32> {
  let k = vec3<f32>(1.0, 2.0 / 3.0, 1.0 / 3.0);
  let p = abs(fract(vec3<f32>(h) + k) * 6.0 - vec3<f32>(3.0));
  return v * mix(vec3<f32>(1.0), clamp(p - vec3<f32>(1.0), vec3<f32>(0.0), vec3<f32>(1.0)), s);
}
// smoothstep that also runs downhill (a > b)
fn sst(a: f32, b: f32, x: f32) -> f32 {
  let t = clamp((x - a) / (b - a), 0.0, 1.0);
  return t * t * (3.0 - 2.0 * t);
}
fn wrapang(a: f32) -> f32 { return a - TAU * floor((a + PI) / TAU); }

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

SCENE = COMMON + r"""
struct Look {
  st: i32,
  seed: f32,
  hz: f32,
  harm: f32,
  m0: vec4<f32>,
  m1: vec4<f32>,
  h1: f32,
  h2: f32,
  mat: i32,
};
fn look_prev() -> Look { return Look(i32(u.a0.x + 0.5), u.a0.y, u.a0.z, u.a0.w, u.a1, u.a2, u.a3.x, u.a3.y, i32(u.a3.z + 0.5)); }
fn look_cur() -> Look { return Look(i32(u.b0.x + 0.5), u.b0.y, u.b0.z, u.b0.w, u.b1, u.b2, u.b3.x, u.b3.y, i32(u.b3.z + 0.5)); }

struct Px {
  col: vec3<f32>,
  coc: f32,           // circle of confusion 0..1 (depth of field)
  fld: f32,           // the experiment's own field, for the criteria (sand, wave height, spikes, flames...)
  pred: f32,          // what the mode alone predicts there (nodal lines, the flames' standing wave), ditto
};

struct Ray { ro: vec3<f32>, rd: vec3<f32> };

// shared per-frame values
fn arrival() -> f32 { return sst(0.0, 1.0, u.mixv.x); }
fn sweepmul() -> f32 { return exp2(u.mixv.w); }
fn chaos() -> f32 {
  let age = u.fx.x;
  if (age < 0.0) { return 0.0; }
  return u.fx.y * exp(-age / 0.55) * sst(-0.01, 0.03, age);
}
fn drive() -> f32 { return u.fx.z * (1.0 - 0.75 * u.aud2.w); }
fn kick() -> f32 { return u.aud.x; }
fn sub_l() -> f32 { return u.aud.y * u.lay.x; }
fn hmid() -> f32 { return u.aud2.x * u.lay.y; }
fn high() -> f32 { return u.aud2.y * u.lay.z; }
fn key_col(L: Look) -> vec3<f32> { return mix(vec3<f32>(1.0, 0.97, 0.92), hsv(L.h1, 0.6, 1.0), 0.4); }
fn acc_col(L: Look) -> vec3<f32> {
  return hsv(L.h2, 0.85, 1.0) * (0.3 + 1.4 * u.aud.z * u.lay.w);
}

fn camera(p: vec2<f32>, tgt: vec3<f32>, fovt: f32) -> Ray {
  let az = u.cam.x;
  let el = u.cam.y;
  let d = u.cam.z;
  let ro = tgt + d * vec3<f32>(cos(el) * sin(az), sin(el), cos(el) * cos(az));
  let fw = normalize(tgt - ro);
  let rt = normalize(cross(fw, vec3<f32>(0.0, 1.0, 0.0)));
  let up = cross(rt, fw);
  return Ray(ro, normalize(fw + (p.x * rt + p.y * up) * fovt));
}
fn focus_coc(dist: f32, fd: f32) -> f32 {
  // macro lenses have a thin plane of focus
  return clamp((abs(dist - fd) / fd - 0.10) * 1.4 * u.dbg.y, 0.0, 1.0);
}

// a dark studio, as seen in reflections: a softbox overhead, a ring light, two coloured strips, the floor
fn studio(d: vec3<f32>, key: vec3<f32>, acc: vec3<f32>, floorc: vec3<f32>) -> vec3<f32> {
  let up = d.y;
  let sb = sst(0.10, 0.04, abs(d.x)) * sst(0.16, 0.08, abs(d.z)) * sst(0.0, 0.3, up);
  var c = key * (sb * 3.0 + sst(0.9, 0.97, up) * 0.15 + exp(-pow((up - 0.42) / 0.025, 2.0)) * 0.8);
  let a = atan2(d.x, d.z) - u.cam.x;
  let band = sst(-0.12, 0.06, up) * sst(0.6, 0.3, up);
  c = c + acc * exp(-pow(wrapang(a - 1.1) / 0.13, 2.0)) * band * 2.2;
  c = c + mix(acc.zxy, key, 0.5) * exp(-pow(wrapang(a + 2.2) / 0.08, 2.0)) * band * 1.1;
  let fe = sin(u.cam.y);
  let front = sst(0.45, 0.30, abs(wrapang(a - PI))) * sst(0.22, 0.12, abs(up - fe)) * sst(0.0, 0.1, up);
  c = c + key * front * 0.9;
  c = c + floorc * sst(0.04, -0.3, up) + vec3<f32>(0.008) * band;
  return c;
}

// the bench everything stands on: dark oiled wood under a pool of light
fn bench(q: vec2<f32>, key: vec3<f32>) -> vec3<f32> {
  let g = fbm(vec2<f32>(q.x * 0.9, q.y * 11.0), 4);
  let wood = mix(vec3<f32>(0.020, 0.013, 0.009), vec3<f32>(0.050, 0.032, 0.021), g);
  return wood * key * (0.3 + 0.7 * exp(-dot(q, q) * 0.15));
}

// ------------------------------------------------------------------ 0. Chladni plate
// m0 = (shape: 0 square / 1 round, n, m, sign), m1.x = rotation. Sand gathers on the nodal lines.
fn chl_sq(x: f32, y: f32, n: f32, m: f32, sg: f32) -> f32 {
  return cos(n * PI * x) * cos(m * PI * y) + sg * cos(m * PI * x) * cos(n * PI * y);
}
fn chl_rd(r: f32, th: f32, m: f32, n: f32, sm: f32) -> f32 {
  // round plate: Bessel-like rings (n nodal circles) and m nodal diameters
  let k = PI * (n * sm + 0.25 * m + 0.25);
  let x = k * r;
  let radial = cos(x - (0.5 * m + 0.25) * PI) * min(1.0, pow(max(x, 1e-4) / (m + 1.0), m)) / sqrt(1.0 + x * 0.5);
  return cos(m * th) * radial;
}
// m0 = (shape: 0 square / 1 round, n, m, sign), m1 = (rotation, second mode's n, m, its share)
fn chl_z(q: vec2<f32>, L: Look, sm: f32) -> f32 {
  let qq = rot(L.m1.x) * q;
  if (L.m0.x < 0.5) {
    let x = qq.x * 0.5 + 0.5;
    let y = qq.y * 0.5 + 0.5;
    return chl_sq(x, y, L.m0.y * sm, L.m0.z * sm, L.m0.w) + L.m1.w * chl_sq(x, y, L.m1.y * sm, L.m1.z * sm, -L.m0.w);
  }
  let r = length(qq);
  let th = atan2(qq.y, qq.x);
  return chl_rd(r, th, L.m0.y, L.m0.z, sm) + L.m1.w * chl_rd(r, th + 0.4, L.m1.y, L.m1.z, sm);
}
// sand on the lines: distance to the nearest nodal line, in plate units
fn chl_line(q: vec2<f32>, L: Look, sm: f32) -> f32 {
  let e = 0.002;
  let z = chl_z(q, L, sm);
  let gx = chl_z(q + vec2<f32>(e, 0.0), L, sm) - chl_z(q - vec2<f32>(e, 0.0), L, sm);
  let gy = chl_z(q + vec2<f32>(0.0, e), L, sm) - chl_z(q - vec2<f32>(0.0, e), L, sm);
  return abs(z) / max(length(vec2<f32>(gx, gy)) / (2.0 * e), 1e-3);
}
fn chl_inside(q: vec2<f32>, L: Look) -> f32 {
  // signed distance to the plate's edge (negative inside)
  if (L.m0.x < 0.5) {
    let d = abs(q) - vec2<f32>(0.94);
    return length(max(d, vec2<f32>(0.0))) + min(max(d.x, d.y), 0.0) - 0.06;
  }
  return length(q) - 1.0;
}

fn station_chladni(p: vec2<f32>) -> Px {
  let Lc = look_cur();
  let Lp = look_prev();
  let key = key_col(Lc);
  let acc = acc_col(Lc);
  let s = arrival();
  let sm = sqrt(sweepmul());
  let ang = Lc.seed * TAU;
  let tgt = vec3<f32>(cos(ang), 0.0, sin(ang)) * u.cam.w;
  let ray = camera(p, tgt, 0.36);
  var o: Px;
  let t = -ray.ro.y / min(ray.rd.y, -1e-4);
  let hit = ray.ro + ray.rd * t;
  let q = hit.xz;
  let fw = max(length(fwidth(q)), 1e-5);   // before any branch: derivatives need uniform control flow
  let edge = chl_inside(q, Lc);
  let ldir = normalize(vec3<f32>(0.35, 1.0, 0.45));
  let gaz = u.cam.x + 1.1;
  let gdir = normalize(vec3<f32>(sin(gaz), 0.28, cos(gaz)));
  if (edge > 0.0) {
    let t2 = (-0.12 - ray.ro.y) / min(ray.rd.y, -1e-4);
    let h2 = ray.ro + ray.rd * t2;
    let sh = sst(0.0, 0.35, chl_inside(h2.xz - vec2<f32>(0.04, 0.06), Lc));
    o.col = bench(h2.xz, key) * (0.25 + 0.75 * sh);
    o.coc = focus_coc(t2, u.cam.z);
    o.fld = 0.0;
    return o;
  }
  // the sand: how likely each grain cell is to hold a grain
  let dc = chl_line(q, Lc, sm);
  let mig = sin(PI * s);                    // sand in flight while the pattern re-forms
  let ch = chaos();
  let w0 = 0.011;
  let w = w0 * (1.0 + 2.2 * mig + 2.0 * ch);
  var rho = exp(-pow(dc / w, 2.0));
  if (s < 0.999) {
    var rp = 0.30;                          // from scattered sand (the first pattern of the night)
    if (Lp.st == 0) {
      let dp = chl_line(q, Lp, sm);
      rp = exp(-pow(dp / w, 2.0));
    }
    rho = mix(rp, rho, s);
  }
  let scat = 0.30 * (0.6 + 0.8 * vnoise(q * 9.0 + vec2<f32>(u.clk.x * 0.7, 0.0)));
  rho = mix(rho, scat, clamp(ch * 1.3, 0.0, 1.0));
  rho = clamp(rho + 0.025, 0.0, 1.0);
  // grains: one per cell at most, jittered, hopping on the kick (the antinodes throw them hardest)
  let g = 0.0046;
  let antinode = clamp(dc / 0.09, 0.0, 1.0);
  let hop = (0.18 * sub_l() * drive() + 0.9 * kick() * drive() + 2.5 * ch) * (0.15 + 0.85 * antinode);
  let fizz = 0.22 * hmid() * drive();
  let beat = floor(u.clk.y);
  let fz = floor(u.clk.x * 24.0);
  var cov = 0.0;
  var gcol = vec3<f32>(0.0);
  let c0 = floor(q / g);
  var sand = vec3<f32>(0.86, 0.82, 0.74);
  var plate = vec3<f32>(0.010, 0.010, 0.012);
  if (Lc.mat == 1) { sand = vec3<f32>(0.035, 0.033, 0.03); plate = vec3<f32>(0.30, 0.30, 0.31); }
  if (Lc.mat == 2) { sand = vec3<f32>(0.95, 0.66, 0.30); plate = vec3<f32>(0.012, 0.010, 0.010); }
  if (Lc.mat == 3) { sand = vec3<f32>(0.92, 0.94, 0.97); plate = vec3<f32>(0.006, 0.012, 0.035); }
  for (var j = -1; j <= 1; j = j + 1) {
    for (var i = -1; i <= 1; i = i + 1) {
      let c = c0 + vec2<f32>(f32(i), f32(j));
      let hh = hash23(c);
      if (hh.x > rho) { continue; }
      let jit = hash22(c + vec2<f32>(beat * 1.37, 7.1)) - 0.5;
      let jz = hash22(c + vec2<f32>(fz * 0.71, 3.3)) - 0.5;
      let ctr = (c + vec2<f32>(0.5) + (hh.yz - 0.5) * 0.55) * g + jit * g * 1.7 * hop + jz * g * fizz;
      let rr = g * (0.30 + 0.16 * hh.y);
      let d = length(q - ctr);
      let a = sst(rr + fw * 0.7, rr - fw * 0.7, d);
      if (a > cov) {
        let l = (q - ctr) / rr;
        let n = normalize(vec3<f32>(l.x, sqrt(max(1.0 - dot(l, l), 0.05)), l.y));
        let tone = 0.75 + 0.5 * hh.z;
        var gc = sand * tone * (key * (0.08 + 0.9 * max(dot(n, ldir), 0.0)) + acc * 1.4 * pow(max(dot(n, gdir), 0.0), 2.0));
        let spk = select(0.0, 1.0, hash21(c + vec2<f32>(floor(u.clk.x * 9.0), 1.9)) < 0.05 * high());
        gc = gc + key * spk * 3.5 * max(n.y, 0.0);
        cov = a;
        gcol = gc;
      }
    }
  }
  // the plate: dark metal mirroring the softbox, shadowed where the sand lies thick
  let rd2 = reflect(ray.rd, vec3<f32>(0.0, 1.0, 0.0));
  let fr = 0.04 + 0.5 * pow(1.0 - abs(ray.rd.y), 5.0);
  var pc = plate * key * (0.6 + 0.4 * dot(ldir, vec3<f32>(0.0, 1.0, 0.0))) + studio(rd2, key, acc, vec3<f32>(0.01)) * fr * select(0.35, 0.12, Lc.mat == 1);
  if (Lc.mat == 1) { pc = pc * (0.85 + 0.3 * vnoise(vec2<f32>(dot(q, vec2<f32>(0.7, 0.7)) * 300.0, 0.0))); }
  pc = pc * (1.0 - 0.45 * clamp(rho * 1.2 - 0.05, 0.0, 1.0));
  // grains smaller than a pixel become a density
  let lod = sst(0.45 * g, 0.9 * g, fw);
  let avg = sand * (key * 0.62 + acc * 0.35);
  var col = mix(pc, gcol, cov);
  col = mix(col, mix(pc, avg, clamp(rho * 0.62, 0.0, 1.0)), lod);
  // the bevelled edge catches the light; the drive bolt sits in the middle
  let rim = exp(-abs(edge + 0.004) / 0.003);
  col = col + (key * 0.25 + acc * 0.5) * rim;
  if (length(q) < 0.055) {
    let l = q / 0.055;
    let n = normalize(vec3<f32>(l.x, sqrt(max(1.0 - dot(l, l), 0.0)) + 0.3, l.y));
    col = studio(reflect(ray.rd, n), key, acc, vec3<f32>(0.03)) * 0.8;
  }
  o.col = col;
  o.coc = focus_coc(t, u.cam.z);
  o.fld = rho;
  o.pred = exp(-pow(dc / w0, 2.0));
  return o;
}

// ------------------------------------------------------------------ 1. Faraday waves
// m0 = (directions, -, rotation, phase seed). Standing waves on a dish of liquid, flipping on the beat.
fn far_k(L: Look) -> f32 { return 14.0 * pow(L.hz * sweepmul() / 55.0, 0.6667); }
// waves finer than about four pixels fade out instead of aliasing into noise
fn far_aa(k: f32, fw: f32) -> f32 { return 1.0 - sst(0.12, 0.25, k * fw / TAU); }
fn far_wave(q: vec2<f32>, L: Look, amp: f32, fw: f32, flip: f32) -> vec3<f32> {
  let nd = i32(L.m0.x + 0.5);
  let k = far_k(L);
  var h = 0.0;
  var g = vec2<f32>(0.0);
  for (var i = 0; i < nd; i = i + 1) {
    let a = L.m0.z + f32(i) * PI / f32(nd);
    let d = vec2<f32>(cos(a), sin(a));
    let ph = hash21(vec2<f32>(L.m0.w * 97.0, f32(i))) * TAU;
    let arg = k * dot(d, q) + ph + PI * flip;
    h = h + cos(arg);
    g = g - sin(arg) * k * d;
  }
  return vec3<f32>(h, g) * amp / f32(nd) * far_aa(k, fw);
}
fn station_faraday(p: vec2<f32>) -> Px {
  let Lc = look_cur();
  let Lp = look_prev();
  let key = key_col(Lc);
  let acc = acc_col(Lc);
  let s = arrival();
  let ang = Lc.seed * TAU;
  let tgt = vec3<f32>(cos(ang), 0.0, sin(ang)) * u.cam.w;
  let ray = camera(p, tgt, 0.36);
  var o: Px;
  let t = -ray.ro.y / min(ray.rd.y, -1e-4);
  let hit = ray.ro + ray.rd * t;
  let q = hit.xz;
  let fw = max(length(fwidth(q)), 1e-5);   // before any branch: derivatives need uniform control flow
  let r = length(q);
  if (r > 1.0) {
    // the dish's rim, then the bench
    if (r < 1.06) {
      let k = (r - 1.03) / 0.03;
      let n = normalize(vec3<f32>(q.x / r * k, sqrt(max(1.0 - k * k, 0.0)) + 0.2, q.y / r * k));
      o.col = studio(reflect(ray.rd, n), key, acc, vec3<f32>(0.02)) * 0.7;
    } else {
      let t2 = (-0.08 - ray.ro.y) / min(ray.rd.y, -1e-4);
      let h2 = ray.ro + ray.rd * t2;
      o.col = bench(h2.xz, key) * (0.3 + 0.7 * sst(1.0, 1.35, length(h2.xz - vec2<f32>(0.05, 0.08))));
    }
    o.coc = focus_coc(t, u.cam.z);
    o.fld = 0.0;
    return o;
  }
  let ch = chaos();
  // (the kick shows as the flip and a ring; swelling the waves on it would darken a mirror-like dish)
  let amp = drive() * (0.30 + 0.70 * sub_l()) * (1.0 + 2.0 * ch);
  let damp = sst(1.0, 0.86, r);
  var w = far_wave(q, Lc, amp, fw, u.clk.y);
  if (s < 0.999) {
    var wp = vec3<f32>(0.0);
    if (Lp.st == 1) { wp = far_wave(q, Lp, amp, fw, u.clk.y); }
    w = mix(wp, w, s);
  }
  // the overdrive breaks the lattice into a choppy sea
  if (ch > 0.01) {
    let k2 = far_k(Lc) * 1.7;
    for (var i = 0; i < 3; i = i + 1) {
      let a = f32(i) * 2.1 + u.clk.x * 0.3;
      let d = vec2<f32>(cos(a), sin(a));
      let arg = k2 * dot(d, q) + u.clk.x * 9.0 + f32(i);
      w = w + vec3<f32>(cos(arg), -sin(arg) * k2 * d) * ch * 0.5 * far_aa(k2, fw);
    }
  }
  // capillary ripples with the high mids, a ring from the centre on each kick
  let kd = far_k(Lc) * 3.1;
  var cap = vec3<f32>(0.0);
  for (var i = 0; i < 3; i = i + 1) {
    let a = Lc.m0.z + 0.7 + f32(i) * 2.0;
    let d = vec2<f32>(cos(a), sin(a));
    let arg = kd * dot(d, q) - u.clk.x * 14.0 + f32(i) * 1.7;
    cap = cap + vec3<f32>(cos(arg), -sin(arg) * kd * d);
  }
  w = w + cap * 0.10 * hmid() * drive() * far_aa(kd, fw);
  let ba = u.clk.z;
  let R = 0.1 + 1.5 * ba;
  let ring = exp(-pow((r - R) / 0.04, 2.0)) * exp(-ba * 3.0) * u.mixv.y * drive() * 0.35 * far_aa(38.0, fw);
  let rarg = 38.0 * (r - R);
  w = w + vec3<f32>(cos(rarg), -sin(rarg) * 38.0 * q / max(r, 1e-3)) * ring;
  w = w * damp;
  let H0 = 0.012;
  // a meniscus climbs the wall
  let men = 0.03 * exp(-(1.0 - r) / 0.025);
  let gm = q / max(r, 1e-3) * men / 0.025;
  let n = normalize(vec3<f32>(-(w.y * H0 + gm.x), 1.0, -(w.z * H0 + gm.y)));
  let refl = reflect(ray.rd, n);
  let cosv = max(dot(n, -ray.rd), 0.0);
  var col = vec3<f32>(0.0);
  let ldir = normalize(vec3<f32>(0.3, 1.0, 0.4));
  let gaz = u.cam.x + 1.1;
  let gdir = normalize(vec3<f32>(sin(gaz), 0.25, cos(gaz)));
  let flow = vec2<f32>(u.clk.x * 0.03, -u.clk.x * 0.02);
  let dye = fbm(q * 1.6 + flow + vec2<f32>(Lc.seed * 13.0), 4);
  if (Lc.mat < 2) {
    // ink: the pattern is drawn by the reflections of the lights (white, or coloured gels)
    let fr = 0.05 + 0.95 * pow(1.0 - cosv, 5.0);
    let base = mix(vec3<f32>(0.004, 0.006, 0.014), hsv(Lc.h2, 0.8, 0.03), dye);
    var lk = key;
    if (Lc.mat == 1) { lk = mix(key, hsv(Lc.h1, 0.85, 1.0), 0.85); }
    col = base + studio(refl, lk, acc, vec3<f32>(0.01)) * (fr * 1.4 + 0.03);
  } else {
    // a pool of liquid metal
    col = studio(refl, key, acc, vec3<f32>(0.03)) * vec3<f32>(0.80, 0.82, 0.86) + vec3<f32>(0.01);
  }
  // spray off the crests in the overdrive, glints with the hats
  let crest = sst(0.6, 1.0, w.x / max(amp, 1e-3));
  let spark = hash21(floor(q * 260.0) + vec2<f32>(floor(u.clk.x * 10.0), 0.0));
  col = col + key * crest * select(0.0, 2.5, spark < 0.02 * high() + 0.08 * ch);
  o.col = col;
  o.coc = focus_coc(t, u.cam.z);
  o.fld = w.x / max(amp, 1e-3) * 0.5 + 0.5;
  return o;
}

// ------------------------------------------------------------------ 2. Ferrofluid
// m0 = (lattice: 0 hexagonal / 1 rings, -, rotation, height). Spikes rise where the field is strongest.
fn fer_a(L: Look) -> f32 { return clamp(0.30 * sqrt(55.0 / (L.hz * sweepmul())), 0.075, 0.32); }
fn fer_site(q: vec2<f32>, L: Look, a: f32) -> vec2<f32> {
  let rr = rot(L.m0.z + 0.12 * u.fx.w);
  if (L.m0.x < 0.5) {
    let p = (rr * q) / a;
    let sz = vec2<f32>(1.0, 1.7320508);
    let hz = sz * 0.5;
    let pa = p - sz * floor(p / sz) - hz;
    let pb = p - hz - sz * floor((p - hz) / sz) - hz;
    var off = pa;
    if (dot(pb, pb) < dot(pa, pa)) { off = pb; }
    return transpose(rr) * ((p - off) * a);
  }
  let r = length(q);
  let i = round(r / a);
  if (i < 0.5) { return vec2<f32>(0.0); }
  let nr = max(round(TAU * i), 1.0);
  let th = atan2(q.y, q.x) - L.m0.z - 0.12 * u.fx.w + i * 0.37;
  let j = round(th * nr / TAU);
  let a2 = j * TAU / nr + L.m0.z + 0.12 * u.fx.w - i * 0.37;
  return vec2<f32>(cos(a2), sin(a2)) * i * a;
}
fn fer_spike(q: vec2<f32>, L: Look, amp: f32) -> f32 {
  let a = fer_a(L);
  let site = fer_site(q, L, a);
  let fs = clamp(1.0 - pow(length(site) / 0.86, 2.0), 0.0, 1.0);
  let hs = a * 1.55 * amp * pow(fs, 0.6) * L.m0.w;
  let d = length(q - site) / (0.5 * a);
  return hs * pow(max(1.0 - d, 0.0), 1.7);
}
fn fer_h(q: vec2<f32>, Lc: Look, Lp: Look, s: f32, amp: f32) -> f32 {
  let r = length(q);
  let pool = 0.035 * sst(0.98, 0.84, r);
  if (pool <= 0.0) { return 0.0; }
  var sp = fer_spike(q, Lc, amp);
  if (s < 0.999) {
    var spp = 0.0;
    if (Lp.st == 2) { spp = fer_spike(q, Lp, amp); }
    sp = mix(spp, sp, s);
  }
  return pool + sp * sst(0.0, 0.035, pool);
}
fn station_ferro(p: vec2<f32>) -> Px {
  let Lc = look_cur();
  let Lp = look_prev();
  let key = key_col(Lc);
  let acc = acc_col(Lc);
  let s = arrival();
  let ch = chaos();
  let amp = drive() * (0.22 + 0.78 * sub_l()) * (1.0 + 0.45 * kick()) + 0.9 * ch;
  let ang = Lc.seed * TAU;
  let tgt = vec3<f32>(cos(ang) * u.cam.w, 0.05, sin(ang) * u.cam.w);
  let ray = camera(p, tgt, 0.36);
  var o: Px;
  let top = 0.035 + 0.32 * 1.55 * max(amp, 0.05) * 1.2 + 0.01;
  var t = max((top - ray.ro.y) / min(ray.rd.y, -1e-4), 0.0);
  let tfar = (-0.001 - ray.ro.y) / min(ray.rd.y, -1e-4);
  var hit = false;
  var tp = t;
  for (var i = 0; i < 160; i = i + 1) {
    let pos = ray.ro + ray.rd * t;
    let h = fer_h(pos.xz, Lc, Lp, s, amp);
    let dy = pos.y - h;
    if (dy < 0.0004) { hit = true; break; }
    tp = t;
    t = t + max(dy * 0.28, 0.0012);
    if (t > tfar) { t = tfar; hit = true; break; }
  }
  // refine between the last step above the surface and the first below
  var lo = tp;
  var hi = t;
  for (var i = 0; i < 6; i = i + 1) {
    let mid = 0.5 * (lo + hi);
    let pos = ray.ro + ray.rd * mid;
    if (pos.y - fer_h(pos.xz, Lc, Lp, s, amp) < 0.0) { hi = mid; } else { lo = mid; }
  }
  t = hi;
  let pos = ray.ro + ray.rd * t;
  let q = pos.xz;
  let r = length(q);
  let e = 0.0015;
  let hx = fer_h(q + vec2<f32>(e, 0.0), Lc, Lp, s, amp) - fer_h(q - vec2<f32>(e, 0.0), Lc, Lp, s, amp);
  let hz = fer_h(q + vec2<f32>(0.0, e), Lc, Lp, s, amp) - fer_h(q - vec2<f32>(0.0, e), Lc, Lp, s, amp);
  var n = normalize(vec3<f32>(-hx / (2.0 * e), 1.0, -hz / (2.0 * e)));
  let fluid = r < 0.975 && pos.y > 0.0015;
  var floorc = vec3<f32>(0.5, 0.5, 0.52) * key;
  if (Lc.mat == 1) { floorc = vec3<f32>(0.015); }
  if (Lc.mat == 2) { floorc = hsv(Lc.h2, 0.85, 1.0) * (0.55 + 0.45 * u.aud.z * u.lay.w) + vec3<f32>(0.02); }
  var col = vec3<f32>(0.0);
  if (fluid) {
    // high mids shiver across the surface
    let rip = vec2<f32>(vnoise(q * 40.0 + vec2<f32>(u.clk.x * 3.0, 0.0)), vnoise(q * 40.0 + vec2<f32>(7.0, u.clk.x * 3.0))) - 0.5;
    n = normalize(n + vec3<f32>(rip.x, 0.0, rip.y) * 0.25 * hmid() * drive());
    let cosv = max(dot(n, -ray.rd), 0.0);
    let fr = 0.045 + 0.955 * pow(1.0 - cosv, 5.0);
    col = studio(reflect(ray.rd, n), key, acc, floorc) * fr * 1.25 + vec3<f32>(0.002);
    let tip = sst(0.6, 0.95, (pos.y - 0.035) / max(0.32 * 1.25 * max(amp, 0.05) * 0.6, 1e-3));
    let spk = hash21(floor(q * 90.0) + vec2<f32>(floor(u.clk.x * 8.0), 4.0));
    col = col + key * tip * select(0.0, 3.0, spk < 0.08 * high());
  } else {
    let gaz = u.cam.x + 1.1;
    let gdir = normalize(vec3<f32>(sin(gaz), 0.3, cos(gaz)));
    let shade = sst(0.97, 1.35, r);
    if (Lc.mat == 0) {
      col = vec3<f32>(0.62, 0.62, 0.64) * key * (0.35 + 0.45 * shade) + acc * 0.08 * max(dot(gdir, vec3<f32>(0.0, 1.0, 0.0)), 0.0);
    } else if (Lc.mat == 1) {
      col = studio(reflect(ray.rd, vec3<f32>(0.0, 1.0, 0.0)), key, acc, vec3<f32>(0.01)) * 0.25 * (0.3 + 0.7 * shade);
    } else {
      col = hsv(Lc.h2, 0.85, 1.0) * (0.55 + 0.45 * u.aud.z * u.lay.w) * (0.55 + 0.25 * vnoise(q * 3.0)) * (0.5 + 0.5 * shade) + vec3<f32>(0.01);
    }
    col = col * (0.15 + 0.85 * sst(0.0, 2.0, length(q)));
  }
  o.col = col;
  o.coc = focus_coc(t, u.cam.z);
  o.fld = clamp((pos.y - 0.03) * 6.0, 0.0, 1.0);
  return o;
}

// ------------------------------------------------------------------ 3. Rubens tube
// m0 = (pattern: 0 standing wave / 1 spectrum / 2 standing wave + travelling pulses, phase). The flames
// stand in the plane z = 0 along a brass tube from x = -2.6 to 2.6.
const RT_R: f32 = 0.06;
const RT_L: f32 = 2.6;
const RT_S: f32 = 0.072;
fn rub_amp(x: f32, L: Look) -> f32 {
  let xn = (x + RT_L) / (2.0 * RT_L);
  let kind = i32(L.m0.x + 0.5);
  if (kind == 1) {
    // the spectrum along the tube, lows at the speaker end
    var b = array<f32, 5>(u.aud.y, u.aud.z, u.aud.w, u.aud2.x, u.aud2.y);
    let f = clamp(xn * 4.0, 0.0, 3.999);
    let i = i32(floor(f));
    return mix(b[i], b[i + 1], f - f32(i)) * 1.15;
  }
  let nh = clamp(L.hz * sweepmul() / 22.0, 2.0, 26.0);
  var a = abs(sin(PI * nh * xn + L.m0.y * PI)) * (0.4 + 0.75 * sub_l());
  if (kind == 2) {
    a = a + exp(-pow((xn - 0.8 * u.clk.z) / 0.06, 2.0)) * u.mixv.y * 0.8;
  }
  return a;
}
fn rub_height(x: f32, Lc: Look, Lp: Look, s: f32) -> f32 {
  var a = rub_amp(x, Lc);
  if (s < 0.999) {
    var ap = 0.0;
    if (Lp.st == 3) { ap = rub_amp(x, Lp); }
    a = mix(ap, a, s);
  }
  let ch = chaos();
  return 0.035 + drive() * (0.05 + 0.28 * a) * (1.0 + 0.22 * kick()) + ch * 0.32;
}
// emission of the flames at (x, y), y measured from the tube's centre line
fn rub_flames(x: f32, y: f32, Lc: Look, Lp: Look, s: f32) -> vec3<f32> {
  if (abs(x) > RT_L || y < RT_R - 0.01) { return vec3<f32>(0.0); }
  let i0 = round(x / RT_S);
  var e = vec3<f32>(0.0);
  for (var k = -1; k <= 1; k = k + 1) {
    let i = i0 + f32(k);
    let xi = i * RT_S;
    if (abs(xi) > RT_L - 0.05) { continue; }
    let h = rub_height(xi, Lc, Lp, s) * (0.9 + 0.2 * hash21(vec2<f32>(i, 3.0)));
    let v = (y - RT_R) / h;
    if (v < -0.05 || v > 1.3) { continue; }
    let fl = vnoise(vec2<f32>(i * 3.7, v * 2.6 - u.clk.x * 4.5)) - 0.5;
    let fl2 = vnoise(vec2<f32>(i * 1.3 + 9.0, v * 6.0 - u.clk.x * 9.0)) - 0.5;
    let ud = (x - xi) / (0.5 * RT_S) - (fl * 1.5 + fl2 * 0.6 * (0.5 + 1.5 * hmid())) * v;
    let wpr = 0.80 * sqrt(clamp(v * 6.0, 0.0, 1.0)) * pow(clamp(1.0 - v * 0.85, 0.0, 1.0), 0.6) + 0.02;
    let dens = sst(wpr, wpr * 0.2, abs(ud)) * sst(1.15, 0.6, v) * sst(-0.04, 0.03, v);
    let core = sst(wpr * 0.55, 0.0, abs(ud)) * sst(0.75, 0.2, v);
    let blue = exp(-max(v, 0.0) / 0.07) * vec3<f32>(0.15, 0.35, 1.0) * 1.2;
    let body = mix(vec3<f32>(1.0, 0.32, 0.06), vec3<f32>(1.0, 0.78, 0.38), core) * mix(1.0, 0.5, sst(0.5, 1.1, v));
    e = e + (blue * 0.8 + body * (1.0 - exp(-max(v, 0.0) / 0.05))) * dens * 1.9;
  }
  return e;
}
fn rub_wall(x: f32, y: f32, Lc: Look, Lp: Look, s: f32) -> vec3<f32> {
  // the back wall, warmed by the flames
  let fh = rub_height(clamp(x, -RT_L, RT_L), Lc, Lp, s);
  let glow = fh * exp(-max(y - RT_R, 0.0) / 0.6) * exp(-max(-y, 0.0) / 0.25) * sst(RT_L + 0.9, RT_L - 0.2, abs(x));
  return vec3<f32>(0.006, 0.006, 0.009) + vec3<f32>(1.0, 0.45, 0.15) * glow * 0.14 + acc_col(Lc) * 0.008;
}
fn rub_solid(x: f32, y: f32, rd: vec3<f32>, Lc: Look, Lp: Look, s: f32) -> vec4<f32> {
  let key = key_col(Lc);
  let acc = acc_col(Lc);
  if (abs(y) < RT_R && abs(x) < RT_L) {
    let ny = y / RT_R;
    let n = vec3<f32>(0.0, ny, sqrt(max(1.0 - ny * ny, 0.0)));
    var metal = vec3<f32>(0.78, 0.55, 0.25);
    if (Lc.mat == 1) { metal = vec3<f32>(0.80, 0.42, 0.28); }
    if (Lc.mat == 2) { metal = vec3<f32>(0.62, 0.64, 0.68); }
    let fh = rub_height(x, Lc, Lp, s);
    let warm = vec3<f32>(1.0, 0.5, 0.18) * fh * 6.0 * max(ny, 0.0);
    let env = studio(reflect(rd, n), key, acc, vec3<f32>(0.02));
    var col = metal * (env * 0.75 + warm * 0.6 + key * 0.02);
    // the row of holes along the top
    let hx = abs(x - round(x / RT_S) * RT_S);
    col = col * (1.0 - 0.8 * sst(0.006, 0.003, hx) * sst(0.8, 0.95, ny));
    return vec4<f32>(col, 1.0);
  }
  if (x < -RT_L && x > -RT_L - 0.32 && abs(y) < 0.2) {
    // the speaker that drives it
    let l = vec2<f32>((x + RT_L + 0.16) / 0.16, y / 0.2);
    return vec4<f32>(vec3<f32>(0.02) + acc * 0.05 * max(1.0 - length(l), 0.0) + key * 0.03 * sst(0.9, 1.0, max(abs(l.x), abs(l.y))), 1.0);
  }
  if (x > RT_L && x < RT_L + 0.04 && abs(y) < RT_R * 1.3) {
    return vec4<f32>(vec3<f32>(0.03) * key, 1.0);
  }
  if (abs(y + 0.18) < 0.12 && abs(abs(x) - 1.9) < 0.02) {
    // the stands it rests on
    return vec4<f32>(vec3<f32>(0.03, 0.03, 0.035) * key, 1.0);
  }
  return vec4<f32>(0.0);
}
const RT_WALL: f32 = -1.2;
const RT_FLOOR: f32 = -0.30;
// the view without the bench's mirror image: (colour, distance to the main surface)
fn rub_view(ro: vec3<f32>, rd: vec3<f32>, Lc: Look, Lp: Look, s: f32) -> vec4<f32> {
  let key = key_col(Lc);
  let tz = select(1e9, -ro.z / rd.z, rd.z < -1e-4 && ro.z > 0.0);
  let tw = select(1e9, (RT_WALL - ro.z) / rd.z, rd.z < -1e-4);
  let ty = select(1e9, (RT_FLOOR - ro.y) / rd.y, rd.y < -1e-4);
  var back = vec3<f32>(0.004);
  var tb = 1e9;
  if (ty < tw) {
    let hb = ro + rd * ty;
    back = bench(hb.xz * 0.7, key) * 0.5 + rub_wall(hb.x, RT_FLOOR, Lc, Lp, s) * 0.5;
    tb = ty;
  } else if (tw < 1e8) {
    let hw = ro + rd * tw;
    back = rub_wall(hw.x, hw.y, Lc, Lp, s);
    tb = tw;
  }
  if (tz < min(ty, tb) + 1e-3) {
    let hp = ro + rd * tz;
    let sol = rub_solid(hp.x, hp.y, rd, Lc, Lp, s);
    let fl = rub_flames(hp.x, hp.y, Lc, Lp, s);
    let main = select(tb, tz, sol.a > 0.5 || luma(fl) > 0.05);
    return vec4<f32>(mix(back, sol.rgb, sol.a) + fl, main);
  }
  return vec4<f32>(back, tb);
}
fn station_rubens(p: vec2<f32>) -> Px {
  let Lc = look_cur();
  let Lp = look_prev();
  let s = arrival();
  let key = key_col(Lc);
  let yaw = u.cam.x + 0.12 * sin(u.fx.w * 0.15);
  let pan = u.cam.w + 0.35 * sin(u.fx.w * 0.11 + Lc.seed * 6.0);
  let D = 3.6 / u.cam.z;
  let tgt = vec3<f32>(pan, 0.24, 0.0);
  let ro = tgt + vec3<f32>(D * sin(yaw), 0.10 * D / 3.6 - 0.02, D * cos(yaw));
  let fw = normalize(tgt - ro);
  let rt = normalize(cross(fw, vec3<f32>(0.0, 1.0, 0.0)));
  let up = cross(rt, fw);
  let rd = normalize(fw + (p.x * rt + p.y * up) * 0.36);
  var o: Px;
  let tz = select(1e9, -ro.z / rd.z, rd.z < -1e-4);
  let ty = select(1e9, (RT_FLOOR - ro.y) / rd.y, rd.y < -1e-4);
  if (ty < tz) {
    // the polished bench in front, mirroring the flames
    let hp = ro + rd * ty;
    let rr = vec3<f32>(rd.x, -rd.y, rd.z);
    let wob = vec3<f32>((vnoise(hp.xz * 7.0) - 0.5) * 0.03, 0.0, 0.0);
    let m = rub_view(hp + vec3<f32>(0.0, 1e-3, 0.0), normalize(rr + wob), Lc, Lp, s);
    o.col = bench(hp.xz * 0.7, key) * 0.6 + m.rgb * 0.24;
    o.coc = focus_coc(ty, D);
    o.fld = 0.0;
    return o;
  }
  let v = rub_view(ro, rd, Lc, Lp, s);
  o.col = v.rgb;
  o.coc = focus_coc(v.w, D);
  let hp = ro + rd * tz;
  o.fld = clamp(luma(rub_flames(hp.x, hp.y, Lc, Lp, s)) * 0.5, 0.0, 1.0);
  o.pred = select(0.0, clamp(rub_amp(hp.x, Lc) / 1.2, 0.0, 1.0), abs(hp.x) < RT_L && tz < 1e8);
  return o;
}

// ------------------------------------------------------------------ 4. Frozen streams
// m0 = (streams, helix, amplitude, phase seed). Water falls from nozzles through a speaker's vibration; a
// strobe at nearly the same frequency freezes it into a standing wave that slowly slips.
fn stm_k(L: Look) -> f32 { return TAU * clamp(L.hz * sweepmul() / 75.0, 0.6, 6.5); }
fn stm_backlight(x: f32, y: f32, Lc: Look) -> vec3<f32> {
  let acc = acc_col(Lc);
  let key = key_col(Lc);
  let box = sst(1.9, 1.3, abs(x)) * sst(1.3, 0.8, abs(y + 0.1));
  if (Lc.mat == 1) {
    return vec3<f32>(0.006) + acc * 0.02 * box;
  }
  if (Lc.mat == 2) {
    let gx = abs(fract(x * 9.0) - 0.5);
    let gy = abs(fract(y * 9.0) - 0.5);
    let grid = max(sst(0.06, 0.02, gx), sst(0.06, 0.02, gy));
    return (vec3<f32>(0.03) + mix(acc, key, 0.3) * (0.10 + 0.55 * grid)) * box;
  }
  let grad = mix(hsv(Lc.h1, 0.75, 1.0), acc / max(0.3 + 1.4 * u.aud.z * u.lay.w, 1e-3), sst(-1.0, 1.0, y));
  let spot = exp(-dot(vec2<f32>(x * 0.55, y + 0.1), vec2<f32>(x * 0.55, y + 0.1)) * 1.3);
  return grad * (0.02 + 0.55 * spot * box) * (0.75 + 0.3 * u.aud.z * u.lay.w);
}
struct Hit2 { d: f32, s: f32, z: f32, bead: f32 };
fn stm_one(x: f32, y: f32, xi: f32, i: f32, Lc: Look, Lp: Look, sa: f32, amp: f32, ch: f32) -> Hit2 {
  var o: Hit2;
  o.d = 1e9;
  if (y > 0.86) { return o; }
  let k = mix(select(stm_k(Lc), stm_k(Lp), Lp.st == 4), stm_k(Lc), sa);
  let ph = Lc.m0.w * TAU + i * 1.9 + u.fx.w * (0.5 + 0.25 * hash21(vec2<f32>(i, 5.0))) + 0.5 * PI * u.clk.y;
  let env = sst(0.86, 0.55, y);
  let a = amp * env * (0.8 + 0.4 * hash21(vec2<f32>(i, 6.0)));
  let arg = k * y + ph;
  let xc = xi + a * sin(arg);
  let zc = select(0.0, a * cos(arg), Lc.m0.y > 0.5);
  let slope = a * k * cos(arg);
  let r = 0.034 * (1.0 - 0.12 * (0.86 - y)) * (1.0 + 0.25 * zc / max(amp, 1e-3) * select(0.0, 1.0, Lc.m0.y > 0.5));
  // where the stream breaks into beads (sooner when the high mids agitate it, all of it in the overdrive)
  let yb = mix(-0.25 - 0.3 * hash21(vec2<f32>(i, 7.0)) + 0.25 * hmid(), 0.8, clamp(ch * 1.5, 0.0, 1.0));
  let lam0 = r * 4.6;
  let neck = 1.0 + 0.4 * sst(yb + 0.3, yb, y) * cos(TAU * (y - yb) / lam0);
  if (y > yb) {
    o.s = (x - xc) / sqrt(1.0 + slope * slope) / (r * neck);
    o.d = abs(o.s);
    o.z = zc;
    return o;
  }
  let lam = r * 4.6;
  let fr = fract(u.clk.x * 0.22 + hash21(vec2<f32>(i, 8.0)));
  let j = floor((yb - y) / lam - fr);
  let yc = yb - (j + fr + 0.5) * lam;
  let xb = xi + amp * sst(0.86, 0.55, yc) * sin(k * yc + ph) + ch * 0.25 * (hash21(vec2<f32>(i, j)) - 0.5);
  let rb = r * 1.35;
  let dv = vec2<f32>(x - xb, y - yc) / rb;
  o.d = length(dv);
  o.s = dv.x;
  o.z = dv.y;
  o.bead = 1.0;
  return o;
}
fn station_stream(p: vec2<f32>) -> Px {
  let Lc = look_cur();
  let Lp = look_prev();
  let sa = arrival();
  let key = key_col(Lc);
  let ch = chaos();
  let zoom = u.cam.z;
  let x = p.x / zoom + u.cam.w + 0.05 * sin(u.fx.w * 0.13);
  let y = p.y / zoom + 0.05;
  let nst = i32(Lc.m0.x + 0.5);
  let sp = min(3.0 / f32(nst), 0.62);
  let amp = 0.10 * Lc.m0.z * drive() * (0.25 + 0.85 * sub_l()) * (1.0 + 0.35 * kick());
  var col = stm_backlight(x, y, Lc);
  var o: Px;
  o.fld = 0.0;
  if (abs(y - 1.04) < 0.05) {
    let ny = (y - 1.04) / 0.05;
    col = vec3<f32>(0.55, 0.42, 0.22) * (0.08 + 0.7 * pow(max(1.0 - ny * ny, 0.0), 1.5) * (0.6 + 0.4 * ny)) * key;
  }
  for (var ii = 0; ii < 11; ii = ii + 1) {
    if (ii >= nst) { break; }
    let i = f32(ii);
    let xi = (i - 0.5 * f32(nst - 1)) * sp;
    // the nozzle and the manifold it hangs from
    if (abs(x - xi) < 0.03 && y > 0.86 && y < 1.0) {
      let nx = (x - xi) / 0.03;
      col = vec3<f32>(0.55, 0.42, 0.22) * (0.15 + 0.9 * pow(1.0 - nx * nx, 2.0)) * key;
    }
    let h = stm_one(x, y, xi, i, Lc, Lp, sa, amp, ch);
    if (h.d < 1.0) {
      var c = vec3<f32>(0.0);
      if (h.bead > 0.5) {
        // a droplet: a tiny ball lens, the backlight upside down inside it
        let nz = sqrt(max(1.0 - h.d * h.d, 0.0));
        let bgc = stm_backlight(x - h.s * 0.07, y - h.z * 0.07, Lc);
        c = bgc * (1.5 * nz * nz + 0.08) + key * pow(max(nz * 0.5 + 0.5 * (-h.s * 0.6 + h.z * 0.6), 0.0), 24.0) * 3.0;
      } else {
        // the stream: a glass rod, the backlight flipped across it, bright edges and a strobe highlight
        // a water rod in backlight: the light focused bright down its middle (upside down), dark edges where
        // it reflects the dark room, a thin strobe highlight
        let sx = clamp(h.s, -1.0, 1.0);
        let nz = sqrt(max(1.0 - sx * sx, 0.0));
        let bgc = stm_backlight(x - sx * 0.07, y, Lc);
        c = bgc * (1.45 * pow(nz, 1.5) + 0.06) + key * exp(-pow((sx + 0.5) / 0.09, 2.0)) * 1.6;
        c = c + mix(key, acc_col(Lc), 0.5) * exp(-pow((sx - 0.88) / 0.06, 2.0)) * 0.35;
        c = c * (0.85 + 0.3 * h.z / max(amp + 1e-3, 1e-3) * select(0.0, 1.0, Lc.m0.y > 0.5));
        c = c + key * select(0.0, 2.5, hash21(vec2<f32>(floor(y * 90.0), i + floor(u.clk.x * 12.0))) < 0.06 * high()) * exp(-pow((sx + 0.45) / 0.1, 2.0));
      }
      let a = sst(1.0, 0.85, h.d);
      col = mix(col, c, a);
      o.fld = max(o.fld, a);
    }
  }
  o.col = col;
  o.coc = 0.0;
  return o;
}

// ------------------------------------------------------------------ 5. Laser Lissajous figures
// m0 = (a1, b1, a2, b2), m1 = (a3, b3, 3D, phase). Each laser bounces off a mirror on a vibrating membrane:
// its ratio against the root draws the chord on the wall.
fn lis_ratio(L: Look, j: i32) -> vec2<f32> {
  if (j == 0) { return L.m0.xy; }
  if (j == 1) { return L.m0.zw; }
  return L.m1.xy;
}
fn lis_xy(s: f32, a: f32, b: f32, dl: f32, A: f32, B: f32, psi: f32, c3: f32) -> vec2<f32> {
  return vec2<f32>(A * (cos(psi) * sin(a * s + dl) + sin(psi) * sin(c3 * s + 0.7)), B * sin(b * s));
}
fn lis_d1(s: f32, a: f32, b: f32, dl: f32, A: f32, B: f32, psi: f32, c3: f32) -> vec2<f32> {
  return vec2<f32>(A * (cos(psi) * a * cos(a * s + dl) + sin(psi) * c3 * cos(c3 * s + 0.7)), B * b * cos(b * s));
}
fn lis_d2(s: f32, a: f32, b: f32, dl: f32, A: f32, B: f32, psi: f32, c3: f32) -> vec2<f32> {
  return -vec2<f32>(A * (cos(psi) * a * a * sin(a * s + dl) + sin(psi) * c3 * c3 * sin(c3 * s + 0.7)), B * b * b * sin(b * s));
}
// Newton steps toward the nearest point of the curve from a starting parameter
fn lis_refine(P: vec2<f32>, s0: f32, a: f32, b: f32, dl: f32, A: f32, B: f32, psi: f32, c3: f32) -> vec2<f32> {
  var s = s0;
  let lim = 0.3 / max(max(a, b), 1.0);
  for (var it = 0; it < 3; it = it + 1) {
    let e = lis_xy(s, a, b, dl, A, B, psi, c3) - P;
    let d1 = lis_d1(s, a, b, dl, A, B, psi, c3);
    let d2 = lis_d2(s, a, b, dl, A, B, psi, c3);
    let g = dot(e, d1);
    let h = dot(d1, d1) + dot(e, d2);
    s = s - clamp(g / select(dot(d1, d1) + 1e-6, h, h > 1e-6), -lim, lim);
  }
  return vec2<f32>(length(lis_xy(s, a, b, dl, A, B, psi, c3) - P), s);
}
// distance to the figure: the curve crosses the pixel's row (and, in 2D, its column) at known parameters;
// the closest crossings are refined to the true nearest point
fn lis_dist(P: vec2<f32>, a: f32, b: f32, dl: f32, A: f32, B: f32, psi: f32, c3: f32) -> vec2<f32> {
  var bu = 1e9;
  var su = 0.0;
  var bl = 1e9;
  var sl = 0.0;
  let ys = asin(clamp(P.y / B, -1.0, 1.0));
  let nb = i32(ceil(b));
  for (var k = 0; k < nb; k = k + 1) {
    for (var r = 0; r < 2; r = r + 1) {
      let s = (select(PI - ys, ys, r == 0) + TAU * f32(k)) / b;
      let c = lis_xy(s, a, b, dl, A, B, psi, c3);
      let t = lis_d1(s, a, b, dl, A, B, psi, c3);
      let du = length(P - c);
      let dlin = abs((P - c).x * t.y - (P - c).y * t.x) / max(length(t), 1e-4);
      if (du < bu) { bu = du; su = s; }
      if (dlin < bl) { bl = dlin; sl = s; }
    }
  }
  if (psi == 0.0) {
    let xs = asin(clamp(P.x / A, -1.0, 1.0));
    let na = i32(ceil(a));
    for (var k = 0; k < na; k = k + 1) {
      for (var r = 0; r < 2; r = r + 1) {
        let s = (select(PI - xs, xs, r == 0) - dl + TAU * f32(k)) / a;
        let c = lis_xy(s, a, b, dl, A, B, 0.0, c3);
        let du = length(P - c);
        if (du < bu) { bu = du; su = s; }
      }
    }
  }
  let r1 = lis_refine(P, su, a, b, dl, A, B, psi, c3);
  let r2 = lis_refine(P, sl, a, b, dl, A, B, psi, c3);
  if (r2.x < r1.x) { return r2; }
  return r1;
}
fn seg_dist(p: vec2<f32>, a: vec2<f32>, b: vec2<f32>) -> f32 {
  let pa = p - a;
  let ba = b - a;
  let h = clamp(dot(pa, ba) / dot(ba, ba), 0.0, 1.0);
  return length(pa - ba * h);
}
fn station_lissajous(p: vec2<f32>, fc: vec2<f32>) -> Px {
  let Lc = look_cur();
  let Lp = look_prev();
  let sa = arrival();
  let ch = chaos();
  let key = key_col(Lc);
  let P = rot(u.cam.y * 0.3) * p / u.cam.z;
  let g = drive();
  let size = (0.40 + 0.30 * g) * (0.82 + 0.22 * sub_l()) * (1.0 + 0.07 * kick()) * (1.0 + 0.25 * ch);
  let A = size * 1.15;
  let B = size * 0.95;
  var lcol = array<vec3<f32>, 3>(vec3<f32>(1.0, 0.06, 0.04), vec3<f32>(0.06, 1.0, 0.16), vec3<f32>(0.12, 0.30, 1.0));
  if (Lc.mat == 1) {
    // three green traces carry three times the luminance of one: dimmer, so the scope stays under the flash limits
    lcol = array<vec3<f32>, 3>(vec3<f32>(0.14, 0.55, 0.19), vec3<f32>(0.06, 0.47, 0.17), vec3<f32>(0.25, 0.55, 0.30));
  } else if (Lc.mat == 2) {
    lcol = array<vec3<f32>, 3>(vec3<f32>(1.0, 0.45, 0.04), vec3<f32>(1.0, 0.06, 0.10), vec3<f32>(0.95, 0.10, 0.65));
  }
  let three = select(0.0, 1.0, Lc.m1.z > 0.5) + clamp(ch * 2.0, 0.0, 1.0);
  let psi = select(0.0, u.fx.w * 0.4 + ch * 2.0, three > 0.0);
  let speck = 0.55 + 0.9 * hash21(floor(fc / 1.5));
  var col = vec3<f32>(0.0);
  var fan = vec3<f32>(0.0);
  var fld = 0.0;
  let src = vec2<f32>(0.0, -1.35);
  for (var j = 0; j < 3; j = j + 1) {
    var ab = lis_ratio(Lc, j);
    if (sa < 0.999 && Lp.st == 5) { ab = mix(lis_ratio(Lp, j), ab, sa); }
    let dl = u.fx.w * (0.35 + 0.17 * f32(j)) + Lc.m1.w * TAU + f32(j) * 1.3;
    let c3 = ab.x + 1.0;
    let hit = lis_dist(P, ab.x, ab.y, dl, A, B, psi, c3);
    let d = hit.x;
    let head = u.clk.x * (1.1 + 0.2 * f32(j)) * TAU;
    let dh = abs(wrapang(hit.y * max(ab.y, 1.0) - head)) / max(ab.y, 1.0);
    let bright = (0.9 + 0.35 * exp(-dh / 0.5)) * (0.92 + 0.12 * kick()) * g;
    let core = exp(-pow(d / (0.0026 + 0.0015 * u.aud.z * u.lay.w), 2.0)) * 2.4;
    let halo = exp(-d / 0.018) * (0.18 + 0.4 * u.aud.z * u.lay.w) + exp(-d / 0.12) * 0.03;
    col = col + lcol[j] * (core * speck + halo) * bright;
    fld = max(fld, core / 2.4);
    // the beam fanning through the haze from the projector below
    for (var k = 0; k < 10; k = k + 1) {
      let s = (f32(k) + fract(u.clk.x * 0.9)) / 10.0 * TAU / max(ab.y, 1.0) * ceil(ab.y);
      let c = lis_xy(s, ab.x, ab.y, dl, A, B, psi, c3);
      let ds = seg_dist(P, src, c);
      let along = clamp((P.y - src.y) / (c.y - src.y), 0.0, 1.0);
      fan = fan + lcol[j] * exp(-pow(ds / 0.004, 2.0)) * (0.012 + 0.03 * high()) * along * g;
    }
  }
  // the wall: rough plaster, lit by the lasers' glow
  let wall = (0.010 + 0.012 * fbm(P * 5.0, 3)) * key;
  col = wall * (1.0 + 2.0 * luma(col)) + col + fan;
  let haze = hash21(floor(fc / 3.0) + vec2<f32>(floor(u.clk.x * 15.0), 0.0));
  col = col + luma(fan) * select(0.0, 3.0, haze < 0.04 * high()) * key;
  var o: Px;
  o.col = col;
  o.coc = 0.0;
  o.fld = fld;
  return o;
}

@fragment
fn fs_scene(i: FOut) -> @location(0) vec4<f32> {
  let fc = i.pos.xy;
  let p = vec2<f32>(fc.x - 0.5 * u.res.x, 0.5 * u.res.y - fc.y) * u.res.z;
  let st = i32(u.b0.x + 0.5);
  var px: Px;
  px.col = vec3<f32>(0.0);
  px.coc = 0.0;
  px.fld = 0.0;
  if (st == 0) { px = station_chladni(p); }
  else if (st == 1) { px = station_faraday(p); }
  else if (st == 2) { px = station_ferro(p); }
  else if (st == 3) { px = station_rubens(p); }
  else if (st == 4) { px = station_stream(p); }
  else if (st == 5) { px = station_lissajous(p, fc); }
  let dm = i32(u.dbg.x + 0.5);
  if (dm == 1 || dm == 2) {
    return vec4<f32>(clamp(select(px.fld, px.pred, dm == 2), 0.0, 1.0), (f32(st) * 16.0 + 8.0) / 255.0, px.coc, 1.0);
  }
  return vec4<f32>(max(px.col, vec3<f32>(0.0)), clamp(max(px.coc, u.mixv.z), 0.0, 1.0));
}
"""

POST = COMMON + r"""
@group(1) @binding(0) var src: texture_2d<f32>;
@group(1) @binding(1) var blur: texture_2d<f32>;
@group(1) @binding(2) var fin: texture_2d<f32>;
struct Dir { v: vec4<f32> };
@group(1) @binding(3) var<uniform> D: Dir;
@group(0) @binding(1) var smp: sampler;

@fragment
fn fs_down(i: FOut) -> @location(0) vec4<f32> {
  // a quarter-size copy (4x4 average through four bilinear taps)
  let px = D.v.xy;
  var c = vec4<f32>(0.0);
  c = c + textureSampleLevel(src, smp, i.uv + vec2<f32>(-px.x, -px.y), 0.0);
  c = c + textureSampleLevel(src, smp, i.uv + vec2<f32>(px.x, -px.y), 0.0);
  c = c + textureSampleLevel(src, smp, i.uv + vec2<f32>(-px.x, px.y), 0.0);
  c = c + textureSampleLevel(src, smp, i.uv + vec2<f32>(px.x, px.y), 0.0);
  return c * 0.25;
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
  if (i32(u.dbg.x + 0.5) == 1 || i32(u.dbg.x + 0.5) == 2) {
    return textureLoad(src, vec2<i32>(i.pos.xy), 0);
  }
  let uv = i.uv;
  let ctr = uv - 0.5;
  let rpx = length(vec2<f32>(ctr.x * u.res.w, ctr.y));
  let ca = u.post.y * ctr * rpx * 0.012;
  let s0 = textureSampleLevel(src, smp, uv, 0.0);
  var c = vec3<f32>(textureSampleLevel(src, smp, uv + ca, 0.0).r, s0.g, textureSampleLevel(src, smp, uv - ca, 0.0).b);
  let bl = textureSampleLevel(blur, smp, uv, 0.0);
  // depth of field and the rack focus: blend toward the blurred copy by the circle of confusion
  let m = sst(0.0, 1.0, max(s0.a, bl.a * 0.85));
  c = mix(c, bl.rgb, m);
  c = c + bl.rgb * sst(0.5, 2.0, luma(bl.rgb)) * u.post.w;
  c = c * u.post.x;
  c = aces(c);
  c = pow(c, vec3<f32>(1.0 / 2.2));
  let l = luma(c);
  c = clamp(mix(vec3<f32>(l), c, u.dbg.w), vec3<f32>(0.0), vec3<f32>(1.0));
  // the kick lifts the shadows and mid-tones, not the highlights: it reads in a dark lab (and survives the
  // encoder, which drops small changes in dark frames) while staying far under the photosensitive limits
  c = c * (1.0 + u.ext.x * (1.0 - sst(0.2, 0.6, luma(c))));
  let v = 1.0 - u.post.z * pow(rpx / (0.5 * u.res.w) * 0.95, 2.4);
  c = c * clamp(v, 0.0, 1.0) * (1.0 - u.dbg.z);
  return vec4<f32>(c, 1.0);
}

// BT.709 limited range, dithered so the dark gradients don't band
fn dith(p: vec2<f32>) -> f32 {
  return hash21(p + vec2<f32>(u.clk.w * 0.618, u.clk.w * 0.382)) + hash21(p * 1.37 + 11.0 + u.clk.w * 0.1) - 1.0;
}

@fragment
fn fs_y(i: FOut) -> @location(0) vec4<f32> {
  let c = textureLoad(fin, vec2<i32>(i.pos.xy), 0).rgb;
  let dz = select(1.0, 0.0, i32(u.dbg.x + 0.5) == 1);
  let y = (16.0 + 219.0 * dot(c, vec3<f32>(0.2126, 0.7152, 0.0722)) + 0.5 * dith(i.pos.xy) * dz) / 255.0;
  return vec4<f32>(y, 0.0, 0.0, 1.0);
}

@fragment
fn fs_uv(i: FOut) -> @location(0) vec4<f32> {
  let b = vec2<i32>(i.pos.xy) * 2;
  let c = (textureLoad(fin, b, 0).rgb + textureLoad(fin, b + vec2<i32>(1, 0), 0).rgb
         + textureLoad(fin, b + vec2<i32>(0, 1), 0).rgb + textureLoad(fin, b + vec2<i32>(1, 1), 0).rgb) * 0.25;
  let y = dot(c, vec3<f32>(0.2126, 0.7152, 0.0722));
  let dz = select(1.0, 0.0, i32(u.dbg.x + 0.5) == 1);
  let cb = (128.0 + 224.0 * (c.b - y) / 1.8556 + 0.5 * dith(i.pos.xy + 3.3) * dz) / 255.0;
  let cr = (128.0 + 224.0 * (c.r - y) / 1.5748 + 0.5 * dith(i.pos.xy + 7.7) * dz) / 255.0;
  return vec4<f32>(cb, cr, 0.0, 1.0);
}

@fragment
fn fs_rgba(i: FOut) -> @location(0) vec4<f32> {
  let c = textureLoad(fin, vec2<i32>(i.pos.xy), 0);
  return vec4<f32>(c.rgb, select(1.0, c.a, i32(u.dbg.x + 0.5) == 1 || i32(u.dbg.x + 0.5) == 2));
}
"""
