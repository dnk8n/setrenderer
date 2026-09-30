"""knisper-style scene built from reusable elements. Draws one frame at the internal resolution."""
from __future__ import annotations

import math

import numpy as np
import pygame

from . import sprites
from .config import get_path
from .timeline import Timeline


def hex2rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def mix(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def scale_c(c, f):
    return tuple(max(0, min(255, int(v * f))) for v in c)


def by_luma(pal):
    return sorted(pal, key=lambda c: 0.3 * c[0] + 0.59 * c[1] + 0.11 * c[2])


class Scene:
    def __init__(self, cfg: dict, tl: Timeline, rng: np.random.Generator, title: str, fingerprint: dict):
        pygame.init()
        self.cfg = cfg
        self.tl = tl
        self.W = int(get_path(cfg, "canvas.width", 480))
        self.H = int(get_path(cfg, "canvas.height", 270))
        self.surf = pygame.Surface((self.W, self.H))
        self.layer = pygame.Surface((self.W, self.H), pygame.SRCALPHA)
        self.title = title
        self.rng = rng
        self.el = cfg.get("elements", {})
        self.map = cfg.get("mapping", {})
        self.horizon = int(self.H * 0.58)
        self.floor_top = int(self.H * 0.70)
        self.font = pygame.font.Font(None, 12)
        self.font_big = pygame.font.Font(None, 16)

        # ---- per-set variation: palettes, per-section looks
        pals = {k: [hex2rgb(c) for c in v] for k, v in cfg["palettes"].items()}
        order = list(get_path(cfg, "variation.palette_order", list(pals)))
        order = [p for p in order if p in pals] or list(pals)
        if get_path(cfg, "variation.shuffle_palettes", True):
            order = [order[i] for i in rng.permutation(len(order))]
        # key of the set rotates the start palette: sets in different keys start differently
        k = int(fingerprint.get("key_pc", 0))
        order = order[k % len(order):] + order[:k % len(order)]
        self.palette_names = order
        self.palettes = pals
        n_sec = int(tl.section_idx.max()) + 1 if tl.n else 1
        sky_choices = get_path(cfg, "elements.sky.style_choices", ["copper"])
        floor_choices = get_path(cfg, "elements.floor.style_choices", ["checker"])
        shapes = get_path(cfg, "elements.n64_shape.shapes", ["cube"])
        hill_choices = get_path(cfg, "elements.hills.style_choices", ["blocks"])
        self.sec_look = []
        for s in range(n_sec):
            self.sec_look.append({
                "palette": order[s % len(order)],
                "sky": sky_choices[int(rng.integers(len(sky_choices)))],
                "floor": floor_choices[int(rng.integers(len(floor_choices)))],
                "shape": shapes[int(rng.integers(len(shapes)))],
                "laser_seed": int(rng.integers(1 << 30)),
                "hills": hill_choices[int(rng.integers(len(hill_choices)))],
            })

        # ---- static world layout
        self.stars = rng.random((140, 3))
        self.hill_seed = rng.random((3, 64))
        n_trees = int(get_path(cfg, "elements.trees.count", 4))
        jpt = get_path(cfg, "elements.trees.jellyfish_per_tree", [2, 4])
        xs = np.linspace(0.06, 0.94, n_trees) if n_trees > 1 else np.array([0.1])
        self.trees = []
        for i, x in enumerate(xs):
            # keep the middle clear for the stage
            if 0.32 < x < 0.68:
                x = 0.25 if x < 0.5 else 0.75
            tx = int(x * self.W + rng.integers(-10, 10))
            th = int(rng.integers(70, 100))
            jel = []
            for _ in range(int(rng.integers(jpt[0], jpt[1] + 1))):
                jel.append({"dx": int(rng.integers(-22, 22)), "len": int(rng.integers(8, 34)),
                            "hue": float(rng.random()), "size": int(rng.integers(7, 12)),
                            "ph": float(rng.random())})
            self.trees.append({"x": tx, "h": th, "w": int(rng.integers(34, 50)), "jelly": jel,
                               "leaf_seed": int(rng.integers(1 << 30))})
        self._leaf_cache = {}

        # ---- car stage (pre-rendered, burned out)
        self.car = self._make_car(rng)
        self.dj_colors = (sprites.SKIN[int(rng.integers(len(sprites.SKIN)))],
                          sprites.HAIR[int(rng.integers(len(sprites.HAIR)))],
                          (int(rng.integers(80, 255)), int(rng.integers(0, 120)), int(rng.integers(120, 255))))
        self.dj_frames = {(a, n): sprites.dj_sprite(a, n, *self.dj_colors) for a in range(3) for n in range(2)}

        # ---- crowd
        cc = self.el.get("crowd", {})
        count = int(cc.get("count", 40))
        types = cc.get("types", {"blocky": 1})
        tnames = list(types)
        tp = np.array([types[t] for t in tnames], float)
        tp /= tp.sum()
        base_pal = pals[order[0]]
        self.crowd = []
        for i in range(count):
            kind = tnames[int(rng.choice(len(tnames), p=tp))]
            spec = sprites.random_spec(rng, kind, base_pal, float(cc.get("flags", 0.15)), float(cc.get("glowsticks", 0.3)))
            depth = float(rng.random()) ** 0.8
            scale = 2 if depth > 0.9 else 1
            y = int(self.floor_top + 6 + depth * (self.H - self.floor_top - 8))
            x = int(rng.integers(8, self.W - 8))
            if scale == 1 and abs(x - self.W / 2) < 60 and depth < 0.25:
                x += 80 if x > self.W / 2 else -80
            self.crowd.append({"char": sprites.Character(spec, scale), "x": x, "y": y, "depth": depth})
        self.crowd.sort(key=lambda c: c["y"])

        msgs = get_path(cfg, "elements.scroller.messages", ["SETRENDER"])
        self.scroll_text = "   ".join(msgs).format(title=title.upper(), bpm=int(round(tl.tempo)))
        self.scroll_surf = self.font_big.render(self.scroll_text + "      ", False, (255, 255, 255))

    # ------------------------------------------------------------------ helpers
    def e(self, name: str, i: int) -> float:
        m = self.map.get(name, {"band": name, "gain": 1.0})
        band = m.get("band", name)
        v = self.tl.env[band][i] if band in self.tl.env else 0.0
        return float(v) * float(m.get("gain", 1.0))

    def pal(self, i: int) -> list:
        return self.palettes[self.sec_look[self.tl.section_idx[i]]["palette"]]

    def accents(self, i: int) -> list:
        p = by_luma(self.pal(i))
        return p[len(p) // 3:]

    def _make_car(self, rng) -> pygame.Surface:
        s = pygame.Surface((150, 52), pygame.SRCALPHA)
        body = (46, 38, 36)
        # tyre rims on cinder blocks
        for wx in (28, 116):
            pygame.draw.rect(s, (110, 110, 110), (wx - 9, 42, 18, 10))
            pygame.draw.rect(s, (80, 80, 80), (wx - 9, 46, 18, 1))
            pygame.draw.circle(s, (70, 64, 60), (wx, 40), 8)
            pygame.draw.circle(s, (30, 26, 24), (wx, 40), 4)
        # body and cabin
        pygame.draw.polygon(s, body, [(4, 38), (4, 26), (22, 22), (40, 10), (100, 8), (118, 22), (146, 26), (146, 38)])
        pygame.draw.polygon(s, (12, 10, 10), [(44, 12), (70, 11), (70, 22), (32, 22)])
        pygame.draw.polygon(s, (12, 10, 10), [(74, 11), (98, 10), (112, 22), (74, 22)])
        # cracks / broken glass shards
        pygame.draw.line(s, (90, 110, 120), (50, 13), (58, 21))
        pygame.draw.line(s, (90, 110, 120), (84, 12), (80, 20))
        # rust and soot
        for _ in range(260):
            x = int(rng.integers(6, 144))
            y = int(rng.integers(10, 38))
            if s.get_at((x, y))[3] and s.get_at((x, y))[:3] == body:
                c = [(120, 60, 24), (150, 80, 30), (90, 40, 20), (20, 18, 18), (60, 52, 48)][int(rng.integers(5))]
                s.set_at((x, y), c)
        pygame.draw.line(s, (20, 18, 18), (4, 30), (146, 30))
        # graffiti tag
        pygame.draw.lines(s, (255, 0, 180), False, [(14, 34), (18, 29), (22, 35), (26, 29), (30, 34)])
        return s

    # ------------------------------------------------------------------ elements
    def draw_sky(self, i):
        look = self.sec_look[self.tl.section_idx[i]]
        pal = by_luma(self.pal(i))
        t = self.tl.t[i]
        hm = self.e("sky_bars", i)
        s = self.surf
        H = self.horizon
        style = look["sky"]
        dark, mid = pal[0], pal[len(pal) // 2]
        if style == "night":
            s.fill(mix(dark, (0, 0, 0), 0.6), (0, 0, self.W, H))
        elif style == "plasma":
            w, h = self.W // 4, H // 4 + 1
            xs = np.arange(w)[None, :]
            ys = np.arange(h)[:, None]
            v = (np.sin(xs / 7.0 + t * 0.9) + np.sin(ys / 5.0 - t * 1.3)
                 + np.sin((xs + ys) / 9.0 + t * 0.7) + np.sin(np.hypot(xs - w / 2, ys - h) / 6.0 - t * 2))
            v = (v + 4) / 8 + hm * 0.25 + self.tl.beat_env[i] * 0.1
            p = np.array(pal, dtype=np.float32)
            idx = (v * (len(p) - 1) * 2).astype(int) % len(p)
            img = (p[idx] * (0.22 + 0.38 * hm + 0.15 * self.tl.beat_env[i])).clip(0, 255).astype(np.uint8)
            small = pygame.surfarray.make_surface(np.transpose(img, (1, 0, 2)))
            s.blit(pygame.transform.scale(small, (self.W, h * 4)), (0, 0))
        else:
            top = dark
            bot = mix(dark, mid, 0.55 + 0.3 * hm)
            for y in range(0, H, 2):
                c = mix(top, bot, y / H)
                # ordered dither between bands, 8-bit style
                pygame.draw.line(s, c, (0, y), (self.W, y))
                pygame.draw.line(s, mix(top, bot, (y + 1.5) / H) if (y // 2) % 2 else c, (0, y + 1), (self.W, y + 1))
            if style == "copper":
                n_bars = 5
                acc = self.accents(i)
                for b in range(n_bars):
                    cy = H * 0.45 + math.sin(t * (0.8 + b * 0.23) + b * 1.7) * H * 0.38
                    col = acc[(b + self.tl.bar_idx[i]) % len(acc)]
                    bh = 10
                    for k in range(-bh, bh + 1):
                        f = (1 - abs(k) / bh) * (0.35 + 0.65 * hm)
                        yy = int(cy + k)
                        if 0 <= yy < H:
                            pygame.draw.line(s, mix(s.get_at((0, yy))[:3], col, f), (0, yy), (self.W, yy))
            elif style == "gradient":
                # retro sun with stripes
                sun_c = self.accents(i)[-1]
                r = int(34 + 6 * self.e("dj", i))
                cx, cy = self.W // 2, H - 34
                pygame.draw.circle(s, sun_c, (cx, cy), r)
                for k in range(6):
                    yy = cy - r // 3 + k * 5 + int(t * 6) % 5
                    pygame.draw.line(s, bot, (cx - r, yy), (cx + r, yy), 2)
        # stars (all styles) twinkle with the highs
        hi = self.e("stars", i)
        speed = 1.0 if style == "starfield" else 0.0
        for k, (sx, sy, sz) in enumerate(self.stars):
            if style == "starfield":
                z = (sz - t * 0.08 * speed * (1 + hi)) % 1.0 + 0.02
                x = int(self.W / 2 + (sx - 0.5) * self.W * 0.6 / z)
                y = int(H / 2 + (sy - 0.5) * H * 0.6 / z)
                if not (0 <= x < self.W and 0 <= y < H):
                    continue
                b = min(1.0, 0.3 / z * (0.5 + hi))
            else:
                x, y = int(sx * self.W), int(sy * H * 0.9)
                b = 0.25 + 0.75 * hi * (0.5 + 0.5 * math.sin(t * 9 + k))
            c = scale_c((255, 255, 255), b)
            s.set_at((x, y), c)
            if b > 0.85:
                s.set_at((x + 1, y), c)
                s.set_at((x, y + 1), c)

    def draw_n64_shape(self, i):
        look = self.sec_look[self.tl.section_idx[i]]
        t = self.tl.t[i]
        shape = look["shape"]
        if shape == "cube":
            V = [(x, y, z) for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)]
            F = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
        elif shape == "octahedron":
            V = [(1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1)]
            F = [(0, 2, 4), (2, 1, 4), (1, 3, 4), (3, 0, 4), (2, 0, 5), (1, 2, 5), (3, 1, 5), (0, 3, 5)]
        else:  # star: a spiky bipyramid, very Mario 64
            V = [(0, 0, 1.2), (0, 0, -1.2)]
            for k in range(10):
                a = k * math.pi / 5
                r = 1.4 if k % 2 == 0 else 0.6
                V.append((r * math.cos(a), r * math.sin(a), 0))
            F = []
            for k in range(10):
                F.append((0, 2 + k, 2 + (k + 1) % 10))
                F.append((1, 2 + (k + 1) % 10, 2 + k))
        rot = t * (self.tl.tempo / 60) * 0.5
        ax, ay = rot * 0.7, rot
        size = 16 + 7 * self.tl.beat_env[i]
        cx = self.W * 0.5 + math.sin(t * 0.13) * self.W * 0.28
        cy = self.horizon * 0.33

        def tr(v):
            x, y, z = v
            y, z = y * math.cos(ax) - z * math.sin(ax), y * math.sin(ax) + z * math.cos(ax)
            x, z = x * math.cos(ay) + z * math.sin(ay), -x * math.sin(ay) + z * math.cos(ay)
            return x, y, z
        P = [tr(v) for v in V]
        acc = self.accents(i)
        light = (0.3, -0.5, -0.8)
        faces = []
        for fi, f in enumerate(F):
            a, b, c = (np.array(P[k]) for k in f[:3])
            n = np.cross(b - a, c - a)
            if n[2] >= 0:
                continue
            n /= np.linalg.norm(n) + 1e-9
            lum = 0.35 + 0.65 * max(0.0, -float(np.dot(n, light)))
            z = sum(P[k][2] for k in f) / len(f)
            faces.append((z, f, lum, fi))
        for z, f, lum, fi in sorted(faces, reverse=True):
            pts = [(float(cx + P[k][0] * size), float(cy + P[k][1] * size)) for k in f]
            pygame.draw.polygon(self.surf, scale_c(acc[fi % len(acc)], lum), pts)

    def draw_hills(self, i):
        t = self.tl.t[i]
        pal = by_luma(self.pal(i))
        n = int(get_path(self.cfg, "elements.hills.layers", 3))
        for L in range(n):
            col = mix((5, 5, 10), pal[min(len(pal) - 1, 1 + L)], 0.35 + 0.15 * L)
            blk = 8
            speed = (L + 1) * 2.0
            base = self.horizon - 26 + L * 12
            off = (t * speed) % blk
            checker = self.sec_look[self.tl.section_idx[i]].get("hills") == "checker" and L == n - 1
            for bx in range(-1, self.W // blk + 2):
                gx = bx + int(t * speed // blk)
                hgt = int(self.hill_seed[L][gx % 64] * (26 - L * 6)) // 4 * 4 + 4
                x = int(bx * blk - off)
                if checker:
                    # 16-bit era checkered soil with a grass lip
                    top = base - hgt
                    for yy in range(top, self.floor_top, 4):
                        c = (196, 108, 36) if ((gx + (yy - top) // 4) % 2) else (132, 64, 20)
                        pygame.draw.rect(self.surf, c, (x, yy, blk, 4))
                    pygame.draw.rect(self.surf, (60, 200, 60), (x, top, blk, 3))
                else:
                    pygame.draw.rect(self.surf, col, (x, base - hgt, blk, self.floor_top - base + hgt))

    def _leaves(self, tree, pal_name):
        key = (tree["leaf_seed"], pal_name)
        if key not in self._leaf_cache:
            r = np.random.default_rng(tree["leaf_seed"])
            w, h = tree["w"], 30
            s = pygame.Surface((w, h), pygame.SRCALPHA)
            greens = [(30, 110, 40), (40, 140, 50), (20, 80, 30), (60, 160, 60)]
            pal = self.palettes[pal_name]
            tint = by_luma(pal)[len(pal) // 2]
            for by in range(0, h, 4):
                for bx in range(0, w, 4):
                    edge = min(bx, w - bx - 4, by, h - by - 4)
                    if edge < 4 and r.random() < 0.35:
                        continue
                    c = mix(greens[int(r.integers(4))], tint, 0.25)
                    pygame.draw.rect(s, c, (bx, by, 4, 4))
            self._leaf_cache[key] = s
        return self._leaf_cache[key]

    def draw_trees(self, i):
        t = self.tl.t[i]
        sway = self.e("trees_sway", i)
        jel = self.e("jellyfish", i)
        glow = self.e("jelly_glow", i)
        ground = self.floor_top + 4
        pal_name = self.sec_look[self.tl.section_idx[i]]["palette"]
        lay = self.layer
        lay.fill((0, 0, 0, 0))
        for k, tr in enumerate(self.trees):
            x, h, w = tr["x"], tr["h"], tr["w"]
            top = ground - h
            pygame.draw.rect(self.surf, (70, 46, 26), (x - 3, top + 10, 6, h - 10))
            pygame.draw.rect(self.surf, (50, 32, 18), (x - 3, top + 10, 2, h - 10))
            dx = int(round(math.sin(t * 1.3 + k) * (1 + 2.5 * sway)))
            leaves = self._leaves(tr, pal_name)
            self.surf.blit(leaves, (x - w // 2 + dx, top - 10))
            for j in tr["jelly"]:
                ax = x + j["dx"] + dx
                ay = top + 18
                L = j["len"] + int(2 * math.sin(t * 1.7 + j["ph"] * 6))
                pygame.draw.line(self.surf, (180, 200, 180), (ax, ay), (ax, ay + L))
                hue = (j["hue"] + t * 0.03 + 0.15 * self.tl.bar_idx[i] * 0.0) % 1.0
                col = pygame.Color(0)
                col.hsva = (hue * 360, 70, 100, 100)
                sz = j["size"] * (0.8 + 0.5 * jel)
                bx, by = ax, ay + L
                a = int(110 + 120 * glow)
                rect = pygame.Rect(int(bx - sz), int(by - sz * 0.7), int(sz * 2), int(sz * 1.4))
                pygame.draw.ellipse(lay, (col.r, col.g, col.b, a), rect)
                pygame.draw.rect(lay, (0, 0, 0, 0), (rect.x, rect.centery, rect.w, rect.h))
                pygame.draw.line(lay, (255, 255, 255, a), (rect.x + 2, rect.centery - 1), (rect.right - 3, rect.centery - 1))
                for tt in range(4):
                    tx = bx - sz * 0.6 + tt * sz * 0.4
                    pts = [(tx + math.sin(t * 4 + tt + q * 0.9 + j["ph"] * 5) * (1 + glow * 1.5), by + q * 2)
                           for q in range(int(4 + 3 * jel) + 1)]
                    pygame.draw.lines(lay, (col.r, col.g, col.b, int(a * 0.8)), False, pts)
        self.surf.blit(lay, (0, 0))

    def draw_lasers(self, i):
        look = self.sec_look[self.tl.section_idx[i]]
        if self.tl.section_energy[i] < float(get_path(self.cfg, "elements.lasers.min_section_energy", 0.45)):
            return
        v = self.e("lasers", i)
        if v < 0.15:
            return
        t = self.tl.t[i]
        acc = self.accents(i)
        lay = self.layer
        lay.fill((0, 0, 0, 0))
        ox, oy = self.W // 2, self.floor_top - 40
        r = np.random.default_rng(look["laser_seed"] + int(self.tl.bar_idx[i]))
        n = 6
        for k in range(n):
            a = -math.pi / 2 + math.sin(t * (1.1 + k * 0.17) + r.random() * 6) * 1.2
            L = self.W
            ex, ey = ox + math.cos(a) * L, oy + math.sin(a) * L
            c = acc[(k + self.tl.beat_idx[i]) % len(acc)]
            pygame.draw.line(lay, (*c, int(200 * min(1, v))), (ox, oy), (ex, ey), 1)
        self.surf.blit(lay, (0, 0))

    def draw_floor(self, i):
        look = self.sec_look[self.tl.section_idx[i]]
        style = look["floor"]
        s = self.surf
        acc = self.accents(i)
        dark = by_luma(self.pal(i))[0]
        top = self.floor_top
        H = self.H
        vx = self.W / 2
        be = self.e("floor_pulse", i)
        bi = int(self.tl.beat_idx[i])
        pygame.draw.rect(s, mix(dark, (0, 0, 0), 0.5), (0, top, self.W, H - top))
        rows = 7
        cols = 14
        ys = [top + (H - top) * ((r / rows) ** 1.6) for r in range(rows + 1)]

        def xat(col, y):
            spread = 0.35 + 0.65 * (y - top) / (H - top)
            return vx + (col / cols - 0.5) * self.W * 2.0 * spread
        r = np.random.default_rng(bi & 0xFFFFFF)
        lit = r.random((rows, cols)) < 0.35
        spectrum = [self.tl.env[b][i] for b in ("sub", "bass", "lowmid", "highmid", "high") if b in self.tl.env]
        for ry in range(rows):
            y0, y1 = ys[ry], ys[ry + 1]
            for cx in range(cols):
                quad = [(xat(cx, y0), y0), (xat(cx + 1, y0), y0), (xat(cx + 1, y1), y1), (xat(cx, y1), y1)]
                if style == "checker":
                    base = (35, 35, 45) if (cx + ry) % 2 else (15, 15, 22)
                    c = mix(base, acc[(cx + ry + bi) % len(acc)], be * 0.95) if lit[ry, cx] else base
                elif style == "tiles":
                    # each column is a spectrum bar: saturday-night lightfloor
                    band = spectrum[cx * len(spectrum) // cols] if spectrum else 0
                    on = (rows - ry) / rows < band + 0.15
                    c = mix((12, 12, 18), acc[cx % len(acc)], (0.25 + 0.75 * be) if on else 0.05)
                else:  # grid
                    c = (8, 8, 14)
                pygame.draw.polygon(s, c, quad)
                if style == "grid":
                    pygame.draw.polygon(s, mix((10, 10, 20), acc[bi % len(acc)], 0.35 + 0.65 * be), quad, 1)
        if style == "grid":
            off = (self.tl.beat_phase[i])
            for k in range(rows):
                y = top + (H - top) * (((k + off) / rows) ** 1.6)
                pygame.draw.line(s, mix((10, 10, 20), acc[0], 0.5 + 0.5 * be), (0, y), (self.W, y))

    def draw_stage(self, i):
        t = self.tl.t[i]
        s = self.surf
        cx = self.W // 2
        base_y = self.floor_top + 8
        sub = self.e("speakers", i)
        # speaker stacks
        for side in (-1, 1):
            x = cx + side * 96 - 14
            for k, (w, h) in enumerate([(28, 26), (28, 20)]):
                y = base_y - 26 - k * 20 - (0 if k == 0 else 6)
                pygame.draw.rect(s, (18, 18, 20), (x, y, w, h))
                pygame.draw.rect(s, (40, 40, 44), (x, y, w, h), 1)
                cr = (8 if k == 0 else 6) + int(round(2 * sub))
                pygame.draw.circle(s, (60, 60, 64), (x + w // 2, y + h // 2), cr)
                pygame.draw.circle(s, (8, 8, 8), (x + w // 2, y + h // 2), max(2, cr // 2))
        # car
        car = self.car
        jitter = int(round(self.e("speakers", i) * self.tl.beat_env[i] * 1.2))
        cxl = cx - car.get_width() // 2
        cyl = base_y - car.get_height() + 2 - jitter
        # flames and smoke from the engine bay
        if get_path(self.cfg, "elements.car_stage.flames", True):
            fl = self.e("flames", i)
            for k in range(7):
                fx = cxl + 124 + k * 3
                fh = 3 + int((4 + 7 * fl) * (0.5 + 0.5 * math.sin(t * 17 + k * 2.1)))
                for q in range(fh):
                    c = mix((255, 240, 80), (255, 40, 0), q / max(fh, 1))
                    s.set_at((fx + (q % 2), cyl + 24 - q), c)
                    s.set_at((fx + 1, cyl + 24 - q), c)
        if get_path(self.cfg, "elements.car_stage.smoke", True):
            lay = self.layer
            lay.fill((0, 0, 0, 0))
            for k in range(10):
                life = (t * 0.35 + k / 10) % 1.0
                sx = cxl + 128 + math.sin(t + k) * 4 + life * 18
                sy = cyl + 20 - life * 70
                pygame.draw.circle(lay, (90, 90, 95, int(90 * (1 - life))), (int(sx), int(sy)), int(2 + life * 7))
            s.blit(lay, (0, 0))
        s.blit(car, (cxl, cyl))
        # DJ table on the roof: planks, decks, mixer with band meters
        roof_y = cyl + 8
        dj = self.el.get("dj", {}).get("enabled", True)
        if dj:
            arms = 0
            if self.tl.section_energy[i] > 0.5 and self.tl.bar_env[i] > 0.35 and (self.tl.bar_idx[i] % 2 == 0):
                arms = 2 if self.tl.section_energy[i] > 0.7 else 1
            nod = 1 if self.tl.beat_phase[i] < 0.3 else 0
            f = self.dj_frames[(arms, nod)]
            s.blit(f, (cx - f.get_width() // 2, roof_y - f.get_height() + 4))
        pygame.draw.rect(s, (95, 70, 40), (cx - 30, roof_y, 60, 4))
        pygame.draw.rect(s, (60, 44, 26), (cx - 30, roof_y + 3, 60, 1))
        spin = t * (self.tl.tempo / 60) * math.pi * 0.66
        for dx in (-19, 19):
            pygame.draw.circle(s, (25, 25, 25), (cx + dx, roof_y - 1), 7)
            pygame.draw.circle(s, (60, 60, 60), (cx + dx, roof_y - 1), 7, 1)
            ex = cx + dx + int(round(math.cos(spin + dx) * 5))
            ey = roof_y - 1 + int(round(math.sin(spin + dx) * 2))
            s.set_at((ex, ey), (255, 255, 255))
        # mixer VU: one LED column per band (direct, measurable band read-out)
        names = [b for b in ("sub", "bass", "lowmid", "highmid", "high") if b in self.tl.env]
        for k, b in enumerate(names):
            v = self.tl.env[b][i]
            for q in range(5):
                on = v * 5 > q + 0.3
                c = [(0, 255, 60), (0, 255, 60), (255, 230, 0), (255, 120, 0), (255, 0, 40)][q]
                s.set_at((cx - 5 + k * 2, roof_y - 2 - q), c if on else (30, 30, 30))

    def draw_crowd(self, i):
        t = self.tl.t[i]
        bounce = self.e("crowd_bounce", i)
        arms_e = self.e("crowd_arms", i)
        ph = self.tl.beat_phase[i]
        bi = int(self.tl.beat_idx[i])
        energy = float(self.tl.section_energy[i])
        dj_up = self.tl.section_energy[i] > 0.5 and self.tl.bar_env[i] > 0.35 and (self.tl.bar_idx[i] % 2 == 0)
        for k, c in enumerate(self.crowd):
            ch = c["char"]
            sp = ch.spec
            p = (ph + sp.phase * 0.15) % 1.0
            amp = (3 + 5 * energy) * ch.scale
            if sp.dance == "jump":
                off = -amp * 1.4 * bounce * math.sin(math.pi * p)
            elif sp.dance == "sway":
                off = -amp * 0.5 * bounce * abs(math.sin(math.pi * p))
            else:
                off = -amp * bounce * (1 - p) ** 2
            dx = 0
            if sp.dance == "sway":
                dx = int(round(math.sin(t * math.pi * self.tl.tempo / 120 + sp.phase * 6) * 2 * ch.scale))
            # arms: follow the DJ when they call it, otherwise the high-mids
            h = (k * 2654435761 + bi * 40503) & 0xFFFF
            if dj_up and (h % 3 != 0):
                arms = 1
            elif arms_e > 0.55 and h % 4 == 0:
                arms = 1
            elif sp.dance == "pump":
                arms = 3 if (bi % 2) else 0
            elif sp.dance == "robot":
                arms = [0, 2, 3, 2][bi % 4]
            else:
                arms = 2 if (arms_e > 0.4 and h % 5 == 1) else 0
            legs = 1 if off < -amp * 0.6 else 0
            f = ch.frame(arms, legs)
            x = c["x"] - f.get_width() // 2 + dx
            y = c["y"] - f.get_height() + int(round(off))
            # soft shadow
            pygame.draw.ellipse(self.surf, (5, 5, 8), (c["x"] - 5 * ch.scale, c["y"] - 2, 10 * ch.scale, 3))
            self.surf.blit(f, (x, y))

    def draw_scroller(self, i):
        t = self.tl.t[i]
        s = self.surf
        y0 = self.H - 16
        strip = pygame.Surface((self.W, 16), pygame.SRCALPHA)
        strip.fill((0, 0, 0, 140))
        s.blit(strip, (0, y0))
        tw = self.scroll_surf.get_width()
        speed = 55.0
        off = (t * speed) % tw
        acc = self.accents(i)
        # sine scroller: blit 4px columns with a vertical wave
        col_w = 4
        amp = 2 + 2 * self.tl.beat_env[i]
        for x in range(0, self.W, col_w):
            sx = int((x + off) % tw)
            w = min(col_w, tw - sx)
            yy = y0 + 2 + int(round(math.sin(x * 0.05 + t * 4) * amp))
            s.blit(self.scroll_surf, (x, yy), (sx, 0, w, 12))
        tint = pygame.Surface((self.W, 16))
        tint.fill(acc[int(t * 2) % len(acc)])
        s.blit(tint, (0, y0), special_flags=pygame.BLEND_RGB_MULT)

    def draw_hud(self, i):
        s = self.surf
        t = self.tl.t[i]
        bi = max(0, int(self.tl.beat_idx[i]) + 1)
        txt = f"1UP {bi:06d}   BPM {int(round(self.tl.tempo))}   STAGE {int(self.tl.section_idx[i]) + 1}"
        s.blit(self.font.render(txt, False, (255, 255, 255)), (6, 4))
        # C64-ish boot box for the first seconds
        if get_path(self.cfg, "elements.hud.boot_text", True) and t < 4.0:
            a = 1.0 if t < 3.0 else 4.0 - t
            box = pygame.Surface((220, 60))
            box.fill((64, 50, 133))
            pygame.draw.rect(box, (120, 105, 196), box.get_rect(), 4)
            lines = ["**** SETRENDER 64 BASIC V2 ****", " 64K RAM SYSTEM  38911 BYTES FREE",
                     "READY.", f'LOAD "{self.title[:14].upper()}",8,1']
            for k, ln in enumerate(lines):
                box.blit(self.font.render(ln, False, (120, 105, 196)), (8, 6 + k * 12))
            if int(t * 3) % 2 == 0:
                pygame.draw.rect(box, (120, 105, 196), (8, 6 + 4 * 12, 6, 8))
            box.set_alpha(int(255 * a))
            s.blit(box, (self.W // 2 - 110, 50))

    def post(self, i):
        glow = float(get_path(self.cfg, "canvas.glow", 0.5))
        s = self.surf
        if glow > 0:
            small = pygame.transform.smoothscale(s, (self.W // 4, self.H // 4))
            arr = pygame.surfarray.pixels3d(small)
            lum = arr.max(axis=2, keepdims=True).astype(np.int16)
            mask = np.clip((lum - 150) * 2, 0, 255) / 255.0
            arr[:] = (arr * mask * glow * (0.7 + 0.6 * self.tl.env["loudness"][i])).clip(0, 255).astype(np.uint8)
            del arr
            small = pygame.transform.gaussian_blur(small, 3)
            s.blit(pygame.transform.smoothscale(small, (self.W, self.H)), (0, 0), special_flags=pygame.BLEND_RGB_ADD)
        # downbeat flash in energetic sections
        fl = self.tl.bar_env[i] * max(0.0, float(self.tl.section_energy[i]) - 0.55) * 60
        if fl > 1:
            s.fill((int(fl),) * 3, special_flags=pygame.BLEND_RGB_ADD)
        # kick shake
        sh = float(get_path(self.cfg, "canvas.shake", 1.5)) * self.e("crowd_bounce", i) * self.tl.beat_env[i]
        if sh >= 0.5:
            bi = int(self.tl.beat_idx[i])
            dx = int(round(sh * (1 if bi % 2 else -1)))
            dy = int(round(sh * (1 if (bi // 2) % 2 else -1)))
            s.scroll(dx, dy)

    # ------------------------------------------------------------------ frame
    def render(self, i: int) -> pygame.Surface:
        self.surf.fill((0, 0, 0))
        en = lambda name: self.el.get(name, {}).get("enabled", True)  # noqa: E731
        if en("sky"):
            self.draw_sky(i)
        if en("n64_shape"):
            self.draw_n64_shape(i)
        if en("lasers"):
            self.draw_lasers(i)
        if en("hills"):
            self.draw_hills(i)
        if en("floor"):
            self.draw_floor(i)
        if en("trees"):
            self.draw_trees(i)
        if en("car_stage"):
            self.draw_stage(i)
        if en("crowd"):
            self.draw_crowd(i)
        self.post(i)
        if en("scroller"):
            self.draw_scroller(i)
        if en("hud"):
            self.draw_hud(i)
        return self.surf
