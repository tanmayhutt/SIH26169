# Live demonstration script (10 to 15 minutes)

For the Functional Verification stage of SIH26169. The evaluators want to see every
mandatory function work, the GUI, and operational success. This script runs the desktop
application; the same flow works in the web app if the machine cannot run the executable.

Before the session: extract the archive for the machine, start `ARGUS` once so the
first-start delay is behind you, and have one `.mp4` ready for Benchmark 2. Keep the user
manual PDF open in another window.

## 0. One sentence (30 s)

"This is a software test bench for coarse alignment of an FSOC terminal: a simulated scene
with a moving laser beacon, disturbances, and a tracker that finds the beacon, measures its
centre to a fraction of a pixel, predicts its motion and steers a rate-limited virtual
pan-tilt camera to keep it centred. Every run writes a per-frame log and a PDF report."

## 1. The window (1 min)

Point at, left to right: the parameter panel (one field per row of the PS table, with the
row number in each tooltip), the six live tiles (each shows its specification), the scene
view (whole 2000 x 2000 screen, cyan camera window), the camera view (what the terminal
sees, 640 x 480), the two plots, the telemetry column.

## 2. Clear acquisition and tracking (2 min)

Scenario: clear line. Press Start.

- Watch SEARCH turn to TRACK in about a second. Say: "acquisition under one second and a
  half, specification two seconds".
- Point at the tracking error tile settling around 2 to 4 px (measured 2.1 to 3.7 px on the clear
  paths), specification 10.
- Point at the camera view: the beacon sits at the centre; the gimbal command plot shows
  the pan and tilt rates inside the 5 deg/s limit.
- Press Stop, then Report. Show the PDF: header with the configuration, the metric table,
  the plots. Say: "this is the automatic performance log the PS asks for; the CSV next to
  it has every frame, including the centroiding error".

## 3. Every motion, one click each (1 min)

Change Motion to circular, then figure8, then random. Start each for ten seconds. Mention
that spiral, sinusoidal and a user-defined waypoint path are there too.

Optional: scenario fast circular. "A 450 px circle at 4 deg/s, 80 percent of the camera's
turn rate. The scenario check says Near the limit." The error stays at 4.6 to 5.3 px with
100 percent lock.

## 4. Disturbances, live, in one run (3 min)

Scenario: clear circular, Duration 60, speed 1x. Press Start and let it lock. Then, without
stopping, change the Disturbances section one step at a time and let each settle for about
ten seconds. Each change shows in the status line, as a dotted line on the plots, and the
error and lock tiles restart from it ("since ... s").

1. Salt and pepper 0.10, Gaussian sigma 20, Poisson on. "All three PS noise kinds (rows 21
   and 22), switched on while it tracks." The error stays well under 10 px.
2. Atmosphere: fog. "Contrast and brightness reduced, blur and turbulence (row 24)."
3. Camera jitter 10, platform linear 12 px/frame. "Rows 23 and 25. The picture starts to sway
   smoothly, it does not jump." The raw error rises with the shake; the report gives the
   vibration-removed error beside it.
4. Everything back to zero and clear. The picture settles back and the error returns.

Stop, open the report: page 2 has one row per setting with its own error, lock and FPS. Say:
"every change is also saved in this run's scenario file, so the same run can be replayed
exactly from the command line."

Then two scenarios on their own:
- lowlight faint. "The beacon is at three to six sigma per frame. A single frame cannot find
  it; the tracker links weak detections across frames and only promotes a chain with
  consistent motion." Show the acquisition in two seconds or less (0.80 to 2.00 s over ten
  seeds).
- platform max. "Both at the PS maximum. The vibration is measured from the tracker's own
  innovation and treated as measurement noise, so the filter smooths it instead of chasing
  it; a random jump every frame cannot be followed by any gimbal, which is why the report
  prints the vibration-removed error." Point it out in the report.

## 5. Multiple targets and identity (2 min)

- Scenario: full stress. Point at the names on the scene view: the designated one is marked
  "(designated)". The tracker keeps it by its appearance signature and audits the designation
  every half second. The telemetry's first line says "following <name>".
- Scenario: decoys identical. "Three look-alikes with the same shape, size and brightness. By
  appearance alone no tracker can tell them apart; the scenario check says so. Designation
  start tells it where the Remote terminal starts, as an operator or GPS cue would." Start: the
  designated one is held as the paths cross.
- Click to designate: before Start, click another target on the preview. It becomes the
  designated one, and the report's "Followed" line names it.

## 6. Hard mode (1 min)

Set Hard mode to yes on clear line. "Now the tracker sees only the camera window, so it
must sweep the screen. The square-spiral search finds the beacon in 2.8 to 12 seconds
at the 5 deg/s limit." This is the honest cost of the rate limit; the PS allows up
to 10 deg/s, and raising it shortens the sweep.

## 7. Benchmark 2, video input (2 min)

Open the `.mp4`. Point at the calibration line: size as displayed, frame rate read from
the file, frame count. Press Start. "The simulator is bypassed; these frames are the scene.
The report carries the detection centroids per frame for comparison with the evaluators'
predefined values, plus acquisition, re-acquisition, lock retention and FPS." If the
evaluators give true positions, load them with Truth CSV before Start: the error tiles and the
report then show tracking and centroiding error against their values.

## 8. Close (30 s)

Show the Downloads page or the web app on the phone: "The same engine runs in a browser
for review without installation, and native builds exist for Windows, Linux, Intel Mac and
Apple silicon." Then the technical report's performance table.

## If something goes wrong

- The window does not open: run from a terminal to read the message; on macOS use Open
  Anyway in Privacy and Security; on Windows choose Run anyway.
- A scenario looks stuck in SEARCH in hard mode: it is sweeping; the spiral takes up to
  twelve seconds at 5 deg/s.
- The video file is refused: it must be a file OpenCV can decode (mp4, avi, mov, mkv);
  re-encode with any converter to H.264 mp4.
