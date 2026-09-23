"""Fixes from an independent review (2026-09-23), each pinned to the behaviour it protects."""
import copy
import csv
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import cv2
import numpy as np

from fsoc_tracker.engine.config import RunConfig
from fsoc_tracker.engine.metrics import summarise
from fsoc_tracker.engine.simulation import Simulation
from fsoc_tracker.engine.sources import SyntheticSource, load_truth
from fsoc_tracker.engine.telemetry import Record


def _run(cfg, seconds):
    cfg = copy.deepcopy(cfg); cfg.duration_s = seconds
    sim = Simulation(cfg, None, write_csv=False)
    for _ in sim.steps():
        pass
    return sim


def test_fps_is_frames_over_processing_time():
    # row 20: the processing rate is frames over processing time; the mean of per-frame rates
    # overstates it when frame times vary (here 3 frames of 10 ms and one of 100 ms)
    import dataclasses
    names = {f.name for f in dataclasses.fields(Record)}
    recs = []
    for i, ms in enumerate((10, 10, 10, 100)):
        kw = {n: 0 for n in names}
        kw.update(frame=i, t_sim=i / 30, proc_ms=ms, fps_inst=1000 / ms, mode="TRACK", tier="none", true_x=float("nan"), true_y=float("nan"))
        recs.append(Record(**kw))
    v = summarise(recs, 0.00625, 1.0).values
    assert abs(v["fps_mean"] - 1000 / 32.5) < 1e-6          # 30.8 FPS, not the 77.5 a mean of rates gives
    assert v["fps_inst_mean"] > v["fps_mean"]


def test_fast_target_is_kept_centred():
    # a 4 deg/s circle (640 px/s, below the 5 deg/s turn rate) must meet row 17 and row 18;
    # before the turn-limited lead it ran at 34 px and 15 % lock
    cfg = RunConfig.load("configs/scenarios/fast_circular.yaml")
    v = _run(cfg, 8.0).summary.values
    assert v["tracking_err_mean_px"] < 10 and v["lock_retention_pct"] > 95


def test_coasting_estimate_cannot_run_off_the_screen():
    # an estimate that drifts off the picture while coasting sends the tracker back to search
    from fsoc_tracker.control.tracker import Mode, Tracker
    cfg = RunConfig()
    tr = Tracker(cfg, 1 / 30, (2000, 2000))
    tr.imm.reset(1990.0, 1000.0); tr.imm.set_velocity(3000.0, 0.0)
    tr._set(Mode.COAST); tr.miss_count = 1
    blank = np.full((2000, 2000), 12, np.uint8)
    for _ in range(10):
        out = tr.step(blank)
        if out.mode == Mode.SEARCH:
            break
    assert out.mode == Mode.SEARCH


def test_video_ground_truth_gives_errors():
    # Benchmark 2: with the evaluators' reference positions the errors are computed against them
    d = Path(tempfile.mkdtemp())
    c = RunConfig(); c.screen.width = c.screen.height = 800; c.duration_s = 2.0; c.targets[0].start = "centre"
    c.targets[0].motion = "circular"; c.targets[0].radius_px = 150; c.camera.width, c.camera.height = 320, 240
    frames = list(SyntheticSource(c))
    with open(d / "clip_truth.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["frame", "x", "y"])
        for fr in frames:
            w.writerow([fr.idx, *fr.truth.beacons[0]])
    assert len(load_truth(d / "clip_truth.csv", 30.0)) == 60
    # the bundled OpenCV lacks an mp4 encoder on some platforms; try the codecs the wheel may carry
    clip = None
    for name, fourcc in (("clip.mp4", "mp4v"), ("clip.avi", "MJPG"), ("clip.mkv", "FFV1")):
        try:
            vw = cv2.VideoWriter(str(d / name), cv2.VideoWriter_fourcc(*fourcc), 30, (800, 800), isColor=True)
            if not vw.isOpened():
                continue
            for fr in frames:
                vw.write(cv2.cvtColor(fr.image, cv2.COLOR_GRAY2BGR))
            vw.release()
        except cv2.error:
            continue                          # some encoders assert on this build; try the next one
        if (d / name).exists() and (d / name).stat().st_size > 0:
            clip = d / name
            break
    if clip is None:
        import pytest
        pytest.skip("this OpenCV build has no video encoder; reading videos (the Benchmark 2 path) does not need one")
    v = RunConfig(); v.video = str(clip); v.video_truth = str(d / "clip_truth.csv"); v.duration_s = 0
    s = _run(v, 0).summary
    assert s.truth_available and s.values["centroid_err_mean_px"] < 1.0


def test_cnn_model_found_from_any_folder():
    # an installed command started outside the repository still loads the AI detector
    code = "from fsoc_tracker.perception.detect import CNNDetector; print(CNNDetector('models/beacon_heatmap.onnx').available())"
    out = subprocess.run([sys.executable, "-c", code], cwd=tempfile.gettempdir(), capture_output=True, text=True,
                         env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1])))
    assert out.stdout.strip().endswith("True")


def test_still_beacon_is_centred_without_oscillation():
    # the derivative term on a one-frame-late, whole-pixel error drove a +/-10 px limit cycle;
    # a still beacon must now be held within a few pixels (row 17)
    cfg = RunConfig(); cfg.targets[0].start = "1700,300"; cfg.targets[0].motion = "static"
    r = _run(cfg, 6.0).telemetry.records[120:]
    assert max(x.tracking_err_px for x in r) < 4.0


def test_platform_sway_never_exceeds_the_set_speed():
    # row 25: +/- 20 px/frame maximum, for every pattern (the figure 8 was sqrt(2) too fast)
    for m in ("linear", "circular", "figure8", "spiral", "random"):
        cfg = RunConfig(); cfg.disturbance.platform_motion = m; cfg.disturbance.platform_px_frame = 20
        r = _run(cfg, 6.0).telemetry.records
        px = np.array([x.platform_dx for x in r]); py = np.array([x.platform_dy for x in r])
        assert np.hypot(np.diff(px), np.diff(py)).max() <= 20.05, m


def test_faint_track_is_not_walked_off_by_noise():
    # a faint beacon (3 to 6 sigma): a refit that slides onto noise, or a network guess on a
    # noise patch, used to kick the track off the beacon (seed 7: 86 px, 79 % lock)
    cfg = RunConfig.load("configs/scenarios/lowlight_faint.yaml"); cfg.seed = 7
    v = _run(cfg, 8.0).summary.values
    assert v["tracking_err_mean_px"] < 10 and v["lock_retention_pct"] > 90
