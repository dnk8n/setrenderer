"""Thin-film interference colour: what a soap film (or the oxide skin on bismuth) reflects at each
thickness, worked out from the physics rather than painted. The film's reflectance at every visible
wavelength (Airy's formula for a thin layer) is lit by an illuminant and integrated against the CIE 1931
colour-matching functions, then converted to linear sRGB. The result is a lookup table the shader indexes
by optical thickness, which is where the endless swirling colours of soap and water come from."""
from __future__ import annotations

import numpy as np

N = 1024                       # table entries
MAX_NM = 1600.0                # thickness range covered (nm); higher orders wash out to pastel anyway
LAMBDA = np.arange(380.0, 781.0, 5.0)

_XYZ_TO_RGB = np.array([[3.2404542, -1.5371385, -0.4985314],
                        [-0.9692660, 1.8760108, 0.0415560],
                        [0.0556434, -0.2040259, 1.0572252]])


def _g(x, mu, s1, s2):
    s = np.where(x < mu, s1, s2)
    return np.exp(-0.5 * ((x - mu) / s) ** 2)


def cmf(lam: np.ndarray) -> np.ndarray:
    """CIE 1931 2-degree colour-matching functions, multi-lobe Gaussian fit (Wyman, Sloan & Shirley 2013)."""
    x = 1.056 * _g(lam, 599.8, 37.9, 31.0) + 0.362 * _g(lam, 442.0, 16.0, 26.7) - 0.065 * _g(lam, 501.1, 20.4, 26.2)
    y = 0.821 * _g(lam, 568.8, 46.9, 40.5) + 0.286 * _g(lam, 530.9, 16.3, 31.1)
    z = 1.217 * _g(lam, 437.0, 11.8, 36.0) + 0.681 * _g(lam, 459.0, 26.0, 13.8)
    return np.stack([x, y, z], 1)


def blackbody(lam_nm: np.ndarray, kelvin: float) -> np.ndarray:
    lam = lam_nm * 1e-9
    h, c, k = 6.62607015e-34, 2.99792458e8, 1.380649e-23
    b = 1.0 / (lam ** 5 * (np.exp(h * c / (lam * k * kelvin)) - 1.0))
    return b / b.max()


def reflectance(d_nm: np.ndarray, lam: np.ndarray, n_film: complex, n_back: complex) -> np.ndarray:
    """Airy reflectance of a film of thickness d between air and a backing medium, at normal incidence
    (the shader folds the viewing angle into the thickness it looks up)."""
    r12 = (1.0 - n_film) / (1.0 + n_film)
    r23 = (n_film - n_back) / (n_film + n_back)
    delta = 4.0 * np.pi * n_film.real * d_nm[:, None] / lam[None, :]
    e = np.exp(1j * delta)
    r = (r12 + r23 * e) / (1.0 + r12 * r23 * e)
    return np.abs(r) ** 2


def table(kelvin: float = 6500.0, tint: tuple[float, float, float] = (1.0, 1.0, 1.0)) -> np.ndarray:
    """(2, N, 4) float32: row 0 a soap film in air, row 1 an oxide skin on bismuth. Each row is
    normalised so its brightest entry has luminance 1 (the shader decides how strongly films show)."""
    d = np.linspace(0.0, MAX_NM, N)
    lam = LAMBDA
    illum = blackbody(lam, kelvin)
    m = cmf(lam) * illum[:, None]
    white = m.sum(0)
    rows = []
    for n_film, n_back in ((1.335 + 0j, 1.0 + 0j), (2.45 + 0j, 1.9 + 3.6j)):
        R = reflectance(d, lam, n_film, n_back)
        xyz = R @ m / white[1]
        rgb = np.clip(xyz @ _XYZ_TO_RGB.T, 0.0, None) * np.asarray(tint)
        lum = rgb @ np.array([0.2126, 0.7152, 0.0722])
        rgb = rgb / max(float(lum.max()), 1e-6)
        rows.append(np.concatenate([rgb, lum[:, None] / max(float(lum.max()), 1e-6)], 1))
    return np.stack(rows).astype(np.float32)
