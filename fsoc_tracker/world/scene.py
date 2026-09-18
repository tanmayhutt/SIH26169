"""Static background of the scene (row 1 and 2)."""
from __future__ import annotations

import numpy as np
import cv2

from ..engine.config import ScreenConfig


def make_background(cfg: ScreenConfig, rng: np.random.Generator) -> np.ndarray:
    h, w = cfg.height, cfg.width
    lvl = cfg.background_level
    if cfg.background == "flat":
        bg = np.full((h, w), lvl, np.uint8)
    elif cfg.background == "gradient":
        col = np.linspace(lvl * 0.4, lvl * 1.8, h, dtype=np.float32)
        bg = np.clip(np.repeat(col[:, None], w, axis=1), 0, 255).astype(np.uint8)
    elif cfg.background == "terrain":
        # low-frequency procedural texture: sum of a few blurred noise octaves
        acc = np.zeros((h, w), np.float32)
        for s, amp in ((64, 1.0), (32, 0.5), (16, 0.25)):
            n = rng.random((h // s + 2, w // s + 2), dtype=np.float32)
            n = cv2.resize(n, (w, h), interpolation=cv2.INTER_CUBIC)
            acc += amp * n
        acc = (acc - acc.min()) / (acc.max() - acc.min() + 1e-6)
        bg = np.clip(lvl * 0.5 + acc * lvl * 3.5, 0, 255).astype(np.uint8)
    else:  # starfield
        bg = np.full((h, w), lvl, np.uint8).astype(np.float32)
        n = int(cfg.star_density * h * w)
        xs = rng.integers(0, w, n)
        ys = rng.integers(0, h, n)
        mags = rng.power(3.0, n)             # many faint, few bright
        vals = 22 + 105 * mags            # brightest star ~127, well below a beacon
        bg[ys, xs] = np.maximum(bg[ys, xs], vals)
        # give the brighter stars a small PSF so they look like the beacon's cousins
        bright = mags > 0.93
        for x, y, v in zip(xs[bright], ys[bright], vals[bright]):
            cv2.circle(bg, (int(x), int(y)), 1, float(v), -1, lineType=cv2.LINE_AA)
        bg = cv2.GaussianBlur(bg, (0, 0), 0.7)
        bg = np.clip(bg, 0, 255).astype(np.uint8)
    return bg
