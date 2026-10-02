"""rubberhose: a 1930s rubber-hose cartoon boss rush, drawn on the GPU as ink-and-paint distance
fields and shot through a 24 fps film look. Frames are pure functions of their index and of the
whole set's analysis, so a slice renders exactly the frames the full render would."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np

from .. import analysis
from ..crop import music as cmusic
from ..timeline import _attack_release
from . import bosses, gags, heroes, rig, shows, stages, story
from .ctx import Ctx
from .engine import Engine
from .ink import GLOW, INK, Ink, rgb
from .story import h01

W, H = 1920.0, 1080.0
FILM_N = 4 * 38
NAMES = {"pepper": "PEPPER", "loaf": "PUMPERNICKEL", "salt": "SALTY", "bulb": "SPARKY", "sugar": "SUGAR"}
GRADES = {"warm": 0.0, "twostrip": 1.0, "mono": 2.0, "clean": 3.0}


class HoseScene:
    pix_fmt = "nv12"

    def __init__(self, cfg: dict, tl, an_slice, rng, title: str, fingerprint: dict):
        clip = cfg["_clip"]
        self.cfg = cfg
        self.fps = float(tl.fps)
        self.start = float(clip["start"])
        self.title = title
        full = analysis.load(Path(clip["analysis"]))
        ex = None
        if clip.get("extras") and Path(clip["extras"]).exists():
            z = np.load(clip["extras"], allow_pickle=True)
            ex = {k: z[k] for k in z.files}
        st = cmusic.build(full, ex, 0.0)
        self.m = story.Music(full, st)
        self.seed = int(rng.integers(1 << 30))
        r2 = np.random.default_rng(self.seed)
        self.cast = heroes.cast_from_title(title, r2)
        self.names = [self._name(k) for k in self.cast]
        want = cfg.get("bosses") or [b["name"] for b in bosses.ROSTER]
        roster = [bosses.BY_NAME[n] for n in want if n in bosses.BY_NAME] or bosses.ROSTER
        self.P = story.plan(self.m, st, r2, roster, cfg.get("story", {}) or {}, st.sounds)
        self.fights: dict[int, story.Fight] = {}
        self.vocal = st
        # smoothed band envelopes for the whole set, one value per video frame
        n = int(math.ceil(full.duration * self.fps)) + 2
        tt = (np.arange(n) + 0.5) / self.fps
        sm = cfg.get("smoothing", {}) or {}
        self.env = {}
        for k in ("sub", "bass", "lowmid", "highmid", "high"):
            a, r = sm.get(k, [0.01, 0.15])
            self.env[k] = _attack_release(full.at(full.bands.get(k, full.loudness), tt).astype(np.float64),
                                          self.fps, a, r).astype(np.float32)
        a, r = sm.get("loudness", [0.2, 0.8])
        self.env["loud"] = _attack_release(full.at(full.loudness, tt).astype(np.float64), self.fps, a, r).astype(np.float32)
        self.bpm = cmusic.local_bpm(self.m.beats, tt[:: int(self.fps)], full.tempo)
        film = cfg.get("film", {}) or {}
        self.grade = GRADES.get(str(film.get("grade", "warm")), 0.0)
        self.grain = float(film.get("grain", 0.045))
        self.dirt = float(film.get("dirt", 1.0))
        self.vignette = float(film.get("vignette", 0.42))
        self.kick_pump = float(film.get("kick_pump", 0.07))
        self.boil = float(cfg.get("boil", 1.0))
        self.hud_on = bool((cfg.get("hud", {}) or {}).get("enabled", True))
        self.size = (int(clip.get("width", 1920)), int(clip.get("height", 1080)))
        self.engine = Engine(*self.size)
        self._transitions()

    def _name(self, kind: str) -> str:
        words = [w for w in self.title.replace("&", " ").replace("-", " ").split() if w]
        for w in words:
            if any(k in w.lower() for k in heroes.KINDS[kind]["words"]):
                return w.upper()
        return NAMES[kind]

    def _fight(self, a: story.Act) -> story.Fight:
        if a.k not in self.fights:
            b = bosses.BY_NAME[a.boss]
            self.fights[a.k] = story.Fight(self.m, self.P, a, b, self.seed + a.k * 7919,
                                           self.cfg.get("story", {}) or {})
        return self.fights[a.k]

    def _transitions(self):
        """Iris cuts: (cut time, close seconds, open seconds, close centre, open centre)."""
        m, P = self.m, self.P
        bar = 4 * m.period
        tr = [(P.intro[1], bar * 1.0, bar * 0.75, (W / 2, 420), (420, 760))]
        for a in P.acts[1:]:
            tr.append((a.t0, bar * 1.0, bar * 0.75, (1300, 420), (420, 760)))
        for it in P.inters:
            tr.append((it.t0, bar * 0.5, bar * 0.5, (420, 760), (W / 2, 540)))
        tr.append((P.outro[0], bar * 1.0, bar * 0.75, (1300, 420), (W / 2, 420)))
        self.trans = sorted(tr)

    # ------------------------------------------------------------------ clocks
    def ctx(self, t: float) -> Ctx:
        m = self.m
        # a beat shows on the frame whose display interval contains it
        bp = m.beat_pos(t + 1.0 / self.fps - 1e-6)
        k = math.floor(bp)
        tb = m.beat_time(k)
        step = math.floor(max(0.0, t - tb) * 24 + 1e-6)
        td = tb + step / 24.0
        fi = int(min(max(0, round(t * self.fps)), len(self.env["sub"]) - 1))
        bar_i = m.bar_at(t)
        kick_bar = bool(m.st.bar_kick[min(bar_i, len(m.st.bar_kick) - 1)]) if len(m.st.bar_kick) else True
        en = float(m.st.bar_energy[min(bar_i, len(m.st.bar_energy) - 1)]) if len(m.st.bar_energy) else 0.5
        kick = math.exp(-max(0.0, t - tb) / 0.12) if kick_bar else 0.15 * math.exp(-max(0.0, t - tb) / 0.12)
        c = Ctx(t=t, td=td, beat=m.beat_pos(td), bar=m.bar_pos(td), sub=float(self.env["sub"][fi]),
                bass=float(self.env["bass"][fi]), lowmid=float(self.env["lowmid"][fi]),
                highmid=float(self.env["highmid"][fi]), high=float(self.env["high"][fi]),
                loud=float(self.env["loud"][fi]), kick=kick, energy=en, drawing=int(k * 64 + step))
        c.seed = self.seed % 1000
        return c

    def hero_pose(self, c: Ctx, k: int, action: str, **kw) -> heroes.Pose:
        p = heroes.Pose(t=c.td, beat=c.beat + 0.5 * k * 0, energy=c.energy, style=(int(c.bar / 8) + k) % 4,
                        blink=1.0 if (c.td + k * 1.3) % 3.7 < 0.1 else 0.0, look=(0.6, 0.0))
        p.mouth = 0.35 + 0.45 * c.squash * c.energy
        if action == "walk":
            p.run = (c.beat * 0.5) % 1.0
            p.action = "walk"
        elif action == "sing":
            p.action = "dance"
            p.style = 2
            p.mouth = 0.4 + 0.6 * c.squash
        elif action == "softshoe":
            p.action = "dance"
            p.style = 1
            p.hat = True
            p.cane = True
            p.facing = 1.0 if int(c.bar / 2 + k) % 2 == 0 else -1.0
        else:
            p.action = action
        for key, v in kw.items():
            setattr(p, key, v)
        return p

    # ------------------------------------------------------------------ frames
    def frame(self, i: int) -> bytes:
        prims, clock, film = self.build(self.start + i / self.fps)
        return self.engine.render(prims, clock, film, out="nv12")

    def frame_rgba(self, i: int) -> bytes:
        prims, clock, film = self.build(self.start + i / self.fps)
        return self.engine.render(prims, clock, film, out="rgba")

    def build(self, t: float):
        c = self.ctx(t)
        ink = Ink(boil=self.boil)
        P = self.P
        mode = "fight"
        if t < P.intro[1]:
            mode = "intro"
        elif t >= P.outro[0]:
            mode = "outro"
        elif story.inter_at(P, t):
            mode = "inter"
        flash = 0.0
        if mode == "intro":
            shows.title_card(ink, c, self.title, self.cast, self.names, t / max(P.intro[1], 1e-3),
                             lambda k, a: self.hero_pose(c, k, a, facing=1.0 if k == 0 else -1.0))
        elif mode == "outro":
            shows.end_card(ink, c, self.cast, lambda k, a: self.hero_pose(c, k, a))
        elif mode == "inter":
            it = story.inter_at(P, t)
            u = (t - it.t0) / max(it.t1 - it.t0, 1e-3)
            hp = lambda k, a: self.hero_pose(c, k, a)  # noqa: E731
            if it.kind == "map":
                shows.map_screen(ink, c, u, self.cast, hp, [], it.act)
            elif it.kind == "singalong":
                shows.singalong(ink, c, u, self.cast, hp, float(self.vocal.vocal_at(t)))
            else:
                bar = 4 * self.m.period
                xs = [W / 2 - 260 + 120 * math.sin(c.bar * math.pi / 4), W / 2 + 260 + 120 * math.sin(c.bar * math.pi / 4)]
                _ = bar
                shows.vaudeville(ink, c, u, self.cast, hp, xs)
            self._gags(ink, c, t, None)
        else:
            flash = self._fight_frame(ink, c, t)
        # lettering cards over everything
        for card in P.cards:
            if card.t0 <= t < card.t1:
                u = (t - card.t0) / max(card.t1 - card.t0, 1e-3)
                sub = None
                if card.kind == "ready":
                    a = story.act_at(P, t)
                    sub = f"ROUND {a.k + 1}: {bosses.BY_NAME[a.boss]['title']}"
                shows.card_text(ink, c, card.text, card.kind, u, sub)
        return ink.array(), (float(c.drawing), t, -2.2, 0.0), self._film(c, t, flash)

    def _fight_frame(self, ink: Ink, c: Ctx, t: float) -> float:
        m, P = self.m, self.P
        a = story.act_at(P, t)
        F = self._fight(a)
        b = bosses.BY_NAME[a.boss]
        stage = stages.STAGES[a.stage]
        bar = 4 * m.period
        c.phase = story.phase_of(a, t)
        c.phase_t = t - a.phases[c.phase] if a.phases else 99.0
        c.ko = (t - a.ko) / max(a.t1 - a.ko, 1e-3) if t >= a.ko else -1.0
        c.intro = min(1.0, (t - a.t0) / max(a.go - a.t0, 1e-3))
        c.sky = a.sky
        c.variant = a.variant
        c.hue = (0.12 * a.variant) % 1.0
        sh = F.active_shots(t)
        recent = [s.ts for s in F.shots if s.ts <= t and t - s.ts < 2.0] if not sh else [s.ts for s in sh]
        c.shot = t - max(recent) if recent else 9.0
        sup = F.super_at(t)
        c.sup = (t - sup) / F.super_dur if sup is not None else -1.0
        bl = F.active_bullets(t)
        hits = [ts + 0.42 for ts, _ in bl if ts + 0.42 <= t]
        c.hurt = 0.55 * math.exp(-(t - max(hits)) / 0.05) if hits else 0.0
        if c.sup >= 0:
            c.hurt = max(c.hurt, 0.7 * (0.5 + 0.5 * math.sin(t * 50)))
        bld = m.st.in_segment(m.st.builds, t)
        c.build = (t - bld.t0) / max(bld.t1 - bld.t0, 1e-3) if bld else 0.0
        laughing = any(g.kind == "laugh" and g.t0 <= t < g.t1 for g in P.gags)

        # camera: punch-in on the kick, shake on supers and drops
        z = 1.0 + 0.016 * c.kick * (0.4 + c.energy)
        sx = sy = 0.0
        if c.sup >= 0 and c.sup < 0.6:
            sx = (h01("sx", c.drawing) - 0.5) * 24
            sy = (h01("sy", c.drawing) - 0.5) * 18
        if c.build > 0.5:
            sx += (h01("bx", c.drawing) - 0.5) * 10 * (c.build - 0.5)
        flash = 0.0
        for card in P.cards:
            if card.kind in ("go", "word") and 0 <= t - card.t0 < 0.25:
                flash = max(flash, 1 - (t - card.t0) / 0.25)
                sy += (h01("dy", c.drawing) - 0.5) * 20 * flash

        with ink.at(W / 2 + sx, H / 2 + sy, 0.0, z):
            with ink.at(-W / 2, -H / 2):
                stage(ink, c, "back")
                # boss: rises in during READY?, sinks after the knockout
                ent = 1 - (1 - c.intro) ** 3
                by_off = (1 - ent) * 700
                if c.ko > 0.55:
                    by_off += ((c.ko - 0.55) / 0.45) ** 2 * 900
                bc = Ctx(**{**c.__dict__})
                if laughing:
                    bc.shot = 0.0
                with ink.at(0, by_off):
                    kw = {}
                    if a.boss in ("organ", "jukebox"):
                        kw["bands"] = (c.sub, c.bass, c.lowmid, c.highmid, c.high)
                    b["draw"](ink, bc, **kw)
                    if c.ko >= 0:
                        for j in range(4):
                            q = (c.ko * 6 + j / 4) % 1.0
                            rig.impact(ink, 1200 + 400 * h01("kx", j, int(c.ko * 6)), 250 + 400 * h01("ky", j, int(c.ko * 6)),
                                       90, q)
                if laughing:
                    gags.laugh(ink, c, None, 0.5, 1250, 160)
                # boss shots
                for s in sh:
                    tt = t - s.ts
                    x, y = F.shot_xy(s, tt)
                    if s.kind == "ring":
                        bosses.ring_wave(ink, x, y, min(1.0, tt / s.life))
                        continue
                    if s.end == "parry" and tt > s.life - 0.12:
                        rig.impact(ink, x, y, 70, (tt - (s.life - 0.12)) / 0.12, col=rgb("ffb3d6"))
                        continue
                    vx, vy = (F.shot_xy(s, tt + 0.02)[0] - x) / 0.02, (F.shot_xy(s, tt + 0.02)[1] - y) / 0.02
                    bosses.projectile(ink, b["shot"], x, y, s.size, s.pink, c.td, s.seed, vx, vy)
                if a.stage == "sea":
                    stage(ink, c, "water")
                # heroes and their shots
                self._heroes(ink, c, t, a, F, bl)
                stage(ink, c, "front")
                if a.stage == "ballroom":
                    cheer = any(g.kind == "audience" and g.t0 <= t < g.t1 for g in P.gags) or c.ko >= 0
                    stages.audience(ink, c, cheer=1.0 if cheer else 0.0)
                self._gags(ink, c, t, a)
        if self.hud_on and c.ko < 0 and t >= a.go:
            shows.hud(ink, c, self._bpm(t), F.cards_at(t))
        return flash

    def _bpm(self, t: float) -> float:
        return float(self.bpm[min(int(t), len(self.bpm) - 1)])

    def _heroes(self, ink: Ink, c: Ctx, t: float, a: story.Act, F: story.Fight, bullets):
        m = self.m
        sup = c.sup
        ko = c.ko >= 0
        hands = {}
        for h, kind in enumerate(self.cast):
            x, y, moving, dirx = F.hero_xy(h, t)
            lift, j, ju = F.jump_at(h, t)
            fight_on = t >= a.go and not ko
            p = self.hero_pose(c, h, "shoot" if fight_on else ("cheer" if ko else "dance"))
            p.look = (1.0, -0.1)
            if moving and not a.sky:
                p.run = ((t - m.bar_time(m.bar_at(t))) / (m.period * 0.5)) % 1.0
                p.facing = dirx
            if j is not None:
                p.action = "parry" if j.parry else "jump"
                p.spin = (ju * 2 * math.pi) if j.parry else 0.0
                p.lift = lift
            if p.action == "shoot":
                p.aim = -0.08 + 0.1 * math.sin(t * 1.3 + h)
                last = [ts for ts, hh in bullets if hh == h and ts <= t]
                p.muzzle = math.exp(-(t - last[-1]) / 0.04) if last else 0.0
                p.facing = 1.0
            if a.sky:
                self._plane(ink, c, kind, x, y, p, h)
            else:
                heroes.draw(ink, kind, x, y, p, 1.0)
            hands[h] = (x + 80, (y if not a.sky else y + 40) - 135 - p.lift)
        # peashooter bullets: little blue-white teardrops that streak to the boss
        for ts, h in bullets:
            tt = t - ts
            hx, hy, *_ = F.hero_xy(h, ts)
            y0 = (hy if not a.sky else hy + 40) - 135 - F.jump_at(h, ts)[0] - 6
            x = hx + 95 + 2600 * tt
            hit = 1180 + 140 * h01("hit", ts)
            if x < hit:
                ink.glow(x, y0, 26, (0.6, 0.85, 1.0, 0.35), soft=16)
                ink.capsule(x - 46, y0, x, y0, 4, 11, fill=rgb("bfe6ff"), ink=2.5, shade=0.2)
                ink.capsule(x - 30, y0, x - 4, y0, 2, 5, fill=rgb("ffffff"), ink=0, shade=0)
            elif tt < 0.42 + 0.1:
                rig.impact(ink, hit, y0, 34, (x - hit) / 260, col=rgb("dff2ff"))
        # super art: a beam from the first hero, then a big burst on the boss
        if sup >= 0:
            hx, hy = hands[0]
            w = 60 * math.sin(math.pi * min(1.0, sup * 1.3)) + 10
            ink.glow(hx + 600, hy, 380, (0.7, 0.9, 1.0, 0.25), soft=60, ry=w * 2)
            ink.capsule(hx + 20, hy, 1300, hy - 60, w * 0.6, w, fill=rgb("dff4ff"), ink=4, shade=0.1)
            ink.capsule(hx + 20, hy, 1300, hy - 60, w * 0.25, w * 0.4, fill=rgb("ffffff"), ink=0, shade=0)
            for k in range(3):
                q = (sup * 4 + k / 3) % 1.0
                ink.arc(hx + 80 + q * 1100, hy - q * 60, w * (1 + q), 4, 0.9, rot=-math.pi / 2, fill=rgb("ffffff", 1 - q))
            rig.impact(ink, 1300, hy - 60, 150 + 30 * c.squash, (sup * 3) % 1.0, col=rgb("dff4ff"))
        # parry pops: a pink flash where the shot was slapped away
        for pt in F.parries:
            if 0 <= t - pt < 0.3:
                ink.star(hands[0][0] - 60, hands[0][1] - 40, 60 + 200 * (t - pt), 8, 3, fill=rgb("ffb3d6"), ink=3,
                         rot=t * 4)

    def _plane(self, ink: Ink, c: Ctx, kind: str, x: float, y: float, p: heroes.Pose, h: int):
        """A little biplane; the hero sits in the cockpit."""
        col = (rgb("d9433a"), rgb("3a6ea8"))[h % 2]
        tilt = 0.08 * math.sin(c.t * 2 + h)
        with ink.at(x, y, tilt):
            ink.box(0, -40, 120, 7, 3, fill=col, ink=4, shade=0.4)
            ink.capsule(-40, -40, -40, 40, 3, fill=INK, ink=0)
            ink.capsule(40, -40, 40, 40, 3, fill=INK, ink=0)
            p2 = heroes.Pose(**{**p.__dict__})
            p2.lift = 0.0
            p2.run = None
            if p2.action in ("jump", "parry"):
                p2.action = "cheer"
            heroes.draw(ink, kind, -10, 80, p2, 0.7)
            with ink.outlined(5):
                ink.ellipse(0, 50, 150, 44, fill=col, ink=0, shade=0.5)
                ink.tri((-120, 40), (-190, -10), (-170, 60), fill=col, ink=0)
            ink.box(10, 70, 140, 8, 3, fill=col, ink=4, shade=0.4)
            ink.ellipse(150, 50, 18, 26, fill=rgb("e8b14a"), ink=3, shade=0.4)
            ink.ellipse(170, 50, 8, 70 * abs(math.sin(c.t * 40)), fill=(0.9, 0.9, 0.9, 0.55), ink=0, shade=0, soft=3)
            for k in range(2):
                q = (c.t * 2 + k / 2 + h * 0.3) % 1.0
                ink.ellipse(-200 - q * 160, 40 - q * 20, 14 + 20 * q, fill=(1, 1, 1, 0.6 * (1 - q)), ink=2 * (1 - q),
                            shade=0)

    def _gags(self, ink: Ink, c: Ctx, t: float, a):
        for g in self.P.gags:
            if g.t0 <= t < g.t1 and g.kind in gags.DRAW and g.kind != "laugh":
                gags.DRAW[g.kind](ink, c, g, (t - g.t0) / max(g.t1 - g.t0, 1e-3))

    # ------------------------------------------------------------------ film
    def _film(self, c: Ctx, t: float, flash: float) -> np.ndarray:
        f = np.zeros(FILM_N, np.float32)
        ff = math.floor(t * 24)
        f[0:4] = [(h01("wx", ff) - 0.5) * 1.8, (h01("wy", ff) - 0.5) * 1.4,
                  1.0 + 0.03 * (h01("fl", ff) - 0.5) + self.kick_pump * c.kick + 0.6 * flash, self.vignette]
        f[4:8] = [self.grain, 2.0, ff % 9973, self.grade]
        f[8:12] = [0.84, 0.55, 0.11, 0.16]
        f[12:16] = [W / 2, H / 2, -1.0, 0.0]
        f[16:20] = [0.0, 0.0, 0.0, 0.07]
        iris = self._iris(t)
        if iris is not None:
            f[12:15] = iris
        P = self.P
        for g in P.gags:
            if g.kind == "burn" and g.t0 <= t < g.t1:
                u = (t - g.t0) / (g.t1 - g.t0)
                f[16:19] = [W * (0.3 + 0.4 * g.seed), H * 0.45, 30 + 1400 * u ** 2]
        if t > P.outro[1] - 0.05:
            f[15] = 1.0
        if self.grade == 3.0 or self.dirt <= 0:
            return f
        # scratches persist for a couple of seconds; dust and hairs change every film frame
        ns = 0
        for w_ in (math.floor(t / 2.3), math.floor(t / 3.7) + 5000):
            if h01("sc", w_) < 0.35 * self.dirt and ns < 4:
                f[24 + ns * 4: 28 + ns * 4] = [h01("scx", w_) * W, 1.2 + 2.0 * h01("scw", w_),
                                               (0.45 if h01("scs", w_) < 0.6 else -0.35), h01("scp", w_) * 50]
                ns += 1
        nd = int(h01("dn", ff) * 6 * self.dirt)
        for k in range(min(nd, 24)):
            f[40 + k * 4: 44 + k * 4] = [h01("dx", ff, k) * W, h01("dy", ff, k) * H, 1.5 + 5 * h01("ds", ff, k) ** 2,
                                         (-1 if h01("dk", ff, k) < 0.6 else 1) * (0.1 + 0.8 * h01("dsh", ff, k))]
        nh = 0
        wh = math.floor(t / 1.5)
        if h01("hr", wh) < 0.12 * self.dirt:
            x0, y0 = h01("hx", wh) * W, h01("hy", wh) * H
            jit = (h01("hj", ff) - 0.5) * 2
            f[136:140] = [x0, y0, x0 + 60 + 80 * h01("hl", wh), y0 + 30 + jit]
            f[140:144] = [x0 + 40 + jit, y0 - 40, 1.6, 0.6]
            nh = 1
        f[20:24] = [ns, nd, nh, 0.0]
        return f

    def _iris(self, t: float):
        for cut, d_close, d_open, cc, co in self.trans:
            if cut - d_close <= t < cut:
                u = (t - (cut - d_close)) / d_close
                return [cc[0], cc[1], 2300 * (1 - u) ** 1.6]
            if cut <= t < cut + d_open:
                u = (t - cut) / d_open
                return [co[0], co[1], 2300 * u ** 1.6]
        P = self.P
        end = P.outro[1]
        if t > end - 2.0:
            u = (t - (end - 2.0)) / 2.0
            return [W / 2, 420, 2300 * (1 - u) ** 1.6]
        return None
