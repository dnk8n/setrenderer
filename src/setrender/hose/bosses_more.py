"""Five more bosses, so a two-hour set has thirteen to beat: the Jelly Queen over the farm orchard
(knisper's jellyfish in the trees), DJ Hamhock, a purple hog on the decks of the festival field who
turns into a dragon for the last phase, Lava Louie in the psychedelic underground rave, Don Cartridge,
a mob-boss game cartridge in a speakeasy street, and the Projectionist, who fights from the cinema's
own stage and burns holes in the film. Original characters in the same rubber-hose style; the nods to
gaming and gangster films are parodies, not anyone's artwork."""
from __future__ import annotations

import math

from . import rig
from .bosses import BRASS, GOLD, PINK, RED, WHITE, _hurt_jitter, _ko, _ramp, big_face, h01_
from .ctx import Ctx
from .ink import GLOW, INK, Ink, mix, rgb


def _hsv(h: float, s: float = 0.75, v: float = 1.0):
    import colorsys
    r, g, b = colorsys.hsv_to_rgb(h % 1.0, s, v)
    return (r, g, b, 1.0)


# ---------------------------------------------------------------- 9. the jelly queen

def jelly_queen(ink: Ink, c: Ctx, bx=1430.0, by=400.0):
    dx, rot, ksq, kdz = _ko(c)
    pal = [(rgb("f59ad0"), rgb("c85aa0")), (rgb("b07ae8"), rgb("6a3aa8")), (rgb("6ad0f0"), rgb("2a6ab0"))][c.phase]
    body = c.col(mix(pal[0], rgb("8a8aa0"), 0.35 * c.dmg))
    body2 = c.col(pal[1])
    pump = c.squash * (0.5 + c.energy) + 0.3 * c.sub
    sag = 1 - 0.16 * c.dmg
    with ink.at(bx + dx + _hurt_jitter(c), by + 25 * math.sin(c.t * 0.9), rot, seed=91):
        ink.glow(0, 60, 360, (body[0], body[1], body[2], 0.35), soft=110)
        n = 9 - int(3 * c.dmg)
        for k in range(n):        # tentacles, swaying with the beat
            x0 = -170 + k * (340 / max(1, n - 1))
            sw = math.sin(c.td * 2 + k * 0.9 + c.beat * math.pi * 0.5)
            ln = 380 + 60 * math.sin(k * 1.3)
            ink.bez(x0, 60, x0 + 70 * sw, 60 + ln * 0.5, x0 - 40 * sw + 30 * math.sin(c.t + k), 60 + ln, 16, 4,
                    fill=(body[0], body[1], body[2], 0.85), ink=3.5, shade=0.3)
            if h01_(k + 11) < c.dmg:   # knotted and bandaged
                ink.box(x0 + 40 * sw, 60 + ln * 0.45, 22, 9, 4, fill=rgb("f6f0e2"), ink=2.5, shade=0.2, rot=0.4)
        for k in range(10):       # frilly skirt
            ink.ellipse(-210 + k * 46, 70, 30, 22 + 6 * math.sin(c.td * 4 + k), fill=body2, ink=3, shade=0.3)
        with ink.at(0, 0, 0, 1 + 0.08 * pump, (1 - 0.06 * pump) * sag):
            with ink.outlined(6):
                ink.pie(0, 70, 250, 270, cut=0.0, half=1.57, rot=math.pi, fill=body)
            for k in range(6):    # glowing spots inside the bell
                ink.ellipse(-150 + 60 * k, -40 - 60 * math.sin(k * 1.7), 18 + 6 * c.high, fill=(1, 1, 1, 0.25), ink=0,
                            shade=0, mat=GLOW, soft=8)
            ink.ellipse(-110, -110, 50, 26, fill=(1, 1, 1, 0.45), ink=0, shade=0, rot=-0.6)
            with ink.at(0, -205, 0.1 * math.sin(c.td * 2) - 0.25 * c.dmg):     # a crown, knocked askew as it's hit
                for k in range(5):
                    x = -80 + k * 40
                    ink.tri((x - 22, 0), (x, -70 - 20 * (k % 2)), (x + 22, 0), fill=c.col(GOLD), ink=3.5)
                    ink.ellipse(x, -55 - 20 * (k % 2), 8, fill=rgb("e03a6a") if k % 2 else rgb("6ad0f0"), ink=2, shade=0)
                ink.box(0, 4, 104, 16, 6, fill=c.col(GOLD), ink=3.5, shade=0.4)
            fire = math.exp(-c.shot * 5)
            big_face(ink, c, 0, -40, 0.95, look=(-0.9, 0.2), angry=0.45 * c.phase, open_=0.25 + 0.6 * fire, blink=kdz)
        if c.phase == 2:          # electric crackles in the last phase
            for k in range(3):
                if math.sin(c.td * 17 + k * 2.1) > 0.2:
                    x = -200 + k * 200
                    pts = [(x, 120), (x + 30, 200), (x - 20, 240), (x + 15, 330)]
                    rig.stroke(ink, pts, 8, col=rgb("fff07a"))
        if c.ko >= 0:
            rig.dazed_stars(ink, 0, -330, 160, c.t)


JELLY = {"name": "jelly", "title": "THE JELLY QUEEN", "stage": "orchard", "sky": False, "emit": (1300, 470),
         "draw": jelly_queen, "shot": "jelly",
         "patterns": [["aimed", "wave", "rain"], ["wave", "rain", "spread"], ["spread", "rain", "wave", "ring"]],
         "face": (1430, 360, 150), "top": (1430, 120), "minions": ("runner", "flyer")}


# ---------------------------------------------------------------- 10. DJ Hamhock (a hog who turns dragon)

def hamhock(ink: Ink, c: Ctx, bx=1440.0, by=905.0):
    dx, rot, ksq, kdz = _ko(c)
    dragon = c.phase == 2
    skin = c.col(mix(rgb("9a5ac8"), rgb("8a2a6a"), 0.7 if dragon else 0.0))
    skin2 = c.col(mix(rgb("5a2a8a"), rgb("4a0a3a"), 0.7 if dragon else 0.0))
    snout = c.col(rgb("f2a6c8"))
    sq = c.squash * (0.5 + c.energy)
    with ink.at(bx + dx + _hurt_jitter(c), by, rot, 1 + 0.05 * sq, 1 - 0.06 * sq - ksq, seed=101):
        if dragon:                # wings, a tail and smoke: the hog's true form
            flap = math.sin(c.td * 3.2)
            for side in (-1, 1):
                with ink.at(side * 150, -520, side * (0.35 + 0.25 * flap)):
                    with ink.outlined(5):
                        ink.tri((0, 0), (side * 420, -200), (side * 300, 120), fill=skin2, ink=0, rnd=10)
                        ink.tri((0, 0), (side * 300, 120), (side * 120, 170), fill=skin2, ink=0, rnd=8)
                    for k in range(3):
                        ink.capsule(0, 0, side * (420 - k * 110), -200 + k * 120, 4, fill=skin, ink=0, shade=0)
            ink.bez(160, -160, 360, -60, 330 + 40 * math.sin(c.t * 3), -300, 30, 10, fill=skin, ink=5, shade=0.4)
            ink.tri((320, -290), (380, -350), (350, -270), fill=c.col(rgb("e03a3a")), ink=3)
        # body behind the decks
        with ink.outlined(6):
            ink.ellipse(0, -360, 250, 230, fill=skin, fill2=skin2, ink=0, shade=0.55)
        if dragon:
            for k in range(5):
                ink.tri((-120 + k * 60, -575 + 10 * (k % 2)), (-100 + k * 60, -640), (-80 + k * 60, -575),
                        fill=c.col(rgb("e8b14a")), ink=3)
        # head
        hy = -560
        with ink.at(0, hy, 0.06 * math.sin(c.beat * math.pi)):
            for side in (-1, 1):  # ears (horns as a dragon)
                if dragon:
                    ink.bez(side * 110, -120, side * 180, -200, side * 150, -280, 18, 4, fill=c.col(rgb("f2e6c8")), ink=3.5)
                else:
                    ink.tri((side * 90, -110), (side * 190, -210), (side * 170, -80), fill=skin, ink=4.5, rnd=6)
                    ink.tri((side * 110, -115), (side * 170, -180), (side * 160, -100), fill=snout, ink=0, rnd=4)
            with ink.outlined(6):
                ink.ellipse(0, 0, 190, 160, fill=skin, fill2=skin2, ink=0, shade=0.5)
            ink.arc(0, -40, 175, 16, 1.25, rot=math.pi, fill=rgb("2a2430"))       # headphones
            for side in (-1, 1):
                ink.ellipse(side * 182, -10, 30, 48, fill=rgb("2a2430"), ink=4, shade=0.3)
                ink.ellipse(side * 182, -10, 18, 32, fill=rgb("ff4a9a") if c.kick > 0.4 else rgb("8a2a5a"), ink=0, shade=0)
            fire = math.exp(-c.shot * 5)
            big_face(ink, c, 0, -20, 0.8, look=(-0.9, 0.2), angry=0.45 * c.phase, open_=0.3 + 0.6 * fire + 0.2 * c.kick,
                     blink=kdz)
            ink.ellipse(0, 26, 62, 44, fill=snout, ink=4, shade=0.4)                  # the snout
            ink.ellipse(-20, 26, 10, 15, fill=rgb("5a1a3a"), ink=0, shade=0)
            ink.ellipse(20, 26, 10, 15, fill=rgb("5a1a3a"), ink=0, shade=0)
            if dragon and fire > 0.3:
                for k in range(4):
                    q = (c.t * 2.5 + k / 4) % 1.0
                    ink.ellipse(-60 - 120 * q, 20 - 40 * q, 16 + 30 * q, fill=(0.4, 0.38, 0.4, 0.6 * (1 - q)), ink=0,
                                shade=0, soft=4)
        # the decks
        ink.box(0, -150, 300, 70, 10, fill=c.col(rgb("3a2a3a")), ink=5, shade=0.4)
        for side in (-1, 1):
            with ink.at(side * 150, -222):
                ink.ellipse(0, 0, 105, 24, fill=rgb("1e1816"), ink=3.5, shade=0.2)
                ink.rings(0, 0, 8, rgb("3a3330"), rgb("1e1816"), radius=100, phase=c.t * 3 * side)
                ink.ellipse(0, 0, 26, 7, fill=c.col(rgb("ff4a9a") if side < 0 else rgb("4ad0ff")), ink=2, shade=0)
        ink.box(0, -225, 40, 18, 4, fill=rgb("5a5660"), ink=3, shade=0.3)
        for k in range(4):
            ink.box(-24 + 16 * k, -230 + 6 * math.sin(c.td * 5 + k), 3, 8, 1, fill=rgb("fff07a"), ink=0, shade=0)
        # arms scratching the records
        for side in (-1, 1):
            sc = math.sin(c.td * 14 + side) * 30 if c.energy > 0.4 else math.sin(c.beat * math.pi) * 15
            hx, hy2 = side * 150 + sc, -240
            rig.hose(ink, side * 210, -380, hx, hy2, 0.25 * side, r=13, col=skin2)
            rig.glove(ink, hx, hy2, math.pi / 2, "open", side=side, s=1.5)
        ink.box(0, -80, 260, 80, 10, fill=c.col(rgb("4a3a44")), ink=5, shade=0.5)
        for k in range(5):
            ink.box(-200 + 100 * k, -80, 30, 50, 6, fill=rgb("2a2024"), ink=3, shade=0.2)
            ink.ellipse(-200 + 100 * k, -80, 18 + 8 * c.sub, fill=rgb("5a4a54"), ink=2.5, shade=0.4)
        if c.ko >= 0:
            rig.dazed_stars(ink, 0, -820, 170, c.t)


HAMHOCK = {"name": "hamhock", "title": "DJ HAMHOCK", "stage": "festival", "sky": False, "emit": (1240, 560),
           "draw": hamhock, "shot": "record", "shot2": "fireball",
           "patterns": [["arc", "aimed", "spread"], ["arc", "spread", "wave", "ring"], ["spread", "rain", "wave", "aimed"]],
           "face": (1440, 330, 140), "top": (1440, 160), "minions": ("runner", "flyer")}


# ---------------------------------------------------------------- 11. Lava Louie

def lava_louie(ink: Ink, c: Ctx, bx=1440.0, by=905.0):
    dx, rot, ksq, kdz = _ko(c)
    hue0 = [0.08, 0.78, (c.t * 0.12) % 1.0][c.phase]
    liquid = c.col(_hsv(hue0 + 0.08, 0.55, 1.0))
    blob = c.col(_hsv(hue0, 0.85, 1.0))
    metal = c.col(rgb("c0c4cc"))
    sq = c.squash * (0.5 + c.energy)
    with ink.at(bx + dx + _hurt_jitter(c), by, rot, 1 + 0.05 * sq, 1 - 0.07 * sq - ksq, seed=111):
        for side in (-1, 1):
            kx = side * (70 + 25 * math.sin(c.beat * math.pi) * (c.phase >= 1))
            rig.hose(ink, side * 70, -60, kx, -10, 0.2 * side, r=12)
            rig.shoe(ink, kx, 0, side, 1.5, rgb("3a2a4a"))
        with ink.outlined(6):     # the base and the cap
            ink.tri((-170, -40), (170, -40), (110, -190), fill=metal, ink=0, rnd=14)
            ink.tri((-170, -40), (-110, -190), (110, -190), fill=metal, ink=0, rnd=14)
            ink.tri((-90, -660), (90, -660), (0, -780), fill=metal, ink=0, rnd=14)
        ink.glow(0, -420, 260, (blob[0], blob[1], blob[2], 0.3 + 0.2 * c.sub), soft=90)
        with ink.outlined(6):     # the glass
            ink.box(0, -425, 140, 240, 110, fill=liquid, ink=0, shade=0.3)
        for k in range(7):        # wax blobs rising and sinking with the bass
            u = (c.t * (0.08 + 0.02 * k) + h01_(k + 5)) % 1.0
            y = -200 - 430 * (0.5 - 0.5 * math.cos(u * 2 * math.pi))
            x = -70 + 140 * h01_(k + 9) + 20 * math.sin(c.t + k)
            r = 30 + 22 * h01_(k + 3) + 14 * c.bass
            ink.ellipse(x, y, r * (1 + 0.15 * math.sin(c.t * 3 + k)), r * (1 - 0.1 * math.sin(c.t * 3 + k)), fill=blob,
                        ink=0, shade=0.3)
        ink.box(-90, -440, 18, 170, 10, fill=(1, 1, 1, 0.35), ink=0, shade=0)
        if c.dmg > 0.4:           # cracked glass, wax dripping
            rig.stroke(ink, [(60, -560), (20, -500), (50, -460), (10, -400)], 3, col=rgb("f6f2e8"))
            for k in range(2):
                q = (c.t * 0.7 + k / 2) % 1.0
                ink.ellipse(120 + 10 * k, -400 + 380 * q, 10, 14, fill=blob, ink=2.5, shade=0.3)
        fire = math.exp(-c.shot * 5)
        big_face(ink, c, 0, -470, 0.8, look=(-0.9, 0.2), angry=0.45 * c.phase, open_=0.3 + 0.6 * fire, blink=kdz)
        for side in (-1, 1):      # arms waving a glowstick and a lighter-shaped flame
            ang = -math.pi / 2 + side * (0.8 + 0.5 * math.sin(c.beat * math.pi + side))
            hx, hy = side * 150 + math.cos(ang) * 150, -300 + math.sin(ang) * 120
            rig.hose(ink, side * 130, -260, hx, hy, 0.2 * side, r=11)
            rig.glove(ink, hx, hy, ang, "fist", side=side, s=1.5)
            if side < 0:
                ink.glow(hx, hy - 40, 50, (0.4, 1.0, 0.5, 0.5), soft=30)
                ink.capsule(hx, hy, hx + 10, hy - 80, 8, fill=rgb("8aff6a"), ink=2.5, shade=0)
        if c.ko >= 0:
            rig.dazed_stars(ink, 0, -850, 160, c.t)


LAVA = {"name": "lava", "title": "LAVA LOUIE", "stage": "rave", "sky": False, "emit": (1300, 470), "draw": lava_louie,
        "shot": "lava",
        "patterns": [["wave", "aimed", "ring"], ["wave", "spread", "ring", "rain"], ["spread", "wave", "ring", "rain"]],
        "face": (1440, 430, 120), "top": (1440, 140), "minions": ("runner", "flyer")}


# ---------------------------------------------------------------- 12. Don Cartridge

def don_cartridge(ink: Ink, c: Ctx, bx=1430.0, by=905.0):
    dx, rot, ksq, kdz = _ko(c)
    shell = c.col(rgb("8a8e98"))
    shell2 = c.col(rgb("5a5e68"))
    suit = c.col(rgb("2a2632"))
    sq = c.squash * (0.5 + c.energy)
    glitch = c.phase == 2 and math.sin(c.td * 23) > 0.5
    for gk, off in ([(1, 9), (2, -9)] if glitch else []) + [(0, 0)]:
        tint = {0: None, 1: (1, 0.2, 0.3, 0.35), 2: (0.2, 0.9, 1, 0.35)}[gk]
        with ink.at(bx + dx + _hurt_jitter(c) + off, by, rot, 1 + 0.05 * sq, 1 - 0.07 * sq - ksq, seed=121,
                    fade=0.6 if gk else None):
            for side in (-1, 1):
                kx = side * (60 + 20 * math.sin(c.beat * math.pi) * (c.phase >= 1))
                rig.hose(ink, side * 60, -80, kx, -10, 0.15 * side, r=13, col=suit)
                rig.shoe(ink, kx, 0, side, 1.6, rgb("1e1612"))
                ink.box(kx + 10 * side, -22, 26, 10, 4, fill=WHITE, ink=3, shade=0.2)          # spats
            with ink.outlined(6):    # the cartridge
                ink.box(0, -400, 190, 260, 24, fill=tint or shell, fill2=None if tint else shell2, ink=0, shade=0.5)
            for k in range(6):       # the grip ridges along the top
                ink.capsule(-150 + k * 60, -630, -150 + k * 60, -600, 7, fill=shell2, ink=0, shade=0)
            peel = c.dmg * 0.4
            with ink.at(0, -430, -peel * 0.3):
                ink.box(0, 0, 150, 150, 12, fill=rgb("f2e6c8"), ink=4, shade=0.2)
                for k in range(3):   # a pixel-art sunset on the label
                    ink.box(0, 90 - k * 22, 140, 10, 2, fill=(rgb("e8605a"), rgb("f0a04a"), rgb("f0d04a"))[k], ink=0, shade=0)
            fire = math.exp(-c.shot * 5)
            big_face(ink, c, 0, -460, 0.85, look=(-0.9, 0.2), angry=0.4 + 0.3 * c.phase, open_=0.25 + 0.6 * fire,
                     blink=kdz)
            with ink.outlined(5):    # the pinstripe vest and lapels
                ink.box(0, -200, 190, 60, 10, fill=suit, ink=0, shade=0.4)
            for k in range(9):
                ink.capsule(-170 + 42 * k, -250, -170 + 42 * k, -150, 1.5, fill=rgb("8a8698"), ink=0, shade=0)
            ink.ellipse(120, -220, 22, fill=rgb("d9433a"), ink=3, shade=0.4)                     # a carnation
            with ink.at(-20, -670, -0.15 + 0.1 * math.sin(c.beat * math.pi) - 0.3 * (c.phase >= 1)):   # the fedora
                with ink.outlined(5):
                    ink.ellipse(0, 0, 230, 34, fill=suit, ink=0, shade=0.4)
                    ink.box(0, -60, 140, 60, 30, fill=suit, ink=0, shade=0.4)
                ink.box(0, -22, 142, 14, 3, fill=rgb("c8372d"), ink=0, shade=0)
            # the joypad tommy gun
            aim = math.exp(-c.shot * 4)
            gx, gy = -230 - 30 * aim, -300
            rig.hose(ink, -150, -330, gx + 60, gy + 10, -0.2, r=12, col=suit)
            rig.hose(ink, 150, -330, gx + 140, gy + 30, 0.3, r=12, col=suit)
            with ink.at(gx, gy, 0.08 * aim):
                ink.box(0, 0, 110, 40, 30, fill=rgb("3a3a44"), ink=4, shade=0.4)
                ink.capsule(-110, -4, -200, -4, 12, fill=rgb("2a2a30"), ink=3)
                ink.ellipse(60, 30, 40, fill=rgb("2a2a30"), ink=3.5, shade=0.4)       # drum magazine
                ink.box(-40, -6, 18, 6, 2, fill=rgb("8a8e98"), ink=0, shade=0)
                ink.box(-40, -6, 6, 18, 2, fill=rgb("8a8e98"), ink=0, shade=0)
                for k in range(2):
                    ink.ellipse(20 + 22 * k, -10 + 8 * k, 9, fill=(rgb("e03a3a"), rgb("3ad04a"))[k], ink=2, shade=0.3)
                if aim > 0.3:
                    ink.star(-215, -4, 30 * aim + 10, 6, 2.5, fill=rgb("fff6c0"), ink=2.5, rot=c.t * 9)
    if c.ko >= 0:
        rig.dazed_stars(ink, bx, by - 820, 160, c.t)


DON = {"name": "don", "title": "DON CARTRIDGE", "stage": "speakeasy", "sky": False, "emit": (1180, 590),
       "draw": don_cartridge, "shot": "pixel",
       "patterns": [["aimed", "aimed", "spread"], ["aimed", "spread", "wave"], ["spread", "spread", "aimed", "rain"]],
       "face": (1430, 430, 130), "top": (1410, 200), "minions": ("runner", "flyer")}


# ---------------------------------------------------------------- 13. the Projectionist

def projectionist(ink: Ink, c: Ctx, bx=1450.0, by=905.0):
    dx, rot, ksq, kdz = _ko(c)
    body = c.col(rgb("3a3a44"))
    body2 = c.col(rgb("22222a"))
    sq = c.squash * (0.5 + c.energy)
    spin = c.t * (3 + 6 * c.energy) * (1 + 2 * (c.phase == 2))
    with ink.at(bx + dx + _hurt_jitter(c), by, rot, 1 + 0.05 * sq, 1 - 0.06 * sq - ksq, seed=131):
        for k, ax in enumerate((-110, 0, 110)):     # tripod legs, the front one tapping the beat
            tap = 20 * max(0.0, math.sin(c.beat * math.pi)) if k == 1 else 0
            ink.capsule(0, -200, ax * 1.4, -tap, 10, fill=c.col(rgb("8a6a44")), ink=3.5)
            rig.shoe(ink, ax * 1.4, -tap, 1 if ax >= 0 else -1, 1.2, rgb("2a2024"))
        # the beam out of the lens (to the left, at the heroes' screen)
        lx, ly = -260, -370
        ink.glow(lx - 300, ly, 380, (1.0, 0.96, 0.8, 0.12 + 0.08 * c.high), soft=80, ry=140)
        with ink.outlined(6):
            ink.box(0, -380, 190, 160, 20, fill=body, fill2=body2, ink=0, shade=0.5)
            ink.box(-210, -370, 70, 60, 16, fill=body, ink=0, shade=0.5)
        for k in range(8):
            ink.ellipse(-170 + k * 48, -520, 6, fill=c.col(rgb("8a8e98")), ink=0, shade=0)
        with ink.at(lx, ly):       # the lens is its third eye
            ink.ellipse(0, 0, 58, fill=rgb("1e1e26"), ink=4, shade=0.3)
            ink.ellipse(0, 0, 40, fill=c.col(rgb("fff2c0")), ink=3, shade=0.3)
            ink.ellipse(-8, 0, 18, fill=INK, ink=0, shade=0)
            if c.dmg > 0.45:
                rig.stroke(ink, [(-30, -30), (-6, -6), (-14, 10), (20, 34)], 3, col=rgb("f6f2e8"))
        fire = math.exp(-c.shot * 5)
        big_face(ink, c, 30, -390, 0.75, look=(-0.9, 0.2), angry=0.45 * c.phase, open_=0.25 + 0.6 * fire, blink=kdz)
        for k, (rx, ry) in enumerate(((-90, -650), (110, -680))):    # the reels
            wob = 0.15 * math.sin(c.t * 7 + k) * c.dmg
            with ink.at(rx, ry, spin * (1 if k else -1) + wob):
                ink.ellipse(0, 0, 120, fill=c.col(rgb("c0c4cc")), ink=5, shade=0.4)
                for j in range(5):
                    a = j * 2 * math.pi / 5
                    ink.ellipse(math.cos(a) * 66, math.sin(a) * 66, 28, fill=body2, ink=3, shade=0.2)
                ink.ellipse(0, 0, 18, fill=body, ink=3, shade=0.3)
        ink.bez(-90, -530, 10, -480 + 30 * math.sin(c.t * 4), 110, -560, 8, fill=rgb("3a2a20"), ink=2.5, shade=0)
        ink.bez(-200, -400, -180, -520, -140, -620, 8, fill=rgb("3a2a20"), ink=2.5, shade=0)
        # the crank arm
        a = spin
        cx, cy = 210 + math.cos(a) * 50, -360 + math.sin(a) * 50
        rig.hose(ink, 190, -300, cx, cy, 0.3, r=11)
        rig.glove(ink, cx, cy, a, "fist", side=1, s=1.4)
        if c.phase == 2 or c.dmg > 0.85:
            for k in range(4):
                q = (c.t * 0.9 + k / 4) % 1.0
                ink.ellipse(60 * math.sin(k + q * 3), -580 - 260 * q, 26 + 40 * q, fill=(0.35, 0.33, 0.33, 0.6 * (1 - q)),
                            ink=0, shade=0, soft=6)
        if c.ko >= 0:
            rig.dazed_stars(ink, 0, -850, 170, c.t)


PROJECTIONIST = {"name": "projectionist", "title": "THE PROJECTIONIST", "stage": "cinema", "sky": False,
                 "emit": (1190, 535), "draw": projectionist, "shot": "reel",
                 "patterns": [["aimed", "arc", "wave"], ["arc", "spread", "wave", "ring"], ["spread", "rain", "arc", "ring"]],
                 "face": (1480, 390, 120), "top": (1460, 150), "minions": ("runner", "flyer")}

ROSTER_MORE = [JELLY, HAMHOCK, LAVA, DON, PROJECTIONIST]


# ---------------------------------------------------------------- their projectiles

def projectile_more(ink: Ink, kind: str, col, t: float, seed: float, ang: float) -> bool:
    if kind == "jelly":
        ink.glow(0, 0, 40, (1.0, 0.6, 0.85, 0.35), soft=24)
        for k in range(3):
            ink.bez(-12 + 12 * k, 10, -16 + 12 * k + 8 * math.sin(t * 12 + k), 28, -10 + 12 * k, 42, 4, 2,
                    fill=col or rgb("f59ad0"), ink=2, shade=0)
        with ink.outlined(3.5):
            ink.pie(0, 10, 26, 28, cut=0.0, half=1.57, rot=math.pi, fill=col or rgb("f59ad0"))
        rig.eye(ink, -8, -2, 5, 8, (-1, 0), 0.0)
        rig.eye(ink, 8, -2, 5, 8, (-1, 0), 0.0)
        return True
    if kind == "lava":
        w = math.sin(t * 9 + seed * 6)
        ink.glow(0, 0, 50, (1.0, 0.5, 0.2, 0.4), soft=30)
        ink.ellipse(0, 0, 26 * (1 + 0.15 * w), 24 * (1 - 0.15 * w), fill=col or rgb("ff7a2a"), fill2=rgb("ffd04a"),
                    ink=4, shade=0.4)
        ink.ellipse(16, 12, 9, fill=col or rgb("ff7a2a"), ink=2.5, shade=0.3)
        return True
    if kind == "pixel":
        p = 9
        for i, j in ((0, 0), (1, 0), (0, 1), (1, 1), (-1, 0), (0, -1), (2, 0), (0, 2)):
            ink.box(i * p * 2 - p, j * p * 2 - p, p, p, 0, fill=col or rgb("7aff7a"), ink=2, shade=0, boil=0.2)
        ink.glow(0, 0, 40, (0.5, 1.0, 0.5, 0.3), soft=24)
        return True
    if kind == "reel":
        with ink.at(0, 0, t * 15):
            ink.ellipse(0, 0, 30, fill=col or rgb("c0c4cc"), ink=4, shade=0.4)
            for j in range(4):
                a = j * math.pi / 2
                ink.ellipse(math.cos(a) * 15, math.sin(a) * 15, 7, fill=rgb("22222a"), ink=0, shade=0)
        ink.capsule(10, 0, 50 * math.cos(ang + math.pi), 50 * math.sin(ang + math.pi), 3, fill=rgb("3a2a20"), ink=0,
                    shade=0)
        return True
    return False
