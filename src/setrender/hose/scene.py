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
from . import bosses, combat, eggs, gags, heroes, rig, shows, stages, story
from .ctx import Ctx
from .engine import Engine
from . import lettering
from .ink import GLOW, INK, Ink, rgb
from .story import h01

W, H = 1920.0, 1080.0
FILM_N = 4 * 38


def _rolled(rows: np.ndarray, dy: float) -> np.ndarray:
    """The film slipping in the gate: the picture rolled down by dy with the frame above showing at
    the top and a black frame line between them (shape rows moved in screen space)."""
    from .ink import BOX, WAVE, Ink as _Ink
    out = []
    for off in (dy, dy - H - 50):
        r = rows.copy()
        ty = r[:, 16].astype(int)
        r[:, 1] += off                                  # every shape's first point / centre
        pts = ~np.isin(ty, (BOX, WAVE))                 # second and third points (not box half-sizes)
        r[pts, 3] += off
        r[pts, 5] += off
        r[ty == WAVE, 3] += off                         # a wave band's bottom edge
        out.append(r)
    bar = _Ink(boil=0.0)
    bar.box(W / 2, dy - 25, W / 2 + 80, 25, 0, fill=(0.02, 0.02, 0.02, 1), ink=0, shade=0)
    return np.concatenate(out + [bar.array()]).astype(np.float32)
NAMES = {"pepper": "PEPPER", "loaf": "PUMPERNICKEL", "salt": "SALTY", "bulb": "SPARKY", "sugar": "SUGAR"}
GRADES = {"warm": 0.0, "twostrip": 1.0, "mono": 2.0, "clean": 3.0}


def running_order(cfg: dict, title: str, rng):
    """The whole cartoon's plan (no GPU needed): analysis, music structure, seed, cast and acts."""
    clip = cfg["_clip"]
    full = analysis.load(Path(clip["analysis"]))
    ex = None
    if clip.get("extras") and Path(clip["extras"]).exists():
        z = np.load(clip["extras"], allow_pickle=True)
        ex = {k: z[k] for k in z.files}
    st = cmusic.build(full, ex, 0.0)
    m = story.Music(full, st)
    seed = int(rng.integers(1 << 30))
    r2 = np.random.default_rng(seed)
    cast = heroes.cast_from_title(title, r2)
    want = cfg.get("bosses") or [b["name"] for b in bosses.ROSTER]
    roster = [bosses.BY_NAME[n] for n in want if n in bosses.BY_NAME] or bosses.ROSTER
    P = story.plan(m, st, r2, roster, cfg.get("story", {}) or {}, st.sounds)
    return full, st, m, seed, cast, P


def highlight_hints(cfg: dict, title: str, rng):
    """Moments worth a highlight clip: supers, knockouts, revives, lost takes, round starts, gags,
    easter eggs and intermissions. Returns (hints [(t, weight, label)], intro end, outro start)."""
    full, st, m, seed, cast, P = running_order(cfg, title, rng)
    hints = []
    bar = 4 * m.period
    for a in P.acts:
        F = combat.Fight(m, P, a, bosses.BY_NAME[a.boss], seed + a.k * 7919, cfg.get("story", {}) or {})
        hints += [(t, 1.2, f"super vs {a.boss}") for t in F.supers]
        hints.append((a.ko, 1.0, f"knockout {a.boss}"))
        hints.append((a.go, 0.6, f"round start {a.boss}"))
        hints += [(r[0] - bar, 0.9, f"revive vs {a.boss}") for r in F.revives]
        hints += [(tk.end - bar, 0.8, f"take {tk.n} lost to {a.boss}") for tk in a.takes if not tk.won]
        hints += [(t, 0.3, f"phase {k + 1} {a.boss}") for k, t in enumerate(a.phases[1:], 1)]
    hints += [(g.t0, 0.5, f"gag {g.kind}") for g in P.gags if g.kind not in ("scratch", "singalong", "laugh")]
    hints += [(g.t0, 0.55, f"egg {g.kind}") for g in P.eggs]
    hints += [(i.t0, 0.4, f"intermission {i.kind}") for i in P.inters]
    return hints, P.intro[1], P.outro[0]


class HoseScene:
    pix_fmt = "nv12"

    def __init__(self, cfg: dict, tl, an_slice, rng, title: str, fingerprint: dict):
        clip = cfg["_clip"]
        self.cfg = cfg
        self.fps = float(tl.fps)
        self.start = float(clip["start"])
        self.title = title
        full, st, self.m, self.seed, self.cast, self.P = running_order(cfg, title, rng)
        self.names = [self._name(k) for k in self.cast]
        self.fights: dict[int, combat.Fight] = {}
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
        bpm = cmusic.local_bpm(self.m.beats, tt[:: int(self.fps)], full.tempo).astype(np.float64)
        last = float(full.tempo)
        for k in range(len(bpm)):          # gaps in the beat grid (fades, the very end): hold the last tempo
            if 70.0 <= bpm[k] <= 190.0:
                last = bpm[k]
            else:
                bpm[k] = last
        self.bpm = bpm
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

    def _fight(self, a: story.Act) -> combat.Fight:
        if a.k not in self.fights:
            b = bosses.BY_NAME[a.boss]
            self.fights[a.k] = combat.Fight(self.m, self.P, a, b, self.seed + a.k * 7919,
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
        for a in P.acts:         # a lost take: iris in on the laughing boss, the TAKE card, back to the stage
            for tk in a.takes:
                if not tk.won:
                    tr.append((tk.end, bar * 0.5, bar * 0.25, (1300, 420), (W / 2, 470)))
                    tr.append((tk.end + story.TAKE_CARD * bar, bar * 0.25, bar * 0.75, (W / 2, 470), (420, 760)))
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
        elif story.take_card_at(P, t):
            mode = "take"
        flash = 0.0
        egg_on = [(g, (t - g.t0) / max(g.t1 - g.t0, 1e-3)) for g in P.eggs if g.t0 <= t < g.t1]
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
        elif mode == "take":
            self._take_card(ink, c, t)
        else:
            flash = self._fight_frame(ink, c, t, egg_on)
        if mode != "fight":
            where = eggs.Where(mode="card" if mode in ("intro", "outro", "take") else "inter")
            for g, u in egg_on:
                if eggs.LAYER.get(g.kind) != "none" and g.kind in eggs.DRAW:
                    eggs.DRAW[g.kind](ink, c, g, u, where)
        # lettering cards over everything
        for card in P.cards:
            if card.t0 <= t < card.t1:
                u = (t - card.t0) / max(card.t1 - card.t0, 1e-3)
                sub = None
                if card.kind == "ready":
                    a = story.act_at(P, t)
                    sub = f"ROUND {a.k + 1}: {bosses.BY_NAME[a.boss]['title']}"
                if card.kind != "take":
                    shows.card_text(ink, c, card.text, card.kind, u, sub)
        rows = ink.array()
        slip = [u for g, u in egg_on if g.kind == "slip"]
        if slip and eggs.frame_slip(slip[0]) > 0:
            rows = _rolled(rows, eggs.frame_slip(slip[0]))
        return rows, (float(c.drawing), t, -2.2, 0.0), self._film(c, t, flash)

    def _take_card(self, ink: Ink, c: Ctx, t: float):
        a, tk = story.take_card_at(self.P, t)
        F = self._fight(a)
        b = bosses.BY_NAME[a.boss]
        bar = 4 * self.m.period
        u = (t - tk.end) / (story.TAKE_CARD * bar)
        beat_u = (t - tk.end) / self.m.period
        prog = min(0.99, F.dmg(tk.end - 1e-3))

        def face(ink2, x, y, s):
            bc = Ctx(**{**c.__dict__})
            bc.laugh, bc.dmg, bc.pie, bc.soot, bc.stache, bc.hurt, bc.ko = 1.0, 0.0, -1.0, -1.0, -1.0, 0.0, -1.0
            bc.hue = (-0.05 * a.variant) % 1.0
            with ink2.at(x, y, 0.08 * math.sin(c.t * 9), s):
                ink2.ellipse(0, 0, 150, fill=rgb("f6efe0"), ink=5, shade=0.3)
                bosses.big_face(ink2, bc, 0, 10, 0.75)
        shows.take_card(ink, c, tk.n + 1, u, beat_u, prog, face, self.cast)
        _ = b

    def _fight_frame(self, ink: Ink, c: Ctx, t: float, egg_on) -> float:
        m, P = self.m, self.P
        a = story.act_at(P, t)
        F = self._fight(a)
        b = bosses.BY_NAME[a.boss]
        stage = stages.STAGES[a.stage]
        bar = 4 * m.period
        tk = story.take_at(a, t)
        c.take = tk.n
        c.phase = story.phase_of(a, t)
        c.phase_t = t - tk.phases[c.phase] if tk.phases else 99.0
        c.ko = (t - a.ko) / max(a.t1 - a.ko, 1e-3) if t >= a.ko else -1.0
        c.intro = min(1.0, max(0.0, (t - tk.t0) / max(tk.go - tk.t0, 1e-3)))
        c.sky = a.sky
        c.variant = a.variant
        c.hue = (-0.05 * a.variant) % 1.0     # rematches come back a shade redder
        c.dmg = F.dmg(t)
        c.laugh = F.laugh(t) if c.ko < 0 else 0.0
        sh = F.active_shots(t)
        recent = [s.ts for s in sh if s.ts <= t]
        c.shot = t - max(recent) if recent else 9.0
        sup = F.super_at(t)
        c.sup = (t - sup) / F.super_dur if sup is not None else -1.0
        bl = F.active_bullets(t)
        hits = [ts + 0.42 for ts, _ in bl if ts + 0.42 <= t]
        c.hurt = 0.55 * math.exp(-(t - max(hits)) / 0.05) if hits else 0.0
        for te, h, q in F.ex_at(t):               # an EX lands a beat after it is thrown
            if q >= 1.0:
                c.hurt = max(c.hurt, 0.9 * math.exp(-(q - 1.0) * m.period / 0.1))
        if c.sup >= 0:
            c.hurt = max(c.hurt, 0.7 * (0.5 + 0.5 * math.sin(t * 50)))
        bld = m.st.in_segment(m.st.builds, t)
        c.build = (t - bld.t0) / max(bld.t1 - bld.t0, 1e-3) if bld else 0.0
        laughing = c.laugh > 0.5 or any(g.kind == "laugh" and g.t0 <= t < g.t1 for g in P.gags)
        # easter eggs on the boss's face and the bits of the fight they need
        hero_at = lambda h, tt: F.hero_xy(h, tt)[:2]  # noqa: E731
        layers = {"back": [], "front": [], "screen": []}
        for g, u in egg_on:
            if g.kind == "pie":
                c.pie = u
            elif g.kind == "pencil":
                c.stache = max(0.0, (u - 0.12) / 0.88)
            elif g.kind == "bomb" and u >= 0.55:
                c.soot = (u - 0.55) / 0.45
            if g.kind == "anvil" and 0.28 <= u < 0.4:
                c.hurt = max(c.hurt, 0.8)
            lay = eggs.LAYER.get(g.kind, "front")
            if lay == "none" or g.kind not in eggs.DRAW:
                continue
            w = eggs.Where(mode="fight", sky=a.sky, ground=combat.GROUND, face=b.get("face"), top=b.get("top"))
            if g.kind in ("qblock", "banana"):
                hh = 0 if g.seed < 0.5 else 1
                w.heroes = [hero_at(hh, g.t0 + (0.5 if g.kind == "qblock" else 0.45) * (g.t1 - g.t0))]
            elif g.kind == "bomb":
                w.heroes = [hero_at(1, g.t0 + 0.35 * (g.t1 - g.t0))]
            elif g.kind == "bowling":
                w.ball_x = F.egg_ball_x(g, t)
            layers[lay].append((g, u, w))

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
        for dn in F.downs:                       # a jolt when a hero goes down
            if 0 <= t - dn.t < 0.2:
                sx += (h01("kx", c.drawing) - 0.5) * 30 * (1 - (t - dn.t) / 0.2)

        with ink.at(W / 2 + sx, H / 2 + sy, 0.0, z):
            with ink.at(-W / 2, -H / 2):
                stage(ink, c, "back")
                for g, u, w in layers["back"]:
                    eggs.DRAW[g.kind](ink, c, g, u, w)
                # boss: rises in during READY? (every take), sinks after the knockout
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
                    if c.phase > 0 and 0 <= c.phase_t < 0.75 * bar and c.ko < 0:
                        self._phase_flourish(ink, c, b, c.phase_t / (0.75 * bar))
                if laughing:
                    gags.laugh(ink, c, None, 0.5, 1250, 160)
                # boss shots
                for s in sh:
                    tt = t - s.ts
                    if s.kind == "ring":
                        if tt < s.life:
                            bosses.ring_wave(ink, *F.shot_xy(s, tt), min(1.0, tt / s.life))
                        continue
                    if tt >= s.life:          # how it ended: popped by a parry, hit a hero, splashed down
                        x, y = F.shot_xy(s, s.life)
                        q = (tt - s.life) / 0.18
                        if s.end == "parry":
                            rig.impact(ink, x, y, 80, q, col=rgb("ffb3d6"))
                        elif s.end == "hit":
                            rig.impact(ink, x, y, 95, q, col=rgb("fff3c4"))
                        elif s.end == "floor":
                            for j in range(3):
                                ink.ellipse(x - 30 + 30 * j, y - 10 - 40 * q, 16 + 22 * q,
                                            fill=(0.95, 0.9, 0.8, 0.8 * (1 - q)), ink=2.5 * (1 - q), shade=0.2)
                        continue
                    x, y = F.shot_xy(s, tt)
                    x2, y2 = F.shot_xy(s, tt + 0.02)
                    bosses.projectile(ink, b["shot"], x, y, s.size, s.pink, c.td, s.seed, (x2 - x) / 0.02, (y2 - y) / 0.02)
                if a.stage == "sea":
                    stage(ink, c, "water")
                # heroes and their shots
                self._heroes(ink, c, t, a, F, bl, tk)
                stage(ink, c, "front")
                if a.stage == "ballroom":
                    cheer = any(g.kind == "audience" and g.t0 <= t < g.t1 for g in P.gags) or c.ko >= 0
                    stages.audience(ink, c, cheer=1.0 if cheer else 0.0)
                for g, u, w in layers["front"]:
                    eggs.DRAW[g.kind](ink, c, g, u, w)
                self._gags(ink, c, t, a)
        if self.hud_on and c.ko < 0 and t >= tk.go:
            states = []
            for h, kind in enumerate(self.cast):
                lh = F.last_hit(h, t)
                states.append({"kind": kind, "hp": F.hp(h, t), "meter": F.meter(h, t), "down": F.down_at(h, t) is not None,
                               "hit_age": t - lh if lh is not None and lh >= tk.t0 else 99.0})
            shows.hud(ink, c, self._bpm(t), states)
        for g, u, w in layers["screen"]:
            eggs.DRAW[g.kind](ink, c, g, u, w)
        return flash

    def _phase_flourish(self, ink: Ink, c: Ctx, b: dict, u: float):
        """The boss changes phase: a puff of smoke all round it and a flash."""
        fx, fy, r = b.get("face", (1400, 450, 150))
        for j in range(10):
            a = j * 2 * math.pi / 10 + 0.3
            rr = r * (1.4 + 1.6 * u)
            ink.ellipse(fx + math.cos(a) * rr * 1.3, fy + math.sin(a) * rr, 50 + 60 * u, fill=(0.96, 0.93, 0.86, 0.85 * (1 - u)),
                        ink=4 * (1 - u), shade=0.3)
        if u < 0.3:
            rig.impact(ink, fx, fy, r * 2.2, u / 0.3, col=rgb("fff3c4"))

    def _bpm(self, t: float) -> float:
        return float(self.bpm[min(int(t), len(self.bpm) - 1)])

    def _heroes(self, ink: Ink, c: Ctx, t: float, a: story.Act, F: combat.Fight, bullets, tk):
        m = self.m
        ko = c.ko >= 0
        hands = {}
        supers = F.supers_at(t)
        for h, kind in enumerate(self.cast):
            dn = F.down_at(h, t)
            if dn is not None:
                self._downed(ink, c, t, a, F, h, kind, dn)
                continue
            x, y, moving, dirx = F.hero_xy(h, t)
            lift, j, ju = F.jump_at(h, t)
            fight_on = t >= tk.go and not ko
            p = self.hero_pose(c, h, "shoot" if fight_on else ("cheer" if ko else "dance"))
            p.look = (1.0, -0.1)
            if moving and not a.sky:
                p.run = ((t - m.bar_time(m.bar_at(t))) / (m.period * 0.5)) % 1.0
                p.facing = dirx
            tilt = 0.0
            if j is not None:
                if j.kind == "slip":          # banana peel: feet fly up, down on the seat
                    p.action, p.lift = "hurt", lift
                    tilt = -1.2 * math.sin(math.pi * ju) * p.facing
                else:
                    p.action = "parry" if j.parry else "jump"
                    p.spin = (ju * 2 * math.pi) if j.parry else 0.0
                    p.lift = lift
            lh = F.last_hit(h, t)
            age = t - lh if lh is not None else 99.0
            if age < 0.4:                       # just hit: flung back, eyes screwed shut
                p.action, p.blink, p.mouth, p.run = "hurt", 1.0, 1.0, None
                tilt = -0.35 * math.exp(-age / 0.2)
            exs = [q for te, hh, q in F.ex_at(t) if hh == h and q < 0.5]
            if exs and p.action in ("shoot", "dance"):
                p.action, p.facing, p.mouth = "ex", 1.0, 0.9
            mine = [s0 for s0, hh in supers if hh == h]
            if mine:
                p.run = None
                p.action = "cheer" if heroes.SUPER.get(kind) == "giant" else "shoot"
                p.facing, p.mouth = 1.0, 1.0
                p.aim = -0.15
            if p.action == "shoot":
                p.aim = -0.08 + 0.1 * math.sin(t * 1.3 + h)
                last = [ts for ts, hh in bullets if hh == h and ts <= t]
                p.muzzle = math.exp(-(t - last[-1]) / 0.04) if last else 0.0
                p.facing = 1.0
            # untouchable after a hit or a revive: blink every other drawing
            rv = [r for r in F.revives if r[2] == h and 0 <= t - r[0] < 0.25 + combat.INV_REVIVE]
            blink = (age < combat.INV_HIT or bool(rv)) and (c.drawing // 2) % 2 == 1
            with ink.at(0, 0, fade=0.65 if blink else None):
                if a.sky:
                    self._plane(ink, c, kind, x, y - p.lift, p, h)
                elif tilt:
                    with ink.at(x, y - p.lift, tilt):
                        p2 = heroes.Pose(**{**p.__dict__})
                        p2.lift = 0.0
                        heroes.draw(ink, kind, 0, 0, p2, 1.0)
                else:
                    heroes.draw(ink, kind, x, y, p, 1.0)
            if age < 0.3:
                rig.impact(ink, x + 30, y - p.lift - (130 if not a.sky else 0), 80, age / 0.3, col=rgb("ffd0a0"))
            hands[h] = (x + 50, y - 10 - p.lift) if a.sky else (x + 80, y - 135 - p.lift)
            for s0 in mine:
                self._super_art(ink, c, kind, hands[h], (t - s0) / F.super_dur, h)
        # peashooter bullets: little blue-white teardrops that streak to the boss
        for ts, h in bullets:
            tt = t - ts
            hx, hy, *_ = F.hero_xy(h, ts)
            y0 = hy - 14 if a.sky else hy - 135 - F.jump_at(h, ts)[0] - 6
            x = hx + (70 if a.sky else 95) + 2600 * tt
            hit = 1180 + 140 * h01("hit", ts)
            if x < hit:
                ink.glow(x, y0, 26, (0.6, 0.85, 1.0, 0.35), soft=16)
                ink.capsule(x - 46, y0, x, y0, 4, 11, fill=rgb("bfe6ff"), ink=2.5, shade=0.2)
                ink.capsule(x - 30, y0, x - 4, y0, 2, 5, fill=rgb("ffffff"), ink=0, shade=0)
            elif tt < 0.42 + 0.1:
                rig.impact(ink, hit, y0, 34, (x - hit) / 260, col=rgb("dff2ff"))
        # EX shots: one card's worth, thrown in a beat
        for te, h, q in F.ex_at(t):
            hx, hy, *_ = F.hero_xy(h, te)
            x0 = hx + (70 if a.sky else 95)
            y0 = hy - (14 if a.sky else 150)
            x1, y1 = 1250.0, 430.0 if not a.sky else 470.0
            if q < 1.0:
                x = x0 + (x1 - x0) * q
                y = y0 + (y1 - y0) * q - 160 * math.sin(math.pi * q)
                rig.speed_lines(ink, x - 40, y, math.atan2(y1 - y0, x1 - x0), n=3, ln=90)
                heroes.ex_shot(ink, self.cast[h], x, y, t, 1.25)
            else:
                rig.impact(ink, x1, y1, 170, min(1.0, (q - 1.0) / 0.6), col=rgb("ffe9a0"))
        # parry pops: a pink flash where a shot or a ghost was slapped
        for pt, h, px, py, kind in F.parries:
            if 0 <= t - pt < 0.3:
                ink.star(px, py, 60 + 200 * (t - pt), 8, 3, fill=rgb("ffb3d6"), ink=3, rot=t * 4)

    def _downed(self, ink: Ink, c: Ctx, t: float, a: story.Act, F: combat.Fight, h: int, kind: str, dn):
        """A hero at 0 HP: flat out on the floor (or their plane spinning away) while their ghost rises;
        parried, the ghost dives back in; not, it floats off and leaves a little grave."""
        dt = t - dn.t
        p = self.hero_pose(c, h, "dance")
        p.facing = 1.0
        if a.sky:
            if dt < 1.8:
                q = dt
                with ink.at(0, 0, fade=min(1.0, max(0.0, (dt - 1.2) / 0.6))):
                    with ink.at(dn.x - 80 * q, dn.y + 420 * q * q, -q * 4):
                        self._plane(ink, c, kind, 0, 0, p, h)
                for j in range(4):
                    qq = (dt * 2 + j / 4) % 1.0
                    ink.ellipse(dn.x - 80 * dt + 60 * j, dn.y + 420 * dt * dt - 60 * j, 18 + 30 * qq,
                                fill=(0.3, 0.28, 0.27, 0.6 * (1 - qq)), ink=0, shade=0, soft=4)
        elif dn.revive is None and t >= dn.away:
            heroes.tomb(ink, dn.x, dn.y, c.t)
        else:
            heroes.lying(ink, kind, dn.x, dn.y, p, 1.0)
        if dn.revive is not None and t >= dn.revive:
            q = min(1.0, (t - dn.revive) / 0.25)
            gx, gy = F.ghost_xy(dn, dn.revive)
            bx, by = dn.x, dn.y - (120 if not a.sky else 0)
            heroes.ghost(ink, kind, gx + (bx - gx) * q, gy + (by - gy) * q, c.t, c.beat, 0.9 - 0.4 * q, 1 - 0.6 * q)
        elif t < dn.away:
            gx, gy = F.ghost_xy(dn, t)
            heroes.ghost(ink, kind, gx, gy, c.t, c.beat, 0.9, min(1.0, dt / 0.3))

    def _super_art(self, ink: Ink, c: Ctx, kind: str, hand, u: float, h: int):
        """Five cards spent: a Sneeze Beam (pepper, salt), a giant spirit belly-flop (rye, sugar) or a
        Bright Idea flash (the bulb)."""
        hx, hy = hand
        style = heroes.SUPER.get(kind, "sneeze")
        bx, by = 1300.0, hy - 60
        if style == "giant":
            if u < 0.3:
                q = u / 0.3
                gx, gy, s = hx - 40, hy + 135 - 60 * q, 1.0 + 1.6 * q
            elif u < 0.6:
                q = (u - 0.3) / 0.3
                gx, gy, s = hx - 40 + (bx - hx) * q, hy + 75 - 520 * math.sin(math.pi * q * 0.9), 2.6
            else:
                q = (u - 0.6) / 0.4
                gx, gy, s = bx - 300 * q, hy + 75 - 200 * q, 2.6 * (1 - 0.5 * q)
            p = self.hero_pose(c, h, "cheer")
            p.mouth = 1.0
            with ink.at(0, 0, fade=0.45 + (0.5 * (u - 0.6) / 0.4 if u > 0.6 else 0.0)):
                ink.glow(gx, gy - 130 * s, 160 * s, (1.0, 0.85, 0.5, 0.35), soft=60)
                heroes.draw(ink, kind, gx, gy, p, s)
            if 0.58 <= u < 0.8:
                rig.impact(ink, bx, 520, 260, (u - 0.58) / 0.22, col=rgb("ffe9a0"))
                lettering.words(ink, "WHAM!", bx - 260, 260, 110, fill=rgb("fff2b0"), wobble=2.0, t=c.t)
            return
        if style == "sneeze" and u < 0.18:      # the wind-up: a big breath in
            k = u / 0.18
            ink.glow(hx - 40, hy - 70, 60 + 50 * k, (1.0, 0.7, 0.7, 0.4 * k), soft=30)
            return
        q = (u - (0.18 if style == "sneeze" else 0.0)) / (0.82 if style == "sneeze" else 1.0)
        w = 70 * math.sin(math.pi * min(1.0, q * 1.2)) + 12
        if style == "sneeze":             # it comes out of the nose, not the hands
            hx, hy = hx - 50, hy - 75
            by = hy - 40
        col = {"sneeze": rgb("e8e2d4") if kind == "salt" else rgb("5a4a3e"), "flash": rgb("fff6b0")}[style]
        core = rgb("ffffff") if style == "flash" or kind == "salt" else rgb("a89480")
        ink.glow(hx + 600, hy, 380, (1.0, 0.95, 0.7, 0.25) if style == "flash" else (0.9, 0.85, 0.8, 0.2), soft=60, ry=w * 2)
        ink.capsule(hx + 20, hy, bx, by, w * 0.6, w * 1.3, fill=col, ink=4, shade=0.1)
        ink.capsule(hx + 20, hy, bx, by, w * 0.25, w * 0.5, fill=core, ink=0, shade=0)
        if style == "sneeze":
            grain = rgb("2a2420") if kind == "pepper" else rgb("ffffff")
            for j in range(26):
                f = (q * 3 + j / 26) % 1.0
                ink.ellipse(hx + 40 + (bx - hx) * f, hy + (by - hy) * f + (h01("gr", j) - 0.5) * w * 2.2, 5, 4,
                            fill=grain, ink=1.5, shade=0)
            if q < 0.35:
                lettering.words(ink, "ACHOO!", hx + 60, hy - 230, 84, fill=rgb("fff2b0"), wobble=2.0, t=c.t)
        else:
            ink.rays(hx, hy, 18, rgb("fff6b0", 0.35 * (1 - q)), rgb("fff6b0", 0.0), phase=c.t * 0.3, radius=0.0)
        for k in range(3):
            qq = (q * 4 + k / 3) % 1.0
            ink.arc(hx + 80 + qq * (bx - hx - 80), hy + (by - hy) * qq, w * (1 + qq), 4, 0.9, rot=-math.pi / 2,
                    fill=rgb("ffffff", 1 - qq))
        rig.impact(ink, bx, by, 150 + 30 * c.squash, (q * 3) % 1.0, col=rgb("dff4ff"))

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
            u = min(1.0, (t - (end - 2.0)) / 2.0)
            return [W / 2, 420, 2300 * (1 - u) ** 1.6]
        return None
