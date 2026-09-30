# ARGUS

**Acquire, Recognise, Guide, Update, Stabilise.** An AI-assisted virtual camera tracking system for
the coarse alignment of mobile Free Space Optical Communication (FSOC) terminals.

Smart India Hackathon 2026, problem statement 26169 (Department of Space, ISRO Space Applications
Centre). Team BlankPoint, Dayananda Sagar College of Engineering, Bengaluru.

ARGUS replaces the camera, pan-tilt mount and optics needed to develop the coarse stage of FSOC
pointing, acquisition and tracking. It renders a configurable scene with one or more moving
beacons, applies atmospheric, platform and sensor disturbances, and steers a rate-limited virtual
camera so the designated beacon stays centred. Every run is measured against the problem
statement's performance limits and writes its own report. The same engine reads the evaluators'
30 fps videos for Benchmark 2.

Try it: **https://sih26169.blankpoint.club/** (web demo and desktop downloads).

## Measured performance

Regression batch: 17 scenarios, 3 seeds each, 15 s per run, laptop CPU. Every value is written by
the software itself and can be rebuilt from its per-frame log with `fsoc-tracker verify`.

| Conditions | Acquisition | Tracking error | Centroiding error | Lock retention | Speed |
|---|---|---|---|---|---|
| Clear sky: line, circle, figure of 8 | 0.60 to 1.33 s | 2.1 to 3.7 px | 0.006 px | 100 % | 195 to 218 FPS |
| Heavy noise: salt and pepper 10 %, Gaussian σ 20, Poisson | 0.67 to 1.00 s | 2.4 to 3.7 px | 0.19 px | 100 % | 104 to 109 FPS |
| Fog and low light | 0.63 to 1.57 s | 2.5 to 3.7 px | 0.08 to 0.15 px | 100 % | 116 to 124 FPS |
| Faint beacon, 3 to 6 σ per frame | 1.03 to 2.00 s | 2.4 to 3.4 px | 0.3 to 4.0 px | 95.9 to 97.8 % | 105 to 109 FPS |
| Identical decoys | 0.60 to 0.63 s | 3.3 to 3.5 px | 0.03 px | 100 % | 94 to 96 FPS |
| **Problem statement limit** | **≤ 2 s** | **≤ 10 px** | | **≥ 95 %** | **≥ 20 FPS** |

At the problem statement's maximum platform motion (20 px per frame sway plus 20 px per frame
random vibration) the tracking error is 21.7 to 23.5 px. This is a physical limit, measured and
reported: a random jump of the picture cannot be known before the frame arrives, and a faster
gimbal (10 deg/s) was tested and does not change it.

## Quick start

Python 3.11 or 3.12.

```bash
git clone https://github.com/tanmayhutt/SIH26169.git && cd SIH26169
python -m venv .venv && source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -e ".[dev,web]"

fsoc-tracker gui                                         # desktop application
```

Standalone desktop builds that need no Python are on the site's downloads page, for Windows,
Linux and macOS (Intel and Apple silicon).

## Usage

```bash
fsoc-tracker run   --scenario configs/scenarios/clear_line.yaml --seed 0
fsoc-tracker video path/to/file.mp4 [--truth truth.csv]  # Benchmark 2: the video replaces the scene
fsoc-tracker batch -s configs/scenarios/*.yaml --seeds 0-2 --duration 15
fsoc-tracker verify results/<run folder>                 # recompute every metric from the frame log
uvicorn webapp.server:app --port 8095                    # web app at http://127.0.0.1:8095/
```

Each run writes one folder, `results/FSOC_<sim|video>_<name>_seed<N>_<date-time>/`, holding the
per-frame log (`_frames.csv`), every metric with its pass or fail (`_summary.json`), the PDF
performance report (`_report.pdf`) and the exact parameters (`_scenario.yaml`), so any run can be
repeated. To evaluate your own scenario, copy `configs/scenarios/TEMPLATE_evaluator.yaml`.

## How it works

```
 scene + beacons ──> disturbance chain ──> frame ──┐          (or a video file, Benchmark 2)
                                                   v
          detector + sub-pixel centroid ──> identity + IMM estimator ──> 5-state tracker
                                                                                 │
          gimbal model (rate, acceleration, latency) <── feed-forward + PI controller
                                                                                 │
                                         telemetry ──> metrics ──> PDF report + CSV + JSON
```

- **Detection**: median filter, background subtraction, a Gaussian matched filter, an adaptive
  threshold on the median absolute deviation, connected components and shape checks, then a
  centre-of-gravity and 2-D Gaussian fit to a fraction of a pixel. A track-before-detect path
  links weak candidates across frames to find beacons at 3 to 6 σ.
- **AI**: a small fully convolutional network (U-Net style, about 0.1 M parameters, ONNX) trained
  on simulator frames with exact labels. It fills gaps only when the classical detector's
  confidence drops, so frame rate and reliability never depend on it.
- **Estimation**: an interacting multiple model filter (constant velocity, constant acceleration,
  coordinated turn) with measurement noise that adapts to measured vibration.
- **Tracking**: SEARCH, VERIFY (3 of 4 frames), TRACK, COAST, REACQUIRE, with Mahalanobis gating
  and an appearance signature that holds the designated beacon among decoys. The designated
  beacon can be chosen by look, by start position, or from the beacons detected in a video.
- **Control**: feed-forward of the target's angular rate plus PI on the pointing error, with
  latency lead limited on tight turns, inside a gimbal model that enforces 5 to 10 deg/s.
- **Scenario check**: every input is clamped, and values beyond the problem statement or
  physically impossible for the camera are flagged before the run.

## Problem statement coverage

- All 25 rows of the parameter table are implemented, with one configuration field per row.
  That covers the screen, camera and FOV, target shape and size, the six motions plus waypoints,
  pan and tilt limits, the three noise models, jitter, five atmosphere presets and platform motion.
- All eight "shall" functions are implemented: environment, multiple targets, movable camera,
  automatic detection, continuous tracking, camera control, live disturbances and real-time statistics.
- Every run writes the performance log the problem statement asks for: simulation duration, FPS,
  acquisition time, mean and maximum tracking error, lock retention and processing time.
- `python tools/ps_audit.py` checks every row, "shall" item and benchmark by running the code.
  39 of 39 checks pass.

## Repository layout

```
fsoc_tracker/
  world/        scene, beacon shapes and motions, gimbal model, disturbance chain, renderer
  perception/   classical and CNN detectors, sub-pixel centroid, IMM estimator, ego-motion
  control/      tracker state machine and identity, controller, a simple baseline for comparison
  engine/       run loop, configuration, scenario check, metrics, report, telemetry, verify
  gui/          PyQt6 desktop application
  cli.py        command line;  ui_shared.py  one interface definition for desktop and web
configs/scenarios/   17 scenarios and an evaluator template
models/              beacon_heatmap.onnx
training/            CNN training on simulator frames
tests/               pytest suite
tools/               PS audit, regression and baseline comparison, packaging check, macOS build
webapp/              FastAPI server and the browser front end
fsoc_tracker.spec    PyInstaller build   .github/workflows/  build and test on every platform
```

## Verification

```bash
python -m pytest                                          # 125 tests
python tools/ps_audit.py                                  # every problem statement item, measured
python webapp/smoke.py                                    # the web app end to end
python tools/compare_batches.py results/a results/b       # regression: no run may be worse
```

Nothing is tuned to a particular video or scenario. A change goes in only as a general fix within
the problem statement's scope, and only when the regression batch shows no run worse than before.

## Team BlankPoint

Shivansh Pandey (team leader), Govind Pandey, Tanmay Tiwari, Manya Kumar, Abhijeet Yadav,
Lakshita Didwania. Team ID 182144.
