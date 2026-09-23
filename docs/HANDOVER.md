# Handover: everything a teammate needs

This document is the single starting point for anyone joining the project. It holds the
context that otherwise lived in one person's notes: what the software is, why it is built the
way it is, what was tried and rejected, how to verify a change, and how to release. If you read
only one file after the problem statement, read this one.

Project: ARGUS, Smart India Hackathon problem statement **SIH26169** (Department of Space,
ISRO Space Applications Centre): an AI-based virtual camera tracking system for coarse alignment
of mobile Free Space Optical Communication terminals.

Status on 2026-09-23: every mandatory item of the problem statement is implemented, tested and
released. Remaining work is preparation for the event (section 13).

---

## 1. Read in this order

1. `26169.pdf`: the problem statement. It is the only source of truth for what to build.
2. `docs/KNOWLEDGE_TRANSFER.md`: the problem statement and our solution explained completely, in
   plain language, for someone new.
3. This file.
4. `CLAUDE.md`: the rules every contributor (human or AI agent) follows in this repository.
5. `COMPLIANCE.md`: every PS row, "shall" item, deliverable and evaluation stage, with where it is
   implemented and how it is verified.
6. `ARCHITECTURE.md`: the design baseline and the reading of the PS it rests on.
7. `docs/TECHNICAL_REPORT.md`: methods, tests, measured performance (the submitted report).
8. `docs/USER_MANUAL.md`: installation and use (the submitted manual).
9. `docs/TESTING_GUIDE.md`: how to exercise every input by hand, with expected results.
10. `docs/DEMO_SCRIPT.md`: the 10 to 15 minute live demonstration.
11. `docs/plan.html`: a plain-English briefing for mentors and non-specialists.
12. `docs/submission/LAKSHYA_SIH2026_26169.pdf`: the SIH idea-submission presentation (8 slides).

`PROGRESS.md` and `web/progress.json` are the running status record; the second drives the
progress page on the site.

## 2. The rules, in short

The full text is in `CLAUDE.md`. The ones that matter most:

- **Build to the PDF, not to a test file.** Readiness means the evaluators' scenarios (Benchmark 1)
  and their 30 fps videos (Benchmark 2). Never tune the tracker to a video one of us recorded. A
  test file may reveal a defect; a change goes in only if it is a general defect inside the PS
  scope and it passes the regression batch with no run worse (section 8).
- **Do not use other SIH26169 teams' repositories.** They are competitors; reason from the PDF.
- **Report measured numbers only.** A physical limit is documented with its measurement, never
  tuned away or hidden.
- **The desktop executable is the deliverable.** It must work offline with no account. The web
  app, the site and any cloud service are additions, never dependencies.
- **One interface definition.** The desktop window and the web page are generated from
  `fsoc_tracker/ui_shared.py`. Change panel fields, tiles, texts or summaries there, never in one
  front end only (section 7).
- **Git:** commit as your own configured identity, never override `user.email`, no co-author
  trailers, short messages. Never commit `results/` or anyone's local `context.md`.

## 3. Set up a development machine

Python 3.11 or 3.12 is required (3.13 is not yet supported by all dependencies).

macOS or Linux:

```
git clone https://github.com/tanmayhutt/SIH26169.git && cd SIH26169
python3.12 -m venv .venv                        # or: uv venv --python 3.12 .venv
.venv/bin/pip install -e ".[dev,web]"
.venv/bin/python -m pytest                      # 29 tests, about 25 s
.venv/bin/fsoc-tracker-gui                      # the desktop application
```

Windows (PowerShell):

```
git clone https://github.com/tanmayhutt/SIH26169.git; cd SIH26169
py -3.12 -m venv .venv
.venv\Scripts\pip install -e ".[dev,web]"
.venv\Scripts\python -m pytest
.venv\Scripts\fsoc-tracker-gui
```

Optional extras: `.[train]` adds PyTorch for retraining the neural detector (section 6.5).

Linux without a desktop (a server or a container) needs the Qt runtime libraries for the GUI and
the offscreen tests: `libegl1 libgl1 libxkbcommon-x11-0 libxcb-cursor0` (Debian and Ubuntu names);
set `QT_QPA_PLATFORM=offscreen` to run without a display.

## 4. Everyday commands

```
fsoc-tracker run -s configs/scenarios/clear_line.yaml [--seed 3] [--duration 20]   # one scenario
fsoc-tracker video path/to/file.mp4 [-s settings.yaml]                              # Benchmark 2
fsoc-tracker batch -s configs/scenarios/*.yaml --seeds 0-2 --duration 15 --out results/b   # regression batch
fsoc-tracker-gui                                                                    # desktop app
uvicorn webapp.server:app --host 127.0.0.1 --port 8095                              # web app locally
python webapp/smoke.py                         # web app end to end: start, run, fetch report
python tools/compare_batches.py results/a results/b   # before/after, exit 1 if any run is worse
python tools/gui_screenshot.py results/shot full_stress   # desktop screenshots without a display
python tools/make_demo_video.py                # regenerate the demo video (docs/demo/, not in git)
python docs/build_pdfs.py                      # USER_MANUAL.pdf and TECHNICAL_REPORT.pdf (needs Chrome)
pyinstaller fsoc_tracker.spec                  # desktop bundle for this machine, into dist/
python tests/package_check.py dist/<archive>   # run a built archive the way a user would
```

Every run writes one folder `results/FSOC_<sim|video>_<name>_seed<N>_<YYYYMMDD-HHMMSS>/` holding
`<label>_report.pdf`, `<label>_frames.csv`, `<label>_summary.json`, `<label>_scenario.yaml`.
`fsoc_tracker/engine/naming.py` owns this scheme.

## 5. Code map

```
fsoc_tracker/
  engine/config.py       every setting as a dataclass, one field per PS row; presets; YAML load/save
  engine/simulation.py   the frame loop: source -> tracker -> controller -> gimbal -> telemetry
  engine/sources.py      frame sources: the simulator or a video file (probe_video calibrates from the file)
  engine/telemetry.py    the per-frame Record and the CSV writer
  engine/metrics.py      the PS limits (SPEC), metric definitions, the summary computed at the end
  engine/report.py       the automatic PDF performance report
  engine/naming.py       run labels and output file names
  world/scene.py         backgrounds (starfield, terrain, gradient, flat)
  world/targets.py       beacon paths: line, circular, figure8, random, spiral, sinusoidal, waypoints, static
  world/camera.py        the gimbal: rate, acceleration and pose limits, one frame of latency
  world/disturbance.py   noise, atmosphere, jitter, platform sway, applied in physical order
  world/renderer.py      draws each frame and its ground truth
  perception/detect.py   classical detector, sub-pixel centroid, CNN heat-map detector (ONNX)
  perception/estimator.py  IMM filter: constant velocity, acceleration and turn models
  perception/egomotion.py  picture shift by phase correlation (a vibration hint)
  control/tracker.py     state machine SEARCH/VERIFY/TRACK/COAST/REACQUIRE, identity, faint path
  control/controller.py  feed-forward plus PID pointing, spiral search in hard mode
  ui_shared.py           the interface definition both front ends draw from
  gui/app.py, theme.py   the PyQt6 desktop application
  cli.py                 run | video | batch | gui
  launcher.py            the packaged executable's entry point (GUI without arguments, CLI with)
webapp/server.py         FastAPI web app over the same engine; static/index.html is the page
webapp/deploy.sh         deploy repository, web app, site and Caddy config to the server
webapp/publish_builds.sh publish a build run's archives on the site
webapp/fetch_builds.sh   download a build run's archives into dist/ (slow on home connections)
configs/scenarios/       13 scenarios plus TEMPLATE_evaluator.yaml
tests/                   test_engine.py, test_ps_compliance.py, package_check.py
training/                train_heatmap.py, finetune_from_video.py (the neural detector)
models/beacon_heatmap.onnx   the shipped detector, 0.3 MB
web/                     the progress page (index.html) and its data (progress.json)
tools/                   compare_batches.py, gui_screenshot.py, make_demo_video.py
.github/workflows/build.yml  four-platform build, tests and package check on each platform
```

## 6. How the system works, and why it is built this way

### 6.1 Reading of the problem statement (settled 2026-09-18, re-checked 2026-09-20)

- The tracker observes the whole scene (the 2000 x 2000 "screen", the PS's "simulated video
  stream") and controls the 640 x 480 camera window (4 x 3 degrees) that represents where the
  terminal points. One screen pixel equals one window pixel, so IFOV = 0.00625 deg/px
  (22.5 arcsec) and the screen spans 12.5 degrees.
- The gimbal turns at most 5 deg/s (26.7 px per frame at 30 Hz). Centre to corner with the target
  known takes 0.95 s, which is why the 2 s acquisition limit is reachable.
- The simulator is half the product, not scaffolding: it covers the first four "shall" items,
  PS rows 1 to 15, Benchmark 1 and all ground truth. Benchmark 2 replaces the simulator's output
  with the evaluators' video; everything downstream runs unchanged.
- Hard mode (off by default) restricts the tracker to the window and flies a square spiral. A
  full sweep takes about 12 s at 5 deg/s, so hard mode cannot meet 2 s for far corners; it is
  demonstrated, not the default.

### 6.2 Perception

- Median filter only when salt and pepper are both present; a dark clipped sky is pepper only,
  and a median would erase faint beacons.
- Background subtraction and a Gaussian matched filter (sigma = size / 3) run in signed 16-bit
  arithmetic with a robust (median absolute deviation) noise level. An earlier unsigned version
  clipped and quantised the response and buried faint beacons.
- Candidates are returned unrefined; only the chosen and the gated ones get the Gaussian
  sub-pixel fit (the fit was the frame-rate drain). Centroids reach about 0.01 px in clear air.
- Confidence = 0.30 SNR term + 0.35 peak/255 + 0.35 size match. Stars score about 0.55, beacons
  0.67 (low light) to 0.96 (clear); a new track needs 0.62 (0.75 in hard mode).
- Faint beacons use track-before-detect: weak detections on a moving-target residual (the frame
  minus a running mean) are linked into motion-consistent chains; a chain hit 6 of 8 frames with
  mean SNR at least 3.5 and the right width is promoted. Off in hard mode. A faint beacon that
  never moves is not covered; the PS does not ask for one.
- The neural detector (84 thousand parameter heat-map network on a 128 x 128 patch, trained on
  simulator frames, run by ONNX Runtime) only fills gaps when the classical detector finds nothing
  near the prediction, and never overrides it. It is warmed up at start so its first use does not
  stall a run.

### 6.3 Estimation, identity and control

- IMM filter with constant velocity, constant acceleration and coordinated turn models, process
  noise sqrt(q) 32, 200 and 71 px/s^2.
- Vibration is estimated from the zero-mean part of the estimator's innovation (phase correlation
  is unreliable on noisy frames), capped at 25 px; it inflates measurement noise, the gate and
  the search region.
- Identity among decoys: an appearance signature (area, peak, fitted width); the configured size
  and shape score candidates by blob area and a fitted width calibrated on a rendered sprite; the
  signature does not blend towards an appearance that looks like two spots merging; an audit every
  15 frames, on a half-size copy of the picture, re-designates after three strikes.
- Controller: feed-forward of the estimated velocity and acceleration, led by the command latency
  plus the estimator lag; the lag is defined at 30 Hz and scales with the camera rate (a 60 fps
  video halved it). PID kp 5, kd 0.3, ki 0.8 with anti-windup.
- Lock means TRACK and the estimate within 30 px of the window centre. Tightening to 20 px did not
  lower error and cut lock under jitter. Tracked rate (share of frames in TRACK) is reported beside
  lock retention so tracker failure and gimbal limits can be told apart.

### 6.4 Disturbances

Applied in physical order (extinction, blur, picture shift, detector noise). Platform motion is a
bounded sway (amplitude at most 20 percent of the screen) with the configured peak speed; a
sustained 20 px per frame shift would leave the screen in seconds.

### 6.5 Tried and rejected (do not repeat without new evidence)

- Half-maximum area as the identity size measure: regressed under noise.
- A heavier signature weight in association: rejected the true beacon under haze.
- Derivative taken from the filtered state, jitter-adaptive process noise, low-passed derivative:
  each helped one scenario and hurt another; none moved the platform-maximum case. Reverted.
- Raising the gimbal to 10 deg/s for the platform maximum: saturation fell to 2 percent, lock did
  not improve. The random vibration is the limit, not the motor.
- Tightening the lock radius to 20 px (see above).
- Limiting the window to lie fully on the screen: made edge targets unreachable.

## 7. The two front ends are one program

`fsoc_tracker/ui_shared.py` defines the parameter panel (sections, labels, tooltips, ranges,
choices), the six tiles and their pass rules, telemetry lines, view captions, end-of-run summary,
help and welcome text, decoy generation, the seed rule and the camera display stretch. The
desktop app draws it with Qt; the web server sends it to the page at `/api/ui` and computes tiles,
telemetry and captions with the same functions. To add or change a setting, change it in
`engine/config.py` and, if it needs a label or tooltip, in `ui_shared.py`; both front ends pick it
up. Differences that remain come from the server: views sent at about 15 fps, one run at a time,
files downloaded instead of opened.

## 8. How to verify a change

1. `python -m pytest` must pass (29 tests; `tests/test_ps_compliance.py` pins every PS default).
2. For any change to perception, estimation or control, run the regression batch before and after
   and compare: `python tools/compare_batches.py results/before results/after` must report no run
   worse. Last recorded state: 36 of 36 runs unchanged (2026-09-22).
3. For interface changes, take screenshots at 1600 x 1000 and 1366 x 768 with
   `tools/gui_screenshot.py` and look at them; check the web page in a browser too.
4. `python webapp/smoke.py` for the web app.
5. After a release build, `tests/package_check.py` runs automatically on each platform; run it on
   the macOS archives locally as well (Intel through Rosetta: `--arch x86_64`).
6. Update `web/progress.json`, `PROGRESS.md`, `COMPLIANCE.md` and the PDFs so they say what the
   code does.

## 9. How to release

1. Push to `main`. A push that changes the application (code, scenarios, model, tests, build
   files, the bundled manual) starts the build by itself; otherwise start it by hand: GitHub,
   Actions, "Build desktop application", Run workflow (or `gh workflow run build.yml --ref main`).
   About 25 minutes. Each of Windows x64, Linux x64 (Ubuntu 22.04 glibc), macOS Intel and macOS
   Apple silicon runs the tests, the web smoke test, packages with PyInstaller and runs the
   package check. When all four pass, the workflow republishes the rolling `latest` pre-release
   and the GitHub packages `argus-desktop` (the archives) and `argus-web` (the web app image,
   started and checked before it is pushed); see README, Releases and packages. For a versioned
   release push a tag: `git tag v1.0.0 && git push origin v1.0.0`. A newer push to `main` cancels
   a main build still running. macOS minutes on a private repository count ten times against the
   Actions allowance, so documentation-only commits do not rebuild.
2. Publish the archives on the site: `bash webapp/publish_builds.sh` (the server downloads them).
3. Deploy code, web app, progress page and PDFs: `bash webapp/deploy.sh`. It syncs the repository
   to the server, reinstalls the virtual environment, restarts the service and reloads Caddy.
   Archives already on the site are kept unless `dist/` holds new ones.

## 10. The server and the site

- Site: `https://sih26169.blankpoint.club/`, behind one login (ask the project owner).
  `/` web app, `/about/` progress page and documents, `/downloads/` archives, PDFs and the demo
  video. `/progress` and `/app` are old addresses that redirect.
- Server: an Ubuntu 24.04 ARM machine. Repository at `/home/ubuntu/SIH169` with its own `.venv`;
  web app as the systemd service `sih26169-web` on 127.0.0.1:8095; static site at
  `/srv/sih26169/site/{about,downloads}`; Caddy site block `/etc/caddy/sih26169.caddy`, generated by
  `deploy.sh` (edit the script, not the file). Logs: `journalctl -u sih26169-web -f`.
- Access you need from the project owner: collaborator access to the GitHub repository, your SSH
  public key added to the server, and the site login. None of these are stored in the repository.

## 11. Known limits (documented, not bugs)

- Platform sway plus vibration at the PS maximum (20 + 20 px per frame): 76 to 88 percent lock,
  about 25 px raw error, 23 px with vibration removed; identical at 10 deg/s. A random jump of the
  whole picture every frame cannot be anticipated. Every PDF produced under vibration says so.
- Full stress (decoys, haze, noise, sway and vibration together): 13 to 17 px, 93 to 99 percent
  lock depending on the seed; it stacks disturbances the PS lists separately.
- Faint beacon: all ten seeds 91 to 97.5 percent lock; one seed acquires in 5.5 s.
- A hand-held phone video of a single dot: tracked about 99.6 percent, lock about 33 percent,
  because the hand's motion exceeds the gimbal's limits. It is harder than the PS describes and
  must not be tuned to (section 2).

## 12. Pitfalls we hit, so you do not

- macOS with Homebrew: the packaged app may print a `dyld: Symbol not found: _FcConfigSetWarningFlags`
  line when started from a terminal. Harmless; the launcher hides Homebrew from the app's PATH.
- The first start of a fresh bundle builds a font cache and takes a few seconds.
- macOS ships bash 3.2: empty arrays under `set -u` fail; `deploy.sh` uses the portable form.
- zsh: a glob that matches nothing is an error (`rm dist/*.zip` fails when there are none).
- Browsers cache permanent redirects; the site uses temporary redirects only.
- Some OpenCV builds cannot write mp4; tests that write a video try several codecs and skip cleanly.
- Windows SmartScreen and macOS Gatekeeper warn on first launch (the builds are not code-signed);
  the manual and the download dialog explain the two clicks.
- PyInstaller symlinks: the launcher creates relative links (or copies on Windows) to the bundled
  data folders on first start; stale links from another machine are repaired.

## 13. What is left, and who

| Item | Owner | How |
|---|---|---|
| Presentation: rename the project to ARGUS on every slide (the PDF still says LAKSHYA) and fill in the Team ID on slide 1. The PDF in `docs/submission/` carries later corrections (slides 2, 4, 5, 6, 8) that the source deck does not; copy them into the source before exporting again | team | compare with `git log -p docs/submission/` |
| Hand-driven GUI session on a Windows and a Linux machine | team | `docs/TESTING_GUIDE.md` sections 2 and 3; note the Processing tile value |
| Rehearse the live demonstration | presenter | `docs/DEMO_SCRIPT.md`, once end to end |
| Narrated screen recording, 3 to 5 min (optional) | team | record the rehearsal |
| Evaluators' scenarios and videos | at the event | copy `configs/scenarios/TEMPLATE_evaluator.yaml`; open videos directly |

Proposed extras, none required by the PS: Benchmark 2 auto-comparison against the evaluators'
predefined centroids; a Monte Carlo envelope over thousands of seeds on a large cloud machine;
blink-coded beacon identification; physically based turbulence; concurrent web runs.

## 14. History in one paragraph

2026-09-18: problem analysed, input model settled, architecture written. 2026-09-19: engine,
simulator, tracker, desktop app, command line, report, first builds, web app and server. 2026-09-20:
faint-beacon track-before-detect, identity fixes, four-platform builds with per-platform package
checks, waypoint paths (PS row 12 user-defined), demo video and script, output naming scheme.
2026-09-21 to 22: platform limit re-measured at 10 deg/s, frame-rate-independent lag compensation,
tracked-rate metric, interface review and fixes. 2026-09-23: desktop and web unified on one
interface definition. The full commit history is in git.
