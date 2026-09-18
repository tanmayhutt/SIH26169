"""Beacon kinematics. Positions are in screen pixels, time in seconds.

Row 12 asks for at least straight line, circular, figure of 8 and random, with spiral and
sinusoidal optional. All are implemented as closed-form or integrated paths so that a run
is exactly reproducible from its seed.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..engine.config import TargetConfig


@dataclass
class TargetState:
    x: float
    y: float
    vx: float
    vy: float
    intensity: float
    visible: bool = True


class Target:
    def __init__(self, cfg: TargetConfig, screen_w: int, screen_h: int, rng: np.random.Generator, index: int = 0):
        self.cfg = cfg
        self.w, self.h = screen_w, screen_h
        self.rng = rng
        self.index = index
        margin = 0.12
        if cfg.start == "random":
            self.x0 = rng.uniform(margin * screen_w, (1 - margin) * screen_w)
            self.y0 = rng.uniform(margin * screen_h, (1 - margin) * screen_h)
        elif cfg.start == "centre":
            self.x0, self.y0 = screen_w / 2, screen_h / 2
        else:
            sx, sy = cfg.start.split(",")
            self.x0, self.y0 = float(sx), float(sy)
        self.heading = math.radians(cfg.heading_deg)
        self.phase = rng.uniform(0, 2 * math.pi)
        # random walk state
        self._rx, self._ry = self.x0, self.y0
        self._rvx = cfg.speed_px_s * math.cos(self.heading)
        self._rvy = cfg.speed_px_s * math.sin(self.heading)
        self._t_prev = 0.0
        self._last = TargetState(self.x0, self.y0, 0.0, 0.0, cfg.intensity)

    # ---------------------------------------------------------------- paths
    def state(self, t: float) -> TargetState:
        c = self.cfg
        m = c.motion
        if m == "static":
            x, y, vx, vy = self.x0, self.y0, 0.0, 0.0
        elif m == "line":
            x, y, vx, vy = self._line(t)
        elif m == "circular":
            w = 2 * math.pi / c.period_s
            a = w * t + self.phase
            cx, cy = self._centre_for_radius(c.radius_px)
            x, y = cx + c.radius_px * math.cos(a), cy + c.radius_px * math.sin(a)
            vx, vy = -c.radius_px * w * math.sin(a), c.radius_px * w * math.cos(a)
        elif m == "figure8":
            w = 2 * math.pi / c.period_s
            a = w * t + self.phase
            cx, cy = self._centre_for_radius(c.radius_px)
            x = cx + c.radius_px * math.sin(a)
            y = cy + 0.5 * c.radius_px * math.sin(2 * a)
            vx = c.radius_px * w * math.cos(a)
            vy = c.radius_px * w * math.cos(2 * a)
        elif m == "spiral":
            w = 2 * math.pi / c.period_s
            a = w * t + self.phase
            r = c.radius_px * (0.15 + 0.85 * ((t / (3 * c.period_s)) % 1.0))
            cx, cy = self._centre_for_radius(c.radius_px)
            x, y = cx + r * math.cos(a), cy + r * math.sin(a)
            vx, vy = -r * w * math.sin(a), r * w * math.cos(a)
        elif m == "sinusoidal":
            lx, ly, lvx, lvy = self._line(t)
            w = 2 * math.pi / c.period_s
            amp = c.radius_px * 0.5
            nx, ny = -math.sin(self.heading), math.cos(self.heading)
            s = amp * math.sin(w * t + self.phase)
            ds = amp * w * math.cos(w * t + self.phase)
            x, y = lx + nx * s, ly + ny * s
            vx, vy = lvx + nx * ds, lvy + ny * ds
            x, y = min(max(x, 0.0), self.w - 1.0), min(max(y, 0.0), self.h - 1.0)
        elif m == "random":
            x, y, vx, vy = self._random_walk(t)
        else:
            raise ValueError(f"unknown motion '{m}'")
        inten = c.intensity
        if c.blink_hz > 0:
            inten = c.intensity * (0.55 + 0.45 * (0.5 + 0.5 * math.sin(2 * math.pi * c.blink_hz * t)))
        vis = 0 <= x < self.w and 0 <= y < self.h
        self._last = TargetState(x, y, vx, vy, inten, vis)
        return self._last

    def _centre_for_radius(self, r: float) -> tuple[float, float]:
        cx = min(max(self.x0, r + 20), self.w - r - 20)
        cy = min(max(self.y0, r + 20), self.h - r - 20)
        return cx, cy

    def _line(self, t: float):
        """Straight line at constant speed, turning back at the screen edges. The
        turnaround is rounded over about 0.4 s (a box-averaged triangle wave), because a
        real platform cannot reverse its velocity instantaneously."""
        c = self.cfg
        vx = c.speed_px_s * math.cos(self.heading)
        vy = c.speed_px_s * math.sin(self.heading)
        r = 0.2 * c.speed_px_s                      # half-width of the rounding, in px of path
        x, sx = _smooth_bounce(self.x0 + vx * t, 0, self.w - 1, r * abs(math.cos(self.heading)))
        y, sy = _smooth_bounce(self.y0 + vy * t, 0, self.h - 1, r * abs(math.sin(self.heading)))
        return x, y, vx * sx, vy * sy

    def _random_walk(self, t: float):
        """Smooth random walk: velocity is an Ornstein-Uhlenbeck process, integrated forward.
        Deterministic given the seed and a monotonic call sequence."""
        c = self.cfg
        dt = max(t - self._t_prev, 0.0)
        if dt > 0:
            steps = max(1, int(round(dt / (1 / 60))))
            h = dt / steps
            tau = 3.0
            sigma = c.speed_px_s * 0.8
            for _ in range(steps):
                self._rvx += (-self._rvx / tau) * h + sigma * math.sqrt(2 * h / tau) * self.rng.standard_normal()
                self._rvy += (-self._rvy / tau) * h + sigma * math.sqrt(2 * h / tau) * self.rng.standard_normal()
                sp = math.hypot(self._rvx, self._rvy)
                vmax = c.speed_px_s * 2.0
                if sp > vmax:
                    self._rvx *= vmax / sp
                    self._rvy *= vmax / sp
                self._rx += self._rvx * h
                self._ry += self._rvy * h
                # reflect at edges
                if self._rx < 20 or self._rx > self.w - 20:
                    self._rvx = -self._rvx
                    self._rx = min(max(self._rx, 20), self.w - 20)
                if self._ry < 20 or self._ry > self.h - 20:
                    self._rvy = -self._rvy
                    self._ry = min(max(self._ry, 20), self.h - 20)
            self._t_prev = t
        return self._rx, self._ry, self._rvx, self._rvy


def _smooth_bounce(v: float, lo: float, hi: float, r: float) -> tuple[float, float]:
    """Triangle wave between lo and hi with corners rounded over +/- r, plus the local
    slope sign. Rounding is the box average of the triangle over [v - r, v + r], which
    turns each instantaneous reversal into a parabolic turnaround."""
    if r <= 1e-6:
        p = _bounce(v, lo, hi)
        span = hi - lo
        s = 1.0 if ((v - lo) % (2 * span)) <= span else -1.0
        return p, s
    n = 9
    acc = 0.0
    for k in range(n):
        acc += _bounce(v - r + 2 * r * k / (n - 1), lo, hi)
    p = acc / n
    slope = (_bounce(v + r, lo, hi) - _bounce(v - r, lo, hi)) / (2 * r)
    return p, max(min(slope, 1.0), -1.0)


def _bounce(v: float, lo: float, hi: float) -> float:
    span = hi - lo
    if span <= 0:
        return lo
    p = (v - lo) % (2 * span)
    return lo + (p if p <= span else 2 * span - p)
