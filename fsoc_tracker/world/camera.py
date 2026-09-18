"""The virtual pan-tilt camera and its gimbal.

Pose is (pan, tilt) in degrees measured from the screen centre. One screen pixel equals one
camera pixel, so a pose converts to the window centre in screen pixels through the IFOV
(field of view divided by resolution). Rows 13 to 15 give the rate limits; the acceleration
limit and command latency are our model of a real gimbal.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from collections import deque

import numpy as np

from ..engine.config import CameraConfig


@dataclass
class RateCommand:
    pan_rate: float = 0.0     # deg/s, positive = window moves right
    tilt_rate: float = 0.0    # deg/s, positive = window moves down
    saturated_pan: bool = False
    saturated_tilt: bool = False


@dataclass
class Gimbal:
    cfg: CameraConfig
    screen_w: int
    screen_h: int
    pan_deg: float = 0.0
    tilt_deg: float = 0.0
    pan_rate: float = 0.0
    tilt_rate: float = 0.0
    _queue: deque = field(default_factory=deque)

    def __post_init__(self):
        self.ifov = self.cfg.ifov_deg
        # Pose limits: the window centre can reach any screen pixel (the window may hang
        # over the edge; those pixels are dark). The screen is the field of regard.
        self.pan_limit = self.screen_w / 2 * self.ifov
        self.tilt_limit = self.screen_h / 2 * self.ifov
        for _ in range(self.cfg.command_latency_frames):
            self._queue.append(RateCommand())

    # -------------------------------------------------------------- control
    def apply(self, cmd: RateCommand, dt: float) -> RateCommand:
        """Queue the command (latency), then integrate the oldest one with rate and
        acceleration saturation. Returns the command that actually acted this frame."""
        self._queue.append(cmd)
        act = self._queue.popleft()
        a_max = self.cfg.max_accel_deg_s2 * dt
        tp = float(np.clip(act.pan_rate, -self.cfg.max_pan_rate_deg_s, self.cfg.max_pan_rate_deg_s))
        tt = float(np.clip(act.tilt_rate, -self.cfg.max_tilt_rate_deg_s, self.cfg.max_tilt_rate_deg_s))
        act.saturated_pan = abs(act.pan_rate) > self.cfg.max_pan_rate_deg_s
        act.saturated_tilt = abs(act.tilt_rate) > self.cfg.max_tilt_rate_deg_s
        self.pan_rate += float(np.clip(tp - self.pan_rate, -a_max, a_max))
        self.tilt_rate += float(np.clip(tt - self.tilt_rate, -a_max, a_max))
        self.pan_deg = float(np.clip(self.pan_deg + self.pan_rate * dt, -self.pan_limit, self.pan_limit))
        self.tilt_deg = float(np.clip(self.tilt_deg + self.tilt_rate * dt, -self.tilt_limit, self.tilt_limit))
        return act

    # ------------------------------------------------------------- geometry
    def window_centre_px(self, platform_dx: float = 0.0, platform_dy: float = 0.0) -> tuple[float, float]:
        """Screen-pixel centre of the camera window, including platform disturbance."""
        cx = self.screen_w / 2 + self.pan_deg / self.ifov + platform_dx
        cy = self.screen_h / 2 + self.tilt_deg / self.ifov + platform_dy
        return cx, cy

    def window_rect(self, platform_dx: float = 0.0, platform_dy: float = 0.0) -> tuple[int, int, int, int]:
        cx, cy = self.window_centre_px(platform_dx, platform_dy)
        x0 = int(round(cx - self.cfg.width / 2))
        y0 = int(round(cy - self.cfg.height / 2))
        return x0, y0, self.cfg.width, self.cfg.height

    def px_to_deg(self, dx_px: float, dy_px: float) -> tuple[float, float]:
        return dx_px * self.ifov, dy_px * self.ifov

    def deg_to_px(self, dpan: float, dtilt: float) -> tuple[float, float]:
        return dpan / self.ifov, dtilt / self.ifov
