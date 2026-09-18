"""Interacting Multiple Model (IMM) estimator over constant velocity, constant acceleration
and coordinated turn models. State is in picture pixels: [x, y, vx, vy, ax, ay].

The IMM runs all three filters in parallel and blends them by how well each explains the
measurements, so straight, circular, figure of eight and random paths are handled without
retuning. `predict(dt)` gives the position the camera should lead to; `gate()` gives the
Mahalanobis distance used to reject clutter.
"""
from __future__ import annotations

import math

import numpy as np


def _F_cv(dt):
    F = np.eye(6)
    F[0, 2] = F[1, 3] = dt
    return F


def _F_ca(dt):
    F = _F_cv(dt)
    F[0, 4] = F[1, 5] = 0.5 * dt * dt
    F[2, 4] = F[3, 5] = dt
    return F


def _F_ct(dt, omega):
    """Coordinated turn on velocity with rate omega (rad/s); acceleration states damped."""
    F = np.eye(6)
    if abs(omega) < 1e-6:
        return _F_cv(dt)
    s, c = math.sin(omega * dt), math.cos(omega * dt)
    F[0, 2] = s / omega
    F[0, 3] = -(1 - c) / omega
    F[1, 2] = (1 - c) / omega
    F[1, 3] = s / omega
    F[2, 2] = c
    F[2, 3] = -s
    F[3, 2] = s
    F[3, 3] = c
    F[4, 4] = F[5, 5] = 0.5
    return F


class _KF:
    def __init__(self, q: float, damp_acc: bool):
        self.x = np.zeros(6)
        self.P = np.eye(6) * 50.0
        self.q = q
        self.damp_acc = damp_acc
        self.H = np.zeros((2, 6))
        self.H[0, 0] = self.H[1, 1] = 1.0
        self.lik = 1.0

    def predict(self, F, dt):
        G = np.array([[0.5 * dt * dt, 0], [0, 0.5 * dt * dt], [dt, 0], [0, dt], [1, 0], [0, 1]])
        Q = G @ G.T * self.q
        if self.damp_acc:
            self.x[4:] *= 0.0
        self.x = F @ self.x
        self.P = F @ self.P @ F.T + Q

    def update(self, z, R):
        S = self.H @ self.P @ self.H.T + R
        y = z - self.H @ self.x
        Sinv = np.linalg.inv(S)
        K = self.P @ self.H.T @ Sinv
        self.x = self.x + K @ y
        self.P = (np.eye(6) - K @ self.H) @ self.P
        d2 = float(y @ Sinv @ y)
        self.lik = math.exp(-0.5 * d2) / (2 * math.pi * math.sqrt(max(np.linalg.det(S), 1e-9)))
        return d2


class IMM:
    def __init__(self, dt: float, meas_sigma_px: float = 1.2):
        self.dt = dt
        self.R = np.eye(2) * meas_sigma_px ** 2
        # q is the variance of a white acceleration (px^2/s^4): sqrt(q) = 45, 250 and 90
        # px/s^2. Beacon paths in the PS reach ~100 px/s^2 and platform sway ~600 px/s^2.
        self.models = [_KF(q=1000.0, damp_acc=True), _KF(q=40000.0, damp_acc=False), _KF(q=5000.0, damp_acc=True)]
        self.names = ["cv", "ca", "ct"]
        self.mu = np.array([0.6, 0.2, 0.2])
        self.Pi = np.array([[0.94, 0.03, 0.03], [0.05, 0.90, 0.05], [0.05, 0.05, 0.90]])
        self.omega = 0.0
        self.last_sigma = 1.2
        self.initialised = False
        self.x = np.zeros(6)
        self.P = np.eye(6) * 50.0

    # ------------------------------------------------------------- lifecycle
    def reset(self, x: float, y: float):
        for m in self.models:
            m.x = np.array([x, y, 0, 0, 0, 0], float)
            m.P = np.diag([4.0, 4.0, 400.0, 400.0, 100.0, 100.0])
        self.mu = np.array([0.6, 0.2, 0.2])
        self.initialised = True
        self._combine()

    def _mix(self):
        cbar = self.Pi.T @ self.mu
        cbar = np.maximum(cbar, 1e-9)
        w = (self.Pi * self.mu[:, None]) / cbar[None, :]
        xs = [m.x.copy() for m in self.models]
        Ps = [m.P.copy() for m in self.models]
        for j, m in enumerate(self.models):
            xj = sum(w[i, j] * xs[i] for i in range(3))
            Pj = sum(w[i, j] * (Ps[i] + np.outer(xs[i] - xj, xs[i] - xj)) for i in range(3))
            m.x, m.P = xj, Pj
        self._cbar = cbar

    def predict(self):
        if not self.initialised:
            return
        self._mix()
        vx, vy = self.x[2], self.x[3]
        sp = math.hypot(vx, vy)
        # turn rate estimate from acceleration perpendicular to velocity
        if sp > 5.0:
            ax, ay = self.x[4], self.x[5]
            self.omega = float(np.clip((vx * ay - vy * ax) / (sp * sp), -3.0, 3.0))
        Fs = [_F_cv(self.dt), _F_ca(self.dt), _F_ct(self.dt, self.omega)]
        for m, F in zip(self.models, Fs):
            m.predict(F, self.dt)
        self._combine()

    def update(self, x: float, y: float, sigma_px: float | None = None) -> float:
        z = np.array([x, y])
        R = self.R if sigma_px is None else np.eye(2) * max(sigma_px, 0.3) ** 2
        d2s = [m.update(z, R) for m in self.models]
        liks = np.array([m.lik for m in self.models])
        mu = self._cbar * liks if hasattr(self, "_cbar") else self.mu * liks
        s = mu.sum()
        self.mu = mu / s if s > 1e-30 else np.array([0.6, 0.2, 0.2])
        self._combine()
        return float(min(d2s))

    def _combine(self):
        self.x = sum(mu * m.x for mu, m in zip(self.mu, self.models))
        self.P = sum(mu * (m.P + np.outer(m.x - self.x, m.x - self.x)) for mu, m in zip(self.mu, self.models))

    # --------------------------------------------------------------- queries
    def gate(self, x: float, y: float) -> float:
        """Mahalanobis distance of a measurement from the predicted position."""
        if not self.initialised:
            return 0.0
        S = self.P[:2, :2] + self.R * max(1.0, (self.last_sigma / 1.2) ** 2)
        y_ = np.array([x, y]) - self.x[:2]
        return float(math.sqrt(max(y_ @ np.linalg.inv(S) @ y_, 0.0)))

    def position(self) -> tuple[float, float]:
        return float(self.x[0]), float(self.x[1])

    def velocity(self) -> tuple[float, float]:
        return float(self.x[2]), float(self.x[3])

    def position_at(self, dt_ahead: float) -> tuple[float, float]:
        x, y = self.position()
        vx, vy = self.velocity()
        return x + vx * dt_ahead + 0.5 * self.x[4] * dt_ahead ** 2, y + vy * dt_ahead + 0.5 * self.x[5] * dt_ahead ** 2

    def uncertainty_px(self) -> float:
        return float(math.sqrt(max(np.trace(self.P[:2, :2]) / 2, 0.0)))
