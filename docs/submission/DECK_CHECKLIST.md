# Presentation checklist

`ARGUS_SIH2026_26169.pdf` in this folder is the current submission deck. Corrections were made
directly in the PDF, so the source presentation file may not have them. Before exporting a new
version, make sure the deck still says all of this. Every number comes from `docs/KNOWLEDGE_TRANSFER.md`
Part D; never round a limit away.

| Slide | Must say |
|---|---|
| All | Project name ARGUS on every slide; slide 1 gives the full form: Acquire, Recognise, Guide, Update, Stabilise |
| 1 | Team ID (still to fill in) |
| 2 | Identity box: named targets; appearance, start cue or click picks the one to follow, re-checked every 0.5 s |
| 2 | OBSERVE: the tracker watches the whole 2000 x 2000 px (12.5 degree) scene because the PS asks it to "observe the environment"; hard mode limits it to the camera window |
| 4 | Engine: one config field per PS row (all 25 rows), 16 scenario files, 45 automated tests |
| 5 | Benchmark 2 screenshot taken mid-run (TRACK locked), not "video ready"; caption says our measured centre is logged every frame (`det_x`, `det_y`) for comparison with the evaluators' values |
| 5 | Stress caption: 57 FPS is with live drawing; the 14.3 px error is the injected shake |
| 5 | Repo link marked "private; access on request"; demo video link filled in (currently the site downloads page, login needed) |
| 6 | Faint beacon over 10 seeds: acquisition 0.8 to 2.0 s; two seeds hold 94 to 95 % lock (slide 8 known limits) |
| 6 | Measured rows (15 s, 3 seeds): clear 0.6-1.3 s, 2.1-3.7 px; random walk 5.1-6.3 px, Pass; heavy noise 2.4-3.7 px; fog and low light 2.5-3.7 px; faint (10 seeds) 0.8-2.0 s, 2.4-3.5 px, 94-97.8 %; decoys + haze + noise + sway 10.3-11.3 px, 98-100 %; platform max about 22-24 px, 93-97 % (physical limit); hard mode 3-12 s, 2.6-3.7 px |
| 5 | Tiles: 0.6-1.3 s, 2.1-3.7 px, 100 %, 0.006 px (0.1-0.2 px heavy noise), 69-216 FPS (frames over processing time, whole pack); stress screenshot caption 0.60 s, 100 %, 75 FPS, 11.2 px |
| 6 | A hard mode row: 3 to 12 s, 7 to 12 px, 100 %, "By design" |
| 6 | Decoys risk: designate by appearance, a start cue or a click; identical look-alikes 100 % lock with the start cue |
| 6 | Verification boxes: 45 automated tests; regression batch 16 scenarios x 3 seeds |
| 8 | Reference [18]: the technical report has 12 pages |
| 8 | Coverage (25 of 25 rows, 8 of 8 "shall", 5 of 5 deliverables), performance log fields, metric definitions (lock, tracking error, centroiding error), known limits |
