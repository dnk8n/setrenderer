"""Procedural pixel-art cast and props for cropcircle, packed into one texture atlas.

Characters are puppets: a pose is a set of joint angles, so every character (people of every
presentation, anime kids, blocky miners, glowing stick figures, robots, aliens, crewmates...)
can perform every dance move. Emissive pixels (glowsticks, LEDs, visors) carry alpha EMI so the
shader renders them unlit and the bloom picks them up.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pygame

from .font import GLYPHS, glyph_image

CW, CH = 32, 48
EMI = 190
OUTLINE = (24, 14, 32, 255)

SKIN = [(255, 226, 196), (247, 206, 160), (232, 180, 130), (214, 150, 100), (190, 120, 76),
        (160, 98, 60), (126, 76, 44), (96, 58, 34), (70, 42, 26)]
HAIR = [(24, 18, 18), (64, 40, 24), (118, 70, 34), (232, 196, 96), (204, 70, 36), (250, 250, 250),
        (255, 70, 180), (60, 210, 255), (140, 255, 90), (170, 100, 255), (255, 150, 40), (150, 150, 160)]
VIVID = [(255, 50, 90), (255, 140, 0), (255, 220, 0), (60, 220, 90), (0, 200, 255), (60, 90, 255),
         (170, 70, 255), (255, 80, 220), (250, 250, 250), (30, 30, 40), (120, 255, 200), (255, 110, 110),
         (90, 60, 140), (40, 120, 90), (200, 40, 40), (240, 200, 160)]
NEON = [(0, 255, 120), (255, 0, 200), (0, 230, 255), (255, 240, 0), (255, 100, 0), (180, 80, 255)]

FLAGS = {
    "progress": None,
    "rainbow": [(228, 3, 3), (255, 140, 0), (255, 237, 0), (0, 128, 38), (36, 64, 142), (115, 41, 130)],
    "trans": [(91, 206, 250), (245, 169, 184), (255, 255, 255), (245, 169, 184), (91, 206, 250)],
    "nonbinary": [(252, 244, 52), (255, 255, 255), (156, 89, 209), (44, 44, 44)],
    "bi": [(214, 2, 112), (214, 2, 112), (155, 79, 150), (0, 56, 168), (0, 56, 168)],
    "pan": [(255, 33, 140), (255, 216, 0), (33, 177, 255)],
    "lesbian": [(213, 45, 0), (255, 154, 86), (255, 255, 255), (211, 98, 164), (163, 2, 98)],
    "ace": [(0, 0, 0), (163, 163, 163), (255, 255, 255), (128, 0, 128)],
    "genderfluid": [(255, 118, 164), (255, 255, 255), (192, 17, 215), (0, 0, 0), (47, 60, 190)],
    "agender": [(0, 0, 0), (188, 196, 199), (255, 255, 255), (183, 246, 132), (255, 255, 255), (188, 196, 199), (0, 0, 0)],
    "aro": [(61, 165, 66), (167, 211, 121), (255, 255, 255), (169, 169, 169), (0, 0, 0)],
    "intersex": None,
    "smiley": None,
    "spiral": None,
}
PRIDE_FLAGS = ["progress", "rainbow", "trans", "nonbinary", "bi", "pan", "lesbian", "ace", "genderfluid",
               "agender", "aro", "intersex"]

# ---------------------------------------------------------------- poses
# L/R: (upper-arm angle from straight down, elbow bend), screen-left and screen-right arms.
# FL/FR: foot offsets (px) from the standing position. crouch lowers the hips (knees fold out).
POSES: list[tuple[str, dict]] = [
    ("idle", dict(L=(12, -5), R=(12, -5))),
    ("bounce_dn", dict(L=(30, 50), R=(30, 50), crouch=3, spread=1)),
    ("bounce_up", dict(L=(18, 30), R=(18, 30), lift=1)),
    ("hands_up", dict(L=(165, 5), R=(165, 5), mouth="open", eyes="happy")),
    ("hands_wide", dict(L=(140, 0), R=(140, 0), spread=3, mouth="open")),
    ("pump_up", dict(L=(25, 60), R=(172, 0), mouth="open")),
    ("pump_dn", dict(L=(25, 60), R=(110, 70), crouch=1)),
    ("point", dict(L=(20, 40), R=(140, 0))),
    ("arms_out", dict(L=(90, 0), R=(90, 0))),
    ("clap_open", dict(L=(35, -70), R=(35, -70))),
    ("clap", dict(L=(28, -100), R=(28, -100), front=True)),
    ("sway_l", dict(L=(45, 40), R=(10, 10), lean=-2)),
    ("sway_r", dict(L=(10, 10), R=(45, 40), lean=2)),
    ("robot_a", dict(L=(90, 90), R=(90, -90))),
    ("robot_b", dict(L=(90, -90), R=(90, 90))),
    ("floss_a", dict(L=(-25, 0), R=(30, 0), lean=2)),
    ("floss_b", dict(L=(30, 0), R=(-25, 0), lean=-2)),
    ("dab", dict(L=(125, 20), R=(80, -150), head_dy=1, front=True)),
    ("vogue_a", dict(L=(150, -140), R=(150, -140), front=True)),
    ("vogue_b", dict(L=(95, -95), R=(170, -20), lean=1)),
    ("headbang", dict(L=(30, 20), R=(30, 20), head_dy=3, crouch=1)),
    ("kick_l", dict(L=(45, 30), R=(45, 30), FL=(-5, -4), lean=1)),
    ("kick_r", dict(L=(45, 30), R=(45, 30), FR=(5, -4), lean=-1)),
    ("wave", dict(L=(12, 0), R=(150, 25), mouth="smile")),
    ("drink", dict(L=(12, 0), R=(25, -125), hold="cup", front=True)),
    ("phone", dict(L=(95, -75), R=(95, -75), hold="phone", front=True)),
    ("airguitar", dict(L=(55, -75), R=(25, -50), hold="guitar", front=True, crouch=1)),
    ("sprinkler", dict(L=(90, 0), R=(150, -150), front=True)),
    ("mower_a", dict(L=(20, -10), R=(50, 40), crouch=2, lean=-1)),
    ("mower_b", dict(L=(20, -10), R=(130, 30), lean=1)),
    ("ymca_m", dict(L=(150, -160), R=(150, -160), front=True)),
    ("ymca_c", dict(L=(150, 10), R=(60, -60), lean=-1)),
    ("ymca_a", dict(L=(165, -35), R=(165, -35))),
    ("scared", dict(L=(35, -140), R=(35, -140), front=True, mouth="O", eyes="wide")),
    ("laugh", dict(L=(30, -90), R=(30, -90), front=True, crouch=2, mouth="open", eyes="closed", lean=1)),
    ("row_a", dict(L=(80, -40), R=(80, -40), sit=True)),
    ("row_b", dict(L=(40, -100), R=(40, -100), sit=True, lean=-1)),
    ("jump", dict(L=(160, 10), R=(160, 10), FL=(-3, -6), FR=(3, -6), mouth="open", eyes="happy")),
    ("cheer", dict(L=(150, 20), R=(150, 20), mouth="open", eyes="happy", spread=2)),
    ("heart", dict(L=(160, -120), R=(160, -120), front=True, eyes="happy")),
    ("flag", dict(L=(20, 30), R=(175, 0), mouth="smile")),
    ("walk_1", dict(L=(-12, 10), R=(18, 10), FL=(1, -2))),
    ("walk_2", dict(L=(5, 5), R=(5, 5))),
    ("walk_3", dict(L=(18, 10), R=(-12, 10), FR=(-1, -2))),
    ("walk_4", dict(L=(5, 5), R=(5, 5), lift=1)),
    ("sit", dict(L=(30, -30), R=(30, -30), sit=True)),
    ("sax_a", dict(L=(30, -105), R=(40, -85), hold="sax", front=True, lean=-1)),
    ("sax_b", dict(L=(30, -105), R=(40, -85), hold="sax", front=True, lean=1, crouch=2)),
    ("sing", dict(L=(20, 20), R=(25, -135), hold="mic", front=True, mouth="open")),
    ("torch", dict(L=(12, 0), R=(160, 10), hold="phone_up")),
    ("side_1", dict(side=0)), ("side_2", dict(side=1)), ("side_3", dict(side=2)), ("side_4", dict(side=3)),
]
POSE_INDEX = {n: k for k, (n, _) in enumerate(POSES)}

BODY = {  # leg, torso, head w, head h, upper arm, forearm, arm w, leg w, torso w
    "human": dict(leg=14, torso=12, hw=8, hh=9, ua=6, fa=6, aw=2, lw=3, tw=8),
    "anime": dict(leg=10, torso=9, hw=13, hh=13, ua=5, fa=5, aw=2, lw=2, tw=7),
    "blocky": dict(leg=12, torso=12, hw=10, hh=10, ua=6, fa=6, aw=4, lw=4, tw=10),
    "stick": dict(leg=13, torso=12, hw=9, hh=9, ua=6, fa=6, aw=1, lw=1, tw=1),
    "alien": dict(leg=12, torso=12, hw=12, hh=12, ua=6, fa=6, aw=2, lw=2, tw=9),
    "robot": dict(leg=12, torso=12, hw=10, hh=9, ua=6, fa=6, aw=3, lw=3, tw=10),
    "baby": dict(leg=7, torso=8, hw=12, hh=11, ua=4, fa=4, aw=3, lw=3, tw=9),
}


@dataclass
class Spec:
    kind: str
    skin: tuple
    hair: tuple
    hair_style: str
    top: tuple
    top_style: str
    bottom: tuple
    bottom_style: str
    shoes: tuple
    hat: str | None = None
    hat_col: tuple = (200, 40, 40)
    glasses: str | None = None
    face: list = field(default_factory=list)
    glow: tuple | None = None
    eye: tuple = (40, 30, 30)
    wheelchair: bool = False
    paint: str | None = None
    role: str = "dancer"


# ---------------------------------------------------------------- drawing helpers
class Canvas:
    def __init__(self, w=CW, h=CH):
        self.s = pygame.Surface((w, h), pygame.SRCALPHA)
        self.w, self.h = w, h

    def px(self, x, y, c):
        x, y = int(round(x)), int(round(y))
        if 0 <= x < self.w and 0 <= y < self.h:
            self.s.set_at((x, y), c if len(c) == 4 else (*c, 255))

    def rect(self, x, y, w, h, c):
        if w <= 0 or h <= 0:
            return
        pygame.draw.rect(self.s, c if len(c) == 4 else (*c, 255), (int(round(x)), int(round(y)), int(w), int(h)))

    def circle(self, x, y, r, c):
        pygame.draw.circle(self.s, c if len(c) == 4 else (*c, 255), (int(round(x)), int(round(y))), int(r))

    def ellipse(self, x, y, w, h, c):
        pygame.draw.ellipse(self.s, c if len(c) == 4 else (*c, 255), (int(round(x)), int(round(y)), int(w), int(h)))

    def limb(self, p0, p1, w, c):
        n = max(2, int(math.hypot(p1[0] - p0[0], p1[1] - p0[1]) * 2) + 1)
        off = (w - 1) / 2
        for k in range(n):
            t = k / (n - 1)
            x = p0[0] + (p1[0] - p0[0]) * t - off
            y = p0[1] + (p1[1] - p0[1]) * t - off
            self.rect(math.floor(x + 0.5), math.floor(y + 0.5), w, w, c)

    def line(self, p0, p1, c):
        self.limb(p0, p1, 1, c)

    def array(self) -> np.ndarray:
        rgb = pygame.surfarray.array3d(self.s).transpose(1, 0, 2)
        a = pygame.surfarray.array_alpha(self.s).T
        return np.dstack([rgb, a]).astype(np.uint8)


def outline(img: np.ndarray, col=OUTLINE) -> np.ndarray:
    a = img[:, :, 3] > 0
    nb = np.zeros_like(a)
    nb[1:, :] |= a[:-1, :]
    nb[:-1, :] |= a[1:, :]
    nb[:, 1:] |= a[:, :-1]
    nb[:, :-1] |= a[:, 1:]
    edge = nb & ~a
    out = img.copy()
    out[edge] = col
    return out


def dark(c, f=0.7):
    return tuple(int(v * f) for v in c[:3])


def light(c, f=1.25):
    return tuple(min(255, int(v * f + 12)) for v in c[:3])


def emi(c):
    return (*c[:3], EMI)


def _dir(a_deg: float, side: int):
    a = math.radians(a_deg)
    return side * math.sin(a), math.cos(a)


def _ik(hip, foot, l1, l2, side):
    dx, dy = foot[0] - hip[0], foot[1] - hip[1]
    d = math.hypot(dx, dy)
    d = min(d, l1 + l2 - 1e-3)
    if d < 1e-3:
        return ((hip[0] + foot[0]) / 2, (hip[1] + foot[1]) / 2)
    a = (l1 * l1 - l2 * l2 + d * d) / (2 * d)
    h = math.sqrt(max(l1 * l1 - a * a, 0.0))
    mx, my = hip[0] + dx * a / d, hip[1] + dy * a / d
    px, py = -dy / d, dx / d
    k1 = (mx + px * h, my + py * h)
    k2 = (mx - px * h, my - py * h)
    return k1 if (k1[0] - hip[0]) * side > (k2[0] - hip[0]) * side else k2


# ---------------------------------------------------------------- character rendering
def draw_character(spec: Spec, pose_name: str, back: bool = False) -> tuple[np.ndarray, tuple]:
    """Returns (48x32x4 image, (hand_r_x, hand_r_y) in px) for one pose. back=True draws the
    character seen from behind (no face, hair over the head, mirrored)."""
    P = dict(POSES[POSE_INDEX[pose_name]][1])
    if back and "side" not in P and spec.kind not in ("crewmate", "creeper", "stick"):
        P["back"] = True
    if "side" in P:
        return draw_side(spec, P["side"])
    if spec.kind == "crewmate":
        return draw_crewmate(spec, pose_name)
    if spec.kind == "creeper":
        return draw_creeper(spec, pose_name)
    B = BODY.get(spec.kind, BODY["human"])
    cv = Canvas()
    feet_y = 46 - P.get("lift", 0)
    cx = 16
    lean = P.get("lean", 0)
    crouch = P.get("crouch", 0)
    sit = P.get("sit", False) or spec.wheelchair
    if sit:
        hip_y = 46 - 7 if not spec.wheelchair else 46 - 11
    else:
        hip_y = feet_y - B["leg"] + crouch
    hip_x = cx + lean / 2
    sh_y = hip_y - B["torso"]
    sh_x = cx + lean
    head_y0 = sh_y - B["hh"] - (1 if spec.kind in ("human", "alien") else 0) + P.get("head_dy", 0)
    if spec.kind in ("anime", "baby"):
        head_y0 = sh_y - B["hh"] + 2 + P.get("head_dy", 0)
    head_x0 = sh_x - B["hw"] / 2
    stick = spec.kind == "stick"
    limb_c = emi(spec.glow or NEON[0]) if stick else None

    # back hair and wheelchair behind everything
    if spec.wheelchair:
        draw_wheelchair(cv, cx, hip_y)
    if not stick:
        draw_hair_back(cv, spec, head_x0, head_y0, B, sh_y)

    # legs
    spread = P.get("spread", 0)
    leg_c = spec.bottom
    for side, key in ((-1, "FL"), (1, "FR")):
        hx = hip_x + side * max(1, B["tw"] // 2 - B["lw"] // 2 - 0) if not stick else hip_x
        if sit:
            knee = (hip_x + side * 5, hip_y - 4 if not spec.wheelchair else hip_y)
            foot = (hip_x + side * 6, 46 if not spec.wheelchair else 45)
        else:
            fo = P.get(key, (0, 0))
            foot = (hx + side * spread + fo[0], feet_y + fo[1])
            knee = _ik((hx, hip_y), foot, B["leg"] * 0.5, B["leg"] * 0.5, side)
        c_up = limb_c or (spec.skin if spec.bottom_style == "shorts" else leg_c)
        c_low = limb_c or (spec.skin if spec.bottom_style in ("shorts", "skirt") else leg_c)
        if spec.kind == "baby":
            c_up = c_low = spec.skin
        cv.limb((hx, hip_y + 1), knee, B["lw"], c_up)
        cv.limb(knee, foot, B["lw"], c_low)
        if not stick:
            flare = 1 if spec.bottom_style == "flares" else 0
            cv.rect(foot[0] - B["lw"] // 2 - (1 if side < 0 else 0) - flare, foot[1] - 1, B["lw"] + 1 + flare * 2, 2,
                    spec.shoes)

    # torso
    tw = B["tw"]
    if stick:
        cv.limb((sh_x, sh_y + 1), (hip_x, hip_y + 1), 1, limb_c)
    else:
        draw_torso(cv, spec, sh_x, sh_y, hip_x, hip_y, tw, sit)

    arms_front = P.get("front", False)
    hand_r = [sh_x + 8, sh_y + 10]

    def do_arms():
        for side, key in ((-1, "L"), (1, "R")):
            a, b = P.get(key, (10, 0))
            if spec.kind == "blocky" or spec.kind == "robot":
                b = b * 0.5
            sx = sh_x + side * (tw // 2 + (B["aw"] - 1) / 2 + (0 if stick else 0.5))
            if stick:
                sx = sh_x
            sy = sh_y + 1 + (0 if not stick else 1)
            d1 = _dir(a, side)
            el = (sx + d1[0] * B["ua"], sy + d1[1] * B["ua"])
            d2 = _dir(a + b, side)
            hd = (el[0] + d2[0] * B["fa"], el[1] + d2[1] * B["fa"])
            sleeve = spec.top
            if spec.top_style in ("tank", "crop"):
                sleeve = spec.skin
            if spec.top_style == "gown":
                sleeve = spec.skin
            if spec.kind in ("robot",):
                sleeve = spec.top
            up_c = limb_c or (sleeve if spec.top_style != "tank" else spec.skin)
            fo_c = limb_c or (spec.top if spec.top_style in ("hoodie", "jacket", "suit") or spec.kind in ("robot", "alien") else spec.skin)
            cv.limb((sx, sy), el, B["aw"], up_c)
            cv.limb(el, hd, B["aw"], fo_c)
            if not stick:
                hand_c = spec.skin if spec.kind not in ("robot",) else (180, 180, 190)
                cv.rect(hd[0] - B["aw"] / 2, hd[1] - B["aw"] / 2, B["aw"] + (1 if B["aw"] < 3 else 0), B["aw"] + (1 if B["aw"] < 3 else 0), hand_c)
            if side > 0:
                hand_r[0], hand_r[1] = hd
            hold = P.get("hold")
            if spec.glow is not None and hold is None and not stick and side < 0 or (spec.glow is not None and not stick and hold is None and side > 0 and pose_name != "flag"):
                gx, gy = d2
                cv.limb((hd[0], hd[1]), (hd[0] + gx * 4, hd[1] + gy * 4), 1, emi(spec.glow))
            if hold and side > 0:
                draw_held(cv, hold, hd, el)
    if P.get("back"):
        do_arms()
        draw_head_back(cv, spec, head_x0, head_y0, B, sh_y)
        img = outline(cv.array())[:, ::-1].copy()
        return img, (CW - 1 - hand_r[0], hand_r[1])
    if not arms_front:
        do_arms()
    draw_head(cv, spec, head_x0, head_y0, B, P)
    if arms_front:
        do_arms()
    img = cv.array()
    if not stick:
        img = outline(img)
    return img, (hand_r[0], hand_r[1])


def draw_head_back(cv, spec, hx, hy, B, sh_y):
    hw, hh = B["hw"], B["hh"]
    k = spec.kind
    if k == "alien":
        cv.ellipse(hx, hy, hw, hh, (160, 170, 160))
        cv.rect(hx - 1, hy - 1, hw + 2, 2, (90, 70, 40))
        cv.rect(hx + 1, hy - 4, hw - 2, 3, (110, 86, 50))
        return
    if k == "robot":
        cv.rect(hx, hy, hw, hh, (160, 165, 180))
        cv.rect(hx + 2, hy + 2, hw - 4, 2, (90, 90, 100))
        cv.line((hx + hw / 2, hy - 1), (hx + hw / 2, hy - 4), (150, 150, 160))
        cv.px(hx + hw / 2, hy - 5, emi((255, 40, 40)))
        return
    skin = spec.skin
    if k in ("anime", "baby"):
        cv.ellipse(hx, hy, hw, hh, skin)
    else:
        cv.rect(hx, hy, hw, hh, skin)
    c, st = spec.hair, spec.hair_style
    if st != "bald" and k != "baby":
        if st in ("long", "braids", "dreads", "bob", "pigtails"):
            cv.rect(hx - 1, hy - 1, hw + 2, hh + (8 if st == "long" else 2), c)
        elif st == "afro":
            cv.circle(hx + hw / 2, hy + hh / 2 - 1, hw * 0.8, c)
        elif st == "mohawk":
            cv.rect(hx + hw // 2 - 1, hy - 4, 3, hh + 2, c)
        else:
            cv.rect(hx - (1 if k == "anime" else 0), hy - 1, hw + (2 if k == "anime" else 0), hh - 2, c)
        if st == "bun":
            cv.circle(hx + hw / 2, hy - 1, 2, dark(c, 0.85))
        if st == "pigtails":
            cv.ellipse(hx - 6, hy + 1, 7, hh + 6, c)
            cv.ellipse(hx + hw - 1, hy + 1, 7, hh + 6, c)
        if st == "braids":
            cv.rect(hx + hw // 2 - 1, hy + hh, 2, 8, c)
    elif k == "baby":
        cv.px(hx + hw // 2, hy - 1, c)
    if spec.hat:
        draw_hat(cv, spec, hx, hy, B)


def draw_wheelchair(cv, cx, hip_y):
    rim = (150, 150, 160)
    cv.circle(cx - 6, hip_y + 4, 6, (30, 30, 34))
    cv.circle(cx - 6, hip_y + 4, 5, rim)
    cv.circle(cx - 6, hip_y + 4, 4, (30, 30, 34))
    cv.circle(cx + 6, hip_y + 4, 6, (30, 30, 34))
    cv.circle(cx + 6, hip_y + 4, 5, rim)
    cv.circle(cx + 6, hip_y + 4, 4, (30, 30, 34))
    cv.rect(cx - 7, hip_y, 14, 2, (60, 60, 70))
    cv.rect(cx - 6, hip_y - 9, 12, 2, (60, 60, 70))


def draw_held(cv, hold, hd, el):
    x, y = hd
    if hold == "cup":
        cv.rect(x - 1, y - 3, 3, 4, (220, 30, 40))
        cv.rect(x - 1, y - 3, 3, 1, (250, 250, 250))
    elif hold == "phone":
        cv.rect(x - 2, y - 5, 4, 5, (20, 20, 24))
        cv.rect(x - 1, y - 4, 2, 3, emi((150, 220, 255)))
    elif hold == "sax":
        cv.line((x - 1, y - 6), (x + 1, y + 3), (230, 180, 40))
        cv.line((x, y - 6), (x + 2, y + 3), (230, 180, 40))
        cv.rect(x + 1, y + 2, 4, 3, (250, 200, 60))
    elif hold == "mic":
        cv.rect(x - 1, y - 3, 2, 3, (40, 40, 40))
        cv.rect(x - 1, y - 4, 2, 1, (180, 180, 190))
    elif hold == "phone_up":
        cv.rect(x - 1, y - 4, 3, 4, (20, 20, 24))
        cv.rect(x - 1, y - 4, 3, 1, emi((255, 255, 230)))
    elif hold == "guitar":
        cv.ellipse(x - 4, y - 1, 7, 6, (190, 40, 30))
        cv.line((x + 2, y + 1), (x + 9, y - 5), (90, 60, 30))


def draw_torso(cv, spec, sh_x, sh_y, hip_x, hip_y, tw, sit):
    c = spec.top
    x0 = sh_x - tw / 2
    h = hip_y - sh_y + 1
    st = spec.top_style
    if spec.kind == "baby":
        cv.rect(x0, sh_y + 1, tw, h - 3, spec.skin)
        cv.rect(x0, hip_y - 3, tw, 5, (245, 245, 245))   # nappy
        cv.rect(sh_x - 1, hip_y - 1, 2, 2, (210, 210, 220))
        return
    if spec.kind == "alien":
        # trench coat down to the knees
        cv.rect(x0 - 1, sh_y + 1, tw + 2, h + 6, (120, 96, 60))
        cv.line((sh_x, sh_y + 2), (sh_x, hip_y + 6), (80, 62, 40))
        cv.rect(x0 - 1, hip_y - 2, tw + 2, 1, (70, 54, 34))
        return
    if spec.kind == "robot":
        cv.rect(x0, sh_y + 1, tw, h, (150, 155, 170))
        cv.rect(x0, sh_y + 1, 1, h, (110, 115, 130))
        for k in range(3):
            cv.px(sh_x - 2 + k * 2, sh_y + 4, emi(NEON[(k * 2) % len(NEON)]))
        cv.rect(sh_x - 2, sh_y + 7, 4, 3, (60, 60, 70))
        return
    if st in ("dress", "gown"):
        L = h + (7 if st == "dress" else 14)
        for k in range(L):
            w = tw + int(k * (0.45 if st == "dress" else 0.5))
            cv.rect(sh_x - w / 2 + (hip_x - sh_x) * (k / max(L, 1)), sh_y + 1 + k, w, 1, c if k % 6 else dark(c, 0.85))
        if st == "gown":
            for k in range(6):
                cv.px(sh_x - 3 + (k * 5) % 7, sh_y + 4 + k * 3, emi(light(c)))
        return
    cv.rect(x0, sh_y + 1, tw, h, c)
    cv.rect(x0, sh_y + 1, 1, h, dark(c, 0.8))
    if st == "crop":
        cv.rect(x0, sh_y + 1 + h - 4, tw, 3, spec.skin)
    if st == "tank":
        cv.rect(x0, sh_y + 1, 2, 2, spec.skin)
        cv.rect(x0 + tw - 2, sh_y + 1, 2, 2, spec.skin)
    if st == "hoodie":
        cv.rect(sh_x - 2, sh_y + h - 5, 4, 3, dark(c, 0.8))
        cv.px(sh_x - 1, sh_y + 2, (230, 230, 230))
        cv.px(sh_x + 1, sh_y + 2, (230, 230, 230))
    if st == "overalls":
        cv.rect(x0 + 1, sh_y + 4, tw - 2, h - 3, (60, 90, 160))
        cv.rect(x0 + 1, sh_y + 1, 1, 3, (60, 90, 160))
        cv.rect(x0 + tw - 2, sh_y + 1, 1, 3, (60, 90, 160))
    if st == "jacket":
        cv.rect(sh_x - 1, sh_y + 1, 2, h, (240, 240, 240))
    if st == "suit":
        cv.rect(sh_x - 1, sh_y + 1, 2, h - 2, (240, 240, 240))
        cv.rect(sh_x - 0, sh_y + 2, 1, h - 4, (200, 20, 40))
    if st == "stripes":
        pal = FLAGS["rainbow"]
        for k in range(h):
            cv.rect(x0 + 1, sh_y + 1 + k, tw - 1, 1, pal[(k * len(pal)) // max(h, 1)])
    if st == "smiley":
        cv.circle(sh_x, sh_y + h // 2, 3, (255, 220, 0))
        cv.px(sh_x - 1, sh_y + h // 2 - 1, (20, 20, 20))
        cv.px(sh_x + 1, sh_y + h // 2 - 1, (20, 20, 20))
        cv.line((sh_x - 1, sh_y + h // 2 + 1), (sh_x + 1, sh_y + h // 2 + 1), (20, 20, 20))
    if st == "sequins":
        for k in range(8):
            cv.px(x0 + 1 + (k * 3) % (tw - 1), sh_y + 2 + (k * 5) % max(h - 2, 1), emi(light(c, 1.5)))
    if spec.glow is not None and st in ("tee", "tank"):
        cv.rect(x0, hip_y - 1, tw, 1, emi(spec.glow))   # LED belt
    # bottoms: skirt over the hips
    if spec.bottom_style == "skirt":
        for k in range(6):
            w = tw + 1 + k
            cv.rect(hip_x - w / 2, hip_y + k - 1, w, 1, spec.bottom)
    elif not sit:
        cv.rect(hip_x - tw / 2, hip_y - 1, tw, 3, spec.bottom)


def draw_hair_back(cv, spec, hx, hy, B, sh_y):
    c, st = spec.hair, spec.hair_style
    hw, hh = B["hw"], B["hh"]
    if spec.kind in ("robot", "alien", "baby"):
        return
    if st == "long":
        cv.rect(hx - 1, hy + 1, hw + 2, (sh_y - hy) + 6, c)
    elif st == "afro":
        cv.circle(hx + hw / 2, hy + hh / 2 - 1, hw * 0.8, c)
    elif st == "braids":
        cv.rect(hx - 1, hy + 2, 2, hh + 8, c)
        cv.rect(hx + hw - 1, hy + 2, 2, hh + 8, c)
    elif st == "pigtails":
        cv.ellipse(hx - 6, hy + 1, 7, hh + 6, c)
        cv.ellipse(hx + hw - 1, hy + 1, 7, hh + 6, c)
    elif st == "dreads":
        for k in range(5):
            cv.rect(hx - 1 + k * (hw + 1) // 4, hy + 2, 1, hh + 7 + (k % 2) * 2, c)
    elif st == "bob":
        cv.rect(hx - 1, hy, hw + 2, hh + 1, c)


def draw_head(cv, spec, hx, hy, B, P):
    hw, hh = B["hw"], B["hh"]
    k = spec.kind
    eyes = P.get("eyes", "open")
    mouth = P.get("mouth", "line")
    if k == "stick":
        c = emi(spec.glow or NEON[0])
        cv.circle(hx + hw / 2, hy + hh / 2, 4, c)
        cv.circle(hx + hw / 2, hy + hh / 2, 3, (0, 0, 0, 0))
        return
    if k == "alien":
        cv.ellipse(hx, hy, hw, hh, (170, 180, 170))
        cv.rect(hx + 2, hy + hh - 3, hw - 4, 3, (170, 180, 170))
        cv.ellipse(hx + 1, hy + 4, 4, 3, (10, 10, 14))
        cv.ellipse(hx + hw - 5, hy + 4, 4, 3, (10, 10, 14))
        cv.px(hx + 2, hy + 4, emi((120, 255, 160)))
        cv.px(hx + hw - 4, hy + 4, emi((120, 255, 160)))
        # trilby: the classic disguise
        cv.rect(hx - 1, hy - 1, hw + 2, 2, (90, 70, 40))
        cv.rect(hx + 1, hy - 4, hw - 2, 3, (110, 86, 50))
        return
    if k == "robot":
        cv.rect(hx, hy, hw, hh, (170, 175, 190))
        cv.rect(hx, hy, hw, 1, (210, 215, 230))
        cv.rect(hx + 1, hy + 3, hw - 2, 3, (20, 20, 30))
        glow = spec.glow or NEON[2]
        t = (POSE_INDEX.get("idle", 0))
        for x in range(hw - 2):
            cv.px(hx + 1 + x, hy + 4, emi(glow) if (x + t) % 3 else emi(light(glow)))
        cv.line((hx + hw / 2, hy - 1), (hx + hw / 2, hy - 4), (150, 150, 160))
        cv.px(hx + hw / 2, hy - 5, emi((255, 40, 40)))
        return
    skin = spec.skin
    if k == "blocky":
        cv.rect(hx, hy, hw, hh, skin)
    elif k == "anime" or k == "baby":
        cv.ellipse(hx, hy, hw, hh, skin)
        cv.rect(hx + 1, hy + hh // 2, hw - 2, hh // 2 - 1, skin)
    else:
        cv.rect(hx, hy + 1, hw, hh - 1, skin)
        cv.rect(hx + 1, hy, hw - 2, 1, skin)
    # face
    cx = hx + hw / 2
    if k in ("anime", "baby"):
        ey = hy + hh // 2
        for s in (-1, 1):
            ex = cx + s * (hw * 0.22) - 1
            if eyes == "closed" or eyes == "happy":
                cv.line((ex - 1, ey + 1), (ex + 1, ey), (40, 30, 40))
                cv.line((ex + 1, ey), (ex + 2, ey + 1), (40, 30, 40))
            else:
                cv.rect(ex - 0.5, ey - 1, 3, 4 if eyes != "wide" else 5, (30, 24, 40))
                cv.rect(ex, ey, 1, 2, spec.eye)
                cv.px(ex + 1, ey - 1, (255, 255, 255))
        cv.px(cx - hw * 0.35, ey + 3, (255, 140, 150))
        cv.px(cx + hw * 0.35, ey + 3, (255, 140, 150))
        my = ey + 4
    else:
        ey = hy + hh // 2 - (0 if k != "blocky" else 0)
        for s in (-1, 1):
            ex = cx + s * 2 - (1 if s > 0 else 0) + (0 if s < 0 else 1)
            if eyes in ("closed", "happy"):
                cv.px(ex - 1, ey, (40, 28, 30))
                cv.px(ex, ey - 1 if eyes == "happy" else ey, (40, 28, 30))
            else:
                cv.px(ex, ey, (30, 22, 26))
                if eyes == "wide":
                    cv.px(ex, ey - 1, (250, 250, 250))
        my = ey + 3
    mc = (120, 40, 50) if "lipstick" not in spec.face else (220, 20, 70)
    if mouth == "open":
        cv.rect(cx - 1, my - 1, 2, 2, (70, 20, 30))
    elif mouth == "O":
        cv.rect(cx - 1, my - 1, 2, 3, (40, 10, 20))
    elif mouth == "smile":
        cv.px(cx - 2, my - 1, mc)
        cv.line((cx - 1, my), (cx + 1, my), mc)
        cv.px(cx + 1, my - 1, mc)
    else:
        cv.line((cx - 1, my), (cx, my), mc)
    if "beard" in spec.face:
        cv.rect(hx, my - 1, hw, hh - (my - hy) + 1, spec.hair)
        cv.rect(cx - 1, my, 2, 1, (70, 20, 30) if mouth in ("open", "O") else mc)
    if "mustache" in spec.face:
        cv.line((cx - 2, my - 1), (cx + 1, my - 1), spec.hair)
    if "blush" in spec.face:
        cv.px(hx + 1, my - 1, (255, 120, 140))
        cv.px(hx + hw - 2, my - 1, (255, 120, 140))
    if spec.paint:
        pal = FLAGS.get(spec.paint) or FLAGS["rainbow"]
        for q, col in enumerate(pal[:4]):
            cv.px(hx + hw - 2, hy + hh // 2 + q - 1, col)
    draw_hair_front(cv, spec, hx, hy, B)
    if spec.glasses == "shades":
        cv.rect(hx + 1, ey - 1, hw - 2, 2, (10, 10, 14))
        cv.px(hx + 2, ey - 1, (90, 90, 120))
    elif spec.glasses == "heart":
        for s in (-1, 1):
            cv.rect(cx + s * 2 - 1 - (1 if s > 0 else 0) + (0 if s < 0 else 1), ey - 1, 2, 2, (255, 60, 150))
    elif spec.glasses == "visor":
        cv.rect(hx, ey - 1, hw, 2, emi(spec.glow or NEON[1]))
    draw_hat(cv, spec, hx, hy, B)


def draw_hair_front(cv, spec, hx, hy, B):
    c, st = spec.hair, spec.hair_style
    hw, hh = B["hw"], B["hh"]
    if spec.kind in ("baby",):
        cv.px(hx + hw // 2, hy - 1, c)
        cv.px(hx + hw // 2 + 1, hy - 2, c)
        return
    if st == "bald" or spec.kind in ("robot", "alien"):
        return
    if st == "mohawk":
        cv.rect(hx + hw // 2 - 1, hy - 4, 3, 5, c)
        return
    if st == "spiky":
        for k in range(5):
            x = hx - 1 + k * (hw + 2) / 4
            cv.line((x, hy + 2), (x + (k - 2) * 0.8, hy - 4), c)
            cv.line((x + 1, hy + 2), (x + (k - 2) * 0.8 + 1, hy - 3), c)
        cv.rect(hx - 1, hy - 1, hw + 2, 3, c)
        return
    top = 2 if spec.kind != "anime" else 4
    cv.rect(hx - (1 if st in ("afro", "long", "bob") else 0), hy - (1 if st == "afro" else 0), hw + (2 if st in ("afro", "long", "bob") else 0), top, c)
    if spec.kind == "anime":
        # fringe
        for k in range(0, hw, 3):
            cv.rect(hx + k, hy + top, 2, 2, c)
    if st == "bun":
        cv.circle(hx + hw / 2, hy - 2, 2, c)
    if st == "undercut":
        cv.rect(hx, hy - 1, hw - 2, 2, c)
        cv.rect(hx + hw - 3, hy + 2, 2, 3, c)
    if st in ("short", "undercut"):
        cv.rect(hx, hy + 2, 1, 2, c)
        cv.rect(hx + hw - 1, hy + 2, 1, 2, c)
    if st == "pigtails":
        cv.rect(hx - 1, hy + 1, 2, 2, (255, 60, 120))
        cv.rect(hx + hw - 1, hy + 1, 2, 2, (255, 60, 120))


def draw_hat(cv, spec, hx, hy, B):
    hw = B["hw"]
    h = spec.hat
    c = spec.hat_col
    if not h:
        return
    if h == "cap":
        cv.rect(hx, hy - 1, hw, 3, c)
        cv.rect(hx + hw - 2, hy + 1, 4, 1, dark(c))
    elif h == "bucket":
        cv.rect(hx, hy - 2, hw, 3, c)
        cv.rect(hx - 1, hy + 1, hw + 2, 1, dark(c))
    elif h == "beanie":
        cv.rect(hx, hy - 2, hw, 3, c)
        cv.px(hx + hw / 2, hy - 3, light(c))
    elif h == "straw":
        cv.rect(hx - 3, hy, hw + 6, 1, (230, 200, 110))
        cv.rect(hx, hy - 3, hw, 3, (210, 180, 90))
        cv.rect(hx, hy - 1, hw, 1, (200, 40, 40))
    elif h == "flowers":
        for k in range(5):
            cv.px(hx + k * (hw - 1) / 4, hy - 1, [(255, 90, 150), (255, 230, 60), (120, 200, 255), (255, 255, 255), (255, 140, 0)][k])
    elif h == "headphones":
        cv.rect(hx - 1, hy - 1, hw + 2, 1, (30, 30, 30))
        cv.rect(hx - 2, hy + 2, 2, 4, (30, 30, 30))
        cv.rect(hx + hw, hy + 2, 2, 4, (30, 30, 30))
        cv.px(hx - 2, hy + 3, emi((255, 0, 120)))
    elif h in ("cat", "fox", "bunny"):
        col = {"cat": (40, 40, 40), "fox": (230, 120, 40), "bunny": (250, 250, 250)}[h]
        hgt = 5 if h == "bunny" else 3
        for s in (0, hw - 2):
            cv.rect(hx + s, hy - hgt, 2, hgt, col)
            cv.px(hx + s + (1 if s == 0 else 0), hy - hgt + 1, (255, 160, 180))
    elif h == "horns":
        cv.px(hx + 1, hy - 1, emi((255, 30, 30)))
        cv.px(hx, hy - 2, emi((255, 30, 30)))
        cv.px(hx + hw - 2, hy - 1, emi((255, 30, 30)))
        cv.px(hx + hw - 1, hy - 2, emi((255, 30, 30)))
    elif h == "halo":
        cv.ellipse(hx, hy - 4, hw, 3, emi((255, 240, 150)))
        cv.ellipse(hx + 2, hy - 3, hw - 4, 1, (0, 0, 0, 0))
    elif h == "bandana":
        cv.rect(hx, hy, hw, 2, c)
        cv.px(hx - 1, hy + 2, c)


def draw_side(spec: Spec, frame: int):
    """Profile walk cycle, facing right (flip for left)."""
    B = BODY.get(spec.kind, BODY["human"])
    if spec.kind in ("crewmate", "creeper"):
        return (draw_crewmate if spec.kind == "crewmate" else draw_creeper)(spec, f"walk_{frame + 1}")
    cv = Canvas()
    stick = spec.kind == "stick"
    lc = emi(spec.glow or NEON[0]) if stick else None
    ang = [(28, -22), (6, 0), (-22, 28), (0, 6)][frame]
    bob = 1 if frame in (1, 3) else 0
    hip = (15, 46 - B["leg"] - bob + 1)
    if spec.wheelchair:
        draw_wheelchair(cv, 16, 46 - 11)
        hip = (14, 46 - 11)
    for k, a in enumerate(ang):
        if spec.wheelchair:
            knee = (hip[0] + 5, hip[1])
            foot = (hip[0] + 5, 45)
        else:
            d = _dir(a, 1)
            knee = (hip[0] + d[0] * B["leg"] / 2, hip[1] + d[1] * B["leg"] / 2)
            d2 = _dir(a - 15 if a > 0 else a + 10, 1)
            foot = (knee[0] + d2[0] * B["leg"] / 2, knee[1] + d2[1] * B["leg"] / 2)
        c = lc or (dark(spec.bottom, 0.8) if k == 0 else spec.bottom)
        if spec.kind == "baby" or spec.bottom_style == "shorts":
            c = lc or spec.skin
        cv.limb(hip, knee, B["lw"], c)
        cv.limb(knee, foot, B["lw"], c if spec.bottom_style not in ("skirt",) else (lc or spec.skin))
        if not stick:
            cv.rect(foot[0] - 1, foot[1] - 1, B["lw"] + 2, 2, spec.shoes)
    tw = max(4, B["tw"] - 3)
    sh = (hip[0] + 1, hip[1] - B["torso"])
    if stick:
        cv.limb(sh, hip, 1, lc)
    else:
        top = spec.top if spec.kind not in ("robot",) else (150, 155, 170)
        if spec.kind == "alien":
            top = (120, 96, 60)
        L = B["torso"] + (6 if spec.top_style in ("dress",) or spec.kind == "alien" else 0) + (12 if spec.top_style == "gown" else 0)
        cv.rect(sh[0] - tw / 2, sh[1] + 1, tw, L, top)
        if spec.kind == "baby":
            cv.rect(sh[0] - tw / 2, sh[1] + 1, tw, B["torso"], spec.skin)
            cv.rect(sh[0] - tw / 2, hip[1] - 3, tw, 4, (245, 245, 245))
    sw = [(-25, 20), (0, 10), (25, 30), (0, 10)][frame]
    d = _dir(sw[0], 1)
    el = (sh[0] + d[0] * B["ua"], sh[1] + 2 + d[1] * B["ua"])
    d2 = _dir(sw[0] + sw[1], 1)
    hd = (el[0] + d2[0] * B["fa"], el[1] + d2[1] * B["fa"])
    arm_c = lc or (spec.top if spec.top_style in ("hoodie", "jacket", "suit") else spec.skin)
    cv.limb((sh[0], sh[1] + 2), el, B["aw"], lc or (spec.top if spec.top_style not in ("tank", "crop", "gown") else spec.skin))
    cv.limb(el, hd, B["aw"], arm_c)
    if spec.glow is not None and not stick:
        cv.limb(hd, (hd[0] + d2[0] * 4, hd[1] + d2[1] * 4), 1, emi(spec.glow))
    # head in profile
    hw, hh = max(7, B["hw"] - 1), B["hh"]
    hx, hy = sh[0] - hw / 2 + 1, sh[1] - hh + (2 if spec.kind in ("anime", "baby") else -1)
    if stick:
        cv.circle(hx + hw / 2, hy + hh / 2, 4, lc)
        cv.circle(hx + hw / 2, hy + hh / 2, 3, (0, 0, 0, 0))
    elif spec.kind == "robot":
        cv.rect(hx, hy, hw, hh, (170, 175, 190))
        cv.rect(hx + hw - 3, hy + 3, 3, 3, emi(spec.glow or NEON[2]))
    elif spec.kind == "alien":
        cv.ellipse(hx, hy, hw + 1, hh, (170, 180, 170))
        cv.ellipse(hx + hw - 3, hy + 4, 3, 3, (10, 10, 14))
        cv.rect(hx - 1, hy - 1, hw + 3, 2, (90, 70, 40))
        cv.rect(hx + 1, hy - 4, hw - 1, 3, (110, 86, 50))
    else:
        if spec.hair_style in ("long", "braids", "dreads", "pigtails"):
            cv.rect(hx - 1, hy + 1, 4, hh + 5, spec.hair)
        if spec.kind in ("anime", "baby"):
            cv.ellipse(hx, hy, hw + 1, hh, spec.skin)
        else:
            cv.rect(hx, hy, hw, hh, spec.skin)
        cv.px(hx + hw, hy + hh // 2 + 1, spec.skin)   # nose
        ex = hx + hw - 2
        ey = hy + hh // 2
        if spec.kind == "anime":
            cv.rect(ex - 1, ey - 1, 2, 3, (30, 24, 40))
            cv.px(ex - 1, ey - 1, (255, 255, 255))
        else:
            cv.px(ex, ey, (30, 22, 26))
        if spec.hair_style != "bald" and spec.kind != "baby":
            cv.rect(hx - 1, hy - 1, hw + 1, 3 if spec.kind != "anime" else 4, spec.hair)
            cv.rect(hx - 1, hy - 1, 3, hh // 2 + 1, spec.hair)
            if spec.hair_style == "mohawk":
                cv.rect(hx + 1, hy - 4, hw - 2, 3, spec.hair)
            if spec.hair_style == "afro":
                cv.circle(hx + hw / 2 - 1, hy + 2, hw * 0.7, spec.hair)
        if "beard" in spec.face:
            cv.rect(hx + 2, hy + hh - 3, hw - 2, 3, spec.hair)
        if spec.hat in ("cap", "bucket", "beanie", "straw", "bandana"):
            cv.rect(hx - 1, hy - 2, hw + 2, 3, spec.hat_col if spec.hat != "straw" else (210, 180, 90))
            if spec.hat in ("cap",):
                cv.rect(hx + hw, hy, 3, 1, dark(spec.hat_col))
            if spec.hat == "straw":
                cv.rect(hx - 3, hy, hw + 6, 1, (230, 200, 110))
        if spec.hat == "headphones":
            cv.rect(hx + 1, hy + 2, 3, 4, (30, 30, 30))
        if spec.glasses == "shades":
            cv.rect(hx + hw - 4, ey - 1, 4, 2, (10, 10, 14))
    img = cv.array()
    if not stick:
        img = outline(img)
    return img, (hd[0], hd[1])


def draw_crewmate(spec: Spec, pose_name: str):
    cv = Canvas()
    c = spec.top
    squash = {"bounce_dn": 2, "headbang": 1, "row_a": 3, "row_b": 3, "sit": 3}.get(pose_name, 0)
    jump = {"jump": 5, "hands_up": 2, "cheer": 2, "bounce_up": 1}.get(pose_name, 0)
    lean = {"sway_l": -2, "sway_r": 2, "floss_a": 1, "floss_b": -1, "laugh": 1}.get(pose_name, 0)
    walk = pose_name.startswith("walk") or pose_name.startswith("side")
    bw, bh = 14 + squash, 17 - squash
    x0, y0 = 16 - bw / 2, 46 - 4 - bh - jump
    cv.rect(x0 - 3 + lean, y0 + 5, 4, 9, dark(c, 0.75))     # backpack
    cv.ellipse(x0 + lean, y0, bw, bh + 3, c)
    cv.rect(x0, y0 + bh / 2, bw, bh / 2, c)
    cv.rect(x0, y0 + bh / 2, 2, bh / 2, dark(c, 0.8))
    vx = x0 + bw / 2 - 1 + lean
    cv.ellipse(vx - 1, y0 + 3, 8, 5, (140, 200, 230))
    cv.rect(vx + 2, y0 + 4, 3, 1, (240, 250, 255))
    lf = [(0, 0), (-1, 1)] if not walk else [(int(2 * math.sin(len(pose_name))), 0), (0, 0)]
    for s, (dx, dy) in zip((-1, 1), lf):
        cv.rect(16 + s * 4 - 2 + dx, 46 - 4 - jump - dy, 4, 4, c)
    if pose_name in ("scared",):
        cv.rect(vx + 1, y0 + 4, 2, 2, (20, 20, 20))
    img = outline(cv.array())
    return img, (16 + 7, y0 + 10)


def draw_creeper(spec: Spec, pose_name: str):
    cv = Canvas()
    bob = {"bounce_dn": 1, "headbang": 2, "jump": -4, "cheer": -2, "hands_up": -2}.get(pose_name, 0)
    rng = np.random.default_rng(7)
    greens = [(70, 160, 60), (90, 190, 80), (50, 120, 45), (120, 210, 110)]
    for y in range(12, 46 - 4):
        for x in range(12, 20):
            cv.px(x, y + bob, greens[int(rng.integers(4))])
    for y in range(4, 12):
        for x in range(11, 21):
            cv.px(x, y + bob, greens[int(rng.integers(4))])
    for (x, y) in [(12, 6), (13, 6), (17, 6), (18, 6), (12, 7), (13, 7), (17, 7), (18, 7), (15, 8), (14, 9),
                   (15, 9), (16, 9), (14, 10), (16, 10)]:
        cv.px(x + 0.4, y + bob, (16, 22, 16))
    step = 1 if pose_name in ("walk_1", "walk_3", "side_1", "side_3", "kick_l") else 0
    for k, x in enumerate((11, 14, 17, 19)):
        cv.rect(x - (step if k % 2 else 0), 42, 3, 4, greens[k % 4])
    return outline(cv.array()), (20, 20)


# ---------------------------------------------------------------- specs
def random_spec(rng: np.random.Generator, kind: str) -> Spec:
    pick = lambda seq: seq[int(rng.integers(len(seq)))]  # noqa: E731
    top_style = pick(["tee", "tee", "tank", "hoodie", "crop", "dress", "gown", "jacket", "stripes", "smiley",
                      "sequins", "overalls", "suit", "tee"])
    bottom_style = pick(["pants", "pants", "shorts", "skirt", "flares", "pants"])
    if top_style in ("dress", "gown"):
        bottom_style = "skirt"
    hair_style = pick(["short", "long", "afro", "mohawk", "bun", "bald", "bob", "braids", "dreads", "undercut",
                       "pigtails", "spiky"])
    if kind == "anime":
        hair_style = pick(["spiky", "pigtails", "long", "bob", "short", "spiky", "pigtails"])
    face = []
    if rng.random() < 0.18 and kind in ("human", "blocky"):
        face.append("beard")
    elif rng.random() < 0.08:
        face.append("mustache")
    if rng.random() < 0.3:
        face.append("lipstick")
    if kind == "anime" or rng.random() < 0.15:
        face.append("blush")
    hat = pick([None, None, None, "cap", "bucket", "beanie", "flowers", "cat", "fox", "bunny", "horns", "halo",
                "bandana", None, "flowers"])
    glasses = pick([None, None, None, None, "shades", "heart", "visor", None])
    glow = pick(NEON) if rng.random() < 0.35 or kind in ("stick", "robot") else None
    hair = pick(HAIR)
    if rng.random() < 0.15:
        hair = (255, 140, 200) if rng.random() < 0.5 else (120, 200, 255)
    return Spec(kind=kind, skin=pick(SKIN), hair=hair, hair_style=hair_style, top=pick(VIVID), top_style=top_style,
                bottom=pick(VIVID + [(40, 50, 90), (30, 30, 36), (90, 70, 50)]), bottom_style=bottom_style,
                shoes=pick([(30, 30, 30), (240, 240, 240), (200, 40, 40), (60, 60, 200), (250, 210, 0)]),
                hat=hat, hat_col=pick(VIVID), glasses=glasses, face=face, glow=glow, eye=pick(VIVID),
                wheelchair=bool(kind in ("human", "anime") and rng.random() < 0.06),
                paint=pick(PRIDE_FLAGS) if rng.random() < 0.15 else None)


KIND_WEIGHTS = {"human": 0.38, "anime": 0.21, "blocky": 0.13, "stick": 0.06, "robot": 0.05, "alien": 0.03,
                "crewmate": 0.07, "creeper": 0.02, "baby": 0.0}


def make_cast(rng: np.random.Generator, n: int, weights: dict | None = None) -> list[Spec]:
    w = dict(KIND_WEIGHTS)
    w.update(weights or {})
    kinds = [k for k in w if w[k] > 0]
    p = np.array([w[k] for k in kinds], float)
    p /= p.sum()
    cast = []
    for i in range(n):
        k = kinds[int(rng.choice(len(kinds), p=p))]
        s = random_spec(rng, k)
        if k == "crewmate":
            s.top = [(197, 17, 17), (19, 46, 209), (17, 127, 45), (237, 84, 186), (239, 125, 13), (245, 245, 87),
                     (107, 47, 187), (56, 254, 220), (80, 239, 57), (214, 224, 240)][i % 10]
        cast.append(s)
    return cast


def special_specs(rng) -> dict[str, Spec]:
    dj = random_spec(rng, "human")
    dj.hat, dj.top_style, dj.glow, dj.role = "headphones", "tee", None, "dj"
    dj.wheelchair = False
    dj.top = (20, 20, 24)
    farmer = Spec(kind="human", skin=SKIN[2], hair=(120, 120, 120), hair_style="short", top=(200, 60, 50),
                  top_style="overalls", bottom=(60, 90, 160), bottom_style="pants", shoes=(70, 50, 30),
                  hat="straw", face=["beard"], role="farmer")
    baby = Spec(kind="baby", skin=SKIN[1], hair=(230, 200, 120), hair_style="short", top=(250, 250, 250),
                top_style="tee", bottom=(250, 250, 250), bottom_style="pants", shoes=(250, 250, 250), role="baby")
    alien = Spec(kind="alien", skin=(170, 180, 170), hair=(0, 0, 0), hair_style="bald", top=(120, 96, 60),
                 top_style="tee", bottom=(60, 60, 60), bottom_style="pants", shoes=(30, 30, 30), role="alien")
    return {"dj": dj, "farmer": farmer, "baby": baby, "alien": alien}


# ---------------------------------------------------------------- animals, homages, flags, glyphs
def _img(w, h):
    return Canvas(w, h)


def cow_frames(rng):
    frames = {}
    spots = [(int(rng.integers(6, 34)), int(rng.integers(8, 18)), int(rng.integers(3, 7))) for _ in range(6)]
    for name, head_dy, mouth, stand in [("stand", 0, False, False), ("chew", 3, False, False), ("moo", -3, True, False),
                                        ("bang", 5, False, False), ("dance", 0, True, True)]:
        cv = _img(48, 32)
        if stand:   # comedic: cow on its hind legs
            cv.rect(18, 4, 12, 20, (245, 245, 240))
            for (x, y, r) in spots[:3]:
                cv.circle(18 + x % 12, 4 + y % 20, r - 1, (30, 26, 26))
            cv.rect(19, 24, 3, 7, (245, 245, 240))
            cv.rect(26, 24, 3, 7, (245, 245, 240))
            cv.rect(14, 8, 4, 3, (245, 245, 240))
            cv.rect(30, 6, 4, 3, (245, 245, 240))
            cv.rect(19, -2 + 4, 10, 8, (245, 245, 240))
            cv.rect(20, 5, 8, 4, (240, 170, 170))
            cv.px(21, 3, (20, 20, 20))
            cv.px(26, 3, (20, 20, 20))
            cv.rect(23, 7, 2, 1, (60, 20, 20))
            cv.px(18, 1, (220, 200, 160))
            cv.px(29, 1, (220, 200, 160))
            cv.rect(22, 12, 4, 2, emi((255, 210, 60)))   # cowbell
        else:
            cv.rect(8, 9, 30, 14, (245, 245, 240))
            for (x, y, r) in spots:
                cv.circle(x + 4, y + 2, r, (30, 26, 26))
            cv.rect(8, 9, 30, 1, (250, 250, 250))
            for lx in (10, 15, 30, 35):
                cv.rect(lx, 22, 3, 8, (235, 235, 230))
                cv.rect(lx, 29, 3, 2, (40, 30, 30))
            cv.rect(30, 22, 5, 3, (250, 180, 190))   # udder
            hy = 6 + head_dy
            cv.rect(36, hy, 10, 10, (245, 245, 240))
            cv.rect(40, hy + 6, 7, 5, (240, 170, 170))
            cv.px(39, hy + 3, (20, 20, 20))
            cv.px(43, hy + 3, (20, 20, 20))
            cv.px(36, hy - 1, (220, 200, 160))
            cv.px(45, hy - 1, (220, 200, 160))
            if mouth:
                cv.rect(42, hy + 9, 3, 2, (60, 20, 20))
            cv.line((8, 10), (5, 18), (230, 230, 225))
            cv.rect(37, hy + 11, 3, 3, (220, 180, 40))   # bell
        frames[name] = outline(cv.array())
    return frames


def chicken_frames():
    out = {}
    for name, hx, hy, legs, wing in [("stand", 10, 2, 0, 0), ("peck", 12, 7, 0, 0), ("fwd", 12, 2, 0, 0),
                                     ("back", 9, 2, 0, 0), ("run1", 11, 3, 1, 1), ("run2", 11, 3, 2, 0),
                                     ("flap", 10, 1, 0, 2)]:
        cv = _img(16, 16)
        cv.ellipse(2, 5, 10, 7, (250, 250, 245))
        cv.rect(1, 5, 3, 3, (250, 250, 245))
        cv.rect(hx, hy, 4, 5, (250, 250, 245))
        cv.px(hx + 2, hy + 1, (20, 20, 20))
        cv.rect(hx + 4, hy + 2, 2, 1, (250, 170, 0))
        cv.rect(hx + 1, hy - 1, 2, 1, (230, 20, 20))
        cv.px(hx + 3, hy + 3, (230, 20, 20))
        if wing == 1:
            cv.rect(4, 4, 5, 2, (230, 230, 225))
        elif wing == 2:
            cv.line((5, 6), (2, 1), (240, 240, 235))
            cv.line((8, 6), (11, 1), (240, 240, 235))
        lx = [(6, 8), (5, 9), (7, 7)][legs]
        for x in lx:
            cv.rect(x, 12, 1, 3, (250, 170, 0))
        out[name] = outline(cv.array())
    return out


def cat_frames():
    out = {}
    for name, tilt in [("c", 0), ("l", -1), ("r", 1), ("d", 0)]:
        cv = _img(16, 16)
        cv.ellipse(3, 8, 10, 8, (60, 60, 64))
        dy = 1 if name == "d" else 0
        cv.rect(4 + tilt, 3 + dy, 8, 7, (60, 60, 64))
        cv.px(4 + tilt, 2 + dy, (60, 60, 64))
        cv.px(11 + tilt, 2 + dy, (60, 60, 64))
        cv.px(6 + tilt, 5 + dy, emi((200, 255, 80)))
        cv.px(9 + tilt, 5 + dy, emi((200, 255, 80)))
        cv.px(7 + tilt, 7 + dy, (255, 150, 160))
        cv.line((13, 13), (15, 9), (60, 60, 64))
        out[name] = outline(cv.array())
    return out


def misc_sprites():
    out = {}
    # chomper
    for k, ang in enumerate([0.05, 0.35, 0.6, 0.35]):
        cv = _img(16, 16)
        cv.circle(8, 8, 7, (255, 230, 0))
        pts = [(8, 8), (16, 8 - 16 * math.tan(ang)), (16, 8 + 16 * math.tan(ang))]
        pygame.draw.polygon(cv.s, (0, 0, 0, 0), pts)
        cv.px(8, 4, (0, 0, 0))
        out[f"chomp{k}"] = cv.array()
    for name, col in [("ghost_r", (255, 0, 0)), ("ghost_p", (255, 184, 255)), ("ghost_c", (0, 255, 255)),
                      ("ghost_o", (255, 184, 82)), ("ghost_b", (33, 33, 255))]:
        for f in range(2):
            cv = _img(16, 16)
            cv.circle(8, 7, 6, col)
            cv.rect(2, 7, 13, 6, col)
            for x in range(2, 15, 4):
                cv.rect(x + (2 if f else 0), 13, 2, 2, col)
            if name != "ghost_b":
                for ex in (5, 10):
                    cv.rect(ex - 1, 5, 3, 4, (255, 255, 255))
                    cv.rect(ex, 6, 2, 2, (30, 30, 200))
            else:
                cv.px(6, 7, (255, 220, 200))
                cv.px(10, 7, (255, 220, 200))
            out[f"{name}{f}"] = cv.array()
    # golden ring, 4 spin frames
    for k, w in enumerate([12, 8, 3, 8]):
        cv = _img(16, 16)
        cv.ellipse(8 - w / 2, 2, w, 12, emi((255, 210, 40)))
        if w > 4:
            cv.ellipse(8 - w / 2 + 2, 4, w - 4, 8, (0, 0, 0, 0))
        out[f"ring{k}"] = cv.array()
    # question block and coin
    cv = _img(16, 16)
    cv.rect(0, 0, 16, 16, (240, 160, 30))
    cv.rect(0, 0, 16, 1, (255, 220, 120))
    for (x, y) in [(5, 3), (6, 2), (7, 2), (8, 2), (9, 2), (10, 3), (10, 4), (9, 5), (8, 6), (7, 7), (7, 8), (7, 11)]:
        cv.rect(x, y, 1, 1, (120, 60, 10))
    for c in [(1, 1), (14, 1), (1, 14), (14, 14)]:
        cv.px(*c, (120, 60, 10))
    out["qblock"] = outline(cv.array())
    for k, w in enumerate([10, 6, 2, 6]):
        cv = _img(12, 16)
        cv.ellipse(6 - w / 2, 1, w, 14, emi((255, 220, 60)))
        out[f"coin{k}"] = cv.array()
    # 1-up mushroom, star, heart, note, exclamation, sweat drop, sparkle, smiley
    cv = _img(16, 16)
    cv.ellipse(0, 1, 16, 10, (60, 200, 60))
    for (x, y, r) in [(4, 4, 2), (12, 4, 2), (8, 2, 1)]:
        cv.circle(x, y, r, (255, 255, 255))
    cv.rect(4, 9, 8, 6, (250, 230, 190))
    cv.px(6, 11, (0, 0, 0))
    cv.px(9, 11, (0, 0, 0))
    out["mushroom"] = outline(cv.array())
    cv = _img(16, 16)
    pts = []
    for k in range(10):
        r = 7.5 if k % 2 == 0 else 3.2
        a = -math.pi / 2 + k * math.pi / 5
        pts.append((8 + r * math.cos(a), 8.5 + r * math.sin(a)))
    pygame.draw.polygon(cv.s, emi((255, 230, 40)), pts)
    cv.px(6, 7, (0, 0, 0))
    cv.px(9, 7, (0, 0, 0))
    out["star"] = cv.array()
    cv = _img(9, 8)
    for (x, y, w) in [(1, 0, 2), (6, 0, 2), (0, 1, 4), (5, 1, 4), (0, 2, 9), (0, 3, 9), (1, 4, 7), (2, 5, 5), (3, 6, 3), (4, 7, 1)]:
        cv.rect(x, y, w, 1, emi((255, 60, 120)))
    out["heart"] = cv.array()
    cv = _img(8, 10)
    cv.rect(5, 0, 1, 8, emi((255, 255, 255)))
    cv.rect(5, 0, 3, 2, emi((255, 255, 255)))
    cv.ellipse(1, 6, 5, 4, emi((255, 255, 255)))
    out["note"] = cv.array()
    cv = _img(6, 12)
    cv.rect(2, 0, 2, 8, (255, 255, 255))
    cv.rect(2, 10, 2, 2, (255, 255, 255))
    out["bang"] = outline(cv.array())
    cv = _img(6, 9)
    cv.ellipse(0, 3, 6, 6, (140, 200, 255))
    cv.rect(2, 0, 2, 4, (140, 200, 255))
    out["sweat"] = outline(cv.array())
    for k, r in enumerate([1, 3, 4]):
        cv = _img(9, 9)
        cv.line((4, 4 - r), (4, 4 + r), emi((255, 255, 255)))
        cv.line((4 - r, 4), (4 + r, 4), emi((255, 255, 255)))
        out[f"sparkle{k}"] = cv.array()
    cv = _img(32, 32)
    cv.circle(16, 16, 15, (255, 220, 0))
    cv.rect(10, 9, 3, 6, (0, 0, 0))
    cv.rect(19, 9, 3, 6, (0, 0, 0))
    pygame.draw.arc(cv.s, (0, 0, 0, 255), (7, 6, 18, 18), math.pi * 1.1, math.pi * 1.9, 2)
    out["smiley"] = cv.array()
    # rainbow pop-tart cat (two frames)
    for f in range(2):
        cv = _img(34, 22)
        cv.rect(6, 3, 18, 14, (250, 200, 160))
        cv.rect(8, 5, 14, 10, (255, 150, 210))
        for k in range(6):
            cv.px(9 + (k * 5) % 12, 6 + (k * 3) % 8, (230, 40, 120))
        cv.rect(20, 8 + f, 10, 8, (150, 150, 150))
        cv.px(21, 7 + f, (150, 150, 150))
        cv.px(28, 7 + f, (150, 150, 150))
        cv.px(23, 10 + f, (20, 20, 20))
        cv.px(27, 10 + f, (20, 20, 20))
        cv.px(22, 13 + f, (255, 140, 160))
        cv.px(28, 13 + f, (255, 140, 160))
        for lx in (7, 11, 18, 22):
            cv.rect(lx + f, 17, 2, 3, (150, 150, 150))
        cv.rect(2, 9 - f, 4, 3, (150, 150, 150))
        out[f"nyan{f}"] = outline(cv.array())
    # space invader (crop circles and TVs use their own copy)
    for f, rows in enumerate([[0x104, 0x088, 0x1FC, 0x376, 0x7FF, 0x5FD, 0x505, 0x0D8],
                              [0x104, 0x489, 0x5FD, 0x777, 0x7FF, 0x3FE, 0x104, 0x202]]):
        cv = _img(11, 8)
        for y, r in enumerate(rows):
            for x in range(11):
                if (r >> (10 - x)) & 1:
                    cv.px(x, y, emi((80, 255, 80)))
        out[f"invader{f}"] = cv.array()
    # dancing hot dog
    for f in range(2):
        cv = _img(16, 32)
        cv.ellipse(3, 2 + f, 10, 26, (200, 90, 50))
        cv.rect(2, 8 + f, 12, 16, (240, 200, 120))
        cv.line((5, 10 + f), (11, 12 + f), (255, 220, 0))
        cv.line((5, 14 + f), (11, 16 + f), (255, 220, 0))
        cv.px(6, 6 + f, (0, 0, 0))
        cv.px(9, 6 + f, (0, 0, 0))
        cv.line((1, 14), (0 - f, 10 + 4 * f), (240, 200, 120))
        cv.line((14, 14), (16, 10 + 4 * (1 - f)), (240, 200, 120))
        cv.rect(4 - f, 28, 2, 4, (200, 90, 50))
        cv.rect(10 + f, 28, 2, 4, (200, 90, 50))
        out[f"hotdog{f}"] = outline(cv.array())
    # goat: normal / screaming
    for f in range(2):
        cv = _img(24, 22)
        cv.rect(3, 8, 14, 8, (235, 225, 210))
        for lx in (4, 7, 13, 16):
            cv.rect(lx, 15, 2, 6, (210, 200, 185))
        cv.rect(15, 3 - f * 2, 7, 7, (235, 225, 210))
        cv.px(15, 1 - f * 2, (150, 130, 100))
        cv.px(16, 0 - f * 2, (150, 130, 100))
        cv.px(19, 5 - f * 2, (20, 20, 20))
        cv.rect(19, 10 - f * 2, 2, 3, (235, 225, 210))
        if f:
            cv.rect(20, 7, 3, 3, (90, 20, 30))
        out[f"goat{f}"] = outline(cv.array())
    # sheep and dog
    for f in range(2):
        cv = _img(22, 16)
        cv.ellipse(2, 2 - f * 2, 16, 10, (245, 245, 245))
        cv.rect(15, 3 - f * 2, 6, 6, (40, 40, 40))
        cv.px(19, 5 - f * 2, (255, 255, 255))
        for lx in (5, 13):
            cv.rect(lx, 11 - f * 2, 2, 4, (40, 40, 40))
        out[f"sheep{f}"] = outline(cv.array())
        cv = _img(24, 16)
        cv.rect(4, 5, 13, 6, (140, 90, 40))
        cv.rect(16, 2, 6, 6, (140, 90, 40))
        cv.px(20, 4, (20, 20, 20))
        cv.rect(22, 5, 2, 2, (30, 20, 20))
        cv.rect(16, 1, 2, 3, (90, 60, 30))
        legs = [(5, 10), (8, 10), (13, 10), (15, 10)] if f == 0 else [(3, 9), (9, 10), (12, 9), (17, 10)]
        for lx, ly in legs:
            cv.rect(lx, ly, 2, 5, (140, 90, 40))
        cv.line((4, 6), (1, 3 + f), (140, 90, 40))
        out[f"dog{f}"] = outline(cv.array())
    # crow and duck
    for f in range(2):
        cv = _img(10, 8)
        cv.ellipse(1, 2, 7, 5, (20, 20, 24))
        cv.rect(6, 1, 3, 3, (20, 20, 24))
        cv.px(9, 2, (230, 180, 0))
        if f:
            cv.line((3, 3), (1, 0), (40, 40, 44))
        out[f"crow{f}"] = cv.array()
        cv = _img(12, 12)
        cv.ellipse(1, 4, 9, 6, (250, 250, 250))
        cv.rect(7, 1, 4, 4, (250, 250, 250))
        cv.rect(10, 3, 2, 1, (250, 160, 0))
        cv.px(9, 2, (0, 0, 0))
        cv.rect(3 + f, 10, 2, 2, (250, 160, 0))
        cv.rect(6 - f, 10, 2, 2, (250, 160, 0))
        out[f"duck{f}"] = outline(cv.array())
    return out


def flag_image(name: str, w=48, h=30) -> np.ndarray:
    img = np.zeros((h, w, 4), np.uint8)
    img[:, :, 3] = 255
    if name == "progress":
        bands = FLAGS["rainbow"]
        for k, c in enumerate(bands):
            img[k * h // 6:(k + 1) * h // 6, :, :3] = c
        chev = [(0, 0, 0), (120, 80, 40), (91, 206, 250), (245, 169, 184), (255, 255, 255)]
        yy, xx = np.mgrid[0:h, 0:w]
        d = xx + np.abs(yy - h / 2)
        for k, c in enumerate(chev):
            m = d < (h * 0.85 - k * 4)
            img[m, :3] = c
        yel = d < (h * 0.85 - 5 * 4)
        img[yel, :3] = (255, 216, 0)
        ring = (np.hypot(xx - 6, yy - h / 2) - 3.2) ** 2 < 1.2
        img[ring, :3] = (121, 2, 170)
        return img
    if name == "intersex":
        img[:, :, :3] = (255, 216, 0)
        yy, xx = np.mgrid[0:h, 0:w]
        ring = np.abs(np.hypot(xx - w / 2, yy - h / 2) - h * 0.28) < 1.8
        img[ring, :3] = (121, 2, 170)
        return img
    if name == "smiley":
        img[:, :, :3] = (10, 10, 10)
        yy, xx = np.mgrid[0:h, 0:w]
        r = np.hypot(xx - w / 2, yy - h / 2)
        img[r < h * 0.4, :3] = (255, 220, 0)
        for ex in (-4, 4):
            img[(np.abs(xx - (w / 2 + ex)) < 1.2) & (np.abs(yy - (h / 2 - 3)) < 2.2), :3] = (0, 0, 0)
        img[(np.abs(r - h * 0.24) < 1.0) & (yy > h / 2 + 1), :3] = (0, 0, 0)
        return img
    if name == "spiral":
        img[:, :, :3] = (10, 10, 10)
        yy, xx = np.mgrid[0:h, 0:w]
        a = np.arctan2(yy - h / 2, xx - w / 2)
        r = np.hypot(xx - w / 2, yy - h / 2)
        img[(np.mod(r - a * 2.0, 6.3) < 2.0) & (r < h * 0.45), :3] = (240, 240, 240)
        return img
    bands = FLAGS[name]
    for k, c in enumerate(bands):
        img[k * h // len(bands):(k + 1) * h // len(bands), :, :3] = c
    return img


# ---------------------------------------------------------------- atlas
class Atlas:
    def __init__(self, w=4096, h=4096):
        self.W, self.H = w, h
        self.img = np.zeros((h, w, 4), np.uint8)
        self.x = self.y = self.row = 0
        self.rects: dict[str, tuple] = {}

    def place(self, name: str, a: np.ndarray) -> tuple:
        h, w = a.shape[:2]
        if self.x + w > self.W:
            self.x, self.y, self.row = 0, self.y + self.row + 1, 0
        if self.y + h > self.H:
            raise RuntimeError("atlas full")
        self.img[self.y:self.y + h, self.x:self.x + w] = a
        r = (self.x / self.W, self.y / self.H, (self.x + w) / self.W, (self.y + h) / self.H)
        self.rects[name] = r
        self.x += w + 1
        self.row = max(self.row, h)
        return r


def build_atlas(cast: list[Spec], specials: dict[str, Spec], rng) -> tuple[Atlas, dict]:
    """Returns the atlas plus lookup tables: char_uv (n_chars, n_poses, 4) and hand offsets."""
    pygame.init()
    at = Atlas()
    everyone = list(cast) + [specials[k] for k in ("dj", "farmer", "baby", "alien")]
    n, npose = len(everyone), len(POSES)
    uv = np.zeros((n, 2, npose, 4), np.float32)       # [char, front/back, pose]
    hand = np.zeros((n, 2, npose, 2), np.float32)
    for c, spec in enumerate(everyone):
        for p, (pname, pd) in enumerate(POSES):
            img, hr = draw_character(spec, pname)
            uv[c, 0, p] = at.place(f"c{c}_{pname}", img)
            hand[c, 0, p] = hr
            if "side" in pd or spec.kind in ("crewmate", "creeper", "stick"):
                uv[c, 1, p], hand[c, 1, p] = uv[c, 0, p], hr
            else:
                img, hr = draw_character(spec, pname, back=True)
                uv[c, 1, p] = at.place(f"c{c}_{pname}_b", img)
                hand[c, 1, p] = hr
    for name, img in cow_frames(rng).items():
        at.place(f"cow_{name}", img)
    for name, img in chicken_frames().items():
        at.place(f"chicken_{name}", img)
    for name, img in cat_frames().items():
        at.place(f"cat_{name}", img)
    for name, img in misc_sprites().items():
        at.place(name, img)
    for name in FLAGS:
        at.place(f"flag_{name}", flag_image(name))
    for ch in GLYPHS:
        at.place(f"g_{ch}", glyph_image(ch))
    white = np.full((4, 4, 4), 255, np.uint8)
    at.place("white", white)
    tables = {"char_uv": uv, "hand": hand, "n_cast": len(cast),
              "special_index": {k: len(cast) + i for i, k in enumerate(("dj", "farmer", "baby", "alien"))},
              "specs": everyone}
    return at, tables
