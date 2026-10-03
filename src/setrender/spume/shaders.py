"""WGSL for spume. One full-screen fragment shader draws every pixel from scratch: a "look" (a motif
of nested bubbles, a kaleidoscope, a palette) maps the pixel to a bubble at some depth of the recursion,
and the bubble is shaded as a lens into one of eight elements under a soap film whose colour comes from
the thin-film table (film.py). During a transition two looks are drawn and mixed. A bloom chain, a post
pass (exposure pump, chromatic aberration, grade, vignette) and a BT.709 NV12 conversion follow.

Coordinates: p has y up, 1 unit = half the screen height, origin at the centre. All motion is a pure
function of the uniforms, which the Python side computes from the planned set for each frame index.
"""

COMMON = r"""
struct U {
  res: vec4<f32>,     // w, h, pixel size in p units, aspect
  clk: vec4<f32>,     // t (s), beat position, bar position, frame index
  aud: vec4<f32>,     // kick, sub, bass, lowmid
  aud2: vec4<f32>,    // highmid, high, loudness, calm (0..1)
  a0: vec4<f32>,      // look A: motif, zoom, camera angle, seed
  a1: vec4<f32>,      //   folds (0 = no kaleidoscope), twist, density, element offset
  a2: vec4<f32>,      //   film base nm, film swing nm, swirl phase, hue shift
  a3: vec4<f32>,      //   motif parameters
  b0: vec4<f32>,      // look B (same layout)
  b1: vec4<f32>,
  b2: vec4<f32>,
  b3: vec4<f32>,
  mixv: vec4<f32>,    // blend 0..1, kind (0 dissolve, 1 bubble iris, 2 pop, 3 ripple), centre x, y
  fx: vec4<f32>,      // pop age (s), pop strength, surge element, surge strength
  light: vec4<f32>,   // light colour (key on the circle of fifths), saturation
  post: vec4<f32>,    // exposure, chromatic aberration, vignette, bloom
  dbg: vec4<f32>,     // debug mode, -, fade to black (0..1), film strength
  lay: vec4<f32>,     // layer gains: film, border, interior, sparkle (isolation renders set them)
  pal0: vec4<f32>,    // per-element hue shifts
  pal1: vec4<f32>,
  ext: vec4<f32>,     // build (0..1), forced element (-1 = none), kick punch, -
};
@group(0) @binding(0) var<uniform> u: U;
@group(0) @binding(1) var lut: texture_2d<f32>;
@group(0) @binding(2) var smp: sampler;

const PI: f32 = 3.14159265;
const TAU: f32 = 6.28318531;
const MAX_NM: f32 = 1600.0;

// hashes of the exact bits of their inputs (PCG), so they stay good however far the dive has gone
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
fn wrap64(x: f32) -> f32 { return x - 64.0 * floor(x / 64.0); }
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
// fbm with as many octaves as the pixel size allows (no shimmer when a pattern gets small)
fn fbm(p: vec2<f32>, pix: f32, maxo: i32) -> f32 {
  var s = 0.0;
  var a = 0.5;
  var q = p;
  var f = 1.0;
  for (var k = 0; k < maxo; k = k + 1) {
    let fade = clamp(1.5 - f * pix * 6.0, 0.0, 1.0);
    if (fade <= 0.0) { s = s + a * 0.5; } else { s = s + a * mix(0.5, vnoise(q), fade); }
    q = mat2x2<f32>(vec2<f32>(1.6, 1.2), vec2<f32>(-1.2, 1.6)) * q + vec2<f32>(3.1, 1.7);
    a = a * 0.5;
    f = f * 2.0;
  }
  return s;
}
fn rot(a: f32) -> mat2x2<f32> {
  let c = cos(a);
  let s = sin(a);
  return mat2x2<f32>(vec2<f32>(c, s), vec2<f32>(-s, c));
}
fn luma(c: vec3<f32>) -> f32 { return dot(c, vec3<f32>(0.2126, 0.7152, 0.0722)); }
fn hue(c: vec3<f32>, h: f32) -> vec3<f32> {
  // rotate hue in YIQ (keeps brightness)
  let y = dot(c, vec3<f32>(0.299, 0.587, 0.114));
  let i = dot(c, vec3<f32>(0.596, -0.274, -0.322));
  let q = dot(c, vec3<f32>(0.211, -0.523, 0.312));
  let a = h * TAU;
  let i2 = i * cos(a) - q * sin(a);
  let q2 = i * sin(a) + q * cos(a);
  return max(vec3<f32>(y + 0.956 * i2 + 0.621 * q2, y - 0.272 * i2 - 0.647 * q2, y - 1.106 * i2 + 1.703 * q2), vec3<f32>(0.0));
}
fn pal(a: vec3<f32>, b: vec3<f32>, c: vec3<f32>, d: vec3<f32>, t: f32) -> vec3<f32> {
  return a + b * cos(TAU * (c * t + d));
}
fn imod(a: i32, m: i32) -> i32 { return ((a % m) + m) % m; }
fn cmul(a: vec2<f32>, b: vec2<f32>) -> vec2<f32> { return vec2<f32>(a.x * b.x - a.y * b.y, a.x * b.y + a.y * b.x); }
fn cdiv(a: vec2<f32>, b: vec2<f32>) -> vec2<f32> { return vec2<f32>(a.x * b.x + a.y * b.y, a.y * b.x - a.x * b.y) / max(dot(b, b), 1e-12); }
fn conj(a: vec2<f32>) -> vec2<f32> { return vec2<f32>(a.x, -a.y); }
fn film_rgb(nm: f32, row: f32) -> vec3<f32> {
  return textureSampleLevel(lut, smp, vec2<f32>(clamp(nm / MAX_NM, 0.0, 1.0), row * 0.5 + 0.25), 0.0).rgb;
}
"""

SCENE = COMMON + r"""
struct Look {
  motif: i32,
  zoom: f32,
  cam: f32,
  seed: f32,
  folds: f32,
  twist: f32,
  density: f32,
  eoff: f32,
  fbase: f32,
  fswing: f32,
  swirl: f32,
  hue: f32,
  m: vec4<f32>,
};

struct Cell {
  local: vec2<f32>,   // inside the bubble: 0 at its centre, length 1 at its wall
  edge: f32,          // distance to the wall, screen units
  size: f32,          // bubble radius, screen units
  id: f32,            // 0..1 hash of the bubble
  elem: i32,          // element 0..7 (fire, water, earth, air, metal, ice, lightning, magma)
  depth: i32,         // level of the recursion this bubble sits at
  wall: f32,          // 1 for walls that are boundaries between levels (drawn thicker)
  fid: f32,           // which foam the bubble belongs to (a hash of its path down the recursion)
};

fn look_a() -> Look {
  return Look(i32(u.a0.x + 0.5), u.a0.y, u.a0.z, u.a0.w, u.a1.x, u.a1.y, u.a1.z, u.a1.w,
              u.a2.x, u.a2.y, u.a2.z, u.a2.w, u.a3);
}
fn look_b() -> Look {
  return Look(i32(u.b0.x + 0.5), u.b0.y, u.b0.z, u.b0.w, u.b1.x, u.b1.y, u.b1.z, u.b1.w,
              u.b2.x, u.b2.y, u.b2.z, u.b2.w, u.b3);
}

fn elem_of(i: i32, j: i32, L: Look) -> i32 {
  // neighbours on the grid (dx, dy in -2..2, not (2, 2)) always differ: dx + 3 dy is never 0 mod 8
  return imod(i + 3 * j + i32(L.eoff), 8);
}

// ------------------------------------------------------------------ motif 0: lather (power-diagram foam, dive)
// One level of foam: a jittered grid of seeds with weights (a power diagram gives bubbles of many sizes),
// the walls' corners rounded by a smooth minimum so cells read as bubbles pressed together.
fn foam_level(q: vec2<f32>, g: f32, lev: f32, L: Look, hole: f32, outer: f32) -> Cell {
  var c: Cell;
  let gi = floor(q / g);
  var best = 1e9;
  var bp = vec2<f32>(0.0);
  var bw = 0.0;
  var bij = vec2<i32>(0);
  let surge_e = i32(u.fx.z + 0.5);
  for (var j = -2; j <= 2; j = j + 1) {
    for (var i = -2; i <= 2; i = i + 1) {
      let cell = gi + vec2<f32>(f32(i), f32(j));
      let h = hash22(cell + vec2<f32>(lev * 17.3 + L.seed, lev * 5.1));
      let s = (cell + 0.5 + (h - 0.5) * 0.72) * g;
      let ci = vec2<i32>(i32(cell.x), i32(cell.y));
      let e = elem_of(ci.x, ci.y, L);
      var w = (hash21(cell + vec2<f32>(lev * 3.7, 9.1 + L.seed)) - 0.5) * 0.30 * g * g;
      if (e == surge_e) { w = w + u.fx.w * 0.22 * g * g; }
      let d = dot(q - s, q - s) - w;
      if (d < best) { best = d; bp = s; bw = w; bij = ci; }
    }
  }
  // distance to the walls: radical lines to every neighbour, smooth-min for rounded corners
  var ed = 1e9;
  let k = 0.10 * g;
  var acc = 0.0;
  for (var j = -2; j <= 2; j = j + 1) {
    for (var i = -2; i <= 2; i = i + 1) {
      let cell = vec2<f32>(f32(bij.x + i), f32(bij.y + j));
      if (i == 0 && j == 0) { continue; }
      let h = hash22(cell + vec2<f32>(lev * 17.3 + L.seed, lev * 5.1));
      let s = (cell + 0.5 + (h - 0.5) * 0.72) * g;
      let ci = vec2<i32>(i32(cell.x), i32(cell.y));
      let e = elem_of(ci.x, ci.y, L);
      var w = (hash21(cell + vec2<f32>(lev * 3.7, 9.1 + L.seed)) - 0.5) * 0.30 * g * g;
      if (e == surge_e) { w = w + u.fx.w * 0.22 * g * g; }
      let ab = s - bp;
      let lab = length(ab);
      let dd = ((dot(q - s, q - s) - w) - (dot(q - bp, q - bp) - bw)) / (2.0 * lab);
      acc = acc + exp(-dd / k);
    }
  }
  ed = -k * log(max(acc, 1e-30));
  if (hole > 0.0) { ed = min(ed, length(q) - hole); }
  if (outer > 0.0) { ed = min(ed, outer - length(q)); }
  let v = q - bp;
  c.local = v / max(length(v) + max(ed, 0.0), 1e-5);
  c.edge = ed;
  c.size = length(v) + max(ed, 0.0);
  c.id = hash21(vec2<f32>(f32(bij.x), f32(bij.y)) + lev * 7.77);
  c.elem = elem_of(bij.x, bij.y, L);
  c.wall = 0.0;
  if (hole > 0.0 && length(q) - hole < ed + 1e-4) { c.wall = 1.0; }
  if (outer > 0.0 && outer - length(q) < ed + 1e-4) { c.wall = 1.0; }
  return c;
}

fn motif_lather(p: vec2<f32>, L: Look) -> Cell {
  let K = L.m.x;            // each level sits inside the previous level's central bubble, K times smaller
  let Rc = 2.22 / K;        // the central bubble is just big enough to fill the screen one level later
  let n = floor(L.zoom);
  let f = L.zoom - n;
  var sc = pow(K, -f);      // level units per screen unit
  var q = p * sc;
  var c: Cell;
  var lev = 0;
  loop {
    let outer = select(0.0, Rc * K, lev > 0);
    if (length(q) < Rc && lev < 4) {
      q = q * K;
      sc = sc * K;
      lev = lev + 1;
      continue;
    }
    let hole = select(Rc, 0.0, lev >= 4);
    c = foam_level(q, L.density, wrap64(n + f32(lev)), L, hole, outer);
    break;
  }
  c.edge = c.edge / sc;
  c.size = c.size / sc;
  c.depth = lev;
  return c;
}

// ------------------------------------------------------------------ motif 1: steiner (rotating chains of bubbles)
fn mobius(z: vec2<f32>, a: vec2<f32>) -> vec2<f32> {
  return cdiv(z - a, vec2<f32>(1.0, 0.0) - cmul(conj(a), z));
}
fn motif_steiner(p: vec2<f32>, L: Look) -> Cell {
  let R0 = 2.12;
  var z = p / R0;
  var sc = 1.0 / R0;
  let nn = max(L.m.x, 3.0);
  let s = sin(PI / nn);
  let ri = (1.0 - s) / (1.0 + s);
  let rho = (1.0 - ri) * 0.5;
  let rm = (1.0 + ri) * 0.5;
  var c: Cell;
  var lev = 0;
  var stride = 0;
  var fid = 0.0;
  loop {
    // a different eccentricity at each level (circles stay tangent under a disk automorphism)
    let ph = L.seed * 3.1 + f32(lev) * 2.4 + L.m.z;
    let a = L.m.y * vec2<f32>(cos(ph), sin(ph)) * select(1.0, 0.6, lev == 0);
    let den = vec2<f32>(1.0, 0.0) - cmul(conj(a), z);
    let w = mobius(z, a);
    sc = sc * (1.0 - dot(a, a)) / max(dot(den, den), 1e-9);
    let r = length(w);
    let dir = select(1.0, -1.0, (lev % 2) == 1);
    let crot = dir * L.zoom * TAU / nn + f32(lev) * 0.7;
    if (r < ri && lev < 5) {
      z = rot(-crot * 0.5) * (w / ri);
      sc = sc / ri;
      lev = lev + 1;
      stride = stride + 3;
      fid = fract(fid * 7.13 + 0.17);
      continue;
    }
    let ang = atan2(w.y, w.x) - crot;
    let k = round(ang / (TAU / nn));
    let ca = k * TAU / nn + crot;
    let cc = rm * vec2<f32>(cos(ca), sin(ca));
    let d = length(w - cc);
    let ki = imod(i32(k), i32(nn + 0.5));
    let m = select(2, 3, (i32(nn + 0.5) % 3) == 0 && (i32(nn + 0.5) % 2) != 0);
    let el = imod(i32(L.eoff) + stride + ki % m, 8);
    if (d < rho) {
      if (ki % 3 == 0 && lev < 4 && i32(nn + 0.5) % 3 == 0) {
        // this bubble holds a chain of its own
        z = rot(crot) * ((w - cc) / rho);
        sc = sc / rho;
        lev = lev + 1;
        stride = stride + 3;
        fid = fract(fid * 7.13 + f32(ki + 1) * 0.618 + 0.17);
        continue;
      }
      c.local = (w - cc) / rho;
      c.edge = (rho - d) / sc;
      c.size = rho / sc;
      c.id = fract(f32(ki) * 0.618 + f32(lev) * 0.31 + L.seed);
      c.elem = el;
      c.depth = lev;
      c.wall = 0.0;
      c.fid = fid;
      return c;
    }
    // the space between the chain, the inner bubble and the outer wall
    let e1 = d - rho;
    let e2 = r - ri;
    let e3 = 1.0 - r;
    c.edge = min(e1, min(e2, e3)) / sc;
    c.local = w * 0.85;
    c.size = 1.0 / sc;
    c.id = fract(f32(lev) * 0.37 + L.seed);
    // one step past this level's chain elements, so the gaps never match a bubble beside them
    c.elem = imod(i32(L.eoff) + stride + m, 8);
    c.depth = lev;
    c.wall = select(0.0, 1.0, e2 < e1 || e3 < e1);
    c.fid = fid;
    return c;
  }
  return c;
}

// ------------------------------------------------------------------ motif 2: hyperbolic foam ({p,q} in the Poincare disk)
fn motif_hyper(p0: vec2<f32>, L: Look) -> Cell {
  let P = L.m.x;
  let Q = L.m.y;
  let D = 1.04;                  // disk radius on screen; outside it the tiling is mirrored (inverted)
  var z = p0 / D;
  var sc = 1.0 / D;
  let rr = dot(z, z);
  var outside = false;
  if (rr > 1.0) {
    z = z / rr;
    sc = sc / rr;
    outside = true;
  }
  let a = PI / P;
  let b = PI / Q;
  let rc = sin(a) / sqrt(cos(b) * cos(b) - sin(a) * sin(a));
  let dc = sqrt(1.0 + rc * rc);
  // the dive: a hyperbolic translation by two cell widths maps the tiling (and its colouring) to itself
  let de = 2.0 * atanh(dc - rc);
  let tr = tanh(fract(L.zoom * 0.5) * 4.0 * de * 0.5);
  z = rot(L.cam * 0.5 + L.m.z) * z;
  let den = vec2<f32>(1.0, 0.0) + tr * z;
  let w0 = cdiv(z + vec2<f32>(tr, 0.0), den);
  sc = sc * (1.0 - tr * tr) / max(dot(den, den), 1e-9);
  z = w0;
  var par = 0;
  var gen = 0;
  for (var it = 0; it < 40; it = it + 1) {
    let ang = atan2(z.y, z.x);
    let k = round(ang / (2.0 * a));
    z = rot(-k * 2.0 * a) * z;
    z.y = abs(z.y);
    let v = z - vec2<f32>(dc, 0.0);
    let l2 = dot(v, v);
    if (l2 < rc * rc) {
      z = vec2<f32>(dc, 0.0) + v * (rc * rc / l2);
      sc = sc * rc * rc / l2;
      par = 1 - par;
      gen = gen + 1;
    } else {
      break;
    }
  }
  var c: Cell;
  let rin = dc - rc;
  c.local = z / rin * 0.92;
  c.edge = (length(z - vec2<f32>(dc, 0.0)) - rc) / sc;
  c.size = rin / sc;
  c.id = fract(f32(gen) * 0.137 + f32(par) * 0.5 + L.seed);
  c.elem = imod(i32(L.eoff) + select(0, 3, par == 1), 8);
  c.depth = gen;
  c.wall = 0.0;
  if (outside) { c.depth = gen + 1; }
  return c;
}

// ------------------------------------------------------------------ motif 3: droste (a spiral of bubbles into itself)
fn motif_droste(p: vec2<f32>, L: Look) -> Cell {
  let N = L.m.x;                 // bubbles around one turn
  let tw = L.m.y;                // ring shift per turn (the spiral)
  let h = TAU / N;               // cell size in log-polar space (square cells: bubbles stay round)
  let lr = log(max(length(p), 1e-6));
  let th = atan2(p.y, p.x) + L.cam * 0.0;
  // sheared lattice: going once round climbs tw rows
  let uu = lr - tw * h * (th / TAU) - L.zoom * h;
  let vv = th;
  let q = vec2<f32>(uu, vv) / h;
  let gi = floor(q);
  var best = 1e9;
  var bs = vec2<f32>(0.0);
  var bij = vec2<f32>(0.0);
  for (var j = -1; j <= 1; j = j + 1) {
    for (var i = -1; i <= 1; i = i + 1) {
      let cell = gi + vec2<f32>(f32(i), f32(j));
      // canonical cell: one turn round is tw rows along
      let wraps = floor(cell.y / N);
      let can = vec2<f32>(cell.x + wraps * tw, cell.y - wraps * N);
      let hh = hash22(vec2<f32>(wrap64(can.x), can.y) + vec2<f32>(L.seed * 3.3, 1.7));
      let s = cell + 0.5 + (hh - 0.5) * 0.55;
      let d = dot(q - s, q - s);
      if (d < best) { best = d; bs = s; bij = cell; }
    }
  }
  var acc = 0.0;
  let k = 0.07;
  for (var j = -1; j <= 1; j = j + 1) {
    for (var i = -1; i <= 1; i = i + 1) {
      if (i == 0 && j == 0) { continue; }
      let cell = bij + vec2<f32>(f32(i), f32(j));
      let wraps = floor(cell.y / N);
      let can = vec2<f32>(cell.x + wraps * tw, cell.y - wraps * N);
      let hh = hash22(vec2<f32>(wrap64(can.x), can.y) + vec2<f32>(L.seed * 3.3, 1.7));
      let s = cell + 0.5 + (hh - 0.5) * 0.55;
      let dd = (dot(q - s, q - s) - dot(q - bs, q - bs)) / (2.0 * length(s - bs));
      acc = acc + exp(-dd / k);
    }
  }
  let ed = -k * log(max(acc, 1e-30));
  let wraps = floor(bij.y / N);
  let can = vec2<f32>(bij.x + wraps * tw, bij.y - wraps * N);
  let r = length(p);
  var c: Cell;
  let v = q - bs;
  // log-polar is conformal: a step in (u, v) is r * h on screen, and the local frame turns with the angle
  c.local = rot(th) * vec2<f32>(v.x, v.y) / max(length(v) + max(ed, 0.0), 1e-5);
  c.edge = ed * h * r;
  c.size = (length(v) + max(ed, 0.0)) * h * r;
  c.id = hash21(vec2<f32>(wrap64(can.x), can.y) + 0.5);
  c.elem = imod(i32(wrap64(can.x)) + 3 * i32(can.y) + i32(L.eoff), 8);
  // depth: rings counted inwards from the screen's corner
  c.depth = i32(max(0.0, floor((log(2.05) - lr) / (h * max(tw, 1.0)))));
  c.wall = 0.0;
  return c;
}

// ------------------------------------------------------------------ motif 4: raft (a hexagonal bubble raft, rafts inside)
fn hex_cell(q: vec2<f32>) -> vec4<f32> {
  // nearest hex centre (axial i, j) and the offset from it, flat-topped hexes of circumradius 1
  let s = vec2<f32>(1.5, 1.7320508);
  let a = vec2<f32>(q.x / 1.5, (q.y - q.x * 0.5773503 * 0.0) );
  let ax = q.x * 2.0 / 3.0;
  let ay = -q.x / 3.0 + 0.5773503 * q.y;
  var rx = round(ax);
  var ry = round(ay);
  let rz = round(-ax - ay);
  let dx = abs(rx - ax);
  let dy = abs(ry - ay);
  let dz = abs(rz + ax + ay);
  if (dx > dy && dx > dz) { rx = -ry - rz; } else if (dy > dz) { ry = -rx - rz; }
  let cx = 1.5 * rx;
  let cy = 1.7320508 * (ry + rx * 0.5);
  _ = s; _ = a;
  return vec4<f32>(q - vec2<f32>(cx, cy), rx, ry);
}
fn hex_sd(v: vec2<f32>) -> f32 {
  // distance to the edge of a flat-topped hex of circumradius 1 (negative inside)
  let k = vec3<f32>(-0.8660254, 0.5, 0.5773503);
  var p = abs(v.yx);
  p = p - 2.0 * min(dot(k.xy, p), 0.0) * k.xy;
  p = p - vec2<f32>(clamp(p.x, -k.z * 0.8660254, k.z * 0.8660254), 0.8660254);
  return length(p) * sign(p.y);
}
fn motif_raft(p: vec2<f32>, L: Look) -> Cell {
  let K = L.m.x;            // each raft is K times smaller than the one around it
  let g = L.density;        // hex circumradius at level 0
  let n = floor(L.zoom);
  let f = L.zoom - n;
  var sc = pow(K, -f) / g;  // hex units per screen unit
  var q = p * sc;
  var c: Cell;
  var lev = 0;
  var fid = 0.0;
  loop {
    let hc = hex_cell(q);
    let v = hc.xy;
    let i = i32(hc.z);
    let j = i32(hc.w);
    let cls = imod(i - j, 3);
    let sd = -hex_sd(v);
    let lv = wrap64(f32(lev) + n);
    if (cls == 0 && lev < 3) {
      // a window: the next raft, K times smaller, inside this hex
      q = v * K;
      sc = sc * K;
      lev = lev + 1;
      fid = fract(fid * 7.13 + hash21(vec2<f32>(f32(i), f32(j)) + 0.5) + 0.17);
      continue;
    }
    // class 1 and 2 cells take elements from two disjoint halves of the eight, so neighbours differ
    let hh = hash21(vec2<f32>(f32(i), f32(j)) + lv * 1.31 + L.seed);
    var e = imod(i32(L.eoff) + (cls - 1) + 2 * i32(floor(hh * 4.0)), 8);
    if (cls == 0) { e = -1; }    // the deepest windows: the recursion carries on below the pixel, as film
    c.local = v / max(length(v) + max(sd, 0.0), 1e-5);
    c.edge = sd / sc;
    c.size = (length(v) + max(sd, 0.0)) / sc;
    c.id = hh;
    c.elem = e;
    c.depth = lev;
    c.wall = 0.0;
    c.fid = fid;
    break;
  }
  return c;
}

// ------------------------------------------------------------------ motif 5: film (one giant soap film; lenses drift in it)
fn motif_film(p: vec2<f32>, L: Look) -> Cell {
  var c: Cell;
  // lenses: a sparse grid of bubbles drifting up through the film
  let g = 0.95;
  let drift = vec2<f32>(0.0, -L.zoom * g * 0.5);
  let q = (p + drift) / g;
  let gi = floor(q);
  var best = 1e9;
  var bc = vec2<f32>(0.0);
  var br = 0.0;
  var bid = vec2<f32>(0.0);
  for (var j = -1; j <= 1; j = j + 1) {
    for (var i = -1; i <= 1; i = i + 1) {
      let cell = gi + vec2<f32>(f32(i), f32(j));
      let hc = vec2<f32>(cell.x, wrap64(cell.y));
      let h = hash22(hc + L.seed * 1.9);
      let ctr = cell + 0.5 + (h - 0.5) * 0.4;
      let rad = 0.14 + 0.14 * hash21(hc + 4.4 + L.seed);
      let d = length(q - ctr) - rad;
      if (d < best) { best = d; bc = ctr; br = rad; bid = cell; }
    }
  }
  if (best < 0.0) {
    // inside a lens: a small lather foam, itself diving
    let lq = (q - bc) / br;
    var L2 = L;
    L2.m.x = 3.2;
    L2.density = 0.3;
    L2.eoff = L.eoff + 2.0;
    let bh = vec2<f32>(bid.x, wrap64(bid.y));
    L2.seed = L.seed + hash21(bh);
    L2.zoom = wrap64(L.zoom * 0.5 + hash21(bh + 2.0) * 3.0);
    c = motif_lather(lq * 1.15, L2);
    c.fid = fract(hash21(bh + 9.1) + 0.3);
    let s = g * br / 1.15;
    c.edge = min(c.edge * s, -best * g);
    if (-best * g < c.edge + 1e-5) { c.wall = 1.0; }
    c.size = c.size * s;
    c.depth = c.depth + 1;
    return c;
  }
  c.local = p * 0.45;
  c.edge = best * g;
  c.size = 3.0;
  c.id = 0.5;
  c.elem = -1;              // the film itself
  c.depth = 0;
  c.wall = 1.0;
  c.fid = 0.0;
  return c;
}

fn motif(p: vec2<f32>, L: Look) -> Cell {
  switch L.motif {
    case 1: { return motif_steiner(p, L); }
    case 2: { return motif_hyper(p, L); }
    case 3: { return motif_droste(p, L); }
    case 4: { return motif_raft(p, L); }
    case 5: { return motif_film(p, L); }
    default: { return motif_lather(p, L); }
  }
}

// ------------------------------------------------------------------ the eight elements
// uv: inside the bubble (about -1.3..1.3), pix: one pixel in uv units, s: the bubble's id, e: intensity
fn el_fire(uv: vec2<f32>, t: f32, pix: f32, s: f32, e: f32) -> vec3<f32> {
  var q = uv * 1.5 + vec2<f32>(s * 9.0, 0.0);
  q.y = q.y - t * 1.4;
  let w = vec2<f32>(fbm(q * 1.2 + vec2<f32>(0.0, t * 0.5), pix * 1.8, 5), fbm(q * 1.2 + vec2<f32>(5.2, 1.3), pix * 1.8, 5));
  let n = fbm(q * 1.4 + 2.2 * (w - 0.5), pix * 2.1, 6);
  // tongues: the noise has to beat a threshold that rises with height
  let h = (uv.y + 1.15) * 0.42;
  let heat = clamp((n - 0.3 - h * (0.75 - 0.25 * e)) * 3.4 + 0.1 * e, 0.0, 1.6);
  let c = vec3<f32>(1.25, 0.18, 0.02) * smoothstep(0.0, 0.35, heat) + vec3<f32>(0.6, 0.45, 0.02) * smoothstep(0.3, 0.8, heat)
        + vec3<f32>(0.5, 0.55, 0.45) * smoothstep(0.85, 1.5, heat);
  let ground = vec3<f32>(0.10, 0.0, 0.03) * (1.0 - smoothstep(0.0, 0.3, heat));
  let blue = vec3<f32>(0.05, 0.2, 1.0) * smoothstep(0.5, 1.15, -uv.y) * smoothstep(0.1, 0.5, heat) * 0.7;
  let ember = pow(hash21(floor(uv * 26.0 + vec2<f32>(0.0, -t * 9.0)) + s), 22.0) * smoothstep(-0.2, 0.8, uv.y) * 2.0;
  return c + ground + blue + vec3<f32>(1.0, 0.5, 0.1) * ember * clamp(1.0 - pix * 26.0, 0.0, 1.0);
}
fn el_water(uv: vec2<f32>, t: f32, pix: f32, s: f32, e: f32) -> vec3<f32> {
  // caustic net: a few rounds of warped sines
  var p = uv * 2.6 + vec2<f32>(s * 13.0, s * 7.0) - 250.0;
  var i = p;
  var c = 1.0;
  let inten = 0.005;
  for (var n = 0; n < 5; n = n + 1) {
    let tt = t * 0.5 * (1.0 - 3.5 / f32(n + 1));
    i = p + vec2<f32>(cos(tt - i.x) + sin(tt + i.y), sin(tt - i.y) + cos(tt + i.x));
    c = c + 1.0 / length(vec2<f32>(p.x / (sin(i.x + tt) / inten), p.y / (cos(i.y + tt) / inten)));
  }
  c = c / 5.0;
  c = 1.17 - pow(c, 1.4);
  let k = clamp(pow(abs(c), 8.0) * (0.7 + 0.8 * e), 0.0, 1.6);
  let fadeK = clamp(1.0 - pix * 7.0, 0.0, 1.0);
  let deep = mix(vec3<f32>(0.0, 0.02, 0.14), vec3<f32>(0.0, 0.16, 0.36), 0.5 + 0.5 * uv.y);
  let r = length(uv);
  let ripple = pow(0.5 + 0.5 * sin(r * 22.0 - t * 5.0), 6.0) * exp(-r * 1.5) * 0.25 * e * fadeK;
  return deep + vec3<f32>(0.2, 0.85, 1.0) * (k * fadeK + 0.18 * (1.0 - fadeK)) + vec3<f32>(0.3, 0.7, 1.0) * ripple;
}
fn el_earth(uv: vec2<f32>, t: f32, pix: f32, s: f32, e: f32) -> vec3<f32> {
  // agate: warped concentric bands around a crystal-lined hollow
  let w = vec2<f32>(fbm(uv * 1.7 + s * 5.0, pix, 4), fbm(uv * 1.7 + s * 5.0 + 3.3, pix, 4)) - 0.5;
  let d = length(uv * vec2<f32>(1.0, 1.15) + w * 0.65 + vec2<f32>(0.08, -0.05));
  let bands = d * 9.0 + fbm(uv * 4.0 + s, pix, 3) * 2.0 - t * 0.15;
  let fb = clamp(1.0 - pix * 30.0, 0.0, 1.0);
  let b = 0.5 + 0.5 * sin(bands * TAU) * fb;
  let tone = fract(bands * 0.21 + s);
  var col = pal(vec3<f32>(0.5, 0.35, 0.25), vec3<f32>(0.45, 0.3, 0.25), vec3<f32>(1.0, 1.0, 1.0),
                vec3<f32>(0.02, 0.15, 0.3) + s * 0.3, tone);
  col = mix(col * 0.22, col * 0.95, b);
  // the hollow: quartz facets catching the light
  let hq = d < 0.22;
  if (hq) {
    let fq = uv * 14.0;
    let f = fract(fq) - 0.5;
    let sp = pow(max(0.0, 1.0 - length(f) * 2.2), 2.0) * (0.5 + 0.5 * sin(t * 4.0 + hash21(floor(fq)) * 30.0));
    col = vec3<f32>(0.55, 0.3, 0.85) * (0.6 + 0.6 * hash21(floor(fq))) + vec3<f32>(1.0) * sp * 0.8 * (0.5 + e);
  }
  return col;
}
fn el_air(uv: vec2<f32>, t: f32, pix: f32, s: f32, e: f32) -> vec3<f32> {
  let r = length(uv);
  let sw = 1.7 / (r + 0.35) - t * 0.35;
  let q = rot(sw) * uv;
  let n = fbm(q * 1.8 + s * 7.0 + vec2<f32>(t * 0.1, 0.0), pix * 1.8, 6);
  let n2 = fbm(q * 4.0 - s * 3.0, pix * 4.0, 4);
  let sky = mix(vec3<f32>(0.10, 0.06, 0.38), vec3<f32>(0.95, 0.32, 0.42), smoothstep(-1.0, 1.0, uv.y + 0.3 * sin(s * 9.0)));
  let cloud = smoothstep(0.45, 0.8, n + 0.15 * n2);
  let streak = pow(abs(sin(atan2(q.y, q.x) * 5.0 + n * 6.0)), 20.0) * clamp(1.0 - pix * 12.0, 0.0, 1.0) * smoothstep(0.2, 1.0, r);
  return mix(sky, vec3<f32>(1.0, 0.85, 0.95), cloud * 0.8) + vec3<f32>(0.8, 0.95, 1.0) * streak * 0.35 * (0.5 + e);
}
fn el_metal(uv: vec2<f32>, t: f32, pix: f32, s: f32, e: f32) -> vec3<f32> {
  // bismuth: hopper crystals (square terraces stepping down into a hollow), smaller ones growing from
  // the corners, each terrace a different colour of its oxide skin
  let q = rot(s * TAU + t * 0.04) * uv * 1.15;
  let d0 = max(abs(q.x), abs(q.y));
  let q1 = rot(0.4 + s) * (abs(q) - vec2<f32>(0.62)) * 2.3;
  let d1 = max(abs(q1.x), abs(q1.y)) / 2.3;
  var d = d0;
  var lv = 0.0;
  var pz = pix;
  if (d1 < 0.2 && d1 < d0 * 0.6) { d = d1 * 2.3; lv = 1.0; pz = pix * 2.3; }
  let terr = d * 7.0;
  let k = floor(terr);
  let f = fract(terr);
  let aa = clamp(pz * 7.0 * 1.5, 0.02, 0.5);
  let nm = 60.0 + ((k * 53.0 + lv * 140.0 + s * 300.0 + 40.0 * sin(t * 0.25 + k)) % 340.0);
  let ox = film_rgb(nm, 1.0);
  let vivid = max((ox - vec3<f32>(luma(ox) * 0.7)) * 3.0 + 0.06, vec3<f32>(0.0));
  // each step is lit along its outer lip and shadowed at its foot
  let lip = smoothstep(1.0 - aa, 1.0, f) + (1.0 - smoothstep(0.0, aa, f));
  let face = 0.45 + 0.55 * f;
  let fade = clamp(1.0 - pz * 7.0 * 2.0, 0.0, 1.0);
  return vivid * (0.45 + 0.55 * e) * mix(0.75, face, fade) + vec3<f32>(1.0, 0.95, 0.9) * lip * 0.3 * fade;
}
fn el_ice(uv: vec2<f32>, t: f32, pix: f32, s: f32, e: f32) -> vec3<f32> {
  // frost: six-fold dendrites, branches on branches
  var q = rot(s * 2.0 + t * 0.03) * uv * 1.25;
  let r = length(q);
  var a = atan2(q.y, q.x);
  let w = PI / 3.0;
  a = abs(((a % w) + w) % w - w * 0.5);
  q = r * vec2<f32>(cos(a), sin(a));
  var d = abs(q.y);
  var sc = 1.0;
  for (var k = 0; k < 4; k = k + 1) {
    let x = q.x * 4.0 * sc;
    let fx = fract(x) - 0.5;
    let br = abs(fx * 0.57 - q.y * 4.0 * sc * 0.0) ;
    let bb = abs((q.y * 4.0 * sc) - abs(fx) * 1.1) / (4.0 * sc);
    d = min(d, bb + 0.004 * f32(k));
    sc = sc * 2.3;
    _ = br;
  }
  let lw = max(0.006, pix * 1.2);
  let line = smoothstep(lw * 2.5, 0.0, d) * smoothstep(1.25, 0.2, r);
  let bg = mix(vec3<f32>(0.0, 0.03, 0.12), vec3<f32>(0.02, 0.18, 0.34), smoothstep(1.2, 0.0, r));
  let glint = pow(hash21(floor(uv * 40.0 + s * 9.0)), 30.0) * (0.5 + 0.5 * sin(t * 6.0 + s * 50.0));
  return bg + vec3<f32>(0.75, 0.95, 1.2) * line * (0.8 + 0.6 * e) + vec3<f32>(0.8, 0.9, 1.0) * glint * clamp(1.0 - pix * 30.0, 0.0, 1.0);
}
fn el_lightning(uv: vec2<f32>, t: f32, pix: f32, s: f32, e: f32) -> vec3<f32> {
  // a plasma globe: filaments from the core to the glass
  let r = length(uv);
  let a = atan2(uv.y, uv.x);
  var glow = vec3<f32>(0.0);
  for (var k = 0; k < 4; k = k + 1) {
    let fk = f32(k);
    let ph = a * 1.0 + fk * 1.7 + s * 9.0 + t * (0.25 + 0.1 * fk);
    let wob = fbm(vec2<f32>(r * 3.0 - t * 1.5, fk * 7.0 + s * 3.0), pix * 3.0, 4) - 0.5;
    let line = abs(sin(ph * 2.0 + wob * 3.0 * r));
    let wdt = max(0.035, pix * 2.5) + 0.05 * r;
    glow = glow + vec3<f32>(0.85, 0.5, 1.2) * (smoothstep(wdt, 0.0, line) + 0.25 * smoothstep(wdt * 4.0, 0.0, line)) * smoothstep(1.35, 0.1, r);
  }
  let core = exp(-r * r * 40.0);
  let bg = vec3<f32>(0.03, 0.0, 0.08) + vec3<f32>(0.18, 0.0, 0.3) * exp(-r * 2.0);
  return bg + glow * (0.5 + 1.2 * e) + vec3<f32>(1.0, 0.85, 1.0) * core * (0.6 + 0.8 * e);
}
fn el_magma(uv: vec2<f32>, t: f32, pix: f32, s: f32, e: f32) -> vec3<f32> {
  // cooling crust: dark plates with glowing seams
  let q = uv * 3.0 + vec2<f32>(s * 11.0, t * 0.12);
  let gi = floor(q);
  var f1 = 9.0;
  var f2 = 9.0;
  for (var j = -1; j <= 1; j = j + 1) {
    for (var i = -1; i <= 1; i = i + 1) {
      let cell = gi + vec2<f32>(f32(i), f32(j));
      let o = cell + hash22(cell + s) * 0.9 + 0.05 + 0.08 * vec2<f32>(sin(t + cell.x), cos(t * 0.7 + cell.y));
      let d = length(q - o);
      if (d < f1) { f2 = f1; f1 = d; } else if (d < f2) { f2 = d; }
    }
  }
  let seam = f2 - f1;
  let wdt = max(0.04, pix * 3.0 * 3.0);
  let heat = smoothstep(wdt * 2.2, 0.0, seam) * (0.6 + 0.6 * e) + 0.08 * fbm(q * 0.7 + t * 0.2, pix * 2.0, 3);
  let crust = vec3<f32>(0.05, 0.025, 0.03) * (0.5 + 0.9 * fbm(q * 2.0, pix * 6.0, 4));
  return crust + vec3<f32>(1.8, 0.35, 0.02) * heat + vec3<f32>(1.0, 0.8, 0.2) * heat * heat * 0.8;
}
fn elem_mean(k: i32, s: f32) -> vec3<f32> {
  var c = vec3<f32>(0.3);
  switch k {
    case 0: { c = vec3<f32>(0.75, 0.22, 0.04); }
    case 1: { c = vec3<f32>(0.04, 0.32, 0.55); }
    case 2: { c = vec3<f32>(0.45, 0.25, 0.18); }
    case 3: { c = vec3<f32>(0.6, 0.4, 0.62); }
    case 4: { c = vec3<f32>(0.55, 0.35, 0.6); }
    case 5: { c = vec3<f32>(0.2, 0.42, 0.62); }
    case 6: { c = vec3<f32>(0.32, 0.12, 0.5); }
    default: { c = vec3<f32>(0.6, 0.15, 0.03); }
  }
  let hs = select(u.pal1[(k - 4) & 3], u.pal0[k & 3], k < 4);
  return hue(c, hs + (s - 0.5) * 0.06);
}
fn element(k: i32, uv: vec2<f32>, t: f32, pix: f32, s: f32, e: f32) -> vec3<f32> {
  var c = vec3<f32>(0.0);
  switch k {
    case 0: { c = el_fire(uv, t, pix, s, e); }
    case 1: { c = el_water(uv, t, pix, s, e); }
    case 2: { c = el_earth(uv, t, pix, s, e); }
    case 3: { c = el_air(uv, t, pix, s, e); }
    case 4: { c = el_metal(uv, t, pix, s, e); }
    case 5: { c = el_ice(uv, t, pix, s, e); }
    case 6: { c = el_lightning(uv, t, pix, s, e); }
    default: { c = el_magma(uv, t, pix, s, e); }
  }
  let hs = select(u.pal1[(k - 4) & 3], u.pal0[k & 3], k < 4);
  return hue(c, hs);
}

// ------------------------------------------------------------------ shading a bubble
struct Shade {
  col: vec3<f32>,
  depth: f32,
  elem: f32,
  id: f32,
  fid: f32,
};

fn shade(c: Cell, L: Look, p: vec2<f32>) -> Shade {
  let px = u.res.z;
  let t = u.clk.x;
  let kick = u.aud.x;
  let sub = u.aud.y;
  let bass = u.aud.z;
  let lowmid = u.aud.w;
  let highmid = u.aud2.x;
  let high = u.aud2.y;
  let calm = u.aud2.w;
  var o: Shade;
  o.depth = f32(c.depth);
  o.elem = f32(c.elem);
  o.id = c.id;
  o.fid = c.fid;

  let lr = min(length(c.local), 1.0);
  let r2 = lr * lr;
  let nz = sqrt(max(1.0 - r2, 0.0));
  let lod = clamp((c.size / px - 3.0) / 9.0, 0.0, 1.0);     // bubbles under a few pixels melt into their colour

  // interior: an element world seen through the bubble's lens
  var el = c.elem;
  if (u.ext.y >= 0.0 && el >= 0) { el = i32(u.ext.y + 0.5); }
  let surging = el == i32(u.fx.z + 0.5);
  var interior = vec3<f32>(0.0);
  var filmw = 0.0;
  if (el >= 0) {
    let lens = c.local / (0.45 + 0.55 * nz);
    let uvI = rot(c.id * TAU) * lens * 1.1;
    let pix = px / max(c.size, 1e-5) * 1.1 * 1.8;
    var ie = 0.3 + 1.3 * highmid;
    if (surging) { ie = ie + 0.9 * u.fx.w; }
    if (lod > 0.0) {
      interior = element(el, uvI, t + c.id * 17.0, pix, c.id, ie);
    }
    interior = mix(elem_mean(el, c.id) * (0.6 + 0.6 * ie), interior, lod) * (0.5 + 1.0 * highmid);
    // the inside of a dome is darker towards its rim
    interior = interior * (0.35 + 0.65 * nz * nz);
    if (surging) { interior = interior * (1.0 + 0.6 * u.fx.w); }
    filmw = 0.05 + 0.95 * pow(lr, 3.5);
  } else {
    filmw = 1.0;
  }
  interior = interior * u.lay.z;

  // soap film: thickness swirls (Marangoni flow), drains downwards, swells with the sub-bass
  let sw = L.swirl;
  var fq = c.local * 1.7 + vec2<f32>(c.id * 31.0, c.id * 17.0);
  fq = rot(sw * 0.6 + c.id * 6.0) * fq;
  let fpix = px / max(c.size, 1e-4);
  let fl = 40.0 * vec2<f32>(cos(sw * 0.01), sin(sw * 0.01));
  let w1 = fbm(fq + fl, fpix * 2.0, 4);
  let w2 = fbm(fq * 1.3 + 3.0 * (vec2<f32>(w1, -w1) - 0.25) - fl.yx * 0.8, fpix * 2.6, 5);
  var nm = L.fbase + L.fswing * (w2 - 0.5) * 2.0 - c.local.y * 120.0 + 70.0 * sub;
  if (el < 0) {
    // the giant film: bands from top to bottom, black film forming at the top where it drains thinnest
    let fp = rot(sw * 0.15) * p;
    let fl2 = 40.0 * vec2<f32>(cos(sw * 0.006), sin(sw * 0.006));
    let g1 = fbm(fp * 0.9 + fl2, px * 0.9, 5);
    let g2 = fbm(fp * 1.4 + 2.5 * vec2<f32>(g1, 1.0 - g1) - fl2.yx * 1.3, px * 1.4, 6);
    let vort = sin(length(fp - vec2<f32>(0.6 * sin(sw * 0.3), 0.2)) * 9.0 - sw * 2.0 + g2 * 6.0);
    nm = L.fbase + L.fswing * ((g2 - 0.5) * 2.4 + 0.18 * vort) - p.y * 230.0 + 70.0 * sub;
  }
  nm = max(nm, 0.0);
  let cos_t = sqrt(max(1.0 - r2 / (1.335 * 1.335), 0.0));
  var fc = film_rgb(nm * cos_t, 0.0);
  fc = max(mix(vec3<f32>(luma(fc)), fc, 1.6), vec3<f32>(0.0));
  fc = max(hue(fc, L.hue), vec3<f32>(0.0)) * u.light.rgb;
  let fstr = u.dbg.w * (0.3 + 1.2 * sub) * u.lay.x;
  var col = interior * (1.0 - 0.55 * filmw * min(fstr, 1.0)) + fc * filmw * fstr * 0.6;
  if (el < 0) {
    // black film is truly dark: the thinnest film reflects almost nothing
    col = fc * fstr * 0.8 * smoothstep(10.0, 90.0, nm);
  }

  // highlight: the window reflection and a sharp glint, as on a real bubble
  if (el >= 0) {
    let hl = c.local - vec2<f32>(-0.42, 0.45);
    let win = smoothstep(0.30, 0.16, length(hl * vec2<f32>(1.0, 1.6))) * 0.22;
    let glint = smoothstep(0.07, 0.0, length(c.local - vec2<f32>(-0.5, 0.52))) * 0.8;
    let rim = smoothstep(0.8, 1.0, lr) * 0.3;
    col = col + (vec3<f32>(win + glint) + fc * rim) * lod * u.lay.x;
  }

  // sparkle and fizz: glints on the film and tiny bubbles rising inside, with the hi-hats
  let fz = c.local * 8.0 + vec2<f32>(0.0, -t * 1.6) + c.id * 40.0;
  let fi = floor(fz);
  let ff = fract(fz) - 0.5 - (hash22(fi) - 0.5) * 0.5;
  let fr = 0.07 + 0.12 * hash21(fi + 3.1);
  let on = step(0.6, hash21(fi + 7.7));
  let ring = smoothstep(max(0.025, fpix * 8.0 * 1.5), 0.0, abs(length(ff) - fr)) * on;
  let twk = pow(0.5 + 0.5 * sin(t * (5.0 + 6.0 * hash21(fi + 1.3)) + hash21(fi + 2.9) * 6.28), 12.0)
            * smoothstep(0.12, 0.0, length(ff));
  let sp = (ring * 0.5 + twk * 1.5) * (0.1 + 1.5 * high) * clamp(1.0 - fpix * 60.0, 0.0, 1.0) * select(1.0, 0.0, el < 0);
  col = col + vec3<f32>(0.9, 0.95, 1.0) * sp * u.lay.w;

  // Plateau borders: where films meet, a liquid edge like the lead in stained glass, its neon line
  // lighting up with the bass
  let bwpx = max(1.6, min(0.05 * c.size / px, 10.0)) * (1.0 + c.wall * 0.9);
  let epx = c.edge / px;
  let inb = (1.0 - smoothstep(bwpx - 0.8, bwpx + 0.8, epx)) * (0.25 + 0.75 * lod);
  let mid = exp(-epx * epx / max(0.06 * bwpx * bwpx, 0.45));
  let edgefilm = film_rgb(L.fbase * 0.5 + 300.0 + 220.0 * sin(c.id * 20.0 + t * 0.3), 0.0);
  let neon = max(mix(vec3<f32>(luma(edgefilm)), edgefilm, 2.0), vec3<f32>(0.0)) * u.light.rgb;
  let glow = (0.06 + 1.7 * bass * bass) * (1.0 + kick * 0.25);
  let lead = vec3<f32>(0.012, 0.008, 0.02);
  col = mix(col, lead * (1.0 - u.lay.y * 0.0), inb * min(u.lay.x + u.lay.z + u.lay.w, 1.0));
  col = col + neon * mid * glow * 1.3 * u.lay.y * (0.3 + 0.7 * lod);
  col = col + neon * exp(-max(epx - bwpx, 0.0) / (1.5 + 0.5 * bwpx)) * 0.12 * glow * u.lay.y;

  o.col = max(col, vec3<f32>(0.0));
  return o;
}

fn render_look(p0: vec2<f32>, L: Look) -> Shade {
  if (L.motif == 9) {
    // the dark before the first bubble and after the last
    return Shade(vec3<f32>(0.0), 0.0, -1.0, 0.0, 0.0);
  }
  var p = p0 * (1.0 - u.ext.z * u.aud.x);                // punch in on the kick
  p = rot(L.cam) * p;
  if (L.folds > 0.5) {
    // kaleidoscope: fold the plane into mirrored wedges
    let n = L.folds;
    let w = PI / n;
    let r = length(p);
    var a = atan2(p.y, p.x) + PI;
    a = a - 2.0 * w * floor(a / (2.0 * w));
    a = abs(a - w);
    p = r * vec2<f32>(cos(a), sin(a));
  }
  // twisted forms: a vortex that tightens with the low mids
  let r = length(p);
  p = rot(L.twist * (1.0 + 0.6 * u.aud.w) * exp(-r * r * 0.6)) * p;
  // breathing warp
  let fw = 30.0 * vec2<f32>(cos(L.swirl * 0.007), sin(L.swirl * 0.007));
  let wv = vec2<f32>(vnoise(p * 0.9 + fw), vnoise(p * 0.9 + fw.yx + 5.1)) - 0.5;
  p = p + wv * (0.05 + 0.12 * u.aud.y) * (1.0 - u.aud2.w * 0.5);
  let c = motif(p, L);
  return shade(c, L, p);
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

@fragment
fn fs_scene(i: FOut) -> @location(0) vec4<f32> {
  let fc = i.pos.xy;
  let p = vec2<f32>(fc.x - 0.5 * u.res.x, 0.5 * u.res.y - fc.y) * u.res.z;
  let A = render_look(p, look_a());
  var s = A;
  let bl = u.mixv.x;
  if (bl > 0.0) {
    let B = render_look(p, look_b());
    let kind = i32(u.mixv.y + 0.5);
    var m = bl;
    var rim = 0.0;
    if (kind == 1 || kind == 2) {
      // a new bubble inflates from a point and swallows the screen
      let ctr = u.mixv.zw;
      let rr = length(p - ctr);
      let R = bl * bl * (2.15 + length(ctr));
      let wob = 0.04 * sin(atan2(p.y - ctr.y, p.x - ctr.x) * 5.0 + u.clk.x * 3.0) * bl;
      let d = rr - R - wob;
      m = 1.0 - smoothstep(-u.res.z, u.res.z, d);
      rim = exp(-abs(d) / (0.012 + 0.03 * bl)) * (1.0 - bl);
    } else if (kind == 4) {
      // collapse: the old look shrinks into one last bubble
      let rr = length(p);
      let R = (1.0 - bl) * (1.0 - bl) * 2.3;
      let d = rr - R;
      m = smoothstep(-u.res.z, u.res.z, d);
      rim = exp(-abs(d) / (0.01 + 0.03 * (1.0 - bl))) * (1.0 - bl * 0.3);
    } else if (kind == 3) {
      // a melt: the film thins through the old look in a noisy front
      let n = fbm(p * 1.3 + 7.0, u.res.z, 4);
      let d = (n + length(p) * 0.15) - (1.25 * bl - 0.05);
      m = 1.0 - smoothstep(-0.02, 0.02, d);
      rim = exp(-abs(d) / 0.02) * 0.8;
    }
    s.col = mix(A.col, B.col, m);
    if (m > 0.5) { s.depth = B.depth; s.elem = B.elem; s.id = B.id; s.fid = B.fid; }
    let rc = film_rgb(300.0 + 500.0 * fract(length(p) * 0.4 + u.clk.x * 0.1), 0.0);
    s.col = s.col + mix(vec3<f32>(luma(rc)), rc, 1.6) * rim * 1.4 * u.lay.x;
  }
  let mode = i32(u.dbg.x + 0.5);
  if (mode == 1) {
    // ids for the criteria: depth, element and the bubble's hash, exact in 8 bits
    let d = clamp(s.depth, 0.0, 15.0);
    let e = select(s.elem, 8.0, s.elem < 0.0);
    return vec4<f32>((d * 16.0 + 8.0) / 255.0, (e * 16.0 + 8.0) / 255.0, floor(s.id * 255.0) / 255.0,
                     floor(s.fid * 255.0) / 255.0);
  }
  // pop: a burst of light and a ring that runs out from the centre
  let age = u.fx.x;
  if (age >= 0.0 && age < 1.5) {
    let rr = length(p);
    let front = age * 2.4;
    let ring = exp(-abs(rr - front) / (0.03 + age * 0.08)) * exp(-age * 2.2) * u.fx.y;
    let rc2 = film_rgb(250.0 + rr * 300.0, 0.0);
    s.col = s.col * (1.0 + 0.5 * exp(-age * 6.0) * u.fx.y) + mix(vec3<f32>(luma(rc2)), rc2, 1.7) * ring * 1.6 * u.lay.x;
  }
  return vec4<f32>(s.col, 1.0);
}
"""

POST = COMMON + r"""
@group(1) @binding(0) var src: texture_2d<f32>;
@group(1) @binding(1) var blur: texture_2d<f32>;
@group(1) @binding(2) var fin: texture_2d<f32>;
struct Dir { v: vec4<f32> };
@group(1) @binding(3) var<uniform> D: Dir;

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

@fragment
fn fs_bright(i: FOut) -> @location(0) vec4<f32> {
  let c = textureSampleLevel(src, smp, i.uv, 0.0).rgb;
  let l = luma(c);
  return vec4<f32>(c * smoothstep(0.6, 1.4, l), 1.0);
}

@fragment
fn fs_blur(i: FOut) -> @location(0) vec4<f32> {
  let w = array<f32, 5>(0.227027, 0.1945946, 0.1216216, 0.054054, 0.016216);
  var c = textureSampleLevel(blur, smp, i.uv, 0.0).rgb * w[0];
  for (var k = 1; k < 5; k = k + 1) {
    let o = D.v.xy * f32(k) * 1.6;
    c = c + textureSampleLevel(blur, smp, i.uv + o, 0.0).rgb * w[k];
    c = c + textureSampleLevel(blur, smp, i.uv - o, 0.0).rgb * w[k];
  }
  return vec4<f32>(c, 1.0);
}

fn aces(x: vec3<f32>) -> vec3<f32> {
  let a = 2.51; let b = 0.03; let c = 2.43; let d = 0.59; let e = 0.14;
  return clamp((x * (a * x + b)) / (x * (c * x + d) + e), vec3<f32>(0.0), vec3<f32>(1.0));
}

@fragment
fn fs_post(i: FOut) -> @location(0) vec4<f32> {
  if (i32(u.dbg.x + 0.5) == 1) {
    return textureLoad(src, vec2<i32>(i.pos.xy), 0);
  }
  let uv = i.uv;
  let ctr = uv - 0.5;
  // chromatic aberration: the colours of a prism, stronger at the edges and on the bass
  let rpx = length(vec2<f32>(ctr.x * u.res.w, ctr.y));          // distance from the centre, square pixels
  let ca = u.post.y * ctr * rpx * 0.02;
  var c = vec3<f32>(textureSampleLevel(src, smp, uv + ca, 0.0).r,
                    textureSampleLevel(src, smp, uv, 0.0).g,
                    textureSampleLevel(src, smp, uv - ca, 0.0).b);
  let bl = textureSampleLevel(blur, smp, uv, 0.0).rgb;
  c = c + bl * u.post.w;
  c = c * u.post.x;
  c = aces(c);
  c = pow(c, vec3<f32>(1.0 / 2.2));
  // vivid: saturation pushed after the tone curve (so colours don't burn to white), and an S-curve
  let l = luma(c);
  c = clamp(mix(vec3<f32>(l), c, u.light.w), vec3<f32>(0.0), vec3<f32>(1.0));
  c = c * c * (3.0 - 2.0 * c) * 0.35 + c * 0.65;
  let v = 1.0 - u.post.z * pow(rpx / (0.5 * u.res.w) * 0.95, 2.6);
  c = c * clamp(v, 0.0, 1.0) * (1.0 - u.dbg.z);
  return vec4<f32>(c, 1.0);
}

// BT.709 limited range, dithered so smooth gradients don't band
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
  return vec4<f32>(c.rgb, select(1.0, c.a, i32(u.dbg.x + 0.5) == 1));
}
"""
