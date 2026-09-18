"""Frame-to-frame global shift of the picture, from phase correlation on a downscaled copy
with the beacon region masked. Used to cancel platform drift in the controller."""
from __future__ import annotations

import cv2
import numpy as np


class EgoMotion:
    def __init__(self, scale: int = 4):
        self.scale = scale
        self.prev: np.ndarray | None = None
        self.win = None

    def step(self, img: np.ndarray, mask_centre: tuple[float, float] | None, mask_r: int = 40) -> tuple[float, float, float]:
        """Returns (dx, dy, confidence) in full-resolution pixels."""
        small = cv2.resize(img, (img.shape[1] // self.scale, img.shape[0] // self.scale), interpolation=cv2.INTER_AREA)
        small = small.astype(np.float32)
        if mask_centre is not None:
            cx, cy = int(mask_centre[0] / self.scale), int(mask_centre[1] / self.scale)
            r = max(mask_r // self.scale, 3)
            cv2.circle(small, (cx, cy), r, float(small.mean()), -1)
        if self.win is None or self.win.shape != small.shape:
            self.win = cv2.createHanningWindow((small.shape[1], small.shape[0]), cv2.CV_32F)
        if self.prev is None or self.prev.shape != small.shape:
            self.prev = small
            return 0.0, 0.0, 0.0
        # featureless background gives a meaningless peak; check texture first
        if small.std() < 1.0:
            self.prev = small
            return 0.0, 0.0, 0.0
        (dx, dy), resp = cv2.phaseCorrelate(self.prev, small, self.win)
        self.prev = small
        conf = float(np.clip(resp, 0, 1))
        if conf < 0.05:
            return 0.0, 0.0, conf
        return float(dx * self.scale), float(dy * self.scale), conf
