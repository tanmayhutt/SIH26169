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
from ..engine.config import ATMOSPHERE_PRESETS, RunConfig
from ..engine.naming import run_label
from ..engine.simulation import Simulation, StepResult
from .theme import STYLESHEET, C, mono, ui_font

SCENARIO_DIR = Path("configs/scenarios")
LABEL_W = 140          # one label column width for every form, so all sections line up

from ..ui_shared import (LABELS, TIPS, HIDDEN, MODES, SPEEDS, DEFAULT_SPEED_INDEX, DURATION_RANGE,
                         EXTRA_TARGETS_MAX, SECTIONS, VIDEO_LOCKED, TILES, SCENE_LEGEND, LiveTiles, blank_tiles, final_tiles,
                         field_spec, camera_crop, scene_header, camera_top, camera_bottom, telemetry_lines, welcome_text,
                         about_text, summary_text, video_loaded_lines, video_preview_header, status_text, extra_targets,
                         new_random_seed, prepare_video_run, target_labels, scenario_check, RUN_TIPS,
                         TRUTH_TIP, truth_sidecar, LIVE_SECTIONS, LIVE_DEBOUNCE_MS, video_beacons, video_targets, beacon_labels)  # noqa: F401
from ..engine.config import target_name


# ----------------------------------------------------------------------------- form helpers
class DataclassForm(QtWidgets.QWidget):
    """Builds editable widgets for every field of a dataclass instance."""
    changed = QtCore.pyqtSignal()

    def __init__(self, obj, parent=None):
        super().__init__(parent)
        self.obj = obj
        self.widgets: dict[str, QtWidgets.QWidget] = {}
        self.scales: dict[str, float] = {}      # display unit / stored unit (salt and pepper: % on screen, fraction stored)
        lay = QtWidgets.QFormLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setVerticalSpacing(6)
        lay.setHorizontalSpacing(10)
        lay.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        lay.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for f in dataclasses.fields(obj):
            if f.name in HIDDEN:
                continue
            v = getattr(obj, f.name)
            w = self._widget(f.name, v)
            if w is None:
                continue
            self.widgets[f.name] = w
            lab = QtWidgets.QLabel(LABELS.get(f.name, f.name.replace("_", " ").capitalize()))
            lab.setProperty("class", "fieldlabel"); lab.setFixedWidth(LABEL_W); lab.setWordWrap(True)
            tip = TIPS.get(f.name)
            if tip:
                lab.setToolTip(tip); w.setToolTip(tip)
            lay.addRow(lab, w)

    def _widget(self, name, v):
        spec = field_spec(name, v)
        if spec is None:
            return None
        k = spec["kind"]
        if spec.get("scale"):
            self.scales[name] = spec["scale"]
            v = v * spec["scale"]
        if k == "bool":
            w = QtWidgets.QCheckBox(); w.setChecked(v); w.toggled.connect(self.changed)
        elif k == "int":
            w = QtWidgets.QSpinBox(); w.setRange(spec["min"], spec["max"]); w.setValue(v); w.valueChanged.connect(self.changed)
        elif k == "float":
            w = QtWidgets.QDoubleSpinBox(); w.setRange(spec["min"], spec["max"]); w.setDecimals(spec["decimals"])
            w.setSingleStep(spec["step"]); w.setValue(v); w.valueChanged.connect(self.changed)
        elif k == "choice":
            w = QtWidgets.QComboBox(); w.addItems(spec["choices"])
            if spec.get("editable"):
                w.setEditable(True)
            if v in spec["choices"] or spec.get("editable"):
                w.setCurrentText(v)
            w.currentTextChanged.connect(self.changed)
        else:
            w = QtWidgets.QLineEdit(v); w.textChanged.connect(self.changed)
        return w

    def values(self) -> dict:
        """The widget values by field name, without writing them into the configuration object
        (the object may belong to a run in progress)."""
        out = {}
        for name, w in self.widgets.items():
            if isinstance(w, QtWidgets.QCheckBox):
                out[name] = w.isChecked()
            elif isinstance(w, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
                # the stored unit, as read() writes it (salt and pepper shows % and stores a fraction)
                out[name] = w.value() / self.scales[name] if name in self.scales else w.value()
            elif isinstance(w, QtWidgets.QComboBox):
                out[name] = w.currentText()
            elif isinstance(w, QtWidgets.QLineEdit):
                out[name] = w.text()
        return out

    def read(self):
        for name, w in self.widgets.items():
            if isinstance(w, QtWidgets.QCheckBox):
                setattr(self.obj, name, w.isChecked())
            elif isinstance(w, (QtWidgets.QSpinBox, QtWidgets.QDoubleSpinBox)):
                setattr(self.obj, name, w.value() / self.scales[name] if name in self.scales else w.value())
            elif isinstance(w, QtWidgets.QComboBox):
                setattr(self.obj, name, w.currentText().strip())
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
                w.setValue(v * self.scales[name] if name in self.scales else v)
            elif isinstance(w, QtWidgets.QComboBox):
                w.setCurrentText(str(v))
            elif isinstance(w, QtWidgets.QLineEdit):
                w.setText(str(v))
            w.blockSignals(False)


def section(title: str, inner: QtWidgets.QWidget, hint: str = "", ref: str = "") -> QtWidgets.QWidget:
    box = QtWidgets.QWidget()
    lay = QtWidgets.QVBoxLayout(box)
    lay.setContentsMargins(0, 8, 0, 12)
    lay.setSpacing(6)
    text = title if not ref else f"{title}&nbsp;&nbsp;<span style='color:{C['faint']}; font-weight:400'>{ref}</span>"
    lab = QtWidgets.QLabel(text)
    lab.setTextFormat(Qt.TextFormat.RichText)
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
        lay = QtWidgets.QVBoxLayout(self); lay.setContentsMargins(10, 8, 10, 8); lay.setSpacing(1)
        self.t = QtWidgets.QLabel(title); self.t.setProperty("class", "tiletitle"); self.t.setFont(ui_font(9.5))
        self.v = QtWidgets.QLabel("\u2013"); self.v.setProperty("class", "tilevalue")
        vf = ui_font(17); vf.setWeight(QtGui.QFont.Weight.DemiBold); self.v.setFont(vf)
        self.u = QtWidgets.QLabel(unit); self.u.setProperty("class", "tileunit"); self.u.setFont(ui_font(9.5))
        self.base_unit = unit
        lay.addWidget(self.t); lay.addWidget(self.v); lay.addWidget(self.u)
        self.setMinimumWidth(110)
        for lab in (self.t, self.v, self.u):
            lab.setMinimumWidth(1)          # let a narrow tile shrink instead of pushing its neighbours

    def show(self, d: dict):
        self.set(d["text"], d.get("state"), d.get("unit"))

    def set(self, text: str, state: str | None = None, unit: str | None = None):
        self.v.setText(text)
        col = {"pass": C["good"], "fail": C["signal"], "warn": C["signal"], None: C["ink"]}.get(state, C["ink"])
        self.v.setStyleSheet(f"color: {col};")
        self.u.setText(unit if unit is not None else self.base_unit)


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


def _bar(p: QtGui.QPainter, y: int, h: int, width: int):
    p.fillRect(0, y, width, h, QtGui.QColor(0, 0, 0, 165))


def _text(p: QtGui.QPainter, x: float, y: float, text: str, col: str, font: QtGui.QFont, max_w: float) -> float:
    """Draw text elided to max_w; returns the x just after it, so strips never overlap."""
    p.setFont(font); p.setPen(QtGui.QColor(col))
    fm = QtGui.QFontMetrics(font)
    t = fm.elidedText(text, Qt.TextElideMode.ElideRight, int(max(max_w, 0)))
    p.drawText(QtCore.QPointF(x, y), t)
    return x + fm.horizontalAdvance(t)


class SceneView(QtWidgets.QLabel):
    """The whole screen, downscaled, with the camera window, truth, estimate and trails.
    A click reports the point in screen pixels (used to designate a target)."""
    clicked = QtCore.pyqtSignal(float, float)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(360, 360)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setProperty("class", "view")
        self.trail_true: list[tuple[float, float]] = []
        self.trail_win: list[tuple[float, float]] = []
        self.names: list[str] = []          # target names in configured order
        self.designated = 0
        self._geom = None                   # (scale, pixmap w, pixmap h, source w, source h) of the last picture

    def set_targets(self, names: list[str], designated: int):
        self.names, self.designated = list(names), int(designated)

    def remember_geometry(self, s: float, pw: int, ph: int, w: int, h: int):
        self._geom = (s, pw, ph, w, h)

    def mousePressEvent(self, ev):
        if self._geom is None:
            return
        s, pw, ph, w, h = self._geom
        ox, oy = (self.width() - pw) / 2.0, (self.height() - ph) / 2.0
        x, y = (ev.position().x() - ox) / s, (ev.position().y() - oy) / s
        if 0 <= x < w and 0 <= y < h:
            self.clicked.emit(float(x), float(y))

    def draw_beacons(self, p: QtGui.QPainter, beacons, s: float, font):
        """Every target with its name; the designated one in the signal colour."""
        for i, (bx, by) in enumerate(beacons):
            des = i == self.designated
            p.setPen(_pen(C["signal"] if des else C["muted"], 1.2 if des else 1.0))
            p.drawEllipse(QtCore.QPointF(bx * s, by * s), 7 if des else 5, 7 if des else 5)
            if len(beacons) > 1 or self.names:
                name = self.names[i] if i < len(self.names) else f"Target {i + 1}"
                p.setFont(font); p.setPen(QtGui.QColor(C["signal"] if des else C["muted"]))
                label = name if not des else name + "  (designated)"
                tw = QtGui.QFontMetrics(font).horizontalAdvance(label)
                x = bx * s + 9 if bx * s + 9 + tw < p.device().width() - 4 else bx * s - 9 - tw   # keep the label on the picture
                p.drawText(QtCore.QPointF(x, by * s - 6), label)

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
            di = min(self.designated, len(res.frame.truth.beacons) - 1)
            tx, ty = res.frame.truth.beacons[di]
            self.trail_true.append((tx * s, ty * s))
            self.draw_beacons(p, res.frame.truth.beacons, s, mono(8))
        if res.track.estimate is not None:
            ex, ey = res.track.estimate
            p.setPen(_pen(C["good"], 1.2))
            p.drawLine(int(ex * s - 8), int(ey * s), int(ex * s + 8), int(ey * s)); p.drawLine(int(ex * s), int(ey * s - 8), int(ex * s), int(ey * s + 8))
        f = mono(8.5); W = pm.width()
        _bar(p, 0, 20, W)
        _text(p, 8, 14, scene_header(w, h, ifov_deg, res.frame.t), C["muted"], f, W - 16)
        _bar(p, pm.height() - 20, 20, W)
        x = 8.0
        for key, txt in SCENE_LEGEND:
            col = C[key]
            if x > W - 40:
                break
            p.fillRect(QtCore.QRectF(x, pm.height() - 13, 8, 3), QtGui.QColor(col))
            x = _text(p, x + 12, pm.height() - 7, txt, col, f, W - x - 20) + 16
        p.end()
        self.remember_geometry(s, pm.width(), pm.height(), w, h)
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
        x0, y0, w, h = res.window
        crop = camera_crop(img, res.window)
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
            p.setPen(_pen(C["ink2"], 1.5)); p.drawLine(int(bx), by, int(bx + bar), by)
            p.setFont(mono(8)); p.drawText(int(bx), by - 5, "1 deg")
        col = {"TRACK": C["good"], "COAST": C["signal"], "REACQUIRE": C["signal"]}.get(tr.mode.value, C["accent"])
        W, Hh = pm.width(), pm.height()
        _bar(p, 0, 22, W)
        top_state, top_detail = camera_top(res.record, ifov_deg)
        x = _text(p, 8, 15, top_state, col, mono(9, bold=True), W - 16) + 16
        _text(p, x, 15, top_detail, C["ink2"], mono(8.5), W - x - 8)
        _bar(p, Hh - 20, 20, W)
        bottom, sat = camera_bottom(res.record)
        x = _text(p, 8, Hh - 6, bottom, C["muted"], mono(8.5), W - 16)
        if sat:
            _text(p, x + 10, Hh - 6, "rate limit", C["signal"], mono(8.5, bold=True), W - x - 18)
        p.end()
        self.setPixmap(pm)


# ----------------------------------------------------------------------------- main window
class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"ARGUS  v{__version__}  SIH26169")
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
        self._last_res = None
        self._build()
        self.apply_cfg(self.cfg)
        self._shortcuts()

    # ------------------------------------------------------------- layout
    def _build(self):
        tb = self.addToolBar("Run"); tb.setMovable(False); tb.setFloatable(False)
        tb.setContextMenuPolicy(Qt.ContextMenuPolicy.PreventContextMenu)
        tb.addWidget(QtWidgets.QLabel("Scenario"))
        self.cmb_scn = QtWidgets.QComboBox(); self.cmb_scn.setMinimumWidth(170)
        self._fill_scenarios()
        self.cmb_scn.currentIndexChanged.connect(self._scenario_picked)
        self.cmb_scn.setToolTip("Ready-made test cases from configs/scenarios. Pick one, then Start. Edit any value on the left before starting.")
        tb.addWidget(self.cmb_scn)
        tb.addSeparator()
        self.act_start = tb.addAction("Start", self.start); self.act_start.setToolTip("Space")
        self.act_pause = tb.addAction("Pause", self.pause); self.act_pause.setToolTip("Space while running")
        self.act_step = tb.addAction("Step", self.step_once); self.act_step.setToolTip("N: advance one frame while paused")
        self.act_stop = tb.addAction("Stop", self.stop); self.act_stop.setToolTip("Esc")
        tb.widgetForAction(self.act_start).setObjectName("primary")
        tb.widgetForAction(self.act_stop).setObjectName("danger")
        tb.addSeparator()
        tb.addWidget(QtWidgets.QLabel("Speed"))
        self.cmb_speed = QtWidgets.QComboBox()
        for name, _ in SPEEDS:
            self.cmb_speed.addItem(name)
        self.cmb_speed.setCurrentIndex(DEFAULT_SPEED_INDEX)
        self.cmb_speed.setToolTip("Playback pacing. Max speed shows the true processing rate.")
        tb.addWidget(self.cmb_speed)
        tb.addSeparator()
        self.act_open = tb.addAction("Open video", self.open_video)
        self.act_open.setToolTip("Benchmark 2 (Ctrl+O): use a video file as the scene; the simulator is bypassed")
        self.act_clear_video = tb.addAction("Simulator", self.clear_video)
        self.act_clear_video.setToolTip("Leave video mode and use the simulated scene again")
        self.act_clear_video.setEnabled(False)
        self.act_truth = tb.addAction("Truth CSV", self.open_truth); self.act_truth.setToolTip(TRUTH_TIP); self.act_truth.setEnabled(False)
        self.video_truth = ""
        spacer = QtWidgets.QWidget(); spacer.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Preferred)
        spacer.setStyleSheet("background: transparent;")
        tb.addWidget(spacer)
        tb.addSeparator()
        self.act_save = tb.addAction("Save scenario", self.save_scenario)
        self.act_save.setToolTip("Ctrl+S: save the current settings as a scenario file")
        tb.addAction("Screenshot", self.screenshot).setToolTip("Ctrl+P: save a PNG of this window into results/")
        tb.addAction("Results", self.open_results).setToolTip("Open the results folder")
        tb.addAction("Manual", self.open_manual).setToolTip("Open the user manual")
        tb.addAction("About", self.help).setToolTip("What each view shows, and where the output goes")

        central = QtWidgets.QWidget(); self.setCentralWidget(central)
        root = QtWidgets.QHBoxLayout(central); root.setContentsMargins(8, 8, 8, 8); root.setSpacing(8)

        self.forms = {
            "screen": DataclassForm(self.cfg.screen), "camera": DataclassForm(self.cfg.camera),
            "target": DataclassForm(self.cfg.targets[0]), "disturbance": DataclassForm(self.cfg.disturbance),
            "tracker": DataclassForm(self.cfg.tracker),
        }
        self.forms["disturbance"].widgets["atmosphere"].currentTextChanged.connect(self._preset_changed)
        # disturbances changed while a run is going reach it after a short pause (LIVE_DEBOUNCE_MS)
        self._live_timer = QtCore.QTimer(self); self._live_timer.setSingleShot(True); self._live_timer.setInterval(LIVE_DEBOUNCE_MS)
        self._live_timer.timeout.connect(self._push_live_disturbance)
        for key in LIVE_SECTIONS:
            self.forms[key].changed.connect(self._live_edited)
        run_w = QtWidgets.QWidget(); rl = QtWidgets.QFormLayout(run_w); rl.setContentsMargins(0, 0, 0, 0); rl.setVerticalSpacing(6); rl.setHorizontalSpacing(10)
        rl.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.ed_name = QtWidgets.QLineEdit(self.cfg.name)
        self.sp_seed = QtWidgets.QSpinBox(); self.sp_seed.setRange(0, 10 ** 6); self.sp_seed.setValue(self.cfg.seed)
        self.sp_seed.setToolTip("Same seed and settings give exactly the same run.")
        self.sp_dur = QtWidgets.QDoubleSpinBox(); self.sp_dur.setRange(*DURATION_RANGE); self.sp_dur.setValue(self.cfg.duration_s)
        self.sp_extra = QtWidgets.QSpinBox(); self.sp_extra.setRange(0, EXTRA_TARGETS_MAX); self.sp_extra.setValue(len(self.cfg.targets) - 1)
        self.sp_extra.setToolTip("Decoy beacons with random paths. The tracker must keep following the designated one.")
        self.chk_random = QtWidgets.QCheckBox("New seed each run"); self.chk_random.setChecked(True)
        self.chk_random.setToolTip("On: each Start draws a new seed (start position, noise, decoys) and a new heading for line paths, so every run is different. "
                                   "Off: the seed shown is used, so a run can be repeated exactly. The seed used is always shown in the status bar and saved with the results.")
        # targets: how many, which one is followed, how it is designated, which one the panel edits
        self.sp_extra.setToolTip(RUN_TIPS["extra"])
        self.chk_identical = QtWidgets.QCheckBox("Identical look"); self.chk_identical.setToolTip(RUN_TIPS["identical"])
        # a video's beacons (found on load) are chosen here, in the Run section; the row shows only with a video
        self.cmb_beacon = QtWidgets.QComboBox(); self.cmb_beacon.setToolTip(RUN_TIPS["beacon"])
        for lab, w in (("Name", self.ed_name), ("Seed", self.sp_seed), ("", self.chk_random), ("Duration (s)", self.sp_dur), ("Extra targets", self.sp_extra),
                       ("", self.chk_identical), ("Beacon", self.cmb_beacon)):
            l = QtWidgets.QLabel(lab); l.setProperty("class", "fieldlabel"); l.setFixedWidth(LABEL_W); rl.addRow(l, w)
        self.run_layout = rl; self.run_layout.setRowVisible(self.cmb_beacon, False)
        # the Target section: pick a target to edit, tick the one to follow
        self.cmb_edit = QtWidgets.QComboBox(); self.cmb_edit.setToolTip(RUN_TIPS["edit"])
        self.chk_desig = QtWidgets.QCheckBox("Designated"); self.chk_desig.setToolTip(RUN_TIPS["designated"])
        self.edit_idx = 0; self.designated_idx = 0
        self.designation_mode = "auto"; self.designation_cue = ""
        tw = QtWidgets.QWidget(); tl = QtWidgets.QFormLayout(tw); tl.setContentsMargins(0, 0, 0, 0); tl.setVerticalSpacing(6); tl.setHorizontalSpacing(10)
        tl.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        for lab, w in (("Target", self.cmb_edit), ("", self.chk_desig)):
            l = QtWidgets.QLabel(lab); l.setProperty("class", "fieldlabel"); l.setFixedWidth(LABEL_W); tl.addRow(l, w)
        self.target_box = QtWidgets.QWidget(); tb_l = QtWidgets.QVBoxLayout(self.target_box); tb_l.setContentsMargins(0, 0, 0, 0); tb_l.setSpacing(8)
        tb_l.addWidget(tw); tb_l.addWidget(self.forms["target"])
        self.lbl_check = QtWidgets.QLabel(""); self.lbl_check.setWordWrap(True); self.lbl_check.setProperty("class", "hint")
        self.lbl_check.setToolTip("Scenario check: values beyond the problem statement, values the camera cannot physically follow, and values that were corrected.")
        rl.addRow(self.lbl_check)
        self.sp_extra.valueChanged.connect(self._targets_changed); self.chk_identical.toggled.connect(self._targets_changed)
        self.cmb_edit.currentIndexChanged.connect(self._edit_changed)
        self.chk_desig.clicked.connect(self._designate_current)
        self.cmb_beacon.activated.connect(self._beacon_chosen)
        self.sp_seed.valueChanged.connect(lambda _v: self._schedule_check())
        self.forms["target"].widgets["name"].textChanged.connect(self._name_edited)
        for f in self.forms.values():
            f.changed.connect(self._schedule_check)
        self._check_timer = QtCore.QTimer(self); self._check_timer.setSingleShot(True); self._check_timer.setInterval(250)
        self._check_timer.timeout.connect(self._run_check)
        panel = QtWidgets.QWidget(); pl = QtWidgets.QVBoxLayout(panel); pl.setContentsMargins(4, 0, 10, 0); pl.setSpacing(0)
        pl.addWidget(section("Run", run_w))
        for key, title, ref, hint in SECTIONS:
            pl.addWidget(section(title, self.target_box if key == "target" else self.forms[key], hint, ref))
        pl.addStretch(1)
        scroll = QtWidgets.QScrollArea(); scroll.setWidget(panel); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setFixedWidth(330); scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        root.addWidget(scroll)

        centre = QtWidgets.QVBoxLayout(); centre.setSpacing(8)
        tiles = QtWidgets.QHBoxLayout(); tiles.setSpacing(8)
        self.tiles = {k: Tile(title, unit) for k, title, unit in TILES}
        for t in self.tiles.values():
            tiles.addWidget(t)
        centre.addLayout(tiles)
        views = QtWidgets.QHBoxLayout(); views.setSpacing(8)
        self.scene_view = SceneView(); self.cam_view = CameraView()
        self.scene_view.clicked.connect(self._scene_clicked)
        self._placeholders()
        views.addWidget(self.scene_view, 1); views.addWidget(self.cam_view, 1)
        centre.addLayout(views, 3)
        pg.setConfigOptions(antialias=False, background=C["surface"], foreground=C["muted"])
        self.plots = QtWidgets.QWidget(); gl = QtWidgets.QGridLayout(self.plots); gl.setContentsMargins(0, 0, 0, 0); gl.setSpacing(6)
        key = lambda col, name: f"<span style='color:{col}'>&#9632;</span>&nbsp;<span style='color:{C['muted']}'>{name}</span>"
        self.p_err = self._plot(f"<span style='color:{C['ink2']}'>Error (px)</span>&nbsp;&nbsp;&nbsp;{key(C['accent'], 'tracking')}&nbsp;&nbsp;{key(C['signal'], 'centroiding')}")
        self.p_cmd = self._plot(f"<span style='color:{C['ink2']}'>Gimbal rate (deg/s)</span>&nbsp;&nbsp;&nbsp;{key(C['accent'], 'pan')}&nbsp;&nbsp;{key(C['signal'], 'tilt')}")
        self.p_fps = self._plot(f"<span style='color:{C['ink2']}'>Processing time per frame (ms)</span>&nbsp;&nbsp;&nbsp;{key(C['signal'], '50 ms = 20 FPS budget')}")
        self.p_mode = self._plot(f"<span style='color:{C['ink2']}'>Tracker state</span>")
        gl.addWidget(self.p_err, 0, 0); gl.addWidget(self.p_cmd, 0, 1); gl.addWidget(self.p_fps, 1, 0); gl.addWidget(self.p_mode, 1, 1)
        self.c_terr = self.p_err.plot(pen=pg.mkPen(C["accent"], width=1.2))
        self.c_cerr = self.p_err.plot(pen=pg.mkPen(C["signal"], width=1.2))
        self.p_err.addLine(y=10, pen=pg.mkPen(C["faint"], style=Qt.PenStyle.DashLine))
        self.c_pan = self.p_cmd.plot(pen=pg.mkPen(C["accent"], width=1.2))
        self.c_tilt = self.p_cmd.plot(pen=pg.mkPen(C["signal"], width=1.2))
        self.lim_lines = [self.p_cmd.addLine(y=v, pen=pg.mkPen(C["faint"], style=Qt.PenStyle.DashLine)) for v in (5, -5)]
        self.c_proc = self.p_fps.plot(pen=pg.mkPen(C["ink"], width=1.2))
        self.p_fps.addLine(y=50, pen=pg.mkPen(C["signal"], style=Qt.PenStyle.DashLine))
        self.c_mode = self.p_mode.plot(pen=pg.mkPen(C["accent"], width=1.4), stepMode="right")
        self.p_mode.getAxis("left").setTicks([[(i, m) for i, m in enumerate(MODES)]])
        self.p_mode.setYRange(-0.3, 4.3)
        self._idle_ranges()
        self.plots.setMinimumHeight(300)
        centre.addWidget(self.plots, 2)
        root.addLayout(centre, 1)

        self.tele = QtWidgets.QPlainTextEdit(); self.tele.setReadOnly(True); self.tele.setFixedWidth(250)
        self.tele.setProperty("class", "tele"); self.tele.setFont(mono(9.5))
        self.tele.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.tele.setLineWrapMode(QtWidgets.QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.tele.setPlainText(self._welcome())
        root.addWidget(self.tele)

        self.status = self.statusBar()
        self.lbl_status = QtWidgets.QLabel(status_text("ready"))
        self.status.addWidget(self.lbl_status, 1)
        self.progress = QtWidgets.QProgressBar(); self.progress.setFixedWidth(220); self.progress.setTextVisible(False); self.progress.setValue(0)
        self.status.addPermanentWidget(self.progress)
        self._set_running(False)
        self._buf_reset()
        self._refresh_target_lists()

    def _plot(self, title):
        pw = pg.PlotWidget()
        pw.setTitle(title, size="9pt", justify="left")
        pw.showGrid(x=True, y=True, alpha=0.15)
        pw.setMenuEnabled(False)
        pw.setMouseEnabled(x=False, y=False)
        pw.hideButtons()
        for ax in ("left", "bottom"):
            a = pw.getAxis(ax); a.setTextPen(pg.mkPen(C["muted"])); a.setPen(pg.mkPen(C["line"])); a.setStyle(tickFont=ui_font(8.5))
        pw.setLabel("bottom", "time (s)", color=C["faint"])
        return pw

    def _idle_ranges(self):
        """Axes that mean something before any data arrives."""
        for pw in (self.p_err, self.p_cmd, self.p_fps, self.p_mode):
            pw.setXRange(0, 10, padding=0)
        self.p_err.setYRange(0, 40, padding=0)
        self.p_cmd.setYRange(-8, 8, padding=0)
        self.p_fps.setYRange(0, 60, padding=0)

    def _placeholders(self):
        self.scene_view.setPixmap(QtGui.QPixmap()); self.cam_view.setPixmap(QtGui.QPixmap())
        self.scene_view.setText("The whole scene appears here when a run starts.")
        self.cam_view.setText("The camera window appears here.")

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
        return welcome_text()

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
                # a scenario file (an evaluator's Benchmark 1 case) is run exactly as written
                self.chk_random.setChecked(False)
                self.lbl_status.setText(status_text("loaded", path=path))
            except Exception as e:
                QtWidgets.QMessageBox.critical(self, "Load failed", str(e))

    # ------------------------------------------------------------- config
    def apply_cfg(self, cfg: RunConfig):
        if self.video_path and not cfg.video:
            self.clear_video()          # before the scenario's own designation cue is read below
        self.cfg = cfg
        self.edit_idx = 0
        self.forms["screen"].write(cfg.screen); self.forms["camera"].write(cfg.camera)
        self.forms["target"].write(cfg.targets[0]); self.forms["disturbance"].write(cfg.disturbance)
        self.forms["tracker"].write(cfg.tracker)
        self.ed_name.setText(cfg.name); self.sp_seed.setValue(cfg.seed); self.sp_dur.setValue(cfg.duration_s)
        self.sp_extra.blockSignals(True); self.sp_extra.setValue(max(len(cfg.targets) - 1, 0)); self.sp_extra.blockSignals(False)
        self.designation_mode = cfg.designation; self.designation_cue = cfg.designation_cue
        self.designated_idx = cfg.designated_index()
        self.video_path = cfg.video
        self._refresh_target_lists()
        self._video_label()

    def _read_targets(self):
        """The panel's target form back into the list, and the list sized to 'Extra targets'."""
        self.forms["target"].read()
        if self.video_path:                 # a video's targets are the beacons the scan found
            return
        seed = self.sp_seed.value()
        t0 = self.cfg.targets[0]
        self.cfg.targets = extra_targets(t0, self.cfg.targets, self.sp_extra.value(), seed, self.chk_identical.isChecked(),
                                         getattr(self, "designated_idx", 0))

    def read_cfg(self, for_run: bool = True) -> RunConfig:
        cfg = self.cfg
        cfg.screen = self.forms["screen"].read(); cfg.camera = self.forms["camera"].read()
        cfg.disturbance = self.forms["disturbance"].read(); cfg.tracker = self.forms["tracker"].read()
        self._read_targets()
        cfg.name = self.ed_name.text().strip() or "run"; cfg.duration_s = self.sp_dur.value()
        if for_run and self.chk_random.isChecked():
            new_random_seed(cfg)
            self.sp_seed.blockSignals(True); self.sp_seed.setValue(cfg.seed); self.sp_seed.blockSignals(False)
            self.forms["target"].write(cfg.targets[self.edit_idx])
        else:
            cfg.seed = self.sp_seed.value()
        cfg.designated = min(self.designated_idx, len(cfg.targets) - 1)
        cfg.designation = "cue" if (self.video_path and self.designation_cue) else self.designation_mode
        # a click on a video's first frame, or a scenario that designates by a cue point
        cfg.designation_cue = self.designation_cue if (self.video_path or self.designation_mode == "cue") else ""
        cfg.video = self.video_path
        cfg.video_truth = self.video_truth if self.video_path else ""
        if cfg.video and for_run:
            # the run gets a copy: the panel keeps its target list for when the video is closed
            import copy
            cfg = prepare_video_run(copy.deepcopy(cfg))
        return cfg

    # ------------------------------------------------------------- targets
    def _refresh_target_lists(self):
        names = target_labels(self.cfg)
        self.designated_idx = min(max(self.designated_idx, 0), len(names) - 1)
        self.cmb_edit.blockSignals(True); self.cmb_edit.clear()
        self.cmb_edit.addItems([("* " if i == self.designated_idx else "") + n for i, n in enumerate(names)])
        self.cmb_edit.setCurrentIndex(min(max(self.edit_idx, 0), len(names) - 1)); self.cmb_edit.blockSignals(False)
        self.edit_idx = self.cmb_edit.currentIndex()
        self._sync_desig_box()
        self.scene_view.set_targets(names, self.designated_idx)
        self._schedule_check()

    def _sync_desig_box(self):
        """The tick box shows whether the target being edited is the designated one. One target
        is always designated, so the box cannot be unticked: tick it on another target instead."""
        on = self.edit_idx == self.designated_idx
        self.chk_desig.blockSignals(True); self.chk_desig.setChecked(on); self.chk_desig.setEnabled(not on); self.chk_desig.blockSignals(False)

    def _designate_current(self, *_):
        self.designated_idx = self.edit_idx
        self._refresh_target_lists()
        self.lbl_status.setText(f"Designated {target_labels(self.cfg)[self.designated_idx]}: the tracker follows it and the report scores it.")
        if self.video_path:
            self._preview_video(self.video_path)

    def _targets_changed(self, *_):
        self._read_targets()
        self._refresh_target_lists()

    def _edit_changed(self, idx: int):
        if idx < 0 or idx >= len(self.cfg.targets):
            return
        self.forms["target"].read()                  # keep the edits of the target being left
        self.edit_idx = idx
        self.forms["target"].write(self.cfg.targets[idx])
        self._sync_desig_box()
        self._schedule_check()

    def _name_edited(self, text: str):
        i = self.edit_idx
        if 0 <= i < len(self.cfg.targets):
            self.cfg.targets[i].name = text
            label = ("* " if i == self.designated_idx else "") + target_name(self.cfg.targets[i], i)
            self.cmb_edit.setItemText(i, label)
            self.scene_view.set_targets(target_labels(self.cfg), self.designated_idx)

    def _beacon_chosen(self, idx: int):
        """The Beacon picker of the Run section: the chosen video beacon is the designated target."""
        if self.thread is not None or not self.video_path or not getattr(self, "video_beacons", None):
            return
        self.designated_idx = int(idx); self.edit_idx = int(idx)
        self.forms["target"].write(self.cfg.targets[self.edit_idx])
        self._preview_video(self.video_path)
        self._schedule_check()

    def _refresh_beacon_list(self):
        vb = getattr(self, "video_beacons", None) or []
        self.cmb_beacon.blockSignals(True); self.cmb_beacon.clear()
        self.cmb_beacon.addItems(beacon_labels(vb) if vb else ["none found"])
        self.cmb_beacon.setCurrentIndex(min(self.designated_idx, max(len(vb) - 1, 0))); self.cmb_beacon.setEnabled(bool(vb))
        self.cmb_beacon.setToolTip(RUN_TIPS["beacon"] if vb else RUN_TIPS["beacon_none"]); self.cmb_beacon.blockSignals(False)

    def _scene_clicked(self, x: float, y: float):
        """A click on the simulator preview before a run designates the target nearest the
        click. On a video the beacon is chosen in the Run section, not on the picture."""
        if self.thread is not None or self.video_path:
            return
        pos = getattr(self, "_preview_pos", None)
        if pos:
            self.designated_idx = int(np.argmin([np.hypot(px - x, py - y) for px, py in pos]))
            self._refresh_target_lists()
            self.lbl_status.setText(f"Designated {target_labels(self.cfg)[self.designated_idx]}: the tracker follows it and the report scores it.")
            self._preview_sim()

    # ------------------------------------------------------------- scenario check and preview
    def _schedule_check(self, *_):
        if self.thread is None:
            self._check_timer.start()

    def _run_check(self):
        if self.thread is not None:
            return
        import copy
        try:
            cfg = copy.deepcopy(self.read_cfg(for_run=False))
        except Exception:
            return
        lines = scenario_check(cfg)
        self.lbl_check.setText("\n".join(lines) if lines else "Scenario check: all values inside the PS envelope.")
        self.lbl_check.setStyleSheet(f"color: {C['signal'] if lines else C['faint']};")
        if not self.video_path:
            self._preview_sim(cfg)

    def _preview_sim(self, cfg: RunConfig | None = None):
        """The scene at t = 0 before a run, every target named, so the designated one can be
        checked and chosen by clicking. With 'New seed each run' the run draws a new seed, so
        random start positions will differ; the choice of target does not."""
        import copy
        from ..world.renderer import World
        if self.thread is not None:
            return
        try:
            cfg = copy.deepcopy(cfg or self.read_cfg(for_run=False))
            world = World(cfg)
            img, truth = world.render()
        except Exception:
            return
        h, w = img.shape[:2]
        side = min(self.scene_view.width(), self.scene_view.height()) - 8
        s = side / max(h, w)
        pm = QtGui.QPixmap.fromImage(to_qimage(img).scaled(int(w * s), int(h * s), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation))
        p = QtGui.QPainter(pm); p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self.scene_view.set_targets(target_labels(cfg), cfg.designated_index())
        self.scene_view.draw_beacons(p, truth.beacons, s, mono(8))
        x0, y0, ww, wh = truth.window
        p.setPen(_pen(C["accent"], 1.5)); p.drawRect(int(x0 * s), int(y0 * s), int(ww * s), int(wh * s))
        _bar(p, 0, 20, pm.width())
        _text(p, 8, 14, "PREVIEW t = 0   click a target to designate it", C["muted"], mono(8.5), pm.width() - 16)
        p.end()
        self._preview_pos = list(truth.beacons)
        self.scene_view.remember_geometry(s, pm.width(), pm.height(), w, h)
        self.scene_view.setPixmap(pm)

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
            self.lbl_status.setText(status_text("video", path=self.video_path))
        else:
            self.lbl_status.setText(status_text("ready"))

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
        self._buf_reset(); self.scene_view.reset(); self.cam_view.reset(); self._last_res = None
        names = cfg.target_names()
        self.scene_view.set_targets(names, self.sim.di)
        self._following = names[self.sim.di] if names else ""
        for k, d in blank_tiles().items():
            self.tiles[k].show(d)
        self.tiles["state"].set("starting", None, "")
        lim = cfg.camera.max_pan_rate_deg_s
        for ln, v in zip(self.lim_lines, (lim, -lim)):
            ln.setValue(v)
        self.p_cmd.setYRange(-1.5 * lim, 1.5 * lim, padding=0)
        self.p_err.enableAutoRange(axis="y"); self.p_fps.enableAutoRange(axis="y")
        for pw in (self.p_err, self.p_cmd, self.p_fps, self.p_mode):
            pw.enableAutoRange(axis="x")
        n_total = getattr(self.sim.source, "n_frames", 0) or int(round(cfg.duration_s * cfg.camera.update_rate_hz))
        self.progress.setRange(0, max(n_total, 1)); self.progress.setValue(0)
        speed = SPEEDS[self.cmb_speed.currentIndex()][1]
        self.thread = QtCore.QThread(); self.worker = Worker(self.sim, speed)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.stepped.connect(self.on_step, Qt.ConnectionType.QueuedConnection)
        self.worker.finished.connect(self.on_finished, Qt.ConnectionType.QueuedConnection)
        self.worker.failed.connect(self.on_failed, Qt.ConnectionType.QueuedConnection)
        self.thread.start()
        self._set_running(True)
        self.lbl_status.setText(status_text("running", name=cfg.name, seed=cfg.seed, out=self.out_dir)
                                + (f"   |   {scenario_check(cfg)[0]}" if scenario_check(cfg) else ""))

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
        # during a run only the live sections stay editable; everything else is fixed for the run
        for key, form in self.forms.items():
            form.setEnabled(not r or key in LIVE_SECTIONS)
        for w in (self.ed_name, self.sp_seed, self.chk_random, self.sp_dur, self.sp_extra,
                  self.chk_identical, self.cmb_edit, self.chk_desig, self.target_box):
            w.setEnabled(not r)
        for a in (self.act_open, self.act_save):
            a.setEnabled(not r)
        if not r and not self.video_path:
            self._sync_desig_box()              # the designated target's own box stays unclickable
        if self.video_path:
            self._set_video_mode(True)          # a video run has no live disturbances (they are in the file)
        self.act_clear_video.setEnabled(bool(self.video_path) and not r)
        self.act_truth.setEnabled(bool(self.video_path) and not r)

    # ------------------------------------------------------------- live disturbances
    def _live_edited(self):
        if self.worker is not None and self.sim is not None and self.sim.accepts_disturbance_changes:
            self._live_timer.start()

    def _push_live_disturbance(self):
        if self.worker is None or self.sim is None:
            return
        if self.sim.request_disturbance(self.forms["disturbance"].values()):
            self.lbl_status.setText(status_text("changing"))

    def _mark_change(self, t: float):
        for pw in (self.p_err, self.p_cmd):
            self._change_lines.append((pw, pw.addLine(x=t, pen=pg.mkPen(C["signal"], width=1, style=Qt.PenStyle.DotLine))))

    # ------------------------------------------------------------- data flow
    def _buf_reset(self):
        self.b_t, self.b_terr, self.b_cerr, self.b_pan, self.b_tilt, self.b_proc, self.b_mode, self.b_lock = ([] for _ in range(8))
        self.live = LiveTiles()
        self._segment = 0
        for pw, ln in getattr(self, "_change_lines", []):
            pw.removeItem(ln)
        self._change_lines = []

    @QtCore.pyqtSlot(object)
    def on_step(self, res: StepResult):
        r = res.record
        self.b_t.append(r.t_sim); self.b_terr.append(r.tracking_err_px); self.b_cerr.append(r.centroid_err_px)
        self.b_pan.append(r.cmd_pan_rate); self.b_tilt.append(r.cmd_tilt_rate); self.b_proc.append(r.proc_ms)
        self.b_mode.append(MODES.index(r.mode)); self.b_lock.append(r.locked)
        self._last_res = res
        self.live.push(r)
        if r.segment != self._segment:          # a disturbance change took effect on this frame
            self._segment = r.segment
            ch = self.sim.changes[r.segment - 1] if len(self.sim.changes) >= r.segment else None
            self.lbl_status.setText(status_text("changed", t=r.t_sim, what=ch["what"] if ch else ""))
            self._mark_change(r.t_sim)
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
        self.tele.setPlainText(telemetry_lines(r, getattr(self, '_following', '')))

    def _update_tiles(self, r):
        for k, d in self.live.tiles().items():
            self.tiles[k].show(d)

    @QtCore.pyqtSlot(object)
    def on_finished(self, sim: Simulation):
        self._teardown()
        if getattr(self, "_last_res", None) is not None:
            ifov = sim.cfg.camera.ifov_deg
            self.scene_view.update_view(self._last_res, ifov)
            self.cam_view.update_view(self._last_res, ifov, sim.cfg.tracker.capture_radius_px)
        if sim.summary:
            self._tiles_from_summary(sim.summary.values, sim.summary.passed)
        try:
            from ..engine.report import write_report          # loaded after the window (see main)
            report = write_report(sim.cfg, sim.telemetry.records, sim.summary, sim.files["report"])
        except Exception as e:
            report = None
            QtWidgets.QMessageBox.warning(self, "Report", f"Report generation failed:\n{e}")
        v = sim.summary.values if sim.summary else {}
        p = sim.summary.passed if sim.summary else {}
        msg = summary_text(v, p, str(sim.files["frames"]), str(report), sim.summary.designation if sim.summary else None,
                           sim.summary.checks if sim.summary else None)
        self.lbl_status.setText(status_text("finished", out=self.out_dir))
        if self.headless:
            return
        box = QtWidgets.QMessageBox(self); box.setWindowTitle("Run complete"); box.setText(msg)
        box.setFont(mono(10))
        if report:
            b = box.addButton("Open report", QtWidgets.QMessageBox.ButtonRole.ActionRole)
            b.clicked.connect(lambda: _open_path(report))
        b2 = box.addButton("Open folder", QtWidgets.QMessageBox.ButtonRole.ActionRole)
        b2.clicked.connect(lambda: _open_path(self.out_dir))
        box.addButton(QtWidgets.QMessageBox.StandardButton.Ok)
        box.exec()

    def _tiles_from_summary(self, v: dict, passed: dict):
        for k, d in final_tiles(v, passed).items():
            self.tiles[k].show(d)

    @QtCore.pyqtSlot(str)
    def on_failed(self, tb: str):
        self._teardown()
        self.lbl_status.setText("Run failed: " + (tb.strip().splitlines() or ["unknown error"])[-1][:160])
        QtWidgets.QMessageBox.critical(self, "Run failed", tb)

    def _teardown(self):
        if self.thread:
            self.thread.quit(); self.thread.wait(2000)
        self.thread = None; self.worker = None
        self._set_running(False)
        self.progress.setValue(self.progress.maximum())

    # ------------------------------------------------------------- files
    def save_scenario(self):
        if self.thread is not None:        # reading the panel writes into the running configuration
            return
        p, _ = QtWidgets.QFileDialog.getSaveFileName(self, "Save scenario", str(SCENARIO_DIR / "custom.yaml"), "YAML (*.yaml)")
        if p:
            self.read_cfg(for_run=False).save(p); self.lbl_status.setText(f"Saved {p}"); self._fill_scenarios()

    def open_video(self):
        if self.thread is not None:
            return
        p, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open video for Benchmark 2", "", "Video (*.mp4 *.avi *.mov *.mkv)")
        if p:
            self.video_path = p; self.ed_name.setText(Path(p).stem); self.video_truth = ""; self.designation_cue = ""
            self._preview_video(p)
            self._video_label()
            side = truth_sidecar(p)
            if side:
                self._set_truth(side)

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
        sc = self.forms["screen"].read()
        if getattr(self, "_pre_video", None) is None:      # what the video replaces, restored by clear_video
            self._pre_video = (sc.width, sc.height, self.forms["camera"].read().update_rate_hz)
        sc.width, sc.height = w, h; self.forms["screen"].write(sc)
        cam = self.forms["camera"].read(); cam.update_rate_hz = float(fps); cam.width = min(cam.width, w); cam.height = min(cam.height, h); self.forms["camera"].write(cam)
        self._set_video_mode(True)
        gray = bgr if (sc.colour and bgr.ndim == 3) else (cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY) if bgr.ndim == 3 else bgr)
        side = min(self.scene_view.width(), self.scene_view.height()) - 8
        s = side / max(h, w)
        pm = QtGui.QPixmap.fromImage(to_qimage(gray).scaled(int(w * s), int(h * s), Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.FastTransformation))
        pnt = QtGui.QPainter(pm)
        pnt.fillRect(0, 0, pm.width(), 22, QtGui.QColor(0, 0, 0, 170))
        pnt.setPen(QtGui.QColor(C["good"])); pnt.setFont(mono(9.5, bold=True))
        pnt.drawText(8, 16, "VIDEO LOADED")
        pnt.setPen(QtGui.QColor(C["ink"])); pnt.setFont(mono(8.5))
        pnt.drawText(130, 16, video_preview_header(info))
        # the camera window at its start position, for scale
        cw, ch = min(self.cfg.camera.width, w), min(self.cfg.camera.height, h)
        pnt.setPen(_pen(C["accent"], 2)); pnt.drawRect(int((w - cw) / 2 * s), int((h - ch) / 2 * s), int(cw * s), int(ch * s))
        pnt.end()
        self.scene_view.setPixmap(pm)
        # a click on this picture is a point on the video (the cue), so map it with the video's
        # own scale and size, not those of the last simulator preview
        self.scene_view.remember_geometry(s, pm.width(), pm.height(), w, h)
        self._preview_pos = None
        self.cam_view.setPixmap(QtGui.QPixmap())
        # the beacons the detector sees in the first frames become the Target list (PS: "a
        # designated moving target"): tick Designated on one, or click it on the picture
        if getattr(self, "_sim_targets", None) is None:
            self._sim_targets = (list(self.cfg.targets), self.designated_idx)
        if getattr(self, "_video_scanned", None) != path:
            self.video_beacons = video_beacons(path, self.forms["tracker"].read())
            self.cfg.targets = video_targets(self.video_beacons, self._sim_targets[0][0])
            self._video_scanned = path
            self.edit_idx = 0; self.designated_idx = 0
            self.forms["target"].write(self.cfg.targets[0])
        self._refresh_target_lists()
        self._refresh_beacon_list()
        self._apply_video_designation()
        self._draw_video_beacons(pm, s)
        self.scene_view.setPixmap(pm)
        self.cam_view.setText("Press Start to run the tracker on this video")
        for t in self.tiles.values():
            t.set("-")
        self.tiles["state"].set("video ready", None, "press Start")
        self.tele.setPlainText(video_loaded_lines(Path(path).name, info, self.forms["camera"].read()))

    def _apply_video_designation(self):
        """The designated target of a video is a detected beacon: the tracker is cued to its
        measured centre, and its measured size is the detector's prior."""
        if not self.video_path or not getattr(self, "video_beacons", None):
            return
        b = self.video_beacons[min(self.designated_idx, len(self.video_beacons) - 1)]
        self.designation_cue = f"{b['x']:.0f},{b['y']:.0f}"
        self.lbl_status.setText(f"Designated {target_labels(self.cfg)[self.designated_idx]} at {b['x']:.0f},{b['y']:.0f} "
                                f"({b['w']:.0f} x {b['h']:.0f} px, peak {b['peak']:.0f}): the tracker follows it and the report scores it. "
                                f"Choose another beacon in the Run section.")

    def _draw_video_beacons(self, pm: QtGui.QPixmap, s: float):
        if not getattr(self, "video_beacons", None):
            return
        p = QtGui.QPainter(pm); p.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        self.scene_view.set_targets(target_labels(self.cfg), self.designated_idx)
        self.scene_view.draw_beacons(p, [(b["x"], b["y"]) for b in self.video_beacons], s, mono(8))
        p.end()

    def open_truth(self):
        p, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Ground truth for this video", str(Path(self.video_path or ".").parent), "CSV (*.csv)")
        if p:
            self._set_truth(p)

    def _set_truth(self, p: str):
        from ..engine.sources import load_truth
        try:
            n = len(load_truth(p, (self.video_info or {}).get("fps", 30.0)))
        except Exception as e:
            QtWidgets.QMessageBox.warning(self, "Ground truth", f"Could not read this file:\n{e}"); return
        self.video_truth = p
        self.lbl_status.setText(f"Ground truth: {p} ({n} frames). Errors and RMSE will be computed against it.")

    def clear_video(self):
        self.video_path = None; self.video_info = None; self.video_truth = ""
        pre = getattr(self, "_pre_video", None)
        if pre is not None:               # the screen size and rate the video's calibration replaced
            sc = self.forms["screen"].read(); sc.width, sc.height = pre[0], pre[1]; self.forms["screen"].write(sc)
            cam = self.forms["camera"].read(); cam.update_rate_hz = pre[2]; self.forms["camera"].write(cam)
            self._pre_video = None
        self._set_video_mode(False)
        if getattr(self, "_sim_targets", None) is not None:
            self.cfg.targets, self.designated_idx = self._sim_targets; self._sim_targets = None
            self.edit_idx = 0; self.forms["target"].write(self.cfg.targets[0]); self._refresh_target_lists()
        self.video_beacons = []; self._video_scanned = None
        self._placeholders()
        for t in self.tiles.values():
            t.set("\u2013")
        self.tele.setPlainText(self._welcome())
        self._video_label()

    def _set_video_mode(self, on: bool):
        """With a video loaded the scene, beacons and disturbances come from the file, so
        those sections are locked; the camera window, its FOV and rate limits still apply."""
        for key, names in VIDEO_LOCKED.items():
            if key == "run":
                for w in (self.sp_extra, self.sp_dur, self.chk_identical):
                    w.setEnabled(not on)
                self.run_layout.setRowVisible(self.cmb_beacon, on)
                if not on:
                    self.designation_cue = ""
                    self._sync_desig_box()
            elif names == "*":
                self.forms[key].setEnabled(not on)
            else:
                for name in names:
                    w = self.forms[key].widgets.get(name)
                    if w is not None:
                        w.setEnabled(not on)
        self.act_clear_video.setEnabled(on)
        self.act_truth.setEnabled(on)

    def screenshot(self):
        Path(self.cfg.output_dir).mkdir(parents=True, exist_ok=True)
        p = Path(self.cfg.output_dir) / f"screenshot_{time.strftime('%Y%m%d_%H%M%S')}.png"
        self.grab().save(str(p)); self.lbl_status.setText(f"Screenshot saved: {p}")

    def open_manual(self):
        for cand in ("docs/USER_MANUAL.pdf", "docs/USER_MANUAL.md", "_internal/docs/USER_MANUAL.pdf", "_internal/docs/USER_MANUAL.md"):
            if Path(cand).exists():
                _open_path(Path(cand)); return
        QtWidgets.QMessageBox.information(self, "User manual", "The manual was not found next to the application. It is on the project site's downloads page as USER_MANUAL.pdf.")

    def open_results(self):
        d = Path(self.cfg.output_dir); d.mkdir(parents=True, exist_ok=True); _open_path(d)

    def help(self):
        QtWidgets.QMessageBox.information(self, "About ARGUS", about_text())


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
    app.setApplicationName("ARGUS")
    app.setStyle("Fusion")          # the same widget look on Windows, Linux and macOS
    app.setStyleSheet(STYLESHEET)
    w = MainWindow(); w.show()
    # The report writer (matplotlib) is the slowest import, and on a first run it also builds
    # its font cache, which took 17 s on a Mac. It is not needed until a run ends, so it loads
    # in the background once the window is on screen instead of before it.
    import threading
    threading.Thread(target=_load_report_writer, name="load-report-writer", daemon=True).start()
    return app.exec()


def _load_report_writer():
    try:
        from scipy.optimize import least_squares  # noqa: F401   the detector's sub-pixel fit, first needed on the first frame
        from ..engine import report  # noqa: F401
    except Exception:
        pass                          # a failure here shows itself, with its message, when a report is written


if __name__ == "__main__":
    sys.exit(main())
