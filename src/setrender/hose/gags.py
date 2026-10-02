"""Running gags, mostly cued by Apple's on-device sound classifier: a jazz horn pops in when it hears
brass, a candlestick phone rings with the ringtones, a black cat strolls through on a meow, a
skeleton plays its ribs like a xylophone (The Skeleton Dance, 1929), a steamboat toots on a foghorn
(Steamboat Willie, 1928), a stork brings a crying baby, a ghost wobbles in on a theremin..."""
from __future__ import annotations

import math

from . import lettering, rig
from .ctx import Ctx
from .ink import GLOW, INK, Ink, rgb
from .story import Gag

W, H = 1920.0, 1080.0


def _slide(u: float, side: float, inner: float, outer: float = 260.0) -> float:
    """x that slides in from the side, holds, then slides back out."""
    k = min(1.0, u / 0.12, (1 - u) / 0.12)
    k = k * k * (3 - 2 * k)
    edge = -outer if side < 0 else W + outer
    tgt = inner if side < 0 else W - inner
    return edge + (tgt - edge) * k


def horn(ink: Ink, c: Ctx, g: Gag, u: float):
    x = _slide(u, g.side, 230)
    y = 640 + 14 * math.sin(c.beat * math.pi)
    f = -g.side
    blow = c.squash
    with ink.at(x, y, 0.15 * f * math.sin(c.beat * math.pi), 1.0):
        with ink.at(0, 0, 0, f, 1.0):
            with ink.outlined(5):
                ink.capsule(-60, 0, 110, -10, 20, 26, fill=rgb("e8b14a"), ink=0, shade=0.5)
                ink.tri((100, -10), (190, -90 - 20 * blow), (190, 70 + 20 * blow), fill=rgb("e8b14a"), ink=0, rnd=10,
                        shade=0.5)
            ink.ellipse(190, -10, 22, 80 + 20 * blow, fill=rgb("5a2a14"), ink=4, shade=0)
            for k in range(3):
                ink.ellipse(10 + k * 30, -34, 8, 12, fill=rgb("f6efe0"), ink=3, shade=0.3)
            rig.eye(ink, -40, -10, 10, 16, (0.6, 0), 0.0)
            rig.eye(ink, -10, -10, 10, 16, (0.6, 0), 0.0)
            ink.ellipse(-85, 4, 26, 22 * (1 + 0.5 * blow), fill=rgb("e8b14a"), ink=4, shade=0.5)
        for k in range(3):
            q = ((c.td * 0.6 + k / 3) % 1.0)
            rig.note(ink, 200 * f + q * 300 * f, -60 - q * 200 + 30 * math.sin(q * 9), 1.0,
                     rgb("3a2416", 1 - q), rot=q * f)


def phone(ink: Ink, c: Ctx, g: Gag, u: float):
    x = _slide(u, g.side, 200)
    ring = math.sin(c.t * 60) * 0.12 * (math.sin(c.t * 4) > 0)
    hop = rig.hop(c.beat) * 30
    with ink.at(x, 1000 - hop, ring):
        ink.ellipse(0, -10, 60, 18, fill=rgb("2a2420"), ink=4, shade=0.3)
        ink.capsule(0, -20, 0, -170, 14, 10, fill=rgb("2a2420"), ink=4, shade=0.4)
        ink.ellipse(0, -190, 34, 26, fill=rgb("2a2420"), ink=4, shade=0.4)
        rig.eye(ink, -12, -195, 9, 14, (0, 0), 0.0)
        rig.eye(ink, 12, -195, 9, 14, (0, 0), 0.0)
        ink.capsule(30, -130, 70, -160 - 30 * abs(ring) * 8, 9, fill=rgb("2a2420"), ink=4, shade=0.3)
        rig.mouth(ink, 0, -160, 22, 0.8)
    if math.sin(c.t * 4) > 0:
        lettering.words(ink, "RING!", x, 760 - hop, 50, fill=rgb("fff2b0"), wobble=2.0, t=c.t)


def cat(ink: Ink, c: Ctx, g: Gag, u: float):
    f = -g.side
    x = (W + 200) * (u if f > 0 else 1 - u) - 100
    step = c.beat * 0.5
    with ink.at(x, 1000):
        for k in range(4):
            ph = step * 2 * math.pi + k * math.pi / 2
            lx = (-40 + k * 26) * f
            ink.capsule(lx, -60, lx + 14 * math.sin(ph) * f, -6 - 8 * max(0, math.cos(ph)), 6, fill=INK, ink=0)
        ink.ellipse(0, -80, 70, 34, fill=INK, ink=0, shade=0)
        ink.bez(-60 * f, -90, -120 * f, -160, -90 * f, -200 + 20 * math.sin(c.td * 3), 8, 5, fill=INK, ink=0)
        with ink.at(70 * f, -120):
            ink.ellipse(0, 0, 40, 36, fill=INK, ink=0, shade=0)
            ink.tri((-34, -20), (-26, -66), (-6, -32), fill=INK, ink=0)
            ink.tri((34, -20), (26, -66), (6, -32), fill=INK, ink=0)
            ink.ellipse(-12, -6, 13, 16, fill=rgb("fff8e0"), ink=0, shade=0)
            ink.ellipse(12, -6, 13, 16, fill=rgb("fff8e0"), ink=0, shade=0)
            ink.pie(-10 + 4 * f, -4, 6, 10, cut=0.5, half=0.3)
            ink.pie(14 + 4 * f, -4, 6, 10, cut=0.5, half=0.3)
            ink.ellipse(0, 10, 7, 5, fill=rgb("f08a7a"), ink=0, shade=0)
    if 0.3 < u < 0.6:
        lettering.words(ink, "MEOW!", x + 60 * f, 790, 46, fill=rgb("fff2b0"), wobble=1.5, t=c.t)


def skeleton(ink: Ink, c: Ctx, g: Gag, u: float, x=None):
    """Plays its own ribs like a xylophone, then dances off."""
    x = _slide(u, g.side, 260) if x is None else x
    bone = rgb("f4efe0")
    sw = math.sin(c.beat * math.pi)
    with ink.at(x, 1000 - rig.hop(c.beat) * 20):
        for side in (-1, 1):
            kx = side * (30 + 20 * sw * side)
            ink.capsule(side * 18, -150, kx, -10, 6, fill=bone, ink=3)
            ink.ellipse(kx + 10 * side, -6, 18, 8, fill=bone, ink=3, shade=0.3)
        ink.ellipse(0, -160, 30, 16, fill=bone, ink=3.5, shade=0.3)
        ink.capsule(0, -170, 0, -300, 6, fill=bone, ink=3)
        for k in range(5):
            hit = (int(c.beat * 2) % 5) == k
            col = rgb("ffe37a") if hit else bone
            ink.arc(0, -290 + k * 24, 46 - k * 3, 6, 1.2, rot=math.pi, fill=col, ink=2.5)
        with ink.at(0, -350, 0.15 * sw):
            ink.ellipse(0, 0, 48, 46, fill=bone, ink=4, shade=0.4)
            ink.ellipse(-16, -2, 13, 15, fill=INK, ink=0, shade=0)
            ink.ellipse(16, -2, 13, 15, fill=INK, ink=0, shade=0)
            ink.tri((-5, 18), (0, 8), (5, 18), fill=INK, ink=0)
            for k in range(5):
                ink.box(-16 + k * 8, 32, 3, 7, 1, fill=bone, ink=2, shade=0)
        mall = -290 + (int(c.beat * 2) % 5) * 24
        for side in (-1, 1):
            hx = side * 70
            ink.capsule(side * 40, -300, hx, mall + 20, 5, fill=bone, ink=3)
            ink.capsule(hx, mall + 20, side * 20, mall, 3, fill=rgb("8a5a34"), ink=2)
            ink.ellipse(side * 18, mall, 9, fill=rgb("c8372d"), ink=2.5, shade=0.3)


def ghost(ink: Ink, c: Ctx, g: Gag, u: float):
    x = W * (0.15 + 0.7 * u) if g.side > 0 else W * (0.85 - 0.7 * u)
    y = 380 + 60 * math.sin(c.t * 2.2)
    k = min(1.0, u / 0.15, (1 - u) / 0.15)
    with ink.at(x, y, 0.1 * math.sin(c.t * 3), 1.0, fade=1 - k * 0.85):
        ink.glow(0, 0, 120, (0.85, 1, 0.9, 0.3), soft=60)
        ink.ellipse(0, -30, 70, 80, fill=rgb("eef8f0"), ink=4, shade=0.3)
        ink.bez(-70, -20, -60, 120 + 20 * math.sin(c.t * 8), 30, 90, 30, 6, fill=rgb("eef8f0"), ink=4, shade=0.3)
        rig.eye(ink, -22, -40, 12, 20, (0, 0.4), 0.0)
        rig.eye(ink, 22, -40, 12, 20, (0, 0.4), 0.0)
        ink.ellipse(0, 10, 16, 20, fill=INK, ink=0, shade=0)


def steamboat(ink: Ink, c: Ctx, g: Gag, u: float):
    x = -300 + (W + 600) * u
    y = 760
    toot = math.sin(c.beat * math.pi * 0.5) > 0.7
    with ink.at(x, y + 6 * math.sin(c.t * 3), 0.03 * math.sin(c.t * 2)):
        ink.ellipse(0, 0, 200, 40, fill=rgb("f6efe0"), ink=4, shade=0.4)
        ink.box(0, -20, 200, 18, 6, fill=rgb("c8372d"), ink=4, shade=0.3)
        ink.box(-20, -70, 120, 40, 8, fill=rgb("f6efe0"), ink=4, shade=0.3)
        for k, sx in enumerate((-60, 40)):
            sq = 1 + (0.25 if toot and k == 0 else 0)
            ink.box(sx, -150, 22, 60 * sq, 6, fill=rgb("2a2420"), ink=4, shade=0.3)
            ink.box(sx, -210 * sq, 28, 8, 3, fill=rgb("c8372d"), ink=3, shade=0)
        ink.ellipse(120, -10, 50, fill=rgb("c8372d"), ink=4, shade=0.4)
        for k in range(6):
            a = c.t * 4 + k
            ink.capsule(120, -10, 120 + math.cos(a) * 46, -10 + math.sin(a) * 46, 4, fill=rgb("f6efe0"), ink=2)
        if toot:
            for k in range(4):
                q = (c.t * 2 + k / 4) % 1.0
                ink.ellipse(-60 - q * 80, -230 - q * 120, 20 + 30 * q, fill=(1, 1, 1, 0.8 * (1 - q)), ink=3 * (1 - q),
                            shade=0.2)


def frog(ink: Ink, c: Ctx, g: Gag, u: float):
    x = 260 if g.side < 0 else W - 260
    k = min(1.0, u / 0.1, (1 - u) / 0.1)
    croak = c.squash
    with ink.at(x, 1080 + 60 - 170 * k):
        ink.ellipse(0, 0, 90, 60, fill=rgb("6aa84a"), ink=4, shade=0.5)
        ink.ellipse(0, 40, 50 * (1 + croak * 0.6), 34 * (1 + croak * 0.8), fill=rgb("e8f0b0"), ink=4, shade=0.3)
        for s in (-1, 1):
            ink.ellipse(s * 40, -55, 26, 26, fill=rgb("6aa84a"), ink=4, shade=0.4)
            rig.eye(ink, s * 40, -55, 15, 17, (0, 0), 0.0)
        ink.arc(0, -10, 50, 3, 1.0, fill=INK)
    if croak > 0.5 and k > 0.9:
        lettering.words(ink, "RIBBIT!", x, 820, 44, fill=rgb("fff2b0"), wobble=1.5, t=c.t)


def stork(ink: Ink, c: Ctx, g: Gag, u: float):
    x = W + 200 - (W + 400) * u
    y = 220 + 40 * math.sin(c.t * 1.5)
    flap = math.sin(c.t * 7)
    with ink.at(x, y):
        ink.ellipse(0, 0, 80, 40, fill=rgb("fbf7ec"), ink=4, shade=0.4)
        for s in (-1, 1):
            ink.bez(0, -10, s * 70, -80 * flap, s * 150, -40 * flap, 22, 6, fill=rgb("fbf7ec"), ink=4, shade=0.3)
        ink.capsule(-70, -10, -110, -60, 12, 9, fill=rgb("fbf7ec"), ink=4)
        ink.ellipse(-120, -70, 24, 22, fill=rgb("fbf7ec"), ink=4, shade=0.3)
        ink.tri((-138, -74), (-200, -60), (-138, -60), fill=rgb("e8a04a"), ink=3)
        rig.eye(ink, -124, -76, 6, 9, (-1, 0), 0.0)
        ink.capsule(-170, -60, -170, 30, 2.5, fill=INK, ink=0)
        with ink.at(-170, 60, 0.2 * math.sin(c.t * 3)):
            ink.ellipse(0, 0, 40, 32, fill=rgb("f6efe0"), ink=4, shade=0.4)
            ink.tri((-20, -24), (0, -40), (20, -24), fill=rgb("f6efe0"), ink=3)
            ink.ellipse(0, 6, 16, 14, fill=rgb("f8c8a8"), ink=3, shade=0.3)
            ink.arc(0, 12, 6, 1.5, 0.9, fill=INK, rot=math.pi)


def gong(ink: Ink, c: Ctx, g: Gag, u: float):
    x = _slide(u, g.side, 230)
    hit = c.squash
    with ink.at(x, 560):
        ink.capsule(-140, -170, -140, 260, 8, fill=rgb("8a2a1a"), ink=3)
        ink.capsule(140, -170, 140, 260, 8, fill=rgb("8a2a1a"), ink=3)
        ink.capsule(-160, -170, 160, -170, 10, fill=rgb("8a2a1a"), ink=3)
        with ink.at(0, 30, 0.08 * hit * math.sin(c.t * 40)):
            ink.glow(0, 0, 160, (1, 0.8, 0.4, 0.3 * hit), soft=60)
            ink.ellipse(0, 0, 120, fill=rgb("e8b14a"), fill2=rgb("b07a2a"), ink=5, shade=0.6)
            ink.rings(0, 0, 18, rgb("f0c86a", 0.5), rgb("b07a2a", 0.0), radius=110)
    if hit > 0.6:
        lettering.words(ink, "GONG!", x, 300, 70, fill=rgb("fff2b0"), wobble=2.0, t=c.t)


def chicken(ink: Ink, c: Ctx, g: Gag, u: float):
    f = -g.side
    x = (W + 200) * (u if f > 0 else 1 - u) - 100
    peck = c.squash
    with ink.at(x, 1000, 0, f, 1.0):
        for s in (-1, 1):
            ph = c.beat * math.pi * 2 + (s > 0) * math.pi
            ink.capsule(s * 10, -50, s * 10 + 14 * math.sin(ph), -4, 3, fill=rgb("e8a04a"), ink=2)
        ink.ellipse(0, -80, 50, 40, fill=rgb("fbf7ec"), ink=4, shade=0.4)
        ink.ellipse(-40, -96, 18, 26, fill=rgb("fbf7ec"), ink=4, shade=0.3, rot=0.5)
        with ink.at(40, -120 + 40 * peck, 0.6 * peck):
            ink.ellipse(0, 0, 26, 24, fill=rgb("fbf7ec"), ink=4, shade=0.4)
            ink.ellipse(0, -26, 10, 12, fill=rgb("d9433a"), ink=3, shade=0)
            ink.tri((22, -4), (44, 2), (22, 8), fill=rgb("e8a04a"), ink=2.5)
            rig.eye(ink, 6, -6, 6, 9, (1, 0), 0.0)


def scratch(ink: Ink, c: Ctx, g: Gag, u: float):
    """A record with a face in the corner, scratched back and forth by a glove."""
    x = _slide(u, g.side, 170, 300)
    y = 230
    back = math.sin(c.t * 14) * 0.9
    with ink.at(x, y):
        ink.ellipse(0, 0, 120, 120, fill=rgb("2a2420"), ink=5, shade=0.3)
        ink.rings(0, 0, 9, rgb("3a3330"), rgb("1e1816"), radius=118, phase=c.t)
        with ink.at(0, 0, back):
            ink.ellipse(0, 0, 40, fill=rgb("c8372d"), ink=3, shade=0.2)
            rig.eye(ink, -12, -6, 7, 11, (0, 0), 0.0)
            rig.eye(ink, 12, -6, 7, 11, (0, 0), 0.0)
            ink.arc(0, 10, 12, 2, 0.9, fill=INK)
        rig.glove(ink, 60 + 20 * back, -70, 2.4, "open", side=1, s=1.3)


def piano(ink: Ink, c: Ctx, g: Gag, u: float):
    x = _slide(u, g.side, 260, 400)
    hop = rig.hop(c.beat) * 26
    with ink.at(x, 1000 - hop, 0.05 * math.sin(c.beat * math.pi)):
        for s in (-1, 1):
            ink.capsule(s * 120, -60, s * 130 + 10 * math.sin(c.beat * math.pi) * s, 0, 10, fill=rgb("2a2420"), ink=3)
        ink.box(0, -160, 170, 110, 16, fill=rgb("2a2420"), ink=5, shade=0.4)
        ink.box(0, -90, 160, 22, 4, fill=rgb("f6efe0"), ink=3, shade=0)
        for k in range(14):
            down = (int(c.beat * 2 + k) % 7 == 0)
            ink.box(-150 + k * 23, -96 + (4 if down else 0), 3, 12, 1, fill=INK, ink=0, shade=0)
        rig.eye(ink, -40, -190, 18, 26, (0, 0), 0.0)
        rig.eye(ink, 40, -190, 18, 26, (0, 0), 0.0)
        rig.mouth(ink, 0, -140, 70, 0.4 + 0.4 * c.squash)


def bird(ink: Ink, c: Ctx, g: Gag, u: float):
    x = _slide(u, g.side, 300)
    with ink.at(x, 300 + 30 * math.sin(c.t * 3)):
        ink.ellipse(0, 0, 30, 24, fill=rgb("5a9ad8"), ink=3.5, shade=0.4)
        ink.tri((26, -4), (46, 0), (26, 6), fill=rgb("e8a04a"), ink=2.5)
        rig.eye(ink, 10, -6, 6, 9, (1, 0), 0.0)
        flap = math.sin(c.t * 20)
        ink.ellipse(-6, -10 - 10 * flap, 18, 10, fill=rgb("4a80c0"), ink=3, shade=0.3, rot=-0.5 * flap)
        q = (c.td * 0.7) % 1.0
        rig.note(ink, 60 + q * 120, -40 - q * 120, 0.7, rgb("3a2416", 1 - q))


def laugh(ink: Ink, c: Ctx, g: Gag, u: float, x=1300.0, y=200.0):
    if int(c.beat * 2) % 2 == 0:
        lettering.words(ink, "HA HA!", x + 30 * math.sin(c.t * 7), y, 64, fill=rgb("fff2b0"), wobble=2.5, t=c.t)


DRAW = {"horn": horn, "phone": phone, "cat": cat, "skeleton": skeleton, "ghost": ghost, "steamboat": steamboat,
        "frog": frog, "stork": stork, "gong": gong, "chicken": chicken, "scratch": scratch, "piano": piano,
        "fiddle": horn, "bird": bird, "laugh": laugh}
