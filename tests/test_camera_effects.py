"""Camera effects beyond the PS table (the PS lists disturbances "... noise, etc."): frame loss and
exposure gain. Off by default, live-changeable like every disturbance, and honest in the report."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from fsoc_tracker.engine.checks import check_config
from fsoc_tracker.engine.config import DisturbanceConfig, RunConfig, ScheduledChange
from fsoc_tracker.engine.simulation import Simulation

ROOT = Path(__file__).resolve().parent.parent


def _cfg(seconds=10, **d) -> RunConfig:
    c = RunConfig.load(ROOT / "configs" / "scenarios" / "clear_line.yaml")
    c.duration_s = seconds
    for k, v in d.items():
        setattr(c.disturbance, k, v)
    return c


def test_both_are_off_by_default():
    d = DisturbanceConfig()
    assert d.frame_drop_frac == 0.0 and d.exposure_gain == 1.0


def test_lost_frames_are_blank_counted_and_the_tracker_coasts_through():
    sim = Simulation(_cfg(frame_drop_frac=0.10), None, write_csv=False)
    lost_pictures = []
    for res in sim.steps():
        if res.record.frame_lost:
            lost_pictures.append(int(res.observed.max()))
    v = sim.summary.values
    assert 6.0 < v["frames_lost_pct"] < 16.0 and set(lost_pictures) == {0}
    assert v["lock_retention_received_pct"] > 95.0            # it held on every picture that arrived
    assert v["tracking_err_mean_px"] < 10.0 and v["reacq_time_max_s"] <= 1.0


def test_exposure_scales_the_light_and_clips_at_white():
    def first_frame(g):
        return next(iter(Simulation(_cfg(seconds=1, exposure_gain=g), None, write_csv=False).steps())).observed
    dark, base, bright = (float(np.median(first_frame(g))) for g in (0.5, 1.0, 4.0))
    assert dark < base < bright                              # the sky follows the exposure
    assert int(first_frame(4.0).max()) == 255                # and the beacon clips at white


def test_a_run_without_them_is_unchanged_and_they_can_change_live():
    key = lambda s: [(r.frame, r.mode, r.est_x) for r in s.telemetry.records]
    a = Simulation(_cfg(seconds=3), None, write_csv=False); a.run()
    b = Simulation(_cfg(seconds=3, frame_drop_frac=0.0, exposure_gain=1.0), None, write_csv=False); b.run()
    assert key(a) == key(b)
    c = _cfg(seconds=4)
    c.schedule = [ScheduledChange(2.0, {"frame_drop_frac": 0.2, "exposure_gain": 2.0})]
    sim = Simulation(c, None, write_csv=False); sim.run()
    assert not any(r.frame_lost for r in sim.telemetry.records[:60]) and sim.changes


def test_the_scenario_check_says_they_are_beyond_the_ps_table():
    c = _cfg(frame_drop_frac=0.05, exposure_gain=2.0)
    fields = {n["field"] for n in check_config(c)}
    assert {"disturbance.frame_drop_frac", "disturbance.exposure_gain"} <= fields
