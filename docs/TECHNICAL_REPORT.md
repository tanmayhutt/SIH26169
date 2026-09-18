# Technical Report

Development of an AI-Based Virtual Camera Tracking System for Coarse Alignment of Mobile
Free Space Optical Communication (FSOC) Terminals. Smart India Hackathon SIH26169.
Organisation: Department of Space / Indian Space Research Organisation, Space Applications Centre.

Sections follow the order the problem statement asks for: problem understanding, system
architecture, software modules, tracking methods, AI methods, test methodology, performance
analysis, future improvements. Figures referenced as `results/...` are produced by the
software itself; the numbers in section 7 are copied from `results/batch/<stamp>/envelope.md`.

---

## 1. Problem understanding

### 1.1 Context
FSOC links carry data on a highly directional laser beam. Compared with radio they offer
gigabit-to-terabit data rates, need no spectrum licence and are immune to electromagnetic
interference, but a small angular pointing error breaks the link. Between moving platforms
(satellites, UAVs) the two terminals must therefore run a Pointing, Acquisition and Tracking
(PAT) loop. PAT has a coarse stage, which brings the remote terminal's beacon into the camera
field of view and holds it there, and a fine stage, which locks the beam precisely. This work
addresses the coarse stage.

### 1.2 The engineering problem in the problem statement
Developing coarse alignment algorithms on hardware needs a camera, a pan-tilt mechanism and
optics. The problem statement asks for a software platform that replaces them: a
configurable virtual scene with one or more moving beacons, a movable virtual camera with
realistic rate limits, a configurable set of disturbances, an automatic detector and tracker
that steers the camera, live statistics, and an automatically generated performance log.

### 1.3 Reading of the specification
- The scene ("screen", >= 2000 x 2000 px) is what the tracker observes each frame: the
  problem statement's "simulated video stream". The 640 x 480 px camera window (4 x 3 deg)
  is the controlled output and represents where the terminal is pointing. Its centre starts
  at the screen centre and moves at 5 to 10 deg/s at most.
- With one screen pixel equal to one camera pixel, the instantaneous field of view (IFOV) is
  4 deg / 640 px = 0.00625 deg = 22.5 arcsec per pixel; the 10 px tracking specification is
  0.0625 deg; at 5 deg/s and 30 Hz the window moves at most 26.7 px per frame; the maximum
  platform motion of 20 px per frame therefore consumes 75% of the slew budget.
- Benchmark 2 replaces the simulated scene with the evaluators' .mp4. The tracker and
  camera control run unchanged on the video frames; the output is the per-frame centroid and
  the timing and lock metrics.
- Two error terms appear in the specification and are both logged: tracking error (true
  beacon to window centre) and centroiding error (measured centroid to true centroid).

---

## 2. System architecture

```
DISPLAY (PyQt6)      scene view, camera view with HUD, live plots, parameter panel
INSTRUMENTATION      telemetry bus -> frames.csv, summary.json, report.pdf
SIMULATION LOOP      fixed step at the camera update rate; deterministic from (scenario, seed)
   WORLD             scene, beacons, camera window and gimbal, disturbance chain, renderer
   PERCEPTION        FrameSource (simulator | video), classical detector, CNN detector,
                     sub-pixel centroid, association and identity, IMM estimator
   CONTROL           state machine, feedforward + PID rate controller, gimbal limits
```

One `Simulation` object drives every frame for the GUI, the command line and the tests, so
all three execute the same code path. A `FrameSource` abstraction yields frames from the
simulator or from a video file; nothing downstream knows which.

Data flow per frame: kinematics advance; the gimbal integrates the previous command; the
renderer draws the scene and applies the disturbance chain; the tracker detects, measures,
associates and updates the estimator; the state machine chooses what to aim at; the
controller emits a rate command clipped by the gimbal model; a telemetry record is written.

---

## 3. Software modules

| Module | Purpose |
|---|---|
| `engine/config.py` | Typed configuration; one field per problem statement parameter row; YAML load and save. |
| `world/scene.py` | Backgrounds: starfield, terrain, gradient, flat. |
| `world/targets.py` | Beacon kinematics: line, circular, figure of 8, random (Ornstein-Uhlenbeck), spiral, sinusoidal, static. |
| `world/camera.py` | Gimbal: pose in degrees, rate and acceleration limits, command latency, IFOV conversions. |
| `world/disturbance.py` | Extinction, turbulence (wander, scintillation), PSF blur, platform sway, vibration, Poisson, Gaussian and salt-and-pepper noise, in physical order. |
| `world/renderer.py` | Draws the scene with sub-pixel beacon placement; returns ground truth. |
| `perception/detect.py` | Classical detector (median, background subtraction, matched filter, adaptive threshold, connected components, shape filters), sub-pixel centroid (centre of gravity plus 2D Gaussian fit), CNN heat-map detector (ONNX). |
| `perception/estimator.py` | IMM over constant velocity, constant acceleration and coordinated turn. |
| `perception/egomotion.py` | Frame-to-frame picture shift by phase correlation. |
| `control/tracker.py` | State machine SEARCH, VERIFY, TRACK, COAST, REACQUIRE; gating; appearance signature for identity; adaptive measurement noise. |
| `control/controller.py` | Feedforward plus PID rate controller with latency lead, deadband and anti-windup. |
| `engine/simulation.py` | The run loop and telemetry record. |
| `engine/metrics.py` | Metric definitions and specification pass/fail. |
| `engine/report.py` | PDF report. |
| `gui/app.py` | Desktop application. |
| `cli.py` | `run`, `video`, `batch`, `gui` commands. |

---

## 4. Tracking methods

### 4.1 Detection and centroiding
A 3x3 median (5x5 added automatically under heavy salt and pepper) removes specks. A 31x31
box blur estimates the smooth background, which is subtracted. A Gaussian matched filter at
one third of the configured beacon size raises the SNR of an extended spot against point
noise and stars. Pixels above mean + k sigma (k = 4) are labelled by connected components;
blobs are kept if their area, aspect ratio and fill are consistent with a spot. Each blob is
scored by SNR, peak brightness and agreement with the expected area of the designated beacon.
The leading candidates are refined by an intensity-weighted centre of gravity on a
background-subtracted patch followed by a 2D Gaussian least-squares fit, giving centroids to
about 0.01 px on clean frames and 0.1 to 0.2 px under heavy noise.

### 4.2 Estimation
An IMM runs three Kalman filters (constant velocity, constant acceleration, coordinated
turn) and blends them by likelihood. Process noise is sized for the accelerations the
problem statement produces (beacon paths to ~100 px/s^2, platform sway to ~600 px/s^2).
Measurement noise adapts: the zero-mean part of the innovation sequence is treated as
vibration and added to the measurement variance, so the estimator smooths jitter instead of
chasing it, while a consistent innovation (lag) is not mistaken for noise.

### 4.3 State machine and identity
SEARCH detects on the whole observed picture. VERIFY requires 3 of 4 consistent frames
before declaring lock, so a noise speck is never counted as acquisition. TRACK searches a
region around the prediction, gates candidates by Mahalanobis distance and rejects those
whose appearance signature (area, peak, PSF width) differs strongly from the beacon being
followed, which holds identity through crossings with decoys. COAST propagates the
prediction through short dropouts; REACQUIRE widens the search with the growing uncertainty
and falls back to SEARCH if it exceeds the screen. In hard mode (tracker restricted to the
window) SEARCH drives an outward spiral.

### 4.4 Control
The angular error is the IFOV times the pixel offset from the window centre to the target
position led by the command latency (velocity and acceleration), with the window's own
motion led likewise. The command is feedforward of the target angular rate plus PID on the
error, with a 1.5 px deadband and integrator clamping while saturated. The gimbal model
applies rate saturation (5 to 10 deg/s), acceleration saturation and a one-frame latency,
and reports saturation to the log.

---

## 5. AI methods

### 5.1 Role
The classical detector is fast and accurate in clear conditions but fails in fog, rain, low
light and heavy noise, where "the brightest compact blob" is the wrong answer. A small
fully convolutional network then provides the measurement. It runs only when the classical
confidence is below a floor, and only on a 128 x 128 region around the prediction, so speed
and reliability never depend on the model.

### 5.2 Network and training
Three-level U-Net-style encoder with skip connection, about 0.1 M parameters, input a
normalised 128 x 128 patch, output a 64 x 64 heat map with a Gaussian bump on the beacon.
Loss: weighted binary cross-entropy. Training data are rendered by the simulator itself
under randomised backgrounds, beacon shapes and sizes, decoys, atmosphere presets and noise;
the simulator knows the beacon position, so labels are exact and unlimited. The model is
exported to ONNX and run with ONNX Runtime on CPU in a few milliseconds. Sub-pixel position
comes from a soft-argmax on the heat map followed by the same Gaussian refinement used by
the classical path.

---

## 6. Test methodology

- Unit tests (`tests/`): IFOV and pose conversions, gimbal saturation and pose limits,
  determinism and screen bounds of every motion type, centroid accuracy on clean frames,
  sub-pixel refinement on a synthetic Gaussian, IMM prediction on a circle, closed-loop
  specification checks on a clear scenario and on a platform-plus-vibration scenario, and a
  Benchmark 2 path that writes a synthetic video and runs the tracker on it.
- Scenario pack (`configs/scenarios/`): the four mandatory motions in clear conditions,
  heavy noise, fog, low light, platform sway with vibration, a multi-target stress case,
  and hard mode.
- Batch envelope: `fsoc-tracker batch --scenario configs/scenarios/*.yaml --seeds 0-N`
  runs every scenario over N seeds and writes `envelope.md` with mean and worst values.
- Every metric has a printed definition (section 8 of the user manual) so the numbers can be
  compared with the evaluators' own.

---

## 7. Performance analysis

Fill from `results/batch/<stamp>/envelope.md` and the individual `report.pdf` files.

| Scenario | Acquisition (s) | Tracking error mean (px) | Centroiding error mean (px) | Lock retention (%) | FPS |
|---|---|---|---|---|---|
| clear, line | | | | | |
| clear, circular | | | | | |
| clear, figure of 8 | | | | | |
| clear, random | | | | | |
| noise (S&P 10%, Gaussian 20, Poisson) | | | | | |
| fog | | | | | |
| low light | | | | | |
| platform sway 20 px/f + vibration 20 px/f | | | | | |
| multi-target stress | | | | | |

Discussion points: centroiding accuracy versus noise; the vibration-removed tracking error
as the physically followable part; slew saturation under maximum platform motion; where the
CNN contributed measurements.

---

## 8. Future improvements

- Reinforcement-learned gain scheduling on top of the classical controller, trained in the
  same simulator.
- Dual-sensor PAT: a wide field acquisition camera feeding a narrow field tracking camera.
- Learned denoiser for extreme scintillation.
- Beacon modulation with lock-in detection for identity in dense clutter.
- Hardware in the loop: the `FrameSource` and gimbal interfaces already isolate the
  simulator, so a real camera and pan-tilt unit can be substituted.
