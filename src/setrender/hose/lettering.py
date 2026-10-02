"""Hand-lettered title type: every glyph is a few pen strokes (lines and quadratic curves) on a
grid 6 units tall, drawn as fat ink-outlined tubes so the words look painted on a title card and
boil like the rest of the drawing."""
from __future__ import annotations

import math

# M x,y moves the pen, L x,y draws a line, Q cx,cy x,y draws a curve. Width follows the name.
GLYPHS = {
    "A": (4.2, "M0,6 L2.1,0 L4.2,6 M0.9,3.9 L3.3,3.9"),
    "B": (3.9, "M0,0 L0,6 M0,0 L2.1,0 Q3.6,0 3.6,1.5 Q3.6,3 2.1,3 L0,3 M2.1,3 Q3.9,3 3.9,4.5 Q3.9,6 2.1,6 L0,6"),
    "C": (3.9, "M3.8,1 Q3,0 2,0 Q0,0 0,3 Q0,6 2,6 Q3,6 3.8,5"),
    "D": (4.0, "M0,0 L0,6 M0,0 L1.8,0 Q4,0 4,3 Q4,6 1.8,6 L0,6"),
    "E": (3.5, "M3.5,0 L0,0 L0,6 L3.5,6 M0,3 L2.7,3"),
    "F": (3.4, "M3.4,0 L0,0 L0,6 M0,3 L2.7,3"),
    "G": (4.0, "M3.8,1 Q3,0 2,0 Q0,0 0,3 Q0,6 2,6 Q4,6 4,3.4 L2.4,3.4"),
    "H": (4.0, "M0,0 L0,6 M4,0 L4,6 M0,3 L4,3"),
    "I": (2.0, "M0,0 L2,0 M1,0 L1,6 M0,6 L2,6"),
    "J": (3.6, "M1,0 L3.6,0 M2.8,0 L2.8,4.5 Q2.8,6 1.4,6 Q0,6 0,4.6"),
    "K": (4.0, "M0,0 L0,6 M3.8,0 L0,3.6 M1.2,2.6 L4,6"),
    "L": (3.4, "M0,0 L0,6 L3.4,6"),
    "M": (4.8, "M0,6 L0,0 L2.4,4 L4.8,0 L4.8,6"),
    "N": (4.0, "M0,6 L0,0 L4,6 L4,0"),
    "O": (4.2, "M2.1,0 Q4.2,0 4.2,3 Q4.2,6 2.1,6 Q0,6 0,3 Q0,0 2.1,0"),
    "P": (3.9, "M0,6 L0,0 L2.1,0 Q3.9,0 3.9,1.7 Q3.9,3.4 2.1,3.4 L0,3.4"),
    "Q": (4.3, "M2.1,0 Q4.2,0 4.2,3 Q4.2,6 2.1,6 Q0,6 0,3 Q0,0 2.1,0 M2.5,4.4 L4.3,6.4"),
    "R": (4.0, "M0,6 L0,0 L2.1,0 Q3.9,0 3.9,1.7 Q3.9,3.4 2.1,3.4 L0,3.4 M2,3.4 L4,6"),
    "S": (3.9, "M3.7,0.9 Q3.1,0 1.9,0 Q0.2,0 0.2,1.5 Q0.2,2.9 1.9,3 Q3.9,3.1 3.9,4.5 Q3.9,6 1.9,6 Q0.6,6 0,5.1"),
    "T": (4.0, "M0,0 L4,0 M2,0 L2,6"),
    "U": (4.0, "M0,0 L0,4 Q0,6 2,6 Q4,6 4,4 L4,0"),
    "V": (4.2, "M0,0 L2.1,6 L4.2,0"),
    "W": (5.0, "M0,0 L1.25,6 L2.5,2 L3.75,6 L5,0"),
    "X": (4.0, "M0,0 L4,6 M4,0 L0,6"),
    "Y": (4.0, "M0,0 L2,3 L4,0 M2,3 L2,6"),
    "Z": (4.0, "M0,0 L4,0 L0,6 L4,6"),
    "0": (3.6, "M1.8,0 Q3.6,0 3.6,3 Q3.6,6 1.8,6 Q0,6 0,3 Q0,0 1.8,0"),
    "1": (3.0, "M0.4,1.2 L1.8,0 L1.8,6 M0.4,6 L3,6"),
    "2": (3.8, "M0.2,1.2 Q0.8,0 2,0 Q3.8,0 3.8,1.7 Q3.8,3 2,4 L0,6 L3.8,6"),
    "3": (3.8, "M0.2,0.8 Q0.9,0 2,0 Q3.6,0 3.6,1.5 Q3.6,2.9 1.8,2.9 Q3.8,3 3.8,4.5 Q3.8,6 2,6 Q0.8,6 0,5.2"),
    "4": (4.0, "M3,6 L3,0 L0,4.2 L4,4.2"),
    "5": (3.8, "M3.6,0 L0.4,0 L0.2,2.8 Q1,2.3 2,2.3 Q3.8,2.3 3.8,4.1 Q3.8,6 1.9,6 Q0.7,6 0,5.2"),
    "6": (3.8, "M3.4,0.6 Q2.8,0 2,0 Q0,0 0,3.4 Q0,6 1.9,6 Q3.8,6 3.8,4.2 Q3.8,2.5 2,2.5 Q0.6,2.5 0,3.6"),
    "7": (3.8, "M0,0 L3.8,0 L1.5,6"),
    "8": (3.8, "M1.9,3 Q0.3,3 0.3,1.5 Q0.3,0 1.9,0 Q3.5,0 3.5,1.5 Q3.5,3 1.9,3 Q0,3 0,4.5 Q0,6 1.9,6 Q3.8,6 3.8,4.5 Q3.8,3 1.9,3"),
    "9": (3.8, "M0.4,5.4 Q1,6 1.8,6 Q3.8,6 3.8,2.6 Q3.8,0 1.9,0 Q0,0 0,1.8 Q0,3.5 1.8,3.5 Q3.2,3.5 3.8,2.4"),
    "!": (1.0, "M0.5,0 L0.5,4.2 M0.5,5.85 L0.5,5.9"),
    "?": (3.8, "M0.2,1.2 Q0.6,0 2,0 Q3.8,0 3.8,1.6 Q3.8,2.8 2,3.4 L2,4.3 M2,5.85 L2,5.9"),
    ".": (1.0, "M0.5,5.85 L0.5,5.9"),
    ",": (1.0, "M0.7,5.6 L0.2,6.8"),
    "-": (3.0, "M0.3,3.2 L2.7,3.2"),
    "'": (1.0, "M0.5,0 L0.5,1.6"),
    ":": (1.0, "M0.5,2 L0.5,2.05 M0.5,5.85 L0.5,5.9"),
    "/": (3.0, "M0,6 L3,0"),
    "&": (4.0, "M3.8,6 L1,2 Q0.4,1 1.2,0.3 Q2,-0.2 2.6,0.5 Q3,1.4 1.8,2.4 L0.6,3.6 Q-0.2,4.8 0.8,5.7 Q2,6.5 3.2,4.6 L3.8,3.8"),
    "#": (4.0, "M1.2,0.5 L0.8,5.5 M3.2,0.5 L2.8,5.5 M0,2 L4,2 M0,4 L4,4"),
    "+": (3.0, "M1.5,1.8 L1.5,4.6 M0.1,3.2 L2.9,3.2"),
    "(": (1.6, "M1.6,-0.2 Q0,3 1.6,6.2"),
    ")": (1.6, "M0,-0.2 Q1.6,3 0,6.2"),
    " ": (2.2, ""),
}


def _parse(path: str) -> list[tuple]:
    """-> list of segments ('L', x0, y0, x1, y1) or ('Q', x0, y0, cx, cy, x1, y1)."""
    segs, pen = [], (0.0, 0.0)
    toks = path.split()
    i = 0
    while i < len(toks):
        t = toks[i]
        cmd, rest = t[0], t[1:]
        if cmd == "M":
            pen = tuple(map(float, rest.split(",")))
        elif cmd == "L":
            p = tuple(map(float, rest.split(",")))
            segs.append(("L", *pen, *p))
            pen = p
        elif cmd == "Q":
            c = tuple(map(float, rest.split(",")))
            i += 1
            p = tuple(map(float, toks[i].split(",")))
            segs.append(("Q", *pen, *c, *p))
            pen = p
        i += 1
    return segs


_CACHE = {k: (w, _parse(p)) for k, (w, p) in GLYPHS.items()}


def text_width(s: str, size: float, track: float = 1.1) -> float:
    u = size / 6.0
    return sum((_CACHE.get(ch, _CACHE[" "])[0] + track) * u for ch in s.upper()) - track * u


def letter(ink, ch: str, x: float, y: float, size: float, weight: float, fill, rot: float = 0.0):
    """Strokes for one glyph, top-left at (x, y) in the current frame."""
    w, segs = _CACHE.get(ch.upper(), _CACHE[" "])
    u = size / 6.0
    r = weight * 0.5
    cx, cy = x + w * u * 0.5, y + 3 * u
    with ink.at(cx, cy, rot):
        for s in segs:
            if s[0] == "L":
                _, x0, y0, x1, y1 = s
                ink.capsule((x0 - w / 2) * u, (y0 - 3) * u, (x1 - w / 2) * u, (y1 - 3) * u, r, r * 0.92,
                            fill=fill, ink=0.0, shade=0.25)
            else:
                _, x0, y0, qx, qy, x1, y1 = s
                ink.bez((x0 - w / 2) * u, (y0 - 3) * u, (qx - w / 2) * u, (qy - 3) * u, (x1 - w / 2) * u,
                        (y1 - 3) * u, r, r * 0.92, fill=fill, ink=0.0, shade=0.25)
    return w * u


def words(ink, s: str, x: float, y: float, size: float, fill=(0.99, 0.93, 0.72, 1), outline=None,
          weight=None, shadow=(0.12, 0.085, 0.07, 0.85), wobble: float = 0.0, t: float = 0.0, track: float = 1.1,
          arc: float = 0.0, align: str = "center", pop=None):
    """Draw a line of lettering centred on (x, y). `wobble` makes letters bob like a cartoon title,
    `arc` bends the baseline (positive = smile), `pop` is a per-letter scale callback."""
    u = size / 6.0
    weight = weight if weight is not None else size * 0.17
    outline = outline if outline is not None else size * 0.07
    tw = text_width(s, size, track)
    x0 = x - tw / 2 if align == "center" else (x - tw if align == "right" else x)
    pos = []
    cx = x0
    for k, ch in enumerate(s.upper()):
        w = _CACHE.get(ch, _CACHE[" "])[0] * u
        mid = cx + w / 2 - x
        dy = (arc * (mid / max(tw / 2, 1)) ** 2 * size) if arc else 0.0
        b = math.sin(t * 7.0 + k * 0.9) * wobble * u
        r = math.sin(t * 5.0 + k * 1.7) * wobble * 0.04
        sc = pop(k) if pop else 1.0
        pos.append((ch, cx, y - 3 * u + dy + b, r, sc))
        cx += w + track * u
    for layer in ("shadow", "body"):
        if layer == "shadow" and not shadow:
            continue
        off = (size * 0.06, size * 0.07) if layer == "shadow" else (0.0, 0.0)
        col = shadow if layer == "shadow" else fill
        with ink.outlined(outline if layer == "body" else outline):
            for ch, lx, ly, r, sc in pos:
                if ch == " ":
                    continue
                w = _CACHE.get(ch, _CACHE[" "])[0] * u
                with ink.at(lx + w / 2 + off[0], ly + 3 * u + off[1], 0.0, sc):
                    letter(ink, ch, -w / 2, -3 * u, size, weight, col, r)
    return tw
