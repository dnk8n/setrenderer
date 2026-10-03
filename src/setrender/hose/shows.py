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


def hud(ink: Ink, c: Ctx, bpm: float, states: list[dict], alpha: float = 1.0):
    """Bottom corners, one panel per hero: their head, three hearts (HP) and five super cards that
    fill with damage dealt and parries; the tempo sits in the middle."""
    with ink.at(0, 0, fade=1 - alpha):
        ink.box(W / 2, 1036, 96, 30, 10, fill=rgb("f6efe0"), ink=4, shade=0.2)
        lettering.words(ink, f"BPM {int(round(bpm))}", W / 2, 1038, 30, fill=rgb("3a2416"), shadow=None,
                        outline=0.0, weight=6)
        for k, st in enumerate(states):
            sgn = 1 if k == 0 else -1
            x0 = 62 if k == 0 else W - 62
            with ink.at(x0 + sgn * 210, 1014, -0.012 * sgn):
                with ink.outlined(5):
                    ink.box(0, 0, 262, 44, 20, fill=rgb("f6efe0"), fill2=rgb("e6dcc4"), ink=0, shade=0.3)
                ink.box(-sgn * 112, 0, 2, 34, 1, fill=rgb("3a2416", 0.4), ink=0, shade=0)
                ink.box(sgn * 30, 0, 2, 34, 1, fill=rgb("3a2416", 0.4), ink=0, shade=0)
            heroes.portrait(ink, st["kind"], x0, 1006, 0.5, c.td, c.beat, down=st["down"])
            for j in range(3):
                x = x0 + sgn * (98 + j * 48)
                full = j < st["hp"]
                last = full and st["hp"] == 1
                lost = (not full) and j == st["hp"] and 0 <= st["hit_age"] < 0.6
                if lost:      # the heart that just went pops up and fades
                    q = st["hit_age"] / 0.6
                    ink.heart(x, 1008 - 60 * q, 22 * (1 + 0.5 * q), fill=rgb("d9433a", 1 - q), ink=3 * (1 - q),
                              rot=0.4 * q * sgn)
                if full:
                    pop = 1.0 + (0.25 * c.squash if last else 0.0)
                    blink = last and (c.beat % 1.0) < 0.35
                    ink.heart(x, 1012, 23 * pop, fill=rgb("fff6e8") if blink else rgb("d9433a"), ink=3.5)
                elif st["down"]:
                    ink.heart(x, 1012, 20, fill=rgb("8a8478", 0.5), ink=2.5)
                else:
                    ink.heart(x, 1012, 20, fill=rgb("3a2416", 0.18), ink=2.5)
            for j in range(5):
                x = x0 + sgn * (262 + j * 38)
                fill = min(1.0, max(0.0, st["meter"] - j))
                whole = fill >= 1.0
                pop = 1.0 + (0.18 * c.squash if whole and j == int(st["meter"]) - 1 else 0.0)
                with ink.at(x, 1014, 0.05 * math.sin(c.td * 2 + j) * sgn, pop):
                    ink.box(0, 0, 15, 24, 4, fill=rgb("fffaf0") if whole else rgb("3a2e28"), ink=3, shade=0.2)
                    if whole:
                        ink.heart(0, 2, 8.5, fill=rgb("d9433a"), ink=0)
                    elif fill > 0:
                        hh = 21 * fill
                        ink.box(0, 21 - hh, 12, hh, 2, fill=rgb("e8b14a"), ink=0, shade=0)


def take_card(ink: Ink, c: Ctx, n: int, u: float, beat_u: float, progress: float, boss_face, cast):
    """A lost take: the clapperboard snaps shut on the downbeat for the next TAKE, and a strip of film
    shows how far into the fight they got (three frames, one per phase) with the boss laughing at the
    far end."""
    ink.rays(W / 2, 420, 30, rgb("6a4a32"), rgb("4a3020"), phase=c.t * 0.05, mat=WATER)
    ink.rings(W / 2, 420, 110, rgb("fff0c0", 0.0), rgb("fff0c0", 0.08), phase=-c.t * 0.2, duty=0.8)
    deco_frame(ink, col=rgb("e8b14a"))
    # the clapperboard
    cx, cy = W / 2, 470
    with ink.at(cx, cy, 0.03 * math.sin(c.td * 2)):
        with ink.outlined(7):
            ink.box(0, 0, 330, 170, 16, fill=rgb("2a2622"), fill2=rgb("1a1714"), ink=0, shade=0.4)
        for yy in (-120, 125):
            ink.capsule(-300, yy, 300, yy, 2.0, fill=rgb("f2efe6", 0.6), ink=0, shade=0, boil=0.6)
        ink.capsule(0, 125, 0, 160, 2.0, fill=rgb("f2efe6", 0.6), ink=0, shade=0, boil=0.6)
        lettering.words(ink, f"TAKE {n}", 0, 20, 120, fill=rgb("f6f2e8"), shadow=None, outline=0.0, weight=9,
                        wobble=0.6, t=c.td)
        clap = min(1.0, beat_u)            # swings down over the first beat and slaps on the second
        ang = -0.55 * (1 - clap ** 2.2) + (0.05 * math.sin((beat_u - 1) * 25) * math.exp(-(beat_u - 1) * 6)
                                           if beat_u > 1 else 0.0)
        with ink.at(-330, -185, ang):
            with ink.outlined(6):
                ink.box(330, -24, 330, 26, 6, fill=rgb("f2efe6"), ink=0, shade=0.3)
            for k in range(7):
                x = 40 + k * 95
                ink.tri((x, 2), (x + 48, -50), (x + 92, -50), fill=rgb("2a2622"), ink=0)
                ink.tri((x, 2), (x + 92, -50), (x + 44, 2), fill=rgb("2a2622"), ink=0)
        if 1.0 <= beat_u < 1.6:
            rig.impact(ink, -300, -200, 120, (beat_u - 1.0) / 0.6)
    # the strip of film with the progress line
    x0, x1, y = 420.0, 1500.0, 820.0
    with ink.outlined(5):
        ink.box((x0 + x1) / 2, y, (x1 - x0) / 2 + 40, 62, 8, fill=rgb("1e1a16"), ink=0, shade=0)
    for k in range(28):
        xx = x0 - 20 + k * (x1 - x0 + 40) / 27
        for sy in (-46, 46):
            ink.box(xx, y + sy, 9, 7, 2, fill=rgb("f2e6c8"), ink=0, shade=0)
    for k in range(3):
        fx0 = x0 + k * (x1 - x0) / 3
        fx1 = fx0 + (x1 - x0) / 3
        ink.box((fx0 + fx1) / 2, y, (fx1 - fx0) / 2 - 8, 32, 4, fill=rgb("e8d8b0"), ink=0, shade=0.2)
    grow = min(1.0, u * 2.5)
    px = x0 + (x1 - x0) * progress * grow
    ink.capsule(x0 + 8, y, max(x0 + 9, px), y, 9, fill=rgb("c8372d"), ink=2.5, shade=0)
    for k, kind in enumerate(cast):
        heroes.ghost(ink, kind, px - 40 + k * 70, y - 120 - 12 * math.sin(c.t * 3 + k), c.t, c.beat, 0.42)
    if boss_face is not None:
        boss_face(ink, x1 + 120, y - 10, 0.55)


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
