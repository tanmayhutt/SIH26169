"""Unit and closed-loop tests. Run with `pytest`."""
from __future__ import annotations

import math
from pathlib import Path

import cv2
import numpy as np
import pytest

from fsoc_tracker.engine.config import RunConfig, TargetConfig, DisturbanceConfig
from fsoc_tracker.engine.simulation import Simulation
from fsoc_tracker.perception.detect import ClassicalDetector, refine_centroid
from fsoc_tracker.perception.estimator import IMM
from fsoc_tracker.world.camera import Gimbal, RateCommand
from fsoc_tracker.world.renderer import World
from fsoc_tracker.world.targets import Target


# ------------------------------------------------------------------ geometry
def test_ifov_and_conversions():
    cfg = RunConfig()
    assert math.isclose(cfg.camera.ifov_deg, 4.0 / 640)
    g = Gimbal(cfg.camera, 2000, 2000)
    dpan, dtilt = g.px_to_deg(640, 480)
    assert math.isclose(dpan, 4.0) and math.isclose(dtilt, 3.0)
    assert g.window_centre_px() == (1000.0, 1000.0)


def test_gimbal_rate_and_pose_limits():
    cfg = RunConfig()
    cfg.camera.command_latency_frames = 0
    cfg.camera.max_accel_deg_s2 = 1e6
    g = Gimbal(cfg.camera, 2000, 2000)
    dt = 1 / 30
    for _ in range(300):
        act = g.apply(RateCommand(50.0, -50.0), dt)
        assert act.saturated_pan and act.saturated_tilt
        assert abs(g.pan_rate) <= 5.0 + 1e-9
    # 300 frames at 5 deg/s = 50 deg requested, clipped to the pose limit
    assert math.isclose(g.pan_deg, g.pan_limit) and math.isclose(g.tilt_deg, -g.tilt_limit)


# ------------------------------------------------------------------ targets
@pytest.mark.parametrize("motion", ["line", "circular", "figure8", "random", "spiral", "sinusoidal", "waypoints"])
def test_targets_stay_on_screen_and_are_deterministic(motion):
    tc = TargetConfig(motion=motion, speed_px_s=200, radius_px=400)
    a = Target(tc, 2000, 2000, np.random.default_rng(3))
    b = Target(tc, 2000, 2000, np.random.default_rng(3))
    for i in range(600):
        t = i / 30
        sa, sb = a.state(t), b.state(t)
        assert 0 <= sa.x < 2000 and 0 <= sa.y < 2000
        assert sa.x == sb.x and sa.y == sb.y


# ------------------------------------------------------------------ detection
def test_centroid_accuracy_on_clean_frame():
    cfg = RunConfig.load(Path(__file__).parent.parent / "configs/scenarios/clear_line.yaml")
    w = World(cfg)
    errs = []
    det = ClassicalDetector(cfg.tracker, cfg.targets[0].size_px)
    for _ in range(10):
        img, truth = w.render()
        tx, ty = truth.beacons[0]
        c = det.detect(img)
        assert c, "no candidates"
        errs.append(math.hypot(c[0].x - tx, c[0].y - ty))
    assert np.mean(errs) < 0.3, errs


def test_refine_centroid_subpixel_synthetic():
    img = np.full((41, 41), 10, np.uint8)
    yy, xx = np.mgrid[0:41, 0:41]
    cx, cy = 20.3, 19.6
    img = np.clip(img + 200 * np.exp(-((xx - cx) ** 2 + (yy - cy) ** 2) / (2 * 2.0 ** 2)), 0, 255).astype(np.uint8)
    x, y, s = refine_centroid(img, 20, 20)
    assert abs(x - cx) < 0.05 and abs(y - cy) < 0.05


# ------------------------------------------------------------------ estimator
def test_imm_tracks_circle_and_predicts():
    dt = 1 / 30
    imm = IMM(dt)
    r, w = 300.0, 2 * math.pi / 10
    rng = np.random.default_rng(0)
    imm.reset(r, 0)
    for i in range(1, 300):
        t = i * dt
        imm.predict()
        x, y = r * math.cos(w * t), r * math.sin(w * t)
        imm.update(x + rng.normal(0, 1), y + rng.normal(0, 1))
    # one-step-ahead prediction error should be small on a smooth circle
    t = 300 * dt
    px, py = imm.position_at(dt)
    err = math.hypot(px - r * math.cos(w * t), py - r * math.sin(w * t))
    assert err < 6.0, err
    assert imm.mu.sum() == pytest.approx(1.0)


# ------------------------------------------------------------------ metrics
def _records(locked_frames: list[bool], dt: float = 1 / 30):
    """Minimal per-frame records: locked or not, beacon in the window, nothing else."""
    import dataclasses
    from fsoc_tracker.engine.telemetry import Record
    out = []
    for i, lk in enumerate(locked_frames):
        vals = {f.name: (0 if f.type in ("int", int) else float("nan")) for f in dataclasses.fields(Record)}
        vals.update(frame=i, t_sim=i * dt, proc_ms=5.0, fps_inst=200.0, mode="TRACK" if lk else "SEARCH", locked=int(lk),
                    tier="classical", in_window=1, true_x=0.0, tracking_err_px=2.0, tracking_err_stab_px=2.0)
        out.append(Record(**vals))
    return out


def test_reacquisition_counts_a_loss_that_is_never_regained():
    """PS row 19: lock at 1 s, lost at 2 s and never regained over the last 8 s must fail."""
    from fsoc_tracker.engine.metrics import summarise
    s = summarise(_records([False] * 30 + [True] * 30 + [False] * 240), 4 / 640, 10.0)
    assert s.values["reacq_count"] == 0
    assert s.values["lock_lost_at_end_s"] == pytest.approx(8.0)
    assert s.values["reacq_time_max_s"] == pytest.approx(8.0)
    assert s.passed["reacq_time_max_s"] is False


def test_reacquisition_of_regained_losses_is_unchanged():
    from fsoc_tracker.engine.metrics import summarise
    s = summarise(_records([True] * 60 + [False] * 15 + [True] * 60), 4 / 640, 5.0)
    assert s.values["reacq_count"] == 1
    assert s.values["reacq_time_max_s"] == pytest.approx(0.5)
    assert s.values["lock_lost_at_end_s"] == 0.0
    assert s.passed["reacq_time_max_s"] is True


# ------------------------------------------------------------------ closed loop
def test_closed_loop_clear_meets_spec():
    cfg = RunConfig.load(Path(__file__).parent.parent / "configs/scenarios/clear_line.yaml")
    cfg.duration_s = 8
    sim = Simulation(cfg, None, write_csv=False)
    s = sim.run()
    v = s.values
    assert v["acquisition_time_s"] <= 2.0, v
    assert v["tracking_err_mean_px"] <= 10.0, v
    assert v["lock_retention_pct"] >= 95.0, v
    assert v["centroid_err_mean_px"] < 0.5, v
    assert v["fps_mean"] >= 20.0, v


def test_closed_loop_with_disturbance_keeps_lock():
    cfg = RunConfig.load(Path(__file__).parent.parent / "configs/scenarios/platform_jitter.yaml")
    cfg.duration_s = 8
    s = Simulation(cfg, None, write_csv=False).run()
    v = s.values
    assert v["acquisition_time_s"] <= 2.0, v
    assert v["lock_retention_pct"] >= 90.0, v
    assert v["centroid_err_mean_px"] < 1.0, v      # identity held under vibration


def test_multi_target_identity_held():
    cfg = RunConfig.load(Path(__file__).parent.parent / "configs/scenarios/full_stress.yaml")
    cfg.duration_s = 10
    s = Simulation(cfg, None, write_csv=False).run()
    v = s.values
    assert v["centroid_err_mean_px"] < 5.0, v      # following the designated beacon, not a decoy
    assert v["lock_retention_pct"] >= 80.0, v


@pytest.mark.parametrize("extra", [3, 8])
def test_many_decoys_from_the_panel_track_the_designated_beacon(extra):
    """Extra targets from the panel (up to 8): with three or more strong spots in view before
    the first lock, the unrefined candidates must be refined on the current frame."""
    from fsoc_tracker.ui_shared import extra_targets
    cfg = RunConfig(seed=0, duration_s=4)
    cfg.targets = extra_targets(cfg.targets[0], cfg.targets, extra, cfg.seed)
    v = Simulation(cfg, None, write_csv=False).run().values
    assert v["acquisition_time_s"] <= 2.0, v
    assert v["centroid_err_mean_px"] < 1.0, v      # measuring the designated beacon, not a decoy
    assert v["lock_retention_pct"] >= 95.0, v


def test_video_source_runs(tmp_path: Path):
    """Benchmark 2 path: write a small synthetic video, then run the tracker on it."""
    cfg = RunConfig(duration_s=3.0)
    cfg.screen.width = cfg.screen.height = 800
    cfg.targets = [TargetConfig(motion="circular", radius_px=150, period_s=6, start="centre")]
    w = World(cfg)
    # the bundled OpenCV lacks an mp4 encoder on some platforms; try the codecs the wheel may carry
    path = None
    for name, fourcc in (("bench.mp4", "mp4v"), ("bench.avi", "MJPG"), ("bench.mkv", "FFV1")):
        cand = tmp_path / name
        try:
            vw = cv2.VideoWriter(str(cand), cv2.VideoWriter_fourcc(*fourcc), 30, (800, 800), isColor=True)
            if not vw.isOpened():
                continue
            for _ in range(90):
                img, _ = w.render()
                vw.write(cv2.cvtColor(img, cv2.COLOR_GRAY2BGR))
            vw.release()
        except cv2.error:
            continue
        if cand.exists() and cand.stat().st_size > 1000:
            path = cand
            break
    if path is None:
        pytest.skip("this OpenCV build has no video encoder; reading videos (the Benchmark 2 path) does not need one")
    vcfg = RunConfig(video=str(path), duration_s=0)
    sim = Simulation(vcfg, tmp_path / "out")
    s = sim.run()
    assert s.values["frames"] >= 80
    assert not s.truth_available
    assert sim.files["frames"].exists() and sim.files["frames"].name.startswith("FSOC_video_")
    assert s.values["lock_retention_pct"] > 80
