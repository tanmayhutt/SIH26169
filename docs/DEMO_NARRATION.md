# Demo video narration (about 4 minutes)

The optional 3 to 5 minute video of the problem statement, narrated. Record the desktop application
at 1600 x 1000 while reading this; each section says what to show and what to say. Every number is
measured (the sources are named at the end); if a rerun gives a different number, say the one on
screen.

## 0:00 to 0:25. The problem, in one breath

*Show: the application at rest, the scene view and the camera view.*

"Two terminals want to talk over a laser beam while both are moving. Before any data flows, each
must find the other and keep it in view: coarse alignment. ARGUS does that in software. It draws a
two-thousand-pixel scene with a moving beacon, adds the disturbances the problem statement lists,
and steers a six-forty by four-eighty camera, limited to five degrees a second, to keep the beacon
centred."

## 0:25 to 1:00. Acquire and track

*Show: scenario clear line, Start. Point at the tiles as they turn green.*

"The tracker watches the whole scene, so it finds the beacon in a few frames, confirms it in three of
four, and turns the camera: lock in about a second, against a two-second limit. Tracking error settles
near three pixels against a limit of ten, and the beacon's centre is measured to about a hundredth of
a pixel. After a second of steady lock the camera view says handoff ready: the point where a fine
pointing stage could take over."

## 1:00 to 1:50. Disturbances, live

*Show: clear circular, running. Change the Disturbances section one step at a time; let each settle.*

"Now the conditions change while it runs. Ten percent salt and pepper, Gaussian and Poisson noise:
still under ten pixels. Fog: contrast and brightness drop. Camera jitter and platform sway: the
picture moves, it never jumps, and the error rises with the shake. Each change is marked on the plots,
the tiles restart from it, and the report gives every setting its own figures. The change is saved
with the run, so the same run can be replayed exactly."

## 1:50 to 2:25. Faint beacons and look-alikes

*Show: lowlight faint, then decoys identical.*

"A faint beacon, three to six times the noise in any one frame, cannot be found in a single picture.
The tracker links weak detections across frames and keeps only a chain that moves consistently. With
look-alike beacons in the scene, it keeps the designated one by its start position and its look, and
rechecks every half second."

## 2:25 to 3:05. Benchmark 2: a video file

*Show: Open video, the first frame, click the beacon, Start. Then open the frames CSV.*

"For the second benchmark the simulator is bypassed: the evaluators' video becomes the scene. Its
size, frame rate and rotation are read from the file. Our measured centre is logged for every frame,
here in the CSV, for comparison with their reference values; with their positions loaded as a truth
file, the report computes the error and the true lock against them."

## 3:05 to 3:40. Numbers you can check

*Show: the end-of-run summary, the report, then a terminal running `fsoc-tracker verify`.*

"Every run writes a per-frame log and a PDF report, automatically. The figures are not taken on
trust: one command rebuilds every metric from the log alone and checks the summary. And we measured
our design against a simple brightest-spot tracker on every scenario: it met the specification in
none of forty-eight runs; ARGUS met it in thirty-three. The fifteen it does not meet are the maximum
shake, where a random jump every frame cannot be followed by any gimbal, the window-only hard mode,
and every disturbance stacked at once, and each is reported as measured."

## 3:40 to 4:00. Close

*Show: the downloads page or the web app.*

"ARGUS runs offline as a desktop application on Windows, Linux and both kinds of Mac, and the same
program runs in a browser. Thank you."

## Sources of the numbers

- Acquisition about 1 s, tracking error near 3 px, centroid about 0.01 px, handoff about a second after
  lock: 10-seed envelope and 15 s runs of clear_line and clear_circular (docs/HANDOVER.md history,
  2026-09-24).
- Noise under 10 px: noisy_line, 2.4 to 3.7 px.
- Baseline 0 of 48, ARGUS 33 of 48: `docs/BASELINE_COMPARISON.md`.
- The shake, hard-mode and stacked limits: `docs/KNOWLEDGE_TRANSFER.md` Part D.
