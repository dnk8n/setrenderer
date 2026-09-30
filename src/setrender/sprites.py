"""Procedural pixel-art characters: blocky (Minecraft-like), stick figures and NES-style sprites.

Every character is generated from a seeded RNG, pre-rendered once per pose, then only blitted.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pygame

SKIN = [(255, 224, 189), (241, 194, 125), (224, 172, 105), (198, 134, 66),
        (141, 85, 36), (99, 57, 29), (70, 40, 22)]
HAIR = [(20, 16, 16), (60, 36, 20), (120, 70, 30), (230, 200, 90), (200, 60, 30),
        (255, 60, 180), (60, 200, 255), (130, 255, 80), (180, 90, 255), (240, 240, 240)]
HAIR_STYLES = ["short", "long", "afro", "mohawk", "bun", "bald", "bob", "braids", "cap"]
BOTTOMS = ["pants", "skirt", "shorts", "dress"]
FLAGS = {
    "rainbow": [(228, 3, 3), (255, 140, 0), (255, 237, 0), (0, 128, 38), (36, 64, 142), (115, 41, 130)],
    "trans": [(91, 206, 250), (245, 169, 184), (255, 255, 255), (245, 169, 184), (91, 206, 250)],
    "nonbinary": [(252, 244, 52), (255, 255, 255), (156, 89, 209), (44, 44, 44)],
    "bi": [(214, 2, 112), (214, 2, 112), (155, 79, 150), (0, 56, 168), (0, 56, 168)],
    "pan": [(255, 33, 140), (255, 216, 0), (33, 177, 255)],
}
NEON = [(0, 255, 120), (255, 0, 200), (0, 220, 255), (255, 240, 0), (255, 90, 0)]

# arm poses: 0 down, 1 both up, 2 out, 3 one up ; legs: 0 together, 1 apart
POSES = [(a, l) for a in range(4) for l in range(2)]


@dataclass
class CharSpec:
    kind: str
    skin: tuple
    hair: tuple
    hair_style: str
    top: tuple
    bottom: tuple
    bottom_style: str
    flag: str | None
    glowstick: tuple | None
    dance: str
    phase: float


def random_spec(rng: np.random.Generator, kind: str, palette: list[tuple], flag_p: float, glow_p: float) -> CharSpec:
    bright = [c for c in palette if sum(c) > 150] or palette
    pick = lambda seq: seq[int(rng.integers(len(seq)))]  # noqa: E731
    flag = pick(list(FLAGS)) if rng.random() < flag_p else None
    return CharSpec(
        kind=kind, skin=pick(SKIN), hair=pick(HAIR), hair_style=pick(HAIR_STYLES),
        top=pick(bright), bottom=pick(palette), bottom_style=pick(BOTTOMS), flag=flag,
        glowstick=pick(NEON) if (flag is None and rng.random() < glow_p) else None,
        dance=pick(["bounce", "bounce", "jump", "sway", "pump", "robot"]),
        phase=float(rng.random()),
    )


def _dark(c, f=0.6):
    return tuple(int(v * f) for v in c)


def _flag(s: pygame.Surface, x: int, y: int, name: str) -> None:
    pygame.draw.line(s, (200, 200, 200), (x, y), (x, y + 12))
    stripes = FLAGS[name]
    h = max(1, 6 // len(stripes)) if len(stripes) > 3 else 2
    for i, c in enumerate(stripes):
        pygame.draw.rect(s, c, (x + 1, y + i * h, 8, h))


def _hair_blocky(s, hx, hy, spec: CharSpec):
    c, st = spec.hair, spec.hair_style
    if st == "bald":
        return
    if st == "cap":
        pygame.draw.rect(s, spec.top, (hx, hy - 1, 8, 3))
        pygame.draw.rect(s, _dark(spec.top), (hx + 6, hy + 1, 4, 1))
        return
    pygame.draw.rect(s, c, (hx, hy, 8, 2))
    if st == "afro":
        pygame.draw.rect(s, c, (hx - 1, hy - 2, 10, 5))
    elif st == "mohawk":
        pygame.draw.rect(s, c, (hx + 3, hy - 3, 2, 4))
    elif st == "bun":
        pygame.draw.rect(s, c, (hx + 2, hy - 3, 4, 3))
    elif st in ("long", "braids"):
        pygame.draw.rect(s, c, (hx - 1, hy, 2, 11 if st == "long" else 13))
        pygame.draw.rect(s, c, (hx + 7, hy, 2, 11 if st == "long" else 13))
    elif st == "bob":
        pygame.draw.rect(s, c, (hx - 1, hy, 2, 7))
        pygame.draw.rect(s, c, (hx + 7, hy, 2, 7))


def _blocky(spec: CharSpec, arms: int, legs: int) -> pygame.Surface:
    s = pygame.Surface((24, 34), pygame.SRCALPHA)
    ox, oy = 8, 8  # origin of the 8-wide body column
    hx, hy = ox, oy
    pygame.draw.rect(s, spec.skin, (hx, hy, 8, 8))
    pygame.draw.rect(s, (20, 20, 30), (hx + 2, hy + 4, 1, 1))
    pygame.draw.rect(s, (20, 20, 30), (hx + 5, hy + 4, 1, 1))
    pygame.draw.rect(s, _dark(spec.skin, 0.8), (hx + 3, hy + 6, 2, 1))
    _hair_blocky(s, hx, hy, spec)
    by = oy + 8
    pygame.draw.rect(s, spec.top, (ox, by, 8, 8))
    pygame.draw.rect(s, _dark(spec.top), (ox, by + 7, 8, 1))
    arm_c = spec.top
    if arms == 0:
        rects = [(ox - 3, by, 3, 8), (ox + 8, by, 3, 8)]
    elif arms == 1:
        rects = [(ox - 3, by - 8, 3, 9), (ox + 8, by - 8, 3, 9)]
    elif arms == 2:
        rects = [(ox - 7, by, 7, 3), (ox + 8, by, 7, 3)]
    else:
        rects = [(ox - 3, by, 3, 8), (ox + 8, by - 8, 3, 9)]
    for r in rects:
        pygame.draw.rect(s, arm_c, r)
        # hands
        hx2 = r[0] + (0 if r[2] <= 3 else (0 if r[0] < ox else r[2] - 2))
        hy2 = r[1] if r[1] < by else r[1] + r[3] - 2
        pygame.draw.rect(s, spec.skin, (hx2, hy2, min(3, r[2]), 2))
    ly = by + 8
    if spec.bottom_style in ("skirt", "dress"):
        top_c = spec.top if spec.bottom_style == "dress" else spec.bottom
        pygame.draw.polygon(s, top_c, [(ox, ly), (ox + 8, ly), (ox + 10, ly + 5), (ox - 2, ly + 5)])
        spread = 2 if legs else 0
        pygame.draw.rect(s, spec.skin, (ox + 1 - spread, ly + 5, 2, 4))
        pygame.draw.rect(s, spec.skin, (ox + 5 + spread, ly + 5, 2, 4))
    else:
        spread = 2 if legs else 0
        leg_h = 5 if spec.bottom_style == "shorts" else 9
        pygame.draw.rect(s, spec.bottom, (ox - spread, ly, 4, leg_h))
        pygame.draw.rect(s, spec.bottom, (ox + 4 + spread, ly, 4, leg_h))
        if leg_h < 9:
            pygame.draw.rect(s, spec.skin, (ox - spread, ly + 5, 4, 4))
            pygame.draw.rect(s, spec.skin, (ox + 4 + spread, ly + 5, 4, 4))
    pygame.draw.rect(s, (30, 30, 30), (ox - (2 if legs else 0), ly + 9, 4, 1))
    pygame.draw.rect(s, (30, 30, 30), (ox + 4 + (2 if legs else 0), ly + 9, 4, 1))
    _accessories(s, spec, arms, left=(ox - 3, by - 9), right=(ox + 9, by - 9))
    return s


def _stick(spec: CharSpec, arms: int, legs: int) -> pygame.Surface:
    s = pygame.Surface((24, 34), pygame.SRCALPHA)
    c = spec.top
    cx, top = 12, 8
    pygame.draw.circle(s, spec.skin, (cx, top + 3), 3)
    if spec.hair_style not in ("bald", "cap"):
        pygame.draw.line(s, spec.hair, (cx - 3, top), (cx + 3, top))
        if spec.hair_style in ("long", "braids", "bob"):
            pygame.draw.line(s, spec.hair, (cx - 3, top), (cx - 3, top + 6))
            pygame.draw.line(s, spec.hair, (cx + 3, top), (cx + 3, top + 6))
        if spec.hair_style == "afro":
            pygame.draw.circle(s, spec.hair, (cx, top + 1), 4, 2)
        if spec.hair_style == "mohawk":
            pygame.draw.line(s, spec.hair, (cx, top - 3), (cx, top))
    pygame.draw.line(s, c, (cx, top + 6), (cx, top + 15))
    sh = top + 8
    ends = {0: [(cx - 4, sh + 6), (cx + 4, sh + 6)], 1: [(cx - 4, sh - 7), (cx + 4, sh - 7)],
            2: [(cx - 7, sh), (cx + 7, sh)], 3: [(cx - 4, sh + 6), (cx + 4, sh - 7)]}[arms]
    for e in ends:
        pygame.draw.line(s, c, (cx, sh), e)
    hip = top + 15
    sp = 5 if legs else 3
    if spec.bottom_style in ("skirt", "dress"):
        pygame.draw.polygon(s, spec.bottom, [(cx, hip - 2), (cx + 4, hip + 3), (cx - 4, hip + 3)])
    pygame.draw.line(s, c, (cx, hip), (cx - sp, hip + 9))
    pygame.draw.line(s, c, (cx, hip), (cx + sp, hip + 9))
    _accessories(s, spec, arms, left=(ends[0][0] - 1, ends[0][1] - 1), right=(ends[1][0], ends[1][1] - 1))
    return s


def _sprite(spec: CharSpec, arms: int, legs: int) -> pygame.Surface:
    """Chunky NES-style: big head, small body."""
    s = pygame.Surface((24, 34), pygame.SRCALPHA)
    ox, oy = 7, 10
    pygame.draw.rect(s, spec.skin, (ox, oy, 10, 9))
    pygame.draw.rect(s, (15, 15, 25), (ox + 2, oy + 4, 2, 2))
    pygame.draw.rect(s, (15, 15, 25), (ox + 6, oy + 4, 2, 2))
    pygame.draw.rect(s, (255, 255, 255), (ox + 2, oy + 4, 1, 1))
    pygame.draw.rect(s, (255, 255, 255), (ox + 6, oy + 4, 1, 1))
    st = spec.hair_style
    if st != "bald":
        hc = spec.top if st == "cap" else spec.hair
        pygame.draw.rect(s, hc, (ox - 1, oy - 2, 12, 4))
        if st in ("long", "braids", "bob"):
            pygame.draw.rect(s, hc, (ox - 1, oy, 2, 10 if st != "bob" else 7))
            pygame.draw.rect(s, hc, (ox + 9, oy, 2, 10 if st != "bob" else 7))
        if st == "afro":
            pygame.draw.rect(s, hc, (ox - 2, oy - 4, 14, 6))
        if st == "mohawk":
            pygame.draw.rect(s, hc, (ox + 4, oy - 5, 2, 4))
        if st == "bun":
            pygame.draw.rect(s, hc, (ox + 3, oy - 5, 4, 3))
    by = oy + 9
    pygame.draw.rect(s, spec.top, (ox + 1, by, 8, 7))
    arm = {0: [(ox - 1, by + 1, 2, 5), (ox + 9, by + 1, 2, 5)],
           1: [(ox - 1, by - 6, 2, 7), (ox + 9, by - 6, 2, 7)],
           2: [(ox - 4, by + 1, 5, 2), (ox + 9, by + 1, 5, 2)],
           3: [(ox - 1, by + 1, 2, 5), (ox + 9, by - 6, 2, 7)]}[arms]
    for r in arm:
        pygame.draw.rect(s, spec.top, r)
    ly = by + 7
    sp = 1 if legs else 0
    if spec.bottom_style in ("skirt", "dress"):
        pygame.draw.rect(s, spec.bottom if spec.bottom_style == "skirt" else spec.top, (ox, ly - 1, 10, 3))
    pygame.draw.rect(s, spec.bottom, (ox + 1 - sp, ly, 3, 4))
    pygame.draw.rect(s, spec.bottom, (ox + 6 + sp, ly, 3, 4))
    pygame.draw.rect(s, (25, 25, 25), (ox - sp, ly + 4, 4, 2))
    pygame.draw.rect(s, (25, 25, 25), (ox + 6 + sp, ly + 4, 4, 2))
    _accessories(s, spec, arms, left=(arm[0][0], arm[0][1] - 1), right=(arm[1][0] + 1, arm[1][1] - 1))
    return s


def _accessories(s, spec: CharSpec, arms: int, left, right) -> None:
    if spec.flag:
        # flag always raised in the right hand
        x, y = right
        _flag(s, min(x, 14), max(0, y - 8), spec.flag)
    elif spec.glowstick and arms in (1, 3):
        x, y = right
        pygame.draw.line(s, spec.glowstick, (x, max(0, y - 4)), (x + 1, y))
        if arms == 1:
            x, y = left
            pygame.draw.line(s, spec.glowstick, (x, max(0, y - 4)), (x - 1, y))


BUILDERS = {"blocky": _blocky, "stick": _stick, "sprite": _sprite}


class Character:
    def __init__(self, spec: CharSpec, scale: int):
        self.spec = spec
        self.scale = scale
        self.frames = {}
        for a, l in POSES:
            if spec.flag and a in (0, 2):
                a2 = 3
            else:
                a2 = a
            surf = BUILDERS[spec.kind](spec, a2, l)
            if scale != 1:
                surf = pygame.transform.scale(surf, (surf.get_width() * scale, surf.get_height() * scale))
            self.frames[(a, l)] = surf

    def frame(self, arms: int, legs: int) -> pygame.Surface:
        return self.frames[(arms, legs)]


def dj_sprite(arms: int, nod: int, skin, hair, top) -> pygame.Surface:
    """DJ with headphones, drawn behind the decks (upper body only)."""
    s = pygame.Surface((30, 26), pygame.SRCALPHA)
    ox, oy = 10, 4 + nod
    pygame.draw.rect(s, skin, (ox, oy, 10, 9))
    pygame.draw.rect(s, hair, (ox - 1, oy - 2, 12, 4))
    pygame.draw.rect(s, (20, 20, 20), (ox - 2, oy + 2, 2, 5))       # headphones
    pygame.draw.rect(s, (20, 20, 20), (ox + 10, oy + 2, 2, 5))
    pygame.draw.rect(s, (20, 20, 20), (ox - 1, oy - 3, 12, 1))
    pygame.draw.rect(s, (0, 0, 0), (ox + 2, oy + 4, 6, 2))            # shades
    by = oy + 9
    pygame.draw.rect(s, top, (ox, by, 10, 10))
    if arms == 0:      # both hands on decks
        pygame.draw.rect(s, top, (ox - 4, by + 2, 4, 3))
        pygame.draw.rect(s, top, (ox + 10, by + 2, 4, 3))
    elif arms == 1:    # one hand up, controlling the floor
        pygame.draw.rect(s, top, (ox - 4, by + 2, 4, 3))
        pygame.draw.rect(s, top, (ox + 10, by - 9, 3, 10))
        pygame.draw.rect(s, skin, (ox + 10, by - 11, 3, 3))
    else:              # both hands up
        pygame.draw.rect(s, top, (ox - 3, by - 9, 3, 10))
        pygame.draw.rect(s, top, (ox + 10, by - 9, 3, 10))
        pygame.draw.rect(s, skin, (ox - 3, by - 11, 3, 3))
        pygame.draw.rect(s, skin, (ox + 10, by - 11, 3, 3))
    return s
