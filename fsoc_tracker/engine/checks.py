"""Scenario check: what a set of values means before it is run.

Three kinds of note, the same in the desktop app, the web app, the command line and the report:

- clamped: a value outside the accepted input range (config.LIMITS) was brought back into it,
  so a typing slip (13 typed where 0.13 was meant) cannot produce an impossible picture;
- beyond_ps: a value is outside what the problem statement specifies (26169.pdf, the row is
  named), so the PS performance targets are not promised for it;
- physical: the combination asks for something the modelled camera cannot do at all, such as a
  beacon moving faster than the gimbal can turn;
- near_limit: it can be done, with little margin (a beacon above 70% of the turn rate).

Values inside the PS envelope produce no note. The check never changes a value that is inside
the accepted range.
"""
from __future__ import annotations

import dataclasses
import math
from pathlib import Path

from ..world.sprites import parse_mask
from .config import LIMITS, RunConfig, parse_xy, target_name

SHAPES = ("square", "circle", "gaussian", "cross", "ring", "diamond", "custom")
DESIGNATIONS = ("auto", "appearance", "start", "cue")


def _note(level: str, field: str, text: str) -> dict:
    return {"level": level, "field": field, "text": text}


def _clamp_object(obj, where: str, notes: list[dict]) -> None:
    for f in dataclasses.fields(obj):
        lim = LIMITS.get(f.name)
        v = getattr(obj, f.name)
        if lim is None or isinstance(v, bool) or not isinstance(v, (int, float)):
            continue
        if isinstance(v, float) and not math.isfinite(v):
            nv = lim[0]
        else:
            nv = min(max(v, lim[0]), lim[1])
        is_int = isinstance(f.default, int) and not isinstance(f.default, bool) if f.default is not dataclasses.MISSING else isinstance(v, int)
        nv = int(round(nv)) if is_int else float(nv)
        if nv != v or type(nv) is not type(v):
            if nv == v:              # an int typed into a float field: fix the type silently
                setattr(obj, f.name, nv)
                continue
            setattr(obj, f.name, nv)
            notes.append(_note("clamped", f"{where}.{f.name}", f"{where} {f.name} = {v:g} is outside the accepted range "
                                                                f"{lim[0]:g} to {lim[1]:g}; set to {nv:g}."))


def max_path_speed_px_s(t) -> float:
    """Peak speed of a target's path in screen px/s (approximate for curved paths)."""
    m = t.motion
    if m in ("line", "waypoints"):
        return float(t.speed_px_s)
    if m == "random":
        return 2.0 * float(t.speed_px_s)          # the random walk is capped at twice the set speed
    if m == "sinusoidal":
        return float(t.speed_px_s) + 0.5 * t.radius_px * 2 * math.pi / max(t.period_s, 1e-6)
    if m in ("circular", "spiral"):
        return t.radius_px * 2 * math.pi / max(t.period_s, 1e-6)
    if m == "figure8":
        return t.radius_px * 2 * math.pi / max(t.period_s, 1e-6) * math.sqrt(2.0)
    return 0.0


def check_config(cfg: RunConfig, clamp: bool = True) -> list[dict]:
    """Return the notes for `cfg`; with clamp=True out-of-range values are fixed in place."""
    notes: list[dict] = []
    if clamp:
        for sec in ("screen", "camera", "disturbance", "tracker"):
            _clamp_object(getattr(cfg, sec), sec, notes)
        for i, t in enumerate(cfg.targets):
            _clamp_object(t, target_name(t, i), notes)
            if t.shape not in SHAPES:
                notes.append(_note("clamped", f"target{i}.shape", f"{target_name(t, i)}: unknown shape '{t.shape}', using square."))
                t.shape = "square"
            if not t.height_px:
                t.height_px = t.size_px
        lo, hi = LIMITS["duration_s"]
        if not cfg.video and not (lo <= cfg.duration_s <= hi):
            d_s = cfg.duration_s
            # min/max pass NaN through, so non-finite values are placed explicitly
            nv = 30.0 if d_s != d_s else (hi if d_s == math.inf else lo if d_s == -math.inf else min(max(d_s, lo), hi))
            notes.append(_note("clamped", "duration_s", f"Duration {cfg.duration_s:g} s is outside {lo:g} to {hi:g} s; set to {nv:g}."))
            cfg.duration_s = nv
        if cfg.designation not in DESIGNATIONS:
            notes.append(_note("clamped", "designation", f"Unknown designation '{cfg.designation}', using auto."))
            cfg.designation = "auto"
        try:
            cfg.designated = int(cfg.designated)       # a scenario file may hold 1.0 or "1"
        except (TypeError, ValueError):
            notes.append(_note("clamped", "designated", f"Designated target '{cfg.designated}' is not a number; using target 1."))
            cfg.designated = 0
        if cfg.targets and not (0 <= cfg.designated < len(cfg.targets)):
            notes.append(_note("clamped", "designated", f"Designated target {cfg.designated + 1} does not exist; using target 1."))
            cfg.designated = 0
        # disturbance schedule: every entry must be able to take effect
        kept = []
        for c in cfg.schedule:
            if not math.isfinite(c.t_s):
                notes.append(_note("clamped", "schedule", f"A disturbance change at t = {c.t_s} s cannot be placed in time; it was dropped."))
                continue
            if c.t_s < 0:
                notes.append(_note("clamped", "schedule", f"A disturbance change at t = {c.t_s:g} s is before the start; it applies at 0 s."))
                c.t_s = 0.0
            if not cfg.video and c.t_s >= cfg.duration_s:
                notes.append(_note("beyond_ps", "schedule", f"A disturbance change at t = {c.t_s:g} s is after the run ends ({cfg.duration_s:g} s) and never applies."))
            if not c.disturbance:
                notes.append(_note("clamped", "schedule", f"The disturbance change at t = {c.t_s:g} s has no usable settings; it was dropped."))
                continue
            kept.append(c)
        cfg.schedule = kept
        if cfg.video and len(cfg.targets) > 1:
            # a video brings its own beacons; only the designated target's appearance is used,
            # as the description of what to look for
            cfg.targets = [cfg.targets[cfg.designated]]
            cfg.designated = 0

    d, cam, scr = cfg.disturbance, cfg.camera, cfg.screen
    ps = []
    # rows 1 to 5
    if scr.width < 2000 or scr.height < 2000:
        ps.append(("screen", f"Screen {scr.width} x {scr.height} px is below the PS minimum of 2000 x 2000 (row 1)."))
    if cam.update_rate_hz < 20:
        ps.append(("camera.update_rate_hz", f"Update rate {cam.update_rate_hz:g} Hz is below the PS update interval of 20 Hz (row 15) and the 30 Hz camera rate (row 5)."))
    elif cam.update_rate_hz < 30:
        ps.append(("camera.update_rate_hz", f"Update rate {cam.update_rate_hz:g} Hz is below the PS camera rate of 30 Hz minimum (row 5)."))
    for name, v, row in (("max_pan_rate_deg_s", cam.max_pan_rate_deg_s, 13), ("max_tilt_rate_deg_s", cam.max_tilt_rate_deg_s, 14)):
        if v < 5 or v > 10:
            ps.append((f"camera.{name}", f"{'Pan' if row == 13 else 'Tilt'} speed {v:g} deg/s is outside the PS range of 5 to 10 deg/s (row {row})."))
    # rows 8 to 12
    for i, t in enumerate(cfg.targets):
        w, h = t.dims
        if not (5 <= w <= 20 and 5 <= h <= 20):
            ps.append((f"target{i}.size", f"{target_name(t, i)}: size {w} x {h} px is outside the PS range of 5-20 x 5-20 px (row 10)."))
        if t.shape == "custom" and not t.mask.strip():
            ps.append((f"target{i}.mask", f"{target_name(t, i)}: shape custom has no mask; a square is drawn. Enter rows of 0 and 1, for example 010;111;010."))
        elif t.shape == "custom" and parse_mask(t.mask) is None:
            ps.append((f"target{i}.mask", f"{target_name(t, i)}: the mask '{t.mask[:40]}' cannot be read (rows of 0 and 1 with at least one 1, "
                                          f"or an image file); a square is drawn. Example: 010;111;010."))
    # rows 21 to 25
    if d.salt_pepper_frac > 0.10 + 1e-9:
        ps.append(("disturbance.salt_pepper_frac", f"Salt and pepper {100 * d.salt_pepper_frac:.0f}% of pixels is above the PS 'around 10%' (row 21)."))
    if d.gaussian_sigma > 20:
        ps.append(("disturbance.gaussian_sigma", f"Gaussian noise sigma {d.gaussian_sigma:g} is above the PS maximum of 20 (row 22)."))
    if d.jitter_px > 20:
        ps.append(("disturbance.jitter_px", f"Camera jitter {d.jitter_px:g} px/frame is above the PS maximum of +/- 20 px/frame (row 23)."))
    if d.platform_px_frame > 20:
        ps.append(("disturbance.platform_px_frame", f"Platform motion {d.platform_px_frame:g} px/frame is above the PS maximum of 20 px/frame (row 25)."))
    if d.turbulence > 0.6:
        ps.append(("disturbance.turbulence", f"Turbulence {d.turbulence:.2f} is above the strongest atmosphere preset (rain, 0.6); the beacon wanders and flickers more than any PS condition describes."))
    if d.contrast < 0.4:
        ps.append(("disturbance.contrast", f"Contrast {d.contrast:.2f} is below the fog preset (0.40), the strongest PS atmosphere (row 24)."))
    for f, text in ps:
        notes.append(_note("beyond_ps", f, text))

    # physical limits of the modelled camera
    px_per_frame = cam.max_pan_rate_deg_s / max(cam.ifov_deg, 1e-9) / max(cam.update_rate_hz, 1e-9)
    px_per_s = px_per_frame * cam.update_rate_hz
    t0 = cfg.designated_target()
    if t0 is not None and not cfg.video:
        v = max_path_speed_px_s(t0)
        if v > px_per_s:
            notes.append(_note("physical", "target.speed", f"{target_name(t0, cfg.designated_index())} moves at up to {v:.0f} px/s but the camera turns at most "
                                                         f"{px_per_s:.0f} px/s ({cam.max_pan_rate_deg_s:g} deg/s): it cannot be kept centred."))
        elif v > 0.7 * px_per_s:
            notes.append(_note("near_limit", "target.speed", f"{target_name(t0, cfg.designated_index())} moves at up to {v:.0f} px/s, {100 * v / px_per_s:.0f}% of the camera's "
                                                         f"{px_per_s:.0f} px/s turn rate: little margin left for noise and vibration."))
    motion = d.jitter_px + (d.platform_px_frame if d.platform_motion != "none" else 0.0)
    if motion > px_per_frame:
        notes.append(_note("physical", "disturbance.motion", f"Jitter plus platform motion reach {motion:g} px/frame, more than the camera can turn in one frame "
                                                             f"({px_per_frame:.1f} px/frame at {cam.max_pan_rate_deg_s:g} deg/s): the picture moves faster than it can be followed."))
    if d.salt_pepper_frac >= 0.5 - 1e-9:
        notes.append(_note("physical", "disturbance.salt_pepper_frac", "Salt and pepper covers half of all pixels: the beacon is buried; detection is unlikely."))
    if cfg.designation == "cue" and parse_xy(cfg.designation_cue) is None:
        notes.append(_note("physical", "designation_cue", "Designation 'cue' needs a point: click the beacon on the scene (video: on the first frame) or type x,y."))
    if cfg.video_truth and not Path(cfg.video_truth).is_file():
        notes.append(_note("physical", "video_truth", f"Ground-truth file {cfg.video_truth} not found: errors cannot be computed."))
    if cfg.designation == "start" and cfg.video:
        notes.append(_note("physical", "designation", "Designation 'start' needs the simulator (a video has no configured start); click the beacon on the first frame instead."))
    if t0 is not None and len(cfg.targets) > 1 and cfg.designation == "appearance" and cfg.look_alikes():
        same = [target_name(cfg.targets[i], i) for i in cfg.look_alikes()]
        notes.append(_note("physical", "designation", f"{', '.join(same)} look{'s' if len(same) == 1 else ''} the same as the designated "
                                                      f"{target_name(t0, cfg.designated_index())}: by appearance alone the tracker cannot tell them apart "
                                                      f"(designation is forced to appearance in this scenario file; auto would use the start position)."))
    return notes


def check_lines(notes: list[dict]) -> list[str]:
    """Notes as text lines, most serious first."""
    order = {"physical": 0, "near_limit": 1, "beyond_ps": 2, "clamped": 3}
    tag = {"physical": "Cannot be met", "near_limit": "Near the limit", "beyond_ps": "Beyond the PS", "clamped": "Corrected"}
    return [f"{tag[n['level']]}: {n['text']}" for n in sorted(notes, key=lambda n: order.get(n["level"], 3))]
