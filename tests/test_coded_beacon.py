"""Coded beacon (beyond the PS): the designated beacon blinks a known bit pattern and the tracker
accepts a spot only when its brightness follows it, so look-alikes are told apart by the code
alone. Off by default; a run without a code is unchanged."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from fsoc_tracker.control.tracker import Mode, Tracker
from fsoc_tracker.engine.checks import check_config
from fsoc_tracker.engine.config import CODE_LOW, RunConfig, TargetConfig, parse_code, same_code
from fsoc_tracker.engine.simulation import Simulation
from fsoc_tracker.world.targets import Target

ROOT = Path(__file__).resolve().parent.parent


def _cfg(name="coded_beacon", seconds=8, seed=1) -> RunConfig:
    c = RunConfig.load(ROOT / "configs" / "scenarios" / f"{name}.yaml")
    c.duration_s, c.seed = seconds, seed
    return c


def _on_beacon(sim) -> float:
    """Share of locked frames in which the camera was on the designated beacon (from the truth)."""
    recs = [r for r in sim.telemetry.records if r.locked]
    return float(np.mean([np.hypot(r.true_x - r.est_x, r.true_y - r.est_y) < 30 for r in recs])) if recs else 0.0


def test_codes_are_read_and_compared_up_to_where_the_cycle_starts():
    assert parse_code("1 0110") == [1, 0, 1, 1, 0]
    assert parse_code("111") is None and parse_code("10") is None and parse_code("10a1") is None
    assert same_code("10110", "01101") and same_code("10110", "11010")
    assert not same_code("10110", "11100") and not same_code("10110", "101100")


def test_a_coded_target_dims_on_its_zero_bits():
    t = Target(TargetConfig(code="10110", code_rate_hz=10, intensity=200, motion="static", start="centre"), 2000, 2000, np.random.default_rng(0))
    got = [round(t.state(k / 10 + 0.01).intensity) for k in range(5)]
    assert got == [200, round(200 * CODE_LOW), 200, 200, round(200 * CODE_LOW)]


def test_the_code_alone_tells_the_beacon_from_look_alikes():
    coded = Simulation(_cfg(), None, write_csv=False)
    v = coded.run().values
    assert _on_beacon(coded) == 1.0 and v["acquisition_time_s"] <= 2.0
    assert coded.tracker.code_rejections >= 1                 # it tried a look-alike and turned it down
    steady = _cfg()
    steady.targets[0].code = ""
    plain = Simulation(steady, None, write_csv=False)
    plain.run()
    assert _on_beacon(plain) < 0.5                            # by appearance alone it follows a look-alike


def test_a_wrong_click_is_corrected_by_the_code():
    c = _cfg(seed=0)
    c.designation, c.designation_cue = "cue", "1500,500"      # on Look-alike A's start, not the beacon
    sim = Simulation(c, None, write_csv=False)
    sim.run()
    assert sim.tracker.code_rejections >= 1 and _on_beacon(sim) == 1.0


def test_a_followed_spot_that_stops_blinking_the_code_is_handed_back():
    c = RunConfig()
    c.targets = [TargetConfig(code="10110", code_rate_hz=10)]
    tr = Tracker(c, 1 / 30, (400, 400))
    rng = np.random.default_rng(0)
    modes = []
    for k in range(150):
        img = rng.normal(20, 4, (400, 400)).clip(0, 255)
        on = k >= 60 or [1, 0, 1, 1, 0][int(k / 3) % 5]      # the code for 2 s, then a steady spot
        img[195:205, 195:205] = 220 if on else 220 * CODE_LOW
        modes.append(tr.step(img.astype(np.uint8)).mode)
    assert Mode.TRACK in modes[:60] and tr.code_rejections >= 1
    assert modes[-1] != Mode.TRACK                               # no steady spot is kept as the beacon


def test_a_run_without_a_code_is_unchanged():
    key = lambda s: [(r.frame, r.mode, r.est_x, r.cam_pan_deg) for r in s.telemetry.records]
    a = _cfg("decoys_identical", 4)
    b = _cfg("decoys_identical", 4)
    b.targets[0].code, b.targets[0].code_rate_hz = "", 12.0
    sa, sb = Simulation(a, None, write_csv=False), Simulation(b, None, write_csv=False)
    sa.run(); sb.run()
    assert key(sa) == key(sb)


def test_the_scenario_check_reads_the_code():
    c = _cfg()
    c.targets[1].code, c.targets[2].code = "01101", "1x0"
    c.targets[0].code_rate_hz = 20
    notes = check_config(c)
    fields = {n["field"] for n in notes}
    assert {"target0.code", "target2.code", "target.code", "target.code_rate_hz"} <= fields
    assert c.targets[2].code == ""                             # an unreadable code is dropped, with a note
    same = [n["text"] for n in notes if n["field"] == "designation"]
    assert len(same) == 1 and "Look-alike A" in same[0] and "Look-alike B" not in same[0]   # only the one blinking the same code
    assert not any(n["field"] == "designation" for n in check_config(_cfg()))   # look-alikes the code tells apart are no problem
