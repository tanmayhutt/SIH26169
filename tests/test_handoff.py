"""Handoff to fine pointing (PS: coarse alignment works "before fine pointing mechanism can take
over"): locked, the estimate within handoff_radius_px of the window centre, held for handoff_hold_s."""
from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
import pytest

from fsoc_tracker.engine.config import RunConfig
from fsoc_tracker.engine.simulation import Simulation
from fsoc_tracker.engine.verify import verify_run

ROOT = Path(__file__).resolve().parent.parent


def _sim(name="clear_line", seconds=6, **tracker):
    c = RunConfig.load(ROOT / "configs" / "scenarios" / f"{name}.yaml")
    c.duration_s = seconds
    for k, v in tracker.items():
        setattr(c.tracker, k, v)
    sim = Simulation(c, None, write_csv=False)
    return sim, sim.run().values


def test_handoff_follows_lock_and_the_hold_time():
    sim, v = _sim()
    recs = sim.telemetry.records
    assert all(r.locked for r in recs if r.handoff)                     # only ever while locked
    assert v["handoff_time_s"] >= v["acquisition_time_s"] + 1.0 - 1e-6   # after lock, held 1 s
    assert v["handoff_pct"] > 90.0
    _, v0 = _sim(handoff_hold_s=0.0)
    assert v0["handoff_time_s"] < v["handoff_time_s"]


def test_shake_at_the_ps_maximum_keeps_handoff_short_of_clear_sky():
    _, clear = _sim()
    _, shaken = _sim("platform_max")
    assert shaken["handoff_pct"] < clear["handoff_pct"]


def test_handoff_never_changes_the_tracking():
    a, _ = _sim(seconds=4)
    b, _ = _sim(seconds=4, handoff_radius_px=50.0, handoff_hold_s=0.2)
    key = lambda s: [(r.frame, r.mode, r.est_x, r.cam_pan_deg) for r in s.telemetry.records]
    assert key(a) == key(b)


def test_handoff_on_a_video_and_verify_reproduces_it(tmp_path):
    path = tmp_path / "v.avi"
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 30, (640, 480))
    if not vw.isOpened():
        pytest.skip("this OpenCV build has no video encoder")
    for i in range(120):
        img = np.full((480, 640, 3), 12, np.uint8)
        x = 320 + int(40 * np.sin(i / 20))
        img[235:245, x - 5:x + 5] = 235
        vw.write(img)
    vw.release()
    out = tmp_path / "FSOC_video_v"
    v = Simulation(RunConfig(video=str(path), duration_s=0), out).run().values
    assert v["handoff_time_s"] == v["handoff_time_s"] and v["handoff_pct"] > 50.0   # reached, from the estimate alone
    assert verify_run(out)["ok"]
