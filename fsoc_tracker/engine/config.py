"""Typed configuration for a run.

Every row of the problem statement parameter table maps to a field here, so the GUI panel,
the CLI, scenario YAML files and the tests all share one definition. Defaults follow the
"Suggested Value" column of the table.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict, fields, is_dataclass
from pathlib import Path
from typing import Any, get_type_hints

import yaml


@dataclass
class ScreenConfig:
    """Row 1: the scene the tracker observes. Row 2: monochrome by default."""
    width: int = 2000
    height: int = 2000
    colour: bool = False
    background: str = "starfield"   # starfield | terrain | gradient | flat
    background_level: int = 12      # mean grey level of the sky, 0..255
    star_density: float = 3e-4      # stars per pixel for the starfield background


@dataclass
class CameraConfig:
    """Rows 3 to 6 and 13 to 15: the virtual pan-tilt camera."""
    width: int = 640
    height: int = 480
    fov_w_deg: float = 4.0
    fov_h_deg: float = 3.0
    update_rate_hz: float = 30.0
    max_pan_rate_deg_s: float = 5.0
    max_tilt_rate_deg_s: float = 5.0
    max_accel_deg_s2: float = 40.0   # gimbal acceleration limit, our model
    command_latency_frames: int = 1  # frames between command and motion
    # Hard mode: tracker sees only the pixels inside the window and must search.
    window_only: bool = False

    @property
    def ifov_deg(self) -> float:
        return self.fov_w_deg / self.width


@dataclass
class TargetConfig:
    """Rows 7 to 12: one beacon. Several may be listed; the first is the designated one."""
    shape: str = "square"            # square | circle | gaussian
    size_px: int = 10
    intensity: int = 235             # peak grey level 0..255
    motion: str = "line"             # line | circular | figure8 | random | spiral | sinusoidal | waypoints | static
    speed_px_s: float = 120.0        # along-track speed for line, random, sinusoidal
    radius_px: float = 400.0         # circular, figure8, spiral
    period_s: float = 12.0           # circular, figure8, sinusoidal
    start: str = "random"            # random | centre | "x,y"
    heading_deg: float = 30.0        # line, sinusoidal
    blink_hz: float = 0.0            # 0 = steady; >0 modulates intensity (optional realism)
    waypoints: str = ""              # user-defined path for motion "waypoints": "x,y; x,y; ..." in screen px, looped at speed_px_s


@dataclass
class DisturbanceConfig:
    """Rows 21 to 25: everything that dirties the picture. All off by default."""
    # Row 21, 22
    salt_pepper_frac: float = 0.0        # 0.10 = ten percent of the image
    gaussian_sigma: float = 0.0          # grey levels, up to 20
    poisson: bool = False
    # Row 23
    jitter_px: float = 0.0               # +/- pixels per frame, up to 20
    # Row 24
    atmosphere: str = "clear"            # clear | haze | fog | rain | lowlight
    contrast: float = 1.0                # user-defined reduction (1.0 = none)
    brightness: float = 0.0              # added grey levels (negative darkens)
    turbulence: float = 0.0              # 0..1 beam wander and scintillation strength
    blur_sigma: float = 0.0              # PSF broadening in pixels
    # Row 25
    platform_motion: str = "none"        # none | linear | circular | random | spiral | figure8
    platform_px_frame: float = 0.0       # peak pixels per frame, up to 20
    platform_period_s: float = 20.0


@dataclass
class TrackerConfig:
    """Perception and control settings. Our design, not PS rows."""
    detector: str = "hybrid"             # classical | cnn | hybrid
    threshold_k: float = 4.0             # adaptive threshold = mean + k*std
    min_area_px: int = 6
    max_area_px: int = 2500
    verify_n: int = 3                    # N of M frames to confirm acquisition
    verify_m: int = 4
    coast_frames: int = 15               # frames without detection before REACQUIRE
    search_roi_px: int = 160             # half-width of the search window around prediction
    gate_px: float = 60.0                # association gate around prediction
    deadband_px: float = 1.5             # do not command the gimbal inside this radius
    capture_radius_px: float = 30.0      # lock is declared when the estimate is within this of the boresight
    acquire_conf_min: float = 0.62       # a new track needs at least this detector confidence (stars score ~0.55, a beacon 0.67-0.96)
    faint_snr_min: float = 3.5           # faint path: mean matched-filter SNR a chain of weak detections must show
    faint_threshold_k: float = 3.0       # faint path: detection threshold in noise sigmas (track-before-detect links the rest)
    kp: float = 5.0                      # rate command per degree of error (1/s)
    kd: float = 0.3
    ki: float = 0.8
    feedforward: float = 1.0             # weight on predicted target angular rate
    estimator_lag_s: float = 0.25        # estimated filter delay, compensated with acceleration feedforward
    ego_motion: bool = True              # size measurement noise from the measured picture shift (jitter)
    cnn_model: str = "models/beacon_heatmap.onnx"
    cnn_confidence_floor: float = 0.55   # engage the CNN when classical confidence is below this


@dataclass
class RunConfig:
    name: str = "default"
    seed: int = 0
    duration_s: float = 30.0
    screen: ScreenConfig = field(default_factory=ScreenConfig)
    camera: CameraConfig = field(default_factory=CameraConfig)
    targets: list[TargetConfig] = field(default_factory=lambda: [TargetConfig()])
    disturbance: DisturbanceConfig = field(default_factory=DisturbanceConfig)
    tracker: TrackerConfig = field(default_factory=TrackerConfig)
    video: str | None = None             # set for Benchmark 2 runs: path to an .mp4
    output_dir: str = "results"

    # ------------------------------------------------------------------ IO
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RunConfig":
        return _build(cls, d or {})

    @classmethod
    def load(cls, path: str | Path) -> "RunConfig":
        with open(path, "r", encoding="utf-8") as f:
            return cls.from_dict(yaml.safe_load(f) or {})

    def save(self, path: str | Path) -> None:
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(self.to_dict(), f, sort_keys=False)


def _build(cls, d: dict[str, Any]):
    """Recursively construct dataclasses, tolerating missing keys."""
    hints = get_type_hints(cls)
    kwargs = {}
    for f in fields(cls):
        if f.name not in d:
            continue
        v = d[f.name]
        ftype = hints.get(f.name)
        if f.name == "targets":
            kwargs[f.name] = [_build(TargetConfig, t or {}) for t in (v or [])]
        elif isinstance(ftype, type) and is_dataclass(ftype):
            kwargs[f.name] = _build(ftype, v or {})
        else:
            kwargs[f.name] = v
    return cls(**kwargs)


ATMOSPHERE_PRESETS: dict[str, dict[str, float]] = {
    # contrast multiplier, brightness offset, blur, turbulence. Row 24 says the reduction in
    # contrast and brightness is user-defined; these are starting points the user can edit.
    "clear":    {"contrast": 1.00, "brightness":   0.0, "blur_sigma": 0.0, "turbulence": 0.0},
    "haze":     {"contrast": 0.70, "brightness":  25.0, "blur_sigma": 0.8, "turbulence": 0.2},
    "fog":      {"contrast": 0.40, "brightness":  60.0, "blur_sigma": 1.6, "turbulence": 0.3},
    "rain":     {"contrast": 0.60, "brightness":  10.0, "blur_sigma": 1.0, "turbulence": 0.6},
    "lowlight": {"contrast": 0.55, "brightness": -30.0, "blur_sigma": 0.3, "turbulence": 0.1},
}


def apply_atmosphere_preset(d: DisturbanceConfig) -> DisturbanceConfig:
    """Fill contrast, brightness, blur and turbulence from the named preset unless the
    user has already overridden them away from the clear defaults."""
    p = ATMOSPHERE_PRESETS.get(d.atmosphere, ATMOSPHERE_PRESETS["clear"])
    if d.contrast == 1.0 and d.brightness == 0.0 and d.blur_sigma == 0.0 and d.turbulence == 0.0:
        d.contrast, d.brightness = p["contrast"], p["brightness"]
        d.blur_sigma, d.turbulence = p["blur_sigma"], p["turbulence"]
    return d
