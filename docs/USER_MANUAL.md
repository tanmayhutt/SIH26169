# FSOC Tracker: User Manual

AI-based virtual camera tracking system for coarse alignment of mobile Free Space Optical
Communication (FSOC) terminals. Smart India Hackathon problem statement SIH26169,
Department of Space / ISRO Space Applications Centre.

## 1. What the application does

The application simulates the coarse alignment stage of an FSOC link entirely in software.

- It draws a scene (the "screen", at least 2000 x 2000 pixels) with a moving optical beacon.
- A virtual pan-tilt camera looks at a 640 x 480 pixel window of that scene (4 x 3 degrees)
  and can turn at a limited speed, like a real motorised mount.
- Disturbances can be added: fog, haze, rain, low light, atmospheric turbulence, platform
  motion, camera vibration, and sensor noise.
- The tracker detects the beacon, measures its centre to a fraction of a pixel, predicts
  where it is going, and steers the camera window to keep it centred.
- Every run writes a per-frame log (`frames.csv`), a summary (`summary.json`) and an
  automatic performance report (`report.pdf`).
- For Benchmark 2, an `.mp4` video can be opened in place of the simulated scene.

## 2. Installation

### 2.1 Standalone executable (no Python needed)

1. Download the archive for your operating system from the release folder
   (`FSOC-Tracker-windows.zip`, `FSOC-Tracker-linux.tar.gz`, `FSOC-Tracker-macos.zip`).
2. Extract it anywhere.
3. Run `FSOC-Tracker` (Windows: `FSOC-Tracker.exe`). The first start takes a few seconds.

Results are written to a `results` folder next to the executable.

### 2.2 From source

Requires Python 3.11 or 3.12.

```
git clone <repository>
cd SIH169
python -m venv .venv
.venv/bin/pip install -e ".[dev]"        # Windows: .venv\Scripts\pip install -e ".[dev]"
.venv/bin/fsoc-tracker-gui               # start the desktop application
```

Optional, to retrain the AI detector: `pip install -e ".[train]"` then
`python training/train_heatmap.py`.

## 3. The main window

```
+------------------+------------------------------------------------+-----------------+
| Parameters       | State | Acquisition | Track err | Centroid | Lock | FPS |  Telemetry  |
| (scrollable,     +------------------------------------------------+  one value per  |
|  hover for help) | Screen view              | Camera view         |  line, every    |
|                  | whole scene, camera      | 640 x 480 with HUD  |  frame          |
|                  | window, trails, 2 deg    | capture ring, error |                 |
|                  | grid, legend             | vector, 1 deg bar   |                 |
|                  +------------------------------------------------+                 |
|                  | Errors      | Gimbal command                   |                 |
|                  | Timing      | Tracker state                    |                 |
+------------------+------------------------------------------------+-----------------+
| Status: what is running and where results go                              [=====]  |
+------------------------------------------------------------------------------------+
```

### Toolbar, left to right

| Control | Action |
|---|---|
| Scenario | Pick a ready-made test case from `configs/scenarios`. "Custom" keeps whatever is in the panel. |
| Start / Pause / Step / Stop | Run control. Space starts or pauses, N steps one frame while paused, Esc stops. |
| Speed | 0.25x to 4x real time, or Max speed (shows the true processing rate). |
| Open video (Benchmark 2) | Choose an `.mp4`; the simulator is bypassed and the video frames become the scene. Ctrl+O. |
| Use simulator | Return to the simulated scene. |
| Save scenario | Save the panel as a `.yaml`; it appears in the Scenario list. Ctrl+S. |
| Screenshot | Save a PNG of the window into `results/`. Ctrl+P. |
| Results folder | Open `results/`. |
| User manual | Open this manual. |
| Help | Legend and output summary. |

### Tiles (live specification check)

Six tiles above the pictures update every frame and turn green when the problem statement
specification is met, amber when it is not: tracker state, acquisition time (2 s or less),
mean tracking error since acquisition (10 px or less), mean centroiding error, lock retention
(target loss under 5 percent), and processing FPS (20 or more). In video mode the two error
tiles read "n/a" because the video carries no ground truth.

### Screen view (left picture)

The whole scene, downscaled, with a 2 degree grid. Cyan rectangle: the camera window and its
centre. Orange circle: the true beacon (simulator only). Green cross: the tracker's estimate.
Grey circles: other targets. Faint trails: where the beacon and the window have been. The
legend is printed along the bottom edge.

### Camera view (right picture)

What the camera window sees, contrast-stretched for display. Cyan cross: boresight. Dashed
ring: the capture radius, green when locked. Line from the centre: the pointing error vector.
Green box: this frame's detection. Orange dot: the prediction, with a fainter ring for the
estimator's uncertainty. Green trail: recent estimates. A 1 degree scale bar sits bottom
right. The banner shows the state, tracking error in pixels and arcseconds, confidence and
which detector produced the measurement; the bottom line shows pan, tilt, the commanded
rates, saturation and processing time.

### Plots

- Errors: tracking error (window centre to beacon, cyan) and centroiding error (measured
  centre to true centre, orange). Dashed line: the 10 pixel specification.
- Gimbal command: pan and tilt rate commands with the rate limit dashed.
- Processing time per frame with the 20 FPS budget (50 ms) dashed.
- Tracker state: SEARCH, VERIFY, TRACK, COAST, REACQUIRE.

### Telemetry column

Every internal quantity for the current frame: state, detector, candidates, confidence, SNR,
pose, commands, detection, estimate, velocity, uncertainty, motion model probabilities,
truth, errors and timing. Before a run it shows a short how-to.

## 4. Parameters

Every row of the problem statement parameter table has a control. Values outside the
suggested range are allowed where the table says "user-defined".

### Run
- Name, Seed: the seed makes a run exactly repeatable.
- Duration (s): length of a simulator run. Ignored for video input (the whole video runs).
- Extra targets: number of additional beacons (decoys) added with random paths.

### Screen (rows 1 to 2)
- Width, Height: scene size in pixels. Default 2000 x 2000.
- Colour camera: renders a three-channel colour frame (PS row 2, optional); the tracker always works on luminance, so results are identical.
- Background: starfield, terrain, gradient or flat. Sky level and star density.

### Camera (rows 3 to 6, 13 to 15)
- Width, Height: camera window in pixels. Default 640 x 480.
- FOV width, height: degrees. Default 4 x 3. Degrees per pixel is derived from these.
- Update rate: frames per second. Default 30.
- Max pan, Max tilt: degrees per second. Default 5.
- Max accel, Command latency: gimbal realism.
- Hard mode: the tracker sees only the pixels inside the window and must search.

### Designated target (rows 7 to 12)
- Shape: square (default), circle, gaussian. Size in pixels (default 10). Peak intensity.
- Motion: line, circular, figure8, random, spiral, sinusoidal, static.
- Speed, Radius, Period, Heading: path parameters. Start: random or centre.
- Blink: optional intensity modulation in Hz. 0 is steady.

### Disturbances (rows 21 to 25)
- Salt and pepper fraction (0.10 = 10 percent), Gaussian sigma (up to 20), Poisson.
- Camera jitter: pixels per frame, up to 20.
- Atmosphere preset: clear, haze, fog, rain, lowlight. Selecting a preset fills contrast,
  brightness, blur and turbulence; each can then be edited.
- Platform motion: none, linear, circular, random, spiral, figure8; speed in pixels per
  frame (up to 20) and period.

### Tracker
- Detector: hybrid (classical first, AI fills gaps), classical, cnn.
- Use picture-shift estimate: phase correlation as a vibration hint.
- Controller gains, deadband, capture radius, estimator lag, minimum confidence to acquire.
- Hard mode (Camera section) restricts the tracker to the window; SEARCH then flies an expanding square spiral of window-sized cells at the rate limit. A full sweep of a 2000 px screen at 5 deg/s takes about 12 s, so acquisition in hard mode is 3 to 12 s depending on where the beacon is.

## 5. Running Benchmark 2 (video input)

1. Click "Open video (Benchmark 2)" and choose the `.mp4` file.
2. Set the camera window size and FOV if the graders specify them.
3. Click Start. The video frames are used as the scene; nothing is drawn by the simulator.
4. When the run ends, `frames.csv` contains the measured beacon centre for every frame
   (`det_x`, `det_y`) and `report.pdf` contains acquisition time, re-acquisition time,
   lock retention rate and FPS. Tracking and centroiding error against truth are not
   available because the video carries no ground truth.

From the command line: `fsoc-tracker video path/to/file.mp4`

## 6. Scenario files and the command line

A scenario is a YAML file with the same fields as the parameter panel. Example:

```yaml
name: fog_circular
seed: 6
duration_s: 30
targets:
  - {shape: square, size_px: 10, motion: circular, radius_px: 400, period_s: 15}
disturbance:
  atmosphere: fog
  gaussian_sigma: 8
```

Commands:

```
fsoc-tracker run --scenario configs/scenarios/fog_circular.yaml [--seed 3] [--duration 20]
fsoc-tracker video path/to/file.mp4
fsoc-tracker batch --scenario configs/scenarios/*.yaml --seeds 0-49
fsoc-tracker gui
```

`batch` runs every scenario over every seed and writes `envelope.md`, a table of the
worst and mean results per scenario.

## 7. Output files

Each run creates `results/<name>_<timestamp>/`:

| File | Contents |
|---|---|
| `frames.csv` | One row per frame: time, state, detection, estimate, camera pose, commands, truth, errors, processing time. |
| `summary.json` | All metrics with their definitions and pass/fail against the specification. |
| `report.pdf` | Three pages: specification check and metric table; time series; paths, histograms and model probabilities. |
| `scenario.yaml` | The exact parameters used, so the run can be repeated. |

## 8. Metric definitions

| Metric | Definition |
|---|---|
| Acquisition time | First frame in TRACK with the tracked beacon within the capture radius (30 px) of the window centre. Spec: 2 s or less. |
| Tracking error | Distance from the true beacon to the window centre, over frames after acquisition. Spec: 10 px or less (mean). |
| Tracking error, vibration removed | The same with the per-frame camera vibration subtracted from the truth: the part a rate-limited gimbal can physically follow. |
| Centroiding error | Distance from the measured beacon centre to the true centre. |
| Lock retention | Percentage of frames after acquisition in TRACK with the beacon inside the capture radius. Target loss is 100 minus this. Spec: loss under 5 percent. |
| Re-acquisition time | Time from losing lock to regaining it. Spec: 1 s or less. |
| FPS | 1 divided by per-frame processing time, averaged. Spec: 20 or more. |

## 9. Troubleshooting

- The window does not start on Linux: install `libxcb-cursor0` (Qt 6 requirement).
- Low frame rate: reduce the screen size, disable Poisson noise, or uncheck Real-time
  pacing to see the true processing speed.
- "Cannot open video": the file must be readable by OpenCV (H.264 `.mp4` is safest).
- The AI detector is not used: `models/beacon_heatmap.onnx` is missing; the classical
  detector runs alone. Retrain with `python training/train_heatmap.py`.
