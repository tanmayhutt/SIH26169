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
    def __init__(self, cfg: TrackerConfig, expected_size_px: float | None = None):
        self.cfg = cfg
        self.expected_size_px = expected_size_px   # designated beacon size from config, if known

    def expected_area(self) -> float | None:
        """Blob area the designated beacon produces after the matched filter, in px."""
        if not self.expected_size_px:
            return None
        mf = max(0.6, self.expected_size_px / 3.0)
        return (self.expected_size_px + 2.0 * mf) ** 2

    def detect(self, img: np.ndarray, roi: tuple[int, int, int, int] | None = None) -> list[Candidate]:
        """Find bright compact blobs. `roi` = (xa, ya, xb, yb) restricts the search."""
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
        # background: heavy blur approximates the smooth sky; subtract it
        bg = cv2.blur(med, (31, 31))
        diff = cv2.subtract(med, bg)
        # matched filter: smoothing at the beacon's scale raises the SNR of an extended
        # spot against single-pixel noise and point-like stars
        if self.expected_size_px:
            mf = max(0.6, self.expected_size_px / 3.0)
            diff = cv2.GaussianBlur(diff, (0, 0), mf)
        mean, std = cv2.meanStdDev(diff)
        thr = float(mean[0][0] + self.cfg.threshold_k * max(std[0][0], 0.5))
        _, mask = cv2.threshold(diff, thr, 255, cv2.THRESH_BINARY)
        n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
        out: list[Candidate] = []
        noise = float(max(std[0][0], 1.0))
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
            snr = (peak - float(mean[0][0])) / noise
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
            out.append((conf, cx + xa, cy + ya, area, peak, snr, bw, bh))
        out.sort(key=lambda r: -r[0])
        res: list[Candidate] = []
        for k, (conf, cx, cy, area, peak, snr, bw, bh) in enumerate(out[:12]):
            if k < 3:      # sub-pixel refinement is the expensive step; only the leaders need it
                gx, gy, sig = refine_centroid(img, cx, cy, r=max(6, int(max(bw, bh))))
            else:
                gx, gy, sig = float(cx), float(cy), float(max(bw, bh)) / 3.0
            res.append(Candidate(gx, gy, area, peak, snr, sig, conf, "classical"))
        return res


class CNNDetector:
    """Heat-map network on a region of interest. Optional; loads lazily."""

    def __init__(self, model_path: str, patch: int = 128):
        self.patch = patch
        self.session = None
        self.path = Path(model_path)

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
