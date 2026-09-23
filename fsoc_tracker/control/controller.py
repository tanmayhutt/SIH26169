"""Turns "the beacon is here, heading there" into a pan/tilt rate command.

    u = k_ff * target_rate  +  PID(angular error)

with a deadband, integrator clamping under saturation, and latency compensation (the
error is taken at the predicted position one command latency ahead). Rate and acceleration
saturation live in the gimbal model; the controller only reports when it asked for more
than the gimbal can give.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..engine.config import TrackerConfig
from ..world.camera import Gimbal, RateCommand
from .tracker import Mode, TrackOutput


@dataclass
class ControlState:
    int_pan: float = 0.0
    int_tilt: float = 0.0
    prev_e_pan: float = 0.0
    prev_e_tilt: float = 0.0
    search_phase: float = 0.0
    waypoints: list = field(default_factory=list)
    wp_index: int = 0


def _square_spiral(dx: float, dy: float, pan_lim: float, tilt_lim: float) -> list[tuple[float, float]]:
    """Centre first, then rings of cells at growing Chebyshev distance, clipped to the pose
    limits. Visits every window-sized cell of the screen once per lap."""
    pts = [(0.0, 0.0)]
    nx, ny = int(np.ceil(pan_lim / dx)), int(np.ceil(tilt_lim / dy))
    for k in range(1, max(nx, ny) + 1):
        ring = []
        for i in range(-k, k + 1):
            ring.append((i, -k)); ring.append((i, k))
        for j in range(-k + 1, k):
            ring.append((-k, j)); ring.append((k, j))
        # walk the ring in angular order so consecutive waypoints are neighbours
        ring = sorted(set(ring), key=lambda c: np.arctan2(c[1], c[0]))
        for i, j in ring:
            p = float(np.clip(i * dx, -pan_lim, pan_lim)); t = float(np.clip(j * dy, -tilt_lim, tilt_lim))
            if not pts or (abs(pts[-1][0] - p) > 1e-6 or abs(pts[-1][1] - t) > 1e-6):
                pts.append((p, t))
    return pts


class Controller:
    TURN_MAX = 0.1    # rad: the largest turn of the path over the velocity lead (small-angle limit)

    def __init__(self, cfg: TrackerConfig, gimbal: Gimbal, dt: float):
        self.cfg = cfg
        self.g = gimbal
        self.dt = dt
        self.s = ControlState()

    def reset(self):
        self.s = ControlState()

    def step(self, out: TrackOutput, ego_dx: float, ego_dy: float, window_only: bool) -> RateCommand:
        cfg, g, s = self.cfg, self.g, self.s
        cx, cy = g.window_centre_px()
        if out.mode == Mode.SEARCH or out.prediction is None:
            return self._search(window_only)
        # target position to aim at: lead by the command latency
        lead = (g.cfg.command_latency_frames + 0.5) * self.dt
        tx, ty = out.prediction if out.mode != Mode.TRACK else out.estimate
        vx, vy = out.velocity
        ax, ay = out.acceleration
        # lead the target through the latency using velocity and acceleration, and
        # feed forward the velocity it will have then
        tx, ty = tx + vx * lead + 0.5 * ax * lead ** 2, ty + vy * lead + 0.5 * ay * lead ** 2
        # the estimated velocity is itself late by the filter delay; advance it too
        # the estimator's delay is a number of frames, so the compensation set in seconds at
        # the 30 Hz reference scales with the frame rate (a 60 fps video halves it)
        ff_lead = lead + cfg.estimator_lag_s * (30.0 / max(g.cfg.update_rate_hz, 1.0))
        # extrapolating velocity along a straight line is only valid while the path turns
        # little over the lead: cap the lead so the path turns by at most TURN_MAX rad. Slow or
        # gently curving targets keep the full lead; a fast, tightly turning one (a circle
        # near the camera's rate limit) gets a short one instead of being led off its path
        sp2 = vx * vx + vy * vy
        if sp2 > 1.0:
            omega = abs(vx * ay - vy * ax) / sp2
            if omega > 1e-6:
                ff_lead = min(ff_lead, max(self.TURN_MAX / omega, lead))
        vx, vy = vx + ax * ff_lead, vy + ay * ff_lead
        # the window also moves during the latency; lead it by its current rate so a
        # constant-velocity target is followed with zero steady-state offset
        wvx, wvy = g.deg_to_px(g.pan_rate, g.tilt_rate)
        cx, cy = cx + wvx * lead, cy + wvy * lead
        e_pan, e_tilt = g.px_to_deg(tx - cx, ty - cy)
        err_px = float(np.hypot(tx - cx, ty - cy))
        if err_px < cfg.deadband_px:
            e_pan = e_tilt = 0.0
            s.int_pan *= 0.9
            s.int_tilt *= 0.9
        # feedforward from target angular rate and measured platform drift
        # The estimator's velocity is measured in picture coordinates, so it already
        # includes platform drift; the ego-motion estimate is used by the tracker to size
        # the measurement noise, not added here (that would count drift twice).
        ff_pan, ff_tilt = g.px_to_deg(vx, vy)
        ego_pan = ego_tilt = 0.0
        d_pan = (e_pan - s.prev_e_pan) / self.dt
        d_tilt = (e_tilt - s.prev_e_tilt) / self.dt
        s.prev_e_pan, s.prev_e_tilt = e_pan, e_tilt
        u_pan = cfg.feedforward * ff_pan + cfg.feedforward * ego_pan + cfg.kp * e_pan + cfg.kd * d_pan + cfg.ki * s.int_pan
        u_tilt = cfg.feedforward * ff_tilt + cfg.feedforward * ego_tilt + cfg.kp * e_tilt + cfg.kd * d_tilt + cfg.ki * s.int_tilt
        # integrator with clamping: do not wind up while saturated
        if abs(u_pan) < g.cfg.max_pan_rate_deg_s:
            s.int_pan = float(np.clip(s.int_pan + e_pan * self.dt, -1.0, 1.0))
        if abs(u_tilt) < g.cfg.max_tilt_rate_deg_s:
            s.int_tilt = float(np.clip(s.int_tilt + e_tilt * self.dt, -1.0, 1.0))
        return RateCommand(float(u_pan), float(u_tilt))

    def _search(self, window_only: bool) -> RateCommand:
        """With the full picture observed, SEARCH just holds still; detection will find the
        beacon. In hard mode fly an expanding square spiral of window-sized cells (80%
        overlap) at the rate limit, then repeat."""
        if not window_only:
            self.s.int_pan = self.s.int_tilt = 0.0
            return RateCommand(0.0, 0.0)
        g = self.g
        if not self.s.waypoints:
            self.s.waypoints = _square_spiral(0.8 * g.cfg.fov_w_deg, 0.8 * g.cfg.fov_h_deg, g.pan_limit, g.tilt_limit)
            self.s.wp_index = 0
        tp, tt = self.s.waypoints[self.s.wp_index]
        e_pan, e_tilt = tp - g.pan_deg, tt - g.tilt_deg
        if abs(e_pan) < 0.25 and abs(e_tilt) < 0.25:
            self.s.wp_index = (self.s.wp_index + 1) % len(self.s.waypoints)
            tp, tt = self.s.waypoints[self.s.wp_index]
            e_pan, e_tilt = tp - g.pan_deg, tt - g.tilt_deg
        # head for the waypoint at the rate limit; both axes arrive together
        dist = max(np.hypot(e_pan, e_tilt), 1e-6)
        vmax = min(g.cfg.max_pan_rate_deg_s, g.cfg.max_tilt_rate_deg_s)
        return RateCommand(float(e_pan / dist * vmax), float(e_tilt / dist * vmax))

    def reset_search(self):
        self.s.waypoints = []
