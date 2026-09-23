"""Automatic performance report (PDF) from the telemetry of one run."""
from __future__ import annotations

import math
import platform
import textwrap
from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
import numpy as np

from .. import __version__
from .checks import check_lines
from .config import RunConfig, target_name
from .metrics import DEFINITIONS, SPEC, Summary
from .telemetry import Record

INK, MUTED, ACCENT, SIGNAL, GOOD, LINE = "#101B23", "#61747F", "#0B6E87", "#A8460F", "#2B6B50", "#D3DCE1"


def _fmt(v):
    if v is None:
        return "n/a"
    if isinstance(v, float):
        return "n/a" if math.isnan(v) else (f"{v:.3f}" if abs(v) < 100 else f"{v:.1f}")
    return str(v)


def _para(fig, x: float, y: float, text: str, chars: int, size: float, color: str, step: float, **kw) -> float:
    """Draw `text` wrapped at `chars` characters, one line per fig.text, and return the y below
    it. Wrapping by hand keeps every block exactly as tall as it is, so nothing overlaps."""
    lines = textwrap.wrap(text, chars) or [""]
    for ln in lines:
        fig.text(x, y, ln, fontsize=size, color=color, **kw)
        y -= step
    return y


def write_report(cfg: RunConfig, records: list[Record], summary: Summary, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    t = np.array([r.t_sim for r in records]) if records else np.zeros(0)
    with PdfPages(path) as pdf:
        # ---------------------------------------------------------- page 1
        fig = plt.figure(figsize=(8.27, 11.69))
        fig.patch.set_facecolor("white")
        fig.text(0.07, 0.955, "ARGUS performance report", fontsize=17, weight="bold", color=INK)
        sub = f"Run '{cfg.name}'   seed {cfg.seed}   {datetime.now():%Y-%m-%d %H:%M}   v{__version__}   {platform.system()} {platform.machine()}"
        fig.text(0.07, 0.932, sub, fontsize=8.5, color=MUTED)
        src = (f"Source: video {cfg.video}  ({cfg.screen.width}x{cfg.screen.height} px as displayed, {cfg.camera.update_rate_hz:.2f} fps average, "
               f"{len(records)} frames, {cfg.duration_s:.2f} s)" + (f"; ground truth {cfg.video_truth}" if cfg.video_truth else "; no ground-truth file")
               if cfg.video else (
            f"Source: simulator, screen {cfg.screen.width}x{cfg.screen.height}, targets {len(cfg.targets)}, "
            f"motion {cfg.designated_target().motion if cfg.targets else '-'}, atmosphere {cfg.disturbance.atmosphere}, "
            f"platform {cfg.disturbance.platform_motion} {cfg.disturbance.platform_px_frame:g} px/f, jitter {cfg.disturbance.jitter_px:g} px, "
            f"S&P {100 * cfg.disturbance.salt_pepper_frac:g}%, gauss {cfg.disturbance.gaussian_sigma:g}, turbulence {cfg.disturbance.turbulence:g}"))
        _para(fig, 0.07, 0.908, src, 122, 7.5, MUTED, 0.013)
        fig.text(0.07, 0.878, f"Camera {cfg.camera.width}x{cfg.camera.height}, FOV {cfg.camera.fov_w_deg:g}x{cfg.camera.fov_h_deg:g} deg, "
                 f"IFOV {cfg.camera.ifov_deg*3600:.1f} arcsec/px, max rate {cfg.camera.max_pan_rate_deg_s:g}/{cfg.camera.max_tilt_rate_deg_s:g} deg/s, "
                 f"{cfg.camera.update_rate_hz:g} Hz", fontsize=8, color=MUTED)
        # which target was followed, and how it was designated (PS: "a designated moving target")
        des = getattr(summary, "designation", {}) or {}
        y = 0.858
        if cfg.targets and not cfg.video:
            parts = []
            for i, tc in enumerate(cfg.targets):
                w, h = tc.dims
                mark = " (designated)" if i == cfg.designated_index() else ""
                parts.append(f"{target_name(tc, i)}{mark}: {tc.shape} {w}x{h} px, {tc.motion}")
            y = _para(fig, 0.07, y, "Targets: " + ";  ".join(parts), 122, 7.5, MUTED, 0.013)
        if des:
            line = f"Followed {des.get('target', '')}, designation: {des.get('mode', 'appearance')}"
            if des.get("cue"):
                line += f" at {des['cue']}"
            if des.get("ambiguous_frames"):
                line += (f".  In {des['ambiguous_frames']} search frames another target looked just like it: by appearance alone the choice may be wrong "
                         f"(use designation 'start' or click the beacon)")
            y = _para(fig, 0.07, y, line, 122, 7.5, SIGNAL if des.get("ambiguous_frames") else MUTED, 0.013)
        y -= 0.008
        # spec table
        fig.text(0.07, y, "Specification check", fontsize=11, weight="bold", color=INK); y -= 0.022
        for k, (op, lim) in SPEC.items():
            v = summary.values.get(k)
            p = summary.passed.get(k)
            col = GOOD if p else (SIGNAL if p is False else MUTED)
            label = "PASS" if p else ("FAIL" if p is False else "n/a")
            fig.text(0.07, y, k.replace("_", " "), fontsize=9, color=INK)
            fig.text(0.47, y, f"{op} {lim:g}", fontsize=9, color=MUTED)
            fig.text(0.62, y, _fmt(v), fontsize=9, color=INK)
            fig.text(0.80, y, label, fontsize=9, weight="bold", color=col)
            y -= 0.02
        notes = []
        if not summary.truth_available:
            notes.append("Ground truth unavailable (video input): tracking and centroiding error are not computed; lock is judged from the tracker's own estimate.")
        sat = summary.values.get("slew_saturation_pct", 0.0)
        if sat > 20:
            notes.append(f"Gimbal at its rate limit in {sat:.0f}% of frames: the target moved faster than the camera can turn at {cfg.camera.max_pan_rate_deg_s:g} deg/s "
                         f"({cfg.camera.max_pan_rate_deg_s / cfg.camera.ifov_deg / cfg.camera.update_rate_hz:.0f} px per frame). Raise the rate limit (PS allows 5 to 10 deg/s) or widen the FOV.")
        stab = summary.values.get("tracking_err_stab_mean_px")
        if cfg.disturbance.jitter_px > 0 and stab is not None and summary.truth_available:
            notes.append(f"Camera vibration of +/- {cfg.disturbance.jitter_px:g} px per frame shifts the whole picture at random every frame. No controller can "
                         f"anticipate a random jump before the frame arrives, so the raw tracking error carries it; with the vibration removed the pointing error is "
                         f"{stab:.1f} px, which is the part the gimbal can physically follow.")
        cnn = summary.values.get("cnn_frames_pct", 0.0)
        if cnn > 0:
            notes.append(f"The AI detector supplied the measurement in {cnn:.0f}% of frames (used when the classical detector found nothing near the prediction).")
        # scenario check: values beyond the PS, values the camera cannot follow, corrected inputs
        for line in check_lines(getattr(summary, "checks", []) or [])[:6]:
            notes.append("Scenario check. " + line)
        y -= 0.004
        for n_ in notes:
            y = _para(fig, 0.07, y, n_, 122, 7.5, SIGNAL, 0.013) - 0.005
        y -= 0.012
        fig.text(0.07, y, "All metrics, with definitions", fontsize=11, weight="bold", color=INK); y -= 0.022
        for k, v in summary.values.items():
            fig.text(0.07, y, k.replace("_", " "), fontsize=8.5, color=INK)
            fig.text(0.40, y, _fmt(v), fontsize=8.5, color=INK, weight="bold")
            d = DEFINITIONS.get(k, "")
            y_end = _para(fig, 0.50, y, d, 70, 6.6, MUTED, 0.0105)
            y = min(y - 0.0195, y_end - 0.006)
            if y < 0.07:                      # continue on a new page rather than drop metrics
                pdf.savefig(fig); plt.close(fig)
                fig = plt.figure(figsize=(8.27, 11.69)); fig.patch.set_facecolor("white")
                y = 0.955
                fig.text(0.07, y, "All metrics, with definitions (continued)", fontsize=11, weight="bold", color=INK); y -= 0.03
        pdf.savefig(fig); plt.close(fig)

        # ---------------------------------------------------------- page 2
        if records:
            fig, axes = plt.subplots(4, 1, figsize=(8.27, 11.69), sharex=True)
            fig.subplots_adjust(hspace=0.35, left=0.1, right=0.97, top=0.95, bottom=0.06)
            te = np.array([r.tracking_err_px for r in records])
            ce = np.array([r.centroid_err_px for r in records])
            ax = axes[0]
            if np.isfinite(te).any():
                ax.plot(t, te, color=ACCENT, lw=0.9, label="tracking error (true beacon to window centre)")
            if np.isfinite(ce).any():
                ax.plot(t, ce, color=SIGNAL, lw=0.9, label="centroiding error (measured to true)")
            ax.axhline(10, color=LINE, ls="--", lw=0.8)
            ax.set_ylabel("pixels"); ax.set_title("Errors", fontsize=10, loc="left")
            if ax.get_legend_handles_labels()[0]:
                ax.legend(fontsize=7, loc="upper right")
            else:
                ax.text(0.5, 0.5, "no ground truth in a video: errors are not computed", transform=ax.transAxes, ha="center", va="center", fontsize=8, color=MUTED)
            ax = axes[1]
            modes = ["SEARCH", "VERIFY", "TRACK", "COAST", "REACQUIRE"]
            mv = np.array([modes.index(r.mode) for r in records])
            ax.step(t, mv, where="post", color=INK, lw=0.9)
            ax.set_yticks(range(len(modes))); ax.set_yticklabels(modes, fontsize=7)
            ax.set_title("Tracker state", fontsize=10, loc="left")
            ax = axes[2]
            ax.plot(t, [r.cmd_pan_rate for r in records], color=ACCENT, lw=0.8, label="pan rate")
            ax.plot(t, [r.cmd_tilt_rate for r in records], color=SIGNAL, lw=0.8, label="tilt rate")
            for lim in (cfg.camera.max_pan_rate_deg_s, -cfg.camera.max_pan_rate_deg_s):
                ax.axhline(lim, color=LINE, ls="--", lw=0.8)
            ax.set_ylabel("deg/s"); ax.legend(fontsize=7, loc="upper right"); ax.set_title("Gimbal command (dashed: limit)", fontsize=10, loc="left")
            ax = axes[3]
            ax.plot(t, [r.proc_ms for r in records], color=INK, lw=0.8)
            ax.axhline(50, color=LINE, ls="--", lw=0.8)
            ax.set_ylabel("ms / frame"); ax.set_xlabel("time (s)"); ax.set_title("Processing time (dashed: 20 FPS)", fontsize=10, loc="left")
            for ax in axes:
                ax.grid(alpha=0.25); ax.spines[["top", "right"]].set_visible(False)
            pdf.savefig(fig); plt.close(fig)

            # ------------------------------------------------------ page 3
            fig, axes = plt.subplots(2, 2, figsize=(8.27, 11.69))
            fig.subplots_adjust(hspace=0.35, wspace=0.3, left=0.1, right=0.97, top=0.95, bottom=0.06)
            ax = axes[0, 0]
            tx = np.array([r.true_x for r in records]); ty = np.array([r.true_y for r in records])
            if np.isfinite(tx).any():
                ax.plot(tx, ty, color=SIGNAL, lw=0.8, label="true beacon")
            ax.plot([r.win_cx for r in records], [r.win_cy for r in records], color=ACCENT, lw=0.8, label="window centre")
            ax.invert_yaxis(); ax.set_aspect("equal"); ax.legend(fontsize=7); ax.set_title("Paths on the screen", fontsize=10, loc="left")
            ax = axes[0, 1]
            fin = te[np.isfinite(te)]
            if len(fin):
                ax.hist(fin, bins=40, color=ACCENT); ax.axvline(10, color=SIGNAL, ls="--")
            ax.set_title("Tracking error histogram", fontsize=10, loc="left"); ax.set_xlabel("px")
            ax = axes[1, 0]
            ax.plot(t, [r.p_cv for r in records], lw=0.8, label="constant velocity")
            ax.plot(t, [r.p_ca for r in records], lw=0.8, label="constant acceleration")
            ax.plot(t, [r.p_ct for r in records], lw=0.8, label="coordinated turn")
            ax.set_ylim(0, 1); ax.legend(fontsize=7); ax.set_title("Motion model probabilities", fontsize=10, loc="left"); ax.set_xlabel("time (s)")
            ax = axes[1, 1]
            tiers = [r.tier for r in records]
            counts = [tiers.count(k) for k in ("classical", "cnn", "none")]
            ax.bar(["classical", "AI (cnn)", "no detection"], counts, color=[ACCENT, SIGNAL, LINE])
            ax.set_title("Which detector provided the measurement", fontsize=10, loc="left")
            for ax in axes.ravel():
                ax.grid(alpha=0.25); ax.spines[["top", "right"]].set_visible(False)
            pdf.savefig(fig); plt.close(fig)
    return path
