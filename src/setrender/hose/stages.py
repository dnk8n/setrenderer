"""Painted stages. Far layers are watercolour washes (granulation, pooled edges, uneven paint),
props closer to the camera are inked cels that dance on the beat, and the nearest layer is drawn
out of focus, like the multiplane and tabletop sets of 1930s cartoons."""
from __future__ import annotations

import math

from . import lettering, rig
from .ctx import Ctx
from .ink import GLOW, INK, WATER, Ink, mix, rgb
from .story import h01

W, H = 1920.0, 1080.0
GROUND = 905.0


def sky(ink: Ink, top, bottom, seed=1):
    ink.box(W / 2, H / 2, W / 2 + 80, H / 2 + 80, 0, fill=top, fill2=bottom, ink=0, shade=0, mat=WATER, boil=0,
            seed=seed)


def wash_cloud(ink: Ink, x, y, s, col, seed, face=False, c: Ctx | None = None):
    with ink.at(x, y, 0, s, mat=WATER, seed=int(seed * 100), boil=0.0):
        for k in range(6):
            a = h01(seed, k)
            ink.ellipse(-150 + k * 60, -20 - 50 * math.sin(k / 5 * math.pi) * (0.6 + a * 0.6), 70 + 40 * a,
                        55 + 30 * a, fill=col, ink=0, shade=0.15, seed=seed * 10 + k)


def cel_cloud(ink: Ink, c: Ctx, x, y, s, seed, face=True, col=rgb("fbf8f0"), col2=rgb("dfe6ea")):
    sq = c.squash * 0.6
    with ink.at(x, y, 0, s * (1 + 0.04 * sq), s * (1 - 0.05 * sq)):
        with ink.outlined(5):
            for k, (dx, dy, r) in enumerate(((-90, 10, 60), (-30, -30, 80), (50, -20, 70), (100, 15, 55), (0, 25, 70))):
                ink.ellipse(dx, dy, r, r * 0.9, fill=col, fill2=col2, ink=0, shade=0.45)
        if face:
            look = (math.sin(c.td * 0.7 + seed * 5), 0.2)
            rig.eye(ink, -18, -10, 11, 17, look, 1.0 if (c.td + seed * 3) % 4 < 0.12 else 0.0)
            rig.eye(ink, 18, -10, 11, 17, look, 1.0 if (c.td + seed * 3) % 4 < 0.12 else 0.0)
            rig.mouth(ink, 0, 20, 34, 0.3 + 0.5 * c.squash if h01(seed) > 0.5 else 0.0)
            rig.blush(ink, -40, 12, 10)
            rig.blush(ink, 40, 12, 10)


def face_tree(ink: Ink, c: Ctx, x, y, s, seed, leaf=rgb("6fa34a"), leaf2=rgb("3f7a34"), trunk=rgb("7a4e2e"),
              face=True):
    """Lollipop tree that squashes on the beat and sways with the low mids."""
    sq = c.squash * (0.4 + 0.6 * c.energy)
    sway = 0.06 * math.sin(c.beat * math.pi + seed * 6) * (0.5 + c.lowmid)
    with ink.at(x, y, 0, s):
        ink.bez(0, 0, 10 * math.sin(seed * 7), -120, -sway * 400, -230, 22, 14, fill=trunk, ink=4, shade=0.4)
        with ink.at(-sway * 420, -300 * (1 - 0.06 * sq), sway, 1 + 0.08 * sq, 1 - 0.08 * sq):
            with ink.outlined(5):
                for k in range(5):
                    a = k / 5 * 2 * math.pi + seed
                    ink.ellipse(math.cos(a) * 55, math.sin(a) * 40, 70, 64, fill=leaf, fill2=leaf2, ink=0, shade=0.5)
                ink.ellipse(0, 0, 80, 74, fill=leaf, fill2=leaf2, ink=0, shade=0.5)
            if face:
                rig.eye(ink, -20, -8, 12, 18, (0.3, 0.2), 0.0)
                rig.eye(ink, 20, -8, 12, 18, (0.3, 0.2), 0.0)
                rig.mouth(ink, 0, 26, 36, 0.25 + 0.6 * c.squash)


def flower(ink: Ink, c: Ctx, x, y, s, seed, col=rgb("f06a6a")):
    sq = c.squash
    lean = 0.18 * math.sin(c.beat * math.pi + seed * 4)
    with ink.at(x, y, 0, s):
        ink.bez(0, 0, -10, -50, 60 * lean, -110, 6, 5, fill=rgb("4f8a3a"), ink=3, shade=0.2)
        ink.ellipse(-22, -40, 22, 9, fill=rgb("6fae4a"), ink=3, shade=0.3, rot=0.5)
        with ink.at(60 * lean, -120, lean, 1 + 0.1 * sq, 1 - 0.1 * sq):
            with ink.outlined(4):
                for k in range(6):
                    a = k * math.pi / 3 + c.td * 0.3
                    ink.ellipse(math.cos(a) * 30, math.sin(a) * 30, 20, 20, fill=col, ink=0, shade=0.4)
            ink.ellipse(0, 0, 22, fill=rgb("ffd54a"), ink=3.5, shade=0.4)
            rig.eye(ink, -7, -3, 5, 8, (0, 0), 0.0)
            rig.eye(ink, 7, -3, 5, 8, (0, 0), 0.0)
            ink.arc(0, 4, 8, 1.6, 0.9, fill=INK)


def audience(ink: Ink, c: Ctx, n=11, y=1080 + 30, col=rgb("1e1410"), alpha=0.92, seed=3, cheer=0.0):
    """Theatre audience silhouettes along the bottom of the frame, out of focus."""
    with ink.at(0, 0, soft=5.0, boil=0.0):
        for k in range(n):
            x = (k + 0.5) / n * W + (h01(seed, k) - 0.5) * 60
            bob = math.sin(c.beat * math.pi * 2 + k * 1.7) * 6 * (0.5 + c.energy) + cheer * 30 * abs(math.sin(c.t * 8 + k))
            r = 70 + 25 * h01(seed, k, "r")
            hy = y - r * 0.6 - bob
            colk = (*col[:3], alpha)
            ink.ellipse(x, hy, r, r * 1.05, fill=colk, ink=0, shade=0)
            kind = int(h01(seed, k, "k") * 4)
            if kind == 0:     # round ears
                ink.ellipse(x - r * 0.85, hy - r * 0.75, r * 0.42, fill=colk, ink=0, shade=0)
                ink.ellipse(x + r * 0.85, hy - r * 0.75, r * 0.42, fill=colk, ink=0, shade=0)
            elif kind == 1:   # bowler hat
                ink.ellipse(x, hy - r * 0.75, r * 1.1, r * 0.2, fill=colk, ink=0, shade=0)
                ink.ellipse(x, hy - r * 0.95, r * 0.65, r * 0.45, fill=colk, ink=0, shade=0)
            elif kind == 2:   # bow
                ink.ellipse(x - r * 0.4, hy - r * 0.95, r * 0.3, r * 0.22, fill=colk, ink=0, shade=0)
                ink.ellipse(x + r * 0.2, hy - r * 0.98, r * 0.3, r * 0.22, fill=colk, ink=0, shade=0)
            if cheer > 0.3 and k % 2 == 0:
                hx = x + r * 0.9
                hy2 = hy - r * 1.2 - 30 * abs(math.sin(c.t * 9 + k))
                ink.ellipse(hx, hy2, 26, 26, fill=colk, ink=0, shade=0)


# ---------------------------------------------------------------- the stages

def ballroom(ink: Ink, c: Ctx, layer: str):
    if layer == "back":
        sky(ink, rgb("5e1f22"), rgb("2e0f12"), 7)
        ink.rays(1250, 520, 22, rgb("e8c47a", 0.55), rgb("c48a3a", 0.25), phase=c.td * 0.04, radius=820, mat=WATER)
        for k, x in enumerate((240, 1700)):
            ink.box(x, 480, 46, 470, 10, fill=rgb("c9a04a"), fill2=rgb("7a5a24"), ink=4, shade=0.5)
            for j in range(4):
                ink.box(x, 120 + j * 16, 60 - j * 6, 6, 3, fill=rgb("e8c47a"), ink=2.5, shade=0.3)
        # chandelier
        with ink.at(960, 60 + 6 * math.sin(c.t * 1.3)):
            ink.capsule(0, -80, 0, 30, 3, fill=rgb("c9a04a"), ink=2)
            ink.ellipse(0, 50, 120, 24, fill=rgb("e8c47a"), ink=4, shade=0.4)
            for k in range(7):
                x = -105 + k * 35
                ink.glow(x, 30, 26, (1, 0.85, 0.5, 0.35 + 0.4 * c.high), soft=22)
                ink.ellipse(x, 28, 7, 12, fill=rgb("fff3c0"), ink=2, shade=0)
        # stage floor
        ink.box(W / 2, 995, W / 2 + 40, 95, 0, fill=rgb("9a5e34"), fill2=rgb("5a3018"), ink=0, shade=0, mat=WATER, boil=0)
        for k in range(6):
            y = 915 + k * 32
            ink.capsule(-20, y, W + 20, y, 1.5, fill=rgb("3a2010"), ink=0, shade=0, boil=0.4)
        ink.box(W / 2, 905, W / 2 + 40, 8, 0, fill=rgb("c9a04a"), ink=3, shade=0.3)
    elif layer == "front":
        # curtains and valance
        for side in (-1, 1):
            x0 = 0 if side < 0 else W
            for k in range(4):
                xx = x0 - side * (40 + k * 46)
                ink.bez(xx, -20, xx - side * 30 * math.sin(c.t * 0.7 + k), 500, xx + side * (60 - k * 10), 1100,
                        44, 52, fill=rgb("a8262a"), fill2=None, ink=4, shade=0.6)
            ink.ellipse(x0 - side * 150, 640, 30, 18, fill=rgb("e8c47a"), ink=3.5, shade=0.4)
        for k in range(14):
            ink.ellipse(k * 148 + 30, 30, 92, 66, fill=rgb("a8262a"), fill2=rgb("6a1418"), ink=4, shade=0.5)
        for k in range(30):
            ink.capsule(k * 66 + 10, 88, k * 66 + 10, 112 + 6 * math.sin(c.td * 3 + k), 4, fill=rgb("e8c47a"), ink=2,
                        shade=0)
        # footlights pulse with the highs
        for k in range(9):
            x = 120 + k * 210
            ink.glow(x, 1000, 70, (1, 0.85, 0.5, 0.18 + 0.35 * c.high), soft=50)
            ink.ellipse(x, 1012, 34, 18, fill=rgb("3a2a20"), ink=3, shade=0.3)
            ink.ellipse(x, 1000, 20, 10, fill=rgb("fff3c0"), ink=2, shade=0)


def skystage(ink: Ink, c: Ctx, layer: str, storm: bool = False):
    sp = c.t * (90 if not storm else 130)
    if layer == "back":
        if storm:
            flash = max(0.0, math.sin(c.td * 7)) ** 20 * c.highmid * (c.phase >= 1)
            sky(ink, mix(rgb("3a4458"), rgb("c8d0e0"), flash), mix(rgb("6a7488"), rgb("e8eaf0"), flash), 11)
        else:
            sky(ink, rgb("8fc0c8"), rgb("f3e6c4"), 5)
        # far ground far below
        ink.wave(930, 26, 1300, -sp * 0.0012, rgb("8aa865") if not storm else rgb("4a5a50"),
                 fill2=rgb("5e7e48") if not storm else rgb("2e3a34"), mat=WATER, seed=4)
        for k in range(8):
            x = (k * 380 - sp * 0.3) % (W + 400) - 200
            wash_cloud(ink, x, 200 + 160 * h01(k, "y"), 0.9 + 0.5 * h01(k),
                       rgb("ffffff", 0.75) if not storm else rgb("8a92a6", 0.85), k * 7.1)
        for k in range(4):
            x = (k * 640 + 200 - sp * 0.7) % (W + 600) - 300
            if storm:
                cel_cloud(ink, c, x, 760 + 80 * h01(k, "cy"), 0.9, k * 3.3, face=False, col=rgb("8a92a6"),
                          col2=rgb("5a6276"))
            else:
                cel_cloud(ink, c, x, 760 + 80 * h01(k, "cy"), 0.9, k * 3.3, face=k % 2 == 0)
    elif layer == "front":
        if storm:
            for k in range(60):
                x = (h01(k, "rx") * (W + 300) - (c.t * 900 + k * 37) * 0.3) % (W + 300) - 150
                y = (h01(k, "ry") * H + c.t * 1500) % (H + 200) - 100
                ink.capsule(x, y, x - 14, y + 46, 1.6, fill=rgb("cfe0f0", 0.6), ink=0, shade=0, boil=0)
        for k in range(3):
            x = (k * 900 - sp * 2.4) % (W + 900) - 450
            with ink.at(0, 0, soft=10.0):
                cel_cloud(ink, c, x, 1040, 1.8, 9 + k, face=False,
                          col=rgb("ffffff") if not storm else rgb("6a7286"), col2=rgb("e0e6ea") if not storm else rgb("4a5266"))


def kitchen(ink: Ink, c: Ctx, layer: str):
    if layer == "back":
        sky(ink, rgb("f2e2b8"), rgb("e2c890"), 21)
        for k in range(16):
            ink.box(k * 128 + 32, 450, 22, 470, 0, fill=rgb("d9b878", 0.5), ink=0, shade=0, mat=WATER, boil=0)
        # window with a little sky and gingham curtains
        ink.box(420, 330, 210, 170, 10, fill=rgb("9cc8d0"), fill2=rgb("e8f0d8"), ink=6, shade=0.2)
        wash_cloud(ink, 400 + 30 * math.sin(c.t * 0.2), 300, 0.6, rgb("ffffff", 0.9), 2.2)
        ink.capsule(420, 160, 420, 500, 6, fill=rgb("8a5a34"), ink=3)
        ink.capsule(210, 330, 630, 330, 6, fill=rgb("8a5a34"), ink=3)
        for side in (-1, 1):
            ink.bez(420 + side * 220, 150, 420 + side * 150, 320, 420 + side * 200, 520, 30, 55,
                    fill=rgb("d9534a"), ink=4, shade=0.5)
        # shelf with plates and jars that hop on the beat
        ink.box(1000, 260, 330, 12, 4, fill=rgb("8a5a34"), ink=4, shade=0.4)
        for k in range(6):
            x = 720 + k * 110
            hop = rig.hop(c.beat + k * 0.5) * 22 * c.energy
            if k % 2 == 0:
                ink.ellipse(x, 200 - hop, 46, 46, fill=rgb("f6f2ea"), ink=4, shade=0.3)
                ink.ellipse(x, 200 - hop, 30, 30, fill=rgb("6fa0c8"), ink=2.5, shade=0)
            else:
                ink.box(x, 205 - hop, 34, 44, 14, fill=rgb("e8d8a8", 0.9), ink=4, shade=0.4)
                ink.box(x, 158 - hop, 36, 10, 4, fill=rgb("c0472c"), ink=3, shade=0.3)
                rig.eye(ink, x - 10, 200 - hop, 6, 9, (0, 0), 0.0)
                rig.eye(ink, x + 10, 200 - hop, 6, 9, (0, 0), 0.0)
        # wall clock with a face, its pendulum on the beat
        with ink.at(1700, 260):
            sw = math.sin(c.beat * math.pi) * 0.5
            ink.capsule(0, 60, math.sin(sw) * 140, 60 + math.cos(sw) * 140, 3, fill=rgb("c9a04a"), ink=2)
            ink.ellipse(math.sin(sw) * 140, 60 + math.cos(sw) * 140, 18, fill=rgb("e8c47a"), ink=3, shade=0.4)
            ink.box(0, 0, 90, 100, 30, fill=rgb("8a5a34"), ink=5, shade=0.5)
            ink.ellipse(0, -10, 70, fill=rgb("f6efe0"), ink=4, shade=0.2)
            rig.eye(ink, -20, -20, 10, 15, (0, 0), 0.0)
            rig.eye(ink, 20, -20, 10, 15, (0, 0), 0.0)
            ink.arc(0, 10, 24, 2.5, 0.9, fill=INK)
        # checkered floor
        for row in range(4):
            y = GROUND + 12 + row * 48
            for k in range(22):
                col = rgb("e8dcc0") if (k + row) % 2 == 0 else rgb("b8423a")
                ink.box(k * 92 - 20 + (row % 2) * 46, y, 46, 24, 0, fill=col, ink=1.5, shade=0, boil=0.3)
        ink.box(W / 2, GROUND, W / 2 + 40, 6, 0, fill=rgb("7a4a2a"), ink=3, shade=0)
    elif layer == "front":
        with ink.at(0, 0, soft=9.0):
            ink.box(200, 1060, 260, 70, 30, fill=rgb("8a5a34"), ink=0, shade=0.3)
            for k in range(3):
                ink.ellipse(110 + k * 80, 990, 42, 40, fill=rgb(("d94f3a", "e8b14a", "8ab04a")[k]), ink=0, shade=0.5)


def graveyard(ink: Ink, c: Ctx, layer: str):
    if layer == "back":
        sky(ink, rgb("1e1838"), rgb("4a3a6a"), 31)
        for k in range(40):
            x, y = h01(k, "sx") * W, h01(k, "sy") * 520
            tw = 0.5 + 0.5 * math.sin(c.t * 3 + k) * c.high
            ink.star(x, y, 5 + 4 * tw, 4, 2.2, fill=rgb("fff3c0", 0.6 + 0.4 * tw), ink=0, shade=0)
        with ink.at(320, 210, 0.1 * math.sin(c.t * 0.3)):
            ink.glow(0, 0, 150, (1, 0.95, 0.75, 0.35), soft=80)
            ink.ellipse(0, 0, 120, fill=rgb("f6efd0"), fill2=rgb("d8cca0"), ink=5, shade=0.5)
            rig.eye(ink, -30, -10, 12, 6, (0, 0), 1.0)
            rig.eye(ink, 30, -10, 12, 6, (0, 0), 1.0)
            ink.arc(0, 40, 30, 3, 0.8, fill=INK)
        ink.wave(760, 40, 1100, 0.6, rgb("3a2e5a"), fill2=rgb("221a3a"), mat=WATER, seed=32)
        # bare trees with faces
        for k, x in enumerate((140, 760, 1840)):
            sway = 0.08 * math.sin(c.beat * math.pi * 0.5 + k)
            with ink.at(x, GROUND, sway):
                ink.bez(0, 0, -20, -200, 10, -380, 30, 12, fill=rgb("2e2238"), ink=4, shade=0.3)
                for j in range(4):
                    a = -math.pi / 2 + (j - 1.5) * 0.6
                    ink.bez(5, -260 - j * 30, 60 * math.cos(a), -330 - j * 20, 140 * math.cos(a), -360 - j * 40 + 80 * math.sin(c.td + j) * 0.2,
                            8, 2, fill=rgb("2e2238"), ink=3, shade=0)
                rig.eye(ink, -10, -220, 9, 13, (0.5, 0), 0.0, white=rgb("e8f6a8"))
                rig.eye(ink, 12, -220, 9, 13, (0.5, 0), 0.0, white=rgb("e8f6a8"))
        ink.box(W / 2, 995, W / 2 + 40, 95, 0, fill=rgb("3a3258"), fill2=rgb("1e1830"), ink=0, shade=0, mat=WATER, boil=0)
        # tombstones that hop on the beat
        for k in range(5):
            x = 260 + k * 330
            hop = rig.hop(c.beat * 0.5 + k * 0.5) * 18 * c.energy
            with ink.at(x, GROUND + 10 - hop, 0.05 * math.sin(c.beat * math.pi + k)):
                ink.box(0, -60, 48, 70, 40, fill=rgb("8a88a0"), fill2=rgb("5a5874"), ink=4, shade=0.5)
                lettering.words(ink, "RIP", 0, -70, 26, fill=rgb("3a3858"), shadow=None, outline=0.0, weight=4)
        for k in range(3):    # ground fog
            ink.wave(GROUND + 30 + k * 20, 12, 700 + k * 200, c.t * (0.3 + 0.1 * k) + k, rgb("d8d0f0", 0.18),
                     mat=WATER, seed=40 + k, boil=0)
    elif layer == "front":
        with ink.at(0, 0, soft=8.0):
            for x in (80, 1840):
                ink.box(x, 1000, 70, 140, 50, fill=rgb("2a2640"), ink=0, shade=0.2)
        for k in range(3):    # bats flapping across
            u = ((c.t * 0.08 + k / 3) % 1.0)
            x = W + 100 - u * (W + 200)
            y = 160 + 60 * k + 30 * math.sin(c.t * 4 + k)
            flap = math.sin(c.t * 18 + k)
            with ink.at(x, y):
                ink.ellipse(0, 0, 14, 12, fill=INK, ink=0, shade=0)
                for side in (-1, 1):
                    ink.tri((0, 0), (side * 50, -30 * flap), (side * 40, 10), fill=INK, ink=0)


def sea(ink: Ink, c: Ctx, layer: str):
    if layer == "back":
        sky(ink, rgb("f2c48a"), rgb("f8e8c0"), 41)
        ink.glow(1500, 380, 120, (1, 0.8, 0.5, 0.4), soft=60)
        ink.ellipse(1500, 380, 80, fill=rgb("ffd88a"), ink=0, shade=0, mat=WATER)
        for k in range(4):
            wash_cloud(ink, (k * 520 + c.t * 8) % (W + 400) - 200, 160 + 60 * k, 0.8, rgb("fff4e0", 0.8), k * 2.7)
        # island with a lighthouse whose lamp blinks on the bar
        ink.wave(640, 40, 600, 1.1, rgb("7a9a6a"), x0=60, x1=520, bottom=700, mat=WATER, seed=44)
        with ink.at(300, 590):
            ink.box(0, -60, 20, 70, 6, fill=rgb("f6efe0"), ink=3, shade=0.4)
            for j in range(3):
                ink.box(0, -110 + j * 40, 21, 8, 2, fill=rgb("c8372d"), ink=2, shade=0)
            ink.glow(0, -140, 60, (1, 0.9, 0.5, 0.25 + 0.5 * c.squash), soft=40)
            ink.ellipse(0, -140, 14, fill=rgb("fff3a0"), ink=2.5, shade=0)
        ink.wave(660, 10, 300, c.t * 0.7, rgb("5a8ab0"), fill2=rgb("2e5a80"), mat=WATER, seed=45)
        for k in range(5):
            u = (c.t * 0.05 + k / 5) % 1.0
            x = u * (W + 200) - 100
            y = 200 + 70 * h01(k, "g") + 12 * math.sin(c.t * 2 + k)
            f = math.sin(c.t * 10 + k)
            ink.bez(x - 30, y + 10 * f, x - 14, y - 12, x, y, 3, 2, fill=INK, ink=0, shade=0)
            ink.bez(x, y, x + 14, y - 12, x + 30, y + 10 * f, 3, 2, fill=INK, ink=0, shade=0)
    elif layer == "water":
        # water in front of the boss, and the pier the heroes stand on
        for k in range(3):
            ink.wave(760 + k * 50, 16 - k * 3, 360 + k * 80, c.t * (1.3 - k * 0.3) + k * 2 + 2 * math.pi * c.beat * 0.25,
                     rgb(("4a7aa8", "3a6a98", "2e5a88")[k]), fill2=rgb("1e3a60"), mat=WATER, seed=46 + k,
                     ink=3 if k == 0 else 0, boil=0.4)
        ink.box(480, GROUND + 18, 520, 20, 6, fill=rgb("9a6a40"), ink=4, shade=0.4)
        for k in range(7):
            ink.box(10 + k * 150, GROUND + 100, 16, 90, 6, fill=rgb("6a4a2a"), ink=4, shade=0.4)
        for k in range(10):
            ink.capsule(-20 + k * 104, GROUND + 4, -20 + k * 104, GROUND + 34, 1.5, fill=rgb("4a2e18"), ink=0, shade=0)
    elif layer == "front":
        with ink.at(0, 0, soft=8.0):
            ink.wave(1030, 24, 500, c.t * 1.8, rgb("2e5a88", 0.9), mat=WATER, seed=49)


def city(ink: Ink, c: Ctx, layer: str):
    if layer == "back":
        sky(ink, rgb("4a2a5a"), rgb("f0a060"), 51)
        for k in range(3):     # searchlights
            a = -math.pi / 2 + 0.5 * math.sin(c.t * 0.4 + k * 2.1)
            x0 = 300 + k * 650
            ink.capsule(x0, 820, x0 + math.cos(a) * 900, 820 + math.sin(a) * 900, 20, 90,
                        fill=(1, 0.95, 0.75, 0.10 + 0.08 * c.high), ink=0, shade=0, mat=GLOW, soft=30)
        for k in range(14):    # far skyline
            x = k * 150 + 40 * h01(k)
            h = 200 + 260 * h01(k, "h")
            ink.box(x, 860 - h / 2, 60 + 20 * h01(k, "w"), h / 2, 4, fill=rgb("6a4a7a"), ink=0, shade=0, mat=WATER, boil=0,
                    seed=k)
            if h01(k, "sp") > 0.5:
                ink.tri((x - 20, 860 - h), (x, 860 - h - 90), (x + 20, 860 - h), fill=rgb("6a4a7a"), ink=0, mat=WATER)
        for k in range(8):     # nearer deco towers with windows on the highs
            x = 80 + k * 260
            h = 260 + 200 * h01(k, "nh")
            with ink.at(x, GROUND):
                for j in range(3):
                    ink.box(0, -h / 2 - j * 40, 90 - j * 22, h / 2 - j * 10, 4, fill=rgb("3a2a4a"), fill2=rgb("2a1e36"),
                            ink=3.5, shade=0.4)
                for j in range(int(h / 50)):
                    for i in (-1, 0, 1):
                        on = h01(k, j, i, int(c.bar)) < 0.3 + 0.5 * c.high
                        ink.box(i * 30, -40 - j * 48, 8, 12, 2, fill=rgb("ffd86a") if on else rgb("4a3a5a"),
                                ink=0, shade=0)
        # rooftop
        ink.box(W / 2, 995, W / 2 + 40, 95, 0, fill=rgb("8a5a4a"), fill2=rgb("5a3a2e"), ink=0, shade=0, mat=WATER, boil=0)
        for k in range(4):
            ink.capsule(-20, GROUND + 25 + k * 40, W + 20, GROUND + 25 + k * 40, 1.5, fill=rgb("3a2018"), ink=0, shade=0)
        ink.box(W / 2, GROUND, W / 2 + 40, 9, 0, fill=rgb("b0a090"), ink=3, shade=0.3)
        # water tower behind the heroes
        with ink.at(150, GROUND):
            for x in (-60, 60):
                ink.capsule(x, 0, x * 0.6, -200, 6, fill=rgb("4a3a30"), ink=3)
            ink.box(0, -290, 95, 100, 20, fill=rgb("9a6a44"), ink=5, shade=0.5)
            ink.tri((-110, -390), (0, -470), (110, -390), fill=rgb("6a4a34"), ink=5)
    elif layer == "front":
        with ink.at(0, 0, soft=8.0):
            ink.box(1860, 980, 80, 180, 6, fill=rgb("5a3a2e"), ink=0, shade=0.3)
            ink.box(60, 1030, 100, 80, 6, fill=rgb("5a3a2e"), ink=0, shade=0.3)


def forest(ink: Ink, c: Ctx, layer: str):
    if layer == "back":
        sky(ink, rgb("a8d0d8"), rgb("f6ecc8"), 61)
        for k in range(3):
            wash_cloud(ink, (k * 700 + c.t * 6) % (W + 400) - 200, 150 + 40 * k, 1.0, rgb("ffffff", 0.8), 3.1 + k)
        ink.wave(640, 50, 1500, 0.4, rgb("9ac07a"), fill2=rgb("78a05a"), mat=WATER, seed=62)
        ink.wave(740, 40, 1000, 2.0, rgb("7aa85a"), fill2=rgb("5a8a44"), mat=WATER, seed=63)
        for k, x in enumerate((90, 400, 760, 1130, 1800)):
            face_tree(ink, c, x, 800 + 20 * (k % 2), 0.8 + 0.2 * h01(k), k * 1.7, face=k % 2 == 1)
        ink.box(W / 2, 995, W / 2 + 40, 95, 0, fill=rgb("8ab85a"), fill2=rgb("5a8a3a"), ink=0, shade=0, mat=WATER, boil=0)
        for k in range(7):
            flower(ink, c, 80 + k * 180, GROUND + 20, 0.8, k * 2.3, col=rgb(("f06a6a", "f0c04a", "c06af0")[k % 3]))
        for k in range(3):    # mushrooms
            x = 980 + k * 70
            ink.capsule(x, GROUND + 10, x, GROUND - 40, 12, fill=rgb("f6efe0"), ink=3)
            ink.ellipse(x, GROUND - 50, 40, 26, fill=rgb("d9433a"), ink=3.5, shade=0.4)
            ink.ellipse(x - 12, GROUND - 58, 7, 5, fill=rgb("fff6e0"), ink=0, shade=0)
    elif layer == "front":
        with ink.at(0, 0, soft=9.0):
            for k in range(5):
                x = k * 480 + 60
                for j in range(5):
                    ink.capsule(x + j * 18, 1100, x + j * 22 - 30 + 20 * math.sin(c.t + j), 960 - 30 * (j % 2), 9, 3,
                                fill=rgb("3f6e2e"), ink=0, shade=0)


STAGES = {"ballroom": ballroom, "sky": skystage, "storm": lambda ink, c, layer: skystage(ink, c, layer, storm=True),
          "kitchen": kitchen, "graveyard": graveyard, "sea": sea, "city": city, "forest": forest}
