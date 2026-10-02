"""WGSL for the rubberhose engine: signed-distance "ink and paint" primitives, a film pass and a
BT.709 YUV (NV12) conversion so the media engine gets frames it can encode without CPU work.

Design space is 1920x1080 with y pointing down, whatever the render resolution. Every primitive
is one instanced quad; its fragment shader evaluates an analytic distance field, so ink lines are
anti-aliased at any resolution, can be thickened on the shadow side and can "boil" (wobble from
drawing to drawing) like hand-inked cels.
"""

COMMON = r"""
struct Scene {
  res: vec4<f32>,      // render w, h, design w, design h
  clock: vec4<f32>,    // drawing index (boil seed), time s, light angle, paper amount
};
@group(0) @binding(0) var<uniform> S: Scene;

fn hash21(p: vec2<f32>) -> f32 {
  var q = fract(p * vec2<f32>(123.34, 456.21));
  q = q + dot(q, q + 45.32);
  return fract(q.x * q.y);
}
fn vnoise(p: vec2<f32>) -> f32 {
  let i = floor(p);
  let f = fract(p);
  let u = f * f * (3.0 - 2.0 * f);
  let a = hash21(i);
  let b = hash21(i + vec2<f32>(1.0, 0.0));
  let c = hash21(i + vec2<f32>(0.0, 1.0));
  let d = hash21(i + vec2<f32>(1.0, 1.0));
  return mix(mix(a, b, u.x), mix(c, d, u.x), u.y);
}
fn fbm(p: vec2<f32>) -> f32 {
  var s = 0.0;
  var a = 0.5;
  var q = p;
  for (var k = 0; k < 4; k = k + 1) {
    s = s + a * vnoise(q);
    q = q * 2.03 + vec2<f32>(17.1, 9.7);
    a = a * 0.5;
  }
  return s;
}
fn rot2(a: f32) -> mat2x2<f32> {
  let c = cos(a);
  let s = sin(a);
  return mat2x2<f32>(vec2<f32>(c, s), vec2<f32>(-s, c));
}
"""

PRIM = COMMON + r"""
struct VIn {
  @location(0) i0: vec4<f32>, @location(1) i1: vec4<f32>, @location(2) i2: vec4<f32>,
  @location(3) i3: vec4<f32>, @location(4) i4: vec4<f32>, @location(5) i5: vec4<f32>,
  @location(6) i6: vec4<f32>, @location(7) i7: vec4<f32>,
};
struct VOut {
  @builtin(position) pos: vec4<f32>,
  @location(0) p: vec2<f32>,
  @location(1) @interpolate(flat) i0: vec4<f32>, @location(2) @interpolate(flat) i1: vec4<f32>,
  @location(3) @interpolate(flat) i2: vec4<f32>, @location(4) @interpolate(flat) i3: vec4<f32>,
  @location(5) @interpolate(flat) i4: vec4<f32>, @location(6) @interpolate(flat) i5: vec4<f32>,
  @location(7) @interpolate(flat) i6: vec4<f32>, @location(8) @interpolate(flat) i7: vec4<f32>,
};

const T_ELLIPSE = 0.0; const T_CAPSULE = 1.0; const T_BEZIER = 2.0; const T_BOX = 3.0;
const T_PIE = 4.0; const T_STAR = 5.0; const T_TRI = 6.0; const T_ARC = 7.0; const T_HEART = 8.0;
const T_RAYS = 9.0; const T_RINGS = 10.0; const T_WAVE = 11.0;

@vertex
fn vs_prim(v: VIn, @builtin(vertex_index) vi: u32) -> VOut {
  let ty = v.i4.x;
  let pad = v.i3.w + v.i4.y * 2.5 + v.i4.w * 1.5 + v.i6.x + 3.0;
  var lo = vec2<f32>(0.0);
  var hi = vec2<f32>(0.0);
  if (ty == T_CAPSULE) {
    let r = max(v.i1.z, v.i1.w);
    lo = min(v.i0.xy, v.i0.zw) - r; hi = max(v.i0.xy, v.i0.zw) + r;
  } else if (ty == T_BEZIER || ty == T_TRI) {
    let r = max(v.i1.z, v.i1.w);
    lo = min(min(v.i0.xy, v.i0.zw), v.i1.xy) - r; hi = max(max(v.i0.xy, v.i0.zw), v.i1.xy) + r;
  } else if (ty == T_BOX) {
    let r = length(v.i0.zw) + v.i1.z;
    lo = v.i0.xy - r; hi = v.i0.xy + r;
  } else if (ty == T_RAYS || ty == T_RINGS) {
    lo = vec2<f32>(-50.0); hi = S.res.zw + 50.0;
    if (v.i1.w > 0.0) { lo = max(lo, v.i0.xy - v.i1.w); hi = min(hi, v.i0.xy + v.i1.w); }
  } else if (ty == T_WAVE) {
    lo = vec2<f32>(v.i0.z, v.i0.y - abs(v.i1.z) * 1.6); hi = vec2<f32>(v.i1.x, v.i0.w);
  } else if (ty == T_ARC) {
    let r = v.i1.z + v.i1.w;
    lo = v.i0.xy - r; hi = v.i0.xy + r;
  } else if (ty == T_HEART) {
    lo = v.i0.xy - v.i1.z * 1.3; hi = v.i0.xy + v.i1.z * 1.3;
  } else {
    let r = max(v.i1.z, v.i1.w);
    lo = v.i0.xy - r; hi = v.i0.xy + r;
  }
  lo = lo - pad; hi = hi + pad;
  var corner = array<vec2<f32>, 6>(vec2<f32>(0.0, 0.0), vec2<f32>(1.0, 0.0), vec2<f32>(0.0, 1.0),
                                   vec2<f32>(0.0, 1.0), vec2<f32>(1.0, 0.0), vec2<f32>(1.0, 1.0));
  let c = corner[vi];
  let p = mix(lo, hi, c);
  var o: VOut;
  o.pos = vec4<f32>(p.x / S.res.z * 2.0 - 1.0, 1.0 - p.y / S.res.w * 2.0, 0.0, 1.0);
  o.p = p;
  o.i0 = v.i0; o.i1 = v.i1; o.i2 = v.i2; o.i3 = v.i3; o.i4 = v.i4; o.i5 = v.i5; o.i6 = v.i6; o.i7 = v.i7;
  return o;
}

fn sd_ellipse(p: vec2<f32>, r: vec2<f32>) -> f32 {
  let k0 = length(p / r);
  let k1 = length(p / (r * r));
  if (k1 < 1e-6) { return -min(r.x, r.y); }
  return k0 * (k0 - 1.0) / k1;
}
fn cross2(a: vec2<f32>, b: vec2<f32>) -> f32 { return a.x * b.y - a.y * b.x; }

// tapered capsule; returns (distance, t along the segment)
fn sd_capsule(p: vec2<f32>, a: vec2<f32>, b: vec2<f32>, ra: f32, rb: f32) -> vec2<f32> {
  let pa = p - a;
  let ba = b - a;
  let hh = dot(ba, ba);
  if (hh < 1e-4) { return vec2<f32>(length(pa) - max(ra, rb), 0.0); }
  let t = clamp(dot(pa, ba) / hh, 0.0, 1.0);
  // uneven capsule (exact) when the radii differ
  let h = sqrt(hh);
  let rr = clamp(ra - rb, -h * 0.99, h * 0.99);
  if (abs(rr) < 0.01) { return vec2<f32>(length(pa - ba * t) - ra, t); }
  let q0 = vec2<f32>(dot(pa, vec2<f32>(ba.y, -ba.x)), dot(pa, ba)) / h;
  let q = vec2<f32>(abs(q0.x), q0.y);
  let cc = vec2<f32>(sqrt(h * h - rr * rr), rr);
  let k = cross2(cc, q);
  let m = dot(cc, q);
  let n = dot(q, q);
  var d = 0.0;
  if (k < 0.0) { d = sqrt(n) - ra; }
  else if (k > cc.x * h) { d = sqrt(n + h * h - 2.0 * q.y * h) - rb; }
  else { d = m / h - ra; }
  return vec2<f32>(d, t);
}

fn dot2(v: vec2<f32>) -> f32 { return dot(v, v); }

// quadratic bezier distance (Inigo Quilez) + the curve parameter of the closest point
fn sd_bezier(pos: vec2<f32>, A: vec2<f32>, B0: vec2<f32>, C: vec2<f32>) -> vec2<f32> {
  var B = B0;
  let bb = A - 2.0 * B + C;
  if (dot(bb, bb) < 0.5) {
    let r = sd_capsule(pos, A, C, 0.0, 0.0);
    return r;
  }
  let a = B - A;
  let b = A - 2.0 * B + C;
  let c = a * 2.0;
  let d = A - pos;
  let kk = 1.0 / dot(b, b);
  let kx = kk * dot(a, b);
  let ky = kk * (2.0 * dot(a, a) + dot(d, b)) / 3.0;
  let kz = kk * dot(d, a);
  let p = ky - kx * kx;
  let p3 = p * p * p;
  let q = kx * (2.0 * kx * kx - 3.0 * ky) + kz;
  var h = q * q + 4.0 * p3;
  var res = 0.0;
  var tt = 0.0;
  if (h >= 0.0) {
    h = sqrt(h);
    let x = (vec2<f32>(h, -h) - q) / 2.0;
    let uv = sign(x) * pow(abs(x), vec2<f32>(1.0 / 3.0));
    tt = clamp(uv.x + uv.y - kx, 0.0, 1.0);
    res = dot2(d + (c + b * tt) * tt);
  } else {
    let z = sqrt(-p);
    let v = acos(clamp(q / (p * z * 2.0), -1.0, 1.0)) / 3.0;
    let m = cos(v);
    let n = sin(v) * 1.732050808;
    let t3 = clamp(vec3<f32>(m + m, -n - m, n - m) * z - kx, vec3<f32>(0.0), vec3<f32>(1.0));
    let r1 = dot2(d + (c + b * t3.x) * t3.x);
    let r2 = dot2(d + (c + b * t3.y) * t3.y);
    if (r1 < r2) { res = r1; tt = t3.x; } else { res = r2; tt = t3.y; }
  }
  return vec2<f32>(sqrt(res), tt);
}

fn sd_box(p: vec2<f32>, b: vec2<f32>, r: f32) -> f32 {
  let rr = min(r, min(b.x, b.y));
  let q = abs(p) - b + rr;
  return length(max(q, vec2<f32>(0.0))) + min(max(q.x, q.y), 0.0) - rr;
}

// pie (wedge) opening along +y with aperture sin/cos c
fn sd_pie(p0: vec2<f32>, c: vec2<f32>, r: f32) -> f32 {
  let p = vec2<f32>(abs(p0.x), p0.y);
  let l = length(p) - r;
  let m = length(p - c * clamp(dot(p, c), 0.0, r));
  return max(l, m * sign(c.y * p.x - c.x * p.y));
}

fn sd_star(p0: vec2<f32>, r: f32, n: f32, m: f32) -> f32 {
  let an = 3.141593 / n;
  let en = 3.141593 / m;
  let acs = vec2<f32>(cos(an), sin(an));
  let ecs = vec2<f32>(cos(en), sin(en));
  let ang = atan2(p0.x, p0.y);
  let bn = ang - 2.0 * an * floor(ang / (2.0 * an)) - an;
  var p = length(p0) * vec2<f32>(cos(bn), abs(sin(bn)));
  p = p - r * acs;
  p = p + ecs * clamp(-dot(p, ecs), 0.0, r * acs.y / ecs.y);
  return length(p) * sign(p.x);
}

fn sd_tri(p: vec2<f32>, p0: vec2<f32>, p1: vec2<f32>, p2: vec2<f32>) -> f32 {
  let e0 = p1 - p0; let e1 = p2 - p1; let e2 = p0 - p2;
  let v0 = p - p0; let v1 = p - p1; let v2 = p - p2;
  let pq0 = v0 - e0 * clamp(dot(v0, e0) / dot(e0, e0), 0.0, 1.0);
  let pq1 = v1 - e1 * clamp(dot(v1, e1) / dot(e1, e1), 0.0, 1.0);
  let pq2 = v2 - e2 * clamp(dot(v2, e2) / dot(e2, e2), 0.0, 1.0);
  let s = sign(e0.x * e2.y - e0.y * e2.x);
  let d = min(min(vec2<f32>(dot(pq0, pq0), s * (v0.x * e0.y - v0.y * e0.x)),
                  vec2<f32>(dot(pq1, pq1), s * (v1.x * e1.y - v1.y * e1.x))),
                  vec2<f32>(dot(pq2, pq2), s * (v2.x * e2.y - v2.y * e2.x)));
  return -sqrt(d.x) * sign(d.y);
}

fn sd_arc(p0: vec2<f32>, sc: vec2<f32>, ra: f32, rb: f32) -> f32 {
  let p = vec2<f32>(abs(p0.x), p0.y);
  if (sc.y * p.x > sc.x * p.y) { return length(p - sc * ra) - rb; }
  return abs(length(p) - ra) - rb;
}

fn sd_heart(p0: vec2<f32>) -> f32 {
  let p = vec2<f32>(abs(p0.x), p0.y);
  if (p.y + p.x > 1.0) { return sqrt(dot2(p - vec2<f32>(0.25, 0.75))) - sqrt(2.0) / 4.0; }
  return sqrt(min(dot2(p - vec2<f32>(0.0, 1.0)), dot2(p - 0.5 * max(p.x + p.y, 0.0)))) * sign(p.x - p.y);
}

fn wave_y(x: f32, v: VOut) -> f32 {
  let w = 6.2831853 / max(v.i1.w, 1.0);
  return v.i0.y + v.i1.z * (sin(x * w + v.i5.y) + 0.35 * sin(x * w * 2.3 + v.i5.y * 1.7 + 1.3)
                            + 0.12 * sin(x * w * 5.1 + v.i5.y * 0.6 + 4.0));
}

// distance (px, negative inside), curve parameter t, and a shading size
fn shape(p: vec2<f32>, v: VOut) -> vec3<f32> {
  let ty = v.i4.x;
  let rot = v.i5.w;
  if (ty == T_ELLIPSE) {
    let lp = rot2(-rot) * (p - v.i0.xy);
    let r = max(v.i1.zw, vec2<f32>(0.01));
    return vec3<f32>(sd_ellipse(lp, r), lp.y / r.y * 0.5 + 0.5, min(r.x, r.y));
  } else if (ty == T_CAPSULE) {
    let r = sd_capsule(p, v.i0.xy, v.i0.zw, v.i1.z, v.i1.w);
    return vec3<f32>(r.x, r.y, max(v.i1.z, v.i1.w));
  } else if (ty == T_BEZIER) {
    let r = sd_bezier(p, v.i0.xy, v.i0.zw, v.i1.xy);
    return vec3<f32>(r.x - mix(v.i1.z, v.i1.w, r.y), r.y, max(v.i1.z, v.i1.w));
  } else if (ty == T_BOX) {
    let lp = rot2(-rot) * (p - v.i0.xy);
    return vec3<f32>(sd_box(lp, v.i0.zw, v.i1.z), lp.y / max(v.i0.w, 0.01) * 0.5 + 0.5, min(v.i0.z, v.i0.w));
  } else if (ty == T_PIE) {
    let lp = rot2(-rot) * (p - v.i0.xy);
    let r = max(v.i1.zw, vec2<f32>(0.01));
    let de = sd_ellipse(lp, r);
    // wedge cut, apex slightly inside the pupil, opening towards angle p0 (0 = up)
    let dir = rot2(v.i5.y) * vec2<f32>(0.0, -1.0);
    let wp = rot2(-v.i5.y) * (lp - dir * min(r.x, r.y) * 0.15);
    let cut = sd_pie(vec2<f32>(wp.x, -wp.y), vec2<f32>(sin(v.i5.z), cos(v.i5.z)), max(r.x, r.y) * 3.0);
    return vec3<f32>(max(de, -cut), lp.y / r.y * 0.5 + 0.5, min(r.x, r.y));
  } else if (ty == T_STAR) {
    let lp = rot2(-rot) * (p - v.i0.xy);
    return vec3<f32>(sd_star(lp, v.i1.z, max(v.i5.y, 3.0), clamp(v.i5.z, 2.0, v.i5.y)), 0.5, v.i1.z * 0.5);
  } else if (ty == T_TRI) {
    return vec3<f32>(sd_tri(p, v.i0.xy, v.i0.zw, v.i1.xy) - v.i1.z, 0.5, 20.0);
  } else if (ty == T_ARC) {
    let lp = rot2(-rot) * (p - v.i0.xy);
    return vec3<f32>(sd_arc(lp, vec2<f32>(sin(v.i5.y), cos(v.i5.y)), v.i1.z, v.i1.w), 0.5, v.i1.w);
  } else if (ty == T_HEART) {
    let lp = rot2(-rot) * (p - v.i0.xy) / v.i1.z;
    return vec3<f32>(sd_heart(vec2<f32>(lp.x, -lp.y + 0.55)) * v.i1.z, 0.5, v.i1.z * 0.4);
  } else if (ty == T_WAVE) {
    let y = wave_y(p.x, v);
    let dy = (wave_y(p.x + 1.0, v) - wave_y(p.x - 1.0, v)) * 0.5;
    let d = (y - p.y) / sqrt(1.0 + dy * dy);
    let depth = (p.y - y) / max(v.i0.w - y, 1.0);
    return vec3<f32>(max(d, p.y - v.i0.w), depth, 40.0);
  }
  return vec3<f32>(-1.0, 0.5, 10.0);
}

fn premul(c: vec3<f32>, a: f32) -> vec4<f32> { return vec4<f32>(c * a, a); }

@fragment
fn fs_prim(v: VOut) -> @location(0) vec4<f32> {
  let ty = v.i4.x;
  let mat = v.i5.x;
  var p = v.p;
  let fill = v.i2;
  let fill2 = v.i7;
  let alpha_mul = 1.0 - v.i6.w;

  // full-screen patterns: sunburst rays and concentric rings
  if (ty == T_RAYS || ty == T_RINGS) {
    let lp = p - v.i0.xy;
    var s = 0.0;
    if (ty == T_RAYS) { s = (atan2(lp.y, lp.x) + v.i5.w) / 6.2831853 * v.i5.y; }
    else { s = length(lp) / max(v.i1.z, 1.0) - v.i5.w; }
    let f = fract(s);
    let pxs = S.res.z / S.res.x;
    var w = pxs / max(v.i1.z, 1.0);
    if (ty == T_RAYS) { w = v.i5.y * pxs / (6.2831853 * max(length(lp), 1.0)); }
    w = w * 1.2 + 1e-4;
    let k = smoothstep(v.i5.z - w, v.i5.z + w, f) * (1.0 - smoothstep(1.0 - w, 1.0, f));
    var col = mix(fill.rgb, fill2.rgb, 1.0 - k);
    var a = mix(fill.a, fill2.a, 1.0 - k);
    if (v.i1.w > 0.0) {
      let rr = length(lp);
      a = a * (1.0 - smoothstep(v.i1.w * 0.6, v.i1.w, rr));
    }
    if (mat == 1.0) { col = col * (0.93 + 0.12 * fbm(p * 0.006 + v.i6.z)); }
    return premul(col, a * alpha_mul);
  }

  // line boil: the outline wobbles from drawing to drawing (paint does not)
  let seed = v.i6.z;
  if (v.i4.w > 0.0) {
    let q = p * 0.045 + vec2<f32>(seed * 3.7 + S.clock.x * 7.31, seed * 1.3 - S.clock.x * 3.17);
    p = p + (vec2<f32>(vnoise(q), vnoise(q + 19.7)) - 0.5) * 2.0 * v.i4.w;
  }
  if (mat == 1.0) {
    // watercolour edge: irregular, static
    let q = p * 0.012 + seed;
    p = p + (vec2<f32>(fbm(q), fbm(q + 7.3)) - 0.5) * 9.0;
  }
  let sh = shape(p, v);
  var d = sh.x - v.i6.x;
  let soft = v.i4.y;
  let pxs = S.res.z / S.res.x;            // design units per rendered pixel
  let aa = pxs * 0.85 + soft;
  if (d - v.i3.w * 0.65 > aa) { discard; }

  // light from the upper left; normal from the distance gradient (finite differences: derivative
  // builtins are not allowed in this non-uniform control flow)
  let e = 1.5;
  var n = vec2<f32>(shape(p + vec2<f32>(e, 0.0), v).x - sh.x, shape(p + vec2<f32>(0.0, e), v).x - sh.x);
  let nl = length(n);
  n = select(vec2<f32>(0.0, 1.0), n / nl, nl > 1e-5);
  let la = S.clock.z;
  let L = vec2<f32>(cos(la), sin(la));
  let away = clamp(dot(n, -L) * 0.5 + 0.5, 0.0, 1.0);

  // ink: centred on the edge, heavier on the shadow side
  var w = v.i3.w * (0.7 + 0.6 * away);
  if (v.i3.w <= 0.0) { w = 0.0; }
  let cov = 1.0 - smoothstep(-aa, aa, d - w * 0.5);
  if (cov <= 0.0) { discard; }
  var m = 0.0;
  if (w > 0.0) { m = smoothstep(-aa, aa, d + w * 0.5); }

  var base = fill.rgb;
  var fa = fill.a;
  if (fill2.a > 0.0) {
    base = mix(fill.rgb, fill2.rgb, clamp(sh.y, 0.0, 1.0));
    fa = mix(fill.a, fill2.a, clamp(sh.y, 0.0, 1.0));
  }

  if (mat == 2.0) {
    // glow: soft additive falloff outside the shape, solid inside
    let g = exp(-max(d, 0.0) / max(soft, 1.0)) * fa;
    return vec4<f32>(base * g * alpha_mul, 0.0);
  }

  // cel shading: a soft band of shadow just inside the edge facing away from the light
  let band = max(v.i6.y, sh.z * 0.55);
  let inner = clamp(1.0 + d / max(band, 1.0), 0.0, 1.0);
  let shade = v.i4.z * inner * inner * pow(away, 1.3);
  var col = base * (1.0 - 0.42 * shade) * mix(vec3<f32>(1.0), vec3<f32>(0.92, 0.85, 0.95), shade);

  if (mat == 1.0) {
    // watercolour: pigment pooling at the edge, uneven wash, granulation, paper showing through
    let pool = exp(min(d, 0.0) / 7.0);
    let wash = fbm(v.p * 0.0045 + seed * 5.1);
    let gran = vnoise(v.p * 0.55 + seed);
    col = col * (0.9 + 0.2 * wash) * (1.0 - 0.17 * pool) * (1.0 - 0.07 * gran);
    col = mix(col, vec3<f32>(0.97, 0.93, 0.82), 0.08 * (1.0 - wash));
  }

  col = mix(col, v.i3.rgb, m);
  let a = cov * mix(fa, 1.0, m) * alpha_mul;
  return premul(col, a);
}
"""

FILM = COMMON + r"""
struct Film {
  a: vec4<f32>,        // weave x, weave y (px), exposure, vignette
  b: vec4<f32>,        // grain amount, grain size, film frame, mode (0 warm, 1 two-strip, 2 b/w, 3 clean)
  c: vec4<f32>,        // saturation, warmth, fade (lifted blacks), halation
  d: vec4<f32>,        // iris centre x, y (design px), iris radius (<0 off), fade to black
  e: vec4<f32>,        // burn centre x, y, burn radius, soft focus
  f: vec4<f32>,        // number of scratches, dust, hairs, paper
  scratch: array<vec4<f32>, 4>,   // x, width, strength, wobble seed
  dust: array<vec4<f32>, 24>,     // x, y, size, kind (sign = dark/light, fraction = shape seed)
  hair: array<vec4<f32>, 4>,      // pairs: (x0, y0, x1, y1), (cx, cy, width, alpha)
};
@group(1) @binding(0) var<uniform> F: Film;
@group(1) @binding(1) var src: texture_2d<f32>;
@group(1) @binding(2) var blur: texture_2d<f32>;
@group(1) @binding(3) var smp: sampler;

struct FOut { @builtin(position) pos: vec4<f32>, @location(0) uv: vec2<f32> };

@vertex
fn vs_full(@builtin(vertex_index) vi: u32) -> FOut {
  var pts = array<vec2<f32>, 3>(vec2<f32>(-1.0, -1.0), vec2<f32>(3.0, -1.0), vec2<f32>(-1.0, 3.0));
  var o: FOut;
  let p = pts[vi];
  o.pos = vec4<f32>(p, 0.0, 1.0);
  o.uv = vec2<f32>(p.x * 0.5 + 0.5, 0.5 - p.y * 0.5);
  return o;
}

@fragment
fn fs_bright(i: FOut) -> @location(0) vec4<f32> {
  let c = textureSample(src, smp, i.uv).rgb;
  let l = dot(c, vec3<f32>(0.2126, 0.7152, 0.0722));
  return vec4<f32>(c * smoothstep(0.55, 1.0, l), 1.0);
}

struct Dir { v: vec4<f32> };
@group(1) @binding(4) var<uniform> D: Dir;

@fragment
fn fs_blur(i: FOut) -> @location(0) vec4<f32> {
  let w = array<f32, 5>(0.227027, 0.1945946, 0.1216216, 0.054054, 0.016216);
  var c = textureSample(blur, smp, i.uv).rgb * w[0];
  for (var k = 1; k < 5; k = k + 1) {
    let o = D.v.xy * f32(k) * 1.5;
    c = c + textureSample(blur, smp, i.uv + o).rgb * w[k];
    c = c + textureSample(blur, smp, i.uv - o).rgb * w[k];
  }
  return vec4<f32>(c, 1.0);
}

fn luma(c: vec3<f32>) -> f32 { return dot(c, vec3<f32>(0.2126, 0.7152, 0.0722)); }

fn seg_dist(p: vec2<f32>, a: vec2<f32>, b: vec2<f32>) -> f32 {
  let pa = p - a; let ba = b - a;
  let h = clamp(dot(pa, ba) / max(dot(ba, ba), 1e-4), 0.0, 1.0);
  return length(pa - ba * h);
}

fn bez_dist(p: vec2<f32>, a: vec2<f32>, c: vec2<f32>, b: vec2<f32>) -> f32 {
  // cheap: polyline through the quadratic curve
  var best = 1e9;
  var prev = a;
  for (var k = 1; k <= 8; k = k + 1) {
    let t = f32(k) / 8.0;
    let q = mix(mix(a, c, t), mix(c, b, t), t);
    best = min(best, seg_dist(p, prev, q));
    prev = q;
  }
  return best;
}

@fragment
fn fs_film(i: FOut) -> @location(0) vec4<f32> {
  let dsz = S.res.zw;
  let px = i.uv * dsz;                       // design-space pixel
  let ff = F.b.z;
  // gate weave: the whole picture shifts a little from film frame to film frame
  let uv = i.uv + F.a.xy / dsz;
  var c = textureSample(src, smp, uv).rgb;
  let bl = textureSample(blur, smp, uv).rgb;
  let mode = F.b.w;

  // soft focus and halation (bright areas bleed warm light)
  c = mix(c, bl, F.e.w);
  c = c + bl * vec3<f32>(1.0, 0.72, 0.5) * F.c.w;

  // colour: cream highlights, warm lifted blacks, slightly faded print
  var g = c;
  let l = luma(g);
  if (mode == 1.0) {
    // two-strip: everything is built from a red-orange and a blue-green record
    let r = g.r;
    let gc = 0.5 * (g.g + g.b);
    g = vec3<f32>(r, gc * 0.92 + r * 0.08, gc * 0.85 + 0.05);
    g = mix(vec3<f32>(luma(g)), g, 1.1);
  } else if (mode == 2.0) {
    g = vec3<f32>(l) * vec3<f32>(1.0, 0.98, 0.94);
  }
  if (mode != 3.0) {
    g = mix(vec3<f32>(luma(g)), g, F.c.x);
    g = g * mix(vec3<f32>(1.0), vec3<f32>(1.06, 1.0, 0.86), F.c.y);
    g = F.c.z * vec3<f32>(0.24, 0.16, 0.11) + g * (1.0 - F.c.z * 0.9);
  }
  // projector flicker / exposure
  g = g * F.a.z;

  // dust, hairs and scratches: dark on the print, light where the negative was dirty
  if (mode != 3.0) {
    let nd = i32(F.f.y);
    for (var k = 0; k < 24; k = k + 1) {
      if (k >= nd) { break; }
      let dd = F.dust[k];
      let q = px - dd.xy;
      let sd = fract(abs(dd.w)) * 97.0;
      let r = dd.z * (0.75 + 0.5 * vnoise(vec2<f32>(atan2(q.y, q.x) * 2.0, sd)));
      let cov = 1.0 - smoothstep(r - 1.0, r + 1.0, length(q));
      if (dd.w < 0.0) { g = mix(g, vec3<f32>(0.08, 0.06, 0.05), cov * 0.85); }
      else { g = mix(g, vec3<f32>(1.0, 0.98, 0.92), cov * 0.75); }
    }
    let nh = i32(F.f.z);
    for (var k = 0; k < 2; k = k + 1) {
      if (k >= nh) { break; }
      let h0 = F.hair[k * 2];
      let h1 = F.hair[k * 2 + 1];
      let dh = bez_dist(px, h0.xy, h1.xy, h0.zw);
      let cov = 1.0 - smoothstep(h1.z * 0.5, h1.z * 0.5 + 1.0, dh);
      g = mix(g, vec3<f32>(0.1, 0.08, 0.06), cov * h1.w);
    }
    let ns = i32(F.f.x);
    for (var k = 0; k < 4; k = k + 1) {
      if (k >= ns) { break; }
      let s = F.scratch[k];
      let x = s.x + sin(px.y * 0.013 + s.w) * 3.0 + sin(px.y * 0.051 + s.w * 2.0) * 1.0;
      let cov = (1.0 - smoothstep(s.y * 0.5, s.y * 0.5 + 1.0, abs(px.x - x)))
                * (0.6 + 0.4 * vnoise(vec2<f32>(px.y * 0.05, s.w)));
      if (s.z < 0.0) { g = mix(g, vec3<f32>(0.12, 0.1, 0.08), cov * -s.z); }
      else { g = mix(g, vec3<f32>(1.0, 0.97, 0.9), cov * s.z); }
    }
  }

  // vignette (projector hot spot)
  let vq = (i.uv - 0.5) * vec2<f32>(dsz.x / dsz.y, 1.0);
  g = g * (1.0 - F.a.w * smoothstep(0.35, 1.05, length(vq)));

  // grain: monochrome, coarser in the shadows, new pattern on every film frame
  if (F.b.x > 0.0) {
    let gp = floor(px / F.b.y);
    let n = (hash21(gp + vec2<f32>(ff * 17.13, ff * 5.71)) + hash21(gp * 1.7 + vec2<f32>(ff * 3.1, 9.0)) - 1.0);
    g = g + n * F.b.x * (0.55 + 0.6 * (1.0 - luma(g)));
  }

  // film burn (rare): the frame bubbles and melts away from a hot spot
  if (F.e.z > 0.0) {
    let q = px - F.e.xy;
    let r = F.e.z * (0.8 + 0.4 * fbm(normalize(q + 0.001) * 3.0 + F.e.z * 0.01));
    let dd = length(q) - r;
    g = mix(g, vec3<f32>(1.0, 0.95, 0.8), 1.0 - smoothstep(-2.0, 2.0, dd));
    let rim = exp(-abs(dd) / 10.0);
    g = mix(g, vec3<f32>(0.9, 0.45, 0.1), rim * 0.8);
    g = mix(g, vec3<f32>(0.1, 0.05, 0.02), exp(-max(dd - 8.0, 0.0) / 6.0) * step(8.0, dd) * 0.6);
  }

  // iris (a circle closing on the subject), then fade
  if (F.d.z >= 0.0) {
    let dd = length(px - F.d.xy) - F.d.z;
    g = g * (1.0 - smoothstep(-1.5, 1.5, dd));
  }
  g = g * (1.0 - F.d.w);
  return vec4<f32>(clamp(g, vec3<f32>(0.0), vec3<f32>(1.0)), 1.0);
}

// BT.709 limited range. Y at full size; Cb/Cr averaged over 2x2 (NV12)
@group(1) @binding(5) var fin: texture_2d<f32>;

@fragment
fn fs_y(i: FOut) -> @location(0) vec4<f32> {
  let c = textureLoad(fin, vec2<i32>(i.pos.xy), 0).rgb;
  let y = (16.0 + 219.0 * dot(c, vec3<f32>(0.2126, 0.7152, 0.0722))) / 255.0;
  return vec4<f32>(y, 0.0, 0.0, 1.0);
}

@fragment
fn fs_uv(i: FOut) -> @location(0) vec4<f32> {
  let b = vec2<i32>(i.pos.xy) * 2;
  let c = (textureLoad(fin, b, 0).rgb + textureLoad(fin, b + vec2<i32>(1, 0), 0).rgb
         + textureLoad(fin, b + vec2<i32>(0, 1), 0).rgb + textureLoad(fin, b + vec2<i32>(1, 1), 0).rgb) * 0.25;
  let y = dot(c, vec3<f32>(0.2126, 0.7152, 0.0722));
  let cb = (128.0 + 224.0 * (c.b - y) / 1.8556) / 255.0;
  let cr = (128.0 + 224.0 * (c.r - y) / 1.5748) / 255.0;
  return vec4<f32>(cb, cr, 0.0, 1.0);
}
"""
