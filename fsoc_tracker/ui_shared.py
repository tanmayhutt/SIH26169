"""One definition of the user interface, shared by the desktop application and the web app.

Everything a user reads or sets is defined here once: the parameter panel (sections, labels,
tooltips, ranges, choices), the live tiles and how they are judged, the telemetry lines, the
text on the scene and camera views, the end-of-run summary, the help and welcome text, how
decoy targets are generated from "Extra targets", and the display contrast stretch of the
camera view. The two front ends only draw; they never keep their own copy of any of this.
"""
from __future__ import annotations

import dataclasses
from collections import deque
from pathlib import Path

import numpy as np

from . import __version__
from .engine.config import ATMOSPHERE_PRESETS, RunConfig, TargetConfig
from .engine.metrics import SPEC

# ----------------------------------------------------------------------------- panel
CHOICES = {
    "background": ["starfield", "terrain", "gradient", "flat"],
    "shape": ["square", "circle", "gaussian"],
    "motion": ["line", "circular", "figure8", "random", "spiral", "sinusoidal", "waypoints", "static"],
    "start": ["random", "centre"],
    "atmosphere": list(ATMOSPHERE_PRESETS.keys()),
    "platform_motion": ["none", "linear", "circular", "random", "spiral", "figure8"],
    "detector": ["hybrid", "classical", "cnn"],
}
LABELS = {
    "width": "Width (px)", "height": "Height (px)", "fov_w_deg": "FOV width (deg)", "fov_h_deg": "FOV height (deg)",
    "update_rate_hz": "Update rate (Hz)", "max_pan_rate_deg_s": "Max pan (deg/s)", "max_tilt_rate_deg_s": "Max tilt (deg/s)",
    "max_accel_deg_s2": "Max accel (deg/s2)", "command_latency_frames": "Latency (frames)",
    "window_only": "Hard mode: see window only", "size_px": "Size (px)", "intensity": "Peak intensity",
    "speed_px_s": "Speed (px/s)", "radius_px": "Radius (px)", "period_s": "Period (s)", "heading_deg": "Heading (deg)",
    "blink_hz": "Blink (Hz, 0 = steady)", "waypoints": "Waypoints (x,y; x,y)", "salt_pepper_frac": "Salt and pepper", "gaussian_sigma": "Gaussian sigma",
    "poisson": "Poisson shot noise", "jitter_px": "Camera jitter (px/frame)", "atmosphere": "Atmosphere preset",
    "contrast": "Contrast multiplier", "brightness": "Brightness offset", "turbulence": "Turbulence (0-1)",
    "blur_sigma": "PSF blur sigma (px)", "platform_motion": "Platform motion", "platform_px_frame": "Platform (px/frame)",
    "platform_period_s": "Platform period (s)", "background_level": "Sky level (0-255)", "star_density": "Star density",
    "colour": "Colour camera", "detector": "Detector", "ego_motion": "Use picture-shift estimate", "threshold_k": "Threshold k (sigma)",
    "kp": "Kp", "kd": "Kd", "ki": "Ki", "feedforward": "Feedforward weight", "deadband_px": "Deadband (px)",
    "capture_radius_px": "Capture radius (px)", "estimator_lag_s": "Estimator lag (s)", "acquire_conf_min": "Acquire confidence",
    "faint_snr_min": "Faint: min chain SNR", "faint_threshold_k": "Faint: threshold (sigma)",
}
TIPS = {
    "width": "PS row 1 (screen) or row 3 (camera). The screen is the whole scene the tracker observes; the camera window is what the terminal points at.",
    "height": "PS row 1 (screen) or row 3 (camera).",
    "colour": "PS row 2. Monochrome by default; colour renders three channels and the tracker uses luminance.",
    "fov_w_deg": "PS row 4. Degrees per pixel = FOV / camera width. Default 4 deg over 640 px = 22.5 arcsec per pixel.",
    "fov_h_deg": "PS row 4. Default 3 deg.",
    "update_rate_hz": "PS row 5. Frames per second of the camera and the simulation clock. Minimum 30.",
    "max_pan_rate_deg_s": "PS row 13. The gimbal cannot turn faster than this. 5 deg/s = 26.7 px per frame at 30 Hz.",
    "max_tilt_rate_deg_s": "PS row 14.",
    "max_accel_deg_s2": "Our gimbal model: how fast the turn rate can change.",
    "command_latency_frames": "Our gimbal model: frames between a command and the motion. The controller leads the target by this.",
    "window_only": "Hard mode. The tracker sees only the inside of the camera window and must sweep a spiral to find the beacon.",
    "shape": "PS row 9. Default square.", "size_px": "PS row 10. 5 to 20 px, default 10.", "intensity": "Peak grey level of the beacon, 0-255.",
    "motion": "PS row 12. Straight line, circular, figure of 8 and random are mandatory; spiral, sinusoidal and user-defined waypoints optional.",
    "speed_px_s": "Along-track speed for line, random, sinusoidal and waypoint paths.", "radius_px": "Radius for circular, figure of 8, spiral; half-amplitude for sinusoidal.",
    "period_s": "Time for one loop of the path.", "heading_deg": "Direction of a line or sinusoidal path.", "start": "PS row 11. Default random.",
    "blink_hz": "Optional intensity modulation of the beacon.",
    "waypoints": "PS row 12, user-defined path: points in screen pixels for motion 'waypoints', followed at Speed and looped. Example 300,300; 1700,400; 1000,1600.",
    "salt_pepper_frac": "PS row 21. 0.10 means 10 percent of pixels are set to black or white.",
    "gaussian_sigma": "PS row 21 and 22. Read-noise standard deviation in grey levels, up to 20.",
    "poisson": "PS row 21. Shot noise that grows with brightness.",
    "jitter_px": "PS row 23. Random shift of the whole picture each frame, up to 20 px.",
    "atmosphere": "PS row 24. Choosing a preset fills contrast, brightness, blur and turbulence; edit them afterwards if you like.",
    "contrast": "PS row 24. 1.0 = none. Fog is about 0.4.", "brightness": "PS row 24. Grey levels added; fog lifts the black level, low light lowers it.",
    "turbulence": "Beam wander and flicker strength.", "blur_sigma": "PSF broadening from the atmosphere.",
    "platform_motion": "PS row 25. Linear is mandatory. All patterns are bounded sways whose peak speed is the value below.",
    "platform_px_frame": "PS row 25. Peak speed of the platform sway, up to 20 px per frame.", "platform_period_s": "Period of circular, figure of 8 and spiral sways.",
    "background": "Scene background.", "background_level": "Mean sky brightness.", "star_density": "Stars per pixel in the starfield.",
    "detector": "hybrid: classical first, CNN fills gaps. classical: never use the CNN. cnn: CNN whenever it is confident.",
    "ego_motion": "Use the frame-to-frame picture shift (phase correlation) as a hint for vibration level.",
    "threshold_k": "Detection threshold in sigmas above the local background.", "kp": "Proportional gain, deg/s per deg of error.",
    "kd": "Derivative gain.", "ki": "Integral gain.", "feedforward": "Weight on the predicted target angular rate.",
    "deadband_px": "No command inside this radius, so vibration is not chased.", "capture_radius_px": "Lock is declared when the estimate is within this of the window centre.",
    "estimator_lag_s": "Assumed delay of the velocity estimate at the 30 Hz reference, compensated with acceleration; scales with the update rate.",
    "acquire_conf_min": "A new track needs at least this detector confidence. Stars and noise clumps score about 0.55, a beacon 0.67 (low light) to 0.96 (clear).",
    "faint_snr_min": "Faint beacons: weak detections are linked across frames; a chain is promoted when its mean matched-filter SNR is at least this.",
    "faint_threshold_k": "Faint beacons: detection threshold in noise sigmas for the chain search (the normal threshold is 4).",
}
HIDDEN = {"cnn_model", "cnn_confidence_floor", "min_area_px", "max_area_px", "verify_n", "verify_m", "coast_frames",
          "search_roi_px", "gate_px"}
RANGES = {"width": (64, 8000), "height": (64, 8000), "size_px": (2, 60), "intensity": (20, 255), "salt_pepper_frac": (0, 0.5),
          "gaussian_sigma": (0, 60), "jitter_px": (0, 60), "platform_px_frame": (0, 60), "contrast": (0.05, 2.0),
          "brightness": (-120, 120), "turbulence": (0, 1), "blur_sigma": (0, 8), "fov_w_deg": (0.2, 60), "fov_h_deg": (0.2, 60),
          "update_rate_hz": (5, 120), "max_pan_rate_deg_s": (0.5, 60), "max_tilt_rate_deg_s": (0.5, 60), "speed_px_s": (0, 2000),
          "radius_px": (10, 3000), "period_s": (1, 600), "heading_deg": (-360, 360), "background_level": (0, 120),
          "star_density": (0, 0.01), "kp": (0, 20), "kd": (0, 5), "ki": (0, 5), "feedforward": (0, 2), "deadband_px": (0, 20),
          "threshold_k": (1, 12), "max_accel_deg_s2": (1, 500), "command_latency_frames": (0, 10), "blink_hz": (0, 15),
          "capture_radius_px": (5, 200), "estimator_lag_s": (0, 1), "acquire_conf_min": (0, 1)}
MODES = ["SEARCH", "VERIFY", "TRACK", "COAST", "REACQUIRE"]
SPEEDS = [("0.25x", 0.25), ("0.5x", 0.5), ("1x real time", 1.0), ("2x", 2.0), ("4x", 4.0), ("Max speed", 0.0)]
DEFAULT_SPEED_INDEX = 2
DURATION_RANGE = (1, 3600)
EXTRA_TARGETS_MAX = 8

# (form key, title, PS reference, hint)
SECTIONS = [
    ("screen", "Screen", "PS rows 1-2", "The whole scene the tracker observes."),
    ("camera", "Camera", "PS rows 3-6, 13-15", "The window the terminal points at, and how fast it can turn."),
    ("target", "Designated target", "PS rows 7-12", "The beacon to follow."),
    ("disturbance", "Disturbances", "PS rows 21-25", "Everything that degrades the picture. All zero is a clear sky."),
    ("tracker", "Tracker", "", "How the software finds and follows the beacon. The defaults are tuned; change with care."),
]
# while a video is loaded the scene, beacons and disturbances come from the file
VIDEO_LOCKED = {"target": "*", "disturbance": "*", "screen": ["width", "height", "background", "background_level", "star_density"],
                "camera": ["update_rate_hz"], "run": ["extra", "duration"]}


def section_object(cfg: RunConfig, key: str):
    return cfg.targets[0] if key == "target" else getattr(cfg, key)


def field_spec(name: str, value) -> dict | None:
    """The widget a field gets, identical in both front ends."""
    lo, hi = RANGES.get(name, (-1e9, 1e9))
    spec = {"name": name, "label": LABELS.get(name, name.replace("_", " ").capitalize()), "tip": TIPS.get(name, "")}
    if isinstance(value, bool):
        spec.update(kind="bool")
    elif isinstance(value, int):
        spec.update(kind="int", min=int(lo), max=int(hi), step=1)
    elif isinstance(value, float):
        narrow = hi - lo <= 2
        spec.update(kind="float", min=lo, max=hi, decimals=3 if narrow else 2, step=0.01 if narrow else 1.0)
    elif isinstance(value, str) and name in CHOICES:
        spec.update(kind="choice", choices=CHOICES[name])
    elif isinstance(value, str):
        spec.update(kind="text")
    else:
        return None
    return spec


def schema(cfg: RunConfig | None = None) -> list[dict]:
    """Panel sections in display order, each with its fields."""
    cfg = cfg or RunConfig()
    out = []
    for key, title, ref, hint in SECTIONS:
        obj = section_object(cfg, key)
        fields = [s for f in dataclasses.fields(obj) if f.name not in HIDDEN and (s := field_spec(f.name, getattr(obj, f.name)))]
        out.append({"key": key, "title": title, "ref": ref, "hint": hint, "fields": fields})
    return out


def extra_targets(t0: TargetConfig, existing: list[TargetConfig], extra: int, seed: int) -> list[TargetConfig]:
    """The designated target plus `extra` decoys: scenario decoys first, then generated ones."""
    rng = np.random.default_rng(seed + 99)
    motions = ["circular", "line", "figure8", "random", "sinusoidal"]
    targets = [t0]
    for i in range(extra):
        if i + 1 < len(existing):
            targets.append(existing[i + 1])
        else:
            targets.append(TargetConfig(shape=["circle", "square", "gaussian"][i % 3], size_px=int(rng.integers(6, 16)),
                                        intensity=int(rng.integers(150, 235)), motion=motions[i % len(motions)],
                                        speed_px_s=float(rng.uniform(60, 180)), radius_px=float(rng.uniform(200, 450)),
                                        period_s=float(rng.uniform(8, 20)), heading_deg=float(rng.uniform(0, 360)), start="centre"))
    return targets


def prepare_video_run(cfg: RunConfig) -> RunConfig:
    """A video run (Benchmark 2) processes the whole file, and the file already holds the scene,
    its beacons and disturbances. Duration and Extra targets are locked in video mode, so their
    panel values must not reach the run: a 30 s duration would cut a longer video short, and
    decoys would switch on the identity audit for spots that are not in the configuration."""
    cfg.duration_s = 0.0
    cfg.targets = cfg.targets[:1]
    return cfg


def new_random_seed(cfg: RunConfig) -> None:
    """'New seed each run': a fresh seed, and a fresh heading for line and sinusoidal paths."""
    cfg.seed = int(np.random.default_rng().integers(0, 10 ** 6))
    t0 = cfg.targets[0]
    if t0.motion in ("line", "sinusoidal"):
        t0.heading_deg = float(np.random.default_rng(cfg.seed).uniform(0, 360))


# ----------------------------------------------------------------------------- views
def display_stretch(inside: np.ndarray) -> np.ndarray:
    """Display-only contrast stretch of the camera window so faint scenes stay visible.
    Measured on the on-screen part only, and never more than 4x so an empty sky stays dark."""
    lo, hi = np.percentile(inside[::4, ::4], (1, 99.8))
    hi = max(hi, lo + 64.0)
    return np.clip((inside.astype(np.float32) - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)


def camera_crop(img: np.ndarray, window) -> np.ndarray:
    """What the camera window sees, stretched for display; black beyond the screen edge."""
    H, W = img.shape[:2]
    x0, y0, w, h = window
    xa, ya, xb, yb = max(x0, 0), max(y0, 0), min(x0 + w, W), min(y0 + h, H)
    crop = np.zeros((h, w) if img.ndim == 2 else (h, w, 3), np.uint8)
    if xb > xa and yb > ya:
        crop[ya - y0:yb - y0, xa - x0:xb - x0] = display_stretch(img[ya:yb, xa:xb])
    return crop


SCENE_LEGEND = [("accent", "camera window"), ("signal", "true beacon"), ("good", "estimate"), ("muted", "other targets")]


def scene_header(w: int, h: int, ifov_deg: float, t: float) -> str:
    return f"Screen {w} x {h} px  |  {w * ifov_deg:.1f} x {h * ifov_deg:.1f} deg  |  t {t:6.2f} s  |  grid 2 deg"


def camera_top(r, ifov_deg: float) -> tuple[str, str]:
    """(state text, detail text) for the top bar of the camera view."""
    err = r.tracking_err_px
    err_s = f"err {err:.1f} px ({err * ifov_deg * 3600:.0f} arcsec)" if np.isfinite(err) else "err n/a (no truth in a video)"
    return f"{r.mode}{'  locked' if r.locked else ''}", f"{err_s}   conf {r.confidence:.2f}   {r.tier}"


def camera_bottom(r) -> tuple[str, bool]:
    """(bottom bar text, gimbal at its rate limit)."""
    return (f"pan {r.cam_pan_deg:+.2f}  tilt {r.cam_tilt_deg:+.2f} deg   cmd {r.cmd_pan_rate:+.2f} {r.cmd_tilt_rate:+.2f} deg/s",
            bool(r.sat_pan or r.sat_tilt))


# ----------------------------------------------------------------------------- tiles
TILES = [("state", "State", "waiting"), ("acq", "Acquisition", "spec ≤ 2 s"), ("terr", "Tracking error", "mean, spec ≤ 10 px"),
         ("cerr", "Centroid error", "mean, vs truth"), ("lock", "Lock retention", "spec: loss < 5%"), ("fps", "Processing", "spec ≥ 20 FPS")]


def blank_tiles() -> dict:
    return {k: {"text": "–", "state": None, "unit": u} for k, _, u in TILES}


class LiveTiles:
    """Live specification tiles from the frames seen so far; the same rules in both apps."""

    def __init__(self):
        self.acq_t = None
        self.n_after = self.lock_after = self.track_after = 0
        self.terr_sum = 0.0; self.terr_n = 0
        self.cerr_sum = 0.0; self.cerr_n = 0
        self.proc = deque(maxlen=60)
        self.last = None

    def push(self, r) -> None:
        self.last = r
        if self.acq_t is None and r.locked:
            self.acq_t = r.t_sim
        if self.acq_t is not None:
            self.n_after += 1
            self.lock_after += bool(r.locked)
            self.track_after += r.mode == "TRACK"
            if np.isfinite(r.tracking_err_px):
                self.terr_sum += r.tracking_err_px; self.terr_n += 1
        if np.isfinite(r.centroid_err_px):
            self.cerr_sum += r.centroid_err_px; self.cerr_n += 1
        self.proc.append(r.proc_ms)

    def tiles(self) -> dict:
        T = blank_tiles()
        r = self.last
        if r is None:
            return T
        state = "pass" if r.mode == "TRACK" and r.locked else ("warn" if r.mode in ("COAST", "REACQUIRE") else None)
        T["state"] = {"text": r.mode, "state": state, "unit": "locked" if r.locked else "not locked"}
        if self.acq_t is not None:
            T["acq"].update(text=f"{self.acq_t:.2f} s", state="pass" if self.acq_t <= SPEC["acquisition_time_s"][1] else "fail")
            if self.terr_n:
                m = self.terr_sum / self.terr_n
                T["terr"].update(text=f"{m:.1f} px", state="pass" if m <= SPEC["tracking_err_mean_px"][1] else "fail")
            else:
                T["terr"].update(text="n/a", unit="no truth in video")
            lk = 100.0 * self.lock_after / max(self.n_after, 1)
            trk = 100.0 * self.track_after / max(self.n_after, 1)
            T["lock"].update(text=f"{lk:.1f} %", state="pass" if 100 - lk < SPEC["target_loss_pct"][1] else "fail", unit=f"tracked {trk:.0f}%")
        else:
            T["acq"].update(text="searching", state="warn")
        if self.cerr_n:
            m = self.cerr_sum / self.cerr_n
            T["cerr"].update(text=f"{m:.3f} px", state="pass" if m < 2 else "warn")
        else:
            T["cerr"].update(text="n/a", unit="no truth in video")
        fps = 1000.0 / max(float(np.mean(self.proc)), 1e-3)
        T["fps"].update(text=f"{fps:.0f} FPS", state="pass" if fps >= SPEC["fps_mean"][1] else "fail")
        return T


def _num(v: dict, k: str):
    x = v.get(k)
    return None if x is None or (isinstance(x, float) and not np.isfinite(x)) else x


def final_tiles(v: dict, passed: dict) -> dict:
    """After a run the tiles show the report's numbers, not the last live estimate."""
    ok = lambda k: {True: "pass", False: "fail"}.get(passed.get(k))
    T = blank_tiles()
    T["state"] = {"text": "finished", "state": None, "unit": f"{v.get('frames', 0)} frames"}
    a = _num(v, "acquisition_time_s")
    T["acq"].update(text=f"{a:.2f} s" if a is not None else "not acquired", state=ok("acquisition_time_s") if a is not None else "fail")
    te = _num(v, "tracking_err_mean_px")
    T["terr"].update(text=f"{te:.1f} px" if te is not None else "n/a", state=ok("tracking_err_mean_px"))
    if te is None:
        T["terr"]["unit"] = "no truth in video"
    ce = _num(v, "centroid_err_mean_px")
    T["cerr"].update(text=f"{ce:.3f} px" if ce is not None else "n/a", state=("pass" if ce < 2 else "warn") if ce is not None else None)
    if ce is None:
        T["cerr"]["unit"] = "no truth in video"
    lk, trk = _num(v, "lock_retention_pct"), _num(v, "tracked_pct")
    T["lock"].update(text=f"{lk:.1f} %" if lk is not None else "n/a", state=ok("target_loss_pct"))
    if trk is not None:
        T["lock"]["unit"] = f"tracked {trk:.0f}%"
    fps = _num(v, "fps_mean")
    T["fps"].update(text=f"{fps:.0f} FPS" if fps is not None else "n/a", state=ok("fps_mean"))
    return T


# ----------------------------------------------------------------------------- text
def telemetry_lines(r) -> str:
    shift = (f"shift      {r.ego_dx:+6.2f} {r.ego_dy:+6.2f} px" if max(abs(r.ego_dx), abs(r.ego_dy)) <= 60 else "shift      unreliable, ignored")
    return "\n".join([
        f"frame      {r.frame}", f"t          {r.t_sim:8.2f} s", f"state      {r.mode}", f"locked     {'yes' if r.locked else 'no'}",
        f"detector   {r.tier}", f"candidates {r.n_candidates}", f"confidence {r.confidence:8.2f}", f"snr        {r.snr:8.1f}",
        f"psf sigma  {r.sigma:8.2f} px", "",
        f"pan        {r.cam_pan_deg:+8.3f} deg", f"tilt       {r.cam_tilt_deg:+8.3f} deg",
        f"cmd pan    {r.cmd_pan_rate:+8.3f} deg/s", f"cmd tilt   {r.cmd_tilt_rate:+8.3f} deg/s",
        f"saturated  {'pan ' if r.sat_pan else ''}{'tilt' if r.sat_tilt else ''}{'no' if not (r.sat_pan or r.sat_tilt) else ''}", "",
        f"detection  {r.det_x:8.2f} {r.det_y:8.2f}", f"estimate   {r.est_x:8.2f} {r.est_y:8.2f}",
        f"velocity   {r.vel_x:+8.1f} {r.vel_y:+8.1f} px/s", f"uncert.    {r.uncertainty_px:8.2f} px",
        f"models     cv {r.p_cv:.2f} ca {r.p_ca:.2f} ct {r.p_ct:.2f}", shift, "",
        f"truth      {r.true_x:8.2f} {r.true_y:8.2f}", f"in window  {'yes' if r.in_window else 'no'}",
        f"track err  {r.tracking_err_px:8.2f} px", f"centroid   {r.centroid_err_px:8.3f} px", "",
        f"proc       {r.proc_ms:8.2f} ms", f"fps inst   {r.fps_inst:8.1f}",
    ])


def welcome_text() -> str:
    return "\n".join([
        "Getting started", "",
        "1  Pick a scenario in the toolbar,", "   or set values on the left.",
        "2  Press Start, or Space.", "3  Watch the tiles: green meets", "   the specification, amber not", "   yet.",
        "4  When the run ends the summary", "   opens. Every run writes the CSV,", "   summary, PDF report and the", "   scenario file.", "",
        "Benchmark 2", "", "Open video, then Start. The video", "replaces the simulated scene.", "",
        "Keys", "", "Space   start or pause", "N       one frame while paused", "Esc     stop",
        "Ctrl+S  save scenario", "Ctrl+P  screenshot", "Ctrl+O  open video", "",
        "Hover any setting to see what it", "does and which PS row it covers.",
    ])


def about_text() -> str:
    return (
        f"ARGUS v{__version__}  (SIH26169, Department of Space / ISRO SAC)\n"
        "Acquire, Recognise, Guide, Update, Stabilise\n\n"
        "WHAT YOU SEE\n"
        "Left picture: the whole scene. Cyan box = camera window. Orange circle = true beacon. Green cross = tracker estimate. Grey circles = other targets.\n"
        "Right picture: what the camera window sees. Dashed ring = capture radius (green when locked). "
        "Green box = this frame's detection. Orange dot = prediction with uncertainty ring. Line from centre = pointing error.\n"
        "Tiles: live specification check while running, the report's final numbers after. Tracked = share of frames in TRACK; lock also needs the beacon centred.\n"
        "Plots: errors, gimbal command with its limit, processing time with the 20 FPS budget, tracker state.\n\n"
        "OUTPUT\nEvery run writes a folder FSOC_<sim|video>_<name>_seed<N>_<date-time>/ holding <label>_frames.csv, _summary.json, _report.pdf and _scenario.yaml.\n\n"
        "The desktop application and the web app are the same program: the same engine, panel, tiles, plots and report.")


def summary_text(v: dict, passed: dict, frames_path: str = "", report_path: str = "") -> str:
    """The end-of-run summary shown in the 'Run complete' dialog of both apps."""
    def f(k, fmt="{:.2f}"):
        x = _num(v, k)
        return "n/a" if x is None else fmt.format(x)
    pf = lambda k: {True: "PASS", False: "FAIL", None: "n/a"}[passed.get(k)]
    msg = (f"Frames {v.get('frames')}    duration {f('duration_s')} s\n"
           f"FPS mean {f('fps_mean', '{:.1f}')}  ({pf('fps_mean')})\n"
           f"Acquisition {f('acquisition_time_s')} s  ({pf('acquisition_time_s')})\n"
           f"Tracking error mean {f('tracking_err_mean_px')} px, max {f('tracking_err_max_px')} px  ({pf('tracking_err_mean_px')})\n"
           f"  with vibration removed: {f('tracking_err_stab_mean_px')} px\n"
           f"Centroiding error mean {f('centroid_err_mean_px', '{:.3f}')} px, RMSE {f('centroid_err_rmse_px', '{:.3f}')} px\n"
           f"Tracked {f('tracked_pct', '{:.1f}')} %   Lock retention {f('lock_retention_pct', '{:.1f}')} %   target loss {f('target_loss_pct', '{:.1f}')} %  ({pf('target_loss_pct')})\n"
           f"Re-acquisitions {v.get('reacq_count', 0)}, max {f('reacq_time_max_s')} s  ({pf('reacq_time_max_s')})"
           + (f"; lock lost for the last {f('lock_lost_at_end_s')} s, not regained" if (_num(v, "lock_lost_at_end_s") or 0) > 0 else "") + "\n"
           f"Processing {f('proc_ms_mean')} ms mean, {f('proc_ms_p99')} ms p99")
    if frames_path or report_path:
        msg += f"\n\nLog: {frames_path}\nReport: {report_path}"
    sat = v.get("slew_saturation_pct") or 0.0
    if sat > 20:
        msg += (f"\n\nNote: the gimbal was at its rate limit in {sat:.0f}% of frames, so the target moved faster than the camera can turn. "
                f"Raise Max pan / Max tilt (the PS allows 5 to 10 deg/s) or widen the FOV and run again.")
    return msg


def video_loaded_lines(name: str, info: dict, cam) -> str:
    w, h, fps, n = info["width"], info["height"], info["fps"], info["frames"]
    lines = ["Video loaded, settings calibrated", "", f"file    {name}", f"size    {w} x {h} px as displayed"]
    if info.get("rotation_deg"):
        lines.append(f"turn    {info['rotation_deg']:.0f} deg tag applied")
    lines.append(f"rate    {fps:.2f} fps average")
    if info.get("variable_rate"):
        lines.append(f"        variable rate, {info.get('fps_timestamps', fps):.1f} fps by timestamps")
    lines += [f"frames  {n} counted", f"length  {info['seconds']:.2f} s", "",
              "Calibrated into the panel:", f"  screen {w} x {h}, update rate {fps:.2f} Hz", "",
              "Not in the file, set by you:", f"  camera window {cam.width} x {cam.height} px",
              f"  FOV {cam.fov_w_deg:g} x {cam.fov_h_deg:g} deg, so 1 px =", f"  {cam.ifov_deg * 3600:.1f} arcsec; degree readouts", "  depend on this setting.", "",
              "Target and disturbance settings are", "locked: the video already contains", "them. No ground truth exists, so", "tracking and centroiding error read", "n/a; lock, acquisition, re-acquisition", "and FPS are measured.", "",
              "Press Start (Space) to run."]
    return "\n".join(lines)


def video_preview_header(info: dict) -> str:
    rot = f"   rotated {info['rotation_deg']:.0f} deg" if info.get("rotation_deg") else ""
    vfr = "   variable rate" if info.get("variable_rate") else ""
    return f"{info['width']} x {info['height']} px   {info['fps']:.2f} fps{vfr}   {info['frames']} frames   {info['seconds']:.2f} s{rot}"


def status_text(kind: str, **kw) -> str:
    """Status-bar lines, the same wording in both apps."""
    return {
        "ready": "Simulator input. Pick a scenario or set values, then press Start.",
        "video": f"Benchmark 2 input: {kw.get('path', '')}  (simulator bypassed). Press Start.",
        "loaded": f"Loaded {kw.get('path', '')}. Its seed and paths are used as written; tick New seed each run for a fresh one. Press Start.",
        "running": f"Running '{kw.get('name', '')}' seed {kw.get('seed', '')}  ->  {kw.get('out', '')}",
        "finished": f"Finished. Report written to {kw.get('out', '')}",
    }[kind]


def front_end_bundle() -> dict:
    """Everything the web page needs to build the same interface as the desktop app."""
    return {
        "version": __version__, "sections": schema(), "tiles": TILES, "modes": MODES, "speeds": SPEEDS,
        "default_speed": DEFAULT_SPEED_INDEX, "duration_range": DURATION_RANGE, "extra_max": EXTRA_TARGETS_MAX,
        "presets": ATMOSPHERE_PRESETS, "video_locked": VIDEO_LOCKED, "legend": SCENE_LEGEND,
        "welcome": welcome_text(), "about": about_text(), "status_ready": status_text("ready"),
        "status_loaded": status_text("loaded", path="{path}"),
    }
