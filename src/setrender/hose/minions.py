"""The bosses' sidekicks, drawn in the same rubber-hose style: runners that scuttle along the floor,
flyers that swoop in at head height and poppers that burst up out of the ground. Each boss has its own
cast (walking records and winged quavers for the gramophone, fire imps for the sun, storm puffs for the
cloud, teacups and a boxing mouse for the kettle, bats and grave hands for the organ, crabs and flying
fish for the octopus, rolling nickels and winged 45s for the jukebox, toadstools, bees and a mole for
the oak). A sidekick the peashooters stop pops and tumbles away with stars round its head."""
from __future__ import annotations

import math

from . import rig
from .ctx import Ctx
from .ink import INK, Ink, rgb

WHITE = rgb("fffaf0")


def _legs(ink: Ink, c: Ctx, y_hip: float, run: float, col=rgb("1e1612"), shoe=rgb("5e3320"), s=0.75):
    for side in (-1, 1):
        q = (run + (0.5 if side > 0 else 0.0)) % 1.0
        fx = math.sin(q * 2 * math.pi) * 20
        fy = -max(0.0, math.cos(q * 2 * math.pi)) * 16
        rig.hose(ink, side * 10, y_hip, fx, fy - 4, 0.25 * side, r=5.0, col=col)
        rig.shoe(ink, fx, fy, -1.0, s, shoe)


def _eyes(ink: Ink, x, y, s=1.0, look=(-0.8, 0.1), angry=0.6):
    for side in (-1, 1):
        rig.eye(ink, x + side * 11 * s, y, 9 * s, 13 * s, look, 0.0, cut=-0.6, side=side)
        ink.capsule(x + side * 4 * s, y - 13 * s + 5 * angry * s, x + side * 20 * s, y - 18 * s - 3 * angry * s, 2.6 * s,
                    fill=INK, ink=0, shade=0)


def _wings(ink: Ink, c: Ctx, x, y, s=1.0, col=WHITE, span=46.0):
    flap = math.sin(c.t * 26)
    for side in (-1, 1):
        with ink.at(x + side * 14 * s, y - 6 * s, side * (0.5 + 0.6 * flap)):
            ink.ellipse(side * span * 0.5 * s, 0, span * 0.55 * s, 13 * s, fill=col, ink=3, shade=0.2)


# ---------------------------------------------------------------- runners (feet on the floor at y)

def record_runner(ink: Ink, c: Ctx, x, y, t, run, seed=0.5):
    with ink.at(x, y):
        _legs(ink, c, -20, run)
    with ink.at(x, y - 54, 0.12 * math.sin(c.t * 14)):
        ink.ellipse(0, 0, 40, 42, fill=rgb("2a2420"), ink=4, shade=0.3)
        ink.rings(0, 0, 6, rgb("3a3330"), rgb("1e1816"), radius=40, phase=c.t)
        ink.ellipse(0, 0, 18, fill=rgb("c8372d"), ink=2.5, shade=0.2)
        _eyes(ink, 0, -2, 0.7)
        rig.mouth(ink, 0, 10, 16, 0.5)


def teacup_runner(ink: Ink, c: Ctx, x, y, t, run, seed=0.5):
    with ink.at(x, y):
        _legs(ink, c, -18, run, shoe=rgb("3a6ea8"))
    with ink.at(x, y - 48, 0.1 * math.sin(c.t * 12)):
        ink.ellipse(0, 22, 48, 9, fill=rgb("f6efe0"), ink=3.5, shade=0.3)
        with ink.outlined(4):
            ink.pie(0, -14, 40, 40, cut=0.0, half=1.57, fill=rgb("f6efe0"))
        ink.arc(40, 2, 14, 5, 1.3, rot=-math.pi / 2, fill=rgb("f6efe0"))
        ink.ellipse(0, -14, 38, 7, fill=rgb("8a5a2a"), ink=2.5, shade=0.2)
        for k in range(3):
            ink.ellipse(-16 + 16 * k, 4, 5, fill=rgb("6a8ac8"), ink=0, shade=0)
        _eyes(ink, 0, -32, 0.7)
        for k in range(2):
            q = (c.t * 1.4 + k / 2) % 1.0
            ink.ellipse(-8 + 14 * k, -60 - 50 * q, 8 + 10 * q, fill=(1, 1, 1, 0.7 * (1 - q)), ink=2 * (1 - q), shade=0.2)


def crab_runner(ink: Ink, c: Ctx, x, y, t, run, seed=0.5):
    with ink.at(x, y - 36):
        for side in (-1, 1):
            for k in range(3):
                ph = c.t * 22 + k + (side > 0) * 2
                ink.capsule(side * (14 + 10 * k), 8, side * (34 + 12 * k), 30 + 6 * math.sin(ph), 3.5, fill=rgb("c8372d"),
                            ink=2.5, shade=0)
        ink.ellipse(0, 0, 44, 28, fill=rgb("e0503a"), fill2=rgb("a82a1e"), ink=4, shade=0.5)
        snap = abs(math.sin(c.t * 9))
        for side in (-1, 1):
            with ink.at(side * 52, -26, side * 0.4):
                ink.ellipse(0, 0, 17, 13, fill=rgb("e0503a"), ink=3, shade=0.4)
                ink.tri((side * 6, -4), (side * 26, -14 - 8 * snap), (side * 22, 2), fill=rgb("e0503a"), ink=2.5)
        for side in (-1, 1):
            ink.capsule(side * 10, -22, side * 14, -42, 2.5, fill=rgb("a82a1e"), ink=0, shade=0)
            rig.eye(ink, side * 14, -48, 7, 9, (-0.8, 0), 0.0)


def nickel_runner(ink: Ink, c: Ctx, x, y, t, run, seed=0.5):
    with ink.at(x, y - 42, c.t * 9):
        ink.ellipse(0, 0, 42, fill=rgb("c9ccd2"), fill2=rgb("8a8e98"), ink=4, shade=0.5)
        ink.ellipse(0, 0, 33, fill=(0, 0, 0, 0), ink=2.5, shade=0, ink_col=rgb("6a6e78"))
    _eyes(ink, x, y - 48, 0.75)
    rig.mouth(ink, x, y - 30, 18, 0.4)


def toadstool_runner(ink: Ink, c: Ctx, x, y, t, run, seed=0.5):
    with ink.at(x, y):
        _legs(ink, c, -16, run, shoe=rgb("4a2e20"))
    with ink.at(x, y - 40, 0.1 * math.sin(c.t * 10)):
        ink.box(0, 4, 18, 22, 8, fill=rgb("f2e6c8"), ink=3.5, shade=0.3)
        with ink.outlined(4):
            ink.pie(0, -14, 46, 34, cut=0.0, half=1.57, rot=math.pi, fill=rgb("d9433a"))
        for k in range(4):
            ink.ellipse(-28 + 18 * k, -30 + 6 * (k % 2), 6, 5, fill=WHITE, ink=0, shade=0)
        _eyes(ink, 0, 0, 0.6)


# ---------------------------------------------------------------- flyers (centred at x, y)

def quaver_flyer(ink: Ink, c: Ctx, x, y, t, vx, seed=0.5):
    with ink.at(x, y, 0.2 * math.sin(c.t * 6)):
        _wings(ink, c, 0, -8, 0.9, rgb("2a2420"))
        rig.note(ink, 0, 18, 2.2, INK)
        _eyes(ink, -4, 14, 0.55)


def imp_flyer(ink: Ink, c: Ctx, x, y, t, vx, seed=0.5):
    ang = math.atan2(0.0, vx)
    with ink.at(x, y):
        for k in range(3):
            ink.ellipse(-math.cos(ang) * (26 + 18 * k), -math.sin(ang) * (26 + 18 * k), 22 - 6 * k,
                        fill=rgb("ffb03a", 0.85 - 0.2 * k), ink=0, shade=0)
        ink.glow(0, 0, 60, (1.0, 0.6, 0.2, 0.4), soft=30)
        ink.ellipse(0, 0, 32, fill=rgb("ff7a2a"), fill2=rgb("ffd04a"), ink=4, shade=0.4)
        for side in (-1, 1):
            ink.tri((side * 14, -26), (side * 22, -48), (side * 4, -30), fill=rgb("c8372d"), ink=2.5)
        _eyes(ink, 0, -4, 0.7)
        rig.mouth(ink, 0, 12, 22, 0.55)


def puff_flyer(ink: Ink, c: Ctx, x, y, t, vx, seed=0.5):
    with ink.at(x, y):
        with ink.outlined(4):
            for px, py, r in ((-22, 4, 22), (0, -8, 28), (22, 4, 22)):
                ink.ellipse(px, py, r, fill=rgb("8a90a0"), ink=0, shade=0.4)
        _eyes(ink, 0, -4, 0.65)
        for k in range(3):
            q = (c.t * 3 + k / 3) % 1.0
            ink.capsule(-18 + 18 * k, 28 + 40 * q, -20 + 18 * k, 38 + 40 * q, 2.5, fill=rgb("bfe3ff", 1 - q), ink=0, shade=0)
        if math.sin(c.t * 17) > 0.4:
            ink.capsule(0, 30, -10, 50, 5, fill=rgb("fff07a"), ink=2.5, shade=0)


def bat_flyer(ink: Ink, c: Ctx, x, y, t, vx, seed=0.5):
    flap = math.sin(c.t * 20)
    with ink.at(x, y):
        for side in (-1, 1):
            ink.tri((side * 10, 0), (side * 80, -40 * flap), (side * 60, 24), fill=rgb("2a2230"), ink=3)
        ink.ellipse(0, 0, 24, 22, fill=rgb("2a2230"), ink=3, shade=0.3)
        for side in (-1, 1):
            ink.tri((side * 14, -14), (side * 10, -36), (side * 2, -18), fill=rgb("2a2230"), ink=2)
        _eyes(ink, 0, -2, 0.55)
        ink.tri((-6, 12), (-3, 20), (0, 12), fill=WHITE, ink=1.5)
        ink.tri((6, 12), (3, 20), (0, 12), fill=WHITE, ink=1.5)


def fish_flyer(ink: Ink, c: Ctx, x, y, t, vx, seed=0.5):
    with ink.at(x, y, 0.25 * math.sin(c.t * 5)):
        _wings(ink, c, 4, -6, 0.9, rgb("8ac8e8"), span=52)
        ink.ellipse(0, 0, 40, 20, fill=rgb("5a9ad8"), fill2=rgb("3a6ea8"), ink=4, shade=0.5)
        ink.tri((34, 0), (60, -18), (60, 18), fill=rgb("5a9ad8"), ink=3)
        rig.eye(ink, -22, -4, 7, 9, (-1, 0), 0.0)
        ink.arc(-34, 6, 8, 2, 0.8, fill=INK)


def winged45_flyer(ink: Ink, c: Ctx, x, y, t, vx, seed=0.5):
    with ink.at(x, y):
        _wings(ink, c, 0, 0, 0.9, rgb("ff8ad8"))
        with ink.at(0, 0, c.t * 12):
            ink.ellipse(0, 0, 28, fill=rgb("2a2420"), ink=3.5, shade=0.3)
            ink.ellipse(0, 0, 12, fill=rgb("ffd84a"), ink=2, shade=0)
        _eyes(ink, 0, -2, 0.55)


def bee_flyer(ink: Ink, c: Ctx, x, y, t, vx, seed=0.5):
    with ink.at(x, y + 6 * math.sin(c.t * 30)):
        _wings(ink, c, 4, -18, 0.8, rgb("e8f4ff", 0.85), span=40)
        ink.ellipse(0, 0, 32, 22, fill=rgb("ffd84a"), ink=4, shade=0.4)
        for k in range(2):
            ink.box(6 + 14 * k, 0, 4, 20, 2, fill=INK, ink=0, shade=0)
        ink.tri((30, 0), (46, -4), (30, 6), fill=INK, ink=0)
        _eyes(ink, -14, -4, 0.55)


# ---------------------------------------------------------------- poppers (top at y; the floor at ground)

def mouse_popper(ink: Ink, c: Ctx, x, top, ground, t):
    with ink.at(x, top):
        ink.box(0, 60, 26, 60, 18, fill=rgb("9a9aa4"), ink=4, shade=0.4)
        ink.ellipse(0, 20, 34, 30, fill=rgb("9a9aa4"), ink=4, shade=0.4)
        for side in (-1, 1):
            ink.ellipse(side * 30, -6, 16, fill=rgb("9a9aa4"), ink=3.5, shade=0.3)
            ink.ellipse(side * 30, -6, 8, fill=rgb("f2b5c8"), ink=0, shade=0)
        _eyes(ink, 0, 14, 0.7)
        ink.ellipse(0, 34, 6, 5, fill=rgb("f08aa0"), ink=2, shade=0)
        for side in (-1, 1):
            punch = 14 * abs(math.sin(c.t * 14 + side))
            ink.ellipse(side * (44 + punch), 40, 16, 14, fill=rgb("d9433a"), ink=3.5, shade=0.4)


def hand_popper(ink: Ink, c: Ctx, x, top, ground, t):
    bone = rgb("f4efe0")
    grab = abs(math.sin(c.t * 8))
    with ink.at(x, top + 30, 0.15 * math.sin(c.t * 5)):
        ink.capsule(-6, 20, -6, 150, 9, fill=bone, ink=3.5)
        ink.capsule(10, 20, 10, 150, 8, fill=bone, ink=3.5)
        ink.ellipse(0, 8, 24, 20, fill=bone, ink=3.5, shade=0.3)
        for k in range(4):
            a = -0.9 + 0.6 * k
            l = 34 - 10 * grab
            ink.capsule(math.sin(a) * 18, -6, math.sin(a) * (24 + l * 0.4), -6 - l, 5, fill=bone, ink=3)
        ink.capsule(22, 6, 40, -8 + 10 * grab, 5, fill=bone, ink=3)


def mole_popper(ink: Ink, c: Ctx, x, top, ground, t):
    with ink.at(x, top):
        ink.box(0, 70, 34, 70, 30, fill=rgb("5a4038"), ink=4, shade=0.4)
        ink.ellipse(0, 26, 36, 32, fill=rgb("5a4038"), ink=4, shade=0.4)
        ink.ellipse(0, 46, 12, 9, fill=rgb("f08aa0"), ink=2.5, shade=0.3)
        for side in (-1, 1):
            ink.ellipse(side * 13, 18, 12, fill=rgb("1e1612"), ink=0, shade=0)
            ink.ellipse(side * 13, 18, 14, fill=(0, 0, 0, 0), ink=3.5, shade=0, ink_col=rgb("c9a04a"))
            ink.ellipse(side * 16, 14, 3, fill=(1, 1, 1, 0.8), ink=0, shade=0)
        ink.capsule(-14, 18, 14, 18, 2.5, fill=rgb("c9a04a"), ink=0, shade=0)
        for side in (-1, 1):
            ink.ellipse(side * 38, 58, 14, 10, fill=rgb("f2b5c8"), ink=3, shade=0.3)


# ---------------------------------------------------------------- sidekicks of the five extra bosses

def goat_runner(ink: Ink, c: Ctx, x, y, t, run, seed=0.5):
    from .stages_more import goat
    with ink.at(x, y, 0, -1.0, 1.0):
        goat(ink, c, 0, 0, 0.75, seed * 10, black=seed < 0.45, bounce=0.0)
    # a headbutting goat leans in
    rig.speed_lines(ink, x + 70, y - 60, 0.0, n=2, ln=50)


def ufo_flyer(ink: Ink, c: Ctx, x, y, t, vx, seed=0.5):
    with ink.at(x, y, 0.15 * math.sin(c.t * 5)):
        ink.ellipse(0, -14, 24, 18, fill=rgb("bfe6ff", 0.85), ink=3, shade=0.3)
        ink.ellipse(0, 0, 58, 15, fill=rgb("b8bcc4"), ink=3.5, shade=0.5)
        for k in range(3):
            ink.ellipse(-30 + 30 * k, 4, 5, fill=rgb("ffe37a") if (int(c.beat * 4) + k) % 2 else rgb("7a6a3a"), ink=0,
                        shade=0)
        rig.eye(ink, -6, -16, 5, 8, (-0.8, 0.4), 0.0)
        rig.eye(ink, 6, -16, 5, 8, (-0.8, 0.4), 0.0)


def babyjelly_flyer(ink: Ink, c: Ctx, x, y, t, vx, seed=0.5):
    from .stages_more import hanging_jelly
    with ink.at(x, y - 70):
        ink.glow(0, 70, 55, (1.0, 0.6, 0.85, 0.4), soft=26)
        hanging_jelly(ink, c, 0, 0, 1.3, seed * 9)


def speaker_runner(ink: Ink, c: Ctx, x, y, t, run, seed=0.5):
    with ink.at(x, y, 0, 0.8):
        _legs(ink, c, -14, run, shoe=rgb("2a2024"))
    with ink.at(x, y - 50, 0.1 * math.sin(c.t * 12), 0.8):
        ink.box(0, 0, 34, 46, 6, fill=rgb("2a2430"), ink=4, shade=0.3)
        ink.ellipse(0, 12, 22 * (1 + 0.2 * c.sub), fill=rgb("4a4450"), ink=3, shade=0.4)
        ink.ellipse(0, -26, 9, fill=rgb("4a4450"), ink=2.5, shade=0.4)
        _eyes(ink, 0, -10, 0.55)


def smiley_flyer(ink: Ink, c: Ctx, x, y, t, vx, seed=0.5):
    with ink.at(x, y, 0.3 * math.sin(c.t * 4)):
        _wings(ink, c, 0, 0, 0.9, rgb("fffaf0"))
        ink.ellipse(0, 0, 34, fill=rgb("ffe02a"), ink=4, shade=0.4)
        ink.ellipse(-12, -8, 5, 9, fill=INK, ink=0, shade=0)
        ink.ellipse(12, -8, 5, 9, fill=INK, ink=0, shade=0)
        ink.arc(0, 2, 20, 4, 1.1, fill=INK)


def goon_runner(ink: Ink, c: Ctx, x, y, t, run, seed=0.5):
    """An 8-bit henchman in a fedora, two frames of walk."""
    p = 5
    frame = int(run * 2) % 2
    rows = ["..HHHH..", ".HHHHHH.", "..FFFF..", "..FEFE..", "..FFFF..", ".SSSSSS.", "SSSSSSSS", ".SSSSSS.",
            ".SS..SS." if frame else "SS....SS", "BB....BB" if frame else ".BB..BB."]
    cols = {"H": rgb("2a2632"), "F": rgb("f2c8a0"), "E": INK, "S": rgb("4a4a5a"), "B": rgb("1e1612")}
    for j, row in enumerate(rows):
        for i, ch in enumerate(row):
            if ch in cols:
                ink.box(x + (i - 3.5) * p * 2, y - (len(rows) - j) * p * 2 + p, p, p, 0, fill=cols[ch], ink=1.5, shade=0,
                        boil=0.2)


def coin_flyer(ink: Ink, c: Ctx, x, y, t, vx, seed=0.5):
    with ink.at(x, y):
        _wings(ink, c, 0, 0, 0.8, rgb("fffaf0"))
        with ink.at(0, 0, 0, abs(math.cos(c.t * 8)) * 0.8 + 0.2, 1.0):
            ink.ellipse(0, 0, 26, 30, fill=rgb("ffd84a"), ink=4, shade=0.5)
            ink.box(0, 0, 5, 16, 2, fill=rgb("e0a020"), ink=0, shade=0)


def popcorn_runner(ink: Ink, c: Ctx, x, y, t, run, seed=0.5):
    with ink.at(x, y, 0, 0.8):
        _legs(ink, c, -14, run, shoe=rgb("5e3320"))
    with ink.at(x, y - 48, 0.1 * math.sin(c.t * 12), 0.8):
        with ink.outlined(4):
            ink.tri((-34, -40), (34, -40), (22, 34), fill=rgb("f6efe0"), ink=0, rnd=6)
            ink.tri((-34, -40), (-22, 34), (22, 34), fill=rgb("f6efe0"), ink=0, rnd=6)
        for k in range(3):
            ink.box(-20 + 20 * k, -2, 5, 34, 2, fill=rgb("d9433a"), ink=0, shade=0)
        for k in range(6):
            ink.ellipse(-28 + 11 * k, -46 - 8 * (k % 2), 11, fill=rgb("fff6c0"), ink=2, shade=0.2)
        _eyes(ink, 0, -16, 0.55)


def reel_flyer(ink: Ink, c: Ctx, x, y, t, vx, seed=0.5):
    with ink.at(x, y):
        _wings(ink, c, 0, 0, 0.9, rgb("fffaf0"))
        with ink.at(0, 0, c.t * 10):
            ink.ellipse(0, 0, 30, fill=rgb("c0c4cc"), ink=4, shade=0.4)
            for j in range(4):
                a = j * math.pi / 2
                ink.ellipse(math.cos(a) * 15, math.sin(a) * 15, 7, fill=rgb("22222a"), ink=0, shade=0)
        _eyes(ink, 0, -4, 0.5)


# ---------------------------------------------------------------- the side villain: a cheeky mate-soda bottle

def mate_runner(ink: Ink, c: Ctx, x, y, t, run, seed=0.5, prop=False):
    """A lanky amber bottle of caffeinated mate soda with a tilted crown cap for a hat and leafy hair.
    It turns up in everyone's fight (a parody mascot, not the real one)."""
    if prop is False:  # on the floor it comes at you sideways, cap first, skidding along on its back
        with ink.at(x, y - 30, -math.pi / 2 + 0.1 * math.sin(c.t * 14), 0.62):
            mate_runner(ink, c, 0, -10, t, run, seed, prop=None)
        rig.speed_lines(ink, x + 80, y - 30, 0.0, n=3, ln=60)
        return
    with ink.at(x, y, 0.12 * math.sin(c.t * 11)):
        with ink.outlined(4):
            ink.capsule(0, 60, 0, -30, 30, fill=rgb("c87a2a", 0.95), ink=0, shade=0.4)
            ink.capsule(0, -30, 0, -78, 12, fill=rgb("c87a2a", 0.95), ink=0, shade=0.4)
        ink.box(0, 20, 30, 26, 6, fill=rgb("f6efd0"), ink=3, shade=0.2)
        ink.bez(-26, 34, 0, 22, 26, 34, 3, fill=rgb("3a8a3a"), ink=0, shade=0)
        ink.box(-12, -10, 4, 30, 2, fill=(1, 1, 1, 0.4), ink=0, shade=0)
        for k in range(3):    # leafy hair
            ink.ellipse(-12 + 12 * k, -96, 7, 13, fill=rgb("4aa84a"), ink=2, shade=0.2, rot=(k - 1) * 0.6)
        with ink.at(4, -84, -0.35):
            ink.box(0, 0, 16, 6, 2, fill=rgb("e8c43a"), ink=2.5, shade=0.3)
            for k in range(5):
                ink.tri((-16 + 8 * k, 6), (-12 + 8 * k, 12), (-8 + 8 * k, 6), fill=rgb("e8c43a"), ink=1.5)
        _eyes(ink, 0, 14, 0.62, angry=0.9)
        rig.mouth(ink, 0, 34, 20, 0.5)
        if prop is True:
            with ink.at(0, -110):
                ink.capsule(0, 0, 0, 14, 3, fill=INK, ink=0, shade=0)
                bl = abs(math.sin(c.t * 40))
                ink.ellipse(0, -2, 46 * bl + 6, 6, fill=rgb("c8372d"), ink=2.5, shade=0.2)


def mate_flyer(ink: Ink, c: Ctx, x, y, t, vx, seed=0.5):
    mate_runner(ink, c, x, y, t, 0.0, seed, prop=True)


def is_mate(s) -> bool:
    return s.kind in ("runner", "flyer") and (s.seed * 7.31) % 1.0 < 0.22


RUNNERS = {"gramophone": record_runner, "kettle": teacup_runner, "octopus": crab_runner, "jukebox": nickel_runner,
           "oak": toadstool_runner, "jelly": goat_runner, "hamhock": goat_runner, "lava": speaker_runner,
           "don": goon_runner, "projectionist": popcorn_runner}
FLYERS = {"gramophone": quaver_flyer, "sun": imp_flyer, "cloud": puff_flyer, "organ": bat_flyer, "octopus": fish_flyer,
          "jukebox": winged45_flyer, "oak": bee_flyer, "jelly": babyjelly_flyer, "hamhock": ufo_flyer,
          "lava": smiley_flyer, "don": coin_flyer, "projectionist": reel_flyer}
POPPERS = {"kettle": mouse_popper, "organ": hand_popper, "oak": mole_popper}


SCALE = 1.25


def draw(ink: Ink, c: Ctx, boss: str, s, x: float, y: float, tt: float, ground: float, vx: float = -1.0):
    """One sidekick at (x, y) tt seconds after it set off (the shot it is, in combat terms)."""
    k = SCALE
    if s.kind == "runner":
        fn = mate_runner if is_mate(s) else RUNNERS.get(boss, record_runner)
        with ink.at(x, ground, 0, k):
            fn(ink, c, 0, 0, tt, (tt * 3.2) % 1.0, seed=s.seed)
    elif s.kind == "flyer":
        fn = mate_flyer if is_mate(s) else FLYERS.get(boss, quaver_flyer)
        with ink.at(x, y, 0, k):
            fn(ink, c, 0, 0, tt, vx, seed=s.seed)
    else:
        warn = tt < s.p1 - 0.05
        if warn:              # the floor cracks and shakes before it bursts out
            q0 = min(1.0, tt / max(s.p1 - 0.05, 1e-3))
            for j in range(5):
                q = (c.t * 4 + j / 5) % 1.0
                ink.ellipse(x - 40 + 20 * j, ground - 6 - 30 * q * q0, 5 + 4 * q0, 4, fill=rgb("8a6a4a", 1 - q), ink=1.5,
                            shade=0)
            rig.stroke(ink, [(x - 60 * q0, ground - 2), (x - 20, ground - 8), (x, ground), (x + 25, ground - 7),
                             (x + 60 * q0, ground - 1)], 4.5)
            return
        fn = POPPERS.get(boss, mole_popper)
        with ink.at(x, y, 0, k):
            fn(ink, c, 0, 0, (ground - y) / k, tt)
        ink.ellipse(x, ground + 6, 90, 22, fill=rgb("6a4a2a"), ink=4, shade=0.4)
        for j in range(4):
            ink.ellipse(x - 60 + 40 * j, ground - 4, 16, 11, fill=rgb("8a6a4a"), ink=3, shade=0.3)


def popped(ink: Ink, c: Ctx, boss: str, s, x: float, y: float, q: float, ground: float):
    """Shot down: a pop, then it tumbles off with stars round its head."""
    if q < 0.35:
        rig.impact(ink, x, y if s.kind != "runner" else ground - 50, 90, q / 0.35, col=rgb("fff3c4"))
    k = min(1.0, q)
    with ink.at(0, 0, fade=k ** 2):
        yy = (y if s.kind != "runner" else ground - 50) - 260 * math.sin(math.pi * k * 0.7) + 500 * k * k
        with ink.at(x + 160 * k, yy, 9 * k, SCALE):
            if s.kind == "runner":
                (mate_runner if is_mate(s) else RUNNERS.get(boss, record_runner))(ink, c, 0, 50, 0.0, 0.0, seed=s.seed)
            elif s.kind == "flyer":
                (mate_flyer if is_mate(s) else FLYERS.get(boss, quaver_flyer))(ink, c, 0, 0, 0.0, -1.0, seed=s.seed)
            else:
                POPPERS.get(boss, mole_popper)(ink, c, 0, -60, 0, 0.0)
        rig.dazed_stars(ink, x + 160 * k, yy - 70, 40, c.t, n=3)
