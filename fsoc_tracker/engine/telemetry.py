"""One record per frame, written to CSV and kept in memory for metrics and plots."""
from __future__ import annotations

import csv
from dataclasses import dataclass, asdict, fields
from pathlib import Path


@dataclass
class Record:
    frame: int
    t_sim: float
    t_wall: float
    proc_ms: float
    fps_inst: float
    mode: str
    locked: int
    tier: str
    n_candidates: int
    confidence: float
    snr: float
    sigma: float
    gate: float
    # camera window
    cam_pan_deg: float
    cam_tilt_deg: float
    win_cx: float
    win_cy: float
    cmd_pan_rate: float
    cmd_tilt_rate: float
    sat_pan: int
    sat_tilt: int
    # measurement and estimate
    det_x: float
    det_y: float
    est_x: float
    est_y: float
    pred_x: float
    pred_y: float
    vel_x: float
    vel_y: float
    uncertainty_px: float
    p_cv: float
    p_ca: float
    p_ct: float
    ego_dx: float
    ego_dy: float
    # truth (NaN when unknown)
    true_x: float
    true_y: float
    true_visible: int
    in_window: int
    tracking_err_px: float      # true beacon to window centre
    tracking_err_deg: float
    tracking_err_stab_px: float # same, with the per-frame vibration removed
    centroid_err_px: float      # measured centroid to true centroid
    platform_dx: float
    platform_dy: float
    jitter_dx: float
    jitter_dy: float
    # disturbance segment: 0 until the first change during the run, then 1, 2, ...
    segment: int = 0


COLUMNS = [f.name for f in fields(Record)]


class Telemetry:
    def __init__(self, path: Path | None = None):
        self.records: list[Record] = []
        self.path = path
        self._fh = None
        self._w = None
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._fh = open(path, "w", newline="", encoding="utf-8")
            self._w = csv.DictWriter(self._fh, fieldnames=COLUMNS)
            self._w.writeheader()

    def add(self, r: Record):
        self.records.append(r)
        if self._w is not None:
            self._w.writerow({k: (f"{v:.4f}" if isinstance(v, float) else v) for k, v in asdict(r).items()})

    def close(self):
        if self._fh is not None:
            self._fh.close()
            self._fh = None
