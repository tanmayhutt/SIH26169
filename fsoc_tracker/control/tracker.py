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

import cv2
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
    MIN_SIGMA = 0.9   # fitted width below this is a single pixel; PS row 10 beacons are 5 to 20 px

    def __init__(self, cfg: RunConfig, dt: float, screen_shape: tuple[int, int]):
        self.cfg = cfg
        self.tc = cfg.tracker
        self.dt = dt
        self.h, self.w = screen_shape
        # the configured beacon size (PS row 10, default 10 px) is the matched-filter prior;
        # for a video it is the user's statement of what to look for, not ground truth
        # the designated target (RunConfig.designated) is the one whose appearance is the prior
        t = cfg.designated_target()
        if t is not None:
            self.classical = ClassicalDetector(self.tc, None, t.shape, t.dims, t.mask)
        else:
            self.classical = ClassicalDetector(self.tc, None, "square")
        self.cnn = CNNDetector(self.tc.cnn_model) if self.tc.detector in ("cnn", "hybrid") else None
        if self.cnn is not None:
            self.cnn.warm_up()          # pay the model start-up here, not in the middle of a track
        self.imm = IMM(dt)
        self.mode = Mode.SEARCH
        self.verify_hits: list[bool] = []
        self.provisional = False          # current VERIFY candidate came through the faint path
        self.faint = False                # the target being followed was acquired through the faint path
        self._chains: list[dict] = []     # track-before-detect chains while searching
        self._faint_v = (0.0, 0.0)
        self._faint_q: list[float] = []
        self._det_img: np.ndarray | None = None
        self._audit_det: ClassicalDetector | None = None   # half-resolution detector for the identity audit
        self._static: np.ndarray | None = None   # running mean of the picture: stars and sky, not a moving beacon
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
        # designation cue: a point near the designated beacon (its start, or a click). While
        # searching, the candidate nearest the cue is taken, so identical-looking decoys cannot
        # be confused with it. After a loss the last estimate becomes the cue.
        self.cue: tuple[float, float] | None = None
        self._cue_mode = False
        self.ambiguous_frames = 0     # search frames in which another spot looked just like the designated one
        self.ambiguous = False

    JITTER_CAP = 25.0   # px; the PS maximum vibration is 20 px/frame
    AMBIGUOUS_MARGIN = 0.15   # appearance scores closer than this cannot tell two spots apart

    def set_cue(self, x: float, y: float) -> None:
        """Tell the tracker where the designated beacon is (or starts)."""
        self.cue = (float(x), float(y))
        self._cue_mode = True

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
            if self.mode == Mode.VERIFY and self.faint and self.imm.initialised:
                # verifying a faint chain: look near the prediction with the faint threshold
                px, py = self.imm.position()
                half = int(self.tc.search_roi_px + 4 * self.jitter_sigma)
                roi = (int(max(px - half, 0)), int(max(py - half, 0)), int(min(px + half, self.w)), int(min(py + half, self.h)))
                fk, fmf = self._faint_params()
                det_img = self._residual(img, 0.03)
                cands = self.classical.detect(det_img, roi, k=fk, mf_sigma=fmf)
            else:
                det_img = img
                cands = self.classical.detect(img, roi)
            # candidates past the first few come back unrefined; whoever picks one refines it
            # on this frame's picture, never on one left over from an earlier frame or state
            self._det_img = det_img
            tier = "classical" if cands else "none"
            # candidates are re-measured on this frame's picture (before, a search after a loss
            # re-measured them on the last tracked frame, and a first search with several strong
            # candidates had no picture at all)
            self._det_img = det_img
            chosen = self._pick_new(cands)
            # the faint path needs a still picture to build its moving-target residual; in hard
            # mode the window sweeps the screen, so the path is off there
            if chosen is None and self.mode == Mode.SEARCH and self.classical.expected_size_px and window_only_rect is None:
                chosen = self._faint_search(img, roi)
                if chosen is not None:
                    tier = "classical"
            if chosen is not None:
                detection = (chosen.x, chosen.y)
                conf, snr, sigma = chosen.confidence, chosen.snr, chosen.sigma
                if self.mode == Mode.SEARCH:
                    self.imm.reset(chosen.x, chosen.y)
                    if self.faint:
                        self.imm.set_velocity(self._faint_v[0] / self.dt, self._faint_v[1] / self.dt)
                    self.designated_sig = _signature(chosen)
                    self.verify_hits = [True]
                    self._set(Mode.VERIFY)
                else:
                    self.imm.update(chosen.x, chosen.y, self._meas_sigma())
                    self.verify_hits.append(True)
            elif self.mode == Mode.VERIFY:
                self.verify_hits.append(False)
            if self.mode == Mode.VERIFY:
                # a provisional (faint) candidate needs a longer, stricter confirmation
                v_n, v_m = (5, 6) if self.provisional else (self.tc.verify_n, self.tc.verify_m)
                hist = self.verify_hits[-v_m:]
                if sum(hist) >= v_n:
                    self._set(Mode.TRACK)
                    self.miss_count = 0
                    self.provisional = False
                elif len(hist) >= v_m and sum(hist) < v_n:
                    self._set(Mode.SEARCH)
                    self.imm.initialised = False
                    self.provisional = False
            n_c = len(cands)

        else:  # TRACK, COAST, REACQUIRE
            px, py = self.imm.position()
            half = int(self.tc.search_roi_px + 4 * self.jitter_sigma)
            if self.mode == Mode.REACQUIRE:
                half = int(min(half * (1.5 + 0.25 * self.miss_count), max(self.w, self.h)))
            roi = (int(max(px - half, 0)), int(max(py - half, 0)),
                   int(min(px + half, self.w)), int(min(py + half, self.h)))
            if self.faint:
                fk, fmf = self._faint_params()
                det_img = self._residual(img, 0.03)
                cands = self.classical.detect(det_img, roi, k=fk, mf_sigma=fmf, refine=0, limit=30)
            else:
                det_img = img
                cands = self.classical.detect(img, roi, refine=0)
            self._det_img = det_img
            n_c = len(cands)
            chosen, gate_d = self._associate(cands)
            if chosen is not None:
                chosen = self.classical.refine(det_img, chosen)
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
                    if self._cue_mode:
                        self.cue = self.imm.position()
                    self._set(Mode.SEARCH)
                    self.imm.initialised = False
                    self.faint = False

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
        # two size measures: the thresholded blob area (sharp when the noise is low) and the
        # fitted width (steady when the noise is high; compared as squared widths because
        # noise inflates every candidate's second moment by about the same amount)
        exp_area = self.classical.expected_area() or (c.area + 1)
        exp_sigma = self.classical.expected_sigma() or max(c.sigma, 0.3)
        area_term = abs(np.log((c.area + 1) / (exp_area + 1)))
        sigma_term = abs(c.sigma ** 2 - exp_sigma ** 2) / (exp_sigma ** 2)
        return 0.75 * area_term + 0.75 * sigma_term - 1.0 * (c.peak / max(peak_max, 1.0)) - 0.5 * c.confidence

    def _audit_designation(self, img: np.ndarray):
        """Every half second in TRACK with several targets configured, look at the whole
        picture and ask whether some other spot matches the designated beacon clearly
        better than the one being followed. Three consecutive strikes re-designate. This
        recovers from locking a decoy while the beacon was briefly out of the picture."""
        # the audit only needs to find the few bright spots, so it looks at a half-size copy
        # of the picture (a quarter of the work); the spots it keeps are then re-measured at
        # full resolution, so sizes and widths are compared on the real pixels
        if self._audit_det is None:
            dims = self.classical.expected_dims or (10.0, 10.0)
            self._audit_det = ClassicalDetector(self.tc, None, self.classical.expected_shape, (dims[0] / 2.0, dims[1] / 2.0), self.classical.expected_mask)
        small = img[::2, ::2]
        coarse = self._audit_det.detect(small, refine=0, limit=8)
        if len(coarse) < 2:
            self._audit_strikes = 0
            return
        floor = self.tc.acquire_conf_min
        cands = []
        for c in coarse:
            if c.confidence < floor - 0.1:
                continue
            full = self.classical.detect(img, (int(max(2 * c.x - 24, 0)), int(max(2 * c.y - 24, 0)), int(min(2 * c.x + 24, self.w)), int(min(2 * c.y + 24, self.h))), refine=1, limit=1)
            if full:
                cands.append(full[0])
        cands = cands[:6]
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
        strong = [c for c in cands if c.confidence >= floor]
        if not strong:
            return None
        cands = strong
        self.provisional = False
        self.faint = False
        if self.cue is not None:
            # designated by a cue: the strong candidate nearest to it (VERIFY then confirms it)
            return min(cands, key=lambda c: np.hypot(c.x - self.cue[0], c.y - self.cue[1]))
        if len(cands) == 1 and self._det_img is not None:
            c = self.classical.refine(self._det_img, cands[0])
            return c if c.sigma >= self.MIN_SIGMA else None
        # The designated target's expected appearance (size, shape) is known from config,
        # so prefer candidates matching it.
        exp_sigma = self.classical.expected_sigma()
        if exp_sigma is not None and len(cands) > 1:
            # the designated beacon is described by its configured size and shape; among
            # several candidates prefer the fitted-width match (independent of the noise
            # level, unlike the thresholded area), then brightness, then detector confidence.
            # the width comes from the sub-pixel fit, so refine the few strong candidates
            cands = [self.classical.refine(self._det_img, c) for c in cands[:6]]
            cands = [c for c in cands if c.sigma >= self.MIN_SIGMA] or cands   # a hot pixel is not a beacon
            peak_max = max(c.peak for c in cands) or 1.0
            scored = sorted(((self._config_score(c, peak_max), c) for c in cands), key=lambda sc: sc[0])
            self.ambiguous = len(self.cfg.targets) > 1 and len(scored) > 1 and scored[1][0] - scored[0][0] < self.AMBIGUOUS_MARGIN
            if self.ambiguous:
                self.ambiguous_frames += 1
            return scored[0][1]
        return cands[0]

    # ------------------------------------------------------- faint beacon path
    def _faint_params(self) -> tuple[float, float]:
        """Threshold and matched-filter width for a dim beacon: a lower threshold, and a
        narrower filter because after extinction only the core of the spot stands above
        the sky."""
        size = self.classical.expected_size_px or 8.0
        return self.tc.faint_threshold_k, max(0.6, size / 6.0)

    def _residual(self, img: np.ndarray, alpha: float) -> np.ndarray:
        """Moving-target residual: the running mean of the picture holds everything static
        (stars, sky gradient, hot pixels); a beacon that moves leaves it behind. The faint
        path detects on the residual so that stars cannot form chains."""
        if self._static is None or self._static.shape != img.shape:
            self._static = img.astype(np.float32)
        else:
            cv2.accumulateWeighted(img, self._static, alpha)
        return cv2.subtract(img, cv2.convertScaleAbs(self._static))

    def _faint_search(self, img: np.ndarray, roi) -> Candidate | None:
        """Track-before-detect. A beacon at 3 to 6 sigma per frame cannot be told from noise
        in one picture, but noise does not move in a straight line: weak candidates are
        linked frame to frame into chains with a consistent velocity, and a chain that keeps
        being hit is promoted to a provisional track. Stars form chains too (static ones),
        so the chain must also carry a matched-filter SNR above `faint_snr_min` on average
        and a spot size near the designated beacon's."""
        k, mf = self._faint_params()
        res = self._residual(img, 0.1)
        cands = self.classical.detect(res, roi, k=k, mf_sigma=mf, refine=0, limit=400)
        gate = 8.0 + 4.0 * self.jitter_sigma
        used = set()
        for ch in self._chains:
            px, py = ch["x"] + ch["vx"], ch["y"] + ch["vy"]
            best, bd = None, gate * (1 + 0.5 * ch["miss"])
            for i, c in enumerate(cands):
                if i in used:
                    continue
                d = float(np.hypot(c.x - px, c.y - py))
                if d < bd:
                    best, bd = i, d
            if best is None:
                ch["miss"] += 1
                ch["x"], ch["y"] = px, py
                ch["hist"].append(False)
            else:
                c = cands[best]; used.add(best)
                a = 0.5
                ch["vx"] = (1 - a) * ch["vx"] + a * (c.x - ch["x"]); ch["vy"] = (1 - a) * ch["vy"] + a * (c.y - ch["y"])
                ch["x"], ch["y"] = c.x, c.y
                ch["miss"] = 0; ch["hits"] += 1; ch["snr"].append(c.snr); ch["sig"].append(c.sigma); ch["hist"].append(True)
                ch["last"] = c
        self._chains = [ch for ch in self._chains if ch["miss"] <= 2][:600]
        # unmatched candidates start new chains (velocity unknown, learned on the next hit)
        for i, c in enumerate(cands):
            if i not in used and len(self._chains) < 600:
                self._chains.append({"x": c.x, "y": c.y, "vx": 0.0, "vy": 0.0, "miss": 0, "hits": 1,
                                     "snr": [c.snr], "sig": [c.sigma], "hist": [True], "last": c})
        # promotion: hit in at least 6 of the last 8 frames, a credible mean SNR, and a spot
        # whose fitted size is within a factor of two of the designated beacon's
        exp_sigma = max(0.6, (self.classical.expected_size_px or 8.0) / 3.0)
        ready = []
        for ch in self._chains:
            h = ch["hist"][-8:]
            if len(h) >= 8 and sum(h) >= 6 and float(np.mean(ch["snr"][-6:])) >= self.tc.faint_snr_min:
                sig = float(np.median(ch["sig"][-6:]))
                if abs(np.log(max(sig, 0.3) / exp_sigma)) < np.log(2.2):
                    ready.append((float(np.mean(ch["snr"][-6:])), ch))
        if not ready:
            return None
        ready.sort(key=lambda r: -r[0])
        ch = ready[0][1]
        self._chains = []
        self.provisional = True
        self.faint = True
        self._faint_q = []
        self._faint_v = (ch["vx"], ch["vy"])
        last = ch["last"]   # appearance of the real detection, so the track's signature is realistic
        return Candidate(ch["x"], ch["y"], last.area, last.peak, float(np.mean(ch["snr"][-6:])), float(np.median(ch["sig"][-6:])), 0.5, "classical", True, last.bw, last.bh, last.hm_area)

    def _associate(self, cands: list[Candidate]) -> tuple[Candidate | None, float]:
        """Gate candidates by Mahalanobis distance, then score by gate and signature."""
        if self.faint:
            return self._associate_faint(cands)
        best, best_score, best_g = None, 1e9, 0.0
        px, py = self.imm.position()
        gate = min((self.tc.gate_px + 4 * self.jitter_sigma) * (1 + 0.5 * self.miss_count), 320.0)
        for c in cands:
            if np.hypot(c.x - px, c.y - py) > gate:
                continue
            # the appearance comparison needs the fitted width, so the few candidates inside
            # the gate are refined here (the detector leaves refinement to whoever needs it)
            if self._det_img is not None:
                c = self.classical.refine(self._det_img, c)
            if c.sigma < self.MIN_SIGMA:      # a single hot pixel (salt, cosmic ray), not a 5 to 20 px spot
                continue
            g = self.imm.gate(c.x, c.y)
            sd = _signature_distance(self.designated_sig, _signature(c))
            # appearance rejection once a signature exists (TRACK, COAST, REACQUIRE); in VERIFY
            # the signature is one frame old and noisy, so position consistency alone decides
            if self.mode != Mode.VERIFY and sd > 1.1:
                continue
            score = g + 2.0 * sd - 0.5 * c.confidence
            if score < best_score:
                best, best_score, best_g = c, score, g
        return best, best_g

    def _associate_faint(self, cands: list[Candidate]) -> tuple[Candidate | None, float]:
        """A faint target sits among noise clumps of similar size, so the gate is small and
        the strongest matched-filter response inside it wins. A running quality measure
        drops the track back to the chain search when what it accepts is no better than
        noise, instead of letting the estimate wander off on noise."""
        px, py = self.imm.position()
        gate = min(12.0 + 3.0 * self.jitter_sigma, 40.0) * (1 + 0.3 * self.miss_count)
        best, best_g = None, 0.0
        for c in cands:
            if c.snr < 2.5 or np.hypot(c.x - px, c.y - py) > gate:
                continue
            g = self.imm.gate(c.x, c.y)
            if g > 5.0:
                continue
            if best is None or c.snr > best.snr:
                best, best_g = c, g
        if best is not None:
            self._faint_q.append(best.snr)
            self._faint_q = self._faint_q[-12:]
            if len(self._faint_q) >= 12 and float(np.mean(self._faint_q)) < 3.0:
                self._set(Mode.SEARCH)
                self.imm.initialised = False
                self.faint = False
                self._faint_q = []
                return None, 0.0
        return best, best_g

    def _update_signature(self, c: Candidate):
        s = _signature(c)
        if self.designated_sig is None:
            self.designated_sig = s
        else:
            # an appearance far from the running signature means two spots have merged (a
            # decoy crossing the beacon) or a burst of noise; the signature is not allowed to
            # drift towards it, so that when the spots separate the beacon still matches
            if _signature_distance(self.designated_sig, s) > 0.6:
                return
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
