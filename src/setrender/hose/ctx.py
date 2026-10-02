"""Per-frame state handed to stages, bosses and gags."""
from __future__ import annotations

import colorsys
import math
from dataclasses import dataclass


@dataclass
class Ctx:
    t: float                 # real time in the set (s)
    td: float                # drawing time: steps at 24 fps, re-phased on every beat
    beat: float              # beat position at td (integer part counts beats)
    bar: float               # bar position at td
    sub: float = 0.0
    bass: float = 0.0
    lowmid: float = 0.0
    highmid: float = 0.0
    high: float = 0.0
    loud: float = 0.0
    kick: float = 0.0        # decays from 1 on each beat (kick bars only)
    energy: float = 0.5      # bar intensity 0..1
    phase: int = 0
    phase_t: float = 99.0    # seconds since this phase began
    hurt: float = 0.0        # hit flash 0..1
    ko: float = -1.0         # knockout progress 0..1, -1 = fighting
    sup: float = -1.0        # super attack progress 0..1
    shot: float = 9.0        # seconds since the boss last fired
    intro: float = 1.0       # entrance progress 0..1
    variant: int = 0
    seed: float = 0.0
    sky: bool = False
    drawing: int = 0
    build: float = 0.0       # 0..1 while a build winds up
    hue: float = 0.0         # palette rotation for rematches

    @property
    def ph(self) -> float:
        """Phase of the current beat (0 on the beat)."""
        return self.beat % 1.0

    @property
    def squash(self) -> float:
        return math.exp(-(self.beat % 1.0) * 6.5)

    def col(self, c, flash: bool = True):
        r, g, b = c[:3]
        a = c[3] if len(c) > 3 else 1.0
        if self.hue:
            h, l, s = colorsys.rgb_to_hls(r, g, b)
            r, g, b = colorsys.hls_to_rgb((h + self.hue) % 1.0, l, s)
        if flash and self.hurt > 0:
            k = self.hurt * 0.45
            r, g, b = r + (1 - r) * k, g + (1 - g) * k, b + (0.9 - b) * k
        return (r, g, b, a)
