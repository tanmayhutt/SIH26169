# Knowledge transfer: the problem statement and our solution, explained completely

This document is for someone who has never seen the project. It explains, in plain language:

- **Part A**: everything the problem statement (the PDF `26169.pdf`) says, line by line, including
  every number in its parameter table and every word of its evaluation criteria.
- **Part B**: how we solve the problem, step by step, and why each step is done the way it is.
- **Part C**: the journey: what we did in what order, what we misread and corrected, what we tried
  and threw away.
- **Part D**: the measured results and the honest limits.
- **Part E**: how to demonstrate it, how to answer likely questions, and a glossary.

Other documents go deeper on one topic: `docs/HANDOVER.md` (working on the code), `COMPLIANCE.md`
(row-by-row compliance), `docs/TECHNICAL_REPORT.md` (the submitted report), `docs/USER_MANUAL.md`
(the submitted manual), `docs/TESTING_GUIDE.md` (manual tests), `docs/DEMO_SCRIPT.md` (the live demo).

---

# Part A. The problem statement, completely

## A1. Where it comes from

| Item | Value in the PDF |
|---|---|
| Competition | Smart India Hackathon (SIH) 2026 |
| Problem statement ID | 26169 (the file is `26169.pdf`); the PDF's first line reads "Problem Statement 4" |
| Organisation | Department of Space / Indian Space Research Organisation (ISRO); it is from ISRO's Space Applications Centre (SAC) |
| Category | Software (not hardware) |
| Theme | Smart Automation, Space Technology |
| YouTube / video link | NA (none given) |
| Dataset link | NA (none given): no data is supplied, so we must create our own test data |
| Length | 3 pages. The PDF was produced on 27 August 2026 |
| Our team and project name | Team Blank Point; project and software name ARGUS (earlier LAKSHYA and FSOC Tracker) |

The mentors listed on the SIH portal for this statement are Pranav Kumar Pandey, Koushik Basak and
Abhishek Khanna. They are not named in the PDF itself.

The PDF has these sections, in order: Title; Description (Background, Description); Parameters and
Specifications (a Functional Objective and a 25-row table); Key Milestones (the heading is present
but empty); Expected Solution (with eight "shall be able to" items); Deliverables (five, plus an
optional video); Evaluation Method and Criteria (a four-stage table with marks).

## A2. The title, word by word

> "Development of an AI-Based Virtual Camera Tracking System for Coarse Alignment of Mobile Free
> Space Optical Communication (FSOC) Terminals"

- **FSOC (Free Space Optical Communication)**: sending data through the air (or space) on a beam
  of light, usually a laser, instead of radio waves or a fibre cable.
- **Terminal**: one end of the link, the box with the laser, the receiver and the optics.
- **Mobile**: the terminals move: on satellites, drones (UAVs), vehicles. So the two ends keep
  moving relative to each other.
- **Coarse alignment**: the first, rough stage of pointing one terminal at the other, getting the
  other terminal into view and keeping it there. (A second, "fine" stage then does the precise
  pointing; that is not our job.)
- **Camera tracking**: coarse alignment is done by a camera that looks for the other terminal and
  a motorised mount (pan-tilt) that turns the camera to follow it.
- **Virtual**: we do all of this in software. No real camera, no real motor, no real laser.
- **AI-based**: the solution should use artificial intelligence or computer vision where it helps.

## A3. The Background section, explained

What the PDF says, and what it means:

1. **"FSOC offers unprecedented advantages for next-generation mobile networks, including
   gigabit-to-terabit data rates, license-free spectrum operation, high immunity to electromagnetic
   interference."** Light can carry far more data than radio (billions to trillions of bits per
   second); nobody needs a government licence to use light frequencies the way they do for radio;
   and light links are not disturbed by electrical noise.
2. **"However, deploying FSOC links between mobile platforms (satellites, UAVs) presents a severe
   challenge of pointing, acquisition and tracking (PAT) of highly narrow laser beams."** A laser
   beam is extremely narrow. If both ends are moving, keeping the beam on the other terminal is
   very hard. The industry name for this is PAT: **P**ointing (aiming), **A**cquisition (finding
   the other end in the first place), **T**racking (staying on it).
3. **"PAT typically happens in two stages: coarse alignment and fine alignment."** First a wide
   camera finds and follows the other terminal roughly; then a precise mechanism steers the laser
   onto it exactly.
4. **"Coarse alignment is one of the key challenges of PAT, where the transmitting terminal must
   first locate and maintain the remote terminal within its camera Field-of-View (FOV)."** Our
   job in one sentence: find the other terminal and keep it inside the camera's view. FOV
   (field of view) means how much of the world the camera sees, measured as an angle.
5. **"Developing and testing such algorithms on real hardware requires expensive cameras, pan-tilt
   mechanisms, and optical components & equipment. A software based virtual camera tracking
   provides an inexpensive and accessible platform for algorithm development and learning."**
   This is why the problem asks for software: a realistic simulation lets people develop and
   test tracking methods without buying the hardware.

## A4. The Description section, explained

- **"Unlike conventional radio-frequency systems, FSOC relies on a highly directional optical
  beam. Even a small angular error can prevent successful communication."** A radio antenna
  spreads its signal widely, so rough pointing is fine; a laser does not, so a tiny aiming error
  means no link at all.
- **"Before fine pointing mechanism can take over, a coarse alignment stage must:"**
  1. **"Observe the surrounding environment"**: look at the scene.
  2. **"Acquire and detect the remote terminal or beacon"**: find the other terminal. In practice
     the remote terminal carries a **beacon**, a bright light that is easy to see.
  3. **"Estimate the position"**: work out exactly where it is.
  4. **"Continuously adjust the pointing direction to maintain visibility"**: keep turning the
     camera so the beacon stays in view.
- **"The participants shall develop this coarse alignment process in software, allowing to develop
  and validate tracking algorithms without specialized hardware and setup. The following section
  provides reference parameters and performance criteria to be considered for the software
  development."** So the table that follows is the specification we are judged against.

## A5. The Functional Objective

> "Develop a software system that autonomously detects, identifies, and continuously tracks a
> designated moving target within a virtual scene by controlling a virtual camera viewport."

Each word matters:

- **autonomously**: no human steering; the software does it by itself.
- **detects**: finds the beacon in the picture.
- **identifies**: tells the right beacon apart from others (the table allows multiple targets, so
  there can be decoys).
- **continuously tracks**: follows it for the whole run, not just once.
- **designated**: one particular target is "ours", the one we were told to follow.
- **moving**: it moves, along the paths listed in row 12.
- **virtual scene**: a simulated picture of the world.
- **by controlling a virtual camera viewport**: the software turns a simulated camera; the
  "viewport" is the part of the scene the camera currently shows.

## A6. The parameter table, every row

The table has four groups: camera parameters (rows 1 to 6), target parameters (7 to 12), camera
motion constraints (13 to 15), performance specifications (16 to 20), and disturbances and noise
(numbered 21, 2, 3, 4, 5 in the PDF; this is a numbering slip in the PDF, and everyone reads them as
rows 21 to 25, which is what we do).

"Suggested value" is the PS's default; "Remarks" tells us what may vary. "User-defined" means the
user of our software must be able to change it.

### Camera parameters

| Row | Parameter | Suggested value | Remarks | Plain meaning | What we built |
|---|---|---|---|---|---|
| 1 | Screen Size (min.) | 2000 x 2000 pixels | Optional: User-defined | The whole simulated world is a picture at least 2000 by 2000 pixels | Default 2000 x 2000, editable (Screen width and height) |
| 2 | Camera Type | Monochrome, Focal Plane Array | Optional: Colour | A black-and-white image sensor (a focal plane array is the grid of light-sensitive pixels); colour is optional | Monochrome by default; "Colour camera" option renders three channels, the tracker works on brightness |
| 3 | Camera Resolution | 640 x 480 pixels | Optional: User-defined | The camera image is 640 wide and 480 high | Default 640 x 480, editable |
| 4 | Camera FOV | User-defined | Default: 4° x 3° | The camera sees 4 degrees wide and 3 degrees high | Default 4 x 3 degrees, editable; so one pixel = 4/640 = 0.00625 degrees = 22.5 arcseconds |
| 5 | Camera update Rate | 30 Hz (min.) | | At least 30 pictures per second | Default 30 Hz, editable upward |
| 6 | Initial Camera Position | Centre of the Screen | | The camera starts pointing at the middle of the world | Starts at the centre |

### Target parameters

| Row | Parameter | Suggested value | Remarks | Plain meaning | What we built |
|---|---|---|---|---|---|
| 7 | Target Type | Beacon Spot | | The thing to follow is a bright spot of light | A rendered bright spot with realistic blur |
| 8 | Number of Targets | 1, mandatory | multiple optional | One target is required; more are allowed | Up to 9 named targets (1 plus up to 8 "Extra targets"); all are detected, the designated one is followed and scored. Designation by appearance, by a start cue or by a point (click or typed) |
| 9 | Target Shape | User-defined | Default: Square | The spot's shape can be chosen; square by default | Square (default), circle, Gaussian, cross, ring, diamond, and custom (a 0/1 mask or a PNG) |
| 10 | Target Size | 5-20 x 5-20 pixels (user-defined) | Default: 10 x 10 | The spot is 5 to 20 pixels wide and 5 to 20 pixels high | Width and height set separately, default 10 x 10 (a square with unequal sides is a rectangle) |
| 11 | Initial Target Location | User-defined | Default: Random | Where the spot starts; random by default | Random (default), centre, or exact x,y typed in the panel or the file |
| 12 | Motion | Selectable, at least four: Straight Line, Circular, Figure of 8, Random | Optional: Spiral, Sinusoidal, User-defined | How the spot moves; four paths are mandatory, three optional | All seven: line, circular, figure of 8, random, spiral, sinusoidal, and user-defined (a list of waypoints); plus static |

### Camera motion constraints

| Row | Parameter | Suggested value | Remarks | Plain meaning | What we built |
|---|---|---|---|---|---|
| 13 | Max. Pan Speed | 5-10 °/s (User-defined) | Default: 5 °/s | The camera can turn left-right at most 5 degrees per second | Enforced in the gimbal model; 5 by default, editable 5 to 10 (wider range allowed) |
| 14 | Max. Tilt Speed | 5-10 °/s (User-defined) | Default: 5 °/s | Same for up-down | Same |
| 15 | Update Interval | ≥ 20 Hz | | Camera commands are sent at least 20 times a second | A command every frame, at 30 Hz |

**Why rows 13 and 14 matter so much:** 5 degrees per second, at 22.5 arcseconds per pixel and 30
frames per second, is **26.7 pixels per frame**. If the beacon moves faster than that across the
picture, the camera physically cannot keep up. This single number shapes much of the design.

### Performance specifications (the pass marks)

| Row | Parameter | Suggested value | Plain meaning | How we measure it |
|---|---|---|---|---|
| 16 | Acquisition Time | ≤ 2 sec | From the start, the beacon must be found and locked within 2 seconds | Time of the first "locked" frame |
| 17 | Tracking Error | ≤ 10 pixels | While tracking, the beacon must stay within 10 px of the camera centre on average | Mean distance, true beacon to camera-window centre, after acquisition |
| 18 | Target Loss | < 5% | The beacon may be lost in fewer than 5 percent of the frames | 100 minus lock retention |
| 19 | Re-acquisition Time | ≤ 1 sec | If lost, it must be found again within 1 second | Longest gap between losing and regaining lock; a loss never regained counts with its length |
| 20 | Processing Speed | ≥ 20 FPS | The software must process at least 20 frames per second | Frames over processing time: 1000 / mean processing ms per frame |

The PDF does not define "lock", "tracking error" or "centroiding error" precisely. Our definitions
are in section A10 and are printed inside every report.

### Disturbances and noise

| Row (PDF number) | Parameter | Suggested value | Remarks | Plain meaning | What we built |
|---|---|---|---|---|---|
| 21 (21) | Image Noise | 1. Salt & Pepper (around 10% of image), 2. Gaussian & 3. Poisson | User Selectable (one or more) | Three kinds of camera noise, any combination: random black and white pixels (about 10 percent), smooth random noise, and light-dependent "shot" noise | All three, each switchable independently; salt and pepper shown in percent on both panels (stored as a fraction) |
| 22 (2) | Max. Standard Deviation of Noise | 20 pixels | User-defined | How strong the Gaussian noise can be (the PDF says "pixels"; it means grey levels) | Gaussian sigma, default up to 20, editable |
| 23 (3) | Max. Camera Jitter | ± 20 pixels / frame | User-defined | The camera shakes; the picture can jump up to 20 px every frame | Camera jitter, up to 20 px per frame (more allowed) |
| 24 (4) | Atmospheric Disturbance | Clear, Haze, Fog, Rain, Low light | User-defined reduction in contrast and brightness | Weather that washes out the picture | Five presets, each with editable contrast, brightness, blur and turbulence |
| 25 (5) | Platform Motion | ± 20 pixels/frame (max.) | User selectable. Default/Mandatory: Linear. Optional: Circular, random, spiral, figure of 8, etc. | The platform carrying the camera itself moves, dragging the whole picture, up to 20 px per frame | Linear (mandatory) plus circular, random, spiral, figure of 8 |

## A7. The Expected Solution section

> "Participants shall develop an AI-assisted camera tracking system capable of automatically
> detecting and continuously tracking a moving optical beacon in a simulated video stream while
> controlling a virtual pan-tilt camera."

Note two phrases: **"AI-assisted"** (AI helps; it need not do everything) and **"simulated video
stream"** (the software itself generates the video it tracks).

"The developed software shall be able to:" (these eight are mandatory functions):

| # | The PS says | What it means | Where it is in our software |
|---|---|---|---|
| 1 | Generate a configurable virtual environment | Make the simulated world, with settings | Scene generator (starfield, terrain, gradient, flat), Screen section |
| 2 | Generate one or more moving targets | Make beacons that move | Beacon paths, Target section, Extra targets |
| 3 | Implement a movable virtual camera | A camera that can be turned | Gimbal model with rate, acceleration and pose limits |
| 4 | Detect the target beacon automatically | Find the beacon with no human help | Classical detector plus neural backup |
| 5 | Track the beacon continuously using computer vision | Keep following it | Estimator, state machine, identity |
| 6 | Control and reposition the virtual camera | Turn the camera to follow | Controller (feed-forward plus PID) |
| 7 | Generate and introduce disturbances due to atmospheric turbulence, platform vibrations, camera motion, noise, etc., in the virtual camera feed | Make the picture realistically bad | Disturbance model: noise, weather, jitter, platform sway |
| 8 | Display tracking performance and statistics in real-time | Show how well it is doing, live | Live tiles, plots, telemetry in the desktop app and the web app |

## A8. The Deliverables section

"Each participating team shall submit the following mandatory deliverables:"

| Deliverable | Exact PS requirement | What we deliver |
|---|---|---|
| Software Application | "A standalone executable application implementing the complete virtual camera tracking system. The application shall provide all the mandatory functions and features as described above." | Native desktop builds for Windows, Linux, macOS Intel and macOS Apple silicon; runs with no installation and no internet |
| Source Code | "Complete source code with proper documentation. The code shall be modular and adequately commented." | This repository, modular packages, docstrings, documents |
| Technical Report | "about 10-15 pages containing problem understanding, system architecture, description of software modules, tracking methods, AI methods (if used), test methodology, performance analysis and future improvements" | `docs/TECHNICAL_REPORT.pdf`, 13 pages, all listed sections |
| User Manual | "description of installation of software, application operation, parameter configuration, GUI description, etc. A 3-5 minutes video may also be provided as an optional deliverable for demonstration of the application." | `docs/USER_MANUAL.pdf`; a demo video of about 4 minutes |
| Performance Log | "The software should be capable of automatically generating a performance report containing simulation duration, FPS, acquisition time, average and maximum tracking error, lock retention rate, processing time, etc." | Every run writes a PDF report, a per-frame CSV and a summary file, automatically |

Note "AI methods (if used)": the PS itself allows a solution where AI is a helper, not the core.

## A9. The Evaluation Method section

"The solutions developed by participating teams will be evaluated using multi-layered evaluation
method." Four stages:

| Stage | Marks | What happens | What they judge |
|---|---|---|---|
| Functional Verification | 20% | "Teams are given 10-15 minutes to demonstrate the software and its functionality." | 1. Implementation of all mandatory functions. 2. Operational success. 3. GUI |
| Benchmark Performance-1 | 30% | "Each team will be given few scenarios." | 1. Execution of the scenario. 2. Log of Centroiding error. 3. Automatically generated performance logs |
| Benchmark Performance-2 | 30% | "Each team will be given a few video files (.mp4) @30 fps, covering a complete screen with noise and moving beacon spot. The software needs to bypass its PTZ camera and take this video as an input to the coarse pointing system." | 1. Comparison of Centroiding error with predefined error values. 2. Performance w.r.t. various parameters like RMSE, acquisition and re-acquisition time, Lock retention rate, FPS, etc. |
| Technical Evaluation | 20% | "Teams present their approach, methods, architecture, design, etc to the evaluators." | 1. Understanding of the problem. 2. System architecture and software design. 3. Selection of Algorithms. 4. AI and computer vision. 5. Innovation and Novelty. 6. Technical Documentation and Presentation. 7. Technical Discussion and Q&A |

What this tells us:

- **60 percent of the marks are benchmarks** run by the evaluators with their own inputs. The
  software must be robust to inputs we have never seen, not tuned to our own tests.
- **Benchmark 1** gives us scenarios, meaning parameter settings: our simulator must accept any
  combination of the table's values.
- **Benchmark 2** gives us videos. "PTZ camera" means pan-tilt-zoom camera, i.e. our virtual
  camera. "Bypass its PTZ camera and take this video as an input" means: skip our own scene
  generator and feed their video frames into the tracker instead. "Covering a complete screen"
  means each video frame is the whole scene (like our 2000 x 2000 screen), not the 640 x 480
  camera view.
- **"Log of centroiding error" and "comparison of centroiding error with predefined error values"**:
  they will compare where we say the beacon centre is, frame by frame, with where they know it is.
  So we must log our measured centre for every frame.
- **RMSE** (root mean square error) is named explicitly, so we report it.

## A10. What the PDF leaves open, and what we decided

| Open question | Our decision | Why |
|---|---|---|
| Does the tracker see the whole screen or only the 640 x 480 camera view? | It sees the whole screen by default ("observe the surrounding environment", "simulated video stream"); a "hard mode" restricts it to the camera view and makes it search | With only the camera view, a blind search at 5 deg/s takes up to 12 s, which cannot meet 2 s acquisition; the PS's own words describe observing the environment |
| How big is the screen in degrees? | One screen pixel equals one camera pixel, so the 2000 px screen spans 12.5 degrees | The only anchor the PS gives is 4 degrees over 640 px |
| What is "tracking error"? | Distance from the true beacon to the camera-window centre | It measures pointing, which is the job |
| What is "centroiding error"? | Distance from our measured beacon centre to the true centre | It measures detection accuracy, which Benchmark 2 compares |
| What is "lock"? | Tracker in TRACK state and its estimate within 30 px of the window centre | Acquisition, loss and re-acquisition all need a clear definition |
| What does "Max. standard deviation of noise: 20 pixels" mean? | 20 grey levels of Gaussian noise | Noise strength is measured in brightness, not position |
| Can a 20 px per frame platform shift be sustained? | Modelled as a sway with that peak speed, bounded within the screen | A steady 20 px per frame shift would leave the screen in seconds |
| How is the "designated" target designated? | Three modes: by appearance (shape, size, brightness), by a start cue (where it starts, as an operator or GPS/ephemeris cue would) or by a point near it (a click or typed x,y) | The PS says "designated moving target" but not how; identical look-alikes cannot be told apart by appearance alone |
| What role should AI play? | Classical computer vision carries the specification; a small neural network fills gaps | Reliability and speed must never depend on a model; the PS says "AI-assisted" and "AI methods (if used)" |

## A11. Numbers that follow from the PS

| Quantity | Value | How it is derived |
|---|---|---|
| One camera pixel | 0.00625 deg = 22.5 arcsec | 4 degrees / 640 px |
| Screen span | 12.5 x 12.5 deg | 2000 px x 0.00625 |
| Fastest camera turn per frame | 26.7 px | 5 deg/s / 0.00625 / 30 Hz |
| Centre to corner of the screen | 0.95 s | the diagonal distance at 5 deg/s, target position known |
| Allowed tracking error | 10 px = 0.0625 deg | row 17 |
| Platform motion at the PS maximum | 20 px per frame = 75 percent of the turn budget | row 25 against row 13 |
| Time budget per frame at 20 FPS | 50 ms | row 20 |

---

# Part B. How we solve it, step by step

## B1. The big picture

The software has two halves inside one program, plus the parts around them:

```
SIMULATOR (makes the world)                      TRACKER (does the job)
scene -> beacons -> disturbances -> picture  ->  detect -> measure centre -> predict -> decide -> steer camera
                                                           |                                         |
                        ground truth (for scoring) --------+----> metrics, per-frame log, PDF report
```

- The **simulator** is not a side tool. It is half the product: it covers the first three "shall"
  items and row 1 to 15, it runs Benchmark 1, and it is the only source of ground truth (where the
  beacon really is) and of training data for the neural network.
- For **Benchmark 2**, the evaluators' video replaces the simulator's picture. Everything after
  that runs unchanged. It is one pipeline with two possible sources, not two programs.
- The tracker **never sees the ground truth**. We proved it: we ran the same scenario twice, the
  second time with the truth deleted before the tracker ran, and got identical results to a
  millionth of a pixel.
- Every run is **repeatable**: the same scenario file and seed give the same result on every
  computer.

## B2. Step 1: build the world (the simulator)

1. **Scene**: a 2000 x 2000 sky: starfield (dim points the tracker must ignore), terrain,
   gradient or flat.
2. **Beacons**: the designated beacon (square by default, 10 px, bright) moves along the chosen
   path at the chosen speed. Other targets, if any, have their own names, shapes, sizes,
   brightnesses and paths, or copy target 1's look ("Identical look").
3. **Camera and gimbal**: a 640 x 480 window placed on the scene where a virtual pan-tilt mount
   points it. The mount obeys the speed limit (5 deg/s), an acceleration limit, and reacts one
   frame late, like a real motor.
4. **Disturbances, applied in physical order** (the order light actually experiences them):
   atmosphere (contrast and brightness loss, blur, turbulence), then the platform sway and camera
   jitter (which move the whole picture), then the sensor noise (salt and pepper, Gaussian,
   Poisson). Doing it in this order, instead of adding filters at the end, makes the picture
   behave like a real camera.

## B3. Step 2: find the beacon (detection)

In plain words: look for bright, compact spots of about the right size, and ignore everything else.

1. **Remove specks** with a median filter, but only when the noise is really salt and pepper; on a
   dark sky a median filter would also erase a faint beacon.
2. **Subtract the background** (a heavy blur of the image estimates the smooth sky).
3. **Matched filter**: blur at the beacon's expected size. This strengthens a spot of that size
   and weakens single-pixel noise and point-like stars.
4. **Threshold**: keep pixels well above the noise level. The noise level is measured robustly, so
   bright stars cannot fool it.
5. **Keep spot-shaped blobs**: right area, not a streak, filled in.
6. **Score each blob**: how strong it is against the noise, how bright, and how well its size
   matches the configured beacon. Stars score about 0.55, beacons 0.67 (low light) to 0.96
   (clear); a new track needs at least 0.62.

## B4. Step 3: measure the centre precisely (centroiding)

The beacon's centre is measured to a fraction of a pixel: a brightness-weighted centre, then a 2D
bell-curve (Gaussian) fit. Accuracy is about 0.01 px in clear air and 0.1 to 0.2 px under heavy
noise. This number is the "centroiding error" Benchmark 2 judges.

## B5. Step 4: predict where it will be (estimation)

The camera reacts one frame late and turns slowly, so we must aim where the beacon will be, not
where it is. An **IMM filter** (Interacting Multiple Model) runs three motion models at once:
steady speed, speeding up or slowing down, and turning. It mixes them by how well each explains
the recent motion. This handles lines, circles, figure-eights and random paths without being told
which one is running.

Camera shake is measured from how much the measurements jump around the prediction, and the filter
then trusts each single frame less, so it averages the shake out instead of chasing it.

## B6. Step 5: decide what to do (the state machine) and keep the right target (identity)

The tracker is always in one of five states:

| State | Meaning | What it does |
|---|---|---|
| SEARCH | nothing found yet | detect on the whole picture |
| VERIFY | a candidate was found | confirm it in 3 of the next 4 frames, so noise is not mistaken for the beacon |
| TRACK | following | detect near the prediction only, update the estimate |
| COAST | missed a frame or two | keep going on the prediction |
| REACQUIRE | lost for longer | search a growing area around the prediction, then fall back to SEARCH |

While coasting or re-acquiring, the prediction can drift. If it lies more than the search window
(160 px) outside the picture, the tracker goes back to a whole-scene search at once instead of
following an estimate that has run off the screen.

**Designation** (row 8, multiple targets): every target has a name (default "Target N"). All are
detected; the tracker follows the designated one and the report scores it. It is designated in
one of three ways: **appearance** (the configured shape, size and brightness), **start** (the
tracker is also told where it starts, as an operator or GPS/ephemeris cue would) or **cue** (a
point near it: a click on the preview before a run, a click on a video's first frame, or typed
x,y). With a cue, the search takes the strong candidate nearest the cue; after a loss the last
estimate becomes the cue. In appearance mode the tracker counts "ambiguous frames" (another spot
scored within 0.15) and the report shows the count. We do not track every beacon at once: the PS
metrics are for one target and one camera.

**Identity**: the tracker remembers what the designated beacon looks like
(size, brightness, width) and rejects spots that look different. Every half second it checks the
whole picture in case it is following a decoy, and switches back if another spot matches the
configured beacon clearly better. When two spots cross, it does not let its memory of the beacon
blend with the merged spot.

## B6a. Checking the scenario before it runs

Every numeric input is clamped to its accepted range in the engine, for every front end. A
scenario check then writes notes, shown live in the panel, at Start, in the end-of-run dialog, on
page 1 of the report and in the summary file:

- **Corrected**: an out-of-range value was clamped (for example salt and pepper 13 becomes 0.5).
- **Beyond the PS**: a value outside the PS table, with the row named (for example jitter above
  20 px per frame, row 23).
- **Near the limit**: the designated beacon moves above 70 percent of the camera turn rate. It can
  be done, with little margin.
- **Cannot be met**: a physical limit, for example a beacon faster than the camera can turn
  (800 px/s at 5 deg/s), or look-alikes of the designated target in appearance mode.

Values inside the PS envelope give no note.

## B7. Step 6: steer the camera (control)

The command to the mount has two parts:

- **Feed-forward**: turn at the speed the beacon is predicted to move, leading it by the mount's
  delay. This does most of the work.
- **PI correction**: a small correction proportional to the remaining error (kp 5) and to its sum
  over time (ki 0.8). The derivative gain kd is 0. It was 0.3 until 2026-09-23: the error reaches
  the controller one frame late and in whole pixels, so a derivative on it drove a limit cycle of
  about +/-10 px. On a still beacon the camera oscillated forever (mean 6.4 px, peak 15.6 px). With
  kd 0 a still beacon is held within 4 px (mean 1.6 px).

The lead is defined at 30 Hz and scales with the camera rate, so a 60 fps video is handled
correctly. Commands never exceed the speed limit; the report says when the mount was at its limit.

The lead is also capped on tight curves. A fixed 0.25 s lead extrapolates in a straight line; on a
fast circle that points the feed-forward off the path. So the lead is shortened until the path
turns by at most 0.1 rad over it. Slow or gently curving beacons keep the full lead. On a 450 px
circle at 4 deg/s (80 percent of the camera turn rate) the error fell from 34.3 px at 14 to 19
percent lock to 8.4 px at 100 percent lock (4.6 to 5.3 px now, with kd 0).

## B8. Step 7: measure and report (the performance log)

Every run writes one folder `results/FSOC_<sim|video>_<name>_seed<N>_<date-time>/` with four files:

- `..._frames.csv`: one row per frame (about 45 columns): time, state, detection, estimate,
  camera position, commands, truth, errors, processing time. This is the centroiding-error log
  Benchmark 1 asks for.
- `..._summary.json`: every metric with its definition and pass or fail.
- `..._report.pdf`: the automatic performance report: specification table with pass and fail,
  plots, notes, definitions.
- `..._scenario.yaml`: the exact settings, so the run can be repeated.

Metrics reported: duration, frames, FPS (frames over processing time; the mean of per-frame
rates is kept beside it for comparison only, since it overstates the rate when frame times vary),
acquisition time, tracking error (mean, maximum, RMSE, and
with vibration removed), centroiding error (mean, maximum, RMSE), lock retention, tracked rate,
target loss, re-acquisition count and times, processing time, gimbal saturation.

## B9. Step 8: Benchmark 2, the video input

1. Open the video (desktop), drop it on the page (web), or `fsoc-tracker video file.mp4`.
2. The software reads the file's real size (applying any rotation tag, as phones write), its real
   frame rate (checked against the timestamps), and its frame count, and sets the screen size and
   update rate to match. The camera window, field of view and speed limits stay as configured,
   because the video cannot tell us those.
3. Each frame becomes the scene; the simulator and its disturbances are skipped.
4. A video carries no ground truth of its own. Without a truth file, tracking and centroiding
   error read "n/a" and lock is judged from the tracker's own estimate, which can overstate it; the
   log still records our measured centre in every frame (`det_x`, `det_y`) for the evaluators'
   comparison, and acquisition, re-acquisition and FPS are measured as usual.
5. With a truth file (a CSV of frame or time, x, y in video pixels; a row with a blank or NaN position says the beacon is not in the frame; a frame not listed is filled in when it lies in a gap of at most a third of a second between two visible rows (a file sampled every few frames; used only to judge lock, no error is scored on it), otherwise it counts as "beacon not visible"), tracking error, centroiding error, RMSE and a true lock retention are
   computed against the evaluators' positions. Give it with `--truth truth.csv`, the "Truth CSV"
   toolbar button (desktop and web), or name it `<video>_truth.csv` next to the video. On a
   noisy_line clip rendered to .mp4 with its truth: tracking error 4.85 px, centroiding error
   0.188 px.

## B10. Step 9: where the AI is

- A small neural network (84 thousand parameters) looks at a 128 x 128 patch around the predicted
  position and draws a "heat map" of where the beacon probably is.
- It was trained on frames our simulator rendered, with exact labels, so no external dataset was
  needed (the PS gives none).
- It runs through ONNX Runtime, a small engine, from a 0.3 MB file; the training library is not
  shipped.
- It is used only when the classical detector finds nothing near the prediction, and never
  overrides it. It is not used while a faint track is active: it was trained on visible beacons,
  and on a 3 to 6 sigma patch its peak was often noise. It is loaded and warmed up at start so its first use does not freeze a run.
- Honest assessment: it is a gap filler. In the standard scenarios it supplies 0 percent of the
  measurements, because the classical path does not miss there; on a real phone video it supplied
  about half the measurements.

The computer vision (detection, centroiding, matched filtering, track-before-detect) and the
estimation are the core; the AI is a safety net. This matches "AI-assisted" in the PS and keeps the
speed and reliability independent of a model.

## B11. Step 10: faint beacons (track-before-detect)

In low light a beacon can be so dim that in any single frame it looks like the noise around it.
Noise sparkles appear and vanish at random, but a real beacon moves along a smooth line. So when
nothing clear is found, the tracker follows many weak candidates across frames and keeps only a
chain that moves consistently, is hit in 6 of 8 frames, and has the right size. That chain becomes
a provisional track that must be confirmed in 5 of 6 frames. This took the faint-beacon scenario
from never acquired to 94.0 to 97.8 percent lock over 10 seeds. Two guards keep a faint track on
the beacon. The sub-pixel refit could slide onto a neighbouring noise clump (the centre jumped
several px, the width ballooned to 7.5 px), so the raw detection is kept when the refit moves more
than 3 px or the width exceeds 2.5 times the track's recent median width, and a much wider
candidate is not associated. On seed 7 this took the run from 86 px error and 78.6 percent lock to
2.8 px and 94.8 percent. The chain linking is vectorised (same greedy
order, identical results), so the 99th-percentile frame time on the faint beacon fell from 149 to
160 ms to 26 to 33 ms.

## B12. Step 11: the interface (desktop and web are one program)

- **Desktop application** (the mandatory deliverable): scenario picker; Start, Pause, Step, Stop;
  speed; Open video; Save scenario; Screenshot; Results; Manual; About. Left: every setting,
  grouped by PS row, with the row number in each tooltip. Top: six live tiles (state, acquisition,
  tracking error, centroid error, lock retention with tracked rate, processing), green when the
  specification is met. Target section: a target picker with a Designated tick box (how the tracker finds it is automatic) and
  the scenario check notes. Centre: the whole scene (before a run, a preview at t = 0
  with every target named; click one to designate it) and the camera view with overlays. Below: four
  plots (errors, gimbal rates with the limit, processing time with the 20 FPS budget, tracker
  state). Right: telemetry. At the end: a summary dialog and the report. During a run the
  Disturbances section stays live: noise, weather, jitter or platform sway changed mid-run reach
  the next frame, the tiles restart from the change and the plots and report mark it; the other
  sections are locked for the run. The change is saved in the run's scenario so it replays exactly.
- **Web application**: the same program on a server, same layout and controls, so reviewers need
  nothing installed. Both are generated from one definition in the code, so they cannot drift
  apart.

## B13. Step 12: packaging for every computer

The desktop app is packaged with PyInstaller into a self-contained folder for Windows x64, Linux
x64, macOS Intel and macOS Apple silicon. Each build runs the tests, and then runs the packaged
program on scenarios, a video and the window before it is published. Nothing needs installing,
and it works offline.

Where each one is built, and why: Windows and Linux on GitHub's machines (the build workflow,
started by hand or by a version tag; about 100 Actions minutes, roughly $0.75 at GitHub's rates).
The two macOS builds on the team's Apple silicon Mac with `bash tools/build_macos.sh`: the Apple
silicon one natively, the Intel one through Rosetta with an x86_64 Python that `uv` installs once
and keeps in `.venv-intel/`. The reason is cost: GitHub charges ten Linux minutes for one macOS
minute, and building all four on GitHub on every push used up the free 2,000 minutes in three
days (about $4.70 per full build, $3.92 of it macOS). Our own server cannot build any of them: it
is an ARM Linux machine and the Linux download is for x64 PCs. A teammate's fork of the
repository has its own free minutes, so a build can also be run there and published with
`REPO_SLUG=<fork> bash webapp/publish_builds.sh`.

## B14. Step 13: how we know it works

- 116 automated tests, including one per group of PS rows that pins every default to the PS.
- A PS audit (`tools/ps_audit.py`) that measures every PS item by running the code: rows 1 to 25,
  the eight "shall" functions, the five deliverables, Benchmark 1, and Benchmark 2 with a rendered
  noisy video and its truth CSV. It writes `docs/PS_AUDIT.md` and fails the build if any check
  fails. Now 39 of 39 pass.
- A regression batch: 16 scenarios x 3 seeds, compared run by run with the previous batch before
  any change is accepted.
- Package checks on each platform, and hand checks on both macOS builds.
- Browser checks of the web app, and screenshot reviews of the desktop window at two screen sizes.

## B15. Step 14: where it lives

- Code: private GitHub repository `tanmayhutt/SIH26169`.
- Site: `https://sih26169.blankpoint.club/` (login required): the web app, the progress page at
  `/about/` with every document, and `/downloads/` with the four builds, both PDFs and the demo
  video.

---

# Part C. The journey: what we did, in order, and what we learned

## C1. Timeline

- **2026-09-18. Understanding.** Read the PS; wrote the architecture and a plain-English plan.
  First mistake, corrected the same day: we had assumed the tracker only sees the 640 x 480 camera
  view. Re-reading the PS word for word ("observe the surrounding environment", "simulated video
  stream", Benchmark 2 videos "covering a complete screen") showed that the tracker observes the
  whole scene and controls the window. We also fixed the centre-to-corner slew (0.95 s, not 1.4 s)
  and settled that Benchmark 2 has a single reading.
- **2026-09-18. A question we answered for the team.** "If they give us videos, why build our own
  fake scenes?" Because the simulator is itself a deliverable: three of the eight "shall" items,
  rows 1 to 15, Benchmark 1 and all the ground truth depend on it. The videos test only the tracker.
- **2026-09-19. Building.** Engine, simulator, tracker, controller, desktop app, command line, PDF
  report, 12 scenarios, tests, first macOS build, user manual and technical report. Many tuning
  rounds (listed in C3). Progress site first on GitHub Pages, then moved to our own server with a
  login.
- **2026-09-19. Video calibration.** A phone video showed wrong size and frame rate; the video
  reader now applies rotation tags and checks the frame rate against timestamps.
- **2026-09-20. Hardening.** Four-platform builds with a check on each platform; the web app
  deployed; faint-beacon track-before-detect; identity through decoy crossings; the user-defined
  waypoint path (row 12's optional "user-defined"); output naming; demo video and script; evaluator
  scenario template.
- **2026-09-21 and 22. Honesty about limits.** Re-measured the platform maximum at the allowed
  10 deg/s: no improvement, so the limit is the random shake, not the motor. Fixed the lead to scale
  with the camera rate (found with a 60 fps phone video, proven on simulated 60 Hz runs). Added the
  tracked rate. Reviewed and fixed the interface.
- **2026-09-23. One program.** Desktop and web built from one interface definition; handover and
  this document written.
- **2026-09-23. The designated target.** The owner found that row 8 and "a designated moving
  target" were not fully met: the tracker picked the beacon by appearance only. Measured: identical
  decoys starting apart, appearance only (20 s, seeds 0 to 4), the designated beacon was acquired in
  1 of 5 runs and never acquired in 3. With the start cue: 5 of 5 pass (acquisition 0.60 to 0.73 s,
  5.7 to 6.6 px, 100% lock). Added designation modes, names, click to designate, user-defined
  shapes with separate width and height, and a typed start. The owner's web-app test also failed:
  the page took salt and pepper 13 (meant as 13%) as a fraction, every pixel went black and the
  beacon was never acquired. With 0.13 the same settings give acquisition 1.40 s, 99.4% lock and
  11.9 px (above 10 px because jitter, turbulence and noise all exceed the PS). Now shown in percent,
  every input is clamped, and the scenario check flags such values. A tracker defect was fixed too:
  while searching, candidates were re-measured on a stale picture (or none, a crash with 50% salt
  and pepper); now on the current frame. The regression batch is unchanged (42 of 42 identical).
- **2026-09-23. An independent review.** A teammate's review found real defects, fixed and
  measured on the whole pack. FPS was the mean of per-frame rates, which overstates the rate (faint
  beacon seed 2, 30 s: 92.0 said, 67.8 true); it is now frames over processing time. The lead
  pointed a fast circling beacon off its path; it is now capped by the path's turn (4 deg/s circle:
  34.3 px to 8.4 px). A coasting estimate could run far off the screen (faint beacon seed 2: 158 px
  error, 75.1% lock); it now falls back to a whole-scene search (5.9 px, 96.2%). The faint path
  was vectorised. Benchmark 2 accepts a ground-truth CSV. Read and shot noise now use independent
  random planes. One reported failure (a 5 px beacon in rain with 10% salt and pepper, never
  acquired) could not be reproduced with our settings: 0.77 to 1.37 s, 6.0 to 6.5 px, 100% lock.
  Regression batch against the committed merge: 38 same, 10 better, 0 worse, 3 new (fast_circular).
- **2026-09-23 evening. The PS audit.** A new tool measures every PS item by running the code. Its
  Shall 6 check found that a still beacon was never settled: the derivative gain drove a limit
  cycle of about +/-10 px (mean 6.4 px, peak 15.6 px). With kd 0 it is held within 4 px (mean
  1.6 px), and tracking errors across the pack dropped by about two thirds. Its row 25 check found
  the figure-8 sway peaking at 28.3 px/frame when set to 20; it is now scaled so its peak equals
  the setting. The faint beacon seed 7 walked off onto noise (86 px, 78.6% lock); the refit and
  width guards and keeping the CNN off faint tracks give 2.8 px, 94.8%. Regression: 0 worse, 5
  better (platform maximum lock). The audit passes 39 of 39. The deck was renamed ARGUS.
- **2026-09-23 night. The target panel, redone.** The owner rejected the six-control flow added
  that morning: a Designated dropdown, a Designation mode, a Cue box and an Edit target dropdown
  in the Run section. Replaced in both apps by one Target picker and one Designated tick box; how
  the tracker identifies the target is automatic (its look, plus its start position when another
  target looks the same), and a scenario file can still force a mode. On a video you click the
  beacon on the first frame.
- **2026-09-23 night. Builds and cost.** GitHub stopped starting build jobs: the free Actions
  minutes were gone, because macOS minutes cost ten times Linux ones and the workflow built all
  four apps on every push. The workflow now builds Windows and Linux only, by hand or on a tag;
  both macOS apps are built on the team's Mac by `tools/build_macos.sh` (Intel through Rosetta)
  and were uploaded that night. The Windows and Linux downloads wait for an Actions budget, the
  monthly reset, or a build on a teammate's fork.
- **2026-09-24. Camera effects.** Exposure gain and frame loss added as disturbances beyond the PS table (the PS
  lists them "etc."), off by default. Measured on clear line, 15 s: 10% frame loss gives 88.0% lock (every lost frame breaks lock) but 100% on the frames received, tracking error 2.59 px (2.35 without) and re-acquisition within 0.10 s; 25% loss: 71.0% lock, 3.04 px, 0.17 s. Exposure x4 clips the beacon at white and raises the centroiding error from 0.006 to 0.093 px; x0.5 changes nothing measurable.
- **2026-09-24. Measured against a simple baseline.** `tools/compare_trackers.py` runs ARGUS and a
  brightest-spot tracker with proportional control over every scenario: ARGUS meets every PS limit in 33 of 48 runs, the baseline in 0 of 48; the baseline's tracking error is 27 to 40 px on clear skies against 2 to 6 px, it holds 1.6% lock among identical decoys and never acquires the faint beacon; it acquires faster on some clear skies (0.37 s against 1.03 s on the circle) because it has no confirmation step.
- **2026-09-24. Handoff to fine pointing.** The PS places coarse alignment "before fine pointing
  mechanism can take over". A run now says when that could happen: locked, estimate within 10 px
  (row 17) of the centre, held 1 s. Measured: clear line 2.20 s (lock at 1.07 s), full PS noise 1.70 s, fog 2.43 s, all held 100%; faint beacon 3.37 s, held 37.8%; platform sway plus shake, the PS maximum and full stress never reach it (the estimate does not stay within 10 px). Tracking is unchanged.
- **2026-09-24. Verifiable figures.** `fsoc-tracker verify <run folder>` rebuilds every metric from a run's
  frames.csv and checks its summary.json (the 51-run regression batch: 51 of 51 reproduce, 32 values each);
  a summary edited by hand is caught. It lets an evaluator confirm our numbers from the log alone.
- **2026-09-24. A full robustness review.** Every PS scenario over ten seeds (170 runs, no crash),
  19 evaluator-style videos (sizes 5 to 20 px, 1080p and 4K, 25 and 60 fps, noise, fog, low light,
  shake, a still beacon, two beacons, a beacon that leaves) and broken files, plus two code
  reviews. Fixed: the start cue pointed at a circular path's centre, so an identical decoy won
  (18% lock, now 100%); a click on a video's first frame (desktop) was mapped with the
  simulator's geometry; a truth file sampled every fifth frame scored 80% of frames as lost lock
  (now 97%); circle, ring, diamond and cross beacons were drawn up to 0.8 px off their truth, so
  their centroiding error was overstated; NaN or infinite values and text in a schedule crashed a
  run (now noted and handled); the packaged app read `--duration 2.5` as a file; `record_check`
  never flagged a commit; the web app answered bad input with 500s and let anyone watching stop
  or change someone else's run.
- **2026-09-23 night. Disturbances during a run.** The PS asks the software to introduce
  disturbances into the camera feed; they were fixed for a whole run. Now the Disturbances
  section stays live while a run is going (the other sections are locked), a change reaches the
  next frame, the tiles restart from it, the plots and the report mark it, and the report gives
  each setting its own figures. A scenario can script the same changes with a `schedule`, and a
  live change is saved into the run's scenario so the run replays exactly. Switching platform
  sway on or off never makes the picture jump. Runs without changes are unchanged.

## C2. Principles we adopted along the way

1. **The PDF is the only source of truth.** Every default is the PS's; a test pins them.
2. **Never tune to our own test videos.** A video one of us recorded (for example a hand-waved dot on
   a phone) is harder than the PS describes. It may reveal a general bug, which we fix and prove on
   the whole scenario pack, but we never bend the system to it.
3. **No competitor code.** Other teams' repositories for SIH26169 are competitors; we reason from
   the PDF alone.
4. **Measured numbers only.** Physical limits are reported with their measurements, never hidden.
5. **Classical first, AI as a helper.**
6. **The desktop executable is the product**; the web app is a convenience.

## C3. What we tried and threw away, and why

| Idea | Result | Decision |
|---|---|---|
| Tracker sees only the camera window by default | Acquisition up to 12 s | Kept only as "hard mode" |
| Keep the camera window fully on the screen | Beacons near the edge became unreachable | Window may hang over the edge |
| Tighter lock radius (20 px) | No lower error, lock worse under shake | Keep 30 px |
| Phase correlation to measure shake | Unreliable on noisy frames | Shake measured from the filter's own surprises |
| Median filter always on | Erased faint beacons on dark skies | Only for real salt-and-pepper noise |
| Sub-pixel fit on every candidate | Too slow | Only on the chosen and nearby ones |
| Half-maximum area as the identity size | Worse under noise | Fitted width plus area |
| Heavier appearance weight in identity | Rejected the true beacon in haze | Kept moderate |
| Control-side tweaks for the platform maximum (filtered derivative, adaptive noise, smoothed derivative) | Helped one scenario, hurt another | Reverted |
| Derivative gain kd 0.3 | A +/-10 px limit cycle: a still beacon never settled (mean 6.4 px, peak 15.6 px) | kd 0; a still beacon is held within 4 px |
| Motor at 10 deg/s for the platform maximum | Saturation 2 percent, lock unchanged | Limit documented as the shake |
| Neural network as the main detector | Less accurate and slower than classical | Kept as a gap filler |
| Six target controls in the Run section (Designated, Designation mode, Cue, Edit target, and more) | Confusing: two dropdowns of names, a mode nobody should have to pick, an empty cue box | One target picker and one Designated tick box; the mode is automatic (start position when look-alikes exist) |
| Building all four desktop apps on GitHub on every push | Used the free Actions minutes in three days (macOS costs 10x) | Windows and Linux on GitHub, by hand; both Macs built locally by `tools/build_macos.sh` |
| A "Cannot be met" label on the 70 percent turn-rate warning | It was met; the label was wrong | A fourth note kind, "Near the limit" |

---

# Part D. Results and honest limits

## D1. Measured results (15-second runs, three seeds each, desktop CPU)

| Scenario | Acquisition | Tracking error (mean) | Lock | Verdict |
|---|---|---|---|---|
| Clear line, circle, figure of 8 | 0.60 to 1.33 s | 2.1 to 3.7 px | 100% | pass |
| Clear random walk | 0.67 to 1.03 s | 5.1 to 6.3 px | 100% | pass |
| Heavy noise (salt and pepper 10%, Gaussian 20, Poisson) | 0.67 to 1.00 s | 2.4 to 3.7 px | 100% | pass |
| Fog and low light | 0.63 to 1.57 s | 2.5 to 3.7 px | 100% | pass |
| Faint beacon (3 to 6 sigma per frame), 10 seeds | 0.80 to 2.00 s | 2.4 to 3.5 px | 94.0 to 97.8% | pass; seeds 7 and 8 at 94.8 and 94.0%, just above the 5% target-loss limit |
| Multi-target stress (decoys, haze, noise, sway, shake) | 0.30 to 1.03 s | 10.3 to 11.3 px | 98.2 to 100% | identity held; error above 10 px because of the shake |
| Sway 12 px/frame plus shake 20 px/frame | about 0.8 s | 19.0 to 19.4 px raw | 99.3 to 100% | shake limit |
| Platform at the PS maximum (20 + 20 px/frame), 5 and 10 deg/s | 0.73 to 0.97 s | 21.7 to 23.5 px | 93.4 to 97.2% | documented physical limit |
| Fast circle, 450 px at 4 deg/s (80% of the camera turn rate) | 0.67 to 0.70 s | 4.6 to 5.3 px | 100% | pass |
| Hard mode (window only) | 2.83 to 11.97 s | 2.6 to 3.7 px | 100% | acquisition beyond 2 s by design (search) |
| Identical decoys, designation start | 0.60 to 0.73 s | 3.3 to 3.5 px | 100% | pass |
| Beacon shapes, 8 x 18 px rectangle among other shapes | 0.73 to 0.83 s | 2.6 to 3.1 px | 100% | pass |

- Centroiding error: 0.006 to 0.007 px in clear air, 0.19 px under heavy noise, 0.08 to 0.15 px in
  fog and low light.
- Processing (frames over processing time): 69 to 216 FPS on a laptop over the whole pack (190 to
  216 clear, 97 to 105 under heavy noise), 95 to 96 FPS on the faint
  beacon over 30 s, 41 to 176 FPS on the slower build machines; the
  requirement is 20.
- Identical tracking numbers on Windows, Linux and both Macs.

## D2. Limits, and how to explain them

- **Shake at the PS maximum.** The picture jumps randomly up to 20 px every frame. A random jump
  cannot be known before the frame arrives, and the camera acts after it sees the frame, so the
  raw error on each frame is about the size of the jump. We report the error with the shake removed
  beside it (the part the camera can physically follow). A faster motor (10 deg/s) was tested and
  does not help. Fixing it would need a larger sensor for electronic stabilisation, outside the PS.
  Lock at this setting is 93.4 to 97.2%, error 21.7 to 23.5 px.
- **Everything at once (full stress)** stacks disturbances the PS lists separately; tracking holds
  at 98.2 to 100% lock over 15 s, error sits at 10.3 to 11.3 px.
- **Faint beacon near the loss limit.** Over 10 seeds lock is 94.0 to 97.8%; seeds 7 and 8 hold
  94.8 and 94.0%, just above the 5% target-loss limit.
- **Look-alikes that start together.** Identical targets that start at the same point as the
  designated beacon cannot be told apart at the start; even with the start cue these runs failed
  (lock 8 to 25%). Look-alikes that start apart pass with the start cue.
- **A faint beacon that never moves** is not covered by track-before-detect (it finds dim things by
  their motion); the PS never asks for one.
- **The builds are not code-signed**, so Windows and macOS warn on first launch; two clicks let it
  run.

---

# Part E. Presenting it

## E0. The presentation

Our SIH idea-submission deck is `docs/submission/ARGUS_SIH2026_26169.pdf`. It follows the SIH
template: title (PS ID, title, theme, category, team ID, team name), proposed solution, technical
approach (methodology and architecture), working prototype, feasibility and viability, impact and
benefits, research and references. Its numbers are the measured ones in Part D.

## E1. The demonstration (Functional Verification, 20%)

Follow `docs/DEMO_SCRIPT.md`: clear line (acquisition, error, report), each motion path, noise,
fog and shake switched on live in one running scenario,
disturbances (noise, fog, faint beacon, shake), decoys, hard mode, a video for Benchmark 2, and the
web app. Keep the report PDF ready to open.

## E2. On the day of the benchmarks

- **Benchmark 1:** copy `configs/scenarios/TEMPLATE_evaluator.yaml`, fill in their values (every
  field is labelled with its PS row), save it in `configs/scenarios/`, pick it, Start. Picking it keeps its seed and paths exactly as
  written. The report and CSV appear automatically.
- **Benchmark 2:** open each video directly. Check the calibration line (size, frame rate, frames).
  Hand over the CSV (`det_x`, `det_y` per frame) and the report. If they give positions, load
  them with Truth CSV so errors and true lock are computed.

## E3. Likely questions and short answers

- **Why not just follow the brightest spot?** We measured it (`docs/BASELINE_COMPARISON.md`): a brightest-spot
  tracker with proportional control meets the PS limits in 0 of 48 runs against our 33 of 48. It lags every
  moving beacon (27 to 40 px), follows the wrong one among identical decoys (1.6% lock) and cannot see the
  faint beacon. It is faster to lock on a clear sky only because it skips our 3-of-4-frame confirmation, the
  step that keeps a noise speck or a decoy from being taken for the beacon.
- **Where is the AI?** A neural detector trained on our simulator fills gaps; the core is computer
  vision and estimation, deliberately, so speed and reliability never depend on a model. In the
  standard scenarios it supplies 0% of the measurements.
- **How do you know the tracker isn't cheating with the ground truth?** We deleted the truth before
  the tracker and got identical results.
- **Why is error above 10 px under maximum shake?** The shake is random and arrives before the
  camera can react; with the shake removed the error is reported separately; a faster motor was
  tested and does not help.
- **Why a simulator if you get videos?** The simulator is a deliverable and Benchmark 1; the videos
  test only the tracker.
- **Why does the tracker see the whole screen?** The PS says the system observes the environment and
  tracks in a simulated video stream; hard mode shows the window-only case too.
- **Does it track multiple targets?** It detects all of them and follows the designated one, which
  is what the PS asks ("a designated moving target", row 8). The target is designated by
  appearance, by a start cue or by a click. Tracking all at once is not required: the PS metrics
  are for one target and one camera.
- **Is it fast enough?** 69 to 216 FPS on a laptop against the required 20, measured as frames
  over processing time (not the mean of per-frame rates, which overstates it).
- **How accurate is the centre?** 0.006 to 0.007 px in clear air, 0.19 px under heavy noise.
- **How do you know every PS item is met?** `tools/ps_audit.py` measures each one by running the
  code (rows 1 to 25, the eight "shall" functions, the deliverables, both benchmarks) and writes
  `docs/PS_AUDIT.md`; 39 of 39 pass, and the build runs it.
- **When is coarse alignment done, so fine pointing can take over?** When the tracker is locked and
  its estimate has stayed within 10 px (the row 17 limit) of the window centre for 1 s; the app says
  "handoff ready". Clear sky: about a second after lock, held 100%. Under the PS maximum shake it is
  never reached, which is the same physical limit as the raw tracking error there.
- **Can the disturbances change while it tracks?** Yes: during a run the Disturbances section
  stays live, so noise, fog, jitter or platform sway can be switched on or off without a restart;
  the next frame carries it, the tiles restart from the change and the report scores each setting
  separately. The change is saved in the run's scenario, so the run replays exactly, and a
  scenario file can script such changes with `schedule`.
- **Can it be used with real hardware?** Yes: the frame source and the gimbal are separate
  interfaces, so a real camera and pan-tilt unit can replace the simulated ones.

## E4. Glossary

| Term | Meaning |
|---|---|
| FSOC | Free Space Optical Communication: data over a light beam through air or space |
| PAT | Pointing, Acquisition and Tracking |
| Coarse / fine alignment | rough camera-based pointing / precise laser pointing |
| Beacon | the bright light on the remote terminal that the camera looks for |
| FOV | field of view: how much the camera sees, as an angle |
| IFOV | the angle one pixel covers (here 22.5 arcsec) |
| Pan / tilt | turning left-right / up-down |
| PTZ | pan-tilt-zoom camera |
| Gimbal | the motorised mount that turns the camera |
| FPS | frames per second |
| Centroid | the measured centre of the beacon spot |
| Centroiding error | measured centre to true centre |
| Tracking error | true beacon to camera centre |
| Lock | tracker in TRACK with the beacon within 30 px of the centre |
| Lock retention / target loss | share of frames locked / 100 minus that |
| Tracked rate | share of frames in TRACK, regardless of centring |
| Acquisition / re-acquisition | first finding the beacon / finding it again after losing it |
| RMSE | root mean square error |
| Salt and pepper, Gaussian, Poisson | random black/white pixels; smooth random noise; brightness-dependent noise |
| Jitter | camera shake: the whole picture jumps each frame |
| Platform motion | the carrier itself moving, dragging the picture |
| Matched filter | a blur at the beacon's size that makes it stand out |
| IMM filter | an estimator running several motion models at once |
| Track-before-detect | linking weak detections across frames before deciding one is real |
| Feed-forward / PID | steering by prediction / correcting by the remaining error |
| ONNX | a standard file format for trained neural networks |
| Designation cue | a point near the designated target (its start, or a click on a video's first frame) that the search starts from; chosen automatically unless a scenario file forces a mode |
| Scenario check | the notes on corrected, beyond-the-PS, near-the-limit and impossible settings shown before and after a run |
| Ground-truth CSV | for a video: the evaluators' beacon position per frame, so errors and true lock can be computed |
| Turn-limited lead | the feed-forward lead shortened so the beacon's path turns at most 0.1 rad over it |
| Scenario | a settings file describing one test |
| Seed | the number that fixes the randomness, so a run can be repeated exactly |
