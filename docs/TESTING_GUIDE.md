# Manual testing guide

How to exercise every part of the system by hand, what each input does, and what a correct
result looks like. Works the same in the desktop application (`ARGUS`), the web app
(project site) and the command line (`fsoc-tracker`). Values in brackets are the problem
statement (PS) rows they implement.

## 1. How the system works, in one page

1. **Scene.** A 2000 x 2000 px picture is drawn every frame: a sky (starfield, terrain,
   gradient or flat), one designated beacon and optional decoys, then the disturbances of the
   chosen scenario (noise, atmosphere, camera jitter, platform sway).
2. **Camera window.** A 640 x 480 window (4 x 3 degrees, so 22.5 arcsec per pixel) sits on
   that scene where a virtual pan-tilt gimbal points it. The gimbal can turn at most 5 deg/s
   (26.7 px per frame at 30 Hz), starts at the screen centre, and reacts one frame late.
3. **Tracker.** Each frame the tracker detects bright compact spots, chooses the designated
   beacon by its configured size and shape (or by a start or click cue, section 4), measures its centre to a fraction of a pixel,
   predicts its motion with three motion models (constant velocity, acceleration, turn), and
   holds an identity so decoys are not followed. Its state machine reads SEARCH, VERIFY,
   TRACK, COAST, REACQUIRE.
4. **Controller.** From the prediction it commands pan and tilt rates so the beacon sits at the
   window centre, leading the target through the latency and feeding forward its velocity.
5. **Log and report.** Every run gets a folder `results/FSOC_<sim|video>_<name>_seed<N>_<date-time>/`.
   Every frame goes to `<label>_frames.csv`; at the end `<label>_summary.json` and
   `<label>_report.pdf` are written with acquisition time, tracking error, centroiding error,
   lock retention, re-acquisition times, FPS and the definitions of each.

Lock means: state TRACK and the estimate within 30 px of the window centre. Acquisition time
is the first frame with lock. Tracking error is the true beacon to the window centre.
Centroiding error is the measured centre to the true centre. Target loss is 100 minus lock
retention. Tracked rate is the share of frames in TRACK regardless of centring: high tracked
with low lock means the camera could not keep up, not that the beacon was lost.

## 2. Five-minute smoke test

1. Start the application. The window opens with the parameter panel left, tiles top, scene and
   camera views centre, plots below, telemetry right.
2. Scenario: clear line. Start. Expected within 2 s: State tile TRACK locked (green),
   Acquisition about 1 s (green), Tracking error settling to 6 to 8 px (green), Processing well
   above 20 FPS (green). The cyan window on the scene view follows the orange truth circle.
3. Stop. Report. A PDF opens: header with the configuration, a table with pass and fail
   marks against the PS limits, plots, and the metric definitions.
4. Open the results folder next to the application. It holds one folder per run named
   `FSOC_sim_clear_line_seed<N>_<date-time>`, with the four labelled files inside.

If step 2 does not lock within 2 s on clear line, something is wrong with the installation,
not the settings; see the manual, section 2.

## 3. Ready-made scenarios and what each proves

Pick these from the Scenario box. Duration 15 s is enough for each.

| Scenario | What it tests | Expect |
|---|---|---|
| clear_line, clear_circular, clear_figure8 | rows 12, 16 to 20 on a clean sky | acquisition under 1.5 s, error 6 to 8 px, 100% lock |
| clear_random | random walk (row 12) | error about 10 px, lock 98% |
| noisy_line | salt and pepper 10%, Gaussian sigma 20, Poisson (rows 21, 22) | error 7 to 8 px, 100% lock |
| fog_circular | fog preset: contrast, brightness, blur, turbulence (row 24) | error 6 to 7 px, 100% lock |
| lowlight_figure8 | low-light preset (row 24) | error 7 to 8 px, 100% lock |
| lowlight_faint | beacon at 3 to 6 sigma per frame; track-before-detect | acquisition 1.3 to 2.8 s, error 7 to 12 px, lock over 90% |
| platform_jitter | sway 12 px/frame plus vibration 20 px/frame (rows 23, 25) | raw error about 20 px, 14 px with vibration removed, lock 96 to 99% |
| platform_max | both at the PS maximum, 20 + 20 px/frame | lock 76 to 88%, error 25 px: the documented physical limit |
| platform_max_10degs | the same with the gimbal at 10 deg/s | the same result: the motor is not the limit, the random jump is |
| full_stress | three beacons, haze, noise, sway, vibration (row 8) | designated beacon held, error 13 to 15 px, lock 98% |
| hardmode_line | tracker sees only the window; must sweep | acquisition 3 to 12 s (spiral sweep), then as clear line |
| decoys_identical | Remote terminal plus three identical look-alikes starting apart, paths crossing; designation start (row 8) | acquisition 0.60 to 0.73 s, error 5.9 to 7.0 px, 100% lock |
| beacon_shapes | designated 8 x 18 px rectangle among a cross, ring, diamond and custom pattern; designation appearance (rows 9, 10) | acquisition 0.73 to 0.83 s, error 6.1 to 7.1 px, lock 99.5 to 100% |
| TEMPLATE_evaluator | every field labelled by PS row, PS defaults | behaves like clear line; copy it to enter evaluator values |

Picking a scenario runs it exactly as written: its seed and paths are kept and "New seed each
run" is switched off. Tick it to get a different starting position and noise each run; untick
it and set Seed to repeat a run exactly.

## 4. Every input you can change, and what to look for

Change one thing at a time from clear line, press Start, watch the tiles.

### Screen (rows 1, 2)
- Width, Height (px): 2000 x 2000 default; try 1200 x 1200 (faster) or 3000 x 3000 (slower,
  watch Processing). Anything from 64 up is accepted.
- Background: starfield (default), terrain, gradient, flat. Starfield adds point-like stars the
  detector must reject; flat is the easiest.
- Colour camera: yes renders a three-channel frame; the tracker still works on luminance.
  Results should not change.

### Camera (rows 3 to 6, 13 to 15)
- Window width, height (px): 640 x 480 default. A smaller window (320 x 240) makes lock
  harder in hard mode; a larger one easier.
- FOV width, height (deg): 4 x 3 default. Changing it changes pixels per degree, so the same
  5 deg/s becomes more or fewer pixels per frame. The report header prints the IFOV.
- Update rate (Hz): 30 default; 60 doubles the frames and halves the per-frame gimbal step.
- Max pan, Max tilt (deg/s): 5 default, PS allows 5 to 10. Raising to 10 shortens the
  hard-mode sweep and helps fast targets; it does not fix vibration (see platform_max_10degs).
- Hard mode (window only): the tracker sees only the window. Expect SEARCH with a square
  spiral, then TRACK. Acquisition depends on where the beacon started, 3 to 12 s.

### Run section: designation (row 8)
- Extra targets, Identical look: tick Identical look and set 3 extra targets. The scenario check
  shows "Cannot be met: ... look the same as the designated ..." while Designation is
  appearance. Switch Designation to start: the note goes and the designated target is followed.
- Designated: pick another target by name. The scene view marks it "(designated)"; the report
  line "Followed" and the error tiles refer to it.
- Click to designate: before Start, click a target on the preview; it becomes the designated one.
- Designation cue: choose cue and click near a beacon, or type x,y in Cue (x,y). Cue without a
  point gives a "Cannot be met" note.
- Edit target: choose which target the Target section shows and edits.

### Target (rows 7 to 12)
- Name: appears on the scene view, the telemetry first line ("following <name>") and the report.
- Shape: square (default), circle, gaussian, cross, ring, diamond, custom. The detector's size
  prior follows the shape. For custom, type a mask such as 010;111;010 (a plus).
- Width, Height (px): set separately, 5 to 20 per the PS, 10 x 10 default. Width 8, Height 18
  draws a rectangle; a circle with unequal sides is an ellipse. Faint and small (5 px, intensity 100) is the
  hardest; large and bright the easiest.
- Peak intensity (0 to 255): 235 default. Below about 120 on a dark sky the faint path
  engages (watch "detector" in telemetry stay classical, acquisition 1.5 to 3 s).
- Motion: line, circular, figure8, random, spiral, sinusoidal, waypoints, static.
- Speed (px/s): 120 default. Above about 700 px/s (26 px per frame) the 5 deg/s gimbal
  saturates; the report then prints a note about it.
- Radius (px), Period (s): size and speed of the circular, figure-8, spiral and sinusoidal
  paths. Short periods with large radii raise the acceleration and the tracking error.
- Start: random, centre, or "x,y" typed in screen pixels (for example 400,1500).
- Waypoints: for motion waypoints, "x,y; x,y; ..." in screen pixels, looped at Speed.
- Extra targets (decoys): 0 to 8. Each decoy has a different size, brightness and path. The
  first target stays designated; the identity check re-designates if a decoy is followed.

### Disturbances (rows 21 to 25)
- Salt and pepper (%, 0 to 50): 10 is the PS "around 10%" (files store 0.10). At 30 the
  picture is mostly specks and the median filter still holds lock.
- Gaussian sigma (grey levels): 20 is the PS maximum; 40 is beyond it and still tracks.
- Poisson: shot noise proportional to brightness.
- Camera jitter (px/frame): 20 is the PS maximum. Above 8 the raw tracking error rises with
  the jitter; the report prints the vibration-removed error and a sentence explaining why.
- Atmosphere: clear, haze, fog, rain, lowlight. Each is a preset of contrast, brightness, blur
  and turbulence; the Contrast and Brightness fields override the preset when set.
- Platform motion: none, linear, circular, random, spiral, figure8, with Platform speed
  (px/frame, 20 is the PS maximum) and period. Sway moves the whole picture; the tracker
  measures it by phase correlation and adapts its noise model.

### Tracker
- Detector: hybrid (default), classical, cnn. Classical alone should give identical results on
  the simulated scenes; cnn alone is slower and less accurate, it is a fallback.
- Min confidence to acquire (0.62): lower it and stars may be acquired; raise it and faint
  beacons take longer.
- Faint path threshold (3.0 sigma) and min chain SNR (3.5): the faint-beacon path. Higher
  values are stricter.
- Controller gains kp, kd, ki, feedforward, estimator lag: the PID and lead. The defaults were
  tuned on the scenario pack; large changes show up as oscillation on the gimbal plot.
- Use picture-shift estimate: on by default; off makes vibration handling worse.

### Scenario check
Start from clear line and watch the notes below the Run section:
- Salt and pepper 13 %: "Beyond the PS: ... above the PS 'around 10%' (row 21)". The run
  still acquires.
- Camera jitter 25: "Beyond the PS" (row 23). Add linear platform motion at 10 px/frame: also
  "Cannot be met", because 35 px/frame is more than the camera's 26.7 px/frame turn.
- Target speed 900 px/s on a line: "Cannot be met: ... moves at up to 900 px/s but the camera
  turns at most 800 px/s". 600 px/s gives the 70 percent warning.
- A scenario file with `salt_pepper_frac: 13`: "Corrected: ... set to 0.5".
The same notes appear at Start in the status bar, in the end dialog, on page 1 of the report
and in the summary `checks`.

## 5. Benchmark 2, video input

1. Prepare an .mp4 (also .avi, .mov, .mkv) that shows a moving bright spot on a noisy
   background. Any frame size works; the PS says 30 fps.
2. Desktop: Open video. Web: drop the file on the panel. Command line:
   `fsoc-tracker video path/file.mp4`.
3. Check the calibration line: width x height as displayed (rotation applied), average fps,
   frame count, seconds. These should match the file's own properties.
4. Start. The simulator is bypassed and the frames are the scene. No ground truth exists, so
   the tracking and centroiding error tiles read n/a; State, Acquisition, Lock and Processing
   still work.
5. Open `<label>_frames.csv`: `det_x`, `det_y` are the measured centroids per frame for comparison with
   the evaluators' predefined values; `est_x`, `est_y` the filtered estimate; `mode` and
   `locked` the state. The report carries acquisition, re-acquisition, lock retention and FPS.

Things to try: a phone video (variable frame rate is handled and flagged), a video with the
beacon leaving and re-entering the frame (watch COAST, REACQUIRE, then TRACK), and a video
with several bright spots (set Width and Height and the shape to the real beacon's, which stay
editable in video mode, or click the beacon on the first frame to set a designation cue).

## 6. Things that should fail, and how they fail

- Speed above about 700 px/s: the gimbal saturates, error grows, the report notes it.
- Jitter above 25 px per frame: lock flickers; the vibration-removed error remains sensible.
- Intensity below about 60 on a bright sky: no detection, SEARCH stays, the report shows
  acquisition n/a. This is correct behaviour: the beacon is not visible.
- A video with no bright spot at all: SEARCH throughout, lock 0%.
- Hard mode with Max pan at 5 deg/s and a beacon in a far corner: acquisition up to 12 s.
- Look-alikes that start at the same point as the designated beacon: they cannot be told apart
  at the start; even with designation start these runs held 8 to 25% lock.
- Impossible values (salt and pepper 13 in a file, a negative size): clamped to the accepted
  range and shown as "Corrected" in the scenario check, never run as typed.

## 7. Command line and batch

```
fsoc-tracker run -s configs/scenarios/noisy_line.yaml --seed 3 --duration 20
fsoc-tracker video path/to/file.mp4 --out results/video1
fsoc-tracker batch -s configs/scenarios/*.yaml --seeds 0-4 --duration 15
```

`batch` writes one folder per scenario and seed plus `envelope.md`, the worst and mean per
scenario. Running the same command twice gives identical numbers: the engine is deterministic
for a given seed.

## 8. Web app specifics

The web page is the desktop window in a browser: every section of this guide applies to it
unchanged, including Pause, Step, Save scenario, Screenshot, Results, Manual, About and the keys.
Differences that come from the server:

- Views update about 15 times a second; plots, log and report cover every frame.
- One run at a time per server; a second visitor sees the run in progress and can watch it.
- The address carries `#run=<id>` while a run is active; anyone with the link can watch.
- Results lists the runs on the server with their files; nothing opens on your disk.
- Desktop app, top right: the archive for the visitor's platform, with install notes.

## 9. Automated checks, for completeness

```
python -m pytest                       # 37 tests: geometry, gimbal, paths, centroid, IMM, metrics, closed loop, identity, decoys, video, desktop panel, PS rows, targets and designation
python webapp/smoke.py                 # web app: start, run a scenario, fetch the report
python tests/package_check.py dist/ARGUS-<platform>.zip   # a built archive, as a user would run it
```
