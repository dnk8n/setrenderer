"""Eight original bosses in 1930s rubber-hose style, each with three phases, its own stage and its
own projectiles. Every boss is drawn from distance-field primitives and bounces on the kick."""
from __future__ import annotations

import math

from . import rig
from .ctx import Ctx
from .ink import GLOW, INK, Ink, mix, rgb

WHITE = rgb("fffaf0")
GOLD = rgb("e8b14a")
BRASS = rgb("d9a441")
RED = rgb("c8372d")
PINK = rgb("ff6fae")


def big_face(ink: Ink, c: Ctx, x, y, s=1.0, look=(-0.8, 0.1), angry=0.0, open_=0.4, blink=0.0, teeth=True,
             brows=True, eye_gap=46, white=WHITE, laugh=0.0):
    """Boss-sized face: tall pie-cut eyes, heavy brows that slant into a V when angry, a big grin or
    gritted teeth. It wears the fight (a plaster, a black eye, a bump, sweat) and laughs when a hero
    goes down."""
    laugh = max(laugh, c.laugh)
    if laugh > 0.5:
        blink = max(blink, 0.85)
        open_ = max(open_, 0.75 + 0.25 * c.squash)
    d = c.dmg if c.ko < 0 else 1.0
    with ink.at(x, y, 0, s * 1.35):
        if d > 0.45:      # a black eye (the left one)
            ink.ellipse(-eye_gap, -28, 50, 66, fill=(0.35, 0.18, 0.42, 0.55 * min(1.0, (d - 0.45) * 5)), ink=0,
                        shade=0, soft=6)
        for side in (-1, 1):
            rig.eye(ink, side * eye_gap, -30, 36, 54, look, blink, cut=-0.6, side=side, white=white,
                    pupil=0.5 - 0.08 * angry)
            if brows:
                inner = (side * 14, -88 + 34 * angry - 8 * laugh)
                outer = (side * (eye_gap + 40), -100 - 14 * angry - 10 * laugh)
                ink.capsule(*inner, *outer, 6 + 4 * angry, 5 + 2 * angry, fill=INK, ink=0, shade=0)
        if angry > 0.55 and laugh < 0.5 and open_ < 0.6:
            rig.mouth(ink, 0, 62, 120, open_, grimace=1.0)
        else:
            rig.mouth(ink, 0, 52, 120, max(open_, laugh), smile=1.0 - 1.4 * angry, teeth=teeth)
        if angry < 0.5:
            rig.blush(ink, -100, 30, 22)
            rig.blush(ink, 100, 30, 22)
        _wear(ink, c, d, eye_gap)
        if c.stache >= 0:
            _moustache(ink, c.stache)
        if c.soot >= 0:
            _soot(ink, c, c.soot, eye_gap)
        if c.pie >= 0:
            _pie(ink, c, c.pie)


def _wear(ink: Ink, c: Ctx, d: float, eye_gap: float):
    """Damage that builds up on a boss's face over a take (reset when the fight restarts)."""
    if d > 0.22:          # a sticking plaster across the cheek
        with ink.at(eye_gap + 46, 6, 0.5):
            ink.box(0, 0, 44, 13, 6, fill=rgb("f2d2a6"), ink=3, shade=0.2)
            ink.box(0, 0, 12, 11, 2, fill=rgb("e8bf8e"), ink=0, shade=0)
            for k in (-1, 1):
                ink.ellipse(k * 28, 0, 2.2, fill=rgb("c89a6a"), ink=0, shade=0)
    if d > 0.62:          # a bump on the head
        k = min(1.0, (d - 0.62) * 6)
        ink.ellipse(eye_gap - 10, -150, 34 * k, 26 * k, fill=rgb("f08a8a"), ink=3.5, shade=0.4)
        ink.ellipse(eye_gap - 18, -160, 10 * k, 6 * k, fill=(1, 1, 1, 0.6), ink=0, shade=0)
    if d > 0.72:          # sweat flying off
        for k in range(3):
            q = (c.t * 1.3 + k / 3) % 1.0
            sx = (-1 if k % 2 else 1) * (eye_gap + 70 + 90 * q)
            ink.ellipse(sx, -110 + 160 * q * q - 40 * q, 9, 14, fill=rgb("bfe3ff", 1 - q * 0.6), ink=2.5 * (1 - q),
                        shade=0.3)
    if d > 0.88 and c.ko < 0:     # smoke out of the ears
        for k in range(3):
            q = (c.t * 0.9 + k / 3) % 1.0
            for side in (-1, 1):
                ink.ellipse(side * (eye_gap + 120 + 30 * q), -60 - 140 * q, 14 + 26 * q,
                            fill=(0.55, 0.52, 0.5, 0.55 * (1 - q)), ink=0, shade=0, soft=4)


def _moustache(ink: Ink, u: float):
    """The animator's pencil gives the boss a curly moustache (drawn in, then rubbed out)."""
    k = min(1.0, u / 0.35) if u < 0.8 else max(0.0, 1 - (u - 0.8) / 0.2)
    if k <= 0:
        return
    with ink.at(0, 22, 0, 1.0, fade=1 - k):
        for side in (-1, 1):
            ink.bez(0, 0, side * 50, -26, side * 96, 4, 13, 4, fill=INK, ink=0, shade=0)
            ink.arc(side * 102, -6, 12, 4, 1.4, rot=-side * 1.2, fill=INK)


def _soot(ink: Ink, c: Ctx, u: float, eye_gap: float):
    """After the bomb: a blackened face, white eyes blinking out of it, a wisp of smoke."""
    k = max(0.0, 1 - max(0.0, u - 0.7) / 0.3)
    with ink.at(0, 0, 0, 1.0, fade=1 - k):
        ink.ellipse(0, -10, 210, 190, fill=(0.08, 0.06, 0.05, 0.92), ink=0, shade=0, soft=10)
        bl = 1.0 if (c.t * 2.5) % 1.0 < 0.12 else 0.0
        for side in (-1, 1):
            ink.ellipse(side * eye_gap, -30, 22, 30 * (1 - bl) + 2, fill=WHITE, ink=0, shade=0)
        for k2 in range(3):
            q = (c.t * 0.7 + k2 / 3) % 1.0
            ink.ellipse(20 * math.sin(q * 6), -200 - 160 * q, 16 + 30 * q, fill=(0.3, 0.28, 0.27, 0.5 * (1 - q)), ink=0,
                        shade=0, soft=5)


def _pie(ink: Ink, c: Ctx, u: float):
    """A cream pie in the kisser: it lands, drips, and slides off."""
    if u < 0.18:
        return
    k = max(0.0, 1 - max(0.0, u - 0.8) / 0.2)
    slide = max(0.0, u - 0.8) * 500
    with ink.at(0, slide, 0, 1.0, fade=1 - k):
        with ink.outlined(5):
            for j, (px, py, r) in enumerate(((0, -10, 120), (-90, 30, 70), (95, 20, 75), (-40, 90, 60), (50, 95, 55),
                                            (0, -110, 70))):
                ink.ellipse(px, py, r, r * 0.85, fill=rgb("fffaf0"), ink=0, shade=0.3)
        for j in range(5):
            dl = min(1.0, (u - 0.18) * 3) * (40 + 30 * math.sin(j * 2.3))
            ink.capsule(-80 + j * 40, 100, -80 + j * 40, 100 + dl, 12, 9, fill=rgb("fffaf0"), ink=3, shade=0.2)
        ink.ellipse(0, -20, 140, 110, fill=(0, 0, 0, 0), ink=4, shade=0, ink_col=rgb("c88a4a"))
        for j in range(4):
            ink.ellipse(-50 + j * 33, -60 + 12 * (j % 2), 9, 6, fill=rgb("c8372d"), ink=2, shade=0.3)


def h01_(k: int) -> float:
    """A fixed pseudo-random 0..1 per index (for which dent, pipe or tube goes first)."""
    return (math.sin(k * 12.9898 + 4.1) * 43758.5453) % 1.0


def _ramp(cols, u: float):
    """Colour ramp through several stops, u in 0..1."""
    u = min(1.0, max(0.0, u)) * (len(cols) - 1)
    k = min(int(u), len(cols) - 2)
    return mix(cols[k], cols[k + 1], u - k)


def _hurt_jitter(c: Ctx) -> float:
    return math.sin(c.t * 90) * 5 * c.hurt


def _ko(c: Ctx):
    """Knocked-out wobble: (dx, rot, squash, eyes closed)."""
    if c.ko < 0:
        return 0.0, 0.0, 0.0, 0.0
    k = min(1.0, c.ko * 1.4)
    return math.sin(c.t * 5) * 30 * k, math.sin(c.t * 3) * 0.12 * k, 0.1 * k, 1.0


# ---------------------------------------------------------------- 1. gramophone

def gramophone(ink: Ink, c: Ctx, bx=1420.0, by=905.0):
    sq = c.squash * (0.5 + c.energy)
    dx, rot, ksq, kdz = _ko(c)
    wood, wood2 = c.col(rgb("8a5230")), c.col(rgb("5c331c"))
    brass = c.col(BRASS if c.phase < 2 else rgb("e0763a"))
    angry = [0.0, 0.6, 1.0][c.phase]
    with ink.at(bx + dx + _hurt_jitter(c), by, rot, 1 + 0.06 * sq, 1 - 0.08 * sq - ksq, seed=11):
        # legs and shoes (charleston in phase 3)
        for side in (-1, 1):
            kx = side * (70 + (40 * math.sin(c.beat * math.pi) if c.phase == 2 else 0))
            rig.hose(ink, side * 80, -60, kx, -10, 0.2 * side, r=11)
            rig.shoe(ink, kx, 0, side, 1.5, rgb("3a2216"))
        # cabinet
        with ink.outlined(6):
            ink.box(0, -170, 175, 125, 20, fill=wood, fill2=wood2, ink=0, shade=0.5)
        ink.box(0, -165, 130, 85, 12, fill=c.col(rgb("a8673c")), ink=3.5, shade=0.3)
        for k in range(5):        # speaker grille
            ink.capsule(-90 + k * 45, -205, -90 + k * 45, -125, 7, fill=wood2, ink=2.5, shade=0)
        if c.phase == 2:          # the lid opens like a jaw full of records
            ink.box(0, -300 - 30 * c.squash, 175, 18, 10, fill=wood, ink=5, shade=0.4, rot=-0.15 - 0.15 * c.squash)
            for k in range(6):
                ink.tri((-150 + k * 55, -292), (-125 + k * 55, -252), (-100 + k * 55, -292), fill=WHITE, ink=3)
        # turntable and spinning record
        ink.ellipse(-20, -300, 150, 34, fill=c.col(rgb("2b2420")), ink=4, shade=0.2)
        ink.rings(-20, -300, 9, rgb("3a3330"), rgb("1e1816"), radius=150, phase=c.t * 2)
        ink.ellipse(-20, -300, 34, 9, fill=c.col(RED), ink=3, shade=0)
        if c.dmg > 0.55:      # a cracked record
            rig.stroke(ink, [(-140, -296), (-100, -306), (-80, -292), (-40, -304)], 3.0)
        if c.dmg > 0.75:      # a spring sprung out of the cabinet
            for k in range(5):
                ink.arc(150 + 14 * k, -120 - 22 * k + 6 * math.sin(c.td * 9 + k), 16, 4, 1.4, rot=math.pi / 2,
                        fill=c.col(rgb("c0c0c4")))
        ink.capsule(110, -300, 30, -330 + 6 * math.sin(c.t * 20), 5, fill=c.col(rgb("c0c0c4")), ink=3)
        # arms: left points at the heroes when firing, right conducts
        fire = math.exp(-c.shot * 5)
        ax, ay = -175, -200
        hx, hy = -330 - 40 * fire, -260 + 30 * math.sin(c.td * 3)
        rig.hose(ink, ax, ay, hx, hy, -0.3, r=12)
        rig.glove(ink, hx, hy, math.pi + 0.3, "point" if fire > 0.3 else "open", side=-1, s=1.7)
        ang = -1.2 + 0.7 * math.sin(c.beat * math.pi)
        rx, ry = 175 + 120 * math.cos(ang), -220 + 120 * math.sin(ang)
        rig.hose(ink, 175, -220, rx, ry, 0.3, r=12)
        rig.glove(ink, rx, ry, ang, "fist", side=1, s=1.7)
        ink.capsule(rx + math.cos(ang) * 45, ry + math.sin(ang) * 45, rx + math.cos(ang - 0.6) * 150,
                    ry + math.sin(ang - 0.6) * 150, 4, 2.5, fill=WHITE, ink=2.5)
        # the horn: neck, flare and bell with the face in it
        breath = 1 + 0.07 * c.sub + 0.05 * fire
        with ink.at(-60, -560, -0.12, breath):
            with ink.outlined(6):
                ink.bez(150, 230, 210, 40, 70, -20, 22, 46, fill=brass, ink=0, shade=0.5)
                ink.tri((90, -20), (-120, -210), (-120, 170), fill=brass, ink=0, rnd=20, shade=0.5)
                ink.ellipse(-130, -20, 95, 200, fill=brass, fill2=c.col(rgb("b07a2a")), ink=0, shade=0.6)
            ink.ellipse(-140, -20, 72, 168, fill=c.col(rgb("4a1a14")), fill2=c.col(rgb("200a08")), ink=4, shade=0.1)
            for k in range(3):
                ink.arc(-40, -20, 120 + k * 45, 3, 0.55, rot=math.pi / 2, fill=mix(brass, INK, 0.35))
            for k in range(int(c.dmg * 5)):    # dents in the brass
                ink.arc(-120 + 60 * h01_(k), -200 + 330 * h01_(k + 7), 26, 5, 1.0, rot=0.6 * k,
                        fill=mix(brass, INK, 0.55))
            with ink.at(-140, -20, 0, 0.62, 0.85):
                big_face(ink, c, 0, 0, 1.0, look=(-0.9, 0.2), angry=angry, open_=0.25 + 0.7 * fire + 0.2 * c.kick,
                         blink=kdz)
        if c.ko >= 0:
            rig.dazed_stars(ink, -200, -820, 130, c.t)


GRAMOPHONE = {"name": "gramophone", "title": "GRAMOPHONE GUS", "stage": "ballroom", "sky": False,
              "emit": (1180, 390), "draw": gramophone, "shot": "note",
              "patterns": [["aimed", "aimed", "arc"], ["aimed", "arc", "wave", "ring"], ["spread", "arc", "wave", "ring"]],
    "face": (1220, 330, 120), "top": (1240, 120)}


# ---------------------------------------------------------------- 2. the sun

def sun(ink: Ink, c: Ctx, bx=1440.0, by=430.0):
    dx, rot, ksq, kdz = _ko(c)
    hot = c.phase / 2
    body = c.col(mix(rgb("ffd54a"), rgb("ff8a3a"), hot * 0.8))
    body2 = c.col(mix(rgb("ffb03a"), rgb("e04a2a"), hot))
    r = 210 * (1 + 0.05 * c.squash * (0.5 + c.energy) + 0.03 * c.sub) * (1 - 0.1 * c.dmg)
    with ink.at(bx + dx + _hurt_jitter(c), by + 20 * math.sin(c.t * 0.8), rot, seed=21):
        ink.glow(0, 0, r * 1.25, (1.0, 0.85, 0.4, 0.45 + 0.2 * c.sub), soft=90)
        if c.phase < 2:
            ink.star(0, 0, r * (1.45 + 0.08 * c.kick), 14, 4.5, fill=c.col(rgb("ffc94a")), ink=5,
                     rot=c.td * 0.4 + 0.1 * c.squash, shade=0.3)
        else:
            for k in range(12):
                a = k * math.pi / 6 + c.td * 0.5
                fl = 1 + 0.25 * math.sin(c.td * 11 + k * 1.7)
                x0, y0 = math.cos(a) * r * 0.9, math.sin(a) * r * 0.9
                x1, y1 = math.cos(a) * r * 1.6 * fl, math.sin(a) * r * 1.6 * fl
                ink.bez(x0, y0, (x0 + x1) / 2 + math.cos(a + 1.6) * 40, (y0 + y1) / 2 + math.sin(a + 1.6) * 40, x1, y1,
                        38, 4, fill=c.col(rgb("ff7a2a")), ink=4, shade=0.3)
        ink.ellipse(0, 0, r, r * (1 - 0.06 * c.squash), fill=body, fill2=body2, ink=6, shade=0.6)
        ink.ellipse(-r * 0.45, -r * 0.5, r * 0.22, r * 0.12, fill=(1, 1, 1, 0.55), ink=0, shade=0, rot=-0.6)
        for k in range(int(c.dmg * 7)):       # sunspots
            a = k * 2.4 + 0.5
            ink.ellipse(math.cos(a) * r * 0.72, math.sin(a) * r * 0.72, 22 - k, 15 - k * 0.6,
                        fill=c.col(rgb("b0461e", 0.75)), ink=0, shade=0, soft=2)
        fire = math.exp(-c.shot * 5)
        big_face(ink, c, 0, 10, 1.15, look=(-0.9, 0.15), angry=0.5 * c.phase, open_=0.3 + 0.6 * fire, blink=kdz)
        if c.phase == 1 and c.ko < 0:      # cool shades
            with ink.outlined(4):
                ink.box(-48, -38, 42, 30, 14, fill=INK, ink=0, shade=0)
                ink.box(48, -38, 42, 30, 14, fill=INK, ink=0, shade=0)
                ink.capsule(-10, -48, 10, -48, 5, fill=INK, ink=0, shade=0)
            ink.capsule(-70, -55, -40, -50, 5, fill=(1, 1, 1, 0.7), ink=0, shade=0)
        if c.phase == 2:                    # sweat
            for k in range(3):
                yy = (c.t * 300 + k * 90) % 260
                ink.ellipse(r * 0.8 + k * 10, -r * 0.3 + yy, 9, 14, fill=rgb("bfe3ff"), ink=2.5, shade=0.3)
        if c.ko >= 0:
            rig.dazed_stars(ink, 0, -r - 40, 150, c.t)


SUN = {"name": "sun", "title": "SUNNY SID", "stage": "sky", "sky": True, "emit": (1300, 470), "draw": sun,
       "shot": "fireball", "patterns": [["aimed", "wave"], ["spread", "wave", "aimed"], ["spread", "rain", "wave"]],
    "face": (1440, 445, 190), "top": (1440, 190)}


# ---------------------------------------------------------------- 3. the storm cloud

def cloud(ink: Ink, c: Ctx, bx=1420.0, by=360.0):
    dx, rot, ksq, kdz = _ko(c)
    dark = max(c.phase / 2, c.dmg)
    col = c.col(mix(rgb("e9eef2"), rgb("6c7486"), dark * 0.85))
    col2 = c.col(mix(rgb("b9c3cf"), rgb("3c4252"), dark))
    pf = 1 + 0.05 * c.squash * (0.5 + c.energy)
    with ink.at(bx + dx + _hurt_jitter(c), by + 15 * math.sin(c.t * 0.9), rot, pf, 1 / pf, seed=31):
        # lightning crown in phase 3
        if c.phase == 2:
            for k in range(3):
                if math.sin(c.td * 13 + k * 2) > 0.3:
                    x = -220 + k * 220
                    pts = [(x, 120), (x - 30, 220), (x + 20, 230), (x - 20, 340)]
                    ink.glow(x - 10, 230, 60, (1, 0.95, 0.5, 0.5), soft=40)
                    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
                        ink.capsule(x0, y0, x1, y1, 9, 6, fill=rgb("fff07a"), ink=3.5, shade=0)
        with ink.outlined(7):
            blobs = [(-250, 40, 110), (-130, -40, 150), (30, -80, 170), (190, -30, 150), (290, 50, 110),
                     (-60, 80, 140), (130, 90, 140)]
            for k, (x, y, r) in enumerate(blobs):
                w = 1 + 0.04 * math.sin(c.td * 2 + k)
                ink.ellipse(x, y, r * w, r * w * 0.92, fill=col, fill2=col2, ink=0, shade=0.55)
        for k in range(int(c.dmg * 5)):      # torn patches of sky showing through
            ink.ellipse(-260 + 130 * k, 120 - 60 * (k % 2), 30 + 6 * k, 18, fill=c.col(rgb("8fb6d8", 0.8)), ink=3,
                        shade=0, soft=1)
        if c.dmg > 0.4:
            for k in range(6):              # drizzle
                q = (c.t * 1.6 + k / 6) % 1.0
                ink.capsule(-240 + k * 90, 160 + 300 * q, -246 + k * 90, 180 + 300 * q, 3, fill=rgb("bfe3ff", 1 - q),
                            ink=0, shade=0)
        fire = math.exp(-c.shot * 5)
        big_face(ink, c, 20, 20, 1.05, look=(-0.9, 0.3), angry=0.4 + 0.3 * c.phase, open_=0.3 + 0.6 * fire,
                 blink=kdz)
        # cheeks puff when blowing
        if fire > 0.2:
            for k in range(3):
                ink.ellipse(-230 - k * 60 - 200 * (1 - fire), 70 + k * 12, 26 - k * 5, 16 - k * 3, fill=(1, 1, 1, 0.8),
                            ink=3, shade=0.2)
        if c.ko >= 0:
            rig.dazed_stars(ink, 20, -260, 160, c.t)


CLOUD = {"name": "cloud", "title": "THUNDERING THELMA", "stage": "storm", "sky": True, "emit": (1260, 420),
         "draw": cloud, "shot": "bolt", "patterns": [["rain", "aimed"], ["rain", "aimed", "wave"], ["rain", "spread", "aimed"]],
    "face": (1440, 385, 160), "top": (1440, 170)}


# ---------------------------------------------------------------- 4. the kettle

def kettle(ink: Ink, c: Ctx, bx=1450.0, by=905.0):
    dx, rot, ksq, kdz = _ko(c)
    heat = max(c.phase / 2, c.dmg)                  # teal, then orange, then red-hot
    body = c.col(_ramp((rgb("6fb3b0"), rgb("e8a04a"), rgb("e0503a"), rgb("ff3a1a")), heat))
    body2 = c.col(_ramp((rgb("3d7f86"), rgb("a8602a"), rgb("8a2214"), rgb("a01808")), heat))
    sq = c.squash * (0.5 + c.energy)
    with ink.at(bx + dx + _hurt_jitter(c), by, rot, 1 + 0.07 * sq, 1 - 0.09 * sq - ksq, seed=41):
        # stove burner
        ink.box(0, -20, 230, 22, 8, fill=rgb("3a3330"), ink=5, shade=0.3)
        for k in range(9):
            fl = 1 + 0.4 * math.sin(c.td * 14 + k * 2.3) + 0.6 * c.sub
            ink.ellipse(-180 + k * 45, -50, 12, 20 * fl, fill=rgb("6ab0ff"), ink=2.5, shade=0)
        # spout and handle
        with ink.outlined(6):
            ink.bez(-170, -230, -280, -260, -350, -390, 50, 26, fill=body, ink=0, shade=0.5)
            ink.ellipse(0, -270, 250, 210, fill=body, fill2=body2, ink=0, shade=0.6)
        ink.arc(180, -330, 150, 16, 1.2, rot=-math.pi * 0.6, fill=c.col(rgb("2e2a28")))
        ink.ellipse(-90, -380, 60, 26, fill=(1, 1, 1, 0.5), ink=0, shade=0, rot=-0.5)
        if heat > 0.6:      # glowing red-hot
            ink.glow(0, -270, 300, (1.0, 0.35, 0.15, 0.25 * (heat - 0.6) / 0.4 * (0.7 + 0.3 * c.squash)), soft=80)
        for k in range(int(c.dmg * 5)):       # dents
            ink.arc(-150 + 75 * k, -170 - 60 * (k % 2), 30, 5, 1.0, rot=0.4 * k, fill=c.col(rgb("2e2a28", 0.6)))
        if c.dmg > 0.7:     # rivets popping off
            for k in range(3):
                q = (c.t * 0.8 + k / 3) % 1.0
                ink.ellipse(200 + 160 * q, -330 - 200 * q + 260 * q * q, 9, fill=rgb("c0c0c4"), ink=2.5, shade=0.4)
        # lid rattles on the beat in phase 2+
        lid_up = (40 * c.squash if c.phase >= 1 else 0) + (20 * math.sin(c.td * 30) if c.phase == 2 else 0)
        with ink.at(0, -470 - lid_up, 0.08 * math.sin(c.td * 20) * (c.phase >= 1)):
            ink.ellipse(0, 0, 150, 34, fill=body, ink=5, shade=0.5)
            ink.ellipse(0, -36, 28, 22, fill=c.col(rgb("2e2a28")), ink=4, shade=0.4)
        fire = math.exp(-c.shot * 5)
        big_face(ink, c, 30, -250, 1.05, look=(-0.9, 0.2), angry=0.5 * c.phase, open_=0.25 + 0.6 * fire + 0.2 * c.kick,
                 blink=kdz)
        if c.dmg > 0.5:     # steam whistling out from under the lid
            for side in (-1, 1):
                for k in range(3):
                    q = (c.t * 2.2 + k / 3) % 1.0
                    ink.ellipse(side * (160 + 120 * q), -480 - 60 * q, 14 + 24 * q, 10 + 18 * q,
                                fill=(1, 1, 1, 0.7 * (1 - q)), ink=2 * (1 - q), shade=0.2)
        # steam from the spout
        for k in range(5):
            u = ((c.t * 0.8 + k / 5) % 1.0)
            ink.ellipse(-360 - 30 * u, -420 - 220 * u, 20 + 40 * u, 18 + 34 * u, fill=(1, 1, 1, 0.75 * (1 - u)),
                        ink=3 * (1 - u), shade=0.2)
        if c.ko >= 0:
            rig.dazed_stars(ink, 0, -600, 150, c.t)


KETTLE = {"name": "kettle", "title": "KETTLE KATE", "stage": "kitchen", "sky": False, "emit": (1100, 520),
          "draw": kettle, "shot": "steam", "patterns": [["aimed", "arc"], ["arc", "wave", "aimed"], ["spread", "arc", "wave"]],
    "face": (1480, 655, 150), "top": (1450, 420)}


# ---------------------------------------------------------------- 5. the pipe organ

def organ(ink: Ink, c: Ctx, bx=1450.0, by=905.0, bands=(0.5,) * 5):
    dx, rot, ksq, kdz = _ko(c)
    wood, wood2 = c.col(rgb("5b2f4a")), c.col(rgb("2e1626"))
    pipe = c.col(rgb("d6b25a"))
    sq = c.squash * (0.5 + c.energy)
    with ink.at(bx + dx + _hurt_jitter(c), by, rot, 1 + 0.04 * sq, 1 - 0.05 * sq - ksq, seed=51):
        # the pipes are a spectrum: each one stretches and glows with its band
        for k in range(9):
            b = bands[min(4, abs(k - 4))]
            h = 300 + 120 * (1 - abs(k - 4) / 4) + 160 * b
            x = -280 + k * 70
            broken = h01_(k + 31) < c.dmg * 0.75
            if broken:
                h *= 0.55
            ink.glow(x, -560 - h * 0.3, 40, (1, 0.9, 0.5, 0.35 * b), soft=40)
            ink.box(x, -430 - h / 2, 26, h / 2, 14, fill=pipe, fill2=c.col(rgb("8a6a2a")), ink=4.5, shade=0.6)
            ink.ellipse(x, -330, 20, 8, fill=INK, ink=0, shade=0)
            if broken:      # a bent, snapped top and a plaster
                with ink.at(x, -430 - h, 0.5 * (1 if k % 2 else -1)):
                    ink.box(0, -30, 24, 34, 10, fill=pipe, ink=4, shade=0.5)
                    rig.stroke(ink, [(-20, -60), (-6, -70), (6, -58), (20, -68)], 3.5)
                ink.box(x, -430 - h * 0.6, 30, 10, 4, fill=rgb("f2d2a6"), ink=2.5, shade=0.2, rot=0.3)
        with ink.outlined(6):
            ink.box(0, -200, 300, 200, 30, fill=wood, fill2=wood2, ink=0, shade=0.5)
            ink.ellipse(0, -380, 230, 120, fill=wood, ink=0, shade=0.4)
        ink.ellipse(0, -330, 170, 120, fill=c.col(rgb("1b0d16")), ink=4, shade=0)
        # keyboard mouth that chomps on the beat
        jaw = 20 + 40 * c.squash
        ink.box(0, -130 + jaw * 0.5, 240, 40, 8, fill=WHITE, ink=4, shade=0.2)
        for k in range(12):
            ink.box(-200 + k * 36, -150 + jaw * 0.5, 9, 22, 2, fill=INK, ink=0, shade=0)
        for k in range(int(c.dmg * 6)):       # knocked-out keys
            ink.box(-180 + 70 * ((k * 3) % 6), -128 + jaw * 0.5, 15, 18, 2, fill=c.col(rgb("1b0d16")), ink=0, shade=0)
        big_face(ink, c, 0, -360, 0.95, look=(-0.8, 0.2), angry=0.4 * c.phase, open_=0.0, blink=kdz, teeth=False,
                 white=rgb("e8f6d8"))
        for side in (-1, 1):
            hx = side * 150 + 30 * math.sin(c.beat * math.pi * 2 + side)
            rig.hose(ink, side * 300, -250, hx, -150, 0.3 * side, r=11)
            rig.glove(ink, hx, -150, math.pi / 2, "open", side=side, s=1.5)
        if c.ko >= 0:
            rig.dazed_stars(ink, 0, -700, 160, c.t)


ORGAN = {"name": "organ", "title": "THE PHANTOM PIPES", "stage": "graveyard", "sky": False, "emit": (1300, 420),
         "draw": organ, "shot": "ghostnote", "patterns": [["wave", "aimed"], ["wave", "arc", "aimed"], ["spread", "wave", "arc"]],
    "face": (1450, 545, 140), "top": (1450, 300)}


# ---------------------------------------------------------------- 6. the octopus

def bez_pt(p0, p1, p2, t):
    u = 1 - t
    return (u * u * p0[0] + 2 * u * t * p1[0] + t * t * p2[0], u * u * p0[1] + 2 * u * t * p1[1] + t * t * p2[1])


def octopus(ink: Ink, c: Ctx, bx=1480.0, by=800.0):
    dx, rot, ksq, kdz = _ko(c)
    skin, skin2 = c.col(rgb("c0507a")), c.col(rgb("7a2a52"))
    sq = c.squash * (0.5 + c.energy)
    with ink.at(bx + dx + _hurt_jitter(c), by + 20 * math.sin(c.t * 1.1), rot, 1 + 0.05 * sq, 1 - 0.06 * sq, seed=61):
        for k in range(6):
            side = -1 if k < 3 else 1
            j = k % 3
            a0 = (-160 + k * 64, -60)
            w = math.sin(c.td * 2.2 + k * 1.3 + c.beat * math.pi * 0.5)
            slam = (c.phase == 2) * math.exp(-(c.beat % 2) * 4) * 120
            a2 = (side * (300 + j * 70) + w * 60, -120 - j * 90 + w * 70 + slam * (k % 2))
            a1 = ((a0[0] + a2[0]) / 2 + w * 90, (a0[1] + a2[1]) / 2 + 160)
            ink.bez(*a0, *a1, *a2, 46, 12, fill=skin, fill2=None, ink=5, shade=0.5)
            for s in range(4):
                px, py = bez_pt(a0, a1, a2, 0.25 + s * 0.18)
                ink.ellipse(px, py + 14, 9 - s, 6 - s * 0.6, fill=rgb("f2b5c8"), ink=2, shade=0)
            if h01_(k + 51) < c.dmg:         # bandaged
                for s in range(3):
                    px, py = bez_pt(a0, a1, a2, 0.55 + s * 0.09)
                    ink.box(px, py, 30, 9, 4, fill=rgb("f6f0e2"), ink=2.5, shade=0.2, rot=0.6 + 0.2 * s)
        with ink.outlined(6):
            ink.ellipse(0, -280, 230, 250, fill=skin, fill2=skin2, ink=0, shade=0.6)
        for k in range(5):
            ink.ellipse(-120 + k * 60, -420 + (k % 2) * 40, 14, 10, fill=c.col(rgb("e88aaa")), ink=0, shade=0)
        fire = math.exp(-c.shot * 5)
        big_face(ink, c, 0, -230, 1.05, look=(-0.9, 0.2), angry=0.45 * c.phase, open_=0.2 + 0.6 * fire, blink=kdz)
        # captain's hat
        with ink.at(10 + 40 * c.dmg, -500 + 30 * c.dmg, -0.12 + 0.05 * c.squash - 0.5 * c.dmg):
            with ink.outlined(5):
                ink.box(0, 0, 150, 40, 18, fill=WHITE, ink=0, shade=0.4)
                ink.ellipse(0, 40, 170, 26, fill=INK, ink=0, shade=0)
            ink.ellipse(0, 6, 26, 20, fill=GOLD, ink=3, shade=0.4)
        if c.ko >= 0:
            rig.dazed_stars(ink, 0, -620, 160, c.t)


OCTOPUS = {"name": "octopus", "title": "CAPTAIN EIGHTARMS", "stage": "sea", "sky": False, "emit": (1300, 520),
           "draw": octopus, "shot": "ink", "patterns": [["arc", "aimed"], ["arc", "wave", "aimed"], ["spread", "arc", "wave"]],
    "face": (1480, 570, 150), "top": (1490, 300)}


# ---------------------------------------------------------------- 7. the jukebox robot

def jukebox(ink: Ink, c: Ctx, bx=1450.0, by=905.0, bands=(0.5,) * 5):
    dx, rot, ksq, kdz = _ko(c)
    wood, wood2 = c.col(rgb("8a4a2a")), c.col(rgb("4a2416"))
    chrome = c.col(rgb("c9ccd2"))
    sq = c.squash * (0.5 + c.energy)
    with ink.at(bx + dx + _hurt_jitter(c), by, rot, 1 + 0.06 * sq, 1 - 0.08 * sq - ksq, seed=71):
        for side in (-1, 1):
            kx = side * (80 + (30 * math.sin(c.beat * math.pi) if c.phase >= 1 else 0))
            rig.hose(ink, side * 90, -90, kx, -10, 0.15 * side, r=14, col=chrome)
            rig.shoe(ink, kx, 0, side, 1.6, rgb("2a2a30"))
        with ink.outlined(6):
            ink.box(0, -330, 200, 240, 40, fill=wood, fill2=wood2, ink=0, shade=0.5)
            ink.ellipse(0, -560, 200, 120, fill=wood, ink=0, shade=0.5)
        # neon tubes along the arch, one colour per band
        neon = [rgb("ff5a5a"), rgb("ffb84a"), rgb("ffe95a"), rgb("6ad36a"), rgb("5ab0ff")]
        for k, col in enumerate(neon):
            b = bands[k]
            if h01_(k + 71) < c.dmg * 0.85 and math.sin(c.t * 37 + k * 3) < 0.7:
                col, b = rgb("3a3438"), 0.0       # a dead tube (flickers now and then)
            r = 175 - k * 22
            ink.arc(0, -540, r, 9, 1.25, rot=math.pi, fill=mix(col, (1, 1, 1, 1), 0.3 * b))
            ink.glow(0, -540 - r * 0.8, 24 + 20 * b, (col[0], col[1], col[2], 0.12 + 0.2 * b), soft=30)
        ink.ellipse(0, -530, 110, 70, fill=c.col(rgb("20304a")), ink=4, shade=0)
        if c.dmg > 0.4:     # cracked glass
            rig.stroke(ink, [(-80, -580), (-30, -540), (-50, -500), (10, -470)], 2.5, col=rgb("dfe8f0"))
            rig.stroke(ink, [(-30, -540), (40, -560), (90, -590)], 2.5, col=rgb("dfe8f0"))
        if c.dmg > 0.6 and math.sin(c.t * 23) > 0.3:     # sparks
            for k in range(4):
                a = c.t * 11 + k * 1.6
                ink.star(160 + 40 * math.cos(a), -420 + 40 * math.sin(a), 14, 4, 2, fill=rgb("fff07a"), ink=2,
                         rot=a)
        big_face(ink, c, 0, -520, 0.6, look=(-0.9, 0.2), angry=0.45 * c.phase, open_=0.0, blink=kdz, brows=True)
        # speaker grille mouth
        op = 0.3 + 0.7 * max(math.exp(-c.shot * 5), c.kick * 0.6)
        ink.box(0, -280, 140, 50 + 50 * op, 30, fill=c.col(rgb("2a1810")), ink=4, shade=0)
        for k in range(7):
            ink.capsule(-120 + k * 40, -280 - 40 * op, -120 + k * 40, -280 + 40 * op, 6, fill=chrome, ink=2, shade=0.3)
        ink.box(0, -160, 150, 30, 10, fill=chrome, ink=4, shade=0.4)
        # arms
        for side in (-1, 1):
            ang = math.pi / 2 + side * (1.2 + 0.4 * math.sin(c.beat * math.pi))
            hx, hy = side * 200 + math.cos(ang) * 150 * side, -380 + math.sin(ang) * 80
            rig.hose(ink, side * 200, -380, hx, hy, 0.15 * side, r=14, col=chrome)
            rig.glove(ink, hx, hy, math.atan2(hy + 380, hx - side * 200), "open", side=side, s=1.6)
        ink.capsule(0, -680, 0, -760, 5, fill=chrome, ink=3)
        ink.glow(0, -770, 20, (1, 0.4, 0.3, 0.4 * c.squash), soft=20)
        ink.ellipse(0, -770, 16, fill=c.col(rgb("ff5a4a")), ink=3, shade=0.3)
        if c.ko >= 0:
            rig.dazed_stars(ink, 0, -820, 160, c.t)


JUKEBOX = {"name": "jukebox", "title": "JUKEBOX JOE", "stage": "city", "sky": False, "emit": (1300, 520),
           "draw": jukebox, "shot": "record", "patterns": [["arc", "aimed"], ["aimed", "ring", "arc"], ["spread", "ring", "arc"]],
    "face": (1450, 385, 90), "top": (1450, 120)}


# ---------------------------------------------------------------- 8. old man oak

def oak(ink: Ink, c: Ctx, bx=1480.0, by=905.0):
    dx, rot, ksq, kdz = _ko(c)
    bark, bark2 = c.col(rgb("7a4e2e")), c.col(rgb("4a2c18"))
    leaf, leaf2 = c.col(mix(rgb("6fa34a"), rgb("c0702a"), max(c.phase * 0.35, c.dmg * 0.8))), c.col(rgb("3f6e2e"))
    sq = c.squash * (0.5 + c.energy)
    with ink.at(bx + dx + _hurt_jitter(c), by, rot + 0.04 * math.sin(c.beat * math.pi), 1 + 0.05 * sq,
                1 - 0.07 * sq - ksq, seed=81):
        # roots as feet
        for k in range(4):
            x = -150 + k * 100
            lift = (c.phase == 2) * 40 * max(0.0, math.sin(c.beat * math.pi + k))
            ink.bez(x * 0.5, -120, x * 1.1, -40 - lift, x * 1.6, -lift, 34, 14, fill=bark, ink=5, shade=0.4)
        with ink.outlined(6):
            ink.box(0, -300, 170, 260, 80, fill=bark, fill2=bark2, ink=0, shade=0.5)
        for k in range(6):
            x = -120 + k * 48
            ink.bez(x, -480, x + 20 * math.sin(k), -350, x - 10, -150, 4, 2, fill=bark2, ink=0, shade=0)
        # branch arms with gloves
        for side in (-1, 1):
            ang = -math.pi / 2 + side * (0.9 + 0.35 * math.sin(c.beat * math.pi + side))
            hx, hy = side * 170 + math.cos(ang) * 230, -420 + math.sin(ang) * 170
            ink.bez(side * 150, -400, side * 230, -500, hx, hy, 30, 16, fill=bark, ink=5, shade=0.4)
            rig.glove(ink, hx, hy, ang, "open", side=side, s=1.7)
        # canopy
        with ink.outlined(7):
            for k, (x, y, r) in enumerate(((-230, -620, 150), (-80, -720, 180), (110, -710, 175), (250, -610, 150),
                                           (0, -580, 170), (-140, -540, 130), (160, -530, 130))):
                w = (1 + 0.05 * math.sin(c.td * 2.5 + k) + 0.04 * c.lowmid) * (1 - 0.4 * c.dmg * h01_(k + 91))
                ink.ellipse(x, y, r * w, r * w * 0.9, fill=leaf, fill2=leaf2, ink=0, shade=0.55)
        if c.dmg > 0.3:         # leaves falling
            for k in range(int(3 + 6 * c.dmg)):
                q = (c.t * 0.35 + k / 9) % 1.0
                lx = -260 + 520 * h01_(k + 101) + 50 * math.sin(c.t * 3 + k)
                ink.ellipse(lx, -560 + 560 * q, 12, 6, fill=leaf, ink=2, shade=0.2, rot=c.t * 4 + k)
        for k in range(7 - int(c.dmg * 6)):          # acorns / apples hanging (fewer as it's shaken)
            a = k * 0.9
            ink.ellipse(-240 + k * 80, -560 + 40 * math.sin(a), 14, 16, fill=c.col(rgb("c0472c")), ink=3, shade=0.5)
        fire = math.exp(-c.shot * 5)
        big_face(ink, c, 0, -310, 1.0, look=(-0.9, 0.2), angry=0.45 * c.phase, open_=0.25 + 0.6 * fire, blink=kdz,
                 white=rgb("f3ead2"))
        if c.ko >= 0:
            rig.dazed_stars(ink, 0, -900, 160, c.t)


OAK = {"name": "oak", "title": "OLD MAN OAK", "stage": "forest", "sky": False, "emit": (1300, 470), "draw": oak,
       "shot": "acorn", "patterns": [["arc", "rain"], ["arc", "wave", "rain"], ["spread", "rain", "arc"]],
    "face": (1480, 595, 140), "top": (1480, 160)}

ROSTER = [GRAMOPHONE, SUN, CLOUD, KETTLE, ORGAN, OCTOPUS, JUKEBOX, OAK]
BY_NAME = {b["name"]: b for b in ROSTER}


# ---------------------------------------------------------------- projectiles

def projectile(ink: Ink, kind: str, x, y, s, pink: bool, t: float, seed: float, vx=-1.0, vy=0.0):
    col = PINK if pink else None
    ang = math.atan2(vy, vx)
    if pink:
        ink.glow(x, y, 40 * s, (1.0, 0.5, 0.75, 0.35), soft=25)
    with ink.at(x, y, 0, s * 1.45, seed=int(seed * 900)):
        if kind == "note":
            rig.note(ink, 0, 0, 1.3, col or INK, rot=0.3 * math.sin(t * 8 + seed * 9), double=seed > 0.5)
        elif kind == "fireball":
            for k in range(3):
                ink.ellipse(-math.cos(ang) * (20 + k * 18), -math.sin(ang) * (20 + k * 18), 22 - k * 6,
                            fill=rgb("ffb03a", 0.8 - k * 0.2), ink=0, shade=0)
            ink.ellipse(0, 0, 26, fill=col or rgb("ff7a2a"), fill2=rgb("ffd04a") if not pink else None, ink=4, shade=0.4)
            rig.eye(ink, -8, -4, 5, 8, (-1, 0), 0.0)
            rig.eye(ink, 6, -4, 5, 8, (-1, 0), 0.0)
        elif kind == "bolt":
            pts = [(-20, -40), (10, -10), (-10, 0), (20, 40)]
            for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
                ink.capsule(x0, y0, x1, y1, 9, 6, fill=col or rgb("fff07a"), ink=3.5, shade=0)
            ink.glow(0, 0, 30, (1, 0.95, 0.5, 0.4), soft=30)
        elif kind == "steam":
            ink.ellipse(0, 0, 30, 24, fill=col or WHITE, ink=4, shade=0.35)
            ink.ellipse(16, -12, 18, 15, fill=col or WHITE, ink=4, shade=0.35)
        elif kind == "ghostnote":
            ink.ellipse(0, 0, 26, 30, fill=col or rgb("d8f0e0"), ink=4, shade=0.3)
            ink.bez(-22, 10, -10, 50 + 10 * math.sin(t * 10), 20, 34, 12, 3, fill=col or rgb("d8f0e0"), ink=4, shade=0.3)
            rig.eye(ink, -9, -6, 6, 10, (-1, 0), 0.0)
            rig.eye(ink, 9, -6, 6, 10, (-1, 0), 0.0)
        elif kind == "ink":
            ink.ellipse(0, 0, 30, 26, fill=col or INK, ink=0, shade=0.3, rot=t * 3)
            ink.ellipse(20, -16, 10, fill=col or INK, ink=0, shade=0)
            ink.ellipse(-22, 14, 8, fill=col or INK, ink=0, shade=0)
        elif kind == "record":
            with ink.at(0, 0, t * 14):
                ink.ellipse(0, 0, 34, 34, fill=col or rgb("2a2420"), ink=4, shade=0.3)
                ink.ellipse(0, 0, 11, fill=RED if not pink else WHITE, ink=2, shade=0)
                ink.arc(0, 0, 22, 2, 0.8, rot=0.5, fill=(1, 1, 1, 0.4))
        elif kind == "acorn":
            with ink.at(0, 0, t * 6):
                ink.ellipse(0, 6, 18, 22, fill=col or rgb("b06a32"), ink=4, shade=0.5)
                ink.ellipse(0, -12, 22, 12, fill=rgb("6a4a2a"), ink=4, shade=0.4)
                ink.capsule(0, -24, 4, -34, 3, fill=rgb("6a4a2a"), ink=2)
        else:
            ink.ellipse(0, 0, 24, fill=col or WHITE, ink=4, shade=0.4)


def ring_wave(ink: Ink, x, y, u: float):
    """Sound-wave shot: arcs that spread as they travel."""
    for k in range(3):
        r = 40 + 60 * u + k * 26
        ink.arc(x + k * 20, y, r, 5 - k, 0.8, rot=math.pi / 2, fill=(*INK[:3], 1 - u * 0.5))
