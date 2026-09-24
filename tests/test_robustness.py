"""Robustness fixes from the full review of 2026-09-24: designation cue, video truth, sprite
centres, non-finite and malformed input, same-frame disturbance changes, the packaged
launcher, the record check and the web server's input handling."""
from __future__ import annotations

import csv
import math

import cv2
import numpy as np
import pytest

from fsoc_tracker.engine.checks import check_config
from fsoc_tracker.engine.config import RunConfig, ScheduledChange, TargetConfig, parse_xy
from fsoc_tracker.engine.simulation import Simulation
from fsoc_tracker.world.sprites import make_sprite


# ------------------------------------------------------------------ designation
@pytest.mark.parametrize("motion, extra", [("circular", {"radius_px": 400, "period_s": 30}),
                                           ("waypoints", {"speed_px_s": 40, "waypoints": "1400,1000; 1400,1400; 1600,1400"})])
def test_start_cue_is_where_the_beacon_really_starts(motion, extra):
    """For circular paths x0, y0 is the path's centre and for waypoints the beacon starts at the
    first waypoint: an identical static decoy at the configured start must not win."""
    c = RunConfig(seed=1, duration_s=5)
    c.targets = [TargetConfig(name="Designated", motion=motion, start="1000,1000", **extra),
                 TargetConfig(name="Decoy", motion="static", start="1030,1000")]
    c.designated = 0
    sim = Simulation(c, None, write_csv=False)
    s0 = sim.source.world.targets[0].state(0.0)
    assert sim.tracker.cue == pytest.approx((s0.x, s0.y))
    v = sim.run().values
    assert v["lock_retention_pct"] >= 95.0 and v["tracking_err_mean_px"] < 10.0, v


# ------------------------------------------------------------------ video truth
def _video_with_truth(tmp_path, keep):
    """A clean 150-frame video of a moving square and a truth CSV listing the frames `keep` picks."""
    path = tmp_path / "v.avi"
    vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 30, (800, 600))
    if not vw.isOpened():
        pytest.skip("this OpenCV build has no video encoder")
    rows = []
    for i in range(150):
        img = np.full((600, 800, 3), 12, np.uint8)
        x, y = 200 + 2 * i, 300
        img[y - 5:y + 5, x - 5:x + 5] = 235
        vw.write(img)
        rows.append((i, x - 0.5, y - 0.5))
    vw.release()
    truth = tmp_path / "truth.csv"
    with open(truth, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["frame", "x", "y"])
        for r in rows:
            k = keep(r[0])
            if k == "row":
                w.writerow(r)
            elif k == "blank":
                w.writerow((r[0], "", ""))
    return path, truth


def _video_lock(path, truth):
    c = RunConfig(video=str(path), duration_s=0)
    c.video_truth = str(truth)
    return Simulation(c, None, write_csv=False).run().values


def test_truth_sampled_every_few_frames_is_not_scored_as_lost_lock(tmp_path):
    full = _video_lock(*_video_with_truth(tmp_path, lambda i: "row"))
    sparse = _video_lock(*_video_with_truth(tmp_path, lambda i: "row" if i % 5 == 0 else None))
    assert full["lock_retention_pct"] >= 95.0
    assert sparse["lock_retention_pct"] >= full["lock_retention_pct"] - 5.0, sparse


def test_blank_truth_rows_and_long_gaps_mean_not_visible(tmp_path):
    """A row with an empty position, or a gap of more than a third of a second, says the beacon
    was away: those frames are lost lock, not filled in."""
    gone = _video_lock(*_video_with_truth(tmp_path, lambda i: "row" if i < 60 or i >= 120 else "blank"))
    gap = _video_lock(*_video_with_truth(tmp_path, lambda i: "row" if i < 60 or i >= 120 else None))
    assert gone["lock_retention_pct"] < 75.0 and gap["lock_retention_pct"] < 75.0


# ------------------------------------------------------------------ rendering
@pytest.mark.parametrize("shape", ["square", "circle", "gaussian", "cross", "ring", "diamond", "custom"])
@pytest.mark.parametrize("w, h", [(10, 10), (11, 11), (14, 14), (12, 7)])
def test_every_sprite_is_centred_on_its_truth(shape, w, h):
    sp = make_sprite(shape, w, h, "010;111;010" if shape == "custom" else "")
    ny, nx = sp.shape
    yy, xx = np.mgrid[0:ny, 0:nx]
    cx, cy = (sp * xx).sum() / sp.sum(), (sp * yy).sum() / sp.sum()
    assert math.hypot(cx - (nx - 1) / 2, cy - (ny - 1) / 2) < 0.01


# ------------------------------------------------------------------ malformed input
def test_non_finite_and_malformed_values_never_crash_a_run():
    c = RunConfig.from_dict({"duration_s": float("nan"), "designated": "1",
                             "targets": [{}, {}],
                             "schedule": [{"t_s": float("nan"), "disturbance": {"jitter_px": 5}},
                                          {"t_s": -0.5, "disturbance": {"jitter_px": 4}},
                                          {"t_s": 0.5, "disturbance": {"jitter_px": "five"}}]})
    notes = check_config(c)
    assert c.duration_s == 30.0 and c.designated == 1
    assert [x.t_s for x in c.schedule] == [0.0]                        # NaN and the unusable entry dropped
    assert sum(n["field"] == "schedule" for n in notes) == 3           # each one noted
    assert parse_xy("nan,nan") is None and parse_xy("inf,5") is None and parse_xy("3,4") == (3.0, 4.0)
    c.duration_s = 1
    Simulation(c, None, write_csv=False).run()


def test_unreadable_custom_mask_is_noted():
    for mask, noted in (("abc", True), ("0;0", True), ("012;111", True), ("010;111;010", False)):
        c = RunConfig(targets=[TargetConfig(shape="custom", mask=mask)])
        assert any("mask" in n["field"] for n in check_config(c)) == noted, mask


def test_changes_on_the_same_frame_are_one_segment_described_in_full():
    c = RunConfig.load("configs/scenarios/clear_line.yaml")
    c.duration_s = 3
    c.schedule = [ScheduledChange(1.0, {"jitter_px": 8}), ScheduledChange(1.0, {"gaussian_sigma": 15})]
    sim = Simulation(c, None, write_csv=False)
    s = sim.run()
    assert len(sim.changes) == 1 and sim.changes[0]["frame"] == 30
    assert "jitter" in s.segments[-1]["change"] and "Gaussian" in s.segments[-1]["change"]


# ------------------------------------------------------------------ packaged launcher
def test_launcher_never_turns_a_number_into_a_path(tmp_path, monkeypatch):
    from fsoc_tracker.launcher import _absolutise
    monkeypatch.chdir(tmp_path)
    out = _absolutise(["run", "--duration", "2.5", "--seed", "-1", "--out", "results2", "-s", "scen.yaml"])
    assert out[2] == "2.5" and out[4] == "-1"
    assert out[6] == str(tmp_path / "results2") and out[8] == str(tmp_path / "scen.yaml")


# ------------------------------------------------------------------ record check
def test_record_check_sees_a_code_only_commit(monkeypatch, capsys):
    """git puts a blank line between a commit's header and its files; the check must still pair them."""
    import tools.record_check as rc
    log = ("\x00aaaaaaa\t2026-09-24\tme\tcode only\n\nfsoc_tracker/engine/metrics.py\n"
           "\x00bbbbbbb\t2026-09-24\tme\tcode and record\n\nfsoc_tracker/cli.py\ndocs/HANDOVER.md\n")
    monkeypatch.setattr(rc, "git", lambda *a: log)
    assert rc.main(["--commits", "2"]) == 1
    assert "aaaaaaa" in capsys.readouterr().out


# ------------------------------------------------------------------ web server input
def test_web_server_rejects_bad_input_and_foreign_control():
    pytest.importorskip("fastapi")
    from fastapi import HTTPException
    import webapp.server as S
    for body in ({"overrides": {"seed": "abc"}}, {"overrides": {"seed": -3}}, {"overrides": [1]},
                 {"overrides": {"duration_s": "nan"}}, {"scenario": "../../x"}, {"overrides": {"designated": "x"}}):
        with pytest.raises(HTTPException) as e:
            S._config_from(body)
        assert e.value.status_code == 400, body

    class FakeRun:
        token = "secret"
    S.RUN["fake"] = FakeRun()
    try:
        for tok in ("", "wrong"):
            with pytest.raises(HTTPException) as e:
                S._controlled("fake", tok)
            assert e.value.status_code == 403
        assert S._controlled("fake", "secret") is S.RUN["fake"]
    finally:
        S.RUN.pop("fake", None)
