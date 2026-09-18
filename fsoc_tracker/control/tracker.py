"""The tracking brain: state machine, association, identity and the estimator.

States (our design):
    SEARCH     no confirmed target. Detect on the whole observed picture.
    VERIFY     a candidate exists; require N of M consistent frames before trusting it.
    TRACK      locked; detect in a region around the prediction, update the estimator.
    COAST      detection missed; propagate the prediction, keep steering to it.
    REACQUIRE  missed for longer; widen the search around the prediction, then fall back
               to SEARCH if the uncertainty exceeds the screen.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

import numpy as np

from ..engine.config import RunConfig
from ..perception.detect import Candidate, ClassicalDetector, CNNDetector
from ..perception.estimator import IMM


class Mode(str, Enum):
    SEARCH = "SEARCH"
    VERIFY = "VERIFY"
    TRACK = "TRACK"
    COAST = "COAST"
    REACQUIRE = "REACQUIRE"


@dataclass
class TrackOutput:
    mode: Mode
    detection: tuple[float, float] | None      # measured centroid this frame
    estimate: tuple[float, float] | None       # filtered position
    prediction: tuple[float, float] | None     # one frame ahead
    velocity: tuple[float, float]
    acceleration: tuple[float, float]
    confidence: float
    n_candidates: int
    tier: str                                  # classical | cnn | none
    gate: float                                # Mahalanobis distance of accepted detection
    snr: float
    sigma: float
    uncertainty_px: float
    model_probs: tuple[float, float, float]
    locked: bool
    signature: dict = field(default_factory=dict)


class Tracker:
    def __init__(self, cfg: RunConfig, dt: float, screen_shape: tuple[int, int]):
        self.cfg = cfg
        self.tc = cfg.tracker
        self.dt = dt
        self.h, self.w = screen_shape
        exp = cfg.targets[0].size_px if (cfg.targets and not cfg.video) else None
        self.classical = ClassicalDetector(self.tc, exp)
        self.cnn = CNNDetector(self.tc.cnn_model) if self.tc.detector in ("cnn", "hybrid") else None
        self.imm = IMM(dt)
        self.mode = Mode.SEARCH
        self.verify_hits: list[bool] = []
        self.miss_count = 0
        self.frames_in_mode = 0
        self.designated_sig: dict | None = None   # appearance signature of the target we follow
        self._cand_hist: list[Candidate] = []
        self._search_roi: tuple[int, int, int, int] | None = None
        # jitter statistics from the measured frame-to-frame picture shift
        self._ego_lp = np.zeros(2)
        self._ego_var = 16.0          # start assuming ~4 px of vibration; adapts within a second
        self.jitter_sigma = 4.0
        self._inn_bias = np.zeros(2)
        self._v_prev = None
        self._acc = np.zeros(2)
        self._audit_strikes = 0
        self.redesignations = 0

    JITTER_CAP = 25.0   # px; the PS maximum vibration is 20 px/frame

    def observe_ego(self, dx: float, dy: float, conf: float = 1.0):
        """Picture shift measured by phase correlation. Only trusted when the correlation
        peak is clear and the shift is physically plausible; on noisy frames it is ignored."""
        if not self.tc.ego_motion or conf < 0.2 or abs(dx) > 60 or abs(dy) > 60:
            return
        e = np.array([dx, dy])
        self._ego_lp = 0.8 * self._ego_lp + 0.2 * e
        dev = e - self._ego_lp
        self._ego_var = 0.9 * self._ego_var + 0.1 * float(dev @ dev) / 2
        self.jitter_sigma = float(min(np.sqrt(self._ego_var), self.JITTER_CAP))

    def _note_innovation(self, x: float, y: float):
        """Vibration shows up as a zero-mean jump of the measurement about the prediction.
        Track its magnitude and use it as measurement noise, so the estimator smooths the
        vibration instead of chasing it. Robust on any frame content, unlike phase correlation."""
        px, py = self.imm.position()
        inn = np.array([x - px, y - py])
        # a lagging estimate gives an innovation that points the same way frame after
        # frame; vibration gives one that flips sign. Only the zero-mean part is noise.
        self._inn_bias = 0.7 * self._inn_bias + 0.3 * inn
        dev = float(np.linalg.norm(inn - self._inn_bias))
        self.jitter_sigma = float(min(0.85 * self.jitter_sigma + 0.15 * 0.7 * dev, self.JITTER_CAP))

    def _meas_sigma(self) -> float:
        s = float(np.hypot(1.2, self.jitter_sigma))
        self.imm.last_sigma = s
        return s

    # ------------------------------------------------------------------ main
    def step(self, img: np.ndarray, window_only_rect: tuple[int, int, int, int] | None = None) -> TrackOutput:
        self.frames_in_mode += 1
        tier = "none"
        detection = None
        gate_d = 0.0
        snr = sigma = 0.0
        conf = 0.0

        if self.imm.initialised:
            self.imm.predict()

        if self.mode in (Mode.SEARCH, Mode.VERIFY):
            roi = window_only_rect and _rect_to_roi(window_only_rect, img.shape)
            cands = self.classical.detect(img, roi)
            tier = "classical" if cands else "none"
            chosen = self._pick_new(cands)
            if chosen is not None:
                detection = (chosen.x, chosen.y)
                conf, snr, sigma = chosen.confidence, chosen.snr, chosen.sigma
                if self.mode == Mode.SEARCH:
                    self.imm.reset(chosen.x, chosen.y)
                    self.designated_sig = _signature(chosen)
                    self.verify_hits = [True]
                    self._set(Mode.VERIFY)
                else:
                    self.imm.update(chosen.x, chosen.y, self._meas_sigma())
                    self.verify_hits.append(True)
            elif self.mode == Mode.VERIFY:
                self.verify_hits.append(False)
            if self.mode == Mode.VERIFY:
                hist = self.verify_hits[-self.tc.verify_m:]
                if sum(hist) >= self.tc.verify_n:
                    self._set(Mode.TRACK)
                    self.miss_count = 0
                elif len(hist) >= self.tc.verify_m and sum(hist) < self.tc.verify_n:
                    self._set(Mode.SEARCH)
                    self.imm.initialised = False
            n_c = len(cands)

        else:  # TRACK, COAST, REACQUIRE
            px, py = self.imm.position()
            half = int(self.tc.search_roi_px + 4 * self.jitter_sigma)
            if self.mode == Mode.REACQUIRE:
                half = int(min(half * (1.5 + 0.25 * self.miss_count), max(self.w, self.h)))
            roi = (int(max(px - half, 0)), int(max(py - half, 0)),
                   int(min(px + half, self.w)), int(min(py + half, self.h)))
            cands = self.classical.detect(img, roi)
            n_c = len(cands)
            chosen, gate_d = self._associate(cands)
            tier = "classical" if chosen is not None else "none"
            # Tier 2: the CNN fills gaps. It is asked only when the classical detector found
            # nothing acceptable near the prediction, and its answer is used only when it is
            # confident and close to the prediction. It never overrides a classical hit.
            if chosen is None and self.cnn is not None and self.tc.detector in ("cnn", "hybrid"):
                c2 = self.cnn.detect(img, px, py)
                if c2 is not None and c2.confidence >= 0.6:
                    g2 = self.imm.gate(c2.x, c2.y)
                    if g2 < 4.0 and np.hypot(c2.x - px, c2.y - py) < self.tc.gate_px:
                        chosen, gate_d, tier = c2, g2, "cnn"
            if chosen is not None:
                detection = (chosen.x, chosen.y)
                conf, snr, sigma = chosen.confidence, chosen.snr, chosen.sigma
                if self.mode == Mode.TRACK:
                    self._note_innovation(chosen.x, chosen.y)
                # after a long gap a distant re-detection must not be read as velocity:
                # re-seed the position and let the velocity re-converge
                if self.miss_count > 3 and np.hypot(chosen.x - px, chosen.y - py) > 3 * max(self.imm.uncertainty_px(), 10.0):
                    self.imm.reset(chosen.x, chosen.y)
                    self._v_prev, self._acc = None, np.zeros(2)
                self.imm.update(chosen.x, chosen.y, self._meas_sigma())
                self._update_signature(chosen)
                self.miss_count = 0
                if self.mode != Mode.TRACK:
                    self._set(Mode.TRACK)
            else:
                self.miss_count += 1
                if self.mode == Mode.TRACK:
                    self._set(Mode.COAST)
                elif self.mode == Mode.COAST and self.miss_count > self.tc.coast_frames:
                    self._set(Mode.REACQUIRE)
                elif self.mode == Mode.REACQUIRE and (self.imm.uncertainty_px() > 0.5 * max(self.w, self.h) or self.miss_count > 6 * self.tc.coast_frames):
                    self._set(Mode.SEARCH)
                    self.imm.initialised = False

        if self.mode == Mode.TRACK and self.frames_in_mode % 15 == 0 and len(self.cfg.targets) > 1:
            self._audit_designation(img)

        est = self.imm.position() if self.imm.initialised else None
        pred = self.imm.position_at(self.dt) if self.imm.initialised else None
        vel = self.imm.velocity() if self.imm.initialised else (0.0, 0.0)
        # acceleration from the smoothed change of the estimated velocity; robust across
        # models (the CV and CT filters carry no acceleration state of their own)
        if self.imm.initialised and self.mode in (Mode.TRACK, Mode.COAST):
            v = np.array(vel)
            if self._v_prev is not None:
                self._acc = 0.75 * self._acc + 0.25 * (v - self._v_prev) / self.dt
            self._v_prev = v
        else:
            self._v_prev, self._acc = None, np.zeros(2)
        acc = (float(self._acc[0]), float(self._acc[1]))
        return TrackOutput(
            mode=self.mode, detection=detection, estimate=est, prediction=pred, velocity=vel, acceleration=acc,
            confidence=conf, n_candidates=n_c, tier=tier, gate=gate_d, snr=snr, sigma=sigma,
            uncertainty_px=self.imm.uncertainty_px() if self.imm.initialised else 0.0,
            model_probs=tuple(float(m) for m in self.imm.mu), locked=self.mode == Mode.TRACK,
            signature=self.designated_sig or {},
        )

    # --------------------------------------------------------------- helpers
    def _config_score(self, c: Candidate, peak_max: float) -> float:
        """How well a candidate matches the designated beacon as configured (size) and
        as the brightest spot. Lower is better."""
        exp_area = self.classical.expected_area() or (c.area + 1)
        return 1.5 * abs(np.log((c.area + 1) / (exp_area + 1))) - 1.0 * (c.peak / max(peak_max, 1.0)) - 0.5 * c.confidence

    def _audit_designation(self, img: np.ndarray):
        """Every half second in TRACK with several targets configured, look at the whole
        picture and ask whether some other spot matches the designated beacon clearly
        better than the one being followed. Three consecutive strikes re-designate. This
        recovers from locking a decoy while the beacon was briefly out of the picture."""
        cands = self.classical.detect(img)
        if len(cands) < 2:
            self._audit_strikes = 0
            return
        px, py = self.imm.position()
        cur = min(cands, key=lambda c: np.hypot(c.x - px, c.y - py))
        if np.hypot(cur.x - px, cur.y - py) > 40:
            self._audit_strikes = 0
            return
        peak_max = max(c.peak for c in cands)
        best = min(cands, key=lambda c: self._config_score(c, peak_max))
        if best is cur or self._config_score(cur, peak_max) - self._config_score(best, peak_max) < 0.6:
            self._audit_strikes = 0
            return
        self._audit_strikes += 1
        if self._audit_strikes >= 3:
            self._audit_strikes = 0
            self.redesignations += 1
            self.imm.reset(best.x, best.y)
            self.designated_sig = _signature(best)
            self._v_prev, self._acc = None, np.zeros(2)
            self.verify_hits = [True]
            self.miss_count = 0
            self._set(Mode.VERIFY)

    def _set(self, m: Mode):
        if m != self.mode:
            self.mode = m
            self.frames_in_mode = 0

    def _pick_new(self, cands: list[Candidate]) -> Candidate | None:
        """In SEARCH/VERIFY choose the best candidate. When several targets exist and a
        designated signature is known (from config: the first target), prefer the closest
        signature; otherwise the highest confidence."""
        if not cands:
            return None
        if self.mode == Mode.VERIFY and self.imm.initialised:
            best, _ = self._associate(cands)
            return best
        # a new track must look like a beacon, not a star or a noise clump
        floor = self.tc.acquire_conf_min + (0.13 if self.cfg.camera.window_only else 0.0)
        cands = [c for c in cands if c.confidence >= floor]
        if not cands:
            return None
        # The designated target is the first configured target. Its expected appearance
        # (size, shape) is known from config, so prefer candidates matching it.
        exp_area = self.classical.expected_area()
        if exp_area is not None and len(cands) > 1:
            # the designated beacon is described by its configured size; among several
            # candidates prefer the size match, then brightness, then detector confidence
            peak_max = max(c.peak for c in cands) or 1.0
            cands = sorted(cands, key=lambda c: 1.5 * abs(np.log((c.area + 1) / (exp_area + 1)))
                           - 1.0 * (c.peak / peak_max) - 0.5 * c.confidence)
            return cands[0]
        return cands[0]

    def _associate(self, cands: list[Candidate]) -> tuple[Candidate | None, float]:
        """Gate candidates by Mahalanobis distance, then score by gate and signature."""
        best, best_score, best_g = None, 1e9, 0.0
        for c in cands:
            g = self.imm.gate(c.x, c.y)
            px, py = self.imm.position()
            gate = min((self.tc.gate_px + 4 * self.jitter_sigma) * (1 + 0.5 * self.miss_count), 320.0)
            if np.hypot(c.x - px, c.y - py) > gate:
                continue
            sd = _signature_distance(self.designated_sig, _signature(c))
            # appearance rejection once a signature exists (TRACK, COAST, REACQUIRE); in VERIFY
            # the signature is one frame old and noisy, so position consistency alone decides
            if self.mode != Mode.VERIFY and sd > 1.1:
                continue
            score = g + 2.0 * sd - 0.5 * c.confidence
            if score < best_score:
                best, best_score, best_g = c, score, g
        return best, best_g

    def _update_signature(self, c: Candidate):
        s = _signature(c)
        if self.designated_sig is None:
            self.designated_sig = s
        else:
            a = 0.1
            for k, v in s.items():
                self.designated_sig[k] = (1 - a) * self.designated_sig.get(k, v) + a * v


def _signature(c: Candidate) -> dict:
    return {"area": float(c.area), "peak": float(c.peak), "sigma": float(c.sigma)}


def _signature_distance(a: dict | None, b: dict) -> float:
    if not a:
        return 0.0
    da = abs(np.log((a["area"] + 1) / (b["area"] + 1)))
    dp = abs(a["peak"] - b["peak"]) / 255.0
    ds = abs(a["sigma"] - b["sigma"]) / 3.0
    return float(1.5 * da + 2.0 * dp + ds)


def _rect_to_roi(rect, shape):
    x0, y0, w, h = rect
    H, W = shape
    return (max(x0, 0), max(y0, 0), min(x0 + w, W), min(y0 + h, H))
