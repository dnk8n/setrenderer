"""The only text on screen: tempo and other geeky music stats, styled like DJ gear.

Top left: BPM (live, from the beat grid), bar.beat counter, phrase, Camelot key, LUFS.
Top right: five-band meter and a kick LED. Bottom: a CDJ-style overview of the whole set
(three-band colour waveform with the playhead) and a zoomed beat-grid waveform.
"""
from __future__ import annotations

import numpy as np

from .parts import hue

GW, GH = 5, 7


class HUD:
    def __init__(self, W: int, H: int, rects: dict, extras: dict | None, clip_start: float, total: float, struct,
                 cfg: dict):
        self.W, self.H = W, H
        self.r = rects
        self.white = rects["white"]
        self.clip_start, self.total = clip_start, total
        self.st = struct
        self.enabled = cfg.get("enabled", True)
        self.wave_cols = None
        if extras is not None and len(extras.get("wave", [])):
            wv = extras["wave"]
            rate = float(extras["rate"])
            ncol = int(W * 0.9)
            edges = np.linspace(0, len(wv), ncol + 1).astype(int)
            cols = np.array([wv[a:max(b, a + 1)].mean(0) for a, b in zip(edges[:-1], edges[1:])])
            cols /= np.percentile(cols, 99, axis=0) + 1e-9
            self.wave_cols = np.clip(cols, 0, 1.2)
            self.wave = wv / (np.percentile(wv, 99, axis=0) + 1e-9)
            self.wave_rate = rate
            self.lufs = extras["lufs_s"]
            self.key_t = extras["key_t"]
            self.key_code = [str(k) for k in extras["key_code"]]
        else:
            self.lufs = None

    # ---------------------------------------------------------------- primitives
    def _text(self, out, s, x, y, col, scale=1, alpha=1.0):
        for ch in s:
            if ch != " ":
                key = f"g_{ch}" if f"g_{ch}" in self.r else "g_ "
                out.append([x, y, GW * scale, GH * scale, *self.r[key], *col, alpha])
            x += (GW + 1) * scale
        return x

    def _rect(self, out, x, y, w, h, col, alpha):
        out.append([x, y, w, h, -1, 0, 0, 0, *col, alpha])

    # ---------------------------------------------------------------- frame
    def build(self, c, bpm: float, bar_no: int, beat_in_bar: int, phrase: tuple, env: dict, kick: bool,
              konami_age: float | None, fade: float = 1.0) -> np.ndarray:
        if not self.enabled or fade <= 0:
            return np.zeros((0, 12), np.float32)
        out: list = []
        a = 0.88 * fade
        neon = (0.35, 1.0, 0.9)
        pink = (1.0, 0.35, 0.8)
        dim = (0.6, 0.65, 0.75)
        T = self.clip_start + c.t
        # panel
        self._rect(out, 6, 6, 148, 50, (0.02, 0.02, 0.06), 0.55 * fade)
        x = self._text(out, f"{bpm:5.1f}" if 60 <= bpm <= 220 else "---.-", 12, 11, neon, 2, a)
        self._text(out, "BPM", x + 4, 18, dim, 1, a)
        self._text(out, f"BAR {bar_no:04d}.{beat_in_bar}", 12, 30, (1, 1, 1), 1, a)
        self._text(out, f"PHR {phrase[0]:02d}.{phrase[1]}", 92, 30, dim, 1, a)
        if self.lufs is not None:
            i = int(np.clip(T * self.wave_rate, 0, len(self.lufs) - 1))
            lu = float(self.lufs[i])
            k = int(np.clip(np.searchsorted(self.key_t, T) - 1, 0, len(self.key_code) - 1))
            code = self.key_code[k]
            x = self._text(out, "KEY", 12, 42, dim, 1, a)
            if code[:-1].isdigit():
                num = int(code[:-1])
                kc = hue((num - 1) / 12.0, 0.75, 1.0)
                self._rect(out, x + 3, 41, 18, 9, kc, 0.9 * fade)
                self._text(out, code.rjust(3), x + 3, 42, (0.05, 0.05, 0.08), 1, a)
            else:
                self._text(out, " --", x + 3, 42, dim, 1, a)
            self._text(out, f"LUFS {lu:5.1f}" if lu > -60 else "LUFS  -INF", 70, 42, pink, 1, a)
        # five-band meter and kick LED, top right
        names = ("sub", "bass", "lowmid", "highmid", "high")
        x0 = self.W - 58
        self._rect(out, x0 - 6, 6, 58, 34, (0.02, 0.02, 0.06), 0.55 * fade)
        for k, n in enumerate(names):
            v = float(env.get(n, 0.0))
            h = int(round(v * 22))
            col = hue(0.55 - k * 0.12, 0.8, 1.0)
            self._rect(out, x0 + k * 8, 34 - h, 6, h, col, a)
            self._rect(out, x0 + k * 8, 35, 6, 1, dim, 0.5 * fade)
        self._rect(out, x0 + 42, 12, 6, 6, (1.0, 0.15, 0.2) if (kick and env.get("beat", 0) > 0.4) else (0.2, 0.05, 0.05), a)
        # whole-set overview with playhead
        if self.wave_cols is not None:
            ncol = len(self.wave_cols)
            bx = (self.W - ncol) // 2
            by = self.H - 12
            ph = T / max(self.total, 1e-6)
            pc = int(ph * ncol)
            self._rect(out, bx - 2, by - 31, ncol + 4, 42, (0.02, 0.02, 0.05), 0.45 * fade)
            for k in range(ncol):
                lo, mi, hi_ = self.wave_cols[k]
                amp = min(1.0, 0.45 * lo + 0.35 * mi + 0.2 * hi_)
                h = max(1, int(amp * 9))
                col = (0.15 + 0.85 * min(1, hi_ * 0.8), 0.35 + 0.5 * min(1, mi), 0.9 if lo > mi else 0.55)
                al = (0.95 if k <= pc else 0.45) * fade
                self._rect(out, bx + k, by + 4 - h // 2, 1, h, col, al)
            self._rect(out, bx + pc, by - 2, 1, 12, (1, 0.2, 0.2), fade)
            # zoomed waveform with beat grid, +/- 4 s around the playhead
            zw = 220
            zx = (self.W - zw) // 2
            zy = by - 18
            span = 8.0
            t0 = T - span / 2
            idx = ((t0 + np.arange(zw) / zw * span) * self.wave_rate).astype(int)
            ok = (idx >= 0) & (idx < len(self.wave))
            for k in np.nonzero(ok)[0][::1]:
                lo, mi, hi_ = self.wave[idx[k]]
                amp = min(1.0, 0.5 * lo + 0.35 * mi + 0.15 * hi_)
                h = max(1, int(amp * 22))
                col = (0.2 + 0.8 * min(1, hi_), 0.45 + 0.4 * min(1, mi), 1.0 if lo > mi else 0.6)
                self._rect(out, zx + k, zy - h // 2, 1, h, col, 0.85 * fade)
            beats = self.st.beats
            db = set(np.round(self.st.downbeats, 3).tolist())
            lo_t, hi_t = c.t - span / 2, c.t + span / 2
            i0, i1 = np.searchsorted(beats, lo_t), np.searchsorted(beats, hi_t)
            for b in beats[i0:i1]:
                px = zx + int((b - lo_t) / span * zw)
                is_down = round(float(b), 3) in db
                self._rect(out, px, zy - 12, 1, 24 if is_down else 6, (1, 0.25, 0.25) if is_down else (1, 1, 1), 0.7 * fade)
            self._rect(out, zx + zw // 2, zy - 13, 1, 26, (1, 1, 1), fade)
        # Konami code: dance-game arrows scroll up the right edge
        if konami_age is not None:
            seq = "^^vv<><>"
            beat = 60 / max(bpm, 60)
            for k, ch in enumerate(seq):
                y = self.H - 60 - (konami_age - k * beat) * 70
                if 50 < y < self.H - 40:
                    hit = abs(y - 70) < 8
                    self._text(out, ch, self.W - 30, int(y), (1, 1, 0.3) if hit else (0.4, 0.9, 1.0), 3, a)
            self._rect(out, self.W - 34, 66, 24, 1, (1, 1, 1), 0.6 * fade)
        return np.array(out, np.float32).reshape(-1, 12)
