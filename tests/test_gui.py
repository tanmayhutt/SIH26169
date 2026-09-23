"""Desktop application behaviour that the engine tests cannot see: what the panel hands to the
run. The window is built offscreen, as the build workflow does."""
from __future__ import annotations

import os
from pathlib import Path

import cv2
import numpy as np
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PyQt6.QtWidgets")

from fsoc_tracker.engine.simulation import Simulation  # noqa: E402
from fsoc_tracker.ui_shared import prepare_video_run  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def qapp():
    return QtWidgets.QApplication.instance() or QtWidgets.QApplication([])


@pytest.fixture
def window(qapp, monkeypatch):
    monkeypatch.chdir(ROOT)                  # the scenario picker reads configs/scenarios
    from fsoc_tracker.gui.app import MainWindow
    w = MainWindow()
    yield w
    w.close()


def _write_video(folder: Path, seconds: float, fps: int = 30, size: int = 160) -> Path | None:
    """A small moving-spot video; skipped where this OpenCV build has no encoder."""
    for name, fourcc in (("clip.avi", "MJPG"), ("clip.mp4", "mp4v")):
        path = folder / name
        vw = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*fourcc), fps, (size, size))
        if not vw.isOpened():
            continue
        for i in range(int(seconds * fps)):
            img = np.full((size, size, 3), 12, np.uint8)
            a = i / fps
            x, y = int(size / 2 + size / 4 * np.cos(a)), int(size / 2 + size / 4 * np.sin(a))
            img[y - 5:y + 5, x - 5:x + 5] = 235
            vw.write(img)
        vw.release()
        if path.exists() and path.stat().st_size > 1000:
            return path
    return None


def test_prepare_video_run_drops_duration_and_decoys():
    from fsoc_tracker.engine.config import RunConfig, TargetConfig
    cfg = RunConfig(duration_s=30, targets=[TargetConfig(), TargetConfig(), TargetConfig()])
    prepare_video_run(cfg)
    assert cfg.duration_s == 0.0 and len(cfg.targets) == 1


def test_desktop_video_run_processes_the_whole_file(window, tmp_path):
    """Benchmark 2 in the desktop app: the locked Duration box (30 s by default) and a decoy
    count left over from a scenario must not reach a video run."""
    path = _write_video(tmp_path, seconds=40)
    if path is None:
        pytest.skip("this OpenCV build has no video encoder")
    window.sp_dur.setValue(30)
    window.sp_extra.setValue(2)
    window.video_path = str(path)
    cfg = window.read_cfg()
    assert cfg.duration_s == 0.0 and len(cfg.targets) == 1
    sim = Simulation(cfg, None, write_csv=False)
    assert sim.source.n_frames == sim.source.info["frames"] == 1200


def test_loaded_scenario_runs_with_its_own_seed_and_heading(window):
    """Benchmark 1: an evaluator's scenario file must run as written. Loading it turns off
    'New seed each run', which would otherwise replace the seed and a line's heading."""
    assert window.chk_random.isChecked()            # a fresh window still varies each run
    i = window.cmb_scn.findData(str(Path("configs/scenarios/clear_line.yaml")))
    assert i > 0
    window.cmb_scn.setCurrentIndex(i)
    assert not window.chk_random.isChecked()
    cfg = window.read_cfg()
    assert cfg.seed == 1 and cfg.targets[0].heading_deg == 25.0     # the values in clear_line.yaml
    window.chk_random.setChecked(True)               # the user can still ask for a fresh run
    fresh = window.read_cfg()
    assert (fresh.seed, fresh.targets[0].heading_deg) != (1, 25.0)
