"""A deliberately simple baseline tracker, to measure what ARGUS's design adds.

It is what a first attempt at the problem statement would do: blur the picture a little, take
the brightest spot, measure its intensity-weighted centre, and steer the camera toward it with a
proportional controller. There is no matched filter or robust noise level, no confirmation over
several frames, no motion model or lead, no gating, no identity among look-alikes, no faint-beacon
path and no search: if nothing stands out, it holds still.

It runs through the same simulator, gimbal limits, metrics and report as ARGUS, selected with
tracker.algorithm = "baseline" (tools/compare_trackers.py runs both over the scenario pack). It is
never the default and is not tuned; it exists only as the comparison.
"""
from __future__ import annotations

import cv2
import numpy as np

from ..engine.config import RunConfig, TrackerConfig
from ..world.camera import Gimbal, RateCommand
from .tracker import Mode, TrackOutput

BLUR_SIGMA = 2.0        # px: enough to stop single noise pixels winning, nothing tuned to the beacon
MIN_CONTRAST = 30.0     # grey levels above the picture's median before a spot counts as a detection
CENTROID_RADIUS = 7     # px around the peak used for the centre of gravity
KP = 5.0                # rate command per degree of error, the same proportional gain as ARGUS


class _NoEstimator:
    """The loop asks the tracker's estimator for its position (to mask the beacon in the
    picture-shift estimate); the baseline has none, so it reports the last detection."""
    def __init__(self):
        self.initialised = False
        self._pos = (0.0, 0.0)

    def position(self) -> tuple[float, float]:
        return self._pos


class BaselineTracker:
    def __init__(self, cfg: RunConfig, dt: float, screen_shape: tuple[int, int]):
        self.cfg = cfg
        self.dt = dt
        self.h, self.w = screen_shape
        self.imm = _NoEstimator()
        self.ambiguous_frames = 0
        self.redesignations = 0
        self.cue = None

    def set_cue(self, x: float, y: float) -> None:
        self.cue = (x, y)            # recorded for the summary; the baseline cannot use it

    def observe_ego(self, dx: float, dy: float, conf: float = 1.0) -> None:
        pass

    def step(self, img: np.ndarray, window_only_rect=None) -> TrackOutput:
        xa = ya = 0
        sub = img
        if window_only_rect is not None:
            x0, y0, w, h = window_only_rect
            xa, ya = max(x0, 0), max(y0, 0)
            sub = img[ya:min(y0 + h, self.h), xa:min(x0 + w, self.w)]
        det = None
        peak = 0.0
        if sub.size:
            blur = cv2.GaussianBlur(sub.astype(np.float32), (0, 0), BLUR_SIGMA)
            _, peak, _, (px, py) = cv2.minMaxLoc(blur)
            if peak - float(np.median(blur[::8, ::8])) >= MIN_CONTRAST:
                r = CENTROID_RADIUS
                ya0, xa0 = max(py - r, 0), max(px - r, 0)
                patch = sub[ya0:py + r + 1, xa0:px + r + 1].astype(np.float32)
                p = np.clip(patch - np.median(patch), 0, None)
                if p.sum() > 0:
                    yy, xx = np.mgrid[0:patch.shape[0], 0:patch.shape[1]]
                    det = (xa + xa0 + float((p * xx).sum() / p.sum()), ya + ya0 + float((p * yy).sum() / p.sum()))
        if det is not None:
            self.imm.initialised, self.imm._pos = True, det
        mode = Mode.TRACK if det is not None else Mode.SEARCH
        return TrackOutput(mode=mode, detection=det, estimate=det, prediction=det, velocity=(0.0, 0.0),
                           acceleration=(0.0, 0.0), confidence=1.0 if det else 0.0, n_candidates=int(det is not None),
                           tier="classical" if det else "none", gate=0.0, snr=0.0, sigma=0.0, uncertainty_px=0.0,
                           model_probs=(1.0, 0.0, 0.0), locked=det is not None)


class BaselineController:
    """Proportional pointing on the latest detection; holds still without one."""

    def __init__(self, cfg: TrackerConfig, gimbal: Gimbal, dt: float):
        self.g = gimbal

    def step(self, out: TrackOutput, ego_dx: float, ego_dy: float, window_only: bool) -> RateCommand:
        if out.detection is None:
            return RateCommand(0.0, 0.0)
        cx, cy = self.g.window_centre_px()
        e_pan, e_tilt = self.g.px_to_deg(out.detection[0] - cx, out.detection[1] - cy)
        return RateCommand(KP * e_pan, KP * e_tilt)
