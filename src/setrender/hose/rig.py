"""Rubber-hose parts shared by every character: hose limbs, four-finger gloves, big shoes, pie-cut
eyes, open mouths, blush and the bounce timing that makes 1930s cartoons dance."""
from __future__ import annotations

import math

from .ink import INK, Ink, rgb

GLOVE = rgb("fbf7ec")
SHOE = rgb("6b3a24")
LIMB = rgb("1e1612")
WHITE = rgb("fffaf0")
MOUTH = rgb("5a1a14")
TONGUE = rgb("e0605a")
BLUSH = rgb("f08a7a", 0.55)


def ease_io(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def bounce(phase: float) -> float:
    """Classic rubber-hose bounce over one beat: down hard on the beat, float up between beats.
    Returns 0 (top) .. 1 (squashed on the beat)."""
    p = phase % 1.0
    return math.exp(-p * 7.0) * 1.0 + 0.0 * p


def hop(phase: float) -> float:
    """Height of a little hop each beat (0 on the beat, peak mid-beat)."""
    p = phase % 1.0
    return math.sin(math.pi * p) ** 1.3


def hose(ink: Ink, x0, y0, x1, y1, bend: float, r: float = 7.0, col=LIMB, taper: float = 0.85):
    """A jointless limb: a quadratic curve that bows sideways by `bend` (fraction of its length)."""
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    dx, dy = x1 - x0, y1 - y0
    cx, cy = mx - dy * bend, my + dx * bend
    ink.bez(x0, y0, cx, cy, x1, y1, r, r * taper, fill=col, ink=2.5, shade=0.25)


def glove(ink: Ink, x, y, ang: float, pose: str = "open", side: float = 1.0, s: float = 1.0, col=GLOVE):
    """A white four-finger glove at the wrist (x, y) pointing along `ang`. side=+1/-1 mirrors the thumb."""
    with ink.at(x, y, ang, s, s * side):
        with ink.outlined(3.2):
            ink.ellipse(16, 0, 15, 14, fill=col, ink=0, shade=0.45)
            if pose == "open":
                for k, (fy, ln) in enumerate(((-9, 17), (0, 19), (9, 16))):
                    ink.capsule(22, fy * 0.8, 22 + ln, fy * 1.5, 6.2, 5.6, fill=col, ink=0, shade=0.35)
                ink.capsule(14, -10, 20, -24, 5.6, 5.0, fill=col, ink=0, shade=0.3)
            elif pose == "point":
                ink.capsule(22, -5, 46, -6, 5.6, 5.2, fill=col, ink=0, shade=0.35)
                ink.capsule(14, -11, 15, -25, 5.4, 5.0, fill=col, ink=0, shade=0.3)
                for k in range(2):
                    ink.ellipse(29, 3 + k * 8, 7, 5.5, fill=col, ink=0, shade=0.35)
            elif pose == "fist":
                for k in range(3):
                    ink.ellipse(28, -8 + k * 8, 7, 6, fill=col, ink=0, shade=0.35)
                ink.ellipse(18, -12, 7, 6, fill=col, ink=0, shade=0.3)
            elif pose == "peace":
                ink.capsule(22, -5, 44, -14, 5.4, 5.0, fill=col, ink=0, shade=0.35)
                ink.capsule(22, 3, 44, 8, 5.4, 5.0, fill=col, ink=0, shade=0.35)
                ink.ellipse(27, 10, 7, 5.5, fill=col, ink=0, shade=0.35)
            ink.ellipse(2, 0, 8, 15, fill=col, ink=0, shade=0.2)
        # the three stitches on the back of the glove
        if pose in ("open", "fist", "point"):
            for k in (-4, 0, 4):
                ink.capsule(10, k, 18, k * 1.2, 0.9, fill=INK, ink=0, shade=0)


def shoe(ink: Ink, x, y, facing: float = 1.0, s: float = 1.0, col=SHOE, lift: float = 0.0):
    """Big round cartoon shoe, heel at (x, y) on the ground."""
    with ink.at(x, y, -lift * 0.5 * facing, s * facing, s):
        with ink.outlined(3.5):
            ink.ellipse(12, -14, 30, 17, fill=col, ink=0, shade=0.55)
            ink.ellipse(-8, -12, 14, 13, fill=col, ink=0, shade=0.5)
        ink.ellipse(22, -22, 8, 4, fill=(1, 0.95, 0.85, 0.55), ink=0, shade=0, rot=-0.3)


def eye(ink: Ink, x, y, rx, ry, look=(0.0, 0.0), blink: float = 0.0, cut: float = 0.7, angry: float = 0.0,
        side: float = 1.0, pupil: float = 0.55, white=WHITE):
    """Tall oval eye with a pie-cut pupil. blink 0..1 closes it to a curved line."""
    if blink > 0.8:
        ink.arc(x, y + ry * 0.1, rx * 1.05, 2.4, 1.15, rot=0.0, fill=INK)
        return
    ry2 = ry * (1 - blink)
    ink.ellipse(x, y, rx, ry2, fill=white, ink=3.0, shade=0.3)
    px = x + look[0] * rx * 0.42
    py = y + look[1] * ry2 * 0.45 + ry2 * 0.12
    prx, pry = rx * pupil, min(ry2 * 0.62, ry * 0.62)
    if pry > 2:
        ink.pie(px, py, prx, pry, cut=cut * side, half=0.33)
    if angry > 0:
        # a heavy lid line slanting into the nose
        ink.capsule(x - rx * 1.1 * side, y - ry * (0.9 - angry * 0.5), x + rx * 1.0 * side, y - ry * (0.9 + angry * 0.15),
                    3.2 + angry * 2, fill=INK, ink=0, shade=0)


def mouth(ink: Ink, x, y, w, open_: float, smile: float = 1.0, teeth: bool = True, tongue: bool = True,
          grimace: float = 0.0):
    """Big grin. open_ 0 = a smile line, 1 = wide open with tongue; grimace 1 = gritted teeth."""
    if grimace > 0.5:
        h = w * (0.22 + 0.25 * open_)
        ink.box(x, y, w * 0.55, h, h * 0.8, fill=MOUTH, ink=3.2, shade=0)
        ink.box(x, y, w * 0.5, h * 0.62, h * 0.5, fill=WHITE, ink=2.2, shade=0.1)
        for k in range(1, 6):
            xx = x - w * 0.5 + k * w / 6
            ink.capsule(xx, y - h * 0.6, xx, y + h * 0.6, 1.2, fill=INK, ink=0, shade=0)
        ink.capsule(x - w * 0.5, y, x + w * 0.5, y, 1.2, fill=INK, ink=0, shade=0)
        return
    if open_ < 0.12:
        ink.arc(x, y - w * 0.25 * smile, w * 0.55, 2.6, 0.95, rot=0.0 if smile >= 0 else math.pi, fill=INK)
        return
    h = w * 0.62 * open_ + 6
    # a D-shaped grin: the lower half of an ellipse, flat across the top
    ink.pie(x, y - h * 0.15, w * 0.56, h, cut=0.0, half=1.5, fill=MOUTH, ink=3.2)
    if tongue and h > 12:
        ink.ellipse(x + w * 0.1, y + h * 0.55, w * 0.25, h * 0.28, fill=TONGUE, ink=0, shade=0.3)
    if teeth and h > 20:
        ink.box(x, y + 2, w * 0.36, min(5.0, h * 0.12), 2.5, fill=WHITE, ink=0, shade=0)
    if open_ > 0.55:
        ink.arc(x - w * 0.6, y - 4, 5, 2.0, 1.0, rot=-0.9, fill=INK)
        ink.arc(x + w * 0.6, y - 4, 5, 2.0, 1.0, rot=0.9, fill=INK)


def stroke(ink: Ink, pts, w: float = 3.0, col=INK):
    """A plain ink stroke through points (cracks, scratches)."""
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        ink.capsule(x0, y0, x1, y1, w * 0.5, fill=col, ink=0.0, shade=0.0)


def blush(ink: Ink, x, y, r):
    ink.ellipse(x, y, r, r * 0.6, fill=BLUSH, ink=0, shade=0, soft=4.0, boil=0.0)


def speed_lines(ink: Ink, x, y, ang: float, n: int = 3, ln: float = 60.0, spread: float = 18.0, alpha: float = 0.8):
    for k in range(n):
        o = (k - (n - 1) / 2) * spread
        with ink.at(x, y, ang):
            ink.capsule(-ln - abs(o) * 0.5, o, -10, o, 1.6, fill=(*INK[:3], alpha), ink=0, shade=0)


def impact(ink: Ink, x, y, r, t: float, col=rgb("fff3c4")):
    """Cartoon 'pow' burst that pops and fades over t in 0..1."""
    if t >= 1:
        return
    k = 1 - t
    with ink.at(x, y, t * 0.6, 0.4 + 0.9 * math.sqrt(t), fade=t ** 2):
        ink.star(0, 0, r, 8, 3.2, fill=col, ink=4, shade=0.1)
        ink.star(0, 0, r * 0.55 * k + 4, 8, 3.2, fill=(1, 1, 1, 1), ink=0, shade=0)


def dazed_stars(ink: Ink, x, y, r, t: float, n: int = 4):
    for k in range(n):
        a = t * 4 + k * 2 * math.pi / n
        ink.star(x + math.cos(a) * r, y + math.sin(a) * r * 0.35, 13, 5, 2.4, fill=rgb("ffe37a"), ink=3,
                 rot=t * 3 + k)


def note(ink: Ink, x, y, s=1.0, col=INK, rot=0.0, double=False):
    """An eighth note (or two beamed sixteenths)."""
    with ink.at(x, y, rot, s):
        if double:
            ink.ellipse(-14, 10, 10, 7.5, fill=col, ink=0, rot=-0.4, shade=0.2)
            ink.ellipse(14, 4, 10, 7.5, fill=col, ink=0, rot=-0.4, shade=0.2)
            ink.capsule(-5, 8, -5, -30, 2.4, fill=col, ink=0, shade=0)
            ink.capsule(23, 2, 23, -36, 2.4, fill=col, ink=0, shade=0)
            ink.capsule(-5, -30, 23, -36, 4, fill=col, ink=0, shade=0)
        else:
            ink.ellipse(0, 0, 11, 8, fill=col, ink=0, rot=-0.4, shade=0.2)
            ink.capsule(9, -2, 9, -40, 2.4, fill=col, ink=0, shade=0)
            ink.bez(9, -40, 22, -30, 18, -14, 3, 1.5, fill=col, ink=0, shade=0)
