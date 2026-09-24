# Point-by-point compliance with the problem statement

Source of truth: `26169.pdf` (SIH26169, Department of Space / ISRO SAC). Every row of its
parameter table, every "shall" item, every deliverable and every evaluation stage is listed
here with where it is implemented and how it is verified. `tests/test_ps_compliance.py`
fails if any default is changed away from the PS. `tools/ps_audit.py` measures every row, "shall"
item, deliverable and benchmark by running the code and writes `docs/PS_AUDIT.md` (39 of 39 pass on
2026-09-23); the build runs it on the Linux job and fails if any check fails.

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
| 8 | Number of targets | 1 mandatory, multiple optional | 1; N named targets via list or "Extra targets" (optionally identical look); all detected, the designated one followed and scored; designation by appearance, start cue or point (click or typed) | `RunConfig.targets/designated/designation/designation_cue`, `TargetConfig.name`, `Tracker` | `test_rows_7_to_12`, `test_multi_target_identity_held`, `test_many_decoys_from_the_panel_track_the_designated_beacon`, `test_designated_target_is_the_one_scored`, `test_identical_decoys_need_a_cue`, `decoys_identical.yaml` | 🟩 |
| 9 | Target shape | user-defined, default square | square; circle, gaussian, cross, ring, diamond, custom (0/1 mask or PNG) | `TargetConfig.shape/mask`, `world/sprites.py` | `test_rows_7_to_12`, `test_width_and_height_separate`, `beacon_shapes.yaml` | 🟩 |
| 10 | Target size | 5-20 x 5-20 px, default 10 x 10 | 10 x 10; width and height editable separately | `TargetConfig.size_px/height_px` | `test_rows_7_to_12`, `test_width_and_height_separate` | 🟩 |
| 11 | Initial target location | user-defined, default random | random; centre; "x,y" typed in the panel or the file | `TargetConfig.start` | `test_rows_7_to_12`, `test_user_defined_start` | 🟩 |
| 12 | Motion | at least line, circular, figure of 8, random; optional spiral, sinusoidal, user-defined | all six, user-defined waypoint path, static | `Target.state`, `Target._waypoints` | `test_targets_stay_on_screen_and_are_deterministic` (7 paths) | 🟩 |
| 13 | Max pan speed | 5 to 10 deg/s, default 5 | 5, editable | `CameraConfig.max_pan_rate_deg_s`, enforced in `Gimbal.apply` | `test_rows_13_to_15`, `test_gimbal_rate_and_pose_limits` | 🟩 |
| 14 | Max tilt speed | 5 to 10 deg/s, default 5 | 5, editable | same | same | 🟩 |
| 15 | Update interval | >= 20 Hz | commands every frame at 30 Hz | `Simulation.steps` | `test_rows_13_to_15` | 🟩 |
| 16 | Acquisition time | <= 2 s | 0.60 to 1.57 s measured on clear, noise, fog and low light (full view); faint beacon 0.80 to 2.00 s over 10 seeds | `metrics.summarise` | `test_closed_loop_clear_meets_spec`, batch envelope | 🟩 |
| 17 | Tracking error | <= 10 px | 2.1 to 3.7 px clear line, circle and figure 8; 5.1 to 6.3 px random walk; 2.4 to 3.7 px heavy noise; 2.5 to 3.7 px fog and low light; 4.6 to 5.3 px on a 450 px circle at 4 deg/s (lead capped by the path's turn); a still beacon held within 4 px (no derivative term, which drove a +/-10 px limit cycle) | same, `Controller.TURN_MAX` | same, `fast_circular.yaml`, `test_review_fixes.py` | 🟩 (🟨 under 20 px/frame vibration the truth itself jumps; vibration-removed value also reported) |
| 18 | Target loss | < 5% | 0% on clear, noise, fog, low light and the fast circle (lock 100%); faint beacon lock 94.0 to 97.8% over 10 seeds (seeds 7 and 8 at 94.8 and 94.0%, just above the limit); a coasting estimate more than 160 px outside the picture falls back to a whole-scene search | same, `Tracker` | same, `test_review_fixes.py` | 🟩 |
| 19 | Re-acquisition time | <= 1 s | 0.07 to 0.4 s measured | same | `test_closed_loop_with_disturbance_keeps_lock` | 🟩 |
| 20 | Processing speed | >= 20 FPS | 69 to 216 FPS at 2000 x 2000 over the 16-scenario pack (2026-09-23 batch); `fps_mean` is frames over processing time (1000 / mean ms), the mean of per-frame rates is kept as `fps_inst_mean` for comparison only | same | all closed-loop tests, `test_review_fixes.py` | 🟩 |
| 21 | Image noise | salt and pepper (~10%), Gaussian, Poisson; one or more selectable | all three, independent switches; salt and pepper shown in percent on both panels, stored as a fraction; inputs clamped, above 10% flagged by the scenario check | `DisturbanceModel.apply_image`, `engine/checks.py` | `test_rows_21_to_25`, `test_salt_and_pepper_shown_in_percent`, `test_scenario_check_clamps_and_warns`, `noisy_line.yaml` | 🟩 |
| 22 | Max standard deviation of noise | 20 px, user-defined | `gaussian_sigma` up to any value | `DisturbanceConfig.gaussian_sigma` | `test_rows_21_to_25` | 🟩 |
| 23 | Max camera jitter | +/- 20 px per frame, user-defined | `jitter_px`, applied to the whole picture | `DisturbanceModel.step` | `platform_jitter.yaml` | 🟩 |
| 24 | Atmospheric disturbance | Clear, Haze, Fog, Rain, Low light; user-defined reduction in contrast and brightness | five presets plus editable contrast, brightness, blur, turbulence | `ATMOSPHERE_PRESETS`, `apply_image` | `test_rows_21_to_25`, `fog_circular.yaml`, `lowlight_figure8.yaml` | 🟩 |
| 25 | Platform motion | +/- 20 px per frame max; linear mandatory; circular, random, spiral, figure of 8 optional | all five as bounded sways with the configured peak speed; the figure 8 is scaled so its peak equals the setting (it peaked at 28.3 px/frame at a 20 setting before 2026-09-23); the PS audit measures the peak of every pattern, never above 20 | `DisturbanceModel._platform` | `test_rows_21_to_25`, `platform_jitter.yaml`, `platform_max.yaml` | 🟩 |

## "The developed software shall be able to"

| Item | Implemented in | Seen in the GUI | Status |
|---|---|---|---|
| Generate a configurable virtual environment | `world/scene.py`, `ScreenConfig` | Screen section, scene view | 🟩 |
| Generate one or more moving targets | `world/targets.py` | Target section, Extra targets, trails | 🟩 |
| Implement a movable virtual camera | `world/camera.py` | cyan window moving on the scene view | 🟩 |
| Detect the target beacon automatically | `perception/detect.py` | green detection box | 🟩 |
| Track the beacon continuously using computer vision | `perception/estimator.py`, `control/tracker.py` | estimate cross, prediction, state | 🟩 |
| Control and reposition the virtual camera | `control/controller.py`, `Gimbal` | gimbal command plot, pan/tilt readout | 🟩 |
| Generate and introduce disturbances (turbulence, vibration, camera motion, noise) in the virtual camera feed | `world/disturbance.py`; changes during a run: `DisturbanceModel.update`, `Simulation.request_disturbance`, scenario `schedule` | Disturbances section, live while a run is going; changes marked on the plots and in the report | 🟩 |
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
| Benchmark performance 2 | 30 | video files (.mp4 @30 fps) covering a complete screen with noise and moving beacon; bypass the PTZ camera; comparison of centroiding error with predefined values; RMSE, acquisition and re-acquisition time, lock retention, FPS | Open video: simulator bypassed, frames used as the scene, `det_x/det_y` per frame, timing and lock metrics in the report. With the evaluators' positions as a truth CSV (`--truth`, Truth CSV button, or `<video>_truth.csv` beside the video), tracking error, centroiding error, RMSE and true lock retention are computed against them | 🟩 |
| Technical evaluation | 20 | understanding, architecture, algorithms, AI and CV, novelty, documentation, Q and A | `ARCHITECTURE.md`, `docs/TECHNICAL_REPORT.pdf` (13 pages), `docs/USER_MANUAL.pdf`, this file | 🟩 |

## Things the PS does not specify, and what we chose

| Question | Our choice | Why |
|---|---|---|
| Does the tracker see the whole screen or only the camera window? | Whole screen by default ("simulated video stream", "observe the surrounding environment"); a hard mode restricts it to the window | Blind search at 5 deg/s cannot meet 2 s acquisition for far corners |
| Screen pixels to degrees | one screen pixel = one camera pixel, so the screen is 12.5 deg wide | a setting; the only anchor the PS gives is 4 deg over 640 px |
| What "tracking error" and "centroiding error" mean | tracking: true beacon to window centre; centroiding: measured centre to true centre. Both logged with printed definitions | the PS uses both terms without defining them |
| What "lock" means | TRACK state with the estimate within 30 px of the window centre | acquisition needs a capture criterion |
| How the "designated" target is designated | appearance (default), start cue or point cue (click or typed); tracking every beacon at once not built | the PS says "a designated moving target" but not how; its metrics are for one target |
| A sustained 20 px per frame platform shift | modelled as a bounded sway with that peak speed | a sustained shift leaves the screen in seconds |
| AI role | classical detector first; CNN fills gaps (not on a faint track, which has its own track-before-detect); trained on the simulator's exact labels; it supplies 0% of measurements in the standard scenarios | keeps FPS and reliability independent of the model |
