"""Desktop application: PyQt6 front end over the same Simulation the CLI uses."""
from __future__ import annotations

import dataclasses
import os
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt
import pyqtgraph as pg

from .. import __version__
from ..engine.config import ATMOSPHERE_PRESETS, RunConfig, TargetConfig
from ..engine.metrics import SPEC
from ..engine.naming import run_label
from ..engine.report import write_report
from ..engine.simulation import Simulation, StepResult
from .theme import STYLESHEET, C

SCENARIO_DIR = Path("configs/scenarios")

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
    "max_accel_deg_s2": "Max accel (deg/s2)", "command_latency_frames": "Command latency (frames)",
    "window_only": "Hard mode: see window only", "size_px": "Size (px)", "intensity": "Peak intensity",
    "speed_px_s": "Speed (px/s)", "radius_px": "Radius (px)", "period_s": "Period (s)", "heading_deg": "Heading (deg)",
    "blink_hz": "Blink (Hz, 0 = steady)", "waypoints": "Waypoints (x,y; x,y)", "salt_pepper_frac": "Salt and pepper fraction", "gaussian_sigma": "Gaussian sigma",
    "poisson": "Poisson shot noise", "jitter_px": "Camera jitter (px/frame)", "atmosphere": "Atmosphere preset",
    "contrast": "Contrast multiplier", "brightness": "Brightness offset", "turbulence": "Turbulence (0-1)",
    "blur_sigma": "PSF blur sigma (px)", "platform_motion": "Platform motion", "platform_px_frame": "Platform speed (px/frame)",
    "platform_period_s": "Platform period (s)", "background_level": "Sky level (0-255)", "star_density": "Star density",
    "colour": "Colour camera", "detector": "Detector", "ego_motion": "Use picture-shift estimate", "threshold_k": "Threshold k (sigma)",
    "kp": "Kp", "kd": "Kd", "ki": "Ki", "feedforward": "Feedforward weight", "deadband_px": "Deadband (px)",
    "capture_radius_px": "Capture radius (px)", "estimator_lag_s": "Estimator lag (s)", "acquire_conf_min": "Min confidence to acquire",
    "faint_snr_min": "Faint path: min chain SNR", "faint_threshold_k": "Faint path: threshold (sigma)",
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
    "motion": "PS row 12. Straight line, circular, figure of 8 and random are mandatory; spiral and sinusoidal optional.",
    "speed_px_s": "Along-track speed for line, random and sinusoidal paths.", "radius_px": "Radius for circular, figure of 8, spiral; half-amplitude for sinusoidal.",
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
    "estimator_lag_s": "Assumed delay of the velocity estimate, compensated with acceleration.",
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


# ----------------------------------------------------------------------------- form helpers
class DataclassForm(QtWidgets.QWidget):
    """Builds editable widgets for every field of a dataclass instance."""
    changed = QtCore.pyqtSignal()

    def __init__(self, obj, parent=None):
        super().__init__(parent)
        self.obj = obj
        self.widgets: dict[str, QtWidgets.QWidget] = {}
        lay = QtWidgets.QFormLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setVerticalSpacing(4)
        lay.setLabelAlignment(Qt.AlignmentFlag.AlignLeft)
        for f in dataclasses.fields(obj):
            if f.name in HIDDEN:
                continue
            v = getattr(obj, f.name)
            w = self._widget(f.name, v)
            if w is None:
                continue
            self.widgets[f.name] = w
            lab = QtWidgets.QLabel(LABELS.get(f.name, f.name.replace("_", " ").capitalize()))
            lab.setProperty("class", "fieldlabel")
            tip = TIPS.get(f.name)
            if tip:
                lab.setToolTip(tip); w.setToolTip(tip)
            lay.addRow(lab, w)

    def _widget(self, name, v):
        lo, hi = RANGES.get(name, (-1e9, 1e9))
        if isinstance(v, bool):
            w = QtWidgets.QCheckBox(); w.setChecked(v); w.toggled.connect(self.changed)
        elif isinstance(v, int):
            w = QtWidgets.QSpinBox(); w.setRange(int(lo), int(hi)); w.setValue(v); w.valueChanged.connect(self.changed)
        elif isinstance(v, float):
            w = QtWidgets.QDoubleSpinBox(); w.setRange(lo, hi); w.setDecimals(3 if hi - lo <= 2 else 2)
            w.setSingleStep(0.01 if hi - lo <= 2 else 1.0); w.setValue(v); w.valueChanged.connect(self.changed)
        elif isinstance(v, str) and name in CHOICES:
            w = QtWidgets.QComboBox(); w.addItems(CHOICES[name])
            if v in CHOICES[name]:
                w.setCurrentText(v)
            w.currentTextChanged.connect(self.changed)
        elif isinstance(v, str):
            w = QtWidgets.QLineEdit(v); w.textChanged.connect(self.changed)
        else:
            return None
        return w

    def read(self):
        for name, w in self.widgets.items():
            if isinstance(w, QtWidgets.QCheckBox):
                setattr(self.obj, name, w.isChecked())
            elif isinstance(w, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
                setattr(self.obj, name, w.value())
            elif isinstance(w, QtWidgets.QComboBox):
                setattr(self.obj, name, w.currentText())
            elif isinstance(w, QtWidgets.QLineEdit):
                setattr(self.obj, name, w.text())
        return self.obj

    def write(self, obj):
        self.obj = obj
        for name, w in self.widgets.items():
            v = getattr(obj, name)
            w.blockSignals(True)
            if isinstance(w, QtWidgets.QCheckBox):
                w.setChecked(bool(v))
            elif isinstance(w, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
                w.setValue(v)
            elif isinstance(w, QtWidgets.QComboBox):
                w.setCurrentText(str(v))
            elif isinstance(w, QtWidgets.QLineEdit):
                w.setText(str(v))
            w.blockSignals(False)


def section(title: str, inner: QtWidgets.QWidget, hint: str = "") -> QtWidgets.QWidget:
    box = QtWidgets.QWidget()
    lay = QtWidgets.QVBoxLayout(box)
    lay.setContentsMargins(0, 6, 0, 10)
    lab = QtWidgets.QLabel(title.upper())
    lab.setProperty("class", "section")
    lay.addWidget(lab)
    if hint:
        h = QtWidgets.QLabel(hint); h.setProperty("class", "hint"); h.setWordWrap(True); lay.addWidget(h)
    lay.addWidget(inner)
    return box


# ----------------------------------------------------------------------------- KPI tiles
class Tile(QtWidgets.QFrame):
    def __init__(self, title: str, unit: str = ""):
        super().__init__()
        self.setProperty("class", "tile")
        lay = QtWidgets.QVBoxLayout(self); lay.setContentsMargins(12, 8, 12, 8); lay.setSpacing(2)
        self.t = QtWidgets.QLabel(title.upper()); self.t.setProperty("class", "tiletitle")
        self.v = QtWidgets.QLabel("-"); self.v.setProperty("class", "tilevalue")
        self.u = QtWidgets.QLabel(unit); self.u.setProperty("class", "tileunit")
        lay.addWidget(self.t); lay.addWidget(self.v); lay.addWidget(self.u)

    def set(self, text: str, state: str | None = None, unit: str | None = None):
        self.v.setText(text)
        col = {"pass": C["good"], "fail": C["signal"], "warn": C["signal"], None: C["ink"]}.get(state, C["ink"])
        self.v.setStyleSheet(f"color: {col}; font-size: 20px; font-weight: 600;")
        if unit is not None:
            self.u.setText(unit)


# ----------------------------------------------------------------------------- worker
class Worker(QtCore.QObject):
    stepped = QtCore.pyqtSignal(object)
    finished = QtCore.pyqtSignal(object)
    failed = QtCore.pyqtSignal(str)

    def __init__(self, sim: Simulation, speed: float):
        super().__init__()
        self.sim = sim
        self.speed = speed           # 0 = as fast as possible
        self._pause = False
        self._stop = False
        self._step_once = False

    @QtCore.pyqtSlot()
    def run(self):
        try:
            next_t = time.perf_counter()
            for res in self.sim.steps():
                while self._pause and not self._stop and not self._step_once:
                    time.sleep(0.01)
                self._step_once = False
                if self._stop:
                    break
                self.stepped.emit(res)
                if self.speed > 0:
                    next_t += self.sim.dt / self.speed
                    lag = next_t - time.perf_counter()
                    if lag > 0:
                        time.sleep(lag)
                    else:
                        next_t = time.perf_counter()
            if self._stop:
                self.sim.finish()
            self.finished.emit(self.sim)
        except Exception:
            import traceback
            self.failed.emit(traceback.format_exc())


# ----------------------------------------------------------------------------- image views
def to_qimage(img: np.ndarray) -> QtGui.QImage:
    if img.ndim == 3:
        rgb = np.ascontiguousarray(img[:, :, ::-1])          # OpenCV BGR to RGB
        h, w, _ = rgb.shape
        return QtGui.QImage(rgb.data, w, h, 3 * w, QtGui.QImage.Format.Format_RGB888).copy()
    h, w = img.shape
    g = np.ascontiguousarray(img)
    return QtGui.QImage(g.data, w, h, w, QtGui.QImage.Format.Format_Grayscale8).copy()


def _pen(col, w=1.0, style=Qt.PenStyle.SolidLine):
    p = QtGui.QPen(QtGui.QColor(col)); p.setWidthF(w); p.setStyle(style); return p


class SceneView(QtWidgets.QLabel):
    """The whole screen, downscaled, with the camera window, truth, estimate and trails."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(360, 360)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setProperty("class", "view")
        self.trail_true: list[tuple[float, float]] = []
        self.trail_win: list[tuple[float, float]] = []

    def reset(self):
        self.trail_true.clear(); self.trail_win.clear()

    def update_view(self, res: StepResult, ifov_deg: float):
        img = res.observed
        h, w = img.shape[:2]
        side = min(self.width(), self.height()) - 8
        s = side / max(h, w)
        small = to_qimage(img).scaled(int(w * s), int(h * s), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation)
        pm = QtGui.QPixmap.fromImage(small)
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        # degree grid every 2 degrees
        step = 2.0 / ifov_deg * s
        p.setPen(_pen(C["line"], 0.6))
        k = 0
        while k * step < pm.width():
            p.drawLine(int(k * step), 0, int(k * step), pm.height()); k += 1
        k = 0
        while k * step < pm.height():
            p.drawLine(0, int(k * step), pm.width(), int(k * step)); k += 1
        x0, y0, ww, wh = res.window
        cx, cy = (x0 + ww / 2) * s, (y0 + wh / 2) * s
        for trail, col in ((self.trail_true[-500:], C["signal"]), (self.trail_win[-500:], C["accent"])):
            if len(trail) > 1:
                p.setPen(_pen(col, 0.9)); p.setOpacity(0.5)
                path = QtGui.QPainterPath(QtCore.QPointF(*trail[0]))
                for pt in trail[1:]:
                    path.lineTo(QtCore.QPointF(*pt))
                p.drawPath(path); p.setOpacity(1.0)
        p.setPen(_pen(C["accent"], 2)); p.drawRect(int(x0 * s), int(y0 * s), int(ww * s), int(wh * s))
        p.drawLine(int(cx - 6), int(cy), int(cx + 6), int(cy)); p.drawLine(int(cx), int(cy - 6), int(cx), int(cy + 6))
        self.trail_win.append((cx, cy))
        if res.frame.truth is not None and res.frame.truth.beacons:
            tx, ty = res.frame.truth.beacons[0]
            self.trail_true.append((tx * s, ty * s))
            p.setPen(_pen(C["signal"], 1.2)); p.drawEllipse(QtCore.QPointF(tx * s, ty * s), 7, 7)
            p.setPen(_pen(C["muted"], 1.0))
            for (bx, by) in res.frame.truth.beacons[1:]:
                p.drawEllipse(QtCore.QPointF(bx * s, by * s), 5, 5)
        if res.track.estimate is not None:
            ex, ey = res.track.estimate
            p.setPen(_pen(C["good"], 1.2))
            p.drawLine(int(ex * s - 8), int(ey * s), int(ex * s + 8), int(ey * s)); p.drawLine(int(ex * s), int(ey * s - 8), int(ex * s), int(ey * s + 8))
        p.fillRect(0, 0, pm.width(), 20, QtGui.QColor(0, 0, 0, 150))
        p.setPen(QtGui.QColor(C["muted"])); p.setFont(QtGui.QFont("Menlo", 9))
        p.drawText(6, 14, f"SCREEN {w} x {h} px   {w * ifov_deg:.1f} x {h * ifov_deg:.1f} deg   frame {res.frame.idx}   t {res.frame.t:6.2f} s   grid 2 deg")
        y = pm.height() - 7
        p.fillRect(0, pm.height() - 20, pm.width(), 20, QtGui.QColor(0, 0, 0, 150))
        for col, txt, dx in ((C["accent"], "camera window", 6), (C["signal"], "true beacon", 120), (C["good"], "tracker estimate", 215), (C["muted"], "other targets", 340)):
            p.setPen(QtGui.QColor(col)); p.drawText(dx, y, txt)
        p.end()
        self.setPixmap(pm)


class CameraView(QtWidgets.QLabel):
    """What the camera window sees, with the HUD."""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(320, 240)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setProperty("class", "view")
        self.trail: list[tuple[float, float]] = []

    def reset(self):
        self.trail.clear()

    def update_view(self, res: StepResult, ifov_deg: float, capture_px: float):
        img = res.observed
        H, W = img.shape[:2]
        x0, y0, w, h = res.window
        xa, ya = max(x0, 0), max(y0, 0)
        xb, yb = min(x0 + w, W), min(y0 + h, H)
        crop = np.zeros((h, w) if img.ndim == 2 else (h, w, 3), np.uint8)
        if xb > xa and yb > ya:
            crop[ya - y0:yb - y0, xa - x0:xb - x0] = img[ya:yb, xa:xb]
        # display-only contrast stretch so faint scenes stay visible
        lo, hi = np.percentile(crop[::4, ::4], (1, 99.8))
        if hi - lo > 8:
            crop = np.clip((crop.astype(np.float32) - lo) * (255.0 / (hi - lo)), 0, 255).astype(np.uint8)
        qi = to_qimage(crop)
        avail_w, avail_h = self.width() - 8, self.height() - 8
        s = min(avail_w / w, avail_h / h, 1.6)
        pm = QtGui.QPixmap.fromImage(qi.scaled(int(w * s), int(h * s), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation))
        p = QtGui.QPainter(pm)
        p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        cx, cy = w * s / 2, h * s / 2
        tr = res.track
        locked = bool(res.record.locked)
        p.setPen(_pen(C["good"] if locked else C["signal"], 1.4, Qt.PenStyle.DashLine))
        p.drawEllipse(QtCore.QPointF(cx, cy), capture_px * s, capture_px * s)
        p.setPen(_pen(C["accent"], 1.2))
        p.drawLine(int(cx - 20), int(cy), int(cx - 6), int(cy)); p.drawLine(int(cx + 6), int(cy), int(cx + 20), int(cy))
        p.drawLine(int(cx), int(cy - 20), int(cx), int(cy - 6)); p.drawLine(int(cx), int(cy + 6), int(cx), int(cy + 20))
        if tr.estimate is not None:
            ex, ey = (tr.estimate[0] - x0) * s, (tr.estimate[1] - y0) * s
            self.trail.append((ex, ey))
            recent = self.trail[-120:]
            if len(recent) > 1:
                p.setPen(_pen(C["good"], 0.8)); p.setOpacity(0.45)
                path = QtGui.QPainterPath(QtCore.QPointF(*recent[0]))
                for pt in recent[1:]:
                    path.lineTo(QtCore.QPointF(*pt))
                p.drawPath(path); p.setOpacity(1.0)
            p.setPen(_pen(C["good"] if locked else C["signal"], 1.2))
            p.drawLine(QtCore.QPointF(cx, cy), QtCore.QPointF(ex, ey))
        if tr.detection is not None:
            dx, dy = (tr.detection[0] - x0) * s, (tr.detection[1] - y0) * s
            p.setPen(_pen(C["good"], 2)); p.drawRect(int(dx - 12), int(dy - 12), 24, 24)
        if tr.prediction is not None:
            px, py = (tr.prediction[0] - x0) * s, (tr.prediction[1] - y0) * s
            p.setPen(_pen(C["signal"], 1)); p.drawEllipse(QtCore.QPointF(px, py), 5, 5)
            r = max(tr.uncertainty_px * 2 * s, 6)
            p.setOpacity(0.5); p.drawEllipse(QtCore.QPointF(px, py), r, r); p.setOpacity(1.0)
        bar = s / ifov_deg
        if bar < pm.width() * 0.6:
            bx = pm.width() - 16 - bar; by = pm.height() - 30
            p.setPen(_pen(C["ink"], 1.5)); p.drawLine(int(bx), by, int(bx + bar), by)
            p.setFont(QtGui.QFont("Menlo", 8)); p.drawText(int(bx), by - 4, "1 deg")
        col = {"TRACK": C["good"], "COAST": C["signal"], "REACQUIRE": C["signal"]}.get(tr.mode.value, C["accent"])
        p.fillRect(0, 0, pm.width(), 22, QtGui.QColor(0, 0, 0, 160))
        p.setPen(QtGui.QColor(col)); p.setFont(QtGui.QFont("Menlo", 10, QtGui.QFont.Weight.Bold))
        p.drawText(8, 16, f"{tr.mode.value}{'  LOCKED' if locked else ''}")
        p.setPen(QtGui.QColor(C["ink"])); p.setFont(QtGui.QFont("Menlo", 9))
        err = res.record.tracking_err_px
        err_s = f"err {err:6.2f} px  {err * ifov_deg * 3600:6.0f} arcsec" if np.isfinite(err) else "err n/a (video: no truth)"
        p.drawText(150, 16, f"{err_s}   conf {tr.confidence:.2f}   {tr.tier}")
        p.fillRect(0, pm.height() - 20, pm.width(), 20, QtGui.QColor(0, 0, 0, 160))
        p.setPen(QtGui.QColor(C["muted"]))
        sat = "  SATURATED" if (res.cmd.saturated_pan or res.cmd.saturated_tilt) else ""
        p.drawText(8, pm.height() - 6, f"pan {res.record.cam_pan_deg:+6.2f}  tilt {res.record.cam_tilt_deg:+6.2f} deg   "
                   f"cmd {res.cmd.pan_rate:+5.2f} {res.cmd.tilt_rate:+5.2f} deg/s{sat}   {res.record.proc_ms:5.1f} ms")
        p.end()
        self.setPixmap(pm)


# ----------------------------------------------------------------------------- main window
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"FSOC Tracker  v{__version__}  SIH26169")
        self.resize(1600, 960)
        self.cfg = RunConfig()
        self.thread: QtCore.QThread | None = None
        self.worker: Worker | None = None
        self.sim: Simulation | None = None
        self.video_path: str | None = None
        self.video_info: dict | None = None
        self.out_dir: Path | None = None
        self.headless = False
        self._last_draw = 0.0
        self._build()
        self.apply_cfg(self.cfg)
        self._shortcuts()

    # ------------------------------------------------------------- layout
    def _build(self):
        tb = self.addToolBar("Run"); tb.setMovable(False)
        tb.addWidget(QtWidgets.QLabel("  Scenario "))
        self.cmb_scn = QtWidgets.QComboBox(); self.cmb_scn.setMinimumWidth(190)
        self._fill_scenarios()
        self.cmb_scn.currentIndexChanged.connect(self._scenario_picked)
        self.cmb_scn.setToolTip("Ready-made test cases from configs/scenarios. Pick one, then Start. Edit any value on the left before starting.")
        tb.addWidget(self.cmb_scn)
        tb.addSeparator()
        self.act_start = tb.addAction("Start", self.start); self.act_start.setToolTip("Space")
        self.act_pause = tb.addAction("Pause", self.pause); self.act_pause.setToolTip("Space while running")
        self.act_step = tb.addAction("Step", self.step_once); self.act_step.setToolTip("N: advance one frame while paused")
        self.act_stop = tb.addAction("Stop", self.stop); self.act_stop.setToolTip("Esc")
        tb.addWidget(QtWidgets.QLabel("  Speed "))
        self.cmb_speed = QtWidgets.QComboBox()
        for name, _ in SPEEDS:
            self.cmb_speed.addItem(name)
        self.cmb_speed.setCurrentIndex(2)
        self.cmb_speed.setToolTip("Playback pacing. Max speed shows the true processing rate.")
        tb.addWidget(self.cmb_speed)
        tb.addSeparator()
        tb.addAction("Open video (Benchmark 2)", self.open_video).setToolTip("Ctrl+O: use an .mp4 as the scene; the simulator is bypassed")
        self.act_clear_video = tb.addAction("Use simulator", self.clear_video)
        tb.addSeparator()
        tb.addAction("Save scenario", self.save_scenario).setToolTip("Ctrl+S")
        tb.addAction("Screenshot", self.screenshot).setToolTip("Ctrl+P: save a PNG of this window into results/")
        tb.addAction("Results folder", self.open_results)
        tb.addAction("User manual", self.open_manual).setToolTip("Opens the user manual (PDF if present, otherwise the Markdown)")
        tb.addAction("Help", self.help)

        central = QtWidgets.QWidget(); self.setCentralWidget(central)
        root = QtWidgets.QHBoxLayout(central); root.setContentsMargins(8, 8, 8, 8); root.setSpacing(8)

        self.forms = {
            "screen": DataclassForm(self.cfg.screen), "camera": DataclassForm(self.cfg.camera),
            "target": DataclassForm(self.cfg.targets[0]), "disturbance": DataclassForm(self.cfg.disturbance),
            "tracker": DataclassForm(self.cfg.tracker),
        }
        self.forms["disturbance"].widgets["atmosphere"].currentTextChanged.connect(self._preset_changed)
        run_w = QtWidgets.QWidget(); rl = QtWidgets.QFormLayout(run_w); rl.setContentsMargins(0, 0, 0, 0); rl.setVerticalSpacing(4)
        self.ed_name = QtWidgets.QLineEdit(self.cfg.name)
        self.sp_seed = QtWidgets.QSpinBox(); self.sp_seed.setRange(0, 10 ** 6); self.sp_seed.setValue(self.cfg.seed)
        self.sp_seed.setToolTip("Same seed and settings give exactly the same run.")
        self.sp_dur = QtWidgets.QDoubleSpinBox(); self.sp_dur.setRange(1, 3600); self.sp_dur.setValue(self.cfg.duration_s)
        self.sp_extra = QtWidgets.QSpinBox(); self.sp_extra.setRange(0, 8); self.sp_extra.setValue(len(self.cfg.targets) - 1)
        self.sp_extra.setToolTip("Decoy beacons with random paths. The tracker must keep following the designated one.")
        self.chk_random = QtWidgets.QCheckBox("New random seed and heading every run"); self.chk_random.setChecked(True)
        self.chk_random.setToolTip("On: each Start draws a new seed (start position, noise, decoys) and a new heading for line paths, so every run is different. "
                                   "Off: the seed shown is used, so a run can be repeated exactly. The seed used is always shown in the status bar and saved with the results.")
        for lab, w in (("Name", self.ed_name), ("Seed", self.sp_seed), ("", self.chk_random), ("Duration (s)", self.sp_dur), ("Extra targets", self.sp_extra)):
            l = QtWidgets.QLabel(lab); l.setProperty("class", "fieldlabel"); rl.addRow(l, w)
        panel = QtWidgets.QWidget(); pl = QtWidgets.QVBoxLayout(panel); pl.setContentsMargins(0, 0, 8, 0)
        pl.addWidget(section("Run", run_w))
        pl.addWidget(section("Screen (PS rows 1-2)", self.forms["screen"], "The whole scene the tracker observes."))
        pl.addWidget(section("Camera (PS rows 3-6, 13-15)", self.forms["camera"], "The window the terminal points at, and how fast it can turn."))
        pl.addWidget(section("Designated target (PS rows 7-12)", self.forms["target"], "The beacon to follow."))
        pl.addWidget(section("Disturbances (PS rows 21-25)", self.forms["disturbance"], "Everything that makes the picture worse. All off = clear sky."))
        pl.addWidget(section("Tracker", self.forms["tracker"], "How the software finds and follows. Defaults are tuned; change with care."))
        pl.addStretch(1)
        scroll = QtWidgets.QScrollArea(); scroll.setWidget(panel); scroll.setWidgetResizable(True)
        scroll.setFixedWidth(340); scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        root.addWidget(scroll)

        centre = QtWidgets.QVBoxLayout(); centre.setSpacing(8)
        tiles = QtWidgets.QHBoxLayout(); tiles.setSpacing(8)
        self.tiles = {
            "state": Tile("State"), "acq": Tile("Acquisition", "spec: 2 s or less"), "terr": Tile("Tracking error, mean", "spec: 10 px or less"),
            "cerr": Tile("Centroiding error, mean", "measured to true"), "lock": Tile("Lock retention", "spec: loss under 5%"),
            "fps": Tile("Processing", "spec: 20 FPS or more"),
        }
        for t in self.tiles.values():
            tiles.addWidget(t)
        centre.addLayout(tiles)
        views = QtWidgets.QHBoxLayout(); views.setSpacing(8)
        self.scene_view = SceneView(); self.cam_view = CameraView()
        views.addWidget(self.scene_view, 1); views.addWidget(self.cam_view, 1)
        centre.addLayout(views, 3)
        pg.setConfigOptions(antialias=False, background=C["surface"], foreground=C["muted"])
        self.plots = QtWidgets.QWidget(); gl = QtWidgets.QGridLayout(self.plots); gl.setContentsMargins(0, 0, 0, 0); gl.setSpacing(6)
        self.p_err = self._plot("Errors (px)"); self.p_cmd = self._plot("Gimbal command (deg/s)")
        self.p_fps = self._plot("Processing time per frame (ms)"); self.p_mode = self._plot("Tracker state")
        gl.addWidget(self.p_err, 0, 0); gl.addWidget(self.p_cmd, 0, 1); gl.addWidget(self.p_fps, 1, 0); gl.addWidget(self.p_mode, 1, 1)
        self.p_err.addLegend(offset=(-10, 5), labelTextSize="8pt")
        self.c_terr = self.p_err.plot(pen=pg.mkPen(C["accent"], width=1.2), name="tracking: window centre to beacon")
        self.c_cerr = self.p_err.plot(pen=pg.mkPen(C["signal"], width=1.2), name="centroiding: measured to true")
        self.p_err.addLine(y=10, pen=pg.mkPen(C["line"], style=Qt.PenStyle.DashLine))
        self.p_cmd.addLegend(offset=(-10, 5), labelTextSize="8pt")
        self.c_pan = self.p_cmd.plot(pen=pg.mkPen(C["accent"], width=1.2), name="pan")
        self.c_tilt = self.p_cmd.plot(pen=pg.mkPen(C["signal"], width=1.2), name="tilt")
        self.lim_lines = [self.p_cmd.addLine(y=v, pen=pg.mkPen(C["line"], style=Qt.PenStyle.DashLine)) for v in (5, -5)]
        self.c_proc = self.p_fps.plot(pen=pg.mkPen(C["ink"], width=1.2))
        self.p_fps.addLine(y=50, pen=pg.mkPen(C["signal"], style=Qt.PenStyle.DashLine))
        self.c_mode = self.p_mode.plot(pen=pg.mkPen(C["accent"], width=1.4), stepMode="right")
        self.p_mode.getAxis("left").setTicks([[(i, m) for i, m in enumerate(MODES)]])
        self.p_mode.setYRange(-0.3, 4.3)
        centre.addWidget(self.plots, 2)
        root.addLayout(centre, 1)

        self.tele = QtWidgets.QPlainTextEdit(); self.tele.setReadOnly(True); self.tele.setFixedWidth(300)
        self.tele.setProperty("class", "tele")
        self.tele.setPlainText(self._welcome())
        root.addWidget(self.tele)

        self.status = self.statusBar()
        self.lbl_status = QtWidgets.QLabel("Ready. Pick a scenario and press Start, or open a video for Benchmark 2.")
        self.status.addWidget(self.lbl_status, 1)
        self.progress = QtWidgets.QProgressBar(); self.progress.setFixedWidth(220); self.progress.setTextVisible(False)
        self.status.addPermanentWidget(self.progress)
        self._set_running(False)
        self._buf_reset()

    def _plot(self, title):
        pw = pg.PlotWidget(title=title)
        pw.showGrid(x=True, y=True, alpha=0.2)
        pw.getPlotItem().titleLabel.setAttr("size", "9pt")
        pw.getPlotItem().titleLabel.setAttr("color", C["muted"])
        pw.setLabel("bottom", "time (s)")
        return pw

    def _shortcuts(self):
        QtGui.QShortcut(QtGui.QKeySequence("Space"), self, activated=self._space)
        QtGui.QShortcut(QtGui.QKeySequence("N"), self, activated=self.step_once)
        QtGui.QShortcut(QtGui.QKeySequence("Escape"), self, activated=self.stop)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+S"), self, activated=self.save_scenario)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+P"), self, activated=self.screenshot)
        QtGui.QShortcut(QtGui.QKeySequence("Ctrl+O"), self, activated=self.open_video)

    def _space(self):
        if self.thread is None:
            self.start()
        else:
            self.pause()

    def _welcome(self) -> str:
        return "\n".join([
            "HOW TO USE", "",
            "1. Pick a scenario in the toolbar,", "   or set values on the left.",
            "2. Press Start (or Space).", "3. Watch the tiles above the views:",
            "   green = meets the spec,", "   amber = does not (yet).",
            "4. When the run ends a report", "   opens; results/ holds the CSV,",
            "   JSON, PDF and scenario file.", "",
            "BENCHMARK 2", "Open video, then Start. The video", "replaces the simulated scene.", "",
            "KEYS", "Space  start / pause", "N      step one frame", "Esc    stop",
            "Ctrl+S save scenario", "Ctrl+P screenshot", "Ctrl+O open video", "",
            "Hover any setting for its meaning", "and the problem statement row.",
        ])

    # ------------------------------------------------------------- scenarios
    def _fill_scenarios(self):
        self.cmb_scn.blockSignals(True)
        self.cmb_scn.clear()
        self.cmb_scn.addItem("Custom (edit the panel)", "")
        if SCENARIO_DIR.exists():
            for pth in sorted(SCENARIO_DIR.glob("*.yaml")):
                self.cmb_scn.addItem(pth.stem.replace("_", " "), str(pth))
        self.cmb_scn.blockSignals(False)

    def _scenario_picked(self, idx):
        path = self.cmb_scn.itemData(idx)
        if path:
            try:
                self.apply_cfg(RunConfig.load(path))
                self.lbl_status.setText(f"Loaded {path}. Press Start.")
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Load failed", str(e))

    # ------------------------------------------------------------- config
    def apply_cfg(self, cfg: RunConfig):
        self.cfg = cfg
        self.forms["screen"].write(cfg.screen); self.forms["camera"].write(cfg.camera)
        self.forms["target"].write(cfg.targets[0]); self.forms["disturbance"].write(cfg.disturbance)
        self.forms["tracker"].write(cfg.tracker)
        self.ed_name.setText(cfg.name); self.sp_seed.setValue(cfg.seed); self.sp_dur.setValue(cfg.duration_s)
        self.sp_extra.setValue(max(len(cfg.targets) - 1, 0))
        self.video_path = cfg.video
        self._video_label()

    def read_cfg(self) -> RunConfig:
        cfg = self.cfg
        cfg.screen = self.forms["screen"].read(); cfg.camera = self.forms["camera"].read()
        t0 = self.forms["target"].read(); cfg.disturbance = self.forms["disturbance"].read(); cfg.tracker = self.forms["tracker"].read()
        cfg.name = self.ed_name.text().strip() or "run"; cfg.duration_s = self.sp_dur.value()
        if self.chk_random.isChecked():
            cfg.seed = int(np.random.default_rng().integers(0, 10 ** 6))
            self.sp_seed.setValue(cfg.seed)
            if t0.motion in ("line", "sinusoidal"):
                t0.heading_deg = float(np.random.default_rng(cfg.seed).uniform(0, 360))
                self.forms["target"].write(t0)
        else:
            cfg.seed = self.sp_seed.value()
        extra = self.sp_extra.value()
        rng = np.random.default_rng(cfg.seed + 99)
        targets = [t0]
        motions = ["circular", "line", "figure8", "random", "sinusoidal"]
        for i in range(extra):
            if i + 1 < len(cfg.targets):
                targets.append(cfg.targets[i + 1])
            else:
                targets.append(TargetConfig(shape=["circle", "square", "gaussian"][i % 3], size_px=int(rng.integers(6, 16)),
                                            intensity=int(rng.integers(150, 235)), motion=motions[i % len(motions)],
                                            speed_px_s=float(rng.uniform(60, 180)), radius_px=float(rng.uniform(200, 450)),
                                            period_s=float(rng.uniform(8, 20)), heading_deg=float(rng.uniform(0, 360)), start="centre"))
        cfg.targets = targets
        cfg.video = self.video_path
        return cfg

    def _preset_changed(self, name):
        p = ATMOSPHERE_PRESETS.get(name)
        if not p:
            return
        f = self.forms["disturbance"]
        for k, v in p.items():
            w = f.widgets.get(k)
            if w is not None:
                w.blockSignals(True); w.setValue(v); w.blockSignals(False)

    def _video_label(self):
        if self.video_path:
            self.lbl_status.setText(f"Benchmark 2 input: {self.video_path}  (simulator bypassed). Press Start.")
        else:
            self.lbl_status.setText("Simulator input. Pick a scenario or set values, then press Start.")

    # ------------------------------------------------------------- actions
    def start(self):
        if self.thread is not None:
            return
        try:
            cfg = self.read_cfg()
            self.out_dir = Path(cfg.output_dir) / run_label(cfg)
            self.sim = Simulation(cfg, self.out_dir)
        except Exception as e:
            QtWidgets.QMessageBox.critical(self, "Cannot start", str(e)); return
        self._buf_reset(); self.scene_view.reset(); self.cam_view.reset()
        for t in self.tiles.values():
            t.set("-")
        for ln, v in zip(self.lim_lines, (cfg.camera.max_pan_rate_deg_s, -cfg.camera.max_pan_rate_deg_s)):
            ln.setValue(v)
        self.progress.setRange(0, getattr(self.sim.source, "n_frames", 0) or 0)
        speed = SPEEDS[self.cmb_speed.currentIndex()][1]
        self.thread = QtCore.QThread(); self.worker = Worker(self.sim, speed)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.stepped.connect(self.on_step, Qt.ConnectionType.QueuedConnection)
        self.worker.finished.connect(self.on_finished, Qt.ConnectionType.QueuedConnection)
        self.worker.failed.connect(self.on_failed, Qt.ConnectionType.QueuedConnection)
        self.thread.start()
        self._set_running(True)
        self.lbl_status.setText(f"Running '{cfg.name}' seed {cfg.seed}  ->  {self.out_dir}")

    def pause(self):
        if self.worker:
            self.worker._pause = not self.worker._pause
            self.act_pause.setText("Resume" if self.worker._pause else "Pause")

    def step_once(self):
        if self.worker:
            self.worker._pause = True; self.act_pause.setText("Resume"); self.worker._step_once = True

    def stop(self):
        if self.worker:
            self.worker._stop = True; self.worker._pause = False

    def _set_running(self, r: bool):
        self.act_start.setEnabled(not r); self.act_pause.setEnabled(r); self.act_step.setEnabled(r); self.act_stop.setEnabled(r)
        self.cmb_scn.setEnabled(not r); self.act_pause.setText("Pause")

    # ------------------------------------------------------------- data flow
    def _buf_reset(self):
        self.b_t, self.b_terr, self.b_cerr, self.b_pan, self.b_tilt, self.b_proc, self.b_mode, self.b_lock = ([] for _ in range(8))
        self._acq_t = None

    @QtCore.pyqtSlot(object)
    def on_step(self, res: StepResult):
        r = res.record
        self.b_t.append(r.t_sim); self.b_terr.append(r.tracking_err_px); self.b_cerr.append(r.centroid_err_px)
        self.b_pan.append(r.cmd_pan_rate); self.b_tilt.append(r.cmd_tilt_rate); self.b_proc.append(r.proc_ms)
        self.b_mode.append(MODES.index(r.mode)); self.b_lock.append(r.locked)
        if self._acq_t is None and r.locked:
            self._acq_t = r.t_sim
        now = time.perf_counter()
        if now - self._last_draw < 1 / 30:
            return
        self._last_draw = now
        ifov = self.sim.cfg.camera.ifov_deg
        self.scene_view.update_view(res, ifov)
        self.cam_view.update_view(res, ifov, self.sim.cfg.tracker.capture_radius_px)
        n = 600
        t = np.array(self.b_t[-n:])
        self.c_terr.setData(t, np.array(self.b_terr[-n:])); self.c_cerr.setData(t, np.array(self.b_cerr[-n:]))
        self.c_pan.setData(t, np.array(self.b_pan[-n:])); self.c_tilt.setData(t, np.array(self.b_tilt[-n:]))
        self.c_proc.setData(t, np.array(self.b_proc[-n:])); self.c_mode.setData(t, np.array(self.b_mode[-n:]))
        self.progress.setValue(r.frame)
        self._update_tiles(r)
        tr = res.track
        lines = [
            f"frame      {r.frame}", f"t          {r.t_sim:8.2f} s", f"state      {r.mode}", f"locked     {'yes' if r.locked else 'no'}",
            f"detector   {r.tier}", f"candidates {r.n_candidates}", f"confidence {r.confidence:8.2f}", f"snr        {r.snr:8.1f}",
            f"psf sigma  {r.sigma:8.2f} px", "",
            f"pan        {r.cam_pan_deg:+8.3f} deg", f"tilt       {r.cam_tilt_deg:+8.3f} deg",
            f"cmd pan    {r.cmd_pan_rate:+8.3f} deg/s", f"cmd tilt   {r.cmd_tilt_rate:+8.3f} deg/s",
            f"saturated  {'pan ' if r.sat_pan else ''}{'tilt' if r.sat_tilt else ''}{'no' if not (r.sat_pan or r.sat_tilt) else ''}", "",
            f"detection  {r.det_x:8.2f} {r.det_y:8.2f}", f"estimate   {r.est_x:8.2f} {r.est_y:8.2f}",
            f"velocity   {r.vel_x:+8.1f} {r.vel_y:+8.1f} px/s", f"uncert.    {r.uncertainty_px:8.2f} px",
            f"models     cv {r.p_cv:.2f} ca {r.p_ca:.2f} ct {r.p_ct:.2f}", f"ego shift  {r.ego_dx:+6.2f} {r.ego_dy:+6.2f} px", "",
            f"truth      {r.true_x:8.2f} {r.true_y:8.2f}", f"in window  {'yes' if r.in_window else 'no'}",
            f"track err  {r.tracking_err_px:8.2f} px", f"centroid   {r.centroid_err_px:8.3f} px", "",
            f"proc       {r.proc_ms:8.2f} ms", f"fps inst   {r.fps_inst:8.1f}",
        ]
        self.tele.setPlainText("\n".join(lines))

    def _update_tiles(self, r):
        T = self.tiles
        state_col = "pass" if r.mode == "TRACK" and r.locked else ("warn" if r.mode in ("COAST", "REACQUIRE") else None)
        T["state"].set(r.mode + (" locked" if r.locked else ""), state_col)
        if self._acq_t is not None:
            T["acq"].set(f"{self._acq_t:.2f} s", "pass" if self._acq_t <= SPEC["acquisition_time_s"][1] else "fail")
            after = [(e, l) for tt, e, l in zip(self.b_t, self.b_terr, self.b_lock) if tt >= self._acq_t]
            te = np.array([e for e, _ in after]); te = te[np.isfinite(te)]
            if len(te):
                m = float(te.mean()); T["terr"].set(f"{m:.1f} px", "pass" if m <= 10 else "fail")
            else:
                T["terr"].set("n/a", None, "no truth (video)")
            lk = 100 * np.mean([l for _, l in after]) if after else 0.0
            T["lock"].set(f"{lk:.1f} %", "pass" if 100 - lk < 5 else "fail")
        else:
            T["acq"].set("searching", "warn")
        ce = np.array(self.b_cerr); ce = ce[np.isfinite(ce)]
        if len(ce):
            T["cerr"].set(f"{ce.mean():.3f} px", "pass" if ce.mean() < 2 else "warn")
        else:
            T["cerr"].set("n/a", None, "no truth (video)")
        fps = 1000.0 / max(np.mean(self.b_proc[-60:]), 1e-3)
        T["fps"].set(f"{fps:.0f} FPS", "pass" if fps >= 20 else "fail")

    @QtCore.pyqtSlot(object)
    def on_finished(self, sim: Simulation):
        self._teardown()
        try:
            report = write_report(sim.cfg, sim.telemetry.records, sim.summary, sim.files["report"])
        except Exception as e:
            report = None
            QtWidgets.QMessageBox.warning(self, "Report", f"Report generation failed:\n{e}")
        v = sim.summary.values if sim.summary else {}
        p = sim.summary.passed if sim.summary else {}
        def f(k, fmt="{:.2f}"):
            x = v.get(k)
            return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else fmt.format(x)
        def pf(k):
            return {True: "PASS", False: "FAIL", None: "n/a"}[p.get(k)]
        msg = (f"Frames {v.get('frames')}    duration {f('duration_s')} s\n"
               f"FPS mean {f('fps_mean', '{:.1f}')}  ({pf('fps_mean')})\n"
               f"Acquisition {f('acquisition_time_s')} s  ({pf('acquisition_time_s')})\n"
               f"Tracking error mean {f('tracking_err_mean_px')} px, max {f('tracking_err_max_px')} px  ({pf('tracking_err_mean_px')})\n"
               f"  with vibration removed: {f('tracking_err_stab_mean_px')} px\n"
               f"Centroiding error mean {f('centroid_err_mean_px', '{:.3f}')} px, RMSE {f('centroid_err_rmse_px', '{:.3f}')} px\n"
               f"Lock retention {f('lock_retention_pct', '{:.1f}')} %   target loss {f('target_loss_pct', '{:.1f}')} %  ({pf('target_loss_pct')})\n"
               f"Re-acquisitions {v.get('reacq_count', 0)}, max {f('reacq_time_max_s')} s  ({pf('reacq_time_max_s')})\n"
               f"Processing {f('proc_ms_mean')} ms mean, {f('proc_ms_p99')} ms p99\n\n"
               f"Log: {sim.files['frames']}\nReport: {report}")
        sat = v.get("slew_saturation_pct", 0.0)
        if sat > 20:
            msg += (f"\n\nNote: the gimbal was at its rate limit in {sat:.0f}% of frames, so the target moved faster than the camera can turn. "
                    f"Raise Max pan / Max tilt (the PS allows 5 to 10 deg/s) or widen the FOV and run again.")
        self.lbl_status.setText(f"Finished. Report written to {self.out_dir}")
        self.last_summary_text = msg
        if self.headless:
            return
        box = QtWidgets.QMessageBox(self); box.setWindowTitle("Run complete"); box.setText(msg)
        box.setFont(QtGui.QFont("Menlo", 10))
        if report:
            b = box.addButton("Open report", QtWidgets.QMessageBox.ButtonRole.ActionRole)
            b.clicked.connect(lambda: _open_path(report))
        b2 = box.addButton("Open folder", QtWidgets.QMessageBox.ButtonRole.ActionRole)
        b2.clicked.connect(lambda: _open_path(self.out_dir))
        box.addButton(QtWidgets.QMessageBox.StandardButton.Ok)
        box.exec()

    @QtCore.pyqtSlot(str)
    def on_failed(self, tb: str):
        self._teardown()
        QtWidgets.QMessageBox.critical(self, "Run failed", tb)

    def _teardown(self):
        if self.thread:
            self.thread.quit(); self.thread.wait(2000)
        self.thread = None; self.worker = None
        self._set_running(False)
        self.progress.setValue(self.progress.maximum())

    # ------------------------------------------------------------- files
    def save_scenario(self):
        p, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save scenario", str(SCENARIO_DIR / "custom.yaml"), "YAML (*.yaml)")
        if p:
            self.read_cfg().save(p); self.lbl_status.setText(f"Saved {p}"); self._fill_scenarios()

    def open_video(self):
        p, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open video for Benchmark 2", "", "Video (*.mp4 *.avi *.mov *.mkv)")
        if p:
            self.video_path = p; self.ed_name.setText(Path(p).stem)
            self._preview_video(p)
            self._video_label()

    def _preview_video(self, path: str):
        """Probe the file, calibrate the settings to it, and show the first frame."""
        import cv2
        from ..engine.sources import probe_video
        try:
            info = probe_video(path)
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Video", f"Could not read this file:\n{e}"); return
        cap = cv2.VideoCapture(path); ok, bgr = cap.read(); cap.release()
        if not ok:
            QtWidgets.QMessageBox.warning(self, "Video", "Could not read the first frame of this file."); return
        w, h, fps, n = info["width"], info["height"], info["fps"], info["frames"]
        self.video_info = {"w": w, "h": h, "fps": fps, "frames": n, "seconds": info["seconds"], "rotation": info["rotation_deg"],
                           "variable": info["variable_rate"], "fps_ts": info["fps_timestamps"]}
        # calibrate the panel: the scene is the video, the clock is its frame rate
        sc = self.forms["screen"].read(); sc.width, sc.height = w, h; self.forms["screen"].write(sc)
        cam = self.forms["camera"].read(); cam.update_rate_hz = float(fps); cam.width = min(cam.width, w); cam.height = min(cam.height, h); self.forms["camera"].write(cam)
        self._set_video_mode(True)
        gray = bgr if (sc.colour and bgr.ndim == 3) else (cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if bgr.ndim == 3 else bgr)
        side = min(self.scene_view.width(), self.scene_view.height()) - 8
        s = side / max(h, w)
        pm = QtGui.QPixmap.fromImage(to_qimage(gray).scaled(int(w * s), int(h * s), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation))
        pnt = QtGui.QPainter(pm)
        pnt.fillRect(0, 0, pm.width(), 22, QtGui.QColor(0, 0, 0, 170))
        pnt.setPen(QtGui.QColor(C["good"])); pnt.setFont(QtGui.QFont("Menlo", 10, QtGui.QFont.Weight.Bold))
        pnt.drawText(8, 16, "VIDEO LOADED")
        pnt.setPen(QtGui.QColor(C["ink"])); pnt.setFont(QtGui.QFont("Menlo", 9))
        rot = f"   rotated {self.video_info['rotation']:.0f} deg" if self.video_info["rotation"] else ""
        vfr = "   variable rate" if self.video_info["variable"] else ""
        pnt.drawText(130, 16, f"{w} x {h} px   {fps:.2f} fps{vfr}   {n} frames   {self.video_info['seconds']:.2f} s{rot}")
        # the camera window at its start position, for scale
        cw, ch = min(self.cfg.camera.width, w), min(self.cfg.camera.height, h)
        pnt.setPen(_pen(C["accent"], 2)); pnt.drawRect(int((w - cw) / 2 * s), int((h - ch) / 2 * s), int(cw * s), int(ch * s))
        pnt.end()
        self.scene_view.setPixmap(pm)
        self.cam_view.setPixmap(QtGui.QPixmap())
        self.cam_view.setText("Press Start to run the tracker on this video")
        for t in self.tiles.values():
            t.set("-")
        self.tiles["state"].set("video ready", None)
        cam = self.forms["camera"].read()
        lines = ["VIDEO LOADED, SETTINGS CALIBRATED", "", f"file      {Path(path).name}", f"size      {w} x {h} px (as displayed)"]
        if self.video_info["rotation"]:
            lines.append(f"rotation  {self.video_info['rotation']:.0f} deg tag applied")
        lines += [f"rate      {fps:.2f} fps (container average)"]
        if self.video_info["variable"]:
            lines.append(f"          variable-rate file; timestamps {self.video_info['fps_ts']:.1f} fps")
        lines += [f"frames    {n} (counted)", f"length    {self.video_info['seconds']:.2f} s", "",
                  "Calibrated into the panel:", f"  screen {w} x {h}, update rate {fps:.2f} Hz", "",
                  "Not in the file, set by you:", f"  camera window {cam.width} x {cam.height} px",
                  f"  FOV {cam.fov_w_deg:g} x {cam.fov_h_deg:g} deg, so 1 px =", f"  {cam.ifov_deg*3600:.1f} arcsec; degree readouts", "  depend on this setting.", "",
                  "Target and disturbance settings are", "locked: the video already contains", "them. No ground truth exists, so", "tracking and centroiding error read", "n/a; lock, acquisition, re-acquisition", "and FPS are measured.", "",
                  "Press Start (Space) to run."]
        self.tele.setPlainText("\n".join(lines))

    def clear_video(self):
        self.video_path = None; self.video_info = None
        self._set_video_mode(False)
        self._video_label()

    def _set_video_mode(self, on: bool):
        """With a video loaded the scene, beacons and disturbances come from the file, so
        those sections are locked; the camera window, its FOV and rate limits still apply."""
        for key in ("target", "disturbance"):
            self.forms[key].setEnabled(not on)
        for name in ("width", "height", "background", "background_level", "star_density"):
            w = self.forms["screen"].widgets.get(name)
            if w is not None:
                w.setEnabled(not on)
        self.forms["camera"].widgets["update_rate_hz"].setEnabled(not on)
        self.sp_extra.setEnabled(not on); self.sp_dur.setEnabled(not on)

    def screenshot(self):
        Path(self.cfg.output_dir).mkdir(exist_ok=True)
        p = Path(self.cfg.output_dir) / f"screenshot_{time.strftime('%Y%m%d_%H%M%S')}.png"
        self.grab().save(str(p)); self.lbl_status.setText(f"Screenshot saved: {p}")

    def open_manual(self):
        for cand in ("docs/USER_MANUAL.pdf", "docs/USER_MANUAL.md", "_internal/docs/USER_MANUAL.pdf", "_internal/docs/USER_MANUAL.md"):
            if Path(cand).exists():
                _open_path(Path(cand)); return
        QtWidgets.QMessageBox.information(self, "User manual", "The manual was not found next to the application. It is docs/USER_MANUAL.md in the repository.")

    def open_results(self):
        d = Path(self.cfg.output_dir); d.mkdir(exist_ok=True); _open_path(d)

    def help(self):
        QtWidgets.QMessageBox.information(self, "FSOC Tracker", (
            f"FSOC Tracker v{__version__}  (SIH26169, Department of Space / ISRO SAC)\n\n"
            "WHAT YOU SEE\n"
            "Left picture: the whole scene. Cyan box = camera window. Orange circle = true beacon. Green cross = tracker estimate.\n"
            "Right picture: what the camera window sees. Dashed ring = capture radius (green when locked). "
            "Green box = this frame's detection. Orange dot = prediction with uncertainty ring. Line from centre = pointing error.\n"
            "Tiles: live specification check. Plots: errors, gimbal command with its limit, processing time with the 20 FPS budget, tracker state.\n\n"
            "OUTPUT\nEvery run writes a folder results/FSOC_<sim|video>_<name>_seed<N>_<date-time>/ holding <label>_frames.csv, _summary.json, _report.pdf and _scenario.yaml.\n\n"
            "See docs/USER_MANUAL.md for parameters and metric definitions."))


def _open_path(p: Path):
    p = Path(p)
    if sys.platform == "darwin":
        subprocess.Popen(["open", str(p)])
    elif os.name == "nt":
        os.startfile(str(p))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(p)])


def main():
    QtCore.QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("FSOC Tracker")
    app.setStyleSheet(STYLESHEET)
    w = MainWindow(); w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
