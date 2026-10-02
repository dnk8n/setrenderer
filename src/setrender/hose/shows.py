"""Everything between the fights: the opening title card, intermissions (bouncing-ball sing-along,
the overworld map, a vaudeville number), title-card lettering, the HUD and THE END."""
from __future__ import annotations

import math

from . import heroes, lettering, rig, stages
from .ctx import Ctx
from .ink import INK, WATER, Ink, mix, rgb
from .story import h01

W, H = 1920.0, 1080.0
CREAM = rgb("fbefc8")
TITLE_FILL = rgb("fde9a6")


def deco_frame(ink: Ink, col=rgb("3a2416"), inset=40):
    """Art-deco border of a title card."""
    for k, w in enumerate((10, 4)):
        d = inset + k * 22
        ink.box(W / 2, H / 2, W / 2 - d, H / 2 - d, 40 - k * 10, fill=(0, 0, 0, 0), ink=w, shade=0)
    for sx in (-1, 1):
        for sy in (-1, 1):
            x, y = W / 2 + sx * (W / 2 - inset - 10), H / 2 + sy * (H / 2 - inset - 10)
            ink.star(x, y, 34, 4, 2.2, fill=rgb("e8b14a"), ink=4, rot=0.0)


def title_card(ink: Ink, c: Ctx, title: str, cast: list[str], names: list[str], u: float, hero_pose):
    """Opening card: rings and rays, the set title, the stars of the show waving."""
    ink.rays(W / 2, 420, 36, rgb("f6d48a"), rgb("e3a456"), phase=c.t * 0.05, mat=WATER)
    ink.rings(W / 2, 420, 120, rgb("fff0c0", 0.0), rgb("fff0c0", 0.18), phase=-c.t * 0.2, duty=0.8)
    ink.ellipse(W / 2, 420, 760, 240, fill=rgb("7a2a1e"), fill2=rgb("4a160e"), ink=8, shade=0.4)
    ink.ellipse(W / 2, 420, 720, 205, fill=(0, 0, 0, 0), ink=3, shade=0, ink_col=rgb("e8b14a"))
    deco_frame(ink)
    title = " ".join(title.replace("_", " ").replace("&", " & ").split())
    parts = [p.strip() for p in title.split(" - ") if p.strip()] or [title]
    pop = lambda k: 1.0 + 0.08 * math.exp(-((c.beat - k * 0.25) % 4) * 3)  # noqa: E731
    if len(parts) >= 2:
        sz = min(120.0, 1500 / max(8, len(parts[0])) * 1.25)
        lettering.words(ink, parts[0], W / 2, 350, sz, fill=TITLE_FILL, wobble=0.6, t=c.td, arc=-0.12, pop=pop)
        sz2 = min(96.0, 1300 / max(6, len(parts[1])) * 1.2)
        lettering.words(ink, " - ".join(parts[1:]), W / 2, 500, sz2, fill=rgb("fff6dc"), wobble=0.4, t=c.td + 1)
    else:
        sz = min(130.0, 1500 / max(8, len(parts[0])) * 1.25)
        lettering.words(ink, parts[0], W / 2, 420, sz, fill=TITLE_FILL, wobble=0.6, t=c.td, arc=-0.12, pop=pop)
    lettering.words(ink, "A RUBBER HOSE REVUE", W / 2, 690, 40, fill=rgb("3a2416"), shadow=None, outline=0.0,
                    weight=7)
    lettering.words(ink, "STARRING", W / 2, 770, 34, fill=rgb("3a2416"), shadow=None, outline=0.0, weight=6)
    lettering.words(ink, f"{names[0]} & {names[1]}", W / 2, 840, 54, fill=rgb("c8372d"), shadow=(0.2, 0.1, 0.05, 0.6),
                    wobble=0.5, t=c.td + 2)
    for k, kind in enumerate(cast):
        x = 330 if k == 0 else W - 330
        heroes.draw(ink, kind, x, 1010, hero_pose(k, "wave"), 1.0)


def end_card(ink: Ink, c: Ctx, cast, hero_pose):
    ink.rays(W / 2, H / 2, 28, rgb("f3c46a"), rgb("e39a4a"), phase=c.t * 0.04, mat=WATER)
    ink.rings(W / 2, H / 2, 90, rgb("fbe2a0", 0.25), rgb("000000", 0.0), phase=-c.t * 0.3)
    deco_frame(ink)
    lettering.words(ink, "THE END", W / 2, 420, 200, fill=TITLE_FILL, wobble=0.5, t=c.td, arc=-0.1)
    for k, kind in enumerate(cast):
        heroes.draw(ink, kind, 700 + k * 520, 960, hero_pose(k, "bow"), 1.1)


def map_screen(ink: Ink, c: Ctx, u: float, cast, hero_pose, stops: list[str], k_from: int):
    """Overworld interlude: a painted island, a dotted path and the heroes walking to the next boss."""
    ink.box(W / 2, H / 2, W / 2 + 60, H / 2 + 60, 0, fill=rgb("7ab0c0"), fill2=rgb("4a88a8"), ink=0, shade=0,
            mat=WATER, boil=0, seed=71)
    for k in range(10):
        x = (k * 230 + c.t * 15) % (W + 200) - 100
        y = 60 + (k * 97) % 960
        ink.arc(x, y, 20, 2, 0.8, rot=math.pi, fill=rgb("e8f4f8", 0.7), boil=0.5)
    with ink.at(0, 0, mat=WATER, boil=0.0):
        for k, (x, y, r) in enumerate(((560, 520, 380), (980, 470, 420), (1380, 560, 360), (820, 760, 260),
                                       (1240, 280, 240), (700, 280, 220))):
            ink.ellipse(x, y, r * 1.1, r * 0.8, fill=rgb("e8d8a0"), ink=0, shade=0.2, seed=80 + k)
        for k, (x, y, r) in enumerate(((560, 520, 340), (980, 470, 380), (1380, 560, 320), (820, 760, 220),
                                       (1240, 280, 200), (700, 280, 190))):
            ink.ellipse(x, y, r * 1.1, r * 0.8, fill=rgb("8ab86a"), fill2=rgb("6a9a4a"), ink=0, shade=0.2, seed=90 + k)
    # the path through the stops
    pts = [(380, 640), (620, 420), (900, 600), (1150, 360), (1420, 520), (1560, 700)]
    for (x0, y0), (x1, y1) in zip(pts[:-1], pts[1:]):
        for j in range(8):
            f = j / 8
            ink.ellipse(x0 + (x1 - x0) * f, y0 + (y1 - y0) * f, 7, 5, fill=rgb("6a4a2a"), ink=0, shade=0, boil=0.6)
    icons = ["tent", "tree", "house", "tower", "boat", "flag"]
    for k, (x, y) in enumerate(pts):
        hop = rig.hop(c.beat + k * 0.25) * 10
        kind = icons[k % len(icons)]
        with ink.at(x, y - hop):
            if kind == "tent":
                ink.tri((-60, 0), (0, -90), (60, 0), fill=rgb("c8372d"), ink=4)
                ink.tri((-20, 0), (0, -50), (20, 0), fill=rgb("3a2416"), ink=2)
            elif kind == "tree":
                stages.face_tree(ink, c, 0, 10, 0.4, k)
            elif kind == "house":
                ink.box(0, -35, 50, 35, 6, fill=rgb("f6efe0"), ink=4, shade=0.3)
                ink.tri((-62, -60), (0, -110), (62, -60), fill=rgb("6a8ac8"), ink=4)
            elif kind == "tower":
                ink.box(0, -70, 26, 70, 8, fill=rgb("b8b0a0"), ink=4, shade=0.4)
                ink.tri((-34, -130), (0, -190), (34, -130), fill=rgb("c8372d"), ink=4)
            elif kind == "boat":
                ink.ellipse(0, -10, 60, 22, fill=rgb("9a6a40"), ink=4, shade=0.4)
                ink.tri((0, -20), (0, -100), (50, -30), fill=CREAM, ink=3)
            else:
                ink.capsule(0, 0, 0, -110, 4, fill=rgb("3a2416"), ink=2)
                ink.tri((0, -110), (60, -90 + 8 * math.sin(c.t * 6)), (0, -70), fill=rgb("f0c04a"), ink=3)
    # heroes walk the path one step per beat
    seg = (u * (len(pts) - 1))
    i = min(int(seg), len(pts) - 2)
    f = seg - i
    x = pts[i][0] + (pts[i + 1][0] - pts[i][0]) * f
    y = pts[i][1] + (pts[i + 1][1] - pts[i][1]) * f
    face = 1.0 if pts[i + 1][0] >= pts[i][0] else -1.0
    for k, kind in enumerate(cast):
        p = hero_pose(k, "walk")
        p.facing = face
        heroes.draw(ink, kind, x - k * 70 * face, y + 30 - k * 6, p, 0.45)
    # clouds drifting over the map, out of focus
    with ink.at(0, 0, soft=8.0):
        for k in range(2):
            stages.cel_cloud(ink, c, (k * 1100 + c.t * 40) % (W + 600) - 300, 200 + k * 600, 1.6, k + 4, face=False,
                             col=rgb("ffffff", 0.75), col2=rgb("e8eef0", 0.75))


def singalong(ink: Ink, c: Ctx, u: float, cast, hero_pose, vocal: float):
    """Follow the bouncing ball: a ball bounces from note to note across a staff, one note a beat."""
    ink.box(W / 2, H / 2, W / 2 + 60, H / 2 + 60, 0, fill=rgb("f3e3b8"), fill2=rgb("d9bf88"), ink=0, shade=0,
            mat=WATER, boil=0, seed=73)
    ink.rays(W / 2, -200, 24, rgb("ffffff", 0.18), rgb("ffffff", 0.0), phase=c.t * 0.02, mat=WATER)
    deco_frame(ink, inset=30)
    y0 = 430
    for k in range(5):
        ink.capsule(160, y0 + k * 36, W - 160, y0 + k * 36, 2.2, fill=rgb("3a2416"), ink=0, shade=0, boil=0.6)
    # treble clef-ish curl
    ink.bez(220, y0 + 170, 160, y0 + 40, 230, y0 - 40, 6, 4, fill=INK, ink=0, shade=0)
    ink.bez(230, y0 - 40, 280, y0 + 60, 200, y0 + 110, 6, 4, fill=INK, ink=0, shade=0)
    beat = c.beat
    n = 8
    b0 = math.floor(beat / n) * n
    xs = [380 + j * 180 for j in range(n)]
    def note_y(j):
        return y0 + 36 * 4 - 18 * int(h01("nt", b0 + j) * 9)
    for j in range(n):
        lit = (b0 + j) <= beat
        col = rgb("c8372d") if lit else INK
        rig.note(ink, xs[j], note_y(j), 1.6, col, double=h01("nd", b0 + j) > 0.7)
        if vocal > 0.3:
            lettering.words(ink, ("LA", "DA", "DOO", "BOP", "HEY")[int(h01("syl", b0 + j) * 5)], xs[j], y0 + 240, 44,
                            fill=col if lit else rgb("6a5a4a"), shadow=None, outline=0.0, weight=7)
    j = int(beat - b0)
    f = beat - math.floor(beat)
    jn = min(j + 1, n - 1)
    bx = xs[j] + (xs[jn] - xs[j]) * f
    by = note_y(j) + (note_y(jn) - note_y(j)) * f - 30 - 160 * math.sin(math.pi * f)
    ink.ellipse(bx, note_y(j) - 22, 24 * (1 - 0.4 * math.sin(math.pi * f)), 6, fill=(0, 0, 0, 0.25), ink=0, shade=0, soft=4)
    sq = math.exp(-f * 9)
    ink.ellipse(bx, by, 26 * (1 + 0.25 * sq), 26 * (1 - 0.25 * sq), fill=rgb("fffaf0"), ink=4, shade=0.5)
    for k, kind in enumerate(cast):
        p = hero_pose(k, "sing")
        heroes.draw(ink, kind, 260 if k == 0 else W - 260, 1000, p, 0.75)


def vaudeville(ink: Ink, c: Ctx, u: float, cast, hero_pose, xs):
    """A soft-shoe number on the ballroom stage, in a spotlight, with straw hats."""
    stages.ballroom(ink, c, "back")
    for k, kind in enumerate(cast):
        x = xs[k]
        ink.ellipse(x, 905, 170, 34, fill=(1, 0.95, 0.75, 0.35), ink=0, shade=0, soft=10)
        p = hero_pose(k, "softshoe")
        heroes.draw(ink, kind, x, 905, p, 1.15)
    stages.ballroom(ink, c, "front")
    stages.audience(ink, c, cheer=0.4 * c.energy)


def hud(ink: Ink, c: Ctx, bpm: float, cards: int, alpha: float = 1.0):
    """Bottom-left card box: tempo instead of hit points, and five super cards that fill with parries."""
    with ink.at(0, 0, fade=1 - alpha):
        ink.box(140, 1010, 92, 34, 10, fill=rgb("f6efe0"), ink=4, shade=0.2)
        lettering.words(ink, f"BPM {int(round(bpm))}", 140, 1012, 32, fill=rgb("3a2416"), shadow=None, outline=0.0,
                        weight=6)
        for k in range(5):
            x = 270 + k * 44
            full = k < cards
            pop = 1.0 + (0.15 * c.squash if full and k == cards - 1 else 0.0)
            with ink.at(x, 1010, 0.06 * math.sin(c.td * 2 + k), pop):
                ink.box(0, 0, 17, 26, 4, fill=rgb("f6efe0") if full else rgb("6a5a4a", 0.6), ink=3, shade=0.2)
                if full:
                    ink.heart(0, 2, 10, fill=rgb("d9433a"), ink=0)


def card_text(ink: Ink, c: Ctx, text: str, kind: str, u: float, sub: str | None = None):
    """Title lettering cards: READY? GO! KNOCKOUT! and the drop exclamations."""
    if kind == "ready":
        s = 150
        y = 430
        pop = 1.0 + 0.12 * math.exp(-(c.beat % 1) * 5)
        with ink.at(W / 2, y, 0, pop * min(1.0, u * 6)):
            lettering.words(ink, text, 0, 0, s, fill=TITLE_FILL, wobble=1.0, t=c.td)
        if sub:
            lettering.words(ink, sub, W / 2, 260, 52, fill=rgb("fff6dc"), wobble=0.4, t=c.td)
    elif kind == "go":
        k = min(1.0, u * 5)
        s = 230 * (0.6 + 0.4 * k) * (1 + 0.1 * math.exp(-u * 8))
        with ink.at(W / 2, 470, -0.05, 1.0, fade=max(0.0, (u - 0.7) / 0.3)):
            lettering.words(ink, text, 0, 0, s, fill=rgb("fff2b0"), wobble=1.4, t=c.td)
    elif kind == "ko":
        k = min(1.0, u * 4)
        s = 200 * (0.3 + 0.7 * k)
        with ink.at(W / 2, 470, 0.04 * math.sin(c.td * 3), 1.0 + 0.06 * c.squash,
                    fade=max(0.0, (u - 0.8) / 0.2)):
            lettering.words(ink, text, 0, 0, s, fill=rgb("fff2b0"), wobble=1.2, t=c.td, arc=-0.15)
    elif kind == "word":
        rot = (h01(text) - 0.5) * 0.3
        s = 170 * (0.5 + 0.5 * min(1.0, u * 6))
        with ink.at(W / 2 + (h01(text, 1) - 0.5) * 300, 330, rot, 1.0, fade=max(0.0, (u - 0.65) / 0.35)):
            ink.star(0, 0, 330 + 20 * c.squash, 12, 3.2, fill=rgb("fff3c4", 0.92), ink=6, shade=0.2,
                     rot=c.td * 0.2)
            lettering.words(ink, text, 0, 0, s * 0.55, fill=rgb("c8372d"), wobble=1.0, t=c.td,
                            shadow=(0.1, 0.05, 0.03, 0.7))
    elif kind == "inter":
        with ink.at(W / 2, 150, 0, min(1.0, u * 5), fade=max(0.0, (u - 0.8) / 0.2)):
            lettering.words(ink, text, 0, 0, 72, fill=TITLE_FILL, wobble=0.8, t=c.td)
