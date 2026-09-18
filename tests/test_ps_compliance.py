"""Point-by-point check of the problem statement parameter table (26169.pdf, rows 1 to 25)
against the application's defaults and capabilities. If anyone changes a default away from
the PS, this file fails.

Rows 16 to 20 (performance) are checked by the closed-loop tests in test_engine.py.
"""
from __future__ import annotations

import inspect

from fsoc_tracker.engine.config import ATMOSPHERE_PRESETS, RunConfig, TargetConfig
from fsoc_tracker.engine.metrics import SPEC
from fsoc_tracker.world import disturbance, targets


def test_rows_1_to_6_camera_parameters():
    c = RunConfig()
    assert c.screen.width >= 2000 and c.screen.height >= 2000          # row 1: screen size min 2000 x 2000
    assert c.screen.colour is False                                     # row 2: monochrome default, colour optional
    assert (c.camera.width, c.camera.height) == (640, 480)              # row 3: camera resolution
    assert (c.camera.fov_w_deg, c.camera.fov_h_deg) == (4.0, 3.0)       # row 4: FOV default 4 x 3 deg
    assert c.camera.update_rate_hz >= 30                                # row 5: camera update rate 30 Hz min
    # row 6: initial camera position at the centre of the screen
    from fsoc_tracker.world.camera import Gimbal
    g = Gimbal(c.camera, c.screen.width, c.screen.height)
    assert g.window_centre_px() == (c.screen.width / 2, c.screen.height / 2)


def test_rows_7_to_12_target_parameters():
    t = TargetConfig()
    assert t.shape == "square"                                          # row 9: default square
    assert (t.size_px, t.size_px) == (10, 10) and 5 <= t.size_px <= 20  # row 10: 5-20 px, default 10 x 10
    assert t.start == "random"                                          # row 11: default random
    assert len(RunConfig().targets) == 1                                # row 8: one target mandatory, more optional
    src = inspect.getsource(targets.Target.state)
    for m in ("line", "circular", "figure8", "random"):                 # row 12: at least these four
        assert f'"{m}"' in src, m
    for m in ("spiral", "sinusoidal"):                                  # row 12: optional ones present too
        assert f'"{m}"' in src, m


def test_rows_13_to_15_camera_motion_constraints():
    c = RunConfig().camera
    assert 5.0 <= c.max_pan_rate_deg_s <= 10.0 and c.max_pan_rate_deg_s == 5.0    # row 13
    assert 5.0 <= c.max_tilt_rate_deg_s <= 10.0 and c.max_tilt_rate_deg_s == 5.0  # row 14
    assert c.update_rate_hz >= 20                                                    # row 15: update interval >= 20 Hz


def test_rows_16_to_20_specification_limits_are_the_ps_values():
    assert SPEC["acquisition_time_s"] == ("<=", 2.0)        # row 16
    assert SPEC["tracking_err_mean_px"] == ("<=", 10.0)     # row 17
    assert SPEC["target_loss_pct"] == ("<", 5.0)            # row 18
    assert SPEC["reacq_time_max_s"] == ("<=", 1.0)          # row 19
    assert SPEC["fps_mean"] == (">=", 20.0)                 # row 20


def test_rows_21_to_25_disturbances():
    d = RunConfig().disturbance
    # row 21: salt and pepper (around 10%), Gaussian, Poisson, one or more selectable
    assert hasattr(d, "salt_pepper_frac") and hasattr(d, "gaussian_sigma") and hasattr(d, "poisson")
    src = inspect.getsource(disturbance.DisturbanceModel.apply_image)
    assert "_sp_bank" in src and "gaussian_sigma" in src and "poisson" in src
    # row 22: max standard deviation of noise 20, user-defined
    assert hasattr(d, "gaussian_sigma")
    # row 23: max camera jitter +/- 20 px per frame, user-defined
    assert hasattr(d, "jitter_px")
    # row 24: Clear, Haze, Fog, Rain, Low light with user-defined contrast and brightness reduction
    assert set(ATMOSPHERE_PRESETS) == {"clear", "haze", "fog", "rain", "lowlight"}
    assert hasattr(d, "contrast") and hasattr(d, "brightness")
    # row 25: platform motion +/- 20 px per frame max; linear mandatory; others optional
    psrc = inspect.getsource(disturbance.DisturbanceModel._platform)
    for m in ("linear", "circular", "figure8", "spiral"):
        assert f'"{m}"' in psrc, m
    assert "random" in psrc
    # all disturbances are off by default (a clear run) and all are user-settable
    assert d.salt_pepper_frac == 0 and d.gaussian_sigma == 0 and d.poisson is False and d.jitter_px == 0
    assert d.atmosphere == "clear" and d.platform_motion == "none"


def test_defaults_were_not_bent_to_a_particular_video():
    """Guards against tuning the mandated camera to suit a test video."""
    c = RunConfig().camera
    assert (c.width, c.height, c.fov_w_deg, c.fov_h_deg, c.update_rate_hz, c.max_pan_rate_deg_s, c.max_tilt_rate_deg_s) == \
           (640, 480, 4.0, 3.0, 30.0, 5.0, 5.0)
