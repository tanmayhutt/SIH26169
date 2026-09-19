"""Frame sources. The tracker never knows whether a frame came from the simulator or from
an evaluator's video file; both yield the same Frame."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ..world.renderer import Truth, World
from .config import RunConfig


@dataclass
class Frame:
    idx: int
    t: float
    image: np.ndarray            # uint8 grayscale, the scene picture
    truth: Truth | None          # None for video files


class SyntheticSource:
    kind = "synthetic"

    def __init__(self, cfg: RunConfig):
        self.world = World(cfg)
        self.dt = self.world.dt
        self.n_frames = int(round(cfg.duration_s / self.dt))
        self.shape = (self.world.h, self.world.w)

    def __iter__(self):
        for i in range(self.n_frames):
            t = i * self.dt
            img, truth = self.world.render()
            yield Frame(i, t, img, truth)


class VideoSource:
    """Benchmark 2: each video frame is used as the scene picture. Truth is unknown."""
    kind = "video"

    def __init__(self, cfg: RunConfig):
        path = Path(cfg.video)
        if not path.exists():
            raise FileNotFoundError(path)
        self.colour = bool(cfg.screen.colour)
        self.cap = cv2.VideoCapture(str(path))
        if not self.cap.isOpened():
            raise RuntimeError(f"cannot open video {path}")
        fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.dt = 1.0 / (fps if fps > 1 else 30.0)
        w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.shape = (h, w)
        n = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.n_frames = n if n > 0 else 10 ** 9
        if cfg.duration_s > 0:
            self.n_frames = min(self.n_frames, int(cfg.duration_s / self.dt))
        # the camera window must fit inside the video
        cfg.camera.width = min(cfg.camera.width, w)
        cfg.camera.height = min(cfg.camera.height, h)
        cfg.screen.width, cfg.screen.height = w, h

    def __iter__(self):
        i = 0
        while i < self.n_frames:
            ok, bgr = self.cap.read()
            if not ok:
                break
            if self.colour and bgr.ndim == 3:
                yield Frame(i, i * self.dt, bgr, None)
            else:
                gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if bgr.ndim == 3 else bgr
                yield Frame(i, i * self.dt, gray, None)
            i += 1
        self.cap.release()


def make_source(cfg: RunConfig):
    return VideoSource(cfg) if cfg.video else SyntheticSource(cfg)
