"""The comparison baseline (control/baseline.py): selectable, never the default, runs every input,
and ARGUS measurably does better where its design matters."""
from __future__ import annotations

from pathlib import Path

from fsoc_tracker.engine.checks import check_config
from fsoc_tracker.engine.config import RunConfig
from fsoc_tracker.engine.simulation import Simulation

ROOT = Path(__file__).resolve().parent.parent


def _values(name, algorithm, seconds=8, **cam):
    c = RunConfig.load(ROOT / "configs" / "scenarios" / f"{name}.yaml")
    c.duration_s, c.tracker.algorithm = seconds, algorithm
    for k, v in cam.items():
        setattr(c.camera, k, v)
    return Simulation(c, None, write_csv=False).run().values


def test_argus_is_the_default_and_an_unknown_algorithm_falls_back_to_it():
    assert RunConfig().tracker.algorithm == "argus"
    c = RunConfig(); c.tracker.algorithm = "magic"
    notes = check_config(c)
    assert c.tracker.algorithm == "argus" and any(n["field"] == "tracker.algorithm" for n in notes)


def test_argus_beats_the_baseline_on_look_alike_decoys_and_noise():
    for name in ("decoys_identical", "noisy_line"):
        a, b = _values(name, "argus"), _values(name, "baseline")
        assert a["lock_retention_pct"] > b["lock_retention_pct"] + 20, (name, a["lock_retention_pct"], b["lock_retention_pct"])
        assert a["tracking_err_mean_px"] < b["tracking_err_mean_px"], name


def test_the_baseline_runs_hard_mode_and_a_scenario_with_a_schedule():
    v = _values("hardmode_line", "baseline", seconds=4)
    assert v["frames"] == 120
    c = RunConfig.load(ROOT / "configs" / "scenarios" / "clear_line.yaml")
    c.duration_s, c.tracker.algorithm = 3, "baseline"
    from fsoc_tracker.engine.config import ScheduledChange
    c.schedule = [ScheduledChange(1.0, {"gaussian_sigma": 10})]
    s = Simulation(c, None, write_csv=False).run()
    assert len(s.segments) == 2
