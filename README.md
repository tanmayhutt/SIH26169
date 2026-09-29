# ARGUS

AI-based virtual camera tracking for the coarse alignment of mobile Free Space Optical
Communication (FSOC) terminals. Smart India Hackathon 2026, problem statement 26169
(Department of Space, ISRO Space Applications Centre). Team BlankPoint.

ARGUS simulates a scene with one or more moving beacons, a pan-tilt camera with realistic rate
limits and a chain of atmospheric, platform and sensor disturbances, then detects, identifies and
tracks the designated beacon and steers the camera to keep it centred. Every run writes a per-frame
log, a summary and a PDF report with the performance metrics the problem statement asks for
(acquisition time, tracking error, target loss, re-acquisition time, processing speed). The same
engine reads the evaluators' videos for Benchmark 2.

## Install and run

Python 3.11 or newer.

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -e ".[dev,web]"

fsoc-tracker gui                                        # desktop application
fsoc-tracker run --scenario configs/scenarios/clear_line.yaml --seed 0
fsoc-tracker video path/to/file.mp4 [--truth truth.csv] # Benchmark 2: the video replaces the simulated scene
fsoc-tracker batch -s configs/scenarios/*.yaml --seeds 0-2 --duration 15
fsoc-tracker verify results/<run folder>                # rebuild every metric from the per-frame log
uvicorn webapp.server:app --port 8095                   # the web app, then open http://127.0.0.1:8095/
```

Each run writes `results/FSOC_<sim|video>_<name>_seed<N>_<date-time>/` with `_frames.csv`,
`_summary.json`, `_report.pdf` and `_scenario.yaml` (the exact parameters, so the run repeats).

A standalone desktop build (no Python needed) is produced by `pyinstaller fsoc_tracker.spec`, by
the GitHub workflow for Windows and Linux, and by `tools/build_macos.sh` for macOS.

## How it works

- **World** (`fsoc_tracker/world/`): scene backgrounds, beacon shapes and motions (line, circular,
  figure of 8, random, spiral, sinusoidal, waypoints), the gimbal model (rate and acceleration
  limits, latency), and the disturbance chain (extinction, turbulence, blur, platform sway,
  vibration, exposure, frame loss, Poisson, Gaussian and salt-and-pepper noise) applied in
  physical order. The renderer returns the ground truth of every frame.
- **Perception** (`fsoc_tracker/perception/`): a classical detector (median, background
  subtraction, matched filter, adaptive threshold, connected components) with a sub-pixel centroid
  (centre of gravity plus a 2-D Gaussian fit); a track-before-detect path for beacons at three to
  six sigma; a small CNN heat-map detector (ONNX, `models/`) that fills gaps in degraded
  conditions; an interacting multiple model estimator (constant velocity, constant acceleration,
  coordinated turn); frame-to-frame ego-motion by phase correlation.
- **Control** (`fsoc_tracker/control/`): a five-state tracker (SEARCH, VERIFY, TRACK, COAST,
  REACQUIRE) with gating, an appearance signature that holds identity among decoys, and an
  optional beacon blink code; a feed-forward plus PI rate controller with latency lead.
- **Engine** (`fsoc_tracker/engine/`): the run loop, typed configuration (one field per problem
  statement row, YAML in and out), the scenario check (values clamped, beyond the PS, near a
  limit or physically impossible), metrics with pass or fail against the PS limits, and the report.
- **Interfaces**: the PyQt6 desktop application (`fsoc_tracker/gui/`), the command line
  (`fsoc_tracker/cli.py`) and the web app (`webapp/`) share one interface definition,
  `fsoc_tracker/ui_shared.py`, so the panel, tiles and texts cannot drift apart.

## Repository layout

```
fsoc_tracker/        the package: world/, perception/, control/, engine/, gui/, cli.py, ui_shared.py
configs/scenarios/   17 scenario files (clear, noise, fog, low light, faint beacon, platform sway and
                     shake, multi-target stress, identical decoys, beacon shapes, fast circle, hard mode,
                     coded beacon) and an evaluator template
models/              beacon_heatmap.onnx, the CNN
training/            trains the CNN on frames rendered by the simulator and exports ONNX
tests/               pytest suite: geometry, motions, centroiding, estimation, closed-loop specification
                     checks, Benchmark 2, designation, robustness, the web server
tools/               ps_audit.py (measures every PS row, shall item and benchmark by running the code),
                     compare_batches.py and compare_trackers.py (regression and baseline comparison),
                     package_check.py (runs a built archive), build_macos.sh, gui_screenshot.py
webapp/              FastAPI server, static page, deploy and publish scripts
fsoc_tracker.spec    PyInstaller build; .github/workflows/build.yml builds and tests on every platform
```

## Verification

```bash
python -m pytest                                                  # the test suite
python tools/ps_audit.py                                          # every PS item, measured; writes results/PS_AUDIT.md
python webapp/smoke.py                                            # the web app end to end
fsoc-tracker batch -s configs/scenarios/*.yaml --seeds 0-2 --duration 15 --out results/b
python tools/compare_batches.py results/a results/b               # no run may be worse after a change
```

Nothing is tuned to a particular video or scenario: a change goes in only if it is a general fix
within the problem statement's scope and the regression batch shows no run worse than before.

## Deliverables

The user manual, the technical report and the presentation are submitted separately and are
available on the project site's downloads page. When the team's records folder sits beside this
repository as `SIH169-records`, the packaging bundles the manual and the report next to the application.
