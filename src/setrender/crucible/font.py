"""A signed-distance font atlas for the overlay, made once per process from the sans font that ships with
pygame (FreeSans Bold, GNU FreeFont): crisp at any size, with outlines and shadows for free."""
from __future__ import annotations

import os

import numpy as np

CHARS = "".join(chr(c) for c in range(32, 127)) + "·×°–→↑μλ"
BASE = 96           # rendering size (px)
PAD = 12            # distance-field spread (px, at BASE)
_CACHE: dict = {}


def atlas():
    """(image (h, w) uint8, glyphs {ch: (u0, v0, u1, v1, w, h, advance)} in BASE pixels, line height)."""
    if "a" in _CACHE:
        return _CACHE["a"]
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame
    from scipy import ndimage
    pygame.font.init()
    f = pygame.font.Font(None, BASE)
    lh = f.get_height()
    digits = max(f.size(c)[0] for c in "0123456789")
    cells = []
    for ch in CHARS:
        w = max(1, f.size(ch)[0])
        surf = f.render(ch, True, (255, 255, 255), (0, 0, 0))
        a = pygame.surfarray.array3d(surf)[:, :, 0].T.astype(np.float32) / 255.0   # (h, w)
        adv = w
        if ch.isdigit():
            # tabular figures: every digit as wide as the widest, so counters don't jitter
            off = (digits - a.shape[1]) // 2
            b = np.zeros((a.shape[0], digits), np.float32)
            b[:, off:off + a.shape[1]] = a
            a, adv = b, digits
        m = np.pad(a, PAD) > 0.5
        if m.any():
            sd = ndimage.distance_transform_edt(~m) - ndimage.distance_transform_edt(m)
        else:
            sd = np.full(m.shape, float(PAD))
        v = np.clip(0.5 - sd / (2.0 * PAD), 0.0, 1.0)
        # half resolution is plenty for a distance field
        hh, ww = v.shape[0] // 2 * 2, v.shape[1] // 2 * 2
        v = v[:hh, :ww].reshape(hh // 2, 2, ww // 2, 2).mean((1, 3))
        cells.append((ch, v, adv, hh, ww))
    W = 2048
    x = y = rowh = 0
    pos = []
    for ch, v, adv, hh, ww in cells:
        if x + v.shape[1] + 1 > W:
            x, y, rowh = 0, y + rowh + 1, 0
        pos.append((x, y))
        x += v.shape[1] + 1
        rowh = max(rowh, v.shape[0])
    H = 1 << int(np.ceil(np.log2(y + rowh + 1)))
    img = np.zeros((H, W), np.uint8)
    glyphs = {}
    for (ch, v, adv, hh, ww), (gx, gy) in zip(cells, pos):
        img[gy:gy + v.shape[0], gx:gx + v.shape[1]] = (v * 255 + 0.5).astype(np.uint8)
        glyphs[ch] = (gx / W, gy / H, (gx + v.shape[1]) / W, (gy + v.shape[0]) / H, float(ww), float(hh), float(adv))
    _CACHE["a"] = (img, glyphs, float(lh))
    return _CACHE["a"]


def text_width(s: str, size: float, tracking: float = 0.0) -> float:
    _, g, lh = atlas()
    k = size / lh
    return sum(g.get(c, g["?"])[6] * k + tracking for c in s) - (tracking if s else 0.0)


def glyphs(s: str, x: float, y: float, size: float, color, align: float = 0.0, tracking: float = 0.0,
           outline: float = 0.0, dark: float = 0.8, weight: float = 0.0) -> np.ndarray:
    """Instances for a line of text: (x, y) is the top-left of the line box (align 0.5 centres, 1 right-aligns);
    size is the line height in pixels."""
    _, g, lh = atlas()
    k = size / lh
    x -= align * text_width(s, size, tracking)
    out = []
    for c in s:
        u0, v0, u1, v1, w, h, adv = g.get(c, g["?"])
        if c != " ":
            out.append([x - PAD * k, y - PAD * k, w * k, h * k, u0, v0, u1, v1, *color, outline, dark, 0.0, weight])
        x += adv * k + tracking
    return np.array(out, np.float32).reshape(-1, 16)
