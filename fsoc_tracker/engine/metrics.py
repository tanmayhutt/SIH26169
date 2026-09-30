"""Summary metrics with explicit definitions, and pass/fail against the PS specification
(rows 16 to 20). Every definition string is printed in the report next to its value."""
from __future__ import annotations

import math
from dataclasses import dataclass, field

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
    "fps_mean": "Processing speed: frames per second of processing time (1000 / mean processing ms). Spec row 20: >= 20 FPS.",
    "fps_inst_mean": "Mean of the per-frame rates 1 / processing time; higher than fps_mean when frame times vary, shown for comparison only.",
    "fps_p5": "5th percentile of instantaneous processing FPS (a slow-frame indicator).",
    "fps_wall": "Frames divided by wall-clock seconds, including rendering and display.",
    "proc_ms_mean": "Mean processing time per frame in milliseconds (detection, estimation, control).",
    "proc_ms_p99": "99th percentile processing time per frame in milliseconds.",
    "proc_ms_max": "Maximum processing time per frame in milliseconds.",
    "acquisition_time_s": "Acquisition time: first frame in TRACK with the tracked beacon within the capture radius (default 30 px) of the window centre, from t = 0. Spec row 16: <= 2 s.",
    "reacq_count": "Number of times lock was lost and regained.",
    "reacq_time_mean_s": "Mean time from losing lock to regaining it.",
    "reacq_time_max_s": "Maximum time from losing lock to regaining it; a loss not regained by the end of the run counts with its length so far. Spec row 19: <= 1 s.",
    "handoff_time_s": "Handoff ready: first time the coarse alignment was stable enough for fine pointing to take over (locked, the estimate within the handoff radius, default 10 px as PS row 17, of the window centre for the hold time, default 1 s).",
    "lock_retention_received_pct": "Lock retention over the frames that did arrive (only with frame loss): a lost frame leaves the tracker blind and breaks lock by definition; this shows how well it held on the pictures it received.",
    "frames_lost_pct": "Percentage of frames the camera link lost (simulated frame loss): they reached the tracker with no picture.",
    "handoff_pct": "Percentage of frames after the first handoff-ready frame that were still handoff ready.",
    "lock_lost_at_end_s": "Length of a lock loss still open when the run ended (0 if the run ended locked).",
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
    "tracked_pct": "Tracked rate: percentage of frames after acquisition in which the tracker held the beacon (state TRACK), whether or not the camera had it centred. Lock retention adds the centring condition.",
    "target_loss_pct": "Target loss: 100 minus lock retention. Spec row 18: < 5%.",
    "slew_saturation_pct": "Percentage of frames in which the commanded rate exceeded the gimbal limit on either axis.",
    "cnn_frames_pct": "Percentage of frames in which the AI detector provided the accepted measurement.",
}


@dataclass
class Summary:
    values: dict = field(default_factory=dict)
    passed: dict = field(default_factory=dict)
    truth_available: bool = True
    designation: dict = field(default_factory=dict)   # which target was followed, and how it was designated
    checks: list = field(default_factory=list)        # scenario check notes (engine/checks.py)
    segments: list = field(default_factory=list)      # one entry per disturbance setting during the run

    def to_dict(self):
        return {"values": self.values, "passed": self.passed, "truth_available": self.truth_available,
                "designation": self.designation, "checks": self.checks,
                "definitions": {k: DEFINITIONS[k] for k in self.values if k in DEFINITIONS},
                "segments": self.segments}


def _pct(a, q):
    return float(np.percentile(a, q)) if len(a) else float("nan")


def summarise(records: list[Record], ifov_deg: float, wall_s: float, changes: list[dict] | None = None) -> Summary:
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
    # the processing rate is frames over processing time; the mean of per-frame rates would
    # overstate it whenever frame times vary (a few slow frames barely move that mean)
    v["fps_mean"] = float(1000.0 / max(float(proc.mean()), 1e-6))
    v["fps_inst_mean"] = float(np.mean(fps_i))
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
        # a loss still open when the run ends was never re-acquired; it has lasted at least
        # until the last frame, so it bounds the maximum re-acquisition time from below
        dt = float(t[1] - t[0]) if n > 1 else 0.0
        open_loss = float(t[-1] - t_lost + dt) if losing else 0.0
        v["reacq_count"] = len(re_times)
        v["reacq_time_mean_s"] = float(np.mean(re_times)) if re_times else 0.0
        v["reacq_time_max_s"] = float(max(re_times + [open_loss])) if (re_times or losing) else 0.0
        v["lock_lost_at_end_s"] = open_loss
        v["lock_retention_pct"] = float(100 * good[after].mean())
        v["target_loss_pct"] = 100 - v["lock_retention_pct"]
        v["tracked_pct"] = float(100 * np.mean([r.mode == "TRACK" for r in records[first:]]))
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
        v["tracked_pct"] = 0.0
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
    ho = np.array([getattr(r, "handoff", 0) for r in records], bool)
    hi = np.flatnonzero(ho)
    v["handoff_time_s"] = float(t[hi[0]]) if len(hi) else float("nan")
    v["handoff_pct"] = float(100 * ho[hi[0]:].mean()) if len(hi) else 0.0
    lost = np.array([getattr(r, "frame_lost", 0) for r in records], bool)
    v["frames_lost_pct"] = float(100 * lost.mean())
    acq = np.flatnonzero(good)
    if lost.any() and len(acq):
        kept = (np.arange(n) >= acq[0]) & ~lost
        v["lock_retention_received_pct"] = float(100 * good[kept].mean()) if kept.any() else float("nan")
    if changes:
        s.segments = segment_summaries(records, good, changes)
    # pass / fail
    for k, (op, lim) in SPEC.items():
        if k not in v or (isinstance(v[k], float) and math.isnan(v[k])):
            s.passed[k] = None
            continue
        x = v[k]
        s.passed[k] = {"<=": x <= lim, "<": x < lim, ">=": x >= lim}[op]
    return s


SEGMENT_DEFINITION = ("When the disturbances change during a run, each setting is a segment. Per segment: tracking, "
                      "vibration-removed and centroiding error means, lock retention and tracked rate over its frames "
                      "after the first acquisition of the run, and FPS as frames over processing time. The run's overall figures "
                      "above span every segment.")


def _mean(a) -> float | None:
    a = np.asarray(a, float)
    a = a[np.isfinite(a)]
    return float(a.mean()) if len(a) else None


def segment_summaries(records: list[Record], good: np.ndarray, changes: list[dict]) -> list[dict]:
    """Metrics for each disturbance setting of a run that changed during the run."""
    seg = np.array([r.segment for r in records])
    t = np.array([r.t_sim for r in records])
    dt = float(t[1] - t[0]) if len(t) > 1 else 0.0
    acquired = np.flatnonzero(good)
    first = int(acquired[0]) if len(acquired) else len(records)
    what = {c["segment"]: c["what"] for c in changes}
    out = []
    for k in sorted(set(seg.tolist())):
        idx = np.flatnonzero(seg == k)
        after = idx[idx >= first]
        pick = lambda name: [getattr(records[i], name) for i in after]
        out.append({
            "segment": int(k), "t_start_s": float(t[idx[0]]), "t_end_s": float(t[idx[-1]] + dt), "frames": int(len(idx)),
            "change": what.get(k, "settings at the start of the run"),
            "tracking_err_mean_px": _mean(pick("tracking_err_px")),
            "tracking_err_stab_mean_px": _mean(pick("tracking_err_stab_px")),
            "centroid_err_mean_px": _mean([records[i].centroid_err_px for i in idx]),
            "lock_retention_pct": float(100 * good[after].mean()) if len(after) else None,
            "tracked_pct": float(100 * np.mean([records[i].mode == "TRACK" for i in after])) if len(after) else None,
            # frames over processing time, as fps_mean for the whole run
            "fps_mean": 1000.0 / max(float(np.mean([records[i].proc_ms for i in idx])), 1e-6),
        })
    return out
