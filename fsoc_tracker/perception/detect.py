"""Beacon detection and sub-pixel centroiding.

Tier 1 (classical): background estimate, adaptive threshold, connected components, shape
filters, then an intensity-weighted centre of gravity refined by a 2D Gaussian fit.
Tier 2 (CNN): a small ONNX heat-map network, engaged when Tier 1 confidence is low. The
classical path is always available so speed and reliability never depend on the model.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from scipy.optimize import least_squares

from ..engine.config import TrackerConfig
from ..world.sprites import make_sprite


@dataclass
class Candidate:
    x: float               # centroid in picture px
    y: float
    area: int
    peak: float
    snr: float
    sigma: float           # fitted PSF width
    confidence: float      # 0..1
    source: str = "classical"
    refined: bool = True   # sub-pixel fit done; False means a blob-based estimate (see ClassicalDetector.refine)
    hm_area: int = 0       # pixels above half of the spot's height over the local background
    bw: int = 0            # blob extent, for a later refinement
    bh: int = 0


def _roi_bounds(shape, cx, cy, half):
    h, w = shape
    xa, ya = int(max(cx - half, 0)), int(max(cy - half, 0))
    xb, yb = int(min(cx + half, w)), int(min(cy + half, h))
    return xa, ya, xb, yb


def refine_centroid(img: np.ndarray, x: float, y: float, r: int = 7) -> tuple[float, float, float]:
    """Intensity-weighted centre of gravity on a background-subtracted patch, then a 2D
    Gaussian least-squares fit. Returns (x, y, sigma) in picture pixels."""
    h, w = img.shape
    xa, ya = int(max(round(x) - r, 0)), int(max(round(y) - r, 0))
    xb, yb = int(min(round(x) + r + 1, w)), int(min(round(y) + r + 1, h))
    patch = img[ya:yb, xa:xb].astype(np.float32)
    if patch.size < 9:
        return x, y, 2.0
    # background from the patch border
    border = np.concatenate([patch[0], patch[-1], patch[:, 0], patch[:, -1]])
    bg = float(np.median(border))
    p = np.clip(patch - bg, 0, None)
    tot = p.sum()
    if tot <= 1e-6:
        return x, y, 2.0
    yy, xx = np.mgrid[ya:yb, xa:xb].astype(np.float32)
    cx = float((p * xx).sum() / tot)
    cy = float((p * yy).sum() / tot)
    sig = float(np.sqrt(max((p * ((xx - cx) ** 2 + (yy - cy) ** 2)).sum() / tot / 2, 0.25)))
    # Gaussian fit for sub-pixel refinement (fast: small patch, few iterations)
    try:
        amp0 = float(p.max())

        def resid(q):
            a, mx, my, s = q
            g = a * np.exp(-((xx - mx) ** 2 + (yy - my) ** 2) / (2 * s * s))
            return (g - p).ravel()

        sol = least_squares(resid, [amp0, cx, cy, max(sig, 0.8)], max_nfev=25,
                            bounds=([0, xa, ya, 0.4], [1e4, xb, yb, 20.0]))
        if sol.success and np.isfinite(sol.x).all():
            _, cx, cy, sig = sol.x
    except Exception:
        pass
    return float(cx), float(cy), float(sig)


class ClassicalDetector:
    def __init__(self, cfg: TrackerConfig, expected_size_px: float | None = None, expected_shape: str = "square",
                 expected_dims: tuple[float, float] | None = None, expected_mask: str = ""):
        self.cfg = cfg
        # the designated beacon's size from config, if known. For a spot of unequal width and
        # height (PS row 10) the size priors use the geometric mean, and the width calibration
        # below renders the real shape.
        if expected_dims is not None and expected_dims[0] and expected_dims[1]:
            self.expected_dims = (float(expected_dims[0]), float(expected_dims[1]))
            expected_size_px = float(np.sqrt(self.expected_dims[0] * self.expected_dims[1]))
        else:
            self.expected_dims = (float(expected_size_px), float(expected_size_px)) if expected_size_px else None
        self.expected_size_px = expected_size_px
        self.expected_shape = expected_shape
        self.expected_mask = expected_mask

    def expected_area(self) -> float | None:
        """Blob area the designated beacon produces after the matched filter, in px."""
        if not self.expected_size_px:
            return None
        mf = max(0.6, self.expected_size_px / 3.0)
        return (self.expected_size_px + 2.0 * mf) ** 2

    def expected_sigma(self) -> float | None:
        """Width the designated beacon's spot shows to `refine_centroid` (a second-moment
        estimate), measured once on a noise-free rendering of the configured sprite so the
        estimator's own bias is included. Unlike the thresholded blob area this does not
        move with the noise level."""
        s = self.expected_size_px
        if not s:
            return None
        legacy = self.expected_shape in ("square", "circle", "gaussian") and (
            self.expected_dims is None or abs(self.expected_dims[0] - self.expected_dims[1]) < 1e-6)
        if getattr(self, "_exp_sigma", None) is None and not legacy:
            w, h = self.expected_dims
            spr = make_sprite(self.expected_shape, int(round(w)), int(round(h)), self.expected_mask)
            sh, sw = spr.shape
            ph, pw = sh + 40, sw + 40
            sp = np.zeros((ph, pw), np.float32)
            sp[20:20 + sh, 20:20 + sw] = spr
            c_x, c_y = 20 + (sw - 1) / 2.0, 20 + (sh - 1) / 2.0
            patch = np.clip(20 + 200 * sp / max(sp.max(), 1e-6), 0, 255).astype(np.uint8)
            _, _, self._exp_sigma = refine_centroid(patch, float(c_x), float(c_y), r=max(6, int(max(w, h)) + 4))
            self._exp_hm = int(np.count_nonzero(patch > 20 + 100))
        if getattr(self, "_exp_sigma", None) is None:
            n = int(s) + 40
            sp = np.zeros((n, n), np.float32)
            c = n // 2
            if self.expected_shape == "gaussian":
                yy, xx = np.mgrid[0:n, 0:n]
                sig = max(s, 2) / 3.0
                sp = np.exp(-((xx - c) ** 2 + (yy - c) ** 2) / (2 * sig * sig)).astype(np.float32)
            elif self.expected_shape == "circle":
                cv2.circle(sp, (c, c), max(int(s) // 2, 1), 1.0, -1, lineType=cv2.LINE_AA)
                sp = cv2.GaussianBlur(sp, (0, 0), 0.6)
            else:
                h = max(int(s), 2) // 2
                sp[c - h:c - h + max(int(s), 2), c - h:c - h + max(int(s), 2)] = 1.0
                sp = cv2.GaussianBlur(sp, (0, 0), 0.6)
            patch = np.clip(20 + 200 * sp / sp.max(), 0, 255).astype(np.uint8)
            _, _, self._exp_sigma = refine_centroid(patch, float(c), float(c), r=max(6, int(s) + 4))
            self._exp_hm = int(np.count_nonzero(patch > 20 + 100))
        return float(self._exp_sigma)

    def expected_hm_area(self) -> float | None:
        """Half-maximum footprint of the designated beacon's sprite, in px (see expected_sigma)."""
        if not self.expected_size_px:
            return None
        self.expected_sigma()
        return float(self._exp_hm)

    def detect(self, img: np.ndarray, roi: tuple[int, int, int, int] | None = None,
               k: float | None = None, mf_sigma: float | None = None, refine: int = 3, limit: int = 12) -> list[Candidate]:
        """Find bright compact blobs. `roi` = (xa, ya, xb, yb) restricts the search.
        `k` overrides the threshold (in noise sigmas), `mf_sigma` the matched-filter width;
        the faint-beacon path lowers both and asks for many unrefined candidates."""
        if roi is not None:
            xa, ya, xb, yb = roi
            sub = img[ya:yb, xa:xb]
        else:
            xa = ya = 0
            sub = img
        if sub.size == 0:
            return []
        # remove isolated specks (salt and pepper) before statistics. Under heavy salt and
        # pepper, 2 to 3 pixel clusters survive a 3x3 median, so add a 5x5 pass when the
        # fraction of saturated pixels says the noise is heavy.
        probe = sub[::7, ::7]
        salt, pepper = np.count_nonzero(probe == 255), np.count_nonzero(probe == 0)
        sp_level = min(salt, pepper) / probe.size          # a dark clipped sky has pepper only
        if sp_level > 0.01:
            med = cv2.medianBlur(cv2.medianBlur(sub, 3), 5)
        elif sp_level > 0.001:
            med = cv2.medianBlur(sub, 3)
        else:
            med = sub          # a median clips faint beacons; Gaussian noise is handled by the matched filter
        # background: heavy blur approximates the smooth sky; subtract it. Signed float from
        # here on: a uint8 subtraction clips the negative half and quantises the matched-filter
        # response to whole grey levels, which buried faint beacons (response 6 to 8 levels
        # against a threshold of 9).
        bg = cv2.blur(med, (31, 31))
        diff = cv2.subtract(med, bg, dtype=cv2.CV_16S)      # signed, integer, fast
        # matched filter: smoothing at the beacon's scale raises the SNR of an extended
        # spot against single-pixel noise and point-like stars
        mf = mf_sigma if mf_sigma is not None else (max(0.6, self.expected_size_px / 3.0) if self.expected_size_px else 0.0)
        if mf > 0:
            diff = cv2.GaussianBlur(diff, (0, 0), mf)
        # robust noise level (median absolute deviation): stars and the beacon itself must
        # not inflate the threshold they are measured against
        probe_d = diff[::8, ::8] if diff.shape[0] > 800 else diff[::2, ::2]
        level = float(np.median(probe_d))
        noise = float(max(np.median(np.abs(probe_d - level)) * 1.4826, 0.5))
        thr = level + (k if k is not None else self.cfg.threshold_k) * noise
        mask = cv2.compare(diff, thr, cv2.CMP_GT)
        n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
        out: list[Candidate] = []
        for i in range(1, n):
            area = int(stats[i, cv2.CC_STAT_AREA])
            if area < self.cfg.min_area_px or area > self.cfg.max_area_px:
                continue
            bw, bh = stats[i, cv2.CC_STAT_WIDTH], stats[i, cv2.CC_STAT_HEIGHT]
            if max(bw, bh) / max(min(bw, bh), 1) > 3.0:      # streaks are not beacons
                continue
            fill = area / float(bw * bh)
            if fill < 0.3:
                continue
            cx, cy = cents[i]
            x0, y0 = int(stats[i, cv2.CC_STAT_LEFT]), int(stats[i, cv2.CC_STAT_TOP])
            peak = float(med[y0:y0 + bh, x0:x0 + bw].max())
            hm_area = 0
            snr = (float(diff[y0:y0 + bh, x0:x0 + bw].max()) - level) / noise   # matched-filter SNR
            # confidence: SNR (saturating softly), peak brightness, and size match to the
            # designated beacon when its size is known. Bright stars are small and dim
            # compared with a beacon, so both terms separate them.
            c_snr = 1.0 - np.exp(-snr / 25.0)
            c_peak = peak / 255.0
            c_size = 1.0
            exp_area = self.expected_area()
            if exp_area:
                c_size = float(np.exp(-abs(np.log((area + 1) / (exp_area + 1))) * 0.9))
            # SNR alone is high for any bright point on a dark sky (a star), so size match
            # and peak brightness carry most of the weight
            conf = float(np.clip(0.30 * c_snr + 0.35 * c_peak + 0.35 * c_size, 0, 1))
            out.append((conf, cx + xa, cy + ya, area, peak, snr, bw, bh, hm_area))
        out.sort(key=lambda r: -r[5] if k is not None else -r[0])   # faint path ranks by matched-filter SNR
        res: list[Candidate] = []
        for j, (conf, cx, cy, area, peak, snr, bw, bh, hm_area) in enumerate(out[:limit]):
            # sub-pixel refinement (a Gaussian least-squares fit) is the expensive step, so
            # only leading candidates that look like a beacon get it here; whichever
            # candidate the tracker finally picks is refined by `refine()` before use
            if j < refine and conf >= 0.35:
                gx, gy, sig = refine_centroid(img, cx, cy, r=max(6, int(max(bw, bh))))
                res.append(Candidate(gx, gy, area, peak, snr, sig, conf, "classical", True, int(bw), int(bh), hm_area))
            else:
                res.append(Candidate(float(cx), float(cy), area, peak, snr, float(max(bw, bh)) / 3.0, conf, "classical", False, int(bw), int(bh), hm_area))
        return res


    def refine(self, img: np.ndarray, c: Candidate) -> Candidate:
        """Sub-pixel fit for a candidate that was returned unrefined."""
        if c.refined:
            return c
        gx, gy, sig = refine_centroid(img, c.x, c.y, r=max(6, int(max(c.bw, c.bh))))
        return Candidate(gx, gy, c.area, c.peak, c.snr, sig, c.confidence, c.source, True, c.bw, c.bh, c.hm_area)


class CNNDetector:
    """Heat-map network on a region of interest. Optional; loads lazily."""

    def __init__(self, model_path: str, patch: int = 128):
        self.patch = patch
        self.session = None
        # a relative path is tried from the working folder, then from the package's own folder,
        # so an installed command started anywhere still finds the model
        p = Path(model_path)
        if not p.is_absolute() and not p.exists():
            for base in (Path(__file__).resolve().parents[2], Path(__file__).resolve().parents[1]):
                if (base / p).exists():
                    p = base / p
                    break
        self.path = p

    def available(self) -> bool:
        if self.session is not None:
            return True
        if not self.path.exists():
            return False
        try:
            import onnxruntime as ort
            so = ort.SessionOptions()
            so.intra_op_num_threads = 2
            self.session = ort.InferenceSession(str(self.path), so, providers=["CPUExecutionProvider"])
            self.input_name = self.session.get_inputs()[0].name
            return True
        except Exception:
            return False

    def warm_up(self) -> None:
        """Load the model and run one inference on an empty patch, so the first real call
        during tracking does not pay the session start-up (about 1.5 s on a laptop)."""
        if self.available():
            try:
                x = np.zeros((1, 1, self.patch, self.patch), np.float32)
                self.session.run(None, {self.input_name: x})
            except Exception:
                pass

    def detect(self, img: np.ndarray, cx: float, cy: float) -> Candidate | None:
        if not self.available():
            return None
        half = self.patch // 2
        H, W = img.shape
        if not (-half < cx < W + half and -half < cy < H + half):
            return None            # prediction is off the picture; nothing to look at
        xa, ya, xb, yb = _roi_bounds(img.shape, cx, cy, half)
        if xb - xa < 16 or yb - ya < 16:
            return None
        crop = np.zeros((self.patch, self.patch), np.float32)
        sub = img[ya:yb, xa:xb].astype(np.float32) / 255.0
        crop[:sub.shape[0], :sub.shape[1]] = sub
        crop = (crop - crop.mean()) / (crop.std() + 1e-3)
        heat = self.session.run(None, {self.input_name: crop[None, None]})[0][0, 0]
        heat = 1 / (1 + np.exp(-heat))
        py, px = np.unravel_index(int(np.argmax(heat)), heat.shape)
        conf = float(heat[py, px])
        if conf < 0.3:
            return None
        # soft-argmax in a 5x5 neighbourhood for sub-pixel position
        y0, y1 = max(py - 2, 0), min(py + 3, heat.shape[0])
        x0, x1 = max(px - 2, 0), min(px + 3, heat.shape[1])
        w = heat[y0:y1, x0:x1]
        yy, xx = np.mgrid[y0:y1, x0:x1]
        sx = float((w * xx).sum() / w.sum())
        sy = float((w * yy).sum() / w.sum())
        scale = self.patch / heat.shape[0]
        gx, gy = xa + (sx + 0.5) * scale, ya + (sy + 0.5) * scale
        gx, gy, sig = refine_centroid(img, gx, gy, r=6)
        return Candidate(gx, gy, 0, float(img[int(gy), int(gx)]) if 0 <= int(gy) < img.shape[0] and 0 <= int(gx) < img.shape[1] else 0.0,
                         0.0, sig, conf, "cnn")
