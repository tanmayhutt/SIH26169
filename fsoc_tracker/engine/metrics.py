"""Summary metrics with explicit definitions, and pass/fail against the PS specification
(rows 16 to 20). Every definition string is printed in the report next to its value."""
from __future__ import annotations

import math
from dataclasses import dataclass, field, asdict

import numpy as np

from .telemetry import Record

SPEC = {
    "acquisition_time_s": ("<=", 2.0),
    "tracking_err_mean_px": ("<=", 10.0),
    "target_loss_pct": ("<", 5.0),
    "reacq_time_max_s": ("<=", 1.0),
    "fps_mean": (">=", 20.0),
}

DEFINITIONS = {
    "duration_s": "Simulation duration: last frame time minus first, in seconds.",
    "frames": "Number of frames processed.",
    "fps_mean": "Processing speed: mean of 1 / per-frame processing time. Spec row 20: >= 20 FPS.",
    "fps_p5": "5th percentile of instantaneous processing FPS (a slow-frame indicator).",
    "fps_wall": "Frames divided by wall-clock seconds, including rendering and display.",
    "proc_ms_mean": "Mean processing time per frame in milliseconds (detection, estimation, control).",
    "proc_ms_p99": "99th percentile processing time per frame in milliseconds.",
    "proc_ms_max": "Maximum processing time per frame in milliseconds.",
    "acquisition_time_s": "Acquisition time: first frame in TRACK with the tracked beacon within the capture radius (default 30 px) of the window centre, from t = 0. Spec row 16: <= 2 s.",
    "reacq_count": "Number of times lock was lost and regained.",
    "reacq_time_mean_s": "Mean time from losing lock to regaining it.",
    "reacq_time_max_s": "Maximum time from losing lock to regaining it. Spec row 19: <= 1 s.",
    "tracking_err_mean_px": "Tracking error: mean distance from the true beacon to the window centre over frames after acquisition. Spec row 17: <= 10 px.",
    "tracking_err_max_px": "Maximum tracking error over frames after acquisition.",
    "tracking_err_rmse_px": "Root mean square tracking error over frames after acquisition.",
    "tracking_err_mean_deg": "Mean tracking error in degrees (pixels times IFOV).",
    "tracking_err_stab_mean_px": "Tracking error with the per-frame camera vibration removed from the truth: the part a rate-limited gimbal can physically follow.",
    "tracking_err_stab_rmse_px": "RMSE of the vibration-removed tracking error.",
    "centroid_err_mean_px": "Centroiding error: mean distance from our measured centroid to the true centroid, over frames with a detection.",
    "centroid_err_max_px": "Maximum centroiding error.",
    "centroid_err_rmse_px": "RMSE of centroiding error.",
    "lock_retention_pct": "Lock retention rate: percentage of frames after acquisition in which the tracker was in TRACK with the beacon within the capture radius of the window centre.",
    "target_loss_pct": "Target loss: 100 minus lock retention. Spec row 18: < 5%.",
    "slew_saturation_pct": "Percentage of frames in which the commanded rate exceeded the gimbal limit on either axis.",
    "cnn_frames_pct": "Percentage of frames in which the AI detector provided the accepted measurement.",
}


@dataclass
class Summary:
    values: dict = field(default_factory=dict)
    passed: dict = field(default_factory=dict)
    truth_available: bool = True

    def to_dict(self):
        return {"values": self.values, "passed": self.passed, "truth_available": self.truth_available,
                "definitions": {k: DEFINITIONS[k] for k in self.values if k in DEFINITIONS}}


def _pct(a, q):
    return float(np.percentile(a, q)) if len(a) else float("nan")


def summarise(records: list[Record], ifov_deg: float, wall_s: float) -> Summary:
    s = Summary()
    if not records:
        return s
    n = len(records)
    t = np.array([r.t_sim for r in records])
    proc = np.array([r.proc_ms for r in records])
    fps_i = np.array([r.fps_inst for r in records])
    locked = np.array([r.locked for r in records], bool)
    inwin = np.array([r.in_window for r in records])
    truth_ok = np.isfinite([r.true_x for r in records]).any()
    s.truth_available = bool(truth_ok)
    good = locked & (inwin == 1) if truth_ok else locked
    v = s.values
    v["duration_s"] = float(t[-1] - t[0] + (t[1] - t[0] if n > 1 else 0))
    v["frames"] = n
    v["fps_mean"] = float(np.mean(fps_i))
    v["fps_p5"] = _pct(fps_i, 5)
    v["fps_wall"] = float(n / wall_s) if wall_s > 0 else float("nan")
    v["proc_ms_mean"] = float(proc.mean())
    v["proc_ms_p99"] = _pct(proc, 99)
    v["proc_ms_max"] = float(proc.max())
    # acquisition
    idx = np.flatnonzero(good)
    if len(idx):
        first = int(idx[0])
        v["acquisition_time_s"] = float(t[first])
        after = np.arange(n) >= first
        # re-acquisitions: runs of not-good after first acquisition
        re_times = []
        losing = False
        t_lost = 0.0
        for i in range(first, n):
            if good[i] and losing:
                re_times.append(t[i] - t_lost)
                losing = False
            elif not good[i] and not losing:
                losing = True
                t_lost = t[i]
        v["reacq_count"] = len(re_times)
        v["reacq_time_mean_s"] = float(np.mean(re_times)) if re_times else 0.0
        v["reacq_time_max_s"] = float(np.max(re_times)) if re_times else 0.0
        v["lock_retention_pct"] = float(100 * good[after].mean())
        v["target_loss_pct"] = 100 - v["lock_retention_pct"]
        if truth_ok:
            te = np.array([r.tracking_err_px for r in records])[after]
            te = te[np.isfinite(te)]
            if len(te):
                v["tracking_err_mean_px"] = float(te.mean())
                v["tracking_err_max_px"] = float(te.max())
                v["tracking_err_rmse_px"] = float(np.sqrt(np.mean(te ** 2)))
                v["tracking_err_mean_deg"] = v["tracking_err_mean_px"] * ifov_deg
            ts = np.array([r.tracking_err_stab_px for r in records])[after]
            ts = ts[np.isfinite(ts)]
            if len(ts):
                v["tracking_err_stab_mean_px"] = float(ts.mean())
                v["tracking_err_stab_rmse_px"] = float(np.sqrt(np.mean(ts ** 2)))
    else:
        v["acquisition_time_s"] = float("nan")
        v["lock_retention_pct"] = 0.0
        v["target_loss_pct"] = 100.0
    if truth_ok:
        ce = np.array([r.centroid_err_px for r in records])
        ce = ce[np.isfinite(ce)]
        if len(ce):
            v["centroid_err_mean_px"] = float(ce.mean())
            v["centroid_err_max_px"] = float(ce.max())
            v["centroid_err_rmse_px"] = float(np.sqrt(np.mean(ce ** 2)))
    sat = np.array([(r.sat_pan or r.sat_tilt) for r in records])
    v["slew_saturation_pct"] = float(100 * sat.mean())
    v["cnn_frames_pct"] = float(100 * np.mean([r.tier == "cnn" for r in records]))
    # pass / fail
    for k, (op, lim) in SPEC.items():
        if k not in v or (isinstance(v[k], float) and math.isnan(v[k])):
            s.passed[k] = None
            continue
        x = v[k]
        s.passed[k] = {"<=": x <= lim, "<": x < lim, ">=": x >= lim}[op]
    return s
