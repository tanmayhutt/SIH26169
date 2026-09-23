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
        self.before_frame = None     # called with (index, time) before each frame is drawn

    def __iter__(self):
        for i in range(self.n_frames):
            t = i * self.dt
            if self.before_frame is not None:
                self.before_frame(i, t)
            img, truth = self.world.render()
            yield Frame(i, t, img, truth)


def probe_video(path: str | Path, count_limit: int = 30000) -> dict:
    """Read a video file's real facts: displayed size (rotation applied), average frame
    rate (cross-checked against frame timestamps, since phone recordings are often
    variable-rate), exact frame count (by scanning, for files up to `count_limit` frames),
    duration and rotation tag. This is what the run and the report are calibrated from."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(path)
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open video {path}")
    ok, first = cap.read()
    if not ok:
        cap.release(); raise RuntimeError(f"cannot decode the first frame of {path}")
    h, w = first.shape[:2]                                   # as displayed (OpenCV applies the rotation tag)
    fps_prop = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
    rot = float(cap.get(cv2.CAP_PROP_ORIENTATION_META) or 0.0)
    n_prop = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    ts, n = [cap.get(cv2.CAP_PROP_POS_MSEC)], 1
    while True:
        if not cap.grab():
            break
        n += 1
        if n <= 300:
            ts.append(cap.get(cv2.CAP_PROP_POS_MSEC))
        if n >= count_limit:
            break
    cap.release()
    frames = n if n < count_limit else max(n_prop, n)
    d = np.diff(np.array(ts)); d = d[d > 0]
    fps_ts = float(1000.0 / np.median(d)) if len(d) else 0.0
    # the container's average rate is the right clock for a whole-file run; the timestamp
    # rate reveals a variable-rate recording when the two disagree
    fps = fps_prop if fps_prop > 1 else (fps_ts if fps_ts > 1 else 30.0)
    variable = fps_ts > 1 and abs(fps_ts - fps) / fps > 0.03
    return {"path": str(path), "width": int(w), "height": int(h), "fps": fps, "fps_timestamps": fps_ts, "variable_rate": bool(variable),
            "frames": int(frames), "seconds": frames / fps if fps else 0.0, "rotation_deg": rot,
            "stored_size": (int(h), int(w)) if rot in (90.0, 270.0, -90.0) else (int(w), int(h)),
            "colour": first.ndim == 3 and not bool((first[..., 0] == first[..., 1]).all() and (first[..., 1] == first[..., 2]).all())}


class VideoSource:
    """Benchmark 2: each video frame is used as the scene picture. Truth is unknown.
    The run is calibrated from the file: the scene is the video's displayed size and the
    clock is its average frame rate."""
    kind = "video"

    def __init__(self, cfg: RunConfig):
        path = Path(cfg.video)
        self.info = probe_video(path)
        self.colour = bool(cfg.screen.colour)
        self.cap = cv2.VideoCapture(str(path))
        if not self.cap.isOpened():
            raise RuntimeError(f"cannot open video {path}")
        fps = self.info["fps"]
        self.dt = 1.0 / fps
        w, h = self.info["width"], self.info["height"]
        self.shape = (h, w)
        self.n_frames = self.info["frames"]
        if cfg.duration_s > 0:
            self.n_frames = min(self.n_frames, int(cfg.duration_s / self.dt))
        # calibrate the configuration to the file so every readout and the report agree
        cfg.screen.width, cfg.screen.height = w, h
        cfg.camera.update_rate_hz = fps
        cfg.camera.width = min(cfg.camera.width, w)
        cfg.camera.height = min(cfg.camera.height, h)

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
