# Slide and spoken answer: why ARGUS watches the whole scene

A slide for the technical evaluation, and the answer to the question it anticipates ("shouldn't the
tracker see only the camera window?"). The reading is decided in `docs/HANDOVER.md` section 6.1 and
`COMPLIANCE.md` ("Things the PS does not specify"); this page only makes it presentable.

## Slide

**Title:** What the tracker sees, and why

**Left, the problem statement's words**
- Coarse alignment must first "observe the surrounding environment"
- It tracks the beacon "in a simulated video stream"
- Benchmark 2 videos cover "a complete screen" and replace the camera ("bypass its PTZ camera")

**Right, what follows, measured (10-seed envelope, 2026-09-24)**
- The tracker observes the whole 2000 x 2000 screen; the 640 x 480 window is what it steers
- A window-only search at 5 deg/s sweeps about 13 window areas: acquisition 3 to 12 s (hard mode)
- Watching the scene: acquisition 0.6 to 1.7 s over ten seeds of every full-view scenario (a faint beacon up to 2.0 s), inside the 2 s limit
- Both are built: hard mode (window only) is one setting, and is demonstrated

**Footer:** One screen pixel is one camera pixel (22.5 arcsec), the only anchor the problem statement
gives (4 deg over 640 px).

## Spoken answer (about 30 seconds)

"The problem statement asks the coarse stage to observe the surrounding environment, and to track the
beacon in a simulated video stream; in Benchmark 2 the video covers the complete screen and replaces the
camera. So the tracker observes the scene and steers the window that stands for where the terminal
points. We also built the stricter reading: with hard mode on, the tracker sees only the window and
has to search. At five degrees a second that search takes three to twelve seconds, which cannot meet
the two-second acquisition limit from a far corner; watching the scene, acquisition was 0.6 to 1.7 seconds
over ten seeds of every scenario, and at most two seconds for a faint beacon. Both are in the application, and we can switch between them now."

*Then show:* clear line with hard mode off, then on.
