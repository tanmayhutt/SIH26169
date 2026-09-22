"""Render the desktop window offscreen and save three screenshots: idle, mid-run, after stop.
Used to review the interface without a display (and on any platform).

    python tools/gui_screenshot.py results/shot full_stress          # results/shot_idle.png, _run.png, _done.png
    W=1366 H=768 python tools/gui_screenshot.py results/small clear_line
"""
import os, sys, time
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PyQt6 import QtWidgets, QtCore
from fsoc_tracker.gui import app as A
out = sys.argv[1]; scen = sys.argv[2] if len(sys.argv) > 2 else "clear_line"
qa = QtWidgets.QApplication(sys.argv); qa.setStyle("Fusion"); qa.setStyleSheet(A.STYLESHEET)
w = A.MainWindow(); w.headless = True; w.resize(int(os.environ.get("W", "1600")), int(os.environ.get("H", "1000"))); w.show()
for _ in range(20): qa.processEvents(); time.sleep(0.02)
w.grab().save(f"{out}_idle.png")
i = w.cmb_scn.findText(scen.replace("_", " "), QtCore.Qt.MatchFlag.MatchContains)
if i >= 0: w.cmb_scn.setCurrentIndex(i)
for _ in range(10): qa.processEvents()
w.start()
t0 = time.time()
while time.time() - t0 < 6: qa.processEvents(); time.sleep(0.01)
w.grab().save(f"{out}_run.png")
w.stop() if hasattr(w, "stop") else None
t0 = time.time()
while time.time() - t0 < 3: qa.processEvents(); time.sleep(0.01)
w.grab().save(f"{out}_done.png")
print("ok")
