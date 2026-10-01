"""cropcircle: a first-person night at a farm festival, rendered on the GPU.

Builds the world, cast, crowd, events and camera plan once (deterministically from the seed and
the audio analysis), then renders any frame index on its own.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from ..config import get_path
from ..gpu import camera as C
from ..gpu import engine as E
from ..gpu import mesh as M
from . import cast, extras as X, music
from .crowd import DANCE, Crowd
from .director import Director, h01
from .events import Events
from .hud import HUD
from .parts import Ctx, Parts, hue, hue_np
from .world import DJ_POS, PLAT_TOP, World, path_x

M_PX = 0.045   # metres per sprite pixel

# time-of-day keyframes over the set: (pos, sky_top, sky_hor, amb_sky, amb_gnd, fog, key_col, key_int, stars, exposure)
TOD = [
    (0.00, (0.22, 0.36, 0.66), (1.00, 0.62, 0.36), (0.42, 0.40, 0.48), (0.26, 0.19, 0.12), (0.62, 0.48, 0.42), (1.0, 0.72, 0.48), 1.3, 0.0, 1.0),
    (0.05, (0.12, 0.16, 0.42), (1.00, 0.42, 0.26), (0.24, 0.20, 0.32), (0.14, 0.10, 0.08), (0.45, 0.28, 0.30), (1.0, 0.5, 0.3), 0.7, 0.0, 1.15),
    (0.11, (0.03, 0.05, 0.18), (0.26, 0.20, 0.45), (0.08, 0.09, 0.17), (0.04, 0.03, 0.03), (0.12, 0.10, 0.20), (0.5, 0.6, 0.9), 0.25, 0.6, 1.6),
    (0.20, (0.008, 0.012, 0.04), (0.05, 0.05, 0.11), (0.075, 0.085, 0.15), (0.03, 0.025, 0.03), (0.04, 0.04, 0.08), (0.55, 0.65, 1.0), 0.45, 1.0, 1.8),
    (0.84, (0.008, 0.012, 0.04), (0.05, 0.05, 0.11), (0.075, 0.085, 0.15), (0.03, 0.025, 0.03), (0.04, 0.04, 0.08), (0.55, 0.65, 1.0), 0.45, 1.0, 1.8),
    (0.91, (0.05, 0.06, 0.20), (0.52, 0.30, 0.46), (0.10, 0.09, 0.16), (0.05, 0.04, 0.04), (0.20, 0.14, 0.22), (0.7, 0.6, 0.8), 0.3, 0.4, 1.6),
    (0.96, (0.25, 0.36, 0.62), (1.00, 0.56, 0.40), (0.34, 0.32, 0.40), (0.20, 0.15, 0.11), (0.60, 0.45, 0.42), (1.0, 0.7, 0.5), 0.9, 0.0, 1.15),
    (1.00, (0.36, 0.52, 0.80), (1.00, 0.76, 0.52), (0.46, 0.45, 0.52), (0.28, 0.22, 0.16), (0.72, 0.62, 0.55), (1.0, 0.82, 0.62), 1.3, 0.0, 1.0),
]


def _tod(p: float):
    ks = [k[0] for k in TOD]
    i = int(np.clip(np.searchsorted(ks, p) - 1, 0, len(TOD) - 2))
    a, b = TOD[i], TOD[i + 1]
    f = (p - a[0]) / max(b[0] - a[0], 1e-6)
    f = f * f * (3 - 2 * f)
    lerp = lambda x, y: tuple(np.array(x) * (1 - f) + np.array(y) * f)  # noqa: E731
    return {"sky_top": lerp(a[1], b[1]), "sky_hor": lerp(a[2], b[2]), "amb_sky": lerp(a[3], b[3]),
            "amb_gnd": lerp(a[4], b[4]), "fog": lerp(a[5], b[5]), "key_col": lerp(a[6], b[6]),
            "key_int": a[7] * (1 - f) + b[7] * f, "stars": a[8] * (1 - f) + b[8] * f, "exposure": a[9] * (1 - f) + b[9] * f}


class CropScene:
    def __init__(self, cfg: dict, tl, an, rng: np.random.Generator, title: str, fingerprint: dict):
        self.cfg = cfg
        self.tl = tl
        self.an = an
        self.rng = rng
        self.fps = tl.fps
        self.dur = an.duration
        clip = cfg.get("_clip", {})
        self.clip_start = float(clip.get("start", 0.0))
        self.total = float(clip.get("total", self.clip_start + self.dur))
        self.W = int(get_path(cfg, "canvas.width", 640))
        self.H = int(get_path(cfg, "canvas.height", 360))
        self.ss = int(get_path(cfg, "canvas.ssaa", 2))
        ex = None
        if clip.get("extras"):
            p = Path(clip["extras"])
            if p.exists():
                z = np.load(p, allow_pickle=False)
                ex = {k: z[k] for k in z.files}
        self.extras = ex
        cfg["_key_pc"] = int(fingerprint.get("key_pc", 0))
        self.struct = music.build(an, ex, self.clip_start)
        self.bpm0 = float(tl.tempo)
        bpm = music.local_bpm(an.beats, tl.t, self.bpm0).astype(np.float64)
        ok = (bpm >= 60) & (bpm <= 220)
        if ok.any():   # hold the last sensible tempo through silence and fade-outs (pure function of the clip)
            idx = np.where(ok, np.arange(len(bpm)), 0)
            np.maximum.accumulate(idx, out=idx)
            first = int(np.argmax(ok))
            idx[:first] = first
            bpm = bpm[idx]
        self.bpm_frame = bpm
        self._wind()
        self._palettes(ex)
        el = cfg.get("elements", {})

        # cast and atlas
        crowd_cfg = el.get("crowd", {})
        n_cast = int(crowd_cfg.get("cast", 68))
        kinds = crowd_cfg.get("kinds") or {}
        specs = cast.make_cast(np.random.default_rng(rng.integers(1 << 31)), n_cast, kinds)
        if not any(s.kind == "creeper" for s in specs):
            specs[-1] = cast.random_spec(np.random.default_rng(7), "creeper")
        specials = cast.special_specs(np.random.default_rng(rng.integers(1 << 31)))
        self.atlas, self.tables = cast.build_atlas(specs, specials, np.random.default_rng(rng.integers(1 << 31)))
        self.rects = self.atlas.rects
        self.special = self.tables["special_index"]
        self.specs = self.tables["specs"]
        self.creeper_char = next(k for k, s in enumerate(specs) if s.kind == "creeper")
        self.scale = np.array([1.0 if s.kind != "anime" else 0.92 for s in self.specs]) * \
            np.random.default_rng(int(rng.integers(1 << 30))).uniform(0.92, 1.08, len(self.specs))

        # world, crowd, events, camera
        lib = E.MeshLibrary()
        tv, ti, self.tinfo = M.terrain(flat_r=115.0)
        lib.add("terrain", tv, ti)
        lib.add("box", *M.box())
        lib.add("cyl", *M.cylinder(12))
        lib.add("cyl6", *M.cylinder(6))
        lib.add("ico", *M.icosphere(1))
        lib.add("ico2", *M.icosphere(2, flat=False))
        lib.add("bell", *M.bell())
        lib.add("flag", *M.plane_xy(8, 4))
        lib.add("quad", *M.plane_xy_centered())
        lib.add("pennant", *M.pennant())
        lib.add("prism", *M.prism())
        lib.add("corn", *M.corn())
        lib.add("corn_lo", *M.corn(lod=1))
        self.world = World(np.random.default_rng(rng.integers(1 << 31)), cfg, self.clip_start, self.total, self.struct, self.tinfo)
        self.world._wind_fn = self.swing_at
        self.world.char_cb = self.char_sprite
        self.world.n_cast = n_cast
        n_people = int(crowd_cfg.get("count", 110))
        self.crowd = Crowd(np.random.default_rng(rng.integers(1 << 31)), n_people, n_cast, self.clip_start, self.dur,
                           self.total, self.struct, crowd_cfg.get("styles"))
        self.director = Director(np.random.default_rng(rng.integers(1 << 31)), self.struct, self.dur, self.world,
                                 self._pick_agent, cfg.get("camera", {}))
        self.events = Events(self, np.random.default_rng(rng.integers(1 << 31)))
        for e in self.events.ev:
            if e.kind == "ufo" and e.t1 - e.t0 > 10:
                tx, tz = e.p.get("target", (0.0, 50.0))
                self.director.force(max(0.0, e.t0 + 4), min(self.dur, e.t0 + 10), "ufo",
                                    pos=(tx * 0.25, 1.6, 12.0), target=(tx, 18.0, tz))
        for (t0, t1, cpos, tgt, fov, ev_end) in self.events.features():
            L = t1 - t0
            for _ in range(3):   # if another framed shot is in the way, try again just after it
                if self.director.force(max(0.0, t0), min(self.dur, t0 + L), "look", pos=cpos, target=tgt, fov=fov):
                    break
                clash = [f[1] for f in self.director.forced if f[0] < t0 + L and t0 < f[1]]
                t0 = max(clash) if clash else t0 + L
                if t0 + 3.0 > ev_end:
                    break
        self.director.plan()
        self.hud = HUD(self.W, self.H, self.rects, ex, self.clip_start, self.total, self.struct, el.get("hud", {}))

        self.engine = E.Engine(self.W, self.H, self.ss, self.atlas.img, self.world.crop.img, lib)
        self.engine.set_crop_params(self.world.crop.params, self.world.crop.rect)
        for name, rows in self.world.static.items():
            self.engine.add_static(name, np.array(rows))
        self.engine.add_static("corn", self.world.corn)
        self.engine.add_static("corn_lo", self.world.corn_far)
        self.u = C.Uniforms(E.FRAME_FLOATS)
        self.moon_az = float(rng.uniform(-0.8, 0.8))
        self.moon_phase = float(rng.uniform(0.3, 0.7))
        self.aurora = float(rng.random() < float(get_path(cfg, "sky.aurora_chance", 0.45)))
        self.clouds = float(rng.uniform(0.0, 0.5))
        self.sun_az = float(rng.uniform(-0.4, 0.4))

    # ---------------------------------------------------------------- precomputed signals
    def _wind(self):
        tl = self.tl
        n = tl.n
        t = tl.t
        T = t + self.clip_start
        kick = np.zeros(n, bool)
        db = self.struct.downbeats
        if len(db):
            bi = np.clip(np.searchsorted(db, t, side="right") - 1, 0, len(db) - 1)
            kick = self.struct.bar_kick[bi].astype(bool)
        self.kick = kick
        base = 0.35 + 0.15 * np.sin(T / 37.0) + 0.1 * np.sin(T / 11.0)
        gust = 0.65 * tl.env["beat"] * (0.4 + tl.env["bass"]) * kick + 0.25 * tl.env["lowmid"]
        ws = (base + gust).astype(np.float64)
        self.ws = ws
        from ..timeline import _attack_release
        self.ws_swing = _attack_release(ws, self.fps, 0.02, 0.15)
        self.wphase = np.cumsum(ws) / self.fps * 2.2
        self.wdir = 0.6 + 0.35 * np.sin(T / 300.0)

    def wind_at(self, t):
        return np.interp(np.asarray(t) * self.fps, np.arange(len(self.ws)), self.ws)

    def swing_at(self, t):
        """Wind as the hanging jellyfish feel it: the beat's gusts, smoothed by their inertia."""
        return np.interp(np.asarray(t) * self.fps, np.arange(len(self.ws_swing)), self.ws_swing)

    def _palettes(self, ex):
        """Accent colours follow the music's key on the Camelot wheel, offset per set."""
        off = float(self.rng.random())
        st = self.struct
        secs = list(self.an.sections) + [self.dur]
        self.sec_hue = []
        for a in secs[:-1]:
            hb = off
            if ex is not None and len(ex.get("key_t", [])):
                k = int(np.clip(np.searchsorted(ex["key_t"], a + self.clip_start + 4) - 1, 0, len(ex["key_code"]) - 1))
                code = str(ex["key_code"][k])
                if code[:-1].isdigit():
                    hb = (int(code[:-1]) - 1) / 12.0 + off * 0.25 + (0.04 if code.endswith("B") else 0)
            self.sec_hue.append(hb % 1.0)
        _ = st

    # ---------------------------------------------------------------- helpers for events and crowd
    def _pick_agent(self, t):
        tl = self.tl
        i = int(np.clip(t * self.fps, 0, tl.n - 1))
        S = self.crowd.state(t, int(tl.beat_idx[i]), float(tl.beat_phase[i]), int(tl.bar_idx[i]), 0.6)
        ok = np.nonzero(S["vis"] & (S["kind"] == DANCE) & ~S["walking"])[0]
        if not len(ok):
            return None
        d = np.hypot(S["x"][ok], S["z"][ok] + 4)
        k = ok[int(np.argmin(d + np.array([h01(q, int(t)) * 6 for q in ok])))]
        return (int(k), float(S["x"][k]), float(S["z"][k]))

    def cast_for(self, seed: int) -> int:
        return int(h01(seed, 77) * self.tables["n_cast"]) % self.tables["n_cast"]

    def char_sprite(self, P: Parts, ci: int, pose: str, pos, face=(0.0, 1.0), y=0.0, scale=1.0, roll=0.0, flash=0.0):
        cp, cr = self._cam_pos, self._cam_right
        pi = cast.POSE_INDEX[pose]
        v = np.array([pos[0] - cp[0], pos[2] - cp[2]])
        v /= np.linalg.norm(v) + 1e-9
        f = np.array(face, float)
        f /= np.linalg.norm(f) + 1e-9
        back = float(f @ v) > 0.25
        uv = self.tables["char_uv"][ci, 1 if back else 0, pi]
        s = self.scale[ci] * scale
        P.sprite((pos[0], pos[1] + y, pos[2]), 32 * M_PX * s, 48 * M_PX * s, tuple(uv), roll=roll, flash=flash)
        P.shadow(pos[0], pos[2], 0.9 * s, 0.45 * s, 0.45, y=pos[1] + 0.02)

    # ---------------------------------------------------------------- frame
    def ctx(self, i: int) -> Ctx:
        tl = self.tl
        t = float(tl.t[i])
        T = self.clip_start + t
        env = {k: float(v[i]) for k, v in tl.env.items()}
        db = self.struct.downbeats
        bi = int(tl.bar_idx[i]) if tl.bar_idx[i] >= 0 else 0
        bar_len = 4 * 60 / max(self.bpm0, 60)
        prev_db = db[bi] if len(db) and bi < len(db) else 0.0
        bar_frac = float(np.clip((t - prev_db) / bar_len, 0, 0.999))
        sec = int(tl.section_idx[i])
        hb = self.sec_hue[min(sec, len(self.sec_hue) - 1)]
        acc = [hue(hb + d, 0.85, 1.0) for d in (0.0, 0.33, 0.5, 0.78)]
        p = T / max(self.total, 1e-6)
        night = 1.0 - min(1.0, max(0.0, (0.11 - p) / 0.08)) - min(1.0, max(0.0, (p - 0.9) / 0.07))
        return Ctx(i=i, t=t, T=T, env=env, beat_phase=float(tl.beat_phase[i]), beat_idx=int(tl.beat_idx[i]),
                   bar_idx=bi, bar_frac=bar_frac, bar_env=float(tl.bar_env[i]), energy=float(tl.section_energy[i]),
                   kick=bool(self.kick[i]), bpm=float(self.bpm_frame[i]), tod=p,
                   wind=(math.cos(self.wdir[i]), math.sin(self.wdir[i]), float(self.ws[i]), float(self.wphase[i])),
                   accents=acc, section=sec, night=max(0.0, night))

    def render(self, i: int) -> memoryview:
        c = self.ctx(i)
        c.events = self.events.active(c.t)
        pos, yaw, pitch, roll, fov, shot = self.director.camera(c)
        u = self.u
        VP, right, up, fwd = u.camera(pos, yaw, pitch, roll, fov, self.W / self.H)
        self._cam_pos, self._cam_right, self._cam_yaw = pos, right, yaw
        c.cam_pos, c.cam_right = pos, right
        P = Parts()
        self.world.frame(c, P, self.rects)
        self._rings(c, P, shot)
        self._crowd(c, P, shot)
        self._stage_people(c, P)
        self.events.frame(c, P, self.rects)
        post_fx = self.events.post(c)
        self._uniforms(c, P, post_fx)
        post = self._post(c, post_fx)
        hud = self._hud(c)
        fd = E.FrameData(u.a.copy(), post, P.mesh_arrays(), P.jelly_arrays(), P.sprite_array(), P.shadow_array(),
                         P.glow_array(), hud)
        return self.engine.render(fd)

    def _crowd(self, c: Ctx, P: Parts, shot):
        S = self.crowd.state(c.t, c.beat_idx, c.beat_phase, c.bar_idx, c.energy)
        if c.T >= self.events.alien_from and self.crowd.n > 3:
            pass
        S = self.events.crowd(c, S)
        if shot.kind == "orbit" and shot.p.get("agent", -1) >= 0:
            k = shot.p["agent"]
            S["vis"][k] = True
            S["pose"][k] = cast.POSE_INDEX["jump"]
            S["y"][k] = 0.7
            S["walking"][k] = False
        vis = np.nonzero(S["vis"])[0]
        if not len(vis):
            return
        cp, cr = self._cam_pos, self._cam_right
        x, z, y = S["x"][vis].copy(), S["z"][vis].copy(), S["y"][vis]
        if shot.kind in ("djzoom", "stage", "car"):   # keep the line of sight to the stage clear-ish
            fwd2 = np.array([-math.sin(self._cam_yaw), -math.cos(self._cam_yaw)])
            dx, dz = x - cp[0], z - cp[2]
            along = dx * fwd2[0] + dz * fwd2[1]
            lat = -dx * fwd2[1] + dz * fwd2[0]
            block = (along > 0) & (along < 5.0) & (np.abs(lat) < 1.1)
            push = np.where(lat >= 0, 1.1 - lat, -1.1 - lat) * block
            x, z = x + -fwd2[1] * push, z + fwd2[0] * push
        if cp[1] < 3.0:   # people step aside for the camera
            dx, dz = x - cp[0], z - cp[2]
            r = np.hypot(dx, dz)
            near = r < 1.6
            k = np.where(near, 1.6 / np.maximum(r, 1e-3), 1.0)
            x, z = cp[0] + dx * k, cp[2] + dz * k
        chars = self.crowd.char[vis]
        if c.T >= self.events.alien_from:
            chars = np.where(vis == 3, self.special["alien"], chars)
        pose = S["pose"][vis].copy()
        face = S["face"][vis]
        v = np.stack([x - cp[0], z - cp[2]], 1)
        v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-9
        d = (face * v).sum(1)
        walking = S["walking"][vis]
        side = walking & (np.abs(d) < 0.6)
        r2 = np.array([cr[0], cr[2]])
        r2 /= np.linalg.norm(r2) + 1e-9
        flip = (face @ r2) < 0
        walk0 = cast.POSE_INDEX["walk_1"]
        side0 = cast.POSE_INDEX["side_1"]
        pose = np.where(side, side0 + (pose - walk0) % 4, pose)
        back = (d > 0.25) & ~side
        uv = self.tables["char_uv"][chars, back.astype(int), pose].copy()
        uv[side & flip] = uv[side & flip][:, [2, 1, 0, 3]]
        s = self.scale[chars]
        n = len(vis)
        rows = np.zeros((n, 16), np.float32)
        rows[:, 0], rows[:, 1], rows[:, 2] = x, y, z
        rows[:, 3] = S["roll"][vis]
        rows[:, 4] = 32 * M_PX * s
        rows[:, 5] = 48 * M_PX * s
        rows[:, 6] = np.where(np.abs(S["roll"][vis]) > 0.01, 0.45, 0.0)
        rows[:, 8:12] = uv
        rows[:, 12:15] = 1.0
        rows[:, 15] = S["flash"][vis]
        P.sprites_many(rows)
        sh = np.zeros((n, 16), np.float32)
        sh[:, 0], sh[:, 1], sh[:, 2] = x, 0.02, z
        sh[:, 4], sh[:, 5], sh[:, 6], sh[:, 7] = 0.9 * s, 0.45 * s, 0.5, 1
        sh[:, 15] = 0.5 * np.clip(1 - y, 0.2, 1)
        P.shadows.append(sh)
        # flags carried by the crowd, emotes and phone torches
        hand = self.tables["hand"]
        for j, k in enumerate(vis):
            if S["flag"][k] or S["emote"][k]:
                ci, pi_, b = chars[j], pose[j], int(back[j])
                hx, hy = hand[ci, b, pi_]
                tv = np.array([cp[0] - x[j], 0, cp[2] - z[j]])
                tv /= np.linalg.norm(tv) + 1e-9
                rv = np.cross([0, 1, 0], tv)
                rv /= np.linalg.norm(rv) + 1e-9
                hpos = np.array([x[j], y[j], z[j]]) + rv * (hx - 15.5) * M_PX * s[j] + np.array([0, (47 - hy) * M_PX * s[j], 0])
                if S["flag"][k]:
                    name = cast.PRIDE_FLAGS[int(h01(k, 5) * len(cast.PRIDE_FLAGS))]
                    P.m("box", C_box(hpos - [0, 0.5, 0], 0.03, 1.9), (0.85, 0.85, 0.85), 8)
                    yaw_f = math.atan2(c.wind[0], c.wind[1]) - math.pi / 2
                    P.m("flag", _affine((hpos[0], hpos[1] + 0.75, hpos[2]), (0.95, 0.6, 1), yaw_f), (1, 1, 1), 1,
                        sway=1.2, extra=self.rects[f"flag_{name}"])
                em = S["emote"][k]
                if em == "torch":
                    P.dot(hpos + [0, 0.12, 0], 0.18, (1.6, 1.5, 1.2), soft=3.0)
                elif em in ("bang", "sweat"):
                    hp = np.array([x[j], y[j] + 2.0 * s[j], z[j]]) + rv * 0.35
                    P.sprite(tuple(hp), 0.22 if em == "bang" else 0.2, 0.42 if em == "bang" else 0.3, self.rects[em], anchor=0.0)

    def _rings(self, c: Ctx, P: Parts, shot):
        """Golden rings float along the corn path; walking through them collects them."""
        zs = np.arange(24.0, 84.0, 3.5)
        cam_z = self._cam_pos[2]
        corn = shot.kind == "corn"
        spin = int(c.t * 10) % 4
        for z in zs:
            x = float(path_x(z))
            y = 1.25 + 0.12 * math.sin(z + c.t * 2)
            if corn and z > cam_z:
                if z - cam_z < 1.2:   # just collected: a sparkle
                    k = int((z - cam_z) / 0.4)
                    P.sprite((x, y, z), 0.5, 0.5, self.rects[f"sparkle{min(2, k)}"], anchor=0.5)
                continue
            P.sprite((x, y, z), 0.45, 0.45, self.rects[f"ring{spin}"], anchor=0.5)

    def _stage_people(self, c: Ctx, P: Parts):
        dj = self.special["dj"]
        st = self.struct
        scratch = False
        for s in st.sounds:
            if s.label == "disc_scratching" and s.t0 <= c.t < s.t1 and s.peak > 0.75:
                scratch = True
                break
        drop = any(e.kind == "drop" and c.t - e.t0 < 3.0 for e in c.events)
        build = any(e.kind == "build" for e in c.events)
        if drop:
            pose = "hands_up" if c.beat_idx % 2 else "pump_up"
        elif build:
            pose = "point" if c.beat_phase < 0.5 else "pump_dn"
        elif scratch:
            pose = "pump_dn" if (c.beat_idx * 2 + (c.beat_phase > 0.5)) % 2 else "robot_b"
        elif not c.kick:
            pose = ["bounce_dn", "bounce_up", "wave", "bounce_up"][c.beat_idx % 4] if c.bar_idx % 4 == 3 else ("bounce_dn" if c.beat_phase < 0.35 else "idle")
        else:
            seq = ["bounce_dn", "bounce_up", "bounce_dn", "pump_up"] if c.energy > 0.6 else ["bounce_dn", "bounce_up"]
            pose = seq[c.beat_idx % len(seq)] if c.beat_phase < 0.5 else "bounce_up"
        self.char_sprite(P, dj, pose, tuple(DJ_POS), face=(0, 1), scale=1.12)
        # a vocalist steps up when the classifier hears singing or rapping
        voc = float(np.max(st.vocal_at(np.array([c.t - 1.0, c.t, c.t + 1.0])))) if st.vocal_t is not None else 0.0
        if voc > 0.55:
            ci = self.cast_for(c.section * 13 + 5)
            pose = "sing" if c.beat_idx % 4 != 3 else ("point" if c.bar_idx % 2 else "wave")
            self.char_sprite(P, ci, pose, (-2.6, PLAT_TOP, -15.2), face=(0.2, 1))
            if c.beat_phase < 0.1:
                pass
            a = (c.t * 0.6) % 1.0
            P.dot((-2.4 + a * 0.6, PLAT_TOP + 2.0 + a * 1.5, -15.2), 0.16, (1.2 * (1 - a),) * 3, mode=2, uv=self.rects["note"])

    def _uniforms(self, c: Ctx, P: Parts, fx: dict):
        u = self.u
        td = _tod(c.tod)
        self._exposure = td["exposure"]
        p = c.tod
        # sun sets in the west at the start and rises in the east at the end
        if p < 0.5:
            el = math.radians(9 - 160 * p)
            az = math.pi / 2 + self.sun_az
        else:
            el = math.radians(-160 * (1 - p) + 9)
            az = -math.pi / 2 + self.sun_az
        sun = np.array([-math.sin(az) * math.cos(el), math.sin(el), -math.cos(az) * math.cos(el)])
        mel = math.radians(18 + 30 * math.sin(math.pi * min(1, max(0, (p - 0.08) / 0.9))))
        moon = np.array([math.sin(self.moon_az) * math.cos(mel), math.sin(mel), -math.cos(self.moon_az) * math.cos(mel)])
        sun_vis = max(0.0, min(1.0, (el + 0.05) / 0.12))
        key_dir = sun if sun_vis > 0.3 else moon
        u.set("key_dir", *key_dir, td["key_int"])
        u.set("key_col", *td["key_col"], td["stars"])
        u.set("sky_top", *td["sky_top"], self.moon_phase)
        aur = self.aurora * c.night * float(get_path(self.cfg, "sky.aurora", 0.6))
        u.set("sky_hor", *td["sky_hor"], aur)
        u.set("amb_sky", *td["amb_sky"], float(get_path(self.cfg, "sky.fog", 0.012)))
        u.set("amb_gnd", *td["amb_gnd"], 0.12)
        u.set("fog_col", *td["fog"], self.clouds)
        u.set("wind", c.wind[0], c.wind[1], c.wind[2], c.wind[3])
        e = c.env
        u.set("audio", e["sub"], e["bass"], e["lowmid"], e["highmid"])
        u.set("audio2", e["high"], e["onset"], e["loudness"], e["beat"])
        u.set("beat", c.beat_phase, c.bar_frac, float(c.beat_idx), c.bar_env)
        u.set("misc", c.energy, self.sec_hue[min(c.section, len(self.sec_hue) - 1)], h01(c.section) , c.tod)
        u.set("res", self.W * self.ss, self.H * self.ss, 1 / (self.W * self.ss), 1 / (self.H * self.ss))
        u.set("sun_sky", *sun, sun_vis)
        u.set("moon_sky", *moon, (1 - sun_vis) * 1.0)
        u.a[C.OFF["cam_fwd"] + 3] = fx.get("psy", 0.0)
        u.a[C.OFF["cam_pos"] + 3] = c.t
        L = P.lights[:24]
        u.lights(np.array(L) if L else np.zeros((0, 16)))
        u.a[C.OFF["nl"] + 1] = c.T
        u.a[C.OFF["nl"] + 2] = sun_vis

    def _post(self, c: Ctx, fx: dict) -> np.ndarray:
        post = np.zeros(E.POST_FLOATS, np.float32)
        hb = self.sec_hue[min(c.section, len(self.sec_hue) - 1)]
        tint = np.array(hue(hb, 0.6, 1.0))
        exp_ = self._exposure * float(get_path(self.cfg, "canvas.exposure", 1.0))
        if self.clip_start < 0.5:          # fade in from black at the start of the set
            exp_ *= min(1.0, c.t / 1.5) ** 2
        if self.clip_start + self.dur >= self.total - 0.5:   # and out at the very end
            exp_ *= min(1.0, max(0.0, (self.total - c.T) / 2.5)) ** 2
        post[0:4] = (exp_, float(get_path(self.cfg, "canvas.bloom", 0.85)), 1.12, 1.06)
        post[4:7] = tint * 0.035
        post[7] = 0.55
        post[8:11] = 1.0 - (1 - tint) * 0.06
        post[11] = float(get_path(self.cfg, "canvas.grain", 0.025))
        post[12] = fx.get("ca", 0.0)
        post[13] = fx.get("invert", 0.0)
        post[14] = fx.get("filter", 0)
        post[15] = fx.get("filter_amt", 0.0)
        post[16] = c.t
        post[17] = float(get_path(self.cfg, "canvas.color_levels", 31))
        post[19] = fx.get("hue", 0.0)
        post[20:23] = (self.W, self.H, self.ss)
        post[24:26] = (0.8, 0.6)
        post[26] = fx.get("speed", 0.0)
        return post

    def _hud(self, c: Ctx) -> np.ndarray:
        st = self.struct
        db = st.downbeats
        bar_no = c.bar_idx + 1
        beats_since = int(np.searchsorted(st.beats, c.t, side="right")) - int(np.searchsorted(st.beats, db[c.bar_idx] - 0.01)) if len(db) else 0
        ph_i = int(np.searchsorted(st.phrases, c.t, side="right")) - 1
        ph_start = st.phrases[max(ph_i, 0)]
        bar_in_phrase = int(np.searchsorted(db, c.t, side="right")) - int(np.searchsorted(db, ph_start - 0.01))
        fade = min(1.0, max(0.0, (c.t - 1.0) / 2.0)) if self.clip_start < 1 else 1.0
        return self.hud.build(c, c.bpm, bar_no, max(1, min(4, beats_since)), (ph_i + 1, max(1, bar_in_phrase)), c.env, c.kick,
                              self.events.konami(c), fade)


def C_box(base, w, h):
    return M.affine(tuple(base), (w, h, w))


def _affine(t, s, yaw):
    return M.affine(t, s, (0, yaw, 0))
