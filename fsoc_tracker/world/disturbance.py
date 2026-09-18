"""Disturbances, applied in the order they happen in nature (rows 21 to 25).

    1. Atmospheric extinction: contrast and brightness change (haze, fog, rain, low light).
    2. Turbulence: beam wander (the spot's position jitters) and scintillation (its
       brightness flickers). Modelled as first-order Gauss-Markov processes.
    3. PSF broadening: blur.
    4. Platform motion: the whole picture shifts by a slow, patterned drift.
    5. Camera jitter: the whole picture shifts by a fast random amount.
    6. Detector noise: Poisson (shot), Gaussian (read), salt and pepper.

Noise on a 4 megapixel frame every 33 ms is expensive in NumPy, so Gaussian and salt and
pepper noise come from banks of pre-generated planes that are rolled by a random offset each
frame. The statistics are identical; the cost drops by an order of magnitude.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import cv2
import numpy as np

from ..engine.config import DisturbanceConfig


@dataclass
class FrameDisturbance:
    """What the disturbance stage did this frame. Logged for truth bookkeeping."""
    wander_dx: float = 0.0        # beam wander applied to each beacon, px
    wander_dy: float = 0.0
    scint: float = 1.0            # intensity multiplier
    platform_dx: float = 0.0      # picture shift from platform motion, px
    platform_dy: float = 0.0
    jitter_dx: float = 0.0        # picture shift from vibration, px
    jitter_dy: float = 0.0

    @property
    def shift(self) -> tuple[float, float]:
        return self.platform_dx + self.jitter_dx, self.platform_dy + self.jitter_dy


class DisturbanceModel:
    def __init__(self, cfg: DisturbanceConfig, shape: tuple[int, int], rng: np.random.Generator, dt: float):
        self.cfg = cfg
        self.h, self.w = shape
        self.rng = rng
        self.dt = dt
        self.t = 0.0
        # Gauss-Markov states for wander and scintillation
        self._wx = self._wy = 0.0
        self._sc = 0.0
        self._rand_walk = np.zeros(2)
        self._rand_vel = np.zeros(2)
        self._phase = rng.uniform(0, 2 * math.pi)
        # noise banks
        self._gauss_bank = None
        self._sp_bank = None
        if cfg.gaussian_sigma > 0 or cfg.poisson:
            self._gauss_bank = rng.standard_normal((4, self.h, self.w)).astype(np.float32)
        if cfg.salt_pepper_frac > 0:
            u = rng.random((4, self.h, self.w), dtype=np.float32)
            self._sp_bank = np.zeros((4, self.h, self.w), np.int8)
            half = cfg.salt_pepper_frac / 2
            self._sp_bank[u < half] = -1
            self._sp_bank[u > 1 - half] = 1

    # ------------------------------------------------------------- per frame
    def step(self) -> FrameDisturbance:
        """Advance the stochastic states one frame and return this frame's disturbance."""
        c = self.cfg
        self.t += self.dt
        d = FrameDisturbance()
        # 2. turbulence: correlated random processes (Greenwood-like corner ~ 6 Hz)
        if c.turbulence > 0:
            tau = 0.17
            a = math.exp(-self.dt / tau)
            s_pos = 2.5 * c.turbulence
            s_int = 0.25 * c.turbulence
            self._wx = a * self._wx + math.sqrt(1 - a * a) * s_pos * self.rng.standard_normal()
            self._wy = a * self._wy + math.sqrt(1 - a * a) * s_pos * self.rng.standard_normal()
            self._sc = a * self._sc + math.sqrt(1 - a * a) * s_int * self.rng.standard_normal()
            d.wander_dx, d.wander_dy = self._wx, self._wy
            d.scint = float(np.clip(math.exp(self._sc - s_int ** 2 / 2), 0.2, 1.8))
        # 4. platform motion
        if c.platform_motion != "none" and c.platform_px_frame > 0:
            d.platform_dx, d.platform_dy = self._platform()
        # 5. jitter
        if c.jitter_px > 0:
            d.jitter_dx = float(self.rng.uniform(-c.jitter_px, c.jitter_px))
            d.jitter_dy = float(self.rng.uniform(-c.jitter_px, c.jitter_px))
        return d

    def _platform(self) -> tuple[float, float]:
        c = self.cfg
        v = c.platform_px_frame              # peak px per frame
        f = 1.0 / self.dt                    # frames per second
        w = 2 * math.pi / c.platform_period_s
        t = self.t
        # A sustained shift of v px/frame would leave the screen in seconds, so every
        # pattern is a bounded sway: amplitude limited to 30% of the screen, and the
        # angular frequency raised if needed so that the PEAK speed is exactly v px/frame.
        amp_max = 0.2 * min(self.w, self.h)
        amp = v / (w * self.dt)
        if amp > amp_max:
            amp = amp_max
            w = v / (amp * self.dt)
        if c.platform_motion == "linear":
            # back-and-forth sway along a fixed heading (the mandatory case)
            s = amp * math.sin(w * t)
            return s * math.cos(self._phase), s * math.sin(self._phase)
        if c.platform_motion == "circular":
            return amp * math.cos(w * t), amp * math.sin(w * t)
        if c.platform_motion == "figure8":
            return amp * math.sin(w * t), 0.5 * amp * math.sin(2 * w * t)
        if c.platform_motion == "spiral":
            r = amp * (0.2 + 0.8 * ((t / (3 * c.platform_period_s)) % 1.0))
            return r * math.cos(w * t), r * math.sin(w * t)
        # random: bounded smooth walk
        self._rand_vel = 0.9 * self._rand_vel + 0.1 * v * self.rng.standard_normal(2)
        sp = np.linalg.norm(self._rand_vel)
        if sp > v:
            self._rand_vel *= v / sp
        self._rand_walk = np.clip(self._rand_walk + self._rand_vel, -0.15 * self.w, 0.15 * self.w)
        return float(self._rand_walk[0]), float(self._rand_walk[1])

    # ------------------------------------------------------------- imaging
    def apply_image(self, img: np.ndarray, beacon_boxes: list[tuple[int, int, int, int]], d: FrameDisturbance) -> np.ndarray:
        """Apply the image-domain stages to a uint8 frame. Beacon boxes let the blur run on
        small regions only, since blurring a smooth background changes nothing."""
        c = self.cfg
        out = img
        # 1. extinction: contrast and brightness. Fog also lifts the black level (airlight).
        if c.contrast != 1.0 or c.brightness != 0.0:
            out = cv2.convertScaleAbs(out, alpha=c.contrast, beta=c.brightness)
        # 3. PSF broadening around beacons
        if c.blur_sigma > 0:
            pad = int(4 * c.blur_sigma) + 4
            for (x0, y0, w, h) in beacon_boxes:
                xa, ya = max(x0 - pad, 0), max(y0 - pad, 0)
                xb, yb = min(x0 + w + pad, self.w), min(y0 + h + pad, self.h)
                if xb > xa and yb > ya:
                    out[ya:yb, xa:xb] = cv2.GaussianBlur(out[ya:yb, xa:xb], (0, 0), c.blur_sigma)
        # 4+5. picture shift
        sx, sy = d.shift
        if abs(sx) > 0.05 or abs(sy) > 0.05:
            M = np.array([[1, 0, sx], [0, 1, sy]], np.float32)
            out = cv2.warpAffine(out, M, (self.w, self.h), flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_CONSTANT, borderValue=int(np.median(out[::16, ::16])))
        # 6. detector noise
        if self._gauss_bank is not None:
            k = int(self.rng.integers(0, self._gauss_bank.shape[0]))
            oy, ox = int(self.rng.integers(0, self.h)), int(self.rng.integers(0, self.w))
            plane = np.roll(self._gauss_bank[k], (oy, ox), axis=(0, 1))
            f = out.astype(np.float32)
            if c.poisson:
                # shot noise: std grows with sqrt of signal; scale so that a 235 peak
                # has roughly sigma 6
                f += plane * np.sqrt(np.maximum(f, 1.0)) * 0.4
            if c.gaussian_sigma > 0:
                f += plane * c.gaussian_sigma
            out = np.clip(f, 0, 255).astype(np.uint8)
        if self._sp_bank is not None:
            k = int(self.rng.integers(0, self._sp_bank.shape[0]))
            oy, ox = int(self.rng.integers(0, self.h)), int(self.rng.integers(0, self.w))
            plane = np.roll(self._sp_bank[k], (oy, ox), axis=(0, 1))
            out = out.copy()
            out[plane == 1] = 255
            out[plane == -1] = 0
        return out
