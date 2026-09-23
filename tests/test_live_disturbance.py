"""Disturbances changed during a run: scheduled in a scenario, or requested live from the
application. PS "shall": generate and introduce disturbances in the virtual camera feed."""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

from fsoc_tracker.engine.config import (DisturbanceConfig, RunConfig, ScheduledChange, apply_disturbance_changes,
                                        clean_disturbance_changes)
from fsoc_tracker.engine.simulation import Simulation

ROOT = Path(__file__).resolve().parent.parent
DETERMINISTIC = ("frame", "mode", "locked", "det_x", "det_y", "est_x", "est_y", "cam_pan_deg", "cam_tilt_deg",
                 "true_x", "true_y", "tracking_err_px", "centroid_err_px", "platform_dx", "jitter_dx", "segment")


def _cfg(name="clear_circular", seconds=8.0) -> RunConfig:
    c = RunConfig.load(ROOT / "configs" / "scenarios" / f"{name}.yaml")
    c.duration_s = seconds
    return c


def _rows(sim: Simulation) -> list[tuple]:
    return [tuple(getattr(r, k) for k in DETERMINISTIC) for r in sim.telemetry.records]


def test_scheduled_change_takes_effect_on_its_frame():
    c = _cfg()
    c.schedule = [ScheduledChange(3.0, {"atmosphere": "fog"}), ScheduledChange(5.0, {"jitter_px": 8})]
    sim = Simulation(c, None, write_csv=False)
    s = sim.run()
    assert [(ch["frame"], ch["segment"]) for ch in sim.changes] == [(90, 1), (150, 2)]
    seg = [r.segment for r in sim.telemetry.records]
    assert seg[89] == 0 and seg[90] == 1 and seg[149] == 1 and seg[150] == 2
    assert sim.changes[0]["after"].contrast == pytest.approx(0.40)       # the fog preset was applied
    assert [g["segment"] for g in s.segments] == [0, 1, 2]
    assert s.segments[1]["t_start_s"] == pytest.approx(3.0) and s.segments[1]["frames"] == 60
    assert c.disturbance.atmosphere == "clear"                           # the run's own settings are untouched


def test_live_change_is_recorded_and_replays_exactly(tmp_path):
    """A change made during the run is saved in the scenario at the frame it took effect on;
    running that scenario gives the same run frame by frame."""
    sim = Simulation(_cfg(), tmp_path / "live")
    for res in sim.steps():
        if res.record.frame == 60:
            assert sim.request_disturbance({"gaussian_sigma": 12, "poisson": True, "atmosphere": "haze"})
    assert [ch["frame"] for ch in sim.changes] == [61]
    replay = RunConfig.load(sim.files["scenario"])
    assert len(replay.schedule) == 1 and replay.schedule[0].t_s == pytest.approx(61 / 30)
    again = Simulation(replay, None, write_csv=False)
    again.run()
    assert _rows(again) == _rows(sim)


def test_no_op_change_leaves_the_run_unchanged():
    base = Simulation(_cfg(seconds=4), None, write_csv=False)
    base.run()
    c = _cfg(seconds=4)
    c.schedule = [ScheduledChange(2.0, {"atmosphere": "clear", "jitter_px": 0})]
    same = Simulation(c, None, write_csv=False)
    s = same.run()
    assert same.changes == [] and s.segments == []
    assert _rows(same) == _rows(base)


@pytest.mark.parametrize("pattern", ["linear", "circular", "figure8", "random"])
def test_platform_change_never_jumps(pattern):
    """Switching the platform sway on, to the PS maximum and off again mid-run: the picture
    moves at most 1.25 times the larger peak speed per frame, and comes back to rest."""
    c = _cfg(seconds=20)
    c.schedule = [ScheduledChange(3.0, {"platform_motion": pattern, "platform_px_frame": 12}),
                  ScheduledChange(8.0, {"platform_motion": "circular", "platform_px_frame": 20}),
                  ScheduledChange(13.0, {"platform_motion": "none"})]
    sim = Simulation(c, None, write_csv=False)
    sim.run()
    r = sim.telemetry.records
    px, py = np.array([x.platform_dx for x in r]), np.array([x.platform_dy for x in r])
    assert np.max(np.hypot(np.diff(px), np.diff(py))) <= 1.25 * 20 + 1e-6
    assert math.hypot(px[-1], py[-1]) < 1e-6


def test_noise_switched_on_mid_run_reaches_the_picture():
    c = _cfg(seconds=2)
    c.schedule = [ScheduledChange(1.0, {"gaussian_sigma": 20, "salt_pepper_frac": 0.1})]
    sim = Simulation(c, None, write_csv=False)
    spread = []
    for res in sim.steps():
        if res.record.frame in (20, 40):
            img = res.observed
            spread.append(float(np.std(img[:200, :200])))
            salt = np.count_nonzero(img == 255) / img.size     # a dark sky with sigma 20 also clips to 0
    assert spread[1] > 3 * spread[0]
    assert 0.04 < salt < 0.06                         # the salt half of about 10 percent salt and pepper


def test_changes_are_cleaned_before_use():
    assert clean_disturbance_changes({"jitter_px": "-5", "atmosphere": "volcano", "bogus": 1, "poisson": "true",
                                      "salt_pepper_frac": 3}) == {"jitter_px": 0.0, "poisson": True, "salt_pepper_frac": 1.0}
    fog = apply_disturbance_changes(DisturbanceConfig(), {"atmosphere": "fog", "contrast": 0.8})
    assert fog.contrast == 0.8 and fog.brightness == 60.0            # an explicit value beats the preset


def test_schedule_round_trips_through_yaml(tmp_path):
    c = RunConfig(schedule=[ScheduledChange(4.0, {"atmosphere": "rain"}), ScheduledChange(1.5, {"jitter_px": 5})])
    c.save(tmp_path / "s.yaml")
    back = RunConfig.load(tmp_path / "s.yaml")
    assert [(x.t_s, x.disturbance) for x in back.schedule] == [(1.5, {"jitter_px": 5.0}), (4.0, {"atmosphere": "rain"})]


def test_video_runs_refuse_disturbance_changes(tmp_path):
    import cv2
    path = tmp_path / "v.avi"
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 30, (160, 160))
    if not vw.isOpened():
        pytest.skip("this OpenCV build has no video encoder")
    for _ in range(30):
        vw.write(np.full((160, 160, 3), 12, np.uint8))
    vw.release()
    sim = Simulation(RunConfig(video=str(path), duration_s=0), None, write_csv=False)
    assert not sim.accepts_disturbance_changes
    assert sim.request_disturbance({"jitter_px": 5}) is False
