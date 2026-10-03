"""The two heroes: small rubber-hose kitchen mascots with big heads (a pepper shaker, a rye loaf,
a salt shaker, a light bulb or a sugar bowl), black hose limbs, white gloves and big shoes.

A title that names one of them ("pepper", "pumpernick", "salt"...) casts it; otherwise the set's
seed picks a pair. Every pose is a pure function of the music clock handed in."""
from __future__ import annotations

import math
from dataclasses import dataclass

from . import rig
from .ink import INK, Ink, mix, rgb

KINDS = {
    "pepper": {"shorts": rgb("c8372d"), "shoe": rgb("5e3320"), "words": ("pepper", "peppa", "pfeffer")},
    "loaf": {"shorts": rgb("3a6ea8"), "shoe": rgb("8a2a22"), "words": ("pumpernick", "bread", "brot", "rye", "loaf")},
    "salt": {"shorts": rgb("2f6f9a"), "shoe": rgb("4a2e20"), "words": ("salt", "salz")},
    "bulb": {"shorts": rgb("4b8a4a"), "shoe": rgb("6b3a24"), "words": ("bulb", "light", "lamp", "edison")},
    "sugar": {"shorts": rgb("c76a9a"), "shoe": rgb("4a2e20"), "words": ("sugar", "sweet", "candy", "zucker")},
}


def cast_from_title(title: str, rng) -> list[str]:
    t = title.lower()
    named = [k for k, v in KINDS.items() if any(w in t for w in v["words"])]
    order = sorted(KINDS, key=lambda k: t.find(next((w for w in KINDS[k]["words"] if w in t), "\x00")))
    named = [k for k in order if k in named]
    pool = [k for k in KINDS if k not in named]
    rng.shuffle(pool)
    return (named + pool)[:2]


@dataclass
class Pose:
    t: float = 0.0            # drawing clock (s), steps at 24 fps
    beat: float = 0.0         # continuous beat count (phase = fractional part)
    facing: float = 1.0
    lift: float = 0.0         # px above the ground
    run: float | None = None  # run-cycle phase, None = standing
    action: str = "dance"     # dance | shoot | jump | parry | wave | cheer | walk | sit | bow | hurt | ex
    aim: float = 0.0          # shooting angle (radians, 0 = facing direction)
    look: tuple = (0.6, 0.0)
    blink: float = 0.0
    mouth: float = 0.3
    spin: float = 0.0
    energy: float = 0.5       # music intensity 0..1 (bigger moves)
    style: int = 0            # dance style
    muzzle: float = 0.0       # 0..1 flash at the finger tip
    hat: bool = False         # straw boater for the vaudeville number
    cane: bool = False


def _head(ink: Ink, kind: str, p: Pose, sq: float):
    f = p.facing
    fx = 10 * f
    if kind in ("pepper", "salt"):
        glass = rgb("e4e6e2") if kind == "pepper" else rgb("f4f6f8")
        glass2 = rgb("b9c2c4") if kind == "pepper" else rgb("cfdde6")
        cap = rgb("b8bcc4") if kind == "pepper" else rgb("6d97c4")
        with ink.outlined(4.5):
            ink.box(0, 0, 54, 62, 30, fill=glass, fill2=glass2, ink=0, shade=0.55)
        # what is left in the shaker, settled at the bottom of the glass
        pile = rgb("4a3c34") if kind == "pepper" else rgb("fbfbf8")
        ink.box(0, 50, 46, 10, 8, fill=pile, ink=0, shade=0.2)
        for k in range(9):
            ink.ellipse(-40 + k * 10, 41 + 3 * math.sin(k * 2.1), 6, 4, fill=pile, ink=0, shade=0, boil=0.5)
        ink.box(0, 22, 48, 3, 2, fill=(1, 1, 1, 0.35), ink=0, shade=0)
        ink.ellipse(-30 * f, -10, 7, 26, fill=(1, 1, 1, 0.7), ink=0, shade=0, rot=0.15 * f)
        with ink.outlined(4.0):
            ink.ellipse(0, -60, 50, 34, fill=cap, ink=0, shade=0.7)
            ink.box(0, -56, 52, 10, 4, fill=mix(cap, (0, 0, 0, 1), 0.15), ink=0, shade=0.4)
        for k in range(-1, 2):
            ink.ellipse(k * 15 + fx * 0.3, -76 - abs(k) * -3, 3.6, 3.0, fill=INK, ink=0, shade=0)
        ink.ellipse(-22 * f, -74, 9, 5, fill=(1, 1, 1, 0.75), ink=0, shade=0, rot=-0.5 * f)
        face_y, face_r = -12, 1.0
    elif kind == "loaf":
        crust = rgb("4a2a1c")
        crust2 = rgb("2e1a12")
        with ink.outlined(4.5):
            ink.box(0, 6, 70, 52, 34, fill=crust, fill2=crust2, ink=0, shade=0.55)
            for k in range(3):
                ink.ellipse((k - 1) * 40, -34 - (1 - abs(k - 1)) * 10, 36, 30, fill=crust, ink=0, shade=0.5)
        for k in range(3):
            x = (k - 1) * 38
            ink.bez(x - 16, -46, x, -58, x + 16, -44, 4, 2.5, fill=rgb("b58a5a"), ink=0, shade=0)
        for k in range(9):
            a = k * 2.1
            ink.ellipse(math.cos(a) * 52, -20 + math.sin(a) * 30, 3.4, 2.0, fill=rgb("e6d3a8"), ink=0, shade=0,
                        rot=a)
        ink.ellipse(-44 * f, -30, 12, 6, fill=(1, 0.9, 0.75, 0.35), ink=0, shade=0, rot=-0.4 * f)
        face_y, face_r = 4, 1.0
    elif kind == "bulb":
        lit = 0.5 + 0.5 * math.exp(-(p.beat % 1.0) * 5)
        glassc = mix(rgb("fff6c9"), rgb("ffe27a"), lit * 0.6)
        ink.glow(0, -8, 64, (1.0, 0.9, 0.5, 0.35 * lit), soft=40)
        with ink.outlined(4.5):
            ink.ellipse(0, -14, 60, 64, fill=glassc, ink=0, shade=0.4)
            ink.box(0, 50, 30, 18, 8, fill=glassc, ink=0, shade=0.3)
        ink.arc(0, -34, 16, 2.2, 1.4, rot=math.pi, fill=mix(rgb("ff9a2a"), rgb("ffffff"), lit * 0.5))
        with ink.outlined(3.5):
            for k in range(3):
                ink.box(0, 70 + k * 10, 28 - k * 2, 5, 3, fill=rgb("a9a59a"), ink=0, shade=0.5)
        ink.ellipse(-30 * f, -40, 9, 18, fill=(1, 1, 1, 0.8), ink=0, shade=0, rot=0.4 * f)
        face_y, face_r = 0, 1.0
    else:  # sugar bowl
        bowl = rgb("f3eee6")
        with ink.outlined(4.5):
            ink.ellipse(0, 10, 66, 52, fill=bowl, fill2=rgb("d8d2c6"), ink=0, shade=0.55)
            ink.ellipse(0, -36, 60, 14, fill=bowl, ink=0, shade=0.3)
            ink.ellipse(0, -48, 14, 10, fill=rgb("c76a9a"), ink=0, shade=0.5)
            ink.arc(-70, 4, 18, 5, 1.4, rot=math.pi / 2, fill=bowl)
            ink.arc(70, 4, 18, 5, 1.4, rot=-math.pi / 2, fill=bowl)
        for k in range(5):
            ink.box(-40 + k * 20, -40 - (k % 2) * 5, 7, 6, 1.5, fill=rgb("ffffff"), ink=2, shade=0.2, rot=k)
        ink.bez(-50, 30, 0, 44, 50, 30, 4, fill=rgb("c76a9a"), ink=0, shade=0)
        face_y, face_r = 2, 1.0
    # face
    ex = 15 * face_r
    look = (p.look[0] * f, p.look[1])
    rig.eye(ink, fx - ex, face_y - 4, 12, 20, look, p.blink, cut=0.7 * f)
    rig.eye(ink, fx + ex, face_y - 4, 12, 20, look, p.blink, cut=0.7 * f)
    ink.ellipse(fx + 6 * f, face_y + 14, 6, 5, fill=rgb("c0473c") if kind != "loaf" else rgb("1e120c"), ink=2.2,
                shade=0.5)
    rig.mouth(ink, fx + 3 * f, face_y + 30, 34, p.mouth * (1 - sq * 0.3))
    rig.blush(ink, fx - 30, face_y + 20, 9)
    rig.blush(ink, fx + 32, face_y + 20, 9)


def draw(ink: Ink, kind: str, x: float, y: float, p: Pose, s: float = 1.0):
    """Hero standing on the ground at (x, y) (feet), about 260 px tall at s=1."""
    st = KINDS[kind]
    f = p.facing
    ph = p.beat % 1.0
    sq = rig.bounce(ph) * (0.5 + 0.5 * p.energy)
    en = 0.5 + p.energy
    air = p.lift > 4 or p.action in ("jump", "parry", "hurt")
    sx_body, sy_body = 1 + 0.10 * sq, 1 - 0.12 * sq
    spin = p.spin * f if p.action == "parry" else 0.0
    with ink.at(x, y - p.lift - (130 * s if spin else 0), spin, s), ink.at(0, 130 if spin else 0):
        # shadow on the ground (stays on the floor)
        with ink.at(0, p.lift, 0, 1.0 - min(p.lift, 200) / 400):
            ink.ellipse(0, -2, 52, 9, fill=(0.15, 0.1, 0.08, 0.28), ink=0, shade=0, soft=3, boil=0)
        hip_y = -88 * sy_body
        # legs
        for side in (-1, 1):
            hx = side * 15
            if p.run is not None:
                q = (p.run + (0.5 if side > 0 else 0.0)) % 1.0
                fx_ = math.sin(q * 2 * math.pi) * 34 * f
                fy_ = -max(0.0, math.cos(q * 2 * math.pi)) * 30
                bend = 0.25 * side
            elif air:
                fx_, fy_ = side * 22 + 10 * f, -40
                bend = 0.35 * side
            else:
                tap = (math.floor(p.beat) % 2 == (0 if side < 0 else 1))
                lift = rig.hop(ph) * 22 * en if tap and p.action in ("dance", "cheer") else 0.0
                if p.style == 1:          # charleston: knees in, heels out
                    fx_ = side * (26 + 14 * math.sin(p.beat * math.pi))
                else:
                    fx_ = side * 26
                fy_ = -lift
                bend = (0.18 + 0.2 * sq) * side
            rig.hose(ink, hx, hip_y, fx_, fy_ - 6, bend, r=7.5)
            rig.shoe(ink, fx_, fy_, f if p.run is not None or side * f > 0 else f, 1.0, st["shoe"],
                     lift=0.6 if fy_ < -5 else 0.0)
        # shorts and torso
        with ink.at(0, hip_y - 14, 0, sx_body, sy_body):
            with ink.outlined(4):
                ink.ellipse(0, -14, 32, 30, fill=rgb("f6efe0"), ink=0, shade=0.45)
                ink.box(0, 10, 34, 18, 12, fill=st["shorts"], ink=0, shade=0.5)
            ink.ellipse(-12, 6, 4, 4, fill=rgb("fff2c0"), ink=1.5, shade=0)
            ink.ellipse(12, 6, 4, 4, fill=rgb("fff2c0"), ink=1.5, shade=0)
        sh_y = hip_y - 42 * sy_body
        head_y = sh_y - 70 * sy_body
        # arms (back one first)
        arms = _arms(p, ph, sq, en, air)
        for side, (hx, hy, ang, gl, bend) in sorted(arms.items(), key=lambda kv: kv[0] * f):
            if side * f < 0:
                rig.hose(ink, side * 26, sh_y, hx, hy, bend, r=6.0)
                rig.glove(ink, hx, hy, ang, gl, side=-side * f if gl == "point" else side, s=0.95)
        with ink.at(0, head_y, 0.03 * math.sin(p.beat * math.pi) * f,
                    sx_body * 1.0, sy_body * 1.0 + 0.04 * sq):
            _head(ink, kind, p, sq)
            if p.hat:
                top = {"pepper": -90, "salt": -90, "loaf": -70, "bulb": -84, "sugar": -62}[kind]
                with ink.at(0, top, -0.15 * f + 0.1 * math.sin(p.beat * math.pi)):
                    with ink.outlined(4):
                        ink.ellipse(0, 0, 74, 14, fill=rgb("f0d890"), ink=0, shade=0.4)
                        ink.box(0, -24, 46, 24, 8, fill=rgb("f0d890"), ink=0, shade=0.4)
                    ink.box(0, -12, 46, 7, 2, fill=rgb("c8372d"), ink=0, shade=0)
        for side, (hx, hy, ang, gl, bend) in sorted(arms.items(), key=lambda kv: kv[0] * f):
            if side * f >= 0:
                rig.hose(ink, side * 26, sh_y, hx, hy, bend, r=6.0)
                rig.glove(ink, hx, hy, ang, gl, side=side if gl != "point" else f, s=0.95)
                if p.cane:
                    tw = math.sin(p.beat * math.pi) * 0.6
                    ink.capsule(hx, hy, hx + math.sin(tw) * 120 * f, hy + math.cos(tw) * 120, 4.5,
                                fill=rgb("2a2420"), ink=2.5)
                    ink.ellipse(hx + math.sin(tw) * 120 * f, hy + math.cos(tw) * 120, 6, fill=rgb("f6efe0"), ink=2)
                if gl == "point" and p.muzzle > 0:
                    tipx = hx + math.cos(ang) * 50
                    tipy = hy + math.sin(ang) * 50
                    ink.star(tipx, tipy, 18 * p.muzzle + 8, 6, 2.5, fill=rgb("fff6c0"), ink=2.5, rot=p.t * 9)


def _arms(p: Pose, ph: float, sq: float, en: float, air: bool) -> dict:
    """side -> (hand x, hand y, glove angle, glove pose, bend), in hero-local coords."""
    f = p.facing
    sh_y = -88 - 42
    out = {}
    for side in (-1, 1):
        front = side * f > 0
        if p.action == "hurt":            # flung back by a hit: hands up, fingers spread
            ang = -math.pi / 2 + side * 1.15 + 0.25 * math.sin(p.t * 30)
            hx, hy = side * 26 + math.cos(ang) * 72, sh_y + math.sin(ang) * 72
            out[side] = (hx, hy, ang, "open", 0.3 * side)
            continue
        if p.action == "ex" and front:    # both hands thrust forward after an EX shot
            ang = 0.0 if f > 0 else math.pi
            hx, hy = side * 26 + math.cos(ang) * 78, sh_y + 6
            out[side] = (hx, hy, ang, "open", 0.05 * side)
            continue
        if p.action == "ex":
            ang = 0.25 if f > 0 else math.pi - 0.25
            hx, hy = side * 20 + math.cos(ang) * 70, sh_y + 16
            out[side] = (hx, hy, ang, "open", 0.05 * side)
            continue
        if p.action == "shoot" and front:
            a = p.aim
            ang = (a if f > 0 else math.pi - a)
            hx, hy = side * 26 + math.cos(ang) * 70, sh_y + math.sin(ang) * 70
            out[side] = (hx, hy, ang, "point", 0.08 * side)
            continue
        if p.action in ("cheer", "parry") or (p.action == "wave" and front):
            wv = math.sin(p.t * 9 + side) * 0.35
            ang = -math.pi / 2 + side * 0.5 + wv
            hx, hy = side * 26 + math.cos(ang) * 74, sh_y + math.sin(ang) * 74
            out[side] = (hx, hy, ang, "open", -0.25 * side)
            continue
        if p.action == "bow":
            out[side] = (side * 30 + 20 * f, sh_y + 80, math.pi / 2, "open", 0.2 * side)
            continue
        if p.run is not None:
            q = (p.run + (0.0 if side > 0 else 0.5)) % 1.0
            sw = math.sin(q * 2 * math.pi)
            hx, hy = side * 26 + sw * 40 * f, sh_y + 46 - abs(sw) * 10
            out[side] = (hx, hy, math.pi / 2 - sw * 0.8 * f, "fist", 0.3 * side)
            continue
        if air:
            out[side] = (side * 62, sh_y - 40, -math.pi / 2 + side * 0.9, "open", -0.3 * side)
            continue
        # dance: swing on the beat, jazz hands when the music is big
        sw = math.sin(p.beat * math.pi + (0 if side > 0 else math.pi))
        up = en - 0.5
        if p.style == 2:     # arms up, waving like a crowd
            ang = -math.pi / 2 + side * (0.45 + 0.25 * sw)
            r = 72
            gl = "open"
        elif p.style == 3:   # finger-snap swing
            ang = math.pi / 2 - side * (0.6 + 0.5 * sw)
            r = 66
            gl = "fist" if sw > 0 else "point"
        else:
            ang = math.pi * (0.5 - side * (0.25 + 0.3 * sw + 0.35 * up))
            r = 70 - 8 * sq
            gl = "open"
        hx, hy = side * 26 + math.cos(ang) * r, sh_y + math.sin(ang) * r
        out[side] = (hx, hy, ang, gl, 0.28 * side * (1 if sw > 0 else -1))
    return out


GHOST = rgb("fbf4ff")


def ghost(ink: Ink, kind: str, x: float, y: float, t: float, beat: float, s: float = 1.0, alpha: float = 1.0):
    """A downed hero's ghost floating up: pale, haloed, little wings beating, glowing pink because the
    partner can parry it back to life."""
    flap = math.sin(beat * math.pi * 2)
    with ink.at(x, y, 0.12 * math.sin(t * 3), s, fade=1 - 0.8 * alpha):
        ink.glow(0, 10, 130, (1.0, 0.45, 0.75, 0.32), soft=55)
        ink.bez(-34, 40, 20 + 30 * math.sin(t * 5), 130, 36 * math.sin(t * 4), 210, 46, 5, fill=GHOST, ink=3, shade=0.2)
        for side in (-1, 1):
            with ink.at(side * 70, -10, side * (0.5 + 0.35 * flap)):
                ink.ellipse(side * 34, 0, 40, 16, fill=GHOST, ink=3, shade=0.2)
        with ink.at(0, 0, 0, 1.0, fade=0.45):
            _head(ink, kind, Pose(t=t, beat=beat, blink=1.0, mouth=0.15, look=(0.0, -1.0)), 0.0)
        ink.ellipse(0, -8, 74, 78, fill=(1.0, 0.95, 1.0, 0.32), ink=0, shade=0)
        ink.ellipse(0, -112, 46, 11, fill=(0, 0, 0, 0), ink=5, shade=0, ink_col=rgb("f0c040"))


def lying(ink: Ink, kind: str, x: float, y: float, p: Pose, s: float = 1.0):
    """A knocked-out hero flat on the floor (eyes shut, stars going round)."""
    p2 = Pose(**{**p.__dict__})
    p2.blink, p2.mouth, p2.action, p2.lift, p2.run, p2.spin = 1.0, 0.05, "dance", 0.0, None, 0.0
    p2.energy = 0.0
    with ink.at(x, y - 38 * s, 0, 1.0, 0.82):
        with ink.at(0, 0, -math.pi / 2 * p.facing):
            draw(ink, kind, 0, 125 * s, p2, s)
    rig.dazed_stars(ink, x - 110 * p.facing * s, y - 90 * s, 46 * s, p.t, n=3)


def tomb(ink: Ink, x: float, y: float, t: float, s: float = 1.0):
    """Where a hero fell and nobody parried their ghost back: a little headstone till the next take."""
    from . import lettering
    with ink.at(x, y, 0.04 * math.sin(t * 2), s):
        with ink.outlined(4):
            ink.box(0, -60, 46, 60, 22, fill=rgb("b8b0a4"), fill2=rgb("8a8478"), ink=0, shade=0.5)
        ink.box(0, -2, 64, 8, 4, fill=rgb("6a8a4a"), ink=3, shade=0.3)
        lettering.words(ink, "RIP", 0, -74, 26, fill=rgb("3a3430"), shadow=None, outline=0.0, weight=5)
        ink.ellipse(-30, -8, 10, 7, fill=rgb("f06a6a"), ink=2, shade=0.3)


def portrait(ink: Ink, kind: str, x: float, y: float, s: float, t: float, beat: float, down: bool = False):
    """The hero's head for the HUD."""
    with ink.at(x, y, 0.06 * math.sin(beat * math.pi), s):
        _head(ink, kind, Pose(t=t, beat=beat, blink=1.0 if down else 0.0, mouth=0.05 if down else 0.35,
                              look=(0.3, 0.0)), 0.0)


def ex_shot(ink: Ink, kind: str, x: float, y: float, t: float, s: float = 1.0):
    """The EX attack each hero throws for one card: a spinning peppercorn bomb, a slice of rye, a salt
    crystal, a lightning bolt or a sugar cube."""
    with ink.at(x, y, t * 12 if kind != "bulb" else 0.0, s):
        ink.glow(0, 0, 70, (1.0, 0.85, 0.5, 0.35), soft=40)
        if kind == "pepper":
            ink.ellipse(0, 0, 34, fill=rgb("3a2a22"), ink=4, shade=0.6)
            ink.ellipse(-10, -12, 9, 6, fill=(1, 1, 1, 0.6), ink=0, shade=0)
            for k in range(5):
                a = k * 1.26
                ink.arc(0, 0, 22, 2, 0.4, rot=a, fill=rgb("1e1410"))
        elif kind == "loaf":
            with ink.outlined(4):
                ink.box(0, 0, 40, 34, 18, fill=rgb("4a2a1c"), ink=0, shade=0.4)
            ink.box(0, 2, 32, 26, 14, fill=rgb("8a6040"), ink=0, shade=0.2)
            for k in range(6):
                ink.ellipse(-20 + k * 8, -8 + 10 * math.sin(k * 2.0), 3, 2, fill=rgb("e6d3a8"), ink=0, shade=0)
        elif kind == "salt":
            ink.box(0, 0, 30, 30, 4, fill=rgb("f4f8fc"), ink=4, shade=0.5, rot=0.785)
            ink.box(-6, -6, 10, 10, 2, fill=(1, 1, 1, 0.8), ink=0, shade=0, rot=0.785)
        elif kind == "bulb":
            pts = [(-30, -40), (8, -6), (-12, 4), (30, 42)]
            for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
                ink.capsule(x0, y0, x1, y1, 12, 9, fill=rgb("fff07a"), ink=4, shade=0)
        else:
            ink.box(0, 0, 28, 28, 6, fill=rgb("fff4f8"), ink=4, shade=0.4)
            for k in range(4):
                ink.ellipse(-12 + 8 * k, -10 + 6 * (k % 2), 3, fill=rgb("c76a9a"), ink=0, shade=0)


SUPER = {"pepper": "sneeze", "salt": "sneeze", "loaf": "giant", "sugar": "giant", "bulb": "flash"}
