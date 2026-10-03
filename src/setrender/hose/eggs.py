"""Easter eggs, about one a minute (story.schedule_eggs deals them out): slapstick on the boss (a
cream pie, an anvil, the animator's pencil drawing on a moustache, a bomb kicked back), projection-booth
gags (a fly on the lens, a hand-shadow rabbit from the audience, the film slipping its sprockets),
nods to the other two templates (the burned-out DJ car, jellyfish, a UFO after a cow), rave and geek
culture (an acid smiley, a mirror ball, a cassette and a pencil, an 8-bit invader, the Konami code on
the joypad, a walking metronome) and a few that the heroes join in (a bowling ball to hop, a banana
peel, a ? block to bump). Everything is original artwork in the rubber-hose style."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from . import heroes, lettering, rig
from .ctx import Ctx
from .ink import GLOW, INK, Ink, mix, rgb
from .story import Gag, h01

W, H = 1920.0, 1080.0
PRIDE = [  # stripes of identity flags, for the balloons
    [rgb("e40303"), rgb("ff8c00"), rgb("ffed00"), rgb("008026"), rgb("004dff"), rgb("750787")],
    [rgb("5bcefa"), rgb("f5a9b8"), rgb("ffffff"), rgb("f5a9b8"), rgb("5bcefa")],
    [rgb("d60270"), rgb("d60270"), rgb("9b4f96"), rgb("0038a8"), rgb("0038a8")],
    [rgb("fcf434"), rgb("ffffff"), rgb("9c59d1"), rgb("2c2c2c")],
    [rgb("ff218c"), rgb("ffd800"), rgb("21b1ff")],
    [rgb("d52d00"), rgb("ff9a56"), rgb("ffffff"), rgb("d362a4"), rgb("a30262")],
]


@dataclass
class Where:
    """What an egg needs to know about the picture it lands in."""
    mode: str = "fight"                    # fight | inter | card
    sky: bool = False
    ground: float = 905.0
    face: tuple | None = None              # boss face (x, y, r) on screen
    top: tuple | None = None               # top of the boss's head
    heroes: list = field(default_factory=list)   # hero (x, y) at the egg's key moment
    ball_x: float | None = None            # bowling ball x (from the fight plan)


LAYER = {"pie": "front", "anvil": "front", "pencil": "screen", "fly": "screen", "shadow": "screen", "slip": "none",
         "balloons": "front", "ufo": "back", "jelly": "front", "smiley": "front", "discoball": "front",
         "cassette": "screen", "invader": "back", "qblock": "front", "pipe": "front", "stagehand": "screen",
         "bowling": "front", "bomb": "front", "metronome": "front", "cuckoo": "screen", "plane": "front",
         "hotair": "back", "car": "back", "bat": "back", "konami": "screen", "banana": "front"}


def _ease(u):
    u = min(1.0, max(0.0, u))
    return u * u * (3 - 2 * u)


def _across(u: float, side: float, margin=200.0) -> float:
    return -margin + (W + 2 * margin) * u if side < 0 else W + margin - (W + 2 * margin) * u


# ---------------------------------------------------------------- slapstick on the boss

def pie(ink: Ink, c: Ctx, g: Gag, u: float, w: Where):
    if w.face is None or u >= 0.18:
        return
    fx, fy, _ = w.face
    q = u / 0.18
    x = -120 + (fx + 120) * q
    y = 560 + (fy - 560) * q - 260 * math.sin(math.pi * q)
    with ink.at(x, y, q * 7):
        ink.ellipse(0, 10, 70, 22, fill=rgb("c88a4a"), ink=4, shade=0.4)
        ink.ellipse(0, -2, 66, 24, fill=rgb("fffaf0"), ink=4, shade=0.3)
        ink.ellipse(0, -10, 10, fill=rgb("c8372d"), ink=2, shade=0.3)


def anvil(ink: Ink, c: Ctx, g: Gag, u: float, w: Where):
    if w.top is None:
        return
    tx, ty = w.top
    land = 0.28
    if u < land:
        q = u / land
        y = -200 + (ty + 200) * q * q
        x, rot = tx, 0.0
        ink.ellipse(tx, ty + 30, 90 * q, 16 * q, fill=(0, 0, 0, 0.25 * q), ink=0, shade=0, soft=6)
    else:
        q = (u - land) / (1 - land)
        x = tx + 500 * q
        y = ty - 380 * q + 1500 * q * q
        rot = 4 * q
    with ink.at(x, y - 50, rot):
        with ink.outlined(5):
            ink.box(0, -40, 100, 26, 6, fill=rgb("4a4c54"), ink=0, shade=0.5)
            ink.tri((-100, -66), (-170, -50), (-100, -18), fill=rgb("4a4c54"), ink=0)
            ink.box(0, 0, 42, 30, 4, fill=rgb("3a3c44"), ink=0, shade=0.4)
            ink.box(0, 38, 80, 14, 4, fill=rgb("3a3c44"), ink=0, shade=0.4)
        ink.box(-30, -52, 40, 5, 2, fill=(1, 1, 1, 0.35), ink=0, shade=0)
    if land <= u < land + 0.3:
        q = (u - land) / 0.3
        rig.impact(ink, tx, ty - 20, 150, q)
        lettering.words(ink, "CLANG!", tx - 330, ty + 90 - 40 * q, 80, fill=rgb("fff2b0"), wobble=2.0, t=c.t)
    if u >= land:
        rig.dazed_stars(ink, tx, ty - 40, 110, c.t, n=5)


def pencil(ink: Ink, c: Ctx, g: Gag, u: float, w: Where):
    """The animator's hand comes in from the top and pencils a moustache on the boss, then rubs it out."""
    if w.face is None:
        return
    fx, fy, r = w.face
    k = min(_ease(u / 0.12), _ease((1 - u) / 0.1))
    draw_u = min(1.0, max(0.0, (u - 0.12) / 0.25))
    erase = u > 0.8
    sx = fx + 40 * math.sin(draw_u * 14) * (draw_u < 1) + (60 * math.sin(c.t * 18) if erase else 0)
    sy = fy + 0.25 * r
    x = sx + (1 - k) * 700
    y = sy - (1 - k) * 900
    with ink.at(x, y, -0.6 if not erase else 2.5):
        ink.capsule(0, 0, 0, -300, 16, fill=rgb("f2c03a"), ink=4, shade=0.4)
        if not erase:
            ink.tri((-16, 0), (16, 0), (0, 44), fill=rgb("f2d8a8"), ink=3)
            ink.tri((-6, 30), (6, 30), (0, 44), fill=INK, ink=0)
            ink.box(0, -306, 17, 22, 6, fill=rgb("f08aa0"), ink=3, shade=0.3)
        else:
            ink.box(0, 4, 17, 22, 6, fill=rgb("f08aa0"), ink=3, shade=0.3)
        ink.box(0, -280, 18, 10, 2, fill=rgb("c0c0c4"), ink=3, shade=0.4)
        rig.glove(ink, -30, -200, -1.2, "fist", side=1, s=2.6)
        rig.hose(ink, -60, -240, -200, -700, 0.15, r=22)
    if erase:
        for j in range(4):
            q = (c.t * 2 + j / 4) % 1.0
            ink.ellipse(sx - 60 + 40 * j, sy + 40 + 120 * q, 6, 4, fill=rgb("f08aa0", 1 - q), ink=0, shade=0)


def bomb(ink: Ink, c: Ctx, g: Gag, u: float, w: Where):
    """A bomb with a lit fuse rolls in, bounces off a hero's head straight back at the boss and goes off."""
    if w.face is None or not w.heroes:
        return
    fx, fy, _ = w.face
    hx, hy = w.heroes[0]
    if u < 0.35:
        q = u / 0.35
        x, y = -100 + (hx + 100) * q, w.ground - 40 - 160 * abs(math.sin(q * math.pi * 3)) * (1 - q)
    elif u < 0.55:
        q = (u - 0.35) / 0.2
        x, y = hx + (fx - hx) * q, (hy - 300) + (fy - hy + 300) * q - 400 * math.sin(math.pi * q)
    else:
        q = (u - 0.55) / 0.45
        if q < 0.35:
            rig.impact(ink, fx, fy, 260, q / 0.35, col=rgb("ffc04a"))
            rig.impact(ink, fx + 60, fy - 60, 170, min(1.0, q / 0.3 + 0.2))
            lettering.words(ink, "BOOM!", fx - 260, fy - 220, 110, fill=rgb("ffb03a"), wobble=2.0, t=c.t)
        return
    with ink.at(x, y, c.t * 6):
        ink.ellipse(0, 0, 40, fill=rgb("26222a"), ink=4, shade=0.6)
        ink.ellipse(-12, -14, 10, 7, fill=(1, 1, 1, 0.5), ink=0, shade=0)
        ink.box(0, -42, 14, 8, 3, fill=rgb("5a5660"), ink=3, shade=0.3)
        ink.bez(0, -50, 16, -70, 6, -86, 3, fill=rgb("c8a060"), ink=0, shade=0)
    sp = 0.6 + 0.4 * math.sin(c.t * 40)
    ink.star(x + 6, y - 88, 16 * sp, 6, 2.4, fill=rgb("ffd84a"), ink=2, rot=c.t * 9)


# ---------------------------------------------------------------- the projection booth

def fly(ink: Ink, c: Ctx, g: Gag, u: float, w: Where):
    """A fly lands on the projector lens: a huge, blurry silhouette strolling across the picture."""
    if u < 0.15:
        q = u / 0.15
        x, y = 1500 - 900 * (1 - q), 300 - 300 * (1 - q)
    elif u < 0.85:
        q = (u - 0.15) / 0.7
        x, y = 1500 - 700 * q + 30 * math.sin(q * 20), 300 + 260 * q
    else:
        q = (u - 0.85) / 0.15
        x, y = 800 - 900 * q, 560 - 700 * q
    walking = 0.15 <= u < 0.85
    with ink.at(x, y, -0.4, 1.9, soft=16.0):
        col = (0.05, 0.04, 0.04, 0.82)
        for k in range(3):
            for side in (-1, 1):
                ph = c.t * 14 + k * 2 + (side > 0) * 3
                ang = side * (0.8 + 0.35 * k) + (0.2 * math.sin(ph) if walking else 0)
                ink.capsule(0, 20 * k - 20, math.cos(ang) * 190 * side * side, 20 * k - 20 + math.sin(ang) * 150 + 40,
                            6, fill=col, ink=0, shade=0)
        ink.ellipse(0, 0, 70, 110, fill=col, ink=0, shade=0)
        ink.ellipse(0, -130, 60, 55, fill=col, ink=0, shade=0)
        fl = 1.0 if walking else math.sin(c.t * 80)
        for side in (-1, 1):
            ink.ellipse(side * 90, -30, 110, 50 * (0.6 + 0.4 * fl), fill=(0.3, 0.3, 0.32, 0.35), ink=0, shade=0,
                        rot=side * 0.6)


def shadow(ink: Ink, c: Ctx, g: Gag, u: float, w: Where):
    """Someone in the audience makes a hand-shadow animal in the projector beam."""
    k = min(_ease(u / 0.15), _ease((1 - u) / 0.15))
    x = 1000 + 300 * (g.seed - 0.5)
    y = 1080 + 420 - 520 * k
    col = (0.04, 0.03, 0.03, 0.78)
    talk = c.squash
    with ink.at(x, y, -0.15, 1.0, soft=10.0):
        ink.capsule(-260, 260, -60, 60, 150, 110, fill=col, ink=0, shade=0)
        if g.seed < 0.5:          # rabbit
            ink.ellipse(0, -30, 150, 105, fill=col, ink=0, shade=0)
            for e in (-1, 1):
                ink.capsule(30 * e - 20, -110, 70 * e - 40, -380 + 30 * math.sin(c.t * 3 + e), 34, 24, fill=col, ink=0,
                            shade=0)
            ink.ellipse(110, 10 + 20 * talk, 60, 34, fill=col, ink=0, shade=0)
            ink.ellipse(30, -60, 12, 9, fill=(0.9, 0.85, 0.7, 0.0), ink=0, shade=0)
        else:                     # dog that barks on the beat
            ink.ellipse(0, -20, 160, 100, fill=col, ink=0, shade=0)
            ink.capsule(-60, -80, -120, -220, 40, 26, fill=col, ink=0, shade=0)
            with ink.at(120, -30, -0.25 * talk):
                ink.capsule(0, 0, 150, -10, 46, 30, fill=col, ink=0, shade=0)
            with ink.at(120, 30, 0.35 * talk):
                ink.capsule(0, 0, 140, 16, 40, 24, fill=col, ink=0, shade=0)


def frame_slip(u: float) -> float:
    """The film slips a frame: the picture rolls down one frame height (the frame line passing
    through), then catches again. Returns the roll in pixels."""
    if u >= 0.55:
        return 0.0
    q = u / 0.55
    return H * q * q * (3 - 2 * q)


# ---------------------------------------------------------------- nods: other templates, identity, rave, geek

def balloons(ink: Ink, c: Ctx, g: Gag, u: float, w: Where):
    """A bunch of balloons in pride-flag stripes floats up through the picture."""
    x = (260 if g.side < 0 else W - 260) + 60 * math.sin(c.t * 0.8)
    y = 1250 - 1700 * u
    knot = (x, y + 330)
    for k, flag in enumerate(PRIDE):
        bx = x - 150 + (k % 3) * 150 + 20 * math.sin(c.t * 1.3 + k)
        by = y - (k // 3) * 150 + 12 * math.sin(c.beat * math.pi + k)
        ink.bez(bx, by + 70, (bx + knot[0]) / 2 + 20, by + 200, *knot, 2, fill=INK, ink=0, shade=0)
        with ink.at(bx, by, 0.1 * math.sin(c.t + k)):
            with ink.outlined(4):
                ink.ellipse(0, 0, 58, 70, fill=flag[0], ink=0, shade=0.2)
            n = len(flag)
            for j, col in enumerate(flag):
                hh = 140 / n
                yy = -70 + hh * (j + 0.5)
                half = 58 * math.sqrt(max(0.0, 1 - (yy / 70) ** 2)) - 2
                if half > 3:
                    ink.box(0, yy, half, hh / 2 + 0.6, 0, fill=col, ink=0, shade=0, boil=0.3)
            ink.ellipse(-20, -30, 12, 20, fill=(1, 1, 1, 0.45), ink=0, shade=0, rot=0.4)
            ink.tri((-8, 70), (8, 70), (0, 82), fill=flag[0], ink=2)


def ufo(ink: Ink, c: Ctx, g: Gag, u: float, w: Where):
    """A little saucer crosses the sky and beams up a cow (a nod to the cropcircle template)."""
    x = _across(u, g.side, 250)
    y = 170 + 20 * math.sin(c.t * 2)
    beam = 0.3 < u < 0.7
    if beam and not w.sky:
        q = (u - 0.3) / 0.4
        ink.tri((x - 40, y + 20), (x - 150, w.ground - 120), (x + 150, w.ground - 120), fill=(1.0, 0.95, 0.6, 0.25),
                ink=0, mat=GLOW)
        cy = w.ground - 150 - (w.ground - 300 - y) * _ease(q)
        with ink.at(x, cy, 0.4 * math.sin(c.t * 3), 0.5):
            ink.ellipse(0, 0, 70, 40, fill=rgb("fbf7ec"), ink=4, shade=0.3)
            ink.ellipse(-20, -10, 18, 12, fill=INK, ink=0, shade=0)
            ink.ellipse(30, 8, 14, 10, fill=INK, ink=0, shade=0)
            ink.ellipse(78, -16, 28, 24, fill=rgb("fbf7ec"), ink=4, shade=0.3)
            for k in range(4):
                ink.capsule(-40 + k * 26, 30, -40 + k * 26 + 10 * math.sin(c.t * 9 + k), 70, 6, fill=rgb("fbf7ec"),
                            ink=3)
    with ink.at(x, y, 0.08 * math.sin(c.t * 3)):
        ink.ellipse(0, -18, 46, 34, fill=rgb("bfe6ff", 0.85), ink=4, shade=0.3)
        ink.ellipse(0, 0, 120, 26, fill=rgb("b8bcc4"), fill2=rgb("7a7e88"), ink=4, shade=0.5)
        for k in range(5):
            on = (int(c.beat * 2) + k) % 2 == 0
            ink.ellipse(-80 + k * 40, 6, 8, fill=rgb("ffe37a") if on else rgb("7a6a3a"), ink=2, shade=0)
        rig.eye(ink, -10, -22, 8, 12, (0.5 if g.side < 0 else -0.5, 0.5), 0.0)
        rig.eye(ink, 12, -22, 8, 12, (0.5 if g.side < 0 else -0.5, 0.5), 0.0)


def jelly(ink: Ink, c: Ctx, g: Gag, u: float, w: Where):
    """A jellyfish drifts by in the breeze, its bell pumping on the beat (knisper's jellyfish in the trees)."""
    x = _across(u, g.side, 200)
    y = 330 + 120 * math.sin(u * 5 + g.seed * 6)
    pump = c.squash
    with ink.at(x, y, 0.15 * math.sin(c.t * 1.5)):
        ink.glow(0, 0, 150, (1.0, 0.6, 0.85, 0.3), soft=60)
        for k in range(6):
            sx = -60 + k * 24
            ink.bez(sx, 30, sx + 40 * math.sin(c.t * 3 + k), 140, sx + 20 * math.sin(c.t * 2 + k * 1.3) - 30 * g.side,
                    240 + 20 * pump, 6, 2, fill=rgb("f4b8e0"), ink=2, shade=0)
        with ink.outlined(4):
            ink.pie(0, 30, 90 * (1 + 0.12 * pump), 85 * (1 - 0.1 * pump), cut=0.0, half=1.57, rot=math.pi, fill=rgb("f08ac8"))
        ink.ellipse(-30, -20, 18, 26, fill=(1, 1, 1, 0.5), ink=0, shade=0, rot=0.4)
        rig.eye(ink, -22, 0, 10, 15, (0, 0.2), 0.0)
        rig.eye(ink, 22, 0, 10, 15, (0, 0.2), 0.0)
        rig.mouth(ink, 0, 22, 30, 0.3 + 0.4 * pump)


def smiley(ink: Ink, c: Ctx, g: Gag, u: float, w: Where):
    """The acid-house smiley bounces across the bottom of the picture, one bounce a beat."""
    x = _across(u, g.side, 120)
    f = c.beat % 1.0
    y = (w.ground if not w.sky else 960) - 60 - 220 * math.sin(math.pi * f)
    sq = math.exp(-f * 9)
    with ink.at(x, y, 0.3 * math.sin(c.beat * math.pi), 1 + 0.2 * sq, 1 - 0.2 * sq):
        ink.ellipse(0, 0, 60, fill=rgb("ffe02a"), ink=5, shade=0.4)
        ink.ellipse(-20, -16, 8, 14, fill=INK, ink=0, shade=0)
        ink.ellipse(20, -16, 8, 14, fill=INK, ink=0, shade=0)
        ink.arc(0, 4, 36, 6, 1.1, fill=INK)


def discoball(ink: Ink, c: Ctx, g: Gag, u: float, w: Where):
    """A mirror ball lowers on its cable and throws light round the room."""
    k = min(_ease(u / 0.2), _ease((1 - u) / 0.15))
    x, y = W / 2 + 200 * (g.seed - 0.5), -140 + 300 * k
    ink.capsule(x, -20, x, y - 70, 3, fill=INK, ink=0, shade=0)
    for j in range(18):
        a = j * 2.4 + c.t * 1.2
        rr = 200 + 600 * ((j * 0.37) % 1.0)
        ink.ellipse(x + math.cos(a) * rr * 1.6, y + 220 + math.sin(a) * rr * 0.6, 9, 6,
                    fill=(1.0, 1.0, 0.9, 0.55 * k), ink=0, shade=0, mat=GLOW, soft=4)
    with ink.at(x, y, 0.0, k):
        ink.glow(0, 0, 120, (1, 1, 0.9, 0.35), soft=50)
        ink.ellipse(0, 0, 72, fill=rgb("c0c4cc"), ink=5, shade=0.4)
        for j in range(5):
            for i in range(5):
                xx, yy = -48 + i * 24 + (c.t * 30) % 24, -48 + j * 24
                if xx * xx + yy * yy < 62 * 62:
                    lit = ((i + j + int(c.t * 8)) % 3 == 0)
                    ink.box(xx, yy, 9, 9, 1, fill=rgb("ffffff") if lit else rgb("8a8e98"), ink=1.5, shade=0)


def cassette(ink: Ink, c: Ctx, g: Gag, u: float, w: Where):
    """A cassette in the corner being wound back with a pencil, the way it was done."""
    k = min(_ease(u / 0.12), _ease((1 - u) / 0.12))
    x, y = (230 if g.side < 0 else W - 230), 170 - (1 - k) * 360
    with ink.at(x, y, -0.12, 1.0):
        with ink.outlined(5):
            ink.box(0, 0, 150, 92, 10, fill=rgb("2a2a30"), ink=0, shade=0.4)
        ink.box(0, -30, 120, 34, 6, fill=rgb("f6efe0"), ink=3, shade=0.2)
        ink.box(0, -30, 110, 6, 2, fill=rgb("c8372d"), ink=0, shade=0)
        ink.box(0, 40, 70, 22, 6, fill=rgb("4a4a52"), ink=3, shade=0.2)
        for side in (-1, 1):
            with ink.at(side * 60, 10, c.t * (8 if side < 0 else 6)):
                ink.ellipse(0, 0, 24, fill=rgb("f6efe0"), ink=3, shade=0.3)
                for j in range(6):
                    ink.box(math.cos(j * 1.05) * 14, math.sin(j * 1.05) * 14, 4, 4, 1, fill=INK, ink=0, shade=0,
                            rot=j * 1.05)
        with ink.at(-60, 10, c.t * 8):
            ink.capsule(0, 0, 0, -160, 10, fill=rgb("f2c03a"), ink=3, shade=0.4)
            ink.box(0, -164, 11, 12, 4, fill=rgb("f08aa0"), ink=2.5, shade=0.3)


def invader(ink: Ink, c: Ctx, g: Gag, u: float, w: Where):
    """An 8-bit space invader marches along the top in big blocky pixels, then pops."""
    rows = ["..X.....X..", "...X...X...", "..XXXXXXX..", ".XX.XXX.XX.", "XXXXXXXXXXX", "X.XXXXXXX.X",
            "X.X.....X.X", "...XX.XX..."]
    alt = ["..X.....X..", "X..X...X..X", "X.XXXXXXX.X", "XXX.XXX.XXX", "XXXXXXXXXXX", ".XXXXXXXXX.",
           "..X.....X..", ".X.......X."]
    pix = rows if int(c.beat) % 2 == 0 else alt
    x = _across(min(u / 0.9, 1.0), g.side, 200)
    y = 130 + 40 * (int(c.beat / 4) % 3)
    if u > 0.9:
        rig.impact(ink, x, y, 120, (u - 0.9) / 0.1, col=rgb("bfffbf"))
        return
    p = 11
    col = rgb("7aff7a")
    for j, row in enumerate(pix):
        for i, ch in enumerate(row):
            if ch == "X":
                ink.box(x + (i - 5) * p * 2, y + (j - 4) * p * 2, p, p, 0, fill=col, ink=2, shade=0, boil=0.2)


def metronome(ink: Ink, c: Ctx, g: Gag, u: float, w: Where):
    """A metronome on little legs strolls by, ticking on the beat."""
    x = _across(u, g.side, 150)
    y = (w.ground if not w.sky else 1000) + 10
    step = c.beat * math.pi
    with ink.at(x, y - abs(math.sin(step)) * 14):
        for side in (-1, 1):
            rig.hose(ink, side * 30, -40, side * 30 + 14 * math.sin(step + (side > 0) * math.pi), 0, 0.1 * side, r=7)
            rig.shoe(ink, side * 30 + 14 * math.sin(step + (side > 0) * math.pi), 0, -g.side, 0.9)
        with ink.outlined(5):
            ink.tri((-90, -40), (90, -40), (0, -330), fill=rgb("8a4a2a"), ink=0, rnd=8, shade=0.4)
        ink.tri((-55, -60), (55, -60), (0, -270), fill=rgb("f2e6c8"), ink=3, rnd=4, shade=0.2)
        sw = math.sin(c.beat * math.pi) * 0.5
        with ink.at(0, -70, sw):
            ink.capsule(0, 0, 0, -200, 4, fill=INK, ink=0, shade=0)
            ink.box(0, -140, 16, 12, 3, fill=rgb("c0c0c4"), ink=3, shade=0.4)
        rig.eye(ink, -16, -120, 8, 12, (-g.side * 0.5, 0), 0.0)
        rig.eye(ink, 16, -120, 8, 12, (-g.side * 0.5, 0), 0.0)


def cuckoo(ink: Ink, c: Ctx, g: Gag, u: float, w: Where):
    """A cuckoo clock in the corner: the bird pops out on each beat of its bar (it's another minute)."""
    k = min(_ease(u / 0.12), _ease((1 - u) / 0.12))
    x, y = (W - 200 if g.side > 0 else 200), -260 + 470 * k
    out = 0.25 < u < 0.85 and (c.beat % 1.0) < 0.5
    with ink.at(x, y):
        ink.capsule(0, -400, 0, -150, 3, fill=INK, ink=0, shade=0)
        with ink.outlined(5):
            ink.box(0, 0, 90, 100, 10, fill=rgb("8a5230"), ink=0, shade=0.4)
            ink.tri((-120, -90), (0, -190), (120, -90), fill=rgb("5c331c"), ink=0, rnd=6)
        ink.ellipse(0, 20, 60, fill=rgb("f6efe0"), ink=4, shade=0.3)
        ang = c.t * 0.5
        ink.capsule(0, 20, math.cos(ang) * 40, 20 + math.sin(ang) * 40, 4, fill=INK, ink=0, shade=0)
        ink.capsule(0, 20, math.cos(ang * 12) * 50, 20 + math.sin(ang * 12) * 50, 2.5, fill=INK, ink=0, shade=0)
        ink.box(0, -70, 30, 24, 4, fill=rgb("2a1810"), ink=3, shade=0)
        if out:
            with ink.at(0, -70 + 10, 0, 1.0):
                ink.capsule(0, 0, 0, 0, 1, fill=INK, ink=0, shade=0)
                ink.ellipse(0, 0, 34, 26, fill=rgb("6aa8d8"), ink=3.5, shade=0.4)
                ink.tri((30, -6), (64, 0), (30, 8), fill=rgb("e8a04a"), ink=2.5)
                rig.eye(ink, 10, -8, 7, 10, (1, 0), 0.0)
            rig.note(ink, 90, -130 - 30 * (c.beat % 1.0), 1.0, rgb("3a2416"))
        for side in (-1, 1):
            ink.capsule(side * 40, 100, side * 40, 220 + 20 * math.sin(c.t * 2 + side), 3, fill=INK, ink=0, shade=0)
            ink.ellipse(side * 40, 236 + 20 * math.sin(c.t * 2 + side), 16, 26, fill=rgb("e8b14a"), ink=3, shade=0.4)


def plane(ink: Ink, c: Ctx, g: Gag, u: float, w: Where):
    """A paper aeroplane with a heart on it loops across."""
    x = _across(u, g.side, 150)
    loop = 2 * math.pi * min(1.0, max(0.0, (u - 0.4) / 0.25))
    y = 380 + 120 * math.sin(u * 4) - (math.sin(loop) * 140 if 0.4 < u < 0.65 else 0)
    rot = (0.0 if g.side < 0 else math.pi) + (-loop if g.side < 0 else loop)
    with ink.at(x, y, rot):
        ink.tri((60, 0), (-60, -30), (-40, 0), fill=rgb("fbf7ec"), ink=3.5)
        ink.tri((60, 0), (-40, 0), (-60, 26), fill=rgb("e8e2d4"), ink=3.5)
        ink.heart(-20, -8, 9, fill=rgb("d9433a"), ink=0)


def hotair(ink: Ink, c: Ctx, g: Gag, u: float, w: Where):
    """A hot-air balloon with a little oompah tuba player drifting through the back of the scene."""
    x = _across(u, g.side, 250)
    y = 230 + 40 * math.sin(c.t * 0.7)
    with ink.at(x, y, 0.05 * math.sin(c.t), 0.75):
        with ink.outlined(5):
            ink.ellipse(0, 0, 130, 150, fill=rgb("d9433a"), ink=0, shade=0.4)
        for k in range(3):
            ink.ellipse(-60 + k * 60, 0, 18, 140, fill=rgb("f0c04a"), ink=0, shade=0)
        for side in (-1, 1):
            ink.capsule(side * 70, 120, side * 40, 220, 2.5, fill=INK, ink=0, shade=0)
        ink.box(0, 245, 50, 30, 6, fill=rgb("9a6a40"), ink=4, shade=0.4)
        ink.ellipse(0, 190, 22, fill=rgb("f6efe0"), ink=3, shade=0.3)
        rig.eye(ink, -6, 186, 5, 8, (0.5, 0), 0.0)
        ink.arc(20, 200, 30, 10, 1.2, rot=-0.5, fill=rgb("e8b14a"))
        if c.squash > 0.4:
            for j in range(2):
                rig.note(ink, 60 + 40 * j, 160 - 50 * (c.beat % 1.0) - 30 * j, 0.9, rgb("3a2416"))


def car(ink: Ink, c: Ctx, g: Gag, u: float, w: Where):
    """The burned-out car with a DJ rig on the roof (from the knisper brief) putters across the back,
    headlights flashing with the kick."""
    x = _across(u, g.side, 300)
    y = (w.ground if not w.sky else 1000) - 150
    f = -g.side
    with ink.at(x, y - abs(math.sin(c.beat * math.pi)) * 8, 0.0, 0.85 * f, 0.85):
        with ink.outlined(5):
            ink.box(0, -50, 220, 60, 30, fill=rgb("6a4a3a"), fill2=rgb("3a2a22"), ink=0, shade=0.5)
            ink.box(-20, -130, 120, 50, 26, fill=rgb("5a3a2e"), ink=0, shade=0.4)
        for k in range(6):
            ink.ellipse(-150 + 60 * k, -40 + 20 * (k % 2), 16, 10, fill=rgb("9a5a2a", 0.8), ink=0, shade=0)
        ink.box(-20, -130, 90, 30, 10, fill=rgb("20304a"), ink=3, shade=0)
        for side in (-1, 1):
            with ink.at(side * 140, 10, c.t * -6 * f):
                ink.ellipse(0, 0, 48, fill=rgb("2a2420"), ink=4, shade=0.3)
                ink.ellipse(0, 0, 18, fill=rgb("8a8478"), ink=3, shade=0.3)
        ink.glow(225, -40, 80, (1.0, 0.95, 0.6, 0.5 * c.kick), soft=40)
        ink.ellipse(215, -40, 18, 24, fill=rgb("fff6c0") if c.kick > 0.3 else rgb("c8b880"), ink=3, shade=0.3)
        with ink.at(-20, -200):
            ink.box(0, 0, 90, 14, 4, fill=rgb("2a2420"), ink=3, shade=0.3)
            for side in (-1, 1):
                ink.ellipse(side * 45, -12, 32, 8, fill=rgb("1e1816"), ink=2.5, shade=0)
            ink.ellipse(0, -70, 30, 34, fill=rgb("f6efe0"), ink=3, shade=0.3)
            ink.ellipse(0, -96, 34, 10, fill=INK, ink=0, shade=0)
            rig.glove(ink, 40, -30 + 10 * c.squash, 0.2, "open", s=0.8)


def bat(ink: Ink, c: Ctx, g: Gag, u: float, w: Where):
    """A bat flaps across with a glowstick."""
    x = _across(u, g.side, 150)
    y = 260 + 90 * math.sin(u * 9)
    flap = math.sin(c.t * 16)
    with ink.at(x, y):
        for side in (-1, 1):
            ink.tri((side * 10, 0), (side * 120, -60 * flap), (side * 90, 30), fill=rgb("2a2230"), ink=3)
        ink.ellipse(0, 0, 30, 26, fill=rgb("2a2230"), ink=3, shade=0.3)
        ink.tri((-18, -16), (-12, -44), (-2, -20), fill=rgb("2a2230"), ink=2)
        ink.tri((18, -16), (12, -44), (2, -20), fill=rgb("2a2230"), ink=2)
        rig.eye(ink, -9, -4, 6, 8, (0, 0), 0.0)
        rig.eye(ink, 9, -4, 6, 8, (0, 0), 0.0)
        a = 0.6 * math.sin(c.beat * math.pi)
        ink.glow(20, 40, 70, (0.4, 1.0, 0.4, 0.5), soft=40)
        ink.capsule(20 - 40 * math.sin(a), 40 - 40 * math.cos(a), 20 + 40 * math.sin(a), 40 + 40 * math.cos(a), 8,
                    fill=rgb("8aff6a"), ink=2.5, shade=0)


def konami(ink: Ink, c: Ctx, g: Gag, u: float, w: Where):
    """Up, up, down, down, left, right, left, right, B, A: tapped in on a joypad pad, one per beat."""
    k = min(_ease(u / 0.1), _ease((1 - u) / 0.1))
    x0, y0 = W / 2 - 330, 110 - (1 - k) * 260
    n = int(min(10, max(0, (u - 0.1) * 22)))
    seq = [-math.pi / 2, -math.pi / 2, math.pi / 2, math.pi / 2, math.pi, 0.0, math.pi, 0.0]
    ink.box(W / 2, y0, 380, 52, 18, fill=rgb("2a2622", 0.85), ink=4, shade=0.2)
    for j in range(10):
        x = x0 + j * 73
        lit = j < n
        if j < 8:
            with ink.at(x, y0, seq[j]):
                ink.box(0, 0, 26, 26, 6, fill=rgb("f6efe0") if lit else rgb("6a5a4a"), ink=3, shade=0.2)
                ink.tri((14, 0), (-8, -12), (-8, 12), fill=INK if lit else rgb("3a3430"), ink=0)
        else:
            ink.ellipse(x, y0, 26, fill=rgb("d9433a") if lit else rgb("6a3a32"), ink=3, shade=0.4)
    if n >= 10:
        q = min(1.0, (u - 0.1 - 10 / 22) * 4)
        for j in range(8):
            a = j * math.pi / 4 + c.t
            ink.star(W / 2 + math.cos(a) * 420 * q, y0 + math.sin(a) * 90 * q, 22, 5, 2.4, fill=rgb("ffe37a"), ink=3,
                     rot=c.t * 4)


# ---------------------------------------------------------------- eggs the heroes join in

def qblock(ink: Ink, c: Ctx, g: Gag, u: float, w: Where):
    """A floating ? block over a hero: they hop up, bump it, and a coin spins out."""
    if not w.heroes:
        return
    hx, hy = w.heroes[0]
    k = min(_ease(u / 0.12), _ease((1 - u) / 0.12))
    bump = math.exp(-max(0.0, u - 0.5) * 30) if u >= 0.5 else 0.0
    y = hy - 430 - 30 * bump
    with ink.at(hx, y, 0.0, k):
        with ink.outlined(5):
            ink.box(0, 0, 50, 50, 6, fill=rgb("f0b030") if u < 0.5 else rgb("a87a4a"), ink=0, shade=0.4)
        for sx in (-1, 1):
            for sy in (-1, 1):
                ink.ellipse(sx * 36, sy * 36, 4, fill=INK, ink=0, shade=0)
        if u < 0.5:
            lettering.words(ink, "?", 0, 4, 64, fill=rgb("fff6dc"), shadow=None, outline=0.0, weight=9)
    if u >= 0.5:
        q = (u - 0.5) / 0.5
        cy = y - 70 - 260 * math.sin(math.pi * min(1.0, q * 1.3))
        with ink.at(hx, cy, 0.0, abs(math.cos(c.t * 14)) + 0.08, 1.0, fade=max(0.0, q - 0.7) / 0.3):
            ink.ellipse(0, 0, 30, 36, fill=rgb("ffd84a"), ink=4, shade=0.5)
            ink.box(0, 0, 6, 18, 2, fill=rgb("e0a020"), ink=0, shade=0)


def pipe(ink: Ink, c: Ctx, g: Gag, u: float, w: Where):
    """A green pipe rises out of the floor and a periscope worm has a look round, on the beat."""
    x = 1010.0
    k = min(_ease(u / 0.15), _ease((1 - u) / 0.15))
    top = w.ground - 170 * k
    peek = min(_ease((u - 0.2) / 0.1), _ease((0.82 - u) / 0.1))
    if peek > 0:
        look = 1.0 if int(c.beat) % 4 < 2 else -1.0
        with ink.at(x, top - 90 * peek):
            ink.capsule(0, 0, 0, 120, 24, fill=rgb("e88aaa"), ink=4, shade=0.4)
            ink.ellipse(0, -10, 34, 30, fill=rgb("e88aaa"), ink=4, shade=0.4)
            rig.eye(ink, -11 + 6 * look, -16, 9, 14, (look, 0), 0.0)
            rig.eye(ink, 11 + 6 * look, -16, 9, 14, (look, 0), 0.0)
    with ink.outlined(5):
        ink.box(x, top + 110, 60, 110, 4, fill=rgb("3aa84a"), fill2=rgb("1e7a2e"), ink=0, shade=0.5)
        ink.box(x, top + 10, 76, 26, 6, fill=rgb("3aa84a"), fill2=rgb("1e7a2e"), ink=0, shade=0.5)
    ink.box(x - 30, top + 110, 10, 100, 4, fill=(1, 1, 1, 0.3), ink=0, shade=0)


def stagehand(ink: Ink, c: Ctx, g: Gag, u: float, w: Where):
    """A stagehand in silhouette crosses the front of the stage with a long ladder, which swings round
    when they stop to look at the camera."""
    x = _across(u, g.side, 400)
    f = -g.side
    turn = 0.45 < u < 0.6
    swing = math.sin(min(1.0, max(0.0, (u - 0.45) / 0.15)) * math.pi) * 2.6 if turn else 0.0
    y = 1100
    col = (0.06, 0.05, 0.05, 0.92)
    step = c.beat * math.pi
    with ink.at(x, y - abs(math.sin(step)) * 10):
        for side in (-1, 1):
            ink.capsule(side * 20, -170, side * 20 + 25 * math.sin(step + (side > 0) * math.pi), -10, 18, fill=col, ink=0,
                        shade=0)
        ink.box(0, -260, 60, 100, 30, fill=col, ink=0, shade=0)
        ink.ellipse(0, -400, 50, 54, fill=col, ink=0, shade=0)
        ink.box(0, -446, 64, 14, 4, fill=col, ink=0, shade=0)
        with ink.at(0, -300, swing * f):
            ink.capsule(-420 * f, 0, 420 * f, 0, 12, fill=col, ink=0, shade=0)
            ink.capsule(-420 * f, 60, 420 * f, 60, 12, fill=col, ink=0, shade=0)
            for j in range(9):
                ink.capsule((-400 + j * 100) * f, 0, (-400 + j * 100) * f, 60, 8, fill=col, ink=0, shade=0)


def bowling(ink: Ink, c: Ctx, g: Gag, u: float, w: Where):
    """A bowling ball rolls along the floor; the heroes hop it as it goes past (planned in combat)."""
    if w.ball_x is None:
        return
    x = w.ball_x
    with ink.at(x, w.ground - 46, -c.t * 9 * g.side):
        ink.ellipse(0, 0, 46, fill=rgb("2a2a40"), ink=4, shade=0.6)
        for j in range(3):
            ink.ellipse(-10 + 12 * j, -18 + 6 * (j % 2), 6, fill=INK, ink=0, shade=0)
    for j in range(3):
        rig.speed_lines(ink, x + 70 * g.side, w.ground - 46, 0.0 if g.side < 0 else math.pi, n=3)


def banana(ink: Ink, c: Ctx, g: Gag, u: float, w: Where):
    """A banana peel lands in front of a hero, who slips on it (planned in combat)."""
    if not w.heroes:
        return
    hx, hy = w.heroes[0]
    if u < 0.25:
        q = u / 0.25
        x, y = W + 100 - (W + 100 - hx - 30) * q, hy - 500 * math.sin(math.pi * q * 0.5) * (1 - q) - 10
        rot = q * 9
    else:
        q = (u - 0.45) / 0.55
        x, y, rot = hx + 30 + max(0.0, q) * 300, hy - 10 - (300 * math.sin(math.pi * q) if q > 0 else 0), max(0.0, q) * 7
    with ink.at(x, y, rot):
        for side in (-1, 0, 1):
            ink.bez(0, 0, side * 40, -20, side * 60, 10 + 10 * abs(side), 12, 6, fill=rgb("f2d24a"), ink=3, shade=0.3)
        ink.ellipse(0, -2, 14, 10, fill=rgb("8a6a2a"), ink=2.5, shade=0.3)


DRAW = {"pie": pie, "anvil": anvil, "pencil": pencil, "bomb": bomb, "fly": fly, "shadow": shadow,
        "balloons": balloons, "ufo": ufo, "jelly": jelly, "smiley": smiley, "discoball": discoball,
        "cassette": cassette, "invader": invader, "metronome": metronome, "cuckoo": cuckoo, "plane": plane,
        "hotair": hotair, "car": car, "bat": bat, "konami": konami, "qblock": qblock, "pipe": pipe,
        "stagehand": stagehand, "bowling": bowling, "banana": banana}
