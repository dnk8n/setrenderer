"""Stages for the five extra bosses: the farm orchard at dusk with jellyfish hanging in the trees, the
festival field (a burned-out car for a DJ booth, lasers, a smoke machine, hay bales, pride flags, a bar
pouring German beer and mate soda, and a crowd of goats and black sheep with a few pixel stick men from
knisper among them), the psychedelic underground rave, a speakeasy street with arcade cabinets, and the
cinema, where the fight happens on stage in front of the screen."""
from __future__ import annotations

import colorsys
import math

from . import rig
from .ctx import Ctx
from .ink import GLOW, INK, WATER, Ink, mix, rgb
from .stages import GROUND, H, W, audience, face_tree, sky, wash_cloud
from .story import h01

PRIDE = [rgb("e40303"), rgb("ff8c00"), rgb("ffed00"), rgb("008026"), rgb("004dff"), rgb("750787")]
TRANS = [rgb("5bcefa"), rgb("f5a9b8"), rgb("ffffff"), rgb("f5a9b8"), rgb("5bcefa")]


def _hsv(h, s=0.8, v=1.0, a=1.0):
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return (r, g, b, a)


def hay_bale(ink: Ink, x, y, s=1.0):
    with ink.at(x, y, 0, s):
        ink.ellipse(0, -60, 90, 62, fill=rgb("e8c46a"), fill2=rgb("c09a3a"), ink=4, shade=0.5)
        for k in range(3):
            ink.arc(-40, -60, 18 + 14 * k, 3, 2.6, rot=0.0, fill=rgb("a8822a"))
        for k in range(5):
            ink.capsule(-60 + 30 * k, -110, -50 + 30 * k, -118, 2, fill=rgb("f2dc8a"), ink=0, shade=0)


def hanging_jelly(ink: Ink, c: Ctx, x, y, s, seed):
    """A jellyfish hanging from a branch, swinging in a wind that blows on the beat."""
    sw = (0.25 + 0.35 * c.kick) * math.sin(c.t * 1.6 + seed * 3)
    with ink.at(x, y, sw, s):
        ink.capsule(0, 0, 0, 40, 1.5, fill=INK, ink=0, shade=0)
        col = _hsv(0.85 + 0.12 * h01(seed), 0.45, 1.0)
        ink.glow(0, 70, 50, (col[0], col[1], col[2], 0.4), soft=26)
        for k in range(4):
            ink.bez(-14 + 9 * k, 75, -18 + 9 * k + 10 * math.sin(c.t * 3 + k), 100, -14 + 9 * k, 125, 3, 1.5, fill=col,
                    ink=1.5, shade=0)
        with ink.outlined(3):
            ink.pie(0, 75, 26, 30, cut=0.0, half=1.57, rot=math.pi, fill=col)
        rig.eye(ink, -7, 62, 4, 6, (0, 0.3), 0.0)
        rig.eye(ink, 7, 62, 4, 6, (0, 0.3), 0.0)


def goat(ink: Ink, c: Ctx, x, y, s, seed, black=False, bounce=1.0):
    """A goat (or a black sheep that looks a lot like one), bobbing to the music."""
    hop = abs(math.sin(c.beat * math.pi + seed * 3)) * 14 * bounce
    body = rgb("2a2426") if black else rgb("f6efe0")
    face = rgb("3a3236") if black else rgb("f6efe0")
    with ink.at(x, y - hop, 0.05 * math.sin(c.beat * math.pi + seed), s):
        for k in range(4):
            lx = -40 + k * 26
            ink.capsule(lx, -30, lx + 6 * math.sin(c.t * 6 + k), 0, 5, fill=rgb("3a3236"), ink=2.5)
        if black:
            with ink.outlined(4):
                for k in range(5):
                    ink.ellipse(-40 + 20 * k, -55 - 8 * (k % 2), 26, fill=body, ink=0, shade=0.3)
        else:
            ink.ellipse(0, -52, 58, 30, fill=body, ink=4, shade=0.4)
        with ink.at(52, -80, 0.2 * math.sin(c.beat * math.pi * 2 + seed)):
            ink.ellipse(0, 0, 24, 20, fill=face, ink=3.5, shade=0.3)
            ink.bez(-6, -14, -20, -40, -34, -30, 5, 2, fill=rgb("c8b090"), ink=2)
            ink.bez(6, -14, 10, -42, -2, -44, 5, 2, fill=rgb("c8b090"), ink=2)
            ink.ellipse(-22, -6, 12, 6, fill=face, ink=2.5, shade=0.2, rot=-0.4)
            rig.eye(ink, 6, -4, 5, 7, (0.6, 0), 0.0, white=rgb("fff2a0"))
            ink.capsule(14, 14, 16, 30, 3, fill=rgb("c8b090") if not black else rgb("8a8288"), ink=0, shade=0)


def pixel_stickman(ink: Ink, c: Ctx, x, y, s, seed):
    """A knisper-style 8-bit stick dancer, visiting from the other template."""
    p = 6 * s
    up = int(c.beat * 2 + seed * 3) % 2
    col = _hsv(h01(seed), 0.7, 1.0)
    pix = [(0, -10), (0, -9), (-1, -10), (1, -10), (-1, -9), (1, -9), (0, -8), (0, -7), (0, -6), (0, -5),
           (-1, -4), (1, -4), (-2, -3), (2, -3), (-2, -2), (2, -2)]
    pix += [(-1, -7), (-2, -8 + up), (1, -7), (2, -8 + (1 - up))]
    for i, j in pix:
        ink.box(x + i * p * 2, y + j * p * 2, p, p, 0, fill=col, ink=1.5, shade=0, boil=0.2)


# ---------------------------------------------------------------- the farm orchard at dusk

def orchard(ink: Ink, c: Ctx, layer: str):
    if layer == "back":
        sky(ink, rgb("3a2a5a"), rgb("f0a070"), 141)
        ink.glow(1500, 230, 110, (1, 0.95, 0.8, 0.5), soft=40)
        ink.ellipse(1500, 230, 70, fill=rgb("fff2d0"), ink=3, shade=0.3)
        for k in range(14):
            x, y = (k * 137) % W, 40 + (k * 71) % 300
            if h01(k, int(c.t * 2)) > 0.3:
                ink.star(x, y, 5 + 3 * c.high, 4, 2, fill=rgb("fff6c0"), ink=0)
        ink.wave(620, 40, 1700, 0.2, rgb("6a5a8a"), fill2=rgb("4a3a6a"), mat=WATER, seed=142)
        # a windmill on the hill
        with ink.at(300, 640):
            ink.tri((-40, 0), (40, 0), (0, -230), fill=rgb("8a5a3a"), ink=4, rnd=6)
            with ink.at(0, -220, c.t * 0.8 + 0.2 * c.kick):
                for k in range(4):
                    with ink.at(0, 0, k * math.pi / 2):
                        ink.box(0, -80, 12, 80, 3, fill=rgb("f2e6c8"), ink=3, shade=0.2)
        # corn rows swaying on the beat
        ink.wave(740, 30, 900, 1.1, rgb("8a7a3a"), fill2=rgb("6a5a2a"), mat=WATER, seed=143)
        for k in range(26):
            x = 20 + k * 74
            lean = 0.12 * math.sin(c.beat * math.pi + k * 0.5) * (0.5 + c.energy)
            with ink.at(x, 800, lean):
                ink.capsule(0, 0, 0, -150, 5, fill=rgb("6a8a3a"), ink=2.5)
                for j in range(3):
                    ink.ellipse((-1) ** j * 20, -50 - 35 * j, 26, 7, fill=rgb("7aa04a"), ink=2, shade=0.2,
                                rot=(-1) ** j * 0.5)
                ink.ellipse(8, -110, 9, 24, fill=rgb("f0c84a"), ink=2.5, shade=0.3)
        # trees with jellyfish hanging from them
        for k, x in enumerate((140, 560, 980)):
            face_tree(ink, c, x, 840, 0.9 + 0.1 * h01(k, "ot"), k * 2.3 + 1, leaf=rgb("4a7a4a"), leaf2=rgb("2f5a3a"),
                      face=k == 1)
            sway = 0.06 * math.sin(c.beat * math.pi + (k * 2.3 + 1) * 6) * (0.5 + c.lowmid)
            for j in range(3):
                hanging_jelly(ink, c, x - sway * 380 - 60 + 60 * j, 840 - 300 * 0.9 + 40, 0.9, k * 7 + j)
        ink.box(W / 2, 995, W / 2 + 40, 95, 0, fill=rgb("7a6a3a"), fill2=rgb("5a4a2a"), ink=0, shade=0, mat=WATER, boil=0)
        ink.box(W / 2, GROUND, W / 2 + 40, 8, 0, fill=rgb("9a8a4a"), ink=3, shade=0.3)
        for k, x in enumerate((700, 1100)):
            hay_bale(ink, x, GROUND + 6, 0.8)
    elif layer == "front":
        with ink.at(0, 0, soft=9.0):
            for k in range(6):
                x = k * 380 + 40
                ink.capsule(x, 1100, x + 20 * math.sin(c.t + k), 930, 10, fill=rgb("4a6a2a"), ink=0, shade=0)
                ink.ellipse(x + 30, 980, 40, 10, fill=rgb("5a7a3a"), ink=0, shade=0, rot=0.6)


# ---------------------------------------------------------------- the festival field

def festival(ink: Ink, c: Ctx, layer: str):
    if layer == "back":
        sky(ink, rgb("141432"), rgb("3a2a5a"), 151)
        for k in range(20):
            x, y = (k * 97) % W, 30 + (k * 53) % 380
            ink.star(x, y, 4 + 3 * c.high * h01(k), 4, 2, fill=rgb("fff6c0"), ink=0)
        # a UFO looking on
        ux, uy = 400 + 200 * math.sin(c.t * 0.2), 150 + 20 * math.sin(c.t)
        ink.tri((ux - 30, uy + 10), (ux - 140, 640), (ux + 140, 640), fill=(1.0, 0.95, 0.6, 0.08 + 0.05 * c.high), ink=0,
                mat=GLOW)
        ink.ellipse(ux, uy - 14, 36, 26, fill=rgb("bfe6ff", 0.85), ink=3, shade=0.3)
        ink.ellipse(ux, uy, 90, 20, fill=rgb("b8bcc4"), ink=3.5, shade=0.5)
        for k in range(5):
            ink.ellipse(ux - 60 + 30 * k, uy + 4, 6, fill=rgb("ffe37a") if (int(c.beat * 2) + k) % 2 else rgb("7a6a3a"),
                        ink=0, shade=0)
        ink.wave(700, 25, 1800, 0.3, rgb("2a3a2a"), fill2=rgb("1a2a1a"), mat=WATER, seed=152)
        # the burned-out car DJ booth, headlights on the kick, a little DJ on the roof
        with ink.at(330, 760, 0.0, 1.1):
            with ink.outlined(5):
                ink.box(0, -50, 220, 60, 30, fill=rgb("6a4a3a"), fill2=rgb("3a2a22"), ink=0, shade=0.5)
                ink.box(-20, -130, 120, 50, 26, fill=rgb("5a3a2e"), ink=0, shade=0.4)
            for k in range(6):
                ink.ellipse(-150 + 60 * k, -40 + 20 * (k % 2), 16, 10, fill=rgb("9a5a2a", 0.8), ink=0, shade=0)
            for side in (-1, 1):
                ink.ellipse(side * 140, 10, 46, fill=rgb("2a2420"), ink=4, shade=0.3)
            ink.glow(230, -40, 140, (1.0, 0.95, 0.6, 0.55 * c.kick), soft=60)
            ink.ellipse(215, -40, 18, 24, fill=rgb("fff6c0") if c.kick > 0.3 else rgb("c8b880"), ink=3, shade=0.3)
            ink.box(-20, -200, 90, 14, 4, fill=rgb("2a2420"), ink=3, shade=0.3)
            ink.ellipse(-20, -255, 26, 30, fill=rgb("f6efe0"), ink=3, shade=0.3)
            ink.ellipse(-20, -280, 30, 9, fill=INK, ink=0, shade=0)
            rig.glove(ink, 20, -228 + 10 * c.squash, 0.3, "open", s=0.7)
        # lasers from the booth, sweeping and changing colour
        for k in range(5):
            a = -math.pi / 2 + 1.1 * math.sin(c.t * 0.7 + k * 1.3)
            col = _hsv(c.t * 0.1 + k * 0.2, 0.9, 1.0, 0.35 + 0.3 * c.high)
            ink.capsule(330, 560, 330 + math.cos(a) * 1600, 560 + math.sin(a) * 1600, 3, 8, fill=col, ink=0, shade=0,
                        mat=GLOW, soft=6)
        # pride flags on poles
        for k, (x, flag) in enumerate(((800, PRIDE), (1160, TRANS), (1640, PRIDE))):
            ink.capsule(x, 820, x, 520, 4, fill=rgb("5a4a3a"), ink=2)
            n = len(flag)
            for j, col in enumerate(flag):
                for i in range(6):
                    wy = 8 * math.sin(c.t * 4 + i * 0.8 + k)
                    ink.box(x + 14 + i * 22, 530 + j * (90 / n) + wy, 11, 45 / n + 0.8, 0, fill=col, ink=0, shade=0, boil=0.3)
        # the bar: German beer and mate soda
        with ink.at(1060, 800):
            ink.box(0, -40, 170, 60, 8, fill=rgb("8a5a3a"), ink=4, shade=0.4)
            ink.box(0, -170, 180, 12, 4, fill=rgb("c8372d"), ink=3, shade=0.3)
            for k in range(7):
                ink.ellipse(-150 + 50 * k, -186, 8, fill=_hsv(k / 7, 0.6, 1.0) if c.high > 0.3 else rgb("fff6c0"),
                            ink=1.5, shade=0)
            for k in range(3):    # steins with foam
                x = -120 + 40 * k
                ink.box(x, -120, 15, 22, 4, fill=rgb("f0c040"), ink=3, shade=0.3)
                ink.ellipse(x, -142, 16, 8, fill=WHITEF, ink=2.5, shade=0)
            for k in range(4):    # mate-soda bottles
                x = 30 + 34 * k
                ink.capsule(x, -100, x, -150, 10, fill=rgb("c87a2a", 0.9), ink=2.5, shade=0.3)
                ink.capsule(x, -150, x, -172, 4, fill=rgb("c87a2a", 0.9), ink=2, shade=0)
                ink.box(x, -120, 9, 8, 2, fill=rgb("f2e6a0"), ink=0, shade=0)
        # the smoke machine
        for k in range(6):
            q = (c.t * 0.12 + k / 6) % 1.0
            ink.ellipse(200 + 1500 * q, 840 - 40 * math.sin(q * 6 + k), 120 + 80 * q, 50 + 30 * q,
                        fill=(0.85, 0.85, 0.95, 0.18 * (1 - q)), ink=0, shade=0, soft=20, boil=0)
        ink.box(W / 2, 995, W / 2 + 40, 95, 0, fill=rgb("3a5a2a"), fill2=rgb("2a4a1e"), ink=0, shade=0, mat=WATER, boil=0)
        ink.box(W / 2, GROUND, W / 2 + 40, 8, 0, fill=rgb("5a7a3a"), ink=3, shade=0.3)
        hay_bale(ink, 1000, GROUND + 6, 0.7)
    elif layer == "front":
        # the crowd: goats and black sheep (and a few pixel stick men) along the front, out of focus
        with ink.at(0, 0, soft=4.0):
            for k in range(9):
                x = 60 + k * 225 + 30 * h01(k, "cx")
                if k % 4 == 2:
                    pixel_stickman(ink, c, x, 1080, 1.4, k)
                else:
                    goat(ink, c, x, 1100, 1.5, k, black=h01(k, "bs") < 0.45)


WHITEF = rgb("fffaf0")


# ---------------------------------------------------------------- the psychedelic underground rave

def rave(ink: Ink, c: Ctx, layer: str):
    if layer == "back":
        sky(ink, rgb("1a0a2a"), rgb("2a0a3a"), 161)
        h0 = c.t * 0.05
        ink.rays(W / 2, 480, 24, _hsv(h0, 0.7, 0.35), _hsv(h0 + 0.5, 0.7, 0.2), phase=c.t * 0.1, mat=WATER)
        ink.rings(W / 2, 480, 70, _hsv(h0 + 0.25, 0.8, 0.5, 0.35), _hsv(h0 + 0.6, 0.8, 0.2, 0.0), phase=-c.t * 0.6 - c.kick * 0.3,
                  duty=0.5)
        for k in range(6):    # UV posters: eyes and spirals
            x, y = 160 + k * 320, 200 + 60 * (k % 2)
            ink.box(x, y, 70, 90, 6, fill=_hsv(h0 + k * 0.15, 0.9, 0.5), ink=3, shade=0.2)
            ink.ellipse(x, y, 40, 26, fill=rgb("fff6c0"), ink=3, shade=0)
            ink.ellipse(x + 10 * math.sin(c.t + k), y, 14, fill=_hsv(h0 + 0.5 + k * 0.1, 0.9, 1.0), ink=0, shade=0)
        for side in (-1, 1):  # speaker stacks pumping on the sub
            x = W / 2 + side * 760
            for j in range(3):
                ink.box(x, GROUND - 90 - j * 175, 110, 85, 8, fill=rgb("1e1820"), ink=4, shade=0.3)
                for i in (-1, 1):
                    ink.ellipse(x + i * 50, GROUND - 90 - j * 175, 38 * (1 + 0.15 * c.sub), fill=rgb("3a3440"), ink=3,
                                shade=0.4)
        if c.kick > 0.7 and c.energy > 0.5:     # strobe
            ink.box(W / 2, H / 2, W / 2, H / 2, 0, fill=(1, 1, 1, 0.08 * c.kick), ink=0, shade=0, mat=GLOW)
        for k in range(5):    # smoke
            q = (c.t * 0.1 + k / 5) % 1.0
            ink.ellipse(1900 - 1700 * q, 820, 160, 60, fill=_hsv(h0 + q, 0.4, 0.9, 0.12 * (1 - q)), ink=0, shade=0,
                        soft=24, boil=0)
        ink.box(W / 2, 995, W / 2 + 40, 95, 0, fill=rgb("2a1a3a"), fill2=rgb("1a0a2a"), ink=0, shade=0, mat=WATER, boil=0)
        for k in range(10):   # a light-up dance floor
            on = h01(k, int(c.beat)) < 0.5
            ink.box(96 + k * 192, GROUND + 50, 90, 40, 4, fill=_hsv(h0 + k * 0.1, 0.8, 0.8 if on else 0.3, 0.8), ink=2,
                    shade=0)
        ink.box(W / 2, GROUND, W / 2 + 40, 6, 0, fill=_hsv(h0, 0.6, 0.9), ink=2, shade=0)
    elif layer == "front":
        with ink.at(0, 0, soft=5.0, boil=0.0):
            for k in range(10):   # ravers with glowsticks
                x = 80 + k * 200
                bob = abs(math.sin(c.beat * math.pi + k)) * 18
                ink.ellipse(x, 1060 - bob, 70, 80, fill=(0.06, 0.03, 0.08, 0.95), ink=0, shade=0)
                a = 0.8 * math.sin(c.beat * math.pi * 2 + k)
                col = _hsv(k * 0.13 + c.t * 0.1, 0.9, 1.0)
                ink.glow(x + 60, 940 - bob, 40, (col[0], col[1], col[2], 0.5), soft=20)
                ink.capsule(x + 60 - 30 * math.sin(a), 940 - bob - 30 * math.cos(a), x + 60 + 30 * math.sin(a),
                            940 - bob + 30 * math.cos(a), 6, fill=col, ink=0, shade=0)


# ---------------------------------------------------------------- the speakeasy street

def speakeasy(ink: Ink, c: Ctx, layer: str):
    if layer == "back":
        sky(ink, rgb("0e1630"), rgb("2a2a5a"), 171)
        ink.ellipse(1650, 160, 60, fill=rgb("f6f0d8"), ink=3, shade=0.3)
        for k in range(7):    # brick buildings
            x = 140 + k * 280
            h = 420 + 140 * h01(k, "bh")
            with ink.at(x, GROUND):
                ink.box(0, -h / 2, 130, h / 2, 4, fill=rgb("6a3a2e"), fill2=rgb("4a2620"), ink=4, shade=0.4)
                for j in range(int(h / 40)):
                    ink.capsule(-128, -20 - 40 * j, 128, -20 - 40 * j, 1.2, fill=rgb("3a1e18"), ink=0, shade=0)
                for j in range(int(h / 110)):
                    for i in (-1, 1):
                        on = h01(k, j, i, int(c.bar / 2)) < 0.35 + 0.4 * c.high
                        ink.box(i * 60, -90 - j * 110, 24, 30, 3, fill=rgb("ffd86a") if on else rgb("2a2030"), ink=3,
                                shade=0)
        for k, (x, y) in enumerate(((420, 420), (1000, 380))):     # neon signs: a joystick and a pixel heart
            glow = 0.4 + 0.5 * (math.sin(c.t * 9 + k * 3) > -0.6) * (0.5 + 0.5 * c.squash)
            col = (rgb("ff4ad0") if k == 0 else rgb("4ad0ff"))
            ink.glow(x, y, 110, (col[0], col[1], col[2], 0.3 * glow), soft=40)
            if k == 0:
                ink.capsule(x, y + 40, x + 10, y - 30, 7, fill=col, ink=0, shade=0)
                ink.ellipse(x + 12, y - 40, 20, fill=col, ink=0, shade=0)
                ink.box(x, y + 50, 60, 14, 6, fill=(0, 0, 0, 0), ink=6, shade=0, ink_col=col)
            else:
                for i, j in ((-1, -1), (1, -1), (-2, 0), (-1, 0), (0, 0), (1, 0), (2, 0), (-1, 1), (0, 1), (1, 1), (0, 2)):
                    ink.box(x + i * 22, y + j * 22, 10, 10, 0, fill=col, ink=0, shade=0)
        # the speakeasy door with its peephole, arcade cabinets and a getaway car
        ink.box(760, GROUND - 120, 60, 120, 8, fill=rgb("3a2418"), ink=4, shade=0.4)
        ink.box(760, GROUND - 170, 20, 8, 3, fill=rgb("ffd86a") if int(c.bar) % 4 == 0 else rgb("1e1410"), ink=2, shade=0)
        for k, x in enumerate((560, 940)):
            with ink.at(x, GROUND):
                ink.box(0, -110, 50, 110, 6, fill=rgb("2a3a6a"), ink=4, shade=0.4)
                ink.box(0, -160, 38, 30, 4, fill=_hsv(c.t * 0.2 + k * 0.3, 0.6, 0.9), ink=3, shade=0)
                ink.capsule(-10, -110, -6, -134, 3, fill=INK, ink=0, shade=0)
                ink.ellipse(-6, -136, 7, fill=rgb("e03a3a"), ink=2, shade=0)
        with ink.at(1250, GROUND - 10, 0, 0.9):
            with ink.outlined(5):
                ink.box(0, -60, 250, 60, 30, fill=rgb("1e1e2a"), ink=0, shade=0.5)
                ink.box(30, -150, 140, 50, 30, fill=rgb("1e1e2a"), ink=0, shade=0.5)
            ink.box(30, -150, 110, 30, 10, fill=rgb("3a4a6a"), ink=3, shade=0)
            for side in (-1, 1):
                ink.ellipse(side * 160, 0, 52, fill=rgb("1a1a1e"), ink=4, shade=0.3)
                ink.ellipse(side * 160, 0, 26, fill=rgb("e6e2d8"), ink=3, shade=0.3)
        for k, x in enumerate((240, 1720)):     # street lamps
            ink.capsule(x, GROUND, x, GROUND - 330, 7, fill=rgb("2a2a30"), ink=3)
            ink.glow(x, GROUND - 350, 70, (1, 0.9, 0.6, 0.4), soft=40)
            ink.ellipse(x, GROUND - 350, 24, 30, fill=rgb("fff2c0"), ink=3, shade=0.2)
        ink.box(W / 2, 995, W / 2 + 40, 95, 0, fill=rgb("4a4a52"), fill2=rgb("2a2a32"), ink=0, shade=0, mat=WATER, boil=0)
        for k in range(30):   # cobbles
            ink.ellipse(30 + k * 66, GROUND + 40 + 30 * (k % 2), 28, 12, fill=rgb("5a5a62"), ink=2, shade=0.3)
        ink.box(W / 2, GROUND, W / 2 + 40, 8, 0, fill=rgb("8a8a92"), ink=3, shade=0.3)
    elif layer == "front":
        with ink.at(0, 0, soft=8.0):
            ink.box(60, 1010, 34, 70, 10, fill=rgb("c8372d"), ink=0, shade=0.3)      # a fire hydrant
            ink.ellipse(60, 940, 40, 20, fill=rgb("c8372d"), ink=0, shade=0.3)
            ink.capsule(1870, 1100, 1870, 820, 14, fill=rgb("1e1e24"), ink=0, shade=0)


# ---------------------------------------------------------------- the cinema (the fourth wall)

def cinema(ink: Ink, c: Ctx, layer: str):
    if layer == "back":
        sky(ink, rgb("4a1218"), rgb("2a0a0e"), 181)
        # the screen behind the fight, running a countdown leader
        sx, sy, sw, sh = 780, 430, 560, 300
        ink.box(sx, sy, sw + 30, sh + 30, 6, fill=rgb("c9a04a"), ink=5, shade=0.5)
        flick = 0.9 + 0.1 * h01("fl", int(c.t * 24))
        ink.box(sx, sy, sw, sh, 2, fill=(0.85 * flick, 0.82 * flick, 0.74 * flick, 1), ink=0, shade=0, mat=WATER)
        a = (c.beat % 4) / 4 * 2 * math.pi
        ink.ellipse(sx, sy, 200, fill=(0, 0, 0, 0), ink=5, shade=0, ink_col=rgb("3a3430"))
        ink.ellipse(sx, sy, 150, fill=(0, 0, 0, 0), ink=3, shade=0, ink_col=rgb("3a3430"))
        ink.capsule(sx - sw, sy, sx + sw, sy, 2, fill=rgb("3a3430"), ink=0, shade=0)
        ink.capsule(sx, sy - sh, sx, sy + sh, 2, fill=rgb("3a3430"), ink=0, shade=0)
        ink.pie(sx, sy, 200, 200, cut=0.0, half=a / 2, rot=a / 2 + math.pi, fill=(0.2, 0.18, 0.16, 0.35))
        # the beam from the booth at the back, dust floating in it
        ink.tri((sx, -40), (sx - sw, sy + sh), (sx + sw, sy + sh), fill=(1.0, 0.96, 0.8, 0.07), ink=0, mat=GLOW)
        for k in range(12):
            q = (c.t * 0.05 + k / 12) % 1.0
            ink.ellipse(sx - 300 + 600 * h01(k, "dx"), 40 + 600 * q, 3, fill=(1, 1, 1, 0.4), ink=0, shade=0)
        for side in (-1, 1):  # curtains and the exit lights
            x0 = 0 if side < 0 else W
            for k in range(5):
                xx = x0 - side * (40 + k * 50)
                ink.bez(xx, -20, xx - side * 20 * math.sin(c.t * 0.6 + k), 500, xx + side * (50 - k * 8), 1000,
                        46, 52, fill=rgb("8a1a20"), ink=4, shade=0.6)
            ink.box(x0 - side * 330, 140, 40, 16, 4, fill=rgb("3ad06a"), ink=3, shade=0)
            ink.glow(x0 - side * 330, 140, 50, (0.3, 1.0, 0.5, 0.3), soft=30)
        ink.box(W / 2, 995, W / 2 + 40, 95, 0, fill=rgb("6a4024"), fill2=rgb("4a2814"), ink=0, shade=0, mat=WATER, boil=0)
        for k in range(5):
            ink.capsule(-20, GROUND + 25 + k * 32, W + 20, GROUND + 25 + k * 32, 1.5, fill=rgb("3a2010"), ink=0, shade=0)
        ink.box(W / 2, GROUND, W / 2 + 40, 8, 0, fill=rgb("c9a04a"), ink=3, shade=0.3)
    elif layer == "front":
        audience(ink, c, n=12, seed=19, cheer=0.3 * c.energy)
