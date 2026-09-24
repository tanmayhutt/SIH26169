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


def test_disturbances_change_live_during_a_desktop_run(window, tmp_path):
    """PS 'shall': introduce disturbances in the virtual camera feed. During a run only the
    Disturbances section is editable; a change reaches the running simulation, is marked, and is
    saved in the run's scenario so it replays."""
    import time
    from fsoc_tracker.engine.config import RunConfig
    window.headless = True
    window.chk_random.setChecked(False)
    window.sp_dur.setValue(6)
    window.cmb_speed.setCurrentIndex(len(window.cmb_speed) - 1)          # Max speed
    window.cfg.output_dir = str(tmp_path)
    window.start()
    app = QtWidgets.QApplication.instance()

    def wait(cond, seconds):
        t0 = time.time()
        while not cond() and time.time() - t0 < seconds:
            app.processEvents(); time.sleep(0.01)
        return cond()

    assert wait(lambda: window.sim is not None and window.sim.telemetry.records, 30)
    assert window.forms["disturbance"].isEnabled()
    assert not window.forms["camera"].isEnabled() and not window.forms["target"].isEnabled()
    assert not window.sp_dur.isEnabled() and not window.act_save.isEnabled()
    window.forms["disturbance"].widgets["atmosphere"].setCurrentText("fog")
    window.forms["disturbance"].widgets["jitter_px"].setValue(6)
    form = window.forms["disturbance"]              # salt and pepper: 10 in the panel's display unit (%)
    form.widgets["salt_pepper_frac"].setValue(0.10 * form.scales.get("salt_pepper_frac", 1.0))
    assert wait(lambda: window.sim.changes, 10), "the change did not reach the run"
    sim = window.sim
    assert wait(lambda: window.thread is None, 60), "run did not finish"
    ch = sim.changes[0]["changes"]
    assert ch["atmosphere"] == "fog" and ch["jitter_px"] == 6 and ch["contrast"] == pytest.approx(0.40)
    assert ch["salt_pepper_frac"] == pytest.approx(0.10)       # 10 % on the panel is a fraction of 0.10 in the run
    assert window.lbl_status.text().startswith("Finished")
    assert sim.summary.segments and sim.summary.segments[-1]["segment"] >= 1
    saved = RunConfig.load(sim.files["scenario"])
    assert saved.disturbance.atmosphere == "clear" and saved.schedule and saved.schedule[0].disturbance["atmosphere"] == "fog"
    assert window.forms["camera"].isEnabled() and window.sp_dur.isEnabled()      # unlocked after the run
    assert not window.act_clear_video.isEnabled()                                   # still no video loaded


# ------------------------------------------------------------------ review of 2026-09-24
def test_video_click_maps_to_video_pixels_and_closing_restores_the_screen(window, tmp_path):
    path = _write_video(tmp_path, seconds=1)
    if path is None:
        pytest.skip("this OpenCV build has no video encoder")
    window.video_path = str(path); window._preview_video(str(path))
    assert window.scene_view._geom[3:] == (160, 160)            # clicks map with the video's size
    window.clear_video()
    sc = window.forms["screen"].read()
    assert (sc.width, sc.height) == (2000, 2000)                 # the video's calibration is undone


def test_picking_a_scenario_closes_the_video_and_its_locks(window, tmp_path):
    path = _write_video(tmp_path, seconds=1)
    if path is None:
        pytest.skip("this OpenCV build has no video encoder")
    window.video_path = str(path); window._preview_video(str(path)); window._set_video_mode(True)
    window.cmb_scn.setCurrentIndex(window.cmb_scn.findData(str(Path("configs/scenarios/clear_line.yaml"))))
    assert window.video_path is None
    assert window.forms["disturbance"].isEnabled() and window.sp_extra.isEnabled() and not window.act_clear_video.isEnabled()


def test_identical_look_copies_the_designated_target_and_keeps_its_edits(window):
    window.sp_extra.setValue(2); window.chk_identical.setChecked(True)
    window.cmb_edit.setCurrentIndex(2); window.chk_desig.click()
    window.forms["target"].widgets["size_px"].setValue(17)
    cfg = window.read_cfg(for_run=False)
    assert cfg.designated == 2 and cfg.targets[2].size_px == 17
    assert all(t.size_px == 17 and t.shape == cfg.targets[2].shape for t in cfg.targets)


def test_save_scenario_keeps_the_seed_and_a_scenario_cue(window, tmp_path):
    window.chk_random.setChecked(True)
    window.sp_seed.setValue(4)
    before = window.forms["target"].widgets["heading_deg"].value()
    cfg = window.read_cfg(for_run=False)                          # what Save scenario writes
    assert cfg.seed == 4 and cfg.targets[0].heading_deg == before
    from fsoc_tracker.engine.config import RunConfig
    sc = RunConfig.load(ROOT / "configs" / "scenarios" / "clear_line.yaml")
    sc.designation, sc.designation_cue = "cue", "400,1500"
    window.apply_cfg(sc)
    run = window.read_cfg(for_run=False)
    assert run.designation == "cue" and run.designation_cue == "400,1500"
