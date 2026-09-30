"""Draws the scene picture the tracker observes and records the ground truth for it."""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

import cv2
import numpy as np

from ..engine.config import RunConfig, apply_atmosphere_preset
from .camera import Gimbal
from .disturbance import DisturbanceModel, FrameDisturbance
from .scene import make_background
from .sprites import make_sprite
from .targets import Target, TargetState


@dataclass
class Truth:
    """Where things really are this frame, in observed-picture pixels."""
    beacons: list[tuple[float, float]] = field(default_factory=list)   # in configured order; RunConfig.designated picks the beacon
    visible: list[bool] = field(default_factory=list)
    disturbance: FrameDisturbance = field(default_factory=FrameDisturbance)
    window: tuple[int, int, int, int] = (0, 0, 0, 0)                   # x0, y0, w, h
    interpolated: bool = False    # video truth filled between two listed frames: visibility only, not scored


class World:
    """Scene, beacons, camera and disturbances. `render()` produces one frame plus truth."""

    def __init__(self, cfg: RunConfig):
        self.cfg = cfg
        self.rng = np.random.default_rng(cfg.seed)
        self.dt = 1.0 / cfg.camera.update_rate_hz
        self.t = 0.0
        apply_atmosphere_preset(cfg.disturbance)
        self.background = make_background(cfg.screen, self.rng)
        self.h, self.w = self.background.shape
        self.targets = [Target(tc, self.w, self.h, self.rng, i) for i, tc in enumerate(cfg.targets)]
        self.gimbal = Gimbal(cfg.camera, self.w, self.h)
        # the model works on its own copy: changes during the run (Simulation.request_disturbance)
        # must not alter the run's configuration, which is saved as the scenario it started from
        self.disturbance = DisturbanceModel(copy.deepcopy(cfg.disturbance), (self.h, self.w), self.rng, self.dt)
        self._sprites: dict[tuple, np.ndarray] = {}

    # ---------------------------------------------------------------- sprite
    def _sprite(self, tc) -> np.ndarray:
        w, h = tc.dims
        key = (tc.shape, w, h, tc.mask if tc.shape == "custom" else "")
        if key not in self._sprites:
            self._sprites[key] = make_sprite(tc.shape, w, h, tc.mask)
        return self._sprites[key]

    # ---------------------------------------------------------------- render
    def render(self) -> tuple[np.ndarray, Truth]:
        cfg = self.cfg
        img = self.background.copy()
        d = self.disturbance.step()
        truth = Truth(disturbance=d)
        boxes = []
        for tgt in self.targets:
            st: TargetState = tgt.state(self.t)
            x = st.x + d.wander_dx
            y = st.y + d.wander_dy
            inten = float(np.clip(st.intensity * d.scint, 0, 255))
            sp = self._sprite(tgt.cfg)
            nh, nw = sp.shape
            # sub-pixel placement by shifting the sprite
            ix, iy = int(np.floor(x)), int(np.floor(y))
            fx, fy = x - ix, y - iy
            # Pixel-centre convention: the sprite's centre index is (n-1)/2, it is placed at
            # ix - n//2, so shift by the difference to land exactly on (x, y).
            offx = nw // 2 - (nw - 1) / 2.0
            offy = nh // 2 - (nh - 1) / 2.0
            M = np.array([[1, 0, fx + offx], [0, 1, fy + offy]], np.float32)
            sps = cv2.warpAffine(sp, M, (nw, nh), flags=cv2.INTER_LINEAR)
            x0, y0 = ix - nw // 2, iy - nh // 2
            xa, ya = max(x0, 0), max(y0, 0)
            xb, yb = min(x0 + nw, self.w), min(y0 + nh, self.h)
            if xb > xa and yb > ya:
                region = img[ya:yb, xa:xb].astype(np.float32)
                patch = sps[ya - y0:yb - y0, xa - x0:xb - x0] * inten
                img[ya:yb, xa:xb] = np.clip(np.maximum(region, patch), 0, 255).astype(np.uint8)
                boxes.append((xa, ya, xb - xa, yb - ya))
            # truth in observed-picture pixels includes the picture shift
            truth.beacons.append((x + d.shift[0], y + d.shift[1]))
            truth.visible.append(st.visible)
        img = self.disturbance.apply_image(img, boxes, d)
        if cfg.screen.colour:
            img = self._colourise(img)
        truth.window = self.gimbal.window_rect()
        self.t += self.dt
        return img, truth

    def _colourise(self, gray: np.ndarray) -> np.ndarray:
        """Colour camera option (PS row 2): a three-channel frame. The sky takes a faint
        blue cast and bright sources a warm one, as a colour FPA would render a near-white
        beacon; luminance is preserved so the tracker sees the same picture."""
        g = gray.astype(np.float32)
        w = np.clip((g - 60.0) / 140.0, 0.0, 1.0)          # 0 on the sky, 1 on a bright source
        b = g * (1.06 - 0.10 * w)
        gch = g * (1.00 + 0.00 * w)
        r = g * (0.94 + 0.12 * w)
        return np.clip(np.dstack([b, gch, r]), 0, 255).astype(np.uint8)   # BGR for OpenCV

    def observed(self, img: np.ndarray) -> np.ndarray:
        """What the tracker is allowed to see. Full picture by default; in hard mode only
        the window, with everything else blacked out."""
        if not self.cfg.camera.window_only:
            return img
        x0, y0, w, h = self.gimbal.window_rect()
        out = np.zeros_like(img)
        xa, ya = max(x0, 0), max(y0, 0)
        xb, yb = min(x0 + w, self.w), min(y0 + h, self.h)
        out[ya:yb, xa:xb] = img[ya:yb, xa:xb]
        return out
