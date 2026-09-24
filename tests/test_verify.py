"""fsoc-tracker verify: a run's metrics rebuilt from its frames.csv must match its summary.json,
and a summary that does not come from its frames must be caught."""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from fsoc_tracker.cli import main as cli
from fsoc_tracker.engine.config import RunConfig, ScheduledChange
from fsoc_tracker.engine.simulation import Simulation
from fsoc_tracker.engine.verify import verify_run

ROOT = Path(__file__).resolve().parent.parent


def _run(tmp_path, name="clear_line", seconds=4, schedule=None) -> Path:
    c = RunConfig.load(ROOT / "configs" / "scenarios" / f"{name}.yaml")
    c.duration_s = seconds
    if schedule:
        c.schedule = schedule
    out = tmp_path / f"FSOC_sim_{name}"
    Simulation(c, out).run()
    return out


def test_a_simulator_run_reproduces_its_summary(tmp_path):
    r = verify_run(_run(tmp_path))
    assert r["ok"] and r["checked"] > 25, r["mismatches"]


def test_segments_of_a_run_whose_disturbances_changed_reproduce(tmp_path):
    out = _run(tmp_path, "clear_circular", 6, [ScheduledChange(2.0, {"atmosphere": "fog"}), ScheduledChange(4.0, {"jitter_px": 8})])
    r = verify_run(out)
    assert r["ok"], r["mismatches"]
    assert len(json.load(open(next(out.glob("*_summary.json"))))["segments"]) == 3


def test_a_video_run_with_truth_reproduces_its_summary(tmp_path):
    path = tmp_path / "v.avi"
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 30, (640, 480))
    if not vw.isOpened():
        pytest.skip("this OpenCV build has no video encoder")
    with open(tmp_path / "truth.csv", "w") as f:
        f.write("frame,x,y\n")
        for i in range(90):
            img = np.full((480, 640, 3), 12, np.uint8)
            x = 200 + 2 * i
            img[235:245, x - 5:x + 5] = 235
            vw.write(img)
            f.write(f"{i},{x - 0.5},239.5\n")
    vw.release()
    c = RunConfig(video=str(path), duration_s=0)
    c.video_truth = str(tmp_path / "truth.csv")
    out = tmp_path / "FSOC_video_v"
    Simulation(c, out).run()
    assert verify_run(out)["ok"]


def test_a_summary_that_does_not_come_from_its_frames_is_caught(tmp_path):
    out = _run(tmp_path)
    sj = next(out.glob("*_summary.json"))
    d = json.load(open(sj))
    d["values"]["tracking_err_mean_px"] -= 1.0                  # a better number than the frames support
    d["passed"]["target_loss_pct"] = not d["passed"]["target_loss_pct"]
    json.dump(d, open(sj, "w"))
    r = verify_run(out)
    assert not r["ok"]
    assert {m[0] for m in r["mismatches"]} >= {"tracking_err_mean_px", "passed.target_loss_pct"}
    assert cli(["verify", str(out)]) == 1


def test_verify_on_a_folder_without_a_run_fails_cleanly(tmp_path):
    assert verify_run(tmp_path)["ok"] is False
    assert cli(["verify", str(tmp_path)]) == 1
