# Handover: everything a teammate needs

This document is the single starting point for anyone joining the project. It holds the
context that otherwise lived in one person's notes: what the software is, why it is built the
way it is, what was tried and rejected, how to verify a change, and how to release. If you read
only one file after the problem statement, read this one.

Project: ARGUS, Smart India Hackathon problem statement **SIH26169** (Department of Space,
ISRO Space Applications Centre): an AI-based virtual camera tracking system for coarse alignment
of mobile Free Space Optical Communication terminals.

Status on 2026-09-23: every mandatory item of the problem statement is implemented, tested and
released. The 2026-09-23 changes (designation, shapes and sizes, scenario check, and the fixes
from the independent review, then the PS audit fixes) still need the four-platform build, publish and deploy. Remaining
work is preparation for the event (section 13).

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
12. `docs/submission/ARGUS_SIH2026_26169.pdf`: the SIH idea-submission presentation (8 slides).
13. `docs/DEMO_NARRATION.md`: the spoken script for the optional 3 to 5 minute demo video, with the source of every number.
14. `docs/submission/WHOLE_SCENE_SLIDE.md`: a slide and a 30-second answer on why the tracker watches the whole scene.
13. `docs/history/CHAT_LOG.md`: every teammate's Claude Code conversation in one file, one block
    per person and session, from the first day on. `python tools/chat_history.py sync` appends
    your own sessions (every Claude Code session on your machine that worked in this repository,
    found by the working directory each log line records, wherever Claude Code was started and on
    any OS) and lists what others added; Claude runs it at the start and end of every task (see
    `CLAUDE.md`). Until 2026-09-25 it looked only in `~/.claude/projects/<repo path with / made ->`,
    which missed Windows, paths with a dot, underscore or space, and sessions started in a parent
    folder, so only the owner's sessions reached the file; `sync --dry-run` shows what it would add. Secrets are
    removed; exact strings to remove go in the ignored local file `.chat_redact`. Read it for the
    reasoning behind a decision; the files above state the current truth.

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
.venv/bin/python -m pytest                      # 126 tests
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
fsoc-tracker video path/to/file.mp4 [-s settings.yaml] [--truth truth.csv]          # Benchmark 2
fsoc-tracker batch -s configs/scenarios/*.yaml --seeds 0-2 --duration 15 --out results/b   # regression batch
fsoc-tracker-gui                                                                    # desktop app
uvicorn webapp.server:app --host 127.0.0.1 --port 8095                              # web app locally
python webapp/smoke.py                         # web app end to end: start, run, fetch report
python tools/compare_batches.py results/a results/b   # before/after, exit 1 if any run is worse
fsoc-tracker verify results/<run folder> [...]        # recompute a run's metrics from its frames.csv, check its summary.json
python tools/compare_trackers.py               # ARGUS against the simple baseline on the pack -> docs/BASELINE_COMPARISON.md
python tools/record_check.py                   # commits that changed code without updating the record
# (a commit written up in a later commit is listed, with that commit, in RECORDED_LATER in the tool)
python tools/ps_audit.py                       # measure every PS item, write docs/PS_AUDIT.md, exit 1 on a failure
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
  engine/config.py       every setting as a dataclass, one field per PS row; presets; YAML load/save;
                         ScheduledChange and the helpers that clean, apply and describe disturbance changes
  engine/simulation.py   the frame loop: source -> tracker -> controller -> gimbal -> telemetry
  engine/sources.py      frame sources: the simulator or a video file (probe_video calibrates from the file)
  engine/telemetry.py    the per-frame Record and the CSV writer
  engine/metrics.py      the PS limits (SPEC), metric definitions, the summary computed at the end
  engine/report.py       the automatic PDF performance report
  engine/naming.py       run labels and output file names
  engine/checks.py       the scenario check: corrected, beyond-the-PS, near-the-limit and cannot-be-met notes
  world/scene.py         backgrounds (starfield, terrain, gradient, flat)
  world/targets.py       beacon paths: line, circular, figure8, random, spiral, sinusoidal, waypoints, static
  world/camera.py        the gimbal: rate, acceleration and pose limits, one frame of latency
  world/disturbance.py   noise, atmosphere, jitter, platform sway, applied in physical order
  world/renderer.py      draws each frame and its ground truth
  world/sprites.py       beacon shapes (square, circle, gaussian, cross, ring, diamond, custom mask)
  perception/detect.py   classical detector, sub-pixel centroid, CNN heat-map detector (ONNX)
  perception/estimator.py  IMM filter: constant velocity, acceleration and turn models
  perception/egomotion.py  picture shift by phase correlation (a vibration hint)
  control/tracker.py     state machine SEARCH/VERIFY/TRACK/COAST/REACQUIRE, identity, faint path
  control/baseline.py    a deliberately simple comparison tracker (tracker.algorithm: baseline), never the default
  control/controller.py  feed-forward plus PID pointing, spiral search in hard mode
  ui_shared.py           the interface definition both front ends draw from
  gui/app.py, theme.py   the PyQt6 desktop application
  cli.py                 run | video | batch | gui
  launcher.py            the packaged executable's entry point (GUI without arguments, CLI with)
webapp/server.py         FastAPI web app over the same engine; static/index.html is the page
webapp/deploy.sh         deploy repository, web app, site and Caddy config to the server
webapp/publish_builds.sh publish a build run's archives on the site
webapp/fetch_builds.sh   download a build run's archives into dist/ (slow on home connections)
configs/scenarios/       17 scenarios plus TEMPLATE_evaluator.yaml
tests/                   test_engine.py, test_ps_compliance.py, test_targets.py, test_review_fixes.py, package_check.py
training/                train_heatmap.py, finetune_from_video.py (the neural detector)
models/beacon_heatmap.onnx   the shipped detector, 0.3 MB
web/                     the progress page (index.html) and its data (progress.json)
tools/                   compare_batches.py, compare_trackers.py, ps_audit.py, gui_screenshot.py, make_demo_video.py
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
  mean SNR at least 3.5 and the right width is promoted. Off in hard mode. While a faint track
  is active, the raw detection is kept when the sub-pixel refit moves it more than 3 px or its
  width exceeds 2.5 times the track's recent median width, and a candidate wider than that is not
  associated: at 3 to 6 sigma the refit could slide onto a neighbouring noise clump (the centre
  jumped several px, the width ballooned to 7.5 px). On lowlight_faint seed 7 this took the run
  from 86 px error and 78.6 percent lock to 2.8 px and 94.8 percent. A faint beacon that
  never moves is not covered; the PS does not ask for one. The chain linking is vectorised with
  NumPy (same greedy order, identical results); it was a Python loop over up to 400 candidates x
  600 chains, and lowlight_faint's 99th-percentile frame time fell from 149 to 160 ms to 26 to 33 ms.
- Read noise and shot noise use independent random planes (they shared one before). Shot noise is
  a Gaussian approximation of Poisson.
- The neural detector (84 thousand parameter heat-map network on a 128 x 128 patch, trained on
  simulator frames, run by ONNX Runtime) only fills gaps when the classical detector finds nothing
  near the prediction, and never overrides it. It is warmed up at start so its first use does not
  stall a run. It supplies 0 percent of measurements in the standard scenarios. It is not used while a faint
  track is active: it was trained on visible beacons, and on a 3 to 6 sigma patch its peak was
  often noise. The model path is
  also looked up from the package folder, so an installed command started elsewhere still loads it.

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
- Designation (PS row 8 and the functional objective: "a designated moving target"): the
  tracker follows `targets[designated]` and the report scores that target. `designation` is
  `appearance` (configured shape, size and brightness), `start` (also told where it starts, as an
  operator or GPS/ephemeris cue would) or `cue` (a point near it: a click on the preview or on a
  video's first frame, or typed). With a cue the search takes the strong candidate nearest the
  cue; after a loss the last estimate becomes the cue. In appearance mode the tracker counts
  ambiguous frames (another spot scored within 0.15). Tracking every beacon at once was dropped:
  the PS metrics are for one target and one camera.
- Coded beacon (beyond the PS, off by default): a target's `code` (for example `10110`) and
  `code_rate_hz` (default 10 bits/s) make it blink that pattern, a 0 bit dimming it to 70 percent
  (`CODE_LOW`). When the designated target has a code, VERIFY lasts until the spot has shown two
  code cycles (1 s for 5 bits at 10 bits/s) and accepts it only when the spot's brightness (core
  mean above the ring median, sampled at the estimate when a dim bit is missed) correlates with the
  code at 0.6 or better at the best phase, the 0 bits at least 12 percent dimmer; a spot plainly
  steady after the shortest stretch that must hold a 0 and a 1 (9 frames for 10110) is turned
  down at once. A rejected spot is followed through the search for 3 s and not picked again. In
  TRACK the check keeps running; two failures half a window apart hand the spot back to SEARCH.
  The appearance audit and the ambiguous-frame count are off for a coded beacon (the code is the
  identity). Codes equal up to where the cycle starts are the same code (the beacon's clock is not
  known); the scenario check says so. Not applied on the faint path (see section 11).
  A 0 bit at 45 percent was tried first: in low light the dim bits fell below the detection
  threshold, the track flickered between TRACK and COAST and slipped onto noise (lowlight_figure8
  40 percent lock), and dropping brightness from the appearance signature to allow it let noise
  clumps in at the screen edge (noisy_line 76 percent). At 70 percent with the full signature
  both hold 100 percent.
- While searching, candidates are re-measured on the current frame. Before 2026-09-23 they were
  re-measured on the last tracked frame (after a loss) or on no picture at all (a crash with
  50 percent salt and pepper). The regression batch is unchanged by the fix.
- Controller: feed-forward of the estimated velocity and acceleration, led by the command latency
  plus the estimator lag; the lag is defined at 30 Hz and scales with the camera rate (a 60 fps
  video halved it). PID kp 5, kd 0, ki 0.8 with anti-windup. The derivative was 0.3 until the PS
  audit: it acted on an error that reaches the controller one frame late and in whole pixels, and
  drove a limit cycle of about +/-10 px, so a still beacon was never settled (mean 6.4 px, peak
  15.6 px). With kd 0 a still beacon is held within 4 px (mean 1.6 px); the integral term stays.
- The acceleration lead (0.25 s) is capped so the path turns by at most `Controller.TURN_MAX` =
  0.1 rad over it. A straight-line extrapolation pointed a fast circling beacon off its path; the
  estimator was fine (within 0.4 to 0.7 px of the truth at every speed, velocity lag 1 to 2
  frames). 450 px circle, 12 s, seed 0, before and after: 1 deg/s 6.3 and 7.1 px; 2 deg/s 6.3 and
  8.4 px; 3 deg/s 16.3 px (fail) and 8.9 px; 4 deg/s 34.3 px at 14 to 19 percent lock and 8.4 px at
  100 percent. Slow or gently curving targets keep the full lead.
- Coasting guard: while coasting or re-acquiring, an estimate more than the search window (160 px)
  outside the picture sends the tracker back to a whole-scene search at once. Before, on
  lowlight_faint seed 2 (30 s) the estimate drifted off the screen: 158 px error, 75.1 percent lock,
  re-acquisition 4.53 s. After: 5.9 px, 96.2 percent, 0.07 s.
- FPS (`fps_mean`) is frames over processing time, 1000 / mean processing ms. It was the mean of
  per-frame rates, which overstates the rate when frame times vary (faint seed 2, 30 s: 92.0 said,
  67.8 true); that value is kept as `fps_inst_mean`, for comparison only.
- Lock means TRACK and the estimate within 30 px of the window centre. Tightening to 20 px did not
  lower error and cut lock under jitter. Tracked rate (share of frames in TRACK) is reported beside
  lock retention so tracker failure and gimbal limits can be told apart.

### 6.4 Disturbances

Applied in physical order (extinction, blur, picture shift, exposure gain, detector noise, frame loss; the last two camera
effects are beyond the PS table and off by default, and a lost frame reaches the tracker as a black picture). Platform motion is a
bounded sway (amplitude at most 20 percent of the screen) with the configured peak speed; a
sustained 20 px per frame shift would leave the screen in seconds. The figure-8 sway is scaled so
its peak equals the setting: it is fastest at its crossing, sqrt(2) times the circle speed, and
set to 20 it peaked at 28.3 px per frame before 2026-09-23. Every pattern stays within the PS
+/-20 px per frame.

Benchmark 2 ground truth: `video_truth` (`--truth`, the Truth CSV button on both front ends, or a
`<video>_truth.csv` or `<video>.csv` beside the video, picked up by the command line and the
desktop app) is a CSV of frame (or t in seconds), x, y in video pixels. Header names are matched
loosely (frame/idx, t/time, x/true_x/cx, y/true_y/cy); without a header the columns are frame, x,
y; a row with a blank or NaN position says the beacon is not in the frame; a frame not listed is filled in when it lies in a gap of at most a third of a second between two visible rows (a file sampled every few frames; used only to judge lock, no error is scored on it), otherwise it counts as "beacon not visible". With it, tracking error, centroiding error,
RMSE and a true lock retention are computed; without it, lock comes from the tracker's own
estimate and can overstate. The report's source line names the file or says "no ground-truth
file".

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
help and welcome text, decoy generation, the seed rule, the camera display stretch, and which
sections stay editable during a run (LIVE_SECTIONS: the disturbances, sent after LIVE_DEBOUNCE_MS). The
desktop app draws it with Qt; the web server sends it to the page at `/api/ui` and computes tiles,
telemetry and captions with the same functions. To add or change a setting, change it in
`engine/config.py` and, if it needs a label or tooltip, in `ui_shared.py`; both front ends pick it
up. Numeric limits live in `engine/config.py` (LIMITS) and every input is clamped there, so no
front end can pass an impossible value; `engine/checks.py` produces the scenario check notes both
panels show. Salt and pepper is shown in percent on both panels and stored as a fraction.
Differences that remain come from the server: views sent at about 15 fps, one run at a time,
files downloaded instead of opened.

## 8. How to verify a change

1. `python -m pytest` must pass (126 tests; `tests/test_ps_compliance.py` pins every PS default).
2. For any change to perception, estimation or control, run the regression batch before and after
   and compare: `python tools/compare_batches.py results/before results/after` must report no run
   worse. Last recorded state (2026-09-24, PR #5 live disturbance changes, against the batch
   after the PS audit fixes): 51 runs compared, all identical, 0 worse. Before that (2026-09-23,
   the PS audit fixes against the previous commit): 0 worse, 5 better (platform maximum lock),
   every other run in its "same" band, although tracking errors dropped by about two thirds (the
   tool flags error increases, not decreases).
3. `python tools/ps_audit.py` must pass: it measures every PS item by running the code and
   writes `docs/PS_AUDIT.md` (39 of 39 on 2026-09-23). CI runs it on the Linux job.
4. For interface changes, take screenshots at 1600 x 1000 and 1366 x 768 with
   `tools/gui_screenshot.py` and look at them; check the web page in a browser too.
5. `python webapp/smoke.py` for the web app.
6. After a release build, `tests/package_check.py` runs automatically on each platform; run it on
   the macOS archives locally as well (Intel through Rosetta: `--arch x86_64`).
7. Update `web/progress.json`, `PROGRESS.md`, `COMPLIANCE.md` and the PDFs so they say what the
   code does.

## 9. How to release

1. Push to `main`. A push that changes the application (code, scenarios, model, tests, build
   files, the bundled manual) starts the build by itself; otherwise start it by hand: GitHub,
   Actions, "Build desktop application", Run workflow (or `gh workflow run build.yml --ref main`).
   About 25 minutes. Each of Windows x64, Linux x64 (Ubuntu 22.04 glibc), macOS Intel and macOS
   Apple silicon runs the tests, the web smoke test, packages with PyInstaller and runs the
   package check. Since 2026-09-23 the workflow builds only Windows and Linux and runs only when
   started by hand or on a tag: a macOS runner minute costs ten Linux minutes and the free
   allowance ran out. The two macOS archives are built with `bash tools/build_macos.sh` on an
   Apple silicon Mac (Intel through Rosetta with an x86_64 Python that uv installs); it runs the
   same smoke test and package check and uploads both. When both GitHub builds pass, the workflow republishes the rolling `latest` pre-release
   and the GitHub packages `argus-desktop` (the archives) and `argus-web` (the web app image,
   started and checked before it is pushed); see README, Releases and packages. For a versioned
   release push a tag: `git tag v1.0.0 && git push origin v1.0.0`. A newer push to `main` cancels
   a main build still running. macOS minutes on a private repository count ten times against the
   Actions allowance, so documentation-only commits do not rebuild.
2. Publish the Windows and Linux archives on the site: `bash webapp/publish_builds.sh` (the
   server downloads them). The macOS archives were uploaded by `tools/build_macos.sh`.
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

- Platform sway plus vibration at the PS maximum (20 + 20 px per frame): 93.4 to 97.2 percent lock,
  21.7 to 23.5 px raw error (platform_max and platform_max_10degs, seeds 0 to 2). A random jump of the
  whole picture every frame cannot be anticipated. Every PDF produced under vibration says so.
- Full stress (decoys, haze, noise, sway and vibration together): 10.3 to 11.3 px, 98.2 to 100
  percent lock over 15 s, seeds 0 to 2; it stacks disturbances the PS lists separately.
- Faint beacon, seeds 0 to 9: acquisition 0.80 to 2.00 s, 2.4 to 3.5 px, lock 94.0 to 97.8
  percent. Seeds 7 and 8 hold 94.8 and 94.0 percent, just above the 5 percent target-loss limit.
- A tracker that observes the whole scene is the documented reading of the PS (section 6.1). A
  low-resolution wide-field finder for acquisition in the window-only reading remains future work.
- Not reproduced: a review reported a 5 px beacon in rain with 10 percent salt and pepper as never
  acquired at about 3 FPS. Our run of that setting (figure of 8, 30 s, seeds 0 to 2): acquisition
  0.77 to 1.37 s, 6.0 to 6.5 px, 100 percent lock, 86 to 99 FPS.
- A hand-held phone video of a single dot: tracked about 99.6 percent, lock about 33 percent,
  because the hand's motion exceeds the gimbal's limits. It is harder than the PS describes and
  must not be tuned to (section 2).
- Look-alikes that start at the same point as the designated beacon cannot be told apart at the
  start. Even with the start cue these runs failed (lock 8 to 25 percent). Look-alikes that start
  apart pass with the start cue (`decoys_identical`, 5 of 5 seeds).
- A coded beacon costs acquisition time: it is confirmed after two code cycles, 0.97 s on every
  clear scenario against 0.60 to 1.17 s steady. On the faint path (3 to 6 sigma) one frame cannot
  show a bit, so the code is not checked there, and the dim bits break the frame-to-frame chains
  that find the beacon: lowlight_faint seed 0, 15 s, acquisition 12.2 s and 63.1 percent lock
  against 1.40 s and 97.8 percent steady. Do not code a beacon at the faint limit. A beacon
  clipped at white (exposure above about 1.2 at intensity 235) shows no 0 bits and fails the code.

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

## 13. Taking over

From 2026-09-24 the project is run by a teammate; the original owner's machine holds nothing the
repository does not, except the server key and the site login. To take over:

1. Access from the previous owner: collaborator rights on `tanmayhutt/SIH26169` (given), your SSH
   public key on the server (`ubuntu@15.206.247.203`), the site login, and `gh auth login` on
   your machine for the publish script.
2. Clone, set up (section 3), run `python -m pytest`, `python tools/ps_audit.py` and
   `python tools/record_check.py`. All three must be clean before you change anything.
3. Builds. GitHub Actions on the main repository is stopped until an Actions budget is set or the
   free minutes reset (macOS minutes cost 10x and used them up on 2026-09-23). Two ways round it:
   run the "Build desktop application" workflow on your own fork (a fork has its own free minutes;
   enable workflows on the fork first) and publish with
   `REPO_SLUG=<your-user>/SIH26169 bash webapp/publish_builds.sh`; or set a small budget on the
   main repository (a Windows plus Linux run is about 100 minutes). The macOS archives need an
   Apple silicon Mac: `bash tools/build_macos.sh`.
4. Every change: the rules in `CLAUDE.md` (the record, the regression batch, one interface
   definition, commit identity). Start a Claude session inside the repository and it reads them.

## 13a. What is left, and who

| Item | Owner | How |
|---|---|---|
| Presentation: fill in the Team ID on slide 1. The PDF in `docs/submission/` carries later corrections (slides 2, 4, 5, 6, 8) that the source deck does not; copy them into the source before exporting again | team | compare with `git log -p docs/submission/` |
| Rebuild the Windows and Linux archives for the 2026-09-23 changes (the macOS ones are current): needs an Actions budget or the monthly reset, then the workflow and `publish_builds.sh` | team | section 9 |
| Hand-driven GUI session on a Windows and a Linux machine | team | `docs/TESTING_GUIDE.md` sections 2 and 3; note the Processing tile value |
| Rehearse the live demonstration | presenter | `docs/DEMO_SCRIPT.md`, once end to end |
| Narrated screen recording, 3 to 5 min (optional) | team | record it while reading `docs/DEMO_NARRATION.md` |
| Evaluators' scenarios and videos | at the event | copy `configs/scenarios/TEMPLATE_evaluator.yaml`; open videos directly |

Proposed extras, none required by the PS: switching the designated target in the middle of a run
(it would be scored in segments); changing the scenario live during a run; manual camera control;
Benchmark 2 comparison against the evaluators'
predefined centroids in their own file format (a truth CSV is already read); a Monte Carlo envelope over thousands of seeds on a large cloud machine;
physically based turbulence; concurrent web runs. Tracking
every beacon at once was dropped as not required.

## 14. History in one paragraph

2026-09-18: problem analysed, input model settled, architecture written. 2026-09-19: engine,
simulator, tracker, desktop app, command line, report, first builds, web app and server. 2026-09-20:
faint-beacon track-before-detect, identity fixes, four-platform builds with per-platform package
checks, waypoint paths (PS row 12 user-defined), demo video and script, output naming scheme.
2026-09-21 to 22: platform limit re-measured at 10 deg/s, frame-rate-independent lag compensation,
tracked-rate metric, interface review and fixes. 2026-09-23: desktop and web unified on one
interface definition; PS row 8 designation (appearance, start or cue, click to designate) found
missing by the owner and added, with target names, user-defined shapes and separate width and
height (rows 9 and 10), a typed start (row 11), the scenario check, salt and pepper in percent
with clamped inputs (the web app had taken 13 as a fraction), editable target appearance in video
mode and the search re-measurement fix; two new scenarios. Then an independent review: FPS as
frames over processing time, the turn-limited lead, the coasting guard, a vectorised faint path,
Benchmark 2 ground truth, independent noise planes, the Near the limit note and fast_circular.
That evening the new PS audit (`tools/ps_audit.py`) found the derivative limit cycle on a still
beacon and the figure-8 sway above 20 px per frame; both were fixed, the faint path got its refit
and width guards (seed 7), and the deck was renamed ARGUS. That night the target controls were
redone as one picker and one Designated tick box with an automatic designation mode, and, with
the free Actions minutes gone (macOS minutes cost 10x), the workflow was cut to Windows and Linux
by hand while `tools/build_macos.sh` builds both macOS archives locally (Intel through Rosetta).
Then disturbances were made changeable during a run (live in both apps, or a `schedule` in a
scenario), replayed exactly from the saved scenario, with per-setting figures in the report. On
2026-09-24 a full review fixed: the start cue (it pointed at a circle's centre, not the beacon),
the desktop click on a video's first frame (mapped with the simulator's geometry), video truth
sampled every few frames (scored as lost lock), sprites drawn up to 0.8 px off their truth,
non-finite and malformed values that crashed a run, the packaged launcher taking `2.5` for a
path, `record_check` (it never flagged anything), front-end state after video mode, and web
input that returned 500s; web runs are now controlled only by the page that started them.
Then camera exposure and frame loss were added as disturbances, and a coded beacon: the
designated beacon blinks a bit pattern and look-alikes are told apart by it, with no start
position or click.
The full commit history is in git.
