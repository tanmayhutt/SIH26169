# Point-by-point compliance with the problem statement

Source of truth: `26169.pdf` (SIH26169, Department of Space / ISRO SAC). Every row of its
parameter table, every "shall" item, every deliverable and every evaluation stage is listed
here with where it is implemented and how it is verified. `tests/test_ps_compliance.py`
fails if any default is changed away from the PS.

Status: 🟩 implemented and verified, 🟨 implemented with a caveat, ⬜ not yet.

## Parameter table

| Row | PS text | Suggested value | Our default | Implemented in | Verified by | Status |
|---|---|---|---|---|---|---|
| 1 | Screen Size (min.) | 2000 x 2000, user-defined | 2000 x 2000, editable | `ScreenConfig.width/height` | `test_rows_1_to_6` | 🟩 |
| 2 | Camera Type | Monochrome FPA, colour optional | monochrome; colour renders a three-channel frame, tracker uses luminance | `ScreenConfig.colour`, `World._colourise` | `test_rows_1_to_6` | 🟩 |
| 3 | Camera Resolution | 640 x 480, user-defined | 640 x 480, editable | `CameraConfig.width/height` | `test_rows_1_to_6` | 🟩 |
| 4 | Camera FOV | user-defined, default 4 x 3 deg | 4 x 3 deg, editable; IFOV derived | `CameraConfig.fov_*`, `ifov_deg` | `test_rows_1_to_6`, `test_ifov_and_conversions` | 🟩 |
| 5 | Camera update rate | 30 Hz min | 30 Hz, editable upward; lag compensation scales with the rate | `CameraConfig.update_rate_hz`, `Controller.step` | `test_rows_1_to_6`, 60 Hz runs of the pack | 🟩 |
| 6 | Initial camera position | centre of the screen | centre | `Gimbal.window_centre_px()` at pose 0 | `test_rows_1_to_6` | 🟩 |
| 7 | Target type | beacon spot | rendered spot with PSF | `World._sprite` | visual, `test_centroid_accuracy_on_clean_frame` | 🟩 |
| 8 | Number of targets | 1 mandatory, multiple optional | 1; N via list or "Extra targets" | `RunConfig.targets` | `test_rows_7_to_12`, `test_multi_target_identity_held` | 🟩 |
| 9 | Target shape | user-defined, default square | square; circle, gaussian | `TargetConfig.shape` | `test_rows_7_to_12` | 🟩 |
| 10 | Target size | 5 to 20 px, default 10 x 10 | 10, editable | `TargetConfig.size_px` | `test_rows_7_to_12` | 🟩 |
| 11 | Initial target location | user-defined, default random | random; centre; "x,y" | `TargetConfig.start` | `test_rows_7_to_12` | 🟩 |
| 12 | Motion | at least line, circular, figure of 8, random; optional spiral, sinusoidal, user-defined | all six, user-defined waypoint path, static | `Target.state`, `Target._waypoints` | `test_targets_stay_on_screen_and_are_deterministic` (7 paths) | 🟩 |
| 13 | Max pan speed | 5 to 10 deg/s, default 5 | 5, editable | `CameraConfig.max_pan_rate_deg_s`, enforced in `Gimbal.apply` | `test_rows_13_to_15`, `test_gimbal_rate_and_pose_limits` | 🟩 |
| 14 | Max tilt speed | 5 to 10 deg/s, default 5 | 5, editable | same | same | 🟩 |
| 15 | Update interval | >= 20 Hz | commands every frame at 30 Hz | `Simulation.steps` | `test_rows_13_to_15` | 🟩 |
| 16 | Acquisition time | <= 2 s | 0.6 to 1.4 s measured (full view) | `metrics.summarise` | `test_closed_loop_clear_meets_spec`, batch envelope | 🟩 |
| 17 | Tracking error | <= 10 px | 6.6 to 7.3 px clear, noise, fog, low light | same | same | 🟩 (🟨 under 20 px/frame vibration the truth itself jumps; vibration-removed value also reported) |
| 18 | Target loss | < 5% | 0 to 2% on full-view scenarios | same | same | 🟩 |
| 19 | Re-acquisition time | <= 1 s | 0.07 to 0.4 s measured | same | `test_closed_loop_with_disturbance_keeps_lock` | 🟩 |
| 20 | Processing speed | >= 20 FPS | 65 to 250 FPS at 2000 x 2000 | same | all closed-loop tests | 🟩 |
| 21 | Image noise | salt and pepper (~10%), Gaussian, Poisson; one or more selectable | all three, independent switches | `DisturbanceModel.apply_image` | `test_rows_21_to_25`, `noisy_line.yaml` | 🟩 |
| 22 | Max standard deviation of noise | 20 px, user-defined | `gaussian_sigma` up to any value | `DisturbanceConfig.gaussian_sigma` | `test_rows_21_to_25` | 🟩 |
| 23 | Max camera jitter | +/- 20 px per frame, user-defined | `jitter_px`, applied to the whole picture | `DisturbanceModel.step` | `platform_jitter.yaml` | 🟩 |
| 24 | Atmospheric disturbance | Clear, Haze, Fog, Rain, Low light; user-defined reduction in contrast and brightness | five presets plus editable contrast, brightness, blur, turbulence | `ATMOSPHERE_PRESETS`, `apply_image` | `test_rows_21_to_25`, `fog_circular.yaml`, `lowlight_figure8.yaml` | 🟩 |
| 25 | Platform motion | +/- 20 px per frame max; linear mandatory; circular, random, spiral, figure of 8 optional | all five as bounded sways with the configured peak speed | `DisturbanceModel._platform` | `test_rows_21_to_25`, `platform_jitter.yaml`, `platform_max.yaml` | 🟩 |

## "The developed software shall be able to"

| Item | Implemented in | Seen in the GUI | Status |
|---|---|---|---|
| Generate a configurable virtual environment | `world/scene.py`, `ScreenConfig` | Screen section, scene view | 🟩 |
| Generate one or more moving targets | `world/targets.py` | Target section, Extra targets, trails | 🟩 |
| Implement a movable virtual camera | `world/camera.py` | cyan window moving on the scene view | 🟩 |
| Detect the target beacon automatically | `perception/detect.py` | green detection box | 🟩 |
| Track the beacon continuously using computer vision | `perception/estimator.py`, `control/tracker.py` | estimate cross, prediction, state | 🟩 |
| Control and reposition the virtual camera | `control/controller.py`, `Gimbal` | gimbal command plot, pan/tilt readout | 🟩 |
| Generate and introduce disturbances (turbulence, vibration, camera motion, noise) in the virtual camera feed | `world/disturbance.py` | Disturbances section | 🟩 |
| Display tracking performance and statistics in real time | `gui/app.py` tiles, plots, telemetry | whole window | 🟩 |

## Deliverables

| Deliverable | PS wording | Where | Status |
|---|---|---|---|
| Software application | standalone executable implementing the complete system | `fsoc_tracker.spec`, built by `.github/workflows/build.yml` for Windows x64, Linux x64, macOS Intel and macOS Apple silicon; each build runs the test suite and a packaged smoke test on its own platform; both macOS archives also exercised by hand (scenarios, video mode, GUI start) | 🟩 |
| Source code | complete, modular, adequately commented, documented | `fsoc_tracker/`, docstrings, `README.md`, `ARCHITECTURE.md` | 🟩 |
| Technical report | 10 to 15 pages: problem understanding, architecture, modules, tracking methods, AI methods, test methodology, performance analysis, future improvements | `docs/TECHNICAL_REPORT.md` and `.pdf`, performance table from the measured envelope | 🟩 |
| User manual | installation, operation, parameter configuration, GUI description | `docs/USER_MANUAL.md` and `.pdf`; also the User manual button and Help in the application | 🟩 |
| Demo video (optional) | 3 to 5 minutes | not produced; the web app at the project site lets an evaluator run every scenario live instead | ⬜ optional |
| Performance log | automatically generated: simulation duration, FPS, acquisition time, average and maximum tracking error, lock retention rate, processing time | `frames.csv`, `summary.json`, `report.pdf` written at the end of every run, each metric with its definition | 🟩 |

## Evaluation stages

| Stage | Marks | PS criteria | Our readiness | Status |
|---|---|---|---|---|
| Functional verification | 20 | implementation of all mandatory functions, operational success, GUI | all eight functions demonstrable live; scenario picker; live tiles | 🟩 |
| Benchmark performance 1 | 30 | execution of given scenarios; log of centroiding error; automatically generated performance logs | scenario YAML loads in one click; `centroid_err_px` per frame in `frames.csv`; report automatic | 🟩 (their file format may need a mapping) |
| Benchmark performance 2 | 30 | video files (.mp4 @30 fps) covering a complete screen with noise and moving beacon; bypass the PTZ camera; comparison of centroiding error with predefined values; RMSE, acquisition and re-acquisition time, lock retention, FPS | Open video: simulator bypassed, frames used as the scene, `det_x/det_y` per frame, timing and lock metrics in the report | 🟩 |
| Technical evaluation | 20 | understanding, architecture, algorithms, AI and CV, novelty, documentation, Q and A | `ARCHITECTURE.md`, `docs/TECHNICAL_REPORT.pdf` (14 pages), `docs/USER_MANUAL.pdf`, this file | 🟩 |

## Things the PS does not specify, and what we chose

| Question | Our choice | Why |
|---|---|---|
| Does the tracker see the whole screen or only the camera window? | Whole screen by default ("simulated video stream", "observe the surrounding environment"); a hard mode restricts it to the window | Blind search at 5 deg/s cannot meet 2 s acquisition for far corners |
| Screen pixels to degrees | one screen pixel = one camera pixel, so the screen is 12.5 deg wide | a setting; the only anchor the PS gives is 4 deg over 640 px |
| What "tracking error" and "centroiding error" mean | tracking: true beacon to window centre; centroiding: measured centre to true centre. Both logged with printed definitions | the PS uses both terms without defining them |
| What "lock" means | TRACK state with the estimate within 30 px of the window centre | acquisition needs a capture criterion |
| A sustained 20 px per frame platform shift | modelled as a bounded sway with that peak speed | a sustained shift leaves the screen in seconds |
| AI role | classical detector first; CNN fills gaps and handles faint beacons; trained on the simulator's exact labels | keeps FPS and reliability independent of the model |
