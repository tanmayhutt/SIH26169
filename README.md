# FSOC Tracker (LAKSHYA)

Team Blank Point. The submission name of the project is **LAKSHYA**; the software and its builds are
called FSOC Tracker.

AI-based virtual camera tracking system for coarse alignment of mobile Free Space Optical
Communication (FSOC) terminals. Smart India Hackathon problem statement **SIH26169**,
Department of Space / ISRO Space Applications Centre.

The application is a software stand-in for an FSOC coarse-alignment test bench. It draws a
scene with a moving optical beacon, adds atmospheric and platform disturbances, and runs a
tracker that finds the beacon, measures its centre to a fraction of a pixel, predicts its
motion and steers a rate-limited virtual pan-tilt camera to keep it centred. It also accepts
`.mp4` files in place of the simulated scene (Benchmark 2). Every run writes a per-frame
CSV log and an automatic PDF performance report.

## Start here

| Document | For |
|---|---|
| `docs/KNOWLEDGE_TRANSFER.md` | The problem statement and our solution explained completely, in plain language |
| `docs/HANDOVER.md` | Working on the code: setup, commands, code map, verification, release, server |
| `CONTRIBUTING.md` | How teammates make and submit changes |
| `CLAUDE.md` | Rules for every contributor and AI agent |
| `COMPLIANCE.md` | Every PS row, deliverable and evaluation stage, with where and how it is met |
| `docs/TECHNICAL_REPORT.md`, `docs/USER_MANUAL.md` | The submitted report and manual (PDFs beside them) |
| `docs/TESTING_GUIDE.md`, `docs/DEMO_SCRIPT.md` | Manual testing, and the live demonstration |
| `26169.pdf` | The problem statement itself |
| `docs/submission/LAKSHYA_SIH2026_26169.pdf` | Our SIH idea-submission presentation (8 slides) |

## Quick start

```
uv venv --python 3.12 .venv                  # or: python3.12 -m venv .venv
uv pip install --python .venv/bin/python -e ".[dev]"
.venv/bin/fsoc-tracker-gui                   # desktop application
.venv/bin/fsoc-tracker run -s configs/scenarios/clear_line.yaml
.venv/bin/fsoc-tracker video path/to/file.mp4
.venv/bin/fsoc-tracker batch -s configs/scenarios/*.yaml --seeds 0-9
.venv/bin/python -m pytest
```

Standalone executable: `.venv/bin/pyinstaller fsoc_tracker.spec` produces `dist/FSOC-Tracker/`.
Run `FSOC-Tracker` inside it (no Python needed). With arguments it acts as the command line tool.
`.github/workflows/build.yml` builds it for Windows x64, Linux x64, macOS Intel and macOS Apple
silicon, running the tests and a packaged smoke test on each; `bash webapp/fetch_builds.sh` pulls
the archives into `dist/` for deployment.

## Layout

```
fsoc_tracker/
  engine/      config (one field per PS parameter row), simulation loop, telemetry, metrics, report
  world/       scene, beacon kinematics, camera and gimbal, disturbance chain, renderer
  perception/  classical detector and sub-pixel centroid, CNN heat-map detector, IMM estimator, ego-motion
  control/     tracker state machine and identity, feedforward + PID controller
  gui/         PyQt6 desktop application
  cli.py       run | video | batch | gui
configs/scenarios/   scenario files (clear, noise, fog, low light, platform sway, multi-target, hard mode)
training/            trains the CNN on frames rendered by the simulator, exports ONNX
tests/               unit and closed-loop tests
docs/                USER_MANUAL.md, TECHNICAL_REPORT.md, plan.html
models/              beacon_heatmap.onnx
```

## Web app

The same program served to a browser (`webapp/`). The desktop window and the web page are built
from one interface definition, `fsoc_tracker/ui_shared.py` (panel, tiles, text, summary), so they
cannot drift apart. Run it with `.venv/bin/uvicorn webapp.server:app --port 8095`,
then open http://127.0.0.1:8095/. `bash webapp/deploy.sh` deploys the repository, the web app (site root),
the progress record and the downloads to the server behind Caddy. `python webapp/smoke.py` is the
cross-platform smoke test the build workflow runs.

## Documents

- `docs/USER_MANUAL.md`: installation, GUI, parameters, Benchmark 2, output files, metric definitions.
- `docs/TECHNICAL_REPORT.md`: problem understanding, architecture, modules, methods, tests, performance.
- `docs/TESTING_GUIDE.md`: how to exercise every input and configuration by hand, with expected outcomes.
- `docs/DEMO_SCRIPT.md`: the 10 to 15 minute live demonstration.
- `ARCHITECTURE.md`: design baseline and the reading of the problem statement it rests on.

## Licence

Submitted for Smart India Hackathon 2026. All rights reserved by the team.
