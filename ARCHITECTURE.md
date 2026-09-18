# AI-Based Virtual Camera Tracking System for Coarse Alignment of Mobile FSOC Terminals

Solution architecture for SIH Problem Statement 26169 (Department of Space / ISRO, Space Applications Centre).
Mentors: Pranav Kumar Pandey (pranavpandey@sac.isro.gov.in), Koushik Basak (koushik@sac.isro.gov.in), Abhishek Khanna (akn@sac.isro.gov.in).

This document is the design baseline for the code, the technical report, and the user manual. The implementation lives in `fsoc_tracker/`; where a constant below differs from the code, the code and `context.md` (Decisions) are current. Notable settled values: PID kp 5 / kd 0.3 / ki 0.8, feedforward 1.0 with acceleration lead 0.25 s, IMM process noise sqrt(q) = 32 / 200 / 71 px/s^2, capture radius 30 px, jitter cap 25 px, signature threshold 1.1, platform sway amplitude <= 20% of screen.

---

## 1. Reading the problem statement correctly

The winning solution depends on a few interpretations that most teams will get wrong.

### 1.0 What is being built, in one paragraph

Two deliverable halves in one application. A **simulator** that generates a configurable scene (screen >= 2000 x 2000 px), one or more moving beacons, a rate-limited virtual pan-tilt camera (640 x 480, 4° x 3°, start at centre), and the full disturbance set, producing the "virtual camera feed". And a **tracker** that consumes that feed, detects the beacon, measures its centroid, predicts its motion and steers the camera, meeting rows 16 to 20. The simulator is mandatory in its own right (the first four "shall be able to" items and parameter rows 1 to 15), is the only way to run Benchmark-1 scenarios (settings, not footage), is the sole source of test data and labelled training data during development, and is the only place ground truth exists. Benchmark-2 substitutes the evaluators' .mp4 for the simulator's output and tests the tracker alone.

### 1.1 What the tracker observes, and what it controls

The problem statement describes "detecting and continuously tracking a moving optical beacon in a **simulated video stream** while controlling a virtual pan-tilt camera", lists "Observe the surrounding environment" as the first step of coarse alignment, and in Benchmark-2 feeds a video "covering a complete screen" straight into the coarse pointing system. Read together:

- The tracker's input is the whole scene (the screen, >= 2000 x 2000 px, monochrome, 30 Hz) with disturbances applied. This is the "virtual camera feed".
- The 640 x 480 camera window (4° x 3° FOV) is the controlled output. It represents where the FSOC terminal is pointing. The task is to bring the beacon inside it quickly and hold it near the centre under the pan/tilt rate limits.
- Tracking error = distance from the true beacon position to the window centre. Centroiding error = distance from our measured centroid to the true centroid.

A **hard mode** setting restricts the tracker's input to the pixels inside the window, forcing a spiral search for acquisition. It exists for algorithm stress testing and is off by default.

| Item | Value | Derived quantity |
|---|---|---|
| Screen (scene) | 2000 x 2000 px | 12.5° x 12.5° under the 1 screen px = 1 window px assumption |
| Camera window | 640 x 480 px, 4° x 3° | IFOV = 0.00625 °/px = 22.5 arcsec/px |
| Tracking error spec | <= 10 px | 0.0625° = 225 arcsec |
| Max pan/tilt speed | 5 to 10 °/s | 26.7 to 53.3 px/frame at 30 Hz |
| Platform motion | +/- 20 px/frame max | up to 75% of the 5 °/s slew budget |
| Camera jitter | +/- 20 px/frame max | zero-mean, not to be chased |
| Windows per screen | ~13 | (2000/640) x (2000/480) |
| Centre to corner slew, target known | 0.95 s | max(4.25°, 4.75°) / 5 °/s, both axes moving together |

Consequences:

1. Acquisition <= 2 s is met from any start position because detection runs on the full scene: a few frames to detect and confirm, then <= 0.95 s of slew. In hard mode a blind spiral over ~13 window areas cannot meet 2 s for far corners; the log reports the true time.
2. The window is rate limited. Placing it on the detection each frame is not permitted and would limit-cycle under +/- 20 px/frame disturbance. The controller commands a rate, uses the predicted target position as feedforward, and saturates at the limit.
3. Jitter is zero-mean at frame rate; the estimator smooths it and the controller follows the smoothed position. Frame-to-frame global shift of the scene is measured and fed forward as platform-drift rejection.
4. Only the window region needs full-fidelity rendering for display; detection on the full scene uses the classical path at full resolution and the CNN on a region of interest around the predicted position once locked.

### 1.2 Two error terms in the PS, both logged

- Tracking error (PS rows 17 and the performance log): distance in px and degrees from the true beacon position to the camera window centre. This is what the control loop minimises.
- Centroiding error (PS Benchmark-1 and Benchmark-2 criteria): distance from our measured centroid to the true centroid. This is detection accuracy, and it is what the evaluators compare against their reference values.

The PS does not define either term formally. Both are logged per frame under their PS names with a printed one-line definition, so whichever an evaluator means, the number and its meaning are on the page.

### 1.3 Benchmark-2 is 30% of the marks and needs a source abstraction

"Video files (.mp4) @30 fps covering a complete screen with noise and moving beacon spot. The software needs to bypass its PTZ camera and take this video as an input to the coarse pointing system."

One reading: the video replaces the simulated scene. `FrameSource` yields each video frame as the scene picture; the scene maker and disturbance stages are skipped; detection, centroiding, estimation, state machine and window control run unchanged; the window is drawn over the video for display. Outputs are the per-frame centroid (compared by the evaluators against their reference values), RMSE, acquisition and re-acquisition time, lock retention rate and FPS, on the same CSV and PDF path as synthetic runs. Frame size is arbitrary; timestamps are frame-index accurate.

### 1.4 Rubric weights drive the build order

| Stage | Marks | What wins it |
|---|---|---|
| Functional verification | 20 | every mandatory function visibly working in a polished GUI within 10 to 15 min |
| Benchmark-1 (given scenarios) | 30 | scenarios are simulator settings; they load in one click, our simulator runs them, centroid log and auto report generated, low RMSE |
| Benchmark-2 (given videos) | 30 | .mp4 replaces the simulator output and tests the tracker alone; ingest works first time, centroiding accuracy, acquisition and re-acquisition timing, FPS |
| Technical evaluation | 20 | aerospace-correct vocabulary: IFOV, IMM, innovation gating, Rytov variance, slew saturation, latency compensation |

---

## 2. Solution overview

A deterministic, physically grounded digital twin of a coarse-pointing loop:

- World layer models the scene, targets, and camera window in angular coordinates, renders the full scene picture that the tracker observes, and applies disturbances in the physical order in which they occur.
- Perception layer runs a three-tier detector (classical sub-pixel centroid, ONNX heatmap CNN, designated-target identity), associates detections with an Interacting Multiple Model (IMM) estimator, and produces a filtered, predicted target state.
- Control layer is a mode state machine (SEARCH, VERIFY, TRACK, COAST, REACQUIRE) driving a feedforward plus PID rate controller with slew and acceleration saturation, anti-windup, latency compensation, and ego-motion rejection, acting on a gimbal model.
- Instrumentation layer publishes every internal quantity onto a telemetry bus, logs CSV at frame rate, computes rubric metrics with explicit definitions, and generates a PDF/HTML report automatically at the end of every run.
- Presentation layer is a PyQt6 console with world view, camera view with HUD, live plots, and a full parameter panel covering every row of the PS parameter table.
- The same engine runs headless from a CLI for batch scenario sweeps and for .mp4 ingest.

---

## 3. Unique selling points

1. Physics-first channel model, not cosmetic filters. Kolmogorov tip/tilt beam wander as an AR(2) process, log-normal scintillation with configurable Rytov variance, PSF broadening by r0, Beer-Lambert extinction with airlight for haze/fog/rain, Poisson shot noise plus Gaussian read noise plus salt-and-pepper at the detector. Disturbances are applied in physical order. Platform motion and jitter perturb the camera pose, so the controller really has to fight them.

2. Sub-pixel centroiding in the star-tracker tradition. Intensity-weighted centre of gravity on a thresholded, background-subtracted blob, refined by 2D Gaussian PSF fit. Target centroiding error below 0.1 px in clear conditions, measured against ground truth and reported. This is the exact quantity ISRO scores.

3. IMM estimator matched to the listed motion classes. Constant Velocity, Constant Acceleration, and Coordinated Turn models with Markov switching handle straight line, circular, figure of 8, spiral, sinusoidal, and random motion without retuning. Innovation covariance drives Mahalanobis gating for clutter rejection and multi-target identity.

4. Predictive re-acquisition. On detection loss the loop enters COAST, propagates the IMM state, points the camera at the prediction, and searches an expanding spiral sized by the prediction covariance ellipse. This is how the <= 1 s re-acquisition spec is met deterministically rather than by luck.

5. Ego-motion rejection. Frame-to-frame global shift from phase correlation on the background is fed forward as a disturbance estimate. The controller cancels platform motion and jitter directly instead of waiting for it to show up as target error. Lock retention under +/- 20 px/frame disturbance improves measurably and the improvement is plotted in the report.

6. Control law that respects the gimbal. Angular error from IFOV, feedforward from IMM target angular rate, PID on the residual, slew-rate and acceleration limits, integrator clamping under saturation, capture-zone deadband, pipeline-latency compensation, and a configurable notch at the platform vibration frequency. Slew saturation percentage is logged and displayed live.

7. AI that never holds the loop hostage. A ~200k parameter fully convolutional heatmap network, trained entirely on frames rendered by our own simulator with perfect labels and domain randomisation, exported to ONNX and run on CPU in under 5 ms at 320 x 240. It is the low-SNR and clutter path; the classical centroid remains the fast path and fallback so FPS and reliability never depend on the model. Soft-argmax on the heatmap gives sub-pixel output from the CNN too.

8. Designated-target identity with multiple beacons. The PS says "detects, identifies, and continuously tracks a designated moving target". With several targets, identity is maintained through crossings by IMM gating plus a lightweight appearance and temporal signature vector, with global nearest neighbour assignment. Designation is by scenario config or by clicking in the camera view.

9. Deterministic, reproducible, batchable. Every run is a (scenario YAML, seed) pair. The headless runner sweeps hundreds of scenario-seed combinations and produces an envelope report. The team can state measured performance across the full disturbance space rather than a single demo.

10. Auto-generated performance report with defined metrics. Simulation duration, mean/p95/min FPS, acquisition time, each re-acquisition time, mean/max/RMSE pointing error, mean/max/RMSE centroiding error, lock retention rate, target loss percentage, processing time mean/p99, slew saturation percentage, and plots. Every metric has a one-line definition printed in the report so evaluators cannot dispute what was measured.

11. Video ingest for Benchmark-2 that replaces the simulated scene with the evaluators' frames, resolution-agnostic, frame-index-accurate, on the same logging path as synthetic runs.

12. Evaluator-grade GUI. World view with FOV rectangle and trails, camera view with boresight, detection box, centroid, prediction, gate ellipse and mode banner, live plots of pointing error, centroiding error, FPS, processing time, slew command with saturation band, and mode timeline. Dark console aesthetic, monospace telemetry, no emojis.

---

## 4. Architecture

### 4.1 Layer diagram

```
+------------------------------------------------------------------------------+
| PRESENTATION      PyQt6 console: WorldView | CameraView+HUD | LivePlots       |
|                   ParameterPanel (every PS row) | ScenarioLoader | ReportBtn   |
+-------------------------------------^----------------------------------------+
                                      | Qt signals (telemetry snapshot, frames)
+-------------------------------------v----------------------------------------+
| INSTRUMENTATION   TelemetryBus (pub/sub) -> CsvLogger, MetricsEngine,         |
|                   ReportGenerator (PDF/HTML), ScenarioRunner (batch, seeds)   |
+-------------------------------------^----------------------------------------+
                                      | per-frame records
+-------------------------------------v----------------------------------------+
| ORCHESTRATION     SimulationEngine: fixed-step clock (30 Hz render,           |
|                   >= 20 Hz control), deterministic RNG streams, pause/step    |
+-------^------------------------------------------------------^---------------+
        |                                                      |
+-------v-----------------+   +--------------------------+   +-v----------------+
| WORLD                   |   | PERCEPTION               |   | CONTROL          |
| SceneModel (angular)    |   | FrameSource (abstract)   |   | ModeFSM          |
| TargetKinematics x N    |-->|  SyntheticSceneSource    |-->| SearchPlanner    |
| CameraOpticalModel      |   |  VideoFileSource         |   | Guidance         |
| DisturbanceChannel      |   | Preprocess               |   | FF+PID RateCtrl  |
|  atmosphere, turbulence,|   | Detector tiers 1..3      |   | SlewLimiter      |
|  platform pose, sensor  |   | SubPixelCentroid         |   | LatencyComp      |
| ViewportRenderer        |<--| Associator (gating)      |   | EgoMotionFF      |
| GimbalModel             |   | IMMEstimator             |   | NotchFilter      |
+-------------------------+   +--------------------------+   +------------------+
        ^                                                              |
        +-------------------- pan/tilt rate command ------------------+
```

### 4.2 Closed-loop data flow (one tick)

```
t_k
 1. SimulationEngine advances TargetKinematics(t_k) and PlatformMotion(t_k)
 2. GimbalModel integrates last rate command -> camera pose (az, el) + platform pose offset
 3. ViewportRenderer projects targets into camera frame using IFOV, applies
    DisturbanceChannel in order:
       radiance -> extinction/airlight -> turbulence (wander, scintillation, blur)
       -> optics PSF and vignetting -> detector (shot, read, FPN, ADC, salt&pepper)
    -> 640x480 uint8 frame + ground truth (true centroid in camera px, visibility flag)
 4. FrameSource yields (frame, timestamp, truth|None)
 5. Preprocess: background estimate, normalisation, optional denoise
 6. Detector:
       Tier 1 classical: adaptive threshold -> connected components -> candidates
       Tier 2 CNN (if Tier 1 confidence low or clutter high): heatmap -> peaks
       Tier 3 identity: assign candidates to designated track via gating + signature
 7. SubPixelCentroid: CoG + Gaussian fit -> (u, v, sigma, snr, confidence)
 8. IMMEstimator: predict to t_k, gate, update -> state (az, el, rates, accel), covariance
 9. ModeFSM decides SEARCH | VERIFY | TRACK | COAST | REACQUIRE
10. Guidance computes desired boresight: measured centroid (TRACK), IMM prediction (COAST),
    SearchPlanner waypoint (SEARCH/REACQUIRE)
11. RateController: e_ang = (centroid - principal_point) * IFOV
       u = FF(target_rate) + FF(-ego_motion) + PID(e_ang, latency-compensated)
       u -> notch -> accel limit -> slew limit (5..10 °/s) -> integrator clamp
12. Command stored for GimbalModel at t_{k+1}
13. TelemetryBus.publish(record_k) -> CsvLogger, MetricsEngine, GUI
```

### 4.3 Module contracts

```python
class FrameSource(Protocol):
    def next(self) -> Frame | None: ...        # Frame(image, t, truth: Truth | None, meta)
    def fps(self) -> float: ...
    def mode(self) -> Literal["synthetic", "video_direct", "video_screen"]: ...

class Detector(Protocol):
    def detect(self, frame: np.ndarray, prior: TrackPrior | None) -> list[Candidate]: ...

class Estimator(Protocol):
    def predict(self, dt: float) -> State: ...
    def update(self, z: Measurement) -> State: ...
    def gate(self, z: Measurement) -> float: ...   # Mahalanobis distance

class Controller(Protocol):
    def step(self, ctx: ControlContext) -> RateCommand: ...   # az_rate, el_rate, saturated flags

class Gimbal(Protocol):
    def apply(self, cmd: RateCommand, dt: float) -> Pose: ...
```

Every module is constructed from a typed config dataclass loaded from YAML, so the GUI panel, the CLI, and the tests share one configuration path.

---

## 5. Component breakdown

### 5.1 World: virtual environment generator

- Coordinate frame: azimuth/elevation in degrees. Screen bounds default 12.5° x 12.5° (2000 x 2000 px at IFOV 0.00625). Screen size, camera resolution, and FOV are all user-defined; IFOV is derived.
- Background presets: deep space starfield (Poisson-distributed point sources with magnitude distribution), terrestrial texture (procedural noise), uniform sky gradient, user image. Background is generated once per scenario as a world-space tile pyramid and sampled per viewport.
- Optional clutter: static false lights and moving decoys for identity testing.
- Camera type: monochrome primary, colour optional (renders three channels, perception uses luminance).

### 5.2 World: target generator

- One mandatory beacon, N optional. Shape: square (default), circle, Gaussian spot, user sprite. Size 5 to 20 px, default 10 x 10, user-defined intensity and optional temporal intensity profile.
- Motion library: straight line, circular, figure of 8, random walk (mandatory four), plus spiral, sinusoidal, waypoint list, user expression. Parameterised by speed, radius, period, phase, start position (random by default). Motion is defined in world angular coordinates so it is independent of camera pose.
- Ground truth per frame: true world position, true camera-frame centroid, in-FOV flag, occlusion flag.

### 5.3 World: camera optical model and gimbal

- The camera window is a 640 x 480 region of the scene at IFOV = FOV / resolution; pinhole projection with principal point and optional distortion when rendering the window view for display.
- PSF: Gaussian (default) or Airy; sigma configurable; broadened by turbulence.
- Gimbal: two-axis rate-driven model with max rate (5 to 10 °/s per axis), max acceleration, optional backlash and command latency. Update interval >= 20 Hz. Initial pose: screen centre.

### 5.4 World: disturbance channel (applied in physical order)

| Stage | Model | PS parameter |
|---|---|---|
| Extinction and airlight | Beer-Lambert attenuation by visibility class; airlight raises floor and lowers contrast | Clear, Haze, Fog, Rain, Low light; user-defined contrast and brightness reduction |
| Beam wander / angle of arrival | AR(2) process with Kolmogorov-shaped PSD; variance from configurable r0 or Cn2 | atmospheric turbulence |
| Scintillation | log-normal irradiance, Rytov variance configurable, temporal correlation | atmospheric turbulence |
| PSF broadening | sigma_eff = sqrt(sigma_optics^2 + (k * lambda/r0)^2) | atmospheric turbulence |
| Platform motion | pose offset trajectory: linear (mandatory), circular, random, spiral, figure of 8; up to +/- 20 px/frame | Platform motion |
| Camera jitter | band-limited noise with configurable resonant peaks, up to +/- 20 px/frame, applied to pose | Max camera jitter |
| Detector noise | Poisson shot noise, Gaussian read noise (sigma up to 20 px-equivalent as specified), fixed pattern, hot pixels, ADC quantisation, salt and pepper (default 10%) | Image noise, Max std dev of noise |

All stages are individually toggleable and seeded. The order is fixed and documented in the report.

### 5.5 Perception: detection and tracking engine

Tier 1, classical (always on, ~1 to 2 ms):
- Background estimation by median or morphological opening; subtraction.
- Adaptive threshold (mean + k * sigma, k tuned by estimated SNR); optional matched filter with the expected PSF.
- Connected components with size, aspect, and compactness filters. Salt-and-pepper rejection by minimum area and median prefilter.
- Candidates with area, peak, SNR.

Tier 2, learned (engaged when Tier 1 confidence is low, SNR is low, or clutter count is high; ~3 to 5 ms CPU):
- Fully convolutional heatmap regressor, ~200k parameters, input 320 x 240 downsample, output beacon likelihood map.
- Trained on simulator output with perfect labels and domain randomisation over every disturbance parameter. Loss: focal on heatmap plus L1 on offset head.
- Peaks extracted by NMS; soft-argmax for sub-pixel refinement; mapped back to full resolution.
- Exported to ONNX, run via ONNX Runtime CPU. Model file < 1 MB.

Tier 3, identity:
- Signature vector per candidate: size, peak intensity, PSF sigma, temporal intensity profile over last M frames, motion consistency with the designated IMM track.
- Mahalanobis gating against IMM innovation covariance; global nearest neighbour assignment; track confirmation N-of-M; tentative tracks for undesignated targets.

Sub-pixel centroid:
- Intensity-weighted centre of gravity within the gated window after background subtraction.
- 2D Gaussian least-squares fit for refinement; falls back to CoG if fit diverges.
- Outputs centroid, sigma, SNR, confidence; centroiding error logged against truth when available.

IMM estimator:
- Models: CV, CA, Coordinated Turn (positive and negative). Markov transition matrix configurable.
- State in angular world coordinates so camera motion does not corrupt target dynamics; measurement converted from camera px via current pose and IFOV.
- Outputs fused state and covariance; model probabilities displayed in GUI.

Ego-motion estimator:
- Phase correlation on background between consecutive frames (target region masked). Produces global shift estimate and confidence. Disabled automatically when background is featureless.

### 5.6 Control: camera controller

Mode FSM:
- SEARCH: no track. Detection runs on the full scene; the first confirmed candidate seeds the track and the window slews to it. In hard mode SearchPlanner emits an outward spiral of waypoints spaced by ~80% FOV overlap.
- VERIFY: candidate found; require N-of-M consistent detections (default 3 of 4) before declaring lock. Prevents noise spikes from being counted as acquisition.
- TRACK: closed loop on measured centroid with IMM smoothing.
- COAST: detection lost; point at IMM prediction; covariance grows; timeout configurable.
- REACQUIRE: expanding spiral centred on the prediction, radius from covariance ellipse; returns to TRACK on VERIFY success or to SEARCH on timeout.

Rate controller:
- e_ang = (centroid_px - principal_point_px) * IFOV, per axis.
- u = k_ff * omega_target_hat - k_ego * omega_platform_hat + PID(e_ang).
- Latency compensation: PID acts on IMM state predicted forward by the measured pipeline latency tau.
- Deadband inside a capture radius (default 2 px) to stop jitter chasing.
- Notch at configured vibration frequency; second-order low-pass on derivative term.
- Acceleration limit then rate limit (5 to 10 °/s); integrator clamped while saturated.
- Gain scheduling keyed on mode and on estimated disturbance level (innovation covariance trace).

### 5.7 Instrumentation: performance monitor and report

Per-frame CSV columns (subset): frame, t_sim, t_wall, proc_ms, fps_inst, mode, lock, cam_az, cam_el, cmd_az_rate, cmd_el_rate, sat_az, sat_el, true_u, true_v, det_u, det_v, centroid_err_px, pointing_err_px, pointing_err_deg, snr, confidence, tier_used, n_candidates, imm_p_cv, imm_p_ca, imm_p_ct, ego_dx, ego_dy.

Summary metrics with printed definitions:
- Simulation duration (s), frames.
- FPS mean, p5, min. Processing time mean, p99, max (ms).
- Acquisition time: first lock declaration from t = 0.
- Re-acquisition times: each COAST/REACQUIRE to TRACK interval; mean and max.
- Pointing error mean, max, RMSE (px and deg) over TRACK frames.
- Centroiding error mean, max, RMSE (px) when truth exists.
- Lock retention rate: TRACK frames / frames after first acquisition.
- Target loss: 1 minus lock retention, compared against < 5%.
- Slew saturation percentage per axis.
- Pass/fail against the PS performance table (rows 16 to 20).

Report: PDF and HTML with the metrics table, spec compliance table, time-series plots, error histogram, mode timeline, scenario parameters, seed, software version, and machine info. Generated automatically at run end and on demand.

Batch runner: `fsoc-tracker run --scenario configs/scenarios/*.yaml --seeds 0..49 --out results/` produces per-run reports plus an aggregate envelope table.

### 5.8 Presentation: GUI

- World view: downscaled 2000 x 2000 screen, camera FOV rectangle, target trails, camera trail, search spiral overlay in SEARCH mode.
- Camera view: live 640 x 480 with HUD: boresight crosshair, capture radius ring, detection box, sub-pixel centroid marker, IMM prediction marker, gate ellipse, mode banner, lock indicator, SNR and confidence readouts.
- Live plots (pyqtgraph): pointing error, centroiding error, FPS and processing time, rate command with saturation bands, IMM model probabilities, mode timeline.
- Parameter panel: one control per PS parameter row, grouped as Camera, Target, Camera Motion Constraints, Disturbances, Perception, Control. Presets for Clear, Haze, Fog, Rain, Low light. Load and save scenario YAML.
- Transport: start, pause, single step, reset, record video, export report. Open-video dialog for Benchmark-2 runs.
- Style: dark console, monospace telemetry, SVG icons, no emojis, keyboard shortcuts documented in the manual.

---

## 6. Implementation plan

Stack: Python 3.11, NumPy, OpenCV, SciPy, Numba, PyTorch (training only), ONNX Runtime, PyQt6, pyqtgraph, PyYAML with schema validation, ReportLab or WeasyPrint for PDF, pytest, PyInstaller. Repository layout:

```
fsoc_tracker/
  world/        scene.py targets.py camera.py gimbal.py disturbance/ renderer.py
  perception/   sources.py preprocess.py detect_classical.py detect_cnn.py identity.py centroid.py imm.py egomotion.py
  control/      fsm.py search.py controller.py filters.py
  engine/       simulation.py telemetry.py metrics.py report.py runner.py
  gui/          app.py views/ panels/ theme/
  cli.py
configs/scenarios/   presets and benchmark scenarios
training/            data generation, train.py, export_onnx.py
tests/               unit and closed-loop regression
docs/                technical report, user manual sources
```

Milestones:

| M | Scope | Exit criterion |
|---|---|---|
| M0 | Scaffold, config schema, RNG streams, telemetry bus, `VideoFileSource`, CI | `pytest` green; `fsoc-tracker run --video x.mp4` produces a CSV |
| M1 | World: scene, targets (4 mandatory motions), camera model, viewport renderer, gimbal | Headless run renders 30 Hz frames with truth; unit tests on projection and IFOV |
| M2 | Tier 1 detector, sub-pixel centroid, CV Kalman, PID with slew limit, TRACK mode only | Clear-sky straight-line scenario meets <= 10 px pointing error, centroiding error < 0.2 px |
| M3 | Full FSM with spiral search, VERIFY, COAST, REACQUIRE; acquisition and re-acquisition metrics | Random start meets <= 2 s acquisition; forced dropout meets <= 1 s re-acquisition |
| M4 | Disturbance channel complete and ordered; noise presets; platform and jitter on pose | All PS disturbance rows configurable; regression suite records baseline metrics |
| M5 | IMM (CV, CA, CT), ego-motion feedforward, latency compensation, notch, gain scheduling | Lock retention > 95% on all six motion types at +/- 20 px/frame disturbance |
| M6 | CNN: data generator, training, ONNX export, Tier 2 integration, Tier 3 identity, multi-target | Low-light and fog scenarios where Tier 1 fails alone pass with Tier 2; identity holds through crossings |
| M7 | Report generator; batch runner and envelope report | Every run ends with a PDF; 50-seed sweep runs unattended |
| M8 | GUI complete, parameter panel, presets, HUD, live plots; PyInstaller builds for Windows and Linux | Fresh laptop runs the executable at >= 20 FPS; 10-minute demo script rehearsed |
| M9 | Technical report (10 to 15 pages), user manual, demo video, final regression | All deliverables in `dist/` and `docs/` |

Integration order is chosen so a closed-loop demo exists at M2 and every later milestone adds a measured improvement recorded in the regression suite; the report's performance section is written from those numbers.

Performance budget at 640 x 480, CPU only: render <= 2 ms, preprocess and Tier 1 <= 2 ms, Tier 2 when engaged <= 5 ms, IMM and control < 0.2 ms, telemetry < 0.5 ms, GUI on a separate thread. Target <= 15 ms per frame, giving >= 60 FPS headroom against the 20 FPS spec.

Testing: unit tests for projection, IFOV, centroid accuracy against synthetic Gaussians, IMM consistency (NEES), slew limiter; closed-loop regression scenarios with stored baseline metrics and tolerance; a Benchmark-1 style scenario pack and a Benchmark-2 style video pack generated by our own renderer for rehearsal.

---

## 7. Compliance checklist

### 7.1 Required capabilities

| Requirement | Module | Evidence in GUI or log |
|---|---|---|
| Configurable virtual environment | world.scene, configs | Parameter panel, scenario YAML |
| One or more moving targets | world.targets | Target list, world view trails |
| Movable virtual camera | world.camera, world.gimbal | FOV rectangle, cam_az/cam_el columns |
| Automatic beacon detection | perception.detect_classical, detect_cnn | Detection box, tier_used column |
| Continuous CV tracking | perception.centroid, imm, identity | Centroid and prediction markers |
| Camera control and repositioning | control.fsm, controller, search | Rate command plot, mode banner |
| Disturbances: turbulence, vibration, camera motion, noise | world.disturbance | Disturbance panel, per-stage toggles |
| Real-time performance display | gui.views, engine.metrics | Live plots, status bar |

### 7.2 PS parameter table

| Row | Parameter | Implementation |
|---|---|---|
| 1 | Screen size min 2000 x 2000 | user-defined, default 2000 x 2000 |
| 2 | Camera type monochrome, colour optional | render mode switch |
| 3 | Camera resolution 640 x 480 | user-defined |
| 4 | Camera FOV default 4° x 3° | user-defined, IFOV derived |
| 5 | Camera update rate 30 Hz min | fixed-step clock, user-defined >= 30 |
| 6 | Initial camera position centre | default pose |
| 7 | Target type beacon spot | Gaussian or shaped spot |
| 8 | Number of targets 1 mandatory, multiple optional | N targets |
| 9 | Target shape default square | square, circle, Gaussian, sprite |
| 10 | Target size 5 to 20 px, default 10 x 10 | user-defined |
| 11 | Initial target location default random | seeded random or fixed |
| 12 | Motion: line, circular, figure of 8, random; optional spiral, sinusoidal, user | all implemented plus waypoint and expression |
| 13 | Max pan speed 5 to 10 °/s, default 5 | slew limiter |
| 14 | Max tilt speed 5 to 10 °/s, default 5 | slew limiter |
| 15 | Update interval >= 20 Hz | control clock |
| 16 | Acquisition time <= 2 s | metric with pass/fail |
| 17 | Tracking error <= 10 px | pointing error metric with pass/fail |
| 18 | Target loss < 5% | lock retention metric with pass/fail |
| 19 | Re-acquisition <= 1 s | metric with pass/fail |
| 20 | Processing speed >= 20 FPS | FPS metric with pass/fail |
| 21 | Image noise: salt and pepper ~10%, Gaussian, Poisson, one or more | detector noise stage |
| 22 | Max noise std dev 20 | user-defined |
| 23 | Max camera jitter +/- 20 px/frame | jitter stage on pose |
| 24 | Atmosphere: Clear, Haze, Fog, Rain, Low light; contrast and brightness reduction | extinction and airlight stage with presets |
| 25 | Platform motion +/- 20 px/frame; linear mandatory, others optional | platform pose stage |

### 7.3 Deliverables

| Deliverable | Produced by |
|---|---|
| Standalone executable | PyInstaller one-folder builds for Windows and Linux, macOS best effort |
| Documented modular source | typed modules, docstrings, README, architecture doc |
| Technical report 10 to 15 pages | `docs/report/`, written from regression metrics |
| User manual | `docs/manual/`: installation, operation, parameter configuration, GUI description |
| Demo video 3 to 5 min | recorded from GUI record function |
| Performance log | auto CSV and PDF/HTML per run, batch envelope report |

### 7.4 Evaluation stages

| Stage | Preparation |
|---|---|
| Functional verification | 10-minute scripted demo: clear run, add each disturbance live, multi-target, video ingest, report export |
| Benchmark-1 | scenario loader accepts evaluator files; if their format differs, a mapping dialog converts to our YAML; centroid log and report generated automatically |
| Benchmark-2 | .mp4 replaces the simulated scene; frame-accurate centroid CSV; report with RMSE, acquisition, re-acquisition, lock retention, FPS |
| Technical evaluation | this document plus report sections on IFOV budget, control law, IMM, channel model, CNN training, test methodology, envelope results, future work |

---

## 8. Future improvements (for the report)

- Reinforcement-learned gain scheduling on top of the classical controller, trained in the same simulator.
- Wide-FOV acquisition sensor plus narrow-FOV tracking sensor as a dual-camera PAT architecture.
- Learned denoiser for extreme scintillation.
- Beacon modulation and lock-in detection for identity in dense clutter.
- Hardware-in-the-loop interface: the FrameSource and Gimbal protocols already isolate the simulator so a real camera and pan-tilt unit can be dropped in.
