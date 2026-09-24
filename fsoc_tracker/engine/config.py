"""Typed configuration for a run.

Every row of the problem statement parameter table maps to a field here, so the GUI panel,
the CLI, scenario YAML files and the tests all share one definition. Defaults follow the
"Suggested Value" column of the table.
"""
from __future__ import annotations

import math
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
    """Rows 7 to 12: one beacon. Several may be listed; `RunConfig.designated` says which one
    the tracker must follow (the first by default)."""
    name: str = ""                   # shown in the panel, the views and the report; empty = "Target N"
    shape: str = "square"            # square | circle | gaussian | cross | ring | diamond | custom
    size_px: int = 10                # row 10: width in px
    height_px: int = 0               # row 10: height in px; 0 = same as the width (a square spot)
    mask: str = ""                   # shape "custom": rows of 0/1 separated by ";" (e.g. "010;111;010"), or a PNG path
    intensity: int = 235             # peak grey level 0..255
    motion: str = "line"             # line | circular | figure8 | random | spiral | sinusoidal | waypoints | static
    speed_px_s: float = 120.0        # along-track speed for line, random, sinusoidal
    radius_px: float = 400.0         # circular, figure8, spiral
    period_s: float = 12.0           # circular, figure8, sinusoidal
    start: str = "random"            # random | centre | "x,y"
    heading_deg: float = 30.0        # line, sinusoidal
    blink_hz: float = 0.0            # 0 = steady; >0 modulates intensity (optional realism)
    # a coded beacon: it blinks a known bit pattern (bit 0 dims it to CODE_LOW, it stays visible),
    # so the tracker can tell it from look-alikes by the code alone. Empty = a steady beacon (the PS default)
    code: str = ""                   # e.g. "10110"
    code_rate_hz: float = 10.0       # bits per second; a bit must last at least two camera frames
    waypoints: str = ""              # user-defined path for motion "waypoints": "x,y; x,y; ..." in screen px, looped at speed_px_s

    def __post_init__(self):
        if not self.height_px or self.height_px <= 0:
            self.height_px = self.size_px

    @property
    def dims(self) -> tuple[int, int]:
        """(width, height) of the spot in px."""
        return int(self.size_px), int(self.height_px or self.size_px)


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
    # camera effects: the PS lists disturbances "due to atmospheric turbulence, platform vibrations,
    # camera motion, noise, etc." in the camera feed; these two are the camera's own
    exposure_gain: float = 1.0           # exposure/gain: scales the light before the sensor noise, clips at 255
    frame_drop_frac: float = 0.0         # share of frames the camera link loses (they arrive with no picture)


@dataclass
class TrackerConfig:
    """Perception and control settings. Our design, not PS rows."""
    algorithm: str = "argus"             # argus | baseline (a deliberately simple tracker, for comparison only)
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
    # handoff to fine pointing (PS: "before fine pointing mechanism can take over"): locked with the
    # estimate held within the row 17 limit of the boresight for this long, so fine pointing could start
    handoff_radius_px: float = 10.0
    handoff_hold_s: float = 1.0
    acquire_conf_min: float = 0.62       # a new track needs at least this detector confidence (stars score ~0.55, a beacon 0.67-0.96)
    faint_snr_min: float = 3.5           # faint path: mean matched-filter SNR a chain of weak detections must show
    faint_threshold_k: float = 3.0       # faint path: detection threshold in noise sigmas (track-before-detect links the rest)
    kp: float = 5.0                      # rate command per degree of error (1/s)
    kd: float = 0.0                      # no derivative: on an error that arrives a frame late in whole pixels it drove a +/-10 px limit cycle
    ki: float = 0.8
    feedforward: float = 1.0             # weight on predicted target angular rate
    estimator_lag_s: float = 0.25        # filter delay at the 30 Hz reference rate (about 7 frames), compensated with acceleration feedforward; scales with the frame rate
    ego_motion: bool = True              # size measurement noise from the measured picture shift (jitter)
    cnn_model: str = "models/beacon_heatmap.onnx"
    cnn_confidence_floor: float = 0.55   # engage the CNN when classical confidence is below this


@dataclass
class ScheduledChange:
    """A change of the disturbances during a run (PS "shall": introduce disturbances in the
    virtual camera feed). `disturbance` holds only the fields that change; the change takes
    effect on the first frame at or after `t_s`. Changes made live in the application are
    recorded here with the time of the frame they took effect on, so the saved scenario replays
    the run exactly."""
    t_s: float = 0.0
    disturbance: dict = field(default_factory=dict)


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
    # which target is the beacon to follow, and how the tracker is told (PS: "a designated
    # moving target"). auto (default): by its configured size, shape and brightness, and when
    # another target looks the same, by its start position as well (as an operator or a
    # GPS/ephemeris cue would). appearance and start force one of those. cue: a point near
    # it, for example a click on the first frame of a video.
    designated: int = 0
    designation: str = "auto"            # auto | appearance | start | cue
    designation_cue: str = ""            # "x,y" in screen (video) px, used when designation == "cue"
    video: str | None = None             # set for Benchmark 2 runs: path to an .mp4
    video_truth: str = ""                # optional ground truth for a video: CSV of frame (or t), x, y in video px
    output_dir: str = "results"
    schedule: list[ScheduledChange] = field(default_factory=list)   # disturbance changes during the run

    # ------------------------------------------------------------ targets
    def designated_index(self) -> int:
        return int(min(max(self.designated, 0), max(len(self.targets) - 1, 0)))

    def designated_target(self) -> "TargetConfig | None":
        return self.targets[self.designated_index()] if self.targets else None

    def look_alikes(self) -> list[int]:
        """Indices of the other targets that look the same as the designated one (same shape,
        size and about the same brightness): by appearance alone they cannot be told apart."""
        t0 = self.designated_target()
        if t0 is None:
            return []
        return [i for i, t in enumerate(self.targets)
                if i != self.designated_index() and t.shape == t0.shape and t.dims == t0.dims and abs(t.intensity - t0.intensity) < 25]

    def resolved_designation(self) -> str:
        """The designation mode a run uses: auto becomes start when look-alikes exist."""
        if self.designation == "auto":
            return "start" if (self.look_alikes() and not self.video) else "appearance"
        return self.designation

    def target_names(self) -> list[str]:
        return [target_name(t, i) for i, t in enumerate(self.targets)]

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
        elif f.name == "schedule":
            def t_of(c):
                try:
                    return float(c.get("t_s", 0.0))
                except (TypeError, ValueError):
                    return float("nan")               # reported and dropped by the scenario check
            entries = [ScheduledChange(t_of(c), clean_disturbance_changes(c.get("disturbance") or {})) for c in (v or []) if isinstance(c, dict)]
            kwargs[f.name] = sorted(entries, key=lambda c: (not math.isfinite(c.t_s), c.t_s if math.isfinite(c.t_s) else 0.0))
        elif isinstance(ftype, type) and is_dataclass(ftype):
            kwargs[f.name] = _build(ftype, v or {})
        else:
            kwargs[f.name] = v
    return cls(**kwargs)


def target_name(t: TargetConfig, i: int) -> str:
    return (t.name or "").strip() or f"Target {i + 1}"


CODE_LOW = 0.7        # brightness of a coded beacon during a 0 bit, as a share of its peak


def parse_code(text: str) -> list[int] | None:
    """A beacon code as bits: "10110" -> [1, 0, 1, 1, 0]; None unless it is 3 to 32 zeros and ones
    with at least one of each (a code of all ones is a steady beacon)."""
    t = "".join(str(text or "").split())
    if not (3 <= len(t) <= 32) or set(t) - {"0", "1"} or len(set(t)) < 2:
        return None
    return [int(ch) for ch in t]


def same_code(a: str, b: str) -> bool:
    """Two codes a tracker cannot tell apart: equal up to where the cycle starts (the beacon's
    clock is not known, so 10110 and 01101 are the same code)."""
    x, y = parse_code(a), parse_code(b)
    return x is not None and y is not None and len(x) == len(y) and "".join(map(str, y)) in "".join(map(str, x)) * 2


def parse_xy(text: str) -> tuple[float, float] | None:
    """"x,y" -> (x, y), or None when empty or malformed."""
    try:
        sx, sy = str(text).split(",")
        x, y = float(sx), float(sy)
    except (ValueError, AttributeError):
        return None
    return (x, y) if math.isfinite(x) and math.isfinite(y) else None     # "nan,nan" is no point


# Accepted input range of every numeric setting, in the units of this file. Values outside are
# clamped before a run (engine/checks.py) whatever the front end, so a typing slip can never
# produce an impossible picture. The PS envelope (what the problem statement specifies) is
# narrower and is checked separately, as warnings.
LIMITS = {"width": (64, 8000), "height": (64, 8000), "size_px": (2, 60), "height_px": (0, 60), "intensity": (20, 255),
          "salt_pepper_frac": (0, 0.5), "gaussian_sigma": (0, 60), "jitter_px": (0, 60), "platform_px_frame": (0, 60),
          "contrast": (0.05, 2.0), "brightness": (-120, 120), "turbulence": (0, 1), "blur_sigma": (0, 8), "fov_w_deg": (0.2, 60),
          "fov_h_deg": (0.2, 60), "update_rate_hz": (5, 120), "max_pan_rate_deg_s": (0.5, 60), "max_tilt_rate_deg_s": (0.5, 60),
          "speed_px_s": (0, 2000), "radius_px": (10, 3000), "period_s": (1, 600), "heading_deg": (-360, 360),
          "background_level": (0, 120), "star_density": (0, 0.01), "kp": (0, 20), "kd": (0, 5), "ki": (0, 5), "feedforward": (0, 2),
          "deadband_px": (0, 20), "threshold_k": (1, 12), "max_accel_deg_s2": (1, 500), "command_latency_frames": (0, 10),
          "blink_hz": (0, 15), "code_rate_hz": (1, 30), "capture_radius_px": (5, 200), "estimator_lag_s": (0, 1), "acquire_conf_min": (0, 1),
          "faint_snr_min": (0, 20), "handoff_radius_px": (1, 200), "handoff_hold_s": (0, 10), "faint_threshold_k": (1, 12), "platform_period_s": (1, 600), "duration_s": (1, 3600), "exposure_gain": (0.25, 4.0), "frame_drop_frac": (0, 0.5)}


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


PLATFORM_MOTIONS = ("none", "linear", "circular", "random", "spiral", "figure8")
_PRESET_FIELDS = ("contrast", "brightness", "blur_sigma", "turbulence")


def clean_disturbance_changes(changes: dict) -> dict:
    """Keep only real DisturbanceConfig fields, cast to their types and clamped to LIMITS, so a
    schedule from a scenario file or a request from the web page cannot inject anything else."""
    kinds = {f.name: f.type for f in fields(DisturbanceConfig)}
    out: dict[str, Any] = {}
    for k, v in (changes or {}).items():
        kind = kinds.get(k)
        if kind is None:
            continue
        if kind in ("bool", bool):
            v = v if isinstance(v, bool) else str(v).strip().lower() in ("1", "true", "yes", "on")
        elif kind in ("float", float):
            try:
                v = float(v)
            except (TypeError, ValueError):
                continue                          # "five" is not a number: the setting is left out
            if not math.isfinite(v):
                continue
            lim = LIMITS.get(k)                  # the same accepted range as a value typed before Start
            if lim is not None:
                v = min(max(v, float(lim[0])), float(lim[1]))
        else:
            v = str(v)
            if k == "atmosphere" and v not in ATMOSPHERE_PRESETS:
                continue
            if k == "platform_motion" and v not in PLATFORM_MOTIONS:
                continue
        out[k] = v
    return out


def apply_disturbance_changes(current: DisturbanceConfig, changes: dict) -> DisturbanceConfig:
    """The disturbance configuration after a change. A new atmosphere preset fills contrast,
    brightness, blur and turbulence unless the change sets them itself (the same rule as a
    scenario file), so `{atmosphere: fog}` means fog."""
    changes = clean_disturbance_changes(changes)
    new = DisturbanceConfig(**{**asdict(current), **changes})
    if "atmosphere" in changes and changes["atmosphere"] != current.atmosphere:
        preset = ATMOSPHERE_PRESETS[changes["atmosphere"]]
        for k in _PRESET_FIELDS:
            if k not in changes:
                setattr(new, k, preset[k])
    return new


def disturbance_diff(before: DisturbanceConfig, after: DisturbanceConfig) -> dict:
    """The fields that differ, as {name: new value}."""
    a, b = asdict(before), asdict(after)
    return {k: b[k] for k in b if b[k] != a[k]}


_SHORT = {"salt_pepper_frac": "salt and pepper", "gaussian_sigma": "Gaussian sigma", "poisson": "Poisson",
          "jitter_px": "jitter", "atmosphere": "atmosphere", "contrast": "contrast", "brightness": "brightness",
          "turbulence": "turbulence", "blur_sigma": "blur", "platform_motion": "platform",
          "platform_px_frame": "platform speed", "platform_period_s": "platform period",
          "exposure_gain": "exposure", "frame_drop_frac": "frame loss"}
_UNIT = {"jitter_px": " px/frame", "platform_px_frame": " px/frame", "platform_period_s": " s", "blur_sigma": " px"}


def describe_disturbance_change(before: DisturbanceConfig, after: DisturbanceConfig) -> str:
    """One line for the status bar and the report, e.g. 'atmosphere clear -> fog, jitter 0 -> 10 px/frame'."""
    def fmt(k, v):
        if isinstance(v, bool):
            return "on" if v else "off"
        if isinstance(v, float):
            return f"{v:g}{_UNIT.get(k, '')}"
        return str(v)
    parts = [f"{_SHORT.get(k, k)} {fmt(k, getattr(before, k))} -> {fmt(k, v)}" for k, v in disturbance_diff(before, after).items()]
    return ", ".join(parts) or "no change"
