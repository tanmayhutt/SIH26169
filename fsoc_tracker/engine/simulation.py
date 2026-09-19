"""The run loop. One object drives a synthetic or video run frame by frame, so the GUI, the
CLI and the tests all execute exactly the same code path."""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

import cv2
import numpy as np

from ..control.controller import Controller
from ..control.tracker import Mode, Tracker, TrackOutput
from ..perception.egomotion import EgoMotion
from ..world.camera import Gimbal, RateCommand
from .config import RunConfig
from .metrics import Summary, summarise
from .sources import Frame, SyntheticSource, VideoSource, make_source
from .telemetry import Record, Telemetry


@dataclass
class StepResult:
    frame: Frame
    observed: np.ndarray
    track: TrackOutput
    cmd: RateCommand
    record: Record
    window: tuple[int, int, int, int]


class Simulation:
    def __init__(self, cfg: RunConfig, out_dir: Path | None = None, write_csv: bool = True):
        self.cfg = cfg
        self.source = make_source(cfg)
        self.dt = self.source.dt
        self.h, self.w = self.source.shape
        if isinstance(self.source, SyntheticSource):
            self.gimbal = self.source.world.gimbal
        else:
            self.gimbal = Gimbal(cfg.camera, self.w, self.h)
        self.tracker = Tracker(cfg, self.dt, (self.h, self.w))
        self.controller = Controller(cfg.tracker, self.gimbal, self.dt)
        self.ego = EgoMotion()
        self.out_dir = out_dir
        if out_dir is not None:
            out_dir.mkdir(parents=True, exist_ok=True)
        self.telemetry = Telemetry(out_dir / "frames.csv" if (out_dir and write_csv) else None)
        self.t_start = None
        self.summary: Summary | None = None
        self.last_cmd = RateCommand()

    # ------------------------------------------------------------------ run
    def steps(self) -> Iterator[StepResult]:
        self.t_start = time.perf_counter()
        window_only = self.cfg.camera.window_only and isinstance(self.source, SyntheticSource)
        for frame in self.source:
            t0 = time.perf_counter()
            img = frame.image
            obs = self.source.world.observed(img) if isinstance(self.source, SyntheticSource) else img
            # the tracker always works on luminance; a colour frame is display only
            lum = cv2.cvtColor(obs, cv2.COLOR_BGR2GRAY) if obs.ndim == 3 else obs
            # ego-motion: mask the current estimate so the beacon does not bias the shift
            mask_c = self.tracker.imm.position() if self.tracker.imm.initialised else None
            ego_dx, ego_dy, ego_conf = self.ego.step(lum, mask_c)
            self.tracker.observe_ego(ego_dx, ego_dy, ego_conf)
            win_rect = self.gimbal.window_rect()
            out = self.tracker.step(lum, win_rect if window_only else None)
            cmd = self.controller.step(out, ego_dx, ego_dy, window_only)
            acted = self.gimbal.apply(cmd, self.dt)
            self.last_cmd = acted
            proc_ms = (time.perf_counter() - t0) * 1000.0
            rec = self._record(frame, out, acted, proc_ms, ego_dx, ego_dy, win_rect)
            self.telemetry.add(rec)
            yield StepResult(frame, obs, out, acted, rec, win_rect)
        self.finish()

    def run(self, progress: Callable[[int, int], None] | None = None) -> Summary:
        n = getattr(self.source, "n_frames", 0)
        for i, _ in enumerate(self.steps()):
            if progress and i % 30 == 0:
                progress(i, n)
        return self.summary

    def finish(self) -> Summary:
        wall = time.perf_counter() - (self.t_start or time.perf_counter())
        self.telemetry.close()
        self.summary = summarise(self.telemetry.records, self.cfg.camera.ifov_deg, wall)
        if self.out_dir is not None:
            with open(self.out_dir / "summary.json", "w", encoding="utf-8") as f:
                json.dump({"config": self.cfg.to_dict(), **self.summary.to_dict()}, f, indent=2)
            self.cfg.save(self.out_dir / "scenario.yaml")
        return self.summary

    # --------------------------------------------------------------- record
    def _record(self, frame: Frame, out: TrackOutput, cmd: RateCommand, proc_ms: float,
                ego_dx: float, ego_dy: float, win_rect) -> Record:
        nan = float("nan")
        x0, y0, w, h = win_rect
        wcx, wcy = x0 + w / 2, y0 + h / 2
        det = out.detection or (nan, nan)
        est = out.estimate or (nan, nan)
        pred = out.prediction or (nan, nan)
        tx = ty = nan
        vis = -1
        inwin = 0
        terr = terr_deg = terr_stab = cerr = nan
        pdx = pdy = jdx = jdy = nan
        if frame.truth is not None and frame.truth.beacons:
            tx, ty = frame.truth.beacons[0]
            vis = int(frame.truth.visible[0])
            inwin = int(x0 <= tx < x0 + w and y0 <= ty < y0 + h)
            terr = math.hypot(tx - wcx, ty - wcy)
            terr_deg = terr * self.cfg.camera.ifov_deg
            d = frame.truth.disturbance
            # the same error with the per-frame vibration removed: what the gimbal could
            # physically be expected to follow
            terr_stab = math.hypot(tx - d.jitter_dx - wcx, ty - d.jitter_dy - wcy)
            if out.detection is not None:
                cerr = math.hypot(det[0] - tx, det[1] - ty)
            d = frame.truth.disturbance
            pdx, pdy, jdx, jdy = d.platform_dx, d.platform_dy, d.jitter_dx, d.jitter_dy
        else:
            # video: "in window" judged from the estimate
            if out.estimate is not None:
                inwin = int(x0 <= est[0] < x0 + w and y0 <= est[1] < y0 + h)
        # lock: tracking, and the tracker's own estimate is held near the boresight
        captured = out.estimate is not None and math.hypot(est[0] - wcx, est[1] - wcy) <= self.cfg.tracker.capture_radius_px
        locked = int(out.locked and captured and (inwin or frame.truth is None))
        return Record(
            frame=frame.idx, t_sim=frame.t, t_wall=time.perf_counter() - self.t_start, proc_ms=proc_ms,
            fps_inst=1000.0 / max(proc_ms, 1e-3), mode=out.mode.value, locked=locked,
            tier=out.tier, n_candidates=out.n_candidates, confidence=out.confidence, snr=out.snr, sigma=out.sigma, gate=out.gate,
            cam_pan_deg=self.gimbal.pan_deg, cam_tilt_deg=self.gimbal.tilt_deg, win_cx=wcx, win_cy=wcy,
            cmd_pan_rate=cmd.pan_rate, cmd_tilt_rate=cmd.tilt_rate, sat_pan=int(cmd.saturated_pan), sat_tilt=int(cmd.saturated_tilt),
            det_x=det[0], det_y=det[1], est_x=est[0], est_y=est[1], pred_x=pred[0], pred_y=pred[1],
            vel_x=out.velocity[0], vel_y=out.velocity[1], uncertainty_px=out.uncertainty_px,
            p_cv=out.model_probs[0], p_ca=out.model_probs[1], p_ct=out.model_probs[2], ego_dx=ego_dx, ego_dy=ego_dy,
            true_x=tx, true_y=ty, true_visible=vis, in_window=inwin, tracking_err_px=terr, tracking_err_deg=terr_deg, tracking_err_stab_px=terr_stab,
            centroid_err_px=cerr, platform_dx=pdx, platform_dy=pdy, jitter_dx=jdx, jitter_dy=jdy,
        )
