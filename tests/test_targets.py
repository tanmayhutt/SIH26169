"""PS rows 8 to 11 (targets) and the scenario check.

Row 8: one designated target, multiple optional; the tracker must follow the designated one
("detects, identifies, and continuously tracks a designated moving target"). Rows 9 and 10:
user-defined shape, 5-20 x 5-20 px. Row 11: user-defined start. Row 21: salt and pepper
"around 10%". Every test states the PS behaviour it protects.
"""
import copy
import math

import numpy as np

from fsoc_tracker.engine.checks import check_config, check_lines
from fsoc_tracker.engine.config import RunConfig, TargetConfig
from fsoc_tracker.engine.simulation import Simulation
from fsoc_tracker.ui_shared import extra_targets, field_spec
from fsoc_tracker.world.sprites import make_sprite


def test_width_and_height_separate():
    # row 10: "5-20 x 5-20 pixels", default 10 x 10
    t = TargetConfig()
    assert t.dims == (10, 10)
    t = TargetConfig(size_px=6, height_px=16)
    sp = make_sprite("square", *t.dims)
    assert sp.shape == (16 + 6, 6 + 6)            # rows = height, columns = width, 3 px padding
    for shape in ("square", "circle", "gaussian", "cross", "ring", "diamond", "custom"):
        s = make_sprite(shape, 12, 12, "010;111;010")
        assert s.max() == 1.0 and s.sum() > 10     # every row-9 shape draws a visible spot


def test_scenario_check_clamps_and_warns():
    # a typing slip (13 where 0.13 was meant) must not produce an impossible picture, and a
    # value beyond the PS must be reported with its row
    c = RunConfig()
    c.disturbance.salt_pepper_frac = 13
    c.disturbance.jitter_px = 25
    notes = check_config(c)
    assert c.disturbance.salt_pepper_frac == 0.5
    levels = {n["level"] for n in notes}
    assert {"clamped", "beyond_ps"} <= levels
    text = " ".join(check_lines(notes))
    assert "row 21" in text and "row 23" in text
    assert check_config(RunConfig()) == []          # the PS defaults are inside the envelope


def test_scenario_check_physical_limit():
    # a beacon faster than the gimbal can turn (5 deg/s = 800 px/s here) cannot be kept centred
    c = RunConfig()
    c.targets[0].motion = "line"; c.targets[0].speed_px_s = 1200
    assert any(n["level"] == "physical" for n in check_config(c))


def test_salt_and_pepper_shown_in_percent():
    # the PS states salt and pepper as a percentage of the image; the panels show it that way
    spec = field_spec("salt_pepper_frac", 0.1)
    assert spec["scale"] == 100.0 and spec["max"] == 50.0


def test_identical_extra_targets_copy_the_look():
    t0 = TargetConfig(shape="circle", size_px=12, height_px=8, intensity=200)
    ts = extra_targets(t0, [t0], 3, seed=1, identical=True)
    assert len(ts) == 4 and all((t.shape, t.dims, t.intensity) == ("circle", (12, 8), 200) for t in ts)


def _run(cfg, seconds=6.0):
    cfg = copy.deepcopy(cfg); cfg.duration_s = seconds
    sim = Simulation(cfg, None, write_csv=False)
    for _ in sim.steps():
        pass
    return sim


def test_designated_target_is_the_one_scored():
    # the report scores the designated target, whichever entry it is: the recorded truth is that
    # target's position plus the same picture shift (platform sway) the other runs see
    cfg = RunConfig.load("configs/scenarios/full_stress.yaml")
    shifts = []
    for di in (0, 1):
        c = copy.deepcopy(cfg); c.designated = di
        sim = _run(c, 0.2)
        assert sim.summary.designation["index"] == di
        r0, st = sim.telemetry.records[0], sim.source.world.targets[di].state(0.0)
        shifts.append((r0.true_x - st.x, r0.true_y - st.y))
    assert math.hypot(shifts[0][0] - shifts[1][0], shifts[0][1] - shifts[1][1]) < 1.0


def test_identical_decoys_need_a_cue():
    # with look-alikes, appearance alone is ambiguous (and says so); the start cue resolves it
    cfg = RunConfig.load("configs/scenarios/decoys_identical.yaml")
    good = _run(cfg, 8.0)
    assert good.summary.values["lock_retention_pct"] > 95
    cfg.designation = "appearance"
    notes = check_config(copy.deepcopy(cfg))
    assert any("look" in n["text"] and n["level"] == "physical" for n in notes)


def test_user_defined_start():
    # row 11: the start location is user-defined as x,y
    cfg = RunConfig()
    cfg.targets[0].start = "400,1500"; cfg.duration_s = 0.1
    sim = Simulation(cfg, None, write_csv=False)
    tg = sim.source.world.targets[0]
    assert (tg.x0, tg.y0) == (400.0, 1500.0)


def test_any_chosen_target_is_followed_among_panel_decoys():
    # the beacon the user ticks is the one followed, whichever it is and whatever the decoys look
    # like: a 9 px square at 198 next to a 10 px square at 235 defeated appearance alone (0 % lock)
    for identical in (False, True):
        for di in (1, 2):
            cfg = RunConfig(); cfg.seed = 7
            cfg.targets = extra_targets(cfg.targets[0], cfg.targets, 2, 7, identical, di); cfg.designated = di
            s = _run(cfg, 6.0)
            assert s.summary.designation["index"] == di
            assert s.summary.values["lock_retention_pct"] > 95, (identical, di, s.summary.values["lock_retention_pct"])


def test_targets_starting_together_fall_back_to_appearance():
    # all three full_stress targets start at the centre: a start cue cannot single one out, so the
    # automatic mode uses appearance there (and the identity is held, as before)
    cfg = RunConfig.load("configs/scenarios/full_stress.yaml")
    s = _run(cfg, 4.0)
    assert s.summary.designation["mode"].startswith("appearance")
    assert s.summary.values["centroid_err_mean_px"] < 5.0


def test_video_beacons_are_listed_and_the_chosen_one_is_followed(tmp_path):
    # Benchmark 2 with several beacons: the detector lists the beacons of the first frames as
    # targets; designating the second one cues the tracker to it and it is the one scored
    import cv2
    from fsoc_tracker.engine.sources import SyntheticSource
    from fsoc_tracker.ui_shared import video_beacons, video_targets
    c = RunConfig(); c.screen.width = c.screen.height = 900; c.duration_s = 3.0; c.camera.width, c.camera.height = 320, 240
    c.targets = [TargetConfig(name="A", start="250,300", motion="line", heading_deg=20, speed_px_s=60),
                 TargetConfig(name="B", start="650,600", motion="line", heading_deg=200, speed_px_s=60, size_px=8, intensity=200)]
    frames = list(SyntheticSource(c))
    clip = None
    for name, fourcc in (("clip.mp4", "mp4v"), ("clip.avi", "MJPG")):
        try:
            vw = cv2.VideoWriter(str(tmp_path / name), cv2.VideoWriter_fourcc(*fourcc), 30, (900, 900), isColor=True)
            if not vw.isOpened():
                continue
            for fr in frames:
                vw.write(cv2.cvtColor(fr.image, cv2.COLOR_GRAY2BGR))
            vw.release(); clip = tmp_path / name; break
        except cv2.error:
            continue
    if clip is None:
        import pytest; pytest.skip("this OpenCV build has no video encoder")
    b = video_beacons(str(clip), c.tracker)
    assert len(b) == 2, b
    ts = video_targets(b)
    second = min(range(2), key=lambda i: math.hypot(b[i]["x"] - 650, b[i]["y"] - 600))    # the dimmer beacon B
    v = RunConfig(); v.video = str(clip); v.duration_s = 0; v.targets = ts; v.designated = second
    v.designation = "cue"; v.designation_cue = f"{b[second]['x']:.0f},{b[second]['y']:.0f}"
    s = _run(v, 0)
    recs = s.telemetry.records
    bx = np.array([fr.truth.beacons[1][0] for fr in frames]); by = np.array([fr.truth.beacons[1][1] for fr in frames])
    ex = np.array([r.est_x for r in recs]); ey = np.array([r.est_y for r in recs])
    ok = np.isfinite(ex)
    assert s.summary.designation["target"] == ts[second].name      # the video run keeps only the chosen beacon, by name
    assert np.nanmean(np.hypot(ex[ok] - bx[ok], ey[ok] - by[ok])) < 5.0      # the estimate follows beacon B, not A
